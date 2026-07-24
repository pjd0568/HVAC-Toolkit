"""Unit definitions and conversions for HVAC quantities.

Implemented from SPEC-unit-conversions.md. Conversion factors are the exact
definitions from NIST SP 811 / the SI brochure (BIPM); nothing here is copied
from any prior application — the category list was decided fresh for this product.

Design
------
The engine is canonical SI: every calculation and every ``PsychroState`` field is
in SI. This module is a *presentation-side* helper — it never runs inside a
calculation. It maps between the canonical SI value of a quantity and the value a
user sees/enters under a chosen unit *system* ("SI" or "IP").

Two directions per quantity, per system:

    to_si(quantity, display_value, system)   # user input  -> engine
    from_si(quantity, si_value, system)      # engine value -> display

Temperature is affine (offset); everything else is a single linear factor. Ratios
that are already dimensionless (relative humidity, sensible-heat ratio, contact
factor) are not units and are deliberately absent — callers render those directly.

Canonical SI unit per quantity (the number the engine actually holds):
    temperature       degC
    humidity_ratio    kg/kg dry air
    enthalpy          kJ/kg dry air
    pressure          kPa
    vol_flow          m3/h            (the volumetric-flow figure the tools take)
    mass_flow         kg/s dry air
    power             kW
    density           kg/m3
    specific_volume   m3/kg dry air
    moisture_rate     kg/s            (condensate / steam / spray water)
    altitude          m               (site elevation, for design pressure)
    duct_flow         m3/h            (same canonical value as vol_flow; a
                                       separate quantity only because duct
                                       sizing displays it in m3/s under SI,
                                       not m3/h — see hvac_engine.duct)
    velocity          m/s             (duct/pipe air or fluid velocity)
    duct_dimension    m               (duct diameter / width / height / axis)
    friction_rate     Pa/m            (straight-duct pressure loss per length)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

SYSTEMS = ("SI", "IP")

# ── Exact conversion constants (NIST SP 811) ────────────────────────────────────
_BTU_PER_LB__PER__KJ_PER_KG = 1.0 / 2.326        # 1 Btu_IT/lb = 2.326 kJ/kg exactly
_GRAINS_PER_LB__PER__KG_PER_KG = 7000.0          # 1 lb moisture/lb dry = 7000 gr/lb
_INHG_PER_KPA = 1.0 / 3.386389                   # 1 inHg (32 degF) = 3.386389 kPa
_CFM_PER_M3H = 1.0 / 1.699010796                 # 1 ft3/min = 1.699010796 m3/h
_LB_PER_KG = 2.204622622                         # 1 kg = 2.204622622 lb
_LBH_PER_KGS = _LB_PER_KG * 3600.0               # kg/s -> lb/h
_LBFT3_PER_KGM3 = 0.06242796058                  # 1 kg/m3 = 0.06242796 lb/ft3
_FT3LB_PER_M3KG = 16.01846337                    # 1 m3/kg = 16.01846337 ft3/lb
_BTUH_PER_KW = 3412.141633                       # 1 kW = 3412.141633 Btu/h
_M_PER_FT = 0.3048                               # 1 ft = 0.3048 m exactly
_LS_PER_M3H = 1.0 / 3.6                          # 1 l/s = 3.6 m3/h exactly
_FPM_PER_MS = 1.0 / (0.3048 / 60.0)              # 1 ft/min = 0.3048/60 m/s exactly
_IN_PER_M = 1.0 / 0.0254                         # 1 in = 0.0254 m exactly
_PA_PER_INWG = 249.0889                          # 1 in water gauge (conventional) = 249.0889 Pa
_M_PER_100FT = 30.48                             # 100 ft = 30.48 m exactly
_PA_PER_PSI = 6894.757                           # 1 lbf/in² (psi) = 6894.757 Pa
_PA_PER_BAR = 100_000.0                          # 1 bar = 10⁵ Pa exactly
_PA_PER_KPA = 1000.0                             # 1 kPa = 1000 Pa exactly


@dataclass(frozen=True)
class _Unit:
    """One unit for one quantity in one system."""

    symbol: str
    to_si: Callable[[float], float]      # display value -> canonical SI value
    from_si: Callable[[float], float]    # canonical SI value -> display value
    decimals: int                        # default display precision


def _linear(si_per_display: float, symbol: str, decimals: int) -> _Unit:
    """A unit that differs from the canonical SI unit by a single factor.

    ``si_per_display`` is how many SI units one display unit is worth, so
    ``to_si = value * si_per_display`` and ``from_si = value / si_per_display``.
    """
    return _Unit(
        symbol=symbol,
        to_si=lambda v: v * si_per_display,
        from_si=lambda v: v / si_per_display,
        decimals=decimals,
    )


def _identity(symbol: str, decimals: int) -> _Unit:
    return _Unit(symbol=symbol, to_si=lambda v: v, from_si=lambda v: v, decimals=decimals)


# ── Quantity table ──────────────────────────────────────────────────────────────
# UNITS[quantity][system] -> _Unit. SI entries are the canonical unit itself
# (identity) except where the conventional SI display differs from the canonical
# unit (humidity ratio shown in g/kg, moisture rate in kg/h).
UNITS: dict[str, dict[str, _Unit]] = {
    "temperature": {
        "SI": _identity("°C", 1),
        "IP": _Unit(
            symbol="°F",
            to_si=lambda f: (f - 32.0) * 5.0 / 9.0,
            from_si=lambda c: c * 9.0 / 5.0 + 32.0,
            decimals=1,
        ),
    },
    "humidity_ratio": {
        # Canonical kg/kg; SI display is g/kg (x1000), IP is grains/lb.
        "SI": _linear(1.0 / 1000.0, "g/kg", 2),
        "IP": _linear(1.0 / _GRAINS_PER_LB__PER__KG_PER_KG, "gr/lb", 1),
    },
    "enthalpy": {
        "SI": _identity("kJ/kg", 1),
        "IP": _linear(2.326, "Btu/lb", 2),
    },
    "pressure": {
        "SI": _identity("kPa", 3),
        "IP": _linear(3.386389, "inHg", 2),
    },
    "vol_flow": {
        "SI": _identity("m³/h", 0),
        "IP": _linear(1.699010796, "CFM", 0),
    },
    "mass_flow": {
        "SI": _identity("kg/s", 3),
        "IP": _linear(1.0 / _LBH_PER_KGS, "lb/h", 0),
    },
    "power": {
        "SI": _identity("kW", 1),
        "IP": _linear(1.0 / _BTUH_PER_KW, "Btu/h", 0),
    },
    "density": {
        "SI": _identity("kg/m³", 3),
        "IP": _linear(1.0 / _LBFT3_PER_KGM3, "lb/ft³", 4),
    },
    "specific_volume": {
        "SI": _identity("m³/kg", 4),
        "IP": _linear(1.0 / _FT3LB_PER_M3KG, "ft³/lb", 3),
    },
    "moisture_rate": {
        # Canonical kg/s; SI display kg/h (x3600), IP lb/h.
        "SI": _linear(1.0 / 3600.0, "kg/h", 1),
        "IP": _linear(1.0 / _LBH_PER_KGS, "lb/h", 1),
    },
    "altitude": {
        "SI": _identity("m", 0),
        "IP": _linear(_M_PER_FT, "ft", 0),
    },
    "duct_flow": {
        # Canonical m3/h (identical value to vol_flow); SI display m3/s (the
        # convention this tool's own reference used), unlike every other
        # tool's m3/h.
        "SI": _linear(3600.0, "m³/s", 3),
        "IP": _linear(1.699010796, "CFM", 0),
    },
    "velocity": {
        "SI": _identity("m/s", 2),
        "IP": _linear(1.0 / _FPM_PER_MS, "fpm", 0),
    },
    "duct_dimension": {
        # Canonical metres (matches diameter/width/height in hvac_engine.duct);
        # SI display mm, IP display inches — same "canonical != SI display"
        # pattern as humidity_ratio (kg/kg canonical, g/kg SI display).
        "SI": _linear(0.001, "mm", 0),
        "IP": _linear(1.0 / _IN_PER_M, "in", 2),
    },
    "friction_rate": {
        "SI": _identity("Pa/m", 2),
        "IP": _linear(_PA_PER_INWG / _M_PER_100FT, "in.wg/100ft", 3),
    },
    "velocity_pressure": {
        # Canonical Pa (Pv = 0.5 * rho * V^2 -- see hvac_engine.duct). A plain
        # pressure, but kept as its own quantity rather than reusing
        # "pressure" (whose canonical/SI display is kPa, sized for barometric
        # readings) -- duct velocity pressures are a few Pa to a few hundred
        # Pa, so a kPa display would round to near-zero at typical decimals.
        "SI": _identity("Pa", 2),
        "IP": _linear(_PA_PER_INWG, "in.wg", 4),
    },
    "duct_run_length": {
        # Canonical metres. A straight index-leg run (hvac_engine.fittings) is
        # typically a few metres, not the mm/in scale of "duct_dimension"
        # (width/height/diameter) -- deliberately a separate quantity so the
        # two never share a display grid. SI display m, IP display ft; 1
        # decimal place since a real run is often e.g. "4.5 m", not a whole
        # number, unlike "altitude" (also canonical m, but whole-number site
        # elevations).
        "SI": _identity("m", 1),
        "IP": _linear(_M_PER_FT, "ft", 1),
    },
}


def _unit(quantity: str, system: str) -> _Unit:
    try:
        by_system = UNITS[quantity]
    except KeyError:
        raise ValueError(f"unknown quantity: {quantity!r}")
    if system not in by_system:
        raise ValueError(f"unknown unit system: {system!r} (expected one of {SYSTEMS})")
    return by_system[system]


def symbol(quantity: str, system: str) -> str:
    """Display unit symbol for a quantity in a system, e.g. ('temperature','IP')->'°F'."""
    return _unit(quantity, system).symbol


def to_si(quantity: str, display_value: float, system: str) -> float:
    """Convert a user-entered display value into the canonical SI value."""
    return _unit(quantity, system).to_si(display_value)


def from_si(quantity: str, si_value: float, system: str) -> float:
    """Convert a canonical SI value into the display value for a system."""
    return _unit(quantity, system).from_si(si_value)


def decimals(quantity: str, system: str) -> int:
    """Default display precision (decimal places) for a quantity in a system."""
    return _unit(quantity, system).decimals


def head_pressure_triplet(pa: float, density_kg_m3: float, system: str) -> dict:
    """Format a pump/static head pressure as a three-unit display group.

    SI → Pa · kPa · bar. IP → psi · in.wg · ft of fluid (using ``density_kg_m3``
    and standard g = 9.80665, matching ``hvac_engine.pipe.STANDARD_G``).
    Returns ``{"parts": [(value, symbol), ...], "summary": "..."}``.
    """
    if system not in SYSTEMS:
        raise ValueError(f"unknown unit system: {system!r}")
    if density_kg_m3 <= 0:
        raise ValueError(f"density must be positive (got {density_kg_m3!r})")

    if system == "SI":
        parts = [
            (f"{pa:.0f}", "Pa"),
            (f"{pa / _PA_PER_KPA:.3f}", "kPa"),
            (f"{pa / _PA_PER_BAR:.4f}", "bar"),
        ]
    else:
        psi = pa / _PA_PER_PSI
        inwg = pa / _PA_PER_INWG
        height_m = pa / (density_kg_m3 * 9.80665)
        ft_fluid = height_m / _M_PER_FT
        parts = [
            (f"{psi:.3f}", "psi"),
            (f"{inwg:.3f}", "in.wg"),
            (f"{ft_fluid:.2f}", "ft fluid"),
        ]
    summary = "  ·  ".join(f"{v} {s}" for v, s in parts)
    return {"parts": parts, "summary": summary}


__all__ = [
    "SYSTEMS",
    "UNITS",
    "symbol",
    "to_si",
    "from_si",
    "decimals",
    "head_pressure_triplet",
]
