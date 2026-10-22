---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '08'
subsystem: api
tags: [mcp-tools, per-call-target, mutation-document, tool-contract, analysis, annotation, building, clash, colors, tdd]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-03 target-keyed bridge (revit_get/revit_post accept target=); 02-04..02-07 documents, document selector tokens (doc1.<gen>.<n>), the 412/400 mutation decision and the only two addressed inactive reads
provides:
  - "Optional per-call `target` on every Revit-facing tool of tools/analysis_tools.py, annotation_tools.py, building_tools.py, clash_tools.py, colors_tools.py (11 tools)"
  - "Optional `document` on the 7 actual mutations (create_dimensions, tag_walls, create_line_based_element, create_surface_based_element, create_level, color_splash, clear_colors), forwarded in the POST body; omitted from the body when not given"
  - "Docstring contract per tool: reads say they read the active document of the selected process and point to read_document_summary/read_document_levels for inactive documents; mutations state the one-open-document default, the several-documents refusal, the HTTP 412 for an inactive document and activate_document"
  - "Client-side refusal of a blank/non-string document so it can never decay into the one-document default"
  - "tests/unit/test_document_contracts.py: hand-classified inventory of all 11 tools and 113 new tests (signature, docstring, forwarding, blank refusal, source and manifest cross-checks)"
affects: [02-09, 02-10, 02-11, 02-12, 02-16]

