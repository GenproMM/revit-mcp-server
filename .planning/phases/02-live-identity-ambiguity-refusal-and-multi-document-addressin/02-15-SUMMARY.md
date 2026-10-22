---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '15'
subsystem: api
status: complete
tags: [mutation-guard, g1-explicit-route-only, response-attribution, http-412, open-model, d-15-exception, execute-code, ironpython3, transforms, view-management]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-04 mutation decision contract (mutation_document_or_response in revit_mcp/identity.py); 02-07 rule that a handler runs in the Revit API context only if it declares uiapp, uidoc or doc; 02-12/02-13/02-14 guard-shell shape with request_document_selector / attribute_response / current_descriptor; 02-20 accepted G1 explicit-route-only and D-15 (2026-10-16)
provides:
  - "transform_elements, create_view and set_active_view call the guard explicitly first; refusals are 503 / 400 / 404 / exact 412 with zero side effects; replies carry the document descriptor and process identity on success and on every error"
  - "set_active_view is a document-bound mutation, not document activation: it switches the view only of the resolved active document and refuses (412, no change) when the injected uidoc is not that Document"
  - "open_model is process-level (no selector, no guard, never refused for a document count); its success reply names the Document Revit actually opened, read from that Document after the API call, and every reply names the process; workset-aware opening untouched"
  - "/execute_code/ stays enabled and unguarded (D-15); every reply, success or error, carries a constant document_scope notice and the process identity and never a changed-document attribution"
  - "execute_revit_code(code, description, target=None, ctx=None): target is forwarded through the injected revit_post (listener preflight and per-target lock), no document parameter, docstring states the trusted exception"
  - "tests/unit/test_routes_view_code_identity.py: 106 tests, real register_*_routes registration with a fake api and fake pyRevit"
affects: [02-16, 02-18]

actuals:
  tokens: 19109   # chars/4 over `git diff f82f409..HEAD` (76438 chars) at the last code commit, test file included; excludes this SUMMARY
  tasks: 2
  commits: 3      # MEASURED: git rev-list --count f82f40939463c2e9c932f019948115d5779e72b4..HEAD before this SUMMARY commit (#3968)
plan_head_before: f82f40939463c2e9c932f019948115d5779e72b4

tech-stack:
  added: []
  patterns:
    - "Guard shell + unchanged nested body (02-12 shape) for the three ordinary mutations"
    - "Process-level shell: unchanged nested body, then a process-only stamp (open_model also adds the actually-opened document; execute_code adds the constant document_scope)"
    - "Row tables in the test file (MUTATIONS, TRANSACTING, EXPECTED_KEYS, READS, PROCESS_LEVEL, REGISTRARS): a new route in any of the four modules fails until it is classified"

key-files:
  created:
    - tests/unit/test_routes_view_code_identity.py
  modified:
    - revit_mcp/transforms.py
    - revit_mcp/view_management.py
    - revit_mcp/worksharing.py
    - revit_mcp/code_execution.py
    - tools/code_execution_tools.py

key-decisions:
  - "Classification by what a route does: transform_elements, create_view, set_active_view change a document (set_active_view changes the view a document shows) and are guarded. model_worksets is a POST that only previews a file on disk: a read, unguarded, signature (doc, request) pinned. open_model and /execute_code/ are process-level and carry no document selector."
  - "set_active_view keeps its injected uidoc (signature uiapp, doc, uidoc, request) but only uses it when uidoc.Document Equals the guard's Document; otherwise 412 document-not-active and nothing changes. No document is ever activated to satisfy a selection."
  - "open_model reads the opened Document's title and path from that Document; the selector and active flag come from the live registry entry that Equals it. If the registry is in doubt or no single entry matches, the reply says document: null (honest unknown) with the real title and path, never the previously active document and never the requested path."
  - "D-15 honoured: no selector, guard, 412, gate or confinement was added to execute_code or execute_revit_code; the existing transaction, suppress_warnings and 409 rolled_back behaviour is the unchanged nested body. execute_code only gained uiapp (so the process identity is read through it, not HOST_APP) and a stamp."
  - "The process-only stamp is a small local helper in worksharing.py and code_execution.py rather than a new identity.py function: identity.py was not edited."

