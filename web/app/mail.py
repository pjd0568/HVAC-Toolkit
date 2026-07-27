"""Outbound email — Resend HTTP API (preferred) or SMTP fallback.

Gmail/Workspace SMTP from Railway often fails (datacentre IP blocks / timeouts)
even with a valid App Password. Prefer ``RESEND_API_KEY`` + a verified domain.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import requests
from flask import current_app

log = logging.getLogger(__name__)

SMTP_TIMEOUT_SEC = 10
RESEND_TIMEOUT_SEC = 15


def mail_configured() -> bool:
    """True when Resend or full SMTP credentials are available."""
    cfg = current_app.config
    if cfg.get("RESEND_API_KEY"):
        return bool(cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("CONTACT_EMAIL"))
    return bool(
        cfg.get("MAIL_SERVER")
        and cfg.get("MAIL_DEFAULT_SENDER")
        and cfg.get("MAIL_USERNAME")
        and cfg.get("MAIL_PASSWORD")
    )


def _from_header() -> str:
    cfg = current_app.config
    sender = (cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("CONTACT_EMAIL") or "").strip()
    brand = (cfg.get("BRAND_NAME") or "HVAC Toolkit").strip()
    # Resend accepts "Name <email@domain>"
    if "<" in sender:
        return sender
    return f"{brand} <{sender}>"


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> bool:
    """Send a plain-text email. Returns True on success."""
    if not mail_configured():
        log.warning("Mail not configured; skipped send: %s", subject)
        return False

    if current_app.config.get("RESEND_API_KEY"):
        return _send_via_resend(to=to, subject=subject, body=body, reply_to=reply_to)
    return _send_via_smtp(to=to, subject=subject, body=body, reply_to=reply_to)


def _send_via_resend(
    *,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None,
) -> bool:
    api_key = (current_app.config.get("RESEND_API_KEY") or "").strip()
    payload: dict = {
        "from": _from_header(),
        "to": [to],
        "subject": subject,
        "text": body,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=RESEND_TIMEOUT_SEC,
        )
        if resp.status_code >= 400:
            log.error(
                "Resend API error %s: %s",
                resp.status_code,
                (resp.text or "")[:500],
            )
            return False
        log.info("Sent email via Resend to %s subject=%r", to, subject)
        return True
    except requests.RequestException:
        log.exception("Resend request failed: %s", subject)
        return False


def _send_via_smtp(
    *,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None,
) -> bool:
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["MAIL_DEFAULT_SENDER"]
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    host = (cfg["MAIL_SERVER"] or "").strip()
    port = int(cfg.get("MAIL_PORT") or 587)
    use_tls = bool(cfg.get("MAIL_USE_TLS", True))
    username = (cfg.get("MAIL_USERNAME") or "").strip()
    password = (cfg.get("MAIL_PASSWORD") or "").replace(" ", "").strip()
    use_ssl = port == 465 or bool(cfg.get("MAIL_USE_SSL"))

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SEC) as smtp:
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SEC) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(msg)
        log.info("Sent email via SMTP to %s subject=%r", to, subject)
        return True
    except smtplib.SMTPAuthenticationError:
        log.exception(
            "SMTP auth failed for %s via %s:%s — Gmail from Railway is unreliable; "
            "prefer RESEND_API_KEY (see SPEC-transactional-email.md).",
            username,
            host,
            port,
        )
        return False
    except TimeoutError:
        log.exception(
            "SMTP timed out to %s:%s — prefer RESEND_API_KEY on Railway.",
            host,
            port,
        )
        return False
    except OSError:
        log.exception(
            "SMTP network error to %s:%s — prefer RESEND_API_KEY on Railway.",
            host,
            port,
        )
        return False
    except Exception:
        log.exception("Failed to send email via SMTP: %s", subject)
        return False
