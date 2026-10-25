---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "07"
subsystem: testing
tags: [pytest, permits, hmac, shared-secret, revit-routes]
requires:
  - phase: 07-02
    provides: HMAC permit minting and IronPython permit verification primitives
provides:
  - Permit-bearing request doubles with API-relative paths for gated unit tests
  - A real-permit permissive authorizer and isolated consumed-nonce registry per test
  - Route and bridge-to-gate test coverage prepared for enforcement in plan 07-08
affects: [07-08, SAFE-12, mutation-safety]
actuals:
  tokens: 6055
  tasks: 2
  commits: 2
plan_head_before: c2472e3b089ebae346d456050ace0c9b2a4084c7
tech-stack:
  added: []
  patterns:
    - Test request bodies use permit.wire_text with the envelope first and a permit bound to request.path.
    - Each unit test starts with a fresh revit_mcp.permits._CONSUMED registry.
key-files:
  created: []
  modified:
    - tests/unit/gate_support.py
    - tests/unit/conftest.py
    - tests/unit/test_security_state.py
    - tests/unit/test_document_contracts.py
    - tests/unit/test_trust_dialect.py
    - tests/unit/test_routes_analysis_color_identity.py
    - tests/unit/test_routes_document_interop_identity.py
    - tests/unit/test_routes_mep_parameter_identity.py
    - tests/unit/test_routes_view_code_identity.py
    - tests/unit/test_audit_correlation.py
    - tests/unit/test_phase5_gate_e2e.py
    - tests/unit/test_secret_gate_e2e.py
key-decisions:
  - "Mint real test permits from the exact envelope-first wire text instead of adding a test-only permit bypass."
  - "Resolve each handler request path from its registered route so a future enforcing gate validates the same API-relative path pyRevit receives."
patterns-established:
  - "Gated handler tests construct requests through gate_support with matching data, path, permit route, and session token."
  - "Bridge-to-real-gate tests assert permit route and target session token alongside the existing secret and call-id assertions."
requirements-completed: [SAFE-12]
coverage:
  - id: D1
    description: "Shared permit-aware test plumbing mints envelope-first, path-bound request permits and isolates consumed nonce state."
    requirement: SAFE-12
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit/test_security_state.py tests/unit/test_document_contracts.py tests/unit/test_trust_dialect.py tests/unit/test_phase7_tracer.py -q"
        status: pass
      - kind: unit
        ref: "uv run pytest tests/unit -q"
        status: pass
    human_judgment: false
  - id: D2
    description: "Route identity and bridge-to-gate suites submit permit-carrying requests tied to the route and Revit target token."
    requirement: SAFE-12
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit/test_routes_analysis_color_identity.py tests/unit/test_routes_document_interop_identity.py tests/unit/test_routes_mep_parameter_identity.py tests/unit/test_routes_view_code_identity.py tests/unit/test_audit_correlation.py tests/unit/test_phase5_gate_e2e.py tests/unit/test_secret_gate_e2e.py -q"
        status: pass
      - kind: unit
        ref: "uv run pytest tests/unit -q"
        status: pass
    human_judgment: false
duration: 25min
completed: 2026-10-25
status: complete
---

# Phase 07 Plan 07: Permit-ready unit request plumbing Summary

**Gated unit requests now carry envelope-first, HMAC-minted permits bound to their API-relative route and pinned Revit session token, without a production bypass.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-10-25T19:01:11Z
- **Completed:** 2026-10-25T19:26:11Z
- **Tasks:** 2/2
- **Files modified:** 12

## Accomplishments

- Extended `gate_support` request doubles so non-GET tests send the envelope-first wire text, a `path`, and a real permit created from the exact arguments, route, and test process token.
- Updated the test-wide permissive bridge authorizer to mint real permits when a secret and machine session token are available, and reset the Revit-side consumed-nonce registry for every test.
- Converted route identity, secret-gate, audit, Phase 5 end-to-end, security-state, document-contract, and trust-dialect request construction so permit enforcement in 07-08 preserves each row's existing assertion purpose.
- Strengthened bridge-to-real-gate envelope expectations to name the permit and validate its route and session binding.

## Task Commits

Each task was committed atomically:

1. **Task 1: Test request doubles carry a path and a real permit; the permissive authorizer mints; the registry is isolated** - `890b35f` (test)
2. **Task 2: Route suites and bridge-to-gate suites send permit-carrying requests the enforcing gate will accept** - `46a99c5` (test)

## Files Created/Modified