patterns-established:
  - "Process-level handler: signature (uiapp, doc, request); unchanged body; reply stamped with process_identity, or identity_error naming why it is unavailable"

requirements-completed: []  # Deliberately empty (02-02..02-14 precedent). IDENT-02 / IDENT-03 / MDOC-02 / MDOC-03 / MDOC-05 span every mutating route and the arbitrary-code exception is an accepted limitation (D-15), not a passed guarantee; no route behaviour has been observed on a real Revit.

coverage:
  - id: R1
    description: "transform_elements, create_view and set_active_view refuse before any collector, element lookup, transaction or view switch: no open document 503, several documents without a selector 400 (candidates listed), explicit inactive document exactly 412 with active_document, closed document 404, invalid selector (title, empty, null, number, list) 400 even with one open document"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_explicit_inactive_document_is_exactly_412_with_zero_side_effects"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_several_documents_without_a_selector_refuse_400_and_list_them"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_an_invalid_selector_is_400_and_never_decays_into_the_sole_document"
        status: pass
    human_judgment: false
  - id: R2
    description: "A selected active document is the one the three handlers work on (injected doc and the other open document untouched) and every reply names token, title, path and the process; set_active_view never activates a document and refuses when the injected uidoc is not the resolved Document"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_active_selection_runs_on_the_resolved_document_and_names_it"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_set_active_view_never_activates_a_document_to_satisfy_a_selection"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_set_active_view_refuses_when_the_injected_uidoc_is_not_the_resolved_document"
        status: pass
    human_judgment: false
  - id: R3
    description: "Transactions open on the resolved document with suppress_warnings immediately after Start; a transaction that cannot start commits nothing and still names the document; success bodies keep their original keys; failure replies are attributed too"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_suppress_warnings_comes_immediately_after_start"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_a_guarded_success_keeps_its_original_body_keys"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_a_failure_after_the_guard_still_names_the_document_it_ran_on"
        status: pass
    human_judgment: false
  - id: R4
    description: "open_model reports the document Revit actually opened (not the previous active one, not the requested path), with the process, on a process-level route that no document count refuses; errors name the process and no document; an unselectable opened document is reported as an honest unknown; the workset configuration and detach option are still applied before the open call"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_open_model_reports_the_newly_opened_document_not_the_previous_active_one"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_open_model_names_what_revit_opened_never_the_requested_path"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_open_model_keeps_the_workset_aware_opening_untouched"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_open_model_is_honest_when_the_opened_document_cannot_be_given_a_selector"
        status: pass
    human_judgment: false
  - id: R5
    description: "/execute_code/ stays registered and runs with two documents open (no refusal, no 412, no guard call); success, error, 409 rolled_back and early 400/503/500 replies all carry the constant document_scope notice and process identity and none carries a changed-document attribution key"
    requirement: "T-02-14 (D-15 label)"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_execute_code_runs_when_two_documents_are_open_and_no_selector_is_given"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_execute_code_early_error_replies_carry_the_notice_too"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_execute_code_rollback_stays_a_409_error_and_carries_the_notice"
        status: pass
    human_judgment: false
  - id: R6
    description: "execute_revit_code is registered with its manifest entry unchanged, takes target before ctx and no document parameter, forwards target (and only then) through the injected transport with a POST body that has no document key, and its docstring states the trusted exception; through the real bridge an unprovable incarnation is refused before any HTTP"
    requirement: "T-02-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_execute_revit_code_forwards_target_and_sends_no_document_field"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_execute_revit_code_docstring_states_the_trusted_exception"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_execute_revit_code_goes_through_the_real_bridge_preflight_and_lock"
        status: pass
    human_judgment: false
  - id: R7
    description: "Every registered route of the four modules is classified (mutation / read / process-level); guarded handlers declare exactly the injected arguments; no route module reads the process-global host object"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_every_registered_route_is_classified"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_mutation_handler_declares_the_api_context_arguments"
        status: pass
      - kind: unit
        ref: "tests/unit/test_routes_view_code_identity.py#test_the_route_modules_never_read_the_process_global_active_document"
        status: pass
    human_judgment: false
