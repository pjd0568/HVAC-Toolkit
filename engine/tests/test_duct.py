"""Tests for hvac_engine.duct (SPEC-duct-sizing.md, Phase A: core sizing).

No primary-source worked example was available to check against in this
session (unlike psychrometrics' ASHRAE HOF Table 3 anchors) — see the spec's
acceptance-tests section. These tests verify internal consistency (round
trips across every "any two variables" combination), sanity bounds against
well-known Moody-chart behaviour, and algebraic properties of the closed-form
inverses, rather than published numeric anchors.
"""

import math

import pytest

from hvac_engine import duct as d


def approx(a, b, tol=1e-6, atol=1e-9):
    return math.isclose(a, b, rel_tol=tol, abs_tol=atol)


# ── Circular: velocity / friction rate basics ───────────────────────────────────

def test_velocity_circular_basic():
    # 1 m3/s (3600 m3/h) through a 400mm duct: A = pi*0.2^2 = 0.12566 m2
    v = d.velocity_circular(3600.0, 0.4)
    assert approx(v, 1.0 / (math.pi * 0.2 ** 2), tol=1e-6)


def test_friction_rate_circular_positive_and_consistent():
    dp_dl, v, re, f = d.friction_rate_circular(3600.0, 0.4)
    assert dp_dl > 0
    assert approx(v, d.velocity_circular(3600.0, 0.4))
    assert re > 0
    assert f > 0


def test_friction_factor_moody_sanity_bound():
    # Re ~ 1e5, eps/D ~ 2e-4 (0.09mm roughness / ~450mm duct): smooth-pipe
    # turbulent regime, Moody-chart f in roughly 0.017-0.021.
    f = d._swamee_jain(1.0e5, 0.00009, 0.45)
    assert 0.015 < f < 0.022


def test_laminar_fallback():
    # Not a realistic HVAC condition, but the function should stay well
    # behaved (f = 64/Re) rather than raising or going negative.
    f = d._swamee_jain(1000.0, 0.00009, 0.4)
    assert approx(f, 64.0 / 1000.0)


def test_zero_or_negative_reynolds_returns_zero():
    assert d._swamee_jain(0.0, 0.00009, 0.4) == 0.0
    assert d._swamee_jain(-5.0, 0.00009, 0.4) == 0.0


# ── Circular: size_circular "any two variables" round trip ─────────────────────

def test_size_circular_requires_exactly_two():
    with pytest.raises(ValueError):
        d.size_circular(volume=3600.0)
    with pytest.raises(ValueError):
        d.size_circular(volume=3600.0, velocity=6.0, diameter=0.4)


@pytest.mark.parametrize("volume,diameter", [(3600.0, 0.4), (1800.0, 0.25), (7200.0, 0.63)])
def test_size_circular_round_trip_all_combinations(volume, diameter):
    base = d.size_circular(volume=volume, diameter=diameter)

    combos = [
        dict(volume=base.volume, velocity=base.velocity),
        dict(volume=base.volume, friction_rate=base.friction_rate),
        dict(velocity=base.velocity, diameter=base.diameter),
        dict(velocity=base.velocity, friction_rate=base.friction_rate),
        dict(diameter=base.diameter, friction_rate=base.friction_rate),
    ]
    for combo in combos:
        result = d.size_circular(**combo)
        assert approx(result.volume, base.volume, tol=1e-4), combo
        assert approx(result.diameter, base.diameter, tol=1e-5), combo
        assert approx(result.velocity, base.velocity, tol=1e-4), combo
        assert approx(result.friction_rate, base.friction_rate, tol=1e-4), combo


def test_size_circular_unreachable_target_raises():
    # At 3600 m3/h, friction rate ranges from ~9.5e-5 Pa/m (at the 3000mm
    # search-range ceiling) to ~9e6 Pa/m (at the 20mm floor) -- a target
    # below that minimum is unreachable within the search range and should
    # raise, not silently return a nonsense diameter.
    with pytest.raises(ValueError):
        d.size_circular(volume=3600.0, friction_rate=1e-8)


