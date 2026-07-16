import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models import (  # noqa: E402
    ActuatorSpec,
    PredictionSpec,
    ProjectMeta,
    ReflexRule,
    SensorSpec,
    SimulationSpec,
    SystemSpec,
)


def _minimal_spec(**overrides) -> dict:
    base = dict(
        project=ProjectMeta(name="Test Pump!", description="desc", offline_required=True),
        sensors=[SensorSpec(id="vib_1", type="vibration", unit="mm_s", sample_rate_hz=100,
                             normal_range=[0, 4], warning_threshold=7, critical_threshold=10)],
        actuators=[ActuatorSpec(id="pump_ctrl", allowed_actions=["shutdown", "reduce_speed"])],
        reflex_rules=[ReflexRule(id="vib_crit", sensor_id="vib_1", comparator=">=", threshold=10,
                                  consecutive_samples=1, action="shutdown", severity="critical")],
    )
    base.update(overrides)
    return base


def test_project_name_is_sanitized():
    meta = ProjectMeta(name="My Cool Pump!!", description="x")
    assert meta.name == "my-cool-pump"


def test_valid_spec_constructs():
    spec = SystemSpec(**_minimal_spec())
    assert spec.project.name == "test-pump"


def test_reflex_rule_bad_sensor_reference_rejected():
    bad = _minimal_spec()
    bad["reflex_rules"] = [ReflexRule(id="r", sensor_id="does_not_exist", comparator=">=",
                                       threshold=1, consecutive_samples=1, action="shutdown",
                                       severity="critical")]
    with pytest.raises(Exception):
        SystemSpec(**bad)


def test_reflex_rule_bad_action_reference_rejected():
    bad = _minimal_spec()
    bad["reflex_rules"] = [ReflexRule(id="r", sensor_id="vib_1", comparator=">=",
                                       threshold=1, consecutive_samples=1, action="switch_to_backup",
                                       severity="critical")]
    with pytest.raises(Exception):
        SystemSpec(**bad)


def test_actuator_always_includes_do_nothing():
    act = ActuatorSpec(id="a", allowed_actions=["shutdown"])
    assert "do_nothing" in act.allowed_actions


def test_bad_target_platform_rejected():
    with pytest.raises(Exception):
        ProjectMeta(name="x", description="y", target_platform="quantum_cloud")


def test_normal_range_ordering_enforced():
    with pytest.raises(Exception):
        SensorSpec(id="s", type="vibration", unit="mm_s", sample_rate_hz=10,
                   normal_range=[10, 0], warning_threshold=7, critical_threshold=10)
