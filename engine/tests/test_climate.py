import math

import pytest

from hvac_engine.climate import (
    EXTREME_RETURN_PERIODS,
    DesignPoint,
    ExtremeSeries,
    HourlyRecord,
    annual_percentile,
    design_conditions,
    extreme_series,
    gumbel_return_value,
    qualifying_years,
)


def test_annual_percentile_single_year_high_and_low_tail():
    # 1..1000: the textbook "k-th hottest/coldest hour" definition.
    values_by_year = {2020: list(range(1, 1001))}

    high = annual_percentile(values_by_year, fraction=0.01, tail="high")
    assert high[2020] == 991  # 1% of 1000 = 10th hottest -> value 991

    low = annual_percentile(values_by_year, fraction=0.01, tail="low")
    assert low[2020] == 10  # 10th coldest -> value 10


def test_annual_percentile_averages_across_years_independently():
    # Year B is Year A shifted +100. Each year's threshold is found on its own
    # series (not a pooled sort of both years together), then the two results
    # are averaged -- this is the behaviour that distinguishes the ASHRAE
    # per-year-then-average method from a single pooled percentile.
    values_by_year = {
        2019: list(range(1, 1001)),
        2020: list(range(101, 1101)),
    }
    result = annual_percentile(values_by_year, fraction=0.01, tail="high")
    assert result[2019] == 991
    assert result[2020] == 1091
    assert (result[2019] + result[2020]) / 2 == 1041


def test_tail_value_rejects_bad_tail_argument():
    with pytest.raises(ValueError):
        annual_percentile({2020: [1, 2, 3]}, fraction=0.1, tail="sideways")


def _flat_record(years_hours: dict[int, list[float | None]]) -> HourlyRecord:
    year, t_db, timestamp = [], [], []
    for y, hours in years_hours.items():
        year.extend([y] * len(hours))
        t_db.extend(hours)
        timestamp.extend(f"{y}-h{i}" for i in range(len(hours)))  # opaque test label
    t_dp = [None] * len(t_db)  # unused by these tests -- wet_bulb_fn is stubbed
    return HourlyRecord(year=year, t_db=t_db, t_dp=t_dp, timestamp=timestamp)


def test_design_conditions_cooling_and_heating_percentiles():
    record = _flat_record({
        2019: [float(v) for v in range(1, 1001)],
        2020: [float(v) for v in range(101, 1101)],
    })

    # Fake wet-bulb: db - 5. Lets the test check the MCWB averaging logic
    # without depending on hvac_engine.psychrometrics at all.
    def wet_bulb_fn(i: int) -> float:
        return record.t_db[i] - 5.0

    dc = design_conditions(record, wet_bulb_fn)

    assert dc.years_used == 2
    assert dc.rejected_years == []
    assert dc.years_requested == 2

    # 0.4% cooling: k=4 -> threshold is the 4th-hottest hour of each year.
    # 2019 top 4 = 997..1000 -> threshold 997; 2020 top 4 = 1097..1100 -> 1097.
    cp = dc.cooling["0.4"]
    assert isinstance(cp, DesignPoint)
    assert cp.db == pytest.approx((997 + 1097) / 2)
    # MCWB = average of (db-5) over each year's top-4 hours, then averaged.
    assert cp.mcwb == pytest.approx(((998.5 - 5) + (1098.5 - 5)) / 2)

    # 99.6% heating: k=4 -> 4th-coldest hour of each year.
    # 2019 bottom 4 = 1..4 -> 4; 2020 bottom 4 = 101..104 -> 104.
    hp = dc.heating["99.6"]
    assert isinstance(hp, DesignPoint)
    assert hp.db == pytest.approx((4 + 104) / 2)
    # Same MCWB averaging as cooling, just over each year's coldest 4 hours:
    # 2019 -> (1-5, 2-5, 3-5, 4-5) avg -2.5; 2020 -> (101-5..104-5) avg 97.5.
    assert hp.mcwb == pytest.approx((-2.5 + 97.5) / 2)

    assert dc.extreme_max_db == 1100.0
    assert dc.extreme_min_db == 1.0
    # 1100.0 is 2020's last hour (local index 999); 1.0 is 2019's first (index 0).
    assert dc.extreme_max_db_at == "2020-h999"
    assert dc.extreme_min_db_at == "2019-h0"
    # _flat_record doesn't carry dew point -- both should degrade to None
    # rather than error, so the web layer can gracefully omit humidity for
    # a record extreme when the source data has a gap at that exact hour.
    assert dc.extreme_max_db_dp is None
    assert dc.extreme_min_db_dp is None


def test_design_conditions_captures_coincident_dew_point_at_extremes():
    year = 2022
    db = [10.0, 20.0, 5.0, 30.0, 15.0]
    dp = [8.0, 18.0, 3.0, 25.0, 12.0]
    record = HourlyRecord(
        year=[year] * len(db),
        t_db=db,
        t_dp=dp,
        timestamp=[f"{year}-h{i}" for i in range(len(db))],
    )

    dc = design_conditions(record, lambda i: db[i] - 5.0)

    # index 3 (db=30) is the year's max; index 2 (db=5) is the min -- the
    # coincident dew point should come from those same two hours.
    assert dc.extreme_max_db == 30.0
    assert dc.extreme_max_db_dp == 25.0
    assert dc.extreme_min_db == 5.0
    assert dc.extreme_min_db_dp == 3.0


