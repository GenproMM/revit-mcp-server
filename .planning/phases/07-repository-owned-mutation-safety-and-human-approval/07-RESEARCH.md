# Phase 7: Repository-owned mutation safety and human approval - Research

**Researched:** 2026-10-25
**Domain:** MCP server-side elicitation (CPython, FastMCP), one-time HMAC permits enforced inside a pyRevit IronPython 3.4 extension, TOML policy with hot reload, payload/deploy impact of an MCP SDK upgrade
**Confidence:** HIGH for the SDK, client-handler, permit and deploy findings (each was read in source or reproduced by a command this session; see Gate-by-Gate Answers and Sources); MEDIUM for Revit API behaviours that were not run live (instance counts, group propagation, shared-parameter file format); the `[ASSUMED]` items are in the Assumptions Log.

> Evidence tags used below. `[VERIFIED: ...]` read in source this session or reproduced by a command; `[CITED: url]` official docs; `[ASSUMED]` not verified. In-repo discrete values carry a path, a line range and a verbatim quote.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Confirmed User Constraints (2026-10-16)

- **D-01 — ownership:** «Вся безопасность касаемо revit mcp должна быть на уровне этого репозитория». Более раннее предложение перенести обязательную защиту в Hermes отвергнуто; оно не является запасным implementation plan.
- **D-02 — lightweight:** пользователь просит стабильную лёгкую адаптацию с возможностью корректировать правила, без ненужного усложнения MCP. Это не запрос на универсальный gateway, отдельный policy cluster или изменение harness.
- **D-03 — human control:** исходный сценарий — перехват опасной операции, понятное объяснение причины и подтверждение пользователя. Классификация адресуется реальному tool/route и аргументам, а не только тексту запроса.
- **D-04 — Jev research:** Jev и аналоги исследованы как варианты. Покупка сервиса, передача BIM-данных и обязательная зависимость от Jev не разрешены. Конкретный адаптер и модель не выбраны (см. D-21 — отложен).

### Канал подтверждения (2026-10-25)

- **D-05 — elicitation через неизменённый HermesFork:** человек подтверждает операцию в окне клиента через стандартную MCP elicitation (form mode). Целевой клиент — `12_GenproAI_HermesFork`: клиент на `mcp==2.0.0`, обработчик `elicitation/create` в `tools/mcp_tool.py` (~2142) направляет запрос в общую очередь подтверждений Hermes (Desktop, а также Telegram/Slack в gateway-режиме). Ответ приходит серверу от клиента, минуя модель. Клиент, не заявивший elicitation capability, отказ, cancel, ошибка → защищённая операция **блокируется**; согласие агента в тексте, tool `approve` или аргумент `approved=true` не принимаются. Локальное Windows-окно и TaskDialog в Revit рассмотрены и не выбраны (Windows-окно невидимо из gateway; TaskDialog блокирует UI-поток и Routes-сервер на время ожидания).
- **D-06 — обновление MCP SDK входит в фазу:** закреплённый `mcp` 1.9.0 (`pyproject.toml`, `uv.lock`) elicitation не содержит вообще (проверено: в `.venv/Lib/site-packages/mcp/` нет ни одного вхождения `elicit`). Обновление до версии с server-side elicitation — часть фазы. Целевую версию (2.x, как у клиента, или последнюю 1.x) выбирает исследование. Обязательная регрессия: регистрация FastMCP и `audit.install_audited_tools` (Phase 6 D-05: обёртка через `functools.wraps` и интроспекция `func_metadata` должны сохранить схему параметров и `user_request`), чистый stdout под stdio (`tests/unit/test_audit_stdio.py`), cold-start gate `tests/test_init_latency.py` (<2.0 s), транспорты `--sse`, `--streamable-http`, `--combined`, полный `uv run pytest tests/unit`. — **Reversibility:** costly — затрагивает каждый tool registrar, обёртку аудита и payload парка; откат означает отказ от канала подтверждения.
- **D-07 — таймаут ожидания 5 минут**, значение задаётся в политике. Ожидание идёт **до** захвата lock в `bridge.py` и до отправки в Revit: Revit и другие вызовы этого процесса не блокируются, транзакция не держится. По истечении срока возвращается отказ с понятной причиной (`expired`), и ассистент может запросить подтверждение заново (новое окно).
- **D-08 — одно «Да» = одна операция.** Любой положительный ответ клиента, включая «на сессию» и «всегда», сервер трактует как разрешение ровно этого вызова с этими нормализованными аргументами. Coalescing и adopted followers в очереди Hermes (`_await_gateway_decision`) не расширяют охват: одноразовость гарантирует наш enforcement. Список элементов в одном вызове инструмента — одно окно. «Окно доверия на N минут» и подтверждение плана из N операций рассмотрены и не выбраны.
- **D-09 — содержимое окна:** инструмент, модель (title и путь документа по Phase 2), нормализованные аргументы, reason codes правила **плюс быстрый точный read-only подсчёт из Revit** там, где факт получается дёшево и точно: параметр instance или type, число экземпляров затронутого типа, текущее значение → новое, число элементов. Что точно узнать нельзя (каскад удаления, охват произвольного кода), показывается как «неизвестно», а не оценкой. Для подсчёта нужен новый read-only маршрут (или маршруты) в расширении; он только читает, транзакций не открывает. Пробное удаление с откатом на рабочей модели не используется. Язык окна — русский.

### Что подтверждать — базовая политика (2026-10-25)

Каждый из 59 инструментов и каждый маршрут классифицирован явно; неизвестный путь не получает allow (критерий 2).

- **D-10 — запись параметров (`set_parameter`, `modify_element`):** confirm, если выполняется хоть одно из условий: параметр типа (затронет все экземпляры); затронуто больше одного элемента; перезаписывается непустое значение; факт установить не удалось. Заполнение **пустого** параметра **одного** экземпляра — allow. Факты берутся из preflight по D-09; при отсутствии факта — confirm.
- **D-11 — всегда confirm:** `delete_elements`, `transform_elements` (move/copy/rotate/mirror), фактические пути создания и привязки общих параметров (включая скрытый `add_shared` в `revit_mcp/placement.py`), `edit_family`, `load_family`.
- **D-12 — `execute_revit_code`: confirm на каждый вызов.** В окне — код (или начало + полная длина + SHA-256, по аналогии с Phase 6 D-04) и явное предупреждение «произвольный код, безопасность содержимого не проверяется». Путь не отключается (Phase 2 D-15 сохраняется); подтверждение не выдаётся за проверку содержимого.
- **D-22 — общие параметры только из ФОП компании:** создание общего параметра в модели (и в семействе) разрешено **только** из файла общих параметров `\\Srv-dfs\BIM\01_Ресурсы плагинов\2_Shared_parameters\ГП_ФОП2025.txt`. Параметр, которого нет в этом файле (по GUID и имени), или источник из любого другого файла → **deny** с причиной; из этого файла → confirm (D-11). Путь хранится в политике (оператор может его сменить, D-15), а не зашит в код. Недоступность файла (share, права) → deny, а не allow. Путь содержит кириллицу и является UNC — сравнение и чтение без потери non-ASCII. Соответствие проверяется по фактическому `ExternalDefinition`/GUID, а не по тексту аргумента от модели; где именно (CPython по файлу или Revit-сторона при загрузке) — решает исследование.
- **D-23 — переопределение параметров = confirm:** любое изменение определения или привязки существующего параметра проекта/общего параметра: привязка к категориям (добавить или убрать категорию), смена instance ↔ type binding, смена группы параметра (`GroupTypeId` / группирование в свойствах), «значения могут различаться по экземплярам группы» (varies across group instances), смена/удаление binding, переименование и т. п. Перечень не закрыт: планировщик составляет полный список таких операций Revit API. Если типизированного инструмента для операции сейчас нет, она доступна только через `execute_revit_code` (уже confirm, D-12) или `edit_family` (confirm, D-11). Нужен ли новый typed tool — решается при планировании, существующий API не выдумывать.
- **D-13 — явно allow:** все инструменты создания (`create_*`, `place_family`, `tag_elements`, `tag_walls`, `create_dimensions`, `create_schedule`, `create_sheet`, `create_view` и т. п.); `save_document`, `link_file`, `export_document`, `export_ifc`, `export_room_data`, `open_model`, `color_splash`, `clear_colors`, `activate_document`, `set_active_view`; все чтения. Пороги для массового создания не вводятся.

### Политика: файл и владелец (2026-10-25)

- **D-14 — два слоя:** базовая политика лежит в репозитории, едет в payload и покрыта unit-тестами (всегда валидна в релизе). Необязательный **файл оператора** лежит на share рядом с `MCP_SECRET_FILE` (`deploy/config.cmd`) и действует на весь парк; сервер подхватывает его изменения на лету (hot reload, атомарно). Локального пользовательского слоя нет: на станции пользователь политику не меняет.
- **D-15 — оператор может менять любые правила, в том числе ослаблять** (например, снять подтверждение удаления). Неснимаемого минимума в коде нет. **Следствие для планирования:** формулировку ROADMAP-критерия 2 («подтверждение охватывает перезапись параметров, удаление, трансформации…») нужно поправить: это поведение базовой политики по умолчанию, а не неизменяемая гарантия. Невалидный, недоступный или частично прочитанный файл оператора ничего не ослабляет (D-17). — **Reversibility:** reversible — неснимаемый минимум можно добавить позже, не меняя формат.
- **D-16 — формат TOML** (stdlib `tomllib`, CPython ≥3.11: без новой зависимости в payload, поддерживает комментарии к каждому правилу). Политика валидируется как данные и не исполняет выражений. Схема, ключи и версия/хеш политики — на усмотрение планировщика.
- **D-17 — невалидный файл оператора:** при старте без ранее принятой версии действует базовая политика из payload; `get_revit_status` честно сообщает «файл оператора не принят: причина», источник (`base` / `operator`) и версию/хеш активной политики. Невалидное обновление на лету сохраняет последнюю валидную версию и выводит диагностику. Ожидающее разрешение не переживает применённую смену политики (критерий 4). Если невалидна сама базовая политика (не должно случиться в релизе), защищённые операции блокируются.

### Revit-сторона и выкладка (2026-10-25)

