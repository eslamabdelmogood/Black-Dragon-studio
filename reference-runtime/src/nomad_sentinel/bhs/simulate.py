"""Runs one scenario under one architecture ("bhs", "baseline", or
"unmitigated") and returns a log of metrics-relevant events."""
from __future__ import annotations

import time
import numpy as np

from .physics import Panel, PanelConfig, CRITICAL_DAMAGE
from .sensing import OpticalSkin, PointSensorBaseline
from .reflex import ReflexKernel
from .cognition import BatForecaster, HermitCrabEvaluator, SquidWeights, select_action
from .scenarios import Scenario


def _dist(a, b):
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def run(
    scenario: Scenario,
    architecture: str,
    n_steps: int = 2000,
    dtype=np.float64,
    seed: int = None,
):
    """architecture in {"bhs", "baseline", "unmitigated"}"""
    cfg = PanelConfig(dtype=dtype)
    panel = Panel(cfg, seed=seed if seed is not None else scenario.seed)
    scenario.apply(panel)
    rng = np.random.default_rng((seed if seed is not None else scenario.seed) + 1)

    log = {
        "detect_time": None,
        "predict_failure_time": None,
        "predict_lead_time": None,
        "localization_error_cells": None,
        "false_alarms": 0,
        "true_alarms": 0,
        "rul_error_mean_abs": None,
        "detection_events": [],
        "damage_trace": [],  # (t, max_damage)
        "reaction_latency": None,
        "wallclock_per_step_ms": None,
        "cracked_cells_final": 0,
    }

    step_times = []
    rul_errors = []
    detected = False
    detect_t = None
    critical_t = None
    first_action_t = None

    if architecture == "bhs":
        optical = OpticalSkin(cfg.height, cfg.width, dtype=dtype)
        reflex = ReflexKernel(cfg.height, cfg.width, dtype=dtype)
        bat = BatForecaster(cfg.height, cfg.width, dt=cfg.dt)
        hermit = HermitCrabEvaluator()
        squid = SquidWeights()
        prev_stress = panel.stress.copy()
        was_triggered = False

    elif architecture == "baseline":
        baseline_sensors = PointSensorBaseline(cfg.height, cfg.width)
        baseline_alarmed = False
        was_triggered = False

    for step_i in range(n_steps):
        t0 = time.perf_counter()
        panel.step()
        t1 = time.perf_counter()
        step_times.append((t1 - t0) * 1000.0)

        max_damage = float(panel.damage.max())
        log["damage_trace"].append((panel.t, max_damage))
        if critical_t is None and max_damage >= CRITICAL_DAMAGE:
            critical_t = panel.t

        if architecture == "bhs":
            T_read = optical.read_temperature(panel.T, rng)
            stress_read = optical.read_stress(panel.stress, rng)
            vib_read = panel.vib  # vibration channel assumed co-located w/ strain skin

            spike_rate, fired = reflex.step(T_read, stress_read, vib_read, prev_stress)
            prev_stress = stress_read

            triggers = ReflexKernel.sustained_trigger(spike_rate)
            any_trigger = bool(triggers.any())
            if any_trigger and not detected:
                detected = True
                detect_t = panel.t
                log["detect_time"] = detect_t

            if any_trigger and not was_triggered:
                yx = np.unravel_index(np.argmax(spike_rate), spike_rate.shape)
                is_true = _dist(yx, scenario.true_fault_yx) <= 8
                if is_true:
                    log["true_alarms"] += 1
                else:
                    log["false_alarms"] += 1
            was_triggered = any_trigger

            bat.update(T_read, stress_read, panel.damage)
            risk, rul = bat.forecast()
            if risk is not None:
                risk_mean = float(risk.mean())
                peak_yx = np.unravel_index(np.argmax(risk), risk.shape)
                if log["predict_failure_time"] is None and risk.max() > 0.3:
                    log["predict_failure_time"] = panel.t
                    if critical_t is not None:
                        log["predict_lead_time"] = max(critical_t - panel.t, 0.0)

                if critical_t is not None and panel.t <= critical_t:
                    peak_damage = float(panel.damage.max())
                    if peak_damage > 0.05:
                        rul_pred = float(rul[peak_yx]) if np.isfinite(rul[peak_yx]) else None
                        rul_true = critical_t - panel.t
                        if rul_pred is not None and rul_pred < 1e5:
                            rul_errors.append(abs(rul_pred - rul_true))

                # cognition -> actuation
                candidates = ["do_nothing", "reduce_speed", "redistribute_load", "isolate_zone", "quick_patch_ignore"]
                isolate_allowed = risk_mean > 0.35
                surviving, vetoed = hermit.score_and_veto(candidates, risk_mean, isolate_allowed)
                weights = squid.update(risk_mean, float(panel.damage.mean()), float(spike_rate.mean()))
                action = select_action(surviving, weights, risk_mean, float(panel.damage.mean()))

                if action != "do_nothing" and first_action_t is None and detect_t is not None:
                    first_action_t = panel.t
                    log["reaction_latency"] = max(first_action_t - detect_t, 0.0)

                if action == "reduce_speed":
                    panel.speed_factor = 0.4
                elif action == "isolate_zone":
                    panel.speed_factor = 0.0
                elif action == "do_nothing":
                    panel.speed_factor = min(panel.speed_factor + 0.05, 1.0)

                log["localization_error_cells"] = _dist(peak_yx, scenario.true_fault_yx)

        elif architecture == "baseline":
            temps, vibs, stresses = baseline_sensors.read(panel, rng)
            triggered, loc = baseline_sensors.alarm(temps, vibs, stresses)
            if triggered and not detected:
                detected = True
                detect_t = panel.t
                log["detect_time"] = detect_t
                log["localization_error_cells"] = _dist(loc, scenario.true_fault_yx)
            if triggered and not was_triggered:
                is_true = _dist(loc, scenario.true_fault_yx) <= 8
                if is_true:
                    log["true_alarms"] += 1
                else:
                    log["false_alarms"] += 1
            was_triggered = bool(triggered)
            if triggered:
                if not baseline_alarmed:
                    panel.speed_factor = 0.5
                    baseline_alarmed = True
                if first_action_t is None:
                    first_action_t = panel.t
                    log["reaction_latency"] = max(first_action_t - detect_t, 0.0)

        # architecture == "unmitigated": no sensing/control, panel just evolves

    log["cracked_cells_final"] = int(panel.crack.sum())
    log["final_damage_mean"] = float(panel.damage.mean())
    log["final_damage_max"] = float(panel.damage.max())
    log["wallclock_per_step_ms"] = float(np.mean(step_times))
    log["total_wallclock_s"] = float(np.sum(step_times) / 1000.0)
    log["rul_error_mean_abs"] = float(np.mean(rul_errors)) if rul_errors else None
    if log["predict_lead_time"] is None:
        log["predict_lead_time"] = 0.0
    return log
