---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "03"
subsystem: payload
tags: [payload, pywin32, mcp-1.30, embeddable-cpython, transports, deploy]
status: complete

requires:
  - phase: 07-repository-owned-mutation-safety-and-human-approval
    provides: "plan 07-01: mcp 1.30 SDK pin in uv.lock"
provides:
  - "_pywin32_paths(libs) in deploy/server.py, deploy/gate.py, deploy/warm.py: identical, silent, called before the first SDK import (D-24)"
  - "tests/unit/test_deploy_libpaths.py: AST parity, call placement, behaviour on a fake libs tree, empty edge, silent stdout"
  - "scripts/scratch_payload_gate.py: local scratch payload with pyRevit's CPython, warm.py + gate.py, SCRATCH_GATE_OK"
  - "tests/test_transports_smoke.py: 59 tools over streamable-http, sse and combined, TRANSPORTS_OK"
affects: [07-04, 07-05, 07-06, 07-07, 07-09, 07-10, 07-11, 07-14]

actuals:
  tokens: 5600         # chars/4 over the realized diff (22525 chars) of the two task commits
  tasks: 2
  commits: 2
plan_head_before: ed949035d3a1370954e3d72e9d37a79894f8ac4d
commits: 2

tech-stack:
  added: []
  patterns:
    - "payload entry points repair sys.path themselves (the embeddable CPython ignores .pth): same function text in three files, pinned by an AST parity test"
    - "scratch payload follows the real build: copy list parsed from deploy/build-payload.cmd, never a hand-kept list"

key-files:
  created: [tests/unit/test_deploy_libpaths.py, scripts/scratch_payload_gate.py, tests/test_transports_smoke.py]
  modified: [deploy/server.py, deploy/gate.py, deploy/warm.py]

key-decisions:
  - "The shim function is placed right after HERE and called right after the libs insert, before the SDK import or runpy, so no import order change is needed anywhere else"
  - "scratch_payload_gate.py only deletes its destination when it is absent, empty or carries its own marker file, on top of the repo/UNC refusal, so a mistyped --dest cannot wipe a real directory"
  - "Both new scripts are LF/UTF-8 without BOM; the three deploy files keep their existing LF working-copy endings"

requirements-completed: [SAFE-19]

coverage:
  - id: D1
    description: "The three payload entry points each define the same _pywin32_paths(libs), call it after libs is on sys.path and before the first mcp/httpx/anyio/tools import or runpy, add win32, win32/lib and pythonwin only when they exist, register pywin32_system32 as a DLL directory, write nothing to stdout, and add nothing on an empty libs tree"
    requirement: SAFE-19
    verification:
      - kind: unit
        ref: "tests/unit/test_deploy_libpaths.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "A payload layout built with the recipe of build-payload.cmd under pyRevit's embeddable CPython 3.12 imports mcp 1.30 and passes gate.py (INIT_LATENCY_S below 2.0, MANIFEST=ok (59 tools), GATE_OK)"
    requirement: SAFE-19
    verification:
      - kind: command
        ref: "uv run python scripts/scratch_payload_gate.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "streamable-http, sse and combined all serve the 59 tools"
    requirement: SAFE-19
    verification:
      - kind: command
        ref: "uv run python tests/test_transports_smoke.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "The shim covers the fleet-side situation on workstations other than this one (research assumption A8: the three paths suffice everywhere); warm.py at update time remains the fleet-side check"
    requirement: SAFE-19
    human_judgment: true
    rationale: "Proven only on this machine (pyRevit-Master CPY3123); other workstations are not reachable from the repository"
---

# Phase 7 Plan 03: Payload pywin32 shim and transport proof Summary

The fleet payload now starts with mcp 1.30: one identical, silent `_pywin32_paths(libs)` shim in `deploy/server.py`, `deploy/gate.py` and `deploy/warm.py` puts the pywin32 directories on `sys.path` and registers the DLL directory before the SDK is imported, proven offline, against a real scratch payload built with pyRevit's embeddable CPython, and over all three HTTP transports.

**Duration:** about 15 min | **Completed:** 2026-10-25 | **Tasks:** 2 | **Files:** 6 (3 created, 3 modified)

## Accomplishments

