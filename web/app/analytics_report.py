"""Aggregated product-analytics reports. No identities and no calculation values."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.analytics import FREE_TOOLS, PRO_TOOLS, TOOLS
from app.extensions import db
from app.models.analytics import AnalyticsEvent, AnalyticsReportRun

logger = logging.getLogger(__name__)

LONDON = ZoneInfo("Europe/London")

# A crashed worker can leave a weekly row in "sending". Thirty minutes is
# longer than a report email and short enough that a later run the same
# morning can retry. A claim newer than this stays exclusive so a second
# process does not send a duplicate.
STALE_SENDING_TIMEOUT = timedelta(minutes=30)

AI_PROMPT = (
    "Analyse this HVAC-CALCS weekly report. Identify the strongest and weakest "
    "parts of the funnel, what content appears to be generating useful product "
    "engagement, and recommend the three highest-priority development or "
    "marketing actions for next week."
)


@dataclass
class ToolRow:
    tool: str
    starts: int = 0
    completions: int = 0
    pro_clicks: int = 0
    registrations: int = 0

    @property
    def completion_rate(self) -> str:
        if self.starts <= 0:
            return "—"
        return f"{round(100 * self.completions / self.starts)}%"


@dataclass
class PathRow:
    source: str
    target: str
    views: int = 0
    clicks: int = 0
    registrations: int = 0
    pro_uses: int = 0
    paid: int = 0


@dataclass
class CampaignRow:
    campaign: str
    source: str
    calculations: int = 0
    pro_clicks: int = 0
    registrations: int = 0
    pro_uses: int = 0
    paid: int = 0


@dataclass
class DayPoint:
    day: date
    completions: int = 0
    registrations: int = 0
    pro_uses: int = 0
    subscriptions: int = 0


@dataclass
class Report:
    start: date
    end: date
    completions: int = 0
    unique_free_journeys: int = 0
    cta_views: int = 0
    cta_clicks: int = 0
    unique_cta_clicks: int = 0
    registrations: int = 0
    pro_uses: int = 0
    unique_pro_uses: int = 0
    checkouts: int = 0
    unique_checkouts: int = 0
    subscriptions: int = 0
    calc_to_cta: str | None = None
    cta_to_registration: str | None = None
    registration_to_pro: str | None = None
    pro_to_checkout: str | None = None
    checkout_to_paid: str | None = None
    calc_to_paid: str | None = None
    previous_start: date | None = None
    previous_end: date | None = None
    deltas: dict[str, str] = field(default_factory=dict)
    calculators: list[ToolRow] = field(default_factory=list)
    paths: list[PathRow] = field(default_factory=list)
    pro_tools: list[tuple[str, int]] = field(default_factory=list)
    campaigns: list[CampaignRow] = field(default_factory=list)
    units: dict[str, int] = field(default_factory=lambda: {"SI": 0, "IP": 0})
    days: list[DayPoint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def london_today(now: datetime | None = None) -> date:
    return _as_london(now).date()


def previous_complete_week(now: datetime | None = None) -> tuple[date, date]:
    """Monday–Sunday immediately before the week that contains ``now`` in London."""
    today = london_today(now)
    this_monday = today - timedelta(days=today.weekday())
    end = this_monday - timedelta(days=1)
    start = end - timedelta(days=6)
    return start, end


def period_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Inclusive London dates as a half-open UTC interval."""
    start_dt = datetime.combine(start, time.min, tzinfo=LONDON).astimezone(timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=LONDON).astimezone(timezone.utc)
    return start_dt, end_dt


