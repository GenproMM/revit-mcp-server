---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '19'
subsystem: api
tags: [process-lifecycle, discovery, listener-collision, start_revit, no-duplicate-launch, mcp-tool]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-03 revit_get.discover_targets facade (usable incarnations, unusable collisions naming every PID, named inventory-unavailable status) and the per-incarnation selected GET /status/
provides:
  - "get_revit_process_status classifying none / one_ready / one_no_document / many / collision / inventory_failure / discovery_failed / discovery_unavailable / unresolved_listeners / status_unavailable from shared discovery"
  - "start_revit launching only on proven absence (inventory read, nothing listening); any usable Revit means already running; every inconclusive discovery refuses with PIDs and starts nothing"
  - "Post-launch report from re-discovery: observed process(es) or an explicit unknown, never a predicted port"
  - "tests/unit/test_process_tools.py: 33 offline tests through the real registrar with a fake discovery facade and a fake Popen"
affects: [02-18, 02-16]

actuals:
  tokens: 11300   # chars/4 over `git diff 36ea8fe..HEAD` (45022 chars) at the last task commit; excludes this SUMMARY
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count 36ea8fe..HEAD before this SUMMARY commit (#3968)
plan_head_before: 36ea8fe20eab86f8092b504d19afb388c966149a

tech-stack:
  added: []
  patterns:
    - "Lifecycle tools reach discovery only through the facade attribute on the injected revit_get; a missing facade is a visible state, never proof Revit is closed"
    - "One _survey() classification shared by the status and launch tools: only kind == none is proven absence"
    - "Fake revit_get that raises on any unselected /status/ request makes the 'no unselected status' rule a test failure, not a convention"

key-files:
  created:
    - tests/unit/test_process_tools.py
  modified:
    - tools/process_tools.py

key-decisions:
  - "Only a read inventory with no listener at all is 'none'. A collision, an unanswered or mismatched listener, an inventory failure, a discovery exception and a missing facade each get their own state and none of them permits a launch."
  - "A usable Revit anywhere means start_revit starts nothing, even when a collision exists beside it (a proven Revit is already running)."
  - "Selected /status/ is asked only for the single validated incarnation and only by get_revit_process_status; start_revit decides from discovery's own document_open, so there is no extra status call to mis-select."
  - "After launch the tool never says which port the process holds. It re-discovers each poll; a collision appearing mid-wait stops the wait with outcome unknown and still launches no second process; an inventory blip or unanswered listener keeps polling."

patterns-established:
  - "Refusals to launch name the PIDs they have and say it is not proof Revit is closed"

requirements-completed: []  # Deliberately empty (02-02/02-03 precedent). This plan guards the local lifecycle offline; AMBIG-01/02/03 and IDENT-01 still need the 02-18 live observation (production collision, multi-process discovery) and the document tools. Nothing is claimed beyond the offline acceptance below.

coverage:
  - id: D1
    description: "get_revit_process_status renders a distinct state for none, one ready, one no-document 503, two usable, a two-PID collision (both PIDs named), inventory failure, discovery exception and missing facade; no row asks /status/ of an unselected incarnation; installed-version reporting preserved"
    requirement: "AMBIG-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_process_tools.py#test_status_every_condition_renders_a_distinct_state"
        status: pass
      - kind: unit
        ref: "tests/unit/test_process_tools.py#test_status_two_pid_collision_names_both_pids_and_is_not_down"
        status: pass
    human_judgment: false
  - id: D2
    description: "start_revit records zero Popen calls for collision, initializing listener, identity mismatch, missing facade, inventory failure, discovery exception and an already running process (one or several); exactly one for proven absence"
    requirement: "AMBIG-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_process_tools.py#test_start_revit_never_launches_when_discovery_is_inconclusive"
        status: pass
      - kind: unit
        ref: "tests/unit/test_process_tools.py#test_start_revit_proven_absence_launches_exactly_once_and_reports_observed"
        status: pass
    human_judgment: false
  - id: D3
    description: "Post-launch report names only a re-discovered incarnation or an explicit unknown; a collision after launch launches no second process; the docstring no longer promises one entry per REVIT_PORT"
    requirement: "AMBIG-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_process_tools.py#test_start_revit_timeout_reports_unknown_identity_never_a_port"
        status: pass
      - kind: unit
        ref: "tests/unit/test_process_tools.py#test_start_revit_collision_after_launch_stops_waiting_and_launches_no_second"
        status: pass
    human_judgment: false
  - id: D4
    description: "Behavior of these tools on a real workstation with Revit, a real two-listener collision or a real launch"
    requirement: "AMBIG-01"
    verification:
      - kind: manual_procedural
        ref: "not run - 02-18 live observation; this plan was offline by instruction and started no Revit"
        status: unknown
    human_judgment: true
    rationale: "Fakes prove the decision logic; the real netstat/handshake/Popen path was deliberately not exercised."

duration: "~20 min"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 19: Process lifecycle under multi-target discovery Summary

**`get_revit_process_status` and `start_revit` now decide from the 02-03 discovery facade instead of one unselected fixed-port `/status/`: a listener collision, unanswered listener or unavailable inventory is reported as such and never launches a Revit, only proven absence does, and the post-launch report names only a re-discovered process or an explicit unknown.**

## Performance

- **Tasks:** 2 of 2 (both `tdd="true"`: RED then GREEN each)
- **Files:** 1 created (`tests/unit/test_process_tools.py`), 1 modified (`tools/process_tools.py`)
- **Live contact:** none. No `mcp__revit__*` tool was called, Revit was not started or stopped, `start_revit` was never run; every Popen in the tests is a recorder.

## Accomplishments

- RED reproduced the 02-03 finding: the old `_bridge_state` issued an unselected `/status/`, which the fake rejects, and read any non-HTTP refusal as "down" (the launch tests failed for exactly that reason before the fix).
- New `_survey()` classifies discovery once for both tools: `none` (inventory read, nothing listening) is the only proof of absence; `collision`, `unresolved_listeners`, `inventory_failure`, `discovery_failed`, `discovery_unavailable` are inconclusive; `one` / `many` are usable incarnations.
- `get_revit_process_status`: distinct `process_state` per condition, `processes` and `ambiguous_listeners` rows (collision names every PID), `revit_running` is `true`, `false` (only for `none`) or `"unknown"`, installed versions preserved, a `str` via `format_response`. The selected `/status/` is requested only for one validated incarnation (HTTP 503 stays running-without-document); with several processes or a collision no status is requested at all.
- `start_revit`: gates before launch. Any usable Revit returns `already_running` without launching; any inconclusive discovery returns an error block naming PIDs and saying it is not proof Revit is closed. After a launch it re-discovers: success lists the observed PID/port/version, a collision stops the wait with `outcome: unknown`, an inventory blip keeps polling, and a timeout reports `observed_processes: unknown`.
- Docstrings rewritten for a model: the one-entry-one-`REVIT_PORT` paragraph is gone; they state when it launches, what is observed, and that targeting is per call. `_bridge_state` was removed.
- `subprocess.Popen` invocation (detached, stdio on DEVNULL, `close_fds`) is unchanged and asserted by the tests.

## Task Commits

1. **Task 1 RED:** `4c92c23` (test) - 14 failing status tests
2. **Task 1 GREEN:** `5f68eaa` (feat) - `_survey` and the status tool
3. **Task 2 RED:** `348fc1c` (test) - 19 failing launch tests (fake Popen)
4. **Task 2 GREEN:** `d0157fd` (feat) - launch gate, post-launch re-discovery, docstring

## Verification (real numbers)

- Task 1 verify `uv run pytest tests/unit/test_process_tools.py tests/unit/test_registration.py -q`: **25 passed** (at the Task 1 commit).
- Task 2 verify `uv run pytest tests/unit/test_process_tools.py tests/unit/test_registration.py tests/unit/test_target_resolution.py -q`: **109 passed**.
- Plan verification `uv run pytest tests/unit -q`: **1056 passed, 3 skipped** (baseline 1023 passed, 3 skipped; +33 new tests).
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.415** (<2.0).
- Not run, not claimed: live multi-target and production collision behaviour (02-18, needs authorization).

## Deviations from Plan

None - plan executed exactly as written. Notes that are not deviations:

- `tests/unit/test_process_tools.py` did not exist; it is created by this plan (it is in `files_modified`).
- The plan names the 02-03 facade `revit_get.discover_targets`; it is used exactly as attached, with no bridge import and the four-argument registrar untouched.
- A usable Revit beside a collision is treated as "already running" for launching (nothing is started), while the status tool reports the state as `collision`. One initial test row asserted the refusal text for that combination and was corrected to the behavior the plan's `<behavior>` actually requires (never launch); no assertion about Popen was weakened.

## Issues Encountered / Surprises

- Every commit prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` from git's post-commit housekeeping (a stale linked-worktree entry on this machine). Commits succeeded; this is unrelated to the plan and was left alone.
- `tools/process_tools.py` was CRLF in the working copy (LF in the index). It was rewritten with LF; git normalizes it (autocrlf warning only), so the diff is content-only.
- Docs still stale and outside this plan: CLAUDE.md "Known sharp edges" Routes target bullet and `deploy/`/README text on `REVIT_PORT` routing; `get_revit_status` still appends `MCP target: host:port`. 02-16 owns status rendering.
- `get_revit_process_status` costs one discovery (one netstat plus handshakes) and, for a single process, one extra selected status call; not benchmarked live.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or file access: the tools only consume the existing discovery facade (threats T-02-01 spoofing and T-02-04 denial of service are mitigated as planned: selected status only for one validated incarnation, Popen blocked on collision or inventory failure and covered by the fake-process-factory tests).

## Next Phase Readiness

- 02-18 can observe the real two-listener collision and multi-process discovery against these tools; both are still live gates, not run.
- `requirements-completed` left empty on purpose (see frontmatter).
- `STATE.md` and `ROADMAP.md` were updated through the gsd-tools verbs and left uncommitted by instruction (the tree carries other sessions' edits to both).

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist: `4c92c23`, `5f68eaa`, `348fc1c`, `d0157fd` (`git log --oneline 36ea8fe..HEAD`); `git rev-list --count 36ea8fe..HEAD` was 4; no tracked file was deleted in any of them.
- Files exist: `tests/unit/test_process_tools.py`, `tools/process_tools.py`.
- `uv run pytest tests/unit -q`: 1056 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.415`.

---
*Phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin*
*Completed: 2026-10-22*
