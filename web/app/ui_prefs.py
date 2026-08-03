"""UI version preference — classic (V1) vs mobile-first (V2).

Cookie ``ui`` holds ``v1`` or ``v2``. When unset, ``UI_DEFAULT`` from config
applies (cutover sets this to ``v2``).
"""

from __future__ import annotations

from flask import current_app, make_response, redirect, request

COOKIE_NAME = "ui"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year
VALID = frozenset({"v1", "v2"})


def default_ui() -> str:
    raw = (current_app.config.get("UI_DEFAULT") or "v2").strip().lower()
    return raw if raw in VALID else "v2"


def current_ui() -> str:
    raw = (request.cookies.get(COOKIE_NAME) or "").strip().lower()
    if raw in VALID:
        return raw
    return default_ui()


def prefer_v2() -> bool:
    return current_ui() == "v2"


def set_ui_cookie(response, version: str) -> None:
    ver = version if version in VALID else default_ui()
    response.set_cookie(
        COOKIE_NAME,
        ver,
        max_age=COOKIE_MAX_AGE,
        samesite="Lax",
        httponly=False,
        path="/",
    )


def redirect_with_ui(version: str, target: str):
    """Redirect and persist the UI cookie."""
    resp = make_response(redirect(target))
    set_ui_cookie(resp, version)
    return resp
