---
phase: "3"
slug: "secret-gate-and-payload-integrity-unit-verified"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-23"
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `03-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8 (dev group; 9.1.1 observed), Python 3.13.7 via `uv run` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options] testpaths = ["tests/unit"]`; shared setup `tests/unit/conftest.py` |
| **Quick run command** | `uv run pytest tests/unit/test_secret_gate_e2e.py tests/unit/test_trust_secret.py tests/unit/test_trust_envelope.py tests/unit/test_integrity_e2e.py tests/unit/test_trust_integrity.py tests/unit/test_trust_listeners.py tests/unit/test_integrity_reader.py tests/unit/test_make_manifest.py tests/unit/test_secret_pipeline.py tests/unit/test_bridge_secret_client.py tests/unit/test_trust_dialect.py tests/unit/test_probe_ipy_trust.py -q` (only the files that exist so far) |
| **Full suite command** | `uv run pytest tests/unit -q` |
| **Estimated runtime** | ~25 seconds (baseline 4054 passed, 3 skipped, 22 s) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (only the test files that exist so far)
- **After every plan wave:** Run `uv run pytest tests/unit -q`
- **Before `/gsd-verify-work`:** Full suite must be green, and the D-04 live checkpoint output recorded
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are filled in by the planner; rows below are keyed by requirement / success criterion.

