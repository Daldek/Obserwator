# Security policy

## Supported versions

Security fixes go into the latest release of Obserwator (and the development branch
`develop`). Older releases are not patched.

## Reporting a vulnerability

Please do not report vulnerabilities in public issues or pull requests.

Use GitHub's private vulnerability reporting: open the **Security** tab of
<https://github.com/Daldek/Obserwator>, choose **Report a vulnerability** and describe
the problem, the affected version and, if possible, how to reproduce it. You get an
answer as soon as the maintainer can read the report; a fix is released as a patch
version and credited in the CHANGELOG unless you prefer otherwise.

## Scope

Obserwator downloads public data from IMGW-PIB and ČHMÚ and writes it to local files or a
versioned store. Reports about the following are in scope:

- the REST server (`obserwator server`, `/api/v1`), including the store write routes and
  their token (`OBSERWATOR_STORE_WRITES_ENABLED`, `OBSERWATOR_STORE_WRITE_TOKEN` or the
  file named by `OBSERWATOR_STORE_WRITE_TOKEN_FILE`, header `X-API-Key`), its
  cross-origin rule (`OBSERWATOR_CORS_ORIGINS`) and the file of the REST API keys of
  `obserwator admin` (`api_keys.json`; deprecated, removed in v4.0.0);
- the web GUI, its own server (`obserwator gui serve`): its private API under `api/`,
  including the computations on request that run Hydrolog's program; its rate limit per
  client address (`OBSERWATOR_REQUEST_LIMIT`, `OBSERWATOR_REQUEST_WINDOW`, `429` with
  `Retry-After`); the „Zgłoś uwagę” form (`POST api/feedback`) and its file
  `<data_dir>/obserwator/feedback.jsonl`, which keeps no client address; the daily totals
  `stats.jsonl`; and the admin panel (`admin/`, `api/admin/…`) with its key
  (`OBSERWATOR_ADMIN_API_KEY` or the file named by `OBSERWATOR_ADMIN_API_KEY_FILE`, header
  `X-Admin-Key`): any admin access without the key, or a key, report or client address
  that leaks;
- the servers' logs (`<state_dir>/obserwator/logs`): a client address, a header, a body or
  a credential written to them;
- the captures of current data (ADR-030): the spool `<state_dir>/obserwator/captures` and
  the publication of each source (`[obserwator.capture]`): a `private` source's captures,
  hourly series or chart served by REST, MCP over HTTP or the GUI, or a credential kept in a
  captured answer;
- a data provider's API key (`OBSERWATOR_<PROVIDER>_API_KEY` or the file of
  `…_API_KEY_FILE`): one logged or written to a URL, an envelope or a sidecar;
- the deployment's scripts and units (`deploy/`: the timers, `obserwator-jobs.sh`,
  `obserwator-backup.sh`): a write outside the roots, `state_dir` and the backup target, or
  a deletion outside the script's own snapshots;
- the MCP server (`obserwator mcp` over stdio and `/mcp` of the REST server), including
  the sandbox of writes (`--allow-writes`, `--allow-dir`): any write or path outside the
  allowed directories;
- writes to the store and to output files: path traversal, overwriting files outside the
  target, corruption of committed versions;
- unsafe parsing of downloaded archives (ZIP, CSV, JSON) and of store files;
- the supply chain of the package.

Problems of the IMGW-PIB or ČHMÚ services themselves are out of scope; report them to the
institute.

## Threat model: an instance on someone else's infrastructure (ADR-025)

An operator other than the author may run Obserwator on his own servers for his own
users, described by `[obserwator.instance]` of `nogat.toml` (`docs/USAGE.md`, „Deploying
an instance for an operator”). This section says what is protected, from whom, and who
does what.

**Assets.** The data root and the raw root (the published series, catalogs, analyses and
archives: integrity and availability, not secrecy; ADR-017); the two secrets, the REST
write token and the GUI's admin key; the reports of „Zgłoś uwagę” (`feedback.jsonl`) and
the daily totals (`stats.jsonl`); the servers' logs (`<state_dir>/obserwator/logs`, no
client address, 14 days); the operator's files under its configuration directory
(`nogat.toml`, the area, the logo, the regulamin, the secret files).

