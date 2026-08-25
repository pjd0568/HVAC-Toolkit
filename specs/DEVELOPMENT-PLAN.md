# HVAC Toolkit — Development Plan

**Living document.** Update status when a module ships, stalls, or scope changes.
**Side panel board:** Cursor Canvas
[`development-plan.canvas.tsx`](/Users/paul/.cursor/projects/Users-paul-Documents-GitHub-HVAC-Toolkit/canvases/development-plan.canvas.tsx)
— traffic-light view; keep in sync whenever this plan changes.
**Stack (locked):** Flask + Jinja V2 UI, pure-Python `hvac_engine`, specs in
`specs/SPEC-*.md`. Not React/Vue/SPA — adapt any external briefs to this pattern.
**Progress query:** When Paul asks *“where are we against plan?”* (or similar),
read this file, refresh the canvas if statuses changed, and reply with
**Achieved / In progress / Future** — do not invent completed work.

**Last reviewed:** 25 Aug 2026

---

## Status legend

| Tag | Meaning |
|-----|---------|
| **Done** | Live on `main` (engine + V2 UI + access, unless noted) |
| **WIP** | Spec and/or partial implementation in flight |
| **Soon** | Nav / placeholder only; engine not started |
| **Planned** | On roadmap; no code yet |
| **Deferred** | Explicitly parked |

---

## Snapshot (quick view)

### Achieved
- Auth, trial/subscribe access gating, billing scaffolding
- Psychrometrics suite (states, mix, coil, desiccant, heat/humidify, adiabatic, AHU)
- Air: duct sizing + index-leg pressure drop
- Hydronics: pipe DN sizer + system pressure-drop / pump head
- **Refrigeration:** PT table + DX pipe sizer (velocity) — on Publish
- **Refrigeration REF-03:** Superheat & subcooling diagnostics — on `main` (local; not Publish yet)
- Public SEO `/tools/*` landings + sitemap
- Unit converter, help, methodology, design guides

### In progress
- REF-03 local sign-off on `main` before promoting to Publish

### Future (engines not started)
- **P0** REF-04 Charge calculator *(nav live)*
- Epic 1 — Room load & grille throw *(nav live)*
- Epic 2 — Acoustics *(nav live)*
- Epic 3 — Expansion vessel & buffer *(nav live)*
- Epic 4 — Fresh air & CO₂ *(nav live)*
- Platform: weather/ASHRAE lookup, Projects engines; R-744; P–h / cycle overview; DX ΔTsat

---

## Suggested delivery order

Order balances **suite fit**, **reuse of existing engines**, and **site-day value**.
Reorder freely; when we start an item we may widen scope — note enhancements in
that epic’s “Scope notes” and update status here.

| Priority | Item | Why next |
|----------|------|----------|
| **P0** | Promote REF-03 SH/SC to Publish | After local sign-off on `main` |
| **P0** | Refrigeration charge calculator | Completes DX commissioning trio |
| **P1** | Epic 3 — Expansion vessel + buffer | Already sketched as pipe Stage 4; extends Hydronics |
| **P1** | Epic 4 — CO₂ / fresh air | Natural fit with psychro + room volume |
| **P2** | Epic 1 — Room load (simplified) | Large surface area; start with UK simplified method, not full CIBSE dynamic |
| **P2** | Epic 1 — Grille throw | Pairs with Air suite; lighter than full load |
| **P3** | Epic 2 — Duct attenuation / NR | Needs octave-band SWL UX + catalogue of attenuators |
| **P3** | Epic 2 — Barrier (Maekawa) | Standalone; good once acoustics suite exists |
| Later | Weather stations, Projects, R-744, P–h | Platform / deferred physics |

---

## Platform & existing suites

