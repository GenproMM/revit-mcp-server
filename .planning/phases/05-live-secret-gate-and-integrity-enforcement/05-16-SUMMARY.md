---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 16
subsystem: security
tags: [shared-secret, bridge, startup, gate, envelope, ironpython3, tdd]

requires:
  - phase: 05-live-secret-gate-and-integrity-enforcement
    provides: "05-01 revit_mcp/security.py (initialize, gate_or_response, strip_envelope) and tests/unit/gate_support.py"
provides:
  - "bridge.revit_post envelopes every POST body with the loaded secret under _mcp before _dispatch"
  - "bridge._secret() lazy memoized loader, reset_secret_cache(), _SECRET_UNSET sentinel"
  - "startup.register_routes calls security.initialize once at extension load, failure isolated in registry.FAILED['security']"
  - "tests/unit/test_phase5_gate_e2e.py: revit_post through a MockTransport into the real gate"
affects: [05-06, 05-07, 05-08, 05-09]

plan_head_before: a5b8365c6294670678913c93c895cf5c191821eb
actuals:
  tokens: 14000
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Envelope built before _dispatch so a model-built bad body is 'NOT sent', never 'outcome unknown'"
    - "Lazy memoized secret with an unset sentinel (None is a valid cached value); tests pin the cache, production has no bypass"
    - "startup initializes state only (no wrapper, no api attribute); failure recorded and gate left closed"

key-files:
  created:
    - tests/unit/test_phase5_gate_e2e.py
  modified:
    - bridge.py
    - startup.py
    - tests/unit/conftest.py
    - tests/unit/test_bridge_secret_client.py
    - tests/unit/test_security_state.py

key-decisions:
  - "The bridge builds the envelope in revit_post before _dispatch and tags a refusal not-sent (RESEARCH Pitfall 4); _send, revit_get and revit_image are untouched"
  - "Secret cache uses an _SECRET_UNSET sentinel so a missing secret file (None) is memoized and not re-read on every POST"
  - "startup passes security.initialize the extension root (holds _manifest.json) and the revit_mcp directory (holds _bridge_secret)"

patterns-established:
  - "Unit tests never read the developer's real secret: conftest autouse pins bridge._secret_cache to None"
  - "Startup rows load the real startup.py from a temp extension tree with a fake pyrevit.routes.API, copying files byte for byte"

requirements-completed: [SEC-02, SEC-03, SEC-06, INTG-02, INTG-07]

duration: 7min
completed: 2026-10-24
status: complete
---

# Phase 5 Plan 16: Bridge envelope and startup gate initialization Summary

**Every POST from the MCP server now carries the shared secret under `_mcp` and passes the real 05-01 gate end to end, a forged or non-object body is refused as "NOT sent", and `startup.py` opens the gate state once at extension load with failures recorded and the gate left closed.**

## Performance

- **Duration:** about 7 min
- **Completed:** 2026-10-24
- **Tasks:** 2 (Task 1 tracer, Task 2 TDD)
- **Files:** 1 created, 5 modified

## Accomplishments

