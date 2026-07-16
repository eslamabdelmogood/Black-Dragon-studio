# Nomad Sentinel — Global AI Hackathon with Qwen Cloud submission

**Track:** 5 — EdgeAgent

## Stress-test results

Run yourself with `python scripts/stress_test_matrix.py` (fully offline,
uses a mock Qwen Cloud response — no API key needed to reproduce).

| Scenario | Cloud Only | Edge Only | Nomad Sentinel |
|---|---|---|---|
| Internet Lost | ❌ | ✅ | ✅ |
| High Latency | ❌ | ✅ | ✅ |
| Compound Fault (diluted hotspot) | ✅ | ❌ | ✅ |

- **Internet Lost / High Latency:** a naive cloud-only agent (no local
  fallback — a deliberately weak baseline, not part of the shipped
  library) produces zero valid actuator commands across 400 steps under
  either condition. `ModeSwitcher` already refuses to attempt the cloud
  path when `network_speed == "slow"`, so Nomad Sentinel never even
  risks the call; Edge Only never needed the network in the first place.
- **Compound Fault:** uses Scenario E, a small, severe, spatially
  concentrated fault on a 40x60-cell panel. The local heuristic
  (`cognition.py`) makes its decision from `risk_field.mean()` alone —
  which dilutes a hotspot covering under 1% of the panel below any
  reasonable escalation threshold. It never isolates within 400 steps;
  the fault sits there the entire run. The cloud path is given
  `risk_field_max` alongside the mean specifically so it can catch what
  the panel-wide average hides, and isolates within 1-6 steps with a
  plain-language explanation every time. This is a real, reproducible
  architectural property (see `docs/architecture.md` and
  `tests/test_cloud_cognition.py::test_cloud_path_receives_risk_max_and_can_isolate_despite_low_mean`),
  not a scripted demo.

## Project description (for the submission form)

Nomad Sentinel is a distributed structural-health-monitoring nervous
system that pairs a local, always-on sensing/reflex layer with a
cloud reasoning layer on Qwen Cloud, connected by an adaptive
edge-cloud orchestration engine that gracefully degrades when
connectivity is poor or absent.

A dense simulated fiber-optic sensor mesh ("optical skin") feeds an
event-driven spiking-neuron reflex kernel — compiled to a real Arm
Ethos-U NPU artifact, µs-latency, fully local — for immediate anomaly
detection. Above that sits a cognitive layer that forecasts risk,
vetoes unsafe actions, and selects an actuator response. That layer
runs two ways: locally, as fast deterministic heuristics, always
available; or via Qwen Cloud, which reasons over the same telemetry to
produce a richer risk assessment, remaining-useful-life estimate, and
a plain-language justification a human operator can actually read —
something the rule-based path can't produce.

A `ModeSwitcher` polls device and link conditions every 5 seconds and
decides which path to use, with hysteresis (cautious to upgrade, fast
to downgrade) so it never flaps. The system is provably robust to
connectivity loss: it never fails to produce an actuator decision,
and it never raises an uncaught exception into the control loop,
regardless of what the cloud call does. All of this is real, runnable
code — not a mockup — demonstrated end-to-end by
`scripts/run_edge_cloud_demo.py` against a simulated compound-fault
scenario with a simulated network outage in the middle of the run.

The backend (API + dashboard) runs on an Alibaba Cloud ECS instance;
decision and telemetry events are persisted to Alibaba Cloud OSS.

## Why EdgeAgent

The track brief asks for: *perceive via edge sensors, reason via cloud
APIs/Skills, and act locally; robust edge-cloud orchestration under
bandwidth/latency constraints; privacy-aware data handling; graceful
degradation in offline/weak-network scenarios.* Nomad Sentinel
addresses each directly:

- **Perceive via edge sensors, act locally** — the optical skin +
  reflex kernel + actuator selection never leave the device.
- **Reason via cloud APIs** — `QwenCloudPlugin` is Qwen Cloud dropped
  into an existing, generic plugin contract, used specifically for the
  reasoning workload (forecasting, veto explanation) that benefits from
  it, not bolted on as a wrapper around everything.
- **Robust edge-cloud orchestration under bandwidth/latency
  constraints** — `ModeSwitcher`'s four-tier mode ladder with
  asymmetric hysteresis, tested live against a simulated outage.
- **Privacy-aware data handling** — only aggregated risk/damage/spike
  summaries are sent to Qwen Cloud, never raw sensor streams.
- **Graceful degradation in offline/weak-network scenarios** — proven,
  not asserted: the demo script runs the exact same scenario through a
  network outage and shows zero missed decisions.

## Submission checklist

- [ ] Public repository with an OSI license visible in the About section (MIT — `LICENSE` is in place, verify GitHub detects it after push)
- [ ] Alibaba Cloud deployment proof: link to `deploy/alibaba_oss_telemetry.py` + `aliyun oss ls` output or console screenshot (see `deploy/README.md` §4)
- [ ] Architecture diagram: `docs/architecture.md` (text/ASCII version); consider exporting the rendered diagram from this conversation as `docs/architecture.svg` or `.png` for a more polished submission
- [ ] ~3 minute demo video (see outline below), uploaded to YouTube/Vimeo/Facebook, public
- [ ] Text description — use the "Project description" section above
- [ ] Track identified — Track 5: EdgeAgent
- [ ] Optional: blog/social post for the Blog Post Prize

## Suggested video outline (~3 min)

1. **0:00–0:20** — The problem: fixed-point sensors are blind between
   sensors and slow to react; show `docs/optical_skin_demo.html` (dense
   skin vs sparse sensors) briefly.
2. **0:20–0:50** — Architecture walkthrough using `docs/architecture.md`'s
   diagram: sensing → reflex → orchestration → Guardian/local vs
   Stallion/Qwen Cloud → actuator.
3. **0:50–1:40** — Live run of `run_edge_cloud_demo.py`: point out the
   per-step log showing `mode=` and `source=` changing as the
   simulated network drops (~1:10) and recovers (~1:30). This is the
   single most important thing to show live — it's the proof, not a
   claim.
4. **1:40–2:20** — Qwen Cloud's actual value-add: show a `veto_reasoning`
   string from a Stallion-mode decision and contrast it with the local
   heuristic's bare action label — "here's what you get that a rule
   engine can't give you."
5. **2:20–2:50** — Alibaba Cloud deployment: dashboard running on the
   ECS instance, `aliyun oss ls` showing an uploaded run log.
6. **2:50–3:00** — Close: real-world relevance (remote/low-connectivity
   industrial infrastructure), and that every layer shown is real,
   runnable code linked in the repo.

## Honest scope notes

- This remains a simulation-first digital twin (no physical panel) —
  same caveat Black Dragon Runtime always carried. The Arm NPU
  compilation and reaction-time benchmarks are real and reproducible;
  the fatigue/thermal physics constants are illustrative.
- `scripts/run_edge_cloud_demo.py` uses a mocked Qwen Cloud response by
  default so it's runnable offline for judges without an API key;
  setting `QWEN_API_KEY` swaps in the real plugin with zero code
  changes, which is itself part of the architectural claim worth
  highlighting in the video.
