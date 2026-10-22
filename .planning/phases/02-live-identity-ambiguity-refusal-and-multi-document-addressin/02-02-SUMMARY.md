---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '02'
subsystem: testing
tags: [identity, live-recheck, netstat, session-token, operator-procedure, retained-reference-doubles]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-01 selected-status vertical slice (bridge selector/listener_snapshot, revit_mcp/identity.py, /status/ process_identity); 02-20 accepted G1/G2/G5 mechanisms
provides:
  - "tests/test_phase2_live_identity.py: standalone operator procedure with never-raising classify_identity_recheck, make_selector, evidence_template and not-run slots for later gates"
  - "tests/unit/test_phase2_live_identity.py: offline no-false-PASS classifier tests (one case per STOP reason)"
  - "tests/unit/test_document_contracts.py: Wave-0 retained-reference-equals-v1 Document doubles for 02-04 (fixtures, not production evidence)"
  - "A recorded live production identity recheck after a full Revit close/reopen: verdict recheck-observed, engineer choice observed"
affects: [02-03, 02-04, 02-18]

actuals:
  tokens: 18000   # chars/4 over `git diff 8490e2e a8925ee` (72067 chars); excludes the uncommitted netstat-fix work (see Deviations)
  tasks: 2
  commits: 2      # MEASURED: git rev-list --count 8490e2e..HEAD before this SUMMARY commit (#3968); the SUMMARY docs commit and the uncommitted netstat fix are not counted
plan_head_before: 8490e2ea4d59d3515cb5bc35a6a8374c4ae191cd

tech-stack:
  added: []
  patterns:
    - "Operator procedures live outside pytest collection in tests/, with a pure never-raising classifier unit-tested offline via importlib under a distinct module name"
    - "A live verdict is only ever printed by the operator run on a live non-synthetic record; the classifier never emits an approval"

key-files:
  created:
    - tests/test_phase2_live_identity.py
    - tests/unit/test_phase2_live_identity.py
    - tests/unit/test_document_contracts.py
  modified:
    - bridge.py   # uncommitted netstat fix, see Deviations
    - tests/test_phase2_preflight.py   # uncommitted
    - tests/unit/test_target_resolution.py   # uncommitted
    - tests/unit/test_phase2_preflight.py   # uncommitted

key-decisions:
  - "Engineer choice at the blocking-human checkpoint: observed (2026-10-22). Production identity matches the accepted G1/G5 mechanisms on a model-less full restart; 02-03 may start."
  - "netstat output is decoded as ASCII with errors=replace and heading lines before the first TCP row are skipped by shape (no host:port field), not by language-specific text; any later non-TCP line or garbled data row still fails closed."
  - "The strict run (identity-recheck-2.json) is authoritative; the earlier run (identity-recheck.json) is kept as evidence only."

patterns-established:
  - "Listener inventory parsing is shape-based and encoding independent; the heading before the first data row is not trusted for content"

requirements-completed: []  # Deliberately empty. IDENT-01/03/04, AMBIG-01/02/03, MDOC-01/05 are only partly advanced by an identity recheck; none is closed by this plan (G2-production, G3, G4, G5-production, G6 are not-run).

coverage:
  - id: D1
    description: "Offline classifier never yields recheck-observed for synthetic, partial, contradictory or non-GET/status records; make_selector round-trips through bridge.parse_target"
    requirement: "IDENT-01"
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit/test_phase2_live_identity.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Wave-0 retained-reference Document doubles (same title, same filename, close-replacement, IsValidObject-raises) with self-tests"
    requirement: "MDOC-01"
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit/test_document_contracts.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Production identity on a freshly restarted Revit: PID/port/token via the shared entry, also on the no-document 503; stable token per incarnation, different across a full restart; old selector refused"
    requirement: "IDENT-03"
    verification:
      - kind: manual_procedural
        ref: "C:\\Users\\Admin\\revit-recheck-captures\\identity-recheck-2.json (machine-local); sentinel PHASE2_IDENTITY_RECHECK_OBSERVED"
        status: pass
    human_judgment: true
    rationale: "Live bench observation with an engineer-controlled full restart; the raw captures are machine-local and cannot be replayed by automation. Scope is model-less no-document identity only."

duration: "~5 days wall-clock (dominated by waiting for the engineer-controlled bench; not a measure of effort)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 02: Production identity recheck Summary

**Production 02-01 identity (PID, Revit version, actual port, per-incarnation GUID session token) was observed live on a model-less Revit across a full close/reopen, with the netstat owner matching the reported PID and the old selector refused with rediscovery guidance; a netstat parsing defect on ru-RU Windows found by that recheck was fixed outside the committed file list.**

## Performance

- **Started:** 2026-10-17T08:05:03+01:00 (first task commit)
- **Completed:** 2026-10-22 (recheck recorded 2026-10-22T06:29:46Z)
- **Tasks:** 2 of 2 (Task 1 auto/tdd, Task 2 blocking-human decision, resolved: observed)
- **Files committed by this plan:** 3 created tests + this SUMMARY; the netstat fix files remain uncommitted (below)

