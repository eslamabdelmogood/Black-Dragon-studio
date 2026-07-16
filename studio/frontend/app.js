const API = "";

const EXAMPLES = {
  1: "Build a monitoring system for an industrial water pump using vibration and temperature sensors. Ignore isolated noise spikes. Reduce speed when vibration stays above 7 mm/s for five samples. Shut down when vibration reaches 10 mm/s or temperature exceeds 105 C. It must continue operating without cloud access.",
  2: "Build a motor overcurrent protection system. Monitor current draw. Alert the operator above 28 amps and shut down above 35 amps to prevent winding damage. Must run fully offline on an ARM edge device.",
  3: "Build a pipeline pressure monitoring system. Watch pressure and flow rate. If pressure exceeds 12 bar shut down the pump feeding the line. If flow rate drops below 5 l/min for five samples, alert the operator.",
};

const state = {
  projectId: null,
  spec: null,
  manifest: null,
  results: null,
};

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

function showScreen(id) {
  $$(".screen").forEach(s => s.classList.remove("active"));
  $("#" + id).classList.add("active");
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res;
}

// ---------------- Screen 1: Home ----------------

$$(".chip").forEach(btn => {
  btn.addEventListener("click", () => {
    $("#promptInput").value = EXAMPLES[btn.dataset.example];
  });
});

$("#createProjectBtn").addEventListener("click", async () => {
  const prompt = $("#promptInput").value.trim();
  $("#homeError").textContent = "";
  if (prompt.length < 10) {
    $("#homeError").textContent = "Please describe the system in a bit more detail.";
    return;
  }
  $("#createProjectBtn").disabled = true;
  try {
    const res = await api("/api/specify", { method: "POST", body: JSON.stringify({ prompt }) });
    const data = await res.json();
    state.projectId = data.project_id;
    state.spec = data.spec;
    renderSpecReview(data);
    showScreen("screen-spec");
  } catch (e) {
    $("#homeError").textContent = "Error: " + e.message;
  } finally {
    $("#createProjectBtn").disabled = false;
  }
});

// ---------------- Screen 2: Spec Review ----------------

function renderSpecReview(data) {
  const spec = data.spec;
  const el = $("#specSummary");
  const sensors = spec.sensors.map(s =>
    `<tr><td>${s.id}</td><td>${s.type}</td><td>${s.unit}</td><td>${s.warning_threshold}</td><td>${s.critical_threshold}</td></tr>`
  ).join("");
  const rules = spec.reflex_rules.map(r =>
    `<li><span class="badge ${r.severity}">${r.severity}</span> ${r.sensor_id} ${r.comparator} ${r.threshold} for ${r.consecutive_samples} sample(s) → <b>${r.action}</b></li>`
  ).join("");
  const assumptions = (spec.assumptions || []).map(a => `<li class="assumption">${a}</li>`).join("") || "<li class='muted'>None</li>";
  const questions = (data.questions || []).map(q => `<li>${q.question} <span class="muted">(default: ${q.default_used ?? "n/a"})</span></li>`).join("");

  el.innerHTML = `
    <div class="spec-block">
      <h3>Purpose</h3>
      <div class="kv"><div class="k">Project</div><div>${spec.project.name}</div></div>
      <div class="kv"><div class="k">Domain</div><div>${spec.project.domain}</div></div>
      <div class="kv"><div class="k">Target platform</div><div>${spec.project.target_platform}</div></div>
      <div class="kv"><div class="k">Offline required</div><div>${spec.project.offline_required}</div></div>
      <div class="kv"><div class="k">Description</div><div>${spec.project.description}</div></div>
    </div>
    <div class="spec-block">
      <h3>Sensors</h3>
      <table class="data-table"><thead><tr><th>id</th><th>type</th><th>unit</th><th>warning</th><th>critical</th></tr></thead><tbody>${sensors}</tbody></table>
    </div>
    <div class="spec-block">
      <h3>Actuators</h3>
      <p>${spec.actuators.map(a => `${a.id}: ${a.allowed_actions.join(", ")}`).join("; ")}</p>
    </div>
    <div class="spec-block">
      <h3>Safety rules (deterministic reflex layer)</h3>
      <ul class="plain">${rules}</ul>
    </div>
    <div class="spec-block">
      <h3>Runtime layers</h3>
      <p class="muted">Sensing → Reflex → Prediction (${spec.prediction.method}, ${spec.prediction.horizon_seconds}s horizon) → Policy → Adaptation (${spec.operating_modes.join(", ")}) → Actuation → Dashboard/Logs</p>
    </div>
    ${questions ? `<div class="spec-block"><h3>Clarifying questions (safe defaults applied)</h3><ul class="plain">${questions}</ul></div>` : ""}
    <div class="spec-block">
      <h3>Assumptions</h3>
      <ul class="plain">${assumptions}</ul>
    </div>
  `;
}

