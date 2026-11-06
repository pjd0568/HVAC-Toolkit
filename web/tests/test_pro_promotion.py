"""Free → Pro promotion config and surfaces."""

from datetime import date, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.pro_promotion import (
    COMPARE_ROWS,
    prompt_for_free_tool,
    prompt_for_landing_slug,
    prompt_for_locked_module,
    should_show_pro_promotion,
)


@pytest.fixture
def promo_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'promo.db'}")
    monkeypatch.setenv("SECRET_KEY", "promo-test")
    application = create_app()
    application.config.update(
        TESTING=True,
        REGISTRATION_OPEN=True,
        TURNSTILE_SITE_KEY="",
        TURNSTILE_SECRET_KEY="",
        ACCESS_DEV_TIER=None,
    )
    return application


@pytest.fixture
def client(promo_app):
    return promo_app.test_client()


def test_compare_rows_omit_project_storage():
    labels = " ".join(row.feature.lower() for row in COMPARE_ROWS)
    assert "project" not in labels
    assert any(row.feature == "DX pipe sizing" and not row.free and row.pro for row in COMPARE_ROWS)


def test_free_prompts_cover_requested_tools():
    duct = prompt_for_free_tool("duct_sizing")
    assert duct is not None
    assert "index leg" in duct.heading.lower()
    pipe = prompt_for_free_tool("pipe_sizing")
    assert pipe is not None
    assert "complete system" in pipe.heading.lower()
    psy = prompt_for_free_tool("psychrometric_single")
    assert psy is not None
    assert "psychrometric chart" in psy.heading.lower()
    assert "Mixed air" in psy.processes
    assert prompt_for_free_tool("unit_converter") is None
    assert prompt_for_landing_slug("unit-converter") is None


def test_locked_module_prompts():
    leg = prompt_for_locked_module("duct.index_leg")
    assert leg is not None
    assert "Index Leg" in leg.heading
    assert prompt_for_locked_module("converter") is None


def test_suite_access_hides_promotion(promo_app):
    promo_app.config["ACCESS_DEV_TIER"] = "pro"
    try:
        with promo_app.test_request_context("/"):
            assert should_show_pro_promotion() is False
    finally:
        promo_app.config["ACCESS_DEV_TIER"] = None


def test_public_duct_result_shows_explore_pro_card(client):
    res = client.get("/tools/duct-sizing-calculator")
    html = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "Explore Pro" in html
    assert "index leg" in html.lower()
    assert "pro-upgrade-dialog" in html
    assert "pro-compare" in html
    assert "project storage" not in html.lower()


def test_converter_has_no_pro_upgrade_dialog(client):
    res = client.get("/tools/unit-converter")
    html = res.get_data(as_text=True)
    assert "pro-upgrade-dialog" not in html
    assert "data-pro-upgrade-open" not in html


def test_locked_index_leg_uses_contextual_gate(client, promo_app):
    with promo_app.app_context():
        user = User(
            email="free-gate@example.com",
            trial_started_at=date.today() - timedelta(days=30),
            subscription_status="trialing",
        )
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

    client.post("/login", data={"email": "free-gate@example.com", "password": "password123"})
    page = client.get("/v2/duct-index-leg/")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "access-gate-panel" in html
    assert "Duct Index Leg is a Pro workflow" in html
    assert "pro-compare" in html
