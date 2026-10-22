---
tags: [debugging, pyrevit, routes, revit-api, phase-2]
date: 2026-10-22
---

# Маршруты pyRevit без аргументов uiapp, uidoc, doc выполняются вне контекста Revit API

**Статус:** исправлено для четырёх маршрутов документов, подтверждено вживую 2026-10-22 · найдено живой приёмкой G4 плана 02-07

## Симптом

`POST /activate_document/` для сохранённого, допустимого документа вернул HTTP 500 `activation-failed`. Исключение `Autodesk.Revit.Exceptions.InternalException` («A managed exception was thrown by Revit or by one of its external applications») без вложенных исключений, стек — только `UIApplication.OpenAndActivateDocument(String)` и кадры интерпретатора IronPython. Окно Revit не переключилось, диалога не было. Чтения G3 на тех же маршрутах при этом давали верные данные, поэтому ошибка выглядела как проблема самой активации.

## Причина

В исходниках pyRevit (`pyrevitlib/pyrevit/routes/server/server.py`, `_handle_route`; `handler.py`, `wants_api_context`, `prepare_handler_kwargs`): обработчик запускается в контексте Revit API (внешнее событие `UI.ExternalEvent`, главный поток) **только если у функции есть аргумент `uiapp`, `uidoc` или `doc`**. Обработчик с одним `request` или вообще без аргументов выполняется «здесь», прямо в потоке HTTP-сервера. Четыре маршрута из планов 02-04…02-06 (`/documents/`, `/activate_document/`, `/document_summary/`, `/document_levels/`) объявляли только `request`, поэтому `OpenAndActivateDocument` вызывался вне потока Revit API и Revit его отклонял. Чтения вне потока API «случайно работали», поэтому наблюдение G3 пришлось снять заново.

## Что не помогло

Диагностика через `/execute_code/` не дала информации: он сначала открывает транзакцию на активном документе, и Revit отвечает «The active document is currently modifiable» — другая причина. Полезным оказалось добавление в ответ маршрута полных сведений об исключении (тип .NET, вложенные, стек), коммит `df1eb56`.

## Исправление

Обработчики стали `list_documents(uiapp)`, `activate_document(uiapp, request)`, `document_summary(uiapp, request)`, `document_levels(uiapp, request)`; везде используется инжектированный `uiapp`, не `HOST_APP` (коммиты `a3f84b9`, `23ce119`, `2764d51`). Охранный тест: каждый `@api.route`-обработчик в `documents.py` объявляет `uiapp`, `uidoc` или `doc`. Для всех изменяющих маршрутов (02-12…02-15) принято `(uiapp, doc, request)`.

## Правило

Любой новый маршрут обязан объявлять `uiapp`, `uidoc` или `doc`. Исключения известны и перечислены тестом 02-17: `/status/` (`revit_status(verbose)`) и `/model_info/` (`get_model_info()`); их поведение вне контекста API не менялось и проверяется отдельно.

Связано: [[Паттерн обработчика маршрута — валидация, транзакция, сериализация]], [[pyRevit Reload при включённых Routes валит Revit на первом же запросе]].
