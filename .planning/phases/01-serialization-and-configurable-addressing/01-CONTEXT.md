# Phase 1: Serialization and configurable addressing - Context

**Gathered:** 2026-09-23
**Status:** Ready for planning
**Mode:** `--auto` — все серые зоны выбраны автоматически, по каждому вопросу принят рекомендованный вариант (по поручению пользователя). Альтернативы — в `01-DISCUSSION-LOG.md`.

<domain>
## Phase Boundary

Мутирующие вызовы, выпущенные этим MCP-сервером, больше не уходят в однопоточный Revit API
параллельно; `/status/` и чтения не ждут мутаций; порт pyRevit Routes задаётся настройкой
развёртывания `REVIT_PORT`, а не константой. Требования: SER-01…SER-05, IDENT-05.

Вне фазы: секрет, идентичность, мультидокумент, мультиинстанс-адресация в одном процессе,
журнал аудита. Никаких правок в `revit_mcp/` — фаза целиком на CPython-стороне и не требует
перезапуска Revit (кроме одной живой проверки порта).

</domain>

<decisions>
## Implementation Decisions

### Размещение транспорта
- **D-01:** Транспорт выносится из `main.py` в новый модуль `bridge.py` в корне репозитория:
  `_get_client`, `_revit_call`, замок, разбор порта. `main.py` импортирует и передаёт в
  `register_tools` те же три callable `revit_get` / `revit_post` / `revit_image` — контракт
  инъекции не меняется, ни один `tools/*_tools.py` не правится. Причина: `bridge.py`
  импортируется в тестах без `FastMCP` и регистрации 54 инструментов. `deploy/build-payload.cmd`
  получает строку `copy` для `bridge.py`; `tests/unit/test_local_bridge_transport.py`
  (сейчас читает текст `main.py`) перенаправляется на `bridge.py`.
- **D-02:** Один модульно-глобальный `asyncio.Lock`, создаваемый лениво при первом POST.
  Один процесс сервера говорит ровно с одной целью (host и port фиксируются при импорте),
  поэтому глобальный замок и есть «замок на цель». Реестр `RevitTarget` по `(host, port)` из
  исследования **не** строится — адресации нескольких инстансов в одном процессе нет в
  требованиях (отложено).
- **D-03:** Замок берётся на **каждый POST** через `revit_post`, без классификации «мутирующий
  или нет» по инструментам. Все мутации в кодовой базе — POST; несколько читающих POST
  (`check_clashes`, `ai_element_filter`) тоже встанут в очередь — это приемлемая цена за
  отсутствие списка, который может разойтись с кодом. GET (`revit_get`) и `revit_image` замок
  не трогают никогда — это и есть SER-02.
- **D-04:** Только `async with lock:` — никаких ручных `acquire`/`release`. Исключение, таймаут
  httpx и `CancelledError` освобождают очередь сами (SER-03).

### Бюджет времени
- **D-05:** Таймаут HTTP-запроса (30 с по умолчанию или переданный `timeout`) отсчитывается
  **после** захвата замка — ожидание в очереди не съедает бюджет вызова (SER-04).
- **D-06:** Ожидание замка ограничено отдельным сроком: `REVIT_QUEUE_TIMEOUT`, по умолчанию
  120 с. По истечении вызов **не отправляется** в Revit и возвращает строку в существующем
  контракте `_revit_call`: `"Error: Revit is busy — a previous mutating call from this server
  has not finished after N s; nothing was sent"`. Никакой позиции в очереди и ETA (Out of Scope).
- **D-07:** Если замок занят и передан `ctx`, один раз отправляется `await ctx.info(...)`
  «ожидаю завершения предыдущей мутации» — под `if ctx:`, никогда `print()`.

### Настраиваемый порт
- **D-08:** `REVIT_PORT` читается из окружения при импорте `bridge.py`, по умолчанию `48884`.
  Разбор — чистая функция (`_resolve_port(value)`), тестируемая отдельно. Нечисловое значение или
  вне 1–65535 → запуск падает с ясным сообщением в **stderr** (stdout — поток протокола). Тихий
  откат на 48884 запрещён: он отправил бы вызовы не тому Revit.
- **D-09:** Документация обновляется в той же фазе: sharp edge в `CLAUDE.md` («порт захардкожен»)
  переписывается, `README.md`, `deploy/README.md`, `deploy/USER-GUIDE.md` — пример блока env с
  `REVIT_PORT`. `deploy/configure_hermes.py` не трогается, пока порт по умолчанию.

