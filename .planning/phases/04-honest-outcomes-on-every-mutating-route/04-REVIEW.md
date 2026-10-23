---
phase: 04-honest-outcomes-on-every-mutating-route
reviewed: 2026-10-23T12:00:00Z
depth: standard
files_reviewed: 50
files_reviewed_list:
  - revit_mcp/annotation.py
  - revit_mcp/building.py
  - revit_mcp/code_execution.py
  - revit_mcp/colors.py
  - revit_mcp/detail.py
  - revit_mcp/document.py
  - revit_mcp/documentation.py
  - revit_mcp/editing.py
  - revit_mcp/interop.py
  - revit_mcp/mep.py
  - revit_mcp/parameters.py
  - revit_mcp/placement.py
  - revit_mcp/rooms.py
  - revit_mcp/structure.py
  - revit_mcp/tags.py
  - revit_mcp/textutils.py
  - revit_mcp/transforms.py
  - revit_mcp/utils.py
  - revit_mcp/view_management.py
  - revit_mcp/worksharing.py
  - tools/annotation_tools.py
  - tools/building_tools.py
  - tools/colors_tools.py
  - tools/detail_tools.py
  - tools/documentation_tools.py
  - tools/editing_tools.py
  - tools/family_tools.py
  - tools/interop_tools.py
  - tools/mep_tools.py
  - tools/room_tools.py
  - tools/structure_tools.py
  - tools/tag_tools.py
  - tools/transform_tools.py
  - tools/utils.py
  - tools/view_management_tools.py
  - scripts/conventions.py
  - scripts/new_tool.py
  - contrib-kit/revitmcp_kit.py
  - CLAUDE.md
  - CONTRIBUTING.md
  - tests/test_phase4_live_outcomes.py
  - tests/unit/test_conventions.py
  - tests/unit/test_format_response.py
  - tests/unit/test_outcome_docstrings.py
  - tests/unit/test_phase4_live_outcomes.py
  - tests/unit/test_routes_analysis_color_identity.py
  - tests/unit/test_routes_document_interop_identity.py
  - tests/unit/test_routes_mep_parameter_identity.py
  - tests/unit/test_routes_view_code_identity.py
  - tests/unit/test_textutils.py
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-10-23
**Depth:** standard
**Files Reviewed:** 50
**Status:** issues_found

## Summary

Reviewed the phase 04 diff (`49ce0ca..HEAD`, planning files excluded). The core design is sound and I
could not find a route where a rollback is reported as success: every one of the 16 transacting
modules commits only through `commit_and_report` (transaction count equals `commit_and_report` count in
each file, and no `.Commit` attribute remains outside the helper), `finalize_outcome`/`classify_outcome`
behave as the truth table in D-04 says, created elements are read only after the committed check, and
every early return inside an open transaction that I traced rolls it back first. The `tests/unit` suite
passes (5218 passed, 3 skipped). The live script `tests/test_phase4_live_outcomes.py` enforces its
seven-route allow-list on every GET and POST, drops `_mcp` from the record, and refuses in-repo paths.

No BLOCKER was found. The findings below are places where a reply, an `outcome` block or the
contributor template says something the code does not back up.

## Warnings

### WR-01: export_document reports a possibly-successful PNG/JPG export as a 422 failure, and never checks the file for PDF/DWG

