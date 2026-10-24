---
phase: 05-live-secret-gate-and-integrity-enforcement
reviewed: 2026-10-24T20:50:00Z
depth: standard
files_reviewed: 38
files_reviewed_list:
  - revit_mcp/trust.py
  - revit_mcp/security.py
  - revit_mcp/integrity.py
  - revit_mcp/status.py
  - revit_mcp/documents.py
  - revit_mcp/code_execution.py
  - revit_mcp/transforms.py
  - revit_mcp/view_management.py
  - revit_mcp/worksharing.py
  - revit_mcp/building.py
  - revit_mcp/editing.py
  - revit_mcp/document.py
  - revit_mcp/documentation.py
  - revit_mcp/interop.py
  - revit_mcp/placement.py
  - revit_mcp/mep.py
  - revit_mcp/parameters.py
  - revit_mcp/rooms.py
  - revit_mcp/structure.py
  - revit_mcp/tags.py
  - revit_mcp/annotation.py
  - revit_mcp/analysis.py
  - revit_mcp/clash.py
  - revit_mcp/colors.py
  - revit_mcp/detail.py
  - bridge.py
  - tools/status_tools.py
  - startup.py
  - deploy/make_manifest.py
  - scripts/conventions.py
  - scripts/new_tool.py
  - scripts/scan_envelope_tolerance.py
  - contrib-kit/revitmcp_kit.py
  - tests/test_phase5_live_gate.py
  - tests/unit/gate_support.py
  - tests/unit/test_phase5_gate_wiring.py
  - tests/unit/test_phase5_gate_e2e.py
  - tests/unit/test_phase5_status_diagnostics.py
  - tests/unit/test_phase5_live_gate.py
  - tests/unit/test_security_state.py
findings:
  critical: 0
  warning: 5
  info: 8
  total: 13
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-10-24T20:50:00Z
**Depth:** standard
**Files Reviewed:** 38 (plus contrib-kit/conventions.py, tests/unit/inventory_support.py, deploy/secret_tool.py read for cross-reference)
**Status:** issues_found

## Summary

The gate core is sound. I traced `startup.py` -> `security.initialize` -> `security.gate_or_response` -> `trust.split_envelope` / `check_secret` / `evaluate_integrity` and found no bypass:

- Every one of the 41 non-GET routes opens with the gate or, for the seven `OPEN_POST_READ_ROUTES`, with `strip_envelope`. The per-file route diffs are preamble-only (+4 lines per route plus one import), with no behavior drift.
- Ordering is correct: no state gives 401 `server_not_configured`; a missing or wrong secret gives 401 before any 423; only `verified_mismatch` blocks; `unverifiable` never blocks.
- The body is re-serialized from the parsed payload, so the gate and the route share one parse and there is no parser differential.
- The secret is compared by hashing both sides and XOR-accumulating the digests, and it is never logged, returned or echoed. Refusal bodies are fixed text.
- An `initialize()` failure leaves `_STATE = None`, so every gated route answers 401.
- I scanned all of `revit_mcp/*.py` and `startup.py` for IronPython 3.4-incompatible syntax: f-strings, async, `@`, `{**x}`, `[*x]`, variable annotations, numeric underscores and multiple unpacking. None found. Stdlib use is also clean: no `json.JSONDecodeError`, `isascii`, `subprocess.run` or `scandir` in the Revit half.
- `python -m pytest tests/unit` passes in full.

No BLOCKER was found. The five WARNINGs are:

- one unauthenticated read route that takes an attacker-controlled filesystem or UNC path,
- two defects in the live-gate runner (path validation, and one-shot enforcement that exists only on paper),
- a stale contributor-kit conventions copy,
- a "closed by default" sentinel that only recognizes the decorator form of route registration.

The INFO items are dead code, test weaknesses and small inconsistencies.

## Warnings

### WR-01: `/model_worksets/` is an unauthenticated read that takes an attacker-controlled path (UNC / RSN) (D-02)

**File:** `revit_mcp/worksharing.py:331-366` (route), `:126-133` (`_model_exists`), `:220-248` (`_extract_file_info`), `:262-281` (`_preview_worksets`); open-list entry at `revit_mcp/trust.py:48-56`.
**Issue:** The route is on the open list, so a missing or wrong secret is never refused. It passes the caller's `file_path` straight to `os.path.exists`, `DB.ModelPathUtils.ConvertUserVisiblePathToModelPath`, `DB.BasicFileInfo.Extract` and `DB.WorksharingUtils.GetUserWorksetInfo`, and echoes the path back in the 404 text and in the success body (`"file_path": file_path`). The phase claims the secret is the "network barrier against callers on the LAN". For this route it is not, and the effects go beyond reading the current model:

