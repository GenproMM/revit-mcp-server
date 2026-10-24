# Phase 5: Live secret gate and integrity enforcement - Research

**Researched:** 2026-10-24
**Domain:** Per-route request gating inside pyRevit Routes handlers (IronPython 3.4-level dialect), extension-load integrity check, `/status/` diagnostics, atomic publish/rollback of the extension folder, restart-per-iteration live acceptance. No new packages.
**Confidence:** HIGH for in-repo facts (files read this session); MEDIUM for pyRevit-internals (read from the dev machine's pyRevit-Master clone, fleet build may differ); LOW for SMB rename-while-loaded behaviour (probe designed, not run on the fleet share).

> Numbering note: ROADMAP text says "wired into the chokepoint in `startup.py`". CONTEXT D-01 supersedes it: the gate is an explicit call at the top of every non-GET handler; `startup.py` only initializes state. Everything below follows CONTEXT.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Решения фазы 3 (`03-CONTEXT.md` D-01…D-17) остаются в силе и здесь не повторяются: конверт
`_mcp` в теле, сравнение SHA-256 + XOR, 401 по секрету / 423 по целостности, стабильный секрет
`_bridge_secret`, fail-closed при отсутствии файла на стороне Revit, `unverifiable` не блокирует,
бинд `exposed` → `degraded` без блокировки. Ниже ссылки на них даны как «03 D-NN».

### Что закрывает секрет
- **D-01:** Шлюз — **явная проверка в каждом маршруте**, без общей обёртки в `startup.py`.
  Каждый не-GET маршрут первым действием обработчика зовёт одну общую проверку (секрет +
  целостность), так же как сейчас зовёт guard документа `mutation_document_or_response`.
  **Закрыт по умолчанию** обеспечивается тестом-сторожем: AST-тест падает, если не-GET маршрут не
  зовёт проверку и не стоит в явном списке открытых чтений; то же правило действует в
  `scripts/conventions.py` / `scripts/intake_package.py`, поэтому забытый маршрут не пройдёт ни
  тесты, ни приём пакета. Добавление маршрута в список открытых — правка списка + тест, по образцу
  `UNLOCKED_GET` в `bridge.py`.
  *Исправление 2026-10-24:* в обсуждении сначала была записана общая обёртка в `startup.py`.
  Это противоречило инварианту фазы 2 G1 explicit-route-only (тест
  `tests/unit/test_phase2_inventory.py::test_startup_installs_no_common_handler_wrapper`: обёртка
  рискует сломать проверку сигнатур pyRevit, инъекцию `doc`/`request`/`uidoc` и ExternalEvent) и
  решению фазы 3 C2. Пользователь выбрал проверку в маршруте + тест-сторож. Фраза ROADMAP о
  «chokepoint в `startup.py`» устарела. — **Reversibility:** costly — список открытых маршрутов
  становится контрактом, на который опираются тесты, документация и поведение парка.
- **D-02:** Уточнение 03 D-03 («шлюз на все POST»): семь POST-маршрутов, которые только читают,
  **открыты без секрета** — `/document_summary/`, `/document_levels/`, `/model_worksets/`,
  `/material_quantities/`, `/clash_check/`, `/ai_filter/`, `/list_category_parameters/`.
  Проверено обследованием: ни один не открывает транзакцию и не меняет выделение. Это выполняет
  SEC-05 и критерий успеха 3 дословно. Все GET открыты (как и было).
- **D-03:** Пограничные POST-маршруты — **под секретом**: `/activate_document/`,
  `/set_active_view/` (меняют, куда попадёт следующая мутация), `/open_model/` (открывает,
  создаёт локальную копию), `/export_document/`, `/export_ifc/`, `/save_document/`,
  `/link_file/` (пишут файлы на диск станции), `/execute_code/`. Открыты только чистые чтения.
- **D-04:** Шлюз целостности (423 при `verified_mismatch`) блокирует **тот же набор** маршрутов,
  что и шлюз секрета: один список открытых чтений на оба шлюза. При порче файлов чтения и
  `/status/` работают, всё остальное, включая `/execute_code/`, получает 423 до переустановки
  файлов и перезапуска Revit.

### Порядок выкладки и смешанные версии (R3)
- **D-05:** Порядок: **сначала payload, потом ext** — один коммит, две публикации с паузой.
  График выкладки на основной share:
  1. payload публикуется до воскресенья (например, в пятницу);
  2. в воскресенье у всех плановая перезагрузка Windows → payload обновляется при входе в понедельник;
  3. на машинах, где перезагрузка не работает, пользователь до публикации ext один раз нажимает
     ярлык «Update RevitMCP» и перезапускает сессию ассистента (оповещение адресное);
  4. ext публикуется в понедельник после обеда или во вторник; включается у каждого при
     следующем перезапуске Revit.
  Это закрывает требование RELEASES.md §R3 о порядке выкладки. — **Reversibility:** one-way —
  после публикации ext мутации без секрета у всего парка начинают отклоняться; именно это
  событие и есть «односторонняя дверь» R3.
- **D-06:** **Предусловие публикации payload первым:** доказано, что версия ext, которая на тот
  момент стоит на основной share, безвредно игнорирует лишний ключ `_mcp` в теле каждого
  POST-маршрута (не падает, не меняет поведение, не возвращает тело запроса с секретом в тексте
  ошибки). Если хоть один маршрут этого не выдерживает, порядок D-05 не применим, пока это не
  решено.
- **D-07:** Состояние «Revit требует секрет, мост его не шлёт» → **строгий 401** без льгот и
  временных окон. Текст отказа доходит до модели и говорит инженеру, что делать: запустить
  «Update RevitMCP» (или перезайти в Windows) и перезапустить сессию ассистента. SEC-01 без
  исключений.
- **D-08:** Диагностика секрета без попытки мутации: Revit-сторона в `/status/` сообщает
  «секрет настроен да/нет» и короткий отпечаток (8 hex-символов SHA-256 от секрета);
  CPython-сторона — «секрет загружен да/нет» и такой же отпечаток. `get_revit_status` сравнивает
  отпечатки и прямо говорит «секреты половин различаются», если так. Цель — случай пилотного
  секрета против флотского (RELEASES.md: у пилотного share свой `MCP_SECRET_FILE`). Сам секрет
  никуда не выводится (SEC-06); отпечаток от 32-байтового случайного значения его не раскрывает.

### Откат Revit-половины
- **D-09:** Механизм отката — **прошлая версия ext рядом на share**: публикация сохраняет
  предыдущий `ext\revit-mcp-server.extension` в `ext-previous\`. Откат — одна команда
  администратора (вернуть `ext-previous\` на место `ext\`) плюс перезапуск Revit у
  пользователей; без git и пересборки. Аналог `versions\` + junction у payload. Откатывать
  payload при этом не нужно: новый мост, шлющий `_mcp`, безвреден для старого ext (D-06).
  Аварийный выключатель-файл отвергнут: это была бы настройка, отключающая защиту, вопреки
  принципу «вшивается при сборке». — **Reversibility:** reversible — меняется только сборочный
  скрипт.
- **D-10:** Публикация ext становится **атомарной**: сборка в `ext-staging\`, там же
  размещение секрета, манифест и все гейты; только после этого `ext\` → `ext-previous\`,
  `ext-staging\` → `ext\`. Это закрывает WR-02 из `03-REVIEW.md`: сейчас `robocopy /MIR` чистит
  живую папку до шагов секрета и манифеста, и Revit, запущенный в этом окне, загрузился бы без
  `_bridge_secret` и отклонял бы все мутации до следующего перезапуска (fail-closed, 03 D-08).
  Исследователю проверить: переименование папки на SMB-share проходит, пока на станциях открыт
  Revit с этим расширением (pyRevit не держит открытыми файлы); если нет — нужен другой способ
  подмены, и это возвращается пользователю.

### Живая приёмка
- **D-11:** Критерий 2 (порча файла видна) доказывается на dev-машине: временный
  `_manifest.json` пишется `deploy/make_manifest.py` в корень junction-репозитория (имя в
  `.gitignore`) → перезапуск → `verified_match` → порча → перезапуск → проверка → удалить
  манифест, `git checkout` изменённого файла, удалить лишний файл → перезапуск → снова
  `unverifiable` и мутации работают. Конвейер публикации (staging, подмена, секрет и манифест в
  `ext\`) проверяется на пилоте R3, не в этой фазе.
- **D-12:** Инсценируемая порча — **два вида за один перезапуск**: изменённый файл (комментарий
  в конце одного доменного модуля → `modified`) и лишний файл `revit_mcp/_zz_probe.py`
  (подчёркивание — не станет доменом → `unexpected`). `/status/` должен назвать оба. Удаление
  файла (`missing`) не инсценируется.
- **D-13:** Живую проверку **проводит Claude** через MCP-инструменты `revit` и прямые
  HTTP-запросы (`Content-Type: text/plain`), Revit перезапускает пользователь. Негативные проверки
  (без конверта, неверный секрет) идут прямыми HTTP-запросами, потому что MCP-инструменты сами
  кладут секрет. Действуют правила живых проверок проекта: перед каждой серией ровно один
  слушатель на порту (`Get-NetTCPConnection -LocalPort 48884 -State Listen` — одна строка),
  шаги записи не повторяются, после правок `bridge.py` перезапускается и процесс MCP-сервера
  этой сессии.
- **D-14:** Модель — **одноразовая тестовая** (новый несохранённый проект или копия
  демо-модели), рабочие модели не трогаются. Проба: `create_level` с уникальным именем;
  `list_levels` показывает, что после 401/423 уровня нет («отклонено до транзакции»), а с верным
  секретом — есть (позитивный контроль).

### Claude's Discretion
- Как общая проверка отдаёт обработчику тело без `_mcp`: маршруты сейчас сами разбирают
  `request.data` через `parse_request_data()`, поэтому секрет не должен остаться в том, что они
  читают дальше (03 D-02, SEC-06). Способ — решение исследователя и планировщика.
- Как общая проверка сочетается с guard документа (один вызов или два подряд) и где её вызывают
  маршруты, не проходящие guard (`/execute_code/`, экспорт, `/open_model/`).
- Шлёт ли мост конверт на все POST, включая открытые чтения (проще и однородно), или только на
  закрытые. По умолчанию — на все POST; Revit-сторона снимает `_mcp` и с открытых маршрутов.
- Где живёт список открытых чтений (`trust.py` рядом с `UNGATED_METHODS` — естественное место)
  и как тест сверяет его с `tests/unit/tool_manifest.txt` и фактическими маршрутами.
- Тексты отказов и подсказок, имя команды отката, имена полей диагностики в `/status/`.
- Проверка целостности выполняется при загрузке расширения (до импорта доменов, как намечено в
  фазе 3); изменение файла после загрузки видно только после перезапуска, и это честно
  записывается в документации.

### Deferred Ideas (OUT OF SCOPE)
- Запуск `update.cmd` по ежедневному расписанию, а не только при входе в систему, — навсегда
  закрывает проблему машин без перезагрузки, но меняет установщик и триггер на всех станциях.
  Отдельная работа.
- Аварийный выключатель шлюзов файлом на share — отвергнут в пользу `ext-previous\` (D-09);
  вернуться, только если откат через перезапуск Revit окажется слишком медленным.
</user_constraints>

<phase_requirements>
## Phase Requirements

Requirement text is from `.planning/REQUIREMENTS.md` lines 39-57 (read this session). All 16 are "built and unit-verified" in Phase 3; Phase 5 makes them user-observably true.

| ID | Description | Research Support |
|----|-------------|------------------|
| SEC-01 | Mutating routes require the shared secret; refused before any transaction | Per-route first-statement gate (Pattern 1), AST sentinel (Pattern 3), fake-world "zero transactions on refusal" tests, live stage L1 |
| SEC-02 | Secret rides in the `text/plain` body via `parse_request_data()` | `bridge._send` POST branch gets the envelope; `split_envelope` already uses only `parse_request_data` |
| SEC-03 | Auth failure is non-200 and visible to the model | 401 via `trust.auth_failure`; `format_response` pair already pinned; wrong-secret probe through the production bridge in live gate |
| SEC-04 | Constant-time compare on both halves | Already built (`_same_digest`); Phase 5 only calls it. Regression only |
| SEC-05 | Reads and `/status/` open without the secret | 15 GET + 7 POST-read routes open (exact list below); sentinel test also forbids the gate on GET routes |
| SEC-06 | Secret never in log, audit, error text | Gate strips `_mcp` from `request.data` before any handler code; leak tests on gate output, caplog, handler reply echo scan |
| SEC-07 | Non-loopback bind detected and reported | `classify_listeners` fed by .NET `GetActiveTcpListeners()` at `/status/` time (Pattern 5); never blocks |
| SEC-08 | Secret injected at build, consistent pair | Existing pipeline; D-08 fingerprints expose a pilot-vs-fleet mismatch live |
| INTG-01 | Manifest built at publish | Existing `make_manifest.py`; staged publish keeps it last |
| INTG-02 | Divergence detected at extension load | `security.initialize()` called from `startup.register_routes()` before the domain loop (Pattern 2) |
| INTG-03 | Check never writes | Existing reader opens `"rb"` only; new module adds no file writes (test) |
| INTG-04 | Mismatch blocks mutations, reads and diagnostics continue | Same gate function returns 423 after the secret passes; same open set |
| INTG-05 | `/status/` names the differing files | `integrity` block carries `modified`/`missing`/`unexpected` |
| INTG-06 | No false positives (pycache, CRLF) | Existing (`hash_normalized`, `git ls-files`); live `verified_match` on dev junction proves it on the real tree |
| INTG-07 | Unreachable reference is not corruption | Existing three-state model; `unverifiable` never blocks and is reported separately |
| INTG-08 | Dev junction unaffected | No `_manifest.json` in repo -> `unverifiable/manifest_missing`; live stage L1 and cleanup stage L4 prove mutations still work |
</phase_requirements>

## Summary

Phase 3 left almost everything pure and tested: `revit_mcp/trust.py` has the envelope split, constant-time compare, 401/423 body builders, the three-state integrity evaluation and the bind classifier; `revit_mcp/integrity.py` reads the manifest and tree; `bridge.py` has `with_envelope()` and `load_secret()`; the deploy scripts stage one secret and one manifest. Nothing calls any of it (verified: no references from `startup.py`, `tools/`, `main.py` or other `revit_mcp/` modules; three `test_inert_*` tests in `tests/unit/test_bridge_secret_client.py` pin that state and must be flipped). Phase 5 is therefore wiring plus four things Phase 3 did not build: (1) a thin pyRevit-dependent helper (`revit_mcp/security.py`) that holds load-time state and exposes the per-route calls, (2) the open-reads list as a contract with a guard test, (3) `/status/` fields, and (4) staged publish plus a rollback script.

The riskiest parts are not the gate logic. They are (a) the amount of existing test machinery that pins "the first statement of a guarded handler is the document guard" and builds request bodies with no envelope (the Phase 2 inventory test plus four fake-pyRevit route suites and `test_document_contracts.py`), which will all go red the moment the first handler gets a gate; (b) the D-06 precondition (the extension currently on the main share must ignore an extra `_mcp` key), which this research could verify only against HEAD, not against whatever is on the share; (c) D-10's atomic swap, because a local NTFS probe run in this session shows that a directory rename fails with WinError 5 when any file inside is open without share-delete, so the "pyRevit holds no open files" premise must be measured on the real share before relying on it; and (d) D-11, which is in direct conflict with `make_manifest.py`'s own refusal to write a manifest inside the git working tree.

**Primary recommendation:** Build one tracer end to end first (envelope in `bridge`, `security.gate_or_response` on `/create_level/` only, shared test helper that adds a test envelope to fake requests), then fan out the same two-statement preamble to the remaining 33 gated routes and the `strip` preamble to the 7 open POST reads, with the AST sentinel written before the fan-out so a forgotten route fails immediately.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Attach secret to every POST | CPython MCP server (`bridge.py`) | — | Only place that builds the POST body; tool modules never import the transport |
| Verify secret, refuse 401 | Revit extension handler (first statement) | `trust.py` pure logic | D-01: explicit per-route call; must run before any Revit API/transaction use |
| Integrity check at load | Revit extension (`startup.py` -> `security.initialize`) | `integrity.py` reader, `trust.evaluate_integrity` | Runs once in the Revit process on the file tree pyRevit loads |
| Refuse 423 on mismatch | Revit extension handler (same call as secret) | — | Same open list for both gates (D-04) |
| Report secret/integrity/bind state | Revit extension `/status/` route | CPython `get_revit_status` (fingerprint compare) | `/status/` is the only always-open diagnostic channel (SEC-05) |
| Open-reads list (contract) | `trust.py` constant | `scripts/conventions.py` mirror, AST tests | Natural sibling of `UNGATED_METHODS`; pinned equal by test like `bridge.py`/`trust.py` constants |
| Forgotten-route protection | Unit tests + `scripts/conventions.py` + `intake_package.py` | — | No runtime wrapper allowed (G1) |
| Atomic publish, previous-version retention, rollback | Build server `.cmd` scripts | Share folder layout | Revit half is read over UNC; swap must be one rename |
| Live acceptance | Standalone script (CPython) + MCP tools + human restarts Revit | — | Same tier as `tests/test_phase4_live_outcomes.py` |

## Standard Stack

### Core
No new libraries. Everything is stdlib plus what the repo already uses.

| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| `hashlib`, `json`, `os`, `errno` | stdlib (CPython 3.13 dev; IronPython 3.4 level on Revit side) | secret digest, manifest, tree reads | Already used by `trust.py`/`integrity.py`, live-verified on `IPY342` (trust.py docstring: "py=3.4.2") |
| `System.Net.NetworkInformation.IPGlobalProperties` (.NET) | Revit's CLR | listener table for SEC-07 | Used in `tests/test_phase2_preflight.py:220-221` (`props.GetActiveTcpListeners()`, `ep.Port`, `str(ep.Address)`) |
| pytest | >=8.0.0 (dev group, `pyproject.toml`) | unit suite | Existing; baseline `5218 passed, 3 skipped` in 77 s (run this session) |
| httpx | >=0.28.1 | bridge transport, direct HTTP probes in live script | Existing |

### Supporting
| Component | Purpose | When to Use |
|-----------|---------|-------------|
| `deploy/secret_tool.py verify` | Pair-check the staged secret against `MCP_SECRET_FILE` | Inside staged publish, before the swap |
| `revit_mcp.integrity.check_integrity(stage_dir)` under `MCP_PYEXE` | Self-check that the staged tree matches its own manifest | Final gate before the swap (importable under pyRevit CPython: `make_manifest.py` already does this import) |
| `scripts/dev_secret.py` | Create `revit_mcp/_bridge_secret` on the dev machine | Prerequisite for any live step on the dev junction (file absent today: `ls revit_mcp/_bridge_secret` -> No such file) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-route call (D-01, locked) | Common `api.route` wrapper | Rejected by the user; breaks Phase 2 G1 test |
| `request.data` rewritten in place | Return cleaned payload to handler and change every handler | 41 handler bodies change instead of 0 |
| Atomic folder rename (D-10, locked) | `robocopy /MIR` from staging to live after all gates pass | Fallback only if the rename is blocked on the share; narrower but non-zero failure window |

**Installation:** none.

**Version verification:** not applicable (no packages). Python for dev/tests: `uv run python --version` -> 3.13.7 (this session).

## Package Legitimacy Audit

No external package is added or changed by this phase. Nothing to run through `package-legitimacy check`.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Project Constraints (from CLAUDE.md)

Extracted from `C:\Users\Admin\source\repos\revit-mcp-server\CLAUDE.md` and the user's global `CLAUDE.md` (both read this session):

- Two-Runtime Rule: Revit half (`startup.py`, `revit_mcp/`) is IronPython 3 at the Python 3.4 language level: `"{}".format(x)`, no f-strings, no `async`, no `pathlib`, no modern typing. Both halves keep the encoding cookie on line 1.
- Route modules import siblings relatively (`from .security import ...`), never flat. Mixing forms loads a module twice with separate state (matters here: `security` holds the load-time state).
- Every document mutation: transaction, `suppress_warnings(t)` immediately after `t.Start()`, commit only via `commit_and_report`. The gate must run before any of that; it never opens a transaction itself.
- POST bodies are `text/plain`, parsed only with `parse_request_data()`; never `json.loads(request.data)` (`scripts/conventions.py` rejects it).
- Route handlers never raise: wrap and return `routes.make_response(data=..., status=...)`. The gate must therefore never raise either.
- A dict is an error only with a truthy `error` key or status in error/failed/failure/exception. Do not put a top-level `error` key in `/status/` for degraded states.
- Refusals before any transaction (400/404/503, and now 401/423) carry no `outcome` block.
- Never `print()` in `main.py`/`bridge.py` under stdio; Revit-side logging via `logging.getLogger(__name__)`.
- After editing `revit_mcp/`, fully close and reopen Revit; pyRevit Reload can crash Revit.
- Shared secret / manifest paragraph in CLAUDE.md ("built, not enforced until Phase 5") must be rewritten in this phase; `tests/unit/test_secret_pipeline.py::test_claude_md_documents_the_secret_and_manifest_pipeline` pins the needles `network barrier`, `MCP_SECRET_FILE`, `scripts/dev_secret.py`, `_manifest.json`, `_bridge_secret`, `_mcp`, `deploy/make_manifest.py`, `unverifiable` - keep them.
- Release checkpoint R3: the phase proposes a release, never publishes (`publish-extension.cmd`, `build-payload.cmd`, push, tag are the user's).
- User global: commits by explicit pathspec; one writer per file; worker summaries are not evidence.

## Architecture Patterns

### System Architecture Diagram

```
MCP client (Claude / Hermes)
   |  tool call
   v
tools/<domain>_tools.py  --revit_post(route, data, ctx, target)-->  bridge.py
                                                                     |  _secret() cached; with_envelope(data, secret)
                                                                     |  (ValueError -> "not-sent" refusal, before _dispatch)
                                                                     |  _dispatch: lock, verify target, _send(...)
                                                                     v
                         POST http://127.0.0.1:48884/genpro_revit_mcp/<route>/   Content-Type: text/plain
                         body: {"_mcp": {"secret": ...}, <domain fields>}
                                                                     |
                                       pyRevit RoutesServer (HTTP thread) -> ExternalEvent -> handler(uiapp[, doc], request)
                                                                     |
        +------------------------------------------------------------+------------------------------------------+
        | FIRST STATEMENTS of every non-GET handler (2 statements)                                              |
        |   gate_refusal = gate_or_response(request)          open POST reads: strip_envelope(request)          |
        |   if gate_refusal is not None: return gate_refusal                                                    |
        |                                                                                                       |
        |   security state (set once by startup -> security.initialize):                                        |
        |     secret (from revit_mcp/_bridge_secret or None) | integrity result (check_integrity(root))         |
        |                                                                                                       |
        |   1 state missing/uninitialized ----------------------------------> 401 server_not_configured         |
        |   2 split_envelope(request.data) -> envelope, payload                                                 |
        |   3 check_secret(envelope secret, expected) != ok ---------------> 401 missing | mismatch | ...      |
        |   4 integrity.state == verified_mismatch ------------------------> 423 + files                        |
        |   5 request.data = payload re-serialized WITHOUT _mcp (type-preserving) ; return None                 |
        +------------------------------------------------------------+------------------------------------------+
                                                                     |  None
                                                                     v
                     mutation_document_or_response(...)  ->  _mutation body (Transaction, suppress_warnings, commit_and_report)
                     (execute_code / open_model / activate_document skip the doc guard but keep the gate)

GET routes and 7 open POST reads: never refused. GET /status/ additionally returns
   secret{configured, fingerprint}, integrity{state, reason, modified, missing, unexpected}, bind, health
        ^
        |  CPython get_revit_status compares Revit's fingerprint with bridge's own -> "secrets of the halves differ"

Extension load (startup.py register_routes):  _load_package -> registry.reset -> identity init -> security.initialize(root)
        -> for each domain: import + register     (integrity is read once here; edits after load show only after restart)
```

### Recommended Project Structure
```
revit_mcp/
├── trust.py        # + OPEN_POST_READ_ROUTES, secret_fingerprint(), clean-body helper, D-07 hint wording
├── integrity.py    # unchanged
├── security.py     # NEW helper (no registrar): initialize(), gate_or_response(), strip_envelope(), status_block()
├── status.py       # + security/integrity/bind block in both 200 and 503 branches
└── <domain>.py     # 34 gated handlers: 2-statement gate preamble; 7 open POST reads: strip preamble
startup.py          # + security.initialize(...) after registry.reset(), before the domain loop (no api use)
bridge.py           # + _secret() cache, envelope in revit_post, revit_get.secret_fingerprint seam
tools/status_tools.py  # get_revit_status: fingerprint compare line
deploy/
├── publish-extension.cmd   # staged build in ext-staging\, gates, swap, ext-previous\
├── rollback-extension.cmd  # NEW: ext-previous\ back to ext\
├── make_manifest.py        # + explicit dev-only repo-dest allowance for D-11 (see Pitfall 8)
tests/unit/
├── test_phase5_gate_wiring.py   # NEW: AST sentinel + behavioural route-suite rows
├── test_security_state.py       # NEW: initialize/gate/status_block against temp trees
tests/test_phase5_live_gate.py   # NEW: staged live runner + classifier (Phase 4 pattern)
```

### Pattern 1: Two-statement gate preamble, gate before the document guard
**What:** Every non-GET handler starts with the gate call and its refusal return; the document guard (when the route has one) follows.
**When to use:** all 34 gated routes. The secret must be checked first so an unauthenticated caller learns nothing about documents (412/404 bodies list candidates).
**Example (design sketch, IronPython-3.4-safe, not run):**
```python
# revit_mcp/<domain>.py
from .security import gate_or_response

@api.route("/create_level/", methods=["POST"])
def create_level_handler(uiapp, doc, request):
    """Create building levels at specified elevations."""
    gate_refusal = gate_or_response(request)
    if gate_refusal is not None:
        return gate_refusal
    document, descriptor, refusal = mutation_document_or_response(
        request_document_selector(request), uiapp=uiapp)
    if refusal is not None:
        return refusal
    return attribute_response(_create_level(document, request), descriptor, uiapp=uiapp)
```
Variable name `gate_refusal` avoids clashing with the document guard's `refusal`, which `test_phase2_inventory.py` asserts by name.

### Pattern 2: `security.py` as a load-time state holder (mirrors `identity.initialize_process_identity`)
**What:** `startup.register_routes()` already initializes identity inside `try/except`, writing failures to `registry.FAILED`. Do the same for security, after `registry.reset()` and before the domain loop.
**Why:** it satisfies the CONTEXT note "a failed gate install must be visible, not leave routes open": an `initialize` failure lands in `registry.FAILED["security"]` (so `/status/` is `degraded`), and the gate treats "no state" as `server_not_configured` (401) so routes stay closed.
**Sketch:**
```python
# startup.py, inside register_routes(), after the identity block
try:
    security = __import__("{}.security".format(_PACKAGE), fromlist=["security"])
    security.initialize(os.path.dirname(package.__path__[0]), package.__path__[0])
except Exception as exc:
    registry.FAILED["security"] = "{}: {}".format(type(exc).__name__, str(exc))
    logger.exception("Failed to initialize the security gate")
```
`startup.py` must still pass `test_startup_installs_no_common_handler_wrapper`: no `api.<attr>`, exactly one `api` argument pass (to `registrar`), no decorated function, and none of `wraps`, `setattr`, `functools`, `mutation_document_or_response`, `decide_mutation_document`, `attribute_response` in the source text [VERIFIED: tests/unit/test_phase2_inventory.py:597-616, read this session]. The sketch above uses none. `initialize` must be idempotent and recompute everything each call (a pyRevit Reload re-runs `startup.py` while submodules stay cached in `sys.modules`).
`root` is the extension root (the directory holding `startup.py` and `_manifest.json`); `package.__path__[0]` is already `os.path.realpath`'d by `_load_package`, so on the dev junction it resolves to the repo root.

### Pattern 3: AST sentinel for "closed by default" (the D-01 guard)
**What:** one test over `inventory_support.route_inventory()` (it already enumerates all 56 `@api.route` handlers and their methods and args):
- every route whose methods contain anything other than GET/HEAD: its first non-docstring statement is `<name> = gate_or_response(request)` (or, for exactly the open set, `strip_envelope(request)`), followed by the `if <name> is not None: return <name>` statement for the gated form;
- nothing at all (no call) appears before that statement (same technique as `test_a_guarded_handler_calls_the_explicit_guard_first_and_attributes_every_reply`, which compares every `ast.Call.lineno` to the guard line);
- the set of routes calling `strip_envelope` equals `trust.OPEN_POST_READ_ROUTES` exactly, and that set equals the seven keys in D-02; every other non-GET route calls `gate_or_response`;
- no GET route calls either function (a gate on a GET would break SEC-05);
- every gated handler declares `request` (all 41 non-GET handlers do: measured this session, only GET handlers lack it).
**Measured counts (this session, via `inventory_support.route_inventory()`):** 56 routes; 41 non-GET; 15 GET; 34 gated (41 minus the 7 open); no route has more than one method; all 7 open POST reads exist as POST routes. `CLAUDE.md` still says 51 routes; the inventory test itself notes the doc is stale.

### Pattern 4: Strip without refusing on the 7 open POST reads
The default (CONTEXT discretion) is for the bridge to envelope every POST. The seven open handlers then see an extra `_mcp` key in `request.data` that they would ignore, but D-02 says the secret must not stay in anything a handler reads. A one-statement `strip_envelope(request)` removes it and never refuses, even for a wrong secret, so a mismatch cannot block diagnostics (SC3). Same type-preserving rewrite as the gate.

### Pattern 5: `/status/` block built from module state; bind from .NET at request time
- `status.py` handler `revit_status(verbose=None)` is pinned to run on pyRevit's HTTP thread: `HTTP_THREAD_ALLOWLIST["/status/"] == ("status", "revit_status", ("verbose",))` and the test asserts `ROUTE_BY_KEY["/status/"].args == ["verbose"]` [VERIFIED: inventory_support.py:147-150 and test_phase2_inventory.py:418-423]. So the block is computed from module state plus a .NET call, never from `uiapp`.
- Bind is computed at request time, not at load: the Routes server may not be bound while `startup.py` runs (identity is likewise read lazily in `/status/`). Build `(host, port)` pairs from `IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners()` using `str(ep.Address)` and `ep.Port` and pass them to `trust.classify_listeners(endpoints, port)` with the bound port from the process identity (`actual_port`). On any exception report `unknown`.
- Include the block in the 200 branch and the 503 (no document) branch; the live gate starts Revit with no model, so the 503 body is the first thing the operator sees. Never a top-level `error` key for degraded states.

Proposed shape (names are Claude's discretion per CONTEXT; this is a recommendation):
```json
{"secret": {"configured": true, "fingerprint": "1a2b3c4d"},
 "integrity": {"state": "verified_mismatch", "reason": null,
               "modified": ["revit_mcp/x.py"], "missing": [], "unexpected": ["revit_mcp/_zz_probe.py"]},
 "bind": "loopback_only"}
```
`integrity` is `trust.evaluate_integrity`'s result dict verbatim (keys `state`, `reason`, `modified`, `missing`, `unexpected`, sorted) [VERIFIED: trust.py:282-290].
Health rule recommendation: `degraded` for `verified_mismatch`, for `bind == exposed` (03 D-16), and for a secret that is not configured (every mutation is refused); not for `unverifiable` (dev junction is permanently `manifest_missing`, INTG-08). See Open Question 1.

### Pattern 6: Envelope in `revit_post`, not in `_send`
`_send` runs after `progress["sent"] = True` is set in `_verified_exchange`, so a `ValueError` from `with_envelope` (non-dict body, or a body already holding `_mcp`) would be classified by `_dispatch`'s generic `except` as `_unconfirmed_kind(method, progress)` = `"unknown"` for a POST, i.e. "the change may have been applied" - false, nothing left the process. Build the body at the top of `revit_post`, turn `ValueError` into a plain refusal string tagged `"not-sent"` (as `_dispatch` already does for `_queue_busy_message`), and pass the finished body into the existing `write` closure/`_send`. Keep `_send` otherwise byte-identical so `test_secret_gate_e2e.py` still drives the real `_send`.
`load_secret()` currently must not run at import (`test_inert_load_secret_is_not_run_at_import`); keep it lazy: a memoized accessor loaded on the first POST, reset by tests. A rotated secret needs a restart of the MCP server process (consistent with the documented rotation and D-13).

### Anti-Patterns to Avoid
- **A module-level "open" flag or env var that bypasses the gate for tests.** A bypass in production code contradicts "built in, not a setting" (D-09 rejected the kill-switch file for the same reason). Tests add the envelope to their fake requests instead.
- **Reading the secret per request.** Load once in `initialize`; rotation is a restart (documented).
- **Putting the gate inside `mutation_document_or_response`.** Three gated routes (`/execute_code/`, `/open_model/`, `/activate_document/`) do not call it, and it lives in `identity.py`, a different concern.
- **Re-hashing files per request.** D-level decision: load-time only; document that edits after load show after restart.
- **Echoing request data in refusal bodies.** `auth_failure`/`integrity_failure` already carry only fixed text and sorted file names.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Envelope parsing | New JSON parse in the gate | `trust.split_envelope` (uses only `parse_request_data`) | Handles bytes/str/dict; IronPython-3 `json.loads(bytes)` TypeError is why the helper exists |
| Secret compare | `==`, `hmac.compare_digest` | `trust.check_secret` / `secret_matches` | Constant time over SHA-256 digests; documented CLR reason; leak tests exist |
| Refusal bodies | Ad-hoc dicts | `trust.auth_failure(reason)` -> `(body, 401)`; `trust.integrity_failure(files)` -> `(body, 423)` | Fixed text, no secret, reason clamped; tests pin the `Error: 401 - ...` pair through `format_response` |
| Integrity verdict | Own walk/hash | `integrity.check_integrity(root)` | Three states, ENOENT corroboration (WR-01), never raises, read-only |
| Bind verdict | String tests on addresses | `trust.classify_listeners` | Handles `::ffff:127.x`, scope ids, brackets, octal-looking quads |
| Which routes exist / their methods | Hand list | `inventory_support.route_inventory()` | Already the single AST discovery used by Phase 2 tests |
| Manifest generation | Directory walk | `deploy/make_manifest.py` (`git ls-files`) | Walk would hash pycache/editor files (INTG-06) |
| Secret creation/staging | Copy commands | `deploy/secret_tool.py ensure/stage/verify` | Create-once, byte-identical, never prints value |

**Key insight:** every decision the phase needs already exists as a pure function; the work is placement (first statement, load time, status), proof (AST + behavioural tests), and deployment safety (staged swap, rollback). New logic should be limited to: type-preserving body cleaning, the fingerprint, the open-set constant, and the `.NET` listener adapter.

## Runtime State Inventory

Not a rename/refactor/migration phase in the Runtime-State sense (no string is renamed). Two adjacent runtime-state facts the planner must treat as inventory:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None - the secret and manifest are files, no datastore | None |
| Live service config | pyRevit `[routes]` on this dev machine: `host = "127.0.0.1"`, `port = 48884` (`%APPDATA%\pyRevit\pyRevit_config.ini`, read this session). pyRevit's own core API route `POST /sessions/` (reload pyRevit) lives in the same RoutesServer (`pyRevitCore.extension/lib/pyrevitcore_api.py:12`) and is outside our gate | None for the phase; record as residual in docs (Security Domain) |
| OS-registered state | Update trigger at logon (scheduled task or Startup folder) refreshes the payload only; no registration changes | None |
| Secrets/env vars | `revit_mcp/_bridge_secret` absent on this dev machine (verified `ls`); `MCP_SECRET_FILE` on build server default `%MCP_SHARE_ROOT%\_build\bridge_secret` (config.cmd). Pilot share has its own file, hence its own secret | Dev: run `uv run python scripts/dev_secret.py` once. Release: fingerprints (D-08) before promotion |
| Build artifacts | `ext-previous\` will hold an older extension including its `revit_mcp\_bridge_secret` copy | Rotation procedure must also clear `ext-previous\` (stale secret copy) |

## Common Pitfalls

### Pitfall 1: The gate is added and ~hundreds of existing handler tests go red
**What goes wrong:** the four fake-pyRevit route suites build requests as `types.SimpleNamespace(data=json.dumps(body).encode("utf-8"))` with no `_mcp` (`request_of` in `test_routes_*_identity.py`; `FakeRequest` in `test_document_contracts.py:1290`). A gated handler answers 401 `missing`, so every success-path row fails.
**Why:** the gate is real code in the handler path; no bypass exists by design.
**How to avoid:** first plan = one shared test helper (in `tests/unit/conftest.py` or `inventory_support.py`) that (a) configures `security` state with a known test secret and `unverifiable` integrity and (b) wraps fake bodies with `{"_mcp": {"secret": TEST_SECRET}}`. Replace the five local `request_of`/`FakeRequest` definitions with it before touching any handler. Keep rows that exercise refusals explicit.
**Warning signs:** many `status 401` assertions failing at once in route suites.

### Pitfall 2: Phase 2 inventory test pins "first statement is the document guard"
**What goes wrong:** `test_a_guarded_handler_calls_the_explicit_guard_first_and_attributes_every_reply` reads `statements[0]`/`statements[1]` as the guard assignment and its `if refusal is not None` (test_phase2_inventory.py:436-473).
**How to avoid:** amend it in the same change: skip the two gate statements, then apply the existing assertions to `statements[2]`/`statements[3]`; keep "no call before the guard line" but compare against the gate line. Also `test_the_execute_route_is_unguarded_...` and `test_open_model_is_process_level_...` inspect call-name sets only and stay green.

### Pitfall 3: `if not request.data` truthiness changes when the body is rewritten
**What goes wrong:** several handlers do `if not request or not request.data: return 400` (e.g. `annotation.py:38`, `editing.py:33,148`, `structure.py:37,156`, `placement.py:162`, `documentation.py:179`). If the gate replaces the body with a parsed `{}` dict, that is falsy and the route answers "No data provided" where it previously proceeded with bytes `b"{}"` (truthy).
**How to avoid:** rewrite `request.data` in the same type it arrived in: bytes -> `json.dumps(payload).encode("utf-8")`, text -> `json.dumps(payload)`, dict -> the cleaned dict (if the incoming dict was empty after stripping, keep the old truthiness by leaving the original type). `json.dumps` default `ensure_ascii=True` keeps it ASCII-safe on both runtimes. Unit-test the empty-payload case on every runtime alias.

### Pitfall 4: A pre-send `ValueError` is reported as "outcome unknown"
See Pattern 6. Build the envelope before `_dispatch`.

### Pitfall 5: `request.data` is writable on the dev pyRevit - fleet unverified
**What goes wrong:** `Request.data` is a plain attribute in the dev machine's clone (`pyrevitlib/pyrevit/routes/server/base.py:21-29`: `self.data = data`). A different pyRevit build could make it a property. [VERIFIED: local file; fleet version not read].
**How to avoid:** the gate treats any failure to rewrite the body as a refusal (fail closed, loud 401/500), so a non-writable attribute shows up in the first live stage, not as a leaked secret. The live stage L1 positive control proves the rewrite works on the real engine.

### Pitfall 6: New untracked `.py` breaks the manifest generator and the publish smoke test
**What goes wrong:** `make_manifest.build_manifest` raises `ManifestError("untracked .py in the published tree ...")` (deploy/make_manifest.py:128-134) and `test_publish_smoke_scratch_share` runs the real publish against the current working tree. A freshly created `revit_mcp/security.py` that is not in the git index fails it.
**How to avoid:** `git add revit_mcp/security.py` (index is enough; `git ls-files` lists staged files) as soon as the file exists, before running the full suite or any live manifest step. The same applies to `_zz_probe.py`: create it only AFTER the temporary manifest is generated (D-12 order).

### Pitfall 7: A forgotten temporary `_manifest.json` blocks the dev's own mutations
**What goes wrong:** on the junction, any edit to a listed file after the manifest is written makes the next Revit start `verified_mismatch` -> 423 for every gated route, `execute_code` included (D-04).
**How to avoid:** the live runner has an explicit `cleanup` stage that deletes `_manifest.json` and `revit_mcp/_zz_probe.py`, `git checkout`s the modified file, and asserts `git status --porcelain` is clean for those paths; the final restart must show `unverifiable/manifest_missing` and a working mutation (D-11).

### Pitfall 8: D-11 contradicts `make_manifest.py`'s own refusal
**What goes wrong:** D-11 says the temporary manifest is written by `make_manifest.py` into the junction repo root. `build_manifest` calls `_refuse_repo_dest(repo, dest)` and raises `"refusing to write a manifest into the git working tree (INTG-08)"` whenever `dest` is inside the repo (deploy/make_manifest.py:98-110), and `tests/unit/test_make_manifest.py` pins the refusal.
**How to avoid (recommended):** add an explicit, opt-in parameter/flag (for example `allow_repo_dest=True` / `--allow-repo-dest`) that only the live-gate runner uses, accepted only when the resulting `_manifest.json` path is git-ignored (`git check-ignore` exit 0; `.gitignore:37` ignores `_manifest.json` [VERIFIED: git check-ignore output this session]). Default behaviour and the existing refusal test stay unchanged; add a test that the flag is refused when the file would not be ignored. Surface to the user as a small, necessary amendment of D-11's mechanism (intent unchanged).

### Pitfall 9: Directory rename is blocked by any open file inside (measured locally)
**What goes wrong:** D-10's swap renames `ext\revit-mcp-server.extension`. A probe run this session on local NTFS (Python `open(..., "rb")` handle held on a file inside the folder, then `os.rename` of the parent folder) failed with `[WinError 5]` (access denied). So the premise "pyRevit holds no open files" is exactly what must be verified on the real share; an open handle on any file or on the folder itself (Explorer window, a process with it as working directory, an SMB handle lease) blocks the swap.
**How to avoid:** make the swap failure non-destructive and detectable: `move LIVE PREV` first (a failure leaves `ext\` intact and aborts the publish), then `move STAGE LIVE`; if the second move fails, move PREV back. Run the probe on the pilot share with Revit open on the extension before relying on it (Open Question 2). Fallback if blocked: copy live to `ext-previous\` with robocopy, then `robocopy /MIR` staging over live only after every gate passed (narrow window, not atomic).
[ASSUMED] for SMB specifics; evidence for SMB is only forum anecdotes (a TrueNAS thread reporting a folder that could not be renamed after a file inside had been opened) and MS-FSCC's rule that a rename needs delete access/sharing; no source found tying it to an SMB server specifically.

### Pitfall 10: Mixed versions - new extension with old bridge, and payload rollback
**What goes wrong:** new ext + old bridge = every mutation 401 `missing` (by design, D-07). Rolling the payload back (junction switch) while the ext is new reproduces that state. A running MCP server process keeps the old `bridge.py` in memory even after `update.cmd` refreshed the payload, so a long assistant session needs a restart too.
**How to avoid:** the 401 `missing` hint wording must name the actions D-07 lists ("Update RevitMCP" or sign in again to Windows, then restart the assistant session). Document: never roll the payload back while the ext is new; ext rollback needs no payload change (a bridge that sends `_mcp` is harmless to the previous ext, D-06). Matrix:

| Revit ext | Bridge | Result |
|-----------|--------|--------|
| old | old | works (today) |
| old | new (sends `_mcp`) | works iff old handlers ignore `_mcp` (D-06 proof) |
| new | old (sends nothing) | gated routes 401 `missing`; reads and `/status/` fine |
| new | new, same secret | works |
| new | new, different secret (pilot vs fleet) | gated routes 401 `mismatch`; fingerprints differ in `get_revit_status` |
| new, no `_bridge_secret` in ext | any | 401 `server_not_configured` (fail closed) |
| new, integrity `verified_mismatch` | any | gated routes 423 naming files; reads fine |

### Pitfall 11: Refusal hint texts are pinned by tests and must match D-07
`trust._AUTH_HINTS[AUTH_MISSING]` today reads "The MCP server sent no shared secret. Update the payload so _bridge_secret exists and restart the MCP server." [VERIFIED: trust.py:43-46]. D-07 wants the model-visible text to say to run "Update RevitMCP" (or sign in again) and restart the assistant session. Update the three hints (including the `mismatch` text for the pilot-vs-fleet case) and the tests that pin them (`test_trust_secret.py`, `test_format_response.py` pair, `test_secret_gate_e2e.py`); never put the secret or its fingerprint in a hint.

### Pitfall 12: The gate must run before `_stamp_exception` on `/execute_code/` and still refuse
The handler is `return _stamp_exception(_execute_code(doc, request), uiapp)`. Put the gate first; a refusal then carries no `document_scope`/`process_identity` stamp, which is acceptable: the bridge attributes provenance from its own handshake (`_received_reply` handles an unstamped body; `_stamp_agrees` returns None). Do not add `uiapp`-based identity reads into the refusal path: nothing should touch the Revit API before the secret is verified.

### Pitfall 13: `/status/` payload rendering
`_project_response` treats a dict with a truthy top-level `error` as an error and renders `status == "active"` dicts field by field via `str(value)`. Nested `integrity`/`secret` dicts render as `Integrity: {...}` lines automatically; do not add a top-level `error` for degraded states, and keep the 503 body's existing `error: "No active Revit document"` as is.

### Pitfall 14: Live gate prerequisites on the dev machine
- `revit_mcp/_bridge_secret` does not exist today; without it the extension reports `server_not_configured` and the bridge sends no envelope.
- The MCP server process of this Claude session must be the one started from the repo (`uv run main.py`), not an installed payload under `%LOCALAPPDATA%\RevitMCP\current`, or the two halves read different secrets (CLAUDE.md); it must be restarted after `bridge.py` is edited (D-13).
- Exactly one listener on 48884 before each series (`Get-NetTCPConnection -LocalPort 48884 -State Listen`); Revit currently not running (only `RevitAccelerator.exe` seen), which can start a second instance by itself.

### Pitfall 15: Two helpers lists in tests must learn the new module
`test_registration.py` pins the helper set `("utils", "textutils", "registry", "identity", "trust", "integrity")` twice (lines 238 and 256); add `security`. `scripts/conventions.py` `LOCAL_MODULES = {"utils", "textutils", "registry", "revit_mcp"}` (line ~50) does not list `identity`, `trust`, `integrity`; extend it with them and `security` so a flat `from security import ...` is rejected like a flat `utils` import. Add `security.py` (and `trust.py`/`integrity.py` if not already) to `test_trust_dialect.py` coverage so the IronPython dialect check runs on it.

## Code Examples

Design sketches. Values (`"_mcp"`, 401, 423, `"verified_mismatch"`, `"health"`, `"degraded"`, route keys) are the verbatim values read this session: `ENVELOPE_KEY = "_mcp"` (trust.py:27), `AUTH_FAILURE_STATUS = 401` (trust.py:36), `INTEGRITY_FAILURE_STATUS = 423` (trust.py:277), `INTEGRITY_MISMATCH = "verified_mismatch"` (trust.py:268 region), `"health": "degraded" if degraded else "healthy"` (status.py:76).

### `security.py` core (gate and strip)
```python
# -*- coding: utf-8 -*-
"""Load-time security state and the per-route gate (helper module, registers no routes)."""

import logging

from . import trust

logger = logging.getLogger(__name__)

_STATE = None  # set by initialize(); None means "not initialized" and the gate refuses


def initialize(root, package_dir):
    global _STATE
    import os
    from . import integrity
    secret = trust.read_secret_file(os.path.join(package_dir, trust.SECRET_FILE_NAME))
    result = integrity.check_integrity(root)            # never raises, read-only
    _STATE = {"secret": secret, "integrity": result}
    return _STATE


def _refusal(body, status):
    from pyrevit import routes
    return routes.make_response(data=body, status=status)


def _rewrite(request, raw, payload):
    """Put the payload back WITHOUT _mcp, in the type it arrived in."""
    request.data = trust.clean_body(raw, payload)        # to be added to trust.py (type-preserving)


def gate_or_response(request):
    """None when the call may proceed, else a routes response (401 or 423). Never raises."""
    try:
        state = _STATE
        raw = getattr(request, "data", None)
        envelope, payload = trust.split_envelope(raw)
        if state is None:
            return _refusal(*trust.auth_failure(trust.AUTH_SERVER_NOT_CONFIGURED))
        verdict = trust.check_secret(trust.envelope_secret(envelope), state["secret"])
        if verdict != trust.AUTH_OK:
            return _refusal(*trust.auth_failure(verdict))
        result = state["integrity"]
        if result.get("state") == trust.INTEGRITY_MISMATCH:
            return _refusal(*trust.integrity_failure(trust.mismatch_files(result)))
        _rewrite(request, raw, payload)
        return None
    except Exception:
        # Fail closed, fixed text, no locals in the message.
        return _refusal(*trust.auth_failure(trust.AUTH_MISMATCH))
```
Note the import of `from . import trust` is relative, as CLAUDE.md requires; `trust.py` already imports `.textutils` relatively.

### Envelope in the bridge (before `_dispatch`)
```python
# bridge.py, revit_post
async def revit_post(endpoint, data, ctx=None, target=None, timeout=30.0, params=None):
    try:
        body = with_envelope(data, _secret())            # ValueError: not a dict / reserved key present
    except ValueError as exc:
        return _uncertain("Error: {}".format(exc), "not-sent", None)

    async def write(client):
        return await _send(client, "POST", endpoint, body, timeout, params)

    return await _dispatch("POST", endpoint, ctx, timeout, write, target)
```
`_uncertain(text, kind, requested)` exists (bridge.py:499) and `_dispatch` already passes `requested=None` through it on early failure.

### Sentinel skeleton (extends `inventory_support`)
```python
GATE = "gate_or_response"
STRIP = "strip_envelope"

def _preamble(route):
    statements = _body(route.node)                    # helper already in test_phase2_inventory.py
    first = statements[0]
    assert isinstance(first, ast.Assign) and isinstance(first.value, ast.Call)
    return call_name(first.value), statements

@pytest.mark.parametrize("route", NON_GET_ROUTES, ids=lambda r: r.key)
def test_every_non_get_route_opens_with_the_gate_or_the_strip(route):
    name, statements = _preamble(route)
    if route.key in trust.OPEN_POST_READ_ROUTES:
        assert name == STRIP
    else:
        assert name == GATE
        second = statements[1]
        assert isinstance(second, ast.If) and isinstance(second.body[0], ast.Return)
    first_line = statements[0].lineno
    for call in route.calls_in():
        assert call.lineno >= first_line
```

### Staged publish skeleton (CRLF, ASCII only in the real file)
```bat
set "LIVE=%MCP_SHARE_ROOT%\ext\%MCP_EXT_NAME%"
set "STAGE=%MCP_SHARE_ROOT%\ext-staging\%MCP_EXT_NAME%"
set "PREV=%MCP_SHARE_ROOT%\ext-previous\%MCP_EXT_NAME%"
rem build everything into %STAGE% (the old %DEST%), all gates there; then:
"%MCP_PYEXE%" "%~dp0secret_tool.py" verify --secret-file "%MCP_SECRET_FILE%" --artifact "%STAGE%\revit_mcp\_bridge_secret" || exit /b 1
rem integrity self-check of the staged tree (verified_match against its own manifest) || exit /b 1
if exist "%PREV%" rmdir /s /q "%PREV%"
if not exist "%MCP_SHARE_ROOT%\ext-previous" mkdir "%MCP_SHARE_ROOT%\ext-previous"
if exist "%LIVE%" ( move "%LIVE%" "%PREV%" >nul || (echo ERROR: live extension is in use, nothing changed. & exit /b 1) )
move "%STAGE%" "%LIVE%" >nul || ( if exist "%PREV%" move "%PREV%" "%LIVE%" >nul & echo ERROR: swap failed, previous restored. & exit /b 1 )
```
This is a sketch of the order of operations only; exact `cmd` quoting needs the same care as the existing script, and `ext`, `ext-staging`, `ext-previous` must be on one volume/folder target for `move` to be a rename (DFS namespace behaviour not verified).

## State of the Art

| Old Approach (this repo before Phase 5) | Current Approach | When Changed | Impact |
|------------------------------------------|------------------|--------------|--------|
| Publish wipes live `ext\` then copies, stages secret, writes manifest (WR-02) | Build in `ext-staging\`, gate, swap, keep `ext-previous\` | This phase (D-10) | A failed publish leaves live untouched; rollback is a rename |
| "`pyRevit offers no way to choose the bind host`" (trust.py docstring, 03 D-16) | pyRevit builds on the dev machine expose `host` in `[routes]` (`routes_host` in `pyrevit/userconfig.py`; config has `host = "127.0.0.1"`) | observed this session on the dev clone | Forced loopback bind may become feasible later; still deferred (CONTEXT out-of-scope); do not change the docstring claim without checking the fleet pyRevit version |
| Phase 3 inert wiring (`test_inert_*`) | Live wiring | This phase | Three inert-pin tests flip to "wired" pins |

**Deprecated/outdated:** the ROADMAP phrase "chokepoint in `startup.py`" (CONTEXT D-01 says so itself); `CLAUDE.md` "54 tools over 51 routes" (inventory shows 56 routes); the "built, not enforced until Phase 5" sharp-edge paragraph.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A directory rename on the fleet SMB share succeeds while stations have Revit open on the extension | Pitfall 9, D-10 | Publish aborts at the first swap (non-destructive by design); fallback to robocopy `/MIR` after gates; returns to user per D-10 |
| A2 | `routes.make_response(data=..., status=401/423)` is passed through by pyRevit's response parser like 409/422 | Pattern 1 | Refusal arrives as a different status; caught by the first live negative probe. 409 and 422 are already used live; 401/423 were never sent live |
| A3 | `Request.data` is assignable on the fleet's pyRevit (6.5.5 vetted installer) | Pitfall 5 | Gate fails closed on every mutation; caught in live stage L1 |
| A4 | The pre-R3 extension on the main share ignores `_mcp` in every POST route (D-06) | Pitfall 10, Open Question 3 | Payload-first order not applicable; proof tool + pilot probe required before publishing the payload |
| A5 | `str(ep.Address)` from `GetActiveTcpListeners()` yields strings `classify_listeners` recognizes (`127.0.0.1`, `0.0.0.0`, `::1`, `::`) | Pattern 5 | `bind` reports `unknown` or `exposed` wrongly; live check expects `loopback_only` on the dev host |
| A6 | `check_integrity` over the UNC share at Revit start is fast enough (about 30 files read and hashed) | Pattern 2 | Slower extension load; not measured; Revit starts in 60-180 s anyway |
| A7 | `ext`, `ext-staging`, `ext-previous` live on one DFS folder target/volume so `move` is a rename | Code Examples | `move` becomes copy+delete (not atomic) or fails |
| A8 | An 8-hex SHA-256 fingerprint of a `token_urlsafe(32)` secret on the open `/status/` is acceptable disclosure | Security Domain | Weak/manual secret would be guessable from the fingerprint; `secret_tool` enforces charset and length only |
| A9 | No pyRevit/Revit component keeps open handles inside the loaded extension folder | Pitfall 9 | See A1 |

## Open Questions

1. **Health policy for non-blocking states.**
   - What we know: dev junction is permanently `unverifiable/manifest_missing` and must not look broken (INTG-08); `exposed` -> `degraded` (03 D-16); a missing secret refuses every mutation.
   - What's unclear: whether `unverifiable` with `read_error`/`absence_unconfirmed` on a fleet machine should be `degraded`.
   - Recommendation: degrade for `verified_mismatch`, `exposed`, and `secret.configured == false`; report `unverifiable` in the block without degrading. Planner confirms with the user if desired (names are discretion).

2. **Does the swap survive a running Revit on the share?**
   - What we know: local NTFS refuses to rename a folder with an open file inside (measured, WinError 5).
   - What's unclear: what pyRevit/Revit keep open on `\\srv-dfs\...\ext\...` during a session.
   - Recommendation: one probe on the pilot share (Revit open with the extension loaded, run the staged swap) is a pilot-R3 checklist item; the script is non-destructive on failure. If it fails, return to the user for the robocopy fallback.

3. **Which extension tree is on the main share now, and does it tolerate `_mcp`?**
   - What we know: static scan of HEAD `revit_mcp/*.py` (this session): 60 functions parse a request body via `parse_request_data`; every use of the parsed variable is `.get(...)`, subscript, `in`, comparison, `isinstance` or truthiness; the only other "uses" flagged were later rebindings of the name `data` to the reply dict (false positives in `detail.py`, `documentation.py`, `editing.py`, `interop.py`, `tags.py`, `parameters.py`). No handler iterates, copies or echoes the request body. R1 and R2 were never published (RELEASES.md Ledger), so the share holds an older tree whose handlers were not scanned.
   - Recommendation: add a small checked-in scanner (the prototype logic above, made rebinding-aware and also flagging any `request.data` use that does not go through `parse_request_data`) and run it against the actual shared `revit_mcp\` folder before the payload is published; corroborate live on the pilot with paired requests (with and without `_mcp`) on harmless invalid bodies for every POST route, comparing status and body text.

4. **Positive control after cleanup vs the one-shot rule.**
   - What we know: write steps are never repeated (project rule); D-11 wants "mutations work again" after the dev manifest is removed.
   - Recommendation: the post-cleanup positive control is a distinct, uniquely named `create_level` (its own step in the record, counted in `POSTS_SENT`), never a retry of an earlier step.

5. **pyRevit core `POST /sessions/` (reload pyRevit) is outside the gate.**
   - What we know: it sits on the same server; reload is the action CLAUDE.md warns can crash Revit.
   - Recommendation: out of scope; add one sentence to the user docs next to the "network barrier" statement. Not a Phase 5 task.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv + Python | unit suite, live runner | yes | Python 3.13.7 | — |
| git | manifest generation, smoke test | yes | 2.56.0.windows.2 | — |
| robocopy, cmd | publish smoke test | yes (`/c/WINDOWS/system32/robocopy`) | built in | — |
| pyRevit (dev clone) | reading routes internals | yes (`%APPDATA%\pyRevit-Master`) | version not read | — |
| Revit with a document | live gate | no (not running; only `RevitAccelerator.exe`) | — | Human starts Revit; Claude cannot |
| Pilot share / main share write access | publish pipeline proof | not touched | — | Scratch-share smoke test only (D-11: pipeline proven on the R3 pilot) |
| Dev secret file `revit_mcp/_bridge_secret` | live gate | no | — | `uv run python scripts/dev_secret.py` |

**Missing dependencies with no fallback:** a human to restart Revit between live stages.
**Missing dependencies with fallback:** dev secret file (script exists).

## Validation Architecture

> Nyquist validation enabled (`.planning/config.json` has no `nyquist_validation` key; absent = enabled).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0.0 (dev group); anyio asyncio backend for bridge tests |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests/unit"]` |
| Quick run command | `uv run pytest tests/unit/test_trust_envelope.py tests/unit/test_trust_secret.py tests/unit/test_trust_integrity.py tests/unit/test_secret_gate_e2e.py tests/unit/test_bridge_secret_client.py tests/unit/test_phase5_gate_wiring.py tests/unit/test_security_state.py -q` |
| Full suite command | `uv run pytest tests/unit -q` (baseline 5218 passed, 3 skipped, 77 s, this session) |
| Route worlds command | `uv run pytest tests/unit/test_routes_analysis_color_identity.py tests/unit/test_routes_document_interop_identity.py tests/unit/test_routes_mep_parameter_identity.py tests/unit/test_routes_view_code_identity.py tests/unit/test_document_contracts.py -q` |
| Live runner | `uv run python tests/test_phase5_live_gate.py <subcommand>` (human restarts Revit between stages) |

### Phase Requirements -> Test Map
| Req ID / Criterion | Behavior | Test Type | Automated Command | File Exists? |
|--------------------|----------|-----------|-------------------|-------------|
| SEC-01, SC1 | Every non-GET route (34) refuses before any side effect without a valid secret | AST sentinel + fake-world rows (zero transactions/collectors touched on 401) | `uv run pytest tests/unit/test_phase5_gate_wiring.py -q` | No - Wave 0 |
| SEC-01, SC1 live | Unauthenticated `create_level` -> 401; `list_levels` shows no level; valid secret -> 200 and level present | live, one-shot | `uv run python tests/test_phase5_live_gate.py run --stage baseline ...` | No - Wave 0 |
| SEC-02 | POST body is `text/plain` and carries `_mcp` under the reserved key; model-built `_mcp` refused as "not-sent" | unit (bridge) | `uv run pytest tests/unit/test_bridge_secret_client.py tests/unit/test_secret_gate_e2e.py -q` | Yes (flip the 3 `test_inert_*`) |
| SEC-03 | 401/423 reach the model as `Error: 401 - ...` / `Error: 423 - ...`; wrong secret through the production bridge | unit + live | `uv run pytest tests/unit/test_format_response.py -q` | Yes |
| SEC-04 | Compare unchanged | unit regression | `uv run pytest tests/unit/test_trust_secret.py -q` | Yes |
| SEC-05, SC3 | GET routes and the 7 open POST reads never call the gate; `strip_envelope` never refuses (wrong secret included) | AST sentinel + unit | `uv run pytest tests/unit/test_phase5_gate_wiring.py -q` | No - Wave 0 |
| SEC-05, SC3 live | Direct GET `/status/`, GET `/list_levels/`, POST `/document_levels/` with no/wrong envelope -> 200 | live | live runner, stages baseline and corrupt | No - Wave 0 |
| SEC-06 | Secret absent from 401/423 bodies, caplog, handler replies; `request.data` after the gate has no `_mcp`; live record contains no secret value | unit leak tests + live record scan | `uv run pytest tests/unit/test_security_state.py -q` | No - Wave 0 |
| SEC-07 | Listener pairs -> `loopback_only`/`exposed`/`unknown`; status block wiring with fake endpoints; never blocks | unit + live (`bind == loopback_only` on dev) | `uv run pytest tests/unit/test_trust_listeners.py tests/unit/test_security_state.py -q` | Partly |
| SEC-08, D-08 | Fingerprint parity bridge vs trust; compare line in `get_revit_status`; pipeline pair check | unit + live (fingerprints equal on dev) | `uv run pytest tests/unit/test_secret_pipeline.py tests/unit/test_status_target.py -q` | Partly |
| INTG-01 | Manifest from `git ls-files` | unit + scratch publish smoke | `uv run pytest tests/unit/test_make_manifest.py tests/unit/test_secret_pipeline.py -q` | Yes |
| INTG-02, SC2 | `security.initialize` on a temp tree reports modified/unexpected; `startup.register_routes` calls it before the domain loop | unit (temp tree + AST of startup) | `uv run pytest tests/unit/test_security_state.py tests/unit/test_phase2_inventory.py -q` | No - Wave 0 |
| INTG-03 | Reader and new module never write | unit (existing `never_writes` family + new) | `uv run pytest tests/unit/test_integrity_reader.py -q` | Yes |
| INTG-04, SC2 | `verified_mismatch` -> 423 on gated routes after the secret passes; reads continue | unit rows + live | `uv run pytest tests/unit/test_phase5_gate_wiring.py -q` | No - Wave 0 |
| INTG-05, SC2 live | `/status/` names both `revit_mcp/<module>.py` (modified) and `revit_mcp/_zz_probe.py` (unexpected) | live stage "corrupt" | live runner | No - Wave 0 |
| INTG-06 | Real tree `verified_match` with a manifest on the junction | live stage "manifest-match" | live runner | No - Wave 0 |
| INTG-07 | `unverifiable` reported, not blocking, not degraded | unit + live | `uv run pytest tests/unit/test_trust_integrity.py tests/unit/test_security_state.py -q` | Partly |
| INTG-08 | Dev junction without manifest: mutations work | live stages baseline and cleanup | live runner | No - Wave 0 |
| D-10 | Staged publish leaves live untouched on any gate failure; `ext-previous` holds the prior tree; rollback restores it | unit smoke on a scratch share (Windows) | `uv run pytest tests/unit/test_secret_pipeline.py -q` (extended) | Partly |
| D-01 | `scripts/conventions.py` rejects a non-GET route without the gate; intake and new_tool template emit it | unit | `uv run pytest tests/unit/test_conventions.py tests/unit/test_phase5_gate_wiring.py -q` | Partly |
| D-06 | Scanner finds no handler that iterates/echoes the body; paired live probe on the pilot | static + pilot (not in this phase's dev run) | scanner command TBD in plan | No - Wave 0 |

### Sampling Rate
- **Per task commit:** the quick run command above plus the touched route suite.
- **Per wave merge:** `uv run pytest tests/unit -q` (about 80 s) and `uv run python tests/test_init_latency.py` after any `bridge.py` change (cold-start gate under 2.0 s).
- **Phase gate:** full suite green; then live stages in order (below); then `/gsd-verify-work`.

### Live acceptance procedure (restart-per-iteration, one-shot writes)
Modeled on `tests/test_phase4_live_outcomes.py` (template/run/classify subcommands, raw record kept outside the repo, sentinel line plus `POSTS_SENT=<n>`, exit codes 0/1/2, pure classifier unit-tested offline in `tests/unit/test_phase4_live_outcomes.py` style). Proposed tokens: `PHASE5_GATE_OK` / `PHASE5_GATE_STOP`.

Preconditions before every series: `uv run python scripts/dev_secret.py` done once; MCP server of the session restarted after the latest `bridge.py` edit; `Get-NetTCPConnection -LocalPort 48884 -State Listen` returns exactly one row (CLAUDE.md); Revit started with NO model and one throwaway unsaved model opened via `open_model`; no workshared model on the command line.

| Stage | Revit state | Steps (all direct HTTP `Content-Type: text/plain; charset=utf-8` unless "MCP") | Proves |
|-------|-------------|----------------------------------------------------------------------------------|--------|
| L1 baseline | restart; no `_manifest.json` | GET `/status/` -> 200/503 body has `secret.configured true`, fingerprint equals the bridge's own, `integrity.state unverifiable/manifest_missing`, `bind loopback_only`; POST `/create_level/` no envelope with name `P5_REJECTED_<ts>` -> 401 `missing`; same with wrong secret -> 401 `mismatch`; POST `/execute_code/` no envelope -> 401 (negative only); GET `/list_levels/` and POST `/document_levels/` no envelope -> 200; MCP `list_levels` -> `P5_REJECTED_*` absent; MCP `create_level` name `P5_ACCEPTED_<ts>` -> 200; MCP `list_levels` -> present; wrong secret through the production bridge -> model-visible `Error: 401 - ...` | SEC-01/03/05/06, INTG-08, SC1, SC3 |
| L2 manifest-match | write temp manifest (flagged repo-dest), restart | GET `/status/` -> `verified_match`; read routes 200; no new write | INTG-02/06 |
| L3 corrupt | append a comment to one domain module, create `revit_mcp/_zz_probe.py` (after manifest exists), restart | GET `/status/` -> `verified_mismatch` naming `modified` module and `unexpected` `revit_mcp/_zz_probe.py`, `health` degraded; MCP `create_level` (valid secret) -> 423 and `list_levels` shows the name absent; `/execute_code/` with a valid secret -> 423; GET `/list_levels/`, POST `/document_levels/` -> 200 | INTG-04/05, SC2, SC3 |
| L4 cleanup | delete manifest and probe file, `git checkout` the module, restart | `unverifiable/manifest_missing`; distinct positive-control `create_level` -> 200 (its own step, never a retry); `git status --porcelain` clean for those paths | INTG-08, D-11 |

Rules: a write step is never repeated; `POSTS_SENT` counts every POST handed to the transport; a stop after a write is a finding, not a retry. D-13 has Claude drive the stages; keep the project's prior practice that the classifier never grants acceptance by itself, so end with an explicit engineer confirmation recorded in VERIFICATION (the user restarts Revit and observes).

### Wave 0 Gaps
- [ ] `tests/unit/test_phase5_gate_wiring.py` - AST sentinel (Pattern 3) plus behavioural rows (401/423 before any transaction)
- [ ] `tests/unit/test_security_state.py` - initialize/gate/strip/status_block against temp trees, leak tests, IronPython-alias simulation
- [ ] Shared test helper adding the test envelope and configuring `security` state; replace `request_of`/`FakeRequest` in the 4 route suites and `test_document_contracts.py`
- [ ] Flip `test_inert_send_posts_exactly_json_dumps`, `test_inert_no_production_call_sites`, `test_inert_load_secret_is_not_run_at_import` into wired pins
- [ ] Amend `test_a_guarded_handler_calls_the_explicit_guard_first_and_attributes_every_reply` for the two-statement preamble
- [ ] Extend `scripts/conventions.py` (`check_route_gate`, `LOCAL_MODULES`), `scripts/new_tool.py` template, `scripts/intake_package.py` paths, and `test_conventions.py`
- [ ] `test_registration.py` helper lists (+`security`); `test_trust_dialect.py` (+`security.py`)
- [ ] `tests/test_phase5_live_gate.py` plus `tests/unit/test_phase5_live_gate.py` (classifier)
- [ ] Scanner for D-06 (checked in, tested on fixtures)
- [ ] `make_manifest.py` opt-in repo-dest flag + tests; staged publish + `rollback-extension.cmd` + extended smoke test (CRLF/ASCII pinned by existing test)
- [ ] Dev secret file via `scripts/dev_secret.py` (environment, not code)

## Security Domain

> `security_enforcement` not set in `.planning/config.json`: treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (shared secret, machine-to-machine) | `trust.check_secret`: SHA-256 digests, XOR-accumulated compare; stable 32-byte `token_urlsafe` secret created once by `secret_tool.py` |
| V3 Session Management | no | Stateless per-request secret; no sessions |
| V4 Access Control | yes | Closed-by-default per-route gate; explicit open list (`OPEN_POST_READ_ROUTES`) guarded by AST test and `conventions.py` |
| V5 Input Validation | yes | Envelope parsed only via `parse_request_data`; non-object bodies and non-dict envelopes yield "missing"; manifest keys validated by `valid_manifest_path` before any open |
| V6 Cryptography | yes | No hand-rolled primitive beyond the documented fixed-time compare over `hashlib.sha256`; never log or return the secret |
| V7 Error handling and logging | yes | Fixed refusal texts; reason clamped; gate fails closed and never raises; no logging of request bodies |
| V14 Configuration / deployment | yes | Atomic staged publish, `ext-previous` rollback, secret byte-equality gate, manifest written last |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthenticated mutation from a LAN caller (pyRevit RoutesServer may bind beyond loopback) | Elevation of Privilege / Tampering | Secret gate on 34 routes; `bind` reported on `/status/`; forced loopback deferred (D-16) |
| Secret echoed in an error body, traceback or log | Information Disclosure | Strip `_mcp` from `request.data` first; refusal bodies fixed; pyRevit logs no request body (read `server.py`/`router.py` in the dev clone: only a route-parameter cast debug line) and `handler.py` builds tracebacks with `traceback.format_tb` (no locals) |
| Timing side channel on compare | Information Disclosure | Existing digest XOR compare, length-equalized |
| Forged envelope by the model (pre-seeded `_mcp` in tool arguments) | Spoofing | `with_envelope` refuses a body that already has `_mcp` |
| Tampered extension file (drift) | Tampering | Load-time manifest check, 423 on mismatch; scope limits stay documented: drift check, not tamper defence, since anyone who can write the share can rewrite `_manifest.json` (03-REVIEW IN-03) |
| Dropped share read as tampering | Denial of Service (self-inflicted) | Three-state model with ENOENT corroboration (WR-01) |
| Half-published extension loaded by a Revit starting mid-publish | Denial of Service | Staged build and swap (D-10) |
| Stale secret copy left in `ext-previous\` after rotation | Information Disclosure | Rotation procedure clears `ext-previous\` |
| `/execute_code/` reads `_bridge_secret` or module state once authenticated | Elevation of Privilege | Accepted: documented as "network barrier, not protection from anyone who can run code or read the share" (CLAUDE.md) |
| pyRevit core `POST /sessions/` reload route | Denial of Service | Outside our gate; documented residual |
| Secret fingerprint on the open `/status/` | Information Disclosure | 8 hex of SHA-256 of a 256-bit random value; D-08 locked; see A8 |

## Sources

### Primary (HIGH confidence) - read this session
- `revit_mcp/trust.py` (whole file), `revit_mcp/integrity.py` (whole file), `revit_mcp/status.py`, `revit_mcp/registry.py`, `revit_mcp/textutils.py`, `revit_mcp/identity.py` lines 1-120 and 500-706, `startup.py`
- `bridge.py` lines 472-562, 734-1149; `tools/status_tools.py`; `tools/utils.py` `format_response`/`_project_response`
- `deploy/publish-extension.cmd`, `deploy/make_manifest.py`, `deploy/secret_tool.py` (first 110 lines), `deploy/config.cmd`, `deploy/README.md` (Layout, Rollback), `deploy/RELEASE-RUNBOOK.md` (sections 2, 8, 9)
- `tests/unit/test_phase2_inventory.py`, `tests/unit/inventory_support.py`, `tests/unit/test_secret_gate_e2e.py`, `tests/unit/test_bridge_secret_client.py` (inert pins), `tests/unit/test_secret_pipeline.py` (publish order and smoke), `tests/unit/test_registration.py`, `tests/unit/conftest.py`, route-suite helpers, `tests/test_phase4_live_outcomes.py` header and structure, `tests/test_phase2_preflight.py` listener snippet
- `scripts/conventions.py`, `scripts/new_tool.py`
- `.planning/phases/05-*/05-CONTEXT.md`, `05-DISCUSSION-LOG.md`; `03-CONTEXT.md`, `03-REVIEW.md`, `03-VERIFICATION.md`; `REQUIREMENTS.md`, `ROADMAP.md` Phase 5, `RELEASES.md`, `STATE.md`
- Local pyRevit clone: `pyrevitlib/pyrevit/routes/server/{base,server,handler,router}.py`, `userconfig.py` routes host/port, `extensions/pyRevitCore.extension/lib/pyrevitcore_api.py`; `%APPDATA%\pyRevit\pyRevit_config.ini` `[routes]`
- Local experiments this session: full unit suite (5218 passed, 3 skipped); NTFS directory-rename-with-open-child probe (failed, WinError 5); AST request-body-use scan of `revit_mcp/*.py`; route counts from `route_inventory()`; `git check-ignore`

### Secondary (MEDIUM/LOW confidence)
- WebSearch on SMB directory rename with open handles: TrueNAS community thread "samba share directory cant rename" (anecdote), Microsoft MS-FSCC file rename information (https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fscc/1d2673a8-8fb9-4868-920a-775ccaa30cf8) - rename requires delete access and sharing; no source tying the failure to SMB specifically (LOW)

### Tertiary (LOW confidence)
- Fleet pyRevit behaviour inferred from the dev clone (A3, A5)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - nothing new; every component already in repo and used live in earlier phases
- Architecture: HIGH for the gate/strip/initialize design and the test strategy (derived from read code and existing test patterns); MEDIUM for pyRevit-internal assumptions (A2, A3)
- Pitfalls: HIGH for test-suite and tooling collisions (read and measured); MEDIUM-LOW for SMB swap behaviour (A1)

**Research date:** 2026-10-24
**Valid until:** 2026-11-24 for in-repo facts (re-run the route inventory if routes change); re-verify pyRevit-dependent assumptions on the fleet build before the R3 pilot
