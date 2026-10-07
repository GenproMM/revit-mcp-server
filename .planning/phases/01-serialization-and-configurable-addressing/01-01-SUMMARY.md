---
phase: 01-serialization-and-configurable-addressing
plan: 01
subsystem: transport
tags: [asyncio, httpx, serialization, config, REVIT_PORT]

requires: []
provides:
  - "bridge.py: the single HTTP exit to pyRevit Routes (config, pooled client, mutation lock, revit_get/revit_post/revit_image)"
  - "Every POST through revit_post serialized by one module-global asyncio.Lock; GET bypasses it"
  - "REVIT_PORT deployment setting, strict parse, refuse-to-start (exit 2 on stderr)"
  - "revit_get.revit_target == REVIT_HOST:REVIT_PORT seam for get_revit_status (plan 01-03)"
affects: [01-02, 01-03, 01-04, 01-05]

actuals:
  tokens: 5000
  tasks: 2
  commits: 2
plan_head_before: ba4aedf7004ab2bcfdcbdadb777e2c573e3ff3e2

tech-stack:
  added: []
  patterns:
    - "Lazy module-global asyncio.Lock taken only via async with"
    - "Transport tests use httpx.MockTransport installed into bridge._http_client; autouse fixture resets lock and client per test"
    - "anyio_backend fixture pins asyncio (trio not installed)"

key-files:
  created:
    - bridge.py
    - tests/unit/test_bridge_serialization.py
  modified:
    - main.py
    - tests/unit/test_local_bridge_transport.py
    - tests/unit/test_textutils.py

key-decisions:
  - "Every POST is locked in this plan (fail-safe default); the read-only allowlist arrives in plan 01-02"
  - "Empty REVIT_PORT is refused, not defaulted (RESEARCH open question 3)"
  - "bridge.py imports mcp lazily inside revit_image so cold start stays cheap (D-19, D-24)"

requirements-completed: [SER-01, SER-02, IDENT-05]

coverage:
  - id: D1
    description: "Two concurrent mutating POSTs through revit_post never overlap on the wire; GETs pass while a POST holds the lock"
    requirement: "SER-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_second_post_waits_for_the_first"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_get_reads_pass_while_locked"
        status: pass
    human_judgment: false
  - id: D2
    description: "Transport moved out of main.py; bridge imports without fastmcp; injection contract and cold-start latency unchanged"
    requirement: "SER-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_main_delegates_transport_to_bridge"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_bridge_imports_without_fastmcp"
        status: pass
      - kind: integration
        ref: "uv run python tests/test_init_latency.py (INIT_LATENCY_S=0.885)"
        status: pass
    human_judgment: false
  - id: D3
    description: "REVIT_PORT selects the dialed URL; invalid, empty or out-of-range value makes the server exit 2 on stderr with empty stdout"
    requirement: "IDENT-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_port_accepts"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_port_refuses"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_port_reaches_base_url"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_port_refusal_writes_stderr_only"
        status: pass
    human_judgment: false

duration: 2 min
completed: 2026-10-07
status: complete
---

# Phase 1 Plan 01: Bridge Serialization and REVIT_PORT Summary

**Transport extracted into bridge.py with all POSTs serialized behind one module-global asyncio.Lock, plus a strictly parsed, refuse-to-start REVIT_PORT setting.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-10-07T06:46:16Z
- **Completed:** 2026-10-07T06:48:02Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- `bridge.py` is the single HTTP exit; `_revit_call` runs `_send` inside `async with _get_lock()` for POST and directly for GET.
- `main.py` is wiring only; the `register_tools(mcp, revit_get, revit_post, revit_image)` contract and every `tools/*_tools.py` are untouched.
- `REVIT_PORT` is resolved once at import via `_resolve_port`; bad values exit 2 with a stderr message, nothing on stdout; `48884` survives only as `DEFAULT_REVIT_PORT`.
- Unit suite 361 passed, 3 skipped (baseline 337); `INIT_LATENCY_S=0.885` (< 2.0).

## Task Commits

1. **Task 1: End-to-end serialized POST (tracer)** - `8ee9c75` (feat)
2. **Task 2: REVIT_PORT strict parse, refuse-to-start, target attribute** - `dad8ab6` (feat)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `bridge.py` - config, pooled client, lock, `_send`, `_revit_call`, the three injected callables
- `main.py` - FastMCP wiring and the refusal guard around the bridge import
- `tests/unit/test_bridge_serialization.py` - MockTransport lock tests and REVIT_PORT tests
- `tests/unit/test_local_bridge_transport.py`, `tests/unit/test_textutils.py` - source-text pins retargeted from main.py to bridge.py

## Decisions Made
- Every POST is locked for now (fail-safe default); plan 01-02 introduces the read-only allowlist.
- Empty `REVIT_PORT` is refused rather than defaulted.
- `mcp` is imported lazily inside `revit_image` and `ctx` is annotated `Any`, keeping `import bridge` free of `mcp.server.fastmcp`.

## Deviations from Plan

None - plan executed exactly as written. Note: the tracer's RED/GREEN cycle was run locally (RED confirmed for the port tests with 20 failures before implementation) but each task landed as a single feat commit rather than separate test/feat commits, matching the plan's per-task commit structure.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. `REVIT_PORT` is optional (default 48884).

## Next Phase Readiness
- Plan 01-02 can refine the error wording and add the read-only POST allowlist on top of `_revit_call`.
- Plan 01-03 can read `revit_get.revit_target` with `getattr`.

## Self-Check: PASSED
- bridge.py, tests/unit/test_bridge_serialization.py FOUND; commits 8ee9c75 and dad8ab6 FOUND.
- `git status --porcelain -- tools revit_mcp tests/unit/conftest.py` empty.

---
*Phase: 01-serialization-and-configurable-addressing*
*Completed: 2026-10-07*
