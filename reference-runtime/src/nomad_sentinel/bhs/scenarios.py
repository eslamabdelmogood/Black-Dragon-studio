"""Four deterministic fault scenarios, injected identically regardless of
which architecture (BHS or baseline) is observing the panel."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from .physics import Panel


@dataclass
class Scenario:
    key: str
    name: str
    true_fault_yx: tuple
    apply: Callable[[Panel], None]
    seed: int = 42


def _scenario_a(panel: Panel):
    panel.inject_thermal_fault(cy=8, cx=30, radius=3, magnitude=180.0)


def _scenario_b(panel: Panel):
    panel.seed_crack(cy=10, cx=30, initial_damage=0.5)
    panel.inject_load_fault(cy=10, cx=30, radius=3, multiplier=6.0)


def _scenario_c(panel: Panel):
    panel.inject_load_fault(cy=20, cx=30, radius=2, multiplier=7.0)


def _scenario_d(panel: Panel):
    panel.inject_thermal_fault(cy=12, cx=25, radius=3, magnitude=120.0)
    panel.inject_vibration_fault(cy=14, cx=27, radius=3, amplitude=0.6)
    panel.inject_load_fault(cy=13, cx=26, radius=3, multiplier=4.0)


def _scenario_e(panel: Panel):
    # Deliberately tiny radius on a 40x60 (2400-cell) panel: severe enough
    # locally to race toward critical damage, but small enough that
    # risk.mean() over the whole field stays diluted and never crosses the
    # local heuristic's escalation threshold (see cognition.py select_action,
    # which only ever sees the scalar mean). risk.max() would catch this
    # immediately -- that's the point: this scenario is designed to show
    # where mean-pooling a per-cell risk field structurally loses signal.
    panel.inject_thermal_fault(cy=20, cx=30, radius=1, magnitude=260.0)
    panel.inject_load_fault(cy=20, cx=30, radius=1, multiplier=9.0)


SCENARIOS = {
    "A": Scenario("A", "Scenario A: Localized Thermal Fault", (8, 30), _scenario_a),
    "B": Scenario("B", "Scenario B: Crack Initiation and Propagation", (10, 30), _scenario_b),
    "C": Scenario("C", "Scenario C: Mechanical Overload", (20, 30), _scenario_c),
    "D": Scenario("D", "Scenario D: Combined Heat + Vibration + Stress Failure", (13, 26), _scenario_d),
    "E": Scenario("E", "Scenario E: Diluted Hotspot (severe but spatially tiny fault)", (20, 30), _scenario_e),
}

ORDER = ["A", "B", "C", "D", "E"]
