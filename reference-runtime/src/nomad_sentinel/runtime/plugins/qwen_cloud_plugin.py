"""
Nomad Sentinel — Qwen Cloud Plugin
═══════════════════════════════════════════════════════════════════════
Drops Qwen Cloud into the runtime as one more InferencePlugin, exactly
like llama_cpp_plugin.py or ollama_plugin.py — same contract, same
auto-discovery, zero changes to PluginRegistry or InferenceRouter.

What makes this plugin different from the others: it is the ONLY plugin
with requires_network=True. That single flag is what CapabilityDetector
and ModeSwitcher use to decide whether this plugin is even attemptable
right now — if the device is offline or the link budget is too tight,
the router never calls infer() here and falls straight to a local
plugin (llama.cpp / the Guardian heuristics), never raising an error
the caller has to handle. Graceful degradation is a property of the
router, this plugin just has to be honest about what it needs.

Why it exists in Nomad Sentinel specifically
----------------------------------------------
Black Dragon's cognitive layer (Bat / Hermit Crab / Squid, see
bhs/cognition.py) is deliberately simple, fast, rule-based arithmetic —
correct for the common case, but it can't explain *why* it vetoed an
action, and it has no way to reason about a compound, ambiguous fault
pattern it wasn't explicitly coded for. This plugin gives
CloudAugmentedCognition (bhs/cloud_cognition.py) a way to hand the same
telemetry to Qwen Cloud and get back a structured, explainable risk
assessment — used only when ModeSwitcher says the network budget allows
it (Workhorse mode). Guardian mode never touches this file.

Endpoint
--------
Uses Qwen Cloud's OpenAI-compatible chat completions endpoint
(DashScope-compatible). Swap QWEN_BASE_URL to point at a self-hosted
Alibaba Cloud PAI-EAS deployment instead of the public Qwen Cloud
endpoint without touching any other code — that's the point of the
plugin boundary.
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from plugin_base import InferencePlugin, PluginCapabilities, PluginHealthStatus, PluginInferenceResult


QWEN_BASE_URL = os.getenv(
    "QWEN_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
QWEN_API_KEY  = os.getenv("QWEN_API_KEY", "")
QWEN_TIMEOUT  = 20   # seconds — kept short; this plugin must never stall the reflex loop

# Structured output contract the cognition layer parses. Keeping this in
# the plugin (not the caller) means any prompt/schema change is a
# one-file diff.
COGNITION_SYSTEM_PROMPT = """You are the cognitive-reasoning layer of an \
industrial structural-health monitoring system. You receive a JSON \
telemetry summary with risk_field_mean (panel-wide average risk) AND \
risk_field_max (the single worst cell). A large gap between the two means \
a small, severe, spatially concentrated fault -- treat a high \
risk_field_max as serious even when risk_field_mean looks nominal; a \
mean-only view would miss it entirely, which is precisely the failure \
mode you exist to avoid. Respond with ONLY a JSON object, no prose, no \
markdown fences, matching this schema:
{
  "risk_mean": <float 0-1>,
  "rul_seconds": <float or null>,
  "recommended_action": one of ["do_nothing","reduce_speed","redistribute_load","isolate_zone"],
  "veto_reasoning": "<one sentence, plain language, for a human operator>",
  "confidence": <float 0-1>
}
Never recommend "quick_patch_ignore" under any circumstance - it is always vetoed."""


class QwenCloudPlugin(InferencePlugin):
    """Talks to Qwen Cloud's OpenAI-compatible endpoint."""

    engine_id = "qwen_cloud"

    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            engine_name           = "Qwen Cloud",
            engine_version         = os.getenv("QWEN_MODEL", "qwen-plus"),
            supports_streaming      = False,   # cognition loop consumes one shot, not a stream
            supports_chat_format    = True,
            requires_network         = True,    # the flag ModeSwitcher keys on
            requires_gpu             = False,   # runs on Alibaba Cloud, not the edge device
            typical_formats           = ["api"],
        )

    def health_check(self) -> PluginHealthStatus:
        """Cheap reachability check — does NOT spend a real inference call."""
        if not QWEN_API_KEY:
            return PluginHealthStatus(healthy=False, message="QWEN_API_KEY not set")
        try:
            req = urllib.request.Request(
                f"{QWEN_BASE_URL}/models",
                headers={"Authorization": f"Bearer {QWEN_API_KEY}"},
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    return PluginHealthStatus(healthy=True, message="Qwen Cloud reachable")
                return PluginHealthStatus(healthy=False, message=f"Qwen Cloud returned HTTP {resp.status}")
        except urllib.error.URLError as e:
            return PluginHealthStatus(healthy=False, message=f"Qwen Cloud unreachable: {e}")
        except Exception as e:
            return PluginHealthStatus(healthy=False, message=f"health check failed: {e}")

    def infer(
        self,
        model_id: str,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> PluginInferenceResult:
        t0 = time.time()

        messages = [{"role": "system", "content": system_prompt or COGNITION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}]

        payload = json.dumps({
            "model":       model_id or os.getenv("QWEN_MODEL", "qwen-plus"),
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{QWEN_BASE_URL}/chat/completions",
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {QWEN_API_KEY}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=QWEN_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            return PluginInferenceResult(
                success=False,
                error=f"Qwen Cloud unreachable: {e}",
                latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return PluginInferenceResult(
                success=False, error=str(e), latency_ms=(time.time() - t0) * 1000,
            )

        latency_ms = (time.time() - t0) * 1000
        try:
            choice       = data["choices"][0]["message"]["content"]
            usage        = data.get("usage", {})
            prompt_tok   = usage.get("prompt_tokens", 0)
            output_tok   = usage.get("completion_tokens", 0)
        except (KeyError, IndexError) as e:
            return PluginInferenceResult(
                success=False, error=f"unexpected Qwen Cloud response shape: {e}",
                latency_ms=latency_ms, raw_engine_meta={"raw": data},
            )

        return PluginInferenceResult(
            success        = True,
            response_text  = choice,
            prompt_tokens   = prompt_tok,
            output_tokens   = output_tok,
            latency_ms      = latency_ms,
            raw_engine_meta  = {"model": data.get("model"), "id": data.get("id")},
        )

    def estimate_ram_gb(self, model_id: str) -> float:
        # Runs entirely on Alibaba Cloud infrastructure — zero device RAM cost.
        return 0.0

    def describe(self) -> str:
        return f"Qwen Cloud ({os.getenv('QWEN_MODEL', 'qwen-plus')}) via {QWEN_BASE_URL}"


# ═══════════════════════════════════════════════════════════════════════════
#  Self-test
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    plugin = QwenCloudPlugin()
    print("Capabilities:", plugin.capabilities())

    health = plugin.health_check()
    print(f"\nHealth: healthy={health.healthy} — {health.message}")

    if health.healthy:
        result = plugin.infer(
            model_id=os.getenv("QWEN_MODEL", "qwen-plus"),
            prompt=json.dumps({
                "risk_field_mean": 0.42, "damage_mean": 0.11,
                "spike_activity": 0.08, "scenario": "compound_heat_vibration_stress",
            }),
        )
        print(f"\nTest inference: success={result.success}")
        print(f"  Response: {result.response_text}")
    else:
        print("\nSkipping live call — set QWEN_API_KEY to test against Qwen Cloud")
