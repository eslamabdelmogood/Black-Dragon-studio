"""
Physical substrate for the Black Dragon Optical Skin (BHS) digital twin.

A 2D finite-difference steel panel (H x W cells) with coupled:
  - heat diffusion
  - mechanical + thermal stress
  - Paris-law-inspired fatigue damage accumulation
  - brittle rupture (crack formation)

The array dtype is configurable (float64 / float32) so the same physics
can be run in a "reference" precision and an "Arm-optimized" precision
for the size/speed comparison in ARM_OPTIMIZATION.md. float32 halves the
memory footprint and is the natural width for NEON/SVE SIMD lanes on
Arm cores, while float64 is kept as the numerically conservative
reference implementation.
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field


AMBIENT_C = 25.0
ENDURANCE_MPA = 12.0
CRITICAL_DAMAGE = 0.92
CONCENTRATION_CAP = 3.0


@dataclass
class PanelConfig:
    height: int = 40
    width: int = 60
    dt: float = 0.05
    alpha: float = 4.0          # thermal diffusivity proxy
    convective_loss: float = 0.15
    base_load_mpa: float = 12.0
    fatigue_k: float = 4.0e-4
    fatigue_n: float = 2.2
    dtype: np.dtype = np.float64


class Panel:
    """Mutable simulation state for one panel instance."""

    def __init__(self, cfg: PanelConfig, seed: int = 0):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        h, w = cfg.height, cfg.width
        dt = cfg.dtype
        self.T = np.full((h, w), AMBIENT_C, dtype=dt)
        self.stress = np.full((h, w), cfg.base_load_mpa, dtype=dt)
        self.damage = np.zeros((h, w), dtype=dt)
        self.crack = np.zeros((h, w), dtype=bool)
        self.vib = np.full((h, w), 0.45, dtype=dt)
        self.heat_source = np.zeros((h, w), dtype=dt)
        self.load_mult = np.ones((h, w), dtype=dt)
        self.vib_source = np.zeros((h, w), dtype=dt)
        self.t = 0.0
        self.speed_factor = 1.0  # actuator-controlled (1.0 = nominal)

    # ---- physics steps -------------------------------------------------
    def _laplacian(self, field: np.ndarray) -> np.ndarray:
        lap = (
            -4.0 * field
            + np.roll(field, 1, axis=0)
            + np.roll(field, -1, axis=0)
            + np.roll(field, 1, axis=1)
            + np.roll(field, -1, axis=1)
        )
        return lap

    def step(self) -> None:
        cfg = self.cfg
        dt = cfg.dt

        # 1. heat diffusion + convective loss + fault heat source
        lap = self._laplacian(self.T)
        self.T += (
            dt
            * (
                cfg.alpha * lap
                - cfg.convective_loss * (self.T - AMBIENT_C)
                + self.heat_source * self.speed_factor
            )
        ).astype(self.T.dtype)

        # 2. mechanical + thermal stress, with capped concentration near damage
        thermal_stress = 2.2 * (self.T - AMBIENT_C)
        mech_stress = cfg.base_load_mpa * self.load_mult * self.speed_factor
        concentration = 1.0 + np.minimum(self.damage, 1.0) * (CONCENTRATION_CAP - 1.0)
        self.stress = ((mech_stress + thermal_stress) * concentration).astype(
            self.stress.dtype
        )

        # 3. Paris-law-ish fatigue damage accumulation, coalescing toward
        #    already-damaged neighbours to mimic micro-crack network growth
        excess = np.maximum(self.stress - ENDURANCE_MPA, 0.0)
        rate = cfg.fatigue_k * np.power(excess, cfg.fatigue_n)
        neighbor_damage = 0.25 * (
            np.roll(self.damage, 1, axis=0)
            + np.roll(self.damage, -1, axis=0)
            + np.roll(self.damage, 1, axis=1)
            + np.roll(self.damage, -1, axis=1)
        )
        coalescence = 0.15 * neighbor_damage * (self.damage > 0)
        self.damage = np.clip(
            self.damage + (rate * dt + coalescence * dt), 0.0, 1.0
        ).astype(self.damage.dtype)

        # 4. brittle rupture
        self.crack = self.crack | (self.damage >= CRITICAL_DAMAGE)

        # 5. vibration field (ambient noise + any active vibration fault)
        noise = self.rng.normal(0.0, 0.015, size=self.vib.shape).astype(self.vib.dtype)
        self.vib = np.clip(0.45 + self.vib_source + noise, 0.0, 2.0).astype(
            self.vib.dtype
        )

        self.t += dt

    # ---- fault injection helpers ---------------------------------------
    def inject_thermal_fault(self, cy: int, cx: int, radius: int, magnitude: float):
        yy, xx = np.ogrid[: self.cfg.height, : self.cfg.width]
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius**2
        self.heat_source[mask] = magnitude

    def inject_load_fault(self, cy: int, cx: int, radius: int, multiplier: float):
        yy, xx = np.ogrid[: self.cfg.height, : self.cfg.width]
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius**2
        self.load_mult[mask] = multiplier

    def inject_vibration_fault(self, cy: int, cx: int, radius: int, amplitude: float):
        yy, xx = np.ogrid[: self.cfg.height, : self.cfg.width]
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius**2
        self.vib_source[mask] = amplitude

    def seed_crack(self, cy: int, cx: int, initial_damage: float = 0.5):
        self.damage[cy, cx] = initial_damage
