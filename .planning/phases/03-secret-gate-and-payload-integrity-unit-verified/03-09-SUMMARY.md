---
phase: 03-secret-gate-and-payload-integrity-unit-verified
plan: 09
subsystem: integrity
tags: [integrity, trust, share-drop, WR-01, gap-closure, ironpython-3.4, unit-tests]

requires:
  - phase: 03-secret-gate-and-payload-integrity-unit-verified
    provides: "integrity.check_integrity / trust.evaluate_integrity (plans 03-04, 03-05), reader hardening tests (03-06)"
provides:
  - "A share that drops mid-check is unverifiable/absence_unconfirmed, never verified_mismatch (WR-01)"
  - "integrity.unconfirmed_absences: manifest re-read first, then each absent entry re-read"
  - "trust.REASON_ABSENCE_UNCONFIRMED and the optional observation key 'unconfirmed'"
affects: [phase-05-integrity-wiring, 03-UAT]

actuals:
  tokens: 7100
  tasks: 2
  commits: 2

plan_head_before: 2943035ed4b7ed534dbeffe3ecb268841dc5a3a2
commits: 2

tech-stack:
  added: []
  patterns:
    - "Corroborate an observed absence before it counts as missing (manifest re-read first, absent entries second)"
    - "Decision stays in the pure trust.evaluate_integrity; the reader only reports observations"

key-files:
  created: []
  modified:
    - revit_mcp/integrity.py
    - revit_mcp/trust.py
    - tests/unit/test_integrity_reader.py
    - tests/unit/test_trust_integrity.py
    - tests/unit/test_trust_dialect.py

key-decisions:
  - "D-13 reason list extended by one code, absence_unconfirmed, under the unverifiable state (user decision; the fold-into-read_error fallback was rejected)"
  - "Corroboration order: manifest re-read first, absent entries second, no retries, no sleeps, no extra I/O on a matching tree"

patterns-established:
  - "share-outage test harness: _share_outage(monkeypatch, make_error, failing_open, failing_listdir, record=None) over the existing _guards"

requirements-completed: [INTG-07, INTG-02, INTG-03, INTG-08]

coverage:
  - id: D1
    description: "A share that drops after _manifest.json was read (ENOENT, winerror 53, winerror 67) is unverifiable/absence_unconfirmed with empty lists and an unchanged tree"
    requirement: "INTG-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_share_drop_after_manifest_read_is_unverifiable_absence_unconfirmed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Mixed (partial read), blip (recovers before corroboration) and republish-between-reads outages are unverifiable, not mismatch"
    requirement: "INTG-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_share_drop_mid_scan_after_some_files_were_read_is_unverifiable"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_share_blip_that_recovers_before_corroboration_is_unverifiable"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_share_drop_manifest_changed_between_reads_is_unverifiable"
        status: pass
    human_judgment: false
  - id: D3
    description: "A real deletion on a reachable tree is still verified_mismatch; the corroboration provably ran; a matching tree costs no extra I/O"
    requirement: "INTG-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_genuine_deletion_is_confirmed_by_a_second_read"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_matching_tree_reads_the_manifest_once"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_unreachable_enoent_on_a_listed_file_is_missing"
        status: pass
    human_judgment: false
  - id: D4
    description: "trust.evaluate_integrity maps a non-empty unconfirmed list to absence_unconfirmed with the documented precedence; the 423 body is unchanged"
    requirement: "INTG-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_integrity.py -k unconfirmed (11 items)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Both modules keep the IronPython 3.4 dialect, the import allow-lists and the read-only rule; engine rows extended"
    requirement: "INTG-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_dialect.py#test_ironpython3_engine_check_integrity_confirms_a_deleted_file"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_never_writes_ast_scan_finds_no_write_call"
        status: pass
    human_judgment: false
  - id: D6
    description: "IronPython 3.4 errno for a dropped network path (and a live share drop in pyRevit's engine) is not observed live; verdict rests on reasoning plus CPython unit tests"
    verification: []
    human_judgment: true
    rationale: "Only CPython on Windows was observed; no live gate was planned (plan stays autonomous)"

