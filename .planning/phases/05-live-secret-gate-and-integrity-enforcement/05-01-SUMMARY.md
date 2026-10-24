---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 01
subsystem: security
tags: [shared-secret, integrity, gate, pyrevit-routes, ironpython3, tdd]

requires:
  - phase: 03-trust-primitives
    provides: revit_mcp/trust.py (split_envelope, check_secret, auth_failure, integrity_failure) and revit_mcp/integrity.py (check_integrity)
provides:
  - revit_mcp/security.py with initialize, gate_or_response and strip_envelope
  - trust.OPEN_POST_READ_ROUTES (D-02), clean_body, gate_failure, GATE_FAILURE_STATUS
  - the gate preamble contract, applied to /create_level/ as the tracer route
  - tests/unit/gate_support.py shared by the route suites
affects: [05-02, 05-03, 05-04, 05-05, 05-06, 05-07, 05-16]

plan_head_before: 6733de9ffcb19812cbdb7cc07806e8efc7499897
actuals:
  tokens: 36000
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Explicit first-call gate in the handler (gate_refusal = gate_or_response(request)), no wrapper"
    - "Type-preserving request.data rewrite (bytes to bytes, text to text, dict to dict)"
    - "Fail-closed module state: _STATE None answers 401 server_not_configured"

key-files:
  created:
    - revit_mcp/security.py
    - tests/unit/gate_support.py
    - tests/unit/test_security_state.py
  modified:
    - revit_mcp/trust.py
    - revit_mcp/building.py
    - tests/unit/test_routes_analysis_color_identity.py
    - tests/unit/test_phase2_inventory.py
    - tests/unit/test_registration.py
    - tests/unit/test_trust_dialect.py
    - tests/unit/test_trust_secret.py

key-decisions:
  - "The gate checks state, then secret (trust.check_secret), then integrity, so a wrong secret is a 401 even under a verified mismatch (D-04)"
  - "A gate that cannot read or rewrite a request answers the fixed HTTP 500 text of trust.gate_failure instead of raising (fail closed and loud)"
  - "strip_envelope imports textutils to test for the reserved key, so a body without it is left byte-for-byte as it arrived"

patterns-established:
  - "Gate preamble variable is named gate_refusal because the Phase 2 inventory test asserts the document guard's own refusal by name"
  - "Route suites build requests with gate_support.request_of, so every handler receives the envelope exactly as production will deliver it"

requirements-completed: [SEC-01, SEC-02, SEC-03, SEC-04, SEC-06, INTG-02, INTG-03, INTG-04]

duration: 35min
completed: 2026-10-24
status: complete
---

# Phase 5 Plan 01: Tracer gate on /create_level/ Summary

**Per-route gate in revit_mcp/security.py closes `/create_level/` end to end: the bridge's enveloped bytes pass into the real handler, while a missing or wrong secret (401) or a verified integrity mismatch (423) is refused before any Revit object is touched.**

## Performance

- **Duration:** about 35 min
- **Completed:** 2026-10-24
- **Tasks:** 2 (Task 1 tracer, Task 2 TDD)
- **Files:** 3 created, 7 modified

## Accomplishments

- `revit_mcp/security.py`: `initialize(root, package_dir)` computes the secret and the integrity verdict from the extension's own files and recomputes on every call; `gate_or_response(request)` refuses in the order state, secret, integrity and rewrites `request.data` without `_mcp` in the type it arrived in; `strip_envelope(request)` serves the seven open POST reads and never refuses or raises.
- `revit_mcp/trust.py`: `OPEN_POST_READ_ROUTES` (the seven D-02 keys), `clean_body`, `gate_failure`, `GATE_FAILURE_STATUS`.
- `/create_level/` opens with the gate preamble ahead of the document guard. Tracer tests drive it through the unchanged `bridge._send` and the IronPython 3 json stand-in: a committed level with the valid secret (request seen by the handler holds no `_mcp` key), 401 missing / mismatch / server_not_configured and 423 naming the files, each with zero transactions, zero events and zero guard calls.
- The full gate contract is pinned in `tests/unit/test_security_state.py` (64 rows): initialize on temp trees, gate and rewrite tables, odd and unreadable requests, SEC-04 regression, normalization-form mismatch, leak checks over bodies, repr and caplog, and a never-writes test. `test_trust_dialect.py` runs the gate and the strip under the simulated IronPython 3 engine and compares them with CPython.

## Task Commits

1. **Task 1 (tracer): gate /create_level/ end to end** - `213f3d4` (feat)
2. **Task 2 RED: failing tests for strip_envelope and the gate contract** - `2a16680` (test)
3. **Task 2 GREEN: strip_envelope and pinned contract** - `96802b8` (feat)

