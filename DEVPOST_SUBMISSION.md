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
The judge scripts auto-install backend requirements if `fastapi` is missing;
if network access is blocked, run `pip install -r studio/backend/requirements.txt`
first.

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
- Engineering Knowledge Graph learning from project 1, user feedback after validation, and reusing components in
  project 2.
- Hard-mode validation via `python scripts/hard_mode_test.py` to demonstrate
  generated ZIPs run independently after extraction.

## Repository and license

Use the root `LICENSE` file for repository licensing. If the repository is
private, share it with the judging addresses required by the challenge before the
submission deadline.

---

# Devpost Form Answers

## Inspiration

Today's AI coding tools are good at generating files, but Physical AI projects need much more than code. An industrial monitoring system requires requirements analysis, architecture, runtime logic, deterministic safety rules, simulation, tests, dashboard, documentation, and a deployment package. The inspiration for Black Dragon Studio was to turn Codex from a coding assistant into an AI engineering team that can produce a complete, validated engineering system from a natural-language idea.

## What it does

Black Dragon Studio transforms a plain-English Physical AI request into a complete industrial-monitoring starter project. A user describes a system such as an industrial pump monitor, reviews and approves a structured `SystemSpec`, then the Studio generates runtime code, sensor configuration, reflex safety rules, simulation scenarios, tests, dashboard, documentation, and a downloadable ZIP. The generated project is validated before export through schema checks, static checks, unit tests, simulation smoke tests, and package validation. After generation, users can submit feedback, and the platform stores reusable engineering knowledge in an Engineering Knowledge Graph so future projects can reuse proven architecture, safety, simulation, validation, dashboard, deployment, metric, and feedback patterns.

## How we built it

We built Black Dragon Studio as a FastAPI backend with a lightweight browser UI and a controlled Jinja2 template engine for the first domain: industrial monitoring systems. The backend converts prompts into a validated Pydantic `SystemSpec`, requires human approval, runs a deterministic engineering-team handoff, renders a project template, validates the result, runs simulations, packages a ZIP, and records reusable components in the Engineering Knowledge Graph. Codex accelerated the implementation of the backend API, generation templates, validation pipeline, tests, frontend workflow, Docker setup, judge scripts, and documentation. GPT-5.6 is supported through the Specification Agent path when `OPENAI_API_KEY` is configured, with deterministic fallback so judges can run the full demo without secrets or network access.

## Challenges we ran into

The biggest challenge was making the project feel like a real engineering platform instead of a thin code-generation demo. We had to keep the MVP honest: one domain, one reliable template, real tests, real simulation, and clear safety limitations. Another challenge was making the system judge-friendly in fresh environments, so we added smoke tests, hard-mode tests, Docker support, auto dependency bootstrapping for judge scripts, and generated artifacts that prove what happened. We also had to design the Knowledge Graph carefully so it stores reusable engineering components and feedback rather than blindly copying raw generated code.

## Accomplishments that we're proud of

We are proud that Black Dragon Studio now runs an end-to-end lifecycle: natural language → approved specification → engineering-team review → generated runtime/simulation/tests/dashboard/docs → validation → ZIP export → user feedback → Knowledge Graph update. The generated projects are runnable and include honest documentation, deterministic safety rules, simulation outputs, and deployment handoff instructions. We are especially proud of the Engineering Knowledge Graph and Feedback Loop, because they make every completed project improve the next one instead of treating each generation as an isolated task.

## What we learned

We learned that the hardest part of Physical AI generation is not writing individual code files; it is coordinating engineering decisions across requirements, safety, simulation, validation, and deployment. We also learned that a strong MVP should be narrow but real: a working industrial-monitoring generator is more valuable than a broad set of fake templates. Finally, we learned that judge experience matters: one-command tests, clear setup, generated evidence, and transparent limitations make a complex developer tool much easier to understand quickly.

## What's next for Black Dragon Studio

Next, Black Dragon Studio will expand beyond industrial monitoring into additional Physical AI domains such as robotics cells, drones, smart factories, infrastructure monitoring, and industrial IoT. We plan to add more templates, richer simulation engines, background generation progress, persistent multi-user storage, and deeper Knowledge Graph retrieval so new projects can automatically adapt proven patterns from similar systems. The long-term goal is for Black Dragon Studio to become an operating system for AI engineering: a platform that designs, validates, simulates, tests, documents, packages, learns, and improves with every generated project.
