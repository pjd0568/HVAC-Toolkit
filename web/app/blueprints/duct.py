"""Duct Sizing tool — an independent 3-column sizer, plus a separate Index
Leg pressure-drop builder below it.

Phase A (core sizing, all three shapes at once) — see specs/SPEC-duct-sizing.md.

Correction #2: the three shapes (circular/rectangular/flat oval) are shown
side by side and all update instantly on a top-input change. Within a
shape's own column, rectangular's width & height and flat-oval's major &
minor can each be nudged, and Correction #4/#5 (below) describe how those
nudges behave per shape.

Correction #3: round-to-25mm, a persistent rectangular "lock" concept, and
removing four top-level fields Paul judged unnecessary as always-visible
inputs.

Correction #4: rectangular width and height are fully independent — no
solving one from the other. `rect_lock_width` / `rect_lock_height` are
independent booleans; a locked dimension survives a Calculate (full
re-size), an unlocked one resets to a fresh 1:1-derived value. Live
edits to volume/target keep all current sizes and only refresh outputs.

Correction #5: flat oval's major and minor are independent too, but every
code path snaps the working pair to a genuine `LINDAB_FLAT_OVAL_CATALOG`
combination — Lindab only manufactures specific major/minor pairs, unlike
rectangular sheet metal which is free-form.

Correction #6 (this revision) — Index Leg rework, off Paul's direct
feedback on the first Phase C build: a single shared duty (one shape/volume
for the whole leg) doesn't match how a real index leg works. A real run is
a SEQUENCE of different pieces — volume drops at every branch, the duct
tapers and can change shape entirely, and terminates at a grille via
louvers/attenuators/dampers/flex. So:

- **The top 3-column sizer is now fully independent of the index leg.**
  `_compute_state()` no longer builds or returns anything index-leg related;
  nudging/locking/stepping the top sizer never touches the leg, and vice
  versa. Two separate JSON endpoints (`/api/state` for the sizer,
  `/api/leg-state` for the leg) reflect this at the routing level too.
- **Every row in the index leg now carries its own volume, shape and size**
  — sized by direct evaluation (`hvac_engine.duct.size_circular/rectangular/
  flat_oval` called with volume + given dimensions, not solved for a
  target), not against one shared duty. Row sizing is free-typed (no
  catalogue snapping) — Paul's scoping default for this session, flagged as
  changeable later.
- **Four row types**: "straight" and "fitting" as before (K-factor / length
  x friction-rate, from `hvac_engine.fittings`), plus two new ones —
  "flex" (a straight run derated via `hvac_engine.duct.apply_flex_derate`)
  and "accessory" (louvers, attenuators, VCD/FD dampers, single-blade
  dampers, grilles — Paul's explicit call: "for custom items we add the
  pressure drop directly, we may add some predefined K factors for some
  elements later" — so this type takes a free-text label plus a manually
  entered Pa value via `hvac_engine.fittings.accessory_pressure_drop()`, and
  needs no shape/volume/size at all).
- **A staging area computes a live preview of the row being composed**
  (fields carried in the query string with a `stage_` prefix, entirely
  separate from the committed `leg_<field>_<i>` rows) before the user clicks
  "Add to Table" to commit it as a new row.
- **Every committed row is directly editable in place** — changing its
  volume/shape/size/length/fitting/label/dp live-recomputes that one row and
  the running total, without needing to touch type/shape (the explicit
  "engineer finds the run's over pressure, tweaks one line's volume/size to
  bring it down" workflow).
- **Clear Table, per-row Remove, and CSV Export** (`/index-leg/export.csv`).

Rows (and the staging draft) are computed by one shared `_compute_row()`,
each wrapped in its own try/except by the caller — one bad row must never
blank out the rest of the table, and a bad staging draft must never affect
the committed rows.
"""

from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, has_request_context, jsonify, render_template, request, session

from hvac_engine import duct as eng
from hvac_engine import fittings as fit

from app.access_gate import require_module, require_suite_access
from app.reports.builder import build_pdf
from app.reports.helpers import pdf_response, report_meta_from_form
from app.units import current_view

bp = Blueprint("duct", __name__)

BASES = ("velocity", "friction_rate")

# Constants for fields removed from the visible UI (Correction #3) -- still
# readable from the query string (kept flexible for a hand-built/shared
# link), just no longer rendered as editable top-level inputs.
DEFAULT_RECT_ASPECT = 1.0

# -- Index Leg (Correction #6) ------------------------------------------------

ROW_SHAPE_LABELS = {
    "circular": "Circular",
    "rectangular": "Rectangular",
    "flat_oval": "Flat Oval",
}

ROW_TYPE_LABELS = {
    "straight": "Straight Duct",
    "fitting": "Fitting",
    "flex": "Flex Duct",
    "accessory": "Accessory / Custom",
}

ROW_FIELDS = (
    "type", "shape", "volume", "diameter", "width", "height",
    "major", "minor", "length", "fitting", "label", "dp",
)

# Sensible starting points when a field is blank -- both for the staging
# area's very first render, and so an existing row that just had its SHAPE
# switched (e.g. circular -> rectangular) doesn't immediately error just
# because its new shape's dimension fields aren't in the submitted form yet.
# All in canonical SI (see hvac_engine.duct's module docstring).
DEFAULT_ROW_VOLUME_SI = 1800.0 / 3600.0 * 3600.0  # 1800 m3/h, matches the top sizer's own default
DEFAULT_ROW_DIAMETER_SI = 0.2      # 200mm
DEFAULT_ROW_WIDTH_SI = 0.4         # 400mm
DEFAULT_ROW_HEIGHT_SI = 0.2        # 200mm
DEFAULT_ROW_MAJOR_SI = 0.4         # 400mm
DEFAULT_ROW_MINOR_SI = 0.2         # 200mm
DEFAULT_ROW_LENGTH_SI = 3.0        # 3 m
DEFAULT_ROW_DP_SI = 10.0           # 10 Pa
DEFAULT_ROW_LABEL = "Accessory"

