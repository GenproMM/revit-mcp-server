# Phase 7: Repository-owned mutation safety and human approval - Pattern Map

**Mapped:** 2026-10-25
**Files analyzed:** 27 new/modified (plus test files)
**Analogs found:** 27 / 27 (all analog paths verified git-tracked; no gitignored mirrors named)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `policy.py` (NEW, CPython root) | service | batch/transform + hot reload | `audit.py` (root module: constants, pure helpers, never-raise writers, thread) | role-match |
| `policy.base.toml` (NEW data) | config | transform | `tests/unit/tool_manifest.txt` (list the guard test pins) | partial |
| `permit.py` (NEW, CPython root) | utility | transform | `bridge.with_envelope` (bridge.py:1195-1224) + `revit_mcp/trust.py` | role-match |
| `revit_mcp/permits.py` (NEW helper, IronPython) | utility | request-response | `revit_mcp/trust.py` (pure, no pyRevit, IronPython dialect) | exact |
| `bridge.py` (MOD: authorizer hook, `with_envelope(permit=)`, status seam) | middleware | request-response | itself, `revit_post` (838-864) | exact |
| `audit.py` (MOD: labels, `record_decision`, fields) | service | event-driven | itself, `OUTCOME_LABELS`, `record_call` (975-990) | exact |
| `main.py` (MOD: install engine) | config | request-response | itself (lines 19-35 install order) | exact |
| `tools/utils.py` (MOD small) | utility | transform | itself `format_response` (16-54) | exact |
| `tools/status_tools.py` (MOD) | controller (tool) | request-response | itself, `get_revit_status` | exact |
| `revit_mcp/security.py` (MOD: permit step, `status_block`) | middleware | request-response | itself `gate_or_response` (124-150) | exact |
| `revit_mcp/trust.py` (MOD: PERMIT_*, `permit_failure`, OPEN set +3) | utility | transform | itself `auth_failure`/`integrity_failure`/`gate_failure` (97-111) | exact |
| `revit_mcp/identity.py` (MOD: `process_token()`) | utility | request-response | itself (session_token) | exact |
| `revit_mcp/parameters.py` (+ `/parameter_preflight/`) | route | request-response (read) | `revit_mcp/worksharing.py:405-416` `model_worksets` (open read) | role-match |
| `revit_mcp/editing.py` (+ `/elements_preflight/`) | route | request-response (read) | same open-read analog; resolution mirrors `_delete_elements` 20-61 | role-match |
| `revit_mcp/placement.py` (+ `/family_preflight/`) | route | request-response (read) | same | role-match |
| `deploy/server.py`, `gate.py`, `warm.py` (pywin32 shim) | config | file-I/O (sys.path) | `deploy/server.py:23-24` sys.path injection | exact |
| `deploy/build-payload.cmd` | config | batch | itself lines 109-114 | exact |
| `deploy/config.cmd` (+ `MCP_POLICY_FILE`) | config | config | itself `MCP_SECRET_FILE` (33-47) | exact |
| `scripts/conventions.py` | config | transform | itself 50-72 | exact |
| `tests/unit/conftest.py` (permissive authorizer fixture) | test | fixture | itself `_no_live_revit_from_the_bridge` (50-93) | exact |
| `tests/unit/gate_support.py` (permit minting) | test | fixture | itself (whole file) | exact |
| `tests/unit/inventory_support.py` + `test_phase2_inventory.py` | test | AST inventory | itself | exact |
| `tests/unit/test_phase5_gate_wiring.py` (counts 56/41/15/34/7 -> 59/44/15/34/10, `D02_OPEN`) | test | AST guard | itself | exact |
| new `tests/unit/test_policy_*.py`, `test_permit_*.py`, base-policy coverage guard | test | AST + data | `test_phase5_gate_wiring.py` + `inventory_support.route_inventory` | role-match |
| `tests/unit/test_payload_ships_root_modules.py` | test | AST guard | itself (regex only matches `copy /y "%REPO%\x.py"`) | exact |
| `tests/unit/test_serialization_scope_docs.py` | test | doc pin | itself (sentence pins) | exact |
| live-bench script `tests/test_phase7_live_gate.py` (user-run) + offline validator | test | request-response | `tests/test_phase5_live_gate.py` | exact |

## Pattern Assignments

### `revit_mcp/permits.py` (utility, request-response)

