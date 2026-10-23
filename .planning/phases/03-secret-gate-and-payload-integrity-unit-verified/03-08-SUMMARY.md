---
phase: 03-secret-gate-and-payload-integrity-unit-verified
plan: 08
subsystem: testing
tags: [hashlib, sha256, ironpython, live-probe, execute_code, pyrevit, d-04, sec-04]

requires:
  - phase: 03-secret-gate-and-payload-integrity-unit-verified
    provides: "03-01/03-05 revit_mcp/trust.py and revit_mcp/integrity.py (the helper modules the probe checks); 03-06 dialect tests"
provides:
  - "scripts/probe_ipy_trust.py: one-shot live probe with separate D04_VERDICT and MODULES_VERDICT (PASS/FAIL/INCONCLUSIVE) and exit codes 0/1/2/3/4"
  - "tests/unit/test_probe_ipy_trust.py: 36 offline tests of the snippet, verdict parser and exit codes"
  - "Observed result: hashlib.sha256 digests, abc/LF vectors and the trust/integrity modules behave in the live IronPython 3.4.2 routes engine; D-04 stays closed"
  - "secret_matches and hash_normalized docstrings and 03-VALIDATION.md SC2 (live) row carry the recorded result"
affects: [phase-03 verification, Phase 5 load-time secret and integrity enforcement]

plan_head_before: f3a09d0b4597d696bf2789a821b622a7f702359e
actuals:
  tokens: 8300
  tasks: 3
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Probe verdicts reproducible from pasted text: the script prints status, error and snippet lines in one parseable stream and the verdict functions re-derive both verdicts from it"
    - "Module-load evidence taken from /status/ (startup's own import pass); the snippet's sys.modules lookup is best-effort and informational"

key-files:
  created:
    - scripts/probe_ipy_trust.py
    - tests/unit/test_probe_ipy_trust.py
  modified:
    - revit_mcp/trust.py
    - revit_mcp/integrity.py
    - tests/unit/test_trust_secret.py
    - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-VALIDATION.md

key-decisions:
  - "Both verdicts PASS, so the plan's both-PASS branch applied: docstrings record the live result, D-04 stays closed, no fallback to System.Security.Cryptography.SHA256 is needed"
  - "Docstrings claim only what the pasted output proves; Revit and pyRevit versions and the single-listener fact were not reported and are recorded as such"

requirements-completed: [SEC-04]

coverage:
  - id: D1
    description: "Live D-04 probe script (snippet, verdict parser, exit codes) with offline tests"
    requirement: SEC-04
    verification:
      - kind: unit
        ref: "tests/unit/test_probe_ipy_trust.py (36 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "hashlib.sha256 digest bytes, abc/LF vectors and trust/integrity module load observed in the live pyRevit routes engine (py=3.4.2)"
    requirement: SEC-04
    verification:
      - kind: manual_procedural
        ref: "uv run python scripts/probe_ipy_trust.py --port 48884 (engineer-run; output re-parsed offline: D04 PASS, MODULES PASS)"
        status: pass
    human_judgment: true
    rationale: "The live engine run is human-run by project practice; the Revit and pyRevit versions and the exact listener count were not reported, so the evidence is the pasted output only"
  - id: D3
    description: "Live result recorded in the secret_matches and hash_normalized docstrings and in 03-VALIDATION.md; docstring-only code change"
    requirement: SEC-04
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_secret.py#test_constant_time_docstring_records_live_check"
        status: pass
    human_judgment: false

duration: "continuation segment about 8 min (Task 1 and the engineer-run Task 2 were not timed by this agent)"
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 08: Live D-04 Probe and Recorded Result Summary

