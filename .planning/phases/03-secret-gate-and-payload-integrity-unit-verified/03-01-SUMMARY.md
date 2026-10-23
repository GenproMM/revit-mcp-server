---
phase: 03-secret-gate-and-payload-integrity-unit-verified
plan: 01
subsystem: security
tags: [shared-secret, envelope, constant-time-compare, ironpython3, sha256, http-401]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: flat top-level document key, the bridge _send path and the no-handler-wrapper rule
provides:
  - revit_mcp/trust.py - pure, inert secret-gate logic (envelope split, SHA-256 + XOR constant-time compare, four-state verdict, 401 body, GET/HEAD method gate, secret file normalization)
  - bridge.with_envelope(data, secret) - client half of the envelope, called by no production code
  - tracer test that runs the real unchanged bridge._send into the Revit-side trust functions and back through format_response
affects: [03-03 bridge secret loading, 03-06 dialect simulation, 03-08 live IPY342 check, 05 live enforcement]

actuals:
  tokens: 8700
  tasks: 2
  commits: 2

plan_head_before: e5ce1baf5dd4ef5cb7bc418a473f7f3291e51e86

tech-stack:
  added: []
  patterns:
    - "Pure Revit-half helper with no pyRevit import, unit-tested under CPython, registered as a helper in test_registration"
    - "One hand-rolled fixed-length compare (SHA-256 both sides, XOR-accumulate) shared by both runtimes, pinned by AST tests"
    - "Fail-closed verdicts: server configuration decided first, unknown verbs gated, reason whitelist in auth_failure"

key-files:
  created:
    - revit_mcp/trust.py
    - tests/unit/test_secret_gate_e2e.py
    - tests/unit/test_trust_secret.py
    - tests/unit/test_trust_envelope.py
  modified:
    - bridge.py
    - tests/unit/test_registration.py

key-decisions:
  - "C1: _mcp stays secret-only and document stays flat; split_envelope returns the whole _mcp dict so call_id and an approval token can ride it later"
  - "C2: small composable pure functions, no decorator, honouring the Phase 2 ban on a startup.py handler wrapper"
  - "C3: hand-rolled compare, with the FixedTimeEquals (.NET Core 2.1+) / Revit 2024 .NET Framework 4.8 fallback reason written into the secret_matches docstring"
  - "gate_applies exempts only GET and HEAD, so an unknown verb is gated (fail closed)"
  - "MIN_SECRET_LENGTH = 16: a shorter expected value is server_not_configured"

patterns-established:
  - "Structure tests over ast for properties of code (no early exit, no logging, no global state, imports) rather than timing"
  - "Route inventory reuse (inventory_support.route_inventory) cross-checked against the raw decorator count"

requirements-completed: [SEC-01, SEC-02, SEC-04, SEC-05, SEC-06]

coverage:
  - id: D1
    description: "A secret built by bridge.with_envelope travels through the unchanged bridge._send as text/plain bytes, is recovered by trust.split_envelope through parse_request_data, and a wrong, missing or unconfigured secret returns a visible HTTP 401 through format_response"
    requirement: "SEC-01"
    verification:
      - kind: integration
        ref: "tests/unit/test_secret_gate_e2e.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "check_secret four-state verdict table, fail-closed on unconfigured or empty secrets"
    requirement: "SEC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_secret.py#test_verdict_table"
        status: pass
    human_judgment: false
  - id: D3
    description: "Constant-time compare structure (SHA-256, XOR-accumulate over 32 positions, no early exit, no direct == of secrets) with the documented fallback reason"
    requirement: "SEC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_secret.py#test_constant_time_visits_every_position"
        status: pass
      - kind: unit
        ref: "tests/unit/test_trust_secret.py#test_constant_time_loop_has_no_early_exit"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET/HEAD-only exemption, checked against the static route inventory (every route GET or POST, /status/ GET)"
    requirement: "SEC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_secret.py#test_method_every_route_is_get_or_post"
        status: pass
    human_judgment: false
  - id: D5
    description: "No secret in any exception, log record, return value or 401 body, even when hashlib raises the secret"
    requirement: "SEC-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_secret.py#test_secret_never_leaks_when_hashing_fails"
        status: pass
    human_judgment: false
  - id: D6
    description: "Constant-time behaviour as measured by wall clock, and hashlib.sha256 under the live IPY342 routes engine"
    requirement: "SEC-04"
    verification: []
    human_judgment: true
    rationale: "Timing tests are flaky by design (research advises against them) and the live engine check is plan 03-08, a blocking human checkpoint"

duration: 12min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 01: Secret gate pure logic and request envelope Summary

**Inert shared-secret gate: `revit_mcp/trust.py` (SHA-256 + XOR constant-time compare, four-state verdict, HTTP 401 body, GET/HEAD-only method gate) plus `bridge.with_envelope`, proven by a tracer that drives the real unchanged `bridge._send` into the Revit-side logic and back through `format_response`.**

## Performance

- **Duration:** about 12 min
- **Completed:** 2026-10-23
- **Tasks:** 2 of 2
- **Files:** 4 created, 2 modified

## Accomplishments

