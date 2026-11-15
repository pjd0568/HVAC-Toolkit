"""Billing — pricing page, Managed Payments Checkout, portal, and Stripe webhooks."""

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

from app.access import PRICE_MONTHLY_GBP, TRIAL_DAYS
from app.stripe_billing import (
    StripeNotConfiguredError,
    checkout_ready,
    claim_stripe_event,
    construct_webhook_event,
    create_billing_portal_session,
    create_checkout_session,
    handle_checkout_session_completed,
    handle_invoice_event,
    handle_subscription_event,
    has_open_stripe_subscription,
    is_eligible_for_checkout_trial,
    normalise_checkout_plan,
    retrieve_checkout_session,
    stripe_configured,
    _field,
    _ts_to_dt,
)

bp = Blueprint("billing", __name__)
logger = logging.getLogger(__name__)


def _annual_checkout_ready() -> bool:
    return bool((current_app.config.get("STRIPE_PRICE_ID_ANNUAL") or "").strip())


def _checkout_success_url() -> str:
    # Stripe replaces the literal placeholder with the completed session id.
    return (
        url_for("billing.checkout_success", _external=True)
        + "?session_id={CHECKOUT_SESSION_ID}"
    )


def _checkout_cancel_url() -> str:
    return url_for("billing.subscribe", cancelled=1, _external=True)


@bp.get("/subscribe")
def subscribe():
    """Pricing page — CTA starts Checkout when Stripe is configured."""
    if request.args.get("cancelled") == "1" and current_user.is_authenticated:
        from app.analytics import note_checkout_cancelled

        note_checkout_cancelled(current_user.id)

    if (
        request.args.get("checkout") == "1"
        and current_user.is_authenticated
        and stripe_configured()
    ):
        if has_open_stripe_subscription(current_user):
            flash(
                "Your Pro trial or subscription is already active. "
                "Manage billing from Account.",
                "info",
            )
            return redirect(url_for("billing.account"))
        return _start_checkout(plan=normalise_checkout_plan(request.args.get("plan")))

    trial_eligible = False
    if current_user.is_authenticated:
        trial_eligible = is_eligible_for_checkout_trial(current_user)

    return render_template(
        "marketing/subscribe.html",
        stripe_ready=checkout_ready() and stripe_configured(),
        annual_ready=_annual_checkout_ready(),
        trial_eligible=trial_eligible,
        checkout_cancelled=request.args.get("cancelled") == "1",
        trial_days=TRIAL_DAYS,
    )


@bp.get("/subscribe/success")
@login_required
def checkout_success():
    """Confirm Checkout via Stripe session retrieval — not the URL alone."""
    session_id = (request.args.get("session_id") or "").strip()
    trial_end = None
    status = None
    confirmed = False

    if session_id and stripe_configured():
        try:
            session = retrieve_checkout_session(session_id)
            ref = str(_field(session, "client_reference_id") or "")
            meta = _field(session, "metadata") or {}
            meta_uid = (
                str(meta.get("user_id"))
                if isinstance(meta, dict)
                else str(_field(meta, "user_id") or "")
            )
            if ref == str(current_user.id) or meta_uid == str(current_user.id):
                confirmed = True
                subscription = _field(session, "subscription")
                if isinstance(subscription, str) or subscription is None:
                    # Expand may still leave an id; prefer local user state after webhook.
                    pass
                else:
                    status = _field(subscription, "status")
                    trial_end = _ts_to_dt(_field(subscription, "trial_end"))
        except (StripeNotConfiguredError, stripe.StripeError):
            logger.exception("Could not retrieve Checkout Session %s", session_id)

    # Prefer authoritative local state once webhooks have landed.
    local_status = (current_user.subscription_status or "").lower()
    if local_status in ("trialing", "active", "past_due"):
        confirmed = True
        status = local_status
        trial_end = current_user.stripe_trial_end

    return render_template(
        "marketing/checkout_success.html",
        confirmed=confirmed,
        status=status or local_status,
        trial_end=trial_end,
        price_monthly=PRICE_MONTHLY_GBP,
        trial_days=TRIAL_DAYS,
        has_portal=bool(current_user.stripe_customer_id),
    )


