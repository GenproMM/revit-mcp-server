# Phase 5: Live secret gate and integrity enforcement - Pattern Map

**Mapped:** 2026-10-24
**Files analyzed:** 22 new/modified (plus 34 gated and 7 open handler bodies, treated as one fan-out row each)
**Analogs found:** 22 / 22 (all analog paths verified git-tracked; no mirror paths)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `revit_mcp/security.py` (NEW) | helper/provider (load-time state + gate) | request-response | `revit_mcp/identity.py` (`initialize_process_identity`, `mutation_document_or_response`) + `revit_mcp/trust.py` | role-match |
| `startup.py` (mod: `security.initialize` block) | config/bootstrap | event-driven (load) | `startup.py:119-126` identity block | exact |
| `revit_mcp/trust.py` (mod: `OPEN_POST_READ_ROUTES`, `secret_fingerprint`, `clean_body`, hints) | utility | transform | `trust.py:40` `UNGATED_METHODS`, `gate_applies`, `auth_failure` | exact |
| 34 gated handlers in `revit_mcp/<domain>.py` (mod preamble) | route handler | request-response | `revit_mcp/editing.py:125-133` | exact |
| 7 open POST-read handlers (mod `strip_envelope` preamble) | route handler | request-response | same, minus refusal | role-match |
| `revit_mcp/status.py` (mod: secret/integrity/bind block) | route handler | request-response | `status.py` existing `registry.snapshot` / `identity_data` blocks | exact |
| `bridge.py` (mod: `revit_post` envelope, `_secret()` cache) | service/transport | request-response | `bridge.py:803-811` `revit_post`, `with_envelope`, `load_secret` (built, unused) | exact |
| `tools/status_tools.py` (mod: fingerprint compare) | tool | request-response | itself + `format_response` | exact |
| `tests/unit/test_phase5_gate_wiring.py` (NEW) | test (AST sentinel + behavioural) | transform | `tests/unit/test_phase2_inventory.py` (guard-first test) + `inventory_support.route_inventory()` | exact |
| `tests/unit/test_security_state.py` (NEW) | test | request-response | `tests/unit/test_trust_integrity.py`, `test_integrity_e2e.py` | role-match |
| shared test-envelope helper (`tests/unit/conftest.py` or `inventory_support.py`) | test helper | transform | `request_of` in `test_routes_*_identity.py`; `FakeRequest` in `test_document_contracts.py:1290` | exact |
| `tests/unit/test_bridge_secret_client.py` (flip `test_inert_*`) | test | request-response | itself, lines 257-314 | exact |
| `tests/test_phase5_live_gate.py` (NEW) | live runner + classifier | request-response, batch | `tests/test_phase4_live_outcomes.py` | exact |
| `tests/unit/test_phase5_live_gate.py` (NEW) | test | transform | `tests/unit/test_phase4_live_outcomes.py` | exact |
| `scripts/conventions.py` (+`check_route_gate`, `LOCAL_MODULES`) | utility (lint rule) | transform | `check_commit_goes_through_report` (393-423), `check_route_registrar` (476-510) | exact |
| `scripts/new_tool.py`, `scripts/intake_package.py` | utility | transform | `check_route_module` composition (613-622) | role-match |
| `deploy/publish-extension.cmd` (mod: staged swap) | deploy script | batch | itself (lines 31-100) | exact |
| `deploy/rollback-extension.cmd` (NEW, CRLF/ASCII) | deploy script | batch | `deploy/publish-extension.cmd` (ASCII, CRLF) | role-match |
| `deploy/make_manifest.py` (mod: opt-in repo-dest) | utility | file-I/O | itself, `_refuse_repo_dest` (98-110) | exact |
| `tests/unit/test_registration.py`, `test_trust_dialect.py`, `test_conventions.py` (mod) | test | transform | themselves | exact |
| D-06 body-scanner (NEW, checked in) | utility | transform | `scripts/conventions.py` `check_request_parsing` (347-387) | role-match |
| `CLAUDE.md` sharp-edge paragraph | doc | n/a | existing paragraph; keep needles pinned by `test_secret_pipeline.py` | exact |

## Pattern Assignments

### `revit_mcp/security.py` (helper, request-response)

**Analogs:** `startup.py:119-126` (initialize + failure into registry), `revit_mcp/identity.py:570` (`mutation_document_or_response`), `revit_mcp/trust.py` (pure logic).