def test_size_circular_rejects_zero_or_negative_values():
    # Real bug caught in web-layer verification: volume=0 with a velocity
    # target used to reach sqrt(0) = 0 diameter, then a ZeroDivisionError
    # deep in friction_rate_circular, instead of a clean ValueError. Guard
    # every "known" value up front instead of letting bad math surface as a
    # crash several calls later.
    with pytest.raises(ValueError):
        d.size_circular(volume=0.0, velocity=6.0)
    with pytest.raises(ValueError):
        d.size_circular(volume=-100.0, velocity=6.0)
    with pytest.raises(ValueError):
        d.size_circular(volume=3600.0, velocity=0.0)
    with pytest.raises(ValueError):
        d.size_circular(volume=3600.0, diameter=-0.1)
    with pytest.raises(ValueError):
        d.size_circular(volume=3600.0, friction_rate=0.0)


def test_size_rectangular_and_flat_oval_reject_zero_volume():
    with pytest.raises(ValueError):
        d.size_rectangular(0.0, 0.4, 0.2)
    with pytest.raises(ValueError):
        d.size_flat_oval(0.0, 0.5, 0.2)


def test_size_rectangular_rejects_zero_or_negative_dimensions():
    # Real bug caught in web-layer verification for Correction #4: with
    # rectangular width/height now free-entry fields, a literal "0" typed by
    # the user is a truthy string in the blueprint's `if width_raw:` check,
    # so it reaches size_rectangular directly (rather than falling back to a
    # derived default) -- previously this hit a bare ZeroDivisionError in the
    # velocity calc, before equivalent_diameter_rectangular's own positivity
    # check was ever reached. Guarded up front, same pattern as
    # size_circular's zero/negative guard above.
    with pytest.raises(ValueError):
        d.size_rectangular(3600.0, 0.0, 0.3)
    with pytest.raises(ValueError):
        d.size_rectangular(3600.0, 0.4, 0.0)
    with pytest.raises(ValueError):
        d.size_rectangular(3600.0, -0.1, 0.3)


def test_size_flat_oval_rejects_zero_minor_or_major_less_than_minor():
    # Same class of bug as rectangular above: minor=0 reached
    # _flat_oval_area() (giving area=0) before
    # equivalent_diameter_flat_oval()'s own check on minor_m<=0 was reached,
    # so the velocity division crashed with ZeroDivisionError instead of a
    # clean ValueError.
    with pytest.raises(ValueError):
        d.size_flat_oval(3600.0, 0.5, 0.0)
    with pytest.raises(ValueError):
        d.size_flat_oval(3600.0, 0.2, 0.3)  # major < minor


def test_propose_functions_reject_zero_volume():
    # propose_* all route through size_circular first, so the guard above
    # should already cover them -- confirm end to end, since this is exactly
    # the call path the web layer's default-volume bug hit.
    with pytest.raises(ValueError):
        d.propose_circular(0.0, velocity=6.0)
    with pytest.raises(ValueError):
        d.propose_rectangular(0.0, aspect_ratio=2.0, velocity=6.0)
    with pytest.raises(ValueError):
        d.propose_flat_oval(0.0, minor_m=0.2, velocity=6.0)


# ── Circular: standard-size snapping ────────────────────────────────────────────

def test_snap_to_standard_diameter_rounds_up():
    assert d.snap_to_standard_diameter(0.37) == 0.4  # 370mm -> 400mm (next size up)
    assert d.snap_to_standard_diameter(0.4) == 0.4    # already a standard size


def test_snap_never_undersizes():
    for raw_mm in (61, 99, 199, 999):
        snapped_mm = d.snap_to_standard_diameter(raw_mm / 1000.0) * 1000.0
        assert snapped_mm >= raw_mm - 1e-6


def test_propose_circular_snaps_and_reresolves():
    result = d.propose_circular(3600.0, velocity=6.0, snap=True)
    assert result.diameter * 1000.0 in d.STANDARD_DIAMETERS_MM
    # Re-resolved at the snapped size, so velocity/friction rate must be
    # internally consistent with that diameter, not the unsnapped target.
    check = d.size_circular(volume=3600.0, diameter=result.diameter)
    assert approx(result.velocity, check.velocity)
    assert approx(result.friction_rate, check.friction_rate)


def test_propose_circular_requires_exactly_one_target():
    with pytest.raises(ValueError):
        d.propose_circular(3600.0)
    with pytest.raises(ValueError):
        d.propose_circular(3600.0, velocity=6.0, friction_rate=1.0)


# ── Rectangular ──────────────────────────────────────────────────────────────

