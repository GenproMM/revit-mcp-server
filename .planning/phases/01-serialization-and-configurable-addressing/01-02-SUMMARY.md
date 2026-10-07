---
phase: 01-serialization-and-configurable-addressing
plan: 02
subsystem: transport
tags: [asyncio, httpx, serialization, queue-bound, allowlist, error-wording]

requires:
  - phase: 01-01
    provides: "bridge.py with the module-global mutation lock and the three injected callables"
provides:
  - "Bounded queue wait: a queued POST keeps its full own timeout; an over-long wait returns an Error string saying NOT sent to Revit"
  - "Honest failure wording: 'was not sent to Revit' (pre-send) vs 'outcome UNKNOWN ... may have been applied ... Verify' (post-send)"
  - "READ_ONLY_POST allowlist (five routes) and NEVER_UNLOCKED set; fail-safe _is_locked classifier"
  - "Single best-effort ctx.info wait message (WAIT_MESSAGE)"
affects: [01-03, 01-04, 01-05]

actuals:
  tokens: 9000
  tasks: 3
  commits: 3
plan_head_before: afa874da3c28ac4841496de64cacdbeccd16bd4a

tech-stack:
  added: []
  patterns:
    - "asyncio.timeout(timeout) as budget around lock acquisition only; budget.reschedule(None) the moment the lock is held"
    - "Failure classification by httpx exception class: _NOT_SENT_ERRORS vs every other TransportError"
    - "Fail-safe allowlist with a never-unlock set checked first and a drift scan over tools/*.py"

key-files:
  created: []
  modified:
    - bridge.py
    - tests/unit/test_bridge_serialization.py

key-decisions:
  - "Anything that is not provably pre-send is reported as outcome UNKNOWN, never as not applied"
  - "TimeoutError that is not our wait bound returns 'Error: TimeoutError' rather than propagating (tools rely on the transport never raising)"
  - "_error_text falls back to the exception class name so no bridge error is a bare 'Error: '"

requirements-completed: [SER-02, SER-03, SER-04]

coverage:
  - id: D1
    description: "A queued POST is sent with exactly its own timeout (connect/read/write/pool); wait is not subtracted"
    requirement: "SER-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_budget_not_shrunk_by_queue_wait"
        status: pass
    human_judgment: false
  - id: D2
    description: "A wait exceeding the call's own bound returns an Error string with 'NOT sent to Revit' / 'nothing was sent' and never reaches the transport"
    requirement: "SER-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_queue_bound_returns_not_sent_without_sending"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_queue_bound_message_is_an_error_string"
        status: pass
    human_judgment: false
  - id: D3
    description: "The lock is released after handler exception, post-send timeout, holder cancel and waiter cancel; waiters are served FIFO"
    requirement: "SER-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_releases_after_handler_exception"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_releases_after_post_send_timeout"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_releases_after_cancellation_of_holder"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_releases_cancelled_waiter_is_never_sent"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_releases_queued_posts_in_arrival_order"
        status: pass
    human_judgment: false
  - id: D4
    description: "Pre-send failures say 'was not sent to Revit' and never UNKNOWN; post-send failures say 'outcome UNKNOWN'; no bare 'Error: '; one best-effort wait message"
    requirement: "SER-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_outcome_unknown_not_claimed_on_connect_error"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_outcome_unknown_error_text_never_empty"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_wait_message_once_when_queued"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_wait_message_failure_does_not_fail_call"
        status: pass
    human_judgment: false
  - id: D5
    description: "Exactly five read-only POST routes, plus GET and revit_image, are served while the lock is held; execute_code/open_model/save_document can never be unlocked; unknown POSTs are locked"
    requirement: "SER-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_allowlist_is_exactly_the_five_read_only_routes"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_allowlist_never_unlocked_routes_stay_locked_even_if_listed"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_allowlist_every_other_tool_post_is_locked"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_allowlisted_post_reads_pass_while_locked"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_image_reads_pass_while_locked"
        status: pass
    human_judgment: false
  - id: D6
    description: "Unlocked reads are not queued behind mutations by this server, but are not isolated from a mutation inside pyRevit's shared request handler"
    requirement: "SER-02"
    verification: []
    human_judgment: true
    rationale: "Unit tests cannot observe pyRevit's shared handler; measured live in plan 01-04 (D-23, D-27)"

