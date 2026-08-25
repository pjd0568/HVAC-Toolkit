"""Refrigeration / DX — PT table and copper pipe sizing (sub-critical).

Per specs/SPEC-refrigeration-dx.md. Thermodynamic properties via CoolProp
(runtime dependency). ACR copper catalogue from BS EN 12735-1 (not BS EN 1057
water copper).

Zeotrope temperature convention (documented in UI/methodology):
  evaporating temperature → dew-point pressure
  condensing temperature → bubble-point pressure
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Literal

LineType = Literal["suction", "liquid", "discharge"]
Orientation = Literal["horizontal", "upflow_riser"]
VelocityStatus = Literal["green", "amber", "red"]

# Standard atmosphere for barg display (bar absolute).
P_ATM_BAR = 1.01325

# Default discharge temperature offset above condensing when not supplied (K).
DEFAULT_DISCHARGE_SUPERHEAT_K = 40.0

# Oil-return / band floors (m/s) — SPEC-refrigeration-dx.md.
OIL_RETURN_FLOOR_MS = 5.0
SUCTION_RISER_MIN_MS = 10.0

# Ideal velocity bands (min, max) m/s.
VELOCITY_BANDS: dict[LineType, tuple[float, float]] = {
    "suction": (8.0, 15.0),
    "liquid": (0.5, 1.5),
    "discharge": (10.0, 18.0),
}

# Absolute max velocity (above → red).
VELOCITY_ABS_MAX: dict[LineType, float] = {
    "suction": 20.0,
    "liquid": 2.5,
    "discharge": 25.0,
}


class CoolPropUnavailableError(ImportError):
    """Raised when CoolProp is not installed."""


def _propsi(*args):
    try:
        from CoolProp.CoolProp import PropsSI
    except ImportError as exc:
        raise CoolPropUnavailableError(
            "CoolProp is required for refrigeration calculations. "
            "Install with: pip install 'CoolProp>=6.6'"
        ) from exc
    return PropsSI(*args)


@dataclass(frozen=True)
class RefrigerantInfo:
    id: str
    label: str
    coolprop_fluid: str
    available: bool
    group: str
    note: str = ""
    is_zeotrope: bool = False


# CoolProp 8.0: R454B / R513A are HEOS mixtures (mole fractions from CoolProp
# predefined blend table ≡ ASHRAE mass compositions).
_R454B_FLUID = "HEOS::R32[0.829248]&R1234yf[0.170752]"
_R513A_FLUID = "HEOS::R1234yf[0.532426]&R134a[0.467574]"

REFRIGERANTS: dict[str, RefrigerantInfo] = {
    "r410a": RefrigerantInfo(
        "r410a", "R-410A", "R410A", True, "Legacy / phasing out", is_zeotrope=True,
    ),
    "r134a": RefrigerantInfo("r134a", "R-134a", "R134a", True, "Legacy / phasing out"),
    "r404a": RefrigerantInfo(
        "r404a", "R-404A", "R404A", True, "Legacy / phasing out", is_zeotrope=True,
    ),
    "r407c": RefrigerantInfo(
        "r407c", "R-407C", "R407C", True, "Legacy / phasing out", is_zeotrope=True,
    ),
    "r32": RefrigerantInfo("r32", "R-32", "R32", True, "Current standards"),
    "r513a": RefrigerantInfo(
        "r513a", "R-513A", _R513A_FLUID, True, "Current standards", is_zeotrope=True,
    ),
    "r454b": RefrigerantInfo(
        "r454b", "R-454B", _R454B_FLUID, True, "Next-gen (A2L / HFO)", is_zeotrope=True,
    ),
    "r1234ze": RefrigerantInfo(
        "r1234ze", "R-1234ze(E)", "R1234ze(E)", True, "Next-gen (A2L / HFO)",
    ),
    "r1234yf": RefrigerantInfo(
        "r1234yf", "R-1234yf", "R1234yf", True, "Next-gen (A2L / HFO)",
    ),
    "r290": RefrigerantInfo("r290", "R-290 (propane)", "R290", True, "Natural"),
    "r600a": RefrigerantInfo("r600a", "R-600a (isobutane)", "R600a", True, "Natural"),
    "r744": RefrigerantInfo(
        "r744",
        "R-744 (CO₂)",
        "CO2",
        False,
        "Natural",
        note="Coming soon — transcritical / CO₂ circuit logic not in v1",
    ),
}

REFRIGERANT_GROUP_ORDER = (
    "Legacy / phasing out",
    "Current standards",
    "Next-gen (A2L / HFO)",
    "Natural",
)

LINE_TYPE_LABELS: dict[LineType, str] = {
    "suction": "Suction (vapour)",
    "liquid": "Liquid",
    "discharge": "Discharge (hot gas)",
}

ORIENTATION_LABELS: dict[Orientation, str] = {
    "horizontal": "Horizontal / downflow",
    "upflow_riser": "Upflow riser",
}


def list_refrigerants(*, include_unavailable: bool = True) -> list[RefrigerantInfo]:
    rows = list(REFRIGERANTS.values())
    if not include_unavailable:
        rows = [r for r in rows if r.available]
    return rows


def get_refrigerant(refrigerant_id: str) -> RefrigerantInfo:
    raw = refrigerant_id.strip().lower().replace(" ", "").replace("-", "")
    if raw.startswith("r1234ze"):
        key = "r1234ze"
    else:
        key = raw if raw.startswith("r") else f"r{raw}"
    info = REFRIGERANTS.get(key)
    if info is None:
        raise ValueError(f"unknown refrigerant: {refrigerant_id!r}")
    return info


def _require_available(info: RefrigerantInfo) -> None:
    if not info.available:
        raise ValueError(
            f"{info.label} is not available in this release "
            f"({info.note or 'coming soon'})"
        )


def _pa_to_barg(p_pa: float) -> float:
    return p_pa / 1e5 - P_ATM_BAR


# ── PT table ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PtRow:
    t_c: float
    p_bubble_barg: float
    p_dew_barg: float
    skipped: bool = False
    skip_reason: str = ""


@dataclass(frozen=True)
class PtTableResult:
    refrigerant: RefrigerantInfo
    t_min_c: float
    t_max_c: float
    t_step_k: float
    rows: tuple[PtRow, ...]
    glide_notable: bool
    max_glide_k: float


def pt_table(
    refrigerant_id: str,
    t_min_c: float = -40.0,
    t_max_c: float = 60.0,
    t_step_k: float = 1.0,
) -> PtTableResult:
    info = get_refrigerant(refrigerant_id)
    _require_available(info)
    if t_step_k <= 0:
        raise ValueError("t_step_k must be positive")
    if t_max_c < t_min_c:
        raise ValueError("t_max_c must be >= t_min_c")

    fluid = info.coolprop_fluid
    rows: list[PtRow] = []
    max_glide_k = 0.0
    n_steps = int(round((t_max_c - t_min_c) / t_step_k))
    for i in range(n_steps + 1):
        t_round = round(t_min_c + i * t_step_k, 6)
        t_k = t_round + 273.15
        try:
            p_bub = _propsi("P", "T", t_k, "Q", 0, fluid)
            p_dew = _propsi("P", "T", t_k, "Q", 1, fluid)
            p_mid = 0.5 * (p_bub + p_dew)
            try:
                t_bub = _propsi("T", "P", p_mid, "Q", 0, fluid) - 273.15
                t_dew = _propsi("T", "P", p_mid, "Q", 1, fluid) - 273.15
                glide = abs(t_dew - t_bub)
            except Exception:
                glide = 0.0
            max_glide_k = max(max_glide_k, glide)
            rows.append(
                PtRow(
                    t_c=t_round,
                    p_bubble_barg=_pa_to_barg(p_bub),
                    p_dew_barg=_pa_to_barg(p_dew),
                )
            )
        except Exception as exc:
            rows.append(
                PtRow(
                    t_c=t_round,
                    p_bubble_barg=float("nan"),
                    p_dew_barg=float("nan"),
                    skipped=True,
                    skip_reason=str(exc).split("\n")[0][:120],
                )
            )

    return PtTableResult(
        refrigerant=info,
        t_min_c=t_min_c,
        t_max_c=t_max_c,
        t_step_k=t_step_k,
        rows=tuple(rows),
        glide_notable=max_glide_k >= 0.1,
        max_glide_k=max_glide_k,
    )


# ── ACR copper catalogue (BS EN 12735-1) ─────────────────────────────────────


@dataclass(frozen=True)
class AcrPipeEntry:
    """One ACR copper size — OD/wall from BS EN 12735-1 imperial series."""

    nominal_inch: str
    od_mm: float
    wall_mm: float
    id_mm: float

    @property
    def label(self) -> str:
        return f'{self.nominal_inch}"'

    @property
    def id_m(self) -> float:
        return self.id_mm / 1000.0

    @property
    def area_m2(self) -> float:
        d = self.id_m
        return pi * (d / 2.0) ** 2


# Imperial OD + commonly stocked wall (coil 0.8 mm where EN marks C; else 1.0 mm).
# ID = OD − 2×wall. Sources: BS EN 12735-1 nominal OD table; wall series per
# Engineering Toolbox / EN availability (C coil / S straight).
_ACR_ROWS: tuple[tuple[str, float, float], ...] = (
    ("1/4", 6.35, 0.80),
    ("3/8", 9.52, 0.80),
    ("1/2", 12.70, 0.80),
    ("5/8", 15.87, 1.00),
    ("3/4", 19.05, 1.00),
    ("7/8", 22.22, 1.00),
    ("1-1/8", 28.57, 1.00),
)

ACR_CATALOGUE: tuple[AcrPipeEntry, ...] = tuple(
    AcrPipeEntry(
        nominal_inch=inch,
        od_mm=od,
        wall_mm=wall,
        id_mm=od - 2.0 * wall,
    )
    for inch, od, wall in _ACR_ROWS
)


def acr_catalogue() -> tuple[AcrPipeEntry, ...]:
    return ACR_CATALOGUE


def find_acr(nominal_inch: str) -> AcrPipeEntry | None:
    key = nominal_inch.strip().rstrip('"')
    for entry in ACR_CATALOGUE:
        if entry.nominal_inch == key:
            return entry
    return None


# ── DX pipe sizing ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AcrSizeResult:
    entry: AcrPipeEntry
    velocity_ms: float
    status_velocity: VelocityStatus
    in_ideal_band: bool


@dataclass(frozen=True)
class DxPipeSizeResult:
    refrigerant: RefrigerantInfo
    line_type: LineType
    orientation: Orientation
    cooling_capacity_kw: float
    mass_flow_kg_s: float
    delta_h_kj_kg: float
    density_kg_m3: float
    p_evap_bara: float
    p_cond_bara: float
    discharge_temp_c: float
    discharge_temp_estimated: bool
    recommended: AcrSizeResult | None
    rows: tuple[AcrSizeResult, ...]
    warnings: tuple[str, ...]
    velocity_only: bool = True


def velocity_limits(
    line_type: LineType,
    orientation: Orientation = "horizontal",
) -> tuple[float, float, float]:
    """Return (ideal_min, ideal_max, abs_max) in m/s."""
    ideal_min, ideal_max = VELOCITY_BANDS[line_type]
    if line_type == "suction" and orientation == "upflow_riser":
        ideal_min = max(ideal_min, SUCTION_RISER_MIN_MS)
    return ideal_min, ideal_max, VELOCITY_ABS_MAX[line_type]


def velocity_status(
    velocity_ms: float,
    line_type: LineType,
    orientation: Orientation = "horizontal",
) -> VelocityStatus:
    ideal_min, ideal_max, abs_max = velocity_limits(line_type, orientation)
    if velocity_ms > abs_max:
        return "red"
    if line_type == "suction" and velocity_ms < OIL_RETURN_FLOOR_MS:
        return "red"
    if line_type == "suction" and orientation == "upflow_riser" and velocity_ms < SUCTION_RISER_MIN_MS:
        return "red"
    if ideal_min <= velocity_ms <= ideal_max:
        return "green"
    return "amber"


@dataclass(frozen=True)
class _CycleStates:
    p_evap: float
    p_cond: float
    h1: float
    h4: float
    rho_suction: float
    rho_liquid: float
    discharge_estimated: bool
    discharge_temp_c: float


def _cycle_states(
    fluid: str,
    evaporating_temp_c: float,
    condensing_temp_c: float,
    subcooling_k: float,
    superheat_k: float,
    discharge_temp_c: float | None,
) -> _CycleStates:
    """Evaporating T → dew pressure; condensing T → bubble pressure."""
    if subcooling_k < 0 or superheat_k < 0:
        raise ValueError("subcooling_k and superheat_k must be >= 0")
    tevap_k = evaporating_temp_c + 273.15
    tcond_k = condensing_temp_c + 273.15

    p_evap = _propsi("P", "T", tevap_k, "Q", 1, fluid)  # dew
    p_cond = _propsi("P", "T", tcond_k, "Q", 0, fluid)  # bubble

    t_suction_k = tevap_k + superheat_k
    h1 = _propsi("H", "P", p_evap, "T", t_suction_k, fluid)
    rho_suction = _propsi("D", "P", p_evap, "T", t_suction_k, fluid)

    t_bubble_cond_k = _propsi("T", "P", p_cond, "Q", 0, fluid)
    t_liquid_k = t_bubble_cond_k - subcooling_k
    if t_liquid_k <= 0:
        raise ValueError("liquid temperature after subcooling is non-physical")
    h3 = _propsi("H", "P", p_cond, "T", t_liquid_k, fluid)
    rho_liquid = _propsi("D", "P", p_cond, "T", t_liquid_k, fluid)
    h4 = h3  # isenthalpic expansion

    estimated = discharge_temp_c is None
    if estimated:
        t_dis_c = condensing_temp_c + DEFAULT_DISCHARGE_SUPERHEAT_K
    else:
        t_dis_c = float(discharge_temp_c)

    return _CycleStates(
        p_evap=p_evap,
        p_cond=p_cond,
        h1=h1,
        h4=h4,
        rho_suction=rho_suction,
        rho_liquid=rho_liquid,
        discharge_estimated=estimated,
        discharge_temp_c=t_dis_c,
    )


def size_dx_pipe(
    cooling_capacity_kw: float,
    refrigerant_id: str,
    evaporating_temp_c: float,
    condensing_temp_c: float,
    subcooling_k: float = 5.0,
    superheat_k: float = 5.0,
    line_type: LineType = "suction",
    orientation: Orientation = "horizontal",
    discharge_temp_c: float | None = None,
) -> DxPipeSizeResult:
    info = get_refrigerant(refrigerant_id)
    _require_available(info)
    if cooling_capacity_kw <= 0:
        raise ValueError("cooling_capacity_kw must be positive")
    if line_type not in VELOCITY_BANDS:
        raise ValueError(f"unknown line_type: {line_type!r}")
    if orientation not in ("horizontal", "upflow_riser"):
        raise ValueError(f"unknown orientation: {orientation!r}")
    if line_type != "suction":
        orientation = "horizontal"

    st = _cycle_states(
        info.coolprop_fluid,
        evaporating_temp_c,
        condensing_temp_c,
        subcooling_k,
        superheat_k,
        discharge_temp_c,
    )

    delta_h = st.h1 - st.h4  # J/kg
    if delta_h <= 0:
        raise ValueError(
            "evaporator enthalpy rise is non-positive — check temps / SC / SH"
        )
    mass_flow = (cooling_capacity_kw * 1000.0) / delta_h  # kg/s

    t_dis_k = st.discharge_temp_c + 273.15
    rho_discharge = _propsi("D", "P", st.p_cond, "T", t_dis_k, info.coolprop_fluid)

    if line_type == "suction":
        rho = st.rho_suction
    elif line_type == "liquid":
        rho = st.rho_liquid
    else:
        rho = rho_discharge

    if rho <= 0:
        raise ValueError("non-physical refrigerant density")

    warnings: list[str] = [
        "Pressure drop (equivalent ΔTsat) is not checked in v1 — size on velocity only."
    ]
    if st.discharge_estimated and line_type == "discharge":
        warnings.append(
            f"Discharge temperature estimated as condensing + "
            f"{DEFAULT_DISCHARGE_SUPERHEAT_K:.0f} K ({st.discharge_temp_c:.1f} °C)."
        )

    rows: list[AcrSizeResult] = []
    for entry in ACR_CATALOGUE:
        v = mass_flow / (rho * entry.area_m2)
        ideal_min, ideal_max, _ = velocity_limits(line_type, orientation)
        status = velocity_status(v, line_type, orientation)
        rows.append(
            AcrSizeResult(
                entry=entry,
                velocity_ms=v,
                status_velocity=status,
                in_ideal_band=ideal_min <= v <= ideal_max,
            )
        )

    recommended = _recommend(rows)
    if recommended is not None:
        if line_type == "suction" and recommended.velocity_ms < OIL_RETURN_FLOOR_MS:
            warnings.append(
                f"Suction velocity {recommended.velocity_ms:.2f} m/s is below "
                f"oil-return floor ({OIL_RETURN_FLOOR_MS:.0f} m/s)."
            )
        if (
            line_type == "suction"
            and orientation == "upflow_riser"
            and recommended.velocity_ms < SUCTION_RISER_MIN_MS
        ):
            warnings.append(
                f"Upflow riser velocity {recommended.velocity_ms:.2f} m/s is below "
                f"{SUCTION_RISER_MIN_MS:.0f} m/s oil-return minimum."
            )
        if not any(r.in_ideal_band for r in rows):
            warnings.append(
                "No catalogue size sits in the ideal velocity band — "
                "showing closest acceptable / least-bad size."
            )

    return DxPipeSizeResult(
        refrigerant=info,
        line_type=line_type,
        orientation=orientation,
        cooling_capacity_kw=cooling_capacity_kw,
        mass_flow_kg_s=mass_flow,
        delta_h_kj_kg=delta_h / 1000.0,
        density_kg_m3=rho,
        p_evap_bara=st.p_evap / 1e5,
        p_cond_bara=st.p_cond / 1e5,
        discharge_temp_c=st.discharge_temp_c,
        discharge_temp_estimated=st.discharge_estimated,
        recommended=recommended,
        rows=tuple(rows),
        warnings=tuple(warnings),
        velocity_only=True,
    )


def _recommend(rows: list[AcrSizeResult]) -> AcrSizeResult | None:
    """Smallest pipe in the ideal band; else smallest non-red; else least-bad."""
    if not rows:
        return None
    for row in rows:
        if row.in_ideal_band:
            return row
    for row in rows:
        if row.status_velocity != "red":
            return row
    # All red — if too slow, pick largest; if too fast, pick smallest.
    if rows[0].velocity_ms > VELOCITY_ABS_MAX["suction"]:
        return rows[0]
    return rows[-1]


__all__ = [
    "ACR_CATALOGUE",
    "AcrPipeEntry",
    "AcrSizeResult",
    "CoolPropUnavailableError",
    "DEFAULT_DISCHARGE_SUPERHEAT_K",
    "DxPipeSizeResult",
    "LINE_TYPE_LABELS",
    "ORIENTATION_LABELS",
    "OIL_RETURN_FLOOR_MS",
    "P_ATM_BAR",
    "PtRow",
    "PtTableResult",
    "REFRIGERANTS",
    "REFRIGERANT_GROUP_ORDER",
    "RefrigerantInfo",
    "SUCTION_RISER_MIN_MS",
    "VELOCITY_BANDS",
    "acr_catalogue",
    "find_acr",
    "get_refrigerant",
    "list_refrigerants",
    "pt_table",
    "size_dx_pipe",
    "velocity_limits",
    "velocity_status",
]