def test_equivalent_diameter_rectangular_differs_from_equal_area():
    # Confirms the implementation is the Huebscher equal-friction/capacity
    # correlation, not the simpler equal-area circular diameter (they are
    # deliberately different quantities for a non-square duct).
    de_huebscher = d.equivalent_diameter_rectangular(0.4, 0.2)
    de_equal_area = math.sqrt(4 * 0.4 * 0.2 / math.pi)
    assert not approx(de_huebscher, de_equal_area, tol=1e-3)


@pytest.mark.parametrize("width,height", [(0.4, 0.2), (0.6, 0.15), (0.3, 0.3), (1.0, 0.25)])
def test_rectangular_from_equivalent_diameter_is_true_inverse(width, height):
    de = d.equivalent_diameter_rectangular(width, height)
    aspect_ratio = width / height
    w2, h2 = d.rectangular_from_equivalent_diameter(de, aspect_ratio)
    assert approx(w2, width, tol=1e-6)
    assert approx(h2, height, tol=1e-6)


def test_rectangular_from_equivalent_diameter_rejects_bad_aspect_ratio():
    with pytest.raises(ValueError):
        d.rectangular_from_equivalent_diameter(0.4, 0.5)  # < 1.0


def test_size_rectangular_aspect_ratio_warning():
    ok = d.size_rectangular(3600.0, 0.6, 0.2)   # 3:1
    assert ok.aspect_ratio == pytest.approx(3.0)
    assert ok.aspect_ratio_warning is False

    bad = d.size_rectangular(3600.0, 0.9, 0.2)  # 4.5:1
    assert bad.aspect_ratio_warning is True


def test_size_rectangular_friction_rate_uses_equivalent_diameter_not_actual_velocity():
    # The friction rate must match a round duct of the SAME diameter carrying
    # the SAME flow -- not a hydraulic-diameter substitution using the actual
    # rectangular velocity (a common implementation mistake this guards against).
    res = d.size_rectangular(3600.0, 0.4, 0.2)
    expected_dp_dl, _, _, _ = d.friction_rate_circular(3600.0, res.equivalent_diameter)
    assert approx(res.friction_rate, expected_dp_dl)


def test_propose_rectangular_actual_velocity_is_lower_than_round_target():
    # Documented ductulator-method property: the target velocity picks the
    # round-duct equivalent; the real rectangular velocity comes out lower
    # for a non-square aspect ratio.
    result = d.propose_rectangular(3600.0, aspect_ratio=2.0, velocity=6.0)
    assert result.velocity < 6.0


# ── Flat oval ────────────────────────────────────────────────────────────────

def test_flat_oval_degenerate_case_is_close_to_a_circle():
    # major == minor is a true circle; the correlation isn't derived to be
    # asymptotically exact there (it's fit over the flat-oval product range),
    # so this is a sanity bound, not exact equality -- see SPEC-duct-sizing.md.
    de = d.equivalent_diameter_flat_oval(0.3, 0.3)
    assert approx(de, 0.3, tol=0.01)


def test_flat_oval_rejects_major_less_than_minor():
    with pytest.raises(ValueError):
        d.equivalent_diameter_flat_oval(0.2, 0.3)


def test_equivalent_diameter_flat_oval_ashrae_hey_t_diaz_worked_example():
    """ASHRAE HOF Ch.21 / Heyt & Diaz (1975): De = 1.55·A^0.625/P^0.25.

    Worked example: 24 in × 12 in flat oval (major × minor).
    A = π·12²/4 + 12·(24−12) = 257.097 in²
    P = π·12 + 2·(24−12) = 61.699 in
    De = 1.55 · A^0.625 / P^0.25 ≈ 17.745 in
    """
    major_m = 24 * 0.0254
    minor_m = 12 * 0.0254
    de_m = d.equivalent_diameter_flat_oval(major_m, minor_m)
    de_in = de_m / 0.0254
    assert approx(de_in, 17.745, tol=0.01)


def test_size_flat_oval_area_and_velocity():
    major, minor = 0.5, 0.2
    res = d.size_flat_oval(3600.0, major, minor)
    expected_area = minor * (major - minor) + (math.pi / 4.0) * minor ** 2
    assert approx(res.velocity, (3600.0 / 3600.0) / expected_area, tol=1e-6)


def test_propose_flat_oval_matches_equivalent_diameter_target():
    result = d.propose_flat_oval(3600.0, minor_m=0.2, friction_rate=1.0)
    circ = d.size_circular(volume=3600.0, friction_rate=1.0)
    assert approx(result.equivalent_diameter, circ.diameter, tol=1e-4)


