"""Provider attribution of the mockup: the lines, which data need which, and how they merge.

The lines are those of Nogat's development standard, §20 (decision ECO-060), quoted byte
for byte:

- S and P: IMGW-PIB data (§5 ust. 3 and 4 of the IMGW-PIB terms);
- H: data of IMGW-PIB's hydrological service hydro.imgw.pl and its backend
  hydro-back.imgw.pl (the service's own terms, https://hydro.imgw.pl/#/regulamin);
- PS, PP and M: PMAXTP, whose own terms (https://klimat.imgw.pl/opady-maksymalne) replace
  S and P;
- C and CP: ČHMÚ (CC BY 4.0);
- then the notice N and the terms RD, RH and RK.

This module is the mockup's one place for them (DEV-20.4). Every route takes its
`attribution` and `terms_notice` fields from here (DEV-20.6, DEV-20.7), and `api/meta`
serves the same texts to the page (web/src/attribution.js).

The sources of the mockup's data:

- `imgw`: danepubliczne.imgw.pl, which gives the archives behind the series and the
  catalogs' station lists, and the current-data API behind `current hydro`, `current
  meteo`, `current synop` and the catalog locations `api_hydro` and `api_meteo`;
- `imgw-hydro`: hydro.imgw.pl, which gives the water states of `current hydro-states` and
  the locations of the package's `hydro_stations_locations.csv` (catalog `location_source`
  "static", written by `reference_data` from `fetch_hydro_states`);
- `pmaxtp`: powietrze.imgw.pl/tpmax-api, the API behind klimat.imgw.pl/opady-maksymalne;
- `chmi`: ČHMÚ series and catalogs, normalized and reformatted;
- `chmi-results`: results computed from them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

S = "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy"
P = "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone"
H = "Dane pochodzą z serwisu hydrologicznego IMGW-PIB https://hydro.imgw.pl"
PS = (
    "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy, "
    "dane pochodzą ze strony https://klimat.imgw.pl/opady-maksymalne"
)
PP = (
    "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego pochodzące ze strony "
    "https://klimat.imgw.pl/opady-maksymalne zostały przetworzone"
)
M = (
    "„Modele probabilistyczne opadów maksymalnych o określonym czasie trwania i prawdopodobieństwie "
    "przewyższenia – Projekt PMAXTP”, red. Bogdan Ozga-Zieliński, Instytut Meteorologii i Gospodarki Wodnej – "
    "Państwowy Instytut Badawczy, Warszawa 2022"
)
C = (
    "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, licencja CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)"
)
#: CP names what was done (DEV-20.3): the series and catalogs as Obserwator's own
#: processed_attribution says, the analyses with the computation added.
CP = "Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)"
CP_RESULTS = "Dane ČHMÚ zostały przetworzone (normalizacja, zmiana formatu i obliczenia)"
N = (
    "Dane IMGW-PIB można wykorzystywać nieodpłatnie do celów prywatnych (niezarobkowych). Wykorzystanie w "
    "działalności gospodarczej, na stronach z reklamami lub do celów wymienionych w regulaminie (m.in. "
    "planowanie w gospodarowaniu wodami, art. 317 Prawa wodnego) wymaga umowy z IMGW-PIB."
)
RD = "Regulamin: https://danepubliczne.imgw.pl/regulations"
RH = "Regulamin: https://hydro.imgw.pl/#/regulamin"
RK = "Regulamin: https://klimat.imgw.pl/opady-maksymalne"

LINES = {"S": S, "P": P, "H": H, "PS": PS, "PP": PP, "M": M, "C": C, "CP": CP, "CPR": CP_RESULTS}
TERMS = {"N": N, "RD": RD, "RH": RH, "RK": RK}
#: The order of the lines, each once (DEV-20.4); CPR names more than CP and replaces it.
ORDER = ("S", "P", "H", "PS", "PP", "M", "C", "CP", "CPR")
REPLACES = {"CPR": ("CP",)}
#: The notice first, then the terms that apply (DEV-20.7).
TERMS_ORDER = ("N", "RD", "RH", "RK")
#: The lines and terms of each data source.
SOURCES: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "imgw": (("S", "P"), ("N", "RD")),
    "imgw-hydro": (("S", "P", "H"), ("N", "RH")),
    "pmaxtp": (("PS", "PP", "M"), ("N", "RK")),
    "chmi": (("C", "CP"), ()),
    "chmi-results": (("C", "CPR"), ()),
}
PMAXTP_DATASET = "pl.imgw.pmaxtp"


def marks(sources: Iterable[str]) -> tuple[list[str], list[str]]:
    """The marks of the lines and of the terms that the given sources need, in order."""
    lines: set[str] = set()
    terms: set[str] = set()
    for source in sources:
        own, notice = SOURCES[source]
        lines.update(own)
        terms.update(notice)
    for mark, replaced in REPLACES.items():
        if mark in lines:
            lines.difference_update(replaced)
    return [mark for mark in ORDER if mark in lines], [mark for mark in TERMS_ORDER if mark in terms]


def fields(*sources: str) -> dict[str, list[str]]:
    """
    The `attribution` and `terms_notice` fields of a document with data of these sources.

    `terms_notice` is left out when no IMGW-PIB data are in it (ČHMÚ alone): Nogat's
    `handoff-1` schema allows no empty list.
    """
    lines, terms = marks(sources)
    out = {"attribution": [LINES[mark] for mark in lines]}
    if terms:
        out["terms_notice"] = [TERMS[mark] for mark in terms]
    return out


def dataset_sources(dataset: str, provider: str) -> tuple[str, ...]:
    """The sources of a dataset's series as the mockup serves them."""
    if dataset == PMAXTP_DATASET:
        return ("pmaxtp",)
    return ("imgw",) if provider == "IMGW-PIB" else ("chmi",)


