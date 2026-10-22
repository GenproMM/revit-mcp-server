---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '14'
subsystem: api
tags: [mutation-guard, g1-explicit-route-only, response-attribution, http-412, http-409-rollback, ironpython3, mep, parameters, rooms, structure, tags]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-04 mutation decision contract (mutation_document_or_response in revit_mcp/identity.py); 02-07 rule that a handler runs in the Revit API context only if it declares uiapp, uidoc or doc; 02-12/02-13 guard-shell shape with request_document_selector / attribute_response; 02-20 accepted G1 explicit-route-only
provides:
  - "Nine mutating route handlers (mep 3, parameters 1, rooms 2, structure 2, tags 1) call the guard explicitly first, before any collector, element lookup or transaction; refusals are 503 / 400 / 404 / exact 412 with zero side effects"
  - "Every reply a guarded handler produces carries the document descriptor and the process identity, including validation errors, exception replies and the 409 rolled_back reply of set_parameter"
  - "set_parameter: the 409 rolled_back branch is byte-for-byte unchanged and is pinned as an error that names the attempted document, so a later, separately authorized G6 run can read which process and document a rolled-back write was attempted on"
  - "tests/unit/test_routes_mep_parameter_identity.py: 200 tests, real register_*_routes registration with a fake api and fake pyRevit"
affects: [02-15, 02-16, 02-18]

actuals:
  tokens: 12431   # chars/4 over `git diff 064b1fc..HEAD` (49724 chars) at the last code commit; excludes this SUMMARY
  tasks: 2
  commits: 3      # MEASURED: git rev-list --count 064b1fc66a2db5fa7d0e37e3517217621338ace0..HEAD before this SUMMARY commit (#3968)
plan_head_before: 064b1fc66a2db5fa7d0e37e3517217621338ace0

tech-stack:
  added: []
  patterns:
    - "Guard shell + unchanged nested body (02-12 shape): selector, guard, run the original body on the guard's Document, stamp the reply"
    - "Row tables in the test file (MUTATIONS, TRANSACTING, EXPECTED_KEYS, READS, REGISTRARS): a new route in any of the five modules fails until it is classified"

key-files:
  created:
    - tests/unit/test_routes_mep_parameter_identity.py
  modified:
    - revit_mcp/mep.py
    - revit_mcp/parameters.py
    - revit_mcp/rooms.py
    - revit_mcp/structure.py
    - revit_mcp/tags.py

key-decisions:
  - "Classification by what a route does: create_duct, create_pipe, create_mep_system, set_parameter, create_room, create_room_separation, create_grid, create_framing, tag_elements change a document and are guarded. project_parameters and element_properties only read, keep their signatures and stay active-document-only; a test pins every registered route of the five modules."
  - "The route bodies are unchanged: no f-string, no new import beyond .identity, the same transactions with suppress_warnings right after Start, the same mm to feet conversions, the same per-element exception handling. Only the registered entry point changed (uiapp, doc, request) and gained the guard."
  - "set_parameter's rollback is not reshaped: the 409 body keys are the original ones; attribute_response adds document and process_identity next to them and nothing else."
  - "Handlers that read doc.ActiveView (create_room_separation, tag_elements) now read it from the guard's Document. Because the guard only accepts an active document, that is the same model the user sees, and it is no longer the injected doc."

patterns-established:
  - "Mutation handler: signature (uiapp, doc, request); first statement the guard call; refusal returned as is; success and failure both stamped"

requirements-completed: []  # Deliberately empty (02-02..02-13 precedent). IDENT-02 / IDENT-03 / MDOC-02 / MDOC-03 / MDOC-05 cover every mutating route of the phase; 02-15 and 02-16 still guard the rest, and no route behavior has been observed on a real Revit.

