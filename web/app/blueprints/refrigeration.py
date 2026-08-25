"""Refrigeration / DX tools — PT table + pipe sizer.

Per specs/SPEC-refrigeration-dx.md. Classic routes redirect to V2.
"""

from __future__ import annotations

from flask import Blueprint
from flask_login import login_required
from hvac_engine import refrigeration as eng

from app.access_gate import require_module

bp = Blueprint("refrigeration", __name__)


def _f(raw: str, label: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{raw}' is not a number ({label})")


def _s(args, key: str, default: str) -> str:
    raw = args.get(key)
    return raw if raw not in (None, "") else default


def _refrigerant_groups():
    by_group: dict[str, list] = {g: [] for g in eng.REFRIGERANT_GROUP_ORDER}
    for info in eng.list_refrigerants():
        by_group.setdefault(info.group, []).append(info)
    return [(g, by_group[g]) for g in eng.REFRIGERANT_GROUP_ORDER if by_group.get(g)]


def _pt_points(result) -> list[dict[str, float]]:
    if result is None:
        return []
    rows: list[dict[str, float]] = []
    for row in result.rows:
        if row.skipped:
            continue
        rows.append({
            "t": float(row.t_c),
            "liq": round(float(row.p_bubble_barg), 3),
            "vap": round(float(row.p_dew_barg), 3),
        })
    return rows


def _compute_pt(args) -> dict:
    refrigerant = _s(args, "refrigerant", "r32")
    error = None
    result = None
    try:
        result = eng.pt_table(refrigerant, t_min_c=-40.0, t_max_c=60.0, t_step_k=1.0)
    except (ValueError, eng.CoolPropUnavailableError) as exc:
        error = str(exc)
    return {
        "fields": {"refrigerant": refrigerant},
        "result": result,
        "error": error,
        "refrigerant_groups": _refrigerant_groups(),
        "pt_points": _pt_points(result),
    }


def _compute_pipe(args) -> dict:
    fields = {
        "capacity_kw": _s(args, "capacity_kw", "10"),
        "refrigerant": _s(args, "refrigerant", "r32"),
        "tevap_c": _s(args, "tevap_c", "-5"),
        "tcond_c": _s(args, "tcond_c", "45"),
        "subcooling_k": _s(args, "subcooling_k", "5"),
        "superheat_k": _s(args, "superheat_k", "5"),
        "line_type": _s(args, "line_type", "suction"),
        "orientation": _s(args, "orientation", "horizontal"),
        "discharge_temp_c": _s(args, "discharge_temp_c", ""),
        "selected": _s(args, "selected", ""),
    }
    error = None
    result = None
    try:
        dis_raw = fields["discharge_temp_c"].strip()
        discharge = _f(dis_raw, "discharge temp") if dis_raw else None
        result = eng.size_dx_pipe(
            cooling_capacity_kw=_f(fields["capacity_kw"], "capacity"),
            refrigerant_id=fields["refrigerant"],
            evaporating_temp_c=_f(fields["tevap_c"], "evaporating temp"),
            condensing_temp_c=_f(fields["tcond_c"], "condensing temp"),
            subcooling_k=_f(fields["subcooling_k"], "subcooling"),
            superheat_k=_f(fields["superheat_k"], "superheat"),
            line_type=fields["line_type"],  # type: ignore[arg-type]
            orientation=fields["orientation"],  # type: ignore[arg-type]
            discharge_temp_c=discharge,
        )
        if not fields["selected"] and result.recommended is not None:
            fields["selected"] = result.recommended.entry.nominal_inch
    except (ValueError, eng.CoolPropUnavailableError) as exc:
        error = str(exc)

    ideal = None
    if fields["line_type"] in eng.VELOCITY_BANDS:
        lo, hi, _ = eng.velocity_limits(
            fields["line_type"],  # type: ignore[arg-type]
            fields["orientation"] if fields["line_type"] == "suction" else "horizontal",  # type: ignore[arg-type]
        )
        ideal = (lo, hi)

    detail = None
    table_rows = []
    if result is not None:
        for row in result.rows:
            selected = row.entry.nominal_inch == fields["selected"]
            table_rows.append(
                {
                    "label": row.entry.label,
                    "nominal": row.entry.nominal_inch,
                    "od_mm": f"{row.entry.od_mm:.2f}",
                    "id_mm": f"{row.entry.id_mm:.2f}",
                    "velocity": f"{row.velocity_ms:.2f}",
                    "status_velocity": row.status_velocity,
                    "selected": selected,
                    "in_ideal": row.in_ideal_band,
                }
            )
            if selected:
                detail = row

    return {
        "fields": fields,
        "result": result,
        "error": error,
        "table_rows": table_rows,
        "detail": detail,
        "ideal_band": ideal,
        "refrigerant_groups": _refrigerant_groups(),
        "line_types": eng.LINE_TYPE_LABELS,
        "orientations": eng.ORIENTATION_LABELS,
    }


def _compute_diagnostics(args) -> dict:
    fields = {
        "refrigerant": _s(args, "refrigerant", "r32"),
        "p_unit": _s(args, "p_unit", "barg"),
        "p_low": _s(args, "p_low", "7.5"),
        "p_high": _s(args, "p_high", "22"),
        "t_suction_c": _s(args, "t_suction_c", "5"),
        "t_liquid_c": _s(args, "t_liquid_c", "35"),
    }
    if fields["p_unit"] not in ("barg", "bara"):
        fields["p_unit"] = "barg"
    error = None
    result = None
    try:
        p_lo = _f(fields["p_low"], "low-side pressure")
        p_hi = _f(fields["p_high"], "high-side pressure")
        if fields["p_unit"] == "bara":
            p_lo = eng._bara_to_barg(p_lo)
            p_hi = eng._bara_to_barg(p_hi)
        result = eng.diagnose_sh_sc(
            fields["refrigerant"],
            p_low_barg=p_lo,
            p_high_barg=p_hi,
            t_suction_c=_f(fields["t_suction_c"], "suction temperature"),
            t_liquid_c=_f(fields["t_liquid_c"], "liquid temperature"),
        )
    except (ValueError, eng.CoolPropUnavailableError) as exc:
        error = str(exc)
    return {
        "fields": fields,
        "result": result,
        "error": error,
        "refrigerant_groups": _refrigerant_groups(),
    }


@bp.get("/")
@require_module("refrig.pt_table")
def index():
    from app.ui_prefs import redirect_to_v2

    return redirect_to_v2("v2.refrig_picker")


@bp.get("/pt-table")
@require_module("refrig.pt_table")
def pt_table_classic():
    from app.ui_prefs import redirect_to_v2

    return redirect_to_v2("v2.refrig_pt_table")


@bp.get("/pipe-sizer")
@require_module("refrig.pipe_sizer")
def pipe_sizer_classic():
    from app.ui_prefs import redirect_to_v2

    return redirect_to_v2("v2.refrig_pipe_sizer")


@bp.get("/diagnostics")
@require_module("refrig.diagnostics")
def diagnostics_classic():
    from app.ui_prefs import redirect_to_v2

    return redirect_to_v2("v2.refrig_diagnostics")


@bp.get("/charge")
@login_required
def charge_classic():
    from app.ui_prefs import redirect_to_v2

    return redirect_to_v2("v2.refrig_charge")
