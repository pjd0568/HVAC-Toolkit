# Functional Spec — Pipe Sizing Module

**Module:** `hvac_engine.pipe` (+ `hvac_engine.pipe_fittings` for Stage 2)
**Status:** v1.1 Stage 2 — system pressure-drop builder on the same page
(14 July 2026). Stage 1 sizing remains as before.
**Clean-room note:** Written from public engineering standards (CIBSE Guide C,
BS EN 10255, BS EN 1057, DIN 11850) and published third-party manufacturer
fluid data (Hydratech Coolflow DTX / EPG / PPG data sheets in
`Support/Hydratech Glycol Data Sheets/`). No reference to any prior codebase,
including `archive/Consumer HVAC App/`.

**Phasing (Paul, 12 July 2026; Stage 2 scoped 14 July 2026):**

| Stage | Scope | Status |
|-------|--------|--------|
| **1** | Flow from load or known flow; fluid properties; DN table + traffic lights; detail panel; PDF + help | Done |
| **2** | System builder — pipe sections, fittings/valves (K), devices (manual ΔP), running ΔP total | **This addendum** |
| **3** | Open vs pressurised, lift / static head | Future |
| **4** | System volume — tanks, coils, chillers; fitting volume ≠ equivalent pipe length | Future |

---

## Purpose

Given a hydronic duty (load and ΔT, or a known volumetric flow), a fluid type
and working temperature, and a pipe material, compute the required flow rate
and evaluate **every standard DN size** in that material's catalogue for
velocity and pressure gradient. Present results with **traffic-light status**
against CIBSE Guide C design limits, and a **detail panel** for the
engineer-selected size showing bore, OD, flow, friction loss, and full fluid
properties.

This is the calculation core for the "Flow & Pipe Sizer" top section of the
full Pipe & Pipe System Calculator Paul described; the system schedule builder
(Stage 2+) reuses the same per-size friction evaluation.

---

## Method sources (public standards)

- **CIBSE Guide C (2016), Section 2** — water velocity and pressure-loss limits
  for closed heating and chilled-water systems; Darcy-Weisbach pressure loss;
  Colebrook-White friction factor; water property tables.
- **CIBSE Guide C, Section 1** — pipe roughness values (commercial steel,
  drawn copper).
- **BS EN 10255** — carbon steel tube dimensions (Series 1 medium grade,
  light wall) — nominal DN and internal bore.
- **BS EN 1057** — copper tube (R250, Table X wall series) — nominal outside
  diameter and bore.
- **DIN 11850** — stainless steel hygienic / dairy tube (thin wall, OD-based
  sizes) — published dimension series used for thin-wall stainless in food/pharma
  HVAC.
- Swamee & Jain (1976) — explicit friction-factor approximation to
  Colebrook-White (same approach as `hvac_engine.duct`).