# ── Shared helpers ───────────────────────────────────────────────────────────

def test_snap_to_increment_rounds_up_to_25mm():
    assert approx(d.snap_to_increment(0.313), 0.325)
    assert approx(d.snap_to_increment(0.300), 0.300)  # already on the grid


def test_snap_to_increment_custom_step():
    assert approx(d.snap_to_increment(0.301, increment_mm=50.0), 0.350)


def test_round_to_increment_rounds_to_nearest_not_always_up():
    # 0.313 is closer to 0.325 than 0.300 -> rounds up here, but the point is
    # it's nearest, not always-up like snap_to_increment.
    assert approx(d.round_to_increment(0.313), 0.325)
    # 0.310 is closer to 0.300 than 0.325 -> rounds DOWN, unlike snap_to_increment
    # (which would round 0.310 up to 0.325).
    assert approx(d.round_to_increment(0.310), 0.300)
    assert approx(d.snap_to_increment(0.310), 0.325)  # confirms the two differ


def test_round_to_increment_exact_multiple_unchanged():
    assert approx(d.round_to_increment(0.300), 0.300)


def test_round_to_increment_custom_step():
    assert approx(d.round_to_increment(0.301, increment_mm=50.0), 0.300)
    assert approx(d.round_to_increment(0.326, increment_mm=50.0), 0.350)


@pytest.mark.parametrize("value,limit,expected", [
    (6.0, 8.0, "green"),
    (7.0, 8.0, "amber"),   # 0.875 -> >= 0.85 amber band
    (8.0, 8.0, "red"),
    (9.0, 8.0, "red"),
])
def test_status_bands(value, limit, expected):
    assert d.status(value, limit) == expected


# ── Lindab catalogue data (real manufacturer data, Correction #2) ───────────────
# Source: Paul's own Support/Duct_Standard_Sizes_Meters.xlsx (Lindab Big Blue
# Book of Ventilation extract). Third-party published data, no clean-room
# concern -- see CLAUDE.md.

def test_lindab_circular_catalog_count_and_order():
    assert len(d.LINDAB_CIRCULAR_CATALOG) == 29
    mms = [c.mm for c in d.LINDAB_CIRCULAR_CATALOG]
    assert mms == sorted(mms)  # strictly ascending, as tabulated
    assert mms[0] == 63
    assert mms[-1] == 1600


def test_standard_diameters_mm_derived_from_catalog():
    assert d.STANDARD_DIAMETERS_MM == tuple(c.mm for c in d.LINDAB_CIRCULAR_CATALOG)


def test_lindab_circular_catalog_special_order_flags():
    # A handful of known special-order-only sizes from the source spreadsheet.
    by_mm = {c.mm: c for c in d.LINDAB_CIRCULAR_CATALOG}
    assert by_mm[180].standard is False
    assert by_mm[224].standard is False
    assert by_mm[280].standard is False
    assert by_mm[600].standard is False
    # And a few confirmed-standard sizes either side of those.
    assert by_mm[160].standard is True
    assert by_mm[200].standard is True
    assert by_mm[630].standard is True


def test_lindab_flat_oval_catalog_count():
    assert len(d.LINDAB_FLAT_OVAL_CATALOG) == 19
    assert d.LINDAB_FLAT_OVAL_CATALOG[0] == d.FlatOvalCatalogSize(250, 100)
    assert d.LINDAB_FLAT_OVAL_CATALOG[-1] == d.FlatOvalCatalogSize(1000, 300)


def test_snap_flat_oval_to_catalog_never_undersizes():
    for target in (0.1, 0.2, 0.35, 0.45, 0.55):
        chosen = d.snap_flat_oval_to_catalog(target)
        de = d.equivalent_diameter_flat_oval(chosen.major_mm / 1000.0, chosen.minor_mm / 1000.0)
        assert de >= target - 1e-9


def test_snap_flat_oval_to_catalog_picks_nearest_above_not_just_any_qualifying_size():
    chosen = d.snap_flat_oval_to_catalog(0.35)
    de_chosen = d.equivalent_diameter_flat_oval(chosen.major_mm / 1000.0, chosen.minor_mm / 1000.0)
    for c in d.LINDAB_FLAT_OVAL_CATALOG:
        de = d.equivalent_diameter_flat_oval(c.major_mm / 1000.0, c.minor_mm / 1000.0)
        if de >= 0.35 - 1e-9:
            assert de >= de_chosen - 1e-9  # nothing smaller also qualifies


