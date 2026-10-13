"""First-party product analytics.

One write path. Allowlisted events and fields only. A failed write is logged
and never raised into a calculation or checkout.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, has_request_context, request, session

logger = logging.getLogger(__name__)

ALLOWED_EVENTS = frozenset({
    "calculator_start",
    "calculator_complete",
    "pro_cta_view",
    "pro_cta_click",
    "registration_start",
    "registration_complete",
    "login",
    "pro_tool_use",
    "checkout_start",
    "subscription_active",
})

# The browser may signal intent. Result and billing events are server-only.
CLIENT_EVENTS = frozenset({
    "calculator_start",
    "pro_cta_view",
    "pro_cta_click",
    "registration_start",
})

# Canonical tools that exist in this codebase.
TOOLS: dict[str, dict[str, str]] = {
    "psychrometric_single": {"category": "psychrometrics", "access": "free"},
    "mixed_air": {"category": "psychrometrics", "access": "pro"},
    "cooling_coil": {"category": "psychrometrics", "access": "pro"},
    "desiccant": {"category": "psychrometrics", "access": "pro"},
    "heat_humidify": {"category": "psychrometrics", "access": "pro"},
    "adiabatic": {"category": "psychrometrics", "access": "pro"},
    "ahu_design": {"category": "psychrometrics", "access": "pro"},
    "interactive_chart": {"category": "psychrometrics", "access": "pro"},
    "duct_sizing": {"category": "air_distribution", "access": "free"},
    "duct_index_leg": {"category": "air_distribution", "access": "pro"},
    "pipe_sizing": {"category": "hydronics", "access": "free"},
    "pipe_system": {"category": "hydronics", "access": "pro"},
    "refrigerant_pt": {"category": "refrigeration", "access": "free"},
    "superheat_subcooling": {"category": "refrigeration", "access": "free"},
    "dx_pipe_sizing": {"category": "refrigeration", "access": "pro"},
    "unit_converter": {"category": "utilities", "access": "free"},
}

CATEGORIES = frozenset({
    "psychrometrics",
    "air_distribution",
    "hydronics",
    "refrigeration",
    "utilities",
})

FREE_TOOLS = frozenset(name for name, meta in TOOLS.items() if meta["access"] == "free")
PRO_TOOLS = frozenset(name for name, meta in TOOLS.items() if meta["access"] == "pro")

# Marketing pages that can show a Pro CTA without being a calculator.
CTA_PLACES = frozenset({"home", "pricing"})

MODULE_TO_TOOL = {
    "psychro.single_point": "psychrometric_single",
    "psychro.mixed_air": "mixed_air",
    "psychro.cooling_coil": "cooling_coil",
    "psychro.desiccant": "desiccant",
    "psychro.heat_humidify": "heat_humidify",
    "psychro.adiabatic_cool": "adiabatic",
    "psychro.ahu": "ahu_design",
    "psychro.interactive_chart": "interactive_chart",
    "duct.sizer": "duct_sizing",
    "duct.index_leg": "duct_index_leg",
    "pipe.sizer": "pipe_sizing",
    "pipe.system": "pipe_system",
    "refrig.pt_table": "refrigerant_pt",
    "refrig.pipe_sizer": "dx_pipe_sizing",
    "refrig.diagnostics": "superheat_subcooling",
    "converter": "unit_converter",
}

SLUG_TO_TOOL = {
    "psychrometric-calculator": "psychrometric_single",
    "mixed-air-calculator": "mixed_air",
    "duct-sizing-calculator": "duct_sizing",
    "chilled-water-pipe-sizing": "pipe_sizing",
    "lthw-pipe-pressure-drop": "pipe_system",
    "refrigerant-pt-table": "refrigerant_pt",
    "superheat-subcooling": "superheat_subcooling",
    "unit-converter": "unit_converter",
}

ENDPOINT_TO_TOOL = {
    "v2.single_point": "psychrometric_single",
    "v2.mixed_air": "mixed_air",
    "v2.cooling_coil": "cooling_coil",
    "v2.desiccant": "desiccant",
    "v2.heat_humidify": "heat_humidify",
    "v2.adiabatic_cool": "adiabatic",
    "v2.ahu": "ahu_design",
    "v2.interactive_chart": "interactive_chart",
    "v2.duct": "duct_sizing",
    "v2.duct_index_leg": "duct_index_leg",
    "v2.pipe": "pipe_sizing",
    "v2.pipe_system": "pipe_system",
    "v2.refrig_pt_table": "refrigerant_pt",
    "v2.refrig_pipe_sizer": "dx_pipe_sizing",
    "v2.refrig_diagnostics": "superheat_subcooling",
    "v2.converter": "unit_converter",
}

ACCESS_STATES = frozenset({"free", "trial", "pro"})
UNIT_SYSTEMS = frozenset({"SI", "IP"})
KNOWN_SOURCES = frozenset({
    "google",
    "linkedin",
    "youtube",
    "facebook",
    "instagram",
    "direct",
    "other",
    "unknown",
})

_SLUG = re.compile(r"^[A-Za-z0-9._~-]{1,80}$")
_SESSION_KEY = "aid"
_UTM_KEY = "utm"
_CTA_SOURCE = "cta_source"
_CTA_TARGET = "cta_target"

# Re-renders and live edits must not inflate the funnel.
_DEDUPE_WINDOWS = {
    "calculator_start": timedelta(minutes=30),
    "pro_cta_view": timedelta(minutes=30),
    "pro_tool_use": timedelta(minutes=30),
    "calculator_complete": timedelta(seconds=15),
}


def resolve_tool(raw: object) -> str | None:
    """Map a slug, module id, endpoint or canonical name to a tool. Else None."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text in TOOLS:
        return text
    if text in MODULE_TO_TOOL:
        return MODULE_TO_TOOL[text]
    if text in SLUG_TO_TOOL:
        return SLUG_TO_TOOL[text]
    if text in ENDPOINT_TO_TOOL:
        return ENDPOINT_TO_TOOL[text]
    return None


