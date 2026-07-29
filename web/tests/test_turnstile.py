"""Turnstile configuration and verify behaviour (network mocked)."""

from unittest.mock import MagicMock, patch

from app.turnstile import turnstile_configured, verify_turnstile_response


def test_turnstile_not_configured_skips_verify(app):
    with app.app_context():
        app.config["TURNSTILE_SITE_KEY"] = ""
        app.config["TURNSTILE_SECRET_KEY"] = ""
        assert turnstile_configured() is False
        assert verify_turnstile_response(None) is True
        assert verify_turnstile_response("") is True


def test_turnstile_configured_requires_token(app):
    with app.app_context():
        app.config["TURNSTILE_SITE_KEY"] = "site"
        app.config["TURNSTILE_SECRET_KEY"] = "secret"
        assert turnstile_configured() is True
        assert verify_turnstile_response(None) is False
        assert verify_turnstile_response("") is False


@patch("app.turnstile.requests.post")
def test_turnstile_accepts_successful_siteverify(mock_post, app):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"success": True}
    mock_post.return_value = mock_resp

    with app.app_context():
        app.config["TURNSTILE_SITE_KEY"] = "site"
        app.config["TURNSTILE_SECRET_KEY"] = "secret"
        with app.test_request_context("/", environ_base={"REMOTE_ADDR": "1.2.3.4"}):
            assert verify_turnstile_response("tok_abc") is True

    mock_post.assert_called_once()
    kwargs = mock_post.call_args.kwargs.get("data") or mock_post.call_args[1].get("data")
    assert kwargs["secret"] == "secret"
    assert kwargs["response"] == "tok_abc"


@patch("app.turnstile.requests.post")
def test_turnstile_rejects_failed_siteverify(mock_post, app):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"success": False, "error-codes": ["invalid-input-response"]}
    mock_post.return_value = mock_resp

    with app.app_context():
        app.config["TURNSTILE_SITE_KEY"] = "site"
        app.config["TURNSTILE_SECRET_KEY"] = "secret"
        with app.test_request_context("/"):
            assert verify_turnstile_response("bad") is False
