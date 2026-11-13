"""The climate stripes' colour scale (Nogat plan M15 prototype) on Hydrolog's annual means."""

from __future__ import annotations

import math

import pytest
from starlette.requests import Request

from obserwator.gui._http import GuiError
from obserwator.gui._stripes import (
    COLOURS,
    StripeScale,
    annual_spread,
    stripes,
    stripes_document,
)

STATION = "250190390"


def analysis(means, normal, *, reference, normal_years):
    """
    An ``obserwator-analysis/1`` of ``temperature.means`` as Hydrolog answers it.

    A year without an annual mean has 9 months with a monthly mean.
    """
    years = []
    for year, mean in means.items():
        known = 12 if mean is not None else 9
        years.append(
            {
                "year": year,
                "tmean_c": mean,
                "anomaly_c": None if mean is None or normal is None else mean - normal,
                "months": [
                    {"month": month, "tmean_c": 1.0 if month <= known else None}
                    for month in range(1, 13)
                ],
            }
        )
    return {
        "schema": "obserwator-analysis/1",
        "station": STATION,
        "analysis": "temperature.means",
        "command": "meteo temperature",
        "status": "ok",
        "hydrolog": {"version": "1.0.0"},
        "inputs": [{"dataset": "pl.imgw.meteo_climate_daily", "series_version": "v1"}],
        "attribution": ["Source: IMGW-PIB"],
        "terms_notice": ["IMGW-PIB terms"],
        "envelope": {
            "schema": "hydrolog-result/1",
            "notices": [],
            "result": {
                "first_year": min(means),
                "last_year": max(means),
                "reference_first_year": reference[0],
                "reference_last_year": reference[1],
                "years": years,
                "period": {"normal_c": normal, "normal_years": normal_years},
            },
        },
    }


def document(asked, used=None, *, spread=(1901, 2000), variant="2025"):
    return stripes_document(
        station=STATION,
        variant=variant,
        centre=(1961, 2010),
        spread=spread,
        asked=asked,
        used=asked if used is None else used,
        lang="en",
    )


# --- the scale ------------------------------------------------------------------------


def test_the_colours_span_k_standard_deviations_around_the_centre_in_16_equal_steps():
    scale = StripeScale(centre=8.0, sd=0.5, k=3.0)
    assert (scale.lo, scale.hi, scale.step) == (6.5, 9.5, 0.1875)
    edges = scale.edges()
    assert len(edges) == len(COLOURS) + 1 == 17
    assert edges[0] == 6.5 and edges[8] == 8.0 and edges[-1] == pytest.approx(9.5)
    # the centre is the boundary between the lightest blue and the lightest red
    assert scale.colour(-0.01) == 7 and COLOURS[7] == "#deebf7"
    assert scale.colour(0.0) == 8 and COLOURS[8] == "#fee0d2"
    assert scale.colour(-1.49) == 0 and scale.colour(1.49) == 15


def test_a_year_beyond_the_scale_takes_its_end_colour_and_one_without_a_mean_is_grey():
    scale = StripeScale(centre=8.0, sd=0.5, k=2.6)
    assert scale.colour(-1.3) == 0 and scale.colour(-5.0) == 0
    assert scale.colour(1.3) == 15 and scale.colour(5.0) == 15
    assert scale.colour(None) is None and scale.colour(math.nan) is None


def test_the_spread_is_the_sample_standard_deviation_of_the_period():
    years = list(range(1901, 2001))
    means = [7.5 if year % 2 else 8.5 for year in years]
    found = annual_spread(years, means, 1901, 2000)
    assert found.sd == pytest.approx(math.sqrt(25 / 99))
    assert (found.first_year, found.last_year, found.years) == (1901, 2000, 100)
    assert not found.fallback


def test_a_period_with_fewer_than_80_percent_annual_means_falls_back_to_the_record():
    years = list(range(1961, 2026))
    means: list[float | None] = [8.0 + (year - 1961) / 10 for year in years]
    # 1951–2000: 40 of 50 years (80 %) is enough
    kept = annual_spread(years, means, 1951, 2000)
    assert not kept.fallback
    assert (kept.first_year, kept.last_year, kept.years) == (1951, 2000, 40)
    # 1950–2000: 40 of 51 years (78 %); the whole record serves
    found = annual_spread(years, means, 1950, 2000)
    assert found.fallback
    assert (found.first_year, found.last_year, found.years) == (1961, 2025, 65)
    assert (found.asked_first_year, found.asked_last_year, found.asked_years) == (
        1950,
        2000,
        40,
    )
    assert found.sd == pytest.approx(
        math.sqrt(sum((n - 32) ** 2 for n in range(65)) / 64) / 10
    )
    # a year without an annual mean does not count: 1951–2000 then has 39 of 50
    means[5] = None
    assert annual_spread(years, means, 1951, 2000).fallback
    means[5] = math.nan
    assert annual_spread(years, means, 1951, 2000).years == 64


@pytest.mark.parametrize(
    ("years", "means", "period", "why"),
    [
        ([2000, 2001], [1.0], (2000, 2001), "length"),
        ([2001, 2000], [1.0, 2.0], (2000, 2001), "increase"),
        ([2000, 2000], [1.0, 2.0], (2000, 2001), "increase"),
        ([2000, 2001], [1.0, 2.0], (2001, 2000), "ends before"),
        ([2000, 2001], [1.0, None], (2000, 2001), "two annual means"),
        ([2000, 2001], [math.nan, 2.0], (2000, 2001), "two annual means"),
    ],
)
def test_the_spread_refuses_inconsistent_input(years, means, period, why):
    with pytest.raises(ValueError, match=why):
        annual_spread(years, means, *period)


