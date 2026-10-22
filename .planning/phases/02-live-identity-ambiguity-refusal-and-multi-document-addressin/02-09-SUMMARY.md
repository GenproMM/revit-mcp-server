---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '09'
subsystem: api
tags: [mcp-tools, per-call-target, mutation-document, tool-contract, detail, documentation, document-save, editing, family, tdd]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-03 target-keyed bridge (revit_get/revit_post accept target=); 02-04..02-07 document selector tokens (doc1.<gen>.<n>), the 412/400 mutation decision; 02-08 tool conventions (target, document, ctx order; _target_options/_blank_document helpers)
provides:
  - "Optional per-call `target` on every Revit-facing tool of tools/detail_tools.py, documentation_tools.py, document_tools.py (save_document), editing_tools.py, family_tools.py (13 tools changed; the four 02-04..02-06 document tools already had it)"
  - "Optional `document` on the 10 actual mutations (create_detail_line, create_sheet, create_schedule, export_document, save_document, delete_elements, modify_element, place_family, load_family, edit_family), forwarded in the POST body only when given"
  - "Docstring contract per tool: reads say they read the active document of the selected process and name read_document_summary/read_document_levels as the only inactive reads; mutations state the one-open-document default, the several-documents refusal, HTTP 412 for an inactive document, that nothing is activated, and activate_document"
  - "Client-side refusal of a blank/non-string document so it can never decay into the one-document default"
  - "tests/unit/test_tool_forwarding_documents.py: 162 tests over a hand-classified inventory of all 18 callables of the five owned registrars"
affects: [02-10, 02-11, 02-12, 02-16, 02-17]