| ID | Module | Status | Spec / notes |
|----|--------|--------|--------------|
| PLAT-01 | Auth + entitlements | **Done** | `SPEC-auth`, `SPEC-access` |
| PLAT-02 | Stripe billing | **Done** (scaffold) | `SPEC-billing-stripe` |
| PLAT-03 | Help + methodology | **Done** | `SPEC-help` |
| PLAT-04 | Design guides | **Done** | `SPEC-design-guides` |
| PLAT-05 | Unit converter | **Done** | `SPEC-unit-converter` |
| PLAT-06 | Weather / ASHRAE design | **Soon** | Placeholder; `SPEC-weather-climate-data` |
| PLAT-07 | Projects / save calcs | **Soon** | Placeholder UI only |
| PSY-01…07 | Psychrometrics suite | **Done** | `SPEC-psychrometrics`, AHU, chart |
| AIR-01 | Duct sizing | **Done** | `SPEC-duct-sizing` |
| AIR-02 | Duct index leg | **Done** | Same family |
| HYD-01 | Pipe DN sizer | **Done** | `SPEC-pipe-sizing` |
| HYD-02 | Pipe system ΔP | **Done** | Stages 1–3 |
| REF-01 | PT table | **Done** | CoolProp bubble/dew; on Publish |
| REF-02 | DX pipe sizer (velocity) | **Done** | ΔTsat friction deferred |
| REF-03 | Superheat & subcooling | **WIP** | On `main`; promote to Publish after local test |
| REF-04 | Charge calculator | **Soon** | Placeholder routes + nav |
| REF-05 | DX pipe ΔTsat / Darcy | **Planned** | Pipe sizer v1.1 |
| REF-06 | P–h / cycle overview | **Deferred** | Out of v1 |
| REF-07 | R-744 / CO₂ | **Deferred** | UI Coming soon only |

---

## Epic R — Refrigeration / DX (active)

Functional brief already partially shipped; remaining items:

### REF-03 — Superheat & Subcooling Diagnostics — **Soon**
- **Inputs:** Refrigerant; high/low gauge pressures; liquid- & suction-line temperatures
- **Logic:** CoolProp bubble/dew at pressures → actual SC / SH
- **Output:** Colour-coded matrix (e.g. SH &lt; 3 K floodback risk)
- **Enhancement ideas:** Target SH by TXV vs EEV; zeotrope mid-point vs dew/bubble
  convention toggle; save “site snapshot” URL; optional discharge SH

### REF-04 — Refrigerant Charge Calculator — **Soon**
- **Inputs:** Factory pre-charge (kg), allowance (m), liquid-line ACR size, installed length (m)
- **Logic:** Extra length × trim g/m factors → additional + total charge
- **Output:** Trim charge + absolute total for F-Gas logbook
- **Enhancement ideas:** Suction/discharge vapour contribution (optional); dual units
  kg/lb; manufacturer-specific trim tables as selectable profiles

### REF-02 gaps vs original pipe brief — **Planned**
- Darcy / equivalent ΔTsat pressure-drop check (UI already disclaims velocity-only)
- Catalogue remains in-engine (not Postgres) by design

---

## Epic 1 — Room Load & Air Distribution — **Soon** (nav)

> Brief mentioned React/Vue — implement as **Flask V2 + `hvac_engine`** like other suites.

### E1-01 — Room Load Calculator — **Soon**
- **Nav:** Air dropdown + air picker · `/v2/coming-soon/room-load/`
- **Inputs:** Room dimensions; U-values (walls, glazing, roof); orientation; internal
  gains (occupancy, lighting, IT)
- **Logic:** Peak sensible and latent cooling / heating loads (kW)
- **Output:** Peak loads with clear component breakdown
- **Scope notes (v1 recommendation):** Start with a **transparent simplified steady-state**
  method (fabric + solar factor + gains + ventilation load), not full CIBSE/ASHRAE
  hourly dynamic simulation. Cite method on Methodology page. Later: weather-slot
  design conditions once PLAT-06 is live.
- **Enhancement ideas:** Linked supply airflow from ΔT; latent from occupancy + moisture;
  UK vs IP units; multi-zone schedule later

### E1-02 — Grille Throw & Air Displacement — **Soon**
- **Nav:** Air dropdown + air picker · `/v2/coming-soon/grille-throw/`
- **Inputs:** Volumetric flow; grille free area; discharge velocity (or derive from Q/A)
- **Logic:** Throw to terminal velocities (e.g. 0.5 and 0.25 m/s)
- **Output:** Throw distances; visual warning if Coanda likely to fail (mounting height /
  distance to ceiling)
- **Enhancement ideas:** Aspect ratio / blade deflection; noise NC estimate light-touch;
  catalogue of common grille types (optional)

**Suite home:** **Air** dropdown + air picker.

---

## Epic 2 — Acoustics & Noise Control — **Soon** (nav)

### E2-01 — Ductwork Attenuation & Room NR — **Soon**
- **Nav:** Acoustics dropdown · `/v2/coming-soon/duct-nr/`
- **Inputs:** Equipment SWL, 8 octave bands (63 Hz–8 kHz); stack of attenuation steps
  (straight duct, bends, lined plenums, silencers)
