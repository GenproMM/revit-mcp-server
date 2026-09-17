---
tags: [debugging, revit-2027, compatibility, elementid]
date: 2026-09-04
---

# Bare DB.ElementId(int) в Revit 2027 падает на неоднозначности перегрузок

**Статус:** обойдено · зафиксировано в коде · актуально для 2027+

## Симптом

В Revit 2027 вызов `DB.ElementId(12345)` падает с ошибкой:

> Multiple targets could match

Тот же код работает в 2024, 2025 и 2026.

## Причина

В Revit 2027 у конструктора `ElementId` появились новые перегрузки — под
`BuiltInParameter`, `BuiltInCategory` и `Int64`. Для IronPython обычный Python `int`
теперь подходит сразу под несколько из них, и CLR не может выбрать целевую перегрузку.

Это не бага Revit и не бага pyRevit — это следствие расширения API, на которое
динамическая типизация IronPython реагирует именно так.

## Обход

Явно указывать тип через `System.Int64`:

```python
import System
DB.ElementId(System.Int64(12345))
```

В проекте это инкапсулировано в `make_element_id` — см.
[[ElementId читается и создаётся только через хелперы]]:

```python
try:
    import System
    return DB.ElementId(System.Int64(int_val))       # однозначно в 2027
except (TypeError, OverflowError, ImportError):
    pass
return DB.ElementId(int_val)                          # фолбэк для старых версий
```

## Почему это отдельно важно для execute_code

Внутри `exec` хелперы из `revit_mcp/utils.py` недоступны. Поэтому в пространство имён
маршрута **предымпортированы** `clr` и `System` — специально чтобы вызывающий мог
использовать 2027-безопасный паттерн. Комментарий в
`revit_mcp/code_execution.py` объясняет это прямо, называя вещи своим именем:
«a common foot-gun».

## Смежная разница версий

`ElementId.Value` (Int64) заменил `IntegerValue` в новых релизах. Чтение тоже идёт через
хелпер, с цепочкой фолбэков.

> [!danger] Новый код с `element.Id.IntegerValue` сломается на Revit 2027
> Это самая частая мина при правках Revit-половины.

## Урок

> В IronPython расширение набора перегрузок в .NET-API — это **breaking change**, даже
> если старая перегрузка никуда не делась. Типизировать аргумент явно дешевле, чем
> отлаживать «Multiple targets could match» на чужой машине.

## Связанное

[[ElementId читается и создаётся только через хелперы]] ·
[[Revit API доступен только внутри процесса Revit]] ·
[[execute_code остаётся аварийным люком для отсутствующих инструментов]]