actuals:
  tokens: 13497   # chars/4 over `git diff cda35a1..HEAD` (53990 chars, 6 files incl. tests) at the last task commit; excludes this SUMMARY
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count cda35a1e9cae93e4ce98bf7025c4834e59942250..HEAD before this SUMMARY commit (#3968)
plan_head_before: cda35a1e9cae93e4ce98bf7025c4834e59942250

tech-stack:
  added: []
  patterns:
    - "Same per-module `_target_options` / `_blank_document` / `_BLANK_DOCUMENT_REFUSAL` helpers as 02-08 (repeated per module; tools/utils.py is outside files_modified)"
    - "Mutation vs read classified by hand per tool, never by HTTP method; a source check requires exactly one `data[\"document\"] = document` per mutation and a transport-call AST check requires every revit_get/revit_post call to splat transport options"
    - "Addressed 02-04..02-06 tools (required `document` first) keep their signatures; this plan only pins their target forwarding"

key-files:
  created:
    - tests/unit/test_tool_forwarding_documents.py
  modified:
    - tools/detail_tools.py
    - tools/documentation_tools.py
    - tools/document_tools.py
    - tools/editing_tools.py
    - tools/family_tools.py

key-decisions:
  - "Parameter order for the optional-document mutations is `..., target, document, ctx`, identical to 02-08. The 02-04..02-06 tools keep their required `document` first; save_document is a mutation with an optional document, so it follows 02-08."
  - "export_document is classed as a document-bound mutation (it writes a file and its route opens a transaction on the document), so it takes `document`; the plan names document exports as document-bound."
  - "get_selected_elements, list_families and list_family_categories are reads: `target` only, no `document` parameter. A read offers no way to ask for an unmeasured inactive-document read (D-11), so the plan's 'refuses if a document argument is supplied' is satisfied by construction (TypeError, no dispatch)."
  - "`document` is put in the body only when given; a given-but-blank value (empty, whitespace, non-string) is refused before any send, and before the save_document / load_family path check."
  - "Docstrings never claim a retarget: every mutation says 'nothing is activated' and points to activate_document. edit_family and save_document say they make no activation call; nothing is claimed about what the family editor does to UI state (prohibition P1, unverified)."

patterns-established:
  - "Forwarding table over the real registered tool functions with a recording fake transport: dropping a target or document makes a specific row fail"

requirements-completed: []  # Deliberately empty (02-08 precedent). MDOC-02/MDOC-03 cover EVERY mutating tool and the route-side default/refusal behavior (02-10..02-12); IDENT-02 needs mutating replies that name their document (02-12). This plan delivers only the tool-side contract for 10 more mutating tools.

coverage:
  - id: D1
    description: "Every Revit-facing callable of the five owned registrars forwards an optional `target` as the transport keyword (never in the body); with no selector the call shape is unchanged"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_forwards_target_as_a_transport_keyword_never_in_the_body"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_forwards_nothing_extra_when_no_selector_is_given"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_every_transport_call_in_the_module_source_forwards_a_target"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each of the 10 mutations (including save_document, delete/modify and the family tools) forwards `document` in the POST body beside its own fields and keeps its legacy body when none is given"
    requirement: "MDOC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_mutations_forward_the_document_in_the_post_body_beside_their_own_fields"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_document_is_attached_exactly_once_per_mutation_in_the_module_source"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_save_document_keeps_its_legacy_body_and_adds_only_the_document"
        status: pass
    human_judgment: false
  - id: D3
    description: "Docstrings state the one-open-document default, the several-documents refusal, HTTP 412, that nothing is activated and the activate_document step, and name every parameter including ctx; no docstring claims an automatic retarget"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_docstrings_name_every_argument_and_state_the_scope_rule"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_mutation_docstrings_never_claim_a_document_is_retargeted_without_activation"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conventions.py (scripts/conventions.py tool-signature checks, unchanged)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Reads cannot be given a document (TypeError, nothing dispatched); a blank or non-string document on a mutation refuses without any send; path checks of save_document and load_family still refuse before sending"
    requirement: "MDOC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_reads_offer_no_way_to_name_a_document_and_never_dispatch_when_asked"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_mutations_refuse_a_blank_document_without_sending"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_documents.py#test_save_document_still_refuses_a_mangled_path_before_sending_even_with_a_document"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live behavior: a document selector passed to these 10 mutations actually refuses/guards on the Revit side (400 several documents, 412 inactive, reply naming the saved/edited document), Save/SaveAs outside any transaction with a selected document, and a target reaches the named process"
    requirement: "MDOC-03"
    verification:
      - kind: manual_procedural
        ref: "not run - route-side guard is plan 02-12; live recheck 02-18"
        status: unknown
    human_judgment: true
    rationale: "This plan is tool-side and offline. The routes behind these tools do not read `document` until 02-12 lands, so the docstring behavior is a contract, not yet an observed fact."

duration: "about 4 min wall clock by the shell clock (start 2026-10-22T18:37:15Z, end about 18:41Z)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 09: target/document on detail, documentation, save, editing and family tools Summary

**All 13 changed tools of the detail, documentation, document (save), editing and family registrars now take an optional per-call `target`, and the 10 real mutations (create_detail_line, create_sheet, create_schedule, export_document, save_document, delete_elements, modify_element, place_family, load_family, edit_family) also take an optional `document` forwarded in the POST body and documented with the one-document default, the several-documents refusal, the inactive-412 rule and an explicit "nothing is activated"; the three reads (get_selected_elements, list_families, list_family_categories) get no `document` argument at all.**

## Performance

- **Duration:** about 4 min (start 2026-10-22T18:37:15Z, end about 18:41Z)
- **Tasks:** 2 of 2, both `tdd="true"` with a separate RED commit each
- **Files:** 1 created (the forwarding test), 5 modified (all in `files_modified`)

## Accomplishments

- **Hand-made inventory of all 18 callables of the five registrars** in `tests/unit/test_tool_forwarding_documents.py`: 10 mutations, 4 reads (list_documents, get_selected_elements, list_families, list_family_categories) and 4 addressed 02-04..02-06 tools (activate_document, read_document_summary, read_document_levels have a required `document` first; they are pinned only for target forwarding and an unchanged signature). A registration test fails if a registrar gains an unclassified tool; the worksharing file-open tool is asserted absent (02-11 owns it).
- **Signatures.** Mutations: `legacy..., target=None, document=None, ctx=None`. Reads: `legacy..., target=None, ctx=None`. Pinned exactly and cross-checked by the unchanged `scripts/conventions.py`.
- **Forwarding is observed, not scanned.** Real registered functions run on a recording fake transport; rows assert route, `target` keyword, and POST body. A source/AST check additionally requires every `revit_get`/`revit_post` call in the five modules to splat transport options, and exactly one `data["document"] = document` per mutation.
- **Edge preserved.** `list_families` still sends its `params` and now also the target; `save_document` keeps its optional `as_central` key out of the body unless given, and still refuses a mangled path before any send (also with a document); `load_family` likewise.
- **Honest scope text.** Reads say they read the active document of the selected process, have no document argument and that only `read_document_summary`/`read_document_levels` read an inactive one. Mutations carry the same document-choice paragraph as 02-08; `export_document` says it writes a file and so follows the same document rule; `edit_family` and `save_document` say they make no activation call. No docstring claims an automatic retarget (prohibition P1 is checked by a test over the wording).
- **Blank selector guard.** A given-but-blank or non-string `document` refuses before any send (names `list_documents`) and before the path checks.

## Task Commits

1. **Task 1 RED:** `4bdd074` (test) - 34 failing tests for detail and documentation tools (16 already passing: registration, reads unaffected, etc.)
2. **Task 1 GREEN:** `7a0b631` (feat) - detail and documentation tools; the generic docstring test was made whitespace-normalizing in this commit (no assertion weakened)
3. **Task 2 RED:** `0b81323` (test) - inventory extended to all five registrars and the route-specific tests added; 65 failing
4. **Task 2 GREEN:** `951f8a6` (feat) - save_document, editing and family tools

## Verification (real numbers)

- Task 1 verify `uv run pytest tests/unit/test_tool_forwarding_documents.py tests/unit/test_conventions.py tests/unit/test_registration.py -q`: **307 passed, 5 skipped** at the Task 1 commit.
- Task 2 verify `uv run pytest tests/unit/test_tool_forwarding_documents.py tests/unit/test_conventions.py tests/unit/test_registration.py tests/unit/test_status_target.py -q` (run together with `test_document_contracts.py`, which must not regress): **717 passed, 3 skipped**.
- Plan verification `uv run pytest tests/unit -q`: **1811 passed, 3 skipped** (baseline 1649 passed, 3 skipped; +162, all in the new test file).
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.366** (<2.0).
- Acceptance, Task 1: all four callables of the two modules carry `target`; the real mutations carry `document` with refusal guidance. Task 2: every row of the forwarding table resolves to a callable of one of the five registrars (registration test), save/edit/family forward target and document, no row for worksharing.
- Offline only. No `mcp__revit__*` tool was called, no `execute_code`, no live bridge or Revit contact (`tests/unit/conftest.py` blocks real access). No accidental live contact.

## Deviations from Plan

None - plan executed exactly as written. Interface choices the plan left open: parameter order `target, document, ctx` (02-08 precedent); `document` omitted from the body when not given; export_document classed as a document-bound mutation; reads expose no `document` parameter (so "refuses if a document argument is supplied" is enforced by construction); the blank-document refusal text is the 02-08 text.

**Total deviations:** 0 auto-fixed. **Impact:** none on scope; no file outside `files_modified` was touched and no existing test needed a change.

## Issues Encountered / Surprises

- **Interim exposure (route side is 02-12), same as 02-08:** the routes behind the ten mutations (`/create_detail_line/`, `/create_sheet/`, `/create_schedule/`, `/export_document/`, `/save_document/`, `/delete_elements/`, `/modify_element/`, `/place_family/`, `/load_family/`, `/edit_family/`) do not read `document` yet. Until 02-12 lands, a model passing `document=<inactive doc>` gets the documented 412/400 only as a contract: the extra key is ignored and the call acts on the active document. For `save_document`, `delete_elements` and `export_document` this means a file write or deletion lands on the active document. These tools should not be used with `document` live before 02-12.
- Replies from these tools still do not name the saved/edited document or answering process (route side 02-12; rendering 02-16). T-02-10 (save responses carry actual attribution) is therefore not yet mitigated.
- The Revit-side `save_document` route is untouched, so "Save/SaveAs outside any transaction" is unchanged by construction, not re-verified.
- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on each commit (stale registered worktree, same as 02-04..02-08). Commits succeeded.
- `tools/*.py` originals are CRLF; the writes preserved it (line-level diffs; `file` confirms CRLF).
- A scripted edit of the `save_document` docstring initially collapsed `\\Models\\ESB.rvt` to single backslashes (a shell-quoting artifact); caught by the SyntaxWarning in the test run and fixed before the commit.

## Known Stubs

None.

## Threat Flags

None new. T-02-03 (selector tampering) is mitigated tool-side by explicit forwarding and the blank-selector refusal; the server-side guard that enforces the resolved identity is 02-12 and is not claimed here. T-02-10 is not mitigated by this plan (replies naming the document are 02-12/02-16).

## Not run / not claimed

- **Route-side behavior of `document`** (guard, 400/412, reply naming the saved/edited document) is not implemented or observed here: 02-12, then live in 02-18.
- **`requirements-completed` is empty on purpose:** MDOC-02/MDOC-03 span every mutating tool and the route-side default (02-10..02-12); IDENT-02 needs mutating replies naming their document (02-12).
- **G2-production, G5-production collision (02-18) and G6** are untouched and not run.
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted (they hold other sessions' work).

## Next Phase Readiness

- 02-10/02-11 can follow the same contract and test shape; worksharing `open_model` (02-11) is deliberately not in this inventory.
- 02-12 must read `document` from the body of the routes listed above and call `mutation_document_or_response` from handlers that declare `uiapp`, `uidoc` or `doc` (live finding of 02-07). Notably `save_document` must stay outside any transaction.
- Stale docs outside this plan: CLAUDE.md "Current surface" tool/route counts.

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist: `4bdd074`, `7a0b631`, `0b81323`, `951f8a6` (`git log --oneline cda35a1..HEAD`); `git rev-list --count cda35a1e9cae93e4ce98bf7025c4834e59942250..HEAD` was 4; no tracked file deleted by any of them.
- Files exist: tests/unit/test_tool_forwarding_documents.py (created); tools/detail_tools.py, tools/documentation_tools.py, tools/document_tools.py, tools/editing_tools.py, tools/family_tools.py (modified).
- `uv run pytest tests/unit -q`: 1811 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.366`.
