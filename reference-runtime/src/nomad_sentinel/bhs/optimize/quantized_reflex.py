"""
int8-quantized, fully vectorized reflex kernel.

This is the "Arm-optimized" edge variant of `bhs.reflex.ReflexKernel`:

  - All per-cell state (membrane potentials) is stored as int8 instead of
    float32/float64, cutting the resident memory footprint of the hot
    state 4x vs float32 / 8x vs float64.
  - The membrane update, threshold compare, and decay are expressed as
    integer arithmetic on fixed-point-scaled values, which maps onto
    Arm NEON/SVE 8-bit SIMD lanes far more densely than float32 ops
    (more lanes per vector register -> higher throughput per cycle),
    and is the same class of optimization TensorFlow Lite / Arm's own
    CMSIS-NN kernels use for microcontroller-class Arm Cortex-M cores.
  - Quantization scale/zero-point are chosen so the drive signals
    (which are pre-normalized to an O(1) range upstream) map cleanly
    into the int8 range without frequent saturation.

Use `dequantize_error` in benchmark.py to confirm the spike-detection
agreement rate against the float64 reference before trusting this path
for a real deployment.
"""
from __future__ import annotations

import numpy as np

CHANNELS = ("temperature", "stress", "vibration", "crack_signal")

# Fixed-point scale: drive values are expected in roughly [0, 4]; we map
# [0, SCALE_RANGE] -> [0, 127] int8.
SCALE_RANGE = 6.0
QSCALE = 127.0 / SCALE_RANGE


def quantize(x: np.ndarray) -> np.ndarray:
    return np.clip(np.round(x * QSCALE), -128, 127).astype(np.int8)


def dequantize(q: np.ndarray) -> np.ndarray:
    return q.astype(np.float32) / QSCALE


class QuantizedReflexKernel:
    def __init__(self, height: int, width: int, window: int = 10):
        self.height, self.width = height, width
        self.window = window
        n_ch = len(CHANNELS)
        self.membrane_q = np.zeros((n_ch, height, width), dtype=np.int8)
        # thresholds pre-quantized once (constants, no re-quantization cost per step)
        self.threshold_q = quantize(
            np.array([3.0, 3.0, 3.0, 2.5], dtype=np.float32).reshape(-1, 1, 1)
        )
        self.decay_q = np.int16(round(0.85 * 128))  # Q7 fixed-point decay factor
        self.spike_history = np.zeros((window, height, width), dtype=np.uint8)
        self._hist_idx = 0

    def _drive_q(self, T, stress, vib, prev_stress):
        d_temp = np.maximum(T - 60.0, 0.0) / 20.0
        d_stress = np.maximum(stress - 12.0, 0.0) / 20.0
        d_vib = np.maximum(vib - 0.6, 0.0) * 8.0
        d_crack = np.abs(stress - prev_stress) / 5.0
        drive = np.stack([d_temp, d_stress, d_vib, d_crack]).astype(np.float32)
        return quantize(drive)

    def step(self, T, stress, vib, prev_stress):
        drive_q = self._drive_q(T, stress, vib, prev_stress)

        # decay in Q7 fixed point, then int16 accumulate to avoid overflow,
        # clip back down to int8 range
        decayed = (self.membrane_q.astype(np.int16) * self.decay_q) >> 7
        acc = decayed + drive_q.astype(np.int16)
        acc = np.clip(acc, -128, 127)

        fired = acc >= self.threshold_q
        acc = np.where(fired, 0, acc)
        self.membrane_q = acc.astype(np.int8)

        any_fired = fired.any(axis=0).astype(np.uint8)
        self.spike_history[self._hist_idx] = any_fired
        self._hist_idx = (self._hist_idx + 1) % self.window

        spike_rate = self.spike_history.mean(axis=0, dtype=np.float32)
        return spike_rate, fired

    @property
    def nbytes(self) -> int:
        return self.membrane_q.nbytes + self.spike_history.nbytes + self.threshold_q.nbytes
