---
tags: [decision, revit-api, compatibility, critical]
date: 2026-09-04
---

# ElementId читается и создаётся только через хелперы

## Решение

Никогда не трогать `ElementId.Value` или `.IntegerValue` напрямую и никогда не
конструировать `DB.ElementId(...)` вручную. Только две функции из
`revit_mcp/utils.py`:

- `get_element_id_value(element_or_id)` → `int`
- `make_element_id(id_value)` → `DB.ElementId`

## Обоснование

Между Revit 2024 и 2027 API идентификаторов менялся дважды:

- `ElementId.Value` (Int64) заменил `IntegerValue` в новых версиях.
- В Revit 2027 голый `DB.ElementId(<int>)` падает с «Multiple targets could match» из-за
  новых перегрузок под `BuiltInParameter` / `BuiltInCategory` / `Int64`.

Поддерживать четыре версии Revit пиннингом зависимостей нельзя — pyRevit один, а Revit
разный. Поэтому разница инкапсулирована в двух функциях, а определение версии
происходит в рантайме через `try`/`except`. Конфигурации не требуется.

См. [[Bare DB.ElementId(int) в Revit 2027 падает на неоднозначности перегрузок]].

## Как это работает

**Чтение** — duck typing плюс цепочка фолбэков:

```python
eid = element_or_id.Id if hasattr(element_or_id, "Id") else element_or_id
try:    return int(eid.Value)          # 2024+
except (AttributeError, TypeError): pass
try:    return int(eid.IntegerValue)   # старые
except (AttributeError, TypeError): raise ValueError(...)
```

Принимает и полный `Element`, и сырой `ElementId`. Возвращает обычный Python `int`,
пригодный для JSON. Кидает `ValueError` на `None` и на нечитаемом входе.

**Создание** — сначала `System.Int64`, потом `int`:

```python
try:
    import System
    return DB.ElementId(System.Int64(int_val))       # 2024+, однозначно в 2027
except (TypeError, OverflowError, ImportError): pass
return DB.ElementId(int_val)                          # фолбэк
```

## Как это применять

> [!danger] Новый код с `element.Id.IntegerValue` сломается на Revit 2027
> Это самая частая мина при правках Revit-половины.

В `execute_code` пространство имён специально содержит предымпортированные `clr` и
`System`, чтобы вызывающий мог использовать 2027-безопасный паттерн
`DB.ElementId(System.Int64(id))` — там хелперы недоступны.

## Хрупкость

Совместимость держится на цепочках `try`/`except`, и это **самые непокрытые тестами
высоколевериджные функции репозитория**. Они чистые, без зависимостей от Revit-хоста
на уровне логики — то есть их можно вытащить в CPython-импортируемый модуль и накрыть
тестами. См. [[Текущие приоритеты]].

## Связанное

[[Revit API доступен только внутри процесса Revit]] ·
[[Строки из Revit прогоняются через sanitize_string]] ·
[[Bare DB.ElementId(int) в Revit 2027 падает на неоднозначности перегрузок]]
