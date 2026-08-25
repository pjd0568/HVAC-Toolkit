# Functional Spec — Refrigeration / DX Module

**Engine module:** `hvac_engine.refrigeration` (+ ACR copper catalogue constants)
**Web tools:** Flask blueprint `refrigeration` + V2 templates (Jinja; not a SPA)
**Status:** Stage 2–5 on `main` / `Publish` (engine + V2 UI + CoolProp dep).
**Clean-room note:** Written from public engineering standards and open property
libraries (CoolProp / REFPROP-family EOS documentation, ASHRAE Handbook —
Fundamentals refrigerant chapters, BS EN 12735-1 copper tube for ACR, and
widely published DX line-sizing design practice for velocity and equivalent
saturation-temperature drop). No reference to any prior codebase, including
`archive/Consumer HVAC App/`.

**Decisions locked (25 Aug 2026):**

| # | Decision |
|---|----------|
| 1 | **R-744 (CO₂) deferred** — no transcritical / full CO₂ circuit logic in v1. May appear in the UI refrigerant list as Coming Soon only. |
| 2 | **Runtime CoolProp** — thermodynamic properties via CoolProp at calculation time (not pre-baked PT grids). |
| 3 | **v1 calc scope** — PT table + DX pipe sizer (velocity). Cycle overview / P–h diagram later. |
| 4 | **Roadmap tools (nav live, engines later)** — Superheat & subcooling diagnostics; refrigerant charge calculator. |

---

## Phasing

| Stage | Scope | Status |
|-------|--------|--------|
| **1** | Spec (this document) | Done |
| **2** | Engine: refrigerant registry, PT table, mass-flow + pipe size, ACR catalogue, pytest | Done |
| **3** | Web: V2 picker + PT table + pipe sizer pages; access gating; Dockerfile / deps | Done |
| **4** | Help / methodology; suite nav + Coming Soon placeholders for diagnostics / charge | Done |
| **5** | Sign-off → push `main` → `Publish` | Done (25 Aug 2026) |
| **Later** | Superheat & subcooling diagnostics (engine + colour-coded UI) | Roadmap #2 |
| **Later** | Refrigerant charge / trim calculator | Roadmap #3 |
| **Later** | Darcy / equivalent ΔTsat friction check on pipe sizer | Pipe sizer v1.1 |
| **Later** | Simple vapour-compression state points / P–h overview | Out of v1 |
| **Later** | R-744 subcritical PT only, then full transcritical gas-cooler logic | Out of v1 |

---

## Purpose

Give UK HVAC / refrigeration engineers linked tools:

1. **PT table** — saturation pressure vs temperature for common refrigerants,
   showing **bubble** (liquid, Q=0) and **dew** (vapour, Q=1) pressures so
   zeotropic glide is visible.
2. **DX pipe sizer** — from cooling capacity and cycle temperatures, compute
   refrigerant mass flow, evaluate ACR copper sizes against **velocity** bands
   and report recommended size, velocity, and mass flow (with oil-return /
   flash-gas warnings). Catalogue lives in-engine (BS EN 12735-1 constants),
   not Postgres — same pattern as water pipe / duct tables.
3. **Superheat & subcooling** *(roadmap)* — measured high/low gauge pressures
   and pipe temperatures → actual SH / SC with colour-coded healthy / risk bands.
4. **Charge calculator** *(roadmap)* — factory pre-charge, pipe allowance,
   liquid-line size, installed length → trim charge and total system charge.

This is **sub-critical DX / vapour-compression line work**, not a full Bitzer /
Danfoss selection suite and not a CO₂ rack calculator.

### Pipe sizer vs roadmap brief

| Brief ask | v1 status |
|-----------|-----------|
| Capacity, refrigerant, Tevap/Tcond, line type | Done |
| CoolProp Δh → ṁ | Done |
| Velocity bands + oil-return warnings | Done |
| Optimum standard ACR diameter | Done (in-module catalogue) |
| Pressure-drop / ΔTsat constraint | Deferred (UI disclaimer) |
| “Query the database” for pipe sizes | N/A — Python constants by design |

---

## Method sources (public)

- **CoolProp** (`PropsSI` / HEOS) — saturation and single-phase thermodynamic
  properties (pressure, density, enthalpy, quality). Same class of EOS data used
  across industry tooling; fluid names and mixture definitions per CoolProp docs.
- **ASHRAE Handbook — Fundamentals** — refrigerant nomenclature, glide
  (bubble/dew), and vapour-compression property concepts.
- **BS EN 12735-1** — copper tubes for air-conditioning and refrigeration
  (ACR); nominal inch sizes and wall / bore dimensions for the catalogue
  (distinct from BS EN 1057 water copper already in `hvac_engine.pipe`).