| Requirement | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|-----------------|-----------|-------------------|-------------|--------|
| SC1, SEC-01, SEC-02 | `check_secret` → ok/missing/mismatch/server_not_configured; secret read from `text/plain` body via `split_envelope` + `parse_request_data` | unit | `uv run pytest tests/unit/test_trust_envelope.py tests/unit/test_trust_secret.py -q` | ❌ W0 | ⬜ pending |
| SC1 (IronPython-targeted) | Same table under simulated IPY dialect (`builtins.unicode = str`, reloaded module) | unit | `uv run pytest tests/unit/test_trust_dialect.py -q` | ❌ W0 | ⬜ pending |
| SC2, SEC-04 | No early exit in digest compare; documented fallback reason (no `FixedTimeEquals` on .NET Framework 4.8) | unit | `uv run pytest tests/unit/test_trust_secret.py -k constant -q` | ❌ W0 | ⬜ pending |
| SC2 (live) | `hashlib.sha256` works under IPY342 | manual | `uv run python scripts/probe_ipy_trust.py --port 48884` (human-run) | n/a | ✅ green |
| SC3, SEC-03 | `auth_failure` → 401, distinct from 409/423/503; `Error: 401 - ...` passthrough; three-assertion pair | unit | `uv run pytest tests/unit/test_format_response.py -k "401 or auth" -q` | extend | ⬜ pending |
| SC4, SEC-06 | Secret never in exception text, logs, result or failure body | unit | `uv run pytest tests/unit/test_trust_secret.py tests/unit/test_bridge_secret_client.py -k "leak or secret_never" -q` | ❌ W0 | ⬜ pending |
| SEC-05 | Gate is POST-only; GET and `/status/` stay open | unit | `uv run pytest tests/unit/test_trust_secret.py -k method -q` | ❌ W0 | ⬜ pending |
| SEC-07 | `classify_listeners` → loopback_only / exposed / unknown | unit | `uv run pytest tests/unit/test_trust_listeners.py -q` | ❌ W0 | ⬜ pending |
| SEC-08, SC7 | One stable secret staged byte-equal into both artifacts; manifest generated right after the `revit_mcp` copy; `.gitignore` entries | unit | `uv run pytest tests/unit/test_secret_pipeline.py -q` | ❌ W0 | ⬜ pending |
| INTG-01, SC5 | Manifest file list from `git ls-files`, never a filesystem walk | unit | `uv run pytest tests/unit/test_make_manifest.py -q` | ❌ W0 | ⬜ pending |
| INTG-02, INTG-05, INTG-06 | match / modified / missing / unexpected; CRLF≡LF; pycache ignored | unit | `uv run pytest tests/unit/test_trust_integrity.py -q` | ❌ W0 | ⬜ pending |
| INTG-07, SC6 | Unreachable reference → `unverifiable`, never `verified_mismatch` | unit | `uv run pytest tests/unit/test_trust_integrity.py tests/unit/test_integrity_reader.py -k "unverifiable or unreachable" -q` | ❌ W0 | ⬜ pending |
| INTG-03, SC6 | Check never writes a file under any input | unit | `uv run pytest tests/unit/test_integrity_reader.py -k never_writes -q` | ❌ W0 | ⬜ pending |
| INTG-04 | `integrity_failure` → 423, distinct from 401/409/503 | unit | `uv run pytest tests/unit/test_trust_integrity.py -k 423 -q` | ❌ W0 | ⬜ pending |
| INTG-08, SC8 | Real working tree → `verified_match` or `unverifiable(manifest_missing)`, never mismatch | unit | `uv run pytest tests/unit/test_integrity_reader.py -k "dev_junction or real_repo" -q` | ❌ W0 | ⬜ pending |
| D-10 client half | `load_secret`, `with_envelope`; live send path unchanged (inert) | unit | `uv run pytest tests/unit/test_bridge_secret_client.py -q` | ❌ W0 | ⬜ pending |
| Regression | `trust`/`integrity` classified as helpers; conventions pass | unit | `uv run pytest tests/unit/test_registration.py tests/unit/test_conventions.py tests/unit/test_phase2_inventory.py -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Planner task mapping (2026-10-23):** SC1/SEC-01/SEC-02 → 03-01 T1-T2, 03-03 T1; SC1 IronPython-targeted → 03-06 T2; SC2/SEC-04 → 03-01 T2; SC2 live → 03-08 T1-T3; SC3/SEC-03 → 03-03 T2; SC4/SEC-06 → 03-01 T2, 03-02 T1, 03-03 T1; SEC-05 → 03-01 T2; SEC-07 → 03-06 T1; SEC-08/SC7 → 03-02 T1-T2, 03-07 T1-T2; INTG-01/SC5 → 03-04 T1, 03-05 T2; INTG-02/05/06 → 03-04 T1-T2; INTG-07/SC6 → 03-04 T2, 03-05 T1; INTG-03/SC6 → 03-05 T1; INTG-04 → 03-04 T1-T2; INTG-08/SC8 → 03-05 T1; D-10 client half → 03-01 T1, 03-03 T1; regression (helpers, conventions) → 03-01 T2, 03-04 T2. Added files beyond the research list: `test_secret_gate_e2e.py` and `test_integrity_e2e.py` (the two tracers), `test_probe_ipy_trust.py` (offline tests of the live probe).

---

## Wave 0 Requirements

- [ ] `tests/unit/test_trust_envelope.py`, `test_trust_secret.py`, `test_trust_integrity.py`, `test_trust_listeners.py` — SEC-01..07, INTG-02..07
- [ ] `tests/unit/test_integrity_reader.py` — INTG-03, INTG-07, INTG-08
- [ ] `tests/unit/test_make_manifest.py` — INTG-01, SC5
- [ ] `tests/unit/test_secret_pipeline.py` — SEC-08, SC7
- [ ] `tests/unit/test_bridge_secret_client.py` — client half, inert guarantee
- [ ] `tests/unit/test_trust_dialect.py` — IronPython simulation plus 3.5+ syntax guard
- [ ] Extensions: `tests/unit/test_format_response.py` (401 pair), `tests/unit/test_registration.py` (helper sets)

*Framework install: none (already present).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `hashlib.sha256` produces a 32-byte digest under IronPython 3 (IPY342); informational `FixedTimeEquals` type probe | SC2, SEC-04 (D-04) | Needs live Revit + pyRevit Routes; cannot run under CPython | POST the RESEARCH "Code Examples" snippet to `/execute_code/` (one listener on 48884 confirmed first); expect `abc_ok=True`, `digest_type=bytes len=32 first4=[227, 79, 109, 236]`; record the engine version |

**Recorded result (plan 03-08, human-run, recorded 2026-10-23):** `scripts/probe_ipy_trust.py` run by the engineer against `127.0.0.1:48884`; output pasted verbatim, both verdicts PASS (re-parsed offline with `parse_output`, `d04_verdict`, `modules_verdict`: `('PASS', [])` each).

```
STATUS_SKIPPED={"identity": "no register_*_routes callable", "integrity": "no register_*_routes callable", "registry": "no register_*_routes callable", "textutils": "no register_*_routes callable", "trust": "no register_*_routes callable", "utils": "no register_*_routes callable"}
STATUS_FAILED={}
py=3.4.2
digest_type=bytes len=32 first4=[227, 79, 109, 236]
abc_ok=True
lf_ok=True
hmac_compare_digest=True
clr_version=4.0.30319.42000
FixedTimeEquals_type_present=False
trust_loaded=True
trust_ok=True
integrity_loaded=True
integrity_ok=True
D04_VERDICT=PASS
MODULES_VERDICT=PASS
```

- Engine: `py=3.4.2` (IronPython 3.4 level), `clr_version=4.0.30319.42000` (.NET Framework 4). `FixedTimeEquals_type_present=False` confirms Conflict C3 on this host; `hmac_compare_digest=True` is informational (the implementation uses neither).
- Revit version: not reported by the engineer. pyRevit version: not reported by the engineer.
- Listener count on port 48884: not reported by the engineer. The probe answered on `127.0.0.1:48884`, which is consistent with a single responding Revit but does not prove exactly one listener.
- Run date: not reported by the engineer; the output was received and recorded on 2026-10-23.
- Not observed here: the engineer's step 1 (full Revit close and reopen) and the throwaway-model step are procedural and were not confirmed in the pasted output.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
