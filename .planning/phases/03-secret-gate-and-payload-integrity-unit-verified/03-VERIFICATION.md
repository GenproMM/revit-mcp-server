---
phase: 03-secret-gate-and-payload-integrity-unit-verified
verified: 2026-10-23T00:00:00Z
status: human_needed
score: 8/8 roadmap success criteria verified (SC6 verified as written; one D-13 residual needs a developer decision)
covered_files:
  - .gitignore
  - .planning/REQUIREMENTS.md
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
covered_digest: "v1:sha256:5f06008181b49387e0d8d4583681bf0fd6999fba40d500af0fe1f0fc28de44b6"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Decide on WR-01: fix now, carry into Phase 5 scope, or accept as documented residual"
    expected: "A decision recorded. If fix: integrity.check_integrity corroborates absence (root and _manifest.json still reachable after observe_tree) before reporting missing files, or treats scope-dir ENOENT / all-listed-files-absent as read_error."
    why_human: "A dropped UNC share mid-scan maps to ENOENT and yields verified_mismatch (423 once wired) instead of unverifiable. Whether this narrow window is acceptable is a risk decision, not something a test can settle."
---

# Phase 3: Secret gate and payload integrity (unit-verified) Verification Report

**Phase Goal:** The logic that will reject an unauthenticated mutation and detect a tampered `revit_mcp/` payload exists, is correct on both runtimes per the unit-test suite, and is generated consistently by the build pipeline, but is not yet wired into a live route (inert by design; live enforcement is Phase 5).
**Verified:** 2026-10-23
**Status:** human_needed (all code-level criteria verified; one warning needs a developer decision)
**Re-verification:** No, initial verification

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Secret-compare rejects wrong or missing secret and accepts correct one, on CPython and IronPython-targeted logic, secret read from the `text/plain` body via `parse_request_data()` | VERIFIED | `revit_mcp/trust.py` `split_envelope` goes only through `textutils.parse_request_data`; `check_secret` returns ok/missing/mismatch/server_not_configured. Tests: `test_trust_envelope.py`, `test_trust_secret.py`, `test_trust_dialect.py` (IPY dialect simulation + 3.5+ construct guard), `test_secret_gate_e2e.py` (through the real `_send`). All pass. |
| SC2 | Constant-time compare using a primitive confirmed on pyRevit's CLR, with documented fallback reason, after a live CLR check | VERIFIED | `_same_digest` XORs all 32 digest bytes, no early exit. Docstring of `secret_matches` records the fallback reason (no `FixedTimeEquals` on .NET Framework) and the live result. `test_constant_time_*` (visits every position, no early exit, no direct compare, docstring records reason and live check). Live half: `03-VALIDATION.md` records the engineer's probe output (py=3.4.2, clr 4.0.30319.42000, `FixedTimeEquals_type_present=False`, `trust_ok=True`, `integrity_ok=True`, `D04_VERDICT=PASS`, `MODULES_VERDICT=PASS`). I cannot re-run it (needs live Revit). Revit version, pyRevit version, exact listener count and run date were not reported by the engineer and are recorded as such in VALIDATION.md; no success criterion demands them, so this is stated, not a gap. |
| SC3 | Auth failure is a non-200 distinct from 409, passes through `_revit_call`'s string contract, paired regression test in the style of `rolled_back` | VERIFIED | `trust.auth_failure` returns `(body, 401)`; `INTEGRITY_FAILURE_STATUS=423`. `tests/unit/test_format_response.py` lines ~193-230: `test_auth_401_reaches_the_model_as_a_visible_error`, `test_auth_failure_dict_renders_as_an_error`, alarm test `test_auth_key_alone_is_not_an_error_signal`. `bridge._send` unchanged, so non-200 collapses to `Error: 401 - ...`. |
| SC4 | Secret never in an exception message or log line from the compare helper | VERIFIED | `secret_matches` and `check_secret` swallow exceptions without keeping text; `auth_failure` clamps reason to a fixed set; `trust.py` has no logging or print. Tests: `test_secret_never_leaks_when_hashing_fails` (caplog), `test_secret_never_in_an_auth_failure_body`, `test_leak_*`, `test_leak_trust_module_has_no_logging_or_print`. |
| SC5 | Manifest list comes from `git ls-files`, not a filesystem walk | VERIFIED | `deploy/make_manifest.py` `tracked_files` runs `git -C repo ls-files -z`; no `os.walk`/`scandir`/`glob` in the module. Tests: `test_ls_files_only_list_with_walkers_banned`, `test_ls_files_untracked_noise_in_dest_never_becomes_an_entry`, `test_grammar_the_generator_never_walks_the_filesystem`. CRLF equivalence in `integrity.hash_normalized` (single hashing function shared with the generator). |
| SC6 | Three-state model never collapses "reference unreachable" into "mismatched"; the check never writes | VERIFIED as written, with WR-01 residual (see below) | Unreachable or unreadable manifest gives `unverifiable` (manifest_missing / read_error / manifest_unreadable). Any non-ENOENT failure on a listed file or on the scope listing gives `unverifiable/read_error` even when other files differ (`test_unreachable_*`). `integrity.py` opens only in `"rb"`; `test_never_writes` family and `test_real_repo_check_leaves_no_manifest_behind` pass. |
| SC7 | Build pipeline generates one secret and one manifest per build, consumed identically by payload and extension, right after the `revit_mcp` copy | VERIFIED | `config.cmd` defines `MCP_SECRET_FILE`. `publish-extension.cmd`: robocopy of `revit_mcp` excludes `_bridge_secret`/`_manifest.json`, then `secret_tool.py stage` to `%DEST%\revit_mcp\_bridge_secret`, then `make_manifest.py --dest %DEST%` as the last write. `build-payload.cmd` stages the same file to `app\_bridge_secret` before `gate.py`, whose `_secret_pair_status` fails on byte inequality. Tests: `test_publish_order_*` (strictly increasing, nothing copied after manifest), `test_build_payload_order_*`, `test_gate_pair_*`, `test_publish_smoke_scratch_share`. Interpretation note: the secret is created once and reused (D-07, user decision, ROADMAP wording "per build" is satisfied as "staged each build from one stable file"); the manifest goes only to the extension side because the payload does not ship `revit_mcp/`. |
| SC8 | On the dev junction layout the integrity check reports `verified_match` or non-blocking `unverifiable`, never a spurious mismatch | VERIFIED | I ran `check_integrity` against the real working tree: `{'state': 'unverifiable', 'reason': 'manifest_missing', ...}` (no `_manifest.json` in the repo, gitignored). Tests `test_real_repo_*` and `test_dev_junction_layout_*` (copy with own manifest matches; stale manifest is the negative control; no manifest is unverifiable) pass. No `__pycache__` or manifest was created by the run. |

