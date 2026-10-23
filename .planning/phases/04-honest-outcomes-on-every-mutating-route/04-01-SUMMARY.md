---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 01
subsystem: api
tags: [outcome-schema, classify_outcome, tag_elements, format_response, transactions, ironpython]
status: complete

requires:
  - phase: 02-document-identity-and-mutation-guard
    provides: guarded route handlers and the fake-pyRevit route worlds the tests run in
provides:
  - "Five pure outcome helpers in revit_mcp/textutils.py (classify_outcome, build_outcome, finalize_outcome, transaction_status_of, exception_outcome), re-exported by revit_mcp/utils.py"
  - "Reply schema: outcome block (transaction_status, requested, succeeded, failed[{item, reason}], revit_failures); status partial (200) and failed (422) beside success (200) and rolled_back (409)"
  - "format_response PARTIAL SUCCESS render branch (banner, Succeeded N of M, Failed item: reason lines, cap 100)"
  - "tag_elements migrated: commit through commit_and_report, outcome via finalize_outcome, 500 outcome via exception_outcome"
affects: [04-02, 04-03, 04-04, 04-05, 04-06, 04-07, phase-06-audit-log]

plan_head_before: 49ce0cadf39fbbd19f20f3b9356608468769f7f4
actuals:
  tokens: 8100   # chars/4 over the +/- lines of the realized diff (32404 chars); the plan estimated 85000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Route pattern: t=None/requested/succeeded/failed before the outer try; swallower = suppress_warnings(t); per-item succeeded/failed; commit_and_report then finalize_outcome; outer except adds exception_outcome"
    - "One reason text feeds both the legacy skipped entry and outcome.failed through a local skip(eid, reason) closure"

key-files:
  created: []
  modified:
    - revit_mcp/textutils.py
    - revit_mcp/utils.py
    - revit_mcp/tags.py
    - tools/utils.py
    - tests/unit/test_textutils.py
    - tests/unit/test_format_response.py
    - tests/unit/test_routes_mep_parameter_identity.py

key-decisions:
  - "Outcome schema is added alongside the legacy keys (tagged_count, tag_ids, skipped, message), never replacing them (D-03); on a 409 the legacy keys are dropped because they would name elements that no longer exist"
  - "classify_outcome is the single classifier: not committed is 409 rolled_back, committed with no failure is 200 success (including the empty call), mixed is 200 partial, all-failed is 422 failed (D-04)"
  - "Only a committed flag that is exactly True counts as committed in finalize_outcome; Pending and Error are 409 with the status string carried verbatim (Pitfall 5)"
  - "partial and rolled_back stay out of format_response's failure set; partial has its own render branch (D-08, D-09)"
  - "Phase 6 note: /activate_document/ is classified ACTIVATION, keeps its existing 200/422 verified-observation reply and deliberately carries NO outcome block. The Phase 6 audit reader must handle it explicitly by route name and must not expect outcome on every state-changing reply."
  - "No item_kind key in outcome: D-03 fixes five keys; the route name plus the item-convention table in 04-01-PLAN.md is how an item is interpreted"

patterns-established:
  - "Test-world arming: arm(world, items, missing=()) makes GetElement answer None for ids in missing and a taggable element otherwise; fake Transaction has a real GetStatus and a HasEnded that is true after Commit or RollBack"
  - "A committed-then-raised 500 is exercised by monkeypatching finalize_outcome in the loaded route module, because tag_elements touches no document member after its commit"

requirements-completed: [TRUTH-01, TRUTH-03, TRUTH-04]

coverage:
  - id: D1
    description: "A mixed valid/invalid tag_elements batch reaches the model as PARTIAL SUCCESS with the failing id and reason (tracer slice, route handler to format_response)"
    requirement: TRUTH-03
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_tag_elements_mixed_batch_reaches_the_model_as_a_partial_with_the_failing_id"
        status: pass
    human_judgment: false
  - id: D2
    description: "classify_outcome truth table and the build/finalize_outcome payload shapes (schema keys, order, duplicates, reason reduction, 409/422 shapes, data not mutated)"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_textutils.py -k 'outcome or classify or transaction_status'"
        status: pass
    human_judgment: false
  - id: D3
    description: "format_response partial branch: banner, counts, requested-null count, 100-line cap with a more line, partial kept out of the error set, 422 string passes verbatim"
    requirement: TRUTH-04
    verification:
      - kind: unit
        ref: "tests/unit/test_format_response.py -k 'partial or 422'"
        status: pass
    human_judgment: false
  - id: D4
    description: "tag_elements answers rollback as 409, all-failed as 422, keeps duplicate ids, and a 500 carries the real transaction status (Committed after a post-commit raise)"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py -k 'tag_elements and (rolled or 422 or duplicate or 500 or committed)'"
        status: pass
    human_judgment: false

duration: 25 min
completed: 2026-10-23
---

# Phase 4 Plan 01: Honest outcomes tracer (tag_elements) Summary

**One pure outcome contract (classifier, five-key schema, finalizer) in `revit_mcp/textutils.py`, proven end to end on `tag_elements`: a mixed batch is a 200 `partial` the model reads as `=== PARTIAL SUCCESS ===` with the failing id, a rollback is a 409, an all-failed batch is a 422, and a 500 names the real transaction status.**

## Performance

- **Duration:** about 25 min (start time was not recorded at launch; estimated)
- **Completed:** 2026-10-23
- **Tasks:** 3 of 3
- **Files modified:** 7 (all in `files_modified`; no files created)

## Accomplishments

