#!/usr/bin/env python3
"""
Nomad Sentinel — Edge/Cloud Orchestration Demo
═══════════════════════════════════════════════════════════════════════
Runs Scenario D (the compound heat+vibration+stress fault — the one
Black Dragon's own README flags as hardest for rule-based cognition)
through the full merged stack:

  sensing (OpticalSkin) -> reflex kernel -> ModeSwitcher (fed a
  simulated flaky network) -> CloudAugmentedCognition, which escalates
  to Qwen Cloud in Stallion mode and falls back to the local Bat /
  Hermit Crab / Squid heuristics whenever the link is down.

This is the script the submission video should show running: it
proves the graceful-degradation claim isn't just a diagram, by
actually cutting the simulated network partway through and showing
the system keep making decisions anyway.

Usage:
    python scripts/run_edge_cloud_demo.py --steps 400 --out outputs/edge_cloud_log.json

Set QWEN_API_KEY to run against the real Qwen Cloud endpoint; without
it, this uses a local mock cloud response so the demo still runs
end-to-end offline (clearly labeled in the output as mocked).
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

# bhs/* uses package-relative imports (from .physics import ...), so it must be
# imported as a real package: put src/ on the path, not the bhs/ dir itself.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
# runtime/core and runtime/plugins use flat sys.path-style imports (matching
# how PluginRegistry.discover() and server.py already load them), so those
# directories go on the path directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "nomad_sentinel", "runtime", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "nomad_sentinel", "runtime", "plugins"))

import numpy as np

from nomad_sentinel.bhs.physics import Panel, PanelConfig
from nomad_sentinel.bhs.sensing import OpticalSkin
from nomad_sentinel.bhs.reflex import ReflexKernel
from nomad_sentinel.bhs.scenarios import SCENARIOS
from nomad_sentinel.bhs.cloud_cognition import CloudAugmentedCognition
from mode_switcher import ModeSwitcher, Mode
from device_monitor import DeviceSnapshot
from plugin_registry import PluginRegistry
from inference_router import InferenceRouter
from plugin_base import InferencePlugin, PluginCapabilities, PluginHealthStatus, PluginInferenceResult


class MockQwenCloudPlugin(InferencePlugin):
    """
    Used when QWEN_API_KEY is not set, so this demo runs fully offline.
    Same response schema the real qwen_cloud_plugin.py produces, so
    CloudAugmentedCognition can't tell the difference -- swapping this
    for the real plugin is a zero-code-change swap, which is the point.
    """
    engine_id = "qwen_cloud"

    def capabilities(self):
        return PluginCapabilities(engine_name="Qwen Cloud (mocked, offline demo)", requires_network=True)

    def health_check(self):
        return PluginHealthStatus(healthy=True, message="mock -- always healthy")

    def infer(self, model_id, prompt, system_prompt="", max_tokens=512, temperature=0.2):
        t0 = time.time()
        data = json.loads(prompt)
        risk = data["risk_field_mean"]
        surviving = data["surviving_actions"]
        if risk > 0.5 and "isolate_zone" in surviving:
            action = "isolate_zone"
            reasoning = "Compound thermal+vibration+load signature -- isolate before propagation accelerates."
        elif risk > 0.2 and "reduce_speed" in surviving:
            action = "reduce_speed"
            reasoning = "Elevated but not yet critical risk -- reduce load while trend is confirmed."
        else:
            action = "do_nothing" if "do_nothing" in surviving else surviving[0]
            reasoning = "Risk within nominal bounds."
        return PluginInferenceResult(
            success=True,
            response_text=json.dumps({
                "risk_mean": risk, "rul_seconds": None,
                "recommended_action": action, "veto_reasoning": reasoning,
                "confidence": 0.8,
            }),
            latency_ms=(time.time() - t0) * 1000 + 45,  # simulate realistic cloud RTT
        )


def build_router():
    """Real qwen_cloud_plugin.py if QWEN_API_KEY is set, mock otherwise."""
    if os.getenv("QWEN_API_KEY"):
        registry = PluginRegistry()
        registry.discover()
        print("[demo] QWEN_API_KEY set -- using real Qwen Cloud plugin")
    else:
        class _FixedRegistry:
            def __init__(self):
                self._plugin = MockQwenCloudPlugin()
            def safe_infer(self, engine_id, model_id, prompt, system_prompt="", max_tokens=512):
                return self._plugin.infer(model_id, prompt, system_prompt, max_tokens)
        registry = _FixedRegistry()
        print("[demo] QWEN_API_KEY not set -- using local mock cloud plugin (offline demo mode)")
    return InferenceRouter(registry=registry)


def flaky_network_snapshot(step: int, total_steps: int) -> DeviceSnapshot:
    """
    Simulated device conditions: network is up for the first third,
    drops for the middle third (the interesting part -- this is where
    Guardian mode has to carry the whole decision), then recovers.
    """
    third = total_steps // 3
    online = not (third <= step < 2 * third)
    return DeviceSnapshot(
        timestamp=time.time(), cpu_percent=35.0, ram_used_gb=2.0, ram_total_gb=8.0,
        ram_free_gb=6.0, ram_percent=25.0, cpu_temp_c=48.0,
        network_online=online, network_speed="fast" if online else "none",
        battery_percent=None, battery_plugged=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--scenario", default="D", choices=list(SCENARIOS.keys()))
    ap.add_argument("--out", default="outputs/edge_cloud_log.json")
    args = ap.parse_args()

    cfg = PanelConfig()
    panel = Panel(cfg, seed=SCENARIOS[args.scenario].seed)
    SCENARIOS[args.scenario].apply(panel)
    rng = np.random.default_rng(SCENARIOS[args.scenario].seed + 1)

    optical = OpticalSkin(cfg.height, cfg.width, dtype=cfg.dtype)
    reflex = ReflexKernel(cfg.height, cfg.width, dtype=cfg.dtype)
    router = build_router()
    cognition = CloudAugmentedCognition(cfg.height, cfg.width, dt=cfg.dt, inference_router=router)
    switcher = ModeSwitcher()

    # ModeSwitcher's hysteresis (30s to upgrade, 10s to downgrade -- see
    # mode_switcher.py Thresholds) is keyed on wall-clock time.time(), which
    # is correct for production but would make a compressed simulation loop
    # sit at NOMAD forever since real elapsed time barely moves. Advance a
    # fake clock by 5s per step here (matching the "poll every 5s" cadence
    # from Nomad's own README) so the demo actually exercises hysteresis at
    # a watchable pace instead of disabling it.
    import mode_switcher as _ms_module
    fake_clock = {"t": time.time()}
    _ms_module.time.time = lambda: fake_clock["t"]

    prev_stress = panel.stress.copy()
    log = []

    for step in range(args.steps):
        panel.step()
        T_read = optical.read_temperature(panel.T, rng)
        stress_read = optical.read_stress(panel.stress, rng)
        spike_rate, _fired = reflex.step(T_read, stress_read, panel.vib, prev_stress)
        prev_stress = stress_read

        cognition.update(T_read, stress_read, panel.damage)

        snap = flaky_network_snapshot(step, args.steps)
        fake_clock["t"] += 5.0
        decision = switcher.decide(snap)

        result = cognition.step(spike_rate, float(panel.damage.mean()), mode=decision.mode)

        if result.action == "reduce_speed":
            panel.speed_factor = 0.4
        elif result.action == "isolate_zone":
            panel.speed_factor = 0.0
        elif result.action == "do_nothing":
            panel.speed_factor = min(panel.speed_factor + 0.05, 1.0)

        log.append({
            "step": step, "t": panel.t, "mode": decision.mode.value,
            "network_online": snap.network_online,
            "source": result.source, "action": result.action,
            "risk_mean": round(result.risk_mean, 4),
            "veto_reasoning": result.veto_reasoning,
            "latency_ms": round(result.latency_ms, 2),
        })

        if step % 50 == 0:
            print(f"step {step:4d}  mode={decision.mode.value:9s}  source={result.source:10s}  "
                  f"action={result.action:18s}  risk={result.risk_mean:.3f}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({
            "scenario": args.scenario,
            "steps": args.steps,
            "cloud_calls": sum(1 for e in log if e["source"] == "qwen_cloud"),
            "local_fallback_calls": sum(1 for e in log if e["source"] == "local"),
            "log": log,
        }, f, indent=2)

    print(f"\nWrote {args.out}")
    print(f"Cloud-sourced decisions: {sum(1 for e in log if e['source'] == 'qwen_cloud')}")
    print(f"Local-fallback decisions: {sum(1 for e in log if e['source'] == 'local')}")


if __name__ == "__main__":
    main()
