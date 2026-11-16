"""
Main FastAPI application of Obserwator: catalog routes, system routes, MCP.

The catalog routes ``/api/v1/<group>/<command>`` come from
`obserwator.api.routes.commands`; ``GET /health`` and ``GET /api/v1`` describe the
server, ``GET /llms.txt`` is the agent guide in the llms.txt format in the
language of ``Accept-Language`` (spec 2026-10-19 §5.8), and ``GET /`` redirects to
the documentation ``/docs``. With ``OBSERWATOR_MCP_ENABLED=true`` and the ``mcp``
extra, ``/mcp`` serves the MCP server in mode ``http`` (Streamable HTTP, spec §6.2,
§6.9), in English like every MCP server; its session manager runs in the lifespan of
this application. The web GUI is a server of its own, ``obserwator gui serve``
(ADR-013), which this application does not serve.

The server keeps Nogat's logs (DEV-12.4 to DEV-12.9) with `SERVER_LOG`: the access log
of the outermost middleware `obserwator.nogat_logging.AccessLog` (no client address,
the static documents of `QUIET` logged only from status 400), the application log and
the lifecycle records ``start`` and ``stop`` of the lifespan, in
``<state_dir>/obserwator/logs/<kind>-YYYY-MM-DD.jsonl``, deleted after 14 days;
standard error gets only the lifecycle records and the errors reduced to their type.
uvicorn runs with ``access_log=False`` and ``log_config=None`` (`run_server`; on its
command line ``--no-access-log --log-level warning``).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, nullcontext
from typing import cast

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.routing import APIRoute
from starlette.applications import Starlette

from obserwator import _environment as environment
from obserwator._version import __version__
from obserwator.agent_guide import agent_guide
from obserwator.api.errors import EXCEPTION_HANDLERS, accept_language
from obserwator.api.routes import commands
from obserwator.api.schemas import HealthCheck
from obserwator.commands import command_schema
from obserwator.config import check_config, settings
from obserwator.nogat_logging import AccessLog, ServerLog

_LOG = logging.getLogger(__name__)

SERVER_LOG = ServerLog(environment.TOOL, __version__, settings.log_dir)
"""The server's logs in ``<state_dir>/obserwator/logs`` (Nogat DEV-12.6)."""
QUIET = (
    r"^/(docs|redoc)(/|$)|^/openapi\.json$|^/llms\.txt$|^/health$"
    r"|^/api/v1(/commands/schema)?$"
)
"""The static content of the access log (Nogat DEV-12.5): the documentation, the OpenAPI
document, the guide, the list of routes, the catalog's schema and the health answer, the
same for every client, are logged only when answered with 400 or more."""

# API metadata
API_TITLE = "Obserwator API"
API_DESCRIPTION = """
API of the public data of IMGW-PIB and ČHMÚ, generated from the Obserwator command catalog.

## Routes

* `GET|POST /api/v1/<group>/<command>` — one route per catalog command
  (`obserwator <group> <command>` in the CLI); the list of routes: `GET /api/v1`, the
  description of the options: `GET /api/v1/commands/schema`.
* `GET /llms.txt` — the guide for AI agents in the llms.txt format (the language
  comes from the `Accept-Language` header: `en` or `pl`, `en` by default).
* `/mcp` — the MCP server (Streamable HTTP) with the catalog routes as tools, when
  the administrator sets `OBSERWATOR_MCP_ENABLED=true`; writes only as a plan.
* Answer: the envelope `obserwator-result/1` (`schema`, `tool`, `version`, `command`,
  `check`, `status`, `result`, `notices`, `page` of a list command); the status
  `partial`/`failed` also has code 200, so read the `status` field. `store export`
  and `series export` return a CSV/JSONL stream with the headers
  `X-Obserwator-Status` and `X-Obserwator-Notices`.
* List commands return the list of items as `result` and page by `limit` (default
  and at most `OBSERWATOR_API_MAX_LIMIT`) and `cursor`: pass `page.next_cursor` while
  `page.truncated` is true.
* Errors: `application/problem+json` (RFC 9457) with the fields `code` and `details`.
* The texts of notices and errors follow `Accept-Language` (`en` or `pl`, `en` by
  default); every answer names its language in `Content-Language`.

## Store

By default the data is NOT kept on the server: the API gives direct links to the
IMGW-PIB and ČHMÚ servers and reads the current data live. The store commands work
only on the roots the administrator names: `OBSERWATOR_RAW_ROOT`, the raw root of the
downloaded sources (`store check|sync|export`, `pmaxtp check|sync|read`), and
`OBSERWATOR_ROOT`, the data root of what is built from them (series, station
catalogs, analyses, `store info|scan`); `series build` and `store catalog` read the
raw root and write the data root. A command whose root is not configured answers 503
`store_unavailable`. Writing (POST without `?check=true`) is off by default (403
`forbidden`): it needs `OBSERWATOR_STORE_WRITES_ENABLED=true`, `OBSERWATOR_STORE_WRITE_TOKEN`
and the header `X-API-Key`; `?check=true` returns the plan `obserwator-plan/1` without
writing and without a token.
"""
API_VERSION = __version__


