"""
Specification Agent.

Converts a natural-language prompt into a structured, Pydantic-validated
`SystemSpec`. Per the constitution (6.1), Codex/the generator must never see
a raw prompt -- only an approved SystemSpec.

Two extraction backends are supported:

1. ``heuristic`` (always available, zero external dependencies): a regex /
   keyword based extractor tuned for the industrial-monitoring MVP use case
   (pumps, motors, bearings, pipelines, structural panels). This is what
   runs by default and what the required demonstration prompt in the
   constitution is verified against.

2. ``llm``: if ``OPENAI_API_KEY`` is set in the environment, the same job is
   delegated to an OpenAI chat-completions call that is instructed to
   return *only* the SystemSpec JSON. The result is still validated with the
   same Pydantic model before anything downstream ever sees it -- the LLM is
   never trusted blindly (constitution 6.1, 6.3).

If the LLM backend is unavailable or returns something that fails
validation, the agent automatically falls back to the heuristic backend so
the product keeps working without any API key (this is what the sandboxed
/ offline evaluation environment relies on).
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional, Tuple

from .models import (
    ActuatorSpec,
    ClarifyingQuestion,
    PredictionSpec,
    ProjectMeta,
    ReflexRule,
    SensorSpec,
    SimulationSpec,
    SystemSpec,
)

# --------------------------------------------------------------------------
# Domain knowledge tables used by the heuristic extractor
# --------------------------------------------------------------------------

SENSOR_KEYWORDS = {
    "vibration": {"type": "vibration", "unit": "mm_s", "default_normal": [0, 4],
                  "default_warning": 7, "default_critical": 10, "sample_rate_hz": 100},
    "temperature": {"type": "temperature", "unit": "celsius", "default_normal": [20, 70],
                     "default_warning": 90, "default_critical": 105, "sample_rate_hz": 1},
    "pressure": {"type": "pressure", "unit": "bar", "default_normal": [1, 8],
                 "default_warning": 10, "default_critical": 12, "sample_rate_hz": 10},
    "strain": {"type": "strain", "unit": "microstrain", "default_normal": [0, 500],
               "default_warning": 800, "default_critical": 1200, "sample_rate_hz": 50},
    "current": {"type": "current", "unit": "amps", "default_normal": [0, 20],
                "default_warning": 28, "default_critical": 35, "sample_rate_hz": 20},
    "flow": {"type": "flow", "unit": "l_min", "default_normal": [10, 100],
             "default_warning": 5, "default_critical": 2, "sample_rate_hz": 5},
    "level": {"type": "level", "unit": "percent", "default_normal": [20, 90],
              "default_warning": 95, "default_critical": 99, "sample_rate_hz": 1},
}

SENSOR_ALIASES = {
    "vibration": "vibration", "vibrations": "vibration", "vib": "vibration",
    "temperature": "temperature", "temp": "temperature", "thermal": "temperature",
    "pressure": "pressure",
    "strain": "strain", "stress": "strain",
    "current": "current", "amperage": "current",
    "flow": "flow", "flow rate": "flow",
    "level": "level",
}

ACTION_KEYWORDS = {
    "shutdown": {"shut down", "shutdown", "shut off", "stop", "halt", "power off"},
    "reduce_speed": {"reduce speed", "slow down", "decrease speed", "throttle down", "lower speed"},
    "increase_cooling": {"increase cooling", "cool down", "activate cooling", "turn on cooling"},
    "isolate_zone": {"isolate", "isolate zone", "seal off"},
    "alert_operator": {"alert operator", "notify operator", "send alert", "page operator"},
    "switch_to_backup": {"switch to backup", "failover", "switch to redundant"},
}

DOMAIN_KEYWORDS = {
    "pump": "pump", "motor": "motor", "bearing": "bearing",
    "pipeline": "pipeline", "panel": "structural_panel", "compressor": "compressor",
    "fan": "fan", "turbine": "turbine",
}

NUMBER_RE = re.compile(r"(-?\d+(?:\.\d+)?)")


def _find_numbers_near(text: str, keyword_span: Tuple[int, int], window: int = 40) -> List[float]:
    start = max(0, keyword_span[0] - window)
    end = min(len(text), keyword_span[1] + window)
    snippet = text[start:end]
    return [float(n) for n in NUMBER_RE.findall(snippet)]


def _detect_subject_name(prompt: str) -> str:
    low = prompt.lower()
    for kw, canonical in DOMAIN_KEYWORDS.items():
        if kw in low:
            return canonical
    return "industrial-system"


def _detect_sensors(prompt: str) -> Tuple[List[SensorSpec], List[str]]:
    low = prompt.lower()
    sensors: List[SensorSpec] = []
    assumptions: List[str] = []
    seen_types = set()

    for alias, canonical in SENSOR_ALIASES.items():
        if canonical in seen_types:
            continue
        idx = low.find(alias)
        if idx == -1:
            continue
        seen_types.add(canonical)
        defaults = SENSOR_KEYWORDS[canonical]
        span = (idx, idx + len(alias))
        nearby_numbers = _find_numbers_near(prompt, span, window=60)

        warning = defaults["default_warning"]
        critical = defaults["default_critical"]
        used_default = True

        # try to associate explicit thresholds mentioned near this sensor
        # keyword: "above 7 mm/s" -> warning-ish, "10 mm/s" -> critical-ish.
        if nearby_numbers:
            nearby_numbers_sorted = sorted(nearby_numbers)
            if canonical in {"flow"}:
                # lower is worse for flow
                nearby_numbers_sorted = sorted(nearby_numbers, reverse=True)
            if len(nearby_numbers_sorted) >= 2:
                warning, critical = nearby_numbers_sorted[0], nearby_numbers_sorted[-1]
                used_default = False
            elif len(nearby_numbers_sorted) == 1:
                critical = nearby_numbers_sorted[0]
                used_default = False

        if used_default:
            assumptions.append(
                f"No explicit thresholds found for '{canonical}' sensor; used safe defaults "
                f"(warning={warning}, critical={critical} {defaults['unit']})."
            )

        sensors.append(
            SensorSpec(
                id=f"{canonical}_1",
                type=canonical,
                unit=defaults["unit"],
                sample_rate_hz=defaults["sample_rate_hz"],
                normal_range=list(defaults["default_normal"]),
                warning_threshold=warning,
                critical_threshold=critical,
            )
        )

    if not sensors:
        assumptions.append(
            "No recognizable sensor keywords found in the prompt; defaulted to a single "
            "vibration sensor with standard industrial thresholds."
        )
        defaults = SENSOR_KEYWORDS["vibration"]
        sensors.append(
            SensorSpec(
                id="vibration_1",
                type="vibration",
                unit=defaults["unit"],
                sample_rate_hz=defaults["sample_rate_hz"],
                normal_range=list(defaults["default_normal"]),
                warning_threshold=defaults["default_warning"],
                critical_threshold=defaults["default_critical"],
            )
        )
    return sensors, assumptions


def _detect_actions(prompt: str) -> List[str]:
    low = prompt.lower()
    found = ["do_nothing"]
    for action, phrases in ACTION_KEYWORDS.items():
        if any(p in low for p in phrases):
            found.append(action)
    if len(found) == 1:
        found.append("shutdown")  # every monitoring system needs at least one real safety action
    return found


def _consecutive_samples_from_prompt(prompt: str, default: int = 5) -> int:
    m = re.search(r"(\d+)\s+(?:consecutive\s+)?samples", prompt.lower())
    if m:
        return max(1, int(m.group(1)))
    return default


def _build_reflex_rules(
    sensors: List[SensorSpec], allowed_actions: List[str], prompt: str
) -> Tuple[List[ReflexRule], List[str]]:
    rules: List[ReflexRule] = []
    assumptions: List[str] = []
    consecutive = _consecutive_samples_from_prompt(prompt)

    warning_action = "reduce_speed" if "reduce_speed" in allowed_actions else (
        "alert_operator" if "alert_operator" in allowed_actions else allowed_actions[-1]
    )
    critical_action = "shutdown" if "shutdown" in allowed_actions else allowed_actions[-1]

    for sensor in sensors:
        lower_is_worse = sensor.type == "flow"
        comparator_warn = "<=" if lower_is_worse else ">="
        comparator_crit = "<=" if lower_is_worse else ">="

        rules.append(
            ReflexRule(
                id=f"{sensor.id}_warning",
                sensor_id=sensor.id,
                comparator=comparator_warn,
                threshold=sensor.warning_threshold,
                consecutive_samples=consecutive,
                action=warning_action,
                severity="warning",
                ignore_isolated_spikes=True,
            )
        )
        rules.append(
            ReflexRule(
                id=f"{sensor.id}_critical",
                sensor_id=sensor.id,
                comparator=comparator_crit,
                threshold=sensor.critical_threshold,
                consecutive_samples=1,
                action=critical_action,
                severity="critical",
                ignore_isolated_spikes=False,
            )
        )
    if not rules:
        assumptions.append("No sensors available to derive reflex rules from.")
    return rules, assumptions


def _offline_required(prompt: str) -> bool:
    low = prompt.lower()
    if "offline" in low or "no cloud" in low or "without cloud" in low or "no internet" in low:
        return True
    if "cloud" in low and "offline" not in low and "without cloud" not in low:
        return False
    return True  # safe default per constitution (industrial edge devices)


def heuristic_extract(prompt: str) -> Tuple[SystemSpec, List[ClarifyingQuestion]]:
    """Rule-based extraction. Deterministic, no external calls, always available."""
    subject = _detect_subject_name(prompt)
    sensors, sensor_assumptions = _detect_sensors(prompt)

    allowed_actions = _detect_actions(prompt)
    reflex_rules, rule_assumptions = _build_reflex_rules(sensors, allowed_actions, prompt)

    assumptions = [*sensor_assumptions, *rule_assumptions]
    questions: List[ClarifyingQuestion] = []

    project_name = f"{subject}-monitor"
    description = prompt.strip()
    if len(description) > 280:
        description = description[:277] + "..."

    offline = _offline_required(prompt)
    if "offline" not in prompt.lower() and "cloud" not in prompt.lower():
        questions.append(
            ClarifyingQuestion(
                field="project.offline_required",
                question="Should the generated system work fully offline (no cloud access)?",
                default_used="true",
            )
        )

    spec = SystemSpec(
        project=ProjectMeta(
            name=project_name,
            description=description,
            domain="industrial_monitoring",
            target_platform="generic_arm_edge",
            offline_required=offline,
        ),
        sensors=sensors,
        actuators=[ActuatorSpec(id=f"{subject}_controller", allowed_actions=allowed_actions)],
        reflex_rules=reflex_rules,
        prediction=PredictionSpec(enabled=True, method="moving_trend", horizon_seconds=30),
        operating_modes=["normal", "safety_first", "degraded"],
        simulation=SimulationSpec(
            duration_seconds=60,
            scenarios=["normal", "gradual_fault", "noise_spike", "critical_fault"],
        ),
        metrics=[
            "detection_latency_ms",
            "false_alarms",
            "correct_action_rate",
            "final_damage_proxy",
        ],
        assumptions=assumptions,
        warnings=[],
    )
    return spec, questions


LLM_SYSTEM_PROMPT = """You are the Specification Agent for Black Dragon Studio.
Convert the user's natural-language Physical AI monitoring request into a
SINGLE JSON object that matches this exact structure (no prose, no markdown
fences, JSON only):

