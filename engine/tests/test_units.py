"""Tests for hvac_engine.units — SI/IP conversions (SPEC-unit-conversions.md)."""

import math

import pytest

from hvac_engine import units as u


def approx(a, b, tol=1e-6):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


# ── Temperature (affine) ────────────────────────────────────────────────────────

def test_temperature_known_points_from_si():
    assert approx(u.from_si("temperature", 0.0, "IP"), 32.0)
    assert approx(u.from_si("temperature", 100.0, "IP"), 212.0)
    assert approx(u.from_si("temperature", 25.0, "IP"), 77.0)
    assert approx(u.from_si("temperature", -40.0, "IP"), -40.0)  # the crossover


def test_temperature_to_si():
    assert approx(u.to_si("temperature", 77.0, "IP"), 25.0)
    assert approx(u.to_si("temperature", 32.0, "IP"), 0.0)


def test_temperature_si_is_identity():
    assert approx(u.from_si("temperature", 21.0, "SI"), 21.0)
    assert approx(u.to_si("temperature", 21.0, "SI"), 21.0)


# ── Humidity ratio ──────────────────────────────────────────────────────────────

def test_humidity_ratio_si_display_is_g_per_kg():
    # 0.010 kg/kg -> 10 g/kg
    assert approx(u.from_si("humidity_ratio", 0.010, "SI"), 10.0)


def test_humidity_ratio_ip_is_grains_per_lb():
    # 0.010 kg/kg -> 70 gr/lb  (7000 gr/lb per kg/kg)
    assert approx(u.from_si("humidity_ratio", 0.010, "IP"), 70.0)
    assert approx(u.to_si("humidity_ratio", 70.0, "IP"), 0.010)


# ── Enthalpy ────────────────────────────────────────────────────────────────────

def test_enthalpy_btu_per_lb():
    # 2.326 kJ/kg == 1 Btu/lb exactly
    assert approx(u.from_si("enthalpy", 2.326, "IP"), 1.0)
    assert approx(u.to_si("enthalpy", 1.0, "IP"), 2.326)


# ── Pressure ────────────────────────────────────────────────────────────────────

def test_pressure_inhg():
    # 1 standard atmosphere 101.325 kPa ~ 29.921 inHg
    assert approx(u.from_si("pressure", 101.325, "IP"), 29.9213, tol=1e-3)
    assert approx(u.to_si("pressure", 29.9213, "IP"), 101.325, tol=1e-3)


# ── Volumetric flow ─────────────────────────────────────────────────────────────

def test_vol_flow_cfm():
    # 1000 m3/h -> ~588.58 CFM
    assert approx(u.from_si("vol_flow", 1000.0, "IP"), 588.5778, tol=1e-3)
    assert approx(u.to_si("vol_flow", 588.5778, "IP"), 1000.0, tol=1e-3)


# ── Mass flow ───────────────────────────────────────────────────────────────────

def test_mass_flow_lb_per_h():
    # 1 kg/s -> 7936.64 lb/h
    assert approx(u.from_si("mass_flow", 1.0, "IP"), 7936.6414, tol=1e-3)


# ── Power / duty ────────────────────────────────────────────────────────────────

def test_power_btu_per_h():
    assert approx(u.from_si("power", 1.0, "IP"), 3412.141633, tol=1e-6)
    assert approx(u.to_si("power", 3412.141633, "IP"), 1.0, tol=1e-6)


# ── Density & specific volume ───────────────────────────────────────────────────

def test_density_lb_per_ft3():
    assert approx(u.from_si("density", 1.2, "IP"), 1.2 * 0.06242796058, tol=1e-6)


def test_specific_volume_ft3_per_lb():
    assert approx(u.from_si("specific_volume", 0.83, "IP"), 0.83 * 16.01846337, tol=1e-6)


# ── Moisture rate ───────────────────────────────────────────────────────────────

def test_moisture_rate_si_is_kg_per_h():
    # 0.001 kg/s -> 3.6 kg/h
    assert approx(u.from_si("moisture_rate", 0.001, "SI"), 3.6)


def test_moisture_rate_ip_is_lb_per_h():
    assert approx(u.from_si("moisture_rate", 0.001, "IP"), 0.001 * 7936.6414, tol=1e-3)


# ── Altitude ────────────────────────────────────────────────────────────────────

def test_altitude_feet():
    # 1 ft = 0.3048 m exactly
    assert approx(u.from_si("altitude", 0.3048, "IP"), 1.0)
    assert approx(u.to_si("altitude", 1.0, "IP"), 0.3048)


def test_altitude_si_is_identity():
    assert approx(u.from_si("altitude", 250.0, "SI"), 250.0)


# ── Duct quantities ─────────────────────────────────────────────────────────────

def test_duct_flow_si_is_m3_per_s():
    # 3600 m3/h -> 1 m3/s exactly
    assert approx(u.from_si("duct_flow", 3600.0, "SI"), 1.0)
    assert approx(u.to_si("duct_flow", 1.0, "SI"), 3600.0)


