---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 06
subsystem: api
tags: [outcome-schema, finalize_outcome, create_sheet, create_schedule, export_document, place_family, edit_family, load_family, transactions, ironpython]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "plan 04-01 outcome helpers (commit_and_report, finalize_outcome, build_outcome, exception_outcome) and the document/interop test world extended in 04-04"
provides:
  - "create_sheet, create_schedule and export_document commit only through commit_and_report; the created element is read only after a committed commit; rollback is a 409 with outcome.succeeded []"
  - "create_sheet: sheet_number and sheet_name are guarded steps (a taken number is a 200 partial); create_schedule: its name and every field not found are failed items beside the schedule id; legacy fields, fields_not_found, available_fields unchanged"
  - "export_document reports the export call's own result: Document.Export Boolean for DWG/PDF, a freshly written file for PNG/JPG; a negative result is a 422 naming the output path (a PDF False is no longer a rolled-back 500)"
  - "place_family commits through commit_and_report; every property it could not set and a failed rotation are outcome.failed steps beside the instance id (200 partial); actual_location is read only after a committed commit; a rollback is a 409 with no fabricated location"
  - "edit_family commits the family-document transaction only through commit_and_report: a rolled-back commit is a 409, closes the family and never calls LoadFamily; no item applied is a 422 without reload; reload failure stays a 500 with the family transaction's real status"
  - "load_family (no transaction) carries outcome with transaction_status null"
  - "The three world invariants (success agrees with classify_outcome, rollback is a 409, 500 names the real status) run over the whole TRANSACTING table with no restriction"
affects: [04-07, 04-11, phase-06-audit-log]

plan_head_before: c59352041d64f708e65e24e5c06c0c89a8a2b838
actuals:
  tokens: 14500   # chars/4 over the +/- lines of the realized diff (58144 chars); the plan estimated 90000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Sheet/schedule/instance: commit first, then read; succeeded is filled only after the committed check and finalize_outcome is called with an empty succeeded and empty data on rollback"
    - "Image export evidence: ExportImage returns nothing, so the file is the evidence and only a file written by this call (mtime >= call start - 2 s) counts"
    - "edit_family gate: finalize_outcome with empty data decides 409/422 before the reload; the legacy-key payload is built after"
    - "Test world: World.values answers an attribute that is itself used as an object (doc.Create); FakeFamilyManager gives edit_family a writable Width parameter"

key-files:
  created: []
  modified:
    - revit_mcp/documentation.py
    - revit_mcp/placement.py
    - tests/unit/test_routes_document_interop_identity.py

key-decisions:
  - "An image export counts only a file written by this call (modification time not older than the call start minus 2 s). A file left by an earlier export of the same view would otherwise turn a failed ExportImage into a success."
  - "A failed export carries no 'exported' block (it would name a file that does not exist); the message states the failure and the output path. A successful export keeps 'exported' unchanged."
  - "A requested rotation on an element whose Location has no Rotate is reported as a failed step 'rotation' (reason 'element location does not support rotation'), not a silent no-op."
  - "edit_family documents_changed reports the family document as changed only when its commit was kept AND at least one item succeeded; a committed edit in which nothing applied is not a change."
  - "edit_family items follow execution order (new_type first, then parameters, then shared); 'already exists' shared parameters are a no-op in neither list and are not counted in requested."

patterns-established:
  - "The document/interop world's invariant tests have no module allow-list any more: OUTCOME_ROWS is the whole TRANSACTING table, so a route added there is covered automatically"

requirements-completed: [TRUTH-01, TRUTH-03, TRUTH-04]

coverage:
  - id: D1
    description: "create_sheet, create_schedule: success carries the new id; rollback is a 409 and the element is never read after the commit event; taken sheet number / schedule name and missing fields are failed steps (200 partial)"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k 'sheet or schedule'"
        status: pass
    human_judgment: false
  - id: D2
    description: "export_document: Boolean or fresh file decides succeeded vs 422; PDF/DWG exceptions are 500 with outcome and RolledBack; rollback is a 409"
    requirement: TRUTH-03
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k 'export_document or dwg_export or pdf_export or image_export or rolled_back_export'"
        status: pass
    human_judgment: false
  - id: D3
    description: "place_family: unset properties and a failed rotation are partial steps; rollback is a 409 with no Location read after the commit and no requested-point location; load_family carries an outcome with null status"
    requirement: TRUTH-04
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k 'place_family or load_family'"
        status: pass
    human_judgment: false
  - id: D4
    description: "edit_family: a rolled-back family commit never reloads (409, no LoadFamily, project unchanged); no item applied is a 422 without reload; partial and reload-failure replies carry the family transaction's outcome"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_edit_family_rolled_back_family_commit_is_a_409_that_never_reloads_the_family"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k 'edit_family'"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every TRANSACTING row (all 8): success agrees with classify_outcome, rollback is a 409 with nothing succeeded, a 500 names the real transaction status"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k every_transacting"
        status: pass
    human_judgment: false
  - id: D6
    description: "Behaviour in a live Revit (real PNG/JPG file name written by ExportImage, real Document.Export Booleans, real sheet-number and schedule-name collisions, real LocationPoint.Rotate result, real EditFamily/LoadFamily)"
    requirement: TRUTH-01
    verification: []
    human_judgment: true
    rationale: "Per D-10 this plan is verified in the fake-pyRevit world only; live confirmation needs a full Revit restart and is plan 04-11. The expected image file name (view name with spaces replaced) is an assumption carried over from the old code."

