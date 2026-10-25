---
phase: "06"
slug: "structured-audit-log-of-true-outcomes"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
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
| AUDIT-01 | Every sent call yields one entry; handshake/probes/not-sent yield none | integration | `uv run pytest tests/unit/test_audit_bridge_hook.py -x` | ✅ | ✅ green |
| AUDIT-01 | `mutation` flag; open-read list mirrors `trust`; every gated route classified | unit | `uv run pytest tests/unit/test_audit_entry.py -x -k mutation` | ✅ | ✅ green |
| AUDIT-02 | Schema 1 fields present | unit | `uv run pytest tests/unit/test_audit_entry.py -x` | ✅ | ✅ green |
| AUDIT-03 | Outcome mapping table (pure builder) | unit | `uv run pytest tests/unit/test_audit_entry.py -x -k outcome` | ✅ | ✅ green |
| AUDIT-03 | Same outcomes through real bridge + fake Revit | integration | `uv run pytest tests/unit/test_audit_bridge_hook.py -x -k outcome` | ✅ | ✅ green |
| AUDIT-03 | Live rollback + partial classifier | unit | `uv run pytest tests/unit/test_phase6_live_audit.py -x` | ✅ | ✅ green |
| AUDIT-04 | Shared `call_id` across bridge calls of one tool call | integration | `uv run pytest tests/unit/test_audit_correlation.py -x` | ✅ | ✅ green |
| AUDIT-04 (D-12) | `user_request` on every tool, other params unchanged | unit | `uv run pytest tests/unit/test_audit_registration.py -x` | ✅ | ✅ green |
| AUDIT-05 | No stdout from audit writer; stdio stream stays clean | static + subprocess | `uv run pytest tests/unit/test_audit_stdio.py -x` | ✅ | ✅ green |
| AUDIT-05 | `import bridge` free of FastMCP; cold start | existing + script | `uv run pytest tests/unit/test_bridge_serialization.py -k imports` ; `python tests/test_init_latency.py` | ✅ | ✅ green |
| AUDIT-06 | Concurrent calls to two incarnations never interleave | integration | `uv run pytest tests/unit/test_audit_writer.py -x -k concurrent` | ✅ | ✅ green |
| AUDIT-07 | Size cap from first write, rotation, prune, held reader | unit | `uv run pytest tests/unit/test_audit_writer.py -x -k "rotate or prune or reader or first_write"` | ✅ | ✅ green |
| AUDIT-08 | Secret absent from file bytes across success/401/exception/truncation | integration | `uv run pytest tests/unit/test_audit_secret.py -x` | ✅ | ✅ green |
| AUDIT-08 | No `_mcp`/body/reply data; key scrub spares `session_token` | unit | `uv run pytest tests/unit/test_audit_entry.py -x -k redact` | ✅ | ✅ green |
| D-18 | Writer failure never changes a tool result | unit | `uv run pytest tests/unit/test_audit_writer.py -x -k never_breaks` | ✅ | ✅ green |
| Payload | `audit.py` shipped by `build-payload.cmd` | unit | `uv run pytest tests/unit/test_payload_ships_root_modules.py -x` | ✅ | ✅ green |
| AUDIT-03 (live) | Real rollback (409 `rolled_back`) and real partial batch recorded truthfully | live, one-shot | `uv run python tests/test_phase6_live_audit.py run-single ...` | n/a | ✅ green (`PHASE6_AUDIT_OK`, 2026-10-25) |
| AUDIT-06 (live) | Two Revit instances, two server processes, separate uncorrupted audit files | live, one-shot | `uv run python tests/test_phase6_live_audit.py run-dual ...` | n/a | ✅ green (`PHASE6_AUDIT_OK`, 2026-10-25) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/audit_support.py` — `Machine`-style fake, in-process fake-Revit HTTP server, audit-file reader/validator
- [x] autouse fixture in `tests/unit/conftest.py` isolating the audit sink/dir and resetting the writer singleton
- [x] `tests/unit/test_audit_entry.py`, `test_audit_bridge_hook.py`, `test_audit_correlation.py`, `test_audit_registration.py`, `test_audit_writer.py`, `test_audit_secret.py`, `test_audit_stdio.py`
- [x] extend `tests/unit/test_payload_ships_root_modules.py` (transitive imports) and `deploy/build-payload.cmd` (copy line)
- [x] `tests/test_phase6_live_audit.py` (standalone one-shot; pure classifier importable by `tests/unit/test_phase6_live_audit.py`)
- Framework install: none

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real rollback and real partial batch recorded truthfully | AUDIT-03 | Needs a real Revit commit veto; trigger must be rehearsed in a scratch document first | `uv run python tests/test_phase6_live_audit.py run ...` (human-run, one-shot) |
| Two Revit instances mutated simultaneously keep separate, uncorrupted entries | AUDIT-06 | Needs two Revit processes on the two-instance bench | `tests/test_phase6_live_audit.py` two-instance step set |

### Live gate results (plan 06-07, run 2026-10-25, Revit 2024)

The gate was run by the assistant on the user's explicit instruction ("запусти Revit и выполни проверку самостоятельно"),
which replaced the plan's "human-run" rule for this run. Scratch copies of two non-workshared test models were used, opened
through `open_model`, never saved, and the user's own project model was never opened. Both instances were stopped afterwards.

| Stage | Verdict | POSTS_SENT | SECRET_OCCURRENCES | Listener check | Record (operator machine) |
|-------|---------|------------|--------------------|----------------|---------------------------|
| Rehearsal of the rollback trigger (1 rehearsal) | `REHEARSAL_ROLLED_BACK` | 1 | n/a | one row on 48884 | audit dir `<scratchpad>/live/audit-rehearsal-1` |
| run-single (criterion 2, live look at 1 and 7) | `PHASE6_AUDIT_OK` | 3 | 0 | one row on 48884 | `<scratchpad>/live/single.json`, audit dir `<scratchpad>/live/audit-single` |
| run-dual (criterion 5) | `PHASE6_AUDIT_OK` | 20 | 0 | one row each on 48884 and 48885, two different PIDs | `<scratchpad>/live/dual.json`, audit dir `<scratchpad>/live/audit-dual` |

`<scratchpad>` is `C:/Users/Admin/AppData/Local/Temp/claude/c--Users-Admin-source-repos-revit-mcp-server/0d6381c7-6fb4-48bd-a175-b2785c1f20cc/scratchpad`.
No run stopped at preflight (POSTS_SENT=0), so no stage needed a rerun, and neither one-shot stage was repeated. `classify` on each
saved record re-judged both as `PHASE6_AUDIT_OK`.

What the audit files showed: the single-Revit file holds one `execute_revit_code` entry recorded as `rolled_back` (HTTP 409,
transaction `RolledBack`), one `tag_elements` entry recorded as `partial` (the missing element in `failed`), and one successful
`set_parameter` entry, all naming the same Revit process. The two-Revit run left two separate files (one per server process), each
holding 10 successful `set_parameter` entries that name both Revit processes, with no corruption.

Rollback trigger that worked live (research assumption A3 now confirmed): posting `DB.BuiltInFailures.GeneralFailures.ValueOutOfRange`
(Error severity) through `doc.PostFailure` from `execute_revit_code` produces a real `rolled_back` 409 and changes nothing in the model.

Deviation from the plan's steps: instance 1 kept its (unsaved) scratch copy open between Part A and Part B instead of being closed and
reopened, because the extra close-and-reopen added a save prompt risk and nothing else. It was the only document in that instance.

Limitation carried from 06-04: ROADMAP criterion 3 (one call_id across several bridge calls) is proven offline with a synthetic
multi-call tool, because no shipped tool makes more than one bridge call.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-10-25

---

## Validation Audit 2026-10-25

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Every requirement's automated command was re-run and selects at least one passing test (full suite: 6297 passed, 3 skipped;
`python tests/test_init_latency.py` gave `INIT_LATENCY_S=0.956`). The two live one-shot rows (AUDIT-03, AUDIT-06) stay manual-only
and are recorded green above.