## Accomplishments

- Standalone operator procedure `tests/test_phase2_live_identity.py` with `make_selector`, never-raising `classify_identity_recheck`, `evidence_template` and an operator `main()` on the stdio-client skeleton; no `test_*` functions; not-run slots for G2-production, G3, G4, G5-production collision and G6 that can never yield a pass.
- Offline classifier tests `tests/unit/test_phase2_live_identity.py`, written RED first (commit `69a0a69`), one case per STOP reason, selector round-trip, never-raises on malformed input, spy proving inventory comes only through `bridge.listener_snapshot`.
- Wave-0 `tests/unit/test_document_contracts.py`: retained-reference-equals-v1 `FakeDocument`/`FakeApplication` doubles (fixtures for 02-04, not production registry evidence).
- Live production recheck, engineer controlled, recorded as observed (table below).

## Task Commits

1. **Task 1 RED: classifier tests** - `69a0a69` (test)
2. **Task 1 GREEN: procedure + Wave-0 doubles** - `a8925ee` (feat); includes a 7-line fixture fix in `tests/unit/test_phase2_live_identity.py`
3. **Task 2: production recheck (blocking-human decision)** - no code commit; evidence is machine-local, choice **observed**

**Plan metadata:** the docs commit that adds this file (`docs(02-02): record production identity recheck observed after full restart`).

Offline suite after Task 1: 970 passed, 3 skipped (baseline 790/3 before this plan's tests and other sessions' work).

## Live evidence (Task 2, engineer-controlled, human choice: observed, 2026-10-22)

Raw captures are machine-local, outside the repository: `C:\Users\Admin\revit-recheck-captures\identity-recheck-2.json` (strict run, authoritative, `recorded_at` 2026-10-22T06:29:46.693470+00:00, schema `phase2-identity-recheck-v1`, `live: true`, `synthetic: false`, route namespace `genpro_revit_mcp`) and `identity-recheck.json` (earlier run, kept as evidence; see Issues). Revit was started with NO model both times, with a full close/reopen between incarnations; never pyRevit Reload, never force-kill.

| Item | Incarnation 1 | Incarnation 2 (after full restart) |
|---|---|---|
| PID | 7316 | 43376 |
| actual_port | 48884 | 48884 |
| Revit version | 2024 | 2024 |
| session_token | 4b7d0419-e8c2-48a7-8abd-c8a1cf96b45e | c76a30f1-a99f-4b4d-bba1-5e2a8ee3af5a |
| netstat owners of port (bridge.listener_snapshot) | [7316] | [43376] |
| Owners snapshot time | 2026-10-20T12:39:42.632128Z | 2026-10-22T06:29:46.269780Z |
| Bootstrap status (no selector) | 2026-10-20T12:39:42.607Z, 503 no-document with full identity | 2026-10-22T06:29:46.244Z, 503 no-document with full identity |
| Selected replies | 2, both kind no-document, identity present: 2026-10-20T12:39:42.854Z, 12:39:43.055Z | 2, both kind no-document, identity present: 2026-10-22T06:29:46.466Z, 06:29:46.671Z |
| Token stable within incarnation | yes (same token in bootstrap and both replies) | yes |

- Token differs across the restart; PID differs across the restart; actual_port is the same (48884), as expected for a single Revit.
- Old selector retry (2026-10-22T06:29:46.690993Z): `accepted=False`, `rediscovery_guidance=True`, text `Error: Listener PID mismatch (owners [43376]); request not sent. Rediscover targets.` (old selector token 4b7d0419-e8c2-48a7-8abd-c8a1cf96b45e).
- Sent routes: **7 requests, all `GET /status/`** (bootstrap, 2 selected, bootstrap, 2 selected, old-selector). The old-selector request was refused by the bridge before any HTTP was sent, per its recorded text.
- Classifier verdict: **recheck-observed**; sentinel `PHASE2_IDENTITY_RECHECK_OBSERVED`; approval **not-granted** (the classifier never approves).
- Engineer choice: **observed**.

### Not-run slots (never passes)

| Gate | Status | Reason |
|---|---|---|
| g2_production | not-run | retained-reference document registry is 02-04; the doubles are fixtures, not evidence |
| g3 | not-run | inactive-document read safety is a later live gate |
| g4 | not-run | production activation is a later live gate |
| g5_production_collision | not-run | duplicate-listener refusal through production code stays with 02-18 (no duplicate-listener condition was created) |
| g6 | not-run | write/read reproduction needs separate explicit user authorization; not authorized |

No model mutation, no `execute_code`, no pyRevit Reload, no route other than `GET /status/`. Scope of the observation: identity on a model-less Revit 2024 (no-document 503) only. It does not cover a document-bearing status, multiple instances, or IPY342 behaviour under other Revit versions.