# Hard ceiling on row count -- purely defensive (a hand-edited query string
# with an absurd leg_row_count shouldn't be able to force the server to loop
# unboundedly); no real index leg needs anywhere near this many rows.
MAX_LEG_ROWS = 60


# -- parsing helpers -----------------------------------------------------------------

def _f(raw):
    """Parse a display string to float, or raise a clear ValueError."""
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{raw}' is not a number")


def _s(args, key, default):
    """Raw display-string for a field: whatever's in the query string, or a
    default -- never raises, so an invalid value still re-populates the form
    field instead of silently reverting to the default."""
    raw = args.get(key)
    return raw if raw not in (None, "") else default


def _basis(args):
    basis = args.get("basis", "velocity")
    return basis if basis in BASES else "velocity"


def _round25(value_m, on):
    """Quantise a dimension to the nearest 25 mm grid point if `on`, else
    pass through unchanged. Thin wrapper so every rectangular call site
    applies the same rule the same way."""
    return eng.round_to_increment(value_m, 25.0) if on else value_m


# SI volume display for the sizer only. Canonical engine flow stays m³/h.
# A bare volume in the query string (no duct_flow_unit) stays m³/s so older
# links keep the same airflow.
DUCT_FLOW_UNITS = ("ls", "m3h", "m3s")
_DUCT_FLOW_SYMBOL = {"ls": "l/s", "m3h": "m³/h", "m3s": "m³/s"}
_DUCT_FLOW_FROM_M3H = {"ls": 1.0 / 3.6, "m3h": 1.0, "m3s": 1.0 / 3600.0}
_DUCT_FLOW_DP = {"ls": 1, "m3h": 1, "m3s": 3}
_DEFAULT_DUCT_VOLUME_M3H = 1800.0


def _duct_flow_unit(args, U) -> str:
    """Active sizer volume unit. IP ignores this and stays on CFM."""
    if U.system != "SI":
        return "m3s"
    raw = (args.get("duct_flow_unit") or "").strip()
    if raw in DUCT_FLOW_UNITS:
        if has_request_context():
            session["duct_flow_unit"] = raw
        return raw
    if args.get("volume") not in (None, ""):
        return "m3s"
    if has_request_context():
        saved = session.get("duct_flow_unit")
        if saved in DUCT_FLOW_UNITS:
            return saved
    return "m3s"


def duct_flow_symbol(unit: str, U) -> str:
    if U.system != "SI":
        return U.sym("duct_flow")
    return _DUCT_FLOW_SYMBOL.get(unit, "m³/s")


def fmt_duct_volume(m3h: float, unit: str, U) -> str:
    if U.system != "SI":
        return U.fmt("duct_flow", m3h)
    factor = _DUCT_FLOW_FROM_M3H.get(unit, _DUCT_FLOW_FROM_M3H["m3s"])
    dp = _DUCT_FLOW_DP.get(unit, 3)
    return f"{m3h * factor:.{dp}f}"


def duct_volume_to_m3h(display: float, unit: str, U) -> float:
    if U.system != "SI":
        return U.to_si("duct_flow", display)
    factor = _DUCT_FLOW_FROM_M3H.get(unit, _DUCT_FLOW_FROM_M3H["m3s"])
    return display / factor


# -- top 3-column sizer (fully independent of the index leg) -------------------------

