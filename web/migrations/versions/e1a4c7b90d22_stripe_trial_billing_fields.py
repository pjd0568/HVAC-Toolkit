"""Stripe trial period fields and webhook idempotency

Revision ID: e1a4c7b90d22
Revises: d5b2e8c14a90
Create Date: 2026-11-15 09:20:00.000000

Adds billing period / trial-end / cancel-at-period-end on users, plus a
unique Stripe event-id table for webhook idempotency. Does not rewrite
existing subscription_status or trial_started_at (paying and legacy app
trials stay as they are).
"""
from alembic import op
import sqlalchemy as sa


revision = "e1a4c7b90d22"
down_revision = "d5b2e8c14a90"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("stripe_trial_end", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "stripe_current_period_end",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "cancel_at_period_end",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("event_id", name="uq_stripe_webhook_events_event_id"),
    )
    op.create_index(
        "ix_stripe_webhook_events_event_id",
        "stripe_webhook_events",
        ["event_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_stripe_webhook_events_event_id", table_name="stripe_webhook_events")
    op.drop_table("stripe_webhook_events")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("cancel_at_period_end")
        batch_op.drop_column("stripe_current_period_end")
        batch_op.drop_column("stripe_trial_end")
