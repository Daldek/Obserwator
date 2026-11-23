"""
Hourly series and live tails for the GUI's tests (ADR-031, O6).

`plant_hours` writes month versions of an hourly series as the O4 contract lays them out
(``series/versions/<slug>/<YYYY-MM>/<label>_<sha8>/`` with ``series.json``, its sidecar
and one Parquet file per station) into a copy of a data root; `plant_month` writes one
day of the fixture's station. `hydro_back_answers` and `chmu_now_answer` make the answers
of a live tail (`ProviderAdapter.live_tail`) in the providers' forms. `add_details` gives
an IMGW-PIB station of a copied root the details of hydro.imgw.pl (ADR-021), its warning
and alarm levels among them.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import respx

import obserwator
from obserwator.attribution import attribution, dataset_origins
from obserwator.datasets import get_dataset
from obserwator.providers.base import Answer

CHMU = "cz.chmu.hydro_subdaily"
IMGW = "pl.imgw.hydro_subdaily"
HYDRO = "149190310"
"""IMGW-PIB's hydrological station of the fixture root."""
HYDRO_CHMU = "0-203-1-900001"
"""ČHMÚ's hydrological station of the fixture root."""
FLAGS = ("value", "missing", "no_phenomenon", "accumulated")
TIERS = ("verified", "telemetry", "operational")
HOUR = timedelta(hours=1)
DETAILS = (
    Path(__file__).parents[2] / "fixtures" / "store" / "hydro_details_recordings.json"
)
"""The recorded answers of hydro.imgw.pl (``pl.imgw.hydro_details``)."""

Pair = tuple[float | None, str | None]
"""The value of an hour and its tier, ``(None, None)`` without a value."""


