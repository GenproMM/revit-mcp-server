---
tags: [debugging, live-gate, revit, two-instance, rollback, phase-6]
date: 2026-10-25
---

# Живой шлюз с двумя Revit — запуск второго экземпляра и триггер отката

**Симптомы и причины.**

| Что случилось | Причина | Что делать |
|---------------|---------|------------|
| `start_revit` не запускает второй Revit | инструмент возвращается сразу, если какой-либо Revit уже отвечает | запускать вторым `Start-Process "C:\Program Files\Autodesk\Revit 2024\Revit.exe"` без модели, ждать `/status/` на порту 48885 (503 без документа — норма); listener-ы: 48884 и 48885 разные PID |
| `open_model` на только что запущенном втором Revit: `ReadTimeout`, и `list_documents` тоже | запросы висят, пока pyRevit инициализируется (известная острая грань); модель не открывается | опрашивать `/status/`, пока Revit не покажет Главную; повторить `open_model` только когда окно на «Главная» без документа (повтор не создаст дубль) |
| `main.mcp.call_tool("execute_revit_code")` вне запроса MCP бросает до отправки | инжектированный `Context` отказывает в `ctx.info` вне запроса | вызывать зарегистрированную функцию (`main.mcp._tool_manager.get_tool(name).fn`) с `ctx=None`; это та же обёртка аудита |
| `CloseMainWindow` не закрывает Revit | модель с несохранёнными правками → запрос сохранения | не убивать процесс, вернуться к пользователю |

**Триггер отката, который работает вживую (A3 подтверждено).** В `execute_revit_code`:

```python
fid = DB.BuiltInFailures.GeneralFailures.ValueOutOfRange
doc.PostFailure(DB.FailureMessage(fid))
```

`ValueOutOfRange` имеет серьёзность Error (проверено через `doc.Application.GetFailureDefinitionRegistry().FindFailureDefinition(fid).GetSeverity()`); ответ — `rolled_back`, HTTP 409, `RolledBack`, модель не меняется. `UnspecifiedError` — не годится (`DocumentCorruption`).

**Параметр стены в русском Revit.** Текстовый параметр называется «Комментарии», проверяется `LookupParameter(...)` и `IsReadOnly`; скрипт сам отказывается до отправки, если параметр не пишется.

Связано: [[2026-10-25 — исполнение фазы 6, семь планов, живой шлюз PHASE6_AUDIT_OK, верификация human_needed]], [[Фаза 6 — живой шлюз выполнен контроллером по просьбе, фаза остаётся на human_needed]].
