"""Acceptance tests from SPEC-ahu-processes.md."""

import pytest

from hvac_engine import processes as proc
from hvac_engine import psychrometrics as psy


# -- Mixing --------------------------------------------------------------------

def test_mix_mass_balance():
    a = psy.state(30.0, w=0.010)
    b = psy.state(10.0, w=0.005)
    r = proc.mix(a, 1.0, b, 1.0)
    assert r.state.w == pytest.approx(0.0075, abs=1e-9)
    assert r.state.h == pytest.approx((a.h + b.h) / 2, abs=1e-9)
    assert r.state.t_db == pytest.approx(20.0, abs=0.2)
    assert not r.fog and r.condensate == 0.0
    assert r.m_da == pytest.approx(2.0)


def test_mix_weighted():
    a = psy.state(28.0, rh=0.5)
    b = psy.state(20.0, rh=0.5)
    r = proc.mix(a, 0.3, b, 0.7)
    assert r.state.w == pytest.approx(0.3 * a.w + 0.7 * b.w, rel=1e-9)


def test_mix_fog_settles_to_saturation():
    warm = psy.state(30.0, rh=0.95)
    cold = psy.state(-10.0, rh=0.9)
    r = proc.mix(warm, 0.5, cold, 0.5)
    if r.fog:
        assert r.state.rh == pytest.approx(1.0, abs=1e-6)
        assert r.condensate >= 0.0
    else:
        assert r.state.rh <= 1.0 + 1e-9


def test_mix_validation():
    a = psy.state(20.0, rh=0.5)
    with pytest.raises(ValueError):
        proc.mix(a, 0.0, a, 0.0)
    with pytest.raises(ValueError):
        proc.mix(a, 1.0, psy.state(20.0, rh=0.5, p=90.0), 1.0)


# -- Sensible ------------------------------------------------------------------

def test_sensible_energy_balance():
    s = psy.state(10.0, w=0.005)
    r = proc.sensible(s, 1.0, 30.0)
    assert r.q_total == pytest.approx(20.3, abs=0.3)
    assert r.state.w == pytest.approx(s.w, rel=1e-12)
    assert r.q_latent == 0.0


def test_sensible_cooling_below_dew_point_raises():
    s = psy.state(25.0, rh=0.6)  # dew point ~16.7
    with pytest.raises(ValueError):
        proc.sensible(s, 1.0, 10.0)


# -- Cooling coil ----------------------------------------------------------------

def test_coil_worked_case():
    """ADP + off-coil T locks moisture on the ON→ADP chord (~90% RH leaving)."""
    on = psy.state(28.0, rh=0.5)
    r = proc.cooling_coil(on, 1.0, t_adp=9.0, t_off=12.0)
    assert r.q_total == pytest.approx(-26.4, abs=1.5)
    assert r.q_sensible < 0 and r.q_latent < 0
    assert 0.0 < r.shr < 1.0
    assert r.condensate > 0.0
    assert r.t_adp == pytest.approx(9.0)
    assert 0.88 < r.state.rh < 0.93
    assert r.contact_factor is not None and 0.0 < r.contact_factor <= 1.0
    assert r.bypass_factor == pytest.approx(1.0 - r.contact_factor)
    assert r.bypass_factor == pytest.approx((12.0 - 9.0) / (28.0 - 9.0))
    assert not r.frost_risk


def test_coil_from_bypass_factor():
    on = psy.state(28.0, rh=0.5)
    r = proc.cooling_coil(on, 1.0, t_adp=9.0, bypass_factor=0.2)
    assert r.state.t_db == pytest.approx(9.0 + 0.2 * (28.0 - 9.0))
    assert r.bypass_factor == pytest.approx(0.2)
    assert r.state.rh < 1.0


def test_coil_legacy_off_coil_rh():
    """AHU-style t_off + rh_off solves ADP then uses the forward chord model."""
    on = psy.state(28.0, rh=0.5)
    r = proc.cooling_coil(on, 1.0, t_off=12.0, rh_off=0.90)
    assert r.state.rh == pytest.approx(0.90, abs=1e-6)
    assert r.t_adp is not None and 4.0 < r.t_adp < 12.0
    assert r.q_total == pytest.approx(-27.0, abs=1.5)


