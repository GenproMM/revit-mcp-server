---
phase: 03-secret-gate-and-payload-integrity-unit-verified
plan: 05
subsystem: payload-integrity
tags: [integrity, manifest, git-ls-files, write-guard, ast-scan, errno, atomic-write]

requires:
  - phase: 03-secret-gate-and-payload-integrity-unit-verified
    provides: "03-04 revit_mcp/integrity.py (read-only check_integrity) and deploy/make_manifest.py (git ls-files generator)"
provides:
  - "tests/unit/test_integrity_reader.py: 46 tests proving the check never writes, unreachable is never mismatch, the dev junction is never a mismatch, hostile keys are never opened, runs are deterministic"
  - "tests/unit/test_make_manifest.py: 22 tests proving the list comes only from git ls-files and every disagreement with the published tree fails the build"
affects: [03-06 IronPython simulation, 03-07 publish-extension.cmd, 03-08 live hashlib check, Phase 5 load-time check and 423 refusal]

plan_head_before: 228c6257d2e07bc6e1d4f2c767f41e994e717b82
actuals:
  tokens: 9600
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Write-guard fixture: builtins.open refuses w/a/x/+ modes and os/shutil mutators raise, installed only around the check; before/after name+bytes+mtime_ns snapshot"
    - "AST scan of the two production modules (open mode literal rb, no write-family call, no shutil) with a planted-violation test so the scan is not vacuous"
    - "Failing-open injection by path suffix to model EACCES, EIO, EINVAL, PermissionError and an errno-less Windows network error"

key-files:
  created:
    - tests/unit/test_integrity_reader.py
    - tests/unit/test_make_manifest.py
  modified: []

key-decisions:
  - "The AST write-call scan treats .replace()/.rename() as banned only on os, shutil or pathlib receivers: integrity.py legitimately calls bytes.replace(b'\\r\\n', b'\\n') inside hash_normalized, a pure function; every other listed name is banned on any receiver"

patterns-established:
  - "Hardening plans add tests only; production code is touched solely when a test exposes a defect (none did here)"

requirements-completed: [INTG-01, INTG-03, INTG-06, INTG-07, INTG-08]

coverage:
  - id: D1
    description: "check_integrity never writes: with every write path monkeypatched to raise it completes for matching, tampered, missing-manifest, broken-manifest and unreadable-file trees, and the tree snapshot is identical afterwards; the AST scan of trust.py and integrity.py finds no non-rb open and no write-family call"
    requirement: "INTG-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_never_writes_leaves_the_tree_untouched"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_never_writes_ast_scan_finds_no_write_call"
        status: pass
    human_judgment: false
  - id: D2
    description: "An unreachable manifest, listed file or revit_mcp directory (EACCES, EIO, EINVAL, PermissionError, errno-less network error) is unverifiable/read_error, never a mismatch even when another file really differs; only ENOENT on a listed file is missing"
    requirement: "INTG-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_unreachable_listed_file_is_unverifiable_read_error"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_unreachable_enoent_on_a_listed_file_is_missing"
        status: pass
    human_judgment: false
  - id: D3
    description: "The real repository working tree is never verified_mismatch and is unverifiable/manifest_missing while no _manifest.json exists; a tmp copy of the layout with a stale manifest is the negative control"
    requirement: "INTG-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_real_repo_is_never_a_mismatch"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_dev_junction_layout_copy_with_a_stale_manifest_is_the_negative_control"
        status: pass
    human_judgment: false
  - id: D4
    description: "Hostile manifest keys (../, absolute, drive letter, backslash) are never passed to open(); two runs over one tree are equal and integrity.py has no global or nonlocal"
    requirement: "INTG-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_hostile_manifest_key_is_never_opened"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_reader.py#test_determinism_two_runs_over_one_tree_are_equal"
        status: pass
    human_judgment: false
  - id: D5
    description: "make_manifest builds its list only from git ls-files (os.walk, scandir, glob banned), never lists pycache/.pyc/untracked noise, and preserves a non-ASCII tracked name"
    requirement: "INTG-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_make_manifest.py#test_ls_files_only_list_with_walkers_banned"
        status: pass
      - kind: unit
        ref: "tests/unit/test_make_manifest.py#test_ls_files_non_ascii_tracked_name_survives_into_the_manifest"
        status: pass
    human_judgment: false
  - id: D6
    description: "Build fails with a non-zero exit and explicit message for an untracked .py in DEST, a tracked file missing from DEST, git absent or failing, a non-checkout, and a --dest equal to or inside the repository (INTG-08)"
    requirement: "INTG-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_make_manifest.py#test_guard_untracked_py_in_dest_names_the_file"
        status: pass
      - kind: unit
        ref: "tests/unit/test_make_manifest.py#test_guard_dest_inside_the_repo_is_refused_and_writes_nothing"
        status: pass
    human_judgment: false
  - id: D7
    description: "Manifest is written atomically (failed os.replace leaves no _manifest.json and no .tmp, and keeps a previous manifest's bytes); output is deterministic ASCII; a truncated manifest evaluates unverifiable/manifest_unreadable"
    requirement: "INTG-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_make_manifest.py#test_atomic_failed_replace_leaves_no_manifest_and_no_tmp"
        status: pass
      - kind: unit
        ref: "tests/unit/test_make_manifest.py#test_atomic_truncated_manifest_is_unverifiable_never_mismatch"
        status: pass
      - kind: unit
        ref: "tests/unit/test_make_manifest.py#test_determinism_equal_dicts_and_exact_bytes"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 05: Integrity Reader and Generator Hardening Summary

