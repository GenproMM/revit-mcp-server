---
phase: "7"
slug: "repository-owned-mutation-safety-and-human-approval"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: true
created: "2026-10-25"
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `07-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 8 (dev group), anyio plugin (`@pytest.mark.anyio`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options] testpaths = ["tests/unit"]`; fixtures `tests/unit/conftest.py` |
| **Quick run command** | `uv run pytest tests/unit/test_policy_*.py tests/unit/test_permit_*.py tests/unit/test_phase7_*.py -q` |
| **Full suite command** | `uv run pytest tests/unit -q` |
| **Cold start / payload gates** | `python tests/test_init_latency.py` (< 2.0 s); `deploy/gate.py` from a scratch payload layout (`GATE_OK`) |
| **Estimated runtime** | quick ~10 s; full ~100 s |

---

## Sampling Rate

- **After every task commit:** quick run command plus the touched module's existing test file
- **After every plan wave:** `uv run pytest tests/unit -q` and `python tests/test_init_latency.py`
- **Before `/gsd-verify-work`:** full suite green on mcp 1.30.0; scratch-payload `deploy/gate.py` prints `GATE_OK` with `INIT_LATENCY_S` < 2.0
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

Filled by the planner per task; requirement-level map below is the contract each task row must trace to.

| Req ID | Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|-----------|-------------------|-------------|--------|
| SAFE-01 | Confirm op blocked without positive elicitation answer; `approved=true`/agent text ignored; nothing sent | unit + protocol | `uv run pytest tests/unit/test_phase7_channel.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-02 | No capability / decline / cancel / raise / timeout block with distinct reasons; stateless HTTP blocks | protocol | `uv run pytest tests/unit/test_phase7_channel.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-03 | Human wait happens before the bridge lock; no transaction held | unit | `uv run pytest tests/unit/test_phase7_wait_unlocked.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-04 | One accept = one call; session/always do not widen; windows unique and serialized | unit | `uv run pytest tests/unit/test_phase7_channel.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-05 | Russian window: tool/document/args/reasons/facts; "неизвестно" for unknowns; sanitized; length cap | unit | `uv run pytest tests/unit/test_policy_messages.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-06 | Policy covers all manifest tools + AST routes; unknown = deny; guard test | unit (AST) | `uv run pytest tests/unit/test_policy_inventory.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-07 | Parameter-write truth table; delete/transform/load/edit/execute confirm; create/read allow | unit | `uv run pytest tests/unit/test_policy_decisions.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-08 | FOP parse (UTF-16/UTF-8/BOM), GUID+name match, unreadable -> deny, Cyrillic exact | unit (fixtures) | `uv run pytest tests/unit/test_policy_fop.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-09 | TOML schema, overlay, closed vocabulary, hash; payload ships data file | unit | `uv run pytest tests/unit/test_policy_loader.py tests/unit/test_payload_ships_root_modules.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-10 | Invalid/partial/unreachable operator file keeps last valid; invalid base blocks; atomic swap | unit | `uv run pytest tests/unit/test_policy_loader.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-11 | Permit round trip CPython -> Revit helper; golden vectors; every negative | unit | `uv run pytest tests/unit/test_permit_protocol.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-12 | Every gated route refuses without permit before effect; AST sentinel; concurrent consume = exactly 1 | unit + AST | `uv run pytest tests/unit/test_phase7_gate_wiring.py tests/unit/test_permit_concurrency.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-13 | Approval discarded on policy hash or facts digest change | unit | `uv run pytest tests/unit/test_phase7_channel.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-14 | `/status/` advertises permit protocol; new ext + old payload -> RU refusal; old ext tolerates key | unit | `uv run pytest tests/unit/test_phase7_rollout.py tests/unit/test_scan_envelope_tolerance.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-15 | Audit labels `denied`/`expired`/`rejected_permit`; no new implicit error signal in `format_response` | unit | `uv run pytest tests/unit/test_audit_entry.py tests/unit/test_format_response.py tests/unit/test_phase7_audit.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-16 | No resend after `unknown`; same permit twice -> second refused | unit | `uv run pytest tests/unit/test_phase7_channel.py tests/unit/test_permit_protocol.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-17 | Execute window shows code head, length, SHA-256 and warning; tool still registered | unit | `uv run pytest tests/unit/test_policy_messages.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-18 | Pinned bypass-limit sentences (arbitrary code, OS access/readable secret, 999.1, `load_family` contents) | unit | `uv run pytest tests/unit/test_phase7_scope_docs.py -q` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-19 | SDK bump keeps FastMCP registration, `user_request` on 59 tools, no `outputSchema`, stdio purity, 3 transports, cold start, payload import | unit + scripts | `uv run pytest tests/unit/test_audit_registration.py tests/unit/test_audit_stdio.py -q` ; `python tests/test_init_latency.py` | ✅ | ✅ green (offline, 2026-10-26) |
| SAFE-20 | Offline negative/concurrency suite; user-run live bench in Hermes Desktop after full Revit restart | manual + unit validator | live bench script (user-run) | ✅ | 🔴 blocked (PHASE7_BENCH_STOP, 2026-10-26) |
| SAFE-21 | ROADMAP criterion 2 reworded per D-15 | manual review | — | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### 07-14 Task 1 — final-tree offline evidence (2026-10-26)

Executed by the controller in the original checkout on `feature/local-revit-mcp-tools`, code HEAD `c90464c4a34acd4825ffc7353a546169eb5fe5a3`, after the user explicitly requested execution without subagents. Existing unrelated working-tree changes were retained. Only this validation record is part of the task commit.

Command adaptation: `PY` below is `C:/Users/Admin/.claude/projects/c--Users-Admin-source-repos-revit-mcp-server/phase7-test-venv/Scripts/python.exe` (mcp 1.30.0, pytest 9.1.1). The map's `uv run pytest` commands were executed as `PY -m pytest`; `python` was replaced with `PY`. The damaged shared `.venv` was not synchronized or changed. All checks below exited 0.

| Gate | Executed command / environment | Final output |
|------|--------------------------------|--------------|
| Complete unit suite | child `cmd.exe /d /c "chcp 866 >nul && PY -m pytest tests/unit -q"` (absolute unquoted interpreter path without spaces) | `6923 passed, 3 skipped in 120.25s (0:02:00)` |
| Cold start | `PY tests/test_init_latency.py` | `INIT_LATENCY_S=0.970` |
| Three transports | `PY tests/test_transports_smoke.py` | `TRANSPORT_OK streamable-http tools=59`; `TRANSPORT_OK sse tools=59`; `TRANSPORT_OK combined tools=59`; `TRANSPORTS_OK` |
| Scratch payload | `UV_OFFLINE=true`, `PY scripts/scratch_payload_gate.py --pyexe C:/Users/Admin/AppData/Roaming/pyRevit-Master/bin/cengines/CPY3123/python.exe --dest C:/Users/Admin/AppData/Local/Temp/revitmcp-07-14-offline-20261026` | `warm ok`; `SECRET=unchecked (MCP_SECRET_FILE not set)`; `POLICY=ok (base dd435f53b542)`; `POLICY_SOURCE=absent`; `INIT_LATENCY_S=1.090`; `TOOLS=59`; `MANIFEST=ok (59 tools)`; `GATE_OK`; `SCRATCH_GATE_OK` |

The scratch destination did not exist before this run. Dependencies were installed exclusively into its `app/libs` from the local uv cache with networking disabled; the embeddable interpreter and shared `.venv` were not modified. No production build or publish script was executed. The scratch gate proves payload layout/import/registration, not staged-secret matching or operator-policy/share readiness. The transport smoke only initialized/listed tools on temporary loopback MCP servers; it made no Revit calls.

Each distinct automated command in the SAFE-01..SAFE-19 map was also run separately (shared identical commands were run once):

| SAFE rows | Arguments after `PY -m pytest` (unless stated) | Exact final output |
|-----------|-----------------------------------------------|--------------------|
| 01, 02, 04, 13 | `tests/unit/test_phase7_channel.py -q` | `11 passed in 2.26s` |
| 03 | `tests/unit/test_phase7_wait_unlocked.py -q` | `1 passed in 3.21s` |
| 05, 17 | `tests/unit/test_policy_messages.py -q` | `18 passed in 2.35s` |
| 06 | `tests/unit/test_policy_inventory.py -q` | `10 passed in 1.19s` |
| 07 | `tests/unit/test_policy_decisions.py -q` | `31 passed in 0.84s` |
| 08 | `tests/unit/test_policy_fop.py -q` | `23 passed in 0.41s` |
| 09 | `tests/unit/test_policy_loader.py tests/unit/test_payload_ships_root_modules.py -q` | `52 passed in 0.59s` |
| 10 | `tests/unit/test_policy_loader.py -q` | `50 passed in 0.51s` |
| 11 | `tests/unit/test_permit_protocol.py -q` | `108 passed in 0.43s` |
| 12 | `tests/unit/test_phase7_gate_wiring.py tests/unit/test_permit_concurrency.py -q` | `25 passed in 0.68s` |
| 14 | `tests/unit/test_phase7_rollout.py tests/unit/test_scan_envelope_tolerance.py -q` | `65 passed in 3.66s` |
| 15 | `tests/unit/test_audit_entry.py tests/unit/test_format_response.py tests/unit/test_phase7_audit.py -q` | `144 passed in 2.00s` |
| 16 | `tests/unit/test_phase7_channel.py tests/unit/test_permit_protocol.py -q` | `119 passed in 2.44s` |
| 18 | `tests/unit/test_phase7_scope_docs.py -q` | `15 passed in 0.31s` |
| 19 | `tests/unit/test_audit_registration.py tests/unit/test_audit_stdio.py -q` | `15 passed in 3.09s` |
| 19 | `PY tests/test_init_latency.py` | `INIT_LATENCY_S=0.934` |

Row runner final line: `SAFE_01_19_AUTOMATED_ROWS_OK`. Green means the mapped automated checks passed, not that every listed behavior has been observed live. In particular, production policy/facts-change behavior, company FOP, IronPython behavior and Hermes rendering still need their applicable live/review evidence.

Invocation failure before the suite: the first Python-to-`cmd /d /s /c` launcher exited 1 with a path-not-found diagnostic before pytest started. Replacing only the launcher with the direct PowerShell-to-child-`cmd /d /c` command above passed; no test, production script or environment dependency was changed to resolve it.

Task 1 is complete. Task 2 is a **blocking-human** checkpoint; no live-bench command, Revit restart/reload, Hermes session, corporate-share access, company FOP read, publication, push or tag was performed. SAFE-20 and SAFE-21 remain pending; `status` and `nyquist_compliant` are unchanged. No completion SUMMARY or live verdict is claimed.

Operator-procedure clarification for Task 2 (from the delivered bench docstring): `--replies` requires a JSON object, not raw pasted assistant text. H4 is a declined deletion followed by the identical request again with a fresh operation code. Retain raw replies locally as supporting observations, and supply the JSON fields with actual Audit call IDs to `ingest`. This clarifies the older plan's `replies.txt` wording without claiming live evidence.

---

## Wave 0 Requirements

- [ ] `tests/unit/conftest.py` — autouse permissive test authorizer in `bridge` (production default fail-closed)
- [ ] `tests/unit/gate_support.py` — `request_of(body, route=...)` / `enveloped_body(...)` mint a real permit; update ~71 call sites
- [ ] `tests/unit/inventory_support.py`, `test_phase2_inventory.py`, `test_phase5_gate_wiring.py` — preflight route class, counts 56/41/7 -> 59/44/10, `scripts/conventions.py` open list + `LOCAL_MODULES`
- [ ] `tests/unit/test_audit_entry.py` — outcome label count 12 -> 15
- [ ] Shared fixtures: fake `ctx` with scripted elicitation, in-memory SDK elicitation harness with Hermes-shaped callback, policy TOML fixtures, FOP fixtures (UTF-16 LE / UTF-8), clock fake
- [ ] mcp 1.30.0 installed via `uv lock`/`uv sync` after the human-verify checkpoint (D-24)
- [ ] Live-bench script and its offline validator (user-run only)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hermes Desktop renders the window, Yes/No/timeout work end to end | SAFE-20 | Needs Hermes Desktop + live Revit; D-20 restricts to user-run bench | User runs live-bench script on a disposable model after full Revit restart |
| Redelivery, changed args, direct curl without permit refused before effect | SAFE-12, SAFE-16, SAFE-20 | Live Routes server | Same bench, scenarios listed in D-20 |
| HMAC vectors and float repr inside Revit's IronPython | SAFE-11 | Needs Revit's IronPython stdlib | Bench probe step |
| Payload-first rollout order (R3 pattern) | SAFE-14 | Fleet deployment | Operator runbook; user runs publish scripts |
| ROADMAP criterion 2 wording | SAFE-21 | Documentation review | Review the diff of ROADMAP.md |
| Operator-file share ACL is read-only for ordinary users | SAFE-09, SAFE-10 (D-27) | Share permissions owned by operator | Operator checks ACL before enabling the file |

---

## Live bench (D-20)

2026-10-26, user-run pilot `2026.10.26-1209.92fbaf5`, Revit **2024**. The controller received console output, not the complete evidence files. Readiness OK: one loopback listener, status 200, permit protocol 1, base policy `dd435f53b542`, blocked=false, operator absent. Direct stage: `DIRECT_CHECK_OK`. Final classifier output, copied unchanged:

```text
PHASE7_BENCH_STOP
POSTS_SENT=5
SECRET_OCCURRENCES=0
REASON=hermes.h1.audit: expected one audit entry
REASON=hermes.h1: expected accepted confirmed delete
REASON=hermes.h2.audit: expected one audit entry
REASON=hermes.h2: expected declined delete without effect
REASON=hermes.h3.audit: expected one audit entry
REASON=hermes.h3: expected expired
REASON=hermes.h4.audit: expected one audit entry
REASON=hermes.h4.audit: expected one audit entry
REASON=hermes.h4: each same-request audit entry needs approval
REASON=hermes.h5.audit: expected one audit entry
REASON=hermes.h5: expected accepted 12.5 mm fractional transform
REVIT_VERSION=2024
```

SAFE-20 remains **blocked / live STOP**, not green. SAFE-21 and phase sign-off remain pending. No direct or Hermes mutation is to be repeated to repair evidence.

- S6/S5a/S5b/S5c: direct-stage judge reported OK (missing/replay/changed-args/changed-route checks); five POST attempts, zero secret occurrences in recorded evidence. This is a stage result, not a replacement final verdict.
- H1: user saw and accepted the client card, confirmed the selected element disappeared. Reply reported one selected plus 13 hosted elements removed. Target audit row shown by the user: confirm/accepted/success.
- H2: declined; element remained; target audit confirm/declined/denied.
- H3: timed out after approximately five minutes; target audit confirm/expired/expired.
- H4: new card appeared for the second request, element remained, different call_ids, both target audits confirm/declined/denied. Operation codes were not recorded, so their difference is unverified; argument equality still needs the original evidence checked offline.
- H5: user accepted card and verified 12.5 mm global-X movement; target audit confirm/accepted/success.
- H6 Telegram/gateway: not verified (D-20).
- Hermes rendering: interactive confirmation card inside the Desktop session; a separate OS window was not required. Actual card contents/cascade prediction were not captured. The edit_family Revit-2025+ limitation does not apply to this Revit-2024 bench; edit_family itself was not live tested.

Read-only diagnosis of the saved final record: 25 entries in one audit segment. Each supplied call_id has one target-route row plus legitimate `/mutation_preflight/` rows (H1/H5: two; others: one). `_scenario_entry` incorrectly requires one row per call_id before filtering tool/route. This explains the STOP but **does not change it into a pass**. Fix the offline classifier with regression tests, then reclassify the original immutable evidence to a separate output without new HTTP or POST. Missing evidence or real duplicate target rows must still stop classification. Selection IDs/categories were also hidden by the tool's message-only projection; fix separately.

Raw evidence stays on the user's workstation outside the repository; no secret, full audit or model data is attached here. Full session context: Obsidian session “2026-10-26 — пилот Phase 7, live STOP из-за аудита”.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
