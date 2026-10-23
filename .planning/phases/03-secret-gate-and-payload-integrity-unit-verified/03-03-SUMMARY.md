---
phase: 03-secret-gate-and-payload-integrity-unit-verified
plan: 03
subsystem: security
tags: [shared-secret, bridge, secret-file, parity-test, http-401, format-response]

requires:
  - phase: 03-secret-gate-and-payload-integrity-unit-verified
    provides: revit_mcp/trust.py (secret_from_bytes, read_secret_file, auth_failure, constants) and bridge.with_envelope from plan 03-01
provides:
  - bridge.load_secret(search_dirs=None) - client half of the secret file contract (payload layout beside bridge.py, dev layout in revit_mcp/), called by no production code
  - bridge._secret_from_bytes - duplicate of trust.secret_from_bytes, pinned identical by a parity table
  - bridge.SECRET_FILE_NAME and MIN_SECRET_LENGTH mirroring trust.py
  - tests proving the send path is inert (exact json.dumps bytes, no _mcp key, no production call sites)
  - 401 visibility pair in test_format_response.py modelled on the rolled_back pair
affects: [03-04, 03-06, 03-08, 05 live enforcement]

plan_head_before: cc9025691ce4298d6cad1d7cc70ad22505dcab7b
actuals:
  tokens: 4300
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Small rule duplicated across the two runtimes (payload ships no revit_mcp/) with a parity test over shared fixtures and real files as the only coupling"
    - "AST call-site test proving a helper is wired into no production module"

key-files:
  created:
    - tests/unit/test_bridge_secret_client.py
  modified:
    - bridge.py
    - tests/unit/test_format_response.py

key-decisions:
  - "load_secret: the first existing _bridge_secret decides, an invalid first file gives None and never falls through to the second"
  - "load_secret skips an unusable search entry (None, int, NUL path) instead of raising, so the never-raises promise holds for hostile arguments"
  - "format_response is unchanged (CLAUDE.md: no new implicit error signals); the 401 status carries the signal and an alarm test documents it"

requirements-completed: [SEC-02, SEC-03, SEC-06, SEC-08]

coverage:
  - id: D1
    description: "bridge.load_secret reads the secret from the first existing file in [beside bridge.py, revit_mcp/], never raises, never logs, and equals trust.read_secret_file for every shared fixture"
    requirement: "SEC-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_secret_client.py#test_parity_load_secret_matches_read_secret_file"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_secret_client.py#test_search_first_existing_file_decides_even_when_invalid"
        status: pass
    human_judgment: false
  - id: D2
    description: "bridge._secret_from_bytes and the four constants are identical to the trust.py rule (BOM, CRLF, 15/16 chars, UTF-16, undecodable, NUL, Cyrillic)"
    requirement: "SEC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_secret_client.py#test_parity_secret_from_bytes_matches_trust"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_secret_client.py#test_constants_equal_the_trust_constants"
        status: pass
    human_judgment: false
  - id: D3
    description: "No secret in any client-half output (load result logs, stdout, with_envelope refusal text); with_envelope never mutates and refuses a pre-seeded _mcp or non-dict body"
    requirement: "SEC-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_secret_client.py#test_secret_never_logged_on_success"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_secret_client.py#test_secret_never_in_with_envelope_refusal_text"
        status: pass
    human_judgment: false
  - id: D4
    description: "The send path is still inert: _send posts exactly json.dumps(data) as text/plain with no _mcp key, and no production module calls load_secret or with_envelope"
    requirement: "SEC-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_secret_client.py#test_inert_send_posts_exactly_json_dumps"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_secret_client.py#test_inert_no_production_call_sites"
        status: pass
    human_judgment: false
  - id: D5
    description: "A 401 auth refusal reaches the model as a visible error: verbatim Error: 401 string, real body as dict renders ERROR DETAILS, auth key alone is not an error signal, 401 distinct from other refusal statuses, no secret rendered"
    requirement: "SEC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_format_response.py#test_auth_401_reaches_the_model_as_a_visible_error"
        status: pass
      - kind: unit
        ref: "tests/unit/test_format_response.py#test_auth_key_alone_is_not_an_error_signal"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 03: Bridge secret loading and the 401 visibility pair Summary

**`bridge.load_secret` reads the shared secret exactly the way `revit_mcp/trust.py` does (duplicated rule, pinned by a 60-case parity table over shared fixtures and real files), a test proves nothing sends it yet, and a three-assertion 401 pair proves a refused mutation reaches the model as a visible error.**

## Performance

- **Duration:** about 3 min
- **Started:** 2026-10-23T09:07:34Z
- **Completed:** 2026-10-23T09:10:30Z
- **Tasks:** 2 of 2
- **Files:** 1 created, 2 modified

## Accomplishments