def station_sources(
    provider: str,
    properties: Mapping[str, Any],
    *,
    location: bool = True,
    current: bool = False,
    results: bool = False,
) -> list[str]:
    """
    The sources of what the mockup shows of a station.

    An IMGW-PIB station is `imgw`. It adds `imgw-hydro` when the product shows its location
    and the location comes from hydro.imgw.pl, or, with `current`, when it is a hydrological
    station shown with its water state. A ČHMÚ station is `chmi`, or `chmi-results` once its
    data were computed on.
    """
    if provider == "IMGW-PIB":
        out = ["imgw"]
        hydro_map = location and properties.get("location_source") == "static"
        if hydro_map or (current and properties.get("kind") == "hydro"):
            out.append("imgw-hydro")
        return out
    return ["chmi-results" if results else "chmi"]


def meta() -> dict[str, Any]:
    """The texts, their order and the sources, for the page (web/src/attribution.js)."""
    return {
        "lines": {**LINES, **TERMS},
        "order": list(ORDER),
        "replaces": {mark: list(replaced) for mark, replaced in REPLACES.items()},
        "terms_order": list(TERMS_ORDER),
        "sources": {name: {"attribution": list(own), "terms_notice": list(notice)} for name, (own, notice) in SOURCES.items()},
    }


def spread(items: list[str], rows: int) -> list[str]:
    """
    One line per cell from the first row down, empty below (DEV-20.5); when the table has
    fewer rows than lines, the rest join its last cell with a newline.
    """
    if rows <= 0:
        return []
    cells = items[:rows] + [""] * max(0, rows - len(items))
    if len(items) > rows:
        cells[rows - 1] = "\n".join(items[rows - 1 :])
    return cells


def _cell(text: str) -> str:
    if any(char in text for char in ',"\r\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def with_columns(text: str, *sources: str, newline: str = "\r\n") -> str:
    """
    A CSV with the trailing columns `attribution` and `terms_notice` (DEV-20.5).

    Every row and column it had stays byte for byte. The rows are split at `newline`, so
    no cell may hold one; Obserwator's `export_series` writes none.
    """
    rows = text.split(newline)
    ends = rows[-1] == ""
    if ends:
        rows = rows[:-1]
    if not rows:
        return text
    found = fields(*sources)
    body = len(rows) - 1
    lines = spread(found["attribution"], body)
    terms = spread(found.get("terms_notice", []), body)
    out = [f"{rows[0]},attribution,terms_notice"]
    out.extend(f"{row},{_cell(lines[index])},{_cell(terms[index])}" for index, row in enumerate(rows[1:]))
    return newline.join(out) + (newline if ends else "")
