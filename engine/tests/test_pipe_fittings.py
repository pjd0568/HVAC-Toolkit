"""Tests for hvac_engine.pipe_fittings — Stage 2 system pressure-drop helpers."""

from __future__ import annotations

import pytest

from hvac_engine import pipe as eng
from hvac_engine import pipe_fittings as pf


def test_catalogue_nonempty_and_keys_unique():
    assert len(pf.FITTINGS) >= 10
    keys = [f.key for f in pf.FITTINGS]
    assert len(keys) == len(set(keys))
    for f in pf.FITTINGS:
        assert f.k >= 0
        assert f.category in pf.CATEGORY_LABELS


def test_fittings_by_category_filters():
    elbows = pf.fittings_by_category(pf.CAT_ELBOW)
    assert elbows
    assert all(f.category == pf.CAT_ELBOW for f in elbows)
    assert len(pf.fittings_by_category(None)) == len(pf.FITTINGS)
    with pytest.raises(ValueError, match="unknown fitting category"):
        pf.fittings_by_category("not_a_category")


def test_fitting_pressure_drop_k_times_pv():
    pv = 100.0
    assert pf.fitting_pressure_drop(0.9, pv) == pytest.approx(90.0)
    assert pf.fitting_pressure_drop(0.0, pv) == 0.0
    with pytest.raises(ValueError):
        pf.fitting_pressure_drop(-0.1, pv)
    with pytest.raises(ValueError):
        pf.fitting_pressure_drop(1.0, -1.0)


def test_straight_pressure_drop_length_times_friction():
    assert pf.straight_pressure_drop(10.0, 250.0) == pytest.approx(2500.0)
    with pytest.raises(ValueError, match="length"):
        pf.straight_pressure_drop(0.0, 250.0)
    with pytest.raises(ValueError, match="length"):
        pf.straight_pressure_drop(-1.0, 250.0)
    with pytest.raises(ValueError, match="friction"):
        pf.straight_pressure_drop(1.0, -1.0)


def test_device_pressure_drop_identity():
    assert pf.device_pressure_drop(25.0) == 25.0
    assert pf.device_pressure_drop(0.0) == 0.0
    with pytest.raises(ValueError):
        pf.device_pressure_drop(-5.0)


def test_velocity_pressure_at_fluid_density():
    # V = 1 m/s, ρ = 1000 kg/m³ → Pv = 500 Pa
    assert eng.velocity_pressure(1.0, 1000.0) == pytest.approx(500.0)
    with pytest.raises(ValueError):
        eng.velocity_pressure(-0.1, 1000.0)
    with pytest.raises(ValueError):
        eng.velocity_pressure(1.0, 0.0)


def test_straight_row_matches_evaluate_size():
    """10 m of DN25 carbon steel @ 1 l/s water 20 °C — Δp = L × Δp/L."""
    props = eng.fluid_properties("water", 20.0)
    flow_m3h = eng.volume_flow_m3h_from_ls(1.0)
    entry = next(e for e in eng.catalogue_for("carbon_steel") if e.dn == 25)
    sized = eng.evaluate_size(flow_m3h, entry, props, "carbon_steel", "lthw")
    dp = pf.straight_pressure_drop(10.0, sized.friction_rate_pa_per_m)
    assert dp == pytest.approx(10.0 * sized.friction_rate_pa_per_m)
    assert sized.friction_rate_pa_per_m > 0


def test_fitting_row_matches_k_times_pv():
    props = eng.fluid_properties("water", 20.0)
    flow_m3h = eng.volume_flow_m3h_from_ls(1.0)
    entry = next(e for e in eng.catalogue_for("carbon_steel") if e.dn == 25)
    sized = eng.evaluate_size(flow_m3h, entry, props, "carbon_steel", "lthw")
    pv = eng.velocity_pressure(sized.velocity_ms, props.density_kg_m3)
    fitting = pf.FITTINGS_BY_KEY["elbow_90_std"]
    dp = pf.fitting_pressure_drop(fitting.k, pv)
    assert dp == pytest.approx(0.9 * pv)
    assert dp > 0
