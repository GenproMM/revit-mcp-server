# Phase 2: Live identity, ambiguity refusal, and multi-document addressing — Pattern Map

**Mapped:** 2026-10-14
**Files analysed:** 33 logical file/file-family changes (including the mandatory contract sweep across existing tools and mutation routes)
**Analogs found:** 26 / 33; the remaining items are deliberate new capabilities or live-only decision gates

> **Source-revision note.** This mapper runs in the isolated worktree
> `C:/Users/Admin/source/repos/revit-mcp-server/.claude/worktrees/agent-afc72d5c43f9a72af`, which is at the older checkout `40af5a7`. The phase context and implementation analogs are from the tracked completed Phase-1 revision `e4181ce` available in this repository's object database. Every analog path below is a tracked source path in that revision, never a capability mirror or generated/runtime copy. The output file itself belongs in this isolated worktree and must be transferred by the controller.

## File Classification

| New/Modified File | Role | Data flow | Closest tracked analog | Match quality |
|---|---|---|---|---|
| `bridge.py` | service / transport boundary | request-response, concurrency | `bridge.py` | exact role; target-aware extension is new |
| `tools/target_tools.py` (new) | controller/tool registrar | request-response, discovery | `tools/process_tools.py` | role-match |
| `tools/status_tools.py` | controller/tool registrar | request-response | `tools/status_tools.py` | exact |
| `tools/model_tools.py` | controller/tool registrar | request-response | `tools/model_tools.py` | exact |
| `tools/*_tools.py` that call Revit | controller/tool registrars | request-response | `tools/editing_tools.py`, `tools/document_tools.py` | role-match contract sweep |
| `tools/*_tools.py` for mutating routes | controller/tool registrars | request-response / CRUD | `tools/editing_tools.py` | exact flow |
| `revit_mcp/identity.py` (new) | utility / model descriptor | transform, request-response | `revit_mcp/status.py`, `revit_mcp/utils.py` | partial; process/document identity is new |
| `revit_mcp/documents.py` (new) | route / service | request-response, event-driven UI activation | `revit_mcp/worksharing.py` | role-match; activation semantics require G4 |
| `revit_mcp/status.py` | route | request-response | `revit_mcp/status.py` | exact |
| `revit_mcp/<mutation-route modules>.py` | routes | CRUD / request-response | `revit_mcp/editing.py`, `revit_mcp/document.py` | exact guard/response shape |
| `revit_mcp/placement.py` (existing `list_levels`) | route | request-response / transform | `revit_mcp/placement.py:617-676` | partial; existing route is not yet proven safe for inactive docs |
| `revit_mcp/model_info.py` | route | request-response / transform | `revit_mcp/model_info.py:20-351` | anti-analog: do **not** retrofit as safe read |
| `startup.py` (conditional only) | config / registration bootstrap | event-driven | `startup.py` | exact registration pattern; no wrapper until G1 passes |
| `tests/unit/test_target_resolution.py` (new) | test | request-response / transform | `tests/unit/test_bridge_serialization.py` | exact test seam |
| `tests/unit/test_target_locks.py` (new) | test | concurrency | `tests/unit/test_bridge_serialization.py` | exact |
| `tests/unit/test_identity_rendering.py` (new) | test | transform | `tests/unit/test_status_target.py` | exact |
| `tests/unit/test_document_contracts.py` (new) | test | transform / request-response | `tests/unit/test_conventions.py`, `tests/unit/test_status_target.py` | role-match |
| `tests/test_phase2_live_identity.py` (new) | standalone live acceptance test | request-response, event-driven | `tests/test_two_instance_targets.py` | exact test-tier/bench shape |
| `tests/unit/tool_manifest.txt` | config / contract | batch | `tests/unit/tool_manifest.txt` | exact |

### Contract-sweep inventory

The planner must treat these as **explicit affected file families**, rather than mistakenly limiting Phase 2 to the new routes:

