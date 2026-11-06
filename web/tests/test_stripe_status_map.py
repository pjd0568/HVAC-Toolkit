"""Billing status mapping — no Stripe network required."""

import pytest

from app.stripe_billing import (
    StripeNotConfiguredError,
    map_stripe_subscription_status,
    normalise_checkout_plan,
    resolve_price_id,
)


def test_map_stripe_subscription_status_known_values():
    assert map_stripe_subscription_status("active") == "active"
    assert map_stripe_subscription_status("trialing") == "active"
    assert map_stripe_subscription_status("past_due") == "active"
    assert map_stripe_subscription_status("canceled") == "canceled"
    assert map_stripe_subscription_status("unpaid") == "canceled"
    assert map_stripe_subscription_status("incomplete") == "trialing"
    assert map_stripe_subscription_status("incomplete_expired") == "canceled"
    assert map_stripe_subscription_status("paused") == "canceled"


def test_map_stripe_subscription_status_unknown_defaults_canceled():
    assert map_stripe_subscription_status(None) == "canceled"
    assert map_stripe_subscription_status("") == "canceled"
    assert map_stripe_subscription_status("something_new") == "canceled"


def test_map_stripe_subscription_status_is_case_insensitive():
    assert map_stripe_subscription_status("ACTIVE") == "active"
    assert map_stripe_subscription_status("Past_Due") == "active"


def test_normalise_checkout_plan():
    assert normalise_checkout_plan("monthly") == "monthly"
    assert normalise_checkout_plan("ANNUAL") == "annual"
    assert normalise_checkout_plan("") == "monthly"
    assert normalise_checkout_plan("weekly") == "monthly"


def test_resolve_annual_price_id(app):
    with app.app_context():
        app.config["STRIPE_PRICE_ID_ANNUAL"] = "price_annual_test"
        assert resolve_price_id("annual") == "price_annual_test"


def test_resolve_annual_price_id_requires_config(app):
    with app.app_context():
        app.config["STRIPE_PRICE_ID_ANNUAL"] = ""
        with pytest.raises(StripeNotConfiguredError):
            resolve_price_id("annual")
