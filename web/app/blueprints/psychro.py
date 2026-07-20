"""Psychrometrics tools: single point, mixed air, cooling coil, AHU supply design.

Each tool has a page route (renders the on-screen form + results) and a sibling
`/report` route (POST-only, generates a PDF). Both call the same `_run_*` helper
for the actual calculation, so the numbers in the PDF can never drift from the
numbers on screen -- one calculation, two consumers. See specs/SPEC-pdf-report.md.
"""

from flask import Blueprint, Response, current_app, render_template, request

from hvac_engine import processes as proc
from hvac_engine import psychrometrics as psy
from hvac_engine.ahu_design import design_ahu_to_supply

from app.chart import chart_payload
from app.climate_slots import get_slots
from app.reports.builder import build_pdf
from app.reports.chart import render_chart
from app.reports.helpers import pdf_response as _pdf_response
from app.reports.helpers import report_meta_from_form as _report_meta_from_form
from app.units import current_view

bp = Blueprint("psychro", __name__)


# Shared second-variable selector, consistent across every module. Dry-bulb
# temperature is always the base; the user picks one of these as the second
# variable. Keys map to hvac_engine.psychrometrics.state() property arguments.
# Labels are unit-aware so they track the active unit system.
def _second_properties(U):
    t = U.sym("temperature")
    return {
        "rh": "Relative humidity (%)",
        "twb": f"Wet bulb ({t})",
        "w": f"Moisture ratio ({U.sym('humidity_ratio')})",
        "tdp": f"Dew point ({t})",
    }


def _f(form, key, default=None):
    raw = form.get(key, "")
    if raw in ("", None):
        if default is None:
            raise ValueError(f"missing value for {key}")
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"'{raw}' is not a number ({key})")


def _state_from_form(form, prefix, p, U):
    """Resolve a PsychroState from the shared dry-bulb + second-variable inputs.

    Reads "<prefix>_t", "<prefix>_prop" and "<prefix>_val" from the form and
    converts them from the active unit system into SI before hitting the engine.
    """
    t = U.to_si("temperature", _f(form, f"{prefix}_t"))
    val = _f(form, f"{prefix}_val")
    prop = form.get(f"{prefix}_prop", "rh")
    if prop == "rh":
        return psy.state(t, rh=val / 100.0, p=p)
    if prop == "twb":
        return psy.state(t, twb=U.to_si("temperature", val), p=p)
    if prop == "w":
        return psy.state(t, w=U.to_si("humidity_ratio", val), p=p)
    if prop == "tdp":
        return psy.state(t, tdp=U.to_si("temperature", val), p=p)
    raise ValueError(f"unknown second-property selection: {prop!r}")


def _resolve_pressure(form, U):
    """Site barometric pressure (kPa, SI) derived from the "altitude" form field.

    Standard-atmosphere design pressure (ASHRAE HOF Ch.1 eqn 3) — HVAC design
    uses the site elevation, not a live/measured weather reading, so pressure is
    always derived from altitude rather than entered directly.
    """
    altitude_si = U.to_si("altitude", _f(form, "altitude"))
    return psy.pressure_from_altitude(altitude_si)


def _m_da(flow_m3h, state):
    """Dry-air mass flow from volumetric flow at the given state."""
    return (flow_m3h / 3600.0) / state.v


def _paste_slot_into(form, prefix, U):
    """Override one state_input() group's three fields (in place, on `form`)
    from a Weather-tool memory slot, if `?paste_<prefix>=<index>` is present
    in the query string -- the "Paste from Slot" buttons _state_input.html
    renders next to every state input, on every psychrometric tool (see
    app/climate_slots.py for where the slots themselves come from).

    Deliberately forgiving: an absent/invalid/out-of-range/empty slot index
    just leaves `form`'s existing values (the tool's normal GET defaults)
    untouched rather than raising -- pasting is a convenience shortcut, never
    a hard requirement to render the page. Prefers relative humidity as the
    second property to show, then wet-bulb, then dew point, then moisture
    ratio -- whichever the slot actually has a value for (a slot copied from
    a rare degraded Max/Min condition might only have dry-bulb).
    """
    raw = request.args.get(f"paste_{prefix}")
    if raw is None:
        return
    try:
        index = int(raw)
    except ValueError:
        return
    slots = get_slots()
    if not 0 <= index < len(slots) or slots[index] is None:
        return
    slot = slots[index]

    if slot["rh"] is not None:
        prop, val = "rh", f"{slot['rh'] * 100:.1f}"
    elif slot["wb"] is not None:
        prop, val = "twb", U.fmt("temperature", slot["wb"])
    elif slot["dp"] is not None:
        prop, val = "tdp", U.fmt("temperature", slot["dp"])
    elif slot["w"] is not None:
        prop, val = "w", U.fmt("humidity_ratio", slot["w"])
    else:
        return  # nothing beyond dry-bulb to paste -- leave the defaults alone

    form[f"{prefix}_t"] = U.fmt("temperature", slot["db"])
    form[f"{prefix}_prop"] = prop
    form[f"{prefix}_val"] = val