1. **Target argument:** every Revit-facing `@mcp.tool()` in all existing `tools/*_tools.py` modules receives an optional per-call `target` before `ctx`, forwards it through the injected transport, and documents it. The process-only local functions (`get_revit_process_status`, `start_revit`) need a deliberate review: they cannot silently keep probing the legacy fixed bridge when the contract changes.
2. **Document argument:** every tool that can mutate a Revit document receives optional `document` before `ctx`, includes it in the POST payload, and documents the one-eligible-document default / multiple-document refusal / inactive-document 412 rule. The source inventory shows mutation-facing modules: `analysis`, `annotation`, `building`, `clash`, `colors` (only mutations), `detail`, `document`, `documentation` (create operations), `editing`, `family`, `interop`, `mep`, `parameter`, `room`, `structure`, `tag`, `transform`, `view_management`, and `worksharing` (where semantically document-bound). `code_execution` is a security-sensitive exception: do not broaden its arbitrary-code surface without an explicit decision; Phase 2 must not use it as a substitute for typed routes.
3. **Revit-side mutation guards/attribution:** mirror the same mutation-route set. A central helper may reduce duplication only after G1 proves it preserves pyRevit's injected handler semantics. Otherwise make explicit per-route changes; never put an unverified universal decorator in front of all routes.
4. **Safe reads:** only two *new, narrow* document-addressed reads are in scope: summary and levels. Existing `/model_info/` and `/list_levels/` are sources for data extraction, not proof that their current routes are safe for inactive documents.

## Pattern Assignments

### `bridge.py` (transport service, target-aware request-response and keyed serialization)

**Analog:** `bridge.py` (tracked Phase-1 source, lines 72-160, 184-240, 243-366)

**Imports/config/client pattern** (lines 72-145):
```python
import os
import json
import base64
import asyncio
import httpx
from typing import Optional, Dict, Any, Union

_http_client: Optional[httpx.AsyncClient] = None
_lock: Optional[asyncio.Lock] = None

def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            base_url=BASE_URL,
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _http_client
```

Copy the lazy event-loop-bound state and `trust_env=False`; refactor the scalar client/lock to maps keyed by a **validated incarnation**. Do not retain a global lock as a hidden fallback. Do not make a second raw HTTP path.

**Injected callable boundary** (lines 148-160):
```python
async def revit_get(endpoint: str, ctx: Any = None, **kwargs) -> Union[Dict, str]:
    return await _revit_call("GET", endpoint, ctx=ctx, **kwargs)

revit_get.revit_target = REVIT_TARGET

async def revit_post(endpoint: str, data: Dict[str, Any], ctx: Any = None, **kwargs) -> Union[Dict, str]:
    return await _revit_call("POST", endpoint, data=data, ctx=ctx, **kwargs)
```

Preserve injected transports: tool modules must not import `bridge`. Phase 2 may extend the keyword contract with `target`, but status/identity metadata must remain accessible through the injected callable or a returned result—not a direct import.

**POST parsing/transport contract** (lines 184-207):
```python
response = await client.post(
    endpoint,
    content=json.dumps(data).encode("utf-8"),
    headers={"Content-Type": "text/plain; charset=utf-8"},
    timeout=timeout,
)
return response.json() if response.status_code == 200 else "Error: {} - {}".format(
    response.status_code, response.text
)
```

Keep this byte/body contract exactly. New `target` and `document` fields are ordinary payload/transport parameters; they must not introduce `application/json`, secret material, Phase-3/5 integrity fields, or a new client.

**Lock policy to preserve while keying by target** (lines 210-240):
```python
UNLOCKED_GET = frozenset({"status"})
NEVER_UNLOCKED = frozenset({"execute_code", "open_model", "save_document"})

def _is_locked(method: str, endpoint: str) -> bool:
    key = _route_key(endpoint)
    if key in NEVER_UNLOCKED:
        return True
    return not (method == "GET" and key in UNLOCKED_GET)
```

