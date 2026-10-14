---
phase: 01-serialization-and-configurable-addressing
plan: 07
subsystem: docs
tags: [serialization, docs, d27-b, a5-a, revit-port, doc-pins]

requires:
  - phase: 01-serialization-and-configurable-addressing
    provides: "01-06 UNLOCKED_GET and the single _serialized lock path; 01-08 backlog item 999.1 (d27-c) and CONTEXT D-28..D-31; 01-04 bench verdicts"
provides:
  - "bridge.py module docstring: Scope, Lock coverage, Why the lock exists, Residual, Time budget, Failure wording, Target"
  - "CLAUDE.md: bridge.py layout, REVIT_PORT setting, serialization bullet with the UNLOCKED_GET rule, 48885 start-order evidence"
  - "README.md Configuration and Serialization scope sections; deploy/README.md REVIT_PORT deployment knob; deploy/USER-GUIDE.md honest two-Revit text in Russian"
  - "tests/unit/test_serialization_scope_docs.py: eight doc-pin tests for the three load-bearing sentences, the Russian sentence, the over-claim list and the no-two-entry rule"
affects: [phase-2 per-call addressing, verify-work, ship gate]

plan_head_before: d714d16c352949d625fb606e8ff8221777db2947
actuals:
  tokens: 14000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Load-bearing doc sentences pinned verbatim by a unit test and kept on one line in every doc so a wrap cannot break the match"
    - "Case-sensitive whole-token regex scan to keep a two-entry example out of user docs"

key-files:
  created:
    - tests/unit/test_serialization_scope_docs.py
  modified:
    - bridge.py
    - CLAUDE.md
    - README.md
    - deploy/README.md
    - deploy/USER-GUIDE.md
    - tests/unit/test_format_response.py

key-decisions:
  - "Docs state the lock as harm reduction for this one process, never as a guarantee or access control; the cross-process limit is stated until d27-c (backlog 999.1) lands, in Russian for engineers"
  - "Simultaneous Revit launch is documented as a possible collision, not a measured result (01-04 Step 8 was not performed)"

requirements-completed: [SER-05, SER-02, IDENT-05]

coverage:
  - id: D1
    description: "bridge.py docstring, CLAUDE.md and README.md carry the three pinned sentences; bridge.py docstring records the 01-04 verdicts, the residual and the /model_info/ rationale; bridge.py code unchanged"
    requirement: "SER-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_serialization_scope_docs.py#test_serialization_scope_pinned_in_bridge_docstring"
        status: pass
      - kind: unit
        ref: "tests/unit/test_serialization_scope_docs.py#test_serialization_scope_pinned_in_claude_md"
        status: pass
      - kind: unit
        ref: "tests/unit/test_serialization_scope_docs.py#test_serialization_scope_readme_documents_port_and_scope"
        status: pass
      - kind: unit
        ref: "tests/unit/test_serialization_scope_docs.py#test_serialization_scope_docstring_has_no_transport_markers"
        status: pass
    human_judgment: false
  - id: D2
    description: "No over-claim phrase in any of the five docs; no revit-a / revit-b two-entry example; no REVIT_PORT JSON key in USER-GUIDE"
    requirement: "SER-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_serialization_scope_docs.py#test_serialization_scope_no_overclaims"
        status: pass
      - kind: unit
        ref: "tests/unit/test_serialization_scope_docs.py#test_serialization_scope_no_two_entry_user_docs"
        status: pass
    human_judgment: false
  - id: D3
    description: "deploy/README.md names bridge.py and REVIT_PORT as a deployment knob; USER-GUIDE replaces the stale two-Revit statements with the 48884/48885 start-order text and the Russian cross-session warning"
    requirement: "IDENT-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_serialization_scope_docs.py#test_serialization_scope_deploy_readme_names_bridge_and_port"
        status: pass
      - kind: unit
        ref: "tests/unit/test_serialization_scope_docs.py#test_serialization_scope_user_guide_single_entry_and_honest"
        status: pass
    human_judgment: false
  - id: D4
    description: "A simultaneous launch of two Revit instances is run live and the ports each PID received are recorded, confirming or correcting the docs' wording that both can land on 48884"
    verification: []
    human_judgment: true
    rationale: "Needs a live workstation with two Revit launches; 01-04 Step 8 was not performed and this plan is documentation only. Docs call it a possible collision, not a measured result"
  - id: D5
    description: "A differently worded Russian over-claim in USER-GUIDE is not machine-detected"
    verification: []
    human_judgment: true
    rationale: "The over-claim list is English; review of the Russian text relies on a human reader (flagged assumption for SER-05)"

duration: 3 min
completed: 2026-10-14
status: complete
---

# Phase 1 Plan 07: Honest Scope Docs Summary

