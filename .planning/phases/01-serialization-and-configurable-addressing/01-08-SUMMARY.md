---
phase: 01-serialization-and-configurable-addressing
plan: 08
subsystem: planning-record
tags: [gap-closure, planning, d27-b, a5-a, d27-c, backlog, debug-lead]
status: complete

requires:
  - phase: 01-04
    provides: "Bench record, measured cross-wiring verdicts, user decisions d27-b / a5-a / d27-c"
provides:
  - "SER-02 in REQUIREMENTS.md narrowed to /status/ (d27-b)"
  - "ROADMAP Phase 1 list line, Goal, SC2, SC5, SC6 aligned with d27-b, a5-a and d27-c"
  - "ROADMAP Phase 2 note: per-call Revit target selection (IDENT-01) and a lock keyed by target"
  - "ROADMAP ## Backlog with Phase 999.1 (d27-c) and its measured evidence; directory 999.1-*/.gitkeep"
  - "01-CONTEXT.md D-28..D-31 plus superseding notes, added lines only"
  - "01-02-SUMMARY.md appended superseding note for READ_ONLY_POST"
  - "param-write-rolls-back debug file: handler cross-wiring as a second candidate mechanism"
affects: [01-06, 01-07, phase-01-verification, phase-02]

requirements-completed: []
requirements: [SER-02, SER-05, IDENT-05]

actuals:
  tokens: 6900
  tasks: 3
  commits: 3
plan_head_before: 98b49389d5a5563981ae12dbd3c3198e8ce61937

tech-stack:
  added: []
  patterns:
    - "Superseded decisions keep their text and gain an indented 'Superseded <date> by D-NN' sub-bullet (added lines only)"
    - "Executed history (SUMMARY files) changes only by an appended note"

key-files:
  created:
    - .planning/phases/999.1-revit-side-fix-for-cross-process-overlap-in-pyrevit-shared-h/.gitkeep
    - .planning/debug/param-write-rolls-back.md (previously untracked, first committed here)
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - .planning/phases/01-serialization-and-configurable-addressing/01-CONTEXT.md
    - .planning/phases/01-serialization-and-configurable-addressing/01-02-SUMMARY.md

key-decisions:
  - "D-28 (d27-b, narrowed): every call through pyRevit's handler takes the lock, only GET /status/ is exempt; /model_info/ stays locked"
  - "D-29 (a5-a): the two-instance harness counts as SC5 evidence; no two-entry user model; per-call target selection moves to Phase 2 with one lock per target"
  - "D-30: d27-c is backlog item 999.1, not a phase"
  - "D-31: plan 01-05 superseded by 01-06, 01-07, 01-08"

duration: 15 min
completed: 2026-10-14
---

# Phase 1 Plan 08: Planning record after the 01-04 bench Summary

**The planning record now says what the 01-04 bench measured and the user decided: only `/status/` skips the queue (d27-b), the two-instance harness is the SC5 evidence (a5-a), and the Revit-side cross-process fix is backlog item 999.1 (d27-c) with its numbers, while Phase 2 is told its lock must be keyed by target.**

## Accomplishments

- **d27-b recorded through every layer (Task 1, tracer).** `01-CONTEXT.md` gained a revision note, D-28, and superseding sub-bullets under D-08 and D-27 and under the Phase Boundary read sentence. `REQUIREMENTS.md` SER-02 now reads "does not block `/status/`; every other call, reads included, waits its turn" and cites d27-b; the traceability row stays `Phase 1 | Pending`; the footer records the change. ROADMAP Phase 1 list line, Goal and success criterion 2 were rewritten to match. `01-02-SUMMARY.md` got an appended `## Superseding note (2026-10-07)`.
- **a5-a, d27-c and the per-target lock (Task 2).** `01-CONTEXT.md` gained D-29, D-30, D-31 and superseding sub-bullets under D-03, D-15, D-17, D-21, D-26 and the first Deferred Idea. ROADMAP SC5 names `tests/test_two_instance_targets.py` as the stand-in for the one-session two-entry check and keeps the staggered-start stop condition; SC6 names another MCP server process and points at 999.1 (d27-c). Phase 2 carries `**Carried from Phase 1 (01-04, decisions a5-a and d27-b):**` (per-call target selection recorded against IDENT-01, lock "keyed by target", `/status/` the only unlocked route). `## Backlog` sits after `## Progress` with `### Phase 999.1 ... (d27-c) (BACKLOG)`, the measured evidence (phase M `cross-wired-mutation`, phase R `cross-wired-read`, pyRevit 6.5.3, Revit 2024.3.30, reproduced twice, `/status/` unaffected) and a source pointer to `01-04-SUMMARY.md`. It is not in `## Phases`, not in the Progress table, and no phase depends on it.
- **Debug lead (Task 3).** `.planning/debug/param-write-rolls-back.md` gained a 2026-10-07 Evidence entry, a `blind_spots_addendum`, and a `second_candidate` block (hypothesis, confirming evidence, discriminating test, relation to the first hypothesis). The original hypothesis text, `falsification_test` and `status: awaiting_human_verify` are intact; only `updated:` changed. The file was untracked before this plan and is committed here by explicit path; the rest of `.planning/debug/` (none other present) was not touched.

