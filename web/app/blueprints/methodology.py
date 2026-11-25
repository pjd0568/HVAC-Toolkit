"""Methodology & Limitations — user-facing standards basis and disclosed simplifications.

Static content sibling to Design Guides / Help. Summarises calculation basis,
climate data provenance, and planning-grade assumptions so a professional user
has a single honest answer without reading code comments.
"""

from flask import Blueprint, redirect, render_template, url_for

bp = Blueprint("methodology", __name__)


@bp.get("/", strict_slashes=False)
def index():
    # Canonical path keeps the trailing slash so sitemap /methodology/ is a 200.
    return render_template("methodology.html", active="methodology", nav="more")
