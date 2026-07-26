"""Methodology & Limitations — user-facing standards basis and disclosed simplifications.

Static content sibling to Design Guides / Help. Summarises calculation basis,
climate data provenance, and planning-grade assumptions so a professional user
has a single honest answer without reading code comments.
"""

from flask import Blueprint, render_template

bp = Blueprint("methodology", __name__)


@bp.get("/")
def index():
    return render_template("methodology.html", active="methodology")
