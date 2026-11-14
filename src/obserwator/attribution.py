"""
The attribution lines and the terms lines that the data providers require (ADR-012).

A product is anything Obserwator shows, writes or returns with a provider's data
or with values derived from them (Nogat DEV §20, ECO-060, ECO-065): an envelope of
a command, a line of the CLI, an export, a stored series, catalog or PMAXTP cell, a
plain download, a web page. Every product takes its lines from here, and the
texts come from the one catalog area ``legal`` (`obserwator.messages.legal`):

==========  ==================================================================
Origin      Data
==========  ==================================================================
imgw        IMGW-PIB archives and current data of danepubliczne.imgw.pl
imgw_hydro  operational data and station locations of hydro.imgw.pl (and of
            its backend hydro-back.imgw.pl)
pmaxtp      PMAXTP of powietrze.imgw.pl and klimat.imgw.pl (own terms)
chmi        ČHMÚ open data (CC BY 4.0)
gugik       the state border of Poland from PRG of GUGiK (ADR-018)
cuzk        the state border of Czechia from RÚIAN of ČÚZK (CC BY 4.0, ADR-018)
==========  ==================================================================

A verbatim copy of a provider file carries the source lines (IMGW-PIB ``S``,
PMAXTP ``PS`` and ``M``, ČHMÚ ``C``); data that were parsed, harmonised,
reformatted, aggregated or used to compute a result also carry the processed
lines (``P``, ``PP``, ``CP``). The packaged borders are always processed data
(simplified), and their one line each, GUGiK's ``G`` and ČÚZK's ``Z``, names the
product and the days of the packaged file (`obserwator._borders`) and says so. IMGW-PIB
data of any origin carry the links to the terms that apply (``RD``, ``RH``, ``RK``),
never a summary of them. Lines of several origins merge in the order of the standard,
each once, so equal lines of different tools merge byte for byte.

A stored product (a series, catalog or analysis written before ECO-065) may hold lines
the standard has retired: `carried` derives the lines of a stored product from the
origins of its data and keeps only another tool's own lines from what was stored.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from typing import Literal

from obserwator._borders import CZECHIA, POLAND, PROVIDERS, border
from obserwator.messages import message
from obserwator.messages.legal import RETIRED_LINES

__all__ = [
    "ORIGINS",
    "Attribution",
    "Origin",
    "attribution",
    "border_origin",
    "carried",
    "dataset_origin",
    "provider_origin",
]

Origin = Literal["imgw", "imgw_hydro", "pmaxtp", "chmi", "gugik", "cuzk"]
"""Origin of provider data with its own attribution and terms."""
ORIGINS: tuple[Origin, ...] = ("imgw", "imgw_hydro", "pmaxtp", "chmi", "gugik", "cuzk")
"""Every origin, in the order of their lines."""

# Plain text: the legal wordings are one text in every language.
_S = str(message("legal.imgw_attribution"))
_P = str(message("legal.imgw_processed_attribution"))
_PS = str(message("legal.pmaxtp_attribution"))
_PP = str(message("legal.pmaxtp_processed_attribution"))
_M = str(message("legal.pmaxtp_monograph"))
_C = str(message("legal.chmi_attribution"))
_CP = str(message("legal.chmi_processed_attribution"))
_RD = str(message("legal.imgw_terms_danepubliczne"))
_RH = str(message("legal.imgw_terms_hydro"))
_RK = str(message("legal.imgw_terms_pmaxtp"))

# The order of DEV-20.7 (terms lines); `_attribution_order` gives that of DEV-20.4.
_TERMS_ORDER = (_RD, _RH, _RK)
# Lines earlier versions of the standard required (ECO-065), never carried on.
_RETIRED = frozenset(RETIRED_LINES)
# Lines of an origin with fixed texts: of a verbatim copy, added by processing, the
# terms lines.
_LINES: dict[Origin, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "imgw": ((_S,), (_P,), (_RD,)),
    "imgw_hydro": ((_S,), (_P,), (_RH,)),
    "pmaxtp": ((_PS, _M), (_PP,), (_RK,)),
    "chmi": ((_C,), (_CP,), ()),
}
_PROVIDERS: dict[str, Origin] = {"IMGW-PIB": "imgw", "CHMI": "chmi"}
_PREFIXES: dict[str, Origin] = {"pl.imgw": "imgw", "cz.chmi": "chmi"}
# The origin of the data of each packaged border.
_BORDER_ORIGINS: dict[str, Origin] = {POLAND: "gugik", CZECHIA: "cuzk"}


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
    """The attribution lines in the order of DEV-20.4: S, P, PS, PP, M, C, CP, G, Z."""
    borders = _border_lines()
    return (_S, _P, _PS, _PP, _M, _C, _CP, borders["gugik"], borders["cuzk"])


def _lines(origin: Origin) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Lines of an origin: of a verbatim copy, added by processing, the terms lines."""
    fixed = _LINES.get(origin)
    return fixed if fixed is not None else ((_border_lines()[origin],), (), ())


