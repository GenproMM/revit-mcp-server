---
phase: 06-structured-audit-log-of-true-outcomes
plan: 03
subsystem: audit
tags: [audit, jsonl, redaction, secret, args, user-request, privacy]

requires:
  - phase: 06-structured-audit-log-of-true-outcomes
    provides: build_entry outcome table, SCHEMA_1_FIELDS names for the request-side fields, bridge._audit passing secret=_secret(), Machine fake and read_entries
provides:
  - audit.shape_args / shape_user_request / windows_user with code-point caps (500 string, 200 list items, depth 4, 2000 user_request, 8192 code)
  - single redaction path (redact_text, _clip, redact) applied before every cut and again on the whole entry and the finished line
  - entry fields windows_user, args, args_truncated, code_length, code_sha256, user_request, user_request_missing, user_request_length, user_request_source
  - tests/unit/test_audit_secret.py, the file-bytes grep of ROADMAP criterion 7 through the real bridge and an audited FastMCP
affects: [06-04, 06-05, 06-06, 06-07, phase-07]

plan_head_before: 64a3cb884e2f3c5ce63a2b4e9bd61bedfc21eca5
actuals:
  tokens: 11000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Redact then cut: every truncation goes through _cut/_clip, which replace the secret (raw and JSON-escaped) before taking the code-point prefix"
    - "Key scrub only for tool arguments (SECRET_ARG_KEY); the whole-entry pass replaces the secret value only, so process.session_token is never touched"
    - "Pure builder keeps windows_user and secret as arguments; record_call supplies them"

key-files:
  created:
    - tests/unit/test_audit_secret.py
  modified:
    - audit.py
    - tests/unit/test_audit_entry.py

key-decisions:
  - "args_truncated is recorded only when the redacted text really exceeded the cap; length is the original (pre-redaction) length"
  - "code_sha256 is taken over the original, unredacted UTF-8 bytes (surrogatepass so a lone surrogate cannot raise); the stored code is redacted"
  - "A bridge call outside any tool (no user_request argument exists) is recorded as user_request_missing true"
  - "List item paths in args_truncated use name[index], nested dict paths use dots"

patterns-established:
  - "A real registered tool is exercised without an MCP request by calling the wrapper stored on the tool with ctx=None (mcp.call_tool injects a Context that refuses use outside a request)"
  - "Secret tests assert on raw file bytes: the raw secret, its JSON-escaped form and every 16-character run"

requirements-completed: [AUDIT-02, AUDIT-08]

coverage:
  - id: D1
    description: "args record the tool's arguments without ctx and None values, cut by code points with the original length or item count listed, requested new parameter values verbatim, no HTTP body or reply data"
    requirement: "AUDIT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_args_long_string_is_cut_and_its_length_listed"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_args_cyrillic_string_is_cut_by_code_points_not_bytes"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_args_never_hold_the_http_body_or_reply_data"
        status: pass
    human_judgment: false
  - id: D2
    description: "execute_revit_code entries carry the code up to 8192 code points, the full length and the SHA-256 of the full UTF-8 bytes; the code cut is not an args_truncated 500 cut"
    requirement: "AUDIT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_code_long_text_is_cut_to_8192_with_length_and_sha256"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_code_hash_is_over_the_original_even_when_the_secret_is_redacted"
        status: pass
    human_judgment: false
  - id: D3
    description: "user_request recorded verbatim, redacted, cut to 2000 with true length, missing flag and source 'assistant'; a missing value never alters the call"
    requirement: "AUDIT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_user_request_long_text_is_cut_to_2000_with_its_true_length"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_user_request_absent_is_recorded_as_missing"
        status: pass
    human_judgment: false
  - id: D4
    description: "windows_user is DOMAIN\\user (USERDOMAIN and USERNAME, else getpass, else unknown), cached per process; no computer name, client, session id or address is written"
    requirement: "AUDIT-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_windows_user_is_computed_once_per_process"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_windows_user_is_written_and_nothing_else_about_the_person_or_machine"
        status: pass
    human_judgment: false
  - id: D5
    description: "The configured secret, its JSON-escaped form and any 16-character run of it never appear in an audit file after success, 401, transport exception, tool raising after its bridge call, secret pasted into args / user_request / execute_revit_code code, echoed in a reply, straddling a cut, or in a route tail"
    requirement: "AUDIT-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_secret.py#test_secret_scenario_leaves_one_entry_and_no_trace_of_the_secret"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_secret.py#test_secret_every_scenario_in_one_log_leaves_nine_entries_and_no_trace"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_redact_secret_straddling_the_argument_cut_leaves_no_16_character_run"
        status: pass
    human_judgment: false
  - id: D6
    description: "A broken writer writes at most one stderr line per process naming only the exception class, never the entry or the secret, and tool replies are unchanged apart from the missing Audit line"
    requirement: "AUDIT-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_secret.py#test_secret_failure_path_writes_one_stderr_line_and_changes_no_reply"
        status: pass
    human_judgment: false
  - id: D7
    description: "No excess personal data and the assistant-reported user_request is never presented as verified (prohibitions, verified by judgment per the plan)"
    requirement: "AUDIT-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_user_request_is_never_claimed_as_seen_by_the_server"
        status: pass
    human_judgment: true
    rationale: "Descriptor-less prohibitions: the rows pin the key set and the source label but cannot prove the absence of any other personal datum; the plan's flagged AUDIT-08 edge probe item stays for human review at verification"

duration: 9min
completed: 2026-10-25
status: complete
---

# Phase 6 Plan 03: Request side of the entry and secret redaction Summary

