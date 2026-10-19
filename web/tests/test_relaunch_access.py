"""Anonymous free calculators, Pro gates, price source, and public copy."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from app.access import PRICE_MONTHLY_GBP, price_unit_amount_pence, tool_access

ROOT = Path(__file__).resolve().parents[1]
FREE_TOOLS = (
    "/tools/psychrometric-calculator",
    "/tools/duct-sizing-calculator",
    "/tools/chilled-water-pipe-sizing",
    "/tools/refrigerant-pt-table",
    "/tools/superheat-subcooling",
    "/tools/unit-converter",
)
PRO_TOOLS = (
    "/v2/psychrometrics/interactive-chart",
    "/v2/psychrometrics/mixed-air",
    "/v2/duct-index-leg/",
    "/v2/pipe-system/",
    "/v2/refrigeration/pipe-sizer/",
)


@pytest.fixture
def client(app):
    return app.test_client()


def test_price_comes_from_one_constant():
    assert PRICE_MONTHLY_GBP == "4.50"
    assert price_unit_amount_pence() == 450


def test_tool_access_is_catalogue_not_entitlement():
    assert tool_access("psychro.single_point") == "free"
    assert tool_access("duct.sizer") == "free"
    assert tool_access("psychro.mixed_air") == "pro"
    assert tool_access("duct.index_leg") == "pro"
    assert tool_access("weather") is None
    assert tool_access("room.load") is None


def test_anonymous_free_calculators(client):
    for path in FREE_TOOLS:
        res = client.get(path)
        assert res.status_code == 200, path
        body = res.get_data(as_text=True)
        assert "access-gate-panel" not in body
        assert "<form" in body


def test_anonymous_pro_workflows_are_gated(client):
    for path in PRO_TOOLS:
        res = client.get(path)
        assert res.status_code == 200, path
        assert b"access-gate-panel" in res.data


def test_anonymous_dashboard_still_requires_login(client):
    res = client.get("/v2/")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_anonymous_duct_pdf_stays_gated(client):
    res = client.post("/duct-sizing/report", data={"volume": "1"})
    assert res.status_code == 200
    assert b"%PDF" not in res.data
    assert b"access-gate-panel" in res.data


def test_subscribe_uses_config_price_and_hides_stripe_setup(client):
    res = client.get("/subscribe")
    html = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "<h1>Pricing</h1>" in html
    assert "£4.50" in html
    assert "9.50" not in html
    assert "STRIPE_SECRET_KEY" not in html
    assert "Pricing/Subscribe" not in html


def test_marketing_does_not_claim_saved_projects(client):
    html = client.get("/").get_data(as_text=True).lower()
    assert "save project files" not in html
    assert "4.50" in html
    assert "not available" in html


def test_sitemap_and_robots(client):
    sitemap = client.get("/sitemap.xml").get_data(as_text=True)
    assert "/tools/refrigerant-pt-table" in sitemap
    assert "/tools/superheat-subcooling" in sitemap
    assert "/tools/unit-converter" in sitemap
    assert "/methods" in sitemap
    assert "/v2/" not in sitemap
    robots = client.get("/robots.txt").get_data(as_text=True)
    assert "Allow: /tools/" in robots
    assert "Disallow: /v2/" in robots
    assert "Disallow: /help" in robots


def test_registration_closed_has_no_trial_cta():
    application = create_app()
    application.config.update(TESTING=True, REGISTRATION_OPEN=False, STRIPE_SECRET_KEY="")
    page = application.test_client().get("/subscribe").get_data(as_text=True)
    assert "Start free trial" not in page
    assert "Try Pro free" not in page
    assert "Online checkout is temporarily unavailable" in page


def test_legacy_tool_paths_still_resolve(client):
    res = client.get("/duct-sizing/", follow_redirects=False)
    assert res.status_code in (301, 302, 303, 307, 308)
    assert "duct" in res.headers["Location"]


def test_trial_expired_and_subscribed_gates(app):
    """Entitlement tiers use the same gate as a signed-in trial, expiry, or subscription.

    ACCESS_DEV_TIER is the app's tier override and is resolved before the user row,
    so this does not need a database.
    """
    client = app.test_client()
    path = "/v2/duct-index-leg/"

    app.config["ACCESS_DEV_TIER"] = "trial"
    trial = client.get(path)
    assert trial.status_code == 200
    assert b"access-gate-panel" not in trial.data

    app.config["ACCESS_DEV_TIER"] = "free"
    expired = client.get(path)
    assert expired.status_code == 200
    assert b"access-gate-panel" in expired.data

    app.config["ACCESS_DEV_TIER"] = "pro"
    paid = client.get(path)
    assert paid.status_code == 200
    assert b"access-gate-panel" not in paid.data

    app.config["ACCESS_DEV_TIER"] = None


def test_checkout_requires_login(client):
    res = client.post("/create-checkout-session")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_public_templates_have_no_stripe_setup_language():
    marketing = ROOT / "app" / "templates" / "marketing"
    blob = "\n".join(p.read_text() for p in marketing.glob("*.html"))
    assert "STRIPE_SECRET_KEY" not in blob
    assert "save project files" not in blob.lower()
