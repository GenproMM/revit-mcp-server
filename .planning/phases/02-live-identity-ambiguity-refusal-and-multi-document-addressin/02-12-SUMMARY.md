---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '12'
subsystem: api
tags: [mutation-guard, g1-explicit-route-only, response-attribution, http-412, ironpython3, annotation, building, colors, detail]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-04 mutation decision contract (decide_mutation_document, mutation_document_or_response in revit_mcp/identity.py); 02-07 rule that a handler runs in the Revit API context only if it declares uiapp, uidoc or doc; 02-08 tools that already send an optional document selector in the POST body; 02-20 accepted G1 explicit-route-only
provides:
  - "Eight mutating route handlers (annotation 2, building 3, colors 2, detail 1) call the guard explicitly first, before any document access or transaction; refusals are 503 / 400 / 404 / exact 412 with zero side effects"
  - "Every reply a guarded handler produces (success, validation error, 500, and the colour routes' HTTP 200 status:error body) carries the document descriptor it ran on and the process identity (IDENT-02)"
  - "revit_mcp/identity.py: guard takes the injected uiapp, request_document_selector(request), attribute_response(response, descriptor, uiapp=None)"
  - "tests/unit/test_routes_analysis_color_identity.py: 143 tests, real register_*_routes registration with a fake api and fake pyRevit, per-handler rows"
affects: [02-13, 02-14, 02-15, 02-16, 02-18]

