"""Stripe Managed Payments helpers for the full-suite subscription.

Creates / resolves the GBP product+price, Checkout Sessions with
``managed_payments[enabled]``, optional 14-day Stripe trials (card collected
up front), Customer Portal sessions, and maps webhook events onto ``User``
rows.

API keys and Price IDs come from env (see Config / .env.example). Product
creation uses the Managed Payments–eligible digital tax code ``txcd_10103100``.
Monthly is the default Checkout plan; annual uses ``STRIPE_PRICE_ID_ANNUAL``.

Do **not** run product creation against a live Stripe account from application
code paths except the explicit ``flask ensure-stripe-product`` CLI (dev only).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Literal

import stripe
from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.access import PRICE_MONTHLY_GBP, TRIAL_DAYS, price_unit_amount_pence
from app.extensions import db
from app.models import StripeWebhookEvent, User

logger = logging.getLogger(__name__)

CheckoutPlan = Literal["monthly", "annual"]
ALLOWED_CHECKOUT_PLANS: frozenset[str] = frozenset({"monthly", "annual"})

# Digital / SaaS tax code eligible for Managed Payments (blueprint + Stripe docs).
MANAGED_PAYMENTS_TAX_CODE = "txcd_10103100"
# Preview API version required by the Managed Payments blueprint for product + Checkout.
STRIPE_MANAGED_PAYMENTS_VERSION = "2026-02-25.preview"

# Minor units follow the display price (4.50 → 450). Checkout still uses STRIPE_PRICE_ID when set.
PRICE_UNIT_AMOUNT_PENCE = price_unit_amount_pence()
PRICE_CURRENCY = "gbp"

PRODUCT_NAME = "hvac-calcs.app — Full suite"
PRODUCT_DESCRIPTION = (
    f"Full HVAC calculator suite — psychrometrics, duct and pipe sizing, "
    f"unit converter, and more. £{PRICE_MONTHLY_GBP}/month after a "
    f"{TRIAL_DAYS}-day free trial."
)

# Stripe subscription.status → our User.subscription_status
# Policy:
# - trialing / active → suite access (see access.py)
# - past_due → keep suite access while Stripe retries (grace)
# - unpaid / incomplete / canceled → no suite access
_STATUS_MAP = {
    "active": "active",
    "trialing": "trialing",
    "past_due": "past_due",
    "canceled": "canceled",
    "unpaid": "unpaid",
    "incomplete": "incomplete",
    "incomplete_expired": "canceled",
    "paused": "canceled",
}

_SUITE_STATUSES = frozenset({"active", "trialing", "past_due"})


def map_stripe_subscription_status(stripe_status: str | None) -> str:
    """Map a Stripe ``subscription.status`` string to our ``User.subscription_status``."""
    status = (stripe_status or "").lower()
    return _STATUS_MAP.get(status, "canceled")


def status_grants_suite_access(status: str | None) -> bool:
    return (status or "").lower() in _SUITE_STATUSES


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


def _ts_to_dt(value: Any) -> datetime | None:
    """Convert a Stripe unix timestamp to an aware UTC datetime."""
    if value is None or value == "":
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def stripe_configured() -> bool:
    return bool(current_app.config.get("STRIPE_SECRET_KEY"))


def checkout_ready() -> bool:
    """True when a Checkout Session can be started (secret key present)."""
    return stripe_configured()


def _client() -> stripe.StripeClient:
    key = current_app.config.get("STRIPE_SECRET_KEY") or ""
    if not key:
        current_app.logger.error("Stripe secret key is not configured")
        raise StripeNotConfiguredError("Online checkout is temporarily unavailable.")
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


def normalise_checkout_plan(raw: object) -> CheckoutPlan:
    """Return ``monthly`` or ``annual``. Unknown values fall back to monthly."""
    text = str(raw or "").strip().lower()
    if text in ALLOWED_CHECKOUT_PLANS:
        return text  # type: ignore[return-value]
    return "monthly"


def resolve_price_id(plan: CheckoutPlan = "monthly") -> str:
    """Return the configured Stripe Price ID for ``plan``.

    Checkout never creates Products or Prices. Set ``STRIPE_PRICE_ID`` (monthly
    £4.50) and optionally ``STRIPE_PRICE_ID_ANNUAL`` in the environment. The
    ``flask ensure-stripe-product`` CLI remains a separate, explicit local-only
    helper and is not called from Checkout.
    """
    if plan == "annual":
        configured = (current_app.config.get("STRIPE_PRICE_ID_ANNUAL") or "").strip()
        if not configured:
            raise StripeNotConfiguredError(
                "Annual checkout is not configured (STRIPE_PRICE_ID_ANNUAL)."
            )
        return configured

    configured = (current_app.config.get("STRIPE_PRICE_ID") or "").strip()
    if configured:
        return configured
    raise StripeNotConfiguredError(
        "Monthly checkout is not configured (STRIPE_PRICE_ID). "
        "Use the existing live £4.50/month Price ID — do not auto-create."
    )


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


def has_open_stripe_subscription(user: User) -> bool:
    """True when the user already has a Stripe-backed suite subscription."""
    status = (user.subscription_status or "").lower()
    if status in _SUITE_STATUSES and user.stripe_subscription_id:
        return True
    if status == "active" and user.stripe_customer_id:
        # Paid subscriber even if subscription id was cleared unexpectedly.
        return True
    return False


def is_eligible_for_checkout_trial(user: User) -> bool:
    """Whether Checkout may attach ``trial_period_days``.

    Rules (server-side, not cookies):
    - Active / open Stripe subscription → not a new trial (caller should block Checkout).
    - ``trial_started_at`` already set (legacy app trial or prior Stripe trial) → paid only.
    - Prior ``stripe_subscription_id`` → paid only (no second free trial).
    - Brand-new eligible account → trial allowed.
    """
    if has_open_stripe_subscription(user):
        return False
    if user.trial_started_at is not None:
        return False
    if user.stripe_subscription_id:
        return False
    status = (user.subscription_status or "none").lower()
    if status in ("active", "past_due"):
        return False
    return True


def create_checkout_session(
    *,
    user: User,
    success_url: str,
    cancel_url: str,
    plan: CheckoutPlan = "monthly",
) -> str:
    """Create a Managed Payments subscription Checkout Session; return its URL.

    Eligible users get a 14-day Stripe trial with a payment method collected at
    Checkout (£0 due today). Others get a normal paid subscription on the same
    recurring Price (no second free trial).
    """
    if has_open_stripe_subscription(user):
        raise StripeNotConfiguredError(
            "An active subscription or trial is already on this account."
        )

    client = _client()
    chosen = normalise_checkout_plan(plan)
    price_id = resolve_price_id(chosen)
    customer_id = ensure_stripe_customer(user)
    with_trial = is_eligible_for_checkout_trial(user) and chosen == "monthly"

    subscription_data: dict[str, Any] = {
        "metadata": {
            "user_id": str(user.id),
            "plan": chosen,
            "trial": "1" if with_trial else "0",
        },
    }
    if with_trial:
        subscription_data["trial_period_days"] = TRIAL_DAYS

    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer": customer_id,
        "client_reference_id": str(user.id),
        "metadata": {
            "user_id": str(user.id),
            "plan": chosen,
            "trial": "1" if with_trial else "0",
        },
        "subscription_data": subscription_data,
        # Always collect a payment method so the first post-trial invoice can bill.
        "payment_method_collection": "always",
    }
    if current_app.config.get("STRIPE_MANAGED_PAYMENTS", True):
        params["managed_payments"] = {"enabled": True}

    session = client.v1.checkout.sessions.create(params, options=_request_options())
    url = _field(session, "url")
    if not url:
        raise RuntimeError("Stripe Checkout Session missing url")
    return str(url)


def create_billing_portal_session(*, user: User, return_url: str) -> str:
    """Create a Stripe Customer Portal session for the logged-in user."""
    if not user.stripe_customer_id:
        raise StripeNotConfiguredError(
            "No Stripe customer is linked to this account yet."
        )
    client = _client()
    session = client.v1.billing_portal.sessions.create(
        {
            "customer": user.stripe_customer_id,
            "return_url": return_url,
        },
        options=_request_options(),
    )
    url = _field(session, "url")
    if not url:
        raise RuntimeError("Stripe Customer Portal session missing url")
    return str(url)


def retrieve_checkout_session(session_id: str) -> Any:
    """Fetch a Checkout Session (success-page confirmation)."""
    client = _client()
    return client.v1.checkout.sessions.retrieve(
        session_id,
        params={"expand": ["subscription"]},
        options=_request_options(),
    )


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
    mapped = map_stripe_subscription_status(_field(subscription, "status"))
    user.subscription_status = mapped
    sub_id = _field(subscription, "id")
    if sub_id:
        user.stripe_subscription_id = sub_id
    customer_id = _id_of(_field(subscription, "customer"))
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = customer_id

    trial_end = _ts_to_dt(_field(subscription, "trial_end"))
    user.stripe_trial_end = trial_end
    user.stripe_current_period_end = _ts_to_dt(
        _field(subscription, "current_period_end")
    )
    user.cancel_at_period_end = bool(_field(subscription, "cancel_at_period_end") or False)

    # Mark trial use so Checkout cannot grant another free trial later.
    stripe_status = (_field(subscription, "status") or "").lower()
    if stripe_status == "trialing" or trial_end is not None:
        if user.trial_started_at is None:
            user.trial_started_at = date.today()


def claim_stripe_event(event_id: str, event_type: str) -> bool:
    """Return True if this event id is new and claimed; False if already processed."""
    if not event_id:
        return True
    row = StripeWebhookEvent(event_id=event_id, event_type=event_type or "")
    db.session.add(row)
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def handle_checkout_session_completed(session: Any) -> None:
    """Fulfill ``checkout.session.completed`` from the related subscription."""
    from app.lifecycle_mail import notify_subscription_status_change

    user = _find_user_for_session(session)
    if user is None:
        logger.error(
            "checkout.session.completed: no user for session %s",
            _field(session, "id"),
        )
        return

    previous_status = user.subscription_status or ""

    customer_id = _id_of(_field(session, "customer"))
    if customer_id:
        user.stripe_customer_id = customer_id

    subscription_id = _id_of(_field(session, "subscription"))
    subscription = None

    if subscription_id:
        client = _client()
        subscription = client.v1.subscriptions.retrieve(
            str(subscription_id),
            params=None,
            options=_request_options(),
        )
        _apply_subscription_to_user(user, subscription)
    else:
        # Do not grant permanent Pro from a session without a subscription.
        logger.warning(
            "checkout.session.completed %s has no subscription; leaving status=%s",
            _field(session, "id"),
            user.subscription_status,
        )
        db.session.commit()
        return

    db.session.commit()
    notify_subscription_status_change(user, previous_status)
    _record_billing_analytics(user, previous_status, subscription)
    logger.info(
        "Synced suite for user %s (status=%s, sub=%s)",
        user.id,
        user.subscription_status,
        user.stripe_subscription_id,
    )


def handle_subscription_event(subscription: Any) -> None:
    """Sync ``customer.subscription.*`` into the matching User row."""
    from app.lifecycle_mail import notify_subscription_status_change

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

    previous_status = user.subscription_status or ""
    previous_cancel = bool(user.cancel_at_period_end)
    _apply_subscription_to_user(user, subscription)
    db.session.commit()
    notify_subscription_status_change(user, previous_status)
    _record_billing_analytics(
        user,
        previous_status,
        subscription,
        previous_cancel_at_period_end=previous_cancel,
    )


def handle_invoice_event(invoice: Any, *, paid: bool) -> None:
    """Handle ``invoice.paid`` / ``invoice.payment_failed`` lightly."""
    from app.analytics import note_invoice_payment_failed, note_confirmed_subscription

    customer_id = _id_of(_field(invoice, "customer"))
    user = (
        User.query.filter_by(stripe_customer_id=customer_id).first()
        if customer_id
        else None
    )
    if user is None:
        return

    if not paid:
        note_invoice_payment_failed(user.id)
        # Keep access policy in sync if Stripe already flipped the subscription;
        # otherwise leave status until the subscription webhook arrives.
        return

    billing_reason = (_field(invoice, "billing_reason") or "").lower()
    if billing_reason in ("subscription_cycle", "subscription_update", "subscription_create"):
        # First successful paid invoice after trial → confirm paid analytics.
        if (user.subscription_status or "").lower() == "active":
            note_confirmed_subscription(user.id, "active")


def _record_billing_analytics(
    user: User,
    previous_status: str,
    subscription: Any,
    *,
    previous_cancel_at_period_end: bool = False,
) -> None:
    from app.analytics import (
        note_confirmed_subscription,
        note_subscription_cancel_scheduled,
        note_subscription_cancelled,
        note_trial_started,
    )

    stripe_status = (_field(subscription, "status") or "").lower()
    previous = (previous_status or "").lower()
    current = (user.subscription_status or "").lower()

    if current == "trialing" and previous != "trialing":
        note_trial_started(user.id)
    note_confirmed_subscription(user.id, stripe_status)

    if user.cancel_at_period_end and not previous_cancel_at_period_end:
        note_subscription_cancel_scheduled(user.id)
    if previous in _SUITE_STATUSES and current in ("canceled", "unpaid"):
        note_subscription_cancelled(user.id)


def construct_webhook_event(payload: bytes, sig_header: str | None) -> stripe.Event:
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET") or ""
    if not secret:
        raise StripeNotConfiguredError(
            "STRIPE_WEBHOOK_SECRET is not set. Use the signing secret from "
            "the Stripe Dashboard webhook endpoint (or stripe listen)."
        )
    return stripe.Webhook.construct_event(payload, sig_header, secret)