def _compute_state(args, U):
    """Compute the top duct-sizing state (top inputs + all 3 columns) from
    request args. Returns (fields, circular, rectangular, flat_oval, error).

    Correction #6: this function is now fully independent of the index leg
    -- it neither reads nor returns anything leg-related. `fields` carries
    every raw display-string field (for re-populating the form / building
    the next request's query string); `circular` / `rectangular` /
    `flat_oval` are dicts of pre-formatted display strings + status flags
    ready to drop straight into the template or a JSON response -- no unit
    or engine maths happens anywhere else.
    """
    fields = {}
    circular = rectangular = flat_oval = None
    error = None

    try:
        # -- top inputs -----------------------------------------------------
        basis = _basis(args)
        default_target = (
            U.fmt("velocity", eng.DEFAULT_MAX_VELOCITY * 0.75)
            if basis == "velocity"
            else U.fmt("friction_rate", eng.DEFAULT_MAX_FRICTION_RATE)
        )
        flow_unit = _duct_flow_unit(args, U)
        fields["duct_flow_unit"] = flow_unit if U.system == "SI" else ""
        fields["volume"] = _s(args, "volume", fmt_duct_volume(_DEFAULT_DUCT_VOLUME_M3H, flow_unit, U))
        fields["basis"] = basis
        fields["target_value"] = _s(args, "target_value", default_target)

        volume_si = duct_volume_to_m3h(_f(fields["volume"]), flow_unit, U)
        target_value_si = U.to_si(basis, _f(fields["target_value"]))

        # Thresholds and default-derivation parameters (Correction #3: no
        # longer rendered as top-level inputs, but still overridable via the
        # query string for a hand-built link).
        max_velocity_si = U.to_si("velocity", _f(_s(args, "max_velocity", U.fmt("velocity", eng.DEFAULT_MAX_VELOCITY))))
        max_friction_si = U.to_si("friction_rate", _f(_s(args, "max_friction_rate", U.fmt("friction_rate", eng.DEFAULT_MAX_FRICTION_RATE))))
        rect_aspect = _f(_s(args, "rect_aspect", str(DEFAULT_RECT_ASPECT)))

        # De_ref -- the true, unsnapped calculated size for the given target.
        # This is also exactly the circular column's "auto" result, and the
        # reference every rectangular-lock calculation re-solves against.
        ref = eng.size_circular(volume=volume_si, **{basis: target_value_si})

        nudge = args.get("nudge") or ""
        nudge_value = args.get("nudge_value")

        # -- circular ---------------------------------------------------------
        circular_mm = args.get("circular_mm", "") or ""
        if nudge == "circular_mm":
            circular_mm = nudge_value or ""
        fields["circular_mm"] = circular_mm

        catalog_by_mm = {c.mm: c for c in eng.LINDAB_CIRCULAR_CATALOG}
        if circular_mm in ("", "auto"):
            circ_result = ref
            circ_is_auto = True
            circ_catalog = None
        else:
            chosen_mm = int(round(_f(circular_mm)))
            circ_result = eng.size_circular(volume=volume_si, diameter=chosen_mm / 1000.0)
            circ_is_auto = False
            circ_catalog = catalog_by_mm.get(chosen_mm)

        circular = {
            "is_auto": circ_is_auto,
            "selected_mm": "" if circ_is_auto else str(int(round(_f(circular_mm)))),
            "diameter": U.fmt("duct_dimension", circ_result.diameter),
            "velocity": U.fmt("velocity", circ_result.velocity),
            "velocity_pressure": U.fmt("velocity_pressure", eng.velocity_pressure(circ_result.velocity)),
            "friction_rate": U.fmt("friction_rate", circ_result.friction_rate),
            "status_velocity": eng.status(circ_result.velocity, max_velocity_si),
            "status_friction": eng.status(circ_result.friction_rate, max_friction_si),
            "gauge_mm": circ_catalog.gauge_mm if circ_catalog else None,
            "standard": circ_catalog.standard if circ_catalog else None,
        }

        # -- rectangular --------------------------------------------------------
        # Correction #4: width and height are now fully independent -- no
        # solving between them anywhere. Each is either pinned (typed/nudged
        # this request or a previous one) or freshly derived from the
        # reference De at a 1:1 aspect ratio. Lock only controls whether a
        # Calculate (full re-size) clears the pin; live volume/target edits
        # keep pinned sizes and only refresh outputs.
        lock_width = args.get("rect_lock_width") == "1"
        lock_height = args.get("rect_lock_height") == "1"
        fields["rect_lock_width"] = "1" if lock_width else ""
        fields["rect_lock_height"] = "1" if lock_height else ""

        round25 = args.get("rect_round25") == "1"
        fields["rect_round25"] = "1" if round25 else ""

        width_raw = args.get("rect_width")
        if nudge == "rect_width":
            width_raw = nudge_value
        if width_raw:
            width_si = U.to_si("duct_dimension", _f(width_raw))
        else:
            width_si, _ = eng.rectangular_from_equivalent_diameter(ref.diameter, DEFAULT_RECT_ASPECT)
        width_si = _round25(width_si, round25)

        height_raw = args.get("rect_height")
        if nudge == "rect_height":
            height_raw = nudge_value
        if height_raw:
            height_si = U.to_si("duct_dimension", _f(height_raw))
        else:
            _, height_si = eng.rectangular_from_equivalent_diameter(ref.diameter, DEFAULT_RECT_ASPECT)
        height_si = _round25(height_si, round25)

        rect_result = eng.size_rectangular(volume_si, width_si, height_si)

        fields["rect_width"] = U.fmt("duct_dimension", rect_result.width)
        fields["rect_height"] = U.fmt("duct_dimension", rect_result.height)

        rectangular = {
            "width": fields["rect_width"],
            "height": fields["rect_height"],
            "velocity": U.fmt("velocity", rect_result.velocity),
            "velocity_pressure": U.fmt("velocity_pressure", eng.velocity_pressure(rect_result.velocity)),
            "friction_rate": U.fmt("friction_rate", rect_result.friction_rate),
            "equivalent_diameter": U.fmt("duct_dimension", rect_result.equivalent_diameter),
            "aspect_ratio": f"{rect_result.aspect_ratio:.2f}",
            "aspect_ratio_warning": rect_result.aspect_ratio_warning,
            "status_velocity": eng.status(rect_result.velocity, max_velocity_si),
            "status_friction": eng.status(rect_result.friction_rate, max_friction_si),
        }

        # -- flat oval ------------------------------------------------------------
        # Correction #5: major and minor are now independent (no more
        # equivalence-preserving solve between them), but every path below
        # ends by snapping the pair to a genuine LINDAB_FLAT_OVAL_CATALOG
        # combination -- see the module docstring for why flat oval needs
        # this and rectangular doesn't.
        oval_major_raw = args.get("oval_major")
        oval_minor_raw = args.get("oval_minor")
        has_pinned_oval = bool(oval_major_raw) and bool(oval_minor_raw)
        oval_nudge_dir = args.get("nudge_dir")  # "1" / "-1" -- stepper clicks only

        if has_pinned_oval:
            major_mm = round(U.to_si("duct_dimension", _f(oval_major_raw)) * 1000.0)
            minor_mm = round(U.to_si("duct_dimension", _f(oval_minor_raw)) * 1000.0)
        else:
            # Fresh: nearest stocked combination at/above the target
            # equivalent diameter -- same "never undersize" convention as
            # circular's stock-diameter snap.
            chosen = eng.snap_flat_oval_to_catalog(ref.diameter)
            major_mm, minor_mm = chosen.major_mm, chosen.minor_mm

        if nudge == "oval_major":
            if oval_nudge_dir is not None:
                major_mm = eng.flat_oval_step_major(major_mm, int(oval_nudge_dir))
            else:
                target_mm = U.to_si("duct_dimension", _f(nudge_value)) * 1000.0
                major_mm = eng.flat_oval_nearest_catalog_major(target_mm)
        elif nudge == "oval_minor":
            if oval_nudge_dir is not None:
                minor_mm = eng.flat_oval_step_minor(major_mm, minor_mm, int(oval_nudge_dir))
            else:
                target_mm = U.to_si("duct_dimension", _f(nudge_value)) * 1000.0
                minor_mm = eng.flat_oval_nearest_minor_for_major(major_mm, target_mm)

        # Final hard guarantee, regardless of which path above ran: snap to a
        # real catalogue pair. This is what makes an unstocked combination
        # unreachable, including from a hand-edited or stale query string.
        major_mm = eng.flat_oval_nearest_catalog_major(major_mm)
        minor_mm = eng.flat_oval_nearest_minor_for_major(major_mm, minor_mm)

        oval_result = eng.size_flat_oval(volume_si, major_mm / 1000.0, minor_mm / 1000.0)

        fields["oval_major"] = U.fmt("duct_dimension", oval_result.major)
        fields["oval_minor"] = U.fmt("duct_dimension", oval_result.minor)

        flat_oval = {
            "major": fields["oval_major"],
            "minor": fields["oval_minor"],
            "velocity": U.fmt("velocity", oval_result.velocity),
            "velocity_pressure": U.fmt("velocity_pressure", eng.velocity_pressure(oval_result.velocity)),
            "friction_rate": U.fmt("friction_rate", oval_result.friction_rate),
            "equivalent_diameter": U.fmt("duct_dimension", oval_result.equivalent_diameter),
            "status_velocity": eng.status(oval_result.velocity, max_velocity_si),
            "status_friction": eng.status(oval_result.friction_rate, max_friction_si),
        }

    except ValueError as exc:
        error = str(exc)

    return fields, circular, rectangular, flat_oval, error


