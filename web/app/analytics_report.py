"""Aggregated product-analytics reports. No identities and no calculation values.

Funnel rates use ordered journeys. The 30-minute and 15-second windows in
``app.analytics`` only suppress duplicate writes. They are not conversion windows.

Attribution window: 7 days, Europe/London dates converted to UTC for queries.
A later event counts only when it is after the earlier event, within 7 days,
on the same session or the same linked user id, and the tool relationship
still matches. Both events must fall inside the reporting period. A conversion
that crosses the period boundary is not included.

Journeys with neither a session id nor a user id are counted in raw totals
and are not merged with each other.
"""

from __future__ import annotations

import html
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.analytics import FREE_TOOLS, PRO_TOOLS, TOOLS
from app.analytics_channels import classify_channel
from app.extensions import db
from app.models.analytics import AnalyticsEvent, AnalyticsReportRun

logger = logging.getLogger(__name__)

LONDON = ZoneInfo("Europe/London")
TIMEZONE_NAME = "Europe/London"
FUNNEL_WINDOW = timedelta(days=7)
MIN_SAMPLE = 5
STALE_SENDING_TIMEOUT = timedelta(minutes=30)
INSUFFICIENT = "insufficient data"

AI_PROMPT = (
    "Analyse this HVAC-CALCS weekly report. Identify the strongest and weakest "
    "parts of the funnel, what content appears to be generating useful product "
    "engagement, and recommend the three highest-priority development or "
    "marketing actions for next week. Treat the activity summary as totals, "
    "not as a sequential funnel. Do not rank a channel by traffic alone."
)

_DELTA_KEYS = (
    "calculations",
    "pro_clicks",
    "registrations",
    "pro_uses",
    "checkout",
    "paid",
)


@dataclass
class ToolRow:
    tool: str
    unique_starts: int = 0
    unique_completions: int = 0
    matched_completions: int = 0
    raw_completions: int = 0
    cta_views: int = 0
    cta_clicks: int = 0
    registrations: int = 0
    pro_uses: int = 0
    checkouts: int = 0
    subscriptions: int = 0

    @property
    def completion_rate(self) -> str:
        return completion_rate_text(self.matched_completions, self.unique_starts)

    @property
    def per_journey(self) -> str:
        if self.unique_completions <= 0:
            return "—"
        return f"{self.raw_completions / self.unique_completions:.2f}"


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
class FunnelStep:
    label: str
    eligible: int = 0
    reached: int = 0
    dropoff: int = 0
    rate: str = INSUFFICIENT


@dataclass
class ChannelRow:
    channel: str
    landing_journeys: int = 0
    calculation_journeys: int = 0
    raw_completions: int = 0
    cta_views: int = 0
    cta_clicks: int = 0
    registration_starts: int = 0
    registrations: int = 0
    pro_uses: int = 0
    checkouts: int = 0
    subscriptions: int = 0
    sequenced_clicks: int = 0
    sequenced_registrations: int = 0
    sequenced_pro: int = 0
    sequenced_checkouts: int = 0
    sequenced_subscriptions: int = 0

    @property
    def click_rate(self) -> str:
        return rate_label(self.sequenced_clicks, self.calculation_journeys)

    @property
    def registration_rate(self) -> str:
        return rate_label(self.sequenced_registrations, self.sequenced_clicks)


@dataclass
class CampaignRow:
    source: str
    medium: str
    campaign: str
    content: str
    touch: str
    landing_journeys: int = 0
    calculation_journeys: int = 0
    raw_completions: int = 0
    cta_clicks: int = 0
    registrations: int = 0
    pro_uses: int = 0
    checkouts: int = 0
    subscriptions: int = 0


@dataclass
class LandingRow:
    path: str
    channel: str
    arrivals: int = 0
    calculator_journeys: int = 0
    matched_completions: int = 0
    unique_starts: int = 0
    cta_clicks: int = 0
    registrations: int = 0
    subscriptions: int = 0

    @property
    def completion_rate(self) -> str:
        text = completion_rate_text(self.matched_completions, self.unique_starts)
        if self.unique_starts <= 0:
            return text
        if self.unique_starts < MIN_SAMPLE and text != INSUFFICIENT:
            return f"{text} (directional)"
        return text


@dataclass
class Audience:
    new_pro_users: int = 0
    returning_pro_users: int = 0
    anonymous_pro_events: int = 0
    internal_pro_events: int = 0


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
    timezone: str = TIMEZONE_NAME
    completions: int = 0
    unique_free_journeys: int = 0
    cta_views: int = 0
    cta_clicks: int = 0
    registration_starts: int = 0
    registrations: int = 0
    pro_uses: int = 0
    checkouts: int = 0
    subscriptions: int = 0
    funnel: list[FunnelStep] = field(default_factory=list)
    previous_start: date | None = None
    previous_end: date | None = None
    comparison_note: str = ""
    deltas: dict[str, str] = field(default_factory=dict)
    calculators: list[ToolRow] = field(default_factory=list)
    paths: list[PathRow] = field(default_factory=list)
    pro_tools: list[tuple[str, int]] = field(default_factory=list)
    channels_first: list[ChannelRow] = field(default_factory=list)
    channels_latest: list[ChannelRow] = field(default_factory=list)
    campaigns: list[CampaignRow] = field(default_factory=list)
    landings: list[LandingRow] = field(default_factory=list)
    audience: Audience = field(default_factory=Audience)
    google_organic_journeys: int = 0
    google_organic_completions: int = 0
    units: dict[str, int] = field(default_factory=lambda: {"SI": 0, "IP": 0})
    days: list[DayPoint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    quality_warnings: list[str] = field(default_factory=list)
    excluded_events: int = 0
    unmapped_views: int = 0
    unmapped_clicks: int = 0
    reconciled: bool = True


def completion_rate_text(matched: int, starts: int) -> str:
    if starts <= 0:
        return INSUFFICIENT
    bounded = max(0, min(matched, starts))
    return f"{round(100 * bounded / starts)}%"


def rate_label(reached: int, eligible: int) -> str:
    if eligible <= 0:
        return INSUFFICIENT
    bounded = max(0, min(reached, eligible))
    pct = round(100 * bounded / eligible)
    if eligible < MIN_SAMPLE:
        return f"{pct}% (directional)"
    return f"{pct}%"


def funnel_rate(reached: int, eligible: int) -> str:
    if eligible < MIN_SAMPLE:
        return INSUFFICIENT
    bounded = max(0, min(reached, eligible))
    return f"{round(100 * bounded / eligible)}%"


def format_delta(current: int, previous: int) -> str:
    """Both counts, from the unrounded values. Zero baseline is not infinite."""
    if previous <= 0 and current <= 0:
        return "0 → 0, No comparable baseline"
    if previous <= 0:
        return f"0 → {current}, New this period"
    change = (current - previous) / previous * 100
    rounded = int(round(change))
    sign = "+" if rounded > 0 else ""
    return f"{previous} → {current}, {sign}{rounded}%"


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
            _included(),
        )
        .order_by(AnalyticsEvent.occurred_at.asc(), AnalyticsEvent.id.asc())
        .all()
    )
    excluded = AnalyticsEvent.query.filter(
        AnalyticsEvent.occurred_at >= start_dt,
        AnalyticsEvent.occurred_at < end_dt,
        AnalyticsEvent.excluded.is_(True),
    ).count()
    report.excluded_events = int(excluded or 0)
    report.audience.internal_pro_events = int(
        AnalyticsEvent.query.filter(
            AnalyticsEvent.occurred_at >= start_dt,
            AnalyticsEvent.occurred_at < end_dt,
            AnalyticsEvent.excluded.is_(True),
            AnalyticsEvent.event_name == "pro_tool_use",
        ).count()
        or 0
    )
    _fill(report, rows)
    today = london_today()
    if end >= today:
        report.comparison_note = (
            f"Comparison omitted: the period includes {today.isoformat()} "
            f"({TIMEZONE_NAME}), which is not a complete day."
        )
        report.deltas = {key: "No comparable baseline" for key in _DELTA_KEYS}
    else:
        length = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=length - 1)
        report.previous_start = prev_start
        report.previous_end = prev_end
        prev_rows = (
            AnalyticsEvent.query.filter(
                AnalyticsEvent.occurred_at >= period_bounds(prev_start, prev_end)[0],
                AnalyticsEvent.occurred_at < period_bounds(prev_start, prev_end)[1],
                _included(),
            )
            .order_by(AnalyticsEvent.occurred_at.asc(), AnalyticsEvent.id.asc())
            .all()
        )
        previous = Report(start=prev_start, end=prev_end)
        _fill(previous, prev_rows)
        report.deltas = {
            "calculations": format_delta(report.completions, previous.completions),
            "pro_clicks": format_delta(report.cta_clicks, previous.cta_clicks),
            "registrations": format_delta(report.registrations, previous.registrations),
            "pro_uses": format_delta(report.pro_uses, previous.pro_uses),
            "checkout": format_delta(report.checkouts, previous.checkouts),
            "paid": format_delta(report.subscriptions, previous.subscriptions),
        }
    report.notes = _notes()
    return report


