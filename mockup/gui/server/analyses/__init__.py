"""The analyses of a station, by name: hydrological (`hydro.py`) and meteorological (`meteo.py`).

Contract of an analysis (used by `server/app.py`, route `GET api/analysis/{name}`):

    def analysis(ctx: Context, params: Params) -> dict

- `ctx.store` is the `Store`, `ctx.code` the station code, `ctx.station` its catalog
  properties (dict, with `provider`, `kind`, `thresholds` for ČHMÚ hydro stations) and
  `ctx.datasets` the series datasets that hold it (`Store.datasets_of`).
- `params` holds the query string (str values); read them with `Params.int`,
  `Params.float`, `Params.choice`, which raise `BadParam` (HTTP 400) on bad input.
- The return value is JSON-ready and has at least
  `{"series_version": str, "computed_by": [provenance, …], …the analysis' own fields}`,
  each provenance from `hydrolog_bridge.call(...)["provenance"]` or
  `hydrolog_bridge.prototype(method, target)`.
- Raise `NoData(text)` (HTTP 404, the text shown in the section) when the station's
  series cannot give the analysis (too short, no Q, …).

A module registers its analyses in its `ANALYSES` dict: name -> `Analysis`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from server.store import Store


class BadParam(ValueError):
    """An option of the query string is invalid (HTTP 400)."""


class NoData(LookupError):
    """The station's data do not allow the analysis (HTTP 404, shown in the section)."""


class Params(dict[str, str]):
    """The query string, with checked readers."""

    def int(self, name: str, default: int | None = None, lo: int | None = None, hi: int | None = None) -> int | None:
        raw = self.get(name)
        if raw in (None, ""):
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise BadParam(f"{name}: not an integer") from exc
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            raise BadParam(f"{name}: outside {lo}..{hi}")
        return value

    def float(self, name: str, default: float | None = None, lo: float | None = None, hi: float | None = None) -> float | None:
        raw = self.get(name)
        if raw in (None, ""):
            return default
        try:
            value = float(raw.replace(",", "."))
        except ValueError as exc:
            raise BadParam(f"{name}: not a number") from exc
        if value != value or (lo is not None and value < lo) or (hi is not None and value > hi):
            raise BadParam(f"{name}: outside {lo}..{hi}")
        return value

    def choice(self, name: str, allowed: tuple[str, ...], default: str) -> str:
        raw = self.get(name) or default
        if raw not in allowed:
            raise BadParam(f"{name}: one of {', '.join(allowed)}")
        return raw


@dataclass(frozen=True)
class Context:
    store: Store
    code: str
    station: dict[str, Any]
    datasets: list[dict[str, Any]]

    def has(self, dataset: str, variable: str | None = None) -> bool:
        for entry in self.datasets:
            if entry["dataset"] == dataset:
                return variable is None or any(
                    name == variable or name.startswith(f"{variable}@") for name in entry["variables"]
                )
        return False


@dataclass(frozen=True)
class Analysis:
    function: Callable[[Context, Params], dict[str, Any]]
    kind: str  # "hydro" | "meteo"
    title: str  # Polish title, as the section shows it


def registry() -> dict[str, Analysis]:
    """Every analysis of both modules."""
    from server.analyses import hydro, meteo

    found: dict[str, Analysis] = {}
    for module in (hydro, meteo):
        for name, analysis in module.ANALYSES.items():
            if name in found:
                raise RuntimeError(f"analysis {name} registered twice")
            found[name] = analysis
    return found
