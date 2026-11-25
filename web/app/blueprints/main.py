from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app.teaser import P_ATM, resolve_teaser_state, teaser_payload
from app.unit_switch import rewrite_next_url
from app.units import get_unit_system, set_flow_unit, set_unit_system

bp = Blueprint("main", __name__)


def _safe_redirect_target(raw: str) -> str:
    """Only honour same-app relative paths, never an absolute/off-site URL."""
    if not raw.startswith("/") or raw.startswith("//"):
        return url_for("main.dashboard")
    # Flask's request.full_path always appends '?'; strip a trailing empty query.
    if raw.endswith("?"):
        raw = raw[:-1]
    return raw or url_for("main.dashboard")


@bp.get("/")
def coming_soon():
    return render_template("marketing/coming_soon.html")


@bp.get("/app")
@login_required
def dashboard():
    return redirect(url_for("v2.dashboard"))


@bp.post("/preferences/units")
def set_units():
    """Flip the active unit system (SI/IP) and return to the page in use.

    GET-driven calculators keep inputs in the query string. Convert those
    display values from the previous system into the new one so labels and
    numbers stay consistent (50 kW becomes ~170607 Btu/h, not 50 Btu/h).
    """
    previous = get_unit_system()
    requested = request.form.get("system", "")
    set_unit_system(requested)
    nxt = _safe_redirect_target(request.form.get("next", ""))
    nxt = rewrite_next_url(nxt, from_system=previous, to_system=get_unit_system())
    return redirect(nxt)


@bp.post("/preferences/flow-unit")
def set_flow_unit_pref():
    """Flip the airflow display unit (m³/h vs m³/s) and return to the page in use."""
    set_flow_unit(request.form.get("unit", ""))
    return redirect(_safe_redirect_target(request.form.get("next", "")))


@bp.post("/preferences/dismiss-stage-cta")
def dismiss_stage_cta():
    """Dismiss the Free→Pro stage CTA for one free tool for the rest of the session."""
    from app.stage_cta import dismiss_stage_cta as dismiss

    dismiss(request.form.get("tool", ""))
    return redirect(_safe_redirect_target(request.form.get("next", "")))


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
    from app.analytics import note_calculator_complete

    note_calculator_complete("psychrometric_single")
    payload["defaults"] = {
        "pressure_sea_level": {
            "SI": P_ATM,
            "IP": round(P_ATM / 3.386389, 3),
        }
    }
    return jsonify(payload)


@bp.post("/e")
def track_event():
    """First-party product event. Drops unknown names and any calculation inputs."""
    from app.analytics import record_client_event

    data = request.get_json(silent=True) or {}
    event = data.get("event") if isinstance(data, dict) else None
    props = data.get("props") if isinstance(data, dict) else None
    record_client_event(event, props)
    return "", 204


@bp.get("/health")
def health():
    from app.mail import mail_backend

    # mail_backend is resend | smtp | none — no secrets, for deploy smoke checks.
    return {"status": "ok", "mail_backend": mail_backend()}