duration: 22min
completed: 2026-10-23
status: complete
---

# Phase 03 Plan 09: WR-01 share-drop corroboration Summary

**An absence the reader cannot confirm (manifest re-read first, then each absent entry) is now unverifiable/absence_unconfirmed instead of a false verified_mismatch, closing WR-01 without masking a real deletion.**

## Performance

- **Duration:** about 22 min (start time was not captured at the start of the run; approximate)
- **Completed:** 2026-10-23T12:31Z (last state verb)
- **Tasks:** 2
- **Files modified:** 5 (2 source, 3 test)

## Accomplishments

- WR-01 closed: a dropped share can no longer be cached by Phase 5 as tampering. The same repro as the scratch probe that gave `verified_mismatch None 5` before the fix gives `unverifiable absence_unconfirmed 0` after it.
- `revit_mcp/trust.py`: `REASON_ABSENCE_UNCONFIRMED = "absence_unconfirmed"`; `evaluate_integrity` accepts the optional list `unconfirmed`. Precedence: manifest_missing, manifest_unreadable, read_error (shape, a non-list `unconfirmed`, or unreadable), absence_unconfirmed, then mismatch or match. `integrity_failure`, `mismatch_files` and `_result` are unchanged.
- `revit_mcp/integrity.py`: new `_list_names`, `observe_tree` returns a fourth key `absent`, new `unconfirmed_absences(root, manifest, absent)`, and `check_integrity` sets `observed["unconfirmed"]` only when there are absent entries. No new import, no new `open(` call, `_read_bytes` signature unchanged.
- 25 new test items (4667 -> 4692 passed in the whole suite).

## Task Commits

1. **Task 1 (tracer, TDD): reproduce WR-01, corroborate, map to absence_unconfirmed** - `f54d3cd` (fix)
2. **Task 2: harden the corroboration (mixed, blip, republish, I/O counts, precedence, no leakage, engine rows)** - `af65ad2` (test)

**Plan metadata:** the docs(03-09) SUMMARY commit follows this file.

Task 1 acceptance checks run while HEAD was `f54d3cd`:
`git show --numstat` of the two test files: `71 0` and `19 0` (additions only); `git show --stat` listed exactly integrity.py, trust.py, test_integrity_reader.py, test_trust_integrity.py (test_integrity_e2e.py untouched).

## Baseline, red and final output

Baseline before the first edit (Step 0):

- `uv run pytest tests/unit -q`: `4667 passed, 3 skipped in 26.62s`; the four-file subset (reader, trust_integrity, e2e, dialect): `188 passed`.
- `git status --porcelain -- bridge.py startup.py main.py tools deploy revit_mcp`: ` M deploy/README.md`, ` M deploy/SETUP-RUNBOOK.md`, ` M deploy/USER-GUIDE.md`, ` M deploy/install.cmd`, ` M deploy/publish-extension.cmd`, ` M startup.py`, `?? deploy/check_routes_config.py` (all foreign, none touched).
- `git hash-object startup.py`: `85de483307be925517bee2ce3f109e5d6538560c`.
- The five plan files were clean before the first edit (precondition met).

RED (Task 1, before the fix, not committed):

```
FAILED test_integrity_reader.py::test_share_drop_after_manifest_read_is_unverifiable_absence_unconfirmed[enoent]
FAILED ...[winerror53]
FAILED ...[winerror67]
FAILED test_trust_integrity.py::test_absence_unconfirmed_reason_value_is_pinned
FAILED test_trust_integrity.py::test_unverifiable_unconfirmed_absence_is_absence_unconfirmed
5 failed, 111 deselected in 0.41s
```

The share-drop items failed with `{'state': 'verified_mismatch', 'reason': None, 'modified': [], 'missing': ['extension.json', 'revit_mcp/__init__.py', 'revit_mcp/alpha.py', 'revit_mcp/beta.py', 'startup.py'], ...}`. The trust-value test failed on `AttributeError` for `REASON_ABSENCE_UNCONFIRMED`; the trust-mapping test failed with `'verified_mismatch' == 'unverifiable'` because the key was not yet read.

