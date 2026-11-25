"""
The attribution lines and the terms lines that the data providers require (ADR-012).

A product is anything Obserwator shows, writes or returns with a provider's data
or with values derived from them (Nogat DEV §20, ECO-060, ECO-065): an envelope of
a command, a line of the CLI, an export, a stored series, catalog or PMAXTP cell, a
plain download, a web page. Every product takes its lines from here, and the
texts come from the one catalog area ``legal`` (`obserwator.messages.legal`):

============  ================================================================
Origin        Data
============  ================================================================
imgw          IMGW-PIB archives and current data of danepubliczne.imgw.pl
imgw_hydro    operational data, station locations and station details of
              hydro.imgw.pl (and of its backend hydro-back.imgw.pl)
pmaxtp        PMAXTP of powietrze.imgw.pl and klimat.imgw.pl (own terms)
chmu          ČHMÚ open data (CC BY 4.0)
pig           PIG-PIB's groundwater monitoring of cbdgmapa.pgi.gov.pl (CC BY 4.0 by
              dane.gov.pl's dataset 170, ADR-035): W with the period and the date of
              each product, WP, and its terms line RW
gugik         the state border of Poland from PRG of GUGiK (ADR-018)
cuzk          the state border of Czechia from RÚIAN of ČÚZK (CC BY 4.0, ADR-018)
gdanskiewody  Gdańskie Wody's measurements of pomiary.gdanskiewody.pl (ADR-034):
              drafts of its lines while its terms are unknown (`provisional`)
============  ================================================================

A verbatim copy of a provider file carries the source lines (IMGW-PIB ``S``,
PMAXTP ``PS`` and ``M``, ČHMÚ ``C``, PIG-PIB ``W``); data that were parsed,
harmonised, reformatted, aggregated or used to compute a result also carry the
processed lines (``P``, ``PP``, ``CP``, ``WP``). The packaged borders are always
processed data (simplified), and their one line each, GUGiK's ``G`` and ČÚZK's ``Z``,
names the product and the days of the packaged file (`obserwator._borders`) and says so.
IMGW-PIB data of any origin carry the links to the terms that apply (``RD``, ``RH``,
``RK``), PIG-PIB's data the link to PIG-PIB's terms of reuse (``RW``), never a summary
of them. Lines of several origins merge in the order of the standard, each once, so
equal lines of different tools merge byte for byte.

PIG-PIB's W names when the data were created and acquired (Nogat DEV-20.13, in G's
forms): ``<period>`` the year of the readings or hours of the product, or the first and
the last joined by an en dash, and ``<date>`` the day of the capture its data come
from, or the first and the last joined by a spaced en dash. Each product fills them
(`attribution` with ``period`` and ``date``, `years_text`, `days_text`); W lines of
several products merge into one W spanning them all, and a W left unfilled (the
placeholders of the table, only where a product names no data) gives way to a filled one.

A stored product (a series, catalog or analysis written before ECO-065) may hold lines
the standard has retired: `carried` derives the lines of a stored product from the
origins of its data and keeps only another tool's own lines from what was stored. A
product written before ECO-071 may hold CP with the processing in parentheses („Dane
ČHMÚ zostały przetworzone (…)”, of Obserwator or of Hydrolog): every `Attribution`
holds it as CP, once.

A provider fed by files (ADR-033) declares its own origin, named by its acronym, with
the line of its provider file and its optional processed line (`declare_origin`): its
lines follow every line of the standard (S … Z), in the order the deployment declares
them, its text before its processed line (DEV-20.4 and Nogat's table of provider lines,
P9).

A provider of the class ``other`` (Nogat plan 2026-11-20, P8, P11; Gdańskie Wody and
every provider fed by files) has one more line after its own: its notice that the data
do not come from a national hydro-meteorological service (and, in the provider's words,
that they are unverified where it says so). It is no line of DEV §20, yet every product
with the provider's data carries it beside them, so a file keeps the distinction after
it leaves the GUI. Gdańskie Wody's lines are drafts until its terms are known
(`provisional`, ADR-034): no server serves its data.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from functools import cache
from typing import TYPE_CHECKING

from obserwator._borders import CZECHIA, POLAND, border
from obserwator.messages import localize, message
from obserwator.messages.legal import RETIRED_LINES

if TYPE_CHECKING:
    from obserwator.providers import ProviderAdapter

__all__ = [
    "ORIGINS",
    "Attribution",
    "Origin",
    "attribution",
    "border_origin",
    "carried",
    "dataset_origin",
    "dataset_origins",
    "days_text",
    "declare_origin",
    "fill",
    "fillable",
    "filled",
    "origins",
    "provider_origin",
    "provisional",
    "years_text",
]

Origin = str
"""
Origin of provider data with its own attribution and terms: one of `ORIGINS` or the
acronym of a provider fed by files (`declare_origin`).
"""
ORIGINS: tuple[Origin, ...] = (
    "imgw",
    "imgw_hydro",
    "pmaxtp",
    "chmu",
    "pig",
    "gugik",
    "cuzk",
    "gdanskiewody",
)
"""Every origin of the packaged providers and borders, in the order of their lines."""

# Plain text: the legal wordings are one text in every language.
_S = str(message("legal.imgw_attribution"))
_P = str(message("legal.imgw_processed_attribution"))
_PS = str(message("legal.pmaxtp_attribution"))
_PP = str(message("legal.pmaxtp_processed_attribution"))
_M = str(message("legal.pmaxtp_monograph"))
_C = str(message("legal.chmu_attribution"))
_CP = str(message("legal.chmu_processed_attribution"))
_RD = str(message("legal.imgw_terms_danepubliczne"))
_RH = str(message("legal.imgw_terms_hydro"))
_RK = str(message("legal.imgw_terms_pmaxtp"))
# PIG-PIB (ADR-035, Nogat DEV-20.13): W in the form of the table, its placeholders
# kept, WP and RW.
_W = str(message("legal.pig_attribution", period="<period>", date="<date>"))
_WP = str(message("legal.pig_processed_attribution"))
_RW = str(message("legal.pig_terms"))
# Gdańskie Wody (ADR-034): drafts of its line, its processed line and its terms line,
# and P8's notice of a provider of the class "other" in its words (always Polish).
_GW = str(message("legal.gdanskiewody_attribution"))
_GWP = str(message("legal.gdanskiewody_processed_attribution"))
_GWN = localize(message("datasets.source_notice_gdanskiewody"), "pl")
_RG = str(message("legal.gdanskiewody_terms"))
# PIG-PIB's P8 notice of the class "other", after its lines (always Polish).
_WN = localize(message("datasets.source_notice_pig"), "pl")

# A filled W: its period (a year, or two joined by an en dash) and its date (a day, or
# two joined by a spaced en dash) in the places of the table's placeholders.
_W_FILLED = re.compile(
    re.escape(_W)
    .replace(re.escape("<period>"), r"(?P<period>[0-9]{4}(?:–[0-9]{4})?)")
    .replace(
        re.escape("<date>"),
        r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2}(?: – [0-9]{4}-[0-9]{2}-[0-9]{2})?)",
    )
)

# The order of DEV-20.7 (terms lines); `_attribution_order` gives that of DEV-20.4.
_TERMS_ORDER = (_RD, _RH, _RK, _RW, _RG)
# Lines earlier versions of the standard required (ECO-065), never carried on.
_RETIRED = frozenset(RETIRED_LINES)
# CP of a product written before ECO-071 began so and named the processing in
# parentheses after it (DEV-20.4).
_OLD_CP = f"{_CP} ("
# Lines of an origin with fixed texts: of a verbatim copy, added by processing, the
# terms lines.
_LINES: dict[Origin, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "imgw": ((_S,), (_P,), (_RD,)),
    "imgw_hydro": ((_S,), (_P,), (_RH,)),
    "pmaxtp": ((_PS, _M), (_PP,), (_RK,)),
    "chmu": ((_C,), (_CP,), ()),
    # W with its placeholders: `attribution` fills them per product (ADR-035). P8's
    # notice of the class "other" follows the lines, verbatim or processed.
    "pig": ((_W, _WN), (_WP,), (_RW,)),
    # P8's notice is carried with the data, verbatim or processed, after the lines.
    "gdanskiewody": ((_GW, _GWN), (_GWP,), (_RG,)),
}
# The origins whose lines are drafts: the provider's terms, and so the wording they
# require, are not known yet (ADR-034). No server serves the data of such an origin.
_PROVISIONAL: frozenset[Origin] = frozenset({"gdanskiewody"})
# The origin of the data of each packaged border.
_BORDER_ORIGINS: dict[str, Origin] = {POLAND: "gugik", CZECHIA: "cuzk"}
# The origins of the providers fed by files, in the order the deployment declares them
# (`declare_origin`), with their lines as in `_LINES`.
_DECLARED: dict[Origin, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {}


def declare_origin(
    origin: Origin,
    line: str,
    processed: str | None = None,
    notice: str | None = None,
) -> None:
    """
    Declare the origin of a provider fed by files and its lines (ADR-033).

    The registry calls this once for each provider file as it is imported; its lines
    follow every line of the standard in `attribution` and every merge.

    Parameters
    ----------
    origin : str
        The provider's acronym: no origin of `ORIGINS` and none declared before.
    line : str
        The line every product with its data carries.
    processed : str or None, optional
        The line a product of its processed data carries after ``line``.
    notice : str or None, optional
        P8's notice of a provider of the class ``other`` (its adapter's
        ``source_notice`` in Polish), which every product with its data carries after
        its lines, verbatim or processed.

    Raises
    ------
    ValueError
        If ``origin`` is taken (a program error: the registry checks the ids).
    """
    if origin in ORIGINS or origin in _DECLARED:
        raise ValueError(f"The origin {origin!r} is taken")
    _DECLARED[origin] = (
        (line, notice) if notice else (line,),
        (processed,) if processed else (),
        (),
    )
    _attribution_order.cache_clear()


def origins() -> tuple[Origin, ...]:
    """
    Every origin: those of `ORIGINS`, then those of the providers fed by files.

    Returns
    -------
    tuple of str
        The origins in the order of their lines.
    """
    return ORIGINS + tuple(_DECLARED)


def provisional(origin: Origin, /) -> bool:
    """
    Whether the lines of an origin are drafts: its provider's terms are not known yet.

    Gdańskie Wody's regulamin is shown only to a signed-in user (ADR-034, the providers
    plan's question 1): its line, processed line and terms line are drafts until the
    terms give their wording. Its data are stored and read by the CLI and the library
    with these drafts, and no server serves them (`obserwator.instance`).

    Parameters
    ----------
    origin : str
        An origin of `origins`.

    Returns
    -------
    bool
        True for an origin whose lines are drafts; False for every other.
    """
    return origin in _PROVISIONAL


@cache
def _border_lines() -> dict[Origin, str]:
    """G of PRG and Z of RÚIAN, with the products and days of the packaged borders."""
    poland, czechia = border(POLAND), border(CZECHIA)
    return {
        "gugik": str(
            message(
                "legal.gugik_attribution",
                products=poland.product,
                period=poland.created[:4],
                date=poland.acquired,
            )
        ),
        "cuzk": str(
            message(
                "legal.cuzk_attribution",
                products=czechia.product,
                date=czechia.acquired,
            )
        ),
    }


@cache
def _attribution_order() -> tuple[str, ...]:
    """
    The attribution lines in the order of DEV-20.4: S, P, PS, PP, M, C, CP, W, WP, G, Z.

    PIG-PIB's P8 notice follows WP (a filled W takes the place of the table's W,
    `_key`). Gdańskie Wody's drafts follow (Nogat's table of provider lines holds no row
    of it yet), then the lines of the providers fed by files, in the order they were
    declared (`declare_origin`): of each its text, its processed line, then P8's
    notice of its class, each line once.
    """
    borders = _border_lines()
    after = tuple(
        line
        for source, extra, _ in (_LINES["gdanskiewody"], *_DECLARED.values())
        for line in (*source[:1], *extra, *source[1:])
    )
    return tuple(
        dict.fromkeys(
            (
                _S,
                _P,
                _PS,
                _PP,
                _M,
                _C,
                _CP,
                _W,
                _WP,
                _WN,
                borders["gugik"],
                borders["cuzk"],
                *after,
            )
        )
    )


def _lines(origin: Origin) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Lines of an origin: of a verbatim copy, added by processing, the terms lines."""
    fixed = _LINES.get(origin) or _DECLARED.get(origin)
    return fixed if fixed is not None else ((_border_lines()[origin],), (), ())


