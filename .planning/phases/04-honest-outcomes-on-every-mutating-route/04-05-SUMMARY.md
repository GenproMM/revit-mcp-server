---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 05
subsystem: api
tags: [outcome-schema, finalize_outcome, transform_elements, create_view, set_active_view, open_model, execute_code, transactions, ironpython]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "plan 04-01 outcome helpers (commit_and_report, finalize_outcome, build_outcome, exception_outcome) and the route pattern proven on tag_elements"
provides:
  - "transform_elements commits only through commit_and_report; success carries outcome (succeeded = every requested id) beside operation/count/message/new_element_ids; rollback is a 409 without count or operation; stays all-or-nothing"
  - "create_view commits only through commit_and_report; the view id and type are read only after a committed commit; a view that cannot take its name is a 200 partial (failed item 'name'); no view created is a 422 (failed item 'view')"
  - "set_active_view (no transaction) carries outcome with transaction_status null on success and on its 500"
  - "open_model (no transaction) carries outcome with transaction_status null: succeeded [requested file path] on success, failed [{item: file path, reason}] on its 500s after validation"
  - "/execute_code/ keeps its literal 409 and error bodies and adds outcome with the real transaction status (requested null, empty lists, Revit failures) on success, 409, error and outer-500 replies"
  - "View/code test world: Transaction.GetStatus, transactions list, three test_every_transacting_* invariants over the whole TRANSACTING table"
affects: [04-06, 04-07, phase-06-audit-log]

plan_head_before: 6f275fc88c9801c9d3f5c31eb0665591460bf794
actuals:
  tokens: 6550   # chars/4 over the +/- lines of the realized diff (26215 chars); the plan estimated 75000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "create_view: commit first, then read the view; succeeded is filled only after the committed check, and finalize_outcome is called with an empty succeeded on rollback"
    - "open_model: a local open_failed(text) closure builds the null-status failed outcome from the requested file path (hoisted so the outer except can use it)"
    - "Test double: TrackedView logs every public read as a viewread event, so a test can prove nothing was read from the view before or after the commit event"

key-files:
  created: []
  modified:
    - revit_mcp/transforms.py
    - revit_mcp/view_management.py
    - revit_mcp/worksharing.py
    - revit_mcp/code_execution.py
    - tests/unit/test_routes_view_code_identity.py

key-decisions:
  - "transform_elements fills outcome.succeeded with the requested ids as given (duplicates kept) only after a committed commit; a committed transform moved every requested element, so it never answers partial (D-05 applied to D-01)."
  - "create_view reports the view Revit actually made: when the name step fails the reply's name is read back from the view (falling back to the requested name) and the message says the requested name could not be taken, with the reason."
  - "A 409 on create_view carries no view_id, name or view_type: the view never existed, so nothing is read from it."
  - "execute_code outcome carries status and Revit failures only; the code text, output and traceback stay in their existing keys (T-04-19). Its D-15 scope notice and attribution behaviour are untouched."
  - "open_model: outcome is added to every 500 that follows validation (workset configuration error, local-copy failure, open failure, no document) and to the outer 500 once the file path is known; 400/404/503 pre-open replies stay without outcome."

patterns-established:
  - "The three test_every_transacting_* invariants in this world run over the full TRANSACTING table (both rows), so a future route added to the table is covered automatically"

requirements-completed: [TRUTH-01]