**One-shot live probe for D-04 (hashlib.sha256 in pyRevit's engine) plus a separate module-load verdict from /status/; the engineer's run passed both and the result is recorded in two docstrings and 03-VALIDATION.md.**

## Performance

- **Duration:** continuation segment about 8 min; Task 1 and the engineer-run Task 2 were not timed by this agent
- **Completed:** 2026-10-23
- **Tasks:** 3 (Task 1 auto, Task 2 human-run checkpoint, Task 3 auto)
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- `scripts/probe_ipy_trust.py` runs the research snippet (extended with `lf_ok` and the `trust_*`/`integrity_*` lines) through `/execute_code/` and checks `/status/`; it reports `D04_VERDICT` and `MODULES_VERDICT` independently, so a module-lookup miss can never fail D-04.
- The engineer ran it live and pasted the output. Observed: `py=3.4.2`, `digest_type=bytes len=32 first4=[227, 79, 109, 236]`, `abc_ok=True`, `lf_ok=True`, `STATUS_SKIPPED` lists `trust` and `integrity` (and `identity`, `registry`, `textutils`, `utils`) as helpers, `STATUS_FAILED={}`, `trust_loaded=True`, `trust_ok=True`, `integrity_loaded=True`, `integrity_ok=True`, `D04_VERDICT=PASS`, `MODULES_VERDICT=PASS`.
- I re-parsed the pasted file offline by importing `parse_output`, `d04_verdict`, `modules_verdict` and `exit_code` from the script (probe not run against Revit): D04 = `('PASS', [])`, MODULES = `('PASS', [])`, exit code 0.
- Informational: `clr_version=4.0.30319.42000` (.NET Framework 4), `FixedTimeEquals_type_present=False` (consistent with Conflict C3 on a .NET Framework host), `hmac_compare_digest=True`. No verdict and no implementation depends on them.
- The `secret_matches` docstring in `revit_mcp/trust.py` replaces the "pending, plan 03-08" sentence with the live-verified result; `hash_normalized` in `revit_mcp/integrity.py` gains one sentence (`integrity_ok` stays, because the probe did print it). A new test asserts "Live-verified" is present and "pending" absent. The SC2 (live) row in 03-VALIDATION.md is green with the pasted output below the Manual-Only table.

## Task Commits

1. **Task 1: live D-04 probe script with offline tests** - `9fd0a45` (feat)
2. **Task 2: human-run live check** - no commit (engineer-run; output recorded in 03-VALIDATION.md by Task 3)
3. **Task 3: record the live result** - `56e7299` (docs)

**Plan metadata:** the SUMMARY commit (docs: complete plan summary), made after this file.

`actuals.commits: 2` counts this plan's task commits. The raw ledger range `plan_head_before..HEAD` read 3 at SUMMARY time because it includes `d38545f`, a session commit from another session that landed on the branch between mine; it is not part of this plan.

## Files Created/Modified

- `scripts/probe_ipy_trust.py` - the probe: `SNIPPET`, `build_body`, `parse_output`, `d04_verdict`, `modules_verdict`, `exit_code`, `main`
- `tests/unit/test_probe_ipy_trust.py` - 36 offline tests (snippet shape, CPython run of the snippet, verdicts, MockTransport exit codes)
- `revit_mcp/trust.py` - `secret_matches` docstring records the live result (docstring only)
- `revit_mcp/integrity.py` - `hash_normalized` docstring records the live result (docstring only)
- `tests/unit/test_trust_secret.py` - `test_constant_time_docstring_records_live_check`
- `.planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-VALIDATION.md` - SC2 (live) row green, recorded output and the not-reported items

## What was and was not observed

Observed (from the pasted output): the engine reports Python 3.4.2 and .NET Framework 4 (`clr_version=4.0.30319.42000`); `hashlib.sha256` returns bytes digests that equal CPython's for the test vectors; `trust` and `integrity` are in `skipped_modules` (loaded as helpers) and nothing is in `failed_domains`; the `/execute_code/` namespace did see startup's module table (`trust_loaded=True`) and both modules behaved correctly there; the probe answered on `127.0.0.1:48884`.

Not reported by the engineer, and therefore not recorded as fact anywhere: the Revit version, the pyRevit version, and the exact listener count on port 48884. The probe answering on that port is consistent with a single responding Revit but does not prove exactly one listener. The run date was also not reported; the output reached this agent on 2026-10-23 and that is the date written in the docstrings (it is the recording date). The procedural steps (full Revit close and reopen, throwaway model) are not visible in the output and are not claimed.

## Decisions Made

- Followed the plan's both-PASS branch; D-04 is not reopened and the CLR fallback is not needed.
- In the `secret_matches` docstring the unreported Revit and pyRevit versions are stated as "not reported" instead of being filled with a guess, as the plan template's `<version>` placeholders would otherwise require.
- Added "hmac.compare_digest present: True (informational)" to the same docstring sentence, because the earlier "Documented fallback reason" paragraph still says it is "unverified on IronPython 3.4"; the earlier paragraph was left untouched (it explains the original choice and still holds).

## Deviations from Plan

None in code or scope. Two wording notes: (1) the docstring says "Revit and pyRevit versions were not reported" in place of the plan's `Revit <version>, pyRevit <version>` because those values do not exist in the evidence; (2) the date is the recording date, not a reported run date.

**Total deviations:** 0 auto-fixed.

## Issues Encountered

- `git commit` printed the known harmless `failed to delete '.git/worktrees/hot-cirrus': Permission denied`; the commit itself succeeded (verified in `git log`).
- Git printed LF-to-CRLF working-copy warnings for the edited files; the diff shows docstring lines only.

## Verification

- `uv run pytest tests/unit/test_trust_secret.py tests/unit/test_trust_dialect.py tests/unit/test_conventions.py -q`: 414 passed, 3 skipped.
- `uv run pytest tests/unit -q`: 4667 passed, 3 skipped, 0 failures.
- `uv run pytest tests/unit/test_probe_ipy_trust.py -q`: 36 passed.
- `trust.secret_matches.__doc__` contains "Live-verified" and not "pending" (`LIVE_RECORDED`).
- `git diff` of `revit_mcp/` for the Task 3 commit: docstring lines only, no code lines.
- `scripts/probe_handler_overlap.py` still carries the user's uncommitted edit, untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- This was the last plan of Phase 3 (8 of 8); the phase is ready for verification. SC2's live half is closed on the pasted evidence.
- The `revit_mcp/` edits are docstring-only, but under CLAUDE.md any later live test of `revit_mcp/` code needs a full Revit close and reopen, not pyRevit Reload.
- Open items for whoever reads this later: Revit and pyRevit versions and the exact listener count were never captured for this run. If they matter for a release record, the engineer must supply them separately.

## Self-Check: PASSED

- FOUND: scripts/probe_ipy_trust.py
- FOUND: tests/unit/test_probe_ipy_trust.py
- FOUND: commit 9fd0a45
- FOUND: commit 56e7299

---
*Phase: 03-secret-gate-and-payload-integrity-unit-verified*
*Completed: 2026-10-23*
