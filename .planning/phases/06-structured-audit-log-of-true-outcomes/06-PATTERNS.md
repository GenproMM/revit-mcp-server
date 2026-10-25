# Phase 6: Structured audit log of true outcomes - Pattern Map

**Mapped:** 2026-10-25
**Files analyzed:** 17 (3 new source/test-support, 4 modified source, 9 new tests/live, 1 payload script)
**Analogs found:** 16 / 17 (all analog paths verified git-tracked: bridge.py, tools/utils.py, tests/test_phase4_live_outcomes.py and the unit tests below are tracked sources, none are gitignored mirrors)

`revit_mcp/` is NOT touched in this phase (D-06). Everything is CPython-side: async, f-strings and modern typing are allowed in `audit.py` and tests. The IronPython rules do not apply.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `audit.py` (NEW, repo root, stdlib-only at import) | service/utility (entry builder + redaction + queue writer + tool wrapper) | event-driven (queue) + transform | `bridge.py` (root module: lazy init, provenance consumption, `_reply_body`, secret handling) | role-match |
| `bridge.py` (MOD: audit hook in `_dispatch`, `/status/` branch, `call_id` in envelope, tag Image) | service (transport) | request-response | itself: `_dispatch` 976-1025, `with_envelope` 1085-1104, `_tag` 473-481 | exact |
| `main.py` (MOD: `audit.install_audited_tools(mcp)` before `register_tools`; `instructions=`) | config/entry | request-response | itself, lines 14-27 | exact |
| `tools/utils.py` (MOD: render `Audit: call_id <id>`) | utility | transform | itself: `format_response` 16-47, `_provenance_lines` 113-148 | exact |
| `deploy/build-payload.cmd` (MOD: copy `audit.py`) | config | batch | itself, lines 109-110 | exact |
| `tests/unit/test_payload_ships_root_modules.py` (MOD: transitive imports) | test | transform | itself, lines 25-60 | exact |
| `tests/unit/conftest.py` (MOD: autouse audit-sink isolation) | test config | - | itself: `_no_live_revit_from_the_bridge` | exact |
| `tests/unit/audit_support.py` (NEW: Machine fake, in-process fake Revit, entry reader) | test helper | request-response | `tests/unit/test_target_locks.py:40-115` (Machine), `tests/unit/gate_support.py` | exact |
| `tests/unit/test_audit_entry.py` | test | transform | `tests/unit/test_format_response.py`, `test_trust_envelope.py` | role-match |
| `tests/unit/test_audit_bridge_hook.py` | test | request-response | `tests/unit/test_target_locks.py` + `test_phase5_gate_e2e.py` | exact |
| `tests/unit/test_audit_correlation.py` | test | request-response | `tests/unit/test_phase5_gate_e2e.py` (gate accepts envelope) | role-match |
| `tests/unit/test_audit_registration.py` | test | transform | `tests/unit/test_phase2_inventory.py:188-205`, `inventory_support.py:178-219` | role-match |
| `tests/unit/test_audit_writer.py` | test | file-I/O | none close (new file-I/O); use RESEARCH Pattern 2 | no analog |
| `tests/unit/test_audit_secret.py` | test | request-response | `tests/unit/test_bridge_secret_client.py`, `test_phase5_gate_e2e.py` | role-match |
| `tests/unit/test_audit_stdio.py` | test | streaming (subprocess stdio) | `tests/unit/test_phase5_gate_e2e.py` (imports `subprocess`) and `tests/test_init_latency.py` | role-match |
| `tests/test_phase6_live_audit.py` (NEW one-shot human-run) + `tests/unit/test_phase6_live_audit.py` (classifier) | test (live) | request-response | `tests/test_phase4_live_outcomes.py` + `tests/unit/test_phase4_live_outcomes.py` | exact |
| `tests/unit/tool_manifest.txt` | config | - | no change (no tool added) | n/a |

## Pattern Assignments

### `bridge.py` hook seams (service, request-response)

**Analog:** itself. Keep `_dispatch(method, endpoint, ctx, timeout, exchange, target=None)` name and signature; move the body to `_dispatch_core` and make `_dispatch` the audit wrapper that creates `progress` and passes it in (RESEARCH "Hook seams").