def _catalog_options():
    """Circular stock-size dropdown options -- static per request (doesn't
    depend on the current sizing state), built once for the page render."""
    return [
        {
            "mm": c.mm,
            "label": f"{c.mm} mm" + ("" if c.standard else " (special order)"),
            "standard": c.standard,
        }
        for c in eng.LINDAB_CIRCULAR_CATALOG
    ]


def _nudge_step(U):
    """Stepper increment for the rectangular/flat-oval nudge buttons, in the
    active display unit -- a round number in whichever system is active
    (10 mm under SI, 0.5 in under IP), not a converted-and-rounded SI value.
    Overridden client-side to a 25 mm/1 in grid step when the rectangular
    "round to 25mm" checkbox is ticked."""
    return 0.5 if U.system == "IP" else 10.0


def _round25_step(U):
    """Stepper increment when the round-to-25mm checkbox is ticked -- always
    a 25 mm grid, converted to the active display unit."""
    return U.conv("duct_dimension", 0.025)


# -- Index Leg: per-row model (Correction #6) -----------------------------------------

def _row_shape_options():
    return [{"key": key, "label": label} for key, label in ROW_SHAPE_LABELS.items()]


def _row_type_options():
    return [{"key": key, "label": label} for key, label in ROW_TYPE_LABELS.items()]


def _fitting_options(shape: str):
    """Fitting-picker entries for the given shape, grouped the way the
    template renders its collapsible categories (SPEC-duct-sizing.md's
    Phase C section) -- one thumbnail per category, not per fitting."""
    return [
        {"key": f.key, "label": f.label, "k": f.k, "thumbnail_key": f.thumbnail_key}
        for f in fit.fittings_for_shape(shape)
    ]


def _row_field_getter(args, index):
    """Returns a `get(field)` closure reading either a committed row's fields
    (`leg_<field>_<index>`) or the staging draft's fields (`stage_<field>`,
    when index is None) -- the two share identical field names, just a
    different key pattern, so the rest of the row-computation logic doesn't
    need to know which one it's looking at."""
    if index is None:
        return lambda field: args.get(f"stage_{field}", "")
    return lambda field: args.get(f"leg_{field}_{index}", "")


def _to_si_or_default(get, field, quantity, U, default_si):
    """Parse a row field to SI, or fall back to a sensible default if it's
    blank -- e.g. a row that just had its shape switched from circular to
    rectangular won't have `width`/`height` in the submitted form yet
    (the DOM only had a `diameter` input a moment ago), so this lets the row
    recompute with a starting size instead of erroring. A genuinely
    non-numeric value (a real typo) still raises via _f(), so this only
    softens "missing", not "wrong"."""
    raw = get(field)
    if raw in (None, ""):
        return default_si
    return U.to_si(quantity, _f(raw))


