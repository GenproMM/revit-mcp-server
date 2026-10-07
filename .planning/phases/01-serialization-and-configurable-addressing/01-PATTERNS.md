# Phase 1: Serialization and configurable addressing - Pattern Map

**Mapped:** 2026-10-06
**Files analyzed:** 12 (3 new, 9 modified)
**Analogs found:** 11 / 12 (CPython side only; no `revit_mcp/` edits)

All analog paths below are git-tracked (checked: `tests/unit/conftest.py` tracked; `bridge.py` does not exist yet).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `bridge.py` (NEW) | service (transport) | request-response + lock | `main.py:21-102` (moved code) | exact (extract + extend) |
| `main.py` (MOD) | config / wiring | request-response | itself | exact |
| `tools/status_tools.py` (MOD) | tool | request-response | itself (`get_revit_status`) | exact |
| `tools/process_tools.py` (MOD, docstring `start_revit` only, Pitfall 8) | tool | request-response | itself, `_say` at 52-63 | exact |
| `tests/unit/test_bridge_serialization.py` (NEW) | test | event-driven (async) | RESEARCH.md skeleton lines 429-451; source-text idiom from `test_local_bridge_transport.py` | role-match (no async test exists yet) |
| `tests/unit/conftest.py` (MOD) | test config | n/a | itself (sys.path setup) | exact |
| `tests/unit/test_local_bridge_transport.py` (MOD) | test | file-I/O (reads source text) | itself | exact |
| `tests/unit/test_textutils.py` (MOD, lines 276-291) | test | file-I/O (reads source text) | itself | exact |
| `deploy/build-payload.cmd` (MOD) | config (build) | batch | lines 109-116 copy list | exact |
| `CLAUDE.md`, `README.md`, `deploy/README.md`, `deploy/USER-GUIDE.md` (MOD) | docs | n/a | existing sharp-edge bullets / env blocks (`USER-GUIDE.md:98-99`, `:217-218`) | exact |
| `tests/unit/tool_manifest.txt` | none | n/a | NOT touched (no new tool) | n/a |
| `scripts/conventions.py` | none | n/a | NOT touched; its registrar pin constrains design | n/a |

## Pattern Assignments

### `bridge.py` (service, request-response + serialization)

**Analog:** `main.py:21-102` (move verbatim, then wrap). Keep this function order: `_get_client`, `revit_get`, `revit_post`, `revit_image`, `_revit_call` (Pitfall 5: `test_local_bridge_transport` slices `def _get_client()` .. `async def revit_get`).

**Header and config to move/extend** (`main.py:1-9, 21-30`):
```python
# -*- coding: utf-8 -*-
import os, httpx, json, base64
from typing import Optional, Dict, Any, Union
REVIT_HOST = os.environ.get("REVIT_HOST", "localhost")
REVIT_PORT = 48884  # <- replace with _resolve_port(os.environ.get("REVIT_PORT"))
BASE_URL = f"http://{REVIT_HOST}:{REVIT_PORT}/revit_mcp"
_http_client: Optional[httpx.AsyncClient] = None
```
Note: `bridge.py` is CPython-side, so f-strings are fine, but must not import `mcp`-heavy modules (D-24). `Image`/`Context` currently come from `mcp.server.fastmcp`; `revit_image` needs `Image`. Import it lazily or from `mcp.server.fastmcp` (already loaded by main anyway); keep `Context` only as a type hint (or `Any`) so `bridge.py` imports in tests cheaply.

**Client (mandatory trust_env=False)** (`main.py:33-47`):
```python
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
Tests inject `bridge._http_client = httpx.AsyncClient(transport=MockTransport(...), base_url=..., trust_env=False)`; `_get_client()` returns it because it is not closed.

**Injected callables** (`main.py:50-73`): `revit_get`, `revit_post`, `revit_image` keep identical signatures (`endpoint, ctx=None, **kwargs`; post takes `data` second). `revit_image` stays unlocked and keeps its `timeout=60.0` and `f"Error: {e}"` shape.

**POST branch to preserve verbatim (pinned by test_textutils)** (`main.py:84-98`):
```python
        else:  # POST
            # The body is JSON, but it is deliberately declared text/plain. ...
            response = await client.post(
                endpoint,
                content=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=timeout,
            )
        return response.json() if response.status_code == 200 else f"Error: {response.status_code} - {response.text}"
```
Keep the literal `else:  # POST` marker and the `"Content-Type": "text/plain` line; `test_the_client_does_not_ask_pyrevit_to_parse_the_body` does `source[source.index("else:  # POST"):]`. Easiest: extract a `_send(method, endpoint, data, timeout, params)` helper that contains that if/else, with the marker intact.