def report_totals(report: Report) -> dict[str, object]:
    path_views = sum(row.views for row in report.paths)
    path_clicks = sum(row.clicks for row in report.paths)
    rates = []
    for row in report.calculators:
        if row.unique_starts <= 0:
            continue
        bounded = max(0, min(row.matched_completions, row.unique_starts))
        rates.append(round(100 * bounded / row.unique_starts))
    return {
        "timezone": report.timezone,
        "cta_views": report.cta_views,
        "path_views": path_views,
        "cta_clicks": report.cta_clicks,
        "path_clicks": path_clicks,
        "views_reconcile": path_views == report.cta_views,
        "clicks_reconcile": path_clicks == report.cta_clicks,
        "raw_completions": report.completions,
        "max_unique_completion_rate_pct": max(rates) if rates else None,
        "funnel_steps": len(report.funnel),
    }


def render_markdown(report: Report) -> str:
    totals = report_totals(report)
    lines = [
        "# HVAC-CALCS Product Analytics",
        "",
        "## 1. Reporting period and timezone",
        f"Start: {report.start.isoformat()}",
        f"End: {report.end.isoformat()}",
        f"Timezone: {report.timezone}",
        "Database comparisons use a half-open UTC interval built from Europe/London midnights.",
        "",
        "## 2. Data-quality status",
    ]
    if report.quality_warnings:
        lines.extend(f"- WARNING: {note}" for note in report.quality_warnings)
    else:
        lines.append("- Headline CTA totals match the pathway table.")
    lines.append(f"- Excluded internal or test events in this period: {report.excluded_events}")
    lines.extend([
        "",
        "## 3. Acquisition summary",
        "First-touch and latest-touch are separate. Historical rows without a capture flag stay unknown.",
        f"Google organic journeys (first-party referrer): {report.google_organic_journeys}",
        f"Google organic raw completions: {report.google_organic_completions}",
        "",
        "## 4. Product activity summary",
        "These are period totals. They are not a sequential cohort funnel.",
        f"Raw free calculations: {report.completions}",
        f"Unique free-calculation journeys: {report.unique_free_journeys}",
        f"Total CTA views: {report.cta_views}",
        f"Total CTA clicks: {report.cta_clicks}",
        f"Registration starts: {report.registration_starts}",
        f"Registrations: {report.registrations}",
        f"Successful Pro tool uses: {report.pro_uses}",
        f"Checkout starts: {report.checkouts}",
        f"Active subscriptions: {report.subscriptions}",
        "",
        "## 5. Sequenced conversion funnel",
        "A step counts only when the later event follows the earlier one on the same journey or linked user, within 7 days, inside this period.",
        "Step | Eligible | Reached | Drop-off | Conversion",
    ])
    for step in report.funnel:
        lines.append(
            f"{step.label} | {step.eligible} | {step.reached} | {step.dropoff} | {step.rate}"
        )
    lines.extend([
        "",
        "## 6. Calculator performance",
        "Calculator | Unique starts | Unique completing journeys | Unique completion rate | Raw completions | Calculations per completing journey | Pro CTA views | Pro CTA clicks | Registrations | Successful target Pro uses | Checkout starts | Active subscriptions",
    ])
    if report.calculators:
        for row in report.calculators:
            lines.append(
                f"{row.tool} | {row.unique_starts} | {row.unique_completions} | {row.completion_rate} | "
                f"{row.raw_completions} | {row.per_journey} | {row.cta_views} | {row.cta_clicks} | "
                f"{row.registrations} | {row.pro_uses} | {row.checkouts} | {row.subscriptions}"
            )
    else:
        lines.append("No free-calculator events in this period.")
    lines.extend([
        "",
        "## 7. Free-to-Pro pathway performance",
        "Source | Target | CTA views | CTA clicks | Registrations | Pro uses | Paid",
    ])
    for row in report.paths:
        lines.append(
            f"{row.source} | {row.target} | {row.views} | {row.clicks} | "
            f"{row.registrations} | {row.pro_uses} | {row.paid}"
        )
    lines.append(
        f"total | — | {report.cta_views} | {report.cta_clicks} | {report.registrations} | — | —"
    )
    lines.extend(["", "## 8. New-user versus returning-user Pro usage"])
    audience = report.audience
    lines.extend([
        f"New registered users using Pro: {audience.new_pro_users}",
        f"Returning registered users using Pro: {audience.returning_pro_users}",
        f"Anonymous or unlinked Pro events: {audience.anonymous_pro_events}",
        f"Internal or test Pro events: {audience.internal_pro_events}",
        "A Pro use in this period is not assumed to come from a registration in this period.",
        "",
        "## 9. Channel performance",
        "### First-touch acquisition",
        _channel_header(),
    ])
    lines.extend(_channel_lines(report.channels_first))
    lines.extend(["", "### Latest-touch conversion influence", _channel_header()])
    lines.extend(_channel_lines(report.channels_latest))
    lines.extend([
        "",
        "## 10. Campaign performance",
        "Touch | UTM source | UTM medium | UTM campaign | UTM content | Unique landing journeys | Unique free-calculation journeys | Raw calculations | CTA clicks | Registrations | Successful Pro uses | Checkout starts | Subscriptions",
    ])
    if report.campaigns:
        for row in report.campaigns:
            lines.append(
                f"{row.touch} | {row.source} | {row.medium} | {row.campaign} | {row.content} | "
                f"{row.landing_journeys} | {row.calculation_journeys} | {row.raw_completions} | "
                f"{row.cta_clicks} | {row.registrations} | {row.pro_uses} | {row.checkouts} | {row.subscriptions}"
            )
    else:
        lines.append("No events in this period.")
    lines.extend([
        "",
        "## 11. Landing-page performance",
        "Landing path | Channel | Unique arrivals | Unique calculator journeys | Calculator completion rate | CTA clicks | Registrations | Subscriptions",
    ])
    if report.landings:
        for row in report.landings:
            lines.append(
                f"{row.path} | {row.channel} | {row.arrivals} | {row.calculator_journeys} | "
                f"{row.completion_rate} | {row.cta_clicks} | {row.registrations} | {row.subscriptions}"
            )
    else:
        lines.append("No landing journeys in this period.")
    lines.extend([
        "",
        "## 12. First-touch and latest-touch attribution",
        "First-touch is the channel section under acquisition. Latest-touch is the channel section under conversion influence.",
        "Stored raw fields are utm_source, utm_medium, utm_campaign, utm_content, utm_term, landing path and referring hostname.",
        "The channel label is recomputed from those fields when the report is built.",
        "",
        "## 13. Organic-search summary",
        f"First-party google / organic journeys: {report.google_organic_journeys}",
        f"Raw completions on those journeys: {report.google_organic_completions}",
        "document.referrer does not provide the visitor's Google search query.",
        "Query, impression, click, click-through rate, average position and landing page in Google's index come from Google Search Console, which is not connected to this dashboard.",
        "Compare Search Console exports to the landing paths in section 11. Do not add the Search Console numbers to these first-party totals.",
        "",
        "## 14. Unit-system usage",
        f"SI: {report.units.get('SI', 0)}",
        f"Imperial: {report.units.get('IP', 0)}",
        "",
        "## 15. Week-on-week comparison",
    ])
    if report.comparison_note:
        lines.append(report.comparison_note)
    else:
        lines.append(f"Previous period: {report.previous_start} to {report.previous_end} ({report.timezone})")
        lines.append("The two periods have the same number of days and do not overlap.")
    lines.extend([
        f"Calculations: {report.deltas.get('calculations', '—')}",
        f"Pro clicks: {report.deltas.get('pro_clicks', '—')}",
        f"Registrations: {report.deltas.get('registrations', '—')}",
        f"Pro uses: {report.deltas.get('pro_uses', '—')}",
        f"Checkout: {report.deltas.get('checkout', '—')}",
        f"Paid: {report.deltas.get('paid', '—')}",
        "",
        "## 16. Unmapped and missing-data counts",
        f"Unmapped or non-result CTA views: {report.unmapped_views}",
        f"Unmapped or non-result CTA clicks: {report.unmapped_clicks}",
        "Missing attribution is unknown. It is not classified as direct.",
        "",
        "## 17. Methodology and definitions",
    ])
    lines.extend(f"- {note}" for note in report.notes)
    lines.extend([
        "",
        "## 18. Automated report-delivery status",
        "The web service does not schedule this email. A separate Railway cron process runs `flask --app wsgi analytics-weekly-report`.",
        "One successful send per London week is stored on analytics_report_runs.weekly_key.",
        "A failed send clears that key so a later run can retry. A second success for the same week cannot insert another key.",
        "",
        "## Machine-readable totals",
        "```json",
        json.dumps(totals, sort_keys=True),
        "```",
        "",
    ])
    return "\n".join(lines)


