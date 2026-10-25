---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "01"
subsystem: infra
tags: [mcp, fastmcp, elicitation, uv, audit-wrapper, dependency-upgrade]

requires:
  - phase: 06-structured-audit-log-of-true-outcomes
    provides: audit.install_audited_tools (the tool wrapper that adds user_request)
provides:
  - "mcp[cli]>=1.30,<2 pin; uv.lock resolved to mcp 1.30.0 and approved by the user"
  - "structured_output=False default in audit.install_audited_tools (59-tool surface and call_tool shape unchanged)"
  - "tests/unit/elicitation_support.py: in-memory Hermes-shaped elicitation client (hermes_callback, connected)"
  - "tests/unit/test_sdk_upgrade.py: SDK regression and elicitation round-trip rows"
affects: [07-02, 07-03, 07-09, 07-14]

actuals:
  tokens: 42850        # chars/4 over the full realized diff, uv.lock included (2259 without uv.lock)
  tasks: 3
  commits: 1
plan_head_before: b3522f84f0b9f9129632e503d20846de492fe625
commits: 1

tech-stack:
  added: [mcp 1.30.0, annotated-doc, attrs, cffi, cryptography, jsonschema, jsonschema-specifications, pycparser, pyjwt, pywin32, referencing, rpds-py]
  patterns: ["structured_output defaulted off at the audit wrapper", "in-memory MCP client session with a scripted elicitation callback"]

key-files:
  created: [tests/unit/elicitation_support.py, tests/unit/test_sdk_upgrade.py]
  modified: [pyproject.toml, uv.lock, audit.py]

key-decisions:
  - "D-24: target mcp 1.30.x (pin <2), not 2.x"
  - "Consent over elicitation is the action only: accept arrives with content {} (Hermes shape), so later plans trust only the action"
  - "structured_output=False is the default in the audit wrapper, not per tool, so no registrar changes"

requirements-completed: [SAFE-19]

coverage:
  - id: D1
    description: "mcp pinned to >=1.30,<2 and uv.lock resolves mcp 1.30.0; resolved package list approved by the user before install"
    requirement: SAFE-19
    verification:
      - kind: unit
        ref: "tests/unit/test_sdk_upgrade.py#test_mcp_version_is_1_30_or_later_1_x"
        status: pass
    human_judgment: false
  - id: D2
    description: "All 59 production tools still listed with no outputSchema and the optional user_request property; call_tool keeps the content-list shape"
    requirement: SAFE-19
    verification:
      - kind: unit
        ref: "tests/unit/test_sdk_upgrade.py#test_all_production_tools_listed_without_output_schema_and_with_user_request"
        status: pass
      - kind: unit
        ref: "tests/unit/test_sdk_upgrade.py#test_call_tool_returns_content_blocks_with_text_not_a_tuple"
        status: pass
    human_judgment: false
  - id: D3
    description: "Form-mode elicitation round trip (accept with empty content, decline, cancel, no capability, Cyrillic message byte-identical) against a Hermes-shaped client"
    requirement: SAFE-19
    verification:
      - kind: unit
        ref: "tests/unit/test_sdk_upgrade.py#test_elicit_form_returns_the_action_the_hermes_style_client_chose"
        status: pass
      - kind: unit
        ref: "tests/unit/test_sdk_upgrade.py#test_client_without_elicitation_callback_reports_no_capability"
        status: pass
      - kind: unit
        ref: "tests/unit/test_sdk_upgrade.py#test_cyrillic_elicitation_message_arrives_byte_identical"
        status: pass
    human_judgment: false
  - id: D4
    description: "Elicitation against a real Hermes Desktop 2.0.0 client behaves like the in-memory harness (research assumption A9)"
    requirement: SAFE-19
    verification: []
    human_judgment: true
    rationale: "Only the D-20 live bench (plan 07-14) can show a real Hermes client; the in-memory harness is a model of its handler"

duration: 5min
completed: 2026-10-25
status: complete
---

# Phase 7 Plan 01: MCP SDK upgrade to 1.30 Summary

**mcp 1.9.0 -> 1.30.0 with the 59-tool surface and call_tool shape held constant by a `structured_output=False` default in the audit wrapper, and server-side `elicit_form` proven against a Hermes-shaped in-memory client.**

## Performance

