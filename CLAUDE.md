# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## The Two-Runtime Rule (read this first)

This repo contains **two separate Python codebases that never share an interpreter**. They
communicate over local HTTP. Mixing their idioms is the single most common way to break things.

| Side | Files | Runtime | Rules |
|------|-------|---------|-------|
| MCP server | `main.py`, `tools/`, `tests/` | CPython ≥3.11 (dev pin 3.13) | async/await, f-strings, `list[str]`, type hints |
| Revit extension | `startup.py`, `revit_mcp/` | IronPython **3** inside pyRevit/Revit | `"{}".format(x)`, **no** f-strings, no `async`, no `pathlib`, no modern typing |

The Revit half ran under IronPython 2.7 until 2026-09-07; pyRevit now attaches
IronPython 3 (engine `IPY342`), and the fleet is standardised on it. Write for the
**intersection** of the two, not for Python 3: IronPython 3.4 sits at the Python 3.4
language level, so f-strings (3.6+) are still a `SyntaxError` at extension load, and
`scripts/conventions.py` still rejects them. What actually changed is import
semantics — see below.

Both halves keep an encoding cookie on line 1 (`# -*- coding: utf-8 -*-` / `UTF-8`) — IronPython needs it.

`revit_mcp/utils.py` and `tools/utils.py` are **unrelated files that happen to share a name**.

Route modules import package siblings **relatively**: `from .utils import ...`, never
`from utils import ...`. A flat import of a sibling is an implicit relative import, which
Python 3 removed — under IronPython 3 it raises `ImportError` at load, the domain is
skipped, its tools never appear, and `/status/` answers `Route does not exist` from
pyRevit's own routes server rather than ours. On 2026-09-07 this took out 22 of 23 domains
on the first pilot machine while the extension itself reported a clean load.

Keep the form consistent, not merely working: pyRevit also puts the module directory on
`sys.path`, so mixing the two forms loads `utils.py` twice under two identities with
separate state. `tests/unit/test_conventions.py` enforces this.

## Commands

```bash
uv sync                              # install (uv.lock is the source of truth; requirements.txt is a stale mirror)
uv run main.py                       # stdio transport (Claude Desktop / Claude Code)
uv run main.py --streamable-http     # HTTP at http://localhost:8000/mcp
uv run main.py --sse                 # SSE at /sse, /messages/
uv run main.py --combined            # both HTTP + SSE under one uvicorn
mcp dev main.py                      # MCP Inspector at http://127.0.0.1:6274

uv sync --group dev                     # adds pytest (dev-only; never ships in the payload)
uv run pytest tests/unit                # Revit-free suite; run before every commit
python tests/test_init_latency.py       # cold-start gate (<2.0s); runs anywhere
python tests/test_model_info_format.py  # needs live Revit + pyRevit Routes on :48884
```

Two test tiers. `tests/unit/` is a pytest suite that must never need Revit, pyRevit or the
network — run it before every commit (`uv run pytest tests/unit`). The two scripts directly
in `tests/` are the older tier: standalone `asyncio.run` programs run one at a time that
print an uppercase sentinel (`MODEL_INFO_OK`, `INIT_LATENCY_S=…`) on pass; they are excluded
from pytest collection because they execute at import. To add one, copy the stdio-client
skeleton from an existing test, keep the absolute-`main.py`-path idiom, and note in a comment
whether it needs live Revit.

There is no lint/format config and no CI. `revit_mcp/` cannot be imported under CPython (it
needs pyRevit), so **new domain logic belongs on the CPython side where it can be tested**;
keep the Revit half a thin data provider. Pure helpers that both halves need go in
`revit_mcp/textutils.py`, which imports nothing from pyRevit and is unit tested.

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

Mirroring by domain: `revit_mcp/clash.py` ⇄ `tools/clash_tools.py`. Each side has one
registration entry point (`register_<domain>_routes(api)` / `register_<domain>_tools(mcp, revit_get, revit_post, revit_image=None)`).
The mirroring is a convention, not a law — `tools/process_tools.py` has no Revit half (it runs
when Revit is closed) and `tools/family_tools.py` maps onto `revit_mcp/placement.py`.

