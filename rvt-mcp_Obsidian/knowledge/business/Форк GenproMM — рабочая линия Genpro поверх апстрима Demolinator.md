---
tags: [business, fork, git, lineage, workflow]
date: 2026-09-04
---

# Форк GenproMM — рабочая линия Genpro поверх апстрима Demolinator

## Топология remotes

```
origin    https://github.com/GenproMM/revit-mcp-server.git      ← наш форк
upstream  https://github.com/Demolinator/revit-mcp-server.git   ← апстрим
```

Ветки на 2026-09-04:

```
* feature/local-revit-mcp-tools     ← текущая работа
  master
  remotes/origin/master
  remotes/upstream/master
  remotes/upstream/feature/revit-2027-support
  remotes/upstream/local-first-setup
```

## Родословная

```
revit-mcp-python (Juan D. Rodriguez / Jean-Marc Couffin)
  → mcp-servers-for-revit/mcp-server-for-revit-python
    → Demolinator/revit-mcp-server (Talal Ahmed)   ← upstream
      → GenproMM/revit-mcp-server                  ← origin, наш
```

Переименования на пути были вынужденными: коммит `774b465` — «Update org and repo names
to comply with Autodesk Revit trademarks». **Торговая марка Autodesk Revit**
ограничивает названия репозиториев и организаций — это важно помнить при публикации.

## Состояние текущей ветки

`feature/local-revit-mcp-tools` опережает `master` ровно на один коммит:

```
910b136 docs: map existing codebase     — 7 документов в .planning/codebase/, 1049 строк
```

То есть на момент сборки этого vault **кода мы ещё не меняли** — сделана только карта
кодовой базы. Это удобная стартовая точка: всё, что описано в vault, соответствует
состоянию апстрима.

## Что уже пришло из апстрима

Крупный слой работы, попавший через `0081712` и `40af5a7`:

- поддержка Revit 2027 (`2ff339e`)
- clash-детект плюс исправления с живого тестирования на 2027 (`67644ee`)
- `save_document` (`d9ea68c`), `load_family` (`14d4dc3`)
- подавление модальных диалогов (`0b8d5ce`, `e41f81b`)
- исправления единиц и хостинга в `place_family` (`afe5039`, `2469821`)
- расширение `link_file` до SAT/SKP/3DM (`2d9002f`)
- исправление `format_response` плюс тест cold-start (`c1231f6`, `56f6077`)

## Регрессия, приехавшая из этой же линии

> [!warning] Не всё из апстрима — улучшение
> `sanitize_string` с ASCII-кодированием пришёл в коммите `bb7cda2` («Add multi-version
> Revit support») и ломает все нелатинские имена элементов. В исходном
> `mcp-servers-for-revit` этого преобразования нет. См.
> [[sanitize_string превращает кириллицу в вопросительные знаки]].

Практический вывод: при синхронизации с апстримом стоит смотреть **диффы**, а не
только сообщения коммитов. Правка кодировок приехала в коммите, чьё название говорило
про `ElementId`.

## Практика работы с форком

- Ветки называются `feature/<тема>`.
- Сообщения коммитов — конвенциональные префиксы, где уместно: `fix(server):`,
  `perf(server):`, `docs:`.
- Тела коммитов подробные: симптом → причина → исправление. Это ценный источник для
  папки [[2026-09-04 — картирование кодовой базы и сборка vault|отладочных заметок]] —
  почти вся папка `knowledge/debugging/` восстановлена именно из них.
- Ко-авторство ИИ фиксируется трейлером `Co-Authored-By`.

## Что стоит решить

- Отдавать ли исправления обратно в `upstream` (например фикс кодировки) или держать
  локально.
- Как отслеживать расхождение с `upstream/master`.

См. [[Открытые вопросы по проекту]].

## Самый первый предок публично жив и активен

`mcp-servers-for-revit/revit-mcp-python` на GitHub (создан 2025-05-19 — та же дата,
что и первый коммит этого дерева) — это не альтернативное решение, а начало этой же
родословной, всё ещё поддерживаемое отдельно от `Demolinator`/`GenproMM`. На
2026-09-04: 176 звёзд, 104 форка, 17 открытых issues, последний push 2026-07-26,
MIT. Каталог mcpservers.org описывает его как ~18 реализованных инструментов против
48 здесь — апстрим сам называет себя «demonstration», не «fully-featured product».

Практический смысл: 17 открытых issues и PR там — бесплатный источник багфиксов для
общих модулей (`status`, `views`, `placement`, `code_execution`, `families`), которые
не проходили через ветку `Demolinator`. Реальный diff этих модулей ещё не построен.
См. [[2026-09-04 — сравнение с апстримом revit-mcp-python и подтверждение родословной форка]].

## Связанное

[[Цены нет — проект под лицензией MIT]] ·
[[Валидация продукта — сборка Empire State Building в живом Revit 2027]] ·
[[sanitize_string превращает кириллицу в вопросительные знаки]] ·
[[Открытые вопросы по проекту]] ·
[[2026-09-04 — сравнение с апстримом revit-mcp-python и подтверждение родословной форка]]
