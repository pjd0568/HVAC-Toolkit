"""Shared fluid-mechanics helpers used by duct and pipe sizing.

Keeps a single Swamee–Jain friction-factor implementation so duct and pipe
pressure-loss calculations cannot silently diverge.
"""

from __future__ import annotations

from math import log10


def swamee_jain(reynolds: float, roughness_m: float, diameter_m: float) -> float:
    """Darcy friction factor via Swamee–Jain (1976) explicit Colebrook–White.

    Valid for roughly 4e3 < Re < 1e8 and ε/D < 0.05 (normal HVAC duct/pipe
    range). Below Re = 2300 returns the laminar relation f = 64/Re so the
    function stays well-behaved at very low velocities.
    """
    if reynolds <= 0:
        return 0.0
    if reynolds < 2300:
        return 64.0 / reynolds
    rel_roughness = roughness_m / diameter_m
    return 0.25 / (log10(rel_roughness / 3.7 + 5.74 / reynolds ** 0.9)) ** 2


__all__ = ["swamee_jain"]
