---
phase: 03-secret-gate-and-payload-integrity-unit-verified
plan: 02
subsystem: infra
tags: [secret, build-tooling, secrets, gitignore, cpython-3.8]

requires:
  - phase: 03-secret-gate-and-payload-integrity-unit-verified
    provides: independent of plan 03-01 (no shared files or imports)
provides:
  - deploy/secret_tool.py - create-once CSPRNG fleet secret, byte-for-byte stage, pair verify, never printed
  - scripts/dev_secret.py - one-time developer secret in revit_mcp/_bridge_secret for the junction layout
  - ignore rules for _bridge_secret and _manifest.json
affects: [03-07 build scripts (call secret_tool), 03-03 bridge secret read, 03-04 extension secret read]

actuals:
  tokens: 6300
  tasks: 2
  commits: 2
plan_head_before: 22554f6904c2a5531f6bf897c6141afb8e8b3c98

tech-stack:
  added: []
  patterns:
    - "O_CREAT|O_EXCL create-once with validate-and-keep on exists and on FileExistsError"
    - "Messages name paths and defects only; the value is never in any output or exception"
    - "Python 3.8 grammar (no annotations) for tools run under pyRevit's embedded CPython"

key-files:
  created:
    - deploy/secret_tool.py
    - scripts/dev_secret.py
    - tests/unit/test_secret_pipeline.py
  modified:
    - .gitignore

key-decisions:
  - "Secret is stable, not per-build (D-07): rotation is only delete-rebuild-republish-restart"
  - "A failed write after O_EXCL create removes the truncated file so a later run does not have to reject it"
  - "ensure uses os.path.exists then O_EXCL, so the race test monkeypatches exists (the plan's design)"

requirements-completed: [SEC-08]

coverage:
  - id: D1
    description: "secret_tool ensure creates the secret once (token_urlsafe(32), O_CREAT|O_EXCL), never overwrites, survives the FileExistsError race"
    requirement: SEC-08
    verification:
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_ensure_creates_token_once, test_ensure_race_file_appears_first, test_ensure_rejects_invalid_existing_and_leaves_it"
        status: pass
    human_judgment: false
  - id: D2
    description: "stage writes byte-equal artifact and verifies; verify fails for missing, empty, BOM, UTF-16, NUL, non-ASCII, short or differing artifact"
    requirement: SEC-08
    verification:
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_stage_makes_dest_byte_equal_and_overwrites_stale, test_verify_pair_*"
        status: pass
    human_judgment: false
  - id: D3
    description: "No output of secret_tool or dev_secret contains the secret value on any success or failure path"
    requirement: SEC-08
    verification:
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_secret_never_printed_*, test_dev_secret_creates_once_and_never_prints"
        status: pass
    human_judgment: false
  - id: D4
    description: "dev_secret creates revit_mcp/_bridge_secret once and refuses an invalid existing file"
    requirement: SEC-08
    verification:
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_dev_secret_*"
        status: pass
    human_judgment: false
  - id: D5
    description: ".gitignore ignores _bridge_secret and _manifest.json at any depth"
    requirement: SEC-08
    verification:
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_gitignore_check_ignore_reports_both_ignored"
        status: pass
    human_judgment: false
  - id: D6
    description: "Both tools parse under the Python 3.8 grammar with no annotations"
    verification:
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_secret_tool_parses_as_python_38, test_dev_secret_parses_as_python_38"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 02: Build-side secret tool Summary

**Stdlib-only `deploy/secret_tool.py` (ensure / stage / verify) creating one stable CSPRNG fleet secret via O_CREAT|O_EXCL, copying it byte-for-byte into artifacts and checking the pair without ever printing it, plus `scripts/dev_secret.py` and git-ignore rules for both artifact names.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-10-23T09:02:55Z
- **Completed:** 2026-10-23T09:05:27Z (tasks; SUMMARY after)
- **Tasks:** 2
- **Files modified:** 4 (3 new, `.gitignore` hunk)

