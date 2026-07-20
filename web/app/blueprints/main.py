from flask import Blueprint, redirect, render_template, request, url_for

from app.units import set_unit_system

bp = Blueprint("main", __name__)


@bp.get("/")
def dashboard():
    return render_template("dashboard.html", active="dashboard")


@bp.post("/preferences/units")
def set_units():
    """Flip the active unit system (SI/IP) and return to the page in use.

    Session-backed today; when auth lands this also writes the user's saved
    preference so it follows them across devices.
    """
    set_unit_system(request.form.get("system", ""))
    nxt = request.form.get("next", "")
    # Only honour same-app relative paths, never an absolute/off-site URL.
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = url_for("main.dashboard")
    return redirect(nxt)


@bp.get("/health")
def health():
    return {"status": "ok"}
