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


# -- Adiabatic / evaporative cooling ---------------------------------------------

def test_adiabatic_cool_effectiveness():
    s = psy.state(35.0, rh=0.20)
    r = proc.adiabatic_cool(s, 1.0, effectiveness=0.85)
    assert r.effectiveness == pytest.approx(0.85)
    assert r.state.t_wb == pytest.approx(s.t_wb, abs=0.05)
    assert r.state.t_db == pytest.approx(
        s.t_db - 0.85 * (s.t_db - s.t_wb), abs=0.05
    )
    assert r.state.w > s.w
    assert r.q_sensible > 0
    assert r.water_rate > 0


def test_adiabatic_cool_duty_mode():
    s = psy.state(32.0, rh=0.25)
    r0 = proc.adiabatic_cool(s, 2.0, effectiveness=0.80)
    r1 = proc.adiabatic_cool(s, 2.0, q_sensible=r0.q_sensible)
    assert r1.state.t_db == pytest.approx(r0.state.t_db, abs=0.05)
    assert r1.effectiveness == pytest.approx(r0.effectiveness, abs=1e-3)


def test_adiabatic_cool_rh_target():
    s = psy.state(30.0, rh=0.25)
    r = proc.adiabatic_cool(s, 1.0, rh_out=0.70)
    assert r.state.rh == pytest.approx(0.70, abs=1e-3)
    assert r.state.t_wb == pytest.approx(s.t_wb, abs=0.05)
    assert 0.0 < r.effectiveness <= 1.0


def test_adiabatic_cool_below_wetbulb_raises():
    s = psy.state(30.0, rh=0.30)
    # Demand more cooling than wet-bulb approach allows.
    cp = 1.006 + 1.86 * s.w
    q_too_much = 1.0 * cp * (s.t_db - s.t_wb) * 1.2
    with pytest.raises(ValueError, match="wet-bulb limit"):
        proc.adiabatic_cool(s, 1.0, q_sensible=q_too_much)


# -- Desiccant dehumidification --------------------------------------------------

def test_desiccant_isenthalpic():
    s = psy.state(25.0, rh=0.60)
    w_out = 0.006
    r = proc.desiccant_dehumidify(s, 1.0, w_out=w_out, eta_d=1.0)
    assert r.state.w == pytest.approx(w_out)
    assert r.state.h == pytest.approx(s.h, abs=1e-6)
    assert r.state.t_db > s.t_db
    assert r.delta_w == pytest.approx(s.w - w_out)
    assert r.moisture_removed == pytest.approx(s.w - w_out)
    assert r.q_total == pytest.approx(0.0, abs=1e-9)
    assert r.dh_adsorption == pytest.approx(0.0, abs=1e-9)


def test_desiccant_efficiency_raises_enthalpy():
    s = psy.state(25.0, rh=0.60)
    w_out = 0.006
    ideal = proc.desiccant_dehumidify(s, 1.0, w_out=w_out, eta_d=1.0)
    real = proc.desiccant_dehumidify(s, 1.0, w_out=w_out, eta_d=0.85)
    assert real.state.h > ideal.state.h
    assert real.state.t_db > ideal.state.t_db
    assert real.dh_adsorption == pytest.approx(
        (1.0 - 0.85) * 2501.0 * (s.w - w_out), rel=1e-9
    )
    assert real.q_total == pytest.approx(real.dh_adsorption, rel=1e-9)


def test_desiccant_from_moisture_duty():
    s = psy.state(28.0, rh=0.50)
    m_da = 2.0
    removed = 0.01  # kg/s
    r = proc.desiccant_dehumidify(s, m_da, moisture_removed=removed, eta_d=1.0)
    assert r.moisture_removed == pytest.approx(removed)
    assert r.state.w == pytest.approx(s.w - removed / m_da)
    assert r.state.h == pytest.approx(s.h, abs=1e-6)


def test_desiccant_from_rh_target():
    s = psy.state(24.0, rh=0.55)
    r = proc.desiccant_dehumidify(s, 1.0, rh_out=0.20, eta_d=1.0)
    assert r.state.rh == pytest.approx(0.20, abs=1e-4)
    assert r.state.w < s.w
    assert r.state.t_db > s.t_db
    assert r.state.h == pytest.approx(s.h, abs=1e-4)