**Existing core to preserve** (`bridge.py:991-1025`):
```python
    budget = None  # must exist before the except clause reads it
    state = None
    requested = None
    progress = {"sent": False}  # whether the requested exchange was ever started
    try:
        resolved = parse_target(target) if target is not None else await resolve_default_target()
        requested = _requested_of(resolved)
        ...
        return await _verified_exchange(
            method, exchange, state, resolved, requested, timeout, progress, False)
    except TimeoutError:
        if budget is not None and budget.expired():
            return _uncertain(_queue_busy_message(timeout), "not-sent", requested)
        return _uncertain("Error: TimeoutError", _unconfirmed_kind(method, progress), requested)
    except Exception as e:
        return _uncertain(_error_text(e), _unconfirmed_kind(method, progress), requested)
    finally:
        if state is not None:
            await _release(state)
```
`_dispatch` catches `Exception`, NOT `CancelledError` (Pitfall 9): in the wrapper, `except asyncio.CancelledError:` write an `unknown` entry (flag `cancelled`) if `progress["sent"]`, then re-raise.

**Provenance consumption** (lines 465-563) - the writer reads the attribute, never httpx:
```python
PROVENANCE_ATTR = "revit_provenance"  # keep in step with tools/utils.py
def _meta(kind, requested=None, process=None, http_status=None, corroborated=None):
    return {"kind": kind, "requested": requested, "process": process,
            "http_status": http_status, "corroborated": corroborated}
def _reply_body(result):   # 507-518: dict itself, or JSON after "Error: NNN - "
```
Reuse `bridge._reply_body(result)` to get the body; pass the dict `getattr(result, PROVENANCE_ATTR, None)` into `audit.record_call`. `kind == "not-sent"` returns without an entry (D-02b).

**`/status/` branch** (`bridge.py:784-788`) - audit only when the contextvar tool is `get_revit_status` (Pitfall 8):
```python
    if endpoint == "/status/" and params is None:
        return await _status_call(target, timeout)
```

**Image tagging** (`_tag`, 473-481): non-text results return untouched (`return value`), so a `revit_image` success has no provenance (Pitfall 7). Extend `_tag` and the early return in `_received_reply` (546-547) to `setattr` the attribute on the `Image` instance.

**Envelope `call_id`** (`with_envelope`, 1085-1104) - add optional `call_id` param; only inside the existing `if secret is not None:` branch (pinned by `test_with_envelope_none_secret_adds_no_envelope`, Pitfall 15):
```python
    body = dict(data)
    if secret is not None:
        body[ENVELOPE_KEY] = {SECRET_KEY: secret}
    return body
```
Caller site is `revit_post` (815-819): `body = with_envelope(data, _secret())` inside `try/except ValueError`; the `not-sent` return there writes no entry.

**Error/never-break pattern (D-18)** - copy the swallow idiom of `_say` (`bridge.py:918-930`):
```python
    if not ctx:
        return
    try:
        await ctx.info(message)
    except Exception:
        pass
```
Audit failure: swallow, one stderr line per process with `type(exc).__name__` only. Never `print` (stdout is the protocol stream); use `sys.stderr.write` as `main.py:7-12` does.

**Import rule:** `import audit` eagerly at the top of `bridge.py` so `deploy/gate.py` fails the build when the file is missing (Pitfall 13). `audit.py` and `bridge.py` must not import `mcp` or `revit_mcp` at module level (`test_bridge_serialization.py::test_bridge_imports_without_fastmcp`). The open-read list is mirrored in `audit.py` and pinned equal to `revit_mcp.trust.OPEN_POST_READ_ROUTES` by a unit test (same trick as `ENVELOPE_KEY`, bridge.py:1081).

---

### `audit.py` (NEW; service/utility, event-driven)

**Analog for module shape:** `bridge.py` (module docstring stating invariants, lazy init, constants mirrored from `revit_mcp/trust.py`, `# -*- coding: utf-8 -*-` line 1).

**Open-read mirror source** (`revit_mcp/trust.py:48-56`), copy verbatim into `audit.py`:
```python
OPEN_POST_READ_ROUTES = frozenset((
    "/document_summary/", "/document_levels/", "/model_worksets/",
    "/material_quantities/", "/clash_check/", "/ai_filter/",
    "/list_category_parameters/",
))
```
`mutation = not (method == "GET" or route in OPEN_POST_READ_ROUTES)`; normalise route like `bridge._route_key` (bridge.py:888) and keep the tail in `route_arg`.

