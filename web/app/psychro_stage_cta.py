"""Journey-scoped Free→Pro stage CTA for psychrometric single-point only.

Counter and dismiss flag live in the Flask session alongside the analytics
``aid``. Homepage teaser completions do not use these helpers.
"""

from __future__ import annotations

from flask import has_request_context, session

from app.access import get_entitlement

COUNT_KEY = "psychro_single_calc_count"
DISMISS_KEY = "psychro_stage_cta_dismissed"
STAGE_THRESHOLD = 3


def psychro_single_calc_count() -> int:
    if not has_request_context():
        return 0
    raw = session.get(COUNT_KEY, 0)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def increment_psychro_single_calc() -> int:
    """Bump the successful single-point calc count for this browser session."""
    if not has_request_context():
        return 0
    next_count = psychro_single_calc_count() + 1
    session[COUNT_KEY] = next_count
    session.modified = True
    return next_count


def psychro_stage_cta_dismissed() -> bool:
    if not has_request_context():
        return False
    return session.get(DISMISS_KEY) is True


def dismiss_psychro_stage_cta() -> None:
    if not has_request_context():
        return
    session[DISMISS_KEY] = True
    session.modified = True


def should_show_psychro_stage_cta() -> bool:
    """True when the free/anonymous journey has hit the stage threshold."""
    if psychro_stage_cta_dismissed():
        return False
    if psychro_single_calc_count() < STAGE_THRESHOLD:
        return False
    try:
        if get_entitlement().has_suite_access:
            return False
    except Exception:
        return False
    return True


__all__ = [
    "COUNT_KEY",
    "DISMISS_KEY",
    "STAGE_THRESHOLD",
    "dismiss_psychro_stage_cta",
    "increment_psychro_single_calc",
    "psychro_single_calc_count",
    "psychro_stage_cta_dismissed",
    "should_show_psychro_stage_cta",
]
