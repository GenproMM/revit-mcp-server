---
status: testing
phase: 05-live-secret-gate-and-integrity-enforcement
source: [05-VERIFICATION.md]
started: 2026-10-24T20:50:16Z
updated: 2026-10-24T20:50:16Z
---

## Current Test

number: 1
name: R3 pilot-first rollout (D-06 payload-first rehearsal on the pilot share)
expected: |
  Payload published to the pilot share first, scan_envelope_tolerance run on the main share's revit_mcp copy
  (deploy/RELEASE-RUNBOOK.md sections 5 and 6.3), pilot machine reports secret/integrity as in the live gate.
awaiting: user response

## Tests

### 1. R3 pilot-first rollout (D-06 rehearsal on the pilot share)
expected: Payload-first rehearsal on the pilot share; scan_envelope_tolerance on the main share's revit_mcp copy (RELEASE-RUNBOOK 5 and 6.3).
result: [pending]

### 2. D-10 second-publish probe with Revit open (on the pilot)
expected: A second publish while Revit is open behaves as D-10 specifies (RELEASE-RUNBOOK).
result: [pending]

### 3. First fleet machine after publish to the main share
expected: get_revit_status says "both halves hold the same secret".
result: [pending]

### 4. R3 release checkpoint decision
expected: Decision recorded in .planning/RELEASES.md Ledger: prepare now / defer / skip (publish-extension.cmd, build-payload.cmd, push and tag are run only by the user).
result: [pending]

### 5. WR-01 decision: /model_worksets/ open read takes a caller-supplied file_path
expected: Decide keep open vs gate it (UNC/SMB coercion and file-existence oracle without the secret; see 05-REVIEW.md WR-01). Not a roadmap-criteria gap.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
