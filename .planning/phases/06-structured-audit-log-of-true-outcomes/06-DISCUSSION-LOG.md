# Phase 6 (was 5): Structured audit log of true outcomes - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-23
**Phase:** 05-structured-audit-log-of-true-outcomes
**Areas discussed:** Где пишется журнал, Корреляция, Схема записи, Что не пишется, Размещение и рост, Проверка
**Mode:** `--auto` — пользователь поручил принять все рекомендованные решения самостоятельно.

---

## Где пишется журнал

| Option | Description | Selected |
|--------|-------------|----------|
| CPython, `_revit_call`, из блока `outcome` ответа | Один писатель на файл; истинный исход приходит в ответе после фазы 3 | ✓ |
| Сторона Revit рядом с `commit_and_report` | Два Revit = два писателя; нужен файл на процесс; нетестируемо под CPython | |
| Обёртка инструмента по возвращённой строке | Повторяет эвристику `format_response` — журнал намерения | |

| Option | Description | Selected |
|--------|-------------|----------|
| Писать и попытки, не дошедшие до Revit (`not_sent`) | Честная запись отказов | ✓ |
| Только дошедшие до Revit | Отказы невидимы в журнале | |

**User's choice:** [auto] рекомендованные варианты.

---

## Корреляция

| Option | Description | Selected |
|--------|-------------|----------|
| Обёртка `mcp.tool` при регистрации + `contextvars` | Ноль правок в 54 инструментах, есть имя инструмента | ✓ |
| `call_id` на каждый HTTP-запрос | Не связывает несколько запросов одного инструмента (AUDIT-04) | |
| Передавать id из каждого инструмента вручную | 54 правки | |

**User's choice:** [auto] рекомендованный вариант.

---

## Что не пишется

| Option | Description | Selected |
|--------|-------------|----------|
| Список разрешённых полей; без значений параметров; путь только хешем | AUDIT-08, Pitfall 13 | ✓ |
| Полный payload запроса | Утечка секрета и данных | |
| Полный путь к модели | Лишние данные в журнале, который могут переслать | |

**User's choice:** [auto] рекомендованный вариант.

---

## Размещение и рост

| Option | Description | Selected |
|--------|-------------|----------|
| Файл на процесс сервера в `%LOCALAPPDATA%\RevitMCP\audit\`, ротация + лимит каталога | Нет чередования и сбоя ротации Windows | ✓ |
| Один общий файл | Чередование строк, `PermissionError` при ротации | |
| Сетевая шара | Блокирующий сетевой ввод-вывод на каждой мутации | |

| Option | Description | Selected |
|--------|-------------|----------|
| `logging` + `QueueHandler`/`QueueListener`, `propagate=False` | Не блокирует event loop, не пишет в stdout | ✓ |
| Прямой `open().write()` в async-коде | Блокирует loop, риск stdout-путаницы | |

**User's choice:** [auto] рекомендованные варианты.

---

## Проверка

| Option | Description | Selected |
|--------|-------------|----------|
| Unit на фикстурах + stdio-тест потока + живой стенд (откат, partial, два Revit) | Все 7 критериев, без перезапуска Revit | ✓ |

**User's choice:** [auto] рекомендованный вариант.

## Claude's Discretion

- Размеры ротации и порог каталога, отдельный `audit.py` или внутри `bridge.py`.

## Deferred Ideas

- Инструмент чтения журнала, централизованный сбор, значения параметров «до/после».
