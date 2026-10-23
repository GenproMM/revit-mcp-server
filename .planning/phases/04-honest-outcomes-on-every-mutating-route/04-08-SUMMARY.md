---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 08
subsystem: testing
tags: [conventions, static-check, ast, commit_and_report, finalize_outcome, scaffolds, contrib-kit]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "all 26 bare Commit() sites migrated to commit_and_report (04-01..04-07) and the outcome helpers"
provides:
  - "check_commit_goes_through_report and check_swallower_is_kept in scripts/conventions.py, wired into check_route_module (repository suite, scripts/intake_package.py and the contributor kit all run them)"
  - "Tree-wide parametrised tests over every revit_mcp/ file (utils.py included) plus 40 detector tests proven on known-bad and known-good sources"
  - "new_tool.py scaffold, contributor-kit scaffold, CONTRIBUTING.md and CLAUDE.md teach the swallower / commit_and_report / finalize_outcome / outcome-status shape"
affects: [04-09, phase-06-audit-log, contributor-kit-release]

plan_head_before: 5ee9428f50e058208c75ff34b16cc17f4228273a
actuals:
  tokens: 4700   # chars/4 over the +/- lines of the realized diff (18926 chars); the plan estimated 65000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Static rule in scripts/conventions.py: stdlib-only AST check, one message per violation kind listing sorted line numbers, same shape as check_element_id"
    - "The one legitimate Commit() is exempted structurally (module-level FunctionDef commit_and_report in a file labelled revit_mcp/utils.py), not by skipping the file in the test"

key-files:
  created: []
  modified:
    - scripts/conventions.py
    - tests/unit/test_conventions.py
    - scripts/new_tool.py
    - contrib-kit/revitmcp_kit.py
    - CONTRIBUTING.md
    - CLAUDE.md

key-decisions:
  - "The utils.py exemption applies only to a module-level def commit_and_report, so a method of the same name on a class in utils.py is still caught (stricter than the plan's FunctionDef wording)"
  - "check_swallower_is_kept also catches the keyword form commit_and_report(t, swallower=None) and skips a call with *args, whose arguments are not statically known"
  - "Task 2 was committed through a temporary index built from HEAD with the working-tree blobs, the user's status-URL hunk in scripts/new_tool.py reverted in the blob only, so it stayed uncommitted"

patterns-established:
  - "Detector tests assert the exact line list in the message, so a checker that stops reporting positions fails the suite"

requirements-completed: [TRUTH-01]

coverage:
  - id: D1
    description: "A bare Commit(), a family-document Commit comparison and a bound Commit reference in revit_mcp/ or a contributed route fail the conventions check; commit_and_report(t, swallower), comments and string mentions pass; the utils.py exemption holds only inside commit_and_report"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_conventions.py -k 'commit_detector'"
        status: pass
    human_judgment: false
  - id: D2
    description: "A discarded suppress_warnings(...) and a commit_and_report without a non-None second argument are caught, in positional and keyword form"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_conventions.py -k 'swallower_detector'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every one of the 26 migrated sites holds: no bare Commit and no discarded swallower in any revit_mcp/ file, utils.py included"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_conventions.py#test_commits_go_through_commit_and_report"
        status: pass
      - kind: unit
        ref: "tests/unit/test_conventions.py#test_suppress_warnings_result_is_kept"
        status: pass
    human_judgment: false
  - id: D4
    description: "Both checks run inside check_route_module, so intake and the kit reject a contributed route that commits on its own"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_conventions.py#test_route_module_check_reports_the_new_violations_with_the_old"
        status: pass
    human_judgment: false
  - id: D5
    description: "The generated POST scaffold (new_tool.py and the Russian kit template) passes the conventions and the documentation describes the new transaction shape"
    requirement: TRUTH-01
    verification:
      - kind: command
        ref: "SCAFFOLD one-liner from 04-08-PLAN.md Task 2 prints 'SCAFFOLD clean'; the kit's `new` output also checks clean"
        status: pass
    human_judgment: true
    rationale: "Whether the rewritten CLAUDE.md, CONTRIBUTING.md and scaffold comments read clearly to a contributor is a judgment no test asserts"

duration: 6 min
completed: 2026-10-23
---

# Phase 4 Plan 08: D-02 static rule and scaffold/docs update Summary

**Two stdlib-only AST checks (no `Commit` outside `commit_and_report`, no discarded swallower) now guard every `revit_mcp/` file and every contributed route, and the scaffolds, `CONTRIBUTING.md` and `CLAUDE.md` teach the honest-outcome transaction shape.**

## Performance

- **Duration:** about 6 min (start 18:41Z, end 18:47Z)
- **Tasks:** 2 of 2
- **Files modified:** 6 (all in `files_modified`; none created)

## Accomplishments

