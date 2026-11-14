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
  their token (`OBSERWATOR_STORE_WRITES_ENABLED`, `OBSERWATOR_STORE_WRITE_TOKEN`, header
  `X-API-Key`) and the file of the REST API keys of `obserwator admin` (`api_keys.json`);
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
- the MCP server (`obserwator mcp` over stdio and `/mcp` of the REST server), including
  the sandbox of writes (`--allow-writes`, `--allow-dir`): any write or path outside the
  allowed directories;
- writes to the store and to output files: path traversal, overwriting files outside the
  target, corruption of committed versions;
- unsafe parsing of downloaded archives (ZIP, CSV, JSON) and of store files;
- the supply chain of the package.

Problems of the IMGW-PIB or ČHMÚ services themselves are out of scope; report them to the
institute.