**Tool wrapper (Pattern 1; install from `main.py`, NOT `register_tools`)** - copy RESEARCH Pattern 1 (`_CALL` ContextVar, `install_audited_tools(mcp)` replacing `mcp.tool`, `_wrap` with `__signature__` + `functools.wraps`, `BeforeValidator(_json_text)` for `user_request`, lazy `from pydantic import ...`). Wrapped function receives `ctx` as kwarg: drop by name when capturing `args`.

**Writer (Pattern 2)** - `SegmentHandler(logging.handlers.BaseRotatingHandler)` roll-forward, never rename; method named `_segment` (not `_name`); `_open` with `newline="\n", errors="backslashreplace"`; logger `revit_mcp.audit`, `propagate=False`, `QueueHandler` over bounded `queue.Queue` to `QueueListener`; formatter `%(message)s`; `atexit.register(listener.stop)`. Everything lazy on first entry (cold-start gate 2.0 s).

**Serialization:** `json.dumps(entry, ensure_ascii=False, separators=(",", ":"), default=<type-name fallback>)`; redact (raw + JSON-escaped secret) BEFORE truncating; final replace pass on the serialized line; scrub arg keys `secret|token|password|api_key` (not `process.session_token`). Secret passed in from `bridge._secret()` at write time (audit never imports bridge).

**Outcome mapping:** use RESEARCH "Entry construction" table. Key fact: label comes from reply TOP-LEVEL `status`, not `outcome.status` (the block has five keys only: `transaction_status, requested, succeeded, failed, revit_failures`). `/activate_document/` is the only mutating route exempt from `outcome_block_missing` (`ROUTES_WITHOUT_OUTCOME_BLOCK`).

---

### `tools/utils.py` (utility, transform) - `Audit:` line

**Analog:** itself (`format_response`, lines 40-47):
```python
    text = _project_response(response)
    provenance = getattr(response, PROVENANCE_ATTR, None)
    if not isinstance(provenance, dict):
        return text
    lines = _provenance_lines(response, provenance, text)
    if not lines:
        return text
    return "\n".join([str(text)] + lines)
```
`_provenance_lines` returns early per kind (113-148), so append `"Audit: call_id {}".format(provenance["audit_call_id"])` in `format_response` after `lines` is built, for every kind, when the hook set the key (only when an entry was written and (mutation or outcome != success)). Careful: `if not lines: return text` must not swallow the audit line. `PROVENANCE_ATTR = "revit_provenance"` is duplicated (line 11) and must stay in step with bridge.py:462. Mind the exact-text assertions in `tests/unit/test_format_response.py` and `test_identity_rendering.py`.

---

### `main.py` (config, request-response)

**Analog:** itself (lines 14-27). Insert between `mcp = FastMCP(...)` and `register_tools(...)`:
```python
mcp = FastMCP("Revit MCP Server", host="127.0.0.1", port=8000, stateless_http=True, json_response=True)

# Register all tools BEFORE the main block
from tools import register_tools
register_tools(mcp, revit_get, revit_post, revit_image)
```
Add `import audit; audit.install_audited_tools(mcp)` before `register_tools`; add `instructions=` kwarg (mcp 1.9.0 supports it) holding the full user_request rule. Keep `main.py`'s `sys.stderr.write` startup-refusal idiom; no `print` (line 61 print is `--combined`-guarded and stays).

Why not `tools/__init__.py`: `tests/unit/test_phase2_inventory.py:188-205` asserts `names[-1] == "ctx"` on callables registered through `register_tools(FakeMCP(), ...)`; `FakeMCP.tool(self)` is zero-arg (`inventory_support.py:178-219`). Registrar signature is pinned by `scripts/conventions.py CANONICAL_TOOL_REGISTRAR`.

---

### `deploy/build-payload.cmd` (config, batch)

