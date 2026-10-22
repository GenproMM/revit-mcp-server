---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '06'
subsystem: api
tags: [addressed-reads, g3-document-only-path, document_summary, document_levels, d-11, ui-switched-diagnostic, ironpython3]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-04 registry (resolve_document, retained-reference Equals, tombstones) and documents.py route module; 02-05 activation and the run_activation orchestration pattern; 02-20 accepted G3 document-only-path
provides:
  - "revit_mcp/documents.py POST /document_summary/ and POST /document_levels/, the only two routes that read an open but inactive document, with run_document_read (shared resolve, refuse, collect, before/after diagnostics), collect_document_summary, collect_document_levels and their run_* wrappers"
  - "tools/document_tools.py read_document_summary(document, target=None, ctx=None) and read_document_levels(document, target=None, ctx=None) with docstrings that list every returned field"
  - "tests/unit/test_document_contracts.py: 49 new tests (28 in Task 1, 21 in Task 2), 136 to 185 in that file"
affects: [02-07, 02-08, 02-09, 02-10, 02-11, 02-18]

actuals:
  tokens: 16600   # chars/4 over `git diff 627579c..HEAD` (66573 chars) at the last task commit; excludes this SUMMARY
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count 627579c1a8ab54e32c703405a1d7f575dd40175b..HEAD before this SUMMARY commit (#3968)
plan_head_before: 627579c1a8ab54e32c703405a1d7f575dd40175b

tech-stack:
  added: []
  patterns:
    - "One orchestration (run_document_read) over an injected snapshot reader, registry and a collect(document) callable; the DB namespace and the element-id reader are injected too (module-level _db / _element_id_value, patchable), so the CPython suite drives real route code with a fake DB that records the Document every collector is built on"
    - "A read refusal is a finished reply decided before any collector exists (selector missing, invalid, stale, unknown, closed, ambiguous, registry unreadable); the collector only ever receives the Document the registry resolved in this very request"
    - "The UI-active document is observed, never used as data: before and after the collection it is re-read through the identity snapshot and reported as active_before / active_after / ui_switched (None when unreadable, never defaulted to false)"

key-files:
  created: []
  modified:
    - revit_mcp/documents.py
    - tools/document_tools.py
    - tests/unit/test_document_contracts.py
    - tests/unit/tool_manifest.txt

key-decisions:
  - "Summary fields are exactly the G3-measured set (title, path, non-type element count via FilteredElementCollector.WhereElementIsNotElementType on that Document, level count) plus project_information name/number/client/status read from that Document's own ProjectInformation. A project-information field that cannot be read is omitted and named in unreadable_fields, never filled from elsewhere. The plan's 'fields beyond the measured set' that 02-07 must recheck: project_information.* and the level_count collector (OfCategory(OST_Levels)), plus every field of the levels reply."
  - "Omitted: any model_info-style category counts, warnings, views and rooms (model_info.py reads revit.doc, RevitProjectInfo and pyrevit queries; none were reviewed as Document-only, so none were carried over). Project information is read straight from Document.ProjectInformation rather than through pyrevit's ProjectInfo wrapper for the same reason."
  - "Levels route returns the list_levels fields (name, elevation_mm, elevation_feet, id) sorted by elevation, plus total_levels and skipped_levels. A level that cannot be read is skipped, logged and counted (list_levels behavior) but the count is now visible in the reply."
  - "Reply vocabulary: 200 success with target_is_active / ui_switched / active_before / active_after (+ active_before_error / active_after_error); 400 document-selector-required / document-selector-invalid / document-identity-ambiguous and request-body-invalid; 404 document-closed / document-token-stale / document-token-unknown; 500 document-read-failed (collector raised; names the attempted and the observed active document, carries no data) and document-read-error (handler-level); 503 document-registry-unavailable and the 02-04 503s. 412 is never returned by a read: an inactive document is the allowed case, not a refusal."
  - "Tool signature is (document, target=None, ctx=None), matching activate_document, not the plan's loose '(target, document, ctx)': a required argument cannot follow a defaulted one, and document is required (omission refuses without POSTing)."
  - "Both routes are locked by default (only GET /status/ is unlocked) and take the request only, the same shape as /activate_document/; whether pyRevit injects a request-only handler stays an 02-07 live question (carried from 02-05)."

patterns-established:
  - "'Exactly two reads' is a pinned fact: a test lists the documents.py route inventory and asserts decide_mutation_document still answers 412 for the same inactive document after both reads succeed"
  - "The collector and its helpers are scanned on AST identifiers for UI or active-document dependencies (ActiveUIDocument, HOST_APP, uiapp, UIDocument, ActiveView, uidoc, revit, doc, OpenAndActivateDocument); the module as a whole has no ActiveUIDocument identifier at all"

requirements-completed: []  # Deliberately empty (02-02..02-05 precedent). IDENT-02, IDENT-03, MDOC-01 and MDOC-05 are advanced offline here, but the plan itself says no inactive-read safety is proved before the live recheck, and no mutating response names its document yet.

coverage:
  - id: R1
    description: "With A active and B selected, /document_summary/ derives title, path, non-type element count, level count and project information from B only, carries B's descriptor, reports target_is_active=false, makes no activation call and leaves the active document as it was"
    requirement: "MDOC-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_summary_of_an_inactive_document_is_read_from_that_document_only"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_summary_reports_the_active_flag_and_the_before_and_after_diagnostics"
        status: pass
    human_judgment: false
  - id: R2
    description: "/document_levels/ returns B's own levels in millimeters (feet rounded to 4 places), sorted, with ids, a skipped-level count, non-ASCII names preserved, an empty list for a model without levels, and never A's levels"
    requirement: "MDOC-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_levels_of_an_inactive_document_are_its_own_in_millimeters_sorted_by_elevation"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_elevations_are_converted_from_feet_and_rounded_like_list_levels"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_a_level_that_cannot_be_read_is_skipped_and_counted_never_silently_dropped"
        status: pass
    human_judgment: false
  - id: R3
    description: "D-08: closed, replaced-with-identical-title-and-path, stale, unknown, malformed, ambiguous and omitted selectors and an unreadable registry are refused by name before any collector is built, for both reads; the reply carries no summary or levels and is never relabeled as active-model data; each request resolves the token again"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_a_closed_token_is_refused_by_name_even_for_an_addressed_read"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_unknown_stale_malformed_and_omitted_selectors_refuse_without_collecting"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_an_ambiguous_lifetime_refuses_and_collects_nothing"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_every_request_resolves_the_live_token_again"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_a_closed_token_never_yields_the_levels_of_an_open_document"
        status: pass
    human_judgment: false
  - id: R4
    description: "A collector failure is a named 500 (document-read-failed) naming the attempted and observed active documents with no data; a switch of the active document during the read is reported (ui_switched=true) and an unreadable after-state is reported as unknown (null), never as false"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_a_collector_that_raises_is_a_named_500_with_no_data_and_the_observed_active_document"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_a_switch_of_the_active_document_during_the_read_is_reported_not_hidden"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_an_unreadable_after_state_leaves_the_switch_unknown_not_false"
        status: pass
    human_judgment: false
  - id: R5
    description: "Exactly two routes can read an inactive document; the mutation guard still answers 412 for the same inactive document after both reads; the collectors and helpers contain no UI, active-view or revit-global identifier and the module never reads ActiveUIDocument"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_exactly_two_routes_read_an_inactive_document_and_the_mutation_guard_is_unchanged"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_the_summary_collector_and_its_helpers_have_no_ui_or_active_document_dependency"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_the_level_collector_and_its_helpers_have_no_ui_or_active_document_dependency"
        status: pass
    human_judgment: false
  - id: R6
    description: "Both routes are POST handlers taking only the request, accept a text/plain bytes or dict body, answer 400 to a missing or malformed body, keep process_identity (or identity_error) on every reply and never raise; both tools post the token and target, render the data with a diagnostic line and the answering process, pass refusals through as text, refuse a blank document without POSTing, keep ctx last and list every returned field in the docstring; both are in the manifest"
    requirement: "MDOC-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_the_summary_route_never_raises"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_the_levels_route_refusals_keep_status_and_process_and_it_never_raises"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_read_document_summary_signature_and_docstring_are_the_api_contract"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_read_document_levels_signature_and_docstring_are_the_api_contract"
        status: pass
      - kind: unit
        ref: "tests/unit/test_registration.py#test_tool_names_match_the_manifest"
        status: pass
    human_judgment: false
  - id: R7
    description: "Production behavior of /document_summary/ and /document_levels/ on live Revit: B's data with A active and A's data with B active (A/B and B/A), target_is_active=false and ui_switched=false on the production routes (not the 02-20 diagnostic button), no dialog, the request-only handler signature under pyRevit injection, Document.ProjectInformation reads on a real nonactive Document, the OfCategory(OST_Levels) count and Level.Elevation/Name/id reads on a nonactive Document, get_element_id_value on 2024-2027"
    requirement: "MDOC-01"
    verification:
      - kind: manual_procedural
        ref: "not run - 02-07 live recheck after a full Revit restart (never pyRevit Reload)"
        status: unknown
    human_judgment: true
    rationale: "The offline fake DB records which Document a collector is built on; it cannot show whether a real FilteredElementCollector on a nonactive Document touches the UI, whether pyRevit's ExternalEvent dispatch of a Routes handler preserves focus, or whether any Revit API read used here quietly depends on the active view. G3 measured the 02-20 diagnostic path only."

duration: "7 min (start 07:24:32Z, end ~07:31Z)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 06: Addressed summary and levels reads Summary

**`POST /document_summary/` and `POST /document_levels/` (tools `read_document_summary` and `read_document_levels`) read the model summary and the levels of one explicitly selected open document, including a nonactive one, only through the Document the registry resolved in that request; a closed, stale, unknown, ambiguous or missing token is refused by name before any collector exists, nothing is activated, and every reply reports the active document before and after as an observation (`ui_switched`), never as proof.**

## Performance

- **Duration:** 7 min (start 2026-10-22T07:24:32Z, end ~07:31Z)
- **Tasks:** 2 of 2, both `tdd="true"` with a separate RED commit each
- **Files:** 0 created, 4 modified (all in `files_modified`)

## Accomplishments

- **One shared orchestration** (`run_document_read`): resolves the token with `resolve_document` (never `decide_mutation_document`, so an inactive document is an allowed read and 412 never appears), turns every refusal into a finished 400/404/503 reply carrying the observed active document, then hands the freshly resolved Document wrapper to a `collect(document)` callable. The active document is read before and after through the same identity snapshot and reported as `active_before`, `active_after`, `ui_switched` (None when either read failed). A collector that raises is a named 500 `document-read-failed` that names the attempted and the observed active document and carries no data.
- **Summary** (`collect_document_summary`): title, path, non-type element count (`FilteredElementCollector(document).WhereElementIsNotElementType().GetElementCount()`), level count (same, `OfCategory(OST_Levels)`), and `project_information` name/number/client/status read from `document.ProjectInformation`. A field that cannot be read is omitted and named in `unreadable_fields`. These are the G3-measured comparison fields, explicitly not the `model_info` category subset (the tool and route docstrings and the rendered text say so).
- **Levels** (`collect_document_levels`): `FilteredElementCollector` on that Document, name sanitized (non-ASCII preserved, None becomes "Unnamed"), `elevation_mm = round(feet * 304.8, 0)`, `elevation_feet` to 4 places, id through `get_element_id_value`, sorted by elevation; unreadable levels skipped, logged and counted in `skipped_levels`.
- **Tools** pass `target` through the injected transport, refuse a blank `document` without POSTing, render the data plus one honest diagnostic sentence (unchanged / WARNING changed / unknown) and the answering process, and pass refusals through unrendered as data. Docstrings list every returned field, say "exactly two reads", say the summary counts are not model_info counts, and say the live recheck (02-07) has not been run.
- **Guards pinned by tests:** the route inventory in `documents.py` is exactly `/documents/`, `/activate_document/`, `/document_summary/`, `/document_levels/`; `decide_mutation_document` still answers 412 for the same inactive document after both reads succeed; the whole-file AST test from 02-05 (one activation call site, no save/open/event machinery) still passes with the new code; the new collectors have no `ActiveUIDocument`/`HOST_APP`/`uiapp`/`UIDocument`/`ActiveView`/`uidoc`/`revit`/`doc` identifier and the module has no `ActiveUIDocument` identifier at all.

## Task Commits

1. **Task 1 RED:** `e810b9f` (test) - 28 failing tests (`run_document_summary` absent, route not registered, tool and manifest line missing); the 108 earlier tests kept passing
2. **Task 1 GREEN:** `c5a8cde` (feat) - summary collector, shared orchestration, route, tool, manifest line
3. **Task 2 RED:** `95c4e99` (test) - 21 failing tests: `run_document_levels` absent, route/tool/manifest missing
4. **Task 2 GREEN:** `eee6d86` (feat) - levels collector, route, tool, manifest line

## Verification (real numbers)

- Task 1 verify `uv run pytest tests/unit/test_document_contracts.py tests/unit/test_registration.py -q`: **147 passed** (all green at the GREEN commit; plus `test_conventions.py`: 393 passed, 3 skipped).
- Task 2 verify `uv run pytest tests/unit/test_document_contracts.py tests/unit/test_registration.py tests/unit/test_conventions.py -q`: **414 passed, 3 skipped**.
- Plan verification `uv run pytest tests/unit -q`: **1205 passed, 3 skipped** (baseline 1156 passed, 3 skipped; +49, all in `test_document_contracts.py`). `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.422** (<2.0).
- Acceptance criteria, Task 1: B's title/path/counts/project information with B's descriptor and no activation call (`uiapp.calls == []`, active document unchanged); closed B returns a named 404 with no data; other addressed legacy reads remain unsupported (route inventory pin plus the 412 guard test). Task 2: B's own names and elevations in millimeters, never A's; unmeasured reads are not advertised (docstrings say exactly two; no other route accepts a selector for an inactive read).
- Offline only. `tests/unit/conftest.py` blocks real Revit and socket access; no `mcp__revit__*` tool was called, Revit was not started, stopped, reloaded or activated, and no live bridge was touched. No accidental live contact.

## Deviations from Plan

**Interface choices (not deviations from a stated requirement):**

- The tool signature is `(document, target=None, ctx=None)`, not the artifacts line's `(target, document, ctx)`: the required argument cannot follow a defaulted one in Python, and it matches `activate_document`.
- The reply vocabulary (`document-read-failed`, `document-read-error`, `target_is_active`, `ui_switched`, `active_before`, `active_after`, `unreadable_fields`, `skipped_levels`) is mine; the plan fixes none of it. See key-decisions.
- `_resolve_for_read` repeats about 30 lines of `run_activation`'s resolve-and-refuse code with read-specific wording ("read" instead of "activate") rather than refactoring the proven 02-05 function; the two can be merged later, but changing `run_activation` was outside this plan's need and its 55 tests are the only guard.

None of Rules 1-4 triggered; no file outside `files_modified` was touched, and no pin test needed a change (the registration, conventions and tool-count style tests passed unmodified, including the manifest comparison once the two names were added).

**Total deviations:** 0 auto-fixed. **Impact:** none on scope.

## Issues Encountered / Surprises

- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on every commit (stale registered worktree pruned by git's auto gc, same as 02-04 and 02-05). Commits succeeded; environment condition.
- While tidying the Task 2 RED tests I removed a leftover junk line and a `globals()["read_rig"]()` indirection before the RED commit; the committed RED run failed only on the missing levels code (21 failures, 136 passes).
- Both task GREEN runs passed on the first run; no auto-fix attempt was needed.

## Known Stubs

None.

## Threat Flags

None new. The two routes expose title, path, counts, project information (name/number/client) and levels of an open inactive model to any local client of the Routes server, which is the T-02-09 disposition (narrow, measured-class reads only) and the existing T-02-07 posture (local clients, no authentication claimed).

## Not run / not claimed

- **G3 live behavior on the production routes is not run.** G3 (accepted in 02-20) measured a diagnostic button on PID 88388 in both directions (nonactive COORD with VENT active, nonactive detached VENT with COORD active; `target_is_active=false`, `ui_switched=false`) for non-type element and level counts. These production routes are a different code path (pyRevit's ExternalEvent dispatch of a Routes handler). Not measured, and so not claimed: that they preserve UI focus, that `Document.ProjectInformation` reads, the `OfCategory(OST_Levels)` collector, `Level.Name`/`Level.Elevation`/`get_element_id_value` on a nonactive Document do not depend on the active view, that no dialog appears, that a request-only `(request)` handler signature is injected, and that `ui_switched` reads correctly through the real `ActiveUIDocument`. All of that is 02-07's live recheck after a full Revit restart.
- **G2-production and G4 live behavior are not run** (unchanged from 02-04/02-05). **G6 is not authorized and not touched.**
- **Requirements are not marked complete.** `requirements-completed` is empty: the plan states no inactive-read safety is proved before the live gate, and IDENT-02 (mutating responses name their document) is not met by reads alone.
- **Revit restart required.** `revit_mcp/documents.py` is `revit_mcp/` code on the IronPython side and the extension directory is a junction to this repo. Before any live test of `/document_summary/` or `/document_levels/` fully close and reopen Revit; pyRevit Reload can crash the process (CLAUDE.md). `/status/` should still list `documents` among registered domains.
- `bridge.py` was not touched: both routes are locked by default (only `GET /status/` skips the lock); `NEVER_UNLOCKED` is as it was.

## Next Phase Readiness

- 02-07 has two concrete production routes to measure A/B and B/A, with a bounded field list (summary: title, path, `non_type_element_count`, `level_count`, `project_information.*`; levels: `name`, `elevation_mm`, `elevation_feet`, `id`) and the diagnostics to read: `target_is_active`, `ui_switched`, `active_before`, `active_after`, `process_identity`. The fields beyond the G3-measured set are `project_information.*` and every levels field; the counts mirror the measured ones.
- Stale docs outside this plan's file list: CLAUDE.md "Current surface" counts (the manifest now lists 59 tool names; two more routes), and `document_tools.py`'s module docstring still says "saving and persistence".
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted per the dispatch instruction (they hold other sessions' uncommitted work); REQUIREMENTS.md untouched by this plan.

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist: `e810b9f`, `c5a8cde`, `95c4e99`, `eee6d86` (`git log --oneline 627579c..HEAD`); `git rev-list --count 627579c1a8ab54e32c703405a1d7f575dd40175b..HEAD` was 4; no tracked file deleted by any of them.
- Files exist: `revit_mcp/documents.py`, `tools/document_tools.py`, `tests/unit/test_document_contracts.py`, `tests/unit/tool_manifest.txt` (59 lines; contains `read_document_summary` and `read_document_levels` once each).
- `uv run pytest tests/unit -q`: 1205 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.422`.
