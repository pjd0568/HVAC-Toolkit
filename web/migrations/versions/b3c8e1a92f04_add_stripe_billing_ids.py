"""add stripe customer and subscription ids

Revision ID: b3c8e1a92f04
Revises: 57a9ef2134bf
Create Date: 2026-07-27 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b3c8e1a92f04"
down_revision = "57a9ef2134bf"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_users_stripe_customer_id"),
            ["stripe_customer_id"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_users_stripe_subscription_id"),
            ["stripe_subscription_id"],
            unique=True,
        )


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_stripe_subscription_id"))
        batch_op.drop_index(batch_op.f("ix_users_stripe_customer_id"))
        batch_op.drop_column("stripe_subscription_id")
        batch_op.drop_column("stripe_customer_id")
