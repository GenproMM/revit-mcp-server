# Phase 2: Live identity, ambiguity refusal, and multi-document addressing — Research

**Researched:** 2026-10-14
**Domain:** адресация нескольких локальных процессов Revit, достоверная атрибуция ответа, безопасное обращение к документам одного сеанса
**Confidence:** MEDIUM — границы CPython-половины и контракты фазы подтверждены чтением кода репозитория; семантика pyRevit injection/ExternalEvent, активация уже открытого документа и безопасность чтений неактивного `Document` не подтверждены и вынесены в обязательные decision gates.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Selecting the Revit process
- **D-01:** Keep one shared MCP entry named `revit`; no user-visible duplicate entries per Revit instance. Give the assistant a way to list available processes with port and identity, then pass an exact process selector with subsequent calls. Selection is **per call**, not mutable shared session state. — **Reversibility:** costly — changing the call contract later touches tool signatures, client guidance and tests.
- **D-02:** If exactly one usable Revit process is available, a call without a process selector may use it. If several are available, the call refuses with the candidate list; never choose the latest, the active-looking process or the default port silently. A selected process that restarts must be selected again from a fresh list rather than being treated as the old target. A selector must therefore distinguish a new process incarnation from a reused port/PID; its concrete representation is for research and planning.
- **D-03:** Calls routed to different Revit targets have separate serialization locks; calls to one target share its lock across documents. Preserve the Phase 1 rule: only GET `/status/` is unlocked. This process-local queue does **not** solve cross-session/curl overlap or the pyRevit handler cross-wiring documented in Phase 1; backlog 999.1 remains open.
- **D-04:** If two processes listen on the same selected port, refuse before sending and name both conflicting PIDs. The process-listing path must not suggest either as an unambiguous target. How to enumerate listeners reliably, how to handle discovery failure, and the race between check and send need research; do not promise a stronger safety guarantee than the implementation can establish.

### Process and document identity
- **D-05:** `/status/` exposes PID, Revit version, actual port and a session token issued once per process start. A mutating route's response names the document it actually changed (title and path); resolve identity at request time, including after API activation and a manual UI switch, not from a cached document. Two unsaved documents both titled `Project1` in different processes must be distinguishable by response fields alone.
- **D-06:** Identity must reach the assistant in the *tool's rendered result*, not merely a nested field discarded by success formatting. Both successful and failed responses must make the selected/answering target intelligible where a response was actually received. Do not label a timed-out or unsent request as a verified response from that document; retain Phase 1's honest not-sent/outcome-unknown distinction.
- **D-07:** The live `param-write-rolls-back` reproduction is repeated with visible identity, and the observed result is recorded as confirming or ruling out the specific “wrong process answered” hypothesis (AMBIG-04). Do not infer the result from the earlier Phase 1 UAT pass or invent port/PID measurements.

### Documents and user-visible behavior
- **D-08:** List the open documents in the selected process with identities and active status. An explicit document selector must resolve one document only; ambiguous names must refuse with distinguishable candidates. A document closed after listing must produce a named error and **must not** fall back to whatever is now active. The precise stable key and error vocabulary are research/planning choices, subject to these rules.
- **D-09:** A mutating call without a document selector may target the only open eligible document. With several open documents it **refuses and lists them**; the tool's own docstring states this default. Do not infer the user's intended document from the current UI selection when several are open.
- **D-10:** A mutation explicitly addressed to a document that is open but **not active in the UI refuses with HTTP 412**. Do not activate it or retarget the mutation automatically. Use the separate activation action first; a mutation can then be retried with the explicit document. This is the user's direct answer after the interrupted question, not an inferred tool selection.
- **D-11:** Addressed **reads** of inactive documents should leave the Revit UI on the engineer's active document **only for routes proven safe with a nonactive `Document`**. The minimum comparison surface is the model summary and the list of levels for each of two documents. Any other addressed read not demonstrated safe must refuse clearly rather than silently switch the UI or read the active document under the wrong label. Research must test both routes' actual data access, including helpers that still read `revit.doc`/`UIDocument`. If either minimum read cannot be made safe, stop at a decision gate and report the limitation rather than silently relaxing this acceptance criterion.
- **D-12:** An engineer can switch the active document through a separate explicit tool call. Research the safe Revit API behavior for already-open saved and unsaved documents, worksharing dialogs and UI state; do not assume the existing `/open_model/` path already implements this action. Never auto-switch merely to satisfy an addressed read or mutation.

### Research and acceptance guardrails
- **D-13:** Before choosing a shared wrapper in `startup.py`, inspect pyRevit's handler signature inspection, `doc`/`request` injection and `ExternalEvent` dispatch. Preserve those semantics and the existing `text/plain`/`parse_request_data()` contract. Route handlers must continue returning error responses instead of raising. The old D-01..D-05 `security.wrap_api` wiring is **not** carried into this phase as a fixed design.
- **D-14:** Verify process identity, same-port ambiguity, UI stability for the two supported inactive-document reads, explicit activation, document-close races, and both single- and multi-process defaults against a live Revit bench. Full process restart is required after `revit_mcp/` changes; pyRevit Reload alone is unsafe. Unit tests and the existing cold-start gate remain required, but they are not substitutes for these live claims. Record observed results rather than declaring unrun checks passed.

### Claude's Discretion
- Exact process/document selector encoding, key format, discovery mechanism, where common response formatting lives, wrapper structure, and message wording, provided the visible behaviors above hold and security work is not pulled forward from Phases 3/5.
- Whether additional read-only routes are proven safe for nonactive documents after the minimum summary/levels comparison works. Do not classify an unmeasured route as safe by analogy.

### Deferred Ideas (OUT OF SCOPE)
- Live secret gate and file-integrity enforcement from the former Phase 4 `--auto` context D-01..D-05 → Phase 5 (logic built in Phase 3); do not carry their secret-in-`_mcp`, 401 or 423 wiring into Phase 2.
- Mutation of an inactive document without explicit activation → future capability only after Document/UIDocument behavior is proven.
- Cross-session pyRevit handler synchronization → `.planning/ROADMAP.md` backlog 999.1 (d27-c); a per-target lock in this MCP process is not that fix.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IDENT-01 | `/status/` возвращает идентичность процесса Revit — PID, версию Revit, порт и токен сессии, выданный один раз при запуске процесса | Расширить payload `/status/`, который сейчас содержит только `document_title`/`api_name`/`health`; проверить живым запуском после полного перезапуска Revit |
| IDENT-02 | Каждый ответ мутирующего маршрута называет документ, который он изменил (заголовок и путь), а не только результат операции | Единая точка атрибуции на уровне маршрута плюс точка вставки в rendered-строку после `format_response` (уже существует паттерн для MCP target) |
| IDENT-03 | Идентичность документа разрешается на момент запроса, а не берётся из кэша — остаётся корректной после `OpenAndActivateDocument` и при смене активного документа пользователем в UI | Резолв документа внутри исполнения маршрута (в API-контексте), не в CPython и не в selector-кэше |
| IDENT-04 | Два документа с одинаковым заголовком (два `Project1`) различимы по полям ответа | В ответе должно быть не только `title`/`path`, но и идентификатор процесса и отличающий признак открытого документа |
| AMBIG-01 | Наличие двух слушателей на одном порту обнаруживается до отправки запроса | Локальный TCP-listener снапшот на CPython-половине непосредственно перед отправкой выбранного target-а |
| AMBIG-02 | При обнаружении двух слушателей сервер отказывает явной ошибкой вместо обращения к недетерминированно выбранному процессу | Никакого fallback с конфликтного порта; отказ формируется до отправки модельного запроса |
| AMBIG-03 | Инженер видит в сообщении об отказе, какие именно процессы конфликтуют (PID), чтобы закрыть лишний | Снапшот возвращает полный список PID; отказ рендерит их в видимую строку |
| AMBIG-04 | Репродукция `param-write-rolls-back` повторно проверяема при видимой идентичности — гипотеза «отвечал другой процесс» становится подтверждаемой или опровергаемой | Живой прогон с записанными identity до/после, последовательно и с намеренным перекрытием; результат фиксируется как есть |
| MDOC-01 | Инженер может получить список открытых в сессии Revit документов с идентичностью каждого | Новый route, перечисляющий текущий набор документов с признаком активного |
| MDOC-02 | Мутирующий инструмент принимает явный идентификатор документа в вызове | Опциональный параметр `document` перед `ctx` во всех мутирующих инструментах (ограничение `scripts/conventions.py`) |
| MDOC-03 | Мутирующий вызов без явного документа не угадывает молча — поведение по умолчанию явно определено и описано в докстринге инструмента | Единственный eligible-документ — единственный допустимый default; иначе отказ со списком, и докстринг это формулирует |
| MDOC-04 | Инженер может переключить активный документ отдельным инструментом | Новый явный activation-route и инструмент; поведение saved/unsaved/workshared проверяется живым стендом |
| MDOC-05 | Обращение к документу, закрытому после получения списка, даёт понятную ошибку, а не работу не с тем документом | Резолв selector-а против текущего набора открытых документов на каждом запросе; отсутствие fallback на активный документ |
</phase_requirements>

