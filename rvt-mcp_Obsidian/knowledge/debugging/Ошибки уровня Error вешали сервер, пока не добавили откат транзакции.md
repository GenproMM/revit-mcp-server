---
tags: [debugging, transaction, liveness, fixed]
date: 2026-09-04
---

# Ошибки уровня Error вешали сервер, пока не добавили откат транзакции

**Статус:** исправлено · коммит `e41f81b`

## Симптом

То же, что и раньше: сервер Routes зависает навсегда. Но уже **после** установки
`suppress_warnings` — то есть защита, которая должна была это исключить, не сработала.

## Причина

Первая версия препроцессора обрабатывала только предупреждения: `DeleteAllWarnings()`
и всё. Сбои **уровня Error** он не трогал, а они тоже поднимают модальный диалог.

Конкретный пример из практики: «Can't cut instance out of Wall» — когда окно не может
подрезать свою хост-стену. Это не предупреждение, это ошибка, и удаление
предупреждений её не убирает.

## Исправление

Препроцессор теперь удаляет предупреждения **и** откатывает транзакцию при любой
ошибке:

```python
def PreprocessFailures(self, failuresAccessor):
    try:
        failuresAccessor.DeleteAllWarnings()
        for f in failuresAccessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Error:
                return DB.FailureProcessingResult.ProceedWithRollBack
    except Exception:
        pass
    return DB.FailureProcessingResult.Continue
```

Плюс `opts.SetClearAfterRollback(True)`, чтобы состояние после отката было чистым.

Итог: ни один сбой Revit — ни warning, ни error — не может заблокировать headless-сервер.

## Урок

> Классификация сбоев в Revit не бинарная. `DeleteAllWarnings()` покрывает ровно
> предупреждения; для ошибок нужен явный `ProceedWithRollBack`. Проверять надо оба
> уровня severity.

Более общий урок: исправление проблемы живости стоит проверять на **обоих** классах
входов, а не только на том, который её обнаружил. Первая версия выглядела рабочей
именно потому, что тестировалась на предупреждении.

## Связанное

[[Модальный диалог Revit вешал headless-сервер навсегда]] ·
[[Каждая транзакция глушит модальные диалоги Revit]] ·
[[Окна и двери без хоста прилипали к началу координат]]
