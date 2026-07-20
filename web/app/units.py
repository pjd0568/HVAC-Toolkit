"""Web-side unit-system preference and display helper.

The engine is canonical SI. This module is the *only* place the web layer decides
which unit system the current request is in, and the only place SI values get
turned into display strings. Every tool — current and future — renders through the
``UnitView`` (``U`` in templates) and converts its inputs through ``U.to_si(...)``,
so adding units to a new tool is free.

Preference source
-----------------
``get_unit_system()`` reads the Flask session today. When auth lands, this becomes
"logged-in user's saved preference, else session, else SI" — a one-function change,
so the preference stays consistent for a user across devices once they sign in.
"""

from __future__ import annotations

from flask import session
from markupsafe import Markup, escape

from hvac_engine import units as eng_units

DEFAULT_SYSTEM = "SI"


def get_unit_system() -> str:
    """Active unit system for this request. Session now; user preference on login."""
    system = session.get("units", DEFAULT_SYSTEM)
    return system if system in eng_units.SYSTEMS else DEFAULT_SYSTEM


def set_unit_system(system: str) -> None:
    """Persist the chosen unit system (session today; will also write user pref later)."""
    if system in eng_units.SYSTEMS:
        session["units"] = system


class UnitView:
    """Per-request façade over ``hvac_engine.units`` bound to the active system.

    Injected into every template as ``U``. Templates render display numbers with
    ``U.fmt(quantity, si_value)`` and unit labels with ``U.sym(quantity)``; blueprints
    convert user input with ``U.to_si(quantity, value)``.
    """

    def __init__(self, system: str) -> None:
        self.system = system

    # -- display -------------------------------------------------------------------
    def sym(self, quantity: str) -> str:
        """Unit symbol for the active system, e.g. sym('temperature') -> '°C' or '°F'."""
        return eng_units.symbol(quantity, self.system)

    def conv(self, quantity: str, si_value: float) -> float:
        """SI value -> raw display value (unformatted)."""
        return eng_units.from_si(quantity, si_value, self.system)

    def fmt(self, quantity: str, si_value, dp: int | None = None, sign: bool = False) -> str:
        """SI value -> formatted display string (number only, no unit).

        ``dp`` overrides the quantity's default precision; ``sign`` forces a leading
        + on positive values (for signed duties). ``None`` renders as an em dash.
        """
        if si_value is None:
            return "—"
        value = eng_units.from_si(quantity, si_value, self.system)
        if dp is None:
            dp = eng_units.decimals(quantity, self.system)
        flag = "+" if sign else ""
        return f"{value:{flag}.{dp}f}"

    def unit(self, quantity: str, si_value, dp: int | None = None, sign: bool = False) -> str:
        """Convenience: formatted number followed by the unit symbol."""
        return f"{self.fmt(quantity, si_value, dp, sign)} {self.sym(quantity)}"

    def html(self, quantity: str, si_value, dp: int | None = None, sign: bool = False,
             suffix: str = "") -> Markup:
        """Value + unit as one ``<span class="valunit">`` group, for on-screen tables.

        Every "results" table cell should render through this (instead of the
        plain ``{{ U.fmt(...) }} {{ U.sym(...) }}`` string join) so the value and
        its unit always get the same CSS-controlled gap and the unit gets its
        own muted, slightly smaller style -- consistent spacing/justification
        across every psychrometric tool, in both SI and IP. ``suffix`` is for a
        trailing qualifier that isn't itself a unit (e.g. "dry air").
        """
        if si_value is None:
            return Markup('<span class="valunit"><span class="v">—</span></span>')
        val = escape(self.fmt(quantity, si_value, dp, sign))
        sym = escape(self.sym(quantity))
        tail = f' <span class="suffix">{escape(suffix)}</span>' if suffix else ""
        return Markup(
            f'<span class="valunit"><span class="v">{val}</span>'
            f'<span class="u">{sym}</span></span>{tail}'
        )

    # -- input ---------------------------------------------------------------------
    def to_si(self, quantity: str, display_value: float) -> float:
        """Display value entered by the user -> canonical SI value for the engine."""
        return eng_units.to_si(quantity, display_value, self.system)


def current_view() -> UnitView:
    return UnitView(get_unit_system())
