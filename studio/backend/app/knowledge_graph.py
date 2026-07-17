"""Engineering Knowledge Graph for Black Dragon Studio.

The graph stores reusable engineering components extracted from completed,
validated projects. It deliberately stores structured summaries and metrics --
not raw generated source code -- so future projects can reuse proven patterns
without copying implementation details blindly.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import FeedbackRecord, SystemSpec
from . import storage

GRAPH_VERSION = "1.0"


def _empty_graph() -> Dict[str, Any]:
    return {
        "version": GRAPH_VERSION,
        "projects": [],
        "components": [],
        "feedback": [],
    }


def _load_graph() -> Dict[str, Any]:
    path = storage.knowledge_graph_path()
    if not os.path.exists(path):
        return _empty_graph()
    try:
        with open(path, "r", encoding="utf-8") as f:
            graph = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _empty_graph()
    graph.setdefault("version", GRAPH_VERSION)
    graph.setdefault("projects", [])
    graph.setdefault("components", [])
    graph.setdefault("feedback", [])
    return graph


def _save_graph(graph: Dict[str, Any]) -> None:
    path = storage.knowledge_graph_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, sort_keys=True)


def _component_id(project_id: str, component_type: str, name: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
    return f"{project_id}:{component_type}:{safe}"


def _spec_fingerprint(spec: SystemSpec) -> Dict[str, Any]:
    return {
        "domain": spec.project.domain,
        "target_platform": spec.project.target_platform,
        "sensor_types": sorted({s.type for s in spec.sensors}),
        "actions": sorted({a for actuator in spec.actuators for a in actuator.allowed_actions}),
        "scenario_names": list(spec.simulation.scenarios),
        "operating_modes": list(spec.operating_modes),
    }


def _safe_metric_summary(metrics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not metrics:
        return {}
    summary: Dict[str, Any] = {}
    for scenario, values in metrics.items():
        if not isinstance(values, dict):
            continue
        summary[scenario] = {
            key: values.get(key)
            for key in (
                "reflex_fire_count",
                "critical_fire_count",
                "false_alarms",
                "final_action",
                "final_mode",
                "correct_action_rate",
                "final_damage_proxy",
            )
            if key in values
        }
    return summary


def extract_components(
    spec: SystemSpec,
    project_id: str,
    manifest: Dict[str, Any],
    metrics: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Create reusable graph components from a completed project."""
    fingerprint = _spec_fingerprint(spec)
    base = {
        "project_id": project_id,
        "project_name": spec.project.name,
        "domain": spec.project.domain,
        "target_platform": spec.project.target_platform,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    validation_stages = [v.get("stage") for v in manifest.get("validation", []) if v.get("passed")]

    components = [
        {
            **base,
            "id": _component_id(project_id, "architecture", spec.project.name),
            "type": "architecture",
            "name": f"{spec.project.domain}:{'-'.join(fingerprint['sensor_types'])}",
            "summary": "Layered Physical AI runtime with sensing, normalization, reflex, prediction, policy, adaptation, actuation, dashboard, and logs.",
            "tags": [spec.project.domain, *fingerprint["sensor_types"], spec.project.target_platform],
            "reusable_fields": {
                "runtime_layers": ["sensing", "normalization", "reflex", "prediction", "policy", "adaptation", "actuation", "dashboard", "logs"],
                "sensor_types": fingerprint["sensor_types"],
                "actions": fingerprint["actions"],
            },
        },
        {
            **base,
            "id": _component_id(project_id, "safety_policy", spec.project.name),
            "type": "safety_policy",
            "name": f"{spec.project.name} reflex policy",
            "summary": "Deterministic warning and critical reflex rules derived from approved thresholds.",
            "tags": ["safety", "reflex", *fingerprint["sensor_types"], *fingerprint["actions"]],
            "reusable_fields": {
                "rule_count": len(spec.reflex_rules),
                "critical_rule_count": len([r for r in spec.reflex_rules if r.severity == "critical"]),
                "ignore_isolated_spikes": any(r.ignore_isolated_spikes for r in spec.reflex_rules),
                "actions": fingerprint["actions"],
            },
        },
        {
            **base,
            "id": _component_id(project_id, "simulation_model", spec.project.name),
            "type": "simulation_model",
            "name": f"{spec.project.name} simulation suite",
            "summary": "Synthetic scenario suite used to validate normal, gradual fault, noise spike, and critical fault behavior.",
            "tags": ["simulation", *fingerprint["scenario_names"], *fingerprint["sensor_types"]],
            "reusable_fields": {
                "duration_seconds": spec.simulation.duration_seconds,
                "scenarios": fingerprint["scenario_names"],
                "metrics": list(spec.metrics),
                "performance_metrics": _safe_metric_summary(metrics),
            },
        },
        {
            **base,
            "id": _component_id(project_id, "validation_strategy", spec.project.name),
            "type": "validation_strategy",
            "name": f"{spec.project.name} validation gates",
            "summary": "Schema, static, unit, simulation, and package checks required before export.",
            "tags": ["testing", "validation", *validation_stages],
            "reusable_fields": {
                "validation_stages": validation_stages,
                "test_strategy": ["schema_validation", "static_validation", "unit_tests", "simulation_smoke_test", "package_validation"],
            },
        },
        {
            **base,
            "id": _component_id(project_id, "dashboard_layout", spec.project.name),
            "type": "dashboard_layout",
            "name": f"{spec.project.name} operational dashboard",
            "summary": "Single-page dashboard pattern showing scenario metrics, reflex triggers, actions, modes, and a simulation timeline.",
            "tags": ["dashboard", "timeline", "metrics", *fingerprint["sensor_types"]],
            "reusable_fields": {
                "panels": ["overview", "configuration", "simulation_metrics", "timeline", "tests", "files", "export"],
                "metric_names": list(spec.metrics),
            },
        },
        {
            **base,
            "id": _component_id(project_id, "deployment_workflow", spec.project.name),
            "type": "deployment_workflow",
            "name": f"{spec.project.name} local handoff",
            "summary": "Local-first deployment workflow with venv setup, dependency installation, tests, simulation, and dashboard preview.",
            "tags": ["deployment", "local", spec.project.target_platform],
            "reusable_fields": {
                "workflow": ["create_venv", "install_requirements", "run_tests", "run_simulation", "preview_dashboard"],
                "hardware_flash_in_scope": False,
                "cloud_deploy_in_scope": False,
            },
        },
        {
            **base,
            "id": _component_id(project_id, "engineering_tradeoff", spec.project.name),
            "type": "engineering_tradeoff",
            "name": f"{spec.project.name} MVP safety tradeoffs",
            "summary": "Reusable tradeoff record: deterministic safety and simulation-first export are prioritized over real hardware flashing or autonomous cloud deployment.",
            "tags": ["tradeoff", "safety", "simulation-first", spec.project.target_platform],
            "reusable_fields": {
                "prioritized": ["deterministic_reflex", "offline_operation", "simulation_before_deployment", "human_review"],
                "deferred": ["hardware_flashing", "cloud_deployment", "safety_certification"],
                "rationale": "MVP exports validated starter projects while requiring independent engineering review before machinery control.",
            },
        },
    ]
    return components


def learn_from_project(
    spec: SystemSpec,
    project_id: str,
    manifest: Dict[str, Any],
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist reusable engineering components from a validated project."""
    graph = _load_graph()
    components = extract_components(spec, project_id, manifest, metrics)
    existing_ids = {c.get("id") for c in graph["components"]}
    for component in components:
        if component["id"] not in existing_ids:
            graph["components"].append(component)

    project_record = {
        "project_id": project_id,
        "project_name": spec.project.name,
        "learned_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": _spec_fingerprint(spec),
        "component_ids": [c["id"] for c in components],
    }
    graph["projects"] = [p for p in graph["projects"] if p.get("project_id") != project_id]
    graph["projects"].append(project_record)
    _save_graph(graph)
    return {"component_count": len(components), "component_ids": project_record["component_ids"]}


def search_similar(spec: SystemSpec, limit: int = 5) -> List[Dict[str, Any]]:
    """Find reusable components from prior validated projects similar to ``spec``."""
    graph = _load_graph()
    wanted = _spec_fingerprint(spec)
    wanted_sensors = set(wanted["sensor_types"])
    wanted_actions = set(wanted["actions"])
    scored: List[Dict[str, Any]] = []

    for component in graph.get("components", []):
        score = 0
        reasons: List[str] = []
        if component.get("domain") == spec.project.domain:
            score += 3
            reasons.append("same domain")
        if component.get("target_platform") == spec.project.target_platform:
            score += 1
            reasons.append("same target platform")
        tags = set(component.get("tags", []))
        shared_sensors = sorted(wanted_sensors & tags)
        shared_actions = sorted(wanted_actions & tags)
        if shared_sensors:
            score += 2 * len(shared_sensors)
            reasons.append("shared sensors: " + ", ".join(shared_sensors))
        if shared_actions:
            score += len(shared_actions)
            reasons.append("shared actions: " + ", ".join(shared_actions))
        if component.get("type") in {"architecture", "safety_policy", "simulation_model", "validation_strategy", "dashboard_layout", "deployment_workflow", "engineering_tradeoff"}:
            score += 1
        if score <= 0:
            continue
        scored.append(
            {
                "component_id": component.get("id"),
                "component_type": component.get("type"),
                "name": component.get("name"),
                "summary": component.get("summary"),
                "source_project_id": component.get("project_id"),
                "source_project_name": component.get("project_name"),
                "score": score,
                "reasons": reasons,
                "reusable_fields": component.get("reusable_fields", {}),
            }
        )

    scored.sort(key=lambda item: (-item["score"], item["component_type"] or "", item["name"] or ""))
    return scored[:limit]


def record_feedback(feedback: FeedbackRecord, spec: SystemSpec) -> Dict[str, Any]:
    """Store user feedback as graph knowledge after a validated project.

    Feedback is deliberately structured as reusable engineering experience: it
    records quality scores, reuse intent, notes, and improvement suggestions.
    That feedback becomes both an auditable feedback record and a searchable
    `user_feedback` graph component for future projects.
    """
    graph = _load_graph()
    payload = feedback.model_dump()
    graph["feedback"].append(payload)

    component = {
        "id": _component_id(feedback.project_id, "user_feedback", feedback.submitted_at),
        "type": "user_feedback",
        "name": f"{feedback.project_name} user feedback",
        "project_id": feedback.project_id,
        "project_name": feedback.project_name,
        "domain": spec.project.domain,
        "target_platform": spec.project.target_platform,
        "validated_at": feedback.submitted_at,
        "summary": (
            f"User feedback scores usefulness={feedback.usefulness_score}/5, "
            f"accuracy={feedback.accuracy_score}/5, safety={feedback.safety_score}/5, "
            f"would_reuse={feedback.would_reuse}."
        ),
        "tags": [
            "feedback",
            "user_feedback",
            spec.project.domain,
            spec.project.target_platform,
            *(s.type for s in spec.sensors),
        ],
        "reusable_fields": {
            "usefulness_score": feedback.usefulness_score,
            "accuracy_score": feedback.accuracy_score,
            "safety_score": feedback.safety_score,
            "would_reuse": feedback.would_reuse,
            "notes": feedback.notes,
            "improvement_suggestions": feedback.improvement_suggestions,
        },
    }
    graph["components"].append(component)
    _save_graph(graph)
    return {
        "feedback_count": len(graph["feedback"]),
        "component_id": component["id"],
        "component_count": len(graph["components"]),
    }


def graph_stats() -> Dict[str, Any]:
    graph = _load_graph()
    return {
        "version": graph.get("version", GRAPH_VERSION),
        "project_count": len(graph.get("projects", [])),
        "component_count": len(graph.get("components", [])),
        "feedback_count": len(graph.get("feedback", [])),
        "component_types": sorted({c.get("type") for c in graph.get("components", []) if c.get("type")}),
    }
