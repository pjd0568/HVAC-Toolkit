"""V2 mobile-first UI — parallel shell under /v2, shared engines with V1."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_login import login_required
from hvac_engine import converter as cv
from hvac_engine import pipe as eng
from hvac_engine import psychrometrics as psy

from app.access_gate import require_module
from app.blueprints import duct as duct_mod
from app.blueprints import pipe as pipe_mod
from app.blueprints import psychro as psy_mod
from app.blueprints import refrigeration as refrig_mod
from app.teaser import TEASER_FORM_SESSION_KEY
from app.ui_prefs import redirect_with_ui
from app.units import current_view

bp = Blueprint("v2", __name__, url_prefix="/v2")


def _safe_next(raw: str | None) -> str:
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return url_for("v2.dashboard")
    return raw


@bp.get("/use-mobile")
@login_required
def use_mobile():
    """Legacy bookmark — ensure V2 cookie and land on the dashboard."""
    return redirect_with_ui("v2", _safe_next(request.args.get("next")) or url_for("v2.dashboard"))


@bp.get("/use-classic")
@login_required
def use_classic():
    """Classic UI is retired — stay on V2."""
    return redirect_with_ui("v2", url_for("v2.dashboard"))


@bp.get("/")
@login_required
def dashboard():
    return render_template("v2/dashboard.html", active="dashboard", nav="home")


@bp.get("/more")
@login_required
def more():
    return render_template("v2/more.html", active="dashboard", nav="more")


@bp.get("/psychrometrics/")
def psychro_picker():
    return render_template("v2/psychro_picker.html", active="psychro", nav="psychro")


@bp.get("/converter")
@require_module("converter")
def converter():
    categories = cv.list_categories()
    cat_ids = {cid for cid, _ in categories}
    cat_id = request.args.get("category", "length")
    if cat_id not in cat_ids:
        cat_id = "length"
    category = cv.get_category(cat_id)
    unit_ids = [u.id for u in category.units]
    from_unit = request.args.get("from_unit", "")
    if from_unit not in unit_ids:
        from_unit = unit_ids[0]
    value_raw = request.args.get("value", "1")
    result = None
    grouped = None
    error = None
    if value_raw.strip() == "":
        value_raw = "1"
    try:
        result = cv.convert_all(cat_id, float(value_raw), from_unit)
    except ValueError:
        error = f"'{value_raw}' is not a number."
    if result is not None:
        group_labels = {
            "Metric": "Metric (SI)",
            "Imperial": "Imperial / US",
            "Other": "Other",
            "Common": "Common",
        }
        grouped = [
            (g, group_labels.get(g, g), [r for r in result.results if r.group == g])
            for g in cv.GROUP_ORDER
        ]
        grouped = [row for row in grouped if row[2]]
    if request.args.get("value") and result is not None and not error:
        from app.analytics import note_calculator_complete

        note_calculator_complete("unit_converter")
    unit_groups = [
        (
            {"Metric": "Metric (SI)", "Imperial": "Imperial / US", "Other": "Other", "Common": "Common"}.get(g, g),
            [u for u in category.units if u.group == g],
        )
        for g in cv.GROUP_ORDER
    ]
    unit_groups = [ug for ug in unit_groups if ug[1]]
    return render_template(
        "v2/converter.html",
        active="converter",
        nav="more",
        categories=categories,
        category=category,
        unit_groups=unit_groups,
        from_unit=from_unit,
        value=value_raw,
        result=result,
        grouped=grouped,
        error=error,
    )


@bp.get("/air/")
def air_picker():
    return render_template("v2/air_picker.html", active="duct", nav="duct")


@bp.get("/water/")
def water_picker():
    return render_template("v2/water_picker.html", active="pipe", nav="pipe")


@bp.get("/refrigeration/")
def refrig_picker():
    return render_template("v2/refrig_picker.html", active="refrig", nav="refrig")


@bp.get("/refrigeration/pt-table/")
@require_module("refrig.pt_table")
def refrig_pt_table():
    state = refrig_mod._compute_pt(request.args)
    if request.args and state.get("result") and not state.get("error"):
        from app.analytics import note_calculator_complete

        note_calculator_complete("refrigerant_pt")
    return render_template(
        "v2/refrig_pt_table.html",
        active="refrig_pt",
        nav="refrig",
        **state,
    )


@bp.get("/refrigeration/pipe-sizer/")
@require_module("refrig.pipe_sizer")
def refrig_pipe_sizer():
    state = refrig_mod._compute_pipe(request.args)
    if request.args and state.get("result") and not state.get("error"):
        from app.analytics import note_pro_tool_use

        note_pro_tool_use("dx_pipe_sizing")
    return render_template(
        "v2/refrig_pipe_sizer.html",
        active="refrig_pipe",
        nav="refrig",
        **state,
    )


@bp.get("/refrigeration/diagnostics/")
@require_module("refrig.diagnostics")
def refrig_diagnostics():
    state = refrig_mod._compute_diagnostics(request.args)
    if request.args and state.get("result") and not state.get("error"):
        from app.analytics import note_calculator_complete

        note_calculator_complete("superheat_subcooling")
    return render_template(
        "v2/refrig_diagnostics.html",
        active="refrig_diagnostics",
        nav="refrig",
        **state,
    )


@bp.get("/refrigeration/charge/")
def refrig_charge():
    """Coming soon — trim charge and total system charge."""
    return render_template(
        "v2/refrig_charge.html",
        active="refrig_charge",
        nav="refrig",
    )


@bp.get("/acoustics/")
def acoustics_picker():
    from app.coming_soon_tools import tools_for_suite

    return render_template(
        "v2/acoustics_picker.html",
        active="acoustics",
        nav="acoustics",
        tools=tools_for_suite("acoustics"),
    )


@bp.get("/coming-soon/<slug>/")
def coming_soon_tool(slug: str):
    """Generic Coming Soon placeholder for roadmap modules."""
    from flask import abort

    from app.coming_soon_tools import tool_by_slug

    tool = tool_by_slug(slug)
    if tool is None:
        abort(404)

    back = {
        "psychro": ("v2.psychro_picker", "All psychro tools"),
        "duct": ("v2.air_picker", "All air tools"),
        "pipe": ("v2.water_picker", "All hydronics tools"),
        "acoustics": ("v2.acoustics_picker", "All acoustics tools"),
    }.get(tool.suite)

    return render_template(
        "v2/coming_soon_tool.html",
        active=tool.active,
        nav=tool.nav,
        tool=tool,
        back_href=url_for(back[0]) if back else None,
        back_label=back[1] if back else None,
    )


@bp.get("/duct-sizing/")
@require_module("duct.sizer")
def duct():
    U = current_view()
    fields, circular, rectangular, flat_oval, error = duct_mod._compute_state(request.args, U)
    return render_template(
        "v2/duct.html",
        active="duct",
        nav="duct",
        U=U,
        fields=fields,
        circular=circular,
        rectangular=rectangular,
        flat_oval=flat_oval,
        error=error,
        catalog_options=duct_mod._catalog_options(),
        nudge_step=duct_mod._nudge_step(U),
        round25_step=duct_mod._round25_step(U),
        report_fields=duct_mod._report_fields_for_sizer(fields) if not error else None,
    )


@bp.get("/duct-index-leg/")
@require_module("duct.index_leg")
def duct_index_leg():
    U = current_view()
    leg = duct_mod._compute_leg_state(request.args, U)
    return render_template(
        "v2/duct_index_leg.html",
        active="duct_index_leg",
        nav="duct",
        U=U,
        leg=leg,
        report_fields=duct_mod._report_fields_for_leg(leg),
    )


@bp.get("/pipe-sizing/")
@require_module("pipe.sizer")
def pipe():
    U = current_view()
    state = pipe_mod._compute_state(request.args, U)
    if request.args and not state.get("error"):
        from app.analytics import note_calculator_complete

        note_calculator_complete("pipe_sizing")
    report_fields = pipe_mod._report_fields_for_sizer(state["fields"]) if not state["error"] else None
    return render_template(
        "v2/pipe.html",
        active="pipe",
        nav="pipe",
        U=U,
        fluids=eng.FLUID_LABELS,
        fluid_groups=eng.FLUID_GROUPS,
        materials=eng.MATERIAL_LABELS,
        applications=eng.APPLICATION_LABELS,
        report_fields=report_fields,
        glycol_concentrations_by_fluid=pipe_mod.GLYCOL_CONCENTRATIONS_BY_FLUID,
        glycol_options_by_fluid=pipe_mod._glycol_options_for_view(U),
        **state,
    )


@bp.get("/pipe-system/")
@require_module("pipe.system")
def pipe_system():
    U = current_view()
    system = pipe_mod._compute_system_state(request.args, U)
    fields = system.get("duty_fields") or {}
    report_fields = pipe_mod._report_fields_for_system(fields, system)
    return render_template(
        "v2/pipe_system.html",
        active="pipe_system",
        nav="pipe",
        U=U,
        fluids=eng.FLUID_LABELS,
        fluid_groups=eng.FLUID_GROUPS,
        materials=eng.MATERIAL_LABELS,
        applications=eng.APPLICATION_LABELS,
        system=system,
        fields=fields,
        report_fields=report_fields,
        glycol_concentrations_by_fluid=pipe_mod.GLYCOL_CONCENTRATIONS_BY_FLUID,
        glycol_options_by_fluid=pipe_mod._glycol_options_for_view(U),
    )


# ── Psychrometrics ──────────────────────────────────────────────────────────


@bp.route("/psychrometrics/interactive-chart", methods=["GET"])
@require_module("psychro.interactive_chart")
def interactive_chart():
    """Multi-Point Interactive Chart — place A–D and map a process between any two."""
    U = current_view()
    form = {"altitude": U.fmt("altitude", 0.0)}
    try:
        pressure = psy_mod._resolve_pressure(form, U)
    except ValueError:
        pressure = psy.P_ATM
    chart = psy_mod._chart_or_blank([], [], pressure, U.system)
    return render_template(
        "v2/interactive_chart.html",
        active="psychro_ix",
        nav="psychro",
        chart=chart,
        pressure=pressure,
        form=form,
        second_properties=psy_mod._second_properties(U),
        resolve_url=url_for("psychro.interactive_resolve"),
        chart_url=url_for("psychro.interactive_chart_payload"),
        process_url=url_for("psychro.interactive_process"),
    )


@bp.route("/psychrometrics/single-point", methods=["GET", "POST"])
@require_module("psychro.single_point")
def single_point():
    """Classic Single Point — resolve a moist-air state (optional Point B)."""
    U = current_view()
    error = None
    pressure = None
    saved = psy_mod._get_saved_points()

    if request.method == "POST":
        action = request.form.get("action", "calculate")
        form = {k: request.form.get(k, d) for k, d in psy_mod._SINGLE_POINT_DEFAULTS.items()}
        if action == "reset":
            psy_mod._clear_saved_points()
            return redirect(url_for("v2.single_point"))
        try:
            pressure, result, _, _ = psy_mod._run_single_point(form, U)
            entry = psy_mod._state_to_session("A", result)
            if action == "add_b":
                if not saved:
                    psy_mod._set_saved_points([entry])
                else:
                    entry["label"] = "B"
                    psy_mod._set_saved_points([saved[0], entry])
            else:
                entry["label"] = "A"
                if len(saved) >= 2:
                    b = dict(saved[1])
                    b["label"] = "B"
                    psy_mod._set_saved_points([entry, b])
                else:
                    psy_mod._set_saved_points([entry])
            saved = psy_mod._get_saved_points()
            from app.analytics import note_calculator_complete

            note_calculator_complete("psychrometric_single")
        except ValueError as exc:
            error = str(exc)
            try:
                pressure = psy_mod._resolve_pressure(form, U)
            except ValueError:
                pressure = None
    else:
        teaser_form = session.pop(TEASER_FORM_SESSION_KEY, None)
        if isinstance(teaser_form, dict):
            form = {k: teaser_form.get(k, d) for k, d in psy_mod._SINGLE_POINT_DEFAULTS.items()}
        else:
            form = psy_mod._display_defaults(
                psy_mod._SINGLE_POINT_DEFAULTS, psy_mod._SINGLE_POINT_FIELD_UNITS, U
            )
            psy_mod._paste_slot_into(form, "s", U)
        try:
            pressure = psy_mod._resolve_pressure(form, U)
        except ValueError:
            pressure = None
    if pressure is None:
        try:
            pressure = psy_mod._resolve_pressure(form, U)
        except ValueError:
            pressure = psy.P_ATM

    chart_pts, chart_segs = psy_mod._chart_points_and_segments(saved)
    chart = psy_mod._chart_or_blank(chart_pts, chart_segs, pressure, U.system)
    return render_template(
        "v2/psychro.html",
        active="psychro",
        nav="psychro",
        form=form,
        second_properties=psy_mod._second_properties(U),
        saved_points=saved,
        error=error,
        chart=chart,
        pressure=pressure,
        can_add_b=len(saved) >= 1,
        has_points=len(saved) >= 1,
    )


def _psychro_simple_post(
    defaults,
    field_units,
    paste_prefixes,
    run_fn,
    unpack,
    tool: str | None = None,
):
    """Shared GET/POST pattern for single-form psychro process tools."""
    U = current_view()
    result = None
    error = None
    pressure = None
    points, segments = [], []
    extra = {}
    if request.method != "POST":
        form = psy_mod._display_defaults(defaults, field_units, U)
        for prefix in paste_prefixes:
            psy_mod._paste_slot_into(form, prefix, U)
        try:
            pressure = psy_mod._resolve_pressure(form, U)
        except ValueError:
            pressure = None
    else:
        form = {k: request.form.get(k, d) for k, d in defaults.items()}
        try:
            packed = run_fn(form, U)
            pressure, points, segments, result, extra = unpack(packed)
            if tool and result is not None:
                from app.analytics import note_pro_tool_use

                note_pro_tool_use(tool)
        except ValueError as exc:
            error = str(exc)
            try:
                pressure = psy_mod._resolve_pressure(form, U)
            except ValueError:
                pressure = None
    chart = psy_mod._chart_or_blank(points, segments, pressure, U.system)
    return U, form, result, error, pressure, chart, extra


@bp.route("/psychrometrics/mixed-air", methods=["GET", "POST"])
@require_module("psychro.mixed_air")
def mixed_air():
    def unpack(packed):
        pressure, sa, sb, ma, mb, mres, points, segments = packed
        return pressure, points, segments, {"a": sa, "b": sb, "m_a": ma, "m_b": mb}, {"mres": mres}

    U, form, result, error, pressure, chart, extra = _psychro_simple_post(
        psy_mod._MIXED_AIR_DEFAULTS,
        psy_mod._MIXED_AIR_FIELD_UNITS,
        ("a", "b"),
        psy_mod._run_mixed_air,
        unpack,
        tool="mixed_air",
    )
    return render_template(
        "v2/mixed_air.html",
        active="psychro_mix",
        nav="psychro",
        form=form,
        second_properties=psy_mod._second_properties(U),
        result=result,
        mres=extra.get("mres"),
        chart=chart,
        error=error,
        pressure=pressure,
    )


@bp.route("/psychrometrics/cooling-coil", methods=["GET", "POST"])
@require_module("psychro.cooling_coil")
def cooling_coil():
    def unpack(packed):
        pressure, on, m_da, result, points, segments = packed
        return pressure, points, segments, result, {"on": on, "m_da": m_da}

    U, form, result, error, pressure, chart, extra = _psychro_simple_post(
        psy_mod._COOLING_COIL_DEFAULTS,
        psy_mod._COOLING_COIL_FIELD_UNITS,
        ("on",),
        psy_mod._run_cooling_coil,
        unpack,
        tool="cooling_coil",
    )
    return render_template(
        "v2/coil.html",
        active="psychro_coil",
        nav="psychro",
        form=form,
        second_properties=psy_mod._second_properties(U),
        on=extra.get("on"),
        m_da=extra.get("m_da"),
        result=result,
        chart=chart,
        error=error,
        pressure=pressure,
    )


@bp.route("/psychrometrics/desiccant", methods=["GET", "POST"])
@require_module("psychro.desiccant")
def desiccant():
    def unpack(packed):
        pressure, on, m_da, result, points, segments = packed
        return pressure, points, segments, result, {"on": on, "m_da": m_da}

    U, form, result, error, pressure, chart, extra = _psychro_simple_post(
        psy_mod._DESICCANT_DEFAULTS,
        psy_mod._DESICCANT_FIELD_UNITS,
        ("on",),
        psy_mod._run_desiccant,
        unpack,
        tool="desiccant",
    )
    return render_template(
        "v2/desiccant.html",
        active="psychro_desiccant",
        nav="psychro",
        form=form,
        second_properties=psy_mod._second_properties(U),
        on=extra.get("on"),
        m_da=extra.get("m_da"),
        result=result,
        chart=chart,
        error=error,
        pressure=pressure,
    )


@bp.route("/psychrometrics/heat-humidify", methods=["GET", "POST"])
@require_module("psychro.heat_humidify")
def heat_humidify():
    def unpack(packed):
        pressure, on, m_da, result, points, segments = packed
        return pressure, points, segments, result, {"on": on, "m_da": m_da}

    U, form, result, error, pressure, chart, extra = _psychro_simple_post(
        psy_mod._HEAT_HUMIDIFY_DEFAULTS,
        psy_mod._HEAT_HUMIDIFY_FIELD_UNITS,
        ("on", "off"),
        psy_mod._run_heat_humidify,
        unpack,
        tool="heat_humidify",
    )
    return render_template(
        "v2/heat_humidify.html",
        active="psychro_heat_humidify",
        nav="psychro",
        form=form,
        second_properties=psy_mod._second_properties(U),
        on=extra.get("on"),
        m_da=extra.get("m_da"),
        result=result,
        chart=chart,
        error=error,
        pressure=pressure,
    )


@bp.route("/psychrometrics/adiabatic-cool", methods=["GET", "POST"])
@require_module("psychro.adiabatic_cool")
def adiabatic_cool():
    def unpack(packed):
        pressure, on, m_da, result, points, segments = packed
        return pressure, points, segments, result, {"on": on, "m_da": m_da}

    U, form, result, error, pressure, chart, extra = _psychro_simple_post(
        psy_mod._ADIABATIC_COOL_DEFAULTS,
        psy_mod._ADIABATIC_COOL_FIELD_UNITS,
        ("on",),
        psy_mod._run_adiabatic_cool,
        unpack,
        tool="adiabatic",
    )
    return render_template(
        "v2/adiabatic_cool.html",
        active="psychro_adiabatic_cool",
        nav="psychro",
        form=form,
        second_properties=psy_mod._second_properties(U),
        on=extra.get("on"),
        m_da=extra.get("m_da"),
        result=result,
        chart=chart,
        error=error,
        pressure=pressure,
    )


@bp.route("/psychrometrics/ahu", methods=["GET", "POST"])
@require_module("psychro.ahu")
def ahu():
    U = current_view()
    result = None
    error = None
    m_da = None
    pressure = None
    oa_frac = None
    pts, segs = [], []
    initial_step = 1
    if request.method != "POST":
        form = psy_mod._display_defaults(psy_mod._AHU_DEFAULTS, psy_mod._AHU_FIELD_UNITS, U)
        psy_mod._paste_slot_into(form, "oa", U)
        psy_mod._paste_slot_into(form, "ra", U)
        psy_mod._paste_slot_into(form, "sup", U)
        try:
            pressure = psy_mod._resolve_pressure(form, U)
        except ValueError:
            pressure = None
        try:
            initial_step = int(request.args.get("step") or 1)
        except ValueError:
            initial_step = 1
    else:
        form = {k: request.form.get(k, d) for k, d in psy_mod._AHU_DEFAULTS.items()}
        try:
            pressure, m_da, result, pts, segs, oa_frac = psy_mod._run_ahu(form, U)
            initial_step = 6
            if result is not None:
                from app.analytics import note_pro_tool_use

                note_pro_tool_use("ahu_design")
        except ValueError as exc:
            result = None
            error = str(exc)
            initial_step = 5
            try:
                pressure = psy_mod._resolve_pressure(form, U)
            except ValueError:
                pressure = None
    chart = psy_mod._chart_or_blank(pts, segs, pressure, U.system)
    return render_template(
        "v2/ahu.html",
        active="psychro_ahu",
        nav="psychro",
        form=form,
        second_properties=psy_mod._second_properties(U),
        result=result,
        m_da=m_da,
        chart=chart,
        error=error,
        pressure=pressure,
        oa_frac=oa_frac,
        season_defaults=psy_mod._ahu_season_defaults_display(U),
        initial_step=initial_step,
    )
