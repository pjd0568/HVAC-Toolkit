"""Open-Meteo I/O boundary for weather / climatic design-condition lookups.

Everything that talks to the network lives here, not in hvac_engine -- the engine
stays pure and dependency-free (see SPEC-weather-climate-data.md, and the same
"engine stays pure, I/O happens at the web boundary" split already used for units
and altitude-derived pressure). This module:

    - geocodes a free-text search into candidate locations, including elevation
      (Open-Meteo's geocoder returns it; that's *why* it was chosen over Photon --
      see the spec) -- elevation feeds the site pressure used below
    - fetches historical hourly dry-bulb/dew-point data for a coordinate
    - builds a hvac_engine.climate.HourlyRecord and calls
      hvac_engine.climate.design_conditions(), supplying a wet-bulb function backed
      by the existing psychrometrics engine (state(t_db, tdp=..., p=...).t_wb) --
      this module is a *consumer* of hvac_engine.psychrometrics, not a duplicate of
      its maths.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import date

import requests

from hvac_engine import psychrometrics as psy
from hvac_engine.climate import (
    EXTREME_RETURN_PERIODS,
    DesignConditions,
    ExtremeAnnual,
    HourlyRecord,
    design_conditions,
    extreme_series,
    qualifying_years,
)
from hvac_engine.psychrometrics import PsychroState

# How many top / bottom candidate hours (by moist-air enthalpy) to solve the true
# iterative wet-bulb for, per year, when finding that year's extreme wet-bulb.
# Thermodynamic wet-bulb is single-valued in enthalpy at fixed pressure, so the
# max/min-enthalpy hour IS the max/min-wet-bulb hour -- one candidate is exact in
# principle; a small margin guards against the dew-point clamp (below) nudging the
# ordering at the very edge. Cheap: enthalpy itself is closed-form per hour, only
# these few candidates get the iterative wet-bulb solve.
_WB_CANDIDATES_PER_YEAR = 10

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"

GEOCODE_TIMEOUT_S = 10
ARCHIVE_TIMEOUT_S = 30       # a 20-year hourly pull is a few MB of JSON

# Reanalysis model for the archive fetch. "era5_seamless" uses ERA5-Land (~9 km
# grid) wherever it's available and falls back to base ERA5 (~31 km) elsewhere
# (e.g. offshore points ERA5-Land doesn't cover) -- so we always get the highest-
# resolution surface temperature available for a coordinate without any null
# handling of our own. The finer grid smooths the extremes less than base ERA5,
# narrowing (but not closing) the well-known reanalysis "damped extremes" gap
# vs. an ASHRAE/CIBSE station value -- see the spec's clean-room/accuracy note.
# The residual gap is fundamental to reanalysis (grid-cell area average vs a point
# station), which is what the manual-override entry is for.
ARCHIVE_MODEL = "era5_seamless"


class WeatherLookupError(RuntimeError):
    """The geocoding or historical-weather API couldn't be reached, or didn't
    return usable data. Surfaced as a clear on-page error -- never silently
    swallowed, since for this route the data *is* the point of the request (same
    reasoning as the standalone chart PNG export route in blueprints/psychro.py).
    """


@dataclass(frozen=True)
class GeoResult:
    name: str
    admin1: str
    country: str
    lat: float
    lon: float
    elevation_m: float

    @property
    def label(self) -> str:
        parts = [p for p in (self.name, self.admin1, self.country) if p]
        return ", ".join(dict.fromkeys(parts))  # de-dupe e.g. admin1 == country


def geocode_search(query: str, count: int = 8) -> list[GeoResult]:
    """Free-text location search. Returns [] for a blank/too-short query instead
    of hitting the API with nothing useful (the search box calls this on every
    keystroke)."""
    query = query.strip()
    if len(query) < 2:
        return []
    try:
        resp = requests.get(
            GEOCODE_URL,
            params={"name": query, "count": count, "language": "en", "format": "json"},
            timeout=GEOCODE_TIMEOUT_S,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise WeatherLookupError(f"location search failed: {exc}") from exc

    out = []
    for r in (resp.json().get("results") or []):
        try:
            out.append(GeoResult(
                name=r.get("name", ""),
                admin1=r.get("admin1", ""),
                country=r.get("country", ""),
                lat=float(r["latitude"]),
                lon=float(r["longitude"]),
                elevation_m=float(r.get("elevation", 0.0)),
            ))
        except (KeyError, TypeError, ValueError):
            continue  # skip a malformed candidate rather than fail the whole search
    return out


def fetch_elevation(lat: float, lon: float) -> float:
    """Site elevation for a raw map click (no geocoder result to hand elevation
    from). Open-Meteo's Elevation API is the same free/keyless family as the
    other two calls in this module -- one provider for the whole lookup."""
    try:
        resp = requests.get(
            ELEVATION_URL, params={"latitude": lat, "longitude": lon},
            timeout=GEOCODE_TIMEOUT_S,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise WeatherLookupError(f"elevation lookup failed: {exc}") from exc
    values = resp.json().get("elevation") or []
    if not values:
        raise WeatherLookupError("elevation lookup returned no data for this point")
    return float(values[0])


def _year_range(years: int) -> tuple[int, int]:
    """(start_year, end_year) for the last `years` complete local calendar years
    -- the current, still-in-progress year is never included."""
    end_year = date.today().year - 1
    return end_year - years + 1, end_year


def _fetch_hourly_json(lat: float, lon: float, start_year: int, end_year: int) -> dict:
    try:
        resp = requests.get(
            ARCHIVE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": f"{start_year}-01-01",
                "end_date": f"{end_year}-12-31",
                "hourly": "temperature_2m,dew_point_2m",
                "models": ARCHIVE_MODEL,
                "timezone": "auto",
            },
            timeout=ARCHIVE_TIMEOUT_S,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise WeatherLookupError(f"historical weather fetch failed: {exc}") from exc
    return resp.json()


def _build_hourly_record(payload: dict) -> HourlyRecord:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    t_db = hourly.get("temperature_2m") or []
    t_dp = hourly.get("dew_point_2m") or []
    if not times or len(times) != len(t_db) or len(times) != len(t_dp):
        raise WeatherLookupError("historical weather response was missing or malformed")
    years = [int(t[:4]) for t in times]
    return HourlyRecord(year=years, t_db=list(t_db), t_dp=list(t_dp), timestamp=list(times))


@dataclass(frozen=True)
class WeatherResult:
    """Everything the web layer needs to render the Summer/Winter/Max-Min
    columns: the raw percentile calculation (climate.py) plus every design
    point already resolved to a full psychrometric state (DB/WB/RH/DP/W), so
    blueprints/templates never have to call hvac_engine.psychrometrics
    directly -- this module stays the one place that happens, same as it
    already is for the cooling MCWB wet-bulb figures.

    `cooling_states`/`heating_states` are keyed the same as
    `dc.cooling`/`dc.heating` ("0.4"/"1.0"/"2.0" and "99.6"/"99"/"98").
    `max_state`/`min_state` are ``None`` only in the rare case the record
    extreme hour itself has no dew-point reading to resolve humidity from --
    the dry-bulb value is still available via `dc.extreme_max_db` regardless.
    """

    dc: DesignConditions
    cooling_states: dict[str, PsychroState | None]
    heating_states: dict[str, PsychroState | None]
    max_state: PsychroState | None
    min_state: PsychroState | None
    pressure: float  # site design pressure, kPa (altitude-derived)
    extreme_annual: ExtremeAnnual | None  # None if too few qualifying years (see below)


@dataclass(frozen=True)
class HourReading:
    """One hour's resolved psychrometric state for the "On This Day" lookup.
    `state` is None if that hour's temperature/dew-point was missing or
    otherwise unusable -- kept in the list (rather than dropped) so every
    hour of the day still gets a row in the table, just shown as a gap."""

    hour: int  # 0-23, local time
    state: PsychroState | None


def _resolve_state(
    t_db: float, *, twb: float | None = None, tdp: float | None = None, p: float
) -> PsychroState | None:
    """A design point's dry-bulb plus a coincident wet-bulb or dew point ->
    full state, or None if the pair can't be resolved (e.g. reanalysis
    rounding put the coincident value a hair on the wrong side of dry-bulb
    even after clamping, or some other edge case) -- never raises, since a
    single unresolvable design point shouldn't take down the whole page."""
    try:
        if twb is not None:
            return psy.state(t_db, twb=min(twb, t_db), p=p)
        if tdp is not None:
            return psy.state(t_db, tdp=min(tdp, t_db), p=p)
    except ValueError:
        return None
    return None


