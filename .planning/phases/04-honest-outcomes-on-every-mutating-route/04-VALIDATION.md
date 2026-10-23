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
| TRUTH-01..04 | Live: real `TransactionStatus`, partial on mixed-id batch, export | live, human | `python tests/test_phase4_live_outcomes.py` | ✅ | ✅ green: `PHASE4_OUTCOMES_OK`, POSTS_SENT=5 (2026-10-23) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Per-task map (filled by the planner, 2026-10-23)

Every task also runs `uv run pytest tests/unit -q` before its commit. AST gate = the one-line
`ast.walk` command in the task's acceptance criteria (no `.Commit` call, no discarded
`suppress_warnings`, no `{**a}` dict unpacking) printing `AST_GATE clean`.

| Task | Wave | Requirement | Test Type | Automated Command | Status |
|------|------|-------------|-----------|-------------------|--------|
| 04-01 T1 (tracer) | 1 | TRUTH-03, TRUTH-04 | unit, route to renderer | `uv run pytest tests/unit/test_routes_mep_parameter_identity.py -q -k "tag_elements and partial"` | ⬜ pending |
| 04-01 T2 | 1 | TRUTH-04, TRUTH-01 | pure unit | `uv run pytest tests/unit/test_textutils.py tests/unit/test_format_response.py tests/unit/test_conventions.py -q` | ⬜ pending |
| 04-01 T3 | 1 | TRUTH-01 | unit (fake pyRevit) | `uv run pytest tests/unit/test_routes_mep_parameter_identity.py -q -k tag_elements` | ⬜ pending |
| 04-02 T1-T3 | 2 | TRUTH-01, TRUTH-03, TRUTH-04 | unit (fake pyRevit) + AST gate | `uv run pytest tests/unit/test_routes_mep_parameter_identity.py -q` | ⬜ pending |
| 04-03 T1-T2 | 2 | TRUTH-01, TRUTH-03, TRUTH-04 | unit (fake pyRevit) + AST gate | `uv run pytest tests/unit/test_routes_analysis_color_identity.py -q` | ⬜ pending |
| 04-04 T1-T2 | 2 | TRUTH-02, TRUTH-01 | unit (fake pyRevit) + AST gate | `uv run pytest tests/unit/test_routes_document_interop_identity.py -q` | ⬜ pending |
| 04-05 T1-T2 | 2 | TRUTH-01 | unit (fake pyRevit) + AST gate | `uv run pytest tests/unit/test_routes_view_code_identity.py -q` | ⬜ pending |
| 04-06 T1-T3 | 3 | TRUTH-01, TRUTH-03, TRUTH-04 | unit (fake pyRevit) + AST gate | `uv run pytest tests/unit/test_routes_document_interop_identity.py -q` | ⬜ pending |
| 04-07 T1-T2 | 3 | TRUTH-01, TRUTH-03, TRUTH-04 | unit (fake pyRevit) + AST gate | `uv run pytest tests/unit/test_routes_analysis_color_identity.py -q` | ⬜ pending |
| 04-10 T1-T2 | 3 | TRUTH-01..04 (instrument) | offline unit | `uv run pytest tests/unit/test_phase4_live_outcomes.py -q` | ⬜ pending |
| 04-08 T1 | 4 | TRUTH-01 (D-02) | static (AST) | `uv run pytest tests/unit/test_conventions.py -q` | ⬜ pending |
| 04-08 T2 | 4 | TRUTH-01 (D-02) | scaffold generation + conventions | SCAFFOLD command in 04-08 Task 2 | ⬜ pending |
| 04-09 T1-T3 | 4 | TRUTH-03, TRUTH-04 | docstring contract | `uv run pytest tests/unit/test_outcome_docstrings.py -q` | ⬜ pending |
| 04-11 T1-T2 | 5 | TRUTH-01..04 | live, human, one-shot | `uv run python tests/test_phase4_live_outcomes.py classify RAW.json` | ✅ green (`PHASE4_OUTCOMES_OK`) |

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
| Partial on a mixed valid/invalid batch, visible in tool text | TRUTH-03, TRUTH-04 | Needs live Revit | `tag_elements` with `[valid id, 999999999]` in a plan view → 200 `partial`, PARTIAL banner with the bad id; one-shot once any POST is sent (a preflight STOP with `POSTS_SENT=0` sent nothing and is rerun to a fresh `--out`), clean up via `delete_elements` |

### Live gate result (plan 04-11, recorded 2026-10-23)

| Property | Value |
|----------|-------|
| **Verdict** | `PHASE4_OUTCOMES_OK` (script's own `classify_outcomes`, re-run on the saved record) |
| **POSTS_SENT** | 5 (one run; the one-shot gate is consumed and was not repeated; no earlier preflight-only records) |
| **Run date** | 2026-10-23 |
| **Listener check** | before the run: exactly one listener on 127.0.0.1:48884, one Revit process, started after the last `revit_mcp/` commit (full restart, not Reload) |
| **Preflight** | status answered, one listener, one document open, text parameter writable, tag target readable |
| **Record (operator machine)** | `C:/Users/Admin/Documents/revit-mcp-test-phase3/RAW.json` (IFC written to `.../out.ifc`, 57 KB) |
| **Run by** | the controller session at the operator's explicit request; scratch copy `MCP_TEST_221026.rvt`; nothing saved |

What the live reply showed, per step:

| Step | Route | Observed |
|------|-------|----------|
| s1 | `/modify_element/` | 200 `success`, `outcome.transaction_status` `Committed`, one parameter set |
| s2 | `/tag_elements/` with `[valid id, 999999999]` | 200 `partial`, valid id in `outcome.succeeded`, 999999999 `Element not found` in `outcome.failed` |
| s3 | `/tag_elements/` with `[999999999]` only | `Error: 422`, status `failed` (distinct from success and partial) |
| s4 | `/export_ifc/` | success, `Committed`, IFC path in `outcome.succeeded`, file exists |
| s5 | `/delete_elements/` of the tag created in s2 | 200 `success`, `Committed`, id in `outcome.succeeded` |

Rollback honesty is not exercised live (provoking an error-severity failure is out of scope); it stays covered by the unit route worlds.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
