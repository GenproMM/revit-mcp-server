---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 03
subsystem: api
tags: [outcome-schema, finalize_outcome, building, annotation, detail, transactions, test-world, ironpython]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "plan 04-01 outcome helpers (commit_and_report, finalize_outcome, build_outcome, exception_outcome) and the route pattern proven on tag_elements; plan 04-02 invariant-test pattern"
provides:
  - "create_line, create_surface, create_level, create_dimensions, tag_walls, create_detail_line commit only through commit_and_report and reply through finalize_outcome"
  - "Failed-item names: input index, 'INDEX.name' (level), 'INDEX.offset' (floor), 'line_style', 'dimension', wall id (tag_walls), element id (create_dimensions)"
  - "Repaired analysis/color fake world: commit_status, TransactionStatus, Transaction.GetStatus, hooks, attr_overrides, per-(category, kind) collector results, a .NET-style List"
  - "TRANSACTING table (6 rows) and three world-wide invariants for the analysis/annotation/building/detail routes; plan 04-07 adds the colour rows"
affects: [04-04, 04-05, 04-06, 04-07, phase-06-audit-log]

plan_head_before: 245cea6ad73f6c47eb17d21f30c10bebcf24e5eb
actuals:
  tokens: 13900   # chars/4 over the +/- lines of the realized diff (55569 chars); the plan estimated 80000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Local fail(idx, reason, item=None) closure: one reason text feeds both the legacy errors string and outcome.failed; item overrides the input index for a secondary step of a created element"
    - "Read labels and parse numbers before the Create call, so once an element exists nothing left in its branch can put it in both succeeded and failed"
    - "Collector fake answers by (category object, 'types' | 'instances') so one route's several collector queries each get their own results"

key-files:
  created: []
  modified:
    - revit_mcp/building.py
    - revit_mcp/annotation.py
    - revit_mcp/detail.py
    - tests/unit/test_routes_analysis_color_identity.py

key-decisions:
  - "A level that exists but cannot be named stays in succeeded and created; only the item 'INDEX.name' is failed, so the reply is a 200 partial (D-12). The legacy errors list still gets 'Level N: <reason>' (its old text)"
  - "create_dimensions counts every input element that adds no geometry reference as a failed item (found nothing, raised, or point-located), not only the ones that raised"
  - "A dimension call where Revit returns no dimension still commits (an empty transaction) and answers 422 with failed item 'dimension'; it is not rolled back as in 04-02's create_mep_system"
  - "The pre-transaction 500 'view is not a plan or detail view' in create_detail_line also carries an outcome (transaction_status null) so every 500 of this world has one"

patterns-established:
  - "Test arming for this world: arm(world, items) takes a list (default collector results) or a {(category name, kind): factories} dict; reach/run helpers reach a real success from a TRANSACTING row"

requirements-completed: [TRUTH-01, TRUTH-03, TRUTH-04]

coverage:
  - id: D1
    description: "The analysis/color fake world can host a migrated route: Commit returns world.commit_status, DB.TransactionStatus exists and agrees with it, GetStatus follows the transaction, and a rollback in the fake is a real 409"
    requirement: TRUTH-04
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_the_fake_world_reports_the_transaction_status_it_commits_with"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py -k every_transacting"
        status: pass
    human_judgment: false
  - id: D2
    description: "create_line, create_surface and create_level report every created and failed item: partial 200 for a mixed batch, 422 when nothing was made, 409 on rollback; level name and floor offset are failed steps beside a succeeded element"
    requirement: TRUTH-03
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py -k 'create_level or create_line or create_surface'"
        status: pass
    human_judgment: false
  - id: D3
    description: "tag_walls (attempted walls only, each skip a failed item), create_dimensions (per-element reference failures, 'dimension' step, 422) and create_detail_line ('line_style' step) report what they did"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py -k 'tag_walls or dimension or detail_line'"
        status: pass
    human_judgment: false
  - id: D4
    description: "Behaviour in a live Revit (real Transaction.GetStatus after Commit, real wall/floor/level creation, real NewDimension and NewDetailCurve results, real line-style sub-categories)"
    requirement: TRUTH-01
    verification: []
    human_judgment: true
    rationale: "Per D-10 this plan is verified in the fake-pyRevit world only; live confirmation needs a full Revit restart and is deferred to the phase's live recheck"

duration: 35 min
completed: 2026-10-23
---

