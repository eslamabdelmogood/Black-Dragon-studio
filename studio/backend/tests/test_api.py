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
    r = client.get("/api/health")
    assert r.status_code == 200


def test_specify_returns_needs_approval():
    r = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "needs_approval"
    assert data["spec"]["sensors"]


def test_generate_requires_approval_first():
    r = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    pid = r.json()["project_id"]
    r2 = client.post(f"/api/projects/{pid}/generate")
    assert r2.status_code == 409


def test_full_lifecycle_reaches_validated_and_downloadable():
    r = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    pid = r.json()["project_id"]

    r = client.post(f"/api/projects/{pid}/approve")
    assert r.status_code == 200

    r = client.post(f"/api/projects/{pid}/generate")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "validated", data
    assert [a["role"] for a in data["manifest"]["engineering_agents"]] == [
        "Chief Architect",
        "Safety Engineer",
        "Embedded Engineer",
        "Simulation Engineer",
        "QA Engineer",
        "Documentation Engineer",
        "Deployment Engineer",
    ]

    r = client.get(f"/api/projects/{pid}/results")
    assert r.status_code == 200
    metrics = r.json()["metrics"]
    assert "critical_fault" in metrics

    r = client.get(f"/api/projects/{pid}/download")
    assert r.status_code == 200
    assert len(r.content) > 1000

    r = client.get(f"/api/projects/{pid}/files")
    assert r.status_code == 200
    files = r.json()["files"]
    assert "README.md" in files
    assert "engineering_review.json" in files
    assert "knowledge_context.json" in files
    assert "docs/engineering_plan.md" in files
    assert "docs/knowledge_graph.md" in files
    assert "deploy/README.md" in files


def test_path_traversal_is_rejected():
    r = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    pid = r.json()["project_id"]
    client.post(f"/api/projects/{pid}/approve")
    client.post(f"/api/projects/{pid}/generate")

    r = client.get(f"/api/projects/{pid}/files/../../../../etc/passwd")
    assert r.status_code in (400, 404)


def test_unknown_project_returns_404():
    r = client.get("/api/projects/deadbeef0000/status")
    assert r.status_code == 404


def test_knowledge_graph_learns_and_reuses_components():
    first = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    first_pid = first.json()["project_id"]
    client.post(f"/api/projects/{first_pid}/approve")
    generated = client.post(f"/api/projects/{first_pid}/generate")
    assert generated.status_code == 200
    assert generated.json()["status"] == "validated"

    stats = client.get("/api/knowledge-graph/stats")
    assert stats.status_code == 200
    assert stats.json()["component_count"] >= 5

    second = client.post("/api/specify", json={"prompt": DEMO_PROMPT})
    second_pid = second.json()["project_id"]
    status = client.get(f"/api/projects/{second_pid}/status").json()
    knowledge_entries = [e for e in status["stage_log"] if e["stage"] == "knowledge_graph_search"]
    assert knowledge_entries
    assert "0 reusable" not in knowledge_entries[-1]["detail"]

    client.post(f"/api/projects/{second_pid}/approve")
    second_generated = client.post(f"/api/projects/{second_pid}/generate")
    assert second_generated.status_code == 200
    context = second_generated.json()["manifest"]["knowledge_context"]
    assert context
    assert {item["component_type"] for item in context}