**Each audit entry now says who asked (the Windows user), what the tool was asked to do (capped, redacted arguments, execute_code text with its length and SHA-256) and what the assistant reported the user wrote, and the shared secret has no path into the log: it is replaced before every cut, over the whole entry and on the finished line, and a file-bytes grep over nine scenarios proves it through the real bridge.**

## Performance

- **Duration:** about 9 min
- **Started:** 2026-10-25T10:07:22Z
- **Completed:** 2026-10-25T10:17Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- `shape_args` drops `ctx` and None values, scrubs values under keys matching `secret|token|password|api_key` (also in nested dicts), cuts strings at 500 code points and lists at 200 items, stops at depth 4, turns non-JSON values (bytes, objects, non-finite floats) into their type name, and records every cut in `args_truncated` as `{arg, length}` or `{arg, count}`.
- `execute_revit_code` keeps its code up to 8192 code points with `code_length` and `code_sha256` over the original UTF-8 bytes; the code cut is reported by `code_length`, not as a 500 cut.
- `shape_user_request`, `windows_user` (cached, cleared by `_reset`) and the new `ALWAYS_PRESENT_FIELDS` entries; Schema 1 docstring updated.
- Redaction is one path: `redact_text` (raw and JSON-escaped), `_cut`/`_clip` (redact, then cut), `redact` (whole entry, keys included) and the unchanged final pass in `serialize_entry`. Every existing cut in `build_entry` and its helpers (route_arg, reasons, `revit_failures`, document fields, `reply_status`, `document_scope`) now goes through it, closing the 06-02 hand-off.
- `tests/unit/test_audit_secret.py` runs nine scenarios on the Machine through the real bridge, the real tool registry and an audited FastMCP, plus the writer-failure stderr rows. A mutation check (redaction disabled) makes the pasted-secret rows fail, so the grep is not vacuous.
- Unit suite: 6034 passed, 3 skipped (baseline 5975 after 06-02, plus 42 entry rows and 17 secret rows). `INIT_LATENCY_S=0.851`.

## Task Commits

1. **Task 1: Entries record who asked and what was asked, redacted before every cut** - `ed8f5bf` (feat)
2. **Task 2: Secret grep across the criterion 7 scenarios through the real bridge** - `17ea423` (test)

**Plan metadata:** committed separately as `docs(06-03)`.

## Files Created/Modified

- `audit.py` - constants, redaction functions, `shape_args`, `shape_user_request`, `windows_user`, `build_entry(..., windows_user=None, secret=None)`, `record_call` supplies both, Schema 1 docstring
- `tests/unit/test_audit_entry.py` - 42 rows: args, code, user_request, windows, redact, schema
- `tests/unit/test_audit_secret.py` - 17 rows (9 scenarios individually, all in one log, replaced-in-place, echo, route tail, no secret loaded, identity fields kept, failure path, quiet when healthy) (new)

## Decisions Made

- `args_truncated` is written only when the redacted text exceeded the cap (a secret that shrinks a 520-character value under 500 is not a cut); `length` is the original length.
- `code_sha256` is computed before redaction so the digest identifies what ran; the stored code is redacted. A lone surrogate is hashed with `surrogatepass` so hashing cannot raise.
- A bridge call made outside any tool has no `user_request` argument, so it is recorded as `user_request_missing: true`.
- List items in `args_truncated` paths use `name[index]`, nested dict keys use dots.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Real `execute_revit_code` cannot run under `mcp.call_tool` in a unit test**
- **Found during:** Task 2 (first run)
- **Issue:** `call_tool` injects a `Context` that raises "Context is not available outside of a request" when the real tool does `await ctx.info(...)`.
- **Fix:** the secret test calls the real registered tool through the wrapper stored on it (`mcp._tool_manager.get_tool(name).fn(ctx=None, ...)`), which is the same audited wrapper a client reaches. No production code changed.
- **Files modified:** `tests/unit/test_audit_secret.py`
- **Committed in:** `17ea423`

---

**Total deviations:** 1 auto-fixed (1 Rule 3, test harness only)
**Impact on plan:** None on behaviour. `bridge.py` was not touched: `_audit` already passed `secret=_secret()`, and no scenario needed a fix in `audit.py` after Task 1.

## Issues Encountered

- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` (stale unrelated worktree, as in 06-01 and 06-02); both commits succeeded.
- `graphify update .` (CLAUDE.md) was not run: `graphify-out/` is already dirty from earlier sessions and the plan restricts commits to its own files.

## Known Stubs

None.

## Threat Flags

None. The only new surface is the request content written to the local audit file, covered by T-06-13 to T-06-17.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 06-04: the entry is complete for schema 1 (every field in `SCHEMA_1_FIELDS` is now produced where it applies); `redact`/`_clip` are the only redaction path any later field must use.
- Open for human review at verification: the plan's flagged AUDIT-08 edge probe item (further edges the probe could not classify) is unresolved by design.

---
*Phase: 06-structured-audit-log-of-true-outcomes*
*Completed: 2026-10-25*

## Self-Check: PASSED

- Created files exist: tests/unit/test_audit_secret.py (verified with `[ -f ]` below).
- Commits found: ed8f5bf, 17ea423; measured `git rev-list --count` from plan_head_before = 2.
- Acceptance criteria re-run: `-k redact` 14 passed, `-k "args or code"` 22 passed, `-k "user_request or windows"` 12 passed; constants print `500 2000 8192 200 True`; secret file 17 passed, `-k "stderr or failure"` 2 passed; full unit suite 6034 passed 3 skipped; `INIT_LATENCY_S=0.851`.
