"""hvac_engine — standalone HVAC calculation engine.

Implemented from the functional specs in /specs, which cite public engineering
standards (ASHRAE Handbook — Fundamentals, CIBSE Guides). Pure Python, no web
framework imports.
"""

from hvac_engine import converter, units
from hvac_engine.ahu_design import design_ahu_to_supply
from hvac_engine.psychrometrics import PsychroState, state

__version__ = "0.1.0"
__all__ = [
    "PsychroState", "state", "design_ahu_to_supply",
    "units", "converter", "__version__",
]