def build_report(start: date, end: date) -> Report:
    if end < start:
        start, end = end, start
    report = Report(start=start, end=end)
    start_dt, end_dt = period_bounds(start, end)
    rows = (
        AnalyticsEvent.query.filter(
            AnalyticsEvent.occurred_at >= start_dt,
            AnalyticsEvent.occurred_at < end_dt,
        )
        .order_by(AnalyticsEvent.occurred_at.asc())
        .all()
    )
    _fill(report, rows)
    length = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)
    report.previous_start = prev_start
    report.previous_end = prev_end
    prev_rows = AnalyticsEvent.query.filter(
        AnalyticsEvent.occurred_at >= period_bounds(prev_start, prev_end)[0],
        AnalyticsEvent.occurred_at < period_bounds(prev_start, prev_end)[1],
    ).all()
    previous = Report(start=prev_start, end=prev_end)
    _fill(previous, prev_rows)
    report.deltas = {
        "calculations": _delta(report.completions, previous.completions),
        "pro_clicks": _delta(report.cta_clicks, previous.cta_clicks),
        "registrations": _delta(report.registrations, previous.registrations),
        "pro_uses": _delta(report.pro_uses, previous.pro_uses),
        "checkout": _delta(report.checkouts, previous.checkouts),
        "paid": _delta(report.subscriptions, previous.subscriptions),
    }
    report.notes = _notes()
    return report


def render_markdown(report: Report) -> str:
    lines = [
        "# HVAC-CALCS Product Analytics",
        "",
        "## Period",
        f"Start: {report.start.isoformat()}",
        f"End: {report.end.isoformat()}",
        "",
        "## Funnel",
        f"Free calculator completions: {report.completions}",
        f"Unique free-calculation journeys: {report.unique_free_journeys}",
        f"Pro CTA views: {report.cta_views}",
        f"Pro CTA clicks: {report.cta_clicks}",
        f"Registrations: {report.registrations}",
        f"Pro tool activations: {report.pro_uses}",
        f"Checkout starts: {report.checkouts}",
        f"Subscriptions: {report.subscriptions}",
        "",
        "## Conversion",
        f"Calculation → Pro CTA: {_pct(report.calc_to_cta)}",
        f"Pro CTA → Registration: {_pct(report.cta_to_registration)}",
        f"Registration → Pro use: {_pct(report.registration_to_pro)}",
        f"Pro use → Checkout: {_pct(report.pro_to_checkout)}",
        f"Checkout → Paid: {_pct(report.checkout_to_paid)}",
        f"Overall calculation → Paid: {_pct(report.calc_to_paid)}",
        "",
        "## Week-on-week / Previous period",
        f"Previous period: {report.previous_start} to {report.previous_end}",
        f"Calculations: {report.deltas.get('calculations', '—')}",
        f"Pro clicks: {report.deltas.get('pro_clicks', '—')}",
        f"Registrations: {report.deltas.get('registrations', '—')}",
        f"Pro uses: {report.deltas.get('pro_uses', '—')}",
        f"Checkout: {report.deltas.get('checkout', '—')}",
        f"Paid: {report.deltas.get('paid', '—')}",
        "",
        "## Free calculator performance",
        "Calculator | Starts | Completions | Completion rate | Pro clicks | Registrations",
    ]
    if report.calculators:
        for row in report.calculators:
            lines.append(
                f"{row.tool} | {row.starts} | {row.completions} | {row.completion_rate} | "
                f"{row.pro_clicks} | {row.registrations}"
            )
    else:
        lines.append("No free-calculator events in this period.")
    lines.extend([
        "",
        "## Free to Pro journeys",
        "Free calculator | Target Pro tool | CTA views | CTA clicks | Registrations | Pro uses | Paid",
    ])
    if report.paths:
        for row in report.paths:
            lines.append(
                f"{row.source} | {row.target} | {row.views} | {row.clicks} | "
                f"{row.registrations} | {row.pro_uses} | {row.paid}"
            )
    else:
        lines.append("No free-to-Pro paths in this period.")
    lines.extend(["", "## Pro tool usage", "Pro tool | Successful uses"])
    if report.pro_tools:
        for name, count in report.pro_tools:
            lines.append(f"{name} | {count}")
    else:
        lines.append("No successful Pro-tool uses in this period.")
    lines.extend([
        "",
        "## Campaign performance",
        "Campaign | Source | Calculations | Pro clicks | Registrations | Pro uses | Paid",
    ])
    if report.campaigns:
        for row in report.campaigns:
            lines.append(
                f"{row.campaign} | {row.source} | {row.calculations} | {row.pro_clicks} | "
                f"{row.registrations} | {row.pro_uses} | {row.paid}"
            )
    else:
        lines.append("No campaign-attributed events in this period.")
    lines.extend([
        "",
        "## Unit-system usage",
        f"SI: {report.units.get('SI', 0)}",
        f"Imperial: {report.units.get('IP', 0)}",
        "",
        "## Data-quality notes",
    ])
    lines.extend(f"- {note}" for note in report.notes)
    lines.append("")
    return "\n".join(lines)