- **Task 1:** `check_commit_goes_through_report` flags every `ast.Attribute` named `Commit` (call, comparison or bound reference) except inside the module-level `commit_and_report` of a file labelled `revit_mcp/utils.py`. `check_swallower_is_kept` flags a bare `suppress_warnings(t)` statement and a `commit_and_report` call whose second argument is missing or `None`. Both are in `check_route_module` after `check_request_parsing`. The tree-wide tests found nothing: D-01's 26 sites are proven migrated (`D02_TREE clean`).
- **Task 2:** both scaffolds show `swallower = suppress_warnings(t)`, per-item `succeeded`/`failed`, `commit_and_report(t, swallower)`, `finalize_outcome(...)` and the four statuses; their non-GET import line gains `commit_and_report, finalize_outcome`. `CONTRIBUTING.md` and `CLAUDE.md` state the swallower rule, the single commit path, the `outcome` keys and statuses, that validation refusals carry no outcome, that `partial` is deliberately not an error (own PARTIAL SUCCESS branch in `format_response`), and that bulk routes now list skipped items in `outcome.failed` while `delete_elements` and `transform_elements` stay all-or-nothing.
- Suite: 5186 passed, 3 skipped (baseline before this plan 5016 + 170 new). `tests/unit/tool_manifest.txt` unchanged. The three pinned serialization-scope sentences in `CLAUDE.md` untouched (`test_serialization_scope_docs.py` green).

## Task Commits

1. **Task 1: D-02 checks, detector tests, tree-wide tests** - `50c307b` (feat)
2. **Task 2: scaffolds and docs** - `5cdcf54` (docs)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED and GREEN committed together**
- **Found during:** Task 1
- **Issue:** the plan requires `uv run pytest tests/unit` green before every commit, which a standalone RED commit would violate (same resolution as 04-01). RED was observed failing first (85 failures, `AttributeError` for the missing checkers), then made green before the single commit.
- **Commit:** 50c307b

**2. [Plan wording, stricter] utils.py exemption limited to a module-level function**
- The plan exempts "the FunctionDef named `commit_and_report`". The checker exempts only a function directly in the module body, so a same-named method elsewhere in `utils.py` is still caught (covered by `test_commit_detector_exemption_does_not_cover_a_nested_other_label`).

**3. [Rule 2 - Missing critical] Keyword form of the swallower argument**
- `commit_and_report(t, swallower=None)` would have passed a positional-only check; it is now caught, and `swallower=s` passes. A call with `*args` is skipped because its arguments are not statically known.

**Total deviations:** 3 (1 blocking-process, 1 stricter reading, 1 added coverage). **Impact:** none on the contract; the checks are slightly stricter than specified.

## Issues Encountered

- `git commit` prints `failed to delete '.git/worktrees/hot-cirrus': Permission denied`; both commits landed (verified with `git log`).
- Task 2 touched `scripts/new_tool.py`, which carries the user's uncommitted status-URL hunk. Commit 5cdcf54 was built from a temporary index (HEAD plus the working-tree blobs, with only that one print line reverted in the `new_tool.py` blob). Afterwards `git reset -q` on the four paths, `git diff -- scripts/new_tool.py` shows only the status-URL hunk, and the previously staged phase-07 and Obsidian entries are still staged exactly as before.
- `graphify update .` was not run (it rewrites `graphify-out/`, which holds another session's uncommitted changes).
- `REQUIREMENTS.md` was not touched; TRUTH-01 completion is left to the orchestrator.

## Release note (T-04-30)

**The contributor kit zip must be rebuilt with `scripts/build_contrib_kit.py` at release.** The kit ships a copy of `scripts/conventions.py` made at build time, so an already-built zip still carries the old checker and would pass a contributed route that commits on its own. `contrib-kit/conventions.py` was deliberately not edited by hand. Rebuilding and publishing the zip is a release step the user runs.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or trust-boundary surface; the change adds checks that reject code and edits documentation and scaffold text. T-04-29 and T-04-31 mitigated; T-04-30 transferred as planned.

## Next Phase Readiness

Ready for 04-09 (tool docstrings). The D-02 rule now holds for the whole tree, so any later route work that reintroduces a bare commit or drops the swallower fails the suite at the introducing commit.

## Self-Check: PASSED

- Files modified exist and are committed: scripts/conventions.py, tests/unit/test_conventions.py, scripts/new_tool.py, contrib-kit/revitmcp_kit.py, CONTRIBUTING.md, CLAUDE.md.
- Commits found: 50c307b, 5cdcf54 (`git log --grep "04-08"`); `git show --stat 5cdcf54` lists exactly the four Task 2 paths.
- Acceptance criteria re-run: D02_TREE prints `clean`; known-bad one-liner prints `True`; `-k "commit_detector or swallower_detector or commits_go_through or result_is_kept"` 84 passed (>= 70); SCAFFOLD prints `clean`; `grep -c commit_and_report scripts/new_tool.py` 4, `finalize_outcome` in the kit 4, in CLAUDE.md 1, in CONTRIBUTING.md 2, `PARTIAL SUCCESS` in CLAUDE.md 1; `git diff -- scripts/new_tool.py` shows only the status-URL hunk; full suite 5186 passed, 3 skipped.