def _key(line: str) -> str:
    """The place of a line in the order: a filled W takes the place of the table's W."""
    return _W if _W_FILLED.fullmatch(line) else line


def _ordered(order: tuple[str, ...], lines: Iterable[str]) -> tuple[str, ...]:
    """``lines`` once each: the known ones in ``order``, any other after them."""
    given = dict.fromkeys(lines)
    places = {line: index for index, line in enumerate(order)}
    known = sorted(
        (line for line in given if _key(line) in places),
        key=lambda line: places[_key(line)],
    )
    return tuple(known) + tuple(line for line in given if _key(line) not in places)


def _merged_w(lines: Iterable[str]) -> str:
    """
    One W of several: the years and the days of every filled one, first to last.

    The table's W (its placeholders) gives way to any filled W; alone it stays.
    """
    years: set[int] = set()
    days: set[date] = set()
    for line in lines:
        found = _W_FILLED.fullmatch(line)
        if found is None:
            continue
        years.update(int(year) for year in found["period"].split("–"))
        days.update(date.fromisoformat(day) for day in found["date"].split(" – "))
    if not years:
        return _W
    return _filled_w(years_text(years), days_text(days))


def _canonical(lines: Iterable[str]) -> tuple[str, ...]:
    """
    ``lines`` once each: an old CP with the processing in parentheses as CP, every W one.

    W lines of several products merge into one, in the place of the first (`_merged_w`).
    """
    unique = dict.fromkeys(
        _CP if line.startswith(_OLD_CP) and line.endswith(")") else line
        for line in lines
    )
    pig = [line for line in unique if _key(line) == _W]
    if len(pig) < 2:
        return tuple(unique)
    merged = _merged_w(pig)
    kept: list[str] = []
    for line in unique:
        if line not in pig:
            kept.append(line)
        elif merged not in kept:
            kept.append(merged)
    return tuple(kept)


