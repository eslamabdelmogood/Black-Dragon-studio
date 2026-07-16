"""Computes the 8 comparison metrics and writes CSVs matching the schema
used in the project's research report / dashboard."""
from __future__ import annotations

import csv
import os
from typing import Dict

FIELDS = [
    "scenario",
    "scenario_name",
    "system",
    "detect_time_s",
    "predict_failure_time_s",
    "predict_lead_time_s",
    "localization_error_cells",
    "false_alarms",
    "true_alarms",
    "rul_error_mean_abs_s",
    "final_damage_mean",
    "final_damage_max",
    "damage_prevented_pct",
    "reaction_latency_s",
    "wallclock_per_step_ms",
    "total_wallclock_s",
    "cracked_cells_final",
]


def damage_prevented_pct(final_damage_mean: float, unmitigated_damage_mean: float) -> float:
    if unmitigated_damage_mean <= 1e-9:
        return 0.0
    return max(0.0, (unmitigated_damage_mean - final_damage_mean) / unmitigated_damage_mean * 100.0)


def row_from_log(scenario_key, scenario_name, system, log, unmitigated_damage_mean) -> Dict:
    return {
        "scenario": scenario_key,
        "scenario_name": scenario_name,
        "system": system,
        "detect_time_s": log["detect_time"],
        "predict_failure_time_s": log["predict_failure_time"],
        "predict_lead_time_s": log["predict_lead_time"],
        "localization_error_cells": log["localization_error_cells"],
        "false_alarms": log["false_alarms"],
        "true_alarms": log["true_alarms"],
        "rul_error_mean_abs_s": log["rul_error_mean_abs"],
        "final_damage_mean": log["final_damage_mean"],
        "final_damage_max": log["final_damage_max"],
        "damage_prevented_pct": damage_prevented_pct(log["final_damage_mean"], unmitigated_damage_mean),
        "reaction_latency_s": log["reaction_latency"],
        "wallclock_per_step_ms": log["wallclock_per_step_ms"],
        "total_wallclock_s": log["total_wallclock_s"],
        "cracked_cells_final": log["cracked_cells_final"],
    }


def write_detailed_csv(path: str, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