- `bridge.revit_post` builds `with_envelope(data, _secret())` before `_dispatch`; a `ValueError` (a body that is not an object, or one that already holds `_mcp`) returns a fixed "Error: the request was NOT sent to Revit: ..." text tagged `not-sent`, with neither body nor secret in it, and no POST reaches the transport. GET calls carry no body.
- `bridge._secret()` loads the secret lazily on the first POST and memoizes it (None included); `reset_secret_cache()` forces a reload; importing bridge never calls `load_secret` (proved by a subprocess import and an AST pin).
- `tests/unit/test_phase5_gate_e2e.py` (11 rows): `revit_post` over a MockTransport into the real `security.gate_or_response` under the IronPython 3 json stand-in; correct secret reaches the handler without `_mcp`; missing and mismatch are visible `Error: 401 - ` texts that `format_response` leaves unchanged and that never contain the secret; forged, list and text bodies send nothing; GET sends no body; lazy memoization rows.
- The three inert pins in `test_bridge_secret_client.py` became wired pins: `test_send_posts_exactly_json_dumps_of_the_body_it_is_given`, `test_envelope_and_secret_loader_are_called_only_from_bridge`, `test_load_secret_runs_lazily_never_at_import`.
- `tests/unit/conftest.py` pins `bridge._secret_cache` to None so no unit test reads the developer's `revit_mcp/_bridge_secret`.
- `startup.py` calls `security.initialize(os.path.dirname(package.__path__[0]), package.__path__[0])` after the identity block and before the domain loop; an exception is recorded as `registry.FAILED["security"]` and logged with `logger.exception`, leaving `_STATE` None (401 `server_not_configured`). The module docstring no longer claims every cross-module import goes to the flat `utils` helper.
- Startup rows (6, names contain "startup") in `test_security_state.py`: source order and the guarding try/except; the real `startup.py` from a temp tree with no `_manifest.json` (secret loaded, integrity unverifiable/manifest_missing, no security failure, REGISTERED == ["example"], gate returns None with the secret and 401 missing without); stub `initialize` raising (`"RuntimeError: boom"`); missing security module (ImportError family); secret absent from the failure record and the log; `check_integrity` raising keeps the gate closed.

## Task Commits

1. **Task 1 (tracer): revit_post envelope, lazy secret, wired pins, conftest pin** - `dae268d` (feat)
2. **Task 2 RED: failing startup rows** - `95c7f0e` (test)
3. **Task 2 GREEN: startup initializes the security gate** - `435ff6c` (feat)

Tracer feedback gate: auto/default mode with an automated-only verify; the tracer verify and the full unit suite were re-run green after the commit, so expansion proceeded (`Tracer verified end-to-end`).

## TDD Gate Compliance

Task 2 RED (`95c7f0e`, 4 of 6 startup rows failing on the missing startup block; the leak row and the `check_integrity`-raising row already held from 05-01 and pin existing behavior) precedes GREEN (`435ff6c`). As in 05-01, the RED commit leaves the suite red by design, following the orchestrator's RED to GREEN commit discipline over the plan's "green before every commit" line. Task 1 is a tracer and is a single commit; its RED run (13 failures) was observed locally before the bridge change.

## Verification

- Task 1: `test_phase5_gate_e2e.py` 11 passed; the four named files together 178 passed; `-k inert` selects nothing, `-k "lazily or only_from_bridge or json_dumps_of_the_body"` 3 passed; the AST listing prints `['_secret', 'reset_secret_cache', 'revit_post']`; `tests/test_init_latency.py` prints `INIT_LATENCY_S=0.551` (below 2.0).
- Task 2: `-k startup` 6 passed; `ORDER_OK`; `test_startup_installs_no_common_handler_wrapper` and `no_route_wrapper` 1 passed each; the five named startup-adjacent suites 1009 passed.
- Full suite: `uv run pytest tests/unit -q` gives 5533 passed, 3 skipped (baseline 5516 passed, 3 skipped).
- No live Revit step was run; Revit and pyRevit were never touched.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None. T-05-04 (initialize failure keeps the gate closed), T-05-05 and T-05-06 (forged body refused as not-sent before `_dispatch`), T-05-07 (conftest pin) and T-05-65 (fixed NOT-sent text, no secret in replies, logs or the failure record, no print in bridge.py) are each covered by rows above.

## Issues Encountered

`git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit (stale linked worktree housekeeping, as recorded in 05-01); the commits are unaffected.

## Next Phase Readiness

The request path from MCP tool to route handler is closed: the bridge sends the envelope on every POST and the extension initializes the gate at load. A deployed extension without a payload secret answers 401 missing on every gated route until the payload and extension are built with the same secret (deploy plans of this phase). Ready for the remaining wave plans.

## Self-Check: PASSED

- Created file exists: tests/unit/test_phase5_gate_e2e.py.
- Commits found: dae268d, 95c7f0e, 435ff6c.
- All acceptance criteria and the plan-level verification re-run green (full unit suite 5533 passed, 3 skipped).
