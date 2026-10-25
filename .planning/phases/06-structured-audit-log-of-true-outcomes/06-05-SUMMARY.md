---
phase: 06-structured-audit-log-of-true-outcomes
plan: 05
subsystem: audit
tags: [audit, retention, prune, rotation, stdio, fake-revit, documentation]

requires:
  - phase: 06-structured-audit-log-of-true-outcomes
    provides: roll-forward SegmentHandler and queue-backed writer (06-01), entry schema (06-02, 06-03), call_id and user_request injection (06-04)
provides:
  - audit.prune(directory, now, max_age_seconds, max_total_bytes), retention_settings(), _positive_int_env(), MAX_AGE_DAYS_ENV, MAX_TOTAL_MB_ENV, DEFAULT_MAX_AGE_DAYS, DEFAULT_MAX_TOTAL_MB, AUDIT_FILE_GLOB; start-up prune in _writer()
  - tests/unit/test_audit_writer.py (42 rows: first_write, rotate, reader, format, ordering, concurrent, two_processes, prune, settings, startup, default directory, never_breaks)
  - tests/unit/test_audit_stdio.py (static AST rows, logger row, real main.py stdio session against a fake Revit)
  - tests/unit/audit_support.py FakeRevitServer; read_entries now orders segments by number
  - CLAUDE.md audit invariant, README.md "### Audit log", bridge.py docstring "Audit" section
affects: [06-06, 06-07]

plan_head_before: 71272151c2dcbe1de15493386baf020548252510
actuals:
  tokens: 12000
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "prune runs before the writer opens its own segment, so a process can never delete its own file; it is case-sensitive (fnmatchcase), regular-files-only, non-recursive and skips symlinks"
    - "FakeRevitServer: a ThreadingHTTPServer in the test process whose identity PID is the test process, so the real netstat listener check in a server subprocess accepts it"

key-files:
  created:
    - tests/unit/test_audit_writer.py
    - tests/unit/test_audit_stdio.py
  modified:
    - audit.py
    - tests/unit/audit_support.py
    - bridge.py
    - CLAUDE.md
    - README.md

key-decisions:
  - "A file that cannot be deleted still counts toward the directory total, and a file already removed by another server is not reported as deleted by this one"
  - "prune and retention failures are silent (no stderr line): only an entry-drop warns, and only once per process"
  - "Invalid retention values (empty, non-ASCII-digit, zero, negative, fractional, hex) fall back to the defaults rather than raising"

patterns-established:
  - "Segment files sort by (writer stem, segment number), not by name: '<stem>.0002.jsonl' sorts before '<stem>.jsonl' lexically"

requirements-completed: [AUDIT-05, AUDIT-06, AUDIT-07]

coverage:
  - id: D1
    description: "Growth is bounded from the first write: exact-cap lines stay, an oversize line is written whole, per-process keep, start-up prune by age (strict) then size (stop at the cap), idempotent, never touching foreign files, symlinks or subdirectories, skipping held files and tolerating vanished ones"
    requirement: "AUDIT-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_writer.py -k 'first_write or rotate or prune or startup or settings'"
        status: pass
    human_judgment: false
  - id: D2
    description: "No record is lost to a held reader, per-process order is the enqueue order, 100 concurrent calls to two incarnations give 100 whole lines naming their own process and outcome, and two server processes write two distinct PID-named files"
    requirement: "AUDIT-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_writer.py#test_reader_holding_the_active_segment_loses_no_record"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_writer.py#test_concurrent_calls_to_two_incarnations_yield_one_whole_line_each"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_writer.py#test_two_processes_write_two_distinct_files_named_with_their_own_pids"
        status: pass
    human_judgment: false
  - id: D3
    description: "A writer failure (unwritable directory, full queue, failing serialization, a raising record_call) never changes a tool result; one stderr line per process names only the exception class"
    requirement: "AUDIT-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_writer.py -k never_breaks"
        status: pass
    human_judgment: false
  - id: D4
    description: "ROADMAP criterion 4: audit.py and bridge.py have no path to stdout, the audit logger does not propagate and has one QueueHandler, and a real main.py stdio session with the audit active emits only valid JSON-RPC lines on stdout while its audit file fills"
    requirement: "AUDIT-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_stdio.py"
        status: pass
      - kind: command
        ref: "uv run python tests/test_init_latency.py (INIT_LATENCY_S=0.851)"
        status: pass
    human_judgment: false
  - id: D5
    description: "CLAUDE.md, README.md and the bridge.py docstring describe the audit log for contributors and engineers (location, contents, retention, finding an entry, user_request)"
    requirement: "AUDIT-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_serialization_scope_docs.py"
        status: pass
    human_judgment: true
    rationale: "Whether the prose is clear to a contributor or engineer is a reading judgment no test asserts; the pinned serialization sentences are test-covered"
---

# Phase 6 Plan 05: Retention, stdio proof and documentation Summary

**Bounded audit growth (start-up prune by age then size, MiB and day settings from the environment), a real main.py stdio session proving stdout stays pure JSON-RPC, and the audit log documented in CLAUDE.md, README.md and the bridge docstring.**

## Performance

- **Tasks:** 3 of 3
- **Commits:** 4 (test, feat, test, docs)
- **Files:** 2 created, 5 modified

## Accomplishments

