import numpy as np
from nomad_sentinel.bhs.physics import Panel, PanelConfig


def test_panel_step_runs_and_stays_finite():
    cfg = PanelConfig()
    panel = Panel(cfg, seed=1)
    panel.inject_thermal_fault(cy=8, cx=30, radius=3, magnitude=100.0)
    for _ in range(50):
        panel.step()
    assert np.isfinite(panel.T).all()
    assert np.isfinite(panel.stress).all()
    assert (panel.damage >= 0).all() and (panel.damage <= 1).all()


def test_damage_only_increases_or_stays_flat_without_repair():
    cfg = PanelConfig()
    panel = Panel(cfg, seed=1)
    panel.inject_load_fault(cy=20, cx=30, radius=2, multiplier=8.0)
    prev = panel.damage.copy()
    for _ in range(30):
        panel.step()
        assert (panel.damage >= prev - 1e-9).all()
        prev = panel.damage.copy()