**Score:** 8/8 truths verified.

### Inertness (explicit check)

| Check | Result |
|-------|--------|
| `main.py`, `startup.py`, `tools/*.py`, other `revit_mcp/*.py` import or reference trust/integrity | None. Case-insensitive grep over `trust|integrity|with_envelope|load_secret|_bridge_secret|_manifest` hits only the new files, docstrings, and unrelated words (e.g. "trusted arbitrary-code"). The uncommitted `startup.py` diff (47 lines, another session) contains zero trust/integrity/secret/manifest references. |
| `bridge.with_envelope` / `load_secret` production caller | None. Repo-wide grep (excluding tests, planning, venv) finds only the definitions in `bridge.py` and docstring mentions. |
| `bridge._send` unchanged | `git diff 55699f5 HEAD -- bridge.py` shows 92 additions and zero removed lines; `_send` still posts `json.dumps(data).encode("utf-8")` unchanged. Pinned by `test_bridge_secret_client.py` inert-send tests. |
| `trust` / `integrity` classified as helpers (no `register_*_routes`) | Yes; live `/status/` probe output lists both under `STATUS_SKIPPED` as helpers; `test_registration.py` passes. |

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `revit_mcp/trust.py` (518 lines) | VERIFIED | Substantive: split_envelope, check_secret, secret_matches, auth_failure, secret_from_bytes, read_secret_file, gate_applies, evaluate_integrity, integrity_failure, classify_listeners. Intentionally not wired (inert by design). |
| `revit_mcp/integrity.py` (137 lines) | VERIFIED | read-only reader, `hash_normalized`, `check_integrity`. Intentionally not wired. |
| `bridge.py` envelope client (`with_envelope`, `load_secret`) | VERIFIED | Intentionally uncalled. |
| `deploy/make_manifest.py`, `deploy/secret_tool.py`, `deploy/gate.py`, `scripts/dev_secret.py`, `scripts/probe_ipy_trust.py` | VERIFIED | Present, tested, wired into `.cmd` pipeline (make_manifest, secret_tool, gate). |
| `deploy/config.cmd`, `publish-extension.cmd`, `build-payload.cmd`, `.gitignore`, `CLAUDE.md` | VERIFIED | `.gitignore` HEAD contains `_bridge_secret` and `_manifest.json` (lines 36-37). `publish-extension.cmd` has one unrelated uncommitted line change (install-folder robocopy file list), not phase-3 related. |

