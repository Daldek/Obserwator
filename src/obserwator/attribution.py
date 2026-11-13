"""
The attribution lines and the terms notice that the data providers require (ADR-012).

A product is anything Obserwator shows, writes or returns with a provider's data
or with values derived from them (Nogat DEV §20, ECO-060): an envelope of a
command, a line of the CLI, an export, a stored series, catalog or PMAXTP cell, a
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
==========  ==================================================================

A verbatim copy of a provider file carries the source lines (IMGW-PIB ``S``,
PMAXTP ``PS`` and ``M``, ČHMÚ ``C``); data that were parsed, harmonised,
reformatted, aggregated or used to compute a result also carry the processed
lines (``P``, ``PP``, ``CP``); data of hydro.imgw.pl add ``H``. IMGW-PIB data of
any origin carry the terms notice ``N`` with the terms that apply (``RD``,
``RH``, ``RK``). Lines of several origins merge in the order of the standard,
each once, so equal lines of different tools merge byte for byte.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from obserwator.messages import message

__all__ = [
    "ORIGINS",
    "Attribution",
    "Origin",
    "attribution",
    "dataset_origin",
    "provider_origin",
]

Origin = Literal["imgw", "imgw_hydro", "pmaxtp", "chmi"]
"""Origin of provider data with its own attribution and terms."""
ORIGINS: tuple[Origin, ...] = ("imgw", "imgw_hydro", "pmaxtp", "chmi")
"""Every origin, in the order of their lines."""

# Plain text: the legal wordings are one text in every language.
_S = str(message("legal.imgw_attribution"))
_P = str(message("legal.imgw_processed_attribution"))
_H = str(message("legal.imgw_hydro_attribution"))
_PS = str(message("legal.pmaxtp_attribution"))
_PP = str(message("legal.pmaxtp_processed_attribution"))
_M = str(message("legal.pmaxtp_monograph"))
_C = str(message("legal.chmi_attribution"))
_CP = str(message("legal.chmi_processed_attribution"))
_N = str(message("legal.imgw_terms_notice"))
_RD = str(message("legal.imgw_terms_danepubliczne"))
_RH = str(message("legal.imgw_terms_hydro"))
_RK = str(message("legal.imgw_terms_pmaxtp"))

# The order of DEV-20.4 (attribution) and DEV-20.7 (terms notice).
_ATTRIBUTION_ORDER = (_S, _P, _H, _PS, _PP, _M, _C, _CP)
_TERMS_ORDER = (_N, _RD, _RH, _RK)
# Lines of an origin: of a verbatim copy, added by processing, the terms notice.
_LINES: dict[Origin, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "imgw": ((_S,), (_P,), (_N, _RD)),
    "imgw_hydro": ((_S, _H), (_P,), (_N, _RH)),
    "pmaxtp": ((_PS, _M), (_PP,), (_N, _RK)),
    "chmi": ((_C,), (_CP,), ()),
}
_PROVIDERS: dict[str, Origin] = {"IMGW-PIB": "imgw", "CHMI": "chmi"}
_PREFIXES: dict[str, Origin] = {"pl.imgw": "imgw", "cz.chmi": "chmi"}


def _ordered(order: tuple[str, ...], lines: Iterable[str]) -> tuple[str, ...]:
    """``lines`` once each: the known ones in ``order``, any other after them."""
    given = dict.fromkeys(lines)
    return tuple(line for line in order if line in given) + tuple(
        line for line in given if line not in order
    )


@dataclass(frozen=True)
class Attribution:
    """
    The lines a product with provider data carries (ADR-012, Nogat DEV §20).

    ``a | b`` merges two products' lines (a product made from both), each
    line once and in the order of the standard.

    Attributes
    ----------
    attribution : tuple of str
        The attribution lines in the order ``S, P, H, PS, PP, M, C, CP``;
        empty for a product without provider data.
    terms_notice : tuple of str
        The terms-of-use notice of IMGW-PIB data, ``N`` followed by the
        terms that apply (``RD``, ``RH``, ``RK``); empty without IMGW-PIB
        data.
    """

    attribution: tuple[str, ...] = ()
    terms_notice: tuple[str, ...] = ()

    def __or__(self, other: Attribution) -> Attribution:
        """The lines of both, each once, in the order of the standard."""
        return Attribution(
            _ordered(_ATTRIBUTION_ORDER, (*self.attribution, *other.attribution)),
            _ordered(_TERMS_ORDER, (*self.terms_notice, *other.terms_notice)),
        )

    def __bool__(self) -> bool:
        """Whether there is any line."""
        return bool(self.attribution or self.terms_notice)

    @property
    def lines(self) -> tuple[str, ...]:
        """The attribution lines followed by the terms notice, as a file shows them."""
        return self.attribution + self.terms_notice

    @classmethod
    def from_lines(cls, lines: Iterable[str]) -> Attribution:
        """
        Read back the lines of a file: the terms lines apart, every other line kept.

        Parameters
        ----------
        lines : iterable of str
            Lines of an ``ATTRIBUTION.txt`` or of another tool's product;
            empty lines are skipped.

        Returns
        -------
        Attribution
            The known terms lines as ``terms_notice``, the rest as
            ``attribution``, each once in the order of the standard (lines
            the standard does not know follow the known ones).
        """
        given = [line for line in lines if line]
        terms = [line for line in given if line in _TERMS_ORDER]
        return cls(
            _ordered(_ATTRIBUTION_ORDER, (line for line in given if line not in terms)),
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
    *origins : {"imgw", "imgw_hydro", "pmaxtp", "chmi"}
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
        source, extra, notice = _LINES[origin]
        lines += source + extra if processed else source
        terms += notice
    return Attribution(
        _ordered(_ATTRIBUTION_ORDER, lines), _ordered(_TERMS_ORDER, terms)
    )


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
