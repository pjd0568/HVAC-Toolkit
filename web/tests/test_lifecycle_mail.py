"""Lifecycle mail transition rules — mail send is mocked."""

from unittest.mock import MagicMock, patch

from app.lifecycle_mail import notify_subscription_status_change


def _user(status: str):
    user = MagicMock()
    user.id = 1
    user.email = "dogfood@example.com"
    user.subscription_status = status
    user.stripe_customer_id = "cus_x"
    user.stripe_subscription_id = "sub_x"
    return user


@patch("app.lifecycle_mail.send_subscription_ended")
@patch("app.lifecycle_mail.send_subscribed")
def test_notify_sends_subscribed_when_becoming_active(mock_sub, mock_end):
    notify_subscription_status_change(_user("active"), previous_status="trialing")
    mock_sub.assert_called_once()
    mock_end.assert_not_called()


@patch("app.lifecycle_mail.send_subscription_ended")
@patch("app.lifecycle_mail.send_subscribed")
def test_notify_sends_ended_when_leaving_active(mock_sub, mock_end):
    notify_subscription_status_change(_user("canceled"), previous_status="active")
    mock_end.assert_called_once()
    mock_sub.assert_not_called()


@patch("app.lifecycle_mail.send_subscription_ended")
@patch("app.lifecycle_mail.send_subscribed")
def test_notify_skips_duplicate_active_webhook(mock_sub, mock_end):
    notify_subscription_status_change(_user("active"), previous_status="active")
    mock_sub.assert_not_called()
    mock_end.assert_not_called()


@patch("app.lifecycle_mail.send_email")
@patch("app.lifecycle_mail.mail_configured", return_value=True)
def test_send_subscribed_also_notifies_owner(mock_cfg, mock_send, app):
    from app.lifecycle_mail import send_subscribed

    with app.app_context():
        app.config["CONTACT_EMAIL"] = "info@hvac-calcs.app"
        app.config["BRAND_NAME"] = "hvac-calcs.app"
        user = _user("active")
        mock_send.return_value = True
        assert send_subscribed(user) is True

    assert mock_send.call_count == 2
    tos = [c.kwargs["to"] for c in mock_send.call_args_list]
    assert "dogfood@example.com" in tos
    assert "info@hvac-calcs.app" in tos
    subjects = [c.kwargs["subject"] for c in mock_send.call_args_list]
    assert any("Thanks for subscribing" in s for s in subjects)
    assert any("[Owner] New subscriber" in s for s in subjects)


@patch("app.lifecycle_mail.send_email")
@patch("app.lifecycle_mail.mail_configured", return_value=True)
def test_send_trial_started_also_notifies_owner(mock_cfg, mock_send, app):
    from app.lifecycle_mail import send_trial_started

    with app.app_context():
        app.config["CONTACT_EMAIL"] = "info@hvac-calcs.app"
        app.config["BRAND_NAME"] = "hvac-calcs.app"
        user = _user("trialing")
        mock_send.return_value = True
        assert send_trial_started(user) is True

    assert mock_send.call_count == 2
    subjects = [c.kwargs["subject"] for c in mock_send.call_args_list]
    assert any("trial has started" in s for s in subjects)
    assert any("[Owner] New trial" in s for s in subjects)
