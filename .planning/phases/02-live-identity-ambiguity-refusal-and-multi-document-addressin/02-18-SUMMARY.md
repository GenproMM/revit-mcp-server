---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '18'
subsystem: testing
tags: [live-acceptance, identity, multi-document, listener-collision, g6, human-checkpoint]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-01..02-17 and 02-19/02-20 production identity, registry, activation and discovery code that this plan observes live
provides:
  - "tests/test_phase2_live_identity.py: single-entry acceptance procedure (phase2-* / g2 / two / mut / g6 / collision commands) with one slot per ROADMAP criterion and per gate G1-G6"
  - "Live acceptance record for Phase 2 on Revit 2024: 8 of 9 criteria and gates G1-G5 observed, G6 stop"
  - "Classifier accepts the Russian-localized default unsaved title (UNSAVED_DEFAULT_TITLES)"
affects: [phase-2-verification, phase-4, backlog-999.1]

actuals:
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count f7514c5..HEAD (two of them are session/test commits, see Task Commits)
plan_head_before: f7514c5319218ffb617b7ca2757b3aad0a8cee08

key-files:
  created: []
  modified:
    - tests/test_phase2_live_identity.py
    - tests/unit/test_phase2_live_identity.py

key-decisions:
  - "Checkpoint verdict: the user answered `accept` to a choice that stated the facts (criterion c5 / AMBIG-04 / G6 is stop). This is recorded as acceptance WITH AMBIG-04 carried as an accepted open risk (backlog 999.1), NOT as nine observed criteria. The classifier verdict stayed `stop`."
  - "AMBIG-04 is not marked complete in REQUIREMENTS.md: the classifier did not assign a G6 outcome."
  - "The localized default title 'Проект1' is accepted by the two-process unit; a saved document or an arbitrary title is still refused (RED test first)."

requirements-completed: [IDENT-01, IDENT-02, IDENT-03, IDENT-04, AMBIG-01, AMBIG-02, AMBIG-03, MDOC-01, MDOC-02, MDOC-03, MDOC-04, MDOC-05]
requirements-open: [AMBIG-04]

coverage:
  - id: C1
    description: "Criteria c1-c4 and c6-c9 and gates G1-G5 observed live, per-criterion, on Revit 2024 (PIDs 52588, 36764, 8308)"
    requirement: "IDENT-01..04, AMBIG-01..03, MDOC-01..05"
    verification:
      - kind: manual_procedural
        ref: "C:\\Users\\Admin\\Documents\\revit-mcp-phase2-evidence-2026-10-23\\acc.json (phase2-classify)"
        status: pass
    human_judgment: true
    rationale: "Engineer looked at the Revit window and recorded every UI/dialog observation by hand."
  - id: C2
    description: "G6 / criterion c5 (AMBIG-04): sequential and overlapped param write/read with identity visible"
    requirement: "AMBIG-04"
    verification:
      - kind: manual_procedural
        ref: "acc.json g6 section; classifier: stop, g6-listing-unusable"
        status: fail
    human_judgment: true
    rationale: "Wrong-process hypothesis not supported (one PID/port/session in every reply); overlapped replies were cross-wired inside one Revit and one write was lost. Classifier stays stop."
  - id: C3
    description: "Offline unit suite and cold-start gate"
    requirement: "all"
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit -q -> 4054 passed, 3 skipped; tests/test_init_latency.py -> INIT_LATENCY_S=0.429"
        status: pass
    human_judgment: false

completed: 2026-10-23
status: human-checkpoint-accepted-with-open-risk
---

# Phase 2 Plan 18: Live acceptance Summary

**Eight of nine ROADMAP criteria and gates G1-G5 were observed live; G6 (criterion c5, AMBIG-04) is `stop`. The user accepted the checkpoint with that gap carried as an open risk.**

## Authorizations (recorded with the user's own words, 2026-10-22 21:20 UTC)

`mutation_authorized`, `g6_authorized`, `collision_authorized`: «Шаг 0. Все разрешаю» for mutations, G6 and the port collision, on the copies `D:\MCP_TEST_221026.rvt` and `C:\Users\Admin\Documents\MCP_TEST_221026.rvt` (SHA256 `b4b7c4c7…25e1`, unchanged before and after every section; nothing was saved or synced).

## Per-criterion result

