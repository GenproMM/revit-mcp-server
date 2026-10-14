# Phase 1: Serialization and configurable addressing - Context

**Gathered:** 2026-09-23 (`--auto`), revised 2026-09-30 (interactive discussion with the user)
**Status:** Ready for planning
**Revision note:** the 2026-09-30 interactive discussion supersedes three `--auto` decisions of
2026-09-23 — queue for every POST (now: POST with a read-only allowlist, D-08), `REVIT_QUEUE_TIMEOUT`
120 s (now: queue bound = call timeout, D-11), live check on a single second Revit (now: two-Revit
bench + cross-instance scenario + stop condition, D-16..D-18). All other `--auto` decisions are kept
(D-19..D-26). Alternatives for both rounds are in `01-DISCUSSION-LOG.md`.

**Revision note 2026-10-07:** the 01-04 bench measured cross-wiring in pyRevit's shared request
handler (`cross-wired-mutation`, `cross-wired-read`; see `01-04-SUMMARY.md` "Bench record", Step 7).
D-28 to D-31 (section "Resolved after the 01-04 bench") supersede D-08, D-03, D-17, D-21 (its
two-entry part) and D-26. The superseded text is kept as written and marked in place.

<domain>
## Phase Boundary

Mutating calls issued through one MCP server process are serialized against their Revit
target, read-only calls stay responsive while a mutation holds the queue, and the Revit
port this server talks to becomes a deployment setting (`REVIT_PORT`) instead of the
literal in `main.py:23`. Requirements: SER-01..05, IDENT-05. No edits under `revit_mcp/` —
the phase is CPython-side and needs no Revit restart except for the live port check.

> Superseded 2026-10-07 by D-28: only `/status/` stays responsive; every other call, reads
> included, queues behind a held lock.

**What this phase does NOT deliver (stated so no downstream agent over-claims it):**
addressing a specific *document* among several open in one Revit session, PID/session
token in responses, and refusal when two Revit processes share one port. Those are
IDENT-01..04, AMBIG-01..04, MDOC-01..05 — now **Phase 2** after the roadmap reorder
decided in this discussion (D-01). After Phase 1 every route still operates on the
active document of the targeted Revit instance.

**User's goal that shaped this discussion:** in one assistant session, work with several
documents — including documents open in *different* Revit instances — e.g. to compare
data between them. Phase 1 delivers the cross-instance half of that; Phase 2 delivers the
cross-document half.

</domain>

<decisions>
## Implementation Decisions

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
  - Superseded 2026-10-07 by D-29.
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
  - Superseded 2026-10-07 by D-28; the allowlist was the measured cross-wired-read;
    `READ_ONLY_POST` is removed by plan 01-06 and GET and `revit_image` take the lock too;
    D-09 stands.
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
  - Extended 2026-10-07 by D-30: the docs also state that overlapping sessions against one Revit
    can still cross-wire (cross-process cross-wiring) until d27-c lands.

### Live acceptance
- **D-16:** Acceptance bench = two Revit instances started together (boot without a model, open
  through `/open_model/` — never a workshared model on the command line). Verify with
  `Get-NetTCPConnection -State Listen` that 48884 and 48885 each have exactly one listener with
  different PIDs — this also closes the research flag on pyRevit's port auto-increment
  (`.planning/research/STACK.md`, MEDIUM confidence). *Supersedes 2026-09-23 D-12.*
- **D-17:** Acceptance includes the user's cross-instance scenario: one assistant session with
  both `revit-a` and `revit-b` entries, a different model open in each; each entry's
  `get_revit_status` returns its own `host:port` and its own `document_title`.
  - Superseded 2026-10-07 by D-29.
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
  - Two-entry example dropped 2026-10-07 by D-29; the `CLAUDE.md` port fix and the `REVIT_PORT`
    docs as a deployment setting stand (plan 01-07).
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

