---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '10'
subsystem: api
tags: [mcp-tools, per-call-target, mutation-document, tool-contract, interop, mep, parameters, rooms, rollback, tdd]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-03 target-keyed bridge (revit_get/revit_post accept target=); 02-04..02-07 document selector tokens and the 412/400 mutation decision; 02-08/02-09 tool conventions (target, document, ctx order; _target_options/_blank_document helpers)
provides:
  - "Optional per-call `target` on every Revit-facing tool of tools/interop_tools.py, mep_tools.py, model_tools.py, parameter_tools.py, room_tools.py (11 tools)"
  - "Optional `document` on the 8 actual mutations (export_ifc, link_file, create_duct, create_pipe, create_mep_system, set_parameter, create_room, create_room_separation), forwarded in the POST body only when given and refused before any send when blank or non-string"
  - "Reads (list_levels, list_project_parameters, get_element_properties) take `target` only, have no `document` parameter, and say they read the active document of the selected process and that only read_document_summary/read_document_levels read an inactive one"
  - "set_parameter docstring states that a rolled-back write is an HTTP 409 error, never a success"
  - "tests/unit/test_tool_forwarding_model.py: 142 tests over a hand-classified inventory of all 11 callables of the five owned registrars, including a 409 rolled_back fixture asserted verbatim for every mutation"
affects: [02-11, 02-12, 02-16, 02-17]