def render_email_text(report: Report) -> str:
    observations = _observations(report)
    obs = "\n".join(f"- {line}" for line in observations) or "- No product events in this period."
    markdown = render_markdown(report)
    return "\n".join([
        "HVAC-CALCS Weekly Product Report",
        "",
        "PERIOD",
        f"{report.start.isoformat()} to {report.end.isoformat()}",
        "",
        "FUNNEL",
        f"Free calculations completed       {report.completions}",
        f"Unique free journeys              {report.unique_free_journeys}",
        f"Pro CTA clicks                    {report.cta_clicks}",
        f"Registrations                     {report.registrations}",
        f"Pro tools used                    {report.pro_uses}",
        f"Checkout starts                   {report.checkouts}",
        f"New subscriptions                 {report.subscriptions}",
        "",
        "PREVIOUS-PERIOD COMPARISON",
        f"Calculations        {report.deltas.get('calculations', '—')}",
        f"Pro clicks          {report.deltas.get('pro_clicks', '—')}",
        f"Registrations       {report.deltas.get('registrations', '—')}",
        f"Pro usage           {report.deltas.get('pro_uses', '—')}",
        f"Checkout            {report.deltas.get('checkout', '—')}",
        f"Subscriptions       {report.deltas.get('paid', '—')}",
        "",
        "TOP FREE CALCULATORS",
        *_top_lines([f"{row.tool} — {row.completions} completions" for row in report.calculators]),
        "",
        "TOP PRO TOOLS",
        *_top_lines([f"{name} — {count} uses" for name, count in report.pro_tools]),
        "",
        "TOP FREE → PRO PATHS",
        *_top_lines([
            f"{row.source} → {row.target} — {row.clicks} clicks, {row.registrations} registrations"
            for row in report.paths
        ]),
        "",
        "CAMPAIGN PERFORMANCE",
        *_top_lines([
            f"{row.campaign} ({row.source}) — {row.calculations} calculations, "
            f"{row.registrations} registrations"
            for row in report.campaigns
        ]),
        "",
        "FACTUAL OBSERVATIONS",
        obs,
        "",
        "AI ANALYSIS",
        "Copy the Markdown report below into Microsoft Copilot and ask:",
        AI_PROMPT,
        "",
        markdown,
    ])


def render_email_html(report: Report) -> str:
    """Short HTML summary. The plain-text part carries the full Markdown."""
    def cell(label: str, value: int) -> str:
        return f"<tr><td>{label}</td><td style=\"text-align:right\">{value}</td></tr>"

    rows = "".join([
        cell("Free calculations completed", report.completions),
        cell("Unique free journeys", report.unique_free_journeys),
        cell("Pro CTA clicks", report.cta_clicks),
        cell("Registrations", report.registrations),
        cell("Pro tools used", report.pro_uses),
        cell("Checkout starts", report.checkouts),
        cell("New subscriptions", report.subscriptions),
    ])
    return (
        "<div style=\"font-family:Georgia,serif;color:#0E1116\">"
        "<h1 style=\"font-size:20px\">HVAC-CALCS Weekly Product Report</h1>"
        f"<p>{report.start.isoformat()} to {report.end.isoformat()}</p>"
        f"<table style=\"border-collapse:collapse\">{rows}</table>"
        "<p>The plain-text part of this message includes the full Markdown report "
        "for Microsoft Copilot.</p>"
        "</div>"
    )


