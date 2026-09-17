---
tags: [сессия, revit-server, rsn, mcp, debugging]
date: 2026-09-17
---

# Сессия: журнал Revit Server закреплён на обязательном UNC-пути

## Информация о сессии

- Модель: GPT-5.6
- Дата: 2026-09-17
- Изменено файлов: 3

## Изменённые файлы

- `tools/worksharing_tools.py` — путь к журналу записан как точный Windows UNC raw string.
- `tests/unit/test_revit_server_paths.py` — добавлен регрессионный тест на обязательное значение пути.
- `rvt-mcp_Obsidian/sessions/2026-09-17 — журнал Revit Server закреплён на обязательном UNC-пути.md` — эта заметка.

## Результаты

- Установлено обязательное расположение журнала:
  `\\srv-dfs\BIM\01_Ресурсы плагинов\10_Облегченные модели\RevitModelLiteProcessorJournal.json`.
- Использование `G:` и альтернативных fallback-путей исключено.
- Файл проверен из CPython-процесса MCP: каталог и файл доступны, JSON разбирается.
- Из журнала прочитано 6 013 моделей.
- Сокращённый путь `RSN://<имя модели>.rvt` успешно преобразован в полный канонический RSN URI.
- Полный RSN URI по-прежнему не зависит от журнала и проходит напрямую.

## Проверка

- `uv run --isolated pytest tests/unit/test_revit_server_paths.py` — 14 passed.
- `uv run --isolated pytest tests/unit` — 337 passed, 3 skipped.
- `git diff --check` — пройден.

## Важно

В рабочем дереве одновременно находились несвязанные изменения транспорта MCP (`main.py`, `test_local_bridge_transport.py` и их заметки). Они намеренно не включены в этот коммит.
