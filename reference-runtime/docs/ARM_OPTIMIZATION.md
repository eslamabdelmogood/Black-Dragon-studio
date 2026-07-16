# Arm Optimization Notes

This document is the "show your work" artifact for the Arm AI Optimization
Challenge. It covers what was optimized, why, the numbers we measured, and
exactly how to reproduce (or challenge) them on real Arm hardware.

## What's being optimized

The BHS digital twin's **reflex kernel** (`src/bhs/reflex.py`) is the hot
path: every simulation timestep, it runs a leaky integrate-and-fire (LIF)
spiking-neuron update over every cell of the panel mesh, across 4 sensed
channels. This is the same shape of workload as an always-on edge-AI
sensing loop (temperature/vibration/strain fusion) that would realistically
run continuously on an Arm Cortex-A/M class device bonded to a physical
structure — so it's the right piece to optimize for size and speed, not
just the prettiest one.

We implemented and benchmarked four versions of it:

| Implementation | File | What changed |
|---|---|---|
| `naive` | `src/bhs/optimize/naive_reflex.py` | Pure Python triple-nested loop over (channel, y, x). Deliberately left un-optimized as the "before" picture. |
| `vectorized_f64` | `src/bhs/reflex.py` | NumPy array ops over the whole mesh at once, float64. This is the simulation's default/reference precision. |
| `vectorized_f32` | `src/bhs/reflex.py` (dtype=float32) | Same vectorized code, float32 state. Halves memory bandwidth per element and matches the native SIMD lane width most Arm NEON/SVE pipelines are tuned around. |
| `quantized_int8` | `src/bhs/optimize/quantized_reflex.py` | Membrane potentials, thresholds, and decay stored and updated as int8 fixed-point values (Q7 decay factor), spike history as uint8. This mirrors the int8 quantization approach used by CMSIS-NN / TFLite Micro on Arm Cortex-M edge targets. |

## Measured results (this run)

Reproduce with:

```bash
python -m bhs.optimize.benchmark --steps 200 --out outputs/arm_benchmark.json
```

Collected in this environment (honest disclosure — **not** Arm hardware,
see below for how to get real Arm numbers):

```
Platform: {'machine': 'x86_64', 'processor': 'x86_64', 'system': 'Linux', 'python': '3.12.3'}
Grid: 40x60, steps: 150

implementation                     mean ms/step  state bytes   vs f64 agree    speedup
naive (unoptimized)                     11.3766       153600          1.000      0.01x
vectorized_f64 (reference)               0.1041       268832          1.000      1.00x
vectorized_f32 (Arm SIMD-width)          0.0802       134416          1.000      1.30x
quantized_int8 (Arm edge)                0.1282        33604          0.998      0.81x
```

**Reading this honestly:**

- **Naive -> vectorized: ~109x speedup.** This is the single biggest,
  least platform-dependent win, and it's real: replacing Python-level
  loops with NumPy array ops is exactly the kind of "developer experience
  + speed" optimization that helps regardless of CPU architecture, and it
  compounds with everything below.
- **float64 -> float32: 1.3x speedup, 2.0x smaller state** (268,832 ->
  134,416 bytes). Halving element width is a straightforward, portable win
  and is the precision NEON/SVE are natively widest for.
- **float32 -> int8 quantization: 4x further memory reduction** (134,416 ->
  33,604 bytes; **8x smaller than the float64 reference**), with **99.8%
  agreement** on the sustained-trigger detection decision vs. the float64
  reference (i.e. quantization essentially does not change *what* the
  system detects). The wallclock number here is **not** faster on this
  x86_64 host — generic NumPy int8 arithmetic doesn't get dedicated SIMD
  treatment the way it does on Arm cores with native int8 dot-product
  instructions (Armv8.2 SDOT/UDOT, or CMSIS-NN kernels on Cortex-M). We are
  reporting that plainly rather than papering over it: **on this
  benchmark, the honest, cross-platform claim is an 8x memory reduction at
  <1% decision-accuracy cost; the throughput claim requires validation on
  real Arm silicon (see below).**

This is why we report *both* size and speed separately per metric, instead
of folding them into one "Arm speedup" number: the memory win is unconditional,
the throughput win for int8 is conditional on the target hardware actually
having the SIMD/NEON int8 path this format is designed for.

## Reproducing on real Arm64 hardware

The whole benchmark is architecture-agnostic Python/NumPy, so it runs
unmodified anywhere `pip install -r requirements.txt` succeeds. To get
Arm-native numbers:

**Option A — Raspberry Pi 4/5 (Cortex-A72 / A76, Armv8-A)**
```bash
git clone <this-repo-url> && cd bhs-optical-skin
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m bhs.optimize.benchmark --steps 500 --out outputs/arm_benchmark_rpi.json
```

**Option B — AWS Graviton (arm64) EC2 instance**
```bash
# on a Graviton (m7g/c7g/t4g) instance running Ubuntu:
sudo apt-get update && sudo apt-get install -y python3-venv
git clone <this-repo-url> && cd bhs-optical-skin
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m bhs.optimize.benchmark --steps 500 --out outputs/arm_benchmark_graviton.json
```

**Option C — Docker buildx, no physical Arm device required**
```bash
docker buildx build --platform linux/arm64 -t bhs-arm64 --load .
docker run --rm bhs-arm64 python -m bhs.optimize.benchmark --steps 500
```
(QEMU-emulated arm64 will not give trustworthy *speed* numbers, but it does
prove the code runs correctly on the Arm instruction set — useful for the
memory/correctness half of the story even without native hardware.)

**Option D — Arm Performix**
Point Arm Performix at the same `python -m bhs.optimize.benchmark` entry
point (or the full `scripts/run_scenarios.py` pipeline) on an Arm-based
target to get vendor-verified latency/throughput numbers instead of our
`time.perf_counter()` measurements. We deliberately kept the benchmark
harness dependency-free (stdlib `time` + NumPy) so it drops into any
profiling wrapper without modification.

Re-run `scripts/build_dashboard.py` afterwards to fold fresh
`outputs/arm_benchmark*.json` results into `docs/dashboard.html`.

## Other size/quality levers already in the codebase

- `bhs.physics.PanelConfig.dtype` lets the *entire* physics substrate (not
  just the reflex kernel) run at float32, halving the panel state footprint
  end-to-end; `scripts/run_scenarios.py` and the benchmark both exercise
  this.
- `OpticalSkin`'s IDW reconstruction weight matrix (`src/bhs/sensing.py`) is
  precomputed once and reused every step, rather than recomputed — an
  "Arm-specific optimization" in the sense that it avoids repeated
  sqrt/division work that is comparatively more expensive on
  power-constrained edge cores than on desktop-class silicon.
