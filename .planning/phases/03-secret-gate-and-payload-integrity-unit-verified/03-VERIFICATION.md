---
phase: 03-secret-gate-and-payload-integrity-unit-verified
verified: 2026-10-23T00:00:00Z
status: passed
score: 8/8 roadmap success criteria verified
covered_files:
  - .gitignore
  - .planning/REQUIREMENTS.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-01-PLAN.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-01-SUMMARY.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-02-PLAN.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-02-SUMMARY.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-03-PLAN.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-03-SUMMARY.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-04-PLAN.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-04-SUMMARY.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-05-PLAN.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-05-SUMMARY.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-06-PLAN.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-06-SUMMARY.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-07-PLAN.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-07-SUMMARY.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-08-PLAN.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-08-SUMMARY.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-09-PLAN.md
  - .planning/phases/03-secret-gate-and-payload-integrity-unit-verified/03-09-SUMMARY.md
  - CLAUDE.md
  - bridge.py
  - deploy/build-payload.cmd
  - deploy/config.cmd
  - deploy/gate.py
  - deploy/make_manifest.py
  - deploy/publish-extension.cmd
  - deploy/secret_tool.py
  - revit_mcp/integrity.py
  - revit_mcp/trust.py
  - scripts/dev_secret.py
  - scripts/probe_ipy_trust.py
  - tests/unit/test_integrity_reader.py
  - tests/unit/test_trust_dialect.py
  - tests/unit/test_trust_integrity.py
covered_digest: "v1:sha256:26f89dd52727185d0ffffa96d20a3ee73d7a591def312939e439ba4fc8cae920"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 8/8 (one open item)
  gaps_closed:
    - "WR-01: a network share dropped mid-scan reported verified_mismatch instead of unverifiable (D-13 / SC6 residual). Closed by gap-closure plan 03-09 (commits f54d3cd, af65ad2, 4ed1ea4)."
  gaps_remaining: []
  regressions: []
---

# Phase 3: Secret gate and payload integrity (unit-verified) Verification Report

**Phase Goal:** The logic that will reject an unauthenticated mutation and detect a tampered `revit_mcp/` payload exists, is correct on both runtimes per the unit-test suite, and is generated consistently by the build pipeline, but is not yet wired into a live route (inert by design; live enforcement is Phase 5).
**Verified:** 2026-10-23
**Status:** passed
**Re-verification:** Yes, after gap closure. The previous report (status `human_needed`) had one open item, WR-01. The user chose to fix it; plan 03-09 executed.

## Re-verification focus: WR-01 is closed

I read the code and ran the checks myself, not from the SUMMARY.

**Mechanism (read in `revit_mcp/integrity.py` and `revit_mcp/trust.py`):**

- `integrity._list_names` is the listing twin of `_read_bytes`: ENOENT gives `absent`, any other error gives `error`.
- `observe_tree` now returns a fourth key, `absent` (sorted): every listed path that read as ENOENT, plus `revit_mcp/` when the scope listing read as ENOENT. Previously the scope-listing ENOENT was swallowed.
- `unconfirmed_absences(root, manifest, absent)` first re-reads the manifest, which must parse and equal the first read. If it does not, every absent entry stays unconfirmed and nothing else is touched. Only then does it re-read each absent entry (the listing for `revit_mcp/`, `_read_bytes` for a file), and an entry counts as confirmed only if it is absent again.
- `check_integrity` calls it only when `absent` is non-empty, so a matching tree costs no extra I/O (pinned by `test_matching_tree_reads_the_manifest_once`).
- `trust.evaluate_integrity` accepts the optional `unconfirmed` key. A non-empty list gives `unverifiable/absence_unconfirmed`. A non-list gives `read_error`. An absent or empty key changes nothing. Precedence is manifest_missing, manifest_unreadable, read_error (shape or unreadable), absence_unconfirmed, then mismatch or match. `REASON_ABSENCE_UNCONFIRMED = "absence_unconfirmed"` is the new reason, the one the user approved.
- The reader still opens only in `"rb"`; the only `open(` matches in `integrity.py` are `"rb"` and a docstring. `check_integrity` still wraps everything and returns `unverifiable/read_error` on any exception.

**Experiment (CPython, temp dir outside the repo, script in the scratchpad; the tree was built there and removed afterward):**

