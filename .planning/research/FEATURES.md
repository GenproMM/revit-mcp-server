# Feature Research

**Domain:** Trust/observability foundation for an AI-driven CAD/BIM automation bridge (multi-instance desktop backend, single-user threat model)
**Researched:** 2026-09-21
**Confidence:** MEDIUM (web-sourced, cross-referenced against official docs for each comparable system; no vendor system was tested directly — see per-claim confidence notes)

## Scope note on comparables

No off-the-shelf system does exactly what revit-mcp-server needs (AI-agent-to-desktop-CAD bridge with multiple interchangeable backend processes). The four capability areas were researched against the *closest* analogous systems per the question brief: browser automation (Playwright, Selenium, CDP), multi-document host apps (AutoCAD, Photoshop, Jupyter, LSP), database/IaC/CDC audit conventions (PostgreSQL, Terraform, generic RDBMS audit tables, OpenTelemetry GenAI conventions), and integrity/self-healing agents (npm/pip, Authenticode, Chrome, CrowdStrike). Every claim below is tagged with the system it came from; where a claim is inferred rather than directly documented, it is marked **[inferred]** and confidence-capped at LOW.

This project is explicitly **single-user desktop, not multi-tenant** (per PROJECT.md: threat model is "AI corrupts the model, a stranger on the network, absence of provability" — not a malicious local operator). Patterns below that only make sense for multi-tenant/distributed systems (e.g., CrowdStrike-grade tamper protection against the legitimate operator) are flagged as **wrong for this project** rather than recommended.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features every comparable system already treats as baseline — missing them here would be a regression relative to the ecosystem norm.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Minimum identity tuple in every response: process/instance id + document id + host/port** | Every multi-backend system studied stamps *some* identity on responses or requires it in the addressing call. PostgreSQL exposes backend PID (`pg_backend_pid()`) so a client can prove which backend process served a connection. CDP requires `targetId` + `sessionId` on every command specifically so a command "affects the right target even when multiple tabs are open." Jupyter Kernel Gateway keys every kernel by a `kernel_id` used in both listing and addressing. None of these systems ship without *some* answer to "which backend/session/target am I talking to." | LOW–MEDIUM | Minimum viable tuple for this project: **Revit process PID (or a session GUID minted at startup) + document title/path + document GUID (if available) + port**. PID alone is reusable after process exit (a stale-PID trap); pair it with a process-start timestamp or a random session token generated once per Revit.exe launch, the way CDP mints a fresh `sessionId` per attach rather than reusing target UUIDs alone. |
| **Explicit, named error when a stale/wrong backend is detected — not silent misrouting** | Selenium Grid's own documented failure mode is instructive: nodes can enter "draining" between session creation and use, and the *only* signal is a hard `NoSuchSessionError` / `InvalidSessionIdException` — there is no soft degradation, no silent retry to a different node. The absence of automatic recovery is itself the convention: comparable systems fail loud, they do not guess. | LOW | Directly addresses PROJECT.md's "two listeners on 48884" and the open `param-write-rolls-back` hypothesis that a different Revit process answered. A response-embedded identity tuple lets the *client* detect drift across calls; the server-side fix (reject a second listener, or make port configurable) is the complementary table-stakes half — see Differentiators. |
| **List-open-documents call, returned as an explicit collection with per-document identity** | AutoCAD's `Application.DocumentManager` collection, Photoshop's `app.documents` array, and Jupyter Kernel Gateway's kernel-list REST endpoint are the three clearest analogs for "host app holds several open documents" and all three expose a queryable list before any addressing happens. This is the universal first step in every multi-document API surveyed. | LOW | Maps directly to the Active requirement "Несколько моделей в одной сессии Revit: перечисление, адресация в вызове, переключение активного." |
| **Per-call explicit document addressing, not just an implicit "active document"** | CDP's `sessionId`-must-prefix-every-command design exists *because* an implicit "current tab" model breaks down under concurrency — CDP deliberately moved away from a single implicit target. Photoshop and AutoCAD both default to an implicit `activeDocument`/`MdiActiveDocument`, but AutoCAD also documents that non-active-document access requires an explicit `LockDocument()` step, i.e. the implicit model is treated as a convenience default layered *on top of* explicit addressing, not a replacement for it. | MEDIUM | For an AI tool-calling context specifically, implicit "active document" is the higher-risk pattern: an LLM cannot see which document is "active" the way a human sees a focused window, so a wrong-document mutation is silent and irreversible (this project's whole threat model). Explicit per-call document identifier should be table stakes for *mutating* tools; an implicit "active/default" convenience is acceptable only for read-only convenience tools, and only if it is overridable per-call. |
| **Audit record with the classic 5-field minimum: who/what/when/before/after** | This is the one truly universal convention: every audit-table reference and every CDC description converges on the same five fields — timestamp, actor/principal, operation type, entity/row key, before-value/after-value. Terraform's plan/apply JSON output and generic RDBMS audit-trigger patterns both reduce to this shape. | LOW–MEDIUM | For this project: timestamp, "actor" = the MCP tool name + document identity tuple (not a human user — there is no human principal per call), operation type = route name, entity = ElementId(s) touched, before/after = parameter or geometry delta where cheaply obtainable, outcome = success/rolled_back/partial. This is exactly what the Active requirement "Локальный структурный журнал аудита всех мутаций с честным результатом" calls for. |
| **Explicit, structured status for partial failure — never silent success** | Terraform's `action_reason: replace_because_tainted` is the concrete precedent: a partially-failed operation gets a *named, structured* state, not a boolean success/fail collapse. This directly validates the PROJECT.md complaint that bulk routes "report success while silently skipping elements" as a real, recognized anti-pattern other mature systems have already solved by naming the partial-failure case. | LOW | This is not a new invention — it is bringing existing bulk routes up to the same standard the project already applied to `rolled_back` (HTTP 409). A parallel "partial" status (e.g. per-element results array with a top-level `status: "partial"` alongside `succeeded`/`skipped` counts) is the direct analog. |
| **Install/deploy-time integrity verification via hash comparison against a manifest** | npm's `package-lock.json` SRI `sha512-...` integrity field and pip's `--require-hashes` mode are the two most mainstream precedents; both hash the artifact and refuse to proceed on mismatch. This is uncontroversial, cheap, and exactly what "manifest+hash files" as a category means. | LOW | Directly maps to the Active requirement "Расхождение файлов payload с эталоном обнаруживается." A flat manifest (path → sha256) shipped alongside the payload and checked at Revit-extension load time is the minimum viable version of this pattern — no code signing infrastructure needed for a single-org internal tool. |
| **Mutation serialization against a single-threaded backend — reject or queue, never allow concurrent writers** | Selenium's own architecture note is explicit: "the blocking nature of the commands means that it only makes sense to have one active session at a time" — commands to one session are sequential by design, not by accident. Jupyter kernels are single-threaded for execution; while busy, the kernel "does not respond to any requests" at all rather than accepting and reordering them. Every single-threaded backend studied enforces serialization at the protocol/session layer, not by hoping callers behave. | MEDIUM | This is the most safety-critical table stake in the whole milestone: PROJECT.md documents an actual httpx pool of 20 concurrent connections hitting a single-threaded Revit API with zero lock/queue/semaphore today. A simple mutex/semaphore around the Revit external-event dispatch (reject with 503, or queue with a short bounded wait) is the minimum; see the concurrency answer below for whether queue-position needs to be surfaced. |