- `bridge.py` (append only): `SECRET_FILE_NAME`, `MIN_SECRET_LENGTH`, `_secret_from_bytes` and `load_secret(search_dirs=None)`. Default search is beside `bridge.py` (payload layout, D-08), then `revit_mcp/` (dev layout, D-09), computed at call time; the first existing file decides. Never raises, never logs, never called at import.
- `tests/unit/test_bridge_secret_client.py` (67 tests): search-order table, default-directory test via a monkeypatched `bridge.__file__`, directory and PermissionError cases with no log records, hostile search entries, parity of `_secret_from_bytes` with `trust.secret_from_bytes` over 18 fixtures plus non-bytes inputs, parity of `load_secret` with `trust.read_secret_file` over the same files written to disk, `with_envelope` refusals with no value leakage, `test_inert_send_posts_exactly_json_dumps`, and an AST test that no production module calls `load_secret` or `with_envelope`.
- `tests/unit/test_format_response.py` (+9 test cases, no existing line changed): verbatim `Error: 401 - ...` passthrough, the real `auth_failure()` body as a dict renders `ERROR DETAILS` for all three reasons, the alarm that a lone `auth` key is not an error signal, 401 distinct from 200/409/412/422/423/503, and no secret in rendered output.

## Task Commits

1. **Task 1: bridge.load_secret, parity and inert-send tests** - `1e2f6b2` (feat) - bridge.py, tests/unit/test_bridge_secret_client.py
2. **Task 2: 401 visibility pair** - `35b978f` (test) - tests/unit/test_format_response.py

## Verification

- `uv run pytest tests/unit -q`: 4301 passed, 3 skipped, 0 failed (03-01 recorded 4180 passed; the extra tests come from plan 03-02 and this plan, plus an unrelated untracked `tests/unit/test_parallel_installation.py` from another session that was not touched).
- `test_bridge_secret_client.py`: 67 passed; selector `-k "inert or secret_never or parity"`: 54 passed (floor 5).
- Guard files `test_serialization_scope_docs`, `test_local_bridge_transport`, `test_textutils`, `test_secret_gate_e2e`, `test_bridge_serialization`: 136 passed.
- `test_format_response.py -k "401 or auth"`: 9 passed (floor 5); whole file 34 passed; `git diff HEAD` showed zero removed lines before commit.
- `CLIENT_HALF_OK` one-liner prints; `INIT_LATENCY_S=0.379` (gate 2.0).
- `git status --porcelain -- revit_mcp tools main.py` prints nothing; `git hash-object startup.py` is `85de483307be925517bee2ce3f109e5d6538560c` before and after.
- RED was observed first for Task 1 (59 failing, 8 incidentally passing); Task 2's tests were written and run together, with one failure (below) fixed before commit.

## Decisions Made

- The first existing file decides in `load_secret`; an empty or malformed first file yields None rather than a silent fallback to a different secret.
- `load_secret` skips a search entry that cannot form a path (`None`, an int, a NUL-bearing string) rather than raising, so "never raises" holds for any argument.
- `format_response` is not touched: the auth refusal is carried by the 401 status plus the string passthrough, and the alarm test fails loudly if `format_response` ever gains an implicit `auth` signal.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in my own test] Over-broad no-secret rendering assertion**
- **Found during:** Task 2
- **Issue:** My first draft also rendered `{"auth": secret}` and asserted the secret absent. That dict deliberately holds the secret as data, so `format_response` correctly echoes it; the plan's behavior covers only the pair built from `auth_failure(SECRET)`.
- **Fix:** Removed that third rendering case; the test now renders the string and dict forms of the real `auth_failure(secret)` body.
- **Files modified:** tests/unit/test_format_response.py
- **Commit:** 35b978f (the failing version was never committed)

**2. [Rule 2 - Missing critical functionality] `load_secret` tolerates unusable search entries**
- **Found during:** Task 1
- **Issue:** The plan's `os.path.join(dir, ...)` raises `TypeError` for a non-path entry, which would break "never raises".
- **Fix:** The path build and `lexists` check are wrapped in `except (TypeError, ValueError): continue`; covered by `test_secret_never_raises_for_hostile_directory_arguments`.
- **Files modified:** bridge.py, tests/unit/test_bridge_secret_client.py
- **Commit:** 1e2f6b2

**Total deviations:** 2 auto-fixed (1 Rule 1 in my own draft, 1 Rule 2). **Impact:** none on scope; additive and inside the plan's files.

## Issues Encountered

`git commit` printed the known harmless `failed to delete '.git/worktrees/hot-cirrus'` error after both commits; both commits exist (verified with `git log`). Git also warns that LF will become CRLF on the working copy; the committed content was written LF and `bridge.py` stays LF-only on disk.

## Known Stubs

None. `load_secret` and `with_envelope` are intentionally uncalled until Phase 5 (D-10); that is pinned by `test_inert_no_production_call_sites`, not a stub.

## Threat Flags

None. `load_secret` adds a read-only local file access inside the MCP server process; it is covered by T-03-14 (never logs, never raises) and is not reachable from any request path.

## Next Phase Readiness

Ready for 03-04. Whoever changes `trust.secret_from_bytes` must change `bridge._secret_from_bytes` in the same commit; the parity table will fail otherwise. SEC-03's question whether Phase 5's `/status/` must distinguish the three 401 reasons is a Phase 5 rendering question and remains flagged.

## Self-Check: PASSED

- FOUND: tests/unit/test_bridge_secret_client.py, bridge.py (`def load_secret(`, `def _secret_from_bytes(`), tests/unit/test_format_response.py (`Error: 401 - `, `from revit_mcp.trust import auth_failure`)
- FOUND commits: 1e2f6b2, 35b978f
- `git rev-list --count cc90256..HEAD` was 2 at SUMMARY time, matching `actuals.commits`
