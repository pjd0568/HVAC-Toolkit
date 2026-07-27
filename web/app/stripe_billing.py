"""Stripe Managed Payments helpers for the full-suite subscription.

Creates / resolves the £9.50 GBP monthly product+price, Checkout Sessions with
``managed_payments[enabled]``, and maps webhook events onto ``User`` rows.

API keys and Price ID come from env (see Config / .env.example). Product creation
uses the Managed Payments–eligible digital tax code ``txcd_10103100``.
"""

from __future__ import annotations

import logging
from typing import Any

import stripe
from flask import current_app

from app.access import PRICE_MONTHLY_GBP, TRIAL_DAYS
from app.extensions import db
from app.models import User

logger = logging.getLogger(__name__)

# Digital / SaaS tax code eligible for Managed Payments (blueprint + Stripe docs).
MANAGED_PAYMENTS_TAX_CODE = "txcd_10103100"
# Preview API version required by the Managed Payments blueprint for product + Checkout.
STRIPE_MANAGED_PAYMENTS_VERSION = "2026-02-25.preview"

# £9.50 → 950 pence.
PRICE_UNIT_AMOUNT_PENCE = 950
PRICE_CURRENCY = "gbp"

PRODUCT_NAME = "HVAC Toolkit — Full suite"
PRODUCT_DESCRIPTION = (
    f"Full HVAC calculator suite — psychrometrics, duct and pipe sizing, "
    f"unit converter, and more. £{PRICE_MONTHLY_GBP}/month after a "
    f"{TRIAL_DAYS}-day free trial."
)

# Stripe subscription.status → our User.subscription_status
_STATUS_MAP = {
    "active": "active",
    "trialing": "active",  # Stripe trial still unlocks the suite
    "past_due": "active",  # grace: keep access while Stripe retries
    "canceled": "canceled",
    "unpaid": "canceled",
    "incomplete": "trialing",
    "incomplete_expired": "canceled",
    "paused": "canceled",
}


class StripeNotConfiguredError(RuntimeError):
    """Raised when Stripe secret key or price id is missing."""


