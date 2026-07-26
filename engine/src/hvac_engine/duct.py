"""Duct sizing — straight-duct friction loss, velocity and equivalent-diameter
calculations for circular, rectangular and flat oval duct.

Implemented from SPEC-duct-sizing.md, itself written from CIBSE Guide C
Section 4 and ASHRAE Handbook of Fundamentals Chapter 21 ("Duct Design")
only. No reference to any prior codebase — see the project's clean-room
rules. Pure Python, zero dependencies, no I/O — same "engine stays pure"
split as every other hvac_engine module (e.g. hvac_engine.climate).

Canonical SI units (matching the rest of hvac_engine):
    volume flow          m3/h   (matches hvac_engine.units' vol_flow convention)
    diameter/width/height/axis   m
    velocity              m/s
    friction rate          Pa/m
    density                kg/m3
    kinematic viscosity    m2/s

This module covers Phase A only (core sizing) — see SPEC-duct-sizing.md for
what's deliberately not here yet (site-adjusted air density, ceiling-void
constraint, fittings/K-factor catalogue, the interactive slider, PDF export).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, pi, sqrt

from hvac_engine.fluid_mechanics import swamee_jain

# ── Standard air (CIBSE Guide C "standard air": 20 degC, 101.325 kPa) ───────────
RHO_STD = 1.2       # kg/m3
NU_STD = 1.51e-5    # m2/s, kinematic viscosity of standard air

# Absolute roughness, galvanized steel duct (ASHRAE Fundamentals Ch.21 /
# CIBSE Guide C typical value). Function parameter, overridable per material.
ROUGHNESS_GALV_STEEL = 0.00009  # m (0.09 mm)

@dataclass(frozen=True)
class CatalogDiameter:
    """One entry in a real manufacturer circular duct size catalogue."""

    mm: int
    gauge_mm: float
    standard: bool  # False = special order only


# Real Lindab spiral duct (SR) diameters, gauges and stock/special-order
# status — extracted from Paul's own copy of the Lindab Big Blue Book of
# Ventilation (Support/Duct_Standard_Sizes_Meters.xlsx). This supersedes the
# earlier EN 1506/DW144 public-standard placeholder (see SPEC-duct-sizing.md)
# now that genuine manufacturer catalogue data is available — this is Lindab's
# own published product range, not proprietary Newsome data, so it carries no
# clean-room concern.
LINDAB_CIRCULAR_CATALOG: tuple[CatalogDiameter, ...] = (
    CatalogDiameter(63, 0.5, True),
    CatalogDiameter(80, 0.5, True),
    CatalogDiameter(100, 0.5, True),
    CatalogDiameter(125, 0.5, True),
    CatalogDiameter(150, 0.5, True),
    CatalogDiameter(160, 0.5, True),
    CatalogDiameter(180, 0.6, False),
    CatalogDiameter(200, 0.6, True),
    CatalogDiameter(224, 0.6, False),
    CatalogDiameter(250, 0.6, True),
    CatalogDiameter(280, 0.6, False),
    CatalogDiameter(300, 0.6, True),
    CatalogDiameter(315, 0.6, True),
    CatalogDiameter(355, 0.8, True),
    CatalogDiameter(400, 0.8, True),
    CatalogDiameter(450, 0.8, True),
    CatalogDiameter(500, 0.8, True),
    CatalogDiameter(560, 0.8, True),
    CatalogDiameter(600, 0.8, False),
    CatalogDiameter(630, 0.8, True),
    CatalogDiameter(710, 0.8, True),
    CatalogDiameter(800, 0.8, True),
    CatalogDiameter(900, 1.0, True),
    CatalogDiameter(1000, 1.0, True),
    CatalogDiameter(1120, 1.0, True),
    CatalogDiameter(1250, 1.0, True),
    CatalogDiameter(1422, 1.0, True),
    CatalogDiameter(1500, 1.0, True),
    CatalogDiameter(1600, 1.2, True),
)

# Backward-compatible flat list — snap_to_standard_diameter(), propose_circular()'s
# `snap` parameter, and the existing engine tests all key off this.
STANDARD_DIAMETERS_MM: tuple[int, ...] = tuple(c.mm for c in LINDAB_CIRCULAR_CATALOG)

MAX_ASPECT_RATIO = 4.0  # rectangular width:height warning threshold (source brief 2.3/3.3)

# Default "recommended" thresholds — a starting point, not a fixed rule (see
# SPEC-duct-sizing.md). Typical CIBSE Guide C low-velocity system guide values.
DEFAULT_MAX_VELOCITY = 8.0        # m/s
DEFAULT_MAX_FRICTION_RATE = 1.0   # Pa/m

# Solver search ranges.
_D_MIN, _D_MAX = 0.02, 3.0   # m -- 20 mm to 3000 mm
_V_MIN, _V_MAX = 0.1, 50.0   # m/s


# ── Friction factor / Darcy-Weisbach core ────────────────────────────────────────

# Back-compat alias — prefer hvac_engine.fluid_mechanics.swamee_jain.
_swamee_jain = swamee_jain


def _friction_rate_from_v_d(
    velocity_ms: float, diameter_m: float, rho: float, nu: float, roughness: float
) -> float:
    """Darcy-Weisbach pressure loss per unit length (Pa/m) from velocity and
    diameter directly."""
    reynolds = velocity_ms * diameter_m / nu
    f = swamee_jain(reynolds, roughness, diameter_m)
    return f * (1.0 / diameter_m) * (rho * velocity_ms ** 2 / 2.0)


def velocity_circular(volume_m3h: float, diameter_m: float) -> float:
    """Velocity (m/s) of a circular duct carrying the given flow."""
    area = pi * diameter_m ** 2 / 4.0
    return (volume_m3h / 3600.0) / area


def velocity_pressure(velocity_ms: float, rho: float = RHO_STD) -> float:
    """Velocity pressure (Pa): Pv = 0.5 * rho * V^2 -- the Bernoulli dynamic-
    pressure term, shown alongside friction rate in the sizing tools per the
    source brief's requested duct design parameters. Applies to any shape's
    own actual velocity, not just circular."""
    return 0.5 * rho * velocity_ms ** 2


def friction_rate_circular(
    volume_m3h: float,
    diameter_m: float,
    rho: float = RHO_STD,
    nu: float = NU_STD,
    roughness: float = ROUGHNESS_GALV_STEEL,
) -> tuple[float, float, float, float]:
    """Straight-duct friction rate for a circular duct.

    Returns (friction_rate_pa_per_m, velocity_ms, reynolds, friction_factor).
    """
    v = velocity_circular(volume_m3h, diameter_m)
    reynolds = v * diameter_m / nu
    f = _swamee_jain(reynolds, roughness, diameter_m)
    dp_dl = f * (1.0 / diameter_m) * (rho * v ** 2 / 2.0)
    return dp_dl, v, reynolds, f


# ── Generic monotonic bisection (used by the "any two variables" solvers) ───────

def _bisect(f, target: float, lo: float, hi: float, increasing: bool,
            tol: float = 1e-9, max_iter: int = 200) -> float:
    f_lo, f_hi = f(lo), f(hi)
    ok = (f_lo <= target <= f_hi) if increasing else (f_lo >= target >= f_hi)
    if not ok:
        raise ValueError(
            f"target {target!r} is not reachable in the search range "
            f"[{lo}, {hi}] (f(lo)={f_lo!r}, f(hi)={f_hi!r})"
        )
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = f(mid)
        if abs(f_mid - target) <= tol * max(1.0, abs(target)):
            return mid
        take_upper_half = (f_mid < target) if increasing else (f_mid > target)
        if take_upper_half:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ── Circular duct sizing ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class CircularResult:
    volume: float           # m3/h
    diameter: float         # m
    velocity: float         # m/s
    friction_rate: float    # Pa/m
    reynolds: float
    friction_factor: float


def size_circular(
    *,
    volume: float | None = None,
    velocity: float | None = None,
    diameter: float | None = None,
    friction_rate: float | None = None,
    rho: float = RHO_STD,
    nu: float = NU_STD,
    roughness: float = ROUGHNESS_GALV_STEEL,
) -> CircularResult:
    """Solve a circular duct given exactly two of the four keyword arguments.

    Volume and diameter are the true two degrees of freedom for a circular
    duct — every combination of two known variables is resolved to a
    (volume, diameter) pair first (directly, by closed form, or by
    bisection where the relationship isn't invertible in closed form), then
    velocity/friction_rate/Reynolds/friction-factor are all re-derived fresh
    from that pair, so every field in the result is mutually consistent.
    """
    given = {"volume": volume, "velocity": velocity, "diameter": diameter,
              "friction_rate": friction_rate}
    known = {k: v for k, v in given.items() if v is not None}
    if len(known) != 2:
        raise ValueError(
            "size_circular needs exactly two of: volume, velocity, diameter, "
            f"friction_rate (got {sorted(known)})"
        )
    non_positive = {k: v for k, v in known.items() if v <= 0}
    if non_positive:
        raise ValueError(
            f"{', '.join(non_positive)} must be greater than zero "
            f"(got {non_positive})"
        )
    keys = frozenset(known)

    if keys == {"volume", "diameter"}:
        q, d = volume, diameter
    elif keys == {"volume", "velocity"}:
        q = volume
        d = sqrt(4.0 * (q / 3600.0) / (pi * velocity))
    elif keys == {"volume", "friction_rate"}:
        q = volume
        d = _bisect(
            lambda x: friction_rate_circular(q, x, rho, nu, roughness)[0],
            friction_rate, _D_MIN, _D_MAX, increasing=False,
        )
    elif keys == {"velocity", "diameter"}:
        d = diameter
        q = velocity * (pi * d ** 2 / 4.0) * 3600.0
    elif keys == {"velocity", "friction_rate"}:
        v = velocity
        d = _bisect(
            lambda x: _friction_rate_from_v_d(v, x, rho, nu, roughness),
            friction_rate, _D_MIN, _D_MAX, increasing=False,
        )
        q = v * (pi * d ** 2 / 4.0) * 3600.0
    elif keys == {"diameter", "friction_rate"}:
        d = diameter
        v = _bisect(
            lambda x: _friction_rate_from_v_d(x, d, rho, nu, roughness),
            friction_rate, _V_MIN, _V_MAX, increasing=True,
        )
        q = v * (pi * d ** 2 / 4.0) * 3600.0
    else:  # pragma: no cover -- unreachable, all C(4,2)=6 pairs handled above
        raise ValueError(f"unsupported combination: {sorted(known)}")

    dp_dl, v, reynolds, f = friction_rate_circular(q, d, rho, nu, roughness)
    return CircularResult(volume=q, diameter=d, velocity=v, friction_rate=dp_dl,
                           reynolds=reynolds, friction_factor=f)


def snap_to_standard_diameter(diameter_m: float) -> float:
    """Nearest Lindab catalogue diameter at or above the given value (round
    up — never undersize a duct). See LINDAB_CIRCULAR_CATALOG for gauge and
    stock/special-order status per size."""
    d_mm = diameter_m * 1000.0
    for size in STANDARD_DIAMETERS_MM:
        if size >= d_mm - 1e-6:
            return size / 1000.0
    return STANDARD_DIAMETERS_MM[-1] / 1000.0  # beyond the largest catalogued size


def propose_circular(
    volume_m3h: float,
    velocity: float | None = None,
    friction_rate: float | None = None,
    snap: bool = True,
    rho: float = RHO_STD,
    nu: float = NU_STD,
    roughness: float = ROUGHNESS_GALV_STEEL,
) -> CircularResult:
    """Given a flow and a target velocity OR friction rate, propose a size.

    If ``snap`` (default), rounds up to the nearest standard diameter and
    re-resolves at that size, so the returned velocity/friction rate reflect
    the real, snapped duct rather than the unsnapped theoretical one.
    """
    if (velocity is None) == (friction_rate is None):
        raise ValueError("propose_circular needs exactly one of velocity or friction_rate")
    if velocity is not None:
        result = size_circular(volume=volume_m3h, velocity=velocity, rho=rho, nu=nu, roughness=roughness)
    else:
        result = size_circular(volume=volume_m3h, friction_rate=friction_rate, rho=rho, nu=nu, roughness=roughness)
    if not snap:
        return result
    snapped = snap_to_standard_diameter(result.diameter)
    return size_circular(volume=volume_m3h, diameter=snapped, rho=rho, nu=nu, roughness=roughness)


# ── Rectangular duct sizing ───────────────────────────────────────────────────

@dataclass(frozen=True)
class RectangularResult:
    volume: float                  # m3/h
    width: float                   # m
    height: float                  # m
    velocity: float                # m/s -- the actual rectangular-duct velocity
    equivalent_diameter: float     # m -- Huebscher equal-friction/capacity De
    friction_rate: float           # Pa/m -- at the round-duct equivalent, same flow
    aspect_ratio: float            # >= 1.0
    aspect_ratio_warning: bool


def equivalent_diameter_rectangular(width_m: float, height_m: float) -> float:
    """Huebscher equal-friction/equal-capacity equivalent diameter.

    De = 1.30 * (a*b)^0.625 / (a+b)^0.25   (ASHRAE Fundamentals Ch.21)
    """
    if width_m <= 0 or height_m <= 0:
        raise ValueError("width and height must be positive")
    a, b = width_m, height_m
    return 1.30 * (a * b) ** 0.625 / (a + b) ** 0.25


def rectangular_from_equivalent_diameter(de_m: float, aspect_ratio: float) -> tuple[float, float]:
    """Closed-form inverse of equivalent_diameter_rectangular for a chosen
    aspect ratio r = width/height (>= 1). See SPEC-duct-sizing.md for the
    derivation (the exponents on the width collapse to exactly 1, so this is
    a true closed form, not an approximation)."""
    if aspect_ratio < 1.0:
        raise ValueError("aspect_ratio must be >= 1.0 (width / height)")
    r = aspect_ratio
    width = de_m * r ** 0.625 * (1.0 + 1.0 / r) ** 0.25 / 1.30
    height = width / r
    return width, height


# Search range for rectangular_other_side()'s bisection -- 20mm to 5m, wide
# enough for any realistic HVAC duct side.
_SIDE_MIN, _SIDE_MAX = 0.02, 5.0


def rectangular_other_side(de_m: float, known_side_m: float) -> float:
    """Solve the OTHER rectangular side given one FIXED side and a target
    equivalent diameter -- "nudge width, height adjusts to maintain
    equivalence" (and the reverse: nudge height, width adjusts). The
    Huebscher relation is symmetric in width/height, so this one function
    serves both directions: call with the side you just changed as
    `known_side_m` and it returns the other one, holding the same De (the
    same friction-rate basis) rather than changing it -- equivalence here
    means picking a different aspect ratio at the *same* De, not a
    different De.
    """
    if known_side_m <= 0:
        raise ValueError(f"known_side must be greater than zero (got {known_side_m!r})")
    return _bisect(
        lambda x: equivalent_diameter_rectangular(known_side_m, x),
        de_m, _SIDE_MIN, _SIDE_MAX, increasing=True,
    )


def size_rectangular(
    volume_m3h: float,
    width_m: float,
    height_m: float,
    rho: float = RHO_STD,
    nu: float = NU_STD,
    roughness: float = ROUGHNESS_GALV_STEEL,
) -> RectangularResult:
    if volume_m3h <= 0:
        raise ValueError(f"volume must be greater than zero (got {volume_m3h!r})")
    if width_m <= 0 or height_m <= 0:
        raise ValueError(
            f"width and height must be greater than zero "
            f"(got width={width_m!r}, height={height_m!r})"
        )
    velocity = (volume_m3h / 3600.0) / (width_m * height_m)
    de = equivalent_diameter_rectangular(width_m, height_m)
    friction_rate, _, _, _ = friction_rate_circular(volume_m3h, de, rho, nu, roughness)
    ar = max(width_m, height_m) / min(width_m, height_m)
    return RectangularResult(
        volume=volume_m3h, width=width_m, height=height_m, velocity=velocity,
        equivalent_diameter=de, friction_rate=friction_rate,
        aspect_ratio=ar, aspect_ratio_warning=ar > MAX_ASPECT_RATIO,
    )


def propose_rectangular(
    volume_m3h: float,
    aspect_ratio: float,
    velocity: float | None = None,
    friction_rate: float | None = None,
    rho: float = RHO_STD,
    nu: float = NU_STD,
    roughness: float = ROUGHNESS_GALV_STEEL,
) -> RectangularResult:
    """Given a flow, a target velocity OR friction rate, and a chosen aspect
    ratio: find the round-duct equivalent diameter, convert to width x height
    at that aspect ratio, and re-resolve.

    Note: the target velocity here is the equivalent round-duct velocity used
    to pick the size -- the resulting *actual* rectangular velocity (in the
    returned RectangularResult) will normally come out lower, because the
    equal-friction rectangle usually has a larger cross-sectional area than
    its round equivalent. This is how the ductulator method works, not a bug.
    """
    if (velocity is None) == (friction_rate is None):
        raise ValueError("propose_rectangular needs exactly one of velocity or friction_rate")
    if velocity is not None:
        circ = size_circular(volume=volume_m3h, velocity=velocity, rho=rho, nu=nu, roughness=roughness)
    else:
        circ = size_circular(volume=volume_m3h, friction_rate=friction_rate, rho=rho, nu=nu, roughness=roughness)
    width, height = rectangular_from_equivalent_diameter(circ.diameter, aspect_ratio)
    return size_rectangular(volume_m3h, width, height, rho, nu, roughness)


# ── Flat oval duct sizing ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class FlatOvalResult:
    volume: float               # m3/h
    major: float                # m
    minor: float                # m
    velocity: float             # m/s -- actual flat-oval velocity
    equivalent_diameter: float  # m
    friction_rate: float        # Pa/m -- at the round-duct equivalent, same flow


def _flat_oval_area(major_m: float, minor_m: float) -> float:
    a, b = major_m, minor_m
    return b * (a - b) + (pi / 4.0) * b ** 2


def _flat_oval_perimeter(major_m: float, minor_m: float) -> float:
    a, b = major_m, minor_m
    return 2.0 * (a - b) + pi * b


def equivalent_diameter_flat_oval(major_m: float, minor_m: float) -> float:
    """Equal-friction/capacity equivalent diameter for flat oval duct.

    De = 1.55 · A^0.625 / P^0.25 — ASHRAE Handbook — Fundamentals, Chapter 21
    (Duct Design), circular equivalent of a flat oval duct for equal airflow,
    resistance and length; after Heyt and Diaz (1975). Area and perimeter use
    the stadium geometry in the same chapter:
    A = (π/4)·b² + b·(a − b),  P = π·b + 2·(a − b), with a = major, b = minor.
    """
    if minor_m <= 0 or major_m < minor_m:
        raise ValueError("major axis must be >= minor axis > 0")
    area = _flat_oval_area(major_m, minor_m)
    perimeter = _flat_oval_perimeter(major_m, minor_m)
    return 1.55 * area ** 0.625 / perimeter ** 0.25


def size_flat_oval(
    volume_m3h: float,
    major_m: float,
    minor_m: float,
    rho: float = RHO_STD,
    nu: float = NU_STD,
    roughness: float = ROUGHNESS_GALV_STEEL,
) -> FlatOvalResult:
    if volume_m3h <= 0:
        raise ValueError(f"volume must be greater than zero (got {volume_m3h!r})")
    if minor_m <= 0 or major_m < minor_m:
        raise ValueError(
            f"major axis must be >= minor axis > 0 "
            f"(got major={major_m!r}, minor={minor_m!r})"
        )
    area = _flat_oval_area(major_m, minor_m)
    velocity = (volume_m3h / 3600.0) / area
    de = equivalent_diameter_flat_oval(major_m, minor_m)
    friction_rate, _, _, _ = friction_rate_circular(volume_m3h, de, rho, nu, roughness)
    return FlatOvalResult(
        volume=volume_m3h, major=major_m, minor=minor_m, velocity=velocity,
        equivalent_diameter=de, friction_rate=friction_rate,
    )


def flat_oval_major_for_de(de_m: float, minor_m: float) -> float:
    """Solve the major axis for a fixed minor axis and target equivalent
    diameter (bisection -- equivalent_diameter_flat_oval isn't invertible in
    the major axis in closed form, unlike the rectangular case)."""
    return _bisect(
        lambda a: equivalent_diameter_flat_oval(a, minor_m),
        de_m, minor_m * 1.000001, minor_m * 20.0, increasing=True,
    )


def flat_oval_minor_for_de(de_m: float, major_m: float) -> float:
    """Solve the minor axis for a FIXED major axis and target equivalent
    diameter -- the reverse of flat_oval_major_for_de, for "nudge minor,
    major stays fixed, maintain equivalence". Minor ranges over (0, major];
    De is monotonically increasing in minor over that range (at minor=major
    the shape degenerates to a true circle, the upper bound on De for this
    major axis -- see the degenerate-case note on equivalent_diameter_flat_oval)."""
    return _bisect(
        lambda b: equivalent_diameter_flat_oval(major_m, b),
        de_m, major_m * 1e-4, major_m, increasing=True,
    )


def propose_flat_oval(
    volume_m3h: float,
    minor_m: float,
    velocity: float | None = None,
    friction_rate: float | None = None,
    rho: float = RHO_STD,
    nu: float = NU_STD,
    roughness: float = ROUGHNESS_GALV_STEEL,
) -> FlatOvalResult:
    """Given a flow, a fixed minor axis, and a target velocity OR friction
    rate: solve for the major axis via flat_oval_major_for_de."""
    if (velocity is None) == (friction_rate is None):
        raise ValueError("propose_flat_oval needs exactly one of velocity or friction_rate")
    if velocity is not None:
        circ = size_circular(volume=volume_m3h, velocity=velocity, rho=rho, nu=nu, roughness=roughness)
    else:
        circ = size_circular(volume=volume_m3h, friction_rate=friction_rate, rho=rho, nu=nu, roughness=roughness)
    major = flat_oval_major_for_de(circ.diameter, minor_m)
    return size_flat_oval(volume_m3h, major, minor_m, rho, nu, roughness)


@dataclass(frozen=True)
class FlatOvalCatalogSize:
    """One entry in a real manufacturer flat-oval duct size catalogue."""

    major_mm: int
    minor_mm: int


# Real Lindab flat-oval major/minor combinations, same source as
# LINDAB_CIRCULAR_CATALOG above (Support/Duct_Standard_Sizes_Meters.xlsx) --
# this closes the "no public standard series for flat oval" gap noted when
# this module was first built.
LINDAB_FLAT_OVAL_CATALOG: tuple[FlatOvalCatalogSize, ...] = (
    FlatOvalCatalogSize(250, 100),
    FlatOvalCatalogSize(300, 100),
    FlatOvalCatalogSize(400, 100),
    FlatOvalCatalogSize(300, 150),
    FlatOvalCatalogSize(400, 150),
    FlatOvalCatalogSize(500, 150),
    FlatOvalCatalogSize(400, 200),
    FlatOvalCatalogSize(500, 200),
    FlatOvalCatalogSize(600, 200),
    FlatOvalCatalogSize(700, 200),
    FlatOvalCatalogSize(500, 250),
    FlatOvalCatalogSize(600, 250),
    FlatOvalCatalogSize(700, 250),
    FlatOvalCatalogSize(800, 250),
    FlatOvalCatalogSize(600, 300),
    FlatOvalCatalogSize(700, 300),
    FlatOvalCatalogSize(800, 300),
    FlatOvalCatalogSize(900, 300),
    FlatOvalCatalogSize(1000, 300),
)


def snap_flat_oval_to_catalog(target_de_m: float) -> FlatOvalCatalogSize:
    """Nearest catalogue flat-oval combination whose equivalent diameter is
    at or above the target (round up -- never undersize a duct), ordered by
    each combination's own computed equivalent diameter."""
    scored = [
        (equivalent_diameter_flat_oval(c.major_mm / 1000.0, c.minor_mm / 1000.0), c)
        for c in LINDAB_FLAT_OVAL_CATALOG
    ]
    scored.sort(key=lambda pair: pair[0])
    for de, c in scored:
        if de >= target_de_m - 1e-9:
            return c
    return scored[-1][1]  # beyond the largest catalogued combination


# ── Flat-oval catalogue-locked major/minor stepping (Correction #5) ─────────────
# Unlike rectangular (real sheet metal, any width/height is fabricable), flat
# oval only exists in Lindab's actual catalogued major/minor pairs -- most
# majors only pair with a handful of minors (e.g. 900mm major only ships with
# a 300mm minor in LINDAB_FLAT_OVAL_CATALOG), so letting major and minor vary
# fully independently like rectangular would let a user land on a size Lindab
# doesn't make. These functions let major/minor still move independently (no
# more "nudge one, solve the other to hold equivalence") while guaranteeing
# every reachable pair is a genuine stocked combination.

def flat_oval_catalog_majors() -> tuple[int, ...]:
    """Sorted distinct major-axis sizes (mm) stocked across the whole
    catalogue -- the set of values the major-axis stepper moves through."""
    return tuple(sorted({c.major_mm for c in LINDAB_FLAT_OVAL_CATALOG}))


def flat_oval_catalog_minors_for_major(major_mm: int) -> tuple[int, ...]:
    """Sorted distinct minor-axis sizes (mm) stocked for one specific major
    axis -- the set of values the minor-axis stepper moves through once a
    major is chosen. Empty if major_mm isn't itself a catalogued major."""
    return tuple(sorted(c.minor_mm for c in LINDAB_FLAT_OVAL_CATALOG if c.major_mm == major_mm))


def flat_oval_nearest_catalog_major(target_major_mm: float) -> int:
    """Nearest stocked major-axis size to an arbitrary value (used to snap a
    typed/hand-edited major onto a real size)."""
    majors = flat_oval_catalog_majors()
    return min(majors, key=lambda m: abs(m - target_major_mm))


def flat_oval_nearest_minor_for_major(major_mm: int, target_minor_mm: float) -> int:
    """Nearest minor-axis size stocked for the given major (used both to snap
    a typed/hand-edited minor, and to re-validate the current minor whenever
    the major changes and the old minor may no longer be offered for it).
    `major_mm` is assumed to already be a genuine catalogued major -- callers
    normally run it through flat_oval_nearest_catalog_major() first."""
    minors = flat_oval_catalog_minors_for_major(major_mm)
    if not minors:
        raise ValueError(f"{major_mm!r}mm is not a catalogued flat-oval major axis")
    return min(minors, key=lambda m: abs(m - target_minor_mm))


def flat_oval_step_major(current_major_mm: int, direction: int) -> int:
    """Next (direction=+1) or previous (direction=-1) stocked major-axis
    size, clamped at the ends of the catalogue -- the major-axis stepper
    button's server-side logic. `current_major_mm` need not already be an
    exact catalogue value (nearest position is used as the starting point),
    so a stale/hand-edited value still steps sensibly."""
    majors = flat_oval_catalog_majors()
    nearest = flat_oval_nearest_catalog_major(current_major_mm)
    idx = majors.index(nearest)
    new_idx = max(0, min(len(majors) - 1, idx + direction))
    return majors[new_idx]


def flat_oval_step_minor(major_mm: int, current_minor_mm: int, direction: int) -> int:
    """Next (direction=+1) or previous (direction=-1) stocked minor-axis size
    for the given major, clamped at the ends of that major's own minor list
    -- the minor-axis stepper button's server-side logic. Independent of
    major: stepping minor never changes major_mm."""
    minors = flat_oval_catalog_minors_for_major(major_mm)
    if not minors:
        raise ValueError(f"{major_mm!r}mm is not a catalogued flat-oval major axis")
    nearest = flat_oval_nearest_minor_for_major(major_mm, current_minor_mm)
    idx = minors.index(nearest)
    new_idx = max(0, min(len(minors) - 1, idx + direction))
    return minors[new_idx]


# ── Shared helpers ─────────────────────────────────────────────────────────────

def snap_to_increment(dimension_m: float, increment_mm: float = 25.0) -> float:
    """Round a rectangular dimension up to the nearest increment (25 mm
    default — source brief's "lock to 25 mm increments" toggle)."""
    inc = increment_mm / 1000.0
    return ceil(dimension_m / inc - 1e-9) * inc


def round_to_increment(dimension_m: float, increment_mm: float = 25.0) -> float:
    """Round a dimension to the NEAREST increment (25 mm default) -- distinct
    from snap_to_increment(), which always rounds up (used where a duct must
    never be undersized, e.g. picking a circular stock diameter). This one
    backs the rectangular "round to 25 mm" web toggle: a duct fabricator
    working to a 25 mm sheet-metal grid rounds to the closest practical size
    in either direction, not always up, so this is a genuinely different
    rounding rule, not a duplicate."""
    inc = increment_mm / 1000.0
    return round(dimension_m / inc) * inc


def status(value: float, limit: float, amber_fraction: float = 0.85) -> str:
    """Traffic-light classification of a value against a threshold.

    'red' at or over the limit, 'amber' within amber_fraction..1.0x of it,
    'green' otherwise. Feeds the on-screen status dots (style v2, app.css
    .dot.green/.amber/.red).
    """
    if value >= limit:
        return "red"
    if value >= limit * amber_fraction:
        return "amber"
    return "green"


# ── Flex duct (index-leg rework) ────────────────────────────────────────────
# A corrugated flexible duct run has materially more friction than an
# equivalent rigid duct at the same size and flow, due to its ribbed inner
# wall. FLEX_DUCT_DERATE is a single representative multiplier applied to an
# otherwise-normal rigid-duct friction-rate calculation for a straight run
# flagged as flex -- same "first-pass planning figure, not a certified design
# value" honesty as the fitting K-factors in hvac_engine.fittings: real flex
# friction depends on how fully the duct is extended (a compressed/kinked run
# can be far worse than this), so this is a starting point, not a substitute
# for manufacturer performance data on a real job. Disclosed in the Index Leg UI.
FLEX_DUCT_DERATE = 1.5  # typical corrugated-flex vs rigid friction-rate multiplier


def apply_flex_derate(friction_rate_pa_per_m: float, derate: float = FLEX_DUCT_DERATE) -> float:
    """Scale a rigid-duct friction rate up for a flexible-duct straight run.
    `derate` defaults to FLEX_DUCT_DERATE but is overridable per call, same
    pattern as rho/nu/roughness elsewhere in this module."""
    return friction_rate_pa_per_m * derate


__all__ = [
    "RHO_STD", "NU_STD", "ROUGHNESS_GALV_STEEL", "STANDARD_DIAMETERS_MM",
    "MAX_ASPECT_RATIO", "DEFAULT_MAX_VELOCITY", "DEFAULT_MAX_FRICTION_RATE",
    "CatalogDiameter", "LINDAB_CIRCULAR_CATALOG",
    "FlatOvalCatalogSize", "LINDAB_FLAT_OVAL_CATALOG", "snap_flat_oval_to_catalog",
    "CircularResult", "RectangularResult", "FlatOvalResult",
    "velocity_circular", "friction_rate_circular", "velocity_pressure", "size_circular",
    "snap_to_standard_diameter", "propose_circular",
    "equivalent_diameter_rectangular", "rectangular_from_equivalent_diameter",
    "rectangular_other_side", "size_rectangular", "propose_rectangular",
    "equivalent_diameter_flat_oval", "flat_oval_major_for_de", "flat_oval_minor_for_de",
    "size_flat_oval", "propose_flat_oval",
    "flat_oval_catalog_majors", "flat_oval_catalog_minors_for_major",
    "flat_oval_nearest_catalog_major", "flat_oval_nearest_minor_for_major",
    "flat_oval_step_major", "flat_oval_step_minor",
    "snap_to_increment", "round_to_increment", "status",
    "FLEX_DUCT_DERATE", "apply_flex_derate",
]
