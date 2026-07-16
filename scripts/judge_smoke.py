"""One-command judge smoke test for Black Dragon Studio.

Runs the full lifecycle in-process with FastAPI TestClient:
1. specify -> approve -> generate -> validate -> package
2. verify downloadable ZIP and simulation metrics
3. generate a second similar project to prove Knowledge Graph reuse
"""
from __future__ import annotations


import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "studio" / "backend"
WORKSPACE = Path(os.environ.get("BDS_JUDGE_WORKSPACE", "/tmp/bds_judge_workspace"))
PROMPT = (ROOT / "sample_prompts" / "industrial_pump.txt").read_text(encoding="utf-8").strip()

os.environ["BDS_WORKSPACE_ROOT"] = str(WORKSPACE)
shutil.rmtree(WORKSPACE, ignore_errors=True)
sys.path.insert(0, str(BACKEND))


from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def generate_project() -> dict:
    specify = client.post("/api/specify", json={"prompt": PROMPT})
    specify.raise_for_status()
    project_id = specify.json()["project_id"]

    approve = client.post(f"/api/projects/{project_id}/approve")
    approve.raise_for_status()

    generated = client.post(f"/api/projects/{project_id}/generate")
    generated.raise_for_status()
    payload = generated.json()
    assert payload["status"] == "validated", payload

    results = client.get(f"/api/projects/{project_id}/results")
    results.raise_for_status()
    assert "critical_fault" in results.json()["metrics"]

    download = client.get(f"/api/projects/{project_id}/download")
    download.raise_for_status()
    assert len(download.content) > 1000
    return {"project_id": project_id, "manifest": payload["manifest"]}


def main() -> None:
    first = generate_project()
    stats = client.get("/api/knowledge-graph/stats")
    stats.raise_for_status()
    assert stats.json()["component_count"] >= 5

    second = generate_project()
    context = second["manifest"].get("knowledge_context", [])
    assert context, "expected the second project to reuse Engineering Knowledge Graph components"

    print("Black Dragon Studio judge smoke test passed")
    print(f"First project:  {first['project_id']}")
    print(f"Second project: {second['project_id']}")
    print(f"Knowledge components reused: {len(context)}")


if __name__ == "__main__":
    main()
