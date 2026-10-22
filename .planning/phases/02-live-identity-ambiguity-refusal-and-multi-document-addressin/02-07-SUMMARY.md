---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '07'
subsystem: testing
tags: [g3-production, g4-production, live-recheck, pyrevit-api-context, uiapp-injection, addressed-reads, activation, ironpython3]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-04 documents registry and routes, 02-05 explicit activation, 02-06 addressed summary and levels reads, 02-20 accepted G3 document-only-path and G4 explicit-activation-api mechanisms, 02-02 operator-procedure pattern
provides:
  - "tests/test_phase2_live_identity.py: classify_g3_production and classify_g4_production (pure, never raising, never an approval) and the g34-start / g3-read / g4-case / g34-observe / g34-classify operator commands, schema phase2-g34-production-v1"
  - "tests/unit/test_phase2_live_identity.py: offline no-false-PASS cases for both production classifiers (every STOP condition, the not-run outcome, and no approval verdict)"
  - "A recorded live production recheck of G3 and G4 on Revit 2024 after a full Revit restart: verdicts g3-production-observed and g4-production-observed, engineer choice observed"
  - "Two live-bench bug fixes outside this plan's file list: activation-failed exception diagnostics (02-05 scope) and the API-context uiapp injection for the four documents routes (02-04 scope)"
affects: [02-08, 02-09, 02-10, 02-11, 02-12, 02-13, 02-14, 02-15, 02-18]

actuals:
  tokens: 52775   # chars/4 over `git diff 5cf3c96..HEAD` (211100 chars, 7 files) at the last code commit; excludes this SUMMARY
  tasks: 2
  commits: 7      # MEASURED: git rev-list --count 5cf3c96ad0731083685c52bd77dcc24bbb59547d..HEAD before this SUMMARY commit (#3968)
plan_head_before: 5cf3c96ad0731083685c52bd77dcc24bbb59547d

tech-stack:
  added: []
  patterns:
    - "Every pyRevit Routes handler that touches the Revit API MUST declare an argument named uiapp, uidoc or doc: pyRevit runs only such handlers in the Revit API context (UI.ExternalEvent, main thread); a handler with only request (or none) runs on the HTTP server thread outside the API context. Pinned by an AST test over every @api.route handler in revit_mcp/documents.py"
    - "A live gate classifier is a pure never-raising function over a recorded evidence file; it prints an *-observed verdict plus approval=not-granted, never an approval; the operator command that prints the sentinel only runs on a live non-synthetic record"
    - "A hardware-facing fact proven by reading the host's own source (pyRevit server.py _handle_route, handler.py wants_api_context/prepare_handler_kwargs) beats an inferred one: the root cause of the activation failure was established that way, not by guessing"

key-files:
  created: []
  modified:
    - tests/test_phase2_live_identity.py
    - tests/unit/test_phase2_live_identity.py
    - revit_mcp/documents.py
    - revit_mcp/identity.py
    - revit_mcp/textutils.py
    - tools/document_tools.py
    - tests/unit/test_document_contracts.py

key-decisions:
  - "G3/G4 production verdicts are observed, not approved: both classifiers and the g34-classify command print an *-observed verdict with approval=not-granted; the human choice (observed) is recorded here, not derived by code."
  - "Engineer choice for the blocking-human decision: observed, taken on the authoritative third run only (g34-production-3.json). The first run (g34-production.json) classified G4 STOP and the second (g34-production-2.json) was diagnostic; neither is used as evidence of observed behavior."
  - "MDOC-04 is observed ONLY within the narrowed saved-existing-path class (non-workshared). Saved workshared activation stays refused and unmeasured; other inactive reads beyond summary and levels stay unsupported."
  - "Rule applied to every later route: a handler must declare uiapp, uidoc or doc, and must use the injected object for every Revit API touch (HOST_APP is no longer read in documents.py). Documented for plans 02-08..02-15."
  - "The /model_info/ and /status/ handlers that declare none of uiapp/uidoc/doc were surveyed read-only and NOT changed; recorded as a follow-up concern (/status/ may be deliberately off the API thread so it answers during Revit startup)."
  - "requirements-completed stays empty: MDOC-04 is observed on the narrowed class only, and IDENT-03, MDOC-01, MDOC-05 are advanced but not closed (no mutating reply names its document yet, no broad sweep, G2-production and G5-production collision gates are 02-18)."