### Честная область действия
- **D-10:** Область сериализации записана явно в докстринге `bridge.py`, в `CLAUDE.md`
  (Known sharp edges) и в README: замок покрывает только вызовы **этого процесса** MCP-сервера.
  Второй MCP-клиент (второй процесс сервера), curl и прямой `/execute_code/` его обходят — это
  снижение вреда, не гарантия корректности (SER-05).

### Тесты и проверка
- **D-11:** Новый `tests/unit/test_bridge_serialization.py` на `httpx.MockTransport` с обработчиком,
  удерживаемым `asyncio.Event`; асинхронные тесты через плагин pytest из `anyio`
  (`@pytest.mark.anyio`) — без новой зависимости. Покрыть: второй POST ждёт первый; GET
  проходит, пока POST держит замок; исключение и отмена освобождают замок; таймаут HTTP
  считается после захвата; срок очереди даёт строку «busy» без отправки; разбор `REVIT_PORT`.
- **D-12:** Живая проверка критерия 5 на стенде: второй Revit, которого pyRevit ставит на 48885,
  и `REVIT_PORT=48885` → `/status/` отвечает заголовком документа именно второго инстанса.
  Перед проверкой — `Get-NetTCPConnection -LocalPort 48885 -State Listen` ровно одна строка.
- **D-13:** Попутный живой эксперимент (исследовательский флаг из STATE.md): что делает очередь
  внешних событий Revit сегодня с двумя перекрывающимися POST (висит / ошибка / сериализует).
  Результат записывается в докстринг `bridge.py` как обоснование, что замок даёт, — не блокирует фазу.
- **D-14:** `python tests/test_init_latency.py` остаётся < 2.0 с — `bridge.py` не импортирует
  ничего тяжелее `httpx`.

### Claude's Discretion
- Точные имена функций внутри `bridge.py`, текст сообщений, форма фикстур MockTransport.
- Нужна ли переменная `REVIT_QUEUE_TIMEOUT` в пользовательской документации или только в `CLAUDE.md`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Объём и требования
- `.planning/ROADMAP.md` §Phase 1 — цель и 6 критериев успеха
- `.planning/REQUIREMENTS.md` §Сериализация (SER), §Идентичность IDENT-05
- `.planning/PROJECT.md` §Context — «пул httpx: 20 соединений, ни замка», «порт 48884 захардкожен в `main.py:23`»

### Исследование
- `.planning/research/PITFALLS.md` §Pitfall 5 (замок совещательный), §Pitfall 6 (голодание `/status/`), §Pitfall 7 (замок после отмены), §Pitfall 8 (`stateless_http` → замок модульно-глобальный)
- `.planning/research/ARCHITECTURE.md` §Question 3 — размещение сериализации (реестр по цели сознательно не берётся, см. D-02)
- `.planning/research/STACK.md` — `asyncio.Lock` против `Semaphore(1)` и очереди

### Код
- `main.py:21-102` — текущий транспорт, переносится в `bridge.py`
- `deploy/build-payload.cmd:109-116` — список копируемых файлов payload
- `tests/unit/test_local_bridge_transport.py` — проверка `trust_env=False`, перенацелить
- `CLAUDE.md` §Known sharp edges — строки про порт и 30-секундный таймаут

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_revit_call` (`main.py:76-102`): единственная точка выхода HTTP к Revit; оборачивается, а не переписывается.
- Контракт «не-200 → строка `Error: <code> - <text>`» — очередь и отказы используют его же.

### Established Patterns
- Инъекция `revit_get`/`revit_post`/`revit_image` в каждый регистратор — сохраняется без изменений.
- `trust_env=False` у клиента — обязателен (коммит `f0af5b0`), переносится в `bridge.py`.
- Нельзя `print()` в stdio-режиме; прогресс только `await ctx.info(...)` под `if ctx:`.

### Integration Points
- `main.py` → `from bridge import revit_get, revit_post, revit_image`.
- `deploy/build-payload.cmd` и `deploy/gate.py` — `bridge.py` должен попасть в payload и пройти gate.

</code_context>

<specifics>
## Specific Ideas

- Сообщение об отказе по очереди должно прямо говорить «nothing was sent», чтобы модель не
  считала операцию, возможно, выполненной.

</specifics>

<deferred>
## Deferred Ideas

- Реестр `RevitTarget` и адресация нескольких Revit-инстансов из одного процесса сервера (поаргументный `port`) — отдельная возможность, не в v0.1.
- `contrib-kit/revitmcp_kit.py` с захардкоженным `48884` — отдельный клиент, настраиваемость порта там не входит в IDENT-05.
- Разделение POST на «мутирующие» и «читающие» для более узкой очереди — только если очередь начнёт мешать на практике.

</deferred>

---

*Phase: 01-serialization-and-configurable-addressing*
*Context gathered: 2026-09-23*
