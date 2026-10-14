---
phase: 01-serialization-and-configurable-addressing
verified: 2026-10-14T10:00:00Z
status: human_needed
score: 6/6 must-haves verified
covered_files:
  - ".planning/REQUIREMENTS.md"
  - ".planning/ROADMAP.md"
  - "CLAUDE.md"
  - "README.md"
  - "bridge.py"
  - "deploy/README.md"
  - "deploy/USER-GUIDE.md"
  - "deploy/build-payload.cmd"
  - "main.py"
  - "scripts/probe_handler_overlap.py"
  - "tests/test_two_instance_targets.py"
  - "tests/unit/test_bridge_serialization.py"
  - "tests/unit/test_payload_ships_root_modules.py"
  - "tests/unit/test_probe_handler_overlap.py"
  - "tests/unit/test_serialization_scope_docs.py"
  - "tests/unit/test_status_target.py"
  - "tools/process_tools.py"
  - "tools/status_tools.py"
covered_digest: "v1:sha256:de8b1f3ef7fe3ff92ca9f0f2dbd8bd2effb9a93b25fc2261a238d2910a2f2db0"
behavior_unverified: 0
overrides_applied: 0
re_verification: false
human_verification:
  - test: "Repeat the overlap probe on the fleet's pyRevit 6.5.5 (scripts/probe_handler_overlap.py --port 48884) against one live Revit"
    expected: "Same verdicts as 6.5.3 (cross-wired-mutation, cross-wired-read, /status/ answering in about 0.01-0.02 s while the handler is busy). This confirms that locking everything except /status/ (d27-b) is still required, and that /status/ is still safe to leave unlocked, on the version users run"
    why_human: "Needs a live Revit with pyRevit 6.5.5. The 01-04 bench ran 6.5.3 only (RESEARCH assumption A2). Unit tests cannot observe pyRevit's shared request handler. The code and the docs state this honestly (bridge.py docstring: 'pyRevit 6.5.5 was not benched')"
  - test: "Measure GET /model_info/ under overlap with a held mutation (extend or run scripts/probe_handler_overlap.py against /model_info/) on a live Revit"
    expected: "A recorded verdict. Until it is measured, /model_info/ stays locked; only a measurement plus a user decision may add it to UNLOCKED_GET"
    why_human: "Live Revit needed; 01-04 did not measure /model_info/. Locking it is the conservative state and is what the code does (UNLOCKED_GET == {'status'})"
  - test: "Simultaneous launch of two Revit instances (both started at once, no stagger), then Get-NetTCPConnection -LocalPort 48884,48885 -State Listen and /routes/sisters"
    expected: "Record which ports each PID received. Confirms or corrects the docs' wording that a simultaneous start 'may collide on 48884' (documented as a possible collision, not a measured result). Per ROADMAP SC5, if a staggered start put both on 48884 the phase would not be accepted; the staggered case was measured fine, the simultaneous case was not run (01-04 Step 8)"
    why_human: "Needs a workstation with two Revit launches; no code can show this"
  - test: "IDENT-05 / SC5 beyond two Revit 2024.3.30 instances: run tests/test_two_instance_targets.py (--ports 48884,48885) on a cross-version pair (for example Revit 2024 plus 2027), and on pyRevit 6.5.5"
    expected: "TWO_INSTANCE_OK; each entry reports its own host:port and its own document_title; one listener per port with different PIDs"
    why_human: "The only live evidence is one pair of Revit 2024.3.30 instances on pyRevit 6.5.3 (recorded by a human in 01-04-SUMMARY.md Bench record). I did not re-run it. Acceptance beyond that same-version pair rests on a human (01-08-SUMMARY backstop item)"
  - test: "Read deploy/USER-GUIDE.md (Russian) for over-claims about serialization or two-Revit use"
    expected: "No sentence promises that sessions or Revit instances are protected from each other; the cross-session warning (lines ~423-433) reads correctly to an engineer"
    why_human: "The over-claim scan in tests/unit/test_serialization_scope_docs.py is English-only; a differently worded Russian over-claim is not machine-detected (01-07-SUMMARY coverage D5)"
---

# Phase 1: Serialization and configurable addressing - Verification Report

