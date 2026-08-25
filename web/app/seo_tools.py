"""Public SEO tool landing pages — indexable marketing copy that CTAs into the app.

These pages are intentionally outside login. Calculators stay gated; Google indexes
the landings instead of empty tool UIs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolLanding:
    slug: str
    title: str  # <title> / H1-adjacent
    meta_description: str
    h1: str
    eyebrow: str
    lead: str
    how_heading: str
    how_body: str
    concept_heading: str
    concept_body: str
    formulas_heading: str
    formulas: tuple[str, ...]
    cta_app_endpoint: str  # flask endpoint after login
    cta_label: str
    related_slugs: tuple[str, ...] = ()


LANDINGS: dict[str, ToolLanding] = {
    "psychrometric-calculator": ToolLanding(
        slug="psychrometric-calculator",
        title="Free Psychrometric Calculator & Chart | HVAC-calcs.app",
        meta_description=(
            "Free online psychrometric calculator for HVAC engineers. Look up dry-bulb, "
            "wet-bulb, RH, dew point, enthalpy and humidity ratio. SI and imperial. "
            "Try without an account on HVAC-calcs.app."
        ),
        h1="Free psychrometric calculator",
        eyebrow="Psychrometrics",
        lead=(
            "Find moist-air properties from common HVAC inputs — dry-bulb and relative "
            "humidity, wet-bulb, or dew point — with SI or imperial units. Use the free "
            "teaser on the homepage, or open the full suite for multi-point charts and "
            "process tools."
        ),
        how_heading="How to use this psychrometric calculator",
        how_body=(
            "Enter two independent state properties (for example dry-bulb temperature and "
            "relative humidity). The calculator solves the psychrometric state and reports "
            "wet-bulb, dew point, humidity ratio, specific enthalpy and density. Switch "
            "between SI and IP units at any time. For a free single-point check without "
            "signing in, use the calculator on the homepage. Full-suite tools add mixed "
            "air, coils, AHU flows and an interactive chart."
        ),
        concept_heading="What is a psychrometric calculator?",
        concept_body=(
            "A psychrometric calculator evaluates the thermodynamic properties of moist air "
            "used in heating, ventilation and air-conditioning design. Engineers use it to "
            "size coils, check supply conditions, and verify comfort and condensation risk "
            "without reading a printed psychrometric chart by hand."
        ),
        formulas_heading="Core moist-air relationships",
        formulas=(
            "Humidity ratio W relates vapour and dry-air mass: W = m_v / m_da (kg/kg_da).",
            "Relative humidity φ ≈ p_v / p_sat(T_db) at the same dry-bulb temperature.",
            "Specific enthalpy of moist air (approximate): h ≈ c_pda·T_db + W·(h_g0 + c_pv·T_db).",
            "Dew-point temperature is the saturation temperature at the partial pressure of water vapour.",
        ),
        cta_app_endpoint="v2.single_point",
        cta_label="Open single-point tool",
        related_slugs=("mixed-air-calculator", "duct-sizing-calculator"),
    ),
    "mixed-air-calculator": ToolLanding(
        slug="mixed-air-calculator",
        title="Free Psychrometric Mixed Air Calculator | HVAC-calcs.app",
        meta_description=(
            "Online mixed-air psychrometric calculator for HVAC design. Blend outdoor and "
            "return airflows, get mixed dry-bulb, humidity and enthalpy. SI and imperial. "
            "14-day free trial on HVAC-calcs.app."
        ),
        h1="Psychrometric mixed air calculator",
        eyebrow="Psychrometrics",
        lead=(
            "Blend outdoor and return airstreams by volume flow and state to find the mixed "
            "condition before the coil or heat recovery. Built for day-to-day AHU and "
            "packaged-unit design checks."
        ),
        how_heading="How to use this mixed air calculator",
        how_body=(
            "Enter outdoor and return dry-bulb and moisture state (RH, wet-bulb or dew point) "
            "plus each stream’s volume flow. The tool computes the mixed dry-bulb, humidity "
            "ratio and enthalpy assuming adiabatic mixing of dry-air mass flows. Use the "
            "result as the entering condition for a cooling-coil or heating calculation in "
            "the suite."
        ),
        concept_heading="What is mixed air in HVAC?",
        concept_body=(
            "Mixed air is the blend of outdoor air and recirculated return air that enters "
            "an air-handling unit. Designers set the outdoor-air fraction for ventilation "
            "and economy cycles; the mixed state drives coil load and supply-air "
            "psychrometrics."
        ),
        formulas_heading="Adiabatic mixing (mass-weighted)",
        formulas=(
            "Dry-air mass flows from volume flow and density: ṁ_da = ρ_da · Q.",
            "Mixed humidity ratio: W_m = (ṁ_da,o·W_o + ṁ_da,r·W_r) / (ṁ_da,o + ṁ_da,r).",
            "Mixed enthalpy: h_m = (ṁ_da,o·h_o + ṁ_da,r·h_r) / (ṁ_da,o + ṁ_da,r).",
            "Mixed dry-bulb follows from the mixed state (h_m, W_m) on the psychrometric chart.",
        ),
        cta_app_endpoint="v2.mixed_air",
        cta_label="Open mixed-air tool",
        related_slugs=("psychrometric-calculator", "duct-sizing-calculator"),
    ),
    "duct-sizing-calculator": ToolLanding(
        slug="duct-sizing-calculator",
        title="Duct Sizing Calculator — Velocity & Pressure Drop | HVAC-calcs.app",
        meta_description=(
            "Online HVAC duct sizing calculator for circular, rectangular and flat-oval "
            "ducts. Size by velocity or pressure gradient with friction loss. SI and "
            "imperial. Trial on HVAC-calcs.app."
        ),
        h1="Duct sizing calculator",
        eyebrow="Air distribution",
        lead=(
            "Size circular, rectangular and flat-oval ducts from airflow and design velocity "
            "or target pressure gradient. Review friction loss and equivalent diameter before "
            "locking a size for fabrication."
        ),
        how_heading="How to use this duct sizing calculator",
        how_body=(
            "Enter design volume flow and choose a sizing method (target velocity or pressure "
            "gradient). Select a shape catalogue and review candidate sizes with velocity and "
            "unit pressure drop. Use the index-leg builder in the app when you need a full "
            "path pressure drop with fittings."
        ),
        concept_heading="What does a duct sizer calculate?",
        concept_body=(
            "Duct sizing balances airflow conveyance against noise, energy and space. Higher "
            "velocity shrinks duct size but raises friction, regenerated noise and fan power. "
            "Engineers pick a size that meets the design velocity band and pressure budget."
        ),
        formulas_heading="Key air-side relationships",
        formulas=(
            "Mean velocity: V = Q / A (m/s) with Q in m³/s and A the internal cross-section.",
            "Darcy–Weisbach friction: Δp/L = f · (ρ · V²) / (2 · D_h).",
            "Hydraulic diameter for rectangular ducts: D_h = 2·a·b / (a + b).",
            "Equivalent circular diameter is often used to compare rectangular options on a common friction basis.",
        ),
        cta_app_endpoint="v2.duct",
        cta_label="Open duct sizing tool",
        related_slugs=("chilled-water-pipe-sizing", "mixed-air-calculator"),
    ),
    "chilled-water-pipe-sizing": ToolLanding(
        slug="chilled-water-pipe-sizing",
        title="Chilled Water Pipe Sizing Calculator | HVAC-calcs.app",
        meta_description=(
            "Chilled water pipe sizing tool for HVAC hydronics. Flow from load and ΔT, "
            "DN catalogue with velocity and pressure-gradient limits. Water and glycol. "
            "SI and imperial on HVAC-calcs.app."
        ),
        h1="Chilled water pipe sizing calculator",
        eyebrow="Hydronics",
        lead=(
            "Convert cooling load and temperature difference into volume flow, then evaluate "
            "standard pipe sizes against velocity and pressure-gradient design limits — "
            "including aqueous glycol fluids."
        ),
        how_heading="How to use this chilled water pipe sizer",
        how_body=(
            "Enter cooling capacity and flow/return ΔT (or a known volume flow), choose fluid "
            "and working temperature, then review every catalogue DN with traffic-light status "
            "for velocity and Pa/m. Pick a size for the detail panel (bore, friction, fluid "
            "properties). Continue into the system pressure-drop builder for fittings and pump head."
        ),
        concept_heading="Why size chilled water pipe carefully?",
        concept_body=(
            "Undersized chilled-water pipe raises pump head and noise; oversized pipe wastes "
            "capital and can hurt control. Design guides set preferred velocity and pressure "
            "gradient bands so coils get design flow without excessive energy use."
        ),
        formulas_heading="Hydronic flow and friction",
        formulas=(
            "Volume flow from load: Q = Φ / (ρ · c_p · ΔT) (m³/s for SI coherent units).",
            "Mean velocity: V = Q / A with A the internal bore area.",
            "Darcy friction loss along length L: Δp = f · (L/D) · (ρ · V² / 2).",
            "Glycol mixtures change ρ, μ and c_p — property correlations must match the fluid and temperature.",
        ),
        cta_app_endpoint="v2.pipe",
        cta_label="Open pipe sizing tool",
        related_slugs=("lthw-pipe-pressure-drop", "duct-sizing-calculator"),
    ),
    "lthw-pipe-pressure-drop": ToolLanding(
        slug="lthw-pipe-pressure-drop",
        title="LTHW Pipe Pressure Drop & Pump Head Calculator | HVAC-calcs.app",
        meta_description=(
            "LTHW and hydronic pipe pressure-drop calculator. Build a circuit with pipe "
            "lengths, fittings and devices to total ΔP and pump duty. SI and imperial. "
            "HVAC-calcs.app."
        ),
        h1="LTHW pipe pressure drop calculator",
        eyebrow="Hydronics",
        lead=(
            "Build a heating or chilled-water index run: pipe sections, fittings (K-values), "
            "and fixed device losses — then read total pressure drop and pump head including "
            "static lift where needed."
        ),
        how_heading="How to use this pipe pressure-drop calculator",
        how_body=(
            "Start from a sized flow (or enter flow directly). Add straight lengths and "
            "fittings from the catalogue, plus any manual ΔP devices. The schedule totals "
            "friction and minor losses so you can set pump duty. Use open vs pressurised "
            "options when static head and lift matter."
        ),
        concept_heading="What is an index-leg pressure drop?",
        concept_body=(
            "The index circuit is the path with the greatest resistance at design flow. "
            "Pump head must overcome that path’s friction, fittings and equipment losses "
            "(plus static effects in open systems). Calculating it section-by-section avoids "
            "guesswork and undersized pumps."
        ),
        formulas_heading="Pressure drop building blocks",
        formulas=(
            "Straight pipe: Δp_f = f · (L/D) · (ρ · V² / 2).",
            "Fittings via loss coefficient: Δp_m = K · (ρ · V² / 2).",
            "Devices (valves, coils) often enter as a manufacturer Δp at design flow.",
            "Pump head H ≈ Δp_total / (ρ · g), reported in m or kPa as preferred.",
        ),
        cta_app_endpoint="v2.pipe_system",
        cta_label="Open system pressure-drop tool",
        related_slugs=("chilled-water-pipe-sizing", "duct-sizing-calculator"),
    ),
}


def list_landings() -> list[ToolLanding]:
    return list(LANDINGS.values())


def get_landing(slug: str) -> ToolLanding | None:
    return LANDINGS.get(slug)
