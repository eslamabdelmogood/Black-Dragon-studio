# Black Dragon Studio — Product Constitution v1.0

## 1. Product Identity

**Product name:** Black Dragon Studio  
**Category:** Developer Tools / Physical AI Engineering Platform  
**Core promise:** Turn a natural-language description of a physical-AI system into a runnable, testable, and exportable starter project.

### One-sentence definition

Black Dragon Studio is an AI-assisted engineering platform that designs, generates, simulates, tests, and packages Physical AI applications from natural-language requirements.

### MVP tagline

> Describe the physical system. Generate the architecture. Run the simulation. Export the project.

---

## 2. The Problem

Building a Physical AI system normally requires engineers to manually combine:

- Sensor definitions
- Edge-processing logic
- Safety and reflex rules
- Predictive models
- Decision policies
- Simulations
- Dashboards
- Tests
- Deployment configuration
- Documentation

These parts are usually created with separate tools and connected manually. This makes prototyping slow, expensive, and error-prone.

Black Dragon Studio reduces this work by converting a user specification into a structured engineering project.

---

## 3. Target Users

The first version is intended for:

1. Embedded and IoT developers
2. Robotics and automation engineers
3. Industrial AI developers
4. Students and researchers building digital twins
5. Small teams that need a fast Physical AI prototype

The MVP is **not** intended to replace certified engineering tools or create safety-certified production systems automatically.

---

## 4. MVP Scope

The MVP must support one complete workflow:

> A user describes an industrial monitoring system, the Studio generates a structured project, runs a deterministic simulation, displays the results, and exports a ZIP package.

### Supported first use case

**Industrial machine monitoring**, such as:

- Pump vibration monitoring
- Motor temperature monitoring
- Bearing fault detection
- Pipeline pressure monitoring
- Structural panel monitoring

### Explicitly out of scope for v1

- Real hardware flashing
- Autonomous weapons
- Medical diagnosis or treatment
- Safety certification
- Arbitrary ROS project generation
- Direct control of real industrial machinery
- Fully autonomous cloud deployment
- Multiple simultaneous generated projects per user
- Fine-tuning models
- Marketplace or billing

---

## 5. Core User Journey

### Step 1 — Describe

The user enters a prompt such as:

> Build a monitoring system for an industrial water pump using vibration and temperature sensors. Reduce speed when vibration becomes dangerous and shut down when temperature exceeds the critical limit.

### Step 2 — Clarify

GPT-5.6 extracts requirements and asks only essential questions when information is missing, such as:

- Which sensors are available?
- What are the warning and critical thresholds?
- What actuator actions are allowed?
- What target device is expected?
- Should the generated system work offline?

The user may skip clarification and accept safe defaults.

### Step 3 — Design

The platform produces a visible project specification containing:

- System purpose
- Sensors
- Actuators
- Runtime layers
- Safety rules
- Simulation scenario
- Metrics
- Target platform
- Assumptions

The user approves this specification before code generation.

### Step 4 — Generate

Codex generates a project from approved templates and structured specifications.

### Step 5 — Validate

The platform runs:

- Schema validation
- Static checks
- Unit tests
- Simulation smoke test
- Safety-rule checks

### Step 6 — Preview

The user sees:

- Architecture diagram
- Sensor readings
- Risk state
- Triggered reflexes
- Actions
- Simulation timeline
- Test results

### Step 7 — Export

The user downloads a ZIP containing:

- Source code
- Configuration
- Simulation
- Tests
- Dashboard
- README
- Architecture diagram
- Generation manifest

---

## 6. Product Principles

### 6.1 Specification before generation

Codex must not generate the project directly from an unstructured prompt. GPT-5.6 must first produce a validated `SystemSpec`.

### 6.2 Templates before arbitrary code

The MVP must use controlled templates. Generated projects may customize templates, but Codex must not invent an unrestricted architecture every time.

### 6.3 Deterministic safety layer

Critical safety actions must be represented as deterministic rules, not delegated solely to an LLM.

### 6.4 Simulation before deployment