GREEN (after the fix):

- `-k "share_drop or absence_unconfirmed"`: `5 passed`.
- reader + trust_integrity + e2e + dialect: `193 passed` after Task 1, `213 passed` after Task 2.
- The three pinned real-deletion tests (`test_unreachable_enoent_on_a_listed_file_is_missing`, `test_unreachable_absent_scope_directory_lists_its_files_as_missing`, `test_edited_deleted_and_added_files_are_named`), source unchanged: `3 passed`.
- `-k "dialect or never_writes or determinism"`: `83 passed`.
- Task 2 acceptance: reader `-k` selector `13 passed`; trust `-k unconfirmed` `11 passed`; the three dialect items `3 passed`; `grep -n '"unverifiable") == 8'` prints one line; `DEV_JUNCTION_OK unverifiable manifest_missing`.
- Final `uv run pytest tests/unit -q`: `4692 passed, 3 skipped in 26.06s` (0 failed, 0 errors; baseline was 4667 passed).
- After the final code commit, `git status --porcelain -- bridge.py startup.py main.py tools deploy revit_mcp` equals the Step 0 output exactly, and `git hash-object startup.py` is still `85de483307be925517bee2ce3f109e5d6538560c`.

Mutation check (observed, in-process only, nothing written): replacing `unconfirmed_absences` with a version that skips the manifest re-read made 10 of the share-drop and real-deletion items fail, so the manifest-first order is pinned by the tests.

## New symbols and tests

Source: `trust.REASON_ABSENCE_UNCONFIRMED`; `integrity._list_names`, `integrity.unconfirmed_absences`; the `absent` key of `integrity.observe_tree`; the optional `unconfirmed` key of the observation.

`tests/unit/test_integrity_reader.py`: helpers `_network_enoent`, `SHARE_DROP`, `_share_outage`, `LISTED`, `LISTED_MANIFEST`, `_normalized`, `_tree_path`; tests `test_share_drop_after_manifest_read_is_unverifiable_absence_unconfirmed` (3), `test_share_drop_mid_scan_after_some_files_were_read_is_unverifiable` (3), `test_share_blip_that_recovers_before_corroboration_is_unverifiable`, `test_share_drop_manifest_changed_between_reads_is_unverifiable`, `test_genuine_deletion_is_confirmed_by_a_second_read`, `test_matching_tree_reads_the_manifest_once`, `test_observe_tree_reports_absent_files_and_scope`, `test_unverifiable_when_the_corroboration_itself_raises`, `test_share_drop_result_carries_no_path_or_error_text`.

`tests/unit/test_trust_integrity.py`: `test_absence_unconfirmed_reason_value_is_pinned`, `test_unverifiable_unconfirmed_absence_is_absence_unconfirmed`, `test_unverifiable_unconfirmed_absence_wins_over_a_modified_file`, `test_unverifiable_read_error_wins_over_an_unconfirmed_absence`, `test_unconfirmed_empty_or_absent_key_changes_nothing`, `test_unverifiable_unconfirmed_of_the_wrong_type_is_read_error` (4), `test_unverifiable_property_unconfirmed_never_mismatch` (15 observations), `test_integrity_423_is_never_built_from_an_unconfirmed_result`.

`tests/unit/test_trust_dialect.py`: two new `_integrity_rows` rows, counts 1 / 4 / 8 plus the `absence_unconfirmed` reason assertion, and `test_ironpython3_engine_check_integrity_confirms_a_deleted_file`. The only existing lines changed are the two count assertions the plan mandates (3 -> 4, 7 -> 8); nothing was loosened.

## Decisions Made

