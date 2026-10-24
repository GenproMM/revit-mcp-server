---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 08
subsystem: deploy
tags: [publish, rollback, integrity-manifest, ext-staging, ext-previous, tdd, windows-cmd]

requires:
  - phase: 03-trust-primitives
    provides: deploy/make_manifest.py, deploy/secret_tool.py, revit_mcp/integrity.py (check_integrity)
provides:
  - publish-extension.cmd builds and gates in ext-staging, swaps by rename, keeps ext-previous
  - deploy/rollback-extension.cmd (one-command Revit-half rollback)
  - make_manifest.py --check (verify a published tree, writes nothing)
  - make_manifest.py --allow-repo-dest (D-11 developer manifest, repo root only, git-ignored only)
affects: [05-10, 05-16]

plan_head_before: 15d5d63b07e099d97ed0505704634d3d0a243987
actuals:
  tokens: 40000
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns:
    - "Build in ext-staging, gate there, swap by two renames; the live folder moves aside first so a busy folder changes nothing"
    - "Scratch-share smoke tests guarded by _assert_scratch before any spawn"

key-files:
  created:
    - deploy/rollback-extension.cmd
  modified:
    - deploy/make_manifest.py
    - deploy/publish-extension.cmd
    - tests/unit/test_make_manifest.py
    - tests/unit/test_secret_pipeline.py

key-decisions:
  - "Rollback keeps exactly one rejected build (ext-rejected) and one previous build (ext-previous), per D-09"
  - "--allow-repo-dest requires dest == repo root AND git check-ignore on _manifest.json; every other in-repo destination keeps the original INTG-08 refusal text"
  - "The SMB rename-while-Revit-is-open case is not measured here; the swap is non-destructive on failure and the share probe goes to the R3 pilot checklist (05-10)"

requirements-completed: [INTG-01, INTG-03, INTG-06, INTG-08, SEC-08]

duration: executed across an interruption
completed: 2026-10-24
status: complete
---

# Phase 5 Plan 08: Staged publish, rollback and manifest modes Summary

**Revit-half publish now builds and verifies in ext-staging and swaps by rename keeping ext-previous, rollback-extension.cmd restores the previous build in one command, and make_manifest.py gained `--check` and `--allow-repo-dest`.**

## Execution note

This plan was executed across an interruption: a first executor finished Task 1 (RED 0413f50, GREEN 00cd57f) and the RED of Task 2 (4cfd029), and left `deploy/rollback-extension.cmd` untracked. A continuation executor reviewed that draft against the plan and its tests (it was complete and correct, no changes needed), committed it, then did Task 3 from scratch. Nothing was redone.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 RED | 0413f50 | test: failing tests for staged publish, ext-previous and make_manifest --check |
| 1 GREEN | 00cd57f | feat: publish through ext-staging, gate there, swap by rename, keep ext-previous |
| 2 RED | 4cfd029 | test: failing rollback rows and publish failure-path rows |
| 2 GREEN | b6c750c | feat: add rollback-extension.cmd |
| 3 RED | faaa234 | test: failing allow_repo_dest rows |
| 3 GREEN | 1b778e2 | feat: add make_manifest --allow-repo-dest |

## Verification

- `uv run pytest tests/unit -q`: 5326 passed, 3 skipped (baseline 5301 passed, 3 skipped).
- `-k publish or rollback` in test_secret_pipeline.py: 23 passed, none skipped on this Windows machine. The in-use row ran (local NTFS refused the rename of a folder with an open file), so no skip was needed.
- `-k rollback`: 5 passed. `-k "allow_repo_dest or repo_dest"`: 6 passed. The three original refusal tests pass unchanged.
- Both .cmd files: ASCII, CRLF throughout; publish contains ext-staging and ext-previous; rollback contains config.cmd and no MCP_PYEXE.
- `git status --porcelain -- _manifest.json` is empty.
- No real publish, rollback or payload build was run; all smoke tests use pytest tmp_path scratch shares.

## Deviations from Plan

None - plan executed as written. One tooling note: a heredoc-written edit script turned `\n` escapes inside string literals into real newlines in two test/source lines; both were caught immediately by the collection error and fixed by Edit before commit.

## Known Stubs

None.

## Threat Flags

None. The new surface (staging and rollback folders, `--allow-repo-dest`) is covered by T-05-32 to T-05-37 in the plan.

## Open item for 05-10

Rename of `ext\<name>` while a workstation's Revit holds it open over SMB (RESEARCH A1/A9) is unmeasured; it belongs in the R3 pilot checklist. If the pilot shows the rename blocked, D-10 returns to the user.

## Self-Check: PASSED

Files found: deploy/rollback-extension.cmd, deploy/make_manifest.py, deploy/publish-extension.cmd, both test files. Commits 0413f50, 00cd57f, 4cfd029, b6c750c, faaa234, 1b778e2 present in git log.