@pytest.mark.parametrize(
    ("centre", "sd", "k"),
    [
        (8.0, 0.0, 3.0),
        (8.0, -0.5, 3.0),
        (8.0, 0.5, 0.0),
        (math.nan, 0.5, 3.0),
        (8.0, math.inf, 3.0),
    ],
)
def test_the_scale_refuses_a_spread_or_k_that_is_not_positive_and_finite(centre, sd, k):
    with pytest.raises(ValueError):
        StripeScale(centre=centre, sd=sd, k=k)


# --- the document on Hydrolog's result --------------------------------------------------


def test_the_centre_and_the_anomalies_are_hydrologs_and_only_the_scale_is_the_prototype():
    means = {year: 7.5 if year % 2 else 8.5 for year in range(1901, 2001)}
    means |= {2001: 9.0, 2002: None, 2003: 9.6, 2004: None}
    found = document(analysis(means, 8.0, reference=(1961, 2010), normal_years=50))
    assert found["status"] == "ok"
    scale = found["scale"]
    assert scale["centre"] | {"fallback": False} == {
        "normal_c": 8.0,
        "first_year": 1961,
        "last_year": 2010,
        "years": 50,
        "asked_first_year": 1961,
        "asked_last_year": 2010,
        "asked_years": 50,
        "fallback": False,
    }
    sd = math.sqrt(25 / 99)
    assert scale["spread"]["sd_c"] == pytest.approx(sd)
    assert (scale["lo_c"], scale["hi_c"]) == pytest.approx((8.0 - 3 * sd, 8.0 + 3 * sd))
    rows = {row["year"]: row for row in found["years"]}
    # the stripes end at the last annual mean; a year inside without one is grey
    assert (found["first_year"], found["last_year"]) == (1901, 2003)
    assert found["grey"] == [2002]
    assert rows[2002]["colour"] is None and rows[2002]["months_missing"] == 3
    assert rows[2001]["anomaly_c"] == pytest.approx(1.0)
    assert [rows[year]["colour"] for year in (1901, 1902, 2001, 2003)] == [
        5,
        10,
        13,
        15,
    ]
    assert found["palette"] == list(COLOURS)
    assert found["provenance"]["engine"] == "prototype"
    assert found["provenance"]["target"] == "M15"
    assert "result" not in found["analysis"]["envelope"]
    assert found["attribution"] == ["Source: IMGW-PIB"]
    assert found["terms_notice"] == ["IMGW-PIB terms"]


def test_without_a_normal_of_the_reference_period_the_whole_record_is_the_centre():
    means = {year: 8.0 + (year % 3) / 2 for year in range(1971, 2026)}
    asked = analysis(means, None, reference=(1961, 2010), normal_years=40)
    whole = analysis(means, 8.5, reference=(1971, 2025), normal_years=55)
    found = document(asked, whole)
    centre = found["scale"]["centre"]
    assert centre["fallback"]
    assert (centre["normal_c"], centre["first_year"], centre["last_year"]) == (
        8.5,
        1971,
        2025,
    )
    assert (centre["years"], centre["asked_years"]) == (55, 40)
    # the spread's 1901–2000 falls back too: the record starts in 1971
    spread = found["scale"]["spread"]
    assert spread["fallback"] and (spread["first_year"], spread["years"]) == (1971, 55)
    assert all(row["colour"] is not None for row in found["years"])


def test_a_failed_analysis_too_few_years_or_no_spread_give_a_failed_document():
    failed = {
        "status": "failed",
        "error": {"schema": "hydrolog-error/1", "message": "No value in the period"},
        "attribution": ["Source: IMGW-PIB"],
    }
    found = document(failed)
    assert found["status"] == "failed"
    assert found["error"]["message"] == "No value in the period"
    one = analysis({2000: 8.0, 2001: None}, 8.0, reference=(2000, 2001), normal_years=1)
    flat = analysis({2000: 8.0, 2001: 8.0}, 8.0, reference=(2000, 2001), normal_years=2)
    for doc in (one, flat):
        found = document(doc)
        assert found["status"] == "failed"
        assert found["error"]["code"] == "data_error"
        assert STATION in found["error"]["message"]
        assert "years" not in found


# --- the route's parameters ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "option"),
    [
        (b"colours=16", "colours"),
        (b"scale=1999", "scale"),
        (b"scale=2025&scale=2019", "scale"),
        (b"centre_first_year=2011&centre_last_year=2010", "centre_first_year"),
        (b"spread_first_year=abc", "spread_first_year"),
        (b"spread_last_year=3000", "spread_last_year"),
    ],
)
async def test_a_wrong_parameter_is_refused_before_hydrolog_runs(query, option):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/prototype/stripes/{STATION}",
            "query_string": query,
            "headers": [],
            "path_params": {"code": STATION},
        }
    )
    with pytest.raises(GuiError) as caught:
        await stripes(request)
    assert caught.value.code == "validation_error"
    assert caught.value.details["option"] == option
