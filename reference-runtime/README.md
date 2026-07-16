# Nomad Sentinel

### A structural nervous system that reasons on Qwen Cloud when it can, and never stops reasoning when it can't

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Global AI Hackathon with Qwen Cloud — Track 5: EdgeAgent**

Nomad Sentinel merges two previously separate projects into one system
built specifically for the EdgeAgent brief — *"perceive via edge
sensors, reason via cloud APIs/Skills, and act locally… robust
edge-cloud orchestration under bandwidth/latency constraints…
graceful degradation in offline/weak-network scenarios"*:

| Layer | From | Role |
|---|---|---|
| **Sensing + reflex** | Black Dragon Runtime | Dense simulated FBG optical-skin mesh + an event-driven spiking reflex kernel, compiled to a real Arm Ethos-U NPU artifact. Always-on, local, µs-latency — never waits on a network round trip. |
| **Edge/cloud orchestration** | Nomad Runtime | `ModeSwitcher` decides every 5s whether current device + link conditions justify escalating to a cloud reasoning backend (`Stallion` mode) or must fall back to local rules (`Guardian`/`Nomad`/`Workhorse`). `PluginRegistry` auto-discovers inference backends with zero router changes. |
| **Cloud cognition** | New — `QwenCloudPlugin` | Drops Qwen Cloud into Nomad's existing plugin contract as the `Stallion`-mode engine. Produces structured risk/RUL/action output *and* a natural-language justification a human operator can read — something the original rule-based cognition layer could never do. |

Nothing about the sensing/reflex layer changed, and nothing about
Nomad's orchestration engine changed — the merge is entirely additive:
one new plugin file, one new cognition wrapper, one repurposed mode
(`Stallion`, previously disabled under different competition rules,
now pointed at Qwen Cloud instead of a local dev backend).

## Architecture

![Nomad Sentinel architecture diagram](docs/architecture.svg)

See [`docs/architecture.md`](docs/architecture.md) for the full diagram
and write-up. Short version:

```
Optical skin (sensing) → Reflex kernel (local, NPU)
                                │
                                ▼
                    ModeSwitcher (device + link conditions)
                        │                       │
                 Guardian/local          Stallion (network OK)
             Bat/HermitCrab/Squid              │
                        │              QwenCloudPlugin → Qwen Cloud
                        │           (via Alibaba Cloud infra)
                        └───────────┬───────────┘
                                    ▼
                         Actuator selection
                       (reduce speed / isolate /
                        redistribute / do nothing)
                                    │
                                    ▼
                    Dashboard + Alibaba Cloud OSS telemetry
```

## Try it

```bash
git clone <this-repo-url> && cd nomad-sentinel
python3 -m venv .venv && source .venv/bin/activate
pip install -e . -r requirements.txt

# Runs fully offline with a local mock of the Qwen Cloud response —
# proves the whole plugin/mode-switching chain works end to end.
python scripts/run_edge_cloud_demo.py --steps 400 --out outputs/edge_cloud_log.json

# With a real Qwen Cloud key, the exact same script calls the real API:
export QWEN_API_KEY=<your-key>
python scripts/run_edge_cloud_demo.py --steps 400 --out outputs/edge_cloud_log.json
```

The demo runs Scenario D (compound heat+vibration+stress fault — the
hardest one for rule-based cognition, per Black Dragon's own scenario
notes) while simulating a network that's up for the first third of the
run, drops entirely for the middle third, and recovers for the last
third. The log shows the system escalating to `qwen_cloud` when it
can and falling back to local heuristics when it can't, with zero
uncaught exceptions and zero missed actuation decisions either way.

Everything from the original Black Dragon Runtime — the Arm NPU
pipeline, the reaction-time benchmark, the four fault scenarios, the
static dashboard — still runs unchanged; see
[`docs/ARM_OPTIMIZATION.md`](docs/ARM_OPTIMIZATION.md),
[`docs/NPU_PIPELINE.md`](docs/NPU_PIPELINE.md),
[`docs/REFLEX_KERNEL_BENCHMARK.md`](docs/REFLEX_KERNEL_BENCHMARK.md).

## Deploying on Alibaba Cloud

See [`deploy/README.md`](deploy/README.md). Short version: the API +
dashboard run on an Alibaba Cloud ECS instance; decision/telemetry
events are written to Alibaba Cloud OSS via
[`deploy/alibaba_oss_telemetry.py`](deploy/alibaba_oss_telemetry.py)
whenever Stallion mode produces a decision.

## Repository layout

```
src/nomad_sentinel/
  bhs/                     # Black Dragon: physics, sensing, reflex, cognition, scenarios
    cloud_cognition.py     # NEW — merges bhs cognition with Nomad's plugin/mode system
  runtime/
    core/                  # Nomad: mode_switcher, plugin_registry, capability_detector, ...
    plugins/
      qwen_cloud_plugin.py # NEW — Qwen Cloud as a Nomad InferencePlugin
      llama_cpp_plugin.py, guardian_plugin.py   # unchanged from Nomad Runtime
    api/                   # Flask API + dashboard
scripts/
  run_edge_cloud_demo.py   # NEW — the merged end-to-end demo (see above)
  run_scenarios.py, build_dashboard.py, reaction_time_benchmark.py, build_npu_model.py
deploy/
  alibaba_oss_telemetry.py # NEW — Alibaba Cloud OSS client
  README.md                # NEW — ECS deployment guide
docs/
  optical_skin_demo.html, dashboard.html, npu_artifacts/, ARM_OPTIMIZATION.md, ...
```

## Notes on scope

This is a simulation-first digital twin, not a certified monitoring
product — see the original Black Dragon Runtime notes for details on
what's illustrative vs. exactly reproducible. The orchestration layer
(mode switching, plugin architecture, graceful degradation) is real,
runnable, unit-tested code, not a mockup — see the smoke test output
referenced in `SUBMISSION.md`.
