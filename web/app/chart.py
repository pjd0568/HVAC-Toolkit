"""Builds the JSON payload for the psychrometric chart component (psychart.js)
and the matching PDF chart renderer (app.reports.chart).

Both consumers read this *one* payload, so their geometry can never disagree.
Neither hardcodes a unit or axis label any more: every coordinate here is
already converted into the caller's active display system (SI or IP), and the
payload carries the unit symbols, a sensible grid step, and pre-formatted
per-point labels (e.g. "21.0 °C" / "69.8 °F") for both the axis text and the
dashed guide-line call-outs -- one formatting pass, not one per renderer.
"""

from __future__ import annotations

import math

from hvac_engine import psychrometrics as psy
from hvac_engine import units as eng_units


def _nice_step(span: float, target_ticks: int = 6) -> float:
    """A 'round' grid step (1/2/2.5/5 x10^n) giving roughly target_ticks divisions."""
    if span <= 0:
        return 1.0
    raw = span / target_ticks
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if step >= raw - 1e-9:
            return step
    return 10 * mag


def chart_payload(points, segments=(), p: float = 101.325, system: str = "SI") -> dict:
    """points: [{label, t, w}] with t in degC and w in kg/kg dry air (engine SI --
    callers always pass raw engine values here, never pre-converted). segments:
    index pairs into points. system: "SI" or "IP", the active display system --
    every number in the returned payload is already converted, so neither
    psychart.js nor app.reports.chart has to touch hvac_engine.units itself.
    """
    ts = [pt["t"] for pt in points]
    ws = [pt["w"] for pt in points]
    t_min_si = min(-5.0, min(ts) - 4.0)
    t_max_si = max(35.0, max(ts) + 4.0)
    w_max_si = max(0.012, max(ws) * 1.3)  # kg/kg dry air, SI

    def curve_si(rh, step):
        out = []
        t = t_min_si
        while t <= t_max_si + 1e-9:
            out.append((round(t, 2), psy.humidity_ratio_from_rh(t, rh, p)))
            t += step
        return out

    sat_si = curve_si(1.0, 0.5)
    rh_curves_si = {str(r): curve_si(r / 100.0, 1.0) for r in (20, 40, 60, 80)}

    def conv_t(t_c: float) -> float:
        return eng_units.from_si("temperature", t_c, system)

    def conv_w(w_kgkg: float) -> float:
        return eng_units.from_si("humidity_ratio", w_kgkg, system)

    def conv_curve(curve):
        return [[round(conv_t(t), 3), round(conv_w(w), 3)] for t, w in curve]

    t_sym = eng_units.symbol("temperature", system)
    w_sym = eng_units.symbol("humidity_ratio", system)
    t_dp = eng_units.decimals("temperature", system)
    w_dp = eng_units.decimals("humidity_ratio", system)

    t_min, t_max = conv_t(t_min_si), conv_t(t_max_si)
    w_max = conv_w(w_max_si)

    disp_points = []
    for pt in points:
        t_disp = conv_t(pt["t"])
        w_disp = conv_w(pt["w"])
        disp_points.append({
            "label": pt["label"],
            "t": round(t_disp, 3),
            "w": round(w_disp, 3),
            "t_label": f"{t_disp:.{t_dp}f} {t_sym}",
            "w_label": f"{w_disp:.{w_dp}f} {w_sym}",
        })

    return {
        "t_min": t_min,
        "t_max": t_max,
        "w_max": w_max,
        "t_step": _nice_step(t_max - t_min),
        "w_step": _nice_step(w_max),
        "t_sym": t_sym,
        "w_sym": w_sym,
        "t_dp": t_dp,
        "w_dp": w_dp,
        "sat": conv_curve(sat_si),
        "rh_curves": {k: conv_curve(v) for k, v in rh_curves_si.items()},
        "points": disp_points,
        "segments": [list(s) for s in segments],
    }