def test_design_conditions_excludes_incomplete_years():
    hours_2019 = [float(v) for v in range(1, 1001)]
    hours_2020 = [float(v) for v in range(101, 1101)]
    # 2021: only half the hours present -> below the 95% completeness bar.
    hours_2021 = [float(v) for v in range(1, 501)] + [None] * 500

    record = _flat_record({2019: hours_2019, 2020: hours_2020, 2021: hours_2021})

    def wet_bulb_fn(i: int) -> float | None:
        v = record.t_db[i]
        return None if v is None else v - 5.0

    dc = design_conditions(record, wet_bulb_fn)

    assert dc.years_used == 2
    assert dc.rejected_years == [2021]
    assert dc.years_requested == 3  # 2 qualifying + 1 rejected
    assert any("excluded" in w for w in dc.warnings)


def test_design_conditions_raises_if_no_year_qualifies():
    record = _flat_record({2021: [None] * 1000})

    with pytest.raises(ValueError):
        design_conditions(record, lambda i: 10.0)


def test_design_conditions_raises_if_wet_bulb_never_available():
    record = _flat_record({2020: [float(v) for v in range(1, 1001)]})

    with pytest.raises(ValueError):
        design_conditions(record, lambda i: None)


# --- Extreme Annual Design Conditions / n-year return periods ----------------

def test_gumbel_return_value_matches_published_ashrae_table():
    # Real ASHRAE HOF Ch.14 "Extreme Annual Design Conditions" values: an
    # annual-maximum dry-bulb mean of 30.5 degC, SD 2.8 degC, gives these
    # return-period maxima. Tables publish mean/SD pre-rounded to 1 dp, so
    # allow 0.15 degC of slack at the longer periods.
    expected = {5: 32.6, 10: 34.2, 20: 35.8, 50: 37.9}
    for n, want in expected.items():
        got = gumbel_return_value(30.5, 2.8, n, "high")
        assert abs(got - want) < 0.15, (n, got, want)


def test_gumbel_return_value_minimum_side():
    # Annual-minimum dry-bulb mean -5.7 degC, SD 1.9 degC -> the cold-end
    # return-period minima from the same published table.
    expected = {5: -7.1, 10: -8.2, 20: -9.3, 50: -10.7}
    for n, want in expected.items():
        got = gumbel_return_value(-5.7, 1.9, n, "low")
        assert abs(got - want) < 0.15, (n, got, want)


def test_gumbel_grows_with_return_period():
    # A longer return period is always a more extreme value.
    vals = [gumbel_return_value(20.0, 3.0, n, "high") for n in (5, 10, 20, 50)]
    assert vals == sorted(vals)
    mins = [gumbel_return_value(0.0, 3.0, n, "low") for n in (5, 10, 20, 50)]
    assert mins == sorted(mins, reverse=True)  # progressively colder


def test_gumbel_rejects_bad_arguments():
    with pytest.raises(ValueError):
        gumbel_return_value(20.0, 3.0, 1, "high")   # n must be >= 2
    with pytest.raises(ValueError):
        gumbel_return_value(20.0, 3.0, 5, "sideways")


def test_extreme_series_uses_sample_std_and_reproduces_table():
    # Two years of maxima {27.7, 33.3} -> mean 30.5; minima {-4.7, -6.7} ->
    # mean -5.7. Sample SD (n-1 denominator) of two points {m-d, m+d} is
    # sqrt(2)*d, so here std_max = sqrt(2)*2.8 and std_min = sqrt(2)*1.0.
    per_year_max = [27.7, 33.3]
    per_year_min = [-4.7, -6.7]
    s = extreme_series(per_year_max, per_year_min, EXTREME_RETURN_PERIODS)
    assert abs(s.mean_max - 30.5) < 1e-9
    assert abs(s.std_max - math.sqrt((27.7 - 30.5) ** 2 + (33.3 - 30.5) ** 2)) < 1e-9
    assert abs(s.mean_min - (-5.7)) < 1e-9
    assert abs(s.std_min - math.sqrt((-4.7 + 5.7) ** 2 + (-6.7 + 5.7) ** 2)) < 1e-9
    # return dicts keyed by every requested period, max > mean > min ends apart
    assert set(s.return_max) == set(EXTREME_RETURN_PERIODS)
    assert s.return_max[50] > s.return_max[5] > s.mean_max
    assert s.return_min[50] < s.return_min[5] < s.mean_min


def test_extreme_series_rejects_single_year_and_mismatched_lengths():
    with pytest.raises(ValueError):
        extreme_series([20.0], [10.0])          # one year -> no sample SD
    with pytest.raises(ValueError):
        extreme_series([20.0, 21.0], [10.0])    # mismatched lengths


def test_qualifying_years_is_public_and_matches_completeness_rule():
    # 2019/2020 complete, 2021 mostly missing -> only the first two qualify,
    # same rule design_conditions uses internally.
    record = _flat_record({
        2019: [float(v) for v in range(1000)],
        2020: [float(v) for v in range(1000)],
        2021: [None] * 990 + [1.0] * 10,
    })
    qualifying, rejected = qualifying_years(record)
    assert sorted(qualifying) == [2019, 2020]
    assert rejected == [2021]
