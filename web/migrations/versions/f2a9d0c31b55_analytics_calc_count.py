"""Add calc_count on analytics events for CTA journey context

Revision ID: f2a9d0c31b55
Revises: e1a4c7b90d22
Create Date: 2026-11-25 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f2a9d0c31b55"
down_revision = "e1a4c7b90d22"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("analytics_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("calc_count", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("analytics_events", schema=None) as batch_op:
        batch_op.drop_column("calc_count")
