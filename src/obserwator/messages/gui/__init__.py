"""
Texts of the web GUI (area ``gui``, ADR-013): the page's words and the server's answers.

The page fetches the whole area in its language from ``GET api/texts?lang=pl|en`` and
names a text by its key without the area: ``t("shell.app_name")`` in JavaScript is the
entry ``gui.shell.app_name``. A key whose name ends in ``.one``, ``.few``, ``.many`` and
``.other`` is a plural: the page picks the form by ``Intl.PluralRules`` of its language
(English has no ``few`` and ``many`` and repeats ``other`` in them). Placeholders follow
``str.format`` (``{name}``; a brace that is text is ``{{`` or ``}}``), in Python and in
the page alike.

Each module of this package holds the texts of one part of the GUI; this module merges
them, and a key is in exactly one of them (``tests/unit/gui/test_texts.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from obserwator.messages import Text
from obserwator.messages.gui import (
    charts,
    hydro_levels,
    hydro_regime,
    meteo_precipitation,
    meteo_temperature,
    pmaxtp,
    public,
    sections,
    server,
    shell,
    station,
    stations,
)

_PARTS: tuple[Mapping[str, Text], ...] = (
    server.MESSAGES,
    public.MESSAGES,
    shell.MESSAGES,
    stations.MESSAGES,
    station.MESSAGES,
    pmaxtp.MESSAGES,
    sections.MESSAGES,
    charts.MESSAGES,
    hydro_levels.MESSAGES,
    hydro_regime.MESSAGES,
    meteo_precipitation.MESSAGES,
    meteo_temperature.MESSAGES,
)


def _merge(parts: tuple[Mapping[str, Text], ...]) -> Mapping[str, Text]:
    merged: dict[str, Text] = {}
    for part in parts:
        twice = sorted(set(merged) & set(part))
        if twice:
            raise ValueError(f"Keys of the area gui in two modules: {twice}")
        merged.update(part)
    return MappingProxyType(merged)


MESSAGES: Mapping[str, Text] = _merge(_PARTS)
