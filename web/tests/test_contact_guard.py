"""Contact form Turnstile, per-IP cap, and duplicate-body drop."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.contact_guard import client_ip, release, reserve


def _form(message: str, name: str = "Paul") -> dict:
    return {
        "name": name,
        "email": "paul@example.com",
        "topic": "help",
        "message": message,
    }


@pytest.fixture
def contact_app(app, tmp_path):
    app.config["CONTACT_GUARD_PATH"] = str(tmp_path / "guard.json")
    app.config["CONTACT_IP_MAX"] = 3
    app.config["CONTACT_IP_WINDOW_SEC"] = 3600
    app.config["CONTACT_BODY_WINDOW_SEC"] = 86400
    app.config["TURNSTILE_SITE_KEY"] = ""
    app.config["TURNSTILE_SECRET_KEY"] = ""
    return app


def test_reserve_caps_ip_and_drops_duplicate_body(contact_app):
    with contact_app.app_context():
        assert reserve("1.1.1.1", "First real question here", now=1_000)[0] is None
        assert reserve("2.2.2.2", "  first   REAL question here ", now=1_001)[0] == "duplicate"
        assert reserve("1.1.1.1", "Second real question here", now=1_002)[0] is None
        assert reserve("1.1.1.1", "Third real question here", now=1_003)[0] is None
        assert reserve("1.1.1.1", "Fourth real question here", now=1_004)[0] == "rate"
        # Other addresses still have their own hourly budget.
        assert reserve("2.2.2.2", "A different question entirely", now=1_005)[0] is None


def test_windows_expire(contact_app):
    with contact_app.app_context():
        contact_app.config["CONTACT_IP_MAX"] = 1
        contact_app.config["CONTACT_IP_WINDOW_SEC"] = 10
        contact_app.config["CONTACT_BODY_WINDOW_SEC"] = 100
        assert reserve("1.1.1.1", "Hello there friend", now=1_000)[0] is None
        assert reserve("1.1.1.1", "Another message now", now=1_005)[0] == "rate"
        assert reserve("1.1.1.1", "Another message now", now=1_011)[0] is None
        assert reserve("9.9.9.9", "Hello there friend", now=1_050)[0] == "duplicate"
        assert reserve("9.9.9.9", "Hello there friend", now=1_101)[0] is None


def test_failed_send_returns_the_slot(contact_app):
    with contact_app.app_context():
        reason, stamp = reserve("1.1.1.1", "Please look at this coil", now=2_000)
        assert reason is None and stamp is not None
        release("1.1.1.1", "Please look at this coil", stamp)
        assert reserve("1.1.1.1", "Please look at this coil", now=2_001)[0] is None


def test_client_ip_trusts_cloudflare_only_with_cf_ray(contact_app):
    headers = {"CF-Connecting-IP": "203.0.113.5"}
    with contact_app.test_request_context("/", headers={**headers, "CF-Ray": "abc"}):
        assert client_ip() == "203.0.113.5"
    with contact_app.test_request_context(
        "/",
        headers=headers,
        environ_base={"REMOTE_ADDR": "10.0.0.8"},
    ):
        assert client_ip() == "10.0.0.8"


def test_contact_get_omits_widget_when_turnstile_unset(contact_app):
    html = contact_app.test_client().get("/contact").get_data(as_text=True)
    assert "cf-turnstile" not in html
    assert "challenges.cloudflare.com" not in html


def test_contact_get_includes_widget_when_turnstile_set(contact_app):
    contact_app.config["TURNSTILE_SITE_KEY"] = "site-key"
    contact_app.config["TURNSTILE_SECRET_KEY"] = "secret"
    html = contact_app.test_client().get("/contact").get_data(as_text=True)
    assert 'class="cf-turnstile"' in html
    assert 'data-sitekey="site-key"' in html
    assert "challenges.cloudflare.com/turnstile/v0/api.js" in html


@patch("app.blueprints.pages.mail_configured", return_value=True)
@patch("app.blueprints.pages.send_email", return_value=True)
def test_contact_post_sends_without_turnstile_when_unset(mock_send, _mail, contact_app):
    res = contact_app.test_client().post("/contact", data=_form("The duct velocity looks wrong."))
    assert res.status_code == 302
    assert res.location.endswith("/contact")
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["subject"].startswith("[Help] Paul via")
    assert mock_send.call_args.kwargs["reply_to"] == "paul@example.com"


@patch("app.blueprints.pages.mail_configured", return_value=True)
@patch("app.blueprints.pages.send_email", return_value=True)
def test_contact_post_requires_turnstile_when_configured(mock_send, _mail, contact_app):
    contact_app.config["TURNSTILE_SITE_KEY"] = "site-key"
    contact_app.config["TURNSTILE_SECRET_KEY"] = "secret"
    res = contact_app.test_client().post("/contact", data=_form("The duct velocity looks wrong."))
    assert res.status_code == 400
    assert "human check" in res.get_data(as_text=True)
    mock_send.assert_not_called()


@patch("app.blueprints.pages.verify_turnstile_response", return_value=True)
@patch("app.blueprints.pages.mail_configured", return_value=True)
@patch("app.blueprints.pages.send_email", return_value=True)
def test_contact_post_rate_limit_and_duplicate(mock_send, _mail, _turnstile, contact_app):
    contact_app.config["TURNSTILE_SITE_KEY"] = "site-key"
    contact_app.config["TURNSTILE_SECRET_KEY"] = "secret"
    client = contact_app.test_client()

    first = client.post("/contact", data=_form("Same spam body about a car."))
    assert first.status_code == 302

    dup = client.post("/contact", data=_form("same   SPAM body about a car.", name="Other"))
    assert dup.status_code == 400
    assert "already received this message" in dup.get_data(as_text=True)

    ok = client.post("/contact", data=_form("A distinct follow-up about the coil."))
    assert ok.status_code == 302

    blocked = client.post("/contact", data=_form("One more distinct follow-up please."))
    assert blocked.status_code == 429
    assert "Too many messages" in blocked.get_data(as_text=True)
    # First send, duplicate drop, one more send, then the hourly cap.
    assert mock_send.call_count == 2


@patch("app.blueprints.pages.mail_configured", return_value=True)
@patch("app.blueprints.pages.send_email", return_value=False)
def test_contact_post_mail_failure_does_not_keep_the_slot(mock_send, _mail, contact_app):
    client = contact_app.test_client()
    failed = client.post("/contact", data=_form("Please retry this same note."))
    assert failed.status_code == 503
    mock_send.return_value = True
    retried = client.post("/contact", data=_form("Please retry this same note."))
    assert retried.status_code == 302
    assert mock_send.call_count == 2
