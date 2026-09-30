# Phase 4 (was 3): Honest outcomes on every mutating route - Context

> **Renumbered 2026-09-30** (roadmap reorder, `01-CONTEXT.md` D-01): this was Phase 3. Old→new: 1→1, 2→3 (secret/integrity logic), 3→4 (honest outcomes), 4→2 (identity/ambiguity/multi-document) + 5 (live secret/integrity wiring, split out), 5→6 (audit). Phase numbers inside this document use the OLD numbering.

**Gathered:** 2026-09-23
**Status:** Ready for planning
**Mode:** `--auto` — все серые зоны выбраны автоматически, по каждому вопросу принят рекомендованный вариант (по поручению пользователя). Альтернативы — в `03-DISCUSSION-LOG.md`.

<domain>
## Phase Boundary

Каждый мутирующий маршрут сообщает, что Revit действительно сделал: реальный
`TransactionStatus`, откат, частичный отказ пакета — никогда предполагаемый или свёрнутый
успех. Требования: TRUTH-01…TRUTH-04. Жёсткое предусловие фазы 5 (журнал аудита читает именно
форму ответа, заданную здесь).

Вне фазы: санитизация traceback (HYG-01), лимиты размера партии (HYG-02), журнал аудита,
идентичность документа в ответе.

</domain>

<decisions>
## Implementation Decisions

### Охват миграции
- **D-01:** На `commit_and_report` переводятся **все** голые `.Commit()` в `revit_mcp/`, а не
  только два названных в PROJECT.md (`editing.py:75` `delete_elements`, `interop.py:96`
  `export_ifc`). Инвентаризация на 2026-09-23 — около 30 мест в `annotation`, `building`, `colors`,
  `detail`, `documentation`, `editing`, `interop`, `mep`, `placement` (включая `ft.Commit()` в
  семейном документе), `rooms`, `structure`, `tags`, `transforms`, `view_management`. Планировщик
  перепроверяет список grep-ом. Без этого TRUTH-01 («все мутирующие маршруты») не выполнено.
- **D-02:** Регрессия запрещается проверкой: `scripts/conventions.py` и `tests/unit/test_conventions.py`
  отвергают `.Commit()` в `revit_mcp/` везде, кроме тела `commit_and_report` в `utils.py`. Тот же
  статический подход, что уже ловит `json.loads(request.data)` и прямой `ElementId`.

### Единая форма исхода
- **D-03:** Каждый ответ мутирующего маршрута получает стандартный блок `outcome` **рядом** с
  существующими ключами (`deleted_ids`, `changes` и т.п. не переименовываются — на них
  опираются докстринги инструментов):
  ```
  "outcome": {
    "transaction_status": "Committed" | "RolledBack" | ... | null,
    "requested": <int|null>,
    "succeeded": [<id или индекс входа>, ...],
    "failed": [{"item": <id или индекс>, "reason": "<str(exc)>"}, ...],
    "revit_failures": [<failures из commit_and_report>]
  }
  ```
  Одноэлементные маршруты тоже несут блок (`requested: 1`) — фаза 5 читает одну схему.
  — **Reversibility:** costly — блок `outcome` читают `format_response` и журнал аудита фазы 5;
  смена схемы — синхронная правка трёх потребителей.
- **D-04:** Статус и HTTP-код выбирает одна чистая функция `classify_outcome(committed,
  n_succeeded, n_failed)` (в `revit_mcp/textutils.py` или `revit_mcp/trust.py` — тестируется из
  CPython), а Revit-зависимый построитель ответа в `utils.py` её вызывает:
  - откат при `Commit()` → **409**, `status: "rolled_back"` (существующий контракт, без изменений);
  - зафиксировано, `failed` пуст → **200**, `status: "success"`;
  - зафиксировано, есть и успехи, и отказы → **200**, `status: "partial"`;
  - ни одного успеха при непустом `failed` → **422**, `status: "failed"` + ключ `error`.
  Ошибки валидации до открытия транзакции (400/404/503) остаются как есть.
- **D-05:** `delete_elements` сохраняет поведение «всё или ничего»: предварительная проверка всех
  id и 404 на первом отсутствующем. Частичное удаление подмножества хуже, чем отказ. Маршрут
  получает `commit_and_report` и блок `outcome`, но не статус `partial`.
- **D-06:** Маршруты, меняющие состояние вне транзакции (`Save`/`SaveAs`, `open_model`, экспорт,
  запись файлов), получают блок `outcome` с `transaction_status: null` и фактическим результатом
  вызова API. `export_ifc`, у которого экспорт идёт внутри транзакции, переходит на
  `commit_and_report`, как и остальные.