<phase_requirements_roadmap>
### ROADMAP Success Criteria (verbatim, критерии 1–9, которые план обязан закрыть)

> 1. `/status/` returns PID, Revit version, port, and a session token issued once at process start — confirmed live against a running Revit instance.
> 2. A mutating route's response names the document it changed (title and path), re-derived at request time rather than cached — confirmed live across an `OpenAndActivateDocument` call and a manual UI document switch, per the existing defensive re-fetch pattern this codebase already established for the null-document bug.
> 3. Two Revit instances both showing the untitled title `Project1` are distinguishable by response fields alone — confirmed live with the two-Revit-instance test bench.
> 4. Starting a second Revit process bound to the same port as an already-running one produces an explicit, named refusal (not a request silently answered by whichever process the OS happened to pick) that identifies both conflicting PIDs — confirmed live by intentionally creating the two-listener condition.
> 5. With identity now visible in every response, the still-open `param-write-rolls-back` "wrong process answered" hypothesis is re-run live and its outcome (confirmed or ruled out) is recorded.
> 6. An engineer can list every open document in the session with its identity, address a call at one explicitly, and switch which document is active via its own tool call — confirmed live with more than one model open in one session.
> 7. Comparing documents open in one session is possible from one assistant session; whether reading an addressed document may switch the active document in the Revit UI is decided in the Phase 2 discussion.
> 8. A mutating call that omits the document argument follows a documented, explicit default (not a silent guess) stated in the tool's own docstring.
> 9. Addressing a document that was closed after being listed produces a clear, named error rather than the call silently operating on a different, currently-open document.

Ссылка: `.planning/ROADMAP.md:93-101`. Критерий 7 уже закрыт на уровне решения: D-10/D-11/D-12 запрещают переключение UI как побочный эффект чтения или мутации, а `list_levels`/model summary — единственная разрешённая поверхность для неактивного документа. [VERIFIED: .planning/ROADMAP.md:93-101; 02-CONTEXT.md:32-36]
</phase_requirements_roadmap>

## Project Constraints (from CLAUDE.md)

Директивы, обязательные к соблюдению планом (проверяются plan-checker-ом):

- **Two-Runtime Rule.** `main.py`, `bridge.py`, `tools/`, `tests/` — CPython ≥3.11 (dev pin 3.13): `async/await`, f-strings, type hints. `startup.py` и `revit_mcp/` — IronPython 3 на уровне языка Python 3.4: без f-strings, без `async`, без `pathlib`, без современного `typing`; форматирование через `"{}".format(x)`; encoding cookie в строке 1. [VERIFIED: CLAUDE.md:11-44]
- **Relative sibling imports в `revit_mcp/`.** `from .utils import ...`, никогда `from utils import ...`. [VERIFIED: CLAUDE.md:31-44]
- **POST всегда `text/plain; charset=utf-8`** и разбор через `parse_request_data()`; `json.loads(request.data)` запрещён (pyRevit ломает `application/json` под IronPython 3). [VERIFIED: CLAUDE.md:129-140; bridge.py:192-205]
- **Route handlers не бросают исключений** — `try/except` вокруг тела и `routes.make_response(data=..., status=...)`; статусы 400/404/500/503. [VERIFIED: CLAUDE.md:142-144; revit_mcp/placement.py:672-676]
- **Tool-функции всегда возвращают `str` через `format_response(response)`**; результат bridge может быть `dict` или `str`, индексировать нельзя. [VERIFIED: CLAUDE.md:158-161]
- **Никакого `print()` в `main.py`/`bridge.py` под stdio** — ломает protocol stream. [VERIFIED: CLAUDE.md:163-166]
- **Каждая мутация в транзакции, `suppress_warnings(t)` сразу после `t.Start()`**; `Save`/`SaveAs` — вне транзакции. [VERIFIED: CLAUDE.md:108-114]
- **Только GET `/status/` вне очереди.** Каждый остальной вызов, включая чтения, ждёт lock. Расширить `UNLOCKED_GET` можно лишь с живым измерением перекрытия и решением пользователя. [VERIFIED: bridge.py:19-26, 210-240; CLAUDE.md:186-197]
- **Все tool-facing размеры — миллиметры**; конвертация в футы `MM_TO_FEET = 1.0 / 304.8`. [VERIFIED: CLAUDE.md:168-174; revit_mcp/placement.py:651]
- **Добавление capability = 2 файла + манифест**: `revit_mcp/<domain>.py` с `register_<domain>_routes`, `tools/<domain>_tools.py` с `register_<domain>_tools(mcp, revit_get, revit_post, revit_image=None)`, имя инструмента в `tests/unit/tool_manifest.txt`. [VERIFIED: CLAUDE.md:86-106]
- **`revit_mcp` не импортируется под CPython**; новая доменная логика — на CPython-стороне, Revit-половина остаётся тонким поставщиком данных. Общие чистые хелперы — `revit_mcp/textutils.py`. [VERIFIED: CLAUDE.md:66-72]
- **После правки любого файла в `revit_mcp/` нужен полный перезапуск Revit**; Reload может уронить процесс. [VERIFIED: CLAUDE.md:201-204]
- **Два слушателя на одном порту — известная практическая опасность**: pyRevit не ставит exclusive-address flag, запросы уходят случайному процессу; проверка `Get-NetTCPConnection -LocalPort 48884 -State Listen` должна вернуть ровно одну строку. [VERIFIED: CLAUDE.md:222-232]
- **`/execute_code/` — неаутентифицированный произвольный IronPython.** Не расширять; предпочитать типизированный route. [VERIFIED: CLAUDE.md:196-198]

## Additional Hard Constraints Discovered in Source (не входят в CLAUDE.md)

- `scripts/conventions.py` фиксирует каноническую сигнатуру регистратора и правила сигнатур инструментов, и `tests/unit/test_conventions.py` это проверяет:
  - `CANONICAL_TOOL_REGISTRAR = ["mcp", "revit_get", "revit_post", "revit_image"]` — точное совпадение аргументов обязательно; проверить `conventions.py:29` [VERIFIED: scripts/conventions.py:29, 442-448];
  - каждый `@mcp.tool()` обязан быть `async def`, аннотирован `-> str`, иметь `ctx` **последним** параметром и `Args:`-блок, перечисляющий **все** параметры [VERIFIED: scripts/conventions.py:451-503].

  **Следствие для плана:** новые параметры `target` и `document` обязаны идти **перед** `ctx`, а их имена — появиться в `Args:` каждого затронутого докстринга, иначе `test_conventions` падает. Это делает «широкий» прокат контракта проверяемым автоматически.
- `scripts/conventions.py` запрещает в `revit_mcp/` импорты из `PY3_ONLY_MODULES = {"pathlib", "dataclasses", "typing", "asyncio", "enum", "secrets", "statistics", "unittest.mock", "concurrent"}`, f-strings и `async`. [VERIFIED: scripts/conventions.py:31-35, 191-232]

  **Следствие для IDENT-01:** генерация session token на Revit-половине не может использовать `secrets` (и, по духу правила, `uuid` требует отдельной проверки). Механизм токена нужно выбрать из доступного IronPython/.NET арсенала (например, `clr` + `System.Guid`) и подтвердить на живом стенде. Это открытый вопрос OQ-5.
- `tests/unit/test_status_target.py` уже реализует ровно тот приём, который требует D-06: строка target добавляется **после** `format_response`, потому что форматтер сводит dict с ключом `message` к одному сообщению; тест прямо проверяет, что строка выживает и на error-string, и на `message`-payload. [VERIFIED: tests/unit/test_status_target.py:60-86; tools/status_tools.py:39-48]

  **Следствие:** механизм видимости identity в фазе 2 — обобщение уже принятого паттерна, а не новая архитектура. Это резко снижает риск для критериев 1–3.

## Summary

Фазу 2 нужно планировать как **сквозной контракт адресации и атрибуции**, а не как новый маршрут `/status/`. Сегодня `bridge.py` жёстко фиксирует один `BASE_URL`, один `AsyncClient` и один ленивый `asyncio.Lock`, и это осознанное состояние после Фазы 1: комментарий в коде прямо относит «choosing a Revit per call, with one lock per target» к Фазе 2. [VERIFIED: bridge.py:60-66, 107-145] Значит, первый технический пласт — CPython-сторона: обнаружение процессов, валидация точного селектора, предзапросная проверка TCP-слушателей и **per-target** очередь; только после этого имеет смысл менять сигнатуры инструментов.

Второй пласт — Revit-сторона: выдать identity при старте процесса, на каждом запросе заново разрешить актуальный документ и вернуть атрибуцию так, чтобы её было видно в итоговой строке инструмента. Здесь критично, что текущий `/status/` возвращает только `document_title`, `api_name` и `health`, а `get_model_info()` внутри себя читает `revit.doc`, перетирая любой потенциальный инъецированный документ. [VERIFIED: revit_mcp/status.py:60-72; revit_mcp/model_info.py:20-39] Поэтому `/model_info/` **нельзя** объявлять безопасным для неактивного документа «по аналогии»: минимум D-11 должен быть закрыт отдельными узкими маршрутами и живой проверкой.

