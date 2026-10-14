# Phase 2: Live identity, ambiguity refusal, and multi-document addressing - Discussion Log

> The 2026-09-23 `--auto` round below is historical. The 2026-10-14 interactive revision at the end supersedes conflicting choices; the canonical planning input is `02-CONTEXT.md`.

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-23
**Phase:** 04-live-identity-ambiguity-refusal-and-multi-document-addressing
**Areas discussed:** Механизм подключения, Идентичность, Отказ при двух слушателях, Мультидокумент, Живая проверка
**Mode:** `--auto` — пользователь поручил принять все рекомендованные решения самостоятельно.

---

## Механизм подключения

| Option | Description | Selected |
|--------|-------------|----------|
| Подмена `api.route` в `startup.py` до регистрации | Ноль правок в 23 доменах | ✓ |
| Декоратор на каждом маршруте | 52 правки, легко забыть на новом маршруте | |
| Подмена `routes.make_response` | Общая функция pyRevit, хрупко | |

| Option | Description | Selected |
|--------|-------------|----------|
| Payload и расширение включают конверт в одном изменении; выкат: сначала payload | Минимальное окно 401 | ✓ |
| Разные фазы для двух сторон | Длинное окно рассогласования | |

**User's choice:** [auto] рекомендованные варианты.

---

## Идентичность

| Option | Description | Selected |
|--------|-------------|----------|
| Вложенный `revit_identity` во всех ответах-словарях | Нет конфликта ключей и ложных сигналов ошибки | ✓ |
| Поля верхнего уровня | Конфликт с `document_title` в `/status/` | |
| Только в мутирующих ответах | Чтения тоже могут прийти не от того процесса | |

| Option | Description | Selected |
|--------|-------------|----------|
| Токен в `AppDomain`, переживает Reload | «Один раз на процесс» по IDENT-01 | ✓ |
| Токен на загрузку `startup.py` | Меняется при Reload | |

| Option | Description | Selected |
|--------|-------------|----------|
| Строка идентичности в `format_response` | Иначе успех-ветка покажет только `message` | ✓ |
| Без изменений `format_response` | Идентичность не дойдёт до модели у большинства мутаций | |

**User's choice:** [auto] рекомендованные варианты.

---

## Отказ при двух слушателях

| Option | Description | Selected |
|--------|-------------|----------|
| ctypes `GetExtendedTcpTable` перед каждым вызовом, без кэша | Быстро, без зависимостей, видит PID | ✓ |
| `psutil` | Новая зависимость в payload | |
| PowerShell `Get-NetTCPConnection` | ~1 с на вызов | |
| Проверять только перед мутациями | Чтения тоже могут прийти не от того процесса | |

| Option | Description | Selected |
|--------|-------------|----------|
| Ошибка проверки → пропустить, `unverifiable` в статусе | Не ломает не-Windows и сбой API | ✓ |
| Ошибка проверки → отказ | Отключит мост из-за самой проверки | |

**User's choice:** [auto] рекомендованные варианты.

---

## Мультидокумент

| Option | Description | Selected |
|--------|-------------|----------|
| `document` — предусловие над активным документом (412 при несовпадении) | Работает для всех маршрутов одинаково | ✓ |
| Перенацеливание `doc` на неактивный документ | Не проверено для UIDocument; маршруты читают `revit.doc` | |

| Option | Description | Selected |
|--------|-------------|----------|
| Без `document`: один документ → в него; несколько → 412 со списком | Никакого тихого угадывания (MDOC-03) | ✓ |
| Без `document` всегда в активный | Угадывание | |
| `document` всегда обязателен | Лишнее трение при одном документе | |

| Option | Description | Selected |
|--------|-------------|----------|
| Параметр `document` у всех инструментов с POST + проверка конвенций | Явная адресация в вызове (MDOC-02) | ✓ |
| Сессионный «активный документ» в bridge без параметра | Не удовлетворяет MDOC-02 | |

**User's choice:** [auto] рекомендованные варианты.

---

## Живая проверка

