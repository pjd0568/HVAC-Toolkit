"""Unit Converter tool — one value in one unit, shown in every unit of a category.

Thin web layer over hvac_engine.converter. Page UI lives under ``/v2/converter``;
this blueprint keeps the classic URL as a redirect and shares engine helpers.
"""

from flask import Blueprint

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
    from app.ui_prefs import redirect_to_v2

    return redirect_to_v2("v2.converter")
