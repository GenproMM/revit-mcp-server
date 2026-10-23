---
phase: "4"
slug: "honest-outcomes-on-every-mutating-route"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-23"
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `04-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 8.0.0 (uv dev group) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests/unit"]` |
| **Quick run command** | `uv run pytest tests/unit/test_textutils.py tests/unit/test_format_response.py tests/unit/test_conventions.py -q` |
| **Route worlds command** | `uv run pytest tests/unit/test_routes_analysis_color_identity.py tests/unit/test_routes_document_interop_identity.py tests/unit/test_routes_mep_parameter_identity.py tests/unit/test_routes_view_code_identity.py -q` |
| **Full suite command** | `uv run pytest tests/unit -q` |
| **Estimated runtime** | ~60 seconds (baseline 4692 passed, 3 skipped) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command plus the one route-world file the task touched
- **After every plan wave:** Run `uv run pytest tests/unit -q`
- **Before `/gsd-verify-work`:** Full suite must be green (>= 4692 passed baseline + new tests) and the live gate recorded
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Filled in by the planner per task; the requirement-level map is:

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| TRUTH-01 | No bare `.Commit()` in `revit_mcp/` outside `commit_and_report` | static (AST) | `uv run pytest tests/unit/test_conventions.py -q` | ❌ W0 | ⬜ pending |
| TRUTH-01 | Migrated route returns 409 `rolled_back` + `outcome.transaction_status == "RolledBack"` when the world's commit status is RolledBack (all 4 worlds) | unit (fake pyRevit) | route worlds command | ❌ W0 | ⬜ pending |
| TRUTH-01 | Success reply carries `outcome` with `transaction_status == "Committed"`, `requested`, `succeeded` | unit (fake pyRevit) | route worlds command | ❌ W0 | ⬜ pending |
| TRUTH-02 | `delete_elements` commits via `commit_and_report`; rollback → 409; missing id → 404 before any transaction (D-05) | unit | `uv run pytest tests/unit/test_routes_document_interop_identity.py -q` | ❌ W0 | ⬜ pending |
| TRUTH-02 | `export_ifc` rollback → 409; `Export()` False with committed tx → 422 `failed` | unit | `uv run pytest tests/unit/test_routes_document_interop_identity.py -q` | ❌ W0 | ⬜ pending |
| TRUTH-03 | Batch with mixed valid/invalid ids returns both `succeeded` and `failed` lists | unit | route worlds command | ❌ W0 | ⬜ pending |
| TRUTH-04 | `classify_outcome` truth table (409 / 200 success / 200 partial / 422 failed, incl. (True,0,0)) | pure unit | `uv run pytest tests/unit/test_textutils.py -q` | ❌ W0 | ⬜ pending |
| TRUTH-04 | `format_response` renders partial banner, "Succeeded: N of M", failed ids + reasons; partial is not an error; 422 passes through | unit | `uv run pytest tests/unit/test_format_response.py -q` | ❌ W0 | ⬜ pending |
| TRUTH-01..04 | Live: real `TransactionStatus`, partial on mixed-id batch, export | live, human | `python tests/test_phase4_live_outcomes.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `revit_mcp/textutils.py` — `classify_outcome` (+ pure outcome finaliser) and truth-table tests in `tests/unit/test_textutils.py`
- [ ] `tools/utils.py` — `partial` branch + `tests/unit/test_format_response.py` pair + 422-string test (D-08, D-09)
- [ ] `scripts/conventions.py` — bare-`.Commit()` check + `tests/unit/test_conventions.py` tests; scaffolds `scripts/new_tool.py`, `contrib-kit/revitmcp_kit.py`, `CONTRIBUTING.md`, `CLAUDE.md` updated (D-02)
- [ ] analysis/color world fake — `commit_status` + `DB.TransactionStatus` so `Commit()` and `commit_and_report` agree
- [ ] Per-item failure injection hook in each route world (missing element id / raising creation call) to produce partial and failed deterministically

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real `TransactionStatus` reaches `outcome` (single-element, batch, export) | TRUTH-01, TRUTH-02 | Needs live Revit + pyRevit Routes after a full restart | One listener on 48884; scratch unsaved document; `modify_element`, `export_ifc` to scratch path; never save |
| Partial on a mixed valid/invalid batch, visible in tool text | TRUTH-03, TRUTH-04 | Needs live Revit | `tag_elements` with `[valid id, 999999999]` in a plan view → 200 `partial`, PARTIAL banner with the bad id; one-shot, clean up via `delete_elements` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