### Differentiators (Competitive Advantage)

Not universal in the comparable systems, but each addresses a specific, named gap this project already identified in its own PROJECT.md — these differentiate a "trustworthy bridge" from a merely functional one.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Refuse-to-serve on ambiguous backend (two listeners on the same port detected)** | No comparable system studied has this exact scenario (two independent OS processes both successfully binding the same port) as a *design case* — it is universally treated as an operator error. The closest analog is the SO_REUSEPORT race-condition note: "there is a race condition when more than one process listens on the same socket... since no error is generated." That absence-of-detection is itself evidence this is genuinely a differentiator: nothing detects this for you, you have to build it. **[inferred beyond search — the specific pyRevit/Routes dual-bind scenario is project-specific, not found in any external precedent]** | MEDIUM | This is the concrete, most novel finding: none of Postgres/CDP/Jupyter/Selenium's identity mechanisms solve "which of two processes bound to the same address answered," because their transport layers make that structurally impossible (Postgres: OS enforces one listener per port; CDP/Jupyter: server assigns its own port per instance). Revit-mcp-server's hardcoded-port design is the actual root cause, and the differentiator is closing it at the port-configuration layer (Active requirement: "Порт настраиваемый") *combined with* an explicit health-check style refusal, not just identity-in-response as a workaround. |
| **Shared-secret gate on mutating routes, scoped to writes only** | None of the browser-automation or CAD-scripting comparables needed this because they run in a single trusted process boundary (a WebDriver session already implies local trust). This is a differentiator specific to this project's threat model (unauthenticated `/execute_code/`, binds observed on `0.0.0.0`) rather than a pattern borrowed from a comparable — closest real-world shape is a simple bearer-token / pre-shared-secret gate, the same primitive many internal admin APIs use. **[inferred — not a pattern pulled from the researched comparables, but directly justified by PROJECT.md's threat model]** | LOW | Already decided in PROJECT.md's Key Decisions table ("Обход политики закрывается общим секретом... секрет и политика вшиваются в payload при сборке"). Scoping the secret check to mutating routes only (not reads) keeps read-only tool-calling ergonomics unchanged for the AI client — this asymmetry (open reads, gated writes) is itself the differentiator over a blanket auth wall. |
| **Correlating one AI tool call to N underlying Revit operations via a shared correlation id** | OpenTelemetry's GenAI semantic conventions formalize exactly this: "a single `trace_id` links the entire chain, from the agent's initial decision through the MCP server's execution to the final response," with each tool call as a child span. This is an emerging (2026) convention, not yet universal, which is why it counts as a differentiator rather than table stakes — most existing MCP servers do not yet do this. | MEDIUM | Concretely: one `check_clashes` or bulk `delete_elements` MCP tool call may internally run dozens of Revit API operations across a single transaction. Stamping a `call_id` (could be the MCP request id, or a minted UUID) on every audit-log line written during that transaction lets a human reconstruct "what did this one AI decision actually do" — the OTel model's `trace_id` is the right shape to borrow even without adopting full OTel plumbing. |
| **Self-restoring payload only at Revit-extension load time, not at runtime** | This is a deliberate, narrower differentiator than Chrome's or CrowdStrike's live self-healing, and PROJECT.md already made this call explicitly ("Самовосстановление payload — только при старте... Замена файлов под работающим движком pyRevit — сценарий, который валит Revit"). Chrome's own precedent supports the *caution*, not the live-restore: Chromium's self-heal only applies to centrally-managed (force-installed) extensions; user-installed ones get a manual "Repair" button, i.e. even Chrome does not attempt silent live-restore for locally-managed artifacts under active use. | MEDIUM | This validates the project's existing decision rather than proposing a new one — cite it as confirmation, not a new requirement. The "restore at start, warn only if network share unreachable" shape below (Anti-Features) also follows from this. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| **Live/hot self-healing of the payload while Revit is running (Chrome-updater or CrowdStrike-style)** | Looks appealing by analogy to "modern agents just fix themselves" — Chrome and CrowdStrike both do this. | PROJECT.md already documents the concrete failure mode: replacing files under a running pyRevit engine has been observed to crash Revit. Chrome's own precedent is weaker than it looks on inspection: even Chrome only silently re-downloads *centrally managed* extensions; a locally-installed one gets a manual warn-and-repair flow, i.e. Chrome does not trust live-restore for an artifact under active local use either. CrowdStrike's model additionally assumes a network-reachable cloud source of truth at all times and a threat model (malicious tampering) this project explicitly excludes ("Защита от целенаправленного локального обхода... не входит"). | Verify-at-load (extension startup) + warn/refuse-to-register-domain on mismatch; restore only when Revit is *not* running (e.g., on next launch, or via a separate maintenance script), never hot-patch a live pyRevit process. |
| **Queue-position / ETA surfaced to the caller while waiting for the single-threaded Revit backend** | Feels like good UX — "tell the user how long they'll wait," the way a job queue dashboard might. | Not a single comparable system studied does this for a synchronous single-backend automation bridge. Selenium's session model has no queue-position concept at all — a second command simply blocks on the HTTP response of the first. Jupyter's kernel protocol has no queue-depth signal either — IOPub only publishes coarse `busy`/`idle` status; when busy, the kernel "does not respond to any requests" rather than returning a position. Building queue-position tracking here would be inventing a feature none of the analogous systems bothered with, for a mechanism (mutex around a single Revit process) that is binary, not a multi-item queue with meaningful position. | A bounded-wait synchronous block (matching Selenium/Jupyter precedent) that returns 503 "Revit busy, retry" past a timeout is sufficient and matches ecosystem norms — this directly answers the brief's question: **queue-position/wait is a nicety, not a table stake**, and for this project specifically (single backend, not a fleet), it is arguably over-engineering. |
| **Full distributed-tracing / OpenTelemetry SDK integration for audit logging** | OpenTelemetry GenAI conventions are the state-of-the-art academically, and it is tempting to adopt the whole stack (collectors, exporters, trace_id propagation across process boundaries). | This is a single-user desktop tool with a local structured log requirement (PROJECT.md: "Локальный структурный журнал аудита"), not a distributed multi-service system with a collector pipeline. OTel's own design payoff (correlating spans *across* independently-scaled services) does not apply when there is one CPython process and one IronPython process talking over one HTTP hop. | Borrow only the *shape* — a correlation id per tool call, before/after fields, structured JSON lines — without the OTel SDK, exporters, or collector infrastructure. A local JSON-lines audit file satisfies the actual requirement at a fraction of the complexity. |
| **Element-level BIM change attribution matching Revit's own worksharing history granularity** | Revit's Sync-with-Central history log (viewable via Collaborate > Show History) looks like a ready-made model to replicate at finer grain. | Research did not surface any evidence that Revit's built-in worksharing history is itself element-granular — it records sync-event-level user/timestamp/comment, not a per-element diff. Chasing parity with a granularity Revit itself does not provide is scope creep beyond what any comparable system actually offers, and the project's own audit log (mutation-route-level, with ElementIds touched) is already at least as granular as Revit's native history. **(LOW confidence claim — Revit's history feature was not directly inspected, only summarized via web search; flag for spot-check against a live Revit "Show History" panel if precision here later matters.)** | Route-level audit entries naming the affected ElementIds is sufficient and already exceeds Revit's own native sync-history granularity as documented. |
| **Tamper protection against the legitimate local operator (maintenance-token-gated uninstall, EDR-style)** | CrowdStrike's tamper protection is the most rigorous integrity model surveyed and might look like the "gold standard" to imitate. | PROJECT.md explicitly excludes this: "Защита от целенаправленного локального обхода — модель угрозы это случайная перезапись файлов инженером, не злоумышленник за консолью станции." CrowdStrike's maintenance-token model exists specifically to resist an authorized local user who wants to remove protection — that is a different, stronger threat model than this project claims. Building it here would be solving a problem the project has explicitly scoped out. | Detect-and-warn (or detect-and-restore-at-next-launch) against *accidental* drift (an engineer overwriting files without realizing, or half-copying an update) is sufficient; no token-gated tamper resistance against a deliberate local actor is in scope. |

