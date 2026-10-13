"""First-party product events.

Events are written to the application log. No analytics cookie is set and
calculation inputs are not accepted.
"""

from __future__ import annotations

import json
import logging

from flask import current_app, has_request_context, request

logger = logging.getLogger(__name__)

ALLOWED_EVENTS = frozenset({
    "page_view",
    "calculator_start",
    "calculator_complete",
    "pro_cta_view",
    "pro_cta_click",
    "registration_start",
    "registration_complete",
    "pro_tool_use",
    "checkout_start",
    "subscription_active",
})

# Only these properties are stored. Anything else from the client is dropped.
ALLOWED_PROPS = frozenset({
    "route",
    "calculator",
    "category",
    "authenticated",
    "access",
    "units",
})


def _server_props() -> dict[str, str]:
    if not has_request_context():
        return {}
    props: dict[str, str] = {"route": request.path[:200]}
    try:
        from flask_login import current_user

        props["authenticated"] = "yes" if current_user.is_authenticated else "no"
    except Exception:
        props["authenticated"] = "no"
    try:
        from app.access import get_entitlement

        props["access"] = get_entitlement().tier
    except Exception:
        pass
    try:
        from app.units import get_unit_system

        props["units"] = get_unit_system()
    except Exception:
        pass
    return props


def track(event: str, **props: object) -> None:
    """Record one semantic event. Unknown events and properties are ignored."""
    if event not in ALLOWED_EVENTS:
        return
    clean: dict[str, str] = {}
    for key, value in props.items():
        if key not in ALLOWED_PROPS or value is None:
            continue
        clean[key] = str(value)[:120]
    for key, value in _server_props().items():
        clean.setdefault(key, value)
    try:
        current_app.logger.info("product_event %s", json.dumps({"event": event, **clean}))
    except Exception:
        logger.info("product_event %s", event)