- **D-18 — расширение требует одноразовое разрешение на каждой мутации.** Каждый закрытый не-GET маршрут (тот же набор, что закрыт Phase 5 gate; семь открытых POST-чтений и GET не затрагиваются) отклоняет запрос без действительного разрешения **до** эффекта. Для allow-операций разрешение выдаёт сервер сам, для confirm — только после «Да». Политика живёт только на CPython-стороне; расширение проверяет одно единое правило и не знает классификацию, поэтому файл оператора не требует релиза расширения. Разрешение передаётся в конверте `_mcp` (как секрет и `call_id`, Phase 5/6), привязано к нормализованным аргументам, процессу/документу (Phase 2 `session_token`), версии политики, сроку и nonce; потребляется атомарно, повтор отклоняется. Проверка встраивается в существующий preamble `gate_or_response` по образцу Phase 5 D-01 (явно в маршруте, тест-сторож, без общей обёртки в `startup.py`). Известное ограничение, которое фаза записывает, а не скрывает: процесс или агент, который может прочитать файл секрета, способен сам выпустить разрешение; это барьер для LAN-вызывающих и случайного curl, а не изоляция от агента с теми же правами ОС. Конкретная схема (HMAC от секрета или иная) и место реестра потребления — предмет исследования. — **Reversibility:** one-way — после публикации ext каждая мутация без разрешения у всего парка отклоняется; старые payload перестают мутировать.
- **D-19 — порядок выкладки как R3 (Phase 5 D-05):** сначала payload (сервер с подтверждениями и разрешениями), затем, после плановой перезагрузки, ext. Предусловие, как Phase 5 D-06: доказать, что ext, стоящий на share в этот момент, безвредно игнорирует новый ключ разрешения в `_mcp` на каждом POST-маршруте. Смешанное состояние «новое ext + старый payload» → строгий отказ с понятным текстом «обновите RevitMCP и перезапустите сессию ассистента», по образцу Phase 5 D-07. Атомарная публикация ext и `ext-previous\` (Phase 5 D-09/D-10) переиспользуются.
- **D-20 — живая приёмка только в Hermes Desktop** на рабочем ПК в контуре компании с доступом к серверу, на одноразовой модели, после полного перезапуска Revit. Её запускает пользователь. Сценарии: «Да», «Нет», таймаут, повторная доставка, изменённые аргументы, прямой curl без разрешения. Канал Telegram/gateway вживую **не** проверяется и записывается как недоказанный, а не как работающий.
- **D-21 — Jev отложен целиком:** ни адаптера, ни точки расширения, ни передачи данных в этой фазе. Phase 7 работает на детерминированных правилах.

### Ограничения дизайна для планирования (из исследования 2026-10-16, уточнены решениями выше)

Механизмы требуют проверки; ничего здесь не считается реализованным или измеренным.

- Основная логика политики — CPython; Revit extension — тонкий поставщик фактов (D-09) и обязательная проверка разрешения перед эффектом (D-18). Оба рантайма находятся в этом репозитории.
- Решения `allow / confirm / deny`; неизвестная операция не разрешается по умолчанию. `readOnlyHint` и рассказ агента не заменяют локальную классификацию.
- Разрешение связано с окончательными аргументами, процессом/документом, версией политики, сроком и идентификатором операции. Подмена, повтор, смена документа/политики и restart не должны использовать старое разрешение. Состояние проверяется непосредственно до эффекта; ожидание человека не держит транзакцию Revit (D-07).
- Threat model: общий секрет аутентифицирует отправителя, но не доказывает согласие человека. Локальный агент с произвольным ОС-доступом и теми же правами может читать/менять файлы (секрет, политику оператора на share при наличии прав записи); политика и подпись сами по себе не создают изоляцию.
- Атомарное потребление одноразового разрешения должно охватывать конкуренцию нескольких MCP-процессов и повторную доставку (Hermes может повторить вызов после reconnect, `tools/mcp_tool.py` ~5927–5946). Подпись без проверки использования не защищает от replay. Минимальный store и поведение после crash — исследовать.
- Не повторять потенциально выполненную мутацию после неизвестного результата. Не обещать exactly-once при произвольном новом tool call без протокола.
- Объяснение строится из фактов и reason codes; неизвестный охват показывается как неизвестный.
- Сохранять честные исходы Phase 4/6. `approved` не означает `committed`; различать denied / expired / committed / rolled_back / partial / unknown, писать их в аудит Phase 6 и не добавлять неявные error-сигналы в `format_response`.

### Existing Decisions That Remain Binding

- Phase 2 D-15: оба execute-code пути остаются включёнными как trusted arbitrary-code exceptions. Не отключать их без нового решения пользователя. Не обещать sandbox или confinement произвольного кода с doc/DB/revit/clr/System/builtins. Подтверждение каждого вызова (D-12) не меняет этого статуса.
- Одноразовое подтверждение execute не доказывает безопасность его содержимого. Обход политики через произвольный код, ОС-доступ и cross-process overlap (999.1) фиксируется явно (критерий 6).
- Один общий MCP entry `revit`, выбор процесса/документа по Phase 2. Не вводить дополнительные записи сервера или отдельную конкурирующую identity registry.
- Все изменения extension проверять live только после полного закрытия/открытия Revit, не Reload. Сначала offline-тесты; live bench — отдельный согласованный scope (D-20).
- Сохранять `text/plain` + `parse_request_data`, IronPython-compatible syntax, транзакции/`suppress_warnings`/`commit_and_report` и исключение Save/SaveAs, штатные ElementId helpers, регистрацию по соглашению и `tests/unit/tool_manifest.txt`.

### Claude's Discretion

- Схема TOML (ключи, группировка инструментов, reason codes), способ hot reload (polling mtime или иное), версия/хеш политики.
- Точная форма payload elicitation (поля формы, текст) в пределах D-09.
- Конкретная схема разрешения и реестра потребления в пределах D-18 — по итогам исследования.
- Сколько read-only preflight-маршрутов нужно для D-09 и как они распределены по доменам (без импорта одного `revit_mcp/` домена из другого).

### Deferred Ideas (OUT OF SCOPE)

### Отдельная быстрая задача (`/gsd-quick`), не Phase 7
- **Умолчания `open_model` для моделей с совместной работой:** по умолчанию открывать с созданием локальной копии (сейчас умолчание `detach="preserve"`, `revit_mcp/worksharing.py:465`, `tools/worksharing_tools.py:207`). Если локальная копия уже существует — опция Revit «Добавить штамп даты и времени к существующей копии»: существующая копия переименовывается с датой и временем, новая создаётся рядом. Сейчас `_make_local_copy` (`revit_mcp/worksharing.py:197-199`) при `overwrite=True` **удаляет** существующую копию, теряя несинхронизированную работу. Рабочие наборы: все пользовательские закрыты (как сейчас); если открыть со всеми закрытыми не удаётся — открыть набор, имя которого содержит «Оси и уровни» (без учёта регистра; точное имя может отличаться). Изменение `revit_mcp/` — полный перезапуск Revit для live-проверки.
- Скиллы диагностики и тестирования плагинов, открывающие модели с отсоединением по умолчанию, — вне этого репозитория (out of scope).

### Not Authorized / Out of Scope
- Изменения Hermes Fork или требование установить специальный Hermes safety plugin.
- Jev: адаптер, точка расширения, внешний API, передача закрытых моделей/параметров/кода (D-21).
- Универсальный policy framework, OPA service, новый отдельный gateway или UI-редактор правил.
- Локальное Windows-окно / TaskDialog как канал подтверждения (D-05); «окно доверия на N минут» и подтверждение плана (D-08).
- Живая проверка канала Telegram/gateway (D-20).
- Скрытое отключение execute-code, ограничение существующих возможностей без согласования и заявления о полной защите машины от агента с теми же ОС-правами.
- Запуск реализации, Revit, live mutations, deployment, commit/push по одному факту создания этого контекста.
</user_constraints>

## Project Constraints (from CLAUDE.md)

Extracted directives the planner must treat as locked (authority equal to CONTEXT.md). Sources: `C:\Users\Admin\.claude\CLAUDE.md` and `./CLAUDE.md`.

- **Two-Runtime Rule.** `main.py`, `bridge.py`, `audit.py`, `tools/`, `tests/` are CPython >=3.11 (dev pin 3.13), async/f-strings allowed. `startup.py` and `revit_mcp/` are IronPython 3 at the Python 3.4 language level: `"{}".format(x)`, **no f-strings**, no `async`, no `pathlib`, no `typing`, no `secrets` (`scripts/conventions.py` `PY3_ONLY_MODULES` lists `"pathlib", "dataclasses", "typing", "asyncio", "enum", "secrets", ...`), relative sibling imports only (`from .utils import ...`), encoding cookie on line 1. New Revit-side helpers therefore must be written for the intersection of both runtimes.
- **Domain isolation:** never import one `revit_mcp/` domain from another (`tests/unit/test_registration.py`, `test_phase2_inventory.py::test_no_revit_mcp_module_imports_a_domain_module_in_any_form_or_scope`).
- **Every non-GET route opens with `gate_refusal = gate_or_response(request)`** before the document guard; the shape (one-argument call, `is not None` test, `return` the refusal) is pinned by AST in `tests/unit/test_phase5_gate_wiring.py`. The seven open POST reads call `strip_envelope(request)` and are listed in `trust.OPEN_POST_READ_ROUTES`, mirrored in `scripts/conventions.py`, `audit.py` and the literal `D02_OPEN`. No bypass flag may exist in production code.
- **Every document mutation runs in a transaction; `suppress_warnings(t)` right after `t.Start()`; commit only via `commit_and_report`; replies via `finalize_outcome`.** Not changed by this phase, but any new Revit code that writes must follow it (the preflight routes only read).
- **POST bodies are `text/plain` and parsed with `parse_request_data()`.** Never `json.loads(request.data)`.
- **Route handlers never raise**; status conventions 400/404/500/503; new refusal statuses must be added deliberately (this research proposes 403 for permit refusals).
- **A dict is an error only with a truthy `error` key or a status in error/failed/failure/exception.** Do not add implicit error signals to `format_response`; `partial` is not an error, `rolled_back` (409) is.
- **Tool functions always return `str` via `format_response`.** The transport coerces exceptions; a bridge result may be dict or str.
- **Never `print()` / `sys.stdout` / `StreamHandler` in `main.py`, `bridge.py`, `audit.py`** (stdio protocol stream); `tests/unit/test_audit_stdio.py` enforces it. New root modules (`policy.py`, `permit.py`, ...) inherit the rule.
- **Audit invariant (Phase 6):** outcome comes from provenance + reply body, never `format_response`; secret redacted in one place (`audit.redact_text`); a writer failure never changes a tool result.
- **All dimensions are millimeters;** Revit-sourced names go through `sanitize_string()`.
- **Tool docstrings are the API contract** (tests pin sentences). Adding confirmation wording to docstrings or `SERVER_INSTRUCTIONS` requires updating the pinning tests.
- **Commands:** `uv sync` / `uv run pytest tests/unit` before every commit; `uv.lock` is the source of truth; `requirements.txt` is a stale mirror. No lint/CI config.
- **Registration by convention:** a capability is 2 files plus `tests/unit/tool_manifest.txt`. This phase adds **no MCP tool**, so the manifest stays at 59 names (preflight routes are bridge-internal).
- **After editing `revit_mcp/` close and reopen Revit fully; never rely on pyRevit Reload.** The extension directory is a junction to the repo (no staging buffer).
- **Payload ships root modules by explicit `copy /y` lines** in `deploy/build-payload.cmd`; `tests/unit/test_payload_ships_root_modules.py` fails when a root module reachable from `main.py` is not copied.
- **Release checkpoints:** at phase close read `.planning/RELEASES.md` and offer R5 via `AskUserQuestion`; never run `publish-extension.cmd`, `build-payload.cmd`, push or tag. Obsidian vault and session-save rules apply to session wrap-up, not to this research.
- **User global policy:** worker delegation (DSH) is optional; this research did not delegate. Never touch Hermes Fork (read-only).

<phase_requirements>
## Phase Requirements

ROADMAP lists `**Requirements**: TBD`; no IDs are assigned. The set below is **proposed** (family `SAFE`), derived from the 7 success criteria (SC) and D-05..D-23. The planner formalizes them in `REQUIREMENTS.md` and `ROADMAP.md` (Traceability table). Full wording and the SC/D mapping are in the section "Proposed Requirement IDs".

| ID | Description | Research Support |
|----|-------------|------------------|
| SAFE-01 | Confirm-class operation never runs without a positive client answer over MCP elicitation; agent text and `approved=true` are ignored | Elicitation round-trip experiments (Gate 1), Hermes handler read (Gate 2) |
| SAFE-02 | No capability / decline / cancel / error / timeout all block, with distinct reasons | Experiment table in "Elicitation behaviour" |
| SAFE-03 | Human wait happens before the bridge lock and holds no transaction; timeout from policy (default 300 s) | `bridge.py` `_dispatch_core` read; Pattern 2 |
| SAFE-04 | One "Yes" authorizes exactly one call; session/always answers do not widen; concurrent windows do not coalesce | Hermes coalescing + FIFO findings; unique code per window; per-process window lock |
| SAFE-05 | Russian window with tool, document, normalized args, reason codes, exact read-only facts, "unknown" for the unknowable | Preflight design (Gate 4) |
| SAFE-06 | All 59 tools and 56+ routes classified in the base policy; unclassified route = deny; guard test fails on a missing entry | Full classification tables (Gate 5) |
| SAFE-07 | Base policy encodes D-10, D-11, D-12, D-13, D-23 defaults | Classification + conditional rules |
| SAFE-08 | Shared parameters only from the company FOP file by GUID+name; unreadable FOP = deny | Gate 6 |
| SAFE-09 | TOML policy, validated as data; base in payload, operator file on share, atomic hot reload, version/hash | Gate 8 |
| SAFE-10 | Bad/missing/partial operator policy never weakens; base-invalid blocks protected ops; status reports source/version/diagnostics | Gate 8, loader tests |
| SAFE-11 | One-time HMAC permit bound to route, exact body bytes, process session token, policy hash, expiry, nonce | Gate 3 |
| SAFE-12 | Every gated Revit route refuses without a valid permit before any effect; permit consumed atomically in `gate_or_response`; sentinel test | Gate 3, Pattern 3 |
| SAFE-13 | Approval does not survive a policy change or changed facts between approval and send | Pattern 2 steps 7-8 |
| SAFE-14 | Payload-first rollout; new ext + old payload refuses with clear text; old ext ignores the new key; status advertises permit protocol | Gate 3 (mixed rollout) |
| SAFE-15 | Audit/replies distinguish denied, expired, rejected_permit, success(committed), rolled_back, partial, unknown; no new implicit error signals | Gate 9 |
| SAFE-16 | No automatic retry after unknown; one permit cannot execute twice; client redelivery creates a new window | Gate 3, pitfalls |
| SAFE-17 | `execute_revit_code` confirm every call with code/length/SHA-256 and the arbitrary-code warning; paths stay trusted | D-12 |
| SAFE-18 | Documented bypass limits (arbitrary code, OS access, readable secret, 999.1, `load_family` content) | Threat model |
| SAFE-19 | MCP SDK upgrade without regression (FastMCP, audit wrapper, stdout purity, 3 transports, cold start, payload import) | Gate 1 evidence |
| SAFE-20 | Offline negative/concurrency suite plus separately authorized live bench (Hermes Desktop, full Revit restart) | Validation Architecture |
| SAFE-21 | ROADMAP SC2 reworded to "base-policy default, not an immutable guarantee" (D-15) | CONTEXT D-15 |
</phase_requirements>

## Summary

The phase is implementable with a small number of new moving parts, all of which were proven or measured in throwaway experiments this session. The single biggest hidden risk is not the permit protocol but the SDK upgrade: **bumping `mcp` to any elicitation-capable 1.x or to 2.x adds an unconditional `pywin32` import on Windows, and with the exact payload recipe (`uv pip install --target libs` against pyRevit's embeddable CPython 3.12.3) `import mcp` fails with `ModuleNotFoundError: No module named 'pywintypes'`.** Putting `libs\win32`, `libs\win32\lib` and `libs\pythonwin` on `sys.path` in `deploy/server.py`, `deploy/gate.py` and `deploy/warm.py` fixes it (reproduced). With that shim and a one-line change in `audit.install_audited_tools` (default `structured_output=False`, otherwise every tool gains an `outputSchema` and `FastMCP.call_tool` changes its return shape), **mcp 1.30.0 passes the entire existing unit suite unchanged (6361 passed, 3 skipped, identical to the 1.9.0 baseline), keeps `user_request` in all 59 tool schemas, serves stdio/SSE/streamable-HTTP/combined, and cold-starts in about 1.05 s versus 0.85 s for 1.9.0 in the real payload layout.**

Elicitation works as designed against an `mcp==2.0.0` client driving a handler shaped like Hermes' (accept returns `content={}`, decline, cancel, handler exception, no capability, server-side timeout), and the Cyrillic window text round-trips intact. Two properties of the unchanged Hermes handler shape the design: (1) it never renders form fields and always answers `accept` with **empty** content, so the server must use an empty schema and rely on `action` only; (2) in gateway sessions it coalesces concurrent prompts with identical text and `/approve all` resolves every pending prompt, so each window must carry a unique code and windows must be serialized per MCP process. A server-side timeout does not dismiss the client prompt; a late answer is ignored by the SDK (verified) and can authorize nothing because the permit is minted only inside the awaiting code path. Under the current `main.py` HTTP configuration (`stateless_http=True, json_response=True`) `check_client_capability` is `False` and an un-guarded elicit hangs until the timeout (verified): confirm-class operations must be blocked there by the capability check.

For the permit, the robust design is: HMAC-SHA256 (key derived from the shared secret) over `route | sha256(exact body text without the envelope) | session_token | exp | nonce | policy_hash`, carried as `_mcp.permit`, verified and consumed inside `gate_or_response` against an in-memory nonce registry in the Revit process. **Do not canonicalize JSON on both sides:** IronPython 3.4.2's `repr(0.1)` is `0.10000000000000001` and `repr(1e16)` is `10000000000000000.0` (executed against pyRevit's `IPY342` engine this session), so any float in tool arguments would break a re-serialized hash. Hash the **wire text** instead: the sender emits the envelope as the first member and the arguments text as the remainder; the receiver splits with `json.JSONDecoder().raw_decode` and hashes the remainder verbatim. Preflight facts come from three new open-read routes colocated with the domains whose resolution they mirror. The D-22 check belongs on the CPython side (read the FOP file there, compare GUID+name of what the Revit side reports it would add). Policy is TOML with a closed vocabulary of built-in checks, loaded with `tomllib` in a worker thread with a timeout (never touch the UNC share on the event loop or at import).

**Primary recommendation:** Upgrade to `mcp==1.30.0` (not 2.x) with the three-file `pywin32` path shim and `structured_output=False`, hook the policy engine at the single choke point `bridge.revit_post` (fail-closed when no engine is installed), use stateless HMAC permits over the exact body text consumed from a Revit-side in-memory registry inside `gate_or_response`, and ship the base policy as a TOML data file copied by `build-payload.cmd`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Classification of tool/route into allow/confirm/deny, reason codes | MCP server (CPython `policy.py`) | Base policy file in payload | D-18: policy lives only on CPython; extension knows one rule |
| Human confirmation prompt | MCP client (HermesFork, unchanged) | MCP server (initiates `elicitation/create`) | D-05; server only asks and interprets `action` |
| Exact read-only facts for the window (instance/type, counts, current value, FOP resolution) | Revit extension (new preflight routes) | MCP server (renders, compares) | Only Revit knows the model; routes read only |
| FOP file (`ГП_ФОП2025.txt`) match | MCP server (reads file in a worker thread) | Revit extension (reports what it would add: GUID, name, source file) | Share access and parsing are testable on CPython; Revit reports facts |
| Permit minting | MCP server (`permit.py`) | — | Needs policy decision, secret, resolved target, final body |
| Permit verification and single-use consumption | Revit extension (`permits.py` + `gate_or_response`) | — | Must reject direct HTTP before any effect; registry survives MCP restarts and covers many MCP processes |
| Serialization lock, honest outcomes, lock-free human wait | MCP server (`bridge.py`) | — | Wait occurs before `_dispatch_core` takes the per-incarnation lock |
| Audit of denied/expired/approved decisions and true outcomes | MCP server (`audit.py`) | Revit reply body (`outcome` block) | Phase 6 owns the log; Revit never writes it |
| Policy distribution, hot reload, status | MCP server (loader) | Share (`operator` TOML), payload (`base` TOML), `get_revit_status` | D-14, D-17 |
| Payload/SDK packaging (pywin32 shim) | Deploy scripts (`deploy/server.py`, `gate.py`, `warm.py`, `build-payload.cmd`) | — | Embeddable CPython ignores `.pth`; verified failure and fix |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp` (official MCP Python SDK) | **1.30.0** (2026-09-07, latest 1.x; target `mcp[cli]>=1.30,<2`) | `FastMCP`, `Context.session.elicit_form`, `check_client_capability` | Elicitation exists since 1.10.0 (`Context.elicit` in `fastmcp/server.py` of the 1.10.0 wheel, read) and is stable through 1.30.0; the 1.x line keeps `FastMCP`, `mcp.settings.host/port`, `ClientSession` used by `gate.py`/tests. `[VERIFIED: pip index versions mcp; wheel mcp-1.30.0 and mcp-1.10.0 inspected; PyPI JSON]` |
| `tomllib` | stdlib (>=3.11; fleet engine is CPython 3.12.3) | Parse base and operator policy | D-16; strict (duplicate key and BOM both raise `TOMLDecodeError`, tested); no new dependency `[VERIFIED: experiment]` |
| `hashlib`, `hmac`, `json`, `secrets`/`os.urandom`, `threading`, `asyncio.timeout` | stdlib | Permit MAC, nonce, hot reload, human-wait timeout | CPython side may use `hmac`; **Revit side must use a hand-rolled HMAC over `hashlib`** (hashlib verified live in pyRevit's engine, `hmac.compare_digest` present but unused, `hmac.new` unverified): parity-tested against the stdlib on RFC 4231 style vectors `[VERIFIED: revit_mcp/trust.py:179-190 docstring; experiment: hand-rolled HMAC equals stdlib on 3 vectors]` |
| `httpx`, `anyio`, `uvicorn`, `pydantic` | already pinned by the repo / pulled by `mcp` | unchanged | `pyproject.toml` lines 8-15 `[VERIFIED: Read]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pywin32` | transitive of `mcp>=1.11` on win32 (`>=310`/`>=311`) | Imported unconditionally by `mcp.os.win32.utilities` at `import mcp` | Must be on `sys.path` in the payload (shim below). Not used by repo code. |
| `jsonschema`, `pyjwt[crypto]` (`cryptography`, `cffi`, `pycparser`), `referencing`, `rpds-py`, `attrs`, `annotated-doc`, `jsonschema-specifications` | transitive of `mcp` 1.30.0 | New wheels in `libs\` (diff of `uv pip compile` against `uv export` of the current lock: `+annotated-doc +attrs +cffi +cryptography +jsonschema +jsonschema-specifications +pycparser +pyjwt +pywin32 +referencing +rpds-py`, `-sniffio`) | Accepted cost of D-06; payload grows by native wheels `[VERIFIED: experiment]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `mcp` 1.30.0 | `mcp` 2.3.0 (matches client generation) | 2.x renames `FastMCP`→`MCPServer` (`from mcp.server.mcpserver import MCPServer, Context`), removes `host/port/stateless_http/json_response` from the constructor and `mcp.settings.host/port` (used by `main.py` `run_combined_async`), replaces `ClientSession`+transport layering by `Client` (used by `deploy/gate.py`, `tests/test_init_latency.py`, unit tests), moves SDK HTTP to `httpx2`, needs `pydantic>=2.12`, still needs `pywin32>=311`. Larger blast radius, no gain for server-side elicitation. `[CITED: https://py.sdk.modelcontextprotocol.io/migration/; wheel mcp-2.3.0 METADATA read]` Not run end to end. |
| `mcp` 1.30.0 | `mcp` 1.10.1 (first elicitation release line, no `pywin32` dependency: `Requires-Dist` of the 1.10.0 wheel has none) | Avoids the deploy shim but freezes a 16-month-old SDK in a security-focused phase. Keep only as a fallback if the shim fails the live bench. `[VERIFIED: wheel 1.10.0 METADATA grep]` |
| `Context.elicit(message, PydanticModel)` | `ctx.session.elicit_form(message, schema_dict, ctx.request_id)` | `ctx.elicit` raises `ValueError("Unexpected elicitation action")` if an accept arrives with `content=None` and validates fields; Hermes returns `content={}`. The low-level call returns the raw `ElicitResult` (`action`, `content`) and positional arguments survive the 1.x→2.x `requestedSchema`→`requested_schema` rename. Prefer the low-level call. `[VERIFIED: mcp/server/elicitation.py:105-142 of 1.30.0; experiment]` |
| Re-serialize JSON on both sides for the args hash | Hash the exact body text | IronPython 3.4.2 float repr differs from CPython (below); text hashing needs no parity |
| Local policy via OPA/ContextForge/etc. | none | Out of scope (D-02, 07-RESEARCH-NOTES) |

**Installation (planner; research did not modify `pyproject.toml`/`uv.lock`):**
```bash
# pyproject.toml: "mcp[cli]>=1.30.0,<2"   then re-lock with uv; review the diff of uv.lock
uv lock && uv sync --group dev
uv run pytest tests/unit -q
```

**Version verification (run this session):**
```bash
python -m pip index versions mcp          # latest 2.3.0; 1.x latest 1.30.0; 2.0.0 and 2.0.1 exist
# release dates from PyPI JSON: 1.9.0 2025-05-15, 1.10.0 2025-06-26, 1.30.0 2026-09-07
```

## Package Legitimacy Audit

`gsd-tools query package-legitimacy check --ecosystem pypi ...` returned **SUS for every package**, but only for registry-metadata reasons (`unknown-downloads` because the PyPI seam has no weekly-download source, `too-new` because the latest release is within the seam's window, `no-repository` where PyPI metadata lacks a URL). None is `SLOP` (all exist, none deprecated, `postinstall` null). `mcp` is the official SDK (`repoUrl` modelcontextprotocol.io; wheel contents match the GitHub project). The seam verdicts are recorded as-is; they are not a finding about the packages.

| Package | Registry | Latest release seen | Source Repo | Seam verdict (reasons) | Disposition |
|---------|----------|---------------------|-------------|------------------------|-------------|
| mcp | PyPI | 2026-10-02 (2.x line); target 1.30.0 (2026-09-07) | modelcontextprotocol.io | SUS (too-new, unknown-downloads) | Existing dependency, version bump. Planner adds `checkpoint:human-verify` before the bump (also required by D-06 "costly"). |
| jsonschema | PyPI | 2026-01-07 | github.com/python-jsonschema/jsonschema | SUS (unknown-downloads) | Transitive of mcp; verify in lock review |
| pyjwt | PyPI | 2026-09-28 | github.com/jpadilla/pyjwt | SUS (too-new, unknown-downloads) | Transitive of mcp |
| cryptography | PyPI | 2026-09-30 | none in metadata | SUS (too-new, unknown-downloads, no-repository) | Transitive of mcp (pyjwt[crypto]) |
| pywin32 | PyPI | 2026-06-04 | github.com/mhammond/pywin32 | SUS (unknown-downloads) | Transitive; needs the sys.path shim |
| referencing | PyPI | 2025-10-13 | github.com/python-jsonschema/referencing | SUS (unknown-downloads) | Transitive |
| rpds-py | PyPI | 2026-10-04 | github.com/crate-py/rpds | SUS (too-new, unknown-downloads) | Transitive |
| attrs | PyPI | 2026-03-19 | none in metadata | SUS (unknown-downloads, no-repository) | Transitive |
| cffi | PyPI | 2026-08-03 | none in metadata | SUS (unknown-downloads, no-repository) | Transitive |
| pycparser | PyPI | 2026-10-22 | github.com/eliben/pycparser | SUS (too-new, unknown-downloads) | Transitive |
| annotated-doc | PyPI | 2026-07-28 | github.com/fastapi/annotated-doc | SUS (unknown-downloads) | Transitive |
| jsonschema-specifications | PyPI | 2025-09-08 | github.com/python-jsonschema/jsonschema-specifications | SUS (unknown-downloads) | Transitive |

**Packages removed due to SLOP verdict:** none.
**Packages flagged SUS:** all of the above (metadata reasons only). The planner inserts one `checkpoint:human-verify` before the dependency bump (reviewing the `uv.lock` diff), not one per transitive package. `npm`-style postinstall check is not applicable (PyPI wheels; `--only-binary=:all:` installs worked in scratch venvs).

## Architecture Patterns

### System Architecture Diagram

```
 Assistant (Hermes) --tools/call--> main.py FastMCP --(audit wrapper: call_id, user_request)--> tool fn (tools/*.py)
                                                                                     |
                                                                                     v   data = tool-built body
                                                                          bridge.revit_post(endpoint, data, ctx, target)
                                                                                     |
                      open POST read? ------yes------------------------------------>|----------------------------------+
                                                                                     | no                               |
                                                                                     v                                  |
                                            resolve target ONCE (selector -> {host,port,pid,session_token})             |
                                                                                     |                                  |
                                            policy engine (policy.py)  <--hot reload (thread, mtime+sha, TTL 2 s)       |
                                              rule = policy.rule_for(route)  [unknown route => DENY]                    |
                                                  | allow                 | check / confirm            | deny           |
                                                  |                       v                            v                |
                                                  |        preflight (POST /*_preflight/, open read, takes lock briefly)|
                                                  |        facts -> reason codes -> allow | confirm | deny              |
                                                  |                       | confirm                                     |
                                                  |             window lock (1 per MCP process)  -- NO bridge lock held |
                                                  |             session.elicit_form(RU message, empty schema)           |
                                                  |             | accept | decline | cancel | timeout 300 s | no cap    |
                                                  |             v        v           v         v              v         |
                                                  |       re-check policy hash + re-run preflight, compare facts digest |
                                                  v             v                                                       |
                                       mint permit (HMAC, TTL 60 s, nonce)                         record_decision(denied/expired) --> refusal text (not-sent)
                                                  |
                                                  v
                          body text = {"_mcp":{secret,call_id,permit}, <args text>}   (envelope FIRST, args hash = sha256(args text))
                                                  |
                                      _dispatch -> lock -> handshake (session token) -> POST text/plain  ===>  Revit / pyRevit Routes
                                                                                                                   |
                                         handler: gate_or_response(request): secret -> integrity -> PERMIT (route, args hash, session, exp, MAC,
                                                  nonce consumed atomically) -> document guard -> transaction -> commit_and_report
                                                                                                                   |
                                         reply (outcome block) <==  audit.record_call (success|partial|failed|rolled_back|unknown|rejected_permit)
```

### Recommended Project Structure (new and changed files)

```
policy.py                    # NEW root module (CPython): load/validate/merge TOML, hot reload, decision engine, checks, messages
permit.py                    # NEW root module (CPython): derive key, mint permit, build wire text (envelope first), HMAC
policy.base.toml             # NEW data file shipped in payload: base policy covering all 59 tools / 56+ routes
bridge.py                    # CHANGED: revit_post hook (authorizer seam, fail-closed), with_envelope(permit=...), status seam
audit.py                     # CHANGED: new labels, record_decision, optional policy fields, structured_output default
main.py                      # CHANGED: install the policy engine at import (no I/O at import)
tools/utils.py               # CHANGED (small): nothing implicit; maybe one attribution line for denied/expired
tools/status_tools.py        # CHANGED: policy/enforcement lines in get_revit_status via a bridge seam
revit_mcp/permits.py         # NEW helper (no routes, no pyRevit): verify + consume, IronPython 3.4 dialect
revit_mcp/security.py        # CHANGED: gate_or_response calls permits; status_block adds permit protocol
revit_mcp/trust.py           # CHANGED: permit_failure(reason), PERMIT_* constants, OPEN_POST_READ_ROUTES += 3 preflight routes
revit_mcp/identity.py        # CHANGED (tiny): process_token() accessor
revit_mcp/parameters.py      # CHANGED: /parameter_preflight/ (open read)
revit_mcp/editing.py         # CHANGED: /elements_preflight/ (open read; serves delete and transform)
revit_mcp/placement.py       # CHANGED: /family_preflight/ (open read; edit_family, load_family, shared-parameter resolution)
deploy/server.py gate.py warm.py   # CHANGED: pywin32 sys.path + DLL dir shim
deploy/build-payload.cmd     # CHANGED: copy policy.py, permit.py, policy.base.toml; stage policy source path
deploy/config.cmd            # CHANGED: MCP_POLICY_FILE (operator file beside MCP_SECRET_FILE)
scripts/conventions.py       # CHANGED: LOCAL_MODULES += "permits"; OPEN reads += 3; kit rebuild (scripts/build_contrib_kit.py)
tests/unit/...               # NEW policy/permit/channel tests; CHANGED gate_support, inventory, wiring, audit pins
```

### Pattern 1: Single choke point in `bridge.revit_post`, fail closed
**What:** `revit_post` is the only POST exit (read: `async def revit_post(endpoint: str, data: Dict[str, Any], ctx: Any = None, target=..., timeout=..., params=...)`, `bridge.py:838-840`). Hook a module-level authorizer there. Default `None` means refuse (`"Error: ... NOT sent ..."`, kind `not-sent`), so "no engine installed" blocks. `main.py` installs the real engine; a `conftest.py` autouse fixture installs a permissive test authorizer (like it already pins `_secret_cache`). Open POST reads (the 7 plus the 3 preflight routes) skip the hook, which also prevents recursion when the engine calls preflight. The hook must **return** refusals (tools such as `execute_revit_code` catch `(ConnectionError, ValueError, RuntimeError)` only, `tools/code_execution_tools.py` read) and never raise.
**When to use:** always; it also covers future tools and alternative paths because enforcement follows the route, not the tool name.
**Resolve the target once** before authorizing (`parse_target(selector)` or `resolve_default_target()`, then pass `_selector_for(resolved)` to `_dispatch`) so permit `session_token`, preflight and send address the same incarnation.

### Pattern 2: Decision flow with human wait outside the lock
1. `policy.current()` (non-blocking; reload runs in a worker thread, below).
2. `rule = policy.rule_for(route)`; unknown route -> deny `unknown_route`.
3. `deny` -> `audit.record_decision(label="denied")`, return refusal text (kind `not-sent`).
4. For `check` rules and confirm rules that need facts: call the preflight route (it takes the per-incarnation lock for milliseconds; that is acceptable and is not the human wait).
5. Evaluate closed-vocabulary checks -> `allow` | `confirm` | `deny` with reason codes.
6. `confirm`: acquire a **per-process asyncio lock** (one window at a time; waiting for it is bounded by the same timeout), build the Russian message with a unique 6-hex code, call `session.elicit_form` under `asyncio.timeout(policy.confirm_timeout_s)`. Capability first (`check_client_capability`), otherwise block.
7. After a positive answer: compare `policy.version` with the version at decision time (changed -> `denied: policy_changed`).
8. Re-run the same preflight and compare a **facts digest** (instance/type, counts, current value, document token); changed -> `denied: facts_changed` (ask again).
9. Mint the permit (TTL 60 s) and send. No automatic resend on any outcome.

**Example (verified pattern, mcp 1.30.0 with an mcp 2.0.0 client):**
```python
# Source: experiment this session (server on mcp 1.30.0, client on mcp 2.0.0 with a Hermes-shaped callback)
import asyncio
from mcp import types

_EMPTY_FORM = {"type": "object", "properties": {}}

async def ask_human(ctx, message, timeout_s):
    """'accepted' | 'declined' | 'cancelled' | 'expired' | 'unavailable'. Never raises except CancelledError."""
    session = getattr(ctx, "session", None)
    if session is None:
        return "unavailable"
    caps = types.ClientCapabilities(elicitation=types.ElicitationCapability())
    if not session.check_client_capability(caps):          # False: no capability, or stateless HTTP session
        return "unavailable"
    try:
        async with asyncio.timeout(timeout_s):
            result = await session.elicit_form(message, _EMPTY_FORM, ctx.request_id)
    except TimeoutError:
        return "expired"
    except Exception:                                      # McpError from a client error (observed: "boom", "Elicitation not supported")
        return "unavailable"
    # Hermes always sends content={} on accept: ignore content, trust action only.
    return {"accept": "accepted", "decline": "declined", "cancel": "cancelled"}.get(result.action, "unavailable")
```

### Pattern 3: Stateless permit, verified and consumed in `gate_or_response`
**Permit** (`_mcp.permit`, all ASCII): `{"v":1,"r":"/set_parameter/","a":"<64 hex>","s":"<session uuid>","e":<exp epoch s>,"n":"<32 hex>","p":"<12 hex>","m":"<64 hex>"}`.
`a = sha256(args_text)`, where `args_text` is the exact JSON object text of the request body **without** the `_mcp` member. `m = HMAC-SHA256(K, "permit1\n"+r+"\n"+a+"\n"+s+"\n"+str(e)+"\n"+n+"\n"+p)`, `K = HMAC-SHA256(secret_utf8, b"revit-mcp/permit/v1")` (domain separation; the secret itself is already in the body, so the MAC is an integrity/consistency device, not an isolation barrier, see Threat Model).
**Wire form:** `{"_mcp":<envelope compact JSON>,<rest of args text>}`: envelope first, args text unchanged after it. Sender:
```python
# Source: experiment this session (CPython 3.13); tools/permit.py is the planner's file
import json
def wire_text(data, envelope):
    core = json.dumps(data, separators=(",", ":"), allow_nan=False)      # ensure_ascii=True (default): pure ASCII
    env = json.dumps({"_mcp": envelope}, separators=(",", ":"))[1:-1]    # '"_mcp":{...}'
    return core, ("{" + env + "}" if core == "{}" else "{" + env + "," + core[1:])
```
Receiver (IronPython 3.4 dialect: no f-strings, `.format` only):
```python
# Source: experiment this session (verified on CPython; raw_decode(s, idx) exists at the 3.4 language level)
import json
def split_wire(text):
    prefix = '{"_mcp":'
    if not text.startswith(prefix):
        return None
    env, end = json.JSONDecoder().raw_decode(text, len(prefix))
    rest = text[end:]
    if rest == "}":
        return env, "{}"
    if rest.startswith(","):
        return env, "{" + rest[1:]
    return None
```
Checks, in order, all fail closed with a verdict word (never the body or secret): `malformed` (not bytes/ASCII text, envelope not first, `trust.split_envelope(raw)[0] != env`, i.e. a duplicate `_mcp` key, bad shape), `unsupported_version`, `bad_signature`, `route_mismatch` (`request.path`), `session_mismatch` (AppDomain token), `args_mismatch`, `expired` / `not_yet_valid` / `ttl_too_long`, `replayed` (nonce in registry), `registry_full`. Registry: `{nonce: exp}` under a `threading.Lock`, purged of entries past `exp+5`, hard cap 4096. Consumption happens in the same function call that verified (check-and-add under the lock), before `request.data` is rewritten. Verification sits **after** the secret and integrity checks and before `request.data = trust.clean_body(raw, payload)` (`security.py:147`).

### Pattern 4: Colocated read-only preflight routes
Three open POST reads, each next to the code whose resolution it mirrors (no cross-domain import): `/parameter_preflight/` (parameters.py, mirrors `set_parameter` and `modify_element` lookup), `/elements_preflight/` (editing.py, delete and transform: counts, categories, pinned, parameter-element detection), `/family_preflight/` (placement.py, `edit_family`, `load_family`, shared-parameter resolution with the same name-to-definition dictionary `edit_family` builds). Each starts with `strip_envelope(request)`, resolves the document with `identity.mutation_document_or_response` (a refusal there means the mutation would also be refused: return it, ask no human), opens no transaction, caps work (e.g. 2000 ids, beyond that report `unknown`), and never raises.

### Pattern 5: Policy engine data model (TOML, closed vocabulary)
```toml
# Source: tomllib round trip tested this session; literal '...' strings keep UNC backslashes and Cyrillic.
schema = 1

[settings]
confirm_timeout_s = 300
permit_ttl_s = 60
shared_parameters_file = '\\Srv-dfs\BIM\01_Ресурсы плагинов\2_Shared_parameters\ГП_ФОП2025.txt'

[routes."/delete_elements/"]
tool = "delete_elements"
decision = "confirm"
reason = "delete"
document_bound = true

[routes."/set_parameter/"]
tool = "set_parameter"
decision = "check"                       # a built-in Python check, never an expression
check = "parameter_write"
confirm_when = ["type_parameter", "multiple_elements", "overwrites_value", "facts_unavailable", "group_member"]
document_bound = true
```
Operator file overlays routes by key (and settings); an unknown route key, unknown check name, unknown reason word or an out-of-range number invalidates the **whole** file (no silent no-ops). `policy_hash = sha256(base bytes LF-normalized + operator bytes LF-normalized)[:12]`.

### Anti-Patterns to Avoid
- **Canonicalizing floats on both sides.** IronPython 3.4.2 float repr is not shortest round-trip (below). Hash text, not re-serialized objects.
- **`ctx.elicit(message, ModelWithRequiredFields)`.** Hermes answers `accept` with `{}`; a required field makes validation raise.
- **Using `content` of an accept as consent evidence.** The client never fills fields; only `action` counts.
- **Touching the operator share or the FOP file on the event loop or at import.** An unreachable SMB share blocks for a long time; the cold-start gate is 2.0 s. Use `asyncio.to_thread` plus a short `wait_for`, and never at import.
- **Raising from the policy hook.** Tools catch only `(ConnectionError, ValueError, RuntimeError)`; return a tagged `Error:` text instead.
- **Adding `kind="denied"` provenance.** Keep `not-sent` for refusals so `format_response` and `build_entry` keep their behaviour; use a dedicated `audit.record_decision`.
- **A `permit_ok` flag, env var or module attribute on the Revit side** that skips verification. Tests mint real permits with a test secret and a monkeypatched session token (as `configure_gate` already does for the secret).
- **Hashing facts or policy in the Revit extension.** The extension knows one rule only (D-18).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TOML parsing | custom parser | `tomllib` (stdlib) | Strict; rejects duplicate keys and BOM (tested); decode `utf-8-sig` first |
| MCP elicitation wire protocol | JSON-RPC by hand | `ServerSession.elicit_form` + `check_client_capability` | Verified in all scenarios |
| Timeout/cancel of the human wait | threads, timers | `asyncio.timeout` | Already used in `bridge._dispatch_core`; `CancelledError` propagates |
| HMAC on CPython | own HMAC | `hmac.new(..., hashlib.sha256)` + `hmac.compare_digest` | Standard |
| HMAC inside IronPython | `hmac` module reliance | 10-line RFC 2104 over `hashlib` with a constant-time compare reusing `trust._same_digest` | `hmac.new` unverified under IPY 3.4; `hashlib` verified live; parity-tested |
| Request signing canonical form | JSON canonicalizer | the exact wire text (envelope first, `raw_decode` split) | Float repr differs between runtimes |
| File change detection | inotify/watchers | `os.stat` (`st_mtime_ns`, size) + SHA-256 of bytes, debounced two identical reads | Works on SMB; no new dependency |
| Atomic policy swap | locks around readers | build an immutable `Policy` object, assign one module reference | Single reference assignment is atomic in CPython |
| Document resolution for the window | title/path lookup | `identity.mutation_document_or_response` (Phase 2) | Token-based, TOCTOU-aware |
| Audit writer | second log | `audit.py` writer, new `record_decision` | Phase 6 owns redaction, retention, one writer per process |

**Key insight:** every hard sub-problem here already has a repo-owned solution (secret envelope, identity registry, audit writer, honest outcomes). The phase adds one decision engine, one MAC string and one registry; it should not add a second transport, log or identity scheme.

## Gate-by-Gate Answers (from the orchestrator's research priorities)

### Gate 1 - MCP SDK upgrade (D-06)

| Question | Answer | Evidence |
|----------|--------|----------|
| First version with server elicitation | 1.10.0 (2025-06-26): `Context.elicit` at `mcp/server/fastmcp/server.py:1064` and `ServerSession.elicit` at `session.py:258` in the 1.10.0 wheel | `[VERIFIED: wheel inspected]` |
| Target | **1.30.0** (`mcp[cli]>=1.30,<2`). 2.x deferred. | Experiments below; `[CITED: github.com/modelcontextprotocol/python-sdk releases v2.0.0, v1.30.0]`: "v1.x now receives only security fixes", suggests `mcp>=1.28,<2` if not ready to migrate |
| Existing unit suite on 1.30.0 | 33 failures, **all** `AttributeError: 'list' object has no attribute 'text'` in the test helper `content[0].text`: since 1.10 `FastMCP.call_tool` returns `(content, structured)` for annotated returns. With `structured_output=False` as default: **6361 passed, 3 skipped**, identical to the 1.9.0 baseline (6361 passed, 3 skipped, 100.5 s) | `[VERIFIED: pytest runs with a scratchpad plugin that sets the default; no repo file modified]` |
| `outcome` on the wire | Without the default, all 59 tools gain `outputSchema {'result': string}` (59/59) and `get_revit_view` too; with 1.9.0: 0. Set `kwargs.setdefault("structured_output", False)` in `audit.install_audited_tools.audited_tool` (`FastMCP.tool(..., structured_output=...)` exists at `server.py:422` of 1.30.0) | `[VERIFIED: tools/list against main.py under both versions]` |
| `user_request` + schema preserved | `set_parameter props: ['document','element_id','parameter_name','target','user_request','value']` on 1.30.0 (and 1.9.0): `functools.wraps` + `__signature__` wrapper survives | `[VERIFIED]` |
| Init latency | 0.98 s (venv, includes client spawn) vs 0.92 s for 1.9.0; in the **payload layout** (embeddable CPython 3.12.3, compiled): 1.03-1.08 s vs 0.83-0.86 s for 1.9.0, gate limit 2.0 s | `[VERIFIED: deploy/gate.py run from scratch app dirs]`. A first run on a freshly created uncompiled tree took 2.7 s (cold file cache/AV/bytecode): `update.cmd` already runs `warm.py` for that |
| Transports | `--streamable-http`, `--sse`, `--combined` (both clients) each answered `tools=59` on 1.30.0 (run on port 8765; port 8000 on this machine is held by another process, untouched) | `[VERIFIED: wrapper script that sets mcp.settings.port]` |
| **Payload import** | With the **exact** build recipe (`uv pip install --python <pyRevit CPY3123> --target libs --python-platform windows --python-version 3.12 --compile-bytecode`), `import mcp` raises `ModuleNotFoundError: No module named 'pywintypes'` (`mcp/os/win32/utilities.py:22-25` imports `pywintypes, win32api, win32con, win32job` unconditionally on win32, reached from `mcp/__init__.py`). Fix: add `libs\win32`, `libs\win32\lib`, `libs\pythonwin` to `sys.path` (and `os.add_dll_directory(libs\pywin32_system32)` as belt and braces) in **`deploy/server.py`, `deploy/gate.py`, `deploy/warm.py`**. Reproduced: with the three paths `import mcp` succeeds (with and without the DLL directory) and `gate.py` printed `GATE_OK` | `[VERIFIED: experiment]`. 1.10.0 has no pywin32 requirement; every release from 1.11.0 on checked does (`pywin32>=310`) |
| No capability | `check_client_capability(...)` returns `False`; an un-guarded `elicit_form` raises `McpError: Elicitation not supported` (client default callback) | `[VERIFIED: nocb experiment]` |
| Stateless HTTP | With `stateless_http=True, json_response=True` (as `main.py` configures) `check_client_capability` is `False` **and** an un-guarded elicit hangs until the caller's timeout; with a stateful, non-JSON server it works. Confirm-class operations are therefore blocked over HTTP transports as configured (documented limitation; stdio is the Hermes path: `configure_hermes.py:171-172` `command`/`args`) | `[VERIFIED: both modes run]` |
| decline / cancel | `ElicitResult.action` `decline` / `cancel`, `content=None` | `[VERIFIED]` |
| Client handler exception | surfaces as `McpError("boom")` on the server | `[VERIFIED]` |
| Timeout without holding the lock | `async with asyncio.timeout(T): await session.elicit_form(...)` inside the policy hook, which runs **before** `_dispatch` takes `state.lock` (`bridge.py:1113-1120`). A late client answer after the server gave up is ignored by the SDK (`ERROR ... Received response with an unknown request ID` on **stderr**, session stays healthy; the next elicit worked) | `[VERIFIED: late-answer experiment]` |
| Unicode | Cyrillic and a non-BMP emoji in the message arrive byte-identical (`EQUAL: True`) | `[VERIFIED]` |
| Message/schema accepted | Empty `properties` form accepted by a 2.0.0 client; schema shown by Hermes is generic ("Approval requested by MCP server") | `[VERIFIED]` + Hermes read |

**Breaking-change checklist for the planner (1.9.0 -> 1.30.0):** (1) pywin32 shim x3 files; (2) `structured_output=False` default; (3) `pyproject.toml` pin; (4) `uv.lock` regenerated: new wheels listed above, `sniffio` dropped; (5) protocol version negotiated by the server is now `2025-11-25` (was `2025-03-26`); (6) deprecation warnings: `ctx.info` unchanged in 1.x; (7) 1.30 closes idle stateful HTTP sessions after 30 min (not relevant to stdio). No change to `FastMCP(...)` construction in `main.py` was needed (the server started with the current arguments).

### Gate 2 - Unchanged HermesFork elicitation handler (read-only)

| Item | Finding | Evidence |
|------|---------|----------|
| Registration | Elicitation is enabled unless config says otherwise: `elicitation_config.get("enabled", True)`; the callback is passed to `ClientSession` via `session_kwargs` | `mcp_tool.py:3714-3716`, `2183-2185` `[VERIFIED: Read]` |
| Form fields | **Not rendered as inputs.** Only the schema summary is shown (`_format_elicitation_schema_summary`: "Approval requested by MCP server '<name>'." when `properties` is empty). The `message` is the content that matters | `mcp_tool.py:2115-2138` |
| Answer | `accept` -> `ElicitResult(action="accept", content={})` (verbatim `mcp_tool.py:2302`); `cancel` on client timeout (`2291`) and on `cancel` answer (`2305`); everything else `decline` | `2280-2307` |
| Approve variants | gateway: `if choice in ("once", "session", "always"): return "accept"`; CLI/TUI: same mapping with `allow_permanent=False`; `timeout` -> `cancel`; missing notify callback / exceptions -> `decline` | `approval.py:5359-5389` |
| Timeout | `self.timeout = _safe_numeric(config.get("timeout", 300), 300, float)`; outer cap = timeout + 5 s grace. `configure_hermes.py` does not set it (default 300 s equals D-07) | `mcp_tool.py:2171`, `2281-2284` |
| Text shown | Gateway: `approval_data = {"command": message, "description": description, "pattern_key": "mcp_elicitation", ...}` (message presented as the "command"); CLI path scrubs both with `redact_sensitive_text` before rendering (long hex such as a full SHA-256 may be masked: show 12-16 hex) | `approval.py:5343-5348`, `3015-3017` |
| Coalescing | Gateway queue: a new request whose `command` **and** `pattern_keys` equal a queued one waits on that leader; `session`/`always` are adopted by followers, `once` is not. So two concurrent prompts with identical text can be answered by one click | `approval.py:4206-4230` |
| FIFO / approve-all | `resolve_gateway_approval`: with `request_id` only that entry; otherwise `resolve_all` resolves every pending entry, else the oldest (FIFO) | `approval.py:2634-2673` |
| Retry on session loss | `_handle_session_expired_and_retry(server_name, exc, _call_once, ...)` re-sends the same `tools/call` once after reconnect; for stdio that means a **fresh server process** and a new window | `mcp_tool.py:5927-5943` |
| Tool timeout | `configure_hermes.py` writes `timeout: 600` for the `revit` entry (covers a 300 s human wait plus execution) | `deploy/configure_hermes.py` `build_block` |
| Unproven | How Hermes **Desktop** renders the message (length, newlines, redaction) and whether `/approve` text commands are offered there: code reading only; D-20 live bench | 07-RESEARCH-NOTES (`approval.tsx`), not observed |

**Design consequences:** (a) empty schema; consent = `action == "accept"` only; (b) message starts with a unique code line (`Код операции: 7F3A91`) so identical operations never coalesce and the human can correlate; (c) serialize windows per MCP process (one pending prompt at a time) so `/approve all` and FIFO cannot approve an unseen prompt; (d) keep the message plain text <= about 1500 characters (hash shown as 16 hex; untrusted strings quoted and truncated); (e) "Yes" may have been "session"/"always" in the UI: irrelevant, the server grants one call.

### Gate 3 - Permit scheme (D-18)

- **Where the single-use registry lives:** Revit side, in memory, module state of `revit_mcp/permits.py`, guarded by a `threading.Lock`. It covers every MCP process (one Revit, many sessions), survives MCP restarts and Hermes redelivery to a fresh server process, and dies with Revit; that is safe because permits bind the process `session_token` (a restart makes old permits invalid for the new incarnation) and live 60 s. A pyRevit **Reload** (forbidden by project rule) could wipe the module registry; the 60 s TTL bounds that window. Optional hardening: keep the registry in the same AppDomain slot mechanism as `identity._AppDomainStore`.
- **Crash/restart:** MCP crash mid-flight: if the request was sent the permit is consumed (replay refused), outcome reported `unknown` on the next read; if not sent it expires in 60 s. Revit crash: new session token.
- **Clock skew:** bridge only talks to loopback (`parse_target` accepts `localhost`, `127.0.0.1`, `::1` only, `bridge.py:188`), so both runtimes use one machine clock; allow `exp` check with a 5 s skew and refuse `exp - now > 120`.
- **Float repr (decisive for canonicalization)** `[VERIFIED: executed IronPython 3.4.2 netfx from pyRevit-Master\bin\netfx\engines\IPY342 through a PowerShell host]`:
  `repr(0.1)` = `0.10000000000000001`, `repr(1.0/3.0)` = `0.33333333333333331`, `repr(1e16)` = `10000000000000000.0`, `repr(1e-7)` = `9.9999999999999995e-08`, `repr(123456789012345678.0)` = `1.2345678901234568e+17`; CPython prints `0.1`, `0.3333333333333333`, `1e+16`, `1e-07`. `(0.1).hex()` works. A non-BMP character has `len == 2` (UTF-16). The bare host had no stdlib (`struct`, `hashlib`, `json` missing), so `hashlib`/`json` there rely on the Lib that pyRevit loads inside Revit (hashlib proven live per `trust.py:179-190`).
- **`hmac`/`hashlib` in IronPython 3.4:** `hashlib.sha256` verified live 2026-10-23 (plan 03-08); `hmac.compare_digest` present, `hmac.new` not exercised: hand-roll HMAC (below) and add the HMAC vectors to `scripts/probe_ipy_trust.py` or a sibling probe for the D-20 bench.
```python
# Source: experiment this session; equals hmac.new(k, m, hashlib.sha256).hexdigest() on 3 vectors incl. a 131-byte key
def hmac_sha256_hex(key, msg):
    block = 64
    if len(key) > block:
        key = hashlib.sha256(key).digest()
    key = key + b"\x00" * (block - len(key))
    outer = bytes(bytearray(b ^ 0x5c for b in bytearray(key)))
    inner = bytes(bytearray(b ^ 0x36 for b in bytearray(key)))
    return hashlib.sha256(outer + hashlib.sha256(inner + msg).digest()).hexdigest()
```
- **Envelope handling today (read):** `with_envelope` puts `{SECRET_KEY: secret}` and `call_id` into `body[ENVELOPE_KEY]` (`bridge.py:1219-1224`); the wire is `json.dumps(data).encode("utf-8")` in `_send` (`bridge.py:905`). Revit side: `trust.split_envelope` returns the **whole** reserved dict (`trust.py:114-135`: "envelope is the whole reserved-key dict (the secret today; a call id or an approval token may ride it later)"), `envelope_secret` reads only `secret`, `clean_body` strips the whole key, `strip_envelope` does the same for open reads. Integration point: `security.gate_or_response` after the integrity check and before `request.data = trust.clean_body(raw, payload)` (`security.py:143-147`).
- **Mixed rollout D-19:** (1) old ext + new payload: unknown sub-keys inside `_mcp` are ignored by `split_envelope`/`envelope_secret`/`clean_body`/`strip_envelope` on all 41 non-GET routes (34 gated through `gate_or_response`, 7 open through `strip_envelope`); the static proof tool `scripts/scan_envelope_tolerance.py` (`--dir <share ext>\revit_mcp`) is the D-06-style precondition to rerun, and `tests/unit/test_audit_correlation.py` already runs the real gate with an extra `call_id`. In this state mutations are still confirmed on the CPython side but not enforced Revit-side: `get_revit_status` must say so (`/status/` lacks `permit.protocol` -> "extension does not enforce permits"). (2) new ext + old payload: no `permit` -> `403`, body `{"error": "Mutation rejected: one-time permit missing", "permit": "missing", "hint": ...}` with the RU+EN sentence "обновите RevitMCP и перезапустите сессию ассистента / run Update RevitMCP and restart the assistant session" (Phase 5 hints are English: `_AUTH_HINTS` in `trust.py:58-72`). (3) The ext advertises `permit: {"protocol": 1}` through `security.status_block` (merged at the top level of `/status/`, `status.py`); the payload reads it from the handshake payload it already fetches.
- **Document binding:** the route's own guard (`decide_mutation_document`) lets an explicit selector reach exactly that document or refuse, and never falls back (read `identity.py:528-567`); without a selector it takes "the only open, active document". For confirm/check paths (the ones with a human wait or preflight) the engine therefore **injects the resolved `document` token into the body before hashing** when the route is document-bound and the tool omitted it, so the effect cannot land on a different document opened during the wait. Document-bound routes = the 31 `GUARDED` routes in `tests/unit/inventory_support.py` plus `/activate_document/`; `/open_model/` and `/execute_code/` take none. Keep a parity test between the policy's `document_bound` flags and the AST fact "handler calls `mutation_document_or_response`".
- **Consumption vs later refusals:** the permit is consumed in the gate. A later document refusal (412/404/400) burns it; the human must re-confirm. Preflight resolves the document first to make that rare.
- **Duplicate/redelivery honesty:** one permit cannot execute twice (registry). A client redelivery after reconnect is a **new** call: new window, new permit; nothing in this phase can tell it from a deliberate repeat. Optional (user decision, see Open Questions): a Revit-side `(route, args_sha, session)` memory of recent consumptions returned by preflight to escalate allow to confirm with a "same operation N s ago" line.

### Gate 4 - Preflight read-only facts (D-09/D-10)

Read of `revit_mcp/parameters.py`, `editing.py`, `transforms.py`, `placement.py`, `tools/family_tools.py`:

| Tool | What is cheap AND exact | Must say "unknown" |
|------|-------------------------|--------------------|
| `set_parameter` | Resolution order is exactly `elem.LookupParameter(name)`, else `doc.GetElement(elem.GetTypeId()).LookupParameter(name)` (`parameters.py:446-454`). Preflight returns: `resolved` = `instance` / `type` / `not_found`; `element_is_type` (the id names an `ElementType`, so *any* parameter is type-level); type name and family; `read_only`; storage type; `has_value`; current display string **and raw internal value** (the route writes `param.Set(float(value))` with **no unit conversion**, `parameters.py:493-494`, so the window must show raw and display values); `group_member` (`elem.GroupId` valid); for type-level writes the instance count of that type = elements of the type's category (`OfCategoryId`, `WhereElementIsNotElementType`) whose `GetTypeId()` equals the type id `[ASSUMED: API behaviour, not run live]` | instance count for system/nested/shared families beyond the category scan; propagation to other group instances `[ASSUMED]`; count when a cap is hit |
| `modify_element` | Uses `elem.LookupParameter` only (instance), no type fallback (`editing.py:203`), up to N parameters, one element; same preflight per parameter name; **a type element id turns every write into a type write** | same as above |
| `delete_elements` | Existence of every id (the route refuses the whole call on a missing id, `editing.py:53-61`); requested count; categories and type names; whether an id is a `ParameterElement`/`FamilySymbol`/`Family`/level/view (deleting a parameter element or a type is an alternative D-23 path) | **Cascade** (`doc.Delete` returns it only after deletion, `editing.py:74-83`); no trial delete (D-09). Do not use `GetDependentElements` as an estimate (semantics unverified) |
| `transform_elements` | Existence, count, categories, pinned flag (the route refuses pinned, `transforms.py:60-71`); operation; for `copy` the new count equals the old | dependent elements moved with hosts |
| `edit_family` | Family loaded and `IsEditable`; instance count of its symbols; whether `parameters` / `new_type_name` / `add_shared_parameters` are present; for shared names: configured file `app.SharedParametersFilename`, the definition the route would resolve (`sp_defs[defn.Name]`, last name wins across groups: report duplicates), its GUID, data type, group, and whether the family already has it. Reload overwrites with `overwriteParameterValues.Value = True` for all instances/types (`placement.py:47-49`) | content/regeneration effects of the family edit |
| `load_family` | path exists, file size, loaded-already flag by name | contents of the `.rfa` (types, nested families, **its own shared parameters**): cannot be verified against the FOP |
| `execute_revit_code` | code length, SHA-256, first 600 characters, heuristic *hints* (tokens like `ParameterBindings`, `Delete`, `OpenSharedParameterFile`) shown as hints, not enforcement | everything else |

**Routes:** three new **open POST reads** (they cannot be gated: a permit-requiring preflight is circular), so add them to `trust.OPEN_POST_READ_ROUTES`, the `audit.py` copy, `scripts/conventions.py` and the literal `D02_OPEN` (pinned counts change: routes 56 -> 59, non-GET 41 -> 44, open reads 7 -> 10, gated stays 34). A GET cannot carry hundreds of element ids. Information disclosure is equivalent to the existing open reads (`/ai_filter/`, `/material_quantities/`).

### Gate 5 - Complete classification (D-10..D-13, D-22, D-23)

**Routes (56).** Source: `@api.route(...)` decorator lines in `revit_mcp/*.py` `[VERIFIED: grep this session; counts match test_phase5_gate_wiring.py: "assert len(ROUTES) == 56", "assert len(NON_GET) == 41", "assert len(GET_ROUTES) == 15", "assert len(GATED_KEYS) == 34"]`. "Doc" = document-bound (explicit `document` selector accepted).

| Route (file:line) | Method | Tool(s) | Class | Base decision | Doc |
|---|---|---|---|---|---|
| `/create_detail_line/` (detail.py:183) | POST | create_detail_line | gated | allow | yes |
| `/create_line/` (building.py:310) | POST | create_line_based_element | gated | allow | yes |
| `/create_surface/` (building.py:668) | POST | create_surface_based_element | gated | allow | yes |
| `/create_level/` (building.py:787) | POST | create_level | gated | allow | yes |
| `/create_dimensions/` (annotation.py:237) | POST | create_dimensions | gated | allow | yes |
| `/tag_walls/` (annotation.py:438) | POST | tag_walls | gated | allow | yes |
| `/tag_elements/` (tags.py:243) | POST | tag_elements | gated | allow | yes |
| `/create_sheet/` (documentation.py:157) | POST | create_sheet | gated | allow | yes |
| `/create_schedule/` (documentation.py:338) | POST | create_schedule | gated | allow | yes |
| `/export_document/` (documentation.py:583) | POST | export_document | gated | allow | yes |
| `/export_ifc/` (interop.py:150) | POST | export_ifc | gated | allow | yes |
| `/link_file/` (interop.py:296) | POST | link_file | gated | allow | yes |
| `/create_duct/` (mep.py:223) | POST | create_duct | gated | allow | yes |
| `/create_pipe/` (mep.py:399) | POST | create_pipe | gated | allow | yes |
| `/create_mep_system/` (mep.py:608) | POST | create_mep_system | gated | allow | yes |
| `/create_room/` (rooms.py:200) | POST | create_room | gated | allow | yes |
| `/create_room_separation/` (rooms.py:363) | POST | create_room_separation | gated | allow | yes |
| `/create_grid/` (structure.py:134) | POST | create_grid | gated | allow | yes |
| `/create_framing/` (structure.py:338) | POST | create_structural_framing | gated | allow | yes |
| `/create_view/` (view_management.py:455) | POST | create_view | gated | allow | yes |
| `/set_active_view/` (view_management.py:469) | POST | set_active_view | gated | allow | yes |
| `/place_family/` (placement.py:532) | POST | place_family | gated | allow | yes |
| `/color_splash/` (colors.py:1165) | POST | color_splash | gated | allow | yes |
| `/clear_colors/` (colors.py:1206) | POST | clear_colors | gated | allow | yes |
| `/save_document/` (document.py:201) | POST | save_document | gated | allow | yes |
| `/activate_document/` (documents.py:655) | POST | activate_document | gated | allow | yes (required) |
| `/open_model/` (worksharing.py:805) | POST | open_model | gated | allow | no |
| `/delete_elements/` (editing.py:126) | POST | delete_elements | gated | **confirm** (`delete`) | yes |
| `/transform_elements/` (transforms.py:218) | POST | transform_elements | gated | **confirm** (`transform`) | yes |
| `/load_family/` (placement.py:610) | POST | load_family | gated | **confirm** (`load_family`) | yes |
| `/edit_family/` (placement.py:1091) | POST | edit_family | gated | **confirm**, plus **deny** when any `add_shared_parameters` name is not in the FOP (D-22) | yes |
| `/execute_code/` (code_execution.py:266) | POST | execute_revit_code | gated | **confirm** every call (`execute_code`) | no |
| `/set_parameter/` (parameters.py:578) | POST | set_parameter | gated | **check** `parameter_write` | yes |
| `/modify_element/` (editing.py:323) | POST | modify_element | gated | **check** `parameter_write` | yes |
| `/ai_filter/` (analysis.py:23) | POST | ai_element_filter | open read | allow (read) | - |
| `/material_quantities/` (analysis.py:295) | POST | get_material_quantities | open read | allow (read) | - |
| `/clash_check/` (clash.py:124) | POST | check_clashes | open read | allow (read) | - |
| `/list_category_parameters/` (colors.py:1219) | POST | list_category_parameters | open read | allow (read) | - |
| `/document_summary/` (documents.py:693) | POST | read_document_summary | open read | allow (read) | - |
| `/document_levels/` (documents.py:711) | POST | read_document_levels | open read | allow (read) | - |
| `/model_worksets/` (worksharing.py:404) | POST | list_model_worksets | open read | allow (read) | - |
| `/room_data/` (analysis.py:184) | GET | export_room_data | GET | allow (read) | - |
| `/model_statistics/` (analysis.py:419) | GET | analyze_model_statistics | GET | allow (read) | - |
| `/selected_elements/` (editing.py:337) | GET | get_selected_elements | GET | allow (read) | - |
| `/model_info/` (model_info.py:20) | GET | get_revit_model_info | GET | allow (read) | - |
| `/documents/` (documents.py:605) | GET | list_documents | GET | allow (read) | - |
| `/project_parameters/` (parameters.py:197) | GET | list_project_parameters | GET | allow (read) | - |
| `/element_properties/<element_id>` (parameters.py:300) | GET | get_element_properties | GET | allow (read) | - |
| `/list_families/` (placement.py:624) | GET | list_families | GET | allow (read) | - |
| `/list_family_categories/` (placement.py:672) | GET | list_family_categories | GET | allow (read) | - |
| `/list_levels/` (placement.py:732) | GET | list_levels | GET | allow (read) | - |
| `/status/` (status.py:18) | GET | get_revit_status, get_revit_process_status | GET | allow (read) | - |
| `/get_view/<view_name>` (views.py:27) | GET | get_revit_view | GET (image) | allow (read) | - |
| `/list_views/` (views.py:211) | GET | list_revit_views | GET | allow (read) | - |
| `/current_view_info/` (views.py:299) | GET | get_current_view_info | GET | allow (read) | - |
| `/current_view_elements/` (views.py:383) | GET | get_current_view_elements | GET | allow (read) | - |

Count check: gated 34 = 27 allow + 5 confirm + 2 check; open reads 7; GET 15; total 56. After this phase add `/parameter_preflight/`, `/elements_preflight/`, `/family_preflight/` (open reads, allow).

**Tools (59).** Source: `tests/unit/tool_manifest.txt` (Read, 59 names) and `tools/*.py` transport calls (grep). Tools without a bridge route: `discover_revit_targets`, `get_revit_process_status` (uses `/status/` per process), `start_revit` (launches a process).

| Group | Tools | Base decision |
|---|---|---|
| Creation (D-13) | create_detail_line, create_dimensions, create_duct, create_grid, create_level, create_line_based_element, create_mep_system, create_pipe, create_room, create_room_separation, create_schedule, create_sheet, create_structural_framing, create_surface_based_element, create_view, place_family, tag_elements, tag_walls | allow |
| Other allow (D-13) | activate_document, set_active_view, save_document, link_file, export_document, export_ifc, open_model, color_splash, clear_colors | allow |
| Reads | ai_element_filter, analyze_model_statistics, check_clashes, export_room_data, get_current_view_elements, get_current_view_info, get_element_properties, get_material_quantities, get_revit_model_info, get_revit_status, get_revit_view, get_selected_elements, list_category_parameters, list_documents, list_families, list_family_categories, list_levels, list_model_worksets, list_project_parameters, list_revit_views, read_document_levels, read_document_summary | allow (read) |
| Local/process | discover_revit_targets, get_revit_process_status, start_revit | allow (no model mutation). `start_revit` is not named in D-13: classified allow explicitly, flagged for user confirmation (Open Questions) |
| Conditional (D-10) | set_parameter, modify_element | check -> confirm when `type_parameter`, `multiple_elements`, `overwrites_value`, `facts_unavailable` (and recommended `group_member`) |
| Always confirm (D-11/D-12) | delete_elements, transform_elements, load_family, edit_family, execute_revit_code | confirm; `edit_family` additionally deny for non-FOP shared names |

Sum: 18 + 9 + 22 + 3 + 2 + 5 = 59. The existing hand tables `TOOL_CLASSES` / `ROUTE_CLASSES` in `tests/unit/inventory_support.py` already enumerate every tool/route by what it does; the policy guard test should be derived from the same AST/registration discovery.

**Alternative mutation paths found (beyond the obviously named tools):**
1. `modify_element` with a type element id writes **type** parameters through an instance-looking tool (`LookupParameter` on an `ElementType`).
2. `set_parameter` falls back from instance to type parameter silently.
3. An element inside a model group: an instance-parameter write can fan out to other group instances (`VariesAcrossGroups` false) `[ASSUMED: Revit behaviour; see InternalDefinition.VariesAcrossGroups]`.
4. `edit_family` reload overwrites parameter values for every instance/type (`overwriteParameterValues.Value = True`).
5. `delete_elements` accepts `ParameterElement`/type/family/level/view ids: deleting a project parameter or a type is a D-23-class effect with cascade.
6. `transform_elements` `copy` creates elements.
7. `load_family` accepts any path and brings types and nested/shared parameters of unknown content.
8. `color_splash`/`clear_colors` write view graphic overrides on existing elements (allowed by D-13).
9. `save_document` (SaveAs) and `open_model` (local copy/stamp) touch the file system (allowed by D-13; HYG-03 is a future requirement).
10. `execute_revit_code` can do anything.

**Guard test design (SAFE-06):** `tests/unit/test_policy_inventory.py` (a) loads `policy.base.toml`; (b) discovers tools with `inventory_support.register_everything()` and routes with `inventory_support.route_inventory()`; (c) asserts set equality `policy tool keys == manifest` and `policy route keys == AST routes + preflight routes`; (d) asserts the decision table above literally (a hand-written expectation, so a policy edit alone cannot pass); (e) asserts `document_bound` flags equal the AST set of handlers calling `mutation_document_or_response`; (f) asserts the engine returns `deny` for a route absent from the policy; (g) a GET route is never `confirm` (nothing can enforce it).

### Gate 6 - D-22 shared parameters from the company FOP

- **Every code path that creates or binds a shared parameter** (grep of `revit_mcp/` for `ParameterBindings`, `.Insert(`, `ReInsert`, `AddParameter`, `OpenSharedParameterFile`, `SharedParametersFilename`, `ExternalDefinition`): only `edit_family` -> `manager.AddParameter(ext_def, cat_set, DB.BuiltInParameterGroup.PG_IDENTITY_DATA, True)` (`placement.py:949-984`, via `app.OpenSharedParameterFile()`, lookup by **name** over all groups, last duplicate name wins). `parameters.py` only **reads** `doc.ParameterBindings` (`parameters.py:218`). No typed tool binds a shared parameter into a **project**; that exists only through `execute_revit_code`, where D-22 cannot be enforced (arbitrary code): record as a limit, show heuristic hints in the window. `load_family` can import shared parameters inside the `.rfa` (not checkable).
- **Where to check:** CPython side. The preflight (`/family_preflight/`) returns for each requested name: `configured_file` (`app.SharedParametersFilename`), `resolved` (found?), `guid`, `name`, `datatype`, `group`, `ambiguous` (duplicate name with different GUIDs), `already_in_family`. The engine reads the FOP file on the CPython side (`asyncio.to_thread` + `wait_for` ~3 s), parses it and requires **every** name to match an entry by **GUID and name**; otherwise `deny shared_parameter_source` (also for `ambiguous`, unresolved, unreadable, undecodable, share unavailable). Compare by content, not path text (a mapped drive or DFS alias of the same file must not false-deny); show the configured path in the window. Residual TOCTOU: `SharedParametersFilename` changed between preflight and effect; re-run preflight after approval and compare the facts digest.
- **File format** `[ASSUMED: from Revit shared-parameter file knowledge; the share was not accessed]`: tab-separated records, `*META`, `*GROUP`, `*PARAM` header lines; data lines `META`, `GROUP <id> <name>`, `PARAM <guid> <name> <datatype> <datacategory> <group> <visible> <description> <usermodifiable> <hidewhennovalue>`; encoding is commonly UTF-16 LE with BOM, possibly UTF-8: sniff BOM (`FF FE`, `FE FF`, `EF BB BF`), try the sniffed encoding strictly, never guess silently, undecodable -> deny. Cyrillic names must compare exactly (NFC-normalize both sides, case-sensitive on names and case-insensitive on GUID).
- Cache the parsed set keyed by `(st_mtime_ns, size)` with a short TTL; a confirm-class path only, so cost is negligible.
- **Known side finding:** `FamilyManager.AddParameter(ExternalDefinition, BuiltInParameterGroup, Boolean)` and every other `BuiltInParameterGroup` overload are **obsolete in Revit 2024 and removed in 2025+**; `Insert`/`ReInsert` on `BindingMap` likewise `[CITED: rvtdocs.com diff pages for FamilyManager and BindingMap]`. The current `edit_family` shared-parameter code therefore likely fails on Revit 2025+ (CLAUDE.md claims support for 2024-2027). Not a Phase 7 task unless the user wants it; the policy applies either way. The live bench must record the Revit version.

### Gate 7 - D-23 operations that redefine an existing parameter

`[CITED: rvtdocs.com member lists for BindingMap, FamilyManager, InternalDefinition]` unless noted.

| Level | API | Effect | Typed tool today |
|-------|-----|--------|------------------|
| Project | `Document.ParameterBindings` (`BindingMap`) `Insert(Definition, Binding[, ForgeTypeId])` | create/bind (shared binding = D-22 path) | none |
| Project | `ReInsert(Definition, Binding[, ForgeTypeId])` | replace binding: add/remove categories, **instance <-> type** (binding class decides), **group** (ForgeTypeId overload) | none |
| Project | `Remove(Definition)` / `Erase(Definition)`, `Clear()` | drop binding(s); values lost | none |
| Project | `InternalDefinition.SetAllowVaryBetweenGroups(Document, bool)` (read: `VariesAcrossGroups`) | "values can vary by group instance"; turning it off re-aligns diverged values `[CITED: blog.autodesk.io, rvtdocs]` | none |
| Project | `doc.Delete(ParameterElement id)` | removes the parameter and values | **`delete_elements`** (confirm) when given such an id |
| Project | rename of a project/shared parameter | no API found in this research | none (`[ASSUMED]`: not available) |
| Family | `FamilyManager.AddParameter(...)` (shared / new) | add | **`edit_family` `add_shared_parameters`** (confirm + D-22) |
| Family | `ReplaceParameter(...)` (2 overloads), `RemoveParameter`, `RenameParameter`, `MakeInstance`, `MakeType`, `MakeReporting`, `MakeNonReporting`, `SetFormula`, `SetDescription`, `SetParameterLocked`, `ReorderParameters`, `SortParameters`, `NewType`, `DeleteCurrentType`, `RenameCurrentType`, `Set(...)` | redefine/rename/swap/lock/formula/values | `edit_family` uses only `NewType`, `CurrentType`, `Set`, `AddParameter` (`placement.py:877-987`); the rest only via `execute_revit_code` |
| Family | `Family.LoadFamily(doc, IFamilyLoadOptions)` with `overwriteParameterValues=True` | overwrites all project instances' type values | `edit_family` reload (confirm) |

No new typed tool is needed for D-23: the existing paths (`edit_family`, `delete_elements`, `execute_revit_code`) are all confirm. Do not add tools for `ReInsert`/`SetAllowVaryBetweenGroups` in this phase (keeps the manifest at 59 and D-02 lightweight); revisit only on user request.

### Gate 8 - Policy TOML, payload and hot reload (D-14..D-17)

- **Base policy:** `policy.base.toml` at the repository root, copied by one added line `copy /y "%REPO%\policy.base.toml" "%BUILD%\app\" >nul || exit /b 1` (the same style as `copy /y "%REPO%\audit.py" "%BUILD%\app\"`), plus `copy /y` lines for `policy.py` and `permit.py`. `tests/unit/test_payload_ships_root_modules.py` regexes only `*.py` copy lines, so add a sibling test for the data file. Load via `os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.base.toml")` (payload layout `app\`).
- **Operator file:** new `MCP_POLICY_FILE` in `deploy/config.cmd`, default beside the secret: `%MCP_SHARE_ROOT%\_build\operator_policy.toml` (the config states `MCP_SECRET_FILE=%MCP_SHARE_ROOT%\_build\bridge_secret`). The workstation does not know the share path at runtime (the payload runs from `%LOCALAPPDATA%`), so `build-payload.cmd` stages a one-line `app\policy_source` file with the UNC path (same pattern as the staged `_bridge_secret`), and `REVIT_MCP_POLICY_FILE` overrides it for development/tests. Build-time check: validate the current operator file with the same validator and warn (do not fail the publish if absent). ACL requirement (outside code): users must have read-only access to the file, otherwise an agent with user rights can weaken fleet policy `[ASSUMED]`.
- **Reload:** poll on use. On each protected call, if more than 2 s passed since the last check, run in `asyncio.to_thread` (with `asyncio.wait_for(..., 3)`) `os.stat` + read + SHA-256; apply only after the same hash was read twice (debounce torn writes from non-atomic editor saves); decode `utf-8-sig`, `tomllib.loads`, validate, build an immutable `Policy`, then assign `policy._ACTIVE = new` (one reference). Any failure keeps the previous `Policy` and stores a diagnostic `{state: "rejected", reason, file_sha, at}`. `get_revit_status` forces a refresh. Never at import (cold start) and never on the loop.
- **Initial state rule (D-17):** startup loads base first (local file, fast, in-process); a bad base sets `blocked=True` (all gated routes deny `policy_invalid`); an operator file that is invalid or unreachable at start leaves `source="base"` with the diagnostic.
- **Merge semantics:** overlay by route key and `[settings]` key; an unknown route/check/reason/enum/number out of range invalidates the file entirely. Operators may set any decision, including `allow` for destructive routes (D-15), but cannot add routes the payload does not know (unknown route = deny anyway).
- **Version/hash:** `policy_hash` 12 hex over both byte strings; `source` = `base` | `operator`; shown in `get_revit_status` (new line), audit entries and the permit `p` field. A hash change between decision and send invalidates the pending approval (SAFE-13).
- **Status seam:** attach `revit_get.policy_status = engine.status` in `bridge.py` beside `revit_get.secret_fingerprint` (the existing seam pattern, `bridge.py:1342`) and render a line in `tools/status_tools.py`.

### Gate 9 - Audit and rendering

- **New labels** appended to `audit.OUTCOME_LABELS` (`audit.py:163-166`, verbatim today: `"success", "partial", "failed", "rolled_back", "rejected_auth", "rejected_integrity", "rejected_document", "error", "unknown", "no_reply", "unverified_reply", "unrecognized"`): `denied`, `expired`, `rejected_permit`. `tests/unit/test_audit_entry.py:138` pins `== 12` and must change to 15.
- `committed` is the existing `success` label with `transaction_status: "Committed"`; `rolled_back`, `partial`, `unknown` exist. Approval is **not** an outcome: add optional fields `policy` (`{source, hash}`), `decision` (`allow|confirm|deny`), `approval` (`accepted|declined|cancelled|expired|unavailable|none`), `approval_wait_ms`, `reasons` (reason codes), `permit` (first 8 hex of the nonce) to `SCHEMA_1_FIELDS` as **additive** optional fields (tests only require `set(entry) <= set(audit.SCHEMA_1_FIELDS)`, `test_audit_entry.py:415`); keep `schema: 1`.
- **Entry point:** `audit.record_decision(call, route, ...)` for decisions that never left the process (they are `kind == "not-sent"`, for which `build_entry` returns `None` by design). Approved-and-sent calls carry the same fields through an extra key in the provenance meta dict passed by `_audit`. Attach `audit_call_id` to the refusal's provenance so `format_response` appends `Audit: call_id <id>` (existing mechanism).
- **Revit-side refusals:** HTTP 403 with `{"permit": "<verdict>"}`; extend `audit._outcome` with `if http_status == 403: return "rejected_permit", <permit verdict word>, None` after the 401/423 branches (reason never a file list or secret, like `rejected_*`).
- **Rendering:** refusals are `Error: ...` strings tagged `not-sent` (existing attribution sentence: "This request was not sent to Revit..."); no change to `_project_response`. Wording distinguishes: `DENIED by policy (<reason>)`, `DECLINED by the user`, `NOT CONFIRMED: no answer within 5 minutes (EXPIRED)`, `UNAVAILABLE: this client cannot confirm` (kept inside the text, not a new status key).

### Gate 10 - Hook point

`bridge.revit_post` before `_dispatch` (Pattern 1). The audit wrapper (`audit._wrap`) only knows tool name and kwargs, not the final route/body; elicitation inside it would not see what is actually sent and would run for tools that never post. The wrapper stays as it is (plus the `structured_output` default). The permit is attached by `with_envelope(data, secret, call_id=..., permit=...)`: `_dispatch` receives the target selector of the **already resolved** incarnation, and `_verified_exchange` re-proves identity under the lock (`bridge.py:1153-1156`), so a restart between decision and send is refused as "NOT sent".

## Runtime State Inventory

Not a rename/refactor/migration phase in the data sense; recorded for the SDK bump and the new permit rule (all five categories answered):

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None - audit logs under `%LOCALAPPDATA%\RevitMCP\audit` keep schema 1 with additive optional fields. No datastore holds policy or permits. | none |
| Live service config | The Hermes config entry `mcp_servers.revit` (`command`, `args`, `timeout: 600`, env) is generated by `deploy/configure_hermes.py`; no change needed (elicitation defaults to enabled, timeout default 300). | none; Desktop behaviour verified only at D-20 |
| OS-registered state | None. | none |
| Secrets/env vars | `_bridge_secret` (unchanged; permit key is derived from it). New optional env `REVIT_MCP_POLICY_FILE`. A rotated secret invalidates in-flight permits (also forces an ext restart as today). | document |
| Build artifacts / installed packages | `libs\` in every installed payload carries mcp 1.9.0 wheels; the new payload replaces them (`update.cmd` + `warm.py` acceptance). The pyRevit engine ABI pin (CPY3123) is unchanged. `.venv` must be re-synced by developers. | rebuild payload; shim in 3 deploy scripts |

## Common Pitfalls

### Pitfall 1: `import mcp` dies in the fleet payload after the bump
**What goes wrong:** `ModuleNotFoundError: No module named 'pywintypes'` (reproduced) at `mcp/os/win32/utilities.py:22`, reached from `mcp/__init__.py` through `client/session_group.py` and `client/stdio/__init__.py`. `gate.py` (build) and `server.py` (workstations) both fail.
**Why:** the embeddable CPython uses a `._pth` file, ignores `.pth`, and `pywin32.pth` is what normally adds `win32`, `win32\lib`, `pythonwin`.
**Avoid:** add the three paths and `os.add_dll_directory(libs\pywin32_system32)` to `server.py`, `gate.py`, `warm.py` before importing `mcp`.
**Warning signs:** `warm.py` or `gate.py` fails at build; Hermes shows the server as failed to start.

### Pitfall 2: Every tool suddenly has an `outputSchema`
**What goes wrong:** 1.10+ infers structured output from `-> str`; clients receive an extra structured block; `FastMCP.call_tool` returns a tuple (33 repo tests fail on `content[0].text`).
**Avoid:** `kwargs.setdefault("structured_output", False)` in `audit.install_audited_tools`.

### Pitfall 3: The Hermes handler answers `accept` with `{}`
**Avoid:** empty form, consent only from `action`; never require fields; do not use `ctx.elicit` with a required-field model.

### Pitfall 4: A hung elicit when the client cannot elicit (stateless HTTP)
**What goes wrong:** `check_client_capability` is `False` and `elicit_form` never returns (hangs to the full timeout).
**Avoid:** capability check first; wrap every elicit in `asyncio.timeout`.

### Pitfall 5: Identical prompt text coalesces in the Hermes gateway; `/approve all` resolves all
**Avoid:** unique code in each message, one window at a time per MCP process, each window gets its own full timeout counted from display.

### Pitfall 6: Late "Yes" after the server gave up
**What goes wrong:** the Hermes prompt stays up after the server's timeout; the user may still click.
**Why harmless:** the SDK ignores the response for an unknown request id (stderr noise only); no permit exists. Put "действует 5 минут" in the text; log the stderr line is expected.

### Pitfall 7: Float formatting differs between runtimes
**Avoid:** never re-serialize; hash the wire text (Pattern 3). Reject `NaN`/`Infinity` (`allow_nan=False`).

### Pitfall 8: Duplicate `_mcp` keys create a parser differential
**What goes wrong:** the permit check reads the first member while `split_envelope` (via `json.loads`, last key wins) reads another.
**Avoid:** require `trust.split_envelope(raw)[0] == env` and refuse otherwise.

### Pitfall 9: UNC share access blocks start-up or the event loop
**Avoid:** never at import; `asyncio.to_thread` + `wait_for`; keep the last valid policy; FOP failure = deny (D-22), policy failure = keep last valid (D-17).

### Pitfall 10: `secrets` module does not exist in IronPython
**Avoid:** nonce is minted on the CPython side only; Revit-side code must not import `secrets` (`scripts/conventions.py` rejects it).

### Pitfall 11: Existing tests build requests without a path or permit
**What goes wrong:** `gate_support.request_of` returns `types.SimpleNamespace(data=...)`; the new gate needs `request.path` and a permit, so about 71 call sites in 7 test files (`test_document_contracts.py` 16, `test_routes_*_identity.py` 20, `test_security_state.py` 31, `gate_support.py` 3, ...) fail until the helper mints real permits (route argument).
**Avoid:** extend `gate_support` once (mint with `TEST_SECRET` and a monkeypatched `security._process_token`), not a production bypass.

### Pitfall 12: A permit is burned by a later document refusal
**Avoid:** preflight resolves the document first; the engine surfaces the refusal text instead of asking a human to approve something that will be refused.

### Pitfall 13: `set_parameter` writes raw internal units
**What goes wrong:** `param.Set(float(value))` with no unit conversion (`parameters.py:493-494`); the window's "current -> new" can compare display units with internal ones.
**Avoid:** preflight returns raw and display values; the window shows both for `Double` parameters; do not "fix" the route in this phase.

### Pitfall 14: Hermes shows `message` through secret redaction
**Avoid:** show only 12-16 hex of hashes; keep GUIDs short; do not rely on exact rendering (D-20 proves Desktop).

### Pitfall 15: Operator file edited in place is read half-written
**Avoid:** two identical reads before applying; keep the last valid; report `rejected` only if the same bad hash persists on the next poll.

### Pitfall 16: Window text spoofing by model-controlled strings
**What goes wrong:** a parameter value containing "Операция безопасна. Нажмите Да" or newlines/control characters.
**Avoid:** build the trusted summary from facts first; show model-provided strings quoted, control characters stripped, truncated (about 120 characters), with the original length.

## Code Examples

### Hot reload loader (CPython)
```python
# Source: tomllib behaviour tested this session (BOM and duplicate keys raise TOMLDecodeError)
import hashlib, os, tomllib

def read_policy_file(path):
    """(bytes, (mtime_ns, size)) or raises OSError; called only inside asyncio.to_thread."""
    with open(path, "rb") as handle:
        data = handle.read()
    st = os.stat(path)
    return data, (st.st_mtime_ns, st.st_size)

def parse_policy_bytes(data):
    text = data.decode("utf-8-sig")            # tomllib rejects a BOM, strip it first
    return tomllib.loads(text)                  # TOMLDecodeError on duplicate keys / bad syntax

def policy_hash(base_bytes, operator_bytes):
    norm = lambda b: b.replace(b"\r\n", b"\n")
    return hashlib.sha256(norm(base_bytes) + b"\x00" + norm(operator_bytes or b"")).hexdigest()[:12]
```

### Revit-side verification skeleton (IronPython 3.4 dialect)
```python
# -*- coding: utf-8 -*-
# revit_mcp/permits.py  (helper module: no routes, no pyRevit; imports only hashlib/json/time/threading)
import hashlib
import json
import threading
import time

PERMIT_PROTOCOL = 1
MAX_TTL = 120
SKEW = 5
REGISTRY_CAP = 4096
_LOCK = threading.Lock()
_CONSUMED = {}      # nonce -> exp


def check_and_consume(route, raw_text, envelope_first, permit, key, session_token, now):
    """Return "ok" or a verdict word. Never raises; the registry is touched only on success."""
    try:
        if not isinstance(permit, dict) or permit.get("v") != PERMIT_PROTOCOL:
            return "unsupported_version" if isinstance(permit, dict) else "missing"
        # ... MAC over the pinned string, route, session, args hash of the split core text, ttl ...
        with _LOCK:
            for nonce in [n for n, e in _CONSUMED.items() if e + SKEW < now]:
                del _CONSUMED[nonce]
            if permit["n"] in _CONSUMED:
                return "replayed"
            if len(_CONSUMED) >= REGISTRY_CAP:
                return "registry_full"
            _CONSUMED[permit["n"]] = permit["e"]
        return "ok"
    except Exception:
        return "malformed"
```
(Verdict ordering: signature before route/session/args so tampering never leaks which field differed beyond the verdict word.)

### Guard-test skeleton (derives from the AST inventory)
```python
# Source: pattern of tests/unit/test_phase5_gate_wiring.py and inventory_support.py (read this session)
from inventory_support import route_inventory, manifest_names

def test_base_policy_covers_every_route_and_tool(base_policy):
    routes = {r.key for r in route_inventory()}
    assert set(base_policy["routes"]) >= routes
    assert set(base_policy["tools"]) == set(manifest_names())
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No server-side elicitation (mcp 1.9.0, spec 2025-03-26) | Form-mode elicitation in `ctx.elicit`/`session.elicit_form` since mcp 1.10.0 (spec 2025-06-18); URL mode and 2025-11-25 in 1.30.0 | 2025-06-26 | Enables D-05 |
| `FastMCP` + `ClientSession` (1.x) | `MCPServer` + `Client` (2.x, spec 2026-07-28), `httpx2` | 2026 (2.0.0) | Out of scope for Phase 7; revisit as its own phase |
| `BuiltInParameterGroup` overloads | `ForgeTypeId`/`GroupTypeId` overloads | obsolete 2024, removed 2025 | `edit_family` shared-parameter code at risk on Revit 2025+ |
| `tests: content[0].text` | `FastMCP.call_tool` returns `(content, structured)` unless `structured_output=False` | mcp 1.10 | Kept stable by the default |

**Deprecated/outdated:** `ServerSession.elicit` (kept as an alias of `elicit_form` in 1.30.0 with a deprecation note: "new code should use elicit_form()"); the repo's 1.9.0 pin; `07-RESEARCH-NOTES` statement of 790 tests (current suite: 6361 tests, about 100 s).

## Threat Model and Security Domain (ASVS L1, block on high)

`security_enforcement` is not disabled in `.planning/config.json` (only `workflow.use_worktrees`/`_auto_chain_active` present), so this section is required. Decision rule for the plan checker: any `high` residual without a test or documented decision blocks.

### Applicable ASVS categories

| ASVS Category | Applies | Standard Control in this phase |
|---------------|---------|--------------------------------|
| V1 Architecture | yes | One enforcement point per runtime (`bridge.revit_post`, `gate_or_response`); deny by default |
| V2 Authentication (service) | yes | Phase 5 shared secret (constant time) + per-operation HMAC permit; not a human identity |
| V3 Session management | partial | Permit nonce single-use; process incarnation binding (`session_token`); no cookies |
| V4 Access control | yes | Policy allow/confirm/deny per route; unknown = deny; closed set of gated routes with sentinel AST test |
| V5 Input validation | yes | TOML schema/closed vocabulary; strict wire parsing; untrusted strings sanitized in the window; `allow_nan=False` |
| V6 Cryptography | yes | HMAC-SHA256 (stdlib on CPython; RFC 2104 over `hashlib` in IronPython, vector-tested); key derived from the secret; constant-time compare; no hand-rolled primitive beyond HMAC glue |
| V7 Error handling and logging | yes | Audit of denied/expired/rejected_permit; secret redaction unchanged; no body or secret in refusal text |
| V8 Data protection | yes | No BIM data leaves the machine (D-21: no Jev); window shows only what the user already addressed |
| V10 Malicious code | partial | `execute_code` stays trusted arbitrary code (D-15); confirm is not a content check |
| V12/V13 Files / API | partial | UNC read of FOP/operator files bounded by timeout; JSON bodies stay `text/plain` |
| V14 Configuration | yes | Operator file ACL, hot reload with last-valid retention, payload-shipped base |

### Known threat patterns

| Pattern | STRIDE | Standard Mitigation | Residual |
|---------|--------|---------------------|----------|
| Agent forges approval in text or `approved=true` | Spoofing | Consent only from `ElicitResult.action == "accept"` on the server's own request; arguments never consulted | none (tested) |
| Agent with same OS rights reads `_bridge_secret` and mints permits or POSTs directly | Elevation | **Not mitigated by design** (D-18; REQUIREMENTS Out of Scope "Защита от целенаправленного локального обхода"); document in CLAUDE.md and `bridge.py` docstring; permit blocks curl/LAN/old payload only | **high, accepted by D-18; must be written down (SAFE-18)** |
| Replay of a captured permit | Tampering/Repudiation | Revit-side nonce registry, 60 s TTL, session binding | low |
| Permit reused for different args/route/process/document | Tampering | MAC over route, args-text hash, session token; explicit document in body | low |
| Clone of an approved call after Hermes redelivery to a fresh server | Repudiation | New window every time; optional duplicate memory | medium (user decision) |
| Operator file weakened by an agent with share write access | Tampering | ACL on the share (outside code); last-valid retention; hash in audit | medium, documented |
| Invalid/partial operator file silently weakens rules | Tampering | Whole-file validation; base remains; first-invalid -> base; invalid base -> block | none (tested) |
| Window text injection by model-controlled strings | Spoofing | Trusted summary first, quoted/truncated untrusted strings, unique code | low |
| Concurrent windows approved by one click (`/approve all`, coalescing) | Tampering | Unique text, serialized windows, one permit per call | low |
| Policy changed between approval and send | Tampering | Hash compare after approval; permit carries `p` | low |
| Facts changed between approval and send (e.g. 340 -> 4000 instances) | Tampering | Re-run preflight, facts digest compare; else re-ask | low |
| FOP check bypass by changing app-level shared-parameter file path | Tampering | Compare by GUID+name content; re-check after approval; `execute_code` can still do it | medium, documented limit |
| Preflight open reads leak model facts to LAN callers | Information disclosure | Same exposure class as the seven existing open reads; Routes binds loopback (`bind` status) | low |
| `execute_revit_code` content abuse after one "Yes" | Elevation | Confirm per call with code/length/SHA-256 and explicit warning; cannot check content | accepted (D-12) |
| Cross-process handler overlap cross-wires a request (backlog 999.1) | Tampering | Permit is bound to the request's own bytes (a cross-wired request carries its own permit); does not fix 999.1, must not be claimed | accepted, documented |
| SDK supply chain (new transitive wheels) | Tampering | Lock review checkpoint, `--only-binary`, pin `<2` | low |
| Stdout corruption by new modules | DoS | `test_audit_stdio.py` extended to the new root modules | none (tested) |
| SMB hang on policy/FOP read | DoS | worker thread + timeout, never at import | low |

## Validation Architecture

> `workflow.nyquist_validation` is absent from `.planning/config.json`, which means enabled.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8 (`[dependency-groups] dev`), anyio plugin for `@pytest.mark.anyio` (existing pattern with an `anyio_backend` fixture) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options] testpaths = ["tests/unit"]`; shared fixtures `tests/unit/conftest.py` (audit dir isolation, bridge network isolation) |
| Quick run command | `uv run pytest tests/unit/test_policy_*.py tests/unit/test_permit_*.py tests/unit/test_phase7_*.py -q` |
| Full suite command | `uv run pytest tests/unit -q` (measured on this machine: 6361 passed, 3 skipped, about 100 s; 07-RESEARCH-NOTES' "790 tests, 6.66 s" is stale) |
| Cold start gate | `python tests/test_init_latency.py` (limit 2.0 s); payload gate `deploy/gate.py` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SAFE-01 | Confirm op blocked without positive answer; text `approved=true`/args ignored; nothing sent | unit (fake ctx + machine) + protocol (real SDK in-memory session with `elicitation_callback`) | `uv run pytest tests/unit/test_phase7_channel.py -q` | No, Wave 0 |
| SAFE-02 | No capability / decline / cancel / raise / timeout all block with distinct reasons; stateless HTTP blocks | protocol | same file | No, Wave 0 |
| SAFE-03 | Wait happens before the lock: a second call proceeds while the first waits; no `state.lock` held during elicit | unit (`test_target_locks.py` style) | `uv run pytest tests/unit/test_phase7_wait_unlocked.py -q` | No, Wave 0 |
| SAFE-04 | `session`-style accept grants one call; identical concurrent windows do not coalesce (unique code); windows serialized | unit | `test_phase7_channel.py` | No, Wave 0 |
| SAFE-05 | Message contains tool/document/args/reasons/facts; "неизвестно" for unknowns; hostile strings sanitized; <= length cap | unit (pure message builder) | `uv run pytest tests/unit/test_policy_messages.py -q` | No, Wave 0 |
| SAFE-06 | Policy covers manifest tools + AST routes + preflight routes; unknown = deny; expectation table literal | unit (AST) | `uv run pytest tests/unit/test_policy_inventory.py -q` | No, Wave 0 |
| SAFE-07 | `check parameter_write` truth table (type/multiple/overwrite/unknown/group); delete/transform/load/edit/execute confirm; allow set | unit | `uv run pytest tests/unit/test_policy_decisions.py -q` | No, Wave 0 |
| SAFE-08 | FOP parse (UTF-16/UTF-8/BOM), GUID+name match, ambiguous, unreadable -> deny; Cyrillic exact | unit with fixture files | `uv run pytest tests/unit/test_policy_fop.py -q` | No, Wave 0 |
| SAFE-09 | TOML schema, overlay, closed vocabulary, hash, units; payload copies data file | unit | `uv run pytest tests/unit/test_policy_loader.py tests/unit/test_payload_ships_root_modules.py -q` | partly (payload test exists, extend) |
| SAFE-10 | Invalid/partial/unreachable operator file keeps last valid; first-invalid -> base; invalid base -> block; atomic swap under threads; no loop block on slow share | unit (+ `time` fakes) | `test_policy_loader.py` | No, Wave 0 |
| SAFE-11 | Permit round trip CPython->Revit helper; golden vectors; every negative (replay, 1-char args change, route, session, expiry, ttl, MAC, malformed, envelope not first, duplicate `_mcp`, non-ASCII, dict body) | unit | `uv run pytest tests/unit/test_permit_protocol.py -q` | No, Wave 0 |
| SAFE-12 | Every gated route refuses without permit before any document/transaction touch; sentinel AST: gate calls permits; 32-thread concurrent consume = exactly 1 ok; open reads unaffected | unit (reuse route harness) + AST | `uv run pytest tests/unit/test_phase7_gate_wiring.py tests/unit/test_permit_concurrency.py -q` | No, Wave 0 |
| SAFE-13 | Approval discarded when policy hash or facts digest changed | unit | `test_phase7_channel.py` | No, Wave 0 |
| SAFE-14 | `/status/` advertises `permit.protocol`; missing permit -> 403 text with the RU hint; old-ext tolerance via `scan_envelope_tolerance` + real gate with extra key | unit + script | `uv run pytest tests/unit/test_phase7_rollout.py tests/unit/test_scan_envelope_tolerance.py -q` | partly |
| SAFE-15 | Audit labels/fields (`denied`, `expired`, `rejected_permit`), reason words, `Audit:` line, no implicit error signal in `format_response`; label count pin updated | unit | `uv run pytest tests/unit/test_audit_entry.py tests/unit/test_format_response.py tests/unit/test_phase7_audit.py -q` | partly (update pins) |
| SAFE-16 | No resend after `unknown` (machine counts exactly one POST); same permit twice -> 2nd refused | unit | `test_phase7_channel.py`, `test_permit_protocol.py` | No, Wave 0 |
| SAFE-17 | Execute window shows code head, length, SHA-256 (16 hex) and the warning; tool still registered | unit | `test_policy_messages.py` | No, Wave 0 |
| SAFE-18 | Pinned documentation sentences (bypass limits, 999.1, readable secret) in CLAUDE.md/bridge docstring | unit (pattern of `test_serialization_scope_docs.py`) | `uv run pytest tests/unit/test_phase7_scope_docs.py -q` | No, Wave 0 |
| SAFE-19 | FastMCP registration, `user_request` schema on all 59 tools, no `outputSchema`, stdio purity incl. new modules, 3 transports smoke, init latency | unit + scripts | `uv run pytest tests/unit/test_audit_registration.py tests/unit/test_audit_stdio.py -q; python tests/test_init_latency.py` | yes (extend) |
| SAFE-20 | Live bench (Hermes Desktop) scenarios Yes/No/timeout/redelivery/changed args/direct curl; HMAC vectors and `float` repr probe inside Revit | manual, user-run after full Revit restart | `tests/test_phase7_live_*.py` pattern (like `tests/test_phase5_live_gate.py`) | No, Wave 0 (script + validator test) |
| SAFE-21 | ROADMAP wording | manual review | - | - |

### Sampling Rate
- **Per task commit:** the quick command above plus the touched module's existing test file.
- **Per wave merge:** `uv run pytest tests/unit -q` (about 100 s) and `python tests/test_init_latency.py`.
- **Phase gate:** full suite green on mcp 1.30.0, `deploy/gate.py` from a scratch payload layout green (`GATE_OK`, `INIT_LATENCY_S` < 2.0), then `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/unit/conftest.py` autouse fixture installing a permissive test authorizer in `bridge` (production default is fail-closed) so the ~hundreds of existing tests that call `bridge.revit_post` keep working.
- [ ] `tests/unit/gate_support.py`: `request_of(body, route=...)` and `enveloped_body(...)` mint a real permit (test secret, monkeypatched session token); update the ~71 call sites in `test_document_contracts.py`, `test_routes_*_identity.py`, `test_security_state.py`.
- [ ] `tests/unit/inventory_support.py` and `test_phase2_inventory.py`: new route class for preflight reads, named exceptions for routes no tool addresses, new counts; `test_phase5_gate_wiring.py`: 56/41/15/34/7 pins -> 59/44/15/34/10 and `D02_OPEN` literal; `scripts/conventions.py` open list and `LOCAL_MODULES` (+ `permits`), contributor kit rebuild (`scripts/build_contrib_kit.py`).
- [ ] `tests/unit/test_audit_entry.py:138` label count 12 -> 15; field-set pins.
- [ ] Shared fixtures: fake `ctx` (session with `check_client_capability`/`elicit_form` scripted), real SDK in-memory elicitation harness (`mcp.shared.memory` style) with Hermes-shaped callback, policy fixtures (valid/invalid/partial TOML, FOP files in UTF-16 LE/UTF-8), clock fake.
- [ ] Framework install: none (pytest present); install mcp 1.30.0 via the planner's `uv lock`/`uv sync` after the human-verify checkpoint.
- [ ] Live-bench script and its offline validator (user-run only).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | lock, sync, payload recipe | yes | 0.11.1 | - |
| CPython dev | tests | yes | 3.13.7 (`.venv`), 3.14.2 system | - |
| pyRevit embeddable CPython (fleet engine) | payload import test | yes (`pyRevit-Master\bin\cengines\CPY3123`) | 3.12.3 | - |
| IronPython 3.4.2 (netfx engine DLLs) | float repr probe | yes (hosted via Windows PowerShell; no stdlib) | 3.4.2 | live probe inside Revit for stdlib-dependent checks |
| HermesFork repo (read-only) | handler reading | yes | `mcp==2.0.0` client pin (`pyproject.toml:184,256`) | - |
| Live Revit + pyRevit Routes | live bench (D-20) | **not probed** (not started, per constraints) | - | user-run bench |
| `\\Srv-dfs\...` share (FOP, operator file) | D-22 / policy | **not accessed** (per constraints) | - | fixtures; unreachable = deny |
| Hermes Desktop | D-20 | not available to this research | - | user-run bench |
| Port 8000 | HTTP smoke | occupied by another process (PID 68852, untouched) | - | wrapper script sets `mcp.settings.port` |

**Missing dependencies with no fallback:** none for planning. **With fallback:** live Revit/Hermes Desktop/share are covered by the user-run bench and fixtures.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | FOP file format and encoding (tab-separated `*META/*GROUP/*PARAM`, UTF-16 LE typical) | Gate 6 | Parser rejects the real file -> every shared parameter denied; fix by adjusting the sniffing; caught by a fixture made from a real FOP copy before the bench |
| A2 | Instance count of a type = elements of the type's category with `GetTypeId()` equal, via a collector, is exact and cheap enough | Gate 4 | Wrong counts shown; mitigate with a cap and "unknown" on overflow; verify in the live bench |
| A3 | Instance-parameter writes on group members can propagate to other group instances | Gate 4 / alt paths | Extra confirm triggered unnecessarily, or missed fan-out; verify on a disposable model |
| A4 | Hermes **Desktop** renders the `message` fully (newlines, ~1500 chars) and offers working Yes/No | Gate 2 | Window unreadable or truncated; D-20 bench; fall back to shorter text |
| A5 | `hmac.new` works in IronPython 3.4 | Gate 3 | None (not used); parity of the hand-rolled HMAC must be proven live |
| A6 | A Hermes redelivery after session loss always starts a fresh server process for stdio | Gate 3 | Same-process redelivery is covered anyway (new window, new permit) |
| A7 | The operator file's share ACL is read-only for ordinary users | Gate 8 | An agent with user rights could weaken fleet policy; deployment requirement to confirm |
| A8 | `libs\win32`, `libs\win32\lib`, `libs\pythonwin` (+ DLL dir) is sufficient on every workstation, not only this machine | Gate 1 | Server fails to start on some machines; covered by `warm.py` acceptance at update time |
| A9 | A 2.0.0 client talking to a **1.30.0** server negotiates and elicits in Hermes Desktop exactly as in my SDK-level test (which used a Hermes-shaped callback, not Hermes itself) | Gate 1 | Elicitation unavailable in the field; fall back path is 2.x (costly) or 1.10.1; D-20 bench decides |
| A10 | No Revit API exists to rename a project/shared parameter (nothing found) | Gate 7 | A missed D-23 operation; it would still be reachable only via `execute_revit_code` (already confirm) |
| A11 | `Element.GetDependentElements` is not an exact delete-cascade preview | Gate 4 | Missed cheaper "known dependents" fact; chosen to say "unknown" per D-09 |
| A12 | Revit 2024-2027 is the supported range and the fleet's actual version is unknown to this research | Gate 6 | The `BuiltInParameterGroup` finding may or may not bite; record version in the bench |

## Open Questions

1. **D-06 target version: 1.30.0 or 2.x?**
   - Known: 1.30.0 passes everything with two small, tested changes (shim, `structured_output=False`); 2.x needs a rename/migration touching `main.py`, `gate.py`, tests and httpx2.
   - Unclear: whether the user wants to match the client generation anyway.
   - Recommendation: 1.30.0 now; schedule 2.x as its own phase. Because D-06 is "costly", the plan should contain a `checkpoint:human-verify` on the dependency bump.
2. **Classification of `start_revit`, `discover_revit_targets`, `get_revit_process_status`.** D-13 is silent. Recommendation: allow (no model mutation), recorded explicitly in the policy.
3. **`load_family` content can import shared parameters not in the FOP (D-22 hole).** Recommendation: keep confirm, show an explicit "содержимое семейства не проверяется" line; ask the user whether they want deny-unless-path-under-an-allowed-folder.
4. **Cancel vs expired mapping.** Hermes answers `cancel` on its own timeout. Recommendation: server timeout -> `expired`; client `cancel` -> `denied` with reason `approval_cancelled`; both non-executing, both worded "подтверждение не получено".
5. **Duplicate-operation memory (Hermes redelivery to a fresh server).** Optional Revit-side `(route, args_sha, session)` recent-consumption memory surfaced through preflight, escalating allow to confirm with "такая же операция уже выполнялась N с назад". Needs a user decision (D-02 lightness vs SC5 honesty).
6. **Operator file location and ACL.** Proposed `%MCP_SHARE_ROOT%\_build\operator_policy.toml` (beside `bridge_secret`), staged path file in the payload. Confirm with the operator who owns the share and its permissions.
7. **Explicit `document` injection** into bodies on confirm/check paths changes what the extension receives from a tool that omitted it (semantically narrower, never wider). Confirm acceptable; alternative is documenting the residual TOCTOU.
8. **Server instructions / docstrings.** Telling the model "denied/expired: do not retry blindly, never ask for approval in chat" requires editing `SERVER_INSTRUCTIONS` and tool docstrings, which tests pin. Include in the plan or skip.
9. **`edit_family` shared-parameter code on Revit 2025+** (removed `BuiltInParameterGroup` overload). Out of scope unless the user wants it fixed; the bench must record the Revit version.
10. **Hermes Desktop behaviours** (rendering, redaction, `/approve` handling) are unproven until D-20.

## Proposed Requirement IDs

Family `SAFE` (Безопасность мутаций). Each line is ready to paste into `REQUIREMENTS.md`; the mapping column ties it to ROADMAP success criteria (SC) and CONTEXT decisions.

- [ ] **SAFE-01** (SC1; D-05): Защищённая операция уровня confirm не выполняется без положительного ответа клиента через MCP elicitation; согласие агента в тексте и аргумент `approved=true` не принимаются.
- [ ] **SAFE-02** (SC1, SC5; D-05, D-07): Отсутствие capability, отказ, cancel, ошибка клиента и таймаут блокируют операцию и различимы в ответе и в журнале.
- [ ] **SAFE-03** (D-07): Ожидание подтверждения идёт до захвата очереди и не держит транзакцию Revit; срок задаётся политикой (по умолчанию 300 с).
- [ ] **SAFE-04** (D-08): Один положительный ответ разрешает ровно один вызов с этими аргументами; «на сессию»/«всегда» и параллельные окна не расширяют охват.
- [ ] **SAFE-05** (SC2; D-09): Окно на русском показывает инструмент, документ, нормализованные аргументы, причины и точные read-only факты Revit; неточное показывается как «неизвестно».
- [ ] **SAFE-06** (SC2): Каждый инструмент и маршрут классифицирован в базовой политике; неклассифицированный путь отклоняется; тест-сторож падает на новый инструмент или маршрут без классификации.
- [ ] **SAFE-07** (SC2; D-10, D-11, D-12, D-13, D-23): Базовая политика по умолчанию подтверждает перезапись параметров типа/непустых/множественных значений, удаление, трансформации, загрузку и правку семейств, выполнение кода; создание и чтения разрешены.
- [ ] **SAFE-08** (SC2; D-22): Общие параметры создаются только из ФОП компании (GUID и имя); недоступный ФОП даёт отказ.
- [ ] **SAFE-09** (SC4; D-14, D-16): Политика — TOML, проверяется как данные; база едет в payload, файл оператора читается с share и применяется атомарно; версия/хеш видны.
- [ ] **SAFE-10** (SC4; D-15, D-17): Невалидная, недоступная или частично прочитанная политика оператора ничего не ослабляет; невалидная база блокирует защищённые операции; статус называет источник, версию и причину.
- [ ] **SAFE-11** (SC3; D-18): Одноразовое разрешение подписано HMAC и привязано к маршруту, точному телу запроса, процессу (session_token), версии политики, сроку и nonce.
- [ ] **SAFE-12** (SC3; D-18): Каждый закрытый не-GET маршрут расширения отклоняет запрос без действительного разрешения до любого эффекта; разрешение потребляется атомарно в `gate_or_response`; повтор, подмена, просрочка и чужой процесс отклоняются; тест-сторож закрыт по умолчанию.
- [ ] **SAFE-13** (SC4): Подтверждение не переживает смену политики и изменение фактов между «Да» и отправкой.
- [ ] **SAFE-14** (SC3; D-19): Выкладка payload-first; новое расширение со старым payload отказывает понятным текстом; старое расширение игнорирует новый ключ; статус сообщает протокол разрешений.
- [ ] **SAFE-15** (SC5): Журнал и ответ различают denied, expired, rejected_permit, committed, rolled_back, partial и unknown; подтверждение не выдаётся за выполнение; `format_response` не получает новых неявных сигналов ошибки.
- [ ] **SAFE-16** (SC5): После неизвестного исхода нет автоповтора; одно разрешение не выполняет мутацию дважды; повторная доставка клиента порождает новое окно.
- [ ] **SAFE-17** (SC6; D-12): `execute_revit_code` подтверждается на каждый вызов (код или начало, длина, SHA-256, предупреждение), путь остаётся доверенным исключением.
- [ ] **SAFE-18** (SC6): Границы обхода зафиксированы: произвольный код, ОС-доступ и читаемый секрет, cross-process overlap 999.1, содержимое `load_family`.
- [ ] **SAFE-19** (D-06): Обновление MCP SDK не ломает регистрацию FastMCP, обёртку аудита и `user_request`, чистоту stdout, три транспорта, cold start и импорт в payload.
- [ ] **SAFE-20** (SC7; D-20): Офлайн негативные и конкурентные тесты зелёные; отдельно разрешённый live bench в Hermes Desktop после полного перезапуска Revit.
- [ ] **SAFE-21** (D-15): ROADMAP-критерий 2 переформулирован: подтверждение — поведение базовой политики по умолчанию, а не неизменяемая гарантия.

Overlap to resolve in `REQUIREMENTS.md`: Future `POLICY-01..04` (config policy, preview + one-time token, second call, admin config) are superseded by SAFE-06..12 (elicitation replaces the two-call token); `IDEM-01..03` remain future (a permit nonce is not an idempotency key); `HYG-03` (SaveAs/export overwrite protection) remains future (D-13 allows these tools).

## Suggested Decomposition (for the planner)

1. **Wave 0 / SDK and plumbing:** dependency bump checkpoint, `uv lock`, pywin32 shim x3, `structured_output=False`, conftest authorizer fixture, `gate_support` permit minting, pin updates. Gate: full suite green on 1.30.0 and `gate.py` GATE_OK in a scratch payload layout.
2. **Policy core:** `policy.py` loader/validator/hot reload, `policy.base.toml`, classification guard test, decision checks, message builder.
3. **Permit core:** `permit.py`, `revit_mcp/permits.py`, wire format, vectors, concurrency tests, `trust.py` additions.
4. **Bridge integration:** authorizer hook, elicitation, window lock, post-approval re-checks, audit `record_decision`, status seam, `format_response` wording.
5. **Revit side:** `gate_or_response` permit step, `status_block` advertisement, three preflight routes, route/test inventory updates, conventions + kit.
6. **Deploy/docs:** `build-payload.cmd` copies and path staging, `config.cmd` variable, runbook updates, CLAUDE.md invariants, ROADMAP criterion 2, live-bench script (user-run) and pinned scope-docs test.

## Sources

### Primary (HIGH confidence)
- This repository, read this session: `bridge.py`, `audit.py`, `main.py`, `revit_mcp/security.py`, `trust.py`, `identity.py`, `parameters.py`, `editing.py`, `placement.py`, `transforms.py`, `code_execution.py`, `status.py`, `tools/utils.py`, `tools/editing_tools.py`, `tools/parameter_tools.py`, `tools/transform_tools.py`, `tools/code_execution_tools.py`, `tools/status_tools.py`, `deploy/build-payload.cmd`, `config.cmd`, `server.py`, `gate.py`, `warm.py`, `configure_hermes.py`, `tests/unit/gate_support.py`, `conftest.py`, `inventory_support.py`, `test_phase5_gate_wiring.py`, `test_payload_ships_root_modules.py`, `scripts/conventions.py`, `scan_envelope_tolerance.py`, `probe_ipy_trust.py`, CONTEXT/RESEARCH-NOTES/REQUIREMENTS/ROADMAP.
- HermesFork (read-only): `tools/mcp_tool.py` (2115-2307, 3714-3716, 5895-5960), `tools/approval.py` (2634-2673, 3015-3017, 4177-4230, 5305-5389), `pyproject.toml`.
- pyRevit routes source: `pyrevitlib\pyrevit\routes\server\server.py`, `router.py`, `base.py` (request path is the API-relative path, e.g. `/set_parameter/`; headers are not populated from the HTTP request).
- Experiments (scratchpad, nothing in the repo modified): SDK wheels `mcp-1.10.0`, `mcp-1.30.0`, `mcp-2.3.0` inspected; scratch venvs with 1.30.0 server and 2.0.0 client (accept/decline/cancel/raise/no-capability/timeout/late answer/Cyrillic); full unit suite on 1.30.0 with and without `structured_output=False`; `tools/list` comparison against 1.9.0; transports; payload-layout import and `gate.py` runs with the pyRevit CPython 3.12.3 engine; IronPython 3.4.2 hosted float/`len` probe; TOML and HMAC round trips.
- PyPI: https://pypi.org/pypi/mcp/json , https://pypi.org/pypi/mcp/1.11.0/json , https://pypi.org/pypi/mcp/1.15.0/json

### Secondary (MEDIUM confidence)
- https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0 and `.../v1.30.0` (release notes)
- https://py.sdk.modelcontextprotocol.io/migration/ (2.x migration: `MCPServer`, constructor/transport changes, httpx2, elicitation gate, stdout redirect)
- https://rvtdocs.com/diff/Autodesk.Revit.DB.BindingMap/?from=2024 and https://rvtdocs.com/diff/Autodesk.Revit.DB.FamilyManager/?from=2024 (member lists, obsolete/removed overloads)
- https://blog.autodesk.io/setting-parameter-varies-between-groups/ and rvtdocs `InternalDefinition` (`SetAllowVaryBetweenGroups`, `VariesAcrossGroups`)

### Tertiary (LOW confidence)
- Shared-parameter file layout and encoding (A1), Revit behaviours marked `[ASSUMED]`, Hermes Desktop rendering (A4): not verified.

## Metadata

**Confidence breakdown:**
- Standard stack / SDK upgrade: HIGH - versions, wheel contents, full suite, payload recipe and gate were run.
- Elicitation channel and Hermes behaviour: HIGH for SDK semantics and handler code; MEDIUM until the Desktop bench (A4, A9).
- Permit scheme: HIGH for design and runtime parity facts (float repr executed in IronPython 3.4.2); registry/consume design verified by reading the gate and handler model, not yet implemented.
- Preflight facts and D-22: MEDIUM - Revit API behaviours unverified live (A1-A3, A11).
- Pitfalls: HIGH - most were reproduced.

**Research date:** 2026-10-25
**Valid until:** 2026-11-25 for stable parts (stack, Hermes code, permit design); re-check `pip index versions mcp` and the Hermes handler before implementation if either repo moves.