The replacement must keep the exact semantic: **only GET `/status/` is unlocked**. Target discovery/preflight and `/status/` handshake must not let model reads bypass the per-target lock. Separate target keys may run in parallel; different documents within one target may not.

**Bounded-wait and honest-failure pattern** (lines 275-353):
```python
if isinstance(e, _NOT_SENT_ERRORS):
    return (
        "Error: {} - could not reach Revit at {}; the request was not sent "
        "to Revit and nothing was changed.".format(name, REVIT_TARGET)
    )
return (
    "Error: {} - the request was sent to Revit but no complete response "
    "arrived within {}s; outcome UNKNOWN - the change may have been applied "
    "in Revit. Verify the model state before retrying.".format(name, timeout)
)
```

Preflight refusal (invalid/stale selector, zero/multiple listeners, PID mismatch, multiple candidates) belongs on the clearly **not sent** path. Add received process/document attribution only after an actual response was received and matched; never attach a verified identity to a timeout, failed connect, queue timeout, or pre-send refusal.

**Specific Phase-2 extension:** extract small pure helpers for strict opaque selector parsing, local listener snapshot parsing, candidate formatting, target-state eviction, incarnation comparison, and post-format identity rendering. The OS snapshot → connect interval is a TOCTOU limitation, not a guarantee to overstate. The selected port with more than one listener must return all conflicting PIDs *before* the model route is sent.

---

### `tools/target_tools.py` (new discovery tool registrar, request-response)

**Analog:** `tools/process_tools.py` (tracked source, lines 1-20, 52-86, 89-147)

**Imports/local-machine distinction** (lines 1-20):
```python
"""Revit process lifecycle tools.

Every other tool in this package is a thin wrapper over the pyRevit Routes
bridge ... These two are the exception: they are what you call when it is *not*.
They therefore talk to the local machine directly ...
"""

import asyncio
import glob
import os
import subprocess
import sys
import time

from mcp.server.fastmcp import Context
from .utils import describe_broken_path, format_response
```

Use this CPython-only location for listener/process discovery. Reuse `subprocess` but keep PowerShell/JSON parsing isolated and unit-injectable. It must report discovery failure honestly; it must not manufacture a usable target.

**Best-effort progress/error isolation** (lines 52-63):
```python
async def _say(ctx, message: str) -> None:
    if not ctx:
        return
    try:
        await ctx.info(message)
    except Exception:
        pass
```

**Registrar/tool and rendered result pattern** (lines 89-147):
```python
def register_process_tools(mcp, revit_get, revit_post=None, revit_image=None):
    _ = revit_post, revit_image

    @mcp.tool()
    async def get_revit_process_status(ctx: Context = None) -> str:
        ...
        return format_response({
            "ready": state == "ready",
            "revit_running": state != "down",
            "installed": [{"version": v, "path": p} for v, p in installed],
            "recommendation": recommendation,
        })
```

The new discovery registrar must use the canonical four registrar parameters even if it only needs `revit_get`, return `str`, and give every argument (including `ctx`) in `Args:`. Its list must expose only selectors discovered from a fresh identity handshake and must flag a same-port collision as unusable rather than listing one ambiguous candidate.

**No close analog:** there is no existing in-process multi-target discovery/selector implementation. Build it above the verified local-process + injected-transport seams, and cover selector/listener decisions with mocked OS and HTTP adapters before bench work.

---

### `tools/status_tools.py` and all tool renderers (tool controller, received-response attribution)

**Analog:** `tools/status_tools.py` (tracked source, lines 4-49)

```python
from mcp.server.fastmcp import Context
from .utils import format_response

@ mcp.tool()
async def get_revit_status(ctx: Context) -> str:
    target = getattr(revit_get, "revit_target", None)
    response = await revit_get("/status/", ctx, timeout=10.0)
    text = format_response(response)
    if target:
        text = "{}\nMCP target: {}".format(text, target)
    return text
```

(The actual decorator spelling is `@mcp.tool()`; spacing above is only to keep this map visually distinct.)

