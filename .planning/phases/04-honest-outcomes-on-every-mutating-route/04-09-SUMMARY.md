---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 09
subsystem: testing
tags: [docstrings, api-contract, outcome-status, partial-success, tools, ast]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "outcome statuses on every mutating route (04-01..04-07): partial 200, failed 422, rolled_back 409, and the PARTIAL SUCCESS banner in format_response"
provides:
  - "An Outcome paragraph (variants P, S, E, A) in 27 mutating-tool docstrings across 14 tools/*_tools.py files, stating only the statuses each tool's route can return"
  - "tests/unit/test_outcome_docstrings.py: OUTCOME_CLASSES covers inventory_support.MUTATION_TOOLS exactly (14 P, 7 S, 4 E, 3 A, 3 EXEMPT) with per-class required and forbidden phrases"
affects: [04-11, phase-06-audit-log]

plan_head_before: ebaa1071f9ad910aca21f78ba74a7b5519e9efa9
actuals:
  tokens: 4300   # chars/4 over the +/- lines of the realized diff (17303 chars); the plan estimated 60000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Docstring contract test: parse tools/*_tools.py with ast, index async functions by name, assert required and forbidden phrases per outcome class (no tool module imported)"

key-files:
  created:
    - tests/unit/test_outcome_docstrings.py
  modified:
    - tools/tag_tools.py
    - tools/annotation_tools.py
    - tools/building_tools.py
    - tools/structure_tools.py
    - tools/colors_tools.py
    - tools/detail_tools.py
    - tools/mep_tools.py
    - tools/room_tools.py
    - tools/documentation_tools.py
    - tools/family_tools.py
    - tools/editing_tools.py
    - tools/interop_tools.py
    - tools/view_management_tools.py
    - tools/transform_tools.py

key-decisions:
  - "The classification table of the plan held unchanged: no 04-02..04-07 deviation moved a route between classes (checked against their Deviations sections and the finalize_outcome / classify_outcome code, which makes 422 reachable only when zero items succeed and at least one failed)"
  - "Each test entry carries a one-line reason so a failing assertion names why the phrase is required or banned"

patterns-established:
  - "A tool docstring may promise only a status its route can return; the per-class FORBIDDEN tuple turns an over-promise into a test failure"

requirements-completed: [TRUTH-03, TRUTH-04]

coverage:
  - id: D1
    description: "The 14 class P tools say the reply starts with PARTIAL SUCCESS, a total failure is HTTP 422 (failed) and a rollback is HTTP 409 (rolled_back)"
    requirement: TRUTH-04
    verification:
      - kind: unit
        ref: "tests/unit/test_outcome_docstrings.py (14 class P parametrised cases)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The 7 class S tools state PARTIAL SUCCESS for a failed follow-up step and HTTP 409, and never mention HTTP 422"
    requirement: TRUTH-03
    verification:
      - kind: unit
        ref: "tests/unit/test_outcome_docstrings.py -k 'create_duct or place_family or create_room'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Class E tools state HTTP 422 and 409 without PARTIAL SUCCESS; class A tools state HTTP 409 only; the three EXEMPT tools mention none of the three statuses"
    requirement: TRUTH-04
    verification:
      - kind: unit
        ref: "tests/unit/test_outcome_docstrings.py (E, A and EXEMPT parametrised cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The classification covers exactly the 31 MUTATION_TOOLS; no signature, Args entry or body changed"
    requirement: TRUTH-04
    verification:
      - kind: unit
        ref: "tests/unit/test_outcome_docstrings.py#test_classification_covers_exactly_the_mutation_tools"
        status: pass
      - kind: command
        ref: "uv run pytest tests/unit -q (5218 passed, 3 skipped)"
        status: pass
    human_judgment: false

duration: 20 min
completed: 2026-10-23
---

# Phase 4 Plan 09: Outcome docstrings for the mutation tools Summary

**Every mutating tool's docstring now tells the model how PARTIAL SUCCESS, HTTP 422 (failed) and HTTP 409 (rolled_back) look, limited to the statuses its route can return, pinned by a 32-case contract test over all 31 mutation tools.**