Tracer feedback gate: auto mode, automated-only verify; the tracer verify and the full suite were re-run green after the commit, so expansion proceeded (`Tracer verified end-to-end`).

## TDD Gate Compliance

RED (`2a16680`, 24 rows failing on the missing `strip_envelope`: AttributeError on the target behavior) precedes GREEN (`96802b8`). The RED commit leaves the full suite red by design, which departs from the plan's "green before every commit" rule; the orchestrator asked for RED to GREEN commit discipline on behavior-adding tasks, so that instruction was followed. Task 1 is a tracer and is a single commit; its RED run (fixture import error because `revit_mcp.security` did not exist) was observed locally and not committed.

## Verification

- Task 1 acceptance: `-k "create_level and (bridge or refus or 401 or 423)"` 10 passed; `git ls-files -- revit_mcp/security.py` prints the path; `OPEN_POST_READ_ROUTES` prints the seven keys; `clean_body` prints `b'{}' {} {}`; inventory, registration and conventions suites green.
- Task 2 acceptance: `test_security_state.py` 64 passed (needs 28); `test_trust_dialect.py -k security` 6 passed; both new test files tracked.
- Full suite: `uv run pytest tests/unit -q` gives 5301 passed, 3 skipped (baseline 5218 passed, 3 skipped).
- Plan verification: `git log --oneline --grep="(05-01)" -- bridge.py startup.py` prints nothing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pinned allow-lists of trust.py imports rejected `json`**
- **Found during:** Task 1 (full suite run)
- **Issue:** `clean_body` needs `json.dumps`, but `test_trust_secret.py::test_trust_imports_nothing_from_revit` and `test_trust_dialect.py::test_dialect_trust_imports_only_hashlib_and_textutils` pinned the import set to hashlib and textutils.
- **Fix:** widened both allow-lists by the standard-library `json` (the intent, nothing from Revit or pyRevit, is unchanged); renamed the dialect test to `..._hashlib_json_and_textutils`.
- **Files modified:** revit_mcp/trust.py, tests/unit/test_trust_secret.py, tests/unit/test_trust_dialect.py (test_trust_secret.py is not in the plan's files_modified)
- **Commit:** 213f3d4

**2. [Rule 1 - Bug] Planned docstring text would not compile**
- **Found during:** Task 1
- **Issue:** the `clean_body` docstring contained a literal backslash-u-XXXX sequence, a SyntaxError in a normal Python 3 string.
- **Fix:** reworded as "an ASCII escape sequence".
- **Files modified:** revit_mcp/trust.py
- **Commit:** 213f3d4

**3. [Rule 3 - Blocking] strip_envelope needs a presence test for the reserved key**
- **Found during:** Task 2 (GREEN)
- **Issue:** `trust.split_envelope` drops the key without saying whether it was present, but the contract rewrites only a dict body that contains `_mcp`.
- **Fix:** `security` imports `textutils` (a helper sibling already allowed) and parses once to test for the key; dialect import test updated to the helper siblings (integrity, textutils, trust).
- **Files modified:** revit_mcp/security.py, tests/unit/test_trust_dialect.py
- **Commit:** 96802b8

**Total deviations:** 3 auto-fixed (1 bug, 2 blocking). **Impact:** none on behavior; two existing pin tests widened by one stdlib module and one helper sibling.

### D-06 findings

None. With the envelope on every request in the analysis, annotation, building, colors and detail suite, no not-yet-gated handler failed because `_mcp` was present, and the helper does not strip it.

## Known Stubs

None.

## Threat Flags

None. No network endpoint, auth path or schema beyond the plan's threat model was added (T-05-01, T-05-02, T-05-03, T-05-08 and T-05-09 are covered by the tracer, leak, SEC-04 and rewrite tests).

## Issues Encountered

`git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit. It comes from git's housekeeping on a stale linked worktree and does not affect the commits.

## Next Phase Readiness

Ready for 05-02 to 05-05 (copy the gate preamble to the other 40 non-GET handlers, using `strip_envelope` for the open reads) and 05-16 (bridge `revit_post` envelope and the `startup.py` `security.initialize` call). `bridge.py` and `startup.py` are untouched.

## Self-Check: PASSED

- Created files exist: revit_mcp/security.py, tests/unit/gate_support.py, tests/unit/test_security_state.py.
- Commits found: 213f3d4, 2a16680, 96802b8.
- All acceptance criteria and the plan-level verification re-run green (full unit suite 5301 passed, 3 skipped).
