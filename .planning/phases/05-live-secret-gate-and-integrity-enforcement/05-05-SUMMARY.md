---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 05
subsystem: security
tags: [shared-secret, integrity, gate, pyrevit-routes, ironpython3, tdd]

requires:
  - phase: 05-live-secret-gate-and-integrity-enforcement
    provides: revit_mcp/security.py (gate_or_response, strip_envelope) and tests/unit/gate_support.py from 05-01
provides:
  - gated preamble on /transform_elements/, /create_view/, /set_active_view/, /open_model/, /execute_code/, /activate_document/
  - strip_envelope preamble on the open reads /model_worksets/, /document_summary/, /document_levels/
  - 401/401/423 refusal rows for the five view/code routes and for /activate_document/, asserting no side effect, no Open* call, no stamp
affects: [05-06, 05-16]

plan_head_before: ead7e7191df9428df6cb5fed9d402a4e8a002457
actuals:
  tokens: 9000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Process-level routes (/execute_code/, /open_model/) gate before _stamp_exception / _stamp_process, so a refusal reads nothing from Revit"
    - "documents.py imports the security helpers inside register_documents_routes, matching that module's cold-start rule"

key-files:
  created: []
  modified:
    - revit_mcp/transforms.py
    - revit_mcp/view_management.py
    - revit_mcp/worksharing.py
    - revit_mcp/code_execution.py
    - revit_mcp/documents.py
    - tests/unit/test_routes_view_code_identity.py
    - tests/unit/test_document_contracts.py

key-decisions:
  - "A refused /execute_code/ is proven not to run submitted code by a row whose code would flip a probe module attribute; the gate answers 401 and the probe stays False"
  - "The two /execute_code/ rows that sent b'{not json' now expect 401 missing; the route's own parse-failure 500 (with the document_scope notice) is kept alive by patching the module's parse_request_data after a valid envelope"
  - "The activate row that looped over None, b'', b'{}', b'not json', b'[1, 2]' was split: envelope-only bodies in bytes, text and dict form give the route's own 400; bodies that cannot carry an envelope give 401 missing"

patterns-established:
  - "Open-read rows are parametrized over none / wrong / valid / mismatch envelope variants, compare against the bare reply, and assert the route's request.data no longer contains _mcp"

requirements-completed: [SEC-01, SEC-03, SEC-05, SEC-06, INTG-04]

duration: 25min
completed: 2026-10-24
status: complete
---

# Phase 5 Plan 05: Gate transforms, view management, model open, arbitrary code and document activation Summary

**Arbitrary IronPython (`/execute_code/`), model open, document activation, view switching, view creation and element transforms now refuse 401 missing, 401 mismatch or 423 integrity mismatch before any Revit read, while `/model_worksets/`, `/document_summary/` and `/document_levels/` stay open and never see the secret.**

## Performance

- **Duration:** about 25 min
- **Completed:** 2026-10-24
- **Tasks:** 2 (Task 1 tracer, Task 2 TDD)
- **Files:** 7 modified, none created

## Accomplishments

- `transform_elements_handler` (transforms), `create_view_handler`, `set_active_view_handler` (view_management), `open_model` (worksharing), `execute_code` (code_execution) and `activate_document` (documents) open with `gate_refusal = gate_or_response(request)` as the first statements after the docstring. For the three that take no document guard (`/execute_code/`, `/open_model/`, `/activate_document/`) it precedes `_stamp_exception`, `_stamp_process`, `process_identity_or_error` and any registry read, so a refusal carries no `document_scope`, `process_identity`, `identity_error` or `observed_active_document` (Pitfall 12).
- `model_worksets`, `document_summary` and `document_levels` open with `strip_envelope(request)`. The handler bodies after every preamble are unedited.
- View/code suite: three parametrized refusal tests over `list(MUTATIONS) + sorted(PROCESS_LEVEL)` (15 rows) assert the status, no `outcome`, `world.events == []`, no transaction, `world.open_calls == []`, no guard call, no stamp and no secret in the reply. A fourth row proves a refused `/execute_code/` never runs the submitted code. `test_model_worksets_needs_no_secret_and_never_sees_the_envelope` runs four envelope variants (none, wrong, valid, integrity mismatch).
- Document suite: `activate_handlers` calls `configure_gate`; the activate rows send enveloped bodies (bytes, text and dict forms as before); new rows prove 401 missing, 401 mismatch and 423 with `uiapp.calls == []` and traps showing neither the registry nor the process identity was read; 8 open-read rows cover summary and levels over four variants.

## Task Commits

1. **Task 1 (tracer): gate transforms, view, open_model and execute_code; strip /model_worksets/** - `e62a179` (feat)
2. **Task 2: gate /activate_document/; strip /document_summary/ and /document_levels/** - `1c29ad8` (feat)

Tracer feedback gate: auto mode, automated-only verify; the tracer verify (156 passed) and the acceptance filters were re-run green after Task 1, and the full unit suite was green (5504 passed, 3 skipped) before the Task 1 commit, so expansion proceeded (`Tracer verified end-to-end`).

## TDD Gate Compliance

Task 1: RED observed locally (21 failed: 15 refusal rows, the probe row, the two changed `/execute_code/` rows' new expectations and 3 `/model_worksets/` variants), then GREEN (156 passed); committed as one change, as in 05-01..05-04. Task 2: RED observed locally (10 failed), then GREEN (325 passed); committed as one change.

## Verification

- Task 1 acceptance: `-k "shared_secret or wrong_secret or integrity_mismatch"` 15 passed (needs at least 15); `-k "model_worksets and envelope"` 4 passed (needs at least 3); `test_phase2_inventory.py -k "execute_route or open_model"` 9 passed (needs at least 2); full suite 5504 passed, 3 skipped.
- Task 2 acceptance: `-k "activate and (secret or mismatch or 401 or 423)"` 3 passed (needs at least 3); the AST one-liner printed `PREAMBLES all`; full suite 5516 passed, 3 skipped (baseline 5483 passed, 3 skipped, plus 33 new rows).

## Deviations from Plan

None - plan executed exactly as written. Two judgment calls inside the plan's latitude are listed under key-decisions (how to keep the `/execute_code/` parse-failure row alive, and how to split the activate bad-body row).

## D-06 findings

None. No pre-existing row failed because of a present `_mcp` key.

## Known Stubs

None.

## Threat Flags

None. T-05-19 is covered by the 401/401/423 rows with `world.events == []` plus the probe row; T-05-20 by `world.open_calls == []`, no `setview` event and `uiapp.calls == []`; T-05-21 by the no-stamp assertions on every refusal; T-05-22 by the four-variant open-read rows.

## Issues Encountered

`git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit (stale linked worktree housekeeping, as in 05-01..05-04); the commits are unaffected. All edited files had LF working copies and kept them.

## Next Phase Readiness

Ready for 05-06, which makes the preamble mandatory with the all-34 sentinel. `bridge.py` and `startup.py` are still untouched, so live use waits for 05-16.

## Self-Check: PASSED

- Modified files exist: revit_mcp/transforms.py, view_management.py, worksharing.py, code_execution.py, documents.py, tests/unit/test_routes_view_code_identity.py, tests/unit/test_document_contracts.py.
- Commits found: e62a179, 1c29ad8 (`git rev-list --count ead7e71..HEAD` is 2).
- All acceptance criteria re-run green; full unit suite 5516 passed, 3 skipped.