Главная граница планирования — не обещать больше, чем можно доказать. Гонку «снапшот слушателей → отправка» нельзя устранить на клиенте; две Revit-инстанции действительно могут слушать один порт, и это зафиксировано как известная опасность. [VERIFIED: CLAUDE.md:222-232] Точно так же нельзя заявлять, что per-target lock решает кросс-сессионное перекрытие обработчика pyRevit — это отдельный backlog 999.1. [VERIFIED: bridge.py:8-17; ROADMAP.md:184-190]

**Primary recommendation:** планировать Phase 2 волнами «доказательство pyRevit-границы → target discovery/lock/identity → document registry и два узких safe-read маршрута → прокат контракта на мутации и инструменты → живые приёмочные ворота», не начиная массовое изменение сигнатур до прохождения G1.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Обнаружение локальных Revit-процессов и отказ при коллизии порта | API / Backend (CPython MCP) | OS / TCP | Только MCP-процесс может проверить слушателей **до** HTTP-запроса; Revit не сообщит о конкурирующем слушателе, потому что ОС уже выбрала получателя. [VERIFIED: 02-CONTEXT.md:24-25; CLAUDE.md:222-232] |
| Per-call process selector и очередь, ключом которой служит target | API / Backend (CPython MCP) | — | Селектор — часть схемы MCP-инструмента; lock защищает исходящие вызовы этой MCP-службы. [VERIFIED: bridge.py:119-145, 312-366; 02-CONTEXT.md:20-25] |
| PID / версия Revit / фактический порт / session token | Revit extension | API / Backend | Источник истины о процессе Revit находится в расширении; CPython только сверяет возвращённую инкарнацию с селектором. [ASSUMED] |
| Перечисление и резолв документов, явная активация | Revit extension | Revit UI | `Application.Documents` и смена активного документа обязаны исполняться в API-контексте Revit; CPython лишь переносит селектор. [ASSUMED] |
| Default/отказ для мутаций и атрибуция изменённого документа | Revit extension | API / Backend | Guard внутри маршрута определяет, какой `Document` допустим; tool-слой предоставляет аргументы и рендерит результат. [ASSUMED] |
| Видимость identity в success и error выводе | API / Backend (CPython MCP) | Revit extension | `format_response` — финальный видимый рендерер; метаданные обязаны выжить после него. [VERIFIED: tools/utils.py:5-107; tools/status_tools.py:39-48] |
| Синхронизация обработчика pyRevit между сессиями | — | Будущая Revit-side инфраструктура | Явно вынесено в backlog 999.1; per-target lock не подаётся как эта гарантия. [VERIFIED: bridge.py:8-17; ROADMAP.md:184-190] |

## Standard Stack

### Core

| Library / facility | Version | Purpose | Why standard |
|---|---|---|---|
| существующий `httpx.AsyncClient` | project-pinned | target-aware локальный HTTP | Уже используется с `trust_env=False`, `text/plain` POST и честной формулировкой отказов; расширять, а не создавать второй путь. [VERIFIED: bridge.py:124-138, 184-207] |
| `asyncio.Lock` (stdlib) | CPython stdlib | одна очередь на инкарнацию target | Существующая модель очереди Фазы 1 доказана; задача — перейти от одного глобала к map, а не приносить пакет синхронизации. [VERIFIED: bridge.py:119-145, 312-345] |
| pyRevit Routes + `routes.make_response` | установленный runtime | регистрация маршрутов и не-бросающие ответы | Весь extension уже живёт на этом транспорте; сохранять injection-семантику, а не заменять сервер. [VERIFIED: startup.py:73-126; CLAUDE.md:142-144] |
| Revit API через pyRevit `HOST_APP` / `revit` | установленный runtime | перечисление, резолв и явная активация документов | Существующий код открытия уже обращается к `HOST_APP.app` / `HOST_APP.uiapp`. [ASSUMED — подтвердить чтением `revit_mcp/worksharing.py` перед реализацией] |

### Supporting

| Facility | Version | Purpose | When to use |
|---|---|---|---|
| `subprocess` + PowerShell `Get-NetTCPConnection` | OS-provided | снапшот слушателей порта перед отправкой | Нужен для AMBIG-01..03. В репозитории `subprocess` уже используется на CPython-стороне, так что новый пакет не требуется. [VERIFIED: tools/process_tools.py:1-30] |
| pyRevit `/routes/sisters` | pyRevit runtime | вспомогательное обнаружение и сверка | Только как дополнительный источник; не может быть единственным доказательством при конфликтующем порту. Phase-1 стенд наблюдал `process_id`, `server_host`, `server_port`, `version`. [ASSUMED — цитата из 01-04-SUMMARY не перечитана в этой сессии] |
| существующий `format_response` | repository code | финальный рендер результата инструмента | Точка вставки identity-суффикса, как уже сделано для `MCP target`. [VERIFIED: tools/utils.py:5-107; tools/status_tools.py:39-48] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Локальный снапшот слушателей | Довериться маршруту, выбранному TCP | Отклонено: при общем порту запрос уже доставлен недетерминированно — нарушает AMBIG-01/02. [VERIFIED: 02-CONTEXT.md:24-25] |
| Map локов по target | Один глобальный lock | Отклонено: нарушает D-03 — неоправданно сериализует независимые Revit-инстансы. [VERIFIED: 02-CONTEXT.md:23] |
| Явный document token | Селектор по `Title` | Отклонено: D-05/D-08 требуют различать одинаковые unsaved-заголовки. [VERIFIED: 02-CONTEXT.md:27-36] |
| Отдельный инструмент активации | Неявная активация внутри read/mutation | Отклонено: D-10..D-12 прямо запрещают автопереключение. [VERIFIED: 02-CONTEXT.md:32-36] |
| Добавить пакет для локальных сокетов | `psutil.get_connections()` | Отклонено как ненужное: `subprocess`+PowerShell уже в проекте; новый пакет требует legitimacy gate и расширяет payload. [VERIFIED: tools/process_tools.py:12-14] |

**Installation:** новых пакетов не требуется — фаза расширяет существующий стек. [ASSUMED]

## Package Legitimacy Audit

Не применяется: план не должен устанавливать внешние пакеты. Единственная потенциальная новая зависимость (`psutil` или аналог для перечисления слушателей) отклонена в пользу уже используемого `subprocess`; если планировщик всё же решит её добавить, обязателен прогон `gsd_run query package-legitimacy check --ecosystem pypi <pkg>` **до** включения в план, а установка — за `checkpoint:human-verify`. [ASSUMED]

## Architecture Patterns

### System Architecture Diagram

```text
MCP клиент (одна общая запись `revit`)
  │  per-call: target selector + optional document selector
  ▼
tool signature (@mcp.tool: async def, -> str, ctx последним, Args:)
  │
  ▼
CPython target resolver  (bridge.py — новая ответственность)
  │
  ├─ 1. локальный снапшот TCP-слушателей выбранного порта
  │        ├─ 0 / >1 / PID ≠ селектора ──► ВИДИМЫЙ ОТКАЗ, модельный запрос НЕ отправляется
  │        ▼ ровно один ожидаемый слушатель
  ├─ 2. handshake к target `/status/` (identity: PID, версия, порт, session token)
  │        ├─ инкарнация не совпала ──► требуется свежий список target-ов
  │        ▼
  ├─ 3. lock, ключ = валидированная инкарнация (все маршруты, кроме GET /status/)
  │        ▼
  └─ 4. text/plain POST к выбранному процессу Routes
              ▼
pyRevit Routes / ExternalEvent boundary
  ├─ /status/  — identity процесса, активный документ не обязателен
  ├─ /documents/ — перечисление открытых документов, активный флаг, identity
  ├─ /activate_document/ — ЯВНАЯ активация (saved / unsaved / workshared)
  ├─ safe reads — model summary и levels только по выбранному Document
  │                 (UI инженера не меняется только после жилого доказательства)
  └─ mutation guard — правило явного/единственного документа; неактивный => 412
              ▼
response attribution: реально ответивший процесс + реальный документ на момент запроса
              ▼
CPython renderer: строка identity добавляется ПОСЛЕ format_response
              ▼
видимый результат / честные формулировки «не отправлено» и «исход неизвестен»
```

Диаграмма описывает поток данных через концептуальные компоненты; сопоставление «файл → ответственность» дано ниже, в таблице Component Responsibilities и в разделе про структуру проекта.

### Component Responsibilities (файл → ответственность)

| Компонент | Ответственность | Не отвечает за |
|---|---|---|
| `bridge.py` | снапшот слушателей, парсинг селектора, target-keyed client/lock, честная формулировка отказов, вставка identity в строку | знание Revit API, выбор документа внутри Revit |
| `tools/*_tools.py` | сигнатуры инструментов (`target`, `document` перед `ctx`), докстринги как контракт | транспорт, разрешение target |
| `revit_mcp/status.py` | identity процесса, не требующая активного документа | атрибуцию мутаций |
| `revit_mcp/documents.py` (новый) | перечисление документов, резолв selector-а, явная активация | рендер строки инструмента |
| mutation guard (в новых/изменённых route-модулях) | правило default/отказа, 412 для неактивного | переключение UI |
| safe-read маршруты (новые) | узкий сбор только по выбранному `Document` | полноту `model_info` |