def send_analytics_report(report: Report, *, kind: str) -> tuple[bool, str]:
    """Send one report to ANALYTICS_REPORT_EMAIL. Returns (ok, message)."""
    from app.mail import mail_configured, send_email

    recipient = (current_app.config.get("ANALYTICS_REPORT_EMAIL") or "").strip()
    if not recipient or "@" not in recipient:
        return False, "Report email is not configured."
    if not mail_configured():
        return False, "Email is not configured."
    subject = f"HVAC-CALCS Weekly Report | {report.start.isoformat()} - {report.end.isoformat()}"
    ok = send_email(
        to=recipient,
        subject=subject,
        body=render_email_text(report),
        html=render_email_html(report),
    )
    if not ok:
        logger.error("analytics report send failed kind=%s", kind)
        return False, "The report email could not be sent."
    return True, "Report sent."


def send_manual_report(start: date, end: date) -> tuple[bool, str]:
    report = build_report(start, end)
    ok, message = send_analytics_report(report, kind="manual")
    _save_run(start, end, kind="manual", status="sent" if ok else "failed", detail=message, weekly_key=None)
    return ok, message


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _sending_is_stale(run: AnalyticsReportRun, moment: datetime) -> bool:
    claimed = run.created_at
    if claimed is None:
        return True
    return _as_utc(moment) - _as_utc(claimed) >= STALE_SENDING_TIMEOUT


def _release_stale_send(run_id: int, key: str) -> bool:
    """Drop one stale sending claim. A concurrent recovery updates zero rows."""
    released = AnalyticsReportRun.query.filter_by(
        id=run_id,
        weekly_key=key,
        status="sending",
    ).update(
        {
            "status": "failed",
            "weekly_key": None,
            "detail": "stale sending released for retry",
        },
        synchronize_session=False,
    )
    db.session.commit()
    db.session.expire_all()
    return released == 1


def send_weekly_analytics_report(now: datetime | None = None) -> str:
    """Send the previous London week once.

    ``weekly_key`` is the period start date. A successful send keeps that
    key and is never sent again. A failed email clears the key so the next
    run can retry. A ``sending`` row younger than ``STALE_SENDING_TIMEOUT``
    blocks a concurrent run. An older ``sending`` row is released once, then
    one new claim may send.
    """
    if not current_app.config.get("ANALYTICS_WEEKLY_REPORT_ENABLED"):
        return "disabled"
    moment = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    start, end = previous_complete_week(now)
    key = start.isoformat()
    existing = AnalyticsReportRun.query.filter_by(weekly_key=key).first()
    if existing is not None:
        if existing.status == "sent" or not _sending_is_stale(existing, moment):
            return "already-sent"
        if not _release_stale_send(existing.id, key):
            return "already-sent"
    run = AnalyticsReportRun(
        period_start=start,
        period_end=end,
        kind="weekly",
        status="sending",
        weekly_key=key,
    )
    try:
        db.session.add(run)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return "already-sent"
    report = build_report(start, end)
    ok, message = send_analytics_report(report, kind="weekly")
    fields = {
        "status": "sent" if ok else "failed",
        "detail": (message or "")[:200],
        "sent_at": datetime.now(timezone.utc) if ok else None,
    }
    if not ok:
        fields["weekly_key"] = None
    owned = AnalyticsReportRun.query.filter_by(
        id=run.id,
        weekly_key=key,
        status="sending",
    ).update(fields, synchronize_session=False)
    db.session.commit()
    if not owned:
        return "lost-claim"
    return "sent" if ok else "failed"