def test_coil_energy_consistency():
    on = psy.state(26.0, rh=0.55)
    r = proc.cooling_coil(on, 2.5, t_adp=8.0, t_off=11.0)
    assert r.q_total == pytest.approx(r.q_sensible + r.q_latent, rel=1e-9)
    assert r.q_total == pytest.approx(2.5 * (r.state.h - on.h), rel=1e-9)


def test_coil_frost_case():
    on = psy.state(16.0, rh=0.3)
    r = proc.cooling_coil(on, 1.0, t_adp=-2.0, t_off=2.0)
    assert r.t_adp is not None and r.t_adp <= 0.0
    assert r.frost_risk


def test_coil_validation():
    on = psy.state(24.0, rh=0.5)
    with pytest.raises(ValueError):
        proc.cooling_coil(on, 1.0, t_adp=10.0, t_off=25.0)
    with pytest.raises(ValueError, match="apparatus dew point"):
        proc.cooling_coil(on, 1.0, t_adp=10.0, t_off=8.0)
    with pytest.raises(ValueError, match="cannot\\s+humidify"):
        proc.cooling_coil(on, 1.0, t_off=22.0, rh_off=0.95)


def test_dry_coil_sensible_only():
    on = psy.state(24.0, rh=0.3)  # dew point ~5 degC
    r = proc.cooling_coil(on, 1.0, t_adp=on.t_dp + 2.0, t_off=15.0)
    assert r.condensate == pytest.approx(0.0, abs=1e-9)
    assert r.q_latent == pytest.approx(0.0, abs=1e-6)
    assert r.shr == pytest.approx(1.0, abs=1e-6)
    assert r.state.w == pytest.approx(on.w, abs=1e-12)


# -- Humidification --------------------------------------------------------------

def test_steam_humidify():
    s = psy.state(20.0, rh=0.3)
    w_target = psy.humidity_ratio_from_rh(20.0, 0.5)
    r = proc.steam_humidify(s, 1.0, w_target)
    assert r.state.t_db == pytest.approx(20.0, abs=0.01)
    assert r.state.rh == pytest.approx(0.5, abs=1e-6)
    assert r.steam_rate > 0.0
    with pytest.raises(ValueError):
        proc.steam_humidify(s, 1.0, s.w * 0.5)


def test_adiabatic_humidify():
    s = psy.state(28.0, rh=0.3)
    r = proc.adiabatic_humidify(s, 1.0, 0.85)
    assert r.state.t_wb == pytest.approx(s.t_wb, abs=0.05)
    assert r.state.t_db < s.t_db
    assert r.state.w > s.w
    assert r.water_rate > 0.0
    with pytest.raises(ValueError):
        proc.adiabatic_humidify(s, 1.0, 1.5)


# -- AHU simulation ---------------------------------------------------------------

def test_ahu_winter_full_fresh_air():
    """Full fresh air winter unit - frost coil active on the raw OA."""
    r = proc.simulate_ahu(
        m_da=2.0,
        outdoor=psy.state(-5.0, rh=0.9),
        oa_fraction=1.0,
        frost_coil_t=5.0,
        reheat_t=21.0,
        steam_rh_target=0.4,
    )
    labels = [s.label for s in r.stages]
    assert labels == ["OA", "FROST", "HC", "HUM", "SUP"]
    assert r.heating_total > 0.0
    assert r.moisture_added > 0.0
    assert r.cooling_total == 0.0


def test_ahu_winter_mixed_frost_coil_idle():
    """30% OA mixes to ~13 degC - frost coil correctly stays off."""
    r = proc.simulate_ahu(
        m_da=2.0,
        outdoor=psy.state(-5.0, rh=0.9),
        return_air=psy.state(21.0, rh=0.5),
        oa_fraction=0.3,
        frost_coil_t=5.0,
        reheat_t=21.0,
        steam_rh_target=0.4,
    )
    labels = [s.label for s in r.stages]
    assert labels == ["OA", "RA", "MA", "HC", "HUM", "SUP"]
    ma = next(s for s in r.stages if s.label == "MA")
    assert 5.0 < ma.state.t_db < 21.0


def test_ahu_summer_chain():
    r = proc.simulate_ahu(
        m_da=2.0,
        outdoor=psy.state(28.0, rh=0.5),
        return_air=psy.state(23.0, rh=0.5),
        oa_fraction=0.3,
        coil_t_off=12.0,
        coil_rh_off=0.9,
        reheat_t=14.0,
    )
    labels = [s.label for s in r.stages]
    assert labels == ["OA", "RA", "MA", "CC", "HC", "SUP"]
    cc = next(s for s in r.stages if s.label == "CC")
    hc = next(s for s in r.stages if s.label == "HC")
    assert cc.q_total < 0.0 < hc.q_total
    assert r.stages[-1].state.t_db == pytest.approx(14.0, abs=1e-9)
    assert r.moisture_removed > 0.0
    assert not r.frost_risk