def test_duct_flow_ip_matches_vol_flow_ip():
    # Same canonical value, same CFM factor as vol_flow's IP entry.
    assert approx(u.from_si("duct_flow", 1000.0, "IP"), u.from_si("vol_flow", 1000.0, "IP"))


def test_velocity_fpm():
    # 1 m/s = 196.8504 fpm
    assert approx(u.from_si("velocity", 1.0, "IP"), 196.8504, tol=1e-4)
    assert approx(u.to_si("velocity", 196.8504, "IP"), 1.0, tol=1e-4)


def test_duct_dimension_mm_and_inches():
    # 1 m -> 1000 mm; 0.0254 m -> 1 in exactly
    assert approx(u.from_si("duct_dimension", 1.0, "SI"), 1000.0)
    assert approx(u.from_si("duct_dimension", 0.0254, "IP"), 1.0)
    assert approx(u.to_si("duct_dimension", 1.0, "IP"), 0.0254)


def test_friction_rate_inwg_per_100ft():
    # 8.1723 Pa/m ~= 1 in.wg/100ft
    assert approx(u.from_si("friction_rate", 8.1723, "IP"), 1.0, tol=1e-3)
    assert approx(u.to_si("friction_rate", 1.0, "IP"), 8.1723, tol=1e-3)


def test_friction_rate_si_is_identity():
    assert approx(u.from_si("friction_rate", 1.5, "SI"), 1.5)


def test_velocity_pressure_si_is_identity_pascals():
    # Screenshot cross-check (Correction #2): V=4.43 m/s, rho=1.2 -> Pv=11.77 Pa.
    assert approx(u.from_si("velocity_pressure", 11.775, "SI"), 11.775)


def test_velocity_pressure_ip_is_inches_water_gauge():
    # Same conversion factor as friction_rate's in.wg leg, without the
    # per-100ft length normalisation -- 249.0889 Pa = 1 in.wg exactly.
    assert approx(u.from_si("velocity_pressure", 249.0889, "IP"), 1.0, tol=1e-6)
    assert approx(u.to_si("velocity_pressure", 1.0, "IP"), 249.0889, tol=1e-6)


# ── Duct run length (index-leg straight runs, Phase C) ──────────────────────────

def test_duct_run_length_si_is_identity_metres():
    assert approx(u.from_si("duct_run_length", 4.5, "SI"), 4.5)


def test_duct_run_length_ip_is_feet():
    # Same 0.3048 m/ft factor as "altitude", just a different display scale
    # (1 decimal, since a run is often e.g. 4.5 m / 14.8 ft, not whole metres).
    assert approx(u.from_si("duct_run_length", 1.0, "IP"), 1.0 / 0.3048, tol=1e-6)
    assert approx(u.to_si("duct_run_length", 1.0, "IP"), 0.3048, tol=1e-6)


def test_duct_run_length_distinct_quantity_from_duct_dimension():
    # Same canonical unit (metres) as duct_dimension, but a deliberately
    # different display quantity -- duct_dimension's SI leg is mm-scaled
    # (x1000), duct_run_length's is not, so they must not be interchangeable.
    assert u.symbol("duct_run_length", "SI") == "m"
    assert u.symbol("duct_dimension", "SI") == "mm"


# ── Round trips across every quantity/system ────────────────────────────────────

@pytest.mark.parametrize("quantity", list(u.UNITS.keys()))
@pytest.mark.parametrize("system", u.SYSTEMS)
def test_round_trip(quantity, system):
    for si in (0.5, 1.0, 12.34, 101.3):
        back = u.to_si(quantity, u.from_si(quantity, si, system), system)
        assert approx(back, si, tol=1e-9)


# ── Symbols & metadata ──────────────────────────────────────────────────────────

def test_symbols():
    assert u.symbol("temperature", "IP") == "°F"
    assert u.symbol("humidity_ratio", "IP") == "gr/lb"
    assert u.symbol("pressure", "IP") == "inHg"
    assert u.symbol("power", "IP") == "Btu/h"
    assert u.symbol("vol_flow", "SI") == "m³/h"


def test_unknown_quantity_and_system_raise():
    with pytest.raises(ValueError):
        u.symbol("torque", "SI")
    with pytest.raises(ValueError):
        u.symbol("temperature", "CGS")


def test_decimals_present_for_all():
    for quantity in u.UNITS:
        for system in u.SYSTEMS:
            assert isinstance(u.decimals(quantity, system), int)


def test_head_pressure_triplet_si():
    t = u.head_pressure_triplet(97_890.0, 998.2, "SI")
    assert t["parts"][0] == ("97890", "Pa")
    assert t["parts"][1][1] == "kPa"
    assert t["parts"][2][1] == "bar"
    assert "Pa" in t["summary"] and "bar" in t["summary"]


def test_head_pressure_triplet_ip():
    # 6894.757 Pa = 1 psi; density chosen so ft-fluid is well-defined.
    t = u.head_pressure_triplet(6894.757, 1000.0, "IP")
    assert t["parts"][0] == ("1.000", "psi")
    assert t["parts"][1][1] == "in.wg"
    assert t["parts"][2][1] == "ft fluid"
