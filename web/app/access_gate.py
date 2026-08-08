"""Helpers to gate suite routes with the shared subscribe panel."""

from __future__ import annotations

from functools import wraps

from flask import jsonify, render_template, request

from app.access import can_access, deny_upgrade_context


def require_module(module_id: str):
    """Decorator: if the user cannot access ``module_id``, show the subscribe
    panel (HTML) or a 403 JSON body for API/CSV routes."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if can_access(module_id):
                return view(*args, **kwargs)
            wants_json = (
                "/api/" in request.path
                or request.path.endswith(".csv")
                or "application/json" in (request.accept_mimetypes.best or "")
            )
            if wants_json:
                return jsonify({
                    "error": "subscription_required",
                    "module": module_id,
                    "message": "This feature requires an active subscription or trial.",
                }), 403
            ctx = deny_upgrade_context(module_id)
            return render_template(
                "access_denied.html",
                active="dashboard",
                nav="more",
                **ctx,
            )

        return wrapped

    return decorator