def years_text(years: Iterable[int], /) -> str:
    """
    ``<period>`` of PIG-PIB's W (G's form): a year, or the first and the last.

    Parameters
    ----------
    years : iterable of int
        The years of the readings or hours of a product.

    Returns
    -------
    str
        ``"2026"``, or ``"2025–2026"`` joined by an en dash.

    Raises
    ------
    ValueError
        If ``years`` is empty.
    """
    found = sorted(set(years))
    if not found:
        raise ValueError("A period needs at least one year")
    first, last = found[0], found[-1]
    return str(first) if first == last else f"{first}–{last}"


def days_text(days: Iterable[date], /) -> str:
    """
    ``<date>`` of PIG-PIB's W (G's form): a day, or the first and the last.

    Parameters
    ----------
    days : iterable of datetime.date
        The days of the captures a product's data come from.

    Returns
    -------
    str
        ``"2026-11-24"``, or ``"2026-11-24 – 2026-12-01"`` joined by a spaced en dash.

    Raises
    ------
    ValueError
        If ``days`` is empty.
    """
    found = sorted(set(days))
    if not found:
        raise ValueError("A date needs at least one day")
    first, last = found[0].isoformat(), found[-1].isoformat()
    return first if first == last else f"{first} – {last}"


def _filled_w(period: str, day: str) -> str:
    """PIG-PIB's W with its period and date (`years_text`, `days_text`)."""
    line = str(message("legal.pig_attribution", period=period, date=day))
    if not _W_FILLED.fullmatch(line):
        raise ValueError(f"Invalid period {period!r} or date {day!r} of W")
    return line