def render_email_text(report: Report) -> str:
    observations = _observations(report)
    obs = "\n".join(f"- {line}" for line in observations) or "- No product events in this period."
    markdown = render_markdown(report)
    return "\n".join([
        "HVAC-CALCS Weekly Product Report",
        "",
        "PERIOD",
        f"{report.start.isoformat()} to {report.end.isoformat()} ({report.timezone})",
        "",
        "ACTIVITY (not a sequential funnel)",
        f"Free calculations completed       {report.completions}",
        f"Unique free journeys              {report.unique_free_journeys}",
        f"Pro CTA clicks                    {report.cta_clicks}",
        f"Registrations                     {report.registrations}",
        f"Pro tools used                    {report.pro_uses}",
        f"Checkout starts                   {report.checkouts}",
        f"New subscriptions                 {report.subscriptions}",
        "",
        "PREVIOUS-PERIOD COMPARISON",
        report.comparison_note or f"Previous period: {report.previous_start} to {report.previous_end}",
        f"Calculations        {report.deltas.get('calculations', '—')}",
        f"Pro clicks          {report.deltas.get('pro_clicks', '—')}",
        f"Registrations       {report.deltas.get('registrations', '—')}",
        f"Pro usage           {report.deltas.get('pro_uses', '—')}",
        f"Checkout            {report.deltas.get('checkout', '—')}",
        f"Subscriptions       {report.deltas.get('paid', '—')}",
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
    """Full report as the HTML body. Mail apps show this part, not the plain text."""
    document = _markdown_email_html(render_markdown(report))
    prompt = html.escape(AI_PROMPT, quote=True)
    return (
        "<div style=\"font-family:Georgia,serif;color:#0E1116;line-height:1.45;max-width:720px\">"
        f"{document}"
        "<h2 style=\"font-size:17px;margin:24px 0 8px\">AI analysis</h2>"
        "<p style=\"margin:0 0 10px\">Copy this report into Microsoft Copilot and ask:</p>"
        f"<p style=\"margin:0 0 10px\">{prompt}</p>"
        "</div>"
    )


def _markdown_email_html(markdown: str) -> str:
    lines = markdown.splitlines()
    parts: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            parts.append(
                "<pre style=\"font-family:Consolas,monospace;font-size:12px;"
                "white-space:pre-wrap;background:#f4f6f8;padding:12px;margin:8px 0 16px\">"
                f"{html.escape(chr(10).join(block), quote=True)}</pre>"
            )
            continue
        if line.startswith("### "):
            parts.append(_email_heading(3, line[4:]))
            index += 1
            continue
        if line.startswith("## "):
            parts.append(_email_heading(2, line[3:]))
            index += 1
            continue
        if line.startswith("# "):
            parts.append(_email_heading(1, line[2:]))
            index += 1
            continue
        if line.startswith("- "):
            items: list[str] = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append(
                    "<li style=\"margin:0 0 4px\">"
                    f"{html.escape(lines[index][2:], quote=True)}</li>"
                )
                index += 1
            parts.append(
                "<ul style=\"margin:8px 0 16px;padding-left:20px\">"
                + "".join(items)
                + "</ul>"
            )
            continue
        if " | " in line:
            rows: list[list[str]] = []
            while index < len(lines) and " | " in lines[index]:
                rows.append([cell.strip() for cell in lines[index].split(" | ")])
                index += 1
            parts.append(_email_table(rows))
            continue
        if line.strip():
            parts.append(
                "<p style=\"margin:0 0 10px\">"
                f"{html.escape(line, quote=True)}</p>"
            )
        index += 1
    return "".join(parts)


def _email_heading(level: int, text: str) -> str:
    safe = html.escape(text, quote=True)
    if level == 1:
        return f"<h1 style=\"font-size:22px;margin:0 0 12px\">{safe}</h1>"
    if level == 2:
        return f"<h2 style=\"font-size:17px;margin:24px 0 8px\">{safe}</h2>"
    return f"<h3 style=\"font-size:15px;margin:18px 0 6px\">{safe}</h3>"


def _email_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    body = rows[1:]
    if not body:
        return (
            "<p style=\"margin:0 0 10px\">"
            f"{html.escape(' | '.join(header), quote=True)}</p>"
        )
    if len(header) <= 5:
        return _email_grid_table(header, body)
    return _email_stacked_table(header, body)


def _email_grid_table(header: list[str], body: list[list[str]]) -> str:
    head = "".join(
        "<th style=\"text-align:left;border-bottom:1px solid #ccc;padding:4px 8px 4px 0\">"
        f"{html.escape(cell, quote=True)}</th>"
        for cell in header
    )
    rendered = []
    for row in body:
        cells = "".join(
            "<td style=\"padding:4px 8px 4px 0;vertical-align:top\">"
            f"{html.escape(row[index] if index < len(row) else '', quote=True)}</td>"
            for index in range(len(header))
        )
        rendered.append(f"<tr>{cells}</tr>")
    return (
        "<table style=\"border-collapse:collapse;width:100%;margin:8px 0 16px;font-size:14px\">"
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rendered)}</tbody></table>"
    )


