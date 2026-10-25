---
phase: 06-structured-audit-log-of-true-outcomes
plan: 07
subsystem: audit
tags: [audit, live-gate, one-shot, rollback, two-instance, validation]

requires:
  - phase: 06-structured-audit-log-of-true-outcomes
    provides: the live-gate instrument tests/test_phase6_live_audit.py (06-06) and the audit log it judges (06-01..06-05)
provides:
  - live evidence for ROADMAP criterion 2 (a real rollback and a real partial batch recorded truthfully) and criterion 5 (two Revit instances, two server processes, separate uncorrupted audit files), plus a live look at criteria 1 and 7
  - the verdicts, POSTS_SENT values, dates and record paths in 06-VALIDATION.md
affects: [06 verification]

plan_head_before: a8afcfb
actuals:
  tokens: 30000
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns:
    - "Rollback trigger for live rehearsal: doc.PostFailure(DB.FailureMessage(DB.BuiltInFailures.GeneralFailures.ValueOutOfRange)) from execute_revit_code answers a real rolled_back 409 and changes nothing"

key-files:
  created: []
  modified:
    - .planning/phases/06-structured-audit-log-of-true-outcomes/06-VALIDATION.md

key-decisions:
  - "The gate was run by the assistant on the user's explicit instruction, which replaced the plan's human-run rule for this run; the one-shot and scratch-model rules were kept"
  - "Instance 1 kept its unsaved scratch copy open between Part A and Part B instead of being closed and reopened"

requirements-completed: [AUDIT-01, AUDIT-03, AUDIT-06, AUDIT-08]

coverage:
  - id: D1
    description: "Pre-gate green without Revit: unit suite, cold start, script template and --help, no _manifest.json, dev secret file present, no revit_mcp/ change since e81b68f"
    requirement: AUDIT-01
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit -q (6297 passed, 3 skipped); INIT_LATENCY_S=0.761"
        status: pass
  - id: D2
    description: "Live single-Revit run: rolled_back (409) and partial recorded truthfully, a successful set_parameter entry, secret absent from every audit file"
    requirement: AUDIT-03
    verification:
      - kind: manual_procedural
        ref: "tests/test_phase6_live_audit.py run-single: PHASE6_AUDIT_OK, POSTS_SENT=3, SECRET_OCCURRENCES=0; classify re-judged OK"
        status: pass
  - id: D3
    description: "Live two-Revit run: two server processes left two separate, uncorrupted audit files naming the right Revit processes"
    requirement: AUDIT-06
    verification:
      - kind: manual_procedural
        ref: "tests/test_phase6_live_audit.py run-dual: PHASE6_AUDIT_OK, POSTS_SENT=20, SECRET_OCCURRENCES=0; classify re-judged OK"
        status: pass
---

# Phase 06 Plan 07: Live audit gate Summary

**Both live stages passed once each: a real rollback and a real partial batch were recorded as `rolled_back` and `partial`, and two Revit instances mutated through two server processes left two separate, uncorrupted audit files.**

## Accomplishments

- Pre-gate (no Revit): 6297 unit tests passed, 3 skipped; `INIT_LATENCY_S=0.761`; `template` and `--help` exit 0; no `_manifest.json`; `revit_mcp/_bridge_secret` present (existence only); `git diff e81b68f..HEAD -- revit_mcp/` empty.
- Rehearsal: after enumerating built-in failure definitions, `GeneralFailures.ValueOutOfRange` (Error severity) posted through `doc.PostFailure` gave `REHEARSAL_ROLLED_BACK` (409, `RolledBack`) on the first try. Research assumption A3 is confirmed.
- run-single: `PHASE6_AUDIT_OK`, `POSTS_SENT=3`, `SECRET_OCCURRENCES=0`. The audit file holds `rolled_back` (409), `partial` and a successful `set_parameter`, all naming one Revit process.
- run-dual: `PHASE6_AUDIT_OK`, `POSTS_SENT=20`, `SECRET_OCCURRENCES=0`. Two files, one per server process, 10 `set_parameter` successes each, naming two Revit processes.
- `classify` on both saved records agreed. Verdicts, counts, dates and record paths are in 06-VALIDATION.md (commit d8ba46b); no PIDs or session tokens were written.

## Deviations

- The plan marked Task 2 as human-run. The user explicitly told the assistant to start Revit and run the gate; the one-shot, scratch-copy, non-workshared and never-saved rules were kept. The user's own project model was never opened. The user closed their running Revit first (a graceful close stalled on a save prompt and was not forced).
- Instance 1 kept its unsaved scratch copy between Part A and Part B instead of a close-and-reopen.
- The second Revit was launched with `Start-Process` because `start_revit` refuses while one answers. An `open_model` call sent while it was still initializing timed out without effect, and was repeated once Revit showed the Home screen with no document.

## Limitations

- ROADMAP criterion 3 (one call_id across several bridge calls) stays proven offline with a synthetic multi-call tool, since no shipped tool makes more than one bridge call (06-04).
- The edge-probe items for AUDIT-05 and AUDIT-06, and whether the model follows the `user_request` wording, remain for human judgment at verification.

## Self-Check: PASSED

- 06-VALIDATION.md contains `PHASE6_AUDIT_` verdicts for both stages; `git show --stat HEAD` for d8ba46b lists only that file.
- Both scratch Revit processes were stopped by exact PID; no Revit process and no listener on 48884/48885 remained.
