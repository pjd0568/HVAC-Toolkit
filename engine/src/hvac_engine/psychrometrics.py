"""Psychrometric properties of moist air.

Implemented from SPEC-psychrometrics.md, which cites:
  ASHRAE Handbook - Fundamentals (2017), Chapter 1 "Psychrometrics"
  Hyland & Wexler (1983), ASHRAE Transactions 89(2A)

Units: temperature degC, pressure kPa, humidity ratio kg/kg dry air,
enthalpy kJ/kg dry air, specific volume m3/kg dry air.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Standard sea-level barometric pressure, kPa
P_ATM = 101.325

# Correlation validity range, degC
T_MIN = -60.0
T_MAX = 90.0

# Ratio of molecular masses, water vapour : dry air (HOF eqn 22 coefficient)
_MW_RATIO = 0.621945

# Hyland-Wexler constants, saturation over ice (HOF eqn 5), T in K, p in Pa
_ICE = (
    -5.6745359e3,
    6.3925247,
    -9.677843e-3,
    6.2215701e-7,
    2.0747825e-9,
    -9.484024e-13,
    4.1635019,
)

# Hyland-Wexler constants, saturation over liquid water (HOF eqn 6), T in K, p in Pa
_WATER = (
    -5.8002206e3,
    1.3914993,
    -4.8640239e-2,
    4.1764768e-5,
    -1.4452093e-8,
    6.5459673,
)


def _check_range(t_c: float, name: str = "temperature") -> None:
    if not (T_MIN <= t_c <= T_MAX):
        raise ValueError(
            f"{name} {t_c:.2f} degC outside correlation validity range "
            f"[{T_MIN}, {T_MAX}] degC"
        )


def saturation_pressure(t_c: float) -> float:
    """Saturation pressure of water vapour, kPa. Hyland-Wexler (HOF eqns 5, 6)."""
    _check_range(t_c)
    t_k = t_c + 273.15
    if t_c < 0.0:
        c1, c2, c3, c4, c5, c6, c7 = _ICE
        ln_p = (
            c1 / t_k
            + c2
            + c3 * t_k
            + c4 * t_k**2
            + c5 * t_k**3
            + c6 * t_k**4
            + c7 * math.log(t_k)
        )
    else:
        c8, c9, c10, c11, c12, c13 = _WATER
        ln_p = (
            c8 / t_k
            + c9
            + c10 * t_k
            + c11 * t_k**2
            + c12 * t_k**3
            + c13 * math.log(t_k)
        )
    return math.exp(ln_p) / 1000.0  # Pa -> kPa


def humidity_ratio_from_vapour_pressure(p_w: float, p: float = P_ATM) -> float:
    """Humidity ratio from partial vapour pressure, kg/kg dry air (HOF eqn 22)."""
    if p_w < 0.0:
        raise ValueError("vapour pressure must be >= 0")
    if p_w >= p:
        raise ValueError("vapour pressure must be below barometric pressure")
    return _MW_RATIO * p_w / (p - p_w)


def vapour_pressure_from_humidity_ratio(w: float, p: float = P_ATM) -> float:
    """Partial vapour pressure from humidity ratio, kPa (inverse of HOF eqn 22)."""
    if w < 0.0:
        raise ValueError("humidity ratio must be >= 0")
    return p * w / (_MW_RATIO + w)


def saturation_humidity_ratio(t_c: float, p: float = P_ATM) -> float:
    """Humidity ratio of saturated moist air, kg/kg dry air."""
    return humidity_ratio_from_vapour_pressure(saturation_pressure(t_c), p)


def relative_humidity(t_c: float, w: float, p: float = P_ATM) -> float:
    """Relative humidity (0..1) from dry bulb and humidity ratio (HOF eqn 12)."""
    return vapour_pressure_from_humidity_ratio(w, p) / saturation_pressure(t_c)


def humidity_ratio_from_rh(t_c: float, rh: float, p: float = P_ATM) -> float:
    """Humidity ratio from dry bulb and relative humidity (0..1)."""
    if not (0.0 <= rh <= 1.0):
        raise ValueError("relative humidity must be between 0 and 1")
    return humidity_ratio_from_vapour_pressure(rh * saturation_pressure(t_c), p)


def enthalpy(t_c: float, w: float) -> float:
    """Specific enthalpy of moist air, kJ/kg dry air (HOF eqn 30)."""
    return 1.006 * t_c + w * (2501.0 + 1.86 * t_c)


def dry_bulb_from_enthalpy(h: float, w: float) -> float:
    """Dry-bulb temperature from enthalpy and humidity ratio (inverse of eqn 30)."""
    return (h - 2501.0 * w) / (1.006 + 1.86 * w)


def specific_volume(t_c: float, w: float, p: float = P_ATM) -> float:
    """Specific volume, m3/kg dry air (HOF eqn 26)."""
    return 0.287042 * (t_c + 273.15) * (1.0 + 1.607858 * w) / p


def density(t_c: float, w: float, p: float = P_ATM) -> float:
    """Moist air density, kg moist air / m3."""
    return (1.0 + w) / specific_volume(t_c, w, p)


def _w_from_wet_bulb_raw(t_c: float, t_wb_c: float, p: float) -> float:
    """HOF eqns 33/35 evaluated directly; may return negative (unphysical) values.

    Used by the bisection inversion in wet_bulb(), which needs the raw function
    value on both sides of the root.
    """
    w_s_wb = saturation_humidity_ratio(t_wb_c, p)
    if t_wb_c >= 0.0:
        num = (2501.0 - 2.326 * t_wb_c) * w_s_wb - 1.006 * (t_c - t_wb_c)
        den = 2501.0 + 1.86 * t_c - 4.186 * t_wb_c
    else:
        num = (2830.0 - 0.24 * t_wb_c) * w_s_wb - 1.006 * (t_c - t_wb_c)
        den = 2830.0 + 1.86 * t_c - 2.1 * t_wb_c
    return num / den


def humidity_ratio_from_wet_bulb(t_c: float, t_wb_c: float, p: float = P_ATM) -> float:
    """Humidity ratio from dry-bulb and thermodynamic wet-bulb (HOF eqns 33, 35)."""
    _check_range(t_c)
    _check_range(t_wb_c, "wet-bulb temperature")
    if t_wb_c > t_c:
        raise ValueError("wet-bulb temperature cannot exceed dry-bulb temperature")
    w = _w_from_wet_bulb_raw(t_c, t_wb_c, p)
    if w < 0.0:
        raise ValueError("state below the saturation curve: no valid humidity ratio")
    return w


def wet_bulb(t_c: float, w: float, p: float = P_ATM) -> float:
    """Thermodynamic wet-bulb temperature, degC. Bisection inversion of eqns 33/35."""
    _check_range(t_c)
    if w < 0.0:
        raise ValueError("humidity ratio must be >= 0")
    lo, hi = T_MIN, t_c
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _w_from_wet_bulb_raw(t_c, mid, p) < w:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    return 0.5 * (lo + hi)


def dew_point(w: float, p: float = P_ATM) -> float:
    """Dew-point temperature, degC. Bisection inversion of saturation_pressure."""
    p_w = vapour_pressure_from_humidity_ratio(w, p)
    if p_w <= saturation_pressure(T_MIN):
        raise ValueError("humidity ratio too low: dew point below correlation range")
    if p_w >= saturation_pressure(T_MAX):
        raise ValueError("humidity ratio too high: dew point above correlation range")
    lo, hi = T_MIN, T_MAX
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if saturation_pressure(mid) < p_w:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    return 0.5 * (lo + hi)


# ── Standard atmosphere (site altitude -> design barometric pressure) ───────────

# US Standard Atmosphere / ASHRAE HOF (2017) Ch.1 eqn 3 constants (troposphere).
_ISA_LAPSE_COEFF = 2.25577e-5  # 1/m
_ISA_EXPONENT = 5.2559

# Range HOF Table 1 tabulates; the lapse-rate model is not representative outside it.
Z_MIN = -500.0
Z_MAX = 9000.0


def pressure_from_altitude(z_m: float) -> float:
    """Standard-atmosphere barometric pressure at site altitude, kPa.

    ASHRAE Handbook - Fundamentals (2017), Ch.1 eqn 3 (US standard atmosphere):
    p = 101.325 * (1 - 2.25577e-5 * z) ** 5.2559, z in metres above sea level.
    This is the standard *design* pressure used for equipment sizing at a given
    site elevation -- not a live/measured weather barometric reading.
    """
    if not (Z_MIN <= z_m <= Z_MAX):
        raise ValueError(
            f"altitude {z_m:.0f} m is outside the standard-atmosphere model range "
            f"({Z_MIN:.0f} to {Z_MAX:.0f} m)"
        )
    return P_ATM * (1.0 - _ISA_LAPSE_COEFF * z_m) ** _ISA_EXPONENT


@dataclass(frozen=True)
class PsychroState:
    """A fully resolved psychrometric state."""

    t_db: float  # dry-bulb temperature, degC
    t_wb: float  # thermodynamic wet-bulb temperature, degC
    t_dp: float  # dew-point temperature, degC
    w: float  # humidity ratio, kg/kg dry air
    rh: float  # relative humidity, 0..1
    h: float  # specific enthalpy, kJ/kg dry air
    v: float  # specific volume, m3/kg dry air
    rho: float  # moist air density, kg/m3
    p_w: float  # partial vapour pressure, kPa
    p: float  # barometric pressure, kPa


def _from_w(t_db: float, w: float, p: float) -> PsychroState:
    _check_range(t_db)
    if w < 0.0:
        raise ValueError("humidity ratio must be >= 0")
    w_s = saturation_humidity_ratio(t_db, p)
    if w > w_s * (1.0 + 1e-9):
        raise ValueError(
            f"supersaturated: w={w:.6f} exceeds saturation humidity ratio "
            f"{w_s:.6f} kg/kg at {t_db:.2f} degC"
        )
    return PsychroState(
        t_db=t_db,
        t_wb=wet_bulb(t_db, w, p),
        t_dp=dew_point(w, p) if w > 1e-12 else float("-inf"),
        w=w,
        rh=relative_humidity(t_db, w, p),
        h=enthalpy(t_db, w),
        v=specific_volume(t_db, w, p),
        rho=density(t_db, w, p),
        p_w=vapour_pressure_from_humidity_ratio(w, p),
        p=p,
    )


def state(
    t_db: float | None = None,
    *,
    rh: float | None = None,
    w: float | None = None,
    twb: float | None = None,
    tdp: float | None = None,
    h: float | None = None,
    p: float = P_ATM,
) -> PsychroState:
    """Resolve a full psychrometric state from a valid property pair.

    Accepted pairs: (t_db, rh) | (t_db, w) | (t_db, twb) | (t_db, tdp) |
    (t_db, h) | (h, w).
    """
    given = {k: v for k, v in dict(rh=rh, w=w, twb=twb, tdp=tdp, h=h).items()
             if v is not None}

    if t_db is None:
        if set(given) != {"h", "w"}:
            raise ValueError("without t_db, exactly h and w must be given")
        return _from_w(dry_bulb_from_enthalpy(h, w), w, p)

    if len(given) != 1:
        raise ValueError(
            f"exactly one of rh/w/twb/tdp/h must accompany t_db, got: "
            f"{sorted(given) or 'none'}"
        )

    key, val = next(iter(given.items()))
    if key == "w":
        return _from_w(t_db, val, p)
    if key == "rh":
        return _from_w(t_db, humidity_ratio_from_rh(t_db, val, p), p)
    if key == "twb":
        return _from_w(t_db, humidity_ratio_from_wet_bulb(t_db, val, p), p)
    if key == "tdp":
        if val > t_db:
            raise ValueError("dew point cannot exceed dry-bulb temperature")
        p_w = saturation_pressure(val)
        return _from_w(t_db, humidity_ratio_from_vapour_pressure(p_w, p), p)
    # key == "h"
    return _from_w(t_db, (val - 1.006 * t_db) / (2501.0 + 1.86 * t_db), p)
