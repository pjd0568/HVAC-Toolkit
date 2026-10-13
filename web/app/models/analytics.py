"""Product-analytics rows. No calculation inputs and no email addresses."""

from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalyticsEvent(db.Model):
    __tablename__ = "analytics_events"

    id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(40), nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    anonymous_session_id = db.Column(db.String(64), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tool = db.Column(db.String(40), nullable=True)
    category = db.Column(db.String(32), nullable=True)
    source = db.Column(db.String(40), nullable=True)
    target = db.Column(db.String(40), nullable=True)
    route = db.Column(db.String(200), nullable=True)
    access_state = db.Column(db.String(16), nullable=True)
    unit_system = db.Column(db.String(8), nullable=True)
    utm_source = db.Column(db.String(64), nullable=True)
    utm_medium = db.Column(db.String(64), nullable=True)
    utm_campaign = db.Column(db.String(80), nullable=True)
    utm_content = db.Column(db.String(80), nullable=True)

    __table_args__ = (
        db.Index("ix_analytics_events_occurred_at", "occurred_at"),
        db.Index("ix_analytics_events_name_time", "event_name", "occurred_at"),
        db.Index("ix_analytics_events_tool_name", "tool", "event_name"),
        db.Index("ix_analytics_events_session", "anonymous_session_id"),
        db.Index("ix_analytics_events_user", "user_id"),
        db.Index("ix_analytics_events_utm_campaign", "utm_campaign"),
        db.Index("ix_analytics_events_utm_source", "utm_source"),
    )


class AnalyticsReportRun(db.Model):
    """One weekly or manual report attempt. Does not store the report body."""

    __tablename__ = "analytics_report_runs"

    id = db.Column(db.Integer, primary_key=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    kind = db.Column(db.String(16), nullable=False)  # weekly | manual
    status = db.Column(db.String(16), nullable=False)  # sending | sent | failed
    weekly_key = db.Column(db.String(32), nullable=True, unique=True)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    detail = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