- **Industry DX line-sizing practice** — suction / liquid / discharge velocity
  bands and equivalent saturation-temperature pressure-drop limits as commonly
  published in manufacturer application guides and refrigeration design
  handbooks (rules coded explicitly below; treat as design guidance, not a
  single named CIBSE table).

---

## Dependency policy

| Package | Role |
|---------|------|
| **CoolProp** | Required at runtime for this module. Add to engine optional extra
  `refrigeration` **and** to `web/requirements.txt` / Docker image so Railway
  and Compose installs succeed. |
| Other engine modules | Remain usable without CoolProp if the optional extra is omitted;
  refrigeration entry points must raise a clear error if CoolProp is missing. |

Engine stays free of Flask imports. CoolProp is the first intentional native
dependency for refrigeration only.

---

## Refrigerant registry (v1)

Internal id → CoolProp fluid string (exact string used in `PropsSI`). UI label
and metadata for GWP class / glide behaviour.

| UI id | Label | CoolProp fluid string | Behaviour | v1 |
|-------|--------|------------------------|-----------|-----|
| `r410a` | R-410A | `R410A` | Near-azeotrope (tiny glide) | Yes |
| `r134a` | R-134a | `R134a` | Pure / single-component | Yes |
| `r404a` | R-404A | `R404A` | Zeotropic blend | Yes |
| `r407c` | R-407C | `R407C` | Zeotropic (noticeable glide) | Yes |
| `r32` | R-32 | `R32` | Pure | Yes |
| `r513a` | R-513A | `R513A` (or HEOS mixture if alias missing) | Near-azeotrope | Yes |
| `r454b` | R-454B | Prefer named `R454B` if present in pinned CoolProp; else HEOS mixture `R32` + `R1234yf` at ASHRAE composition (document exact mole/mass fractions used) | Zeotropic | Yes |
| `r1234ze` | R-1234ze(E) | `R1234ze(E)` | Pure | Yes |
| `r1234yf` | R-1234yf | `R1234yf` | Pure | Yes |
| `r290` | R-290 (propane) | `R290` or `Propane` | Pure, A3 | Yes |
| `r600a` | R-600a (isobutane) | `R600a` or `IsoButane` | Pure, A3 | Yes |
| `r744` | R-744 (CO₂) | `CO2` / `R744` | — | **Coming Soon only** (no calc) |

Implementation must resolve aliases against the pinned CoolProp version in CI /
Docker and fail tests if a “Yes” fluid cannot be loaded.

**Glide UI rule:** for every PT row, always return both bubble and dew pressure.
When `|T_dew − T_bubble|` at a reference pressure is below a small threshold
(e.g. 0.1 K), the UI may note “negligible glide” but still show both columns.

---

## Task A — PT table engine

### Inputs

| Input | Description |
|-------|-------------|
| `refrigerant` | Registry id (e.g. `r32`) |
| `t_min_c` | Default **−40** |
| `t_max_c` | Default **+60** |
| `t_step_k` | Default **1** |

Reject R-744 with a structured “not available in v1” error (web shows Coming Soon).

### Method

For each temperature \(T\) from \(t_\min\) to \(t_\max\) inclusive:

\[
P_\mathrm{bubble} = P_\mathrm{sat}(T, Q=0),\quad
P_\mathrm{dew} = P_\mathrm{sat}(T, Q=1)
\]

CoolProp: `PropsSI("P", "T", T_K, "Q", 0|1, fluid)`.

### Outputs (SI internally; display barg)

| Field | Unit | Notes |
|-------|------|--------|
| `t_c` | °C | Row temperature |
| `p_bubble_barg` | bar gauge | \(P_\mathrm{abs}/\mathrm{1e5} - 1\) (standard atmosphere 1.01325 bar → use **1.01325 bar** absolute for gauge, document constant) |
| `p_dew_barg` | bar gauge | Same |
| `glide_k` | K | Optional per-row or header: dew−bubble temperature span at mid-range / at each P — pick one definition and document in methodology |

Skip or flag rows where CoolProp cannot evaluate (near critical, below triple, etc.).

### Engine API (sketch)

```
list_refrigerants() -> list[RefrigerantInfo]
pt_table(refrigerant_id, t_min_c=-40, t_max_c=60, t_step_k=1) -> PtTableResult
```

---

## Task B — ACR copper catalogue

**Not a Postgres table.** Follow `hvac_engine.pipe` pattern: pure-Python catalogue
constants transcribed from **BS EN 12735-1** (cite table / wall series in code
comments). Do **not** reuse BS EN 1057 water copper IDs.

