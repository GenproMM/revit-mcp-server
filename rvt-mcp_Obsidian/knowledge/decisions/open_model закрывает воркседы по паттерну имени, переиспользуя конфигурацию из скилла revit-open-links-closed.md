---
tags: [decision, worksharing, new-tool, external-skill]
date: 2026-09-08
---

# open_model закрывает воркседы по паттерну имени, переиспользуя конфигурацию из скилла revit-open-links-closed

## Решение

Новый маршрут `POST /open_model/` (`revit_mcp/worksharing.py`) открывает
модель с диска, всегда применяя `WorksetConfiguration`, и по умолчанию
детачит с сохранением рабочих наборов (`DetachAndPreserveWorksets`).
Компаньон `POST /model_worksets/` читает рабочие наборы файла **без
открытия** — превью перед решением, что закрывать.

## Обоснование

До этой сессии в проекте не было ни одного маршрута, открывающего модель:
`execute_code` не подходит — он всегда оборачивает тело в транзакцию, а
`OpenDocumentFile`/`OpenAndActivateDocument` транзакцию не терпят вообще (см.
[[Save и SaveAs выполняются вне транзакции]] — тот же класс ограничения API,
что и `SaveAs`). Пункт бэклога 8 в [[Текущие приоритеты]] отдельно называл
эту потребность: «портировать `open_revit_server_model` из `GenproMCP`» —
инструмент другого, внутреннего MCP-сервера компании (`genpro-revit-mcp`),
недоступного на этой машине без сети компании.

Прямого доступа к `GenproMCP` не было, но пользователь указал на скилл
`revit-open-links-closed` в приватном репозитории `GenproMM/MastermindServices`
(ветка `master`, доступна локально через `git fetch` — репозиторий приватный,
но клонирован на машину заранее). Скилл описывает открытие федеративной
модели с Revit Server с закрытыми связями (`#_RVT_LINK` в имени workset'а) —
цель другая (`RSN://`, связи), но код в `references/worksets-config.md`
конфигурации `WorksetConfiguration` — это в точности то, что нужно локальному
маршруту:

```python
worksets_preview = WorksharingUtils.GetUserWorksetInfo(model_path)
link_ids = [wp.Id for wp in worksets_preview if "#_RVT_LINK" in wp.Name.upper()]
config = WorksetConfiguration(WorksetConfigurationOption.OpenAllWorksets)
if link_ids:
    config.Close(link_ids)
options.DetachFromCentralOption = DetachFromCentralOption.DetachAndPreserveWorksets
options.SetOpenWorksetsConfiguration(config)
```

Тот же файл явно документирует, почему **не** `CloseAllWorksets` (элементы
закрытого набора невидимы `FilteredElementCollector`, а конфигурация
применяется только один раз при открытии — «открыть закрыто, потом
дооткрыть» нереализуемо) и не `OpenLastViewed` (непредсказуемо, зависит от
прошлой сессии автора файла). Оба ограничения перенесены как есть — они не
специфичны для Revit Server, это общее поведение API.

Локальный маршрут обобщил `#_RVT_LINK` до произвольного списка паттернов
(`close_worksets_matching`, по умолчанию `["#_RVT_LINK"]`) — тестовая модель
сессии реальных `#_RVT_LINK`-наборов не содержала, паттерн проверен на
кириллических именах («Подложки», «Скрытые»).

## Логика маршрута

```
GetUserWorksetInfo(model_path)  — без открытия
config = WorksetConfiguration(OpenAllWorksets)
config.Close([ws.Id for ws in worksets if любой паттерн ⊆ ws.Name.upper()])
options.DetachFromCentralOption = preserve|discard|none
options.SetOpenWorksetsConfiguration(config)
HOST_APP.uiapp.OpenAndActivateDocument(model_path, options, False)
```

Не-workshared файл детектится тем же `GetUserWorksetInfo` (пустой список без
ошибки — не через `BasicFileInfo.IsWorkshared`, которое на части версий
Revit возвращает `None`) и открывается вообще без детача/конфигурации —
Revit отвергает оба на не-workshared файле.

## Как это применять

> [!warning] Запуск Revit из командной строки с workshared-моделью
> Открывает диалог выбора рабочих наборов, который вешает headless
> Routes-сервер навсегда — см. [[Модальный диалог Revit вешал headless-сервер
> навсегда]]. `open_model` обходит именно этот диалог, явно передавая
> `WorksetConfiguration` — без неё Revit *всегда* спрашивает.

## Проверка

Живой прогон на реальной 98 МБ модели (13 рабочих наборов, два закрыты по
паттерну): открытие детачем — 21 с без диалога, заголовок документа получил
суффикс `_отсоединено` от самого Revit (подтверждение детача), затем
сохранение как центральный (см. [[SaveAs детач-модели требует
WorksharingSaveAsOptions.SaveAsCentral]]) и повторное чтение
`model_worksets` на сохранённом файле — все 13 наборов на месте.

## Связанное

[[SaveAs детач-модели требует WorksharingSaveAsOptions.SaveAsCentral]] ·
[[Модальный диалог Revit вешал headless-сервер навсегда]] ·
[[Разработчики инструментов работают без доступа к репозиторию]] ·
[[2026-09-08 — семь пользовательских сценариев на живой модели, детач-open, edit_family, фикс section-view и unicode-пробника]]
