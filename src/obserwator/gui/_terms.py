"""
The regulamin of a public GUI (Nogat DEV-15.7): the kit's terms filled for the deployment.

A port of ``fill`` of Nogat's ``scripts/terms.py`` (the reference of the filling,
``design/README.md`` "Kit"): first the blocks, between ``<!-- block: <name> -->`` and
``<!-- /block -->`` lines, are kept for Obserwator's data sources and dropped
otherwise; then every ``{{name}}`` becomes its value, HTML-escaped. A field without a
value, or a ``{{`` left, means no page and no link.

An operator's instance (ADR-025, I15; Nogat DEV-15.7, ECO-079) serves its own
regulamin instead: the Markdown of ``[obserwator.instance] terms``, written from the
kit's draft ``nogat-terms-operator.md``, is built by `build`, a port of Nogat's
``build`` (its Markdown subset; raw HTML is escaped, never passed on), and filled the
same way; one the deployment cannot fill refuses the start.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from obserwator.exceptions import ObserwatorValidationError
from obserwator.gui._config import GuiConfig
from obserwator.messages import message

_LOG = logging.getLogger(__name__)

BLOCKS: tuple[str, ...] = ("imgw", "imgw-hydro", "pmaxtp", "chmi", "gugik", "cuzk")
"""The blocks of Obserwator's data sources, the packaged borders of PRG (GUGiK) and
RÚIAN (ČÚZK) among them (ADR-018); ``osm`` joins them with a basemap."""
PROVIDER_BLOCKS: Mapping[str, tuple[str, ...]] = {
    "IMGW-PIB": ("imgw", "imgw-hydro"),
    "CHMI": ("chmi",),
}
"""The blocks of each provider's data, dropped when an instance turns it ``off``."""
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
"""The blocks a GUI may list (Nogat's ``BLOCKS``, kit 1.0.0)."""
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
"""Every field of the template (Nogat's ``PLACEHOLDERS``, kit 1.0.0)."""
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


def served_blocks(config: GuiConfig) -> tuple[str, ...]:
    """
    The source blocks of the regulamin the deployment keeps (DEV-15.7, ADR-025).

    `BLOCKS`, with ``osm`` when the map has a basemap; on an instance without the
    blocks of a provider that is ``off`` (`PROVIDER_BLOCKS`) and, with ``pmaxtp =
    "off"``, without ``pmaxtp``: the regulamin names only the sources served.
    """
    blocks = (*BLOCKS, "osm") if config.basemap is not None else BLOCKS
    instance = config.instance
    if instance is None:
        return blocks
    dropped = {
        block
        for provider, names in PROVIDER_BLOCKS.items()
        if not instance.serves(provider)
        for block in names
    }
    if not instance.pmaxtp:
        dropped.add("pmaxtp")
    return tuple(block for block in blocks if block not in dropped)


def _values(config: GuiConfig) -> dict[str, str]:
    """The fields the deployment fills: the project's, ``[nogat.gui]``'s, ``[nogat.operator]``'s."""
    service_url = config.gui.get("obserwator")
    operator = config.operator or {}
    return {
        "service_name": "Obserwator",
        **({"service_url": service_url} if service_url else {}),
        **{
            field: operator.get(key, "")
            for key, field in OPERATOR_FIELDS.items()
            if key in operator or (field in OPTIONAL and config.operator is not None)
        },
        "software_licence": "MIT",
        "source_url": "https://github.com/Daldek/Obserwator",
        "tokens_href": "nogat/tokens.css",
        "kit_href": "nogat/",
    }


def terms_page(config: GuiConfig, web: Path) -> bytes | None:
    """
    ``regulamin.html`` of the deployment, or None when the GUI is not public.

    On an instance with ``terms`` (ADR-025, I15) it is the operator's regulamin, built
    from its Markdown with `build` and filled as the kit's page; otherwise the kit's
    regulamin 1.0 (``nogat-terms.html``). Either keeps the source blocks of
    `served_blocks` only.

    Parameters
    ----------
    config : GuiConfig
        The settings: ``operator`` (``[nogat.operator]``), the ``obserwator``
        address of ``gui`` (``[nogat.gui]``), the basemap (block ``osm``) and the
        instance.
    web : Path
        The GUI's web directory, holding the kit in ``nogat/``.

    Returns
    -------
    bytes or None
        The filled page in UTF-8. The kit's: None without a usable
        ``[nogat.operator]``, without the GUI's own address, or when the filling
        fails (logged as a warning).

    Raises
    ------
    ObserwatorValidationError
        When the operator's regulamin cannot be filled for the deployment (a field
        left or without its value: ``[nogat.gui] obserwator``, ``[nogat.operator]``,
        or one the operator writes by hand), ``details.option`` ``instance.terms``:
        the server does not start (fail closed).
    """
    instance = config.instance
    if instance is not None and instance.terms is not None:
        terms = instance.terms
        try:
            frame = (web / TEMPLATE).read_text(encoding="utf-8")
            page = fill(
                build(terms.text, frame), _values(config), served_blocks(config)
            )
        except ValueError as exc:
            raise ObserwatorValidationError(
                message("instance.terms_unfilled", path=terms.path, reason=str(exc)),
                details={"option": "instance.terms", "path": str(terms.path)},
            ) from None
        return page.encode("utf-8")
    service_url = config.gui.get("obserwator")
    if config.operator is None or not service_url:
        return None
    template = (web / TEMPLATE).read_text(encoding="utf-8")
    try:
        page = fill(template, _values(config), served_blocks(config))
    except ValueError as exc:
        _LOG.warning("%s", message("gui.public.terms_not_served", reason=str(exc)))
        return None
    return page.encode("utf-8")


