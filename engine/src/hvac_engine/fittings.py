"""Local (fitting) loss coefficients for duct system pressure-drop accounting
— the "index leg" pressure-drop table companion to hvac_engine.duct.

Implemented from SPEC-duct-sizing.md's Phase C section, itself written from
the standard local-loss method described in ASHRAE Fundamentals Chapter 32
and CIBSE Guide C Section 4. No reference to any prior codebase — see the
project's clean-room rules.

Method: every fitting's pressure loss is expressed as a loss coefficient K
against the velocity pressure at that point --

    dp_fitting = K * Pv,  Pv = hvac_engine.duct.velocity_pressure(velocity)

A straight run's loss is just its friction rate (from hvac_engine.duct)
times its length. Both draw on an existing duct-sizing result -- this
module is a pure accounting layer, it does no sizing of its own.

IMPORTANT — data provenance, flagged honestly: the K values below
are REPRESENTATIVE / TYPICAL single-point figures of the kind quick-reference
duct design guides publish for common fittings, not the full multi-parameter
geometry-dependent correlations ASHRAE Ch.32 / CIBSE Guide C Section 4
actually tabulate (a real elbow's K varies continuously with its r/D or r/W
ratio; a real tee/branch's K varies with the branch/main area ratio and the
flow-split fraction; a real damper's K varies with blade angle). Treat every
value here as a first-pass planning figure, not a certified design value, and
cross-check against a real ASHRAE/CIBSE copy (or a manufacturer's own published
K-factor data) before relying on a result for a real job. Disclosed in the
duct Index Leg UI.
"""

from __future__ import annotations

from dataclasses import dataclass

ROUND_FAMILY = "round"          # serves circular AND flat oval (round-equivalent)
RECTANGULAR_FAMILY = "rectangular"


@dataclass(frozen=True)
class Fitting:
    """One entry in the fitting K-factor catalogue.

    `family` is a labelling/grouping aid for the picker UI, not an
    enforcement rule -- dp = K * Pv is shape-agnostic, so a round-family K
    can still be applied against a rectangular duct's velocity pressure if a
    user picks one; the web layer tags the row with its family so this stays
    visible rather than hidden.

    `thumbnail_key` groups fittings onto a shared category icon (one drawing
    per category, not per fitting -- see SPEC-duct-sizing.md's Phase C
    section for why).
    """

    key: str
    label: str
    family: str
    k: float
    thumbnail_key: str


# ── Round family (circular + flat oval) ──────────────────────────────────────
_ROUND_FITTINGS: tuple[Fitting, ...] = (
    Fitting("round_elbow_90_smooth_r1.5", "90° Smooth Bend (r/D 1.5)", ROUND_FAMILY, 0.22, "elbow_smooth"),
    Fitting("round_elbow_90_smooth_r1.0", "90° Smooth Bend (r/D 1.0)", ROUND_FAMILY, 0.33, "elbow_smooth"),
    Fitting("round_elbow_90_mitred", "90° Mitred Elbow", ROUND_FAMILY, 1.20, "elbow_mitred"),
    Fitting("round_elbow_45_smooth", "45° Smooth Bend", ROUND_FAMILY, 0.15, "elbow_smooth"),
    Fitting("round_tee_branch_90", "Tee — 90° Branch Takeoff", ROUND_FAMILY, 1.00, "tee_branch"),
    Fitting("round_tee_straight", "Tee — Straight-Through Main", ROUND_FAMILY, 0.15, "tee_straight"),
    Fitting("round_reducer_gradual", "Gradual Reducer (Contraction)", ROUND_FAMILY, 0.05, "transition"),
    Fitting("round_enlarger_gradual", "Gradual Enlarger (Expansion)", ROUND_FAMILY, 0.20, "transition"),
    Fitting("round_damper_open", "Butterfly Damper (Fully Open)", ROUND_FAMILY, 0.20, "damper"),
    Fitting("round_entry_sharp", "Duct Entry (Sharp-Edged)", ROUND_FAMILY, 0.50, "entry"),
    Fitting("round_exit", "Duct Exit to Space/Plenum", ROUND_FAMILY, 1.00, "exit"),
)

