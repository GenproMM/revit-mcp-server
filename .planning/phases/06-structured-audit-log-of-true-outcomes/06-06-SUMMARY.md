---
phase: 06-structured-audit-log-of-true-outcomes
plan: 06
subsystem: audit
tags: [audit, live-gate, one-shot, classifier, rollback, two-instance, fake-revit]

requires:
  - phase: 06-structured-audit-log-of-true-outcomes
    provides: schema-1 entries and the roll-forward writer (06-01..06-03), call_id and user_request wrapper (06-04), retention, FakeRevitServer and audit_support (06-05)
  - phase: 04-truthful-outcomes
    provides: the one-shot live script pattern (tests/test_phase4_live_outcomes.py)
provides:
  - tests/test_phase6_live_audit.py (template, rehearse, run-single, run-dual, child, classify; pure classify_single and classify_dual)
  - tests/unit/test_phase6_live_audit.py (193 offline rows, including end-to-end runs through the real main.py tools against the Machine fake)
  - the human-run live-gate instrument that plan 06-07 runs; nothing was run against a live Revit
affects: [06-07]

plan_head_before: cede82f76672749f5f9224c66cf62f00e0c3d042
actuals:
  tokens: 36000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "One-shot live script: posts_sent counted before each call, record written with open('x'), refusals before any request, preflight with POSTS_SENT=0 may be rerun"
    - "Classifiers find a step's entry by the call_id on the reply's Audit line, never by order; reasons carry field values but never the secret or a process id"
    - "A second server process is faked offline by a child stand-in that leaves a canned record and audit file, because one process has one audit writer"

key-files:
  created:
    - tests/test_phase6_live_audit.py
    - tests/unit/test_phase6_live_audit.py
  modified: []

key-decisions:
  - "Writes call the function FastMCP registered for the tool (main.mcp._tool_manager.get_tool(name).fn, the audit wrapper) with ctx=None instead of main.mcp.call_tool, because call_tool outside an MCP request makes execute_revit_code raise before anything is sent"
  - "set_parameter reports the parameter name in outcome.succeeded, so w3 is judged as succeeded == [parameter] plus args.element_id == the wall id (the plan said wall id in succeeded)"
  - "A preflight stop prints only the stop reason, not the classifier's list of missing steps; a stop with POSTS_SENT of 1 or more prints both"
  - "Reasons refer to audit files by role (parent/child), never by name, so no PID reaches VALIDATION.md through a reason"
  - "run-dual: a missing, unreadable or timed-out child record sets posts_sent to unknown (null) and the report says to treat the one-shot gate as consumed"

patterns-established:
  - "Counting the secret: SECRET_OCCURRENCES counts the whole secret, its JSON-escaped form and every 16-character run in audit lines, replies and the saved record; any non-zero count is a stop"

requirements-completed: [AUDIT-01, AUDIT-03, AUDIT-06, AUDIT-08]

coverage:
  - id: D1
    description: "classify_single judges ROADMAP criteria 1, 2 and 7 from a saved record and the audit files: rolled_back with HTTP 409 and the code hash, partial with item 999999999 and its reason, a successful set_parameter entry with document token/title/path, the verified Revit PID, the sent user_request, call_id equal to the reply's Audit line id, no secret in any file"
    requirement: "AUDIT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase6_live_audit.py (the canned single record plus 34 single perturbation rows)"
        status: pass
    human_judgment: false
  - id: D2
    description: "classify_dual judges ROADMAP criterion 5: two PID-named server-process files, whole lines with no CRLF, each process wrote exactly the entries it issued, each entry names the Revit its call addressed, no secret"
    requirement: "AUDIT-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase6_live_audit.py (the canned dual record plus 17 dual perturbation rows)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The one-shot refusals and counting: --out or --audit-dir inside the repository, existing --out, non-empty --audit-dir, bad ids, blank names, a missing rollback file, --count outside 1..20 are refused before any request; POSTS_SENT is counted before each call; a preflight stop sends nothing and allows a rerun to a fresh --out"
    requirement: "AUDIT-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase6_live_audit.py (refusal rows, preflight fault rows, tool_step counting rows)"
        status: pass
      - kind: command
        ref: "uv run python tests/test_phase6_live_audit.py run-single ... --audit-dir . --out tests/record.json (exit 2, nothing written)"
        status: pass
    human_judgment: false
  - id: D4
    description: "run-single, rehearse and run-dual drive the real main.py tools, the real bridge and the real audit writer end to end against the Machine fake and judge their own output as PHASE6_AUDIT_OK"
    requirement: "AUDIT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase6_live_audit.py#test_run_single_end_to_end_through_the_audited_tools_is_ok"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase6_live_audit.py#test_run_dual_end_to_end_with_a_second_server_process_is_ok"
        status: pass
    human_judgment: false
  - id: D5
    description: "Whether the rollback trigger code, the two-instance bench and the real Revit replies match what the classifiers expect (research assumption A3, Pitfall 18)"
    requirement: "AUDIT-03"
    verification: []
    human_judgment: true
    rationale: "Only a real Revit rolls a transaction back and only a human can run the one-shot gate; 06-07 runs it. The offline Machine fake proves the classifiers and the runner, not Revit's behaviour"