### Recommended Project Structure

```text
bridge.py                          # target resolver, preflight, target-keyed client/lock, attribution
tools/
├── target_tools.py                # список доступных target-ов (кандидат вместо расширения process_tools)
├── status_tools.py                # аргумент target + видимая identity
├── model_tools.py                 # target/document для разрешённых чтений
└── *_tools.py                     # target у Revit-facing инструментов, document у мутирующих
revit_mcp/
├── identity.py                    # identity процесса + дескриптор/токен документа
├── documents.py                   # list / resolve / activate / безопасные чтения
└── [существующие route-модули]    # атрибуция в ответах мутаций после прохождения G1
tests/unit/
├── test_target_resolution.py
├── test_target_locks.py
├── test_identity_rendering.py
└── test_document_contracts.py
tests/
└── test_phase2_live_identity.py   # standalone, обязательные живые ворота
```

Имена файлов — рекомендация планировщику, а не существующая структура. [ASSUMED]

### Pattern 1: Identity append после форматирования (уже принятый в проекте)

**What:** видимая строка identity добавляется к результату **после** `format_response`, а не передаётся скрытым полем dict.
**When to use:** везде, где identity обязана дойти до модели — мутации, чтения, отказы при полученном ответе.
**Why:** форматтер сводит dict с ключом `message` к одной строке, поэтому вложенное поле исчезает; проект уже решил эту задачу для MCP target и покрыл её тестом.

```python
# Source: tools/status_tools.py:39-48 (проверено чтением файла в этой сессии)
target = getattr(revit_get, "revit_target", None)
response = await revit_get("/status/", ctx, timeout=10.0)
text = format_response(response)
if target:
    # Appended after formatting so it survives format_response reducing
    # a dict with a "message" key to the message alone, and so it is
    # present on error strings (503, refused connection) too.
    text = "{}\nMCP target: {}".format(text, target)
return text
```

### Pattern 2: Отказ до отправки (fail-closed preflight)

**What:** при неоднозначности target-а инструмент возвращает видимую строку отказа и **не** вызывает транспорт.
**When to use:** коллизия слушателей, несовпадение инкарнации, отсутствие селектора при нескольких кандидатах.
**Example:** в существующей очереди уже есть образец «вернуть строку вместо отправки» — `_queue_busy_message()` формируется, когда вызов не был отправлен, и текст это прямо утверждает. [VERIFIED: bridge.py:296-309, 346-351]

### Pattern 3: Резолв документа на момент запроса

**What:** каждый маршрут, адресованный документу, начинает с чтения текущего набора открытых документов и повторного разрешения селектора; при отсутствии — именованная ошибка.
**When to use:** все мутации с `document`, все safe reads, activation.
**Anti-pattern:** хранение `Document` или `doc.Title` в модульной переменной между запросами; проект уже знает этот класс дефектов (см. `model_info.py`, где `doc` берётся заново внутри обработчика). [VERIFIED: revit_mcp/model_info.py:20-39]

### Anti-Patterns to Avoid

- **Кэшировать активный документ** между запросами — нарушает IDENT-03 и даёт ложную атрибуцию после смены UI. [VERIFIED: 02-CONTEXT.md:27-31]
- **Расширять `UNLOCKED_GET`** без живого измерения перекрытия — прямо запрещено комментарием в коде и тестом. [VERIFIED: bridge.py:210-218; CLAUDE.md:186-197]
- **Единый глобальный wrapper в `startup.py` до G1** — рискует сломать signature inspection и ExternalEvent dispatch. [VERIFIED: 02-CONTEXT.md:38-40]
- **Объявлять read безопасным «по аналогии»** с `list_levels` — D-11 требует индивидуального доказательства. [VERIFIED: 02-CONTEXT.md:34-36]
- **Вводить secret/integrity-проверку в identity envelope** — это работа Фаз 3/5. [VERIFIED: 02-CONTEXT.md:11-14, 101]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| HTTP-транспорт | второй клиент или сырые сокеты | существующий `httpx` путь, расширенный по target | В нём уже есть отказ от env-прокси, честные формулировки «не отправлено/неизвестно» и `text/plain` POST. [VERIFIED: bridge.py:124-138, 184-207, 275-309] |
| Разбор тела POST | `json.loads(request.data)` в новом guard | `parse_request_data()` | `application/json` под IronPython 3 ломается до вызова обработчика. [VERIFIED: CLAUDE.md:129-140] |
| Смена активного документа «попутно» | auto-activate в read/mutation | явный activation-инструмент + 412 | Прямое решение D-10..D-12. [VERIFIED: 02-CONTEXT.md:32-36] |
| Определение конфликта порта по ответу | вывод PID из успешного ответа Routes | локальный снапшот слушателей + отказ | Успешный ответ уже поздно получить для AMBIG-01. [VERIFIED: 02-CONTEXT.md:24-25] |
| Кросс-сессионная сериализация | заявлять, что lock покрывает curl/другие MCP-процессы | сохранить ограничение backlog 999.1 | Phase-1 стенд показал cross-wiring обработчика pyRevit. [VERIFIED: bridge.py:8-17, 30-38] |
| Видимость identity | добавлять identity как «ещё одно поле» ответа | суффикс после `format_response` | Форматтер может вернуть только `output`/`message`/`result`/`data`. [VERIFIED: tools/utils.py:27-70] |
| Генерация session token | `import secrets` в `revit_mcp/` | .NET/IronPython-адекватный механизм | `secrets` входит в `PY3_ONLY_MODULES` и запрещён конвенциями. [VERIFIED: scripts/conventions.py:31-35, 222-232] |

**Key insight:** сложность фазы не в открытии ещё одного Revit, а в цепочке провенанса «слушатель ОС → инкарнация процесса → документ, в котором реально исполнялся маршрут → строка, которую увидел ассистент», с честными разрывами на каждом звене.

## Feasibility and Prescriptive Design

### 1. Process selector: incarnation-qualified opaque string

Использовать **один** непрозрачный селектор `target`, включающий как минимум **порт + PID + session token**. Хост, версию Revit и токен показывать в структурированном дескрипторе. Порт или PID по отдельности недостаточны: перезапущенный Revit может переиспользовать и то, и другое, а D-02 требует отличать новую инкарнацию. Конкретная кодировка — на усмотрение реализации, но парсер обязан отвергать отсутствующие, дублированные и неизвестные поля. [VERIFIED: 02-CONTEXT.md:22, 27]

Рекомендуемая последовательность для **каждого** Revit-facing вызова:

1. `target` отсутствует → discovery. Выбирать только если usable-кандидат ровно один; иначе вернуть видимый список кандидатов, не отправляя модельный запрос. [VERIFIED: 02-CONTEXT.md:22]
2. Селектор присутствует → валидировать синтаксис **до** любой сетевой работы; снять снапшот слушателей выбранного порта. Если количество ≠ 1 — отказ; при >1 назвать все конфликтующие PID. **Не** использовать `GET /status/` как арбитра коллизии: это уже маршрутизированный запрос. [VERIFIED: 02-CONTEXT.md:24-25]
3. Требовать, чтобы единственный PID слушателя совпал с PID в селекторе; затем выполнить handshake к `/status/` и сверить token/PID/порт. Несовпадение → отказ и требование свежего списка. [ASSUMED]
4. Взять lock, ключом которого является **валидированная инкарнация**, и отправить запрос. Map не должна молча переиспользовать старый lock после смены session token. [ASSUMED]
5. На каждый **полученный** ответ сравнить identity с запрошенным. Timeout, pre-send отказ и post-send неизвестный исход сохраняют текущие формулировки и **не** заявляют проверенную identity. [VERIFIED: bridge.py:275-309; 02-CONTEXT.md:28-31]

**Честность TOCTOU:** интервал «снапшот → connect» не превращается в доказательство неизменности владельца порта. Формулировать гарантию узко: *сервер отказал, когда снапшот непосредственно перед отправкой был неоднозначен или не совпал с PID селектора*. Если состояние слушателей изменилось после снапшота, либо handshake поймает несовпадение до модельного запроса, либо финальный ответ обязан сообщить фактически полученную identity. Гонку нельзя называть невозможной. [VERIFIED: 02-CONTEXT.md:24-25; ASSUMED]

### 2. Refactor bridge ownership before touching tools

Выделить из фиксированного bridge менеджер с раздельными обязанностями: discovery/preflight (парсеры + тонкий OS-адаптер), target state (client/lock по квалифицированному target с вытеснением устаревшего состояния), send (точный `text/plain` контракт), attribution (только идентичности, реально полученные из HTTP-ответа), rendering (одна видимая строка identity).