**Analog:** `revit_mcp/trust.py` plus RESEARCH "Revit-side verification skeleton" (07-RESEARCH.md:748-782).
Helper module: encoding cookie line 1, no pyRevit, no f-strings, `.format()` only, imports only hashlib/json/time/threading, relative imports only (`from . import trust`). Never raises; returns verdict words; fixed text with no body or secret in it (trust.py:97-111 `gate_failure`). Use hand-rolled HMAC over `hashlib` (parity-tested), not `secrets`/`pathlib`/`typing` (rejected by `scripts/conventions.py` `PY3_ONLY_MODULES`).

**Registry pattern** (07-RESEARCH.md:761-781): `_LOCK = threading.Lock()`, `_CONSUMED = {}` nonce->exp, purge past `exp+SKEW`, cap 4096, check-and-add under the lock, only on success.

### `revit_mcp/security.py` (MOD, middleware)

**Analog:** itself. Insert the permit step inside `gate_or_response` after the integrity check (line 145-146) and before `request.data = trust.clean_body(...)` (line 147); keep the whole function in one `try/except Exception` that answers `trust.gate_failure()`.

```python
# security.py:136-150 (existing shape to extend)
try:
    state = _STATE
    if state is None:
        return _refusal(*trust.auth_failure(trust.AUTH_SERVER_NOT_CONFIGURED))
    raw = _raw_data(request)
    envelope, payload = trust.split_envelope(raw)
    verdict = trust.check_secret(trust.envelope_secret(envelope), state["secret"])
    if verdict != trust.AUTH_OK:
        return _refusal(*trust.auth_failure(verdict))
    if state["integrity"].get("state") == trust.INTEGRITY_MISMATCH:
        return _refusal(*trust.integrity_failure(trust.mismatch_files(state["integrity"])))
    # <-- Phase 7: permits.check_and_consume(...) -> _refusal(*trust.permit_failure(verdict))
    request.data = trust.clean_body(raw, payload)
    return None
except Exception:
    return _refusal(*trust.gate_failure())
```
`_refusal` imports pyRevit lazily (113-116): keep so CPython tests import the module. `status_block` (78-110) returns a dict never carrying the secret: add the permit protocol there with the same try/except fallback.

### `revit_mcp/trust.py` (MOD)

**Analog:** itself. Add `PERMIT_*` verdict constants beside `AUTH_*` (30-37), a `permit_failure(verdict)` returning `(body, status)` like `gate_failure()` (97-111), and extend `OPEN_POST_READ_ROUTES` (48-56) with `/parameter_preflight/`, `/elements_preflight/`, `/family_preflight/`. `split_envelope` (114-135) parses through `parse_request_data` and returns `(envelope, payload)`: reuse it; do not add a second parse. RESEARCH rule: hash wire text (`raw_decode`), not re-serialized JSON.

### New preflight routes in `parameters.py` / `editing.py` / `placement.py` (route, request-response read)

**Analog:** `revit_mcp/worksharing.py:405-416` (open read) and the gated handler head in `revit_mcp/editing.py:126-137`.

**Open-read preamble** (worksharing.py:414-416):
```python
# Phase 5 open read (D-02): never refused; the reserved envelope key is removed.
strip_envelope(request)
try:
    data = {}
    if request and request.data:
        data = parse_request_data(request.data)
```
Imports (worksharing.py:23): `from .security import gate_or_response, strip_envelope` (only these names may come from security; `SECURITY_IMPORTS` in conventions.py:57). Error statuses: 400/404/500/503 via `routes.make_response(data=..., status=...)`. Document resolution: `mutation_document_or_response(request_document_selector(request), uiapp=uiapp)` (editing.py:134-137); a refusal there is returned as-is. No `DB.Transaction`, never raise, cap work (2000 ids -> report "unknown"). Do not import another `revit_mcp/` domain; use `.utils` helpers (`make_element_id`, `get_element_id_value`, `sanitize_string`).

**Gated-route preamble (unchanged, for reference)** (editing.py:129-137):
```python
gate_refusal = gate_or_response(request)
if gate_refusal is not None:
    return gate_refusal
document, descriptor, refusal = mutation_document_or_response(
    request_document_selector(request), uiapp=uiapp)
if refusal is not None:
    return refusal
```
Element lookup to mirror for `/elements_preflight/` (editing.py:53-61): `elem = doc.GetElement(make_element_id(eid))`.

### `bridge.py` (MOD, middleware, request-response)