**Entry points.** The GUI's private API (`api/…`, GET and HEAD, `POST api/feedback`),
rate-limited per client address; the REST API `/api/v1` (reads; writes only with
`OBSERWATOR_STORE_WRITES_ENABLED` and the token); the admin panel (`/admin`, `/admin/*`,
`/api/admin/*`, header `X-Admin-Key`); `/mcp` when enabled (reads and plans only); the
outbound fetches: IMGW-PIB's current data, PMAXTP and the live hours of „Wykres
godzinowy” by the servers, the hourly poll and the night's harvests by the timers, the
basemap by the browser.

**Threats and what Obserwator does about them.**

- *A source the instance does not serve leaks* (a guessed station code, a hidden route):
  the filter runs on the server, once per read of the data root, for every route of both
  servers; a station not served answers `not_found` exactly like a code that does not
  exist; an `off` provider and `pmaxtp = "off"` make no outbound request.
- *A source the operator keeps private leaks*: every source of a tier other than
  `verified` is `public` or `private` by `[obserwator.capture]` (hydro.imgw.pl's backend
  `private` by default), read on every request; REST and MCP over HTTP answer `not_found`
  (`details.reason` `private`) for its dataset, a version below it and a series built from
  it, and the GUI draws no chart of it, all before any request (ADR-030 D5).
- *A misconfiguration starts silently*: every field of `[obserwator.instance]` is checked
  at start (`validation_error`, exit 2, `details.option`), as are a data root of an
  unknown layout and, on an instance, weak or unreadable secrets (shorter than 32 bytes,
  a key file that is not UTF-8, or a key file group or others may access, checked on
  POSIX systems only: Windows has no permission bits, its ACLs are the operator's to
  set); `obserwator config show --json` lists what remains as `problems`.
- *A stolen or guessed secret*: one token and one key, compared in constant time, read
  from the environment or from `*_FILE` files of mode 0600, never from `nogat.toml`,
  never logged or printed; the REST API keys of `obserwator admin` are checked by nothing,
  deprecated and removed in v4.0.0.
- *Script injection through the operator's files*: the logo is served from the GUI's own
  origin as an image whose type is read from its content, an SVG with
  `Content-Security-Policy: sandbox; default-src 'none'` and `nosniff`; the regulamin is
  Markdown rendered with raw HTML escaped and links only to `https`, `http`, `mailto`,
  `#` or a field; the page's own CSP allows its origin and the basemap's only.
- *A page of another origin reads the API with a visitor's browser*: the REST server
  allows cross-origin requests only from the origins of `OBSERWATOR_CORS_ORIGINS` (none
  when unset), never with credentials; both servers send `X-Content-Type-Options:
  nosniff`, `Referrer-Policy: no-referrer` and a `Permissions-Policy` that denies every
  browser feature no page uses.
- *Overload*: the rate limit per client address of the GUI (`OBSERWATOR_REQUEST_LIMIT`),
  the page size limit of REST lists, the readers' limit of the GUI.

**Trust in the reverse proxy.** TLS ends at the operator's edge. The servers trust the
client address only from the proxies named by uvicorn's `FORWARDED_ALLOW_IPS`; set it to
the proxy's address, never `*` on a reachable port. Both servers listen on `127.0.0.1`
behind the proxy.

**What the operator must provide.** TLS and a reverse proxy at the edge; a rule of the
edge (SSO, Cloudflare Access, an IP list) in front of `/admin`, `/admin/*` and
`/api/admin/*` on every instance, and in front of everything when the data are private
(Obserwator has no accounts); the secret files (0600, owned by the service's user); backups
of the two roots, `state_dir` and the configuration directory; updates by installing the
next git tag in a maintenance window; the regulamin and the data sources' terms
(DEV §20) of the deployment.

**What Obserwator guarantees.** No secret in any tracked file; a start refused rather than
a wrong instance served; the same filter in both servers; no client address in its logs
or files; every change released under a tag with its CHANGELOG.
