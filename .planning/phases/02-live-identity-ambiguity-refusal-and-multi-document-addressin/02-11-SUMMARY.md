---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '11'
subsystem: api
tags: [mcp-tools, per-call-target, mutation-document, tool-contract, structure, tag, transform, views, worksharing, open-model, tdd]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-03 target-keyed bridge (revit_get/revit_post/revit_image accept target=); 02-04..02-07 document selector tokens and the 412/400 mutation decision; 02-08..02-10 tool conventions (target, document, ctx order; _target_options/_blank_document helpers)
provides:
  - "Optional per-call `target` on every Revit-facing tool of tools/structure_tools.py, tag_tools.py, transform_tools.py, view_management_tools.py, view_tools.py, worksharing_tools.py (12 tools)"
  - "Optional `document` on the 6 actual mutations (create_grid, create_structural_framing, tag_elements, transform_elements, create_view, set_active_view), forwarded in the POST body only when given and refused before any send when blank or non-string"
  - "The four view reads (get_revit_view, list_revit_views, get_current_view_info, get_current_view_elements) take `target` only and say they read the active document of the selected process, never activate a document or switch views, and that only read_document_summary/read_document_levels read an inactive one; get_revit_view's revit_image fetch carries the target"
  - "list_model_worksets (file read from disk) and open_model (file open) classed as process-level: `target` only, no `document` argument; open_model's docstring separates opening a file from activate_document and says to read the opened document from the reply (document_title, activated), never assume it"
  - "tests/unit/test_tool_forwarding_views.py: 137 tests over a hand-classified inventory of all 12 callables of the six owned registrars"
affects: [02-12, 02-16, 02-17, 02-18]

