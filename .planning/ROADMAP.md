# Roadmap: revit-mcp-server

## Overview

Milestone v0.1 «Доверенный мост» adds a trust layer onto a working 54-tool dual-runtime
bridge, without touching the 23 existing domain modules where it can be avoided. The path
runs from the fully CPython-testable, no-Revit-restart-required work (serialization,
configurable addressing, secret/integrity helper logic, honest per-route outcomes) through
a single deliberately-late convergence phase that wires everything into `startup.py` live
(the one phase that costs a full Revit restart per iteration), and finishes with a
structured audit log built on top of outcomes that are, by that point, already honest.
Two hard orderings shape this sequence: `commit_and_report`/honest-batch-reporting must
exist before the audit log is built on it (an audit log built earlier would faithfully
record the same false successes it exists to expose), and configurable-port plus
two-listener detection must land before or alongside per-instance/per-document addressing
(addressing "the instance on port X" is incoherent while two processes can share a port).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Serialization and configurable addressing** - Mutating calls from this server queue instead of racing, `/status/` stays responsive throughout, and the Revit port this server talks to is no longer hardcoded
- [ ] **Phase 2: Secret gate and payload integrity (unit-verified)** - The shared-secret compare and the file-manifest integrity check are built and unit-tested on both runtimes, plus the build pipeline that generates the secret and the manifest, ready to wire in
- [ ] **Phase 3: Honest outcomes on every mutating route** - Every mutating route, including the two known stragglers, reports what actually happened in Revit rather than an assumed success
- [ ] **Phase 4: Live identity, ambiguity refusal, and multi-document addressing** - Every response names the document and process that handled it, two listeners on one port produce an explicit refusal instead of a coin-flip, and an engineer can list, address, and switch between documents open in one Revit session — with the secret gate and integrity check now live and enforced
- [ ] **Phase 5: Structured audit log of true outcomes** - Every mutation lands in a local, rotation-capped JSONL log carrying the same honest outcome the client saw, without leaking the secret

## Phase Details

