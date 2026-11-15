"""Acceptance tests for design_ahu_to_supply (SPEC-ahu-processes.md)."""

import pytest

from hvac_engine import psychrometrics as psy
from hvac_engine.ahu_design import design_ahu_to_supply, supply_process_title
from hvac_engine.processes import cooling_coil


def _labels(r):
    return [s.label for s in r.stages]


def _stage(r, label):
    return next(s for s in r.stages if s.label == label)


def _supply_on_chord(on, t_adp: float, bf: float, t_sup: float):
    """Off-coil moisture from the ADP chord, then reheat to ``t_sup``."""
    c = cooling_coil(on, 1.0, t_adp=t_adp, bypass_factor=bf)
    return psy.state(t_sup, w=c.state.w, p=on.p)


# -- Cool + reheat on the ADP / bypass-factor chord ----------------------------

def test_supply_dehumid_uses_adp_chord_not_saturation_waypoint():
    on = psy.state(28.0, rh=0.5)
    t_adp, bf = 9.0, 0.15
    sup = _supply_on_chord(on, t_adp, bf, t_sup=18.0)
    r = design_ahu_to_supply(m_da=1.5, supply=sup, outdoor=on, t_adp=t_adp)
    labs = _labels(r)
    assert "SAT" not in labs
    assert labs[0] == "OA"
    assert "CC" in labs and "HC" in labs
    cc = _stage(r, "CC")
    assert cc.state.w == pytest.approx(sup.w, abs=5e-5)
    assert "ADP 9.0" in cc.note
    assert "bypass factor" in cc.note
    assert r.cooling_total < 0
    assert r.heating_total > 0
    assert r.moisture_removed > 0
    assert _stage(r, "SUP").state.t_db == pytest.approx(sup.t_db, abs=0.05)
    assert _stage(r, "SUP").state.w == pytest.approx(sup.w, abs=5e-5)


def test_supply_dehumid_matches_forward_cooling_coil():
    on = psy.state(28.0, rh=0.5)
    t_adp, bf = 9.0, 0.20
    forward = cooling_coil(on, 1.2, t_adp=t_adp, bypass_factor=bf)
    # Leave at the coil off-coil state (no reheat).
    r = design_ahu_to_supply(
        m_da=1.2, supply=forward.state, outdoor=on, t_adp=t_adp,
    )
    cc = _stage(r, "CC")
    assert cc.state.t_db == pytest.approx(forward.state.t_db, abs=0.05)
    assert cc.state.w == pytest.approx(forward.state.w, abs=5e-5)
    assert cc.q_total == pytest.approx(forward.q_total, abs=0.05)
    assert "HC" not in _labels(r)


def test_colder_adp_allows_drier_supply():
    on = psy.state(30.0, rh=0.55)
    warm = design_ahu_to_supply(
        m_da=1.0,
        supply=_supply_on_chord(on, 10.0, 0.25, 16.0),
        outdoor=on,
        t_adp=10.0,
    )
    cold = design_ahu_to_supply(
        m_da=1.0,
        supply=_supply_on_chord(on, 6.0, 0.25, 16.0),
        outdoor=on,
        t_adp=6.0,
    )
    assert _stage(cold, "CC").state.w < _stage(warm, "CC").state.w


# -- Sensible-only duties -------------------------------------------------------

def test_supply_sensible_cooling_only():
    on = psy.state(26.0, w=0.008)
    # ADP above dew point → dry coil if provided; equal moisture uses sensible path.
    t_adp = on.t_dp + 2.0
    sup = psy.state(18.0, w=0.008)
    r = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on, t_adp=t_adp)
    assert _labels(r) == ["OA", "CC", "SUP"]
    assert r.cooling_total < 0
    assert r.moisture_removed == pytest.approx(0.0, abs=1e-9)
    assert _stage(r, "CC").q_latent == pytest.approx(0.0, abs=1e-6)
    assert "Dry coil" in _stage(r, "CC").note


