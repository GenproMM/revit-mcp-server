# Roadmap: revit-mcp-server

## Overview

Milestone v0.1 «Доверенный мост» adds a trust layer onto a working 54-tool dual-runtime
bridge, without touching the 23 existing domain modules where it can be avoided. The path
starts with the fully CPython-testable serialization and configurable-port work, then brings
live identity, two-listener refusal and multi-document addressing forward as early as their
dependencies allow — so an engineer can work with several documents, including documents in
different Revit instances, in one assistant session — then builds the secret/integrity logic
and honest per-route outcomes, wires the secret gate and integrity check live, builds
a structured audit log on top of outcomes that are, by that point, already honest, and then
adds repository-owned mutation policies and human approval without changing Hermes Fork.
Two hard orderings shape this sequence: `commit_and_report`/honest-batch-reporting must
exist before the audit log is built on it (an audit log built earlier would faithfully
record the same false successes it exists to expose), and configurable-port plus
two-listener detection must land before or alongside per-instance/per-document addressing
(addressing "the instance on port X" is incoherent while two processes can share a port).

**Reorder 2026-09-30** (Phase 1 discussion, `phases/01-serialization-and-configurable-addressing/01-CONTEXT.md` D-01):
the former Phase 4 was split. Identity, ambiguity refusal and multi-document addressing
depend only on Phase 1 and moved up to Phase 2; live wiring of the secret gate and integrity
check became its own Phase 5. Accepted cost: two live-Revit restart-cycle phases (2 and 5)
instead of one, and the `startup.py` chokepoint is touched twice.

## Phases

**Releases:** Phases 3–7 each carry a **Release checkpoint**. When a phase closes, offer the release before routing to the next phase — protocol, checklist and ledger in `.planning/RELEASES.md`.

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Serialization and configurable addressing** - Every call from this server except `/status/` queues instead of racing, `/status/` stays responsive throughout, and the Revit port this server talks to is a deployment setting instead of a hardcoded constant — one server process per Revit instance; choosing a Revit per call is Phase 2 (completed 2026-10-14)
- [x] **Phase 2: Live identity, ambiguity refusal, and multi-document addressing** - Every response names the document and process that handled it, two listeners on one port produce an explicit refusal instead of a coin-flip, and an engineer can list, address, and switch between documents open in one Revit session (completed 2026-10-23)
- [x] **Phase 3: Secret gate and payload integrity (unit-verified)** - The shared-secret compare and the file-manifest integrity check are built and unit-tested on both runtimes, plus the build pipeline that generates the secret and the manifest, ready to wire in (completed 2026-10-23)
- [ ] **Phase 4: Honest outcomes on every mutating route** - Every mutating route, including the two known stragglers, reports what actually happened in Revit rather than an assumed success
- [ ] **Phase 5: Live secret gate and integrity enforcement** - The Phase 3 secret gate and integrity check are wired into the live chokepoint and binding
- [ ] **Phase 6: Structured audit log of true outcomes** - Every mutation lands in a local, rotation-capped JSONL log carrying the same honest outcome the client saw, without leaking the secret
- [ ] **Phase 7: Repository-owned mutation safety and human approval** - Редактируемые правила, объяснение риска и одноразовое подтверждение опасных операций реализованы в этом репозитории; Hermes Fork не изменяется, Jev необязателен и не ослабляет правила

## Phase Details

### Phase 1: Serialization and configurable addressing

