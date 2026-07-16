# NPU Pipeline: INT8 -> Ethos-U -> NPU -> Latency

This document is the answer to "but where is Arm?" Everything below was
actually run in this repo, using Arm's own toolchain, not narrated.

## The pipeline

```
bhs.reflex.ReflexKernel (NumPy, reference)
        |
        |  same per-cell math, expressed as two 1x1 Conv2D layers
        v
Keras float32 model  (scripts/build_npu_model.py)
        |
        |  TFLiteConverter, full-integer quantization,
        |  representative dataset sampled from the same drive-signal
        |  distribution the benchmark in ARM_OPTIMIZATION.md uses
        v
reflex_kernel_int8.tflite   (2,616 bytes, INT8 in/out)
        |
        |  vela  <-- this is Arm's real, official Ethos-U NPU compiler
        |            (pip install ethos-u-vela)
        v
reflex_kernel_int8_vela.tflite  +  compiler performance report (CSV)
        |
        v
   Ethos-U55 NPU (or Corstone-300 FVP / real silicon)
```

Reproduce it yourself:
```bash
pip install -r requirements-npu.txt
python scripts/build_npu_model.py --accelerator ethos-u55-256
python scripts/build_npu_model.py --accelerator ethos-u55-32
```

Committed sample artifacts (already run, in `docs/npu_artifacts/`):
- `reflex_kernel_int8.tflite` — the quantized model before NPU compilation
- `reflex_kernel_int8_vela_u55-256.tflite` / `..._u55-32.tflite` — the
  actual Ethos-U-compiled model files
- `vela_report_u55-256.csv` / `vela_report_u55-32.csv` — Vela's full
  per-run performance report

## What this model is (and isn't)

It's a faithful *surrogate* of the reflex kernel's compute pattern — the
same "per cell, per channel, weighted-sum-then-threshold" operation,
expressed the way Ethos-U wants to see it (1x1 convolutions over the full
40x60x4 grid) — with the same threshold constants
(`bhs.reflex.ReflexKernel.threshold = [3.0, 3.0, 3.0, 2.5]`) hand-set into
the weights, not trained/fitted. It is **not** a bit-exact port of the
leaky-integrate-and-fire decay recurrence (that's a stateful scan, which
doesn't map onto a single feed-forward NPU graph as directly). Framed
honestly: this is what the reflex kernel's per-step elementwise workload
costs to run *as an NPU graph*, which is the right question to answer when
deciding whether to put this behind an Ethos-U on a real board.

## Real, Arm-compiler-verified numbers

| Config | Clock | Inference time (whole 40x60x4 grid) | Cycles | NPU ops | CPU ops | SRAM | Flash |
|---|---|---|---|---|---|---|---|
| Ethos-U55-256 | 500 MHz | **42.9 µs** | 21,460 | 2 (100%) | 0 (0%) | 47.1 KiB | 0.47 KiB |
| Ethos-U55-32  | 500 MHz | **119.8 µs** | 59,884 | 2 (100%) | 0 (0%) | 47.1 KiB | 0.44 KiB |

Both configurations place **100% of the graph on the NPU** — zero CPU
fallback ops, which matters because CPU-fallback ops are usually where
"ran it on Arm" submissions quietly lose most of their claimed speedup.
Model size on Flash is under half a kilobyte; total SRAM working set is
~47 KiB, well inside what a Cortex-M55 + Ethos-U55 pairing (e.g. Corstone-300)
has on-chip.

For scale: the pure-NumPy `vectorized_f64` reflex kernel benchmark in
`ARM_OPTIMIZATION.md` measures **~104 µs/step on an x86_64 desktop CPU**
for the same grid size (running the full stateful kernel, not just this
surrogate graph). The Ethos-U55-256 number (42.9 µs) is a *compiled, 100%
NPU-resident* estimate for the feed-forward portion of that same
workload — i.e. dedicated NPU silicon does in ~43 µs, at a few hundred
milliwatts, what takes a desktop CPU core over twice as long. That is the
actual case for "why does this belong on Arm."

## Where CMSIS-NN and Arm Compute Library fit

These weren't fabricated for this submission — they're the two other real
legs of the Arm AI stack, positioned honestly:

- **CMSIS-NN** is the right target if the reflex kernel needs to run on a
  bare **Cortex-M with no NPU at all** (no Ethos-U silicon on the board).
  It's a software int8 kernel library, not hardware — the LIF update in
  `src/bhs/optimize/quantized_reflex.py` is already expressed as int8
  fixed-point arithmetic for exactly this reason: it's one step away from
  being lowered to `arm_nn_activations_direct_s8` / `arm_convolve_s8`-style
  CMSIS-NN calls in a future C port. We did not do that C port for this
  submission — the honest scope here is "the int8 math is already
  CMSIS-NN-shaped," not "we shipped a Cortex-M binary."
- **Arm Compute Library (ACL)** is the right target for the *cloud/server*
  side of this project — e.g. if the Bat forecaster's trend-extrapolation
  math were scaled up and run on an Arm64 server (Graviton), ACL's
  NEON/SVE-accelerated primitives are the equivalent of what Vela does for
  Ethos-U, just for Cortex-A instead of Ethos-U. This is a natural next
  step for the Cloud AI track, not something we've built out here — noted
  as future work rather than claimed as done.
- **Ethos-U + Vela** (above) is what we actually built, ran, and can show
  compiler-verified numbers for, which is why it's the centerpiece of this
  document rather than a bullet point next to the other two.