### Resolved at plan time (2026-10-06, after RESEARCH.md)
- **D-25:** D-18 reads the **staggered** bench run as acceptance: instance B is launched only after
  instance A answers `/status/`. D-18 fires only if the staggered launch still puts both on 48884.
  A truly simultaneous launch is also run and its outcome recorded as a launch-order finding;
  staggered start becomes the documented procedure for multi-instance setups.
- **D-26:** The two-entry setup (`revit-a` / `revit-b`) is scoped to the **stdio** transport in
  this phase — docs and live acceptance use stdio only. HTTP/SSE multi-entry needs a configurable
  MCP listen port (hardcoded 8000) and is deferred; the docs say so explicitly.
  - Superseded 2026-10-07 by D-29.
- **D-27:** If the D-23 experiment shows a read hijacking a pending mutation through pyRevit's
  shared handler, execution **stops at a checkpoint for the user** — options: (a) accept and
  document, (b) lock every API-context route and exempt only `/status/` and `/model_info/`
  (changes SER-02's meaning), (c) Revit-side fix in a later phase. Not chosen unilaterally.
  - Resolved 2026-10-07: option (b), narrowed by the user, see D-28; option (c) is recorded as a
    backlog item, see D-30.

### Resolved after the 01-04 bench (2026-10-07)
- **D-28 (d27-b, narrowed by the user):** `bridge.py` takes the lock for every call that goes
  through pyRevit's handler (GET reads, `revit_image`, every POST) and exempts only GET
  `/status/`, which pyRevit serves on its HTTP thread and which the bench measured unaffected.
  `/model_info/` stays locked because its overlap was not measured. SER-02 now means "does not
  block `/status/`", and slow reads queue behind mutations. Supersedes D-08. Evidence:
  `01-04-SUMMARY.md` "Bench record", Step 7. — **Reversibility:** reversible (one frozenset plus
  tests), but unlocking a route needs a live overlap measurement and the user's decision.
- **D-29 (a5-a):** the two-instance harness (`tests/test_two_instance_targets.py`,
  `TWO_INSTANCE_OK` on the 01-04 bench) counts as SC5 evidence. Standing product constraint: users
  share ONE `revit` MCP entry and cannot copy it, so the two-entry scheme of D-03 and D-17 is not
  documented for users and `REVIT_PORT` stays a deployment and development setting. Per-call target
  selection inside one server moves to Phase 2 (IDENT-01) with one lock per Revit target. D-02
  (one process = one target) stands as the transport model. Supersedes D-03, D-17 and the
  two-entry parts of D-21 and D-26.
- **D-30 (d27-c to the backlog):** the Revit-side fix for cross-process overlap in pyRevit's shared
  handler is backlog item 999.1 in ROADMAP.md, not a phase. Until it lands, docs say overlapping
  sessions against one Revit can still cross-wire.
- **D-31:** plan 01-05 is superseded (`status: superseded` in its frontmatter) and replaced by gap
  plans 01-06 (d27-b in `bridge.py`), 01-07 (honest-scope docs) and 01-08 (this planning record).

### Claude's Discretion
- Lock primitive details and where exactly the read-only allowlist lives (a set in `bridge.py`,
  a flag at the `revit_post` call site, …), as long as D-08's fail-safe default and its unit test hold.
- How `get_revit_status` obtains `host:port` without tool modules importing the transport
  (e.g. an attribute on the injected callable or an extra injected value) — must respect the
  "tool modules never import the transport" rule.
- Exact function names in `bridge.py`, wording of the queue-busy and outcome-unknown messages,
  MockTransport fixture shape.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and requirements
- `.planning/ROADMAP.md` §Phase 1 — goal and 6 success criteria; reordered phase list (D-01)
- `.planning/REQUIREMENTS.md` §SER, §IDENT-05; MDOC/IDENT/AMBIG now traced to Phase 2
- `.planning/PROJECT.md` §Context — 20-connection pool with no lock; port hardcoded at `main.py:23`; Out of Scope (queue position/ETA)

### Research
- `.planning/research/PITFALLS.md` §Pitfall 5 (advisory lock), §6 (`/status/` starvation), §7 (lock after cancel), §8 (`stateless_http` → module-global lock)
- `.planning/research/ARCHITECTURE.md` §"Should the lock be global or per-target-instance?" — per-target rationale (satisfied by D-07 since one process = one target)
- `.planning/research/STACK.md` §"Configurable port" — `REVIT_PORT` pattern, pyRevit port auto-increment (MEDIUM confidence, verify live per D-16), `asyncio.Lock` vs `Semaphore`, no standalone `fastmcp` middleware

### Code
- `main.py:21-102` — current transport, moves to `bridge.py`
- `tools/status_tools.py` — `get_revit_status`, where `host:port` is surfaced (D-06)
- `deploy/build-payload.cmd:109-116` — payload copy list
- `tests/unit/test_local_bridge_transport.py` — `trust_env=False` check, retarget
- `CLAUDE.md` §Known sharp edges — port line, 30 s timeout line, two Revit on 48884, init-time hangs

### History
- `.planning/debug/param-write-rolls-back.md` — open "wrong process answered" hypothesis; the D-16 listener check is relevant context

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_revit_call` (`main.py:76-102`): the single HTTP exit to Revit; wrapped, not rewritten.
- `main.py:22` `REVIT_HOST = os.environ.get(...)`: the pattern `REVIT_PORT` mirrors, plus validation (D-05).
- The "non-200 → `Error: <code> - <text>`" contract — queue errors reuse it.

### Established Patterns
- Injection of `revit_get`/`revit_post`/`revit_image` into every registrar — unchanged.
- `format_response` treats a dict as an error only with a truthy `error` key or error-like `status`;
  new queue/timeout errors must fit this contract.
- Tools pass custom `timeout=` (e.g. `/status/` 10 s, `process_tools` 5 s); D-11's queue bound follows the per-call value.
- No `print()` under stdio; progress only via `await ctx.info(...)` under `if ctx:`.

### Integration Points
- `main.py` → `from bridge import revit_get, revit_post, revit_image`.
- `deploy/build-payload.cmd` and `deploy/gate.py` — `bridge.py` must ship in the payload and pass the gate.
- `tests/unit/` — lock behavior, allowlist membership (D-08/D-09), `REVIT_PORT` parsing.

</code_context>

<specifics>
## Specific Ideas

- The motivating use case: compare data between documents in one assistant session, including
  documents in different Revit instances (`revit-a` / `revit-b`).
- The queue-busy refusal must say "nothing was sent" in so many words, so the model never treats
  the operation as possibly applied.
- For Phase 2 (recorded so it is not lost): comparing documents inside one instance should ideally
  not force switching the active document in the UI. This is in tension with the old `--auto`
  decision D-14 of the former Phase 4 context ("verification, not retargeting": addressed document
  must be active, else 412) — resolve in the Phase 2 discussion.

</specifics>

<deferred>
## Deferred Ideas

- One MCP server discovering all Revit instances (48884..4888x) and addressing "instance +
  document" per call / a `RevitTarget` registry — rejected for now in favor of D-02/D-04; revisit
  only if D-18 triggers or the fleet regularly runs more than two instances.
  - Revisited 2026-10-07 by D-29: per-call target selection is now Phase 2 scope.
- Runtime target-switch tool — rejected (shared state under `stateless_http`).
- `contrib-kit/revitmcp_kit.py` with a hardcoded `48884` — separate client, not part of IDENT-05.
- Configurable MCP listen port (hardcoded 8000) so two HTTP/SSE-transport entries can coexist — see D-26.

</deferred>

---

*Phase: 01-serialization-and-configurable-addressing*
*Context gathered: 2026-09-23, revised 2026-09-30*
