# Project Research Summary

**Project:** revit-mcp-server
**Domain:** Trust/identity/integrity foundation for an existing dual-runtime (CPython + IronPython 3) Revit MCP bridge
**Researched:** 2026-09-21
**Confidence:** MEDIUM-HIGH (stack and architecture claims are HIGH, verified against primary sources including a local pyRevit-Master checkout; feature-comparable-system claims are MEDIUM, web-sourced with no direct vendor testing; several specific items are explicitly flagged LOW/unverified and listed below)

This is not a greenfield research pass -- it targets exactly the four capability areas of milestone v0.1 "Doverennyi most" (shared-secret auth, payload integrity plus self-restore, mutation serialization, structured audit log) plus the configurable-port prerequisite, layered onto a mature 54-tool/23-domain codebase whose conventions and known bugs are already documented in .planning/PROJECT.md and CLAUDE.md.
## Executive Summary

This milestone adds a trust layer to a working dual-runtime bridge, and the single most important architectural finding is that it can be done almost entirely without touching the 23 existing domain modules. pyRevit's Routes API has no middleware -- verified by reading pyRevit's own source, not inferred from docs -- but the api object every domain registrar receives is one mutable instance built once in startup.py and passed by reference. Monkey-patching api.route before the registration loop wraps all 51 routes with a secret check and identity stamp at a cost of roughly 2 changed files (startup.py, main.py) plus 2 new helper modules. The same "already covers everything" property holds for mutation serialization (wrap revit_post in main.py, the sole HTTP chokepoint) and for the audit log. Zero new dependencies are needed anywhere: hashlib.sha256 is safe on both runtimes, asyncio.Lock is the correct serialization primitive, and stdlib logging with a small JSON formatter covers the audit trail. The one real asymmetry is the secret comparison -- hmac.compare_digest is very likely absent from IronPython 3's hmac port (its own docs list new/update/digest/hexdigest/copy and conspicuously omit it), so the Revit side must use .NET's CryptographicOperations.FixedTimeEquals instead. This is a deliberate, documented split, not an oversight.

The recommended approach is: build everything unit-testable on the CPython side first (secret compare, manifest diffing, the per-instance lock/registry), build the IronPython-side helpers as inert, unwired modules second, wire both together in startup.py last, and treat that final wiring step as the only phase requiring a live-Revit verification cycle -- because verifying a revit_mcp/ change costs a full Revit restart (reload-then-request has been observed to crash the process). This ordering minimizes the expensive bottleneck to essentially once per milestone rather than once per capability.

The key risks are not "will this work" but "will it silently re-break something this codebase already fixed once." The audit log is the sharpest case: if it's wired to log the requested mutation rather than commit_and_report's actual per-element outcome, it reproduces the exact silent-success bug (commit c1231f6) this project already paid to fix, but now inside the very feature meant to catch dishonesty. The self-restore feature carries an equally sharp risk: "at start" is ambiguous between "fresh Revit process" and "pyRevit extension reload," and the latter is the documented Revit-crashing path -- a restore wired to the wrong trigger could overwrite a developer's in-progress edit on the dev junction, or worse, retrigger the crash it exists to prevent corruption around. Both risks are avoidable, but only if sequencing respects real dependencies: commit_and_report coverage and honest partial-failure reporting must land before the audit log is built on top of them, not in parallel.

## Key Findings

### Recommended Stack

Zero new dependencies for the entire milestone -- every primitive needed already ships with CPython 3.11+ stdlib, IronPython 3.4-level stdlib, or the .NET BCL that Revit's process already hosts. The workstation constraint (AppLocker/EDR, no network in the payload) makes this a hard requirement, not just tidiness.