def _display_defaults(defaults, field_units, U):
    """Render GET-time default field values in the active unit system.

    Stored defaults are canonical-SI display values (°C, kPa, m³/h — where the SI
    display unit equals the engine's canonical unit), so each is converted straight
    to the active system for the pre-filled form.
    """
    out = dict(defaults)
    for key, quantity in field_units.items():
        raw = defaults.get(key, "")
        if raw not in ("", None):
            out[key] = U.fmt(quantity, float(raw))
    return out


# -- PDF report helpers ------------------------------------------------------------
# Shared by every tool's /report route. See specs/SPEC-pdf-report.md.
# _report_meta_from_form / _pdf_response now live in app.reports.helpers (imported
# above) so every blueprint's report route builds metadata and the PDF response the
# same way -- see that module's docstring.

def _site_condition_rows(form, pressure, U):
    return [
        ("Altitude", form["altitude"], U.sym("altitude")),
        ("Barometric Pressure (derived from altitude)",
         U.fmt("pressure", pressure, 3), U.sym("pressure")),
    ]


def _safe_chart_png(points, segments, system):
    """render_chart(), but a failure here must never take the whole report down --
    the chart is one section of the PDF, not the reason for generating it. Any
    exception is logged and swallowed; build_pdf() already renders fine with
    chart_png=None (it just omits the "Psychrometric Chart" section).
    """
    try:
        return render_chart(chart_payload(points, segments, system=system))
    except Exception:
        current_app.logger.exception("psychrometric chart render failed for PDF report")
        return None


def _state_input_rows(prefix, label, form, second_properties, U):
    """Report rows for one state_input() group — mirrors the on-screen labels.

    Both the dry-bulb and second-value inputs need a unit alongside the raw
    entered number: dry-bulb is always temperature, but the second value's
    unit depends on which second property is selected (%, temperature, or
    humidity ratio).
    """
    prop = form.get(f"{prefix}_prop", "rh")
    val_unit = "%" if prop == "rh" else (
        U.sym("humidity_ratio") if prop == "w" else U.sym("temperature")
    )
    return [
        (f"{label} Dry Bulb", form[f"{prefix}_t"], U.sym("temperature")),
        (f"{label} Second Property", second_properties.get(prop, prop), ""),
        (f"{label} Second Value", form[f"{prefix}_val"], val_unit),
    ]


