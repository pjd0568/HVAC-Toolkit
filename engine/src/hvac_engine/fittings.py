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

Typical K figures align with SMACNA HVAC Systems Duct Design / ASHRAE
supplemental fitting-loss tables (single-point planning values).
"""

from __future__ import annotations

from dataclasses import dataclass

ROUND_FAMILY = "round"          # serves circular AND flat oval (round-equivalent)
RECTANGULAR_FAMILY = "rectangular"

# Picker filter categories (also used as shared schematic groups).
CATEGORY_ELBOW = "elbow"
CATEGORY_JUNCTION = "junction"
CATEGORY_TRANSITION = "transition"
CATEGORY_ENTRY = "entry"
CATEGORY_EXIT = "exit"
CATEGORY_OBSTRUCTION = "obstruction"

CATEGORIES: tuple[tuple[str, str], ...] = (
    (CATEGORY_ELBOW, "Elbows"),
    (CATEGORY_JUNCTION, "Junctions"),
    (CATEGORY_TRANSITION, "Transitions"),
    (CATEGORY_ENTRY, "Entries"),
    (CATEGORY_EXIT, "Exits"),
    (CATEGORY_OBSTRUCTION, "Obstructions"),
)


@dataclass(frozen=True)
class Fitting:
    """One entry in the fitting K-factor catalogue.

    `family` is a labelling/grouping aid for the picker UI, not an
    enforcement rule -- dp = K * Pv is shape-agnostic, so a round-family K
    can still be applied against a rectangular duct's velocity pressure if a
    user picks one; the web layer tags the row with its family so this stays
    visible rather than hidden.

    `category` drives the visual picker filter chips. `icon` is the static
    image stem under ``images/duct-fittings/{icon}.png`` (one drawing per
    fitting). `thumbnail_key` remains as an alias of `category` for older
    callers.
    """

    key: str
    label: str
    family: str
    k: float
    category: str
    icon: str

    @property
    def thumbnail_key(self) -> str:
        return self.category


# ── Round family (circular + flat oval) ──────────────────────────────────────
_ROUND_FITTINGS: tuple[Fitting, ...] = (
    Fitting("round_elbow_90_smooth_r1.5", "90° Smooth Elbow (r/D 1.5)", ROUND_FAMILY, 0.15, CATEGORY_ELBOW, "round_elbow_90_smooth_r1.5"),
    Fitting("round_elbow_90_smooth_r1.0", "90° Smooth Elbow (r/D 1.0)", ROUND_FAMILY, 0.22, CATEGORY_ELBOW, "round_elbow_90_smooth_r1.0"),
    Fitting("round_elbow_90_mitred", "90° Mitred Elbow", ROUND_FAMILY, 1.20, CATEGORY_ELBOW, "round_elbow_90_mitred"),
    Fitting("round_elbow_90_5piece", "90° 5-Piece Elbow (r/D 1.5)", ROUND_FAMILY, 0.24, CATEGORY_ELBOW, "round_elbow_90_5piece"),
    Fitting("round_elbow_45_smooth", "45° Smooth Elbow", ROUND_FAMILY, 0.09, CATEGORY_ELBOW, "round_elbow_45_smooth"),
    Fitting("round_flex_elbow_90", "Flexible Duct 90° Elbow", ROUND_FAMILY, 0.50, CATEGORY_ELBOW, "round_flex_elbow_90"),
    Fitting("round_tee_branch_90", "Tee — 90° Branch Takeoff", ROUND_FAMILY, 1.20, CATEGORY_JUNCTION, "round_tee_branch_90"),
    Fitting("round_tee_straight", "Tee — Straight-Through Main", ROUND_FAMILY, 0.20, CATEGORY_JUNCTION, "round_tee_straight"),
    Fitting("round_wye_45_branch", "45° Wye — Branch Flow", ROUND_FAMILY, 0.40, CATEGORY_JUNCTION, "round_wye_45_branch"),
    Fitting("round_reducer_gradual", "Conical Transition — Converging", ROUND_FAMILY, 0.15, CATEGORY_TRANSITION, "round_reducer_gradual"),
    Fitting("round_enlarger_gradual", "Conical Transition — Diverging", ROUND_FAMILY, 0.40, CATEGORY_TRANSITION, "round_enlarger_gradual"),
    Fitting("round_to_rect_transition", "Round → Rectangular Transition", ROUND_FAMILY, 0.30, CATEGORY_TRANSITION, "round_to_rect_transition"),
    Fitting("round_entry_sharp", "Abrupt / Flush Entrance", ROUND_FAMILY, 0.50, CATEGORY_ENTRY, "round_entry_sharp"),
    Fitting("round_entry_bellmouth", "Bellmouth Entrance", ROUND_FAMILY, 0.05, CATEGORY_ENTRY, "round_entry_bellmouth"),
    Fitting("round_exit", "Abrupt Exit / Free Discharge", ROUND_FAMILY, 1.00, CATEGORY_EXIT, "round_exit"),
    Fitting("round_damper_open", "Butterfly Damper (Fully Open)", ROUND_FAMILY, 0.20, CATEGORY_OBSTRUCTION, "round_damper_open"),
    Fitting("round_screen_grille", "Screen / Grille / Mesh", ROUND_FAMILY, 0.50, CATEGORY_OBSTRUCTION, "screen_grille"),
)

# ── Rectangular family ────────────────────────────────────────────────────────
_RECTANGULAR_FITTINGS: tuple[Fitting, ...] = (
    Fitting("rect_elbow_90_mitred_no_vanes", "90° Mitred Elbow (No Vanes)", RECTANGULAR_FAMILY, 1.20, CATEGORY_ELBOW, "rect_elbow_90_mitred_no_vanes"),
    Fitting("rect_elbow_90_mitred_vanes", "90° Mitred Elbow (Turning Vanes)", RECTANGULAR_FAMILY, 0.25, CATEGORY_ELBOW, "rect_elbow_90_mitred_vanes"),
    Fitting("rect_elbow_90_radiused", "90° Smooth Radius Elbow", RECTANGULAR_FAMILY, 0.20, CATEGORY_ELBOW, "rect_elbow_90_radiused"),
    Fitting("rect_tee_branch_90", "Tee — 90° Branch Takeoff", RECTANGULAR_FAMILY, 1.00, CATEGORY_JUNCTION, "rect_tee_branch_90"),
    Fitting("rect_tee_straight", "Tee — Straight-Through Main", RECTANGULAR_FAMILY, 0.15, CATEGORY_JUNCTION, "rect_tee_straight"),
    Fitting("rect_transition_contraction", "Pyramidal Transition — Converging", RECTANGULAR_FAMILY, 0.15, CATEGORY_TRANSITION, "rect_transition_contraction"),
    Fitting("rect_transition_expansion", "Pyramidal Transition — Diverging", RECTANGULAR_FAMILY, 0.40, CATEGORY_TRANSITION, "rect_transition_expansion"),
    Fitting("rect_to_round_transition", "Rectangular → Round Transition", RECTANGULAR_FAMILY, 0.30, CATEGORY_TRANSITION, "round_to_rect_transition"),
    Fitting("rect_entry_abrupt", "Abrupt Entrance", RECTANGULAR_FAMILY, 0.50, CATEGORY_ENTRY, "rect_entry_abrupt"),
    Fitting("rect_exit_abrupt", "Abrupt Exit", RECTANGULAR_FAMILY, 1.00, CATEGORY_EXIT, "rect_exit_abrupt"),
    Fitting("rect_damper_open", "Blade Damper (Fully Open)", RECTANGULAR_FAMILY, 0.25, CATEGORY_OBSTRUCTION, "rect_damper_open"),
    Fitting("rect_screen_grille", "Screen / Grille / Mesh", RECTANGULAR_FAMILY, 0.50, CATEGORY_OBSTRUCTION, "screen_grille"),
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
    "CATEGORY_ELBOW", "CATEGORY_JUNCTION", "CATEGORY_TRANSITION",
    "CATEGORY_ENTRY", "CATEGORY_EXIT", "CATEGORY_OBSTRUCTION",
    "CATEGORIES",
    "FITTINGS", "FITTINGS_BY_KEY", "fittings_for_shape",
    "fitting_pressure_drop", "straight_pressure_drop", "accessory_pressure_drop",
]