- Tracer (Task 1): `bridge.with_envelope({...}, secret)` posts through the real `_send` as `text/plain; charset=utf-8` bytes; a simulated Revit handler built from `trust.split_envelope` / `check_secret` / `auth_failure` answers 200 with the payload minus `_mcp` (flat `document` key intact) or a 401 that reaches `format_response` verbatim as `Error: 401 - ...` naming `mismatch`, `missing` or `server_not_configured`.
- Hardening (Task 2): verdict table including empty and Cyrillic (NFC vs NFD) rows, counting-sequence and AST proof that the compare visits all 32 positions with no early exit, a leak test with a `hashlib` fake that raises the secret, the method rule cross-checked against `route_inventory()` (every route GET or POST, `/status/` GET), secret-file normalization, and the envelope edge table.
- `trust` registered as a helper in both `test_registration.py` sets. `startup.py`, every other `revit_mcp` module, `tools/` and `main.py` are untouched; `with_envelope` is called by no production code.

## Task Commits

1. **Task 1: tracer** - `310c134` (feat) - revit_mcp/trust.py, bridge.py, tests/unit/test_secret_gate_e2e.py
2. **Task 2: hardening** - `56ba399` (feat) - revit_mcp/trust.py, tests/unit/test_trust_secret.py, tests/unit/test_trust_envelope.py, tests/unit/test_registration.py

## Verification

- `uv run pytest tests/unit -q`: 4180 passed, 3 skipped, 0 failed (plan baseline 4054 passed, 3 skipped; the count also includes an unrelated untracked `tests/unit/test_parallel_installation.py` from another session, which this plan did not touch or commit).
- Tracer: 5 passed. `test_trust_secret.py` + `test_trust_envelope.py`: 116 passed (plan floor 30). Selector `-k "constant or leak or secret_never or method"`: 39 passed (floor 8).
- `TRACER_OK` and `GATE_OK` acceptance one-liners print as required.
- `uv run python tests/test_init_latency.py`: `INIT_LATENCY_S=0.368` (gate 2.0).
- `git hash-object startup.py` is `85de483307be925517bee2ce3f109e5d6538560c` before and after (the file carries the user's own uncommitted edits, which were not touched).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Hardened `auth_failure` and `read_secret_file` against hostile inputs**
- **Found during:** Task 1 and Task 2
- **Issue:** `reason not in <dict>` would raise `TypeError` for an unhashable reason (a list or dict); `open(None)` and a path holding a NUL raise `TypeError` / `ValueError`, which the plan's `except (IOError, OSError)` would not catch, so "never raises" would not hold.
- **Fix:** `auth_failure` tests membership in a tuple of the three reasons; `read_secret_file` also catches `TypeError` and `ValueError`. Tests cover both (`["x", SECRET]`, `{"k": SECRET}` reasons; `None` and a NUL path).
- **Files modified:** revit_mcp/trust.py, tests/unit/test_trust_secret.py
- **Commit:** 310c134, 56ba399

**2. [Rule 1 - Bug in plan text] `missing` hint wording**
- **Found during:** Task 1
- **Issue:** the plan's hint reads "so app\_bridge_secret exists", an evident markdown-escape artifact.
- **Fix:** shipped as "so _bridge_secret exists".
- **Files modified:** revit_mcp/trust.py
- **Commit:** 310c134

**3. [Process] Task 2 code written ahead of its tests**
- `tdd="true"` was not enforced (TDD mode off). Task 1 followed RED then GREEN (the e2e file failed on the missing module first). For Task 2 the three new functions were written before their tests, and all tests passed on first run; no failing-first run was recorded for them.

**Total deviations:** 2 auto-fixed (1 Rule 2, 1 Rule 1) plus 1 process note. **Impact:** none on scope; all additive and within the plan's files.

## Issues Encountered

A shell-quoting slip wrote a literal NUL byte and tab/CR/LF characters into `trust.py`'s `secret_from_bytes` (CPython reported "source code string cannot contain null bytes" at test collection). Fixed before Task 2's commit by rewriting those two lines as escape sequences; the committed file has no control characters (verified by byte count).

## Known Stubs

None.

## Threat Flags

None. `trust.py` adds no endpoint, performs no I/O beyond the read-only `read_secret_file`, and nothing calls it yet.

## Decisions for review at plan check

- C1, C2 and C3 (above) are adopted from 03-RESEARCH.md; CONTEXT.md was not rewritten.
- SEC-04 and SEC-05 remain flagged: no wall-clock timing test was added, and live proof that `/status/` answers without a secret is Phase 5.

## Next Phase Readiness

Ready for 03-02 and 03-03. Plan 03-03 duplicates `secret_from_bytes` in `bridge.py` and must keep the rule identical; plan 03-08 updates the `secret_matches` docstring after the live IPY342 `hashlib.sha256` check.

## Self-Check: PASSED

- FOUND: revit_mcp/trust.py, tests/unit/test_secret_gate_e2e.py, tests/unit/test_trust_secret.py, tests/unit/test_trust_envelope.py
- FOUND commits: 310c134, 56ba399
- `git rev-list --count e5ce1ba..HEAD` = 2, matching `actuals.commits`