Core technologies:
- hmac.compare_digest (CPython) / System.Security.Cryptography.CryptographicOperations.FixedTimeEquals via clr (IronPython 3) -- constant-time secret compare; asymmetric by necessity, not error -- IronPython's own hmac.rst reference omits compare_digest, the strongest available (but not fully conclusive) signal it's absent
- Static bearer token (not HMAC-over-body) -- matches the loopback-only, non-adversarial threat model exactly; HMAC-over-body buys tamper-evidence against a network MITM that doesn't exist under a 127.0.0.1-only bind
- hashlib.sha256 on both runtimes for the payload manifest -- no C-accelerator gap, unlike hmac.compare_digest, so no .NET fallback needed here
- asyncio.Lock (not Semaphore(1), not a queue+worker) -- states the true single-holder invariant honestly; a queue is deferred scope creep since idempotency/retries are explicitly out of scope this milestone
- stdlib logging plus a small custom JsonlFormatter, propagate = False, dedicated FileHandler/RotatingFileHandler only -- never structlog, never a raw open().write(), and never anything that could inherit a root StreamHandler and corrupt the stdio MCP protocol stream
- os.replace (same-volume atomic rename) after a temp-name copy -- the safe pattern for restoring files from a network share without a partial write ever landing on the name startup.py is about to import

### Expected Features

No off-the-shelf system does exactly what this bridge needs (AI-agent-to-desktop-CAD, multiple interchangeable backend processes) -- findings below are drawn from the closest comparables (Playwright/CDP, Selenium/Grid, Jupyter Kernel Gateway, AutoCAD/.NET, PostgreSQL, Terraform) and are MEDIUM confidence, web-sourced, cross-referenced across at least two official-domain sources for every P1 claim.

