#!/usr/bin/env python3
"""
INT8 -> Ethos-U -> NPU -> Latency
==================================

Builds a small Keras model that mirrors the reflex kernel's per-cell
update (membrane mix + per-channel spike-threshold logits, run over the
full 40x60x4 grid as two 1x1 convolutions -- the Ethos-U-friendly way to
express "the same elementwise math, at every cell, every channel, every
step" that `bhs.reflex.ReflexKernel` does in NumPy), full-integer int8
quantizes it, and compiles it with Arm's real, official Ethos-U NPU
compiler (`vela`, pip package `ethos-u-vela`) targeting an Ethos-U55.

This produces a genuine NPU-compiled artifact (`*_vela.tflite`) plus a
compiler-verified performance report (SRAM/Flash footprint, MAC count,
cycle count, inferences/sec) for a real Arm NPU config -- not a narrated
or hand-waved estimate.

Requires: tensorflow (for the int8 quantizing converter) and
ethos-u-vela (the NPU compiler). Both are pip-installable; see
requirements-npu.txt.

Usage:
    python scripts/build_npu_model.py --accelerator ethos-u55-256
    python scripts/build_npu_model.py --accelerator ethos-u55-32
"""
import argparse
import csv
import os
import subprocess
import sys

import numpy as np

H, W, C = 40, 60, 4  # matches bhs.reflex.ReflexKernel's (channel, y, x) drive tensor
THRESHOLDS = (3.0, 3.0, 3.0, 2.5)  # matches bhs.reflex.ReflexKernel.threshold


def build_and_quantize(out_dir: str) -> str:
    import tensorflow as tf

    inputs = tf.keras.Input(shape=(H, W, C), batch_size=1, name="drive_in")
    x = tf.keras.layers.Conv2D(8, 1, activation="relu", name="membrane_mix")(inputs)
    x = tf.keras.layers.Conv2D(C, 1, activation=None, name="spike_logits")(x)
    outputs = tf.keras.layers.Activation("sigmoid", name="spike_prob")(x)
    model = tf.keras.Model(inputs, outputs, name="reflex_kernel_cell_update")

    # Hand-set, interpretable weights (not a randomly trained black box):
    # membrane_mix expands each channel into itself + a decayed copy;
    # spike_logits recombines them with the same per-channel thresholds
    # the NumPy reflex kernel uses, as a negative bias.
    w1 = np.zeros((1, 1, C, 8), dtype=np.float32)
    for c in range(C):
        w1[0, 0, c, c] = 1.0
        w1[0, 0, c, c + 4] = 0.5
    model.get_layer("membrane_mix").set_weights([w1, np.zeros((8,), dtype=np.float32)])

    w2 = np.zeros((1, 1, 8, C), dtype=np.float32)
    for c in range(C):
        w2[0, 0, c, c] = 1.0
        w2[0, 0, c + 4, c] = 0.5
    b2 = np.array([-t for t in THRESHOLDS], dtype=np.float32)
    model.get_layer("spike_logits").set_weights([w2, b2])

    def representative_dataset():
        rng = np.random.default_rng(0)
        for _ in range(50):
            yield [rng.uniform(0, 4, size=(1, H, W, C)).astype(np.float32)]

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite_model = converter.convert()

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "reflex_kernel_int8.tflite")
    with open(path, "wb") as f:
        f.write(tflite_model)
    print(f"Wrote {path} ({len(tflite_model)} bytes, int8)")
    return path


def compile_for_npu(tflite_path: str, accelerator: str, out_dir: str):
    cmd = [
        "vela", tflite_path,
        "--accelerator-config", accelerator,
        "--system-config", "Ethos_U55_High_End_Embedded",
        "--output-dir", out_dir,
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    csv_path = None
    for fn in os.listdir(out_dir):
        if fn.endswith(".csv"):
            csv_path = os.path.join(out_dir, fn)
    if csv_path is None:
        print("No Vela CSV report found.")
        return

    with open(csv_path) as f:
        row = list(csv.DictReader(f))[0]

    print("\n--- Vela / Ethos-U compiler report ---")
    for key in (
        "accelerator_configuration", "core_clock", "inference_time",
        "inferences_per_second", "cycles_total", "sram_memory_used",
        "off_chip_flash_memory_used", "nn_macs",
    ):
        print(f"  {key:28s} = {row[key]}")
    print(f"\n  inference_time = {float(row['inference_time'])*1e6:.2f} microseconds "
          f"for the whole {H}x{W}x{C} grid, on {accelerator} @ {float(row['core_clock'])/1e6:.0f} MHz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accelerator", default="ethos-u55-256",
                     choices=["ethos-u55-32", "ethos-u55-64", "ethos-u55-128", "ethos-u55-256"])
    ap.add_argument("--out-dir", default="outputs/npu")
    args = ap.parse_args()

    tflite_path = build_and_quantize(args.out_dir)
    compile_for_npu(tflite_path, args.accelerator, os.path.join(args.out_dir, f"vela_{args.accelerator}"))


if __name__ == "__main__":
    main()
