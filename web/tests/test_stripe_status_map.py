"""Billing status mapping — no Stripe network required."""

from app.stripe_billing import map_stripe_subscription_status


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
