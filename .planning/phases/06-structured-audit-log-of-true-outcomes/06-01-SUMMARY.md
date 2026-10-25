---
phase: 06-structured-audit-log-of-true-outcomes
plan: 01
subsystem: audit
tags: [audit, jsonl, logging, queuehandler, contextvars, fastmcp, bridge, provenance]

requires:
  - phase: 02-process-identity
    provides: bridge provenance (kind, process, http_status, corroborated) on every result
  - phase: 04-truthful-outcomes
    provides: reply status values success/partial/failed/rolled_back
provides:
  - audit.py (CPython-only, stdlib-only at import): call state contextvar, install_audited_tools(mcp), pure build_entry, serialize_entry with secret redaction, queue-backed roll-forward JSONL writer
  - bridge._dispatch audit hook (_audit around the unchanged _dispatch_core) and the audit_call_id provenance key
  - injected optional user_request parameter on every registered tool
  - 'Audit: call_id <id>' as the last line of a mutation or non-success reply
  - payload copy line for audit.py and a transitive payload test
affects: [06-02, 06-03, 06-04, 06-05, 06-06, 06-07, phase-07]

plan_head_before: 39b10c54f909db98f56f460c2a06b03bfd923ccd
actuals:
  tokens: 10000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Wrapper of mcp.tool installed from main.py (not register_tools) so unwrapped-signature tests keep passing"
    - "Audit hook around the unchanged bridge core (_dispatch -> _dispatch_core), never-raise _audit"
    - "Roll-forward BaseRotatingHandler (no rename) behind a bounded QueueHandler/QueueListener"
    - "Lazy writer: no directory, thread or file until the first entry"

key-files:
  created:
    - audit.py
    - tests/unit/audit_support.py
    - tests/unit/test_audit_tracer.py
  modified:
    - bridge.py
    - main.py
    - tools/utils.py
    - tests/unit/conftest.py
    - tests/unit/test_identity_rendering.py
    - tests/unit/test_payload_ships_root_modules.py
    - deploy/build-payload.cmd

key-decisions:
  - "Outcome label is the reply's top-level status (success/partial/failed/rolled_back), never outcome.status (does not exist), never format_response"
  - "A not-sent call writes no entry and carries no Audit line; the Audit line appears only when an entry was written and the call was a mutation or did not succeed"
  - "build-payload.cmd copy line went into the Task 1 commit so every commit keeps the payload test green"

patterns-established:
  - "audit.record_call is the storage seam: the bridge never touches files"
  - "Test isolation: autouse _isolated_audit_log points REVIT_MCP_AUDIT_DIR under a session temp base and resets the writer around every test"

requirements-completed: [AUDIT-01, AUDIT-04, AUDIT-05]

coverage:
  - id: D1
    description: "One audited tool call through the production bridge writes exactly one schema-1 JSONL line (call_id uuid4, tool, route, method, mutation, kind, http_status, outcome, verified process) and the reply ends with 'Audit: call_id <same id>'"
    requirement: "AUDIT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_tracer.py#test_mutation_writes_one_entry_and_the_reply_names_its_call_id"
        status: pass
    human_judgment: false
  - id: D2
    description: "Identical back-to-back calls give two entries with distinct call_ids; a bridge call outside any tool gets its own call_id with tool null"
    requirement: "AUDIT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_tracer.py#test_identical_calls_make_two_entries_with_two_call_ids"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_tracer.py#test_a_bridge_call_outside_any_tool_gets_its_own_call_id"
        status: pass
    human_judgment: false
  - id: D3
    description: "A successful read is logged without an Audit line; a call refused before sending (not-sent) writes nothing"
    requirement: "AUDIT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_tracer.py#test_successful_read_is_logged_but_the_reply_has_no_audit_line"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_tracer.py#test_a_call_refused_before_sending_writes_nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "The wrapper adds an optional user_request to every tool schema, keeps ctx out of the schema yet passes it to the function; all 59 manifest tools register with tools.FAILED empty"
    requirement: "AUDIT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_tracer.py#test_wrapper_injects_user_request_and_keeps_ctx"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_tracer.py#test_every_manifest_tool_registers_through_the_wrapper"
        status: pass
    human_judgment: false
  - id: D5
    description: "Importing audit and bridge creates no directory, thread or file and prints nothing; stdio cold start stays under 2.0 s (0.776 s)"
    requirement: "AUDIT-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_tracer.py#test_importing_audit_and_bridge_creates_nothing"
        status: pass
      - kind: other
        ref: "uv run python tests/test_init_latency.py -> INIT_LATENCY_S=0.776"
        status: pass
    human_judgment: false
  - id: D6
    description: "The payload copies audit.py and the payload test follows repo-root imports transitively"
    requirement: "AUDIT-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_payload_ships_root_modules.py#test_payload_copies_every_root_module_reachable_from_main"
        status: pass
    human_judgment: false
  - id: D7
    description: "The audit writer can never change or break a tool call (D-18): record_call and _audit swallow every failure"
    requirement: "AUDIT-05"
    verification: []
    human_judgment: true
    rationale: "Prohibition is verified by judgment in this plan; the dedicated never-breaks rows and stdout-purity checks arrive in 06-05"

