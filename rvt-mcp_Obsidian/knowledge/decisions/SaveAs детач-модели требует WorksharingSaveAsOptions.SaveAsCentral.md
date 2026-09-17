---
tags: [decision, worksharing, persistence, revit-api]
date: 2026-09-08
---

# SaveAs детач-модели требует WorksharingSaveAsOptions.SaveAsCentral

## Решение

`save_document` определяет `as_central` сам, по `doc.IsWorkshared`, если
вызывающий не передал флаг явно. Для рабочей модели (в том числе только что
открытой через `open_model` с детачем) значение по умолчанию — `True`.

## Обоснование

Первая же попытка сохранить только что открытую детач-модель провалилась с
сообщением самого Revit API:

```
The document just had worksharing enabled or was opened detached, so
WorksharingSaveAsOptions.SaveAsCentral must be set to true for SaveAs.
Parameter name: options
```

Существовавший маршрут `save_document` (см. [[Save и SaveAs выполняются вне
транзакции]]) строил только голый `SaveAsOptions()` — рабочий путь для
обычного, не workshared документа, но Revit прямо отказывает в этом случае
для любого документа, который **когда-либо** был детачнут или получил
worksharing в этой сессии. Без этой опции сценарий «открыть с детачем и
сохранить результат» был в принципе недостижим — то есть половина
пользовательского сценария «открыть модель с детачем и сохранить рабочие
наборы» не работала, при том что сам детач (`open_model`) отрабатывал
корректно.

Установка `SaveAsCentral = True` — это не побочный эффект, а именно то, что
нужно: сохранение как новый центральный файл переносит рабочие наборы в
новый файл. Проверено вживую: сохранённый файл, прочитанный обратно через
`model_worksets`, показал все 13 рабочих наборов исходной модели, включая
два, что были закрыты при открытии (закрытие workset на **открытии** не
удаляет его из файла).

## Логика маршрута

```
если as_central не передан явно:
    as_central = doc.IsWorkshared
если as_central:
    ws_opts = WorksharingSaveAsOptions(); ws_opts.SaveAsCentral = True
    save_opts.SetWorksharingOptions(ws_opts)
doc.SaveAs(model_path, save_opts)
```

## Как это применять

> [!warning] Любой новый маршрут, вызывающий SaveAs на workshared документе
> Должен либо явно решить вопрос `WorksharingSaveAsOptions`, либо
> переиспользовать `save_document` целиком — Revit откажет молча-неявно
> (конкретным `ArgumentException`, но не раньше, чем вызов дойдёт до API) на
> любом документе, что хоть раз был детачнут в текущей сессии.

## Проверка

Живой прогон: `open_model` (detach=preserve) → `save_document` (as_central
по умолчанию) → `model_worksets` на сохранённом файле — все 13 рабочих
наборов на месте, включая два закрытых при открытии.

## Связанное

[[Save и SaveAs выполняются вне транзакции]] ·
[[open_model закрывает воркседы по паттерну имени, переиспользуя конфигурацию из скилла revit-open-links-closed]] ·
[[2026-09-08 — семь пользовательских сценариев на живой модели, детач-open, edit_family, фикс section-view и unicode-пробника]]
