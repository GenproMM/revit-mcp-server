# Phase 1: Serialization and configurable addressing - Research

**Researched:** 2026-10-06
**Domain:** asyncio mutual exclusion at an HTTP bridge seam (CPython 3.11+/3.12, httpx 0.28, FastMCP in `mcp` 1.9.0) plus pyRevit Routes port assignment (IronPython side, read-only research)
**Confidence:** HIGH for the CPython design (prototyped and run this session); MEDIUM for the live two-instance port behaviour (source read, not yet exercised live); one MEDIUM-LOW finding about pyRevit internals that changes how honestly SER-01/SER-02 can be worded (see Summary, finding 1)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Roadmap order
- **D-01:** Old Phase 4 is split. IDENT-01..04 + AMBIG-01..04 + MDOC-01..05 become the new
  **Phase 2**, immediately after this phase (they depend only on `REVIT_PORT`). Live wiring of
  the secret gate and integrity check becomes its own later phase (new Phase 5). New order:
  1 Serialization+port → 2 Identity/ambiguity/multi-document → 3 Secret+integrity
  (unit-verified) → 4 Honest outcomes → 5 Live secret+integrity enforcement → 6 Audit log.
  Accepted cost: two live-Revit restart-cycle phases instead of one, and the `startup.py`
  chokepoint is touched twice. ROADMAP.md, REQUIREMENTS.md traceability and the phase
  directories are renumbered to match.

### Instance selection model
- **D-02:** One MCP server process = one Revit target. `REVIT_PORT` (alongside the existing
  `REVIT_HOST`) is read once at import and fixed for the life of the process. No runtime
  "switch target" tool and no per-call `port` argument — both were rejected (switch state
  would be shared across all clients under `stateless_http=True`; a per-call argument touches
  all 54 tools). — **Reversibility:** costly — moving to per-call instance addressing later
  means changing every tool signature/docstring and the client-config guidance.
- **D-03:** Working with two Revit instances in one assistant session = two MCP server entries
  in the client config (e.g. `revit-a` → 48884, `revit-b` → 48885). The client namespaces their
  tools, so one conversation can read both and compare. Documented with a concrete two-entry
  config example (README, `deploy/USER-GUIDE.md`).
- **D-04:** End-state addressing is "instance chosen by config entry, document chosen per call"
  (document-per-call arrives in Phase 2). Phase 1 must not build anything that blocks this —
  one target and one pooled `httpx.AsyncClient` per process stays.
- **D-05:** `REVIT_PORT` defaults to `48884`; parsing is a pure function (e.g. `_resolve_port(value)`)
  tested on its own. Invalid value (not an integer, or outside 1..65535) → the server refuses to
  start with a clear message on **stderr** (never stdout — stdio protocol). No silent fallback
  to 48884: a typo must never quietly land on a different Revit.
- **D-06:** `get_revit_status` reports the target `host:port` this MCP server entry talks to,
  added on the CPython side (no Revit-side change). PID/session token stay in Phase 2.

### Serialization lock
- **D-07:** One lock per target, keyed by `host:port`. Since one process has exactly one target
  (D-02), this is a single module-global `asyncio.Lock`, created lazily on first use — no
  `RevitTarget` registry is built. Not per document — Revit's API is single-threaded per process,
  so all documents of one instance share one queue.
- **D-08:** Every POST takes the lock by default; an explicit, unit-tested read-only allowlist
  opts out: `/ai_filter/`, `/material_quantities/`, `/clash_check/`,
  `/list_category_parameters/`, `/model_worksets/` (researcher to confirm each is truly
  read-only and whether any other POST belongs there). Fail-safe direction: a new tool that is
  not classified waits in the queue rather than racing. GET (`revit_get`) and `revit_image`
  never take the lock (SER-02). *Supersedes 2026-09-23 D-03 ("every POST, no classification").*
- **D-09:** `/execute_code/`, `/open_model/`, and `/save_document/` always take the lock and can
  never be allowlisted — arbitrary code can mutate anything, and open/save change session state
  that a concurrent mutation would otherwise hit. A unit test pins this.
- **D-10:** Only `async with lock:` — no manual `acquire`/`release`. Exceptions, httpx timeouts and
  `CancelledError` release the queue by construction (SER-03).

### Time budget in the queue
- **D-11:** A call's own request timeout (30 s default, or the `timeout=` passed) starts counting
  only after the lock is acquired (SER-04). Queue wait has its own bound, **equal to that call's
  own timeout**; worst case ≈ 2× the call timeout. No new env variable.
  *Supersedes 2026-09-23 D-06 (`REVIT_QUEUE_TIMEOUT`, 120 s).*
- **D-12:** Exceeding the queue-wait bound returns an explicit error, in the existing
  `_revit_call` `"Error: …"` string contract, stating the mutation was **NOT sent to Revit**
  (queue busy, "nothing was sent") — so the model knows nothing changed. It must never render as success.
- **D-13:** On client-side timeout after the request was sent, the lock is released immediately
  (SER-03) and the outcome is reported as **unknown** — "no response; the change may have been
  applied in Revit; verify before retrying" (e.g. `edit_family` already documents that Revit often
  completes after the client gives up). Holding the lock until Revit is idle was rejected
  (conflicts with SER-03; no idle signal exists).
