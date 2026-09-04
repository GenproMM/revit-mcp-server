# Coding Conventions

**Analysis Date:** 2026-09-04

## Two-Runtime Rule (read first)

This repo holds **two separate Python codebases with different rules**:

| Side | Location | Runtime | Python |
|------|----------|---------|--------|
| MCP server | `main.py`, `tools/` | CPython (>=3.11, see `pyproject.toml`) | Modern async Python |
| Revit extension | `startup.py`, `revit_mcp/` | IronPython inside pyRevit / Revit | Python 2.7-compatible dialect |

Never mix them. `revit_mcp/` must stay IronPython-safe: no f-strings, no
`async`/`await`, no `pathlib`, no modern typing. `tools/` is free to use
`async def`, `list[str]`, and f-strings.

## Naming Patterns

**Files:**
- Extension modules: bare domain name — `revit_mcp/clash.py`, `revit_mcp/mep.py`
- MCP tool modules: `<domain>_tools.py` — `tools/clash_tools.py`, `tools/view_tools.py`
- Every extension module has a matching tool module (1:1 by domain)

**Functions:**
- `snake_case` throughout both sides
- Registration entry points: `register_<domain>_routes(api)` in `revit_mcp/`,
  `register_<domain>_tools(mcp, revit_get, revit_post, revit_image=None)` in `tools/`
- Route handlers: `<action>_handler` — `delete_elements_handler` (`revit_mcp/editing.py:22`)
- Module-private helpers prefixed with `_` — `_resolve_bic`, `_resolve_categories`
  (`revit_mcp/clash.py`), `_get_client`, `_revit_call` (`main.py`)

**Variables:**
- `snake_case`; module-level constants `UPPER_SNAKE` (`REVIT_HOST`, `BASE_URL` in `main.py`)
- Private module constants `_UPPER_SNAKE` — `_FRIENDLY`, `_DEFAULT_CATEGORIES` (`revit_mcp/clash.py`)
- Revit API members keep their .NET PascalCase (`doc.Delete`, `t.Start()`)

**Types:**
- Classes `PascalCase`, private ones underscore-prefixed — `_FailureSwallower` (`revit_mcp/utils.py`)

## Code Style

**Formatting:**
- No formatter config committed (no `.pre-commit-config.yaml`, no `[tool.black]` in `pyproject.toml`)
- De facto: 4-space indent, ~88-100 col soft wrap, double quotes preferred
- Every file starts with an encoding cookie: `# -*- coding: utf-8 -*-` (`tools/`)
  or `# -*- coding: UTF-8 -*-` (`revit_mcp/`). Keep it — IronPython needs it.

**Linting:**
- None configured. Correctness is enforced by review and the smoke tests in `tests/`.

**String formatting:**
- `revit_mcp/`: **always** `"...{}".format(x)` — f-strings break IronPython
- `tools/` and `main.py`: f-strings allowed (`BASE_URL` in `main.py`), `.format()` still common

## Import Organization

**Order (`revit_mcp/` modules, see `revit_mcp/editing.py:6-12`):**
1. Local extension helpers — `from utils import get_element_name, make_element_id, ...`
   (note: flat `utils`, not `revit_mcp.utils` — pyRevit puts the module dir on `sys.path`)
2. pyRevit / Revit API — `from pyrevit import routes, revit, DB`, `from System.Collections.Generic import List`
3. Stdlib — `json`, `logging`, `traceback`

**Order (`tools/` modules):**
1. `from mcp.server.fastmcp import Context`
2. `from .utils import format_response` (relative import — tools is a real package)

**Lazy imports:** `startup.py` and `tools/__init__.py` import submodules *inside*
the register function, not at module top. Keeps import failures isolated per
domain and keeps stdio cold start low (see `tests/test_init_latency.py`).

**Path aliases:** none.

## Error Handling

**Extension side (`revit_mcp/`) — never raise out of a route handler.**
Wrap the whole handler body in `try/except` and return a structured response:

```python
@api.route("/delete_elements/", methods=["POST"])
def delete_elements_handler(doc, request):
    try:
        if not doc:
            return routes.make_response(data={"error": "No active Revit document"}, status=503)
        ...
    except Exception as e:
        logger.error("...: {}".format(str(e)))
        return routes.make_response(data={"error": str(e), "traceback": traceback.format_exc()}, status=500)
```