def prune_analytics_events(now: datetime | None = None) -> int:
    """Delete analytics events older than ANALYTICS_RETENTION_DAYS. Not accounts or billing."""
    days = int(current_app.config.get("ANALYTICS_RETENTION_DAYS") or 365)
    if days < 1:
        return 0
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    cutoff = moment - timedelta(days=days)
    deleted = AnalyticsEvent.query.filter(AnalyticsEvent.occurred_at < cutoff).delete(
        synchronize_session=False
    )
    db.session.commit()
    return int(deleted or 0)


def latest_weekly_run() -> AnalyticsReportRun | None:
    return (
        AnalyticsReportRun.query.filter_by(kind="weekly")
        .order_by(AnalyticsReportRun.created_at.desc())
        .first()
    )


def events_today_count(now: datetime | None = None) -> int:
    today = london_today(now)
    start_dt, end_dt = period_bounds(today, today)
    return AnalyticsEvent.query.filter(
        AnalyticsEvent.occurred_at >= start_dt,
        AnalyticsEvent.occurred_at < end_dt,
    ).count()


def last_event_at() -> datetime | None:
    row = AnalyticsEvent.query.order_by(AnalyticsEvent.occurred_at.desc()).first()
    return row.occurred_at if row else None


def _fill(report: Report, rows: list[AnalyticsEvent]) -> None:
    free_actors: set[str] = set()
    cta_actors: set[str] = set()
    pro_actors: set[str] = set()
    checkout_actors: set[str] = set()
    paid_actors: set[str] = set()
    registered_users: set[int] = set()
    pro_users: set[int] = set()
    actors_by_stage: dict[str, set[str]] = {
        "complete": set(),
        "click": set(),
        "register": set(),
        "pro": set(),
        "checkout": set(),
        "paid": set(),
    }
    calc_rows: dict[str, ToolRow] = {name: ToolRow(tool=name) for name in sorted(FREE_TOOLS)}
    path_rows: dict[tuple[str, str], PathRow] = {}
    pro_counts: dict[str, int] = {}
    campaigns: dict[tuple[str, str], CampaignRow] = {}
    by_day: dict[date, DayPoint] = {}
    actor_paths: dict[str, set[tuple[str, str]]] = {}
    actor_pro_tools: dict[str, set[str]] = {}

    for row in rows:
        actor = _actor(row)
        day = _event_day(row.occurred_at)
        point = by_day.setdefault(day, DayPoint(day=day))
        name = row.event_name
        if name == "calculator_complete" and row.tool in FREE_TOOLS:
            report.completions += 1
            point.completions += 1
            if actor:
                free_actors.add(actor)
                actors_by_stage["complete"].add(actor)
            calc_rows[row.tool].completions += 1
            if row.unit_system in {"SI", "IP"}:
                report.units[row.unit_system] += 1
            _campaign(campaigns, row).calculations += 1
        elif name == "calculator_start" and row.tool in FREE_TOOLS:
            calc_rows[row.tool].starts += 1
        elif name == "pro_cta_view":
            report.cta_views += 1
            path = _path(path_rows, row.source, row.target)
            if path:
                path.views += 1
        elif name == "pro_cta_click":
            report.cta_clicks += 1
            if actor:
                cta_actors.add(actor)
                actors_by_stage["click"].add(actor)
                if row.source in FREE_TOOLS and row.target in PRO_TOOLS:
                    actor_paths.setdefault(actor, set()).add((row.source, row.target))
            if row.source in FREE_TOOLS:
                calc_rows[row.source].pro_clicks += 1
            path = _path(path_rows, row.source, row.target)
            if path:
                path.clicks += 1
            _campaign(campaigns, row).pro_clicks += 1
        elif name == "registration_complete":
            report.registrations += 1
            point.registrations += 1
            if actor:
                actors_by_stage["register"].add(actor)
            if row.user_id:
                registered_users.add(row.user_id)
            if row.source in FREE_TOOLS:
                calc_rows[row.source].registrations += 1
            path = _path(path_rows, row.source, row.target)
            if path:
                path.registrations += 1
            _campaign(campaigns, row).registrations += 1
        elif name == "pro_tool_use" and row.tool in PRO_TOOLS:
            report.pro_uses += 1
            point.pro_uses += 1
            pro_counts[row.tool] = pro_counts.get(row.tool, 0) + 1
            if actor:
                pro_actors.add(actor)
                actors_by_stage["pro"].add(actor)
                if row.tool:
                    actor_pro_tools.setdefault(actor, set()).add(row.tool)
            if row.user_id:
                pro_users.add(row.user_id)
            _campaign(campaigns, row).pro_uses += 1
        elif name == "checkout_start":
            report.checkouts += 1
            if actor:
                checkout_actors.add(actor)
                actors_by_stage["checkout"].add(actor)
        elif name == "subscription_active":
            report.subscriptions += 1
            point.subscriptions += 1
            if actor:
                paid_actors.add(actor)
                actors_by_stage["paid"].add(actor)
            _campaign(campaigns, row).paid += 1

    report.unique_free_journeys = len(free_actors)
    report.unique_cta_clicks = len(cta_actors)
    report.unique_pro_uses = len(pro_actors)
    report.unique_checkouts = len(checkout_actors)
    report.calc_to_cta = _rate(actors_by_stage["complete"] & actors_by_stage["click"], actors_by_stage["complete"])
    report.cta_to_registration = _rate(
        actors_by_stage["click"] & actors_by_stage["register"],
        actors_by_stage["click"],
    )
    report.registration_to_pro = _rate(registered_users & pro_users, registered_users)
    report.pro_to_checkout = _rate(actors_by_stage["pro"] & actors_by_stage["checkout"], actors_by_stage["pro"])
    report.checkout_to_paid = _rate(actors_by_stage["checkout"] & actors_by_stage["paid"], actors_by_stage["checkout"])
    report.calc_to_paid = _rate(actors_by_stage["complete"] & actors_by_stage["paid"], actors_by_stage["complete"])

    for actor, pairs in actor_paths.items():
        if actor not in actors_by_stage["pro"] and actor not in actors_by_stage["paid"]:
            continue
        for source, target in pairs:
            path = path_rows.get((source, target))
            if path is None:
                continue
            if target in actor_pro_tools.get(actor, set()):
                path.pro_uses += 1
            if actor in actors_by_stage["paid"]:
                path.paid += 1

    report.calculators = sorted(
        [row for row in calc_rows.values() if row.starts or row.completions or row.pro_clicks or row.registrations],
        key=lambda row: (-row.completions, -row.starts, row.tool),
    )
    report.paths = sorted(
        path_rows.values(),
        key=lambda row: (-row.clicks, -row.registrations, row.source, row.target),
    )
    report.pro_tools = sorted(pro_counts.items(), key=lambda item: (-item[1], item[0]))
    report.campaigns = sorted(
        campaigns.values(),
        key=lambda row: (-row.calculations, -row.registrations, row.campaign),
    )
    cursor = report.start
    days: list[DayPoint] = []
    while cursor <= report.end:
        days.append(by_day.get(cursor, DayPoint(day=cursor)))
        cursor += timedelta(days=1)
    report.days = days


