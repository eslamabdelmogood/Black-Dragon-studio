"""Filesystem storage for studio projects.

MVP uses local filesystem storage only, exactly as specified in the
constitution (section 11, "Storage"):

    workspace/projects/<project_id>/
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from .models import SystemSpec

_WORKSPACE_ROOT = os.environ.get(
    "BDS_WORKSPACE_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace"),
)
_PROJECTS_ROOT = os.path.join(_WORKSPACE_ROOT, "projects")

_ID_RE = re.compile(r"^[a-f0-9]{6,32}$")


class UnknownProjectError(KeyError):
    pass


def _validate_project_id(project_id: str) -> str:
    """Prevents path traversal: project ids are always studio-generated hex
    strings, never derived from user input directly (constitution: security 15)."""
    if not _ID_RE.match(project_id):
        raise ValueError(f"invalid project_id '{project_id}'")
    return project_id


def project_dir(project_id: str) -> str:
    _validate_project_id(project_id)
    return os.path.join(_PROJECTS_ROOT, project_id)


def generated_dir(project_id: str) -> str:
    return os.path.join(project_dir(project_id), "generated")


def knowledge_graph_path() -> str:
    return os.path.join(_WORKSPACE_ROOT, "engineering_knowledge_graph.json")


def ensure_project(project_id: str) -> str:
    d = project_dir(project_id)
    os.makedirs(d, exist_ok=True)
    return d


def save_state(project_id: str, state: Dict[str, Any]) -> None:
    d = ensure_project(project_id)
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def load_state(project_id: str) -> Dict[str, Any]:
    d = project_dir(project_id)
    path = os.path.join(d, "state.json")
    if not os.path.exists(path):
        raise UnknownProjectError(project_id)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def project_exists(project_id: str) -> bool:
    try:
        return os.path.exists(os.path.join(project_dir(project_id), "state.json"))
    except ValueError:
        return False


def list_projects() -> list:
    if not os.path.isdir(_PROJECTS_ROOT):
        return []
    return sorted(os.listdir(_PROJECTS_ROOT))