Status code conventions in use: `400` bad/missing request data, `404` element
not found, `500` unexpected exception, `503` no active document.

**Transactions:** create, `Start()`, then immediately `suppress_warnings(t)`
(`revit_mcp/utils.py`) before any model edit — otherwise a Revit modal dialog
hangs the headless Routes server forever. Pattern at `revit_mcp/editing.py:55-58`.

**ID handling:** never touch `ElementId.Value` / `.IntegerValue` directly. Use
`get_element_id_value()` and `make_element_id()` from `revit_mcp/utils.py` —
they span Revit 2024-2027 API differences and raise `ValueError` on bad input.

**Strings:** run any Revit-sourced name through `sanitize_string()` /
`get_element_name()` (`revit_mcp/utils.py`) before putting it in JSON.

**Best-effort helpers:** helpers that must not break callers swallow exceptions
silently (`suppress_warnings`, `normalize_string`). Use sparingly and document why.

**Server side (`main.py`) — errors become strings, not exceptions.**
`_revit_call` returns `f"Error: {status} - {text}"` or `f"Error: {e}"`. Tools
never see an exception from the transport.

**Presentation:** all tool returns go through `format_response()`
(`tools/utils.py`). A dict is an error only if it has a truthy `error` key or a
status in `error/failed/failure/exception`; every other dict is data. Do not
add new implicit error signals — this exact rule was a fixed bug (commit `c1231f6`).

## Logging

**Framework:** stdlib `logging`. Every module declares
`logger = logging.getLogger(__name__)` right after imports.

**Patterns:**
- `logger.error("Message: {}".format(str(e)))` inside except blocks
- `logger.info("<Domain> routes registered successfully")` at the end of each
  `register_*_routes` function
- **Never `print()` in `main.py` under stdio transport** — it corrupts the
  protocol stream. The one existing `print` is guarded to `--combined` mode.

**MCP context logging (`tools/`):** `await ctx.info(...)` for progress and
`await ctx.error(...)` for failures, guarded by `if ctx:`
(`tools/code_execution_tools.py:86`, `tools/colors_tools.py:48`).

## Comments

**When to Comment:**
- Explain *why*, especially non-obvious Revit/IronPython constraints. Strong
  examples: the failure-swallowing rationale in `revit_mcp/utils.py`, the
  slow-filter note in `revit_mcp/clash.py:1-16`, the keep-alive client rationale
  in `main.py:26-30`.
- Record measurements and their thresholds inline (`tests/test_init_latency.py`).

**Docstrings:**
- Module docstring on every file describing the domain
- Docstring on every route handler and every `@mcp.tool()` function
- Tool docstrings are the LLM-facing API contract: purpose, behavior/scope
  rules, return shape, known limitations, then an `Args:` block naming every
  parameter including `ctx`. See `check_clashes` in `tools/clash_tools.py` as
  the reference example. Write these for a model, not a developer.

## Function Design

**Size:** route handlers run long (50-150 lines) because validate → transact →
serialize lives together. Extract to module-private `_helpers` when branching
logic (category resolution, geometry math) grows.

**Parameters:**
- Route handlers take pyRevit's injected `(doc, request)`
- Tool functions use keyword args with defaults and `ctx: Context = None` **last**
- Registration functions take the injected `revit_get` / `revit_post` /
  `revit_image` callables — modules never import the transport directly.
  Unused injected params are acknowledged: `_ = revit_image` (`tools/clash_tools.py:9`)

**Return Values:**
- Route handlers: always `routes.make_response(data=..., status=...)`
- Tool functions: always `-> str`, always the result of `format_response(response)`

**Type hints:** used in `tools/` and `main.py` (`list[str]`, `Union[Dict, str]`).
Absent in `revit_mcp/` by necessity.

## Module Design

**Exports:** implicit; each module's contract is its single
`register_*_routes` / `register_*_tools` function.

**Barrel files:** `tools/__init__.py` is the one barrel — it imports and calls
every `register_*_tools`. `startup.py` is its mirror for routes. Adding a
domain means editing both, in the same order as the existing entries.

---

*Convention analysis: 2026-09-04*