def _compute_row(get, U):
    """Compute one index-leg row (or the staging draft, via the same
    function) from its own `get(field)` accessor. Returns a dict of
    pre-formatted display strings/status ready for the template or JSON --
    no unit or engine maths anywhere else. Raises ValueError for a row that
    can't be computed (an unknown type/shape/fitting key, or a genuinely
    non-numeric field) -- the caller isolates this per-row so one bad row
    never blanks out the rest of the table.

    Four row types (see the module docstring for the full rationale):
    "straight"/"flex" size a duct at THIS row's own volume+shape+dimensions
    (direct evaluation, not solved for a target -- an index leg is a
    sequence of already-decided pieces) and derive dp from length x friction
    rate (flex gets `hvac_engine.duct.apply_flex_derate` applied first);
    "fitting" sizes the same way but derives dp from K x velocity pressure;
    "accessory" needs no shape/volume/size at all -- Paul's explicit call is
    a direct manually-entered Pa value via
    `hvac_engine.fittings.accessory_pressure_drop()`.
    """
    row_type = get("type") or "straight"
    if row_type not in ROW_TYPE_LABELS:
        raise ValueError(f"unknown row type: {row_type!r}")

    if row_type == "accessory":
        label = get("label") or DEFAULT_ROW_LABEL
        dp_si = _to_si_or_default(get, "dp", "velocity_pressure", U, DEFAULT_ROW_DP_SI)
        dp_pa = fit.accessory_pressure_drop(dp_si)
        return {
            "type": row_type,
            "type_label": ROW_TYPE_LABELS[row_type],
            "shape": "",
            "label": label,
            "volume_display": "",
            "size_display": "",
            "size_edit": "",
            "velocity_display": "—",
            "velocity_pressure_display": "—",
            "friction_rate_display": "—",
            "friction_or_k_display": "—",
            "k": None,
            "fitting_key": "",
            "length_display": "",
            "dp_display": U.fmt("velocity_pressure", dp_pa),
            "dp_pa": dp_pa,
        }

    shape = get("shape") or "circular"
    if shape not in ROW_SHAPE_LABELS:
        raise ValueError(f"unknown duct shape: {shape!r}")

    volume_si = _to_si_or_default(get, "volume", "duct_flow", U, DEFAULT_ROW_VOLUME_SI)

    if shape == "circular":
        diameter_si = _to_si_or_default(get, "diameter", "duct_dimension", U, DEFAULT_ROW_DIAMETER_SI)
        result = eng.size_circular(volume=volume_si, diameter=diameter_si)
        size_edit = U.fmt("duct_dimension", result.diameter)
        size_display = f'{size_edit} {U.sym("duct_dimension")} dia'
    elif shape == "rectangular":
        width_si = _to_si_or_default(get, "width", "duct_dimension", U, DEFAULT_ROW_WIDTH_SI)
        height_si = _to_si_or_default(get, "height", "duct_dimension", U, DEFAULT_ROW_HEIGHT_SI)
        result = eng.size_rectangular(volume_si, width_si, height_si)
        size_edit = f'{U.fmt("duct_dimension", result.width)} x {U.fmt("duct_dimension", result.height)}'
        size_display = f'{size_edit} {U.sym("duct_dimension")}'
    else:  # flat_oval
        major_si = _to_si_or_default(get, "major", "duct_dimension", U, DEFAULT_ROW_MAJOR_SI)
        minor_si = _to_si_or_default(get, "minor", "duct_dimension", U, DEFAULT_ROW_MINOR_SI)
        result = eng.size_flat_oval(volume_si, major_si, minor_si)
        size_edit = f'{U.fmt("duct_dimension", result.major)} x {U.fmt("duct_dimension", result.minor)}'
        size_display = f'{size_edit} {U.sym("duct_dimension")}'

    velocity_pressure_pa = eng.velocity_pressure(result.velocity)
    friction_rate_si = result.friction_rate
    if row_type == "flex":
        friction_rate_si = eng.apply_flex_derate(friction_rate_si)

    if row_type in ("straight", "flex"):
        length_si = _to_si_or_default(get, "length", "duct_run_length", U, DEFAULT_ROW_LENGTH_SI)
        dp_pa = fit.straight_pressure_drop(length_si, friction_rate_si)
        label = ROW_TYPE_LABELS[row_type]
        fitting_key = ""
        k = None
        length_display = U.fmt("duct_run_length", length_si)
    else:  # fitting
        available = fit.fittings_for_shape(shape)
        fitting_key = get("fitting") or (available[0].key if available else "")
        fitting = fit.FITTINGS_BY_KEY.get(fitting_key)
        if fitting is None:
            raise ValueError(f"unknown fitting: {fitting_key!r}")
        dp_pa = fit.fitting_pressure_drop(fitting.k, velocity_pressure_pa)
        label = fitting.label
        k = fitting.k
        length_display = ""

    friction_rate_display = U.fmt("friction_rate", friction_rate_si)
    if row_type == "fitting" and k is not None:
        friction_or_k_display = f"K={k:.2f}"
    else:
        # Straight / flex: friction rate (Pa/m or in.wg/100ft).
        friction_or_k_display = f"{friction_rate_display} {U.sym('friction_rate')}"

    return {
        "type": row_type,
        "type_label": ROW_TYPE_LABELS[row_type],
        "shape": shape,
        "label": label,
        "volume_display": U.fmt("duct_flow", volume_si),
        "size_display": size_display,
        "size_edit": size_edit,
        "velocity_display": U.fmt("velocity", result.velocity),
        "velocity_pressure_display": U.fmt("velocity_pressure", velocity_pressure_pa),
        "friction_rate_display": friction_rate_display,
        "friction_or_k_display": friction_or_k_display,
        "k": k,
        "fitting_key": fitting_key,
        "length_display": length_display,
        "dp_display": U.fmt("velocity_pressure", dp_pa),
        "dp_pa": dp_pa,
    }


def _blank_row(row_type: str, shape: str, fitting_key: str) -> dict:
    """A row that failed to compute -- every display field degrades to a
    placeholder, dp_pa is 0.0 so it's safely excluded from the running total
    (the caller adds the error message and raw fields on top of this)."""
    return {
        "type": row_type or "straight",
        "type_label": ROW_TYPE_LABELS.get(row_type, "—"),
        "shape": shape or "",
        "label": "—",
        "volume_display": "",
        "size_display": "",
        "size_edit": "",
        "velocity_display": "—",
        "velocity_pressure_display": "—",
        "friction_rate_display": "—",
        "friction_or_k_display": "—",
        "k": None,
        "fitting_key": fitting_key or "",
        "length_display": "",
        "dp_display": "—",
        "dp_pa": 0.0,
    }