**Goal**: Calls issued through this MCP server no longer reach pyRevit's shared request handler in parallel — every call except `/status/` waits its turn (d27-b) — and the server's target port is a deployment setting instead of a hardcoded constant. One MCP server process targets one Revit instance, users share one `revit` entry, and choosing a Revit instance per call is Phase 2. Every route still operates on the targeted instance's active document — document addressing is Phase 2.
**Depends on**: Nothing (first phase)
**Requirements**: SER-01, SER-02, SER-03, SER-04, SER-05, IDENT-05
**Context**: `phases/01-serialization-and-configurable-addressing/01-CONTEXT.md`
**Success Criteria** (what must be TRUE):

  1. Two mutating tool calls issued back-to-back never open overlapping Revit transactions from this server — verified with a concurrent-request test that holds one call and confirms the second waits.
  2. `/status/` returns promptly even while another call holds the serialization lock, and every other call, reads included, waits its turn (d27-b, decided after the 01-04 bench measured cross-wired reads in pyRevit's shared handler) — verified with a concurrent test, not inferred from code shape.
  3. A mutating call that times out, throws, or is cancelled releases the lock immediately — verified by forcing an exception inside the locked region and re-acquiring right after.
  4. Waiting in the queue does not shrink a call's own request timeout budget below what an unqueued call would get; a wait that exceeds its bound returns an explicit "not sent to Revit" error.
  5. Setting `REVIT_PORT` changes which port this server talks to, exercised live with two Revit instances started one after the other: each of 48884 and 48885 has exactly one listener with a different PID, and two stdio server processes (the two-instance harness `tests/test_two_instance_targets.py`) each get their own `host:port` and `document_title` from `get_revit_status`; per decision a5-a the harness stands in for the original one-session two-entry check, because users share one `revit` entry and cannot copy it, so a two-entry session is not a user-facing setup. If a staggered start puts both instances on 48884, the phase is not accepted and addressing is revisited before Phase 2.
  6. The documented scope of serialization is explicit and honest: it covers calls issued through this one server process only; it is not represented anywhere as a guarantee against another MCP server process (a second assistant session), curl, or `/execute_code/` called directly; and the docs say overlapping sessions against one Revit can still cross-wire until backlog item 999.1 (d27-c) lands.

**Plans:** 7/7 plans complete

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — `bridge.py` transport with one mutation lock on every POST, strict `REVIT_PORT` (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — bounded queue wait with full send budget, honest not-sent / outcome-unknown errors, read-only allowlist (wave 2)
- [x] 01-03-PLAN.md — `get_revit_status` names its target, two-entry harness, payload ships `bridge.py` (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-04-PLAN.md — live two-Revit bench, D-23 overlap probe, conditional D-18 / D-27 decision gate (wave 3, checkpoints)

**Superseded**

- ~~01-05-PLAN.md — honest serialization scope and `REVIT_PORT` / two-entry docs~~ — superseded 2026-10-07 by 01-06..01-08 (d27-b / a5-a), not executed

**Gap closure after the 01-04 bench** *(run with `/gsd-execute-phase 1 --gaps-only`)*

- [x] 01-08-PLAN.md — planning record: SER-02 narrowed, ROADMAP SC2/SC5/SC6, Phase 2 per-target lock note, d27-c in Backlog, debug lead (gap, wave 1)
- [x] 01-06-PLAN.md — d27-b in `bridge.py`: every call except GET `/status/` takes the lock (`/model_info/`, GET reads, `revit_image` included); D-08 allowlist removed (gap, wave 3)
- [x] 01-07-PLAN.md — honest-scope docs pinned by tests: process-local lock, only `/status/` unlocked, cross-wiring until d27-c, `REVIT_PORT` as a deployment setting (gap, wave 4, after 01-06 and 01-08)

### Phase 2: Live identity, ambiguity refusal, and multi-document addressing

**Goal**: Every response can be attributed to a specific document in a specific Revit process; two processes listening on the same port produce a loud, named refusal instead of an unpredictable answer; an engineer can enumerate, address, and switch between documents open in one Revit session. Combined with per-call selection of the Revit target inside the one shared `revit` server entry (carried here from Phase 1, see the note below), one assistant session can read and compare documents across instances and within one instance.
**Depends on**: Phase 1 (port configurability)
**Context**: `phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-CONTEXT.md` (interactive revision 2026-10-14; supersedes incompatible pre-reorder `--auto` decisions)
**Requirements**: IDENT-01, IDENT-02, IDENT-03, IDENT-04, AMBIG-01, AMBIG-02, AMBIG-03, AMBIG-04, MDOC-01, MDOC-02, MDOC-03, MDOC-04, MDOC-05
**Carried from Phase 1 (01-04, decisions a5-a and d27-b):** per-call selection of the Revit target inside the one shared `revit` server entry belongs here (recorded against IDENT-01); once one server process can address several Revit instances the serialization lock must be keyed by target, one lock per Revit target and never one global lock; `/status/` stays the only unlocked route per target unless a live overlap measurement says otherwise.
**Success Criteria** (what must be TRUE):

  1. `/status/` returns PID, Revit version, port, and a session token issued once at process start — confirmed live against a running Revit instance.
  2. A mutating route's response names the document it changed (title and path), re-derived at request time rather than cached — confirmed live across an `OpenAndActivateDocument` call and a manual UI document switch, per the existing defensive re-fetch pattern this codebase already established for the null-document bug.
  3. Two Revit instances both showing the untitled title `Project1` are distinguishable by response fields alone — confirmed live with the two-Revit-instance test bench.
  4. Starting a second Revit process bound to the same port as an already-running one produces an explicit, named refusal (not a request silently answered by whichever process the OS happened to pick) that identifies both conflicting PIDs — confirmed live by intentionally creating the two-listener condition.
  5. With identity now visible in every response, the still-open `param-write-rolls-back` "wrong process answered" hypothesis is re-run live and its outcome (confirmed or ruled out) is recorded.
  6. An engineer can list every open document in the session with its identity, address a call at one explicitly, and switch which document is active via its own tool call — confirmed live with more than one model open in one session.
  7. Comparing documents open in one session is possible from one assistant session; whether reading an addressed document may switch the active document in the Revit UI is decided in the Phase 2 discussion (tension with the `--auto` "verification, not retargeting" decision in `02-CONTEXT.md` D-14).
  8. A mutating call that omits the document argument follows a documented, explicit default (not a silent guess) stated in the tool's own docstring.
  9. Addressing a document that was closed after being listed produces a clear, named error rather than the call silently operating on a different, currently-open document.

**Plans**: TBD

- [x] 02-01-PLAN.md
- [x] 02-02-PLAN.md
- [x] 02-03-PLAN.md
- [x] 02-04-PLAN.md
- [x] 02-05-PLAN.md
- [x] 02-06-PLAN.md
- [x] 02-07-PLAN.md
- [x] 02-08-PLAN.md
- [x] 02-09-PLAN.md
- [x] 02-10-PLAN.md
- [x] 02-11-PLAN.md
- [x] 02-12-PLAN.md
- [x] 02-13-PLAN.md
- [x] 02-14-PLAN.md
- [x] 02-15-PLAN.md
- [x] 02-16-PLAN.md
- [x] 02-17-PLAN.md
- [x] 02-18-PLAN.md
- [x] 02-19-PLAN.md
- [x] 02-20-PLAN.md

### Phase 3: Secret gate and payload integrity (unit-verified)

**Goal**: The logic that will reject an unauthenticated mutation and detect a tampered `revit_mcp/` payload exists, is correct on both runtimes per the unit-test suite, and is generated consistently by the build pipeline — but is not yet wired into a live route. This phase's output is inert by design (ARCHITECTURE.md's build-before-wiring ordering): live enforcement is Phase 5's job.
**Release checkpoint**: R1 — on phase close, offer a release bundling Phases 1–3 (Phases 1–2 were never shipped); the Phase 3 code ships dormant. See `.planning/RELEASES.md`.
**Depends on**: Nothing (parallel to Phases 1–2, different runtimes/files)
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04, SEC-05, SEC-06, SEC-07, SEC-08, INTG-01, INTG-02, INTG-03, INTG-04, INTG-05, INTG-06, INTG-07, INTG-08
**Success Criteria** (what must be TRUE):

  1. A unit test proves the secret-compare helper rejects a wrong or missing secret and accepts a correct one, on both the CPython side and the IronPython-targeted logic, with the secret read from the `text/plain` body via `parse_request_data()` — never a new header-parsing path.
  2. A unit test proves the secret-compare helper runs in constant time using whatever primitive is confirmed available on pyRevit's hosted CLR (`CryptographicOperations.FixedTimeEquals` if present; a hand-rolled fixed-length compare with a documented fallback reason if not) — this requires the live CLR-availability check called out in Research Flags before the implementation is finalized, not assumed.
  3. A unit test proves an auth failure is designed to surface as a non-200 status distinct from 409 (`rolled_back`'s reserved meaning), matching the existing `_revit_call` string-passthrough contract, with a paired regression test in the style of the existing `rolled_back` test.
  4. A unit test proves the secret never appears in an exception message or log line produced by the compare helper itself.
  5. A unit test proves the manifest-generation logic builds its file list from `git ls-files` (or equivalent tracked-file source), not a filesystem walk — so `__pycache__`, `.pyc`, and line-ending normalization cannot produce a false mismatch.
  6. A unit test proves the integrity check's three-state model (`verified_match` / `verified_mismatch` / `unverifiable`) never collapses "reference unreachable" into "mismatched," and that the check function itself never writes a file under any input.
  7. The build pipeline (`deploy/config.cmd` or equivalent) generates one shared secret and one file-hash manifest per build, consumed identically by both the payload and the extension side, immediately after the `revit_mcp` copy step so the manifest cannot describe a different tree than what shipped.
  8. On the dev machine's junction layout, running the integrity check against the live working tree reports `verified_match` (or an explicit, non-blocking `unverifiable`) — never a spurious mismatch that would (once wired in Phase 5) block mutations for every developer.

**Plans:** 9/9 plans complete

Plans:

- [x] 03-09-PLAN.md

**Wave 1**

- [x] 03-01-PLAN.md — Tracer: secret envelope end to end (with_envelope -> unchanged _send -> split_envelope/check_secret -> visible 401) plus compare, leak and method hardening in revit_mcp/trust.py
- [x] 03-02-PLAN.md — deploy/secret_tool.py (create once, stage, verify), scripts/dev_secret.py, .gitignore entries

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-03-PLAN.md — bridge.load_secret with parity to trust.py, inert send-path pin, the 401 format_response pair
- [x] 03-04-PLAN.md — Integrity slice end to end: make_manifest.py (git ls-files), integrity.py reader, evaluate_integrity, visible 423

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-05-PLAN.md — Hardening: check never writes, unreachable is never mismatch, dev junction quiet, generator build guards

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 03-06-PLAN.md — classify_listeners (SEC-07) and the IronPython 3 engine simulation / 3.5+ construct guard
- [x] 03-07-PLAN.md — Build wiring: config.cmd MCP_SECRET_FILE, publish-extension.cmd and build-payload.cmd staging and manifest, gate.py pair check, CLAUDE.md

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 03-08-PLAN.md — Live D-04 check (human-run): hashlib and the new modules in pyRevit's engine, recorded in code and validation

### Phase 4: Honest outcomes on every mutating route

**Goal**: Every mutating route reports what Revit actually did — including partial batch failure and rollback — never an assumed or collapsed success. This is a hard prerequisite for Phase 6's audit log, not parallel work: an audit log built against routes that still collapse partial failure into `status: success` would faithfully record the same lie it exists to expose.
**Release checkpoint**: R2 — on phase close, offer a release; mutation response shape changes. See `.planning/RELEASES.md`.
**Depends on**: Nothing (independent of Phases 1–3 and 5; must complete before Phase 6)
**Requirements**: TRUTH-01, TRUTH-02, TRUTH-03, TRUTH-04
**Success Criteria** (what must be TRUE):

  1. Every mutating route's response reflects the real `TransactionStatus` Revit returned, not a value assumed at the call site — exercised against at least one route per module family (single-element, batch, export).
  2. `delete_elements` and `export_ifc` are migrated onto `commit_and_report`, closing the two known remaining gaps named in PROJECT.md's Context.
  3. A batch operation run against a mix of valid and invalid element ids returns the succeeded and skipped/failed ids alongside each other, not only a count.
  4. A batch operation's partial failure produces a status distinguishable both from full success and from full failure — exercised live against at least one batch route with an intentionally-invalid id mixed in.

**Plans**: TBD

### Phase 5: Live secret gate and integrity enforcement

**Goal**: The secret gate and integrity check built in Phase 3 are wired into the live request chokepoint in `startup.py` (the same one Phase 2 uses for identity) and become binding. This is a live-Revit restart-per-iteration phase.
**Release checkpoint**: R3 — on phase close, offer a PILOT-FIRST release (one-way door: unauthenticated mutations start failing). Plan the mixed-version rollout order (Revit half at next Revit restart, CPython half at next logon) and the Revit-half rollback during planning of this phase, not at release time. See `.planning/RELEASES.md`.
**Depends on**: Phase 2 (live chokepoint), Phase 3 (secret/integrity logic to wire in)
**Requirements**: live enforcement of SEC-01..08 and INTG-01..08 (traced to Phase 3, where the logic is built; they become user-observably true here)
**Success Criteria** (what must be TRUE):

  1. An unauthenticated mutation is rejected before any transaction opens — confirmed live.
  2. A deliberately corrupted `revit_mcp/` file is detected and reported by `/status/` while reads keep working — confirmed live.
  3. Reads and `/status/` stay available without the secret, so a secret mismatch never blocks diagnostics — confirmed live.

**Plans**: TBD

### Phase 6: Structured audit log of true outcomes

**Goal**: Every mutation is recorded in a local, structured, honest log — reflecting Phase 4's real per-element outcomes, not the request's stated intent — without becoming a second place the shared secret leaks. Deliberately last: both research documents agree this is the single highest-value ordering decision in the milestone.
**Release checkpoint**: R4 — on phase close, offer a release. See `.planning/RELEASES.md`.
**Depends on**: Phase 4 (honest outcomes to log), Phase 2 (identity fields to include in each entry), Phase 5 (live secret, so the no-leak check is meaningful)
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

### Phase 7: Repository-owned mutation safety and human approval

**Goal:** Инженер получает понятное объяснение риска и подтверждает конкретную опасную операцию до её выполнения. Вся логика безопасности принадлежит revit-mcp-server (CPython + Revit extension), правила корректируются без изменения кода, Hermes Fork не требует доработок. Jev — необязательный семантический классификатор, не источник разрешения и не замена детерминированным правилам.
**Release checkpoint:** R5 = v0.1 — при закрытии фазы предложить PILOT-FIRST релиз и закрытие milestone (`/gsd-complete-milestone`). См. `.planning/RELEASES.md`.
**Depends on:** Phase 6; использует identity/addressing Phase 2, honest outcomes Phase 4 и live authentication/integrity Phase 5, не создавая параллельных механизмов
**Requirements**: TBD — формализовать при планировании по 07-CONTEXT.md; новые идентификаторы требований пока не назначены
**Context**: `phases/07-repository-owned-mutation-safety-and-human-approval/07-CONTEXT.md`
**Research inputs**: `phases/07-repository-owned-mutation-safety-and-human-approval/07-RESEARCH-NOTES.md` (исследование сессии, не завершённая проверка реализации)
**Success Criteria** (what must be TRUE):

  1. Правила и обязательное enforcement находятся только в этом репозитории; read-only интеграционная проверка использует неизменённый Hermes. Несовместимый или отсутствующий канал подтверждения блокирует защищённую операцию, а не принимает сообщение агента или `approved=true`.
  2. Валидируемая локальная политика классифицирует все доступные инструменты/маршруты, включая альтернативные пути мутации; неизвестный путь не получает неявного разрешения. Подтверждение охватывает перезапись параметров, удаление, трансформации и фактические пути создания общих параметров; ограничения instance/type и каскадного охвата явно видны человеку.
  3. Одноразовое разрешение связано с нормализованными аргументами, выбранными процессом/документом, версией политики и сроком; оно проверяется до эффекта и атомарно потребляется. Повтор, изменение аргументов/документа, restart, отказ и timeout не разрешают мутацию. Прямой вызов защищённого HTTP-маршрута без надлежащего разрешения отклоняется до эффекта, а не только на MCP-стороне.
  4. Ошибочная/отсутствующая политика и недоступность Jev не ослабляют обязательные правила. Hot reload атомарен; первая невалидная конфигурация блокирует защищённые операции, невалидное обновление сохраняет последнюю валидную версию с диагностикой. Ожидающее разрешение не переживает применённую смену политики.
  5. Повторная доставка не выполняет одну разрешённую мутацию дважды; журнал и ответ различают отказ, expiry, committed, rolled_back, partial и unknown, не выдавая подтверждение за успешное выполнение. После неизвестного результата автоматического повтора нет; гарантия при новом запросе клиента описана отдельно и не завышена.
  6. Оба execute-code пути сохраняют явный статус доверенного произвольного кода по D-15, без скрытого отключения и без обещания sandbox/полной confinement. Перед заявлением о защите всех операций зафиксированы границы обхода через arbitrary code, ОС-доступ и cross-process handler overlap (backlog 999.1).
  7. Офлайн негативные/конкурентные тесты и отдельно разрешённый live bench подтверждают контракт. Изменения Revit extension проверяются после полного restart, не Reload; ни принятие фазы, ни создание этих материалов не разрешает live-операции или внешнюю передачу BIM-данных.

**Plans:** 0 plans — фаза добавлена, декомпозиция и проверка совместимости ещё не выполнены

Plans:

- [ ] TBD (run /gsd-plan-phase 7 to break down)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7
(Phase 2 requires Phase 1. Phases 3 and 4 have no dependency on 1–2 and may be interleaved. Phase 5 requires Phases 2 and 3. Phase 6 requires Phases 2, 4 and 5. Phase 7 builds on Phases 2, 4, 5 and 6; backlog 999.1 remains a separate acceptance concern for cross-process guarantees.)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Serialization and configurable addressing | 7/7 | Complete    | 2026-10-14 |
| 2. Live identity, ambiguity refusal, and multi-document addressing | 20/20 | Complete    | 2026-10-23 |
| 3. Secret gate and payload integrity (unit-verified) | 9/9 | Complete    | 2026-10-23 |
| 4. Honest outcomes on every mutating route | 0/TBD | Not started | - |
| 5. Live secret gate and integrity enforcement | 0/TBD | Not started | - |
| 6. Structured audit log of true outcomes | 0/TBD | Not started | - |
| 7. Repository-owned mutation safety and human approval | 0/TBD | Not planned | - |

## Backlog

### Phase 999.1: Revit-side fix for cross-process overlap in pyRevit's shared handler (d27-c) (BACKLOG)

**Goal:** Captured for future planning. Two MCP server processes (two assistant sessions) sending overlapping requests to one Revit must not cross-wire inside pyRevit's shared request handler; `bridge.py`'s lock is per process, so only a Revit-side fix closes this.
**Evidence:** 01-04 bench, 2026-10-07, pyRevit 6.5.3, two Revit 2024.3.30, `scripts/probe_handler_overlap.py` run twice with identical verdicts. Phase M `cross-wired-mutation`: the overlapped mutation answered 200 with the other caller's output and its own body never ran. Phase R `cross-wired-read`: `/list_levels/` returned the mutation's output. `/status/` unaffected (0.01-0.02 s).
**Source:** `phases/01-serialization-and-configurable-addressing/01-04-SUMMARY.md` "Bench record", Step 7.
**Why it matters:** A mutation can be lost while reported as success (see `.planning/debug/param-write-rolls-back.md`, second candidate).
**When promoted:** A live-Revit restart-cycle phase (changes under `revit_mcp/` or `startup.py` need a full Revit restart); not yet benched on pyRevit 6.5.5.
**Requirements:** TBD
**Plans:** 0 plans

Plans:

- [ ] TBD (promote with /gsd-review-backlog when ready)