**Analog:** itself. Hook point is `revit_post` (838-864); the envelope is built before `_dispatch` so a refusal reads "NOT sent":
```python
call = audit.current_call() or audit.anonymous_call()
try:
    body = with_envelope(data, _secret(), call_id=call.call_id)
except ValueError as exc:  # fixed text: carries neither the body nor the secret
    return _uncertain("Error: the request was NOT sent to Revit: {}".format(exc), "not-sent", None)
async def write(client): return await _send(client, "POST", endpoint, body, timeout, params)
return await _dispatch("POST", endpoint, ctx, timeout, write, target, call=call)
```
Phase 7: before `with_envelope`, resolve target once, call the authorizer (None installed = refuse via `_uncertain(..., "not-sent", None)`), skip it for `trust.OPEN_POST_READ_ROUTES` + 3 preflight routes, and RETURN refusals (never raise). `with_envelope` (1200-1224) rejects a model-supplied `_mcp` key and only adds `call_id` beside a secret: add `permit=` the same way (key `PERMIT_KEY` beside `SECRET_KEY`/`CALL_ID_KEY` at 1195-1197). Wire form changes to envelope-first text (permit.py `wire_text`); `_send` must send `text/plain` bytes of that text. Human wait occurs before `_dispatch_core` (so before lock, 1096). Do NOT add to `UNLOCKED_GET` (921). Never `print()` (test_audit_stdio).

### `permit.py` (NEW, CPython utility)

**Analog:** `bridge.with_envelope` for shape (pure function, fixed-text `ValueError`, never mutate the argument) and RESEARCH Pattern 3 for the algorithm (07-RESEARCH.md:346-372): `a = sha256(args_text)`, `m = HMAC(K, "permit1\n"+r+"\n"+a+"\n"+s+"\n"+e+"\n"+n+"\n"+p)`, `K = HMAC(secret, b"revit-mcp/permit/v1")`, `wire_text(data, envelope)` with `json.dumps(..., separators=(",", ":"), allow_nan=False)`. Root module: must be added as `copy /y "%REPO%\permit.py"` (see test below).

### `policy.py` (NEW, CPython service)

**Analog:** `audit.py` for conventions: module docstring stating schema, UPPER_CASE constants at top (109-130), `OPEN_POST_READ_ROUTES` mirrored literal pinned by a test (audit.py:135), `_warn_once` single-stderr-line failure style (772), thread/queue writer with `_reset()` for tests (836-1025), never raises (record_call 975-990). Load pattern: RESEARCH "Hot reload loader" (07-RESEARCH.md:727-746): `tomllib`, `utf-8-sig`, read in `asyncio.to_thread`, never touch the UNC share at import. Elicitation helper: RESEARCH Pattern 2 `ask_human` (07-RESEARCH.md:326-342): `session.check_client_capability`, `elicit_form(message, {"type":"object","properties":{}}, ctx.request_id)`, `asyncio.timeout`, trust only `result.action`.
No root module may `print`, use `sys.stdout` or `StreamHandler` (AST-enforced by `tests/unit/test_audit_stdio.py`: extend its scanned list to the new modules).

### `audit.py` (MOD)

**Analog:** itself.
```python
# audit.py:163-166
OUTCOME_LABELS = (
    "success", "partial", "failed", "rolled_back", "rejected_auth", "rejected_integrity",
    "rejected_document", "error", "unknown", "no_reply", "unverified_reply", "unrecognized",
)
```
Add labels (denied, expired, rejected_permit); pinned by `tests/unit/test_audit_entry.py:138` (12 -> 15) and the `SCHEMA_1_FIELDS` / `ALWAYS_PRESENT_FIELDS` tuples (203-221) when adding policy fields. `record_decision` copies `record_call` (975-990): try/except -> `_warn_once(exc)` -> return None; message is a finished line via `serialize_entry(entry, secret)` (secret redacted only through `redact_text`, 345). `install_audited_tools._wrap` (270-292): set `structured_output=False` default in `audited_tool` (311-318) to keep tool return shape on mcp 1.30; keep `functools.wraps` + `__signature__` + `user_request`.

### `tools/utils.py` / `tools/status_tools.py` (MOD small)

**Analog:** `format_response` (tools/utils.py:16-54). Append attribution lines only via provenance (`provenance.get("audit_call_id")` pattern, line 49-51); do NOT add an implicit error signal (dict is an error only with truthy `error` or status in error/failed/failure/exception). Refusals use the existing bridge `"Error: ... NOT sent ..."` string with kind `not-sent`.