def test_snap_flat_oval_to_catalog_beyond_largest_returns_largest():
    chosen = d.snap_flat_oval_to_catalog(10.0)
    assert chosen == d.FlatOvalCatalogSize(1000, 300)


# ── Flat-oval catalogue-locked stepping (Correction #5) ──────────────────────────
# Backs the "major and minor move independently, but only through real
# stocked sizes -- never an unstocked combination" rectangular-style
# workflow for flat oval, applied against LINDAB_FLAT_OVAL_CATALOG's actual
# (sparse) major/minor pairing.

def test_flat_oval_catalog_majors_sorted_and_distinct():
    assert d.flat_oval_catalog_majors() == (250, 300, 400, 500, 600, 700, 800, 900, 1000)


def test_flat_oval_catalog_minors_for_major_matches_real_pairings():
    # Real gaps in the catalogue: 900 and 1000mm majors only ship with a
    # 300mm minor; 600 and 700mm each offer three minors.
    assert d.flat_oval_catalog_minors_for_major(600) == (200, 250, 300)
    assert d.flat_oval_catalog_minors_for_major(700) == (200, 250, 300)
    assert d.flat_oval_catalog_minors_for_major(900) == (300,)
    assert d.flat_oval_catalog_minors_for_major(1000) == (300,)
    assert d.flat_oval_catalog_minors_for_major(250) == (100,)


def test_flat_oval_catalog_minors_for_major_unknown_major_is_empty():
    assert d.flat_oval_catalog_minors_for_major(350) == ()


def test_flat_oval_nearest_catalog_major():
    assert d.flat_oval_nearest_catalog_major(620) == 600   # closer to 600 than 700
    assert d.flat_oval_nearest_catalog_major(680) == 700   # closer to 700 than 600
    assert d.flat_oval_nearest_catalog_major(1500) == 1000  # clamps at the largest
    assert d.flat_oval_nearest_catalog_major(10) == 250     # clamps at the smallest


def test_flat_oval_nearest_minor_for_major():
    assert d.flat_oval_nearest_minor_for_major(600, 220) == 200  # closer to 200 than 250
    assert d.flat_oval_nearest_minor_for_major(600, 240) == 250  # closer to 250 than 200
    assert d.flat_oval_nearest_minor_for_major(900, 100) == 300  # only option, whatever the target


def test_flat_oval_nearest_minor_for_major_rejects_unknown_major():
    with pytest.raises(ValueError):
        d.flat_oval_nearest_minor_for_major(350, 100)


def test_flat_oval_step_major_moves_through_catalog_and_clamps():
    assert d.flat_oval_step_major(600, 1) == 700
    assert d.flat_oval_step_major(600, -1) == 500
    assert d.flat_oval_step_major(250, -1) == 250   # clamped at the smallest
    assert d.flat_oval_step_major(1000, 1) == 1000  # clamped at the largest


def test_flat_oval_step_major_from_a_non_exact_value_snaps_first():
    # 620 isn't a catalogued major; steps from its NEAREST position (600).
    assert d.flat_oval_step_major(620, 1) == 700


def test_flat_oval_step_minor_moves_through_current_majors_list_and_clamps():
    assert d.flat_oval_step_minor(600, 200, 1) == 250
    assert d.flat_oval_step_minor(600, 300, 1) == 300   # clamped at the largest
    assert d.flat_oval_step_minor(600, 200, -1) == 200  # clamped at the smallest
    assert d.flat_oval_step_minor(900, 300, 1) == 300   # only one option either way


def test_flat_oval_step_minor_is_independent_of_major():
    # Stepping minor never changes major -- confirmed by checking the
    # returned value is still drawn from major 600's own minor list.
    stepped = d.flat_oval_step_minor(600, 200, 1)
    assert stepped in d.flat_oval_catalog_minors_for_major(600)


def test_flat_oval_step_minor_rejects_unknown_major():
    with pytest.raises(ValueError):
        d.flat_oval_step_minor(350, 100, 1)