def _actor(row: AnalyticsEvent) -> str | None:
    if row.anonymous_session_id:
        return f"s:{row.anonymous_session_id}"
    if row.user_id:
        return f"u:{row.user_id}"
    return None


def _event_day(occurred_at: datetime) -> date:
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return occurred_at.astimezone(LONDON).date()


def _path(bucket: dict[tuple[str, str], PathRow], source: str | None, target: str | None) -> PathRow | None:
    if source not in FREE_TOOLS or target not in PRO_TOOLS:
        return None
    key = (source, target)
    row = bucket.get(key)
    if row is None:
        row = PathRow(source=source, target=target)
        bucket[key] = row
    return row


def _campaign(bucket: dict[tuple[str, str], CampaignRow], event: AnalyticsEvent) -> CampaignRow:
    campaign = event.utm_campaign or "unknown"
    source = event.utm_source or "unknown"
    key = (campaign, source)
    row = bucket.get(key)
    if row is None:
        row = CampaignRow(campaign=campaign, source=source)
        bucket[key] = row
    return row


def _rate(numerator: set, denominator: set) -> str | None:
    if not denominator:
        return None
    return f"{round(100 * len(numerator) / len(denominator))}%"


def _delta(current: int, previous: int) -> str:
    if previous <= 0:
        if current == 0:
            return "0"
        return "No comparable baseline"
    change = round(100 * (current - previous) / previous)
    sign = "+" if change > 0 else ""
    return f"{sign}{change}%"


