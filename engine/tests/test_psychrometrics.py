"""Acceptance tests from SPEC-psychrometrics.md — public ASHRAE anchor values."""

import math

import pytest

from hvac_engine import psychrometrics as psy


# ── Saturation pressure vs HOF Table 3 anchor values ──────────────────────────

@pytest.mark.parametrize(
    "t_c, expected_kpa, tol",
    [
        (0.0, 0.6112, 0.001),
        (20.0, 2.3392, 0.002),
        (25.0, 3.1699, 0.002),
        (-20.0, 0.10326, 0.0005),
        (50.0, 12.3513, 0.01),
    ],
)
def test_saturation_pressure_anchors(t_c, expected_kpa, tol):
    assert psy.saturation_pressure(t_c) == pytest.approx(expected_kpa, abs=tol)


def test_saturation_pressure_out_of_range():
    with pytest.raises(ValueError):
        psy.saturation_pressure(-61.0)
    with pytest.raises(ValueError):
        psy.saturation_pressure(91.0)


# ── Standard worked example: 40 degC db / 20 degC wb at sea level ─────────────

def test_hof_worked_example():
    s = psy.state(40.0, twb=20.0)
    assert s.w == pytest.approx(0.00650, abs=0.0002)
    assert s.h == pytest.approx(56.7, abs=0.3)
    assert s.v == pytest.approx(0.896, abs=0.003)
    assert s.t_dp == pytest.approx(7.4, abs=0.3)


# ── Round-trip consistency ─────────────────────────────────────────────────────

@pytest.mark.parametrize("t_db", [-10.0, 0.0, 15.0, 25.0, 35.0, 50.0])
@pytest.mark.parametrize("rh", [0.2, 0.5, 0.9])
def test_wet_bulb_round_trip(t_db, rh):
    s = psy.state(t_db, rh=rh)
    s2 = psy.state(t_db, twb=s.t_wb)
    assert s2.w == pytest.approx(s.w, abs=1e-6)


@pytest.mark.parametrize("t_c", [-15.0, 0.0, 10.0, 30.0, 60.0])
def test_dew_point_saturation_self_consistency(t_c):
    w_s = psy.saturation_humidity_ratio(t_c)
    assert psy.dew_point(w_s) == pytest.approx(t_c, abs=0.01)


@pytest.mark.parametrize("t_db, rh", [(22.0, 0.5), (35.0, 0.3), (5.0, 0.8)])
def test_enthalpy_round_trip(t_db, rh):
    s = psy.state(t_db, rh=rh)
    assert psy.dry_bulb_from_enthalpy(s.h, s.w) == pytest.approx(t_db, abs=1e-9)
    s2 = psy.state(t_db, h=s.h)
    assert s2.w == pytest.approx(s.w, rel=1e-9)


def test_state_pairs_agree():
    ref = psy.state(24.0, rh=0.55)
    for s in (
        psy.state(24.0, w=ref.w),
        psy.state(24.0, twb=ref.t_wb),
        psy.state(24.0, tdp=ref.t_dp),
        psy.state(24.0, h=ref.h),
        psy.state(h=ref.h, w=ref.w),
    ):
        assert s.t_db == pytest.approx(24.0, abs=1e-6)
        assert s.rh == pytest.approx(0.55, abs=1e-4)


# ── Physical sanity ────────────────────────────────────────────────────────────

def test_saturated_state_temperatures_coincide():
    s = psy.state(20.0, rh=1.0)
    assert s.t_wb == pytest.approx(20.0, abs=0.02)
    assert s.t_dp == pytest.approx(20.0, abs=0.02)


def test_ordering_db_wb_dp():
    s = psy.state(28.0, rh=0.4)
    assert s.t_dp < s.t_wb < s.t_db


def test_altitude_effect():
    sea = psy.state(20.0, rh=0.5)
    alt = psy.state(20.0, rh=0.5, p=90.0)  # ~1000 m
    assert alt.w > sea.w  # same RH holds more moisture per kg dry air at low p
    assert alt.v > sea.v


def test_density_typical_room_air():
    s = psy.state(20.0, rh=0.5)
    assert s.rho == pytest.approx(1.199, abs=0.01)


# ── Validation errors ──────────────────────────────────────────────────────────

def test_supersaturation_rejected():
    w_s = psy.saturation_humidity_ratio(20.0)
    with pytest.raises(ValueError, match="supersaturated"):
        psy.state(20.0, w=w_s * 1.05)


def test_bad_inputs_rejected():
    with pytest.raises(ValueError):
        psy.state(20.0, rh=1.2)
    with pytest.raises(ValueError):
        psy.state(20.0, twb=25.0)
    with pytest.raises(ValueError):
        psy.state(20.0, tdp=25.0)
    with pytest.raises(ValueError):
        psy.state(20.0)  # no second property
    with pytest.raises(ValueError):
        psy.state(20.0, rh=0.5, w=0.005)  # two second properties


def test_dew_point_of_dry_air_is_minus_inf_marker():
    s = psy.state(20.0, w=0.0)
    assert math.isinf(s.t_dp)


# ── Standard atmosphere: pressure_from_altitude ─────────────────────────────────

def test_pressure_from_altitude_sea_level():
    assert psy.pressure_from_altitude(0.0) == pytest.approx(101.325, abs=1e-9)


def test_pressure_from_altitude_known_points():
    # HOF Table 1 (US standard atmosphere) anchor values.
    assert psy.pressure_from_altitude(1000.0) == pytest.approx(89.88, abs=0.05)
    assert psy.pressure_from_altitude(2000.0) == pytest.approx(79.50, abs=0.05)


def test_pressure_from_altitude_decreases_with_height():
    assert psy.pressure_from_altitude(500.0) < psy.pressure_from_altitude(0.0)
    assert psy.pressure_from_altitude(2000.0) < psy.pressure_from_altitude(500.0)


def test_pressure_from_altitude_out_of_range_rejected():
    with pytest.raises(ValueError, match="outside the standard-atmosphere"):
        psy.pressure_from_altitude(psy.Z_MAX + 1000.0)
    with pytest.raises(ValueError, match="outside the standard-atmosphere"):
        psy.pressure_from_altitude(psy.Z_MIN - 1000.0)
