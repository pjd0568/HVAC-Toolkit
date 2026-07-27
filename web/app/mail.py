"""Minimal outbound email via SMTP (contact form + lifecycle mail)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger(__name__)

# Keep UX snappy — a long hang looks like a dead submit button.
SMTP_TIMEOUT_SEC = 10


def mail_configured() -> bool:
    """True when SMTP host, sender, username and password are all set."""
    cfg = current_app.config
    return bool(
        cfg.get("MAIL_SERVER")
        and cfg.get("MAIL_DEFAULT_SENDER")
        and cfg.get("MAIL_USERNAME")
        and cfg.get("MAIL_PASSWORD")
    )


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

    host = (cfg["MAIL_SERVER"] or "").strip()
    port = int(cfg.get("MAIL_PORT") or 587)
    use_tls = bool(cfg.get("MAIL_USE_TLS", True))
    username = (cfg.get("MAIL_USERNAME") or "").strip()
    # App passwords are often copied with spaces; Gmail accepts either form.
    password = (cfg.get("MAIL_PASSWORD") or "").replace(" ", "").strip()

    # Port 465 ⇒ implicit SSL; 587 ⇒ STARTTLS. MAIL_USE_SSL forces SSL.
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
        log.info("Sent email to %s subject=%r", to, subject)
        return True
    except smtplib.SMTPAuthenticationError:
        log.exception(
            "SMTP auth failed for %s via %s:%s — check MAIL_USERNAME / App Password "
            "(no quotes in Railway; 2SV must be on).",
            username,
            host,
            port,
        )
        return False
    except TimeoutError:
        log.exception(
            "SMTP timed out connecting to %s:%s — try MAIL_PORT=465 and "
            "MAIL_USE_SSL=true (Gmail SSL) if 587 is blocked.",
            host,
            port,
        )
        return False
    except OSError:
        log.exception(
            "SMTP network error to %s:%s — outbound mail port may be blocked.",
            host,
            port,
        )
        return False
    except Exception:
        log.exception("Failed to send email: %s", subject)
        return False
