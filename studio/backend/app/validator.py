"""Validation Pipeline (constitution section 16).

Five stages, each returning a `ValidationStageResult`. Every stage actually
runs the relevant check (subprocess, file inspection, etc.) -- nothing here
is faked or assumed to pass (constitution 14.9: "Never claim a command
succeeded unless its exit code and output were checked.").
"""
from __future__ import annotations

import json
import os
import py_compile
import re
import subprocess
import sys
import zipfile
from typing import List

from .models import SystemSpec, ValidationStageResult

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"(?i)secret\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
]

_TIMEOUT_S = int(os.environ.get("BDS_SUBPROCESS_TIMEOUT", "60"))


def stage1_schema(spec: SystemSpec) -> ValidationStageResult:
    """Pydantic already enforced most of this at construction time; this
    stage re-checks the business rules the constitution calls out
    explicitly, so a failure here is a real (re-verified) failure."""
    details: List[str] = []
    passed = True

    if not spec.project.name:
        passed = False
        details.append("project name is empty")

    if len(spec.sensors) < 1:
        passed = False
        details.append("at least one sensor is required")

    all_actions = {a for act in spec.actuators for a in act.allowed_actions}
    if len(all_actions) < 1:
        passed = False
        details.append("at least one allowed action is required")

    for rule in spec.reflex_rules:
        if rule.action not in all_actions:
            passed = False
            details.append(f"rule '{rule.id}' references undeclared action '{rule.action}'")
        sensor_ids = {s.id for s in spec.sensors}
        if rule.sensor_id not in sensor_ids:
            passed = False
            details.append(f"rule '{rule.id}' references undeclared sensor '{rule.sensor_id}'")

    sensor_units = {s.type: s.unit for s in spec.sensors}
    for s in spec.sensors:
        if sensor_units.get(s.type) != s.unit:
            passed = False
            details.append(f"sensor '{s.id}' unit mismatch for type '{s.type}'")

    if passed:
        details.append("all schema checks passed")
    return ValidationStageResult(stage="schema_validation", passed=passed, details=details)


def stage2_static(output_dir: str) -> ValidationStageResult:
    details: List[str] = []
    passed = True

    py_files = []
    for root, _, files in os.walk(os.path.join(output_dir, "src")):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    for root, _, files in os.walk(os.path.join(output_dir, "tests")):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    sim_path = os.path.join(output_dir, "simulation", "simulator.py")
    if os.path.exists(sim_path):
        py_files.append(sim_path)

    for path in py_files:
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as exc:
            passed = False
            details.append(f"syntax error in {os.path.relpath(path, output_dir)}: {exc}")

    for cfg_name in ("sensors.yaml", "actuators.yaml", "reflex_rules.yaml", "runtime.yaml"):
        cfg_path = os.path.join(output_dir, "config", cfg_name)
        if not os.path.exists(cfg_path):
            passed = False
            details.append(f"missing config file: config/{cfg_name}")
            continue
        try:
            import yaml

            with open(cfg_path, "r", encoding="utf-8") as f:
                yaml.safe_load(f)
        except Exception as exc:  # noqa: BLE001
            passed = False
            details.append(f"config/{cfg_name} failed to parse: {exc}")

    secret_hits = []
    for root, _, files in os.walk(output_dir):
        if os.sep + "outputs" + os.sep in root + os.sep:
            continue
        for f in files:
            if not f.endswith((".py", ".yaml", ".yml", ".json", ".md")):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            except OSError:
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern.search(content):
                    secret_hits.append(os.path.relpath(path, output_dir))
                    break
    if secret_hits:
        passed = False
        details.append(f"possible hardcoded secrets found in: {secret_hits}")

    if passed:
        details.append(f"compiled {len(py_files)} python files, parsed 4 config files, no secrets found")
    return ValidationStageResult(stage="static_validation", passed=passed, details=details)


def _run(cmd: List[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
    )


def stage3_unit_tests(output_dir: str) -> ValidationStageResult:
    details: List[str] = []
    try:
        proc = _run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=output_dir)
    except FileNotFoundError as exc:
        return ValidationStageResult(stage="unit_tests", passed=False, details=[str(exc)])
    except subprocess.TimeoutExpired:
        return ValidationStageResult(stage="unit_tests", passed=False, details=["pytest timed out"])

    passed = proc.returncode == 0
    tail = "\n".join((proc.stdout + "\n" + proc.stderr).strip().splitlines()[-20:])
    details.append(f"exit_code={proc.returncode}")
    details.append(tail)
    return ValidationStageResult(stage="unit_tests", passed=passed, details=details)


