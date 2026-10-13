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
    # When set, /tools/<slug> renders this view with no login (same engine path).
    free_view: str = ""
    faqs: tuple[tuple[str, str], ...] = ()
    example: str = ""
    pro_next: str = ""
    pro_endpoint: str = ""


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
        free_view="v2.single_point",
        pro_endpoint="v2.interactive_chart",
        example=(
            "At sea-level pressure, 24 °C dry-bulb and 50% RH resolves to about "
            "17.1 °C wet-bulb, 12.9 °C dew point, 9.3 g/kg humidity ratio and "
            "47.8 kJ/kg enthalpy."
        ),
        pro_next=(
            "Need process lines, AHU analysis, charts and reports? "
            "Explore the full Psychrometric suite in Pro."
        ),
        faqs=(
            (
                "Which two inputs does a state need?",
                "Dry-bulb plus one of relative humidity, wet-bulb, dew point or humidity ratio. "
                "The page solves the rest at the stated barometric pressure.",
            ),
            (
                "Does this replace a printed chart?",
                "It is the same style of moist-air state check engineers do on a chart. "
                "Coil geometry, fan heat and control strategy are separate design steps.",
            ),
        ),
    ),
    "mixed-air-calculator": ToolLanding(
        slug="mixed-air-calculator",
        title="Psychrometric Mixed Air Calculator | HVAC-CALCS",
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
        free_view="v2.duct",
        pro_endpoint="v2.duct_index_leg",
        pro_next=(
            "Need the pressure drop for the complete run including fittings and equipment? "
            "Build the Index Leg in Pro."
        ),
        faqs=(
            (
                "What does one section include?",
                "Airflow and a size (or a velocity / friction target) for a single duct. "
                "Fittings, equipment and the index run are the Pro index-leg tool.",
            ),
            (
                "Which friction method is used?",
                "Darcy–Weisbach with an explicit Colebrook–White friction factor. "
                "See Methods for the equivalent-diameter rules and their limits.",
            ),
        ),
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
        free_view="v2.pipe",
        pro_endpoint="v2.pipe_system",
        pro_next=(
            "Need total circuit resistance and pump head? "
            "Build the complete Pipe System in Pro."
        ),
        faqs=(
            (
                "Is this the pump head?",
                "No. This page sizes one pipe from flow and checks velocity and pressure gradient. "
                "Circuit fittings, devices and pump head are the Pipe System workflow.",
            ),
            (
                "Which fluids are included?",
                "Water and the glycol mixtures implemented in the engine, at the mean temperature you enter. "
                "Property sources are listed on the Methods page.",
            ),
        ),
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
        pro_next=(
            "Pipe system pressure drop and pump head are part of HVAC-CALCS Pro."
        ),
    ),
    "refrigerant-pt-table": ToolLanding(
        slug="refrigerant-pt-table",
        title="Refrigerant PT Table | HVAC-CALCS",
        meta_description=(
            "Refrigerant pressure-temperature table for HVAC engineers. Bubble and dew "
            "pressures from CoolProp, in barg, for common refrigerants. No account required."
        ),
        h1="Refrigerant PT table",
        eyebrow="Refrigeration",
        lead=(
            "Look up bubble and dew pressure against temperature for a chosen refrigerant. "
            "Zeotropic blends show glide. Pressures are gauge (barg) relative to 1.01325 bar absolute."
        ),
        how_heading="How to use this PT table",
        how_body=(
            "Choose a refrigerant. The table lists saturation pressures across a fixed "
            "temperature range. Use dew pressure with evaporating temperature and bubble "
            "pressure with condensing temperature when you move on to line sizing."
        ),
        concept_heading="What is a refrigerant PT table?",
        concept_body=(
            "A pressure-temperature table is the saturation relationship technicians and "
            "designers use to relate gauge readings to evaporating and condensing temperatures."
        ),
        formulas_heading="Saturation basis",
        formulas=(
            "Bubble pressure is the saturated liquid pressure (quality 0).",
            "Dew pressure is the saturated vapour pressure (quality 1).",
            "Glide is the temperature difference between dew and bubble at the same pressure.",
            "Properties come from CoolProp HEOS. R-744 transcritical behaviour is out of scope.",
        ),
        cta_app_endpoint="v2.refrig_pt_table",
        cta_label="Open PT table",
        related_slugs=("superheat-subcooling", "duct-sizing-calculator"),
        free_view="v2.refrig_pt_table",
        pro_endpoint="v2.refrig_pipe_sizer",
        pro_next=(
            "Need suction, liquid or discharge line sizes? DX pipe sizing is in Pro."
        ),
        faqs=(
            (
                "Why do bubble and dew differ?",
                "Zeotropic blends boil across a glide, so liquid and vapour saturation "
                "pressures are not the same at one temperature.",
            ),
            (
                "Is CO₂ included?",
                "Transcritical R-744 logic is not part of this table.",
            ),
        ),
    ),
    "superheat-subcooling": ToolLanding(
        slug="superheat-subcooling",
        title="Superheat and Subcooling Calculator | HVAC-CALCS",
        meta_description=(
            "DX superheat and subcooling check from suction and liquid pressures and "
            "pipe temperatures. CoolProp saturation temperatures. No account required."
        ),
        h1="Superheat and subcooling",
        eyebrow="Refrigeration",
        lead=(
            "Enter low-side and high-side pressures with suction and liquid line temperatures. "
            "The tool reports superheat and subcooling against dew and bubble temperatures."
        ),
        how_heading="How to use this diagnostic",
        how_body=(
            "Select the refrigerant and whether pressures are barg or bara. Enter the gauge "
            "readings and the measured pipe temperatures. Superheat is suction temperature "
            "minus dew temperature at the low-side pressure. Subcooling is bubble temperature "
            "at the high-side pressure minus liquid temperature."
        ),
        concept_heading="What do superheat and subcooling tell you?",
        concept_body=(
            "Superheat shows how far the suction vapour is above saturation. Subcooling shows "
            "how far the liquid is below saturation. Both are field checks against the "
            "equipment maker’s targets, not a charge calculator."
        ),
        formulas_heading="Definitions used here",
        formulas=(
            "SH = T_suction − T_dew(P_low).",
            "SC = T_bubble(P_high) − T_liquid.",
            "Colour bands are typical TXV field guidance, not a manufacturer specification.",
            "The charge calculator is not available.",
        ),
        cta_app_endpoint="v2.refrig_diagnostics",
        cta_label="Open superheat tool",
        related_slugs=("refrigerant-pt-table",),
        free_view="v2.refrig_diagnostics",
        pro_endpoint="v2.refrig_pipe_sizer",
        pro_next="DX pipe sizing for the circuit is in Pro.",
        faqs=(
            (
                "Does this calculate refrigerant charge?",
                "No. It compares measured pressures and temperatures with saturation state. "
                "A system charge calculator is not available.",
            ),
            (
                "Which pressure unit should I use?",
                "Match the manifold. Barg is gauge; bara is absolute. The tool converts bara "
                "to gauge before the saturation lookup.",
            ),
        ),
    ),
    "unit-converter": ToolLanding(
        slug="unit-converter",
        title="HVAC Unit Converter | HVAC-CALCS",
        meta_description=(
            "Convert HVAC units for length, flow, pressure, power and more. SI and imperial. "
            "No account required on HVAC-CALCS."
        ),
        h1="Unit converter",
        eyebrow="Utilities",
        lead=(
            "Convert a single value across the units used on HVAC drawings and data sheets. "
            "The same conversion factors back the calculator displays."
        ),
        how_heading="How to use the converter",
        how_body=(
            "Pick a category, enter a value and the unit you have. Every other unit in that "
            "category is shown from the same canonical conversion."
        ),
        concept_heading="Why a dedicated converter?",
        concept_body=(
            "Mixed SI and imperial schedules are still common. Converting in the same place "
            "as the design tools avoids a second spreadsheet with a different factor."
        ),
        formulas_heading="Conversion basis",
        formulas=(
            "Each category converts through one canonical SI quantity.",
            "Display rounding follows the unit, not a second formula.",
        ),
        cta_app_endpoint="v2.converter",
        cta_label="Open converter",
        related_slugs=("duct-sizing-calculator", "chilled-water-pipe-sizing"),
        free_view="v2.converter",
        faqs=(
            (
                "Are these the same factors as the calculators?",
                "Yes. The converter and the calculator displays share the engine unit module.",
            ),
        ),
    ),
}


def list_landings() -> list[ToolLanding]:
    return list(LANDINGS.values())


def get_landing(slug: str) -> ToolLanding | None:
    return LANDINGS.get(slug)