def _hour_enthalpy(t_db: float, t_dp: float, pressure: float) -> float | None:
    """Moist-air enthalpy (kJ/kg dry air) for one hour, from dry-bulb + dew point.

    All closed-form (saturation pressure -> humidity ratio -> enthalpy), so this
    is cheap enough to evaluate for every hour of a multi-year series -- unlike
    the iterative wet-bulb solve, which we then run only on the enthalpy-ranked
    candidate hours. Returns None if the pair can't be resolved (out-of-range or
    physically inconsistent), so a bad hour is simply skipped."""
    try:
        p_w = psy.saturation_pressure(min(t_dp, t_db))
        w = psy.humidity_ratio_from_vapour_pressure(p_w, pressure)
        return psy.enthalpy(t_db, w)
    except ValueError:
        return None


def _wet_bulb_at(t_db: float, t_dp: float, pressure: float) -> float | None:
    """True (iterative) thermodynamic wet-bulb for one hour, or None if it can't
    be resolved. Same dew-point clamp as the design-hour wet-bulb function."""
    try:
        return psy.state(t_db, tdp=min(t_dp, t_db), p=pressure).t_wb
    except ValueError:
        return None


def _year_wet_bulb_extremes(
    record: HourlyRecord, idxs: list[int], pressure: float
) -> tuple[float, float] | None:
    """One year's (max_wb, min_wb), found by ranking its hours on enthalpy and
    solving the true wet-bulb only for the top/bottom candidates. Returns None if
    the year has no hour whose wet-bulb can be resolved at all."""
    scored: list[tuple[float, int]] = []
    for i in idxs:
        t_db, t_dp = record.t_db[i], record.t_dp[i]
        if t_db is None or t_dp is None:
            continue
        h = _hour_enthalpy(t_db, t_dp, pressure)
        if h is not None:
            scored.append((h, i))
    if not scored:
        return None

    def _resolved(cands: list[tuple[float, int]]) -> list[float]:
        out = []
        for _h, i in cands:
            wb = _wet_bulb_at(record.t_db[i], record.t_dp[i], pressure)
            if wb is not None:
                out.append(wb)
        return out

    hottest = _resolved(heapq.nlargest(_WB_CANDIDATES_PER_YEAR, scored))
    coldest = _resolved(heapq.nsmallest(_WB_CANDIDATES_PER_YEAR, scored))
    if not hottest or not coldest:
        return None
    return max(hottest), min(coldest)