### Key Link Verification

| From | To | Status | Details |
|------|----|--------|---------|
| `bridge.with_envelope` | `trust.split_envelope` | WIRED in tests only | `test_secret_gate_e2e.py` goes with_envelope -> real `_send` -> split_envelope/check_secret -> visible 401. `ENVELOPE_KEY`/`SECRET_KEY`/`SECRET_FILE_NAME`/`MIN_SECRET_LENGTH` pinned equal across halves. |
| `bridge._secret_from_bytes` | `trust.secret_from_bytes` | WIRED (parity test) | Intentional duplication, parity pinned. |
| `make_manifest.hash_normalized` | `integrity.hash_normalized` | WIRED | Generator imports the reader's hash function. |
| `publish-extension.cmd` | `secret_tool.py stage`, `make_manifest.py` | WIRED | Ordering tested. |
| `build-payload.cmd` | `secret_tool.py stage`, `gate.py` pair check | WIRED | Ordering tested. |

### Data-Flow Trace (Level 4)

Not applicable: the phase renders no dynamic data and is inert; the e2e tests exercise the real `_send` and real `format_response` paths.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full unit suite | `uv run pytest tests/unit -q` | 4667 passed, 3 skipped, 53 s (baseline before phase: 4054 passed, 3 skipped) | PASS |
| Phase-3 test files | `pytest test_trust_secret/dialect, test_make_manifest, test_integrity_reader, test_trust_integrity` | 291 passed | PASS |
| SC8 on real tree | `check_integrity('.')` | `unverifiable / manifest_missing`, no files written | PASS |
| SC6/INTG-03/INTG-08 subset | `-k "dev_junction or real_repo or never_writes"` | 16 passed | PASS |
| WR-01 mechanism, CPython on this Windows host | `open(r'\\localhost\nosuchshare_zz\...','rb')` and `os.listdir` on the same | `errno == 2 (ENOENT)` for both opens (winerror not preserved) and for listdir (winerror 3) | CONFIRMED |

### Probe Execution

Step 7c: no `probe-*.sh` declared by the phase. `scripts/probe_ipy_trust.py` is a human-run live probe; its recorded output is in `03-VALIDATION.md` and its offline parser is covered by `test_probe_ipy_trust.py` (passes).

### Requirements Coverage