actuals:
  tokens: 13830   # chars/4 over `git diff e80e538..HEAD` (55319 chars, 7 files incl. tests) at the last task commit; excludes this SUMMARY
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count e80e538c085afe1cd8b3ab5ab260f22275796964..HEAD before this SUMMARY commit (#3968)
plan_head_before: e80e538c085afe1cd8b3ab5ab260f22275796964

tech-stack:
  added: []
  patterns:
    - "Same per-module `_target_options` / `_blank_document` / `_BLANK_DOCUMENT_REFUSAL` helpers as 02-08..02-10 (repeated per module; tools/utils.py is outside files_modified); read-only modules (view_tools, worksharing_tools) carry only `_target_options`"
    - "Four tool kinds classified by hand, never by HTTP method: mutation (target + document), read (target only), file_read and file_open (target only, process-level)"
    - "An AST check requires every revit_get/revit_post/revit_image call in the six modules to splat transport options; a source check requires exactly one `data[\"document\"] = document` per mutation and exactly one `/open_model/` string (in worksharing_tools.py)"

key-files:
  created:
    - tests/unit/test_tool_forwarding_views.py
  modified:
    - tools/structure_tools.py
    - tools/tag_tools.py
    - tools/transform_tools.py
    - tools/view_management_tools.py
    - tools/view_tools.py
    - tools/worksharing_tools.py

key-decisions:
  - "Parameter order for the optional-document mutations is `..., target, document, ctx`, identical to 02-08..02-10; reads and process-level tools are `..., target, ctx`."
  - "set_active_view is a document-bound mutation: it changes the view one document shows. Its docstring says it never activates a document, refuses an inactive document with 412 and points to activate_document. create_view likewise."
  - "The four view tools are reads: `target` only and no `document` parameter. An explicitly selected inactive document cannot be expressed on a read, so the plan's 'unsupported inactive view reads refuse before dispatch' is met by construction (TypeError, nothing dispatched), the same call as 02-09/02-10. No view read triggers an activation or a view switch."
  - "list_model_worksets is classed as a process-level file inspection, not a document read and not a mutation: it reads the .rvt from disk through the selected process (its existing behavior), takes no document and says it does not read or change any open document. The plan's wording ('model_worksets ... choose process per call') supports target only."
  - "open_model is classed as process-level file opening. It takes `target` only; there is no pre-open document token to send, and no `document` parameter was invented. The docstring states it does not select, activate or change an already open document (activate_document does that), that the newly opened document must be read from the reply (document_title, activated, fields the route returns today) and never assumed, and that list_documents supplies its selector. The `activate` option keeps its meaning (activate the file that was just opened) and is not described as activating an existing document."
  - "Not claimed: that the route answers with a document selector for the opened model. It does not today (it returns document_title and activated); a selector in the reply, if wanted, is route-side work."

patterns-established:
  - "Process-level worksharing tools have no document argument and a test that only worksharing_tools.py can reach /open_model/, so a view or edit tool cannot gain a hidden file open"

requirements-completed: []  # Deliberately empty (02-08..02-10 precedent). MDOC-02/MDOC-03 cover every mutating tool and the route-side default/refusal (02-12); IDENT-02 needs mutating replies that name their document (02-12). This plan delivers only the tool-side contract for 6 more mutating tools and the target on the remaining views and worksharing tools.

coverage:
  - id: D1
    description: "Every Revit-facing callable of the six owned registrars forwards an optional `target` as the transport keyword (never in the body), including the revit_image fetch of get_revit_view; with no selector the call shape is unchanged"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_forwards_target_as_a_transport_keyword_never_in_the_body"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_forwards_nothing_extra_when_no_selector_is_given"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_every_transport_call_in_the_module_source_forwards_a_target"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_get_revit_view_fetches_the_image_with_the_target_and_keeps_the_view_name_in_the_path"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each of the 6 mutations forwards `document` in the POST body beside its own fields and keeps its legacy body when none is given"
    requirement: "MDOC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_mutations_forward_the_document_in_the_post_body_beside_their_own_fields"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_document_is_attached_exactly_once_per_mutation_in_the_module_source"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_tag_elements_keeps_its_legacy_body_and_adds_only_the_document"
        status: pass
    human_judgment: false
  - id: D3
    description: "Docstrings state the one-open-document default, the several-documents refusal, HTTP 412, that nothing is activated and the activate_document step on mutations; active-document scope with no document argument on reads; file-from-disk scope on list_model_worksets; file-open scope and reply-derived identity on open_model; every parameter including ctx named; no docstring claims an automatic retarget"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_docstrings_name_every_argument_and_state_the_scope_rule"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_mutation_docstrings_never_claim_a_document_is_retargeted_without_activation"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conventions.py (scripts/conventions.py tool-signature checks, unchanged)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Reads and process-level tools cannot be given a document (TypeError, nothing dispatched); a blank or non-string document on a mutation refuses without any send; mangled-path checks of open_model and list_model_worksets still refuse before sending"
    requirement: "MDOC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_reads_offer_no_way_to_name_a_document_and_never_dispatch_when_asked"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_mutations_refuse_a_blank_document_without_sending"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_worksharing_tools_still_refuse_a_mangled_path_before_sending"
        status: pass
    human_judgment: false
  - id: D5
    description: "open_model is process-level: it sends the exact selected target, no document token, only it reaches /open_model/, and the document it reports comes from the received reply rather than the requested path"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_open_model_is_process_level_and_sends_the_exact_target_and_no_document_token"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_open_model_reports_the_document_the_reply_names_not_the_requested_path"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_views.py#test_only_open_model_may_reach_the_file_open_route_no_view_or_edit_tool_opens_a_file"
        status: pass
    human_judgment: false
  - id: D6
    description: "Live behavior: a document selector passed to the 6 mutations actually refuses/guards on the Revit side (400 several documents, 412 inactive, reply naming the changed document), a target reaches the named process, and an open_model reply identifies the opened document on a real multi-document session"
    requirement: "MDOC-03"
    verification:
      - kind: manual_procedural
        ref: "not run - route-side guard is plan 02-12; live recheck 02-18"
        status: unknown
    human_judgment: true
    rationale: "This plan is tool-side and offline. The routes behind these tools do not read `document` until 02-12 lands, so the docstring behavior is a contract, not yet an observed fact."

duration: "about 6 min wall clock by the shell clock (start about 2026-10-22T18:47Z, end 18:53Z)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 11: target/document on structure, tag, transform, view and worksharing tools Summary

**All 12 tools of the structure, tag, transform, view-management, view and worksharing registrars now take an optional per-call `target`; the 6 real mutations (create_grid, create_structural_framing, tag_elements, transform_elements, create_view, set_active_view) also take an optional `document` forwarded in the POST body with the one-document default, the several-documents refusal, the inactive-412 rule and "nothing is activated" in their docstrings; the four view reads (including the image export) take `target` only; and `open_model` and `list_model_worksets` are explicitly process-level file tools with no `document` argument, `open_model` documented as opening a file (not activating an open document) whose result must be read from the reply.**

## Performance

- **Duration:** about 6 min (start about 2026-10-22T18:47Z, end 18:53Z)
- **Tasks:** 2 of 2, both `tdd="true"` with a separate RED commit each
- **Files:** 1 created (the forwarding test), 6 modified (all in `files_modified`)

## Accomplishments

- **Hand-made inventory of all 12 callables of the six registrars** in `tests/unit/test_tool_forwarding_views.py`: 6 mutations, 4 view reads, 1 file read (list_model_worksets) and 1 file open (open_model). A registration test fails if a registrar gains an unclassified tool.
- **Signatures.** Mutations: `legacy..., target=None, document=None, ctx=None`. Reads and process-level tools: `legacy..., target=None, ctx=None`. Pinned exactly and cross-checked by the unchanged `scripts/conventions.py`.
- **Forwarding is observed, not scanned.** Real registered functions run on a recording fake transport (GET, POST and IMAGE); rows assert route, `target` keyword and POST body. An AST check requires every `revit_get`/`revit_post`/`revit_image` call to splat transport options, and a source check requires exactly one `data["document"] = document` per mutation.
- **Image path.** `get_revit_view` now calls `revit_image(path, ctx, **_target_options(target))`; the view name stays in the path and the tool still returns the image or error string unformatted.
- **Edges preserved.** `tag_elements` keeps `add_leader`/`orientation` always in the body and its optional keys out unless given; `transform_elements` still forwards a zero `angle`; `list_model_worksets` keeps the `__ALL_USER_WORKSETS__` default; `open_model` keeps every option (including `activate=False`, `local_path`) and its mangled-path refusal and RSN pass-through, now also with a target. Millimeter payloads and route transaction behavior are untouched.
- **File open is not activation.** `open_model` takes no `document`; a test confirms its body never carries one, that it sends the exact selected target, that its reply is formatted verbatim (a reply naming a different document title is reported as such, never the requested path), and that no other module in the six contains the `/open_model/` route string, so a view or edit tool cannot gain a hidden file open. The docstring says it does not select, activate or change an already open document and names `activate_document` and `list_documents`.
- **No UI side effect from reads.** The four view reads say they never activate a document or switch views; each sends exactly one call (asserted for every tool), so none can trigger an activation or a workset dialog as a hidden extra request.
- **Blank selector guard.** A given-but-blank or non-string `document` refuses before any send (names `list_documents`).

## Task Commits

1. **Task 1 RED:** `f3e5d8d` (test) - 41 failing tests for structure, tag and transform tools (16 already passing: registration, manifest, etc.)
2. **Task 1 GREEN:** `b8d427a` (feat) - structure, tag and transform tools
3. **Task 2 RED:** `67f65a9` (test) - inventory extended to view, view-management and worksharing, worksharing/view-specific tests added; 55 failing
4. **Task 2 GREEN:** `0acad5f` (feat) - view, view-management and worksharing tools

## Verification (real numbers)

- Task 1 verify `uv run pytest tests/unit/test_tool_forwarding_views.py tests/unit/test_conventions.py tests/unit/test_registration.py -q`: **314 passed, 4 skipped**.
- Task 2 verify `uv run pytest tests/unit/test_tool_forwarding_views.py tests/unit/test_conventions.py tests/unit/test_registration.py tests/unit/test_format_response.py -q`: **419 passed, 3 skipped**.
- Plan verification `uv run pytest tests/unit -q`: **2090 passed, 3 skipped** (baseline 1953 passed, 3 skipped; +137, all in the new test file).
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.377** (<2.0).
- Offline only. No `mcp__revit__*` tool was called, no `execute_code`, no live bridge or Revit contact (`tests/unit/conftest.py` blocks real access). No accidental live contact.

## Deviations from Plan

None - plan executed exactly as written. Interface choices the plan left open: parameter order `target, document, ctx` (02-08..02-10 precedent); `document` omitted from the body when not given; set_active_view and create_view classed as document-bound mutations; the four view tools classed as reads with no `document` parameter (so "unsupported inactive read refuses before dispatch" is enforced by construction); list_model_worksets classed as a process-level disk read and open_model as process-level file opening, neither with a `document` parameter.

**Total deviations:** 0 auto-fixed. **Impact:** none on scope; no file outside `files_modified` was touched and no existing test needed a change.

## Issues Encountered / Surprises

- **Interim exposure (route side is 02-12), same as 02-08..02-10:** the routes behind the six mutations (`/create_grid/`, `/create_framing/`, `/tag_elements/`, `/transform_elements/`, `/create_view/`, `/set_active_view/`) do not read `document` yet. Until 02-12 lands, a model passing `document=<inactive doc>` gets the documented 412/400 only as a contract: the extra key is ignored and the call acts on the active document. These tools should not be used with `document` live before 02-12.
- **`open_model` does not return a document selector.** Its route replies with `document_title` and `activated` (read from `revit_mcp/worksharing.py`, offline reading, not a live observation). The tool docstring therefore tells the model to take the opened document from the reply and call `list_documents` for a selector. Whether a selector should also appear in the reply is route-side and not decided here.
- **`open_model` with several documents open.** This plan did not change or observe how the route behaves when the opened file is already open, or whether `OpenAndActivateDocument` changes UI state beyond activating the new file; nothing is claimed about it.
- Replies from the mutation tools still do not name the changed document or the answering process (route side 02-12; rendering 02-16).
- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on each commit (stale registered worktree, as in earlier plans). Commits succeeded.
- `tools/*.py` originals are CRLF; the rewrites were converted back to CRLF. `core.autocrlf=true` shows the new test file as stat-dirty in `git status` with an empty diff after CRLF restore; harmless.

## Known Stubs

None.

## Threat Flags

None new. T-02-03 (selector tampering) is mitigated tool-side by explicit forwarding and the blank-selector refusal; the server-side guard that enforces the resolved identity is 02-12 and is not claimed here. T-02-08 is addressed tool-side: no view or worksharing-inspection read can start an activation or a workset dialog (each sends one request and none reaches `/open_model/`). T-02-10 is addressed in the tool wording and reply pass-through (identity is taken from the received reply); the route replying with a document selector remains a later step.

## Not run / not claimed

- **Route-side behavior of `document`** (guard, 400/412, reply naming the changed document) is not implemented or observed here: 02-12, then live in 02-18.
- **Live behavior of `open_model` on a multi-document session** (what it replies, whether the opened document appears in `list_documents`, UI side effects) was not run.
- **`requirements-completed` is empty on purpose:** MDOC-02/MDOC-03 span every mutating tool and the route-side default (02-12); IDENT-02 needs mutating replies naming their document (02-12).
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted (they hold other sessions' work).

## Next Phase Readiness

- 02-12 must read `document` from the body of the routes listed above and call `mutation_document_or_response` from handlers that declare `uiapp`, `uidoc` or `doc` (live finding of 02-07). `/open_model/` must stay free of any document guard (it opens a file; the handler declares `doc` already).
- Stale docs outside this plan: CLAUDE.md "Current surface" tool/route counts.

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist: `f3e5d8d`, `b8d427a`, `67f65a9`, `0acad5f` (`git log --oneline`); `git rev-list --count e80e538c085afe1cd8b3ab5ab260f22275796964..HEAD` was 4; `git diff e80e538..HEAD --name-only` lists exactly the 7 files of `files_modified`; no tracked file deleted by any of them.
- Files exist: tests/unit/test_tool_forwarding_views.py (created, tracked); tools/structure_tools.py, tools/tag_tools.py, tools/transform_tools.py, tools/view_management_tools.py, tools/view_tools.py, tools/worksharing_tools.py (modified).
- `uv run pytest tests/unit -q`: 2090 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.377`.