Helper module, registers NO route (reported as SKIPPED helper by discovery, which is fine). Imports are relative (`from . import trust`), never flat. IronPython 3.4 dialect: `"{}".format`, no f-strings. Encoding cookie line 1. Must `git add` immediately (manifest generator and smoke test fail on an untracked `.py`).

**Core pattern** (RESEARCH sketch lines 493-544, copy as-is; uses only trust.py names verified present: `read_secret_file`, `SECRET_FILE_NAME`, `split_envelope`, `envelope_secret`, `check_secret`, `AUTH_OK`, `AUTH_SERVER_NOT_CONFIGURED`, `auth_failure`, `INTEGRITY_MISMATCH`, `integrity_failure`, `mismatch_files`):
```python
_STATE = None  # None = not initialized; the gate refuses (401 server_not_configured)

def initialize(root, package_dir):          # idempotent, recompute all (pyRevit Reload re-runs startup.py)
    global _STATE
    secret = trust.read_secret_file(os.path.join(package_dir, trust.SECRET_FILE_NAME))
    result = integrity.check_integrity(root)      # never raises, read-only
    _STATE = {"secret": secret, "integrity": result}

def gate_or_response(request):                    # never raises, fail closed
    try:
        envelope, payload = trust.split_envelope(getattr(request, "data", None))
        if _STATE is None: return _refusal(*trust.auth_failure(trust.AUTH_SERVER_NOT_CONFIGURED))
        verdict = trust.check_secret(trust.envelope_secret(envelope), _STATE["secret"])
        if verdict != trust.AUTH_OK: return _refusal(*trust.auth_failure(verdict))
        if _STATE["integrity"].get("state") == trust.INTEGRITY_MISMATCH:
            return _refusal(*trust.integrity_failure(trust.mismatch_files(_STATE["integrity"])))
        request.data = <type-preserving rewrite without _mcp>
        return None
    except Exception:
        return _refusal(*trust.auth_failure(trust.AUTH_MISMATCH))

def _refusal(body, status):
    from pyrevit import routes
    return routes.make_response(data=body, status=status)
```
Type-preserving rewrite (Pitfall 3): bytes -> `json.dumps(payload).encode("utf-8")`, text -> `json.dumps(payload)`, dict -> cleaned dict; keeps truthiness for `if not request.data`. Detect runtime with `if bytes is str:` only, never `unicode` (see `trust.py` `_BYTES_TYPE`/`_TEXT_TYPE` aliases, used in `gate_applies`).

`strip_envelope(request)` = same split + rewrite, never refuses, never raises (open reads, wrong secret included).

**Status block:** `status_block()` computes from `_STATE` plus a request-time .NET call; see `/status/` below.

---

### `startup.py` (bootstrap, event-driven)

**Analog:** `startup.py:119-126` (exact).
```python
    try:
        identity = __import__("{}.identity".format(_PACKAGE), fromlist=["identity"])
        identity.initialize_process_identity()
    except Exception as exc:
        registry.FAILED["identity"] = "{}: {}".format(type(exc).__name__, str(exc))
        logger.exception("Failed to initialize process identity")
```
Add a sibling block right after it (before `for name in _domain_modules(package)`, line 128), `security.initialize(os.path.dirname(package.__path__[0]), package.__path__[0])`, failure -> `registry.FAILED["security"]`. Constraint: `tests/unit/test_phase2_inventory.py:597-616` (`test_startup_installs_no_common_handler_wrapper`) bans `api.<attr>`, decorators, `wraps`, `setattr`, `functools`, and the names `mutation_document_or_response`, `decide_mutation_document`, `attribute_response` in startup source. The block above uses none. No `api` argument pass other than `registrar(api)`.

---

### 34 gated handlers (route handler, request-response)

**Analog:** `revit_mcp/editing.py:7-8, 125-133` (document guard preamble).
```python
from .identity import mutation_document_or_response, request_document_selector, attribute_response
...
    @api.route("/delete_elements/", methods=["POST"])
    def delete_elements_handler(uiapp, doc, request):
        """Delete one or more elements from the Revit model."""
        # G1 explicit guard: first, before any document access, file output or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_delete_elements(document, request), descriptor, uiapp=uiapp)
```
**New preamble** (two statements BEFORE the guard; variable name `gate_refusal`, because the Phase 2 inventory test asserts `refusal` by name):
```python
        gate_refusal = gate_or_response(request)
        if gate_refusal is not None:
            return gate_refusal
```
plus `from .security import gate_or_response` (relative). Routes with no doc guard (`/execute_code/` at `revit_mcp/code_execution.py:265`, `/open_model/`, `/activate_document/`, exports, `/save_document/`, `/link_file/`) get the same two statements as the very first lines; for `/execute_code/` the gate precedes `_stamp_exception(...)` (a refusal carries no stamp, acceptable).
**Open set (7)** `/document_summary/`, `/document_levels/`, `/model_worksets/`, `/material_quantities/`, `/clash_check/`, `/ai_filter/`, `/list_category_parameters/`: single first statement `strip_envelope(request)`.
GET routes: no call at all.

