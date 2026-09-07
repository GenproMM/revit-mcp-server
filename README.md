# Revit MCP Server

MCP server for Autodesk Revit 2024/2025/2026/2027 via pyRevit — 51 tools for building design, editing, analysis, clash detection, MEP, interop, documentation, and model persistence.

Works with any MCP client: Claude Desktop, Claude Code, Cursor, Windsurf, Copilot, or any other MCP-compatible application.

## How It Works

```
AI Client ──stdio/SSE/HTTP──> MCP Server (Python/FastMCP) ──HTTP :48884──> pyRevit Routes ──> Revit API
```

The MCP server runs on your machine and communicates with Revit through pyRevit's Routes API. Any MCP-compatible AI client can connect to it.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Windows 10/11** | Revit is Windows-only |
| **Autodesk Revit** | 2024, 2025, 2026, or 2027 |
| **pyRevit** | Installed and loaded in Revit |
| **uv** | Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/)) |
| **A project open in Revit** | Tools require an active document |

## Install pyRevit (if not already installed)

pyRevit is a free add-in that lets scripts run inside Revit. This MCP server needs it to communicate with Revit.

1. Go to https://github.com/pyrevitlabs/pyRevit/releases
2. Download the latest **.exe installer** (e.g. `pyRevit_CLI_x.x.x.x_admin_signed.exe`)
3. Run the installer — accept all defaults, click **Next** through each screen
4. Open (or restart) Revit — you should see a **pyRevit** tab in the ribbon at the top
5. In the pyRevit tab, click **Settings** (gear icon)
6. In the Settings window, go to the **Routes** section on the left
7. Check the box to **Enable Routes Server**
8. Click **Save Settings** and let pyRevit reload

To verify: open a browser and go to `http://localhost:48884/` — you should see a response (not a "connection refused" error).

## Quick Start

> **Deploying to a team?** Don't follow this section. The steps below set up a
> single developer machine from a git clone with internet access. For rolling
> this out across an organisation — a file share, self-contained runtime,
> silent updates, and no admin rights on workstations — see
> [deploy/README.md](deploy/README.md).

### Step 1: Clone and install

```bash
git clone https://github.com/Demolinator/revit-mcp-server.git
cd revit-mcp-server
uv sync
```

### Step 2: Install the pyRevit extension

The `revit_mcp/` folder and `startup.py` need to run inside Revit via pyRevit.

1. Copy the repo folder to `%APPDATA%\pyRevit\Extensions\`
2. Rename the copy to **`revit-mcp-server.extension`** — the trailing
   `.extension` is required, and the name itself matters: pyRevit keys its
   config section by the folder name, so a different name is a different
   extension as far as its enabled/disabled state is concerned.
3. In Revit, go to pyRevit tab > Settings > Custom Extensions
4. Add the path to the `.extension` folder
5. **Fully restart Revit.** pyRevit's Reload button is not enough for changes
   under `revit_mcp/` — reload-then-request has been observed to crash Revit.

> The "MCP Server for Revit Python" entry in pyRevit's Extensions panel points
> at a different upstream repository and will not install this fork.

### Step 3: Activate pyRevit Routes

1. In Revit, go to pyRevit tab > Settings
2. Navigate to Routes > activate **Routes Server**
3. pyRevit will start listening on `http://localhost:48884/`

### Step 4: Verify connection

Open a browser and go to:

```
http://localhost:48884/revit_mcp/status/
```

You should see:

```json
{
  "status": "active",
  "health": "healthy",
  "revit_available": true,
  "document_title": "your_project_name",
  "api_name": "revit_mcp"
}
```

### Step 5: Start the MCP server

```bash
uv run main.py
```

That's it. Your AI client can now connect.

## Connecting Your AI Client

### Claude Desktop / Claude Code

Add to your MCP config:

```json
{
  "mcpServers": {
    "revit": {
      "command": "uv",
      "args": ["run", "main.py"],
      "cwd": "/path/to/revit-mcp-server"
    }
  }
}
```

### Cursor / Windsurf / Other MCP Clients

Use HTTP transport:

```bash
uv run main.py --streamable-http
```

Then configure your client to connect to `http://localhost:8000/mcp`.

### Transport Modes

| Flag | Transport | Endpoints | Use Case |
|------|-----------|-----------|----------|
| *(none)* | stdio | stdin/stdout | Claude Desktop / Claude Code |
| `--sse` | SSE | `/sse`, `/messages/` | Legacy clients |
| `--streamable-http` | HTTP | `/mcp` | HTTP-based clients |
| `--combined` | Both | All above | Maximum compatibility |

### Testing with MCP Inspector

```bash
mcp dev main.py
```

Then open `http://127.0.0.1:6274` in your browser.

## Supported Tools (51)

### Create (15)

| Tool | Description |
|------|-------------|
| `create_level` | Create new levels with elevations |
| `create_line_based_element` | Create walls, beams, and other line-based elements |
| `create_surface_based_element` | Create floors, roofs, and surface elements |
| `place_family` | Place a family instance at specified location |
| `create_grid` | Create column grid lines |
| `create_structural_framing` | Create structural beams and framing |
| `create_sheet` | Create new drawing sheets |
| `create_schedule` | Create schedules with custom fields |
| `create_room` | Create rooms at specified levels |
| `create_room_separation` | Create room separation boundary lines |
| `create_duct` | Create ducts between two points (MEP) |
| `create_pipe` | Create pipes between two points (MEP) |
| `create_mep_system` | Create mechanical or piping systems |
| `create_detail_line` | Create view-specific detail lines |
| `create_view` | Create floor plans, sections, elevations, 3D views |