**File:** `revit_mcp/documentation.py:415-424` and `:467-472`
**Issue:** The expected output path is *guessed* before the export runs (`export_dir/<view name>.png`),
and the new image-export verdict is `os.path.exists(file_path) and mtime >= start - 2`. Revit's
`ImageExportOptions` with `ExportRange.SetOfViews` (the range this route sets, line 443) is documented
to derive the file name from `FilePath` plus the view type and view name, so the file Revit writes is
not necessarily the guessed one. If it differs, a working export is now answered with HTTP 422
`failed` / "expected export file was not created" and the transaction is committed. Before the phase the
same guess only produced a wrong `file_path`/`file_size_kb: 0`; now it flips the verdict. For PDF and
DWG the opposite hole remains: `export_ok` is the bare Boolean from `Document.Export`, and
`file_path` in `outcome.succeeded` and in `exported.file_path` is the same unverified guess (DWG export
with the default options also decorates the name). 04-06-SUMMARY lists "real PNG/JPG file name written
by ExportImage" as not verified live, and the 04-11 live set exercised only `export_ifc`.
**Fix:** After the call, resolve the real file instead of trusting the guess, and use it everywhere:
```python
stem = os.path.join(export_dir, safe_name)
fresh = [p for p in glob.glob(glob.escape(stem) + "*" + ext)   # IronPython: fnmatch on os.listdir
         if os.path.getmtime(p) >= export_started - 2]
export_ok = bool(fresh)
file_path = fresh[0] if fresh else file_path
```
Do this for PDF and DWG too (require a fresh file in addition to the Boolean), and run one live
PNG/PDF/DWG export before the 422 verdict is trusted. Use `os.listdir` plus `startswith`/`endswith`
rather than `glob` if `glob.escape` is unavailable at the 3.4 language level.

### WR-02: edit_family reload-failure 500 reports Committed/succeeded items that never reached the project

**File:** `revit_mcp/placement.py:1031-1041`
**Issue:** `ft` is the transaction on the *family document*, which is closed without saving
(`family_doc.Close(False)`, line 1032). When `LoadFamily` raises, the 500 reply is built with
`exception_outcome(ft, requested, outcome_succeeded, outcome_failed)`. `ft` is `Committed`, so
`exception_outcome` keeps `succeeded` (every applied parameter, `shared:NAME`, `new_type:NAME`) and
`transaction_status` is `"Committed"`. The reply therefore tells the Phase 6 audit reader (and the
model, via the raw 500 body) that those items succeeded, while the message beside it says the reload
failed and the project copy is unchanged. This is the exact "reads as success" shape the phase exists to
remove. The same call sets `touched["family_edited"]` for the identical reason elsewhere, so the code
already knows the commit alone does not mean the project changed.
**Fix:** Build this one reply with an empty `succeeded` and an added failed item for the reload step:
```python
reload_failed = outcome_failed + [{"item": "reload", "reason": str(le)}]
...
"outcome": build_outcome(transaction_status_of(ft), requested, [], reload_failed, [])
```
(import `build_outcome`/`transaction_status_of`, already re-exported by `.utils`).

### WR-03: link_file answers "Linked file ..." inside a 422 failed reply

**File:** `revit_mcp/interop.py:254-275`
**Issue:** When Revit returns no element id (`result_id is None`) the route records a failed item and
`finalize_outcome` answers HTTP 422, but the route's own `data` is built unconditionally with
`"message": "Linked file '<name>'"` (or "Imported file ...") and `"element_id": null`. Unlike
`export_ifc` and `export_document` in this same phase, which switch the message when the operation did
not happen, the 422 body here carries a success sentence next to `status: failed`. The model reads the
raw body of a non-200 reply, so it sees both.
**Fix:**
```python
if result_id is None:
    message = "Revit returned no element id; nothing was {}ed from '{}'".format(mode, file_name)
else:
    message = "{}ed file '{}'".format(mode.capitalize(), file_name)
```

### WR-04: create_view returns 500/400 replies without `outcome` from inside an open transaction

**File:** `revit_mcp/view_management.py:120, 150, 226, 248, 283, 294`
**Issue:** D-14 and the plan text ("D-14 applies to every 500 of a transacting route"), plus CLAUDE.md
("A validation refusal before any transaction ... carries no outcome"), imply that a reply produced after
`t.Start()` carries an `outcome` with the real `transaction_status`. In `_create_view` the transaction
starts at line 59-61, and these six refusals (no view family type found, no floor plan to host the
elevation marker, unsupported `view_type`) are returned after `t.RollBack()` with a bare
`{"error": ...}`. The Phase 6 audit reader cannot tell "rolled back, nothing changed" from "route did not
report". The opposite inconsistency exists in `revit_mcp/detail.py:80-83`, where a refusal made *before*
any transaction (`t` is `None`) carries `outcome` with `transaction_status: null`, contradicting the
documented rule. Either way the "carries an outcome iff a transaction was opened" contract is not
uniform.
**Fix:** Add `"outcome": exception_outcome(t, requested, succeeded, failed)` to the six `create_view`
replies (the RollBack makes it `RolledBack`), and drop the outcome from the pre-transaction `detail.py`
500, or state the exception in CLAUDE.md/CONTRIBUTING.md.

