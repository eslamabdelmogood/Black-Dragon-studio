# Black Dragon Studio

**An autonomous AI engineering team that turns a product idea into a production-ready Physical AI project.**

Building Physical AI systems today requires multiple engineering disciplines
working sequentially — requirements → architecture → code → simulation →
tests → deployment. Black Dragon Studio compresses that pipeline: describe
the system you need to monitor in plain English, review the structured
specification it produces, approve it, and get back a validated, tested,
simulated, documented, runnable project you can download as a ZIP.

This repository is the merge of two prior projects into one buildable
codebase, per `black_dragon_studio_constitution_v1.md`:

- **`studio/`** (new) — the Studio itself: the FastAPI backend implementing
  the specify → approve → generate → validate → simulate → export pipeline
  described in the constitution, a lightweight web frontend, and the
  `industrial_monitoring` project template Codex renders from.
- **`reference-runtime/`** (from `nomad-sentinel`, which itself absorbed
  `Black-Dragon-Runtime`) — the earlier, hand-built Physical AI runtime
  (Sensing → Reflex → Cognition → Actuation layers over a structural-panel
  digital twin) that the Studio's generated-project architecture is
  modeled on. Kept as a reference implementation and worked example, not
  modified.

See `BUILD_LOG.md` for what was actually built, what was reused, and what
was deliberately simplified for this pass.

## Quickstart

```bash
cd studio/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                   # 22 backend tests
uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

Then, in the browser:
1. **Describe** the system (e.g. "monitor pump vibration and temperature,
   shut down above 10 mm/s or 105°C").
2. **Review** the generated specification — sensors, thresholds, safety
   rules, assumptions — and approve it.
3. Watch the **6-stage generation pipeline** run for real (parse → validate
   → generate → test → simulate → package).
4. Explore the generated project in the **workspace**: architecture
   diagram, config, four simulated fault scenarios with a live timeline,
   test results, and every generated file.
5. **Download** the finished project as a self-contained ZIP.

No API key is required — the default heuristic Specification Agent handles
the whole industrial-monitoring domain deterministically. Set
`OPENAI_API_KEY` in `studio/backend/.env` to route specification extraction
through an LLM instead (with automatic fallback to the heuristic agent if
the call fails or its output doesn't validate).

## Repository layout

```
black-dragon-studio/
├── black_dragon_studio_constitution_v1.md   # the source spec for this build
├── BUILD_LOG.md                              # what was built, decisions & gaps
├── studio/
│   ├── backend/            # FastAPI service (spec agent, generator, validator, packager)
│   │   ├── app/
│   │   │   ├── main.py            # API routes
│   │   │   ├── models.py          # SystemSpec (Pydantic) schema
│   │   │   ├── spec_agent.py      # NL prompt -> SystemSpec
│   │   │   ├── generator.py       # Jinja2 template engine
│   │   │   ├── validator.py       # 5-stage validation pipeline
│   │   │   ├── packager.py        # ZIP export
│   │   │   ├── storage.py         # workspace/projects/<id>/ filesystem store
│   │   │   └── templates/industrial_monitoring/   # the one template, v1.0.0
│   │   └── tests/          # 22 tests covering spec agent, models, pipeline, API
│   └── frontend/           # vanilla HTML/CSS/JS single-page app (6 screens)
└── reference-runtime/       # merged nomad-sentinel / Black-Dragon-Runtime project
```

## Honest status

This is a working MVP of the full pipeline for **one domain** (industrial
equipment monitoring: pumps, motors, bearings, pipelines) with **one
template**. It is not the full multi-template, multi-agent Codex
orchestration described in the constitution's long-term vision — see
`BUILD_LOG.md` for the specific scope decisions and what a v2 would add.