duration: 8min
completed: 2026-10-25
status: complete
---

# Phase 6 Plan 01: Structured audit log tracer slice Summary

**One thin end-to-end audit slice: a FastMCP tool wrapper (contextvar call state plus injected optional `user_request`), a never-raise hook around the production bridge dispatch, and a lazy queue-backed roll-forward JSONL writer that leaves one honest schema-1 line per sent call and tells the model its `call_id` on every mutation.**

## Performance

- **Duration:** about 8 min
- **Started:** 2026-10-25T09:41Z (approximate, not captured at start)
- **Completed:** 2026-10-25T09:49:02Z
- **Tasks:** 2
- **Files modified:** 10 (3 created, 7 modified)

## Accomplishments

- `audit.py` (stdlib-only at import) with the call state, `install_audited_tools`, pure `build_entry`/`serialize_entry` (secret replaced raw and JSON-escaped on the finished line), `SegmentHandler` (roll-forward, never renames), lazy `_writer`, never-raising `record_call`, `flush`, `_reset`.
- `bridge._dispatch` is now a thin wrapper that times the call, reads the contextvar (or builds an anonymous call), delegates to the unchanged `_dispatch_core`, and hands the tagged result to `_audit`; provenance gains `audit_call_id` for mutations and non-successes.
- Every registered tool gains an optional `user_request` schema property through a wrapper installed in `main.py` before `register_tools`; `ctx` stays out of the schema and still reaches the function; all 59 manifest tools register with `tools.FAILED` empty.
- `format_response` ends a mutation or non-success reply with `Audit: call_id <id>`; a successful read and a not-sent refusal carry none and write nothing.
- Unit suite: 5892 passed, 3 skipped (baseline 5884 plus 8 new tracer rows); cold start `INIT_LATENCY_S=0.776`.

## Task Commits

1. **Task 1: End to end audited tool call (tracer)** - `7440870` (feat)
2. **Task 2: Ship the slice (payload copy line done in Task 1 commit; transitive payload test)** - `d4deff4` (test)

**Plan metadata:** committed separately as `docs(06-01)` (SUMMARY, STATE, ROADMAP, REQUIREMENTS).

## Files Created/Modified

- `audit.py` - entry builder, redaction, wrapper, writer (new)
- `tests/unit/audit_support.py` - Machine fake with canned replies, selector helper, entry reader (new)
- `tests/unit/test_audit_tracer.py` - 8 tracer rows (new)
- `bridge.py` - `_dispatch` wrapper, `_dispatch_core`, `_audit`, eager `import audit`, `import time`
- `main.py` - `audit.install_audited_tools(mcp)` before `register_tools` (CRLF kept)
- `tools/utils.py` - trailing `Audit: call_id` line and docstring bullet (CRLF kept)
- `tests/unit/conftest.py` - autouse `_isolated_audit_log` plus session base dir
- `tests/unit/test_identity_rendering.py` - mutation reply: Audit line is last, process line second to last
- `tests/unit/test_payload_ships_root_modules.py` - transitive walk, renamed test
- `deploy/build-payload.cmd` - `copy /y "%REPO%\audit.py"` after the bridge.py line

