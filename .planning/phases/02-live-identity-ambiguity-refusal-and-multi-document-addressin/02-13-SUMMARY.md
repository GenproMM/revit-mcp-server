---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '13'
subsystem: api
tags: [mutation-guard, g1-explicit-route-only, response-attribution, http-412, ironpython3, save, export, family, nested-documents]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-04 mutation decision contract (mutation_document_or_response in revit_mcp/identity.py); 02-07 rule that a handler runs in the Revit API context only if it declares uiapp, uidoc or doc; 02-12 guard-shell shape and request_document_selector / attribute_response helpers; 02-20 accepted G1 explicit-route-only
provides:
  - "Eleven mutating route handlers (document 1, documentation 3, editing 2, interop 2, placement 3) call the guard explicitly first, before any directory is created, file written, Save/SaveAs, export, LoadFamily, EditFamily or transaction; refusals are 503 / 400 / 404 / exact 412 with zero side effects"
  - "Every reply a guarded handler produces carries the document descriptor and the process identity; save_document re-reads title and path from the resolved Document after the operation and never reports the requested path when the document ended up elsewhere"
  - "edit_family reports documents_changed: the guard-resolved project (changed only through the reload) and the nested family document it opened (title/path read when opened, never saved), on success and on every error reply"
  - "revit_mcp/identity.py: current_descriptor(descriptor, document), family_document_info(document)"
  - "tests/unit/test_routes_document_interop_identity.py: 224 tests, real register_*_routes registration with a fake api and fake pyRevit"
affects: [02-14, 02-15, 02-16, 02-18]

actuals:
  tokens: 18165   # chars/4 over `git diff 2e27561..HEAD` (72660 chars) at the last code commit; excludes this SUMMARY
  tasks: 2
  commits: 3      # MEASURED: git rev-list --count 2e275619f1568fd4b7b1e35897a65509d248ba27..HEAD before this SUMMARY commit (#3968)
plan_head_before: 2e275619f1568fd4b7b1e35897a65509d248ba27

tech-stack:
  added: []
  patterns:
    - "Guard shell + unchanged nested body (02-12 shape): selector, guard, run the original body on the guard's Document, stamp the reply"
    - "Nested-document ledger: a body that opens a second document records it in a dict the shell owns, so the reply is built from facts captured at the point of the operation rather than from the injected doc"
    - "Fake pyRevit with an event log, per-(label, method) hooks (SaveAs, EditFamily) and a nested FamilyDoc; every touch, collector, transaction, save and close is observable"

key-files:
  created:
    - tests/unit/test_routes_document_interop_identity.py
  modified:
    - revit_mcp/document.py
    - revit_mcp/documentation.py
    - revit_mcp/editing.py
    - revit_mcp/interop.py
    - revit_mcp/placement.py
    - revit_mcp/identity.py   # outside files_modified, see Deviations

key-decisions:
  - "Classification by what a route does: delete_elements, modify_element, create_sheet, create_schedule, export_document, export_ifc, link_file, place_family, load_family, edit_family, save_document change a document or write output from one and are guarded. selected_elements, list_families, list_family_categories and list_levels only read, keep their signatures and stay active-document-only; a test pins every registered route of the five modules."
  - "export_document and export_ifc are guarded and attributed to the originating Document even though the output goes to disk: they open a transaction on it (kept as is) and name the view or file."
  - "A save reply names the document as it stands after the operation: current_descriptor re-reads Title and PathName from the resolved Document. SaveAs additionally returns previous_path. If the document's real path differs from the requested one, file_path is the real path and the request moves to requested_file_path (prohibition: never report a save against a path the document did not reach)."
  - "edit_family: the family document's edit is closed without saving, so it is never reported saved; its changed flag is the transaction commit status (a rolled-back commit is not reported as a change); the project is changed only when the reload ran. Unchanged behavior of the route (it still ignores the return of LoadFamily)."
  - "No document-bound token for the nested family document: it is not an open project and is never in the registry; it is described by role, title and path."

patterns-established:
  - "Mutation handler: signature (uiapp, doc, request); first statement the guard call; refusal returned as is; success and failure both stamped"
  - "Row tables in the test file (MUTATIONS, TRANSACTING, EARLY_ERROR, READS, REGISTRARS): a new route in any of the five modules fails until it is classified"

requirements-completed: []  # Deliberately empty (02-02..02-12 precedent). IDENT-02 / IDENT-03 / MDOC-02 / MDOC-03 / MDOC-05 cover every mutating route of the phase; 02-14..02-16 still guard the rest, and no route behavior has been observed on a real Revit.