# Phase 4 Plan 03: building, annotation and detail outcomes Summary

**Six more mutating routes (`create_line`, `create_surface`, `create_level`, `create_dimensions`, `tag_walls`, `create_detail_line`) now commit only through `commit_and_report` and answer through `finalize_outcome`: every created id and every failed input or step reaches the model, a mixed batch is a 200 partial, an all-failed one a 422 and a rollback a 409. The analysis/color fake world was repaired first so it can prove all of it.**

## Performance

- **Duration:** about 35 min (start time was not recorded at launch; estimated)
- **Completed:** 2026-10-23
- **Tasks:** 2 of 2
- **Files modified:** 4 (all in `files_modified`; none created)

## Accomplishments

- **World repair (Task 1):** `World` gained `commit_status`, `hooks`, `attr_overrides`, `transactions`, `collector_items`, `break_start`, `db`; the fake `Transaction` now tracks Uninitialized/Started/commit status/RolledBack with a real `GetStatus` and `HasEnded`; `db.TransactionStatus` and `db.BuiltInCategory` are assigned once so a comparison inside a route is stable. A test pins that `Commit()` and `TransactionStatus.Committed` agree. All 143 pre-existing tests in the file kept passing.
- **building.py (Task 1):** `requested = len(input list)`; created element ids go to `succeeded`; every legacy `errors` entry has a structured twin in `failed` (item = input index, reason without the "Element N: " or "Level N: " prefix, via a local `fail` closure that replaced all 22 `errors.append` sites). In `create_level` the name assignment is its own guarded step: a level that cannot be named is succeeded, in `created`, and `0.name` is failed. Inner "Transaction failed" 500s and outer 500s carry `exception_outcome`.
- **annotation.py and detail.py (Task 2):** `create_dimensions` requested 1; elements adding no reference become failed items; no dimension from Revit is a `dimension` failed step (422). `tag_walls` counts only walls it attempts; each skip is a failed item and keeps its legacy `skipped` twin. `create_detail_line` makes a missing or unappliable `line_style` a failed `line_style` step beside the created line; view name and line id are read only after the committed check.
- **Invariants:** `TRANSACTING` has 6 rows (create_line, create_surface, create_level, create_dimensions, tag_walls, create_detail_line); the three `test_every_transacting_*` tests run 18 cases (success agrees with `classify_outcome`, rollback is a 409 with nothing succeeded, a 500 names the real transaction status).
- Suite: 4807 passed baseline (04-02), now **4854 passed, 3 skipped**. `tests/unit/tool_manifest.txt` unchanged. AST gates print `AST_GATE clean` for building.py, annotation.py and detail.py. `colors.py` untouched (its two 200-error tests still pass; plan 04-07).

## Task Commits

