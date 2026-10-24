---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 07
subsystem: security
tags: [status, diagnostics, shared-secret, fingerprint, integrity, bind, ironpython3, tdd]

requires:
  - phase: 05-live-secret-gate-and-integrity-enforcement
    provides: "05-01 revit_mcp/security.py load-time state (_STATE with secret and integrity) and gate_support.py"
  - phase: 05-live-secret-gate-and-integrity-enforcement
    provides: "05-16 bridge._secret() lazy memoized loader and the startup security.initialize call"
provides:
  - "trust.secret_fingerprint(secret): 8 lowercase hex of SHA-256 for a configured secret, else None"
  - "trust.security_alerts(block): plain-word alerts for verified_mismatch (423), exposed bind (not blocked) and an unconfigured secret (401)"
  - "security.status_block(port, listeners=None) and security._dotnet_listeners(): secret / integrity / bind block"
  - "/status/ 200 and 503 replies carry secret, integrity, bind, health and (when non-empty) security_alerts"
  - "D-07 wording in the three 401 hints"
  - "bridge.secret_fingerprint, bridge.loaded_secret_fingerprint and the seam revit_get.secret_fingerprint"
  - "get_revit_status 'Shared secret:' comparison line (same / DIFFER / extension none / server none / not reported)"
affects: [05-06, 05-10, 05-11, 05-12]

plan_head_before: 026d33292894b14eb6ba5ba93f8446753edd41e9
actuals:
  tokens: 8500
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Open /status/ discloses only configured plus an 8-hex SHA-256 fingerprint; leak rows scan payload repr, hints and tool text"
    - "Security block built in a guarded lazy relative import inside status.py's try; an ImportError leaves the block absent"
    - "Tool reads the transport fingerprint with getattr(revit_get, 'secret_fingerprint', None), never an import of bridge"
    - "bridge fingerprint duplicates the trust rule on purpose; a parity table pins the two together"

key-files:
  created:
    - tests/unit/test_phase5_status_diagnostics.py
  modified:
    - revit_mcp/trust.py
    - revit_mcp/security.py
    - revit_mcp/status.py
    - tools/status_tools.py
    - bridge.py
    - tests/unit/test_trust_secret.py
    - tests/unit/test_bridge_secret_client.py
    - tests/unit/test_status_target.py
    - tests/unit/test_security_state.py
    - tests/unit/test_trust_dialect.py

key-decisions:
  - "Health degrades for verified_mismatch, an exposed bind and a missing extension secret; unverifiable integrity (any reason) is reported but never degrades or blocks"
  - "The 503 branch gains health ('degraded' for registry, identity or security alerts, else 'healthy') and keeps error 'No active Revit document'; no top-level error is added for a degraded 200"
  - "revit_get.secret_fingerprint is assigned at the end of the bridge secret section, not beside revit_target, because loaded_secret_fingerprint depends on _secret() defined there"
  - "When the extension has no secret the comparison line names the extension first, whatever this server holds"

patterns-established:
  - "status.py tests load the real file under a synthetic package whose __path__ is the real revit_mcp directory, with real security, trust, integrity and textutils and fake pyrevit, utils, identity and registry"

requirements-completed: [SEC-03, SEC-05, SEC-06, SEC-07, SEC-08, INTG-05, INTG-07]

duration: 13min
completed: 2026-10-24
status: complete
---

# Phase 5 Plan 07: Status diagnostics Summary

**`/status/` now reports whether the extension holds a secret (8-hex SHA-256 fingerprint only), the load-time integrity verdict naming differing files, and the Routes bind; `get_revit_status` compares the fingerprints of both halves in one line and the 401 hints name the D-07 actions, with the secret itself appearing nowhere.**

## Performance

- **Duration:** about 13 min
- **Completed:** 2026-10-24
- **Tasks:** 3 (Task 1 tracer, Tasks 2 and 3 TDD)
- **Files:** 1 created, 10 modified

## Accomplishments

- `trust.secret_fingerprint` applies the same "configured" rule as `check_secret` (text or bytes of at least 16 once stripped) and returns `sha256(utf-8)[:8]`; never raises.
- `security.status_block(port, listeners=None)` returns `{secret: {configured, fingerprint}, integrity, bind}`; the default `_dotnet_listeners()` imports `System.Net.NetworkInformation` inside the function and yields `None` on any failure (which reads as `unknown`, always the case under CPython). Never raises; an uninitialized state reports `unverifiable/read_error` and `configured: false`.
- `revit_mcp/status.py` builds the block in a guarded sub-block (lazy `from .security import status_block` and `from .trust import security_alerts`), adds it to the 200 and 503 replies, and sets `health` to `degraded` when the registry, an identity error or a security alert says so. `revit_status(verbose=None)` signature and the no-`uiapp` rule are unchanged; with the security module unimportable `/status/` still answers without the block.
- `trust.security_alerts` yields one sentence each for a verified mismatch (files named, 423), an exposed bind (the secret is the only barrier; mutations not blocked) and an unconfigured secret (401 `server_not_configured`); unverifiable integrity, whatever its reason, never alerts.
- `_AUTH_HINTS` rewritten to the D-07 actions (missing: Update RevitMCP or sign out of Windows, restart the assistant session; mismatch: different builds, same build, call `get_revit_status`; server_not_configured: reinstall the extension and fully restart Revit). Dict keys and the `error/auth/hint` body shape are unchanged; no hint holds a secret or an 8-hex word.
- `bridge.secret_fingerprint` (parity pinned against trust over ASCII, Cyrillic, None, empty, too-short and bytes), `loaded_secret_fingerprint()` and the seam `revit_get.secret_fingerprint`.
- `tools/status_tools.py` `_secret_line`: builds the comparison from `_body_of(response)` (dict or the JSON of an "Error: 503 - ..." text) and the transport seam; inserted after the formatted status and before "MCP target:"; no line at all when neither side reports, so every existing exact-text row is unchanged. The `get_revit_status` docstring now explains the secret line, that the fingerprint is not the secret, that `integrity` unverifiable is not damage, and the `bind` values.
- `tests/unit/test_phase5_status_diagnostics.py` (34 rows): tracer, bind table, status_block variants, alert rows, health rule, 503 branch, ImportError row, signature/uiapp pin, hint and leak rows, end-to-end comparison lines.