coverage:
  - id: R1
    description: "Each of the eleven changing handlers refuses before any transaction, collector, directory creation, Save/SaveAs, export, LoadFamily or EditFamily: no open document 503, several documents without a selector 400 (candidates listed), explicit inactive document exactly 412 with active_document, closed document 404, invalid selector (title, empty, null, number, list) 400 even with one open document"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_explicit_inactive_document_is_exactly_412_with_zero_side_effects"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_a_refused_save_as_creates_no_directory_and_saves_nothing"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_an_invalid_selector_is_400_and_never_decays_into_the_sole_document"
        status: pass
    human_judgment: false
  - id: R2
    description: "A selected active document is the one the handler works on (injected doc untouched, other open document untouched) and every reply names its token, title, path and the process; an omitted selector with one active document works the same"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_active_selection_runs_on_the_resolved_document_and_names_it"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_sole_active_document_is_used_without_a_selector_and_named"
        status: pass
    human_judgment: false
  - id: R3
    description: "Save and SaveAs stay outside any transaction and act only on the resolved Document; the reply names the document actually saved with title and path re-read after the operation, and never claims the requested path when the document ended elsewhere; a failed SaveAs still names the document"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_save_as_runs_outside_any_transaction_and_names_where_the_document_now_lives"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_save_as_that_lands_elsewhere_never_claims_the_requested_path"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_save_in_place_saves_the_resolved_document_outside_any_transaction"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_save_document_source_opens_no_transaction"
        status: pass
    human_judgment: false
  - id: R4
    description: "Existing transactions keep suppress_warnings immediately after Start, open on the resolved document, and the load-bearing 409 rolled_back of modify_element still reaches the client as an error carrying the document identity"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_suppress_warnings_comes_immediately_after_start"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_rolled_back_409_stays_an_error_and_names_the_document"
        status: pass
    human_judgment: false
  - id: R5
    description: "edit_family names every document it actually worked on: the guard-resolved project and the nested family document, with changed flags that follow what really happened (reload ran, commit status, transaction that failed to start, unknown type rolled back, reload failure), on success and on error replies; a refusal opens no family and reports no change"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_edit_family_reports_the_project_and_the_family_document_it_changed"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_edit_family_reload_failure_is_a_500_that_says_the_project_did_not_change"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_edit_family_refusal_opens_no_family_and_reports_no_change"
        status: pass
    human_judgment: false
  - id: R6
    description: "Reads stay reads and every registered route of the five modules is classified; every mutating handler declares uiapp, doc and request and nothing reads HOST_APP"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_every_registered_route_is_classified"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_reads_keep_their_signature_and_are_not_guarded"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_document_interop_identity.py#test_mutation_handler_declares_the_api_context_arguments"
        status: pass
    human_judgment: false
  - id: R7
    description: "Live behavior on a real Revit: pyRevit actually injecting uiapp with doc and request into these eleven handlers, Document.Equals/IsValidObject on real documents, a real SaveAs updating PathName, EditFamily's family document and its Title/PathName, no transaction on a refusal, replies naming the changed document"
    requirement: "IDENT-02"
    verification:
      - kind: manual_procedural
        ref: "not run - needs a full Revit close and reopen (never pyRevit Reload), then 02-18"
        status: unknown
    human_judgment: true
    rationale: "The fake pyRevit models the dispatch rule proven from pyRevit source in 02-07; it does not prove how a real Revit handles these handlers, what a real family document reports as Title/PathName, or whether Application.Documents lists a family document while EditFamily has it open. No live route was touched."

duration: "about 9 min of execution (ledger 2026-10-22T19:07:45Z, last code commit about 19:15Z)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 13: Explicit document guard on save, documentation, editing, interop and family mutations Summary

**Eleven mutating routes (`/save_document/`, `/create_sheet/`, `/create_schedule/`, `/export_document/`, `/delete_elements/`, `/modify_element/`, `/export_ifc/`, `/link_file/`, `/place_family/`, `/load_family/`, `/edit_family/`) now call `mutation_document_or_response` as their first statement, refuse 503/400/404/exact 412 before any file output, Save/SaveAs, EditFamily or transaction, run their unchanged bodies on the document the guard resolved, and stamp that document and the process identity on every reply; a save names the document as re-read after the operation, and `edit_family` reports the project and the nested family document separately.**