coverage:
  - id: R1
    description: "Each of the nine changing handlers refuses before any collector, element lookup or transaction: no open document 503, several documents without a selector 400 (candidates listed), explicit inactive document exactly 412 with active_document, closed document 404, invalid selector (title, empty, null, number, list) 400 even with one open document"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_explicit_inactive_document_is_exactly_412_with_zero_side_effects"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_several_documents_without_a_selector_refuse_400_and_list_them"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_an_invalid_selector_is_400_and_never_decays_into_the_sole_document"
        status: pass
    human_judgment: false
  - id: R2
    description: "A selected active document is the one the handler works on (injected doc untouched, other open document untouched) and every reply names its token, title, path and the process; an omitted selector with one active document works the same"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_active_selection_runs_on_the_resolved_document_and_names_it"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_sole_active_document_is_used_without_a_selector_and_named"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_a_guarded_success_opens_its_transaction_on_the_resolved_document"
        status: pass
    human_judgment: false
  - id: R3
    description: "The set_parameter 409 rollback stays HTTP 409 with status rolled_back (never a success, no new_value, message says the value was NOT changed), and now names the attempted document and the process; a refused document never starts a transaction; the 409 source branch is pinned unchanged"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_a_rolled_back_parameter_write_stays_409_and_is_never_a_success"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_a_rolled_back_parameter_write_names_the_attempted_document_and_process"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_a_rolled_back_parameter_write_on_a_refused_document_never_starts_a_transaction"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_parameter_rollback_source_is_unchanged"
        status: pass
    human_judgment: false
  - id: R4
    description: "Existing transactions keep suppress_warnings immediately after Start, open on the resolved document, a transaction that cannot start commits nothing and still names the document, success bodies keep their original keys, and the mm to feet and level-elevation arithmetic is unchanged"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_suppress_warnings_comes_immediately_after_start"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_a_guarded_success_keeps_its_original_body_keys"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_create_grid_keeps_converting_millimetres_to_feet"
        status: pass
    human_judgment: false
  - id: R5
    description: "Reads stay reads and every registered route of the five modules is classified; every mutating handler declares exactly uiapp, doc and request and nothing reads HOST_APP or revit.doc"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_every_registered_route_is_classified"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_reads_keep_their_signature_and_are_not_guarded"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_mep_parameter_identity.py#test_the_route_modules_never_read_the_process_global_active_document"
        status: pass
    human_judgment: false
  - id: R6
    description: "Live behavior on a real Revit: pyRevit actually injecting uiapp with doc and request into these nine handlers, Document.Equals/IsValidObject on real documents, doc.ActiveView of the resolved document, no transaction on a refusal, replies naming the changed document, and a real rolled-back parameter write (G6)"
    requirement: "IDENT-02"
    verification:
      - kind: manual_procedural
        ref: "not run - needs a full Revit close and reopen (never pyRevit Reload), then 02-18; G6 is not authorized"
        status: unknown
    human_judgment: true
    rationale: "The fake pyRevit models the dispatch rule proven from pyRevit source in 02-07; it does not prove how a real Revit handles these handlers. No live route was touched."

duration: "about 11 min of execution (RED commit 2026-10-22T19:21Z, last code commit 19:22Z)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 14: Explicit document guard on MEP, parameter, room, structure and tag mutations Summary

**Nine mutating routes (`/create_duct/`, `/create_pipe/`, `/create_mep_system/`, `/set_parameter/`, `/create_room/`, `/create_room_separation/`, `/create_grid/`, `/create_framing/`, `/tag_elements/`) now call `mutation_document_or_response` as their first statement, refuse 503/400/404/exact 412 before any collector or transaction, run their unchanged bodies on the document the guard resolved, and stamp that document and the process identity on every reply; `set_parameter`'s 409 `rolled_back` is untouched, still an error, and now says which document and process the rolled-back write was attempted on.**

## Performance

- **Duration:** about 11 min
- **Tasks:** 2 of 2, both `tdd="true"`; one shared RED commit (the two tasks share one new test file, as in 02-13), two GREEN commits
- **Files:** 1 created (test file), 5 modified; `identity.py` was not touched (the existing helpers sufficed)

## Accomplishments

- **Guard shell, no wrapper (G1):** each original handler body is kept verbatim as a nested function that receives the guard's Document; the registered handler is the thin shell `(uiapp, doc, request)` that selects, guards, delegates and stamps. `startup.py` is untouched. Route modules import only `.identity` and `.utils`.
- **No side effect before the guard:** a refused request records zero document touches, collectors or transactions on every one of the nine routes (event-log assertion `world.events == []`).
- **The work lands on the guard's document:** the injected `doc` and the other open document record no touches; `doc.ActiveView` in `create_room_separation` and `tag_elements` is read from the resolved document.
- **set_parameter rollback honesty (T-02-02, prohibition):** a `commit_status == RolledBack` run returns HTTP 409, `status: rolled_back`, `transaction_status`, `failures`, `attempted_value` and the original "NOT changed" message, with no `new_value`; the reply additionally names the attempted document (token, title, path, active) and `process_identity`. A source pin asserts the commit_and_report call, the `committed` test, the `rolled_back` body and the single `status=409` are still in `parameters.py`.
- **Reads stay reads:** `project_parameters` and `element_properties` keep their signatures, call no guard and work on the injected document.

### Handler signatures touched

| Route | Handler | Before | After |
|-------|---------|--------|-------|
| `/create_duct/` | `create_duct_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_pipe/` | `create_pipe_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_mep_system/` | `create_mep_system_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/set_parameter/` | `set_parameter_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_room/` | `create_room_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_room_separation/` | `create_room_separation_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_grid/` | `create_grid_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_framing/` | `create_framing_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/tag_elements/` | `tag_elements_handler` | `(doc, request)` | `(uiapp, doc, request)` |

Unchanged (reads): `/project_parameters/` `(doc, shared_only, prefix, search, summary_only)`, `/element_properties/<element_id>` `(doc, element_id)`.

The nested bodies are `_create_duct`, `_create_pipe`, `_create_mep_system`, `_set_parameter`, `_create_room`, `_create_room_separation`, `_create_grid`, `_create_framing`, `_tag_elements`, each `(doc, request)`.

## Task Commits

