"""Stripe subscription status → User.subscription_status mapping."""

from app.stripe_billing import (
    map_stripe_subscription_status,
    normalise_checkout_plan,
    status_grants_suite_access,
)


def test_map_stripe_subscription_status_known_values():
    assert map_stripe_subscription_status("active") == "active"
    assert map_stripe_subscription_status("trialing") == "trialing"
    assert map_stripe_subscription_status("past_due") == "past_due"
    assert map_stripe_subscription_status("canceled") == "canceled"
    assert map_stripe_subscription_status("unpaid") == "unpaid"
    assert map_stripe_subscription_status("incomplete") == "incomplete"
    assert map_stripe_subscription_status("incomplete_expired") == "canceled"
    assert map_stripe_subscription_status("paused") == "canceled"


def test_map_stripe_subscription_status_unknown_defaults_canceled():
    assert map_stripe_subscription_status(None) == "canceled"
    assert map_stripe_subscription_status("") == "canceled"
    assert map_stripe_subscription_status("something_new") == "canceled"


def test_map_stripe_subscription_status_is_case_insensitive():
    assert map_stripe_subscription_status("ACTIVE") == "active"
    assert map_stripe_subscription_status("Past_Due") == "past_due"
    assert map_stripe_subscription_status("TRIALING") == "trialing"


def test_status_grants_suite_access():
    assert status_grants_suite_access("active")
    assert status_grants_suite_access("trialing")
    assert status_grants_suite_access("past_due")
    assert not status_grants_suite_access("canceled")
    assert not status_grants_suite_access("unpaid")
    assert not status_grants_suite_access("incomplete")


def test_normalise_checkout_plan():
    assert normalise_checkout_plan("monthly") == "monthly"
    assert normalise_checkout_plan("ANNUAL") == "annual"
    assert normalise_checkout_plan("") == "monthly"
    assert normalise_checkout_plan("weekly") == "monthly"
