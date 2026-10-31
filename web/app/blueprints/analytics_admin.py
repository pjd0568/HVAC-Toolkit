"""Owner-only product analytics. Hidden from subscribers."""

from __future__ import annotations

import hmac
import secrets
from datetime import date, timedelta

from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from app.analytics import is_analytics_owner
from app.analytics_channels import build_campaign_url
from app.analytics_report import (
    build_report,
    events_today_count,
    last_event_at,
    london_today,
    previous_complete_week,
    render_markdown,
    send_manual_report,
    send_weekly_analytics_report,
    weekly_job_health,
)

bp = Blueprint("analytics_admin", __name__, url_prefix="/admin/analytics")

_MAX_DAYS = 366


@bp.before_request
def _owner_only():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.path))
    if not is_analytics_owner():
        return render_template("analytics/forbidden.html"), 403
    return None


@bp.get("/", strict_slashes=False)
def dashboard():
    return _render_dashboard(preview=False)


@bp.get("/preview", strict_slashes=False)
def preview():
    return _render_dashboard(preview=True)


def _render_dashboard(*, preview: bool):
    if preview:
        start, end = previous_complete_week()
        days = None
    else:
        start, end, days = _selected_period()
    report = build_report(start, end)
    health = weekly_job_health()
    utm = _utm_link()
    return render_template(
        "analytics/dashboard.html",
        report=report,
        days=days,
        markdown=render_markdown(report),
        filename=_filename(start, end),
        csrf_token=_csrf_token(),
        events_today=events_today_count(),
        last_event_at=last_event_at(),
        health=health,
        chart=_chart(report),
        preview=preview,
        utm=utm,
        public_base=_public_base(),
    )


@bp.get("/report.md", strict_slashes=False)
def download():
    start, end, _days = _selected_period()
    body = render_markdown(build_report(start, end))
    response = Response(body, mimetype="text/markdown; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{_filename(start, end)}"'
    return response


@bp.post("/send")
def send():
    token = request.form.get("csrf_token") or ""
    expected = session.get("_analytics_csrf") or ""
    if not expected or not hmac.compare_digest(token, expected):
        flash("The report was not sent. Refresh the page and try again.", "error")
        return redirect(url_for("analytics_admin.dashboard"))
    start, end, days = _selected_period()
    ok, message = send_manual_report(start, end)
    flash(message if ok else message, "success" if ok else "error")
    return redirect(url_for("analytics_admin.dashboard", days=days, start=start.isoformat(), end=end.isoformat()))


@bp.post("/retry-weekly")
def retry_weekly():
    token = request.form.get("csrf_token") or ""
    expected = session.get("_analytics_csrf") or ""
    if not expected or not hmac.compare_digest(token, expected):
        flash("The weekly report was not sent. Refresh the page and try again.", "error")
        return redirect(url_for("analytics_admin.dashboard"))
    result = send_weekly_analytics_report()
    if result == "sent":
        flash("Weekly report sent.", "success")
    elif result == "already-sent":
        flash("That week was already sent.", "error")
    elif result == "disabled":
        flash("Weekly reports are disabled. Set ANALYTICS_WEEKLY_REPORT_ENABLED.", "error")
    elif result == "failed":
        flash("The weekly report email could not be sent. The week can be retried.", "error")
    else:
        flash("The weekly report did not send.", "error")
    return redirect(url_for("analytics_admin.dashboard"))


def _selected_period() -> tuple[date, date, int | None]:
    today = london_today()
    raw_days = request.values.get("days")
    raw_start = request.values.get("start")
    raw_end = request.values.get("end")
    if raw_start and raw_end:
        start = _parse_date(raw_start)
        end = _parse_date(raw_end)
        if start and end:
            if end < start:
                start, end = end, start
            if (end - start).days > _MAX_DAYS:
                start = end - timedelta(days=_MAX_DAYS)
            return start, end, None
    days = 30
    if raw_days in {"7", "30", "90"}:
        days = int(raw_days)
    # Presets end yesterday so a partial today is not compared with a full day.
    end = today - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return start, end, days


def _public_base() -> str:
    from flask import current_app

    return (current_app.config.get("PUBLIC_BASE_URL") or "https://hvac-calcs.app").rstrip("/")


def _utm_link() -> dict[str, str]:
    source = (request.values.get("utm_source") or "").strip().lower()
    medium = (request.values.get("utm_medium") or "").strip().lower()
    campaign = (request.values.get("utm_campaign") or "").strip().lower()
    content = (request.values.get("utm_content") or "").strip().lower()
    if not any((source, medium, campaign, content)):
        return {"source": "", "medium": "", "campaign": "", "content": "", "url": "", "error": ""}
    url = build_campaign_url(
        _public_base() + "/",
        source=source,
        medium=medium,
        campaign=campaign,
        content=content,
    )
    error = "" if url else "Use lowercase letters, numbers and underscores in every field."
    return {
        "source": source,
        "medium": medium,
        "campaign": campaign,
        "content": content,
        "url": url or "",
        "error": error,
    }


def _parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _filename(start: date, end: date) -> str:
    return f"hvac-calcs-analytics-{start.isoformat()}_to_{end.isoformat()}.md"


def _csrf_token() -> str:
    token = session.get("_analytics_csrf")
    if not isinstance(token, str) or len(token) < 16:
        token = secrets.token_urlsafe(32)
        session["_analytics_csrf"] = token
    return token


def _chart(report) -> dict:
    peak = 1
    for point in report.days:
        peak = max(peak, point.completions, point.registrations, point.pro_uses, point.subscriptions)
    width = 640
    height = 160
    step = width / max(len(report.days) - 1, 1)

    def series(attr: str) -> str:
        coords = []
        for index, point in enumerate(report.days):
            x = round(index * step, 1)
            y = round(height - (getattr(point, attr) / peak) * (height - 8) - 4, 1)
            coords.append(f"{x},{y}")
        return " ".join(coords)

    return {
        "width": width,
        "height": height,
        "completions": series("completions"),
        "registrations": series("registrations"),
        "pro_uses": series("pro_uses"),
        "subscriptions": series("subscriptions"),
    }