{
  "project": {"name": str, "description": str, "domain": "industrial_monitoring",
              "target_platform": "generic_arm_edge", "offline_required": bool},
  "sensors": [{"id": str, "type": one of ["vibration","temperature","pressure",
              "strain","current","flow","level","generic"], "unit": str,
              "sample_rate_hz": number, "normal_range": [low, high],
              "warning_threshold": number, "critical_threshold": number}],
  "actuators": [{"id": str, "allowed_actions": [subset of ["do_nothing",
              "reduce_speed","shutdown","isolate_zone","increase_cooling",
              "alert_operator","switch_to_backup"]]}],
  "reflex_rules": [{"id": str, "sensor_id": str, "comparator": one of
              [">=","<=",">","<","=="], "threshold": number,
              "consecutive_samples": int, "action": str,
              "severity": "warning"|"critical", "ignore_isolated_spikes": bool}],
  "prediction": {"enabled": bool, "method": "moving_trend", "horizon_seconds": number},
  "operating_modes": [subset of ["normal","safety_first","energy_saving","maintenance","degraded"]],
  "simulation": {"duration_seconds": number, "scenarios": [str, ...]},
  "metrics": [str, ...],
  "assumptions": [str, ...],
  "warnings": [str, ...]
}

Every action referenced by a reflex_rule MUST be included in some actuator's
allowed_actions. Every sensor_id referenced by a reflex_rule MUST exist in
sensors. Prefer deterministic, conservative thresholds. Record every
assumption you had to make in "assumptions". Output ONLY the JSON object.
"""


def llm_extract(prompt: str) -> Optional[Tuple[SystemSpec, List[ClarifyingQuestion]]]:
    """Attempts extraction via an OpenAI-compatible chat completion. Returns
    None (never raises) if no API key is configured or the call/parse fails,
    so callers can transparently fall back to the heuristic extractor."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        import urllib.request

        model = os.environ.get("SPEC_AGENT_MODEL", "gpt-5.6")
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        data = json.loads(content)
        spec = SystemSpec.model_validate(data)
        return spec, []
    except Exception:
        return None


def extract_spec(prompt: str) -> Tuple[SystemSpec, List[ClarifyingQuestion], str]:
    """Returns (spec, clarifying_questions, source) where source is
    'llm' or 'heuristic'."""
    llm_result = llm_extract(prompt)
    if llm_result is not None:
        spec, questions = llm_result
        return spec, questions, "llm"
    spec, questions = heuristic_extract(prompt)
    return spec, questions, "heuristic"
