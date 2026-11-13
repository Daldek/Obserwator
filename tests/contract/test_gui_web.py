"""
The web GUI's page files (GUI plan D15, D16; Nogat DEV-15.1, DEV-15.3, DEV-15.6).

The copies of Nogat's tokens, marks and kit and the vendored libraries keep the bytes
their manifests name; the page loads nothing from another origin and has no inline script
or style (CSP ``'self'``); every text the page's scripts name is an entry of the catalog's
area ``gui``, and no Polish word is left in their literals.
"""

import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from obserwator.gui import WEB_DIR
from obserwator.messages.gui import MESSAGES

SRC = WEB_DIR / "src"
SCRIPTS = sorted(SRC.rglob("*.js"))
PAGES = sorted(path for path in WEB_DIR.rglob("*.html") if "nogat" not in path.parts)
STYLES = sorted((WEB_DIR / "css").rglob("*.css"))
KEYS = {key.removeprefix("gui.") for key in MESSAGES}
# Polish letters, and Polish words that no English text uses, as words of their own (not
# joined by "-", "_" or "." into a class name, an id or a key)
POLISH = re.compile(
    "[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]"
    r"|(?<![\w.-])(?:nie|brak|albo|lub|oraz|jest|dla|tylko|przez|bez|przy|czy"
    r"|stacj(?:a|i|e|ach|ami)|dane|danych|plik\w*|pobierz|wczytuj\w*|wybierz|kliknij"
    r"|zobacz\w*|wynik\w*|okres\w*|lata|rok|dni|opad\w*|stany|stanu|wody|przep\w+)(?![\w.-])",
    re.IGNORECASE,
)
# Ids of the panel's sections in the address (``?section=dane``): names, not texts
SECTION_IDS = frozenset(
    {
        "stacja",
        "teraz",
        "dane",
        "pobierz",
        "opady",
        "susze",
        "temperatura",
        "snieg",
        "trendy",
    }
)
# The character before a slash that starts a regular expression, not a division
_REGEX_AFTER = frozenset("(,=:[!&|?{};+-*%<>~^")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _skip_regex(text: str, i: int) -> int:
    """The index after the regular expression literal starting at ``text[i] == "/"``."""
    i += 1
    in_class = False
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            return i + 1
        elif char == "\n":
            return i
        i += 1
    return i


def _quoted(text: str, i: int) -> tuple[str, int]:
    """A quoted string starting at ``text[i]``: its content and the index after it."""
    quote = text[i]
    j = i + 1
    while j < len(text) and text[j] != quote:
        j += 2 if text[j] == "\\" else 1
    return text[i + 1 : j], j + 1


def _code(text: str, i: int, found: list[str], *, until: str | None = None) -> int:
    """Scan code from ``i``, collecting literals, until an unmatched ``}`` or the end."""
    depth = 0
    last = ""
    while i < len(text):
        char = text[i]
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        if char == "/" and (last == "" or last in _REGEX_AFTER):
            i = _skip_regex(text, i)
            last = "a"
            continue
        if char in "'\"":
            value, i = _quoted(text, i)
            found.append(value)
            last = "a"
            continue
        if char == "`":
            i = _template(text, i, found)
            last = "a"
            continue
        if until is not None:
            if char == "{":
                depth += 1
            elif char == "}":
                if depth == 0:
                    return i + 1
                depth -= 1
        if not char.isspace():
            last = char
        i += 1
    return i


def _template(text: str, i: int, found: list[str]) -> int:
    """A template literal starting at ``text[i] == "`"``: its text parts, then its code."""
    i += 1
    part: list[str] = []
    while i < len(text):
        char = text[i]
        if char == "\\":
            part.append(text[i : i + 2])
            i += 2
            continue
        if char == "`":
            found.append("".join(part))
            return i + 1
        if text.startswith("${", i):
            found.append("".join(part))
            part = []
            i = _code(text, i + 2, found, until="}")
            continue
        part.append(char)
        i += 1
    found.append("".join(part))
    return i


def literals(text: str) -> list[str]:
    """The string literals of a script and the text parts of its templates; comments skipped."""
    found: list[str] = []
    _code(text, 0, found)
    return found