**Copy the ordering, not merely the fields:** call `format_response(response)` first, then append a visible `Process:`/`Document:` attribution suffix when and only when identity was received. `format_response` intentionally collapses a dict containing `message`, `result`, `output`, or `data`, so nested identity fields alone are insufficient. Apply the shared helper consistently to success and received non-200/error responses.

**Tool signature/docstring pattern:** `tools/document_tools.py:12-49` and `tools/editing_tools.py:12-50` demonstrate optional business arguments before `ctx` and the `data` construction boundary:
```python
async def save_document(
    file_path: str = None,
    overwrite: bool = True,
    as_central: bool = None,
    ctx: Context = None,
) -> str:
    ...
    response = await revit_post("/save_document/", data, ctx)
    return format_response(response)
```

For Phase 2 insert `target` and, for mutations, `document` **before** `ctx`; include both in each affected docstring's `Args:` block. Build the request data after validation and pass it via the injected `revit_post` callable. Do not change a tool to return a dict or index a possible error string.

**Tool-contract mechanical guard:** `scripts/conventions.py:421-503` (tracked source) mandates registrar arguments exactly `(mcp, revit_get, revit_post, revit_image)` and requires `async def`, `-> str`, `ctx` last, and every argument listed under `Args:`. This makes the broad signature rollout a testable requirement, not a review convention.

---

### `tools/model_tools.py` and safe-read tool surface (controller, request-response/transform)

**Analog:** `tools/model_tools.py` (tracked source, lines 4-29)

```python
def register_model_tools(mcp, revit_get, revit_post=None, revit_image=None):
    _ = revit_post, revit_image

    @mcp.tool()
    async def list_levels(ctx: Context = None) -> str:
        ...
        response = await revit_get("/list_levels/", ctx)
        return format_response(response)
```

Use the thin injected transport → format-response shape for `list_documents`, explicit activation, addressed summary, and addressed levels tools. Do **not** simply add `document` to legacy `get_revit_model_info`/`list_levels` and send their old endpoints: point them to the new narrow document-addressed endpoints only after G3 passes. Their docstrings must say that inactive-document reads are supported only on the measured summary/levels surface and that no UI switch is implicit.

---

### `revit_mcp/identity.py` (new IronPython utility/model descriptor)

**Closest analogs:** `revit_mcp/status.py:7-12, 38-90`; `revit_mcp/utils.py` via the imported `sanitize_string` pattern.

**IronPython import/format/error pattern** from `revit_mcp/status.py:7-12, 38-90`:
```python
from pyrevit import routes
import logging
from .utils import sanitize_string

logger = logging.getLogger(__name__)

try:
    from pyrevit import revit
    doc = revit.doc
    ...
    return routes.make_response(data=payload)
except Exception as e:
    logger.error("Health check failed:{}".format(str(e)))
    return routes.make_response(data={
        "status": "unhealthy",
        "revit_available": False,
        "error": str(e),
        "api_name": "revit_mcp"
    }, status=503)
```

This helper is an IronPython-3.4 file: UTF-8 encoding cookie on line 1; no f-strings, `async`, `pathlib`, `typing`, `dataclasses`, or `secrets`; relative sibling imports only. Build opaque process/document descriptors through allowed Revit/.NET facilities only after G1/G2 establish what is stable. `title` and `path` are presentation fields, never the unique key. Avoid caching `revit.doc` or a `Document` object between requests.

**No exact analog:** the codebase has no session-token/document-token registry. Keep the new module a small pure-ish descriptor/resolution provider invoked in the API context; do not import one route domain from another. `startup.py` discovery treats helpers without a registrar as helpers, which is acceptable.

---

### `revit_mcp/documents.py` (new route service: list, resolve, activate, narrow reads)

**Analog:** `revit_mcp/worksharing.py:275-350, 352-424` (route shape and guarded POST); `revit_mcp/placement.py:617-676` (document-only level collection).

