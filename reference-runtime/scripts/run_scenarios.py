#!/usr/bin/env python3
"""Runs all four fault scenarios under the BHS architecture, the fixed
point-sensor baseline, and an unmitigated (no sensing/control) reference,
then writes a metrics CSV compatible with docs/dashboard.html.

Usage:
    python scripts/run_scenarios.py --steps 2000 --out outputs/metrics.csv
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bhs.scenarios import SCENARIOS, ORDER
from bhs.simulate import run
from bhs.metrics import row_from_log, write_detailed_csv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--out", type=str, default="outputs/metrics.csv")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rows = []
    for key in ORDER:
        scenario = SCENARIOS[key]
        print(f"Running {scenario.name} ...")

        unmitigated_log = run(scenario, "unmitigated", n_steps=args.steps, seed=args.seed)
        unmitigated_damage_mean = unmitigated_log["final_damage_mean"]

        for system in ("bhs", "baseline", "unmitigated"):
            log = unmitigated_log if system == "unmitigated" else run(
                scenario, system, n_steps=args.steps, seed=args.seed
            )
            row = row_from_log(key, scenario.name, system, log, unmitigated_damage_mean)
            rows.append(row)
            print(
                f"  [{system:12s}] detect={row['detect_time_s']}  "
                f"lead={row['predict_lead_time_s']:.2f}s  "
                f"loc_err={row['localization_error_cells']}  "
                f"damage_prevented={row['damage_prevented_pct']:.1f}%  "
                f"ms/step={row['wallclock_per_step_ms']:.4f}"
            )

    write_detailed_csv(args.out, rows)
    print(f"\nWrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
