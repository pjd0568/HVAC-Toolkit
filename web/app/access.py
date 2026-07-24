"""Access tiers — Free / Trial / Pro module flags.

See specs/SPEC-access.md and specs/SPEC-auth.md. Trial / Pro bind to the
authenticated User row; ACCESS_DEV_TIER still forces tier for local UI testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from flask import current_app
from flask_login import current_user

TierName = Literal["free", "trial", "pro"]
ModuleTier = Literal["free", "pro"]

TRIAL_DAYS = 14

# module_id → catalogue entry. Labels are for nav / upgrade copy.
MODULES: dict[str, dict[str, str]] = {
    "dashboard": {"tier": "free", "label": "Dashboard"},
    "help": {"tier": "free", "label": "Help"},
    "guides": {"tier": "free", "label": "Design Guides"},
    "psychro.single_point": {"tier": "free", "label": "Psychrometrics — Single Point"},
    "psychro.mixed_air": {"tier": "pro", "label": "Psychrometrics — Mixed Air"},
    "psychro.cooling_coil": {"tier": "pro", "label": "Psychrometrics — Cooling Coil"},
    "psychro.ahu": {"tier": "pro", "label": "Psychrometrics — AHU Design"},
    "duct.sizer": {"tier": "free", "label": "Duct Sizing"},
    "duct.index_leg": {"tier": "pro", "label": "Duct Index Leg"},
    "pipe.sizer": {"tier": "free", "label": "Pipe Sizing"},
    "pipe.system": {"tier": "pro", "label": "Pipe System"},
    "weather": {"tier": "pro", "label": "Weather & Design Conditions"},
    "converter": {"tier": "pro", "label": "Unit Converter"},
    "projects": {"tier": "pro", "label": "Projects"},
}


@dataclass(frozen=True)
class Entitlement:
    """Resolved access state for the current request."""

    tier: TierName
    can_use_pro: bool
    trial_days_remaining: int | None
    trial_started: date | None
    trial_ends: date | None


def _today() -> date:
    return date.today()


def _entitlement_from_trial(started: date | None) -> Entitlement:
    if started is None:
        return Entitlement("free", False, 0, None, None)
    ends = started + timedelta(days=TRIAL_DAYS)
    remaining = (ends - _today()).days
    if remaining > 0:
        return Entitlement("trial", True, remaining, started, ends)
    return Entitlement("free", False, 0, started, ends)


def _entitlement_for_user(user) -> Entitlement:
    status = (user.subscription_status or "none").lower()
    if status == "active":
        return Entitlement("pro", True, None, user.trial_started_at, None)
    return _entitlement_from_trial(user.trial_started_at)


def get_entitlement() -> Entitlement:
    """Resolve Free / Trial / Pro for this request.

    Priority: Config.ACCESS_DEV_TIER (dev) → authenticated user record → free.
    """
    forced = current_app.config.get("ACCESS_DEV_TIER")
    if forced in ("free", "trial", "pro"):
        if forced == "pro":
            return Entitlement("pro", True, None, None, None)
        if forced == "free":
            return Entitlement("free", False, 0, None, None)
        started = _today()
        ends = started + timedelta(days=TRIAL_DAYS)
        remaining = max(0, (ends - _today()).days)
        return Entitlement("trial", remaining > 0, remaining if remaining > 0 else 0, started, ends)

    if current_user.is_authenticated:
        return _entitlement_for_user(current_user)

    # Anonymous visitors are gated out of the app shell; treat as free if asked.
    return Entitlement("free", False, 0, None, None)


def module_tier(module_id: str) -> ModuleTier:
    entry = MODULES.get(module_id)
    if entry is None:
        # Unknown modules default to Pro so new tools don't ship free by accident.
        return "pro"
    return entry["tier"]  # type: ignore[return-value]


def module_label(module_id: str) -> str:
    entry = MODULES.get(module_id)
    return entry["label"] if entry else module_id


def is_pro_module(module_id: str) -> bool:
    return module_tier(module_id) == "pro"


def can_access(module_id: str) -> bool:
    """True if the current entitlement may use this module."""
    if module_tier(module_id) == "free":
        return True
    return get_entitlement().can_use_pro


@dataclass
class AccessView:
    """Template façade — ``access`` in Jinja."""

    entitlement: Entitlement

    @property
    def tier(self) -> TierName:
        return self.entitlement.tier

    @property
    def can_use_pro(self) -> bool:
        return self.entitlement.can_use_pro

    @property
    def trial_days_remaining(self) -> int | None:
        return self.entitlement.trial_days_remaining

    def can(self, module_id: str) -> bool:
        if module_tier(module_id) == "free":
            return True
        return self.entitlement.can_use_pro

    def is_pro(self, module_id: str) -> bool:
        return is_pro_module(module_id)

    def label(self, module_id: str) -> str:
        return module_label(module_id)


def current_access() -> AccessView:
    return AccessView(get_entitlement())


def deny_upgrade_context(module_id: str) -> dict:
    """Context for the shared upgrade / trial-ended panel."""
    ent = get_entitlement()
    return {
        "module_id": module_id,
        "module_label": module_label(module_id),
        "entitlement": ent,
        "trial_expired": ent.tier == "free" and ent.trial_started is not None,
    }


__all__ = [
    "MODULES",
    "TRIAL_DAYS",
    "AccessView",
    "Entitlement",
    "can_access",
    "current_access",
    "deny_upgrade_context",
    "get_entitlement",
    "is_pro_module",
    "module_label",
    "module_tier",
]