---

### `revit_mcp/trust.py` (utility, transform)

**Analog:** itself, `trust.py:40` and `236-249`.
```python
UNGATED_METHODS = ("GET", "HEAD")
```
Add next to it: `OPEN_POST_READ_ROUTES = frozenset(("/document_summary/", ...))` (route-key form must match `inventory_support` `route.key`, which uses `"/name/"`), `secret_fingerprint(secret)` (first 8 hex of sha256, reuse `_digest`-style hashing at `trust.py:89`), `clean_body(raw, payload)`. Update `_AUTH_HINTS` (`trust.py:42-56`) to the D-07 wording ("Update RevitMCP" or sign in again, then restart the assistant session); tests pinning hints: `test_trust_secret.py`, `test_format_response.py`, `test_secret_gate_e2e.py`. Never put the secret or fingerprint in a hint.

---

### `revit_mcp/status.py` (route handler, request-response)

**Analog:** itself, lines ~20-70: `registry.snapshot(...)` guarded by `try/except` with a `logger.warning` fallback, then `identity_data` built the same way. Add `secret`, `integrity`, `bind` using that same lazy guarded pattern (`from . import security` inside the try; degrade, never fail). `/status/` handler signature is pinned `("verbose",)` on pyRevit's HTTP thread (`inventory_support.py:147-150`): no `uiapp`. Bind: .NET `IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners()`, `str(ep.Address)`, `ep.Port` (snippet at `tests/test_phase2_preflight.py:220-221`) fed to `trust.classify_listeners(endpoints, port)`. Include the block in BOTH the 200 and the 503 branch. Health: `"health": "degraded" if degraded else "healthy"` (status.py:76); degrade on mismatch, exposed, unconfigured secret; not on `unverifiable`. No top-level `error` key.

---

### `bridge.py` (transport, request-response)

**Analog:** `bridge.py:803-811` (`revit_post`) and `bridge.py:836-855` (`_send`, which stays byte-identical).
```python
async def revit_post(endpoint, data, ctx=None, target=None, timeout=30.0, params=None):
    async def write(client) -> Union[Dict, str]:
        return await _send(client, "POST", endpoint, data, timeout, params)
    return await _dispatch("POST", endpoint, ctx, timeout, write, target)
```
Change: build `body = with_envelope(data, _secret())` first; on `ValueError` return `_uncertain("Error: {}".format(exc), "not-sent", None)` (helper at `bridge.py:499`); pass `body` into `write`. Build before `_dispatch`, not in `_send`, so a refusal is not mislabelled "outcome unknown" (Pitfall 4). `_secret()` is a lazy memoized `load_secret()` (never at import; resets in tests). `UNLOCKED_GET`/`NEVER_UNLOCKED` (`bridge.py:868-876`) is the model for the explicit-list-plus-test style used for `OPEN_POST_READ_ROUTES`.

---

### `tests/unit/test_phase5_gate_wiring.py` (AST sentinel)

**Analog:** `tests/unit/test_phase2_inventory.py:436-473` (`test_a_guarded_handler_calls_the_explicit_guard_first_and_attributes_every_reply`) and `tests/unit/inventory_support.py` (`route_inventory()`, route `.key`, `.calls_in()`, `HTTP_THREAD_ALLOWLIST`). Use the RESEARCH sentinel skeleton (lines 563-586). Same file must amend the Phase 2 test: skip the two gate statements, then assert on `statements[2]`/`statements[3]`; compare "no call before guard" against the gate line. Also assert: set of `strip_envelope` callers == `trust.OPEN_POST_READ_ROUTES`; no GET route calls either; every other non-GET calls `gate_or_response`; measured counts 56 routes / 41 non-GET / 15 GET / 34 gated.

---

### Shared test-envelope helper

