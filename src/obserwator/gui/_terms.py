"""
The regulamin of a public GUI (Nogat DEV-15.7): the kit's terms filled for the deployment.

A port of ``fill`` of Nogat's ``scripts/terms.py`` (the reference of the filling,
``design/README.md`` "Kit"): first the blocks, between ``<!-- block: <name> -->`` and
``<!-- /block -->`` lines, are kept for Obserwator's data sources and dropped
otherwise; then every ``{{name}}`` becomes its value, HTML-escaped. A field without a
value, or a ``{{`` left, means no page and no link.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from obserwator.gui._config import GuiConfig
from obserwator.messages import message

_LOG = logging.getLogger(__name__)

BLOCKS: tuple[str, ...] = ("imgw", "imgw-hydro", "pmaxtp", "chmi", "gugik", "cuzk")
"""The blocks of Obserwator's data sources, the packaged borders of PRG (GUGiK) and
RÚIAN (ČÚZK) among them (ADR-018); ``osm`` joins them with a basemap."""
KNOWN_BLOCKS: frozenset[str] = frozenset(
    {
        "imgw",
        "imgw-hydro",
        "pmaxtp",
        "chmi",
        "gugik",
        "cuzk",
        "copernicus",
        "isric",
        "wody-polskie",
        "osm",
    }
)
"""The blocks a GUI may list (Nogat's ``BLOCKS``, kit 0.6.2)."""
PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "service_name",
        "service_url",
        "operator_name",
        "operator_email",
        "terms_effective",
        "processor",
        "processor_transfer",
        "processor_cookie",
        "mail_provider",
        "mail_transfer",
        "software_licence",
        "source_url",
        "tokens_href",
        "kit_href",
    }
)
"""Every field of the template (Nogat's ``PLACEHOLDERS``, kit 0.4.0)."""
OPTIONAL: frozenset[str] = frozenset(
    {"processor_transfer", "processor_cookie", "mail_transfer"}
)
"""The only fields whose value may be empty (it must still be given)."""
OPERATOR_FIELDS: Mapping[str, str] = {
    "name": "operator_name",
    "email": "operator_email",
    "terms_effective": "terms_effective",
    "processor": "processor",
    "processor_transfer": "processor_transfer",
    "processor_cookie": "processor_cookie",
    "mail_provider": "mail_provider",
    "mail_transfer": "mail_transfer",
}
"""The field of each key of ``[nogat.operator]``."""
TEMPLATE = Path("nogat") / "nogat-terms.html"
"""The kit's template, relative to the GUI's web directory."""

PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
BLOCK = re.compile(
    r"^<!-- block: (?P<name>[a-z][a-z0-9-]*) -->\n(?P<body>.*?)^<!-- /block -->\n",
    re.MULTILINE | re.DOTALL,
)


def kept(listed: Iterable[str]) -> set[str]:
    """
    The blocks kept for the ``listed`` ones.

    Parameters
    ----------
    listed : iterable of str
        Names of `KNOWN_BLOCKS`.

    Returns
    -------
    set of str
        The blocks whose lines stay.

    Raises
    ------
    ValueError
        When a name is no block of the terms.
    """
    chosen = set(listed)
    unknown = sorted(chosen - KNOWN_BLOCKS)
    if unknown:
        raise ValueError(
            message("gui.public.terms_unknown_blocks", blocks=", ".join(unknown))
        )
    return chosen


def fill(template: str, values: Mapping[str, str], blocks: Iterable[str]) -> str:
    """
    The template with its blocks chosen and its fields filled, HTML-escaped.

    Parameters
    ----------
    template : str
        The kit's ``nogat-terms.html``.
    values : Mapping of str to str
        A value for every field of the template; only those of `OPTIONAL` may be
        empty.
    blocks : iterable of str
        The blocks to keep; every other block goes with its marker lines.

    Returns
    -------
    str
        The filled page.

    Raises
    ------
    ValueError
        On an unknown block, a missing, empty or unknown value, or a ``{{`` left
        after the filling.
    """
    keep = kept(blocks)
    names = set(PLACEHOLDER.findall(template))
    missing = sorted(
        name
        for name in names
        if name not in values
        or (name not in OPTIONAL and not str(values[name]).strip())
    )
    unknown = sorted(set(values) - PLACEHOLDERS)
    if missing or unknown:
        raise ValueError(
            message(
                "gui.public.terms_bad_values",
                missing=", ".join(missing) or "-",
                unknown=", ".join(unknown) or "-",
            )
        )
    text = BLOCK.sub(lambda m: m["body"] if m["name"] in keep else "", template)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = PLACEHOLDER.sub(lambda m: html.escape(str(values[m[1]])), text)
    if "{{" in text:
        raise ValueError(message("gui.public.terms_field_left"))
    return text


def terms_page(config: GuiConfig, web: Path) -> bytes | None:
    """
    ``regulamin.html`` of the deployment, or None when the GUI is not public.

    Parameters
    ----------
    config : GuiConfig
        The settings: ``operator`` (``[nogat.operator]``), the ``obserwator``
        address of ``gui`` (``[nogat.gui]``) and the basemap (block ``osm``).
    web : Path
        The GUI's web directory, holding the kit in ``nogat/``.

    Returns
    -------
    bytes or None
        The filled page in UTF-8; None without a usable ``[nogat.operator]``, without
        the GUI's own address, or when the filling fails (logged as a warning).
    """
    service_url = config.gui.get("obserwator")
    if config.operator is None or not service_url:
        return None
    values = {
        "service_name": "Obserwator",
        "service_url": service_url,
        **{
            field: config.operator.get(key, "")
            for key, field in OPERATOR_FIELDS.items()
            if key in config.operator or field in OPTIONAL
        },
        "software_licence": "MIT",
        "source_url": "https://github.com/Daldek/Obserwator",
        "tokens_href": "nogat/tokens.css",
        "kit_href": "nogat/",
    }
    blocks = (*BLOCKS, "osm") if config.basemap is not None else BLOCKS
    template = (web / TEMPLATE).read_text(encoding="utf-8")
    try:
        page = fill(template, values, blocks)
    except ValueError as exc:
        _LOG.warning("%s", message("gui.public.terms_not_served", reason=str(exc)))
        return None
    return page.encode("utf-8")
