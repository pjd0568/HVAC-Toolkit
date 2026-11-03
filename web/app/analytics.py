"""First-party product analytics.

One write path. Allowlisted events and fields only. A failed write is logged
and never raised into a calculation or checkout.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, g, has_request_context, request, session

from app.analytics_channels import (
    UTM_KEYS,
    classify_channel,
    normalise_path,
    normalise_utm,
    parse_referrer,
)

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
CTA_PLACEMENTS = frozenset({
    "result",
    "home",
    "pricing",
    "landing",
    "gate",
    "nav",
    "stage",
})

_SLUG = re.compile(r"^[a-z0-9._~-]{1,40}$")
_SESSION_KEY = "aid"
_UTM_KEY = "utm"
_ATTR_KEY = "attr"
_CTA_SOURCE = "cta_source"
_CTA_TARGET = "cta_target"
_CTA_PLACEMENT = "cta_placement"
_CTA_AT = "cta_at"
_EXCLUDED_FLAG = "analytics_excluded"

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
    """Store first-touch once and latest-touch on a new campaign or referrer.

    Attribution lives in the existing session. There is no separate analytics
    cookie. A full referring URL is never stored.
    """
    if not has_request_context():
        return
    try:
        incoming, unusable = _incoming_touch()
        path = normalise_path(request.path or "")
        host, _safe_path = parse_referrer(request.referrer, _own_hosts())
        now = datetime.now(timezone.utc).isoformat()
        current = session.get(_ATTR_KEY)
        if not isinstance(current, dict) or "first" not in current:
            legacy = _legacy_utm()
            if legacy and not incoming and not host:
                # An older session only kept the latest campaign. That is not
                # evidence of the first landing, so first-touch stays unknown.
                current = {
                    "first": {"captured": False},
                    "latest": _touch(legacy, path, None, captured=True, unusable=False, seen_at=now),
                }
            else:
                snap = _touch(incoming, path, host, captured=True, unusable=unusable, seen_at=now)
                current = {"first": dict(snap), "latest": dict(snap)}
            session[_ATTR_KEY] = current
            session.modified = True
            return
        latest = current.get("latest") if isinstance(current.get("latest"), dict) else {}
        reason = _latest_reason(latest, incoming, host)
        if reason == "campaign":
            current["latest"] = _touch(
                incoming,
                path,
                host or _text(latest.get("referrer_host")),
                captured=True,
                unusable=unusable,
                seen_at=now,
            )
            session[_ATTR_KEY] = current
            session.modified = True
        elif reason == "referrer":
            current["latest"] = _touch({}, path, host, captured=True, unusable=False, seen_at=now)
            session[_ATTR_KEY] = current
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
    utm_term: str | None = None,
    cta_placement: str | None = None,
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
            utm_term=utm_term,
            cta_placement=cta_placement,
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
    if has_request_context():
        g.analytics_calc_complete = resolve_tool(tool) or ""
    record_analytics_event("calculator_complete", tool=tool)


def note_confirmed_subscription(user_id: int, stripe_status: object) -> None:
    """Record one active subscription after Stripe's own status is ``active``.

    ``trialing`` and ``past_due`` do not count. A second webhook for the same
    user does not write another row. Checkout success pages must not call this.
    """
    if stripe_status != "active" or not isinstance(user_id, int):
        return
    try:
        from app.models.analytics import AnalyticsEvent

        already = AnalyticsEvent.query.filter_by(
            event_name="subscription_active",
            user_id=user_id,
        ).count()
        if already:
            return
        record_analytics_event(
            "subscription_active",
            route="/webhooks/stripe",
            user_id=user_id,
        )
    except Exception:
        logger.exception("analytics subscription record failed")


def link_session_to_user(user_id: int) -> None:
    """Stamp the internal user id onto this session's existing rows.

    Rows are updated in place. Nothing is copied and no email is stored.
    """
    if not isinstance(user_id, int) or not has_request_context():
        return
    sid = session.get(_SESSION_KEY)
    if not isinstance(sid, str):
        return
    try:
        from app.extensions import db
        from app.models.analytics import AnalyticsEvent

        AnalyticsEvent.query.filter(
            AnalyticsEvent.anonymous_session_id == sid,
            AnalyticsEvent.user_id.is_(None),
        ).update({AnalyticsEvent.user_id: user_id}, synchronize_session=False)
        db.session.commit()
    except Exception:
        logger.exception("analytics journey link failed")
        try:
            from app.extensions import db

            db.session.rollback()
        except Exception:
            logger.exception("analytics journey link rollback failed")


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
    placement = _clean_placement(data.get("placement") or data.get("cta_id"))
    record_analytics_event(
        event_name,
        tool=tool,
        source=source,
        target=target,
        cta_placement=placement,
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
    utm_term: str | None,
    cta_placement: str | None,
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

    placement = _clean_placement(cta_placement)
    if event_name in {"registration_start", "registration_complete", "login"} and has_request_context():
        source_name = source_name or _clean_source(session.get(_CTA_SOURCE))
        target_name = target_name or resolve_tool(session.get(_CTA_TARGET))
        placement = placement or _clean_placement(session.get(_CTA_PLACEMENT))

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
    touches = _event_touches(utm_source, utm_medium, utm_campaign, utm_content, utm_term, uid)
    excluded = _is_excluded(uid)

    if event_name == "pro_cta_click" and has_request_context():
        session[_CTA_SOURCE] = source_name or ""
        session[_CTA_TARGET] = target_name or ""
        session[_CTA_PLACEMENT] = placement or ""
        session[_CTA_AT] = datetime.now(timezone.utc).isoformat()
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
        cta_placement=placement,
        excluded=excluded,
        **touches,
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


def _clean_source(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text in CTA_PLACES:
        return text
    return resolve_tool(text)


def _clean_utm(key: str, raw: object) -> str | None:
    return normalise_utm(key, raw)


def _clean_placement(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = normalise_utm("utm_source", raw)
    if text in CTA_PLACEMENTS:
        return text
    if text and _SLUG.fullmatch(text):
        return "other"
    return None


def _own_hosts() -> set[str]:
    host = (request.host or "").split(":")[0].lower()
    return {host} if host else set()


def _text(raw: object) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:200]
    return None


def _incoming_touch() -> tuple[dict[str, str], bool]:
    clean: dict[str, str] = {}
    raw_present = False
    for key in UTM_KEYS:
        raw = request.args.get(key)
        if raw:
            raw_present = True
        item = normalise_utm(key, raw)
        if item:
            clean[key] = item
    return clean, raw_present and not clean


def _legacy_utm() -> dict[str, str]:
    raw = session.get(_UTM_KEY)
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, str] = {}
    for key in UTM_KEYS:
        item = normalise_utm(key, raw.get(key))
        if item:
            clean[key] = item
    return clean


def _touch(
    utm: dict[str, str],
    path: str | None,
    host: str | None,
    *,
    captured: bool,
    unusable: bool,
    seen_at: str,
) -> dict[str, object]:
    data: dict[str, object] = {key: utm.get(key) for key in UTM_KEYS}
    data["landing_path"] = path
    data["referrer_host"] = host
    data["captured"] = captured
    data["unusable"] = unusable
    data["seen_at"] = seen_at
    return data


def _latest_reason(latest: dict, incoming: dict[str, str], host: str | None) -> str | None:
    campaign = incoming.get("utm_campaign")
    if campaign and campaign != latest.get("utm_campaign"):
        return "campaign"
    if host and host != latest.get("referrer_host"):
        return "referrer"
    return None


def _session_touches() -> tuple[dict, dict]:
    if not has_request_context():
        return {}, {}
    raw = session.get(_ATTR_KEY)
    if not isinstance(raw, dict):
        return {}, {}
    first = raw.get("first") if isinstance(raw.get("first"), dict) else {}
    latest = raw.get("latest") if isinstance(raw.get("latest"), dict) else {}
    return first, latest


def _explicit_utm(
    utm_source: str | None,
    utm_medium: str | None,
    utm_campaign: str | None,
    utm_content: str | None,
    utm_term: str | None,
) -> dict[str, str]:
    pairs = {
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_content": utm_content,
        "utm_term": utm_term,
    }
    clean: dict[str, str] = {}
    for key, value in pairs.items():
        item = normalise_utm(key, value)
        if item:
            clean[key] = item
    return clean


def _channel_for(touch: dict) -> str | None:
    if not touch:
        return None
    captured = bool(touch.get("captured"))
    source = touch.get("utm_source") if isinstance(touch.get("utm_source"), str) else None
    host = touch.get("referrer_host") if isinstance(touch.get("referrer_host"), str) else None
    return classify_channel(
        utm_source=source,
        referrer_host=host,
        captured=captured,
        utm_unusable=bool(touch.get("unusable")),
    )


def _parse_seen(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _fields_from_touch(touch: dict, prefix: str) -> dict[str, object]:
    """Map a session touch onto event columns. ``prefix`` is first or latest."""
    source = touch.get("utm_source") if isinstance(touch.get("utm_source"), str) else None
    medium = touch.get("utm_medium") if isinstance(touch.get("utm_medium"), str) else None
    campaign = touch.get("utm_campaign") if isinstance(touch.get("utm_campaign"), str) else None
    content = touch.get("utm_content") if isinstance(touch.get("utm_content"), str) else None
    term = touch.get("utm_term") if isinstance(touch.get("utm_term"), str) else None
    landing = touch.get("landing_path") if isinstance(touch.get("landing_path"), str) else None
    host = touch.get("referrer_host") if isinstance(touch.get("referrer_host"), str) else None
    if prefix == "first":
        return {
            "first_captured": bool(touch.get("captured")),
            "first_utm_source": source,
            "first_utm_medium": medium,
            "first_utm_campaign": campaign,
            "first_utm_content": content,
            "first_utm_term": term,
            "first_landing_path": landing,
            "first_referrer_host": host,
            "first_seen_at": _parse_seen(touch.get("seen_at")),
            "first_channel": _channel_for(touch),
        }
    return {
        "latest_captured": bool(touch.get("captured")),
        "utm_source": source,
        "utm_medium": medium,
        "utm_campaign": campaign,
        "utm_content": content,
        "utm_term": term,
        "latest_landing_path": landing,
        "latest_referrer_host": host,
        "latest_seen_at": _parse_seen(touch.get("seen_at")),
        "latest_channel": _channel_for(touch),
    }


def _event_touches(
    utm_source: str | None,
    utm_medium: str | None,
    utm_campaign: str | None,
    utm_content: str | None,
    utm_term: str | None,
    user_id: int | None,
) -> dict[str, object]:
    first, latest = _session_touches()
    explicit = _explicit_utm(utm_source, utm_medium, utm_campaign, utm_content, utm_term)
    if not first and not latest and user_id is not None and not has_request_context():
        copied = _copy_user_touches(user_id)
        if copied:
            return copied
    if explicit:
        latest = dict(latest)
        latest.update(explicit)
        if "captured" not in latest:
            latest["captured"] = bool(first.get("captured")) if first else False
    fields = _fields_from_touch(first, "first")
    fields.update(_fields_from_touch(latest, "latest"))
    if not first and not latest and explicit:
        # Caller supplied campaign fields without a landing snapshot.
        fields["latest_captured"] = False
        fields["first_captured"] = False
    return fields


def _copy_user_touches(user_id: int) -> dict[str, object] | None:
    """Reuse attribution already stored for this user. Does not invent values."""
    from app.models.analytics import AnalyticsEvent

    prior = (
        AnalyticsEvent.query.filter(
            AnalyticsEvent.user_id == user_id,
            AnalyticsEvent.latest_captured.is_(True),
        )
        .order_by(AnalyticsEvent.occurred_at.desc())
        .first()
    )
    if prior is None:
        return None
    return {
        "first_captured": prior.first_captured,
        "first_utm_source": prior.first_utm_source,
        "first_utm_medium": prior.first_utm_medium,
        "first_utm_campaign": prior.first_utm_campaign,
        "first_utm_content": prior.first_utm_content,
        "first_utm_term": prior.first_utm_term,
        "first_landing_path": prior.first_landing_path,
        "first_referrer_host": prior.first_referrer_host,
        "first_seen_at": prior.first_seen_at,
        "first_channel": prior.first_channel,
        "latest_captured": prior.latest_captured,
        "utm_source": prior.utm_source,
        "utm_medium": prior.utm_medium,
        "utm_campaign": prior.utm_campaign,
        "utm_content": prior.utm_content,
        "utm_term": prior.utm_term,
        "latest_landing_path": prior.latest_landing_path,
        "latest_referrer_host": prior.latest_referrer_host,
        "latest_seen_at": prior.latest_seen_at,
        "latest_channel": prior.latest_channel,
    }


def internal_emails() -> set[str]:
    raw = current_app.config.get("ANALYTICS_INTERNAL_EMAILS") or ""
    return {part.strip().lower() for part in str(raw).split(",") if part.strip()}


def _email_is_internal(email: str | None) -> bool:
    if not email:
        return False
    return email.strip().lower() in (analytics_admin_emails() | internal_emails())


def _is_excluded(user_id: int | None) -> bool:
    if has_request_context() and session.get(_EXCLUDED_FLAG) is True:
        return True
    email = None
    if has_request_context():
        try:
            from flask_login import current_user

            if current_user.is_authenticated:
                email = getattr(current_user, "email", None)
        except Exception:
            email = None
    if _email_is_internal(email):
        if has_request_context():
            session[_EXCLUDED_FLAG] = True
            session.modified = True
        return True
    if user_id is None:
        return False
    try:
        from app.extensions import db
        from app.models import User

        user = db.session.get(User, user_id)
    except Exception:
        return False
    if user is not None and _email_is_internal(getattr(user, "email", None)):
        return True
    return False