$("#backHomeBtn").addEventListener("click", () => {
  state.projectId = null;
  showScreen("screen-home");
});

$("#approveBtn").addEventListener("click", async () => {
  $("#approveBtn").disabled = true;
  try {
    await api(`/api/projects/${state.projectId}/approve`, { method: "POST" });
    showScreen("screen-progress");
    await runGeneration();
  } catch (e) {
    alert("Approve failed: " + e.message);
  } finally {
    $("#approveBtn").disabled = false;
  }
});

// ---------------- Screen 3: Generation Progress ----------------

const STAGE_LABELS = {
  parsing_requirements: "Parsing requirements",
  validating_specification: "Validating specification",
  generating_project: "Generating project",
  running_tests: "Running tests",
  running_simulation: "Running simulation",
  packaging_project: "Packaging project",
};

function renderStageList(activeStage) {
  const ul = $("#stageList");
  ul.innerHTML = Object.entries(STAGE_LABELS).map(([key, label]) => {
    const cls = key === activeStage ? "active" : "";
    return `<li data-stage="${key}" class="${cls}"><span class="dot"></span>${label}</li>`;
  }).join("");
}

function markStage(key, statusStr) {
  const li = document.querySelector(`#stageList li[data-stage="${key}"]`);
  if (!li) return;
  li.classList.remove("active");
  li.classList.add(statusStr === "failed" ? "failed" : "done");
}

async function runGeneration() {
  renderStageList("parsing_requirements");
  markStage("parsing_requirements", "done");
  markStage("validating_specification", "done");
  $("#progressError").textContent = "";

  const order = ["generating_project", "running_tests", "running_simulation", "packaging_project"];
  order.forEach((s, i) => { if (i === 0) document.querySelector(`li[data-stage="${s}"]`).classList.add("active"); });

  try {
    const res = await api(`/api/projects/${state.projectId}/generate`, { method: "POST" });
    const data = await res.json();
    state.manifest = data.manifest;

    (data.manifest.validation || []).forEach(v => {
      const map = {
        schema_validation: "validating_specification",
        static_validation: "generating_project",
        unit_tests: "running_tests",
        simulation_smoke_test: "running_simulation",
        package_validation: "packaging_project",
      };
      markStage(map[v.stage], v.passed ? "completed" : "failed");
    });

    if (data.status === "validated") {
      await loadWorkspace();
      showScreen("screen-workspace");
    } else {
      $("#progressError").textContent = `Generation stopped at status '${data.status}'. See details below.`;
      const failed = (data.manifest.validation || []).filter(v => !v.passed);
      $("#progressError").textContent += "\n" + failed.map(f => `${f.stage}: ${f.details.join(" | ")}`).join("\n");
    }
  } catch (e) {
    $("#progressError").textContent = "Generation failed: " + e.message;
  }
}

// ---------------- Screen 4: Workspace ----------------

$$(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach(t => t.classList.remove("active"));
    $$(".tab-content").forEach(c => c.classList.remove("active"));
    tab.classList.add("active");
    $("#tab-" + tab.dataset.tab).classList.add("active");
  });
});