**Analogs (replace all five):**
- `tests/unit/test_routes_view_code_identity.py:556-559` (same shape in the other three `test_routes_*_identity.py`):
```python
def request_of(body):
    if body is None:
        return types.SimpleNamespace(data=None)
    return types.SimpleNamespace(data=json.dumps(body).encode("utf-8"))
```
- `tests/unit/test_document_contracts.py:1290-1292`: `class FakeRequest(object): def __init__(self, body): self.data = body`.
Put one helper in `tests/unit/conftest.py` (autouse-style fixture pattern at lines 22-60: `monkeypatch`, REPO_ROOT on sys.path) or `inventory_support.py`: configures `security._STATE` with a known test secret and `unverifiable` integrity, and wraps bodies with `{"_mcp": {"secret": TEST_SECRET}}`. No production bypass flag (anti-pattern). Refusal rows stay explicit. Note `request_of(None)` keeps `data=None` (gate then answers 401 missing).

---

### `tests/test_phase5_live_gate.py` and `tests/unit/test_phase5_live_gate.py`

**Analog:** `tests/test_phase4_live_outcomes.py` (746 lines) and `tests/unit/test_phase4_live_outcomes.py` (800 lines).

Structure to copy (line refs in the runner): module docstring with Commands / Output tokens / POSTS_SENT one-shot rule / Safety / Operator procedure (1-107); constants `REPO_ROOT`, `DEFAULT_PORT`, `SENTINEL_OK`, `SENTINEL_STOP`, `VERDICT_OK/STOP`, `STEP_KEYS`, `ALLOWED_ENDPOINTS` frozenset + `_require_allowed(endpoint)` (108-160); `_outside_repo(path)` (185); `_bridge()` production-bridge accessor (201); `evidence_template()` (215); per-step `_judge_*` and `_judge(record)` (286-408); `classify_outcomes(record)` pure (415); `_Parser`/`_build_parser`/`_refusal` (451-506); `_save` never overwrites (653); `_cmd_classify` and `main(argv)` with exit codes 0 ok / 1 stop / 2 usage (717-746). Output `PHASE5_GATE_OK|PHASE5_GATE_STOP` plus `POSTS_SENT=<n>`. Differences: stages L1-L4 (baseline, manifest-match, corrupt, cleanup) as subcommands; negative probes are direct `httpx` POSTs with `Content-Type: text/plain; charset=utf-8` (MCP/bridge would add the secret); raw record outside the repo and must contain no secret value; the runner never reads/prints the secret; distinct uniquely named `create_level` for the post-cleanup positive control (counted, never a retry).

Unit-test side (copy): load the script with `importlib.util.spec_from_file_location("phase5_live_gate_procedure", SCRIPT_PATH)` under a different module name (basename collision with the test file), canned replies rendered by real `tools.utils.format_response`, perturbation tests (every field change -> stop naming the field), runner refuses before any request, a raised POST still counts, AST test that only allowed routes are named.

---

### `scripts/conventions.py` (`check_route_gate`)

**Analog:** `check_commit_goes_through_report` (393-423: parse via `_parse(label, source)`, return `[error]` on a parse error, walk the AST, return a list of one formatted violation string) and `check_route_registrar` (476-510). Compose into `check_route_module` (613-622) by appending `+ check_route_gate(label, source)`. Rule: every `@api.route` handler with a non-GET method must start with `gate_or_response` assignment + `if ... is not None: return` (or `strip_envelope` only for routes in the mirrored open set); GET handlers must not call either. Mirror the open-set constant (pinned equal to `trust.OPEN_POST_READ_ROUTES` by test, like the `bridge.py`/`trust.py` constant pins). Extend `LOCAL_MODULES` (line 42) from `{"utils", "textutils", "registry", "revit_mcp"}` with `identity`, `trust`, `integrity`, `security`. Update `scripts/new_tool.py` template and `scripts/intake_package.py` to emit and check the preamble.

---

### `deploy/publish-extension.cmd` (staged swap) and `deploy/rollback-extension.cmd`

