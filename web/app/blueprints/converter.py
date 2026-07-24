"""Unit Converter tool — one value in one unit, shown in every unit of a category.

Thin web layer over hvac_engine.converter. Server-rendered (consistent with the other
tools); the category and from-unit selects auto-submit so the unit list and results
refresh without a separate button press.
"""

from flask import Blueprint, render_template, request

from hvac_engine import converter as cv

from app.access_gate import require_module

bp = Blueprint("converter", __name__)

GROUP_LABELS = {
    "Metric": "Metric (SI)",
    "Imperial": "Imperial / US",
    "Other": "Other",
    "Common": "Common",
}


@bp.route("/", methods=["GET"])
@require_module("converter")
def index():
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
        grouped = [
            (g, GROUP_LABELS.get(g, g), [r for r in result.results if r.group == g])
            for g in cv.GROUP_ORDER
        ]
        grouped = [row for row in grouped if row[2]]

    # Units grouped for the from-unit <select> (optgroups).
    unit_groups = [
        (GROUP_LABELS.get(g, g), [u for u in category.units if u.group == g])
        for g in cv.GROUP_ORDER
    ]
    unit_groups = [ug for ug in unit_groups if ug[1]]

    return render_template(
        "converter.html", active="converter",
        categories=categories, category=category, unit_groups=unit_groups,
        from_unit=from_unit, value=value_raw, result=result, grouped=grouped,
        error=error,
    )
