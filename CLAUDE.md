# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## The Two-Runtime Rule (read this first)

This repo contains **two separate Python codebases that never share an interpreter**. They
communicate over local HTTP. Mixing their idioms is the single most common way to break things.

| Side | Files | Runtime | Rules |
|------|-------|---------|-------|
| MCP server | `main.py`, `tools/`, `tests/` | CPython ≥3.11 (dev pin 3.13) | async/await, f-strings, `list[str]`, type hints |
| Revit extension | `startup.py`, `revit_mcp/` | IronPython 2.7 inside pyRevit/Revit | Python 2 dialect only: `"{}".format(x)`, **no** f-strings, no `async`, no `pathlib`, no modern typing |

Both halves keep an encoding cookie on line 1 (`# -*- coding: utf-8 -*-` / `UTF-8`) — IronPython needs it.

`revit_mcp/utils.py` and `tools/utils.py` are **unrelated files that happen to share a name**.
Route modules import helpers as bare `from utils import ...` (not `from .utils import ...`) because
pyRevit puts the module directory on `sys.path` — which also means `revit_mcp/` modules cannot be
imported under CPython at all.

## Commands

```bash
uv sync                              # install (uv.lock is the source of truth; requirements.txt is a stale mirror)
uv run main.py                       # stdio transport (Claude Desktop / Claude Code)
uv run main.py --streamable-http     # HTTP at http://localhost:8000/mcp
uv run main.py --sse                 # SSE at /sse, /messages/
uv run main.py --combined            # both HTTP + SSE under one uvicorn
mcp dev main.py                      # MCP Inspector at http://127.0.0.1:6274

python tests/test_init_latency.py       # cold-start gate (<2.0s); runs anywhere
python tests/test_model_info_format.py  # needs live Revit + pyRevit Routes on :48884
```

There is no pytest, no runner, no lint/format config, and no CI. Tests are standalone
`asyncio.run` scripts run one at a time; they print an uppercase sentinel (`MODEL_INFO_OK`,
`INIT_LATENCY_S=…`) on pass. To add one, copy the stdio-client skeleton from an existing
test, keep the absolute-`main.py`-path idiom, and note in a comment whether it needs live Revit.

Verifying the Revit side requires Revit open with a document, pyRevit installed, and
Routes Server enabled — check `http://localhost:48884/revit_mcp/status/` in a browser.

## Architecture

```
MCP client ──stdio/SSE/HTTP──> main.py + tools/ ──HTTP :48884──> startup.py + revit_mcp/ ──> Revit API
             (CPython, async)                    (IronPython, sync, in Revit process)
```

`main.py` builds the `FastMCP` server, owns the one pooled `httpx.AsyncClient`, and exposes
`revit_get` / `revit_post` / `revit_image`. Those three callables are **injected** into every
tool registrar — tool modules never import the transport.

Strict 1:1 mirroring by domain: `revit_mcp/clash.py` ⇄ `tools/clash_tools.py`. Each side has one
registration entry point (`register_<domain>_routes(api)` / `register_<domain>_tools(mcp, revit_get, revit_post, revit_image=None)`)
called from a hand-maintained barrel (`startup.py` / `tools/__init__.py`). Imports live *inside*
those register functions, not at module top — this isolates per-domain import failures and keeps
stdio cold start low.

**Adding a capability means editing 4 places, in the same order as existing entries.** A missing
line in either barrel silently drops the capability with no error:

1. `revit_mcp/<domain>.py` — `@api.route("/<name>/", methods=[...])` handler taking pyRevit's injected `(doc, request)`
2. `startup.py` — import + `register_<domain>_routes(api)`
3. `tools/<domain>_tools.py` — `@mcp.tool()` async function, `ctx: Context = None` **last**
4. `tools/__init__.py` — import + `register_<domain>_tools(...)`

Current surface: 49 MCP tools over 48 routes across 22 domain modules.

## Non-negotiable invariants

**Every document mutation runs in a transaction, and `suppress_warnings(t)` comes immediately
after `t.Start()`.** Without it a routine Revit warning pops a modal dialog that blocks the
headless Routes server *forever* — every later request times out until a human clicks it.
Pattern: `revit_mcp/editing.py:55-58`. The one exception: `Save`/`SaveAs` must run **outside**
any transaction (`revit_mcp/document.py`).

**Never touch `ElementId.Value` / `.IntegerValue` or call `DB.ElementId(int)` directly.** Use
`get_element_id_value()` and `make_element_id()` from `revit_mcp/utils.py` — they span the
Revit 2024–2027 API differences via try/except chains. Bare `DB.ElementId(<int>)` fails on
2027 with "Multiple targets could match". These are the highest-leverage untested functions
in the repo.

**A parameter is "shared" only if its `InternalDefinition.GetTypeId()` ForgeTypeId starts with
`revit.local.shared`** (vs `revit.local.project` for a plain project parameter). Never test for
`DB.ExternalDefinition`: `doc.ParameterBindings` always yields `InternalDefinition`, because a
shared parameter acquires an internal definition the moment it loads into a project — so that
test reports "not shared" for every parameter, `ADSK_*` included. Helpers:
`_classify_definition()` in `revit_mcp/parameters.py`.