# ── Rectangular family ────────────────────────────────────────────────────────
_RECTANGULAR_FITTINGS: tuple[Fitting, ...] = (
    Fitting("rect_elbow_90_mitred_no_vanes", "90° Mitred Elbow (No Vanes)", RECTANGULAR_FAMILY, 1.30, "elbow_mitred"),
    Fitting("rect_elbow_90_mitred_vanes", "90° Mitred Elbow (Turning Vanes)", RECTANGULAR_FAMILY, 0.40, "elbow_vaned"),
    Fitting("rect_elbow_90_radiused", "90° Radiused Elbow (r/W 1.0)", RECTANGULAR_FAMILY, 0.25, "elbow_smooth"),
    Fitting("rect_tee_branch_90", "Tee — 90° Branch Takeoff", RECTANGULAR_FAMILY, 1.00, "tee_branch"),
    Fitting("rect_tee_straight", "Tee — Straight-Through Main", RECTANGULAR_FAMILY, 0.15, "tee_straight"),
    Fitting("rect_transition_contraction", "Transition (Contraction)", RECTANGULAR_FAMILY, 0.05, "transition"),
    Fitting("rect_transition_expansion", "Transition (Expansion)", RECTANGULAR_FAMILY, 0.20, "transition"),
    Fitting("rect_damper_open", "Blade Damper (Fully Open)", RECTANGULAR_FAMILY, 0.25, "damper"),
)

FITTINGS: tuple[Fitting, ...] = _ROUND_FITTINGS + _RECTANGULAR_FITTINGS

FITTINGS_BY_KEY: dict[str, Fitting] = {f.key: f for f in FITTINGS}


def fittings_for_shape(shape: str) -> tuple[Fitting, ...]:
    """Fittings offered for a given duct-sizing shape -- round family for
    circular/flat oval (this app treats flat oval via its round-duct
    equivalent diameter throughout, so the same fittings apply), rectangular
    family for rectangular. Raises ValueError for an unrecognised shape."""
    if shape in ("circular", "flat_oval"):
        return _ROUND_FITTINGS
    if shape == "rectangular":
        return _RECTANGULAR_FITTINGS
    raise ValueError(f"unknown duct shape: {shape!r}")


def fitting_pressure_drop(k: float, velocity_pressure_pa: float) -> float:
    """Fitting pressure loss (Pa): dp = K * Pv."""
    return k * velocity_pressure_pa


def straight_pressure_drop(length_m: float, friction_rate_pa_per_m: float) -> float:
    """Straight-duct pressure loss (Pa) over a run of the given length."""
    if length_m <= 0:
        raise ValueError(f"length must be greater than zero (got {length_m!r})")
    return length_m * friction_rate_pa_per_m


def accessory_pressure_drop(dp_pa: float) -> float:
    """Pressure loss (Pa) for a manually-entered "Accessory" index-leg row --
    louvers, attenuators, VCD/FD dampers, single-blade dampers, grilles and
    similar items that don't have a well-standardised K-factor the way an
    elbow does (manufacturers publish their own selection charts/performance
    data for these, not a generic loss coefficient). Rather than invent a
    representative K-factor the way the fittings above do, this is a direct
    pass-through of a value the user reads off their own manufacturer data --
    Paul's explicit call (8 July 2026): "for custom items we add the pressure
    drop directly, we may add some predefined K factors for some elements
    later." Kept as its own small function (identity plus validation) rather
    than inlined in the web layer, so the "must be a real, non-negative
    pressure" rule lives in one tested place, same as every other pressure-
    drop function in this module.
    """
    if dp_pa < 0:
        raise ValueError(f"pressure drop must be zero or greater (got {dp_pa!r})")
    return dp_pa


__all__ = [
    "ROUND_FAMILY", "RECTANGULAR_FAMILY", "Fitting",
    "FITTINGS", "FITTINGS_BY_KEY", "fittings_for_shape",
    "fitting_pressure_drop", "straight_pressure_drop", "accessory_pressure_drop",
]