def _default_row_raw(U) -> dict:
    """Display-unit defaults for a newly added Tabulator row."""
    return {
        "type": "straight",
        "shape": "circular",
        "volume": U.fmt("duct_flow", DEFAULT_ROW_VOLUME_SI),
        "diameter": U.fmt("duct_dimension", DEFAULT_ROW_DIAMETER_SI),
        "width": U.fmt("duct_dimension", DEFAULT_ROW_WIDTH_SI),
        "height": U.fmt("duct_dimension", DEFAULT_ROW_HEIGHT_SI),
        "major": U.fmt("duct_dimension", DEFAULT_ROW_MAJOR_SI),
        "minor": U.fmt("duct_dimension", DEFAULT_ROW_MINOR_SI),
        "length": U.fmt("duct_run_length", DEFAULT_ROW_LENGTH_SI),
        "fitting": "",
        "label": DEFAULT_ROW_LABEL,
        "dp": U.fmt("velocity_pressure", DEFAULT_ROW_DP_SI),
    }


def _compute_leg_state(args, U):
    """Build the full index-leg state: every committed row (each isolated in
    its own try/except -- a bad row is flagged and excluded from the total
    without affecting any other row) plus a live staging-draft preview
    (also isolated -- a bad draft never touches the committed rows). Fully
    independent of `_compute_state()` / the top 3-column sizer -- see the
    module docstring's Correction #6.

    Also computes the safety margin (a user-entered % applied to the total
    pressure drop) and returns both the base total and the margin-adjusted
    total for display in the tfoot and in the PDF/CSV reports.
    """
    try:
        row_count = int(_s(args, "leg_row_count", "0") or "0")
    except (TypeError, ValueError):
        row_count = 0
    row_count = max(0, min(MAX_LEG_ROWS, row_count))

    rows = []
    total_pa = 0.0
    for i in range(row_count):
        get = _row_field_getter(args, i)
        raw = {field: get(field) for field in ROW_FIELDS}
        try:
            row = _compute_row(get, U)
            row["error"] = None
        except ValueError as exc:
            row = _blank_row(raw.get("type"), raw.get("shape"), raw.get("fitting"))
            row["error"] = str(exc)
        row["index"] = i
        row["raw"] = raw
        rows.append(row)
        total_pa += row["dp_pa"]

    stage_get = _row_field_getter(args, None)
    stage_raw = {field: stage_get(field) for field in ROW_FIELDS}
    try:
        stage = _compute_row(stage_get, U)
        stage_error = None
    except ValueError as exc:
        stage = None
        stage_error = str(exc)

    # Safety margin: a percentage the engineer applies to the calculated total
    # to allow for fitting inaccuracy, future extensions, etc.
    try:
        safety_margin = max(0.0, float(args.get("leg_safety_margin", "0") or "0"))
    except (TypeError, ValueError):
        safety_margin = 0.0
    margin_pa = total_pa * safety_margin / 100.0
    total_with_margin_pa = total_pa + margin_pa

    return {
        "row_count": row_count,
        "rows": rows,
        "total_display": U.fmt("velocity_pressure", total_pa),
        "total_sym": U.sym("velocity_pressure"),
        "safety_margin": safety_margin,
        "margin_amount_display": U.fmt("velocity_pressure", margin_pa),
        "total_with_margin_display": U.fmt("velocity_pressure", total_with_margin_pa),
        "shape_options": _row_shape_options(),
        "type_options": _row_type_options(),
        "fittings_by_shape": {
            s: _fitting_options(s) for s in ROW_SHAPE_LABELS
        },
        "stage": stage,
        "stage_raw": stage_raw,
        "stage_error": stage_error,
        "duct_dimension_sym": U.sym("duct_dimension"),
        "duct_flow_sym": U.sym("duct_flow"),
        "duct_run_length_sym": U.sym("duct_run_length"),
        "velocity_pressure_sym": U.sym("velocity_pressure"),
        "friction_rate_sym": U.sym("friction_rate"),
        "default_row_raw": _default_row_raw(U),
    }


def _leg_csv_rows(leg: dict):
    """(header, data_rows, footer_rows) for the CSV export -- kept separate
    from the route function so the row-building logic is easy to unit-test
    without going through Flask's request/response cycle.

    `footer_rows` is always a list (may contain 1 or 3 rows when a safety
    margin is set); the caller uses `writer.writerows(footer_rows)`.
    """
    header = [
        "#", "Type", "Shape", "Volume", "Size", "Velocity",
        "Velocity Pressure", "Friction Rate / K", "Length", "Pressure Drop",
    ]
    data_rows = []
    for row in leg["rows"]:
        data_rows.append([
            row["index"] + 1,
            row["type_label"],
            ROW_SHAPE_LABELS.get(row["shape"], ""),
            row["volume_display"],
            row["size_display"],
            row["velocity_display"],
            row["velocity_pressure_display"],
            row.get("friction_or_k_display") or row["friction_rate_display"],
            row["length_display"],
            row["dp_display"] + (f" ({row['error']})" if row.get("error") else ""),
        ])

    footer_rows = [["", "", "", "", "", "", "", "", "TOTAL", leg["total_display"]]]
    margin = leg.get("safety_margin", 0)
    if margin > 0 and leg.get("total_with_margin_display"):
        footer_rows.append(["", "", "", "", "", "", "", "", f"Margin (+{margin:.0f}%)", leg.get("margin_amount_display", "")])
        footer_rows.append(["", "", "", "", "", "", "", "", "TOTAL WITH MARGIN", leg["total_with_margin_display"]])

    return header, data_rows, footer_rows


