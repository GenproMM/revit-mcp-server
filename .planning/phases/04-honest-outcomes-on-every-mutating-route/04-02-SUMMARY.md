---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 02
subsystem: api
tags: [outcome-schema, finalize_outcome, mep, rooms, structure, set_parameter, transactions, ironpython]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "plan 04-01 outcome helpers (commit_and_report, finalize_outcome, build_outcome, exception_outcome, transaction_status_of) and the tag_elements reference migration"
provides:
  - "create_duct, create_pipe, create_mep_system, create_room, create_room_separation, create_grid, create_framing commit only through commit_and_report and reply through finalize_outcome"
  - "set_parameter success and 409 bodies carry outcome (item = parameter name); its literal 409 branch is untouched"
  - "D-12 failed steps: diameter, width, height, system_name, name, number, INDEX.name (grids), plus zero-length grid/beam and empty NewRoomBoundaryLines entries by input index"
  - "D-15: create_mep_system rolls back and answers 422 when Revit created no system"
  - "Three parametrised world-wide invariants over every TRANSACTING route (success agrees with classify_outcome, rollback is 409, 500 names the real transaction status)"
affects: [04-03, 04-04, 04-05, 04-06, 04-07, phase-06-audit-log]

plan_head_before: df5cdbe446ccd88b20f8de0c4083a2669223498a
actuals:
  tokens: 12700   # chars/4 over the +/- lines of the realized diff (50872 chars); the plan estimated 85000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "_set_step(failed, item, lookup, make_value): one guarded secondary Set() step that records 'parameter not found', 'parameter is read-only', 'Set() returned false' or str(exception) in outcome.failed"
    - "Read the created element's id while it is valid (before commit), build the legacy reply only after commit_result['committed']"
    - "Test-world attribute-override map (world.attr_overrides) for document members that must answer a configured object, e.g. doc.Create"

key-files:
  created: []
  modified:
    - revit_mcp/mep.py
    - revit_mcp/rooms.py
    - revit_mcp/structure.py
    - revit_mcp/parameters.py
    - tests/unit/test_routes_mep_parameter_identity.py

key-decisions:
  - "A secondary step counts as failed when the parameter is missing, read-only, raises on Set, or Set() answers False; the primary element stays in succeeded so the reply is a 200 partial, never hidden"
  - "create_mep_system with no resulting system calls t.RollBack() and answers 422 with transaction_status RolledBack, instead of committing an empty transaction (D-15)"
  - "create_room never reads the room after a rolled-back commit: a not-committed result returns finalize_outcome's 409 before any Area/Name/Number lookup (Pitfall 2)"
  - "set_parameter keeps its hand-written 409 body (status=409 appears exactly once) and gains outcome through build_outcome; it is not routed through finalize_outcome"
  - "An unsupported parameter StorageType in set_parameter is rolled back and answered 400 rather than committing no write and reporting success"

patterns-established:
  - "Invariant tests parametrised over the TRANSACTING table catch any new route that skips the outcome contract"

requirements-completed: [TRUTH-01, TRUTH-03, TRUTH-04]

coverage:
  - id: D1
    description: "Duct, pipe and MEP-system replies report real transaction status, failed dimension/name steps as partial, an empty system as a rolled-back 422, and rollback as 409"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py -k 'duct or pipe or mep_system'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Room, separation-line, grid and beam replies list what was created and what failed by index or step, with partial and 422 where they apply; room is not read after a rollback"
    requirement: TRUTH-03
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py -k 'grid or framing or room'"
        status: pass
    human_judgment: false
  - id: D3
    description: "set_parameter carries the outcome schema without losing its literal 409 branch; unsupported StorageType is a 400 rollback"
    requirement: TRUTH-04
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_parameter_rollback_source_is_unchanged"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py -k set_parameter"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every transacting route of the mep/parameter world is pinned to the outcome invariant (success status agrees with classify_outcome, rollback 409, 500 carries the real transaction status)"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py -k 'every_transacting or parameter_rollback_source'"
        status: pass
    human_judgment: false
  - id: D5
    description: "Behaviour in a live Revit (real Transaction.GetStatus after Commit, real Parameter.Set results, real NewMechanicalSystem returning null)"
    requirement: TRUTH-01
    verification: []
    human_judgment: true
    rationale: "Per D-10 this plan is verified in the fake-pyRevit world only; live confirmation needs a full Revit restart and is deferred to the phase's live recheck"

duration: 30 min
completed: 2026-10-23
---

# Phase 4 Plan 02: mep, rooms, structure and set_parameter outcomes Summary

**Seven more mutating routes now commit only through `commit_and_report` and answer through `finalize_outcome` (real transaction status, created ids, failed items with reasons, partial/422/409), `set_parameter` gains `outcome` beside its untouched 409, and three parametrised invariants pin every transacting route of the world to the contract.**

## Performance

- **Duration:** about 30 min (start time was not recorded at launch; estimated)
- **Completed:** 2026-10-23
- **Tasks:** 3 of 3
- **Files modified:** 5 (all in `files_modified`; none created)

## Accomplishments

