"""Black Dragon Studio backend.

Implements the API contract from the constitution (section 13) end to end:
specify -> approve -> generate -> status -> simulate -> results -> download.

Run with:
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import generator, packager, storage, validator
from .engineering_team import run_engineering_team, summarize_agent_results
from .models import (
    GenerationManifest,
    ProjectStatus,
    SpecifyRequest,
    SpecifyResponse,
    SystemSpec,
    ValidationStageResult,
    new_project_id,
)
from .spec_agent import extract_spec

app = FastAPI(title="Black Dragon Studio", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")

GENERATION_STAGES = [
    "parsing_requirements",
    "validating_specification",
    "generating_project",
    "running_tests",
    "running_simulation",
    "packaging_project",
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _get_state(project_id: str) -> Dict[str, Any]:
    try:
        return storage.load_state(project_id)
    except storage.UnknownProjectError:
        raise HTTPException(status_code=404, detail=f"unknown project_id '{project_id}'")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _save_state(project_id: str, state: Dict[str, Any]) -> None:
    state["updated_at"] = _now()
    storage.save_state(project_id, state)


def _append_stage_log(state: Dict[str, Any], stage: str, status: str, detail: str = "") -> None:
    state.setdefault("stage_log", []).append(
        {"stage": stage, "status": status, "detail": detail, "at": _now()}
    )


# --------------------------------------------------------------------------
# Screen 1 / Step 1-2: Describe + Clarify
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "time": _now()}


@app.post("/api/specify", response_model=SpecifyResponse)
def specify(req: SpecifyRequest) -> SpecifyResponse:
    spec, questions, source = extract_spec(req.prompt)
    project_id = new_project_id()

    state = {
        "project_id": project_id,
        "status": ProjectStatus.NEEDS_APPROVAL.value,
        "prompt": req.prompt,
        "spec": json.loads(spec.model_dump_json()),
        "spec_source": source,
        "questions": [q.model_dump() for q in questions],
        "warnings": list(spec.warnings),
        "created_at": _now(),
        "stage_log": [],
    }
    _append_stage_log(state, "parsing_requirements", "completed", f"source={source}")
    _save_state(project_id, state)

    return SpecifyResponse(
        project_id=project_id,
        status=ProjectStatus.NEEDS_APPROVAL,
        spec=spec,
        questions=questions,
        warnings=spec.warnings,
    )


# --------------------------------------------------------------------------
# Screen 2: Specification Review (get / edit / approve)
# --------------------------------------------------------------------------

@app.get("/api/projects/{project_id}/spec")
def get_spec(project_id: str) -> Dict[str, Any]:
    state = _get_state(project_id)
    return {"project_id": project_id, "status": state["status"], "spec": state["spec"]}


class SpecUpdateRequest(BaseModel):
    spec: Dict[str, Any]


@app.put("/api/projects/{project_id}/spec")
def update_spec(project_id: str, req: SpecUpdateRequest) -> Dict[str, Any]:
    state = _get_state(project_id)
    if state["status"] not in {ProjectStatus.NEEDS_APPROVAL.value, ProjectStatus.DRAFT.value}:
        raise HTTPException(status_code=409, detail="spec can only be edited before approval")
    try:
        validated = SystemSpec.model_validate(req.spec)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"invalid spec: {exc}")
    state["spec"] = json.loads(validated.model_dump_json())
    _save_state(project_id, state)
    return {"project_id": project_id, "status": state["status"], "spec": state["spec"]}


@app.post("/api/projects/{project_id}/approve")
def approve(project_id: str) -> Dict[str, Any]:
    state = _get_state(project_id)
    if state["status"] not in {ProjectStatus.NEEDS_APPROVAL.value, ProjectStatus.DRAFT.value}:
        raise HTTPException(status_code=409, detail=f"cannot approve from status '{state['status']}'")
    try:
        SystemSpec.model_validate(state["spec"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"spec failed validation: {exc}")
    state["status"] = ProjectStatus.APPROVED.value
    _append_stage_log(state, "validating_specification", "completed", "spec approved by user")
    _save_state(project_id, state)
    return {"project_id": project_id, "status": state["status"]}


# --------------------------------------------------------------------------
# Screen 3: Generation Progress (Steps 4-5 in the constitution)
# --------------------------------------------------------------------------

@app.post("/api/projects/{project_id}/generate")
def generate(project_id: str) -> Dict[str, Any]:
    state = _get_state(project_id)
    if state["status"] != ProjectStatus.APPROVED.value:
        raise HTTPException(
            status_code=409, detail=f"project must be 'approved' before generation, currently '{state['status']}'"
        )

    spec = SystemSpec.model_validate(state["spec"])
    engineering_agents = run_engineering_team(spec)
    state["engineering_agents"] = summarize_agent_results(engineering_agents)
    _append_stage_log(
        state,
        "engineering_team_review",
        "completed",
        " -> ".join(agent.role for agent in engineering_agents),
    )
    state["status"] = ProjectStatus.GENERATING.value
    _save_state(project_id, state)

    output_dir = os.path.join(storage.generated_dir(project_id), spec.project.name)

    # Stage: generating_project
    try:
        manifest = generator.generate_project(spec, project_id, output_dir, engineering_agents)
        _append_stage_log(state, "generating_project", "completed", f"{len(manifest.files)} files written")
    except Exception as exc:  # noqa: BLE001
        state["status"] = ProjectStatus.FAILED.value
        _append_stage_log(state, "generating_project", "failed", str(exc))
        _save_state(project_id, state)
        raise HTTPException(status_code=500, detail=f"generation failed: {exc}")

    state["status"] = ProjectStatus.VALIDATING.value
    _save_state(project_id, state)

    # Stages 1-4: schema, static, unit tests, simulation smoke test
    results: List[ValidationStageResult] = validator.run_pre_package_pipeline(spec, output_dir)
    for r in results:
        constitution_stage = {
            "schema_validation": "validating_specification",
            "static_validation": "generating_project",
            "unit_tests": "running_tests",
            "simulation_smoke_test": "running_simulation",
        }[r.stage]
        _append_stage_log(state, constitution_stage, "completed" if r.passed else "failed", "; ".join(r.details)[:500])

    all_pre_passed = all(r.passed for r in results)
    manifest.validation = results

    if not all_pre_passed:
        state["status"] = ProjectStatus.VALIDATION_FAILED.value
        state["manifest"] = json.loads(manifest.model_dump_json())
        state["output_dir"] = output_dir
        _save_state(project_id, state)
        return {
            "project_id": project_id,
            "status": state["status"],
            "manifest": state["manifest"],
        }

    # Packaging + stage 5
    zip_path = os.path.join(storage.project_dir(project_id), "export", f"{spec.project.name}.zip")
    try:
        packager.make_zip(output_dir, zip_path, root_name=spec.project.name)
        _append_stage_log(state, "packaging_project", "completed", zip_path)
    except Exception as exc:  # noqa: BLE001
        state["status"] = ProjectStatus.FAILED.value
        _append_stage_log(state, "packaging_project", "failed", str(exc))
        _save_state(project_id, state)
        raise HTTPException(status_code=500, detail=f"packaging failed: {exc}")

    stage5 = validator.stage5_package_validation(output_dir, zip_path, manifest.files)
    manifest.validation.append(stage5)

    state["manifest"] = json.loads(manifest.model_dump_json())
    state["output_dir"] = output_dir
    state["zip_path"] = zip_path
    state["status"] = ProjectStatus.VALIDATED.value if stage5.passed else ProjectStatus.VALIDATION_FAILED.value
    _save_state(project_id, state)

    return {"project_id": project_id, "status": state["status"], "manifest": state["manifest"]}


@app.get("/api/projects/{project_id}/status")
def status(project_id: str) -> Dict[str, Any]:
    state = _get_state(project_id)
    return {
        "project_id": project_id,
        "status": state["status"],
        "stage_log": state.get("stage_log", []),
        "warnings": state.get("warnings", []),
    }


# --------------------------------------------------------------------------
# Screen 5: Simulation
# --------------------------------------------------------------------------

@app.post("/api/projects/{project_id}/simulate")
def simulate(project_id: str) -> Dict[str, Any]:
    state = _get_state(project_id)
    output_dir = state.get("output_dir")
    if not output_dir or not os.path.isdir(output_dir):
        raise HTTPException(status_code=409, detail="project has not been generated yet")

    sim_path = os.path.join(output_dir, "simulation", "simulator.py")
    proc = subprocess.run(
        [sys.executable, "simulator.py"],
        cwd=os.path.join(output_dir, "simulation"),
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("BDS_SUBPROCESS_TIMEOUT", "60")),
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"simulation failed: {proc.stderr[-2000:]}")

    state["status"] = ProjectStatus.SIMULATED.value
    _append_stage_log(state, "running_simulation", "completed", "manual re-run via /simulate")
    _save_state(project_id, state)

    return get_results(project_id)


@app.get("/api/projects/{project_id}/results")
def get_results(project_id: str) -> Dict[str, Any]:
    state = _get_state(project_id)
    output_dir = state.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=409, detail="project has not been generated yet")

    metrics_path = os.path.join(output_dir, "outputs", "metrics.json")
    results_path = os.path.join(output_dir, "outputs", "simulation_results.json")
    if not (os.path.exists(metrics_path) and os.path.exists(results_path)):
        raise HTTPException(status_code=409, detail="no simulation results yet; run /generate or /simulate first")

    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    return {
        "project_id": project_id,
        "metrics": metrics,
        "scenarios": results,
        "test_results": state.get("manifest", {}).get("validation", []),
    }


# --------------------------------------------------------------------------
# Screen 4: Project Workspace -- Files tab
# --------------------------------------------------------------------------

@app.get("/api/projects/{project_id}/files")
def list_files(project_id: str) -> Dict[str, Any]:
    state = _get_state(project_id)
    manifest = state.get("manifest")
    if not manifest:
        raise HTTPException(status_code=409, detail="project has not been generated yet")
    return {"project_id": project_id, "files": manifest["files"]}


@app.get("/api/projects/{project_id}/files/{file_path:path}")
def get_file(project_id: str, file_path: str) -> Dict[str, Any]:
    state = _get_state(project_id)
    output_dir = state.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=409, detail="project has not been generated yet")

    # prevent path traversal: resolve and ensure the path stays inside output_dir
    full_path = os.path.normpath(os.path.join(output_dir, file_path))
    if not full_path.startswith(os.path.normpath(output_dir) + os.sep):
        raise HTTPException(status_code=400, detail="invalid file path")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="file not found")

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="binary file, cannot preview")

    return {"path": file_path, "content": content}


# --------------------------------------------------------------------------
# Screen 6: Export
# --------------------------------------------------------------------------

@app.get("/api/projects/{project_id}/download")
def download(project_id: str) -> FileResponse:
    state = _get_state(project_id)
    zip_path = state.get("zip_path")
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=409, detail="project has not been packaged yet")
    filename = os.path.basename(zip_path)
    return FileResponse(zip_path, media_type="application/zip", filename=filename)


@app.get("/api/projects/{project_id}/manifest")
def get_manifest(project_id: str) -> Dict[str, Any]:
    state = _get_state(project_id)
    manifest = state.get("manifest")
    if not manifest:
        raise HTTPException(status_code=409, detail="project has not been generated yet")
    return manifest


# --------------------------------------------------------------------------
# Static frontend (single-page vanilla JS app, see /frontend)
# --------------------------------------------------------------------------

if os.path.isdir(_FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        index_path = os.path.join(_FRONTEND_DIR, "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
