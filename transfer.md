# HVAC Toolkit — Transfer / Handover Document

**Written:** 12 July 2026
**Purpose:** Full specification and current state of the project, plus the next
build step (Pipe & Pipe System Calculator), for continuing development in
**Cursor with Grok AI**. This file plus `CLAUDE.md` are the two things a new
assistant should read first. `CLAUDE.md` is the running session-by-session
history; this file is the consolidated snapshot.

---

## 1. What this project is

A commercial, subscription-based **HVAC engineering toolkit** — a web app of
calculators for HVAC engineers, designers and contractors. Private venture by
Paul (HVAC technical manager), built on personal equipment in personal time,
to be released under his own brand.

- **Planned model:** ~£4.99/mo / £50/yr. SI + imperial units. UK first, then US/international.
- **Target users:** HVAC engineers, designers, contractors.
- **Current stage:** Clean-room rebuild well underway. Engine + web app both
  working locally. No auth, no database wired to features, no payment layer yet.

### 1.1 Critical IP-separation rules (never violate)

The product must stay completely separate from Paul's employer (Newsome Ltd):

1. **Never** copy code, files, structure, naming or UI from the Newsome internal
   app. The folder `archive/Consumer HVAC App/` is a **frozen reference
   prototype** — it was forked from the work tool, which is exactly why it can't
   become the product. Read it only for feature scope, never copy from it.
2. The real product is a **clean-room rebuild**: new repo, new architecture, code
   written from **public engineering standards** (ASHRAE Handbook of
   Fundamentals, CIBSE Guides, NIST SP 811 — public physics, nobody owns it).
   **Method: write a short functional spec per module (inputs, outputs, method,
   standard citation) BEFORE coding**, then code from the spec with the old files
   closed. The `specs/` folder is the IP trail.
3. Nothing here ever goes to company storage, company machines, or the Newsome
   intranet app.
4. Development is on Paul's personal PC, personal time, private personal GitHub
   repo (commit history evidences own-time work).

**For the new assistant:** follow the spec-first method. Every new module gets a
`specs/SPEC-*.md` written from public standards first, then engine code, then the
web layer. Do not read or copy from `archive/`.

---

## 2. Repository layout

