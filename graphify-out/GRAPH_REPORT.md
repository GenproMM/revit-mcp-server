# Graph Report - revit-mcp-server  (2026-09-07)

## Corpus Check
- 93 files · ~124,802 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 840 nodes · 1222 edges · 77 communities (52 shown, 25 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 24 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9fd8c7d6`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- tools/utils.py
- main.py
- parameters.py
- test_textutils.py
- colors.py
- test_conventions.py
- revit_mcp/utils.py
- extension.json
- get_element_id_value
- Supported Tools (49) catalogue
- startup.py
- Revit L2 Floor Plan View Pane (Snowdon Towers sample model)
- clash.py
- make_element_id
- Как сделать свой инструмент для RevitMCP
- list_model_elements Tool Screenshot
- format_response
- test_registration.py
- Инструкция: как сделать свой инструмент для RevitMCP
- Первичная настройка и пилотная раскатка
- get_element_name
- contrib-kit/conventions.py
- suppress_warnings
- scripts/conventions.py
- configure_hermes.py
- Architecture
- find_family_symbol_safely
- intake_package.py
- revitmcp_kit.py
- Contributing
- Codebase Concerns
- Coding Conventions
- process_tools.py
- All tool-facing dimensions are millimeters
- Route handlers never raise invariant
- except Exception: pass proliferation (60+ occurrences)
- Bulk routes report success despite per-element skips
- Port 48884 hardcoded sharp edge
- _revit_call single 30s timeout sharp edge
- mcp-server-for-revit
- AGENTS.md — правила для ИИ-ассистента в этом репозитории
- Агент: сборка пакета инструмента Revit MCP
- Набор разработчика инструментов Revit MCP
- Разработка инструментов Revit MCP
- Агент: разработка инструмента Revit MCP
- External Integrations
- Testing Patterns
- AGENTS.md — правила для ИИ-ассистента в этом наборе
- Technology Stack
- Codebase Structure
- Скилл Hermes для разработки инструментов
- new_tool.py
- Commit c1231f6: format_response mislabeling fix
- clash_tools.py
- _expected_tools
- analysis_tools.py
- annotation_tools.py
- building_tools.py
- code_execution_tools.py
- colors_tools.py
- detail_tools.py
- documentation_tools.py
- editing_tools.py
- family_tools.py
- interop_tools.py
- model_tools.py
- room_tools.py
- status_tools.py
- tag_tools.py
- transform_tools.py
- view_management_tools.py
- view_tools.py

## God Nodes (most connected - your core abstractions)
1. `format_response()` - 70 edges
2. `get_element_id_value()` - 42 edges
3. `get_element_name()` - 39 edges
4. `suppress_warnings()` - 36 edges
5. `make_element_id()` - 17 edges
6. `sanitize_string()` - 16 edges
7. `color_elements_by_parameter()` - 14 edges
8. `normalize_string()` - 13 edges
9. `JsonBytesTolerant` - 13 edges
10. `Architecture` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Available Tools (31) - historical tool count` --semantically_similar_to--> `Supported Tools (49) catalogue`  [INFERRED] [semantically similar]
  LLM.txt → README.md
- `httpx==0.28.1 package` --conceptually_related_to--> `revit_get()`  [INFERRED]
  requirements.txt → main.py
- `ElementId cross-version helper invariant` --references--> `get_element_id_value()`  [EXTRACTED]
  CLAUDE.md → revit_mcp/utils.py
- `Dict-is-error-only-if-truthy-error-key rule` --rationale_for--> `format_response()`  [EXTRACTED]
  CLAUDE.md → tools/utils.py
- `Revit L2 Floor Plan View Pane (Snowdon Towers sample model)` --references--> `get_view (pyRevit route, revit_mcp/views.py)`  [INFERRED]
  images/get_view_tool.png → revit_mcp/views.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Two-Runtime architecture (CPython MCP server + IronPython Revit extension)** — main, tools_utils, tests_test_init_latency, startup, revit_mcp_utils, claude_two_runtime_rule [INFERRED 0.85]
- **Domain mirroring pattern instantiated by clash detection** — revit_mcp_clash, tools_clash_tools, startup, tools_init, claude_domain_mirroring_pattern [INFERRED 0.85]
- **Three docs describing the same 2/3/4-step tool registration workflow** — claude_adding_capability_workflow, readme_creating_your_own_tools, llm_writing_new_functions_workflow [INFERRED 0.90]
- **get_view end-to-end flow: Claude request → MCP tool → pyRevit route → rendered floor plan** — images_get_view_tool_claude_desktop_panel, images_get_view_tool_get_view_tool_call_card, tools_view_tools_get_revit_view, revit_mcp_views_get_view, images_get_view_tool_revit_l2_view_pane [INFERRED 0.85]
- **MCP Tool Invocation and Response Flow (Claude to Revit)** — images_list_model_tool_list_model_elements_tool, images_list_model_tool_snowdon_towers_model, images_list_model_tool_claude_chat_ui, images_list_model_tool_model_analysis_summary [INFERRED 0.85]

## Communities (77 total, 25 thin omitted)

### Community 0 - "tools/utils.py"
Cohesion: 0.14
Nodes (9): revit_mcp/utils.py vs tools/utils.py naming collision, Register document persistence tools with the MCP server., register_document_tools(), Register MEP tools with the MCP server., register_mep_tools(), Register parameter tools with the MCP server., register_parameter_tools(), Register structure tools with the MCP server. (+1 more)

### Community 1 - "main.py"
Cohesion: 0.05
Nodes (44): Any, AsyncClient, MCP client -> main.py+tools -> startup.py+revit_mcp -> Revit API architecture, graphify knowledge graph integration workflow, CLAUDE.md Contributor Guide, MCP Server Runtime (CPython >=3.11), Never print() under stdio transport, Obsidian Knowledge Vault session workflow (+36 more)

### Community 2 - "parameters.py"
Cohesion: 0.11
Nodes (18): _as_bool(), _get_binding_categories(), _get_binding_kind(), _get_definition_data_type(), _get_definition_group_name(), _get_param_group_name(), _get_param_value_display(), _name_prefix() (+10 more)

### Community 3 - "test_textutils.py"
Cohesion: 0.08
Nodes (36): object, JsonBytesTolerant, normalize_string(), Return Revit text as a JSON-safe text string. Revit API strings arrive as .NET…, sanitize_string() with the empty-input contract parameter values need. A…, Whitespace-trimmed variant of sanitize_string()., Stand-in for the json module whose loads() also accepts UTF-8 bytes. pyRevit's…, sanitize_string() (+28 more)

### Community 4 - "colors.py"
Cohesion: 0.05
Nodes (46): Shared parameter ForgeTypeId classification rule, revit_mcp/colors.py 1246-line size sharp edge, color_splash tool (README entry), modify_element / set_parameter tools (README entry), Modify category (9 tools), check_view_compatibility(), clean_parameter_value_for_json(), color_elements_by_parameter() (+38 more)

### Community 5 - "test_conventions.py"
Cohesion: 0.12
Nodes (22): parametrize, The docstring is the API contract the model sees before calling., The parameters.py shape: swallowed NameError, blank data, no log., Guarded by the *named* exception -- the distinction the check turns on., DB.ElementId(<BuiltInCategory>) is a different, valid overload., A sanity anchor: the reference tool module must pass every checker., f-strings, async and Python-3-only imports break extension load., _read() (+14 more)

### Community 6 - "revit_mcp/utils.py"
Cohesion: 0.32
Nodes (6): find_family_symbol_safely(), get_element_name_safe(), get_family_name_safe(), IronPython Compatibility Notes, _FailureSwallower, Resolve Revit failures during a transaction without ever showing a modal…

### Community 7 - "extension.json"
Cohesion: 0.15
Nodes (12): author, author_profile, builtin, default_enabled, dependencies, description, image, name (+4 more)

### Community 8 - "get_element_id_value"
Cohesion: 0.19
Nodes (10): Register all analysis routes with the API, register_analysis_routes(), clear_element_colors(), Clear color overrides for elements in a category Args: doc: Revit document…, Register all interop routes with the API, register_interop_routes(), get_element_id_value(), Extract an integer element ID from an Element or ElementId. Accepts both a full… (+2 more)

### Community 9 - "Supported Tools (49) catalogue"
Cohesion: 0.11
Nodes (18): POST route text to /execute_code/ to test without restart, /execute_code/ unauthenticated escape hatch, Tool docstrings are the API contract, Transaction + suppress_warnings(t) invariant, check_clashes tool (README entry), execute_revit_code tool (README entry), get_revit_model_info tool (README entry), save_document tool (README entry) (+10 more)

### Community 10 - "startup.py"
Cohesion: 0.09
Nodes (25): Adding a capability: 4-place edit workflow, Writing New Functions: 3-part registration process, Creating Your Own Tools (2 files + 2 registration lines), is_degraded(), Clear all three collections in place, keeping the same objects., Return a JSON-serializable view for the /status/ route. The default is…, True when at least one domain failed to register., reset() (+17 more)

### Community 11 - "Revit L2 Floor Plan View Pane (Snowdon Towers sample model)"
Cohesion: 0.39
Nodes (8): Claude Desktop Chat Panel (L2 Floor Plan request), get_view Tool-Call Card (embedded floor plan thumbnail), Project Browser — Area Plans (Rentable) → L2 node selected, Revit L2 Floor Plan View Pane (Snowdon Towers sample model), get_view Tool Screenshot (Claude + Revit), Snowdon Towers Sample Architectural.rvt (demo model), get_view (pyRevit route, revit_mcp/views.py), get_revit_view (MCP tool, tools/view_tools.py)

### Community 12 - "clash.py"
Cohesion: 0.20
Nodes (9): _describe(), _location_mm(), Register clash/interference detection routes with the API., Resolve a category name (BuiltInCategory id or friendly alias) to a…, Resolve a list of names to (valid_bics, unknown_names)., Return the centre of the element's bounding box in mm, or None., register_clash_routes(), _resolve_bic() (+1 more)

### Community 13 - "make_element_id"
Cohesion: 0.15
Nodes (13): ElementId cross-version helper invariant, Multi-Version Revit Support (2024-2027), Revit 2027 .NET 10 compatibility note, Register all annotation routes with the API, register_annotation_routes(), Register all MEP routes with the API, register_mep_routes(), Register all tag routes with the API (+5 more)

### Community 14 - "Как сделать свой инструмент для RevitMCP"
Cohesion: 0.06
Nodes (30): 10. Куда смотреть ещё, 1. Общая картина, 2.1. Проверьте, что Revit и RevitMCP работают, 2.2. Найдите Python, 2.3. Распакуйте набор разработчика, 2.4. Установите VS Code и Kilo Code, 2.5. Откройте папку набора в VS Code, 2. Настройка среды (один раз) (+22 more)

### Community 15 - "list_model_elements Tool Screenshot"
Cohesion: 0.60
Nodes (6): list_model_elements Tool Screenshot, Claude Desktop Chat UI Pane, list_model_elements MCP Tool Call, Model Analysis Summary (18 Levels, 54 Rooms), Revit Project Browser Panel (Views Tree), Snowdon Towers Sample Architectural Model

### Community 16 - "format_response"
Cohesion: 0.12
Nodes (27): Tool functions always return str via format_response, parametrize, New /status/ fields must not vanish -- degraded state has to be visible., _revit_call collapses every non-200 and every exception to a string., Guards the fork's ASCII-mangling regression at the presentation layer., The exact shape that regressed: data-bearing dict with no "status"., `{"error": None}` and `{"error": ""}` are success, not failure., test_active_status_renders_the_status_block() (+19 more)

### Community 17 - "test_registration.py"
Cohesion: 0.12
Nodes (25): The guard against a silently dropped tool. Adding or removing a tool is a…, The whole point of discovery-with-isolation. One developer's broken module must…, An exception inside register_*_tools is contained the same way., A route module whose registrar is missing or misspelled is invisible., Both halves must exist, or a route is unreachable from the MCP client. Derived…, Helpers must stay helpers -- otherwise discovery would need to load them., The premise that makes alphabetical registration order safe. Every cross-module…, Module names startup.py's _domain_modules() would scan. (+17 more)

### Community 18 - "Инструкция: как сделать свой инструмент для RevitMCP"
Cohesion: 0.08
Nodes (24): Инструкция: как сделать свой инструмент для RevitMCP, Куда смотреть ещё, Частые ошибки, Часть 1. Что вы вообще делаете, Часть 2. Настройка среды. Один раз, Часть 3. Делаем инструмент, Часть 4. Проверка, Часть 5. Сдача (+16 more)

### Community 19 - "Первичная настройка и пилотная раскатка"
Cohesion: 0.08
Nodes (23): Corporate deployment (closed network), Diagnosing a broken workstation, First-time install (per user), Layout, Releasing, Rollback, Starting Revit from the MCP server, The interpreter: pyRevit's, not ours (+15 more)

### Community 20 - "get_element_name"
Cohesion: 0.19
Nodes (10): Register all building creation routes with the API, register_building_routes(), Register all model information routes with the API, register_model_info_routes(), Register all room routes with the API, register_room_routes(), get_element_name(), Get the name of a Revit element. Useful for both FamilySymbol and other… (+2 more)

### Community 21 - "contrib-kit/conventions.py"
Cohesion: 0.15
Nodes (22): _blank_strings_and_comments(), check_element_id(), check_encoding_cookie(), check_ironpython_dialect(), check_package(), check_route_module(), check_route_registrar(), check_tool_module() (+14 more)

### Community 22 - "suppress_warnings"
Cohesion: 0.19
Nodes (10): Register code execution routes with the API., register_code_execution_routes(), Register all detail routes with the API, register_detail_routes(), Register all documentation routes with the API, register_documentation_routes(), Register all editing routes with the API, register_editing_routes() (+2 more)

### Community 23 - "scripts/conventions.py"
Cohesion: 0.15
Nodes (22): _blank_strings_and_comments(), check_element_id(), check_encoding_cookie(), check_ironpython_dialect(), check_package(), check_route_module(), check_route_registrar(), check_tool_module() (+14 more)

### Community 24 - "configure_hermes.py"
Cohesion: 0.15
Nodes (21): build_block(), detect_indent(), die(), find_mcp_servers(), hermes_config_path(), hermes_is_running(), main(), Parse with ruamel; return an error string, or None if the doc is usable. (+13 more)

### Community 25 - "Architecture"
Cohesion: 0.10
Nodes (19): Anti-Patterns, Architectural Constraints, Architecture, Bare `ElementId(int)` / `.IntegerValue`, Component Responsibilities, Cross-Cutting Concerns, Data Flow, Entry Points (+11 more)

### Community 26 - "find_family_symbol_safely"
Cohesion: 0.29
Nodes (6): Register all placement-related routes with the API, register_placement_routes(), Register all structure routes with the API, register_structure_routes(), find_family_symbol_safely(), Safely find a family symbol by name. Uses get_element_name() for consistent…

### Community 27 - "intake_package.py"
Cohesion: 0.20
Nodes (17): Exception, apply_package(), check_collisions(), check_layout(), _fail(), main(), _norm(), Only the manifest, the two halves, optional tests and notes. (+9 more)

### Community 28 - "revitmcp_kit.py"
Cohesion: 0.45
Nodes (12): cmd_check(), cmd_new(), cmd_pack(), cmd_probe(), _die(), _find_package(), _load_manifest(), main() (+4 more)

### Community 29 - "Contributing"
Cohesion: 0.17
Nodes (11): Adding a capability: two files, Commits, Contributing, How discovery finds your module, Non-negotiable invariants, Testing, The two-runtime rule (read this first), Tool budget (+3 more)

### Community 30 - "Codebase Concerns"
Cohesion: 0.18
Nodes (10): Codebase Concerns, Dependencies at Risk, Fragile Areas, Known Bugs, Missing Critical Features, Performance Bottlenecks, Scaling Limits, Security Considerations (+2 more)

### Community 31 - "Coding Conventions"
Cohesion: 0.18
Nodes (10): Code Style, Coding Conventions, Comments, Error Handling, Function Design, Import Organization, Logging, Module Design (+2 more)

### Community 32 - "process_tools.py"
Cohesion: 0.20
Nodes (10): _bridge_state(), _discover(), [(version, exe_path)] for every Revit found, newest first., C:\\...\\Revit 2027\\Revit.exe' -> '2027'; falls back to the folder name., Best-effort progress log. ctx.info() raises when there is no active request…, One of "ready", "no_document", "down". The distinction matters: `/status/`…, Register Revit process lifecycle tools., register_process_tools() (+2 more)

### Community 41 - "AGENTS.md — правила для ИИ-ассистента в этом репозитории"
Cohesion: 0.20
Nodes (9): AGENTS.md — правила для ИИ-ассистента в этом репозитории, Главное правило: НЕ создавай файлы вручную, Два рантайма — не смешивать, Докстринг инструмента — это контракт для модели, Запреты, Коммиты, Куда смотреть дальше, Обязательный цикл (+1 more)

### Community 42 - "Агент: сборка пакета инструмента Revit MCP"
Cohesion: 0.20
Nodes (9): Агент: сборка пакета инструмента Revit MCP, Если застрял, Чего не делать никогда, Шаг 0. Выяснить задачу до того, как писать код, Шаг 1. Сгенерировать каркас, Шаг 2. Заполнить TODO, Шаг 3. Проверить форму, Шаг 4. Проверить поведение на живой модели (+1 more)

### Community 43 - "Набор разработчика инструментов Revit MCP"
Cohesion: 0.20
Nodes (9): Главное, что ломается, Докстринг — это не документация, Как это выглядит целиком, Набор разработчика инструментов Revit MCP, Не редактируйте `conventions.py`, Чего в пакет не входит, Четыре команды, Что делает `probe` и почему он важен (+1 more)

### Community 44 - "Разработка инструментов Revit MCP"
Cohesion: 0.20
Nodes (9): 1. Назначение, 2. Когда применять и когда нет, 3. Входные данные и грабли, 4. Эталон, 5. Процедура, 6. Выходные данные, 7. Запреты, 8. Приёмка (+1 more)

### Community 45 - "Агент: разработка инструмента Revit MCP"
Cohesion: 0.20
Nodes (9): Агент: разработка инструмента Revit MCP, Если застрял, Чего не делать никогда, Шаг 0. Понять задачу, прежде чем писать, Шаг 1. Проверить, не существует ли это уже, Шаг 2. Сгенерировать каркас, Шаг 3. Заполнить TODO, Шаг 4. Проверить (+1 more)

### Community 46 - "External Integrations"
Cohesion: 0.20
Nodes (9): APIs & External Services, Authentication & Identity, CI/CD & Deployment, Data Storage, Environment Configuration, External Integrations, Integration Risks, Monitoring & Observability (+1 more)

### Community 47 - "Testing Patterns"
Cohesion: 0.20
Nodes (9): Common Patterns, Coverage, Fixtures and Factories, Mocking, Test File Organization, Test Framework, Test Structure, Test Types (+1 more)

### Community 48 - "AGENTS.md — правила для ИИ-ассистента в этом наборе"
Cohesion: 0.25
Nodes (7): AGENTS.md — правила для ИИ-ассистента в этом наборе, Главное правило: НЕ создавай файлы вручную, Два рантайма — не смешивать, Докстринг инструмента — это контракт для модели, Если застрял, Запреты, Обязательный цикл

### Community 49 - "Technology Stack"
Cohesion: 0.25
Nodes (7): Configuration, Frameworks, Key Dependencies, Languages, Platform Requirements, Runtime, Technology Stack

### Community 50 - "Codebase Structure"
Cohesion: 0.25
Nodes (7): Codebase Structure, Directory Layout, Directory Purposes, Key File Locations, Naming Conventions, Special Directories, Where to Add New Code

### Community 51 - "Скилл Hermes для разработки инструментов"
Cohesion: 0.33
Nodes (5): Грабли frontmatter, Куда его класть, Почему копия, а не ссылка, Скилл Hermes для разработки инструментов, Что ещё нужно сделать в том репозитории

### Community 52 - "new_tool.py"
Cohesion: 0.90
Nodes (4): _add_to_manifest(), _fail(), main(), _write()

### Community 54 - "clash_tools.py"
Cohesion: 0.50
Nodes (3): Strict 1:1 domain mirroring pattern, Register clash detection tools with the MCP server., register_clash_tools()

### Community 55 - "_expected_tools"
Cohesion: 0.67
Nodes (3): _expected_tools(), main(), Tool names the payload is supposed to expose, or None if unavailable.…

## Ambiguous Edges - Review These
- `Revit MCP Server README` → `LLM.txt Project Architecture (stale nested-extension layout)`  [AMBIGUOUS]
  CLAUDE.md · relation: conceptually_related_to

## Knowledge Gaps
- **216 isolated node(s):** `name`, `type`, `builtin`, `default_enabled`, `rocket_mode_compatible` (+211 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **25 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Revit MCP Server README` and `LLM.txt Project Architecture (stale nested-extension layout)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `revit_mcp/utils.py vs tools/utils.py naming collision` connect `tools/utils.py` to `revit_mcp/utils.py`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Why does `format_response()` connect `format_response` to `tools/utils.py`, `process_tools.py`, `Commit c1231f6: format_response mislabeling fix`, `clash_tools.py`, `analysis_tools.py`, `annotation_tools.py`, `building_tools.py`, `code_execution_tools.py`, `colors_tools.py`, `detail_tools.py`, `documentation_tools.py`, `editing_tools.py`, `family_tools.py`, `interop_tools.py`, `model_tools.py`, `room_tools.py`, `status_tools.py`, `tag_tools.py`, `transform_tools.py`, `view_management_tools.py`, `view_tools.py`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Why does `get_element_id_value()` connect `get_element_id_value` to `parameters.py`, `colors.py`, `revit_mcp/utils.py`, `clash.py`, `make_element_id`, `get_element_name`, `suppress_warnings`, `find_family_symbol_safely`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **What connects `name`, `type`, `builtin` to the rest of the system?**
  _216 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `tools/utils.py` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._
- **Should `main.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0545790934320074 - nodes in this community are weakly interconnected._