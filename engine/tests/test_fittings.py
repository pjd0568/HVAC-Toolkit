"""Tests for hvac_engine.fittings -- the index-leg pressure-drop catalogue
(SPEC-duct-sizing.md, Phase C)."""

import math

import pytest

from hvac_engine import fittings as f


def approx(a, b, tol=1e-9):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


# ── Catalogue shape ──────────────────────────────────────────────────────────

def test_catalog_counts_match_spec():
    # 11 round-family + 8 rectangular-family = 19 total (SPEC-duct-sizing.md).
    round_fittings = [x for x in f.FITTINGS if x.family == f.ROUND_FAMILY]
    rect_fittings = [x for x in f.FITTINGS if x.family == f.RECTANGULAR_FAMILY]
    assert len(round_fittings) == 11
    assert len(rect_fittings) == 8
    assert len(f.FITTINGS) == 19


def test_all_keys_are_unique():
    keys = [x.key for x in f.FITTINGS]
    assert len(keys) == len(set(keys))


def test_fittings_by_key_matches_fittings_tuple():
    assert len(f.FITTINGS_BY_KEY) == len(f.FITTINGS)
    for fitting in f.FITTINGS:
        assert f.FITTINGS_BY_KEY[fitting.key] is fitting


def test_every_fitting_has_positive_k():
    for fitting in f.FITTINGS:
        assert fitting.k > 0


def test_every_fitting_has_a_thumbnail_key():
    for fitting in f.FITTINGS:
        assert fitting.thumbnail_key


# ── fittings_for_shape ───────────────────────────────────────────────────────

def test_fittings_for_shape_circular_is_round_family():
    result = f.fittings_for_shape("circular")
    assert result == f._ROUND_FITTINGS
    assert all(x.family == f.ROUND_FAMILY for x in result)


def test_fittings_for_shape_flat_oval_is_also_round_family():
    # Flat oval is handled via its round-duct equivalent diameter throughout
    # this app (see hvac_engine.duct) -- same fitting set as circular.
    assert f.fittings_for_shape("flat_oval") == f.fittings_for_shape("circular")


def test_fittings_for_shape_rectangular_is_rectangular_family():
    result = f.fittings_for_shape("rectangular")
    assert result == f._RECTANGULAR_FITTINGS
    assert all(x.family == f.RECTANGULAR_FAMILY for x in result)


def test_fittings_for_shape_rejects_unknown_shape():
    with pytest.raises(ValueError):
        f.fittings_for_shape("triangular")


# ── fitting_pressure_drop ────────────────────────────────────────────────────

def test_fitting_pressure_drop_is_k_times_velocity_pressure():
    assert approx(f.fitting_pressure_drop(0.22, 11.775), 0.22 * 11.775)


def test_fitting_pressure_drop_zero_k_is_zero_drop():
    assert f.fitting_pressure_drop(0.0, 50.0) == 0.0


# ── straight_pressure_drop ───────────────────────────────────────────────────

def test_straight_pressure_drop_is_length_times_friction_rate():
    assert approx(f.straight_pressure_drop(4.5, 1.2), 4.5 * 1.2)


def test_straight_pressure_drop_rejects_zero_length():
    with pytest.raises(ValueError):
        f.straight_pressure_drop(0.0, 1.2)


def test_straight_pressure_drop_rejects_negative_length():
    with pytest.raises(ValueError):
        f.straight_pressure_drop(-2.0, 1.2)


# ── accessory_pressure_drop (direct-entry items: louvers, attenuators, ─────
# VCD/FD dampers, single-blade dampers, grilles -- no standard K-factor,
# Paul's explicit call: "for custom items we add the pressure drop directly")

def test_accessory_pressure_drop_is_identity():
    assert f.accessory_pressure_drop(15.0) == 15.0


def test_accessory_pressure_drop_allows_zero():
    assert f.accessory_pressure_drop(0.0) == 0.0


def test_accessory_pressure_drop_rejects_negative():
    with pytest.raises(ValueError):
        f.accessory_pressure_drop(-5.0)


# ── Specific K-factor spot checks (against SPEC-duct-sizing.md's tables) ────

@pytest.mark.parametrize(
    "key,expected_k",
    [
        ("round_elbow_90_smooth_r1.5", 0.22),
        ("round_elbow_90_smooth_r1.0", 0.33),
        ("round_elbow_90_mitred", 1.20),
        ("round_elbow_45_smooth", 0.15),
        ("round_tee_branch_90", 1.00),
        ("round_tee_straight", 0.15),
        ("round_reducer_gradual", 0.05),
        ("round_enlarger_gradual", 0.20),
        ("round_damper_open", 0.20),
        ("round_entry_sharp", 0.50),
        ("round_exit", 1.00),
        ("rect_elbow_90_mitred_no_vanes", 1.30),
        ("rect_elbow_90_mitred_vanes", 0.40),
        ("rect_elbow_90_radiused", 0.25),
        ("rect_tee_branch_90", 1.00),
        ("rect_tee_straight", 0.15),
        ("rect_transition_contraction", 0.05),
        ("rect_transition_expansion", 0.20),
        ("rect_damper_open", 0.25),
    ],
)
def test_spot_check_k_factors(key, expected_k):
    assert approx(f.FITTINGS_BY_KEY[key].k, expected_k)