**Route/validation/error shape** from `revit_mcp/worksharing.py:278-350`:
```python
@api.route("/model_worksets/", methods=["POST"])
def model_worksets(doc, request):
    try:
        data = {}
        if request and request.data:
            data = parse_request_data(request.data)

        file_path = data.get("file_path")
        if not file_path:
            return routes.make_response(
                data={"error": "file_path is required (full path to a .rvt file)"},
                status=400,
            )
        ...
    except Exception as e:
        logger.error("model_worksets failed: {}".format(str(e)))
        return routes.make_response(data={"error": str(e)}, status=500)
```

**Existing pure-document level collector to copy narrowly** from `revit_mcp/placement.py:625-676`:
```python
if not doc:
    return routes.make_response(
        data={"error": "No active Revit document"}, status=503
    )
levels = (
    DB.FilteredElementCollector(doc)
    .OfCategory(DB.BuiltInCategory.OST_Levels)
    .WhereElementIsNotElementType()
    .ToElements()
)
...
return routes.make_response(data={
    "levels": levels_info,
    "total_levels": len(levels_info),
    "status": "success",
})
```

Implement list/resolve/activation and the new summary/levels endpoints as non-raising handlers that parse POST through `parse_request_data(request.data)` and return `routes.make_response`. Each request must enumerate current open documents and resolve the opaque selector anew. A closed selector must name that failure; it must never fall back to the active document. Activation is a separate action and has a live G4 gate for saved, unsaved, and workshared documents; do not copy `/open_model/` as proof of already-open activation behavior.

**Safe-read anti-pattern:** `revit_mcp/model_info.py:20-39` expressly does this:
```python
@api.route("/model_info/", methods=["GET"])
def get_model_info():
    try:
        doc = revit.doc
        if not doc:
            return routes.make_response(
                data={"error": "No active Revit document"}, status=503
            )
```

Never retrofit or advertise it as document-addressed safe reading. It re-fetches active `revit.doc` and the rest of its large collector surface is unmeasured. The narrow routes must accept/use only the resolved `Document`, avoid `revit.doc`/`UIDocument`, and remain provisional until the A-active/B-inactive live UI/data test passes.

---

### `revit_mcp/status.py` (route, process identity request-response)

**Analog:** `revit_mcp/status.py:15-92`

```python
def register_status_routes(api):
    @api.route('/status/', methods=["GET"])
    def revit_status(verbose=None):
        try:
            from pyrevit import revit
            want_verbose = str(verbose).lower() in ("true", "1", "yes")
            ...
            doc = revit.doc
            if doc:
                payload = {
                    "status": "active",
                    "health": "degraded" if degraded else "healthy",
                    "revit_available": True,
                    "document_title": sanitize_string(doc.Title) if doc.Title else "Untitled",
                    "api_name": "revit_mcp",
                }
                return routes.make_response(data=payload)
            ...
        except Exception as e:
            ...
```

Extend this lightweight, doc-optional endpoint with PID, Revit version, actual port, and an once-per-process session token from `identity.py`. Preserve health/registry reporting and the 503 behavior when no document is active. It is the handshake endpoint, so it must remain cheap and is the sole unlocked GET; it must not turn into a document guard or a mutation route.

---

### Existing Revit mutation route modules (routes, CRUD/request-response)

**Primary analog:** `revit_mcp/editing.py:18-110, 112-155`; **Save exception:** `revit_mcp/document.py:21-132`.

**Mutation guard + transaction pattern** from `revit_mcp/editing.py:18-57`:
```python
@api.route("/delete_elements/", methods=["POST"])
def delete_elements_handler(doc, request):
    try:
        if not doc:
            return routes.make_response(
                data={"error": "No active Revit document"}, status=503
            )
        if not request or not request.data:
            return routes.make_response(data={"error": "No data provided"}, status=400)
        data = parse_request_data(request.data)
        ...
        t = DB.Transaction(doc, "Delete Elements via MCP")
        t.Start()
        suppress_warnings(t)
```

