сессия: последовательное открытие и сохранение трёх моделей Revit 2024 и исправление ошибки null document.

## Информация о сессии
- Модель: gpt-5.6-sol
- Провайдер: genpro
- Дата: 2026-09-14
- Изменено файлов: 6

## Результат

- Revit 2024 был запущен через MCP.
- Три модели открыты поочерёдно с `detach: preserve`.
- Сохранены в `C:\Users\Admin\Documents` как `MCP_TEST_0.rvt`, `MCP_TEST_1.rvt`, `MCP_TEST_2.rvt`.
- Наличие и размеры выходных файлов проверены.
- В `revit_mcp/code_execution.py` добавлена защита от `DB.Transaction(None, ...)`.
- В `tests/unit/test_conventions.py` добавлен регрессионный тест.

## Проверка кода

`uv run pytest tests/unit -q` → `301 passed, 3 skipped`.
`git diff --check` → без ошибок.