Текущие скалярные факты, обязанные измениться: `BASE_URL` собирается из import-time окружения, `_get_client()` владеет ровно одним клиентом, `_get_lock()` возвращает один глобальный lock. [VERIFIED: bridge.py:107-145] Сохранить инвариант `UNLOCKED_GET = frozenset({"status"})`; `/model_info/` намеренно остаётся залоченным, потому что перекрытие не измерялось. [VERIFIED: bridge.py:210-240]

**Влияние на тесты:** `tests/unit/test_bridge_serialization.py` инжектирует клиент через `bridge._http_client` с фиксированным `base_url="http://test:1/revit_mcp"` и в autouse-фикстуре сбрасывает `bridge._lock` и `bridge._http_client`. [VERIFIED: tests/unit/test_bridge_serialization.py:28-44] При переходе к map эти три точки станут точками правки тестов; сам файл — готовый шаблон для новых тестов `target`-логики (MockTransport, без Revit и сети).

### 3. Document identity — живой реестр, не `Title` и не кэш

Реализовать extension-side сервис дескрипторов документов, используемый list/activate/safe-read маршрутами и mutation guard:

- перечислять **текущие** открытые документы на каждом резолве; различать `title`, `path`, признак активного и непрозрачный токен документа;
- для сохранённых документов путь может быть читаемым признаком, но не единственным идентификатором; для unsaved ни title, ни path не уникальны. [VERIFIED: 02-CONTEXT.md:27-36]
- токен выдаётся конкретному открытому объекту и разрешается **только** против текущего перечисления; закрытый токен даёт именованную ошибку и никогда не откатывается на активный документ. [VERIFIED: 02-CONTEXT.md:32-33]
- реестр — это bookkeeping селектора, **не** источник активного документа. Identity в ответе мутации выводится из фактического документа в момент исполнения маршрута (после активации/смены UI), что закрывает IDENT-03. [VERIFIED: 02-CONTEXT.md:27-31]
- механизм идентичности объекта Revit (`GetHashCode`, путь, свойство Revit или собственный токен) **не выбирать** статически: сначала живой пробник должен установить, какое значение стабильно в течение жизни документа, различает два unsaved `Project1` и становится невалидным после закрытия. [ASSUMED]

### 4. Safe reads — только узкие новые маршруты

**Не** ретрофитить `get_model_info()`: обработчик перетирает локальную переменную значением `revit.doc`. [VERIFIED: revit_mcp/model_info.py:20-39] **Не** объявлять `/list_levels/` безопасным только потому, что он принимает инъецированный `doc`: маршрут всё равно исполняется в реальном pyRevit API-контексте, и стабильность UI нужно измерять. [VERIFIED: revit_mcp/placement.py:617-639]

Создать два намеренно узких адресуемых маршрута, каждый принимает явный document token и в том же запросе перечисляет/валидирует документ:

- **document summary** — минимальная сводка, собираемая только по выбранному `Document` и хелперам, доказанно не читающим глобальный `revit.doc`/`UIDocument`;
- **document levels** — коллектор и сериализация только по выбранному `Document`.

Оба возвращают дескриптор и данные вместе. Полный `/model_info/` включает project info, категорийные коллекторы, warnings, rooms, views/sheets и связи — копировать его целиком значит неоправданно расширить поверхность риска для неактивного документа. Только после живого A/B-теста (документ A активен, B — нет) эти два маршрута можно объявить поддерживаемыми; любое другое адресованное чтение явно отказывает, пока не измерено отдельно. [VERIFIED: 02-CONTEXT.md:34-36]

### 5. Mutation guard и прокат контракта инструментов

Каждая мутация обязана принимать опциональный `document`, каждый Revit-facing инструмент — опциональный `target`, и оба — **перед** `ctx` (иначе падает `test_conventions`). [VERIFIED: scripts/conventions.py:470-478] Сейчас `list_levels` принимает только `ctx` и вызывает `revit_get("/list_levels/", ctx)`; `get_revit_status` уже читает `revit_target` через `getattr` — образец того, как инструмент получает сведения о target, не импортируя транспорт. [VERIFIED: tools/model_tools.py:13-28; tools/status_tools.py:41-42]

На границе Revit-маршрута использовать общий guard **только после** прохождения G1. Он обязан:

1. разрешить явный `document` против текущего набора открытых документов;
2. при явном селекторе и неактивном документе вернуть зафиксированный `HTTP 412`;
3. без селектора мутировать только при ровно одном eligible-документе, иначе отказать со списком;
4. передавать дальше фактический документ только после подтверждения соответствия разрешённой identity;
5. добавлять request-time identity документа во все ответы мутаций, включая non-200, где ответ реально получен.

В extension-коде сейчас сосуществуют обработчики вида `def handler(doc, request)` и маршруты, читающие `revit.doc` внутри; наборы инъецируемых аргументов различаются. [VERIFIED: revit_mcp/status.py:18-19; revit_mcp/model_info.py:20-21; revit_mcp/placement.py:617-618; startup.py:73-126] Поэтому выбор общего wrapper без изучения реализации pyRevit — недопустимый риск для D-13. [VERIFIED: 02-CONTEXT.md:38-40]

## Mandatory Decision Gates

| Gate | Триггер / требуемое доказательство | Pass | Stop |
|---|---|---|---|
| **G1 — pyRevit wrapper feasibility** | Изучить фактическую реализацию `routes.API.route` (inspection сигнатур, инъекция `doc`/`uidoc`/`request`, ExternalEvent dispatch), затем минимальный неизменяющий живой пробник с инъецированными `doc`, `uidoc`, `request`. | Общий wrapper можно вводить только если он сохраняет точную семантику инъекции и не-бросающие ответы. | Общий wrapper не вводить; планировать явные правки маршрутов либо сократить объём с решением пользователя. [VERIFIED: 02-CONTEXT.md:38-40] |
| **G2 — document token feasibility** | Два сохранённых/unsaved документа с одинаковым заголовком: list → независимый резолв → закрыть один → повторить токен. | Токен указывает ровно на один документ в течение жизни и даёт именованный отказ после закрытия. | Остановиться до проката контракта селектора и выбрать другой наблюдаемый механизм identity. [VERIFIED: 02-CONTEXT.md:32-33] |
| **G3 — inactive read safety** | A активен, B нет: вызвать summary и levels по B, проверить, что данные — от B и активный документ UI остался A; повторить в обратном порядке. | Пометить безопасными **только** измеренные маршруты. | Не активировать автоматически; вернуть явный отказ и доложить, что минимум D-11 не достигается. [VERIFIED: 02-CONTEXT.md:34-36] |
| **G4 — activation** | Явно активировать уже открытые saved и unsaved документы; наблюдать worksharing-диалоги и состояние UI. | Инструмент выпускать только для наблюдаемо поддержанных случаев с явными отказами для остальных. | Не переиспользовать `/open_model/` и не включать автоактивацию. [VERIFIED: 02-CONTEXT.md:34-36] |
| **G5 — ambiguity race** | Создать дублирующий слушатель на порту, затем проверить discovery и preflight непосредственно перед отправкой. | Отказ называет все PID, запрошенный маршрут не отправляется. | Задокументировать точное ограничение и не заявлять защиту сильнее снапшота. [VERIFIED: 02-CONTEXT.md:24-25] |
| **G6 — AMBIG-04 diagnosis** | Повторить write/read репродукцию последовательно и с намеренным перекрытием; сохранить видимые identity и исход транзакции. | Зафиксировать «подтверждено» или «опровергнуто» по каждому прогону. | Требование остаётся незакрытым; вывод не выдумывать. [VERIFIED: 02-CONTEXT.md:29-30] |

## Common Pitfalls

### Pitfall 1: Порт считается идентичностью процесса
**What goes wrong:** перезапущенный Revit переиспользует порт (и PID), устаревший селектор попадает в новый процесс.
**Why:** текущий target — это `host:port` и только. [VERIFIED: bridge.py:107-112]
**How to avoid:** квалифицировать селектор session token-ом и перепроверять handshake-ом перед модельным трафиком. [VERIFIED: 02-CONTEXT.md:22, 27]
**Warning signs:** identity из `/status/` не совпадает со списком.

### Pitfall 2: Коллизия обнаруживается после запроса
**What goes wrong:** сам `/status/` или модельный вызов уходит произвольному слушателю.
**Why:** две Revit-инстанции действительно могут слушать один порт, pyRevit не ставит exclusive-address flag. [VERIFIED: CLAUDE.md:222-232]
**How to avoid:** снапшот слушателей до любого выбранного HTTP-запроса; путь отказа не должен отправлять модельный запрос.
**Warning signs:** в снапшоте два PID или PID не равен селектору.

### Pitfall 3: Один глобальный lock сериализует разные Revit
**What goes wrong:** независимые target-ы блокируют друг друга, а lock перестаёт выражать владение target-ом.
**Why:** сейчас есть module-global `_lock`. [VERIFIED: bridge.py:119-145]
**How to avoid:** lock по валидированной инкарнации; один lock на target, общий для его документов. [VERIFIED: 02-CONTEXT.md:23]