## Accomplishments

- Added one `Outcome:` paragraph immediately before `Args:` in 27 tool docstrings (14 files): P (partial or total failure) for 14 tools, S (created element, follow-up steps can fail) for 7, E (fails without partial) for 4, A (all or nothing) for 2 newly edited (`set_parameter` already stated the 409 and is unchanged). `save_document`, `load_family`, `set_active_view` (no transaction) are untouched.
- Wrote `tests/unit/test_outcome_docstrings.py`: `OUTCOME_CLASSES` (tool to class and reason), `REQUIRED` / `FORBIDDEN` phrase tuples per class, a parametrised test per tool plus a completeness test (32 cases). A tool missing from `tools/` fails instead of being skipped.
- Verified the classification against the implemented routes rather than the plan alone: `classify_outcome` / `finalize_outcome` in `revit_mcp/textutils.py` (422 needs zero succeeded and at least one failed, so a route that puts the created id in `succeeded` can never answer 422), `delete_elements` and `transform_elements` (all requested ids succeed on commit, no failed items), and the 04-02..04-07 SUMMARYs (`create_sheet` taken number and `create_schedule` missing field are partials, `export_document` negative result is a 422, `edit_family` all-failed is a 422, `place_family` property/rotation failures are partials).

## Task Commits

1. **Task 1: batch-tool docstrings (tag, annotation, building, structure, colors)** - `cdd8fdd` (docs)
2. **Task 2: single-element creation docstrings (detail, mep, room, documentation, family)** - `6ba5e80` (docs)
3. **Task 3: remaining docstrings and the contract test** - `c4e8652` (test)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED observed before the Task 3 docstrings, but not committed separately**
- **Found during:** Task 3
- **Issue:** the commit protocol requires `uv run pytest tests/unit` green before every commit, so a standalone RED commit is not allowed (same resolution as 04-01..04-07).
- **Fix:** wrote the test first and saw exactly the six expected failures (create_view, delete_elements, export_ifc, link_file, modify_element, transform_elements), then edited the docstrings and committed test and docstrings together.
- **Commit:** c4e8652

**2. [Rule 3 - Blocking] Mixed line endings in `tools/`**
- **Found during:** Task 1
- **Issue:** the plan assumes uniform files; 11 of the 14 edited files are CRLF in the working tree (annotation, building and colors are LF).
- **Fix:** the edit script (scratchpad, not committed) detects each file's ending and preserves it, so the diffs are insertions only (`git show -U0` shows no added or removed `async def`, `def`, `return` or `data` line).

**Total deviations:** 2 (both blocking-process). **Impact:** none on the shipped contract. No tool moved between classes.

## Issues Encountered

- `git commit` printed `failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit; all three landed (verified with `git log`). Harmless, as the orchestrator warned.
- The first session was cut off after Task 2's edits and before its commit; the work on disk was re-verified (DOCS check and the full unit suite) and committed on resume.
- `graphify update .` was not run: it rewrites `graphify-out/`, which holds another session's uncommitted changes. `REQUIREMENTS.md` was not touched; TRUTH-03 and TRUTH-04 completion is left to the orchestrator.

## Known Stubs

None.

## Threat Flags

None. Text-only docstring changes and a test; no new endpoint, auth path or trust-boundary surface. T-04-32 and T-04-33 are mitigated by the paragraphs and the per-class required/forbidden assertions.

## Next Phase Readiness

04-11 (live gate) can rely on the docstrings describing the shapes it will observe. `uv run pytest tests/unit`: 5218 passed, 3 skipped; `tests/unit/tool_manifest.txt` unchanged.

## Self-Check: PASSED

- `tests/unit/test_outcome_docstrings.py` exists; commits cdd8fdd, 6ba5e80, c4e8652 found in `git log`.
- Task acceptance criteria re-run: Task 1 and 2 DOCS commands print `DOCS ok`; `test_outcome_docstrings.py` 32 passed; `-k "create_duct or place_family or create_room"` 4 passed; Task 3 `git show --stat HEAD` lists only the four tool files and the test.