def _email_stacked_table(header: list[str], body: list[list[str]]) -> str:
    blocks: list[str] = []
    labels = header[1:]
    for row in body:
        title = row[0] if row else ""
        pairs = []
        for index, label in enumerate(labels, start=1):
            value = row[index] if index < len(row) else ""
            pairs.append(
                "<tr>"
                "<td style=\"padding:2px 16px 2px 0;color:#444;vertical-align:top\">"
                f"{html.escape(label, quote=True)}</td>"
                "<td style=\"padding:2px 0;vertical-align:top\">"
                f"{html.escape(value, quote=True)}</td>"
                "</tr>"
            )
        blocks.append(
            "<div style=\"margin:0 0 14px;padding:8px 0;border-top:1px solid #e2e2e2\">"
            "<p style=\"margin:0 0 6px;font-weight:bold\">"
            f"{html.escape(title, quote=True)}</p>"
            f"<table style=\"border-collapse:collapse;font-size:14px\">{''.join(pairs)}</table>"
            "</div>"
        )
    return "".join(blocks)


def send_analytics_report(report: Report, *, kind: str) -> tuple[bool, str, str | None]:
    """Send one report. Returns (ok, message, provider message id)."""
    from app.mail import mail_configured, send_email

    recipient = (current_app.config.get("ANALYTICS_REPORT_EMAIL") or "").strip()
    if not recipient or "@" not in recipient:
        return False, "Report email is not configured.", None
    if not mail_configured():
        return False, "Email is not configured.", None
    subject = f"HVAC-CALCS Weekly Report | {report.start.isoformat()} - {report.end.isoformat()}"
    ok = send_email(
        to=recipient,
        subject=subject,
        body=render_email_text(report),
        html=render_email_html(report),
    )
    message_id = getattr(send_email, "last_message_id", None)
    if not isinstance(message_id, str) or not message_id:
        message_id = None
    else:
        message_id = message_id[:80]
    if not ok:
        logger.error("analytics report send failed kind=%s", kind)
        return False, "The report email could not be sent.", None
    logger.info(
        "analytics report sent kind=%s period=%s..%s provider_message_id=%s",
        kind,
        report.start.isoformat(),
        report.end.isoformat(),
        message_id or "",
    )
    return True, "Report sent.", message_id


def send_manual_report(start: date, end: date) -> tuple[bool, str]:
    report = build_report(start, end)
    ok, message, message_id = send_analytics_report(report, kind="manual")
    _save_run(
        start,
        end,
        kind="manual",
        status="sent" if ok else "failed",
        detail=message,
        weekly_key=None,
        message_id=message_id,
    )
    return ok, message


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _sending_is_stale(run: AnalyticsReportRun, moment: datetime) -> bool:
    claimed = run.started_at or run.created_at
    if claimed is None:
        return True
    return _as_utc(moment) - _as_utc(claimed) >= STALE_SENDING_TIMEOUT


def _release_stale_send(run_id: int, key: str) -> bool:
    released = AnalyticsReportRun.query.filter_by(
        id=run_id,
        weekly_key=key,
        status="sending",
    ).update(
        {
            "status": "failed",
            "weekly_key": None,
            "detail": "stale sending released for retry",
            "completed_at": datetime.now(timezone.utc),
        },
        synchronize_session=False,
    )
    db.session.commit()
    db.session.expire_all()
    return released == 1


