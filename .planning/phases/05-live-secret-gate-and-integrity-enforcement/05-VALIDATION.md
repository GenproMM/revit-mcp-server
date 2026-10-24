---
phase: "5"
slug: "live-secret-gate-and-integrity-enforcement"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-24"
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `05-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0.0 (dev group); anyio asyncio backend for bridge tests |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests/unit"]` |
| **Quick run command** | `uv run pytest tests/unit/test_trust_envelope.py tests/unit/test_trust_secret.py tests/unit/test_trust_integrity.py tests/unit/test_secret_gate_e2e.py tests/unit/test_bridge_secret_client.py tests/unit/test_phase5_gate_wiring.py tests/unit/test_security_state.py -q` |
| **Full suite command** | `uv run pytest tests/unit -q` |
| **Estimated runtime** | ~80 seconds (baseline 5218 passed, 3 skipped, 77 s) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command plus the touched route suite
- **After every plan wave:** Run `uv run pytest tests/unit -q`; after any `bridge.py` change also `python tests/test_init_latency.py` (<2.0 s)
- **Before `/gsd-verify-work`:** Full suite must be green, then live stages L1–L4 in order
- **Max feedback latency:** 80 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner / execute-phase) | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_phase5_gate_wiring.py` — AST sentinel plus behavioural rows (401/423 before any transaction)
- [ ] `tests/unit/test_security_state.py` — initialize/gate/strip/status_block against temp trees, leak tests
- [ ] Shared test helper adding the test envelope and configuring `security` state for the 4 route suites and `test_document_contracts.py`
- [ ] Flip the three `test_inert_*` pins in `tests/unit/test_bridge_secret_client.py`
- [ ] `tests/test_phase5_live_gate.py` plus `tests/unit/test_phase5_live_gate.py` (classifier)
- [ ] D-06 scanner, checked in and tested on fixtures

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Unauthenticated mutation rejected live, no level created | SEC-01, SC1 | Needs live Revit + pyRevit Routes | Live stage L1 baseline |
| Manifest match on the junction | INTG-02/06 | Needs Revit restart with manifest present | Live stage L2 |
| Corrupted/unexpected file reported by `/status/`, reads continue, mutations 423 | INTG-04/05, SC2, SC3 | Needs Revit restart after corruption | Live stage L3 |
| Cleanup and distinct positive-control write | INTG-08, D-11 | Needs Revit restart | Live stage L4 |
| D-06 paired probes on pilot share | D-06 | Pilot machine only | Pilot release procedure |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 80s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