**Phase Goal:** Calls issued through this MCP server no longer reach pyRevit's shared request handler in parallel - every call except `/status/` waits its turn (d27-b) - and the server's target port is a deployment setting instead of a hardcoded constant. One MCP server process targets one Revit instance, users share one `revit` entry, and choosing a Revit per call is Phase 2. Every route still operates on the targeted instance's active document.
**Verified:** 2026-10-14
**Status:** human_needed
**Re-verification:** No - initial verification (no prior VERIFICATION.md existed)

The code goal is achieved in the codebase. No truth failed. Status is `human_needed` only because several statements can be confirmed solely with a live Revit (pyRevit 6.5.5, `/model_info/` overlap, simultaneous launch, a cross-version pair). The code and docs state each of these as unmeasured, which is what the verification brief required.

## Goal Achievement

### Observable Truths (ROADMAP success criteria, as revised by plan 01-08)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Two mutating calls back-to-back never open overlapping Revit transactions from this server; a concurrent test holds one call and confirms the second waits | VERIFIED | `bridge._serialized` (bridge.py:312-353) wraps every non-`/status/` call in `async with _get_lock()`. My own concurrent run through `bridge.revit_post/revit_get` over `httpx.MockTransport` (POST, GET, POST, GET /model_info/, GET /status/ fired together) gave `maxactive 1`. Unit tests `test_second_post_waits_for_the_first`, `test_mixed_get_post_queue_in_arrival_order`, `test_releases_queued_posts_in_arrival_order` pass |
| SC2 | `/status/` returns promptly while another call holds the lock; every other call, reads included, waits (d27-b); verified with a concurrent test | VERIFIED | `UNLOCKED_GET = frozenset({"status"})` (bridge.py:218); `_is_locked` returns False only for GET with route key `status` (bridge.py:230-240). My run: with a POST holding the lock, `GET /status/` returned in 0.0 s; `GET /list_levels/` and `GET /model_info/` waited. Tool-layer tracer `test_d27b_tool_path_model_info_waits_status_does_not`, `test_unlocked_is_exactly_get_status`, `test_unlocked_every_tool_endpoint_except_status_is_locked` (drift scan, floor of 40 endpoints) pass. `READ_ONLY_POST` is gone from bridge.py. `revit_image` is routed through `_serialized` (bridge.py:163-181). The claim that `/status/` is safe on pyRevit's HTTP thread rests on the 6.5.3 bench; see human items |
| SC3 | A mutating call that times out, throws or is cancelled releases the lock immediately; verified by forcing an exception and re-acquiring | VERIFIED | `async with` is the only lock path, and transport errors are returned, not raised (bridge.py:331-344). My run: a handler that raised `ReadError` returned the "outcome UNKNOWN" text, and the next POST was acquired and answered. Unit tests `test_releases_after_handler_exception`, `test_releases_after_post_send_timeout`, `test_releases_after_cancellation_of_holder`, `test_releases_cancelled_waiter_is_never_sent` pass. `CancelledError` is not caught in bridge.py |
| SC4 | Waiting in the queue does not shrink a call's own request timeout; a wait beyond its bound returns an explicit "not sent to Revit" error | VERIFIED | `asyncio.timeout(timeout)` bounds acquisition only; `budget.reschedule(None)` is called once the lock is held, so `send()` gets the whole timeout (bridge.py:331-336). My run: with the lock held by a slow call, `revit_post(timeout=0.1)` returned `Error: Revit queue busy ... The request was NOT sent to Revit: nothing was sent and nothing was changed.` Tests `test_budget_not_shrunk_by_queue_wait`, `test_get_budget_not_shrunk_by_queue_wait`, `test_queue_bound_returns_not_sent_without_sending`, `test_get_queue_bound_returns_not_sent`, `test_image_queue_bound_returns_not_sent` pass |
| SC5 | `REVIT_PORT` changes the port this server talks to; live with two staggered Revit instances: one listener each on 48884/48885, different PIDs, and two stdio server processes (`tests/test_two_instance_targets.py`) each get their own `host:port` and `document_title` from `get_revit_status`; staggered start must not put both on 48884 | VERIFIED (scope: one same-version pair; live part recorded by a human, not re-run by me) | Code: `REVIT_PORT = _resolve_port(os.environ.get("REVIT_PORT"))` (bridge.py:109); I ran `REVIT_PORT=48885` and got `BASE_URL http://localhost:48885/revit_mcp`, `revit_target localhost:48885`; `REVIT_PORT=abc` and `REVIT_PORT=` both exit 2 on stderr and nothing on stdout. `tools/status_tools.py:48` appends `MCP target: host:port` to every outcome, covered by `tests/unit/test_status_target.py`. Harness `tests/test_two_instance_targets.py` exists. Live: `01-04-SUMMARY.md` Bench record shows `/routes/sisters` with PIDs 11088->48884 and 35780->48885, one listener each, and `TWO_INSTANCE_OK` with distinct documents, from a staggered start (D-18 not triggered). Not covered: cross-version pair, pyRevit 6.5.5, simultaneous launch (human items) |
| SC6 | The documented scope of serialization is explicit and honest: one server process only; not a guarantee against another MCP server process, curl or `/execute_code/`; docs say overlapping sessions can still cross-wire until backlog 999.1 (d27-c) | VERIFIED | Same three sentences are present in `bridge.py` docstring, `CLAUDE.md:~185`, `README.md:144-150`, `deploy/README.md:~202`, plus a Russian cross-session warning in `deploy/USER-GUIDE.md:429-433`. Backlog item 999.1 exists in ROADMAP.md and as a directory under `.planning/phases/`. `tests/unit/test_serialization_scope_docs.py` (8 tests) pins the sentences, scans for over-claims, and rejects a two-entry (`revit-a`/`revit-b`) example in user docs. All pass |