coverage:
  - id: D1
    description: "transform_elements: committed move/copy reports every requested id; rollback is a 409 with nothing succeeded; mid-way raise is a 500 with transaction_status RolledBack; pre-commit refusals carry no outcome"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py -k 'transform'"
        status: pass
    human_judgment: false
  - id: D2
    description: "create_view: success succeeded [view id]; name failure is a partial; no view is a 422; rollback is a 409 and the view is never read after the commit event"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py -k 'create_view or created_view or view_that_cannot or no_view'"
        status: pass
    human_judgment: false
  - id: D3
    description: "set_active_view and open_model carry outcome with transaction_status null and open no transaction; refusals and validation replies carry none"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py -k 'set_active_view or open_model'"
        status: pass
    human_judgment: false
  - id: D4
    description: "execute_code: outcome on success (Committed), 409 (RolledBack) and error (status after rollback); never carries the code, output or traceback; early errors carry none"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py -k 'execute_code'"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every TRANSACTING row: success agrees with classify_outcome, rollback is a 409 with nothing succeeded, a 500 names the real transaction status"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py -k every_transacting"
        status: pass
    human_judgment: false
  - id: D6
    description: "Behaviour in a live Revit (real Name-assignment failure on a duplicate view name, real CreateIsometric/CreateSection results, real transform, real open and code runs)"
    requirement: TRUTH-01
    verification: []
    human_judgment: true
    rationale: "Per D-10 this plan is verified in the fake-pyRevit world only; live confirmation needs a full Revit restart and is plan 04-11"

duration: "about 5 min measured after the reading phase (start time was recorded after loading the plan and prior summaries)"
completed: 2026-10-23
---

# Phase 4 Plan 05: view and code route outcomes Summary

**`transform_elements` and `create_view` now commit only through `commit_and_report` and answer with the outcome schema (a rollback is a 409, `create_view` reads the new view only after a kept commit and treats the name as its own step), while `set_active_view`, `open_model` and `/execute_code/` carry the same `outcome` block, with a null transaction status where no transaction exists.**

## Performance

- **Duration:** about 5 min of measured execution (see frontmatter); reading the plan, summaries and sources came before the clock
- **Completed:** 2026-10-23
- **Tasks:** 2 of 2
- **Files modified:** 5 (all in `files_modified`; none created)

## Accomplishments

- **Task 1, transforms.py:** `_transform_elements` hoists `t`/`requested`/`succeeded`/`failed`, captures the swallower, keeps every pre-validation and in-transaction validation branch as it was, commits through `commit_and_report` and replies through `finalize_outcome` (data keeps `operation`, `count`, `message`, `new_element_ids` for copy). The 500 gains `exception_outcome`.
- **Task 1, view_management.py:** `_create_view` appends `{"item": "view", ...}` when Revit returns no view, wraps `new_view.Name = name` as the guarded step `"name"`, commits through `commit_and_report`, returns the `finalize_outcome` 409 before touching the view, and otherwise reads the id and type after the commit. `_set_active_view` adds `build_outcome(None, 1, [view_name], [], [])` to its success and the failed form to its 500 (view name read defensively).
- **Task 2, worksharing.py:** `_open_model` still opens no transaction; success carries `build_outcome(None, 1, [file_path], [], [])`; the workset-configuration, local-copy, open-failed, no-document and outer 500s carry the failed form with the reply's own error text as the reason.
- **Task 2, code_execution.py:** both literal branches kept; success and 409 add `build_outcome(commit_result["transaction_status"], None, [], [], commit_result["failures"])`; the exec-error reply adds `exception_outcome(t, None, [], [])` after its rollback; the outer 500 adds it when a transaction exists.
- **Tests:** the fake `Transaction` gained a real `GetStatus`, a `status` that follows Start/Commit/RollBack, a truthful `HasEnded` and a `world.transactions` list. 29 new tests: the three `every_transacting` invariants (2 rows each), transform (5), create_view (6), set_active_view (3), open_model (4), execute_code (5). Pinned key lists for transform_elements, create_view, set_active_view, open_model and execute_code each gained only `"outcome"`.
- Suite: 4891 passed baseline (04-04), now **4920 passed, 3 skipped**. `tests/unit/tool_manifest.txt` unchanged. AST gates print `AST_GATE clean` for all four modules; `test_conventions` and `test_registration` green.

## Task Commits