def fillable(formula: str, /) -> bool:
    """
    Whether a license formula has placeholders each product fills (PIG-PIB's W).

    Parameters
    ----------
    formula : str
        The attribution formula of a dataset's license (`obserwator.datasets.License`).

    Returns
    -------
    bool
        True for PIG-PIB's W with ``<period>`` and ``<date>`` (ADR-035).
    """
    return formula == _W


def fill(formula: str, /, *, period: str, date: str) -> str:
    """
    A license formula with its placeholders filled: the ``attribution`` of a sidecar.

    Parameters
    ----------
    formula : str
        The attribution formula of a dataset's license.
    period, date : str
        The years of the version's data (`years_text`) and the days of the captures
        it comes from (`days_text`).

    Returns
    -------
    str
        PIG-PIB's W with its period and date; any other formula unchanged.

    Raises
    ------
    ValueError
        If ``period`` or ``date`` is not in G's form.
    """
    return _filled_w(period, date) if fillable(formula) else formula


def filled(lines: Iterable[str], /) -> tuple[str, ...]:
    """
    PIG-PIB's W lines among ``lines`` whose period and date are filled.

    Parameters
    ----------
    lines : iterable of str
        Lines a product holds, e.g. those of an ``ATTRIBUTION.txt``.

    Returns
    -------
    tuple of str
        The filled W lines, in the order given.
    """
    return tuple(line for line in lines if _W_FILLED.fullmatch(line))