At the beginning of each affected mutation handler, replace only the active-doc assumption with the shared/proven document resolution result: explicit selector must resolve exactly one current open document; omitted selector is permitted only when exactly one eligible document exists; multiple candidates visibly refuse; explicit non-active document visibly returns HTTP 412; no path auto-activates. Resolve/attach the actual document descriptor at execution time, then include it in every received response, including route errors.

Do not disturb existing transaction semantics. Every mutation still starts a transaction and calls `suppress_warnings(t)` immediately afterwards. Preserve rollback/error response behavior:
```python
except Exception as e:
    logger.error("Failed to delete elements: {}".format(str(e)))
    return routes.make_response(
        data={"error": str(e), "traceback": traceback.format_exc()}, status=500
    )
```

**Save exception:** `revit_mcp/document.py:21-132` has the same POST/validation/non-raising shape but intentionally does **not** start a transaction:
```python
@api.route("/save_document/", methods=["POST"])
def save_document(doc, request):
    try:
        ...
        data = parse_request_data(request.data)
        ...
        doc.Save()
        return routes.make_response(data={"status": "success", ...})
    except Exception as e:
        return routes.make_response(data={"error": str(e)}, status=500)
```

Do not add a transaction around `Save`/`SaveAs`; only add document resolution and request-time attribution.

**Response-format companion:** `tools/utils.py:14-107` is the reason that a route's metadata cannot be considered model-visible on its own. It treats a dict as error only if `error` is truthy or `status` is one of `error`, `failed`, `failure`, `exception`; preserve this predicate and append attribution after it renders.

---

### `startup.py` (conditional registration bootstrap, event-driven)

**Analog:** `startup.py:37-126`

```python
def _domain_modules(package):
    package_dir = package.__path__[0]
    names = []
    for entry in os.listdir(package_dir):
        if not entry.endswith(".py") or entry.startswith("_"):
            continue
        names.append(entry[:-3])
    names.sort()
    return names

for name in _domain_modules(revit_mcp):
    try:
        module = __import__("{}.{}".format(_PACKAGE, name), fromlist=[name])
        registrar = _registrar_in(module)
        ...
        registrar(api)
    except Exception as exc:
        registry.FAILED[name] = "{}: {}".format(type(exc).__name__, str(exc))
```

A new `documents.py` route registrar is discovered automatically—no barrel list edit is needed. **Do not modify `startup.py` to install a global wrapper unless G1 has first inspected actual `routes.API.route` signature inspection, doc/request injection, and ExternalEvent dispatch and the live non-mutating probe proves exact preservation.** If G1 fails, use explicit route changes instead. In either case, imports in this Revit half stay compatible with IronPython and route errors return responses rather than escape.

---

### Unit tests: target resolution and keyed locks

**Analog:** `tests/unit/test_bridge_serialization.py:1-113` (tracked Phase-1 source)

```python
@pytest.fixture(autouse=True)
def _reset_bridge_state():
    bridge._lock = None
    bridge._http_client = None
    yield
    bridge._lock = None
    bridge._http_client = None

def _install_client(handler):
    bridge._http_client = httpx.AsyncClient(
        base_url="http://test:1/revit_mcp",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
```

```python
@pytest.mark.anyio
async def test_second_post_waits_for_the_first():
    gate = _Gate()
    _install_client(gate.handler)
    first = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)
    second = asyncio.ensure_future(bridge.revit_post("/p2/", {}))
    await asyncio.sleep(0.05)
    assert gate.seen == ["/revit_mcp/p1/"]
```

Adapt the fixture to reset/close all target-keyed client/lock state. Keep `httpx.MockTransport`, `anyio_backend == "asyncio"`, no network and no Revit. Assert:

- malformed/omitted/multiple target selector decision table;
- zero/multiple listener and selector-PID mismatch return refusal **without HTTP model-route send**;
- handshake session/PID/port mismatch requires rediscovery and does not reuse stale state;
- same validated target serializes all non-status calls; distinct validated targets overlap; a restarted token gets a new lock key;
- the Phase-1 exact `/status/` exemption regression tests remain true.

