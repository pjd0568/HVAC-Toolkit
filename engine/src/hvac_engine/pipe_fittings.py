"""Local (fitting) loss coefficients for hydronic pipe system pressure-drop
accounting — the Stage 2 system-builder companion to hvac_engine.pipe.

Implemented from specs/SPEC-pipe-sizing.md Stage 2 addendum (14 Jul 2026),
itself written from the standard local-loss method in CIBSE Guide C
Section 4 and Crane TP-410-style summaries. No reference to any prior
codebase — see the project's clean-room rules.

Method: every fitting's pressure loss is expressed as a loss coefficient K
against the velocity pressure at that point —

    dp_fitting = K * Pv,  Pv = hvac_engine.pipe.velocity_pressure(V, rho)

A straight run's loss is its friction rate (from hvac_engine.pipe.evaluate_size)
times its length. A "device" row is a manually-entered Pa value (coils, HX,
manufacturer strainers, etc.). This module is a pure accounting layer —
it does no pipe sizing of its own.

IMPORTANT — data provenance, flagged honestly (same standard as
hvac_engine.fittings for duct): the K values below are REPRESENTATIVE /
TYPICAL single-point figures of the kind quick-reference hydronic design
guides publish for common fittings and valves (fully open), not the full
geometry- and Reynolds-dependent correlations CIBSE Guide C / Crane
actually tabulate (a real elbow's K varies with r/D; a real tee's with
area ratio and flow split; a real valve's with opening angle). Treat every
value here as a first-pass planning figure, not a certified design value,
and cross-check against a primary table or manufacturer data before
relying on a result for a real job.
"""

from __future__ import annotations

from dataclasses import dataclass

# Categories for the picker UI (grouping only — dp = K * Pv is category-agnostic).
CAT_ELBOW = "elbow"
CAT_TEE = "tee"
CAT_TRANSITION = "transition"
CAT_VALVE = "valve"
CAT_STRAINER = "strainer"

CATEGORY_LABELS: dict[str, str] = {
    CAT_ELBOW: "Elbows",
    CAT_TEE: "Tees",
    CAT_TRANSITION: "Transitions / entry-exit",
    CAT_VALVE: "Valves",
    CAT_STRAINER: "Strainers",
}


@dataclass(frozen=True)
class Fitting:
    """One entry in the hydronic fitting / valve K-factor catalogue."""

    key: str
    label: str
    category: str
    k: float


FITTINGS: tuple[Fitting, ...] = (
    # Elbows
    Fitting("elbow_90_std", "90° Elbow (standard)", CAT_ELBOW, 0.90),
    Fitting("elbow_90_lr", "90° Elbow (long radius)", CAT_ELBOW, 0.45),
    Fitting("elbow_45", "45° Elbow", CAT_ELBOW, 0.40),
    # Tees
    Fitting("tee_run", "Tee — flow through run", CAT_TEE, 0.40),
    Fitting("tee_branch", "Tee — flow through branch", CAT_TEE, 1.50),
    # Transitions / entry / exit
    Fitting("contraction_sudden", "Sudden contraction", CAT_TRANSITION, 0.50),
    Fitting("enlargement_sudden", "Sudden enlargement", CAT_TRANSITION, 1.00),
    Fitting("entry_sharp", "Pipe entry (sharp-edged)", CAT_TRANSITION, 0.50),
    Fitting("exit", "Pipe exit", CAT_TRANSITION, 1.00),
    # Valves (fully open — representative)
    Fitting("valve_gate_open", "Gate valve (fully open)", CAT_VALVE, 0.20),
    Fitting("valve_globe_open", "Globe valve (fully open)", CAT_VALVE, 10.0),
    Fitting("valve_ball_open", "Ball valve (fully open)", CAT_VALVE, 0.05),
    Fitting("valve_butterfly_open", "Butterfly valve (fully open)", CAT_VALVE, 0.30),
    Fitting("valve_check_swing", "Swing check valve", CAT_VALVE, 2.00),
    # Strainers
    Fitting("strainer_y", "Y-strainer", CAT_STRAINER, 2.50),
)

FITTINGS_BY_KEY: dict[str, Fitting] = {f.key: f for f in FITTINGS}


def fittings_by_category(category: str | None = None) -> tuple[Fitting, ...]:
    """All fittings, or only those in `category`. Raises on unknown category."""
    if category is None:
        return FITTINGS
    if category not in CATEGORY_LABELS:
        raise ValueError(f"unknown fitting category: {category!r}")
    return tuple(f for f in FITTINGS if f.category == category)


def fitting_pressure_drop(k: float, velocity_pressure_pa: float) -> float:
    """Fitting / valve pressure loss (Pa): dp = K × Pv."""
    if k < 0:
        raise ValueError(f"K-factor must be zero or greater (got {k!r})")
    if velocity_pressure_pa < 0:
        raise ValueError(
            f"velocity pressure must be zero or greater (got {velocity_pressure_pa!r})"
        )
    return k * velocity_pressure_pa


def straight_pressure_drop(length_m: float, friction_rate_pa_per_m: float) -> float:
    """Straight-pipe pressure loss (Pa) over a run of the given length."""
    if length_m <= 0:
        raise ValueError(f"length must be greater than zero (got {length_m!r})")
    if friction_rate_pa_per_m < 0:
        raise ValueError(
            f"friction rate must be zero or greater (got {friction_rate_pa_per_m!r})"
        )
    return length_m * friction_rate_pa_per_m


def device_pressure_drop(dp_pa: float) -> float:
    """Pressure loss (Pa) for a manually-entered device row — coils, HX,
    manufacturer loss data, etc. Identity plus non-negative validation.
    """
    if dp_pa < 0:
        raise ValueError(f"pressure drop must be zero or greater (got {dp_pa!r})")
    return dp_pa


__all__ = [
    "CAT_ELBOW",
    "CAT_STRAINER",
    "CAT_TEE",
    "CAT_TRANSITION",
    "CAT_VALVE",
    "CATEGORY_LABELS",
    "FITTINGS",
    "FITTINGS_BY_KEY",
    "Fitting",
    "device_pressure_drop",
    "fitting_pressure_drop",
    "fittings_by_category",
    "straight_pressure_drop",
]
