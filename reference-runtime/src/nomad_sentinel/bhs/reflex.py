"""
Layer 2: the reflex kernel.

Each mesh cell carries one leaky integrate-and-fire (LIF) neuron per sensed
channel (temperature, stress, vibration, crack-signal). This is a genuine
event-based encoding: detection is driven by a sliding-window spike rate
crossing a threshold, not a disguised value threshold.

This module is intentionally the "hot loop" of the simulation (it runs
every timestep, for every cell, for every channel) and is therefore the
piece rewritten in `bhs.optimize` for the Arm-optimization comparison:
a naive per-cell Python loop vs. a fully vectorized NumPy implementation
with an int8-quantized threshold/membrane representation.
"""
from __future__ import annotations

import numpy as np

CHANNELS = ("temperature", "stress", "vibration", "crack_signal")


class ReflexKernel:
    def __init__(self, height: int, width: int, window: int = 10, dtype=np.float64):
        self.height, self.width = height, width
        self.window = window
        self.dtype = dtype
        n_ch = len(CHANNELS)
        self.membrane = np.zeros((n_ch, height, width), dtype=dtype)
        self.threshold = np.array([4.0, 4.0, 4.0, 3.5], dtype=dtype).reshape(-1, 1, 1)
        self.decay = dtype(0.7)
        self.spike_history = np.zeros((window, height, width), dtype=dtype)
        self._hist_idx = 0

    def _drive(self, T, stress, vib, prev_stress):
        crack_signal = np.abs(stress - prev_stress)
        d_temp = np.maximum(T - 60.0, 0.0) / 20.0
        d_stress = np.maximum(stress - 12.0, 0.0) / 20.0
        d_vib = np.maximum(vib - 0.6, 0.0) * 8.0
        d_crack = crack_signal / 5.0
        return np.stack([d_temp, d_stress, d_vib, d_crack]).astype(self.dtype)

    def step(self, T, stress, vib, prev_stress):
        drive = self._drive(T, stress, vib, prev_stress)
        self.membrane = self.membrane * self.decay + drive
        fired = self.membrane >= self.threshold
        self.membrane = np.where(fired, 0.0, self.membrane)

        any_fired = fired.any(axis=0).astype(self.dtype)
        self.spike_history[self._hist_idx] = any_fired
        self._hist_idx = (self._hist_idx + 1) % self.window

        spike_rate = self.spike_history.mean(axis=0)
        channel_names = [CHANNELS[i] for i in range(len(CHANNELS))]
        return spike_rate, fired

    @staticmethod
    def sustained_trigger(spike_rate: np.ndarray, rate_threshold: float = 0.5):
        return spike_rate >= rate_threshold
