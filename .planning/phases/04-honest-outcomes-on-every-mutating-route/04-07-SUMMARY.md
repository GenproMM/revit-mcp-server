---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 07
subsystem: api
tags: [outcome-schema, finalize_outcome, colors, transactions, test-world, ironpython]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "plan 04-01 outcome helpers (commit_and_report, finalize_outcome, exception_outcome); plan 04-03 repaired analysis/color fake world and TRANSACTING table"
provides:
  - "color_splash and clear_colors commit only through commit_and_report and answer with the status and HTTP code finalize_outcome chose"
  - "color_elements_by_parameter and clear_element_colors return (payload, http_status) on every path"
  - "Per-element override failures are outcome.failed entries {item: element id, reason: str(exc)}"
  - "TRANSACTING has 8 rows: all eight transacting routes of the analysis/color world are pinned to the outcome contract"
affects: [04-08, 04-09, 04-10, 04-11, phase-06-audit-log]

plan_head_before: 0fa3b652f26e655f19dc9357f963560b51f2f646
actuals:
  tokens: 3500    # chars/4 over the +/- lines of the realized diff (14038 chars); the plan estimated 70000
  tasks: 2
  commits: 1

tech-stack:
  added: []
  patterns:
    - "Module-level route function returns (payload, http_status); the route wrapper unpacks it and passes status= to make_response"
    - "Exception branch keeps its historic 200 error body and adds outcome via exception_outcome(t, requested, succeeded, failed)"
    - "Element id read inside the per-element try, before the API call, so the failed entry always has an item and the except handler cannot raise"

key-files:
  created: []
  modified:
    - revit_mcp/colors.py
    - tests/unit/test_routes_analysis_color_identity.py

key-decisions:
  - "The colour routes' exception path stays HTTP 200 with status 'error' (plan D-04/D-14); the world-wide 500 invariant test branches on module: colour rows expect 200 + status 'error' + outcome.transaction_status equal to the real transaction status, every other row still expects 500"
  - "requested for color_splash is the sum of group sizes (every element of every group is attempted), set before the transaction so a transaction that fails to start still reports requested"
  - "A partial colour run keeps the legacy message 'Successfully colored N elements ...' with N the real colored count; only a 409 drops it"

patterns-established:
  - "Colour test arming: ColourElement(ident, mark) with a String 'Mark' parameter, world.override_failures {id: exception} and world.overridden make SetElementOverrides failures reproducible; doc.Settings.Categories is iterable"

requirements-completed: [TRUTH-01, TRUTH-03, TRUTH-04]

coverage:
  - id: D1
    description: "color_splash reports every element it could not colour: 200 partial for a mixed run, 422 when every override fails, 409 on rollback with no 'Successfully colored' text; legacy statistics keep their meaning"
    requirement: TRUTH-03
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py -k color_splash"
        status: pass
    human_judgment: false
  - id: D2
    description: "clear_colors reports per-element outcomes the same way (partial, 422, 409), legacy elements_processed unchanged"
    requirement: TRUTH-04
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py -k clear_colors"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pre-existing 200 error/warning validation bodies and the exception body keep their status codes and keys; the exception body gains outcome"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py -k 'color_failures_keep_their_http_200 or validation_bodies or that_raises_keeps_its_200'"
        status: pass
    human_judgment: false
  - id: D4
    description: "All eight transacting routes of the analysis/color world agree with classify_outcome on success, answer 409 on rollback and carry the real transaction status on exception"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py -k every_transacting"
        status: pass
    human_judgment: false
  - id: D5
    description: "Behaviour in a live Revit (real Transaction.GetStatus after Commit, real View.SetElementOverrides failures)"
    requirement: TRUTH-01
    verification: []
    human_judgment: true
    rationale: "Per D-10 this plan is verified in the fake-pyRevit world only; live confirmation needs a full Revit restart and belongs to the phase's live recheck"

duration: 25 min
completed: 2026-10-23
---

# Phase 4 Plan 07: colour route outcomes Summary

**`color_splash` and `clear_colors` now commit only through `commit_and_report` and answer through `finalize_outcome`: an element whose override fails is a named `outcome.failed` entry (mixed run 200 partial, all failed 422), a rolled-back colour transaction is a 409 with `succeeded: []` and no "Successfully colored" text, and the historic 200 error/warning bodies are untouched.**

## Performance

- **Duration:** about 25 min (start time not recorded at launch; estimated)
- **Completed:** 2026-10-23
- **Tasks:** 2 of 2
- **Files modified:** 2 (both in `files_modified`; none created)

## Accomplishments

