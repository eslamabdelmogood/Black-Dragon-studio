import json
import sys
import os

import numpy as np

# NOTE: src/ itself must be on the path (not just runtime/core and
# runtime/plugins) -- without it, `import nomad_sentinel` can silently
# resolve to an unrelated editable-installed copy of the package
# elsewhere on the machine instead of this repo's source tree. Bit us
# once during development; keeping this comment so it doesn't happen
# again silently.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "nomad_sentinel", "runtime", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "nomad_sentinel", "runtime", "plugins"))

from nomad_sentinel.bhs.cloud_cognition import CloudAugmentedCognition
from mode_switcher import Mode
from inference_router import InferenceRouter
from plugin_base import PluginInferenceResult


class _FakeRegistry:
    """Stands in for PluginRegistry -- returns a fixed structured response,
    matching the schema QwenCloudPlugin's real infer() produces."""

    def safe_infer(self, engine_id, model_id, prompt, system_prompt="", max_tokens=512):
        data = json.loads(prompt)
        return PluginInferenceResult(
            success=True,
            response_text=json.dumps({
                "risk_mean": data["risk_field_mean"],
                "rul_seconds": 10.0,
                "recommended_action": "isolate_zone" if data["risk_field_mean"] > 0.35 else "do_nothing",
                "veto_reasoning": "test reasoning",
                "confidence": 0.9,
            }),
            latency_ms=5.0,
        )


def _cog_with_history():
    cog = CloudAugmentedCognition(height=4, width=4, dt=0.05, inference_router=InferenceRouter(registry=_FakeRegistry()))
    T = np.full((4, 4), 40.0)
    stress = np.full((4, 4), 20.0)
    damage = np.full((4, 4), 0.05)
    for _ in range(3):
        T += 10
        stress += 8
        damage += 0.05
        cog.update(T, stress, damage)
    return cog, damage


def test_stallion_mode_uses_cloud_source():
    cog, damage = _cog_with_history()
    spike_rate = np.full((4, 4), 0.05)
    result = cog.step(spike_rate, float(damage.mean()), mode=Mode.STALLION)
    assert result.source == "qwen_cloud"
    assert result.veto_reasoning == "test reasoning"


def test_guardian_mode_never_touches_cloud():
    cog, damage = _cog_with_history()
    spike_rate = np.full((4, 4), 0.05)
    result = cog.step(spike_rate, float(damage.mean()), mode=Mode.GUARDIAN)
    assert result.source == "local"


def test_cloud_path_receives_risk_max_and_can_isolate_despite_low_mean():
    """
    Regression test for the diluted-hotspot fix: a severe, spatially tiny
    fault should keep risk_mean low (diluted across the field) while
    risk_max is near-critical. The cloud path must see BOTH values and be
    allowed to isolate on risk_max alone, even though risk_mean never
    crosses the veto threshold the local path is gated on.
    """
    captured = {}

    class _CapturingRegistry:
        def safe_infer(self, engine_id, model_id, prompt, system_prompt="", max_tokens=512):
            data = json.loads(prompt)
            captured["risk_field_mean"] = data["risk_field_mean"]
            captured["risk_field_max"] = data["risk_field_max"]
            captured["surviving_actions"] = data["surviving_actions"]
            return PluginInferenceResult(
                success=True,
                response_text=json.dumps({
                    "risk_mean": data["risk_field_mean"], "rul_seconds": None,
                    "recommended_action": "isolate_zone", "veto_reasoning": "hotspot", "confidence": 0.9,
                }),
                latency_ms=5.0,
            )

    cog = CloudAugmentedCognition(height=6, width=6, dt=0.05, inference_router=InferenceRouter(registry=_CapturingRegistry()))
    T = np.full((6, 6), 40.0)
    stress = np.full((6, 6), 20.0)
    damage = np.zeros((6, 6))
    # One severe, held-steady hotspot cell -- rest of the 36-cell field is
    # nominal, so risk_mean stays tiny (dilution) while risk_max at this one
    # cell should clear the isolate threshold. Magnitudes chosen to mirror
    # Scenario E's real behaviour (risk_max ~0.96-0.98 there).
    T[3, 3] = 140.0
    stress[3, 3] = 140.0
    damage[3, 3] = 1.0
    for _ in range(3):
        cog.update(T, stress, damage)  # held steady -- slope ~0, so forecast doesn't need extrapolation to see it
    spike_rate = np.full((6, 6), 0.01)
    result = cog.step(spike_rate, float(damage.mean()), mode=Mode.STALLION)

    assert captured["risk_field_max"] > captured["risk_field_mean"]  # confirms real dilution in this fixture
    assert "isolate_zone" in captured["surviving_actions"]  # cloud-side veto pass let it through despite low mean
    assert result.source == "qwen_cloud"
    assert result.action == "isolate_zone"


def test_no_router_always_falls_back_local():
    cog = CloudAugmentedCognition(height=4, width=4, dt=0.05, inference_router=None)
    T = np.full((4, 4), 40.0)
    stress = np.full((4, 4), 20.0)
    damage = np.full((4, 4), 0.05)
    cog.update(T, stress, damage)
    cog.update(T + 10, stress + 8, damage + 0.05)
    spike_rate = np.full((4, 4), 0.05)
    result = cog.step(spike_rate, float(damage.mean()), mode=Mode.STALLION)
    assert result.source == "local"