---

## Feature Dependencies

```
Minimum identity tuple in response
    └──requires──> PID/session-token minted per Revit.exe launch (already exists implicitly as process; needs capture)
    └──enhances──> Explicit stale/wrong-backend detection (client compares tuple across calls)

List-open-documents call
    └──requires──> Minimum identity tuple (each listed document needs its own identity fields)
    └──enables──> Per-call explicit document addressing

Per-call explicit document addressing
    └──requires──> List-open-documents call (client must discover valid identifiers first)
    └──conflicts──> Implicit "active document" as the ONLY addressing mode (must coexist, not replace)

Refuse-to-serve on ambiguous backend (two listeners)
    └──requires──> Configurable port (Active requirement) + Minimum identity tuple (to prove ambiguity exists)

Shared-secret gate on mutating routes
    └──requires──> 127.0.0.1 bind enforcement (Active requirement) — a secret without bind enforcement over 0.0.0.0 is a weaker second line, not a substitute
    └──enhances──> Audit log (secret-rejected attempts are themselves auditable events)

Mutation serialization (mutex/queue on Revit calls)
    └──requires──> nothing else in this milestone — foundational, blocks concurrent DB.Transaction opens
    └──enables──> Reliable audit log (log entries can't interleave from concurrent transactions if writes are serialized)
    └──enables──> commit_and_report coverage on all mutating routes (a serialized single-writer path is what makes rollback reporting trustworthy)

Audit log with who/what/when/before/after + partial-failure status
    └──requires──> Mutation serialization (to guarantee one coherent audit line per operation, not interleaved partial writes)
    └──requires──> commit_and_report on all mutating routes (honest partial-failure status is exactly what commit_and_report already solved for rollback — extending it, not duplicating it)
    └──enhances──> Correlation id per AI tool call (differentiator — turns N audit lines into one reconstructable story)

Payload integrity manifest+hash check
    └──requires──> nothing else — independent of the identity/audit work, can ship in parallel
    └──enables──> Self-restore-at-load (Differentiator) — restore requires knowing what's wrong first
```