### Unit tests: identity rendering and tool schema

**Analog:** `tests/unit/test_status_target.py:17-84` (tracked Phase-1 source)

```python
class _FakeMCP(object):
    def __init__(self):
        self.tools = {}
    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator

async def fake_get(endpoint, ctx=None, timeout=30.0):
    calls.append((endpoint, timeout))
    return response
```

```python
out = _run_status(_make_get({"status": "active", "message": "hello"}))
assert "hello" in out
assert out.splitlines()[-1] == "MCP target: 127.0.0.1:48885"
```

Use this fake registrar/callable seam for new tools and renderer helpers. Test identity suffix survival for `message`, `result`, `data`, normal structured success, error dict, and error string. Separately test that pre-send/timeout/outcome-unknown strings **do not claim received identity**. Add a source/schema test across all affected mutation tools for `target` and `document` before `ctx` and both names in `Args:`; do not weaken `test_conventions`.

**Manifest analog:** `tests/unit/test_registration.py:105-126` reads `tests/unit/tool_manifest.txt` and fails for both missing and undeclared tools. Add every new MCP tool in the same change as its registrar; do not hand-maintain a registration barrel.

---

### `tests/test_phase2_live_identity.py` (new standalone live acceptance test)

**Analog:** `tests/test_two_instance_targets.py:1-128` (tracked Phase-1 source)

```python
"""Two MCP entries, two Revit ports, one client ...

Older tier: a standalone script, run on its own, excluded from pytest.
"""
...
MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
...
asyncio.run(main())
```

```python
def _listeners(ports):
    """Best effort: {port: [pids]} of listening sockets, via PowerShell."""
    script = (
        "Get-NetTCPConnection -State Listen -LocalPort {} "
        "-ErrorAction SilentlyContinue | "
        "Select-Object LocalPort,OwningProcess | ConvertTo-Json -Compress"
    ).format(",".join(str(p) for p in ports))
```

Copy the standalone `asyncio.run`, absolute-`main.py` path, explicit sentinel, and live/offline precondition documentation—not its old two-entry architecture. Phase 2's harness must exercise one shared MCP entry with per-call selectors. It records observations (not fabricated pass claims) for G1–G6: identity fields and restart staleness, collision refusal and PIDs/no-send, two same-title processes, list/close/retry documents, explicit activation, UI unchanged and correct data for addressed inactive summary/levels, and the `param-write-rolls-back` diagnosis. Any `revit_mcp/` change requires full Revit restart before this test; Reload is explicitly unsafe.

## Shared Patterns

### Two-runtime boundary

**Sources:** `CLAUDE.md:10-35`; `bridge.py:72-77`; `revit_mcp/status.py:1-12`

- CPython files (`bridge.py`, `tools/`, `tests/`) can use async, modern annotations, `asyncio`, `httpx`, and f-strings if desired.
- IronPython route/helper files (`startup.py`, `revit_mcp/`) require a UTF-8 cookie on line 1, synchronous handlers, `"{}".format(...)`, no f-strings or modern typing, and relative imports such as `from .utils import ...`.
- The two halves communicate only over local HTTP. Do not import `revit_mcp` on the CPython test side or have tools import `bridge`.

### Route parsing and non-raising error contract

**Source:** `revit_mcp/document.py:21-45`, `revit_mcp/editing.py:18-39`

```python
try:
    if not doc:
        return routes.make_response(
            data={"error": "No active Revit document"}, status=503
        )
    if not request or not request.data:
        return routes.make_response(data={"error": "No data provided"}, status=400)
    data = parse_request_data(request.data)
    ...
except Exception as e:
    logger.error("...: {}".format(str(e)))
    return routes.make_response(data={"error": str(e)}, status=500)
```

