"""
Answers of the GUI's private API: JSON with strong ETags, files, the error document.

Every answer from the data root carries a strong ETag made of the versions it was read
from and the query, with ``Cache-Control: no-cache``, so the browser asks again and gets
``304`` while nothing changed (GUI plan D7). An error is the document
``obserwator-error/1`` with the registry's HTTP status, its texts in the page's language
(``Accept-Language``: ``pl`` or ``en``, Polish by default) and no server path (D6).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import Response

from obserwator._jsonable import jsonable
from obserwator.error_report import ERROR_SCHEMA, error_document
from obserwator.exceptions import ERROR_CODES, ErrorCode, ObserwatorError
from obserwator.messages import Lang, Message, localize, message

JSON = "application/json"
NO_CACHE = "no-cache"
DEFAULT_LANG: Lang = "pl"
"""The page's language when the request names none: the GUI is Polish by default (DEV-2.2)."""
HTTP_ONLY: Mapping[str, tuple[int, str]] = {
    "rate_limited": (429, "gui.errors.title_rate_limited"),
    "unauthorized": (401, "gui.errors.title_unauthorized"),
}
"""The codes of Nogat's registry that only HTTP answers use (AGI-6.3), outside
`ERROR_CODES`: their status and the key of their title (DEV-15.9, DEV-15.13)."""