## Decisions Made

- Resolved the blocking-human checkpoint as **observed**; 02-03 may start (it builds on the observed production identity and the netstat fix).
- Treat `identity-recheck-2.json` as authoritative; keep `identity-recheck.json` as evidence.
- Keep requirements un-closed (`requirements-completed: []`): an identity recheck advances IDENT-01/03/04 and AMBIG/MDOC groundwork but closes none of them.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1/3 - Bug/Blocking] netstat heading mis-decoded on ru-RU Windows made the listener inventory unavailable**
- **Found during:** Task 2 (the live recheck)
- **Issue:** `netstat.exe` prints its banner/heading in OEM cp866, which the cp1251 locale mis-decodes. `bridge.parse_netstat_listener_rows` rejected the unknown heading, `listener_snapshot` returned `None`, the classifier STOPped `inventory-unavailable`, and every selected `get_revit_status(target=...)` would have refused with "Listener inventory unavailable".
- **Fix (made at the user's instruction "make fix"):** (1) `bridge.parse_netstat_listener_rows` and the AST-pinned copy in `tests/test_phase2_preflight.py` now skip lines BEFORE the first TCP row when no field parses as host:port (shape-based, language and encoding independent); any non-TCP line after the first row, or a garbled data row, still fails closed; no rows returns `None`. (2) `bridge.listener_snapshot` and the preflight `os_listener_snapshot` run netstat with `encoding="ascii", errors="replace"`. (3) Tests: two pinned-kwargs tests updated (`tests/unit/test_target_resolution.py`, `tests/unit/test_phase2_preflight.py`) and regression tests added using the real cp866 heading bytes in `tests/unit/test_target_resolution.py`.
- **Files modified:** `bridge.py`, `tests/test_phase2_preflight.py`, `tests/unit/test_target_resolution.py`, `tests/unit/test_phase2_preflight.py` (outside the plan's `files_modified` list)
- **Verification:** 975 passed, 3 skipped; `scripts/conventions.py` clean; `INIT_LATENCY_S=0.724`; live `bridge.listener_snapshot([48884])` returned `{48884: [91920]}` matching netstat at that moment.
- **Committed in:** NOT committed. These four files also hold earlier uncommitted 02-01 work, so committing them from this plan would bundle unrelated work. The user must decide how to commit them.

---

**Total deviations:** 1 auto-fixed (Rule 1/3), uncommitted
**Impact on plan:** The fix was required for any selected-status call on a Russian-locale Windows host; without it the recheck could not pass. It is a narrow parser/decoding change; fail-closed behaviour for malformed rows is retained. The production observation recorded above was taken with this fix in place.

## Issues Encountered

- The earlier run (`identity-recheck.json`, 2026-10-17) classified STOP `no-document-reply-missing` for incarnation 1 because that start had model "Проект1" open, so there was no no-document 503 to check. Everything else matched. It was re-run strictly with Revit started model-less both times; the strict run is the authoritative record.
- The 02-02 plan-head ledger (`gsd-plan-head-before-02-02`) was not created by the Task 1 agent; it was created at SUMMARY time with the parent of the first task commit (`8490e2e`), and `commits: 2` was measured from it.

## User Setup Required

None. `workflow.use_worktrees=false` was set in untracked `.planning/config.json` so executors run sequentially on the dirty tree (revert: `gsd-tools query config-set workflow.use_worktrees true`).

## Next Phase Readiness

- 02-03 (wave 4) may start; it builds on the observed production identity and the netstat parsing fix.
- Still open and not claimed here: G2-production (02-04), G3, G4, G5-production collision (02-18), G6 (unauthorized).
- Before 02-03 relies on a committed baseline, the uncommitted netstat fix in `bridge.py` and tests (interleaved with 02-01 work) must be committed or otherwise preserved by the user.
- Raw captures live only on this machine at `C:\Users\Admin\revit-recheck-captures\`; they are not in the repository.

## Known Stubs

None. The not-run slots in `evidence_template()` are intentional, honest placeholders that cannot yield a pass.

## Threat Flags

None. No new network endpoints, auth paths or schema changes were added by the committed files.

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits `69a0a69` and `a8925ee` exist (`git show --stat`); `git rev-list --count 8490e2e..HEAD` was 2.
- Files exist: `tests/test_phase2_live_identity.py`, `tests/unit/test_phase2_live_identity.py`, `tests/unit/test_document_contracts.py`.
- Raw capture `C:\Users\Admin\revit-recheck-captures\identity-recheck-2.json` exists and was read; this SUMMARY's PID/port/token/netstat owners/timestamps/sent-route count/verdict values match it (7 routes, owners [7316] and [43376], tokens as tabled).
- `uv run pytest tests/unit -q`: 975 passed, 3 skipped.

---
*Phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin*
*Completed: 2026-10-22*
