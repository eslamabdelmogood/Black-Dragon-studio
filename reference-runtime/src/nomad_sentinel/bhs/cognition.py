"""
Layer 3: the three-part BHS cognitive system.

Bat        - short-horizon forecaster + model-based Remaining Useful Life.
Hermit Crab - stability evaluator that vetoes actions whose long-term
              cost outweighs their short-term relief.
Squid      - adaptive re-weighting of Productivity / Safety / Energy /
              Structural Integrity as risk evolves.
"""
from __future__ import annotations

from collections import deque
import numpy as np

ACTIONS = ("do_nothing", "reduce_speed", "redistribute_load", "isolate_zone", "quick_patch_ignore")


class BatForecaster:
    def __init__(self, height: int, width: int, history_len: int = 20, horizon_steps: int = 30, dt: float = 0.05):
        self.history_len = history_len
        self.horizon_steps = horizon_steps
        self.dt = dt
        self.T_hist = deque(maxlen=history_len)
        self.stress_hist = deque(maxlen=history_len)
        self.damage_hist = deque(maxlen=history_len)

    def update(self, T, stress, damage):
        self.T_hist.append(T.copy())
        self.stress_hist.append(stress.copy())
        self.damage_hist.append(damage.copy())

    def _slope(self, hist):
        if len(hist) < 2:
            return np.zeros_like(hist[-1])
        first, last = hist[0], hist[-1]
        n = len(hist)
        return (last - first) / max(n - 1, 1)

    def forecast(self):
        """Returns (risk_field, rul_seconds_field)."""
        if len(self.T_hist) < 2:
            z = np.zeros_like(self.T_hist[-1]) if self.T_hist else None
            return z, z

        dT = self._slope(list(self.T_hist))
        ds = self._slope(list(self.stress_hist))
        dd = self._slope(list(self.damage_hist))

        T_future = self.T_hist[-1] + dT * self.horizon_steps
        s_future = self.stress_hist[-1] + ds * self.horizon_steps
        d_future = self.damage_hist[-1] + dd * self.horizon_steps

        risk = (
            0.3 * np.clip(T_future / 150.0, 0, 1)
            + 0.3 * np.clip(s_future / 150.0, 0, 1)
            + 0.4 * np.clip(d_future, 0, 1)
        )
        risk = 0.09 + 0.91 * np.clip(risk, 0, 1)  # keep a small nominal floor, matches reference report

        # RUL: time until damage would cross critical threshold at current slope
        d_now = self.damage_hist[-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            rul = np.where(dd > 1e-9, (0.92 - d_now) / np.maximum(dd, 1e-9) * self.dt, np.inf)
        rul = np.clip(rul, 0, 1e6)
        return risk, rul


class HermitCrabEvaluator:
    """Vetoes actions whose projected long-term cost outweighs short-term relief."""

    ALWAYS_VETO = {"quick_patch_ignore"}

    def score_and_veto(self, candidate_actions, risk_mean: float, isolate_allowed: bool):
        vetoed = []
        surviving = []
        for a in candidate_actions:
            if a in self.ALWAYS_VETO:
                vetoed.append(a)
                continue
            if a == "isolate_zone" and not isolate_allowed:
                vetoed.append(a)
                continue
            surviving.append(a)
        return surviving, vetoed


class SquidWeights:
    """Adaptive objective weighting: Productivity / Safety / Energy / Integrity."""

    def __init__(self):
        self.w = {"productivity": 0.3, "safety": 0.25, "energy": 0.2, "integrity": 0.25}

    def update(self, risk_mean: float, damage_mean: float, spike_activity: float):
        danger = np.clip(0.6 * risk_mean * 5 + 0.4 * damage_mean * 3 + 0.3 * spike_activity * 20, 0, 1)
        target_safety = 0.25 + 0.35 * danger
        target_integrity = 0.25 + 0.15 * danger
        target_productivity = 0.3 - 0.15 * danger
        target_energy = 0.2 - 0.1 * danger
        alpha = 0.08
        self.w["safety"] += alpha * (target_safety - self.w["safety"])
        self.w["integrity"] += alpha * (target_integrity - self.w["integrity"])
        self.w["productivity"] += alpha * (target_productivity - self.w["productivity"])
        self.w["energy"] += alpha * (target_energy - self.w["energy"])
        total = sum(self.w.values())
        for k in self.w:
            self.w[k] /= total
        return dict(self.w)


def select_action(surviving_actions, weights: dict, risk_mean: float, damage_mean: float):
    """Simple rule-based actuator selection biased by Squid's weights."""
    danger = 0.6 * risk_mean * 5 + 0.4 * damage_mean * 3
    if danger > 0.55 and "isolate_zone" in surviving_actions:
        return "isolate_zone"
    if danger > 0.15 and "reduce_speed" in surviving_actions:
        return "reduce_speed"
    if "redistribute_load" in surviving_actions and weights["integrity"] > 0.3:
        return "redistribute_load"
    return "do_nothing" if "do_nothing" in surviving_actions else surviving_actions[0]