def _png_response(png_bytes, filename):
    return Response(
        png_bytes,
        mimetype="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _chart_png_or_500(points, segments, system):
    """Like _safe_chart_png(), but for the standalone PNG-export route: there the
    chart *is* the whole point of the request, so a failure must be reported (a
    clear 500), not silently swallowed the way it is when the chart is just one
    section of a larger PDF (see _safe_chart_png()).
    """
    try:
        return render_chart(chart_payload(points, segments, system=system)), None
    except Exception as exc:
        current_app.logger.exception("chart PNG export failed")
        return None, str(exc)


# -- Single point ----------------------------------------------------------------

_SINGLE_POINT_DEFAULTS = {
    "s_t": "21", "s_prop": "rh", "s_val": "50", "altitude": "0",
}
_SINGLE_POINT_FIELD_UNITS = {"s_t": "temperature", "altitude": "altitude"}


def _run_single_point(form, U):
    pressure = _resolve_pressure(form, U)
    result = _state_from_form(form, "s", pressure, U)
    points = [{"label": "1", "t": result.t_db, "w": result.w}]
    segments = []
    return pressure, result, points, segments


@bp.route("/", methods=["GET", "POST"])
def single_point():
    U = current_view()
    result = None
    error = None
    pressure = None
    if request.method == "POST":
        form = {k: request.form.get(k, d) for k, d in _SINGLE_POINT_DEFAULTS.items()}
        try:
            pressure, result, points, segments = _run_single_point(form, U)
        except ValueError as exc:
            error = str(exc)
    else:
        form = _display_defaults(_SINGLE_POINT_DEFAULTS, _SINGLE_POINT_FIELD_UNITS, U)
        _paste_slot_into(form, "s", U)
        pressure = _resolve_pressure(form, U)
    chart = None
    if result:
        chart = chart_payload(points, segments, system=U.system)
    return render_template(
        "psychro.html", active="psychro", form=form,
        second_properties=_second_properties(U), result=result, error=error,
        chart=chart, pressure=pressure,
    )


@bp.route("/report", methods=["POST"])
def single_point_report():
    U = current_view()
    form = {k: request.form.get(k, d) for k, d in _SINGLE_POINT_DEFAULTS.items()}
    try:
        pressure, result, points, segments = _run_single_point(form, U)
    except ValueError as exc:
        return Response(f"Cannot generate report: {exc}", status=400)

    chart_png = _safe_chart_png(points, segments, U.system)
    sp = _second_properties(U)
    input_rows = (
        _site_condition_rows(form, pressure, U)
        + _state_input_rows("s", "State", form, sp, U)
    )
    result_rows = [
        ("Dry-bulb Temperature", U.fmt('temperature', result.t_db, 2), U.sym('temperature')),
        ("Wet-bulb Temperature", U.fmt('temperature', result.t_wb, 2), U.sym('temperature')),
        ("Dew-point Temperature",
         "— (dry air)" if result.t_dp < -273 else U.fmt('temperature', result.t_dp, 2),
         "" if result.t_dp < -273 else U.sym('temperature')),
        ("Relative Humidity", f"{result.rh * 100:.1f}", "%"),
        ("Humidity Ratio", U.fmt('humidity_ratio', result.w), f"{U.sym('humidity_ratio')} dry air"),
        ("Specific Enthalpy", U.fmt('enthalpy', result.h, 2), f"{U.sym('enthalpy')} dry air"),
        ("Specific Volume", U.fmt('specific_volume', result.v), f"{U.sym('specific_volume')} dry air"),
        ("Density", U.fmt('density', result.rho), U.sym('density')),
        ("Vapour Pressure", U.fmt('pressure', result.p_w, 4), U.sym('pressure')),
    ]
    meta = _report_meta_from_form("Psychrometrics - Single Point")
    pdf = build_pdf(meta, input_rows, result_rows, chart_png)
    return _pdf_response(pdf, "psychrometrics-single-point.pdf")


@bp.route("/chart.png", methods=["POST"])
def single_point_chart_png():
    U = current_view()
    form = {k: request.form.get(k, d) for k, d in _SINGLE_POINT_DEFAULTS.items()}
    try:
        pressure, result, points, segments = _run_single_point(form, U)
    except ValueError as exc:
        return Response(f"Cannot generate chart: {exc}", status=400)

    png, err = _chart_png_or_500(points, segments, U.system)
    if png is None:
        return Response(f"Could not generate chart image: {err}", status=500)
    return _png_response(png, "psychrometrics-single-point-chart.png")


# -- Mixed air ---------------------------------------------------------------------

_MIXED_AIR_DEFAULTS = {
    "a_t": "28", "a_prop": "rh", "a_val": "50", "flow_a": "1500",
    "b_t": "20", "b_prop": "rh", "b_val": "50", "flow_b": "3500",
    "altitude": "0",
}
_MIXED_AIR_FIELD_UNITS = {
    "a_t": "temperature", "b_t": "temperature",
    "flow_a": "vol_flow", "flow_b": "vol_flow", "altitude": "altitude",
}


def _run_mixed_air(form, U):
    pressure = _resolve_pressure(form, U)
    sa = _state_from_form(form, "a", pressure, U)
    sb = _state_from_form(form, "b", pressure, U)
    ma = _m_da(U.to_si("vol_flow", _f(form, "flow_a")), sa)
    mb = _m_da(U.to_si("vol_flow", _f(form, "flow_b")), sb)
    mres = proc.mix(sa, ma, sb, mb)
    points = [
        {"label": "A", "t": sa.t_db, "w": sa.w},
        {"label": "B", "t": sb.t_db, "w": sb.w},
        {"label": "MIX", "t": mres.state.t_db, "w": mres.state.w},
    ]
    segments = [(0, 2), (1, 2)]
    return pressure, sa, sb, ma, mb, mres, points, segments


@bp.route("/mixed-air", methods=["GET", "POST"])
def mixed_air():
    U = current_view()
    result = None
    error = None
    mres = None
    chart = None
    pressure = None
    if request.method != "POST":
        form = _display_defaults(_MIXED_AIR_DEFAULTS, _MIXED_AIR_FIELD_UNITS, U)
        _paste_slot_into(form, "a", U)
        _paste_slot_into(form, "b", U)
        pressure = _resolve_pressure(form, U)
    else:
        form = {k: request.form.get(k, d) for k, d in _MIXED_AIR_DEFAULTS.items()}
        try:
            pressure, sa, sb, ma, mb, mres, points, segments = _run_mixed_air(form, U)
            result = {"a": sa, "b": sb, "m_a": ma, "m_b": mb}
            chart = chart_payload(points, segments, system=U.system)
        except ValueError as exc:
            error = str(exc)
    return render_template(
        "mixed_air.html", active="psychro_mix", form=form,
        second_properties=_second_properties(U), result=result, mres=mres,
        chart=chart, error=error, pressure=pressure,
    )


@bp.route("/mixed-air/report", methods=["POST"])
def mixed_air_report():
    U = current_view()
    form = {k: request.form.get(k, d) for k, d in _MIXED_AIR_DEFAULTS.items()}
    try:
        pressure, sa, sb, ma, mb, mres, points, segments = _run_mixed_air(form, U)
    except ValueError as exc:
        return Response(f"Cannot generate report: {exc}", status=400)

    chart_png = _safe_chart_png(points, segments, U.system)
    sp = _second_properties(U)
    input_rows = (
        _site_condition_rows(form, pressure, U)
        + _state_input_rows("a", "Stream A", form, sp, U)
        + [("Stream A Flow", form['flow_a'], U.sym('vol_flow'))]
        + _state_input_rows("b", "Stream B", form, sp, U)
        + [("Stream B Flow", form['flow_b'], U.sym('vol_flow'))]
    )
    result_rows = [
        ("Stream A Dry Bulb", U.fmt('temperature', sa.t_db), U.sym('temperature')),
        ("Stream A Humidity Ratio", U.fmt('humidity_ratio', sa.w), U.sym('humidity_ratio')),
        ("Stream A Mass Flow", U.fmt('mass_flow', ma), f"{U.sym('mass_flow')} dry air"),
        ("Stream B Dry Bulb", U.fmt('temperature', sb.t_db), U.sym('temperature')),
        ("Stream B Humidity Ratio", U.fmt('humidity_ratio', sb.w), U.sym('humidity_ratio')),
        ("Stream B Mass Flow", U.fmt('mass_flow', mb), f"{U.sym('mass_flow')} dry air"),
        ("Mixed Dry Bulb", U.fmt('temperature', mres.state.t_db), U.sym('temperature')),
        ("Mixed Relative Humidity", f"{mres.state.rh * 100:.0f}", "%"),
        ("Mixed Humidity Ratio", U.fmt('humidity_ratio', mres.state.w), U.sym('humidity_ratio')),
        ("Mixed Enthalpy", U.fmt('enthalpy', mres.state.h), U.sym('enthalpy')),
        ("Mixed Mass Flow", U.fmt('mass_flow', mres.m_da), f"{U.sym('mass_flow')} dry air"),
    ]
    if mres.fog:
        result_rows.append((
            "Fog Warning",
            f"Mixed condition settled to saturation; condensate "
            f"{U.fmt('moisture_rate', mres.condensate)}",
            U.sym('moisture_rate'),
        ))
    meta = _report_meta_from_form("Psychrometrics - Mixed Air")
    pdf = build_pdf(meta, input_rows, result_rows, chart_png)
    return _pdf_response(pdf, "psychrometrics-mixed-air.pdf")


@bp.route("/mixed-air/chart.png", methods=["POST"])
def mixed_air_chart_png():
    U = current_view()
    form = {k: request.form.get(k, d) for k, d in _MIXED_AIR_DEFAULTS.items()}
    try:
        pressure, sa, sb, ma, mb, mres, points, segments = _run_mixed_air(form, U)
    except ValueError as exc:
        return Response(f"Cannot generate chart: {exc}", status=400)

    png, err = _chart_png_or_500(points, segments, U.system)
    if png is None:
        return Response(f"Could not generate chart image: {err}", status=500)
    return _png_response(png, "psychrometrics-mixed-air-chart.png")


# -- Cooling coil --------------------------------------------------------------------

_COOLING_COIL_DEFAULTS = {
    "on_t": "28", "on_prop": "rh", "on_val": "50", "flow": "5000",
    "off_t": "12", "off_prop": "rh", "off_val": "90",
    "altitude": "0",
}
_COOLING_COIL_FIELD_UNITS = {
    "on_t": "temperature", "off_t": "temperature",
    "flow": "vol_flow", "altitude": "altitude",
}


def _run_cooling_coil(form, U):
    pressure = _resolve_pressure(form, U)
    on = _state_from_form(form, "on", pressure, U)
    off_state = _state_from_form(form, "off", pressure, U)
    m_da = _m_da(U.to_si("vol_flow", _f(form, "flow")), on)
    result = proc.cooling_coil(on, m_da, off_state.t_db, off_state.rh)
    points = [
        {"label": "ON", "t": on.t_db, "w": on.w},
        {"label": "OFF", "t": result.state.t_db, "w": result.state.w},
    ]
    segments = [(0, 1)]
    if result.t_adp is not None:
        points.append({
            "label": "ADP", "t": result.t_adp,
            "w": psy.saturation_humidity_ratio(result.t_adp, pressure),
        })
        segments.append((1, 2))
    return pressure, on, m_da, result, points, segments


@bp.route("/cooling-coil", methods=["GET", "POST"])
def cooling_coil():
    U = current_view()
    result = None
    error = None
    on = None
    m_da = None
    chart = None
    pressure = None
    if request.method != "POST":
        form = _display_defaults(_COOLING_COIL_DEFAULTS, _COOLING_COIL_FIELD_UNITS, U)
        _paste_slot_into(form, "on", U)
        _paste_slot_into(form, "off", U)
        pressure = _resolve_pressure(form, U)
    else:
        form = {k: request.form.get(k, d) for k, d in _COOLING_COIL_DEFAULTS.items()}
        try:
            pressure, on, m_da, result, points, segments = _run_cooling_coil(form, U)
            chart = chart_payload(points, segments, system=U.system)
        except ValueError as exc:
            error = str(exc)
    return render_template(
        "coil.html", active="psychro_coil", form=form,
        second_properties=_second_properties(U), on=on, m_da=m_da,
        result=result, chart=chart, error=error, pressure=pressure,
    )


@bp.route("/cooling-coil/report", methods=["POST"])
def cooling_coil_report():
    U = current_view()
    form = {k: request.form.get(k, d) for k, d in _COOLING_COIL_DEFAULTS.items()}
    try:
        pressure, on, m_da, result, points, segments = _run_cooling_coil(form, U)
    except ValueError as exc:
        return Response(f"Cannot generate report: {exc}", status=400)

    chart_png = _safe_chart_png(points, segments, U.system)
    sp = _second_properties(U)
    input_rows = (
        _site_condition_rows(form, pressure, U)
        + _state_input_rows("on", "On-coil", form, sp, U)
        + [("On-coil Flow", form['flow'], U.sym('vol_flow'))]
        + _state_input_rows("off", "Off-coil", form, sp, U)
    )
    result_rows = [
        ("On-coil Dry Bulb", U.fmt('temperature', on.t_db), U.sym('temperature')),
        ("Off-coil Dry Bulb", U.fmt('temperature', result.state.t_db), U.sym('temperature')),
        ("Total Cooling", U.fmt('power', -result.q_total), U.sym('power')),
        ("Sensible / Latent",
         f"{U.fmt('power', -result.q_sensible)} / {U.fmt('power', -result.q_latent)}", U.sym('power')),
        ("Sensible Heat Ratio", f"{result.shr:.2f}", ""),
        ("Condensate", U.fmt('moisture_rate', result.condensate), U.sym('moisture_rate')),
        ("Dry-air Mass Flow", U.fmt('mass_flow', m_da), U.sym('mass_flow')),
    ]
    if result.t_adp is not None:
        result_rows += [
            ("Apparatus Dew Point", U.fmt('temperature', result.t_adp), U.sym('temperature')),
            ("Contact / Bypass Factor", f"{result.contact_factor:.2f} / {result.bypass_factor:.2f}", ""),
        ]
    if result.frost_risk:
        result_rows.append(("Frost Risk", "Yes — apparatus dew point at or below freezing", ""))
    meta = _report_meta_from_form("Psychrometrics - Cooling Coil")
    pdf = build_pdf(meta, input_rows, result_rows, chart_png)
    return _pdf_response(pdf, "psychrometrics-cooling-coil.pdf")


@bp.route("/cooling-coil/chart.png", methods=["POST"])
def cooling_coil_chart_png():
    U = current_view()
    form = {k: request.form.get(k, d) for k, d in _COOLING_COIL_DEFAULTS.items()}
    try:
        pressure, on, m_da, result, points, segments = _run_cooling_coil(form, U)
    except ValueError as exc:
        return Response(f"Cannot generate chart: {exc}", status=400)

    png, err = _chart_png_or_500(points, segments, U.system)
    if png is None:
        return Response(f"Could not generate chart image: {err}", status=500)
    return _png_response(png, "psychrometrics-cooling-coil-chart.png")


# -- AHU duty (supply-driven design) ---------------------------------------------------

_AHU_DEFAULTS = {
    "flow": "5000",
    "oa_t": "28", "oa_prop": "rh", "oa_val": "50",
    "oa_frac": "100",
    "ra_t": "22", "ra_prop": "rh", "ra_val": "50",
    "sup_t": "14", "sup_prop": "rh", "sup_val": "90",
    "fan_pos": "none", "fan_sfp": "2.0", "fan_kw": "",
    "altitude": "0",
}
_AHU_FIELD_UNITS = {
    "flow": "vol_flow", "oa_t": "temperature",
    "ra_t": "temperature", "sup_t": "temperature", "altitude": "altitude",
}


def _run_ahu(form, U):
    pressure = _resolve_pressure(form, U)
    supply = _state_from_form(form, "sup", pressure, U)
    oa = _state_from_form(form, "oa", pressure, U)
    oa_frac = _f(form, "oa_frac") / 100.0
    ra = _state_from_form(form, "ra", pressure, U) if oa_frac < 1.0 else None

    # Supply volumetric flow (converted to SI) at the known supply condition.
    flow_m3h = U.to_si("vol_flow", _f(form, "flow"))
    m_da = _m_da(flow_m3h, supply)

    kwargs = dict(
        m_da=m_da, supply=supply, outdoor=oa,
        return_air=ra, oa_fraction=oa_frac,
    )
    if form["fan_pos"] in ("blow", "draw"):
        kwargs["fan_position"] = form["fan_pos"]
        if form["fan_kw"].strip():
            kwargs["fan_power_kw"] = _f(form, "fan_kw")
        elif form["fan_sfp"].strip():
            kwargs["fan_power_kw"] = _f(form, "fan_sfp") * (flow_m3h / 3.6) / 1000.0

    result = design_ahu_to_supply(**kwargs)

    pts = [
        {"label": s.label, "t": s.state.t_db, "w": s.state.w}
        for s in result.stages
    ]
    labels = [s.label for s in result.stages]
    segs = []
    chain_start = 0
    if "MA" in labels:
        i_ma = labels.index("MA")
        segs += [(labels.index("OA"), i_ma), (labels.index("RA"), i_ma)]
        chain_start = i_ma
    for i in range(chain_start, len(labels) - 1):
        if labels[i] == "RA" or labels[i + 1] == "RA":
            continue
        segs.append((i, i + 1))

    return pressure, m_da, result, pts, segs


@bp.route("/ahu", methods=["GET", "POST"])
def ahu():
    U = current_view()
    result = None
    error = None
    m_da = None
    chart = None
    pressure = None
    if request.method != "POST":
        form = _display_defaults(_AHU_DEFAULTS, _AHU_FIELD_UNITS, U)
        _paste_slot_into(form, "oa", U)
        _paste_slot_into(form, "ra", U)
        _paste_slot_into(form, "sup", U)
        pressure = _resolve_pressure(form, U)
    else:
        form = {k: request.form.get(k, d) for k, d in _AHU_DEFAULTS.items()}
        try:
            pressure, m_da, result, pts, segs = _run_ahu(form, U)
            chart = chart_payload(pts, segs, system=U.system)
        except ValueError as exc:
            result = None
            error = str(exc)
    return render_template(
        "ahu.html", active="psychro_ahu", form=form,
        second_properties=_second_properties(U), result=result, m_da=m_da,
        chart=chart, error=error, pressure=pressure,
    )


@bp.route("/ahu/report", methods=["POST"])
def ahu_report():
    U = current_view()
    form = {k: request.form.get(k, d) for k, d in _AHU_DEFAULTS.items()}
    try:
        pressure, m_da, result, pts, segs = _run_ahu(form, U)
    except ValueError as exc:
        return Response(f"Cannot generate report: {exc}", status=400)

    chart_png = _safe_chart_png(pts, segs, U.system)
    sp = _second_properties(U)
    input_rows = (
        _site_condition_rows(form, pressure, U)
        + _state_input_rows("oa", "Outdoor Air", form, sp, U)
        + [("Outdoor Air Fraction", form['oa_frac'], "%")]
        + _state_input_rows("ra", "Return Air", form, sp, U)
        + _state_input_rows("sup", "Supply", form, sp, U)
        + [("Supply Flow", form['flow'], U.sym('vol_flow'))]
        + [("Fan Position", form["fan_pos"], "")]
    )
    if form["fan_pos"] in ("blow", "draw"):
        input_rows.append(("Fan SFP", form['fan_sfp'], "W per l/s"))
        if form["fan_kw"].strip():
            input_rows.append(("Fan Power", form['fan_kw'], "kW"))

    result_rows = []
    for s in result.stages:
        name = s.name + (f" ({s.note})" if s.note else "")
        result_rows.append((
            f"{s.label} — {name}",
            f"{U.fmt('temperature', s.state.t_db)} {U.sym('temperature')}, "
            f"{s.state.rh * 100:.0f}% RH, "
            f"{U.fmt('humidity_ratio', s.state.w)} {U.sym('humidity_ratio')}, "
            f"{U.fmt('enthalpy', s.state.h)} {U.sym('enthalpy')}",
            "",
        ))
    result_rows += [
        ("Total Cooling (Coil Duty)", U.fmt('power', -result.cooling_total), U.sym('power')),
        ("Total Heating (Reheat + Preheat)", U.fmt('power', result.heating_total), U.sym('power')),
        ("Moisture Added / Removed",
         f"{U.fmt('moisture_rate', result.moisture_added)} / "
         f"{U.fmt('moisture_rate', result.moisture_removed)}", U.sym('moisture_rate')),
        ("Dry-air Mass Flow", U.fmt('mass_flow', result.m_da), U.sym('mass_flow')),
    ]
    for w in result.warnings:
        result_rows.append(("Warning", w, ""))
    meta = _report_meta_from_form("Psychrometrics - AHU Design")
    pdf = build_pdf(meta, input_rows, result_rows, chart_png)
    return _pdf_response(pdf, "psychrometrics-ahu-design.pdf")


@bp.route("/ahu/chart.png", methods=["POST"])
def ahu_chart_png():
    U = current_view()
    form = {k: request.form.get(k, d) for k, d in _AHU_DEFAULTS.items()}
    try:
        pressure, m_da, result, pts, segs = _run_ahu(form, U)
    except ValueError as exc:
        return Response(f"Cannot generate chart: {exc}", status=400)

    png, err = _chart_png_or_500(pts, segs, U.system)
    if png is None:
        return Response(f"Could not generate chart image: {err}", status=500)
    return _png_response(png, "psychrometrics-ahu-design-chart.png")
