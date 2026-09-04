<!-- refreshed: 2026-09-04 -->
# Architecture

**Analysis Date:** 2026-09-04

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│              MCP Client (Claude Desktop / Code)              │
│           stdio | SSE (/sse) | streamable-http (/mcp)        │
└──────────────────────────┬──────────────────────────────────┘
                           │  MCP protocol
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 MCP Server process (CPython 3.11+)           │
├──────────────────┬──────────────────┬───────────────────────┤
│  FastMCP server  │  Tool registry   │   HTTP transport      │
│    `main.py`     │ `tools/__init__` │  `main.py` helpers    │
│                  │ `tools/*_tools`  │  revit_get/post/image │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         └──────────────────┴─────────────────────┘
                           │  HTTP JSON, keep-alive AsyncClient
                           │  http://localhost:48884/revit_mcp/...
                           ▼
┌─────────────────────────────────────────────────────────────┐
│        pyRevit Routes server (IronPython, in-process Revit)  │
│        `startup.py` → `revit_mcp/*.py` route modules         │
└──────────────────────────┬──────────────────────────────────┘
                           │  Revit API (DB, revit.doc, Transaction)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Autodesk Revit document (.rvt)                  │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| MCP server bootstrap | Creates `FastMCP`, config, transport selection | `main.py` |
| HTTP bridge | `revit_get` / `revit_post` / `revit_image` over a shared `httpx.AsyncClient` | `main.py` |
| Tool registry | Imports and calls every `register_*_tools` | `tools/__init__.py` |
| Tool modules | Declare `@mcp.tool()` functions, marshal args, call bridge | `tools/*_tools.py` (48 tools) |
| Response formatter | Normalizes Routes dicts/errors into MCP text | `tools/utils.py` |
| Route registry | Imports and calls every `register_*_routes` at extension load | `startup.py` |
| Route modules | `@api.route()` handlers running real Revit API work | `revit_mcp/*.py` |
| Revit helpers | Element IDs, name sanitizing, failure suppression | `revit_mcp/utils.py` |

## Pattern Overview

**Overall:** Two-process bridge — an async MCP façade (CPython) fronting a synchronous pyRevit Routes REST API (IronPython) embedded in Revit.

**Key Characteristics:**
- Strict mirroring: one `tools/X_tools.py` per `revit_mcp/X.py` route module
- Registration-function convention on both sides (`register_*_tools`, `register_*_routes`)
- Dependency injection: HTTP callables are passed into tool registrars rather than imported
- All Revit mutation happens behind `DB.Transaction` inside route handlers only
- Stateless request/response; no shared session state between calls

## Layers

**MCP tool layer (CPython, async):**
- Purpose: Expose Revit capabilities as MCP tools with docstring-driven schemas
- Location: `tools/`
- Contains: `@mcp.tool()` async functions, argument dicts, `format_response` calls
- Depends on: `mcp.server.fastmcp`, injected `revit_get`/`revit_post`/`revit_image`
- Used by: MCP clients through `main.py`

**Transport/bridge layer:**
- Purpose: HTTP plumbing, connection pooling, error-to-string coercion, image decoding
- Location: `main.py` (`_get_client`, `_revit_call`, `revit_image`)
- Depends on: `httpx`, `anyio`, `uvicorn` (combined mode)
- Used by: every tool module

**Revit route layer (IronPython, sync):**
- Purpose: Real BIM work — collectors, geometry, transactions, exports
- Location: `revit_mcp/`
- Contains: `@api.route(...)` handlers with `(doc, request)` signature
- Depends on: `pyrevit.routes`, `pyrevit.revit`, `pyrevit.DB`, `System`
- Used by: the bridge layer over HTTP

**Revit helper layer:**
- Purpose: Cross-version (Revit 2024–2027) compatibility and safety
- Location: `revit_mcp/utils.py`
- Contains: `get_element_id_value`, `make_element_id`, `suppress_warnings`, `sanitize_string`, `find_family_symbol_safely`

## Data Flow

### Primary Request Path

1. Client invokes a tool; FastMCP dispatches to the registered coroutine (`tools/clash_tools.py:12`)
2. Tool assembles a plain dict payload and awaits `revit_post("/clash_check/", data, ctx)` (`tools/clash_tools.py:47`)
3. `_revit_call` issues the HTTP request on the pooled client (`main.py:66`)
4. pyRevit Routes dispatches to the matching handler (`revit_mcp/clash.py`)
5. Handler reads `doc`, runs collectors/transaction, returns `routes.make_response(data=...)`
6. `_revit_call` returns parsed JSON or an `Error: <code> - <body>` string (`main.py:80`)
7. `format_response` renders success payload or an `=== ERROR DETAILS ===` block (`tools/utils.py`)

### Extension startup flow

1. pyRevit loads the extension described by `extension.json`
2. `startup.py` creates `api = routes.API("revit_mcp")`
3. `register_routes()` imports each module and calls its `register_*_routes(api)` (`startup.py:15`)
4. Any import failure is logged and re-raised, aborting registration wholesale

### Image flow

1. Tool awaits `revit_image(endpoint, ctx)` (`main.py:52`)
2. Route returns `{"image_data": "<base64 png>"}`
3. Bridge base64-decodes and wraps in `mcp.server.fastmcp.Image`

**State Management:**
- Server holds one mutable global: `_http_client` in `main.py`
- Revit-side state is the live document; nothing is cached between requests

## Key Abstractions

**Tool registrar:**
- Purpose: Group related MCP tools and receive HTTP callables by injection
- Examples: `tools/status_tools.py`, `tools/mep_tools.py`, `tools/colors_tools.py`
- Pattern: `def register_X_tools(mcp, revit_get, revit_post, revit_image=None)` with nested `@mcp.tool()` coroutines