def stage4_simulation_smoke_test(output_dir: str) -> ValidationStageResult:
    details: List[str] = []
    sim_path = os.path.join(output_dir, "simulation", "simulator.py")
    if not os.path.exists(sim_path):
        return ValidationStageResult(stage="simulation_smoke_test", passed=False, details=["simulation/simulator.py missing"])

    try:
        proc = _run([sys.executable, "simulator.py"], cwd=os.path.join(output_dir, "simulation"))
    except subprocess.TimeoutExpired:
        return ValidationStageResult(stage="simulation_smoke_test", passed=False, details=["simulation timed out"])

    if proc.returncode != 0:
        return ValidationStageResult(
            stage="simulation_smoke_test",
            passed=False,
            details=[f"exit_code={proc.returncode}", proc.stderr[-2000:]],
        )

    metrics_path = os.path.join(output_dir, "outputs", "metrics.json")
    results_path = os.path.join(output_dir, "outputs", "simulation_results.json")
    if not os.path.exists(metrics_path) or not os.path.exists(results_path):
        return ValidationStageResult(
            stage="simulation_smoke_test", passed=False, details=["outputs/metrics.json or simulation_results.json not produced"]
        )

    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    at_least_one_response = False
    for _name, m in metrics.items():
        if m.get("final_action") and m.get("final_action") != "do_nothing":
            at_least_one_response = True
        if m.get("critical_fire_count", 0) > 0:
            at_least_one_response = True

    if not at_least_one_response:
        return ValidationStageResult(
            stage="simulation_smoke_test",
            passed=False,
            details=["no scenario produced a non-trivial response/action"],
        )

    details.append(f"simulation completed, {len(metrics)} scenarios, metrics computed")
    return ValidationStageResult(stage="simulation_smoke_test", passed=True, details=details)


def stage5_package_validation(output_dir: str, zip_path: str, manifest_files: List[str]) -> ValidationStageResult:
    details: List[str] = []
    passed = True

    required_dirs = ["config", "src", "simulation", "dashboard", "tests", "outputs", "architecture", "docs", "deploy"]
    for d in required_dirs:
        if not os.path.isdir(os.path.join(output_dir, d)):
            passed = False
            details.append(f"missing required directory: {d}/")

    if not os.path.exists(os.path.join(output_dir, "README.md")):
        passed = False
        details.append("missing README.md")

    for required_file in ("engineering_review.json", "docs/engineering_plan.md", "deploy/README.md"):
        if not os.path.exists(os.path.join(output_dir, required_file)):
            passed = False
            details.append(f"missing required generated artifact: {required_file}")

    if not (os.path.exists(os.path.join(output_dir, "requirements.txt")) or os.path.exists(os.path.join(output_dir, "pyproject.toml"))):
        passed = False
        details.append("missing requirements.txt / pyproject.toml (setup command target)")

    if not os.path.exists(zip_path):
        passed = False
        details.append(f"zip not found at {zip_path}")
    else:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                bad = zf.testzip()
                if bad is not None:
                    passed = False
                    details.append(f"zip corrupted at member {bad}")
                names = set(n.split("/", 1)[1] if "/" in n else n for n in zf.namelist() if not n.endswith("/"))
        except zipfile.BadZipFile:
            passed = False
            details.append("zip failed to open")
            names = set()

        missing_from_zip = [f for f in manifest_files if f not in names and not f.startswith("outputs/")]
        if missing_from_zip:
            passed = False
            details.append(f"manifest files missing from zip: {missing_from_zip[:10]}")

    if passed:
        details.append("package validation passed: structure, README, setup files, and zip integrity all OK")
    return ValidationStageResult(stage="package_validation", passed=passed, details=details)


def run_pre_package_pipeline(spec: SystemSpec, output_dir: str) -> List[ValidationStageResult]:
    """Stages 1-4, run before packaging (so a failing simulation blocks export)."""
    results = [
        stage1_schema(spec),
        stage2_static(output_dir),
        stage3_unit_tests(output_dir),
        stage4_simulation_smoke_test(output_dir),
    ]
    return results
