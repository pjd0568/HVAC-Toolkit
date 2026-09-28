"""Cloudflare Turnstile helpers for registration and contact bot protection.

When ``TURNSTILE_SITE_KEY`` and ``TURNSTILE_SECRET_KEY`` are both set, the
register and contact forms show the widget and POSTs must pass siteverify.
When unset (local/dev), verification is skipped so those forms still work
without Cloudflare.
"""

from __future__ import annotations

import logging

import requests
from flask import current_app, request

log = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SITEVERIFY_TIMEOUT_SEC = 10


def turnstile_configured() -> bool:
    site = (current_app.config.get("TURNSTILE_SITE_KEY") or "").strip()
    secret = (current_app.config.get("TURNSTILE_SECRET_KEY") or "").strip()
    return bool(site and secret)


def turnstile_site_key() -> str:
    return (current_app.config.get("TURNSTILE_SITE_KEY") or "").strip()


def verify_turnstile_response(token: str | None) -> bool:
    """Return True if the token is valid, or if Turnstile is not configured."""
    if not turnstile_configured():
        return True

    token = (token or "").strip()
    if not token:
        return False

    secret = (current_app.config.get("TURNSTILE_SECRET_KEY") or "").strip()
    payload = {
        "secret": secret,
        "response": token,
    }
    # Optional: bind to client IP when available (helps Cloudflare scoring).
    remote = request.headers.get("CF-Connecting-IP") or request.remote_addr
    if remote:
        payload["remoteip"] = remote

    try:
        resp = requests.post(
            SITEVERIFY_URL,
            data=payload,
            timeout=SITEVERIFY_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Turnstile siteverify failed: %s", exc)
        return False

    ok = bool(data.get("success"))
    if not ok:
        log.info("Turnstile rejected token; codes=%s", data.get("error-codes"))
    return ok