- **Hydratech Coolflow data sheets** (`Support/Hydratech Glycol Data Sheets/`)
  — DTX, EPG, PPG density, viscosity, specific heat and freezing point at
  **fixed catalogue concentration and temperature points** (not copied from any
  prior app; manufacturer's published data Paul holds independently).

---

## Inputs (Stage 1)

| Input | Description |
|-------|-------------|
| **Flow mode** | `from_load` — calculate flow from duty; `flow_known` — user supplies flow directly |
| **Load** | Duty in kW (SI) / Btu/h (IP) — only when `from_load` |
| **ΔT** | Temperature difference across the circuit (K / °F difference) |
| **LWT** | Leaving water temperature (°C / °F) — the temperature of water **leaving** the heat emitter (heating) or **leaving** the chiller coil (chilled water). Used with ΔT to derive the return temperature and the **mean water temperature** for property lookup |
| **Fluid** | `water`, `dtx`, `epg`, `ppg` |
| **Glycol concentration** | Fixed catalogue % — only for glycol fluids (see § Fluids) |
| **Application** | `lthw` or `chw` — selects CIBSE Guide C velocity / Pa·m⁻¹ limits |
| **Material** | `carbon_steel` (BS EN 10255), `copper` (BS EN 1057), `dairy_ss` (DIN 11850 thin-wall) |
| **Known flow** | Volumetric flow in l/s when `flow_known` (canonical conversion via m³/h internally) |
| **Selected DN** | Optional — which catalogue row is highlighted in the detail panel |

---

## Outputs (Stage 1)

### Flow (always shown when computable)

Both **l/s** and **m³/h** displayed together (Paul's requirement), regardless
of the global SI/IP toggle. The global toggle still controls duty, temperature,
velocity, and pressure-gradient displays.

### Size table (all DN sizes for the chosen material)

Per row: DN label, internal diameter, velocity, pressure gradient (Pa/m),
traffic-light dots for velocity and pressure gradient.

### Detail panel (selected DN)

Internal diameter, outside diameter, volumetric flow (l/s + m³/h), velocity,
pressure gradient, Reynolds number, flow regime, fluid name, concentration,
mean water temperature, density, dynamic viscosity, specific heat, freezing
point.

---

## Calculations

### Mean water temperature

For property evaluation (ρ, μ, cp):

    T_mean = LWT + ΔT / 2

This is the mid-point between leaving and return water temperatures. Documented
explicitly so engineers can challenge it; it is the usual CIBSE practice for
friction sizing in recirculating systems.

### Flow from load

    Q̇ = ṁ · cp · ΔT        (duty)
    ṁ = Q̇ / (cp · ΔT)
    V̇ = ṁ / ρ              (m³/s)
    V̇_m3h = V̇ × 3600

Engine canonical units: duty **kW**, ΔT **K**, mass flow **kg/s**, volumetric
flow **m³/h**, temperature **°C**.

### Friction loss (each DN size)

Reynolds number:

    Re = V · D / ν

Darcy friction factor *f* via Swamee–Jain (explicit Colebrook–White). Laminar
fallback *f = 64/Re* below Re = 2300.

Darcy–Weisbach pressure gradient:

    Δp/L = f · (1/D) · (ρ · V² / 2)     [Pa/m]

Velocity from flow and internal bore:

    V = V̇ / A,    A = π · D² / 4

Kinematic viscosity ν = μ / ρ.

### Absolute roughness (CIBSE Guide C, Section 1)

| Material | ε (m) | Note |
|----------|-------|------|
| Carbon steel (commercial) | 0.00015 | galvanised / commercial steel pipe |
| Copper (drawn) | 0.0000015 | smooth drawn tube |
| Dairy stainless | 0.0000015 | smooth hygienic thin-wall tube |

### CIBSE Guide C design limits (Stage 1 defaults)

| Application | Max velocity (m/s) | Max Δp/L (Pa/m) | Source |
|-------------|-------------------|-----------------|--------|
| LTHW (heating) | 1.5 | 300 | Guide C Table 2.2 — closed heating systems |
| CHW (chilled water) | 1.5 | 400 | Guide C Table 2.2 — closed chilled-water systems |

Traffic-light classification (ideal band — not duct's single upper limit):

- **Green** — velocity and ΔP/L both within the ideal band (see `IDEAL_BANDS` in engine).
- **Amber** — below the ideal minimum (oversized / uneconomic) OR above the ideal
  maximum but still below the CIBSE absolute maximum (commercially pushed sizing).
- **Red** — at or above the CIBSE absolute maximum (out of limits).

---

## Fluids

### Water

Properties (ρ, μ, cp) from a **fixed-temperature catalogue** derived from
CIBSE Guide C / ASHRAE Handbook water tables (0–100 °C anchor points, linear
interpolation). Freezing point 0 °C.

### Glycol fluids — fixed concentration catalogue

Concentrations available in the UI are **per fluid**, taken from the Hydratech
data sheet grid (% v/v in water). See addendum below for the exact steps.

Fluids:

| ID | Display name | Basis |
|----|--------------|-------|
| `dtx` | Coolflow DTX (DTX) | Coolflow DTX data sheet |
| `epg` | Coolflow IGE (EG) | Coolflow IGE data sheet |
| `ppg` | Coolflow NTP (PPG) | Coolflow NTP data sheet |

At each (fluid, concentration %, temperature °C) grid point the engine holds
ρ, μ, cp, and freezing point. Properties at arbitrary temperature within the
tabulated range are **linearly interpolated**; concentration is **not**
interpolated — the user picks a catalogue percentage.

---

## Pipe size catalogues (DN)

All dimensions stored as **metres internally**; displayed in **mm** under SI
(unchanged under IP — DN/mm convention per Paul's direction).

### Carbon steel — BS EN 10255 (Series 1, medium)

DN 15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300 — with
published internal bore and outside diameter per the standard.

### Copper — BS EN 1057 (R250, Table X)

Nominal sizes 15, 18, 22, 28, 35, 42, 54, 76.1, 108, 133, 159, 219.1 (mm OD)
with tabulated bore.

### Dairy stainless — DIN 11850

OD-based thin-wall series: 25, 32, 40, 50, 65, 80, 100, 125, 150, 200 mm with
1.5 mm wall (ID = OD − 3 mm). Labelled by OD; DN column shows the OD value.

Imperial fridge copper and PVC — **out of scope** for v1.

---

## Web tool (`/pipe-sizing`)

- Nav: **Hydronics → Pipe Sizing** (green `tile-water` tint).
- GET-driven; every state in the query string (shareable URL).
- Layout: inputs panel → two columns (size table | detail panel).
- Row click / link sets `selected_dn` without losing other inputs.
- PDF report via shared `reports/builder.py` (Inputs + Results + size table;
  no chart).
- Help section replaces the "soon" stub.

---

## Validation targets (engine tests)

1. Water at 20 °C, 1 l/s in DN25 carbon steel — velocity and Pa/m cross-checked
   against hand Darcy–Weisbach calculation.
2. Load 100 kW, ΔT 20 K, LWT 50 °C (mean 60 °C) — flow rate cross-checked
   against ṁ = Q/(cp·ΔT).
3. 30 % PPG at 10 °C — properties match tabulated catalogue point.
4. Band-status boundaries: ideal green zone, amber below/above ideal, red at absolute max.

---

## Deferred (later stages)

- Open vs pressurised; pump static head / lift (Stage 3).
- System volume; true fitting internal volume (Stage 4).
- Plastic / press-fit pipe series; imperial fridge copper.
- Pump duty point.
- Equivalent-length method (Stage 2 uses K × velocity pressure only).
- Geometry-dependent full CIBSE/Crane multi-parameter fitting tables.

---

## Addendum — Stage 2 Pipe System pressure-drop builder (14 Jul 2026)

Paul confirmed defaults: same `/pipe-sizing` page (below the Stage 1 panels);
row types straight / fitting / device; K-factors + manual ΔP (not
equivalent lengths); lift and system volume stay Stages 3–4.

### Purpose

Total the dynamic pressure drop along a hydronic circuit (or index circuit)
as a spreadsheet-style schedule: straight pipe runs, local losses at
fittings/valves, and manufacturer devices entered as direct Pa. Reuses the
Stage 1 fluid / material / friction evaluation — no second friction method.

### Method

For each row independently:

| Type | Pressure drop |
|------|----------------|
| **Straight** | `Δp = L × (Δp/L)` where `Δp/L` comes from `evaluate_size()` at that row’s DN and flow |
| **Fitting** | `Δp = K × Pv`, `Pv = ½ ρ V²` at that row’s velocity and fluid density |
| **Device** | User-entered Δp (Pa), validated ≥ 0 — coils, heat exchangers, strainers with published loss, etc. |

Running total = sum of committed row Δp. Optional **safety margin %** added
to the total (same pattern as duct Index Leg).

Fluid properties, material roughness, and application come from the page’s
Design Inputs (shared with Stage 1). Each row carries its own DN and may
override flow (l/s); blank flow uses the Stage 1 duty flow.

### K-factor catalogue (`hvac_engine.pipe_fittings`)

Representative single-point loss coefficients for common closed-circuit
hydronic fittings and valves, of the kind published in quick-reference
pipework design guides / Crane TP-410 / CIBSE Guide C Section 4 summaries.
**Not** the full geometry- and Reynolds-dependent correlations (elbow r/D,
tee area ratio and flow split, valve opening angle). Flagged on the module
docstring, this spec, and an on-page note-banner — planning figures until
cross-checked against a primary table or manufacturer data for a real job.

Catalogue groups (one flat list, filterable by category in the UI):

- Elbows — 90° standard / long-radius, 45°
- Tees — run-through / branch
- Transitions — sudden contraction / enlargement, entry, exit
- Valves — gate / globe / ball / butterfly (fully open), swing check
- Strainers — Y-type (representative)

### Web tool

- Panel **Pipe System — Pressure Drop** replaces the Stage 1 placeholder on
  the same page.
- Spreadsheet table: Type | DN | Flow (l/s) | Length / Fitting / Description+ΔP |
  Velocity | Pv or ΔP/L or K | Pressure Drop | Remove.
- Stage row at top of table (“+ Add”); committed rows editable in place;
  Clear; safety margin %; CSV export of the schedule.
- Instant AJAX refetch (`/pipe-sizing/api/system-state`) — same exception to
  plain-GET as duct Index Leg. Query-string state (`sys_*`) so a built
  system remains a shareable URL.
- PDF: when system rows exist, include a “Pipe System — Pressure Drop”
  table after the size catalogue (system-first layout optional later —
  Stage 2 keeps sizer Inputs/Results + size table + system table).
- Help section: replace the “planned later” note with Stage 2 how-to.

### Engine surface

- `hvac_engine.pipe.velocity_pressure(velocity_ms, density_kg_m3)` —
  `Pv = ½ ρ V²` (fluid density, not air’s fixed ρ).
- `hvac_engine.pipe_fittings` — `Fitting` catalogue, `fitting_pressure_drop`,
  `straight_pressure_drop`, `device_pressure_drop` (manual Pa).

### Validation targets

1. Straight DN25 carbon steel, water 20 °C, 1 l/s, 10 m — Δp = 10 ×
   `evaluate_size(...).friction_rate_pa_per_m`.
2. Fitting K=0.9 at known V and ρ — Δp = 0.9 × ½ρV².
3. Device 25 Pa identity; negative rejected.
4. Unknown fitting key / bad DN isolates to one row without blanking the total.

---

## Addendum — traffic-light methodology (12 Jul 2026)

Paul supplied lifecycle-cost framing for ΔP/L and per-DN velocity limits. These
replace the earlier flat CIBSE Guide C ideal bands for traffic lights (friction
calculation method unchanged).

### ΔP/L bands (Pa/m) — same for LTHW and CHW

| Band | Range | Meaning |
|------|-------|---------|
| Red (low) | &lt; 100 | Below acceptable lower limit |
| Amber (lower) | 100 – 150 | CAPEX-heavy / OPEX-light — oversized |
| Amber (transition) | 150 – 200 | Between lower and ideal |
| **Green (ideal)** | **200 – 300** | Optimised sweet spot |
| Amber (transition) | 300 – 400 | Between ideal and upper |
| Amber (upper) | 400 – 500 | CAPEX-light / OPEX-heavy — commercially pushed |
| Red (high) | &gt; 500 | Above acceptable upper limit |

### Velocity bands (m/s) — per DN

| DN range | Minimum | Ideal | Maximum |
|----------|---------|-------|---------|
| 15 – 50 | 0.6 | 0.8 – 1.2 | 1.5 |
| 65 – 150 | 0.6 | 1.2 – 1.8 | 2.5 |
| 200+ | 0.6 | 1.8 – 2.5 | 3.0 |

Traffic lights: green within ideal; amber below minimum (oversized) or above ideal
max but at/below maximum; red above maximum.

### Recommended size and table window

- **Recommended** = smallest DN with ideal friction (200–300 Pa/m) and velocity
  not red (auto-selected row; traffic lights reflect actual band status only).
- **On-screen table** = full material catalogue (all DN sizes).

---

## Addendum — Hydratech glycol data (12 Jul 2026)

Glycol properties regenerated from `Support/Hydratech Glycol Data Sheets/
Hydratech_Glycol_Data.xlsx` (All Data (Tidy) sheet). Each fluid uses the
manufacturer's own concentration grid (% v/v), not a shared 10–50 % ladder.

| ID | Display name | Coolflow product | Catalogue % v/v |
|----|--------------|------------------|-----------------|
| `ppg` | Coolflow NTP (PPG) | NTP | 25, 33, 39, 44, 48, 53, 60 |
| `epg` | Coolflow IGE (EG) | IGE | 20, 27, 32, 37, 41, 45, 50, 55, 58 |
| `dtx` | Coolflow DTX (DTX) | DTX | 22, 28, 33, 38, 42, 46, 50, 52, 54 |

Engine module: `hvac_engine/glycol_data.py` (regenerate via
`engine/scripts/build_glycol_data.py` if the spreadsheet is updated).

### Labels

- Dairy stainless (DIN 11850) labelled **DN** (not OD), consistent with other materials.

### Layout

- Three equal-height columns: size table | pipe spec | flow &amp; fluid detail.