Every generated project must include a runnable simulation or mock sensor source.

### 6.5 Human approval

The user must approve the generated specification before the system creates files.

### 6.6 Honest claims

The platform must clearly label:

- Simulated results
- Estimated results
- Measured results
- Generated assumptions
- Untested hardware mappings

### 6.7 No secret leakage

API keys and credentials must never appear in generated files, logs, ZIP packages, screenshots, or prompts.

### 6.8 Reproducibility

Every project must include the exact structured specification, template version, generation time, and validation results.

---

## 7. Black Dragon Runtime Model

Generated projects follow a simplified layered architecture.

```text
Sensors / Simulated Inputs
          ↓
Signal Normalization
          ↓
Reflex Layer
          ↓
Prediction Layer
          ↓
Reasoning / Policy Layer
          ↓
Adaptation Layer
          ↓
Actuation
          ↓
Dashboard + Logs
```

### Layer A — Sensing

Defines sensor channels, units, sampling cadence, ranges, and simulated data.

### Layer B — Reflex

Executes deterministic low-latency safety rules.

Examples:

- Reduce speed when vibration remains above threshold for N samples.
- Shut down when temperature exceeds a hard safety limit.
- Ignore isolated noise spikes.

### Layer C — Prediction

Estimates short-horizon risk using a simple deterministic or lightweight statistical model in v1.

### Layer D — Reasoning

Selects an action from the allowed action set using policies and current state.

### Layer E — Adaptation

Changes priorities or thresholds based on operating mode, such as:

- Normal
- Safety-first
- Energy-saving
- Maintenance
- Degraded/offline

For the MVP, these layers may be simple, but they must be clearly separated.

---

## 8. Required Generated Project Structure

```text
generated-project/
├── README.md
├── LICENSE
├── pyproject.toml
├── system_spec.json
├── generation_manifest.json
├── architecture/
│   └── architecture.mmd
├── config/
│   ├── sensors.yaml
│   ├── actuators.yaml
│   ├── reflex_rules.yaml
│   └── runtime.yaml
├── src/
│   └── black_dragon_app/
│       ├── __init__.py
│       ├── main.py
│       ├── sensing.py
│       ├── reflex.py
│       ├── prediction.py
│       ├── policy.py
│       ├── adaptation.py
│       ├── actuation.py
│       └── logging.py
├── simulation/
│   ├── simulator.py
│   └── scenarios.json
├── dashboard/
│   └── index.html
├── tests/
│   ├── test_reflex.py
│   ├── test_policy.py
│   └── test_smoke.py
└── outputs/
    └── .gitkeep
```

---

## 9. System Specification Schema

GPT-5.6 must output a JSON object conforming to this logical structure:

```json
{
  "project": {
    "name": "pump-monitor",
    "description": "Industrial pump monitoring system",
    "domain": "industrial_monitoring",
    "target_platform": "generic_arm_edge",
    "offline_required": true
  },
  "sensors": [
    {
      "id": "vibration_1",
      "type": "vibration",
      "unit": "mm_s",
      "sample_rate_hz": 100,
      "normal_range": [0, 4],
      "warning_threshold": 7,
      "critical_threshold": 10
    }
  ],
  "actuators": [
    {
      "id": "pump_controller",
      "allowed_actions": [
        "do_nothing",
        "reduce_speed",
        "shutdown"
      ]
    }
  ],
  "reflex_rules": [
    {
      "id": "high_vibration",
      "condition": "vibration_1 >= 10 for 5 consecutive samples",
      "action": "shutdown",
      "severity": "critical"
    }
  ],
  "prediction": {
    "enabled": true,
    "method": "moving_trend",
    "horizon_seconds": 30
  },
  "operating_modes": [
    "normal",
    "safety_first",
    "degraded"
  ],
  "simulation": {
    "duration_seconds": 60,
    "scenarios": [
      "normal",
      "gradual_fault",
      "noise_spike",
      "critical_fault"
    ]
  },
  "metrics": [
    "detection_latency_ms",
    "false_alarms",
    "correct_action_rate",
    "final_damage_proxy"
  ],
  "assumptions": [],
  "warnings": []
}
```