duration: 20min
completed: 2026-10-25
status: complete
---

# Phase 6 Plan 06: The human-run live audit gate Summary

**A one-shot, machine-judged live gate (rehearse, run-single, run-dual with a concurrent child server process, classify) that sends each write once through the audited tools into a scratch audit directory and judges ROADMAP criteria 1, 2, 5 and 7 from the record and the audit files alone; built and proven offline, not run live.**

## Performance

- **Duration:** about 20 min (2026-10-25T10:44:09Z to 11:04:10Z)
- **Tasks:** 2 (both TDD: RED then GREEN)
- **Files:** 2 created
- **Commits:** 4 (test, feat, test, feat)

## Accomplishments

- `classify_single` and `classify_dual` are pure and never raise: any internal error is a stop whose text has the secret replaced. A step's entry is found by the `call_id` on its reply's `Audit:` line; a call_id that matches no entry, two entries, a different call_id on a near-identical entry, a CRLF, a torn line, a non-object line, a missing secret and a secret leak are each a named stop.
- `secret_occurrences` counts the whole secret, its JSON-escaped form and every 16-character run; the report prints only `SECRET_OCCURRENCES=<n>`. Reasons carry field values but never the secret and never a process id (files are named by role).
- `refusal()` is one function for all commands, decided before the bridge or a tool is touched; the runner sets `REVIT_MCP_AUDIT_DIR` and `REVIT_PORT` before the first bridge import.
- `run-single` preflight: exactly one usable Revit and no port collision, `/status/` identity, one OS listener owner, one open document, the wall parameter present, text and writable, the tag element readable. Then w1 (`execute_revit_code` with the operator's rehearsed code), w2 (`tag_elements` with `[tag id, 999999999]`), w3 (`set_parameter`), each once, in order, with `posts_sent` counted before each call even when the call raises.
- `run-dual` preflight: exactly two usable Revit instances, one document each, the parameter writable on each wall (lowest port gets `--wall-a`). The runner starts `child` before it writes, issues K calls per Revit with `asyncio.gather`, waits for the child, merges its record, reads every audit file and classifies.
- `rehearse` sends one `execute_revit_code` call and reports `REHEARSAL_ROLLED_BACK`, `REHEARSAL_COMMITTED` or `REHEARSAL_OTHER` from the audit entry of that call.
- 193 unit rows. They include real end-to-end runs of `rehearse`, `run-single` and `run-dual` through the real `main.py` tools, the real bridge and the real audit writer against the `Machine` fake, so the whole path ends in `PHASE6_AUDIT_OK` offline.
- Full suite `uv run pytest tests/unit`: 6297 passed, 3 skipped (the 3 skips are pre-existing), 0 failed. Baseline after 06-05 was 6104 passed, so this plan added 193.

## Task Commits

1. **Task 1 RED:** `6f0d5b0` test(06-06): failing rows for the classifiers and refusals (with a stub-only script)
2. **Task 1 GREEN:** `a7cb259` feat(06-06): pure classifiers and refusals (141 passed)
3. **Task 2 RED:** `c170305` test(06-06): failing rows for the runner (52 failed)
4. **Task 2 GREEN:** `5fef679` feat(06-06): rehearse, run-single, run-dual and child (193 passed)

**Plan metadata:** committed separately as `docs(06-06)` (SUMMARY, STATE, ROADMAP, REQUIREMENTS).

## Files Created/Modified

- `tests/test_phase6_live_audit.py` - the live-gate script; module docstring holds the commands, tokens, exit codes, one-shot rule, refusals and the operator procedure
- `tests/unit/test_phase6_live_audit.py` - the offline twin

## Decisions Made

See `key-decisions` above. The two that change what 06-07 sees: writes use the registered audit wrapper with `ctx=None` (not `main.mcp.call_tool`), and w3 is judged on `succeeded == [parameter]` plus `args.element_id`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `main.mcp.call_tool` cannot drive `execute_revit_code` outside a request**
- **Found during:** Task 2 (a probe of the production path before writing the runner)
- **Issue:** The plan has every write go through `main.mcp.call_tool`. Outside a real MCP request FastMCP hands the tool a Context that refuses use, and `execute_revit_code` calls `ctx.info(...)`, so the call raised `ToolError: Context is not available outside of a request` and sent nothing. The rollback step and the rehearsal could never have reached Revit, and the one-shot gate would have been spent on a runner bug. (`set_parameter` worked, which is why it is easy to miss.) The existing unit tests already work around this by calling `tool.fn(ctx=None, ...)`.
- **Fix:** `_tool_callable` resolves the function FastMCP registered for the tool, which is the audit wrapper itself (call state, `user_request`, the real tool, the production bridge, the audit writer), and calls it with `ctx=None`. Resolution happens before `posts_sent` is counted, so a lookup failure never counts as a sent POST. No fallback to `call_tool`: a retry after a raised tool could send a write twice.
- **Files modified:** tests/test_phase6_live_audit.py
- **Verification:** the end-to-end rows run all three write tools and the rehearsal through it and end in `PHASE6_AUDIT_OK` / `REHEARSAL_ROLLED_BACK`
- **Committed in:** `5fef679`

**2. [Rule 1 - Bug] The plan's "wall id in succeeded" does not match the route**
- **Found during:** Task 1 (reading `revit_mcp/parameters.py` for the canned records)
- **Issue:** `set_parameter` builds `build_outcome(..., [parameter_name], ...)`, so `outcome.succeeded` is `["Comments"]`, not the wall id. A classifier requiring the wall id there would stop a correct live run.
- **Fix:** w3 is judged as `succeeded == [parameter]` and `args.element_id == the wall id`, which keeps the intent (the entry names the wall that was written).
- **Files modified:** tests/test_phase6_live_audit.py, tests/unit/test_phase6_live_audit.py
- **Verification:** rows `w3-succeeded-not-the-parameter` and `w3-wrong-wall`
- **Committed in:** `a7cb259`

**3. [Rule 2 - Missing critical] No PID in a reason**
- **Found during:** Task 1
- **Issue:** the 06-07 threat model (T-06-36) forbids PIDs and session tokens in `06-VALIDATION.md`, but stop reasons are what gets copied there, and audit file names carry the server PID.
- **Fix:** reasons name files by role (`parent audit file`, `child audit file`) and say "a different Revit" instead of printing PIDs; a unit row checks that none of five PIDs appears in a reason.
- **Committed in:** `a7cb259`

---

**Total deviations:** 3 auto-fixed (2 Rule 1, 1 Rule 2)
**Impact on plan:** the first was needed for the rollback step to run at all; the other two keep the classifier correct and the verdict text safe to commit.

## Issues Encountered

- Two retries in the tests, not the script: a torn-line row whose two halves happened to join into valid JSON (the row now asserts the line really is torn, and the aligned-hybrid line has its own row, caught by the counts), and a second in-process run reusing the first run's audit writer (a real rerun is a new process; the row calls `audit._reset()`).
- `git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit (a stale unrelated worktree entry, as in 06-01 and 06-05); all commits succeeded.
- A first attempt to append the Task 2 rows in one shell command failed with `ENAMETOOLONG`; nothing had been written, and the rows were written through a scratch file instead.

## Limitations

- Nothing here has run against a live Revit. The classifiers expect the shapes the Phase 4 routes document: `execute_code` answers HTTP 409 `rolled_back` with a non-Committed `transaction_status` when a posted error-severity failure rolls the transaction back (research assumption A3), `tag_elements` answers `partial` with `succeeded == [tag id]` and `failed` holding item 999999999 with a reason, and a saved scratch model's `document.path` is non-empty. If the live reply differs, the stop reasons name the field.
- run-dual is proven with a stand-in for the second server process (one process has one audit writer). The two-process write path itself (two real PID-named files) is proven by `test_two_processes_write_two_distinct_files_named_with_their_own_pids` in 06-05; the live run in 06-07 is the first time both write against two real Revit instances.
- Concurrency in run-dual is not asserted to overlap in time: the classifier judges integrity, not interleaving.

## Known Stubs

None.

## Threat Flags

None. The script adds one local subprocess (the child server process) and local file writes outside the repository, both inside the plan's T-06-30 to T-06-33.

## User Setup Required

None for this plan. Plan 06-07 needs a human with Revit (see the script's operator procedure).

## Next Phase Readiness

Ready for 06-07. The operator procedure is in the script's module docstring: rehearse until `REHEARSAL_ROLLED_BACK`, run `run-single` once, then `run-dual` once, each under the POSTS_SENT rule, and attach the printed output and records. `classify RECORD.json` re-judges a saved record at any time without sending anything.

## Self-Check: PASSED

- Files exist: `tests/test_phase6_live_audit.py`, `tests/unit/test_phase6_live_audit.py` (verified with `[ -f ]` below).
- Commits exist: 6f0d5b0, a7cb259, c170305, 5fef679 (`git rev-list --count cede82f..HEAD` = 4 at SUMMARY time).
- Acceptance criteria re-run: unit file 193 passed (asks 25); the importlib one-liner prints `[] PHASE6_AUDIT_OK PHASE6_AUDIT_STOP`; `template` exits 0 with `posts_sent`; the `run-single ... --audit-dir . --out tests/record.json` command exits 2 naming the repository and writes nothing; `--help` lists template, rehearse, run-single, run-dual, child, classify; `uv run pytest tests/unit` 6297 passed, 3 skipped, 0 failed.
