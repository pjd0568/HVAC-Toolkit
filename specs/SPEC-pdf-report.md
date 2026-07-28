# Functional Spec — PDF Report Writer

**Module:** `web.app.reports` (Flask-side; not part of `hvac_engine` — this is a
presentation concern, no physics of its own)
**Status:** v1.0 — 3 July 2026
**Clean-room note:** Layout only (header block, input/results tables, chart image) —
no content, structure or code from the frozen prototype (`archive/Consumer HVAC App/`),
which has no PDF/report feature to begin with. Report-writing generally is a standard
pattern, not proprietary.

## Purpose

A single, reusable PDF report writer that any calculator in the toolkit can call to
produce a professional, shareable record of a calculation: what was entered, what was
returned, and (where the tool has one) the psychrometric chart with the state points
plotted and read off against both axes. Built once, used first by the four
psychrometric tools; any future calculator (duct, pipe) needs only to supply its own
input/result rows to get a report for free.

## Scope (this pass)

Wired into: Single Point, Mixed Air, Cooling Coil, Desiccant, Heat & Humidify, AHU Design.
Not wired into: Unit Converter (no "duty" concept — a single conversion doesn't
warrant a report), Duct/Pipe Sizing (not built yet).

## Library choice

- **reportlab** (Platypus flowables) for document assembly — table/paragraph layout,
  precise header positioning, mature and widely used for structured engineering
  reports, no system-level dependencies (unlike WeasyPrint's Cairo/Pango), so it stays
  compatible with the project's lean Docker deployment.
- **matplotlib**, server-side, for the chart image (PNG embedded in the PDF). The
  on-screen tool pages already render an SVG chart client-side via `psychart.js`, but
  that's JS and can't run server-side to produce a static image; the PDF chart is a
  separate renderer that consumes the *same* `chart_payload()` dict the SVG component
  uses (see `app/chart.py`), so the two views can never disagree on saturation curve,
  points or axis ranges — the underlying data is one source, two renderers.

## Report contents

1. **Header** — brand name (+ logo from `Config.REPORT_LOGO_PATH`, defaulting to the
   packaged V2 mark at `static/images/brand/logo-pdf.png`; falls back to text-only
   if the file is missing), tool title (e.g. "Psychrometrics - Cooling Coil"), and a
   project/system information block: Project, System, Date (auto, today), Revision,
   Author. A future per-user company logo should override `logo_path` on `ReportMeta`
   only — UI chrome stays product-branded.
2. **Inputs** — a table of every value the user entered, in the active display unit
   system (°C/°F, kPa/inHg, etc. — same `U.fmt`/`U.sym` used on screen), one row per
   field, human-readable labels matching the on-screen form labels.
3. **Results** — a table of the calculated outputs, same labels/units as the on-screen
   results table for that tool.
4. **Chart** (where the tool has one — all four current tools do) — dry-bulb
   temperature (x) vs moisture content (y), saturation curve, faint 20/40/60/80% RH
   curves, the state points plotted and labelled with the *same* labels used in the
   results table (so a reader can tie a chart point straight back to a table row —
   "duty points tying in with the table of results"), process-line segments between
   them. For every plotted point, a dashed red guide line runs horizontally from the
   point to the y-axis (labelled with the moisture content value) and vertically down
   to the x-axis (labelled with the dry-bulb value) — read-off lines, not part of the
   process itself.

## Data contract (`web/app/reports/builder.py`)

```
ReportMeta(project, system, revision, author, date, tool_title)

build_pdf(meta: ReportMeta, input_rows: list[(label, value_str)],
          result_rows: list[(label, value_str)],
          chart_png: bytes | None) -> bytes
```

Callers (blueprints) are responsible for formatting `value_str` through the active
`UnitView` before handing rows to the builder — the builder itself is unit-agnostic,
so it has no dependency on `hvac_engine` and stays reusable for non-psychrometric
calculators.

## Chart data contract (`web/app/reports/chart.py`)

```
render_chart(payload: dict, p_kpa: float) -> bytes  # PNG
```

`payload` is exactly the dict `app.chart.chart_payload()` already produces (t_min,
t_max, w_max, sat, rh_curves, points, segments) — no new chart-geometry code path,
just a second renderer over the same data.

## Report metadata source (project/system/author)

There is no auth or project database yet (`Projects` is a static placeholder — see
CLAUDE.md status). Project, System, Revision and Author are plain free-text fields the
user fills in at download time, submitted alongside a hidden mirror of the calculation
inputs to a sibling `/report` route (so the PDF is generated from a fresh POST, no
server-side session state needed). When auth/projects land, this becomes the same
one-function swap already used for units: `get_unit_system()` reads session today,
user preference later — `report_author_default()` would follow the same pattern.

## Not yet

- No per-user company logo upload yet — `REPORT_LOGO_PATH` / `ReportMeta.logo_path`
  already accept an override path; UI + storage still to land.
- No persisted report history (each PDF is generated on demand, not stored).
- No company/letterhead template variants (single fixed layout for now).
- Author is not tied to a logged-in identity on every tool (auth exists; report
  author is still a free-text field at download time).