### Pitfall 4: Кэш активного документа переживает смену UI
**What goes wrong:** мутация/чтение атрибутируется документу A после переключения Revit на B.
**Why:** D-05 прямо называет этот режим отказа. [VERIFIED: 02-CONTEXT.md:27-31]
**How to avoid:** выводить дескриптор документа внутри исполнения API-запроса и прикреплять после операции.
**Warning signs:** title/path в ответе не совпадает с UI после активации/ручного переключения.

### Pitfall 5: Title/path как уникальный ключ документа
**What goes wrong:** два unsaved `Project1` коллизируют, либо закрытый документ откатывается на активный.
**Why:** одинаковые unsaved-заголовки — явный приёмочный случай. [VERIFIED: 02-CONTEXT.md:27-36]
**How to avoid:** непрозрачный токен времени жизни + валидация против живого перечисления; кандидаты включают различающие признаки.
**Warning signs:** более одного совпадения по title даёт выбор вместо отказа.

### Pitfall 6: Полный `/model_info/` объявлен safe для неактивного документа
**What goes wrong:** обработчик читает глобальное активное состояние, а ответ помечен как выбранный неактивный документ.
**Why:** обработчик читает `revit.doc`, а его хелперы охватывают существенно больше узкого коллектора. [VERIFIED: revit_mcp/model_info.py:7, 20-39]
**How to avoid:** новые узкие маршруты + живая проверка данных и UI на двух документах.
**Warning signs:** активный UI меняется; ответы A и B неожиданно совпадают.

### Pitfall 7: Универсальный wrapper в `startup.py` ломает Routes injection
**What goes wrong:** изменённая сигнатура приводит к пропуску маршрута, потере API-контекста или request data.
**Why:** обработчики имеют разные сигнатуры, а реализация inspection/ExternalEvent в этой сессии не читалась. [VERIFIED: revit_mcp/status.py:18-19; revit_mcp/model_info.py:20-21; revit_mcp/placement.py:617-618]
**How to avoid:** обязательный G1 + живой неизменяющий пробник; сохранять `text/plain`/`parse_request_data`.

### Pitfall 8: Identity есть в JSON, но не видна модели
**What goes wrong:** ключ `message` скрывает соседние поля, а non-200 превращается в непрозрачную строку. [VERIFIED: tools/utils.py:27-36; bridge.py:207]
**How to avoid:** добавлять суффикс identity **после** форматирования (уже принятый паттерн) либо единый тестируемый рендерер; различать «ответ получен» и «не отправлено/неизвестно».
**Warning signs:** новый тест вида `test_identity_survives_message_payload` не написан.

### Pitfall 9: Новые параметры инструмента ломают конвенции
**What goes wrong:** `target`/`document` добавлены после `ctx` или не упомянуты в `Args:` → падает `test_conventions`.
**Why:** конвенции требуют `ctx` последним и полноту `Args:`-блока. [VERIFIED: scripts/conventions.py:470-499]
**How to avoid:** добавлять новые параметры строго перед `ctx` и в докстринг в том же коммите.

### Pitfall 10: Фаза 2 незаметно реализует политику Фазы 5
**What goes wrong:** метаданные identity превращаются в проверку секрета или целостности.
**Why:** живая enforcement-логика явно отложена. [VERIFIED: 02-CONTEXT.md:11-14, 101]
**How to avoid:** identity несёт только семантику селектора и атрибуции; никаких 401/423/секретных проверок в этой фазе.

## Code Examples

Все примеры ниже — иллюстративные псевдокод-схемы; конкретные имена и словарь ошибок не являются контрактом до прохождения G1/G2. [ASSUMED]

### Последовательность валидации target (CPython)

```python
# Illustrative CPython flow — the send path must stay the existing text/plain one.
async def call_selected_target(selector, endpoint, *, method, payload, ctx):
    target = parse_and_validate_selector(selector)   # malformed -> refusal, no send
    pids = listeners_on_port(target.port)            # local OS snapshot
    if len(pids) != 1 or pids[0] != target.pid:
        return render_refusal(target, pids)          # model request never sent

    identity = await get_status_for(target)          # only after an unambiguous snapshot
    if not same_incarnation(target, identity):
        return render_stale_selector(target, identity)

    async with lock_for(identity):                   # keyed by validated incarnation
        response = await existing_text_plain_send(identity, method, endpoint, payload)
    return render_with_received_identity(response, identity)
```

Опорная структура: `_serialized()` держит lock, `_send()` выполняет ровно один HTTP-обмен, а `_is_locked()` оставляет незалоченным только `GET /status/`. [VERIFIED: bridge.py:230-240, 312-336, 356-366]

### Контракт резолва документа

```python
# IronPython-safe shape; final API selection belongs to G1/G2 — no f-strings, no typing.
def resolve_document_or_refuse(requested_token, current_documents):
    matches = [d for d in current_documents
               if token_for_open_document(d) == requested_token]
    if len(matches) != 1:
        return None, named_closed_or_ambiguous_error(requested_token)
    return matches[0], None
```

Несущие свойства — ровно одно совпадение и отсутствие откатa на активный документ; кодировка ключа остаётся свободной. [VERIFIED: 02-CONTEXT.md:32-33]

### Обязательства докстринга мутирующего инструмента

```text
Scope: `target` is selected per call. `document` is optional only when exactly one
eligible document is open; with several open documents this tool refuses and lists
candidates. An explicitly selected inactive document returns HTTP 412; call the
separate activation tool and retry. Returned text identifies the actual responding
process and document when a response was received.

Args:
    target: opaque process selector from the target list, or omitted when exactly one process is available
    document: opaque document selector from the document list, or omitted when exactly one document is open
    ctx: MCP context for logging
```

Формулировки можно менять; неизменны семантика default/отказа/активации и требование `Args:`-блока со всеми параметрами. [VERIFIED: 02-CONTEXT.md:20-25, 32-36; scripts/conventions.py:487-499]

### Существующий паттерн видимой identity

Приведён выше в Pattern 1 — это фактический код проекта, а не предложение. [VERIFIED: tools/status_tools.py:39-48]

## State of the Art

| Old approach | Current required approach | When changed | Impact |
|---|---|---|---|
| Один import-time `REVIT_HOST:REVIT_PORT`, один глобальный lock | Одна общая запись `revit`, выбор target per call, lock на target | Phase-1 a5-a, перенесено в Phase 2 (комментарий в `bridge.py` фиксирует принадлежность фазе) | Требует селектора в API инструментов и keyed-состояния в bridge. [VERIFIED: bridge.py:60-66, 107-145; ROADMAP.md:90] |
| Lock только для мутаций + allowlist чтений | Lock для всего, кроме GET `/status/` | Phase-1 d27-b после живого измерения перекрытия | Target-keyed реализация обязана сохранить строгий default. [VERIFIED: bridge.py:19-26, 210-240] |
| Только активный документ | Адресуемые чтения только после индивидуального доказательства | Phase-2 D-11 | Нужны новые узкие маршруты и decision gate; сплошной ретаргетинг чтений запрещён. [VERIFIED: 02-CONTEXT.md:34-36] |
| Две клиентские записи MCP для двух Revit | Одна общая запись `revit` | Phase-1 a5-a | Нельзя документировать дублирующиеся записи; выбор живёт внутри инструментов. [VERIFIED: ROADMAP.md:90] |

**Deprecated/outdated:** обход очереди для чтений недопустим — Phase-1 стенд измерял `cross-wired-read`, и текущий код разлочивает только `GET /status/`. [VERIFIED: bridge.py:19-26, 210-218]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | Существует представление открытого документа Revit, позволяющее выдать непрозрачный токен и валидировать его против текущего набора документов. | Feasibility §3 | Не удастся различить unsaved/одноимённые документы либо появится возможность устаревшего выбора. |
| A2 | Handshake к `/status/` после снапшота слушателей способен обнаружить смену инкарнации до запрошенного модельного маршрута. | Feasibility §1 | Гонка может привести к неверной атрибуции; ограничение нужно задокументировать и измерить живьём. |
| A3 | `Session token` можно сгенерировать на Revit-половине без запрещённых конвенциями модулей (`secrets` запрещён, `uuid` требует проверки). | Constraints / OQ-5 | IDENT-01 придётся закрывать другим механизмом; это влияет на формат селектора. |
| A4 | Узкие summary и levels можно собрать только по выбранному `Document`, без чтения `revit.doc`/`UIDocument`. | Feasibility §4 | Минимум D-11 недостижим; фаза обязана остановиться на G3 и доложить ограничение. |
| A5 | Уже открытые saved и unsaved документы можно явно активировать в поддержанных условиях. | G4 | Инструмент активации придётся ограничить документированными отказами или вынести решение пользователю. |
| A6 | Общий route-wrapper способен сохранить signature inspection и ExternalEvent dispatch pyRevit. | G1 / Mutation guard | Wrapper может сломать регистрацию или исполнение в API-контексте; без доказательства его вводить нельзя. |
| A7 | `Get-NetTCPConnection` доступен и парсируем из окружения MCP-сервера. | Standard Stack / Environment | AMBIG-01..03 потребуют другого одобренного механизма локального перечисления слушателей. |
| A8 | Цитата полей `/routes/sisters` (`process_id`, `server_host`, `server_port`, `version`) из Phase-1 стенда. | Standard Stack | Вспомогательное обнаружение придётся строить иначе; на AMBIG-01..03 это не влияет, поскольку основное доказательство — локальный снапшот. |
| A9 | Внешняя документация Revit API/pyRevit по неактивному `Document` и активации недоступна в этой среде. | Sources / OQ-1..OQ-4 | Решения останутся привязанными к живым воротам G1–G6, а не к цитатам из документации. |

