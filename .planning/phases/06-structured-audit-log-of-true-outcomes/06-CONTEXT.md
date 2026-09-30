# Phase 6 (was 5): Structured audit log of true outcomes - Context

> **Renumbered 2026-09-30** (roadmap reorder, `01-CONTEXT.md` D-01): this was Phase 5. Old→new: 1→1, 2→3 (secret/integrity logic), 3→4 (honest outcomes), 4→2 (identity/ambiguity/multi-document) + 5 (live secret/integrity wiring, split out), 5→6 (audit). Phase numbers inside this document use the OLD numbering.

**Gathered:** 2026-09-23
**Status:** Ready for planning
**Mode:** `--auto` — все серые зоны выбраны автоматически, по каждому вопросу принят рекомендованный вариант (по поручению пользователя). Альтернативы — в `05-DISCUSSION-LOG.md`.

<domain>
## Phase Boundary

Каждая мутация попадает в локальный структурный JSONL-журнал с тем же честным исходом, который
увидел клиент (откат как откат, частичный отказ как частичный отказ), с идентичностью документа и
процесса, общим идентификатором вызова, ограниченным ростом и без секрета.
Требования: AUDIT-01…AUDIT-08.

Вне фазы: инструмент чтения или поиска по журналу, централизованный сбор журналов, OpenTelemetry,
история на уровне элементов worksharing.

</domain>

<decisions>
## Implementation Decisions

### Где пишется журнал
- **D-01:** Журнал пишет **сторона CPython**, в `bridge.py`, на уровне `_revit_call` — там, где
  доступен сырой HTTP-ответ (код и разобранное тело) **до** сворачивания не-200 в строку. Источник
  исхода — блок `outcome` и `status`, которые вернул Revit (фаза 3), и `revit_identity` (фаза 4);
  журнал никогда не выводит успех заново через эвристику `format_response`. Причина выбора стороны:
  процесс сервера — единственный писатель своего файла даже при двух Revit (Pitfall 12); истинный
  исход приходит в ответе и так. — **Reversibility:** costly — перенос записи на сторону Revit
  потребует файла на процесс Revit и переделки корреляции.
- **D-02:** Записываются все POST (то же правило, что у очереди фазы 1), GET — никогда. Включая
  попытки, **не дошедшие** до Revit: отказ по двум слушателям, срок очереди, транспортная ошибка —
  с исходом `not_sent` / `transport_error`. Журнал честен и о том, что ничего не произошло.

### Корреляция вызова инструмента
- **D-03:** Идентификатор на вызов инструмента (AUDIT-04) задаётся без правки 54 функций: при
  регистрации инструментов `mcp.tool` оборачивается так, что каждый вызов инструмента ставит
  `contextvars`-значение `(tool_name, call_id=uuid4)`; `bridge` его читает. Все POST одного вызова
  инструмента получают один `call_id`. Нет значения → свой `call_id` на запрос. **Исследовательский
  флаг:** проверить, что интроспекция сигнатур FastMCP (`func_metadata` / `inspect.signature`)
  следует `__wrapped__` при `functools.wraps`, иначе обёртка сломает схемы параметров.
- **D-04:** `call_id` также кладётся в конверт `_mcp.call_id` — строки лога pyRevit можно
  сопоставить с записью журнала.

### Схема записи (schema 1)
- **D-05:** Поля: `ts` (UTC ISO, миллисекунды), `schema: 1`, `call_id`, `tool`, `route`, `method`,
  `http_status`, `outcome` (`success` | `partial` | `rolled_back` | `failed` | `rejected_auth` |
  `rejected_integrity` | `rejected_document` | `not_sent` | `transport_error`), `transaction_status`,
  `requested`, `succeeded` (id), `failed` (`[{item, reason}]`), `identity` (`pid`,
  `session_token`, `revit_version`, `port`, `document_title`, `document_path_sha` — первые
  12 hex SHA-256 полного пути), `duration_ms`, `parameter_names` (если есть в payload).
  — **Reversibility:** costly — внешние читатели журнала опираются на схему; поле `schema`
  заложено для эволюции.
- **D-06:** Ответ, в котором у мутирующего маршрута нет блока `outcome` (регрессия фазы 3),
  пишется с `outcome` из `status`, но с флагом `outcome_block_missing: true` — пропуск виден, а не
  маскируется под успех.

### Что не пишется (AUDIT-08)
- **D-07:** Запись строится **по списку разрешённых полей**, тело запроса целиком не пишется
  никогда. Не пишутся: конверт `_mcp` (секрет), значения параметров, полный путь к модели (только
  хеш и title), код `/execute_code/` (только длина и SHA-256). Id элементов и имена параметров
  пишутся.
- **D-08:** Редакция в одной функции-писателе: удалить `_mcp` и любые ключи, похожие на
  `secret|token|password`, до сериализации. Тест критерия 7 ищет значение секрета в файле после
  успешного вызова, отказа 401 и пути с исключением — ноль вхождений.

