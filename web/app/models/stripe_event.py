"""Idempotency ledger for Stripe webhook event ids."""

from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


class StripeWebhookEvent(db.Model):
    __tablename__ = "stripe_webhook_events"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(255), nullable=False, unique=True, index=True)
    event_type = db.Column(db.String(128), nullable=False)
    processed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