**Registration is by convention — there is no barrel to edit.** `startup.py` and
`tools/__init__.py` discover every module exposing a `register_*_routes` /
`register_*_tools` callable. **Adding a capability is 2 files plus the manifest:**

1. `revit_mcp/<domain>.py` — `@api.route("/<name>/", methods=[...])` handler taking pyRevit's injected `(doc, request)`
2. `tools/<domain>_tools.py` — `@mcp.tool()` async function, `ctx: Context = None` **last**
3. `tests/unit/tool_manifest.txt` — add the tool name, same commit

Discovery rules that matter when writing a module:

- Order is alphabetical and **must stay insignificant — never import one `revit_mcp/` domain
  from another.** `tests/unit/test_registration.py` enforces this.
- A module exposing no registrar is treated as a helper and *reported*, so a misspelled
  registrar name surfaces instead of vanishing.
- Failures are isolated per domain: one broken module no longer kills the extension, but it
  is not silent — `/status/` returns `"health": "degraded"` and names the failed domains
  (`?verbose=true` also lists the registered ones).
- Imports still live *inside* the register functions, which keeps stdio cold start low.

Current surface: 54 MCP tools over 51 routes across 23 domain modules. The authoritative
list is `tests/unit/tool_manifest.txt`; `deploy/gate.py` blocks a release that diverges from it.

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

**A POST body is declared `text/plain` and parsed with `parse_request_data()`.** pyRevit
parses an `application/json` body itself, before dispatch, and that parse is broken under
IronPython 3: `routes/server/server.py` hands the raw bytes from `rfile.read()` to a
3.5-level `json.loads`, which answers `TypeError: the JSON object must be str, not 'bytes'`.
Every POST route then returns 500 with nothing reaching Revit. The extension cannot patch
it — the routes server runs in its own IronPython engine with its own module table, so a
patch installed from `startup.py` lands on a different copy of that module (measured live,
2026-09-07). So `main.py` sends `Content-Type: text/plain; charset=utf-8` and handlers call
`parse_request_data(request.data)` (`revit_mcp/textutils.py`), which takes bytes, str or
dict. Never hand-roll the parse: `scripts/conventions.py` and `tests/unit/` reject
`json.loads(request.data)`, and any client that still sends `application/json` — curl
included — hits pyRevit's broken parse rather than the route.

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
  handler, then call the handler with `doc`. Strip `\r\n` — IronPython's `exec` rejects CRLF
  source. Since the modules now use `from .utils import …`, `exec` them with a package context
  (`__package__ = "revit_mcp"` in the namespace, after `import revit_mcp`) rather than by
  prepending `revit_mcp/` to `sys.path`, which no longer resolves a relative import.

- **Never detect the runtime by asking whether a Python 2 builtin exists.** pyRevit defines
  `unicode` in its IronPython 3 engine as an alias of `str`, so `try: unicode / except
  NameError` reports Python 2 on a Python 3 runtime. `textutils.py` did exactly that until
  2026-09-08: both type aliases collapsed onto `str`, no real `bytes` matched, and every POST
  route answered 500 (`'bytes' object has no attribute 'get'`) while the CPython unit suite
  stayed green, because CPython has no `unicode` and so took the correct branch. Use
  `if bytes is str:` — true only on Python 2. `scripts/conventions.py` accepts either guard
  and prefers this one.
- Two Revit instances can **both** bind `127.0.0.1:48884` — pyRevit's routes server sets no
  exclusive-address flag, so nothing fails loudly and requests land on whichever process the
  OS picks. Open a model in one and the other answers `No active Revit document`. Check
  `Get-NetTCPConnection -LocalPort 48884 -State Listen` returns exactly one row before
  trusting any live result; note Revit Accelerator can start a second instance by itself.
- Launching Revit with a workshared model on the command line pops the **workset selection
  dialog**, which blocks the headless routes server forever. Boot Revit with no model and
  open through `/open_model/`, which supplies a `WorksetConfiguration` and so never prompts.
- Requests sent while Revit is still initializing **hang** rather than failing: handlers run
  through a Revit external event that does not pump until startup finishes. Poll `/status/`
  (a GET, which answers 503 promptly) before issuing the first POST.

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
