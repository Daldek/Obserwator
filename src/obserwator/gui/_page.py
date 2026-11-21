"""
The page and its files with a long cache: versioned addresses (GUI plan D7).

``index.html`` is served rendered (`Site`): its own files (``theme-init.js``, ``src/``,
``css/``, ``nogat/``) under ``v/<build>/``, where ``<build>`` is a digest of every file
the page loads from its package (`build_digest`); MapLibre's stylesheet at
``vendor/maplibre-gl/maplibre-gl.css?v=<version>``, the versions read from
``vendor/vendor.json``, which ``<meta name="obserwator-vendor">`` gives to ``map.js`` for
MapLibre's module and the glyphs; and a ``modulepreload`` of every module ``src/main.js``
imports statically (`module_closure`), so the browser asks for all of them at once
instead of one level of imports after another. The modules' relative imports keep them
under the same ``v/<build>/``.

`WebFiles` answers a file of the current build under ``v/<build>/`` and a file of
``vendor/`` asked with its library's version (``?v=``) with ``Cache-Control:
public, max-age=31536000, immutable``; the page, an address of an older build (the file
of this one), the API and every other file stay ``no-cache`` with their ETag.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from obserwator.gui._http import NO_CACHE, etag_of, not_modified

BUILT = ("theme-init.js", "src", "css", "nogat", "vendor")
"""What the page loads from its package, versioned together under ``v/<build>/``."""
VERSIONED = "v"
"""The first part of a build's address: ``v/<build>/src/main.js``."""
IMMUTABLE = "public, max-age=31536000, immutable"
"""The cache of a versioned address: a year, never asked again."""
ENTRY = "src/main.js"
"""The page's module."""
_IMPORT = re.compile(
    r"""^\s*(?:import|export)\b(?:[^;"'`]*?\bfrom)?\s*["']([^"']+)["']""", re.MULTILINE
)
"""A static ``import``/``export … from`` of a module at the start of a line."""
_OWN = re.compile(r'(\s(?:src|href)=")((?:theme-init\.js|src/|css/|nogat/)[^"]*)"')
_VENDOR = re.compile(r'(\s(?:src|href)=")(vendor/([^/"]+)/[^"?]*)"')


def build_digest(web: Path) -> str:
    """
    The digest of the page's files (`BUILT`): their paths and bytes, 16 hex digits.

    Parameters
    ----------
    web : Path
        The page's directory.

    Returns
    -------
    str
        The same for the same files; another for any change of one.
    """
    digest = hashlib.sha256()
    for name in BUILT:
        top = web / name
        files = sorted(top.rglob("*")) if top.is_dir() else [top]
        for path in files:
            if path.is_file():
                digest.update(path.relative_to(web).as_posix().encode("utf-8") + b"\0")
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()[:16]


def vendor_versions(web: Path) -> dict[str, str]:
    """
    The version of each directory of ``vendor/``, from ``vendor/vendor.json``.

    Parameters
    ----------
    web : Path
        The page's directory.

    Returns
    -------
    dict of str to str
        ``{"maplibre-gl": "6.14.0", "glyphs": "2.0", …}``.
    """
    manifest = json.loads((web / "vendor" / "vendor.json").read_text(encoding="utf-8"))
    versions: dict[str, str] = {}
    for library in manifest["libraries"]:
        for name in library["files"]:
            versions[name.split("/", 1)[0]] = str(library["version"])
    return versions


def module_closure(web: Path, entry: str = ENTRY) -> list[str]:
    """
    Every module ``entry`` imports statically, directly or not, without ``entry``.

    Parameters
    ----------
    web : Path
        The page's directory.
    entry : str, optional
        The first module, relative to ``web``.

    Returns
    -------
    list of str
        Paths relative to ``web``, in the order they are first imported; a dynamic
        ``import()`` (MapLibre, loaded when the map is drawn) is not followed.
    """
    seen = [entry]
    for module in seen:
        text = (web / module).read_text(encoding="utf-8")
        for specifier in _IMPORT.findall(text):
            if not specifier.startswith((".", "/")):
                continue
            found = posixpath.normpath(
                posixpath.join(posixpath.dirname(module), specifier)
            )
            if found not in seen and (web / found).is_file():
                seen.append(found)
    return seen[1:]


def render_page(
    page: str, build: str, versions: dict[str, str], modules: list[str]
) -> str:
    """
    ``index.html`` with its versioned addresses and its ``modulepreload`` links.

    Parameters
    ----------
    page : str
        ``index.html`` as written, every address relative to it.
    build : str
        The build digest (`build_digest`).
    versions : dict of str to str
        The versions of ``vendor/`` (`vendor_versions`).
    modules : list of str
        The modules to preload (`module_closure`).

    Returns
    -------
    str
        The page to serve.
    """

    def vendor(match: re.Match[str]) -> str:
        version = versions.get(match[3])
        suffix = f"?v={version}" if version else ""
        return f'{match[1]}{match[2]}{suffix}"'

    text = _OWN.sub(rf'\1{VERSIONED}/{build}/\2"', page)
    text = _VENDOR.sub(vendor, text)
    head = [
        f'<meta name="obserwator-vendor" content="{html.escape(json.dumps(versions))}">'
    ]
    head += [
        f'<link rel="modulepreload" href="{VERSIONED}/{build}/{module}">'
        for module in modules
    ]
    return text.replace(
        '<script type="module"', "\n".join(head) + '\n<script type="module"', 1
    )


@dataclass(frozen=True)
class Site:
    """
    The rendered page of a build and what its files are versioned by.

    Attributes
    ----------
    build : str
        The build digest.
    versions : dict of str to str
        The versions of ``vendor/``.
    page : bytes
        The rendered ``index.html``.
    """

    build: str
    versions: dict[str, str]
    page: bytes

    @classmethod
    def load(cls, web: Path) -> Site:
        """Read the page's directory once: its digest, versions and rendered page."""
        build = build_digest(web)
        versions = vendor_versions(web)
        page = render_page(
            (web / "index.html").read_text(encoding="utf-8"),
            build,
            versions,
            module_closure(web),
        )
        return cls(build, versions, page.encode("utf-8"))

    async def index(self, request: Request) -> Response:
        """``index.html``: the rendered page, ``no-cache`` with its ETag."""
        etag = etag_of("page", self.build)
        unchanged = not_modified(request, etag)
        if unchanged is not None:
            return unchanged
        return Response(
            self.page,
            media_type="text/html",
            headers={"Cache-Control": NO_CACHE, "ETag": f'"{etag}"'},
        )


class WebFiles(StaticFiles):
    """
    The page's files: those of a versioned address cached for a year (`IMMUTABLE`).

    Parameters
    ----------
    site : Site
        The build and the vendored versions.
    **kwargs : Any
        `StaticFiles`'s.
    """

    def __init__(self, *, site: Site, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.site = site

    async def get_response(self, path: str, scope: Scope) -> Response:
        parts = PurePosixPath(path.replace(os.sep, "/")).parts
        cache = None
        if parts and parts[0] == VERSIONED:
            if len(parts) < 3 or parts[2] not in BUILT:
                raise HTTPException(status_code=404)
            path = os.path.join(*parts[2:])
            if parts[1] == self.site.build:
                cache = IMMUTABLE
        elif len(parts) > 1 and parts[0] == "vendor":
            asked = Request(scope).query_params.get("v")
            if asked is not None and asked == self.site.versions.get(parts[1]):
                cache = IMMUTABLE
        response = await super().get_response(path, scope)
        if cache is not None and response.status_code in (200, 304):
            response.headers["Cache-Control"] = cache
        return response
