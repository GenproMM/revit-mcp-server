---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
reviewed: 2026-10-23T00:00:00Z
depth: quick
files_reviewed: 52
files_reviewed_list:
  - bridge.py
  - main.py
  - revit_mcp/annotation.py
  - revit_mcp/building.py
  - revit_mcp/code_execution.py
  - revit_mcp/colors.py
  - revit_mcp/detail.py
  - revit_mcp/document.py
  - revit_mcp/documentation.py
  - revit_mcp/documents.py
  - revit_mcp/editing.py
  - revit_mcp/identity.py
  - revit_mcp/interop.py
  - revit_mcp/mep.py
  - revit_mcp/parameters.py
  - revit_mcp/placement.py
  - revit_mcp/rooms.py
  - revit_mcp/status.py
  - revit_mcp/structure.py
  - revit_mcp/tags.py
  - revit_mcp/textutils.py
  - revit_mcp/transforms.py
  - revit_mcp/view_management.py
  - revit_mcp/worksharing.py
  - scripts/probe_handler_overlap.py
  - startup.py
  - tools/analysis_tools.py
  - tools/annotation_tools.py
  - tools/building_tools.py
  - tools/clash_tools.py
  - tools/code_execution_tools.py
  - tools/colors_tools.py
  - tools/detail_tools.py
  - tools/document_tools.py
  - tools/documentation_tools.py
  - tools/editing_tools.py
  - tools/family_tools.py
  - tools/interop_tools.py
  - tools/mep_tools.py
  - tools/model_tools.py
  - tools/parameter_tools.py
  - tools/process_tools.py
  - tools/room_tools.py
  - tools/status_tools.py
  - tools/structure_tools.py
  - tools/tag_tools.py
  - tools/target_tools.py
  - tools/transform_tools.py
  - tools/utils.py
  - tools/view_management_tools.py
  - tools/view_tools.py
  - tools/worksharing_tools.py
findings:
  critical: 1
  warning: 5
  info: 7
  total: 13
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-10-23
**Depth:** quick (pattern scan plus targeted reads of bridge.py, identity.py, documents.py, document.py, code_execution.py, worksharing.py, placement.py edit_family, status.py, startup.py)
**Files Reviewed:** 52
**Status:** issues_found

## Summary

The Phase 02 identity and document-confinement design holds up under inspection. Findings below are the exceptions.

Verified clean, with no findings:

- Every mutating route except `/execute_code/` (D-15) and `/open_model/` (process-level, D-01) calls `mutation_document_or_response` first. Each handler then passes the guard's `document` to its worker, never the injected `doc`.
- Every `t.Start()` or `ft.Start()` in `revit_mcp/` (30 sites) is followed by `suppress_warnings`.
- No f-strings in `revit_mcp/` or `startup.py`. No flat sibling imports and no cross-domain imports. Every file has an encoding cookie.
- No `json.loads(request.data)`. All POST handlers use `parse_request_data`.
- No bare `DB.ElementId(<int>)`. The only `DB.ElementId(...)` call is `documentation.py:173`, which passes a `BuiltInCategory` enum.
- Tool functions have `ctx` last, and every `await revit_get/post/image` call is wired to `**options` or `target`.
- The only `print` is the `--combined` one, which is guarded.
- `uv run pytest tests/unit` passes: 4054 passed, 3 skipped.

The one material defect is systemic. Mutation handlers discard the `Commit()` status, so a silent rollback is reported as success.

## Critical Issues

### CR-01: 25 mutation handlers discard `Transaction.Commit()` status and report success after a silent rollback

**File:** `revit_mcp/annotation.py:183,362`, `building.py:247,560,651`, `colors.py:865,983`, `detail.py:128`, `documentation.py:98,235,451`, `editing.py:75`, `interop.py:96,225`, `mep.py:161,321,490`, `placement.py:446`, `rooms.py:105,275`, `structure.py:89,273`, `tags.py:219`, `transforms.py:174`, `view_management.py:297`
**Issue:** Each of these sites calls a bare `t.Commit()` and builds a `"status": "success"` reply from in-memory counters.

Every one of these transactions installs `_FailureSwallower` through `suppress_warnings`. On any error-severity failure the swallower returns `ProceedWithRollBack`, and `Commit()` then returns `TransactionStatus.RolledBack` instead of raising. The handler never reads that return value (see `utils.py:20-30`, which describes this exact bug).

Failure scenario:
1. A model calls `create_framing`, `create_duct`, `delete_elements` or `transform_elements` on geometry that triggers an error-severity failure, for example a duct that cannot connect or an element that cannot be deleted.
2. The swallower rolls the transaction back.
3. The route returns `{"status": "success", "created": [...], "count": N}` or "Deleted N elements".
4. The model proceeds as if the change exists. Nothing exists in the model.