def _pct(value: str | None) -> str:
    return value if value else "not calculated"


def _notes() -> list[str]:
    return [
        "Event counts are stored rows. Unique journeys are distinct first-party session ids, or the internal user id when a session id is absent.",
        "A visitor can complete several calculations in one journey. Conversion percentages use unique journeys, not raw event counts.",
        "Calculator starts and Pro CTA views are counted once per session and tool (or source and target) in a 30-minute window so re-rendering is not treated as new interest.",
        "A Pro tool use is a successful result, counted once per session and tool in a 30-minute window. Opening a Pro page is not a use.",
        "subscription_active is recorded only when Stripe confirms the subscription has become active. Visiting the checkout success page does not count.",
        "Campaign values are shown only when a utm_campaign or utm_source was present. Missing attribution is unknown, not guessed.",
        "Engineering calculation inputs and outputs are not stored.",
        "Percentages are omitted when the denominator is zero.",
    ]


def _observations(report: Report) -> list[str]:
    lines: list[str] = []
    if report.calculators:
        top = report.calculators[0]
        tied = [row.tool for row in report.calculators if row.completions == top.completions and row.completions]
        if top.completions and len(tied) == 1:
            lines.append(f"{_label(top.tool)} recorded the most completed free calculations this period ({top.completions}).")
        elif top.completions:
            names = ", ".join(_label(name) for name in tied)
            lines.append(f"{names} each recorded {top.completions} completed free calculations, the highest this period.")
    clicked = [row for row in report.calculators if row.pro_clicks]
    if clicked:
        best = max(clicked, key=lambda row: row.pro_clicks)
        lines.append(f"{_label(best.tool)} generated {best.pro_clicks} Pro CTA clicks.")
    if report.paths:
        path = report.paths[0]
        lines.append(
            f"{_label(path.source)} → {_label(path.target)} recorded {path.clicks} Pro CTA clicks "
            f"and {path.registrations} registrations."
        )
    return lines


def _label(tool: str) -> str:
    return tool.replace("_", " ")


def _top_lines(items: list[str]) -> list[str]:
    if not items:
        return ["None recorded."]
    return [f"{index}. {text}" for index, text in enumerate(items[:3], start=1)]


def _save_run(
    start: date,
    end: date,
    *,
    kind: str,
    status: str,
    detail: str,
    weekly_key: str | None,
) -> None:
    try:
        db.session.add(AnalyticsReportRun(
            period_start=start,
            period_end=end,
            kind=kind,
            status=status,
            weekly_key=weekly_key,
            sent_at=datetime.now(timezone.utc) if status == "sent" else None,
            detail=detail[:200],
        ))
        db.session.commit()
    except Exception:
        logger.exception("analytics report run log failed")
        db.session.rollback()


def _as_london(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(LONDON)
    if now.tzinfo is None:
        return now.replace(tzinfo=LONDON)
    return now.astimezone(LONDON)


def tool_label(name: str) -> str:
    return TOOLS.get(name, {}).get("category", name)
