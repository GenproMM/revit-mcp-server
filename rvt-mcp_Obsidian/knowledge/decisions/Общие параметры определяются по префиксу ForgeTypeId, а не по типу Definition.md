---
tags: [decision, revit-api, shared-parameters, new-capability]
date: 2026-09-04
---

# Общие параметры определяются по префиксу ForgeTypeId, а не по типу Definition

## Решение

Для классификации параметра проекта как общего (shared) или обычного использовать
`InternalDefinition.GetTypeId().TypeId` и проверять префикс:

```python
_SHARED_TYPEID_PREFIX = "revit.local.shared"
_PROJECT_TYPEID_PREFIX = "revit.local.project"

def _classify_definition(definition):
    type_id = definition.GetTypeId().TypeId
    lowered = type_id.lower()
    if lowered.startswith(_SHARED_TYPEID_PREFIX):
        guid = type_id.split(":", 1)[1].split("-")[0]
        return True, guid, type_id
    if lowered.startswith(_PROJECT_TYPEID_PREFIX):
        return False, None, type_id
    return None, None, type_id
```

Реализовано в `revit_mcp/parameters.py` (`_classify_definition` и соседние хелперы
`_get_binding_kind`, `_get_binding_categories`, `_get_definition_data_type`,
`_get_definition_group_name`), выставлено наружу через новый маршрут
`GET /project_parameters/` и инструмент `list_project_parameters`
(`tools/parameter_tools.py`).

## Почему не так, как казалось очевидным

`isinstance(definition, DB.ExternalDefinition)` на `doc.ParameterBindings` **всегда
неверно** — общий параметр приобретает `InternalDefinition` в момент загрузки в
проект, и `BindingMap` в принципе не отдаёт `ExternalDefinition`. Полный разбор
ошибки: [[Определение общих параметров через ExternalDefinition ошибочно на BindingMap]].

Перекрёстно проверено вторым независимым методом —
`FilteredElementCollector(doc).OfClass(DB.SharedParameterElement)` + сверка по имени
через `spe.GetDefinition().Name` — совпадение 315/315 биндингов на живой модели.
ForgeTypeId-способ выбран основным, потому что не требует прохода коллектором по
всем `SharedParameterElement` документа (в этой модели их 607, большинство живёт
внутри семейств, а не привязано на уровне проекта).

## Форма ответа инструмента

`list_project_parameters(shared_only, prefix, search, summary_only)` возвращает:

- **summary**: `total`, `shared`, `non_shared`, `unclassified` (когда `GetTypeId()`
  не смог определить происхождение — старый API или встроенный параметр),
  `skipped` (биндинг не прочитался — не валит весь список), плюс разбивку по
  префиксу имени (`name.split('_')[0]`) отдельно для shared и non-shared.
- **parameters** (если не `summary_only`): `name`, `is_shared`, `guid`, `binding`
  (`instance`/`type`), `data_type`, `group`, `categories`.

`summary_only=true` — дешёвый режим для моделей с сотнями параметров, не тащит
полный список.

## Ограничения (задокументированы в докстринге инструмента)

- Область действия — только параметры, привязанные через Project Parameters
  (`Document.ParameterBindings`). Общие параметры, живущие внутри семейств, но не
  привязанные на уровне проекта, не попадают в список — так же, как и встроенные
  (built-in) параметры.
- `is_shared` может быть `None` (не `True`/`False`) — считается в `unclassified`.

## Как проверено

Без перезапуска Revit: реальный текст файла `parameters.py` выполнен через
`/execute_code/` в изолированном пространстве имён с фейковым `api`, перехватившим
зарегистрированный хендлер, вызван напрямую на `doc`. Результат совпал с ручной
прото-версией: 315 всего, 309/6, `shared_only=true&prefix=ADSK_` → 84. Реальный HTTP-
маршрут ещё не вызывался — нужен полный перезапуск Revit для регистрации.

## Связанное

[[Определение общих параметров через ExternalDefinition ошибочно на BindingMap]] ·
[[2026-09-04 — фикс кириллицы и правильный детект общих параметров, новый инструмент list_project_parameters]] ·
[[ElementId читается и создаётся только через хелперы]] ·
[[48 MCP-инструментов зеркалят 48 маршрутов pyRevit]]
