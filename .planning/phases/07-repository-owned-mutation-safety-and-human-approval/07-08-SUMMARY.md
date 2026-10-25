---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "08"
subsystem: security
status: complete
---

# Phase 7 Plan 08 Summary

## Outcome

The Revit-side explicit gate now enforces the one-time mutation permit after shared-secret and integrity checks, before body cleanup or any route effect. The status surface reports both permit protocol support and the active approval-policy diagnostics.

## Changes

- Added `identity.process_token()` to read the startup-owned AppDomain process token safely without touching Revit objects.
- Added the single `permits.check_and_consume(...)` enforcement call in `security.gate_or_response`.
  - Order remains state -> secret (`401`) -> integrity (`423`) -> permit (`403`) -> cleaned request body.
  - Missing, replayed, retargeted, expired, or session-mismatched permits are refused before document access, collectors, or transactions.
  - Open POST reads continue to use `strip_envelope()` without consuming a permit.
- Added AST and behavioral coverage for the sole enforcement point, refusal ordering, replay, route/session binding, and every owned fake-pyRevit mutation handler.
- Converted legacy gate tests to true byte/text wire bodies with real permits. Dict payloads remain unsupported for cryptographic permit verification because exact wire text is unavailable.
- Added permit protocol data to the `/status/` security block, including its fallback response.
- Exposed `policy.status` through the injected `revit_get.policy_status` seam and rendered approval-policy and permit-enforcement status lines in `get_revit_status`.
- Added an offline mixed-rollout regression suite, including an old-extension test from revision `781a548` that proves a permit envelope is stripped harmlessly by the pre-Phase-7 gate.

## Verification

- `uv run pytest tests/unit/test_phase7_gate_wiring.py tests/unit/test_phase5_gate_wiring.py tests/unit/test_phase7_tracer.py tests/unit/test_routes_mep_parameter_identity.py tests/unit/test_conventions.py -q`
  - `916 passed, 3 skipped`
- `uv run pytest tests/unit/test_phase7_rollout.py tests/unit/test_phase5_status_diagnostics.py tests/unit/test_status_target.py -q`
  - `59 passed`
- `uv run python scripts/scan_envelope_tolerance.py --dir revit_mcp`
  - `ENVELOPE_SCAN_OK files=33`
- `uv run pytest tests/unit -q`
  - `6697 passed, 3 skipped`
- `uv run python tests/test_init_latency.py`
  - `INIT_LATENCY_S=0.998`
- `graphify update .` completed after code changes.

## Constraints observed

- No Revit process was started, reloaded, restarted, or contacted.
- No extension/payload publication, deployment, push, or tag was performed.
- The repository junction means enforcement takes effect locally only after a future full Revit restart; fleet rollout remains the user-run R5 payload-first procedure.

## Follow-up

Proceed with the remaining Phase 7 plans. The user-run live verification remains plan 07-14 and requires a full Revit close/reopen, never Reload.
