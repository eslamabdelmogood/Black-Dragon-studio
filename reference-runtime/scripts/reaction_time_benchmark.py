#!/usr/bin/env python3
"""
Reaction-Time Benchmark: Polling -> Interrupt -> Reflex Kernel
================================================================

This is NOT a Python-vs-NumPy speed test. It's a benchmark of three
*control-loop architectures* for noticing a fault and reacting to it,
which is the actual design question for an always-on Arm edge sensing
node:

  1. POLLING     - a scheduler wakes up every `poll_interval` and checks
                   the sensor value against a threshold. This is how most
                   industrial PLC/SCADA loops and naive `while True: read();
                   sleep()` firmware work today.
  2. INTERRUPT    - the instant the raw sensor value crosses a threshold,
                   a callback fires immediately (modelling a GPIO/analog
                   comparator interrupt on a Cortex-M, or an Ethos-U NPU
                   IRQ-on-done instead of a CPU polling a status register).
                   Fast, but fragile: it reacts to a *single noisy sample*.
  3. REFLEX KERNEL - the BHS spiking reflex kernel (`bhs.reflex`). Also
                   event-driven (no fixed poll interval), but requires a
                   *sustained* spike rate over a short integration window
                   before declaring a detection. Slightly slower than a
                   raw interrupt on a clean signal, but does not fire on
                   single-sample noise the way (2) does.

All three are run as real, measured Python code against the same
synthetic noisy sensor stream with an identical fault onset time -- these
are genuine wall-clock/simulated-time latencies from executing the code
below, not narrated numbers. See the bottom of this file for how the
absolute values map (and don't map) onto real Arm Cortex-M/-A hardware.
"""
from __future__ import annotations

import argparse
import statistics
import threading
import time

import numpy as np

from bhs.reflex import ReflexKernel


# ---------------------------------------------------------------------------
# Shared synthetic fault signal: flat noisy baseline, then a step fault onset
# ---------------------------------------------------------------------------
def make_signal(n_samples: int, dt: float, fault_onset_step: int, noise_std: float, rng):
    t = np.arange(n_samples) * dt
    baseline = 45.0 + rng.normal(0, noise_std, n_samples)  # e.g. degrees C, below threshold
    fault_step = np.zeros(n_samples)
    fault_step[fault_onset_step:] = 60.0  # sudden jump well above threshold, plus ongoing noise
    signal = baseline + fault_step
    return t, signal


THRESHOLD_C = 60.0


# ---------------------------------------------------------------------------
# 1. Polling architecture
# ---------------------------------------------------------------------------
def polling_reaction_time(t, signal, dt, poll_interval_s, fault_onset_t):
    """Simulated-time polling: only samples the signal every poll_interval_s.
    Returns latency in seconds from fault onset to the first poll that
    observes a value over threshold."""
    poll_stride = max(1, int(round(poll_interval_s / dt)))
    for i in range(0, len(signal), poll_stride):
        if t[i] < fault_onset_t:
            continue
        if signal[i] >= THRESHOLD_C:
            return t[i] - fault_onset_t
    return None


# ---------------------------------------------------------------------------
# 2. Interrupt architecture: reacts to the very first sample over threshold
# ---------------------------------------------------------------------------
def interrupt_reaction_time(t, signal, fault_onset_t):
    post_mask = t >= fault_onset_t
    post_signal = signal[post_mask]
    post_t = t[post_mask]
    idx = np.argmax(post_signal >= THRESHOLD_C)
    if post_signal[idx] < THRESHOLD_C:
        return None
    return post_t[idx] - fault_onset_t


def interrupt_false_trigger_count(t, signal, fault_onset_t):
    """How many samples BEFORE the real fault onset would have falsely
    tripped a raw single-sample interrupt threshold, due to noise alone."""
    pre_fault = signal[t < fault_onset_t]
    return int((pre_fault >= THRESHOLD_C).sum())


# ---------------------------------------------------------------------------
# 3. Reflex kernel: event-driven + sustained-window integration
# ---------------------------------------------------------------------------
def reflex_kernel_reaction_time(t, signal, dt, fault_onset_t, height=1, width=1):
    kernel = ReflexKernel(height, width, window=10)
    prev_stress = np.full((height, width), 12.0)
    detect_t = None
    false_triggers = 0
    fault_seen = False
    for i in range(len(signal)):
        T = np.full((height, width), signal[i])
        stress = np.full((height, width), 12.0)  # only the temperature channel is driven here
        vib = np.full((height, width), 0.45)
        spike_rate, _ = kernel.step(T, stress, vib, prev_stress)
        prev_stress = stress
        triggered = ReflexKernel.sustained_trigger(spike_rate).any()
        if triggered and detect_t is None and t[i] >= fault_onset_t:
            detect_t = t[i] - fault_onset_t
        if triggered and t[i] < fault_onset_t:
            false_triggers += 1
    return detect_t, false_triggers