async function loadWorkspace() {
  $("#workspaceTitle").textContent = `Project: ${state.spec.project.name}`;

  // Overview
  $("#tab-overview").innerHTML = `
    <div class="kv"><div class="k">Status</div><div>Validated</div></div>
    <div class="kv"><div class="k">Template</div><div>${state.manifest.template} v${state.manifest.template_version}</div></div>
    <div class="kv"><div class="k">Generated at</div><div>${state.manifest.generated_at}</div></div>
    <div class="kv"><div class="k">Files generated</div><div>${state.manifest.files.length}</div></div>
    <div class="kv"><div class="k">Spec source</div><div>${state.manifest.spec_source}</div></div>
    <p class="muted" style="margin-top:16px;">All simulation results are SIMULATED, not measured on real hardware. This project is not safety-certified.</p>
  `;

  // Architecture
  try {
    const r = await api(`/api/projects/${state.projectId}/files/architecture/architecture.mmd`);
    const d = await r.json();
    $("#architectureView").textContent = d.content;
  } catch (e) { $("#architectureView").textContent = "unavailable: " + e.message; }

  // Configuration
  const configFiles = ["config/sensors.yaml", "config/actuators.yaml", "config/reflex_rules.yaml", "config/runtime.yaml"];
  let configHtml = "";
  for (const f of configFiles) {
    try {
      const r = await api(`/api/projects/${state.projectId}/files/${f}`);
      const d = await r.json();
      configHtml += `<h3>${f}</h3><pre class="code">${escapeHtml(d.content)}</pre>`;
    } catch (e) {}
  }
  $("#tab-configuration").innerHTML = configHtml;

  // Tests
  const testsHtml = state.manifest.validation.map(v =>
    `<div class="spec-block"><h3>${v.stage} — <span class="badge ${v.passed ? "info" : "critical"}">${v.passed ? "passed" : "failed"}</span></h3><pre class="code">${escapeHtml(v.details.join("\n"))}</pre></div>`
  ).join("");
  $("#tab-tests").innerHTML = testsHtml;

  // Files tree
  const tree = $("#fileTree");
  tree.innerHTML = state.manifest.files.map(f => `<li data-path="${f}">${f}</li>`).join("");
  tree.querySelectorAll("li").forEach(li => {
    li.addEventListener("click", async () => {
      tree.querySelectorAll("li").forEach(x => x.classList.remove("active"));
      li.classList.add("active");
      try {
        const r = await api(`/api/projects/${state.projectId}/files/${li.dataset.path}`);
        const d = await r.json();
        $("#fileContent").textContent = d.content;
      } catch (e) {
        $("#fileContent").textContent = "(cannot preview this file: " + e.message + ")";
      }
    });
  });

  // Export tab
  $("#setupCmd").textContent =
`cd ${state.spec.project.name}
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python simulation/simulator.py`;
  $("#manifestView").textContent = JSON.stringify(state.manifest, null, 2);
  $("#warningsList").innerHTML = (state.spec.warnings || []).map(w => `<li>${w}</li>`).join("") || "<li class='muted'>None</li>";

  // Simulation tab
  await loadResults();
}

$("#downloadBtn").addEventListener("click", () => {
  window.location.href = `/api/projects/${state.projectId}/download`;
});

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------- Screen 5: Simulation ----------------

async function loadResults() {
  try {
    const r = await api(`/api/projects/${state.projectId}/results`);
    const d = await r.json();
    state.results = d;

    const select = $("#scenarioSelect");
    select.innerHTML = Object.keys(d.metrics).map(s => `<option value="${s}">${s}</option>`).join("");
    select.onchange = () => renderScenario(select.value);
    renderScenario(select.value);
  } catch (e) {
    $("#simMetrics").innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function renderScenario(name) {
  const m = state.results.metrics[name];
  const timeline = state.results.scenarios[name].timeline;

  $("#simMetrics").innerHTML = `
    <div class="kv"><div class="k">Reflex fires</div><div>${m.reflex_fire_count}</div></div>
    <div class="kv"><div class="k">Critical fires</div><div>${m.critical_fire_count}</div></div>
    <div class="kv"><div class="k">False alarms</div><div>${m.false_alarms}</div></div>
    <div class="kv"><div class="k">Final action</div><div>${m.final_action}</div></div>
    <div class="kv"><div class="k">Final mode</div><div>${m.final_mode}</div></div>
    <div class="kv"><div class="k">Correct action rate</div><div>${m.correct_action_rate}</div></div>
  `;

  const tbody = document.querySelector("#timelineTable tbody");
  tbody.innerHTML = timeline.filter((e, i) => e.fired_rule || i % 10 === 0).slice(0, 200).map(e =>
    `<tr><td>${e.step}</td><td>${e.fired_rule || "-"}</td><td><span class="badge ${e.severity}">${e.severity}</span></td><td>${e.mode}</td><td>${e.action}</td><td>${e.reason}</td></tr>`
  ).join("");
}

$("#rerunSimBtn").addEventListener("click", async () => {
  $("#rerunSimBtn").disabled = true;
  try {
    await api(`/api/projects/${state.projectId}/simulate`, { method: "POST" });
    await loadResults();
  } catch (e) {
    alert("Simulation failed: " + e.message);
  } finally {
    $("#rerunSimBtn").disabled = false;
  }
});
