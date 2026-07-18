import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["BDS_WORKSPACE_ROOT"] = "/tmp/bds_api_tests_workspace"
shutil.rmtree(os.environ["BDS_WORKSPACE_ROOT"], ignore_errors=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

DEMO_PROMPT = (
    "Build a monitoring system for an industrial water pump using vibration and "
    "temperature sensors. Ignore isolated noise spikes. Reduce speed when vibration "
    "stays above 7 mm/s for five samples. Shut down when vibration reaches 10 mm/s "
    "or temperature exceeds 105 C. It must continue operating without cloud access."
)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_specify_returns_needs_approval():
    response = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "needs_approval"
    assert data["spec"]["sensors"]


def test_generate_requires_approval_first():
    response = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    assert response.status_code == 200

    project_id = response.json()["project_id"]
    generate_response = client.post(f"/api/projects/{project_id}/generate")

    assert generate_response.status_code == 409


def test_full_lifecycle_reaches_validated_and_downloadable():
    response = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    assert response.status_code == 200
    project_id = response.json()["project_id"]

    approve_response = client.post(f"/api/projects/{project_id}/approve")
    assert approve_response.status_code == 200

    generate_response = client.post(f"/api/projects/{project_id}/generate")
    assert generate_response.status_code == 200

    data = generate_response.json()
    assert data["status"] == "validated", data
    assert [agent["role"] for agent in data["manifest"]["engineering_agents"]] == [
        "Chief Architect",
        "Safety Engineer",
        "Embedded Engineer",
        "Simulation Engineer",
        "QA Engineer",
        "Documentation Engineer",
        "Deployment Engineer",
    ]

    results_response = client.get(f"/api/projects/{project_id}/results")
    assert results_response.status_code == 200
    metrics = results_response.json()["metrics"]
    assert "critical_fault" in metrics

    download_response = client.get(f"/api/projects/{project_id}/download")
    assert download_response.status_code == 200
    assert len(download_response.content) > 1000

    files_response = client.get(f"/api/projects/{project_id}/files")
    assert files_response.status_code == 200

    files = files_response.json()["files"]
    assert "README.md" in files
    assert "engineering_review.json" in files
    assert "knowledge_context.json" in files
    assert "docs/engineering_plan.md" in files
    assert "docs/knowledge_graph.md" in files
    assert "deploy/README.md" in files


def test_path_traversal_is_rejected():
    response = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    assert response.status_code == 200
    project_id = response.json()["project_id"]

    assert client.post(f"/api/projects/{project_id}/approve").status_code == 200
    assert client.post(f"/api/projects/{project_id}/generate").status_code == 200

    traversal_response = client.get(
        f"/api/projects/{project_id}/files/../../../../etc/passwd"
    )
    assert traversal_response.status_code in (400, 404)


def test_unknown_project_returns_404():
    response = client.get("/api/projects/deadbeef0000/status")
    assert response.status_code == 404


def test_knowledge_graph_learns_and_reuses_components():
    first_response = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    assert first_response.status_code == 200
    first_project_id = first_response.json()["project_id"]

    assert client.post(
        f"/api/projects/{first_project_id}/approve"
    ).status_code == 200

    first_generated = client.post(
        f"/api/projects/{first_project_id}/generate"
    )
    assert first_generated.status_code == 200
    assert first_generated.json()["status"] == "validated"

    stats_response = client.get("/api/knowledge-graph/stats")
    assert stats_response.status_code == 200
    assert stats_response.json()["component_count"] >= 5

    second_response = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    assert second_response.status_code == 200
    second_project_id = second_response.json()["project_id"]

    status_response = client.get(f"/api/projects/{second_project_id}/status")
    assert status_response.status_code == 200

    stage_log = status_response.json()["stage_log"]
    knowledge_entries = [
        entry for entry in stage_log
        if entry["stage"] == "knowledge_graph_search"
    ]
    assert knowledge_entries
    assert "0 reusable" not in knowledge_entries[-1]["detail"]

    assert client.post(
        f"/api/projects/{second_project_id}/approve"
    ).status_code == 200

    second_generated = client.post(
        f"/api/projects/{second_project_id}/generate"
    )
    assert second_generated.status_code == 200

    context = second_generated.json()["manifest"]["knowledge_context"]
    assert context
    assert {item["component_type"] for item in context}


def test_feedback_updates_knowledge_graph():
    response = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    assert response.status_code == 200
    project_id = response.json()["project_id"]

    assert client.post(
        f"/api/projects/{project_id}/approve"
    ).status_code == 200

    generated_response = client.post(
        f"/api/projects/{project_id}/generate"
    )
    assert generated_response.status_code == 200
    assert generated_response.json()["status"] == "validated"

    feedback_response = client.post(
        f"/api/projects/{project_id}/feedback",
        json={
            "usefulness_score": 5,
            "accuracy_score": 4,
            "safety_score": 5,
            "would_reuse": True,
            "notes": "The generated safety rules and simulation are useful.",
            "improvement_suggestions": [
                "Add more pump cavitation scenarios"
            ],
        },
    )
    assert feedback_response.status_code == 200, feedback_response.text

    payload = feedback_response.json()
    assert payload["knowledge_graph_update"]["component_id"]

    stats_response = client.get("/api/knowledge-graph/stats")
    assert stats_response.status_code == 200
    assert stats_response.json()["feedback_count"] >= 1

    status_response = client.get(f"/api/projects/{project_id}/status")
    assert status_response.status_code == 200

    stage_log = status_response.json()["stage_log"]
    assert any(entry["stage"] == "user_feedback" for entry in stage_log)