## Open Questions

1. **Какова фактическая семантика `routes.API.route` (inspection сигнатур, инъекция, ExternalEvent dispatch) и совместим ли с ней общий wrapper?**
   - Что известно: сигнатуры обработчиков в репозитории разнородны, часть маршрутов читает `revit.doc` внутри. [VERIFIED: revit_mcp/status.py:18-19; revit_mcp/model_info.py:20-21; revit_mcp/placement.py:617-618]
   - Что неизвестно: реализация signature inspection и диспетчеризации в установленной версии pyRevit.
   - Рекомендация: G1 — первый шлюз реализации; до него общий wrapper не вводить.

2. **Какой механизм Revit даёт корректный токен документа для двух unsaved `Project1`?**
   - Что известно: title/path по отдельности не закрывают требование. [VERIFIED: 02-CONTEXT.md:27-36]
   - Что неизвестно: стабильность и уникальность кандидатов на протяжении жизни документа.
   - Рекомендация: живой пробник G2 по жизненному циклу saved/unsaved/close, затем фиксация формата.

3. **Возможна ли явная активация уже открытого документа для saved, unsaved и workshared случаев?**
   - Что известно: в репозитории есть `host.uiapp.OpenAndActivateDocument(...)` в контексте открытия пути, а не активации уже открытого документа. [ASSUMED — подтвердить чтением `revit_mcp/worksharing.py` перед реализацией]
   - Что неизвестно: допустимая перегрузка/контекст вызова и поведение диалогов.
   - Рекомендация: реализовывать только после G4, не переносить логику `/open_model/` по аналогии.

4. **Сохраняют ли минимальные чтения неактивного документа UI инженера?**
   - Что известно: `get_model_info()` читает активный документ, `list_levels(doc)` принимает инъецированный. [VERIFIED: revit_mcp/model_info.py:20-39; revit_mcp/placement.py:617-639]
   - Что неизвестно: побочные эффекты pyRevit/Routes в контексте неактивного `Document`.
   - Рекомендация: новые узкие реализации + G3; при неудаче — стоп, а не тихое ослабление D-11.

5. **Откуда Revit-половина берёт «фактический порт» и допустимый session token без запрещённых модулей?**
   - Что известно: `secrets` (и ряд других модулей) запрещены конвенциями для `revit_mcp/`. [VERIFIED: scripts/conventions.py:31-35, 222-232]
   - Что неизвестно: доступный API/переменная окружения установленного Routes-сервера, а также IronPython-адекватный источник случайности/идентификатора.
   - Рекомендация: изучить исходники установленного pyRevit Routes и сверить вывод `/status/` со снапшотом ОС в рамках G5.

6. **Какова судьба существующего харнесса `tests/test_two_instance_targets.py`?**
   - Что известно: файл существует, описывает «Two MCP entries, two Revit ports», работает и офлайн, и требует двух живых Revit. [ASSUMED — читались только первые строки]
   - Что неизвестно: покрывает ли он критерий «одна общая запись + per-call выбор».
   - Рекомендация: считать его reuse-asset для offline-части и заменить/дополнить новым харнессом одной записи для живой части; не выдавать его за доказательство Phase 2.

## Environment Availability

| Dependency | Required by | Available | Version / observation | Fallback |
|---|---|---|---|---|
| `uv` | unit-тесты, cold-start gate | ✓ | 0.11.1 (наблюдено локально 2026-10-14) | — |
| локальный Python | CPython-тесты | ✓ | 3.14.2 (наблюдено локально); совместимость с dev pin не проверялась | запуск через `uv run` |
| `curl.exe` | неизменяющая живая HTTP-проверка | ✓ | 8.22.0 (наблюдено локально) | live-харнесс на Python |
| Windows TCP-инвентарь (`Get-NetTCPConnection`) | AMBIG-01..03 | не подтверждено в этой среде | требует проверки на инженерном стенде | обязательный human checkpoint; ослабленного вывода не делать |
| Два живых Revit + pyRevit Routes | все живые ворота G1–G6 | не запускалось | инструкция задачи запрещает mutating/live действия | стенд под управлением человека после полного перезапуска Revit |
| PowerShell/`subprocess` на CPython-стороне | снапшот слушателей | ✓ | `subprocess` уже используется в `tools/process_tools.py` | — |

**Missing dependencies with no fallback:** живые Revit/pyRevit для G1–G6; ни unit-, ни source-тесты не способны установить эти утверждения. [VERIFIED: 02-CONTEXT.md:38-40]

**Missing dependencies with fallback:** сам TCP-инвентарь не верифицирован в этой среде, но `subprocess`-путь в проекте уже есть, поэтому замена на другой локальный механизм возможна без новых пакетов. [VERIFIED: tools/process_tools.py:12-14]

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | `pytest` через `uv run`; unit-набор обязан работать без Revit, pyRevit и сети. [VERIFIED: CLAUDE.md:47-59] |
| Config file | отдельного конфига не наблюдено; следовать существующим конвенциям прямого pytest. [ASSUMED] |
| Quick run command | `uv run pytest tests/unit` |
| Full suite command | `uv run pytest tests/unit` + `python tests/test_init_latency.py` (cold-start gate < 2.0 с); живые ворота — отдельный человекоуправляемый прогон, не pytest |

Существующие асинхронные тесты используют фикстуру `anyio_backend` → `"asyncio"` и `httpx.MockTransport`, заменяя транспорт целиком; trio специально не добавляется. [VERIFIED: tests/unit/test_bridge_serialization.py:22-44]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| IDENT-01 | схема `/status/` содержит PID/версию/порт/токен; устаревший селектор отвергается | unit + live | `uv run pytest tests/unit/test_target_resolution.py -x` + живой прогон | ❌ Wave 0 |
| IDENT-02 | identity мутации выживает рендер инструмента | unit + live | `uv run pytest tests/unit/test_identity_rendering.py -x` + живая мутация | ❌ Wave 0 |
| IDENT-03 | ручное переключение/активация даёт фактический документ | live | живой харнесс после полного перезапуска | ❌ только live |
| IDENT-04 | одноимённые документы различимы в ответе | unit + live | тесты дескриптора + стенд двух инстансов | ❌ Wave 0 |
| AMBIG-01 | дублирующий слушатель обнаружен до отправки | unit + live | тест с mock OS-адаптера + live checkpoint | ❌ Wave 0 |
| AMBIG-02 | при дублирующем слушателе модельный запрос не отправляется | unit + live | `uv run pytest tests/unit/test_target_resolution.py -x` + checkpoint | ❌ Wave 0 |
| AMBIG-03 | отказ перечисляет все PID | unit + live | fixture-тест рендера отказа + checkpoint | ❌ Wave 0 |
| AMBIG-04 | репродукция даёт записанное доказательство identity | live | отдельный скрипт + сохранённая консоль | ❌ только live |
| MDOC-01 | список открытых документов с identity и активным флагом | unit + live | тест сериализации дескрипторов + живой тест | ❌ Wave 0 |
| MDOC-02 | мутация принимает явный document selector | schema/unit + live | тесты регистрации/схемы + живая явная мутация | ❌ Wave 0 |
| MDOC-03 | без селектора отказ только при >1 eligible-документе | unit + live | тест таблицы решений guard-а + живой тест | ❌ Wave 0 |
| MDOC-04 | отдельная активация меняет UI только по запросу | live | прогоны saved и unsaved | ❌ только live |
| MDOC-05 | закрытый токен даёт именованный отказ без fallback | unit + live | fixture close-race + live list-close-retry | ❌ Wave 0 |

Дополнительно обязательны regression-тесты, защищающие существующие инварианты при прокате контракта: `test_unlocked_every_tool_endpoint_except_status_is_locked`, `test_unlocked_is_exactly_get_status`, `test_unlocked_model_info_is_locked`, `test_unlocked_never_unlocked_stay_locked_even_if_listed`, `test_bridge_imports_without_fastmcp` и полный `test_conventions`. [VERIFIED: tests/unit/test_bridge_serialization.py:100-116, 507-560]

### Sampling Rate

- **Per task commit:** `uv run pytest tests/unit`.
- **Per wave merge:** `uv run pytest tests/unit` + `python tests/test_init_latency.py`.
- **Phase gate:** полный unit/cold-start набор плюс все зафиксированные живые ворота G1–G6, каждый — после полного перезапуска Revit при любой правке `revit_mcp/`. [VERIFIED: CLAUDE.md:47-59, 201-204; 02-CONTEXT.md:38-40]

