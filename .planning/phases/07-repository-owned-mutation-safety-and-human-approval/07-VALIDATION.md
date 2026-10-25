---
phase: "7"
slug: "repository-owned-mutation-safety-and-human-approval"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| SAFE-01 | Confirm op blocked without positive elicitation answer; `approved=true`/agent text ignored; nothing sent | unit + protocol | `uv run pytest tests/unit/test_phase7_channel.py -q` | ❌ W0 | ⬜ pending |
| SAFE-02 | No capability / decline / cancel / raise / timeout block with distinct reasons; stateless HTTP blocks | protocol | `uv run pytest tests/unit/test_phase7_channel.py -q` | ❌ W0 | ⬜ pending |
| SAFE-03 | Human wait happens before the bridge lock; no transaction held | unit | `uv run pytest tests/unit/test_phase7_wait_unlocked.py -q` | ❌ W0 | ⬜ pending |
| SAFE-04 | One accept = one call; session/always do not widen; windows unique and serialized | unit | `uv run pytest tests/unit/test_phase7_channel.py -q` | ❌ W0 | ⬜ pending |
| SAFE-05 | Russian window: tool/document/args/reasons/facts; "неизвестно" for unknowns; sanitized; length cap | unit | `uv run pytest tests/unit/test_policy_messages.py -q` | ❌ W0 | ⬜ pending |
| SAFE-06 | Policy covers all manifest tools + AST routes; unknown = deny; guard test | unit (AST) | `uv run pytest tests/unit/test_policy_inventory.py -q` | ❌ W0 | ⬜ pending |
| SAFE-07 | Parameter-write truth table; delete/transform/load/edit/execute confirm; create/read allow | unit | `uv run pytest tests/unit/test_policy_decisions.py -q` | ❌ W0 | ⬜ pending |
| SAFE-08 | FOP parse (UTF-16/UTF-8/BOM), GUID+name match, unreadable -> deny, Cyrillic exact | unit (fixtures) | `uv run pytest tests/unit/test_policy_fop.py -q` | ❌ W0 | ⬜ pending |
| SAFE-09 | TOML schema, overlay, closed vocabulary, hash; payload ships data file | unit | `uv run pytest tests/unit/test_policy_loader.py tests/unit/test_payload_ships_root_modules.py -q` | partial | ⬜ pending |
| SAFE-10 | Invalid/partial/unreachable operator file keeps last valid; invalid base blocks; atomic swap | unit | `uv run pytest tests/unit/test_policy_loader.py -q` | ❌ W0 | ⬜ pending |
| SAFE-11 | Permit round trip CPython -> Revit helper; golden vectors; every negative | unit | `uv run pytest tests/unit/test_permit_protocol.py -q` | ❌ W0 | ⬜ pending |
| SAFE-12 | Every gated route refuses without permit before effect; AST sentinel; concurrent consume = exactly 1 | unit + AST | `uv run pytest tests/unit/test_phase7_gate_wiring.py tests/unit/test_permit_concurrency.py -q` | ❌ W0 | ⬜ pending |
| SAFE-13 | Approval discarded on policy hash or facts digest change | unit | `uv run pytest tests/unit/test_phase7_channel.py -q` | ❌ W0 | ⬜ pending |
| SAFE-14 | `/status/` advertises permit protocol; new ext + old payload -> RU refusal; old ext tolerates key | unit | `uv run pytest tests/unit/test_phase7_rollout.py tests/unit/test_scan_envelope_tolerance.py -q` | partial | ⬜ pending |
| SAFE-15 | Audit labels `denied`/`expired`/`rejected_permit`; no new implicit error signal in `format_response` | unit | `uv run pytest tests/unit/test_audit_entry.py tests/unit/test_format_response.py tests/unit/test_phase7_audit.py -q` | partial | ⬜ pending |
| SAFE-16 | No resend after `unknown`; same permit twice -> second refused | unit | `uv run pytest tests/unit/test_phase7_channel.py tests/unit/test_permit_protocol.py -q` | ❌ W0 | ⬜ pending |
| SAFE-17 | Execute window shows code head, length, SHA-256 and warning; tool still registered | unit | `uv run pytest tests/unit/test_policy_messages.py -q` | ❌ W0 | ⬜ pending |
| SAFE-18 | Pinned bypass-limit sentences (arbitrary code, OS access/readable secret, 999.1, `load_family` contents) | unit | `uv run pytest tests/unit/test_phase7_scope_docs.py -q` | ❌ W0 | ⬜ pending |
| SAFE-19 | SDK bump keeps FastMCP registration, `user_request` on 59 tools, no `outputSchema`, stdio purity, 3 transports, cold start, payload import | unit + scripts | `uv run pytest tests/unit/test_audit_registration.py tests/unit/test_audit_stdio.py -q` ; `python tests/test_init_latency.py` | partial | ⬜ pending |
| SAFE-20 | Offline negative/concurrency suite; user-run live bench in Hermes Desktop after full Revit restart | manual + unit validator | live bench script (user-run) | ❌ W0 | ⬜ pending |
| SAFE-21 | ROADMAP criterion 2 reworded per D-15 | manual review | — | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

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

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
