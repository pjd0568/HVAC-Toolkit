from __future__ import annotations

from datetime import date

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import User
from app.turnstile import turnstile_configured, turnstile_site_key, verify_turnstile_response

bp = Blueprint("auth", __name__)


def _register_template(**extra):
    return render_template(
        "auth/register.html",
        turnstile_site_key=turnstile_site_key() if turnstile_configured() else "",
        **extra,
    )


def _registration_open() -> bool:
    return bool(current_app.config.get("REGISTRATION_OPEN"))


def _safe_next(raw: str | None) -> str:
    """Only honour same-app relative paths."""
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return url_for("v2.dashboard")
    return raw


@bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("v2.dashboard"))
    # Local preview helper — only when ACCESS_DEV_TIER is set (never in prod).
    if current_app.config.get("ACCESS_DEV_TIER") and request.args.get("preview") == "1":
        from datetime import date

        from app.extensions import db
        from app.models import User

        email = "preview@example.com"
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(
                email=email,
                trial_started_at=date.today(),
                subscription_status="active",
            )
            user.set_password("preview")
            db.session.add(user)
            db.session.commit()
        login_user(user, remember=True)
        from app.ui_prefs import redirect_with_ui

        return redirect_with_ui("v2", url_for("v2.dashboard"))
    return render_template(
        "auth/login.html",
        next=request.args.get("next", ""),
    )


@bp.post("/login")
def login_post():
    email = User.normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    nxt = _safe_next(request.form.get("next"))

    user = User.query.filter_by(email=email).first() if email else None
    if user is None or not user.check_password(password):
        flash("Invalid email or password.", "error")
        return render_template("auth/login.html", next=request.form.get("next", "")), 401

    login_user(user, remember=bool(request.form.get("remember")))
    return redirect(nxt)


@bp.get("/register")
def register():
    if not _registration_open():
        flash("Registration is closed while we prepare the launch.", "info")
        return redirect(url_for("main.coming_soon"))
    if current_user.is_authenticated:
        return redirect(url_for("v2.dashboard"))
    return _register_template()


@bp.post("/register")
def register_post():
    if not _registration_open():
        flash("Registration is closed while we prepare the launch.", "info")
        return redirect(url_for("main.coming_soon"))

    email = User.normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    password2 = request.form.get("password2", "")

    errors: list[str] = []
    if turnstile_configured() and not verify_turnstile_response(
        request.form.get("cf-turnstile-response")
    ):
        errors.append("Please complete the human check and try again.")
    if not email or "@" not in email:
        errors.append("Enter a valid email address.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if password != password2:
        errors.append("Passwords do not match.")
    if email and User.query.filter_by(email=email).first():
        errors.append("An account with that email already exists.")

    if errors:
        for msg in errors:
            flash(msg, "error")
        return _register_template(), 400

    user = User(
        email=email,
        trial_started_at=date.today(),
        subscription_status="trialing",
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user)

    from app.lifecycle_mail import send_trial_started

    send_trial_started(user)

    flash("Account created. Your 14-day free trial has started.", "success")
    # Land on Single Point so the homepage teaser can hand off after signup.
    return redirect(url_for("v2.single_point", from_teaser=1))


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("Signed out.", "info")
    return redirect(url_for("main.coming_soon"))