## Performance

- **Duration:** about 9 min
- **Tasks:** 2 of 2, both `tdd="true"`; one shared RED commit (see Deviations), two GREEN commits
- **Files:** 1 created (test file), 6 modified (`identity.py` outside `files_modified`)

## Accomplishments

- **Where the guard lives:** unchanged from 02-12; the route modules import only `.identity`, `.utils` (the cross-domain import invariant holds).
- **Handler shape (G1, explicit, no wrapper):** the original handler body is kept verbatim as a nested function that receives the guard's Document; the registered handler is the thin shell (`uiapp, doc, request`). `startup.py` is untouched.
- **Save and SaveAs:** still outside any transaction (pinned both by behavior, no `transaction`/`start` event, and by a source check that `document.py` contains no `DB.Transaction`). Both act on the guard's Document only; the injected `doc` and any other open document record zero touches.
- **Reply attribution for saves:** `current_descriptor` re-reads Title and PathName from the resolved Document after the operation (token and active flag stay the guard's). SaveAs also returns `previous_path`; if the document's real path differs from the request, `file_path` is the real path and the request is kept as `requested_file_path`.
- **No output before the guard:** a refused SaveAs creates no parent directory, a refused IFC export creates no output directory, a refused document export creates no `RevitMCPExport` directory.
- **Nested documents:** `edit_family` records the family document's title and path right after `EditFamily` returns, before it is closed, and reports `documents_changed`: `[project (changed only if the reload ran), family (changed = its edit transaction committed, saved always false)]`. Early errors (family not loaded) list only the unchanged project; a refusal carries no `documents_changed`.
- **Reads stay reads:** `selected_elements`, `list_families`, `list_family_categories`, `list_levels` keep their signatures, call no guard and work on the injected document; the test file pins every registered route of the five modules.

### Handler signatures touched

| Route | Handler | Before | After |
|-------|---------|--------|-------|
| `/save_document/` | `save_document` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_sheet/` | `create_sheet_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/create_schedule/` | `create_schedule_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/export_document/` | `export_document_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/delete_elements/` | `delete_elements_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/modify_element/` | `modify_element_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/export_ifc/` | `export_ifc_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/link_file/` | `link_file_handler` | `(doc, request)` | `(uiapp, doc, request)` |
| `/place_family/` | `place_family` | `(doc, request)` | `(uiapp, doc, request)` |
| `/load_family/` | `load_family` | `(doc, request)` | `(uiapp, doc, request)` |
| `/edit_family/` | `edit_family` | `(doc, request)` | `(uiapp, doc, request)` |

Unchanged (reads): `/selected_elements/` `(doc, uidoc)`, `/list_families/` `(doc, request)`, `/list_family_categories/` `(doc)`, `/list_levels/` `(doc)`.

## Task Commits

1. **RED (both tasks):** `6b83e06` (test) - 210 failing, 14 passing (classification, reads, source pin); failures were the missing `uiapp` argument, missing guard and missing helpers
2. **Task 1 GREEN:** `31d803a` (feat) - save, sheet, schedule, export_document, delete, modify guarded; `identity.py` helpers
3. **Task 2 GREEN:** `95ff93c` (feat) - export_ifc, link_file, place_family, load_family, edit_family guarded; `documents_changed`

## Verification (real numbers)

- Plan verify `uv run pytest tests/unit/test_routes_document_interop_identity.py tests/unit/test_document_contracts.py tests/unit/test_conventions.py -q`: **763 passed, 3 skipped**.
- `uv run pytest tests/unit -q`: **2457 passed, 3 skipped** (baseline 2233 passed, 3 skipped; +224, all in the new test file). No pre-existing failure.
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.367** (<2.0).
- Offline only. No `mcp__revit__*` tool was called, `/execute_code/` was not used, Revit and the live bridge were not touched (a Revit was open and left alone). No accidental live contact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Two pure helpers added to revit_mcp/identity.py (outside `files_modified`)**
- **Found during:** Task 1 design
- **Issue:** The plan requires the save reply to name the document actually saved and `edit_family` to identify a nested family document at the point of the operation. The shared descriptor reader lived only inside the registry's private `_descriptor`, and a route module may not import another domain.
- **Fix:** `current_descriptor(descriptor, document)` (re-reads title/path from a Document, falls back to the guard's values, never raises, never mutates) and `family_document_info(document)` (title, path, `is_family_document`), both sharing one small reader. Existing 02-04/02-12 contract tests unchanged.
- **Files modified:** `revit_mcp/identity.py`
- **Commit:** `31d803a`

**2. [Interface choice] One RED commit for both tasks**
- The two tasks share one new test file; instead of two partial RED commits, the whole file was committed once (`6b83e06`) and the suite was therefore red for the interop/placement rows between `31d803a` and `95ff93c` (57 failing, all in the new file, none pre-existing). Both GREEN commits passed their own task rows.

**3. [Interface choice] Guard shell around an unchanged nested body** (the 02-12 design, reused). The `edit_family` body gained three small recording lines (`touched[...]`), nothing else changed in its logic. The one behavior-neutral addition: its edit commit's status is now compared (`ft.Commit() == DB.TransactionStatus.Committed`) to set a flag instead of being discarded; the flow after it is identical.

**4. [Interface choice] `open_model` is not in these modules** and is not a document-bound mutation (plan text); it is untouched.

**Total deviations:** 1 Rule 3 (one file outside `files_modified`), 3 interface notes. **Impact:** none on scope.

## Issues Encountered / Surprises

- `git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on every commit (stale registered worktree, as in 02-04/02-05/02-12). Commits succeed.
- First GREEN run of the new test file failed only because the fake `System` module lacked `Int64` (`make_element_id` builds `DB.ElementId(System.Int64(n))`); a test-double gap, not a code defect. Fixed in the test file before the Task 1 commit.
- Both GREEN runs otherwise passed at the first execution with no auto-fix attempt on production code.
- Possible live concern, not tested: EditFamily's family document may appear in `Application.Documents` while open. The handler closes it on every path before returning and requests are serialized through the API thread, so a concurrent guard should not see it, but a family document left open by a crash would make the registry count an extra eligible document. Worth a live look in 02-18.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: local-path-disclosure | revit_mcp/document.py, revit_mcp/placement.py | Save, SaveAs and edit_family replies now carry the changed documents' title and full local path (previous_path, requested_file_path, documents_changed), as the listing routes already do (T-02-07, local MCP clients only; external authentication is Phase 5 and is not claimed). |

## Not run / not claimed

- **Live behavior is not run.** Whether pyRevit injects `uiapp` with `doc` and `request` into these handlers, how a real Document answers `Equals`/`IsValidObject`, whether a real SaveAs updates `PathName` as the fake does, what a real family document reports, and that no transaction opens on a refusal: unobserved. G2-production, G5-production collision (02-18) and G6 (not authorized) are not run.
- **`revit_mcp/` changed (identity.py, document.py, documentation.py, editing.py, interop.py, placement.py).** The extension directory is a junction to this repo, so Revit needs a full close and reopen (never pyRevit Reload, which can crash the process) before any live route check.
- **Tool-side rendering of the stamp is not part of this plan.** The reply body carries `document`, `process_identity` and, for `edit_family`, `documents_changed`; the tool renderers (and `format_response`, which collapses `message`-bearing dicts) belong to the provenance plans.
- **Requirements:** `requirements-completed` stays empty. IDENT-02, IDENT-03, MDOC-02, MDOC-03 and MDOC-05 span every mutating route; the rest are not yet guarded and nothing was observed live.
- **Malformed bodies** keep their old behavior (the handler's own error reply, now stamped), not a new 400.
- **Stale docs outside this plan:** CLAUDE.md "Current surface" counts and the `startup.py` / `documents.py` module notes.

## Next Phase Readiness

- 02-14..02-16 can add rows to `MUTATIONS` / `TRANSACTING` / `EARLY_ERROR` / `READS` / `REGISTRARS` in `tests/unit/test_routes_document_interop_identity.py` or copy its doubles; the `FamilyDoc`, hook and `break_start` doubles cover nested documents and Save-like methods.
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted per the dispatch instruction (they hold other sessions' uncommitted work).

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist in `git log`: `6b83e06`, `31d803a`, `95ff93c`; `git rev-list --count 2e275619f1568fd4b7b1e35897a65509d248ba27..HEAD` was 3 and the per-plan ledger file holds that base; no tracked file deleted by any of them.
- Files exist: `tests/unit/test_routes_document_interop_identity.py`, `revit_mcp/document.py`, `revit_mcp/documentation.py`, `revit_mcp/editing.py`, `revit_mcp/interop.py`, `revit_mcp/placement.py`, `revit_mcp/identity.py`.
- `uv run pytest tests/unit -q`: 2457 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.367`.
