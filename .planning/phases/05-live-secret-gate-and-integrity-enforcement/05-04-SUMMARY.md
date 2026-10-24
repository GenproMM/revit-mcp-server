---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 04
subsystem: security
tags: [shared-secret, integrity, gate, pyrevit-routes, ironpython3, tdd]

requires:
  - phase: 05-live-secret-gate-and-integrity-enforcement
    provides: revit_mcp/security.py (gate_or_response) and tests/unit/gate_support.py from 05-01
provides:
  - gated preamble on /create_duct/, /create_pipe/, /create_mep_system/, /set_parameter/, /create_room/, /create_room_separation/, /create_grid/, /create_framing/, /tag_elements/
  - parametrized 401/401/423 refusal rows over the mep/parameter suite's MUTATIONS table, asserting no event, no transaction, no parameter Set() and no guard call
affects: [05-05, 05-16]

plan_head_before: fec74277e257e7ad7cb60f9641c9571ad2d97d40
actuals:
  tokens: 5500
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Gate preamble copied verbatim from the 05-01..05-03 handlers: gate_refusal = gate_or_response(request) before the document guard, after the docstring"
    - "One _refused(world, key, request, status) helper asserts status, no outcome, no events, no transactions, world.sets == [], no guard call and no secret in the reply"

key-files:
  created: []
  modified:
    - revit_mcp/mep.py
    - revit_mcp/parameters.py
    - revit_mcp/rooms.py
    - revit_mcp/structure.py
    - revit_mcp/tags.py
    - tests/unit/test_routes_mep_parameter_identity.py

key-decisions:
  - "The suite's local request_of was replaced by gate_support.request_of and configure_gate(monkeypatch) runs in the world fixture; call() needed no change because the refusal rows pass request= through its **extra"
  - "The strict xfail marks for rooms, structure and tags lived only in the Task 1 commit and were removed in Task 2 (no xfail remains in the suite)"

patterns-established:
  - "Refusal rows reopen one document and clear world.events first, so a call that slipped past the gate would visibly reach the document guard, a transaction or a parameter Set()"

requirements-completed: [SEC-01, SEC-03, SEC-06, INTG-04]

duration: 12min
completed: 2026-10-24
status: complete
---

# Phase 5 Plan 04: Gate mep, parameters, rooms, structure and tags Summary

**Nine more mutations, including the only parameter-writing route (`/set_parameter/`), now open with the 05-01 gate and refuse 401 missing, 401 mismatch or 423 integrity mismatch before the document guard, any Revit object or any parameter `Set()`.**

## Performance

- **Duration:** about 12 min
- **Completed:** 2026-10-24
- **Tasks:** 2 (Task 1 tracer, Task 2 TDD)
- **Files:** 6 modified, none created

## Accomplishments

- `create_duct_handler`, `create_pipe_handler`, `create_mep_system_handler` (mep), `set_parameter_handler` (parameters), `create_room_handler`, `create_room_separation_handler` (rooms), `create_grid_handler`, `create_framing_handler` (structure) and `tag_elements_handler` (tags) open with `gate_refusal = gate_or_response(request)` as the first statement after the docstring, ahead of the document guard. `from .security import gate_or_response` is a relative import next to the `.identity` import. No line after a preamble was edited. The two GET reads of parameters (`/project_parameters/`, `/element_properties/`) are untouched and keep their signatures (SEC-05).
- The suite now sends enveloped requests. All 258 pre-existing rows passed unchanged with the envelope, including the 409 `rolled_back` of `set_parameter` and the Phase 4 `tag_elements` partial tracer.
- Three new tests over all 9 `MUTATIONS` keys (27 rows): no secret gives 401 `missing`, a wrong secret 401 `mismatch`, a valid secret with a verified mismatch 423 naming `revit_mcp/detail.py`. Each row asserts no `outcome` key, `world.events == []`, `world.transactions == []`, `world.sets == []`, `world.guard_calls == []`, and that neither secret occurs in the reply.

## Task Commits

1. **Task 1 (tracer): enveloped suite, gate mep and set_parameter, 27 refusal rows with rooms, structure and tags as strict xfail** - `df0cbcb` (feat)
2. **Task 2: gate rooms, structure and tags, drop the xfail marks** - `ce93e21` (feat)

Tracer feedback gate: auto mode, automated-only verify; the tracer verify (285 passed, 15 xfailed) and the full unit suite (5468 passed, 3 skipped, 15 xfailed) were re-run green after Task 1, so expansion proceeded (`Tracer verified end-to-end`).

## TDD Gate Compliance

Task 1: RED observed locally (12 failed for the four not-yet-gated routes x 3 tests, 15 strict xfailed) and committed together with GREEN as a tracer, as in 05-01..05-03. Task 2: RED observed locally (xfail marks removed, 15 failed), then GREEN (300 passed); committed as one change because the RED step is only the removal of the marks.

## Verification

- Task 1 acceptance: `-k "shared_secret or wrong_secret or integrity_mismatch"` 12 passed, 15 xfailed, 0 failed (needs at least 12); `uv run pytest tests/unit -q` 5468 passed, 3 skipped, 15 xfailed.
- Task 2 acceptance: same filter 27 passed, no xfailed, 0 failed (needs 27); `GATED_FIRST all` for all nine routes; `test_phase2_inventory.py` and `test_conventions.py` 937 passed, 3 skipped; no `xfail` left in the suite.
- Plan-level: `uv run pytest tests/unit -q` gives 5483 passed, 3 skipped (baseline 5456 passed, 3 skipped, plus 27 new rows).

## Deviations from Plan

None - plan executed exactly as written.

## D-06 findings

None. No pre-existing row of this suite failed because of a present `_mcp` key.

## Known Stubs

None.

## Threat Flags

None. No endpoint, auth path or trust-boundary change beyond the plan's threat model (T-05-17 is covered by the 27 refusal rows with `world.events == []` and `world.sets == []`; T-05-18 by `world.guard_calls == []` on every refusal row).

## Issues Encountered

`git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit (stale linked worktree housekeeping, as in 05-01..05-03); the commits are unaffected. Line endings were preserved per file (CRLF working copies of mep, parameters, rooms, structure and the suite; LF for tags).

## Next Phase Readiness

Ready for 05-05 (remaining non-GET handlers) and 05-16 (bridge envelope and the `startup.py` `security.initialize` call). `bridge.py` and `startup.py` are untouched, so live use waits for those plans.

## Self-Check: PASSED

- Modified files exist: revit_mcp/mep.py, parameters.py, rooms.py, structure.py, tags.py, tests/unit/test_routes_mep_parameter_identity.py.
- Commits found: df0cbcb, ce93e21 (`git rev-list --count fec7427..HEAD` is 2).
- All acceptance criteria re-run green; full unit suite 5483 passed, 3 skipped.