**Analog:** `deploy/publish-extension.cmd`. Reuse verbatim: header comment style, `setlocal`, `call "%~dp0config.cmd" || exit /b 1`, `find-python.cmd` + `MCP_PYEXE` check, extension.json `findstr` guards (lines 40-49), allow-list copy (63-70), robocopy line with `/XJ /XD __pycache__ /XF *.pyc _bridge_secret _manifest.json` (73-75), `secret_tool.py stage ... --dest "%DEST%\revit_mcp\_bridge_secret"` (82), `make_manifest.py --repo "%REPO%" --dest "%DEST%"` (89, last write), installer-script robocopy with the trailing-dot trick (95-96).
Change: `DEST` -> `%MCP_SHARE_ROOT%\ext-staging\%MCP_EXT_NAME%`; everything (secret, manifest, `secret_tool verify`, integrity self-check) happens in staging; then swap (RESEARCH lines 590-599): `move LIVE PREV` first (failure leaves live intact), then `move STAGE LIVE`, on failure move PREV back. `ext-previous` created if absent. Fallback `robocopy /MIR` only if the SMB rename is blocked (A1; return to user).
`rollback-extension.cmd` (NEW): same header/`config.cmd` preamble; reverse swap `ext-previous\` -> `ext\`; one command, no git. ASCII-only, CRLF (existing smoke test pins both; `publish-extension.cmd` is "ASCII text, with CRLF"; note `build-payload.cmd`/`update.cmd` show no CRLF, so copy the publish script's line endings, not theirs).

---

### `deploy/make_manifest.py` (opt-in repo dest)

**Analog:** itself, `_refuse_repo_dest` (98-110) and `build_manifest` (128-134 untracked `.py` refusal). Add opt-in `allow_repo_dest`/`--allow-repo-dest`, accepted only when `git check-ignore` exits 0 for the target `_manifest.json` (`.gitignore:37`). Default and the existing refusal test in `tests/unit/test_make_manifest.py` unchanged; add a test that the flag is refused when the path is not ignored.

---

### `tests/unit/test_bridge_secret_client.py` (flip inert pins)

**Analog:** itself, lines 257-314 (`test_inert_send_posts_exactly_json_dumps`, `test_inert_no_production_call_sites` using `_production_files()` + `_call_names(tree)`, `test_inert_load_secret_is_not_run_at_import`). Flip the first to assert the body carries `_mcp`; second to assert `with_envelope`/`load_secret` ARE called from `bridge.py` only; third keeps "no Name reference to `load_secret` at module import level" (memoized lazy accessor).

---

## Shared Patterns

### Gate-first, never-raise handler contract
**Source:** `revit_mcp/editing.py:125-133` (guard preamble) and CLAUDE.md "Route handlers never raise".
**Apply to:** every non-GET handler; refusals (401/423) carry no `outcome` block, built via `routes.make_response(data=..., status=...)`.

### Initialization-failure isolation
**Source:** `startup.py:119-126`.
**Apply to:** `security.initialize`; failure lands in `registry.FAILED["security"]` (health degraded) and the gate treats uninitialized state as 401 `server_not_configured` (closed, never open).

### Explicit list + guard test (closed by default)
**Source:** `bridge.py:868-876` `UNLOCKED_GET` / `NEVER_UNLOCKED` with a pinning test; `trust.py:40` `UNGATED_METHODS`.
**Apply to:** `OPEN_POST_READ_ROUTES` in `trust.py`, mirrored in `scripts/conventions.py`; AST sentinel compares both to the real route inventory.

### IronPython-3.4 dialect + relative imports
**Source:** `scripts/conventions.py` `check_ironpython_dialect` (191+), `LOCAL_MODULES` (42).
**Apply to:** `security.py`, every handler edit; add `security.py` to `tests/unit/test_trust_dialect.py` and `security` to the helper tuples in `tests/unit/test_registration.py` (lines ~238, ~256).

### Test-and-live-runner evidence discipline
**Source:** `tests/test_phase4_live_outcomes.py` (one-shot, `POSTS_SENT`, record outside repo, classifier never grants acceptance alone).
**Apply to:** Phase 5 live runner; direct HTTP negative probes only; secret never printed or recorded.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| .NET listener adapter in `security.py`/`status.py` | helper | request-response | Only a test-script snippet exists (`tests/test_phase2_preflight.py:220-221`); no production code reads the listener table on the Revit side. Use RESEARCH Pattern 5. |
| Atomic folder swap with `ext-previous\` | deploy | batch | No existing swap/rename logic; payload uses `versions\` + junction (see `deploy/README.md` Layout/Rollback) as the conceptual analog only. Use RESEARCH skeleton lines 590-599. |
| D-06 scanner (any `request.data` use not via `parse_request_data`, iteration/echo of body) | utility | transform | Only a prototype in RESEARCH Open Question 3; structure it after `check_request_parsing` (`scripts/conventions.py:347`). |

## Metadata

**Analog search scope:** `startup.py`, `bridge.py`, `revit_mcp/`, `tools/`, `tests/`, `tests/unit/`, `scripts/`, `deploy/`.
**Files scanned:** ~25 read or grepped; tracked-source gate: `git ls-files` confirmed for `revit_mcp/trust.py`, `tests/unit/inventory_support.py`, and `deploy/*` (listing).
**Pattern extraction date:** 2026-10-24