**Analog:** itself (lines 109-110):
```
copy /y "%REPO%\main.py"            "%BUILD%\app\" >nul || exit /b 1
copy /y "%REPO%\bridge.py"          "%BUILD%\app\" >nul || exit /b 1
```
Add the same form for `audit.py` right after `bridge.py` (the regex in `test_payload_ships_root_modules.py` matches `copy /y "%REPO%\<name>.py"`).

### `tests/unit/test_payload_ships_root_modules.py` (MOD)

**Analog:** itself (`_root_modules_main_imports` uses `ast.walk` over `main.py` for `Import`/`ImportFrom` with `node.level == 0`, `_COPY` regex lines 25-37). Generalize to a transitive walk (main -> bridge -> audit); keep the non-vacuity assert (`"bridge" in root_modules`) and add `"audit"`.

---

### `tests/unit/conftest.py` (MOD) - autouse audit isolation (Pitfall 14)

**Analog:** itself, `_no_live_revit_from_the_bridge` (monkeypatch style with `hasattr` guards):
```python
    monkeypatch.setattr(bridge, "_states", {})
    if hasattr(bridge, "_selected_client"):
        monkeypatch.setattr(bridge, "_selected_client", refusing_client)
```
Add a sibling autouse fixture: `monkeypatch.setenv("REVIT_MCP_AUDIT_DIR", str(tmp_path))` and reset the `audit` writer singleton (use `hasattr` guards). Without it every bridge-path test writes to `%LOCALAPPDATA%\RevitMCP\audit` and the new `Audit:` lines change exact-text assertions.

---

### `tests/unit/audit_support.py`, `test_audit_bridge_hook.py`, `test_audit_correlation.py`, `test_audit_secret.py` (test helpers/integration)

**Analog:** `tests/unit/test_target_locks.py:40-115` (fake machine through the real bridge):
```python
class Machine(object):
    def __init__(self):
        self.listeners = {PORT_A: [PID_A], PORT_B: [PID_B]}
        self.identity = {PORT_A: (PID_A, TOKEN_A), PORT_B: (PID_B, TOKEN_B)}
        ...
    def snapshot(self, ports, **_kwargs):
        return dict((p, list(self.listeners.get(p, []))) for p in ports)
    async def respond(self, request):
        ... if path == PREFIX + "/status/": ... return httpx.Response(200, json={"status": "active", "process_identity": {...}})
    def client(self, target):
        client = httpx.AsyncClient(base_url="http://127.0.0.1:{}{}/".format(target["port"], PREFIX),
            transport=httpx.MockTransport(self.respond), trust_env=False)

@pytest.fixture
def machine(monkeypatch):
    fake = Machine()
    monkeypatch.setattr(bridge, "listener_snapshot", fake.snapshot)
    monkeypatch.setattr(bridge, "_selected_client", fake.client)
```
Reuse for per-`kind` entries and "handshake/probe -> no entry"; add canned bodies (409 `rolled_back`, 422, 200 partial, 401, 423, wrong `process_identity` stamp for `unknown`, `faults` for transport error). Use `bridge._selector_for({...})` for explicit targets.

**Gate acceptance of `_mcp.call_id`:** `tests/unit/test_phase5_gate_e2e.py` (MockTransport handler wraps received bytes, runs real `security.gate_or_response`) with `from gate_support import TEST_SECRET, configure_gate`; `WRONG_SECRET` constant at line 25. Set `bridge._secret_cache` directly in tests wanting a secret.

**Fake-Revit HTTP server (real sockets, stdio test)** - RESEARCH Pattern 3 / "Code Examples" skeleton (ThreadingHTTPServer, `process_identity` pid = `os.getpid()`); `skipif(sys.platform != "win32")`; the autouse conftest guards `listener_snapshot` unless `run=` is injected: restore real `_selected_client` as `test_target_locks.py` does with `REAL_SELECTED_CLIENT`.

---

### `tests/unit/test_audit_registration.py` (test, transform)

**Analog:** `tests/unit/test_phase2_inventory.py:188-205` + `inventory_support.register_everything()`. Build a real `FastMCP`, call `audit.install_audited_tools(mcp)`, then `register_tools(mcp, ...)`; assert every tool schema has `user_request` and other parameters/defaults/required flags equal the unwrapped signatures; JSON-looking values (`'{"a":1}'`, `'[1,2]'`) accepted.

