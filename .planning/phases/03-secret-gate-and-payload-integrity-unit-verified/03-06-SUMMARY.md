---
phase: 03-secret-gate-and-payload-integrity-unit-verified
plan: 06
subsystem: trust-gate
tags: [bind-classification, loopback, ironpython3, engine-simulation, ast-guard, tokenize, dialect]

requires:
  - phase: 03-secret-gate-and-payload-integrity-unit-verified
    provides: "03-01 revit_mcp/trust.py secret gate, 03-04 revit_mcp/integrity.py reader, 03-05 hardening tables"
provides:
  - "trust.classify_listeners(endpoints, port): loopback_only / exposed / unknown from a plain (host, port) list, plus _as_port and _is_loopback_host"
  - "tests/unit/test_trust_listeners.py: 86 tests, the bind classification table"
  - "tests/unit/test_trust_dialect.py: 69 tests, IronPython 3 engine simulation (unicode builtin injected, textutils/trust/integrity reloaded), digest-type variants, 3.5+ construct guard with 30 known-bad and 18 known-good snippets, import allow-lists"
affects: [03-07 publish-extension.cmd, 03-08 live hashlib/import check, Phase 5 wiring (bind reporting on /status/, load-time integrity)]

plan_head_before: e95b5f78c9d803cb19406638d8088057f9397430
actuals:
  tokens: 8000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Engine simulation context manager: inject builtins.unicode = str, reload textutils then trust then integrity, restore the builtin and reload again in finally"
    - "Construct guard as ast.walk plus tokenize over module source, with a known-bad and a known-good snippet table so the guard itself is proven both ways"

key-files:
  created:
    - tests/unit/test_trust_listeners.py
    - tests/unit/test_trust_dialect.py
  modified:
    - revit_mcp/trust.py

key-decisions:
  - "A dotted-quad part with a leading zero is not loopback: some stacks read it as octal, so 0127.0.0.1 is not provably 127.0.0.1; it classifies as exposed"
  - "Non-IP text (a hostname, an empty string) is exposed, never loopback, as the plan records; a malformed or non-text entry makes the whole result unknown"
  - "The guard also flags a positional argument after *args (a 3.4 SyntaxError), beyond the plan's list; trust.py and integrity.py contain none"
  - "scripts/conventions.py is read-only here: the new guard lives only in test_trust_dialect.py (contrib-kit copy drift)"

patterns-established:
  - "Simulate the real engine, then compare to plain CPython: a CPython-green suite is not evidence for the IronPython half"

requirements-completed: [SEC-07, SEC-04, INTG-02]

coverage:
  - id: D1
    description: "classify_listeners returns loopback_only, exposed or unknown for the given port across loopback spellings, wildcards, LAN, hostname, mixed, other-port, text-port and hostile inputs, and never raises"
    requirement: "SEC-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_listeners.py#test_classification_table"
        status: pass
      - kind: unit
        ref: "tests/unit/test_trust_listeners.py#test_a_hostile_endpoint_never_raises"
        status: pass
    human_judgment: false
  - id: D2
    description: "Under a simulated pyRevit IronPython 3 engine (unicode aliased to str, three modules reloaded) trust keeps bytes/str aliases and the verdict, bytes-body envelope, integrity, check_integrity and listener results equal plain CPython; the engine is always restored"
    requirement: "SEC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_dialect.py#test_ironpython3_engine_results_equal_plain_cpython"
        status: pass
      - kind: unit
        ref: "tests/unit/test_trust_dialect.py#test_ironpython3_engine_leaves_cpython_modules_behind"
        status: pass
    human_judgment: false
  - id: D3
    description: "secret_matches gives the same verdicts when the digest arrives as bytearray or as a bytes subclass"
    requirement: "SEC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_dialect.py#test_digest_types_do_not_change_the_verdicts"
        status: pass
    human_judgment: false
  - id: D4
    description: "An AST and tokenize guard finds no construct IronPython 3.4 cannot load in trust.py or integrity.py, detects each in a known-bad snippet, and import allow-lists hold (trust: hashlib + .textutils; integrity: errno, hashlib, json, os + .trust)"
    requirement: "INTG-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_dialect.py#test_dialect_modules_use_no_construct_above_python34"
        status: pass
      - kind: unit
        ref: "tests/unit/test_trust_dialect.py#test_dialect_guard_finds_each_known_bad_construct"
        status: pass
    human_judgment: false
  - id: D5
    description: "trust.py and integrity.py actually load in the live pyRevit IPY342 engine (hashlib.sha256, relative imports, no FAILED-domain entry on /status/)"
    requirement: "INTG-02"
    verification: []
    human_judgment: true
    rationale: "Needs a live Revit with pyRevit; assigned to plan 03-08. The simulation here is evidence, not a live measurement"

duration: 5min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 06: Bind classifier and IronPython 3 proof Summary

**trust.classify_listeners names a Routes bind loopback_only, exposed or unknown by hand-parsed literal loopback forms, and trust.py plus integrity.py are proven in a simulated IronPython 3 engine (unicode builtin injected, modules reloaded) and fenced by an AST/tokenize guard against every 3.5+ construct.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-10-23T09:32:29Z
- **Completed:** 2026-10-23T09:37:30Z
- **Tasks:** 2
- **Files modified:** 3 (1 production, 2 new tests)

## Accomplishments