patterns-established:
  - "Plan-level live gate with an engineer-controlled bench and a per-case human observation field (ui, dialog_required_input, data_matches_addressed) that callbacks and policy acceptance can never fill"
  - "A live gate that fails is rerun in full after the fix and the later run supersedes, with the failed runs kept as evidence of the divergence (machine-local, outside the repo)"

requirements-completed: []  # Deliberately empty. See key-decisions: MDOC-04 observed on the narrowed class only; IDENT-03, MDOC-01, MDOC-05 advanced, not closed.

coverage:
  - id: D1
    description: "G3 production classifier: observed only for two distinct documents read in both directions, target_is_active false, active document unchanged by Equals before and after each read, returned identity and data belonging to the addressed document; STOP for any missing direction, UI change, synthetic record or unset engineer observation"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_live_identity.py (G3 production classifier cases)"
        status: pass
    human_judgment: false
  - id: D2
    description: "G4 production classifier: observed only when the saved existing-path case activated on the explicit call with the observed active document equal to the target, every exercised refusal returned its reason with the UI unchanged, and every case has an explicit engineer dialog observation; saved-workshared allow attempt and an unset dialog field are STOP; an absent refusal class is not-run, never pass; no classifier can return an approval verdict"
    requirement: "MDOC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_live_identity.py (G4 production classifier cases)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The four documents routes (/documents/, /activate_document/, /document_summary/, /document_levels/) run in the Revit API context: every handler declares uiapp, uidoc or doc, uses the injected uiapp for every Revit API touch, and an AST pin fails if a new @api.route handler in documents.py declares none"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py (API-context pin and HostAppTrap tests, commit a3f84b9 RED, 2764d51 GREEN)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A 500 activation-failed reply carries an exception diagnostic (type, message, inner exception chain) rendered by the activate_document tool, so a failed activation names its cause"
    requirement: "MDOC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py and tests/unit/test_textutils.py (commits c9d9e21 RED, df1eb56 GREEN)"
        status: pass
    human_judgment: false
  - id: D5
    description: "G3 live production behavior on Revit 2024 (PID 57588): an addressed summary and levels read of an inactive document returns that document's own data with the active document unchanged, in both directions (A active / B read, then B active / A read)"
    requirement: "MDOC-01"
    verification:
      - kind: manual_procedural
        ref: "C:\\Users\\Admin\\revit-recheck-captures\\g34-production-3.json (machine-local), g34-classify -> g3-production-observed"
        status: pass
    human_judgment: true
    rationale: "Whether a real FilteredElementCollector read on a nonactive Document moves the UI is a live Revit fact the offline fakes cannot show; the engineer observed the window and the data."
  - id: D6
    description: "G4 live production behavior on Revit 2024 (PID 57588): activate_document on the saved existing-path document activates only on the explicit call and shows no dialog; unsaved and detached documents are refused 422 with the active document unchanged and no dialog"
    requirement: "MDOC-04"
    verification:
      - kind: manual_procedural
        ref: "C:\\Users\\Admin\\revit-recheck-captures\\g34-production-3.json (machine-local), g34-classify -> g4-production-observed"
        status: pass
    human_judgment: true
    rationale: "Whether the active window changed and whether any dialog requiring input appeared is an independent engineer observation; callback completion never fills it."
  - id: D7
    description: "Saved workshared activation refusal, G2-production same-title pair and close-then-replacement, G5-production collision, and G6 on the production routes"
    verification: []
    human_judgment: true
    rationale: "Not run. saved_workshared was optional and the bench had no such model; G2-production and G5-production are 02-18; G6 is not authorized."

# Metrics
duration: "about 10h 50m wall clock (2026-10-22T07:31Z to 18:22Z), almost all of it engineer-controlled bench and two live-bug fix cycles; agent execution time much smaller"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 07: G3/G4 production recheck Summary

**G3 (addressed summary and levels reads of an inactive document, both directions) and G4 (explicit activation of a saved existing-path document, refusal of unsaved and detached documents) are observed on the production routes on Revit 2024 after a full restart, but only after the live bench exposed that the four documents routes ran outside the Revit API context; declaring `uiapp` on each handler fixed it, and the engineer chose `observed` on the third, authoritative run.**

## Performance

- **Duration:** about 10h 50m wall clock (start about 2026-10-22T07:31Z, last bench observation 18:21Z), mostly the engineer-controlled bench and two fix cycles
- **Tasks:** 2 of 2 (Task 1 auto/tdd, Task 2 blocking-human checkpoint resolved `observed`)
- **Commits:** 7 (2 for Task 1, 5 for the two bench-found gaps)
- **Files modified:** 7 (2 in `files_modified`, 5 outside it, see Deviations)