def test_supply_heating_only():
    on = psy.state(15.0, rh=0.5)
    sup = psy.state(22.0, w=on.w)
    r = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on)
    assert _labels(r) == ["OA", "HC", "SUP"]
    assert r.cooling_total == 0.0
    assert r.heating_total > 0


# -- Reachability / winter humidification ---------------------------------------

def test_supply_heat_and_humidify_winter():
    oa = psy.state(-5.0, rh=0.9)
    ra = psy.state(21.0, rh=0.5)
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
    on = psy.state(20.0, rh=0.3)
    sup = psy.state(20.0, rh=0.5)
    assert sup.w > on.w
    r = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on)
    assert "HUM" in _labels(r)
    assert "HC" not in _labels(r)
    assert r.moisture_added > 0
    assert _stage(r, "SUP").state.w == pytest.approx(sup.w, abs=5e-5)


def test_dry_adp_cannot_dehumidify():
    on = psy.state(28.0, rh=0.5)
    # ADP above dew point while asking for drier supply.
    t_adp = on.t_dp + 1.0
    sup = psy.state(18.0, w=on.w * 0.7)
    with pytest.raises(ValueError, match="dry"):
        design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on, t_adp=t_adp)


def test_supply_moisture_below_adp_raises():
    on = psy.state(28.0, rh=0.5)
    t_adp = 9.0
    w_adp = psy.saturation_humidity_ratio(t_adp)
    # Ask for moisture below saturated ADP — impossible on this chord.
    sup = psy.state(14.0, w=w_adp * 0.5)
    with pytest.raises(ValueError, match="below the ADP"):
        design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on, t_adp=t_adp)


def test_missing_adp_raises_when_dehumidifying():
    on = psy.state(28.0, rh=0.5)
    sup = psy.state(14.0, rh=0.9)
    with pytest.raises(ValueError, match="apparatus dew point"):
        design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on)


# -- Mixing ---------------------------------------------------------------------

def test_supply_with_oa_ra_mixing():
    oa = psy.state(30.0, rh=0.55)
    ra = psy.state(24.0, rh=0.5)
    t_adp = 8.0
    # Build a reachable supply from the mixed on-coil condition.
    m_da = 2.0
    from hvac_engine.processes import mix
    mx = mix(oa, m_da * 0.3, ra, m_da * 0.7)
    sup = _supply_on_chord(mx.state, t_adp, 0.2, 14.0)
    r = design_ahu_to_supply(
        m_da=m_da, supply=sup, outdoor=oa, return_air=ra, oa_fraction=0.3,
        t_adp=t_adp,
    )
    labs = _labels(r)
    assert labs[:3] == ["OA", "RA", "MA"]
    ma = _stage(r, "MA").state
    assert ma.w == pytest.approx(0.3 * oa.w + 0.7 * ra.w, rel=1e-6)
    assert r.cooling_total < 0
    assert "SAT" not in labs


# -- Frost ----------------------------------------------------------------------

def test_supply_frost_flagged():
    on = psy.state(25.0, rh=0.5)
    t_adp = -2.0
    # Reachable supply on the frost ADP chord, then reheat.
    forward = cooling_coil(on, 1.0, t_adp=t_adp, bypass_factor=0.25)
    sup = psy.state(12.0, w=forward.state.w)
    r = design_ahu_to_supply(m_da=1.0, supply=sup, outdoor=on, t_adp=t_adp)
    assert r.frost_risk
    assert any("Frost" in w for w in r.warnings)


# -- Stage continuity -----------------------------------------------------------

def test_supply_stage_continuity():
    oa = psy.state(30.0, rh=0.6)
    ra = psy.state(23.0, rh=0.5)
    from hvac_engine.processes import mix
    mx = mix(oa, 0.6, ra, 0.9)
    t_adp = 7.0
    forward = cooling_coil(mx.state, 1.5, t_adp=t_adp, bypass_factor=0.18)
    sup = psy.state(13.0, w=forward.state.w)
    r = design_ahu_to_supply(
        m_da=1.5, supply=sup, outdoor=oa, return_air=ra, oa_fraction=0.4,
        t_adp=t_adp,
    )
    chain = [s for s in r.stages if s.label not in ("OA", "RA")]
    prev = _stage(r, "MA").state
    for s in chain[1:]:
        assert s.state.w <= prev.w + 1e-9 or abs(s.state.w - prev.w) < 1e-9
        prev = s.state