### Deploy: `deploy/server.py`, `gate.py`, `warm.py` (pywin32 shim)

**Analog:** `deploy/server.py:21-24`:
```python
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "libs"))
sys.path.insert(0, HERE)
```
`gate.py:17-18` has `sys.path.insert(0, os.path.join(HERE, "libs"))` before `from mcp import ...`: add `libs\win32`, `libs\win32\lib`, `libs\pythonwin` right there in all three (and keep stdout clean: server.py comment line 15). `gate.py` prints sentinels (`INIT_LATENCY_S=`, `MANIFEST=ok`, `GATE_OK`): extend for the policy file presence and keep `LIMIT = 2.0`.

### `deploy/build-payload.cmd` (MOD)

**Analog:** itself lines 109-114. Add `copy /y "%REPO%\policy.py"` and `permit.py` lines in the exact form the regex `^\s*copy\s+/y\s+"%REPO%\\([A-Za-z0-9_]+)\.py"` matches (test_payload_ships_root_modules.py:22), and a separate non-`.py` line for `policy.base.toml`:
```
copy /y "%REPO%\main.py"            "%BUILD%\app\" >nul || exit /b 1
copy /y "%REPO%\audit.py"           "%BUILD%\app\" >nul || exit /b 1
```
Policy source path staging: follow the secret staging style (line 126, `secret_tool.py stage --secret-file "%MCP_SECRET_FILE%" --dest ...`) if the operator path must reach the payload.

### `deploy/config.cmd` (MOD)

**Analog:** itself lines 33-47: `if not defined MCP_SECRET_FILE set "MCP_SECRET_FILE=%MCP_SHARE_ROOT%\_build\bridge_secret"` with a `rem` block explaining who reads it. Add `MCP_POLICY_FILE` the same way (beside the secret, ASCII share root, Cyrillic only in the policy TOML literal strings).

### `scripts/conventions.py` (MOD)

**Analog:** itself. `LOCAL_MODULES = {"utils", "textutils", "registry", "revit_mcp", "identity", "trust", "integrity", "security"}` (50-51): add `"permits"`. `OPEN_POST_READ_ROUTES` (64-72): add the 3 preflight routes; three-place pin (trust.py, conventions.py, `D02_OPEN`). Rebuild the contributor kit with `scripts/build_contrib_kit.py`.

### Tests

**`tests/unit/conftest.py`** (analog: itself 50-93): add an autouse fixture that installs a permissive authorizer in `bridge` (production default is fail-closed), same style as `monkeypatch.setattr(bridge, "_secret_cache", None)` guarded by `hasattr`.

**`tests/unit/gate_support.py`** (analog: itself): extend the helpers:
```python
TEST_SECRET = "phase5-test-secret-0123456789-abcdefXYZ"
def configure_gate(monkeypatch, secret=TEST_SECRET, integrity=None): ... monkeypatch.setattr(security, "_STATE", {...})
def enveloped_body(body, secret=TEST_SECRET, as_type="bytes"): ...   # add permit=/route=
def request_of(body, secret=TEST_SECRET): ... types.SimpleNamespace(data=...)  # add path/route
```
Existing ~71 call sites use `request_of(body)`: keep it working by minting a real permit by default with a monkeypatched session token (Wave 0 gap).

**`tests/unit/test_phase5_gate_wiring.py`** (analog: itself): AST-pinned shape `gate_refusal = gate_or_response(request)` / `if gate_refusal is not None: return gate_refusal` (lines 78-99); `_strip_statement` for open reads (102-110); update pins (lines 115-126): `len(D02_OPEN)==10`, `ROUTES==59`, `NON_GET==44`, `GATED_KEYS==34`, plus the literal `D02_OPEN` (27-35). New base-policy guard from RESEARCH (07-RESEARCH.md:785-794):
```python
from inventory_support import route_inventory, manifest_names
routes = {r.key for r in route_inventory()}
assert set(base_policy["routes"]) >= routes
assert set(base_policy["tools"]) == set(manifest_names())
```
`inventory_support.py` (`route_inventory` 316, `ROUTE_CLASSES` 112, `manifest_names` 222, `register_everything` 189, `ALLOWED_ROUTE_CLASSES` 153) needs a new route class for the preflight reads.