def test_ahu_full_fresh_air_no_mixing():
    r = proc.simulate_ahu(
        m_da=1.0,
        outdoor=psy.state(28.0, rh=0.5),
        oa_fraction=1.0,
        coil_t_off=12.0,
    )
    labels = [s.label for s in r.stages]
    assert "MA" not in labels and "RA" not in labels


def test_ahu_stage_continuity():
    r = proc.simulate_ahu(
        m_da=1.5,
        outdoor=psy.state(30.0, rh=0.4),
        return_air=psy.state(22.0, rh=0.5),
        oa_fraction=0.5,
        coil_t_off=11.0,
        reheat_t=16.0,
        fan_pickup_dt=0.5,
    )
    chain = [s for s in r.stages if s.label not in ("OA", "RA")]
    for prev, cur in zip(chain, chain[1:]):
        dh = cur.state.h - prev.state.h
        assert cur.q_total == pytest.approx(1.5 * dh, abs=1e-6)


def test_ahu_validation():
    oa = psy.state(20.0, rh=0.5)
    with pytest.raises(ValueError):
        proc.simulate_ahu(m_da=1.0, outdoor=oa, oa_fraction=0.5)
    with pytest.raises(ValueError):
        proc.simulate_ahu(
            m_da=1.0, outdoor=oa, steam_rh_target=0.5, adiabatic_effectiveness=0.8
        )


# -- Fan gain ---------------------------------------------------------------------

def test_fan_gain_from_power():
    s = psy.state(14.0, rh=0.85)
    r = proc.fan_gain(s, 2.0, power_kw=3.0)
    cp = 1.006 + 1.86 * s.w
    assert r.state.t_db == pytest.approx(14.0 + 3.0 / (2.0 * cp), abs=1e-9)
    assert r.q_total == pytest.approx(3.0, rel=0.01)  # enthalpy duty ~ input power
    assert r.state.w == pytest.approx(s.w, rel=1e-12)


def test_fan_gain_from_dt():
    s = psy.state(20.0, rh=0.5)
    r = proc.fan_gain(s, 1.0, dt=1.2)
    assert r.state.t_db == pytest.approx(21.2, abs=1e-9)


def test_fan_gain_validation():
    s = psy.state(20.0, rh=0.5)
    with pytest.raises(ValueError):
        proc.fan_gain(s, 1.0)
    with pytest.raises(ValueError):
        proc.fan_gain(s, 1.0, power_kw=1.0, dt=1.0)
    with pytest.raises(ValueError):
        proc.fan_gain(s, 1.0, power_kw=-1.0)


def test_ahu_fan_position_changes_coil_duty():
    base = dict(
        m_da=2.0,
        outdoor=psy.state(28.0, rh=0.5),
        return_air=psy.state(23.0, rh=0.5),
        oa_fraction=0.3,
        coil_t_off=12.0,
        coil_rh_off=0.9,
        fan_power_kw=3.0,
    )
    blow = proc.simulate_ahu(fan_position="blow", **base)
    draw = proc.simulate_ahu(fan_position="draw", **base)

    labels_blow = [s.label for s in blow.stages]
    labels_draw = [s.label for s in draw.stages]
    assert "FAN" in labels_blow and labels_blow.index("FAN") < labels_blow.index("CC")
    assert "FAN" not in labels_draw

    cc_blow = next(s for s in blow.stages if s.label == "CC")
    cc_draw = next(s for s in draw.stages if s.label == "CC")
    # blow-through fan preheats the on-coil air -> bigger coil duty
    assert abs(cc_blow.q_total) > abs(cc_draw.q_total)
    # draw-through fan warms the supply instead
    assert draw.stages[-1].state.t_db > cc_draw.state.t_db
    # same off-coil condition either way
    assert cc_blow.state.t_db == pytest.approx(cc_draw.state.t_db)


def test_ahu_fan_position_validation():
    with pytest.raises(ValueError):
        proc.simulate_ahu(
            m_da=1.0, outdoor=psy.state(20.0, rh=0.5), fan_position="sideways"
        )
