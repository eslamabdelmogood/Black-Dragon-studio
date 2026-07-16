"""
Deliberately UNoptimized reference implementation of the reflex kernel's
per-timestep update: plain nested Python loops over every cell and
channel, no vectorization. This exists purely as the "before" baseline
for the Arm-optimization benchmark in ARM_OPTIMIZATION.md -- it is not
used anywhere in the main simulation path.
"""
from __future__ import annotations
import numpy as np

CHANNELS = ("temperature", "stress", "vibration", "crack_signal")


class NaiveReflexKernel:
    def __init__(self, height, width, window=10):
        self.height, self.width = height, width
        self.window = window
        n_ch = len(CHANNELS)
        self.membrane = [[[0.0 for _ in range(width)] for _ in range(height)] for _ in range(n_ch)]
        self.threshold = [3.0, 3.0, 3.0, 2.5]
        self.decay = 0.85
        self.spike_history = [[[0.0 for _ in range(width)] for _ in range(height)] for _ in range(window)]
        self._hist_idx = 0

    def step(self, T, stress, vib, prev_stress):
        h, w = self.height, self.width
        any_fired = [[0.0 for _ in range(w)] for _ in range(h)]
        for y in range(h):
            for x in range(w):
                d_temp = max(T[y, x] - 60.0, 0.0) / 20.0
                d_stress = max(stress[y, x] - 12.0, 0.0) / 20.0
                d_vib = max(vib[y, x] - 0.6, 0.0) * 8.0
                d_crack = abs(stress[y, x] - prev_stress[y, x]) / 5.0
                drives = (d_temp, d_stress, d_vib, d_crack)
                fired_here = False
                for c in range(4):
                    m = self.membrane[c][y][x] * self.decay + drives[c]
                    if m >= self.threshold[c]:
                        m = 0.0
                        fired_here = True
                    self.membrane[c][y][x] = m
                any_fired[y][x] = 1.0 if fired_here else 0.0

        self.spike_history[self._hist_idx] = any_fired
        self._hist_idx = (self._hist_idx + 1) % self.window

        spike_rate = np.zeros((h, w))
        for k in range(self.window):
            for y in range(h):
                for x in range(w):
                    spike_rate[y, x] += self.spike_history[k][y][x]
        spike_rate /= self.window
        return spike_rate