| Scenario | Result |
|----------|--------|
| Intact tree | `verified_match` |
| One file genuinely deleted, tree reachable | `verified_mismatch`, `missing == ['revit_mcp/b.py']` |
| Whole `revit_mcp/` genuinely deleted, root reachable | `verified_mismatch`, all three files listed missing |
| Share drop: manifest read once, then every `open` and `os.listdir` raises `OSError(ENOENT, msg, None, 53)` | `unverifiable / absence_unconfirmed`, `missing == []` |
| Everything raising ENOENT from the first open | `unverifiable / manifest_missing` (the pre-existing D-13 path, still non-blocking) |
| One file modified, tree reachable | `verified_mismatch`, `modified == ['revit_mcp/a.py']` |
| Real repo tree (dev-junction layout) | `unverifiable / manifest_missing`, nothing written (no `_manifest.json`, `__pycache__` or `_bridge_secret` in `git status`) |

SC6 therefore holds in both directions: a dropped share never reads as tampering, and a real single-file deletion on a reachable tree still reads as a mismatch with the file named. My first run of this script gave a spurious `unverifiable` on the tamper case. That was my own harness leaking a patched `open` into the module and not the code under test. I removed the leak and the rerun is the table above.

**Test evidence:** `uv run pytest tests/unit -q` gives **4692 passed, 3 skipped** in 26 s. That matches what the orchestrator saw. The earlier verification had 4667 passed, so there are 25 new tests and no loss. The focused files `test_trust_dialect`, `test_integrity_reader`, `test_trust_integrity` and `test_registration` give 216 passed. New tests cover the share drop after the manifest read, a drop after some files were read, a blip that recovers before corroboration, a manifest changed between reads, genuine-deletion confirmation, one manifest read on a matching tree, `observe_tree` reporting `absent`, a raising corroboration, no path or error text in the result, an IronPython-3 engine simulation of a genuine deletion, the pinned reason value, precedence, wrong-type `unconfirmed`, and a property test that `unconfirmed` never yields a mismatch. `test_integrity_423_is_never_built_from_an_unconfirmed_result` is also present.

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Secret compare rejects wrong or missing secret and accepts the correct one, secret read from the `text/plain` body via `parse_request_data()` | VERIFIED | `trust.split_envelope` uses only `textutils.parse_request_data`. Suites `test_trust_envelope`, `test_trust_secret`, `test_trust_dialect` and `test_secret_gate_e2e` pass in the 4692. Source unchanged by 03-09 apart from the integrity section of `trust.py`. |
| SC2 | Constant-time compare using a primitive confirmed on pyRevit's CLR, with documented fallback reason | VERIFIED | `_same_digest` XORs all 32 digest bytes, no early exit. The fallback reason and live result are in the `secret_matches` docstring and in `03-VALIDATION.md`. I did not re-run the live probe (needs Revit). |
| SC3 | Auth failure is a non-200 distinct from 409 and passes through `_revit_call`'s string contract, with a regression test in the `rolled_back` style | VERIFIED | `auth_failure` returns 401, `INTEGRITY_FAILURE_STATUS = 423`; the pairing tests in `test_format_response.py` pass; `bridge._send` is unchanged. |
| SC4 | Secret never in an exception message or log line from the compare helper | VERIFIED | The leak tests pass. `trust.py` has no logging or print. The 03-09 change adds no secret-bearing path. A test pins that the share-drop result carries no path or error text. |
| SC5 | Manifest list comes from `git ls-files`, not a filesystem walk | VERIFIED | `deploy/make_manifest.py` is unchanged by 03-09, and the walker-banned tests pass. |
| SC6 | Three-state model never collapses "reference unreachable" into "mismatched"; the check never writes | VERIFIED, WR-01 residual closed | See the re-verification section above. The unreachable manifest and non-ENOENT errors were already unverifiable. A dropped share now gives `absence_unconfirmed`. A genuine deletion still gives `verified_mismatch`. `integrity.py` opens only in `"rb"`, and the `test_never_writes` family passes. |
| SC7 | Build pipeline generates one secret and one manifest per build, consumed identically, right after the `revit_mcp` copy | VERIFIED | `deploy/*.cmd` and `deploy/*.py` are untouched since the previous verification (`git diff 169d360 HEAD` over `deploy`, `bridge.py`, `main.py`, `startup.py`, `tools` is empty). The publish-order, build-payload-order and gate-pair tests pass. |
| SC8 | On the dev junction layout the check reports `verified_match` or a non-blocking `unverifiable`, never a spurious mismatch | VERIFIED | I ran `check_integrity` on the real tree: `unverifiable / manifest_missing`, nothing written. `test_real_repo_*` and `test_dev_junction_layout_*` pass. |

**Score:** 8/8 truths verified.

### Inertness (re-checked)

