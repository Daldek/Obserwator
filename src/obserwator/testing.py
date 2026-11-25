"""Offline fixture roots for contract tests of Obserwator consumers.

``build_fixture_store`` builds a small raw root and the data root built from it
(ADR-017) with the real public writers (``init_store``, ``write_archive``,
``sync_store``, ``build_series``, ``build_catalog``) while every HTTP request is
answered from recordings shipped with the package. No request reaches the network;
an unrecorded request fails as a connection error, and no replayed answer reaches the
capture spool of ``state_dir`` (ADR-030 D7).

Requires the ``pyarrow`` dependency of series building (``obserwator[store]``).
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import threading
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Literal, Self, get_args
from unittest import mock
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

import httpx

from obserwator import captures as _captures
from obserwator import fetch as _fetch
from obserwator.datasets import archive_files, get_dataset
from obserwator.exceptions import (
    ObserwatorDataError,
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.fetch import download_hydro_data, download_meteo_data
from obserwator.messages import message
from obserwator.providers.pl import imgw as _imgw
from obserwator.store import (
    build_catalog,
    build_series,
    init_store,
    sync_store,
    write_archive,
)
from obserwator.store import captures as _store_captures
from obserwator.store import writer as _writer
from obserwator.store.types import PathArg, StoreHandle
from obserwator.store.writer import _canonical

__all__ = ["FixtureRoots", "FixtureVariant", "build_fixture_store", "fixture_files"]

FixtureVariant = Literal[
    "complete",
    "corrupt",
    "unknown_schema",
    "complete_pl_cz",
    "groundwater",
    "groundwater_pl",
]

_RECORDINGS = ("recordings.json", "builder_recordings.json")
_CHMU_RECORDINGS = ("chmu_builder_recordings.json",)
_GROUNDWATER_RECORDINGS = ("chmu_groundwater_recordings.json",)
_HYDRO = "pl.imgw.hydro_daily"
_METEO = "pl.imgw.meteo_precip_daily"
_UNKNOWN_LABEL = "2026-10-20"
# Recorded answers in the order the scenario requests them; repeated URLs are queued.
_SCENARIO = (
    "hydro_get",
    "same_bytes_new_signal",
    "new_bytes_get",
    "meteo_get",
    "meteo_1995_get",
    "hydro_stations_head",
    "hydro_stations_head",
    "hydro_stations_get",
    "meteo_stations_head",
    "meteo_stations_head",
    "meteo_stations_get",
    "hydro_current",
    "meteo_current",
)
# Station sources of each provider's catalog, stored by store sync (ADR-015).
_IMGW_SOURCES = (
    "pl.imgw.hydro_stations",
    "pl.imgw.meteo_stations",
    "pl.imgw.hydro_now",
    "pl.imgw.meteo_now",
)
_CHMU_SOURCES = (
    "cz.chmu.hydro_stations",
    "cz.chmu.meteo_stations",
    "cz.chmu.hydro_now",
    "cz.chmu.meteo_now",
)
_CHMU_HYDRO = "cz.chmu.hydro_daily"
_CHMU_METEO = "cz.chmu.meteo_daily"
# Fictional ČHMÚ stations of the fixture files (spec 2026-10-18 §13.2).
_CHMU_FULL, _CHMU_GAP = "0-203-1-900001", "0-203-1-900002"
_CHMU_ELEMENTS, _CHMU_RAIN = "0-203-0-90001", "0-203-0-90000000002"
# ČHMÚ part of complete_pl_cz (spec 2026-10-18 §13.2 scenarios (1)-(3) and (8)):
# sync_store selectors with the expected statuses of the items and of the series.
_CHMU_STEPS: tuple[tuple[str, Mapping[str, Any], tuple[str, ...], str], ...] = (
    (
        "ČHMÚ hydro (1) first publication",
        {"datasets": (_CHMU_HYDRO,), "stations": (_CHMU_FULL, _CHMU_GAP)},
        ("new",) * 4,
        "new",
    ),
    (
        "ČHMÚ hydro (2) republication",
        {"datasets": (_CHMU_HYDRO,), "stations": (_CHMU_GAP,)},
        ("relabeled",) * 2,
        "unchanged",
    ),
    (
        "ČHMÚ hydro (3) correction",
        {"datasets": (_CHMU_HYDRO,), "stations": (_CHMU_FULL,), "years": (2024,)},
        ("new",),
        "new",
    ),
    (
        "ČHMÚ hydro (8) reserialization",
        {"datasets": (_CHMU_HYDRO,), "stations": (_CHMU_FULL,), "years": (2023,)},
        ("unchanged",),
        "unchanged",
    ),
    (
        "ČHMÚ meteo",
        {"datasets": (_CHMU_METEO,), "stations": (_CHMU_ELEMENTS, _CHMU_RAIN)},
        # The temperature and snow elements of the precipitation-only station are
        # not published: unchanged without a version.
        ("new",) * 7 + ("unchanged",) * 5,
        "new",
    ),
)
# ČHMÚ's groundwater part of the variant ``groundwater`` (ADR-032): a real bore and a
# real spring, synchronized from ``chmu_groundwater_recordings.json``.
_GW_DAILY, _GW_WEEKLY = "cz.chmu.groundwater_daily", "cz.chmu.groundwater_weekly"
_GW_BORE, _GW_SPRING = "0-203-1-VP0624", "0-203-1-PP0744"
_GROUNDWATER_SOURCES = ("cz.chmu.groundwater_stations", "cz.chmu.groundwater_now")
_GROUNDWATER_STEPS: tuple[tuple[str, Mapping[str, Any], int], ...] = (
    (
        "ČHMÚ groundwater daily 2024",
        {
            "datasets": (_GW_DAILY,),
            "stations": (_GW_BORE, _GW_SPRING),
            "years": (2024,),
        },
        2,
    ),
    (
        "ČHMÚ groundwater weekly 2012 of the bore",
        {"datasets": (_GW_WEEKLY,), "stations": (_GW_BORE,), "years": (2012,)},
        1,
    ),
    (
        "ČHMÚ groundwater weekly 2014 of the spring",
        {"datasets": (_GW_WEEKLY,), "stations": (_GW_SPRING,), "years": (2014,)},
        1,
    ),
    (
        "ČHMÚ groundwater recent months of the bore in the listing",
        {"datasets": ("cz.chmu.groundwater_recent",), "stations": (_GW_BORE,)},
        1,
    ),
    (
        "ČHMÚ groundwater characteristics",
        {
            "datasets": ("cz.chmu.groundwater_characteristic",),
            "stations": (_GW_BORE, _GW_SPRING),
        },
        2,
    ),
)
# The recorded answers the groundwater steps and sources request, in their order (the
# list of the objects is checked by HEAD before its sync heads and gets it).
_GROUNDWATER_SCENARIO = (
    "gw_historical_listing",
    "gw_pp0744_d_2024_head",
    "gw_pp0744_d_2024_get",
    "gw_vp0624_d_2024_head",
    "gw_vp0624_d_2024_get",
    "gw_historical_listing",
    "gw_vp0624_w_2012_head",
    "gw_vp0624_w_2012_get",
    "gw_historical_listing",
    "gw_pp0744_w_2014_head",
    "gw_pp0744_w_2014_get",
    "gw_recent_listing",
    "gw_recent_vp0624_d_202610_head",
    "gw_recent_vp0624_d_202610_get",
    "gw_characteristic_listing",
    "gw_characteristic_pp0744_head",
    "gw_characteristic_pp0744_get",
    "gw_characteristic_vp0624_head",
    "gw_characteristic_vp0624_get",
    "gw_stations_head",
    "gw_stations_head",
    "gw_stations_get",
    "gw_now_get",
)
# Recorder patching is process-global; serialize concurrent builders.
_HTTP_LOCK = threading.Lock()


def fixture_files() -> Traversable:
    """
    Return the packaged fixture data directory.

    Layout: ``archives/<server path>`` (IMGW-PIB yearbooks and station lists,
    ČHMÚ station files and metadata), ``listings/`` (ČHMÚ directory
    listings), ``variants/``, recorded HTTP answers ``recordings.json``,
    ``builder_recordings.json``, ``chmu_recordings.json``,
    ``chmu_catalog_recordings.json``, ``chmu_builder_recordings.json``,
    ``chmu_groundwater_recordings.json``, ``hydro_details_recordings.json`` and
    ``meteo_details_recordings.json`` (real answers of hydro.imgw.pl's backend),
    ``contract_recordings.json`` (live endpoints of the interface contract tests),
    ``pig_recordings.json`` (real rows of PIG-PIB's ArcGIS services ``mwp`` and
    ``mwp_auto``, cut to a few points, answered by the private ``_PigService``),
    and ``contract_schemas.json`` (JSON Schemas with examples of the store documents
    ``obserwator-store/1`` ... ``obserwator-pmaxtp/1``, the envelope
    ``obserwator-result/1`` and the error documents ``problem+json`` and
    ``obserwator-error/1``). Data are short synthetic samples with fictional station
    codes, not real yearbooks, except the recorded answers of hydro.imgw.pl's backend
    and ČHMÚ's groundwater files: the real files of two objects with the server's
    headers, their listings and object lists cut to the real rows of them, and
    PIG-PIB's recorded rows.

    Returns
    -------
    importlib.resources.abc.Traversable
        Synthetic archives and recorded HTTP answers, read via
        ``importlib.resources``.
    """
    return files("obserwator").joinpath("_data", "fixtures")


def _interactions(recordings: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Recorded interactions of the given files keyed by case, in file order."""
    result: dict[str, dict[str, Any]] = {}
    for name in recordings:
        document = json.loads(
            fixture_files().joinpath(name).read_text(encoding="utf-8")
        )
        base = str(document.get("base_url")).rstrip("/")
        for interaction in document["interactions"]:
            interaction.setdefault("url", f"{base}/{interaction.get('path')}")
            result[interaction["case"]] = interaction
    return result


def _body(interaction: Mapping[str, Any]) -> tuple[bytes, dict[str, str]]:
    headers = dict(interaction.get("headers") or {})
    if "json" in interaction:
        headers.setdefault("Content-Type", "application/json")
        return json.dumps(interaction["json"], ensure_ascii=False).encode(
            "utf-8"
        ), headers
    if "body" in interaction:
        return str(interaction["body"]).encode("utf-8"), headers
    if "archive" in interaction:
        resource = fixture_files().joinpath(
            "archives", *interaction["archive"].split("/")
        )
    elif "variant" in interaction or "listing" in interaction:
        relative = interaction.get("variant") or interaction["listing"]
        resource = fixture_files().joinpath(*relative.split("/"))
    else:
        return b"", headers
    data = resource.read_bytes()
    expected = interaction.get("sha256")
    if expected is not None and hashlib.sha256(data).hexdigest() != expected:
        raise ObserwatorDataError(
            message(
                "testing.checksum_recording_does_not_match", case=interaction["case"]
            )
        )
    return data, headers


@contextmanager
def _recorded_http(
    cases: Iterable[str] | None,
    *,
    recordings: Iterable[str] = _RECORDINGS,
    keep: bool = False,
) -> Iterator[None]:
    """
    Answer synchronous httpx requests from recordings, in the given order per URL.

    ``cases=None`` replays every interaction of ``recordings`` in file order. A
    replayed answer is no provider's answer: unless ``keep`` (a test of the captures),
    the library's requests keep none in the capture spool (`obserwator.captures`), so a
    fixture built on a machine with a real spool never reaches it (ADR-030 D7).
    """
    recorded = _interactions(recordings)
    queues: dict[tuple[str, str], deque[Mapping[str, Any]]] = {}
    for case in recorded if cases is None else cases:
        interaction = recorded[case]
        queues.setdefault((interaction["method"], interaction["url"]), deque()).append(
            interaction
        )

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        queue = queues.get((request.method, str(request.url)))
        if not queue:
            raise httpx.ConnectError(
                message(
                    "testing.no_recorded_response",
                    method=request.method,
                    url=request.url,
                ),
                request=request,
            )
        interaction = queue.popleft()
        content, headers = _body(interaction)
        return httpx.Response(
            interaction["status"], headers=headers, content=content, request=request
        )

    with ExitStack() as stack:
        stack.enter_context(_HTTP_LOCK)
        stack.enter_context(
            mock.patch.object(httpx.HTTPTransport, "handle_request", handle)
        )
        if not keep:
            stack.enter_context(
                mock.patch("obserwator.captures.keep_response", return_value=None)
            )
        yield
    left = sorted(f"{method} {url}" for (method, url), queue in queues.items() if queue)
    if left:
        raise ObserwatorDataError(
            message("testing.recorded_responses_were_not_used", left=", ".join(left))
        )


def _expect(step: str, status: str, expected: str) -> None:
    if status != expected:
        raise ObserwatorDataError(
            message(
                "testing.fixture_step_ended_status_expected",
                step=step,
                status=status,
                expected=expected,
            )
        )


@contextmanager
def _without_reference_data() -> Iterator[None]:
    """Hide the local static locations file (``settings.reference_dir``) from the catalog.

    Fixture stores must not depend on reference data a user fetched with
    ``python -m obserwator.reference_data``. Process-global: call under ``_HTTP_LOCK``.
    """
    original = _imgw._static_file
    _imgw._static_file = lambda: (Path(_imgw.STATIC_LOCATIONS), None)
    try:
        yield
    finally:
        _imgw._static_file = original


def _add_unknown_version(root: Path) -> None:
    """Series version of an unknown major schema, which writers refuse to produce."""
    data = _canonical({"schema": "obserwator-series/2", "dataset": _HYDRO})
    sha = hashlib.sha256(data).hexdigest()
    target = (
        root
        / "series"
        / "versions"
        / get_dataset(_HYDRO).slug
        / f"{_UNKNOWN_LABEL}_{sha[:8]}"
    )
    target.mkdir(parents=True)
    (target / "series.json").write_bytes(data)
    (target / "series.json.meta.json").write_bytes(
        _canonical(
            {
                "schema": "obserwator-meta/2",
                "producer": "obserwator",
                "dataset": _HYDRO,
                "sha256": sha,
                "size_bytes": len(data),
                "extra": {
                    "version": {"label": _UNKNOWN_LABEL, "label_source": "downloaded"}
                },
            }
        )
    )


def _add_groundwater(raw: StoreHandle, data: StoreHandle) -> None:
    """
    ČHMÚ's groundwater files of the variant ``groundwater`` and their two series.

    The daily files of 2024 of the bore and the spring, the weekly file of 2012 of
    the bore and of 2014 of the spring, the bore's ``recent`` months of the listing
    (2026-10) and the characteristics of both, each synchronized new; then the
    daily and the weekly series, each built new.
    """
    for step, selectors, count in _GROUNDWATER_STEPS:
        report = sync_store(raw, **selectors)
        _expect(
            step,
            ", ".join(sorted(item.status for item in report.items)),
            ", ".join(("new",) * count),
        )
    for dataset in (_GW_DAILY, _GW_WEEKLY):
        series = build_series(data, raw_root=raw, dataset=dataset)
        _expect(f"{dataset}: series", series.status, "new")


def _add_chmu(raw: StoreHandle, data: StoreHandle, *, groundwater: bool) -> None:
    """
    ČHMÚ part of ``complete_pl_cz``, replayed from ``chmu_builder_recordings.json``.

    Each step is one `sync_store` into the raw root (listing, then HEAD and GET
    of every new or changed file), then `build_series` of the step's dataset
    into the data root; the station sources are synchronized and the ČHMÚ
    catalog is built last. ``groundwater`` adds ČHMÚ's groundwater objects
    (`_add_groundwater` and the two lists of the objects among the station
    sources) from ``chmu_groundwater_recordings.json`` before the sources.
    """
    recordings: tuple[str, ...] = _CHMU_RECORDINGS
    sources: tuple[str, ...] = _CHMU_SOURCES
    cases: list[str] | None = None
    if groundwater:
        recordings += _GROUNDWATER_RECORDINGS
        cases = [*_interactions(_CHMU_RECORDINGS), *_GROUNDWATER_SCENARIO]
        sources += _GROUNDWATER_SOURCES
    with _recorded_http(cases, recordings=recordings):
        for step, selectors, items, built in _CHMU_STEPS:
            report = sync_store(raw, **selectors)
            _expect(
                step,
                ", ".join(sorted(item.status for item in report.items)),
                ", ".join(sorted(items)),
            )
            series = build_series(data, raw_root=raw, dataset=selectors["datasets"][0])
            _expect(f"{step}: series", series.status, built)
        if groundwater:
            _add_groundwater(raw, data)
        synced = sync_store(raw, datasets=sources)
        _expect(
            "ČHMÚ station sources",
            ", ".join(sorted({item.status for item in synced.items})),
            "new",
        )
        catalog = build_catalog(data, raw_root=raw, provider="CHMU")
        _expect("ČHMÚ station catalog", catalog.status, "new")


@dataclass(frozen=True)
class FixtureRoots:
    """
    The two roots of a fixture built by `build_fixture_store` (ADR-017).

    Attributes
    ----------
    raw : StoreHandle
        The raw root (``obserwator-store.json``): archive versions and station
        sources.
    data : StoreHandle
        The data root (``obserwator-data.json``): the series and station
        catalogs built from the raw root.
    """

    raw: StoreHandle
    data: StoreHandle


def build_fixture_store(
    root: PathArg, *, data_root: PathArg, variant: FixtureVariant = "complete"
) -> FixtureRoots:
    """
    Build offline fixture roots with the public writers in two empty directories.

    ``root`` becomes the raw root (archives, station sources) and ``data_root``
    the data root (series, catalogs) built from it (ADR-017). ``complete``
    contains:

    * ``codz_2024.zip`` (``pl.imgw.hydro_daily``) in three versions: the old one, the
      same bytes relabeled under a newer HTTP signal and newer bytes (current);
    * two ``imgw_hydro_daily`` series: an older one built from the old archive and
      the current one built from the newer archive;
    * ``imgw_meteo_precip_daily`` series that is outdated (``1995_o.zip`` was stored
      after the series was built from ``2001_01_o.zip``);
    * both station lists and a ``stations.geojson`` catalog with stations whose
      ``geometry`` is ``null`` in ``stations/versions/imgw_stations/``, built
      without the local static locations file (recorded in its sidecar as
      ``available: false``).

    ``corrupt`` additionally truncates the sidecar of the old hydro archive
    version (raw root); ``unknown_schema`` additionally adds an ``imgw_hydro_daily``
    series version with ``obserwator-meta/2``/``obserwator-series/2`` that
    readers must report without parsing (data root).

    ``complete_pl_cz`` is ``complete`` plus the ČHMÚ provider (spec 2026-10-18
    §13.3), synchronized with `sync_store` from ``chmu_builder_recordings.json``
    (fictional station codes):

    * ``cz.chmu.hydro_daily`` files: ``H_0-203-1-900002_DQ_2004.json`` and
      ``…_2006.json`` in a first and a ``relabeled`` version (the same bytes
      republished), ``H_0-203-1-900001_DQ_2024.json`` in a first and a
      corrected version, and ``H_0-203-1-900001_DQ_2023.json`` in one version
      with an observation in ``observations/`` (re-serialized bytes with the
      same canonical content, ``content_unchanged``);
    * ``cz.chmu.meteo_daily`` CSV files of ``0-203-0-90001`` (SRA, T, TMA,
      TMI, SCE, SNO) and ``0-203-0-90000000002`` (SRA only);
    * the ``chmu_hydro_daily`` series in two versions (before and after the
      correction), the ``chmu_meteo_daily`` series, both ČHMÚ station lists
      and the ČHMÚ catalog ``stations/versions/chmu_stations/``.

    ``groundwater`` is ``complete_pl_cz`` plus ČHMÚ's groundwater (ADR-032), real
    files and server headers of ``chmu_groundwater_recordings.json`` synchronized
    before the ČHMÚ station sources, so that its one ČHMÚ catalog holds them:

    * ``cz.chmu.groundwater_daily`` files of 2024 of the bore ``0-203-1-VP0624``
      (Rakousy) and of the spring ``0-203-1-PP0744`` (Želechy), and
      ``cz.chmu.groundwater_weekly`` files of 2012 of the bore and of 2014 of the
      spring;
    * the bore's ``cz.chmu.groundwater_recent`` month 2026-10 and the
      ``cz.chmu.groundwater_characteristic`` files of both objects (archives
      without a series);
    * the ``chmu_groundwater_daily`` and ``chmu_groundwater_weekly`` series;
    * the list (``cz.chmu.groundwater_stations``) and the current metadata
      (``cz.chmu.groundwater_now``) of the two objects, cut to their rows.

    ``groundwater_pl`` is ``groundwater`` plus PIG-PIB (ADR-035): the real rows of
    its ArcGIS services in ``pig_recordings.json`` (eleven points), answered with
    ArcGIS's semantics and synchronized by `sync_store` on a clock that starts at
    the probe's capture, 2026-11-24 22:16 UTC, and moves only when a paced request
    waits (no request sleeps, and the raw versions are dated by that clock):

    * the points (``pl.pig.groundwater_stations``), October 2026's readings
      (``pl.pig.groundwater_readings``, ``MWP_2026-10.jsonl.gz``, with the one
      reading of 9390, a point missing from the points) and the night's capture of
      ``pl.pig.groundwater_operational`` of 2026-11-24 (the harvest by watermark
      from ``OBJECTID`` 0, with the stored hour 02 of 2026-03-29);
    * the readings series ``pig_groundwater_readings``, the hourly series
      ``pig_groundwater_subdaily`` (the months 2026-03, 2026-10 and 2026-11) and
      the PIG catalog ``stations/versions/pig_stations/`` (among them the
      automatic bore 6495 „Olszyc Szlachecki”, the weekly bore 853 „Tucznawa” and
      the spring 1247 „Falsztyn”).

    Parameters
    ----------
    root : str or os.PathLike
        Directory of the raw root; it must not exist or be an empty directory.
    data_root : str or os.PathLike
        Directory of the data root, outside ``root``; it must not exist or be
        an empty directory.
    variant : {"complete", "corrupt", "unknown_schema", "complete_pl_cz", "groundwater", "groundwater_pl"}, optional
        Fixture variant to build.

    Returns
    -------
    FixtureRoots
        Handles of the built raw and data roots.

    Raises
    ------
    ObserwatorValidationError
        If ``variant`` is unknown.
    ObserwatorStoreError
        If ``root`` or ``data_root`` is not an empty directory.
    ObserwatorStoreConflictError
        If one root lies in the other (``details.reason`` ``nested_store``).
    ObserwatorDataError
        If a build step ends with an unexpected status, a recording does not match
        its checksum or recorded answers are left unused.
    ObserwatorConnectionError
        If a request has no recorded answer.
    """
    if variant not in get_args(FixtureVariant):
        raise ObserwatorValidationError(
            message(
                "testing.unknown_fixture_variant_allowed",
                variant=variant,
                allowed=", ".join(get_args(FixtureVariant)),
            )
        )
    paths = Path(root), Path(data_root)
    for path in paths:
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise ObserwatorStoreError(
                message("testing.fixture_store_needs_empty_directory", path=path)
            )
    raw = init_store(paths[0])
    data = init_store(paths[1], kind="data")
    (hydro,) = archive_files(_HYDRO, years=(2024,))
    (meteo_2001,) = archive_files(_METEO, years=(2001,), months=(1,))
    (meteo_1995,) = archive_files(_METEO, years=(1995,))
    with _recorded_http(_SCENARIO):
        old = write_archive(
            raw, archive=hydro, response=download_hydro_data("dobowe", 2024)
        )
        _expect("codz_2024 v1", old.status, "new")
        first = build_series(data, raw_root=raw, dataset=_HYDRO)
        _expect("series hydro v1", first.status, "new")
        relabeled = write_archive(
            raw, archive=hydro, response=download_hydro_data("dobowe", 2024)
        )
        _expect("codz_2024 v2", relabeled.status, "relabeled")
        newer = write_archive(
            raw, archive=hydro, response=download_hydro_data("dobowe", 2024)
        )
        _expect("codz_2024 v3", newer.status, "new")
        second = build_series(data, raw_root=raw, dataset=_HYDRO)
        _expect("series hydro v2", second.status, "new")
        meteo = write_archive(
            raw,
            archive=meteo_2001,
            response=download_meteo_data("dobowe", "opad", 2001, 1),
        )
        _expect("2001_01_o", meteo.status, "new")
        precip = build_series(data, raw_root=raw, dataset=_METEO)
        _expect("series meteo", precip.status, "new")
        late = write_archive(
            raw,
            archive=meteo_1995,
            response=download_meteo_data("dobowe", "opad", 1995),
        )
        _expect("1995_o", late.status, "new")
        sources = sync_store(raw, datasets=_IMGW_SOURCES)
        _expect(
            "station sources",
            ", ".join(sorted({item.status for item in sources.items})),
            "new",
        )
        with _without_reference_data():
            catalog = build_catalog(data, raw_root=raw)
        _expect("station catalog", catalog.status, "new")
        if catalog.without_location == 0:
            raise ObserwatorDataError(message("testing.fixture_station_catalog_has_no"))
    if variant == "corrupt":
        sidecar = old.path.with_name(f"{old.path.name}.meta.json")
        sidecar.write_bytes(sidecar.read_bytes()[: sidecar.stat().st_size // 2])
    elif variant == "unknown_schema":
        _add_unknown_version(data.root)
    elif variant in ("complete_pl_cz", "groundwater", "groundwater_pl"):
        _add_chmu(raw, data, groundwater=variant != "complete_pl_cz")
        if variant == "groundwater_pl":
            _add_pig(raw, data)
    return FixtureRoots(raw, data)


# --- PIG-PIB's ArcGIS services, answered from recorded rows (tests only) -----------

_PIG_RECORDINGS = "pig_recordings.json"
_PIG_ZONE = ZoneInfo("Europe/Warsaw")
"""The zone by which ``mwp_auto`` converts its stored times to epochs (W9)."""
_PIG_STORED = "%Y-%m-%d %H:%M:%S"
_PIG_PATH = re.compile(r"([a-z_]+/MapServer/[0-9]+)/query")
_PIG_AFTER = re.compile(r"OBJECTID > ([0-9]+)")
_PIG_TIME = re.compile(
    r"TIME >= TIMESTAMP '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})' AND "
    r"TIME < TIMESTAMP '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})'"
)
_PIG_PAGE = 1000
_PIG_ERROR: dict[str, object] = {
    "error": {"code": 400, "message": "Unable to complete operation.", "details": []}
}
"""The answer (HTTP 200) of the services to a query they cannot complete."""


@dataclass
class _ArcgisTable:
    """
    One layer or table of an ArcGIS service, as recorded.

    Attributes
    ----------
    head : dict
        A recorded page answer's keys other than ``features`` and
        ``exceededTransferLimit`` (``fields``, ``spatialReference``…).
    rows : list of dict
        Its features as recorded (``attributes``, ``geometry``). A row of
        ``mwp_auto``'s table 2 may carry the attribute ``_stored``, its stored wall
        time ``YYYY-MM-DD HH:MM:SS``, which is never served.
    """

    head: dict[str, Any]
    rows: list[dict[str, Any]]


def _pig_document() -> dict[str, Any]:
    """``pig_recordings.json``, parsed afresh."""
    document: dict[str, Any] = json.loads(
        fixture_files().joinpath(_PIG_RECORDINGS).read_text(encoding="utf-8")
    )
    return document


def _pig_tables_of(document: Mapping[str, Any]) -> dict[str, _ArcgisTable]:
    return {
        name: _ArcgisTable(table["head"], table["rows"])
        for name, table in document["tables"].items()
    }


def _pig_tables() -> dict[str, _ArcgisTable]:
    """
    The recorded tables of PIG-PIB's services, a fresh copy on each call.

    Returns
    -------
    dict of str to _ArcgisTable
        By ``<service>/MapServer/<n>``: ``mwp/MapServer/0`` (points),
        ``mwp/MapServer/1`` (readings), ``mwp_auto/MapServer/0`` (automatic points)
        and ``mwp_auto/MapServer/2`` (hourly rows).
    """
    return _pig_tables_of(_pig_document())


def _pig_stored(row: Mapping[str, Any]) -> datetime:
    """A row's stored wall time: its ``_stored``, else its epoch's Warsaw wall time."""
    attributes = row["attributes"]
    stored = attributes.get("_stored")
    if isinstance(stored, str):
        return datetime.strptime(stored, _PIG_STORED)
    wall = datetime.fromtimestamp(attributes["TIME"] / 1000, tz=_PIG_ZONE)
    return wall.replace(tzinfo=None)


def _pig_value(row: Mapping[str, Any], name: str) -> object:
    """An attribute as a statistic sees it: ``TIME`` the stored time unconverted."""
    if name == "TIME":
        stored = _pig_stored(row).replace(tzinfo=UTC)
        return int(stored.timestamp()) * 1000
    return row["attributes"].get(name)


class _PigService:
    """
    PIG-PIB's ArcGIS ``query`` endpoints answered from rows, with ArcGIS semantics.

    Usable as a respx ``side_effect`` and as an `httpx.MockTransport` handler. A POST
    form (or a GET query string) to ``<base_url><service>/MapServer/<n>/query``
    is answered over that table's rows: ``returnCountOnly=true`` by the count,
    ``outStatistics`` (``min``/``max`` of fields) by one feature of the statistics,
    otherwise by a page of the rows in ``OBJECTID`` order (``resultOffset``,
    ``resultRecordCount``, ``exceededTransferLimit`` only while rows remain, the
    geometry only with ``returnGeometry=true``). ``where`` is ``1=1``,
    ``OBJECTID > N`` or a ``TIME`` range of two ``TIMESTAMP``s compared with the
    stored times (W9); any other query is answered by ArcGIS's error object with
    HTTP 200.

    Parameters
    ----------
    tables : Mapping of str to _ArcgisTable or None, optional
        The tables by ``<service>/MapServer/<n>``; the recorded ones by default.

    Attributes
    ----------
    tables : dict of str to _ArcgisTable
        The tables answered from; tests may change them between requests.
    requests : list of tuple
        Every request answered, in order: its path below the base URL (e.g.
        ``mwp/MapServer/1/query``) and its form.
    """

    def __init__(self, tables: Mapping[str, _ArcgisTable] | None = None) -> None:
        document = _pig_document()
        self._base = str(document["base_url"])
        self.tables: dict[str, _ArcgisTable] = (
            _pig_tables_of(document) if tables is None else dict(tables)
        )
        self.requests: list[tuple[str, dict[str, str]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request (HTTP 200, JSON)."""
        address = str(request.url.copy_with(query=None))
        form = dict(request.url.params)
        if request.method == "POST":
            body = request.read().decode("utf-8")
            form.update(parse_qsl(body, keep_blank_values=True))
        path = (
            address.removeprefix(self._base) if address.startswith(self._base) else ""
        )
        self.requests.append((path, form))
        content = json.dumps(
            self._answer(path, form), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json; charset=UTF-8"},
            content=content,
            request=request,
        )

    def _answer(self, path: str, form: Mapping[str, str]) -> object:
        match = _PIG_PATH.fullmatch(path)
        table = self.tables.get(match[1]) if match else None
        if table is None:
            return _PIG_ERROR
        fields = {field["name"]: field for field in table.head.get("fields", ())}
        rows = self._where(table, fields, form.get("where", ""))
        if rows is None:
            return _PIG_ERROR
        if form.get("returnCountOnly") == "true":
            return {"count": len(rows)}
        if "outStatistics" in form:
            return self._statistics(fields, rows, form["outStatistics"])
        try:
            offset = int(form.get("resultOffset", "0"))
            count = int(form.get("resultRecordCount", str(_PIG_PAGE)))
        except ValueError:
            return _PIG_ERROR
        if offset < 0 or count < 1:
            return _PIG_ERROR
        geometry = form.get("returnGeometry") == "true"
        features = []
        for row in rows[offset : offset + count]:
            feature: dict[str, Any] = {
                "attributes": {
                    name: value
                    for name, value in row["attributes"].items()
                    if name != "_stored"
                }
            }
            if geometry and "geometry" in row:
                feature["geometry"] = row["geometry"]
            features.append(feature)
        page: dict[str, Any] = {**table.head, "features": features}
        if offset + count < len(rows):
            page["exceededTransferLimit"] = True
        return page

    @staticmethod
    def _where(
        table: _ArcgisTable, fields: Mapping[str, Any], where: str
    ) -> list[dict[str, Any]] | None:
        """The rows a ``where`` selects in ``OBJECTID`` order; None if not understood."""
        rows = sorted(table.rows, key=lambda row: int(row["attributes"]["OBJECTID"]))
        if where == "1=1":
            return rows
        if after := _PIG_AFTER.fullmatch(where):
            last = int(after[1])
            return [row for row in rows if row["attributes"]["OBJECTID"] > last]
        if (between := _PIG_TIME.fullmatch(where)) and "TIME" in fields:
            start, end = (
                datetime.strptime(text, _PIG_STORED) for text in between.groups()
            )
            return [row for row in rows if start <= _pig_stored(row) < end]
        return None

    @staticmethod
    def _statistics(
        fields: Mapping[str, Any], rows: list[dict[str, Any]], text: str
    ) -> object:
        """The answer of ``outStatistics``: one feature of every statistic asked."""
        try:
            asked = json.loads(text)
        except ValueError:
            return _PIG_ERROR
        if not isinstance(asked, list) or not asked:
            return _PIG_ERROR
        attributes: dict[str, object] = {}
        described: list[dict[str, object]] = []
        for statistic in asked:
            if not isinstance(statistic, dict):
                return _PIG_ERROR
            kind = statistic.get("statisticType")
            field = statistic.get("onStatisticField")
            name = statistic.get("outStatisticFieldName")
            if kind not in ("min", "max") or not isinstance(field, str):
                return _PIG_ERROR
            if field not in fields or not isinstance(name, str) or not name:
                return _PIG_ERROR
            values: list[Any] = [
                value for row in rows if (value := _pig_value(row, field)) is not None
            ]
            pick = min if kind == "min" else max
            attributes[name] = pick(values) if values else None
            described.append(
                {"name": name, "type": fields[field]["type"], "alias": name}
            )
        return {
            "displayFieldName": "",
            "fieldAliases": {item["name"]: item["name"] for item in described},
            "fields": described,
            "features": [{"attributes": attributes}],
        }


# --- PIG-PIB's part of the variant groundwater_pl (ADR-035) -------------------------

_PIG_POINTS = "pl.pig.groundwater_stations"
_PIG_READINGS = "pl.pig.groundwater_readings"
_PIG_OPERATIONAL = "pl.pig.groundwater_operational"
_PIG_SUBDAILY = "pl.pig.groundwater_subdaily"
_PIG_CAPTURED = datetime(2026, 11, 24, 22, 16, tzinfo=UTC)
"""When the probe captured the recorded answers: where the clock of the part starts."""
_PIG_PACE = timedelta(minutes=2)
"""How long the night's harvest of the part is spread over (``--pace-until``)."""


class _PigClock:
    """The clock of PIG-PIB's part: it moves only when a paced request waits."""

    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def now(self) -> datetime:
        """The current time, UTC."""
        return self.moment

    def sleep(self, seconds: float, /) -> None:
        """Move on by ``seconds`` at once."""
        self.moment += timedelta(seconds=seconds)


def _following(clock: _PigClock) -> type[datetime]:
    """`datetime` whose ``now`` is ``clock``'s: the writer's dates of the part."""

    class _Now(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            """``clock``'s time in ``tz``."""
            moment = clock.now()
            return cls.combine(moment.date(), moment.timetz()).astimezone(tz)

    return _Now


@contextmanager
def _pig_answered(clock: _PigClock) -> Iterator[None]:
    """
    PIG-PIB's services answered by `_PigService` on ``clock``, the spool a scratch one.

    Every synchronous httpx request to PIG-PIB's host is answered from the recorded
    rows and any other fails as a connection error. The paced requests and the
    capture spool follow ``clock``, whose waits move it at once; the night's answers
    go to a spool of their own, never the one of ``state_dir`` (ADR-030 D7), whose
    day the run seals; the writer dates the versions by ``clock``. Process-global:
    patched under ``_HTTP_LOCK``.
    """
    service = _PigService()
    host = httpx.URL(service._base).host

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        if request.url.host != host:
            raise httpx.ConnectError(
                message(
                    "testing.no_recorded_response",
                    method=request.method,
                    url=request.url,
                ),
                request=request,
            )
        return service(request)

    with ExitStack() as stack:
        stack.enter_context(_HTTP_LOCK)
        spool = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        for owner, name, value in (
            (httpx.HTTPTransport, "handle_request", handle),
            (_fetch, "_clock", lambda: clock),
            (_fetch, "_ARCGIS", _fetch._Spacing()),
            (_captures, "_now", clock.now),
            (_captures, "spool_root", lambda: spool),
            (_store_captures, "spool_root", lambda: spool),
            (_writer, "datetime", _following(clock)),
        ):
            stack.enter_context(mock.patch.object(owner, name, value))
        yield


def _add_pig(raw: StoreHandle, data: StoreHandle) -> None:
    """
    PIG-PIB's part of ``groundwater_pl``: its datasets synchronized, then built.

    `sync_store` of the points and of the readings, then the night's harvest of
    ``mwp_auto`` by watermark (``pace_until`` two minutes on, its day sealed), each
    new, on a clock that starts at the probe's capture (`_pig_answered`); then the
    readings series, the hourly series and the PIG catalog, each built new.
    """
    clock = _PigClock(_PIG_CAPTURED)
    with _pig_answered(clock):
        for key in (_PIG_POINTS, _PIG_READINGS):
            report = sync_store(raw, datasets=[key])
            _expect(key, ", ".join(item.status for item in report.items), "new")
        until = (clock.now() + _PIG_PACE).astimezone().strftime("%H:%M")
        night = sync_store(raw, datasets=[_PIG_OPERATIONAL], pace_until=until)
        _expect(_PIG_OPERATIONAL, ", ".join(item.status for item in night.items), "new")
        for key in (_PIG_READINGS, _PIG_SUBDAILY):
            series = build_series(data, raw_root=raw, dataset=key)
            _expect(f"{key}: series", series.status, "new")
        catalog = build_catalog(data, raw_root=raw, provider="PIG")
        _expect("PIG-PIB station catalog", catalog.status, "new")