**`tests/unit/test_payload_ships_root_modules.py`**: no edit needed; it fails until `policy.py`/`permit.py` copy lines exist (transitive walk main -> bridge -> audit/policy/permit). The TOML is not covered by it: add a separate assertion for `policy.base.toml` in `build-payload.cmd`.

**`tests/unit/test_serialization_scope_docs.py`**: sentence pins `SCOPE_SENTENCE`, `STATUS_SENTENCE`, `CROSS_PROCESS_SENTENCE` (15-24) must survive; the `OVERCLAIM_SCANNED` docs (CLAUDE.md, README.md, deploy/README.md, deploy/USER-GUIDE.md) must not gain over-claim phrases ("guarantees exclusive", ...) in the new approval wording. Add a similar pin for the documented bypass limits (SAFE-18).

**Live bench `tests/test_phase7_live_gate.py`** (analog `tests/test_phase5_live_gate.py`): sentinels `PHASE5_GATE_OK` / `PHASE5_GATE_STOP` (31-32), stage consumption (`STAGES`, `EXPECTED_POSTS`, `ALLOWED_ENDPOINTS` allow-list 42), evidence record plus pure offline validator `classify_stage/classify_phase` (287-318), `_outside_repo` for `--out`, lazy `_bridge()` import (375-379), `_direct_client(port)` seam (382-385), `_plain()` strips `_mcp` from evidence (367-372), `scan_secret` (658), `_run_refusal` pre-flight refusals (426-440), `--out` must not exist. User-run only (D-20); write steps never repeat.

## Shared Patterns

### Route preamble (non-GET gated)
**Source:** `revit_mcp/editing.py:129-137`; pinned by `test_phase5_gate_wiring.py:78-99`. Apply to every gated route; no new route may skip it. Open reads use `strip_envelope(request)` as first statement instead.

### Never-raise refusal with fixed text
**Source:** `revit_mcp/trust.py:97-111` (`gate_failure`) and `security.py:149-150`. Apply to permits, preflight routes, authorizer. Nothing returned or logged contains body, secret or exception text.

### Envelope (`_mcp`) handling
**Source:** `bridge.py:1195-1224` (CPython), `trust.py:114-142` (Revit). Model-supplied `_mcp` refused; new `permit` key rides beside `secret`/`call_id`; old ext ignoring the new key must be proven harmless (D-19).

### Two-runtime dialect
**Source:** CLAUDE.md. `revit_mcp/*` (permits.py, preflight code): cookie line 1, `"{}".format`, relative imports, no `secrets`/`pathlib`/`typing`/`dataclasses`/`enum`, `if bytes is str` for runtime detection, `parse_request_data` for bodies. Root modules (`policy.py`, `permit.py`, `audit.py`, `bridge.py`): f-strings allowed, never print/stdout.

### Honest outcomes
**Source:** `audit.py` `OUTCOME_LABELS`; `tools/utils.py format_response`. `approved` is not `committed`; `rolled_back` (409) stays an error; `partial` stays non-error.

### Registration by convention
No new MCP tool: `tests/unit/tool_manifest.txt` stays 59 names; preflight routes are bridge-internal and open reads.

## No Analog Found

| File / concern | Role | Data Flow | Reason |
|---|---|---|---|
| Server-side elicitation (`ctx.session.elicit_form`) | service | request-response | No elicitation exists in repo (mcp 1.9.0); use RESEARCH Pattern 2 example |
| Revit-side one-time nonce registry | utility | stateful | No in-process consumption registry exists; use RESEARCH skeleton |
| TOML policy loader/hot reload | service | batch | No TOML or mtime-polling in repo; use RESEARCH loader example |
| pywin32 `sys.path`/DLL shim | config | file-I/O | Only the `libs` insertion exists; extend it |
| In-memory MCP elicitation test harness | test | fixture | No existing; RESEARCH Wave 0 (`mcp.shared.memory` with Hermes-shaped callback) |

## Metadata

**Analog search scope:** `bridge.py`, `audit.py`, `main.py`, `tools/utils.py`, `revit_mcp/{security,trust,editing,worksharing}.py`, `deploy/`, `tests/unit/`, `tests/test_phase5_live_gate.py`, `scripts/conventions.py`
**Files scanned:** ~25 (targeted reads; large files via grep then offset reads)
**Tracked-source gate:** `git ls-files` confirmed audit.py, bridge.py, deploy/server.py, revit_mcp/security.py, tests/test_phase5_live_gate.py tracked; `policy.base.toml` does not exist yet (new).
**Pattern extraction date:** 2026-10-25
