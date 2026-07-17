"""Deterministic engineering-team orchestration for Black Dragon Studio.

The long-term product vision describes Black Dragon Studio as an autonomous
engineering team rather than a single coding assistant.  The MVP keeps that
promise in a controlled, auditable way: each role reviews the approved
``SystemSpec`` and produces a structured handoff before template generation.
No role invents hidden state or unvalidated code; every finding is derived
from the same schema-validated specification that drives generation.
"""
from __future__ import annotations

from typing import Dict, List

from .models import EngineeringAgentResult, SystemSpec


AGENT_ORDER = [
    "Chief Architect",
    "Safety Engineer",
    "Embedded Engineer",
    "Simulation Engineer",
    "QA Engineer",
    "Documentation Engineer",
    "Deployment Engineer",
]


def _runtime_layers() -> List[str]:
    return [
        "Sensing",
        "Signal Normalization",
        "Reflex",
        "Prediction",
        "Policy",
        "Adaptation",
        "Actuation",
        "Dashboard/Logs",
    ]


def run_engineering_team(spec: SystemSpec) -> List[EngineeringAgentResult]:
    """Return role-by-role engineering handoffs for an approved spec."""
    sensor_summary = ", ".join(f"{s.id}:{s.type}" for s in spec.sensors)
    actions = sorted({a for actuator in spec.actuators for a in actuator.allowed_actions})
    critical_rules = [r for r in spec.reflex_rules if r.severity == "critical"]
    warning_rules = [r for r in spec.reflex_rules if r.severity == "warning"]

    results: List[EngineeringAgentResult] = [
        EngineeringAgentResult(
            role="Chief Architect",
            responsibility="Translate the approved specification into a coherent Physical AI architecture.",
            outputs=[
                f"Selected industrial_monitoring architecture for {spec.project.name}.",
                "Runtime layers: " + " -> ".join(_runtime_layers()) + ".",
                f"Bound {len(spec.sensors)} sensor(s), {len(spec.actuators)} actuator group(s), and {len(spec.reflex_rules)} reflex rule(s).",
            ],
            handoff_to="Safety Engineer",
        ),
        EngineeringAgentResult(
            role="Safety Engineer",
            responsibility="Ensure deterministic safety behavior is represented before generation.",
            outputs=[
                f"Verified {len(critical_rules)} critical rule(s) and {len(warning_rules)} warning rule(s).",
                "Critical actions remain rule-based and are not delegated to an LLM.",
                "Allowed actions: " + ", ".join(actions) + ".",
            ],
            handoff_to="Embedded Engineer",
        ),
        EngineeringAgentResult(
            role="Embedded Engineer",
            responsibility="Map the system to an edge-runtime configuration and offline constraints.",
            outputs=[
                f"Target platform: {spec.project.target_platform}.",
                f"Offline operation required: {spec.project.offline_required}.",
                "Sensor bindings: " + sensor_summary + ".",
            ],
            handoff_to="Simulation Engineer",
        ),
        EngineeringAgentResult(
            role="Simulation Engineer",
            responsibility="Create deterministic synthetic scenarios for validation before deployment.",
            outputs=[
                f"Simulation duration: {spec.simulation.duration_seconds} seconds.",
                "Scenarios: " + ", ".join(spec.simulation.scenarios) + ".",
                "Simulator must emit metrics.json and simulation_results.json.",
            ],
            handoff_to="QA Engineer",
        ),
        EngineeringAgentResult(
            role="QA Engineer",
            responsibility="Define the validation gates that must pass before export.",
            outputs=[
                "Run schema validation, static checks, unit tests, simulation smoke test, and package validation.",
                "Reject exports when generated tests or simulation fail.",
                "Check generated text files for common secret patterns.",
            ],
            handoff_to="Documentation Engineer",
        ),
        EngineeringAgentResult(
            role="Documentation Engineer",
            responsibility="Generate operator-facing documentation and honest limitations.",
            outputs=[
                "Include README, architecture diagram, system_spec.json, and generation_manifest.json.",
                "Label all generated sensor results as simulated, not measured.",
                "Record assumptions and unsupported hardware mappings.",
            ],
            handoff_to="Deployment Engineer",
        ),
        EngineeringAgentResult(
            role="Deployment Engineer",
            responsibility="Package the validated project for local deployment and handoff.",
            outputs=[
                "Prepare a self-contained ZIP export.",
                "Include local setup commands for venv, dependencies, tests, simulation, and dashboard preview.",
                "Keep real hardware flashing and autonomous cloud deployment out of MVP scope.",
            ],
            handoff_to=None,
        ),
    ]
    return results


def summarize_agent_results(results: List[EngineeringAgentResult]) -> List[Dict[str, object]]:
    """Serialize agent results for project state and generated artifacts."""
    return [r.model_dump() for r in results]
