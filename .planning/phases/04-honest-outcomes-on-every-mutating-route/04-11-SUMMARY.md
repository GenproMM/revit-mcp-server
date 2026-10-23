---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 11
subsystem: testing
tags: [live-gate, one-shot, outcome-schema, TransactionStatus]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "04-10 one-shot instrument; 04-01..04-09 migrated routes, docstrings and static rule"
provides:
  - "Live evidence for ROADMAP criteria 1, 2 and 4: PHASE4_OUTCOMES_OK recorded in 04-VALIDATION.md"
affects: []

plan_head_before: 2c5ca0e
actuals:
  tasks: 2
  commits: 1

key-files:
  created: []
  modified:
    - .planning/phases/04-honest-outcomes-on-every-mutating-route/04-VALIDATION.md

key-decisions:
  - "The live run was executed by the controller session at the operator's explicit request (the plan's default was operator-run). Conditions were checked first: one listener on 48884, one Revit process started after the last revit_mcp/ commit, one scratch document, SCRATCH folder empty and outside the repo. The model was not saved."
  - "The operator supplied no parameter name; the Russian built-in 'Комментарии' was used. The script's read-only preflight confirmed it writable before any POST."
---

# Phase 04 Plan 11: Live outcome gate Summary

One live run of the D-11 set on a freshly restarted Revit 2024 answered `PHASE4_OUTCOMES_OK` with `POSTS_SENT=5`. The one-shot gate is consumed and was not repeated.

## Observed

| Step | Route | Result |
|------|-------|--------|
| s1 | modify_element | 200 success, `Committed` |
| s2 | tag_elements `[valid, 999999999]` | 200 `partial`, valid id succeeded, 999999999 `Element not found` failed |
| s3 | tag_elements `[999999999]` | `Error: 422`, status `failed` |
| s4 | export_ifc | `Committed`, path in `succeeded`, 57 KB file exists |
| s5 | delete_elements of the s2 tag | 200 success, `Committed` |

Record on the operator's machine: `C:/Users/Admin/Documents/revit-mcp-test-phase3/RAW.json`. Verdict, date, listener check and record path are in `04-VALIDATION.md`; PIDs and session tokens were deliberately left out.

## Follow-ups for the operator

- Close the scratch model **without saving**: wall 286691 carries the in-memory comment `phase4 live`.
- Rollback honesty is not exercised live (out of scope); it stays covered by the unit route worlds.
- Open question carried from 04-04 (assumption A3): the IFC exporter's own model changes stay committed with the export transaction. Autodesk's sample rolls them back instead.
- 04-06 live assumption: PNG/JPG export expects `<export dir>/<view name>.png|.jpg`; real Revit may name it differently, which now answers 422 instead of a false success. Not part of this gate's route set.

## Deviations

None to the contract. Task 1 was run by the controller on explicit instruction instead of being handed back to the operator.