duration: 3 min
completed: 2026-10-07
status: complete
---

# Phase 1 Plan 02: Bounded Queue Wait, Honest Failures, Read-Only Allowlist Summary

**Queued POSTs keep their whole own timeout, an over-long wait says "NOT sent to Revit", post-send failures say "outcome UNKNOWN", and five handler-verified read-only POSTs bypass the queue behind a fail-safe allowlist.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-10-07T06:49:36Z
- **Completed:** 2026-10-07T06:52:09Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- `_revit_call` bounds only the wait for the lock (`asyncio.timeout(timeout) as budget`, `budget.reschedule(None)` on acquisition) and then hands httpx the call's full timeout; worst case is about twice the call timeout (D-11).
- Queue-busy, pre-send and post-send failure strings are distinct, start with a letter after `Error: `, and `format_response` passes them through unchanged (T-01-06).
- Lock release on handler exception, post-send timeout, holder cancel, waiter cancel and bound expiry is covered; `CancelledError` is never caught in `bridge.py` (T-01-07).
- `READ_ONLY_POST` (5 routes) / `NEVER_UNLOCKED` (3 routes) / `_is_locked`; a drift test scans 38 literal `revit_post` endpoints in `tools/*.py` (T-01-08).
- Unit suite 385 passed, 3 skipped (was 361 after plan 01-01); `INIT_LATENCY_S=0.828` (< 2.0); `git status -- tools revit_mcp` empty.

## Task Commits

1. **Task 1: Bounded wait end-to-end (tracer)** - `4efd535` (feat)
2. **Task 2: Failure honesty, release on every exit, one wait message** - `071868e` (feat)
3. **Task 3: Read-only allowlist** - `9d2bb9c` (feat)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `bridge.py` - `_queue_busy_message`, `_NOT_SENT_ERRORS`, `WAIT_MESSAGE`, `_say`, `_error_text`, `_transport_failure_message`, `READ_ONLY_POST`, `NEVER_UNLOCKED`, `_route_key`, `_is_locked`, reworked `_revit_call`
- `tests/unit/test_bridge_serialization.py` - 25 new tests for SER-02/03/04, D-08, D-09, D-13, D-14; `_Gate` now also records the per-request timeout

## Decisions Made
- A transport error that is not provably pre-send is reported as outcome UNKNOWN, so the model never retries a maybe-applied mutation as if it had failed.
- A `TimeoutError` not caused by the wait bound returns `Error: TimeoutError` instead of propagating.

## Deviations from Plan

None - plan executed exactly as written. The tracer's RED was confirmed locally (2 of 3 Task 1 tests, 6 of 12 Task 2 tests, 8 of 10 Task 3 tests failing) before each implementation; each task landed as one `feat` commit, as in plan 01-01. One cosmetic touch: `_error_text` is annotated `Exception` rather than `BaseException` so the plan's "no `BaseException` in bridge.py" read-check is unambiguous.

## Issues Encountered
None

## Known Stubs
None.

## Threat Flags
None - no new network endpoint, auth path or schema surface; the allowlist and wording changes are the plan's own T-01-06..T-01-09 mitigations. T-01-10 (unlocked read inside pyRevit's shared handler) remains transferred to plan 01-04.

## Next Phase Readiness
- Plan 01-03 can add `mcp_target` on the status tool via `revit_get.revit_target`.
- The A7 instant (deadline firing between acquire and `reschedule(None)`) is not unit-reproducible and is covered only by the release-and-reacquire tests, as the plan records.

## Self-Check: PASSED
- bridge.py, tests/unit/test_bridge_serialization.py FOUND; commits 4efd535, 071868e, 9d2bb9c FOUND.
- `git rev-list --count afa874d..HEAD` = 3 at SUMMARY time; `git status --porcelain -- tools revit_mcp` empty.

---
*Phase: 01-serialization-and-configurable-addressing*
*Completed: 2026-10-07*