## Accomplishments

- **Task 1:** `classify_g3_production` and `classify_g4_production` in `tests/test_phase2_live_identity.py` are pure, never-raising, and cannot return an approval verdict. G3 is observed only for two distinct documents read in both directions with `target_is_active` false, the active document equal before and after each read, and the returned identity and data belonging to the addressed document. G4 is observed only when the saved existing-path case activated on the explicit call with the observed active document equal to the target, each exercised refusal returned its reason with the UI unchanged, and every case has an explicit engineer dialog observation. An unset dialog field, a saved-workshared allow attempt, a missing direction, or a synthetic record is STOP; an absent refusal class is not-run. Operator commands `g34-start`, `g3-read`, `g4-case`, `g34-observe`, `g34-classify` record schema `phase2-g34-production-v1`. The unit file has RED-first cases for every STOP condition.
- **Task 2 (live, engineer-controlled):** after a full Revit close and reopen, the third run recorded G3 in both directions and G4 allow plus two refusals, all with the engineer's independent UI and dialog observations, and the engineer chose `observed`.
- **Bench-found fixes (outside the plan's file list):** exception diagnostics in the activation-failed reply, and the Revit API-context fix for all four documents routes with an AST pin so later routes cannot regress it.

## Task Commits

1. **Task 1 RED:** `7f7d22d` (test) - failing G3/G4 production classifier and g34 procedure tests
2. **Task 1 GREEN:** `7cd3894` (feat) - G3/G4 production classifiers and g34 operator commands
3. **Task 2:** blocking-human checkpoint, no code commit; resolved `observed` (see Live Evidence)
4. **Gap A RED (02-05 scope):** `c9d9e21` (test) - failing activation-failed exception diagnostics tests
5. **Gap A GREEN (02-05 scope):** `df1eb56` (fix) - record exception diagnostics in the activation-failed reply
6. **Gap B RED (02-04 scope):** `a3f84b9` (test) - failing API-context tests for the documents routes
7. **Gap B identity pass-through (02-04 scope):** `23ce119` (feat) - the live snapshot and process identity read an injected uiapp
8. **Gap B GREEN (02-04 scope):** `2764d51` (fix) - run the documents routes in the Revit API context via an injected uiapp

**Plan metadata:** the docs commit that adds this SUMMARY (`docs(02-07)`); STATE.md and ROADMAP.md are updated through gsd-tools and deliberately left uncommitted (they hold other sessions' work).

## Files Created/Modified

- `tests/test_phase2_live_identity.py` - production G3/G4 classifiers, g34 operator commands, `exception` lines in the g4-case output
- `tests/unit/test_phase2_live_identity.py` - offline no-false-PASS tests for both classifiers
- `revit_mcp/documents.py` - handlers now `list_documents(uiapp)`, `activate_document(uiapp, request)`, `document_summary(uiapp, request)`, `document_levels(uiapp, request)`; `HOST_APP` no longer used; `exception` key in the 500 activation-failed reply
- `revit_mcp/identity.py` - `read_live_snapshot(uiapp=None)` and `process_identity_or_error(uiapp=None)` optional pass-through
- `revit_mcp/textutils.py` - `exception_diagnostics` pure helper
- `tools/document_tools.py` - `activate_document` renders the exception diagnostic
- `tests/unit/test_document_contracts.py` - API-context AST pin, HostAppTrap tests, exception-diagnostics tests

## Live Evidence (authoritative run: g34-production-3.json)

Machine-local raw captures live outside the repo in `C:\Users\Admin\revit-recheck-captures\`: `g34-production.json` + `g34-transcript.txt` (first run), `g34-production-2.json` (diagnostic run), `activation-diag.txt` (execute_code diagnostic), and the authoritative `g34-production-3.json` + `g34-transcript-3.txt`. The third run was re-read read-only and `g34-classify` re-run offline on it for this SUMMARY: all values below match the file.

**Bench:** Revit 2024, PID 57588, actual_port 48884 (listener owners `[57588]`), session_token `cfc3f5db-9625-4feb-b833-d2b2cee0b8be`, schema `phase2-g34-production-v1`, `live: true`, `synthetic: false`, recorded 2026-10-22. Four documents open:

| # | Document | Class | Token |
|---|----------|-------|-------|
| 1 | Р_Низино_ПТОР_maggenda_отсоединено | detached | doc1.c90626afe12d.1 |
| 2 | Проект1 | unsaved | doc1.c90626afe12d.2 |
| 3 | Window_Test_R2024 (`C:\Users\Admin\Documents\RevitFamilies\Window_1500x1500_R2024\Window_Test_R2024.rvt`) | saved | doc1.c90626afe12d.3 |
| 4 | MCP_TEST_221026 (`C:\Users\Admin\Documents\MCP_TEST_221026.rvt`) | saved | doc1.c90626afe12d.4 |

**G3, addressed reads (production routes /document_summary/ and /document_levels/):**

| Slot | Active before | Target | Summary / levels returned | target_is_active | ui_switched | Active after | Engineer observation (UTC) |
|------|---------------|--------|---------------------------|------------------|-------------|--------------|----------------------------|
| a_active_b_read | .4 | .3 Window_Test_R2024 | non_type_elements=2233, level_count=2; levels: Уровень 1 0.0 mm, Window test level 0.0 mm | false | false | .4 | ui=unchanged, data matches, 18:08:58Z |
| b_active_a_read | .3 | .4 MCP_TEST_221026 | elements=3775, level_count=2; levels: Уровень 1 0.0 mm, Уровень 2 4000.0 mm | false | false | .3 | ui=unchanged, data matches, 18:14:38Z |

Verdict `g3-production-observed`; `PHASE2_G3_PRODUCTION_OBSERVED approval=not-granted`. Note: the engineer observation for G3 recorded `ui` and `data` only; `dialog_required_input` is null for the G3 slots (the plan requires the per-case dialog field for G4, which is set). Skipped levels were 0 in both reads.

**G4, explicit activation (production route /activate_document/):**

| Case | Target | Reply | Active before -> after | Engineer observation (UTC) |
|------|--------|-------|------------------------|----------------------------|
| allow | .4 MCP_TEST_221026 (saved, existing path) | HTTP 200, activation=activated, observed_active_document=.4 | .3 -> .4 | ui=target-active, dialog=none, 18:16:11Z |
| unsaved | .2 Проект1 | HTTP 422, reason=unsaved | .4 -> .4 | ui=unchanged, dialog=none, 18:17:27Z |
| detached_or_non_file | .1 Р_Низино_ПТОР_maggenda_отсоединено | HTTP 422, reason=detached | .4 -> .4 | ui=unchanged, dialog=none, 18:21:54Z |
| saved_workshared | not-run (optional; none on the bench) | - | - | - |

Verdict `g4-production-observed`; `PHASE2_G4_PRODUCTION_OBSERVED approval=not-granted`. Allow was requested once.

**Engineer choice: `observed`.** MDOC-04 is observed ONLY within the narrowed saved-existing-path class (non-workshared). Saved workshared activation remains refused and unmeasured; other inactive reads beyond summary and levels remain unsupported.

**Not run (never passes):** G2-production same-title pair and close-then-replacement (02-18); G5-production collision (02-18); saved-workshared refusal case (no such model on the bench); G6 (not authorized). `execute_code` stayed enabled (D-15) and was used once only, engineer-run, for the diagnostic described in Deviation 2.

## Decisions Made

See `key-decisions`. In short: the verdicts are observed, not approved; the third run alone is the evidence; MDOC-04 is observed on the narrowed class only; the API-context rule is now documented and pinned for every later route; `/model_info/` and `/status/` were surveyed and left alone.

## Deviations from Plan

The live bench found a real bug in code delivered by 02-04, 02-05 and 02-06, in files outside this plan's `files_modified`. All of it was fixed inside this plan because the Task 2 gate cannot be observed without it. Sequence:

### Auto-fixed Issues

**1. [Rule 1 - Bug] G4 allow returned HTTP 500 activation-failed on the first live run**
- **Found during:** Task 2 (first run, `g34-production.json`, 2026-10-22 about 12:17)
- **Issue:** G3 was observed in both directions (`ui_switched=False`), but G4 allow for the saved eligible document Window_Test_R2024 returned HTTP 500 activation-failed with `observed_active_document=None`, the active window unchanged and no dialog. Refusals for unsaved and detached were 422 as expected. The classifier stopped G4 (`allow-not-activated`, `engineer-ui-unexpected`, `listing-unusable`), as designed.
- **Fix:** None directly; this triggered the diagnosis below.
- **Files modified:** none
- **Verification:** classifier STOP is the evidence; raw capture kept machine-local.

**2. [Rule 3 - Blocking] Diagnostic attempt through /execute_code/ proved nothing**
- **Found during:** Task 2 diagnosis
- **Issue:** `activation-diag.txt` shows the attempt failed with "The active document is currently modifiable." because `/execute_code/` opens a transaction before running code, so it said nothing about the production route. A safety classifier initially blocked the orchestrator from running it and the engineer ran the script manually. It changed no document; MCP_TEST_221026 stayed active.
- **Fix:** abandoned; replaced with exception diagnostics (next item).
- **Files modified:** none
- **Verification:** the same documents were checked unchanged afterwards by the engineer.

**3. [Rule 2 - Missing critical functionality] Activation-failed reply carried no cause (02-05 scope)**
- **Found during:** Task 2 diagnosis
- **Issue:** a 500 activation-failed reply named nothing about the exception, so the failure could not be diagnosed from the bench.
- **Fix:** `exception_diagnostics` pure helper in `revit_mcp/textutils.py`, an `exception` key in the 500 activation-failed reply, rendered by `activate_document` in `tools/document_tools.py`; the g4-case command prints the exception lines. The second run (`g34-production-2.json`) then exposed `Autodesk.Revit.Exceptions.InternalException` "A managed exception was thrown by Revit or by one of its external applications." from `UIApplication.OpenAndActivateDocument(String)`, with no inner exception.
- **Files modified:** `revit_mcp/textutils.py`, `revit_mcp/documents.py`, `tools/document_tools.py`, `tests/unit/test_document_contracts.py`, `tests/test_phase2_live_identity.py`
- **Verification:** RED `c9d9e21`, GREEN `df1eb56`; offline suite green.
- **Committed in:** `c9d9e21`, `df1eb56`

**4. [Rule 1 - Bug] Root cause: documents routes ran outside the Revit API context (02-04 scope, affects 02-04, 02-05, 02-06)**
- **Found during:** Task 2 diagnosis, after the second run
- **Issue:** proven by reading pyRevit's own source (`pyrevitlib/pyrevit/routes/server/server.py` `_handle_route` and `handler.py` `wants_api_context` / `prepare_handler_kwargs`): pyRevit runs a route handler in the Revit API context (UI.ExternalEvent, `Execute(uiapp)`, main thread) only if the handler declares an argument named `uiapp`, `uidoc` or `doc`. Handlers with only `request` (or none) run on the HTTP server thread outside the API context. The four routes added by 02-04..02-06 (`/documents/`, `/activate_document/`, `/document_summary/`, `/document_levels/`) declared no such argument, so `OpenAndActivateDocument` ran off the API thread and Revit refused it. The earlier G3 reads had also run off-thread, so G3 had to be re-measured; the first-run G3 result is not used.
- **Fix:** handlers are now `list_documents(uiapp)`, `activate_document(uiapp, request)`, `document_summary(uiapp, request)`, `document_levels(uiapp, request)`; the injected `uiapp` is used for every Revit API touch (`identity.read_live_snapshot(uiapp=None)` and `process_identity_or_error(uiapp=None)` take it as an optional pass-through); `HOST_APP` is no longer used in `documents.py`; an AST pin test asserts every `@api.route` handler in `documents.py` declares `uiapp`, `uidoc` or `doc`; HostAppTrap tests fail if the module reaches for `HOST_APP`. The docs now state the rule for plans 02-08..02-15: every new route handler MUST declare `uiapp`, `uidoc` or `doc`.
- **Files modified:** `revit_mcp/documents.py`, `revit_mcp/identity.py`, `tests/unit/test_document_contracts.py`
- **Verification:** RED `a3f84b9`, then `23ce119` (identity pass-through) and `2764d51` (documents.py). Offline suite 1536 passed, 3 skipped; `scripts/conventions.py` clean; `INIT_LATENCY_S` 0.412. Live: after a full Revit restart the third run observed G3 in both directions and G4 allow plus refusals.
- **Committed in:** `a3f84b9`, `23ce119`, `2764d51`

**5. Survey (read-only, no change): other handlers outside the API context**
- The only other `revit_mcp` route handlers that declare none of `uiapp`/`uidoc`/`doc` are `get_model_info()` (`/model_info/`, `revit_mcp/model_info.py`) and `revit_status(verbose=None)` (`/status/`, `revit_mcp/status.py`). They run on the HTTP thread. NOT changed: the `/status/` one may be deliberate so it answers during Revit startup, and neither was in scope. Recorded as a follow-up concern.

---

**Total deviations:** 4 fixes inside the plan (1 live failure that triggered the diagnosis, 1 blocked diagnostic path, 1 missing-diagnostics gap, 1 root-cause bug) plus 1 read-only survey. 7 commits, 5 of them outside `files_modified`.
**Impact on plan:** the plan's gate caught a real defect that offline tests could not (the CPython suite has no pyRevit dispatch). The fixes are necessary for any live behavior of the documents routes and are now pinned. No change to the read contract was made to get a pass: the same G3/G4 acceptance was applied to the third run as the plan states, and the failed first and second runs were not reinterpreted.

## Issues Encountered

- First live run STOPped G4 (see Deviation 1); the plan's rule "If the saved existing-path activation fails, STOP for a user decision" was followed: the divergence was reported and the engineer chose to fix and rerun.
- pyRevit Reload was not used; each `revit_mcp/` edit was followed by a full Revit close and reopen before a live run (CLAUDE.md).
- `/execute_code/` opens a transaction, so it cannot call `OpenAndActivateDocument`; it is not a valid way to reproduce activation.
- The g3 engineer observation did not capture `dialog_required_input` (null for both G3 slots); the G4 cases all have it.

## Known Stubs

None.

## Threat Flags

None new. T-02-03 is mitigated by this gate (production reads returned the addressed document's data with `ui_switched=false` in both directions); T-02-08 by activating only the measured allow class and exercising unsaved and detached only as refusals (no dialog); T-02-13 by no save, reopen or source-path retry (saved-workshared not exercised). The injected-`uiapp` change narrows, not widens, the trust surface.

## Not run / not claimed

- **MDOC-04 beyond the narrowed class:** saved workshared activation is not measured and not claimed; the refusal path for it was not exercised on this bench.
- **Other inactive reads** beyond summary and levels remain unsupported.
- **G2-production** same-title pair and close-then-replacement, and **G5-production** collision: 02-18.
- **G6:** not authorized, not touched.
- **Requirements:** `requirements-completed` is empty. IDENT-03, MDOC-01 and MDOC-05 are advanced, not closed. MDOC-04 is observed on the narrowed class only.
- **Machine-local evidence:** the raw captures are outside the repo; this SUMMARY records their values but not the files.
- **Revit restart:** any later edit under `revit_mcp/` needs a full Revit close and reopen before a live run (never pyRevit Reload).

## Next Phase Readiness

- Wave 9 (02-08..02-15) can proceed on demonstrated summary/levels reads and the narrowed activation. Every route handler added by those plans MUST declare `uiapp`, `uidoc` or `doc`, and the AST pin in `tests/unit/test_document_contracts.py` currently covers `documents.py` only; extend or add the same pin for any new route module.
- Follow-up concern: `get_model_info()` and `revit_status()` run on the HTTP thread. Decide deliberately whether either should move into the API context; `/status/` may need to stay off it so it answers during startup.
- Stale docs outside this plan: CLAUDE.md "Current surface" tool and route counts.
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted per the dispatch instruction.

## Self-Check: PASSED

Verified before writing this line:
- Commits exist in `git log`: `7f7d22d`, `7cd3894`, `c9d9e21`, `df1eb56`, `a3f84b9`, `23ce119`, `2764d51`; `git rev-list --count 5cf3c96ad0731083685c52bd77dcc24bbb59547d..HEAD` was 7, and the per-plan ledger file holds that same base.
- Files exist on disk: `tests/test_phase2_live_identity.py`, `tests/unit/test_phase2_live_identity.py`, `revit_mcp/documents.py`, `revit_mcp/identity.py`, `revit_mcp/textutils.py`, `tools/document_tools.py`, `tests/unit/test_document_contracts.py`.
- `C:\Users\Admin\revit-recheck-captures\g34-production-3.json` exists (45655 bytes), was read read-only, and contains the PID 57588, port 48884, session token, four document tokens, G3 values (2233 / 3775 elements, levels, `ui_switched` false, active before/after), G4 replies (200 activated; 422 unsaved; 422 detached; saved_workshared not-run), and engineer observations; `g34-classify` re-run offline on it printed `g3-production-observed` and `g4-production-observed`, both `approval=not-granted`.
