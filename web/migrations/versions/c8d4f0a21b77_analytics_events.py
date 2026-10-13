"""analytics events and report runs

Revision ID: c8d4f0a21b77
Revises: b3c8e1a92f04
Create Date: 2026-10-13 20:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c8d4f0a21b77"
down_revision = "b3c8e1a92f04"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anonymous_session_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("tool", sa.String(length=40), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("target", sa.String(length=40), nullable=True),
        sa.Column("route", sa.String(length=200), nullable=True),
        sa.Column("access_state", sa.String(length=16), nullable=True),
        sa.Column("unit_system", sa.String(length=8), nullable=True),
        sa.Column("utm_source", sa.String(length=64), nullable=True),
        sa.Column("utm_medium", sa.String(length=64), nullable=True),
        sa.Column("utm_campaign", sa.String(length=80), nullable=True),
        sa.Column("utm_content", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analytics_events_occurred_at", "analytics_events", ["occurred_at"])
    op.create_index("ix_analytics_events_name_time", "analytics_events", ["event_name", "occurred_at"])
    op.create_index("ix_analytics_events_tool_name", "analytics_events", ["tool", "event_name"])
    op.create_index("ix_analytics_events_session", "analytics_events", ["anonymous_session_id"])
    op.create_index("ix_analytics_events_user", "analytics_events", ["user_id"])
    op.create_index("ix_analytics_events_utm_campaign", "analytics_events", ["utm_campaign"])
    op.create_index("ix_analytics_events_utm_source", "analytics_events", ["utm_source"])

    op.create_table(
        "analytics_report_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("weekly_key", sa.String(length=32), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("weekly_key"),
    )


def downgrade():
    op.drop_table("analytics_report_runs")
    op.drop_index("ix_analytics_events_utm_source", table_name="analytics_events")
    op.drop_index("ix_analytics_events_utm_campaign", table_name="analytics_events")
    op.drop_index("ix_analytics_events_user", table_name="analytics_events")
    op.drop_index("ix_analytics_events_session", table_name="analytics_events")
    op.drop_index("ix_analytics_events_tool_name", table_name="analytics_events")
    op.drop_index("ix_analytics_events_name_time", table_name="analytics_events")
    op.drop_index("ix_analytics_events_occurred_at", table_name="analytics_events")
    op.drop_table("analytics_events")
