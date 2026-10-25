---
status: testing
phase: 06-structured-audit-log-of-true-outcomes
source: [06-VERIFICATION.md]
started: 2026-10-25T11:44:02Z
updated: 2026-10-25T11:44:02Z
---

## Current Test

number: 1
name: Criterion 3 (one call_id across several bridge calls) accepted on offline evidence
expected: |
  Accept the offline proof (a synthetic read + mutation + image tool through the real wrapper and bridge gives three ordered entries
  with one call_id equal to the Audit line id, also present in the POST envelope), or require a live proof once a real tool makes
  more than one bridge call. No shipped tool does today.
awaiting: user response

## Tests

### 1. Criterion 3 on offline evidence
expected: accept the synthetic multi-call proof, or defer until a real multi-call tool exists
result: [pending]

### 2. AUDIT-05 and AUDIT-06 edge probes
expected: accept the stdio-session test, the two-subprocess-writer test and the live run-dual as sufficient, or name a missing probe
result: [pending]

### 3. user_request compliance by the model
expected: in a real client session, a mutation after a user message such as "да" records the last substantive request in user_request (user_request_source "assistant", unverified by design)
result: [pending]

### 4. Review warnings WR-01..WR-03 (lone surrogate drops an entry; failed read audited as success; NaN/Infinity in the log)
expected: accept as known limitations, or add three small fixes in audit.py with tests before the R4 release checkpoint (patches are in 06-REVIEW.md)
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