- **Duration:** about 5 min for this continuation (Tasks 1 and 2 ran in the earlier session, the user's review time is not counted)
- **Started:** 2026-10-25T17:58:02Z (Task 3 resume)
- **Completed:** 2026-10-25T18:03Z
- **Tasks:** 3 (Task 2 is the human checkpoint)
- **Files modified:** 5 in one commit

## Accomplishments

- `pyproject.toml` pins `mcp[cli]>=1.30,<2`; `uv.lock` resolves mcp 1.30.0 (`uv lock --check` OK).
- `audit.install_audited_tools` passes `structured_output=False` unless the caller sets it. Measured without it: FastMCP 1.30 gives `-> str` tools an `outputSchema` and `call_tool` returns a tuple. With it: no `outputSchema` on any of the 59 tools and `call_tool` returns content blocks with `.text`, as on 1.9.0.
- `tests/unit/elicitation_support.py`: `hermes_callback(script)` (steps accept / decline / cancel / raise / hang, records `.messages`, declines when the script is exhausted) and `connected(server, callback=None)` over `create_connected_server_and_client_session`.
- `tests/unit/test_sdk_upgrade.py`: 9 passing cases (version range, 59-tool surface, call_tool shape, accept/decline/cancel, no capability, Cyrillic, exhausted script).

## Checkpoint record (Task 2, blocking-human)

Presented to the real user, who replied: **"approved"**. Reviewed package delta (`uv.lock` re-resolved, nothing installed at that point):

- **Added:** annotated-doc 0.0.5, attrs 26.1.0, cffi 2.1.1, cryptography 50.0.2, jsonschema 4.26.0, jsonschema-specifications 2025.9.1, pycparser 3.12, pyjwt 2.15.1, pywin32 312, referencing 0.37.0, rpds-py 2026.9.1
- **Changed:** mcp 1.9.0 -> 1.30.0; typer 0.15.4 -> 0.27.3 (typing-inspection 0.4.0 -> 0.4.2 also moved in the lock)
- **Removed:** nothing. `sniffio` stays, contrary to the research note.

## Task Commits

1. **Task 1: pin and resolve** - no commit by design (committed with Task 3)
2. **Task 2: user review** - checkpoint, no commit
3. **Task 3: install, audit default, harness and tests** - `8ccb854` (chore(07-01))

## Files Created/Modified

- `pyproject.toml`, `uv.lock` - the pin and the re-resolved lock
- `audit.py` - `kwargs.setdefault("structured_output", False)` and the docstring sentence
- `tests/unit/elicitation_support.py`, `tests/unit/test_sdk_upgrade.py` - new

## Verification

- `uv run pytest tests/unit/test_sdk_upgrade.py tests/unit/test_audit_registration.py tests/unit/test_audit_stdio.py -q`: 21 passed
- `uv run pytest tests/unit -q`: **6370 passed, 3 skipped**, 0 failed
- `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.951** (< 2.0)
- `uv lock --check` OK; `importlib.metadata.version("mcp")` = 1.30.0 in the verification environment
- No existing test helper needed a change on 1.30.

## Decisions Made

See `key-decisions`. No file outside the plan's list was touched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `uv sync` could not replace packages in the shared `.venv`**
- **Found during:** Task 3 (`uv sync --group dev`)
- **Issue:** about 15 other processes (`uv ... run main.py` -> `.venv\Scripts\python.exe main.py`, started by other Claude sessions and by Hermes) are running from this repo's `.venv`. `uv sync` failed repeatedly with `failed to remove directory ... Access denied (os error 5)` and left `.venv` half-upgraded: `mcp-1.9.0`, `typer-0.15.4`, `typing_inspection-0.4.0` and `ruamel_yaml-0.19.1` dist-info directories have lost their `METADATA`/`RECORD` (`uv pip check` reports 4 broken packages). No process was stopped.
- **Fix:** verified the committed lock in a separate environment instead: `UV_PROJECT_ENVIRONMENT=<scratchpad>/venv130 uv sync --frozen --group dev` (installs exactly the approved lock), and ran every check there. The commit content (pyproject.toml, uv.lock, audit.py, tests) does not depend on `.venv`.
- **Files modified:** none in the repo
- **Commit:** n/a

**Total deviations:** 1 auto-fixed (1 blocking, environment only). **Impact:** the repository is correct and verified on mcp 1.30.0; the shared `.venv` must be rebuilt (see below).

## Issues Encountered

- **Action needed from the user:** the repo `.venv` is in a broken mixed 1.9.0/1.30.0 state. A new `uv run main.py` or `uv run pytest` against it may fail or load the wrong mcp until it is repaired. Close the sessions that hold it (the many `uv --directory ...revit-mcp-server run main.py` processes), then run `uv sync --group dev` (or delete `.venv` and run it). Running MCP servers already loaded their modules in memory and are unaffected until restarted. A restart of those servers after the repair is also what puts mcp 1.30 behind the live `revit` entry.
- Research assumption A9 (a 2.0.0 Hermes client elicits like this harness) stays unverified until the D-20 live bench (07-14).

## Threat Flags

None. The new dependency surface was exactly the threat T-07-SC and was reviewed at the blocking checkpoint.

## Known Stubs

None.

## Next Phase Readiness

Plans 07-02 and 07-09 can import `elicitation_support.hermes_callback` / `connected` and call `ctx.session.elicit_form` on mcp 1.30. Plan 07-03 still owns the payload-side pywin32 shim.

## Self-Check: PASSED

- FOUND: tests/unit/elicitation_support.py, tests/unit/test_sdk_upgrade.py
- FOUND: commit 8ccb854 (5 files: pyproject.toml, uv.lock, audit.py, the two test files; none from graphify-out/ or .planning/)
- `git rev-list --count b3522f8..HEAD` = 1 (measured)