---

# Phase 2 Plan 15: Transform/view guard, process-scoped open_model and the D-15 execute exception Summary

**The last ordinary mutation family (transform_elements, create_view, set_active_view) now runs behind the explicit per-handler guard; open_model reports the document Revit actually opened plus the process; and the two arbitrary-code surfaces stay enabled, unguarded and honestly labelled as the user's trusted exception.**

## What was built

**Task 1 (guard transform and view routes).** `transforms.py` and `view_management.py` use the 02-12 shell: the original body becomes a nested function on the guard's Document, and the registered handler `(uiapp, doc, request)` calls `mutation_document_or_response(request_document_selector(request), uiapp=uiapp)` first, then `attribute_response`. `create_view` and the `doc.ActiveView` fallback of the elevation branch now read the resolved document's view, never the injected one. `set_active_view` is `(uiapp, doc, uidoc, request)`: after the guard, the injected `uidoc` is used only if `uidoc.Document.Equals(resolved)`; otherwise it answers 412 `document-not-active`, attributed, and nothing changes. Open-but-inactive selections are refused by the guard itself (exact 412) and no document is activated to satisfy them.

**Task 2 (open_model and the D-15 exception).**
- `worksharing.py`: `open_model(uiapp, doc, request)` wraps the unchanged opening body (now `_open_model(uiapp, request)`; `HOST_APP` is gone, it opens through `uiapp.Application` / `uiapp.OpenAndActivateDocument`). The success reply gains `document`: title and path read from the opened Document, selector and active flag from the live-registry entry that Equals it (or `document: null` when that cannot be established). Every reply, errors included, gets `process_identity` (or `identity_error`). `WorksetConfiguration`/`SetOpenWorksetsConfiguration` and the detach option are untouched. `model_worksets` is unchanged.
- `code_execution.py`: `execute_code(uiapp, doc, request)` wraps the unchanged body (`_execute_code`) and stamps every reply with `DOCUMENT_SCOPE_NOTICE` (trusted arbitrary-code exception, no document guard or confinement, `doc` is only the starting context, changed documents are not identified or attributed) and the process identity. No selector, guard, 412 path or changed-document key was added.
- `tools/code_execution_tools.py`: `execute_revit_code(code, description="Code execution", target=None, ctx=None)`, `target` forwarded as a keyword only when given, no document field in the POST body, docstring rewritten for a model (the stale "IronPython 2.7.12" is now "IronPython 3 (Python 3.4 language level)"). File keeps its CRLF line endings.

## Commits

1. **RED:** `7ca3fbd` (test) - `tests/unit/test_routes_view_code_identity.py` created (92 failed, 14 passed at that point; failures were the missing guard, signatures, document/document_scope keys, target parameter and docstring)
2. **Task 1 GREEN:** `820c1d5` (feat) - transforms.py, view_management.py (+ one test-double fix: `XYZ.Zero`)
3. **Task 2 GREEN:** `beb2cfd` (feat) - worksharing.py, code_execution.py, tools/code_execution_tools.py

## Verification (real numbers)