## Decisions Made

- Outcome label comes from the reply body's top-level `status` (the `outcome` block has no `status` key), falling back to HTTP status then to `success` only for a completed read; a mutation 200 with no status is `unrecognized`, never `success`.
- Not-sent: no entry, no Audit line (Open Question 2 resolved as the research recommended).
- The `build-payload.cmd` copy line was committed with Task 1 rather than Task 2, so no commit leaves the payload test red.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Existing rendering assertion expected the process line last**
- **Found during:** Task 1 (full-suite run)
- **Issue:** `test_identity_rendering.py::test_a_received_200_is_tagged_with_the_handshake_identity` asserted the last line of a mutation reply is the process line; the new Audit line is now last. This is the case the plan anticipated in Task 2.
- **Fix:** assert `lines[-2] == PROCESS_LINE_A` and `lines[-1].startswith("Audit: call_id ")`. No production special-casing, hook left on.
- **Files modified:** `tests/unit/test_identity_rendering.py` (only test file touched for this reason)
- **Verification:** `uv run pytest tests/unit -q` -> 5892 passed, 3 skipped
- **Committed in:** `7440870`

**2. [Rule 3 - Blocking] Payload copy line moved from Task 2 into the Task 1 commit**
- **Found during:** Task 1 (full-suite run)
- **Issue:** `main.py` now imports `audit`, so `test_payload_copies_every_root_module_main_imports` failed until `deploy/build-payload.cmd` copies it; the plan requires the suite green before every commit.
- **Fix:** added the one copy line (LF kept) in the Task 1 commit; Task 2 commit holds the transitive-walk test change.
- **Files modified:** `deploy/build-payload.cmd`
- **Committed in:** `7440870`

---

**Total deviations:** 2 auto-fixed (2 Rule 3, both ordering/assertion consequences the plan anticipated)
**Impact on plan:** None on behaviour; one assertion updated, one task boundary shifted by a single line.

## Issues Encountered

- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` (git housekeeping on a stale unrelated worktree entry); the commits succeeded. Not touched.
- Start time was not captured at executor start; duration is approximate.

## Known Stubs

None. Entry fields deferred to later plans (rejected_auth/integrity/document outcomes, outcome block fields, documents, args, user_request, redaction before truncation, retention) are planned in 06-02..06-05 and are not stubs in this plan's contract.

## Threat Flags

None. The only new surface is the local audit directory and the wrapper, both in the plan's threat model (T-06-01..T-06-07).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 06-02: `build_entry` outcome table and entry fields extend without changing shape; `OPEN_POST_READ_ROUTES` copy awaits its equality pin.
- Note for the next plans: the `Machine` fake and `read_entries` in `tests/unit/audit_support.py` are the shared harness; `Audit:` is now the last line of any real-bridge mutation reply, so exact-text assertions on such replies must account for it.

---
*Phase: 06-structured-audit-log-of-true-outcomes*
*Completed: 2026-10-25*

## Self-Check: PASSED

- Created files exist: audit.py, tests/unit/audit_support.py, tests/unit/test_audit_tracer.py (verified with `[ -f ]`).
- Commits found: 7440870, d4deff4 (`git log`).
- Acceptance criteria re-run: tracer 8 passed; `-k imports` passed; `_audit/_dispatch/_dispatch_core` present; audit.py `ALL_PRESENT`; audit.py imports contain none of mcp/pydantic/bridge/revit_mcp/httpx; `grep -c audit.py build-payload.cmd` = 1; `-k reachable_from_main` 1 passed; full unit suite 5892 passed 3 skipped; `INIT_LATENCY_S=0.776`.