Apply to new document/activation/safe-read POST routes and modified mutation routes. Parse POST only with `parse_request_data`; selectors must reject malformed, unknown, ambiguous, or closed values explicitly. Add `412` only for the locked explicit-inactive mutation condition; do not silently activate or fall back.

### Tool rendering and received identity

**Sources:** `tools/utils.py:14-107`; `tools/status_tools.py:39-49`

```python
text = format_response(response)
if target:
    text = "{}\nMCP target: {}".format(text, target)
return text
```

Use one shared Phase-2 renderer that appends *received* target/document identity after formatting. Preserve `format_response`'s error predicate; identity fields must not cause a data dict to be classified as an error. A selector/preflight/queue/connect failure reports the correct honest state but no verified answering process/document.

### Serialization and failure honesty

**Source:** `bridge.py:210-240, 275-353`

- Only GET `/status/` skips the target-local queue.
- The Phase-2 keyed lock covers calls made by this one MCP server process only; it is not cross-session/curl serialization and does not close backlog 999.1.
- Pre-send refusal says nothing was sent. Post-send incomplete POST says outcome is unknown. The port-snapshot race must be documented narrowly rather than promised away.

### Registration and manifest

**Sources:** `tools/__init__.py:61-104`; `startup.py:73-126`; `tests/unit/test_registration.py:105-126`

New `tools/target_tools.py` and `revit_mcp/documents.py` are convention-discovered. Their registrar names must match the patterns, and every new tool name must be added to `tests/unit/tool_manifest.txt`. No static barrel/import list should be introduced.

### Required decision gates, not patterns to paper over

1. **G1:** inspect real pyRevit Routes signature inspection/injection/ExternalEvent behavior and prove a non-mutating probe before using a global wrapper.
2. **G2:** live-test a document token against duplicate saved/unsaved titles and closure; title/path are not stable keys.
3. **G3:** prove only new narrow summary/levels reads return B while A stays active in UI. On failure, refuse—never auto-switch.
4. **G4:** prove explicit activation for already-open saved/unsaved/workshared states before advertising it.
5. **G5:** live same-port collision must list PIDs and avoid sending the requested route.
6. **G6:** repeat and record the param-write-rolls-back outcome with visible identity; do not infer a verdict.

## No Analog Found

| File / change | Role | Data flow | Reason / planner instruction |
|---|---|---|---|
| `tools/target_tools.py` selector/discovery semantics | controller | discovery/request-response | No existing one-entry, incarnation-qualified multi-target tool; compose local `subprocess` discovery with bridge transport and unit seams. |
| `revit_mcp/identity.py` session + open-document opaque tokens | utility/model | transform | No registry/token equivalent exists. Establish mechanism only after G1/G2. |
| `revit_mcp/documents.py` explicit activation | route/service | event-driven UI activation | Existing `/open_model/` opens a path and is not proof of activating an already-open document. Gate G4 first. |
| Target-keyed bridge client/lock map | service | concurrency | Current bridge is intentionally one fixed target/one global lock. Preserve its invariants while replacing scalar state. |
| Inactive-document summary/levels support | route | request-response | Current model info is actively unsafe as an analog; existing levels collector is only a narrow data-loop analog. Gate G3 first. |
| Full route-wrapper in `startup.py` | middleware | request-response | Injection semantics are unverified. Conditional design only; no wrapper if G1 fails. |

## Metadata

**Analog search scope:** tracked Phase-1 source revision `e4181ce`: `bridge.py`, `main.py`, `startup.py`, `tools/`, `revit_mcp/`, `tests/unit/`, `tests/`, `scripts/conventions.py`
**Tracked-source verification:** verified through the local repository object database (`git show`/`git ls-tree` against `e4181ce`); no `.gsd`, plugin mirror, generated, or runtime path appears above
**Strong analogs used:** bridge transport/serialization, status rendering, process tool discovery, worksharing route lifecycle, placement levels collector, editing transaction route, document save exception, convention tests, bridge MockTransport tests, status-target rendering tests, two-instance standalone harness
**Pattern extraction date:** 2026-10-14