def send_weekly_analytics_report(now: datetime | None = None) -> str:
    """Send the previous London week once.

    ``weekly_key`` is the period start date. A successful send keeps that
    key. A failed email clears the key so the next run can retry. A
    ``sending`` row younger than 30 minutes blocks a concurrent run.
    """
    if not current_app.config.get("ANALYTICS_WEEKLY_REPORT_ENABLED"):
        logger.info("analytics_weekly_report status=disabled")
        return "disabled"
    moment = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    start, end = previous_complete_week(now)
    key = start.isoformat()
    existing = AnalyticsReportRun.query.filter_by(weekly_key=key).first()
    if existing is not None:
        if existing.status == "sent" or not _sending_is_stale(existing, moment):
            logger.info("analytics_weekly_report period=%s status=already-sent", key)
            return "already-sent"
        if not _release_stale_send(existing.id, key):
            logger.info("analytics_weekly_report period=%s status=already-sent", key)
            return "already-sent"
    attempt = AnalyticsReportRun.query.filter_by(period_start=start, kind="weekly").count() + 1
    started = datetime.now(timezone.utc)
    run = AnalyticsReportRun(
        period_start=start,
        period_end=end,
        kind="weekly",
        status="sending",
        weekly_key=key,
        started_at=started,
        attempt_count=attempt,
    )
    try:
        db.session.add(run)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logger.info("analytics_weekly_report period=%s status=already-sent", key)
        return "already-sent"
    logger.info("analytics_weekly_report period=%s status=sending attempt=%s", key, attempt)
    report = build_report(start, end)
    ok, message, message_id = send_analytics_report(report, kind="weekly")
    fields = {
        "status": "sent" if ok else "failed",
        "detail": (message or "")[:200],
        "sent_at": datetime.now(timezone.utc) if ok else None,
        "completed_at": datetime.now(timezone.utc),
        "provider_message_id": message_id,
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
        logger.error("analytics_weekly_report period=%s status=lost-claim", key)
        return "lost-claim"
    result = "sent" if ok else "failed"
    logger.info(
        "analytics_weekly_report period=%s status=%s attempt=%s provider_message_id=%s",
        key,
        result,
        attempt,
        message_id or "",
    )
    return result


def prune_analytics_events(now: datetime | None = None) -> int:
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


def weekly_job_health(now: datetime | None = None) -> dict[str, object]:
    """Whether the last complete London week has a successful send."""
    start, end = previous_complete_week(now)
    sent = AnalyticsReportRun.query.filter_by(weekly_key=start.isoformat(), status="sent").first()
    last_sent = (
        AnalyticsReportRun.query.filter_by(kind="weekly", status="sent")
        .order_by(AnalyticsReportRun.sent_at.desc())
        .first()
    )
    london = _as_london(now)
    enabled = bool(current_app.config.get("ANALYTICS_WEEKLY_REPORT_ENABLED"))
    missed = False
    if enabled and sent is None:
        this_monday = london.date() - timedelta(days=london.weekday())
        deadline = datetime.combine(this_monday, time(9, 0), tzinfo=LONDON)
        if london >= deadline:
            missed = True
            logger.warning("analytics weekly report missed period=%s", start.isoformat())
    return {
        "period_start": start,
        "period_end": end,
        "sent_run": sent,
        "last_sent": last_sent,
        "missed": missed,
        "enabled": enabled,
        "timezone": TIMEZONE_NAME,
    }


def events_today_count(now: datetime | None = None) -> int:
    today = london_today(now)
    start_dt, end_dt = period_bounds(today, today)
    return AnalyticsEvent.query.filter(
        AnalyticsEvent.occurred_at >= start_dt,
        AnalyticsEvent.occurred_at < end_dt,
        _included(),
    ).count()


def last_event_at() -> datetime | None:
    row = (
        AnalyticsEvent.query.filter(_included())
        .order_by(AnalyticsEvent.occurred_at.desc())
        .first()
    )
    return row.occurred_at if row else None


def _included():
    return or_(AnalyticsEvent.excluded.is_(False), AnalyticsEvent.excluded.is_(None))


def _fill(report: Report, rows: list[AnalyticsEvent]) -> None:
    by_session: dict[str, list[AnalyticsEvent]] = defaultdict(list)
    by_user: dict[int, list[AnalyticsEvent]] = defaultdict(list)
    for row in rows:
        if row.anonymous_session_id:
            by_session[row.anonymous_session_id].append(row)
        if row.user_id is not None:
            by_user[row.user_id].append(row)

    def candidates(event: AnalyticsEvent) -> list[AnalyticsEvent]:
        found: list[AnalyticsEvent] = []
        seen: set[int] = set()
        pools: list[AnalyticsEvent] = []
        if event.anonymous_session_id:
            pools.extend(by_session.get(event.anonymous_session_id, []))
        if event.user_id is not None:
            pools.extend(by_user.get(event.user_id, []))
        for item in pools:
            marker = id(item)
            if marker in seen or item is event:
                continue
            seen.add(marker)
            found.append(item)
        found.sort(key=lambda item: (_aware(item.occurred_at), item.id or 0))
        return found

    def after(earlier: AnalyticsEvent, later: AnalyticsEvent) -> bool:
        start_at = _aware(earlier.occurred_at)
        end_at = _aware(later.occurred_at)
        return start_at < end_at <= start_at + FUNNEL_WINDOW

    def first_match(events: list[AnalyticsEvent], predicate) -> tuple[dict[str, AnalyticsEvent], dict[str, AnalyticsEvent]]:
        groups: dict[str, list[AnalyticsEvent]] = defaultdict(list)
        for event in events:
            key = _journey(event)
            if key:
                groups[key].append(event)
        reached: dict[str, AnalyticsEvent] = {}
        for key, items in groups.items():
            for prev in items:
                for cand in candidates(prev):
                    if after(prev, cand) and predicate(prev, cand):
                        reached[key] = cand
                        break
                if key in reached:
                    break
        eligible = {key: items[0] for key, items in groups.items()}
        return eligible, reached

    def advance(stage: dict[str, AnalyticsEvent], predicate) -> dict[str, AnalyticsEvent]:
        reached: dict[str, AnalyticsEvent] = {}
        for key, prev in stage.items():
            for cand in candidates(prev):
                if after(prev, cand) and predicate(prev, cand):
                    reached[key] = cand
                    break
        return reached

    completes = [row for row in rows if row.event_name == "calculator_complete" and row.tool in FREE_TOOLS]
    complete_stage, view_stage = first_match(completes, _view_follows)
    click_stage = advance(view_stage, _click_follows)
    reg_start_stage = advance(click_stage, _registration_start_follows)
    reg_done_stage = advance(reg_start_stage, _registration_complete_follows)
    pro_stage = advance(reg_done_stage, _pro_follows)
    checkout_stage = advance(pro_stage, _checkout_follows)
    paid_stage = advance(checkout_stage, _subscription_follows)
    paid_from_complete = advance(complete_stage, _subscription_follows)

    report.funnel = [
        _step("Free completion → CTA view", complete_stage, view_stage),
        _step("CTA view → CTA click", view_stage, click_stage),
        _step("CTA click → registration start", click_stage, reg_start_stage),
        _step("Registration start → registration complete", reg_start_stage, reg_done_stage),
        _step("Registration complete → successful target Pro use", reg_done_stage, pro_stage),
        _step("Successful Pro use → checkout", pro_stage, checkout_stage),
        _step("Checkout → active subscription", checkout_stage, paid_stage),
        _step("Free completion → active subscription", complete_stage, paid_from_complete),
    ]

    calc: dict[str, ToolRow] = {name: ToolRow(tool=name) for name in sorted(FREE_TOOLS)}
    starts: dict[str, dict[str, list[datetime]]] = defaultdict(lambda: defaultdict(list))
    dones: dict[str, dict[str, list[datetime]]] = defaultdict(lambda: defaultdict(list))
    paths: dict[tuple[str, str], PathRow] = {
        ("unmapped source", "—"): PathRow("unmapped source", "—"),
        ("unmapped target", "—"): PathRow("unmapped target", "—"),
        ("other CTA placement", "—"): PathRow("other CTA placement", "—"),
    }
    pro_counts: dict[str, int] = {}
    by_day: dict[date, DayPoint] = {}
    free_journeys: set[str] = set()
    journey_events: dict[str, list[AnalyticsEvent]] = defaultdict(list)
    reg_users_in_period: set[int] = set()

    for row in rows:
        key = _journey(row)
        if key:
            journey_events[key].append(row)
        day = _event_day(row.occurred_at)
        point = by_day.setdefault(day, DayPoint(day=day))
        name = row.event_name
        if name == "calculator_complete" and row.tool in FREE_TOOLS:
            report.completions += 1
            point.completions += 1
            calc[row.tool].raw_completions += 1
            if key:
                free_journeys.add(key)
                dones[row.tool][key].append(_aware(row.occurred_at))
            if row.unit_system in {"SI", "IP"}:
                report.units[row.unit_system] += 1
        elif name == "calculator_start" and row.tool in FREE_TOOLS and key:
            starts[row.tool][key].append(_aware(row.occurred_at))
        elif name == "pro_cta_view":
            report.cta_views += 1
            bucket = _path_bucket(row)
            _path_row(paths, bucket).views += 1
            if row.source in FREE_TOOLS:
                calc[row.source].cta_views += 1
            if bucket[0] != row.source:
                report.unmapped_views += 1
        elif name == "pro_cta_click":
            report.cta_clicks += 1
            bucket = _path_bucket(row)
            _path_row(paths, bucket).clicks += 1
            if row.source in FREE_TOOLS:
                calc[row.source].cta_clicks += 1
            if bucket[0] != row.source:
                report.unmapped_clicks += 1
        elif name == "registration_start":
            report.registration_starts += 1
        elif name == "registration_complete":
            report.registrations += 1
            point.registrations += 1
            bucket = _path_bucket(row)
            _path_row(paths, bucket).registrations += 1
            if row.source in FREE_TOOLS:
                calc[row.source].registrations += 1
            if row.user_id is not None:
                reg_users_in_period.add(row.user_id)
        elif name == "pro_tool_use" and row.tool in PRO_TOOLS:
            report.pro_uses += 1
            point.pro_uses += 1
            pro_counts[row.tool] = pro_counts.get(row.tool, 0) + 1
        elif name == "checkout_start":
            report.checkouts += 1
        elif name == "subscription_active":
            report.subscriptions += 1
            point.subscriptions += 1

    report.unique_free_journeys = len(free_journeys)
    for tool, per_journey in dones.items():
        calc[tool].unique_completions = len(per_journey)
        for key, moments in per_journey.items():
            prior = starts[tool].get(key, [])
            if any(start_at < done_at <= start_at + FUNNEL_WINDOW for start_at in prior for done_at in moments):
                calc[tool].matched_completions += 1
    for tool, per_journey in starts.items():
        calc[tool].unique_starts = len(per_journey)

    _attribute_downstream(calc, paths, rows, candidates, after)
    report.calculators = sorted(
        [row for row in calc.values() if _tool_visible(row)],
        key=lambda row: (-row.raw_completions, -row.unique_starts, row.tool),
    )
    recognised = [row for key, row in paths.items() if key[0] not in {"unmapped source", "unmapped target", "other CTA placement"}]
    specials = [paths[key] for key in (("unmapped source", "—"), ("unmapped target", "—"), ("other CTA placement", "—"))]
    report.paths = sorted(recognised, key=lambda row: (-row.clicks, -row.views, row.source, row.target)) + specials
    report.pro_tools = sorted(pro_counts.items(), key=lambda item: (-item[1], item[0]))
    _channels_and_campaigns(report, rows, journey_events, click_stage, reg_done_stage, pro_stage, checkout_stage, paid_stage)
    _audience(report, rows, reg_users_in_period)
    _reconcile(report)
    cursor = report.start
    days: list[DayPoint] = []
    while cursor <= report.end:
        days.append(by_day.get(cursor, DayPoint(day=cursor)))
        cursor += timedelta(days=1)
    report.days = days


def _attribute_downstream(calc, paths, rows, candidates, after) -> None:
    """Count Pro use, checkout and subscription after a linked CTA for that source."""
    clicks = [
        row for row in rows
        if row.event_name == "pro_cta_click" and row.source in FREE_TOOLS and row.target in PRO_TOOLS
    ]
    for click in clicks:
        bucket = _path_bucket(click)
        for cand in candidates(click):
            if not after(click, cand):
                continue
            if cand.event_name == "pro_tool_use" and cand.tool == click.target:
                calc[click.source].pro_uses += 1
                _path_row(paths, bucket).pro_uses += 1
            elif cand.event_name == "checkout_start":
                calc[click.source].checkouts += 1
            elif cand.event_name == "subscription_active":
                calc[click.source].subscriptions += 1
                _path_row(paths, bucket).paid += 1


def _channels_and_campaigns(report, rows, journey_events, click_stage, reg_stage, pro_stage, checkout_stage, paid_stage) -> None:
    first_channel: dict[str, str] = {}
    latest_channel: dict[str, str] = {}
    landing_path: dict[str, str] = {}
    for key, events in journey_events.items():
        first = events[0]
        last = events[-1]
        first_channel[key] = _touch_channel(first, "first")
        latest_channel[key] = _touch_channel(last, "latest")
        landing_path[key] = first.first_landing_path or "unknown"
        if first_channel[key] == "google / organic":
            report.google_organic_journeys += 1

    def blank(channel: str) -> ChannelRow:
        return ChannelRow(channel=channel)

    first_rows: dict[str, ChannelRow] = {}
    latest_rows: dict[str, ChannelRow] = {}
    landing_rows: dict[tuple[str, str], LandingRow] = {}
    campaign_rows: dict[tuple, CampaignRow] = {}
    seen_campaign_journey: set[tuple] = set()

    sequenced = {
        "click": set(click_stage),
        "register": set(reg_stage),
        "pro": set(pro_stage),
        "checkout": set(checkout_stage),
        "paid": set(paid_stage),
    }
    # click_stage is reached from views, which is the cohort. sequenced_clicks
    # for a channel should be free-calculation journeys that reached a click.
    calc_journeys = {key for key, events in journey_events.items() if any(event.event_name == "calculator_complete" and event.tool in FREE_TOOLS for event in events)}
    start_journeys = {key for key, events in journey_events.items() if any(event.event_name == "calculator_start" and event.tool in FREE_TOOLS for event in events)}

    for key in journey_events:
        for table, channel in ((first_rows, first_channel[key]), (latest_rows, latest_channel[key])):
            row = table.setdefault(channel, blank(channel))
            row.landing_journeys += 1
            if key in calc_journeys:
                row.calculation_journeys += 1
            if key in sequenced["click"]:
                row.sequenced_clicks += 1
            if key in sequenced["register"]:
                row.sequenced_registrations += 1
            if key in sequenced["pro"]:
                row.sequenced_pro += 1
            if key in sequenced["checkout"]:
                row.sequenced_checkouts += 1
            if key in sequenced["paid"]:
                row.sequenced_subscriptions += 1
        landing = landing_rows.setdefault(
            (landing_path[key], first_channel[key]),
            LandingRow(path=landing_path[key], channel=first_channel[key]),
        )
        landing.arrivals += 1
        if key in calc_journeys:
            landing.calculator_journeys += 1
        if key in start_journeys:
            landing.unique_starts += 1

    matched_tools = _matched_journeys(rows)
    for key in matched_tools:
        if key in landing_path:
            landing = landing_rows.get((landing_path[key], first_channel[key]))
            if landing:
                landing.matched_completions += 1

    for row in rows:
        key = _journey(row)
        channel_first = first_channel.get(key or "", "unknown")
        channel_latest = latest_channel.get(key or "", "unknown")
        if row.event_name == "calculator_complete" and row.tool in FREE_TOOLS:
            if key and channel_first == "google / organic":
                report.google_organic_completions += 1
            _channel_get(first_rows, channel_first).raw_completions += 1
            _channel_get(latest_rows, channel_latest).raw_completions += 1
        elif row.event_name == "pro_cta_view":
            _channel_get(first_rows, channel_first).cta_views += 1
            _channel_get(latest_rows, channel_latest).cta_views += 1
        elif row.event_name == "pro_cta_click":
            _channel_get(first_rows, channel_first).cta_clicks += 1
            _channel_get(latest_rows, channel_latest).cta_clicks += 1
            if key and key in landing_path:
                landing_rows[(landing_path[key], first_channel[key])].cta_clicks += 1
        elif row.event_name == "registration_start":
            _channel_get(first_rows, channel_first).registration_starts += 1
            _channel_get(latest_rows, channel_latest).registration_starts += 1
        elif row.event_name == "registration_complete":
            _channel_get(first_rows, channel_first).registrations += 1
            _channel_get(latest_rows, channel_latest).registrations += 1
            if key and key in landing_path:
                landing_rows[(landing_path[key], first_channel[key])].registrations += 1
        elif row.event_name == "pro_tool_use" and row.tool in PRO_TOOLS:
            _channel_get(first_rows, channel_first).pro_uses += 1
            _channel_get(latest_rows, channel_latest).pro_uses += 1
        elif row.event_name == "checkout_start":
            _channel_get(first_rows, channel_first).checkouts += 1
            _channel_get(latest_rows, channel_latest).checkouts += 1
        elif row.event_name == "subscription_active":
            _channel_get(first_rows, channel_first).subscriptions += 1
            _channel_get(latest_rows, channel_latest).subscriptions += 1
            if key and key in landing_path:
                landing_rows[(landing_path[key], first_channel[key])].subscriptions += 1

        touch, source, medium, campaign, content = _campaign_identity(row)
        ident = (touch, source, medium, campaign, content)
        camp = campaign_rows.setdefault(
            ident,
            CampaignRow(source=source, medium=medium, campaign=campaign, content=content, touch=touch),
        )
        if key and (ident, key) not in seen_campaign_journey:
            seen_campaign_journey.add((ident, key))
            camp.landing_journeys += 1
            if key in calc_journeys:
                camp.calculation_journeys += 1
        if row.event_name == "calculator_complete" and row.tool in FREE_TOOLS:
            camp.raw_completions += 1
        elif row.event_name == "pro_cta_click":
            camp.cta_clicks += 1
        elif row.event_name == "registration_complete":
            camp.registrations += 1
        elif row.event_name == "pro_tool_use" and row.tool in PRO_TOOLS:
            camp.pro_uses += 1
        elif row.event_name == "checkout_start":
            camp.checkouts += 1
        elif row.event_name == "subscription_active":
            camp.subscriptions += 1

    report.channels_first = _sorted_channels(first_rows)
    report.channels_latest = _sorted_channels(latest_rows)
    report.campaigns = sorted(
        campaign_rows.values(),
        key=lambda row: (-row.raw_completions, -row.registrations, row.source, row.campaign),
    )
    report.landings = sorted(
        landing_rows.values(),
        key=lambda row: (-row.arrivals, row.path, row.channel),
    )


def _audience(report: Report, rows: list[AnalyticsEvent], reg_users: set[int]) -> None:
    new_users: set[int] = set()
    returning: set[int] = set()
    anonymous = 0
    created: dict[int, datetime] = {}
    user_ids = {row.user_id for row in rows if row.event_name == "pro_tool_use" and row.user_id is not None}
    if user_ids:
        from app.models import User

        for user in User.query.filter(User.id.in_(user_ids)).all():
            created[user.id] = _aware(user.created_at)
    start_dt, end_dt = period_bounds(report.start, report.end)
    for row in rows:
        if row.event_name != "pro_tool_use" or row.tool not in PRO_TOOLS:
            continue
        if row.user_id is None:
            anonymous += 1
            continue
        moment = created.get(row.user_id)
        if row.user_id in reg_users or (moment is not None and start_dt <= moment < end_dt):
            new_users.add(row.user_id)
        else:
            returning.add(row.user_id)
    report.audience.new_pro_users = len(new_users)
    report.audience.returning_pro_users = len(returning)
    report.audience.anonymous_pro_events = anonymous


def _reconcile(report: Report) -> None:
    path_views = sum(row.views for row in report.paths)
    path_clicks = sum(row.clicks for row in report.paths)
    if path_views != report.cta_views or path_clicks != report.cta_clicks:
        report.reconciled = False
        report.quality_warnings.append(
            "CTA pathway totals do not match the headline totals. "
            f"views {path_views}/{report.cta_views}, clicks {path_clicks}/{report.cta_clicks}."
        )
        logger.error(
            "analytics CTA mismatch views_detail=%s views_headline=%s clicks_detail=%s clicks_headline=%s",
            path_views,
            report.cta_views,
            path_clicks,
            report.cta_clicks,
        )
    else:
        report.reconciled = True


def _matched_journeys(rows: list[AnalyticsEvent]) -> set[str]:
    starts: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    found: set[str] = set()
    for row in rows:
        key = _journey(row)
        if not key or row.tool not in FREE_TOOLS:
            continue
        if row.event_name == "calculator_start":
            starts[(key, row.tool)].append(_aware(row.occurred_at))
    for row in rows:
        key = _journey(row)
        if not key or row.event_name != "calculator_complete" or row.tool not in FREE_TOOLS:
            continue
        done = _aware(row.occurred_at)
        if any(start_at < done <= start_at + FUNNEL_WINDOW for start_at in starts.get((key, row.tool), [])):
            found.add(key)
    return found


def _path_bucket(row: AnalyticsEvent) -> tuple[str, str]:
    source = row.source if row.source in FREE_TOOLS else None
    target = row.target if row.target in PRO_TOOLS else None
    placement = row.cta_placement or ""
    if source is None:
        return ("unmapped source", "—")
    if target is None:
        return ("unmapped target", "—")
    if placement and placement != "result":
        return ("other CTA placement", "—")
    return (source, target)


def _path_row(paths: dict[tuple[str, str], PathRow], bucket: tuple[str, str]) -> PathRow:
    row = paths.get(bucket)
    if row is None:
        row = PathRow(source=bucket[0], target=bucket[1])
        paths[bucket] = row
    return row


def _touch_channel(row: AnalyticsEvent, which: str) -> str:
    if which == "first":
        return classify_channel(
            utm_source=row.first_utm_source,
            referrer_host=row.first_referrer_host,
            captured=bool(row.first_captured),
        )
    return classify_channel(
        utm_source=row.utm_source,
        referrer_host=row.latest_referrer_host,
        captured=bool(row.latest_captured),
    )


def _campaign_identity(row: AnalyticsEvent) -> tuple[str, str, str, str, str]:
    source = row.utm_source or "unknown"
    medium = row.utm_medium or "unknown"
    campaign = row.utm_campaign or "unknown"
    content = row.utm_content or "unknown"
    if bool(row.latest_captured):
        touch = "latest"
    elif row.utm_source or row.utm_medium or row.utm_campaign or row.utm_content:
        touch = "historical-unsplit"
    else:
        touch = "unknown"
    return touch, source, medium, campaign, content


def _channel_get(table: dict[str, ChannelRow], channel: str) -> ChannelRow:
    row = table.get(channel)
    if row is None:
        row = ChannelRow(channel=channel)
        table[channel] = row
    return row


def _sorted_channels(table: dict[str, ChannelRow]) -> list[ChannelRow]:
    return sorted(table.values(), key=lambda row: (-row.landing_journeys, -row.subscriptions, row.channel))


def _tool_visible(row: ToolRow) -> bool:
    return bool(
        row.unique_starts
        or row.unique_completions
        or row.raw_completions
        or row.cta_views
        or row.cta_clicks
        or row.registrations
        or row.pro_uses
        or row.checkouts
        or row.subscriptions
    )


def _step(label: str, eligible: dict, reached: dict) -> FunnelStep:
    eligible_n = len(eligible)
    reached_n = len(reached)
    return FunnelStep(
        label=label,
        eligible=eligible_n,
        reached=reached_n,
        dropoff=max(eligible_n - reached_n, 0),
        rate=funnel_rate(reached_n, eligible_n),
    )


def _view_follows(complete: AnalyticsEvent, view: AnalyticsEvent) -> bool:
    return view.event_name == "pro_cta_view" and view.source == complete.tool


def _click_follows(view: AnalyticsEvent, click: AnalyticsEvent) -> bool:
    if click.event_name != "pro_cta_click":
        return False
    if not view.source and not view.target:
        return False
    if view.source != click.source or view.target != click.target:
        return False
    if view.cta_placement and click.cta_placement and view.cta_placement != click.cta_placement:
        return False
    return True


def _registration_start_follows(click: AnalyticsEvent, reg: AnalyticsEvent) -> bool:
    if reg.event_name != "registration_start":
        return False
    if not reg.source and not reg.target:
        return False
    if reg.source and reg.source != click.source:
        return False
    if reg.target and reg.target != click.target:
        return False
    return True


def _registration_complete_follows(start: AnalyticsEvent, done: AnalyticsEvent) -> bool:
    if done.event_name != "registration_complete":
        return False
    if start.source and done.source and start.source != done.source:
        return False
    if start.target and done.target and start.target != done.target:
        return False
    return True


def _pro_follows(reg: AnalyticsEvent, pro: AnalyticsEvent) -> bool:
    return (
        pro.event_name == "pro_tool_use"
        and bool(reg.target)
        and reg.target in PRO_TOOLS
        and pro.tool == reg.target
    )


def _checkout_follows(pro: AnalyticsEvent, checkout: AnalyticsEvent) -> bool:
    return checkout.event_name == "checkout_start"


def _subscription_follows(earlier: AnalyticsEvent, paid: AnalyticsEvent) -> bool:
    return paid.event_name == "subscription_active"


def _journey(row: AnalyticsEvent) -> str | None:
    if row.anonymous_session_id:
        return f"s:{row.anonymous_session_id}"
    if row.user_id is not None:
        return f"u:{row.user_id}"
    return None


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _event_day(occurred_at: datetime) -> date:
    return _aware(occurred_at).astimezone(LONDON).date()


def _channel_header() -> str:
    return (
        "Channel | Unique landing journeys | Unique free-calculation journeys | Raw completed calculations | "
        "CTA views | CTA clicks | Registration starts | Registrations completed | Successful Pro activations | "
        "Checkout starts | Active subscriptions | CTA click conversion | Registration conversion"
    )


def _channel_lines(rows: list[ChannelRow]) -> list[str]:
    if not rows:
        return ["No journeys in this period."]
    lines = []
    for row in rows:
        lines.append(
            f"{row.channel} | {row.landing_journeys} | {row.calculation_journeys} | {row.raw_completions} | "
            f"{row.cta_views} | {row.cta_clicks} | {row.registration_starts} | {row.registrations} | "
            f"{row.pro_uses} | {row.checkouts} | {row.subscriptions} | {row.click_rate} | {row.registration_rate}"
        )
    return lines


def _notes() -> list[str]:
    return [
        "Unique starts are distinct journeys with a calculator_start. Unique completing journeys are distinct journeys with a calculator_complete. The unique completion rate is completing journeys that had an earlier start for the same calculator, divided by unique starts, inside 7 days. It cannot exceed 100%.",
        "Raw completions are stored calculator_complete rows. Repeats closer than 15 seconds were not stored. Starts closer than 30 minutes for the same session and calculator were not stored. Those windows are duplicate suppression, not the conversion window.",
        "The sequenced funnel does not divide unrelated totals. Denominators below 5 journeys, including zero, are insufficient data.",
        "CTA pathway rows include unmapped source, unmapped target and other CTA placement. Their views and clicks sum to the headline totals.",
        "First-touch is stored once. Latest-touch updates on a new UTM campaign or a new external referrer. Rows captured before this split stay unknown and are not guessed.",
        "A channel is direct only when capture ran and there was no campaign and no external referrer. Missing capture is unknown. Referrer privacy features can hide organic and referral visits, so some of them appear direct.",
        "Search queries are not read from the referrer. Google Search Console is a separate export.",
        "subscription_active is written only when a verified Stripe subscription status is active. The checkout success page does not count. A second confirmation for the same user is not stored again.",
        "Internal and test activity is excluded when the signed-in email is in ANALYTICS_ADMIN_EMAILS or ANALYTICS_INTERNAL_EMAILS. The flag is set on the server. Historical rows are not relabelled.",
        "Engineering calculation inputs and outputs are not stored. Full referring URLs are not stored.",
        "Week-on-week percentages use the unrounded counts. A zero baseline is shown as new this period or no comparable baseline, not as infinity. A period that includes the current London day is not compared.",
    ]


def _observations(report: Report) -> list[str]:
    lines: list[str] = []
    if report.quality_warnings:
        lines.append("CTA totals did not reconcile. See the data-quality section before acting on pathway rows.")
    if report.calculators:
        top = max(report.calculators, key=lambda row: row.raw_completions)
        if top.raw_completions:
            lines.append(f"{top.tool.replace('_', ' ')} recorded {top.raw_completions} completed free calculations.")
    if report.comparison_note:
        lines.append(report.comparison_note)
    return lines


def _save_run(
    start: date,
    end: date,
    *,
    kind: str,
    status: str,
    detail: str,
    weekly_key: str | None,
    message_id: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    try:
        db.session.add(AnalyticsReportRun(
            period_start=start,
            period_end=end,
            kind=kind,
            status=status,
            weekly_key=weekly_key,
            sent_at=now if status == "sent" else None,
            started_at=now,
            completed_at=now,
            attempt_count=1,
            provider_message_id=message_id,
            detail=(detail or "")[:200],
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