actuals:
  tokens: 11480   # chars/4 over `git diff 0184a32..HEAD` (45928 chars, 6 files incl. tests) at the last task commit; excludes this SUMMARY
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count 0184a325cd0131294a7ce6d83ebf828bb6763d2a..HEAD before this SUMMARY commit (#3968)
plan_head_before: 0184a325cd0131294a7ce6d83ebf828bb6763d2a

tech-stack:
  added: []
  patterns:
    - "Transport keyword built by a tiny module-level helper (`_target_options`): no `target` key at all when the caller gave none, so every pre-existing call shape is byte-identical"
    - "Mutation vs read is classified by hand per tool in a test inventory, never by HTTP method (analysis, clash and colors read through POST); a source check requires exactly one `data[\"document\"] = document` per mutation and none for a read"
    - "A read tool has no `document` parameter at all: the model cannot ask for an unmeasured inactive-document read, so no read is misadvertised as inactive-safe"

key-files:
  created: []
  modified:
    - tools/analysis_tools.py
    - tools/annotation_tools.py
    - tools/building_tools.py
    - tools/clash_tools.py
    - tools/colors_tools.py
    - tests/unit/test_document_contracts.py

key-decisions:
  - "Parameter order is `..., target, document, ctx` (02-PATTERNS: target and, for mutations, document before ctx); both default to None. This differs from document_tools where `document` is required and comes first; 02-09..02-11 should follow the order used here for optional-document mutations."
  - "Reads take `target` only. Document-select on an inactive read is refused by construction (no parameter) and by docstring; the only inactive reads remain read_document_summary and read_document_levels (D-11)."
  - "Classification: color_splash and clear_colors are mutations (they write/remove view color overrides); list_category_parameters, ai_element_filter, get_material_quantities and check_clashes are reads that travel as POST and get no document."
  - "`document` is put in the body only when given; a given-but-blank (empty, whitespace, non-string) value is refused before any send, because forwarding or dropping it would turn an explicit but broken choice into the one-open-document default."
  - "The shared `_blank_document` / `_target_options` helpers are repeated per module rather than added to tools/utils.py, which is outside files_modified; a later cleanup can hoist them."

patterns-established:
  - "Tool-side forwarding test seam: register one module on a recording fake transport and assert (method, route, body, transport options) for the no-selector, target-only and document cases"

requirements-completed: []  # Deliberately empty (02-02..02-07 precedent). MDOC-02/MDOC-03 cover EVERY mutating tool and the route-side default/refusal behavior (02-09..02-12); IDENT-02 needs mutating replies that name their document (02-12). This plan delivers the tool-side contract for 7 of the mutating tools only.

coverage:
  - id: D1
    description: "Every Revit-facing tool in the five modules accepts an optional `target` as a transport keyword (never in the body) and, when it is omitted, sends exactly the pre-existing call shape"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_addressing_forwards_target_as_a_transport_keyword_never_in_the_body"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_addressing_forwards_nothing_extra_when_no_selector_is_given"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each of the 7 mutating tools accepts `document`, forwards it in the POST body beside its own fields (color_splash with custom_colors, clear_colors) and keeps its legacy body when none is given"
    requirement: "MDOC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_addressing_mutations_forward_the_document_in_the_post_body"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_color_mutations_put_the_document_in_the_body_beside_their_own_fields"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_document_is_attached_exactly_once_per_mutation_in_the_module_source"
        status: pass
    human_judgment: false
  - id: D3
    description: "Mutation docstrings state the one-open-document default, the several-documents refusal, the HTTP 412 for an open-but-inactive document and the activate_document step; read docstrings state active-document-only scope and name the only two inactive reads; every parameter including ctx is in Args"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_addressing_docstrings_name_every_argument_and_state_the_scope_rule"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conventions.py (scripts/conventions.py tool-signature checks, unchanged)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Reads cannot be given a document; a blank or non-string document on a mutation refuses without any send and never reaches the default; color mutations keep their error wrapper and never raise"
    requirement: "MDOC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_addressing_reads_offer_no_way_to_name_a_document"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_addressing_mutations_refuse_a_blank_document_without_sending"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_color_mutations_keep_their_error_wrapper_and_never_raise"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live behavior: a document selector passed to these 7 mutations actually refuses/guards on the Revit side (400 several documents, 412 inactive, response naming the changed document), and a target reaches the named process"
    requirement: "MDOC-03"
    verification:
      - kind: manual_procedural
        ref: "not run - route-side guard is plan 02-12; live recheck 02-18"
        status: unknown
    human_judgment: true
    rationale: "This plan is tool-side and offline. The routes behind these tools do not read `document` until 02-12 lands, so the docstring behavior is a contract, not yet an observed fact."

duration: "about 4 min wall clock by the shell clock (start 2026-10-22T18:30:30Z, end about 18:35Z)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 08: target/document on analysis, annotation, building, clash and color tools Summary

**All 11 tools of the analysis, annotation, building, clash and color modules now take an optional per-call `target`, and the 7 real mutations (create_dimensions, tag_walls, the three building creators, color_splash, clear_colors) also take an optional `document` that is forwarded in the POST body and documented with the one-document default, the several-documents refusal and the inactive-412 rule; the 4 reads get no `document` argument at all.**

## Performance

- **Duration:** about 4 min (start 2026-10-22T18:30:30Z, end about 18:35Z)
- **Tasks:** 2 of 2, both `tdd="true"` with a separate RED commit each
- **Files:** 0 created, 6 modified (all in `files_modified`)

## Accomplishments

- **Inventory by hand, not by method.** `GROUP_ONE_TOOLS`/`GROUP_TWO_TOOLS` in `tests/unit/test_document_contracts.py` classify every tool: reads `ai_element_filter`, `export_room_data`, `get_material_quantities`, `analyze_model_statistics`, `check_clashes`, `list_category_parameters` (four of them POST); mutations `create_dimensions`, `tag_walls`, `create_line_based_element`, `create_surface_based_element`, `create_level`, `color_splash`, `clear_colors`. A registration test fails if a module gains an unclassified tool.
- **Signatures.** Reads: `legacy..., target=None, ctx=None`. Mutations: `legacy..., target=None, document=None, ctx=None`. Pinned exactly (order, defaults, `ctx` last) and cross-checked by the unchanged `scripts/conventions.py`.
- **Forwarding.** `target` goes as the transport keyword only when given, never in the body; `document` goes in the body only when given, so the no-selector call is byte-identical to the old one. The five modules still never import the transport and none of them fetches an image, so there is no image path that could lose a target.
- **Honest scope text.** Every read says it reads the document active in the selected process, has no document argument, and that only `read_document_summary` and `read_document_levels` read an inactive document. Mutations carry the same four-sentence document-choice paragraph. `list_category_parameters` says it is a read although it POSTs; `color_splash`/`clear_colors` say they write/remove color overrides.
- **Blank selector guard.** A given-but-blank or non-string `document` refuses before any send (it names `list_documents`), rather than decaying into the "only open document" default.

## Task Commits

1. **Task 1 RED:** `4561151` (test) - 47 failing tests for analysis/annotation/building (19 already passing: registration, legacy body shape, no-transport-import, reads rejecting `document=`)
2. **Task 1 GREEN:** `f78c616` (feat) - analysis, annotation, building tools
3. **Task 2 RED:** `4261e9b` (test) - inventory extended to clash and colors and the generic tests re-parametrized over all five modules; 25 failing
4. **Task 2 GREEN:** `404cf60` (feat) - clash and color tools

## Verification (real numbers)

- Task verify `uv run pytest tests/unit/test_document_contracts.py tests/unit/test_conventions.py -q`: **539 passed, 3 skipped** at the final commit.
- Plan verification `uv run pytest tests/unit -q`: **1649 passed, 3 skipped** (baseline 1536 passed, 3 skipped; +113, all in `test_document_contracts.py`; the RED-to-GREEN run for Task 1 alone was 1602 passed).
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.358** (<2.0).
- Acceptance, Task 1: signatures, Args and forwarding for the nine tools of analysis/annotation/building are pinned; no read advertises an inactive-document read (no `document` parameter, docstring points to the two measured reads). Task 2: `color_splash`/`clear_colors` carry `document`; `list_category_parameters` and `check_clashes` do not; no image fetch exists to lose a target.
- Offline only. No `mcp__revit__*` tool was called, no `execute_code`, no live bridge or Revit contact (`tests/unit/conftest.py` blocks real access). No accidental live contact.

## Deviations from Plan

None - plan executed exactly as written. Interface choices that the plan left open: parameter order `target, document, ctx` (see key-decisions); `document` omitted from the body when not given; the blank-document refusal and its error text are mine; a second pass renamed the Task 1 test names from `first_group` to `addressing` and parametrized them over all five modules in the Task 2 RED commit (test file only, no assertion weakened).

**Total deviations:** 0 auto-fixed. **Impact:** none on scope; no file outside `files_modified` was touched and no existing pin test needed a change.

## Issues Encountered / Surprises

- **Interim exposure to know about (route side is 02-12):** the routes behind the seven mutations (`/create_dimensions/`, `/tag_walls/`, `/create_line/`, `/create_surface/`, `/create_level/`, `/color_splash/`, `/clear_colors/`) do not read `document` yet. Until 02-12 lands, a model that passes `document=<inactive doc>` gets the docstring's promised 412/400 behavior only as a contract: the extra key is ignored and the call acts on the active document. 02-08 and 02-12 are both wave 9 and 02-12 has no dependency on 02-08, so the two should land together before any live use or release. Docstring text is the plan's required contract and I kept it, not weakened it.
- Replies from these tools still do not name the answering process or the changed document (02-16 renders provenance; 02-12 adds it on the route side).
- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on each commit (stale registered worktree pruned by git auto gc; same as 02-04..02-06). Commits succeeded.
- `tools/*.py` originals are committed with CRLF; the writes preserved it, so the diffs are line-level.

## Known Stubs

None.

## Threat Flags

None new. T-02-03 (selector tampering) is mitigated tool-side by explicit forwarding and the blank-selector refusal; the central server-side guard is 02-12 and is not claimed here. T-02-05: every call of these tools still goes through the injected target-keyed `revit_get`/`revit_post`; the modules import no transport and fetch no images.

## Not run / not claimed

- **Route-side behavior of `document`** (guard, 400/412, response naming the document) is not implemented or observed here: 02-12, then live in 02-18.
- **`requirements-completed` is empty on purpose:** MDOC-02/MDOC-03 span every mutating tool and the route-side default (02-09..02-12); IDENT-02 needs the mutating replies to name their document (02-12).
- **G2-production, G5-production collision (02-18) and G6** are untouched and not run.
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted (they hold other sessions' work).

## Next Phase Readiness

- 02-09..02-11 can copy this contract exactly: `target, document, ctx` order for optional-document mutations, the `_target_options`/`_blank_document` pattern, the document-choice paragraph, and the hand-classified inventory with the generic signature/docstring/forwarding tests (extend `ALL_ADDRESSING_TOOLS` and `ADDRESSING_MODULES`, or add a sibling file per the later plans).
- 02-12 must read `document` from the body of the seven routes above and call `mutation_document_or_response` from handlers that declare `uiapp`, `uidoc` or `doc` (live finding of 02-07).
- Stale docs outside this plan: CLAUDE.md "Current surface" tool/route counts.

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist: `4561151`, `f78c616`, `4261e9b`, `404cf60` (`git log --oneline 0184a32..HEAD`); `git rev-list --count 0184a325cd0131294a7ce6d83ebf828bb6763d2a..HEAD` was 4; no tracked file deleted by any of them.
- Files exist and are modified: tools/analysis_tools.py, tools/annotation_tools.py, tools/building_tools.py, tools/clash_tools.py, tools/colors_tools.py, tests/unit/test_document_contracts.py.
- `uv run pytest tests/unit -q`: 1649 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.358`.
