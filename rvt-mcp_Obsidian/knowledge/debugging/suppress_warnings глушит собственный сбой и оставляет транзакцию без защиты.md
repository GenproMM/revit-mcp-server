---
tags: [debugging, open-bug, transaction, liveness]
date: 2026-09-04
---

# suppress_warnings глушит собственный сбой и оставляет транзакцию без защиты

**Статус:** ОТКРЫТАЯ БАГА · `revit_mcp/utils.py` · риск живости

## Симптом

Если конфигурирование обработки сбоев выбросит исключение, `suppress_warnings` **молча
вернётся**, и транзакция пойдёт **без** подавления модальных диалогов — ровно тот
сценарий, от которого функция существует.

Наружу это выглядит как зависший сервер Routes без единой записи в логе.

## Причина

```python
def suppress_warnings(transaction):
    try:
        opts = transaction.GetFailureHandlingOptions()
        opts.SetForcedModalHandling(False)
        opts.SetClearAfterRollback(True)
        opts.SetFailuresPreprocessor(_FailureSwallower())
        transaction.SetFailureHandlingOptions(opts)
    except Exception:
        pass          # ← сбой самой защиты становится невидимым
```

Функция задокументирована как best-effort и «never raises» — и это разумно: падение
здесь сорвало бы операцию, которая, возможно, прошла бы нормально. Но `pass` без лога
делает проблему **недиагностируемой**.

То же относится к `_FailureSwallower.PreprocessFailures` — там внутри тоже
`except Exception: pass`.

## Триггер

Версия Revit API, где отличается сигнатура `SetFailuresPreprocessor` или
`GetFailureHandlingOptions`. Это вполне реальный риск при поддержке матрицы
2024 / 2025 / 2026 / 2027 — API идентификаторов уже менялся дважды
([[Bare DB.ElementId(int) в Revit 2027 падает на неоднозначности перегрузок]]).

## Обходной путь

Нет.

## Исправление

Как минимум `logger.warning` в обработчике, чтобы зависший сервер стал диагностируемым:

```python
except Exception as e:
    logger.warning("suppress_warnings failed, transaction unprotected: {}".format(str(e)))
```

Оставить функцию не выбрасывающей — правильно. Оставить её **немой** — нет.

Дополнительно стоит подумать о признаке в ответе: если защита не установилась, клиент
имеет право знать, что операция шла в незащищённом режиме.

## Урок

> Best-effort-функция может глотать исключение, но не имеет права глотать **факт своего
> сбоя**. Особенно если она существует ради свойства живости: молчаливый отказ защиты
> хуже, чем отсутствие защиты, потому что о нём никто не узнает.

## Связанное

[[Каждая транзакция глушит модальные диалоги Revit]] ·
[[Модальный диалог Revit вешал headless-сервер навсегда]] ·
[[Широкий except Exception используется как поток управления]] ·
[[ElementId читается и создаётся только через хелперы]]