### Catalogue fields

| Field | Description |
|-------|-------------|
| `nominal_inch` | e.g. `1/4`, `3/8`, `1/2`, `5/8`, `3/4`, `7/8`, `1-1/8` |
| `nominal_mm` | Metric marketing size if published alongside |
| `od_mm` | Outside diameter |
| `wall_mm` | Wall thickness for the chosen series |
| `id_mm` | Internal diameter (= OD − 2×wall, or tabulated bore) |

Minimum seed set (exact OD/wall/ID filled from BS EN 12735-1 at implementation):

`1/4"`, `3/8"`, `1/2"`, `5/8"`, `3/4"`, `7/8"`, `1-1/8"` — extend later if needed
(1-3/8", 1-5/8", …).

---

## Task C — DX pipe sizing engine

### Inputs

| Input | Description |
|-------|-------------|
| `cooling_capacity_kw` | Evaporator duty \(Q\) (kW) |
| `refrigerant` | Registry id |
| `evaporating_temp_c` | Evaporating temperature (°C) — for zeotropes, define as **mid-point** or **dew** and document; default recommendation: **dew point** for suction state consistency |
| `condensing_temp_c` | Condensing temperature (°C) — same convention (document; default **bubble** or mid — pick one and test) |
| `subcooling_k` | Liquid subcooling below bubble at condenser pressure (K) |
| `superheat_k` | Suction superheat above dew at evaporator pressure (K) |
| `line_type` | `suction` \| `liquid` \| `discharge` |
| `orientation` | `horizontal` \| `upflow_riser` (suction only; affects min velocity) |

### Thermodynamic states (sub-critical)

Assume a simple vapour-compression sketch for property points (not a full cycle
solver):

1. **Evaporator pressure** from evaporating temperature (dew or mid per convention).
2. **Condenser pressure** from condensing temperature (bubble or mid per convention).
3. **Evaporator outlet (suction gas):** \(P = P_\mathrm{evap}\), \(T = T_\mathrm{evap} + \mathrm{SH}\) → \(h_1, \rho_1\).
4. **Expansion device inlet (liquid line):** \(P = P_\mathrm{cond}\), \(T = T_\mathrm{bubble,cond} - \mathrm{SC}\) → \(h_3, \rho_3\) (subcooled liquid).
5. **Evaporator inlet:** isenthalpic expansion \(h_4 = h_3\) at \(P_\mathrm{evap}\) → \(h_4\).
6. **Discharge (hot gas):** at \(P_\mathrm{cond}\), estimate discharge temperature — v1 may use a **user-supplied discharge temp** *or* a simple isentropic compression estimate with fixed efficiency; **prefer user discharge temp or a documented default ΔT above condensing** so the engine stays transparent. Spec default for v1: **optional `discharge_temp_c`**; if omitted, use \(T_\mathrm{cond} + 40\,\mathrm{K}\) as a transparent placeholder and flag it in the UI as an estimate.

**Enthalpy difference for mass flow (evaporator):**

\[
\Delta h = h_1 - h_4 \quad [\mathrm{J/kg}],\qquad
\dot{m} = \frac{Q}{\Delta h} \quad [\mathrm{kg/s}]
\]

with \(Q\) in W when \(\Delta h\) in J/kg (or consistent kW / kJ/kg).

### Density by line type

| `line_type` | State for \(\rho\) |
|-------------|-------------------|
| `suction` | Evaporator outlet (superheated vapour) |
| `liquid` | Subcooled liquid at condenser pressure |
| `discharge` | Hot gas at condenser pressure and discharge temperature |

### Velocity and area

\[
A = \frac{\dot{m}}{\rho\, V},\qquad
V = \frac{\dot{m}}{\rho\, A},\qquad
A = \pi (D_i/2)^2
\]

### Design limits (code these constants)

| Line | Target velocity (m/s) | Notes |
|------|----------------------|--------|
| Suction, horizontal | **8 – 15** | Ideal band |
| Suction, upflow riser | **≥ 10** (cap still 15) | Oil return against gravity |
| Liquid | **0.5 – 1.5** | Limit flash gas / liquid hammer |
| Discharge | **10 – 18** | Hot gas |

**Oil-return warning (UI red):** suction velocity **&lt; 5 m/s** (any orientation), or
upflow riser **&lt; 10 m/s**. Amber when outside ideal band but above hard floor.

**Equivalent ΔTsat pressure-drop guidance (v1 optional output):** if friction ΔP
is computed later, convert to saturation temperature change at local pressure.
v1 **may omit full Darcy ΔP** and size on velocity only; if omitted, UI copy
must say pressure drop is not yet checked. Preferred Stage 2 add: Darcy–Weisbach
with refrigerant viscosity from CoolProp + ΔTsat limits:

