# Phase 4 (was 3): Honest outcomes on every mutating route - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-23
**Phase:** 03-honest-outcomes-on-every-mutating-route
**Areas discussed:** Охват миграции, Единая форма исхода, Видимость частичного отказа, Проверка
**Mode:** `--auto` — пользователь поручил принять все рекомендованные решения самостоятельно.

---

## Охват миграции

| Option | Description | Selected |
|--------|-------------|----------|
| Все ~30 голых `.Commit()` + запрет проверкой конвенций | TRUTH-01 требует все маршруты | ✓ |
| Только `delete_elements` и `export_ifc` | Закрывает TRUTH-02, но не TRUTH-01 | |

**User's choice:** [auto] рекомендованный вариант.

---

## Единая форма исхода

| Option | Description | Selected |
|--------|-------------|----------|
| Блок `outcome` рядом с существующими ключами | Не ломает докстринги, одна схема для аудита | ✓ |
| Переименовать ключи всех маршрутов в единую схему | Ломает контракт существующих инструментов | |
| Только счётчики `requested`/`succeeded` | Нарушает TRUTH-03 (нужны id) | |

| Option | Description | Selected |
|--------|-------------|----------|
| success 200 / partial 200 / rolled_back 409 / failed 422 | Частичный отказ отличим и от успеха, и от полного отказа | ✓ |
| partial как 207 | `_revit_call` свернёт его в строку «Error», модель может повторить уже применённое | |
| partial как ошибка | Неправда: часть изменений сохранена | |

| Option | Description | Selected |
|--------|-------------|----------|
| `delete_elements` остаётся «всё или ничего» | Удаление подмножества хуже отказа | ✓ |
| `delete_elements` переходит на partial | Молча удалит часть | |

**User's choice:** [auto] рекомендованные варианты.

---

## Видимость частичного отказа

| Option | Description | Selected |
|--------|-------------|----------|
| Явная ветка `partial` в `format_response` + пара тестов | Отказы видны, `has_error` не трогается | ✓ |
| Положиться на `message` | Успех-ветка покажет только сообщение, id отказов потеряются | |

**User's choice:** [auto] рекомендованный вариант.

---

## Проверка

| Option | Description | Selected |
|--------|-------------|----------|
| Unit-тесты + `/execute_code/` exec, один перезапуск в конце | Минимум перезапусков Revit | ✓ |
| Перезапуск Revit на каждый модуль | Дорого и рискованно | |

**User's choice:** [auto] рекомендованный вариант.

## Claude's Discretion

- Модуль для `classify_outcome`, имя построителя ответа, порядок миграции, смысл `item` у маршрутов создания.

## Deferred Ideas

- HYG-01, HYG-02, dry-run (POLICY-02).
