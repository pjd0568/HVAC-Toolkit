"""Transactional emails — trial welcome, subscribed, cancelled + owner alerts.

Customer mail goes to the user; owner pings go to ``CONTACT_EMAIL``
(e.g. ``info@hvac-calcs.app``). Failures are logged; callers should not fail
the request if mail is down.
"""

from __future__ import annotations

import logging

from flask import current_app, url_for

from app.access import PRICE_MONTHLY_GBP, TRIAL_DAYS
from app.mail import mail_configured, send_email
from app.models import User

log = logging.getLogger(__name__)


def _brand() -> str:
    return current_app.config.get("BRAND_NAME", "hvac-calcs.app")


def _contact() -> str:
    return current_app.config.get("CONTACT_EMAIL", "info@hvac-calcs.app")


def _login_url() -> str:
    try:
        return url_for("auth.login", _external=True)
    except RuntimeError:
        base = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
        return f"{base}/login"


def _subscribe_url() -> str:
    try:
        return url_for("billing.subscribe", _external=True)
    except RuntimeError:
        base = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
        return f"{base}/subscribe"


def _dashboard_url() -> str:
    try:
        return url_for("main.dashboard", _external=True)
    except RuntimeError:
        base = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
        return f"{base}/"


def _notify_owner(*, subject: str, body: str) -> bool:
    """Ping CONTACT_EMAIL; no-op if mail unset or contact blank."""
    if not mail_configured():
        log.warning("Mail not configured; skipped owner alert: %s", subject)
        return False
    to_addr = (_contact() or "").strip()
    if not to_addr:
        return False
    return send_email(to=to_addr, subject=subject, body=body)


def send_owner_trial_started(user: User) -> bool:
    brand = _brand()
    subject = f"[Owner] New trial — {user.email}"
    body = f"""New trial account on {brand}.

Email: {user.email}
User id: {user.id}
Trial: {TRIAL_DAYS} days from today

Dashboard (after login): {_dashboard_url()}
"""
    return _notify_owner(subject=subject, body=body)


def send_owner_subscribed(user: User) -> bool:
    brand = _brand()
    subject = f"[Owner] New subscriber — {user.email}"
    body = f"""Paid subscription activated on {brand}.

Email: {user.email}
User id: {user.id}
Plan: £{PRICE_MONTHLY_GBP}/month
Stripe customer: {user.stripe_customer_id or '—'}
Stripe subscription: {user.stripe_subscription_id or '—'}
"""
    return _notify_owner(subject=subject, body=body)


def send_owner_subscription_ended(user: User) -> bool:
    brand = _brand()
    subject = f"[Owner] Subscription ended — {user.email}"
    body = f"""A paid subscription ended / cancelled on {brand}.

Email: {user.email}
User id: {user.id}
Stripe customer: {user.stripe_customer_id or '—'}
Stripe subscription: {user.stripe_subscription_id or '—'}
"""
    return _notify_owner(subject=subject, body=body)


def send_trial_started(user: User) -> bool:
    """Welcome email when a new account starts the free trial."""
    if not mail_configured():
        log.warning("Mail not configured; skipped trial welcome for user %s", user.id)
        return False

    brand = _brand()
    subject = f"Welcome to {brand} — your {TRIAL_DAYS}-day trial has started"
    body = f"""Hi,

Thanks for creating an account with {brand}.

Your {TRIAL_DAYS}-day free trial of the full calculator suite is active now.
Open the toolkit here:
{_dashboard_url()}

After the trial, continue with a subscription at £{PRICE_MONTHLY_GBP}/month:
{_subscribe_url()}

Questions? Reply to this email or write to {_contact()}.

— {brand}
"""
    ok = send_email(to=user.email, subject=subject, body=body)
    send_owner_trial_started(user)
    return ok


def send_subscribed(user: User) -> bool:
    """Thank-you email after a successful subscription payment."""
    if not mail_configured():
        log.warning("Mail not configured; skipped subscribed email for user %s", user.id)
        return False

    brand = _brand()
    subject = f"Thanks for subscribing to {brand}"
    body = f"""Hi,

Thanks for subscribing to {brand}.

Your account now has full access to the calculator suite (£{PRICE_MONTHLY_GBP}/month).
Open the toolkit:
{_dashboard_url()}

Manage billing, invoices and cancellation through the email receipts Stripe / Link
send you for this subscription (Help → Account, billing & cancel in the app).
For support, reply here or email {_contact()}.

— {brand}
"""
    ok = send_email(to=user.email, subject=subject, body=body)
    send_owner_subscribed(user)
    return ok


def send_subscription_ended(user: User) -> bool:
    """Soft farewell when a paid subscription is cancelled or ends."""
    if not mail_configured():
        log.warning("Mail not configured; skipped cancellation email for user %s", user.id)
        return False

    brand = _brand()
    subject = f"Sorry to see you go — {brand}"
    body = f"""Hi,

Your {brand} subscription has ended, so paid suite access is no longer active.

You can restart anytime from the pricing page:
{_subscribe_url()}

If you left because something didn’t work, we’d genuinely like to know —
reply to this email or contact {_contact()}.

Thanks for trying {brand}.

— {brand}
"""
    ok = send_email(to=user.email, subject=subject, body=body)
    send_owner_subscription_ended(user)
    return ok


def notify_subscription_status_change(user: User, previous_status: str) -> None:
    """Send subscribed / cancelled mail only on meaningful status transitions.

    Avoids duplicate emails when Stripe retries webhooks or sends both
    ``checkout.session.completed`` and ``customer.subscription.updated``.
    """
    previous = (previous_status or "").lower()
    current = (user.subscription_status or "").lower()

    if previous != "active" and current == "active":
        send_subscribed(user)
    elif previous == "active" and current == "canceled":
        send_subscription_ended(user)