- **Credential coercion.** A UNC path (`\\attacker-host\share\x.rvt`) makes the Revit process authenticate over SMB to a host the caller chooses (NetNTLMv2 exposure for the Windows user running Revit).
- **File-existence oracle.** The 404 versus 200 answer reveals whether any path exists on the machine or its shares.
- **Disclosure of workset names** from any `.rvt` readable by the Revit user.

The seven open reads were classified as "reads" on the basis of model mutation only (`MUTATION_PRIMITIVES` in `test_phase5_gate_wiring.py`). That classification does not consider file-system or network side effects. The related open reads (`clash_check`, `ai_filter`, `material_quantities`, `list_category_parameters`, `document_*`) are caller-addressed model reads and are less severe.
**Fix:** Preferably remove `/model_worksets/` from `OPEN_POST_READ_ROUTES` (`trust.py`, `scripts/conventions.py`, `D02_OPEN` in the wiring test) and gate it like `open_model`, which takes the same path argument and is already gated. If it must stay open, reject non-drive-letter paths before any API call:

```python
text = str(file_path).strip()
if text.startswith("\\\\") or text.startswith("//"):
    return routes.make_response(
        data={"error": "UNC paths are not accepted by this open read"}, status=400)
```

and stop echoing `file_path` in the 404 reply.

### WR-02: Live-gate runner accepts `..` in `--module`, so `corrupt` and `restore` can touch any tracked file

**File:** `tests/test_phase5_live_gate.py:394-402` (`_valid_module`), used at `:433`, `:624`, `:644`; effects at `:626-630` and `:647`.
**Issue:** `_valid_module` checks only the `revit_mcp/` prefix, the `.py` suffix, the absence of `/_`, and `git ls-files --error-unmatch`. I verified that git normalizes the pathspec: `_valid_module(REPO_ROOT, "revit_mcp/../startup.py", require_clean=False)` returns `None`, and `git ls-files --error-unmatch -- revit_mcp/../startup.py` exits 0. Consequences:

- `corrupt --module revit_mcp/../startup.py` appends a comment line to `startup.py` or `bridge.py`. The integrity manifest then no longer matches, and the run would classify an unrelated file as the "chosen module".
- `restore --module revit_mcp/../bridge.py` runs `git checkout -- revit_mcp/../bridge.py` with `require_clean=False`, which silently discards uncommitted edits to any tracked file. That is a data-loss path in a tool the operator runs on a dirty developer tree.

Even for a legitimate module, `restore` discards all uncommitted edits to it, not only the appended marker line. Nothing warns about that.
**Fix:** Reject traversal and non-normalized paths:

```python
import posixpath
if (not isinstance(module, str) or posixpath.normpath(module) != module
        or ".." in module.split("/") or "\\" in module
        or not module.startswith("revit_mcp/") or module.count("/") != 1
        or not module.endswith(".py") or "/_" in module):
    return "--module must be a tracked non-private revit_mcp/<name>.py"
```

In `restore`, undo only the appended marker line instead of `git checkout -- <module>`, or refuse when the module has changes other than the marker.

### WR-03: One-shot accounting of the live write stages is advisory only, and the evidence can be lost after writes were sent

**File:** `tests/test_phase5_live_gate.py:591-617` (`_cmd_run`), `:324-329` (`_save`), `:426-440` (`_run_refusal`).
**Issue:** The module docstring (lines 11-13) says POSTS_SENT>=1 "consumes that stage permanently", and the project memory says live write steps never repeat. Nothing enforces it:

- The only guard is `--out already exists`. A second `run --stage match --out <new file>` repeats all seven POSTs, including the real `create_level` calls (`P5_P_CREATE_<stamp>`). No ledger, lock or sentinel file records that a stage was consumed.
- `_save` runs after the writes, outside any `try`/`finally`. If `_run_steps` is interrupted by a `BaseException` (Ctrl-C, `CancelledError`), or `client.aclose()` raises, or `_save` raises `OSError`, the posts were already sent and no record exists. In the `OSError` case `main` prints `USAGE: ...` and returns 2 and never prints `MSG_CONSUMED`. The operator is told to treat it as a usage error and may rerun the stage.
- The file is created with mode `"x"` only after all the writes, so the existence check does not protect against a concurrent or aborted run.

