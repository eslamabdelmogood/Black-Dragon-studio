"""
Layer 1 sensing: the distributed Optical Skin (simulated FBG network) and
the traditional fixed point-sensor baseline it is benchmarked against.
"""
from __future__ import annotations

import numpy as np


class OpticalSkin:
    """Simulated Fiber Bragg Grating network with inverse-distance-weighted
    reconstruction of the full mesh from sparse, noisy grating readings."""

    def __init__(self, height: int, width: int, spacing: int = 2, dtype=np.float64):
        self.height, self.width = height, width
        self.spacing = spacing
        self.dtype = dtype
        ys = np.arange(0, height, spacing)
        xs = np.arange(0, width, spacing)
        gy, gx = np.meshgrid(ys, xs, indexing="ij")
        self.grating_y = gy.ravel()
        self.grating_x = gx.ravel()
        self.n_gratings = self.grating_y.size

        # Precompute IDW weights (dense but cheap for a 60x40 panel; this is
        # the natural target for the Arm-optimized vectorized/quantized path).
        full_y, full_x = np.mgrid[0:height, 0:width]
        fy = full_y.ravel()[:, None].astype(np.float32)
        fx = full_x.ravel()[:, None].astype(np.float32)
        gy_f = self.grating_y[None, :].astype(np.float32)
        gx_f = self.grating_x[None, :].astype(np.float32)
        dist = np.sqrt((fy - gy_f) ** 2 + (fx - gx_f) ** 2) + 1e-3
        w = 1.0 / (dist**2)
        self.weights = (w / w.sum(axis=1, keepdims=True)).astype(dtype)  # (cells, gratings)

    @property
    def coverage_fraction(self) -> float:
        return 1.0  # every cell reachable via interpolation, by construction

    def read(self, field: np.ndarray, noise_std: float, rng: np.random.Generator) -> np.ndarray:
        raw = field[self.grating_y, self.grating_x]
        noisy = raw + rng.normal(0.0, noise_std, size=raw.shape).astype(raw.dtype)
        recon = self.weights @ noisy.astype(self.weights.dtype)
        return recon.reshape(self.height, self.width).astype(field.dtype)

    def read_temperature(self, T: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        return self.read(T, noise_std=0.15, rng=rng)

    def read_stress(self, stress: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        # strain-equivalent noise in kPa-scale terms, folded into MPa here
        return self.read(stress, noise_std=0.15, rng=rng)


class PointSensorBaseline:
    """10 fixed temperature sensors + 5 fixed vibration sensors, evenly
    spread, driving fixed-threshold alarms with no spatial reconstruction."""

    TEMP_THRESHOLD_C = 80.0
    VIB_THRESHOLD = 0.9
    STRESS_THRESHOLD_MPA = 60.0  # conservative concession, see README

    def __init__(self, height: int, width: int):
        self.height, self.width = height, width
        self.temp_sensors = self._evenly_spaced(10, height, width)
        self.vib_sensors = self._evenly_spaced(5, height, width)
        self.n_sensors = len(self.temp_sensors) + len(self.vib_sensors)

    @staticmethod
    def _evenly_spaced(n, h, w):
        pts = []
        cols = int(np.ceil(np.sqrt(n * w / h)))
        rows = int(np.ceil(n / cols))
        ys = np.linspace(0, h - 1, rows).astype(int)
        xs = np.linspace(0, w - 1, cols).astype(int)
        for y in ys:
            for x in xs:
                pts.append((int(y), int(x)))
                if len(pts) == n:
                    return pts
        return pts

    @property
    def coverage_fraction(self) -> float:
        return self.n_sensors / (self.height * self.width)

    def read(self, panel, rng: np.random.Generator):
        temps = [
            panel.T[y, x] + rng.normal(0, 0.2)
            for (y, x) in self.temp_sensors
        ]
        vibs = [
            panel.vib[y, x] + rng.normal(0, 0.02)
            for (y, x) in self.vib_sensors
        ]
        stresses = [
            panel.stress[y, x] + rng.normal(0, 0.3)
            for (y, x) in self.temp_sensors
        ]
        return temps, vibs, stresses

    def alarm(self, temps, vibs, stresses):
        """Returns (triggered: bool, location: (y,x) or None)."""
        for (y, x), t, s in zip(self.temp_sensors, temps, stresses):
            if t >= self.TEMP_THRESHOLD_C or s >= self.STRESS_THRESHOLD_MPA:
                return True, (y, x)
        for (y, x), v in zip(self.vib_sensors, vibs):
            if v >= self.VIB_THRESHOLD:
                return True, (y, x)
        return False, None