| Criterion | Status | Observed |
|---|---|---|
| c1 IDENT-01 | observed | `/status/` PID/version/port/token; restart changed PID 63032→52588 and token; old selector refused with guidance |
| c2 IDENT-02/03 | observed | mutating reply names the changed document, also after activation and after a manual UI switch |
| c3 IDENT-04 | observed | two Revit (PID 52588:48884, PID 36764:48885) both with an unsaved «Проект1», distinguishable by response fields |
| c4 AMBIG-01..03 | observed | default and selected call refused naming PIDs [8308, 69116], zero connections reached the second listener |
| **c5 AMBIG-04** | **stop** | see G6 |
| c6 MDOC-01/02/04 | observed | list, explicit addressing, activation; inactive write HTTP 412 `document-not-active` |
| c7 MDOC-01 | observed | inactive reads (G3, both directions) without a UI switch |
| c8 MDOC-03 | observed | omitted document with one open → applied to it; with two open → HTTP 400 `document-selector-required` |
| c9 MDOC-05 | observed | stale token of a closed document → HTTP 404 `document-closed`, also after replacement (new token) |

Gates: G1 G2 G3 G4 G5 observed; G6 stop. Informational: http-thread and serialization observed; saved-workshared refusal not-run (no workshared bench model).

## G6 evidence (not an approval)

- Sequential (seq1, seq2, readback): all HTTP 200, each `old_value` equals the previous `new_value`, one PID/port/session throughout. No rollback reproduced.
- Overlapped (two writes plus a read, three server processes): all three calls received the **same** reply text («Set Комментарии from '' to 'g6-ovb' on element 286693»). The write to element 286692 reported success with that foreign text and was lost (readback `old=''`); the read returned that text instead of a document list.
- Identity in every reply was PID 8308, port 48884, one session: the wrong-process hypothesis is not supported by this run. The cross-wiring is the overlap limitation recorded as backlog 999.1; the per-process lock is not shown to cover it.
- Classifier: `g6-listing-unusable`, verdict `stop`. The run is one-shot by design and was not repeated.

## Task Commits

1. **Task 1 RED:** `bce0b40` (test) - acceptance procedure, authorization flags, gated sections
2. **Task 1 GREEN:** `1b7cfe7` (feat) - procedure and offline cases
3. **Task 2 (live):** no code; evidence in the local record (outside the repository)
4. **Fix found by the live run:** `4f3bc66` (fix) - localized default unsaved title; RED test first

## Deviations from Plan

1. **Lost one-shot case, corrected with the user's choice A.** `mut:active_named` was first sent with a parameter that element 311 (a Level) does not have («Комментарии»): HTTP 404 before any transaction, no write. The procedure never repeats a write, so with the user's explicit approval (option A) the case and its three `sent_calls` entries were removed from the working record and re-run with a valid wall parameter. Originals: `acc_attempt1_backup.json`, `acc_attempt3_backup_before_sentcalls_edit.json`.
2. **Mutation section reset.** Revit PID 52588 was closed overnight; the section held only start and two copy registrations (no case, no write). It was reset and restarted on PID 8308 (`acc_attempt2_backup_before_mutation_reset.json`).
3. **Classifier fix `4f3bc66`.** The two-process unit required the title `Project1`; a Russian Revit says «Проект1». User chose to teach the classifier (option P).
4. **Collision made with an auxiliary raw TCP listener** (`aux_listener.py`, SO_REUSEADDR), recorded as `auxiliary-routes-server`: it shows the production refusal on a real netstat collision, not automatic primary-port assignment.
5. **Section order.** Two Revit at once make an unselected bootstrap call ambiguous, so `http-thread`/`mut-start`/`g6-start` ran with one Revit; the two-process section was captured first.
6. A no-file-path document was produced with a temporary directory junction that was removed afterwards (open files cannot be renamed); that bench copy `…\mcp_nofile_real\MCP_TEST_nofile2_221026.rvt` and `MCP_TEST_nofile_221026.rvt` remain in Documents and can be deleted.

## Issues Encountered / Surprises

- Every commit prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied`; commits succeed (same note as 02-19).
- The `mcp__revit__get_element_properties` and `ai_element_filter` tools return counts only here; element ids came from `get_current_view_elements`.

## Known Stubs

None.

## Threat Flags

None. The only new surface is a bench-only local listener that was started and stopped by the procedure's operator.

## Next Phase Readiness

- AMBIG-04 stays open; fix belongs to backlog 999.1 (Revit-side handler serialization). Phase 4 batch-outcome claims are not made here.
- Raw evidence (PIDs, ports, tokens): `C:\Users\Admin\Documents\revit-mcp-phase2-evidence-2026-10-23\`.

## Self-Check: PASSED

- Commits exist: `bce0b40`, `1b7cfe7`, `4f3bc66`; `uv run pytest tests/unit -q`: 4054 passed, 3 skipped; `INIT_LATENCY_S=0.429`.
- Classifier on the live record: criteria c1-c4, c6-c9 observed, c5 stop, verdict stop (reproduced above).

---
*Phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin*
*Completed: 2026-10-23*