**Route registrar:**
- Purpose: Group related Revit endpoints under the `revit_mcp` API namespace
- Examples: `revit_mcp/document.py:16`, `revit_mcp/tags.py:18`
- Pattern: `def register_X_routes(api)` with nested `@api.route("/name/", methods=[...])` handlers taking `(doc, request)`

**Response envelope:**
- Purpose: Uniform success/failure shape across ~50 endpoints
- Examples: `routes.make_response(data={"status": "success", "message": ...})`, error form `data={"error": ...}, status=4xx/5xx`
- Consumed by: `format_response` in `tools/utils.py`

**Failure suppressor:**
- Purpose: Keep the headless Routes server from blocking on Revit modal dialogs
- Examples: `_FailureSwallower` and `suppress_warnings` in `revit_mcp/utils.py`
- Pattern: Called immediately after `transaction.Start()`

## Entry Points

**`main.py` (`__main__`):**
- Location: `main.py:120`
- Triggers: MCP client spawn or manual launch
- Responsibilities: Selects transport from argv — default `stdio`, `--sse`, `--http`/`--streamable-http`, `--combined`

**`run_combined_async` :**
- Location: `main.py:92`
- Triggers: `--combined` flag
- Responsibilities: Merges SSE routes into the streamable-http Starlette app and serves both under one uvicorn instance

**`startup.py`:**
- Location: `startup.py:113` (module-level `register_routes()` call)
- Triggers: pyRevit extension load inside Revit
- Responsibilities: Registers all 40+ routes; raises on failure

## Architectural Constraints

- **Two runtimes:** `tools/` and `main.py` run on CPython 3.11+; `revit_mcp/` runs on IronPython inside Revit. Never use f-strings, `list[str]`, or CPython-only libs in `revit_mcp/` — those modules use `.format()` and `# -*- coding: UTF-8 -*-` headers.
- **Threading:** MCP side is a single asyncio loop; Revit side is single-threaded on the Revit API context. Concurrency at the tool layer does not buy parallelism in Revit.
- **Transactions:** Every document mutation must be wrapped in `DB.Transaction` and paired with `suppress_warnings(t)`. Exception: `Save`/`SaveAs` must NOT run in a transaction (`revit_mcp/document.py`).
- **Import path quirk:** `revit_mcp/*.py` import helpers as `from utils import ...` (top-level), not `from .utils import ...`, because pyRevit puts the module directory on `sys.path`. `tools/utils.py` is a distinct, unrelated module.
- **Global state:** `_http_client` in `main.py` is the only module-level mutable singleton.
- **Fixed port:** Routes port is hardcoded to `48884`; only host is configurable via `REVIT_HOST`.
- **Cold start:** ~0.9s stdio initialize is the framework import floor (`tests/test_init_latency.py`).

## Anti-Patterns

### Errors returned as strings instead of raised

**What happens:** `_revit_call` swallows every exception and returns `"Error: {e}"` (`main.py:82`).
**Why it's wrong:** Type of a tool result silently changes from `dict` to `str`; callers must handle both, and `format_response` is the only thing preventing garbled output.
**Do this instead:** Always pass results through `format_response` (`tools/utils.py`) and never index a bridge result directly.

### Treating any status-less dict as an error

**What happens:** Earlier logic flagged data-bearing responses without a `status` key as failures, so `get_revit_model_info` rendered an `=== ERROR DETAILS ===` header.
**Why it's wrong:** Real data was hidden behind a false error.
**Do this instead:** Failure is signalled only by an `error` key or an explicit failure status — the current rule in `tools/utils.py`; `tests/test_model_info_format.py` guards it.

### Mutating the document outside a transaction

**What happens:** Direct `doc.Create...` / parameter `Set` calls without `DB.Transaction`.
**Why it's wrong:** Revit throws, or a modal dialog blocks the Routes server indefinitely and all subsequent requests time out.
**Do this instead:** Follow `revit_mcp/colors.py:779` — `with DB.Transaction(doc, "…") as t:` plus `suppress_warnings(t)`.

### Bare `ElementId(int)` / `.IntegerValue`

**What happens:** Version-specific ID handling breaks across Revit 2024–2027.
**Why it's wrong:** `ElementId.Value` (Int64) replaced `IntegerValue` in newer releases.
**Do this instead:** Use `get_element_id_value` and `make_element_id` from `revit_mcp/utils.py`.

## Error Handling

**Strategy:** Defensive at every boundary — never let an exception escape a handler or a bridge call.

**Patterns:**
- Route handlers: whole body in `try/except`, `logger.error(...)`, `routes.make_response(data={"error": str(e)}, status=500)`
- Missing document: `status=503` with `{"error": "No active Revit document"}`
- Bad payload: `status=400`; not found: `status=404`
- Bridge: exceptions become `"Error: {e}"` strings
- Tool layer: `format_response` emits `=== ERROR DETAILS ===` with details, traceback, and extra debug fields

## Cross-Cutting Concerns

**Logging:** `logging.getLogger(__name__)` per module on the Revit side, written to the pyRevit log. The MCP side logs via FastMCP/uvicorn settings; no custom logger.
**Validation:** Manual, in-handler — presence checks on required keys, `isinstance` guards, explicit JSON parsing of `request.data`. No pydantic models on the Revit side; MCP-side schemas are inferred from tool type hints.
**Encoding:** All Revit strings pass through `sanitize_string`/`normalize_string` to stay ASCII-safe for JSON.
**Units:** Revit internal units are feet; modules define conversions such as `MM_TO_FEET = 1.0 / 304.8` (`revit_mcp/tags.py:16`).
**Authentication:** None — the bridge assumes a loopback-only Routes server.

---

*Architecture analysis: 2026-09-04*