### Query (13)

| Tool | Description |
|------|-------------|
| `get_revit_status` | Check if the API is active and responding |
| `get_revit_model_info` | Get model information |
| `list_levels` | Get all levels with elevations |
| `list_families` | Get available family types |
| `list_family_categories` | Get all family categories |
| `get_revit_view` | Export a view as an image |
| `list_revit_views` | List all exportable views |
| `get_current_view_info` | Get active view details |
| `get_current_view_elements` | Get elements in current view |
| `get_selected_elements` | Get currently selected elements |
| `list_category_parameters` | List parameters for a category |
| `get_element_properties` | Get all parameters and properties of an element |
| `list_project_parameters` | List project parameters, flagging which are shared |

### Modify (9)

| Tool | Description |
|------|-------------|
| `delete_elements` | Delete elements from the model |
| `modify_element` | Modify element parameter values |
| `color_splash` | Color elements by parameter values |
| `clear_colors` | Reset element colors |
| `tag_walls` | Tag all walls in current view |
| `set_parameter` | Set a single parameter value on an element |
| `tag_elements` | Tag specific elements with annotation symbols |
| `transform_elements` | Move, copy, rotate, or mirror elements |
| `set_active_view` | Switch the active view in Revit |

### Analyze (5)

| Tool | Description |
|------|-------------|
| `ai_element_filter` | Filter elements by category and parameters |
| `export_room_data` | Export room areas, volumes, boundaries |
| `get_material_quantities` | Material takeoff data |
| `check_clashes` | Detect hard clashes (interferences) between disciplines, e.g. structure vs MEP |
| `analyze_model_statistics` | Element counts and model stats |

### Document (2)

| Tool | Description |
|------|-------------|
| `create_dimensions` | Create dimension annotations |
| `export_document` | Export views to PDF or image |

### Interop & Persistence (4)

| Tool | Description |
|------|-------------|
| `export_ifc` | Export model to IFC format (IFC2x3/IFC4) |
| `link_file` | Link or import DWG, DXF, DGN, SAT, SKP, 3DM, or RVT files |
| `load_family` | Load a Revit family (`.rfa`) from disk so its types can be placed |
| `save_document` | Save / Save-As the model to disk (persistence across sessions) |

### Advanced (1)

| Tool | Description |
|------|-------------|
| `execute_revit_code` | Execute IronPython code in Revit context |

### Revit process (2)

The only two tools that work while Revit is **closed** — everything else goes
through the pyRevit Routes bridge, which lives inside the Revit process.

| Tool | Description |
|------|-------------|
| `get_revit_process_status` | Is Revit running, is a document open, which versions are installed |
| `start_revit` | Launch Revit (optionally opening a model) and wait for the bridge |

## Architecture

Two runtimes communicate over HTTP:

| Component | Runtime | Location | Purpose |
|-----------|---------|----------|---------|
| `main.py` + `tools/` | Python 3.11+ (CPython) | Your machine | MCP protocol, tool definitions |
| `startup.py` + `revit_mcp/` | IronPython 2.7 (inside Revit) | Revit process | pyRevit route handlers, Revit API |

## Multi-Version Revit Support

This server supports Revit 2024, 2025, 2026, and 2027 through centralized helper functions that handle the ElementId API differences across versions:

- `get_element_id_value()` — Extracts integer IDs using `.Value` (2024+) with `.IntegerValue` fallback
- `make_element_id()` — Creates ElementIds using `System.Int64` (2024+) with `int` fallback

No configuration needed — version detection is automatic via try/except at runtime.

> **Revit 2027 note:** Revit 2027 runs on **.NET 10** (vs .NET 8 in 2025/2026). This MCP server is pyRevit-based, so .NET compatibility is handled by pyRevit itself — ensure you run a **pyRevit build with Revit 2027 support**. None of the 48 tools use APIs removed in 2027 (AXM/FormIt import, `Mechanical.Zone` members, legacy rebar creation, or the dropped `EnergyDataSettings` properties).

## Unit Handling

All tools accept **millimeters (mm)**. The server converts to Revit's internal feet.

| From | To mm |
|------|-------|
| meters | x 1000 |
| feet | x 304.8 |
| inches | x 25.4 |

## Creating Your Own Tools

Adding a new tool takes 2 files. Registration is by convention — there is no list to
append to, so a forgotten registration line is no longer possible:

1. **Route handler** in `revit_mcp/<domain>.py` (IronPython 2.7), exposing
   `register_<domain>_routes(api)`
2. **Tool definition** in `tools/<domain>_tools.py` (Python 3.11+), exposing
   `register_<domain>_tools(mcp, revit_get, revit_post, revit_image=None)`

Then add the new tool's name to `tests/unit/tool_manifest.txt` in the same commit — that
file is the authoritative tool list, and `deploy/gate.py` refuses to publish a build that
diverges from it.

Verify with `uv run pytest tests/unit`, then call the tool through `mcp dev main.py`.

**Read [CONTRIBUTING.md](CONTRIBUTING.md) first.** It covers the two-runtime rule, the
transaction and ElementId invariants, and how to write a tool docstring — which is the
API contract the model actually sees.

See `LLM.txt` for background (note: its directory layout and tool count are out of date).

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) — almost none of
the conventions in this codebase are enforced by tooling, so they are worth reading before
your first pull request.

## Author

**Talal Ahmed**

## License

MIT
