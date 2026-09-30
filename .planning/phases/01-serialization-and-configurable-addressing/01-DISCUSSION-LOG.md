# Phase 1: Serialization and configurable addressing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-23
**Phase:** 01-serialization-and-configurable-addressing
**Areas discussed:** Размещение и форма замка, Бюджет времени, Настраиваемый порт, Честная область действия и проверка
**Mode:** `--auto` — пользователь поручил принять все рекомендованные решения самостоятельно.

---

## Размещение и форма замка

| Option | Description | Selected |
|--------|-------------|----------|
| Новый `bridge.py`, один глобальный `asyncio.Lock` | Тестируется без FastMCP; один процесс = одна цель | ✓ |
| Реестр `RevitTarget` по `(host, port)` с замком на цель | Рекомендация исследования под мультиинстанс; в требованиях нет адресации нескольких инстансов | |
| Оставить всё в `main.py` | Меньше файлов, но тест тянет регистрацию 54 инструментов | |

| Option | Description | Selected |
|--------|-------------|----------|
| Замок на каждый POST | Без списка «мутирующих» инструментов, который может разойтись с кодом | ✓ |
| Замок только на классифицированные мутирующие инструменты | Уже очередь, но нужен поддерживаемый список | |

**User's choice:** [auto] рекомендованные варианты.

---

## Бюджет времени

| Option | Description | Selected |
|--------|-------------|----------|
| Таймаут HTTP после захвата + отдельный срок очереди 120 с | SER-04 и нет бесконечного ожидания | ✓ |
| Ожидание без срока | Может висеть вечно при зависшем Revit | |
| Один общий таймаут на ожидание и запрос | Нарушает SER-04 | |

**User's choice:** [auto] рекомендованный вариант.

---

## Настраиваемый порт

| Option | Description | Selected |
|--------|-------------|----------|
| `REVIT_PORT`, неверное значение → падение запуска с сообщением в stderr | Громкий отказ вместо тихого обращения к 48884 | ✓ |
| Неверное значение → откат на 48884 с предупреждением | Тихо отправит вызовы не тому Revit | |

**User's choice:** [auto] рекомендованный вариант.

---

## Честная область действия и проверка

| Option | Description | Selected |
|--------|-------------|----------|
| Область записана в докстринге, CLAUDE.md и README; тесты на MockTransport + anyio | SER-05; без новой зависимости | ✓ |
| Только комментарий в коде | Недостаточно для SER-05 | |

**User's choice:** [auto] рекомендованный вариант.

## Claude's Discretion

- Имена функций, тексты сообщений, фикстуры тестов, упоминание `REVIT_QUEUE_TIMEOUT` в пользовательских документах.

## Deferred Ideas

- Реестр нескольких Revit-целей в одном процессе сервера.
- Порт в `contrib-kit/revitmcp_kit.py`.
- Более узкая очередь по классификации POST.

---

# Revision 2026-09-30 — interactive discussion with the user

**Mode:** interactive (default). Supersedes 2026-09-23 D-03, D-06, D-12 — see CONTEXT.md revision note.
**Areas discussed:** Roadmap reorder, Модель выбора экземпляра, Ключ замка сериализации, Живая приёмка REVIT_PORT, Бюджет времени в очереди

**Trigger:** the user asked to verify that after this phase users can address a specific model
via MCP while parallel Revit sessions and other models are open. Finding: Phase 1 as planned
delivers only instance targeting by port (one instance per MCP entry, active document only);
document addressing, PID identity and two-listener refusal were in Phase 4.

---

## Roadmap reorder

| Option | Description | Selected |
|--------|-------------|----------|
| Переставить фазы | Bring identity/multi-document forward | ✓ |
| Оставить как есть | Accept that the scenario lands in Phase 4 | |
| Влить в фазу 1 | Merge IDENT/AMBIG/MDOC into Phase 1 | |

| Option | Description | Selected |
|--------|-------------|----------|
| Разделить фазу 4 | IDENT-01..04+AMBIG+MDOC → new Phase 2; live secret/integrity wiring → later phase | ✓ |
| Влить в фазу 1 | Phase 1 = SER + all IDENT + AMBIG + MDOC | |
| Только порядок 1→2→4→3→5 | Move Phase 4 before Phase 3 without splitting | |

**User's choice:** Split Phase 4.

---

## Модель выбора экземпляра

| Option | Description | Selected |
|--------|-------------|----------|
| Один MCP-сервер на порт | REVIT_PORT fixed per process; two entries for two Revit | ✓ |
| Инструмент переключения цели | set_revit_target(port); shared state under stateless_http | |
| Аргумент port в каждом вызове | Optional port on all 54 tools | |

| Option | Description | Selected |
|--------|-------------|----------|
| Экземпляр в конфиге, документ в вызове | Per-entry instance, per-call document in Phase 2 | ✓ (with note) |
| Один сервер видит все Revit | Discovery across 48884..4888x | |

**Notes:** "Первый вариант, но важно чтобы в одной сессии можно было вызвать несколько документов,
в том числе в разных экземплярах Revit. Например для сравнения данных между документами."

| Option | Description | Selected |
|--------|-------------|----------|
| Громко упасть при старте | stderr message, no start | ✓ |
| Вернуться к 48884 с предупреждением | Silent-ish fallback | |

| Option | Description | Selected |
|--------|-------------|----------|
| Да, в get_revit_status | host:port added CPython-side | ✓ |
| Нет, всё в фазе 2 | | |

---

## Ключ замка сериализации

| Option | Description | Selected |
|--------|-------------|----------|
| Один замок на цель host:port | Per-target; one per process today | ✓ |
| Замок на документ | Rejected: Revit API single-threaded per process | |

| Option | Description | Selected |
|--------|-------------|----------|
| Все POST, кроме явно помеченных | Fail-safe default + read-only allowlist with unit test | ✓ |
| Все POST без исключений | Long read-POSTs block mutations | |
| Только явно помеченные мутации | Unmarked new tool races silently | |

| Option | Description | Selected |
|--------|-------------|----------|
| Да, все три | execute_code, open_model, save_document under lock | ✓ |
| Только execute_code | | |

---

## Живая приёмка REVIT_PORT

| Option | Description | Selected |
|--------|-------------|----------|
| Два Revit + проверка автосдвига | Verify 48884/48885 each one listener, different PIDs | ✓ |
| Один Revit на другом стартовом порту | pyrevit configs routes port 48890 | |

| Option | Description | Selected |
|--------|-------------|----------|
| Да | Cross-instance comparison scenario in acceptance | ✓ |
| Нет, только в фазе 2 | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Остановиться и пересмотреть адресацию | Phase 1 not accepted if no auto-increment | ✓ |
| Принять фазу 1 и передать в фазу 2 | | |

---

## Бюджет времени в очереди

| Option | Description | Selected |
|--------|-------------|----------|
| Отдельный предел + явная ошибка | Timeout starts after acquire; "NOT sent" error on wait overrun | ✓ |
| Ждать без предела | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Равен таймауту вызова | Default 30 s | ✓ |
| Фиксированный, настраиваемый env | REVIT_QUEUE_TIMEOUT | |
| На усмотрение Claude | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Отпустить сразу, исход «неизвестен» | Per SER-03 | ✓ |
| Держать, пока Revit не освободится | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Одно ctx.info при начале ожидания | No position/ETA | ✓ |
| Нет | | |

---

## Claude's Discretion

- Lock primitive and allowlist location; how get_revit_status learns host:port without importing the transport; error message wording.

## Deferred Ideas

- Single server discovering all instances; runtime target-switch tool; non-switching reads of addressed documents (Phase 2 constraint).