def tool_for_endpoint(endpoint: str | None) -> str | None:
    if not endpoint:
        return None
    return ENDPOINT_TO_TOOL.get(endpoint)


def capture_campaign() -> None:
    """Keep UTM values on the first-party session. Ignore anything else."""
    if not has_request_context():
        return
    try:
        stored = dict(session.get(_UTM_KEY) or {})
        changed = False
        for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content"):
            raw = request.args.get(key)
            if not raw:
                continue
            clean = _clean_utm(key, raw)
            if clean:
                stored[key] = clean
                changed = True
        if changed:
            session[_UTM_KEY] = stored
            session.modified = True
    except Exception:
        logger.exception("analytics campaign capture failed")


def record_analytics_event(
    event_name: str,
    *,
    tool: str | None = None,
    category: str | None = None,
    source: str | None = None,
    target: str | None = None,
    route: str | None = None,
    access_state: str | None = None,
    unit_system: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    utm_content: str | None = None,
    user_id: int | None = None,
) -> None:
    """Validate and store one product event. Never raises."""
    try:
        _record(
            event_name,
            tool=tool,
            category=category,
            source=source,
            target=target,
            route=route,
            access_state=access_state,
            unit_system=unit_system,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            user_id=user_id,
        )
    except Exception:
        logger.exception("analytics record failed for %s", event_name)
        try:
            from app.extensions import db

            db.session.rollback()
        except Exception:
            logger.exception("analytics rollback failed")


def note_calculator_complete(tool: str) -> None:
    record_analytics_event("calculator_complete", tool=tool)


def note_pro_tool_use(tool: str) -> None:
    record_analytics_event("pro_tool_use", tool=tool)


