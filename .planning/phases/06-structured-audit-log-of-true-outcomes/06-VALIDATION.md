---
phase: "06"
slug: "structured-audit-log-of-true-outcomes"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-25"
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `06-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (`[tool.pytest.ini_options] testpaths = ["tests/unit"]`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/unit -x -q -k audit` |
| **Full suite command** | `uv run pytest tests/unit` |
| **Estimated runtime** | ~85 seconds (baseline 5884 passed, 3 skipped, 83 s) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit -x -q -k audit`
- **After every plan wave:** Run `uv run pytest tests/unit`
- **Before `/gsd-verify-work`:** Full suite must be green, `python tests/test_init_latency.py` < 2.0 s, then the human-run live gate
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

Filled in by the planner/executor once task IDs exist. Requirement → command map from research:

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| AUDIT-01 | Every sent call yields one entry; handshake/probes/not-sent yield none | integration | `uv run pytest tests/unit/test_audit_bridge_hook.py -x` | ❌ W0 | ⬜ pending |
| AUDIT-01 | `mutation` flag; open-read list mirrors `trust`; every gated route classified | unit | `uv run pytest tests/unit/test_audit_entry.py -x -k mutation` | ❌ W0 | ⬜ pending |
| AUDIT-02 | Schema 1 fields present | unit | `uv run pytest tests/unit/test_audit_entry.py -x` | ❌ W0 | ⬜ pending |
| AUDIT-03 | Outcome mapping table (pure builder) | unit | `uv run pytest tests/unit/test_audit_entry.py -x -k outcome` | ❌ W0 | ⬜ pending |
| AUDIT-03 | Same outcomes through real bridge + fake Revit | integration | `uv run pytest tests/unit/test_audit_bridge_hook.py -x -k outcome` | ❌ W0 | ⬜ pending |
| AUDIT-03 | Live rollback + partial classifier | unit | `uv run pytest tests/unit/test_phase6_live_audit.py -x` | ❌ W0 | ⬜ pending |
| AUDIT-04 | Shared `call_id` across bridge calls of one tool call | integration | `uv run pytest tests/unit/test_audit_correlation.py -x` | ❌ W0 | ⬜ pending |
| AUDIT-04 (D-12) | `user_request` on every tool, other params unchanged | unit | `uv run pytest tests/unit/test_audit_registration.py -x` | ❌ W0 | ⬜ pending |
| AUDIT-05 | No stdout from audit writer; stdio stream stays clean | static + subprocess | `uv run pytest tests/unit/test_audit_stdio.py -x` | ❌ W0 | ⬜ pending |
| AUDIT-05 | `import bridge` free of FastMCP; cold start | existing + script | `uv run pytest tests/unit/test_bridge_serialization.py -k imports` ; `python tests/test_init_latency.py` | ✅ | ⬜ pending |
| AUDIT-06 | Concurrent calls to two incarnations never interleave | integration | `uv run pytest tests/unit/test_audit_writer.py -x -k concurrent` | ❌ W0 | ⬜ pending |
| AUDIT-07 | Size cap from first write, rotation, prune, held reader | unit | `uv run pytest tests/unit/test_audit_writer.py -x -k "rotate or prune or reader or first_write"` | ❌ W0 | ⬜ pending |
| AUDIT-08 | Secret absent from file bytes across success/401/exception/truncation | integration | `uv run pytest tests/unit/test_audit_secret.py -x` | ❌ W0 | ⬜ pending |
| AUDIT-08 | No `_mcp`/body/reply data; key scrub spares `session_token` | unit | `uv run pytest tests/unit/test_audit_entry.py -x -k redact` | ❌ W0 | ⬜ pending |
| D-18 | Writer failure never changes a tool result | unit | `uv run pytest tests/unit/test_audit_writer.py -x -k never_breaks` | ❌ W0 | ⬜ pending |
| Payload | `audit.py` shipped by `build-payload.cmd` | unit | `uv run pytest tests/unit/test_payload_ships_root_modules.py -x` | ✅ (extend) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/audit_support.py` — `Machine`-style fake, in-process fake-Revit HTTP server, audit-file reader/validator
- [ ] autouse fixture in `tests/unit/conftest.py` isolating the audit sink/dir and resetting the writer singleton
- [ ] `tests/unit/test_audit_entry.py`, `test_audit_bridge_hook.py`, `test_audit_correlation.py`, `test_audit_registration.py`, `test_audit_writer.py`, `test_audit_secret.py`, `test_audit_stdio.py`
- [ ] extend `tests/unit/test_payload_ships_root_modules.py` (transitive imports) and `deploy/build-payload.cmd` (copy line)
- [ ] `tests/test_phase6_live_audit.py` (standalone one-shot; pure classifier importable by `tests/unit/test_phase6_live_audit.py`)
- Framework install: none

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real rollback and real partial batch recorded truthfully | AUDIT-03 | Needs a real Revit commit veto; trigger must be rehearsed in a scratch document first | `uv run python tests/test_phase6_live_audit.py run ...` (human-run, one-shot) |
| Two Revit instances mutated simultaneously keep separate, uncorrupted entries | AUDIT-06 | Needs two Revit processes on the two-instance bench | `tests/test_phase6_live_audit.py` two-instance step set |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