def _mcp_app() -> Starlette | None:
    """
    Streamable HTTP application of ``/mcp`` (spec 2026-10-19 §6.2).

    Returns
    -------
    starlette.applications.Starlette or None
        The MCP server in mode ``http``; None unless ``OBSERWATOR_MCP_ENABLED=true`` and
        the ``mcp`` extra is installed (``/mcp`` is then an unknown route: 404
        ``not_found``).
    """
    if not settings.mcp_enabled:
        return None
    try:
        from obserwator.mcp.server import http_app
    except ImportError:
        return None  # the lifespan logs the missing extra
    return http_app()


_MCP = _mcp_app()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Start the logs, check ``nogat.toml``, run the session manager of ``/mcp`` with the app.

    The lifecycle record ``start`` sums up the settings (`SERVER_LOG`); ``stop`` follows
    the end of serving, also when the start fails.
    """
    SERVER_LOG.start(
        {
            "host": settings.host,
            "port": settings.port,
            "env": settings.env,
            "root": settings.root,
            "raw_root": settings.raw_root,
            "store_writes_enabled": settings.store_writes_enabled,
            "mcp": _MCP is not None,
        }
    )
    try:
        if settings.mcp_enabled and _MCP is None:
            _LOG.warning(
                "OBSERWATOR_MCP_ENABLED=true, but the MCP server needs the extra: pip "
                "install obserwator[mcp]; the route /mcp does not exist"
            )
        check_config()  # an unusable settings file stops the server instead of being ignored
        # A route of another application never runs its lifespan by itself.
        async with (
            nullcontext() if _MCP is None else _MCP.router.lifespan_context(_MCP)
        ):
            yield
    finally:
        SERVER_LOG.stop()


def _operation_id(route: APIRoute) -> str:
    """``operationId`` of a route outside the catalog: ``obserwator_system_<function>``."""
    # Catalog routes name their id themselves (obserwator_<group>_<verb>, AGI-6.2).
    return f"obserwator_system_{route.name}"


# Create FastAPI app
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        *(
            {"name": group, "description": text}
            for group, text in cast(
                dict[str, str], command_schema(lang="en")["groups"]
            ).items()
        ),
        {
            "name": "System",
            "description": "Server state, the list of routes and the guide",
        },
    ],
    exception_handlers=EXCEPTION_HANDLERS,
    lifespan=_lifespan,
    generate_unique_id_function=_operation_id,
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Outermost: the access log records every answer, the middleware's own too (DEV-12.8).
app.add_middleware(AccessLog, log=SERVER_LOG, quiet=QUIET)

# Catalog routes /api/v1/<group>/<command>
app.include_router(commands.router)

if _MCP is not None:
    # Only the /mcp route: a mount at "/" would answer unknown paths with a
    # plain 404 instead of the problem document.
    app.router.routes.extend(_MCP.routes)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """The start page is the API's documentation (the web GUI is `obserwator gui serve`)."""
    return RedirectResponse("/docs")


@app.get("/health", response_model=HealthCheck, tags=["System"], summary="Server state")
async def health_check() -> HealthCheck:
    """State of the server and the version of the package."""
    return HealthCheck(status="ok", version=API_VERSION)


@app.get("/api/v1", tags=["System"], summary="API routes")
async def api_info() -> dict[str, object]:
    """List the routes of the command catalog."""
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "schema": "/api/v1/commands/schema",
        "routes": commands.catalog_routes(),
    }


@app.get(
    "/llms.txt",
    tags=["System"],
    summary="The llms.txt guide",
    response_class=Response,
    responses={
        200: {
            "description": "The guide in the llms.txt format (markdown)",
            "content": {"text/markdown": {"schema": {"type": "string"}}},
        }
    },
)
async def llms_txt(request: Request) -> Response:
    """
    Guide for AI agents in the llms.txt format.

    The header Accept-Language chooses the language: en or pl, en by default.
    """
    lang = accept_language(request.headers.get("accept-language"))
    response = Response(
        "".join(agent_guide(format="llms", lang=lang)),
        media_type="text/markdown; charset=utf-8",
    )
    response.headers["Content-Language"] = lang
    response.headers.add_vary_header("Accept-Language")
    return response


def run_server(
    *, host: str | None = None, port: int | None = None, reload: bool | None = None
) -> None:
    """
    Run the API server with uvicorn until it is stopped.

    uvicorn keeps no log of its own (``access_log=False``, ``log_config=None``): the
    app's `SERVER_LOG` writes every record (Nogat DEV-12.8). A given ``host`` or
    ``port`` goes before the settings (DEV-18.1) and into them, so the lifecycle record
    ``start`` names the address served; with ``reload`` the server runs in a process
    of its own, which reads the settings again (``OBSERWATOR_HOST``,
    ``OBSERWATOR_PORT``) for that record.

    Parameters
    ----------
    host, port : str and int, optional
        The address to listen on; ``OBSERWATOR_HOST`` and ``OBSERWATOR_PORT`` when
        omitted.
    reload : bool, optional
        Restart when the code changes; by default unless ``OBSERWATOR_ENV=production``.
    """
    import uvicorn

    if host is not None:
        settings.host = host
    if port is not None:
        settings.port = port
    uvicorn.run(
        "obserwator.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=not settings.is_production if reload is None else reload,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run_server()
