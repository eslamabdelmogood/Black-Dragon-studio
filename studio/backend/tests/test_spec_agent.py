import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.spec_agent import extract_spec, heuristic_extract  # noqa: E402
from app.models import SystemSpec  # noqa: E402

DEMO_PROMPT = (
    "Build a monitoring system for an industrial water pump using vibration and "
    "temperature sensors. Ignore isolated noise spikes. Reduce speed when vibration "
    "stays above 7 mm/s for five samples. Shut down when vibration reaches 10 mm/s "
    "or temperature exceeds 105 C. It must continue operating without cloud access."
)


def test_heuristic_extract_returns_valid_spec():
    spec, questions = heuristic_extract(DEMO_PROMPT)
    assert isinstance(spec, SystemSpec)
    sensor_types = {s.type for s in spec.sensors}
    assert "vibration" in sensor_types
    assert "temperature" in sensor_types


def test_heuristic_extract_picks_up_explicit_thresholds():
    spec, _ = heuristic_extract(DEMO_PROMPT)
    vib = next(s for s in spec.sensors if s.type == "vibration")
    assert vib.warning_threshold == 7.0
    assert vib.critical_threshold == 10.0
    temp = next(s for s in spec.sensors if s.type == "temperature")
    assert temp.critical_threshold == 105.0


def test_heuristic_extract_sets_offline_required():
    spec, _ = heuristic_extract(DEMO_PROMPT)
    assert spec.project.offline_required is True


def test_reflex_rules_reference_valid_sensors_and_actions():
    spec, _ = heuristic_extract(DEMO_PROMPT)
    sensor_ids = {s.id for s in spec.sensors}
    allowed = {a for act in spec.actuators for a in act.allowed_actions}
    for rule in spec.reflex_rules:
        assert rule.sensor_id in sensor_ids
        assert rule.action in allowed


def test_extract_spec_falls_back_to_heuristic_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec, questions, source = extract_spec(DEMO_PROMPT)
    assert source == "heuristic"
    assert isinstance(spec, SystemSpec)


def test_vague_prompt_still_produces_a_valid_spec():
    spec, questions = heuristic_extract("Monitor my machine and keep it safe.")
    assert isinstance(spec, SystemSpec)
    assert len(spec.sensors) >= 1
    assert len(spec.assumptions) >= 1