- **D-14:** When a call has to wait, emit exactly one `await ctx.info(...)` ("waiting for the
  previous mutation to finish"), guarded by `if ctx:`, never `print()`. No queue position or ETA
  (Out of Scope).

### Honest scope (SER-05)
- **D-15:** Scope is stated in the `bridge.py` docstring, `CLAUDE.md` (Known sharp edges) and README:
  serialization covers calls issued through this one MCP server process only. It is not a guarantee
  against a second MCP entry pointed at the same port, another assistant session, curl, or
  `/execute_code/` called directly — harm reduction, not a correctness guarantee.

### Live acceptance
- **D-16:** Acceptance bench = two Revit instances started together (boot without a model, open
  through `/open_model/` — never a workshared model on the command line). Verify with
  `Get-NetTCPConnection -State Listen` that 48884 and 48885 each have exactly one listener with
  different PIDs — this also closes the research flag on pyRevit's port auto-increment
  (`.planning/research/STACK.md`, MEDIUM confidence). *Supersedes 2026-09-23 D-12.*
- **D-17:** Acceptance includes the user's cross-instance scenario: one assistant session with
  both `revit-a` and `revit-b` entries, a different model open in each; each entry's
  `get_revit_status` returns its own `host:port` and its own `document_title`.
- **D-18:** **Stop condition.** If the bench shows no auto-increment (both instances on 48884),
  Phase 1 is NOT accepted on criterion 5. Stop and bring the finding back to the user as a decision
  (e.g. forcing a per-instance port from `startup.py`, or PID-based addressing) — the
  one-server-per-port model cannot serve the user's scenario in that case. Do not paper over it by
  accepting on a single Revit. — **Reversibility:** one-way — if this triggers, D-02/D-03 have to
  be revisited before Phase 2 builds on them.

### Carried over from the 2026-09-23 `--auto` round (still valid)
- **D-19:** The transport moves out of `main.py` into a new root module `bridge.py`: `_get_client`,
  `_revit_call`, the lock, port parsing. `main.py` imports and passes the same three callables
  `revit_get` / `revit_post` / `revit_image` to `register_tools` — the injection contract does not
  change and no `tools/*_tools.py` edit is needed for serialization. Reason: `bridge.py` imports in
  tests without `FastMCP` and without registering 54 tools.
- **D-20:** `deploy/build-payload.cmd` gets a `copy` line for `bridge.py`; `deploy/gate.py` must pass
  with it. `tests/unit/test_local_bridge_transport.py` (currently reads `main.py` text) is retargeted
  at `bridge.py`; `trust_env=False` (commit `f0af5b0`) moves with the client and stays mandatory.
- **D-21:** Docs updated in the same phase: the `CLAUDE.md` sharp edge "port is hardcoded" is
  rewritten; `README.md`, `deploy/README.md`, `deploy/USER-GUIDE.md` get an env block example with
  `REVIT_PORT` (and the two-entry example of D-03). `deploy/configure_hermes.py` untouched while the
  default port holds.
- **D-22:** New `tests/unit/test_bridge_serialization.py` on `httpx.MockTransport` with a handler
  held by an `asyncio.Event`; async tests via anyio's pytest plugin (`@pytest.mark.anyio`) — no new
  dependency. Cover: second POST waits for the first; GET passes while POST holds the lock; allowlisted
  POST passes while the lock is held; exception and cancellation release the lock; HTTP timeout
  counted after acquire; queue bound yields the "nothing was sent" error without sending;
  outcome-unknown message on post-send timeout; `REVIT_PORT` parsing.
- **D-23:** Side experiment on the bench (research flag from STATE.md): what Revit's external-event
  queue does today with two overlapping POSTs (hang / error / serialize). Result goes into the
  `bridge.py` docstring as the rationale for what the lock buys — does not block the phase.
- **D-24:** `python tests/test_init_latency.py` stays < 2.0 s — `bridge.py` imports nothing heavier than `httpx`.

### Claude's Discretion
- Lock primitive details and where exactly the read-only allowlist lives (a set in `bridge.py`,
  a flag at the `revit_post` call site, …), as long as D-08's fail-safe default and its unit test hold.
- How `get_revit_status` obtains `host:port` without tool modules importing the transport
  (e.g. an attribute on the injected callable or an extra injected value) — must respect the
  "tool modules never import the transport" rule.
- Exact function names in `bridge.py`, wording of the queue-busy and outcome-unknown messages,
  MockTransport fixture shape.

### Deferred Ideas (OUT OF SCOPE)
- One MCP server discovering all Revit instances (48884..4888x) and addressing "instance +
  document" per call / a `RevitTarget` registry — rejected for now in favor of D-02/D-04; revisit
  only if D-18 triggers or the fleet regularly runs more than two instances.
- Runtime target-switch tool — rejected (shared state under `stateless_http`).
- `contrib-kit/revitmcp_kit.py` with a hardcoded `48884` — separate client, not part of IDENT-05.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SER-01 | Mutating calls of this MCP server do not go to Revit in parallel | `asyncio.Lock` at the `revit_post` seam inside `bridge._revit_call`; prototype passes "second POST is not sent until first completes" (Architecture Pattern 1). The lock is more valuable than assumed: pyRevit shares ONE request handler object across all HTTP threads (Summary finding 1). |
| SER-02 | Lock held by a mutation does not block `/status/` and read calls | GET and `revit_image` bypass the lock; allowlisted POSTs bypass it; prototype proves `wait_for(..., 1.0)` on GET and allowlisted POST while the lock is held. Live caveat in Pitfall 1: only `/status/` and `/model_info/` are fully off pyRevit's shared handler. |
| SER-03 | Exception, timeout or cancel inside the serialized section releases the queue | `async with lock:` only (D-10); prototype proves release after ReadTimeout, after `CancelledError`, after queue-bound expiry. |
| SER-04 | Queueing never leaves a call with less than its own time budget | `asyncio.timeout(bound)` wraps only the wait; `budget.reschedule(None)` the moment the lock is held; httpx `timeout=` is passed only to the send, so it starts fresh. Prototype asserts `request.extensions["timeout"]["read"] == 5.0` for a call that queued. |
| SER-05 | Scope of serialization documented honestly | Wording constraints + a doc-pin test (Validation Architecture). Also: the honest rationale is stronger than "UX only" (finding 1) but the guarantee is still process-local. |
| IDENT-05 | Routes port configurable by `REVIT_PORT` | `_resolve_port` pure function (strict ASCII-digit parse, 1..65535, refuse on invalid); `BASE_URL` built from it; `get_revit_status` surfaces `host:port`. pyRevit side: port is a *starting* port per user; second instance auto-increments (source-verified). |
</phase_requirements>

## Summary

The CPython half of this phase is small and fully testable without Revit. I prototyped the whole serialization seam in the scratchpad (not in the repo) and ran 16 tests against the repo's own venv (`uv run --group dev pytest`): second POST waits and is not sent early; GET and an allowlisted POST pass while the lock is held; the second call still gets its full `timeout` after queueing; the queue bound returns a "NOT sent" error without sending anything; a post-send `httpx.ReadTimeout` releases the lock and yields an "outcome unknown" message; `CancelledError` releases the lock; and strict port parsing refuses `""`, `"abc"`, `"0"`, `"65536"`, `"48884.0"`, `"4_8884"`, Arabic-Indic digits and `"+1"`. The pattern is: `async with asyncio.timeout(timeout) as budget: async with lock: budget.reschedule(None); send(...)` — it satisfies D-10 literally (only `async with lock:`), bounds only the wait (D-11), and needs no new dependency.

Three findings change how the plan should be written, beyond the CONTEXT decisions:

1. **pyRevit has ONE shared request handler for every HTTP thread, so overlapping requests race inside Revit's own plumbing, not just "20 transactions".** `server.py` creates module-level `REQUEST_HNDLR` and `EVENT_HNDLR` once; each request thread assigns `REQUEST_HNDLR.request`/`.handler`, calls `reset()`, `Raise()`, then spins on `IsPending` and `join()` with no lock around the sequence; `Execute()` reads `self.handler`/`self.request` at execution time, not at raise time. Two overlapping requests that need the API context can therefore have one overwrite the other's handler before Execute runs — the wrong route executes, one caller receives the other's response, or a route runs twice. This is source-verified (installed 6.5.3 and the `develop` branch); whether Revit coalesces two `Raise()` calls is contested in public sources and is exactly what D-23 should measure. Consequences: (a) the lock is a correctness mechanism for mutation-vs-mutation, not merely UX — this corrects the inference in `.planning/research/PITFALLS.md` Pitfall 5; (b) **D-08's allowlist and the GET exemption mean a read can still overlap a mutation's submission window and hijack it** — an unlocked read overlapping a pending mutation can replace its handler, and the mutation's caller would get a read-shaped dict that `format_response` renders as success. Only `/status/` and `/model_info/` take no `doc`/`uiapp`/`uidoc` argument and therefore run directly on the HTTP thread instead of the shared handler. The locked decisions stay as written; the plan must (i) run D-23 early enough to inform the `bridge.py` docstring, (ii) word SER-02 in docs as "this server does not queue reads behind mutations", never "reads are safe during mutations", and (iii) escalate to the user if D-23 shows read-vs-mutation cross-wiring (Open Question 1).

2. **pyRevit's port auto-increment is real, but it is a registration race, not a bind check, which puts criterion 5 and the D-18 stop condition at risk from launch order alone.** `serverinfo._get_next_available_port` starts at `user_config.routes_port` (one `[routes] port` per Windows user in `pyRevit_config.ini`, currently `48884`) and skips ports found in the per-process `serverinfo.pickle` files of *other running Revit processes*. It never checks that the port is actually free on the OS. The second instance only sees the first if the first has already written its pickle (written in `activate_server()` during pyRevit session load). `ThreadedHttpServer` sets `allow_reuse_address = True`; on Windows `SO_REUSEADDR` lets two sockets bind the same port without error, which matches the documented "two listeners on 48884" incident (that Windows semantic is [ASSUMED] from general knowledge; the flag itself is verified). So two Revits launched at the same moment — or a `RevitAccelerator` pre-warm racing a user launch (`RevitAccelerator.exe` is running on this machine right now, no Revit process) — can both pick 48884. **The bench must start instance B only after instance A answers `/status/`**, and a both-on-48884 result from a simultaneous launch is a launch-order finding to record, not by itself proof that the one-server-per-port model is unworkable. This reading of D-18 needs user confirmation (Open Question 2).

3. **The move to `bridge.py` has more call sites than D-20 lists.** Two existing tests read `main.py` text: `tests/unit/test_local_bridge_transport.py` (D-20 covers it) and `tests/unit/test_textutils.py::test_the_client_does_not_ask_pyrevit_to_parse_the_body`, which does `source.index("else:  # POST")` and checks `'"Content-Type": "text/plain'`. It will fail with `FileNotFoundError`-style or `ValueError` after the move unless retargeted *and* the literal `else:  # POST` marker is preserved (or the test is updated with the move). Also the default `anyio` pytest plugin parametrizes every `@pytest.mark.anyio` test over `["asyncio", "trio"]` and `trio` is not installed, so unmodified `@pytest.mark.anyio` tests fail on the trio param (reproduced); a one-line `anyio_backend` fixture override in `tests/unit/conftest.py` fixes it without adding `trio`.

**Primary recommendation:** Build `bridge.py` as `asyncio.timeout(wait-bound)` around `async with lock:` with `budget.reschedule(None)` on acquisition, a fail-safe `READ_ONLY_POST` set (the five D-08 routes, all confirmed read-only by reading their handlers), classification of pre-send vs post-send httpx errors, and a function attribute on `revit_get` carrying `host:port` for `get_revit_status`; prove every success criterion in `tests/unit/test_bridge_serialization.py`; and run the live bench with a staggered start plus the D-23 overlap experiment before finalising the `bridge.py` docstring.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Mutation queue / lock | MCP server process (CPython, `bridge.py`) | — | The only place a lock can live that unit tests can reach; the Revit side cannot be changed in this phase (no `revit_mcp/` edits). Scope is this process only (D-15). |
| Queue-wait bound and per-call timeout | MCP server process (`bridge.py`) | — | Time budgets are a property of the client call; httpx enforces the request timeout, `asyncio.timeout` the wait. |
| Read-only classification (allowlist) | MCP server process (`bridge.py`) | `tests/unit` drift test | Must be fail-safe: unknown route = locked. A test binds the set to the real tool endpoints. |
| `REVIT_PORT` parsing / refuse-to-start | MCP server process (`bridge.py` import, `main.py` stderr + exit) | Client config (env block) | Env is read once at import (D-02); invalid value must not reach stdout. |
| Port assignment per Revit instance | pyRevit (Revit process, `serverinfo.py`) | `pyRevit_config.ini` `[routes] port` | The extension cannot influence it from `startup.py`; only start order and the per-user start port matter. |
| Target `host:port` shown to the model | MCP server process (`status_tools.py` reading attribute of injected callable) | — | D-06 forbids a Revit-side change; `document_title` already comes from `/status/`. |
| Which instance is "a" or "b" | Client config (two MCP entries) | Launch order in Windows | Port ↔ instance mapping is by start order, not by model or version. |
| Distribution of `bridge.py` | Build (`deploy/build-payload.cmd`, `deploy/gate.py`) | `deploy/server.py` sys.path injection | Payload copies named files only; a missing `copy` line is an `ImportError` at deployed start. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio` (stdlib) `Lock`, `timeout` | CPython 3.11+ (dev 3.13.7; deployed pyRevit CPython is 3.12 — `CPY3123`) | Mutual exclusion and bounded queue wait | `asyncio.timeout` is 3.11+, matches `requires-python = ">=3.11"`. [VERIFIED: pyproject.toml:6 `requires-python = ">=3.11"`; prototype ran on 3.13.7] |
| `httpx` | 0.28.1 (already pinned) | Pooled client, `MockTransport` for tests | [VERIFIED: uv run import, `httpx 0.28.1`; pyproject.toml:12 `"httpx>=0.28.1"`] |
| `anyio` pytest plugin | 4.9.0 (already a runtime dep) | `@pytest.mark.anyio` async tests | D-22: no new dependency. [VERIFIED: uv run import, `anyio 4.9.0`; pyproject.toml:13 `"anyio>=4.9.0"`] |
| `pytest` | 9.1.1 (dev group) | Unit suite | Existing. [VERIFIED: uv run import] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `mcp` | 1.9.0 (lock) | `Context.info` for the one wait message | Guard with `if ctx:` and `try/except Exception` — `Context.request_context` raises `ValueError("Context is not available outside of a request")` [VERIFIED: .venv/Lib/site-packages/mcp/server/fastmcp/server.py:950-953]. `process_tools._say` is the existing best-effort pattern. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.timeout` + `reschedule(None)` | `asyncio.wait_for(lock.acquire(), bound)` + manual `release()` | Violates D-10 (no manual acquire/release); the reschedule form keeps `async with lock:` literal. |
| Module-global lock | `asyncio.Semaphore(1)` / queue+worker | `Lock` states the single-holder invariant; queue+worker is redesign (STACK.md). |
| `anyio_backend` override | install `trio` | Adds a dependency for nothing; the lock under test is `asyncio.Lock`, so only asyncio is meaningful. |

**Installation:** none. No package is added. `uv sync --group dev` already provides everything.

**Version verification:** versions above were read from the project's own venv this session (`uv run --group dev python -c ...`). No registry lookup was needed because nothing new is installed.

## Package Legitimacy Audit

No external packages are installed by this phase. `trio` is explicitly **not** to be installed (it appears only as a failing default parametrization of the already-installed `anyio` plugin).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 MCP client A (entry "revit-a", env REVIT_PORT=48884)     MCP client B (entry "revit-b", REVIT_PORT=48885)
          │ stdio                                                   │ stdio
          ▼                                                         ▼
  main.py process A                                         main.py process B     (one process = one target, D-02)
   FastMCP: tool calls run CONCURRENTLY (tg.start_soon per request)
          │ tool(...) → revit_get / revit_post / revit_image   (injected, tools never import transport)
          ▼
  bridge._revit_call(method, endpoint, ctx, timeout)
          │
          ├─ GET / revit_image ───────────────────────────────┐ never locked (SER-02)
          ├─ POST ∈ READ_ONLY_POST ───────────────────────────┤
          │                                                   ▼
          └─ any other POST (fail-safe default) ──► [ wait-bound = timeout ] ──► async with lock (module-global)
                                                         │ expired → "Error: … NOT sent to Revit"      │ acquired: budget.reschedule(None)
                                                         ▼                                              ▼
                                                  (nothing sent)                          httpx send, timeout starts NOW (SER-04)
                                                                                                │
              pre-send failure (ConnectError/ConnectTimeout/PoolTimeout) → "not sent"           │
              post-send failure (ReadTimeout, ReadError, …) → "outcome UNKNOWN, verify first"   │ lock released on every exit (SER-03)
                                                                                                ▼
                                          http://REVIT_HOST:REVIT_PORT/revit_mcp/<route>   (trust_env=False, text/plain body)
                                                                                                │
                                    pyRevit Routes (inside Revit process): ThreadedHttpServer, one thread per request
                                      ├─ /status/, /model_info/ (no doc/uiapp/uidoc arg) → run on the HTTP thread
                                      └─ every other route → shared REQUEST_HNDLR + ExternalEvent → Revit main thread
```

### Recommended Project Structure
```
bridge.py                         # NEW root module: config, client, lock, _revit_call, revit_get/post/image
main.py                           # imports the three callables from bridge; FastMCP wiring only
tools/status_tools.py             # reads getattr(revit_get, "revit_target", None) for D-06
tests/unit/conftest.py            # + anyio_backend fixture (asyncio only) + autouse reset of bridge state
tests/unit/test_bridge_serialization.py   # NEW (D-22)
tests/unit/test_local_bridge_transport.py # retarget to bridge.py (trust_env=False)
tests/unit/test_textutils.py      # retarget test_the_client_does_not_ask_pyrevit_to_parse_the_body
deploy/build-payload.cmd          # + copy bridge.py
```

### Pattern 1: bounded wait, unbounded-by-the-wait send (prototyped, 16/16 passing)
**What:** the queue-wait deadline exists only until the lock is held, and the request timeout is handed to httpx only at send time, so SER-04 holds by construction.
**When to use:** every locked POST.
**Example:**
```python
# Source: prototype run in this session (scratchpad), CPython 3.13.7, httpx 0.28.1
async def _revit_call(method, endpoint, data=None, ctx=None, timeout=30.0, params=None):
    budget = None                                   # see Pitfall 6: must exist before the except
    try:
        if not _is_locked(method, endpoint):
            return await _send(method, endpoint, data, timeout, params)
        lock = _get_lock()
        if lock.locked():
            await _say(ctx, "waiting for the previous mutation to finish")   # D-14, once, best-effort
        async with asyncio.timeout(timeout) as budget:     # D-11: wait bound == call timeout
            async with lock:                               # D-10: nothing but `async with`
                budget.reschedule(None)                    # lock held: the wait bound no longer applies
                try:
                    return await _send(method, endpoint, data, timeout, params)   # fresh full timeout
                except httpx.TransportError as e:
                    ...                                    # pre-send vs post-send wording (Pitfall 4)
    except TimeoutError:
        if budget is not None and budget.expired():        # only OUR wait deadline, not a TimeoutError from the body
            return "Error: Revit queue busy ... NOT sent to Revit; nothing was changed ..."
        raise
    except Exception as e:
        return "Error: {}".format(str(e) or type(e).__name__)   # str(httpx timeout) is '' (verified)
```
**Why it is safe:** if the deadline fires in the instant between acquire completing and `reschedule(None)`, CPython's `Lock.acquire` re-wakes the next waiter on `CancelledError` when `_locked` was not yet set, so no lock is leaked. [ASSUMED: from reading CPython behaviour; the prototype proved cancel-while-held and expiry-while-waiting, not that exact instant.]

### Pattern 2: read-only allowlist as a fail-safe set with a drift test
**What:** a `frozenset` of route keys that opt OUT of locking, plus a never-unlock set, plus a test that scans `tools/*.py` for every literal `revit_post("/x/"` endpoint.
```python
READ_ONLY_POST = frozenset({"ai_filter", "material_quantities", "clash_check",
                            "list_category_parameters", "model_worksets"})
NEVER_UNLOCKED = frozenset({"execute_code", "open_model", "save_document"})   # D-09
def _route_key(endpoint):                     # tolerate query strings and missing slashes
    return endpoint.split("?", 1)[0].strip("/")
def _is_locked(method, endpoint):
    return method == "POST" and _route_key(endpoint) not in READ_ONLY_POST   # unknown -> locked
```
The drift test asserts: every allowlist entry is an endpoint some tool actually posts to (a rename must not leave a dead entry); `READ_ONLY_POST ∩ NEVER_UNLOCKED == ∅`; every endpoint outside the set is locked; a made-up endpoint is locked; GET is never locked.

### Pattern 3: `host:port` for `get_revit_status` without importing the transport (D-06)
**What:** set a plain attribute on the injected function, read it with `getattr(..., None)` in the tool.
```python
# bridge.py (after the functions are defined)
revit_get.revit_target = "{}:{}".format(REVIT_HOST, REVIT_PORT)
# tools/status_tools.py
target = getattr(revit_get, "revit_target", None)
response = await revit_get("/status/", ctx, timeout=10.0)
if target:
    if isinstance(response, dict):
        response = dict(response, mcp_target=target)          # lands under "Mcp Target:" in format_response
    else:
        response = "{}\n(MCP target: {})".format(response, target)   # 503/transport errors are strings
return format_response(response)
```
Why an attribute and not a new registrar parameter: `scripts/conventions.py:29` pins `CANONICAL_TOOL_REGISTRAR = ["mcp", "revit_get", "revit_post", "revit_image"]`, so a fifth parameter would fail the convention checks. `getattr(..., None)` also keeps the existing tests that register tools with fake callables working. [VERIFIED: scripts/conventions.py:29]

### Anti-Patterns to Avoid
- **Manual `acquire()`/`release()` or `asyncio.wait_for(lock.acquire(), …)`:** violates D-10 and reintroduces the leak class SER-03 forbids.
- **One `asyncio.timeout` around lock plus send:** the wait would eat the call's own budget (breaks SER-04).
- **Locking inside `_revit_call` for every method, then exempting `/status/` by name:** lock the POST branch only; GET never touches the lock (SER-02 must not depend on a name list).
- **Catching bare `TimeoutError` as "queue busy":** a `TimeoutError` raised by the body would be misreported as "not sent". Use `budget.expired()`.
- **Claiming "Revit refuses a second transaction anyway":** wrong for this stack (finding 1); the serialization point inside pyRevit is a shared mutable handler, not a queue.
- **Reading `REVIT_PORT` per call:** D-02 fixes it at import.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Queue with timeout | a deque + worker task + futures | `asyncio.Lock` (FIFO-fair) + `asyncio.timeout` | Lock waiters are FIFO; cancellation of a waiter is handled by the stdlib. |
| Test transport | a fake `httpx.AsyncClient` | `httpx.MockTransport(handler)` with an async handler held by `asyncio.Event` | Real request objects; `request.extensions["timeout"]` exposes the per-call timeout so SER-04 is testable (verified: returns `{"connect","read","write","pool"}` all equal to the passed float). |
| Async test runner | `asyncio.run` boilerplate per test | anyio plugin + `anyio_backend` override | Already installed (D-22). |
| Port validation | `int(os.environ[...])` | strict `isascii() and isdigit()` then range check | `int()` accepts `"4_8884"`, `" 48884 "`, Arabic-Indic digits — a typo must not silently pass (D-05). |
| Listener enumeration for the bench | parsing `netstat` text | `Get-NetTCPConnection -State Listen` and pyRevit's own `GET /routes/sisters` | Both give PID/port directly (see Live bench). |

**Key insight:** this phase has almost no code worth inventing; the cost is in the edge semantics (budget accounting, error classification, test isolation) and in honest wording, all of which the stdlib primitives already cover.

## Runtime State Inventory

This phase is not a rename, but it moves the transport out of `main.py` and changes how a value (the port) is sourced, so the "what still carries the old shape" questions were answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — the bridge keeps no database; all state is in the Revit session (`.planning/codebase`, vault note "Базы данных нет"). | none |
| Live service config | pyRevit `[routes] enabled/core_api/host/port` in `%APPDATA%\pyRevit\pyRevit_config.ini` currently `host = "127.0.0.1"`, `port = 48884` [VERIFIED: pyRevit_config.ini lines 72-77 quoted below]. Per-user, shared by all instances of that user. `deploy/install.cmd:130` runs `"!PYREVIT!" configs routes port 48884`. | none for default; the start port stays 48884. Do not change it per-instance — it cannot be per-instance. |
| OS-registered state | `RevitAccelerator.exe` (PID 74984 at research time) can pre-launch a hidden Revit (vault note 2026-09-08, hypothesis). Installed Revit versions: 2024, 2025, 2027. | Bench pre-check: no unexpected `Revit.exe` before starting A (see Live bench). |
| Secrets/env vars | `REVIT_HOST` already read from env; client configs carry it: `deploy/configure_hermes.py:181` (`'REVIT_HOST: "127.0.0.1"'`), `deploy/USER-GUIDE.md:98-99` and `:217-218`. `REVIT_PORT` is new and optional. | docs only (D-21); `configure_hermes.py` untouched. |
| Build artifacts / installed packages | Deployed installs at `%LOCALAPPDATA%\RevitMCP\current\app\` contain `main.py` but will not contain `bridge.py` until a rebuilt payload is published and `update.cmd` runs. `deploy/server.py` catches `ImportError` and prints a **misleading** message ("Dependencies … built for a different CPython") — a missing `bridge.py` is a `ModuleNotFoundError`, a subclass. `.kilo/worktrees/hot-cirrus/` holds a stale copy of `main.py` (separate worktree). | `deploy/build-payload.cmd` copy line (D-20); `deploy/gate.py` spawns `server.py` and will fail the build if `bridge.py` is absent, which is the intended net. Ignore the worktree. |

Verbatim from `%APPDATA%\pyRevit\pyRevit_config.ini`: `[routes]` / `enabled = true` / `core_api = true` / `host = "127.0.0.1"` / `port = 48884`.

## Common Pitfalls

### Pitfall 1: Believing "read-only" calls are safe while a mutation is in flight
**What goes wrong:** the CPython test proves reads are not queued behind the lock, then docs or tool docstrings say reads are safe during mutations.
**Why it happens:** every route except `/status/` and `/model_info/` goes through pyRevit's single shared `REQUEST_HNDLR`; an unlocked read can overlap a pending mutation's submission window.
**How to avoid:** SER-02 wording is "this server does not queue reads behind mutations". Run D-23 and, if it shows cross-wiring, take Open Question 1 to the user. Do not add a read lock on your own; it contradicts SER-02 and D-08.
**Warning signs:** a mutation returns a dict that looks like a read result; the same mutation appears applied twice or not at all after a concurrent read.
[VERIFIED: pyRevit 6.5.3 `server.py:41-42,109-110,115,117,128,132`; `handler.py:100,305-309`; `develop` branch shows the same structure. 6.5.5 (fleet) not read: [ASSUMED] same.]

### Pitfall 2: `asyncio.Lock` bound to a dead event loop across tests
**What goes wrong:** test 2 raises `RuntimeError: <asyncio.locks.Lock object … [locked]> is bound to a different event loop` (reproduced on 3.13.7) because the module-global lock was contended in test 1's loop; the pooled `httpx.AsyncClient` has the same problem.
**How to avoid:** an `autouse` fixture in `tests/unit/conftest.py` that sets `bridge._lock = None` and `bridge._http_client = None` around every test, and tests inject a per-test `httpx.AsyncClient(transport=MockTransport(...), base_url=..., trust_env=False)` by assigning `bridge._http_client` (no production hook needed because `_get_client()` returns an existing open client).
**Warning signs:** tests pass alone and fail in the full run.

### Pitfall 3: the default anyio plugin runs every async test on `trio`
**What goes wrong:** `@pytest.mark.anyio` tests fail with `ModuleNotFoundError: No module named 'trio'` on the `[trio]` parametrization (reproduced). [VERIFIED: `.venv/Lib/site-packages/anyio/pytest_plugin.py:173-175` `@pytest.fixture(scope="module", params=get_all_backends())`]
**How to avoid:** in `tests/unit/conftest.py`: `@pytest.fixture(scope="module") def anyio_backend(): return "asyncio"` (module scope, or the override is ignored by module-scoped plugin fixtures).
**Warning signs:** half the new tests error, named `[trio]`.

### Pitfall 4: empty timeout messages and the pre-send/post-send distinction
**What goes wrong:** `str(httpx.ReadTimeout(""))` is `''` (verified), so the current `f"Error: {e}"` returns the literal `"Error: "` — a model cannot tell a timeout from anything else, and for a mutation cannot tell "not applied" from "maybe applied".
**How to avoid:** classify on a locked POST: `httpx.ConnectError`, `httpx.ConnectTimeout`, `httpx.PoolTimeout` → "request was not sent to Revit"; any other `httpx.TransportError` (ReadTimeout, WriteTimeout, ReadError, RemoteProtocolError) → "outcome UNKNOWN … may have been applied … verify before retrying" (D-13). Never start these strings with a digit: `tools/process_tools.py:82-84` treats `Error: <digits>…` as "server answered" (`no_document`). Fall back to `type(e).__name__` when `str(e)` is empty. [VERIFIED: tools/process_tools.py:82-84]

### Pitfall 5: two existing tests read `main.py` source
**What goes wrong:** after the move, `test_local_bridge_transport.py` (D-20) and `test_textutils.py::test_the_client_does_not_ask_pyrevit_to_parse_the_body` both fail; the second does `source.index("else:  # POST")` and `'"Content-Type": "text/plain'`, so the literal marker and header line must survive in `bridge.py` or the test must change in the same commit.
**How to avoid:** retarget both in the same task as the move; keep `else:  # POST` and the explanatory comment block verbatim in `_send`/`_revit_call`; `test_local_bridge_transport` slices `source.split("def _get_client()", 1)[1].split("async def revit_get", 1)[0]` — keep that function order in `bridge.py` or relax the slice.
[VERIFIED: tests/unit/test_local_bridge_transport.py:9-15; tests/unit/test_textutils.py:276-290]

### Pitfall 6: `budget` unbound in the `except TimeoutError` handler
**What goes wrong:** `UnboundLocalError` if a `TimeoutError` is raised before `async with asyncio.timeout(...) as budget` assigns it (e.g. on the unlocked path). **How to avoid:** `budget = None` first and test `budget is not None and budget.expired()` (shown in Pattern 1).

### Pitfall 7: two MCP entries on HTTP transports collide on port 8000
**What goes wrong:** `main.py` hardcodes `FastMCP(..., host="127.0.0.1", port=8000, ...)`. Two entries in `--streamable-http`/`--sse`/`--combined` mode would both try to bind 8000. [VERIFIED: main.py:13-19, `port=8000`]
**How to avoid:** the D-03 two-entry model is for stdio (the client spawns one process per entry — the default and the fleet configuration). Say so in the docs; do not widen scope to a `MCP_PORT` setting (not requested).

### Pitfall 8: stale "second Revit is unreachable" statements
**What goes wrong:** after this phase the sentence in `tools/process_tools.py` (`start_revit` docstring: "Only one Revit is started; a second instance would bind a different Routes port and be unreachable anyway.") and in USER-GUIDE ("оба его занимают порт 48884") are only half true. **How to avoid:** update the wording in the D-21 doc pass; `start_revit` probes *its own* target port, so on a `REVIT_PORT=48885` entry it will launch Revit while 48884 is already running — which is correct for the bench, but must be stated in its docstring, since it is the tool the model sees. Tool docstrings are the API contract (CLAUDE.md).

### Pitfall 9: `ctx.info` failing inside the wait
**What goes wrong:** raising out of the progress line fails the call. **How to avoid:** the `_say` pattern from `process_tools.py:52-63` (guard + `try/except Exception`), and emit the message *before* entering `asyncio.timeout`, so message latency does not consume the wait bound.

### Pitfall 10: port-to-instance mapping is by start order and moves
**What goes wrong:** "revit-a = 48884" silently points at a different Revit after a restart (close A, start C → C takes 48884, because the first unused port from the start port wins). **How to avoid:** the D-17 check (`document_title` + `host:port` in `get_revit_status`) is the control; the docs must say the port identifies a launch slot, not a model; true identity is Phase 2 (PID/session token).

## Code Examples

### Strict port parsing (prototyped; all cases below verified)
```python
class RevitConfigError(ValueError):
    pass

def _resolve_port(value):
    if value is None:                       # unset -> default
        return 48884
    text = str(value).strip()
    if not (text.isascii() and text.isdigit()):
        raise RevitConfigError("REVIT_PORT must be an integer in 1..65535, got {!r}".format(value))
    port = int(text)
    if not 1 <= port <= 65535:
        raise RevitConfigError("REVIT_PORT out of range 1..65535: {}".format(port))
    return port
# verified: None→48884, "48885"→48885, " 48885 "→48885;
# refused: "", "abc", "0", "65536", "-1", "48884.0", "4_8884", "٤٨٨٨٤", "+1"
```
`main.py` guard (stderr only, never stdout; exit non-zero; the protocol stream is stdout):
```python
try:
    from bridge import revit_get, revit_post, revit_image
except ValueError as exc:                    # RevitConfigError is a ValueError
    sys.stderr.write("revit-mcp: {}\n".format(exc))
    sys.exit(2)
```
`deploy/server.py` runs `main.py` through `runpy.run_path` with `HERE` on `sys.path`, so `import bridge` resolves in the deployed layout; a `SystemExit` propagates as a normal exit, and a `ValueError` is not caught by its `except ImportError`. [VERIFIED: deploy/server.py sys.path inserts and `except ImportError`]

### Concurrency test skeleton (prototype, passes)
```python
@pytest.mark.anyio
async def test_second_post_waits_get_and_allowlisted_pass():
    gate, started, seen = asyncio.Event(), asyncio.Event(), []
    async def handler(req):
        seen.append((req.url.path, req.extensions["timeout"]["read"]))
        if req.url.path.endswith("/p1/"):
            started.set(); await gate.wait()
        return httpx.Response(200, json={"ok": req.url.path})
    bridge._http_client = httpx.AsyncClient(base_url="http://x:1/revit_mcp",
                                            transport=httpx.MockTransport(handler), trust_env=False)
    t1 = asyncio.create_task(bridge._revit_call("POST", "/p1/", {}, timeout=5.0))
    await started.wait()
    t2 = asyncio.create_task(bridge._revit_call("POST", "/p2/", {}, timeout=5.0))
    await asyncio.sleep(0.05)
    assert [p for p, _ in seen] == ["/revit_mcp/p1/"]                              # SER-01
    await asyncio.wait_for(bridge._revit_call("GET", "/status/", timeout=1.0), 1.0)           # SER-02
    await asyncio.wait_for(bridge._revit_call("POST", "/ai_filter/", {}, timeout=1.0), 1.0)   # SER-02
    gate.set(); await t1; await t2
    assert ("/revit_mcp/p2/", 5.0) in seen                                          # SER-04: full budget
```
Note `MockTransport` does not enforce timeouts; assert on `request.extensions["timeout"]` and simulate failures by raising `httpx.ReadTimeout("", request=req)` / `httpx.ConnectError("", request=req)` from the handler.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.wait_for(lock.acquire(), t)` | `asyncio.timeout()` with `Timeout.reschedule()`/`expired()` | Python 3.11 | A bounded wait around `async with lock:` with no manual acquire/release. |
| Lock bound to loop at creation | Lock binds to a loop lazily at first contended acquire | Python 3.10 | Creating it lazily is fine, but tests spanning loops must reset it (Pitfall 2). |
| pyRevit 6.5.5 (fleet vetted installer) | 7.0.0 published 2026-10-06 | 2026-10-06 | Fleet standard stays 6.5.5 (memory: the GitHub 6.5.5 build is broken, vetted installer is the standard); do not read 7.0.0 behaviour into this research. [CITED: api.github.com/repos/pyrevitlabs/pyRevit/releases] |

**Deprecated/outdated:**
- `.planning/research/PITFALLS.md` Pitfall 5 inference that "the external-event queue is very likely already the true serialization point" — contradicted by `server.py`/`handler.py` (shared handler, no lock). Treat it as superseded by finding 1 pending D-23.
- `.planning/research/STACK.md` "MEDIUM confidence" on port auto-increment — upgraded: the mechanism is source-verified, the live behaviour and race are what the bench settles.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Whether Revit coalesces two `Raise()` calls before `Execute` is unresolved (public sources conflict: "queued and executed sequentially" vs "a later action can replace its payload"). | Summary finding 1 | D-23 decides; either way the shared-handler overwrite window exists, but the observable symptom (wrong route run vs. one response shared) differs. |
| A2 | pyRevit **6.5.5** (fleet) has the same shared-handler and port-registration code as the installed 6.5.3 and `develop`. | Summary 1, 2 | If 6.5.5 differs, the pitfall wording and bench expectations change. Quick check: diff `server.py`/`serverinfo.py` of the fleet install. |
| A3 | On Windows, `SO_REUSEADDR` (`allow_reuse_address = True`) allows two processes to bind the same TCP port without error, which explains the observed double listener. | Summary 2 | If false, the double-listener has another cause (e.g. `ListRunningRevits` not seeing a pre-warmed instance); the staggered-start mitigation might not suffice. |
| A4 | `RevitController.ListRunningRevits()` sees a `RevitAccelerator`-hosted Revit process. | Summary 2 | If not, a pre-warmed instance never reserves its port in anyone's view. |
| A5 | The client used for the acceptance session (Hermes/"Гена" or Claude) namespaces the tools of two MCP entries so both are callable in one conversation. | D-03/D-17 | The cross-instance scenario cannot be demonstrated; fall back to two sessions and record it. Checked at the bench. |
| A6 | `/routes/sisters` on a live instance returns all registered servers (ports, process ids) incl. duplicates. Read in source (`routes/api.py`), not yet called live. | Live bench | The cross-check falls back to `Get-NetTCPConnection` + `Get-Process` only. |
| A7 | The deadline firing in the instant between acquire completion and `reschedule(None)` leaks no lock (reading of CPython `Lock.acquire`). | Pattern 1 | A leaked lock = SER-03 violation; mitigated by the "re-acquire right after" test, but that exact instant is not unit-reproducible. |

## Open Questions

1. **Does D-23 show read-vs-mutation cross-wiring, and if so should reads join the lock?**
   - What we know: pyRevit shares one request handler across HTTP threads with no lock (source). Only `/status/` and `/model_info/` bypass it. D-08/SER-02 deliberately leave reads unlocked.
   - What's unclear: whether Revit coalesces or sequences overlapping `Raise()`s, and how large the overwrite window is when Revit is busy.
   - Recommendation: implement as decided; run the D-23 overlap protocol (below) early on the bench, before writing the `bridge.py` rationale docstring. If it shows a read hijacking a pending mutation, **stop and ask the user**: options are (a) accept and document, (b) lock every route that takes an API context and exempt only `/status/` and `/model_info/` (changes SER-02's meaning), (c) a Revit-side fix in a later phase. Do not choose unilaterally.

2. **Does D-18 fire on a launch-order race, or only on a proven design failure?**
   - What we know: second-instance port choice depends on the first having registered; simultaneous launches can collide (source), and the double-listener has been observed once on this machine.
   - What's unclear: the user's intent for "started together" (D-16).
   - Recommendation: run the bench staggered (A answers `/status/` before B is launched) as the acceptance run; separately record what a truly simultaneous launch does. If staggered still yields two on 48884, D-18 triggers as written. If only simultaneous does, report it to the user as a launch-order finding with the staggered start as the documented procedure, rather than self-accepting or self-failing the criterion.

3. **Empty `REVIT_PORT=""`:** D-05 says invalid → refuse. Recommend refusing (a templated-but-blank value should not silently become 48884). Planner's discretion; the prototype refuses it.

4. **Two-entry docs for HTTP transports** (Pitfall 7): confirm the user is content to scope the two-entry example to stdio.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | `uv run pytest tests/unit` | ✓ | 0.11.1 | — |
| CPython (dev) | unit tests, `bridge.py` | ✓ | 3.13.7 | — |
| pytest / anyio / httpx / mcp | unit suite | ✓ | 9.1.1 / 4.9.0 / 0.28.1 / 1.9.0 | — |
| `trio` | (not needed) | ✗ | — | `anyio_backend` override (Pitfall 3) |
| Baseline suite | regression gate | ✓ | `337 passed, 3 skipped in 2.06s` | — |
| Revit 2024 / 2025 / 2027 | live bench | ✓ installed (`C:\Program Files\Autodesk\Revit 20xx`) | — | — |
| Revit running now | live bench | ✗ (none running; zero listeners in 48884-48890) | — | start for the bench |
| `RevitAccelerator.exe` | (hazard) | ✓ running, PID 74984 | — | check for hidden Revit before each bench run |
| pyRevit | live bench | ✓ `%APPDATA%\pyRevit-Master`, v6.5.3.26176 locally (fleet standard 6.5.5) | 6.5.3 | — |
| `pyrevit configs routes port` | start-port control | ✓ in CLI help (`pyrevit configs routes port [<port_number>]`) | — | edit `[routes] port` |
| `Get-NetTCPConnection` | listener check | ✓ (PowerShell) | — | `netstat -ano` |

**Missing dependencies with no fallback:** none for the unit tier. The live tier needs a human at the keyboard with Revit.
**Missing dependencies with fallback:** `trio` (override fixture).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 with the installed anyio 4.9.0 plugin (`@pytest.mark.anyio`), `httpx.MockTransport` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options] testpaths = ["tests/unit"]`; add fixtures to `tests/unit/conftest.py` |
| Quick run command | `uv run pytest tests/unit/test_bridge_serialization.py -q` |
| Full suite command | `uv run pytest tests/unit` (baseline today: 337 passed, 3 skipped) |
| Latency gate | `python tests/test_init_latency.py` (< 2.0 s; D-24) |
| Payload gate | `deploy/gate.py` via `deploy/build-payload.cmd` (needs the `bridge.py` copy line) |

### Phase Requirements → Test Map
| Req / Criterion | Behavior | Test Type | Automated Command | File Exists? |
|-----------------|----------|-----------|-------------------|--------------|
| SER-01 / SC1 | Second mutating POST is not sent while the first is held; proceeds after release | unit (async, MockTransport) | `uv run pytest tests/unit/test_bridge_serialization.py -k second_post_waits -q` | ❌ Wave 0 |
| SER-02 / SC2 | GET, `revit_image` path and allowlisted POST return within 1 s while a POST holds the lock | unit (async) | `… -k reads_pass_while_locked` | ❌ Wave 0 |
| SER-03 / SC3 | Release after handler exception, post-send `ReadTimeout`, `CancelledError`, and queue-bound expiry; re-acquire immediately (`lock.locked()` false, next call succeeds) | unit (async) | `… -k releases` | ❌ Wave 0 |
| SER-04 / SC4a | A call that queued still sends with `request.extensions["timeout"]["read"] == its own timeout` | unit (async) | `… -k budget_not_shrunk` | ❌ Wave 0 |
| SER-04 / SC4b | Wait beyond bound returns `Error: …NOT sent to Revit…`, handler never sees the request | unit (async) | `… -k queue_bound` | ❌ Wave 0 |
| D-13 | Post-send `ReadTimeout` → "outcome UNKNOWN / may have been applied"; pre-send `ConnectError` → "not sent" | unit (async) | `… -k outcome_unknown` | ❌ Wave 0 |
| D-08/D-09 | Allowlist exactly the five routes; `execute_code`, `open_model`, `save_document` never in it; unknown POST locked; every allowlist entry is a real tool endpoint; no locked-by-default route missing from the tool scan | unit (static scan of `tools/*.py`) | `… -k allowlist` | ❌ Wave 0 |
| D-14 | Exactly one `ctx.info` call when a call has to wait; none when it does not; a raising `ctx.info` does not fail the call | unit (fake ctx) | `… -k wait_message` | ❌ Wave 0 |
| IDENT-05 / SC5 (code part) | `_resolve_port` accepts None/`"48885"`/`" 48885 "`; refuses `""`, `"abc"`, `"0"`, `"65536"`, `"-1"`, `"48884.0"`, `"4_8884"`, Arabic-Indic digits, `"+1"`; `BASE_URL`/client `base_url` carries the configured port; nothing written to stdout on refusal | unit | `… -k port` | ❌ Wave 0 |
| D-06 | `get_revit_status` output contains `host:port` for dict and string (503/transport) responses; works with a bare fake `revit_get` lacking the attribute | unit (fake mcp + fake callable) | `uv run pytest tests/unit/test_status_target.py -q` | ❌ Wave 0 |
| D-20 | `trust_env=False` in `bridge.py` client block; text/plain POST marker in `bridge.py` | unit (retargeted existing tests) | `uv run pytest tests/unit/test_local_bridge_transport.py tests/unit/test_textutils.py -q` | ✅ retarget |
| SER-05 / SC6 | `bridge.py` docstring, `CLAUDE.md` sharp edges and `README.md` each state the process-local scope and name second client / curl / `/execute_code/`; none claims a guarantee | unit (doc pin: substring checks) + manual review | `uv run pytest tests/unit -k serialization_scope` | ❌ Wave 0 |
| D-19 | `import bridge` works with no FastMCP imported | unit | `uv run python -c "import sys, bridge; assert 'mcp.server.fastmcp' not in sys.modules"` | ❌ Wave 0 |
| D-24 | Cold start < 2.0 s | script | `python tests/test_init_latency.py` | ✅ |
| D-20 | Payload includes `bridge.py` and gate passes | build/gate | `deploy\build-payload.cmd` | ✅ (edit) |
| SC5 live | Two Revits, ports 48884/48885, distinct PIDs; two MCP entries return own `host:port` + `document_title` | **live Revit** | see Live bench | manual, human at keyboard |
| D-23 | Overlap experiment recorded | **live Revit** | see Live bench | manual |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_bridge_serialization.py -q` (sub-second; prototype ran 16 tests in 0.39 s) plus the retargeted files after the move.
- **Per wave merge:** `uv run pytest tests/unit` (about 2 s) and `python tests/test_init_latency.py`.
- **Phase gate:** full unit suite green, latency gate green, `deploy\build-payload.cmd` gate green, live bench recorded, before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/unit/conftest.py` — `anyio_backend` fixture returning `"asyncio"` (module scope) and an `autouse` fixture resetting `bridge._lock`/`bridge._http_client` per test (Pitfalls 2, 3).
- [ ] `tests/unit/test_bridge_serialization.py` — all rows above marked Wave 0.
- [ ] `tests/unit/test_status_target.py` — fake `mcp` with a `.tool()` decorator capturing the function, fake `revit_get`.
- [ ] Retarget `test_local_bridge_transport.py` and `test_textutils.py::test_the_client_does_not_ask_pyrevit_to_parse_the_body` to `bridge.py` in the same commit as the move.
- [ ] `bridge.py` itself and the `main.py` import shim.
- Framework install: none.

### Live bench (criterion 5, D-16, D-17, D-23) — procedure, to be written into the plan as a `checkpoint:human-verify`
Cannot be automated: needs two Revit processes. Use only GET probes from the shell, and `Content-Type: text/plain` for any POST (a curl POST with `application/json` hits pyRevit's broken parse). After editing anything under `revit_mcp/` a full Revit restart is required; this phase edits none, so no restart cycle is needed except to launch the instances.

1. Pre-check: `Get-Process Revit -ErrorAction SilentlyContinue` is empty (RevitAccelerator may pre-warm one); `Get-NetTCPConnection -State Listen -LocalPort 48884,48885` is empty.
2. Start instance A with no model. Poll `GET http://127.0.0.1:48884/revit_mcp/status/` until it answers (a 503 "No active Revit document" counts as up). Do not start B before this — registration happens before the server answers.
3. Start instance B (optionally a different Revit version, e.g. 2024 and 2027, so the two are unmistakable). Poll `GET http://127.0.0.1:48885/revit_mcp/status/`.
4. Listener proof: `Get-NetTCPConnection -State Listen -LocalPort 48884,48885 | Select LocalAddress,LocalPort,OwningProcess` must show exactly one row per port with two different PIDs; map with `Get-Process -Id <pid>`. Cross-check with `GET http://127.0.0.1:48884/routes/sisters` (pyRevit built-in; `process_id` and `server_port` per server; a duplicated `server_port` shows up here too).
5. Open a different model in each through `/open_model/` (never a workshared model on the command line).
6. Client config with two entries, e.g. `{"revit-a": {… "env": {"REVIT_HOST": "127.0.0.1", "REVIT_PORT": "48884"}}, "revit-b": {… "env": {"REVIT_HOST": "127.0.0.1", "REVIT_PORT": "48885"}}}` (same `command`/`args` as the existing entry). In ONE assistant session call `get_revit_status` on each; record `host:port` and `document_title`. Also check the model can name both documents in one reply (A5).
7. D-23 overlap experiment (record, don't gate): against instance A only, with `curl.exe --data-binary` and `-H "Content-Type: text/plain"`, send `/execute_code/` with a code body that sleeps a few seconds on Revit's thread and prints a marker "A"; while it runs, send a second `/execute_code/` printing "B", then a GET `/list_levels/`, and a GET `/status/`. Record: each caller's response vs its marker, how many times each body ran, whether `/status/` answered immediately, and whether anything hung. Then fully restart that Revit. The outcome feeds the `bridge.py` docstring and Open Question 1.
8. Negative probes: `REVIT_PORT=abc` (and `""`) makes the server exit non-zero with a stderr message and an untouched stdout; `REVIT_PORT=48999` (nothing listening) makes `get_revit_status` report the target `127.0.0.1:48999` in a connection error rather than silently using 48884.

## Security Domain

`security_enforcement` is not set to false anywhere (no `.planning/config.json` exists), so it is treated as enabled. This phase adds no authentication, no secrets and no new network surface.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Out of this phase (SEC-* are Phase 3/5). Do not add a header or token path. |
| V3 Session Management | no | `stateless_http=True` unchanged; the lock is process state, not session state. |
| V4 Access Control | partial | The lock is *not* an access control. Docs must not present it as one (SER-05): a second client, curl or `/execute_code/` bypasses it. |
| V5 Input Validation | yes | `REVIT_PORT` strict parse (ASCII digits, 1..65535, refuse otherwise); `REVIT_HOST` already an env string used to build a URL. |
| V6 Cryptography | no | none |
| V7 Error handling/logging | yes | Error strings must not leak more than today; never write to stdout under stdio; stderr only for the config refusal. |
| V12/V13 Communications | unchanged | Loopback HTTP, `trust_env=False` stays mandatory (commit `f0af5b0`) so no environment proxy ever sees the traffic. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Typo'd `REVIT_PORT` silently targets a different Revit instance (wrong model mutated) | Tampering / Spoofing | Refuse to start on invalid value (D-05); show target `host:port` in `get_revit_status` (D-06). |
| Over-claimed serialization gives false confidence against a second client | Repudiation / Tampering | Honest scope in `bridge.py`, `CLAUDE.md`, README (D-15, SER-05); doc-pin test. |
| Mutation "not sent" vs "maybe applied" confusion leads to a blind retry that double-applies | Tampering | Distinct, explicit messages (D-12, D-13); never start with digits; never render as success. |
| Environment proxy intercepts loopback calls | Information disclosure | `trust_env=False` retained in the moved client; existing test retargeted. |
| `print()` to stdout corrupts the MCP stdio stream | Denial of service | stderr only; one `ctx.info` guarded by `if ctx:`. |

## Sources

### Primary (HIGH confidence)
- Repo files read this session: `main.py` (22-24, 33-47, 76-102), `tools/__init__.py`, `tools/utils.py` (`format_response`), `tools/status_tools.py`, `tools/process_tools.py` (52-86), `tests/unit/test_local_bridge_transport.py`, `tests/unit/test_textutils.py` (276-290), `tests/unit/test_format_response.py` (149-187), `tests/unit/conftest.py`, `pyproject.toml`, `deploy/build-payload.cmd` (95-125), `deploy/gate.py`, `deploy/server.py`, `scripts/conventions.py:29`, `revit_mcp/status.py`, `revit_mcp/analysis.py`, `revit_mcp/clash.py`, `revit_mcp/colors.py` (list_category_parameters), `revit_mcp/worksharing.py` (`/model_worksets/`, header comment), all `.planning/` context documents, vault note on the double listener.
- Installed pyRevit 6.5.3 source at `%APPDATA%\pyRevit-Master\pyrevitlib\pyrevit`: `routes/server/server.py` (41-42, 109-110, 115-117, 128, 132, 164, 251), `routes/server/handler.py` (100, 146-152, 305-309), `routes/server/serverinfo.py` (76-118), `routes/api.py` (`/routes/status`, `/routes/sisters`), `routes/__init__.py` (`route` decorator returns `f`), `coreutils/moduleutils.py` (`has_any_arguments` via argspec), `coreutils/appdata.py`, `loader/sessionmgr.py:177-183`, `userconfig.py:454-465`; `pyrevit configs routes --help` output.
- `.venv/Lib/site-packages/mcp/server/lowlevel/server.py:507-510` (`tg.start_soon` per incoming message, so tool calls run concurrently), `mcp/server/fastmcp/server.py:950-953,1042-1044`, `anyio/pytest_plugin.py:173-175`.
- Prototype runs (scratchpad, not in repo): 16 tests passed with the repo's own venv; lock cross-loop `RuntimeError` reproduced; anyio trio-param failure reproduced.

### Secondary (MEDIUM confidence)
- [pyRevit `develop` `serverinfo.py` and `server.py` via raw.githubusercontent.com](https://github.com/pyrevitlabs/pyRevit/tree/develop/pyrevitlib/pyrevit/routes/server) — same port selection and the same module-level shared handler with no lock.
- [pyRevit releases (GitHub API)](https://api.github.com/repos/pyrevitlabs/pyRevit/releases) — v6.5.5.26237, v7.0.0.26278 published 2026-10-06.

### Tertiary (LOW confidence)
- [Camera-FOV issue #5](https://github.com/RaulKalev/Camera-FOV/issues/5) ("If Revit has not executed the previous event yet, a later action can replace its payload") versus an Autodesk-forum summary that raised events "are queued and executed sequentially" — conflicting; unresolved, hence A1 and D-23.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — nothing new; versions read from the project venv.
- Architecture (lock seam, budget, classification): HIGH — prototyped and run.
- Allowlist correctness: HIGH for the five routes (handlers read; no `Transaction` in `analysis.py`/`clash.py`; `/list_category_parameters/` only collects and reads; `/model_worksets/` reads worksets from disk and its module states it opens no transaction). Not exhaustively audited for non-model side effects (e.g. memory/CPU on huge models).
- pyRevit port assignment: MEDIUM — source-verified on 6.5.3 and `develop`, not yet live; fleet 6.5.5 unread.
- pyRevit shared-handler race: MEDIUM — structure source-verified; Revit's `Raise()` coalescing semantics unresolved, hence D-23.
- Pitfalls: HIGH for test/tooling ones (reproduced), MEDIUM for live ones.

**Research date:** 2026-10-06
**Valid until:** 2026-11-05 for the CPython design; re-check pyRevit findings if the fleet moves off 6.5.5.
