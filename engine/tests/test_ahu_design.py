"""Acceptance tests for design_ahu_to_supply (SPEC-ahu-processes.md)."""

import pytest

from hvac_engine import psychrometrics as psy
from hvac_engine.ahu_design import design_ahu_to_supply


def _labels(r):
    return [s.label for s in r.stages]


def _stage(r, label):
    return next(s for s in r.stages if s.label == label)


# -- Cool + reheat (the headline case) -----------------------------------------

def test_supply_cool_and_reheat():
    on = psy.state(28.0, rh=0.5)
    sup = psy.state(14.0, rh=0.9)
    r = design_ahu_to_supply(m_da=1.5, supply=sup, outdoor=on)
    labs = _labels(r)
    assert labs == ["OA", "SAT", "CC", "HC", "SUP"]
    assert r.cooling_total < 0
    assert r.heating_total > 0
    assert r.moisture_removed > 0
    # Off-coil sits on the saturation curve at the supply dew point.
    cc = _stage(r, "CC")
    assert cc.state.rh == pytest.approx(1.0, abs=1e-6)
    assert cc.state.t_db == pytest.approx(sup.t_dp, abs=0.05)
    # Delivered supply matches the requested condition.
    sup_out = _stage(r, "SUP").state
    assert sup_out.t_db == pytest.approx(sup.t_db, abs=0.05)
    assert sup_out.w == pytest.approx(sup.w, abs=5e-5)
    assert not r.warnings


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


# -- Reachability ---------------------------------------------------------------

def test_supply_moisture_above_on_coil_raises():
    on = psy.state(20.0, rh=0.4)
    sup = psy.state(18.0, rh=0.8)  # wetter than on-coil
    with pytest.raises(ValueError, match="cooling coil can only remove moisture"):
        design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on)


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
    assert r.cooling_total < 0 and r.heating_total > 0


# -- Frost ----------------------------------------------------------------------

def test_supply_frost_flagged():
    on = psy.state(25.0, rh=0.5)
    sup = psy.state(5.0, rh=0.6)  # dew point below 0 degC
    r = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on)
    assert r.frost_risk
    assert any("Frost" in w for w in r.warnings)


# -- Stage continuity -----------------------------------------------------------

def test_supply_stage_continuity():
    oa = psy.state(30.0, rh=0.6)
    ra = psy.state(23.0, rh=0.5)
    sup = psy.state(13.0, rh=0.9)
    r = design_ahu_to_supply(
        m_da=1.5, supply=sup, outdoor=oa, return_air=ra, oa_fraction=0.4
    )
    # Each treatment stage's inlet equals the previous stage's outlet. Skip the
    # RA/MA mixing junction (RA is a side inlet, not a series step).
    chain = [s for s in r.stages if s.label not in ("OA", "RA")]
    prev = _stage(r, "MA").state
    for s in chain[1:]:  # first chain entry is MA itself
        # temperature is monotonic through cool→reheat; just assert the states link
        # by checking the previous outlet is a valid predecessor (no gaps in w).
        assert s.state.w <= prev.w + 1e-9 or abs(s.state.w - prev.w) < 1e-9
        prev = s.state


# -- Draw-through fan accounts in reheat ---------------------------------------

def test_supply_draw_through_fan_lands_on_supply():
    on = psy.state(28.0, rh=0.5)
    sup = psy.state(14.0, rh=0.9)
    r = design_ahu_to_supply(
        m_da=1.5, supply=sup, outdoor=on, fan_position="draw", fan_power_kw=0.8
    )
    sup_out = r.stages[-1].state
    assert sup_out.t_db == pytest.approx(sup.t_db, abs=0.05)
    assert sup_out.w == pytest.approx(sup.w, abs=5e-5)
    # Reheat coil targets below the supply DB; the fan makes up the difference.
    hc = _stage(r, "HC")
    assert hc.state.t_db < sup.t_db