### Wave 0 Gaps

- [ ] `tests/unit/test_target_resolution.py` — парсер селектора, таблица решений default, коллизия/несовпадение PID с утверждением «не отправлено», устаревшая инкарнация.
- [ ] `tests/unit/test_target_locks.py` — одна инкарнация сериализуется, разные target-ы идут параллельно, устаревшая инкарнация не переиспользует ключ.
- [ ] `tests/unit/test_identity_rendering.py` — identity выживает при `message`/`result`/`data`-payload и на строковом error-пути; «не отправлено/неизвестно» остаётся без атрибуции.
- [ ] `tests/unit/test_document_contracts.py` — таблица решений document-selector-а (default/отказ/412) и покрытие схемы всех мутирующих инструментов.
- [ ] `tests/test_phase2_live_identity.py` — standalone-харнесс, записывающий PID слушателей, identity, список документов, активацию, наблюдения UI по safe reads, close-race и результат AMBIG-04.
- [ ] обновить `tests/unit/tool_manifest.txt` для каждого нового инструмента в том же коммите. [VERIFIED: CLAUDE.md:86-106; tests/unit/test_registration.py:105-126]
- [ ] расширить `tests/unit/test_status_target.py`-подобным покрытием для новых инструментов: строка identity обязана добавляться после `format_response`. [VERIFIED: tests/unit/test_status_target.py:60-86]

## Security Domain

Анализ обязателен: `security_enforcement` не выставлен в `false`, отдельного отключения в конфиге не найдено. [ASSUMED]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard control |
|---|---|---|
| V2 Authentication | нет в этой фазе | Проверки секрета не добавлять — это работа Фаз 3/5. [VERIFIED: 02-CONTEXT.md:11-14, 101] |
| V3 Session Management | да | Session token — различитель инкарнации процесса, **не** аутентификационный секрет. [VERIFIED: 02-CONTEXT.md:22, 27] |
| V4 Access Control | да | Отказ при неоднозначности селектора предотвращает «confused targeting»; неактивная мутация получает 412. [VERIFIED: 02-CONTEXT.md:24-25, 32-34] |
| V5 Input Validation | да | Строгий разбор target/document селекторов, отказ на отсутствующие/неизвестные/неоднозначные значения; тело — только через `parse_request_data()`. [VERIFIED: CLAUDE.md:129-140; 02-CONTEXT.md:32-36] |
| V6 Cryptography | нет | Токен не является криптографическим доказательством; ничего не хешировать и не подписывать в этой фазе. [VERIFIED: 02-CONTEXT.md:11-14] |
| V7/V10 Error handling | да | Обработчики не бросают исключений; явный отказ вместо тихого fallback на активный документ. [VERIFIED: CLAUDE.md:142-144; 02-CONTEXT.md:32-33] |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Запрос уходит не тому Revit из-за общего порта | Spoofing / Tampering | Снапшот слушателей до отправки, сверка PID, явный отказ со списком. [VERIFIED: CLAUDE.md:222-232; 02-CONTEXT.md:24-25] |
| Устаревший селектор после перезапуска/переиспользования PID | Spoofing | Селектор, квалифицированный session token-ом; handshake и обязательный новый выбор. [VERIFIED: 02-CONTEXT.md:22, 27] |
| Изменён не тот документ | Tampering | Default только для единственного документа, явный выбор, 412 для неактивного, без автоактивации. [VERIFIED: 02-CONTEXT.md:32-36] |
| Cross-wiring ответов между сессиями pyRevit | Tampering / Repudiation | Сохранить явное ограничение; не заявлять, что target-lock это решает; backlog 999.1. [VERIFIED: bridge.py:8-17] |
| Скрытая атрибуция в error-ответе | Repudiation | Общий рендерер + тесты на status/non-200/transport-исходы; identity заявляется только при полученном ответе. [VERIFIED: 02-CONTEXT.md:28-31; tools/utils.py:72-107] |
| Расширение поверхности `/execute_code/` | Elevation of Privilege | Не трогать и не расширять; предпочитать типизированные маршруты. [VERIFIED: CLAUDE.md:196-198] |

## Sources

### Primary (HIGH confidence)

Внешняя первичная документация в этой сессии получить не удалось: провайдер `context7`, выбранный исследовательским seam, был недоступен, поэтому его результат трактуется как пробел исследования, а не как доказательство. [ASSUMED]

### Repository evidence (HIGH for the quoted file facts — каждый файл прочитан в этой сессии)

- `bridge.py` — фиксированный target/client/global lock, покрытие очереди, `text/plain` POST, честные формулировки отказов, `UNLOCKED_GET`/`NEVER_UNLOCKED`. [VERIFIED: bridge.py:8-17, 60-70, 107-145, 184-240, 275-366]
- `revit_mcp/status.py` — текущий payload `/status/` без PID/версии/порта/токена; `doc = revit.doc`. [VERIFIED: revit_mcp/status.py:18-90]
- `revit_mcp/model_info.py` — импорт `revit`, `doc = revit.doc` внутри обработчика, широкая поверхность сбора. [VERIFIED: revit_mcp/model_info.py:7-14, 20-39]
- `revit_mcp/placement.py` — `list_levels(doc)` с `FilteredElementCollector(doc)`, миллиметровая конвертация, не-бросающий возврат. [VERIFIED: revit_mcp/placement.py:617-676]
- `tools/utils.py` — порядок ветвей `format_response`, error-рендер и «ADDITIONAL RESPONSE DATA». [VERIFIED: tools/utils.py:5-107]
- `tools/status_tools.py` — существующий приём «identity после форматирования», `get_revit_model_info` без селекторов. [VERIFIED: tools/status_tools.py:13-65]
- `tools/model_tools.py` — `list_levels(ctx=None)` без document-параметра. [VERIFIED: tools/model_tools.py:13-28]
- `tools/process_tools.py` — `subprocess`/`glob` уже используются на CPython-стороне. [VERIFIED: tools/process_tools.py:1-30]
- `scripts/conventions.py` — каноническая сигнатура регистратора, правила сигнатур инструментов, запрещённые модули IronPython. [VERIFIED: scripts/conventions.py:24-35, 191-232, 421-503]
- `tests/unit/test_status_target.py` — образец проверки видимой identity на success, message-payload и error-string. [VERIFIED: tests/unit/test_status_target.py:22-86]
- `tests/unit/test_bridge_serialization.py` — фикстура сброса `bridge._lock`/`bridge._http_client`, MockTransport, список инвариантов очереди. [VERIFIED: tests/unit/test_bridge_serialization.py:19-44, 66-116, 507-560]
- `.planning/phases/02-.../02-CONTEXT.md` — обязательные решения D-01..D-14 и границы фазы. [VERIFIED: 02-CONTEXT.md:8-105]
- `.planning/REQUIREMENTS.md` — тексты IDENT-01..04, AMBIG-01..04, MDOC-01..05 и трассировка. [VERIFIED: .planning/REQUIREMENTS.md:10-31, 157-169]
- `.planning/ROADMAP.md` — goal, девять критериев, перенос a5-a/d27-b, backlog 999.1. [VERIFIED: .planning/ROADMAP.md:84-104, 182-190]
- `CLAUDE.md` — Two-Runtime Rule, transport/route-инварианты, listener-опасность, restart-требование. [VERIFIED: CLAUDE.md:11-44, 86-106, 108-166, 186-236]

### Secondary (MEDIUM confidence)

- Поля `/routes/sisters` (`process_id`, `server_host`, `server_port`, `version`) и результаты Phase-1 overlap-стенда (`cross-wired-mutation`, `cross-wired-read`) приведены по сводке Phase-1 и в этой сессии не перечитаны из первоисточника. Перед использованием в плане перечитать `.planning/phases/01-.../01-04-SUMMARY.md`. [ASSUMED]
- Публичная документация Revit API по неактивному `Document` и активации не подтверждена: соответствующие member-страницы получить не удалось. Поведение остаётся за воротами G2–G4. [ASSUMED]

### Tertiary (LOW confidence)

- Любые утверждения о поведении pyRevit signature inspection/ExternalEvent dispatch, об идентичности объекта документа Revit и о допустимости активации уже открытого документа остаются гипотезами до живого пробника. [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** в части «расширять существующий bridge/runtime», **MEDIUM** по подключению Windows/Revit-механик.
- Architecture: **HIGH** для границы CPython и обязательных решений D-01..D-14, **MEDIUM** для Revit-механик wrapper-а и документов (ожидают G1/G2).
- Pitfalls: **HIGH** для наблюдаемых в репозитории ловушек (single global lock, форматтер, конвенции, listener-коллизия), **MEDIUM** для активации и неактивных чтений.
- Requirements coverage: все IDENT/AMBIG/MDOC имеют хотя бы один автоматизируемый слой проверки; IDENT-03, AMBIG-04, MDOC-04 закрываются **только** живым прогоном.

**Research date:** 2026-10-14
**Valid until:** факты репозитория — до изменения соответствующих файлов; выводы о живом API Revit/pyRevit — не по времени, а по факту прохождения G1–G6.