### Dependency Notes

- **Per-call document addressing requires list-open-documents:** every comparable system (AutoCAD, Photoshop, Jupyter) exposes the collection before or alongside addressing — a client cannot safely address a document it cannot first enumerate and verify still exists.
- **Mutation serialization is a prerequisite for a trustworthy audit log, not a parallel, independent feature:** if two transactions can interleave today (as PROJECT.md documents — up to 20 concurrent `DB.Transaction` opens), an audit log written from that state cannot be trusted to represent "what happened" as a coherent sequence. Order phases so serialization lands before or together with the audit log, never after.
- **`commit_and_report` completion conflicts with treating partial-failure audit as a separate concern:** PROJECT.md notes `commit_and_report` is not yet applied everywhere (`editing.py`'s delete path, `interop.py`'s `export_ifc`). The audit log's "honest partial failure" requirement and the outstanding `commit_and_report` rollout are the same underlying fix seen from two angles — do not plan them as unrelated work items.
- **Refuse-to-serve on ambiguous backend requires configurable port:** the two-listeners problem exists *because* the port is hardcoded (PROJECT.md: "Порт 48884 захардкожен в main.py:23 — единственное место в рантайме"). Detecting ambiguity without first making the port assignable only lets you detect the problem, not resolve it for the second Revit instance.