def test_flat_oval_stepping_never_produces_an_unstocked_combination():
    # End-to-end guarantee: starting from every real catalogue entry, every
    # major-step and minor-step in both directions must land on another
    # genuine catalogue pair.
    catalog_pairs = {(c.major_mm, c.minor_mm) for c in d.LINDAB_FLAT_OVAL_CATALOG}
    for major, minor in catalog_pairs:
        for direction in (1, -1):
            new_major = d.flat_oval_step_major(major, direction)
            new_minor = d.flat_oval_nearest_minor_for_major(new_major, minor)
            assert (new_major, new_minor) in catalog_pairs

            new_minor2 = d.flat_oval_step_minor(major, minor, direction)
            assert (major, new_minor2) in catalog_pairs


# ── Velocity pressure (Correction #2) ────────────────────────────────────────────

def test_velocity_pressure_matches_screenshot_worked_example():
    # Cross-checked against Paul's own reference VB calculator screenshot:
    # V=4.43 m/s, rho=1.2 kg/m3 -> Pv=11.77 Pa.
    assert approx(d.velocity_pressure(4.43, rho=1.2), 11.77, tol=1e-3)


def test_velocity_pressure_default_rho_is_rho_std():
    assert approx(d.velocity_pressure(4.43), d.velocity_pressure(4.43, rho=d.RHO_STD))


def test_velocity_pressure_scales_with_velocity_squared():
    assert approx(d.velocity_pressure(2.0) * 4.0, d.velocity_pressure(4.0))


# ── Cross-shape equivalence solvers (Correction #2) ──────────────────────────────
# These back the "nudge width/height/major/minor, the other dimension adjusts
# to hold the same equivalent diameter (friction rate)" live-update workflow.

@pytest.mark.parametrize("width,target_de", [(0.3, 0.35), (0.5, 0.4), (0.2, 0.25)])
def test_rectangular_other_side_round_trip(width, target_de):
    height = d.rectangular_other_side(target_de, width)
    de = d.equivalent_diameter_rectangular(width, height)
    assert approx(de, target_de, tol=1e-6)


def test_rectangular_other_side_is_symmetric_in_which_side_is_known():
    # Fixing width and solving for height, or fixing that same height and
    # solving for width, must recover the original width -- the Huebscher
    # relation is symmetric in the two sides.
    width, height = 0.4, 0.25
    de = d.equivalent_diameter_rectangular(width, height)
    solved_height = d.rectangular_other_side(de, width)
    assert approx(solved_height, height, tol=1e-6)
    solved_width = d.rectangular_other_side(de, height)
    assert approx(solved_width, width, tol=1e-6)


def test_rectangular_other_side_rejects_non_positive_known_side():
    with pytest.raises(ValueError):
        d.rectangular_other_side(0.3, 0.0)
    with pytest.raises(ValueError):
        d.rectangular_other_side(0.3, -0.1)


@pytest.mark.parametrize("major,target_de", [(0.6, 0.4), (0.8, 0.5), (0.5, 0.35)])
def test_flat_oval_minor_for_de_round_trip(major, target_de):
    minor = d.flat_oval_minor_for_de(target_de, major)
    de = d.equivalent_diameter_flat_oval(major, minor)
    assert approx(de, target_de, tol=1e-6)


def test_flat_oval_minor_for_de_stays_within_valid_range():
    # minor must stay in (0, major] for a valid flat-oval shape.
    minor = d.flat_oval_minor_for_de(0.4, 0.6)
    assert 0.0 < minor < 0.6


@pytest.mark.parametrize("minor,target_de", [(0.2, 0.3), (0.25, 0.4), (0.15, 0.25)])
def test_flat_oval_major_for_de_round_trip(minor, target_de):
    major = d.flat_oval_major_for_de(target_de, minor)
    de = d.equivalent_diameter_flat_oval(major, minor)
    assert approx(de, target_de, tol=1e-6)


# ── Flex duct derate (index-leg rework) ──────────────────────────────────────

def test_apply_flex_derate_uses_default_multiplier():
    assert approx(d.apply_flex_derate(2.0), 2.0 * d.FLEX_DUCT_DERATE)


def test_apply_flex_derate_is_always_an_increase():
    # A flex run must never come out with a LOWER friction rate than the
    # rigid duct it's derated from -- that would silently understate a
    # flex section's real pressure drop.
    assert d.apply_flex_derate(1.5) > 1.5


def test_apply_flex_derate_custom_multiplier():
    assert approx(d.apply_flex_derate(2.0, derate=2.0), 4.0)
