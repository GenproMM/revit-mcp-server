---
status: complete
phase: 01-serialization-and-configurable-addressing
source: [01-VERIFICATION.md]
started: 2026-10-14T08:30:38Z
updated: 2026-10-14T10:09:21Z
---

## Current Test

[testing complete]

## Tests

### 1. Repeat the overlap probe on the fleet's pyRevit 6.5.5 (scripts/probe_handler_overlap.py --port 48884) against one live Revit
expected: Same verdicts as 6.5.3; /status/ still safe to leave unlocked
result: pass

### 2. Measure GET /model_info/ under overlap with a held mutation on a live Revit
expected: A recorded verdict; /model_info/ stays locked until measured and a user decision adds it to UNLOCKED_GET
result: pass

### 3. Simultaneous launch of two Revit instances, then Get-NetTCPConnection -LocalPort 48884,48885 -State Listen and /routes/sisters
expected: Record which ports each PID received; confirms or corrects the docs' "may collide on 48884" wording
result: pass

### 4. IDENT-05 / SC5 beyond two Revit 2024.3.30 instances: run tests/test_two_instance_targets.py (--ports 48884,48885) on a cross-version pair and on pyRevit 6.5.5
expected: TWO_INSTANCE_OK; each entry reports its own host:port and document_title; one listener per port with different PIDs
result: pass

### 5. Read deploy/USER-GUIDE.md (Russian) for over-claims about serialization or two-Revit use
expected: No sentence promises that sessions or Revit instances are protected from each other; the cross-session warning (~lines 423-433) reads correctly
result: pass

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