# --- the operator's regulamin: a port of ``build`` of Nogat's ``scripts/terms.py`` -------

_MARKER = re.compile(r"^<!-- (?:block: (?P<name>[a-z][a-z0-9-]*)|/block) -->$")
_HEADING = re.compile(r"^(?P<level>#{2,3}) (?P<text>.+)$")
_BULLET = re.compile(r"^- (?P<text>.+)$")
_NUMBERED = re.compile(r"^\d+\. (?P<text>.+)$")
_QUOTE = re.compile(r"^> (?P<text>.+)$")
_INLINE = re.compile(
    r"\[(?P<text>[^\]]+)\]\((?P<href>[^)\s]+)\)"
    r"|<(?P<auto>https?://[^>\s]+|\{\{[a-z][a-z0-9_]*\}\})>"
    r"|\*\*(?P<strong>.+?)\*\*"
    r"|`(?P<code>[^`]+)`"
)
_BODY = re.compile(
    r'(?s)(?P<head>.*<main class="nogat-terms">\n).*?(?P<foot></main>.*)'
)
_TITLE = re.compile(r"<title>.*?</title>")


def _inline(text: str) -> str:
    """The HTML of one line of text with its inline marks; everything else escaped."""
    out = []
    end = 0
    for m in _INLINE.finditer(text):
        out.append(html.escape(text[end : m.start()], quote=False))
        if m["text"] is not None:
            href = html.escape(m["href"])
            out.append(f'<a href="{href}">{html.escape(m["text"], quote=False)}</a>')
        elif m["auto"] is not None:
            href = html.escape(m["auto"])
            out.append(f'<a href="{href}">{html.escape(m["auto"], quote=False)}</a>')
        elif m["strong"] is not None:
            out.append(f"<strong>{html.escape(m['strong'], quote=False)}</strong>")
        else:
            out.append(f"<code>{html.escape(m['code'], quote=False)}</code>")
        end = m.end()
    out.append(html.escape(text[end:], quote=False))
    return "".join(out)


def build(source: str, frame: str) -> str:
    """
    The HTML template of a regulamin in the kit's Markdown subset (Nogat ``build``).

    ``#`` to ``###`` headings, paragraphs, ``-`` and ``1.`` lists (a block marker
    inside a list keeps it open), ``>`` quotes with one line per paragraph,
    ``**strong**``, `` `code` ``, ``[text](href)`` and ``<href>``; any other text,
    raw HTML included, is escaped. The ``{{fields}}`` and the block markers stay for
    `fill`.

    Parameters
    ----------
    source : str
        The Markdown, starting with its ``# `` title.

    Returns
    -------
    str
        The page's template: the kit's head (tokens and ``nogat-terms.css``), the body
        and the footer linking back to the service.

    Raises
    ------
    ValueError
        When the source does not start with a ``# `` title.
    """
    lines = source.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError(message("gui.public.terms_no_title"))
    title = lines[0][2:]
    body = [f"<h1>{_inline(title)}</h1>"]
    paragraph: list[str] = []
    open_list: str | None = None
    quoting = False

    def close(*, keep_list: bool = False) -> None:
        nonlocal open_list, quoting
        if paragraph:
            body.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()
        if quoting:
            body.append("</blockquote>")
            quoting = False
        if open_list and not keep_list:
            body.append(f"</{open_list}>")
            open_list = None

    for line in lines[1:]:
        if _MARKER.match(line):
            close(keep_list=True)
            body.append(line)
        elif not line.strip():
            close()
        elif m := _HEADING.match(line):
            close()
            level = len(m["level"])
            body.append(f"<h{level}>{_inline(m['text'])}</h{level}>")
        elif (m := _BULLET.match(line)) or (m := _NUMBERED.match(line)):
            kind = "ul" if line.startswith("- ") else "ol"
            close(keep_list=open_list == kind)
            if open_list != kind:
                body.append(f"<{kind}>")
                open_list = kind
            body.append(f"<li>{_inline(m['text'])}</li>")
        elif m := _QUOTE.match(line):
            if not quoting:
                close()
                body.append("<blockquote>")
                quoting = True
            body.append(f"<p>{_inline(m['text'])}</p>")
        else:
            if quoting or open_list:
                close()
            paragraph.append(line)
    close()
    found = _BODY.fullmatch(frame)
    if found is None:
        raise ValueError(message("gui.public.terms_no_title"))
    head = _TITLE.sub(
        lambda _: f"<title>{html.escape(title, quote=False)}</title>", found["head"]
    )
    return head + "\n".join(body) + "\n" + found["foot"]