def _extreme_annual(record: HourlyRecord, pressure: float) -> ExtremeAnnual | None:
    """Assemble the ASHRAE HOF Ch.14 extreme-annual DB + WB return-period block.

    Uses hvac_engine.climate.qualifying_years so the year set is identical to the
    percentile method's, then hands the pure engine plain per-year number lists
    (extreme_series does the mean/SD + Gumbel maths). Returns None if fewer than
    two qualifying years exist for either variable -- a standard deviation needs
    at least two years -- in which case the tool simply omits the block."""
    qualifying, _rejected = qualifying_years(record)
    if len(qualifying) < 2:
        return None
    years = sorted(qualifying)

    db_max = [max(record.t_db[i] for i in qualifying[y]) for y in years]
    db_min = [min(record.t_db[i] for i in qualifying[y]) for y in years]

    wb_max: list[float] = []
    wb_min: list[float] = []
    for y in years:
        pair = _year_wet_bulb_extremes(record, qualifying[y], pressure)
        if pair is not None:
            wb_max.append(pair[0])
            wb_min.append(pair[1])
    if len(wb_max) < 2:
        return None  # not enough years with usable humidity data for a WB series

    return ExtremeAnnual(
        db=extreme_series(db_max, db_min, EXTREME_RETURN_PERIODS),
        wb=extreme_series(wb_max, wb_min, EXTREME_RETURN_PERIODS),
        periods=EXTREME_RETURN_PERIODS,
        n_years=len(years),
    )


def fetch_design_conditions(
    lat: float, lon: float, elevation_m: float, years: int = 20
) -> WeatherResult:
    """The end-to-end lookup: fetch history, derive design conditions, and
    resolve every design point to a full psychrometric state.

    `elevation_m` (from geocode_search) derives the design barometric pressure via
    hvac_engine.psychrometrics.pressure_from_altitude -- the same standard-
    atmosphere pressure every psychrometric tool already uses, so the wet-bulb
    figures here are consistent with the rest of the app rather than a second,
    disconnected pressure assumption.
    """
    start_year, end_year = _year_range(years)
    payload = _fetch_hourly_json(lat, lon, start_year, end_year)
    record = _build_hourly_record(payload)
    pressure = psy.pressure_from_altitude(elevation_m)

    def wet_bulb_fn(i: int) -> float | None:
        t_db = record.t_db[i]
        t_dp = record.t_dp[i]
        if t_db is None or t_dp is None:
            return None
        try:
            # Occasional reanalysis rounding can put dew point a hair above dry
            # bulb (physically impossible); clamp rather than let it raise.
            return psy.state(t_db, tdp=min(t_dp, t_db), p=pressure).t_wb
        except ValueError:
            return None  # skip this one hour rather than fail the whole lookup

    dc = design_conditions(record, wet_bulb_fn, years_requested=years)

    cooling_states = {
        label: _resolve_state(pt.db, twb=pt.mcwb, p=pressure) for label, pt in dc.cooling.items()
    }
    heating_states = {
        label: _resolve_state(pt.db, twb=pt.mcwb, p=pressure) for label, pt in dc.heating.items()
    }
    max_state = (
        _resolve_state(dc.extreme_max_db, tdp=dc.extreme_max_db_dp, p=pressure)
        if dc.extreme_max_db_dp is not None else None
    )
    min_state = (
        _resolve_state(dc.extreme_min_db, tdp=dc.extreme_min_db_dp, p=pressure)
        if dc.extreme_min_db_dp is not None else None
    )

    return WeatherResult(
        dc=dc,
        cooling_states=cooling_states,
        heating_states=heating_states,
        max_state=max_state,
        min_state=min_state,
        pressure=pressure,
        extreme_annual=_extreme_annual(record, pressure),
    )


