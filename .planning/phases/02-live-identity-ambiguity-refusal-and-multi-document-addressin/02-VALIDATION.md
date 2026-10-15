---
phase: "02"
slug: "live-identity-ambiguity-refusal-and-multi-document-addressin"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-14"
---

# Phase 02 — Validation Strategy

> The automated suite proves contracts and refusal behavior without Revit. Live Revit evidence is mandatory before claiming process, document, activation, and UI-safety behavior. This is a draft strategy, not validation sign-off.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest via `uv run` for Revit-free unit tests; standalone Python script for cold-start; separately operated live Revit bench |
| **Config file** | Existing `tests/unit/` suite; no standalone pytest config required |
| **Quick run command** | `uv run pytest tests/unit` |
| **Full suite command** | `uv run pytest tests/unit` and `python tests/test_init_latency.py`; live gates G1–G6 separately, after a full Revit restart following `revit_mcp/` edits |
| **Estimated runtime** | Measure during execution; do not assume a live-bench duration |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit`.
- **After every plan wave:** Run `uv run pytest tests/unit` and `python tests/test_init_latency.py`.
- **Before `/gsd-verify-work`:** The unit/cold-start checks must pass and live gates G1–G6 must have recorded observations, not inferred passes.
- **Max feedback latency:** Measure the automated suite during the first execution wave; live checks are explicit human-controlled checkpoints rather than an automated latency promise.

---

## Per-Task Verification Map

The revised plans assign 02-20 to Wave 1 as the blocking G1–G5 preflight, followed by 02-01 (Wave 2) through 02-18 (Wave 12); 02-19 runs in Wave 5. The map below defines required checks. All named future tests remain missing until their producing plan runs; the commands are not currently runnable. This strategy remains a draft because the public arbitrary-code capability decision and live observations are unresolved.

| Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command / Live Gate | File Exists | Status |
|-------------|------------|-----------------|-----------|-------------------------------|-------------|--------|
| IDENT-01 | T-02-01 | Status identity contains PID, version, actual port and per-start token; stale incarnation refuses | unit + live | 02-20 W1: `uv run pytest tests/unit/test_phase2_preflight.py -q` and G1/G5; 02-01 W2: `uv run pytest tests/unit/test_target_resolution.py -x` | ❌ pending creation | ⬜ pending |
| IDENT-02 | T-02-02 | Mutating response visibly names the actual process/document after formatting, including received error replies | unit + live | 02-16 W10: `uv run pytest tests/unit/test_identity_rendering.py -x`; 02-12–02-15 W9 route contract tests; 02-18 W12 live mutation | ❌ pending creation | ⬜ pending |
| IDENT-03 | T-02-02 | Identity reflects activation and manual UI switch at request time | live | 02-20 W1 feasibility G2/G4; 02-18 W12 manual switch and request-time response | ❌ live | ⬜ pending |
| IDENT-04 | T-02-01 | Same-title unsaved documents in different processes differ by response identity | unit + live | 02-04 W5: `uv run pytest tests/unit/test_document_contracts.py -x`; 02-18 W12 two-instance bench | ❌ pending creation | ⬜ pending |
| AMBIG-01, AMBIG-02, AMBIG-03 | T-02-01 | Ambiguous listener snapshot refuses before model request and lists all conflicting PIDs | unit + live | 02-20 W1 preflight G5; 02-03 W4: `uv run pytest tests/unit/test_target_resolution.py -x`; 02-18 W12 live collision | ❌ pending creation | ⬜ pending |
| AMBIG-04 | T-02-02 | `param-write-rolls-back` wrong-process hypothesis is diagnosed from recorded identity, not presumed | live | 02-18 W12 G6 write/read reproduction and retained observations | ❌ live | ⬜ pending |
| MDOC-01 | T-02-03 | Live document list identifies each open document and active state | unit + live | 02-20 W1 G2; 02-04 W5: `uv run pytest tests/unit/test_document_contracts.py -x`; 02-18 W12 live list | ❌ pending creation | ⬜ pending |
| MDOC-02, MDOC-03 | T-02-03 | Explicit document accepted; omitted document defaults only for one eligible document, otherwise refuses with candidates | schema/unit + live | 02-04 W5: `uv run pytest tests/unit/test_document_contracts.py -x`; 02-08–02-15 W9 tool/route contract tests; 02-18 W12 multi-document bench | ❌ pending creation | ⬜ pending |
| MDOC-04 | T-02-03 | Explicit activation changes UI only on request; inactive-document mutation returns HTTP 412 | unit + live | 02-20 W1 G4 feasibility; 02-05 W6: `uv run pytest tests/unit/test_document_contracts.py -x`; 02-18 W12 activation/412 bench | ❌ pending creation | ⬜ pending |
| MDOC-05 | T-02-03 | Closed document selector refuses by name without active-document fallback | unit + live | 02-20 W1 G2 lifetime; 02-04 W5: `uv run pytest tests/unit/test_document_contracts.py -x`; 02-18 W12 close/retry | ❌ pending creation | ⬜ pending |
| D-11 comparison surface | T-02-03 | Only proven-safe summary/levels read inactive document while UI stays on active document | unit + live | 02-20 W1 G3 feasibility; 02-06 W7 guard tests; 02-18 W12 G3 A/B and B/A | ❌ pending creation | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Threat refs are validation identifiers, not a claim that Phase 3/5 security enforcement exists.*

---

## Preflight and Early-Wave Test Requirements

- [ ] 02-20 W1: `tests/test_phase2_preflight.py` and `tests/unit/test_phase2_preflight.py` — operator-only G1–G5 observation procedure, classifier and STOP branch; G1/OQ-5 must record both the process-start token facility and an authoritative Revit-side actual-port source reconciled with an independent OS listener/PID snapshot. No offline PASS for absent or inconsistent live evidence.
- [ ] 02-01 W2 and 02-03 W4: `tests/unit/test_target_resolution.py` — selector parsing, discovery defaults, OS listener adapter, no-send ambiguity, stale incarnation.
- [ ] 02-03 W4 creates and 02-19 W5 extends `tests/unit/test_target_locks.py` — same-target serialization, independent targets, incarnation-key isolation, status-only bypass.
- [ ] 02-16 W10 creates and 02-17 W11 extends `tests/unit/test_identity_rendering.py` — identity survives `message`/`result`/`data` and received errors; unsent/unknown outcomes do not claim a verified document.
- [ ] 02-02 W3 through 02-17 W11: `tests/unit/test_document_contracts.py` — document default/refusal/412/close-race, tool schemas and safe-read allowlist, expanded with route-family fixtures in 02-12–02-15 W9.
- [ ] 02-09, 02-10 and 02-11 W9: `tests/unit/test_tool_forwarding_documents.py`, `tests/unit/test_tool_forwarding_model.py` and `tests/unit/test_tool_forwarding_views.py` — separate task-local assertions for every owned registered callable's injected target keyword and every document-bound mutation's POST document field; each task runs its file before completion.
- [ ] 02-18 W12: `tests/test_phase2_live_identity.py` or equivalent recorded bench procedure — G1–G6 observations with actual PID, port, session token and UI state; do not mark a gate passed until the live bench runs.
- [ ] 02-03 W4, 02-04 W5 and 02-05 W6: update `tests/unit/tool_manifest.txt` alongside each new tool.
- [ ] Public arbitrary-code capability: no approved confinement or shutdown decision exists. A live G1 observation alone cannot establish whole-process isolation; keep phase sign-off blocked rather than claim `doc`-argument validation protects `/execute_code/`.

Do not add repository-local test shims or install packages to work around a sandbox; the existing suite is Revit-free. Existing regression coverage for bridge serialization, registration, conventions, target rendering and cold-start remains mandatory.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| pyRevit signature inspection and ExternalEvent dispatch | D-13 | Runtime injection must be verified on installed pyRevit | G1: inspect Routes implementation and run a nonmutating `doc`/`uidoc`/`request` probe before using a shared wrapper; identify the Revit-side actual-port and process-start token sources, reconcile port/PID with the independent listener snapshot, and STOP on missing or inconsistent evidence. |
| Document token lifecycle | MDOC-01, MDOC-05 | Revit object identity and close race need live models | G2: list same-title documents, address each, close one, retry stale token; record named refusal. |
| Inactive summary and levels | D-11 | Correct document data and UI stability cannot be proven by unit tests | G3: active A/read B, then active B/read A; compare distinct data and inspect UI after each read. Stop if either minimum route is unsafe. |
| Explicit activation | MDOC-04 | Saved, unsaved and workshared UI/dialog behavior differs | G4: activate each supported already-open case explicitly; record UI and any dialog; refuse unsupported cases without auto-switch. |
| Port collision | AMBIG-01..03 | Two-listener OS state must be observed | G5: intentionally establish two listeners at selected port; capture both PIDs and show no model request was sent. State the snapshot→send race honestly. |
| Wrong-process reproduction | AMBIG-04 | Outcome requires original live write/read conditions | G6: repeat sequential and overlapping `param-write-rolls-back` reproductions with recorded identities and mutation results; classify hypothesis only from evidence. |
| Process restart and same-title two-instance comparison | IDENT-01..04, D-02 | Process incarnation and actual route target need live evidence | Fully restart Revit after extension edits; compare token before/after and two unsaved `Project1` responses. |

---

## Validation Sign-Off

- [ ] Revised plans assign task IDs/waves to all mapped checks and specify observable failure signals for every runnable command; the 40/40 failure-direction probe passes, but future test paths and live measurements remain unverified.
- [ ] No three consecutive tasks lack automated verification or an explicit earlier-wave test dependency.
- [ ] The first execution wave creates its preflight tests before relying on them; later waves create their own focused checks.
- [ ] No watch-mode flags.
- [ ] Automated feedback latency measured.
- [ ] G1–G6 live results recorded, with any unsupported case left open rather than declared passed.
- [ ] `nyquist_compliant: true` set only after evidence exists.

**Approval:** pending
