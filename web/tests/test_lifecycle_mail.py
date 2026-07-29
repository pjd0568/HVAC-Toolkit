"""Lifecycle mail transition rules — mail send is mocked."""

from unittest.mock import MagicMock, patch

from app.lifecycle_mail import notify_subscription_status_change


def _user(status: str):
    user = MagicMock()
    user.id = 1
    user.email = "dogfood@example.com"
    user.subscription_status = status
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
