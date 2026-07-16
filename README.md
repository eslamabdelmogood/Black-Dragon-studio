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
6. Generate a second similar project to see the **Engineering Knowledge Graph** reuse validated architecture, safety, simulation, validation, dashboard, deployment, metrics, and trade-off components from the first project.

No API key is required — the default heuristic Specification Agent handles
the whole industrial-monitoring domain deterministically. Set
`OPENAI_API_KEY` in `studio/backend/.env` to route specification extraction
through an LLM instead (with automatic fallback to the heuristic agent if
the call fails or its output doesn't validate).


## OpenAI Build Week / Devpost readiness

Black Dragon Studio is prepared for the **Developer Tools** track: it is a tool
for developers and Physical AI engineers that generates runnable repositories,
validates them, exports them, and learns reusable engineering patterns from each
validated project.

For judges and reviewers:

```bash
# fastest full-lifecycle smoke test, including Knowledge Graph reuse
python scripts/judge_smoke.py

# hard-mode judge simulation: multiple prompts, ZIP extraction, generated tests/simulators
python scripts/hard_mode_test.py

# containerized demo
docker compose up --build
# open http://localhost:8000
```

See [`DEVPOST_SUBMISSION.md`](DEVPOST_SUBMISSION.md) for the project pitch,
track rationale, GPT-5.6/Codex usage notes, supported platforms, demo video
script, judge test plan, and submission checklist. Use `scripts/hard_mode_test.py`


## How GPT-5.6 and Codex are used

- **Codex** accelerated the implementation of the backend API, structured
  `SystemSpec`, generator, templates, validation pipeline, simulation/export
  flow, tests, frontend workspace, deterministic engineering-team review, and
  Engineering Knowledge Graph.
- **GPT-5.6** is supported in the product through the Specification Agent: set
  `OPENAI_API_KEY` and optionally `SPEC_AGENT_MODEL=gpt-5.6` to route natural
  language requirement extraction through an OpenAI chat-completions call. The
  returned JSON is still validated against `SystemSpec` before generation.
- **Deterministic fallback** is always available so judges can run the complete
  project without API keys or network access.

## Competition demo script

Use the prompt in `sample_prompts/industrial_pump.txt`, approve the generated
specification, run generation, inspect simulation results, show the generated
files, download the ZIP, then create a second similar project to demonstrate
Engineering Knowledge Graph reuse. Keep the video under three minutes and show
where Codex and GPT-5.6 fit into the workflow.

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
│   │   └── tests/          # 24 tests covering spec agent, models, pipeline, API
│   └── frontend/           # vanilla HTML/CSS/JS single-page app (6 screens)
└── reference-runtime/       # merged nomad-sentinel / Black-Dragon-Runtime project
```

## Honest status

This is a working MVP of the full pipeline for **one domain** (industrial
equipment monitoring: pumps, motors, bearings, pipelines) with **one
template**. It is not the full multi-template, multi-agent Codex
orchestration described in the constitution's long-term vision — see
`BUILD_LOG.md` for the specific scope decisions and what a v2 would add.