## Accomplishments
- `ensure_secret` never overwrites or regenerates: existing files are validated and kept, and a `FileExistsError` from a racing build is validated and kept, so two builds cannot produce two secrets.
- `validate_secret_bytes` rejects empty, UTF-8 BOM, UTF-16, NUL, non-ASCII, whitespace/newline and shorter-than-16 content, naming only the path and defect.
- `stage_secret` writes the artifact then runs `verify_pair`; `main` exposes `ensure`, `stage`, `verify` and returns 1 with `ERROR:` on stderr for any failure.
- `dev_secret.py` creates `revit_mcp/_bridge_secret` once through `secret_tool.ensure_secret`; `.gitignore` carries `_bridge_secret` and `_manifest.json`.
- 45 new tests in `tests/unit/test_secret_pipeline.py`; full unit suite 4225 passed, 3 skipped.

## Task Commits

1. **Task 1: deploy/secret_tool.py** - `28944ad` (feat; pathspec commit of `deploy/secret_tool.py` and the test file)
2. **Task 2: dev_secret helper and ignore rules** - `31e0b5c` (feat; committed through a temporary index so only this task's `.gitignore` lines were included)

**Plan metadata:** the `docs(03-02): complete plan summary` commit following this file.

## Files Created/Modified
- `deploy/secret_tool.py` - build-time secret generation, staging and pair verification (CPython 3.8, stdlib)
- `scripts/dev_secret.py` - one-time developer secret for the junction layout
- `tests/unit/test_secret_pipeline.py` - secret_tool, dev_secret and ignore-rule tests (03-07 extends it)
- `.gitignore` - two ignore lines plus a comment appended

## Decisions Made
- Followed the plan. Extra behavior: if the write fails after the `O_EXCL` create, the truncated file is removed so a later run does not have to reject it (never deletes a pre-existing file; it only removes a file this call just created).

## Deviations from Plan

None - plan executed exactly as written.

The plan's dirty-tree protocol worked as specified: the Task 2 commit `31e0b5c` lists exactly `.gitignore`, `scripts/dev_secret.py`, `tests/unit/test_secret_pipeline.py`; its `.gitignore` still holds the uncommented `.planning/*` line; the working-tree `.gitignore` diff now shows only the user's pre-existing commented-out GSD hunk; the real index still holds the foreign staged files (ROADMAP.md, phase-07 files, Obsidian notes), untouched.

## Issues Encountered
- `git commit` prints the harmless `failed to delete '.git/worktrees/hot-cirrus'` error; both commits succeeded.
- CRLF warnings from git on new files are cosmetic (autocrlf); not acted on.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Threat Flags

None. T-03-08 (output disclosure), T-03-09 (silent rotation), T-03-10, T-03-11, T-03-12 (dev secret committed) are mitigated and test-covered; T-03-13 is accepted per the plan (secret is a LAN barrier only, stated in the module docstring).

## Next Phase Readiness
- Plan 03-07 can call `secret_tool.py ensure|stage|verify` from the build scripts and extend `tests/unit/test_secret_pipeline.py`.
- `.gitignore` caveat for the orchestrator: the commit contains only this plan's lines; the user's uncommitted commented-out GSD block remains uncommitted in the working tree.

## Self-Check: PASSED

- `deploy/secret_tool.py`, `scripts/dev_secret.py`, `tests/unit/test_secret_pipeline.py` exist; commits `28944ad` and `31e0b5c` exist.
- Acceptance: `-k "secret_never_printed or ensure or stage or verify"` 37 passed; PY38_OK printed; `git check-ignore -v` names `.gitignore` for both artifacts; no `_bridge_secret` file exists in the working tree; `uv run pytest tests/unit -q` 4225 passed, 3 skipped, 0 failed.

---
*Phase: 03-secret-gate-and-payload-integrity-unit-verified*
*Completed: 2026-10-23*