def record_client_event(event_name: object, props: object) -> None:
    """Browser beacon. Unknown events and calculation fields are dropped."""
    if not isinstance(event_name, str) or event_name not in CLIENT_EVENTS:
        return
    data = props if isinstance(props, dict) else {}
    tool = resolve_tool(data.get("tool") or data.get("calculator"))
    source = _clean_source(data.get("source") or data.get("calculator"))
    target = resolve_tool(data.get("target"))
    record_analytics_event(
        event_name,
        tool=tool,
        source=source,
        target=target,
    )


def track(event: str, **props: object) -> None:
    """Compatibility wrapper for server call sites. Unknown keys are ignored."""
    tool = resolve_tool(props.get("tool") or props.get("calculator"))
    source = _clean_source(props.get("source"))
    target = resolve_tool(props.get("target"))
    route = props.get("route") if isinstance(props.get("route"), str) else None
    user_raw = props.get("user_id")
    user_id = user_raw if isinstance(user_raw, int) else None
    record_analytics_event(
        event,
        tool=tool,
        category=props.get("category") if isinstance(props.get("category"), str) else None,
        source=source,
        target=target,
        route=route,
        user_id=user_id,
    )


def analytics_admin_emails() -> set[str]:
    raw = current_app.config.get("ANALYTICS_ADMIN_EMAILS") or ""
    return {part.strip().lower() for part in str(raw).split(",") if part.strip()}


def is_analytics_owner() -> bool:
    try:
        from flask_login import current_user

        if not current_user.is_authenticated:
            return False
        email = (getattr(current_user, "email", "") or "").strip().lower()
        return bool(email) and email in analytics_admin_emails()
    except Exception:
        return False


def _record(
    event_name: str,
    *,
    tool: str | None,
    category: str | None,
    source: str | None,
    target: str | None,
    route: str | None,
    access_state: str | None,
    unit_system: str | None,
    utm_source: str | None,
    utm_medium: str | None,
    utm_campaign: str | None,
    utm_content: str | None,
    user_id: int | None,
) -> None:
    if event_name not in ALLOWED_EVENTS:
        return

    tool_name = resolve_tool(tool) if tool else None
    if tool and tool_name is None:
        return
    if event_name in {"calculator_start", "calculator_complete", "pro_tool_use"} and not tool_name:
        return

    source_name = _clean_source(source)
    target_name = resolve_tool(target) if target else None
    if target and target_name is None:
        target_name = None

    if event_name in {"registration_start", "registration_complete"} and has_request_context():
        source_name = source_name or _clean_source(session.get(_CTA_SOURCE))
        target_name = target_name or resolve_tool(session.get(_CTA_TARGET))

    cat = None
    if tool_name:
        cat = TOOLS[tool_name]["category"]
    elif isinstance(category, str) and category in CATEGORIES:
        cat = category

    access = _request_access(access_state)
    units = _request_units(unit_system)
    path = _request_route(route)
    uid = _request_user_id(user_id)
    sid = _anonymous_id()
    utm = _request_utm(utm_source, utm_medium, utm_campaign, utm_content)

    if event_name == "pro_cta_click" and has_request_context():
        session[_CTA_SOURCE] = source_name or ""
        session[_CTA_TARGET] = target_name or ""
        session.modified = True

    if _is_duplicate(event_name, tool_name, source_name, target_name, sid, uid):
        return

    from app.extensions import db
    from app.models.analytics import AnalyticsEvent

    row = AnalyticsEvent(
        event_name=event_name,
        occurred_at=datetime.now(timezone.utc),
        anonymous_session_id=sid,
        user_id=uid,
        tool=tool_name,
        category=cat,
        source=source_name,
        target=target_name,
        route=path,
        access_state=access,
        unit_system=units,
        utm_source=utm.get("utm_source"),
        utm_medium=utm.get("utm_medium"),
        utm_campaign=utm.get("utm_campaign"),
        utm_content=utm.get("utm_content"),
    )
    db.session.add(row)
    db.session.commit()


