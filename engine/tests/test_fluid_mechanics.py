"""Regression: duct and pipe share one Swamee–Jain implementation."""

from hvac_engine import duct as duct_mod
from hvac_engine import pipe as pipe_mod
from hvac_engine.fluid_mechanics import swamee_jain


def test_duct_and_pipe_swamee_jain_agree():
    cases = [
        (1.0e5, 0.00009, 0.45),
        (5.0e4, 0.00015, 0.05),
        (1000.0, 0.00009, 0.4),   # laminar branch
        (0.0, 0.00009, 0.4),
    ]
    for re, eps, diam in cases:
        shared = swamee_jain(re, eps, diam)
        assert duct_mod._swamee_jain(re, eps, diam) == shared
        assert pipe_mod._swamee_jain(re, eps, diam) == shared