### Размещение, рост, параллельные процессы
- **D-09:** Каталог — локальный диск `%LOCALAPPDATA%\RevitMCP\audit\` (переопределение
  `REVIT_MCP_AUDIT_DIR`), не сетевая шара, не репозиторий; вне Windows — `~/.revit-mcp/audit/`.
- **D-10:** **Отдельный файл на процесс сервера:** `audit-<YYYYMMDD-HHMMSS>-<pid>.jsonl`. Два
  клиента MCP (или два сервера на 48884 и 48885 для двух Revit) никогда не пишут в один файл —
  нет чередования строк и нет сбоя ротации Windows на файле, открытом другим процессом (AUDIT-06).
  В каждой записи есть `port`.
- **D-11:** Рост ограничен с первой записи (AUDIT-07): `RotatingFileHandler` в процессе
  (5 MB × 3 резервных копии) плюс при старте удаление самых старых файлов, пока каталог не станет
  ≤ 50 MB.
- **D-12:** Стек записи — стандартный `logging`: выделенный логгер `revit_mcp.audit`,
  `propagate = False`, только файловый обработчик через `QueueHandler`/`QueueListener` (запись не
  блокирует event loop), свой JSON-форматтер с `ensure_ascii=False` в UTF-8 (кириллица в
  названиях). Никакого `StreamHandler`, никакого stdout (AUDIT-05).
- **D-13:** Сбой журнала никогда не ломает вызов инструмента: ошибка записи проглатывается,
  одно предупреждение в stderr на процесс.

### Проверка
- **D-14:** Unit: построение записи из фикстур ответов (success, partial, 409 rolled_back, 401,
  423, 412, not_sent), редакция, именование и очистка каталога, корреляция `call_id` через
  обёрнутый инструмент, тест stdout: запуск `main.py` по stdio с включённым журналом — поток
  протокола разбирается без мусора (критерий 4).
- **D-15:** Живая проверка на стенде: намеренный откат (`modify_element` с ошибкой уровня error) и
  частичный пакетный отказ дают записи с истинным исходом (критерий 2); два Revit (48884/48885) с
  двумя процессами сервера, мутации в оба — два файла без повреждений (критерий 5). Эта фаза не
  правит `revit_mcp/`, перезапуск Revit не нужен.

### Claude's Discretion
- Точные размеры ротации и порог каталога (в пределах «несколько МБ на файл, десятки МБ всего»).
- Имя модуля записи (`bridge.py` или отдельный `audit.py` рядом с ним — во втором случае
  `build-payload.cmd` копирует и его).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Объём и требования
- `.planning/ROADMAP.md` §Phase 5 — цель и 7 критериев
- `.planning/REQUIREMENTS.md` §Аудит (AUDIT), §Out of Scope (OpenTelemetry, поэлементная история)
- `.planning/phases/03-honest-outcomes-on-every-mutating-route/03-CONTEXT.md` — схема блока `outcome` (вход журнала)
- `.planning/phases/04-live-identity-ambiguity-refusal-and-multi-document-addressin/04-CONTEXT.md` — `revit_identity`, коды 412/404, отказы слушателей
- `.planning/phases/02-secret-gate-and-payload-integrity-unit-verified/02-CONTEXT.md` — конверт `_mcp`, 401/423
- `.planning/phases/01-serialization-and-configurable-addressing/01-CONTEXT.md` — `bridge.py`, правило «все POST»

### Исследование
- `.planning/research/PITFALLS.md` §Pitfall 11 (журнал намерения вместо исхода), §Pitfall 12 (параллельные писатели, ротация, блокирующая запись), §Pitfall 13 (утечка секрета и путей)
- `.planning/research/STACK.md` — `logging` + JSON-форматтер, `propagate = False`

### Код
- `main.py` / `bridge.py` — `_revit_call`, место записи
- `tools/__init__.py` — регистрация инструментов, место обёртки `mcp.tool`
- `CLAUDE.md` §Non-negotiable invariants — «Never print() in main.py under stdio»

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_revit_call` видит объект ответа httpx до свёртки в строку — единственное место с полным исходом.
- Автообнаружение регистраторов в `tools/__init__.py` — одна точка, где можно обернуть `mcp.tool`.

### Established Patterns
- stdout — поток протокола; всё диагностическое — в stderr или файл.
- Конверт `_mcp` (фаза 2) уже несёт служебные поля; `call_id` добавляется туда же.

### Integration Points
- `bridge.py` (запись), `tools/__init__.py` или `main.py` (контекст вызова инструмента), `deploy/build-payload.cmd` (если появится отдельный модуль).

</code_context>

<specifics>
## Specific Ideas

- Главный сценарий чтения журнала — коллега спрашивает «кто удалил эту стену и почему сказало success»: запись должна отвечать по id элемента.

</specifics>

<deferred>
## Deferred Ideas

- MCP-инструмент чтения или поиска по журналу аудита.
- Централизованный сбор журналов со станций.
- Запись значений параметров «до/после» — после решения команды о персональных данных в значениях.

</deferred>

---

*Phase: 05-structured-audit-log-of-true-outcomes*
*Context gathered: 2026-09-23*
