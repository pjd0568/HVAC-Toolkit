"""Canonical public calculator URLs (/tools/...) and /v2 → /tools redirects.

Free calculators are indexed and reported under /tools/<slug>. The signed-in
V2 shell may still serve the same engines at /v2/... for suite navigation;
anonymous hits on those paths permanently redirect to the public URL.
"""

from __future__ import annotations

from flask import redirect, request, url_for
from flask_login import current_user

# V2 endpoint → public SEO slug (free, runnable without an account).
FREE_V2_TO_SLUG: dict[str, str] = {
    "v2.single_point": "psychrometric-calculator",
    "v2.duct": "duct-sizing-calculator",
    "v2.pipe": "chilled-water-pipe-sizing",
    "v2.refrig_pt_table": "refrigerant-pt-table",
    "v2.refrig_diagnostics": "superheat-subcooling",
    "v2.converter": "unit-converter",
}

# Path prefixes (with and without trailing slash) → public slug.
FREE_V2_PATH_TO_SLUG: dict[str, str] = {
    "/v2/psychrometrics/single-point": "psychrometric-calculator",
    "/v2/duct-sizing": "duct-sizing-calculator",
    "/v2/duct-sizing/": "duct-sizing-calculator",
    "/v2/pipe-sizing": "chilled-water-pipe-sizing",
    "/v2/pipe-sizing/": "chilled-water-pipe-sizing",
    "/v2/refrigeration/pt-table": "refrigerant-pt-table",
    "/v2/refrigeration/pt-table/": "refrigerant-pt-table",
    "/v2/refrigeration/diagnostics": "superheat-subcooling",
    "/v2/refrigeration/diagnostics/": "superheat-subcooling",
    "/v2/converter": "unit-converter",
}

# Pro marketing landings (not runnable anonymously) — still have a public URL.
PRO_V2_TO_SLUG: dict[str, str] = {
    "v2.mixed_air": "mixed-air-calculator",
    "v2.pipe_system": "lthw-pipe-pressure-drop",
}

PRO_V2_PATH_TO_SLUG: dict[str, str] = {
    "/v2/psychrometrics/mixed-air": "mixed-air-calculator",
    "/v2/pipe-system": "lthw-pipe-pressure-drop",
    "/v2/pipe-system/": "lthw-pipe-pressure-drop",
}


def tools_path_for_slug(slug: str) -> str:
    return f"/tools/{slug}"


def canonical_tools_path(path: str | None) -> str | None:
    """Map a request path to its public /tools/... form when known."""
    if not path:
        return None
    text = path.split("?", 1)[0].split("#", 1)[0]
    if text.startswith("/tools/"):
        return text.rstrip("/") or "/tools"
    slug = FREE_V2_PATH_TO_SLUG.get(text) or PRO_V2_PATH_TO_SLUG.get(text)
    if slug:
        return tools_path_for_slug(slug)
    # Strip trailing slash variants for /v2/... single-point (no trailing slash in route).
    if text.endswith("/") and text[:-1] in FREE_V2_PATH_TO_SLUG:
        return tools_path_for_slug(FREE_V2_PATH_TO_SLUG[text[:-1]])
    return text


def maybe_redirect_v2_to_tools():
    """301 anonymous (and unauthenticated) free /v2 calculator hits to /tools.

    Signed-in suite users keep the V2 chrome. Public embeds already run under
    /tools and must not redirect.
    """
    from flask import g

    if getattr(g, "public_embed", False):
        return None
    try:
        from app.access import get_entitlement

        # Signed-in (or ACCESS_DEV_TIER) suite users keep the V2 app shell.
        if get_entitlement().has_suite_access:
            return None
        if current_user.is_authenticated:
            return None
    except Exception:
        pass
    endpoint = request.endpoint or ""
    slug = FREE_V2_TO_SLUG.get(endpoint)
    if not slug:
        # Pro V2 tools: send anonymous visitors to the marketing landing.
        slug = PRO_V2_TO_SLUG.get(endpoint)
    if not slug:
        return None
    target = url_for("pages.tool_landing", slug=slug)
    # Preserve query string (shared links) except empty trailing ?.
    qs = request.query_string.decode("utf-8", "ignore") if request.query_string else ""
    if qs:
        target = f"{target}?{qs}"
    return redirect(target, code=301)
