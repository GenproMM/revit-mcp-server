---
tags: [debugging, pyrevit, routes, threading, crash, operations]
date: 2026-09-04
---

# pyRevit Reload при включённых Routes валит Revit на первом же запросе

**Статус:** обойдено процедурой · причина — баг в самом pyRevit, не в этом репозитории
· найдено при настройке окружения на живой машине

## Симптом

Revit.exe завершается молча — без диалога, без сообщения пользователю. В системном
логе Windows (`Get-WinEvent`, источник `.NET Runtime`) — `System.InvalidOperationException`
дважды подряд, оба раза один и тот же стек:

```
IronPython.Modules.PythonThread+ThreadObj.Start()          ← фоновый поток
  → PythonOps.PrintWithDest → ScriptIO.GetOutput
    → new ScriptConsole(...) → MetroWindow..ctor → Window..ctor
      → InputManager..ctor → InvalidOperationException
```

Порт `48884` при этом либо не слушается вовсе, либо любой HTTP-запрос к
`/revit_mcp/*` зависает без ответа и без ошибки — не 404, не connection refused,
именно бесконечное ожидание.

## Причина

Известный баг самого pyRevit —
[issue #3473](https://github.com/pyrevitlabs/pyRevit/issues/3473), воспроизводится
100%: при включённых Routes сервер, пересозданный во время **pyRevit Reload**,
падает на первом же входящем запросе. Сервер, поднятый при обычном **старте**
Revit, работает стабильно сколько угодно.

Это создаёт видимость случайности — я на этой же сессии дважды спровоцировал
падение: один раз кликнув pyRevit → Reload по привычной инструкции из README,
второй раз послав тестовый curl-запрос к ещё не зарегистрированному маршруту
сразу после reload (traceback `RouteHandlerNotDefinedException` печатался через
тот же фоновый поток и добивал то, что reload уже подготовил).

Механизм смерти — общий для обеих причин: два обработчика маршрутов без аргумента
`doc` (`revit_status()` в `revit_mcp/status.py`, `get_model_info()` в
`revit_mcp/model_info.py`) выполняются pyRevit на **фоновом потоке** HTTP-сервера,
а не в UI-потоке Revit. Любая запись в лог/консоль оттуда лениво создаёт WPF-окно
Output вне UI-потока → `InvalidOperationException` в чужом потоке → процесс убит
целиком.

## Обход

1. Никогда не нажимать pyRevit → Reload, пока `[routes] enabled = true`.
   Только полный перезапуск Revit подхватывает правки в `revit_mcp/`.
2. Не поднимать `debug`/`verbose` в `[core]` конфига pyRevit для отладки Routes —
   это увеличит вероятность, что `logger.warning`/`logger.error` из тех двух
   безаргументных обработчиков дойдёт до консоли и повторит крах. Диагностику
   брать из файлового лога (`filelogging = true`,
   `%APPDATA%\pyRevit\<год>\pyRevit_<год>_<PID>_runtime.log`).
3. Перед любым HTTP-запросом к Routes проверять цепочкой: процесс Revit жив →
   порт слушается → и только потом стучаться в `/status/`.

## Урок

> «Порт слушается» и «сервер отвечает» — разные утверждения. Между reload и первым
> запросом есть окно, где TCP уже принимает соединения, а обработчик обречён убить
> процесс. Не доверяйте netstat — сначала journal/event-лог, потом осторожный запрос.

## Связанное

[[pyRevit Routes — единственная внешняя интеграция проекта]] ·
[[Модальный диалог Revit вешал headless-сервер навсегда]]
