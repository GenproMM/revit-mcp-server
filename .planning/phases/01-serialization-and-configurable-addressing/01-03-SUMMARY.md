---
phase: 01-serialization-and-configurable-addressing
plan: 03
subsystem: transport
tags: [status, REVIT_PORT, two-entry, payload, deploy, bridge]

requires:
  - phase: 01-01
    provides: "revit_get.revit_target seam and bridge.py root module"
provides:
  - "get_revit_status ends with 'MCP target: host:port' in every outcome (dict, message payload, Error string)"
  - "tests/test_two_instance_targets.py: older-tier harness driving two stdio entries with different REVIT_PORT (ENTRY / LISTENERS / TWO_INSTANCE_OK / TWO_INSTANCE_FAIL)"
  - "deploy/build-payload.cmd copies bridge.py; unit guard that every root module main.py imports is copied"
  - "start_revit docstring true for a second-port entry"
affects: [01-04, 01-05]

actuals:
  tokens: 4500
  tasks: 2
  commits: 2
plan_head_before: 4734857c2403ba4255b75ec1e7d6360a7e8e5990

tech-stack:
  added: []
  patterns:
    - "Tool modules read transport facts off the injected callable (getattr(revit_get, 'revit_target', None)), never import it"
    - "Target line appended after format_response so it survives message-reduction and error strings"
    - "Payload copy-list guard: ast-parse main.py imports vs copy lines in build-payload.cmd"

key-files:
  created:
    - tests/unit/test_status_target.py
    - tests/test_two_instance_targets.py
    - tests/unit/test_payload_ships_root_modules.py
  modified:
    - tools/status_tools.py
    - tools/process_tools.py
    - deploy/build-payload.cmd
    - pyproject.toml

key-decisions:
  - "Target line is appended after format_response, not through it, so format_response's error/message rules stay untouched"
  - "No target line when the injected callable has no revit_target, keeping bare-fake tests byte-identical"
  - "Staged local gate run replaces running build-payload.cmd, which publishes to the fleet share"

requirements-completed: [IDENT-05]

coverage:
  - id: D1
    description: "get_revit_status names the configured MCP target for dict, message-payload and Error-string responses, and is unchanged without the attribute"
    requirement: "IDENT-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_status_target.py#test_status_reports_target_for_dict"
        status: pass
      - kind: unit
        ref: "tests/unit/test_status_target.py#test_status_reports_target_for_error_string"
        status: pass
      - kind: unit
        ref: "tests/unit/test_status_target.py#test_status_reports_target_when_payload_has_message"
        status: pass
      - kind: unit
        ref: "tests/unit/test_status_target.py#test_status_unchanged_without_target_attribute"
        status: pass
      - kind: unit
        ref: "tests/unit/test_status_target.py#test_status_keeps_endpoint_and_short_timeout"
        status: pass
    human_judgment: false
  - id: D2
    description: "Two stdio server processes with REVIT_PORT 48997 / 48998 each report their own target in connection-error output; harness exits 1 with TWO_INSTANCE_FAIL offline"
    requirement: "IDENT-05"
    verification:
      - kind: integration
        ref: "uv run python tests/test_two_instance_targets.py --ports 48997,48998 (rc=1, both target= lines, TWO_INSTANCE_FAIL)"
        status: pass
    human_judgment: false
  - id: D3
    description: "TWO_INSTANCE_OK with two live Revit instances on different ports and different models"
    requirement: "IDENT-05"
    verification: []
    human_judgment: true
    rationale: "Needs two live Revit instances; accepted live in plan 01-04 (D-16, D-17, D-18)"
  - id: D4
    description: "The payload ships bridge.py; the deployed layout passes the acceptance gate"
    requirement: "IDENT-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_payload_ships_root_modules.py#test_payload_copies_every_root_module_main_imports"
        status: pass
      - kind: integration
        ref: "staged local app layout: deploy/gate.py -> GATE_OK, MANIFEST=ok (54 tools), INIT_LATENCY_S=0.959"
        status: pass
    human_judgment: false

duration: 4 min
completed: 2026-10-07
status: complete
---