- `audit.prune` deletes only regular `audit-*.jsonl` files directly inside the audit directory (case-sensitive match, no recursion, symlinks skipped). It removes files strictly older than the age limit first, then the oldest until the total is at or below the cap, and returns the names this call deleted. It never raises.
- `retention_settings()` reads `REVIT_MCP_AUDIT_MAX_AGE_DAYS` (default 180) and `REVIT_MCP_AUDIT_MAX_TOTAL_MB` (default 500, MiB = 1024 * 1024 bytes); bad values fall back to the defaults.
- `_writer()` prunes after creating the directory and before its own segment exists, inside its own try/except.
- 42 writer rows: segment cap from the first write (exact cap stays, one byte over rolls, oversize line written whole), rotation without rename, a reader holding segment 1 while 20 records land, no CRLF, lone surrogate, enqueue order, 100 concurrent calls to two incarnations, two real subprocess writers, the prune and settings rows, start-up prune, default directories, and four never_breaks rows.
- A real `main.py` stdio session (initialize, `get_revit_status`, `execute_revit_code` with `user_request` "проверка") against `FakeRevitServer` yields only JSON-RPC lines on stdout, an `Audit: call_id` line in the mutation reply, one audit file with both entries, and no secret in the file or stderr.
- Documentation: `audit.py` joins the no-print invariant in CLAUDE.md, plus an audit invariant paragraph; README gains "### Audit log"; the bridge.py docstring gains an "Audit" section. The pinned "Serialization scope" sentences are untouched.

## Task Commits

1. `78f98fb` test(06-05): writer, retention, reader, concurrency and never_breaks rows (RED: 21 failing until `audit.prune` existed); also the `read_entries` ordering fix
2. `32e9eb0` feat(06-05): `audit.prune`, retention settings and the start-up prune (GREEN: 42 passed)
3. `1061ace` test(06-05): stdio session, static and logger rows, `FakeRevitServer`
4. `3b04219` docs(06-05): CLAUDE.md, README.md, bridge.py docstring

## Verification

- `uv run pytest tests/unit/test_audit_writer.py -q`: 42 passed (plan asks 22). `-k prune`: 11 passed (asks 7). `-k never_breaks`: 4 passed (asks 4). The `-k "first_write or rotate or ..."` filter: 24 passed.
- `uv run pytest tests/unit/test_audit_stdio.py -q -rs`: 5 passed, no skip on this Windows machine; `-k static`: 3 passed.
- `uv run python tests/test_init_latency.py`: `INIT_LATENCY_S=0.851` (below 2.0), exit 0.
- `uv run python -c "import audit; ..."` prints `180 500 REVIT_MCP_AUDIT_MAX_AGE_DAYS REVIT_MCP_AUDIT_MAX_TOTAL_MB`.
- Doc criteria: `grep -c "audit.py" CLAUDE.md` is 4 and the no-print line names `audit.py`; `### Audit log` appears once in README.md; `user_request` appears in README.md; `'audit.record_call' in bridge.__doc__` is True; `tests/unit/test_serialization_scope_docs.py` 8 passed.
- Full suite `uv run pytest tests/unit -q`: 6104 passed, 3 skipped, 0 failed (the 3 skips are pre-existing).
- The "Edge probe" items for AUDIT-05 and AUDIT-06 stay flagged for human review at verification, as the plan states; live two-Revit proof is 06-07.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] read_entries sorted segments by file name, putting segment 1 last**
- **Found during:** Task 1 (the reader row)
- **Issue:** `"<stem>.0002.jsonl"` sorts before `"<stem>.jsonl"` ('0' < 'j'), so `read_entries` returned a writer's first segment after its later ones and broke order assertions.
- **Fix:** `_segment_order` sorts by (writer stem, segment number), segment 1 being the plain name.
- **Files modified:** tests/unit/audit_support.py
- **Commit:** 78f98fb

**2. [Resume note] test_audit_writer.py already existed, untracked**
- The previous executor (killed by a rate limit) had left a complete `tests/unit/test_audit_writer.py` on disk although the brief said the tree had no edits. It was read in full, checked against the plan's behavior rows, run RED (21 failures, all `audit.prune` / retention settings missing), and committed as the Task 1 RED commit. No row was weakened.

**3. [Note] Task 2 had no RED phase**
- `audit.py` and `bridge.py` already had no path to stdout, so the stdio rows passed on first run. No source fix was needed in this task. The session row asserts on the actual bytes (every stdout line parsed, the `Audit:` line, the file entries), so it is not vacuous.

**Total deviations:** 1 auto-fixed (Rule 1), 2 notes. **Impact:** none on scope; no production code besides the planned `audit.py` additions changed. `bridge.py` changed only in its docstring.

## Known Stubs

None.

## Threat Flags

None. The only new surface is local file deletion in the audit directory, which is the plan's own T-06-24 and is covered by the foreign-file, symlink and subdirectory rows.

## Issues Encountered

- `git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on this machine after each commit (a stale worktree entry that git's housekeeping cannot remove). All four commits succeeded; the message is unrelated to this plan.

## Next Phase Readiness

Ready for 06-06. The writer is bounded, readers and concurrency are proven offline, and criterion 4 is proven by a real stdio session. Criterion 5's live half and the two-Revit run remain for 06-07.

## Self-Check: PASSED

- Files exist: audit.py, tests/unit/test_audit_writer.py, tests/unit/test_audit_stdio.py, tests/unit/audit_support.py, CLAUDE.md, README.md, bridge.py.
- Commits exist: 78f98fb, 32e9eb0, 1061ace, 3b04219 (`git rev-list --count 7127215..HEAD` = 4 at SUMMARY time).