The backend must validate this object with Pydantic before code generation.

---

## 10. Studio Architecture

```text
Browser UI
   ↓
FastAPI Backend
   ├── Project API
   ├── Generation API
   ├── Validation API
   └── Export API
   ↓
GPT-5.6 Specification Agent
   ↓
Validated SystemSpec
   ↓
Codex Generation Session
   ↓
Template Engine
   ↓
Sandboxed Workspace
   ↓
Tests + Simulation
   ↓
Preview + ZIP Export
```

---

## 11. Technology Stack

### Frontend

- Next.js
- TypeScript
- Simple responsive UI
- Mermaid for architecture diagrams
- No complex design system required for MVP

### Backend

- Python 3.11+
- FastAPI
- Pydantic
- Jinja2 templates
- Pytest
- Subprocess execution inside an isolated working directory

### AI

- GPT-5.6 for:
  - Requirement extraction
  - Clarifying questions
  - System specification
  - Explanations
  - Review of validation failures

- Codex for:
  - Project file generation
  - Targeted code changes
  - Test repair
  - README generation
  - Refactoring generated output

### Storage

MVP may use local filesystem storage:

```text
workspace/projects/<project_id>/
```

No database is required for the first version.

---

## 12. Required Screens

### Screen 1 — Home

- Product name and one-line explanation
- Prompt box
- Three example prompts
- Create Project button

### Screen 2 — Specification Review

- Parsed system purpose
- Sensors
- Actuators
- Runtime layers
- Safety rules
- Assumptions
- Edit and Approve buttons

### Screen 3 — Generation Progress

Display real stages:

1. Parsing requirements
2. Validating specification
3. Generating project
4. Running tests
5. Running simulation
6. Packaging project

Do not display fake progress percentages.

### Screen 4 — Project Workspace

Tabs:

- Overview
- Architecture
- Configuration
- Simulation
- Tests
- Files
- Export

### Screen 5 — Simulation

Show:

- Time
- Sensor values
- Current state
- Risk level
- Triggered rule
- Selected action
- Event timeline

### Screen 6 — Export

- Download ZIP
- Copy setup command
- View generation manifest
- View warnings and limitations

---

## 13. API Contract

### `POST /api/specify`

Input:

```json
{
  "prompt": "Build a pump monitoring system..."
}
```

Output:

```json
{
  "project_id": "uuid",
  "status": "needs_approval",
  "spec": {},
  "questions": [],
  "warnings": []
}
```

### `POST /api/projects/{project_id}/approve`

Approves the current specification.

### `POST /api/projects/{project_id}/generate`

Starts project generation.

### `GET /api/projects/{project_id}/status`

Returns the actual current stage and logs.

### `POST /api/projects/{project_id}/simulate`

Runs the generated simulation.

### `GET /api/projects/{project_id}/results`

Returns metrics, timeline, and test results.

### `GET /api/projects/{project_id}/download`

Returns the generated ZIP.

---

## 14. Codex Operating Instructions

Codex must follow these rules:

1. Read this constitution before writing code.
2. Build the smallest complete vertical slice first.
3. Do not create features outside the MVP scope.
4. Keep generated projects template-based and reproducible.
5. Never store API keys in the repository.
6. Use typed interfaces and validation.
7. Write tests for every core module.
8. All shell commands must have clear error handling.
9. Never claim a command succeeded unless its exit code and output were checked.
10. Do not hide failed tests.
11. Generated safety rules must remain deterministic.
12. The LLM may explain or propose actions but may not bypass the safety policy.
13. Keep a `BUILD_LOG.md` documenting major implementation decisions.
14. At the end of each milestone:
    - Run tests
    - Run lint/type checks
    - Run one end-to-end example
    - Update README
15. Prefer working code over unnecessary abstraction.

---

## 15. Security Requirements