| Option | Description | Selected |
|--------|-------------|----------|
| Один перезапуск после зелёных unit-тестов, чек-лист 1–9, тест порчи на копии | Бюджет «один цикл перезапуска» | ✓ |
| Итерации с перезапуском на каждое изменение | Дорого, Reload роняет Revit | |

**User's choice:** [auto] рекомендованный вариант.

## Claude's Discretion

- Форма строки идентичности, тексты 412/404, имена помощников, идентичность в ответах-списках.

## Deferred Ideas (2026-09-23 snapshot)

- Перенацеливание на неактивный документ.
- Мультиинстанс-адресация из одного сервера — **superseded** by a5-a and the interactive round below; it is now in Phase 2.
- Перекрёстная сверка PID ответа и слушателя.

---

## Interactive revision — 2026-10-14

**Phase:** 02-live-identity-ambiguity-refusal-and-multi-document-addressin
**Areas discussed:** inactive-document reads and comparison, process selection, missing document, inactive-document mutation. The user chose to **update** the existing automatically generated context, not to accept it wholesale. This section records only answers actually received; earlier `--auto` mechanism proposals are not recast as user confirmations.

### Reading an inactive document and comparing models

| Option | Description | Selected |
|--------|-------------|----------|
| Only proven-safe addressed reads without UI switch | Read inactive documents only on routes validated against a nonactive `Document`; refuse other addressed reads | ✓ |
| Switch the active document for every addressed read | Simpler active-document reuse, but disturbs the engineer's Revit UI | |
| Refuse all reads of inactive documents | No inactive-document comparison within one process | |

**User's choice:** Read without switching the UI on proven-safe routes; unsupported addressed reads explicitly refuse. The minimum comparison is the **model summary and level list for two documents**. No broader safe-route list was confirmed.

### Selecting a Revit process

| Option | Description | Selected |
|--------|-------------|----------|
| Only process is implicit; multiple processes require exact selection | Refuse with process list if several; do not guess | ✓ |
| Always require a process selector | Explicit even for one process | |
| Choose a default/latest process when several exist | Convenient but risks acting on the wrong model | |

**User's choice:** List available processes with ports and identity, then pass an exact selector on subsequent calls. With exactly one process, an omitted selector may use it. With more than one, refuse and list candidates; after a restart, select afresh. This updates Phase 1's a5-a one-shared-entry decision and supersedes this log's old “multi-instance addressing deferred” entry.

### A mutation with no document selector

| Option | Description | Selected |
|--------|-------------|----------|
| Multiple documents: refuse and list | No silent guess based on the active UI document | ✓ |
| Multiple documents: use active | Implicitly chooses a document the caller did not name | |
| Require document even when only one is open | Strict, but adds friction in the unambiguous case | |

**User's choice:** Multiple open documents → refusal with list. The one-document case may proceed. The tool docstring must state the default (MDOC-03).

### Explicit mutation targeting an inactive document

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse with 412 (Recommended) | Ask for explicit activation first; no automatic UI change | ✓ |
| Activate then mutate automatically | Switches the UI as a side effect of the mutation | |
| Mutate without activating | Requires separately proven Document/UIDocument semantics across mutating routes | |

**User's choice:** “Отказ 412 (Recommended)”. The preceding question's tool result was interrupted/unknown; the user then gave this choice directly in a separate message, so it is confirmed without interpreting the interrupted result.

### Boundary changes and discretion

- The earlier D-01..D-05 proposals combining identity wiring with secret/integrity wiring belong to Phase 5, not the current phase. The `document` portion of an envelope remains a possible technical approach, not a mandate.
- The concrete process selector, document key, safe API for already-open document activation, listener enumeration and wrapper-signature preservation remain research/planning questions. No live bench findings were claimed in this discussion.
- Cross-session pyRevit handler synchronization remains backlog 999.1; this phase's per-target lock only serializes this MCP server process.

**Canonical decisions:** `02-CONTEXT.md`, revised 2026-10-14. No Phase 2 code or plan was created by this discussion.
