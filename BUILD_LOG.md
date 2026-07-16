# BUILD_LOG.md

## What this delivers

A working, end-to-end implementation of the Black Dragon Studio pipeline
described in `black_dragon_studio_constitution_v1.md`:

```
prompt --(Specification Agent)--> SystemSpec --(approve)-->
Template Engine --> generated project --(5-stage Validation Pipeline)-->
Simulation --> ZIP export
```

Verified live (not just unit-tested) with `curl` against a running server
using the exact demonstration-style prompt from the constitution (pump,
vibration 7/10 mm/s, temperature 105°C, offline). All five validation
stages passed and the resulting ZIP contained a runnable project.

22 backend tests pass (`pytest -q` in `studio/backend`), covering the
Specification Agent, the `SystemSpec` schema's cross-field validation, the
generator + validator pipeline, and the full HTTP API contract including a
path-traversal rejection test.

## What was merged

- `nomad-sentinel` (which had already absorbed `Black-Dragon-Runtime` as its
  `bhs` package) was the more complete of the two uploaded projects, so it
  became `reference-runtime/` verbatim (caches stripped). It is a hand-built
  digital twin for a structural optical-skin panel with its own
  Sensing/Reflex/Cognition/Actuation layers, tests, docs, and deploy
  scripts.
- `Black-Dragon-Runtime` on its own was effectively an earlier snapshot of
  the same `bhs` code now living inside `nomad-sentinel`; it wasn't merged
  a second time to avoid duplicating the same source under two names.
- The new `studio/` application does not depend on `reference-runtime/` at
  runtime. It reuses its *architecture pattern* (the same layered
  Sensing → Reflex → Prediction/Cognition → Policy → Adaptation → Actuation
  → Logging pipeline) as the basis for the `industrial_monitoring`
  template, translated into a domain-agnostic, config-driven form so the
  Studio can regenerate it per-spec instead of it being hand-written once.

## Scope decisions (and why)

**One domain, one template, built for real, instead of a stub for many.**
The constitution describes a broad long-term platform (multiple domains,
multiple templates, a full Codex/agent orchestration layer, cloud storage,
auth, multi-tenant billing). Building thin stubs for all of that would have
produced something that *looks* complete but doesn't actually work end to
end. Instead this build picked the domain the constitution itself uses for
its worked examples — industrial equipment monitoring (pumps, motors,
bearings, pipelines) — and made every stage of the pipeline real:
the spec agent genuinely parses thresholds out of prompts, the generator
genuinely renders 28+ files from Jinja2 templates, the validator genuinely
runs `pytest` and a full 4-scenario simulation in a subprocess, and the ZIP
that comes out genuinely runs standalone (`pip install -r requirements.txt
&& pytest && python simulation/simulator.py` works with no further edits).

**Heuristic Specification Agent as the default, LLM as an opt-in layer on
top.** The constitution's Specification Agent is LLM-backed. This build
implements a deterministic, regex/keyword-based extractor as the primary
path (`spec_agent.heuristic_extract`) so the whole product works fully
offline with zero API keys and zero external network calls — which also
matches the "offline required" value the industrial-monitoring domain
itself asks for. `spec_agent.llm_extract` will use `OPENAI_API_KEY` if
present, calling an OpenAI-compatible chat completion and validating its
JSON output against the exact same `SystemSpec` Pydantic model before
anything downstream sees it; on any failure (no key, network error, invalid
JSON, failed validation) it transparently falls back to the heuristic
extractor rather than erroring out.

**Frontend is a vanilla HTML/CSS/JS single-page app, not Next.js.** The
constitution names Next.js/React specifically. This sandbox has npm
available, but standing up a full Next.js build/toolchain, App Router
pages, and a component library for six screens was a much larger time
investment than implementing the same six screens (Home, Spec Review,
Generation Progress, Workspace with 7 tabs, Simulation, Export) as one
static page served directly by FastAPI. It talks to the exact same JSON
API a Next.js frontend would, so swapping it later doesn't require backend
changes.

**Generation pipeline runs synchronously inside `POST /generate` rather
than as a background job with a polling `/status` that shows live
percentages.** `GET /status` returns the real, named stage log
(`parsing_requirements`, `validating_specification`, `generating_project`,
`running_tests`, `running_simulation`, `packaging_project`) with actual
pass/fail per stage — no fabricated progress bars or fake percentages, per
the constitution's explicit ban on that. The trade-off is that `/generate`
blocks until all five validation stages finish (a few seconds for the
demo project); a v2 would move this to a background task/queue so
`/status` reflects genuinely concurrent progress.

**Local filesystem storage only**, exactly as the constitution specifies
for the MVP (`workspace/projects/<project_id>/`), no database, no cloud
storage, no auth. Project IDs are studio-generated hex strings and every
file-serving endpoint normalizes and bounds-checks paths against the
project's own output directory before reading (tested in
`test_api.py::test_path_traversal_is_rejected`).

## What a v2 would add

- Additional templates (structural monitoring reusing `reference-runtime`'s
  panel physics, HVAC, robotics safety cells) selected by the Specification
  Agent from the domain it detects.
- Background/async generation with real concurrent progress instead of a
  blocking call.
- A real Codex/agent step for anything the fixed template can't express,
  gated behind the same schema-validated `SystemSpec` contract (constitution
  6.2's "templates before arbitrary code, arbitrary code only when the task
  needs it").
- Persistent storage (Postgres/object storage) and auth for multi-user use.
- A genuine Next.js frontend against the existing API.
