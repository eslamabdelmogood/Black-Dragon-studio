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
from .knowledge_graph import graph_stats, learn_from_project, record_feedback, search_similar
from .models import (
    FeedbackRecord,
    FeedbackRequest,
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

    knowledge_context = search_similar(spec)

    state = {
        "project_id": project_id,
        "status": ProjectStatus.NEEDS_APPROVAL.value,
        "prompt": req.prompt,
        "spec": json.loads(spec.model_dump_json()),
        "spec_source": source,
        "questions": [q.model_dump() for q in questions],
        "warnings": list(spec.warnings),
        "knowledge_context": knowledge_context,
        "created_at": _now(),
        "stage_log": [],
    }
    _append_stage_log(state, "parsing_requirements", "completed", f"source={source}")
    _append_stage_log(
        state,
        "knowledge_graph_search",
        "completed",
        f"{len(knowledge_context)} reusable component(s) found",
    )
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


@@ -153,58 +166,68 @@ def approve(project_id: str) -> Dict[str, Any]:
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

    knowledge_context = state.get("knowledge_context", [])

    output_dir = os.path.join(storage.generated_dir(project_id), spec.project.name)

    # Stage: generating_project
    try:
        manifest = generator.generate_project(spec, project_id, output_dir, engineering_agents, knowledge_context)
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
@@ -214,55 +237,101 @@ def generate(project_id: str) -> Dict[str, Any]:
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

    if stage5.passed:
        metrics = {}
        metrics_path = os.path.join(output_dir, "outputs", "metrics.json")
        if os.path.exists(metrics_path):
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
        learning = learn_from_project(spec, project_id, state["manifest"], metrics)
        state["knowledge_graph_learning"] = learning
        _append_stage_log(
            state,
            "knowledge_graph_learning",
            "completed",
            f"{learning['component_count']} reusable component(s) stored",
        )

    _save_state(project_id, state)

    return {"project_id": project_id, "status": state["status"], "manifest": state["manifest"]}


@app.post("/api/projects/{project_id}/feedback")
def submit_feedback(project_id: str, req: FeedbackRequest) -> Dict[str, Any]:
    state = _get_state(project_id)
    if state.get("status") not in {ProjectStatus.VALIDATED.value, ProjectStatus.SIMULATED.value}:
        raise HTTPException(status_code=409, detail="feedback is accepted after a project has validated or simulated")

    spec = SystemSpec.model_validate(state["spec"])
    record = FeedbackRecord(
        project_id=project_id,
        project_name=spec.project.name,
        **req.model_dump(),
    )
    state.setdefault("feedback", []).append(record.model_dump())
    learning = record_feedback(record, spec)
    state["knowledge_graph_feedback"] = learning
    _append_stage_log(
        state,
        "user_feedback",
        "completed",
        f"feedback stored as {learning['component_id']}",
    )
    _save_state(project_id, state)
    return {
        "project_id": project_id,
        "status": state["status"],
        "feedback": record.model_dump(),
        "knowledge_graph_update": learning,
    }


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
@@ -334,46 +403,51 @@ def get_file(project_id: str, file_path: str) -> Dict[str, Any]:
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


@app.get("/api/knowledge-graph/stats")
def knowledge_graph_stats() -> Dict[str, Any]:
    return graph_stats()


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
