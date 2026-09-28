"""Abuse limits for the public contact form.

Gunicorn runs two workers, so the counters live in a lock file both processes
share (one file per container). Limits:

* 3 accepted submissions per client IP per hour
* the same message body (ignoring case and extra whitespace) only once per day

A failed send gives the slot back so a mail outage does not lock the sender out.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import tempfile
import time
from pathlib import Path

from flask import current_app, request

log = logging.getLogger(__name__)


def client_ip() -> str:
    """Visitor address. Prefer Cloudflare's header when the request came through it."""
    ip = ""
    if (request.headers.get("CF-Ray") or "").strip():
        ip = (request.headers.get("CF-Connecting-IP") or "").strip()
    if not ip:
        ip = (request.remote_addr or "").strip()
    return (ip or "unknown")[:64]


def _normalize(message: str) -> str:
    return " ".join(message.casefold().split())


def _body_key(message: str) -> str:
    return hashlib.sha256(_normalize(message).encode()).hexdigest()


def _store_path() -> Path:
    raw = (current_app.config.get("CONTACT_GUARD_PATH") or "").strip()
    if raw:
        return Path(raw)
    return Path(tempfile.gettempdir()) / "hvac-contact-guard.json"


def _load(raw: str) -> dict:
    if not raw.strip():
        return {"ips": {}, "bodies": {}}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("contact guard store corrupt; resetting")
        return {"ips": {}, "bodies": {}}
    if not isinstance(data, dict):
        return {"ips": {}, "bodies": {}}
    if not isinstance(data.get("ips"), dict):
        data["ips"] = {}
    if not isinstance(data.get("bodies"), dict):
        data["bodies"] = {}
    return data


def _mutate(fn):
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.seek(0)
            data = _load(fh.read())
            result = fn(data)
            fh.seek(0)
            fh.truncate()
            json.dump(data, fh, separators=(",", ":"))
            fh.flush()
            return result
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _prune(data: dict, now_ms: int) -> None:
    ip_window_ms = int(current_app.config.get("CONTACT_IP_WINDOW_SEC", 3600)) * 1000
    body_window_ms = int(current_app.config.get("CONTACT_BODY_WINDOW_SEC", 86400)) * 1000
    ips = data["ips"]
    for key, stamps in list(ips.items()):
        if not isinstance(stamps, list):
            del ips[key]
            continue
        kept = [t for t in stamps if isinstance(t, int) and not isinstance(t, bool) and now_ms - t < ip_window_ms]
        if kept:
            ips[key] = kept
        else:
            del ips[key]
    bodies = data["bodies"]
    for key, stamp in list(bodies.items()):
        if not isinstance(stamp, int) or isinstance(stamp, bool) or now_ms - stamp >= body_window_ms:
            del bodies[key]


def reserve(ip: str, message: str, now: float | None = None) -> tuple[str | None, int | None]:
    """Claim a send slot.

    Returns ``(reason, stamp)``. ``reason`` is ``None`` when the message may be
    sent, ``"rate"`` when this IP is over the hourly cap, or ``"duplicate"``
    when this body was already accepted. ``stamp`` is set when a slot was
    consumed (including a duplicate) so a failed send can call :func:`release`.

    ``now`` is seconds (tests). Stamps are stored as integer milliseconds so the
    lock file round-trips exactly.
    """
    now_ms = int((time.time() if now is None else float(now)) * 1000)
    ip_max = int(current_app.config.get("CONTACT_IP_MAX", 3))
    key = _body_key(message)

    def op(data: dict) -> tuple[str | None, int | None]:
        _prune(data, now_ms)
        stamps = list(data["ips"].get(ip, []))
        if len(stamps) >= ip_max:
            return "rate", None
        stamp = now_ms
        while stamp in stamps:
            stamp += 1
        stamps.append(stamp)
        data["ips"][ip] = stamps
        if key in data["bodies"]:
            return "duplicate", stamp
        data["bodies"][key] = stamp
        return None, stamp

    return _mutate(op)


def release(ip: str, message: str, stamp: int) -> None:
    """Give back a slot when the email was not actually sent."""
    key = _body_key(message)

    def op(data: dict) -> None:
        if data["bodies"].get(key) == stamp:
            del data["bodies"][key]
        stamps = data["ips"].get(ip)
        if isinstance(stamps, list) and stamp in stamps:
            stamps.remove(stamp)
            if stamps:
                data["ips"][ip] = stamps
            else:
                del data["ips"][ip]

    _mutate(op)
