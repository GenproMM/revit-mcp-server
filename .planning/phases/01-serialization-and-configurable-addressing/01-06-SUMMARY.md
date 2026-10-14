---
phase: 01-serialization-and-configurable-addressing
plan: 06
subsystem: infra
tags: [asyncio, httpx, serialization, lock, d27-b, pyrevit]

requires:
  - phase: 01-serialization-and-configurable-addressing
    provides: "01-02 bridge.py lock and bounded wait; 01-03 status target; 01-04 bench evidence (cross-wired-read, cross-wired-mutation); 01-08 CONTEXT D-28..D-31"
provides:
  - "bridge.UNLOCKED_GET = frozenset({'status'}): the only lock exemption (GET /status/)"
  - "bridge._is_locked rewritten fail-safe; READ_ONLY_POST removed"
  - "bridge._serialized: one bounded-wait lock path shared by _revit_call and revit_image"
  - "revit_image(endpoint, ctx=None, timeout=60.0) now locked, with a bounded queue wait"
  - "Wording that no longer calls the queue holder a mutation"
  - "Tool-path tracer, classifier tests and an all-endpoint drift scan over tools/*.py"
affects: [01-07 docs, phase-2 per-target lock, verify-work]

plan_head_before: 294244cafd88240c5993afedcd18980685da867d
actuals:
  tokens: 6000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "One serialized coroutine (_serialized) takes a zero-argument send callable; every transport path goes through it"
    - "Fail-safe classifier: only an explicit allow-listed (GET, route key) pair skips the lock"
    - "Drift scan: regex over tools/*.py endpoints asserted against the classifier, with a size floor so it cannot pass vacuously"

key-files:
  created: []
  modified:
    - bridge.py
    - tests/unit/test_bridge_serialization.py

key-decisions:
  - "d27-b applied as narrowed by the user: every call from this process except GET /status/ takes the lock; /model_info/ stays locked because its overlap was never measured"
  - "A locked GET or image failure after sending returns Error: <reason> and never claims outcome UNKNOWN (a read changes nothing, D-13)"
  - "READ_ONLY_POST is deleted, not kept as a parallel path (assumption-delta decision: promote)"

requirements-completed: [SER-01, SER-02, SER-03, SER-04]