def _field(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from a StripeObject or dict (StripeObject has no ``.get``)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except (KeyError, TypeError):
        return default


def _id_of(value: Any) -> str | None:
    """Expand ``cus_…`` / ``sub_…`` whether Stripe returned an id or an object."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return _field(value, "id")


def stripe_configured() -> bool:
    return bool(current_app.config.get("STRIPE_SECRET_KEY"))


def checkout_ready() -> bool:
    """True when a Checkout Session can be started (secret key present)."""
    return stripe_configured()


def _client() -> stripe.StripeClient:
    key = current_app.config.get("STRIPE_SECRET_KEY") or ""
    if not key:
        raise StripeNotConfiguredError(
            "STRIPE_SECRET_KEY is not set. Copy it from the Stripe Dashboard "
            "(Test mode → Developers → API keys)."
        )
    # Leave api_version unset on the client; Managed Payments calls pass the
    # blueprint version per-request.
    return stripe.StripeClient(key)


def _request_options() -> dict[str, str]:
    return {"stripe_version": STRIPE_MANAGED_PAYMENTS_VERSION}


def create_subscription_product() -> dict[str, str]:
    """Create the Managed Payments–eligible monthly product and default price.

    Returns ``{"product_id", "price_id"}``. Prefer setting ``STRIPE_PRICE_ID``
    in the environment after the first run.
    """
    client = _client()
    product = client.v1.products.create(
        {
            "name": PRODUCT_NAME,
            "description": PRODUCT_DESCRIPTION,
            "tax_code": MANAGED_PAYMENTS_TAX_CODE,
            "default_price_data": {
                "unit_amount": PRICE_UNIT_AMOUNT_PENCE,
                "currency": PRICE_CURRENCY,
                "tax_behavior": "inclusive",
                "recurring": {"interval": "month"},
            },
            "metadata": {"app": "hvac-toolkit", "plan": "full_suite"},
        },
        options=_request_options(),
    )
    price_id = _id_of(_field(product, "default_price"))
    product_id = _field(product, "id")
    if not price_id or not product_id:
        raise RuntimeError("Stripe product created without default_price")
    return {"product_id": str(product_id), "price_id": str(price_id)}


def resolve_price_id() -> str:
    """Return configured Price ID, or create the product+price once."""
    configured = (current_app.config.get("STRIPE_PRICE_ID") or "").strip()
    if configured:
        return configured
    created = create_subscription_product()
    current_app.config["STRIPE_PRICE_ID"] = created["price_id"]
    logger.warning(
        "Created Stripe product %s / price %s — set STRIPE_PRICE_ID in env "
        "so this is not recreated on the next boot.",
        created["product_id"],
        created["price_id"],
    )
    return created["price_id"]


def ensure_stripe_customer(user: User) -> str:
    """Return an existing Stripe Customer id or create one for ``user``."""
    if user.stripe_customer_id:
        return user.stripe_customer_id

    client = _client()
    customer = client.v1.customers.create(
        {
            "email": user.email,
            "metadata": {"user_id": str(user.id)},
        },
        options=_request_options(),
    )
    user.stripe_customer_id = customer["id"]
    db.session.commit()
    return user.stripe_customer_id


def create_checkout_session(*, user: User, success_url: str, cancel_url: str) -> str:
    """Create a Managed Payments subscription Checkout Session; return its URL."""
    client = _client()
    price_id = resolve_price_id()
    customer_id = ensure_stripe_customer(user)

    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer": customer_id,
        "client_reference_id": str(user.id),
        "metadata": {"user_id": str(user.id)},
        "subscription_data": {
            "metadata": {"user_id": str(user.id)},
        },
    }
    if current_app.config.get("STRIPE_MANAGED_PAYMENTS", True):
        params["managed_payments"] = {"enabled": True}

    session = client.v1.checkout.sessions.create(params, options=_request_options())
    url = _field(session, "url")
    if not url:
        raise RuntimeError("Stripe Checkout Session missing url")
    return str(url)


def _find_user_for_session(session: Any) -> User | None:
    ref = _field(session, "client_reference_id")
    if ref and str(ref).isdigit():
        user = db.session.get(User, int(ref))
        if user is not None:
            return user

    meta = _field(session, "metadata") or {}
    uid = meta.get("user_id") if isinstance(meta, dict) else _field(meta, "user_id")
    if uid and str(uid).isdigit():
        user = db.session.get(User, int(uid))
        if user is not None:
            return user

    customer_id = _id_of(_field(session, "customer"))
    if customer_id:
        return User.query.filter_by(stripe_customer_id=customer_id).first()
    return None


def _apply_subscription_to_user(user: User, subscription: Any) -> None:
    status = (_field(subscription, "status") or "").lower()
    user.subscription_status = _STATUS_MAP.get(status, "canceled")
    sub_id = _field(subscription, "id")
    if sub_id:
        user.stripe_subscription_id = sub_id
    customer_id = _id_of(_field(subscription, "customer"))
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = customer_id


def handle_checkout_session_completed(session: Any) -> None:
    """Fulfill ``checkout.session.completed`` — unlock suite for the user."""
    user = _find_user_for_session(session)
    if user is None:
        logger.error(
            "checkout.session.completed: no user for session %s",
            _field(session, "id"),
        )
        return

    customer_id = _id_of(_field(session, "customer"))
    if customer_id:
        user.stripe_customer_id = customer_id

    subscription_id = _id_of(_field(session, "subscription"))

    if subscription_id:
        client = _client()
        subscription = client.v1.subscriptions.retrieve(
            str(subscription_id),
            params=None,
            options=_request_options(),
        )
        _apply_subscription_to_user(user, subscription)
    else:
        # Payment mode fallback — treat completed checkout as subscribed.
        user.subscription_status = "active"

    db.session.commit()
    logger.info(
        "Unlocked suite for user %s (status=%s, sub=%s)",
        user.id,
        user.subscription_status,
        user.stripe_subscription_id,
    )


def handle_subscription_event(subscription: Any) -> None:
    """Sync ``customer.subscription.*`` into the matching User row."""
    sub_id = _field(subscription, "id")
    customer_id = _id_of(_field(subscription, "customer"))

    user = None
    if sub_id:
        user = User.query.filter_by(stripe_subscription_id=sub_id).first()
    if user is None and customer_id:
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
    meta = _field(subscription, "metadata") or {}
    uid = meta.get("user_id") if isinstance(meta, dict) else _field(meta, "user_id")
    if user is None and uid and str(uid).isdigit():
        user = db.session.get(User, int(uid))

    if user is None:
        logger.warning("subscription event: no user for sub %s", sub_id)
        return

    _apply_subscription_to_user(user, subscription)
    db.session.commit()


def construct_webhook_event(payload: bytes, sig_header: str | None) -> stripe.Event:
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET") or ""
    if not secret:
        raise StripeNotConfiguredError(
            "STRIPE_WEBHOOK_SECRET is not set. Use the signing secret from "
            "the Stripe Dashboard webhook endpoint (or stripe listen)."
        )
    return stripe.Webhook.construct_event(payload, sig_header, secret)