**Fix:** Persist consumption before the first POST. For example, create the `--out` file with mode `"x"` and the template record (`posts_sent: 0`) before `_run_steps`. Rewrite it atomically in a `finally` that also catches `BaseException`. Print `MSG_CONSUMED` whenever `record["posts_sent"] > 0`, whatever happens afterwards:

```python
_save(args.out, record)           # placeholder created before any write
try:
    ...
finally:
    _rewrite(args.out, record)    # always persists posts_sent
```

For a hard stop, also refuse when a sibling `*.consumed` marker for the stage exists next to the evidence directory.

### WR-04: `contrib-kit/conventions.py` is a stale tracked copy with none of the Phase 4/5 checks, while the kit now scaffolds gated routes

**File:** `contrib-kit/conventions.py:42` (`LOCAL_MODULES` without `identity`, `trust`, `integrity`, `security`); missing: `check_route_gate`, `check_request_parsing`, `check_commit_goes_through_report`, `check_swallower_is_kept` (diff against `scripts/conventions.py`); `contrib-kit/revitmcp_kit.py:15, 31, 376`.
**Issue:** `revitmcp_kit.py` says `conventions.py` beside it is "the exact copy" and imports it by local name. Its `cmd_new` template was changed in this phase to emit the gate preamble, but the tracked `contrib-kit/conventions.py` was not updated. Its `check_package` therefore performs no gate check, no commit/swallower check, and no `request.data` parse check. It also does not flag a flat `from security import ...`. `scripts/build_contrib_kit.py:24, 38` correctly packages `scripts/conventions.py` instead, so the shipped zip is fine. Running the kit from a checkout (`python contrib-kit/revitmcp_kit.py check ...`) silently validates an ungated route as clean. That is exactly the failure mode the "closed by default" invariant exists to prevent, and the stale file is a trap.
**Fix:** Delete the tracked `contrib-kit/conventions.py` (the build already sources `scripts/conventions.py`), or add a unit test that asserts it is byte-identical to `scripts/conventions.py` modulo line endings.

### WR-05: "Closed by default" sentinel and conventions gate check only recognize the `@x.route(...)` decorator form

**File:** `scripts/conventions.py:553-560` (`_route_decorator`), `:663-700` (`check_route_gate`); `tests/unit/inventory_support.py:338-341` (`route_inventory`); consumers `tests/unit/test_phase5_gate_wiring.py:51-61`, `:150-165`.
**Issue:** Both detectors look only at decorators of the form `@<obj>.route(...)` (a `Call` whose `func` is an `Attribute` named `route`). A route registered another way is invisible to every Phase 5 check, and none of the checks is coupled to the real `api` object. Examples: `api.route("/x/", methods=["POST"])(handler)`, or `route = api.route` followed by `@route("/x/", methods=["POST"])`. Such a handler would be neither gated nor seen as ungated, and `test_the_measured_route_counts_are_pinned` (56 routes) would not change. The comment in `conventions.py` calls the rule "closed by default", and the contributor intake runs the same detector on untrusted code. `check_route_registrar` already detects `api.route(...)` calls via `has_routes`, but only to insist that a registrar exists, so the information is available and unused.
**Fix:** In `check_route_gate`, treat any `Call` to `<name>.route` that is not in decorator position, and any decorator that is a Name or Attribute alias of `route`, as a violation ("register routes only with the literal @api.route decorator"). Add a negative test for the non-decorator form. In `route_inventory`, assert that the count of `.route(` calls in the module equals the count of decorators found.

## Info

### IN-01: Dead production code: `trust.gate_applies` and `UNGATED_METHODS`

**File:** `revit_mcp/trust.py:41, 315-327`
**Issue:** `gate_applies` and `UNGATED_METHODS` are referenced only by tests. No production code calls them, since the gate is an explicit per-handler call, not a method switch. They are described as the fail-closed method rule, which can mislead a reader into thinking the gate consults it.
**Fix:** Remove both together with their tests, or call `gate_applies(request.method)` from `gate_or_response` so the documented rule is actually enforced.

### IN-02: Live-gate runner's direct HTTP client ignores the proxy hazard the bridge documents

