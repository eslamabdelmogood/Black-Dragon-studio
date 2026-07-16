"""Hard-mode competition-style test for Black Dragon Studio.

This script intentionally exercises the project like a skeptical hackathon judge:
- starts from a clean local workspace and no OpenAI API key
- generates multiple projects from different prompt qualities/domains
- verifies approval gates, stage logs, path traversal protection, ZIP exports
- extracts each ZIP and runs the generated project's own tests and simulator
- verifies the Engineering Knowledge Graph learns from early projects and is reused
"""
from __future__ import annotations

import io
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "studio" / "backend"
WORKSPACE = Path(os.environ.get("BDS_HARD_MODE_WORKSPACE", "/tmp/bds_hard_mode_workspace"))
TIMEOUT_S = int(os.environ.get("BDS_HARD_MODE_TIMEOUT", "90"))

PROMPTS: List[str] = [
    (ROOT / "sample_prompts" / "industrial_pump.txt").read_text(encoding="utf-8").strip(),
    (ROOT / "sample_prompts" / "pipeline_pressure.txt").read_text(encoding="utf-8").strip(),
    "Build a motor overcurrent protection system. Monitor current draw. Alert the operator above 28 amps and shut down above 35 amps to prevent winding damage. Must run fully offline on an ARM edge device.",
    "Monitor my machine and keep it safe with conservative defaults, simulation, tests, dashboard, documentation, and an export package.",
]

os.environ.pop("OPENAI_API_KEY", None)
os.environ["BDS_WORKSPACE_ROOT"] = str(WORKSPACE)
shutil.rmtree(WORKSPACE, ignore_errors=True)
sys.path.insert(0, str(BACKEND))


def ensure_backend_dependencies() -> None:
    """Install backend dependencies when the script is run from a fresh Codespace.

    Judges often run this script before creating a virtual environment.
    Auto-installing the backend requirements makes the judge scripts
    self-contained while still using the repository's pinned requirements file.
    """
    required_modules = ("fastapi", "httpx", "pydantic", "jinja2", "yaml")
    missing = [module for module in required_modules if importlib.util.find_spec(module) is None]
    if not missing:
        return

    requirements = BACKEND / "requirements.txt"
    print(
        f"Missing backend dependencies ({', '.join(missing)}); "
        f"installing from {requirements}...",
        flush=True,
    )
    try:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(requirements),
            ]
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "Could not auto-install backend dependencies. Run:\n"
            f"  {sys.executable} -m pip install -r {requirements}\n"
            "Then re-run this script."
        ) from exc


ensure_backend_dependencies()

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def assert_ok(response, label: str):
    if response.status_code >= 400:
        raise AssertionError(f"{label} failed: {response.status_code} {response.text[:1000]}")
    return response


def run(cmd: List[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S)
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed in {cwd}: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout[-2000:]}\nSTDERR:\n{proc.stderr[-2000:]}"
        )


def extract_project_zip(project_id: str, zip_bytes: bytes) -> Path:
    extract_root = Path(tempfile.mkdtemp(prefix=f"bds_{project_id}_"))
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        bad = zf.testzip()
        if bad:
            raise AssertionError(f"corrupt zip member: {bad}")
        zf.extractall(extract_root)
    children = [p for p in extract_root.iterdir() if p.is_dir()]
    if len(children) != 1:
        raise AssertionError(f"expected one project directory in zip, got {children}")
    return children[0]


def verify_generated_project(project_id: str, zip_bytes: bytes) -> None:
    project_dir = extract_project_zip(project_id, zip_bytes)
    required = [
        "README.md",
        "system_spec.json",
        "generation_manifest.json",
        "engineering_review.json",
        "knowledge_context.json",
        "docs/engineering_plan.md",
        "docs/knowledge_graph.md",
        "deploy/README.md",
        "dashboard/index.html",
        "simulation/simulator.py",
    ]
    for rel in required:
        if not (project_dir / rel).exists():
            raise AssertionError(f"missing generated artifact {rel} in {project_dir}")
    run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=project_dir)
    run([sys.executable, "simulator.py"], cwd=project_dir / "simulation")
    if not (project_dir / "outputs" / "metrics.json").exists():
        raise AssertionError("generated simulator did not produce outputs/metrics.json")


def generate_lifecycle(prompt: str, index: int) -> Dict[str, object]:
    start = time.perf_counter()
    specify = assert_ok(client.post("/api/specify", json={"prompt": prompt}), f"specify[{index}]")
    payload = specify.json()
    project_id = payload["project_id"]
    assert payload["status"] == "needs_approval"
    assert payload["spec"]["sensors"], "spec must include at least one sensor"

    generate_before_approval = client.post(f"/api/projects/{project_id}/generate")
    assert generate_before_approval.status_code == 409, "generation must require approval"

    assert_ok(client.post(f"/api/projects/{project_id}/approve"), f"approve[{index}]")
    generated = assert_ok(client.post(f"/api/projects/{project_id}/generate"), f"generate[{index}]")
    generated_payload = generated.json()
    assert generated_payload["status"] == "validated", generated_payload

    manifest = generated_payload["manifest"]
    assert manifest["engineering_agents"], "manifest must include engineering-agent handoffs"
    assert "engineering_review.json" in manifest["files"]
    assert "knowledge_context.json" in manifest["files"]

    validations = {v["stage"]: v["passed"] for v in manifest["validation"]}
    expected_stages = {
        "schema_validation",
        "static_validation",
        "unit_tests",
        "simulation_smoke_test",
        "package_validation",
    }
    assert expected_stages <= validations.keys(), validations
    assert all(validations[s] for s in expected_stages), validations

    status = assert_ok(client.get(f"/api/projects/{project_id}/status"), f"status[{index}]").json()
    stage_names = [entry["stage"] for entry in status["stage_log"]]
    assert "knowledge_graph_search" in stage_names
    assert "engineering_team_review" in stage_names
    assert "knowledge_graph_learning" in stage_names

    traversal = client.get(f"/api/projects/{project_id}/files/../../../../etc/passwd")
    assert traversal.status_code in (400, 404), traversal.text

    results = assert_ok(client.get(f"/api/projects/{project_id}/results"), f"results[{index}]").json()
    assert results["metrics"], "simulation metrics must be present"

    download = assert_ok(client.get(f"/api/projects/{project_id}/download"), f"download[{index}]")
    verify_generated_project(project_id, download.content)

    elapsed = time.perf_counter() - start
    return {
        "project_id": project_id,
        "elapsed_s": round(elapsed, 2),
        "knowledge_context_count": len(manifest.get("knowledge_context", [])),
        "file_count": len(manifest["files"]),
    }


def main() -> None:
    health = assert_ok(client.get("/api/health"), "health")
    assert health.json()["status"] == "ok"

    summaries = [generate_lifecycle(prompt, i) for i, prompt in enumerate(PROMPTS, start=1)]
    stats = assert_ok(client.get("/api/knowledge-graph/stats"), "knowledge stats").json()
    assert stats["project_count"] == len(PROMPTS), stats
    assert stats["component_count"] >= len(PROMPTS) * 5, stats
    assert any(s["knowledge_context_count"] > 0 for s in summaries[1:]), summaries

    print("Black Dragon Studio hard-mode test passed")
    print(f"Workspace: {WORKSPACE}")
    print(f"Knowledge graph stats: {stats}")
    for summary in summaries:
        print(summary)


if __name__ == "__main__":
    main()
