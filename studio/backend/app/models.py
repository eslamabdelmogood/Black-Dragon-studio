"""
Pydantic data models for Black Dragon Studio.

The central artifact of the whole pipeline is `SystemSpec`: a validated,
structured description of a Physical AI monitoring system. Nothing is
generated from a raw prompt directly -- the prompt is always converted to a
`SystemSpec` first (see spec_agent.py), the user approves it, and only the
approved spec is ever handed to the generator.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

# --------------------------------------------------------------------------
# Enums / controlled vocabularies
# --------------------------------------------------------------------------

ALLOWED_SENSOR_TYPES = {
    "vibration",
    "temperature",
    "pressure",
    "strain",
    "current",
    "flow",
    "level",
    "generic",
}

ALLOWED_ACTIONS = {
    "do_nothing",
    "reduce_speed",
    "shutdown",
    "isolate_zone",
    "increase_cooling",
    "alert_operator",
    "switch_to_backup",
}

ALLOWED_TARGET_PLATFORMS = {
    "generic_arm_edge",
    "raspberry_pi",
    "x86_edge_gateway",
    "cloud_simulation_only",
}

ALLOWED_OPERATING_MODES = {
    "normal",
    "safety_first",
    "energy_saving",
    "maintenance",
    "degraded",
}


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    NEEDS_APPROVAL = "needs_approval"
    APPROVED = "approved"
    GENERATING = "generating"
    GENERATED = "generated"
    VALIDATING = "validating"
    VALIDATED = "validated"
    VALIDATION_FAILED = "validation_failed"
    SIMULATED = "simulated"
    FAILED = "failed"


# --------------------------------------------------------------------------
# SystemSpec sub-models (section 9 of the constitution)
# --------------------------------------------------------------------------

class ProjectMeta(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=500)
    domain: str = Field(default="industrial_monitoring")
    target_platform: str = Field(default="generic_arm_edge")
    offline_required: bool = Field(default=True)

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        import re

        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", v.strip().lower())
        cleaned = re.sub(r"-+", "-", cleaned).strip("-")
        if not cleaned:
            raise ValueError("project name must contain at least one alphanumeric character")
        return cleaned[:64]

    @field_validator("target_platform")
    @classmethod
    def check_platform(cls, v: str) -> str:
        if v not in ALLOWED_TARGET_PLATFORMS:
            raise ValueError(
                f"target_platform '{v}' not in {sorted(ALLOWED_TARGET_PLATFORMS)}"
            )
        return v


class SensorSpec(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    type: str
    unit: str
    sample_rate_hz: float = Field(gt=0, le=100_000)
    normal_range: List[float] = Field(..., min_length=2, max_length=2)
    warning_threshold: float
    critical_threshold: float

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in ALLOWED_SENSOR_TYPES:
            raise ValueError(f"sensor type '{v}' not in {sorted(ALLOWED_SENSOR_TYPES)}")
        return v

    @model_validator(mode="after")
    def check_thresholds(self) -> "SensorSpec":
        lo, hi = self.normal_range
        if lo > hi:
            raise ValueError(f"sensor {self.id}: normal_range must be [low, high]")
        if not (self.warning_threshold < self.critical_threshold or self.warning_threshold > self.critical_threshold):
            # equal thresholds are technically fine (immediate critical), only
            # forbid the case where they are on the "wrong side" of each other
            pass
        # direction-agnostic check: critical must be further from the normal
        # band than warning, in the same direction
        band_mid = (lo + hi) / 2.0
        if self.critical_threshold >= band_mid and self.warning_threshold >= band_mid:
            if self.critical_threshold < self.warning_threshold:
                raise ValueError(
                    f"sensor {self.id}: critical_threshold must be >= warning_threshold "
                    "for an upper-bound sensor"
                )
        if self.critical_threshold <= band_mid and self.warning_threshold <= band_mid:
            if self.critical_threshold > self.warning_threshold:
                raise ValueError(
                    f"sensor {self.id}: critical_threshold must be <= warning_threshold "
                    "for a lower-bound sensor"
                )
        return self


class ActuatorSpec(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    allowed_actions: List[str] = Field(..., min_length=1)

    @field_validator("allowed_actions")
    @classmethod
    def check_actions(cls, v: List[str]) -> List[str]:
        bad = [a for a in v if a not in ALLOWED_ACTIONS]
        if bad:
            raise ValueError(f"unknown actuator actions {bad}, allowed: {sorted(ALLOWED_ACTIONS)}")
        if "do_nothing" not in v:
            v = ["do_nothing", *v]
        return v


class ReflexRule(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    sensor_id: str
    comparator: str = Field(default=">=")
    threshold: float
    consecutive_samples: int = Field(default=1, ge=1, le=1000)
    action: str
    severity: str = Field(default="warning")
    ignore_isolated_spikes: bool = Field(default=True)

    @field_validator("comparator")
    @classmethod
    def check_comparator(cls, v: str) -> str:
        if v not in {">=", "<=", ">", "<", "=="}:
            raise ValueError(f"invalid comparator '{v}'")
        return v

    @field_validator("severity")
    @classmethod
    def check_severity(cls, v: str) -> str:
        if v not in {"warning", "critical"}:
            raise ValueError("severity must be 'warning' or 'critical'")
        return v


class PredictionSpec(BaseModel):
    enabled: bool = Field(default=True)
    method: str = Field(default="moving_trend")
    horizon_seconds: float = Field(default=30, gt=0, le=3600)


class SimulationSpec(BaseModel):
    duration_seconds: float = Field(default=60, gt=0, le=3600)
    scenarios: List[str] = Field(
        default_factory=lambda: ["normal", "gradual_fault", "noise_spike", "critical_fault"]
    )


class SystemSpec(BaseModel):
    project: ProjectMeta
    sensors: List[SensorSpec] = Field(..., min_length=1)
    actuators: List[ActuatorSpec] = Field(..., min_length=1)
    reflex_rules: List[ReflexRule] = Field(default_factory=list)
    prediction: PredictionSpec = Field(default_factory=PredictionSpec)
    operating_modes: List[str] = Field(default_factory=lambda: ["normal", "safety_first", "degraded"])
    simulation: SimulationSpec = Field(default_factory=SimulationSpec)
    metrics: List[str] = Field(
        default_factory=lambda: [
            "detection_latency_ms",
            "false_alarms",
            "correct_action_rate",
            "final_damage_proxy",
        ]
    )
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    @field_validator("operating_modes")
    @classmethod
    def check_modes(cls, v: List[str]) -> List[str]:
        bad = [m for m in v if m not in ALLOWED_OPERATING_MODES]
        if bad:
            raise ValueError(f"unknown operating_modes {bad}, allowed: {sorted(ALLOWED_OPERATING_MODES)}")
        return v

    @model_validator(mode="after")
    def cross_check_references(self) -> "SystemSpec":
        sensor_ids = {s.id for s in self.sensors}
        all_actions: set[str] = set()
        for act in self.actuators:
            all_actions.update(act.allowed_actions)

        for rule in self.reflex_rules:
            if rule.sensor_id not in sensor_ids:
                raise ValueError(
                    f"reflex rule '{rule.id}' references unknown sensor_id '{rule.sensor_id}'"
                )
            if rule.action not in all_actions:
                raise ValueError(
                    f"reflex rule '{rule.id}' references action '{rule.action}' "
                    f"that is not declared allowed for any actuator"
                )
        return self


# --------------------------------------------------------------------------
# Project envelope (studio-side bookkeeping, not part of the generated repo)
# --------------------------------------------------------------------------

class ClarifyingQuestion(BaseModel):
    field: str
    question: str
    default_used: Optional[str] = None


class SpecifyRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=4000)


class SpecifyResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    spec: SystemSpec
    questions: List[ClarifyingQuestion] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ValidationStageResult(BaseModel):
    stage: str
    passed: bool
    details: List[str] = Field(default_factory=list)


class EngineeringAgentResult(BaseModel):
    role: str
    responsibility: str
    outputs: List[str] = Field(default_factory=list)
    handoff_to: Optional[str] = None


class GenerationManifest(BaseModel):
    project_id: str
    project_name: str
    template: str = "industrial_monitoring"
    template_version: str = "1.0.0"
    studio_version: str = "0.1.0"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    spec_hash: str
    files: List[str] = Field(default_factory=list)
    validation: List[ValidationStageResult] = Field(default_factory=list)
    spec_source: str = "heuristic"  # "heuristic" or "llm"
    engineering_agents: List[EngineeringAgentResult] = Field(default_factory=list)
    knowledge_context: List[dict] = Field(default_factory=list)


def new_project_id() -> str:
    return uuid4().hex[:12]