- **Task 1, mep.py:** `_create_duct`, `_create_pipe`, `_create_mep_system` migrated. Dimensions (`diameter`, `width`, `height`) and `system_name` are guarded `_set_step`s. `create_mep_system` rolls back and answers 422 (`outcome.failed [{item: "system", reason}]`, `RolledBack`) when no system results; the "all connectors assigned" 500 keeps its status and gains `exception_outcome`. The created element's id is read before commit and the legacy keys are built only when committed.
- **Task 2, rooms.py and structure.py:** `create_grid` reports zero-length grids by input index and a failed grid-name assignment as `"INDEX.name"`; `create_framing` reports zero-length beams by index; `create_room` runs name and number as guarded steps and reads area/name/number only after a committed commit; `create_room_separation` lists created line ids and, when Revit returns nothing, fails every input index (422).
- **Task 3, parameters.py:** `set_parameter` success body carries `outcome` with `succeeded: [parameter_name]`; the literal 409 branch (exactly one `status=409`) carries `outcome` with `succeeded: []`; the 500 reply carries `exception_outcome`; a StorageType matching none of the four branches now rolls back and answers 400.
- **Tests:** the fake world gained `attr_overrides` (consulted by `RouteDocument.__getattr__` before `hooks`) and a `transactions` list; `arm()` now arms `doc.Create` to return two separation lines so the `create_room_separation` TRANSACTING row stays a real 200 success. `EXPECTED_KEYS` gained `"outcome"` for all eight migrated rows in the same commits as their modules.
- Suite: 4741 passed baseline (04-01), now **4807 passed, 3 skipped**. `tests/unit/tool_manifest.txt` unchanged. AST gates print `AST_GATE clean` for mep.py, rooms.py, structure.py, parameters.py.

## Task Commits

1. **Task 1: duct, pipe, MEP system outcomes (D-12, D-14, D-15)** - `b1b4e5d` (feat)
2. **Task 2: room, separation line, grid, beam outcomes (D-12, TRUTH-03)** - `9c2c081` (feat)
3. **Task 3: set_parameter outcome and the world-wide invariants (D-03, D-04, D-14)** - `d232877` (feat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED and GREEN committed together per task, not as separate commits**
- **Found during:** all three tasks
- **Issue:** the plan's commit protocol requires `uv run pytest tests/unit` green before every commit, which a standalone RED commit would violate (same resolution as 04-01). Each task's RED was observed failing (19, 16 and 7 failing tests respectively) before the implementation and then made green before its single commit.
- **Commit:** b1b4e5d, 9c2c081, d232877

**2. [Rule 2 - Missing critical] A `Set()` that answers False is also a failed step**
- **Found during:** Task 1
- **Issue:** the plan names "missing, read-only or raises on Set"; Revit's `Parameter.Set` also reports failure by returning False, which would have been silently counted as success.
- **Fix:** `_set_step` records `"Set() returned false"` in that case (`is False`, so a truthy mock or `None` is not misread). Applied in `mep.py` and `rooms.py`.
- **Files modified:** revit_mcp/mep.py, revit_mcp/rooms.py
- **Commit:** b1b4e5d, 9c2c081

**3. [Plan option taken] `_set_step` is duplicated in mep.py and rooms.py**
- Domain modules must not import each other and the plan forbids editing `utils.py`/`textutils.py` here, so each module carries its own 15-line copy. A later plan may hoist it into `revit_mcp/utils.py` if more modules need it.

**4. [Plan wording] The two `system_name` writes in `create_mep_system` became one step per branch**
- The old code wrote the name in the rename branch (with a Comments fallback) and again unconditionally after it. Each branch now runs exactly one `system_name` step (rename branch keeps the Comments fallback; new-system branch uses System Name only), so the behaviour is preserved and a failure is reported once. A test asserts the name is written once.

**Total deviations:** 4 (1 blocking-process, 1 missing-critical, 2 plan-option choices). **Impact:** none on the shipped contract.

## Issues Encountered

- `git commit` prints `failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit; all three commits landed (verified with `git log`). Harmless, as the orchestrator warned.
- The five touched files have CRLF in the working tree (autocrlf, LF in the index); every edit preserved CRLF line endings.
- `graphify update .` was not run: it rewrites `graphify-out/`, which holds another session's uncommitted changes in this tree.
- Behaviour change worth knowing: a non-numeric `diameter`/`width`/`height` used to raise inside the transaction (whole call rolled back, 500). `float()` now sits inside the guarded step, so the duct or pipe is created and the reply is a 200 partial naming the step. This follows the plan's "or an exception" rule; moving it to pre-transaction 400 validation would be a separate decision.
- A short `NewRoomBoundaryLines` result (fewer lines than requested, not none) cannot be attributed to input indices and is reported as success with the lines Revit returned; only the empty result fails every index.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface; `outcome.failed[].reason` is `str(exc)` or fixed route text and `build_outcome` copies only `item` and `reason`. T-04-06 (empty MEP system commit), T-04-07 (silent dimension/name skips) and T-04-08 (reads after a rolled-back commit) are mitigated and tested.

## Next Phase Readiness

Ready for 04-03. The route pattern, `_set_step`, the `attr_overrides` test hook and the TRANSACTING invariants are in place; later plans that add rows to `TRANSACTING` get the three invariants for free, and must add `"outcome"` to `EXPECTED_KEYS` in the same commit as the module change.

## Self-Check: PASSED

- Files modified exist and are committed: revit_mcp/mep.py, revit_mcp/rooms.py, revit_mcp/structure.py, revit_mcp/parameters.py, tests/unit/test_routes_mep_parameter_identity.py.
- Commits found: b1b4e5d, 9c2c081, d232877 (`git log --grep "04-02"`); `git rev-list --count` from `plan_head_before` reports 3.
- Task acceptance criteria re-run: Task 1 AST gate clean, `-k "duct or pipe or mep_system"` 80 passed, `-k "mep_system and 422"` 1 passed; Task 2 AST gate clean, `-k "grid or framing or room"` 99 passed, `-k "millimetres or level_elevation"` 2 passed; Task 3 `status=409` count and pattern print `1 True`, AST gate clean, `-k "every_transacting or parameter_rollback_source"` 28 passed (3 x 9 TRANSACTING rows + 1 source pin); full suite 4807 passed, 3 skipped.
- Plan verification: `git show --stat` of the three commits lists only `files_modified` paths; `tests/unit/tool_manifest.txt` unchanged.
