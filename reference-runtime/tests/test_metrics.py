from nomad_sentinel.bhs.scenarios import SCENARIOS
from nomad_sentinel.bhs.simulate import run
from nomad_sentinel.bhs.metrics import row_from_log, damage_prevented_pct


def test_bhs_detects_faster_than_baseline_on_scenario_a():
    scenario = SCENARIOS["A"]
    bhs_log = run(scenario, "bhs", n_steps=400)
    baseline_log = run(scenario, "baseline", n_steps=400)
    assert bhs_log["detect_time"] is not None
    if baseline_log["detect_time"] is not None:
        assert bhs_log["detect_time"] <= baseline_log["detect_time"]


def test_damage_prevented_pct_bounds():
    assert damage_prevented_pct(0.0, 1.0) == 100.0
    assert damage_prevented_pct(1.0, 1.0) == 0.0
    assert damage_prevented_pct(0.5, 0.0) == 0.0


def test_row_from_log_has_expected_fields():
    scenario = SCENARIOS["A"]
    log = run(scenario, "bhs", n_steps=100)
    row = row_from_log("A", scenario.name, "bhs", log, unmitigated_damage_mean=1.0)
    assert row["scenario"] == "A"
    assert row["system"] == "bhs"
    assert "damage_prevented_pct" in row