# -- PDF report (mirrors the psychrometric tools' pattern, see
# blueprints/psychro.py and specs/SPEC-pdf-report.md) --------------------------------
#
# Duct Sizing has no chart to draw (there's no psychrometric process to plot).
# When index-leg rows exist the PDF is leg-table-first (Paul's request: "the
# table is what I wanted, not the duct sizer values") -- Inputs/Results for the
# 3-column sizer are omitted and only the leg table is included.  When no leg
# rows exist (3-column sizer only) the original Inputs + Results layout is used.
#
# Column widths (mm) for the 11-column Index Leg PDF table on A4
# (content width ≈ 178 mm, see app/reports/builder.py's _CONTENT_WIDTH).
# Proportioned so narrow fixed columns (#, Shape, Volume) don't waste space
# and wider columns (Item, Size, Pressure Drop) get room to breathe.
_LEG_PDF_COL_WIDTHS_MM = [5, 18, 26, 15, 14, 22, 15, 14, 14, 13, 22]  # sum = 178 mm

def _duct_input_rows(fields, U):
    basis_label = "Velocity" if fields["basis"] == "velocity" else "Friction Rate"
    target_unit = U.sym(fields["basis"])
    circular_mm = fields.get("circular_mm") or ""
    circular_desc = "Auto (calculated)" if not circular_mm else f"{circular_mm} {U.sym('duct_dimension')} (Lindab stock)"
    return [
        ("Air Volume", fields["volume"], duct_flow_symbol(fields.get("duct_flow_unit") or "m3s", U)),
        ("Sizing Basis", basis_label, ""),
        ("Target Value", fields["target_value"], target_unit),
        ("Circular Stock Size", circular_desc, ""),
        ("Rectangular Round to 25mm", "Yes" if fields.get("rect_round25") == "1" else "No", ""),
        ("Rectangular Width Lock", "Yes" if fields.get("rect_lock_width") == "1" else "No", ""),
        ("Rectangular Height Lock", "Yes" if fields.get("rect_lock_height") == "1" else "No", ""),
    ]


def _duct_result_rows(circular, rectangular, flat_oval, U):
    rows = [
        ("Circular — Diameter", circular["diameter"], U.sym("duct_dimension")),
        ("Circular — Velocity", circular["velocity"], U.sym("velocity")),
        ("Circular — Velocity Pressure", circular["velocity_pressure"], U.sym("velocity_pressure")),
        ("Circular — Friction Rate", circular["friction_rate"], U.sym("friction_rate")),
    ]
    if not circular["is_auto"] and circular["gauge_mm"] is not None:
        rows.append((
            "Circular — Gauge",
            f'{circular["gauge_mm"]} mm ({"standard stock" if circular["standard"] else "special order only"})',
            "",
        ))
    rows += [
        ("Rectangular — Width", rectangular["width"], U.sym("duct_dimension")),
        ("Rectangular — Height", rectangular["height"], U.sym("duct_dimension")),
        ("Rectangular — Aspect Ratio", rectangular["aspect_ratio"], ": 1"),
        ("Rectangular — Velocity", rectangular["velocity"], U.sym("velocity")),
        ("Rectangular — Velocity Pressure", rectangular["velocity_pressure"], U.sym("velocity_pressure")),
        ("Rectangular — Friction Rate", rectangular["friction_rate"], U.sym("friction_rate")),
        ("Rectangular — Equivalent Diameter", rectangular["equivalent_diameter"], U.sym("duct_dimension")),
        ("Flat Oval — Major Axis", flat_oval["major"], U.sym("duct_dimension")),
        ("Flat Oval — Minor Axis", flat_oval["minor"], U.sym("duct_dimension")),
        ("Flat Oval — Velocity", flat_oval["velocity"], U.sym("velocity")),
        ("Flat Oval — Velocity Pressure", flat_oval["velocity_pressure"], U.sym("velocity_pressure")),
        ("Flat Oval — Friction Rate", flat_oval["friction_rate"], U.sym("friction_rate")),
        ("Flat Oval — Equivalent Diameter", flat_oval["equivalent_diameter"], U.sym("duct_dimension")),
    ]
    return rows


def _leg_table_for_report(leg: dict):
    """(headers, rows, footer_count) for the Index Leg's `extra_tables` PDF section.

    One column beyond the CSV export (`_leg_csv_rows`): "Item", carrying
    `row["label"]` -- the one piece of information that actually identifies
    *which* fitting was used or what an accessory row's free-text description
    was (Type/Shape alone only say "Fitting"/"Rectangular" or "Accessory /
    Custom"/"—", which reads as anonymous once there's more than one fitting
    or accessory row in the leg). Plus footer rows (TOTAL, optional margin rows).

    Footer rows place their label in col 0 and the value in the last column
    (col n-1), with all intermediate columns empty. `_item_table`'s SPAN
    commands then merge cols 0..n-2 into a single right-aligned label cell,
    which is what prevents long labels like "TOTAL WITH MARGIN" from bleeding
    into the value cell. `footer_count` tells `_item_table` how many trailing
    rows to treat this way.
    """
    headers = [
        "#", "Type", "Item", "Shape", "Volume", "Size", "Velocity",
        "Vel. Pressure", "Friction / K", "Length", "Pressure Drop",
    ]
    n_cols = len(headers)  # 11
    rows = []
    for row in leg["rows"]:
        friction_or_k = row.get("friction_or_k_display") or row["friction_rate_display"]
        dp_cell = row["dp_display"] + (" (error)" if row.get("error") else "")
        rows.append([
            str(row["index"] + 1),
            row["type_label"],
            row["label"] or "—",
            ROW_SHAPE_LABELS.get(row["shape"], "") or "—",
            row["volume_display"] or "—",
            row["size_display"] or "—",
            row["velocity_display"],
            row["velocity_pressure_display"],
            friction_or_k,
            row["length_display"] or "—",
            dp_cell,
        ])
    # Footer rows: label in col 0, empty cols 1..n-2, value in col n-1.
    # _item_table will SPAN cols 0..n-2 into one right-aligned label cell.
    rows.append(["TOTAL"] + [""] * (n_cols - 2) + [f'{leg["total_display"]} {leg["total_sym"]}'])
    footer_count = 1
    margin = leg.get("safety_margin", 0)
    if margin > 0 and leg.get("total_with_margin_display"):
        rows.append([f"+ {margin:.0f}% margin"] + [""] * (n_cols - 2) + [leg.get("margin_amount_display", "")])
        rows.append(["TOTAL WITH MARGIN"] + [""] * (n_cols - 2) + [f'{leg["total_with_margin_display"]} {leg["total_sym"]}'])
        footer_count = 3
    return headers, rows, footer_count