## Task Commits

1. **Task 1: d27-b through CONTEXT, REQUIREMENTS, ROADMAP, 01-02 note** - `c39676c` (docs)
2. **Task 2: a5-a, backlog 999.1, Phase 2 per-target lock note** - `ac8cde3` (docs)
3. **Task 3: debug lead, second candidate mechanism** - `2b9b790` (docs)

## Verification

- All `<automated>` checks of the three tasks print their passing value. The Backlog evidence check initially printed 1 (all markers on one line); the source pointer was moved onto its own `**Source:**` line and the check now prints 2.
- `git diff --numstat 791a8d2` for `01-CONTEXT.md` (42 added, 0 deleted) and `01-02-SUMMARY.md` (additions only); `01-04-SUMMARY.md` prints nothing.
- `git status --porcelain -- bridge.py tools revit_mcp tests` is empty: no product code or test change.
- `roadmap.get-phase 1` still resolves Phase 1 and returns the new Goal.
- `git rev-list --count 98b4938..HEAD` = 3 at SUMMARY write time.

## Deviations from Plan

None - plan executed exactly as written. `phase.next-decimal 999` returned `999.1` and `generate-slug` returned `revit-side-fix-for-cross-process-overlap-in-pyrevit-shared-h`, both as the plan expected. One cosmetic touch: the Backlog `**Source:**` line is separate from `**Evidence:**` so the plan's own line-count check reaches 2.

## Requirements status

`SER-02`, `SER-05` and `IDENT-05` are NOT marked complete by this plan, so `requirements-completed` is empty. This plan only records their meaning; the behaviour (01-06), the docs (01-07) and phase verification close them. The plan itself says SER-02's traceability row stays `Phase 1 | Pending`.

## Issues Encountered

- Each `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` from git's post-commit housekeeping (a stale linked-worktree entry on Windows). All three commits were created; the message is not related to this plan.

## Known Stubs

None. The Backlog entry's single "TBD (promote with /gsd-review-backlog when ready)" plan line is the add-backlog template's intentional placeholder.

## Threat Flags

None - documentation only; T-01-23 is transferred to backlog item 999.1, T-01-28 mitigated by the append-only numstat checks, T-01-29 by the SC5 wording and the backstop truth below.

## Open items carried forward (backstop, not resolved here)

- **Cross-version Revit pair not benched.** `REVIT_PORT` addressing and staggered port allocation were shown on two Revit 2024.3.30 instances only; IDENT-05 / SC5 acceptance rests on a same-version pair. Phase verification should ask a human (`human_needed`).
- pyRevit 6.5.5 (RESEARCH A2), `/model_info/` overlap behaviour and simultaneous launch remain unmeasured (from `01-04-SUMMARY.md` follow-up item 7).
- Whether Phase 2 per-call target selection needs its own requirement ID is for the Phase 2 discussion (recorded against IDENT-01 for now).

## Next Phase Readiness

- Ready for 01-06 (d27-b in `bridge.py`) and then 01-07 (honest-scope docs, after 01-06 and 01-08).

## Self-Check: PASSED

- Created files FOUND: `.planning/phases/999.1-revit-side-fix-for-cross-process-overlap-in-pyrevit-shared-h/.gitkeep`, `.planning/debug/param-write-rolls-back.md`.
- Commits `c39676c`, `ac8cde3`, `2b9b790` FOUND in `git log`.

---
*Phase: 01-serialization-and-configurable-addressing*
*Completed: 2026-10-14*
