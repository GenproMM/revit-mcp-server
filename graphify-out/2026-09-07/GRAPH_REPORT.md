# Graph Report - .  (2026-09-04)

## Corpus Check
- 61 files · ~79,347 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 350 nodes · 552 edges · 41 communities (19 shown, 22 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 18 edges (avg confidence: 0.83)
- Token cost: 253,539 input · 0 output

## Community Hubs (Navigation)
- MCP Tool Registration Layer
- CLAUDE.md Project Conventions
- Shared Parameter Classification
- main.py Transport Bridge
- colors.py Value Formatting
- colors.py Color Generation
- utils.py Naming Helpers
- pyRevit Extension Manifest
- Route Registration Barrel
- Document Save & Editing
- Adding a New Capability
- get_view Tool Demo
- Clash Detection
- ElementId Version Helpers
- Transaction Failure Suppression
- list_model_elements Demo
- Value Normalization Helpers
- uv Install & Setup
- analysis.py Route Module
- annotation.py Route Module
- building.py Route Module
- code_execution.py Route Module
- detail.py Route Module
- documentation.py Route Module
- mep.py Route Module
- model_info.py Route Module
- placement.py Route Module
- rooms.py Route Module
- status.py Route Module
- structure.py Route Module
- tags.py Route Module
- transforms.py Route Module
- views.py Route Module
- Millimeter Unit Convention
- Route Handlers Never Raise
- Broad except:pass Debt
- Bulk Route Partial Success
- Hardcoded Port 48884
- Single 30s Timeout
- Package Metadata

## God Nodes (most connected - your core abstractions)
1. `format_response()` - 49 edges
2. `register_tools()` - 25 edges
3. `register_routes()` - 24 edges
4. `color_elements_by_parameter()` - 14 edges
5. `_safe_str()` - 9 edges
6. `Revit MCP Server README` - 9 edges
7. `Supported Tools (49) catalogue` - 9 edges
8. `get_element_id_value()` - 8 edges
9. `normalize_string()` - 7 edges
10. `LLM.txt Context Document` - 7 edges

## Surprising Connections (you probably didn't know these)
- `httpx==0.28.1 package` --conceptually_related_to--> `revit_get()`  [INFERRED]
  requirements.txt → main.py
- `Dict-is-error-only-if-truthy-error-key rule` --rationale_for--> `format_response()`  [EXTRACTED]
  CLAUDE.md → tools/utils.py
- `Available Tools (31) - historical tool count` --semantically_similar_to--> `Supported Tools (49) catalogue`  [INFERRED] [semantically similar]
  LLM.txt → README.md
- `Revit L2 Floor Plan View Pane (Snowdon Towers sample model)` --references--> `get_view (pyRevit route, revit_mcp/views.py)`  [INFERRED]
  images/get_view_tool.png → revit_mcp/views.py
- `ElementId cross-version helper invariant` --references--> `get_element_id_value()`  [EXTRACTED]
  CLAUDE.md → revit_mcp/utils.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Two-Runtime architecture (CPython MCP server + IronPython Revit extension)** — main, tools_utils, tests_test_init_latency, startup, revit_mcp_utils, claude_two_runtime_rule [INFERRED 0.85]
- **Domain mirroring pattern instantiated by clash detection** — revit_mcp_clash, tools_clash_tools, startup, tools_init, claude_domain_mirroring_pattern [INFERRED 0.85]
- **Three docs describing the same 2/3/4-step tool registration workflow** — claude_adding_capability_workflow, readme_creating_your_own_tools, llm_writing_new_functions_workflow [INFERRED 0.90]
- **get_view end-to-end flow: Claude request → MCP tool → pyRevit route → rendered floor plan** — images_get_view_tool_claude_desktop_panel, images_get_view_tool_get_view_tool_call_card, tools_view_tools_get_revit_view, revit_mcp_views_get_view, images_get_view_tool_revit_l2_view_pane [INFERRED 0.85]
- **MCP Tool Invocation and Response Flow (Claude to Revit)** — images_list_model_tool_list_model_elements_tool, images_list_model_tool_snowdon_towers_model, images_list_model_tool_claude_chat_ui, images_list_model_tool_model_analysis_summary [INFERRED 0.85]

## Communities (41 total, 22 thin omitted)

### Community 0 - "MCP Tool Registration Layer"
Cohesion: 0.06
Nodes (51): Strict 1:1 domain mirroring pattern, MCP Server Runtime (CPython >=3.11), Tool functions always return str via format_response, Register analysis tools with the MCP server., register_analysis_tools(), Register annotation tools with the MCP server., register_annotation_tools(), Register building creation tools with the MCP server. (+43 more)

### Community 1 - "CLAUDE.md Project Conventions"
Cohesion: 0.06
Nodes (37): MCP client -> main.py+tools -> startup.py+revit_mcp -> Revit API architecture, Commit c1231f6: format_response mislabeling fix, Dict-is-error-only-if-truthy-error-key rule, graphify knowledge graph integration workflow, CLAUDE.md Contributor Guide, POST route text to /execute_code/ to test without restart, Obsidian Knowledge Vault session workflow, Revit Extension Runtime (IronPython 2.7) (+29 more)

### Community 2 - "Shared Parameter Classification"
Cohesion: 0.10
Nodes (26): Shared parameter ForgeTypeId classification rule, color_splash tool (README entry), modify_element / set_parameter tools (README entry), Modify category (9 tools), _as_bool(), _classify_definition(), _get_binding_categories(), _get_binding_kind() (+18 more)

### Community 3 - "main.py Transport Bridge"
Cohesion: 0.13
Nodes (21): Any, AsyncClient, Never print() under stdio transport, Context, FastMCP framework, Image, _get_client(), Simple GET request to Revit API (+13 more)

### Community 4 - "colors.py Value Formatting"
Cohesion: 0.13
Nodes (17): revit_mcp/colors.py 1246-line size sharp edge, clean_parameter_value_for_json(), format_numeric_for_json(), get_numeric_parameter_raw_value(), get_parameter_value_for_sorting(), get_parameter_value_improved(), get_parameter_value_json_safe(), list_category_parameters() (+9 more)

### Community 5 - "colors.py Color Generation"
Cohesion: 0.12
Nodes (17): check_view_compatibility(), color_elements_by_parameter(), generate_distinct_colors(), generate_gradient_colors(), generate_random_color(), hex_to_rgb(), interpolate_color(), Interpolate color based on position (0.0 to 1.0) for smooth gradients Args:… (+9 more)

### Community 6 - "utils.py Naming Helpers"
Cohesion: 0.22
Nodes (12): revit_mcp/utils.py vs tools/utils.py naming collision, find_family_symbol_safely(), get_element_name_safe(), get_family_name_safe(), IronPython Compatibility Notes, _describe(), find_family_symbol_safely(), get_element_name() (+4 more)

### Community 7 - "pyRevit Extension Manifest"
Cohesion: 0.15
Nodes (12): author, author_profile, builtin, default_enabled, dependencies, description, image, name (+4 more)

### Community 8 - "Route Registration Barrel"
Cohesion: 0.20
Nodes (8): Register all interop routes with the API, register_interop_routes(), Register all parameter routes with the API, register_parameter_routes(), Register all view management routes with the API, register_view_management_routes(), Register all MCP route modules, register_routes()

### Community 9 - "Document Save & Editing"
Cohesion: 0.22
Nodes (7): Transaction + suppress_warnings(t) invariant, save_document tool (README entry), Interop & Persistence category (4 tools), Register document persistence routes with the API., register_document_routes(), Register all editing routes with the API, register_editing_routes()

### Community 10 - "Adding a New Capability"
Cohesion: 0.36
Nodes (7): Adding a capability: 4-place edit workflow, Writing New Functions: 3-part registration process, Creating Your Own Tools (2 files + 2 registration lines), Register clash/interference detection routes with the API., register_clash_routes(), Register color-related routes with the API, register_color_routes()

### Community 11 - "get_view Tool Demo"
Cohesion: 0.39
Nodes (8): Claude Desktop Chat Panel (L2 Floor Plan request), get_view Tool-Call Card (embedded floor plan thumbnail), Project Browser — Area Plans (Rentable) → L2 node selected, Revit L2 Floor Plan View Pane (Snowdon Towers sample model), get_view Tool Screenshot (Claude + Revit), Snowdon Towers Sample Architectural.rvt (demo model), get_view (pyRevit route, revit_mcp/views.py), get_revit_view (MCP tool, tools/view_tools.py)

### Community 12 - "Clash Detection"
Cohesion: 0.29
Nodes (6): _location_mm(), Resolve a category name (BuiltInCategory id or friendly alias) to a…, Resolve a list of names to (valid_bics, unknown_names)., Return the centre of the element's bounding box in mm, or None., _resolve_bic(), _resolve_categories()

### Community 13 - "ElementId Version Helpers"
Cohesion: 0.33
Nodes (7): ElementId cross-version helper invariant, Multi-Version Revit Support (2024-2027), Revit 2027 .NET 10 compatibility note, get_element_id_value(), make_element_id(), Create a DB.ElementId from an integer value. Compatible with Revit 2024, 2025,…, Extract an integer element ID from an Element or ElementId. Accepts both a full…

### Community 14 - "Transaction Failure Suppression"
Cohesion: 0.29
Nodes (6): clear_element_colors(), Clear color overrides for elements in a category Args: doc: Revit document…, _FailureSwallower, Resolve Revit failures during a transaction without ever showing a modal…, Configure a transaction so Revit failures never block on a modal dialog.…, suppress_warnings()

### Community 15 - "list_model_elements Demo"
Cohesion: 0.60
Nodes (6): list_model_elements Tool Screenshot, Claude Desktop Chat UI Pane, list_model_elements MCP Tool Call, Model Analysis Summary (18 Levels, 54 Rooms), Revit Project Browser Panel (Views Tree), Snowdon Towers Sample Architectural Model

### Community 16 - "Value Normalization Helpers"
Cohesion: 0.50
Nodes (4): get_parameter_value_safe(), Safely get parameter value from element Args: element: Revit element…, normalize_string(), Whitespace-trimmed variant of sanitize_string().

### Community 17 - "uv Install & Setup"
Cohesion: 0.67
Nodes (3): uv install command (brew / irm install.ps1), README_UV.md UV Setup Guide, uv venv virtual environment setup steps

## Ambiguous Edges - Review These
- `Revit MCP Server README` → `LLM.txt Project Architecture (stale nested-extension layout)`  [AMBIGUOUS]
  CLAUDE.md · relation: conceptually_related_to

## Knowledge Gaps
- **35 isolated node(s):** `builtin`, `default_enabled`, `type`, `rocket_mode_compatible`, `name` (+30 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **22 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Revit MCP Server README` and `LLM.txt Project Architecture (stale nested-extension layout)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `MCP client -> main.py+tools -> startup.py+revit_mcp -> Revit API architecture` connect `CLAUDE.md Project Conventions` to `Adding a New Capability`, `main.py Transport Bridge`?**
  _High betweenness centrality (0.112) - this node is a cross-community bridge._
- **Why does `register_color_routes()` connect `Adding a New Capability` to `Route Registration Barrel`, `colors.py Value Formatting`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `register_parameter_routes()` connect `Route Registration Barrel` to `Shared Parameter Classification`, `Adding a New Capability`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **What connects `builtin`, `default_enabled`, `type` to the rest of the system?**
  _35 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `MCP Tool Registration Layer` be split into smaller, more focused modules?**
  _Cohesion score 0.06322624743677376 - nodes in this community are weakly interconnected._
- **Should `CLAUDE.md Project Conventions` be split into smaller, more focused modules?**
  _Cohesion score 0.0553306342780027 - nodes in this community are weakly interconnected._