**The scope of serialization (process-local lock, only `/status/` unqueued, cross-wiring between sessions until d27-c) is now stated identically in the bridge.py docstring, CLAUDE.md and README, in Russian for engineers, and pinned by eight doc tests; `REVIT_PORT` is documented as a deployment setting and no user doc shows a two-entry setup.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-10-14T08:18:08Z
- **Completed:** 2026-10-14T08:21:26Z
- **Tasks:** 2 (tracer, then docs expansion), 4 commits (RED/GREEN per task)
- **Files modified:** 7 (1 created)

## Accomplishments

- `bridge.py` module docstring rewritten for a developer with the three pinned sentences, the not-covered list (another MCP server process, curl, `/execute_code/`), the 01-04 rationale (2026-10-07, pyRevit 6.5.3, Revit 2024.3.30, `cross-wired-mutation`, `cross-wired-read`, twice, `/status/` unaffected), why `/model_info/` stays locked, the post-timeout residual, the time budget, failure wording, and the `REVIT_PORT` target rules. It points at backlog item 999.1. Code is unchanged (AST comparison against `HEAD` printed `BRIDGE_CODE_UNCHANGED`).
- `CLAUDE.md`: `bridge.py` in the Two-Runtime table, diagram and prose; the old "port 48884 is hardcoded" bullet replaced by the `REVIT_HOST` / `REVIT_PORT` bullet (read once, exit 2 on invalid, deployment setting, one shared `revit` entry); the 30 s timeout bullet replaced by the queue-wait worst case of about twice the timeout; a serialization bullet with the three sentences, the residual and the `UNLOCKED_GET` rule; the two-instance bullet extended with the 48885 bench result and the pyRevit port-registration mechanism.
- `README.md` gained "Configuration" and "Serialization scope"; `deploy/README.md` names `bridge.py`, lists it in the `app\` layout, and carries a `REVIT_PORT` deployment note plus the cross-process sentence; `deploy/USER-GUIDE.md` troubleshooting row and the port paragraph are rewritten (first Revit gets 48884, a second started afterwards gets 48885 and is not reached, a simultaneous start may collide, not measured) and a new paragraph holds the Russian cross-session sentence.
- `tests/unit/test_serialization_scope_docs.py`: eight `test_serialization_scope_*` tests, including a guard that the bridge docstring does not copy the three source markers other tests slice on.

## Task Commits

1. **Task 1: end-to-end scope sentences (tracer, TDD)**
   - RED `1311697` (test): 2 of 4 failed (bridge docstring and CLAUDE.md pins); the marker and over-claim tests pass vacuously and guard the change.
   - GREEN `8302635` (docs): bridge.py docstring, CLAUDE.md, one comment in `tests/unit/test_format_response.py`.
2. **Task 2: user and deployment docs (TDD)**
   - RED `27f99f2` (test): 3 of 8 failed (README, deploy README, USER-GUIDE); the over-claim and two-entry scans already held.
   - GREEN `7892023` (docs): README.md, deploy/README.md, deploy/USER-GUIDE.md.

**Plan metadata:** committed separately (docs: complete plan).

Tracer gate: Task 1's `<verify>` re-ran green (full suite, bridge code unchanged, one-line diff in `test_format_response.py`) before Task 2 started.

## Deviations from Plan

None - plan executed exactly as written. Two small notes: the pinned sentences must sit on one line in each doc (a hard wrap broke the substring match twice during GREEN and was fixed by re-flowing, not by changing the test), and CLAUDE.md also gained a short "wording note" bullet about not-sent versus outcome-unknown failures, which is additive to what the plan listed.

**Total deviations:** 0

## Issues Encountered

- `git commit` printed `failed to delete '.git/worktrees/hot-cirrus': Permission denied` and LF-to-CRLF warnings; housekeeping noise, all commits exist.
- Out-of-scope observation, not changed: README.md Architecture table still says the Revit half runs IronPython 2.7 (CLAUDE.md says IronPython 3). Left alone as pre-existing and outside this plan's files-of-concern.

## Known Stubs

None.

## Threat Flags

None - documentation and a doc test only; no new endpoint, auth path or file access.

## Verification

- `uv run pytest tests/unit -k serialization_scope -q`: 8 passed.
- `uv run pytest tests/unit -q`: 416 passed, 3 skipped.
- `uv run python tests/test_init_latency.py`: INIT_LATENCY_S=0.738 (below 2.0).
- `git status --porcelain -- deploy/configure_hermes.py bridge.py tools revit_mcp main.py`: empty after the tasks.
- `git diff --numstat -- tests/unit/test_format_response.py` before the Task 1 commit: 1 added, 1 deleted.

## Next Phase Readiness

Backstop items for human verification: a live simultaneous launch of two Revit instances (D4), and a Russian-language read-through of USER-GUIDE for over-claims (D5). pyRevit 6.5.5 and a `/model_info/` overlap measurement remain unmeasured, as stated in the docs.

## Self-Check: PASSED

All four task commits (1311697, 8302635, 27f99f2, 7892023) and all created or modified files exist on disk.
