# Black Dragon Studio — Devpost Submission Guide

## Track

**Developer Tools**

Black Dragon Studio is a developer tool for embedded, IoT, robotics, automation,
and Physical AI engineers. It turns natural-language requirements into a
validated starter repository with runtime code, sensor configuration,
deterministic safety rules, simulation, tests, dashboard, documentation, and a
ZIP export.

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
uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

### Option B — Docker

```bash
docker compose up --build
# open http://localhost:8000
```

### Option C — one-command smoke test

```bash
python scripts/judge_smoke.py
```

The smoke test runs specify → approve → generate → validate → results → download,
then creates a second similar project to prove Engineering Knowledge Graph reuse.

### Option D — hard-mode competition simulation

```bash
python scripts/hard_mode_test.py
```

The hard-mode script starts from a clean workspace with no OpenAI API key,
generates multiple industrial-monitoring projects from strong and vague prompts,
verifies approval gates and path traversal protection, downloads and extracts
every ZIP, then runs each generated project's own tests and simulator.

## Demo prompt

```text
Build an industrial pump monitoring system using vibration and temperature sensors.
Ignore isolated noise spikes. Reduce speed when vibration stays above 7 mm/s for
five samples. Shut down when vibration reaches 10 mm/s or temperature exceeds
105 C. It must continue operating without cloud access.
```

## Demo video script under 3 minutes

1. **Problem:** Physical AI projects require requirements, architecture, runtime,
   safety, simulation, tests, dashboard, docs, and deployment.
2. **Product:** Black Dragon Studio turns a prompt into a validated Physical AI
   starter project.
3. **Live flow:** paste the pump prompt, review the spec, approve it, run
   generation, view simulation metrics, inspect generated files, and download ZIP.
4. **Moat:** show `engineering_review.json`, `docs/engineering_plan.md`,
   `knowledge_context.json`, and `docs/knowledge_graph.md`.
5. **Codex/GPT-5.6:** explain that Codex built the pipeline and GPT-5.6 powers the
   optional specification extraction path with deterministic fallback.

## Supported platforms

- Local development: Linux, macOS, Windows with Python 3.11+
- Containerized demo: Docker / Docker Compose
- Browser: any modern browser against the FastAPI-served single-page app

## What judges should look for

- Full lifecycle from prompt to downloadable ZIP.
- Deterministic safety/reflex rules, not LLM-only safety behavior.
- Five validation stages before export.
- Generated simulation results and dashboard timeline.
- Engineering-team role handoffs.
- Engineering Knowledge Graph learning from project 1 and reusing components in
  project 2.
- Hard-mode validation via `python scripts/hard_mode_test.py` to demonstrate
  generated ZIPs run independently after extraction.

## Repository and license

Use the root `LICENSE` file for repository licensing. If the repository is
private, share it with the judging addresses required by the challenge before the
submission deadline.