### Phase 1: Serialization and configurable addressing
**Goal**: Mutating calls issued through this MCP server no longer reach Revit's single-threaded API in parallel, and the server's target port is a deployment setting instead of a hardcoded constant.
**Depends on**: Nothing (first phase)
**Requirements**: SER-01, SER-02, SER-03, SER-04, SER-05, IDENT-05
**Success Criteria** (what must be TRUE):
  1. Two mutating tool calls issued back-to-back never open overlapping Revit transactions from this server — verified with a concurrent-request test that holds one call and confirms the second waits.
  2. `/status/` and other read-only calls return promptly even while a mutating call holds the serialization lock — verified with a concurrent test, not inferred from code shape.
  3. A mutating call that times out, throws, or is cancelled releases the lock immediately — verified by forcing an exception inside the locked region and re-acquiring right after.
  4. Waiting in the queue does not shrink a call's own request timeout budget below what an unqueued call would get.
  5. Setting `REVIT_PORT` changes which port this server talks to, exercised against a live Revit instance bound to a non-default port (the fleet's own precedent — pyRevit already puts a second instance on 48885 — makes this cheap to verify live).
  6. The documented scope of serialization is explicit and honest: it covers calls issued through this one process only; it is not represented anywhere as a guarantee against a second client, curl, or `/execute_code/` called directly.
**Plans**: TBD

### Phase 2: Secret gate and payload integrity (unit-verified)
**Goal**: The logic that will reject an unauthenticated mutation and detect a tampered `revit_mcp/` payload exists, is correct on both runtimes per the unit-test suite, and is generated consistently by the build pipeline — but is not yet wired into a live route. This phase's output is inert by design (ARCHITECTURE.md's build-before-wiring ordering): live enforcement is Phase 4's job, which is deliberately the only phase requiring a Revit restart per change.
**Depends on**: Nothing (parallel to Phase 1, different runtimes/files)
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04, SEC-05, SEC-06, SEC-07, SEC-08, INTG-01, INTG-02, INTG-03, INTG-04, INTG-05, INTG-06, INTG-07, INTG-08
**Success Criteria** (what must be TRUE):
  1. A unit test proves the secret-compare helper rejects a wrong or missing secret and accepts a correct one, on both the CPython side and the IronPython-targeted logic, with the secret read from the `text/plain` body via `parse_request_data()` — never a new header-parsing path.
  2. A unit test proves the secret-compare helper runs in constant time using whatever primitive is confirmed available on pyRevit's hosted CLR (`CryptographicOperations.FixedTimeEquals` if present; a hand-rolled fixed-length compare with a documented fallback reason if not) — this requires the live CLR-availability check called out in Research Flags before the implementation is finalized, not assumed.
  3. A unit test proves an auth failure is designed to surface as a non-200 status distinct from 409 (`rolled_back`'s reserved meaning), matching the existing `_revit_call` string-passthrough contract, with a paired regression test in the style of the existing `rolled_back` test.
  4. A unit test proves the secret never appears in an exception message or log line produced by the compare helper itself.
  5. A unit test proves the manifest-generation logic builds its file list from `git ls-files` (or equivalent tracked-file source), not a filesystem walk — so `__pycache__`, `.pyc`, and line-ending normalization cannot produce a false mismatch.
  6. A unit test proves the integrity check's three-state model (`verified_match` / `verified_mismatch` / `unverifiable`) never collapses "reference unreachable" into "mismatched," and that the check function itself never writes a file under any input.
  7. The build pipeline (`deploy/config.cmd` or equivalent) generates one shared secret and one file-hash manifest per build, consumed identically by both the payload and the extension side, immediately after the `revit_mcp` copy step so the manifest cannot describe a different tree than what shipped.
  8. On the dev machine's junction layout, running the integrity check against the live working tree reports `verified_match` (or an explicit, non-blocking `unverifiable`) — never a spurious mismatch that would (once wired in Phase 4) block mutations for every developer.
**Plans**: TBD

### Phase 3: Honest outcomes on every mutating route
**Goal**: Every mutating route reports what Revit actually did — including partial batch failure and rollback — never an assumed or collapsed success. This is a hard prerequisite for Phase 5's audit log, not parallel work: an audit log built against routes that still collapse partial failure into `status: success` would faithfully record the same lie it exists to expose.
**Depends on**: Nothing (independent of Phases 1, 2, 4; must complete before Phase 5)
**Requirements**: TRUTH-01, TRUTH-02, TRUTH-03, TRUTH-04
**Success Criteria** (what must be TRUE):
  1. Every mutating route's response reflects the real `TransactionStatus` Revit returned, not a value assumed at the call site — exercised against at least one route per module family (single-element, batch, export).
  2. `delete_elements` and `export_ifc` are migrated onto `commit_and_report`, closing the two known remaining gaps named in PROJECT.md's Context.
  3. A batch operation run against a mix of valid and invalid element ids returns the succeeded and skipped/failed ids alongside each other, not only a count.
  4. A batch operation's partial failure produces a status distinguishable both from full success and from full failure — exercised live against at least one batch route with an intentionally-invalid id mixed in.
**Plans**: TBD

### Phase 4: Live identity, ambiguity refusal, and multi-document addressing
**Goal**: Every response can be attributed to a specific document in a specific Revit process; two processes listening on the same port produce a loud, named refusal instead of an unpredictable answer; an engineer can enumerate, address, and switch between documents open in one Revit session. This is the single phase that wires `startup.py` — `api.route` is monkey-patched before the registration loop, activating Phase 2's secret gate and integrity check live at the same chokepoint, at the cost of the one Revit-restart-per-iteration cycle this milestone budgets for.
**Depends on**: Phase 1 (port configurability), Phase 2 (secret/integrity logic to wire in)
**Requirements**: IDENT-01, IDENT-02, IDENT-03, IDENT-04, AMBIG-01, AMBIG-02, AMBIG-03, AMBIG-04, MDOC-01, MDOC-02, MDOC-03, MDOC-04, MDOC-05
**Success Criteria** (what must be TRUE):
  1. `/status/` returns PID, Revit version, port, and a session token issued once at process start — confirmed live against a running Revit instance.
  2. A mutating route's response names the document it changed (title and path), re-derived at request time rather than cached — confirmed live across an `OpenAndActivateDocument` call and a manual UI document switch, per the existing defensive re-fetch pattern this codebase already established for the null-document bug.
  3. Two Revit instances both showing the untitled title `Project1` are distinguishable by response fields alone — confirmed live with the two-Revit-instance test bench.
  4. Starting a second Revit process bound to the same port as an already-running one produces an explicit, named refusal (not a request silently answered by whichever process the OS happened to pick) that identifies both conflicting PIDs — confirmed live by intentionally creating the two-listener condition.
  5. With identity now visible in every response, the still-open `param-write-rolls-back` "wrong process answered" hypothesis is re-run live and its outcome (confirmed or ruled out) is recorded.
  6. An engineer can list every open document in the session with its identity, address a mutating call at one explicitly, and switch which document is active via its own tool call — confirmed live with more than one model open in one session.
  7. A mutating call that omits the document argument follows a documented, explicit default (not a silent guess) stated in the tool's own docstring.
  8. Addressing a document that was closed after being listed produces a clear, named error rather than the call silently operating on a different, currently-open document.
  9. The secret gate and integrity check from Phase 2 are now live and binding: an unauthenticated mutation is rejected before any transaction opens, and a deliberately corrupted `revit_mcp/` file is detected and reported by `/status/` while reads keep working — both confirmed live, in the same restart cycle as the identity work above.
**Plans**: TBD

### Phase 5: Structured audit log of true outcomes
**Goal**: Every mutation is recorded in a local, structured, honest log — reflecting Phase 3's real per-element outcomes, not the request's stated intent — without becoming a second place the shared secret leaks. Deliberately last: both research documents agree this is the single highest-value ordering decision in the milestone.
**Depends on**: Phase 3 (honest outcomes to log), Phase 4 (identity fields to include in each entry)
**Requirements**: AUDIT-01, AUDIT-02, AUDIT-03, AUDIT-04, AUDIT-05, AUDIT-06, AUDIT-07, AUDIT-08
**Success Criteria** (what must be TRUE):
  1. Every mutation produces a JSONL entry containing timestamp, tool, route, document/instance identity, affected elements, and outcome.
  2. A deliberately-triggered rollback and a deliberately-triggered partial batch failure each produce a log entry that records that true outcome, not a generic "mutation completed" — confirmed live, not inferred from the writer's code shape.
  3. One tool call spanning multiple underlying Revit operations produces log entries sharing one correlation id.
  4. Nothing is ever written to stdout by the audit writer — confirmed by running the stdio transport with logging active and checking the protocol stream stays clean.
  5. Running two Revit instances simultaneously and mutating both does not interleave or corrupt either instance's log entries — confirmed live with the two-Revit-instance test bench.
  6. The log file is subject to a rotation or size cap from its first write, not appended to unbounded.
  7. Grepping the log for the configured secret value returns nothing, across a request that included it, an auth failure, and an exception path.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5
(Phases 1 and 2 have no dependency on each other and may be worked in either order or interleaved; Phase 3 is independent of both but must complete before Phase 5; Phase 4 requires Phases 1 and 2; Phase 5 requires Phases 3 and 4.)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Serialization and configurable addressing | 0/TBD | Not started | - |
| 2. Secret gate and payload integrity (unit-verified) | 0/TBD | Not started | - |
| 3. Honest outcomes on every mutating route | 0/TBD | Not started | - |
| 4. Live identity, ambiguity refusal, and multi-document addressing | 0/TBD | Not started | - |
| 5. Structured audit log of true outcomes | 0/TBD | Not started | - |
