---
tags: [session, comparison, upstream, fork]
date: 2026-09-04
---

# Сессия: сравнение с апстримом revit-mcp-python и подтверждение родословной форка

## Задача

Пользователь попросил сравнить этот репозиторий с решением, на которое ссылается
`https://mcpservers.org/ru/servers/revit-mcp/revit-mcp-python`.

## Метод

1. Локальный агент (Explore) перепроверил актуальную картину этого репозитория:
   число инструментов, транспорты, лицензию, известные слабые места — сверено с
   `.planning/codebase/CONCERNS.md` и `git log`.
2. `WebFetch` по странице mcpservers.org → она указывает на
   `github.com/revit-mcp/revit-mcp-python` (владелец организации на GitHub:
   `mcp-servers-for-revit`).
3. `WebFetch` по самому GitHub-репозиторию и `api.github.com` за метриками
   (звёзды, форки, issues, даты).
4. `git remote -v` и `git log --reverse` в этом репозитории для дат/родословной.

## Находка: это не конкурент, а предок этого же кода

`mcp-servers-for-revit/revit-mcp-python` создан **19.05.2025** — та же дата, что и
первый коммит в этом дереве (`42e6ac5 "First Commit"`, автор `jotaderodriguez`,
LICENSE с копирайтом Juan Rodriguez). Это подтверждает и расширяет то, что уже было
задокументировано в
[[Форк GenproMM — рабочая линия Genpro поверх апстрима Demolinator]]:
цепочка `revit-mcp-python → mcp-servers-for-revit/mcp-server-for-revit-python →
Demolinator/revit-mcp-server (upstream) → GenproMM/revit-mcp-server (origin, наш)`.

То есть страница на mcpservers.org описывает **самое начало** этой родословной, а не
альтернативное решение.

## Внешние метрики апстрима (сняты 2026-09-04, через `api.github.com`)

- Owner: `mcp-servers-for-revit`, создан 2025-05-19, последний push 2026-07-26.
- 176 звёзд, 104 форка, 17 открытых issues, MIT license, default branch `master`.
- Каталог mcpservers.org на момент проверки перечислял только **18 реализованных
  инструментов** (+9 «pending»: `get_selected_elements`, `create_line_based_element`,
  `create_surface_based_element`, `delete_elements`, `modify_element`, `reset_model`,
  `tag_walls`, `search_modules`, `use_module`) — против 48 в этом репозитории.
  Сам апстрим описывает себя как «work in progress, more of a demonstration than a
  fully-featured product».

## Вывод, отданный пользователю

Функционально этот репозиторий далеко впереди (MEP, clash detection, интероп-импорт
множества форматов, персистентность, поддержка Revit 2024–2027, нормализация мм) —
догонять апстрим по фичам незачем. Но у апстрима есть то, чего нет здесь напрямую:
живой поток из 17 issues / ~12 PR как источник багфиксов для общих модулей
(`status`, `views`, `placement`, `code_execution`), и канал дистрибуции через каталог
расширений pyRevit.

Общие слабые места у обеих линий: `execute_code` без аутентификации, pyRevit Routes
API официально в draft-статусе, отсутствие CI и headless-тестов, один
документ/инстанс Revit одновременно.

## Не сделано

Не построен реальный diff общих модулей (`status`, `views`, `placement`,
`code_execution`, `families`) между этим деревом и `mcp-servers-for-revit/master` —
предложено пользователю как следующий шаг, если понадобится подтянуть конкретные
чужие багфиксы.

## Связанное

[[Форк GenproMM — рабочая линия Genpro поверх апстрима Demolinator]] ·
[[Продукт — это мост между ИИ-ассистентом и Autodesk Revit]] ·
[[Цены нет — проект под лицензией MIT]] ·
[[Открытые вопросы по проекту]]