**Score:** 6/6 truths verified (0 present-but-behavior-unverified). Behavioral claims were exercised by my own concurrent run plus the passing named tests, not by symbol presence.

### Plan must_haves: prohibitions and backstops

| Item | Status | Evidence |
|------|--------|----------|
| Prohibition (01-06): MUST NOT exempt any route other than GET `/status/` from the lock | VERIFIED (test-tier, wired) | `test_unlocked_is_exactly_get_status` and the endpoint drift scan fail if `UNLOCKED_GET` widens; `NEVER_UNLOCKED = {execute_code, open_model, save_document}` is checked first (bridge.py:222, 238) |
| Prohibition (01-06): MUST NOT misword a waiting or failed call | VERIFIED for the cases the plan names (test-tier), with one edge exception see WR-01 | `test_wait_message_does_not_name_the_holder_a_mutation`, `test_get_post_send_failure_is_not_outcome_unknown`; queue-busy text says NOT sent. A POST that returns a 200 with an unparseable body is not labelled UNKNOWN (see Warnings) |
| Backstop (01-06): on pyRevit 6.5.5 overlap cross-wires like 6.5.3 | ? UNCERTAIN, routed to human verification | Needs live Revit; not claimed anywhere as measured |
| Backstop (01-06): `/model_info/` overlap measured before anyone unlocks it | ? UNCERTAIN, routed to human verification | Stays locked, as coded and documented |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bridge.py` | One HTTP exit, one lock path, strict `REVIT_PORT`, `UNLOCKED_GET`, `_serialized`, locked `revit_image` | VERIFIED | 367 lines, substantive, wired: `main.py:4` imports `revit_get, revit_post, revit_image` from it and injects them via `register_tools` (main.py:28). No `httpx`/`requests` call exists in `tools/` or `main.py`, so no path bypasses the lock |
| `main.py` | Wiring only; refuses to start on bad `REVIT_PORT` | VERIFIED | `except ValueError` writes stderr and `sys.exit(2)`; observed exit 2, empty stdout |
| `tools/status_tools.py` | `get_revit_status` names `MCP target` in every outcome | VERIFIED | line 25-48; `test_status_target.py` passes |
| `tools/process_tools.py` | `start_revit` docstring true for second-port entry | VERIFIED | docstring at lines 188-194 describes `REVIT_PORT`/48885 behaviour |
| `deploy/build-payload.cmd` | Payload ships `bridge.py` | VERIFIED | line 110 `copy /y "%REPO%\bridge.py" "%BUILD%\app\"`; `test_payload_ships_root_modules.py` passes |
| `tests/test_two_instance_targets.py` | Two-stdio-entry harness | VERIFIED (exists, substantive); live run not repeated | see IN-04 in 01-REVIEW.md about a missing failure sentinel on a crashing entry |
| `scripts/probe_handler_overlap.py` + `tests/unit/test_probe_handler_overlap.py` | D-23 probe with unit-tested classifier | VERIFIED, with caveat WR-02 | classifier does not flag non-200 statuses |
| `tests/unit/test_bridge_serialization.py` | Lock, wait, budget, port tests; tool-path tracer; drift scan | VERIFIED | 57 tests in this file pass inside the 416 total |
| `tests/unit/test_serialization_scope_docs.py` | Doc pins | VERIFIED | 8 tests pass |
| `README.md`, `CLAUDE.md`, `deploy/README.md`, `deploy/USER-GUIDE.md` | Honest scope + `REVIT_PORT` as deployment setting | VERIFIED | content checked by grep and by the doc-pin tests |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `main.py` | `bridge.py` | `from bridge import revit_get, revit_post, revit_image` | WIRED | main.py:4 |
| `main.py` | all tool registrars | `register_tools(mcp, revit_get, revit_post, revit_image)` | WIRED | main.py:28; 24 domains registered (init-latency run) |
| `bridge.revit_get` / `revit_post` | `_revit_call` -> `_serialized` -> `_get_lock()` | `async with` | WIRED | bridge.py:148-160, 356-366 |
| `bridge.revit_image` | `_serialized` | `fetch()` closure | WIRED | bridge.py:163-181 |
| `bridge.revit_get.revit_target` | `tools/status_tools.py` | `getattr(revit_get, "revit_target", None)` | WIRED | bridge.py:155; status_tools.py:~45 |
| `bridge.py` | payload | `build-payload.cmd:110` | WIRED | guard test passes |
| `REVIT_PORT` env | `BASE_URL` / httpx client base | `_resolve_port` -> `BASE_URL` -> `_get_client` | WIRED | observed `http://localhost:48885/revit_mcp` |

