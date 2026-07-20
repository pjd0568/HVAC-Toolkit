"""Session-backed "memory slots" for a psychrometric condition.

Lets the Weather tool copy a design condition (Summer/Winter/Max/Min, or any
single hour from "On This Day") into one of 3 labelled slots, so it can be
reused elsewhere -- a psychrometric tool or the future Load Calculator --
without re-entering the numbers by hand. Same "session now, real persistence
once auth/Projects lands" pattern already used for the unit-system
preference (see app/units.py) and the PDF report's free-text fields.

Scope note (Paul's call): the slots themselves are session-wide, so any
future consuming module can read them the same way, but the *visible banner*
is only rendered on the Weather page for now -- other tools don't have a use
for them yet.
"""

from __future__ import annotations

from typing import TypedDict

from flask import session

NUM_SLOTS = 3
SESSION_KEY = "climate_slots"


class SlotCondition(TypedDict):
    """A single stored condition. Temperatures in degC, w in kg/kg, rh 0..1 --
    always canonical SI, same convention as everywhere else in the engine/web
    split; the banner converts to the active display unit system at render
    time via UnitView, same as every other results table in the app."""

    label: str
    db: float
    wb: float | None
    rh: float | None
    dp: float | None
    w: float | None
    source: str  # short provenance string, e.g. "Summer 1% -- Manchester, UK"


def get_slots() -> list[SlotCondition | None]:
    """The 3 slots, in order. Never raises -- a missing/corrupt session value
    (e.g. after a schema change) degrades to 3 empty slots rather than 500ing
    the Weather page."""
    raw = session.get(SESSION_KEY)
    if not isinstance(raw, list) or len(raw) != NUM_SLOTS:
        return [None] * NUM_SLOTS
    return raw


def save_slot(
    index: int,
    label: str,
    db: float,
    wb: float | None,
    rh: float | None,
    dp: float | None,
    w: float | None,
    source: str,
) -> None:
    if not 0 <= index < NUM_SLOTS:
        raise ValueError(f"slot index out of range: {index}")
    slots = get_slots()
    slots[index] = SlotCondition(
        label=label.strip() or f"Slot {index + 1}",
        db=db, wb=wb, rh=rh, dp=dp, w=w,
        source=source,
    )
    session[SESSION_KEY] = slots


def clear_slot(index: int) -> None:
    if not 0 <= index < NUM_SLOTS:
        raise ValueError(f"slot index out of range: {index}")
    slots = get_slots()
    slots[index] = None
    session[SESSION_KEY] = slots


__all__ = ["NUM_SLOTS", "SlotCondition", "get_slots", "save_slot", "clear_slot"]
