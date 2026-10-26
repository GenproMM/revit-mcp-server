---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "09"
subsystem: approval-and-audit
status: complete
---

# Phase 7 Plan 09 Summary

## Outcome

The MCP confirmation channel now serializes one human-confirmation window per event loop and records the policy decision separately from Revit's actual outcome. Every accepted mutation remains a single send with a one-time permit; every policy refusal is a durable, not-sent audit record.

## Changes

- Added `approval._window_lock()` keyed by the current running event loop.
  - Confirm windows serialize within an MCP server process.
  - Each opening gets its own six-hex operation code.
  - One policy timeout covers both waiting for an earlier window and elicitation.
  - Waiting occurs before the bridge's per-target Revit lock.
- Retained action-only consent:
  - request arguments such as `approved=true` do not grant consent;
  - elicitation accept content is ignored;
  - every accept covers one call only and mints a new permit.
- Completed confirmation result handling:
  - unavailable, declined, cancelled, client-error, timeout, and cancellation are distinct;
  - cancellation propagates rather than being turned into approval;
  - cancellation and timeout user text retains `подтверждение не получено`.
- Extended audit schema and outcomes with `denied`, `expired`, and `rejected_permit`.
  - Policy refusal entries are not-sent and include policy source/hash, decision, approval, wait duration, reasons, and ordinary shaped request data.
  - Permitted sends carry those fields plus the first eight nonce characters.
  - A Revit 403 permit verdict is recorded as `rejected_permit`; approved calls retain Revit's own `success` or `rolled_back` outcome.
- Added channel, unlocked-wait, and decision-audit suites, plus policy and schema regression coverage.

## Verification

All checks used an isolated CPython environment because the shared repository `.venv` could not be updated while files were locked.

- Focused channel / lock / tracer suite: `27 passed`.
- Focused audit suite: `188 passed`.
- Full Revit-free suite: `6714 passed, 3 skipped`.
- Cold start: `INIT_LATENCY_S=0.949`.
- `graphify update .` completed after source changes.

## Constraints observed

- No live Revit route was called and no Revit process was started, reloaded, or restarted.
- No extension or payload was built, deployed, published, pushed, tagged, or released.
- Generated graph files were refreshed as required but intentionally excluded from commits because they are unrelated generated working-tree changes.

## Commits

- `a0156ce feat(07-09): serialize confirmation windows`
- `adf1f28 feat(07-09): audit approval decisions`

## Follow-up

Continue with Phase 7 Plan 10 (mutation preflight). Live verification remains Plan 07-14 and requires a future full Revit close/reopen, never Reload.
