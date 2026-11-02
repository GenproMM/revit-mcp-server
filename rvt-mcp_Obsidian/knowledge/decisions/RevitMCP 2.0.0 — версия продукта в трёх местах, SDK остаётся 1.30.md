---
tags: [decision, release, version, status]
date: 2026-11-02
---

# RevitMCP 2.0.0 — версия продукта в трёх местах, SDK остаётся 1.30

**Решение пользователя (2026-11-02):** «обновить версию mcp до 2.0» — это версия **продукта**, не библиотеки MCP SDK. SDK остаётся `mcp[cli]>=1.30,<2` (решение фазы 7 не пересматривалось).

## Где живёт версия

- `pyproject.toml` (и `uv.lock`) — `2.0.0`;
- `revit_mcp/runtime_info.PRODUCT_VERSION` — для Revit-половины;
- `tools/status_tools.PRODUCT_VERSION` — для MCP-сервера (payload не содержит `revit_mcp`, поэтому копия).

`tests/unit/test_runtime_info.py` держит три значения равными.

## Что видно в статусе

- `/status/` → блок `runtime`: `product_version`, `extension` (commit и дата из `_manifest.json`, путь загрузки), `python`, `pyrevit` (версия, `EngineVersion`, домашняя папка), `revit` (версия, подверсия, сборка). Манифест читается один раз и кешируется.
- `runtime_alerts` + `health: degraded`, если движок не Python 3 (IronPython 2.7) — с готовой командой исправления.
- `get_revit_status`: строки `MCP server: …`, `Revit extension: …`, `Revit side: …`, при расхождении — `Versions DIFFER`. Показываются при наличии `runtime` или настоящего моста (seam `secret_fingerprint`), чтобы голый транспорт сохранял прежний текст (тесты `test_status_target`).

## Не меняли

Формат `VERSION` сборки (`yyyy.MM.dd-HHmm.<sha>`) — от него зависят каталоги `versions\` и `update.cmd`. Версия продукта сообщается отдельно.

Связано: [[IronPython 2.7 молча теряет общий секрет — open rb отдаёт str]], [[2026-11-02 — pilot2 у тестировщиков, IPY2712 прятал секрет, RevitMCP 2.0.0 rc1 и подготовка ГПО]].