@bp.get("/account/billing")
@login_required
def account():
    """Account billing summary + Customer Portal entry."""
    return render_template(
        "marketing/account_billing.html",
        trial_days=TRIAL_DAYS,
        price_monthly=PRICE_MONTHLY_GBP,
        portal_ready=bool(current_user.stripe_customer_id and stripe_configured()),
    )


@bp.post("/create-checkout-session")
@login_required
def create_checkout_session_route():
    """Create a Managed Payments Checkout Session and redirect to Stripe."""
    plan = normalise_checkout_plan(
        request.form.get("plan") or request.args.get("plan")
    )
    return _start_checkout(plan=plan)


@bp.post("/create-portal-session")
@login_required
def create_portal_session_route():
    """Open Stripe Customer Portal for the logged-in user's Stripe customer."""
    if not stripe_configured():
        flash("Billing management is temporarily unavailable.", "error")
        return redirect(url_for("billing.account"))
    if not current_user.stripe_customer_id:
        flash(
            "No Stripe billing profile is linked yet. Start a trial or subscribe first.",
            "error",
        )
        return redirect(url_for("billing.subscribe"))

    return_url = url_for("billing.account", _external=True)
    try:
        portal_url = create_billing_portal_session(
            user=current_user,
            return_url=return_url,
        )
    except StripeNotConfiguredError as exc:
        flash(str(exc), "error")
        return redirect(url_for("billing.account"))
    except stripe.StripeError:
        logger.exception("Stripe Customer Portal session create failed")
        flash(
            "Could not open billing management. Try again or contact us.",
            "error",
        )
        return redirect(url_for("billing.account"))

    return redirect(portal_url, code=303)


def _start_checkout(*, plan: str):
    """Shared Checkout start for POST and ``?checkout=1`` deep links."""
    if not stripe_configured():
        logger.error("Checkout requested but Stripe is not configured")
        flash(
            "Online checkout is temporarily unavailable. Please contact us.",
            "error",
        )
        return redirect(url_for("billing.subscribe"))

    if has_open_stripe_subscription(current_user):
        flash("Your Pro trial or subscription is already active.", "info")
        return redirect(url_for("billing.account"))

    chosen = normalise_checkout_plan(plan)
    if chosen == "annual" and not _annual_checkout_ready():
        flash(
            "The annual plan is temporarily unavailable. Please choose monthly "
            "or contact us.",
            "error",
        )
        return redirect(url_for("billing.subscribe"))

    try:
        checkout_url = create_checkout_session(
            user=current_user,
            success_url=_checkout_success_url(),
            cancel_url=_checkout_cancel_url(),
            plan=chosen,
        )
    except StripeNotConfiguredError:
        logger.exception("Checkout not configured")
        flash(
            "Online checkout is temporarily unavailable. Please contact us.",
            "error",
        )
        return redirect(url_for("billing.subscribe"))
    except stripe.StripeError:
        logger.exception("Stripe Checkout Session create failed")
        flash(
            "Could not start checkout. Check Stripe keys, Managed Payments "
            "terms acceptance, and that your product tax code is eligible.",
            "error",
        )
        return redirect(url_for("billing.subscribe"))

    from app.analytics import track

    track("checkout_start", route="/create-checkout-session")
    return redirect(checkout_url, code=303)


@bp.post("/webhooks/stripe")
def stripe_webhook():
    """Receive Stripe events — Checkout, subscription lifecycle, invoices."""
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

    event_id = event.get("id") if isinstance(event, dict) else _field(event, "id")
    event_type = event["type"] if isinstance(event, dict) else _field(event, "type")
    data_object = (
        event["data"]["object"]
        if isinstance(event, dict)
        else _field(_field(event, "data"), "object")
    )

    if event_id and not claim_stripe_event(str(event_id), str(event_type or "")):
        logger.info("Ignoring duplicate Stripe event %s", event_id)
        return {"received": True, "duplicate": True}, 200

    try:
        if event_type in (
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        ):
            handle_checkout_session_completed(data_object)
        elif event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            handle_subscription_event(data_object)
        elif event_type == "invoice.paid":
            handle_invoice_event(data_object, paid=True)
        elif event_type == "invoice.payment_failed":
            handle_invoice_event(data_object, paid=False)
        else:
            logger.debug("Ignoring Stripe event %s", event_type)
    except Exception:
        logger.exception("Error handling Stripe event %s", event_type)
        return {"error": "handler failed"}, 500

    return {"received": True}, 200
