"""
uvicorn for `obserwator.gui.serve` (imported with the ``gui`` extra).

The server binds the address, announces ``Obserwator GUI: <url>`` on standard error once
it listens and stops gracefully on Ctrl+C or ``SIGTERM``, returning, so the command ends
with exit code 0. uvicorn's own access log is off: it would write the client's address,
which the GUI never keeps (Nogat DEV-15.10); the app writes its own lines. Behind a
reverse proxy uvicorn takes the client's address from ``X-Forwarded-For`` only when the
proxy is one of ``FORWARDED_ALLOW_IPS`` (default ``127.0.0.1``), so the rate limit counts
clients, not the proxy.
"""

from __future__ import annotations

import contextlib
import errno
import signal
import socket
import sys
import threading
import webbrowser
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import uvicorn
from starlette.applications import Starlette

from obserwator.exceptions import ObserwatorError, ObserwatorValidationError
from obserwator.messages import message

_GRACE_S = 5
"""How long open requests may take to end at a stop [s]."""
_IN_USE = frozenset(
    code
    for code in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", None))
    if code is not None
)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def url_of(host: str, port: int) -> str:
    """The address of the page, ``http://<host>:<port>/`` (an IPv6 host in brackets)."""
    shown = f"[{host}]" if ":" in host else host
    return f"http://{shown}:{port}/"


def _bind(host: str, port: int) -> socket.socket:
    """A socket bound to ``host:port`` (port 0: a free one)."""
    try:
        family, kind, proto, _, address = socket.getaddrinfo(
            host, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
        )[0]
    except socket.gaierror as exc:
        raise ObserwatorValidationError(
            message("gui.server.bad_host", host=host, reason=str(exc)),
            details={"option": "host", "value": host, "reason": "invalid_host"},
        ) from exc
    listener = socket.socket(family, kind, proto)
    try:
        if sys.platform != "win32":  # on Windows the option would share the port
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(address)
    except OSError as exc:
        listener.close()
        if exc.errno in _IN_USE:
            raise ObserwatorError(
                message("gui.server.port_in_use", host=host, port=port),
                code="conflict",
                details={"reason": "port_in_use", "host": host, "port": port},
            ) from exc
        raise
    return listener


class _Server(uvicorn.Server):
    """uvicorn's server that announces its address and stops quietly on a signal."""

    def __init__(self, config: uvicorn.Config, *, url: str, open_browser: bool) -> None:
        super().__init__(config)
        self._url = url
        self._open_browser = open_browser

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        """Stop gracefully on ``SIGINT`` or ``SIGTERM`` without re-raising them."""
        if threading.current_thread() is not threading.main_thread():
            yield
            return
        handled = [signal.SIGINT, signal.SIGTERM]
        previous = {
            number: signal.signal(number, self.handle_exit) for number in handled
        }
        try:
            yield
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        """Start, then announce the address (and open the browser)."""
        await super().startup(sockets=sockets)
        if self.should_exit:
            return
        print(
            message("gui.server.listening", url=self._url), file=sys.stderr, flush=True
        )
        if self._open_browser:
            threading.Thread(
                target=webbrowser.open, args=(self._url,), daemon=True
            ).start()


def run(app: Starlette, *, host: str, port: int, open_browser: bool) -> dict[str, Any]:
    """
    Serve ``app`` on ``host:port`` until a signal stops it.

    Returns
    -------
    dict
        ``url``, ``started_at`` and ``stopped_at``.
    """
    listener = _bind(host, port)
    try:
        url = url_of(host, listener.getsockname()[1])
        started_at = _now()
        config = uvicorn.Config(
            app,
            log_config=None,
            access_log=False,
            proxy_headers=True,
            server_header=False,
            lifespan="on",
            timeout_graceful_shutdown=_GRACE_S,
        )
        _Server(config, url=url, open_browser=open_browser).run(sockets=[listener])
    finally:
        listener.close()
    return {"url": url, "started_at": started_at, "stopped_at": _now()}