`execute_code`, `parameters.py` and `editing.py:236+` already use `commit_and_report`, so the mitigation is known. Only these routes lack it. This pattern predates Phase 02, but Phase 02 touched every one of these files and `format_response` now stamps "Verified Revit process / document" onto the reply, which makes the false success look verified.

**Fix:**
```python
result = commit_and_report(t, swallower)   # swallower = suppress_warnings(t)
if not result["committed"]:
    return routes.make_response(data={
        "status": "rolled_back",
        "transaction_status": result["transaction_status"],
        "failures": result["failures"],
        "message": "Revit rolled the transaction back at Commit(); no changes were saved.",
    }, status=409)
```
Capture the `suppress_warnings(t)` return value at each site, and keep 409, since `format_response` treats "rolled_back" as non-failure only for non-200. Add a unit-level convention check that no `revit_mcp/*.py` contains a bare `.Commit()` statement.

## Warnings

### WR-01: `/execute_code/` leaves its transaction open if `commit_and_report` raises

**File:** `revit_mcp/code_execution.py:126,132,177-187,249`
**Issue:** `captured_output.close()` runs at line 126, before `commit_and_report(t, swallower)` at line 132. If `Commit()` raises, the `except Exception as exec_error` handler calls `captured_output.getvalue()` on the closed `StringIO` (line 182). That raises `ValueError: I/O operation on closed file`.

The new exception escapes the inner handler before `t.RollBack()` at line 186 runs. The outer `except` at line 249 then returns a bare 500 with the transaction still started on `doc`.

Failure scenario:
1. User code leaves the document in a state where `Commit()` throws, for example it ended or rolled back the transaction itself, or it closed the document.
2. The route answers 500.
3. The next request on the headless Routes server meets a dangling open transaction. `Transaction.Start` then fails, or Revit holds the document in a transaction.

**Fix:** Do not close `captured_output` before the commit. Close it in a `finally`. In the handler, use `partial_output = captured_output.getvalue() if not captured_output.closed else ""`. Put `if t.HasStarted() and not t.HasEnded(): t.RollBack()` in a `finally` that also covers the outer `except`.

### WR-02: `edit_family` reports success when the family transaction was rolled back

**File:** `revit_mcp/placement.py:921-922,958-972`
**Issue:** `touched["family_edited"] = (ft.Commit() == Committed)` records the status, but control flow ignores it. The route still reloads the unmodified family into the project and replies `"status": "success"`, `parameters_applied`, `"message": "Edited family ... N param(s) applied"`. Only `documents_changed` carries the truth.

Failure scenario:
1. `NewType` or `Set` raises an error-severity failure.
2. The swallower vetoes the commit.
3. The model reads "success, 3 params applied" in the headline text, since `format_response` projects `message` first.

**Fix:** If `touched["family_edited"]` is false, close the family document without saving and return a 409 `rolled_back` reply listing the failures. Capture the swallower from `suppress_warnings(ft)` and use `commit_and_report`.

### WR-03: `edit_family` shared-parameter add calls `FamilyManager.AddParameter` with arguments that do not match any overload

**File:** `revit_mcp/placement.py:907-913`
**Issue:** The call is `manager.AddParameter(ext_def, cat_set, DB.BuiltInParameterGroup.PG_IDENTITY_DATA, True)`.

The `FamilyManager.AddParameter(ExternalDefinition, ...)` overloads I know take `(ExternalDefinition, BuiltInParameterGroup, bool isInstance)` or `(ExternalDefinition, ForgeTypeId, bool)`. None takes a `CategorySet`. I verified this against my knowledge of the Revit API, not against Revit, so confirm live.

`BuiltInParameterGroup` is also deprecated and removed from newer Revit APIs, and the fleet spans 2024-2027. The inline comment `# instance=False → type parameter` contradicts the value `True`, which means instance.

Failure scenario: every `add_shared_parameters` entry lands in `shared_parameters_failed` with a `TypeError` or `AttributeError` string, while the route still returns "success" overall.

**Fix:** Use the `ForgeTypeId` overload with `DB.GroupTypeId.IdentityData`, falling back to `BuiltInParameterGroup` through try/except. Drop `cat_set`. Pass the intended `isInstance` value and fix the comment. Verify live on 2024 and 2027.

### WR-04: `launch_revit` hands a possibly workshared `model_path` to `Revit.exe`, which wedges the Routes server

**File:** `tools/process_tools.py:376-377,434-441,456`
**Issue:** `model_path` is appended to the command line unconditionally. CLAUDE.md "Known sharp edges" says that launching Revit with a workshared model on the command line pops the workset-selection dialog, and that dialog blocks the headless Routes server forever. The docstring does not warn about this and does not point to `open_model`, which supplies a `WorksetConfiguration`.

