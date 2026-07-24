"""Pipe Sizing tool — Stage 1 sizer + Stage 2 system ΔP + Stage 3 lift/head.

Per specs/SPEC-pipe-sizing.md. GET-driven; system rows use `sys_*` query params
with an AJAX `/api/system-state` endpoint (same instant-update exception as
duct Index Leg). Stage 3 uses `circuit` + `lift` on the same form/API.
"""

from __future__ import annotations

import csv
import io
from urllib.parse import urlencode

from flask import Blueprint, Response, jsonify, render_template, request

from hvac_engine import pipe as eng
from hvac_engine import pipe_fittings as pfit
from hvac_engine import units as eng_units

from app.access_gate import require_module
from app.reports.builder import build_pdf
from app.reports.helpers import pdf_response, report_meta_from_form
from app.units import current_view

bp = Blueprint("pipe", __name__)

TOOL_TITLE = "Hydronics - Pipe Sizing"

GLYCOL_CONCENTRATIONS_BY_FLUID = {
    k: list(v) for k, v in eng.GLYCOL_CONCENTRATIONS_PCT.items()
}

SYS_ROW_TYPE_LABELS = {
    "straight": "Straight pipe",
    "fitting": "Fitting / valve",
    "device": "Device (manual ΔP)",
}

SYS_ROW_FIELDS = ("type", "dn", "flow_ls", "length", "fitting", "label", "dp")

DEFAULT_SYS_LENGTH_SI = 5.0  # m
DEFAULT_SYS_DP_SI = 10.0     # Pa
DEFAULT_SYS_LABEL = "Device"
DEFAULT_LIFT_SI = 0.0        # m — no lift until the engineer enters one
MAX_SYS_ROWS = 60

# PDF column widths (mm) for the system table — sum ≈ 178 mm content width.
_SYS_PDF_COL_WIDTHS_MM = [8, 28, 22, 18, 18, 40, 22, 22]  # sum = 178


def _glycol_options_for_view(U) -> dict[str, list[dict[str, object]]]:
    """Concentration choices with unit-aware freeze-point labels for the UI."""
    out: dict[str, list[dict[str, object]]] = {}
    for fluid, concs in eng.GLYCOL_CONCENTRATIONS_PCT.items():
        rows: list[dict[str, object]] = []
        for pct in concs:
            fp_c = eng.glycol_freeze_point_c(fluid, pct)
            fp_disp = f"{U.fmt('temperature', fp_c)} {U.sym('temperature')}"
            rows.append({
                "pct": pct,
                "label": f"{pct} % — fp {fp_disp}",
            })
        out[fluid] = rows
    return out


@bp.context_processor
def _inject_glycol_concentrations():
    U = current_view()
    return {
        "glycol_concentrations_by_fluid": GLYCOL_CONCENTRATIONS_BY_FLUID,
        "glycol_options_by_fluid": _glycol_options_for_view(U),
    }


def _delta_t_k(raw: str, U) -> float:
    """ΔT is a temperature difference — °F difference converts to K, not absolute °F."""
    val = _f(raw, "ΔT")
    if U.system == "IP":
        return val * 5.0 / 9.0
    return val


def _f(raw: str, label: str = "value") -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{raw}' is not a number ({label})")


def _choice(raw: str, allowed: set[str], default: str) -> str:
    return raw if raw in allowed else default


def _build_url(path: str, params: dict[str, str], **updates) -> str:
    merged = {**params, **{k: str(v) for k, v in updates.items()}}
    return f"{path}?{urlencode(merged)}"