# „Regulamin <whose terms>: <address>”: the first word of every terms line (DEV §20).
_TERMS_WORD = _RD.split(" ", 1)[0] + " "


def _is_terms(line: str) -> bool:
    """Whether a line is a terms line: one of the standard's or of its form."""
    return line in _TERMS_ORDER or (line.startswith(_TERMS_WORD) and ": " in line)


@dataclass(frozen=True)
class Attribution:
    """
    The lines a product with provider data carries (ADR-012, Nogat DEV §20).

    ``a | b`` merges two products' lines (a product made from both), each
    line once and in the order of the standard. The attribution lines are kept
    once each, and a CP written before ECO-071 („Dane ČHMÚ zostały przetworzone
    (…)”) becomes the canonical CP (DEV-20.4).

    Attributes
    ----------
    attribution : tuple of str
        The attribution lines in the order ``S, P, PS, PP, M, C, CP, G, Z``;
        empty for a product without provider data.
    terms_notice : tuple of str
        The links to the terms of IMGW-PIB data that apply (``RD``, ``RH``,
        ``RK``); empty without IMGW-PIB data.
    """

    attribution: tuple[str, ...] = ()
    terms_notice: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Hold an old CP as CP, each attribution line once (DEV-20.4, ECO-071)."""
        object.__setattr__(self, "attribution", _canonical(self.attribution))

    def __or__(self, other: Attribution) -> Attribution:
        """The lines of both, each once, in the order of the standard."""
        return Attribution(
            _ordered(_attribution_order(), (*self.attribution, *other.attribution)),
            _ordered(_TERMS_ORDER, (*self.terms_notice, *other.terms_notice)),
        )

    def __bool__(self) -> bool:
        """Whether there is any line."""
        return bool(self.attribution or self.terms_notice)

    @property
    def lines(self) -> tuple[str, ...]:
        """The attribution lines followed by the terms lines, as a file shows them."""
        return self.attribution + self.terms_notice

    @classmethod
    def from_lines(cls, lines: Iterable[str]) -> Attribution:
        """
        Read back the lines of a file: the terms lines apart, every other line kept.

        Parameters
        ----------
        lines : iterable of str
            Lines of an ``ATTRIBUTION.txt`` or of another tool's product;
            empty lines and lines the standard retired (ECO-065) are skipped.

        Returns
        -------
        Attribution
            The terms lines („Regulamin <whose terms>: <address>”) as
            ``terms_notice``, the rest as ``attribution``, each once in the
            order of the standard (lines the standard does not know follow the
            known ones).
        """
        given = [line for line in lines if line and line not in _RETIRED]
        terms = [line for line in given if _is_terms(line)]
        return cls(
            _ordered(
                _attribution_order(), (line for line in given if line not in terms)
            ),
            _ordered(_TERMS_ORDER, terms),
        )

    def fields(self) -> dict[str, list[str]]:
        """
        The fields of a JSON document with these lines (Nogat DEV-20.6, DEV-20.7).

        Returns
        -------
        dict of str to list of str
            ``attribution`` and, when there are terms, ``terms_notice``; empty
            for an empty `Attribution`.
        """
        fields: dict[str, list[str]] = {}
        if self.attribution:
            fields["attribution"] = list(self.attribution)
        if self.terms_notice:
            fields["terms_notice"] = list(self.terms_notice)
        return fields


def attribution(
    *origins: Origin,
    processed: bool = True,
    period: str | None = None,
    date: str | None = None,
) -> Attribution:
    """
    The lines of a product made with data of the given origins.

    Parameters
    ----------
    *origins : {"imgw", "imgw_hydro", "pmaxtp", "chmu", "pig", "gugik", "cuzk"}
        Origins of the data in the product; none gives an empty `Attribution`.
    processed : bool, optional
        Whether the data were processed in any way (parsed, harmonised,
        reformatted, aggregated, used to compute a result); False only for a
        verbatim copy of a provider file.
    period, date : str or None, optional
        PIG-PIB's W: the years of the product's readings or hours (`years_text`) and
        the days of the captures its data come from (`days_text`), both or neither;
        without them W keeps the placeholders of the table, which a filled W of a
        merged product replaces.

    Returns
    -------
    Attribution
        The merged lines of every origin.

    Raises
    ------
    ValueError
        If only one of ``period`` and ``date`` is given, or either is not in G's form.

    Examples
    --------
    >>> attribution("imgw").attribution[-1]
    'Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone'
    >>> attribution("chmu", processed=False).terms_notice
    ()
    """
    if (period is None) != (date is None):
        raise ValueError("PIG-PIB's W needs both its period and its date")
    pig = _W if period is None or date is None else _filled_w(period, date)
    lines: list[str] = []
    terms: list[str] = []
    for origin in origins:
        source, extra, notice = _lines(origin)
        lines += source + extra if processed else source
        terms += notice
    return Attribution(
        _ordered(_attribution_order(), (pig if line == _W else line for line in lines)),
        _ordered(_TERMS_ORDER, terms),
    )


def carried(
    stored: Attribution, *origins: Origin, processed: bool = True
) -> Attribution:
    """
    The lines of a stored product, derived from the origins of its data.

    A series, catalog or analysis result keeps the lines it was written with, and
    those of a product stored before ECO-065 are partly retired (H, N, the terms
    lines before they named their terms). The lines of its data are derived anew
    from their origins; of what was stored only the attribution lines another tool
    added and the standard does not derive stay (DEV-20.6). Hydrolog's ČHMÚ line
    naming its computation, of a result stored before ECO-071, is CP (`Attribution`).
    Stored terms lines never stay: they are derived.

    Parameters
    ----------
    stored : Attribution
        The lines the stored product holds.
    *origins : {"imgw", "imgw_hydro", "pmaxtp", "chmu", "gugik", "cuzk"}
        Origins of the data in the product.
    processed : bool, optional
        Whether the data were processed (see `attribution`).

    Returns
    -------
    Attribution
        The derived lines and another tool's own attribution lines, each once in
        the order of the standard.

    Examples
    --------
    >>> old = Attribution(("Dane pochodzą z serwisu hydrologicznego IMGW-PIB "
    ...     "https://hydro.imgw.pl",), ("Regulamin: https://hydro.imgw.pl/#/regulamin",))
    >>> carried(old, "imgw") == attribution("imgw")
    True
    """
    derived = attribution(*origins, processed=processed)
    known = frozenset(_attribution_order())
    own = tuple(
        line
        for line in stored.attribution
        if line not in known and line not in _RETIRED and not _is_terms(line)
    )
    return derived | Attribution(own)


def dataset_origin(key: str, /) -> Origin:
    """
    Origin of the data of a dataset.

    Parameters
    ----------
    key : str
        Full dataset key, e.g. ``"pl.imgw.hydro_daily"``.

    Returns
    -------
    {"imgw", "imgw_hydro", "pmaxtp", "chmu"}
        The origin the adapter of the provider of the key's prefix gives
        (`ProviderAdapter.dataset_origin`): ``"pmaxtp"`` for ``pl.imgw.pmaxtp``,
        ``"imgw_hydro"`` for the station details of hydro.imgw.pl
        (``pl.imgw.hydro_details``), ``"imgw"`` for the other ``pl.imgw.*`` keys
        and ``"chmu"`` for ``cz.chmu.*``.

    Raises
    ------
    ValueError
        If the key belongs to no known provider (a program error: keys come
        from the registry).
    """
    from obserwator.datasets import providers

    prefix = key.rpartition(".")[0]
    for provider in providers():
        if provider.key_prefix == prefix:
            return provider.adapter.dataset_origin(key)
    raise ValueError(f"No attribution for the dataset {key!r}")


def dataset_origins(key: str, /) -> tuple[Origin, ...]:
    """
    Origins of the data of a dataset: those of its inputs for a sub-daily series.

    A sub-daily series (``DatasetDescriptor.inputs``, ADR-031) holds the data of
    every dataset it is built from, so its lines are theirs: ``pl.imgw.hydro_subdaily``
    has IMGW-PIB's telemetry (``imgw``) and hydro.imgw.pl's hours (``imgw_hydro``).

    Parameters
    ----------
    key : str
        Full dataset key, e.g. ``"pl.imgw.hydro_subdaily"``.

    Returns
    -------
    tuple of Origin
        The origins of the inputs once each, in the order of `ORIGINS`; for any
        other dataset its one `dataset_origin`.

    Raises
    ------
    ValueError
        If the key belongs to no known provider (a program error: keys come
        from the registry).
    """
    from obserwator.datasets import datasets

    descriptor = next((item for item in datasets() if item.key == key), None)
    if descriptor is None or descriptor.inputs is None:
        return (dataset_origin(key),)
    found = {dataset_origin(item) for item in descriptor.inputs}
    return tuple(origin for origin in origins() if origin in found)


def provider_origin(provider: str, /) -> Origin:
    """
    Origin of the station and archive data of a provider.

    Parameters
    ----------
    provider : str
        Provider identifier, ``"IMGW"`` or ``"CHMU"``.

    Returns
    -------
    {"imgw", "chmu"}
        The origin of the provider's archives and station lists.

    Raises
    ------
    ValueError
        If the provider is unknown (a program error: identifiers come from the
        registry).
    """
    return _adapter(provider).origin


def border_origin(provider: str, /) -> Origin:
    """
    Origin of the state border a provider's station locations are checked against.

    A station catalog keeps a location only inside its provider's country (ADR-018),
    so the catalog and every product of it carry the lines of that border too.

    Parameters
    ----------
    provider : str
        Provider identifier, ``"IMGW"`` or ``"CHMU"``.

    Returns
    -------
    {"gugik", "cuzk"}
        ``"gugik"`` (Poland, PRG) for IMGW-PIB, ``"cuzk"`` (Czechia, RÚIAN) for ČHMÚ.

    Raises
    ------
    ValueError
        If the provider is unknown (a program error: identifiers come from the
        registry).
    """
    return _BORDER_ORIGINS[_adapter(provider).border]


def _adapter(provider: str) -> ProviderAdapter:
    """The adapter of a provider by its identifier; `ValueError` for an unknown one."""
    from obserwator.datasets import providers

    for item in providers():
        if item.id == provider:
            return item.adapter
    raise ValueError(f"No attribution for the provider {provider!r}")
