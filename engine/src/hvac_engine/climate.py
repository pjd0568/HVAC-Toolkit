"""Climatic design conditions -- ASHRAE HOF Ch.14 percentile method.

Implemented from SPEC-weather-climate-data.md. Pure calculation only: this module
never makes a network call and has zero third-party dependencies, exactly like the
rest of hvac_engine. It operates on hourly dry-bulb/dew-point series the *caller*
has already fetched and parsed (see web/app/weather_client.py for the Open-Meteo
client that supplies a HourlyRecord) -- the same "engine stays pure, I/O happens at
the web boundary" split used for units and altitude-derived pressure.

Method summary (see the spec for the full rationale):
    - A design percentile (e.g. the "0.4% cooling" condition) is computed *per local
      calendar year* -- the value at that percentile of just that year's hours -- and
      then averaged across all qualifying years. This is the actual ASHRAE method: it
      is not the same as sorting one long pooled multi-year series.
    - All hours of the year are used; there is no seasonal pre-filter.
    - Years with too much missing data are excluded rather than allowed to skew the
      average.
    - Mean coincident wet-bulb is computed from the hours identified by the dry-bulb
      threshold in each year, using wet-bulb values the caller supplies per hour
      (see wet_bulb_fn below) -- this module never touches psychrometrics directly,
      the web layer wires that up using hvac_engine.psychrometrics.state(tdp=...).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Literal

# Annual cumulative frequency of occurrence, per ASHRAE HOF Ch.14. Labels are the
# conventional design-condition names; values are the tail fraction of hours.
COOLING_FRACTIONS: dict[str, float] = {"0.4": 0.004, "1.0": 0.01, "2.0": 0.02}
HEATING_FRACTIONS: dict[str, float] = {"99.6": 0.004, "99": 0.01, "98": 0.02}

# A calendar year needs at least this fraction of its hours present to be used.
MIN_YEAR_COMPLETENESS = 0.95

# Return periods (years) for the ASHRAE HOF Ch.14 "Extreme Annual Design
# Conditions" block -- the n-year return-period values of extreme dry-bulb /
# wet-bulb temperature. The conventional published set.
EXTREME_RETURN_PERIODS: tuple[int, ...] = (5, 10, 20, 50)

# Euler-Mascheroni constant, used in the Gumbel (Type-I extreme value) reduction.
_EULER_MASCHERONI = 0.5772156649


@dataclass(frozen=True)
class HourlyRecord:
    """One flat hourly series, local time, spanning one or more calendar years.

    `year[i]` / `t_db[i]` / `t_dp[i]` / `timestamp[i]` all describe hour `i`.
    Missing hours are `None` in t_db/t_dp (not omitted) so every list stays the
    same length. `timestamp` is an opaque, caller-defined per-hour label (the
    web layer uses the ISO datetime string Open-Meteo returns) -- this module
    never parses it, only echoes back the one belonging to a computed extreme
    so the caller can show *when* the record max/min occurred.
    """

    year: list[int]
    t_db: list[float | None]
    t_dp: list[float | None]
    timestamp: list[str]

    def __post_init__(self) -> None:
        n = len(self.year)
        if len(self.t_db) != n or len(self.t_dp) != n or len(self.timestamp) != n:
            raise ValueError("year, t_db, t_dp and timestamp must all be the same length")
        if n == 0:
            raise ValueError("HourlyRecord cannot be empty")


@dataclass(frozen=True)
class DesignPoint:
    """A design dry-bulb with its mean coincident wet-bulb.

    Used for both cooling (top-of-summer -- MCWB alongside DB is genuine,
    standard ASHRAE table content) and heating (bottom-of-winter -- ASHRAE
    heating tables don't traditionally carry a coincident wet-bulb column,
    since winter latent load usually isn't the governing design case, but one
    is computed here the same way so every design point this module produces
    resolves to a full psychrometric state via
    hvac_engine.psychrometrics.state(t_db, twb=...), not dry-bulb alone).
    """

    db: float
    mcwb: float


@dataclass(frozen=True)
class DesignConditions:
    years_requested: int
    years_used: int
    rejected_years: list[int]
    cooling: dict[str, DesignPoint]       # keys: "0.4", "1.0", "2.0"
    heating: dict[str, DesignPoint]       # keys: "99.6", "99", "98"
    extreme_max_db: float
    extreme_min_db: float
    extreme_max_db_at: str                # timestamp of the extreme_max_db hour
    extreme_min_db_at: str                # timestamp of the extreme_min_db hour
    extreme_max_db_dp: float | None       # coincident dew point at that hour, if available
    extreme_min_db_dp: float | None       # coincident dew point at that hour, if available
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExtremeSeries:
    """One variable's extreme-annual statistics and n-year return-period values.

    Built from the per-year annual maxima and minima of a single quantity (e.g.
    dry-bulb). `mean_max`/`std_max` are the mean and sample standard deviation of
    the annual maxima; `mean_min`/`std_min` the same for the annual minima.
    `return_max`/`return_min` map each return period n -> the n-year return-period
    value at that end of the distribution (Gumbel reduction, see
    gumbel_return_value). All temperatures in degC (this module is pure SI).
    """

    mean_max: float
    std_max: float
    mean_min: float
    std_min: float
    return_max: dict[int, float]
    return_min: dict[int, float]


@dataclass(frozen=True)
class ExtremeAnnual:
    """The ASHRAE HOF Ch.14 "Extreme Annual Design Conditions" temperature block:
    the extreme-annual dry-bulb and wet-bulb series, and the return periods used.

    `n_years` is how many qualifying calendar years the statistics were computed
    from -- the sample size behind the mean/SD, distinct from the return periods.
    Note the DB and WB extremes are *independent* extremes (the year's hottest
    hour and its most-humid hour are generally different hours), so a max-DB and a
    max-WB return-period value do not describe one coincident psychrometric state.
    """

    db: ExtremeSeries
    wb: ExtremeSeries
    periods: tuple[int, ...]
    n_years: int


def _year_index_map(years: list[int]) -> dict[int, list[int]]:
    """hour index positions grouped by calendar year, in original order."""
    out: dict[int, list[int]] = {}
    for i, y in enumerate(years):
        out.setdefault(y, []).append(i)
    return out


def _qualifying_years(
    record: HourlyRecord, min_completeness: float = MIN_YEAR_COMPLETENESS
) -> tuple[dict[int, list[int]], list[int]]:
    """Split years into (qualifying -> valid-hour indices, rejected years).

    A year qualifies if at least `min_completeness` of its hours have a dry-bulb
    reading. Rejected years are excluded entirely rather than allowed to skew the
    per-year-then-average calculation with a partial year.
    """
    by_year = _year_index_map(record.year)
    qualifying: dict[int, list[int]] = {}
    rejected: list[int] = []
    for y, idxs in by_year.items():
        valid = [i for i in idxs if record.t_db[i] is not None]
        completeness = len(valid) / len(idxs) if idxs else 0.0
        if completeness >= min_completeness:
            qualifying[y] = valid
        else:
            rejected.append(y)
    return qualifying, sorted(rejected)


def qualifying_years(
    record: HourlyRecord, min_completeness: float = MIN_YEAR_COMPLETENESS
) -> tuple[dict[int, list[int]], list[int]]:
    """Public wrapper over the year-selection rule (see _qualifying_years).

    Exposed so the web layer can build the extreme-annual DB/WB series over
    exactly the same set of qualifying years the percentile method uses, rather
    than duplicating (and risking drift from) the ≥95%-completeness rule.
    """
    return _qualifying_years(record, min_completeness)


def _tail_value(values: list[float], fraction: float, tail: str) -> float:
    """The value at a tail fraction of one year's hours.

    e.g. fraction=0.004 ("0.4%") on 8760 hours is the 35th-hottest hour of that
    year (tail="high") or the 35th-coldest (tail="low") -- the textbook description
    of an ASHRAE annual design-condition percentile (8760 x 0.004 = 35.04).
    """
    n = len(values)
    if n == 0:
        raise ValueError("no values to compute a percentile from")
    ordered = sorted(values)
    k = max(1, min(n, round(fraction * n)))
    if tail == "high":
        return ordered[n - k]
    if tail == "low":
        return ordered[k - 1]
    raise ValueError(f"tail must be 'high' or 'low', got {tail!r}")


def annual_percentile(
    values_by_year: dict[int, list[float]], fraction: float, tail: Literal["high", "low"]
) -> dict[int, float]:
    """Per-year tail-fraction threshold value, one entry per input year."""
    return {y: _tail_value(v, fraction, tail) for y, v in values_by_year.items()}


def _design_point_for_tail(
    label: str,
    frac: float,
    tail: Literal["high", "low"],
    db_by_year: dict[int, list[float]],
    qualifying: dict[int, list[int]],
    record: HourlyRecord,
    wet_bulb_fn: Callable[[int], float | None],
    warnings: list[str],
    tail_name: str,
) -> DesignPoint:
    """Shared per-year-then-average logic for both cooling (tail="high") and
    heating (tail="low"): find each year's dry-bulb threshold, average those
    for the design DB, then average the coincident wet-bulb at the identified
    hours for the MCWB. Identical maths either side of the distribution --
    only which tail of each year's hours counts as "identified" changes.
    """
    per_year_db = annual_percentile(db_by_year, frac, tail)
    mcwb_years: list[float] = []
    skipped_years: list[int] = []
    for y, idxs in qualifying.items():
        threshold = per_year_db[y]
        if tail == "high":
            sel_idxs = [i for i in idxs if record.t_db[i] >= threshold]
        else:
            sel_idxs = [i for i in idxs if record.t_db[i] <= threshold]
        wbs = [wb for wb in (wet_bulb_fn(i) for i in sel_idxs) if wb is not None]
        if wbs:
            mcwb_years.append(sum(wbs) / len(wbs))
        else:
            skipped_years.append(y)
    if not mcwb_years:
        raise ValueError(
            f"could not compute mean coincident wet-bulb for the {label}% {tail_name} "
            "design condition -- no dew-point data at any identified design hour"
        )
    if skipped_years:
        warnings.append(
            f"{label}% {tail_name} MCWB skipped {len(skipped_years)} year(s) with no "
            "dew-point data at the design hours: "
            + ", ".join(str(y) for y in skipped_years)
        )
    return DesignPoint(
        db=sum(per_year_db.values()) / len(per_year_db),
        mcwb=sum(mcwb_years) / len(mcwb_years),
    )


def design_conditions(
    record: HourlyRecord,
    wet_bulb_fn: Callable[[int], float | None],
    years_requested: int | None = None,
) -> DesignConditions:
    """Compute cooling/heating design conditions from an hourly record.

    `wet_bulb_fn(hour_index)` returns the wet-bulb temperature (degC) for that
    specific hour, or None if it can't be computed (e.g. missing dew point) --
    supplied by the caller so this module never has to know about psychrometrics
    or site pressure. It is only called for the small number of hours identified
    as design-condition hours in each year (tens of hours per year, not the full
    multi-year series), so a per-hour iterative calculation there stays cheap.
    """
    qualifying, rejected = _qualifying_years(record)
    warnings: list[str] = []
    if rejected:
        warnings.append(
            f"{len(rejected)} year(s) excluded for incomplete data: "
            + ", ".join(str(y) for y in rejected)
        )
    if not qualifying:
        raise ValueError("no calendar year in the requested range had enough data to use")

    db_by_year = {y: [record.t_db[i] for i in idxs] for y, idxs in qualifying.items()}

    cooling: dict[str, DesignPoint] = {
        label: _design_point_for_tail(
            label, frac, "high", db_by_year, qualifying, record, wet_bulb_fn, warnings, "cooling"
        )
        for label, frac in COOLING_FRACTIONS.items()
    }

    heating: dict[str, DesignPoint] = {
        label: _design_point_for_tail(
            label, frac, "low", db_by_year, qualifying, record, wet_bulb_fn, warnings, "heating"
        )
        for label, frac in HEATING_FRACTIONS.items()
    }

    all_valid_idx = [i for idxs in qualifying.values() for i in idxs]
    max_idx = max(all_valid_idx, key=lambda i: record.t_db[i])
    min_idx = min(all_valid_idx, key=lambda i: record.t_db[i])

    return DesignConditions(
        years_requested=years_requested if years_requested is not None
        else len(qualifying) + len(rejected),
        years_used=len(qualifying),
        rejected_years=rejected,
        cooling=cooling,
        heating=heating,
        extreme_max_db=record.t_db[max_idx],
        extreme_min_db=record.t_db[min_idx],
        extreme_max_db_at=record.timestamp[max_idx],
        extreme_min_db_at=record.timestamp[min_idx],
        extreme_max_db_dp=record.t_dp[max_idx],
        extreme_min_db_dp=record.t_dp[min_idx],
        warnings=warnings,
    )


def _gumbel_factor(n: int) -> float:
    """The Gumbel reduction factor F(n) for an n-year return period:

        F(n) = -(sqrt(6)/pi) * (gamma + ln(ln(n/(n-1))))

    with gamma the Euler-Mascheroni constant. This is the ASHRAE HOF Ch.14
    extreme-annual form. F grows with n (a longer return period is a more
    extreme value); F(1) is undefined (ln(ln(1)) -> -inf) and rejected below.
    """
    if n < 2:
        raise ValueError("return period n must be >= 2 years")
    return -(math.sqrt(6.0) / math.pi) * (
        _EULER_MASCHERONI + math.log(math.log(n / (n - 1)))
    )


def gumbel_return_value(mean: float, std: float, n: int, tail: Literal["high", "low"]) -> float:
    """The n-year return-period extreme value from the mean and (sample) standard
    deviation of a series of annual extremes (ASHRAE HOF Ch.14):

        high (maximum): mean + std * F(n)
        low  (minimum): mean - std * F(n)

    e.g. annual-maximum dry-bulb mean 30.5 degC, SD 2.8 degC -> 32.6 / 34.2 /
    35.8 / 37.9 degC at n = 5 / 10 / 20 / 50 (matches published ASHRAE tables).
    """
    f = _gumbel_factor(n)
    if tail == "high":
        return mean + std * f
    if tail == "low":
        return mean - std * f
    raise ValueError(f"tail must be 'high' or 'low', got {tail!r}")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sample_std(values: list[float]) -> float:
    """Sample standard deviation (n-1 denominator), the ASHRAE extreme-annual
    convention. Requires at least two values."""
    n = len(values)
    if n < 2:
        raise ValueError("need at least two annual extremes for a standard deviation")
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def extreme_series(
    per_year_max: list[float],
    per_year_min: list[float],
    periods: tuple[int, ...] = EXTREME_RETURN_PERIODS,
) -> ExtremeSeries:
    """Extreme-annual statistics + n-year return-period values for one variable.

    `per_year_max`/`per_year_min` are that variable's annual maximum / minimum,
    one value per qualifying calendar year (same length, same year order). Needs
    at least two years so a sample standard deviation exists -- the caller checks
    the year count and skips the whole extreme-annual block if too few.
    """
    if len(per_year_max) != len(per_year_min):
        raise ValueError("per_year_max and per_year_min must be the same length")
    mean_max, std_max = _mean(per_year_max), _sample_std(per_year_max)
    mean_min, std_min = _mean(per_year_min), _sample_std(per_year_min)
    return ExtremeSeries(
        mean_max=mean_max,
        std_max=std_max,
        mean_min=mean_min,
        std_min=std_min,
        return_max={n: gumbel_return_value(mean_max, std_max, n, "high") for n in periods},
        return_min={n: gumbel_return_value(mean_min, std_min, n, "low") for n in periods},
    )


__all__ = [
    "COOLING_FRACTIONS",
    "HEATING_FRACTIONS",
    "MIN_YEAR_COMPLETENESS",
    "EXTREME_RETURN_PERIODS",
    "HourlyRecord",
    "DesignPoint",
    "DesignConditions",
    "ExtremeSeries",
    "ExtremeAnnual",
    "annual_percentile",
    "qualifying_years",
    "gumbel_return_value",
    "extreme_series",
    "design_conditions",
]
