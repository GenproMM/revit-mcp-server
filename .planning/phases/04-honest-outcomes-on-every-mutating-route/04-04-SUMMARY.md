---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 04
subsystem: api
tags: [outcome-schema, finalize_outcome, delete_elements, export_ifc, link_file, save_document, modify_element, transactions, ironpython]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "plan 04-01 outcome helpers (commit_and_report, finalize_outcome, build_outcome, exception_outcome) and the route pattern proven on tag_elements"
provides:
  - "delete_elements commits only through commit_and_report; success carries outcome beside deleted_ids/cascaded_ids/deleted_count/message; rollback is a 409 without deleted_ids; stays all-or-nothing (D-05)"
  - "modify_element success classified through finalize_outcome (partial 200 / failed 422), item = parameter name; literal 409 keeps attempted_changes and gains outcome"
  - "export_ifc commits through commit_and_report and reads the Boolean Document.Export returns: False is a 422 failed item 'Document.Export returned False' (D-06)"
  - "link_file with no element id back from Revit is a 422 failed item (file path) instead of success with element_id null"
  - "save_document (still no transaction) carries outcome with transaction_status null on both success replies and every 500"
  - "Fake document/interop world: Transaction.GetStatus, transactions list, writable-parameter arming, Export hook, configurable imported id, three world-wide invariants over the editing and interop rows"
affects: [04-05, 04-06, 04-07, phase-06-audit-log]

plan_head_before: d8652374128f67ebfdcda05b9f3cfb900453e2df
actuals:
  tokens: 8600   # chars/4 over the +/- lines of the realized diff (34558 chars); the plan estimated 75000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Local fail(param_name, reason) closure in modify_element: one reason text feeds both the legacy failed entry and outcome.failed"
    - "_document_handle(doc, preferred): the item a save outcome names (requested path, else the document's path, else its title); never raises"
    - "Test arming for this world: arm(world, items, missing, read_only) installs a (None, 'GetElement') hook that answers elements with a writable Mark parameter; reach(world, key) arms and opens one document"

key-files:
  created: []
  modified:
    - revit_mcp/editing.py
    - revit_mcp/interop.py
    - revit_mcp/document.py
    - tests/unit/test_routes_document_interop_identity.py

key-decisions:
  - "delete_elements fills outcome.succeeded with the requested ids only after a committed commit; a committed call deleted every requested element, so it never answers partial (D-05). The legacy de-duplicated deleted_ids and cascaded_ids are untouched."
  - "export_ifc appends succeeded only when Export returned True and the commit was kept; file size is read only for that case. A False return is a failed item even when the commit itself succeeded, so the reply is a 422 with transaction_status Committed."
  - "The exporter's own model changes stay committed with the export transaction, as before (A3: Autodesk's sample rolls them back). D-06 says migrate onto commit_and_report, not change commit vs rollback; recorded for the user as an open question."
  - "save_document item for a 500 is the requested save-as path when given, else the document's path or title; for a success it is the path the document reports after the save, falling back to its title when that path is empty."
  - "In link_file an .rvt is only ever linked, so mode is now set to 'link' in that branch: the failed reason, the 'mode' key and the message no longer say 'imported' for a linked Revit file."

patterns-established:
  - "The three test_every_transacting_* invariants take a module allow-list (OUTCOME_MODULES). Plan 04-06 adds documentation and placement to it until it covers the whole TRANSACTING table"

requirements-completed: [TRUTH-01, TRUTH-02, TRUTH-03]

coverage:
  - id: D1
    description: "delete_elements reports the real commit: 200 success with outcome, 409 on rollback with no deleted_ids, 404 before any transaction for a missing id, 500 with outcome, never partial"
    requirement: TRUTH-02
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k 'delete'"
        status: pass
    human_judgment: false
  - id: D2
    description: "modify_element is classified honestly: some parameters failing is 200 partial, all failing is 422, rollback is 409 with attempted_changes and outcome"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k 'modify'"
        status: pass
    human_judgment: false
  - id: D3
    description: "export_ifc reports Revit's own Boolean: True is succeeded, False is a 422 failed item, rollback is a 409, a raising Export is a 500 with outcome"
    requirement: TRUTH-02
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k 'export_ifc'"
        status: pass
    human_judgment: false
  - id: D4
    description: "link_file with no element id is a 422 naming the file; with an id it is a 200 success; save_document carries an outcome with transaction_status null and still opens no transaction"
    requirement: TRUTH-03
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k 'link_file or import or save'"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_save_document_source_opens_no_transaction"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every editing and interop TRANSACTING row: success agrees with classify_outcome, rollback is a 409 with nothing succeeded, a 500 names the real transaction status"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py -k every_transacting"
        status: pass
    human_judgment: false
  - id: D6
    description: "Behaviour in a live Revit (real Document.Export Boolean, real Import/Link out-reference, real Delete cascade, real Save)"
    requirement: TRUTH-02
    verification: []
    human_judgment: true
    rationale: "Per D-10 this plan is verified in the fake-pyRevit world only; live confirmation needs a full Revit restart and is plan 04-11"

