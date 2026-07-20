"""Tests for hvac_engine.converter (SPEC-unit-converter.md)."""

import math

import pytest

from hvac_engine import converter as cv


def approx(a, b, tol=1e-6):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def _result(cr, unit_id):
    for r in cr.results:
        if r.unit_id == unit_id:
            return r
    raise AssertionError(f"{unit_id} not in results")


# ── convert_all shape ────────────────────────────────────────────────────────────

def test_convert_all_returns_every_unit():
    cr = cv.convert_all("length", 25.0, "mm")
    ids = {r.unit_id for r in cr.results}
    assert ids == {u.id for u in cv.CATEGORIES["length"].units}
    assert len(cr.results) == len(cv.CATEGORIES["length"].units)


def test_input_row_flagged_and_unchanged():
    cr = cv.convert_all("length", 25.0, "mm")
    src = _result(cr, "mm")
    assert src.is_input and approx(src.value, 25.0)
    assert src.notation == "entered value"
    assert sum(1 for r in cr.results if r.is_input) == 1


# ── Length (the worked example from the request) ─────────────────────────────────

def test_length_25mm_equivalents():
    cr = cv.convert_all("length", 25.0, "mm")
    assert approx(_result(cr, "cm").value, 2.5)
    assert approx(_result(cr, "in").value, 0.984251968504)
    assert approx(_result(cr, "m").value, 0.025)
    assert approx(_result(cr, "yd").value, 0.0273403762)
    assert approx(_result(cr, "mile").value, 1.5534e-5, tol=1e-4)


def test_length_notation_string():
    cr = cv.convert_all("length", 25.0, "mm")
    # 1 mm = 0.0393701 in
    assert _result(cr, "in").notation.startswith("1 mm = ")
    assert "in" in _result(cr, "in").notation


# ── Temperature (affine + formula notation) ──────────────────────────────────────

def test_temperature_values():
    cr = cv.convert_all("temperature", 25.0, "degC")
    assert approx(_result(cr, "degF").value, 77.0)
    assert approx(_result(cr, "K").value, 298.15)
    assert approx(_result(cr, "degR").value, 536.67)


def test_temperature_formula_notation():
    cr = cv.convert_all("temperature", 25.0, "degC")
    assert _result(cr, "degF").notation == "°F = °C × 9/5 + 32"
    assert _result(cr, "K").notation == "K = °C + 273.15"


def test_temperature_from_fahrenheit():
    cr = cv.convert_all("temperature", 98.6, "degF")
    assert approx(_result(cr, "degC").value, 37.0)
    assert _result(cr, "degC").notation == "°C = (°F − 32) × 5/9"


def test_absolute_zero_warning():
    cr = cv.convert_all("temperature", -300.0, "degC")  # below 0 K
    assert cr.warning is not None
    cr2 = cv.convert_all("temperature", 20.0, "degC")
    assert cr2.warning is None


# ── Spot checks across categories ────────────────────────────────────────────────

def test_pressure_known():
    cr = cv.convert_all("pressure", 1.0, "atm")
    assert approx(_result(cr, "kPa").value, 101.325)
    assert approx(_result(cr, "psi").value, 14.6959, tol=1e-4)
    assert approx(_result(cr, "inHg").value, 29.9213, tol=1e-4)


def test_power_known():
    cr = cv.convert_all("power", 1.0, "kW")
    assert approx(_result(cr, "btuh").value, 3412.14, tol=1e-4)
    assert approx(_result(cr, "hp").value, 1.34102, tol=1e-4)
    assert approx(_result(cr, "tonref").value, 0.284345, tol=1e-4)


def test_energy_kwh_to_btu():
    cr = cv.convert_all("energy", 1.0, "kWh")
    assert approx(_result(cr, "Btu").value, 3412.14, tol=1e-4)
    assert approx(_result(cr, "MJ").value, 3.6)


def test_vol_flow_cfm_to_ls():
    cr = cv.convert_all("vol_flow", 1000.0, "cfm")
    assert approx(_result(cr, "ls").value, 471.947, tol=1e-4)
    assert approx(_result(cr, "m3h").value, 1699.01, tol=1e-4)


def test_humidity_ratio_grains():
    cr = cv.convert_all("humidity_ratio", 0.010, "kgkg")
    assert approx(_result(cr, "gkg").value, 10.0)
    assert approx(_result(cr, "grlb").value, 70.0)


def test_enthalpy_btu_per_lb():
    cr = cv.convert_all("enthalpy", 2326.0, "Jkg")
    assert approx(_result(cr, "Btulb").value, 1.0)


# ── Round trips for every linear category ────────────────────────────────────────

@pytest.mark.parametrize("cat", [c for c in cv.CATEGORIES.values() if c.kind == "linear"])
def test_round_trip_linear(cat):
    a = cat.units[0]
    b = cat.units[-1]
    cr = cv.convert_all(cat.id, 7.0, a.id)
    v_b = _result(cr, b.id).value
    cr2 = cv.convert_all(cat.id, v_b, b.id)
    assert approx(_result(cr2, a.id).value, 7.0, tol=1e-9)


# ── Catalog integrity ────────────────────────────────────────────────────────────

def test_unit_ids_unique_within_category():
    for cat in cv.CATEGORIES.values():
        ids = [u.id for u in cat.units]
        assert len(ids) == len(set(ids)), f"dup ids in {cat.id}"


def test_linear_base_unit_has_factor_one():
    for cat in cv.CATEGORIES.values():
        if cat.kind != "linear":
            continue
        assert any(approx(u.factor, 1.0) for u in cat.units), f"{cat.id} has no base unit"


def test_groups_are_known():
    for cat in cv.CATEGORIES.values():
        for u in cat.units:
            assert u.group in cv.GROUP_ORDER


def test_list_categories_matches():
    listed = dict(cv.list_categories())
    assert set(listed) == set(cv.CATEGORIES)
    assert listed["temperature"] == "Temperature"


def test_unknown_category_and_unit_raise():
    with pytest.raises(ValueError):
        cv.convert_all("mojo", 1.0, "x")
    with pytest.raises(ValueError):
        cv.convert_all("length", 1.0, "furlong")