def test_desiccant_validation():
    s = psy.state(22.0, rh=0.5)
    with pytest.raises(ValueError):
        proc.desiccant_dehumidify(s, 1.0, w_out=s.w * 1.1)
    with pytest.raises(ValueError):
        proc.desiccant_dehumidify(s, 1.0, w_out=0.005, eta_d=0.0)
    with pytest.raises(ValueError):
        proc.desiccant_dehumidify(s, 1.0, w_out=0.005, rh_out=0.2)
    with pytest.raises(ValueError):
        proc.desiccant_dehumidify(s, 1.0, moisture_removed=s.w * 1.0 + 1.0)


# -- Heat + steam humidification -------------------------------------------------

def test_heat_humidify_state_mode():
    s1 = psy.state(5.0, rh=0.80)
    t2, w2 = 22.0, 0.008
    r = proc.heat_and_humidify(s1, 1.0, t_out=t2, w_out=w2)
    assert r.state_x.t_db == pytest.approx(t2)
    assert r.state_x.w == pytest.approx(s1.w)
    assert r.state.t_db == pytest.approx(t2, abs=0.01)
    assert r.state.w == pytest.approx(w2)
    assert r.q_sensible > 0 and r.q_latent > 0
    assert r.q_total == pytest.approx(r.q_sensible + r.q_latent, rel=1e-9)
    assert r.steam_rate == pytest.approx(w2 - s1.w)


def test_heat_humidify_duty_mode_roundtrip():
    s1 = psy.state(8.0, rh=0.70)
    r0 = proc.heat_and_humidify(s1, 1.5, t_out=20.0, w_out=0.0075)
    r1 = proc.heat_and_humidify(
        s1, 1.5, q_sensible=r0.q_sensible, steam_rate=r0.steam_rate
    )
    assert r1.state.t_db == pytest.approx(r0.state.t_db, abs=0.05)
    assert r1.state.w == pytest.approx(r0.state.w, abs=1e-7)


def test_heat_humidify_heat_only():
    s1 = psy.state(10.0, rh=0.5)
    r = proc.heat_and_humidify(s1, 1.0, t_out=25.0, w_out=s1.w)
    assert r.steam_rate == pytest.approx(0.0, abs=1e-12)
    assert r.q_latent == pytest.approx(0.0, abs=1e-9)
    assert r.state.w == pytest.approx(s1.w)
    assert r.state_x.t_db == pytest.approx(25.0)


def test_heat_humidify_validation():
    s1 = psy.state(15.0, rh=0.4)
    with pytest.raises(ValueError, match="heating only"):
        proc.heat_and_humidify(s1, 1.0, t_out=10.0, w_out=0.01)
    with pytest.raises(ValueError, match="cannot dry"):
        proc.heat_and_humidify(s1, 1.0, t_out=20.0, w_out=s1.w * 0.5)
    with pytest.raises(ValueError):
        proc.heat_and_humidify(s1, 1.0, q_sensible=0.0, steam_rate=0.0)


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


# -- Interactive chart process map (SPEC-interactive-psych-chart) ---------------

def test_map_state_process_heat_humidify():
    a = psy.state(5.0, rh=0.8)
    b = psy.state(21.0, rh=0.5)
    r = proc.map_state_process(a, b)
    assert r.heat_cool == "heat"
    assert r.moisture_action == "humidify"
    assert r.delta_t == pytest.approx(16.0, abs=1e-9)
    assert r.delta_w > 0
    assert r.q_total is None


def test_map_state_process_cool_dehumidify_with_flow():
    a = psy.state(28.0, rh=0.6)
    b = psy.state(14.0, rh=0.9)
    m_da = 1.0  # kg/s
    r = proc.map_state_process(a, b, m_da=m_da)
    assert r.heat_cool == "cool"
    assert r.moisture_action == "dehumidify"
    assert r.q_total == pytest.approx(m_da * (b.h - a.h), abs=1e-9)
    assert r.moisture_kg_h == pytest.approx(m_da * (b.w - a.w) * 3600.0, abs=1e-6)
    h_sens = psy.enthalpy(b.t_db, a.w)
    assert r.q_sensible == pytest.approx(m_da * (h_sens - a.h), abs=1e-9)
    assert r.q_latent == pytest.approx(r.q_total - r.q_sensible, abs=1e-9)


def test_map_state_process_none_when_identical():
    a = psy.state(20.0, rh=0.5)
    r = proc.map_state_process(a, a)
    assert r.heat_cool == "none"
    assert r.moisture_action == "none"
    assert r.delta_t == pytest.approx(0.0, abs=1e-12)
    assert r.delta_w == pytest.approx(0.0, abs=1e-12)