Must have (table stakes):
- A minimum identity tuple (process/session id + document id + host/port) in every response -- every multi-backend comparable studied stamps some identity; PID alone is a stale-PID trap, so pair it with a session token or start-timestamp
- Explicit, named, loud rejection of a stale/ambiguous backend -- comparable systems fail loud, never silently misroute or soft-degrade
- List-open-documents as an explicit collection before any addressing happens (AutoCAD DocumentManager, Photoshop app.documents, Jupyter kernel-list)
- Per-call explicit document addressing for mutating tools specifically -- an LLM cannot see which document is "active" the way a human sees a focused window, so implicit-active is acceptable for reads only, never for mutations
- The classic 5-field audit minimum: who/what/when/before/after, plus an honest outcome field (success/rolled_back/partial)
- Explicit structured partial-failure status (Terraform's action_reason: replace_because_tainted precedent) -- never collapse partial success into boolean true
- Manifest+hash integrity check at deploy/load time (npm SRI, pip --require-hashes precedent)
- Mutation serialization enforced at the protocol/session layer, not left to caller discipline (Selenium's and Jupyter's single-threaded-backend precedent)

Should have (differentiators specific to this project, not borrowed from any comparable):
- Refuse-to-serve on ambiguous two-listener detection -- no comparable system studied has this scenario as a design case at all, because their transport layers make it structurally impossible; this is genuinely novel work, gated on configurable port landing first
- Shared-secret gate scoped to mutating routes only, leaving reads ungated -- an asymmetry justified purely by this project's own threat model, not a pattern pulled from a comparable
- A correlation id linking one AI tool call to the N underlying Revit operations it triggers -- the OTel GenAI trace_id shape is worth borrowing; the SDK/collector infrastructure is not

Defer (v2+, explicitly anti-features for this milestone):
- Queue-position/ETA feedback while waiting on the single-threaded backend -- not a table stake anywhere studied; a bounded-wait-then-503 is what every comparable single-threaded backend actually does
- Full OpenTelemetry SDK integration -- one process, one HTTP hop; the collector/exporter payoff doesn't apply
- Element-level audit granularity matching (or exceeding) Revit's own worksharing history -- Revit's native Sync history is not itself element-granular (LOW confidence claim, not directly inspected -- flag for spot-check), so this project's route-level audit already meets or exceeds the bar
- Live/hot self-healing of the payload while Revit is running -- already excluded by PROJECT.md's own decision; even Chrome does not attempt this for locally-managed (non-centrally-pushed) artifacts
- Tamper protection against the legitimate local operator (CrowdStrike-style) -- explicitly out of scope per the stated threat model (accidental overwrite, not a hostile console user)

### Architecture Approach

The whole design rests on two already-existing, verified single-instantiation chokepoints: the shared api object built once in startup.py and passed by reference into every register_star_routes(api) call, and the shared _http_client/injected revit_get/revit_post callables built once in main.py and passed into every register_star_tools(...) call. Every one of the four capabilities attaches to one of these two points, which is what keeps the domain-file edit count at zero.

Major components:
1. revit_mcp/security.py (new, Revit side, helper -- no registrar, same sanctioned pattern as textutils.py/utils.py) -- secret verification, identity stamping, and a wrap_api() installer that monkey-patches api.route before the registration loop runs
2. revit_mcp/integrity.py (new, Revit side, helper) -- verify_and_restore(package_dir, manifest), called at the very top of register_routes(), before any revit_mcp domain module has been imported into any IronPython module table -- this is the one moment file replacement is provably safe
3. main.py / new bridge.py (CPython side) -- a RevitTarget registry keyed by (host, port), each holding its own httpx.AsyncClient and its own asyncio.Lock; secret header injection on outgoing POSTs; this is also where the audit log should be written from, since it's the one side guaranteed to be a single writer even when two Revit processes exist
4. deploy/publish-extension.cmd + deploy/config.cmd (build pipeline) -- single source for secret generation shared by both build scripts, and the point where the file-hash manifest and golden copy for restore are generated, immediately after the revit_mcp robocopy so the manifest can never describe a different tree than what actually shipped

### Critical Pitfalls

Ranked here by (likelihood in this environment) times (cost if hit), per PITFALLS.md's own framing -- this project's history shows failures here are systemic (one wrong idiom reproduces across every module that copies it), so "already hit once" pitfalls outrank novel-sounding ones.

1. The audit log records the route's claimed outcome, not commit_and_report's actual one -- reproducing the silent-success bug one layer up, inside the very feature meant to catch it. The two natural integration points (CPython tool wrapper, _revit_call) are both on the wrong side of the real per-element outcome for batch routes. Fix: complete commit_and_report / honest-partial-failure-reporting on every mutating route first, log from the single point that already holds the true outcome (Revit side, where commit_and_report's return dict lives), and treat this as a hard dependency ordering -- audit logging must be the last of the four capability groups to land, not built in parallel.
2. A shared-secret gate resurrects the exact 200-vs-non-200 silent-success trap the rolled_back fix (409) exists to avoid, if the auth-failure status code or shape is decided ad hoc per route instead of via one shared helper with its own tested contract (401/403, never a status-less 200 with an "error" key format_response's hardcoded string set doesn't recognize).
3. Self-restore triggers on pyRevit extension reload, not just fresh-process start -- the exact Reload-crashes-Revit path this project has already documented -- and on the dev junction, silently overwrites in-progress unsaved edits under the guise of "fixing corruption." Gate restore on an unambiguous new-process signal, disable it outright on the dev junction, and never wire a live file-write into a code path reachable from the Reload button.
4. A client-side asyncio.Lock in main.py only serializes calls issued through that one process -- it gives false confidence against a second MCP client, curl, or /execute_code/ hit directly, none of which route through the lock. Document its actual scope precisely and confirm (live, not by assumption) what Revit's own external-event queue already does with two overlapping requests before overselling the lock as a correctness guarantee rather than harm reduction.
5. Hash-based integrity verification breaks on ordinary differences between dev-junction and pilot-copy deployments (pycache/.pyc, core.autocrlf line-ending normalization) unless the manifest is derived from git ls-files, not a filesystem walk -- otherwise a verifier can "restore" perfectly good files in a loop, and if self-restore isn't purely start-time-gated (see item 3), each pass risks a crash.
6. Holding the mutation lock across the full 30s _revit_call timeout, if naively wrapped around "all calls" rather than "mutating calls only," starves /status/ -- the one diagnostic surface meant to answer "why is everything hung" becomes unavailable exactly when something is hung. /status/ must be explicitly excluded from the lock and remain unauthenticated even after the secret gate lands.

## Implications for Roadmap

Based on combined research, suggested phase structure:

### Phase 1: CPython-side foundations (lock/registry, secret injection, audit writer) -- no wiring
Rationale: This is the fully unit-testable half; STACK.md and ARCHITECTURE.md agree it can proceed independently and in parallel with Phase 2, and PITFALLS.md's most severe risks (audit log dishonesty, lock scope-creep, stateless_http assumptions) are best caught by tests written here, before any live-Revit dependency exists.
Delivers: RevitTarget registry keyed by (host, port) each with its own asyncio.Lock; secret header injection in _revit_call/revit_post; the audit JsonlFormatter plus instance-namespaced RotatingFileHandler (never attached to root logger); configurable REVIT_PORT via env var.
Addresses: Identity tuple table stake, mutation serialization table stake, shared-secret differentiator.
Avoids: Pitfall 4 (lock scoped only to mutating calls, /status/ excluded), Pitfall 5 (module-global lock, not session-scoped), Pitfall 7 (async with lock exclusively).

### Phase 2: Revit-side helpers (security.py, integrity.py) -- inert, unwired
Rationale: Same "build before wiring" argument as Phase 1, on the other runtime. Can proceed in parallel with Phase 1. Deliberately does not touch startup.py yet -- safe to merge early with zero blast radius.
Delivers: revit_mcp/security.py (secret verify via FixedTimeEquals, identity-stamp logic, wrap_api() installer) and revit_mcp/integrity.py (verify_and_restore using a git-ls-files-derived manifest, three-state model: verified_match / verified_mismatch / unverifiable).
Uses: System.Security.Cryptography.CryptographicOperations.FixedTimeEquals, hashlib.sha256 on both runtimes.
Implements: The api-monkey-patch mechanism and the load-time-only restore boundary from ARCHITECTURE.md.

### Phase 3: commit_and_report completion plus honest partial-failure reporting on remaining routes
Rationale: FEATURES.md and PITFALLS.md both independently flag this as a hard prerequisite for the audit log, not parallel work -- an audit log built against routes still returning bare status: success on partial batch failure encodes the old lie structurally. This is unrelated to the cross-cutting wrapper mechanism (ARCHITECTURE.md is explicit: it's a small, separately-budgeted, per-route fix) and can proceed at any point, but must complete before Phase 6.
Delivers: commit_and_report applied to editing.py's delete path and interop.py's export_ifc; batch routes in building.py/clash.py/analysis.py emit a requested/succeeded/skipped/failures shape instead of collapsing partial skips into status: success.
Addresses: The "explicit structured partial failure" table stake.

### Phase 4: Deploy pipeline -- secret and manifest generation
Rationale: Needs Phase 1/2's interface shapes decided (what the secret header/field looks like, what the manifest schema is) but not their full implementation, so it can start once those are fixed rather than waiting for full completion.
Delivers: Shared secret generated once in deploy/config.cmd, consumed by both build-payload.cmd and publish-extension.cmd; file-hash manifest plus golden copy generated in publish-extension.cmd immediately after the revit_mcp robocopy.
Implements: The build-pipeline placement table from ARCHITECTURE.md.

### Phase 5: Wire startup.py -- the single live-Revit-verification phase
Rationale: This is the one phase that requires a full Revit restart per change (reload-is-unsafe), so ARCHITECTURE.md's suggested build order explicitly defers it until everything else exists and is unit-tested, to minimize live-verification cycles to essentially one.
Delivers: api = security.wrap_api(api) installed before the domain registration loop; integrity.verify_and_restore(...) called at the top of register_routes(), before any domain import; the two-listener refuse-to-serve check (now cheap, since identity tuple plus configurable port both exist).
Addresses: All remaining Active requirements that depend on the wrapper being live.
Avoids: Pitfall 3 (self-restore-on-reload vs fresh-start ambiguity) -- this is the design gate to resolve before merging this phase, with an explicit live test: open Revit, click Reload, confirm no restore fires; kill and restart, confirm it does.

### Phase 6: Structured audit log, wired to true outcomes
Rationale: Deliberately last. Both FEATURES.md's dependency graph and PITFALLS.md's top pitfall agree: the audit log's only defensible source of truth is commit_and_report's actual return shape (Phase 3) flowing through a serialized write path (Phase 1). Building this earlier guarantees it inherits whatever partial-failure lies still exist upstream.
Delivers: Audit entries with the 5-field minimum plus honest outcome, written from the CPython side (single-writer guarantee even across two Revit processes), redaction of the secret field applied at the single log-writing function, rotation from day one.
Avoids: Pitfall 1 (silent-success-one-layer-up), Pitfall 12 (interleaved/corrupted concurrent writes -- solved by instance-namespacing per STACK.md), Pitfall 13 (secret/PII leakage into the log).

### Phase Ordering Rationale

- Phases 1 and 2 can run in parallel (different runtimes, zero shared files) -- this is the fastest path to Phase 5, which is the true bottleneck.
- Phase 3 (commit_and_report completion) is inserted as a hard gate before Phase 6 specifically because two independent research docs (FEATURES.md's dependency graph, PITFALLS.md's top pitfall) converge on the same conclusion from different angles: treating them as unrelated work items is the single most likely way to ship a dishonest audit log.
- Phase 5 is placed last among the "wiring" phases (not first) precisely because it is the only phase requiring a live-Revit restart per iteration -- every other phase should be as complete and unit-tested as possible before it, per ARCHITECTURE.md's explicit "Suggested Build Order" rationale.
- Phase 4 (deploy pipeline) is allowed to overlap with Phases 1-3 once interfaces are fixed, since it has no runtime dependency on the wiring itself.

### Tensions the roadmap must decide explicitly (docs disagree or under-specify)

- Two-listener refusal timing: FEATURES.md places "refuse-to-serve on ambiguous two-listener detection" in v1.x (Add After Validation), calling it cheap once prerequisites land but not blocking. PROJECT.md's own Active requirements list it as in-scope for v0.1 itself, and the still-open param-write-rolls-back bug's unresolved "wrong process answered" hypothesis arguably makes it load-bearing for this milestone, not a follow-up. The roadmap must pick one; research does not resolve this for you.
- Per-call instance addressing shape: ARCHITECTURE.md flags MEDIUM confidence on whether the milestone wants an explicit port/instance argument on every mutating tool call, versus a session-level "active instance" set once via a switch_active_instance tool. The registry/lock object model is correct under either resolution, but the calling convention differs -- this is a product decision, not something research can settle.
- Where the secret travels: PITFALLS.md recommends the secret ride inside the text/plain JSON body (reusing the already-proven parse_request_data path) specifically to avoid an untested second code path for header extraction. STACK.md's worked examples show it as a header (X-Revit-MCP-Token) with MEDIUM confidence on pyRevit's header-casing behavior. These are in tension -- verify header behavior live before choosing headers over body, per the verification list below.

### Research Flags

Phases likely needing deeper research during planning:
- Phase 5 (wire startup.py): the reload-vs-fresh-start detection mechanism has no confirmed pyRevit API answer (does pyRevit distinguish "engine reload" from "extension reload" from "Revit process start"?) -- flagged explicitly in PITFALLS.md as needing live verification, not assumption.
- Phase 6 (audit log): the exact schema for batch-route partial-failure payloads needs to be nailed down against real batch-route behavior before the audit consumer is built against it.

Phases with standard patterns (skip research-phase):
- Phase 1 (CPython foundations): asyncio.Lock, httpx.AsyncClient registries, and stdlib logging are all well-documented, HIGH-confidence patterns already partially precedented in this codebase's own main.py.
- Phase 4 (deploy pipeline): extends existing, already-read deploy .cmd scripts with one more generation step; no novel pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH for stdlib/BCL API claims (official docs, primary sources); MEDIUM for the hmac.compare_digest-absent-in-IronPython-3 claim specifically (absence-of-evidence from IronPython's own docs, not an explicit "unimplemented" statement) |
| Features | MEDIUM -- every P1 claim corroborated across two or more independent official-domain sources, but no comparable system was tested directly; several claims explicitly marked LOW/inferred (the two-listener scenario has no external precedent at all -- genuinely novel to this project) |
| Architecture | HIGH -- every chokepoint claim verified by reading this repo's actual code and a local pyRevit-Master source checkout, not pyRevit's docs (which are silent on the relevant internals) or inference |
| Pitfalls | HIGH for claims tied to this repo's own documented history (silent rollback, IronPython-2-builtin misdetection, null-document bug); MEDIUM for Revit API/Transaction-semantics claims verified against Autodesk docs but not exercised live in this environment |

Overall confidence: MEDIUM-HIGH -- the mechanism-level architecture and stack findings are unusually well-grounded (primary source reads, not inference), which is exactly what makes the remaining gaps worth taking seriously rather than assuming away.

### Gaps to Address

A live Revit test bench is available for this milestone -- the items below should be verified on a pilot machine before implementation, not assumed:

- pyRevit request.headers case-sensitivity/normalization -- undocumented; verify with a live request before hardening any header-based secret check (this also feeds the "secret in header vs. body" tension above).
- Whether System.Security.Cryptography.CryptographicOperations exists on the exact .NET runtime pyRevit's IPY342 engine hosts -- FixedTimeEquals requires .NET Core 2.1+/.NET Standard 2.1+; if the hosted CLR predates this, fall back to a hand-rolled fixed-length XOR-accumulate compare (never a == b or a.Equals(b)).
- Exact pyrevit configs routes port CLI semantics (auto-increment behavior across instances) -- sourced from community/secondary references, not pyrevitlabs.io directly; run pyrevit configs routes --help on a pilot machine before relying on it in code.
- What Revit's external-event queue actually does today with two overlapping mutating requests (hang? error? silent serialize?) -- PITFALLS.md flags this as inferred from Autodesk's Transaction-semantics docs only, not exercised live; this materially changes what the asyncio.Lock is even for (correctness guarantee vs. harm-reduction/UX).
- Whether pyRevit distinguishes extension-reload from fresh-process-start in any exposed API -- needed to safely gate self-restore; PITFALLS.md is explicit this must not be assumed.
- Revit's native worksharing/Sync-history granularity -- the FEATURES.md anti-feature argument (don't chase element-level parity) rests on a LOW-confidence, not-directly-inspected claim; spot-check via a live "Show History" panel if this later matters for scoping the audit log's ambition.

## Sources

### Primary (HIGH confidence)
- This repository, read directly: main.py, startup.py, tools/utils.py, revit_mcp/utils.py, revit_mcp/textutils.py, revit_mcp/editing.py, revit_mcp/status.py, revit_mcp/registry.py, tools/editing_tools.py, deploy .cmd scripts, deploy/gate.py, extension.json, CLAUDE.md, .planning/PROJECT.md
- Local pyRevit-Master checkout (pyrevitlib/pyrevit/): routes/api.py, routes/server/router.py, routes/server/handler.py, routes/server/server.py, loader/sessionmgr.py, extensions/components.py, loader/hooks.py -- ground truth for "no middleware exists" and extension load ordering
- pyRevit official docs: docs.pyrevitlabs.io/reference/pyrevit/routes/ and routes/server/ -- Request/Response shape, activate_server() config sourcing
- Microsoft Learn / .NET docs -- CryptographicOperations.FixedTimeEquals, stable since .NET Core 2.1
- Python official docs -- asyncio-sync.html (Lock vs Semaphore semantics)
- IronPython docs (ironpython-docs/library/hmac.rst, hashlib.rst) and github.com/IronLanguages/ironpython3

### Secondary (MEDIUM confidence)
- Community sources on pyrevit configs routes port auto-increment behavior (Notion page, search snippets -- not pyrevitlabs.io directly)
- Selenium, Jupyter Kernel Gateway, CDP, AutoCAD .NET, Photoshop UXP, PostgreSQL, Terraform official docs -- feature-comparable analysis, each corroborated across two or more sources for P1 claims
- OpenTelemetry GenAI semantic conventions blog posts -- emerging (2026) convention, not yet universal

### Tertiary (LOW confidence)
- Revit worksharing/Sync-history granularity claim (Autodesk help plus community blog summary, not directly inspected)
- The two-listener-refusal scenario as a "differentiator" -- explicitly inferred beyond search; no external precedent found for this exact failure mode
- CPython RotatingFileHandler Windows rotation-failure behavior -- issue-tracker discussion, not a documentation guarantee

---
Research completed: 2026-09-21
Ready for roadmap: yes