duration: "about 6 min measured after the reading phase (start time was recorded after loading the plan and prior summaries)"
completed: 2026-10-23
---

# Phase 4 Plan 04: delete, export, link and save outcomes Summary

**`delete_elements` and `export_ifc`, the two gaps PROJECT.md names, now commit only through `commit_and_report` and answer with the outcome schema: a delete is all-or-nothing and says so, and an export that Revit's `Document.Export` answers `False` to is a 422, not a success. `modify_element`, `link_file` and `save_document` report the same schema.**

## Performance

- **Duration:** about 6 min of measured execution (see frontmatter); reading the plan, summaries and sources came before the clock
- **Completed:** 2026-10-23
- **Tasks:** 2 of 2
- **Files modified:** 4 (all in `files_modified`; none created)

## Accomplishments

- **Task 1, editing.py:** `_delete_elements` keeps its pre-validation loop and its 404; the swallower is captured, `commit_and_report` is the only commit, `outcome.succeeded` is the requested ids after a kept commit, and the reply goes through `finalize_outcome` with `deleted_count`, `deleted_ids`, `cascaded_ids` and `message` as data (so a rollback is a 409 with no `deleted_ids`). A mid-loop exception still rolls back and re-raises into a 500 that carries the outcome. `_modify_element` tracks `succeeded` (parameter names) and `outcome_failed` through a local `fail(param_name, reason)` closure; success goes through `finalize_outcome`, the literal 409 branch keeps `attempted_changes` and gains `outcome`.
- **Task 2, interop.py:** `_export_ifc` keeps `export_ok = bool(doc.Export(...))` inside the transaction, commits through `commit_and_report`, puts the path in `succeeded` or `{item: path, reason: "Document.Export returned False"}` in `failed`, reads the file size only for a kept successful export and words the message accordingly. `_link_file` fails the file path when no element id came back (`"Revit returned no element id for the {mode}ed file"`), otherwise succeeds it; the unsupported-extension 400 is untouched.
- **Task 2, document.py:** still no `DB.Transaction`. Both success replies carry `build_outcome(None, 1, [handle], [], [])`, and every 500 (including the worksharing-options one) carries `failed [{item, reason: str(exc)}]`. The never-saved 400 stays without an outcome.
- **Tests:** the fake world gained `Transaction.GetStatus`, `transactions`, a `(None, name)` hook fallback, `db.StorageType`, distinguishable `db.ElementId`s, a configurable `imported_id` behind the `clr.Reference` double, and `arm`/`reach` helpers with writable and read-only `Mark` parameters. 40 new tests cover delete (committed, rolled back, missing id, mid-loop raise, cannot start, cascade), modify (partial, all read-only, success keys, rollback, cannot start), export (True, False, rollback, raise), link (no id as import and as link, id, unsupported type), save (in place, save-as, raises, save-as raises, untitled, never saved) and the three invariants over the editing and interop rows (`OUTCOME_MODULES`).
- Suite: 4854 passed baseline (04-03), now **4891 passed, 3 skipped**. `tests/unit/tool_manifest.txt` unchanged. AST gates print `AST_GATE clean` for editing.py, interop.py and document.py.

## Task Commits

