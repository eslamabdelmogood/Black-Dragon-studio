import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.knowledge_graph import GRAPH_VERSION, _empty_graph  # noqa: E402
from app.models import FeedbackRecord, FeedbackRequest  # noqa: E402


def test_empty_graph_contains_feedback_collection():
    graph = _empty_graph()
    assert graph == {
        "version": GRAPH_VERSION,
        "projects": [],
        "components": [],
        "feedback": [],
    }


def test_feedback_models_match_feedback_loop_payload():
    request = FeedbackRequest(
        usefulness_score=5,
        accuracy_score=4,
        safety_score=5,
        would_reuse=True,
        notes="Useful generated safety and simulation artifacts.",
        improvement_suggestions=["Add cavitation scenarios"],
    )
    record = FeedbackRecord(
        project_id="abc123",
        project_name="industrial-pump-monitor",
        **request.model_dump(),
    )

    assert record.usefulness_score == 5
    assert record.accuracy_score == 4
    assert record.safety_score == 5
    assert record.would_reuse is True
    assert record.submitted_at
