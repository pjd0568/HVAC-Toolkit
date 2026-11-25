"""Methodology & Limitations — user-facing standards basis and disclosed simplifications.

Static content sibling to Design Guides / Help. Summarises calculation basis,
climate data provenance, and planning-grade assumptions so a professional user
has a single honest answer without reading code comments.
"""

from flask import Blueprint, redirect, render_template, request

bp = Blueprint("methodology", __name__)


@bp.get("/")
def index():
    # Canonical path is /methodology/ (trailing slash). Bare /methodology 301s here.
    return render_template("methodology.html", active="methodology", nav="more")


@bp.before_app_request
def _canonicalize_methodology_slash():
    # Only the exact bare path — do not touch /methodology/foo.
    if request.path == "/methodology":
        return redirect("/methodology/", code=301)