| Line | Typical max ΔTsat |
|------|-------------------|
| Suction | 1.5 – 2.0 K |
| Liquid | 0.5 – 1.0 K |
| Discharge | ~1.0 K |

### Size selection

1. Compute \(\dot{m}\) and \(\rho\).
2. For each ACR catalogue row, compute \(V\).
3. Recommend the **smallest** pipe whose velocity lies in the **ideal** band for
   that line type (and orientation).
4. If none in band: recommend closest that stays under max velocity and below
   flash/oil limits; attach clear warnings.
5. Return full per-size table (traffic-light style, like pipe sizer) for engineer override.

### Engine API (sketch)

```
size_dx_pipe(...) -> DxPipeSizeResult
  .mass_flow_kg_s
  .density_kg_m3
  .recommended: AcrSizeResult | None
  .rows: list[AcrSizeResult]   # velocity, status green/amber/red
  .warnings: list[str]
```

---

## Web layer (Flask + Jinja V2)

### Module access IDs

| module_id | Label |
|-----------|--------|
| `refrig.pt_table` | Refrigeration — PT Table |
| `refrig.pipe_sizer` | Refrigeration — DX Pipe Sizing |

Add both to `SUITE_MODULES` and `MODULES` in `web/app/access.py`. Gate with
`@require_module(...)`.

### Routes (proposed)

| Path | Role |
|------|------|
| `/v2/refrigeration/` | Picker (PT + pipe sizer) |
| `/v2/refrigeration/pt-table/` | PT table form + results |
| `/v2/refrigeration/pipe-sizer/` | Pipe sizing form + results |
| Optional JSON | `/v2/refrigeration/api/pt-table`, `.../api/size-pipe` for progressive enhancement — same engine helpers |

Classic blueprint prefix `/refrigeration/...` may redirect to V2 like other tools.

### UI requirements

**PT table:** refrigerant `<select>` (R-744 disabled / Coming Soon); table columns
Temp (°C), Liquid pressure (barg), Vapour pressure (barg); short note on glide.

**Pipe sizer:** inputs for capacity, refrigerant, Tevap, Tcond, SC, SH, line type,
orientation; optional discharge temp. Results: ṁ, recommended size, velocity,
warnings in **red** for oil-return / out-of-band. Per-size table with traffic lights.

**Dashboard:** new “Refrigeration” suite card linking the picker (alongside
Psychrometrics / Air / Hydronics).

### Units

Canonical SI in engine. Display SI first; IP display may follow existing
`hvac_engine.units` patterns in a later polish pass (not blocking v1).

---

## Testing

| Area | Checks |
|------|--------|
| CoolProp load | Every v1 refrigerant resolves; R-744 listed but rejected by calc APIs |
| PT table | R-32 bubble≈dew; R-407C / R-454B show glide; barg conversion vs known anchor points |
| Mass flow | Hand check \(\dot{m}=Q/\Delta h\) with CoolProp enthalpies for one refrigerant |
| Velocity | Synthetic ρ, ṁ → expected V for a known ID |
| Selection | Smallest size in band; red flag when V &lt; 5 m/s suction |
| Missing CoolProp | Clear `ImportError` / app error message |

---

## Out of scope (v1)

- R-744 / transcritical gas cooler, flash tank, parallel compression
- Full P–h diagram / COP / compressor selection
- Oil separator / riser double-riser geometry detail beyond velocity floor
- Postgres storage of pipe dimensions or calculation history
- React / FastAPI / Prisma (wrong stack for this repo)

---

## Implementation order (after this spec is signed)

1. Pin CoolProp in `engine` optional extra + `web/requirements.txt`; verify Docker build.
2. `hvac_engine.refrigeration` registry + `pt_table` + tests.
3. ACR catalogue from BS EN 12735-1 + `size_dx_pipe` + tests.
4. Blueprint + V2 templates + `access.py` + dashboard card.
5. Methodology / help note; local review on `main`.
6. User sign-off → `git push origin main:Publish`.

---

## Open implementation details (resolved in Stage 2)

1. **CoolProp 8.0 strings:** R-454B → `HEOS::R32[0.829248]&R1234yf[0.170752]`; R-513A → `HEOS::R1234yf[0.532426]&R134a[0.467574]` (mole fractions ≡ ASHRAE mass blends). Named fluids for the rest.
2. **Zeotrope convention:** evaporating = **dew**; condensing = **bubble** (documented in UI + methodology).
3. **v1 sizing:** velocity-only with explicit UI disclaimer (ΔTsat friction deferred).