actuals:
  tokens: 11048   # chars/4 over `git diff 98d61d7..HEAD` (44194 chars) at the last code commit; excludes this SUMMARY
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count 98d61d73c996e672b274a3bc6419a8ac4ce03c90..HEAD before this SUMMARY commit (#3968)
plan_head_before: 98d61d73c996e672b274a3bc6419a8ac4ce03c90

tech-stack:
  added: []
  patterns:
    - "Guard shell + unchanged body: the registered handler is a thin shell (selector, guard, run, stamp); the original handler body is kept verbatim as a nested function that now receives the guard's document, so transaction, unit and rollback code is untouched and the diff stays small"
    - "A reply is attributed by mutating the pyRevit Response's data dict in place (status and every other key kept); attribution never raises and never overwrites the outcome"
    - "Route tests import the real route module against a fake pyRevit and observe every document touch, collector and transaction in one event log, with an injected-doc decoy and a HOST_APP trap"

key-files:
  created:
    - tests/unit/test_routes_analysis_color_identity.py
  modified:
    - revit_mcp/identity.py   # outside files_modified, see Deviations
    - revit_mcp/annotation.py
    - revit_mcp/building.py
    - revit_mcp/colors.py
    - revit_mcp/detail.py
    # revit_mcp/analysis.py: in files_modified, deliberately NOT changed (no mutating route)

key-decisions:
  - "analysis.py is unchanged: all four of its routes (ai_filter, room_data, material_quantities, model_statistics) only read; ai_filter and material_quantities travel as POST and stay reads. A test pins that classification, so a future mutating route in any owned module fails until it is classified."
  - "Reply attribution key is `document` (the 02-04 descriptor: document, title, path, active, saved) plus `process_identity` (or `identity_error`). `document` is the same key and shape that /document_summary/ and /document_levels/ already use. None of the owned replies used a `document` key before."
  - "A request whose body cannot be parsed yields no selector (None), so the handler's own parse reports its own error exactly as before and nothing has been touched; a present-but-null `document` is returned as an invalid selector and is refused, never read as omitted."
  - "The handler runs its work on the Document the guard returned, never on the injected `doc`. The guard only returns the active document, so this is the same model; using the guard's object makes the attribution true by construction."
  - "The colour routes keep their HTTP 200 + status:error + message contract. The identity sits in the body beside that message."

patterns-established:
  - "Every mutating handler: signature (uiapp, doc, request); first statement the guard call; refusal returned as is; success and failure both stamped"
  - "Test row per handler for refusal-before-side-effect (503 no document, 400 several/invalid, exact 412, 404 closed), plus attribution on success, validation error and failure"

requirements-completed: []  # Deliberately empty (02-02..02-11 precedent). IDENT-02 / MDOC-02 / MDOC-03 / MDOC-05 cover every mutating route of the phase; 02-13..02-15 still guard the rest, and no route behavior has been observed on a real Revit.

coverage:
  - id: R1
    description: "Each of the eight changing handlers refuses before any transaction, collector or document access: no open document 503, several documents without a selector 400 (candidates listed), explicit inactive document exactly 412 with active_document, closed document 404, invalid selector (title, empty, null, number, list) 400 even with one open document"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_explicit_inactive_document_is_exactly_412_with_zero_side_effects"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_an_invalid_selector_is_400_and_never_decays_into_the_sole_document"
        status: pass
    human_judgment: false
  - id: R2
    description: "A selected active document is the one the handler works on (injected doc untouched, guard document touched) and every reply names its title, path and token and the process; an omitted selector with one active document works the same"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_active_selection_runs_on_the_resolved_document_and_names_it"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_sole_active_document_is_used_without_a_selector_and_named"
        status: pass
    human_judgment: false
  - id: R3
    description: "Replies produced after the guard keep the identity on failure and validation errors, including the colour routes' HTTP 200 status:error body; create_level success keeps status 200 and its original body keys"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_a_failure_after_the_guard_still_names_the_document_it_ran_on"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_color_failures_keep_their_http_200_error_body_and_gain_the_identity"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_create_level_success_keeps_its_body_and_opens_the_transaction_on_the_resolved_document"
        status: pass
    human_judgment: false
  - id: R4
    description: "Reads stay reads: the four analysis routes and list_category_parameters keep their signatures, call no guard, and answer without attribution; every registered route of the five modules is classified, so a new route cannot be missed"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_reads_keep_their_signature_and_are_not_guarded"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_every_registered_route_is_classified"
        status: pass
    human_judgment: false
  - id: R5
    description: "Every mutating handler declares uiapp, doc and request (pyRevit runs it in the Revit API context) and the guard and the attribution read nothing through HOST_APP"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_mutation_handler_declares_the_api_context_arguments"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_analysis_color_identity.py#test_the_guard_reads_everything_through_the_injected_uiapp"
        status: pass
    human_judgment: false
  - id: R6
    description: "Live behavior on a real Revit: pyRevit actually injecting uiapp together with doc and request into these eight handlers, the guard refusing and the work running on the active document, no transaction opened on a refusal, replies naming the changed document"
    requirement: "IDENT-02"
    verification:
      - kind: manual_procedural
        ref: "not run - needs a full Revit close and reopen (never pyRevit Reload), then 02-18"
        status: unknown
    human_judgment: true
    rationale: "The fake pyRevit models the dispatch rule proven from pyRevit source in 02-07; it does not prove how a real Revit handles these handlers. No live route was touched."

duration: "about 10 min of execution (start 2026-10-22T18:58:58Z, SUMMARY about 19:10Z)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 12: Explicit document guard on annotation, building, colors and detail mutations Summary

**Eight mutating routes (`/create_dimensions/`, `/tag_walls/`, `/create_line/`, `/create_surface/`, `/create_level/`, `/color_splash/`, `/clear_colors/`, `/create_detail_line/`) now call `mutation_document_or_response` as their first statement, refuse 503/400/404/exact 412 before any transaction, run their unchanged bodies on the document the guard resolved, and stamp that document's descriptor and the process identity onto every reply they produce.**

## Performance

- **Duration:** about 10 min (start 2026-10-22T18:58:58Z)
- **Tasks:** 2 of 2, both `tdd="true"` with a separate RED commit each
- **Files:** 1 created (test file), 5 modified (`identity.py` outside `files_modified`; `analysis.py` listed but unchanged)

## Accomplishments

- **Where the guard lives:** `decide_mutation_document` and `mutation_document_or_response` were already in `revit_mcp/identity.py` (a helper, not a registrar, and on the allowed-helper list in `test_registration.py`), so no move out of `documents.py` was needed and the "never import one domain from another" invariant holds: the route modules import only `.identity`.
- **Handler shape (G1, explicit, no wrapper):** each registered handler is `(uiapp, doc, request)`; the first statement calls `mutation_document_or_response(request_document_selector(request), uiapp=uiapp)`, a refusal is returned unchanged, otherwise the original handler body (kept verbatim as a nested function whose first argument is now the guard's document) runs and `attribute_response` stamps `document` and `process_identity`. Nothing is added to `startup.py` (the 02-04 test still pins that).
- **Order:** the guard precedes `DB.Transaction` in every handler (refusal rows assert the event log is empty: no transaction, collector or document touch; `create_level` success asserts the first events are `transaction`, `start` on the resolved document).
- **Reads stay reads:** `list_category_parameters` and the four analysis routes are untouched and unguarded; tests pin their signatures and that they never call the guard.
- **Colors:** `colors.py` gained one import and two guard shells (+18 lines, 1235 to 1253); no new route, no new helper, no split, original bodies and the `with DB.Transaction` / `suppress_warnings` code untouched.

### Handler signatures touched

| Route | Before | After |
|-------|--------|-------|
| `/create_dimensions/` `create_dimensions_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/tag_walls/` `tag_walls_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_line/` `create_line_based` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_surface/` `create_surface_based` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_level/` `create_level_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/color_splash/` `color_splash` | `(doc, request)` | `(uiapp, doc, request)` |
| `/clear_colors/` `clear_colors` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_detail_line/` `create_detail_line_handler` | `(doc, request)` | `(uiapp, doc, request)` |

`doc` and `request` are kept as declared (pyRevit still injects them by name); `uiapp` is added so the guard reads the application through the injected object, never `HOST_APP`.

## Task Commits

1. **Task 1 RED:** `0ce4dcf` (test) - 82 failing tests: guard rows, attribution and helper contracts for annotation/building (8 passed: classification and reads)
2. **Task 1 GREEN:** `8714d0c` (feat) - `identity.py` uiapp pass-through plus two helpers, annotation and building guarded
3. **Task 2 RED:** `0215412` (test) - 49 failing tests for colors and detail rows (all failures were colors/detail rows)
4. **Task 2 GREEN:** `7c390df` (feat) - colors and detail guarded

## Verification (real numbers)

- Plan verify `uv run pytest tests/unit/test_routes_analysis_color_identity.py tests/unit/test_document_contracts.py tests/unit/test_conventions.py -q`: **682 passed, 3 skipped** (Task 1: 629 passed, 3 skipped).
- `uv run pytest tests/unit -q`: **2233 passed, 3 skipped** (baseline 2090 passed, 3 skipped; +143, all in the new test file). No pre-existing failure.
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.365** (<2.0).
- Offline only. No `mcp__revit__*` tool was called, `/execute_code/` was not used, Revit and the live bridge were not touched (a Revit was open and left alone). No accidental live contact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The guard could not read the injected uiapp (revit_mcp/identity.py, outside `files_modified`)**
- **Found during:** Task 1 design (dispatch rule 1, from the 02-07 finding)
- **Issue:** `mutation_document_or_response` read the snapshot with `read_live_snapshot()` and the identity with `process_identity_or_error()`, both falling back to `HOST_APP` when given no uiapp. A route handler cannot use the guard without reaching `HOST_APP`, which 02-07 showed is not safe in the routes engine.
- **Fix:** optional `uiapp=None` on the guard, passed to `read_live_snapshot(uiapp)` and `process_identity_or_error(uiapp)` (default behavior unchanged; the existing 53 contract tests still pass). Added `request_document_selector` and `attribute_response`, the two pure never-raising helpers every route needs (rule 2 of the dispatch: shared pieces go in the helper module).
- **Files modified:** `revit_mcp/identity.py`
- **Commit:** `8714d0c`

**2. [Interface choice] `analysis.py` has nothing to guard**
- All four routes in `revit_mcp/analysis.py` are reads (two travel as POST, as the plan itself says to keep classified as reads). The file is in `files_modified` but is unchanged; a test pins the classification. The plan's wording "every changing route in these modules" is satisfied by zero routes there.

**3. [Interface choice] Guard shell around an unchanged nested body**
- Rather than threading the selector, the guard and the stamp through the many return statements of each handler, the original handler body is kept as a nested function (renamed, same indentation) and the registered handler wraps it. Every reply, including the early 400/404 validation replies and the outer 500, is therefore stamped, and the transaction and rollback code is textually unchanged.

**Total deviations:** 1 Rule 3 (one file outside `files_modified`), 2 interface notes. **Impact:** none on scope.

## Issues Encountered / Surprises

- `git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on every commit (stale registered worktree, same as 02-04/02-05). Commits succeed.
- Both RED runs failed for the intended reasons (no guard, missing helpers, missing `uiapp` argument); both GREEN runs passed at the first execution with no auto-fix attempt.
- The new test file is large because every handler gets the full refusal matrix; it does not import another test module (self-contained doubles).

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: local-path-disclosure | revit_mcp/identity.py (attribute_response) | Mutation replies now carry the changed document's title and full local path, as the listing routes already do (T-02-07, local MCP clients only; external authentication is Phase 5 and is not claimed). |

## Not run / not claimed

- **Live behavior is not run.** Whether pyRevit injects `uiapp` together with `doc` and `request` into these handlers, whether the guard and registry behave on a real Document in these routes, and that no transaction opens on a refusal: unobserved. G2-production, G5-production collision and G6 are not run (02-18; G6 not authorized).
- **`revit_mcp/` changed (identity.py, annotation.py, building.py, colors.py, detail.py).** The extension directory is a junction to this repo, so Revit needs a full close and reopen (never pyRevit Reload, which can crash the process) before any live route check.
- **Tool-side rendering of the stamp is not part of this plan.** The reply body carries `document` and `process_identity`; the tool renderers that surface them to the model belong to the provenance plans (02-13..02-17); `format_response` collapses `message`-bearing dicts, so route metadata alone is not yet model-visible.
- **Requirements:** `requirements-completed` stays empty. IDENT-02, MDOC-02, MDOC-03 and MDOC-05 span every mutating route; the save/documentation/editing/interop/family routes (02-13..02-15) and the rest are not yet guarded, and nothing was observed live.
- **Malformed bodies:** a body that cannot be parsed keeps its old behavior (the handler's own error reply, now stamped with the resolved document, with nothing touched); it is not a new 400.

## Next Phase Readiness

- 02-13..02-15 can copy this shape: import `mutation_document_or_response`, `request_document_selector`, `attribute_response` from `.identity`, make the handler `(uiapp, doc, request)`, guard first, run the body on the guard's document, stamp the reply. The test file's `World`/`load`/`call` doubles and per-row matrix are reusable by adding rows to `MUTATIONS`, `READS` and `REGISTRARS`.
- Stale docs outside this plan: CLAUDE.md "Current surface" counts and the `startup.py` / `documents.py` module notes.
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted per the dispatch instruction (they hold other sessions' uncommitted work).

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist in `git log`: `0ce4dcf`, `8714d0c`, `0215412`, `7c390df`; `git rev-list --count 98d61d73c996e672b274a3bc6419a8ac4ce03c90..HEAD` was 4 and the per-plan ledger file holds that base; no tracked file deleted by any of them.
- Files exist: `tests/unit/test_routes_analysis_color_identity.py`, `revit_mcp/identity.py`, `revit_mcp/annotation.py`, `revit_mcp/building.py`, `revit_mcp/colors.py`, `revit_mcp/detail.py`.
- `uv run pytest tests/unit -q`: 2233 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.365`.
