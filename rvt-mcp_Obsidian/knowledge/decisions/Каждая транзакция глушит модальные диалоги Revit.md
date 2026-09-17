---
tags: [decision, transaction, robustness, revit-api, critical]
date: 2026-09-04
---

# Каждая транзакция глушит модальные диалоги Revit

## Решение

Сразу после `transaction.Start()` — и до любого изменения модели — вызывается
`suppress_warnings(t)` из `revit_mcp/utils.py`. Без исключений, во всех маршрутах,
работающих через транзакцию.

```python
t = DB.Transaction(doc, "MCP: ...")
t.Start()
suppress_warnings(t)   # ← обязательно здесь, не позже
# ... правки модели ...
t.Commit()
```

## Обоснование

Рутинное предупреждение Revit во время транзакции (например «окно не подрезает
хост-стену») открывает **модальный диалог**, который блокирует headless-сервер Routes
навсегда. Все последующие запросы отваливаются по таймауту, пока живой человек не
нажмёт OK. Для автоматизации это фатально.

История: [[Модальный диалог Revit вешал headless-сервер навсегда]], затем
[[Ошибки уровня Error вешали сервер, пока не добавили откат транзакции]].

## Как это работает

`_FailureSwallower` реализует `DB.IFailuresPreprocessor`:

```python
def PreprocessFailures(self, failuresAccessor):
    try:
        failuresAccessor.DeleteAllWarnings()          # предупреждения удаляем, операция идёт
        for f in failuresAccessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Error:
                return DB.FailureProcessingResult.ProceedWithRollBack   # ошибки — откат
    except Exception:
        pass
    return DB.FailureProcessingResult.Continue
```

`suppress_warnings` навешивает его на транзакцию плюс выключает форсированную
модальность:

```python
opts = transaction.GetFailureHandlingOptions()
opts.SetForcedModalHandling(False)
opts.SetClearAfterRollback(True)
opts.SetFailuresPreprocessor(_FailureSwallower())
transaction.SetFailureHandlingOptions(opts)
```

Итог: предупреждения удаляются автоматически (операция продолжается), ошибки чисто
откатывают транзакцию. Ни один сбой Revit не может заблокировать сервер.

## Известная слабость

`suppress_warnings` — best-effort и **никогда не выбрасывает**. Если конфигурирование
провалится, функция молча вернётся, и транзакция пойдёт **без** защиты — ровно тот
сценарий, от которого она защищает. См.
[[suppress_warnings глушит собственный сбой и оставляет транзакцию без защиты]].

## Исключения из правила

`Save` / `SaveAs` и `LoadFamily` **не** запускаются в транзакции вообще — см.
[[Save и SaveAs выполняются вне транзакции]].

## Связанное

[[Паттерн обработчика маршрута — валидация, транзакция, сериализация]] ·
[[Модальный диалог Revit вешал headless-сервер навсегда]] ·
[[Revit API доступен только внутри процесса Revit]]
