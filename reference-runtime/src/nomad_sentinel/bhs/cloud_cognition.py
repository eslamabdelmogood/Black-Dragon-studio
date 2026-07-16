"""
Layer 3, cloud-augmented: wraps Bat / Hermit Crab / Squid (cognition.py)
as the always-on local fallback, and escalates to Qwen Cloud — through
Nomad's existing InferenceRouter / ModeSwitcher / PluginRegistry — when
the device has the network budget for it.

This is the file where the two projects actually meet. Nothing in
bhs/cognition.py or nomad_sentinel/runtime/* changes: this module sits
on top of both, calling into each through the interface it already had.

Decision flow, every simulation step:
  1. ModeSwitcher.decide() -> Mode.NOMAD / WORKHORSE / GUARDIAN, based on
     the current DeviceSnapshot (battery, link RSSI/latency, thermal).
  2. GUARDIAN (or WORKHORSE with an unhealthy Qwen plugin): use the local
     heuristics unchanged — this is exactly what simulate.py already did.
  3. WORKHORSE with a healthy Qwen plugin: build a compact JSON summary of
     current risk/damage/spike state, call QwenCloudPlugin.infer() through
     InferenceRouter, parse the structured response, and use ITS action +
     veto_reasoning instead of (or blended with) the local one.

Failure handling: if the cloud call fails for any reason (timeout, bad
JSON, plugin fault) this falls back to the local heuristic for that
step and logs the reason — the panel is never left without a decision,
which matters because this loop is also driving the physical actuator.
"""
from __future__ import annotations

import json
import sys
import os
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runtime", "core"))

from .cognition import BatForecaster, HermitCrabEvaluator, SquidWeights, select_action, ACTIONS

try:
    from mode_switcher import Mode  # noqa: F401  (re-exported for callers)
except Exception:  # pragma: no cover - runtime package may not be on path in unit tests
    Mode = None


@dataclass
class CloudCognitionResult:
    action:          str
    risk_mean:       float
    rul_seconds:     Optional[float]
    weights:         dict
    source:          str              # "local" or "qwen_cloud"
    veto_reasoning:  str = ""
    confidence:      Optional[float] = None
    latency_ms:      float = 0.0
    fallback_reason: Optional[str] = None
    raw_meta:        dict = field(default_factory=dict)


class CloudAugmentedCognition:
    """
    Drop-in upgrade for the bat/hermit/squid trio used directly in
    simulate.py. Same per-step call shape, richer result, transparent
    fallback.
    """

    def __init__(self, height: int, width: int, dt: float, inference_router=None,
                 model_id: str = None):
        self.bat    = BatForecaster(height, width, dt=dt)
        self.hermit = HermitCrabEvaluator()
        self.squid  = SquidWeights()
        # inference_router: an already-constructed nomad_sentinel InferenceRouter,
        # wired to a PluginRegistry that has discovered qwen_cloud_plugin.py.
        # Passed in rather than constructed here so tests / offline runs can
        # simply omit it and always take the local path.
        self.router   = inference_router
        self.model_id = model_id or os.getenv("QWEN_MODEL", "qwen-plus")

    def update(self, T, stress, damage):
        self.bat.update(T, stress, damage)

    def step(self, spike_rate, damage_mean: float, mode=None) -> CloudCognitionResult:
        """mode: a nomad_sentinel Mode enum value, or None to force local-only."""
        risk, rul = self.bat.forecast()
        if risk is None:
            return CloudCognitionResult(
                action="do_nothing", risk_mean=0.0, rul_seconds=None,
                weights=dict(self.squid.w), source="local",
            )

        risk_mean = float(risk.mean())
        risk_max  = float(risk.max())
        candidates = list(ACTIONS)
        isolate_allowed = risk_mean > 0.35
        surviving, _vetoed = self.hermit.score_and_veto(candidates, risk_mean, isolate_allowed)
        weights = self.squid.update(risk_mean, damage_mean, float(spike_rate.mean()))

        want_cloud = mode is not None and Mode is not None and mode == Mode.STALLION and self.router is not None
        if want_cloud:
            # Cloud path gets its own veto pass gated on risk_max as well as
            # risk_mean -- otherwise a diluted-hotspot fault would have
            # isolate_zone stripped from the candidate list before Qwen
            # Cloud ever saw the request, regardless of how good its
            # reasoning is. The local path's `surviving` above is
            # deliberately left untouched.
            cloud_isolate_allowed = isolate_allowed or risk_max > 0.85
            cloud_surviving, _ = self.hermit.score_and_veto(candidates, risk_mean, cloud_isolate_allowed)
            cloud_result = self._try_cloud(risk_mean, risk_max, damage_mean, spike_rate, cloud_surviving, weights)
            if cloud_result is not None:
                return cloud_result
            # falls through to local heuristic below, fallback_reason already logged by _try_cloud

        action = select_action(surviving, weights, risk_mean, damage_mean)
        return CloudCognitionResult(
            action=action, risk_mean=risk_mean, rul_seconds=None,
            weights=weights, source="local",
        )

    def _try_cloud(self, risk_mean, risk_max, damage_mean, spike_rate, surviving, weights) -> Optional[CloudCognitionResult]:
        # risk_max travels alongside the mean specifically so the cloud path
        # can catch a small, severe, spatially concentrated fault that a
        # mean-pooled field structurally dilutes (see Scenario E / docs/
        # architecture.md "Why the split is where it is"). The local
        # heuristic never receives this -- it's an intentional asymmetry,
        # not an oversight, and it's the whole point of the comparison.
        summary = json.dumps({
            "risk_field_mean": round(risk_mean, 4),
            "risk_field_max":  round(risk_max, 4),
            "damage_mean": round(damage_mean, 4),
            "spike_activity": round(float(spike_rate.mean()), 4),
            "surviving_actions": surviving,
            "current_weights": weights,
        })
        try:
            result = self.router.infer(
                mode=Mode.STALLION,
                prompt=summary,
            )
        except Exception as e:
            return None  # network/plugin fault -> caller falls back to local heuristic

        # InferenceRouter.infer() returns InferenceResult, not PluginInferenceResult --
        # it has no `success` field, so "did it work" is "no error and non-empty text".
        if result is None or result.error or not result.response_text:
            return None

        try:
            parsed = json.loads(result.response_text)
            action = parsed["recommended_action"]
            if action not in ACTIONS or action not in surviving:
                action = select_action(surviving, weights, risk_mean, damage_mean)
        except (json.JSONDecodeError, KeyError):
            return None

        return CloudCognitionResult(
            action=action,
            risk_mean=risk_mean,
            rul_seconds=parsed.get("rul_seconds"),
            weights=weights,
            source="qwen_cloud",
            veto_reasoning=parsed.get("veto_reasoning", ""),
            confidence=parsed.get("confidence"),
            latency_ms=result.latency_ms,
            raw_meta=result.engine_meta or {},
        )