def _time(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _runs(days: Sequence[date]) -> list[list[str]]:
    """The runs of consecutive days, ``[[first, last], …]`` as ISO dates."""
    runs: list[list[date]] = []
    for day in sorted(days):
        if runs and day - runs[-1][1] == timedelta(days=1):
            runs[-1][1] = day
        else:
            runs.append([day, day])
    return [[first.isoformat(), last.isoformat()] for first, last in runs]


def _write_month(
    root: Path,
    dataset: str,
    code: str,
    days: Sequence[date],
    points: Mapping[str, Sequence[Pair]],
    made: str,
) -> str:
    """One month version holding every hour of ``days`` of one station; its label."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    descriptor = get_dataset(dataset)
    month = days[0].strftime("%Y-%m")
    hours = [
        datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(hours=h)
        for day in days
        for h in range(24)
    ]
    tiers = [
        tier
        for tier in TIERS
        if any(item[1] == tier for pairs in points.values() for item in pairs)
    ]
    lines = attribution(*dataset_origins(dataset)).fields()
    columns = {
        "time": pa.array(hours, pa.timestamp("us", tz="UTC")),
        "hydro_year": pa.array(
            [h.year + (1 if h.month >= 11 else 0) for h in hours], pa.int32()
        ),
    }
    coverage = {}
    for variable, unit in descriptor.variables.items():
        pairs = points.get(variable, [(None, None)] * len(hours))
        columns[f"{variable}_value"] = pa.array([v for v, _ in pairs], pa.float64())
        columns[f"{variable}_flag"] = pa.DictionaryArray.from_arrays(
            pa.array([0 if v is not None else 1 for v, _ in pairs], pa.int8()),
            pa.array(FLAGS, pa.string()),
        )
        if len(tiers) > 1:
            columns[f"{variable}_tier"] = pa.DictionaryArray.from_arrays(
                pa.array(
                    [None if t is None else TIERS.index(t) for _, t in pairs],
                    pa.int8(),
                ),
                pa.array(TIERS, pa.string()),
            )
        held = [h for h, (v, _) in zip(hours, pairs, strict=True) if v is not None]
        gaps = [
            [_time(h), _time(h)]
            for h, (v, _) in zip(hours, pairs, strict=True)
            if v is None and held and held[0] < h < held[-1]
        ]
        coverage[variable] = {
            "unit": unit,
            "first": _time(held[0]) if held else None,
            "last": _time(held[-1]) if held else None,
            "with_value": len(held),
            "accumulated": 0,
            "gaps": gaps,
        }
    metadata = {
        "obserwator_schema": "obserwator-series/1",
        "dataset": dataset,
        "units": json.dumps(dict(descriptor.variables), sort_keys=True),
        **{name: json.dumps(value) for name, value in lines.items()},
    }
    table = pa.table(columns).replace_schema_metadata(metadata)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    parquet = sink.getvalue().to_pybytes()
    index = {
        "schema": "obserwator-series/1",
        "dataset": dataset,
        "year_type": "calendar",
        "month": month,
        "tiers": tiers,
        "periods": _runs(days),
        "stations": {
            code: {
                "file": f"stations/{code}.parquet",
                "sha256": hashlib.sha256(parquet).hexdigest(),
                "rows": len(hours),
                "variables": coverage,
            }
        },
        **lines,
    }
    data = (
        json.dumps(index, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    label = made[:10]
    version = (
        root / "series" / "versions" / descriptor.slug / month / f"{label}_{sha[:8]}"
    )
    (version / "stations").mkdir(parents=True)
    (version / "stations" / f"{code}.parquet").write_bytes(parquet)
    (version / "series.json").write_bytes(data)
    # The provider's fields (producer, country, licence) of its daily series' sidecar
    daily = "chmu_hydro_daily" if dataset == CHMU else "imgw_hydro_daily"
    template = max((root / "series/versions" / daily).glob("*/*.meta.json"))
    sidecar = {
        **json.loads(template.read_text(encoding="utf-8")),
        "dataset": dataset,
        "downloaded_at": made,
        "sha256": sha,
        "size_bytes": len(data),
        "request": {"dataset": dataset, "month": month},
        "tier": "operational",
        "publication": "public" if dataset == CHMU else "private",
        "extra": {
            "derived": "series",
            "version": {"label": label, "label_source": "inputs"},
            "series_schema": "obserwator-series/1",
            "source_files": [],
        },
    }
    (version / "series.json.meta.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )
    return f"{month}/{version.name}"


def plant_month(root, dataset, day, points, *, made="2026-11-23T15:00:00Z"):
    """
    One month version of an hourly series holding one day of the fixture's station.

    ``points`` maps each variable to 24 ``(value, tier)`` pairs, hour 0 to 23 UTC of
    ``day`` (``(None, None)`` without a value); a variable without any value is
    left out of the coverage's values, as the builder leaves it.
    """
    code = HYDRO_CHMU if dataset == CHMU else HYDRO
    return _write_month(root, dataset, code, [day], points, made)


def plant_hours(
    root: Path,
    dataset: str,
    code: str,
    first: date,
    last: date,
    value: Callable[[datetime, str], Pair],
    *,
    made: str = "2026-11-23T15:00:00Z",
) -> list[str]:
    """
    The month versions of an hourly series holding one station's days ``first`` to ``last``.

    ``value(hour, variable)`` gives each hour's ``(value, tier)`` (UTC, the start of the
    hour), ``(None, None)`` without a value. One version per month touched; the labels.
    """
    days = [first + timedelta(days=step) for step in range((last - first).days + 1)]
    months: dict[str, list[date]] = {}
    for day in days:
        months.setdefault(day.strftime("%Y-%m"), []).append(day)
    variables = tuple(get_dataset(dataset).variables)
    labels = []
    for month_days in months.values():
        hours = [
            datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(hours=h)
            for day in month_days
            for h in range(24)
        ]
        points = {name: [value(hour, name) for hour in hours] for name in variables}
        labels.append(_write_month(root, dataset, code, month_days, points, made))
    return labels


def _hydro_back_url(path: str, code: str, hours: int) -> str:
    return f"https://hydro-back.imgw.pl/station/hydro/{path}?id={code}&hoursInterval={hours}"


def hydro_back_answers(
    code: str,
    hours: int,
    now: datetime,
    value: Callable[[datetime, str], float | None],
) -> tuple[Answer, ...]:
    """
    hydro-back's H, Q and T of one station, ``hours`` back from ``now`` (a live tail).

    ``operational`` holds the full hours of the span and, as the backend gives them, the
    10-minute points of its last two hours; ``value(time, variable)`` gives each point's
    value (None leaves the point out).
    """
    end = now.replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % 10)
    start = (now - hours * HOUR).replace(minute=0, second=0, microsecond=0) + HOUR
    answers = []
    for variable, path in (
        ("H", "status/data"),
        ("Q", "discharge"),
        ("T", "water-temperature"),
    ):
        entries = []
        moment = start
        while moment <= end:
            tail = end - moment <= timedelta(hours=2)
            if moment.minute == 0 or tail:
                found = value(moment, variable)
                if found is not None:
                    entries.append({"date": _time(moment), "value": found})
            moment += timedelta(minutes=10)
        body = {"operational": entries, "hdModelStateForecast": []}
        answers.append(
            Answer(
                _hydro_back_url(path, code, hours),
                now,
                200,
                json.dumps(body).encode("utf-8"),
                "pl.imgw.hydro_operational",
            )
        )
    return tuple(answers)


def chmu_now_answer(
    code: str, now: datetime, value: Callable[[datetime, str], float | None]
) -> Answer:
    """ČHMÚ's ``now`` file of one station: H, Q and TH every 10 minutes of its UTC day."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    series = []
    for con, variable in (("H", "H"), ("Q", "Q"), ("TH", "T")):
        data = []
        moment = start
        while moment <= now:
            found = value(moment, variable)
            if found is not None:
                data.append({"dt": _time(moment), "value": found})
            moment += timedelta(minutes=10)
        series.append({"tsConID": con, "unit": "", "tsData": data})
    body = {"objList": [{"objID": code, "tsList": series}]}
    return Answer(
        f"https://opendata.chmi.cz/hydrology/now/data/{code}.json",
        now,
        200,
        json.dumps(body).encode("utf-8"),
        "cz.chmu.hydro_current",
    )