---

## MVP Definition

### Launch With (v1 — this milestone, "Доверенный мост")

- [ ] **Identity tuple in every response** (process/session id + document title/path + port) — foundational; every other feature in this milestone depends on being able to name "which backend, which document"
- [ ] **List + per-call address + switch active document** — Active requirement, direct precedent in AutoCAD/Photoshop/Jupyter
- [ ] **Mutation serialization (mutex or bounded queue around Revit calls)** — highest-severity gap found in PROJECT.md (20 concurrent transactions into a single-threaded API); every comparable single-threaded backend enforces this at the protocol layer
- [ ] **`commit_and_report` on all mutating routes, including honest partial-failure status** — extends an already-validated pattern (409 `rolled_back`) rather than introducing a new one; Terraform's `action_reason` precedent validates naming partial failure explicitly instead of collapsing it to boolean success
- [ ] **Structured local audit log (who/what/when/before/after + outcome) per mutation** — the universal 5-field minimum found across every audit-table/CDC reference
- [ ] **Shared secret on mutating routes + forced 127.0.0.1 bind** — closes the concretely observed `0.0.0.0` bind and unauthenticated `/execute_code/` gaps
- [ ] **Payload manifest+hash check at extension load, restore only at Revit startup (never live)** — npm/pip precedent for the check; Chrome's own restraint (no live-restore for locally-managed artifacts) validates the "load-time only" design already decided in PROJECT.md

