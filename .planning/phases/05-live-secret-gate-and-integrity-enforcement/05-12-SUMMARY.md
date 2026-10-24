---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 12
subsystem: phase-5-live-gate
status: complete
---

# Plan 05-12 Summary

## Completed

- Added the lazy, one-shot `run` command to the standalone Phase 5 live-gate procedure. It validates its evidence-output path and repository/secret prerequisites before HTTP activity, performs read-only listener/status/document preflight, records the exact step evidence, and classifies the resulting record.
- Added all three live stages: `match` (7 POSTs), `corrupt` (4 POSTs), and `cleanup` (1 POST). Direct calls use the text/plain wire contract; tool calls register the production tools against the injected bridge seam and capture model-visible text plus raw replies.
- POST accounting now occurs immediately before direct and tool bridge calls. Each stage remains consumed after any POST attempt, including an exception-producing request; a preflight stop persists an evidence record with `posts_sent: 0` and explicit rerun guidance.
- Added `corrupt --module`, `restore [--module]`, and `scan-secret FILE...` helpers. Corruption is limited to one tracked non-private `revit_mcp/*.py` path and its temporary probe; restore removes only Phase 5 temporary integrity artifacts and optionally checks out the named module. Secret scanning obtains the value only via `bridge.load_secret()` and never prints it.
- Expanded offline tests with fake direct HTTP/bridge seams and temporary Git repositories. The tests cover stage success paths, preflight/refusal behavior, POST counting after a raised call, text/plain/envelope shapes, bridge secret-cache reset, LF/CRLF corruption, restore failures, and scan-secret output tokens.

## Verification

- `uv run pytest tests/unit/test_phase5_live_gate.py -q` — **73 passed**.
- `uv run python -m py_compile tests/test_phase5_live_gate.py tests/unit/test_phase5_live_gate.py` — passed.
- `git diff --check -- tests/test_phase5_live_gate.py tests/unit/test_phase5_live_gate.py` — passed (Git emitted pre-existing working-copy LF→CRLF warnings only).
- `uv run pytest tests/unit -q` — failed in 8 pre-existing Windows scratch-share publish/rollback cases in `tests/unit/test_secret_pipeline.py`; `cmd.exe` mis-parsed `deploy/config.cmd`, beginning with `'ONCE' is not recognized`. The focused Phase 5 suite passed and this plan did not alter the deployment scripts.

## Safety boundary

- No live `run`, `corrupt`, `restore`, or `scan-secret` command was executed against the repository/Revit.
- No Revit process, payload, extension publication, rollback, tag, or push was touched.
- Plans 05-13 through 05-15 remain explicit human/live checkpoints and must not be started without approval.