**File:** `tests/test_phase5_live_gate.py:382-385` (compare `bridge.py:623-632`)
**Issue:** `bridge._selected_client` sets `trust_env=False` because Windows or environment proxies turn localhost traffic into an empty `ReadError` on pyRevit's HTTP/1.0 server. `_direct_client` does not. On a proxied workstation the direct steps could take a different path from the bridge steps, or fail after a counted POST, which burns a one-shot stage on an artifact of the environment.
**Fix:** `httpx.AsyncClient(base_url=..., timeout=30.0, trust_env=False)`.

### IN-03: `scripts/new_tool.py` docstring contradicts the project rule, and scaffolding can leave an orphan route file

**File:** `scripts/new_tool.py:14, 302-303`
**Issue:** The header says generated files avoid "flat helper imports", but the invariant (CLAUDE.md, `check_ironpython_dialect`) is that helper imports must be relative. Separately, `_write(route_path)` succeeds and `_write(tool_path)` can then fail with "already exists", leaving a scaffolded, gated route module with no tool and no manifest entry. The generated POST scaffold also imports `make_element_id, suppress_warnings, commit_and_report, finalize_outcome` that a read-only route never uses.
**Fix:** Reword the docstring ("relative helper imports"). Check both targets for existence before writing either.

### IN-04: Weak or inert assertions in the Phase 5 tests

**File:** `tests/unit/test_phase5_live_gate.py:527, 424`
**Issue:**

- `test_scan_secret_has_exact_status_without_secret_output` asserts `secret not in capsys.readouterr().out + capsys.readouterr().err`. The first `readouterr()` drains both streams, so the second one returns empty strings and stderr is never inspected.
- `test_run_refusals_do_not_write_or_request` has a dead statement `code = proc._cmd_run`.
- The fake `_Client.post` answers 401 for any `/create_level/` or `/execute_code/` body, whatever secret it carries. The match-stage run therefore proves the runner's bookkeeping, not that a wrong secret differs from a missing one.
- There is no test for the abnormal-termination and rerun paths described in WR-03.

**Fix:** Capture once (`captured = capsys.readouterr()`; assert on `captured.out + captured.err`). Delete the dead line. Make the fake compare against the expected secret. Add the rerun and abort cases.

### IN-05: Duplicate initialization in `status.py`

**File:** `revit_mcp/status.py:38, 61`
**Issue:** `identity_data = {}` is assigned at line 38 (needed by the outer `except`) and again at line 61, immediately after the registry block. The second assignment is redundant and obscures that line 38 is the load-bearing one.
**Fix:** Remove line 61.

### IN-06: `get_revit_status` can claim "this MCP server loaded none" when the transport simply has no fingerprint seam

**File:** `tools/status_tools.py:41-57`
**Issue:** When the reply has a `secret` block but `revit_get.secret_fingerprint` is not callable, `local` stays `None` and the function returns "this MCP server loaded none; every mutation is refused (401 missing)". That is a factual claim the code did not establish. In production the seam always exists (`bridge.py:1222`), but a bare or alternate transport would print a false and alarming diagnosis.
**Fix:** If `reader` is not callable, return "" or "the transport does not report its own secret fingerprint".

### IN-07: Integrity scope is narrower than the loaded code

**File:** `revit_mcp/integrity.py:103-139`, `deploy/make_manifest.py:40, 155-167`
**Issue:** `present_py` and the "untracked .py" guard look only at `.py` files directly inside `revit_mcp/`. A file added elsewhere (a `.py` in a sub-package under `revit_mcp/`, or an extra bundle folder that pyRevit scans) is outside the unexpected-file check. The gate's integrity claim ("extension files match the published manifest") is stronger than what is verified, and the status text does not say so.
**Fix:** Document the exact scope (listed files plus top-level `revit_mcp/*.py`) in the status alert and runbook, or walk `revit_mcp/` recursively in both the generator and `observe_tree`.

### IN-08: `scan_envelope_tolerance.py` cannot see a body parse that goes through `getattr` or an alias

**File:** `scripts/scan_envelope_tolerance.py:127-135, 83-90`
**Issue:** The scan recognizes `request.data` only as an attribute load on a `Name` literally called `request`, and only `parse_request_data(<expr>.data)`. `documents.py:561` reads `getattr(request, "data", None)`, and a handler that names the argument `req` would not be seen. A clean `ENVELOPE_SCAN_OK` is used as the static half of the D-06 proof, so these gaps can hide a non-tolerant old handler.
**Fix:** Flag any `getattr(<name>, "data")` and any parameter alias of `request` as a finding, or limit the claim in the docstring to "handlers that use `request.data` directly".

---

_Reviewed: 2026-10-24T20:50:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