1. **RED (both tasks):** `05dafa6` (test) - 182 failing, 18 passing (classification, two read pins, source pins, three bodies that already ran on the fake); failures were the missing `uiapp` argument, missing guard and missing attribution
2. **Task 1 GREEN:** `1951236` (feat) - mep.py and parameters.py guarded; test fixture fixes (optional read parameters, element `Category`)
3. **Task 2 GREEN:** `d47cadd` (feat) - rooms.py, structure.py, tags.py guarded

## Verification (real numbers)

- Plan verify `uv run pytest tests/unit/test_routes_mep_parameter_identity.py tests/unit/test_document_contracts.py tests/unit/test_conventions.py tests/unit/test_format_response.py -q`: **764 passed, 3 skipped**.
- `uv run pytest tests/unit -q`: **2657 passed, 3 skipped** (baseline 2457 passed, 3 skipped; +200, all in the new test file). No pre-existing failure.
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.373** (<2.0).
- Offline only. No `mcp__revit__*` tool was called, `/execute_code/` was not used, Revit and the live bridge were not touched (a Revit was open and left alone). No accidental live contact.

## Deviations from Plan

### Auto-fixed Issues

None - plan executed as written. `revit_mcp/identity.py` needed no change.

### Interface choices

**1. One RED commit for both tasks.** The two tasks share one new test file; the whole file was committed once (`05dafa6`), so the suite was red for the rooms/structure/tags rows between `1951236` and `d47cadd` (all in the new file, none pre-existing). Same choice as 02-13.

**2. Guard shell around an unchanged nested body** (the 02-12/02-13 design, reused). No body line changed; the five files differ from their parents only by the new import, the renamed inner definition and the added shell.

**3. Two test-double gaps fixed in the test file after RED** (not production defects): `call()` now skips injected arguments a handler does not declare (the `project_parameters` read has optional query parameters), and the fake element has `Category = None`.

**Total deviations:** 0 auto-fixes, 3 interface notes. **Impact:** none on scope.

## Issues Encountered / Surprises

- `git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on every commit (stale registered worktree, as in earlier plans). Commits succeed.
- Seven of the nine bodies already ran to a 200 on the fake before any production change (the RED run showed them passing the key-shape test), which confirms the fixtures drive the real original bodies rather than a stand-in.
- `create_mep_system` still opens its transaction before its own `element_ids` check (it rolls back and answers 400); unchanged, and pinned by a test that expects a rollback event and no commit.
- `tag_elements` and `create_room_separation` call `doc.ActiveView` when no `view_name` is sent. With the guard that is the active document's active view; with several open documents the caller must name the document, so this no longer depends on which model the injected `doc` happened to be.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or file access; replies gain the same `document` descriptor (title and local path) the earlier guarded routes already carry (T-02-07, local MCP clients only).

## Not run / not claimed

- **Live behavior is not run.** Whether pyRevit injects `uiapp` with `doc` and `request` into these handlers, how a real Document answers `Equals`/`IsValidObject`, what a real rolled-back parameter write looks like, and that no transaction opens on a refusal: unobserved. G2-production, G5-production collision (02-18) and G6 (the parameter-write campaign, not authorized) are not run. This plan only makes the identity visible so a later G6 can use it.
- **`revit_mcp/` changed (mep.py, parameters.py, rooms.py, structure.py, tags.py).** The extension directory is a junction to this repo, so Revit needs a full close and reopen (never pyRevit Reload, which can crash the process) before any live route check.
- **Tool-side rendering of the stamp is not part of this plan.** The reply body carries `document` and `process_identity`; the tool renderers (and `format_response`, which collapses `message`-bearing dicts) belong to the provenance plans.
- **Requirements:** `requirements-completed` stays empty. IDENT-02, IDENT-03, MDOC-02, MDOC-03 and MDOC-05 span every mutating route; 02-15 and 02-16 still guard the rest and nothing was observed live.
- **Malformed bodies** keep their old behavior (the handler's own error reply, now stamped), not a new 400.
- **Transaction-outcome work stays out of scope:** the other eight routes still call `t.Commit()` without checking its status (Phase 4); nothing was changed about commit reporting.

## Next Phase Readiness

- 02-15 and 02-16 can add rows to the tables in `tests/unit/test_routes_mep_parameter_identity.py` or copy its doubles (`FakeElement`, `FakeParam`, hooks keyed by `(label or None, name)`).
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted per the dispatch instruction (they hold other sessions' uncommitted work).

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist in `git log`: `05dafa6`, `1951236`, `d47cadd`; `git rev-list --count 064b1fc66a2db5fa7d0e37e3517217621338ace0..HEAD` was 3 and the per-plan ledger file holds that base; no tracked file deleted by any of them.
- Files exist: `tests/unit/test_routes_mep_parameter_identity.py`, `revit_mcp/mep.py`, `revit_mcp/parameters.py`, `revit_mcp/rooms.py`, `revit_mcp/structure.py`, `revit_mcp/tags.py`.
- `uv run pytest tests/unit -q`: 2657 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.373`.