def add_details(raw: Path, data: Path, code: str) -> None:
    """
    Give an IMGW-PIB station of copied roots hydro.imgw.pl's details (ADR-021).

    The recorded page of Kłodzko (150160180: warning level 160 cm, alarm level 240 cm)
    re-keyed to ``code`` is synced from a map holding ``code`` alone into the raw root,
    and the IMGW-PIB catalog of the data root is built again from it.
    """
    recorded = {
        item["case"]: item
        for item in json.loads(DETAILS.read_text(encoding="utf-8"))["interactions"]
    }
    page = copy.deepcopy(recorded["status_150160180"]["json"])
    page["id"] = code
    page["status"]["name"] = code
    mapped = recorded["map"]
    station = {**mapped["json"]["stations"][0], "id": code}
    with respx.mock(assert_all_mocked=True) as router:
        router.get(mapped["url"]).mock(
            return_value=httpx.Response(
                200, json={**mapped["json"], "stations": [station]}
            )
        )
        router.get(recorded["status_unknown"]["url"].replace("999999999", code)).mock(
            return_value=httpx.Response(200, json=page)
        )
        synced = obserwator.sync_store(raw, datasets=["pl.imgw.hydro_details"])
    assert [item.status for item in synced.items] == ["new"]
    obserwator.build_catalog(data, raw_root=raw)


class FakeTail:
    """
    A live tail's ``fetch`` (`LiveTail`) answering as the providers do, without a request.

    IMGW-PIB's station gets hydro-back's three answers, ČHMÚ's its ``now`` file, made at
    ``now()`` from ``value(time, variable)``; each request is noted in ``asked`` as
    ``(provider, code, hours)``. ``failure`` makes every request raise it.
    """

    def __init__(
        self,
        now: Callable[[], datetime],
        value: Callable[[datetime, str], float | None],
        failure: Exception | None = None,
    ) -> None:
        self.now = now
        self.value = value
        self.failure = failure
        self.asked: list[tuple[str, str, int]] = []

    def __call__(self, provider: str, code: str, hours: int) -> Sequence[Answer]:
        self.asked.append((provider, code, hours))
        if self.failure is not None:
            raise self.failure
        if provider == "IMGW":
            return hydro_back_answers(code, hours, self.now(), self.value)
        return (chmu_now_answer(code, self.now(), self.value),)