- **D-13 reason list extended by one code.** D-13 listed three `unverifiable` reasons (manifest_missing, manifest_unreadable, read_error). This plan adds `absence_unconfirmed` under the same state. The three states, the never-writes rule and the D-15 423 body are unchanged, and the user confirmed the new code. **Fallback, rejected by the user and recorded only for reversibility:** a one-line change in `evaluate_integrity` mapping a non-empty `unconfirmed` to `read_error`. Nothing outside these two modules and their tests reads the reason yet (Phase 5 is not wired).
- **Corroboration order.** Manifest re-read first (must parse equal to the first read), then each absent entry. Whatever the timing of a single outage, either the manifest re-read fails or the absent files read successfully the second time; both leave the absence unconfirmed. A real deletion on a reachable tree reproduces and stays a mismatch.

## Residuals (recorded, not closed)

1. **IronPython errno mapping: not observed live.** It is unknown which errno IronPython 3.4, in pyRevit's routes engine, raises for a dropped UNC share. Only CPython on Windows was observed: ENOENT for `open` and for `os.listdir`. By construction the verdict is `unverifiable` either way: an ENOENT goes through the corroboration, and any other errno or a non-OSError is `read_error`. This is reasoning backed by CPython unit tests, not a live observation, and no live gate was run or planned. The same wording is in the `unconfirmed_absences` docstring in `revit_mcp/integrity.py`.
2. **Two-outage window.** Two separate outages bracketing the manifest re-read (one covering the first scan, one covering the re-read of the absent entries, with the share reachable for the manifest re-read in between) can still produce a false mismatch.
3. **Revit restart after editing.** `revit_mcp/integrity.py` and `revit_mcp/trust.py` changed. Any later live test of them needs Revit fully closed and reopened; pyRevit Reload is not safe (CLAUDE.md). The repository is junctioned as the deployed extension, so the edits are live at the next Revit start. No live test was run here.

## Requirements

INTG-02, INTG-03, INTG-07 and INTG-08 were Complete before this plan and stay Complete. The plan corrects the implementation behind them; it adds and reopens no requirement. 03-UAT.md test 1 can be resolved as "fixed in 03-09" (the orchestrator updates tracking files).

## Deviations from Plan

None - plan executed exactly as written. (The Task 2 SUMMARY step says the orchestrator commits the SUMMARY; per the dispatch brief the executor commits SUMMARY.md alone as `docs(03-09): complete plan summary`.)

**Total deviations:** 0.

## Issues Encountered

None. Every new test passed on its first run after the implementation; the manifest-first ordering was confirmed non-vacuous by the in-process mutation above. `git commit` printed the harmless `failed to delete '.git/worktrees/hot-cirrus'` error both times; the commits were verified with `git log`.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or file-access pattern: every new read goes through `_read_bytes` or `_list_names`, and the AST write scan and literal-`rb` test stay green.

## State verbs run (results left uncommitted)

- `state.record-metric --phase 03 --plan 09 --duration "22 min" --tasks 2 --files 5`: `recorded: true`.
- `state.record-session --stopped-at "Completed 03-09-PLAN.md" --resume-file None`: updated Last session, Stopped At.
- `roadmap.update-plan-progress 03`: `plan_count 9, summary_count 8, status "In Progress"` (run before this SUMMARY existed, so it counted 8 summaries; it reads 9/9 once this file is on disk, and the orchestrator reconciles).
- `state.advance-plan`, `state.update-progress`, `requirements.mark-complete` were deliberately not run (gap-closure 9th plan; requirements already Complete). STATE.md, ROADMAP.md and REQUIREMENTS.md are not committed by this plan.

## Self-Check: PASSED

- FOUND: revit_mcp/integrity.py (`def unconfirmed_absences`), revit_mcp/trust.py (`REASON_ABSENCE_UNCONFIRMED = "absence_unconfirmed"`), the three test files.
- FOUND commits: f54d3cd, af65ad2 (`git rev-list --count` from the ledger base `2943035` = 2).
- `uv run pytest tests/unit -q`: 4692 passed, 3 skipped.
- startup.py hash unchanged (85de483307be925517bee2ce3f109e5d6538560c); the bridge/startup/main/tools/deploy/revit_mcp status equals the baseline.