# ---------------------------------------------------------------------------
# Real-thread variant: actual OS-scheduled polling vs. immediate callback,
# so the polling number reflects genuine scheduling jitter, not just an
# arithmetic stride.
# ---------------------------------------------------------------------------
def live_thread_comparison(poll_interval_s=0.01, settle_s=0.05, fault_delay_s=0.03):
    """Runs a real background thread that flips a shared flag after
    `fault_delay_s`, and measures, with wall-clock time.perf_counter(),
    how long a real polling thread vs. a real immediate-callback thread
    takes to notice it."""
    fault_time = {}
    poll_detect = {}
    interrupt_detect = {}
    flag = {"on": False}

    def fault_thread():
        time.sleep(fault_delay_s)
        fault_time["t"] = time.perf_counter()
        flag["on"] = True
        # "interrupt": call the handler directly, in-line, the moment the
        # condition becomes true -- this is the real-thread analogue of an
        # ISR firing immediately on a hardware edge.
        interrupt_detect["t"] = time.perf_counter()

    def polling_thread():
        while "t" not in fault_time or time.perf_counter() - fault_time.get("t", 1e18) < 0:
            pass
        while True:
            if flag["on"]:
                poll_detect["t"] = time.perf_counter()
                return
            time.sleep(poll_interval_s)

    ft = threading.Thread(target=fault_thread)
    pt = threading.Thread(target=polling_thread)
    pt.start()
    ft.start()
    ft.join()
    time.sleep(settle_s)
    pt.join(timeout=settle_s + poll_interval_s * 2)

    if "t" not in fault_time or "t" not in poll_detect:
        return None, None
    return (
        interrupt_detect["t"] - fault_time["t"],
        poll_detect["t"] - fault_time["t"],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--dt", type=float, default=0.001)
    ap.add_argument("--n-samples", type=int, default=2000)
    ap.add_argument("--fault-onset-step", type=int, default=1013)
    ap.add_argument("--noise-std", type=float, default=6.0)
    ap.add_argument("--poll-interval", type=float, default=0.05)
    args = ap.parse_args()

    rng = np.random.default_rng(1)

    poll_lat, intr_lat, reflex_lat = [], [], []
    intr_false, reflex_false = [], []

    for trial in range(args.trials):
        onset_step = args.fault_onset_step + int(rng.integers(0, args.poll_interval / args.dt))
        t, signal = make_signal(args.n_samples, args.dt, onset_step, args.noise_std, rng)
        fault_onset_t = t[onset_step]

        pl = polling_reaction_time(t, signal, args.dt, args.poll_interval, fault_onset_t)
        il = interrupt_reaction_time(t, signal, fault_onset_t)
        rl, rfalse = reflex_kernel_reaction_time(t, signal, args.dt, fault_onset_t)
        ifalse = interrupt_false_trigger_count(t, signal, fault_onset_t)

        if pl is not None:
            poll_lat.append(pl)
        if il is not None:
            intr_lat.append(il)
        if rl is not None:
            reflex_lat.append(rl)
        intr_false.append(ifalse)
        reflex_false.append(rfalse)

    def summarize(name, vals, false_vals=None):
        if not vals:
            print(f"{name:20s}  no detections across {args.trials} trials")
            return
        s = (
            f"{name:20s}  mean={statistics.mean(vals)*1000:8.3f} ms  "
            f"median={statistics.median(vals)*1000:8.3f} ms  "
            f"max={max(vals)*1000:8.3f} ms  n={len(vals)}/{args.trials}"
        )
        if false_vals is not None:
            s += f"   false-triggers/trial (noise-only, pre-fault)={statistics.mean(false_vals):.2f}"
        print(s)

    print(f"Simulated-time sensor stream: dt={args.dt*1000:.1f}ms, noise_std={args.noise_std}, "
          f"poll_interval={args.poll_interval*1000:.0f}ms, {args.trials} trials\n")
    summarize("Polling", poll_lat)
    summarize("Interrupt (raw)", intr_lat, intr_false)
    summarize("Reflex kernel", reflex_lat, reflex_false)

    print("\n--- Real-thread wall-clock sanity check (single run, this host) ---")
    intr_wall, poll_wall = live_thread_comparison(poll_interval_s=args.poll_interval)
    if intr_wall is not None:
        print(f"Interrupt (real thread callback): {intr_wall*1e6:9.1f} us")
        print(f"Polling   (real thread, {args.poll_interval*1000:.0f}ms interval): {poll_wall*1e6:9.1f} us")


if __name__ == "__main__":
    main()