- `classify_listeners` is the pure half of SEC-07 (D-16): only listeners on the given port count; every host a literal loopback form (127.0.0.0/8, `::1`, the full-form IPv6 loopback, `::ffff:127.x`, bracketed, `%scope`) gives `loopback_only`; a wildcard, LAN, public, hostname or malformed address gives `exposed`; anything unreadable gives `unknown`. It never raises, blocks nothing and collects nothing; the .NET listener collection and `/status/` reporting remain Phase 5. No new import in trust.py (no `ipaddress`).
- The engine simulation reproduces the 2026-09-08 `unicode` incident setup: `builtins.unicode = str`, then `textutils`, `trust`, `integrity` reloaded in that order. The verdict table, the bytes-body envelope split under the IronPython 3 `json` stand-in, the integrity decision rows, `check_integrity` on a tmp tree (clean and tampered), the listener table and the gate/secret-file helpers all equal plain CPython and the tables' stated expectations. The context manager restores the builtin (or a previous value) and reloads again in `finally`, including when the body raises.
- Mutation check (scratch copy, deleted afterwards): putting the old `try: unicode / except NameError` probe back into textutils turns 8 of the new tests red (the injection, alias, equality, bytes-body and digest tests), so the simulation does detect the incident class.
- Digest-type variants (`bytearray`, a `bytes` subclass) from a fake `hashlib` leave `check_secret` / `secret_matches` unchanged.
- The construct guard flags f-strings, async/await, dict/iterable unpacking in displays, multiple `*`/`**` in a call, `@`/`@=`, annotations, walrus, positional-only parameters, underscore numeric literals, bytes `%`, `.hex()`, `os.scandir`, `subprocess.run` and imports from `conventions.PY3_ONLY_MODULES`; a Store-context `a, *b = x` is not flagged. trust.py and integrity.py are clean and their import allow-lists are pinned.

## Task Commits

1. **Task 1: classify_listeners** - `b43a578` (feat)
2. **Task 2: IronPython 3 engine simulation and 3.5+ construct guard** - `d868742` (test)

**Plan metadata:** recorded in the `docs(03-06)` commit that adds this file.

## Files Created/Modified

- `revit_mcp/trust.py` - added `BIND_LOOPBACK_ONLY/EXPOSED/UNKNOWN`, `_as_port`, `_is_loopback_ipv4`, `_is_loopback_host`, `classify_listeners` (IronPython 3.4 dialect, no new import)
- `tests/unit/test_trust_listeners.py` - 86-test bind classification table, host and port helper tables, hostile-input test
- `tests/unit/test_trust_dialect.py` - 69 tests: engine simulation, digest types, construct guard (30 bad, 18 good snippets), import allow-lists

## Decisions Made

- Leading-zero dotted-quad parts are not loopback (octal ambiguity), so `0127.0.0.1` and `127.0.0.01` classify as `exposed`.
- A malformed entry anywhere in the list makes the result `unknown` rather than ignoring the entry; a hostname or empty host is `exposed`.
- The guard additionally flags a positional argument after `*args`, a real 3.4 SyntaxError not in the plan's list.
- `scripts/conventions.py` untouched; the guard reuses `PY3_ONLY_MODULES` read-only and the test also asserts the repository's own `check_ironpython_dialect` is quiet on both modules.

## Deviations from Plan

None - plan executed exactly as written. The two additions (leading-zero rejection, positional-after-star flag, plus extra known-bad rows) are inside the plan's stated intent that only provable loopback passes and that the guard fence every sub-3.5 form.

**Total deviations:** 0
**Impact on plan:** none.

## Issues Encountered

- The Task 2 acceptance line `git status --porcelain -- scripts revit_mcp prints nothing` is not literally satisfiable on this permanently dirty tree: `scripts/intake_package.py`, `scripts/new_tool.py` and `scripts/probe_handler_overlap.py` carry other sessions' uncommitted edits. `scripts/conventions.py` and `revit_mcp/` are clean after the commits, and `git hash-object startup.py` is unchanged (`85de4833...`, the same value as before the plan; startup.py itself carries a foreign uncommitted edit that was left alone).
- `git commit` printed the known harmless `failed to delete '.git/worktrees/hot-cirrus'` error; both commits succeeded.

## Verification

- `uv run pytest tests/unit/test_trust_listeners.py -q`: 86 passed
- `uv run pytest tests/unit/test_trust_dialect.py -q`: 69 passed
- `uv run pytest tests/unit/test_trust_dialect.py tests/unit/test_textutils.py tests/unit/test_trust_secret.py tests/unit/test_trust_integrity.py -q` (dialect first): 249 passed
- `uv run pytest tests/unit -q`: 4602 passed, 3 skipped, 0 failed
- `BIND_OK` one-liner printed; `contains: BIND_LOOPBACK_ONLY = "loopback_only"` present in trust.py
- `graphify update .` not run (instructed not to run graphify; nothing under graphify-out was staged)

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or file access; the classifier is pure and takes data in.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 03-07 (publish script) and 03-08 (live check). The live IPY342 import of trust.py/integrity.py and `hashlib.sha256` under the routes engine remain a human-run gate in 03-08 (D5 above).
- Phase 5 owns collecting `GetActiveTcpListeners()` into (host, port) pairs, calling `classify_listeners`, and reporting `bind: exposed` / `health: degraded`.

## Self-Check: PASSED

- FOUND: tests/unit/test_trust_listeners.py, tests/unit/test_trust_dialect.py, revit_mcp/trust.py
- FOUND commits: b43a578, d868742
- `git rev-list --count e95b5f7..HEAD` = 2 before this SUMMARY commit

---
*Phase: 03-secret-gate-and-payload-integrity-unit-verified*
*Completed: 2026-10-23*