class GuiError(Exception):
    """
    An answer of the private API other than 200, with its text from the catalog.

    Parameters
    ----------
    code : str
        A code of the error registry (`ERROR_CODES`), or one of `HTTP_ONLY`:
        ``rate_limited`` (429, Nogat DEV-15.9), ``unauthorized`` (401, DEV-15.13).
    text : str
        What happened: a catalog `Message`, rendered in the page's language.
    details : Mapping or None, optional
        JSON-compatible context (``option``, ``value``, ``allowed``, ``reason``).
    headers : Mapping or None, optional
        Extra headers of the answer (``Retry-After``, ``Allow``).
    """

    def __init__(
        self,
        code: str,
        text: str,
        /,
        *,
        details: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(text)
        self.code = code
        self.text = text
        self.details = dict(details or {})
        self.headers = dict(headers or {})

    @property
    def status(self) -> int:
        """The HTTP status of the code."""
        if self.code in HTTP_ONLY:
            return HTTP_ONLY[self.code][0]
        spec = ERROR_CODES.get(self.code)  # type: ignore[call-overload]
        return (spec.http_status if spec is not None else None) or 500


def page_lang(request: Request) -> Lang:
    """The page's language: the first of ``pl`` and ``en`` in ``Accept-Language``, else Polish."""
    for part in request.headers.get("accept-language", "").split(","):
        tag = part.split(";")[0].strip().lower()[:2]
        if tag in ("pl", "en"):
            return tag  # type: ignore[return-value]
    return DEFAULT_LANG


def clean(value: Any) -> Any:
    """A JSON-ready copy: non-finite numbers as null, tuples as lists, paths as text."""
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [clean(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    return value


def dumps(document: Any, *, indent: int | None = None) -> bytes:
    """UTF-8 JSON of a cleaned document, compact unless ``indent`` is given."""
    separators = (",", ":") if indent is None else (",", ": ")
    text = json.dumps(
        clean(document),
        ensure_ascii=False,
        separators=separators,
        indent=indent,
        allow_nan=False,
    )
    return (text + ("\n" if indent is not None else "")).encode("utf-8")


def etag_of(*parts: object) -> str:
    """A strong ETag of what an answer was made from: versions, the query, a key."""
    text = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _not_modified(request: Request, etag: str) -> bool:
    given = request.headers.get("if-none-match", "")
    return any(tag.strip() in (f'"{etag}"', "*") for tag in given.split(","))


def not_modified(request: Request, etag: str) -> Response | None:
    """
    ``304`` when the request's ``If-None-Match`` holds ``etag``, before the answer is made.

    Parameters
    ----------
    request : Request
        The request answered.
    etag : str
        Strong ETag of the answer (`etag_of`).

    Returns
    -------
    Response or None
        The ``304`` with the ETag and ``Cache-Control: no-cache``; None when the
        answer must be made.
    """
    if not _not_modified(request, etag):
        return None
    return Response(
        status_code=304, headers={"Cache-Control": NO_CACHE, "ETag": f'"{etag}"'}
    )


def json_response(
    request: Request,
    document: Any,
    *,
    etag: str | None = None,
    status: int = 200,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """
    A JSON answer, ``304`` when the request's ``If-None-Match`` holds its ETag.

    Parameters
    ----------
    request : Request
        The request answered.
    document : Any
        JSON-compatible document; non-finite numbers become null.
    etag : str or None, optional
        Strong ETag of the document (`etag_of`); None for an answer without one.
    status : int, optional
        HTTP status.
    headers : Mapping or None, optional
        Extra headers.

    Returns
    -------
    Response
        The answer with ``Cache-Control: no-cache``.
    """
    extra = {"Cache-Control": NO_CACHE, **(headers or {})}
    if etag is not None:
        extra["ETag"] = f'"{etag}"'
        if status == 200 and _not_modified(request, etag):
            return Response(status_code=304, headers=extra)
    return Response(dumps(document), status_code=status, media_type=JSON, headers=extra)


def content_disposition(filename: str) -> str:
    """``attachment`` with an ASCII name and the exact name in RFC 5987 form."""
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def attachment(
    request: Request,
    body: bytes,
    *,
    filename: str,
    media_type: str,
    etag: str | None = None,
) -> Response:
    """A file to download: ``Content-Disposition: attachment`` and an optional ETag."""
    headers = {
        "Cache-Control": NO_CACHE,
        "Content-Disposition": content_disposition(filename),
    }
    if etag is not None:
        headers["ETag"] = f'"{etag}"'
        if _not_modified(request, etag):
            return Response(status_code=304, headers=headers)
    return Response(body, media_type=media_type, headers=headers)


def hide_paths(value: object, directories: Iterable[Path]) -> object:
    """``value`` with the server's directories written as paths relative to them (D6)."""
    for directory in sorted(
        {str(path): path for path in directories}.values(),
        key=lambda path: len(str(path)),
        reverse=True,
    ):
        value = jsonable(value, root=directory, server=True)
    return value


def error_body(exc: GuiError | ObserwatorError, lang: Lang) -> dict[str, Any]:
    """The document ``obserwator-error/1`` of an error, in ``lang``."""
    if isinstance(exc, ObserwatorError):
        return error_document(
            exc.code, exc.detail, exc.details, hint=exc.hint, lang=lang
        ).to_dict()
    if exc.code in HTTP_ONLY:
        return {
            "schema": ERROR_SCHEMA,
            "code": exc.code,
            "title": str(message(HTTP_ONLY[exc.code][1], lang=lang)),
            "message": localize(exc.text, lang),
            "details": exc.details,
            "exit_code": None,
        }
    code: ErrorCode = exc.code  # type: ignore[assignment]
    return error_document(code, exc.text, exc.details, lang=lang).to_dict()


def error_response(
    request: Request,
    exc: GuiError | ObserwatorError,
    directories: Iterable[Path] = (),
) -> Response:
    """
    The error answer: its registry status, its document in the page's language.

    Parameters
    ----------
    request : Request
        The request answered (its ``Accept-Language`` chooses the language).
    exc : GuiError or ObserwatorError
        The error.
    directories : iterable of Path, optional
        Server directories to hide in the texts.

    Returns
    -------
    Response
        ``application/json`` with ``Cache-Control: no-cache``.
    """
    lang = page_lang(request)
    body = hide_paths(error_body(exc, lang), directories)
    if isinstance(exc, GuiError):
        status, headers = exc.status, exc.headers
    else:
        spec = ERROR_CODES[exc.code]
        status, headers = spec.http_status or 500, {}
    return Response(
        dumps(body),
        status_code=status,
        media_type=JSON,
        headers={"Cache-Control": NO_CACHE, "Content-Language": lang, **headers},
    )


def text_of(value: Message | str, lang: Lang) -> str:
    """A catalog message in ``lang``; another text unchanged."""
    return localize(value, lang)
