---
tags: [debugging, ironpython, secret, pyrevit, pilot]
date: 2026-11-02
---

# IronPython 2.7 молча теряет общий секрет — open rb отдаёт str

**Статус:** причина найдена и подтверждена; на ПК исправлено переключением движка на IPY342; в коде — алерт в `/status/`.

## Симптом

Тестировщик pilot2 (e.nazarova): `/status/` → `health: degraded`, `secret.configured=False`, все изменения модели — `401 server_not_configured`. При этом путь расширения один и с пилотной раздачи, `integrity=verified_match`, `failed_domains` пусто, файл `_bridge_secret` на share читается PowerShell и совпадает с payload, Revit перезапущен после появления файла.

## Причина

pyRevit на этой машине был прикреплён к движку **IronPython 2.7 (IPY2712)**, а не IPY342. Измерено на собственных движках pyRevit (хостинг DLL из PowerShell):

| Движок | `bytes is str` | `type(open(p, "rb").read())` |
|---|---|---|
| IPY2712 | False | `str` |
| IPY342 | False | `bytes` |

`textutils` выбирает ветку Python 3 по `bytes is str` (у IronPython 2.7 есть отдельный тип `bytes`), поэтому `_BYTES_TYPE = bytes`. `trust.secret_from_bytes` проверяет `isinstance(raw, bytes)` → False → секрет `None`, без исключения и без лога. Проверка целостности типы не проверяет, поэтому проходит — отсюда обманчивая картина «всё цело, но секрета нет».

## Исправление

- На ПК: при закрытом Revit `pyrevit attach master 342 --attached` (раздел 2б START-HERE, `gpo-prep.ps1`).
- В коде 2.0.0: `/status/` показывает движок в `runtime.python` и `runtime.pyrevit.engine`, при Python 2 — `runtime_alerts` с командой исправления и `degraded`.
- Не сделано: сама проверка в `textutils` (`sys.version_info[0] == 2` вместо `bytes is str`) — требует новой сборки, движок 2.7 официально не поддерживается.

## Как диагностировать

`deploy/diag-secret.ps1` или `(& pyrevit env) -match 'Engine:'` — строка `Engine: IPY2712…`.

Связано: [[RevitMCP 2.0.0 — версия продукта в трёх местах, SDK остаётся 1.30]], [[Целевой рантайм Revit-половины — IronPython 3, не 2.7]].
