# Functional Spec — Weather & Climatic Design Data

**Engine module:** `hvac_engine.climate` (pure — no network, no dependencies)
**Web layer:** `web/app/weather_client.py` (Open-Meteo HTTP client + wet-bulb enrichment),
`web/app/blueprints/weather.py` → `/weather`
**Status:** to build (this spec written first, per the project's spec-first rule).
**Standards cited:** ASHRAE Handbook of Fundamentals 2017/2021, Chapter 14 ("Climatic
Design Information") — percentile method only, applied here to a different (open)
dataset. Not an ASHRAE data product; see Clean-room / accuracy note below.

## Purpose

A site weather lookup: the user finds a project location on a map (or by text search),
and the tool returns cooling and heating **design conditions** for that exact
latitude/longitude — the peak summer and winter dry-bulb (and coincident wet-bulb)
figures an engineer currently pulls from an ASHRAE climatic-design table for the
nearest station. This is the module Paul currently does by hand from ASHRAE's 5-year
data; the output is designed to plug straight into the future Load Calculator module
(site design conditions are one of its required inputs) and into the existing
psychrometric tools (a cooling-coil or AHU-design "on-coil" outdoor air state).

Because the underlying dataset is a global reanalysis grid rather than a station
network, results are available for *any* coordinate — not just the nearest airport —
which is a genuine advantage for sites far from a reference station, but it is a
different data source from ASHRAE's own tables and must never be presented as
ASHRAE data (see Clean-room / accuracy note).

Deliberately out of scope for this pass (flagged for a later spec): the future-climate
/ climate-change offset (+ΔT scenario toggle), degree-day totals, solar/wind design
data, and saving a location against a Project (Projects is still a static placeholder —
same "session now, real thing later" pattern as the PDF report's Project/Author fields).

## Data sources

Both are free, keyless, and already fit the project's "no vendor lock-in, no card on
file" constraint from the deployment review.

- **Geocoding — Open-Meteo Geocoding API** (`https://geocoding-api.open-meteo.com/v1/search`).
  Chosen over Photon/Nominatim for one reason worth recording: it returns **elevation**
  for every result, which feeds directly into the barometric-pressure-from-altitude
  calculation every psychrometric tool already uses
  (`hvac_engine.psychrometrics.pressure_from_altitude`) — one provider serves both the
  location pin and the site pressure, no second geocoder needed. Trade-off flagged for
  Paul: its free-text matching (GeoNames-backed) is weaker on UK postcodes than
  Photon/Nominatim; if postcode-level search precision proves insufficient in practice,
  swap the search call for Photon (same `GeoResult` shape, one function to change) —
  Photon results would just need an elevation fallback added.
- **Historical weather — Open-Meteo Historical Weather (Archive) API**
  (`https://archive-api.open-meteo.com/v1/archive`), ERA5/ERA5-Land reanalysis, hourly,
  back to 1940, global coverage at native ~9-25 km grid resolution. Hourly variables
  used: `temperature_2m`, `dew_point_2m`. Requested with `timezone=auto` so the returned
  hours are in the site's local time — design-condition percentiles are conventionally
  computed against local calendar years, not UTC.

## Method — replicating ASHRAE's percentile design conditions

ASHRAE HOF Ch.14 design values (0.4%/1%/2% cooling, 99.6%/99%/98% heating) are **annual
cumulative frequency of occurrence** values, not simple all-time maxima/minima, and not
a single multi-year pooled percentile either. The correct method, implemented here:

1. For each *local calendar year* fully covered by the archive query, take that year's
   hourly dry-bulb series.
2. **Reject years with material missing data** (< 95% hourly coverage, i.e. ERA5 not
   yet finalised for very recent dates, or a gap in the record) rather than let a thin
   year skew the average. The result reports how many of the requested years actually
   qualified.
3. Sort that year's hourly values. For a cooling percentile *p* (e.g. 0.4%), take the
   value at the *p*-th percentile **from the hot end** — the value exceeded by only
   *p*% of that year's hours. For a heating percentile (e.g. 99.6%, meaning 0.4% of
   hours are colder), take the value at the (100−99.6)=0.4th percentile **from the cold
   end**. Both are the same primitive with a `tail="high"|"low"` flag — see Engine API.
4. Repeat per year, then **average the per-year values across all qualifying years**.
   This is the actual ASHRAE method (it smooths one freak year rather than letting a
   single heatwave or cold snap dominate) and is different from — and more correct
   than — sorting the entire multi-year pooled dataset once.
5. **All 8760/8784 hours of the year are used**, not a manually chosen "summer months"
   or "winter months" window — the percentile threshold naturally lands wherever the
   extreme hours actually fall. (An earlier draft of this idea, from a scoping
   conversation, suggested pre-filtering to Jun-Aug / Dec-Feb; that is a shortcut for a
   simple max/min approach and is unnecessary — and slightly wrong — once the proper
   percentile method is used.)
6. **Mean coincident wet-bulb (MCWB)** for each cooling percentile: within each
   qualifying year, take the set of hours whose dry-bulb is at or above that year's
   threshold value from step 3, compute each of those hours' wet-bulb (see below), and
   average within the year; then average those per-year figures across years — the
   same two-level averaging as the dry-bulb value itself. This is a documented
   simplification of ASHRAE's own coincident-value method (which bins hours within a
   narrow band around the threshold rather than everything above it); flagged as a
   scope decision — the two methods should read within a few tenths of a degree of
   each other for enough years of record, but this one is far simpler to implement
   and explain. Only a small number of hours per year (typically 20-90, depending on
   the percentile) ever need a wet-bulb calculation — never the full multi-year series
   — which keeps this fast.
7. **Wet-bulb from dry-bulb + dew-point** reuses the existing engine, not new
   psychrometric maths: `hvac_engine.psychrometrics.state(t_db, tdp=t_dp, p=p)` → `.t_wb`.
   `p` is the site's design pressure from `pressure_from_altitude(elevation)`, using the
   elevation the geocoder returned for this location — so this module is a *consumer*
   of the existing psychrometrics engine, not a duplicate of it.

## Years of record

User-selectable: **10 / 15 / 20 years** (default **20**), ending at the last fully
complete local calendar year. Framing for the UI: more years smooths year-to-year
variability but reflects an older climate baseline; fewer years is more reflective of
recent conditions but noisier. (This is the natural seam where a future "future
climate" scenario spec would plug in a +ΔT shift on top of the historical baseline —
deliberately not built here.)

## Engine API — `hvac_engine.climate` (pure, dataclasses + arithmetic only)

```
@dataclass(frozen=True)
class HourlyRecord:
    year: list[int]          # local calendar year for each hour, same length as t_db
    t_db: list[float]        # dry-bulb, degC
    t_dp: list[float | None] # dew point, degC (None = missing hour)

@dataclass(frozen=True)
class CoolingPoint:
    db: float         # design dry-bulb, degC
    mcwb: float        # mean coincident wet-bulb, degC

@dataclass(frozen=True)
class DesignConditions:
    years_requested: int
    years_used: int                       # after rejecting incomplete years
    rejected_years: list[int]
    cooling: dict[str, CoolingPoint]       # keys "0.4", "1.0", "2.0"
    heating: dict[str, float]              # keys "99.6", "99", "98" -> design DB
    extreme_max_db: float                  # single hottest hour in the whole record
    extreme_min_db: float                  # single coldest hour in the whole record
    warnings: list[str]

annual_percentile(values_by_year: dict[int, list[float]], fraction: float,
                   tail: Literal["high", "low"]) -> dict[int, float]
    # per-year threshold value at the given tail fraction, one entry per input year

design_conditions(record: HourlyRecord, wet_bulb_fn: Callable[[int], float]) -> DesignConditions
    # wet_bulb_fn(hour_index) -> wet-bulb degC for one hour; the caller (web layer)
    # supplies this so the pure engine never has to know about psychrometrics.state()
    # or pressure — it just asks for wet-bulb at the specific hour indices it needs.
```

Kept dependency-free and network-free like the rest of `hvac_engine`: it operates on
plain lists the web layer has already fetched and parsed, exactly the same "engine
stays pure, I/O happens at the web boundary" split the units/altitude work already
established. Fully unit-testable with small synthetic multi-year series with known
percentile answers — no network calls in the test suite.

## Web layer — `web/app/weather_client.py` (new — I/O boundary, not part of the engine)

```
@dataclass
class GeoResult:
    name: str; admin1: str; country: str
    lat: float; lon: float; elevation_m: float

geocode_search(query: str, count: int = 8) -> list[GeoResult]
fetch_design_conditions(lat: float, lon: float, elevation_m: float, years: int) -> DesignConditions
    # calls the archive API, builds a HourlyRecord, and supplies design_conditions()
    # a wet_bulb_fn backed by hvac_engine.psychrometrics.state(..., tdp=...)
```

`requests` is added to `web/requirements.txt` (not to the engine's dependencies —
the engine stays at zero dependencies). Reasonable timeouts (10 s geocoding, 30 s
archive fetch — a 20-year hourly pull is a few MB of JSON) with a clear on-page error
if either API is unreachable, matching the "surface a clear error" precedent set for
the standalone chart PNG export. No caching layer yet (flag for later, once repeated
same-location lookups within a session become a real cost — no Redis/cache
infrastructure exists yet, same "not yet" flag as the PDF report's project database).

## Web tool — `/weather`

Follows the app's existing conventions: server-rendered, shareable GET URLs, same
`panel` / `form-grid` / `results` table / `note-banner` / `warn-banner` classes and
`details.notes` pattern already used across the psychrometric tools, same PDF-report
pattern (`_report_form.html`, a sibling `/report` route re-running the identical
calculation from hidden fields — no server-side session).

- **Search box** (typeahead against a new `GET /weather/search?q=` JSON endpoint that
  thinly wraps `geocode_search`) and a **Leaflet.js map** (OpenStreetMap tiles, loaded
  from CDN — the first external CDN dependency in this app; flagged for Paul, easy to
  self-host later if the product needs to work fully offline). Picking a search result
  or clicking the map sets `lat`/`lon`/`place` and resubmits as a normal GET, consistent
  with how the unit converter's selects auto-submit — no bespoke client-side rendering
  path to maintain.
- **Years of record** selectbox (10/15/20, default 20), also part of the GET query so
  a specific lookup is a shareable link.
- **Results**, once a location is set: a primary results table — Cooling Design
  Conditions (0.4%/1%/2% DB with MCWB) and Heating Design Conditions (99.6%/99%/98%
  DB) — using the existing unit-aware `U.fmt`/`valunit` rendering so IP users see
  °F/gr·lb automatically. A `details.notes` disclosure holds the extended/secondary
  figures (absolute record max/min DB, years actually used vs requested, any rejected
  years) so the primary table stays short and scannable, the same pattern the coil
  tool already uses for its application notes.
- A **note-banner** always shown alongside results: *"Estimated from ERA5 reanalysis
  data (Open-Meteo), not an official ASHRAE/CIBSE design-condition table. For
  business-critical plant, cross-check against the nearest station's published
  design data."* — the honesty flag this module needs given the accuracy caveat below.
- **PDF report**: reuses `app/reports/builder.py` unchanged (it is already
  tool-agnostic). Inputs table: location name, lat/lon, elevation, years of
  record/used. Results table: the same cooling/heating rows as on screen. No chart —
  there is no natural psychrometric process to draw for a bare design-condition
  lookup, and `build_pdf(..., chart_png=None)` already supports this.
- Nav / dashboard placement (flagged, easy to rename later): a new top-level nav
  group **"Site Data"** with one item **"Weather & Design Conditions"**, positioned
  after Projects and before Air Treatment — it is a prerequisite input to the design
  tools rather than one of the three disciplines, so it doesn't fit the existing
  Air Treatment/Air Distribution/Hydronics grouping. Dashboard tile uses the existing
  neutral `tile-util` tint (same reasoning as the Unit Converter: a utility input, not
  a discipline calculator).

## Clean-room / accuracy note

No code, data, or design here comes from the archived prototype or from Newsome's
internal tools — the method is implemented directly from the published ASHRAE HOF
Ch.14 percentile definition, applied to Open-Meteo's public ERA5 reanalysis feed.
Genuinely new engineering caveat worth recording in the product itself (not just this
spec): **ERA5 is a reanalysis model, not raw station observations** — it is very good
for spatial coverage (any lat/lon, not just airports) but its extremes are typically
slightly damped compared to a real thermometer at a real station, because the model
grid smooths sub-grid-scale spikes. That is *why* the note-banner above exists on
every result: this tool is a strong first-pass site figure and is uniquely good for
sites far from any reference station, but it is not a substitute for a published
ASHRAE/CIBSE design-condition table on a project where the design margin matters.

## Addendum (6 Jul 2026) — full psychrometric states, memory slots, On This Day

Follow-up scope, requested after the first working version above: present Summer/
Winter/Max-Min as three columns each showing a *complete* psychrometric state (not
just DB and, for cooling, MCWB), let the user copy any of those conditions into one
of 3 labelled "memory slots" for reuse in a future module, and add a per-day hourly
lookup independent of the multi-year percentile calculation.

- **Heating gained a mean coincident wet-bulb, symmetric with cooling.** ASHRAE
  heating tables don't traditionally carry a coincident-humidity column (winter
  latent load usually isn't the governing case), but every design point in this
  module now resolves to a full state, so `hvac_engine.climate` computes an MCWB for
  heating the same way it already did for cooling — same per-year-then-average
  method, just over each year's *coldest* identified hours instead of the hottest.
  `CoolingPoint` is renamed `DesignPoint` (used for both `cooling` and `heating`
  dicts) since it's no longer cooling-specific.
- **`DesignConditions` gained `extreme_max_db_dp`/`extreme_min_db_dp`** — the
  coincident dew point at the record max/min dry-bulb hour (same index already used
  for `extreme_max_db_at`/`extreme_min_db_at`, no extra pass over the data). `None`
  if that specific hour's dew point was missing — degrades gracefully rather than
  raising, since a single record hour's data gap shouldn't block anything else.
- **New web-layer bundle `WeatherResult`** (`weather_client.py`): wraps the raw
  `DesignConditions` plus every design point already resolved to a full
  `hvac_engine.psychrometrics.PsychroState` (DB/WB/RH/Dew Point/Moisture Ratio) —
  `cooling_states`/`heating_states` (keyed the same as `dc.cooling`/`dc.heating`)
  and `max_state`/`min_state`. Resolution never raises: an unresolvable pair (e.g.
  missing dew point at the exact record hour) yields `None` for that one state
  rather than failing the whole page — the raw dry-bulb value is always available
  regardless via `dc.*` directly. `fetch_design_conditions()`'s return type changed
  from `DesignConditions` to `WeatherResult` (its only caller is this app's own
  blueprint, so no external compatibility concern).
- **New `fetch_hourly_for_date()`** — a single-day archive fetch (not a year range),
  deliberately independent of `fetch_design_conditions()`: On This Day never
  re-triggers the multi-year percentile calculation, so picking a new date is fast
  regardless of how slow the Summer/Winter/Max-Min fetch was.
- **Web tool restructured**: the old two stacked tables (Cooling, Heating) plus a
  separate Extremes table are now three side-by-side columns — Summer, Winter,
  Absolute Max/Min — each a vertical DB/WB/RH/Dew Point/Moisture Ratio stack.
  Summer/Winter each have a percentage selector (0.4/1/2% cooling, 99.6/99/98%
  heating; default 1%/99% per product decision) that swaps between three
  server-rendered blocks client-side (`weathermap.js::setPctBlock`) — no
  client-side recompute or reformatting, since every percentile's full state is
  already rendered in the page, just hidden.
- **Memory slots** (`app/climate_slots.py`): 3 session-backed slots, each a label
  plus a full condition (db/wb/rh/dp/w/source). Product decision: slots are
  session-wide (so a future consumer — a psychrometric tool or the Load Calculator
  — can read them the same way once built) but the *visible banner* only renders on
  the Weather page for now. A "Copy to Slot" mini-form sits under every
  Summer/Winter percentile block and the Max/Min column; values travel as hidden SI
  fields taken from the exact state just displayed, so a slot can never disagree
  with what was on screen when copied. Same "session now, real persistence once
  auth lands" pattern as the unit-system preference and the PDF report's
  Project/Author fields.
- **On This Day**: a date picker (HTML5 `<input type="date">`, bounded to
  Open-Meteo's ERA5 archive start (1940) through yesterday) below the Design
  Conditions section. Submits as its own form (`#day-form`, separate from
  `#weather-form`) so picking a date never re-runs the percentile fetch. Renders an
  hour-by-hour table (DB/WB/RH/Dew Point/Moisture Ratio) for the selected date at
  the already-picked location; a missing hour degrades to "—" for that row rather
  than dropping it, so every hour of the day still gets a row.
- Product decision explicitly accepted: because the Design Conditions section and
  On This Day section share one page/one GET route, picking a new "On This Day"
  date currently *also* re-runs the (slow) multi-year percentile fetch if a
  location is set, even though On This Day itself doesn't need it — a redundant but
  not incorrect refetch. Flagged rather than fixed with an AJAX endpoint, to avoid
  duplicating unit-aware formatting logic in JavaScript; ties into the "caching
  fetched archive data" item below, which would remove the redundancy for free once
  built.

## Not yet (flagged for future specs)

- Future-climate offset (+ΔT by scenario/year) — the natural next spec once this
  baseline module is proven; the years-of-record selector above is the seam it plugs
  into.
- Saving a looked-up location against a Project (waits on the same auth/Projects
  database dependency already flagged in SPEC-pdf-report.md).
- Reading memory slots from a psychrometric tool or the future Load Calculator —
  the slots are already session-wide and ready for this; only the consuming side
  doesn't exist yet.
- Renaming/editing a saved slot in place (currently: clear it and copy a fresh
  condition with the label you want) and copying a single On This Day hour into a
  slot (currently slots only come from the Summer/Winter/Max-Min columns).
- Caching fetched archive data (per-location, keyed on lat/lon rounded + years) to
  avoid re-fetching a multi-MB payload on every repeat lookup — would also remove
  the On This Day redundant-refetch noted in the addendum above.
- Wet-bulb design percentiles (0.4%/1%/2% WB with mean coincident DB — used for
  evaporative cooling / cooling-tower sizing) and degree-day totals — cheap
  additions once the base module is live, deliberately left out of the first cut to
  keep the primary results focused on what the Load Calculator actually needs first
  (cooling/heating coil sizing).

## Addendum — Extreme Annual Design Conditions / n-year return periods (12 Jul 2026)

Adds the ASHRAE HOF Ch.14 **Extreme Annual Design Conditions** block: the n-year
return-period values of extreme dry-bulb and wet-bulb temperature (both the hot and
cold ends), for return periods **n = 5, 10, 20 and 50 years**. Requested because
most design tools offer a 5/10/20/50-year maximum, not just the single absolute
record extreme the first cut showed. On screen this **replaces** the old "Absolute
Max / Min" column (the single record extreme + its timestamp is retained, but moved
into the "Extended data" disclosure and the PDF, rather than occupying a main
column).

### Method (ASHRAE HOF Ch.14, extreme-annual / Gumbel)

1. For each qualifying calendar year (same ≥95%-completeness rule as the percentile
   method above), take that year's **annual extreme**: the maximum and minimum
   dry-bulb, and the maximum and minimum wet-bulb.
2. Across the qualifying years, compute the **mean** and **sample standard
   deviation** (n−1) of each of those four annual-extreme series.
3. The n-year return-period value is a Gumbel (Type-I extreme value) estimate:

       F(n) = -(sqrt(6)/pi) * (0.5772 + ln(ln(n / (n - 1))))
       n-year maximum = mean_max + std_max * F(n)
       n-year minimum = mean_min - std_min * F(n)

   where 0.5772 is the Euler–Mascheroni constant. This is the published ASHRAE
   extreme-annual reduction. Verified numerically against a real ASHRAE table:
   mean/SD of 30.5/2.8 °C gives 32.6 / 34.2 / 35.8 / 37.9 °C at n = 5/10/20/50;
   a min mean/SD of −5.7/1.9 gives −7.1 / −8.2 / −9.3 / −10.7 °C — both match the
   published values to rounding.

### Where each piece lives

- **Engine (`hvac_engine.climate`, pure):** `EXTREME_RETURN_PERIODS`,
  `gumbel_return_value(mean, std, n, tail)`, `extreme_series(per_year_max,
  per_year_min, periods)` → `ExtremeSeries` (mean/SD each end + the n-year dicts),
  and `ExtremeAnnual` (the DB + WB pair). `qualifying_years()` is now public so the
  web layer can reuse the exact same year-selection rule. No psychrometrics in the
  engine — it only ever sees plain per-year number lists.
- **Web layer (`weather_client.py`):** builds the per-year DB extremes directly
  from the hourly dry-bulb series, and the per-year **WB** extremes by ranking each
  year's hours by moist-air **enthalpy** (closed-form, one saturation-pressure eval
  per hour — cheap) and solving the true iterative wet-bulb only at the handful of
  top/bottom-enthalpy candidate hours per year. Thermodynamic wet-bulb is
  single-valued in enthalpy at fixed pressure, so the max/min-enthalpy hour *is* the
  max/min-wet-bulb hour — this is an exact shortcut against our own psychrometric
  model, not an approximation, and it avoids a full iterative wet-bulb solve over
  every hour of every year (which would be ~10⁵–10⁶ solves for a 20-year pull).

### Presentation

- The third column becomes **"Return Period Extremes"** with a small return-period
  selector (5 / 10 / 20 / 50, default 50 — the most conservative, matching the page's
  existing "most extreme shown by default" convention for the percentile tier). For
  the selected n it shows the max DB, max WB, min DB and min WB.
- **DB and WB return-period values are independent extremes, not a coincident
  psychrometric state** (unlike the Summer/Winter percentile columns, which pair a
  design DB with its *mean coincident* WB). So this column shows the bare
  temperatures only — no derived RH/dew-point/moisture-ratio, which would falsely
  imply the max DB and max WB occur together. Copy-to-slot on this column therefore
  copies the dry-bulb alone (a DB-only slot).
- Mean and sample SD of each annual-extreme series are shown in the "Extended data"
  disclosure (the ASHRAE table's Mean/Std-dev columns) so the method is transparent.

### Not included (deliberately)

- **Extreme annual wind speed** (the 1%/2.5%/5% WS column in the ASHRAE block): the
  archive fetch currently pulls temperature + dew point only. Adding WS is a small
  extension (one more `hourly=` variable + its own percentile calc) but is out of
  scope for this pass, which is about temperature return periods.

## Addendum — ERA5-Land model + manual entry (12 Jul 2026)

Two changes prompted by the honest accuracy question: reanalysis reads *lower* than
an ASHRAE/CIBSE station value because a grid cell is an area average and damps
extremes — a professional could rightly challenge it for formal design.

- **Model pinned to ERA5-Land where available.** The archive fetch now passes
  `models=era5_seamless` (weather_client `ARCHIVE_MODEL`), which uses ERA5-Land
  (~9 km grid) on land and falls back to base ERA5 (~31 km) elsewhere (offshore
  points). Finer grid = less-smoothed surface temperature, narrowing but **not
  closing** the reanalysis-vs-station gap. The residual gap is fundamental (grid
  average vs point station), which is what manual entry is for. The on-page
  note-banner now names ERA5-Land, states the values run low, and points at the
  Manual Entry tab.
- **Manual entry mode.** A `?mode=` tab strip toggles between the ERA5-Land site
  lookup and a **Manual Entry** form where the engineer types authoritative
  Summer/Winter design DB + WB straight off an ASHRAE or CIBSE table (plus an
  optional site elevation for pressure and a free-text source label). Values are
  entered in the active unit system; the blueprint (`_parse_manual`) converts to
  SI and `weather_client.manual_design_states` derives the full psychrometric
  state (RH/dew point/moisture) at the altitude-derived pressure — the tool does
  the psychrometric arithmetic, the numbers are the user's. Renders through the
  same `state_table`/`copy_form` components (so copy-to-slot works) and gets its
  own PDF (`report()` branches on `mode=manual`, no map). Winter WB is optional
  (DB-only shows a dry-bulb with dashed humidity). Everything is GET, so a
  manual set is a shareable URL like the rest of the app.
- **Why manual matters commercially:** licensing ASHRAE/CIBSE data to *embed* is
  a cost (ASHRAE offers a one-time ~US$2,000 Software Developer license for the
  RP-1923 station data; CIBSE is bespoke/quote-based). Manual entry lets a user
  bring authoritative figures into the tool with zero licensing exposure for the
  app — the launch-stage answer until revenue justifies a data licence.
- **Still out of scope:** auto-ingesting ASHRAE/CIBSE tables, wind speed, and any
  bias-correction offset on the reanalysis (deliberately avoided — hard to justify
  rigorously; manual entry is the honest route to authoritative numbers).