- **Logic:** Band-by-band subtraction; A-weight + NR curve at receiver
- **Output:** Final dBA and NR; optional band table
- **Enhancement ideas:** End reflection / room effect / distance; regenerated noise for
  high-velocity duct (flag as approximate); save path as shareable URL

### E2-02 — Acoustic Barrier Screening (Maekawa) — **Soon**
- **Nav:** Acoustics dropdown · `/v2/coming-soon/barrier/`
- **Inputs:** Source height, receiver height, barrier height, distances
- **Logic:** Path length difference → IL per band (Maekawa)
- **Output:** dB reduction per frequency band
- **Enhancement ideas:** Finite barrier correction; ground reflection simple model;
  outdoor plant screen vs indoor partition modes

**Suite home:** **Acoustics** top-nav dropdown + picker.

---

## Epic 3 — Hydronic Plant Sizing — **Soon** (nav)

> Overlaps **pipe Stage 4** in `SPEC-pipe-sizing.md` (system volume, buffer, expansion).
> Prefer one coherent Hydronics Stage 4 rather than a parallel product island.

### E3-01 — Expansion Vessel Sizing — **Soon**
- **Nav:** Hydronics dropdown · `/v2/coming-soon/expansion-vessel/`
- **Inputs:** Total system water volume; static head (m); max flow/return temperatures
- **Logic:** Thermal expansion + acceptance factor → min vessel volume + pre-charge
- **Output:** Vessel litres (or L) and initial pre-charge pressure
- **Enhancement ideas:** Fluid = water vs glycol (reuse glycol properties); open vs sealed
  already on pipe system; manufacturer vessel catalogue optional

### E3-02 — Buffer Tank Sizing — **Soon**
- **Nav:** Hydronics dropdown · `/v2/coming-soon/buffer-tank/`
- **Inputs:** Min compressor/boiler output (kW); max starts/hour; system ΔT
- **Logic:** Min volume to limit short-cycling
- **Output:** Minimum system / buffer volume
- **Enhancement ideas:** Existing plant volume credit; heat-pump vs chiller presets;
  link from pipe system “total volume” when that lands

**Suite home:** **Hydronics** dropdown + water picker.

---

## Epic 4 — Ventilation & IAQ — **Soon** (nav)

### E4-01 — Fresh Air & CO₂ Modelling — **Soon**
- **Nav:** Psychro dropdown · `/v2/coming-soon/co2/`
- **Inputs:** Room volume; fresh air flow; occupancy / generation rates
- **Logic:** Build-up equation → time to critical CO₂ (e.g. 1,000 ppm) at peak occupancy
- **Output:** Time-to-threshold; steady-state ppm if infinite time; optional chart later
- **Enhancement ideas:** Decay after occupancy; outdoor baseline ppm; CIBSE/ASHRAE outdoor
  air rate cross-check; link to psychro mixed-air for supply condition

**Suite home:** **Psychrometrics** dropdown + picker.

---
## How we work each module

1. Write/extend `specs/SPEC-*.md` (clean-room, public methods only).
2. Engine + pytest in `engine/src/hvac_engine/`.
3. Flask blueprint + V2 templates; `access.py` module ids; help + methodology blurb.
4. Update **this plan** (status + date) and refrigeration/other suite nav as needed.
5. Local review on `main` → Paul signs off → `git push origin main:Publish` when going live.

When tackling an epic, expect a short design huddle: confirm v1 method, units, and
any scope wideners before coding.

---

## Change log

| Date | Change |
|------|--------|
| 25 Aug 2026 | Plan created. Epics 1–4 added. Refrigeration REF-01/02 Done; REF-03/04 Soon. Mapped Epic 3 to pipe Stage 4. |
| 25 Aug 2026 | Added traffic-light Cursor Canvas board (`development-plan.canvas.tsx`); agent keeps it synced with this plan. |
| 25 Aug 2026 | Wired Coming Soon links into suite menus, pickers, hamburger, and dashboard for Epics 1–4 + Acoustics. |
| 25 Aug 2026 | Shipped REF-01 PT table + REF-02 DX pipe sizer to `main` / `Publish`. Next: REF-03 SH/SC. |
| 25 Aug 2026 | REF-03 Superheat & subcooling on `main` only (local testing; not Publish). |
