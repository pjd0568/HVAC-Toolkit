"""Access — 14-day trial then subscription for the full suite.

See specs/SPEC-access.md and specs/SPEC-auth.md. Trial / subscription bind to
the authenticated User row; ACCESS_DEV_TIER still forces tier for local UI
testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from flask import current_app
from flask_login import current_user

# Internal tier codes. UI labels: Trial / Subscribed / Trial ended (never "Pro").
TierName = Literal["free", "trial", "pro"]

TRIAL_DAYS = 14
PRICE_MONTHLY_GBP = "4.50"

# Modules that need an active trial or subscription. Always-open pages
# (dashboard, help, guides, methodology) and Coming Soon placeholders
# (weather, projects) are omitted — they stay reachable after trial expiry
# so users can still reach pricing and reference material.
SUITE_MODULES: frozenset[str] = frozenset({
    "psychro.single_point",
    "psychro.mixed_air",
    "psychro.cooling_coil",
    "psychro.desiccant",
    "psychro.heat_humidify",
    "psychro.adiabatic_cool",
    "psychro.ahu",
    "duct.sizer",
    "duct.index_leg",
    "pipe.sizer",
    "pipe.system",
    "refrig.pt_table",
    "refrig.pipe_sizer",
    "converter",
})

COMING_SOON_MODULES: frozenset[str] = frozenset({
    "weather",
    "projects",
    "refrig.diagnostics",
    "refrig.charge",
    "room.load",
    "air.grille_throw",
    "pipe.expansion_vessel",
    "pipe.buffer_tank",
    "iaq.co2",
    "acoustics.duct_nr",
    "acoustics.barrier",
})

# module_id → label (for upgrade / gate copy).
MODULES: dict[str, dict[str, str]] = {
    "dashboard": {"label": "Dashboard"},
    "help": {"label": "Help"},
    "guides": {"label": "Design Guides"},
    "psychro.single_point": {"label": "Psychrometrics — Single Point"},
    "psychro.mixed_air": {"label": "Psychrometrics — Mixed Air"},
    "psychro.cooling_coil": {"label": "Psychrometrics — Cooling Coil"},
    "psychro.desiccant": {"label": "Psychrometrics — Desiccant Dehumidification"},
    "psychro.heat_humidify": {"label": "Psychrometrics — Heating & Humidification"},
    "psychro.adiabatic_cool": {"label": "Psychrometrics — Adiabatic Cooling"},
    "psychro.ahu": {"label": "Psychrometrics — AHU Design"},
    "duct.sizer": {"label": "Duct Sizing"},
    "duct.index_leg": {"label": "Duct Index Leg"},
    "pipe.sizer": {"label": "Pipe Sizing"},
    "pipe.system": {"label": "Pipe System"},
    "pipe.expansion_vessel": {"label": "Hydronics — Expansion Vessel"},
    "pipe.buffer_tank": {"label": "Hydronics — Buffer Tank"},
    "room.load": {"label": "Air — Room Load"},
    "air.grille_throw": {"label": "Air — Grille Throw"},
    "iaq.co2": {"label": "Ventilation — Fresh Air & CO₂"},
    "acoustics.duct_nr": {"label": "Acoustics — Duct Attenuation & NR"},
    "acoustics.barrier": {"label": "Acoustics — Barrier Screening"},
    "refrig.pt_table": {"label": "Refrigeration — PT Table"},
    "refrig.pipe_sizer": {"label": "Refrigeration — DX Pipe Sizing"},
    "refrig.diagnostics": {"label": "Refrigeration — Superheat & Subcooling"},
    "refrig.charge": {"label": "Refrigeration — Charge Calculator"},
    "weather": {"label": "Weather & Design Conditions (ASHRAE lookup)"},
    "converter": {"label": "Unit Converter"},
    "projects": {"label": "Projects"},
}


@dataclass(frozen=True)
class Entitlement:
    """Resolved access state for the current request."""

    tier: TierName
    has_suite_access: bool
    trial_days_remaining: int | None
    trial_started: date | None
    trial_ends: date | None

    @property
    def can_use_pro(self) -> bool:
        """Alias kept for older call sites — means full suite access."""
        return self.has_suite_access


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
    """Resolve Trial / Subscribed / expired for this request.

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


def module_label(module_id: str) -> str:
    entry = MODULES.get(module_id)
    return entry["label"] if entry else module_id


def is_coming_soon(module_id: str) -> bool:
    return module_id in COMING_SOON_MODULES


def requires_suite(module_id: str) -> bool:
    """True if this module needs an active trial or subscription."""
    if module_id in SUITE_MODULES:
        return True
    # Unknown calculator modules default to gated so new tools don't ship open.
    if module_id in MODULES or module_id in COMING_SOON_MODULES:
        return False
    return True


def can_access(module_id: str) -> bool:
    """True if the current entitlement may use this module."""
    if not requires_suite(module_id):
        return True
    return get_entitlement().has_suite_access


@dataclass
class AccessView:
    """Template façade — ``access`` in Jinja."""

    entitlement: Entitlement

    @property
    def tier(self) -> TierName:
        return self.entitlement.tier

    @property
    def has_suite_access(self) -> bool:
        return self.entitlement.has_suite_access

    @property
    def can_use_pro(self) -> bool:
        return self.entitlement.has_suite_access

    @property
    def trial_days_remaining(self) -> int | None:
        return self.entitlement.trial_days_remaining

    @property
    def price_monthly(self) -> str:
        return PRICE_MONTHLY_GBP

    def can(self, module_id: str) -> bool:
        if not requires_suite(module_id):
            return True
        return self.entitlement.has_suite_access

    def is_coming_soon(self, module_id: str) -> bool:
        return is_coming_soon(module_id)

    def label(self, module_id: str) -> str:
        return module_label(module_id)


def current_access() -> AccessView:
    return AccessView(get_entitlement())


def deny_upgrade_context(module_id: str) -> dict:
    """Context for the shared trial-ended / subscribe panel."""
    ent = get_entitlement()
    return {
        "module_id": module_id,
        "module_label": module_label(module_id),
        "entitlement": ent,
        "trial_expired": ent.tier == "free" and ent.trial_started is not None,
        "price_monthly": PRICE_MONTHLY_GBP,
    }


__all__ = [
    "COMING_SOON_MODULES",
    "MODULES",
    "PRICE_MONTHLY_GBP",
    "SUITE_MODULES",
    "TRIAL_DAYS",
    "AccessView",
    "Entitlement",
    "can_access",
    "current_access",
    "deny_upgrade_context",
    "get_entitlement",
    "is_coming_soon",
    "module_label",
    "requires_suite",
]
