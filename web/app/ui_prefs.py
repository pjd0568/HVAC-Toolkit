"""UI version preference — V2 is the only app shell.

Cookie ``ui`` may still be written as ``v2`` for older clients; ``v1`` / classic
is ignored. Helpers that previously branched on preference always resolve to V2.
"""

from __future__ import annotations

from flask import make_response, redirect, request, url_for

COOKIE_NAME = "ui"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def default_ui() -> str:
    return "v2"


def current_ui() -> str:
    return "v2"


def prefer_v2() -> bool:
    return True


def set_ui_cookie(response, version: str = "v2") -> None:
    """Persist the UI cookie (always ``v2``)."""
    response.set_cookie(
        COOKIE_NAME,
        "v2",
        max_age=COOKIE_MAX_AGE,
        samesite="Lax",
        httponly=False,
        path="/",
    )


def redirect_with_ui(version: str, target: str):
    """Redirect and persist the V2 UI cookie."""
    resp = make_response(redirect(target))
    set_ui_cookie(resp, "v2")
    return resp


def redirect_to_v2(endpoint: str, **values):
    """Send classic tool URLs into the V2 shell.

    Preserves the query string on GET. Uses 307 on POST so form bodies follow.
    """
    target = url_for(endpoint, **values)
    qs = request.query_string.decode() if request.query_string else ""
    if qs:
        sep = "&" if ("?" in target) else "?"
        target = f"{target}{sep}{qs}"
    code = 307 if request.method in ("POST", "PUT", "PATCH") else 302
    return redirect(target, code=code)