### Data-Flow Trace (Level 4)

Not applicable in the UI sense. The one dynamic value the phase renders is the `MCP target` line: its source is `REVIT_HOST`/`REVIT_PORT` read from the environment at import (`bridge.REVIT_TARGET`), not a literal. FLOWING.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full unit suite | `uv run pytest tests/unit` | 416 passed, 3 skipped | PASS |
| Cold-start gate | `uv run python tests/test_init_latency.py` | `INIT_LATENCY_S=0.777` (< 2.0) | PASS |
| Concurrency (SC1, SC2) over a mock transport | own script `chk.py`: POST, GET, POST, GET /model_info/, GET /status/ together | `maxactive 1`; `/status/` answered in 0.0 s while a POST held the lock | PASS |
| Lock release after exception (SC3) | same script, handler raising `ReadError` then a fresh POST | "outcome UNKNOWN" text returned, next POST answered | PASS |
| Bounded wait (SC4) | same script, 0.1 s call queued behind a slow call | `Error: Revit queue busy ... NOT sent to Revit` | PASS |
| `REVIT_PORT=48885` | `import bridge` | `http://localhost:48885/revit_mcp`, target `localhost:48885` | PASS |
| `REVIT_PORT=abc` / empty | `python main.py` | exit 2, message on stderr, stdout empty | PASS |

### Probe Execution