- **D-07:** `reason` в `failed` — только `str(exc)`, без traceback (HYG-01 отложен, новые утечки
  не добавляются).

### Видимость частичного отказа для модели
- **D-08:** `format_response` (`tools/utils.py`) получает явную ветку для `status == "partial"`:
  баннер `=== PARTIAL SUCCESS ===`, `message`, строка «Succeeded: N of M», список неудачных
  элементов с причинами. Это **не** новый сигнал ошибки — `has_error` и множество
  `error/failed/failure/exception` не меняются (запрет CLAUDE.md соблюдён). Без ветки
  успех-ветка вернула бы один `message`, и отказы исчезли бы.
- **D-09:** Пара тестов в `test_format_response.py` по образцу `rolled_back`: `partial`-словарь
  отображается с баннером и id отказавших элементов; тест-сигнал, что `partial` сознательно не
  входит в множество отказов. Плюс тест, что 422 `failed` доходит видимой ошибкой.

### Проверка
- **D-10:** Итерации без перезапуска Revit: чистая классификация — unit-тестами; маршруты — приёмом
  из CLAUDE.md (текст модуля через `/execute_code/`, `exec` в пространстве имён с
  `__package__ = "revit_mcp"` и фиктивным `api`). Один полный перезапуск Revit в конце фазы для
  живых критериев 1 и 4.
- **D-11:** Живой набор критерия 1: по одному маршруту на семейство — одноэлементный
  (`modify_element`), пакетный, экспорт (`export_ifc`). Критерий 4 — пакетный маршрут с
  поэлементным `continue` (не `delete_elements`, см. D-05); конкретный маршрут выбирает
  планировщик из `building`/`tags`/`colors`.

### Claude's Discretion
- В каком из чистых модулей живёт `classify_outcome`.
- Имя Revit-зависимого построителя ответа и порядок миграции модулей.
- Что считать `item` для маршрутов создания (индекс входа или созданный id).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Объём и требования
- `.planning/ROADMAP.md` §Phase 3 — цель и 4 критерия
- `.planning/REQUIREMENTS.md` §Честный результат (TRUTH)
- `.planning/PROJECT.md` §Context — два известных пропуска `commit_and_report`

### Исследование и история
- `.planning/research/PITFALLS.md` §Pitfall 11 — аудит лжёт, если исходы не честные; требуемая форма `{requested, succeeded, skipped, transaction_status, failures}`
- `.planning/debug/param-write-rolls-back.md` — откуда взялся `commit_and_report` и 409
- Память проекта «rolled_back 409 is load-bearing» — почему откат обязан быть не-200

### Код
- `revit_mcp/utils.py:83-135` — `suppress_warnings`, `commit_and_report`
- `revit_mcp/editing.py:227-270` — эталонная обработка отката (409) и `failed`
- `revit_mcp/editing.py:54-101`, `revit_mcp/interop.py:89-117` — два названных пропуска
- `tools/utils.py:5-107` — `format_response`, где добавляется ветка `partial`
- `tests/unit/test_format_response.py:151-190` — образец пары тестов
- `CLAUDE.md` §Non-negotiable invariants — транзакции, `suppress_warnings`, правило «dict is an error only if…»

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `commit_and_report()` уже возвращает `committed`, `transaction_status`, `failures`.
- Три маршрута уже мигрированы (`code_execution`, `parameters`, `editing.modify_element`) — образцы.

### Established Patterns
- Пакетные маршруты ловят поэлементные исключения, делают `continue` и отвечают `success` — именно это исправляется.
- `suppress_warnings(t)` сразу после `t.Start()` и его возвращаемый swallower передаётся в `commit_and_report`.

### Integration Points
- `format_response` — единственный отрисовщик на стороне MCP.
- Блок `outcome` — вход журнала аудита фазы 5.

</code_context>

<specifics>
## Specific Ideas

- Модели нужно видеть id неудачных элементов, а не только счётчик — иначе она не сможет исправить и повторить только их.

</specifics>

<deferred>
## Deferred Ideas

- Санитизация traceback в ответах (HYG-01).
- Лимиты размера партии (HYG-02).
- Dry-run для разрушительных инструментов — вместе с preview-токеном (POLICY-02).

</deferred>

---

*Phase: 03-honest-outcomes-on-every-mutating-route*
*Context gathered: 2026-09-23*
