"""Pipe sizing for closed hydronic systems (LTHW / CHW).

Implemented from specs/SPEC-pipe-sizing.md. Pure Python, canonical SI
throughout. Friction loss via Darcy-Weisbach with Swamee-Jain explicit
Colebrook-White (same approach as hvac_engine.duct). Pipe dimensions from
BS EN 10255 (carbon steel), BS EN 1057 (copper), DIN 11850 (dairy stainless).
Fluid properties: water from CIBSE/ASHRAE anchor tables; standard aqueous
ethylene / monopropylene glycol from ASHRAE secondary-coolant correlations;
Hydratech Coolflow proprietary blends from published data sheets at fixed
concentration grid points.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Literal

from hvac_engine.fluid_mechanics import swamee_jain
from hvac_engine.glycol_data import (
    FLUID_LABELS as _HYDRATECH_LABELS,
    GLYCOL_CONCENTRATIONS_PCT as _HYDRATECH_CONCS,
    glycol_concentrations as _hydratech_concentrations,
    glycol_freeze_point_c as _hydratech_freeze_point_c,
    glycol_grid as _hydratech_grid,
)
from hvac_engine import standard_glycol as _std_glycol

FlowMode = Literal["from_load", "flow_known"]
Application = Literal["lthw", "chw"]
FluidId = Literal["water", "eg", "mpg", "dtx", "epg", "ppg"]
MaterialId = Literal["carbon_steel", "copper", "dairy_ss"]
CircuitType = Literal["open", "pressurised"]
GlycolFluidId = Literal["eg", "mpg", "dtx", "epg", "ppg"]

# Standard acceleration due to gravity (m/s²) — BIPM / ISO 80000-3.
STANDARD_G = 9.80665

# Application keys used by the sizer (and historically mirrored CIBSE Guide C
# Table 2.2's single 1.5 m/s LTHW/CHW figure). Traffic-light *status* uses the
# per-DN bands below — not this flat 1.5 m/s limit. The DN ≤ 50 maximum of
# 1.5 m/s aligns with that CIBSE small-pipe figure; larger DN allow higher
# velocities for erosion/noise/lifecycle reasons (see VELOCITY_BANDS_BY_DN).
CIBSE_LIMITS: dict[Application, dict[str, float]] = {
    "lthw": {"max_velocity_ms": 1.5},
    "chw": {"max_velocity_ms": 1.5},
}

# Per-DN velocity bands (m/s): (dn_max, minimum, ideal_min, ideal_max, maximum).
# These drive green/amber/red status — not the flat CIBSE 1.5 m/s figure.
# DN ≤ 50 max matches CIBSE Guide C Table 2.2; larger sizes follow industry
# acoustic / erosion / pump-head practice (documented in the Pipe Sizing
# Design Limits guide).
VELOCITY_BANDS_BY_DN: tuple[tuple[int, float, float, float, float], ...] = (
    (50, 0.6, 0.8, 1.2, 1.5),
    (150, 0.6, 1.2, 1.8, 2.5),
    (9999, 0.6, 1.8, 2.5, 3.0),
)

# ΔP/L design bands (Pa/m) — lifecycle-cost framing for closed LTHW/CHW
# distribution (not a named CIBSE/ASHRAE table). Lower 100–150: CAPEX-heavy /
# OPEX-light. Ideal 200–300: sweet spot. Upper 400–500: CAPEX-light /
# OPEX-heavy. Below 100 or above 500 → red.
FRICTION_BANDS: dict[str, float] = {
    "red_low_pa_per_m": 100.0,
    "lower_min_pa_per_m": 100.0,
    "lower_max_pa_per_m": 150.0,
    "ideal_min_pa_per_m": 200.0,
    "ideal_max_pa_per_m": 300.0,
    "upper_min_pa_per_m": 400.0,
    "upper_max_pa_per_m": 500.0,
    "red_high_pa_per_m": 500.0,
}

# Pipe shell density for kg/m estimate (kg/m³) — carbon steel, copper, stainless.
PIPE_METAL_DENSITY: dict[MaterialId, float] = {
    "carbon_steel": 7850.0,
    "copper": 8960.0,
    "dairy_ss": 8000.0,
}

# Absolute roughness ε (m) — CIBSE Guide C Section 1.
ROUGHNESS: dict[MaterialId, float] = {
    "carbon_steel": 0.00015,
    "copper": 0.0000015,
    "dairy_ss": 0.0000015,
}

FLUID_LABELS: dict[FluidId, str] = {
    "water": "Water",
    "eg": _std_glycol.FLUID_LABELS["eg"],
    "mpg": _std_glycol.FLUID_LABELS["mpg"],
    "dtx": _HYDRATECH_LABELS["dtx"],
    "epg": _HYDRATECH_LABELS["epg"],
    "ppg": _HYDRATECH_LABELS["ppg"],
}

# Optgroup layout for the fluid <select> — water first, then library glycols,
# then Hydratech Coolflow proprietary blends.
FLUID_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("", (("water", "Water"),)),
    (
        "Standard glycol (ASHRAE)",
        (
            ("eg", FLUID_LABELS["eg"]),
            ("mpg", FLUID_LABELS["mpg"]),
        ),
    ),
    (
        "Hydratech Coolflow",
        (
            ("dtx", FLUID_LABELS["dtx"]),
            ("epg", FLUID_LABELS["epg"]),
            ("ppg", FLUID_LABELS["ppg"]),
        ),
    ),
)

GLYCOL_CONCENTRATIONS_PCT: dict[GlycolFluidId, tuple[int, ...]] = {
    **_std_glycol.GLYCOL_CONCENTRATIONS_PCT,
    **_HYDRATECH_CONCS,
}


def glycol_concentrations(fluid: GlycolFluidId) -> tuple[int, ...]:
    if fluid in _std_glycol.GLYCOL_CONCENTRATIONS_PCT:
        return _std_glycol.glycol_concentrations(fluid)  # type: ignore[arg-type]
    return tuple(_hydratech_concentrations(fluid))  # type: ignore[arg-type]


def glycol_freeze_point_c(fluid: GlycolFluidId, concentration_pct: int) -> float:
    if fluid in _std_glycol.GLYCOL_CONCENTRATIONS_PCT:
        return _std_glycol.freeze_point_c(fluid, concentration_pct)  # type: ignore[arg-type]
    return _hydratech_freeze_point_c(fluid, concentration_pct)  # type: ignore[arg-type]

MATERIAL_LABELS: dict[MaterialId, str] = {
    "carbon_steel": "Carbon steel (BS EN 10255)",
    "copper": "Copper (BS EN 1057)",
    "dairy_ss": "Thin-wall stainless (DIN 11850)",
}

APPLICATION_LABELS: dict[Application, str] = {
    "lthw": "LTHW — low-pressure hot water",
    "chw": "CHW — chilled water",
}

CIRCUIT_LABELS: dict[CircuitType, str] = {
    "pressurised": "Pressurised closed circuit",
    "open": "Open tank",
}


@dataclass(frozen=True)
class PipeCatalogEntry:
    """One stocked / standard pipe size."""

    dn: int
    label: str
    id_m: float
    od_m: float


@dataclass(frozen=True)
class FluidProperties:
    """Fluid state at the working mean temperature."""

    fluid: FluidId
    concentration_pct: int
    temperature_c: float
    density_kg_m3: float
    dynamic_viscosity_pa_s: float
    cp_j_kgk: float
    freezing_point_c: float

    @property
    def kinematic_viscosity_m2_s(self) -> float:
        return self.dynamic_viscosity_pa_s / self.density_kg_m3


@dataclass(frozen=True)
class FlowResult:
    """Duty-derived or user-supplied flow."""

    mass_flow_kg_s: float
    volume_flow_m3h: float
    from_load: bool


@dataclass(frozen=True)
class PipeSizeResult:
    """Evaluation of one catalogue size at the given flow."""

    entry: PipeCatalogEntry
    velocity_ms: float
    friction_rate_pa_per_m: float
    reynolds: float
    friction_factor: float
    status_velocity: str
    status_friction: str

    @property
    def regime(self) -> str:
        if self.reynolds < 2300:
            return "Laminar"
        if self.reynolds < 4000:
            return "Transitional"
        return "Turbulent"


@dataclass(frozen=True)
class HeadBreakdown:
    """Static lift + friction combined into required pump head (Stage 3)."""

    circuit: CircuitType
    lift_height_m: float
    density_kg_m3: float
    static_head_pa: float
    friction_pa: float
    pump_duty_pa: float
    static_applies_to_pump: bool


# ── Pipe catalogues (public standard dimensions) ─────────────────────────────

# BS EN 10255 Series 1 medium — internal bore and OD (mm) from the standard.
_CARBON_STEEL_MM: tuple[tuple[int, float, float], ...] = (
    (15, 16.1, 21.3),
    (20, 21.7, 26.9),
    (25, 27.3, 33.7),
    (32, 36.9, 42.4),
    (40, 42.5, 48.3),
    (50, 54.5, 60.3),
    (65, 70.3, 76.1),
    (80, 82.5, 88.9),
    (100, 107.1, 114.3),
    (125, 131.7, 139.7),
    (150, 159.3, 168.3),
    (200, 207.1, 219.1),
    (250, 260.4, 273.0),
    (300, 309.7, 323.9),
)

# BS EN 1057 R250 Table X — OD and bore (mm).
_COPPER_MM: tuple[tuple[int, float, float], ...] = (
    (15, 15.0, 13.6),
    (18, 18.0, 16.6),
    (22, 22.0, 20.4),
    (28, 28.0, 26.4),
    (35, 35.0, 33.6),
    (42, 42.0, 40.4),
    (54, 54.0, 52.0),
    (76, 76.1, 73.7),
    (108, 108.0, 105.2),
    (133, 133.0, 130.0),
    (159, 159.0, 155.8),
    (219, 219.1, 215.4),
)

# DIN 11850 — OD with 1.5 mm wall (ID = OD − 3 mm).
_DAIRY_SS_MM: tuple[tuple[int, float, float], ...] = (
    (25, 25.0, 22.0),
    (32, 32.0, 29.0),
    (40, 40.0, 37.0),
    (50, 50.0, 47.0),
    (65, 65.0, 62.0),
    (80, 80.0, 77.0),
    (100, 100.0, 97.0),
    (125, 125.0, 122.0),
    (150, 150.0, 147.0),
    (200, 200.0, 197.0),
)


def _entries_from_mm(rows: tuple[tuple[int, float, float], ...], prefix: str) -> tuple[PipeCatalogEntry, ...]:
    out: list[PipeCatalogEntry] = []
    for dn, id_mm, od_mm in rows:
        out.append(
            PipeCatalogEntry(
                dn=dn,
                label=f"{prefix}{dn}",
                id_m=id_mm / 1000.0,
                od_m=od_mm / 1000.0,
            )
        )
    return tuple(out)


PIPE_CATALOGUES: dict[MaterialId, tuple[PipeCatalogEntry, ...]] = {
    "carbon_steel": _entries_from_mm(_CARBON_STEEL_MM, "DN"),
    "copper": _entries_from_mm(_COPPER_MM, "Cu "),
    "dairy_ss": _entries_from_mm(_DAIRY_SS_MM, "DN"),
}


def catalogue_for(material: MaterialId) -> tuple[PipeCatalogEntry, ...]:
    try:
        return PIPE_CATALOGUES[material]
    except KeyError:
        raise ValueError(f"unknown material: {material!r}")


# ── Water properties (CIBSE / ASHRAE anchor table, °C) ───────────────────────
# (T, ρ kg/m³, μ Pa·s, cp J/kg·K)
_WATER_TABLE: tuple[tuple[float, float, float, float], ...] = (
    (0.0, 999.8, 0.001792, 4217.0),
    (10.0, 999.7, 0.001307, 4192.0),
    (20.0, 998.2, 0.001002, 4182.0),
    (30.0, 995.7, 0.000801, 4178.0),
    (40.0, 992.2, 0.000653, 4179.0),
    (50.0, 988.0, 0.000547, 4181.0),
    (60.0, 983.2, 0.000467, 4185.0),
    (70.0, 977.8, 0.000404, 4190.0),
    (80.0, 971.8, 0.000355, 4196.0),
    (90.0, 965.3, 0.000315, 4203.0),
    (100.0, 958.4, 0.000282, 4212.0),
)


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def _interp_table(
    temp_c: float,
    table: tuple[tuple[float, float, float, float], ...],
) -> tuple[float, float, float]:
    if temp_c <= table[0][0]:
        _, rho, mu, cp = table[0]
        return rho, mu, cp
    if temp_c >= table[-1][0]:
        _, rho, mu, cp = table[-1]
        return rho, mu, cp
    for i in range(len(table) - 1):
        t0, rho0, mu0, cp0 = table[i]
        t1, rho1, mu1, cp1 = table[i + 1]
        if t0 <= temp_c <= t1:
            return (
                _lerp(temp_c, t0, t1, rho0, rho1),
                _lerp(temp_c, t0, t1, mu0, mu1),
                _lerp(temp_c, t0, t1, cp0, cp1),
            )
    raise RuntimeError("interpolation failed")


def _interp_glycol(
    table: tuple[tuple[float, float, float, float, float], ...],
    temp_c: float,
) -> tuple[float, float, float, float]:
    if temp_c <= table[0][0]:
        _, rho, mu, cp, fp = table[0]
        return rho, mu, cp, fp
    if temp_c >= table[-1][0]:
        _, rho, mu, cp, fp = table[-1]
        return rho, mu, cp, fp
    for i in range(len(table) - 1):
        t0, rho0, mu0, cp0, fp0 = table[i]
        t1, rho1, mu1, cp1, fp1 = table[i + 1]
        if t0 <= temp_c <= t1:
            return (
                _lerp(temp_c, t0, t1, rho0, rho1),
                _lerp(temp_c, t0, t1, mu0, mu1),
                _lerp(temp_c, t0, t1, cp0, cp1),
                _lerp(temp_c, t0, t1, fp0, fp1),
            )
    raise RuntimeError("glycol interpolation failed")


def mean_water_temperature_c(lwt_c: float, delta_t_k: float) -> float:
    return lwt_c + delta_t_k / 2.0


def fluid_properties(
    fluid: FluidId,
    temperature_c: float,
    concentration_pct: int = 0,
) -> FluidProperties:
    if fluid == "water":
        if concentration_pct not in (0,):
            raise ValueError("water has no glycol concentration")
        rho, mu, cp = _interp_table(temperature_c, _WATER_TABLE)
        return FluidProperties(
            fluid=fluid,
            concentration_pct=0,
            temperature_c=temperature_c,
            density_kg_m3=rho,
            dynamic_viscosity_pa_s=mu,
            cp_j_kgk=cp,
            freezing_point_c=0.0,
        )

    if fluid in _std_glycol.GLYCOL_CONCENTRATIONS_PCT:
        rho, mu, cp, fp = _std_glycol.fluid_properties_si(
            fluid, temperature_c, concentration_pct  # type: ignore[arg-type]
        )
        return FluidProperties(
            fluid=fluid,
            concentration_pct=concentration_pct,
            temperature_c=temperature_c,
            density_kg_m3=rho,
            dynamic_viscosity_pa_s=mu,
            cp_j_kgk=cp,
            freezing_point_c=fp,
        )

    if concentration_pct not in glycol_concentrations(fluid):  # type: ignore[arg-type]
        allowed = glycol_concentrations(fluid)  # type: ignore[arg-type]
        raise ValueError(
            f"glycol concentration must be one of {allowed}, got {concentration_pct!r}"
        )
    grid = _hydratech_grid(fluid, concentration_pct)
    rho, mu, cp, fp = _interp_glycol(grid, temperature_c)
    return FluidProperties(
        fluid=fluid,
        concentration_pct=concentration_pct,
        temperature_c=temperature_c,
        density_kg_m3=rho,
        dynamic_viscosity_pa_s=mu,
        cp_j_kgk=cp,
        freezing_point_c=fp,
    )


def flow_from_load(load_kw: float, delta_t_k: float, props: FluidProperties) -> FlowResult:
    if load_kw <= 0:
        raise ValueError("load must be positive")
    if delta_t_k <= 0:
        raise ValueError("delta T must be positive")
    q_w = load_kw * 1000.0
    mass = q_w / (props.cp_j_kgk * delta_t_k)
    vol_m3h = mass / props.density_kg_m3 * 3600.0
    return FlowResult(mass_flow_kg_s=mass, volume_flow_m3h=vol_m3h, from_load=True)


def flow_from_volume_rate(volume_flow_m3h: float) -> FlowResult:
    if volume_flow_m3h <= 0:
        raise ValueError("flow must be positive")
    # Mass flow filled by caller once density known; store volume only here.
    return FlowResult(mass_flow_kg_s=0.0, volume_flow_m3h=volume_flow_m3h, from_load=False)


def complete_known_flow(flow: FlowResult, props: FluidProperties) -> FlowResult:
    if flow.from_load:
        return flow
    mass = flow.volume_flow_m3h / 3600.0 * props.density_kg_m3
    return FlowResult(
        mass_flow_kg_s=mass,
        volume_flow_m3h=flow.volume_flow_m3h,
        from_load=False,
    )


def volume_flow_ls(volume_flow_m3h: float) -> float:
    return volume_flow_m3h / 3.6


def volume_flow_m3h_from_ls(flow_ls: float) -> float:
    return flow_ls * 3.6


# ── Velocity pressure + friction (Darcy–Weisbach + Swamee–Jain) ───────────────

def velocity_pressure(velocity_ms: float, density_kg_m3: float) -> float:
    """Dynamic (velocity) pressure Pv = ½ ρ V² in Pa — for local fitting losses.

    Uses the working fluid density (not a fixed air density). Raises if
    velocity or density is negative.
    """
    if velocity_ms < 0:
        raise ValueError(f"velocity must be zero or greater (got {velocity_ms!r})")
    if density_kg_m3 <= 0:
        raise ValueError(f"density must be positive (got {density_kg_m3!r})")
    return 0.5 * density_kg_m3 * velocity_ms ** 2


def hydrostatic_pressure_pa(height_m: float, density_kg_m3: float) -> float:
    """Static head as pressure: P = ρ g h (Pa).

    ``height_m`` is the vertical fluid column (lift). Uses ``STANDARD_G``.
    """
    if height_m < 0:
        raise ValueError(f"lift height must be zero or greater (got {height_m!r})")
    if density_kg_m3 <= 0:
        raise ValueError(f"density must be positive (got {density_kg_m3!r})")
    return density_kg_m3 * STANDARD_G * height_m


def head_breakdown(
    circuit: CircuitType,
    lift_height_m: float,
    density_kg_m3: float,
    friction_pa: float,
) -> HeadBreakdown:
    """Combine static lift and circuit friction into required pump head.

    Open systems: pump duty = static + friction.
    Pressurised (closed): circulating pump duty = friction only; static head is
    still reported for height / fill context but not added to pump duty.
    """
    if circuit not in ("open", "pressurised"):
        raise ValueError(f"unknown circuit type: {circuit!r}")
    if friction_pa < 0:
        raise ValueError(f"friction pressure drop must be zero or greater (got {friction_pa!r})")
    static_pa = hydrostatic_pressure_pa(lift_height_m, density_kg_m3)
    applies = circuit == "open"
    pump_pa = static_pa + friction_pa if applies else friction_pa
    return HeadBreakdown(
        circuit=circuit,
        lift_height_m=lift_height_m,
        density_kg_m3=density_kg_m3,
        static_head_pa=static_pa,
        friction_pa=friction_pa,
        pump_duty_pa=pump_pa,
        static_applies_to_pump=applies,
    )


# Back-compat alias — prefer hvac_engine.fluid_mechanics.swamee_jain.
_swamee_jain = swamee_jain


def evaluate_size(
    volume_flow_m3h: float,
    entry: PipeCatalogEntry,
    props: FluidProperties,
    material: MaterialId,
    application: Application,
) -> PipeSizeResult:
    if volume_flow_m3h <= 0:
        raise ValueError("flow must be positive")
    d = entry.id_m
    if d <= 0:
        raise ValueError("internal diameter must be positive")

    area = pi * d ** 2 / 4.0
    v = (volume_flow_m3h / 3600.0) / area
    nu = props.kinematic_viscosity_m2_s
    re = v * d / nu
    rough = ROUGHNESS[material]
    f = swamee_jain(re, rough, d)
    dp_dl = f * (1.0 / d) * (props.density_kg_m3 * v ** 2 / 2.0)

    return PipeSizeResult(
        entry=entry,
        velocity_ms=v,
        friction_rate_pa_per_m=dp_dl,
        reynolds=re,
        friction_factor=f,
        status_velocity=velocity_status(v, entry.dn),
        status_friction=friction_status(dp_dl),
    )


def evaluate_catalogue(
    volume_flow_m3h: float,
    material: MaterialId,
    props: FluidProperties,
    application: Application,
) -> list[PipeSizeResult]:
    return [
        evaluate_size(volume_flow_m3h, entry, props, material, application)
        for entry in catalogue_for(material)
    ]


def velocity_limits_for_dn(dn: int) -> tuple[float, float, float, float]:
    """Return (minimum, ideal_min, ideal_max, maximum) velocity in m/s for a DN."""
    for dn_max, min_v, ideal_min, ideal_max, max_v in VELOCITY_BANDS_BY_DN:
        if dn <= dn_max:
            return min_v, ideal_min, ideal_max, max_v
    return VELOCITY_BANDS_BY_DN[-1][1:]


def velocity_status(velocity_ms: float, dn: int) -> str:
    """Per-DN velocity traffic light — green ideal, amber border bands, red outside."""
    min_v, ideal_min, ideal_max, max_v = velocity_limits_for_dn(dn)
    if velocity_ms > max_v or velocity_ms < min_v:
        return "red"
    if ideal_min <= velocity_ms <= ideal_max:
        return "green"
    return "amber"


def friction_status(friction_pa_per_m: float) -> str:
    """Pa/m traffic light — lifecycle-cost bands (100–150 / 200–300 / 400–500)."""
    fb = FRICTION_BANDS
    if friction_pa_per_m < fb["red_low_pa_per_m"]:
        return "red"
    if friction_pa_per_m <= fb["lower_max_pa_per_m"]:
        return "amber"
    if friction_pa_per_m < fb["ideal_min_pa_per_m"]:
        return "amber"
    if friction_pa_per_m <= fb["ideal_max_pa_per_m"]:
        return "green"
    if friction_pa_per_m < fb["upper_min_pa_per_m"]:
        return "amber"
    if friction_pa_per_m <= fb["upper_max_pa_per_m"]:
        return "amber"
    return "red"


def _within_absolute_limits(row: PipeSizeResult) -> bool:
    return (
        velocity_status(row.velocity_ms, row.entry.dn) != "red"
        and friction_status(row.friction_rate_pa_per_m) != "red"
    )


def band_status(
    value: float,
    min_ideal: float,
    max_ideal: float,
    absolute_max: float,
) -> str:
    """Traffic-light against an ideal band (not a single upper limit).

    Green — within the ideal range (min_ideal .. max_ideal).
    Amber — below min_ideal (oversized / uneconomic) OR above max_ideal but still
            below the CIBSE absolute maximum (commercially pushed sizing).
    Red   — at or above the absolute maximum (out of limits).
    """
    if value >= absolute_max:
        return "red"
    if value < min_ideal:
        return "amber"
    if value <= max_ideal:
        return "green"
    return "amber"


def status(value: float, limit: float, amber_fraction: float = 0.85) -> str:
    """Legacy upper-limit-only classifier (duct-style). Prefer band_status for pipe."""
    if value >= limit:
        return "red"
    if value >= limit * amber_fraction:
        return "amber"
    return "green"


def pipe_mass_per_m(material: MaterialId, entry: PipeCatalogEntry) -> float:
    """Linear mass of the pipe shell (kg/m) from OD, ID and material density."""
    rho = PIPE_METAL_DENSITY[material]
    area = pi / 4.0 * (entry.od_m ** 2 - entry.id_m ** 2)
    return rho * area


def wall_thickness_m(entry: PipeCatalogEntry) -> float:
    return (entry.od_m - entry.id_m) / 2.0


def default_selected_dn(
    results: list[PipeSizeResult],
    application: Application,
) -> int | None:
    """Pick the recommended size — smallest DN with ideal friction and velocity not red."""
    idx = recommended_index(results, application)
    if idx is not None:
        return results[idx].entry.dn
    return results[0].entry.dn if results else None


def recommended_index(results: list[PipeSizeResult], application: Application) -> int | None:
    """Index of the smallest size with ideal friction (200–300 Pa/m) and velocity not red."""
    for i, row in enumerate(results):
        if (
            friction_status(row.friction_rate_pa_per_m) == "green"
            and velocity_status(row.velocity_ms, row.entry.dn) != "red"
        ):
            return i
    for i, row in enumerate(results):
        if _within_absolute_limits(row):
            return i
    return None


def find_result(results: list[PipeSizeResult], dn: int) -> PipeSizeResult | None:
    for row in results:
        if row.entry.dn == dn:
            return row
    return None


def _row_is_red(row: PipeSizeResult) -> bool:
    return row.status_velocity == "red" or row.status_friction == "red"


def trim_catalogue_view(
    results: list[PipeSizeResult],
    application: Application,
    *,
    selection_buffer: int = 1,
    selected_dn: int | None = None,
) -> list[PipeSizeResult]:
    """Return a focused slice of the catalogue for the on-screen table.

    Centres on the recommended size and the ideal-friction (200–300 Pa/m) band,
    with one buffer size each side — avoids listing the full catalogue of small
    DN rows that are red on velocity.  The selected row is always kept visible.
    """
    n = len(results)
    if n == 0:
        return results

    rec = recommended_index(results, application)
    if rec is None:
        return list(results)

    ideal_friction_idx = [
        i for i, r in enumerate(results)
        if friction_status(r.friction_rate_pa_per_m) == "green"
    ]

    start = rec - selection_buffer
    end = rec + selection_buffer

    if ideal_friction_idx:
        start = min(start, min(ideal_friction_idx) - selection_buffer)
        end = max(end, max(ideal_friction_idx) + selection_buffer)

    if selected_dn is not None:
        for i, row in enumerate(results):
            if row.entry.dn == selected_dn:
                start = min(start, i)
                end = max(end, i)
                break

    start = max(0, start)
    end = min(n - 1, end)
    return results[start : end + 1]


__all__ = [
    "APPLICATION_LABELS",
    "Application",
    "CIBSE_LIMITS",
    "CIRCUIT_LABELS",
    "CircuitType",
    "FRICTION_BANDS",
    "FLUID_GROUPS",
    "FLUID_LABELS",
    "FlowMode",
    "FlowResult",
    "FluidId",
    "FluidProperties",
    "GLYCOL_CONCENTRATIONS_PCT",
    "GlycolFluidId",
    "HeadBreakdown",
    "MATERIAL_LABELS",
    "MaterialId",
    "PIPE_CATALOGUES",
    "PIPE_METAL_DENSITY",
    "PipeCatalogEntry",
    "PipeSizeResult",
    "ROUGHNESS",
    "STANDARD_G",
    "band_status",
    "catalogue_for",
    "friction_status",
    "complete_known_flow",
    "default_selected_dn",
    "evaluate_catalogue",
    "evaluate_size",
    "find_result",
    "flow_from_load",
    "flow_from_volume_rate",
    "fluid_properties",
    "glycol_concentrations",
    "glycol_freeze_point_c",
    "head_breakdown",
    "hydrostatic_pressure_pa",
    "mean_water_temperature_c",
    "pipe_mass_per_m",
    "recommended_index",
    "status",
    "trim_catalogue_view",
    "velocity_limits_for_dn",
    "velocity_pressure",
    "velocity_status",
    "VELOCITY_BANDS_BY_DN",
    "volume_flow_ls",
    "volume_flow_m3h_from_ls",
    "wall_thickness_m",
]
