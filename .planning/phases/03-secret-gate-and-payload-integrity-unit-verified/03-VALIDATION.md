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
| **Quick run command** | `uv run pytest tests/unit/test_trust_secret.py tests/unit/test_trust_envelope.py tests/unit/test_trust_integrity.py tests/unit/test_trust_listeners.py tests/unit/test_integrity_reader.py tests/unit/test_make_manifest.py tests/unit/test_secret_pipeline.py tests/unit/test_bridge_secret_client.py tests/unit/test_trust_dialect.py -q` |
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
| SC2 (live) | `hashlib.sha256` works under IPY342 | manual | `/execute_code/` snippet from RESEARCH "Code Examples" | n/a | ⬜ pending |
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

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