1. **Task 1: create_line, create_surface, create_level outcomes and the repaired world (D-12)** - `9de644e` (feat)
2. **Task 2: create_dimensions, tag_walls, create_detail_line outcomes** - `5e9aded` (feat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED and GREEN committed together per task, not as separate commits**
- **Found during:** both tasks
- **Issue:** the plan's commit protocol requires `uv run pytest tests/unit` green before every commit, which a standalone RED commit would violate (same resolution as 04-01 and 04-02). Each task's RED was observed failing (22 tests in Task 1, 24 in Task 2) before the implementation and then made green before its single commit.
- **Commit:** 9de644e, 5e9aded

**2. [Rule 2 - Missing critical] A floor whose offset cannot be applied is a failed step, not a hidden one**
- **Found during:** Task 1 (`create_surface`)
- **Issue:** `Floor.Create` ran first, then `float(offset)` and `offset_param.Set(...)` could raise or be skipped silently (read-only or missing parameter), either losing the created floor from `created` or reporting success with the offset not applied. Same class of lie as the level name.
- **Fix:** offset is parsed before the create call; the floor is in `created` and `succeeded` right after `Floor.Create`; a missing/read-only parameter, a `Set()` that answers False, or an exception appends failed item `"INDEX.offset"` (legacy `errors` gets the same text). Test `test_a_floor_whose_offset_cannot_be_applied_...`.
- **Files modified:** revit_mcp/building.py, tests/unit/test_routes_analysis_color_identity.py
- **Commit:** 9de644e

**3. [Rule 1 - Bug] Type, level and number-parsing reads moved before each Create call**
- **Found during:** Task 1 (walls, beams, floors, roofs)
- **Issue:** `get_element_name(wall_type)` and `get_element_name(level)` were evaluated after the element existed; if one raised, the element would be both in Revit and in `errors`, and now in both `succeeded` and `failed`.
- **Fix:** the names are read before the create call, so after creation only the id read remains. No behaviour change on the success path.
- **Commit:** 9de644e

**4. [Rule 2 - Missing critical] create_dimensions counts every referenceless element as failed**
- **Found during:** Task 2
- **Issue:** the plan names only the path that "only logs a warning" (an exception), but an element for which no reference was found, or a point-located one, was dropped silently, which is exactly the TRUTH-01 gap the behaviour row ("one yields no reference") describes.
- **Fix:** any input element that adds nothing to the reference array is a failed item (`"no geometry reference found"` or `"no geometry reference: <error>"`); the 400 for fewer than two references stays unchanged and carries no outcome.
- **Commit:** 5e9aded

**5. [Plan wording] Collector fake answers per (category, kind), not one flat list**
- **Found during:** Task 2
- **Issue:** `tag_walls` asks four collector questions (wall tag types, walls, existing tags, all through `OfCategory`/`OfClass`/`WhereElementIsNotElementType`) and a single `collector_items` list would conflate them.
- **Fix:** the fake collector remembers the category object and kind and consults `world.results`, falling back to `collector_items`. `arm()` takes a list or a `{(category name, kind): factories}` dict. `db.BuiltInCategory` is a stable MagicMock so category objects compare by identity. The fake `System.Collections.Generic.List` became a list subclass with `Add` (the surface route calls `curve_loops.Add`).
- **Files modified:** tests/unit/test_routes_analysis_color_identity.py

**6. [Plan wording] The pre-transaction "not a plan or detail view" 500 of create_detail_line carries an outcome too**
- It is a 500, so D-14 applies; `transaction_status` is null because no transaction exists. Not a 4xx validation, so D-04 does not exempt it.

**Total deviations:** 6 (1 blocking-process, 2 missing-critical, 1 bug, 2 plan-wording). **Impact:** none on the shipped contract; all additive.

## Issues Encountered

- `git commit` prints `failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit; both commits landed (verified with `git log`). Harmless, as the orchestrator warned.
- The working-tree files of this plan are LF (git warns that LF will become CRLF on next touch via autocrlf); edits kept LF.
- `graphify update .` was not run: it rewrites `graphify-out/`, which holds another session's uncommitted changes in this tree.
- Behaviour change worth knowing: `create_surface` now reports a floor `offset` that Revit could not apply as a partial instead of a silent success; callers that passed `offset` to a floor type without the height-above-level parameter will see `failed: [{item: "N.offset"}]`.
- A dimension call that finds no dimension still commits an empty transaction (the plan keeps it a 422, not a rollback); if a rolled-back empty transaction is preferred, that is a one-line change like `create_mep_system` in 04-02.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface; `outcome.failed[].reason` is `str(exc)` or fixed route text and `build_outcome` copies only `item` and `reason`. T-04-10 (batch `errors` hidden behind success), T-04-11 (silently skipped walls, references, line style) and T-04-12 (a fake world with no TransactionStatus) are mitigated and tested.

## Next Phase Readiness

Ready for 04-04. `colors.py` shares this world and follows in 04-07: add its rows to `TRANSACTING` and `"outcome"` to its pinned keys in the same commit as the module change. The world now has `commit_status`, `TransactionStatus`, `GetStatus`, hooks, `attr_overrides` and category-aware collector results for it to build on.

## Self-Check: PASSED

- Files modified exist and are committed: revit_mcp/building.py, revit_mcp/annotation.py, revit_mcp/detail.py, tests/unit/test_routes_analysis_color_identity.py.
- Commits found: 9de644e, 5e9aded (`git log --grep "04-03"`); `git rev-list --count` from `plan_head_before` reports 2.
- Task acceptance criteria re-run: Task 1 AST gate clean, `-k "create_level or create_line or create_surface"` 65 passed, `-k color_failures_keep_their_http_200` 2 passed; Task 2 AST gate clean, `-k "tag_walls or dimension or detail_line"` 70 passed, `-k every_transacting` 18 passed (3 x 6 TRANSACTING rows); full suite 4854 passed, 3 skipped.
- Plan verification: `git show --stat` of each commit lists only `files_modified` paths; `tests/unit/tool_manifest.txt` unchanged.