- `tests/unit/gate_support.py` - Defines the test route/token, creates permit-bearing wire bodies, attaches `path`, and configures a matching Revit test token and nonce registry.
- `tests/unit/conftest.py` - Mints a real bridge authorization permit and isolates `revit_mcp.permits._CONSUMED` through autouse fixtures.
- `tests/unit/test_security_state.py` - Adds API-relative paths to raw and gated request doubles without weakening malformed-envelope cases.
- `tests/unit/test_document_contracts.py` - Binds activation and open-read request construction to their handler routes.
- `tests/unit/test_trust_dialect.py` - Replays the same permit-bearing serialized bodies across plain and simulated IronPython verdict scenarios.
- `tests/unit/test_routes_analysis_color_identity.py` - Resolves registered handler paths, binds mutation/open-read requests to them, and routes the real bridge tracer through permit wire text.
- `tests/unit/test_routes_document_interop_identity.py` - Uses registered handler paths for normal and refusal request doubles.
- `tests/unit/test_routes_mep_parameter_identity.py` - Uses registered handler paths for normal and refusal request doubles while preserving CRLF source style.
- `tests/unit/test_routes_view_code_identity.py` - Adds route paths to normal, malformed, refusal, and open-read request doubles.
- `tests/unit/test_audit_correlation.py` - Verifies permit route and session token beside the existing secret/call-id correlation assertions.
- `tests/unit/test_phase5_gate_e2e.py` - Pins the matching test process token and confirms the real bridge body contains permit route/session fields.
- `tests/unit/test_secret_gate_e2e.py` - Sends envelope-first permit wire text through the secret-gate tracer and asserts the reserved envelope contains the route-bound permit.

## Decisions Made

- Used a fixed test policy hash and 60-second permit TTL, matching the planned test plumbing contract, while leaving production policy behavior untouched.
- Kept deliberately malformed and envelope-free rows raw; they only gain `path`, so they continue to test their original refusal behavior.
- Derived normal handler paths from registered route tables in identity suites rather than duplicating route constants at every call site.

## Verification

- `uv run pytest tests/unit/test_routes_analysis_color_identity.py tests/unit/test_routes_document_interop_identity.py tests/unit/test_routes_mep_parameter_identity.py tests/unit/test_routes_view_code_identity.py tests/unit/test_audit_correlation.py tests/unit/test_phase5_gate_e2e.py tests/unit/test_secret_gate_e2e.py -q` — 1107 passed.
- `uv run pytest tests/unit -q` — 6624 passed, 3 skipped.
- `grep -c '"permit"' tests/unit/test_audit_correlation.py` — passed (at least one assertion names the permit).
- All pytest commands used the mandated clean scratch `UV_PROJECT_ENVIRONMENT`; the repository `.venv` was not touched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test determinism] Reused minted permit bytes across cross-engine verdict comparison**
- **Found during:** Task 1
- **Issue:** The plain CPython and simulated IronPython scenarios minted independent permits with random nonces, making their serialized inputs differ and invalidating the equality check.
- **Fix:** Cached the permit-bearing body table once and replayed the same bytes in both scenarios.
- **Files modified:** `tests/unit/test_trust_dialect.py`
- **Verification:** Focused security/trust tests and the full unit suite passed.
- **Committed in:** `890b35f`

**2. [Rule 1 - Test correctness] Compared the API-relative permit route with the prefixed HTTP request path correctly**
- **Found during:** Task 1
- **Issue:** A bridge correlation assertion equated `/modify_element/` with `/genpro_revit_mcp/modify_element/`, although pyRevit receives the former as `request.path`.
- **Fix:** Kept the exact permit route assertion and checked that the HTTP path ends in that API-relative route.
- **Files modified:** `tests/unit/test_audit_correlation.py`
- **Verification:** Audit correlation tests and the full unit suite passed.
- **Committed in:** `890b35f`

---

**Total deviations:** 2 auto-fixed (2 Rule 1 test-correctness fixes).
**Impact on plan:** Both fixes preserve the intended verifier contract and existing row semantics; production code was not changed.

## Issues Encountered

- The git commit command reported a non-fatal inability to delete `.git/worktrees/hot-cirrus`; the commit completed and `git log -1` confirmed `46a99c5`.
- Repository checkout attributes warned that several modified test files will normalize LF to CRLF on a later Git touch. No line-ending conversion was intentionally introduced; the CRLF source file was preserved during editing.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 07-08 can enable Revit-side permit enforcement knowing unit request doubles, bridge authorization output, and route-specific gate paths already meet the real permit contract.
- No live Revit or Routes-server check was run; this plan is test plumbing only and all automated unit checks are green.

## Self-Check: PASSED

- Confirmed both task commits exist: `890b35f`, `46a99c5`.
- Confirmed all twelve modified test files exist and no production module was changed by this plan.

---
*Phase: 07-repository-owned-mutation-safety-and-human-approval*
*Completed: 2026-10-25*