def _is_duplicate(
    event_name: str,
    tool: str | None,
    source: str | None,
    target: str | None,
    sid: str | None,
    user_id: int | None,
) -> bool:
    window = _DEDUPE_WINDOWS.get(event_name)
    if window is None or (not sid and user_id is None):
        return False
    from app.models.analytics import AnalyticsEvent

    cutoff = datetime.now(timezone.utc) - window
    query = AnalyticsEvent.query.filter(
        AnalyticsEvent.event_name == event_name,
        AnalyticsEvent.occurred_at >= cutoff,
    )
    if sid:
        query = query.filter(AnalyticsEvent.anonymous_session_id == sid)
    else:
        query = query.filter(AnalyticsEvent.user_id == user_id)
    if event_name in {"calculator_start", "calculator_complete", "pro_tool_use"}:
        query = query.filter(AnalyticsEvent.tool == tool)
    if event_name == "pro_cta_view":
        query = query.filter(
            AnalyticsEvent.source == source,
            AnalyticsEvent.target == target,
        )
    return query.first() is not None


def _anonymous_id() -> str | None:
    if not has_request_context():
        return None
    current = session.get(_SESSION_KEY)
    if isinstance(current, str) and 16 <= len(current) <= 64 and "@" not in current:
        return current
    fresh = secrets.token_urlsafe(24)
    session[_SESSION_KEY] = fresh
    session.modified = True
    return fresh


def _request_user_id(explicit: int | None) -> int | None:
    if isinstance(explicit, int):
        return explicit
    if not has_request_context():
        return None
    try:
        from flask_login import current_user

        if current_user.is_authenticated:
            return int(current_user.id)
    except Exception:
        return None
    return None


def _request_route(explicit: str | None) -> str | None:
    if has_request_context():
        path = request.path or ""
        return path[:200] or None
    if isinstance(explicit, str) and explicit.startswith("/") and "@" not in explicit:
        return explicit[:200]
    return None


def _request_access(explicit: str | None) -> str | None:
    if isinstance(explicit, str) and explicit in ACCESS_STATES:
        return explicit
    if not has_request_context():
        return None
    try:
        from app.access import get_entitlement

        tier = get_entitlement().tier
        return tier if tier in ACCESS_STATES else None
    except Exception:
        return None


def _request_units(explicit: str | None) -> str | None:
    if isinstance(explicit, str) and explicit in UNIT_SYSTEMS:
        return explicit
    if not has_request_context():
        return None
    try:
        from app.units import get_unit_system

        system = get_unit_system()
        return system if system in UNIT_SYSTEMS else None
    except Exception:
        return None


def _request_utm(
    utm_source: str | None,
    utm_medium: str | None,
    utm_campaign: str | None,
    utm_content: str | None,
) -> dict[str, str]:
    stored = {}
    if has_request_context():
        raw = session.get(_UTM_KEY)
        if isinstance(raw, dict):
            stored = raw
    pairs = {
        "utm_source": utm_source or stored.get("utm_source"),
        "utm_medium": utm_medium or stored.get("utm_medium"),
        "utm_campaign": utm_campaign or stored.get("utm_campaign"),
        "utm_content": utm_content or stored.get("utm_content"),
    }
    clean: dict[str, str] = {}
    for key, value in pairs.items():
        item = _clean_utm(key, value)
        if item:
            clean[key] = item
    return clean


def _clean_source(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text in CTA_PLACES:
        return text
    return resolve_tool(text)


def _clean_utm(key: str, raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or "@" in text or _SLUG.fullmatch(text) is None:
        return None
    if key == "utm_source":
        lowered = text.lower()
        if lowered in KNOWN_SOURCES:
            return lowered
    limit = 64 if key in {"utm_source", "utm_medium"} else 80
    return text[:limit]