Union of PLAN frontmatter `requirements` (03-01: SEC-01,02,04,05,06; 03-02: SEC-08; 03-03: SEC-02,03,06,08; 03-04: INTG-01,02,04,05,06; 03-05: INTG-01,03,06,07,08; 03-06: SEC-07,04,INTG-02; 03-07: SEC-08,INTG-01; 03-08: SEC-04) equals the 16 phase IDs. No orphaned IDs; REQUIREMENTS.md maps no other ID to Phase 3.

| Requirement | Plans | Status | Evidence |
|-------------|-------|--------|----------|
| SEC-01 | 03-01 | SATISFIED (logic; live in Phase 5) | `check_secret`, e2e 401 before any handler |
| SEC-02 | 03-01, 03-03 | SATISFIED | body envelope via `parse_request_data` only |
| SEC-03 | 03-03 | SATISFIED | 401 pair in `test_format_response.py` |
| SEC-04 | 03-01, 03-06, 03-08 | SATISFIED | fixed-length XOR over SHA-256; live probe recorded |
| SEC-05 | 03-01 | SATISFIED (logic) | `gate_applies`, `test_method_*`, `/status/` and GET ungated |
| SEC-06 | 03-01, 03-03 | SATISFIED | leak tests |
| SEC-07 | 03-06 | SATISFIED (classifier; collection in Phase 5) | `classify_listeners`, `test_trust_listeners.py` |
| SEC-08 | 03-02, 03-03, 03-07 | SATISFIED | secret_tool, config.cmd, gate pair check |
| INTG-01 | 03-04, 03-05, 03-07 | SATISFIED | `git ls-files` generator wired after copy |
| INTG-02 | 03-04, 03-06 | SATISFIED (logic; load-time call in Phase 5) | `check_integrity`, `evaluate_integrity` |
| INTG-03 | 03-05 | SATISFIED | `"rb"` only, never-writes tests |
| INTG-04 | 03-04 | SATISFIED (logic) | `integrity_failure` 423 |
| INTG-05 | 03-04 | SATISFIED (logic) | result names modified/missing/unexpected; `mismatch_files` |
| INTG-06 | 03-04, 03-05 | SATISFIED | CRLF normalized, pycache/.pyc not in scope |
| INTG-07 | 03-05 | SATISFIED with WR-01 residual | see below |
| INTG-08 | 03-05 | SATISFIED | real tree gives `unverifiable/manifest_missing` |

Checkbox consistency: all 16 IDs are `[x]` in REQUIREMENTS.md and `Complete` in the traceability table (lines 141-156), consistent with the evidence. Caveat: SEC-01, SEC-03 (user-observable), SEC-05, INTG-02, INTG-04 and INTG-05 describe live behavior. ROADMAP Phase 5 states they "become user-observably true" there and that they are traced to Phase 3 "where the logic is built", so the Complete mark means "logic built and unit-verified", not "enforced live". A reader of REQUIREMENTS.md alone could over-read it.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `revit_mcp/integrity.py:54-61, 103-108` | ENOENT treated as legitimate absence | Warning | WR-01 (below) |
| `deploy/publish-extension.cmd:61-83` | Fallible stage/manifest steps run after `rmdir` of the live DEST | Warning | WR-02: operator error in `make_manifest` (untracked `.py`, git failure) leaves the shared extension re-populated without a manifest/secret. Fails closed once Phase 5 lands; today it is an outage risk on a shared path. Not a phase-3 success criterion; recommend carrying into Phase 5 / a follow-up. |
| `trust.py:146-159` vs `secret_from_bytes` | Strip sets differ (IN-02) | Info | Real `token_urlsafe` secrets unaffected |
| `integrity.py`, `make_manifest.py` | Scope is `*.py` directly in `revit_mcp/`, case-sensitive (IN-03) | Info | Documented scope; drift check, not tamper defence |
| `deploy/gate.py` | `unchecked` passes; uses `assert` (IN-04) | Info | Config.cmd always sets the variable |
| `deploy/secret_tool.py`, `make_manifest.py` | IN-01, IN-05 | Info | Fail closed / cosmetic |

