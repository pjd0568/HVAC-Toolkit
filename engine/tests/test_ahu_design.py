"""Acceptance tests for design_ahu_to_supply (SPEC-ahu-processes.md)."""

import pytest

from hvac_engine import psychrometrics as psy
from hvac_engine.ahu_design import design_ahu_to_supply


def _labels(r):
    return [s.label for s in r.stages]


def _stage(r, label):
    return next(s for s in r.stages if s.label == label)


# -- Cool + reheat (default 90% off-coil RH — matches simulate_ahu) ------------

def test_supply_cool_default_off_coil_rh_matches_supply_when_supply_at_90pct():
    # Supply already at 90% RH: off-coil at the same moisture + 90% RH lands on
    # the supply dry bulb, so no reheat stage is needed.
    on = psy.state(28.0, rh=0.5)
    sup = psy.state(14.0, rh=0.9)
    r = design_ahu_to_supply(m_da=1.5, supply=sup, outdoor=on)
    assert "CC" in _labels(r)
    assert "HC" not in _labels(r)
    cc = _stage(r, "CC")
    assert cc.state.rh == pytest.approx(0.90, abs=1e-3)
    assert cc.state.w == pytest.approx(sup.w, abs=5e-5)
    assert cc.state.t_db == pytest.approx(sup.t_db, abs=0.05)
    assert r.cooling_total < 0
    assert r.moisture_removed > 0
    assert r.heating_total == pytest.approx(0.0, abs=1e-9)
    sup_out = _stage(r, "SUP").state
    assert sup_out.t_db == pytest.approx(sup.t_db, abs=0.05)
    assert sup_out.w == pytest.approx(sup.w, abs=5e-5)


def test_supply_cool_and_reheat_cf1_saturated_off_coil():
    # Idealised CF=1 model: off-coil = supply dew point, saturated; then reheat.
    on = psy.state(28.0, rh=0.5)
    sup = psy.state(14.0, rh=0.9)
    r = design_ahu_to_supply(m_da=1.5, supply=sup, outdoor=on, coil_rh_off=1.0)
    labs = _labels(r)
    assert labs == ["OA", "SAT", "CC", "HC", "SUP"]
    assert r.cooling_total < 0
    assert r.heating_total > 0
    assert r.moisture_removed > 0
    cc = _stage(r, "CC")
    assert cc.state.rh == pytest.approx(1.0, abs=1e-6)
    assert cc.state.t_db == pytest.approx(sup.t_dp, abs=0.05)
    sup_out = _stage(r, "SUP").state
    assert sup_out.t_db == pytest.approx(sup.t_db, abs=0.05)
    assert sup_out.w == pytest.approx(sup.w, abs=5e-5)
    assert not r.warnings


def test_default_off_coil_rh_uses_less_cooling_than_cf1():
    # CF=1 cools further to the dew point → larger (more negative) cooling duty.
    on = psy.state(30.0, rh=0.55)
    sup = psy.state(16.0, rh=0.55)
    r90 = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on, coil_rh_off=0.90)
    r100 = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on, coil_rh_off=1.0)
    assert r100.cooling_total < r90.cooling_total
    assert _stage(r90, "CC").state.rh == pytest.approx(0.90, abs=1e-3)
    assert _stage(r100, "CC").state.rh == pytest.approx(1.0, abs=1e-6)


# -- Sensible-only duties -------------------------------------------------------

def test_supply_sensible_cooling_only():
    on = psy.state(26.0, w=0.008)
    sup = psy.state(18.0, w=0.008)  # same moisture, cooler
    r = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on)
    assert _labels(r) == ["OA", "CC", "SUP"]
    assert r.cooling_total < 0
    assert r.moisture_removed == pytest.approx(0.0, abs=1e-9)
    assert _stage(r, "CC").q_latent == 0.0


def test_supply_heating_only():
    on = psy.state(15.0, rh=0.5)
    sup = psy.state(22.0, w=on.w)  # same moisture, warmer
    r = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on)
    assert _labels(r) == ["OA", "HC", "SUP"]
    assert r.cooling_total == 0.0
    assert r.heating_total > 0


# -- Reachability / winter humidification ---------------------------------------

