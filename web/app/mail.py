"""Outbound email — Resend HTTP API (preferred) or SMTP fallback.

Gmail/Workspace SMTP from Railway often fails (datacentre IP blocks / timeouts)
even with a valid App Password. Prefer ``RESEND_API_KEY`` + a verified domain.

Reads ``RESEND_API_KEY`` from the process environment at send time (not only
from the Flask config snapshot) so Railway variable updates are reliable.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

import requests
from flask import current_app

log = logging.getLogger(__name__)

SMTP_TIMEOUT_SEC = 10
RESEND_TIMEOUT_SEC = 15


def _resend_api_key() -> str:
    """Live env first, then Flask config (local / tests)."""
    return (
        os.environ.get("RESEND_API_KEY")
        or current_app.config.get("RESEND_API_KEY")
        or ""
    ).strip()


def mail_backend() -> str:
    """Return ``resend``, ``smtp``, or ``none`` (no secrets)."""
    if _resend_api_key():
        cfg = current_app.config
        if cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("CONTACT_EMAIL"):
            return "resend"
        return "none"
    cfg = current_app.config
    if (
        cfg.get("MAIL_SERVER")
        and cfg.get("MAIL_DEFAULT_SENDER")
        and cfg.get("MAIL_USERNAME")
        and cfg.get("MAIL_PASSWORD")
    ):
        return "smtp"
    return "none"


def mail_configured() -> bool:
    """True when Resend or full SMTP credentials are available."""
    return mail_backend() != "none"


def _from_header() -> str:
    cfg = current_app.config
    sender = (cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("CONTACT_EMAIL") or "").strip()
    brand = (cfg.get("BRAND_NAME") or "hvac-calcs.app").strip()
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
    html: str | None = None,
) -> bool:
    """Send an email. Returns True on success. ``html`` is optional.

    ``last_message_id`` is the provider id for this call, or None. It is not
    a recipient address.
    """
    ok, message_id = deliver_email(
        to=to,
        subject=subject,
        body=body,
        reply_to=reply_to,
        html=html,
    )
    send_email.last_message_id = message_id
    return ok


def deliver_email(
    *,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    html: str | None = None,
) -> tuple[bool, str | None]:
    """Send one message. The id is the provider id when Resend returns one."""
    backend = mail_backend()
    if backend == "none":
        log.warning("Mail not configured; skipped send subject=%r", subject)
        return False, None
    if backend == "resend":
        return _send_via_resend(to=to, subject=subject, body=body, reply_to=reply_to, html=html)
    ok = _send_via_smtp(to=to, subject=subject, body=body, reply_to=reply_to, html=html)
    return ok, None


def _send_via_resend(
    *,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None,
    html: str | None = None,
) -> tuple[bool, str | None]:
    api_key = _resend_api_key()
    payload: dict = {
        "from": _from_header(),
        "to": [to],
        "subject": subject,
        "text": body,
    }
    if html:
        payload["html"] = html
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        log.info("Sending email via Resend subject=%r", subject)
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
            return False, None
        message_id = None
        try:
            payload_id = resp.json().get("id")
            if isinstance(payload_id, str) and payload_id and "@" not in payload_id:
                message_id = payload_id[:80]
        except ValueError:
            message_id = None
        log.info("Sent email via Resend subject=%r provider_message_id=%s", subject, message_id or "")
        return True, message_id
    except requests.RequestException:
        log.exception("Resend request failed subject=%r", subject)
        return False, None


def _send_via_smtp(
    *,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None,
    html: str | None = None,
) -> bool:
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["MAIL_DEFAULT_SENDER"]
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    host = (cfg["MAIL_SERVER"] or "").strip()
    port = int(cfg.get("MAIL_PORT") or 587)
    use_tls = bool(cfg.get("MAIL_USE_TLS", True))
    username = (cfg.get("MAIL_USERNAME") or "").strip()
    password = (cfg.get("MAIL_PASSWORD") or "").replace(" ", "").strip()
    use_ssl = port == 465 or bool(cfg.get("MAIL_USE_SSL"))

    try:
        log.info("Sending email via SMTP via %s:%s", host, port)
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
        log.info("Sent email via SMTP subject=%r", subject)
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
