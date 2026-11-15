"""Unit tests for Stripe Checkout trial eligibility and status mapping."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.access import TRIAL_DAYS, _entitlement_for_user
from app.stripe_billing import (
    StripeNotConfiguredError,
    create_checkout_session,
    has_open_stripe_subscription,
    is_eligible_for_checkout_trial,
    map_stripe_subscription_status,
    resolve_price_id,
)


def _user(**kwargs):
    defaults = dict(
        trial_started_at=None,
        subscription_status="none",
        stripe_customer_id=None,
        stripe_subscription_id=None,
        stripe_trial_end=None,
        stripe_current_period_end=None,
        cancel_at_period_end=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_map_stripe_keeps_trialing_distinct_from_active():
    assert map_stripe_subscription_status("trialing") == "trialing"
    assert map_stripe_subscription_status("active") == "active"
    assert map_stripe_subscription_status("past_due") == "past_due"
    assert map_stripe_subscription_status("unpaid") == "unpaid"
    assert map_stripe_subscription_status("incomplete") == "incomplete"


def test_new_user_is_eligible_for_checkout_trial():
    user = _user()
    assert is_eligible_for_checkout_trial(user) is True
    assert has_open_stripe_subscription(user) is False


def test_previous_trial_user_not_eligible():
    user = _user(trial_started_at=date.today() - timedelta(days=30))
    assert is_eligible_for_checkout_trial(user) is False


def test_active_subscriber_not_eligible_and_has_open_sub():
    user = _user(
        subscription_status="active",
        stripe_customer_id="cus_x",
        stripe_subscription_id="sub_x",
        trial_started_at=date.today() - timedelta(days=40),
    )
    assert is_eligible_for_checkout_trial(user) is False
    assert has_open_stripe_subscription(user) is True


def test_stripe_trialing_grants_suite_access():
    end = datetime.now(timezone.utc) + timedelta(days=10)
    user = _user(
        subscription_status="trialing",
        stripe_subscription_id="sub_t",
        trial_started_at=date.today(),
        stripe_trial_end=end,
    )
    ent = _entitlement_for_user(user)
    assert ent.tier == "trial"
    assert ent.has_suite_access is True
    assert ent.trial_ends == end.date()


def test_legacy_app_trial_without_stripe_still_works():
    user = _user(
        subscription_status="trialing",
        trial_started_at=date.today(),
        stripe_subscription_id=None,
    )
    ent = _entitlement_for_user(user)
    assert ent.tier == "trial"
    assert ent.has_suite_access is True


def test_past_due_keeps_suite_with_billing_issue():
    user = _user(
        subscription_status="past_due",
        stripe_subscription_id="sub_x",
        trial_started_at=date.today() - timedelta(days=20),
    )
    ent = _entitlement_for_user(user)
    assert ent.tier == "pro"
    assert ent.has_suite_access is True
    assert ent.billing_issue is True


def test_subscribe_page_shows_trial_cta(app):
    app.config["REGISTRATION_OPEN"] = True
    app.config["STRIPE_SECRET_KEY"] = "sk_test_x"
    html = app.test_client().get("/subscribe").get_data(as_text=True)
    assert "Start your 14-day free trial" in html
    assert "Cancel before the trial ends" in html


def test_resolve_price_id_requires_existing_monthly_price(app):
    app.config["STRIPE_PRICE_ID"] = ""
    with app.app_context():
        with pytest.raises(StripeNotConfiguredError, match="STRIPE_PRICE_ID"):
            resolve_price_id("monthly")


def test_checkout_session_uses_existing_price_and_trial(app):
    app.config["STRIPE_SECRET_KEY"] = "sk_test_x"
    app.config["STRIPE_PRICE_ID"] = "price_live_monthly_450"
    app.config["STRIPE_MANAGED_PAYMENTS"] = True

    user = _user(id=42, email="trial@example.com", stripe_customer_id="cus_existing")
    captured: dict = {}

    fake_session = {"url": "https://checkout.stripe.test/session"}
    fake_client = MagicMock()
    fake_client.v1.checkout.sessions.create.side_effect = (
        lambda params, options=None: captured.update(params=params, options=options)
        or fake_session
    )

    with app.app_context():
        with patch("app.stripe_billing._client", return_value=fake_client):
            url = create_checkout_session(
                user=user,
                success_url="https://app.test/success?session_id={CHECKOUT_SESSION_ID}",
                cancel_url="https://app.test/subscribe?cancelled=1",
                plan="monthly",
            )

    assert url.startswith("https://checkout.stripe.test/")
    params = captured["params"]
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": "price_live_monthly_450", "quantity": 1}]
    assert params["customer"] == "cus_existing"
    assert params["client_reference_id"] == "42"
    assert params["payment_method_collection"] == "always"
    assert params["subscription_data"]["trial_period_days"] == TRIAL_DAYS
    assert params["managed_payments"] == {"enabled": True}
    fake_client.v1.products.create.assert_not_called()


def test_checkout_session_omits_trial_for_previous_trial_user(app):
    app.config["STRIPE_SECRET_KEY"] = "sk_test_x"
    app.config["STRIPE_PRICE_ID"] = "price_live_monthly_450"

    user = _user(
        id=7,
        email="returning@example.com",
        stripe_customer_id="cus_old",
        trial_started_at=date.today() - timedelta(days=40),
    )
    captured: dict = {}
    fake_client = MagicMock()
    fake_client.v1.checkout.sessions.create.side_effect = (
        lambda params, options=None: captured.update(params=params) or {"url": "https://c.test"}
    )

    with app.app_context():
        with patch("app.stripe_billing._client", return_value=fake_client):
            create_checkout_session(
                user=user,
                success_url="https://app.test/ok",
                cancel_url="https://app.test/cancel",
                plan="monthly",
            )

    assert "trial_period_days" not in captured["params"]["subscription_data"]
    assert captured["params"]["line_items"][0]["price"] == "price_live_monthly_450"
