---
tags: [atlas, tools, catalog, api]
date: 2026-09-04
---

# 48 MCP-инструментов зеркалят 48 маршрутов pyRevit

> [!info] Обновление 2026-09-04, вторая сессия
> Заголовок и число ниже устарели, но не переименовано — на заметку ссылаются
> 13 других файлов. Актуально: **49 инструментов над 48 маршрутами** — новый
> `list_project_parameters` (`GET /project_parameters/`) не добавляет отдельный
> маршрут, потому что домен `parameters` уже был зарегистрирован в обоих barrel-
> файлах; это первый случай в проекте, когда счётчики инструментов и маршрутов
> разошлись. См.
> [[2026-09-04 — фикс кириллицы и правильный детект общих параметров, новый инструмент list_project_parameters]].

Было 48 функций под `@mcp.tool()` в `tools/` и 48 обработчиков `@api.route()`
в `revit_mcp/` — теперь 49 и 48 соответственно. Соответствие один к одному не
автоматическое — оно поддерживается вручную двумя списками регистрации
([[Регистрация ведётся двумя рукописными списками]]).

Все инструменты принимают миллиметры
([[Все инструменты принимают миллиметры, Revit внутри считает в футах]]).

## Создание (15)

| Инструмент | Маршрут | Что делает |
|---|---|---|
| `create_level` | `POST /create_level/` | Уровни с отметками |
| `create_line_based_element` | `POST /create_line/` | Стены, балки и прочее линейное |
| `create_surface_based_element` | `POST /create_surface/` | Перекрытия, кровли, поверхности |
| `place_family` | `POST /place_family/` | Экземпляр семейства в точке |
| `create_grid` | `POST /create_grid/` | Оси колонн |
| `create_structural_framing` | `POST /create_framing/` | Балки и каркас |
| `create_sheet` | `POST /create_sheet/` | Листы |
| `create_schedule` | `POST /create_schedule/` | Спецификации с полями |
| `create_room` | `POST /create_room/` | Помещения на уровне |
| `create_room_separation` | `POST /create_room_separation/` | Линии разделения помещений |
| `create_duct` | `POST /create_duct/` | Воздуховоды между точками |
| `create_pipe` | `POST /create_pipe/` | Трубы между точками |
| `create_mep_system` | `POST /create_mep_system/` | Механические и трубопроводные системы |
| `create_detail_line` | `POST /create_detail_line/` | Линии детализации (привязаны к виду) |
| `create_view` | `POST /create_view/` | Планы, разрезы, фасады, 3D |

## Чтение (13)

| Инструмент | Маршрут | Что делает |
|---|---|---|
| `get_revit_status` | `GET /status/` | Живо ли API |
| `get_revit_model_info` | `GET /model_info/` | Сводка по модели |
| `list_levels` | `GET /list_levels/` | Уровни с отметками |
| `list_families` | `GET /list_families/` | Доступные типы семейств |
| `list_family_categories` | `GET /list_family_categories/` | Категории семейств |
| `get_revit_view` | `GET /get_view/<view_name>` | Экспорт вида картинкой |
| `list_revit_views` | `GET /list_views/` | Экспортируемые виды |
| `get_current_view_info` | `GET /current_view_info/` | Детали активного вида |
| `get_current_view_elements` | `GET /current_view_elements/` | Элементы активного вида |
| `get_selected_elements` | `GET /selected_elements/` | Текущее выделение |
| `list_category_parameters` | `POST /list_category_parameters/` | Параметры категории |
| `get_element_properties` | `GET /element_properties/<element_id>` | Все параметры элемента |
| `list_project_parameters` | `GET /project_parameters/` | Параметры проекта, общие vs обычные |

## Изменение (9)

| Инструмент | Маршрут | Что делает |
|---|---|---|
| `delete_elements` | `POST /delete_elements/` | Удаление элементов |
| `modify_element` | `POST /modify_element/` | Изменение значений параметров |
| `color_splash` | `POST /color_splash/` | Раскраска по значению параметра |
| `clear_colors` | `POST /clear_colors/` | Сброс переопределений цвета |
| `tag_walls` | `POST /tag_walls/` | Марки на все стены текущего вида |
| `set_parameter` | `POST /set_parameter/` | Одно значение на одном элементе |
| `tag_elements` | `POST /tag_elements/` | Марки на конкретные элементы |
| `transform_elements` | `POST /transform_elements/` | Перенос, копия, поворот, зеркало |
| `set_active_view` | `POST /set_active_view/` | Переключение активного вида |

## Анализ (5)

| Инструмент | Маршрут | Что делает |
|---|---|---|
| `ai_element_filter` | `POST /ai_filter/` | Фильтр по категориям и параметрам |
| `export_room_data` | `GET /room_data/` | Площади, объёмы, границы помещений |
| `get_material_quantities` | `POST /material_quantities/` | Ведомость материалов |
| `check_clashes` | `POST /clash_check/` | Жёсткие коллизии между дисциплинами |
| `analyze_model_statistics` | `GET /model_statistics/` | Подсчёты и статистика модели |

## Документация (3)

`create_dimensions` → `POST /create_dimensions/` · `export_document` →
`POST /export_document/` · плюс листы и спецификации из блока «Создание»
(`create_sheet`, `create_schedule` живут в `revit_mcp/documentation.py`).

## Обмен и персистентность (4)

| Инструмент | Маршрут | Что делает |
|---|---|---|
| `export_ifc` | `POST /export_ifc/` | Экспорт в IFC2x3 / IFC4 |
| `link_file` | `POST /link_file/` | Связь или импорт DWG, DXF, DGN, SAT, SKP, 3DM, RVT |
| `load_family` | `POST /load_family/` | Загрузка `.rfa` с диска |
| `save_document` | `POST /save_document/` | Save / SaveAs модели |

## Продвинутое (1)

| Инструмент | Маршрут | Что делает |
|---|---|---|
| `execute_revit_code` | `POST /execute_code/` | Произвольный IronPython в контексте Revit |

> [!danger] Это самый опасный маршрут проекта
> См. [[execute_code даёт неаутентифицированное исполнение кода внутри Revit]].

## Распределение по модулям

Самые густые модули инструментов: `analysis_tools.py` и `family_tools.py` и
`view_tools.py` — по 4 инструмента; `building_tools.py`, `colors_tools.py`,
`documentation_tools.py`, `editing_tools.py`, `mep_tools.py` — по 3. Остальные — по
одному-двум.

Форма трафика: 13 точек вызова GET, 35 POST и 1 запрос картинки.

## Связанное

[[Архитектура — это мост между двумя рантаймами Python]] ·
[[Карта модулей и их размеры]] ·
[[Добавление возможности требует правок в четырёх местах]] ·
[[Докстринг инструмента — это контракт для модели, а не для разработчика]]