actuals:
  tokens: 13198   # chars/4 over `git diff 0acd46b..HEAD` (52791 chars, 6 files incl. tests) at the last task commit; excludes this SUMMARY
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count 0acd46b1145f07e002fb2eb8b957fde1d9f3369f..HEAD before this SUMMARY commit (#3968)
plan_head_before: 0acd46b1145f07e002fb2eb8b957fde1d9f3369f

tech-stack:
  added: []
  patterns:
    - "Same per-module `_target_options` / `_blank_document` / `_BLANK_DOCUMENT_REFUSAL` helpers as 02-08/02-09 (repeated per module; tools/utils.py is outside files_modified)"
    - "Mutation vs read classified by hand per tool, never by HTTP method; a source check requires exactly one `data[\"document\"] = document` per mutation and an AST check requires every revit_get/revit_post call to splat transport options"
    - "A 409 rolled_back reply (bridge string 'Error: 409 - ...') must come back from every mutation tool byte-identical"

key-files:
  created:
    - tests/unit/test_tool_forwarding_model.py
  modified:
    - tools/interop_tools.py
    - tools/mep_tools.py
    - tools/model_tools.py
    - tools/parameter_tools.py
    - tools/room_tools.py

key-decisions:
  - "Parameter order for the optional-document mutations is `..., target, document, ctx`, identical to 02-08/02-09; reads are `..., target, ctx`."
  - "export_ifc is classed as a document-bound mutation (it writes a file from a document), the same call 02-09 made for export_document; link_file adds a link or import to a document. The plan names export/link as document-bound."
  - "list_levels, list_project_parameters and get_element_properties are reads: `target` only, no `document` parameter. Reading an inactive document is offered only by read_document_summary/read_document_levels (D-11), so the plan's 'clear refusal if a document argument is accidentally accepted' is met by construction (TypeError, nothing dispatched) rather than by a runtime refusal branch."
  - "The plan text lists `model_info` among the legacy reads, but tools/model_tools.py registers only list_levels; the model-info tool is get_revit_model_info in tools/status_tools.py, which is outside this plan's files_modified and was not touched. The status_tools tool keeps its `ctx`-only signature and `Scope: the active document only` text."
  - "set_parameter's rollback sentence is grounded in the route code (revit_mcp/parameters.py builds status `rolled_back`) and the existing test_format_response rollback tests; it is offline reading, not a live observation. Transaction outcome semantics (Phase 4) and units were not touched."

patterns-established:
  - "Rollback honesty fixture: every mutation tool of the module family returns the 'Error: 409 - {rolled_back ...}' string verbatim; a dict `rolled_back` is only formatted by format_response and never relabelled by the tool"

requirements-completed: []  # Deliberately empty (02-08/02-09 precedent). MDOC-02/MDOC-03 cover EVERY mutating tool and the route-side default/refusal (02-11, 02-12); IDENT-02 needs mutating replies that name their document (02-12). This plan delivers only the tool-side contract for 8 more mutating tools.

coverage:
  - id: D1
    description: "Every Revit-facing callable of the five owned registrars forwards an optional `target` as the transport keyword (never in the body); with no selector the call shape is unchanged"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_forwards_target_as_a_transport_keyword_never_in_the_body"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_forwards_nothing_extra_when_no_selector_is_given"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_every_transport_call_in_the_module_source_forwards_a_target"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each of the 8 mutations forwards `document` in the POST body beside its own fields and keeps its legacy body when none is given"
    requirement: "MDOC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_mutations_forward_the_document_in_the_post_body_beside_their_own_fields"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_document_is_attached_exactly_once_per_mutation_in_the_module_source"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_set_parameter_keeps_its_legacy_body_and_adds_only_the_document"
        status: pass
    human_judgment: false
  - id: D3
    description: "Docstrings state the one-open-document default, the several-documents refusal, HTTP 412, that nothing is activated and the activate_document step, and name every parameter including ctx; reads state active-document scope with no document argument; no docstring claims an automatic retarget"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_docstrings_name_every_argument_and_state_the_scope_rule"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_mutation_docstrings_never_claim_a_document_is_retargeted_without_activation"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conventions.py (scripts/conventions.py tool-signature checks, unchanged)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Reads cannot be given a document (TypeError, nothing dispatched); a blank or non-string document on a mutation refuses without any send; path checks of export_ifc and link_file still refuse before sending"
    requirement: "MDOC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_reads_offer_no_way_to_name_a_document_and_never_dispatch_when_asked"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_mutations_refuse_a_blank_document_without_sending"
        status: pass
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_export_ifc_and_link_file_still_refuse_a_mangled_path_before_sending"
        status: pass
    human_judgment: false
  - id: D5
    description: "A 409 rolled_back reply reaches the model verbatim from every mutation tool, never as a success"
    requirement: "T-02-02 (threat register)"
    verification:
      - kind: unit
        ref: "tests/unit/test_tool_forwarding_model.py#test_a_rolled_back_409_stays_a_visible_failure_never_a_success"
        status: pass
      - kind: unit
        ref: "tests/unit/test_format_response.py#test_rolled_back_409_reaches_the_model_as_a_visible_error"
        status: pass
    human_judgment: false
  - id: D6
    description: "Live behavior: a document selector passed to these 8 mutations actually refuses/guards on the Revit side (400 several documents, 412 inactive, reply naming the changed document), a target reaches the named process, and G6 (param write rollback) is diagnosed live"
    requirement: "MDOC-03"
    verification:
      - kind: manual_procedural
        ref: "not run - route-side guard is plan 02-12; live recheck 02-18; G6 live diagnosis is a later human-run gate"
        status: unknown
    human_judgment: true
    rationale: "This plan is tool-side and offline. The routes behind these tools do not read `document` until 02-12 lands, so the docstring behavior is a contract, not yet an observed fact."

duration: "about 4 min wall clock by the shell clock (start 2026-10-22T18:43:08Z, end about 18:47Z)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 10: target/document on interop, MEP, model, parameter and room tools Summary

**All 11 tools of the interop, MEP, model, parameter and room registrars now take an optional per-call `target`, and the 8 real mutations (export_ifc, link_file, create_duct, create_pipe, create_mep_system, set_parameter, create_room, create_room_separation) also take an optional `document` forwarded in the POST body with the one-document default, the several-documents refusal, the inactive-412 rule and "nothing is activated" in their docstrings; the three reads (list_levels, list_project_parameters, get_element_properties) get no `document` argument and say they read the active document only.**

## Performance

- **Duration:** about 4 min (start 2026-10-22T18:43:08Z, end about 18:47Z)
- **Tasks:** 2 of 2, both `tdd="true"` with a separate RED commit each
- **Files:** 1 created (the forwarding test), 5 modified (all in `files_modified`)

## Accomplishments

- **Inventory of all 11 callables of the five registrars** in `tests/unit/test_tool_forwarding_model.py`: 8 mutations and 3 reads. A registration test fails if a registrar gains an unclassified tool.
- **Signatures.** Mutations: `legacy..., target=None, document=None, ctx=None`. Reads: `legacy..., target=None, ctx=None`. Pinned exactly and cross-checked by the unchanged `scripts/conventions.py`.
- **Forwarding is observed, not scanned.** Real registered functions run on a recording fake transport; rows assert route, `target` keyword and POST body. A source/AST check additionally requires every `revit_get`/`revit_post` call to splat transport options and exactly one `data["document"] = document` per mutation.
- **Edges preserved.** `list_project_parameters` still sends its filter `params` and now also the target; `get_element_properties` keeps the id in the path; `export_ifc` and `link_file` still refuse a mangled path before any send (also with a document); optional body keys stay out of the body unless given.
- **Honest read scope (D-11).** `list_levels` points to `read_document_levels` for a named document and says it never reports an inactive document's levels as its own; `list_project_parameters` and `get_element_properties` say the same and name both addressed read tools. Nothing relabels active-model data as coming from an inactive selector (prohibition checked by construction: reads have no document parameter).
- **Rollback honesty (D-07 groundwork).** `set_parameter`'s docstring says a rolled-back write is HTTP 409 `rolled_back` and must be treated as a failed write. A parametrized fixture feeds the bridge-shaped `Error: 409 - {"status": "rolled_back", ...}` string to every mutation of the five modules and asserts it comes back byte-identical; a second test pins that a dict `rolled_back` is only run through `format_response`, never relabelled by a tool. No HTTP status or transaction semantics were changed.
- **Blank selector guard.** A given-but-blank or non-string `document` refuses before any send (names `list_documents`) and before the path checks.

## Task Commits

1. **Task 1 RED:** `56a4928` (test) - 50 failing tests for interop, MEP and model tools (23 already passing: registration, manifest, reads unaffected, etc.)
2. **Task 1 GREEN:** `29ecf6d` (feat) - interop, MEP and model tools
3. **Task 2 RED:** `c59d7cd` (test) - inventory extended to parameter and room tools, route-specific tests and the 409 fixture added; 43 failing
4. **Task 2 GREEN:** `6a5f817` (feat) - parameter and room tools; also fixes a bug in one of my own RED tests (`run_tool("create_room", name=...)` collided with the helper's own `name` argument), so that test was changed to call the registered tool directly. No assertion was weakened.

## Verification (real numbers)

- Task 1 verify `uv run pytest tests/unit/test_tool_forwarding_model.py tests/unit/test_conventions.py tests/unit/test_registration.py tests/unit/test_status_target.py -q`: **335 passed, 3 skipped** at the Task 1 commit.
- Task 2 verify `uv run pytest tests/unit/test_tool_forwarding_model.py tests/unit/test_conventions.py tests/unit/test_registration.py tests/unit/test_format_response.py -q` (run together with `test_status_target.py`): **429 passed, 3 skipped**.
- Plan verification `uv run pytest tests/unit -q`: **1953 passed, 3 skipped** (baseline 1811 passed, 3 skipped; +142, all in the new test file).
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.376** (<2.0).
- Offline only. No `mcp__revit__*` tool was called, no `execute_code`, no live bridge or Revit contact (`tests/unit/conftest.py` blocks real access). No accidental live contact.

## Deviations from Plan

None - plan executed exactly as written. Interface choices the plan left open: parameter order `target, document, ctx` (02-08/02-09 precedent); `document` omitted from the body when not given; export_ifc classed as a document-bound mutation; reads expose no `document` parameter, so "refusal if a document argument is accepted" is enforced by construction. One plan-text mismatch is reported, not a deviation: the plan mentions `model_info`, but `model_tools.py` holds only `list_levels` (see key-decisions).

**Total deviations:** 0 auto-fixed. **Impact:** none on scope; no file outside `files_modified` was touched and no existing test needed a change.

## Issues Encountered / Surprises

- **Interim exposure (route side is 02-12), same as 02-08/02-09:** the routes behind the eight mutations (`/export_ifc/`, `/link_file/`, `/create_duct/`, `/create_pipe/`, `/create_mep_system/`, `/set_parameter/`, `/create_room/`, `/create_room_separation/`) do not read `document` yet. Until 02-12 lands, a model passing `document=<inactive doc>` gets the documented 412/400 only as a contract: the extra key is ignored and the call acts on the active document. These tools should not be used with `document` live before 02-12.
- Replies from these tools still do not name the changed document or the answering process (route side 02-12; rendering 02-16).
- **`get_revit_model_info` is untouched:** it lives in `tools/status_tools.py`, outside this plan's files; its address/scope text is not changed here.
- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on each commit (stale registered worktree, as in 02-04..02-09). Commits succeeded.
- `tools/*.py` originals are CRLF; the rewrites were converted back to CRLF (line-level diffs). `core.autocrlf=true` makes the new test file show as stat-dirty in `git status` with an empty diff after a CRLF restore; harmless.

## Known Stubs

None.

## Threat Flags

None new. T-02-03 (selector tampering) is mitigated tool-side by explicit forwarding and the blank-selector refusal; the server-side guard that enforces the resolved identity is 02-12 and is not claimed here. T-02-02 (rollback repudiation) is covered tool-side by the verbatim-409 fixture; the live reproduction of the rollback defect is not run.

## Not run / not claimed

- **Route-side behavior of `document`** (guard, 400/412, reply naming the changed document) is not implemented or observed here: 02-12, then live in 02-18.
- **G6 (parameter write rollback) live diagnosis** and the G2/G5 live gates were not run.
- **`requirements-completed` is empty on purpose:** MDOC-02/MDOC-03 span every mutating tool and the route-side default (02-11, 02-12); IDENT-02 needs mutating replies naming their document (02-12).
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted (they hold other sessions' work).

## Next Phase Readiness

- 02-11 (worksharing open_model) and the remaining tool rollouts follow the same contract and test shape.
- 02-12 must read `document` from the body of the routes listed above and call `mutation_document_or_response` from handlers that declare `uiapp`, `uidoc` or `doc` (live finding of 02-07).
- Stale docs outside this plan: CLAUDE.md "Current surface" tool/route counts.

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist: `56a4928`, `29ecf6d`, `c59d7cd`, `6a5f817` (`git log --oneline 0acd46b..HEAD`); `git rev-list --count 0acd46b1145f07e002fb2eb8b957fde1d9f3369f..HEAD` was 4; no tracked file deleted by any of them.
- Files exist: tests/unit/test_tool_forwarding_model.py (created, tracked); tools/interop_tools.py, tools/mep_tools.py, tools/model_tools.py, tools/parameter_tools.py, tools/room_tools.py (modified).
- `uv run pytest tests/unit -q`: 1953 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.376`.
