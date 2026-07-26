"""Minimal outbound email via SMTP (optional — contact form)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger(__name__)


def mail_configured() -> bool:
    cfg = current_app.config
    return bool(cfg.get("MAIL_SERVER") and cfg.get("MAIL_DEFAULT_SENDER"))


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> bool:
    """Send a plain-text email. Returns True on success."""
    cfg = current_app.config
    if not mail_configured():
        log.warning("Mail not configured; skipped send: %s", subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["MAIL_DEFAULT_SENDER"]
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    host = cfg["MAIL_SERVER"]
    port = int(cfg.get("MAIL_PORT") or 587)
    use_tls = bool(cfg.get("MAIL_USE_TLS", True))
    username = cfg.get("MAIL_USERNAME") or ""
    password = cfg.get("MAIL_PASSWORD") or ""

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except Exception:
        log.exception("Failed to send email: %s", subject)
        return False
