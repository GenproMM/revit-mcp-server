---
tags: [debugging, pyrevit, install, routes, pilot]
date: 2026-10-30
---

# pyrevit forget не снимает UNC-путь без точного совпадения, без host Routes слушает 0.0.0.0

**Статус:** учтено в START-HERE.txt (блок снятия пути, раздел 2а). Измерено на pyRevit 6.5.5 со scratch-конфигом.

## forget

- `pyrevit extensions paths forget <p>`: локальные пути нормализуются, UNC — нет («Path is not local. Skipping normalization»). Снимается только **точное, с учётом регистра** совпадение строки; расхождение (регистр, хвостовой `\`, `install\..\ext` против `ext`) — тихий no-op с кодом 0.
- Старые установки хранили путь буквально: `\\srv-dfs\BIM\06_RevitMCP\install\..\ext` (install.cmd берёт `%~dp0..\ext`).
- Каждый `forget` переписывает `userextensions` и молча выкидывает все пути, недоступные в этот момент.
- Поэтому путь берётся из JSON `userextensions` и передаётся аргументом, никогда не набирается руками.
- Windows PowerShell 5.1: `@(json | ConvertFrom-Json)` даёт ОДИН элемент (весь массив) — писать `foreach ($x in (… | ConvertFrom-Json))`.

## host

- `[routes]` без `host`: `PyRevitConsts.ConfigsRoutesHostDefault = ""` → сервер слушает 0.0.0.0, `/execute_code/` доступен из сети.
- В CLI pyRevit команды для host нет. `deploy/check_routes_config.py` останавливает установку 2.0 («No option 'host' in section: 'routes'»).
- Решение пользователя (2026-10-30): добавлять `host = "127.0.0.1"` только если строки нет; существующий host не менять (раздел 2а START-HERE, `gpo-prep.ps1`).

Связано: [[Раскатка 2.0 — файлы везёт автообновление, ГПО только готовит машины]].