def _ordered(order: tuple[str, ...], lines: Iterable[str]) -> tuple[str, ...]:
    """``lines`` once each: the known ones in ``order``, any other after them."""
    given = dict.fromkeys(lines)
    return tuple(line for line in order if line in given) + tuple(
        line for line in given if line not in order
    )


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
    line once and in the order of the standard.

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


def attribution(*origins: Origin, processed: bool = True) -> Attribution:
    """
    The lines of a product made with data of the given origins.

    Parameters
    ----------
    *origins : {"imgw", "imgw_hydro", "pmaxtp", "chmi", "gugik", "cuzk"}
        Origins of the data in the product; none gives an empty `Attribution`.
    processed : bool, optional
        Whether the data were processed in any way (parsed, harmonised,
        reformatted, aggregated, used to compute a result); False only for a
        verbatim copy of a provider file.

    Returns
    -------
    Attribution
        The merged lines of every origin.

    Examples
    --------
    >>> attribution("imgw").attribution[-1]
    'Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone'
    >>> attribution("chmi", processed=False).terms_notice
    ()
    """
    lines: list[str] = []
    terms: list[str] = []
    for origin in origins:
        source, extra, notice = _lines(origin)
        lines += source + extra if processed else source
        terms += notice
    return Attribution(
        _ordered(_attribution_order(), lines), _ordered(_TERMS_ORDER, terms)
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
    added and the standard does not derive stay, e.g. Hydrolog's ČHMÚ line naming
    its computation (DEV-20.6). Stored terms lines never stay: they are derived.

    Parameters
    ----------
    stored : Attribution
        The lines the stored product holds.
    *origins : {"imgw", "imgw_hydro", "pmaxtp", "chmi", "gugik", "cuzk"}
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
    {"imgw", "pmaxtp", "chmi"}
        ``"pmaxtp"`` for ``pl.imgw.pmaxtp``, ``"imgw"`` for the other
        ``pl.imgw.*`` keys and ``"chmi"`` for ``cz.chmi.*``.

    Raises
    ------
    ValueError
        If the key belongs to no known provider (a program error: keys come
        from the registry).
    """
    if key == "pl.imgw.pmaxtp":
        return "pmaxtp"
    try:
        return _PREFIXES[key.rpartition(".")[0]]
    except KeyError:
        raise ValueError(f"No attribution for the dataset {key!r}") from None


def provider_origin(provider: str, /) -> Origin:
    """
    Origin of the station and archive data of a provider.

    Parameters
    ----------
    provider : str
        Provider identifier, ``"IMGW-PIB"`` or ``"CHMI"``.

    Returns
    -------
    {"imgw", "chmi"}
        The origin of the provider's archives and station lists.

    Raises
    ------
    ValueError
        If the provider is unknown (a program error: identifiers come from the
        registry).
    """
    try:
        return _PROVIDERS[provider]
    except KeyError:
        raise ValueError(f"No attribution for the provider {provider!r}") from None


def border_origin(provider: str, /) -> Origin:
    """
    Origin of the state border a provider's station locations are checked against.

    A station catalog keeps a location only inside its provider's country (ADR-018),
    so the catalog and every product of it carry the lines of that border too.

    Parameters
    ----------
    provider : str
        Provider identifier, ``"IMGW-PIB"`` or ``"CHMI"``.

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
    try:
        return _BORDER_ORIGINS[PROVIDERS[provider]]
    except KeyError:
        raise ValueError(f"No attribution for the provider {provider!r}") from None
