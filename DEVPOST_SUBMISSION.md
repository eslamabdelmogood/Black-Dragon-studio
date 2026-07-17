# Black Dragon Studio — Devpost Submission Guide

## Track

**Developer Tools**

Black Dragon Studio is a developer tool for embedded, IoT, robotics, automation,
and Physical AI engineers. It turns natural-language requirements into a
validated starter repository with runtime code, sensor configuration,
deterministic safety rules, simulation, tests, dashboard, documentation, and a
ZIP export, then uses post-generation feedback to improve its Engineering
Knowledge Graph.

## One-sentence pitch

Black Dragon Studio transforms natural-language requirements into complete,
validated, deployment-ready Physical AI starter projects by simulating an
autonomous engineering team and learning from every generated project through an
Engineering Knowledge Graph.

## Why this belongs in Developer Tools

- It generates runnable repositories for developers, not consumer content.
- It includes testing, validation, simulation, packaging, and deployment handoff.
- It implements an agentic engineering workflow with deterministic role handoffs.
- It stores reusable engineering components in a graph so future projects do not
  start from zero.

## How GPT-5.6 and Codex were used

- **Codex** was used to build the FastAPI backend, Pydantic `SystemSpec`, Jinja2
  generation templates, validation pipeline, simulation/export workflow,
  frontend workspace, automated tests, Engineering Team handoffs, and Engineering
  Knowledge Graph.
- **GPT-5.6 path in-product:** when `OPENAI_API_KEY` is configured, the
  Specification Agent calls the OpenAI API using `SPEC_AGENT_MODEL` with default
  `gpt-5.6`, validates the JSON against `SystemSpec`, and falls back to the
  deterministic heuristic extractor if the model/API is unavailable.
- **Judge-friendly fallback:** the product works without API keys so judges can
  test the full lifecycle immediately.

## Judge quickstart

### Option A — local Python

```bash
cd studio/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# open http://localhost:8000
