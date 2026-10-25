---
tags: [debugging, payload, mcp-sdk, pywin32, deploy, phase-7]
date: 2026-10-25
---

# mcp 1.11+ импортирует pywin32, а embeddable CPython payload его не находит

**Статус:** найдено исследованием фазы 7 · обход проверен в scratch-раскладке payload · в код ещё не внесено (план 07-03)

## Симптом

После обновления `mcp` с 1.9.0 до любой версии от 1.11.0 сервер, собранный рецептом `deploy/build-payload.cmd`, не стартует: `import mcp` падает с `ModuleNotFoundError: No module named 'pywintypes'`. На dev-машине (`uv run main.py` из `.venv`) всё работает, поэтому unit-suite остаётся зелёным.

## Причина

- Начиная с 1.11.0 `mcp` на Windows безусловно импортирует `pywin32`.
- `pywin32` раскладывает свои модули по `win32`, `win32\lib`, `pythonwin` и подключает их через `.pth`-файл.
- Embeddable CPython, на котором живёт payload парка, `.pth` игнорирует — эти каталоги не попадают в `sys.path`.

## Обход

- В `deploy/server.py`, `deploy/gate.py`, `deploy/warm.py` рядом с существующей вставкой `libs` добавить в `sys.path` `libs\win32`, `libs\win32\lib`, `libs\pythonwin` (плюс каталог DLL).
- С этим shim `deploy/gate.py` в scratch-раскладке напечатал `GATE_OK`.
- Допущение A8: этого хватает на всех станциях, не только на этой машине. Проверяется `warm.py` при обновлении.

## Урок

Зелёный unit-suite не доказывает, что payload импортируется: обновление зависимостей проверять сборкой payload и `deploy/gate.py` на встроенном CPython pyRevit (в фазе 7 это `scripts/scratch_payload_gate.py`, план 07-03).

Связано: [[Фаза 7 — SDK 1.30 вместо 2.x, load_family с предупреждением, без памяти повторов, файл оператора рядом с секретом]], [[Гейт холодного старта мерил SMB-задержку шары, а не старт сервера]], [[2026-10-25 — планирование фазы 7, четырнадцать планов в девять волн, SDK 1.30, требования SAFE-01..21]].
