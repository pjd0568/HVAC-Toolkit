"""first and latest touch, CTA placement, report delivery audit

Revision ID: d5b2e8c14a90
Revises: c8d4f0a21b77
Create Date: 2026-10-31 08:00:00.000000

Historical rows keep nulls in every new column. Null attribution is unknown.
It is not backfilled.

"""
from alembic import op
import sqlalchemy as sa


revision = "d5b2e8c14a90"
down_revision = "c8d4f0a21b77"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analytics_events", sa.Column("utm_term", sa.String(length=80), nullable=True))
    op.add_column("analytics_events", sa.Column("cta_placement", sa.String(length=40), nullable=True))
    op.add_column("analytics_events", sa.Column("excluded", sa.Boolean(), nullable=True))
    op.add_column("analytics_events", sa.Column("first_captured", sa.Boolean(), nullable=True))
    op.add_column("analytics_events", sa.Column("latest_captured", sa.Boolean(), nullable=True))
    op.add_column("analytics_events", sa.Column("first_utm_source", sa.String(length=64), nullable=True))
    op.add_column("analytics_events", sa.Column("first_utm_medium", sa.String(length=64), nullable=True))
    op.add_column("analytics_events", sa.Column("first_utm_campaign", sa.String(length=80), nullable=True))
    op.add_column("analytics_events", sa.Column("first_utm_content", sa.String(length=80), nullable=True))
    op.add_column("analytics_events", sa.Column("first_utm_term", sa.String(length=80), nullable=True))
    op.add_column("analytics_events", sa.Column("first_landing_path", sa.String(length=200), nullable=True))
    op.add_column("analytics_events", sa.Column("first_referrer_host", sa.String(length=120), nullable=True))
    op.add_column("analytics_events", sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analytics_events", sa.Column("first_channel", sa.String(length=80), nullable=True))
    op.add_column("analytics_events", sa.Column("latest_landing_path", sa.String(length=200), nullable=True))
    op.add_column("analytics_events", sa.Column("latest_referrer_host", sa.String(length=120), nullable=True))
    op.add_column("analytics_events", sa.Column("latest_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analytics_events", sa.Column("latest_channel", sa.String(length=80), nullable=True))

    op.add_column("analytics_report_runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analytics_report_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analytics_report_runs", sa.Column("attempt_count", sa.Integer(), nullable=True))
    op.add_column("analytics_report_runs", sa.Column("provider_message_id", sa.String(length=80), nullable=True))


def downgrade():
    op.drop_column("analytics_report_runs", "provider_message_id")
    op.drop_column("analytics_report_runs", "attempt_count")
    op.drop_column("analytics_report_runs", "completed_at")
    op.drop_column("analytics_report_runs", "started_at")
    op.drop_column("analytics_events", "latest_channel")
    op.drop_column("analytics_events", "latest_seen_at")
    op.drop_column("analytics_events", "latest_referrer_host")
    op.drop_column("analytics_events", "latest_landing_path")
    op.drop_column("analytics_events", "first_channel")
    op.drop_column("analytics_events", "first_seen_at")
    op.drop_column("analytics_events", "first_referrer_host")
    op.drop_column("analytics_events", "first_landing_path")
    op.drop_column("analytics_events", "first_utm_term")
    op.drop_column("analytics_events", "first_utm_content")
    op.drop_column("analytics_events", "first_utm_campaign")
    op.drop_column("analytics_events", "first_utm_medium")
    op.drop_column("analytics_events", "first_utm_source")
    op.drop_column("analytics_events", "latest_captured")
    op.drop_column("analytics_events", "first_captured")
    op.drop_column("analytics_events", "excluded")
    op.drop_column("analytics_events", "cta_placement")
    op.drop_column("analytics_events", "utm_term")