- **colors.py:** `color_elements_by_parameter` and `clear_element_colors` initialise `t`, `requested`, `succeeded`, `failed`; keep `swallower = suppress_warnings(t)` right after `t.Start()`; call `commit_and_report(t, swallower)` inside the `with DB.Transaction(...) as t` block; read the element id inside the per-element `try` and append it to `succeeded` after a successful active-view override or `{"item": id, "reason": str(e)}` to `failed`. The result dict no longer carries `status`; `finalize_outcome` adds it with `outcome` and the HTTP code. Validation branches return `(dict, 200)` unchanged (category not found, no elements: `error` for colour-splash, `warning` for clear); the exception branch returns its old dict plus `outcome = exception_outcome(t, requested, succeeded, failed)` with 200. `_color_splash` and `_clear_colors` unpack the pair and pass `status=http_status`.
- **Tests:** `TRANSACTING` gained `/color_splash/` and `/clear_colors/` (8 rows), so `-k every_transacting` runs 24 cases. 14 new behaviour tests: partial, 422, success names every id, rollback 409 without claim text, exception body gains outcome, validation bodies carry no outcome, for each route. World additions: `override_failures`/`overridden`, `FakeView.SetElementOverrides`, an iterable `doc.Settings.Categories` with a "Walls" category, `ColourElement` with a String "Mark" parameter, `DB.StorageType`.
- **Gates:** AST gate prints `AST_GATE clean` for colors.py (no bare `Commit`, no discarded `suppress_warnings`, no `**` dict splat). Suite: 4854 passed (04-03) now **4988 passed, 3 skipped**. `tests/unit/tool_manifest.txt` unchanged. Nothing else in `revit_mcp/` or `tools/` called the two functions whose return type changed (checked by grep).

## Task Commits

Both tasks landed in one commit (see Deviations):

1. **Tasks 1 and 2: color_splash and clear_colors outcomes, world-wide invariants over both colour routes** - `f9fb577` (feat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] One commit for both tasks, RED and GREEN together**
- **Found during:** both tasks
- **Issue:** the plan requires `uv run pytest tests/unit` green before every commit (a standalone RED commit would violate it, same resolution as 04-01..04-03), and both tasks edit the same two files and the same shared test arming (the TRANSACTING table, the world, the 500 invariant), so a clean Task 1 / Task 2 split would have needed a fabricated intermediate state.
- **Fix:** RED observed first (16 tests failing for the missing `outcome`, the world itself behaving: the two validation-body tests were already green), GREEN for both routes, one commit.
- **Commit:** f9fb577

**2. [Plan wording] The world-wide 500 invariant cannot apply to the colour rows as written**
- **Found during:** Task 1 (RED)
- **Issue:** `test_every_transacting_500_carries_the_real_transaction_status` asserts HTTP 500, but the plan (and `test_color_failures_keep_their_http_200_error_body_and_gain_the_identity`) fix the colour exception contract as HTTP 200 with status "error".
- **Fix:** the test branches on `key[0] == "colors"`: 200, status "error", and the same `outcome.transaction_status == world.transactions[-1].status` and `succeeded == []` checks as every other row. No assertion was weakened for the other six rows; the 200-error test is unchanged and passes.
- **Commit:** f9fb577

**3. [Plan wording] "no elements" status differs per route**
- The plan lists the no-elements body as a 200 "warning" for both routes; in the code it is "error" for `color_splash` and "warning" for `clear_colors`. Both are kept exactly as they were and each is pinned by its own test.

**4. [Rule 1 - Bug] The per-element except handler could raise**
- **Found during:** Task 1
- **Issue:** the old handler called `get_element_id_value(element)` inside `except`; if that read was what failed, the handler raised out of the loop and the whole call became a 200 "error" with the colored elements already overridden in the transaction.
- **Fix:** the id is read once inside the `try` before the API call and the handler reuses it (item may be `None` if the id itself cannot be read).
- **Commit:** f9fb577

**Total deviations:** 4 (1 blocking-process, 2 plan-wording, 1 bug). **Impact:** none on the shipped contract; all additive.

## Issues Encountered

- `git commit` printed `failed to delete '.git/worktrees/hot-cirrus': Permission denied`; the commit landed (verified with `git log -1`). Harmless, as the orchestrator warned.
- The working-tree files are LF (git warns LF will become CRLF on next touch); edits kept LF.
- `graphify update .` was not run (it rewrites `graphify-out/`, which holds another session's uncommitted changes).
- REQUIREMENTS.md was not touched (orchestrator owns requirement completion at phase end; TRUTH-01/03/04 are still declared by sibling plans). STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted for the orchestrator.
- Behaviour change worth knowing: a partial colour run still says "Successfully colored N elements in M color groups" in `message` (N is the real count); the partial status, the HTTP 200 and `outcome.failed` carry the failures. A colour run that fails every element now answers HTTP 422 instead of a 200 "success" with 0 colored.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface. T-04-26 (override failures only logged) and T-04-27 (rolled-back colour transaction reported as success) are mitigated and tested; T-04-28 is covered by the 04-01 renderer cap.

## Next Phase Readiness

Ready for 04-08. The analysis/color world is complete: 8 TRANSACTING rows, every transacting route committed through `commit_and_report`.

## Self-Check: PASSED

- Files modified exist and are committed: revit_mcp/colors.py, tests/unit/test_routes_analysis_color_identity.py.
- Commit found: f9fb577 (`git log --grep "04-07"`); `git rev-list --count` from `plan_head_before` reports 1.
- Task acceptance criteria re-run: AST gate `AST_GATE clean`; `-k "color_failures_keep_their_http_200 or never_reach_a_style"` 4 passed; `-k color_splash` 26 passed; `-k every_transacting` 24 passed (3 x 8 TRANSACTING rows); full suite 4988 passed, 3 skipped.
- Plan verification: `git show --stat` lists only the two `files_modified` paths; `tests/unit/tool_manifest.txt` unchanged.