# -- Draw-through fan accounts in reheat ---------------------------------------

def test_supply_draw_through_fan_lands_on_supply():
    on = psy.state(28.0, rh=0.5)
    t_adp = 9.0
    forward = cooling_coil(on, 1.5, t_adp=t_adp, bypass_factor=0.2)
    # Reheat target above off-coil so a heating stage exists before the fan.
    assert forward.state.t_db < 16.0
    sup = psy.state(16.0, w=forward.state.w)
    r = design_ahu_to_supply(
        m_da=1.5, supply=sup, outdoor=on, fan_position="draw", fan_power_kw=0.8,
        t_adp=t_adp,
    )
    sup_out = r.stages[-1].state
    assert sup_out.t_db == pytest.approx(sup.t_db, abs=0.05)
    assert sup_out.w == pytest.approx(sup.w, abs=5e-5)
    hc = _stage(r, "HC")
    assert hc.state.t_db < sup.t_db


def test_supply_process_titles():
    on = psy.state(28.0, rh=0.5)
    t_adp = 9.0
    forward = cooling_coil(on, 1.0, t_adp=t_adp, bypass_factor=0.15)
    reheat = design_ahu_to_supply(
        m_da=1.0, supply=psy.state(18.0, w=forward.state.w), outdoor=on, t_adp=t_adp,
    )
    assert supply_process_title(reheat) == "Dehumidification and reheat"
    dehum = design_ahu_to_supply(
        m_da=1.0, supply=forward.state, outdoor=on, t_adp=t_adp,
    )
    assert supply_process_title(dehum) in (
        "Cooling and dehumidification",
        "Dehumidification and reheat",
    )
    # Pure dehumid with leaving DB = off-coil → no reheat.
    assert "HC" not in _labels(dehum)
    assert supply_process_title(dehum) == "Cooling and dehumidification"

    sensible = design_ahu_to_supply(
        m_da=1.0, supply=psy.state(18.0, w=0.008), outdoor=psy.state(26.0, w=0.008),
        t_adp=psy.state(26.0, w=0.008).t_dp + 2.0,
    )
    assert supply_process_title(sensible) == "Sensible cooling only"
    warm = psy.state(15.0, rh=0.4)
    heating = design_ahu_to_supply(
        m_da=1.0, supply=psy.state(22.0, w=warm.w), outdoor=warm,
    )
    assert supply_process_title(heating) == "Heating"
    winter = design_ahu_to_supply(
        m_da=1.0, supply=psy.state(21.0, rh=0.4), outdoor=psy.state(-5.0, rh=0.9),
    )
    assert supply_process_title(winter) == "Heating and humidification"


def test_all_return_air_has_no_outdoor_stage():
    ra = psy.state(22.0, rh=0.5)
    t_adp = ra.t_dp + 2.0
    sup = psy.state(16.0, w=ra.w)
    r = design_ahu_to_supply(
        m_da=1.2, supply=sup, outdoor=ra, return_air=ra, oa_fraction=0.0,
        t_adp=t_adp,
    )
    assert _labels(r)[0] == "RA"
    assert "OA" not in _labels(r)
    assert "MA" not in _labels(r)
    assert supply_process_title(r) == "Sensible cooling only"


def test_blow_through_fan_raises_on_coil():
    on = psy.state(28.0, rh=0.5)
    t_adp = 9.0
    forward = cooling_coil(on, 1.0, t_adp=t_adp, bypass_factor=0.2)
    # After blow-through the on-coil is warmer; still reach the same W with ADP.
    r = design_ahu_to_supply(
        m_da=1.0, supply=psy.state(16.0, w=forward.state.w), outdoor=on,
        fan_position="blow", fan_power_kw=1.0, t_adp=t_adp,
    )
    assert "FAN" in _labels(r)
