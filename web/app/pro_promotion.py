"""Contextual Free → Pro promotion copy and Free/Pro comparison.

Single source for post-result cards, the upgrade dialog, and the locked-module
access gate. Analytics tool ids match ``app.analytics.TOOLS``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.access import PRICE_ANNUAL_GBP, PRICE_MONTHLY_GBP, get_entitlement


@dataclass(frozen=True)
class CompareRow:
    feature: str
    free: bool
    pro: bool


@dataclass(frozen=True)
class ProPrompt:
    """One Free→Pro message keyed by free tool or locked suite module."""

    key: str
    heading: str
    body: str
    card_blurb: str
    source_tool: str
    target_tool: str
    next_endpoint: str | None = None
    processes: tuple[str, ...] = ()
    # Static sample under /static — shown on the stage CTA for export proof.
    example_export_path: str = "examples/sample-pro-report.pdf"
    example_export_label: str = "See a sample Pro PDF report"


# Compact matrix shown in the dialog and on the access gate. No project storage.
COMPARE_ROWS: tuple[CompareRow, ...] = (
    CompareRow("Single-point psychrometrics", True, True),
    CompareRow("Interactive psychrometric workflows", False, True),
    CompareRow("Single-section duct sizing", True, True),
    CompareRow("Duct index-leg workflow", False, True),
    CompareRow("Single-section pipe sizing", True, True),
    CompareRow("Pipe system / pump-head workflow", False, True),
    CompareRow("Refrigerant PT", True, True),
    CompareRow("Superheat / subcooling", True, True),
    CompareRow("DX pipe sizing", False, True),
    CompareRow("Advanced HVAC processes / AHU design", False, True),
    CompareRow("Pro PDF / CSV / chart outputs", False, True),
)

_PSYCHRO_PROCESSES = (
    "Mixed air",
    "Cooling coil",
    "Heating / humidification",
    "Adiabatic cooling",
    "Desiccant",
    "AHU design",
)

# Free calculators → recommended Pro workflow.
_FREE_PROMPTS: dict[str, ProPrompt] = {
    "psychrometric_single": ProPrompt(
        key="psychrometric_single",
        heading="Unlock the full psychrometric suite in Pro",
        body=(
            "Free resolves a single air state. Pro opens the interactive multi-point "
            "chart and the full psychrometric workflow set — mixed air, coils, "
            "humidification, adiabatic cooling, desiccant and AHU design — plus PDF, "
            "CSV and chart exports for the job file."
        ),
        card_blurb=(
            "Continue into the full Pro psychrometric suite: interactive chart, "
            "process tools and exportable reports."
        ),
        source_tool="psychrometric_single",
        target_tool="interactive_chart",
        next_endpoint="v2.interactive_chart",
        processes=_PSYCHRO_PROCESSES,
    ),
    "duct_sizing": ProPrompt(
        key="duct_sizing",
        heading="Unlock the full duct index-leg calculator in Pro",
        body=(
            "Free sizes one duct section. Pro builds the complete index leg — "
            "straight runs, fittings and equipment pressure drops in one schedule — "
            "and unlocks PDF, CSV and chart exports."
        ),
        card_blurb=(
            "Continue into the Pro duct index-leg calculator for the full run and "
            "exportable reports."
        ),
        source_tool="duct_sizing",
        target_tool="duct_index_leg",
        next_endpoint="v2.duct_index_leg",
    ),
    "pipe_sizing": ProPrompt(
        key="pipe_sizing",
        heading="Unlock the full pipe circuit calculator in Pro",
        body=(
            "Free sizes one pipe section. Pro builds the complete hydronic circuit — "
            "pipe runs, fittings, devices and required pump head — and unlocks PDF, "
            "CSV and chart exports."
        ),
        card_blurb=(
            "Continue into the Pro pipe-system calculator for the full circuit, pump "
            "head and exportable reports."
        ),
        source_tool="pipe_sizing",
        target_tool="pipe_system",
        next_endpoint="v2.pipe_system",
    ),
    "refrigerant_pt": ProPrompt(
        key="refrigerant_pt",
        heading="Continue into the complete refrigeration workflow",
        body=(
            "Free gives the PT table for saturation checks. Pro continues into DX pipe "
            "sizing for suction, liquid and discharge lines."
        ),
        card_blurb=(
            "Need suction, liquid or discharge line sizes? Continue with DX pipe sizing in Pro."
        ),
        source_tool="refrigerant_pt",
        target_tool="dx_pipe_sizing",
        next_endpoint="v2.refrig_pipe_sizer",
    ),
    "superheat_subcooling": ProPrompt(
        key="superheat_subcooling",
        heading="Continue into the complete refrigeration workflow",
        body=(
            "Free checks superheat and subcooling from field pressures and temperatures. "
            "Pro continues into DX pipe sizing for the circuit."
        ),
        card_blurb="DX pipe sizing for the circuit is available in Pro.",
        source_tool="superheat_subcooling",
        target_tool="dx_pipe_sizing",
        next_endpoint="v2.refrig_pipe_sizer",
    ),
}

# Locked suite modules → capability-first gate copy.
_LOCKED_PROMPTS: dict[str, ProPrompt] = {
    "duct.index_leg": ProPrompt(
        key="duct.index_leg",
        heading="Duct Index Leg is a Pro workflow",
        body=(
            "Build the complete duct run, evaluate each section and determine the "
            "index leg within one workflow."
        ),
        card_blurb="",
        source_tool="duct_index_leg",
        target_tool="duct_index_leg",
        next_endpoint="v2.duct_index_leg",
    ),
    "pipe.system": ProPrompt(
        key="pipe.system",
        heading="Pipe System is a Pro workflow",
        body=(
            "Assemble the hydronic circuit, add fittings and devices, and calculate "
            "pump head in one workflow."
        ),
        card_blurb="",
        source_tool="pipe_system",
        target_tool="pipe_system",
        next_endpoint="v2.pipe_system",
    ),
    "psychro.interactive_chart": ProPrompt(
        key="psychro.interactive_chart",
        heading="The multi-point psychrometric chart is a Pro workflow",
        body=(
            "Plot multiple air states and process lines on the interactive chart, then "
            "continue into mixed air, coil and AHU design tools."
        ),
        card_blurb="",
        source_tool="interactive_chart",
        target_tool="interactive_chart",
        next_endpoint="v2.interactive_chart",
        processes=_PSYCHRO_PROCESSES,
    ),
    "psychro.mixed_air": ProPrompt(
        key="psychro.mixed_air",
        heading="Mixed Air is a Pro workflow",
        body="Blend outdoor and return air and carry the mixed state into the next process.",
        card_blurb="",
        source_tool="mixed_air",
        target_tool="mixed_air",
        next_endpoint="v2.mixed_air",
    ),
    "psychro.cooling_coil": ProPrompt(
        key="psychro.cooling_coil",
        heading="Cooling Coil is a Pro workflow",
        body="Size coil duty from on-coil and off-coil states as part of the psychrometric suite.",
        card_blurb="",
        source_tool="cooling_coil",
        target_tool="cooling_coil",
        next_endpoint="v2.cooling_coil",
    ),
    "psychro.desiccant": ProPrompt(
        key="psychro.desiccant",
        heading="Desiccant dehumidification is a Pro workflow",
        body="Model desiccant process states within the psychrometric suite.",
        card_blurb="",
        source_tool="desiccant",
        target_tool="desiccant",
        next_endpoint="v2.desiccant",
    ),
    "psychro.heat_humidify": ProPrompt(
        key="psychro.heat_humidify",
        heading="Heating & humidification is a Pro workflow",
        body="Follow heating and moisture addition between psychrometric states.",
        card_blurb="",
        source_tool="heat_humidify",
        target_tool="heat_humidify",
        next_endpoint="v2.heat_humidify",
    ),
    "psychro.adiabatic_cool": ProPrompt(
        key="psychro.adiabatic_cool",
        heading="Adiabatic cooling is a Pro workflow",
        body="Model adiabatic / evaporative cooling as part of the psychrometric suite.",
        card_blurb="",
        source_tool="adiabatic",
        target_tool="adiabatic",
        next_endpoint="v2.adiabatic_cool",
    ),
    "psychro.ahu": ProPrompt(
        key="psychro.ahu",
        heading="AHU Design is a Pro workflow",
        body="Chain psychrometric processes for AHU duty in one workflow.",
        card_blurb="",
        source_tool="ahu_design",
        target_tool="ahu_design",
        next_endpoint="v2.ahu",
    ),
    "refrig.pipe_sizer": ProPrompt(
        key="refrig.pipe_sizer",
        heading="DX Pipe Sizing is a Pro workflow",
        body="Size suction, liquid and discharge lines from the refrigeration suite.",
        card_blurb="",
        source_tool="dx_pipe_sizing",
        target_tool="dx_pipe_sizing",
        next_endpoint="v2.refrig_pipe_sizer",
    ),
}

# Public landing slug → free analytics tool key.
_LANDING_TO_FREE: dict[str, str] = {
    "psychrometric-calculator": "psychrometric_single",
    "duct-sizing-calculator": "duct_sizing",
    "chilled-water-pipe-sizing": "pipe_sizing",
    "refrigerant-pt-table": "refrigerant_pt",
    "superheat-subcooling": "superheat_subcooling",
}

# Free module_id → free analytics tool key (V2 shell).
_MODULE_TO_FREE: dict[str, str] = {
    "psychro.single_point": "psychrometric_single",
    "duct.sizer": "duct_sizing",
    "pipe.sizer": "pipe_sizing",
    "refrig.pt_table": "refrigerant_pt",
    "refrig.diagnostics": "superheat_subcooling",
}


def should_show_pro_promotion() -> bool:
    """Hide Free→Pro marketing when the visitor already has suite access."""
    try:
        return not get_entitlement().has_suite_access
    except Exception:
        return True


def prompt_for_free_tool(tool: str | None) -> ProPrompt | None:
    if not tool:
        return None
    return _FREE_PROMPTS.get(tool)


def prompt_for_locked_module(module_id: str | None) -> ProPrompt | None:
    if not module_id:
        return None
    return _LOCKED_PROMPTS.get(module_id)


def prompt_for_landing_slug(slug: str | None) -> ProPrompt | None:
    if not slug:
        return None
    return prompt_for_free_tool(_LANDING_TO_FREE.get(slug))


def prompt_for_free_module(module_id: str | None) -> ProPrompt | None:
    if not module_id:
        return None
    return prompt_for_free_tool(_MODULE_TO_FREE.get(module_id))


def price_footer() -> dict[str, str]:
    return {
        "monthly": PRICE_MONTHLY_GBP,
        "annual": PRICE_ANNUAL_GBP,
        "tagline": (
            "14 days free, then £"
            f"{PRICE_MONTHLY_GBP}/month. Cancel before the trial ends and pay nothing."
        ),
    }


__all__ = [
    "COMPARE_ROWS",
    "CompareRow",
    "ProPrompt",
    "price_footer",
    "prompt_for_free_module",
    "prompt_for_free_tool",
    "prompt_for_landing_slug",
    "prompt_for_locked_module",
    "should_show_pro_promotion",
]