duration: "about 11 min measured after the reading phase (start time recorded after loading the plan and prior summaries)"
completed: 2026-10-23
---

# Phase 4 Plan 06: documentation and placement outcomes Summary

**`create_sheet`, `create_schedule`, `export_document`, `place_family` and the family-document commit in `edit_family` now commit only through `commit_and_report` and answer with the outcome schema: a taken sheet number, a missing schedule field, an unset property or a failed rotation is a visible partial, an export Revit answers `False` to is a 422, and a rolled-back family edit is a 409 that never reloads into the project.**

## Performance

- **Duration:** about 11 min of measured execution (see frontmatter); reading the plan, summaries and sources came before the clock
- **Completed:** 2026-10-23
- **Tasks:** 3 of 3
- **Files modified:** 3 (all in `files_modified`; none created)

## Accomplishments

- **Task 1, documentation.py:** the three handlers hoist `t`/`requested`/`succeeded`/`failed`, capture the swallower, commit through `commit_and_report`, and on a rollback return the `finalize_outcome` 409 before reading the created sheet or schedule. `sheet_number`, `sheet_name` and the schedule `name` are guarded steps; each requested field not found appends `{item: field, reason: "field not found"}` beside the legacy `fields_not_found`. `_export_document` fixes the expected output path before running, records the export result per format (DWG/PDF Boolean, PNG/JPG fresh-file check), and the PDF False branch now continues to the commit and answers 422 instead of rolling back into a 500; the DWG and PDF exception branches keep their 500 and gain `exception_outcome`.
- **Task 2, placement.py:** `_place_family` appends a structured twin `{item, reason}` for every legacy `properties_failed` entry (`read-only`, `not found`, `unsupported type`, `str(error)`) and for a rotation that returns False, raises or cannot rotate; it reads the instance id and `Location` only after the committed check, and the requested-point fallback survives only for a committed instance whose `Location` cannot be read (bare `except:` narrowed to `except Exception:` with a warning log). `_load_family` adds `build_outcome(None, 1, ...)` to its success, `already_loaded` and 500 replies; the 400/404 validation replies stay without outcome.
- **Task 3, placement.py:** `_edit_family` captures `swallower` after `ft.Start()`, records items (`new_type:NAME`, parameter names, `shared:NAME`), commits through `commit_and_report`, and gates on `finalize_outcome` before touching the project: 409 closes the family and returns, 422 closes it without reload, 200 reloads as before. The reload-failure 500 and the outer 500 carry `exception_outcome(ft, ...)` (`ft` hoisted to `None`).
- **Tests:** 50 new: 17 for Task 1 (sheet 3, schedule 4, export 10), 13 for Task 2 (place_family 9, load_family 4), 8 for Task 3 (edit_family), and 12 from the three invariants now covering the documentation and place_family rows (the whole 8-row TRANSACTING table). World additions: `World.values`, `FakeFamilyManager`/`FakeFamParam` (edit_family now reaches a real success: the old MagicMock manager reported every parameter read-only), `TrackedSheet`, `FakeSchedule`, `TrackedInstance`. Suite: 4920 passed baseline (04-05), now **4970 passed, 3 skipped**. `tests/unit/tool_manifest.txt` unchanged. AST gates print `AST_GATE clean` for documentation.py and placement.py.

## Task Commits

