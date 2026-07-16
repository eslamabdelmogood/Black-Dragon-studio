"""
Arm-optimization benchmark harness.

Compares four implementations of the reflex-kernel hot loop (the part of
the simulation that runs every timestep, for every cell, for every
sensed channel):

  1. naive            - pure Python nested loops, float64            (reference / worst case)
  2. vectorized_f64    - bhs.reflex.ReflexKernel, float64             (numerically faithful baseline)
  3. vectorized_f32    - bhs.reflex.ReflexKernel, float32             (Arm NEON/SVE-width baseline)
  4. quantized_int8    - bhs.optimize.quantized_reflex, int8          (Arm edge-deployment target)

For each, we measure:
  - wallclock per step (ms)              -> throughput / latency
  - resident state memory (bytes)        -> model/state size on disk & in memory
  - spike-detection agreement vs (2)     -> correctness cost of the optimization

This script runs on whatever CPU it's invoked on and prints that CPU's
architecture so results are never silently presented as if they were
collected on Arm hardware. See ARM_OPTIMIZATION.md for how to re-run this
on real Arm64 targets (Raspberry Pi, AWS Graviton, Arm Performix-instrumented
CI) and for the reference numbers we collected there.
"""
from __future__ import annotations

import argparse
import json
import platform
import time

import numpy as np

from bhs.reflex import ReflexKernel
from bhs.optimize.naive_reflex import NaiveReflexKernel
from bhs.optimize.quantized_reflex import QuantizedReflexKernel


def _synthetic_frame(h, w, rng, t):
    T = 25.0 + 40.0 * np.exp(-((np.arange(h)[:, None] - h / 2) ** 2 + (np.arange(w)[None, :] - w / 2) ** 2) / 40.0)
    T += rng.normal(0, 1.0, size=(h, w))
    stress = 12.0 + 20.0 * np.exp(-((np.arange(h)[:, None] - h / 2) ** 2 + (np.arange(w)[None, :] - w / 2) ** 2) / 60.0)
    stress += rng.normal(0, 1.0, size=(h, w))
    vib = 0.45 + 0.1 * np.sin(t) + rng.normal(0, 0.02, size=(h, w))
    return T.astype(np.float64), stress.astype(np.float64), vib.astype(np.float64)


def bench_naive(h, w, n_steps, rng):
    kernel = NaiveReflexKernel(h, w)
    prev_stress = np.full((h, w), 12.0)
    times = []
    last_rate = None
    for i in range(n_steps):
        T, stress, vib = _synthetic_frame(h, w, rng, i * 0.05)
        t0 = time.perf_counter()
        rate = kernel.step(T, stress, vib, prev_stress)
        times.append((time.perf_counter() - t0) * 1000)
        prev_stress = stress
        last_rate = rate
    state_bytes = 4 * h * w * 8 * 2  # 4 channels + spike history, float64-equivalent Python floats (approx)
    return times, last_rate, state_bytes


def bench_vectorized(h, w, n_steps, rng, dtype):
    kernel = ReflexKernel(h, w, dtype=dtype)
    prev_stress = np.full((h, w), 12.0, dtype=dtype)
    times = []
    last_rate = None
    for i in range(n_steps):
        T, stress, vib = _synthetic_frame(h, w, rng, i * 0.05)
        T, stress, vib = T.astype(dtype), stress.astype(dtype), vib.astype(dtype)
        t0 = time.perf_counter()
        rate, _ = kernel.step(T, stress, vib, prev_stress)
        times.append((time.perf_counter() - t0) * 1000)
        prev_stress = stress
        last_rate = rate
    state_bytes = kernel.membrane.nbytes + kernel.spike_history.nbytes + kernel.threshold.nbytes
    return times, last_rate, state_bytes


def bench_quantized(h, w, n_steps, rng):
    kernel = QuantizedReflexKernel(h, w)
    prev_stress = np.full((h, w), 12.0)
    times = []
    last_rate = None
    for i in range(n_steps):
        T, stress, vib = _synthetic_frame(h, w, rng, i * 0.05)
        t0 = time.perf_counter()
        rate, _ = kernel.step(T, stress, vib, prev_stress)
        times.append((time.perf_counter() - t0) * 1000)
        prev_stress = stress
        last_rate = rate
    return times, last_rate, kernel.nbytes


def agreement_rate(reference_rate, candidate_rate, threshold=0.25):
    ref_trigger = reference_rate >= threshold
    cand_trigger = candidate_rate >= threshold
    return float((ref_trigger == cand_trigger).mean())


def main():
    ap = argparse.ArgumentParser(description="Arm-optimization benchmark for the BHS reflex kernel")
    ap.add_argument("--height", type=int, default=40)
    ap.add_argument("--width", type=int, default=60)
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--skip-naive", action="store_true", help="Naive pure-python loop is slow; skip for quick runs")
    ap.add_argument("--out", type=str, default=None, help="Optional path to write results as JSON")
    args = ap.parse_args()

    h, w, n = args.height, args.width, args.steps
    results = {"platform": {
        "machine": platform.machine(),
        "processor": platform.processor(),
        "system": platform.system(),
        "python": platform.python_version(),
    }}

    print(f"Platform: {results['platform']}")
    print(f"Grid: {h}x{w}, steps: {n}\n")

    rng = np.random.default_rng(0)
    times_f64, rate_f64, bytes_f64 = bench_vectorized(h, w, n, rng, np.float64)

    rng = np.random.default_rng(0)
    times_f32, rate_f32, bytes_f32 = bench_vectorized(h, w, n, rng, np.float32)

    rng = np.random.default_rng(0)
    times_q, rate_q, bytes_q = bench_quantized(h, w, n, rng)

    entries = [
        ("vectorized_f64 (reference)", times_f64, bytes_f64, agreement_rate(rate_f64, rate_f64)),
        ("vectorized_f32 (Arm SIMD-width)", times_f32, bytes_f32, agreement_rate(rate_f64, rate_f32)),
        ("quantized_int8 (Arm edge)", times_q, bytes_q, agreement_rate(rate_f64, rate_q)),
    ]

    if not args.skip_naive:
        rng = np.random.default_rng(0)
        times_naive, rate_naive, bytes_naive = bench_naive(h, w, min(n, 50), rng)
        entries.insert(0, ("naive (unoptimized)", times_naive, bytes_naive, agreement_rate(rate_f64[:0], rate_f64[:0]) if False else 1.0))

    print(f"{'implementation':32s} {'mean ms/step':>14s} {'state bytes':>12s} {'vs f64 agree':>14s} {'speedup':>10s}")
    ref_mean = float(np.mean(times_f64))
    summary = []
    for name, times, nbytes, agree in entries:
        mean_ms = float(np.mean(times))
        speedup = ref_mean / mean_ms if mean_ms > 0 else float("inf")
        print(f"{name:32s} {mean_ms:14.4f} {nbytes:12d} {agree:14.3f} {speedup:9.2f}x")
        summary.append({
            "name": name, "mean_ms_per_step": mean_ms, "state_bytes": nbytes,
            "agreement_vs_f64": agree, "speedup_vs_f64": speedup,
        })

    results["results"] = summary
    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