- `_pywin32_paths(libs)` is defined right after `HERE` and called right after `sys.path.insert(0, os.path.join(HERE, "libs"))` in the three entry points. It appends `libs\win32`, `libs\win32\lib` and `libs\pythonwin` when they are directories not already on `sys.path`, calls `os.add_dll_directory` on `libs\pywin32_system32` inside `try/except OSError`, writes nothing, and returns the directories it added.
- `tests/unit/test_deploy_libpaths.py` (15 tests) pins AST equality of the three copies, the call position (after the libs insert, before the first SDK import or `runpy`), the argument, the order and single registration on a fake libs tree, the DLL directory call, the empty edge, idempotence, a swallowed `OSError`, and silent stdout/stderr.
- Negative control: in the scratch payload, `import mcp.server.fastmcp` with only `libs` on `sys.path` fails with `No module named 'pywintypes'`; through the entry points it works. This reproduces the research finding and shows the shim is what fixes it.
- `scripts/scratch_payload_gate.py` builds the payload layout under `%TEMP%\revitmcp-phase7-scratch-payload` (recipe: `uv export` from uv.lock, `uv pip install --target` with pyRevit's CPY3123, copy list parsed from `deploy/build-payload.cmd`, `tools\` and `tests\` copied), runs `warm.py` and `gate.py` with `MCP_SECRET_FILE` removed, and prints `SCRATCH_GATE_OK`.
- `tests/test_transports_smoke.py` starts the server per mode on a free loopback port and lists the tools with the matching client.

## Verification output

`uv run python scripts/scratch_payload_gate.py` (final lines):

```
$ ...\CPY3123\python.exe ...\revitmcp-phase7-scratch-payload\app\warm.py
warm ok
$ ...\CPY3123\python.exe ...\revitmcp-phase7-scratch-payload\app\gate.py
SECRET=unchecked (MCP_SECRET_FILE not set)
INIT_LATENCY_S=1.094
SERVER=Revit MCP Server
TOOLS=59
MANIFEST=ok (59 tools)
GATE_OK
SCRATCH_GATE_OK
```

`uv run python tests/test_transports_smoke.py`:

```
TRANSPORT_OK streamable-http tools=59
TRANSPORT_OK sse tools=59
TRANSPORT_OK combined tools=59
TRANSPORTS_OK
```

`uv run pytest tests/unit -q`: `6413 passed, 3 skipped` (baseline 6398 plus the 15 new tests), run before each commit.

## Task Commits

1. Task 1 (shim and parity tests): `f776afe` fix(07-03)
2. Task 2 (scratch payload gate and transports smoke): `e5398e9` test(07-03)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Destination safety in the scratch gate**
- **Found during:** Task 2
- **Issue:** The plan refuses a destination inside the repository or on a UNC path, but the script also empties and recreates its destination, so a mistyped `--dest` pointing at an unrelated directory (or a directory containing the repository) would be deleted.
- **Fix:** It additionally refuses a destination that contains the repository and any existing non-empty directory that lacks the script's own marker file (`.revitmcp-scratch-payload`).
- **Files modified:** scripts/scratch_payload_gate.py
- **Commit:** e5398e9

**2. [Process] TDD RED not committed separately**
- **Found during:** Task 1
- **Issue:** The project rule is a green unit suite before every commit; a RED-only commit of the new test file would break it.
- **Fix:** The RED run (15 failed) was observed locally, then test and shim were committed together in one commit. The GREEN run showed 15 passed.
- **Commit:** f776afe

**Total deviations:** 1 auto-fixed (Rule 2), 1 process note. **Impact:** none on scope; the safety guard only narrows what the script may delete.

## Issues Encountered

- The three deploy files have LF endings in the working copy (the repo has `core.autocrlf=true`), unlike `tests/test_init_latency.py`, which is CRLF. The shim edit detected and preserved LF per file.

## Known Stubs

None.

## Threat Flags

None. The scratch gate writes only under the local temp directory (T-07-12 mitigated by the refusal rules), the shim is silent (T-07-13, capsys row), and T-07-11 is mitigated by the identical shims, the AST parity test and the scratch gate run.

## Next Phase Readiness

Ready for the next plan of the phase. The fleet-side check of research assumption A8 remains `warm.py` at update time on each workstation; only this machine was exercised here.

## Self-Check: PASSED

- FOUND: tests/unit/test_deploy_libpaths.py, scripts/scratch_payload_gate.py, tests/test_transports_smoke.py
- FOUND: commits f776afe and e5398e9
- `grep -c "def _pywin32_paths(libs):"` reports 1 for each of deploy/server.py, deploy/gate.py, deploy/warm.py
- `git rev-list --count ed94903..HEAD` before this commit: 2 (matches `commits: 2`)
