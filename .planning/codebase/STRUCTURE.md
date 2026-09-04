# Codebase Structure

**Analysis Date:** 2026-09-04

## Directory Layout

```
revit-mcp-server/
├── main.py                 # MCP server entry point + HTTP bridge to Revit
├── startup.py              # pyRevit extension entry point; registers all routes
├── extension.json          # pyRevit extension manifest
├── pyproject.toml          # Python project metadata (mcp[cli], py>=3.11)
├── requirements.txt        # Pinned runtime deps for the MCP process
├── uv.lock                 # uv lockfile
├── .python-version         # Pinned interpreter version
├── tools/                  # MCP tool layer (CPython, async) — 48 tools
├── revit_mcp/              # pyRevit Routes handlers (IronPython, sync)
├── tests/                  # Standalone stdio smoke scripts
├── images/                 # README screenshots
├── LLM.txt                 # Long-form reference doc for LLM consumers
├── README.md               # User-facing setup and tool catalogue
├── README_UV.md            # uv-specific setup notes
└── .planning/codebase/     # GSD codebase map documents
```

## Directory Purposes

**`tools/`:**
- Purpose: MCP-facing tool definitions; the only place `@mcp.tool()` appears
- Contains: One `*_tools.py` per Revit domain, plus `__init__.py` registry and `utils.py` formatter
- Key files: `tools/__init__.py` (registration fan-out), `tools/utils.py` (`format_response`)

**`revit_mcp/`:**
- Purpose: Revit-side REST handlers; the only place the Revit API is touched
- Contains: One module per domain, each exporting `register_*_routes(api)`
- Key files: `revit_mcp/utils.py` (version-safe helpers, `suppress_warnings`), `revit_mcp/colors.py` (largest, 1246 lines), `revit_mcp/building.py` (662 lines), `revit_mcp/placement.py` (612 lines)

**`tests/`:**
- Purpose: End-to-end smoke checks driven through a real stdio MCP client
- Contains: `tests/test_init_latency.py` (cold-start budget < 2.0s), `tests/test_model_info_format.py` (no false error header)
- Note: Plain `asyncio.run` scripts with `assert`, not a pytest suite

**`images/`:**
- Purpose: README assets only; no code

## Key File Locations

**Entry Points:**
- `main.py`: MCP server; transport chosen by argv (`stdio` default, `--sse`, `--http`, `--combined`)
- `startup.py`: pyRevit extension load hook; calls `register_routes()` at import time

**Configuration:**
- `pyproject.toml`: project name, `requires-python >=3.11`, `mcp[cli]>=1.9.0`
- `requirements.txt`: fully pinned transitive set
- `extension.json`: pyRevit manifest (`name`, `type: extension`, rocket-mode compatible)
- `main.py:22-24`: `REVIT_HOST` env var, hardcoded port `48884`, `BASE_URL`

**Core Logic:**
- `tools/__init__.py`: single place to wire a new tool module
- `startup.py`: single place to wire a new route module
- `main.py:44-83`: `revit_get` / `revit_post` / `revit_image` / `_revit_call`
- `tools/utils.py`: response normalization for every tool
- `revit_mcp/utils.py`: element ID, naming, and transaction-safety helpers

**Testing:**
- `tests/test_init_latency.py`, `tests/test_model_info_format.py`

## Naming Conventions

**Files:**
- Route modules: `revit_mcp/<domain>.py` — e.g. `mep.py`, `rooms.py`, `clash.py`
- Tool modules: `tools/<domain>_tools.py` — e.g. `mep_tools.py`, `room_tools.py`, `clash_tools.py`
- Domain names pair up but are not always identical (`revit_mcp/rooms.py` ↔ `tools/room_tools.py`; `tools/family_tools.py` maps onto `revit_mcp/placement.py`)

**Functions:**
- Route registrars: `register_<domain>_routes(api)`
- Tool registrars: `register_<domain>_tools(mcp, revit_get, revit_post, revit_image=None)`
- Tools are `snake_case`, verb-first, and become the client-visible name (`check_clashes`, `get_revit_model_info`)

**Endpoints:**
- Lowercase snake_case with both leading and trailing slashes: `/status/`, `/place_family/`, `/clash_check/`, `/save_document/`

**Directories:**
- Flat, single-level; no nesting inside `tools/` or `revit_mcp/`

## Where to Add New Code

**New Revit capability (the standard change):**
1. Route handler: add `@api.route("/<name>/", methods=["POST"])` inside the matching `revit_mcp/<domain>.py`, or create the module with a `register_<domain>_routes(api)` function
2. Register it: add the import + call in `startup.py` `register_routes()`
3. Tool wrapper: add an `@mcp.tool()` coroutine in `tools/<domain>_tools.py`, returning `format_response(await revit_post(...))`
4. Register it: add the import + call in `tools/__init__.py` `register_tools()`
5. Update the tool count and catalogue in `README.md`

**New domain module:**
- Revit side: `revit_mcp/<domain>.py` with `# -*- coding: UTF-8 -*-`, IronPython-compatible syntax
- MCP side: `tools/<domain>_tools.py`
- Both must be wired into their respective registries or they are silently absent

**Shared Revit helpers:**
- `revit_mcp/utils.py` — import from route modules as `from utils import ...` (top-level, not relative)

**Shared MCP helpers:**
- `tools/utils.py` — import as `from .utils import format_response`

**Tests:**
- `tests/test_<topic>.py`, written as a standalone stdio client script run with `python tests/<file>.py`

## Special Directories

**`.venv/`:**
- Purpose: local virtualenv for the CPython MCP process
- Generated: Yes | Committed: No (`.gitignore`)

**`__pycache__/`, `tools/__pycache__/`:**
- Purpose: bytecode cache
- Generated: Yes | Committed: No

**`.planning/codebase/`:**
- Purpose: GSD codebase map documents
- Generated: Yes (by mapper agents) | Committed: Yes

**`images/`:**
- Purpose: README screenshots
- Generated: No | Committed: Yes

---

*Structure analysis: 2026-09-04*