# Phase 1 Plan 03: Status Reports Its Target, Payload Ships bridge.py Summary

**`get_revit_status` now ends every reply with `MCP target: host:port` (even on 503 or a refused connection), a two-entry stdio harness proves two ports report their own targets, and the payload build copies `bridge.py` behind a unit guard and a staged gate run.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-10-07T06:52:30Z
- **Completed:** 2026-10-07T06:56:04Z
- **Tasks:** 2
- **Files modified:** 7 (3 created, 4 modified)

## Accomplishments
- `get_revit_status` reads `getattr(revit_get, "revit_target", None)` and appends the target line after `format_response`; no transport import, registrar signature and manifest unchanged. Docstring tells the model the port is a launch slot, not a model, and to compare the `Document:` line (RESEARCH Pitfall 10).
- `tests/test_two_instance_targets.py` runs two stdio entries concurrently with their own `REVIT_PORT`, prints `ENTRY`/`LISTENERS` lines, and prints `TWO_INSTANCE_OK` only when both are `active`, targets match, documents differ and each port has one distinct listener. Offline run: exit 1, `target=127.0.0.1:48997`, `target=127.0.0.1:48998`, `TWO_INSTANCE_FAIL`.
- `deploy/build-payload.cmd` copies `bridge.py`; `test_payload_copies_every_root_module_main_imports` fails (verified by removing the line) when a root module main.py imports is not copied. Staged local layout (`main.py`, `bridge.py`, server/gate, `tools/`, `tests/`) passes `gate.py`: `GATE_OK`.
- `start_revit` docstring now states it probes its own `REVIT_PORT`, pyRevit's first-free-port-from-48884 rule, and the one-at-a-time launch requirement.
- Unit suite: 391 passed, 3 skipped (385 after plan 01-02).

## Task Commits

1. **Task 1: Status reports target + two-entry harness (tracer)** - `e547979` (feat)
2. **Task 2: Ship bridge.py, start_revit docstring** - `d50d951` (feat)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `tools/status_tools.py` - target line appended after `format_response`; docstring rewritten
- `tests/unit/test_status_target.py` - five fake-MCP tests for D-06
- `tests/test_two_instance_targets.py` - older-tier two-entry harness (D-17)
- `deploy/build-payload.cmd` - `copy /y "%REPO%\bridge.py"` after the main.py line
- `tests/unit/test_payload_ships_root_modules.py` - copy-list guard
- `tools/process_tools.py` - `start_revit` docstring only
- `pyproject.toml` - dependency comment only (httpx is imported in bridge.py)

## Decisions Made
- Target line is appended after formatting to survive `format_response`'s message-reduction and to appear on error strings.
- With no `revit_target` attribute the output is exactly `format_response(response)`.
- `deploy\build-payload.cmd` was never run (it publishes to the fleet share); verification used a staged temp copy.

## Deviations from Plan

None - plan executed exactly as written. RED for the five status tests was confirmed (3 failing) before implementing; each task landed as one `feat` commit, matching plans 01-01 and 01-02.

## Issues Encountered
None. Git warns that LF will become CRLF on the new/edited files; the repo's existing line-ending handling applies.

## Known Stubs
None.

## Threat Flags
None - T-01-11..T-01-14 are the plan's own mitigations; no new endpoint, auth path or schema surface.

## Next Phase Readiness
- Plan 01-04 runs `tests/test_two_instance_targets.py` against two live Revit instances (staggered launch, D-25) and checks RESEARCH A5 (client namespaces two entries).

## Self-Check: PASSED
- tools/status_tools.py, tests/unit/test_status_target.py, tests/test_two_instance_targets.py, tests/unit/test_payload_ships_root_modules.py FOUND; commits e547979, d50d951 FOUND.
- `git rev-list --count 4734857..HEAD` = 2 at SUMMARY time; `git diff --stat -- uv.lock deploy/configure_hermes.py deploy/gate.py deploy/server.py tests/unit/tool_manifest.txt revit_mcp` empty.

---
*Phase: 01-serialization-and-configurable-addressing*
*Completed: 2026-10-07*