- Use environment variables for all API credentials.
- Include `.env.example`, never `.env`.
- Add generated workspaces to `.gitignore`.
- Sanitize project names and filenames.
- Prevent path traversal.
- Set execution timeouts.
- Restrict generated subprocess commands.
- Do not run arbitrary user-provided shell commands.
- Limit generated ZIP size.
- Escape all user text rendered in HTML.
- Keep generation and execution in separate directories.
- Clearly warn that generated code is not safety-certified.

---

## 16. Validation Pipeline

Every generated project must pass:

### Stage 1 — Schema validation

- Valid project name
- At least one sensor
- At least one allowed action
- Every action referenced by a rule exists
- Thresholds use compatible units

### Stage 2 — Static validation

- Python syntax
- Imports
- Configuration parsing
- No hardcoded secrets

### Stage 3 — Unit tests

- Reflex fires on sustained danger
- Reflex ignores a single noise spike
- Critical threshold triggers critical action
- Invalid action is rejected

### Stage 4 — Simulation smoke test

- Simulation completes
- Output log is produced
- At least one fault scenario triggers a response
- Metrics are calculated

### Stage 5 — Package validation

- README exists
- Setup command works
- Required directories exist
- ZIP opens correctly
- Manifest matches produced files

---

## 17. MVP Acceptance Criteria

The MVP is complete only when a judge can:

1. Open the app.
2. Enter a natural-language pump-monitoring request.
3. Review and approve the generated specification.
4. Generate a runnable project.
5. See all generated files.
6. Run the built-in simulation.
7. Observe a safety rule firing.
8. See passing tests.
9. Download the ZIP.
10. Run the exported project using documented commands.

### Required demonstration prompt

> Build a safety monitoring system for an industrial water pump. Monitor vibration and temperature. Ignore isolated noise spikes. Reduce speed when vibration stays above 7 mm/s for five samples. Shut down when vibration reaches 10 mm/s or temperature exceeds 105°C. It must continue operating without cloud access.

---

## 18. Build Milestones

### Milestone 1 — Skeleton

- Monorepo
- Next.js frontend
- FastAPI backend
- Health endpoint
- Basic prompt screen

### Milestone 2 — Specification Agent

- GPT-5.6 integration
- Pydantic `SystemSpec`
- Clarifying-question flow
- Specification review screen

### Milestone 3 — Template Generator

- One industrial-monitoring template
- Configuration generation
- Source-code generation
- README generation

### Milestone 4 — Validation

- Pytest generation
- Static checks
- Test runner
- Real progress/log display

### Milestone 5 — Simulation

- Deterministic pump simulator
- Event timeline
- Metrics
- Dashboard preview

### Milestone 6 — Codex Integration

- Codex generates or edits project files
- Session instructions
- Error-repair loop
- Codex session ID documentation

### Milestone 7 — Export and Polish

- ZIP export
- Architecture diagram
- Complete README
- Example project
- Demo-ready UI
- Three-minute video script

---

## 19. OpenAI Build Week Positioning

### Track

**Developer Tools**

### Submission description

Black Dragon Studio is a developer tool that uses GPT-5.6 and Codex to transform natural-language Physical AI requirements into a validated architecture, deterministic reflex policies, a runnable simulation, tests, documentation, and an exportable starter repository.

### How GPT-5.6 is essential

GPT-5.6 converts ambiguous natural-language requirements into a structured and reviewable engineering specification and explains assumptions and validation failures.

### How Codex is essential

Codex creates and repairs the actual runnable project, tests, configuration, simulation, dashboard, and documentation from the approved specification.

### What judges should see

- A non-trivial working product
- A coherent end-to-end experience
- Real code generated by Codex
- A visible validation pipeline
- A runnable output project
- A clear explanation of where GPT-5.6 and Codex accelerated development

---

## 20. Final Definition of Done

Black Dragon Studio v1 is done when it can reliably generate **one high-quality industrial monitoring project** from natural language, validate it, simulate it, display its behavior, and export it as a runnable repository.

The MVP must not claim to generate every robot, drone, vehicle, or industrial system.

Its promise is smaller and credible:

> Generate a safe, structured, and runnable Physical AI monitoring prototype from a natural-language specification.
