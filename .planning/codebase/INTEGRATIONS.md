# External Integrations

**Analysis Date:** 2026-09-04

The project has exactly **one** external integration boundary: a local, unauthenticated HTTP link to the pyRevit Routes server. There are no cloud services, no databases, no auth providers, and no outbound network traffic to the internet.

## APIs & External Services

**Autodesk Revit (via pyRevit Routes) — the only integration:**
- Service: pyRevit Routes HTTP server hosted inside the running Revit process.
- Base URL: `http://{REVIT_HOST}:48884/revit_mcp` (`main.py:20-23`).
- Client: `httpx.AsyncClient`, single pooled instance (max 10 keep-alive / 20 total connections) created in `main.py:_get_client`.
- Call helpers: `revit_get`, `revit_post`, `revit_image` in `main.py`, injected into every tool module by `tools/__init__.py:register_tools`.
- Auth: **none**. No API key, token, or TLS — plain HTTP on loopback.
- Server side: routes registered against `routes.API("revit_mcp")` in `startup.py:12`, with 22 `register_*_routes(api)` calls covering status, model info, views, placement, colors, code execution, building, editing, structure, annotation, analysis, documentation, rooms, view management, tags, transforms, MEP, parameters, interop, detail, clash, and document modules under `revit_mcp/`.
- Traffic shape: 12 GET call sites, 35 POST call sites, 1 image call site across `tools/`.

**Revit .NET API (in-process, Revit side):**
- Reached through `pyrevit.DB` / `pyrevit.revit` in every `revit_mcp/*.py`.
- Direct CLR access exposed to callers of the code-execution route: `clr` and `System` are pre-imported into the exec namespace (`revit_mcp/code_execution.py:66-72`).

## Data Storage

**Databases:**
- None. No ORM, no connection string, no query layer anywhere in the repo.

**File Storage:**
- Local Windows filesystem only, driven through the Revit API:
  - IFC export writes to a caller-supplied directory via `doc.Export(...)` (`revit_mcp/interop.py:96`); supports `IFC2x3` (default) and `IFC4` (`revit_mcp/interop.py:64-73`).
  - External file link/import via `doc.Import(...)` and link options (`revit_mcp/interop.py:159-213`); accepted types are DWG, DXF, DGN, SAT, SKP, 3DM, RVT with `DWGImportOptions`, `SATImportOptions`, `SKPImportOptions`.
  - Model persistence: `doc.Save()` / `doc.SaveAs(model_path, SaveAsOptions())` in `revit_mcp/document.py:69-89`, deliberately executed outside any `Transaction`.
  - Documentation output defaults under `USERPROFILE` (fallback `HOME`, then `C:\`) — `revit_mcp/documentation.py:332`.
  - `tempfile` used for scratch output in one Revit-side module.
- View images are returned inline as base64 PNG decoded into an `mcp.server.fastmcp.Image` (`main.py:revit_image`), never persisted by the server.

**Caching:**
- None, other than HTTP keep-alive connection pooling in `main.py:_get_client`.

## Authentication & Identity

**Auth Provider:**
- None. The MCP server exposes all 48 tools with no authentication and binds to `127.0.0.1:8000`; the Routes server likewise accepts unauthenticated calls on `:48884`.
- Trust model is "loopback only". Setting `REVIT_HOST` to a non-local host would send unauthenticated model-mutating and arbitrary-code-execution requests over the network in cleartext.

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry/APM integration.

**Logs:**
- Revit side: stdlib `logging` module-level loggers (`logger = logging.getLogger(__name__)`) in `revit_mcp/__init__.py` and every route module; errors logged in `startup.py:register_routes` and per-handler `except` blocks.
- MCP server side: uvicorn logging at `mcp.settings.log_level` for HTTP transports (`main.py:run_combined_async`); stdio mode emits nothing. Tool-level failures are returned to the client as `"Error: ..."` strings from `main.py:_revit_call`, not logged.
- Response normalization for the client happens in `tools/utils.py:format_response`, which treats a dict as an error only when it has an `error` key or a `status` of error/failed/failure/exception.

## CI/CD & Deployment

**Hosting:**
- Not hosted. Runs locally: `uv run main.py` for stdio, plus `--sse`, `--streamable-http` (`http://localhost:8000/mcp`), and `--combined` modes (`main.py:__main__`).
- The Revit half deploys as a pyRevit extension — copied to `%APPDATA%\pyRevit\Extensions\` as `mcp-server-for-revit-python.extension`, or installed from the pyRevit Extensions panel using `extension.json`.

**CI Pipeline:**
- None. No `.github/`, no workflow files. Tests are run manually as scripts (`tests/test_init_latency.py`, `tests/test_model_info_format.py`).

## Environment Configuration

**Required env vars:**
- None are required. `REVIT_HOST` (`main.py:21`) is optional and defaults to `localhost`.

**Secrets location:**
- No secrets exist in this project. No `.env` file is present; `.gitignore` covers only `__pycache__`, build artifacts, `.venv`, and `*TODO.md`.

## Webhooks & Callbacks

**Incoming:**
- The pyRevit Routes endpoints under `/revit_mcp/...` are the only HTTP surface on the Revit side (e.g. `/revit_mcp/status/`, `/revit_mcp/execute_code/` — `revit_mcp/code_execution.py:21`). These are request/response, not webhooks.
- The MCP server exposes `/sse`, `/messages/`, and `/mcp` when run with an HTTP transport.

**Outgoing:**
- None. The server never calls out beyond `REVIT_HOST:48884`.

## Integration Risks

- `POST /revit_mcp/execute_code/` runs caller-supplied IronPython with `exec` in a namespace pre-loaded with `clr`, `System`, `DB`, and the live document (`revit_mcp/code_execution.py:61-81`) — full arbitrary code execution inside Revit, gated only by network reachability.
- Modal-dialog deadlock is the main liveness hazard for the integration: an unhandled Revit warning would block the Routes server indefinitely. Mitigated by `suppress_warnings` / `_FailureSwallower` in `revit_mcp/utils.py`, which must be called right after every `transaction.Start()`.
- No retry or circuit breaking on the httpx client; a Revit-side hang surfaces as a 30s (or 60s for images) timeout returned as an error string.

---

*Integration audit: 2026-09-04*