@dataclass(frozen=True)
class ManualConditions:
    """Design conditions the engineer typed in by hand (e.g. straight off an ASHRAE
    or CIBSE table), instead of derived from the ERA5 lookup. `summer`/`winter` are
    full PsychroStates resolved from the entered DB + WB at the site pressure, or
    None if that end wasn't fully entered (e.g. a winter DB with no wet-bulb) --
    in which case the caller still shows the raw dry-bulb via summer_db/winter_db.
    `pressure` is the altitude-derived design pressure used for the humidity
    derivations, same standard-atmosphere basis as every other tool."""

    pressure: float
    summer: PsychroState | None
    winter: PsychroState | None
    summer_db: float | None
    winter_db: float | None


def manual_design_states(
    elevation_m: float | None,
    summer_db: float | None,
    summer_wb: float | None,
    winter_db: float | None,
    winter_wb: float | None,
) -> ManualConditions:
    """Resolve user-entered Summer/Winter design DB+WB (all SI degC) into full
    psychrometric states. No network -- this is a pure consumer of
    hvac_engine.psychrometrics, same as the ERA5 path's design-point resolution.
    Wet-bulb is clamped to <= dry-bulb (a value a hair over from rounding would
    otherwise raise) via _resolve_state, which never raises -> an unresolvable
    pair simply yields None for that end rather than failing the page."""
    pressure = psy.pressure_from_altitude(elevation_m or 0.0)

    def _st(db: float | None, wb: float | None) -> PsychroState | None:
        if db is None or wb is None:
            return None
        return _resolve_state(db, twb=wb, p=pressure)

    return ManualConditions(
        pressure=pressure,
        summer=_st(summer_db, summer_wb),
        winter=_st(winter_db, winter_wb),
        summer_db=summer_db,
        winter_db=winter_db,
    )


def _fetch_single_day_json(lat: float, lon: float, on_date: date) -> dict:
    date_str = on_date.isoformat()
    try:
        resp = requests.get(
            ARCHIVE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": date_str,
                "end_date": date_str,
                "hourly": "temperature_2m,dew_point_2m",
                "models": ARCHIVE_MODEL,
                "timezone": "auto",
            },
            timeout=GEOCODE_TIMEOUT_S,  # a single day is a tiny payload
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise WeatherLookupError(f"historical weather fetch failed: {exc}") from exc
    return resp.json()


def fetch_hourly_for_date(
    lat: float, lon: float, elevation_m: float, on_date: date
) -> list[HourReading]:
    """The 24 (23/25 on a DST-transition day) hourly readings for one specific
    calendar date at this site -- the "On This Day" section. Deliberately
    independent of fetch_design_conditions: a single-day archive pull is a
    tiny payload, so picking a date never re-runs the multi-year percentile
    fetch that backs the Summer/Winter/Max-Min columns above it."""
    payload = _fetch_single_day_json(lat, lon, on_date)
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    t_db_list = hourly.get("temperature_2m") or []
    t_dp_list = hourly.get("dew_point_2m") or []
    if not times:
        raise WeatherLookupError("no hourly data returned for this date")
    pressure = psy.pressure_from_altitude(elevation_m)

    readings: list[HourReading] = []
    for i, t in enumerate(times):
        try:
            hour = int(t[11:13])
        except (ValueError, IndexError):
            hour = i
        t_db = t_db_list[i] if i < len(t_db_list) else None
        t_dp = t_dp_list[i] if i < len(t_dp_list) else None
        state = _resolve_state(t_db, tdp=t_dp, p=pressure) if t_db is not None and t_dp is not None else None
        readings.append(HourReading(hour=hour, state=state))
    return readings


__all__ = [
    "WeatherLookupError",
    "GeoResult",
    "WeatherResult",
    "HourReading",
    "ManualConditions",
    "geocode_search",
    "fetch_elevation",
    "fetch_design_conditions",
    "fetch_hourly_for_date",
    "manual_design_states",
]
