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
| 05-01-T1 | 05-01 | 1 | SEC-01, SEC-02, SEC-03, SEC-06, INTG-04 | T-05-01, T-05-02 | /create_level/ refused 401/423 before guard, collector or transaction; handler never sees `_mcp` | route world (tracer) | `uv run pytest tests/unit/test_routes_analysis_color_identity.py -q -k create_level` | partly (suite exists; gate_support.py new) | ⬜ pending |
| 05-01-T2 | 05-01 | 1 | SEC-02, SEC-04, SEC-06, INTG-02, INTG-03 | T-05-03, T-05-08, T-05-09 | strip never refuses, gate fails closed on odd requests, type-preserving rewrite, initialize on temp trees, never writes, never leaks, same verdicts under IronPython 3 | unit | `uv run pytest tests/unit/test_security_state.py tests/unit/test_trust_dialect.py -q` | No - created in task | ⬜ pending |
| 05-02-T1 | 05-02 | 2 | SEC-01, INTG-04 | T-05-10, T-05-11 | 7 gated routes refuse with zero events | route world (tracer) | `uv run pytest tests/unit/test_routes_analysis_color_identity.py -q` | Yes | ⬜ pending |
| 05-02-T2 | 05-02 | 2 | SEC-05, SEC-06 | T-05-12, T-05-13 | 4 open reads never refuse, never see `_mcp` | route world | `uv run pytest tests/unit/test_routes_analysis_color_identity.py -q -k open_read` | Yes | ⬜ pending |
| 05-03-T1 | 05-03 | 2 | SEC-01, INTG-04 | T-05-14, T-05-16 | document/documentation/editing refuse, no file written | route world (tracer) | `uv run pytest tests/unit/test_routes_document_interop_identity.py -q` | Yes | ⬜ pending |
| 05-03-T2 | 05-03 | 2 | SEC-01, INTG-04 | T-05-14, T-05-15 | interop/placement refuse, no file written | route world | `uv run pytest tests/unit/test_routes_document_interop_identity.py -q` | Yes | ⬜ pending |
| 05-04-T1 | 05-04 | 2 | SEC-01, INTG-04 | T-05-17 | mep/parameters refuse, no Set() | route world (tracer) | `uv run pytest tests/unit/test_routes_mep_parameter_identity.py -q` | Yes | ⬜ pending |
| 05-04-T2 | 05-04 | 2 | SEC-01, INTG-04 | T-05-17, T-05-18 | rooms/structure/tags refuse | route world | `uv run pytest tests/unit/test_routes_mep_parameter_identity.py -q` | Yes | ⬜ pending |
| 05-05-T1 | 05-05 | 2 | SEC-01, SEC-05, INTG-04 | T-05-19, T-05-20, T-05-21 | execute_code/open_model/views refuse before any Revit read; workset preview open | route world (tracer) | `uv run pytest tests/unit/test_routes_view_code_identity.py -q` | Yes | ⬜ pending |
| 05-05-T2 | 05-05 | 2 | SEC-01, SEC-05 | T-05-20, T-05-22 | activate_document gated; summary/levels open | route world | `uv run pytest tests/unit/test_document_contracts.py -q` | Yes | ⬜ pending |
| 05-06-T1 | 05-06 | 4 | SEC-01, SEC-05 | T-05-23, T-05-24 | every non-GET route gated or on the exact open list | AST sentinel (tracer) | `uv run pytest tests/unit/test_phase5_gate_wiring.py tests/unit/test_phase2_inventory.py -q` | No - created in task | ⬜ pending |
| 05-06-T2 | 05-06 | 4 | SEC-01 | T-05-23, T-05-25 | conventions/kit/intake reject a forgotten gate | unit | `uv run pytest tests/unit/test_conventions.py -q` | Yes | ⬜ pending |
| 05-06-T3 | 05-06 | 4 | SEC-01 | T-05-26 | scaffolds emit the gate | unit | `uv run pytest tests/unit/test_conventions.py -q -k "scaffold or build_route_source or kit"` | Yes | ⬜ pending |
| 05-07-T1 | 05-07 | 3 | SEC-08, SEC-06 | T-05-27 | fingerprint on /status/ and comparison line; no secret | unit e2e (tracer) | `uv run pytest tests/unit/test_phase5_status_diagnostics.py -q` | No - created in task | ⬜ pending |
| 05-07-T2 | 05-07 | 3 | SEC-07, INTG-05, INTG-07, SEC-03 | T-05-29, T-05-30, T-05-31 | bind, health, alerts, 503 branch, D-07 hints | unit | `uv run pytest tests/unit/test_phase5_status_diagnostics.py tests/unit/test_trust_secret.py -q` | partly | ⬜ pending |
| 05-07-T3 | 05-07 | 3 | SEC-08 | T-05-27, T-05-30 | bridge fingerprint parity, every comparison case | unit | `uv run pytest tests/unit/test_bridge_secret_client.py tests/unit/test_status_target.py -q` | Yes | ⬜ pending |
| 05-08-T1 | 05-08 | 1 | INTG-01, SEC-08 | T-05-32, T-05-34, T-05-37 | staged publish, gates in staging, swap, ext-previous | scratch-share smoke (tracer) | `uv run pytest tests/unit/test_secret_pipeline.py tests/unit/test_make_manifest.py -q` | Yes | ⬜ pending |
| 05-08-T2 | 05-08 | 1 | INTG-01 | T-05-33 | failed/in-use publish non-destructive; rollback | scratch-share smoke | `uv run pytest tests/unit/test_secret_pipeline.py -q -k "publish or rollback"` | Yes | ⬜ pending |
| 05-08-T3 | 05-08 | 1 | INTG-08 | T-05-35 | dev manifest only at repo root and only git-ignored | unit | `uv run pytest tests/unit/test_make_manifest.py -q` | Yes | ⬜ pending |
| 05-09-T1 | 05-09 | 1 | SEC-02, SEC-06 | T-05-38 | D-06 static scan of the pre-phase tree | static (tracer) | `uv run python scripts/scan_envelope_tolerance.py --git-rev c187004` | No - created in task | ⬜ pending |
| 05-09-T2 | 05-09 | 1 | SEC-06 | T-05-38, T-05-39 | full suspect table, --dir mode | unit | `uv run pytest tests/unit/test_scan_envelope_tolerance.py -q` | No - created in Task 1 | ⬜ pending |
| 05-10-T1 | 05-10 | 5 | SEC-08, INTG-01 | T-05-41, T-05-42, T-05-43, T-05-45 | R3 order, preconditions, rollback, matrix documented | docs check (tracer) | Task 1 DOCS_OK one-liner | n/a | ⬜ pending |
| 05-10-T2 | 05-10 | 5 | SEC-05, INTG-07, INTG-08 | T-05-44 | CLAUDE.md/user guide describe the enforced gate | unit (doc needles) | `uv run pytest tests/unit/test_secret_pipeline.py tests/unit/test_serialization_scope_docs.py -q` | Yes | ⬜ pending |
| 05-11-T1 | 05-11 | 4 | SEC-01, SEC-03, SEC-05 | T-05-46, T-05-47, T-05-48 | match-stage classifier refuses partial evidence | unit (tracer) | `uv run pytest tests/unit/test_phase5_live_gate.py -q` | No - created in task | ⬜ pending |
| 05-11-T2 | 05-11 | 4 | INTG-04, INTG-05, INTG-07, INTG-08 | T-05-46 | corrupt/cleanup/phase classifiers | unit | `uv run pytest tests/unit/test_phase5_live_gate.py -q -k "corrupt or cleanup or phase"` | No - created in Task 1 | ⬜ pending |
| 05-12-T1 | 05-12 | 5 | SEC-01, SEC-02 | T-05-49 | run match against a fake Revit; POSTS_SENT counted | unit (tracer) | `uv run pytest tests/unit/test_phase5_live_gate.py -q -k run` | Yes (05-11) | ⬜ pending |
| 05-12-T2 | 05-12 | 5 | INTG-04, INTG-08 | T-05-49 | corrupt/cleanup runs; refusals before any request | unit | `uv run pytest tests/unit/test_phase5_live_gate.py -q` | Yes (05-11) | ⬜ pending |
| 05-12-T3 | 05-12 | 5 | SEC-06, INTG-03 | T-05-50, T-05-51, T-05-52 | corrupt/restore on temp repos; scan-secret | unit | `uv run pytest tests/unit/test_phase5_live_gate.py -q -k "corrupt_cmd or restore or scan_secret"` | Yes (05-11) | ⬜ pending |
| 05-13-T1 | 05-13 | 6 | INTG-06 | T-05-57 | real junction tree verified_match with the dev manifest | live prep (tracer) | `uv run python deploy/make_manifest.py --check --dest .` | n/a | ⬜ pending |
| 05-13-T3 | 05-13 | 6 | SEC-01, SEC-03, SEC-05, SEC-07, SEC-08, INTG-02 | T-05-54, T-05-56 | live L1 match: 401 before transaction, reads open, fingerprints equal | live, one-shot | `uv run python tests/test_phase5_live_gate.py classify --stage match C:/Temp/phase5/S1-match.json` | n/a | ⬜ pending |
| 05-14-T1 | 05-14 | 7 | INTG-05 | T-05-59 | corruption staged, reader sees both files | live prep (tracer) | `uv run python deploy/make_manifest.py --check --dest .` | n/a | ⬜ pending |
| 05-14-T3 | 05-14 | 7 | INTG-02, INTG-03, INTG-04, INTG-05, SEC-05 | T-05-58, T-05-60, T-05-61 | live L2 corrupt: 423 incl. execute_code, reads open; junction restored | live, one-shot | `uv run python tests/test_phase5_live_gate.py classify --stage corrupt C:/Temp/phase5/S2-corrupt.json` | n/a | ⬜ pending |
| 05-15-T1 | 05-15 | 8 | INTG-08 | — | junction clean, manifest absent | live prep (tracer) | `uv run python deploy/make_manifest.py --check --dest .` | n/a | ⬜ pending |
| 05-15-T3 | 05-15 | 8 | INTG-07, INTG-08, SEC-06 | T-05-62, T-05-63, T-05-64 | live L3 cleanup and phase verdict; no secret in any record | live, one-shot | `uv run python tests/test_phase5_live_gate.py classify-phase C:/Temp/phase5/S1-match.json C:/Temp/phase5/S2-corrupt.json C:/Temp/phase5/S3-cleanup.json` | n/a | ⬜ pending |
| 05-16-T1 | 05-16 | 2 | SEC-02, SEC-03, SEC-06 | T-05-05, T-05-06, T-05-07, T-05-65 | every POST carries the envelope and passes the real gate; 401 texts without the secret; forged `_mcp` refused not-sent | unit e2e (tracer) | `uv run pytest tests/unit/test_phase5_gate_e2e.py tests/unit/test_bridge_secret_client.py -q` | No - created in task | ⬜ pending |
| 05-16-T2 | 05-16 | 2 | INTG-02, INTG-07 | T-05-04 | startup initializes the gate at load; failure recorded in registry.FAILED and the gate stays closed | unit (startup loader) | `uv run pytest tests/unit/test_security_state.py -q -k startup` | Yes (05-01) | ⬜ pending |

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
| L1 match (plan 05-13): manifest match on the junction; unauthenticated, wrong-secret and no-envelope /execute_code/ POSTs 401 with no level created; open reads and /status/ without a secret; authenticated create_level commits; fingerprints equal; bind loopback_only | SEC-01/02/03/05/07/08, INTG-02/06, SC1, SC3 | Needs live Revit + pyRevit Routes, restart with the temporary manifest present | `tests/test_phase5_live_gate.py run --stage match` (D-11 restarts reduced to three: the baseline secret checks run in the match stage) |
| L2 corrupt (plan 05-14): `/status/` names the modified module and `revit_mcp/_zz_probe.py`, health degraded; create_level and execute_code 423; reads continue | INTG-02/03/04/05, SEC-05, SC2, SC3 | Needs Revit restart after the corruption | `tests/test_phase5_live_gate.py run --stage corrupt`, then `restore` |
| L3 cleanup (plan 05-15): unverifiable/manifest_missing, healthy, distinct positive-control write | INTG-07/08, D-11 | Needs Revit restart on the restored junction | `tests/test_phase5_live_gate.py run --stage cleanup`, then `classify-phase` and `scan-secret` |
| D-06 payload-first rehearsal on the pilot share, D-10 second-publish probe with Revit open | D-06, D-10 | Pilot machine only, at R3 | RELEASE-RUNBOOK.md section 5 / 6.3 (plan 05-10) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 80s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