Failure scenario:
1. A model calls the launch tool with a central or local `.rvt` path.
2. Revit stops on the dialog.
3. The call waits out the 240 s default and returns "timeout".
4. Revit stays wedged until a human clicks.

**Fix:** In the docstring, state that `model_path` must not be a workshared model and that the recommended flow is to launch with no model, then call `open_model`. Optionally refuse `model_path` outright, since `open_model` covers the use case.

### WR-05: `open_model` default `overwrite_local=True` deletes an arbitrary caller-named file

**File:** `revit_mcp/worksharing.py:171-203,468`
**Issue:** `_make_local_copy` runs `os.remove(local_path)` whenever `os.path.exists(local_path)` and `overwrite` is true. `overwrite_local` defaults to `True`. `local_path` is caller-supplied, with no extension or location check.

Two consequences:
- The default replaces a user's existing local copy, losing any unsynchronised work, without asking.
- `local_path` set to any existing file, for example a `.docx`, deletes it before `CreateNewLocal` runs. If `CreateNewLocal` then fails, the file is already gone.

This is a typed route, not covered by the D-15 `/execute_code/` exception.

**Fix:** Default `overwrite_local` to `False` in both `revit_mcp/worksharing.py` and `tools/worksharing_tools.py`. Require `local_path` to end in `.rvt`, and refuse to remove a file whose header `BasicFileInfo.Extract` cannot read as a Revit file. Prefer renaming the old copy to `*.bak` over deleting it.

## Info

### IN-01: Three colour tools return raw error strings instead of `format_response(...)`

**File:** `tools/colors_tools.py:95-98,146-149,189-192`
**Issue:** The `except Exception` branches return `error_msg` directly. This breaks the "tool functions always return `str` via `format_response`" invariant, and a failure here carries no provenance line. Low impact, since the bridge never raises and only unexpected errors reach it.
**Fix:** `return format_response("Error: ...")`.

### IN-02: `listener_snapshot` reads IPv4 listeners only, but `parse_target` accepts `::1`

**File:** `bridge.py:174,252`
**Issue:** `netstat.exe -ano -p tcp` lists IPv4 sockets only. A hand-built `revit1:` selector with host `::1` can therefore never find its owner and is always refused with "No listener". Likewise an IPv6 listener on the same port is invisible to the collision check. Reachable only through hand-built selectors, because discovery probes `127.0.0.1`.
**Fix:** Either reject `::1` in `parse_target`, or also parse `-p tcpv6` rows.

### IN-03: `get_revit_status` still prints "MCP target: localhost:48884"

**File:** `tools/status_tools.py:101-105` (`revit_get.revit_target` set at `bridge.py:797`)
**Issue:** Per the bridge docstring, `REVIT_HOST` and `REVIT_PORT` "no longer route a call". Printing them as "MCP target" suggests that port is where calls go.
**Fix:** Drop the line, or label it "configured discovery port".

### IN-04: Dead variable and unsafe boolean parsing in `save_document`

**File:** `revit_mcp/document.py:63-67,59`
**Issue:** `is_new` (via `doc.IsModelInPlace`) is assigned and never read. `bool(data.get("overwrite", True))` makes the JSON string `"false"` evaluate to `True`, and a SaveAs overwrites by default.
**Fix:** Remove `is_new`. Parse `overwrite` strictly, accepting only a real boolean or rejecting with 400.

### IN-05: `startup.py` docstring is stale, and the registry import is not isolated

**File:** `startup.py:14-16,136`
**Issue:** The docstring claims that "every cross-module import goes to the flat `utils` helper", which is the opposite of the current relative-import rule. `registry = __import__(...)` at line 136 sits outside the per-domain `try`. If it fails, the whole extension fails to load, which contradicts the isolation promise.
**Fix:** Update the docstring. Guard or comment the registry import as a deliberate hard dependency.

### IN-06: `_project_response` can raise on a non-string `status` or `health`

**File:** `tools/utils.py:162-163`
**Issue:** `response.get("status", "").lower()` raises `AttributeError` when a route sends `"status": null` or a number. A tool must never raise, and the transport coerces it to an opaque "Error: ...".
**Fix:** `str(response.get("status") or "").lower()`.

### IN-07: `BASE_URL` in `bridge.py` is unused

**File:** `bridge.py:149`
**Issue:** `BASE_URL` is computed from the retired single-port configuration and never read. Each client builds its own `base_url` in `_selected_client`.
**Fix:** Remove `BASE_URL`. Keep `REVIT_TARGET`, which `revit_get.revit_target` still uses.

---

_Reviewed: 2026-10-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick_