def _resolve_glycol_pct(fluid: str, raw: str) -> int:
    """Pick a valid catalogue concentration for the fluid."""
    concs = eng.glycol_concentrations(fluid)  # type: ignore[arg-type]
    try:
        pct = int(raw)
    except (TypeError, ValueError):
        pct = concs[len(concs) // 2]
    if pct in concs:
        return pct
    return min(concs, key=lambda c: abs(c - pct))


def _s(args, key: str, default: str) -> str:
    raw = args.get(key)
    return raw if raw not in (None, "") else default


def _to_si_or_default(get, field: str, quantity: str, U, default_si: float) -> float:
    raw = get(field)
    if raw in (None, ""):
        return default_si
    return U.to_si(quantity, _f(raw, field))


# ── Stage 1 sizer ─────────────────────────────────────────────────────────────

def _compute_state(args, U):
    """Parse query args and return template context pieces for Stage 1."""
    mode = _choice(args.get("mode", ""), {"from_load", "flow_known"}, "from_load")
    application = _choice(args.get("application", ""), set(eng.CIBSE_LIMITS), "lthw")
    fluid = _choice(args.get("fluid", ""), set(eng.FLUID_LABELS), "water")
    material = _choice(args.get("material", ""), set(eng.MATERIAL_LABELS), "carbon_steel")

    glycol_pct = 0
    if fluid != "water":
        glycol_pct = _resolve_glycol_pct(fluid, args.get("glycol_pct", ""))

    fields = {
        "mode": mode,
        "application": application,
        "fluid": fluid,
        "material": material,
        "glycol_pct": str(glycol_pct),
        "load": args.get("load", "100"),
        "delta_t": args.get("delta_t", "20"),
        "lwt": args.get("lwt", "50"),
        "flow_ls": args.get("flow_ls", "1.0"),
    }

    error = None
    flow = None
    props = None
    rows = []
    selected = None
    mean_t_c = None
    duty_flow_ls = None

    try:
        delta_t_k = _delta_t_k(fields["delta_t"], U)
        lwt_c = U.to_si("temperature", _f(fields["lwt"], "LWT"))
        mean_t_c = eng.mean_water_temperature_c(lwt_c, delta_t_k)

        conc = 0 if fluid == "water" else glycol_pct
        props = eng.fluid_properties(fluid, mean_t_c, concentration_pct=conc)

        if mode == "from_load":
            load_kw = U.to_si("power", _f(fields["load"], "load"))
            flow = eng.flow_from_load(load_kw, delta_t_k, props)
        else:
            flow_ls = _f(fields["flow_ls"], "flow")
            flow = eng.complete_known_flow(
                eng.flow_from_volume_rate(eng.volume_flow_m3h_from_ls(flow_ls)),
                props,
            )

        duty_flow_ls = eng.volume_flow_ls(flow.volume_flow_m3h)
        rows = eng.evaluate_catalogue(flow.volume_flow_m3h, material, props, application)

        selected_dn_raw = args.get("selected_dn", "")
        selected_dn = None
        if selected_dn_raw.isdigit():
            selected_dn = int(selected_dn_raw)
        if selected_dn is None:
            selected_dn = eng.default_selected_dn(rows, application)
        selected = eng.find_result(rows, selected_dn) if selected_dn is not None else None
        if selected is None and rows:
            selected = rows[0]
        if selected is not None:
            fields["selected_dn"] = str(selected.entry.dn)

    except ValueError as exc:
        error = str(exc)

    table_rows = []
    query_base = {k: v for k, v in fields.items()}
    if selected is not None:
        query_base["selected_dn"] = str(selected.entry.dn)
    # Preserve Stage 2/3 params when clicking a size row.
    for key, value in args.items():
        if key.startswith("sys_") or key.startswith("stage_") or key in ("circuit", "lift"):
            query_base[key] = value

    for row in rows:
        table_rows.append({
            "dn": row.entry.dn,
            "label": row.entry.label,
            "velocity": U.fmt("velocity", row.velocity_ms),
            "velocity_sym": U.sym("velocity"),
            "friction": U.fmt("friction_rate", row.friction_rate_pa_per_m),
            "friction_sym": U.sym("friction_rate"),
            "status_velocity": row.status_velocity,
            "status_friction": row.status_friction,
            "selected": selected is not None and row.entry.dn == selected.entry.dn,
            "url": _build_url(request.path, query_base, selected_dn=row.entry.dn),
        })

    flow_display = None
    if flow is not None:
        m3h = flow.volume_flow_m3h
        flow_display = {
            "ls": f"{eng.volume_flow_ls(m3h):.3f}",
            "m3h": f"{m3h:.3f}",
            "mass_kg_s": f"{flow.mass_flow_kg_s:.4f}",
        }

    pipe_spec = None
    detail = None
    if selected is not None and props is not None and flow is not None:
        kg_m = eng.pipe_mass_per_m(material, selected.entry)
        wall_m = eng.wall_thickness_m(selected.entry)
        pipe_spec = {
            "label": selected.entry.label,
            "material": eng.MATERIAL_LABELS[material],
            "id": U.html("duct_dimension", selected.entry.id_m),
            "od": U.html("duct_dimension", selected.entry.od_m),
            "wall": U.html("duct_dimension", wall_m),
            "kg_m": f"{kg_m:.2f} kg/m",
        }
        detail = {
            "flow_ls": f"{eng.volume_flow_ls(flow.volume_flow_m3h):.3f} l/s",
            "flow_m3h": f"{flow.volume_flow_m3h:.3f} m³/h",
            "mass_flow": f"{flow.mass_flow_kg_s:.4f} kg/s",
            "velocity": U.html("velocity", selected.velocity_ms),
            "friction": U.html("friction_rate", selected.friction_rate_pa_per_m),
            "reynolds": f"{selected.reynolds:.0f}",
            "regime": selected.regime,
            "friction_factor": f"{selected.friction_factor:.4f}",
            "fluid": eng.FLUID_LABELS[fluid],
            "concentration": "—" if fluid == "water" else f"{glycol_pct} %",
            "mean_temp": U.html("temperature", mean_t_c),
            "density": U.html("density", props.density_kg_m3),
            "viscosity": f"{props.dynamic_viscosity_pa_s * 1000:.3f} mPa·s",
            "cp": f"{props.cp_j_kgk:.0f} J/(kg·K)",
            "freezing": U.html("temperature", props.freezing_point_c),
            "status_velocity": selected.status_velocity,
            "status_friction": selected.status_friction,
        }

    fb = eng.FRICTION_BANDS

    return {
        "fields": fields,
        "error": error,
        "flow_display": flow_display,
        "duty_flow_ls": duty_flow_ls,
        "table_rows": table_rows,
        "catalogue_results": rows,
        "pipe_spec": pipe_spec,
        "detail": detail,
        "props": props,
        "limits": {
            "velocity_note": (
                "Per DN: 15–50 ideal 0.8–1.2 m/s (max 1.5); "
                "65–150 ideal 1.2–1.8 (max 2.5); 200+ ideal 1.8–2.5 (max 3.0)"
            ),
            "friction_ideal": (
                f"{U.fmt('friction_rate', fb['ideal_min_pa_per_m'])} – "
                f"{U.fmt('friction_rate', fb['ideal_max_pa_per_m'])} "
                f"{U.sym('friction_rate')}"
            ),
            "friction_lower": (
                f"{U.fmt('friction_rate', fb['lower_min_pa_per_m'])} – "
                f"{U.fmt('friction_rate', fb['lower_max_pa_per_m'])} "
                f"{U.sym('friction_rate')} (CAPEX-heavy)"
            ),
            "friction_upper": (
                f"{U.fmt('friction_rate', fb['upper_min_pa_per_m'])} – "
                f"{U.fmt('friction_rate', fb['upper_max_pa_per_m'])} "
                f"{U.sym('friction_rate')} (CAPEX-light)"
            ),
        },
        "application_label": eng.APPLICATION_LABELS[application],
    }


# ── Stage 2 system builder ────────────────────────────────────────────────────

def _duty_context(args, U):
    """Fluid / material / duty flow shared by system rows — raises ValueError
    if Design Inputs can't resolve (same parse path as Stage 1)."""
    state = _compute_state(args, U)
    if state["error"]:
        raise ValueError(state["error"])
    if state["props"] is None or state["duty_flow_ls"] is None:
        raise ValueError("duty flow and fluid properties are required")
    material = state["fields"]["material"]
    application = state["fields"]["application"]
    default_dn = None
    if state.get("fields", {}).get("selected_dn"):
        try:
            default_dn = int(state["fields"]["selected_dn"])
        except (TypeError, ValueError):
            default_dn = None
    if default_dn is None and state["catalogue_results"]:
        default_dn = state["catalogue_results"][0].entry.dn
    return {
        "props": state["props"],
        "material": material,
        "application": application,
        "duty_flow_ls": state["duty_flow_ls"],
        "default_dn": default_dn,
        "dn_options": [
            {"dn": e.dn, "label": e.label}
            for e in eng.catalogue_for(material)  # type: ignore[arg-type]
        ],
    }


def _sys_field_getter(args, index: int | None):
    """Getter for sys_* fields. index=None → stage_* draft fields."""
    if index is None:
        prefix = "stage_"

        def get(field: str) -> str:
            return _s(args, f"{prefix}{field}", "")

        return get

    def get(field: str) -> str:
        return _s(args, f"sys_{field}_{index}", "")

    return get


def _fitting_options_grouped() -> list[dict]:
    """Category-grouped options for <optgroup> rendering."""
    groups = []
    for cat, label in pfit.CATEGORY_LABELS.items():
        items = [
            {"key": f.key, "label": f"{f.label} (K={f.k:g})", "k": f.k}
            for f in pfit.fittings_by_category(cat)
        ]
        groups.append({"category": cat, "label": label, "fittings": items})
    return groups


def _compute_sys_row(get, ctx: dict, U) -> dict:
    """Evaluate one system row. Raises ValueError on bad inputs."""
    row_type = get("type") or "straight"
    if row_type not in SYS_ROW_TYPE_LABELS:
        raise ValueError(f"unknown row type: {row_type!r}")

    if row_type == "device":
        label = get("label") or DEFAULT_SYS_LABEL
        dp_si = _to_si_or_default(get, "dp", "velocity_pressure", U, DEFAULT_SYS_DP_SI)
        dp_pa = pfit.device_pressure_drop(dp_si)
        return {
            "type": row_type,
            "type_label": SYS_ROW_TYPE_LABELS[row_type],
            "label": label,
            "dn": None,
            "dn_label": "—",
            "flow_ls_display": "",
            "velocity_display": "—",
            "velocity_pressure_display": "—",
            "friction_or_k_display": "—",
            "k": None,
            "fitting_key": "",
            "length_display": "",
            "dp_display": U.fmt("velocity_pressure", dp_pa),
            "dp_pa": dp_pa,
        }

    # Resolve DN against the current material catalogue.
    dn_raw = get("dn")
    try:
        dn = int(dn_raw) if dn_raw not in (None, "") else int(ctx["default_dn"])
    except (TypeError, ValueError):
        raise ValueError(f"'{dn_raw}' is not a valid DN")
    entry = next((e for e in eng.catalogue_for(ctx["material"]) if e.dn == dn), None)
    if entry is None:
        raise ValueError(f"DN {dn} is not in the {ctx['material']} catalogue")

    # Flow: blank → duty flow from Design Inputs.
    flow_raw = get("flow_ls")
    if flow_raw in (None, ""):
        flow_ls = float(ctx["duty_flow_ls"])
    else:
        flow_ls = _f(flow_raw, "flow")
    if flow_ls <= 0:
        raise ValueError("flow must be positive")

    flow_m3h = eng.volume_flow_m3h_from_ls(flow_ls)
    sized = eng.evaluate_size(
        flow_m3h, entry, ctx["props"], ctx["material"], ctx["application"],
    )
    pv = eng.velocity_pressure(sized.velocity_ms, ctx["props"].density_kg_m3)

    if row_type == "straight":
        length_si = _to_si_or_default(
            get, "length", "duct_run_length", U, DEFAULT_SYS_LENGTH_SI,
        )
        dp_pa = pfit.straight_pressure_drop(length_si, sized.friction_rate_pa_per_m)
        return {
            "type": row_type,
            "type_label": SYS_ROW_TYPE_LABELS[row_type],
            "label": SYS_ROW_TYPE_LABELS[row_type],
            "dn": dn,
            "dn_label": entry.label,
            "flow_ls_display": f"{flow_ls:.3f}",
            "velocity_display": U.fmt("velocity", sized.velocity_ms),
            "velocity_pressure_display": U.fmt("velocity_pressure", pv),
            "friction_or_k_display": U.fmt("friction_rate", sized.friction_rate_pa_per_m),
            "k": None,
            "fitting_key": "",
            "length_display": U.fmt("duct_run_length", length_si),
            "dp_display": U.fmt("velocity_pressure", dp_pa),
            "dp_pa": dp_pa,
        }

    # fitting
    fitting_key = get("fitting") or pfit.FITTINGS[0].key
    fitting = pfit.FITTINGS_BY_KEY.get(fitting_key)
    if fitting is None:
        raise ValueError(f"unknown fitting: {fitting_key!r}")
    dp_pa = pfit.fitting_pressure_drop(fitting.k, pv)
    return {
        "type": row_type,
        "type_label": SYS_ROW_TYPE_LABELS[row_type],
        "label": fitting.label,
        "dn": dn,
        "dn_label": entry.label,
        "flow_ls_display": f"{flow_ls:.3f}",
        "velocity_display": U.fmt("velocity", sized.velocity_ms),
        "velocity_pressure_display": U.fmt("velocity_pressure", pv),
        "friction_or_k_display": f"K={fitting.k:g}",
        "k": fitting.k,
        "fitting_key": fitting_key,
        "length_display": "",
        "dp_display": U.fmt("velocity_pressure", dp_pa),
        "dp_pa": dp_pa,
    }


def _blank_sys_row(row_type: str, fitting_key: str) -> dict:
    return {
        "type": row_type or "straight",
        "type_label": SYS_ROW_TYPE_LABELS.get(row_type, "—"),
        "label": "—",
        "dn": None,
        "dn_label": "—",
        "flow_ls_display": "",
        "velocity_display": "—",
        "velocity_pressure_display": "—",
        "friction_or_k_display": "—",
        "k": None,
        "fitting_key": fitting_key or "",
        "length_display": "",
        "dp_display": "—",
        "dp_pa": 0.0,
    }


def _pressure_triplet(pa: float, density_kg_m3: float, U) -> dict:
    """SI: Pa·kPa·bar; IP: psi·in.wg·ft fluid — see SPEC Stage 3."""
    return eng_units.head_pressure_triplet(pa, density_kg_m3, U.system)


def _compute_head_state(args, U, *, friction_pa: float, density_kg_m3: float | None) -> dict:
    """Stage 3 lift / static head / pump duty, using Stage 2 friction total."""
    circuit = _choice(args.get("circuit", ""), set(eng.CIRCUIT_LABELS), "pressurised")
    lift_raw = _s(args, "lift", "")
    fields = {
        "circuit": circuit,
        "lift": lift_raw if lift_raw else U.fmt("duct_run_length", DEFAULT_LIFT_SI),
    }

    blank = {
        "fields": fields,
        "circuit_label": eng.CIRCUIT_LABELS[circuit],
        "lift_sym": U.sym("duct_run_length"),
        "lift_display": fields["lift"],
        "lift_visible": circuit == "open",
        "note": "",
        "static": None,
        "friction": None,
        "pump": None,
        "static_applies": circuit == "open",
        "error": None,
        "fluid_label": None,
    }

    if density_kg_m3 is None:
        blank["error"] = "Resolve Design Inputs (fluid / duty) to calculate static head."
        return blank

    try:
        if lift_raw in ("", None):
            lift_m = DEFAULT_LIFT_SI
        else:
            lift_m = U.to_si("duct_run_length", _f(lift_raw, "lift"))
        # Pressurised closed circuits do not use lift for pump duty (return cancels it).
        lift_for_calc = lift_m if circuit == "open" else 0.0
        hb = eng.head_breakdown(circuit, lift_for_calc, density_kg_m3, friction_pa)  # type: ignore[arg-type]
        # Keep the typed lift for the open-tank field even when pressurised (so
        # switching back to open restores the value); store actual entered height.
        lift_display = U.fmt("duct_run_length", lift_m)
    except ValueError as exc:
        blank["error"] = str(exc)
        return blank

    note = (
        "Open tank: required pump head = static lift + friction "
        "(return does not cancel the lift to the open water surface)."
        if hb.static_applies_to_pump
        else (
            "Pressurised closed circuit: return / gravity cancels physical lift — "
            "circulating pump head = friction only. Static lift is not used."
        )
    )
    static_triplet = (
        _pressure_triplet(hb.static_head_pa, density_kg_m3, U)
        if hb.static_applies_to_pump
        else {"parts": [], "summary": "Not applicable (closed circuit)"}
    )
    return {
        "fields": fields,
        "circuit_label": eng.CIRCUIT_LABELS[circuit],
        "lift_sym": U.sym("duct_run_length"),
        "lift_display": lift_display,
        "lift_visible": circuit == "open",
        "note": note,
        "static": static_triplet,
        "friction": _pressure_triplet(hb.friction_pa, density_kg_m3, U),
        "pump": _pressure_triplet(hb.pump_duty_pa, density_kg_m3, U),
        "static_applies": hb.static_applies_to_pump,
        "error": None,
        "static_pa": hb.static_head_pa,
        "friction_pa": hb.friction_pa,
        "pump_duty_pa": hb.pump_duty_pa,
        "fluid_label": None,  # filled by caller when props known
    }


def _compute_system_state(args, U) -> dict:
    """Full Stage 2 system state: per-row isolation + staging draft + margin."""
    try:
        ctx = _duty_context(args, U)
        ctx_error = None
    except ValueError as exc:
        ctx = None
        ctx_error = str(exc)

    try:
        row_count = int(_s(args, "sys_row_count", "0") or "0")
    except (TypeError, ValueError):
        row_count = 0
    row_count = max(0, min(MAX_SYS_ROWS, row_count))

    rows = []
    total_pa = 0.0
    for i in range(row_count):
        get = _sys_field_getter(args, i)
        raw = {field: get(field) for field in SYS_ROW_FIELDS}
        if ctx is None:
            row = _blank_sys_row(raw.get("type", ""), raw.get("fitting", ""))
            row["error"] = ctx_error
        else:
            try:
                row = _compute_sys_row(get, ctx, U)
                row["error"] = None
            except ValueError as exc:
                row = _blank_sys_row(raw.get("type", ""), raw.get("fitting", ""))
                row["error"] = str(exc)
        row["index"] = i
        row["raw"] = raw
        rows.append(row)
        total_pa += row["dp_pa"]

    stage_get = _sys_field_getter(args, None)
    stage_raw = {field: stage_get(field) for field in SYS_ROW_FIELDS}
    # Seed stage defaults once so the first render has a usable draft.
    if not stage_raw.get("type"):
        stage_raw["type"] = "straight"
    if not stage_raw.get("dn") and ctx and ctx["default_dn"] is not None:
        stage_raw["dn"] = str(ctx["default_dn"])
    if not stage_raw.get("fitting"):
        stage_raw["fitting"] = pfit.FITTINGS[0].key
    if not stage_raw.get("length"):
        stage_raw["length"] = U.fmt("duct_run_length", DEFAULT_SYS_LENGTH_SI)
    if not stage_raw.get("label"):
        stage_raw["label"] = DEFAULT_SYS_LABEL
    if not stage_raw.get("dp"):
        stage_raw["dp"] = U.fmt("velocity_pressure", DEFAULT_SYS_DP_SI)

    if ctx is None:
        stage = None
        stage_error = ctx_error
    else:
        try:
            stage = _compute_sys_row(lambda f: stage_raw.get(f, ""), ctx, U)
            stage_error = None
        except ValueError as exc:
            stage = None
            stage_error = str(exc)

    try:
        safety_margin = max(0.0, float(args.get("sys_safety_margin", "0") or "0"))
    except (TypeError, ValueError):
        safety_margin = 0.0
    margin_pa = total_pa * safety_margin / 100.0
    total_with_margin_pa = total_pa + margin_pa

    density = ctx["props"].density_kg_m3 if ctx else None
    head = _compute_head_state(
        args, U, friction_pa=total_with_margin_pa, density_kg_m3=density
    )
    if ctx is not None:
        props = ctx["props"]
        fluid_bits = [eng.FLUID_LABELS[props.fluid]]
        if props.fluid != "water":
            fluid_bits.append(f"{props.concentration_pct} % v/v")
        fluid_bits.append(f"mean {U.fmt('temperature', props.temperature_c)} {U.sym('temperature')}")
        head["fluid_label"] = " · ".join(fluid_bits)
    else:
        head["fluid_label"] = "Set fluid in Design Inputs above"

    return {
        "row_count": row_count,
        "rows": rows,
        "total_display": U.fmt("velocity_pressure", total_pa),
        "total_sym": U.sym("velocity_pressure"),
        "safety_margin": safety_margin,
        "margin_amount_display": U.fmt("velocity_pressure", margin_pa),
        "total_with_margin_display": (
            U.fmt("velocity_pressure", total_with_margin_pa) if safety_margin > 0 else ""
        ),
        "type_options": [
            {"value": k, "label": v} for k, v in SYS_ROW_TYPE_LABELS.items()
        ],
        "dn_options": ctx["dn_options"] if ctx else [],
        "fitting_groups": _fitting_options_grouped(),
        "duty_flow_ls": f"{ctx['duty_flow_ls']:.3f}" if ctx else "",
        "stage": stage,
        "stage_raw": stage_raw,
        "stage_error": stage_error,
        "ctx_error": ctx_error,
        "run_length_sym": U.sym("duct_run_length"),
        "velocity_pressure_sym": U.sym("velocity_pressure"),
        "velocity_sym": U.sym("velocity"),
        "friction_rate_sym": U.sym("friction_rate"),
        "head": head,
    }


def _sys_csv_rows(system: dict):
    header = [
        "#", "Type", "Item", "DN", "Flow (l/s)", "Velocity",
        "Friction / K", "Length", "Pressure Drop",
    ]
    data_rows = []
    for row in system["rows"]:
        data_rows.append([
            row["index"] + 1,
            row["type_label"],
            row["label"],
            row["dn_label"],
            row["flow_ls_display"],
            row["velocity_display"],
            row["friction_or_k_display"],
            row["length_display"],
            row["dp_display"] + (f" ({row['error']})" if row.get("error") else ""),
        ])
    footer_rows = [["", "", "", "", "", "", "", "TOTAL", system["total_display"]]]
    margin = system.get("safety_margin", 0)
    if margin > 0 and system.get("total_with_margin_display"):
        footer_rows.append([
            "", "", "", "", "", "", "",
            f"Margin (+{margin:.0f}%)",
            system.get("margin_amount_display", ""),
        ])
        footer_rows.append([
            "", "", "", "", "", "", "",
            "TOTAL WITH MARGIN",
            system["total_with_margin_display"],
        ])
    return header, data_rows, footer_rows


def _sys_table_for_report(system: dict):
    headers = [
        "#", "Type", "Item", "DN", "Flow", "Velocity", "Friction / K", "ΔP",
    ]
    n_cols = len(headers)
    rows = []
    for row in system["rows"]:
        rows.append([
            str(row["index"] + 1),
            row["type_label"],
            row["label"] or "—",
            row["dn_label"],
            row["flow_ls_display"] or "—",
            row["velocity_display"],
            row["friction_or_k_display"],
            row["dp_display"] + (" (error)" if row.get("error") else ""),
        ])
    rows.append(
        ["TOTAL"] + [""] * (n_cols - 2)
        + [f'{system["total_display"]} {system["total_sym"]}']
    )
    footer_count = 1
    margin = system.get("safety_margin", 0)
    if margin > 0 and system.get("total_with_margin_display"):
        rows.append(
            [f"+ {margin:.0f}% margin"] + [""] * (n_cols - 2)
            + [system.get("margin_amount_display", "")]
        )
        rows.append(
            ["TOTAL WITH MARGIN"] + [""] * (n_cols - 2)
            + [f'{system["total_with_margin_display"]} {system["total_sym"]}']
        )
        footer_count = 3
    return headers, rows, footer_count


def _report_fields_for(fields: dict, system: dict) -> dict:
    out = dict(fields)
    out["sys_row_count"] = str(system["row_count"])
    out["sys_safety_margin"] = str(system.get("safety_margin", 0))
    for row in system["rows"]:
        for f in SYS_ROW_FIELDS:
            out[f"sys_{f}_{row['index']}"] = row["raw"].get(f, "")
    head = system.get("head") or {}
    hf = head.get("fields") or {}
    out["circuit"] = hf.get("circuit", "pressurised")
    out["lift"] = hf.get("lift", "")
    return out


# ── Routes ────────────────────────────────────────────────────────────────────

@bp.route("/", methods=["GET"])
def index():
    U = current_view()
    state = _compute_state(request.args, U)
    system = _compute_system_state(request.args, U)
    report_fields = _report_fields_for(state["fields"], system)
    return render_template(
        "pipe.html",
        active="pipe",
        U=U,
        fluids=eng.FLUID_LABELS,
        materials=eng.MATERIAL_LABELS,
        applications=eng.APPLICATION_LABELS,
        system=system,
        report_fields=report_fields,
        **state,
    )


@bp.route("/api/system-state", methods=["GET"])
@require_module("pipe.system")
def api_system_state():
    U = current_view()
    system = _compute_system_state(request.args, U)
    return jsonify(system)


@bp.route("/system/export.csv", methods=["GET"])
@require_module("pipe.system")
def system_export_csv():
    U = current_view()
    system = _compute_system_state(request.args, U)
    header, data_rows, footer_rows = _sys_csv_rows(system)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(data_rows)
    writer.writerows(footer_rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=pipe-system.csv"},
    )


def _report_rows(state, U, system=None):
    f = state["fields"]
    input_rows = [
        ("Flow mode", "From load" if f["mode"] == "from_load" else "Flow known", ""),
        ("Application", eng.APPLICATION_LABELS[f["application"]], ""),
        ("Fluid", eng.FLUID_LABELS[f["fluid"]], ""),
    ]
    if f["fluid"] != "water":
        input_rows.append(("Glycol concentration", f"{f['glycol_pct']} %", ""))
    input_rows.extend([
        ("Material", eng.MATERIAL_LABELS[f["material"]], ""),
        ("ΔT", f["delta_t"], U.sym("temperature")),
        ("LWT", f["lwt"], U.sym("temperature")),
    ])
    if f["mode"] == "from_load":
        input_rows.append(("Load", f["load"], U.sym("power")))
    else:
        input_rows.append(("Flow", f["flow_ls"], "l/s"))

    head = system.get("head") if system else None
    if head and head.get("fields"):
        input_rows.append(("Circuit type", head["circuit_label"], ""))
        input_rows.append(("Static lift", head["fields"].get("lift", ""), head["lift_sym"]))

    result_rows: list[tuple[str, str, str]] = []
    if state["flow_display"]:
        fd = state["flow_display"]
        result_rows = [
            ("Volumetric flow", fd["ls"], "l/s"),
            ("Volumetric flow", fd["m3h"], "m³/h"),
            ("Mass flow", fd["mass_kg_s"], "kg/s"),
        ]

    head = system.get("head") if system else None
    if head and not head.get("error") and head.get("pump"):
        result_rows.extend([
            ("Circuit type", head["circuit_label"], ""),
            ("Static lift", head["lift_display"], head["lift_sym"]),
            ("Static head", head["static"]["summary"], ""),
            ("Circuit friction", head["friction"]["summary"], ""),
            ("Required pump head", head["pump"]["summary"], ""),
        ])

    size_headers = ["DN", f"Velocity ({U.sym('velocity')})", f"ΔP/L ({U.sym('friction_rate')})"]
    catalogue = state.get("catalogue_results") or []
    size_rows = []
    for row in catalogue:
        size_rows.append((
            row.entry.label,
            U.fmt("velocity", row.velocity_ms),
            U.fmt("friction_rate", row.friction_rate_pa_per_m),
        ))
    return input_rows, result_rows, ("Pipe size table", size_headers, size_rows)


@bp.route("/report", methods=["POST"])
def report():
    U = current_view()
    state = _compute_state(request.form, U)
    if state["error"]:
        return Response(state["error"], status=400)

    system = _compute_system_state(request.form, U)
    input_rows, result_rows, size_table = _report_rows(state, U, system)

    extra = [size_table]
    if system["rows"]:
        headers, rows, footer_count = _sys_table_for_report(system)
        extra.append(
            ("Pipe System — Pressure Drop", headers, rows, _SYS_PDF_COL_WIDTHS_MM, footer_count)
        )

    meta = report_meta_from_form(TOOL_TITLE)
    pdf = build_pdf(
        meta=meta,
        input_rows=input_rows,
        result_rows=result_rows,
        extra_tables=extra,
    )
    return pdf_response(pdf, "pipe-sizing-report.pdf")
