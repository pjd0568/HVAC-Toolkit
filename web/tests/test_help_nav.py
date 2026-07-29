"""Help nav includes Account, billing & cancel for go-live support copy."""

from app.blueprints.help import ACTIVE_TO_ANCHOR, HELP_NAV


def test_help_nav_includes_account_billing():
    getting_started = HELP_NAV[0]
    assert getting_started["group"] == "Getting Started"
    ids = [s["id"] for s in getting_started["sections"]]
    assert "account-billing" in ids


def test_subscribe_active_maps_to_account_billing_help():
    assert ACTIVE_TO_ANCHOR.get("subscribe") == "account-billing"
