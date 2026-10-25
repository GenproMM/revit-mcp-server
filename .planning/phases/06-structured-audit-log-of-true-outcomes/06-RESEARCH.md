# Phase 6: Structured audit log of true outcomes - Research

**Researched:** 2026-10-25
**Domain:** CPython-side audit writer (stdlib `logging` + JSONL), FastMCP tool wrapping, bridge provenance consumption, Windows file semantics
**Confidence:** HIGH (every load-bearing claim below was either read in this session's source files or reproduced by a throwaway experiment on this machine; the few `[ASSUMED]` items are listed in the Assumptions Log)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Источник записи и место записи
- **D-01:** Журнал пишет **сторона CPython**, один писатель на процесс сервера. Источник исхода —
  результат `revit_get` / `revit_post` / `revit_image`, уже помеченный фазой 2 атрибутом
  provenance (`revit_provenance`: `kind` ∈ `received` | `not-sent` | `unknown` | `no-reply`,
  `requested`, `process` {pid, actual_port, session_token, revit_version}, `http_status`,
  `corroborated`), и тело ответа: блок `outcome` из `finalize_outcome` (фаза 4), `status`,
  `document`, `documents_changed`, `observed_active_document`, `document_scope`. Тело ответа не-200
  достаётся из текста `Error: NNN - {json}` тем же способом, что `bridge._reply_body`. Журнал
  **никогда** не выводит успех эвристикой `format_response`. Это заменяет старый D-01 («сырой
  httpx-ответ в `_revit_call`»): provenance уже несёт всё нужное. Точка подключения (обёртка
  публичных callables моста или отдельный модуль, вызываемый из них) — на усмотрение планировщика.
  — **Reversibility:** costly — перенос записи на сторону Revit потребовал бы файла на процесс
  Revit, правки `revit_mcp/`, релиза расширения и переделки корреляции.

### Что попадает в журнал
- **D-02:** Пишется **каждый отправленный вызов Revit, инициированный инструментом**: GET и POST,
  чтения и запись, включая 7 открытых POST-чтений (`trust.OPEN_POST_READ_ROUTES`),
  `revit_image` и явный вызов инструмента `get_revit_status`. **Не пишутся:**
  (a) служебные вызовы моста — рукопожатие `GET /status/` перед каждой отправкой
  (`_verify_target` / `_handshake`) и пробы портов discovery (`_probe_port`);
  (b) вызовы с `kind = not-sent` — отказ по слушателям, неоднозначная цель, занятая очередь,
  ошибка соединения до отправки, отказ конверта. Пишутся `unknown` и `no-reply` (отправлено,
  полного ответа нет). Инструменты, которые вообще не обращаются к мосту (`process_tools`,
  отказы валидации на стороне CPython), записей не дают. Это заменяет старый D-02 («все POST,
  включая `not_sent`»).
- **D-03:** Каждая запись несёт `mutation: true|false`. Чтение — это GET или POST к маршруту из
  списка открытых POST-чтений; всё остальное, включая `/execute_code/`, — мутация. Мост не может
  импортировать `revit_mcp/trust.py` (в payload нет `revit_mcp/`), поэтому держит свою копию
  списка, а unit-тест закрепляет её равенство `trust.OPEN_POST_READ_ROUTES` (тот же приём, что для
  `ENVELOPE_KEY`).
- **D-04:** `/execute_code/` пишется с текстом кода до ~8 КБ, полной длиной и SHA-256 всего кода,
  `document_scope` из ответа и исходом. Документ ему **не** приписывается как изменённый (фаза 2,
  D-15); модель назначения пишется как адресованная (см. D-09), не как изменённая.

### Корреляция вызова инструмента
- **D-05:** `call_id` (uuid4) — один на вызов инструмента (AUDIT-04). Задаётся без правки 59
  функций: при регистрации `mcp.tool` оборачивается так, что вызов инструмента ставит
  `contextvars`-значение (имя инструмента, `call_id`, аргументы, `user_request`), а мост его
  читает. Все обращения к Revit одного вызова получают один `call_id`. Нет контекста → свой
  `call_id` на запрос, `tool: null`. **Исследовательский флаг:** интроспекция FastMCP
  (`func_metadata` / `inspect.signature`) через обёртку с `functools.wraps` / `__wrapped__` — схема
  параметров не должна сломаться; та же обёртка добавляет параметр из D-12. (`ctx` передаётся в
  40 из 41 вызовов `revit_post`, но обёртка нужна в любом случае — ради аргументов и
  `user_request`.)
- **D-06:** `call_id` кладётся в конверт `_mcp.call_id` каждого POST. Текущее расширение читает
  из конверта только секрет и лишние ключи игнорирует (`revit_mcp/trust.py:131-140`; подтвердить
  unit-тестом), поэтому **`revit_mcp/` в этой фазе не меняется**: без нового манифеста, релиза
  расширения и перезапуска Revit. У GET тела нет, поэтому `call_id` туда не уходит. Запись
  `call_id` в лог pyRevit отложена.
- **D-07:** Ответ инструмента показывает короткую строку `Audit: call_id <id>` **только у
  мутаций и у ошибок** (любой исход, кроме успеха, в том числе отказы 4xx/5xx и
  unknown/no-reply). У успешных чтений строки нет — экономия токенов. Рендерит её
  `format_response`. Как `call_id` попадает туда (provenance-атрибут или contextvar), решает
  планировщик.

### Схема записи (schema 1)
- **D-08:** Поля: `ts` (UTC ISO, мс), `schema: 1`, `call_id`, `tool`, `route`, `method`,
  `mutation`, `kind` (provenance), `http_status`, `outcome`, `transaction_status`, `requested`,
  `succeeded`, `failed` (`[{item, reason}]`), `revit_failures`, `process` (`pid`, `port`,
  `session_token`, `revit_version`), `corroborated`, `document` (D-09), `windows_user` (D-10),
  `args` (D-11), `user_request` / `user_request_missing` / `user_request_length` (D-12),
  `duration_ms`. Сопоставление исходов: `outcome.status` или `status` тела → `success` | `partial`
  | `failed` | `rolled_back`; HTTP 401 → `rejected_auth`, 423 → `rejected_integrity`, 412/404 по
  документу → `rejected_document`, прочие 4xx/5xx → `error`; `kind = unknown` → `unknown`,
  `no-reply` → `no_reply`. Ответ мутирующего маршрута без блока `outcome` пишется с исходом из
  `status` и флагом `outcome_block_missing: true` — регрессия видна, а не маскируется (старый
  D-06 сохраняется). — **Reversibility:** costly — схему будет читать инструмент статистики;
  поле `schema` заложено для эволюции.

### Модель, «кто», содержимое запроса и персональные данные
- **D-09:** Модель назначения пишется для **каждой** операции: `token` (doc1…), `title` и
  **полный путь**. Для workshared-модели — путь к центральной модели, если ответ его содержит
  (локальная копия — отдельным полем); если в ответах центрального пути нет, фаза его не добывает
  (это правка `revit_mcp/`) — пишется то, что есть, и это отмечается. Приоритет источника:
  `document` из ответа маршрута → `documents_changed` → селектор документа из аргументов →
  нет. Поле `document_source` называет источник; у `execute_code` — роль «addressed», не
  «changed». Если GET-чтение документ не сообщает, исследователь проверяет, годится ли title
  активного документа из рукопожатия `/status/` как помеченный запасной вариант. Это решение
  пользователя заменяет хеш пути (старый D-05) и рекомендацию Pitfall 13 о путях.
- **D-10:** «Кто» — **только пользователь Windows** процесса сервера (`windows_user`,
  `DOMAIN\user`). Имя компьютера, клиент MCP и id сессии не пишутся (рассмотрены, не выбраны).
- **D-11:** «Запрос» — это **аргументы инструмента целиком**, кроме `ctx`; `user_request` хранится
  отдельно. Лимиты: строковое значение ~500 символов с сохранением исходной длины, код
  `execute_code` ~8 КБ (D-04), длинные списки (id) — первые N элементов плюс общее число.
  **Запрошенные новые значения параметров пишутся** — это заменяет старый D-07 и отложенный пункт
  о значениях. Тело HTTP-запроса и данные ответа (результаты чтений) не пишутся.
- **D-12:** **Запрос пользователя.** Регистрационная обёртка добавляет во **все** инструменты
  необязательный параметр `user_request`. Его описание для модели: скопировать последнее сообщение
  пользователя дословно; если это краткое подтверждение («да», «согласую», «делай», «ок»…) —
  скопировать последний содержательный запрос перед ним. Сервер промпта не видит, поэтому запись
  помечает источник как сообщённый ассистентом (`user_request_source: "assistant"`, без
  проверки). Не передан → вызов выполняется, `user_request: null`, `user_request_missing: true`;
  отказа нет. Текст дословный, до ~2000 символов, с сохранением исходной длины и редакцией
  значения секрета. — **Reversibility:** costly — меняет опубликованную входную схему всех 59
  инструментов, которую видят Hermes и Claude Code; конвенция «в `Args:` названы все параметры»
  (`scripts/conventions.py check_tools`, `tests/unit/test_conventions.py`) должна признать
  внедрённый параметр. **Исследовательский флаг:** как FastMCP принимает параметр, добавленный
  обёрткой, без правки каждой функции, и нужна ли та же инструкция в `instructions` сервера.

### Чего в журнале нет (AUDIT-08)
- **D-13:** Не пишутся никогда: конверт `_mcp`, тело HTTP, данные ответа, значение секрета —
  нигде. Редакция в одной функции-писателе перед сериализацией: удалить ключи аргументов вида
  `secret|token|password|api_key` (но не поля идентичности процесса вроде `session_token`, которые
  не являются секретом) и заменить любое вхождение настроенного значения секрета в любой строке
  записи, включая `user_request` и `args`. Тест критерия 7 ищет значение секрета в файле после
  успешного вызова, отказа 401, пути с исключением и вызова, в аргументы или `user_request`
  которого вставлен секрет, — ноль вхождений.

### Размещение, рост, параллельные процессы
- **D-14:** Каталог — локальный диск: `%LOCALAPPDATA%\RevitMCP\audit\` (переопределение
  `REVIT_MCP_AUDIT_DIR`), вне Windows — `~/.revit-mcp/audit/`. Не сетевая шара, не репозиторий.
- **D-15:** **Отдельный файл на процесс сервера:** `audit-<YYYYMMDD-HHMMSS>-<pid>.jsonl`. Один
  процесс сервера теперь обслуживает несколько экземпляров Revit одновременно (фаза 2, D-01/D-03:
  у каждого экземпляра свой lock, вызовы к разным процессам перекрываются) — единственный
  внутрипроцессный писатель сериализует строки, процесс указан в каждой записи. Два процесса
  сервера (две сессии ассистента) никогда не пишут в один файл (AUDIT-06).
- **D-16:** Рост ограничен с первой записи (AUDIT-07): ротация файла процесса по размеру плюс
  очистка при старте: удалить файлы **старше 180 дней**, затем самые старые, пока каталог не
  станет **≤ 500 МБ**. Оба порога настраиваются переменными окружения. Файл, открытый другим
  живым процессом, удалить не получится — сбой проглатывается, файл пропускается.
- **D-17:** Стек записи — стандартный `logging`: логгер `revit_mcp.audit`, `propagate = False`,
  только файловый обработчик через `QueueHandler`/`QueueListener` (запись не блокирует event
  loop), JSON-форматтер с `ensure_ascii=False`, UTF-8. Никакого `StreamHandler`, ничего в stdout
  (AUDIT-05). Инициализация дешёвая или ленивая — холодный старт под гейтом `deploy/gate.py`
  (< 2,0 с).
- **D-18:** Сбой журнала никогда не ломает вызов инструмента: ошибка проглатывается, одно
  предупреждение в stderr на процесс.

### Проверка
- **D-19:** Unit-тесты (без Revit):
  - построение записи по каждому `kind` и исходу: 200 success/partial, 409 rolled_back,
    422 failed, 401, 423, 412, unknown, no-reply;
  - `not-sent` → записи нет; рукопожатие и пробы discovery → записей нет; GET-чтение → запись
    есть;
  - копия списка открытых чтений равна `trust`;
  - общий `call_id` у инструмента с несколькими запросами; `call_id` в конверте POST;
  - каждый зарегистрированный инструмент имеет `user_request`, исходные параметры целы;
  - обрезка и редакция `user_request` и `args`, grep секрета;
  - очистка каталога по возрасту и объёму;
  - чистота stdout: `main.py` по stdio с включённым журналом, поток протокола разбирается без
    мусора (критерий 4).
- **D-20:** Живая проверка на стенде (её проводит человек; шаги записи однократные):
  намеренный откат и частичный пакетный отказ дают записи с истинным исходом (критерий 2);
  мутации в два экземпляра Revit через один процесс сервера плюс второй процесс сервера —
  файлы целы и не перемешаны (критерий 5). Фаза не правит `revit_mcp/`, поэтому перезапуск Revit
  ради неё не нужен.

### Claude's Discretion

- Точные размеры ротации файла, константы обрезки (~500 / ~2000 / ~8 КБ / N id) в пределах
  выбранного порядка величин.
- Модуль записи: `bridge.py` или отдельный `audit.py` рядом с ним. Во втором случае
  `deploy/build-payload.cmd` должен его копировать (сейчас копируются только `main.py` и
  `bridge.py`), а `deploy/gate.py`, возможно, проверять.
- Где живёт обёртка регистрации: `tools/__init__.py` (`register_tools`) или `main.py`.
- Писать ли размер ответа в байтах для чтений.
- Точная таблица сопоставления HTTP-кодов и исходов сверх D-08.

### Deferred Ideas (OUT OF SCOPE)

- Инструмент статистики и поиска по журналу (MCP-инструмент или внешний скрипт).
- Централизованный сбор журналов со станций.
- Значения параметров «до/после» — нужно, чтобы маршруты читали и возвращали старое значение (правка `revit_mcp/`, релиз расширения).
- Запись `call_id` в лог pyRevit на стороне Revit (конверт уже несёт его, D-06).
- Путь к центральной модели, если ответы маршрутов его не несут (правка `revit_mcp/`).

</deferred>
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (REQUIREMENTS.md:76-83) | Research Support |
|----|-------------------------------------|------------------|
| AUDIT-01 | Каждая мутация записывается в локальный структурный журнал JSONL | Hook at the bridge `_dispatch` boundary + gated `_status_call` (see "Hook seams"); JSONL via `QueueHandler` -> roll-forward file handler; D-02 widens this to all sent calls |
| AUDIT-02 | Запись содержит время, инструмент, маршрут, идентичность документа, затронутые элементы и исход | Entry schema + document-source priority + `outcome.succeeded/failed` lists (see "Entry construction"); `tool` comes from the contextvar set by the registration wrapper |
| AUDIT-03 | Записывается фактический исход, а не намерение | Outcome mapping table keyed on provenance `kind`, HTTP status and the reply body's top-level `status` (NOT `outcome.status`, which does not exist); no `format_response` heuristics |
| AUDIT-04 | Один вызов инструмента связывается со своими записями общим идентификатором | `contextvars` `CallState` set by an `mcp.tool` wrapper installed in `main.py`; `call_id` also rides `_mcp.call_id`; today no tool makes >1 bridge call, so the shared-id proof is a synthetic-tool unit test |
| AUDIT-05 | Журнал не ломает stdio-транспорт — ничего не пишется в stdout | Only a file handler behind a queue; static AST test + a subprocess stdio test against an in-process fake Revit (harness verified to work) |
| AUDIT-06 | Журнал не повреждается при двух одновременно работающих экземплярах Revit | One writer thread per server process, file per process (D-15); concurrency unit test with two fake incarnations; live two-Revit step is human-run |
| AUDIT-07 | Рост журнала ограничен | Roll-forward segments (size cap from first write) + start-up age/size prune; `RotatingFileHandler` rejected on evidence (drops records while a reader holds the file) |
| AUDIT-08 | Журнал не содержит секрета и не содержит лишних персональных данных | Single redaction function: key-name scrub + value replacement (raw and JSON-escaped), redact-before-truncate, final pass over the serialized line; grep test over four scenarios |
</phase_requirements>

## Summary

The phase is almost entirely CPython-side and needs **no new packages** (stdlib only; `pydantic` is already an `mcp` dependency and is imported lazily). The bridge already tags every result with provenance, so the writer can be a pure function from `(call context, method, route, provenance, parsed reply body, timing)` to one JSON line. All the ingredients CONTEXT.md assumes exist and were confirmed: the `kind` set, the `outcome` block, `document` descriptors, `process_identity`, the open-read list, and the envelope tolerance on the Revit side. `revit_mcp/` does not change.

Six findings change how the plan must be structured (details in "Common Pitfalls"): (1) wrapping tools inside `tools.register_tools` would break `tests/unit/test_phase2_inventory.py` (it asserts `names[-1] == "ctx"` on the registered callables), so the wrapper must be installed from `main.py` on the `mcp` object instead; (2) a user message that is valid JSON (`{"a":1}`, `[1,2]`) makes FastMCP's `pre_parse_json` turn `user_request` into a list/dict and the call fails validation - reproduced; fix with a `BeforeValidator`; (3) stdlib `RotatingFileHandler` **drops audit records on Windows while any reader holds the file** (WinError 32 on rename) - reproduced; use a small roll-forward `BaseRotatingHandler` subclass that never renames; (4) `revit_image` success results carry no provenance (`_tag` ignores non-text), and `get_revit_process_status`/`start_revit` call `/status/` through the bridge internally, so both need explicit handling to satisfy D-02; (5) `outcome` has exactly five keys and no `status` - the label comes from the reply's top-level `status`; `/activate_document/` is the only mutating route with no `outcome` block; (6) no existing tool performs more than one bridge call, so success criterion 3 cannot be shown live - prove it with a synthetic multi-call tool and say so.

An in-process fake Revit (an `http.server` thread whose identity PID is the test process's own PID) passes the real bridge's netstat ownership check and handshake on this machine, so rollback/partial/401/423/unknown entries, concurrency and the stdio-cleanliness criterion can all be exercised automatically through the production bridge path with real sockets. Only the real-Revit rollback trigger and the two-Revit run stay human-run (D-20).

**Primary recommendation:** Add one stdlib-only root module `audit.py` (pure entry builder + redaction + lazy queue-backed roll-forward JSONL writer + `install_audited_tools(mcp)`), hook it at `bridge._dispatch` and the `/status/` branch, install the tool wrapper from `main.py`, copy `audit.py` in `build-payload.cmd`, and test with the existing fake-Machine pattern plus an in-process fake-Revit HTTP server.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Capture tool name, args, user_request, call_id | MCP server (tool registration wrapper, `audit.py`) | - | Only the CPython side sees tool arguments; Revit sees HTTP bodies only |
| Decide outcome label / classify mutation | MCP server (`audit.build_entry`) | Revit routes (supply `status`, `outcome`, `error_code`) | D-01: provenance + reply body, never `format_response` heuristics |
| Correlation id to Revit | MCP server bridge (`_mcp.call_id` in envelope) | Revit extension (ignores it, D-06) | No `revit_mcp/` change in this phase |
| Durable write, rotation, retention | MCP server process (one writer thread) | OS filesystem (`%LOCALAPPDATA%\RevitMCP\audit`) | D-15/D-17; per-process file avoids cross-process locking |
| Secret redaction | MCP server (`audit.py`, single function) | - | The secret lives in `bridge._secret()`; Revit side never logs |
| "Audit: call_id" display | `tools/utils.py format_response` | bridge (puts id in provenance meta) | D-07 |
| Live truth checks (rollback, two-Revit) | Human on bench | Offline fake Revit for everything else | D-20 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `logging` + `logging.handlers.QueueHandler/QueueListener/BaseRotatingHandler` | stdlib (dev .venv Python 3.13.7 [VERIFIED: ran `.venv/Scripts/python.exe --version`]; payload runs pyRevit's CPython >=3.11) | Off-event-loop JSONL file writer | D-17; stdlib, no dependency |
| `contextvars`, `uuid`, `hashlib`, `datetime`, `queue`, `atexit`, `getpass`, `os` | stdlib | `call_id` scope, uuid4 ids, SHA-256 of code, UTC `ts`, bounded queue, flush at exit, Windows user | Nothing external needed |
| `pydantic` (`Field`, `BeforeValidator`) | 2.11.4 already installed via `mcp` [VERIFIED: `.venv/Lib/site-packages/pydantic-2.11.4.dist-info`] | Declare the injected `user_request` parameter | Already a transitive dependency; import it lazily inside `install_audited_tools` so `import bridge` stays free of `mcp` |
| `mcp` | 1.9.0 [VERIFIED: uv.lock `name = "mcp"` / `version = "1.9.0"`; `.venv` dist-info `mcp-1.9.0`] | `FastMCP.tool`, `Tool.from_function`, `func_metadata` | Existing server |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `http.server.ThreadingHTTPServer` | stdlib | In-process fake Revit for tests | Unit tests of the real bridge path and the stdio test |
| `pytest` | 9.1.1 [VERIFIED: `.venv` dist-info] | Test runner | Existing suite |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Roll-forward segment handler | `RotatingFileHandler` | Rejected: on Windows a reader holding the active file makes `os.rename` fail and every record is dropped until the reader lets go (reproduced below) |
| `QueueHandler`+`QueueListener` | direct `FileHandler` with `asyncio.to_thread` | D-17 chose the queue; keep it, with a **bounded** `queue.Queue` so a stalled disk drops (and warns once) instead of growing memory |
| Wrapper in `register_tools` | Wrapper in `main.py` on the `mcp` object | `register_tools` placement breaks `test_phase2_inventory` (see Pitfall 1) |

**Installation:** none. `uv sync --group dev` already provides everything.

**Version verification:** no packages are added. `mcp 1.9.0` and `pydantic 2.11.4` were read from the installed dist-info directories; `uv.lock` pins `mcp` at 1.9.0.

## Package Legitimacy Audit

No external package is installed by this phase. Only the standard library plus `mcp`/`pydantic`, which are already locked in `uv.lock` and in the payload.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | - | - | - | - | - | Nothing to audit |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
MCP client (Hermes / Claude Code)
   |  tools/call {args..., user_request}
   v
FastMCP (main.py)  -- mcp.tool replaced by audit.install_audited_tools(mcp)
   |  wrapper: pop user_request, build CallState{call_id, tool, args, user_request}
   |  _CALL.set(state)  (contextvar, per request task)
   v
tool function (unchanged, tools/*_tools.py)
   |  await revit_post/revit_get/revit_image(...)
   v
bridge._dispatch  (NEW thin wrapper)           bridge.revit_get("/status/") -> _status_call
   |  t0; progress={"sent":False,...}              |  audit only if tool == "get_revit_status"
   |  result = await <existing _dispatch core>     v
   |     handshake(_verify_target) -- NOT audited  (same hook)
   |     lock, send, _received_reply -> provenance
   |  on CancelledError after send -> record "unknown", re-raise
   v
audit.record_call(call, method, endpoint, provenance, body, duration, ...)   [never raises, D-18]
   |  kind == not-sent  -> return (no entry, D-02b)
   |  build_entry(): outcome mapping, document source, truncation, redaction, one JSON line
   v
logger "revit_mcp.audit" (propagate=False) -> bounded Queue -> QueueListener thread
   -> RollForwardFileHandler -> %LOCALAPPDATA%\RevitMCP\audit\audit-<ts>-<pid>[.NNNN].jsonl
   |
   +-- provenance meta["audit_call_id"] = id  (when entry written and (mutation or outcome != success))
   v
tools/utils.format_response -> "...\nAudit: call_id <id>"
```

### Recommended Project Structure
```
audit.py                      # NEW root module, stdlib-only at import (payload copy line required)
bridge.py                     # hook in _dispatch + /status/ branch; call_id in envelope; tag Image results
main.py                       # audit.install_audited_tools(mcp) before register_tools; FastMCP(instructions=...)
tools/utils.py                # render "Audit: call_id <id>" from provenance meta
tests/unit/audit_support.py   # shared helpers: Machine fake, fake-Revit HTTP server, entry reader
tests/unit/test_audit_*.py    # see Validation Architecture
tests/test_phase6_live_audit.py  # one-shot human-run live gate (pattern of tests/test_phase4_live_outcomes.py)
deploy/build-payload.cmd      # + copy /y "%REPO%\audit.py" "%BUILD%\app\"
```
`revit_mcp/` is untouched. `scripts/conventions.py` needs no change: `check_tools` reads tool *source* ASTs and never sees the injected parameter (the `Args:` rule applies to source functions only) [VERIFIED: scripts/conventions.py:748-800 reads `node.args.args` from source].

### Hook seams (exact)

| Seam | Where | What it knows | Use |
|------|-------|---------------|-----|
| `_dispatch(method, endpoint, ctx, timeout, exchange, target)` | bridge.py:976 | method, endpoint, result (provenance-tagged), plus `progress["sent"]` | The ONE choke point for `revit_get` (non-status), `revit_post`, `revit_image` |
| `/status/` branch of `revit_get` -> `_status_call` | bridge.py:784-788, 735 | selector, result with provenance | Audit only when contextvar tool is `get_revit_status` |
| `revit_post` envelope build | bridge.py:804-819 | `data`, secret | Add `call_id` to `_mcp` |
| `_verify_target` / `_handshake` / `_probe_port` | bridge.py:704, 683, 342 | handshake payload | Never audited (D-02a) |
| `with_envelope(data, secret)` | bridge.py:1085 | - | Extend with an optional `call_id` |

Keep `_dispatch`'s name and signature; add the audit wrapper around its body (rename the current body to e.g. `_dispatch_core`) so nothing that calls `_dispatch` changes. `progress` (currently created inside `_dispatch`) must be created in the wrapper and passed in so the wrapper can see whether the exchange was started. No unit test calls `_dispatch` directly (only docstrings mention it) [VERIFIED: grep of tests/unit].

### Pattern 1: Tool wrapper installed from main.py (verified prototype)
**What:** Replace `mcp.tool` on the instance so every `@mcp.tool()` registered afterwards is wrapped; the wrapper advertises one extra optional parameter through `__signature__` and pops it before calling the real function.
**When to use:** always; install before `register_tools(mcp, ...)`.
**Example (prototype run against the repo's `.venv` mcp 1.9.0 with `tools.clash_tools.register_clash_tools`):**
```python
# Source: experiment exp_wrap.py / exp_wrap2.py (scratchpad), mcp 1.9.0 tools/base.py + utilities/func_metadata.py
import contextvars, functools, inspect, json
from typing import Annotated, Optional

_CALL = contextvars.ContextVar("revit_mcp_audit_call", default=None)

def _json_text(value):
    # FastMCP.pre_parse_json json.loads() any str arg; a user message like '{"a":1}' or '[1,2]'
    # arrives as dict/list and would fail `Optional[str]` validation. Turn it back into text.
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)

def install_audited_tools(mcp):
    from pydantic import BeforeValidator, Field          # lazy: `import bridge` must not import mcp/pydantic
    user_request_type = Annotated[Optional[str], BeforeValidator(_json_text),
                                  Field(description=USER_REQUEST_DESCRIPTION)]
    original_tool = mcp.tool

    def audited_tool(*args, **kwargs):
        register = original_tool(*args, **kwargs)
        def decorator(fn):
            register(_wrap(fn, user_request_type))
            return fn                                     # FastMCP's decorator returns the original
        return decorator
    mcp.tool = audited_tool                               # instance attribute shadows the method

def _wrap(fn, user_request_type):
    signature = inspect.signature(fn)
    if "user_request" in signature.parameters:
        raise ValueError("tool already declares user_request")
    extra = inspect.Parameter("user_request", inspect.Parameter.KEYWORD_ONLY,
                              default=None, annotation=user_request_type)
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        user_request = kwargs.pop("user_request", None)
        state = new_call(fn.__name__, kwargs, user_request)    # drops ctx by name
        token = _CALL.set(state)
        try:
            return await fn(*args, **kwargs)
        finally:
            _CALL.reset(token)
    wrapper.__signature__ = signature.replace(parameters=list(signature.parameters.values()) + [extra])
    return wrapper
```
Observed in the prototype: the published JSON schema gains `user_request` (`anyOf string/null`, `default null`, the description); `ctx` stays out of the schema; the wrapped function receives `ctx` as a kwarg (so `new_call` must drop `ctx` by name and/or by `isinstance(..., Context)` checked lazily); defaults of all original parameters appear in `kwargs` (FastMCP passes the full model dump), so the captured `args` already contains defaults and `None`s - drop `None`-valued entries in the entry to save space (discretion). `KEYWORD_ONLY` appended last is always a valid signature regardless of defaults on the original parameters. [VERIFIED: experiment output]

### Pattern 2: Roll-forward file handler (verified prototype, Python 3.13.7 and 3.14.2)
**What:** A `logging.handlers.BaseRotatingHandler` subclass that, when the active segment would exceed `max_bytes`, closes it and starts the next segment file; it never renames and never deletes a file it does not own.
```python
# Source: experiment exp_seg.py (scratchpad)
class SegmentHandler(logging.handlers.BaseRotatingHandler):
    def __init__(self, directory, stem, max_bytes, keep):
        self.directory, self.stem, self.max_bytes, self.keep, self.seq = directory, stem, max_bytes, keep, 1
        super().__init__(self._segment(1), "a", encoding="utf-8", delay=True)   # no file until first write
    def _segment(self, n):                      # NOT `_name`: logging.Handler owns `self._name`
        return os.path.join(self.directory, self.stem + (".jsonl" if n == 1 else ".%04d.jsonl" % n))
    def _open(self):                            # LF endings, never CRLF; never raise on a lone surrogate
        return open(self.baseFilename, self.mode, encoding="utf-8", errors="backslashreplace", newline="\n")
    def shouldRollover(self, record):
        try: size = os.path.getsize(self.baseFilename)
        except OSError: size = 0
        return size > 0 and size + len(record.getMessage().encode("utf-8")) + 1 > self.max_bytes
    def doRollover(self):
        if self.stream: self.stream.close(); self.stream = None
        self.seq += 1
        self.baseFilename = os.path.abspath(self._segment(self.seq))
        old = self.seq - self.keep                # prune only OWN oldest segment; a held file simply survives
        if old >= 1:
            try: os.remove(self._segment(old))
            except OSError: pass
```
Behaviour verified: with a reader holding segment 1 open, 14 records produced zero handler errors and segments 3-5 plus the held segment 1 remained; no `\r\n` in any segment; names match `audit-*.jsonl`. Wire it as: `logger("revit_mcp.audit", propagate=False, level=INFO)` -> `QueueHandler(bounded queue.Queue)` -> `QueueListener(queue, SegmentHandler)`; formatter `%(message)s`; `atexit.register(listener.stop)` (registered after `logging` imported, so it runs first). [VERIFIED: experiment]

### Pattern 3: In-process fake Revit through the real bridge (verified)
A `ThreadingHTTPServer` on `127.0.0.1:<free port outside 48884..>` inside the **test process**, whose `/status/` answers `process_identity = {"pid": os.getpid(), "actual_port": PORT, "session_token": <uuid4>, "revit_version": "2024"}`, passes the real `listener_snapshot` (real `netstat.exe`) and the identity handshake, because the LISTENING owner PID is the test process. Address it with an explicit selector built by `bridge._selector_for({...})` (never the default-discovery path, so a real Revit on 48884 cannot interfere). Experiment result: a GET returned `ProvenanceDict` with `kind: received, http_status: 200, corroborated: True`; a POST answered by a canned `409 {"status":"rolled_back", "outcome": {...}}` came back as `ProvenanceText "Error: 409 - {...}"` with `kind: received`. [VERIFIED: experiment exp_fake_revit.py] Windows-only (`listener_snapshot` returns `None` elsewhere); mark such tests `skipif(sys.platform != "win32")`. The unit-suite autouse fixture in `tests/unit/conftest.py` blocks `listener_snapshot` and the HTTP client by default; the fake-Revit tests must restore `bridge._selected_client` to the real factory and pass `run=`/un-guard `listener_snapshot` themselves (see how `tests/unit/test_target_locks.py` saves `REAL_SELECTED_CLIENT`), or run the server side in the subprocess for the stdio test.

### Entry construction (pure function)

`audit.build_entry(...)` must be a pure function (no I/O, no clock reads beyond arguments) so every table row of D-19 is a unit test. Inputs the bridge supplies: `call` (CallState), `method`, `endpoint`, `provenance` (the `revit_provenance` meta dict or None), `body` (via the existing `_reply_body(result)`), `duration_ms`, `sent` flag, `active_title_hint`.

**Provenance meta shape** [VERIFIED: bridge.py:484-486]: `{"kind", "requested", "process", "http_status", "corroborated"}`; kinds named at bridge.py:454-460: `"received"`, `"not-sent"`, `"unknown"`, `"no-reply"`, `"unverified-reply"` (only produced by `_status_call`). `process` is `{"pid","actual_port","session_token","revit_version"}` (bridge.py:494-497). For `unknown`/`no-reply`/`unverified-reply` there is no `process`; keep `requested` (`{"address","pid"}`) in the entry as `requested_target` so an unknown outcome can still be traced to the Revit that may have applied it.

**Outcome block on the wire** [VERIFIED: revit_mcp/textutils.py:365-371] - exactly these five keys, in this order: `"transaction_status"`, `"requested"`, `"succeeded"`, `"failed"` (each `{"item", "reason"}`), `"revit_failures"`. There is **no `status` inside `outcome`**; the label is the reply's top-level `"status"`. CONTEXT D-08's phrase "`outcome.status` или `status` тела" resolves to: use top-level `status`. `classify_outcome` pairs [VERIFIED: textutils.py:340-346]: not committed -> `("rolled_back", 409)`; `n_failed == 0` -> `("success", 200)`; `n_succeeded > 0` -> `("partial", 200)`; else `("failed", 422)`. On 409 the payload is `{"status","message","transaction_status","failures","outcome"}` (textutils.py:393-402); on 422 it also carries a truthy `"error"` (textutils.py:407-411).

**Outcome mapping the writer must implement (precedence top to bottom):**

| Condition | `outcome` label | Notes |
|-----------|-----------------|-------|
| `kind == "not-sent"` | *no entry* | D-02b |
| `kind == "unknown"` | `unknown` | POST sent, no trustworthy reply (transport error mid-flight, bad JSON, conflicting stamp, cancel) |
| `kind == "no-reply"` | `no_reply` | read without a usable reply |
| `kind == "unverified-reply"` | `unverified_reply` (or `error`) | only `/status/`; D-08 does not name it - add it explicitly |
| `kind == "received"` and HTTP 401 | `rejected_auth` | body keys `error`, `auth` in {`missing`,`mismatch`,`server_not_configured`}, `hint` [VERIFIED: trust.py:260-273]; record `auth` as `reason` |
| HTTP 423 | `rejected_integrity` | body keys `error`, `integrity`, `files` [VERIFIED: trust.py:484-498]; record `integrity` as reason, do not copy the file list |
| body has `error_code` that is one of the document-guard codes (400/404/412/503) | `rejected_document` | codes at identity.py: `document-selector-invalid`, `document-token-stale`, `document-closed`, `document-token-unknown`, `document-selector-required`, `document-not-active`, `no-open-document`, `document-identity-ambiguous`, `document-identity-unavailable`, `document-active-unknown`, `document-registry-unavailable`. Refusal payload keys `error`, `error_code`, `process_identity`/`identity_error`, `candidates`, `active_document` [VERIFIED: identity.py:602-609]. Match on the `document-*`/`no-open-document` code, **not** on bare 404/412/503 (a 404 also means "element not found" on other routes) |
| top-level `status` in {`success`,`partial`,`failed`,`rolled_back`} | that status | with HTTP 200/200/422/409 respectively |
| other 4xx/5xx | `error` | still copy `outcome.transaction_status/succeeded/failed` if the body has an `outcome` block: Phase 4 D-14 says a 500 after `Commit()` carries `transaction_status: "Committed"` and the model DID change |
| 200 and `status` absent on a **read** | `success` | a completed read |
| 200 and `status` absent/unknown on a **mutation** | `unrecognized` + raw `reply_status` | never default to success |
| mutation, no `outcome` block, route not in `ROUTES_WITHOUT_OUTCOME_BLOCK` | add `outcome_block_missing: true` | D-08; the only exempt route is `/activate_document/` (see Pitfall 11) |

All mutating POST routes except `/activate_document/` reference `outcome` in their module [VERIFIED: scan of revit_mcp/*.py by script this session: analysis, clash, documents(3 routes: activate + two open reads), colors `/list_category_parameters/` and worksharing `/model_worksets/` are the open reads; documents.py `/activate_document/` has 0 outcome references]; STATE.md records "/activate_document/ deliberately carries no outcome block (Phase 6 audit reader handles it by route name)" [VERIFIED: .planning/STATE.md line 147].

**`mutation` flag (D-03):** `mutation = not (method == "GET" or route in OPEN_POST_READ_ROUTES)`. The mirrored constant must equal `revit_mcp.trust.OPEN_POST_READ_ROUTES`, which is verbatim [VERIFIED: revit_mcp/trust.py:48-56]:
`"/document_summary/"`, `"/document_levels/"`, `"/model_worksets/"`, `"/material_quantities/"`, `"/clash_check/"`, `"/ai_filter/"`, `"/list_category_parameters/"`. Pin by a unit test importing `revit_mcp.trust` (pure; other tests already do, e.g. tests/unit/test_bridge_secret_client.py). Add a second pin: for every route found by the existing `tests/unit/inventory_support.route_inventory()`, `mutation` computed by the writer equals "gated by the Revit side".

**Route string:** endpoints reaching the bridge include path tails (`/element_properties/{id}`, `/get_view/{view_name}`) and query strings (`params=` is passed separately for GET). Normalise to `"/" + first_path_segment + "/"` (the same `_route_key` idea at bridge.py:888) and keep the tail in a separate optional `route_arg` (truncate to 200 chars) - the element id in the tail is exactly what "find the entry by element id" needs, and a view name can be arbitrary text.

**Document block (D-09):** reply key `document` is a descriptor [VERIFIED: revit_mcp/identity.py:381-387]: `{"document": <token>, "title": ..., "path": ..., "active": ..., "saved": ...}` - the token is stored under the key **`document`**, not `token`; the entry's `document.token` is populated from it. Priority `document` -> `documents_changed` (list of descriptors with `role` project/family and `changed`; family entries have no token and carry `is_family_document`, placement.py:98-117) -> request-argument selector (`args["document"]`, an opaque `doc1.<gen>.<n>` token, title unknown) -> none; `document_source` names which. For `/execute_code/` (reply carries `document_scope`) record `role: "addressed"`/no changed document (Phase 2 D-15). `observed_active_document` (documents.py:154-155) is a separate field, not the changed document.

Central-model path: no code in `revit_mcp/` references `GetWorksharingCentralModelPath` or exposes a central path in descriptors [VERIFIED: grep this session, only unrelated "central" strings in document.py/worksharing.py]; descriptors carry `doc.PathName`. Therefore write what the reply gives and note `central_path: not reported` is not needed as a field; an `open_model` request's `file_path` already lands in `args`.

**Handshake-title fallback (D-09 research flag):** `/status/` answers `document_title` (title only, no token, no path) [VERIFIED: revit_mcp/status.py:104-106]; the handshake payload is currently discarded after `state.identity` is set (bridge.py:729-731). It is usable only as a **labelled hint**: the active document at handshake time under the bridge lock, but the user can switch the active document in the UI between handshake and route execution (the lock does not cover the UI), and Phase 2's rule is that a document is attributed only if the route reports it. Recommendation: if implemented, store `progress["active_title_hint"]` from `_verify_target`, write it as `document: {"title": hint}` with `document_source: "handshake_active_title"` and never fill `token`/`path` from it; otherwise skip it. Default recommendation: implement (cheap) because D-09 invited it; keep it clearly separate from route-reported attribution.

**Affected elements (AUDIT-02):** `outcome.succeeded` (ids or input indexes) and `outcome.failed` (`{item, reason}`). The user wants to find an entry by element id, so cap generously: first 500 ids of `succeeded`, first 100 `failed` entries (matches `_PARTIAL_FAILED_CAP = 100` at tools/utils.py:151) with `succeeded_count`/`failed_count` carrying the true totals. Same cap idea for list-valued `args` (D-11 "first N plus total").

**`args` handling:** capture the post-validation kwargs dict (shallow copy) at call start; at write time: drop `ctx`; drop `None` values; **redact first, truncate second**; string values truncated to ~500 chars with the original length recorded (keep the value a string; add a top-level `args_truncated: [{"arg", "length"}]` so the stats tool sees a stable type); `execute_revit_code.code` up to ~8 KB with `code_length` and `code_sha256` over the full text (D-04). Keys matching `secret|token|password|api_key` (case-insensitive, matched on tool-argument keys and nested dict keys only, never on the writer's own `process.session_token`) are replaced by a marker. `user_request` ~2000 chars with `user_request_length`.

**Entry fields (schema 1, D-08)** plus two recommended additions: `server_pid` (the MCP server process that wrote the line, so concatenated files stay attributable - D-15 says the process is named in every record) and `requested_target` (for non-received kinds). Raw `reply_status` only when unrecognised. `ts`: `datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")`. `windows_user`: `USERDOMAIN\USERNAME` from the environment, falling back to `getpass.getuser()`, then `"unknown"`; compute once, lazily. Serialize with `json.dumps(entry, ensure_ascii=False, separators=(",", ":"), default=<safe type-name fallback, never repr>)`; JSON escaping of control characters is what guarantees one entry per line even for a `user_request` containing newlines.

### Anti-Patterns to Avoid
- **Deriving success from `format_response`:** it is a text projection with its own heuristics (CLAUDE.md "A dict is an error only if ..."); the writer reads provenance + body fields only.
- **`RotatingFileHandler`:** loses records under a Windows reader (Pitfall 3).
- **Importing `mcp` (or pydantic at module level) from `audit.py`/`bridge.py`:** `tests/unit/test_bridge_serialization.py::test_bridge_imports_without_fastmcp` fails and cold start grows.
- **Eager audit init at import:** create the directory, thread, prune and Windows-user lookup lazily on the first entry; the 2.0 s init gate (`deploy/gate.py`, `tests/test_init_latency.py`) must not move.
- **Logging `exc_info`/tracebacks, `repr(exception)` or `str(httpx exception)` into entries:** log type names only; the writer's own failure path writes at most the exception class name to stderr, once per process.
- **Putting the wrapper in `register_tools`:** see Pitfall 1.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Off-loop writing | custom thread + queue protocol | `QueueHandler`/`QueueListener` (bounded `queue.Queue`) | stdlib, tested; override `handleError` on both handlers to drop + warn once |
| Rotation base | own file-switching loop | `BaseRotatingHandler.shouldRollover/doRollover` hooks (roll-forward subclass) | keeps `emit`, locking and `handleError` semantics |
| JSON escaping / one-line guarantee | manual string building | `json.dumps(..., ensure_ascii=False)` | control characters in `user_request` are escaped, no line forging |
| Correlation ids | counters/timestamps | `uuid.uuid4()` | D-05 |
| Per-call context propagation | passing a `call_id` through 59 tool functions | `contextvars.ContextVar` set in the wrapper | tasks spawned inside the call inherit it; concurrent requests are isolated |
| JSON-typed parameter coercion | custom FastMCP subclass | pydantic `BeforeValidator` on the injected parameter | verified fix for the `pre_parse_json` trap |
| Windows user | `os.getlogin()` first | env `USERDOMAIN`/`USERNAME`, then `getpass.getuser()` | `getlogin` can fail without a console session [ASSUMED] |

**Key insight:** the honest-outcome work is already done upstream (Phase 4 blocks, Phase 2 provenance). The risk in this phase is not computing the outcome but (a) losing records, (b) leaking the secret, (c) silently changing the published tool schema, and (d) a writer that can break a tool call. Every "don't hand-roll" item above is about not re-introducing one of those.

## Secret and personal-data handling (AUDIT-08)

Where the secret value can appear on the CPython side: the request body `_mcp.secret` (built by `with_envelope`, bridge.py:1085-1104) - never copied into an entry because bodies are not logged (D-11/D-13); tool `args` and `user_request` if the model or user pasted it; `execute_revit_code.code` (the model could read `revit_mcp/_bridge_secret` through arbitrary code and paste it into a later call); `failed[].reason` and `revit_failures` text from Revit (a route cannot reach the secret - the envelope is stripped before the route parses its body - but `/execute_code/` output could, and a reason string passes through); error strings and exception texts (`_error_text`, bridge.py:933) - not written, only type names; URLs (GET has no body, the secret is never in a URL or query).

The secret's format is `secrets.token_urlsafe(32)` (A-Z a-z 0-9 `_` `-`, 43 chars) [VERIFIED: deploy/secret_tool.py:5-8, 24-27, 40 `_TOKEN = re.compile(r"\A[A-Za-z0-9_-]+\Z")`], but `bridge._secret_from_bytes` accepts any >=16-char text (bridge.py:1113-1133), so redact generically:
1. Walk every string in the entry structure and replace the secret by `[REDACTED]`, then also its JSON-escaped form `json.dumps(secret)[1:-1]` (differs only for secrets containing `"`, `\` or non-ASCII).
2. **Redact before truncate.** Truncating first can leave a long prefix of the secret at the cut; redact the full string, then cut.
3. Final belt-and-braces pass: after `json.dumps`, `.replace()` both forms on the serialized line. The replacement text contains no quote or backslash, so the line stays valid JSON.
4. Key scrub on tool arguments (`secret|token|password|api_key`), keeping the writer's own identity fields (`process.session_token`) out of that filter by construction (they are written by the writer, not passed through `args`).
5. Skip all replacement when no secret is loaded (`None`); the bridge passes `_secret()` at write time (audit.py never imports bridge).
6. Do not log the secret fingerprint either; it is harmless but unneeded noise.
7. Writer failure path: stderr gets `type(exc).__name__` only, once per process (D-18); never the entry.

Personal data is bounded by decision: Windows user, full document path/title (D-09 overrides PITFALLS Pitfall 13 on paths), tool arguments, verbatim user request. The log directory under `%LOCALAPPDATA%` is per-user by default ACL; do not widen it.

## Common Pitfalls

### Pitfall 1: Wrapping inside `register_tools` breaks existing signature tests
**What goes wrong:** `tests/unit/test_phase2_inventory.py::test_tool_signature_matches_its_class` asserts `names[-1] == "ctx"` and `names[-3:] == ["target","document","ctx"]` on `inspect.signature(TOOLS[name])`, where `TOOLS` comes from `inventory_support.register_everything()` which calls `tools.register_tools(FakeMCP(), ...)` [VERIFIED: tests/unit/test_phase2_inventory.py:188-205; inventory_support.py:178-219]. A wrapper installed in `register_tools` adds `user_request` after `ctx` and fails them (and the `test_tool_forwarding_*` suites that read `inspect.signature(tools[name])`).
**How to avoid:** install from `main.py` (`audit.install_audited_tools(mcp)` before `register_tools(mcp, ...)`); `register_tools`' signature (pinned by `scripts/conventions.py CANONICAL_TOOL_REGISTRAR`) and `FakeMCP.tool(self)` (zero-arg) stay untouched. The "every registered tool has `user_request`" test builds a real `FastMCP`, installs the wrapper, calls `register_tools`, and compares schemas with the unwrapped signatures.
**Warning signs:** phase2-inventory or forwarding tests failing on signature order.

### Pitfall 2: A JSON-looking user message breaks the call
**What goes wrong:** `FuncMetadata.pre_parse_json` runs `json.loads` on every `str` argument and replaces it when the result is not `str|int|float` [VERIFIED: .venv/.../func_metadata.py `pre_parse_json`]. `user_request='{"ids": [1,2]}'` or `'[1,2]'` becomes a dict/list and `Optional[str]` validation raises -> the tool call fails. Reproduced: plain annotation errors on those two values; `null`/`42`/Cyrillic text pass.
**How to avoid:** `BeforeValidator(_json_text)` (Pattern 1); reproduced fix passes all five probe values. The text is then `json.dumps`-normalised, not byte-identical - acceptable for a model-reported field, note it.

### Pitfall 3: `RotatingFileHandler` drops audit records on Windows while a reader holds the file
**What goes wrong:** Reproduced on Python 3.14.2: `RotatingFileHandler(maxBytes=200, backupCount=2)`; after opening the active file for reading (a stats tool, an editor), 5 more records produced 4 `PermissionError: [WinError 32]` rotation failures and only 3 lines survived in the file; the failing `emit` writes nothing. A rotation failure loses the record, not just the rotation.
**How to avoid:** roll-forward handler (Pattern 2); never rename. Prune only files this process created, tolerate `OSError`.

### Pitfall 4: `_name` collides with `logging.Handler._name`
**What goes wrong:** a method called `_name` on a `Handler` subclass is shadowed by the `None` attribute set in `Handler.__init__`; the first rollover raises `TypeError: 'NoneType' object is not callable` (hit in the first prototype run). **How to avoid:** call it `_segment`.

### Pitfall 5: `QueueHandler.prepare` stringifies the record
**What goes wrong:** passing a dict as the log message loses structure (`str(dict)`); a custom JSON formatter on the file handler never sees the dict. **How to avoid:** build, redact and serialize the line in the single writer function and log the finished string; file formatter is `%(message)s`.

### Pitfall 6: Windows text mode writes CRLF; lone surrogates raise
**What goes wrong:** `FileHandler` opens in text mode, so `\n` becomes `\r\n` on Windows; `ensure_ascii=False` with `encoding="utf-8"` raises on a lone surrogate. **How to avoid:** `open(..., newline="\n", errors="backslashreplace")` in `_open` (Pattern 2); test asserts no `\r\n` and a surrogate round-trips without a handler error.

### Pitfall 7: `revit_image` success carries no provenance
**What goes wrong:** `_tag` returns non-dict/str values untouched (bridge.py:473-481) and `_received_reply` returns early for them (bridge.py:546-547), so a successful `get_view` image (an `mcp.server.fastmcp.Image`) reaches the hook with no provenance (kind/process/http_status unknown). An `Image` instance accepts attributes [VERIFIED: ran `Image(...)`; setattr works, no `__slots__`].
**How to avoid:** extend `_tag`/`_received_reply` to attach the provenance attribute to such objects too (tools do not run images through `format_response`, so nothing else changes), or special-case image results in the hook as `received/200/success` with no process. Prefer tagging; add a unit test.

### Pitfall 8: Internal `/status/` calls would flood the log and contradict D-02
**What goes wrong:** `tools/process_tools.py:231` calls `revit_get("/status/", ctx, target=entry["selector"], timeout=5.0)` inside `get_revit_process_status` (and `start_revit` polls) [VERIFIED: tools/process_tools.py:231-233, 315]. CONTEXT D-02 says tools that do not touch the bridge produce no entries and only the explicit `get_revit_status` is logged; but these tools DO call the bridge.
**How to avoid:** audit the `/status/` branch only when the contextvar tool name is `get_revit_status`; every other `/status/` call (process tools, live scripts, no context) writes nothing. Record this as the interpretation of D-02.

### Pitfall 9: A cancelled sent POST leaves no record
**What goes wrong:** `_dispatch` catches `Exception` but not `asyncio.CancelledError`; a client that disconnects (or a tool timeout) after the POST was handed to Revit cancels the task, the lock is released, the mutation may still apply, and nothing is logged.
**How to avoid:** in the audit wrapper catch `asyncio.CancelledError`; if `progress["sent"]` is true write an `unknown` entry (flag `cancelled: true`) synchronously (enqueue is non-blocking), then re-raise. Not in CONTEXT; consistent with D-02's "sent, no complete reply -> unknown". Needs `progress` created in the wrapper.

### Pitfall 10: `outcome.status` does not exist
See "Entry construction". A writer that reads `body["outcome"]["status"]` records `null` for every mutation.

### Pitfall 11: `/activate_document/` is a mutation with no `outcome` block
It is POST, gated, not in the open list -> `mutation: true`, and replies `{"status": "success", "activation": "activated"|"already-active", "document": ..., "message": ...}` or `{error, error_code, reason, document, exception?}` with 200/422/500 (revit_mcp/documents.py:225-300). Put it in a named `ROUTES_WITHOUT_OUTCOME_BLOCK = {"/activate_document/"}` so `outcome_block_missing` stays a real regression signal; add a test that every other gated POST route's module references `outcome` (use `inventory_support.route_inventory()`).

### Pitfall 12: A 500 with an `outcome` block is not "just an error"
Phase 4 D-14: an exception after `Commit()` answers 500 with `outcome.transaction_status == "Committed"` and the succeeded items; the model changed. Copy the block's fields whatever the HTTP code; do not blank them because the label is `error`.

### Pitfall 13: `audit.py` missing from the payload
`test_payload_ships_root_modules.py` only inspects `main.py`'s direct imports [VERIFIED: tests/unit/test_payload_ships_root_modules.py:25-37]; `bridge.py` importing `audit` would not be caught, and `deploy/server.py` reports `ImportError` as a CPython-version mismatch. **How to avoid:** add `copy /y "%REPO%\audit.py"  "%BUILD%\app\"` to `deploy/build-payload.cmd` (beside the `bridge.py` line, ~line 99); make the test follow root-module imports transitively (main -> bridge -> audit); import `audit` eagerly at the top of `bridge.py` so `deploy/gate.py` (which spawns the built `server.py`) fails the build if the file is absent. `deploy/warm.py` only imports `tools` and needs no change.

### Pitfall 14: Unit tests writing into the developer's real audit directory
`tests/unit/conftest.py` already neutralises the bridge per test (autouse). Add an autouse fixture that points the audit sink at a null/collecting sink (or `REVIT_MCP_AUDIT_DIR` at `tmp_path`) and resets the module singleton; otherwise every bridge-path test (e.g. `test_phase5_gate_e2e.py`, `test_target_locks.py`) would create files under `%LOCALAPPDATA%\RevitMCP\audit` and, with `Audit: call_id` lines, change exact-text assertions. Do not add a user-facing "audit off" switch to production.

### Pitfall 15: `with_envelope(data, None)` adds no envelope
Pinned by `test_with_envelope_none_secret_adds_no_envelope` [VERIFIED: tests/unit/test_bridge_secret_client.py:234]. Revit's verdict is `missing` either way. Recommendation: add an optional `call_id` parameter to `with_envelope`; put `call_id` into the envelope only when a secret exists (keeps the pinned test); the 401 entry still gets its `call_id` from the contextvar/anonymous state. The Revit parse ignores extra keys: `split_envelope` returns the whole `_mcp` dict and only `SECRET_KEY` is read (`envelope_secret`) [VERIFIED: revit_mcp/trust.py:123-141, 144-150]; confirm with a unit test that a body carrying `_mcp.call_id` still passes the gate (use `tests/unit/gate_support.py`).

### Pitfall 16: Token cost of the injected parameter
`user_request` adds one schema property (with description) to 59 tools in every session's tool list. Keep the property description short and put the full rule (verbatim copy; a bare confirmation like "да/согласую/делай/ок" means the last substantive request before it) in `FastMCP(..., instructions=...)` (supported in 1.9.0: `instructions` parameter at fastmcp/server.py:140). Models then pay the full text once, not 59 times. Output tokens also grow with every call (a 2000-char echo); this is the accepted D-12 cost.

### Pitfall 17: No existing tool spans more than one bridge call
A scan of `tools/*_tools.py` found no tool with more than one `revit_get/revit_post/revit_image` call and none inside a loop [VERIFIED: AST scan this session]. Success criterion 3 therefore cannot be demonstrated live with a real tool. Prove it with a synthetic tool registered through the audited `FastMCP` that issues two `revit_post` calls against the fake Revit, plus a concurrency test (two simultaneous `call_tool` invocations get different `call_id`s, each shared by its own entries). State this limitation in the verification doc.

### Pitfall 18: Revit has never been made to roll back live in this project
Phase 4's live set exercised `success`, `partial` and `failed` (422) only [VERIFIED: tests/test_phase4_live_outcomes.py docstring steps s1-s5; 04-VERIFICATION.md line 62]. Success criterion 2 needs a real `rolled_back` (409). Rolling back is safe to rehearse in a scratch document because nothing is kept. Candidate trigger via `execute_revit_code` (code runs inside the route's transaction with `suppress_warnings`; an error-severity failure at commit makes `_FailureSwallower.PreprocessFailures` return `DB.FailureProcessingResult.ProceedWithRollBack` when `has_error`, revit_mcp/utils.py) is [ASSUMED]: posting an error-severity failure (e.g. `doc.PostFailure(DB.FailureMessage(<error failure id>))`) inside the code. The plan must schedule a rehearsal before the one-shot gate and may fall back to a known constraint-violating parameter write (the unit fixtures use the `"Constraints are not satisfied"` failure text). Write steps in the live gate are one-shot (project memory `phase2_live_acceptance_one_shot`).

## Code Examples

### Fake Revit server (verified harness skeleton)
```python
# Source: experiment exp_fake_revit.py (scratchpad); real bridge, real netstat, one process
IDENT = {"pid": os.getpid(), "actual_port": PORT, "session_token": TOKEN, "revit_version": "2024"}
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    def do_GET(self):
        self._send(200, {"status": "active", "document_title": "T", "process_identity": IDENT}
                   if self.path.endswith("/status/") else {"status": "success", "process_identity": IDENT})
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._send(409, {"status": "rolled_back", "outcome": {...}, "process_identity": IDENT})
sel = bridge._selector_for({"host": "127.0.0.1", "port": PORT, "pid": os.getpid(), "session_token": TOKEN})
reply = await bridge.revit_post("/set_parameter/", {"a": 1}, target=sel)   # ProvenanceText "Error: 409 - {...}"
```
A reply whose own `process_identity` stamp disagrees is discarded by `_received_reply` as `unknown`; a handler that sleeps past the call timeout exercises `unknown`/`no_reply`; a handler that answers 401/423 bodies exercises the gate outcomes; echoing the request body in a failed `reason` exercises redaction of reply text.

### Provenance -> `Audit:` line
Add the key from the hook: `provenance["audit_call_id"] = call_id` when an entry was written and `(mutation or outcome != "success")`; render in `tools/utils.format_response` after the provenance lines for every kind (the per-kind branches in `_provenance_lines` return early, so append it in `format_response`). Recommendation on D-07's "any outcome other than success": a `not-sent` call writes no entry (D-02b), so a "call_id" line would point at nothing - omit it there (open question 2).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Old CONTEXT D-01: raw httpx response inside `_revit_call` | Provenance attribute + parsed reply body | Phase 2 (02-16) | Writer needs no httpx knowledge |
| Old D-02: log all POSTs incl. `not_sent` | Log only sent calls, reads included | CONTEXT 2026-10-25 | Smaller volume, `mutation` flag distinguishes |
| `RotatingFileHandler` | roll-forward segments | this research | No dropped records under Windows readers |

**Deprecated/outdated:** `tools/` registrars calling `mcp.tool()` stay as-is; do not edit the 59 functions.

## Runtime State Inventory

Not a rename/refactor/migration phase - omitted by instruction. (New state created: the per-user directory `%LOCALAPPDATA%\RevitMCP\audit\` - outside `versions\` and `current\`, so `deploy/update.cmd`'s `robocopy /MIR` into `versions\<REMOTE>` never touches it [VERIFIED: deploy/update.cmd:15, 83-85].)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `os.getlogin()` can fail without a console session, so use env/`getpass` first | Don't Hand-Roll | Low: fall-back chain covers either way |
| A2 | `BaseRotatingHandler.emit/shouldRollover/doRollover` and `FileHandler._open/baseFilename` behave on pyRevit's embedded CPython (3.12 per deploy/server.py comment) as on the tested 3.13.7/3.14.2 | Pattern 2 | Medium: run the writer tests on the payload interpreter once (gate machine) |
| A3 | An error-severity failure posted from `execute_revit_code` (e.g. `doc.PostFailure`) yields a real `rolled_back` 409 in live Revit | Pitfall 18 | Medium: live criterion 2 needs a rehearsed trigger; fall back to a constraint-violating parameter write |
| A4 | Each MCP request is handled in its own task so the `ContextVar` set in the wrapper does not leak across concurrent requests (stdio and HTTP) | Pattern 1 | Medium: the synthetic concurrency test (two simultaneous `call_tool`) must pass; if not, key the state by task |
| A5 | Antivirus/indexers open files with share-delete so they cannot block the writer; roll-forward is robust either way | Pitfall 3 | Low |
| A6 | Default sizes: segment 10 MiB, keep newest 10 segments per process, directory cap 500 MB, age 180 days (env-overridable) | Entry/handler | Low: discretion area; needs user confirmation only if disk budgets matter |

## Open Questions

1. **D-02 vs `process_tools`.** CONTEXT says `process_tools` produce no entries, but `get_revit_process_status`/`start_revit` call `/status/` through the bridge.
   - Recommendation: audit `/status/` only for tool `get_revit_status` (Pitfall 8).
2. **D-07 for calls that were never sent.** The `Audit: call_id` line for a `not-sent` error would reference a non-existent entry.
   - Recommendation: show the line only when an entry was written; mention in the plan so the user can overrule.
3. **Handshake title as hint (D-09).** Implement as a labelled `handshake_active_title` hint or skip.
   - Recommendation: implement, clearly separated; costs one `progress` field.
4. **`call_id` in the envelope without a secret.** Keep the pinned "no secret, no envelope" behaviour (Pitfall 15) or always send `{"call_id": ...}`.
   - Recommendation: keep pinned behaviour.
5. **Cancellation entries (Pitfall 9)** are an addition beyond the decisions; recommended, low cost.
6. **Live rollback trigger (A3)** must be rehearsed before the one-shot gate.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (dev) | all tests | yes | `.venv` 3.13.7; system 3.14.2 [VERIFIED: ran `--version`] | - |
| uv | `uv run pytest` | yes | 0.11.1 [VERIFIED: `uv --version`] | `.venv/Scripts/python.exe -m pytest` |
| pytest | unit suite | yes | 9.1.1 [VERIFIED: dist-info] | - |
| `netstat.exe` | fake-Revit tests through the real bridge | yes (Windows) | system | tests are `skipif(not win32)` |
| Free loopback port outside 48884-49011 (e.g. 48990 is inside the probe window; use an explicit selector, so any free port works) | fake Revit | yes | - | pick an ephemeral port |
| Live Revit (one, then two instances) | D-20 live criteria 2 and 5 | human bench | - | none - human-run gate |

Baseline: `uv run pytest tests/unit` -> 5884 passed, 3 skipped in 83 s on the current tree [VERIFIED: ran this session]. **Missing dependencies with no fallback:** none for automated work; live Revit is by design human-run.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (`[tool.pytest.ini_options] testpaths = ["tests/unit"]`) |
| Config file | `pyproject.toml` |
| Quick run command | `uv run pytest tests/unit -x -q -k audit` |
| Full suite command | `uv run pytest tests/unit` (about 83 s today) |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUDIT-01 | Every sent call (GET, POST, image, explicit status) yields one entry; handshake/probes/not-sent yield none | integration (real bridge + `Machine` fake) | `uv run pytest tests/unit/test_audit_bridge_hook.py -x` | Wave 0 |
| AUDIT-01 | `mutation` flag; open-read list mirrors `trust`; every gated route classified | unit | `uv run pytest tests/unit/test_audit_entry.py -x -k mutation` | Wave 0 |
| AUDIT-02 | Schema 1 fields present: ts, tool, route, method, document(+source), succeeded/failed, outcome, process, windows_user, args, user_request | unit | `uv run pytest tests/unit/test_audit_entry.py -x` | Wave 0 |
| AUDIT-03 | Table: 200 success/partial, 409 rolled_back, 422 failed, 401, 423, document refusal, 500-with-outcome, unknown, no_reply, unverified, missing outcome block, `/activate_document/` | unit (pure builder) | `uv run pytest tests/unit/test_audit_entry.py -x -k outcome` | Wave 0 |
| AUDIT-03 | Same outcomes through the real bridge + fake Revit (409/422/200 partial/401/423/timeout/bad JSON/stamp conflict/cancel) | integration | `uv run pytest tests/unit/test_audit_bridge_hook.py -x -k outcome` | Wave 0 |
| AUDIT-03 | Live: real rollback and real partial batch recorded truthfully | live (human, one-shot) | `uv run python tests/test_phase6_live_audit.py run ...` ; classifier unit-tested by `uv run pytest tests/unit/test_phase6_live_audit.py -x` | Wave 0 |
| AUDIT-04 | One synthetic tool, two bridge calls -> one shared `call_id`; two concurrent tool calls -> distinct ids; `_mcp.call_id` in POST bodies; no context -> own id and `tool: null`; gate accepts envelope with `call_id` | integration | `uv run pytest tests/unit/test_audit_correlation.py -x` | Wave 0 |
| AUDIT-04 (D-12) | Every registered tool exposes `user_request`; other parameters/defaults/required flags unchanged; JSON-looking values accepted; missing -> `user_request_missing` | unit (real FastMCP + `register_tools`) | `uv run pytest tests/unit/test_audit_registration.py -x` | Wave 0 |
| AUDIT-05 | `audit.py`/`bridge.py` have no `print`/`sys.stdout`/`StreamHandler`; stdio session with audit active keeps every stdout line valid JSON-RPC | static + subprocess (Windows, fake Revit) | `uv run pytest tests/unit/test_audit_stdio.py -x` | Wave 0 |
| AUDIT-05 | `import bridge` still free of `mcp.server.fastmcp`; cold start gate | existing + script | `uv run pytest tests/unit/test_bridge_serialization.py -k imports` ; `python tests/test_init_latency.py` | exists |
| AUDIT-06 | 100 concurrent calls to two fake incarnations through one writer: every line parses, counts match, each line names the right process; two writer processes -> two distinct files | integration | `uv run pytest tests/unit/test_audit_writer.py -x -k concurrent` | Wave 0 |
| AUDIT-06 | Live: two Revit instances mutated simultaneously via one server plus a second server process | live (human) | `tests/test_phase6_live_audit.py` step set, parsed by the same classifier | Wave 0 |
| AUDIT-07 | Segment never exceeds cap + one entry; segment count bounded; held reader loses no record; start-up prune by age then size; prune skips unreadable/held files | unit | `uv run pytest tests/unit/test_audit_writer.py -x -k "rotate or prune or reader"` | Wave 0 |
| AUDIT-07 | First write is already capped (cap applies from entry 1) | unit | `uv run pytest tests/unit/test_audit_writer.py -x -k first_write` | Wave 0 |
| AUDIT-08 | Secret absent (raw, JSON-escaped, stripped) from file bytes after: successful call, 401, exception/timeout path, secret pasted into args and `user_request` and `code`, secret echoed in a failed `reason`, secret straddling the truncation boundary; writer-failure stderr clean | integration | `uv run pytest tests/unit/test_audit_secret.py -x` | Wave 0 |
| AUDIT-08 | No `_mcp`, body or reply data in entries; key-scrub spares `session_token` | unit | `uv run pytest tests/unit/test_audit_entry.py -x -k redact` | Wave 0 |
| D-18 | Writer failure (unwritable dir, full queue, bad serialization) never changes a tool result; one stderr warning per process | unit | `uv run pytest tests/unit/test_audit_writer.py -x -k never_breaks` | Wave 0 |
| Payload | `audit.py` copied by `build-payload.cmd`; transitive root-module import check | unit | `uv run pytest tests/unit/test_payload_ships_root_modules.py -x` | exists (extend) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit -x -q -k audit`
- **Per wave merge:** `uv run pytest tests/unit`
- **Phase gate:** full suite green, `python tests/test_init_latency.py` < 2.0 s, then the human-run live gate; `/gsd-verify-work` after that

### Wave 0 Gaps
- [ ] `tests/unit/audit_support.py` - `Machine`-style fake (copy the pattern at `tests/unit/test_target_locks.py:48-110`), in-process fake-Revit HTTP server, audit-file reader/validator
- [ ] autouse fixture in `tests/unit/conftest.py` isolating the audit sink/dir and resetting the writer singleton
- [ ] `tests/unit/test_audit_entry.py`, `test_audit_bridge_hook.py`, `test_audit_correlation.py`, `test_audit_registration.py`, `test_audit_writer.py`, `test_audit_secret.py`, `test_audit_stdio.py`
- [ ] extend `tests/unit/test_payload_ships_root_modules.py` (transitive imports) and `deploy/build-payload.cmd` (copy line)
- [ ] `tests/test_phase6_live_audit.py` (standalone, one-shot, no `test_*` functions; pure classifier importable by `tests/unit/test_phase6_live_audit.py`), following `tests/test_phase4_live_outcomes.py`
- [ ] extend `tests/unit/tool_manifest.txt`: **no change** (no tool added)
- Framework install: none

Manual-only (justified): real-Revit rollback and two-Revit simultaneous mutation - they need Revit processes and, for rollback, a real commit veto; everything else is covered offline.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (the shared secret gate is Phase 3/5; this phase only avoids leaking it) | - |
| V3 Session Management | no | - |
| V4 Access Control | partial | per-user directory under `%LOCALAPPDATA%`; no widening of ACLs; no network share (D-14) |
| V5 Input Validation / output encoding | yes | `json.dumps` escaping guarantees one record per line (log-forging via newlines in `user_request`/args is impossible); bounded sizes |
| V6 Cryptography | minimal | SHA-256 via `hashlib` for `code_sha256`; never hand-roll |
| V7 Error Handling and Logging | yes | no secrets or tracebacks in the log; failure to log never breaks the call; no stdout |
| V8 Data Protection | yes | redaction single point, retention (180 d / 500 MB), documented personal data (Windows user, paths, prompts) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret leaked into the log via args/prompt/code/reply text | Information disclosure | Value replacement (raw + JSON-escaped) before truncation, final pass on the serialized line, key scrub, grep test over 4+ scenarios |
| Log forging via newline/quote injection in `user_request` | Tampering | JSON string escaping; one `json.dumps` per entry; never string-format JSON |
| Writer exception text leaking entry contents to stderr | Information disclosure | Exception class name only, once per process |
| Audit dropped when a reader/AV holds the file | Repudiation | Roll-forward handler (no rename), bounded queue with one warning |
| Unbounded growth / disk fill | Denial of service | Segment cap from first write, per-process segment limit, start-up age/size prune, bounded queue |
| Model supplies a false `user_request` | Spoofing | Recorded as `user_request_source: "assistant"` unverified (D-12); never presented as proof |
| Entry attributes a change to the wrong Revit/document | Repudiation | Process only from provenance `received`; document only from the reply (D-09); hint clearly labelled |
| Another server process writes the same file | Tampering | File name carries timestamp and PID; no cross-process shared file (D-15) |

## Sources

### Primary (HIGH confidence)
- Repository files read this session: `bridge.py` (full), `main.py`, `tools/__init__.py`, `tools/utils.py`, `tools/status_tools.py`, `tools/target_tools.py`, `tools/code_execution_tools.py`, `tools/process_tools.py` (partial), `revit_mcp/textutils.py:300-443`, `revit_mcp/identity.py:340-707`, `revit_mcp/trust.py` (secret/envelope/open-read/auth/integrity parts), `revit_mcp/security.py:100-152`, `revit_mcp/documents.py:195-300`, `revit_mcp/placement.py:90-130`, `revit_mcp/status.py:60-140`, `revit_mcp/utils.py:30-200`, `scripts/conventions.py:700-833`, `deploy/build-payload.cmd`, `deploy/gate.py`, `deploy/update.cmd`, `deploy/secret_tool.py`, `tests/unit/conftest.py`, `test_registration.py`, `test_target_locks.py`, `inventory_support.py`, `test_phase2_inventory.py`, `test_tool_forwarding_model.py`, `test_payload_ships_root_modules.py`, `test_bridge_secret_client.py`, `gate_support.py`.
- Installed library source: `.venv/Lib/site-packages/mcp/server/fastmcp/{tools/base.py, tools/tool_manager.py, utilities/func_metadata.py, server.py}` (mcp 1.9.0).
- Experiments (scratchpad `exp_rot.py`, `exp_seg.py`, `exp_wrap.py`, `exp_wrap2.py`, `exp_fake_revit.py`) run on this machine.
- Full unit suite run: 5884 passed, 3 skipped.

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` Pitfalls 11-13 (partially superseded by CONTEXT D-01/D-09).
- `.planning/phases/04-honest-outcomes-on-every-mutating-route/04-CONTEXT.md` D-03..D-15, 04-VERIFICATION.md.

### Tertiary (LOW confidence)
- Behaviour of the stdlib handler hooks on Python 3.11/3.12 (not run here) - A2.
- Live rollback trigger via `PostFailure` - A3.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - stdlib only; `mcp`/`pydantic` versions read from lock and dist-info
- Architecture / seams: HIGH - every seam was read in the source; the wrapper, handler and fake-Revit harness were prototyped and run
- Pitfalls: HIGH - items 1-4, 6-8, 10-11, 13-15, 17 verified by reading or running; 9, 12, 16, 18 are reasoned from code (18 partly assumed)

**Research date:** 2026-10-25
**Valid until:** 2026-11-25 (stable stdlib/mcp 1.9.0 pin; re-check if `uv.lock` bumps `mcp`)
