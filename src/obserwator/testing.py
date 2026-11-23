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
import threading
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Literal, get_args
from unittest import mock

import httpx

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
from obserwator.store.types import PathArg, StoreHandle
from obserwator.store.writer import _canonical

__all__ = ["FixtureRoots", "FixtureVariant", "build_fixture_store", "fixture_files"]

FixtureVariant = Literal[
    "complete", "corrupt", "unknown_schema", "complete_pl_cz", "groundwater"
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
    ``meteo_details_recordings.json`` (real answers of hydro.imgw.pl's backend) and
    ``contract_recordings.json`` (live endpoints of the interface contract tests),
    and ``contract_schemas.json`` (JSON Schemas with examples of the store documents
    ``obserwator-store/1`` ... ``obserwator-pmaxtp/1``, the envelope
    ``obserwator-result/1`` and the error documents ``problem+json`` and
    ``obserwator-error/1``). Data are short synthetic samples with fictional station
    codes, not real yearbooks, except the recorded answers of hydro.imgw.pl's backend
    and ČHMÚ's groundwater files: the real files of two objects with the server's
    headers, their listings and object lists cut to the real rows of them.

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

    Parameters
    ----------
    root : str or os.PathLike
        Directory of the raw root; it must not exist or be an empty directory.
    data_root : str or os.PathLike
        Directory of the data root, outside ``root``; it must not exist or be
        an empty directory.
    variant : {"complete", "corrupt", "unknown_schema", "complete_pl_cz", "groundwater"}, optional
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
    elif variant in ("complete_pl_cz", "groundwater"):
        _add_chmu(raw, data, groundwater=variant == "groundwater")
    return FixtureRoots(raw, data)
