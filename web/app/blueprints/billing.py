"""Billing — pricing page, Managed Payments Checkout, and Stripe webhooks."""

from __future__ import annotations

import logging

import stripe
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.stripe_billing import (
    StripeNotConfiguredError,
    checkout_ready,
    construct_webhook_event,
    create_checkout_session,
    handle_checkout_session_completed,
    handle_subscription_event,
    stripe_configured,
)

bp = Blueprint("billing", __name__)
logger = logging.getLogger(__name__)


@bp.get("/subscribe")
def subscribe():
    """Pricing page — CTA starts Checkout when Stripe is configured."""
    return render_template(
        "marketing/subscribe.html",
        stripe_ready=checkout_ready() and stripe_configured(),
    )


@bp.get("/subscribe/success")
@login_required
def checkout_success():
    flash(
        "Payment received. If your suite isn’t unlocked yet, refresh in a moment "
        "while we confirm with Stripe.",
        "success",
    )
    return redirect(url_for("main.dashboard"))


@bp.post("/create-checkout-session")
@login_required
def create_checkout_session_route():
    """Create a Managed Payments Checkout Session and redirect to Stripe."""
    if not stripe_configured():
        flash(
            "Checkout isn’t configured yet. Add STRIPE_SECRET_KEY (and "
            "STRIPE_PRICE_ID) from the Stripe Dashboard.",
            "error",
        )
        return redirect(url_for("billing.subscribe"))

    if current_user.subscription_status == "active":
        flash("Your subscription is already active.", "info")
        return redirect(url_for("main.dashboard"))

    success_url = url_for("billing.checkout_success", _external=True)
    cancel_url = url_for("billing.subscribe", _external=True)

    try:
        checkout_url = create_checkout_session(
            user=current_user,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except StripeNotConfiguredError as exc:
        flash(str(exc), "error")
        return redirect(url_for("billing.subscribe"))
    except stripe.StripeError:
        logger.exception("Stripe Checkout Session create failed")
        flash(
            "Could not start checkout. Check Stripe Test mode keys, Managed "
            "Payments terms acceptance, and that your product tax code is eligible.",
            "error",
        )
        return redirect(url_for("billing.subscribe"))

    return redirect(checkout_url, code=303)


@bp.post("/webhooks/stripe")
def stripe_webhook():
    """Receive Stripe events — primarily ``checkout.session.completed``."""
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = construct_webhook_event(payload, sig_header)
    except StripeNotConfiguredError:
        logger.exception("Webhook secret missing")
        return {"error": "webhook not configured"}, 500
    except ValueError:
        logger.warning("Invalid webhook payload")
        return {"error": "invalid payload"}, 400
    except stripe.SignatureVerificationError:
        logger.warning("Invalid webhook signature")
        return {"error": "invalid signature"}, 400

    event_type = event["type"]
    data_object = event["data"]["object"]

    try:
        if event_type in (
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        ):
            handle_checkout_session_completed(data_object)
        elif event_type in (
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            handle_subscription_event(data_object)
        else:
            logger.debug("Ignoring Stripe event %s", event_type)
    except Exception:
        logger.exception("Error handling Stripe event %s", event_type)
        return {"error": "handler failed"}, 500

    return {"received": True}, 200
