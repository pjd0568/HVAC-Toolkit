"""Site Data - Weather & Design Conditions: map + location search -> ASHRAE-style
cooling/heating design conditions for that exact coordinate.

Thin web layer over app.weather_client (the Open-Meteo I/O boundary) and
hvac_engine.climate (the pure percentile calculation) -- see
specs/SPEC-weather-climate-data.md. Server-rendered with a shareable GET URL,
consistent with the other tools: once a location is picked, lat/lon/elevation/
place/years are all query parameters, so a specific lookup is a link. The map
and search box are JS-driven (static/js/weathermap.js) but resolve to a normal
form submit -- no bespoke client-side rendering path, same as every other tool's
auto-submitting selects.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta

from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, url_for

from hvac_engine.climate import COOLING_FRACTIONS, EXTREME_RETURN_PERIODS, HEATING_FRACTIONS

from app.access_gate import require_module
from app.climate_slots import clear_slot, save_slot
from app.reports.builder import ReportMeta, build_pdf
from app.reports.map_image import MAP_ASPECT, render_location_map_png
from app.units import current_view
from app.weather_client import (
    WeatherLookupError,
    fetch_design_conditions,
    fetch_elevation,
    fetch_hourly_for_date,
    geocode_search,
    manual_design_states,
)

bp = Blueprint("weather", __name__)

YEAR_OPTIONS = (10, 15, 20)
DEFAULT_YEARS = 20

# "On This Day" date bounds: Open-Meteo's ERA5 archive starts 1940; "yesterday"
# rather than today, since today's data may still be provisional/incomplete.
EARLIEST_DAY = date_cls(1940, 1, 1)


def _max_day() -> date_cls:
    return date_cls.today() - timedelta(days=1)


def _parse_day(raw: str | None) -> date_cls | None:
    """A valid `date` query param -> a date object, or None if absent,
    unparseable, or outside the archive's range -- never raises, so a bad/
    stale date in the URL degrades to "no day selected" rather than a 500."""
    if not raw:
        return None
    try:
        d = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None
    if d < EARLIEST_DAY or d > _max_day():
        return None
    return d

# Hours/year each percentile represents, for a concrete "what does 0.4% mean"
# figure alongside the raw percentage -- e.g. 0.4% of a nominal 8760-hour year
# is ~35 hours. This is "hours per year the condition is met or exceeded on
# average", not a rare "1-in-N-year" event -- ASHRAE design percentiles are an
# annual cumulative frequency, the same tail recurs to some degree every year.
_HOURS_PER_YEAR = 8760
COOLING_HOURS = {label: round(frac * _HOURS_PER_YEAR) for label, frac in COOLING_FRACTIONS.items()}
HEATING_HOURS = {label: round(frac * _HOURS_PER_YEAR) for label, frac in HEATING_FRACTIONS.items()}


def _format_timestamp(ts: str) -> str:
    """Open-Meteo's local-time ISO string -> a readable date/time. Falls back to
    the raw value if it's ever not parseable (defensive; shouldn't happen)."""
    try:
        return datetime.fromisoformat(ts).strftime("%d %b %Y, %H:%M")
    except (ValueError, TypeError):
        return ts


def _years_from(args) -> int:
    try:
        years = int(args.get("years", DEFAULT_YEARS))
    except (TypeError, ValueError):
        return DEFAULT_YEARS
    return years if years in YEAR_OPTIONS else DEFAULT_YEARS


def _location_from(args):
    """(lat, lon, elevation, place) from query/form args, or None if unset."""
    lat_raw, lon_raw = args.get("lat", ""), args.get("lon", "")
    if lat_raw in ("", None) or lon_raw in ("", None):
        return None
    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
        elevation = float(args.get("elevation", "0") or 0.0)
    except (TypeError, ValueError):
        return None
    return lat, lon, elevation, args.get("place", "").strip()


# Manual-entry field names (query params). Kept together so index(), report()
# and the report_form hidden fields all reference the same set.
_MANUAL_FIELDS = ("m_su_db", "m_su_wb", "m_wi_db", "m_wi_wb", "m_elev", "m_label")


def _parse_manual(args, U):
    """Parse the manual design-condition inputs (Summer/Winter DB+WB, an optional
    site elevation and a free-text source label) into (ManualConditions|None,
    raw_dict, error). Temperatures and elevation are entered in the active unit
    system and converted to SI here before any psychrometrics. A blank field is
    None (Winter WB in particular is optional); a non-numeric entry yields a
    clean on-page error rather than a 500, same as every other tool. Returns
    (None, raw, None) when nothing has been entered yet so the form just shows
    empty."""
    raw = {name: args.get(name, "").strip() for name in _MANUAL_FIELDS}

    def _to_si(name: str, quantity: str) -> float | None:
        val = raw[name]
        if val == "":
            return None
        return U.to_si(quantity, float(val))

    if not any(raw[n] for n in ("m_su_db", "m_su_wb", "m_wi_db", "m_wi_wb")):
        return None, raw, None  # nothing entered yet

    try:
        elevation_si = _to_si("m_elev", "altitude") or 0.0
        manual = manual_design_states(
            elevation_si,
            _to_si("m_su_db", "temperature"),
            _to_si("m_su_wb", "temperature"),
            _to_si("m_wi_db", "temperature"),
            _to_si("m_wi_wb", "temperature"),
        )
    except (TypeError, ValueError):
        return None, raw, "Enter numbers only for the design temperatures and elevation."
    return manual, raw, None


@bp.route("/", methods=["GET"])
@require_module("weather")
def index():
    U = current_view()
    mode = "manual" if request.args.get("mode") == "manual" else "era5"
    manual, manual_raw, manual_error = _parse_manual(request.args, U)
    years = _years_from(request.args)
    location = _location_from(request.args)
    dc = cooling_states = heating_states = max_state = min_state = None
    extreme_annual = None
    error = None
    lat = lon = elevation = None
    place = ""
    extreme_max_at = extreme_min_at = None
    if mode == "era5" and location is not None:
        lat, lon, elevation, place = location
        try:
            result = fetch_design_conditions(lat, lon, elevation, years=years)
            dc = result.dc
            cooling_states = result.cooling_states
            heating_states = result.heating_states
            max_state = result.max_state
            min_state = result.min_state
            extreme_annual = result.extreme_annual
            extreme_max_at = _format_timestamp(dc.extreme_max_db_at)
            extreme_min_at = _format_timestamp(dc.extreme_min_db_at)
        except WeatherLookupError as exc:
            error = str(exc)

    # "On This Day" is deliberately independent of the block above: picking a
    # date never re-triggers (or depends on the success of) the multi-year
    # percentile fetch -- see fetch_hourly_for_date's docstring.
    selected_day = _parse_day(request.args.get("date"))
    day_readings = None
    day_error = None
    if mode == "era5" and location is not None and selected_day is not None:
        try:
            day_readings = fetch_hourly_for_date(lat, lon, elevation, selected_day)
        except WeatherLookupError as exc:
            day_error = str(exc)

    return render_template(
        "weather.html", active="weather",
        mode=mode, manual=manual, manual_raw=manual_raw, manual_error=manual_error,
        years=years, year_options=YEAR_OPTIONS,
        lat=lat, lon=lon, elevation=elevation, place=place,
        dc=dc, error=error,
        cooling_hours=COOLING_HOURS, heating_hours=HEATING_HOURS,
        cooling_states=cooling_states, heating_states=heating_states,
        max_state=max_state, min_state=min_state,
        extreme_annual=extreme_annual,
        return_periods=EXTREME_RETURN_PERIODS,
        default_period=EXTREME_RETURN_PERIODS[-1],  # most extreme (50-yr) shown first
        extreme_max_at=extreme_max_at, extreme_min_at=extreme_min_at,
        selected_day=selected_day.isoformat() if selected_day else "",
        day_min=EARLIEST_DAY.isoformat(), day_max=_max_day().isoformat(),
        day_readings=day_readings, day_error=day_error,
        # climate_slots is no longer passed explicitly -- it's injected into
        # every template app-wide now that the banner is global (see
        # app/__init__.py::inject_climate_slots), not just this page.
    )


@bp.route("/slots/save", methods=["POST"])
@require_module("weather")
def save_slot_route():
    """Copy a condition (from a Summer/Winter percentile block, the Max/Min
    column, or an On This Day hour) into one of the 3 session-backed slots.
    Values arrive as hidden fields already in SI -- the templates render them
    from the same PsychroState/DesignPoint the page itself displays, so a
    slot can never disagree with what was on screen when it was copied."""
    form = request.form

    def _f(name: str) -> float | None:
        raw = form.get(name, "")
        if raw in ("", None):
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    try:
        index = int(form["slot"])
    except (KeyError, ValueError):
        return Response("Invalid slot", status=400)

    db = _f("db")
    if db is None:
        return Response("Missing dry-bulb value", status=400)

    try:
        save_slot(
            index,
            label=form.get("label", ""),
            db=db, wb=_f("wb"), rh=_f("rh"), dp=_f("dp"), w=_f("w"),
            source=form.get("source", "").strip(),
        )
    except ValueError as exc:
        return Response(str(exc), status=400)
    return redirect(form.get("next") or url_for("weather.index"))


@bp.route("/slots/clear", methods=["POST"])
def clear_slot_route():
    form = request.form
    try:
        index = int(form["index"])
    except (KeyError, ValueError):
        return Response("Invalid slot", status=400)
    try:
        clear_slot(index)
    except ValueError as exc:
        return Response(str(exc), status=400)
    return redirect(form.get("next") or url_for("weather.index"))


@bp.route("/search", methods=["GET"])
@require_module("weather")
def search():
    """JSON typeahead endpoint for the search box (see weathermap.js)."""
    try:
        results = geocode_search(request.args.get("q", ""))
    except WeatherLookupError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify([
        {"label": r.label, "lat": r.lat, "lon": r.lon, "elevation_m": r.elevation_m}
        for r in results
    ])


@bp.route("/elevation", methods=["GET"])
@require_module("weather")
def elevation():
    """JSON endpoint the map-click flow uses when there's no geocoder result to
    take elevation from (see weathermap.js)."""
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "lat and lon are required"}), 400
    try:
        elevation_m = fetch_elevation(lat, lon)
    except WeatherLookupError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"elevation_m": elevation_m})


def _state_rows(U, tag, db, state):
    """Dry-bulb plus (if resolved) wet-bulb/RH/dew-point/moisture-ratio for one
    named condition. Dry-bulb is always shown from the raw design-point value
    (never from `state`), so a condition still shows *something* even in the
    rare case its full state couldn't be resolved (see WeatherResult's
    max_state/min_state docstring) -- consistent with how the on-screen
    columns degrade the same way."""
    rows = [(f"{tag} Dry-Bulb", U.fmt("temperature", db, 1), U.sym("temperature"))]
    if state is None:
        return rows
    rows.append((f"{tag} Wet-Bulb", U.fmt("temperature", state.t_wb, 1), U.sym("temperature")))
    rows.append((f"{tag} Relative Humidity", f"{state.rh * 100:.0f}", "%"))
    rows.append((f"{tag} Dew Point", U.fmt("temperature", state.t_dp, 1), U.sym("temperature")))
    rows.append((f"{tag} Moisture Ratio", U.fmt("humidity_ratio", state.w), U.sym("humidity_ratio")))
    return rows


def _design_condition_rows(U, result):
    dc = result.dc
    rows = []
    for label in ("0.4", "1.0", "2.0"):
        tag = f"Summer {label}% (~{COOLING_HOURS[label]} h/yr)"
        rows.extend(_state_rows(U, tag, dc.cooling[label].db, result.cooling_states.get(label)))
    for label in ("99.6", "99", "98"):
        tag = f"Winter {label}% (~{HEATING_HOURS[label]} h/yr)"
        rows.extend(_state_rows(U, tag, dc.heating[label].db, result.heating_states.get(label)))
    rows.append(("Years of Record Used", f"{dc.years_used} of {dc.years_requested} requested", ""))
    rows.extend(_extreme_annual_rows(U, result.extreme_annual))
    rows.extend(_state_rows(U, "Absolute Record Maximum", dc.extreme_max_db, result.max_state))
    rows.append(("Absolute Record Maximum — Recorded", _format_timestamp(dc.extreme_max_db_at), ""))
    rows.extend(_state_rows(U, "Absolute Record Minimum", dc.extreme_min_db, result.min_state))
    rows.append(("Absolute Record Minimum — Recorded", _format_timestamp(dc.extreme_min_db_at), ""))
    return rows


def _extreme_annual_rows(U, ea):
    """Extreme Annual Design Conditions block for the PDF: the mean/std-dev of the
    annual extremes plus the n-year return-period values, dry-bulb and wet-bulb,
    both ends. Omitted entirely if there were too few qualifying years to compute
    it (ea is None) -- see ExtremeAnnual / _extreme_annual."""
    if ea is None:
        return []
    tsym = U.sym("temperature")
    rows = [
        (f"Extreme Annual — from {ea.n_years} yrs (mean ± SD)", "", ""),
        ("Annual Max Dry-Bulb — mean",
         f"{U.fmt('temperature', ea.db.mean_max, 1)} ± {U.fmt('temperature', ea.db.std_max, 1)}", tsym),
        ("Annual Min Dry-Bulb — mean",
         f"{U.fmt('temperature', ea.db.mean_min, 1)} ± {U.fmt('temperature', ea.db.std_min, 1)}", tsym),
        ("Annual Max Wet-Bulb — mean",
         f"{U.fmt('temperature', ea.wb.mean_max, 1)} ± {U.fmt('temperature', ea.wb.std_max, 1)}", tsym),
        ("Annual Min Wet-Bulb — mean",
         f"{U.fmt('temperature', ea.wb.mean_min, 1)} ± {U.fmt('temperature', ea.wb.std_min, 1)}", tsym),
    ]
    for n in ea.periods:
        rows.append((f"{n}-Year Max Dry-Bulb", U.fmt("temperature", ea.db.return_max[n], 1), tsym))
        rows.append((f"{n}-Year Max Wet-Bulb", U.fmt("temperature", ea.wb.return_max[n], 1), tsym))
        rows.append((f"{n}-Year Min Dry-Bulb", U.fmt("temperature", ea.db.return_min[n], 1), tsym))
        rows.append((f"{n}-Year Min Wet-Bulb", U.fmt("temperature", ea.wb.return_min[n], 1), tsym))
    return rows


def _manual_condition_rows(U, manual):
    """PDF rows for a manually-entered design-condition set: the site pressure
    used for the humidity derivations, then the Summer/Winter DB/WB/RH/etc.
    Only an end that was actually entered (its DB is not None) is included."""
    rows = [("Site Design Pressure", U.fmt("pressure", manual.pressure), U.sym("pressure"))]
    if manual.summer_db is not None:
        rows.extend(_state_rows(U, "Summer (cooling)", manual.summer_db, manual.summer))
    if manual.winter_db is not None:
        rows.extend(_state_rows(U, "Winter (heating)", manual.winter_db, manual.winter))
    return rows


def _safe_map_png(lat: float, lon: float) -> bytes | None:
    """A failed map snapshot must never take down the whole PDF -- the design-
    condition tables are the point of this report, the map is one section of
    it (same reasoning as psychro.py's _safe_chart_png)."""
    try:
        return render_location_map_png(lat, lon)
    except Exception:
        current_app.logger.exception("site location map render failed for PDF report")
        return None


@bp.route("/report", methods=["POST"])
@require_module("weather")
def report():
    """Mirrors the psychrometric tools' PDF pattern (see _report_form.html): the
    calculation inputs travel as hidden fields and are recomputed here from
    scratch -- no server-side session, and the PDF can never drift from the
    numbers the user was looking at."""
    U = current_view()
    form = request.form

    # Manual-entry PDF: built from the typed design conditions, no ERA5 fetch and
    # no location map (there's no site to plot). Same hidden-field-round-trip
    # pattern as the ERA5 path, just a different input set.
    if form.get("mode") == "manual":
        manual, raw, manual_error = _parse_manual(form, U)
        if manual is None:
            return Response(
                f"Cannot generate report: {manual_error or 'no manual design conditions entered'}",
                status=400,
            )
        label = raw.get("m_label", "").strip()
        input_rows = [
            ("Data Source", label or "Manually entered", ""),
            ("Basis", "User-entered design conditions (not ERA5-derived)", ""),
        ]
        result_rows = _manual_condition_rows(U, manual)
        meta = ReportMeta(
            brand_name=current_app.config["BRAND_NAME"],
            tool_title="Site Data - Weather & Design Conditions (Manual)",
            project=form.get("report_project", "").strip(),
            system=form.get("report_system", "").strip(),
            revision=form.get("report_revision", "").strip(),
            author=form.get("report_author", "").strip(),
            logo_path=current_app.config.get("REPORT_LOGO_PATH", "") or "",
        )
        pdf = build_pdf(meta, input_rows, result_rows)
        return Response(
            pdf, mimetype="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="weather-design-conditions-manual.pdf"'},
        )

    try:
        lat = float(form["lat"])
        lon = float(form["lon"])
        elevation = float(form.get("elevation", "0") or 0.0)
    except (KeyError, ValueError) as exc:
        return Response(f"Cannot generate report: missing or invalid location ({exc})", status=400)
    years = _years_from(form)
    place = form.get("place", "").strip()

    try:
        result = fetch_design_conditions(lat, lon, elevation, years=years)
    except WeatherLookupError as exc:
        return Response(f"Cannot generate report: {exc}", status=400)

    input_rows = [
        ("Location", place or "—", ""),
        ("Latitude", f"{lat:.4f}", "°"),
        ("Longitude", f"{lon:.4f}", "°"),
        ("Elevation", U.fmt("altitude", elevation, 0), U.sym("altitude")),
        ("Years of Record Requested", str(years), ""),
    ]
    result_rows = _design_condition_rows(U, result)

    meta = ReportMeta(
        brand_name=current_app.config["BRAND_NAME"],
        tool_title="Site Data - Weather & Design Conditions",
        project=form.get("report_project", "").strip(),
        system=form.get("report_system", "").strip(),
        revision=form.get("report_revision", "").strip(),
        author=form.get("report_author", "").strip(),
        logo_path=current_app.config.get("REPORT_LOGO_PATH", "") or "",
    )
    map_png = _safe_map_png(lat, lon)
    pdf = build_pdf(
        meta, input_rows, result_rows,
        chart_png=map_png, chart_title="Site Location Map", chart_aspect=MAP_ASPECT,
    )
    return Response(
        pdf, mimetype="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="weather-design-conditions.pdf"'},
    )