### WR-05: create_dimensions lists elements as dimensioned that it reports as failed

**File:** `revit_mcp/annotation.py:195-199` (with `:133-134`)
**Issue:** During reference collection an element that contributes no reference is added to
`outcome.failed` (line 134, "no geometry reference found"). The dimension is then created from the
remaining references, but `created[0]["elements_dimensioned"]` is set to the *full* `element_ids` list,
so the same reply names the same element id both as dimensioned and as failed. A model that retries only
the failed ids from `outcome.failed` is correct; one that trusts `elements_dimensioned` is not.
**Fix:** Track the ids that actually appended a reference:
```python
referenced_ids = []          # next to element_points
...
if ref_array.Size > refs_before:
    referenced_ids.append(eid)
...
"elements_dimensioned": referenced_ids,
```

## Info

### IN-01: Contributor templates tell the contributor to call `exception_outcome` but do not import it, and show `t` declared inside the `try`

**File:** `scripts/new_tool.py:110` and `:278`; `contrib-kit/revitmcp_kit.py:174` and `:304`
**Issue:** Both templates say "In the outer `except`, build the 500 reply with exception_outcome", but the
generated import line adds only `commit_and_report, finalize_outcome`, so following the instruction
gives a `NameError` inside the error handler. The commented transaction snippet also creates `t` inside
the `try`, whereas every real route hoists `t = None` above it (needed for `exception_outcome(t, ...)`
to work when the exception happens before `Start()`). The stub body (lines 125-134) still returns a
hand-written `"status": "success"` with no `outcome`.
**Fix:** Add `exception_outcome` to `suppress_import` in both generators and add `t = None` plus
`requested/succeeded/failed` hoisting to the commented skeleton.

### IN-02: Live-gate classifier never reads `preflight.tag_element_found`

**File:** `tests/test_phase4_live_outcomes.py:286-303`
**Issue:** `_judge_preflight` checks `status_ok`, `listeners`, `documents` and `parameter_writable`, but
the fifth recorded preflight field (`tag_element_found`) is not judged. `run` itself stops on it before
any write, so a live run is safe, but `classify RECORD.json` (advertised as "re-judges a saved record")
would accept a hand-edited or partial record whose tag target was never read.
**Fix:** Add `if pre.get("tag_element_found") is not True: reasons.append(...)`.

### IN-03: colors routes lose the real status when an exception unwinds the `with DB.Transaction(...)`

**File:** `revit_mcp/colors.py:798, 916` (same shape at `:972, 1031`)
**Issue:** `t` is bound by `with DB.Transaction(...) as t`, so by the time the outer `except` builds
`exception_outcome(t, ...)` the transaction has been disposed (and rolled back by `Dispose`).
`transaction_status_of` swallows the resulting exception and the reply reports
`transaction_status: null` instead of `RolledBack`; `status: error` is returned with HTTP 200 as before.
Not a correctness bug for the model (the error banner still shows), but the audit reader gets "unknown"
where the truth is knowable.
**Fix:** Use `t = DB.Transaction(...)` with an explicit `try/finally`, as every other module does, or
read the status inside the `with` before it exits.

### IN-04: `_set_step` is duplicated between rooms.py and mep.py

**File:** `revit_mcp/rooms.py:22-40`, `revit_mcp/mep.py:22-40`
**Issue:** Two identical helpers. The duplication is forced by the rule that domain modules never import
each other, but `revit_mcp/textutils.py` already hosts the shared outcome helpers and the step helper
touches no Revit type (it takes callables).
**Fix:** Move it to `textutils.py`, re-export through `utils.py`, and import it from both modules.

---

_Reviewed: 2026-10-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