Step 7c: SKIPPED for the conventional `scripts/*/tests/probe-*.sh` pattern (none exist; the phase's probe is `scripts/probe_handler_overlap.py`, a live-Revit experiment that sends mutating requests, which this verifier must not run). Its classifier is covered by 8 unit tests; the live run is a human item.

### Requirements Coverage

Requirement IDs from PLAN frontmatter: 01-01 [SER-01, SER-02, IDENT-05]; 01-02 [SER-02, SER-03, SER-04]; 01-03 [IDENT-05]; 01-04 [IDENT-05, SER-01, SER-02]; 01-06 [SER-01..SER-04]; 01-07 [SER-05, SER-02, IDENT-05]; 01-08 [SER-02, SER-05, IDENT-05]. Union = SER-01..05 and IDENT-05, which equals the six IDs requested. REQUIREMENTS.md maps exactly these six to Phase 1; no other ID maps to Phase 1. No orphaned requirements.

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SER-01 | 01-01, 01-04, 01-06 | Mutating calls of this server are not sent to Revit in parallel | SATISFIED | SC1; every non-`/status/` call is locked, a strictly stronger rule than "mutating calls" |
| SER-02 | 01-01, 01-02, 01-04, 01-06, 01-07, 01-08 | A held queue does not block `/status/`; every other call, reads included, waits (d27-b) | SATISFIED | SC2. REQUIREMENTS.md SER-02 text was narrowed by 01-08 to match; code matches the narrowed text |
| SER-03 | 01-02, 01-06 | Exception, timeout or cancellation inside the locked region releases the queue | SATISFIED | SC3 |
| SER-04 | 01-02, 01-06 | Queue wait does not shrink a call's own time budget | SATISFIED | SC4 |
| SER-05 | 01-07, 01-08 | Serialization scope documented honestly | SATISFIED | SC6; five docs plus 8 pin tests. Russian user-guide over-claim review is a human item |
| IDENT-05 | 01-01, 01-03, 01-04, 01-07, 01-08 | Pyrevit Routes port configurable via `REVIT_PORT` | SATISFIED (scoped) | SC5. Strict parse, refuse-to-start and target naming verified here; live two-instance evidence is one same-version pair on pyRevit 6.5.3 (human items above) |

Traceability table in REQUIREMENTS.md already shows all six as Complete with `[x]` boxes, consistent with this verification. ROADMAP Phase 1 header still shows `[ ]` and "In Progress"; that bookkeeping is the orchestrator's to update after acceptance.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (all files modified by the phase) | - | `TBD`/`FIXME`/`XXX` debt markers | none found | grep over bridge.py, test files, probe, status_tools returned nothing |
| `bridge.py` | 207, 352 | A POST that was sent but whose 200 response is not JSON is returned as bare `Error: Expecting value...` instead of the "outcome UNKNOWN" wording | Warning | I reproduced it (`MockTransport` answering 200 `notjson`). Contradicts the 01-02 key decision ("anything not provably pre-send is reported as outcome UNKNOWN"). Not covered by any success criterion; edge case because Routes always answers JSON. Matches 01-REVIEW WR-01 |
| `scripts/probe_handler_overlap.py` | 87-118 | `classify_phase` can return `serialized` for non-200 answers | Warning | The probe could print a false `D27_TRIGGER=no`. Does not affect shipped behavior; matches 01-REVIEW WR-02 |
| `bridge.py` | 108-111 | `REVIT_HOST` is unvalidated (empty or unbracketed IPv6 gives a malformed `BASE_URL`) | Warning | Not in any requirement (only the port is); matches 01-REVIEW WR-03 |
| `bridge.py` | 57-58 | Docstring says "The lock is never held while waiting for Revit", which is inaccurate | Info | Wording only; 01-REVIEW IN-01 |
| docs | - | README components table still says IronPython 2.7; internal IDs (`d27-c`) appear in user-facing docs | Info | 01-REVIEW IN-04; the `d27-c` sentence is pinned verbatim by tests |

None of these is a blocker. The three warnings are the same three that 01-REVIEW.md reports (0 critical, 3 warnings); I independently reproduced WR-01 and read the code for WR-02 and WR-03.

### Human Verification Required

See the `human_verification` list in the frontmatter (five items):

1. **pyRevit 6.5.5 overlap probe** - confirm d27-b is still required and `/status/` still bypasses the shared handler on the fleet version.
2. **`/model_info/` overlap measurement** - until measured it stays locked (that is the coded and documented state).
3. **Simultaneous launch of two Revit instances** - record the ports each PID gets; the docs call a collision "possible", not measured.
4. **IDENT-05 / SC5 beyond two Revit 2024.3.30 instances** - cross-version pair and pyRevit 6.5.5 with `tests/test_two_instance_targets.py`.
5. **Russian read-through of `deploy/USER-GUIDE.md`** for over-claims the English scan cannot see.

### Gaps Summary

No gaps. All six success criteria are met in the codebase, all six requirement IDs are accounted for and satisfied, and the lock-coverage prohibition is enforced by tests that fail if `UNLOCKED_GET` is widened or a tool endpoint is added unlocked. Items I could not confirm are live-Revit-only, and the code and docs describe them as unmeasured rather than as guarantees. Three review warnings (WR-01 UNKNOWN wording for an unparseable 200, WR-02 probe classifier on non-200, WR-03 `REVIT_HOST` validation) remain as advisory follow-ups; none blocks Phase 1 acceptance. WR-01 is the one worth fixing before Phase 4 builds honest outcomes on this transport.

---

_Verified: 2026-10-14_
_Verifier: Claude (gsd-verifier)_