**Lock core pattern** (RESEARCH.md Pattern 1, prototyped 16/16): `budget = None` first; `async with asyncio.timeout(timeout) as budget: async with lock: budget.reschedule(None); return await _send(...)`; `except TimeoutError: if budget is not None and budget.expired(): return "Error: ... NOT sent to Revit ..."`; classify `httpx.ConnectError/ConnectTimeout/PoolTimeout` = not sent, other `httpx.TransportError` = outcome UNKNOWN; fall back to `type(e).__name__` when `str(e)` is empty; messages never start with a digit (`process_tools.py:82-84` parses `Error: <digits>`). Emit the single wait message before entering `asyncio.timeout`.

**Allowlist (Pattern 2):** `READ_ONLY_POST` frozenset of the five D-08 routes (all appear as tool endpoints: `ai_filter`, `material_quantities`, `clash_check`, `list_category_parameters`, `model_worksets` are all in the `revit_post("/…/")` grep of `tools/`); `NEVER_UNLOCKED = {execute_code, open_model, save_document}` (all three also present in tools). `_is_locked(method, endpoint)` = POST and route key not in allowlist.

**Best-effort ctx pattern to copy for the wait message** (`tools/process_tools.py:52-63`):
```python
async def _say(ctx, message: str) -> None:
    if not ctx:
        return
    try:
        await ctx.info(message)
    except Exception:
        pass
```
Do not import it from `tools.process_tools` (bridge must not import tools); duplicate it.

**Target attribute (D-06):** after the functions are defined: `revit_get.revit_target = "{}:{}".format(REVIT_HOST, REVIT_PORT)`.

**Port parsing:** `_resolve_port(value)` and `RevitConfigError(ValueError)` per RESEARCH.md "Strict port parsing" (isascii and isdigit, 1..65535, `None` -> 48884, `""` refused).

---

### `main.py` (wiring)

**Analog:** itself. Remove lines 21-102 (config, client, callables, `_revit_call`) and the now unused imports (`httpx`, `json`, `base64`, `Dict/Any/Union`, `os` if unused). Keep `import sys`, `anyio`, `FastMCP`. Wiring site (`main.py:105-107`):
```python
from tools import register_tools
register_tools(mcp, revit_get, revit_post, revit_image)
```
Add before it (stderr only, never stdout; stdio protocol):
```python
try:
    from bridge import revit_get, revit_post, revit_image
except ValueError as exc:            # RevitConfigError subclasses ValueError
    sys.stderr.write("revit-mcp: {}\n".format(exc))
    sys.exit(2)
```
Keep the `print()` at `main.py:150` as is (guarded to `--combined`). Keep the encoding cookie on line 1.

---

### `tools/status_tools.py` (D-06)

**Analog:** itself, `get_revit_status` (lines 32-33). Registrar signature must stay `(mcp, revit_get, revit_post=None, revit_image=None)` — `scripts/conventions.py:29,443` pins `["mcp","revit_get","revit_post","revit_image"]` names (defaults are allowed), so surface `host:port` by `getattr(revit_get, "revit_target", None)` (RESEARCH.md Pattern 3), never by a fifth parameter and never by importing `bridge`. Dict responses get `mcp_target=` added (renders as "Mcp Target:"); string responses (503/transport error) get an appended line. Always `return format_response(response)`. Update the docstring (it is the API contract): mention the reported target and keep an `Args:` block naming `ctx`.

---

### `tests/unit/test_bridge_serialization.py` (NEW)

**Analog:** no async test exists in `tests/unit/`. Use RESEARCH.md "Concurrency test skeleton" (lines 429-451) with `@pytest.mark.anyio`. Style conventions from existing tests: encoding cookie + module docstring ending "Needs no Revit." (see `tests/unit/test_registration.py:1-17`); `REPO_ROOT` is on `sys.path` via conftest, so `import bridge` works directly (same as `import tools` at `test_registration.py:19`).

Source-text reading idiom (for doc-pin / allowlist drift tests), from `test_local_bridge_transport.py:4-15`:
```python
ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "bridge.py").read_text(encoding="utf-8")
```
Allowlist drift test: regex-scan `tools/*.py` for `revit_post\(\s*"(/[^"]+)"` (the endpoints are literal; confirmed list includes all 5 allowlisted + 3 never-unlocked routes), assert allowlist subset of real endpoints, disjoint from `NEVER_UNLOCKED`, unknown endpoint locked, GET never locked.

Required cases (D-22): second POST waits; GET and allowlisted POST pass while locked; exception and cancellation release; `request.extensions["timeout"]["read"]` equals the passed timeout for a queued call; queue bound returns "NOT sent" without sending; post-send `httpx.ReadTimeout("", request=req)` yields outcome-unknown; `_resolve_port` table; SER-05 doc-pin (docstring contains the scope wording).