1. **Task 1: sheet, schedule and document export report outcomes (D-06, D-12)** - `92df42d` (feat)
2. **Task 2: place_family properties and rotation as failed steps, load_family outcome (D-12, D-06)** - `af31a2f` (feat)
3. **Task 3: edit_family never reloads after a rolled-back family commit (D-01, D-14)** - `a53c834` (feat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED and GREEN committed together per task, not as separate commits**
- **Found during:** all tasks
- **Issue:** the plan's commit protocol requires `uv run pytest tests/unit` green before every commit, which a standalone RED commit would violate (same resolution as 04-01 to 04-05). Each task's RED was observed failing (16 tests in Task 1, 14 in Task 2, 7 in Task 3) before the implementation and made green before its single commit.
- **Commits:** 92df42d, af31a2f, a53c834

**2. [Rule 2 - Missing critical] An image export must have been written by this call**
- **Found during:** Task 1 (`export_document` PNG/JPG)
- **Issue:** the plan says "whether the expected file exists after ExportImage". A file left by an earlier export of the same view would make a failed `ExportImage` report success, which is the dishonesty the plan removes.
- **Fix:** the file counts only if its modification time is not older than the call start minus 2 s (coarse timestamp slack). A test pins a stale file as a 422.
- **Files modified:** revit_mcp/documentation.py
- **Commit:** 92df42d

**3. [Rule 2 - Missing critical] A rotation that cannot happen is a failed step**
- **Found during:** Task 2 (`place_family`)
- **Issue:** when the instance's `Location` has no `Rotate` the old code skipped silently, so a requested rotation vanished.
- **Fix:** it appends `{item: "rotation", reason: "element location does not support rotation"}`.
- **Files modified:** revit_mcp/placement.py
- **Commit:** af31a2f

**4. [Rule 1 - Bug] edit_family reported the family document as changed when nothing applied**
- **Found during:** Task 3
- **Issue:** `touched["family_edited"]` followed the commit status alone, so a committed edit with every item failed showed `changed: true` for a document that was closed unsaved with no change.
- **Fix:** it is `committed and at least one item succeeded`.
- **Files modified:** revit_mcp/placement.py
- **Commit:** a53c834

**5. [Plan wording] edit_family test names carry "edit_family"**
- The plan's acceptance filter `-k "edit_family and rolled"` selects by test name, so the new edit_family tests start with `test_edit_family_`.

**6. [Plan wording] The old MagicMock family manager was replaced**
- With the unarmed `MagicMock` `FamilyManager`, `fam_param.IsReadOnly` is truthy, so every parameter of an existing edit_family test would classify as failed (a 422). `FamilyDoc` now builds a `FakeFamilyManager` with a writable `Width`; no existing assertion was weakened.

**Total deviations:** 6 (1 blocking-process, 2 missing-critical, 1 bug, 2 plan-wording). **Impact:** none on the shipped contract beyond the added honesty.

## Issues Encountered

- `git commit` prints `failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit; all three landed (verified with `git log`). Harmless, as the orchestrator warned.
- The three files are LF in the working tree (git warns that LF will become CRLF on next touch via autocrlf); edits kept LF. `documentation.py` and `placement.py` were read and written as UTF-8.
- The bash tool choked on heredocs that contain an odd number of apostrophes; edit scripts were written with the Write tool into the scratchpad and run from there.
- `graphify update .` was not run: it rewrites `graphify-out/`, which holds another session's uncommitted changes in this tree.
- REQUIREMENTS.md was not touched (the orchestrator owns requirement completion); no gsd-tools verb edited it. STATE.md and ROADMAP.md were updated through gsd-tools verbs and left uncommitted for the orchestrator.
- Behaviour changes worth knowing: (a) `create_sheet` with a number already in use used to roll back into a 500 and now keeps the sheet and answers 200 `partial` (in real Revit the setter throws inside the transaction, so the reply shape is confirmed live in 04-11); (b) `create_schedule` with a taken name behaves the same; (c) `export_document` PDF with `Document.Export` False used to roll back into a 500 and is now a 422; (d) `edit_family` where every parameter fails used to answer 200 `success` and reload, and is now a 422 without reload.
- Live assumption to confirm in 04-11: for PNG/JPG the expected file is `<export dir>/<view name with spaces replaced>.png|.jpg`, as the old code assumed. If Revit appends the view type or name to `ImageExportOptions.FilePath`, the route now answers a 422 ("expected export file was not created") where it used to claim success with a size of 0 KB.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface. T-04-22 (edit_family reloading after a rolled-back commit), T-04-23 (fabricated location, hidden property failures) and T-04-24 (export ignoring its result) are mitigated and tested; T-04-25 (paths and `str(exc)` in the outcome) is accepted as planned.

## Next Phase Readiness

Ready for 04-07. The whole document/interop world is migrated and its invariant tests cover every row of its TRANSACTING table. Live confirmation of the export Booleans and image file name, the sheet-number and schedule-name collisions, the rotation result and the family edit/reload is plan 04-11 (needs a full Revit restart, never pyRevit Reload).

## Self-Check: PASSED

- Files modified exist and are committed: revit_mcp/documentation.py, revit_mcp/placement.py, tests/unit/test_routes_document_interop_identity.py.
- Commits found: 92df42d, af31a2f, a53c834 (`git log --grep "04-06"`); `git rev-list --count` from `plan_head_before` reports 3.
- Task acceptance criteria re-run: Task 1 AST gate clean, `-k "sheet or schedule or export_document"` 68 passed, `-k refused_document_export` 1 passed; Task 2 `-k "place_family or load_family"` 50 passed, `-k "load_family_refusal or placement_reads"` 4 passed; Task 3 AST gate clean, `-k "edit_family and rolled"` 1 passed, `-k "edit_family or every_transacting"` 56 passed (16 edit_family tests plus 3 x 8 rows = 40 required); full suite 4970 passed, 3 skipped.
- Plan verification: `git show --stat` of each commit lists only `files_modified` paths; no file deleted by any commit; `tests/unit/tool_manifest.txt` unchanged.
