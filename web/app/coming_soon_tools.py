"""Coming-soon tool catalogue — placeholders linked from V2 suite menus.

IDs must match ``COMING_SOON_MODULES`` / ``MODULES`` in ``app.access``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComingSoonTool:
    module_id: str
    slug: str
    title: str
    lead: str
    planned_inputs: tuple[str, ...]
    suite: str  # psychro | duct | pipe | refrig | acoustics | more
    nav: str
    active: str
    picker_desc: str


# Roadmap tools with placeholder pages (refrigeration Soon pages are bespoke).
COMING_SOON_TOOLS: dict[str, ComingSoonTool] = {
    "room.load": ComingSoonTool(
        module_id="room.load",
        slug="room-load",
        title="Room load calculator",
        lead="Peak sensible and latent cooling / heating loads from fabric, orientation, and gains.",
        planned_inputs=(
            "Room dimensions",
            "U-values (walls, glazing, roof)",
            "Orientation and internal gains (occupancy, lighting, IT)",
        ),
        suite="duct",
        nav="duct",
        active="room_load",
        picker_desc="Simplified steady-state peak loads (kW) with a clear component breakdown.",
    ),
    "air.grille_throw": ComingSoonTool(
        module_id="air.grille_throw",
        slug="grille-throw",
        title="Grille throw & air displacement",
        lead="Throw to terminal velocities with a Coanda risk warning when mounting is too far from the ceiling.",
        planned_inputs=(
            "Volumetric airflow",
            "Grille free area and discharge velocity",
            "Mounting height / distance to ceiling",
        ),
        suite="duct",
        nav="duct",
        active="grille_throw",
        picker_desc="Throw to 0.5 and 0.25 m/s; visual Coanda failure warning.",
    ),
    "pipe.expansion_vessel": ComingSoonTool(
        module_id="pipe.expansion_vessel",
        slug="expansion-vessel",
        title="Expansion vessel sizing",
        lead="Minimum sealed-system vessel volume and pre-charge from system volume, static head, and temperatures.",
        planned_inputs=(
            "Total system water volume",
            "Static head (m)",
            "Maximum flow / return temperatures",
        ),
        suite="pipe",
        nav="pipe",
        active="expansion_vessel",
        picker_desc="Thermal expansion → vessel litres and initial pre-charge pressure.",
    ),
    "pipe.buffer_tank": ComingSoonTool(
        module_id="pipe.buffer_tank",
        slug="buffer-tank",
        title="Buffer tank sizing",
        lead="Minimum system volume to limit compressor or boiler short-cycling.",
        planned_inputs=(
            "Minimum plant output (kW)",
            "Maximum starts per hour",
            "System temperature delta",
        ),
        suite="pipe",
        nav="pipe",
        active="buffer_tank",
        picker_desc="Short-cycle protection volume for heat pumps and chillers.",
    ),
    "iaq.co2": ComingSoonTool(
        module_id="iaq.co2",
        slug="co2",
        title="Fresh air & CO₂ modelling",
        lead="Time to reach a critical CO₂ threshold under peak occupancy from room volume and outdoor air.",
        planned_inputs=(
            "Room volume",
            "Fresh air flow rate",
            "Occupancy / CO₂ generation rates",
        ),
        suite="psychro",
        nav="psychro",
        active="iaq_co2",
        picker_desc="Build-up equation → time to e.g. 1,000 ppm and steady-state ppm.",
    ),
    "acoustics.duct_nr": ComingSoonTool(
        module_id="acoustics.duct_nr",
        slug="duct-nr",
        title="Ductwork attenuation & room NR",
        lead="Octave-band path from equipment SWL through duct attenuators to receiver dBA and NR.",
        planned_inputs=(
            "Equipment SWL across 8 octave bands (63 Hz–8 kHz)",
            "Attenuation steps (duct, bends, lined plenums, silencers)",
        ),
        suite="acoustics",
        nav="acoustics",
        active="acoustics_duct_nr",
        picker_desc="Band-by-band attenuation → final dBA and Noise Rating.",
    ),
    "acoustics.barrier": ComingSoonTool(
        module_id="acoustics.barrier",
        slug="barrier",
        title="Acoustic barrier screening",
        lead="Maekawa path-length difference → insertion loss per frequency band.",
        planned_inputs=(
            "Source, receiver, and barrier heights",
            "Horizontal distances source–barrier and barrier–receiver",
        ),
        suite="acoustics",
        nav="acoustics",
        active="acoustics_barrier",
        picker_desc="Decibel reduction per band for outdoor plant screens.",
    ),
}


def tools_for_suite(suite: str) -> list[ComingSoonTool]:
    return [t for t in COMING_SOON_TOOLS.values() if t.suite == suite]


def tool_by_slug(slug: str) -> ComingSoonTool | None:
    for t in COMING_SOON_TOOLS.values():
        if t.slug == slug:
            return t
    return None