# --- copies ------------------------------------------------------------------------------


def test_vendored_files_keep_the_bytes_of_their_manifest():
    manifest = json.loads(
        (WEB_DIR / "vendor" / "vendor.json").read_text(encoding="utf-8")
    )
    files = {
        name: entry["sha256"]
        for library in manifest["libraries"]
        for name, entry in library["files"].items()
    }
    assert files
    changed = sorted(
        name for name, sha in files.items() if _sha256(WEB_DIR / "vendor" / name) != sha
    )
    assert changed == []


def test_nogat_copies_keep_the_bytes_of_their_manifests():
    nogat = WEB_DIR / "nogat"
    identity = json.loads((nogat / "nogat.json").read_text(encoding="utf-8"))
    kit = json.loads((nogat / "nogat-kit.json").read_text(encoding="utf-8"))
    files = {name: entry["sha256"] for name, entry in identity["files"].items()}
    files.update(kit["files"])
    changed = sorted(
        name for name, sha in files.items() if _sha256(nogat / name) != sha
    )
    assert changed == []


# --- the page and the CSP -----------------------------------------------------------------


def test_the_page_loads_nothing_from_another_origin():
    remote = re.compile(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", re.IGNORECASE)
    imports = re.compile(r"""(?:\bfrom|\bimport)\s*\(?\s*["'](?:https?:)?//""")
    css = re.compile(
        r"""(?:url\(\s*["']?|@import\s+["'])(?:https?:)?//""", re.IGNORECASE
    )
    found = [
        str(path) for path in PAGES if remote.search(path.read_text(encoding="utf-8"))
    ]
    found += [
        str(path)
        for path in SCRIPTS
        if imports.search(path.read_text(encoding="utf-8"))
    ]
    found += [
        str(path) for path in STYLES if css.search(path.read_text(encoding="utf-8"))
    ]
    assert PAGES and SCRIPTS
    assert found == []


@pytest.mark.parametrize(
    "page", PAGES, ids=lambda path: path.relative_to(WEB_DIR).as_posix()
)
def test_a_page_has_no_inline_script_or_style(page):
    html = page.read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b[^>]*>", html, re.IGNORECASE)
    assert all(re.search(r"\bsrc\s*=", tag, re.IGNORECASE) for tag in scripts)
    assert re.search(r"<style\b", html, re.IGNORECASE) is None
    assert re.search(r"\sstyle\s*=", html, re.IGNORECASE) is None
    assert re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE) is None


# --- texts --------------------------------------------------------------------------------


def _key_calls(text: str) -> Iterator[tuple[str, str]]:
    """Each ``t("…")``, ``tn("…")`` and ``has("…")`` of a script: the function and its key."""
    pattern = r"""(?<![\w.$])(t|tn|has)\(\s*(["'`])([^"'`$]*?)(\$\{|\2)"""
    for function, _, key, end in re.findall(pattern, text):
        yield function, key + ("${" if end == "${" else "")


def test_every_text_the_page_names_is_an_entry_of_the_catalog():
    missing = []
    for path in SCRIPTS:
        where = path.relative_to(WEB_DIR).as_posix()
        for function, key in _key_calls(path.read_text(encoding="utf-8")):
            if key.endswith("${"):
                prefix = key.removesuffix("${")
                if not any(known.startswith(prefix) for known in KEYS):
                    missing.append(f"{where}: {function}(`{prefix}…`)")
            elif function == "tn":
                if f"{key}.other" not in KEYS:
                    missing.append(f"{where}: tn({key!r})")
            elif key not in KEYS:
                missing.append(f"{where}: {function}({key!r})")
    assert missing == []


def test_the_page_scripts_hold_no_polish_text():
    found = []
    for path in SCRIPTS:
        for value in literals(path.read_text(encoding="utf-8")):
            if value in SECTION_IDS or value.startswith(("https://", "http://")):
                continue
            if POLISH.search(value):
                found.append(f"{path.relative_to(WEB_DIR).as_posix()}: {value[:60]!r}")
    assert found == [], "a text of the page belongs in obserwator.messages.gui"
