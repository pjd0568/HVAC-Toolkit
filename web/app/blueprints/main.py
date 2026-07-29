from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app.teaser import P_ATM, resolve_teaser_state, teaser_payload
from app.units import set_unit_system

bp = Blueprint("main", __name__)


@bp.get("/")
def coming_soon():
    return render_template("marketing/coming_soon.html")


@bp.get("/app")
@login_required
def dashboard():
    return render_template("dashboard.html", active="dashboard")


@bp.post("/preferences/units")
@login_required
def set_units():
    """Flip the active unit system (SI/IP) and return to the page in use."""
    set_unit_system(request.form.get("system", ""))
    nxt = request.form.get("next", "")
    # Only honour same-app relative paths, never an absolute/off-site URL.
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = url_for("main.dashboard")
    return redirect(nxt)


@bp.post("/api/psychro/teaser")
def psychro_teaser_calculate():
    """Public single-point psychrometric calculate for the homepage teaser."""
    data = request.get_json(silent=True) or {}
    system = str(data.get("system") or "SI").upper()
    prop = str(data.get("prop") or "rh").lower()
    try:
        t_db = float(data["t_db"])
        val = float(data["val"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "t_db and val are required numbers"}), 400

    pressure = data.get("pressure", None)
    try:
        p_display = None if pressure in (None, "") else float(pressure)
        state, U = resolve_teaser_state(
            system=system, t_db=t_db, prop=prop, val=val, pressure=p_display
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    payload = teaser_payload(state, U, prop=prop, val=val)
    payload["ok"] = True
    payload["defaults"] = {
        "pressure_sea_level": {
            "SI": P_ATM,
            "IP": round(P_ATM / 3.386389, 3),
        }
    }
    return jsonify(payload)


@bp.get("/health")
def health():
    from app.mail import mail_backend

    # mail_backend is resend | smtp | none — no secrets, for deploy smoke checks.
    return {"status": "ok", "mail_backend": mail_backend()}
