# Null document при переключении моделей

## Симптом

При открытии нескольких моделей подряд MCP-мост завершал запрос с ошибкой Revit API:
`The input argument "document" of function "Transaction_constructor" ... is null`.

## Причина

`revit_mcp/code_execution.py` создавал `DB.Transaction(doc, ...)` без проверки внедрённого `doc`. Во время `OpenAndActivateDocument` pyRevit может кратковременно передать `None` или устаревший документ.

## Решение

Перед созданием транзакции повторно получить `revit.doc`, если входной `doc` пустой. Если активного документа нет, вернуть ответ `503` и не вызывать конструктор транзакции.

## Проверка

Добавлен регрессионный тест на порядок проверки. Набор `uv run pytest tests/unit -q`: 301 passed, 3 skipped.