### Add After Validation (v1.x)

- [ ] **Refuse-to-serve on ambiguous two-listener detection** — trigger: once port is configurable and identity tuple exists, this becomes cheap; do it once the prerequisites land, but it is not blocking for the rest of the milestone
- [ ] **Correlation id linking one AI tool call to its N underlying audit-log lines** — trigger: once the audit log itself is live and proves useful, add the OTel-style `trace_id`/`call_id` field to make multi-operation tool calls reconstructable as one story

### Future Consideration (v2+)

- [ ] **Permission policy + two-step confirmation with preview token** — explicitly deferred in PROJECT.md pending this milestone's identity/secret/audit foundation
- [ ] **Idempotency and safe retries** — explicitly deferred pending serialization landing first
- [ ] **Full OpenTelemetry SDK / distributed tracing integration** — defer indefinitely; the correlation-id *shape* is worth adopting now, the SDK/collector infrastructure is not justified for a single-process desktop tool

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Identity tuple in every response | HIGH | LOW | P1 |
| Mutation serialization | HIGH | MEDIUM | P1 |
| Audit log (5-field minimum + partial-failure status) | HIGH | MEDIUM | P1 |
| `commit_and_report` full coverage | HIGH | LOW | P1 |
| Shared secret + 127.0.0.1 bind enforcement | HIGH | LOW | P1 |
| List/address/switch multi-document | MEDIUM | MEDIUM | P1 |
| Payload manifest+hash check, load-time restore | MEDIUM | LOW | P1 |
| Refuse-to-serve on ambiguous two-listener | MEDIUM | LOW (once port configurable) | P2 |
| Correlation id across one tool call's operations | MEDIUM | LOW | P2 |
| Queue-position/ETA feedback while waiting | LOW | MEDIUM | P3 (anti-feature — skip) |
| Live/hot self-healing payload | LOW (net negative — crash risk) | HIGH | P3 (anti-feature — skip) |
| Full OTel SDK integration | LOW (for this project's scale) | HIGH | P3 (defer) |

---

## Comparable-System Feature Analysis

| Capability | Playwright/CDP | Selenium/Grid | Jupyter Kernel Gateway | AutoCAD/.NET | PostgreSQL | Terraform | Our Approach |
|---|---|---|---|---|---|---|---|
| Backend identity in every call | `targetId`+`sessionId` prefix on every command (explicit) | `sessionId` per WebDriver instance (explicit) | `kernel_id` in every REST path (explicit) | No response-level id; relies on in-process object reference (implicit, single-process assumption) | `pg_backend_pid()` queryable, not auto-included per query (available on demand) | N/A (not a live session model) | Explicit tuple (PID/session token + document id + port) in every response, not just on demand |
| Multi-document listing | N/A (targets, not documents) | N/A | REST list-kernels endpoint | `DocumentManager` collection | N/A | N/A | REST-analog list-open-documents MCP tool |
| Wrong-backend detection | Session-scoped commands make cross-target leakage structurally hard | Hard error only (`NoSuchSessionError`), no soft detection | Kernel busy = no response, not misrouting | Not addressed (single process assumption breaks down with multiple AutoCAD instances) | N/A (one backend per connection by OS design) | N/A | Client-side comparison of identity tuple across calls + server-side refuse-on-ambiguous-port |
| Partial-failure reporting | N/A | N/A | N/A | N/A | N/A | Named `action_reason` (e.g. tainted) — structured partial state | Extend `commit_and_report`/409 pattern with a `partial` status + per-element results |
| Concurrency handling | Per-context isolation allows true parallelism (contexts are independent) | Sequential within one session; parallel only via multiple sessions | Single-threaded; busy = unresponsive, no queue | Not documented for concurrent scripts | Each connection = its own backend process, so no shared-state contention at this layer | N/A (not a live session model) | Mutex/queue around single Revit API surface; bounded wait + 503, no queue-position UI |

---

## Sources

All findings below came from `WebSearch` (general web search, not a curated/verified provider) — confidence tagged per claim above; treat as MEDIUM where corroborated by an official-domain source in the result set, LOW where inferred or single-sourced.

- Playwright docs: `playwright.dev/docs/api/class-browsercontext`, `playwright.dev/docs/pages`
- Selenium docs and issue tracker: `selenium.dev/documentation/webdriver/drivers/`, `selenium.dev/documentation/grid/advanced_features/endpoints/`, `github.com/SeleniumHQ/selenium` issues (session/grid failure modes)
- Jupyter: `jupyter-kernel-gateway.readthedocs.io`, `jupyter-client.readthedocs.io/en/stable/messaging.html` (kernel busy/idle protocol)
- Language Server Protocol spec and GitHub issues: `microsoft.github.io/language-server-protocol/specifications/specification-3-14/`, `github.com/Microsoft/language-server-protocol` issues #281, #298, #2154
- Chrome DevTools Protocol: `chromedevtools.github.io/devtools-protocol/tot/Target/`, Browserbase engineering blog on CDP target tracking
- PostgreSQL docs: `postgresql.org/docs/current/protocol-flow.html`, `postgresql.org/docs/current/connect-estab.html`, pgPedia on `pg_backend_pid()`
- AutoCAD .NET API: Autodesk help docs on Create/Open/Save/Close Drawings, Autodesk Community threads on `ActiveDocument`/`MdiActiveDocument`
- Photoshop scripting: `developer.adobe.com/photoshop/uxp/2022/ps-reference/classes/documents`, ExtendScript vs UXP documentation
- Terraform: `developer.hashicorp.com/terraform/internals/json-format`, Spacelift/OneUptime blog posts on Terraform audit trail practice
- Database audit design: Red Gate "Database Design for Audit Logging," Wikipedia "Change data capture," DEV Community audit-fields reference
- Revit worksharing: Autodesk help on Workshared File Management, Revit Monsters worksharing guide (Show History feature)
- OpenTelemetry GenAI semantic conventions: `opentelemetry.io/blog/2026/genai-observability/`, Datadog and Greptime engineering blogs on GenAI OTel conventions
- npm/pip integrity: `docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/`, `pip.pypa.io/en/stable/topics/secure-installs/`, `pip.pypa.io/en/stable/cli/pip_hash/`
- Authenticode: Microsoft Learn archive blog posts on Authenticode/assembly loading behavior, Trail of Bits blog on Windows binary verification
- Chrome extension integrity: PixieBrix docs on extension corruption, Google Chrome Help support threads
- CrowdStrike Falcon: CrowdStrike engineering blog "Tech Analysis: Addressing Claims About Falcon Sensor Vulnerability," InventiveHQ knowledge base on tamper/uninstall protection
- Port-sharing/race conditions: grpc-io mailing list discussion, Wikipedia "Port (computer networking)"
- HTTP identity headers: http.dev X-Request-ID reference, Oracle Cloud Infrastructure load balancer header docs

**Not independently verified (no direct access to vendor source code or live testing of any comparable system) — all findings are secondary/web-sourced summaries.** Where a claim materially affects a P1 decision (mutation serialization, identity tuple minimum, partial-failure naming), it was corroborated across at least two independent official-domain sources; single-sourced or explicitly inferred claims are marked inline above and should not be treated as verified fact without a follow-up check.

---
*Feature research for: trust/identity/integrity foundation, revit-mcp-server milestone v0.1 "Доверенный мост"*
*Researched: 2026-09-21*