### `tests/unit/test_audit_entry.py` (test, transform)

**Analog:** `tests/unit/test_format_response.py` (pure function table tests); plus pin `audit.OPEN_POST_READ_ROUTES == revit_mcp.trust.OPEN_POST_READ_ROUTES` (other tests already import `revit_mcp.trust`, e.g. `test_bridge_secret_client.py`), and route classification vs `inventory_support.route_inventory()`.

### `tests/unit/test_audit_stdio.py` (test, streaming)

**Analog:** `tests/test_init_latency.py` (stdio-client skeleton with absolute `main.py` path, per CLAUDE.md). Parse every stdout line as JSON-RPC with audit active against the in-process fake Revit; plus an AST test that `audit.py`/`bridge.py` contain no `print`, `sys.stdout` or `StreamHandler`.

### `tests/unit/test_audit_writer.py` (test, file-I/O) - NO ANALOG

Use RESEARCH Pattern 2 and Pitfalls 3, 4, 6: cap applies from first write; reader holding the active segment loses no record; no `\r\n`; lone surrogate does not raise; prune by age then size skips held files; concurrent writers via two incarnations; writer failure never changes tool result and warns once.

### `tests/test_phase6_live_audit.py` + `tests/unit/test_phase6_live_audit.py` (live gate, classifier)

**Analog:** `tests/test_phase4_live_outcomes.py` (standalone, no `test_*` functions, nothing at import, `template`/`run`/`classify` commands, uppercase sentinel tokens plus count line, refuses `--out` that exists or lies inside the repo, write steps one-shot) and its unit twin that imports the pure classifier. Keep the one-shot rule (project memory: write steps never repeat; check parameter exists first; one Revit for mutation steps). Schedule a rollback-trigger rehearsal in a scratch document before the gate (Pitfall 18, A3 assumed).

---

## Shared Patterns

### Never break a tool call, never write stdout
**Source:** `bridge.py:918-930` (`_say`), `main.py:7-12` (stderr-only message)
**Apply to:** `audit.py` writer, `bridge.py` hook. Swallow exceptions, write `type(exc).__name__` to stderr once per process, no `exc_info`, no `repr(exception)`, no `print`.

### Provenance is the only source of outcome truth
**Source:** `bridge.py:465-563` (`_meta`, `_tag`, `_received_reply`, `_reply_body`)
**Apply to:** `audit.build_entry`. Never derive success from `format_response` (CLAUDE.md "dict is an error only if..."). Process only from provenance `received`; document only from the reply (priority `document` -> `documents_changed` -> args selector -> none, plus `document_source`); `execute_code` documents are "addressed", not changed.

### Lazy imports and cold start
**Source:** `bridge.py:836` (`from mcp.server.fastmcp import Image` inside the function, "keeps cold start cheap"), `tools/__init__.py:63-70`
**Apply to:** `audit.py` (pydantic inside `install_audited_tools`; directory, thread, prune, Windows-user lookup on the first entry).

### Secret never in the log
**Source:** `bridge.py:1085-1104` (`with_envelope` fixed-text refusals), `bridge._secret()`
**Apply to:** `audit.py` single redaction function; grep-the-file tests over success, 401, exception path, secret pasted into args/`user_request`/code, secret echoed in a failed `reason`, secret straddling the truncation cut.

### Two-runtime / convention checks
**Source:** `scripts/conventions.py` `check_tools` (reads tool SOURCE ASTs, never sees the injected parameter, so no change needed), CLAUDE.md "Tool functions always return `str` via `format_response`".
**Apply to:** all tool-facing changes; do not edit the 59 tool functions.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `tests/unit/test_audit_writer.py` (and the `SegmentHandler` in `audit.py`) | test/service | file-I/O, rotation | No existing log-file writer in the repo; use RESEARCH Pattern 2 (verified prototype) and stdlib `logging.handlers.BaseRotatingHandler` |

## Metadata

**Analog search scope:** `bridge.py`, `main.py`, `tools/__init__.py`, `tools/utils.py`, `revit_mcp/trust.py` (read-only reference), `tests/unit/*`, `tests/test_phase4_live_outcomes.py`, `deploy/build-payload.cmd`
**Files scanned:** ~25
**Pattern extraction date:** 2026-10-25