def _report_fields_for_sizer(fields: dict) -> dict:
    """Hidden fields for the duct-sizer PDF report (no index-leg state)."""
    return dict(fields)


def _report_fields_for_leg(leg: dict) -> dict:
    """Hidden fields for the index-leg PDF report (no 3-column sizer state)."""
    out = {
        "leg_row_count": str(leg["row_count"]),
        "leg_safety_margin": str(leg.get("safety_margin", 0)),
    }
    for row in leg["rows"]:
        for f in ROW_FIELDS:
            out[f"leg_{f}_{row['index']}"] = row["raw"].get(f, "")
    return out


def _report_fields_for(fields: dict, leg: dict) -> dict:
    """Legacy combined flatten — prefer `_report_fields_for_sizer` /
    `_report_fields_for_leg` now that the modules are separate pages."""
    out = _report_fields_for_sizer(fields)
    out.update(_report_fields_for_leg(leg))
    return out


# -- routes -----------------------------------------------------------------------------

@bp.route("/", methods=["GET"])
@require_module("duct.sizer")
def index():
    from app.ui_prefs import redirect_to_v2

    return redirect_to_v2("v2.duct")


@bp.route("/index-leg/", methods=["GET"])
@require_module("duct.index_leg")
def index_leg():
    """Standalone Index Leg / duct system pressure-drop module."""
    from app.ui_prefs import redirect_to_v2

    return redirect_to_v2("v2.duct_index_leg")


@bp.route("/report", methods=["POST"])
@require_suite_access("duct.sizer")
def report():
    """Download PDF Report for the 3-column duct sizer only."""
    U = current_view()
    fields, circular, rectangular, flat_oval, error = _compute_state(request.form, U)
    if error:
        return Response(f"Cannot generate report: {error}", status=400)
    meta = report_meta_from_form("Air Distribution - Duct Sizing")
    input_rows = _duct_input_rows(fields, U)
    result_rows = _duct_result_rows(circular, rectangular, flat_oval, U)
    pdf = build_pdf(meta, input_rows=input_rows, result_rows=result_rows)
    return pdf_response(pdf, meta=meta, fallback="duct-sizing")


@bp.route("/index-leg/report", methods=["POST"])
@require_module("duct.index_leg")
def report_leg():
    """Download PDF Report for the Index Leg pressure-drop table."""
    U = current_view()
    leg = _compute_leg_state(request.form, U)
    if not leg["rows"]:
        return Response("Cannot generate report: add at least one index-leg row.", status=400)
    meta = report_meta_from_form("Air Distribution - Index Leg")
    headers, rows, footer_count = _leg_table_for_report(leg)
    pdf = build_pdf(
        meta,
        input_rows=None,
        result_rows=None,
        extra_tables=[("Index Leg — Pressure Drop", headers, rows, _LEG_PDF_COL_WIDTHS_MM, footer_count)],
    )
    return pdf_response(pdf, meta=meta, fallback="duct-index-leg")


@bp.route("/api/state", methods=["GET"])
@require_module("duct.sizer")
def api_state():
    """Top 3-column sizer JSON -- independent of the index leg (Correction
    #6): this response never carries leg data, and recomputing it never
    re-derives the leg."""
    U = current_view()
    fields, circular, rectangular, flat_oval, error = _compute_state(request.args, U)
    if request.args.get("intent") == "calculate" and not error:
        from app.analytics import note_calculator_complete

        note_calculator_complete("duct_sizing")
    return jsonify({
        "fields": fields,
        "circular": circular,
        "rectangular": rectangular,
        "flat_oval": flat_oval,
        "error": error,
    })


@bp.route("/api/leg-state", methods=["GET"])
@require_module("duct.index_leg")
def api_leg_state():
    """Index-leg JSON -- independent of the top sizer (Correction #6): this
    never touches or recomputes the 3-column state above it."""
    U = current_view()
    leg = _compute_leg_state(request.args, U)
    try:
        row_count = int(request.args.get("leg_row_count") or "0")
    except (TypeError, ValueError):
        row_count = 0
    if row_count > 0:
        from app.analytics import note_pro_tool_use

        note_pro_tool_use("duct_index_leg")
    return jsonify(leg)


@bp.route("/index-leg/export.csv", methods=["GET"])
@require_module("duct.index_leg")
def export_leg_csv():
    """Download the current index-leg table as CSV -- recomputes from the
    query string the same way the page/API routes do, so the export can
    never disagree with what's on screen."""
    U = current_view()
    leg = _compute_leg_state(request.args, U)
    header, data_rows, footer_rows = _leg_csv_rows(leg)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(data_rows)
    writer.writerows(footer_rows)

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=index-leg.csv"},
    )