---

### `tests/unit/conftest.py` (MOD)

**Analog:** itself (tracked). Current content is only the `sys.path` insert (lines 12-18). Append, per RESEARCH Pitfalls 2-3:
```python
import pytest

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"          # module scope; trio is not installed

@pytest.fixture(autouse=True)
def _reset_bridge_state():
    import bridge
    bridge._lock = None
    bridge._http_client = None
    yield
    bridge._lock = None
    bridge._http_client = None
```
Name the globals in `bridge.py` exactly `_lock` and `_http_client`. Importing `bridge` inside an autouse fixture makes every test import it; acceptable (httpx only) but keep REVIT_PORT in the test environment valid.

---

### `tests/unit/test_local_bridge_transport.py` and `tests/unit/test_textutils.py:276-291` (retarget)

**Analog:** themselves. Change `(ROOT / "main.py")` to `(ROOT / "bridge.py")` at `test_local_bridge_transport.py:9`; keep the slice `split("def _get_client()", 1)[1].split("async def revit_get", 1)[0]` valid by keeping function order. In `test_textutils.py:280-283` change `"main.py"` to `"bridge.py"` and update the docstring ("bridge.py's content type..."). `source.index("else:  # POST")` must still find the marker.

---

### `deploy/build-payload.cmd` (MOD)

**Analog:** lines 109-110 of the same file:
```bat
copy /y "%REPO%\main.py"            "%BUILD%\app\" >nul || exit /b 1
```
Add the identical line for `bridge.py` immediately after it. `deploy/gate.py` spawns the deployed `server.py`, so a missing copy fails the build (intended net); `deploy/server.py` puts HERE on `sys.path`, so `import bridge` resolves. No edit to `gate.py` expected.

---

### Docs (D-15, D-21, D-26, Pitfall 8, Pitfall 10)

**Analogs:** `CLAUDE.md` "Known sharp edges" bullet "Port `48884` is hardcoded; only the host is configurable" (rewrite: `REVIT_HOST`/`REVIT_PORT`, invalid value refuses to start; add a serialization-scope bullet in the same list; also update the "30s timeout for everything" bullet). Env block examples: `deploy/USER-GUIDE.md:98-99` and `:217-218` (existing `REVIT_HOST` block) — add `REVIT_PORT` plus the two-entry `revit-a` (48884) / `revit-b` (48885) example, scoped to stdio only; state that port = launch slot, staggered start documented, HTTP/SSE multi-entry deferred (port 8000). Fix stale lines: USER-GUIDE "оба его занимают порт 48884" and `start_revit` docstring in `tools/process_tools.py` ("a second instance would bind a different Routes port and be unreachable anyway"). `deploy/configure_hermes.py` untouched. Wording: "this server does not queue reads behind mutations", never "reads are safe during mutations".

## Shared Patterns

### Error-string contract
**Source:** `main.py:100-102`. **Apply to:** all `bridge.py` error returns: `f"Error: {status} - {text}"` for non-200, `"Error: ..."` string for exceptions; tools then run `format_response(response)`. Never return a dict with an `error` key from the bridge.

### No `print()` under stdio
**Source:** CLAUDE.md invariants; `main.py:150` is the only guarded print. **Apply to:** `bridge.py`, port-refusal path (`sys.stderr.write` + `sys.exit(2)`).

### Tool modules never import the transport
**Source:** `tools/status_tools.py` header (`from .utils import format_response` only). **Apply to:** `status_tools.py` change; use `getattr(revit_get, "revit_target", None)`.

### Registrar signature pin
**Source:** `scripts/conventions.py:29,443` and `tests/unit/test_conventions.py:207`. **Apply to:** do not alter any `register_*_tools` parameter list.

### Test source-text idiom, no Revit
**Source:** `tests/unit/test_local_bridge_transport.py`, `tests/unit/test_registration.py` (module docstring "Needs no Revit", `REPO_ROOT` via `os.path`/`pathlib`). **Apply to:** all new tests.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| async test cases in `tests/unit/test_bridge_serialization.py` | test | async/event-driven | No async or `httpx.MockTransport` test exists in `tests/unit/` (baseline: 337 passed, 3 skipped); use RESEARCH.md skeleton and the `anyio_backend` override. |

## Metadata

**Analog search scope:** `main.py`, `tools/`, `tests/unit/`, `scripts/conventions.py`, `deploy/build-payload.cmd`, `deploy/gate.py`
**Files read:** main.py, status_tools.py, process_tools.py (excerpt), conftest.py, test_local_bridge_transport.py, test_textutils.py (excerpt), test_registration.py (head), build-payload.cmd (excerpt), conventions.py (excerpt)
**Pattern extraction date:** 2026-10-06