1. **Task 1: delete_elements onto commit_and_report (D-05) and modify_element classified** - `4594272` (feat)
2. **Task 2: export_ifc uses the Export result, link_file and save_document report outcomes (D-06)** - `a701ce8` (feat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED and GREEN committed together per task, not as separate commits**
- **Found during:** both tasks
- **Issue:** the plan's commit protocol requires `uv run pytest tests/unit` green before every commit, which a standalone RED commit would violate (same resolution as 04-01 to 04-03). Each task's RED was observed failing (17 tests in Task 1, 18 in Task 2) before the implementation and then made green before its single commit.
- **Commit:** 4594272, a701ce8

**2. [Rule 1 - Bug] An .rvt file reported the mode that was asked for, not the one it got**
- **Found during:** Task 2 (`link_file`)
- **Issue:** the `.rvt` branch always creates a link, but `mode` kept the request's value, so an `.rvt` asked to be "imported" said "Imported file", and the new failed reason would have said "imported" too.
- **Fix:** `mode = "link"` at the top of the `.rvt` branch. The `mode` key of the reply, the message and the failed reason now agree with what Revit did.
- **Files modified:** revit_mcp/interop.py
- **Commit:** a701ce8

**3. [Plan wording] Four export test names start with `test_export_ifc_`**
- The plan's acceptance filter `-k "export_ifc and (False or 422)"` selects by test name, so the four export tests carry `export_ifc` in their names.

**4. [Plan wording] The invariant tests accept 200 or 422 before asserting 200**
- `test_every_transacting_success_...` first checks the status agrees with `classify_outcome` (which also gives a readable failure for a 422) and then asserts the armed row reached a real 200, so an unarmed row cannot hide behind a 422.

**Total deviations:** 4 (1 blocking-process, 1 bug, 2 plan-wording). **Impact:** none on the shipped contract.

## Issues Encountered

- `git commit` prints `failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit; both commits landed (verified with `git log`). Harmless, as the orchestrator warned.
- The four files are LF in the working tree (git warns that LF will become CRLF on next touch via autocrlf); edits kept LF. `revit_mcp/document.py` is UTF-8 and was read and written as UTF-8.
- `graphify update .` was not run: it rewrites `graphify-out/`, which holds another session's uncommitted changes in this tree.
- REQUIREMENTS.md was not touched (the orchestrator owns requirement completion); no gsd-tools verb edited it.
- Behaviour changes worth knowing: (a) `modify_element` where every parameter fails (not found, read-only, set raised) used to answer 200 `success` and now answers 422; (b) `link_file` where Revit hands back no element id used to answer 200 with `element_id: null` and now answers 422; (c) `export_ifc` where `Document.Export` returns False used to answer 200 `Exported IFC` and now answers 422.
- Open question for the user (A3): the IFC exporter's own changes are committed with the export transaction, as before; Autodesk's sample rolls them back instead. This plan kept the commit.
- An id that Revit cascades into another requested id is reported once in `deleted_ids` (existing de-duplication) while `outcome.succeeded` lists the requested ids as given.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface; `outcome.failed[].reason` is `str(exc)` or fixed route text and `build_outcome` copies only `item` and `reason`. T-04-14 (delete bare commit), T-04-15 (export ignoring Export's Boolean) and T-04-16 (a partial delete) are mitigated and tested; T-04-17 (paths in the outcome) is accepted as planned.

## Next Phase Readiness

Ready for 04-05. Plan 04-06 migrates documentation and placement in this same world: add `"documentation"` and `"placement"` to `OUTCOME_MODULES` and `"outcome"` to the pinned key lists in the same commit as each module change. `arm` and `reach` are already in place for the TRANSACTING rows of those modules. Live confirmation of the export Boolean, the import out-reference and the delete cascade is plan 04-11.

## Self-Check: PASSED

- Files modified exist and are committed: revit_mcp/editing.py, revit_mcp/interop.py, revit_mcp/document.py, tests/unit/test_routes_document_interop_identity.py.
- Commits found: 4594272, a701ce8 (`git log --grep "04-04"`); `git rev-list --count` from `plan_head_before` reports 2.
- Task acceptance criteria re-run: Task 1 AST gate clean, `-k "delete or modify"` 52 passed, `-k "delete and (404 or missing)"` 2 passed; Task 2 AST gate clean, `-k "export_ifc or link_file or save"` 71 passed, `-k "export_ifc and (False or 422)"` 1 passed; full suite 4891 passed, 3 skipped.
- Plan verification: `git show --stat` of each commit lists only `files_modified` paths; no file deleted by either commit; `tests/unit/tool_manifest.txt` unchanged.
