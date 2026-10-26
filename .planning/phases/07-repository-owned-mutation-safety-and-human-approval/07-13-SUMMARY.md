---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "13"
subsystem: operator-bench-and-offline-evidence-classifier
status: complete
requirements-completed: []
---

# Phase 7 Plan 13 Summary

## Outcome

Delivered the operator-run Phase 7 acceptance bench and verified its implementation offline. This completes the bench-delivery plan only: no live acceptance is claimed, SAFE-20 remains pending live evidence, and Phase 7 is not complete.

Scope authorized by the user: finish offline checks and commit the bench; do not start Revit, Routes or Hermes, run live preflight/direct/ingest, or access a share. The user subsequently authorized fixes confined to the bench and its unit tests.

## Changes

- `tests/test_phase7_live_bench.py` is a standalone CPython script with `template`, `preflight`, `direct`, `ingest` and `classify` commands, lazy runtime imports and no import-time I/O. It documents the disposable non-workshared model, full Revit restart, no-save procedure, H1-H5 operator scenarios and unverified H6 gateway channel.
- The classifier requires audit JSONL evidence correlated by unique call ID, expected tool and route. Pasted approval/outcome assertions cannot replace audit fields. H4 requires two distinct confirmed calls with identical arguments; H5 requires a successful approved move with audit vector X equal to 12.5 mm.
- Preflight correlates a canonical session UUID, listener PID and actual port, requires permit protocol 1 and records Revit version and a local policy snapshot. Network-hosted policy is refused before the first HTTP request.
- Direct steps use the real permit minting/wire helpers for S6 missing permit, S5a replay, S5b argument mismatch and S5c route mismatch. The HTTP client targets loopback with environment proxies disabled; the endpoint allow-list is limited to status, list_levels, create_level and create_grid.
- Output is exclusively reserved outside the repository. The conservative POST-attempt count is flushed and fsynced before transport receives a write; a later read/transport failure preserves a STOP record and the nonzero one-shot count. Complete evidence requires exactly five direct POST attempts.
- Response evidence retains only allow-listed verdicts/statuses, not raw response bodies, secret envelopes, permit MACs or exception messages. Local-path guards reject UNC/network drives and Windows reparse points before following them; policy, secret and audit-file paths are guarded as well.
- Level absence requires HTTP 200, the production `levels`/`total_levels` schema and exact name comparison, rather than treating malformed data as absence.
- `tests/unit/test_phase7_live_bench.py` provides 46 offline cases covering positive synthetic evidence, refusals, audit correlation, secret scans, CLI classification, fake-backed preflight/direct logic, real permit verification against fake transport, persistence after failure and local-policy isolation.

## Verification

Checks used the existing isolated `phase7-test-venv`; the shared repository `.venv` was not synchronized or changed.

- Focused bench suite: **46 passed in 0.46s**, exit 0; final repeat after the H4 procedure clarification: **46 passed in 2.60s**, exit 0.
- Full unit suite through child cmd at code page 866: **6923 passed, 3 skipped in 123.95s**, exit 0. Final repeat after the H4 operator-procedure clarification: **6923 passed, 3 skipped in 120.79s**, exit 0.
- Cold-start gate: **INIT_LATENCY_S=0.975**, exit 0; final repeat **INIT_LATENCY_S=1.153**, exit 0, both below the 2.0s threshold.
- Scoped staged whitespace check (`git diff --cached --check`) passed; path-only commit dry-run selected exactly the two bench files and this summary.
- Both Python files parsed successfully with `ast.parse`, use LF and UTF-8 without BOM; the standalone script has no pytest-style `test_` functions.
- Import plus the offline `template` command produced the evidence JSON and exited 0 without runtime/secret/policy loading.
- `graphify update .` completed using AST extraction. Generated graph files are deliberately excluded from the bench commit.

All preflight/direct/ingest implementation exercises were fake-backed unit calls with synthetic secrets and scratch files. No such CLI command was run against a real system. No Revit, Routes, Hermes, share, real shared-secret read, deployment, push or tag was used.

## Deviations and evidence limits

- Initial passing tests did not expose missing-audit and wrong-tool/route false positives. The controller reproduced both with synthetic records; the authorized offline fixes now reject them and add regression coverage.
- The implementation review also corrected the level-list contract to production `total_levels`, strengthened PID/port identity checks, removed global policy-reader monkeypatching and persisted the one-shot marker before POST.
- The policy snapshot is freshly loaded from a guarded, isolated local policy store. It does not prove the cached policy of another running MCP process. A network-hosted operator policy yields STOP rather than share access or silent base-policy fallback.
- Audit and local operator observations are evidence inputs, not cryptographic attestation of Hermes UI behavior or model effects. Actual client rendering, confirmation windows, IronPython HMAC/float behavior, company FOP acceptance and mutation effects remain unverified live.
- The DSH hub was unreachable; no DSH worker ran and no standalone fallback was used. A GSD agent assisted with scoped review/implementation; the controller inspected the files, corrected defects, ran full checks and owns the commit.
- Existing dirty/staged planning, Obsidian, scripts and generated graph changes are not part of this delivery. Shared ROADMAP, STATE, REQUIREMENTS and VALIDATION files were not rewritten or included; this summary is the scoped delivery record.

## Next

Stop here. Plan 07-14 remains the separately authorized human/live checkpoint. Do not infer permission to run the bench, restart Revit, access the deployment share, publish a release or mark SAFE-20 complete from this offline delivery.
