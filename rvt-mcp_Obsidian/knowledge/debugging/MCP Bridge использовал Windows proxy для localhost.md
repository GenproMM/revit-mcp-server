# MCP Bridge использовал Windows proxy для localhost

## Симптом

Инструменты MCP Revit в одной из сессий возвращали пустое сообщение `Error: `.

## Причина

CPython-часть Revit MCP использовала общий `httpx.AsyncClient`, который по умолчанию учитывал настройки прокси из окружения Windows. Для локального адреса pyRevit Routes (`127.0.0.1:48884`) это приводило к разрыву соединения и `ReadError('')`. Слой транспорта скрывал пустой текст исключения, поэтому агент видел только `Error: `.

## Проверка гипотезы

- `http.client` напрямую к `127.0.0.1:48884` получил HTTP 200.
- `httpx.AsyncClient` с настройками окружения получил `ReadError('')`.
- `httpx.AsyncClient(trust_env=False)` получил HTTP 200.
- `hermes mcp test revit` успешно подключился и обнаружил 54 инструмента.

## Исправление

В `main.py` для локального `httpx.AsyncClient` добавлен параметр:

```python
trust_env=False
```

Добавлен регрессионный тест `tests/unit/test_local_bridge_transport.py`.

## Проверка после исправления

- полный unit-набор: 338 passed, 3 skipped;
- `hermes mcp test revit`: Connected, 54 tools;
- прямой MCP-вызов `get_selected_elements`: успешен.

После остановки уже запущенного stdio-процесса требуется перезапуск Gena Desktop, чтобы был создан новый процесс с исправленным кодом.

**Дата:** 2026-09-17
**Связано с:** [[2026-09-17 — MCP Bridge падал из-за прокси Windows, добавлен trust_env_false]]
---