coverage:
  - id: D1
    description: "Lock coverage: _is_locked is False only for GET on route key status; UNLOCKED_GET is exactly {status}; READ_ONLY_POST removed; execute_code, open_model, save_document stay locked even if listed"
    requirement: "SER-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_unlocked_is_exactly_get_status"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_unlocked_never_unlocked_stay_locked_even_if_listed"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_unlocked_unknown_empty_and_prefix_routes_are_locked"
        status: pass
    human_judgment: false
  - id: D2
    description: "Through the tool layer, get_revit_status answers while a POST holds the lock and get_revit_model_info waits for it"
    requirement: "SER-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_d27b_tool_path_model_info_waits_status_does_not"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET reads, the five former D-08 POSTs and revit_image queue behind a held POST; every literal tools/*.py endpoint except GET /status/ is locked"
    requirement: "SER-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_unlocked_every_tool_endpoint_except_status_is_locked"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_image_waits_while_locked"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_get_read_waits_while_locked"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_former_allowlist_post_waits_while_locked"
        status: pass
    human_judgment: false
  - id: D4
    description: "Bounded wait, full budget from acquisition and arrival-order release hold for GET and image calls too; queue-busy and read-failure wording is honest"
    requirement: "SER-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_get_queue_bound_returns_not_sent"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_image_queue_bound_returns_not_sent"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_get_budget_not_shrunk_by_queue_wait"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_mixed_get_post_queue_in_arrival_order"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_get_post_send_failure_is_not_outcome_unknown"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_wait_message_does_not_name_the_holder_a_mutation"
        status: pass
    human_judgment: false
  - id: D5
    description: "On the fleet's pyRevit 6.5.5 overlapping requests cross-wire as measured on 6.5.3, and /model_info/ overlap behaviour is measured live before anyone unlocks it (backstop truths; neither was benched)"
    verification: []
    human_judgment: true
    rationale: "Needs a live Revit on pyRevit 6.5.5; unit tests cannot observe pyRevit's shared request handler"

duration: 4 min
completed: 2026-10-14
status: complete
---

# Phase 1 Plan 06: d27-b Lock Coverage Summary

**Every call this MCP server makes to Revit except GET /status/ now queues behind one lock through a single bounded-wait path (`_serialized`), covering GET reads, `/model_info/`, the former D-08 POST allowlist and `revit_image`.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-10-14T08:12:25Z
- **Completed:** 2026-10-14T08:16Z
- **Tasks:** 2 (tracer, then expansion), 4 commits (RED/GREEN per task)
- **Files modified:** 2

## Accomplishments

- Replaced the D-08 read-only POST allowlist (measured as `cross-wired-read` on the 01-04 bench) with `UNLOCKED_GET = frozenset({"status"})`; `_is_locked` is fail-safe: exact route-key match, `NEVER_UNLOCKED` first, unknown routes and methods lock.
- Extracted the lock-wait-send body into `_serialized(method, endpoint, ctx, timeout, send)`; `_revit_call` and `revit_image` both delegate to it. `revit_image` gained a `timeout` keyword (default 60 s, so `tools/view_tools.py` is unchanged).
- A read that fails after sending returns `Error: <reason>` and never says outcome UNKNOWN; only POST keeps the possibly-applied wording.
- `WAIT_MESSAGE` and the queue-busy text now say a previous call from this server holds the queue; the busy text still says NOT sent to Revit, nothing was sent and nothing was changed.
- Tracer `test_d27b_tool_path_model_info_waits_status_does_not` drives the real `bridge.revit_get` through `register_status_tools`. The drift scan covers more than 40 literal tool endpoints (it asserts that floor), so a future tool or a widened `UNLOCKED_GET` fails the suite.

## Task Commits

1. **Task 1: tool-path tracer + lock coverage** (TDD)
   - RED `ad7165d` (test): 10 new tests failed on the planned behavior (the lock-coverage and wait assertions); `test_status_passes_while_locked` and the GET send-failure test already held and guard the post-change behavior.
   - GREEN `fac859a` (feat): `UNLOCKED_GET`, rewritten `_is_locked`, GET failure wording, module docstring.
2. **Task 2: revit_image and every endpoint behind one serialized path** (TDD)
   - RED `0763770` (test): 4 failed (image waits, image `timeout` keyword TypeError, mixed arrival order, "mutation" in the wait message).
   - GREEN `0f4fb42` (feat): `_serialized`, locked `revit_image`, reworded messages.

**Plan metadata:** committed separately (docs: complete plan).

Tracer gate: Task 1's `<verify>` re-ran green end to end before Task 2 started (tracer verified, expansion allowed).

## Files Created/Modified

- `bridge.py` - lock coverage (`UNLOCKED_GET`, `_is_locked`), `_serialized`, locked `revit_image`, wording
- `tests/unit/test_bridge_serialization.py` - tracer, classifier tests, waits-while-locked tests, drift scan, `_FakeMCP`, `_image_handler`; seven `test_allowlist_*` tests and the allowlisted-reads-pass test removed; `test_get_reads_pass_while_locked` renamed `test_status_passes_while_locked` with its body unchanged

## Decisions Made

- Applied d27-b as the user narrowed it at the 01-04 gate. `/model_info/` stays locked until its overlap is measured live.
- Kept `NEVER_UNLOCKED` and checked it first, so a mistaken edit of `UNLOCKED_GET` still cannot unlock execute_code, open_model or save_document (T-01-26).
- Test-only helper `_image_handler` records `/get_view/` hits in `gate.seen` so the image path is observable in ordering tests.

## Deviations from Plan

None - plan executed exactly as written. Two tests listed as behavior for the new code (`test_get_post_send_failure_is_not_outcome_unknown` after Task 1 and `test_get_queue_bound_returns_not_sent` / `test_get_budget_not_shrunk_by_queue_wait` in Task 2) already passed at their RED step, because Task 1's GREEN had already locked GET calls and the unchanged path returned the right text. They are regression pins, not RED drivers; the other new tests in each RED commit failed for the intended reason.

**Total deviations:** 0

## Issues Encountered

- A heredoc-written test edit embedded a raw U+0089 character in a bytes literal (SyntaxError at collection); replaced with the `\x89` escape before the Task 2 RED commit. No effect on the committed history.
- `git commit` printed `failed to delete '.git/worktrees/hot-cirrus': Permission denied` on each commit; stale-worktree housekeeping noise, all four commits exist.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or file access; the change only narrows the set of calls that bypass the lock (T-01-10, T-01-26 mitigated; T-01-23 stays transferred to backlog 999.1; T-01-24 and T-01-25 stay accepted).

## Verification

- `uv run pytest tests/unit -q`: 408 passed, 3 skipped.
- `uv run pytest tests/unit/test_bridge_serialization.py -q`: 57 passed.
- `uv run pytest tests/unit/test_local_bridge_transport.py tests/unit/test_textutils.py -q`: 28 passed.
- `uv run python tests/test_init_latency.py`: `INIT_LATENCY_S=0.781` (below 2.0).
- `D27B_CLASSIFIER_OK` and `IMAGE_LOCKED_OK` acceptance one-liners printed.
- `git status --porcelain -- tools revit_mcp main.py deploy`: empty; only `bridge.py` and its test file changed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 01-07 can document the new lock coverage and the residual risks (T-01-23 cross-process overlap, T-01-24 abandoned-call overlap).
- Open for phase verification (human_needed): confirm on pyRevit 6.5.5 that overlap cross-wiring still occurs, and measure `/model_info/` overlap with `scripts/probe_handler_overlap.py` before anyone proposes unlocking it.
- Phase 2: the module-global lock must become one lock per `host:port` target once one server addresses several Revit instances (recorded in ROADMAP by plan 01-08).

## Self-Check: PASSED

- `bridge.py` and `tests/unit/test_bridge_serialization.py` exist; commits `ad7165d`, `fac859a`, `0763770`, `0f4fb42` found in `git log`.
- RED commits precede their GREEN commits (`test(01-06)` before `feat(01-06)` for both tasks).
- Task 1 and Task 2 acceptance criteria re-run: all pass.

---
*Phase: 01-serialization-and-configurable-addressing*
*Completed: 2026-10-14*