1. **Task 1: transform_elements, create_view and set_active_view report outcomes (D-01, D-06, D-12)** - `d7764af` (feat)
2. **Task 2: open_model and execute_code carry the outcome schema (D-06, D-13)** - `af9b158` (feat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED and GREEN committed together per task, not as separate commits**
- **Found during:** both tasks
- **Issue:** the plan's commit protocol requires `uv run pytest tests/unit` green before every commit, which a standalone RED commit would violate (same resolution as 04-01 to 04-04). Each task's RED was observed failing (19 tests in Task 1, 9 in Task 2) before the implementation and then made green before its single commit.
- **Commit:** d7764af, af9b158

**2. [Plan wording] Task 2's pinned-key edits were applied in Task 2, not Task 1**
- The open_model and execute_code pinned key sets gain `"outcome"` in the commit that changes those modules, so every commit is green. The open_model added-key set stays `{"document", "process_identity"}` because `"outcome"` joined the original list, which is what the plan describes.

**3. [Plan wording] create_view reply names the view Revit actually made after a failed name step**
- Beyond the plan text: on a `name` failure `reply["name"]` is the view's real name (read back defensively) rather than the requested one, and the message states the requested name and the reason. A reply naming a name the view does not have would be the same kind of dishonesty this phase removes.

**Total deviations:** 3 (1 blocking-process, 2 plan-wording). **Impact:** none on the shipped contract.

## Issues Encountered

- `git commit` prints `failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit; both commits landed (verified with `git log`). Harmless, as the orchestrator warned.
- The five files are LF in the working tree (git warns that LF will become CRLF on next touch via autocrlf); edits kept LF. `transforms.py` and `worksharing.py` contain non-ASCII (an em dash) and were read and written as UTF-8.
- `graphify update .` was not run: it rewrites `graphify-out/`, which holds another session's uncommitted changes in this tree.
- REQUIREMENTS.md was not touched (the orchestrator owns requirement completion); no gsd-tools verb edited it. STATE.md and ROADMAP.md were updated through gsd-tools verbs and left uncommitted for the orchestrator.
- Behaviour changes worth knowing: (a) `create_view` where Revit returns no view used to hit `get_element_id_value(None)` after the commit and answer 500; it now answers 422 `failed` with item `view`. (b) `create_view` where the name is taken used to roll back into a 500 with the view lost; it now keeps the created view and answers 200 `partial` with failed step `name` (in real Revit the Name setter throws inside the transaction, so this is the reply shape only, confirmed live in 04-11).
- The outer `/execute_code/` 500 (an exception outside the exec handler after a transaction exists) is implemented but has no test: it is unreachable from the fake world without patching the module, since every exception inside the transaction block lands in the exec-error handler first.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface. T-04-18 (bare commits) mitigated and tested; T-04-19 mitigated and tested (`test_execute_code_outcome_never_carries_the_code_the_output_or_the_traceback`); T-04-20 (execute_code is arbitrary code) and T-04-21 (file paths in the open_model outcome) accepted as planned.

## Next Phase Readiness

Ready for 04-06 and 04-07. The view/code world is fully migrated and its `every_transacting` invariants cover the whole table. Live confirmation of the view name step, the transform and the open/execute outcomes is plan 04-11 (needs a full Revit restart, never pyRevit Reload).

## Self-Check: PASSED

- Files modified exist and are committed: revit_mcp/transforms.py, revit_mcp/view_management.py, revit_mcp/worksharing.py, revit_mcp/code_execution.py, tests/unit/test_routes_view_code_identity.py.
- Commits found: d7764af, af9b158 (`git log --grep "04-05"`); `git rev-list --count` from `plan_head_before` reports 2.
- Task acceptance criteria re-run: Task 1 AST gate clean, `-k "transform or create_view or set_active_view or every_transacting"` 82 passed, `-k "section_basis or millimetres"` 2 passed; Task 2 AST gate clean, `-k "open_model or execute_code"` 35 passed, conventions and registration 267 passed; full suite 4920 passed, 3 skipped.
- Plan verification: `git show --stat` of each commit lists only `files_modified` paths; no file deleted; `tests/unit/tool_manifest.txt` unchanged.
