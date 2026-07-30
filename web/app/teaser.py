"""Homepage psychrometric teaser: public calculate + post-signup hydrate helpers.

Keeps teaser math on the engine (``hvac_engine.psychrometrics.state``) and stores
canonical SI in ``hvac_teaser_state`` so hydrate into Single Point never depends
on which unit system the visitor had active on the marketing page.
"""

from __future__ import annotations

from typing import Any

from hvac_engine import psychrometrics as psy
from hvac_engine import units as eng_units

from app.units import UnitView

TEASER_STORAGE_KEY = "hvac_teaser_state"
TEASER_FORM_SESSION_KEY = "psychro_teaser_form"
P_ATM = psy.P_ATM


def _qty(U: UnitView, quantity: str, si_value: float, dp: int | None = None) -> dict[str, Any]:
    return {
        "si": si_value,
        "value": eng_units.from_si(quantity, si_value, U.system),
        "display": U.fmt(quantity, si_value, dp),
        "symbol": U.sym(quantity),
    }


def resolve_teaser_state(
    *,
    system: str,
    t_db: float,
    prop: str,
    val: float,
    pressure: float | None = None,
) -> tuple[psy.PsychroState, UnitView]:
    """Convert display inputs → SI and resolve a full ``PsychroState``."""
    if system not in eng_units.SYSTEMS:
        raise ValueError("system must be SI or IP")
    U = UnitView(system)
    t_si = U.to_si("temperature", t_db)
    p_si = P_ATM if pressure is None else U.to_si("pressure", pressure)
    if p_si <= 0:
        raise ValueError("pressure must be positive")

    prop = (prop or "rh").lower()
    if prop == "rh":
        if not 0 <= val <= 100:
            raise ValueError("relative humidity must be between 0 and 100%")
        state = psy.state(t_si, rh=val / 100.0, p=p_si)
    elif prop == "twb":
        twb_si = U.to_si("temperature", val)
        state = psy.state(t_si, twb=twb_si, p=p_si)
    else:
        raise ValueError("prop must be rh or twb")
    return state, U


def teaser_payload(state: psy.PsychroState, U: UnitView, *, prop: str, val: float) -> dict[str, Any]:
    """JSON body for the public calculate endpoint and localStorage snapshot."""
    t_dp = None if state.t_dp < -273 else state.t_dp
    return {
        "system": U.system,
        "inputs": {
            "t_db": _qty(U, "temperature", state.t_db, 2),
            "prop": prop,
            "val": val,
            "pressure": _qty(U, "pressure", state.p, 3),
            "rh_pct": round(state.rh * 100.0, 2),
        },
        "outputs": {
            "t_dp": None if t_dp is None else _qty(U, "temperature", t_dp, 2),
            "t_wb": _qty(U, "temperature", state.t_wb, 2),
            "w": _qty(U, "humidity_ratio", state.w),
            "h": _qty(U, "enthalpy", state.h, 2),
            "v": _qty(U, "specific_volume", state.v),
            "rho": _qty(U, "density", state.rho),
            "rh_pct": round(state.rh * 100.0, 2),
        },
        "si": {
            "t_db": state.t_db,
            "t_wb": state.t_wb,
            "t_dp": state.t_dp,
            "w": state.w,
            "rh": state.rh,
            "h": state.h,
            "v": state.v,
            "rho": state.rho,
            "p_w": state.p_w,
            "p": state.p,
            "prop": prop,
        },
        "symbols": {
            "temperature": U.sym("temperature"),
            "humidity_ratio": U.sym("humidity_ratio"),
            "enthalpy": U.sym("enthalpy"),
            "specific_volume": U.sym("specific_volume"),
            "density": U.sym("density"),
            "pressure": U.sym("pressure"),
        },
    }


def form_from_teaser_si(si: dict[str, Any], system: str) -> dict[str, str]:
    """Build Single Point form fields (display units) from stored SI teaser state."""
    U = UnitView(system if system in eng_units.SYSTEMS else "SI")
    prop = si.get("prop") or "rh"
    if prop not in ("rh", "twb"):
        prop = "rh"
    if prop == "rh":
        val = f"{float(si['rh']) * 100.0:.1f}"
    else:
        val = U.fmt("temperature", float(si["t_wb"]), 2)
    # Suite derives pressure from altitude; sea-level default matches teaser default.
    altitude = "0"
    if abs(float(si.get("p", P_ATM)) - P_ATM) > 0.05:
        # Approximate ISA inverse so a non-default teaser pressure lands near-right.
        # p = P_ATM * (1 - L*z)^EXP  →  z = (1 - (p/P_ATM)^(1/EXP)) / L
        p = float(si["p"])
        ratio = max(min(p / P_ATM, 1.2), 0.5)
        z_m = (1.0 - ratio ** (1.0 / 5.2559)) / 2.25577e-5
        altitude = U.fmt("altitude", z_m, 0)
    return {
        "s_t": U.fmt("temperature", float(si["t_db"]), 2),
        "s_prop": prop,
        "s_val": val,
        "altitude": altitude,
    }


def session_point_from_si(si: dict[str, Any], label: str = "A") -> dict[str, Any]:
    """Serialize SI teaser fields into the Single Point session point shape."""
    return {
        "label": label,
        "t_db": float(si["t_db"]),
        "t_wb": float(si["t_wb"]),
        "t_dp": float(si["t_dp"]),
        "w": float(si["w"]),
        "rh": float(si["rh"]),
        "h": float(si["h"]),
        "v": float(si["v"]),
        "rho": float(si["rho"]),
        "p_w": float(si["p_w"]),
        "p": float(si["p"]),
    }