Root of the working repo is `hvac-toolkit/`. (It sits inside `C:\CoWork\` here,
alongside `archive/` and `Support/`, but only `hvac-toolkit/` is the product.)

```
hvac-toolkit/
├── README.md                 Dev quickstart + first-commit instructions
├── docker-compose.yml        Web + Postgres 16 (Postgres present, not yet used by features)
├── .gitignore
│
├── specs/                    Functional specs — the clean-room IP trail. Spec BEFORE code.
│   ├── SPEC-psychrometrics.md
│   ├── SPEC-ahu-processes.md
│   ├── SPEC-unit-conversions.md      (engine units display layer)
│   ├── SPEC-unit-converter.md        (the converter catalogue tool)
│   ├── SPEC-duct-sizing.md           (large — sizing + fittings + index leg)
│   ├── SPEC-pdf-report.md
│   ├── SPEC-design-guides.md
│   ├── SPEC-weather-climate-data.md
│   ├── SPEC-help.md
│   └── SPEC-pipe-sizing.md           ← STUB. Next module. See §7.
│
├── engine/                   hvac_engine — standalone, pure-Python, ZERO web imports.
│   ├── pyproject.toml         Package name "hvac-engine" v0.1.0, py>=3.10, no runtime deps.
│   ├── src/hvac_engine/
│   │   ├── __init__.py         Exports PsychroState, state, design_ahu_to_supply, units, converter
│   │   ├── psychrometrics.py   Hyland-Wexler moist-air properties; state() solver; pressure_from_altitude
│   │   ├── processes.py        Mixing, sensible, cooling coil (ADP/CF/condensate/frost), humidification, simulate_ahu
│   │   ├── ahu_design.py       design_ahu_to_supply — inverse solver (supply-driven AHU)
│   │   ├── units.py            SI/IP display layer (canonical-SI, NIST SP 811 factors)
│   │   ├── converter.py        Rich 17-category unit-conversion catalogue (converter tool)
│   │   ├── duct.py             Duct sizing: circular/rectangular/flat-oval, Lindab catalogue
│   │   └── fittings.py         Duct fitting K-factors + straight/accessory pressure drop
│   └── tests/                 pytest — one test_*.py per engine module (see §5 for counts)
│
└── web/                      Flask app consuming the engine.
    ├── wsgi.py                Entry point (flask --app wsgi run)
    ├── requirements.txt       flask, gunicorn, reportlab, matplotlib, requests, staticmap, -e ../engine
    ├── Dockerfile
    ├── run.bat / commands.txt Local convenience
    └── app/
        ├── __init__.py         App factory; registers blueprints; context processors
        ├── config.py           Config (BRAND_NAME, REPORT_LOGO_PATH, etc.)
        ├── units.py            Web unit-system layer: UnitView `U`, session-backed preference
        ├── climate_slots.py    3 session-backed "memory slots" (global banner)
        ├── weather_client.py   Open-Meteo I/O boundary (geocode/archive/elevation)
        ├── chart.py            chart_payload() — unit-aware psychrometric chart data
        ├── blueprints/
        │   ├── main.py         Dashboard (/)
        │   ├── psychro.py      4 psychrometric tools + report + chart.png routes
        │   ├── duct.py         Duct sizing + index leg + api/state + report
        │   ├── converter.py    Unit converter
        │   ├── weather.py      Weather & design conditions + slots + search + elevation
        │   ├── guides.py       Reference / design guides
        │   ├── help.py         In-app help / user guide
        │   └── projects.py     Projects placeholder (Pro, static)
        ├── reports/            PDF report package
        │   ├── builder.py       reportlab PDF assembly (build_pdf, _data_table, _item_table)
        │   ├── chart.py         matplotlib static PNG chart for the PDF
        │   ├── helpers.py       Shared _report_meta_from_form / _pdf_response
        │   └── map_image.py     Static map PNG (weather report)
        ├── templates/         Jinja2 (base.html + per-tool + shared macros)
        └── static/
            ├── css/app.css      Style v2 (light theme, discipline tints, traffic-light dots)
            └── js/              psychart.js, ductsizer.js, weathermap.js
```

**Also on disk (NOT part of the working codebase — do not index/copy):**
- `archive/` — frozen prototype + design mockups + original plan doc. Reference only.
- `Support/` — logos, PDFs, spreadsheets. Read only when a task points at a
  specific file. **Relevant to pipe work:** `Support/Hydratech Glycol Data Sheets/`
  (Coolflow DTX/IGE/NTP data sheet PDFs + `Hydratech_Glycol_Data.xlsx`) — glycol
  property data for the pipe module. Also `Support/Lindab_Big_Blue_Book_of_Ventilation.pdf`
  and `Support/Duct_Standard_Sizes_Meters.xlsx` (already used for duct sizing).

---

## 3. Architecture principles (follow these)

1. **Engine is pure.** `hvac_engine` has zero web-framework imports and zero
   network calls. It is canonical SI internally. It's independently tested against
   published worked examples. The web app consumes it.
2. **Unit conversion happens only at the web boundary.** The engine speaks SI;
   `web/app/units.py` (`UnitView`, injected into every template as `U`) converts
   to/from the user's chosen system (SI or IP). This keeps IP/clean-room concerns
   out of the engine.
3. **Every result is a shareable URL.** Tools are plain GET requests where
   possible; state lives in the query string; a link reproduces the exact result.
   (Duct sizing's live 3-column tool is a deliberate JS exception, but even it
   rewrites the URL via `history.replaceState`.)
4. **Spec before code.** `specs/SPEC-*.md` written from public standards first.
5. **Group tools by what's being designed** (Air Treatment / Air Distribution /
   Hydronics / Utilities / Reference / Site Data), NOT by "air side / water side"
   (that's the work app's taxonomy — avoid it).
6. **PDF reports are shared and generic.** `reports/builder.py` is unit-agnostic
   and engine-agnostic — callers hand it `(label, value, unit)` rows. Any new tool
   plugs into it.
7. **No auth/DB yet.** Unit preference and climate slots use the Flask **session**
   today; the pattern is "session now, real user record later — one function to
   swap" once auth lands.

**Naming/UI conventions:** Style v2 (light theme, blue-primary/green-secondary,
light left nav). Modules named "Heading - Title" in Caps Case (e.g.
"Psychrometrics - Single Point", "Utilities - Unit Converter"). Discipline tints:
air treatment/psychro = blue, hydronics/water = green, air distribution/duct =
magenta, utilities = neutral. Traffic-light status dots (green in-range / amber
borderline / red out-of-range) on sizing results.

---

## 4. Module-by-module current state

### 4.1 Psychrometrics engine (`hvac_engine/psychrometrics.py`) — DONE
- Moist-air properties via **Hyland-Wexler** saturation pressure (ASHRAE HOF).
- `state()` solves a full psychrometric state from dry-bulb + one of {RH,
  wet-bulb, dew point, moisture ratio}. Returns `PsychroState`.
- `pressure_from_altitude(z)` — ASHRAE HOF standard atmosphere,
  `p = 101.325·(1 − 2.25577e-5·z)^5.2559`, valid −500..9000 m. This is the
  standard **design** pressure for a site elevation.
- Spec: `SPEC-psychrometrics.md`.

### 4.2 Air-treatment processes (`hvac_engine/processes.py`) — DONE
- Mixing (with fog/saturation handling), sensible heating/cooling, cooling coil
  (ADP, contact factor, condensate, frost-risk), steam + adiabatic humidification.
- `simulate_ahu` — forward chained AHU simulation with fan gains (blow-through
  before coil / draw-through after coil; power given directly or estimated from
  SFP per Approved Document L 2021 limits, 2.0 W/l/s central balanced).
- Spec: `SPEC-ahu-processes.md`.

### 4.3 AHU design inverse solver (`hvac_engine/ahu_design.py`) — DONE
- `design_ahu_to_supply` — the **inverse** solver: given required supply/off-unit
  condition, mix OA/RA to on-coil, check reachability, derive off-coil = supply
  dew point saturated + reheat. Handles sensible-only and heating-only degenerate
  cases; frost + fan handling. This is what the web AHU tool uses (not the forward
  `simulate_ahu`).

### 4.4 Units display layer (`hvac_engine/units.py`) — DONE
- Canonical-SI conversion, NIST SP 811 exact factors. Quantities: temperature,
  humidity_ratio, enthalpy, pressure, vol_flow, mass_flow, power, density,
  specific_volume, moisture_rate, altitude, duct_flow, velocity, duct_dimension,
  friction_rate, velocity_pressure, duct_run_length.
- IP conventions: duty **Btu/h**, humidity ratio **grains/lb**, barometric
  pressure **inHg**, plus °F, CFM, lb/h, ft³/lb, lb/ft³. Fan ratings (SFP, kW)
  stay metric.
- `duct_flow` SI display is **m³/s** (a deliberate divergence from other tools' m³/h).
- Consumed at the web boundary by `web/app/units.py` `UnitView`.
- Specs: `SPEC-unit-conversions.md`.

### 4.5 Unit converter catalogue (`hvac_engine/converter.py`) — DONE
- Separate/richer sibling of `units.py`: **17 categories** (length, area, volume,
  mass, force, pressure, temperature, speed, vol_flow, mass_flow, power, energy,
  time, angle, density, humidity_ratio, enthalpy). `convert_all()` returns a value
  in every unit of a category at once with the relationship printed beside it.
- Spec: `SPEC-unit-converter.md`. Web tool at `/converter`.

### 4.6 Duct sizing (`hvac_engine/duct.py` + `fittings.py`) — DONE, heavily iterated
- Circular/rectangular/flat-oval sizing (Darcy-Weisbach, Swamee-Jain, Huebscher
  equivalent diameter). `size_*()` solves any-two-of-four. **Real Lindab catalogue
  data** (`LINDAB_CIRCULAR_CATALOG` 29 diameters w/ gauge + special-order flags;
  `LINDAB_FLAT_OVAL_CATALOG` 19 major/minor pairs — from `Support/`, third-party
  published data, no IP concern). `velocity_pressure()`, `round_to_increment()`,
  flat-oval catalogue snapping/stepping, `apply_flex_derate`, cross-shape
  equivalence solvers.
- `fittings.py` — 19-entry K-factor catalogue (round + rectangular families),
  `fitting_pressure_drop = K·Pv`, `straight_pressure_drop = length·friction_rate`,
  `accessory_pressure_drop` (manual direct-Pa entry). **K-factors are
  representative single-point values**, not full ASHRAE Ch.32/CIBSE Guide C
  multi-parameter correlations — flagged honestly in the spec and on-page.
- **Web tool** = a single live 3-column tool (circular/rectangular/flat-oval side
  by side, JS-driven no-reload via `/api/state`) PLUS an **Index Leg** builder: a
  real spreadsheet-style data-grid of rows (straight / fitting / flex / accessory),
  per-row pressure drop, running total, safety-margin input, CSV export, and a
  leg-first PDF report. Auto-select on typed inputs.
- Spec: `SPEC-duct-sizing.md` (large). Phase B interactive ductulator slider is
  **descoped** (Paul's call). Branch balancing and full ASHRAE Ch.32 K-factor
  tables are future work.
- **Recent fixes (see CLAUDE.md):** index-leg PDF sync, table-width/overflow
  fixes, the "+ Add" button scrollbar root-cause fix.

### 4.7 Weather & design conditions (`weather_client.py` + `climate.py`) — DONE
- Engine: `hvac_engine.climate` (pure) — ASHRAE HOF Ch.14 percentile design
  conditions computed per-year then averaged across qualifying years (≥95%
  coverage). Plus **n-year return-period extremes** (Gumbel reduction, n=5/10/20/50)
  for extreme DB/WB hot and cold ends.
- Web: Open-Meteo geocoding + ERA5-Land archive (`ARCHIVE_MODEL=era5_seamless`) +
  elevation. Leaflet map + search. Three columns (Summer / Winter / Return-Period
  Extremes), each a full psychrometric state. 3 memory slots (global banner). "On
  This Day" hourly lookup. **Manual Entry mode** (`?mode=manual`) — engineer types
  authoritative ASHRAE/CIBSE DB+WB and the tool does the psychrometrics. PDF with map.
- **Honest caveat baked in:** ERA5-Land reanalysis is a grid-cell area average,
  runs low vs ASHRAE station data, biased toward undersizing — manual entry is the
  defensible route. ASHRAE sells a ~US$2,000 one-time Software Developer license
  (RP-1923) to embed their design data; buy if/when revenue justifies. Wind-speed
  column deliberately out of scope.
- Spec: `SPEC-weather-climate-data.md`.

### 4.8 PDF reports (`web/app/reports/`) — DONE
- `builder.py` reportlab assembly, unit-agnostic `(label, value, unit)` rows,
  optional `extra_tables` and chart. `chart.py` matplotlib PNG (mirrors on-screen
  SVG chart via the same `chart_payload()`). `helpers.py` shared meta/response
  builders (used by both psychro and duct blueprints). `map_image.py` static map.
- Every tool has a "Download PDF Report" + "Export Chart (PNG)" flow. Spec:
  `SPEC-pdf-report.md`.

### 4.9 Reference / design guides (`guides.py`) — DONE (1 article)
- Static article registry, `/reference` index + `/reference/<slug>`. First
  article: "Cooling Coil Design" (clean-room rewrite w/ original SVG diagrams).
  Pattern is reusable. Spec: `SPEC-design-guides.md`.

### 4.10 In-app help (`help.py`) — DONE
- Context-aware Help button in the topbar of every page → `/help#<anchor>`. Single
  guide page, sticky sidebar index, client-side search, one section per module.
  Spec: `SPEC-help.md`.

### 4.11 Projects (`projects.py`) — PLACEHOLDER (Pro, static)
- Static placeholder page: dummy projects + saved calcs, "in development" banner.
  No persistence, no Save-to-Project wired into calculators. Future Pro feature —
  needs auth + DB.

---

## 5. Tests & verification

- Engine tests live in `engine/tests/` — one `test_*.py` per module. Test-function
  counts: ahu_design 8, climate 15, converter 20, duct 64, fittings 18, processes
  24, psychrometrics 18, units 31 (**198 test functions; ~300 test cases counting
  parametrization** — CLAUDE.md reports ~298 passing).
- Run: `cd engine && pip install -e .[dev] && pytest`.
- Web layer is verified per-session via the Flask test client + standalone Jinja
  renders. **Real `flask run` click-through and git commits are done on Paul's own
  machine** (see §8).

---

## 6. Known environment gotcha (important for anyone else, not for Cursor/local)

Development so far has been in a Cowork sandbox whose file mount served **stale /
truncated reads through bash** (`cat`, `cp`, `python` reading a file) even when
the file on disk was correct. Verification was always run against the
authoritative file-tool content or fresh `/tmp` copies, never a direct bash read;
files were only ever written via file tools, never bash `>>`/heredoc.

**In Cursor on Paul's real machine this does not apply** — the filesystem is
real. Worth doing one full `git diff` review of the whole tree on first checkout
to confirm everything on disk matches expectations, then it's a normal repo.

---

## 7. NEXT STEP — Pipe & Pipe System Calculator

This is the priority module. `specs/SPEC-pipe-sizing.md` currently exists only as
a **stub**. Follow the spec-first, clean-room method: **write the full spec from
public standards first, then the engine module + tests, then the web tool.**

### 7.1 Existing stub (verbatim scope notes)
- LTHW / CHW flow rate from load: `m = Q / (cp · ΔT)`, water properties vs temperature.
- Pressure gradient: **Darcy-Weisbach + Colebrook-White** (CIBSE Guide C tables as
  the public validation source).
- Sizing mode: given load/flow + velocity and Pa/m limits, propose a size from
  standard **steel (BS EN 10255)** / **copper (BS EN 1057)** size series (public standards).
- **Glycol correction factors** (published property data only — see
  `Support/Hydratech Glycol Data Sheets/`).
- Clean-room note: write from CIBSE Guide C + public property data only.

### 7.2 Suggested spec/build scope (to confirm with Paul before building)
Mirror the duct module's shape and quality bar:

**Engine (`hvac_engine/pipe.py`, pure Python, + `test_pipe.py`):**
- Water properties (density, dynamic/kinematic viscosity, specific heat) as a
  function of temperature — from public property data (IAPWS-IF97 simplified, or
  CIBSE Guide C property tables). Cover the LTHW/CHW/hot-water range.
- Glycol correction: ethylene & propylene glycol property adjustment vs
  concentration and temperature, from the Hydratech Coolflow data sheets (public
  manufacturer data) and/or ASHRAE secondary-coolant tables. Corrects density,
  viscosity, specific heat, and hence flow rate for a given duty and the friction
  factor.
- Flow from load: `mass_flow = Q / (cp · ΔT)`; volumetric flow from density.
  (Plain-text formula for Paul's docs: `m = Q / (Cp × ΔT)`.)
- Pressure gradient: Reynolds number → friction factor via **Colebrook-White**
  (or Swamee-Jain explicit approximation, as duct.py already does for air) →
  Darcy-Weisbach `Δp/L = f · (1/D) · (ρ · V² / 2)`. Absolute roughness per material.
- Standard size series: BS EN 10255 (steel), BS EN 1057 (copper), and consider
  plastic/press-fit series later. Bore/ID per size (published). Snap-up convention
  like circular duct.
- Sizing modes: (a) given flow + velocity limit → propose size; (b) given flow +
  Pa/m limit → propose size; (c) check a chosen size → velocity, Pa/m, Reynolds,
  regime. Any-two-of style, matching duct.py's ergonomics.
- Optional (flag as future): fittings/valves K-factor or equivalent-length
  pressure drop, index-leg/circuit pressure-drop builder (mirror duct's index
  leg), pump duty point.

**Units:** add pipe quantities to `hvac_engine/units.py` and `web/app/units.py`
as needed (pipe bore in mm/in, flow in l/s + m³/h SI / GPM IP, pressure gradient
in Pa/m + ft head/100ft or similar IP — confirm IP conventions with Paul).

**Web tool (`blueprints/pipe.py`, register at `/pipe-sizing`, + `pipe.html`):**
- New nav item under **Hydronics** (green tint). Add dashboard tile.
- Inputs: fluid (water / glycol type + %), flow temperature + ΔT (or direct
  flow), material, sizing basis (velocity or Pa/m limit). GET-driven, shareable URL.
- Outputs: proposed size (+ next up/down), velocity, Pa/m, Reynolds/regime,
  total Δp for a given length, traffic-light dots against velocity/Pa-m limits.
- PDF report via the shared `reports/builder.py` (no chart, or a small
  velocity/Pa-m context). Help section in `help.py` + `help.html`.
- Consider an index-leg/circuit pressure-drop builder as a follow-up phase
  (reuse the duct index-leg pattern), like Phase C for duct.

**Validation targets:** cross-check against CIBSE Guide C pipe-sizing tables and
a couple of hand-worked examples (state them in the spec). Glycol cases against
the Hydratech data sheets.

**Scope questions to ask Paul first (recommended, before building):**
1. Fluids: water only first, or water + glycol from the start?
2. Materials for v1: steel + copper only, or add plastic/press-fit?
3. Index-leg/circuit builder now, or sizing-only first (like duct Phase A)?
4. IP unit conventions for pipe (bore, flow, pressure gradient / head).

---

## 8. Outstanding project-level items (not module-specific)

- **git init + first commit on Paul's machine** (never done in-sandbox — mount
  corrupts `.git`; and local commits are better own-time evidence anyway).
  Instructions are in `hvac-toolkit/README.md`.
- Private personal GitHub repo + push.
- Brand name / domain still TBC (single `BRAND_NAME` config variable; placeholder
  "HVAC Toolkit").
- Auth + database (Alembic + Postgres already in docker-compose) — needed before
  Projects, Save-to-Project, and persisting unit preference to a user record.
- Commercial layer: Stripe Checkout/Portal/Tax (Stripe never touches card data),
  Cloudflare, transactional email, Sentry. See
  `archive/Consumer App Direction/REVIEW-AND-PLAN.md` for the full phased plan.
- Duct follow-ups: branch balancing, full ASHRAE Ch.32 K-factor tables.
- Weather follow-ups: future-climate +ΔT scenario, caching archive fetches,
  wind-speed extremes, wiring design conditions into a future Load Calculator and
  into the psychrometric tools' outdoor-air state.

---

## 9. Running it locally (Cursor / Paul's PC)

```bash
# Engine tests
cd hvac-toolkit/engine
pip install -e .[dev]
pytest

# Web app (dev server) — Paul's usual command
cd hvac-toolkit/web
pip install -r requirements.txt        # do this after any session that touches requirements.txt
python -m flask --app wsgi run --debug
# or: run.bat

# Full stack (web + Postgres)
cd hvac-toolkit
docker compose up --build
```

Key routes: `/` dashboard, `/psychrometrics` (+ `/mixed-air`, `/cooling-coil`,
`/ahu`), `/duct-sizing`, `/converter`, `/weather`, `/reference`, `/help`,
`/projects`. Pipe will be `/pipe-sizing`.

---

## 10. TL;DR for the next assistant

The engine is pure SI and well-tested; the web app converts units at the boundary
and keeps every result in the URL. Psychrometrics, AHU, duct sizing, unit
converter, weather/design-conditions, PDF reports, guides and help are all built
and working. **Your next job is the Pipe & Pipe System Calculator:** write
`SPEC-pipe-sizing.md` from CIBSE Guide C + public standards, build
`hvac_engine/pipe.py` + tests (water/glycol properties, Colebrook-White /
Darcy-Weisbach, BS EN 10255 / BS EN 1057 size series), then a `/pipe-sizing`
Flask tool under the Hydronics nav group with a PDF report — matching the duct
module's structure and quality. Confirm the four scope questions in §7.2 with Paul
first. Keep the clean-room rules: public standards only, never touch `archive/`.
```