**Route handlers never raise.** Wrap the whole body in `try/except` and return
`routes.make_response(data=..., status=...)`. Status conventions: `400` bad/missing payload,
`404` element not found, `500` unexpected exception, `503` no active document.

**A dict is an error only if it has a truthy `error` key or a status in
`error/failed/failure/exception`.** Every other dict is data. Do not add new implicit error
signals to `format_response` (`tools/utils.py`) — treating status-less dicts as failures was a
real shipped bug (commit `c1231f6`) that hid valid data behind an `=== ERROR DETAILS ===` banner;
`tests/test_model_info_format.py` guards against its return.

**Tool functions always return `str`, always via `format_response(response)`.** The transport
coerces exceptions to `"Error: …"` strings, so a bridge result may be `dict` or `str` — never
index one directly.

**Never `print()` in `main.py` under stdio transport** — it corrupts the protocol stream. The
one existing `print` is guarded to `--combined` mode. Revit-side logging goes through
`logger = logging.getLogger(__name__)`; tool-side progress uses `await ctx.info(...)` guarded by `if ctx:`.

**All tool-facing dimensions are millimeters.** Routes convert to Revit's internal feet
(`MM_TO_FEET = 1.0 / 304.8`). Any Revit-sourced name goes through `sanitize_string()` /
`get_element_name()` before landing in JSON — these guard against `None`/type edge cases
but preserve non-ASCII text (e.g. Cyrillic element/view names); pyRevit's routes JSON
serializer escapes it as `\uXXXX`, so it round-trips to the client intact.

## Tool docstrings are the API contract

A `@mcp.tool()` docstring is what the model sees, so write it for a model, not a developer:
purpose, scope rules, return shape, known limitations, then an `Args:` block naming every
parameter including `ctx`. `check_clashes` in `tools/clash_tools.py` is the reference example.

## Known sharp edges

- Port `48884` is hardcoded; only the host is configurable (`REVIT_HOST`, defaults to `localhost`).
- `_revit_call` uses one 30s timeout for everything — a clash check shares a status ping's budget.
- Bulk routes catch per-element exceptions, `continue`, and still report `"status": "success"`; the count is the only hint that elements were skipped.
- `/execute_code/` is unauthenticated arbitrary IronPython with full `doc`/`DB`/`clr`/`System` access. It is the de-facto fallback for missing tools — prefer promoting a snippet into a typed route.
- `revit_mcp/colors.py` is 1246 lines (twice the next largest). Split by route before adding to it.
- `except Exception: pass` appears 60+ times in `revit_mcp/`; when touching one, narrow it and log at warning level.
- After editing anything under `revit_mcp/` (the IronPython/Routes side), pyRevit's **Reload**
  button is not enough to safely pick up the change — reload-then-request has been observed to
  crash the whole Revit process. Fully close and reopen Revit (which restarts the Routes server
  cleanly) before testing route changes live.
- `%APPDATA%\pyRevit\Extensions\revit-mcp-server.extension` is a **directory junction to this
  repo**, so edits here are the deployed extension — no copy step, but also no staging buffer.
  To exercise a new route's logic without restarting Revit, POST the route file's own text to
  `/execute_code/`, `exec` it in a throwaway namespace with a fake `api` object that captures the
  handler, then call the handler with `doc`. Prepend `revit_mcp/` to `sys.path` (its modules
  import `from utils import …`) and strip `\r\n` — IronPython's `exec` rejects CRLF source.

## Reference documents

- `.planning/codebase/` — detailed maps: `ARCHITECTURE.md`, `CONVENTIONS.md`, `TESTING.md`, `STACK.md`, `STRUCTURE.md`, `INTEGRATIONS.md`, `CONCERNS.md`
- `README.md` — user setup, pyRevit install, full tool catalogue
- `LLM.txt` — long-form background; note its directory layout predates the current flat layout

## Obsidian Knowledge Vault
Хранилище знаний: .\rvt-mcp_Obsidian
### При старте сессии
Прочитай 00-home/index.md и текущие приоритеты.md.
Если задача касается модуля — прочитай заметку из knowledge/.
### При завершении (пользователь: "сохрани сессию")
1. Создай заметку в sessions/ с датой
2. Обнови текущие приоритеты.md
3. Если решение — создай в knowledge/decisions/
4. Если баг — создай в knowledge/debugging/
5. Обнови index.md если новые заметки
6. Если в текущей сессии были изменены файлы — создай коммит только из файлов, затронутых в этой сессии (тех, которые ты создал или редактировал через Write/Edit). Изменения из предыдущих сессий не включать. Каждая сессия — отдельный коммит. 
Шаблон:
сессия: <краткое описание работы за сессию в одном предложении>

## Информация о сессии
- Модель: <текущая LLM модель, например claude-sonnet-4-6>
- Дата: <дата последних изменений в формате YYYY-MM-DD>
- Изменено файлов: <N>

## Изменённые файлы
- <список файлов из git status>

## Результаты
- <что было сделано, список ключевых изменений>

Если изменений нет — коммит не создавать.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