def test_supply_heat_and_humidify_winter():
    # Cold dry OA mixed with return → on-coil drier than supply → heat + steam.
    oa = psy.state(-5.0, rh=0.9)
    ra = psy.state(21.0, rh=0.5)
    # 21 °C / 40% is wetter than a 30% OA mix of −5/90 and 21/50.
    sup = psy.state(21.0, rh=0.4)
    r = design_ahu_to_supply(
        m_da=1.5, supply=sup, outdoor=oa, return_air=ra, oa_fraction=0.3,
    )
    labs = _labels(r)
    assert labs[:3] == ["OA", "RA", "MA"]
    assert "HC" in labs
    assert "HUM" in labs
    assert "CC" not in labs
    assert r.heating_total > 0
    assert r.moisture_added > 0
    assert r.cooling_total == pytest.approx(0.0, abs=1e-9)
    assert r.moisture_removed == pytest.approx(0.0, abs=1e-9)
    hum = _stage(r, "HUM")
    assert "Humidification required" in hum.note
    sup_out = _stage(r, "SUP").state
    assert sup_out.t_db == pytest.approx(sup.t_db, abs=0.05)
    assert sup_out.w == pytest.approx(sup.w, abs=5e-5)


def test_supply_humidify_only_when_already_at_supply_db():
    # On-coil already at supply dry bulb but drier → steam only.
    on = psy.state(20.0, rh=0.3)
    # Same DB, higher RH → wetter.
    sup = psy.state(20.0, rh=0.5)
    assert sup.w > on.w
    r = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on)
    assert "HUM" in _labels(r)
    assert "HC" not in _labels(r)
    assert r.moisture_added > 0
    assert _stage(r, "SUP").state.w == pytest.approx(sup.w, abs=5e-5)


def test_invalid_coil_rh_off_raises():
    on = psy.state(28.0, rh=0.5)
    sup = psy.state(14.0, rh=0.9)
    with pytest.raises(ValueError, match="off-coil RH"):
        design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on, coil_rh_off=0.0)


# -- Mixing ---------------------------------------------------------------------

def test_supply_with_oa_ra_mixing():
    oa = psy.state(30.0, rh=0.55)
    ra = psy.state(24.0, rh=0.5)
    sup = psy.state(13.0, rh=0.95)
    r = design_ahu_to_supply(
        m_da=2.0, supply=sup, outdoor=oa, return_air=ra, oa_fraction=0.3
    )
    labs = _labels(r)
    assert labs[:3] == ["OA", "RA", "MA"]
    # Mixed on-coil moisture is the mass-weighted blend of OA and RA.
    ma = _stage(r, "MA").state
    assert ma.w == pytest.approx(0.3 * oa.w + 0.7 * ra.w, rel=1e-6)
    assert r.cooling_total < 0


# -- Frost ----------------------------------------------------------------------

def test_supply_frost_flagged():
    on = psy.state(25.0, rh=0.5)
    # Low dew point: CF=1 off-coil is at/below freezing.
    sup = psy.state(5.0, rh=0.6)
    r = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on, coil_rh_off=1.0)
    assert r.frost_risk
    assert any("Frost" in w for w in r.warnings)


# -- Stage continuity -----------------------------------------------------------

def test_supply_stage_continuity():
    oa = psy.state(30.0, rh=0.6)
    ra = psy.state(23.0, rh=0.5)
    # Use CF=1 so cool→reheat is present and moisture falls then holds.
    sup = psy.state(13.0, rh=0.9)
    r = design_ahu_to_supply(
        m_da=1.5, supply=sup, outdoor=oa, return_air=ra, oa_fraction=0.4,
        coil_rh_off=1.0,
    )
    chain = [s for s in r.stages if s.label not in ("OA", "RA")]
    prev = _stage(r, "MA").state
    for s in chain[1:]:  # first chain entry is MA itself
        assert s.state.w <= prev.w + 1e-9 or abs(s.state.w - prev.w) < 1e-9
        prev = s.state


# -- Draw-through fan accounts in reheat ---------------------------------------

def test_supply_draw_through_fan_lands_on_supply():
    on = psy.state(28.0, rh=0.5)
    sup = psy.state(14.0, rh=0.9)
    r = design_ahu_to_supply(
        m_da=1.5, supply=sup, outdoor=on, fan_position="draw", fan_power_kw=0.8,
        coil_rh_off=1.0,
    )
    sup_out = r.stages[-1].state
    assert sup_out.t_db == pytest.approx(sup.t_db, abs=0.05)
    assert sup_out.w == pytest.approx(sup.w, abs=5e-5)
    # Reheat coil targets below the supply DB; the fan makes up the difference.
    hc = _stage(r, "HC")
    assert hc.state.t_db < sup.t_db


def test_blow_through_fan_raises_on_coil():
    on = psy.state(28.0, rh=0.5)
    sup = psy.state(14.0, rh=0.9)
    r = design_ahu_to_supply(
        m_da=1.0, supply=sup, outdoor=on,
        fan_position="blow", fan_power_kw=1.0,
    )
    assert "FAN" in _labels(r)