- `uv run pytest tests/unit -q`: **2763 passed, 3 skipped** (baseline 2657 passed, 3 skipped; +106, all in the new test file). No pre-existing failure.
- Task 1 verify (`test_document_contracts.py test_conventions.py test_section_basis.py test_registration.py test_tool_forwarding_views.py` plus the new file's guard rows) and Task 2 verify set: pass.
- `uv run python scripts/conventions.py`: clean (exit 0, no output). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.383** (<2.0).
- Offline only. No `mcp__revit__*` tool was called, `/execute_code/` and `execute_revit_code` were never invoked against Revit, the live bridge and every document were left alone (a Revit was open). No accidental live contact.

## Handler signatures touched

| Route | Before | After |
|-------|--------|-------|
| `/transform_elements/` | `(doc, request)` | `(uiapp, doc, request)` guarded |
| `/create_view/` | `(doc, request)` | `(uiapp, doc, request)` guarded |
| `/set_active_view/` | `(doc, uidoc, request)` | `(uiapp, doc, uidoc, request)` guarded |
| `/open_model/` | `(doc, request)` | `(uiapp, doc, request)` process-level |
| `/execute_code/` | `(doc, request)` | `(uiapp, doc, request)` process-level, D-15 |
| `/model_worksets/` | `(doc, request)` | unchanged (read, pinned) |

## Deviations from Plan

### Auto-fixed Issues

None. `revit_mcp/identity.py` and `tests/unit/tool_manifest.txt` needed no change (tool name unchanged).

### Interface choices

1. **One RED commit for both tasks** (one shared new test file), so the suite was red for the task-2 rows between `7ca3fbd` and `beb2cfd` (all in the new file, none pre-existing). Same choice as 02-13/02-14.
2. **Local process-only stamp helpers** in `worksharing.py` and `code_execution.py` (about ten lines each) instead of a new `identity.py` function, to stay inside the plan's `files_modified`.
3. **`execute_code` gained `uiapp`** in its signature. It already declared `doc`, so it already ran in the API context; `uiapp` is only there so the process identity is read through the injected object instead of HOST_APP. The existing `revit.doc` fallback for a null injected doc is kept as is (execution semantics unchanged, and `test_conventions.py` pins it).
4. **A test-double gap fixed after RED** (`XYZ.Zero` in the fake DB), not a production defect.

## Issues Encountered / Surprises

- `git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on every commit (stale registered worktree, as in earlier plans). Commits succeed.
- `transform_elements` and `create_view` still call `t.Commit()` without checking its status (pre-existing, Phase 4 transaction-outcome work); unchanged.
- The docstring of the old tool described `doc` as "The active Revit document"; that is exactly the claim D-15 forbids, so it is replaced, not softened.

## Known Stubs

None.

## Threat Flags

None. No new endpoint or auth path. Replies gain the same `document` descriptor (title and local path) earlier guarded routes carry; `open_model` now echoes the opened document's title and path (local MCP clients only, T-02-07). T-02-11 stays accepted (D-15); T-02-14 is mitigated by the docstring, the constant notice on every reply and the tests that assert the notice and the absence of attribution keys and selector.

## Not run / not claimed

- **Live behaviour is not run.** Whether pyRevit injects `uiapp` with `doc`/`uidoc`/`request` into these handlers, how a real Document answers `Equals`/`IsValidObject`, what Revit opens for a real `open_model` (including the workset behaviour with no dialog) and how a real UIDocument responds to `ActiveView =`: unobserved. G2-production and G5-production (02-18) are not run; G6 is not authorized.
- **`revit_mcp/` changed (transforms.py, view_management.py, worksharing.py, code_execution.py).** The extension directory is a junction to this repo, so Revit needs a **full close and reopen** (never pyRevit Reload, which can crash the process) before any live route check.
- **D-15 is an accepted limitation, not a passed guarantee.** Arbitrary code is not document-confined and its changed documents are not attributed; this plan labels that honestly and does not mark IDENT-02/03 or MDOC-02/03/05 complete for arbitrary code.
- **Tool-side rendering** of `document`/`document_scope`/`process_identity` by `format_response` and the tool renderers is not part of this plan.
- **Requirements:** `requirements-completed` stays empty (see frontmatter).
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted per the dispatch instruction (they hold other sessions' uncommitted work).

## Next Phase Readiness

- 02-16 can reuse the doubles in `tests/unit/test_routes_view_code_identity.py` (`FakeUIDocument`, `World.open_plan`/`open_calls` for process-level opens) or the earlier files' tables.
- This was the last route-side plan; the remaining plans are the provenance/tool-rendering and live-recheck work.

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist in `git log`: `7ca3fbd`, `820c1d5`, `beb2cfd`; `git rev-list --count f82f40939463c2e9c932f019948115d5779e72b4..HEAD` was 3 and the per-plan ledger file holds that base; no tracked file was deleted by any of them.
- Files exist: `tests/unit/test_routes_view_code_identity.py`, `revit_mcp/transforms.py`, `revit_mcp/view_management.py`, `revit_mcp/worksharing.py`, `revit_mcp/code_execution.py`, `tools/code_execution_tools.py`.
- `uv run pytest tests/unit -q`: 2763 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.383`.
