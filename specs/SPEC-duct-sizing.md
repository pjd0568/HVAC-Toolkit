# Functional Spec — Duct Sizing Module

**Module:** `hvac_engine.duct`
**Status:** v1.7 (Phase A: core sizing, real catalogue data, live 3-column
web UI, rectangular width/height fully independent with per-dimension lock,
flat-oval major/minor independent but catalogue-locked; Phase C: index-leg
pressure-drop table, rebuilt as an independent per-row system builder —
Correction #6, built and verified) — 9 July 2026
**Clean-room note:** This spec is written from public engineering standards
only (CIBSE Guide C, ASHRAE Handbook of Fundamentals). No reference to any
prior codebase, including `archive/Consumer HVAC App/`. The Lindab catalogue
data added in v1.1 is Paul's own copy of Lindab's published product
literature (third-party manufacturer data he obtained independently) — using
it carries no clean-room concern; it is not Newsome data and nothing here was
copied from the Newsome app or the frozen prototype.

**Scope of this version:** the request behind this spec (`Support/Duct Sizer
Module.md`) describes a full module — sizing, an interactive graphical
ductulator slider, an index-leg/fittings pressure-drop system builder, and PDF
reporting. Scoped with Paul (7 Jul) to build in phases, same pattern as the
weather tool. **Phase A, covered here and built this session, is core sizing
only**: straight-duct friction loss and velocity for circular, rectangular and
flat oval duct, plus a "propose a size" solver.

- **Phase B (interactive ductulator slider) — decided not needed, 8 July
  2026.** Paul's own call, revisited once the live 3-column sizing tool
  (Correction #2 onward) was working: a slider would only replicate the
  calculation the sizing tool already does live (change an input, watch
  velocity/friction rate respond instantly) with a different control widget,
  not add new capability. Descoped rather than deferred — not planned for a
  future session unless that changes.
- **Phase C** — the index-leg / system schedule builder: itemised fittings,
  a K-factor lookup (ASHRAE Fundamentals Ch.32 fitting database / CIBSE
  Guide C Section 4 — public standard data, not Lindab-specific), pressure
  drop per fitting/straight run and a running total. Branch balancing
  insight (comparing index legs against each other) stays deferred beyond
  this; scoped with Paul (8 July) to build a broad common fitting set — now
  **built and verified this session**, see the "Phase C" section below.
- **Phase D** — PDF report export for a duct run (the report engine at
  `web/app/reports/builder.py` is already generic and tool-agnostic — reuse,
  not rebuild, once Phase C exists to report on).

## Purpose

Given an airflow and a duct geometry (or a target velocity/friction rate),
compute velocity, straight-duct friction loss per unit length, and — for
rectangular and flat oval shapes — the circular equivalent diameter used to
size them off the same friction-loss basis as round duct. This is the
calculation core the "Quick Calculator" (spec section 2.1, Element 1) sits on
top of; the slider (Element 2) is a UI layer over the same functions, not a
separate calculation path.

## Method sources (public standards)

- **CIBSE Guide C, Section 4** ("Flow of fluids in pipes and ducts") — Darcy
  formula for pressure loss, use of the Colebrook-White friction factor for
  turbulent flow in ducts, standard-air convention, typical galvanized-steel
  duct roughness values, and the treatment of non-circular ducts via a
  circular equivalent diameter.
- **ASHRAE Handbook — Fundamentals (2021), Chapter 21 "Duct Design"** —
  Darcy-Weisbach pressure-loss equation, the Colebrook-White friction-factor
  relation (and the Swamee-Jain explicit approximation used here for
  computational efficiency per the source brief), the Huebscher equal-
  friction/equal-capacity rectangular equivalent-diameter correlation, and the
  corresponding flat-oval equivalent-diameter correlation.
- Swamee, P.K. & Jain, A.K. (1976), "Explicit equations for pipe-flow
  problems", ASCE Journal of the Hydraulics Division — source of the explicit
  friction-factor approximation to Colebrook-White used here.
- **Lindab Big Blue Book of Ventilation** (`Support/Duct_Standard_Sizes_Meters.xlsx`,
  Paul's own extract) — the real circular spiral-duct diameter/gauge/
  stock-vs-special-order series, and the real flat-oval major/minor
  combination series, both used directly as of v1.1 (see note below).

**Note on Lindab catalogue data (superseded 8 Jul; original EN 1506/DW144
placeholder note below kept for history).** The original build (7 Jul) used
the public EN 1506/DW144 preferred-diameter series as a clean-room-safe proxy
for Lindab's actual spiral-duct sizes, since Lindab's own dimensions were
assumed proprietary and unavailable. Paul then supplied his own copy of
Lindab's published catalogue data directly
(`Support/Duct_Standard_Sizes_Meters.xlsx`, extracted from the Big Blue Book
of Ventilation) — real third-party manufacturer data, not proprietary
Newsome data, so no clean-room concern. `STANDARD_DIAMETERS_MM` and the
circular stock-size dropdown now use this real data via
`LINDAB_CIRCULAR_CATALOG` — 29 diameters (63 mm–1600 mm) each carrying its
real sheet gauge and a standard/special-order-only flag (e.g. 180 mm, 224 mm,
280 mm and 600 mm are special order only; everything else in the range is
stock). A parallel `LINDAB_FLAT_OVAL_CATALOG` (19 major/minor combinations,
250×100 mm to 1000×300 mm) closes the "no public flat-oval standard series"
gap flagged in the original build — `snap_flat_oval_to_catalog()` picks the
nearest-at-or-above real combination by its own computed equivalent diameter.

*(Original 7 Jul note, kept for history: "the source brief asks for
snap-to-size against Lindab's spiral duct catalogue. Lindab's actual product
dimensions are proprietary manufacturer data, not a public standard, and are
not used here..." — this constraint no longer applies now that Paul has
supplied the real catalogue himself.)*

**Note on the flat-oval equivalent-diameter correlation:** implemented per the
commonly published closed-form (`equivalent_diameter_flat_oval`, cited above),
but — unlike the psychrometrics module's anchor values, which were checked
against ASHRAE HOF Table 3 — this specific coefficient set could not be
independently verified against a primary-source page in this session (no
internet access to the Handbook itself). Treat flat-oval results as
provisional pending a page-reference check against CIBSE Guide C or ASHRAE
Fundamentals Ch.21 before relying on them for a live client deliverable. This
is the same "flag the data gap rather than present false confidence" approach
the source brief itself asks for (section 3.2), applied here to a formula gap
rather than a fittings-catalogue gap. Circular and rectangular (Darcy-Weisbach,
Swamee-Jain, Huebscher) are standard, widely cross-published forms and are not
flagged.

## Conventions

- SI internally, canonical units matching the rest of `hvac_engine`:
  volumetric flow **m³/h** (matches `hvac_engine.units`' `vol_flow`
  convention, e.g. the psychrometric AHU tools), dimensions (diameter, width,
  height, major/minor axis) **metres**, velocity **m/s**, friction rate
  **Pa/m**, density **kg/m³**, kinematic viscosity **m²/s**.
- The web layer displays duct flow as **m³/s** in SI (not m³/h) — matching
  Paul's own reference tool's convention — via a dedicated `duct_flow`
  quantity in `app/units.py` distinct from the shared `vol_flow` quantity used
  elsewhere in the app; canonical SI value is unchanged (m³/h under the hood,
  same "engine is SI, unit choice is presentation-only" split as everywhere
  else). Duct dimensions display in mm (SI) / inches (IP); friction rate
  displays in Pa/m (SI) / in.wg per 100 ft (IP).
- **Standard air**: 20 °C, 101.325 kPa, ρ = 1.2 kg/m³, kinematic viscosity
  ν = 1.51×10⁻⁵ m²/s (CIBSE Guide C "standard air" convention). Both are
  function parameters with this default — not hardcoded — so a future
  phase can feed site-adjusted density (e.g. from `hvac_engine.psychrometrics`
  at the site's design altitude/temperature) without an API change. Not wired
  to site altitude yet in Phase A (flagged below).
- **Duct roughness**: galvanized steel, ε = 0.09 mm, also a function
  parameter with this default, overridable per material.
- Friction factor: **Swamee-Jain explicit approximation** to Colebrook-White
  (valid 4×10³ < Re < 10⁸, ε/D < 0.05 — the normal HVAC duct range), per the
  source brief's own suggestion of "high-accuracy explicit approximations…
  for computational efficiency". Laminar (`Re < 2300`) falls back to
  `f = 64/Re`, included for robustness at very low velocities though not a
  realistic HVAC duct condition.
- Solver ranges: diameter search 20 mm–3000 mm, velocity search 0.1–50 m/s —
  wide enough for any realistic HVAC duct; a target outside what's reachable
  in that range raises `ValueError` with the attempted bounds, rather than
  silently returning a bad answer.
- Aspect ratio (rectangular): flagged if width:height exceeds 4:1 (source
  brief section 2.3/3.3).
- Velocity/friction-rate "in range" thresholds are user-supplied; this module
  ships sensible **default** thresholds (`DEFAULT_MAX_VELOCITY` = 8 m/s,
  `DEFAULT_MAX_FRICTION_RATE` = 1.0 Pa/m — typical CIBSE Guide C low-velocity
  system guide values) that the web layer can offer as a starting point, not
  a fixed rule — real limits vary by application, system type and space
  (main run vs. branch, plant room vs. occupied space), which is exactly why
  the source brief calls these "user-defined or system-recommended".

## Functions

### Circular duct

`velocity_circular(volume_m3h, diameter_m) -> m/s`
V = Q / A, A = πD²/4.

`friction_rate_circular(volume_m3h, diameter_m, rho=RHO_STD, nu=NU_STD, roughness=ROUGHNESS_GALV_STEEL) -> (dp_dl, velocity, reynolds, friction_factor)`
Darcy-Weisbach: Δp/L = f · (1/D) · (ρV²/2), f via Swamee-Jain.

`size_circular(*, volume=None, velocity=None, diameter=None, friction_rate=None, rho=RHO_STD, nu=NU_STD, roughness=ROUGHNESS_GALV_STEEL) -> CircularResult`
Exactly two of the four keyword arguments must be given; solves for the other
two (the "any two variables" bi-directional flow, source brief section 2.1).
Volume and diameter are the true two degrees of freedom — every combination
resolves to a (volume, diameter) pair (directly, or by closed-form, or by
bisection where the relationship isn't invertible in closed form), then
velocity/friction_rate/Reynolds/friction-factor are all re-derived fresh from
that pair so every field in the result is mutually consistent.
`CircularResult(volume, diameter, velocity, friction_rate, reynolds, friction_factor)`.

`propose_circular(volume_m3h, velocity=None, friction_rate=None, snap=True, ...) -> CircularResult`
Convenience wrapper: given a flow and a target velocity **or** friction rate,
solve for diameter via `size_circular`, then (if `snap`) round up to the
nearest `STANDARD_DIAMETERS_MM` entry and re-resolve at that size (so the
returned velocity/friction rate reflect the real, snapped duct, not the
unsnapped theoretical one).

`snap_to_standard_diameter(diameter_m) -> m`
Nearest EN 1506/DW144 preferred diameter **at or above** the given value
(round up, never undersize).

### Rectangular duct

`equivalent_diameter_rectangular(width_m, height_m) -> m`
Huebscher equal-friction/equal-capacity correlation:
De = 1.30 · (a·b)^0.625 / (a+b)^0.25

`rectangular_from_equivalent_diameter(de_m, aspect_ratio) -> (width_m, height_m)`
Closed-form inverse of the above for a chosen aspect ratio r = width/height
(≥ 1) — see derivation note below.

`size_rectangular(volume_m3h, width_m, height_m, ...) -> RectangularResult`
Velocity = Q / (width·height) (the **actual** rectangular-duct velocity).
Friction rate = the friction rate of a round duct of diameter `De` carrying
the *same flow* Q (equal-friction basis — this is the entire point of the
equivalent-diameter method: it is not the friction rate you'd get from the
actual rectangular velocity and a hydraulic-diameter substitution).
`RectangularResult(volume, width, height, velocity, equivalent_diameter,
friction_rate, aspect_ratio, aspect_ratio_warning)`.

`propose_rectangular(volume_m3h, aspect_ratio, velocity=None, friction_rate=None, ...) -> RectangularResult`
Given a flow, a target velocity **or** friction rate, and a chosen aspect
ratio: finds the round-duct equivalent diameter via `size_circular`, converts
to width×height at that aspect ratio, and re-resolves via `size_rectangular`.
**Note (documented for the UI, not just here):** the target velocity in this
mode is the equivalent *round-duct* velocity used to pick the size — the
resulting actual rectangular velocity (in the returned `RectangularResult`)
will normally come out lower, because the equal-friction rectangle usually has
a larger cross-sectional area than the round duct it's equivalent to. This is
a known property of the ductulator method, not a bug — flagged so it isn't
mistaken for one when the two numbers don't match.

**Derivation of the closed-form inverse:** with b = a/r (a = width, b =
height, r = a/b ≥ 1), substituting into the Huebscher relation:

    De = 1.30 · a^1.0 · r^-0.625 · (1 + 1/r)^-0.25

(the exponents on `a` collapse to exactly 1 — `(ab)^0.625` contributes `a^1.25`,
`(a+b)^0.25` removes `a^0.25`.) So:

    width = De · r^0.625 · (1 + 1/r)^0.25 / 1.30
    height = width / r

### Flat oval duct

`equivalent_diameter_flat_oval(major_m, minor_m) -> m`
De = 1.55 · A^0.625 / P^0.25, where for a stadium (two semicircles of
diameter = minor axis, joined by a straight section of length major − minor):
A = b·(a−b) + (π/4)·b², P = 2·(a−b) + π·b. **Provisional — see the flat-oval
note above.**

`size_flat_oval(volume_m3h, major_m, minor_m, ...) -> FlatOvalResult`
Same pattern as rectangular: actual velocity from the real cross-sectional
area, friction rate from the round-duct equivalent at the same flow.

`propose_flat_oval(volume_m3h, minor_m, velocity=None, friction_rate=None, ...) -> FlatOvalResult`
Given a flow, a fixed minor axis, and a target velocity or friction rate:
solves for the major axis by bisection (no closed form here, unlike
rectangular — `equivalent_diameter_flat_oval` isn't invertible in `a` in
closed form because of the mixed linear/quadratic terms under the fractional
powers).

### Shared

`status(value, limit, amber_fraction=0.85) -> "green" | "amber" | "red"`
Traffic-light classification of a computed value against a threshold — feeds
the on-screen status dots (style v2, `app.css` `.dot.green/.amber/.red`,
approved 3 Jul, not yet used by any tool until this one).

`snap_to_increment(dimension_m, increment_mm=25.0) -> m`
Round a rectangular dimension up to the nearest increment (25 mm default —
source brief section 2.1's "lock to 25 mm increments" toggle).

`round_to_increment(dimension_m, increment_mm=25.0) -> m` (v1.2)
Round to the NEAREST increment (25 mm default) — a genuinely different rule
from `snap_to_increment`'s always-round-up, not a duplicate. `snap_to_increment`
exists for "never undersize" contexts (picking a circular stock diameter);
`round_to_increment` is for a fabricator working to a 25 mm sheet-metal grid,
who rounds to the closest practical size in either direction. Backs the
rectangular column's "Round to 25mm" web toggle (see Web architecture below).

`velocity_pressure(velocity_ms, rho=RHO_STD) -> Pa`
Pv = 0.5 · ρ · V² — the Bernoulli dynamic-pressure term, shown alongside
friction rate for every shape's own actual velocity (v1.1 addition, requested
alongside the 3-column web rebuild). Cross-checked against Paul's own
reference VB calculator screenshot: V = 4.43 m/s, ρ = 1.2 kg/m³ → Pv = 11.77 Pa
(`test_velocity_pressure_matches_screenshot_worked_example`). Given its own
`velocity_pressure` quantity in `app/units.py` (canonical Pa; SI display Pa,
IP display in.wg) rather than reusing the existing `pressure` quantity, whose
canonical/SI display is kPa (sized for barometric readings) — a kPa display
would round a duct's few-Pa-to-few-hundred-Pa velocity pressure to near zero.

### Cross-shape equivalence solvers (v1.1)

Added to support the rebuilt web tool's "nudge one dimension, the other
adjusts to hold the same duty" interaction (see Web architecture below) —
each is the inverse of an existing equivalent-diameter function, solving for
one free dimension given the other plus a target De:

`rectangular_other_side(de_m, known_side_m) -> m`
Symmetric in width/height — the Huebscher relation doesn't care which side is
"width" — so this one function serves both "solve height given width" and
"solve width given height". Bisection over a 20 mm–5000 mm search range
(`_SIDE_MIN`/`_SIDE_MAX`); De is confirmed monotonically increasing in the
free side over that range (checked numerically, not just assumed, across
representative width/height combinations before shipping).

`flat_oval_major_for_de(de_m, minor_m) -> m` *(already existed from the
original build; documented here for completeness alongside its new sibling)*
Solve the major axis for a fixed minor axis and target De — bisection, no
closed form (unlike rectangular) because of the mixed linear/quadratic terms
under the fractional powers.

`flat_oval_minor_for_de(de_m, major_m) -> m`
The reverse: solve the minor axis for a *fixed* major axis and target De —
needed for "nudge minor, major stays put". Minor ranges over (0, major]; De
is monotonically increasing in minor over that range (at minor = major the
shape is a true circle — the upper bound on De for that major axis).
Confirmed numerically monotonic and an exact round-trip inverse of
`equivalent_diameter_flat_oval` across representative major/target-De pairs.

## Web architecture (v1.1) — 3-column live tool

**This is the second major web-layer revision.** The first build (7 Jul) was
a single-shape-at-a-time page with a shape selector and "view as" conversion
links between full page reloads — mis-scoped against Paul's actual intent
(caught via his own screenshot and detailed follow-up feedback). v1.1 rebuilds
the web layer again, per Paul's explicit workflow description: volume + a
sizing basis (velocity or Pa/m) at the top, and all three shapes
(circular/rectangular/flat oval) shown **simultaneously** as three side-by-side
columns, all recomputing "with changes in primary input values" — not a
one-shape-at-a-time choice.

**Instant, no page reload — a deliberate, scoped exception to this app's
usual "everything is a plain GET, no JS required" convention.** Asked
explicitly (AskUserQuestion) whether the live-update feel needed to be
JS-driven and instant, or reload-per-step; Paul chose instant/no-reload. This
pulls forward a slice of what was originally scoped as "Phase B, the
interactive ductulator slider" — accepted as a conscious scope decision, not
scope creep, since it's the same underlying interaction Phase B was always
going to need.

- **`blueprints/duct.py::_compute_state(args, U)`** is the single calculation
  helper shared by both routes — `GET /duct-sizing/` (full page, server
  rendered on load) and `GET /duct-sizing/api/state` (JSON, called by
  `static/js/ductsizer.js` on every top-input change or per-column nudge, no
  navigation). The two routes can never disagree, and all unit conversion +
  display formatting happens exactly once, here — the JSON payload already
  carries pre-formatted display strings; JavaScript never repeats engine or
  unit maths.
- **State model**: the top inputs (volume, basis, target, thresholds,
  rectangular aspect ratio, flat-oval default minor) always drive a fresh
  reference equivalent diameter (`ref = size_circular(volume=..., **{basis:
  target})` — this is also exactly the circular column's own "auto" result).
  Each of the three columns is independently either "derived fresh" from that
  reference, or "pinned" to specific dimensions the user already
  nudged/selected (`circular_mm`; `rect_width` + `rect_height`; `oval_major` +
  `oval_minor` — each column's pin is completely independent of the other
  two, confirmed by test). A `nudge` / `nudge_value` pair means "the user just
  changed this one field to this value — hold this column's *current*
  equivalent diameter fixed (computed from its old pinned values) and solve
  the paired dimension" — exactly `rectangular_other_side` /
  `flat_oval_major_for_de` / `flat_oval_minor_for_de`.
- **Client responsibility, not server**: when a *top* input changes,
  `ductsizer.js` clears all three columns' pinned fields before calling the
  API, forcing a fresh derivation across the board — "all three update with
  changes in primary input values" falls out of this client-side reset, not
  server-side memory (the server is fully stateless per request, same as
  every other tool in the app).
- **Circular** gets a real Lindab stock-diameter `<select>` (built once at
  page load, not re-sent by the API — the option list never changes with
  state) instead of a nudge, since a circular duct has only one free
  dimension; selecting "Auto" reverts to the true, unsnapped calculated size.
- **No-JS fallback**: the whole form is also a plain GET form. A no-JS submit
  of the top "Calculate" button carries forward whatever pinned column state
  is currently in the (hidden) form fields rather than resetting it — a
  known, accepted degradation versus the JS path (which always resets pinned
  state on a primary-input change) — a "Reset all to calculated" link
  (plain `<a>` to the bare `/duct-sizing/` URL) is provided as the no-JS way
  back to fully fresh sizing.
- **Shareable URL preserved despite live updates**: every API response is
  applied to the DOM *and* used to rebuild the page's query string via
  `history.replaceState`, so the browser URL always reflects the exact
  current state (including any pinned/nudged columns) even though no
  navigation occurred — consistent with the rest of the app's "every result
  is a shareable link" convention.
- **Known, accepted rounding artifact**: because `duct_dimension`'s SI display
  precision is whole millimetres (0 dp), a nudge's "hold the old equivalent
  diameter fixed" calculation is done from the *rounded* mm value already on
  screen, not the full-precision SI value the previous request computed
  internally (there is no server-side session — every request is stateless,
  matching every other tool). This introduces a small drift in the true
  equivalent diameter per nudge (observed ~0.1–0.3 mm equivalent-diameter
  drift on a single nudge in verification, i.e. well under 0.1% of duty) —
  imperceptible for engineering purposes and smaller than any real
  manufacturing tolerance, but worth knowing so a future reader doesn't
  mistake it for a solver bug. Bounded per nudge, not unbounded — it does not
  compound catastrophically even across many successive nudges, since each
  nudge only reintroduces sub-mm rounding, not accumulating error.

## Web architecture addendum (v1.2) — rectangular lock + round-25mm, UI simplification

Off direct follow-up feedback on the v1.1 3-column tool: three refinements
to the rectangular column, plus removing four fields Paul said weren't
needed as always-visible top-level inputs.

- **Round-to-25mm** (`rect_round25`, a checkbox): when ticked, both
  rectangular sides quantise to the nearest 25 mm grid point via the new
  `round_to_increment()` (nearest, not always-up), and the nudge step
  switches from the general 10 mm/0.5 in grid to a 25 mm/1 in grid. Unticked
  (the default) gives true-to-the-millimetre free entry, unchanged from v1.1.
  Applies uniformly across all three rectangular code paths (auto-derivation,
  a transient nudge, and a persistent lock — see next point) so the checkbox
  behaves the same regardless of which is active.
- **Lock width / lock height** (`rect_lock`: `""` / `"width"` / `"height"`) —
  requested for a shallow-ceiling-void scenario, where one side is fixed by
  the building fabric, not by the airflow. This is a genuinely different
  behaviour from v1.1's plain nudge, not a rename of it: a nudge holds the
  *current* column's equivalent diameter fixed and is silently cleared back
  to fresh auto-derivation the next time a top input changes (v1.1
  behaviour, unchanged, and still what happens when `rect_lock` is empty). A
  lock is a *persistent* constraint — the locked side survives a top-input
  change (the client never clears it), and the free side is re-solved fresh
  against the *current* reference equivalent diameter on **every** request,
  including one triggered by a top-input change, not held from a stale prior
  nudge. Concretely: lock height at 300 mm, then increase the airflow — width
  grows to carry the extra duty while height stays exactly 300 mm, which is
  the ceiling-void use case working as intended. The web layer's per-column
  "Reset to calculated" action also clears the lock back to `""` (free),
  since resetting to calculated should mean fully fresh 2:1 auto-sizing, not
  a still-locked side.
- **Removed as always-visible top-level inputs**: Max Velocity, Max Friction
  Rate, Rectangular Aspect Ratio, Flat Oval Minor Axis. Paul's own
  assessment: these don't need a dedicated row. Thresholds now default
  silently to `DEFAULT_MAX_VELOCITY`/`DEFAULT_MAX_FRICTION_RATE`; rectangular
  aspect ratio defaults to 2:1 (still adjustable — nudging either side already
  changes the effective ratio at a fixed duty, which is the whole point of
  the nudge mechanism, so a separate ratio field was redundant once nudge
  existed); flat-oval minor axis defaults to 200 mm (adjustable via its own
  nudge control, same reasoning). All four remain readable from the query
  string with the old defaults if absent, so a hand-built/shared link that
  still carries them keeps working — only the rendered `<input>` was removed,
  not the server-side flexibility.
- **Column boxes widened** to match the Design Inputs panel's own width
  (`max-width: 1100px` on `.duct-columns`, matching the panel above) rather
  than an unbounded/ambient width inherited from the page's `.content`
  wrapper.

Verified: 3 new engine tests for `round_to_increment` (nearest-vs-always-up
distinction, exact-multiple passthrough, custom step) — 240 engine tests
total (up from 237). Web layer re-verified via a real Flask test client:
lock width persisting a fixed value while height re-solves to a *different*
value after a simulated volume change (and the reverse for lock height);
round-25mm producing exact 25 mm multiples in auto mode, in combination with
a lock, and on a live nudge; the four removed fields confirmed absent from
the rendered page but still accepted (and correctly applied) if hand-added to
the query string; full regression pass confirming every other page still
200s, including SI/IP end-to-end for the new lock+round25 combination.

## Web architecture addendum (v1.3) — rectangular width/height made fully independent

Paul's direct correction to v1.2's rectangular lock design, the same session
it shipped: v1.2's "nudge one side, the other auto-solves via
`rectangular_other_side()` to hold the same equivalent diameter" was the
*opposite* of what he wanted for rectangular specifically. His words: he
wants to "change the width and depth freely... and see the impact on
velocity, aspect ratio and pressure drop and rely on the traffic light
warnings to make a decision" — i.e. the user drives both dimensions directly
and reads the consequences off the live numbers and traffic-light dots,
rather than the tool silently solving one dimension to match the other.
Rectangular-only — circular's stock-diameter dropdown and flat oval's
nudge-and-solve behaviour are unaffected; Paul was explicit this feedback
didn't apply to them.

- **No more cross-solving between rectangular width and height, anywhere.**
  `rectangular_other_side()` stays in the engine (still a valid generic
  utility, and still used by flat oval's minor/major solve) but is no longer
  called from the rectangular code path in `blueprints/duct.py`. Editing
  width changes width only; editing height changes height only;
  `size_rectangular(volume, width, height)` is called directly on whatever
  pair currently exists.
- **Lock is now per-dimension**: `rect_lock_width` / `rect_lock_height`
  (independent `"1"`/`""` booleans) replace v1.2's single three-way
  `rect_lock` (`""`/`"width"`/`"height"`). Meaning is narrower than v1.2's,
  matching the simpler model — a locked dimension survives a top-input
  (volume/basis/target) change; an unlocked one resets to a fresh
  2:1-aspect-ratio value derived from the new reference equivalent diameter.
  That's the *only* thing lock does now; it no longer implies "the other
  side solves to match," since nothing solves anymore. Both sides can be
  locked simultaneously — no longer a contradiction now that there's no
  solving from the other side to conflict with.
- **UI**: the three-way Free/Lock Width/Lock Height radio group is gone.
  Each dimension (Width, Height) is its own row: an always-editable stepper
  plus a padlock-icon toggle button beside it (open/closed clasp SVG icons,
  swapped via a `data-locked` attribute, with a text label reading "Locked"
  or "Unlocked"). Both width and height are now *always* shown as editable
  fields — v1.2's stepper-vs-read-only-tag toggle (`rect-width-stepper` /
  `rect-width-readonly` etc.) is removed entirely, since there's no more
  "solved, therefore read-only" side. The round-to-25mm checkbox moved to
  its own left-justified row above the two dimension rows (previously
  right-aligned via `margin-left:auto` in the old controls row). The
  traffic-light legend below the Design Inputs panel gained padding
  (`.status-legend`: `padding: 10px 14px`, was margin-only).
- **Round-to-25mm** (`rect_round25`) unchanged in effect — still quantises
  to the nearest 25 mm grid via `round_to_increment`, still switches the
  nudge step to 25 mm — but now applies independently per dimension, since
  there's no paired solve step to also round.
- **Real bug found and fixed during this session's verification, not
  shipped**: rectangular's `if width_raw:` truthiness check treats a literal
  `"0"` query-string value as present (non-empty string, therefore truthy in
  Python), so a user typing `0` into either field reached
  `size_rectangular()`/`size_flat_oval()` directly rather than falling back
  to a derived default. Both functions computed velocity (a division by
  width×height or by flat-oval area) *before* their own positivity checks
  were reached, so this surfaced as a bare `ZeroDivisionError` (an
  uncaught-by-`except ValueError` 500) instead of the clean on-page error
  every other bad-input path in this app shows. Fixed at the engine
  boundary, same pattern as the existing `size_circular` zero/negative
  guard: `size_rectangular` now validates `width_m`/`height_m` > 0 up front,
  and `size_flat_oval` validates `minor_m > 0` and `major_m >= minor_m` up
  front (mirroring `equivalent_diameter_flat_oval`'s own check, just moved
  earlier so it's reached before the velocity division). +2 engine tests
  covering both.

Verified: 242 engine tests total (up from 240 — the 2 new zero/negative
rectangular- and flat-oval-dimension regression tests above). Web layer
verified via a real Flask test client rebuilt from Read-tool-confirmed
source (the sandbox mount truncated several files again this session,
including a freshly-`cp`'d `hvac_engine/units.py` missing `from_si`/
`decimals`/`__all__`, and `duct.html` cut off mid-template — both
re-synced from trusted content before testing): editing width alone leaves
height untouched and vice versa; locking width alone persists it across a
simulated primary-input (volume) change while the unlocked height re-solves
to a genuinely different value (and the reverse for locking height); both
sides locked simultaneously each independently hold their own value across
a primary-input change; round-to-25mm still quantises correctly per
dimension on a nudge; a literal zero width now returns a clean `error`
field (HTTP 200) instead of a 500; full regression pass confirms every
other page (dashboard, all four psychrometric tools, converter, reference
guides, projects) still 200s. `ductsizer.js` rewritten for the two
independent lock-toggle buttons (replacing the old 3-way radio handling and
the now-dead stepper-vs-readonly visibility toggle) and syntax-checked
clean. Real `flask run` click-through (the two padlock toggles, confirming
free width/height edits update velocity/aspect-ratio/friction-rate live,
and the ceiling-void scenario with height locked) and a git commit are
still the one thing only Paul's machine can confirm.

## Web architecture addendum (v1.4) — flat oval made independent but catalogue-locked

Paul's follow-up the same session as Correction #4: apply the same "stop
solving one dimension from the other" change to flat oval, but flagged a
real risk Correction #4 didn't have to handle — flat oval only exists in
Lindab's actual catalogued major/minor pairs (most majors only pair with a
handful of minors; e.g. a 900mm major only ships with a 300mm minor), so
naive independent entry could land on an unmanufactured combination. His
own example (a guessed 900mm major with only a limited set of depths)
matches the real catalogue exactly — 900mm only pairs with 300mm.

- **Six new engine functions** (`flat_oval_catalog_majors`,
  `flat_oval_catalog_minors_for_major`, `flat_oval_nearest_catalog_major`,
  `flat_oval_nearest_minor_for_major`, `flat_oval_step_major`,
  `flat_oval_step_minor`) give major and minor their own independent
  stepping through the *real* catalogue values (not a fixed mm delta —
  `LINDAB_FLAT_OVAL_CATALOG`'s majors/minors aren't evenly spaced).
  `flat_oval_major_for_de`/`flat_oval_minor_for_de` (the old equivalence
  solvers) stay in the engine, unused by this workflow now, same precedent
  as `rectangular_other_side` after Correction #4.
- **Hard validity guarantee, not just a stepping convenience.** Every
  request path in `blueprints/duct.py`'s flat-oval section — pinned, fresh,
  major-stepped, minor-stepped, typed, or a stale/hand-edited query string —
  ends with `major_mm = flat_oval_nearest_catalog_major(major_mm)` then
  `minor_mm = flat_oval_nearest_minor_for_major(major_mm, minor_mm)`. This
  is what makes an unstocked combination structurally unreachable, not just
  unlikely: even a URL hand-edited to an invalid pair (e.g. 900/100, which
  isn't a real Lindab combination) gets silently corrected to the nearest
  real one (900/300) rather than passed through or erroring.
- **Fresh/default derivation now catalogue-snapped too**, closing a gap that
  existed even before this correction: previously the flat-oval "auto" state
  used `propose_flat_oval` with a fixed 200mm minor and a continuous
  (unsnapped) major — never actually guaranteed to be a real stocked size.
  Now uses `snap_flat_oval_to_catalog(reference_equivalent_diameter)`, the
  same "nearest real combination at or above the target, never undersize"
  convention circular's stock-diameter snap already used.
  `DEFAULT_OVAL_MINOR_M`/`oval_minor_default` are removed as dead code (no
  longer needed once "auto" itself snaps to a catalogue combination).
- **UI**: major/minor number inputs are now `readonly` — the +/- steppers
  are the only way to change them (typing was the one interaction that could
  invite an off-catalogue value; removing it is simpler and safer than
  relying on typed-value snapping alone, though the server still snaps a
  typed value if one arrives via a hand-built link). Steppers send a step
  **direction** (`data-oval-step` + `data-dir`, posted as `nudge_dir`,
  "1"/"-1") rather than a client-computed next value, since the next real
  catalogue size isn't a fixed distance away — the server looks up the
  actual next/previous stocked size. Column subhead and the page's top
  note-banner updated to describe the new behaviour.
- **Ductulator (Phase B) descoped** — see the "Scope of this version"
  section at the top of this spec.

Verified: 254 engine tests (12 new — catalogue majors/minors-for-major
lookups, nearest-major/nearest-minor snapping, step-major/step-minor
clamping at both ends, stepping from a non-exact starting value, and an
exhaustive sweep confirming every real catalogue pair steps to another real
pair in both directions on both axes). Web layer verified via a real Flask
test client: the default/fresh oval state is always a genuine catalogue
pair; stepping major up/down lands on the correct next/previous real size
and forces an invalid minor to snap (walked major from 600mm all the way up
to 900mm confirmed minor correctly snaps to 900's only stocked minor, 300mm,
partway through the walk); stepping minor moves within the current major's
list only and leaves major untouched; clamping confirmed at both ends of
both axes; a typed/hand-edited value (620mm) snaps to the nearest real major
(600mm); a directly-constructed invalid pair (900/100) snaps to a valid one
(900/300) rather than passing through; an exhaustive sweep over every one of
the 19 real catalogue pairs, stepped in both directions on both axes,
confirmed every single result is still a genuine catalogue pair (76 stepping
checks, all valid); reset-to-calculated still works; rectangular's
Correction #4 independent-width/height behaviour re-confirmed unaffected
(regression); full page regression pass. `ductsizer.js` syntax-checked
clean. Real `flask run` click-through (the oval steppers, confirming the
displayed numbers only ever show real Lindab sizes, and that typing is no
longer possible in those two fields) and a git commit are still the one
thing only Paul's machine can confirm.

## Phase C — Index Leg pressure-drop table (module: `hvac_engine.fittings`)

Scoped with Paul (8 July, same session as the v1.4 addendum above) via 3
quick questions: a **broad common fitting set** (not a minimal starter set,
not the full ASHRAE Ch.32 catalogue), **extending the existing duct-sizing
page** (not a separate tool), and **instant no-reload updates** matching the
sizing tool's existing feel. His own framing of the workflow: state the duct
shape first, copy down the volume/size/velocity/pressure-drop-per-m from
whichever of the three already-sized shapes above is chosen, then build up a
run of straight sections (enter a length in m) and fittings (a collapsible
side list of fittings with K-factors and a thumbnail — "visual aid as
description only, could be confusing" otherwise) against a running
pressure-drop total.

### Method

Standard local-loss method (ASHRAE Fundamentals Ch.32, CIBSE Guide C Section
4): every fitting's pressure loss is expressed as a loss coefficient K
against the *velocity pressure* at that point in the system —

    dp_fitting = K * Pv,  where Pv = velocity_pressure(velocity)   (already
                          in hvac_engine.duct, Correction #2)

A straight run's pressure loss is just its already-computed friction rate
times its length —

    dp_straight = length_m * friction_rate_pa_per_m

Both draw on the *duty* (velocity, friction rate) of whichever duct shape
the user has selected as the "index leg" basis — no new sizing maths, this
module is purely an accounting layer over `hvac_engine.duct`'s existing
results.

### Data provenance — flagged honestly, matching the flat-oval note above

**The K-factors below are representative/typical single-point values of the
kind quick-reference duct design guides publish for common fittings, not the
full multi-parameter geometry-dependent correlations ASHRAE Fundamentals
Ch.32 and CIBSE Guide C Section 4 actually tabulate.** A real elbow's K
varies continuously with its radius-to-diameter (or radius-to-width) ratio;
a real tee/branch's K varies with the branch-to-main area ratio and the
flow-split fraction; a real damper's K varies with blade angle. This session
had no way to check a page-specific table against a primary source, so every
value below is a first-pass planning figure — cross-check against a real
ASHRAE/CIBSE copy (or a manufacturer's own published K-factor data, same as
the Lindab size catalogues) before relying on a result for an actual job.
Flagged on the tool's own page (a note-banner, same treatment as the
flat-oval equivalent-diameter note) as well as here.

### Fitting catalogue (`FITTINGS`, `hvac_engine/fittings.py`)

Two "families" — round (serves both circular and flat oval, since this app
already treats flat oval via its round-duct equivalent diameter throughout)
and rectangular. A fitting's family is a labelling/grouping aid for the
picker UI, not an enforcement rule — the pressure-drop formula (`K * Pv`) is
shape-agnostic, so a round-family K can still be applied against a
rectangular duct's velocity pressure if the user picks one; the web layer
tags each added row with its family so this stays visible, not hidden.

**Round family** (circular + flat oval), 11 fittings:

| key | label | K |
|---|---|---|
| `round_elbow_90_smooth_r1.5` | 90° Smooth Bend (r/D 1.5) | 0.22 |
| `round_elbow_90_smooth_r1.0` | 90° Smooth Bend (r/D 1.0) | 0.33 |
| `round_elbow_90_mitred` | 90° Mitred Elbow | 1.20 |
| `round_elbow_45_smooth` | 45° Smooth Bend | 0.15 |
| `round_tee_branch_90` | Tee — 90° Branch Takeoff | 1.00 |
| `round_tee_straight` | Tee — Straight-Through Main | 0.15 |
| `round_reducer_gradual` | Gradual Reducer (Contraction) | 0.05 |
| `round_enlarger_gradual` | Gradual Enlarger (Expansion) | 0.20 |
| `round_damper_open` | Butterfly Damper (Fully Open) | 0.20 |
| `round_entry_sharp` | Duct Entry (Sharp-Edged) | 0.50 |
| `round_exit` | Duct Exit to Space/Plenum | 1.00 |

**Rectangular family**, 8 fittings:

| key | label | K |
|---|---|---|
| `rect_elbow_90_mitred_no_vanes` | 90° Mitred Elbow (No Vanes) | 1.30 |
| `rect_elbow_90_mitred_vanes` | 90° Mitred Elbow (Turning Vanes) | 0.40 |
| `rect_elbow_90_radiused` | 90° Radiused Elbow (r/W 1.0) | 0.25 |
| `rect_tee_branch_90` | Tee — 90° Branch Takeoff | 1.00 |
| `rect_tee_straight` | Tee — Straight-Through Main | 0.15 |
| `rect_transition_contraction` | Transition (Contraction) | 0.05 |
| `rect_transition_expansion` | Transition (Expansion) | 0.20 |
| `rect_damper_open` | Blade Damper (Fully Open) | 0.25 |

19 fittings total. Each also carries a `thumbnail_key` (one of
`elbow_smooth`/`elbow_mitred`/`elbow_vaned`/`tee_branch`/`tee_straight`/
`transition`/`damper`/`entry`/`exit`) — a small shared original inline SVG
per *category*, not per fitting (19 bespoke drawings would be disproportionate
to a first-pass common set; the thumbnail's job is distinguishing categories
at a glance in the picker list, which a shared category icon already does).
All original line diagrams, drawn fresh for this app — same clean-room
approach as the design-guide article's diagrams.

### Functions

- `fitting_pressure_drop(k: float, velocity_pressure_pa: float) -> float` —
  `k * velocity_pressure_pa`.
- `straight_pressure_drop(length_m: float, friction_rate_pa_per_m: float) ->
  float` — `length_m * friction_rate_pa_per_m`. Rejects a non-positive length.
- `fittings_for_shape(shape: str) -> tuple[Fitting, ...]` — round family for
  `"circular"`/`"flat_oval"`, rectangular family for `"rectangular"`.
- `Fitting` (frozen dataclass): `key`, `label`, `family`, `k`, `thumbnail_key`.

### Web architecture — extends the existing duct-sizing page, no new route

Per the interaction-style decision above, this is a new section on
`/duct-sizing/`, computed inside the same `_compute_state()` and returned
under a new `index_leg` key from both the page render and `/api/state` — one
shared state function, same guarantee as the three sizing columns that the
JSON API can never disagree with the initial page render.

New query-string fields:

- `leg_shape` — `"circular"` / `"rectangular"` / `"flat_oval"`, which
  already-computed shape result supplies the duty (velocity, friction rate,
  velocity pressure) every row in the table is calculated against. Changing
  this recomputes every row's pressure drop against the new duty — existing
  rows are **not** cleared, so a user can compare the same run built in a
  different duct shape (an intentional side benefit of keeping the row list
  independent of the shape selector, not just an accident of the data
  model).
- `leg_row_count` — how many rows exist.
- Per row *i* (0-indexed): `leg_type_i` (`"straight"` / `"fitting"`), plus
  either `leg_length_i` (metres/feet, display units) or `leg_fitting_i` (a
  `FITTINGS` key).

Each row is computed independently inside its own try/except — an unknown
fitting key (e.g. a stale link referencing a fitting removed in a future
catalogue revision) or an unparseable/non-positive straight length marks
*that one row* with an error message and excludes it from the running total,
rather than failing the whole page the way a top-level input error does
elsewhere in this tool. This is deliberately more forgiving than the
existing single try/except around `_compute_state()`, because an index leg
can easily have a dozen rows and one bad one shouldn't hide the other
eleven's correct numbers.

The duty summary (Volume / Size / Velocity / Friction Rate) is read directly
off whichever of `circular`/`rectangular`/`flat_oval`'s already-formatted
display dicts `leg_shape` points at — no new engine calculation, pure
pass-through, so it can never disagree with the numbers already showing in
that shape's own column above.

### Verified (built and tested this session, 8 July)

292 engine tests total (33 new for `fittings.py`'s catalogue/pressure-drop
functions, plus 5 for the new `duct_run_length` unit quantity). Web layer
verified via a real Flask test client: a straight row's drop cross-checked
against `length x friction_rate` read directly off the selected column; a
combined straight+fitting run's total cross-checked against
`length x friction_rate + K x Pv` computed independently; an unknown fitting
key and a non-positive straight length each produce an isolated per-row
error excluded from the running total while every other row and the three
sizing columns stay correct; switching `leg_shape` to rectangular correctly
swaps in the 8 rectangular-family fittings and a "W x H" duty-size string;
an unknown `leg_shape` degrades only this table, not the rest of the page;
checked under both SI and IP; full regression pass across every other page
in the app. See CLAUDE.md's "8 July 2026, latest still" entry for the full
write-up. Real `flask run` click-through and a git commit remain the one
thing only Paul's own machine can confirm.

## Correction #6 (9 July 2026) — Index Leg rebuilt as an independent per-row system builder

Paul's direct architectural correction to the Phase C build above, delivered
the next session: the original design let a single shape selector define the
*whole* run, which doesn't match how a real index leg works. His own words:
"the shape choice appears to define the whole run and this doesn't work...
all the duct pieces along the length of the run are sequenced one by one and
as the run proceeds the run reduces in size, eventually the duct may change
to circular and then finally terminate at a grille... the index can be a
mixture of sizes, shapes, and fittings/straights, along with accessories such
as louvers, attenuators, dampers (VCD/FD), single blade dampers, flex and
grilles." His requested model: the top 3-column tool becomes a genuinely
independent duct sizer; the index leg below it is a separate builder where
each row carries its own volume/shape/type, a live-preview staging area lets
the engineer check a row before committing it, committed rows are directly
editable in place (so an over-pressure run can be tuned row by row without
rebuilding it), and the table supports Clear, per-row Remove, and Export.

On the accessory pressure-drop method specifically, Paul was explicit and
this governs the whole accessory row type: **"For custom items we add the
pressure drop directly, we may add some predefined K factors for some
elements later."** — manual direct-Pa entry only; no accessory K-factor
catalogue was built this pass.

### What changed

- **Full decoupling.** The three sizing columns and the index leg are now two
  completely independent state objects with two independent JSON endpoints
  (`/duct-sizing/api/state` for the sizer, `/duct-sizing/api/leg-state` for
  the leg) and two independent client-side fetch/apply cycles in
  `ductsizer.js`. `_compute_state()` no longer returns an `index_leg` key at
  all — the coupling that caused the original problem (one shape selector
  driving every row) is gone at the data-model level, not just hidden in the
  UI. `leg_shape` and the shape-drives-all-rows query fields from the
  original Phase C build are removed.
- **Per-row direct-evaluation sizing.** Each row now calls
  `hvac_engine.duct.size_circular`/`size_rectangular`/`size_flat_oval`
  directly with its **own** volume and its own dimensions — the row *is* an
  already-decided piece of duct, exactly matching a real index leg being a
  sequence of pieces that individually shrink, change shape, and terminate at
  a grille. Nothing is solved for a target; a row's velocity/friction
  rate/velocity pressure fall out of whatever volume+size the engineer typed.
- **Four row types**, replacing the old two (`straight`/`fitting`):
  - `straight` — as before: `length_m x friction_rate_pa_per_m`.
  - `fitting` — as before: `K x Pv`, fitting picked from the existing
    round/rectangular `fittings_for_shape()` catalogue for the row's own
    shape.
  - `flex` (new) — a straight run through `apply_flex_derate()`
    (`hvac_engine.duct`, new function, `FLEX_DUCT_DERATE = 1.5`) before the
    straight-run formula: `length_m x (friction_rate_pa_per_m x 1.5)`.
    **Assumed default, flagged to Paul**: flex duct is modelled as a straight
    run carrying a friction-rate derate multiplier rather than a distinct
    correlation — a common simplified approach, but the 1.5x figure is a
    placeholder pending a real manufacturer curve or a published flex-duct
    friction chart.
  - `accessory` (new) — manual direct-Pa entry per Paul's explicit answer
    above: no shape, no volume, no computed K-factor. New engine function
    `hvac_engine.fittings.accessory_pressure_drop(dp_pa) -> float` is the
    identity function with a `dp_pa >= 0` validation guard (rejects a
    negative entry with a clear `ValueError`, consistent with every other
    validated input in this app) — deliberately trivial, existing purely so
    the accessory path goes through the same "engine validates, web layer
    catches" pattern as every other row type rather than skipping validation
    because the maths happens to be a no-op. A `label` free-text field
    (default "Accessory") identifies the row in the table and CSV export
    since there's no fitting/shape name to fall back on.
- **Staging + commit workflow**, the mechanism behind "check a row before
  adding it, then tweak the next similar one without re-typing everything."
  A `stage_<field>` query-string namespace (mirroring the committed
  `leg_<field>_<i>` namespace field-for-field) computes a live preview
  completely independently of the committed rows table — typing in the
  staging area never touches the table until "Add to Table" is clicked.
  Clicking Add copies the current staging values into a new row at the next
  index, then — per Paul's own description of the workflow ("the shape and
  type... can remain the same as the run won't fundamentally change, just
  tweaks to size and volume") — clears only the "specific item" fields
  (length, fitting selection, accessory label, accessory dp) while
  preserving type/shape/volume/size, so adding a run of five straight
  circular sections at slightly different sizes doesn't require re-selecting
  "straight" and "circular" five times.
- **In-place row editing.** Every committed row's fields are live, editable
  inputs (not a static table with an edit button) — changing a row's volume
  or size fires the same debounced fetch as any other field and the row's
  own pressure drop, and the running total, update immediately. This is
  exactly Paul's stated use case: build the whole leg, notice the total is
  over pressure, adjust one row's size or volume without rebuilding the run
  from scratch.
- **Per-row and per-draft error isolation, extended.** Every row (and now
  also the staging draft) is computed inside its own try/except — unchanged
  principle from the original Phase C build, just applied one level deeper
  now that a row also carries its own volume/shape rather than inheriting
  them from a single page-level shape selector. A bad row's error can never
  affect any other row, the running total (which excludes only the failed
  row), or the staging preview.
- **Clear Table, per-row Remove, CSV Export** — all new. Clear resets
  `leg_row_count` to 0. Remove deletes one row; because rows are read fresh
  from the DOM by loop position on every request (no separate client-side
  row-index array to keep in sync), removing a row automatically renumbers
  the rest with no extra bookkeeping. Export (`GET
  /duct-sizing/index-leg/export.csv`) recomputes from the exact same query
  string the page is showing — same "every result is a shareable/exportable
  URL, computed once, never a stale snapshot" principle as the rest of the
  app — and returns a `text/csv` attachment with a header row, one data row
  per committed row (type/shape/volume/size/velocity/velocity
  pressure/friction-rate-or-K/length/pressure-drop), and a final TOTAL row.
  **Assumed default, flagged to Paul**: this CSV column layout/format hasn't
  been reviewed against any specific downstream use (e.g. a particular
  report template) — easy to adjust once Paul knows what he wants to do with
  an exported leg.
- **Free-typed row sizing — assumed default, flagged to Paul.** Unlike the
  top 3-column sizer's circular stock-diameter snap and flat-oval catalogue
  lock, index-leg rows accept any typed size with no catalogue snapping.
  This matches "a real index leg is whatever the engineer actually specified
  on a drawing," but means nothing stops a row being sized to a diameter
  Lindab doesn't stock — worth a follow-up if Paul wants the same
  catalogue-locking discipline applied here too.

### Web architecture

- `blueprints/duct.py` — `_compute_leg_state(args, U)` is the new single
  entry point (mirrors `_compute_state()`'s existing "one function, two
  routes can never disagree" pattern): computes `row_count` rows (each via
  `_compute_row()`, its own try/except, falling back to `_blank_row()` on
  failure) plus one staging draft (also its own try/except), and returns
  `shape_options`/`type_options`/`fittings_by_shape` alongside the computed
  data so the template/JS never hardcode the catalogue. `ROW_FIELDS` (12
  fields: type/shape/volume/diameter/width/height/major/minor/length/
  fitting/label/dp) is the one shared field list every row and the staging
  draft both read through `_row_field_getter()`.
- `GET /duct-sizing/` — full page, server-rendered on load, includes both the
  sizer and the leg builder.
- `GET /duct-sizing/api/state` — sizer only (no leg data at all now).
- `GET /duct-sizing/api/leg-state` — leg only (no sizer data at all).
- `GET /duct-sizing/index-leg/export.csv` — CSV attachment, recomputed from
  the query string.
- `templates/duct.html` — new `leg_field_grid` macro (the 12-field grid,
  `data-row-field`/`data-shape-field`/`data-size-for`/`data-type-for`
  attributes driving client-side show/hide of the fields relevant to the
  current type/shape), used identically for both the staging area and every
  committed row.
- `static/js/ductsizer.js` — the sizer's existing logic is untouched apart
  from removing every reference to the old shape-driven leg rendering. A new,
  fully independent Leg module (gated on the presence of `#leg-panel`)
  mirrors the field-grid macro client-side (`buildFieldGridHtml()`), reads
  committed rows fresh from the DOM by loop position on every request
  (`readFieldsFrom` + `buildLegParams`), rebuilds the whole rows table from
  each JSON response, and updates the CSV export link's `href` after every
  change so Export always reflects the current on-screen state.

### Verified (9 July 2026)

Engine: 298 tests total (6 new — `apply_flex_derate`'s default multiplier,
that it always increases the friction rate, and a custom-multiplier case, in
`test_duct.py`; `accessory_pressure_drop`'s identity behaviour, zero-allowed
boundary, and negative-rejection, in `test_fittings.py`).

Web layer verified via a real Flask test client, 14 checks: default page
load carries both the sizer and the new leg-builder markup; the default
(no-rows) leg state always returns a valid staging preview with no error; a
single circular straight row's pressure drop cross-checked exactly against a
direct `size_circular()` + `straight_pressure_drop()` call; a 4-row mixed leg
(circular straight, rectangular fitting, circular flex, accessory) with each
row a genuinely different shape/volume — the running total cross-checked
exactly against the sum of four independently-computed engine calls,
confirming rows really are sized independently rather than inheriting a
shared duty; an unknown fitting key on one row produces an isolated error
that excludes only that row from the total while the other three still
compute and sum correctly; a negative accessory dp is rejected with a clean
per-row error; `/api/state` and `/api/leg-state` confirmed to carry zero
overlap in their response keys (genuine decoupling, not just a UI-level
illusion); CSV export returns `text/csv` with the correct row count and a
TOTAL row matching the on-screen total; Clear Table returns an empty row
list; the full leg recomputes correctly end-to-end under the IP unit system;
editing a committed row's volume changes that row's pressure drop on the
next fetch; a row with a shape but no explicit dimensions falls back to
sensible defaults rather than erroring (the shape-switch case); a genuinely
unparseable numeric field still produces a clean per-row error, not a crash;
full regression pass confirms every other page in the app (dashboard, all
four psychrometric tools, converter, reference guides, projects, weather)
still 200s.

Note for future test-writing in this app: `duct_flow`'s SI **display** unit
is m³/**s** (canonical storage is m³/h — see the "Conventions" section
above), and `duct_dimension`'s SI display unit is **mm** (canonical storage
is metres) — sending a raw query-string value assuming the canonical unit
rather than the display unit is an easy self-inflicted test bug (hit and
resolved during this session's own verification, not a defect in the
shipped code).

**This session hit a new, worse variant of the sandbox mount's staleness
issue**: bash-served reads of several freshly-rewritten web-layer files
(`duct.py` blueprint, `duct.html`, `ductsizer.js`, `app.css`) returned
entirely unrelated stale content from an earlier point in the session, or
0 bytes, rather than the previously-seen truncation/null-byte-padding
pattern. Worked around by writing verified file content directly into `/tmp`
via bash heredocs (bypassing the Cowork outputs directory and mount
entirely for this step) rather than the previous Write-then-`cp` pattern —
this proved reliable and is worth using first, not as a fallback, if this
recurs. **Real `flask run` click-through (the staging area, Add to Table,
in-place row editing across all four row types, Clear, Remove, and a
downloaded CSV) and a git commit remain the one thing only Paul's own
machine can confirm.**

## Not yet (Phase A/C gaps, deliberate)

- Site-altitude-adjusted air density (currently standard air only; the
  parameter exists on every function so this is a non-breaking follow-up).
- Ceiling-void constraint (lock max height, scale width to hit target area).
- Branch balancing (comparing multiple index legs against each other) —
  stays deferred beyond the single-run pressure-drop table above.
- The full ASHRAE Ch.32/CIBSE Guide C Section 4 geometry-dependent K-factor
  tables (r/D-varying elbow curves, area-ratio-varying tee/branch tables) —
  the catalogue above is a representative single-point first pass; see the
  data-provenance note.
- The interactive ductulator slider — Phase B, decided not needed (see
  "Scope of this version" at the top).
- PDF export for a duct result — Phase D (reuses the existing generic report
  builder once there's a system/run to report on, not just one duty point).

## Acceptance tests

Since no primary-source worked example was available to check against in this
session (unlike psychrometrics' HOF Table 3 anchors), tests in
`test_duct.py` verify:

- **Internal consistency / round-trip**: for a grid of (Q, D) pairs, every
  pairwise combination of two known variables fed into `size_circular`
  resolves back to the same four values as the direct (Q, D) calculation,
  within tight tolerance.
- **Friction-factor sanity bound**: Swamee-Jain output falls within the
  well-known Moody-chart range for the relevant Reynolds number/relative
  roughness (e.g. Re ≈ 1×10⁵, ε/D ≈ 2×10⁻⁴ → f ≈ 0.018–0.020, smooth-pipe
  turbulent regime).
- **Rectangular**: `rectangular_from_equivalent_diameter` is a true algebraic
  inverse of `equivalent_diameter_rectangular` (round-trip to float
  tolerance) for a range of aspect ratios; equal-friction De for a square
  duct differs from the equal-*area* circular diameter (they are deliberately
  different quantities — confirms the implementation isn't accidentally using
  the simpler equal-area formula).
- **Flat oval**: degenerate case minor = major (a true circle) comes out
  *close* to De = d but not exact (~0.3% high with the 1.55 coefficient used
  here) — checked as an approximate sanity bound (within 1%), not exact
  equality. This is expected, not a bug: the flat-oval correlation is an
  independent empirical fit over the flat-oval product range (major
  meaningfully greater than minor), not derived to be asymptotically exact at
  an edge case no manufacturer actually produces — worth knowing so a future
  reader doesn't "fix" the coefficient to force exact equality here.
- **Aspect ratio / snap / status**: boundary behaviour at exactly 4:1, snap-up
  (never down) at and between standard sizes, and the three status bands.
- **v1.1 additions**: Lindab circular catalogue count/ordering/gauge/
  standard-vs-special-order flags cross-checked against known entries from
  the source spreadsheet; flat-oval catalogue count and snap-to-nearest-above
  behaviour (never undersizes, picks the true nearest qualifying entry, not
  just any qualifying one); `velocity_pressure` checked against the
  screenshot worked example and its `rho`-scaling/default behaviour;
  `rectangular_other_side` and `flat_oval_minor_for_de` round-trip-inverse
  and monotonicity checked numerically across representative inputs before
  being wired into the live web tool. 237 engine tests passing (up from 211).
  Web layer verified via a real Flask test client against both routes: all 3
  columns' numeric agreement with direct engine calls, the circular
  stock-size pick, both nudge directions (with the equivalence-holds check
  above, to a 0.5 mm tolerance for display-rounding), per-column
  independence (nudging one column leaves the other two's pinned state
  untouched), primary-input-change reset, bad/zero/unreachable-target error
  paths (still return 200 with a clean `error` field from the JSON route,
  never a 500), the friction-rate basis path, and SI/IP end-to-end. Full
  regression pass confirms every pre-existing page still 200s.