- **Tracer slice (Task 1):** `tag_elements` commits only through `commit_and_report(t, swallower)`, builds `succeeded`/`failed` per item and replies through `finalize_outcome`. A test drives the real handler with ids `[5, 999999999]` and feeds the reply into `format_response`, which prints the PARTIAL SUCCESS banner, `Succeeded: 1 of 2` and the failing id with its reason.
- **Helper contract (Tasks 1 and 2):** `classify_outcome`, `build_outcome`, `finalize_outcome`, `transaction_status_of`, `exception_outcome`, all pure and at the Python 3.4 language level, re-exported from `revit_mcp/utils.py`. `commit_and_report` is untouched.
- **Renderer (Task 1, pinned in Task 2):** `_partial_lines` in `tools/utils.py`; the `has_error` expression and its failure set are unchanged (grep count 1).
- **Edge cases (Task 3):** rollback 409 with `outcome.succeeded == []` and no `tag_ids`; all-missing 422 with a truthy `error` that reaches the model as the bridge's `Error: 422 - ...` string; duplicate valid ids reported twice; 500 before Start reports `Uninitialized`, 500 after Commit reports `Committed` and keeps what was tagged.
- Suite: 4692 passed baseline, now **4741 passed, 3 skipped**. `tests/unit/tool_manifest.txt` unchanged.

## Task Commits

1. **Task 1 (tracer): partial batch end to end** - `8d788ed` (feat)
2. **Task 2: helper contract and renderer pinned** - `13b466b` (test)
3. **Task 3: rollback, all-failed, duplicates, 500 outcome** - `8ac3093` (feat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED and GREEN committed together per task, not as separate commits**
- **Found during:** Tasks 2 and 3
- **Issue:** the plan's commit protocol requires `uv run pytest tests/unit` green before every commit, which a standalone RED commit would violate. Each task's RED was observed failing (import error for the missing helpers in Task 2; the two outcome-on-500 tests in Task 3; the tracer test in Task 1) and then made green before its single commit.
- **Files modified:** none beyond the plan
- **Commit:** 13b466b, 8ac3093

**2. [Rule 1 - Bug, test double] Fake `Transaction.HasEnded` always returned False**
- **Found during:** Task 3 (committed-then-raised row)
- **Issue:** the route's inner `except` calls `RollBack()` when `HasStarted() and not HasEnded()`. With the fake's constant False a committed transaction was rolled back and its status flipped to `RolledBack`, which real Revit never does after Commit.
- **Fix:** `HasEnded` now returns true after Commit or RollBack. No existing test depended on the old behaviour.
- **Files modified:** tests/unit/test_routes_mep_parameter_identity.py
- **Commit:** 8ac3093

**3. [Plan option taken] Committed-then-raised row uses a monkeypatch, not a world flag**
- **Found during:** Task 3. `tag_elements` makes no document access after its commit, so a `world.explode_after_commit` flag had nothing to hit. The plan's stated fallback (monkeypatch `finalize_outcome` in the loaded `revit_mcp.tags` module) was used and the unused flag was removed.

**4. [Plan wording] FakeElement made taggable by default instead of a separate arming helper**
- The plan allowed extending `arm` or adding `arm_tagging`. `FakeElement` now carries a wall category and a point location, and `arm(world, items, missing=())` gained `missing`. `TRANSACTING`'s existing tag row therefore tags one element for real without a special case; the other four route modules' tests are unaffected (suite green).

**Total deviations:** 4 (1 blocking-process, 1 test-double bug, 2 plan-option choices). **Impact:** none on the shipped contract.

## Issues Encountered

- `git commit` prints `failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit; the commits landed (verified with `git log`). Harmless, as the orchestrator warned.
- `revit_mcp/textutils.py` and `tools/utils.py` have CRLF in the working tree (autocrlf, LF in the index); edits preserved each file's line endings.
- `graphify update .` was not run: it rewrites `graphify-out/`, which holds another session's uncommitted changes in this tree.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface; `outcome.failed[].reason` is `str(exc)` or fixed route text and `build_outcome` copies only `item` and `reason` (T-04-02 mitigated and tested).

## Next Phase Readiness

Ready for 04-02. Plans 04-02 through 04-07 import the five helpers from `.utils` and copy the route pattern in `04-01-PLAN.md`. Each must add `"outcome"` to its pinned key lists in the same commit as the module change (Pitfall 3) and must arm its route-world fake so success paths stay real (the analysis_color world still needs `commit_status` and a `TransactionStatus` namespace, per 04-PATTERNS).

## Self-Check: PASSED

- Files modified exist and are committed: revit_mcp/textutils.py, revit_mcp/utils.py, revit_mcp/tags.py, tools/utils.py, tests/unit/test_textutils.py, tests/unit/test_format_response.py, tests/unit/test_routes_mep_parameter_identity.py.
- Commits found: 8d788ed, 13b466b, 8ac3093 (`git log --grep "04-01"`).
- Task acceptance criteria re-run: tracer test `1 passed`; `AST_GATE clean`; classify one-liner prints `('rolled_back', 409) ('success', 200) ('partial', 200) ('failed', 422)`; test_conventions 0 failures; textutils outcome filter 35 passed; format_response partial/422 filter 7 passed; rolled_back pair 2 passed; failure-set grep prints 1; tag_elements rolled/422/duplicate/500/committed filter 5 passed; suppress_warnings filter 9 passed; full suite 4741 passed, 3 skipped.
- Plan verification: `git show --stat` over the three commits lists only `files_modified` paths.