No `TBD`, `FIXME` or `XXX` in the phase's files without reference (grep of changed implementation files found none).

### WR-01 assessment (SC6 and the three-state model)

I read `revit_mcp/integrity.py` and reproduced the mechanism:

- `_read_bytes` returns `absent` for `errno == ENOENT`; `observe_tree` omits such files from `hashes`; `evaluate_integrity` then lists them as `missing` and returns `verified_mismatch`. The scope `os.listdir` ENOENT is swallowed (`names = []`, nothing added to `unreadable`).
- On this Windows host, CPython raises `errno 2 (ENOENT)` for an open under a nonexistent UNC share name, and for `os.listdir` of the same. So a share that vanishes after `_manifest.json` was read makes every listed file `absent` and the verdict `verified_mismatch` with all files `missing`.
- `deploy/install.cmd` sets `EXTPATH=%SHARE%\ext`, so the extension is registered with pyRevit from the share itself; the UNC scenario is the real deployment, not a hypothetical.
- Existing tests pin the ENOENT-is-missing behavior (`test_unreachable_enoent_on_a_listed_file_is_missing`, `test_unreachable_absent_scope_directory_lists_its_files_as_missing`) and test unreachability only through injected non-ENOENT errors or an unreadable manifest. No test or docstring discloses the share-drop residual.
- What I did not verify: whether IronPython 3.4 on the real engine maps a bad network path to ENOENT. The CPython mapping is confirmed; the IronPython one is unknown.

Judgment: SC6 as literally written ("reference unreachable", where the reference is the manifest) is satisfied and tested: an unreachable or unreadable manifest, and every non-ENOENT file error, give `unverifiable`. But the D-13 intent stated in `trust.py` ("an unreachable share can never be reported as tampering") has a narrow, real, undisclosed hole: a drop after the manifest read. The window is milliseconds at load, and Phase 5 caches the verdict, so a single hit would produce 423 on every mutation until Revit restarts. This is a documented-by-review residual rather than a failed success criterion, but it contradicts a stated invariant and has a small fix, so it is raised as a developer decision rather than silently passed.

### Human Verification Required

#### 1. WR-01 decision

**Test/decision:** Choose one: (a) fix before Phase 5 (after `observe_tree`, re-check that `root` is a directory and `_manifest.json` is still a file, else return `unverifiable(read_error)`; or treat scope-dir ENOENT and "all listed files absent" as `read_error`), plus a test that simulates the share vanishing mid-scan; (b) add the fix to Phase 5 scope explicitly; (c) accept and record the residual in the `integrity.py` docstring and CLAUDE.md.
**Expected:** A recorded decision; if (a) or (b), a test that a mid-scan ENOENT on all files does not yield `verified_mismatch`.
**Why human:** Risk acceptance for a narrow window against a fleet-wide blocked-mutations failure mode; not decidable by tests.

### Gaps Summary

No success criterion failed. The phase delivered inert, unit-tested logic: 4667 tests pass, nothing in the live path imports or calls it, `_send` is byte-identical, the build pipeline stages one secret and a git-ls-files manifest in the right order, and the real working tree reports a non-blocking `unverifiable`. The single open item is the WR-01 residual (a share dropped mid-scan reads as tampering), which needs a developer decision before Phase 5 caches the verdict. WR-02 (publish wipes DEST before the fallible steps) is a non-blocking deploy hazard worth tracking. The live-probe metadata gaps (Revit/pyRevit versions, listener count, run date) are recorded as unreported in `03-VALIDATION.md` and are not required by any success criterion. `03-VALIDATION.md` frontmatter still reads `status: draft`, `nyquist_compliant: false` with unchecked sign-off boxes, a bookkeeping item for `/gsd-validate-phase`, not a goal gap.

---

_Verified: 2026-10-23_
_Verifier: Claude (gsd-verifier)_