## Task Commits

1. **Task 1 (tracer): secret fingerprint on /status/ and the "same secret" line** - `035b7cc` (feat)
2. **Task 2: bind, health rule, alerts, 503 block, D-07 hints** - `e35475e` (feat)
3. **Task 3: bridge fingerprint seam and every comparison-line case** - `66a1dd1` (feat)

Tracer feedback gate: auto/default mode with an automated-only verify; the tracer verify, the `http_thread` inventory pin and the full unit suite were green after the commit, so expansion proceeded.

## TDD Gate Compliance

Tasks 2 and 3 were driven RED first (the new rows were run and seen failing: 23 failures for Task 2, 17 for Task 3, before any implementation) and then made green. Each task is committed as one test-plus-implementation commit, keeping the full unit suite green at every commit, as the plan's "green before every commit" rule asks; there is no separate RED commit. The Task 1 tracer was likewise seen failing before the GREEN change.

## Verification

- `uv run pytest tests/unit -q`: **5590 passed, 3 skipped** (baseline 5533 passed, 3 skipped), after Task 3.
- Task 1: `test_phase5_status_diagnostics`, `test_status_target`, `test_process_identity`, `test_parallel_installation` green; `-k http_thread` 2 passed; the fingerprint one-liner printed `8 True None None`.
- Task 2: `test_phase5_status_diagnostics` 33 passed (at least 15 required); `trust.auth_failure('missing')` one-liner printed `True True`.
- Task 3: `-k secret` in `test_status_target.py` 11 passed (at least 7); `-k fingerprint` in `test_bridge_secret_client.py` 9 passed (at least 3); `uv run python tests/test_init_latency.py` printed `INIT_LATENCY_S=1.414` (below 2.0).
- No live Revit step was run, and Revit/pyRevit were not touched; the `System.Net` listener adapter and `revit_mcp/` edits are therefore verified only through CPython tests with stand-ins.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Two structural import allow-lists rejected the .NET adapter**
- **Found during:** Task 1 (full unit suite)
- **Issue:** `test_security_state.py::test_the_gate_source_adds_no_compare_primitive_of_its_own` and `test_trust_dialect.py::test_dialect_security_imports_only_os_and_the_helper_siblings` pinned security.py's imports to `{os, pyrevit}`, so the plan-mandated function-level `System.Net.NetworkInformation` import in `_dotnet_listeners` failed them.
- **Fix:** each allow-list gains `System.Net.NetworkInformation` with a comment naming the adapter; no other assertion was loosened (still no hashlib, hmac or secrets in security.py).
- **Files modified:** tests/unit/test_security_state.py, tests/unit/test_trust_dialect.py
- **Commit:** 035b7cc

**2. [Rule 3 - Blocking] Seam assignment placed after the secret section, not beside revit_target**
- **Found during:** Task 3
- **Issue:** `revit_get.secret_fingerprint = loaded_secret_fingerprint` beside `revit_target` (bridge.py line ~797) would raise NameError at import, since `loaded_secret_fingerprint` and `_secret()` are defined much later.
- **Fix:** assigned at the end of the secret section with a comment explaining the placement; the seam is the same object (a test pins identity).
- **Files modified:** bridge.py
- **Commit:** 66a1dd1

**3. [Environment] Stale zero-byte `.git/index.lock` removed**
- **Found during:** Task 1 commit
- **Issue:** a zero-byte lock from before this session blocked the first commit; no git process was running.
- **Fix:** removed the stale lock and re-ran the commit. `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` printed after every commit is a pre-existing stray worktree directory, unrelated to this plan; the commits themselves succeeded.

**Total deviations:** 2 auto-fixed (Rule 3) plus 1 environment note. **Impact:** none on behavior or scope.

## Issues Encountered

- `tools/status_tools.py` is stored CRLF while the rest of the touched files are LF; edits to it were made preserving CRLF (no mixed endings).
- The `Shared secret:` line and the docstring wording are Claude's discretion per the plan; the live runner (05-11/05-12) pins the names `secret`, `integrity`, `bind`, `security_alerts`.

## Known Stubs

None.

## Threat Flags

None. The only new public surface is the planned `secret` / `integrity` / `bind` fields on the already-open `/status/`, limited to `configured`, the 8-hex fingerprint, file names and the bind verdict (T-05-27, T-05-31 mitigated; leak rows in all three tasks).

## Self-Check: PASSED

- Created: tests/unit/test_phase5_status_diagnostics.py found.
- Commits 035b7cc, e35475e, 66a1dd1 found in `git log`; `plan_head_before..HEAD` count is 3.