**Unit proof that the SHA-256 integrity check writes nothing, never reports an unreachable reference or the dev junction as tampering, and that the manifest generator lists only `git ls-files` entries and fails the publish loudly on every disagreement; 68 new tests, no production change needed.**

## Performance

- **Duration:** about 20 min (a session-limit interruption occurred after Task 1's test file was written; resumed and re-verified from disk)
- **Completed:** 2026-10-23
- **Tasks:** 2
- **Files modified:** 2 created, 0 production files changed

## Accomplishments

- `tests/unit/test_integrity_reader.py` (46 tests): write-guard fixture plus before/after snapshot for five tree classes; AST scan of `trust.py` and `integrity.py` with a planted-violation test; unreachable manifest/file/listdir rows for five error shapes; real-repo and tmp-copy dev-junction rows with a stale-manifest negative control; five hostile keys proven never opened; determinism, no-cache and re-entrant-reader rows.
- `tests/unit/test_make_manifest.py` (22 tests): walkers banned; untracked noise never listed; untracked `.py`, missing tracked file, dest in or equal to the repo, git absent, git failing, non-checkout and empty listing all fail the build; atomic write with failing `os.replace`; deterministic ASCII bytes; non-ASCII tracked name (ran, not skipped); truncated manifest evaluates unverifiable; Python 3.8 grammar and no annotations.
- Acceptance: `DEV_JUNCTION_OK unverifiable manifest_missing` from the repository root; `python deploy/make_manifest.py --dest .` exits 1 with an `INTG-08` message and leaves no `_manifest.json`.

## Task Commits

1. **Task 1: Reader never writes, unreachable is never tampered, quiet on the dev junction** - `0272199` (test)
2. **Task 2: Generator lists only tracked files and fails loudly** - `6541c30` (test)

**Plan metadata:** committed separately (docs: complete plan summary)

## Files Created/Modified

- `tests/unit/test_integrity_reader.py` - never-writes, unreachable, dev-junction, traversal, determinism tests for `revit_mcp/integrity.py`
- `tests/unit/test_make_manifest.py` - ls-files-only, build guards, atomic write, determinism, grammar tests for `deploy/make_manifest.py`

## Decisions Made

- The AST write-call scan bans `replace` and `rename` only on `os`, `shutil` and `pathlib` receivers. `integrity.hash_normalized` calls `bytes.replace` (a pure function), so banning the name on every receiver would fail a correct module. All other listed names (`write`, `remove`, `unlink`, `mkdir`, ...) are banned on any receiver, and a planted-violation test shows each banned shape is still detected.

## Deviations from Plan

None - plan executed exactly as written. Both TDD tasks passed on first run because 03-04 had already built the contract (errno-based classification, hostile-key filtering, atomic write, dest refusal); no hardening test exposed a defect, so `revit_mcp/integrity.py` and `deploy/make_manifest.py` are unchanged. The RED phase was therefore not observable; the planted-violation and guard-refuses-a-write tests confirm the guards are not vacuous.

## Issues Encountered

- The previous executor run was cut off by an API session-limit error after writing `test_integrity_reader.py` and before any commit; the resume re-ran the file (46 passed) and continued from Task 1's commit.
- `uv run pytest tests/unit -q`: 4447 passed, 3 skipped (the 3 skips are not in this plan's files; the plan's own files ran with 0 skipped).
- `startup.py` hash is `85de483307be925517bee2ce3f109e5d6538560c` before and after; it already carried another session's edits and was not touched or committed.
- `tests/unit/test_parallel_installation.py` is an untracked file from another session; it was left alone.
- Git prints LF-to-CRLF working-copy warnings on add; harmless (hashing is CRLF-insensitive by design).

## Known Stubs

None.

## Threat Flags

None. Threats T-03-25 to T-03-31 are covered by the tests above; no new surface was added.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 03-06 can simulate IronPython 3 import of `integrity.py`; 03-07 can wire `make_manifest.py` into `publish-extension.cmd` knowing it refuses an in-repo dest and an untracked `.py`.
- Live behaviour (hashlib under IronPython 3, the dev junction on a real workstation) remains for 03-08 and Phase 5.

## Self-Check: PASSED

- FOUND: tests/unit/test_integrity_reader.py, tests/unit/test_make_manifest.py
- FOUND commits: 0272199, 6541c30 (`git log --oneline --grep="03-05"`); `git rev-list --count 228c625..HEAD` before this summary: 2
- Acceptance checks re-run: DEV_JUNCTION_OK, `make_manifest.py --dest .` exit 1 with INTG-08, no `_manifest.json` at repository root, `startup.py` hash unchanged, `uv run pytest tests/unit -q` 4447 passed 3 skipped.
- Note: `integrity.py` and `make_manifest.py` untouched (`git status --short -- revit_mcp deploy/make_manifest.py` empty).

---
*Phase: 03-secret-gate-and-payload-integrity-unit-verified*
*Completed: 2026-10-23*
