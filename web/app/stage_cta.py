"""Journey-scoped Free→Pro stage CTA after N successful free calculations.

Applies to psychrometric single-point, duct sizing, and pipe sizing. Counter and
dismiss flags live in the Flask session. Homepage teaser completions do not use
these helpers.
"""

from __future__ import annotations

from flask import has_request_context, session

from app.access import get_entitlement

STAGE_THRESHOLD = 3
STAGE_TOOLS = frozenset({"psychrometric_single", "duct_sizing", "pipe_sizing"})

# Legacy psychro-only keys — still read so existing sessions keep their count.
_LEGACY_PSYCHRO_COUNT = "psychro_single_calc_count"
_LEGACY_PSYCHRO_DISMISS = "psychro_stage_cta_dismissed"


def _count_key(tool: str) -> str:
    return f"stage_cta_count:{tool}"


def _dismiss_key(tool: str) -> str:
    return f"stage_cta_dismissed:{tool}"


def stage_calc_count(tool: str) -> int:
    if tool not in STAGE_TOOLS or not has_request_context():
        return 0
    raw = session.get(_count_key(tool))
    if raw is None and tool == "psychrometric_single":
        raw = session.get(_LEGACY_PSYCHRO_COUNT, 0)
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def increment_stage_calc(tool: str) -> int:
    """Bump the successful calc count for this free tool in the browser session."""
    if tool not in STAGE_TOOLS or not has_request_context():
        return 0
    next_count = stage_calc_count(tool) + 1
    session[_count_key(tool)] = next_count
    if tool == "psychrometric_single":
        session[_LEGACY_PSYCHRO_COUNT] = next_count
    session.modified = True
    return next_count


def stage_cta_dismissed(tool: str) -> bool:
    if tool not in STAGE_TOOLS or not has_request_context():
        return False
    if session.get(_dismiss_key(tool)) is True:
        return True
    if tool == "psychrometric_single" and session.get(_LEGACY_PSYCHRO_DISMISS) is True:
        return True
    return False


def dismiss_stage_cta(tool: str) -> None:
    if tool not in STAGE_TOOLS or not has_request_context():
        return
    session[_dismiss_key(tool)] = True
    if tool == "psychrometric_single":
        session[_LEGACY_PSYCHRO_DISMISS] = True
    session.modified = True


def should_show_stage_cta(tool: str | None) -> bool:
    """True when the free/anonymous journey has hit the stage threshold."""
    if not tool or tool not in STAGE_TOOLS:
        return False
    if stage_cta_dismissed(tool):
        return False
    if stage_calc_count(tool) < STAGE_THRESHOLD:
        return False
    try:
        if get_entitlement().has_suite_access:
            return False
    except Exception:
        return False
    return True


# Back-compat aliases used by psychro views/tests during the rename.
COUNT_KEY = _LEGACY_PSYCHRO_COUNT
DISMISS_KEY = _LEGACY_PSYCHRO_DISMISS


def psychro_single_calc_count() -> int:
    return stage_calc_count("psychrometric_single")


def increment_psychro_single_calc() -> int:
    return increment_stage_calc("psychrometric_single")


def psychro_stage_cta_dismissed() -> bool:
    return stage_cta_dismissed("psychrometric_single")


def dismiss_psychro_stage_cta() -> None:
    dismiss_stage_cta("psychrometric_single")


def should_show_psychro_stage_cta() -> bool:
    return should_show_stage_cta("psychrometric_single")


__all__ = [
    "COUNT_KEY",
    "DISMISS_KEY",
    "STAGE_THRESHOLD",
    "STAGE_TOOLS",
    "dismiss_psychro_stage_cta",
    "dismiss_stage_cta",
    "increment_psychro_single_calc",
    "increment_stage_calc",
    "psychro_single_calc_count",
    "psychro_stage_cta_dismissed",
    "should_show_psychro_stage_cta",
    "should_show_stage_cta",
    "stage_calc_count",
    "stage_cta_dismissed",
]