| Check | Result |
|-------|--------|
| Any reference to trust or integrity from `main.py`, `startup.py`, `tools/` or other `revit_mcp/` modules | None. A case-insensitive search for `trust\|integrity\|with_envelope\|load_secret\|_bridge_secret\|_manifest\|absence_unconfirmed` hits only the two new files and unrelated words ("trusted arbitrary-code", "do not trust the UI state", "trustworthy reply", "Never trust a route's own status"). There is no `from .trust` or `import integrity` anywhere except `integrity.py` importing `.trust` (a within-phase import). |
| `bridge._send` unchanged | `git diff 169d360 HEAD -- bridge.py` is empty. The prior check showed `_send` byte-identical to the baseline. |
| `startup.py` working-copy diff (another session) | Zero trust, integrity, secret or manifest lines. |
| `trust` and `integrity` still helpers (no `register_*_routes`) | `test_registration.py` passes. |

### Dialect guards

`tests/unit/test_trust_dialect.py` passes. It was extended for the new key: the simulated-engine integrity matrix now expects 4 mismatch and 8 unverifiable rows including `absence_unconfirmed`, and an IronPython-3 engine test confirms a genuine deletion is still a mismatch. The new code uses no f-strings and no 3.5+ constructs, and the 3.5+ construct guard is green.

### Requirements Coverage

The 16 IDs are SEC-01..08 and INTG-01..08. They are all `[x]` in `.planning/REQUIREMENTS.md` (lines 39-57) and `Complete` in the traceability table (lines 141-156). The union of PLAN frontmatter requirements still equals this set, with no orphans. 03-09's gap closure maps to INTG-07 (an unreachable reference is not tampering) and INTG-03 (never writes), both now satisfied without the earlier WR-01 caveat. The earlier caveat still applies: SEC-01, SEC-03, SEC-05, INTG-02, INTG-04 and INTG-05 describe live behaviour. `Complete` means "logic built and unit-verified", and live enforcement is Phase 5 per the ROADMAP.

### Anti-Patterns

No `TBD`, `FIXME` or `XXX` in the changed files. The WR-01 warning from the prior report (`integrity.py` treating ENOENT as legitimate absence) is resolved.

## Known residuals (stated honestly; none is a success-criterion gap)

1. **IronPython 3.4 errno mapping for a dropped network path is not observed live.** Only CPython on Windows was observed (ENOENT for `open` and for `os.listdir`). The verdict is `unverifiable` either way: an ENOENT goes through the corroboration, and any other errno or a non-`OSError` becomes `read_error`. That claim rests on reasoning plus CPython unit tests, not on a live gate. The `unconfirmed_absences` docstring records this.
2. **Two separate outages can still give a false mismatch.** One outage must cover the first scan and a second must cover the re-read of the absent entries, with the share reachable for the manifest re-read in between. The docstring discloses this. There are no retries or sleeps by design.
3. **Live probe metadata not reported.** The engineer-run live probe (`D04_VERDICT=PASS`, `MODULES_VERDICT=PASS`) did not report Revit or pyRevit versions, listener count or run date. This is recorded in `03-VALIDATION.md`. No success criterion demands those fields.
4. **Non-blocking review items left open and out of scope for 03-09:**
   - **WR-02:** `deploy/publish-extension.cmd` removes the live extension before the fallible stage and manifest steps. An error there leaves the shared extension re-populated without a manifest or secret. It fails closed once Phase 5 lands.
   - **IN-01 to IN-05** from `03-REVIEW.md`: strip-set difference, scope limited to `*.py` directly in `revit_mcp/`, `deploy/gate.py` letting `unchecked` pass and using `assert`, and cosmetic items.
   - Track WR-02 as a deploy hazard for Phase 5 or a follow-up. It is not a phase gap.
5. **Bookkeeping:** `03-VALIDATION.md` frontmatter still reads `status: draft` and `nyquist_compliant: false` with unchecked sign-off boxes, and the working tree has uncommitted work from another session (`startup.py`, `tests/unit/test_parallel_installation.py`, graphify-out) that does not touch this phase.

## Gaps Summary

None. WR-01 is verifiably closed and nothing regressed. The phase delivers inert, unit-verified secret-gate and integrity logic that is correct on both runtimes per the suite, with the build pipeline staging one secret and one `git ls-files` manifest in the right order. The unit suite (4692 passed, 3 skipped) is green, nothing in the live path references the new modules, `_send` is unchanged, and the dev junction reports a non-blocking `unverifiable`.

---

_Verified: 2026-10-23_
_Verifier: Claude (gsd-verifier)_
