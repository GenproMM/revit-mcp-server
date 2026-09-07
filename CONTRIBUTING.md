# Contributing

Read this before your first change. Almost nothing here is enforced by tooling —
there is no linter and no CI — so the conventions are the review.

## The two-runtime rule (read this first)

This repository holds **two Python codebases that never share an interpreter.**
They talk over local HTTP. Mixing their idioms is the most common way to break things.

| Side | Files | Runtime | Dialect |
|---|---|---|---|
| MCP server | `main.py`, `tools/`, `tests/` | CPython ≥3.11 | `async`/`await`, f-strings, `list[str]`, type hints |
| Revit extension | `startup.py`, `revit_mcp/` | IronPython 2.7 inside Revit | Python 2 only: `"{}".format(x)`, **no** f-strings, no `async`, no `pathlib`, no modern typing |

Both halves keep an encoding cookie on line 1 — `# -*- coding: utf-8 -*-` in `tools/`,
`# -*- coding: UTF-8 -*-` in `revit_mcp/`. IronPython needs it.

`revit_mcp/utils.py` and `tools/utils.py` are **unrelated files that happen to share a
name.** Route modules import helpers as bare `from utils import ...`, not
`from .utils import ...`, because pyRevit puts the module directory on `sys.path`.

## Adding a capability: two files

Registration is by convention. There is no list to append to — discovery finds your
module, so a forgotten registration line is no longer possible.

**1. `revit_mcp/<domain>.py`** — the Revit half.

```python
# -*- coding: UTF-8 -*-
"""What this domain does."""

from utils import get_element_name, get_element_id_value, suppress_warnings
from pyrevit import routes, DB
import json
import logging

logger = logging.getLogger(__name__)

MM_TO_FEET = 1.0 / 304.8


def register_<domain>_routes(api):
    """Register <domain> routes with the API."""

    @api.route("/<name>/", methods=["POST"])
    def <name>_handler(doc, request):
        """Docstring for a developer. State the expected payload."""
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document"}, status=503
                )
            ...
            return routes.make_response(data={"status": "success", ...})
        except Exception as e:
            logger.error("<name> failed: {}".format(str(e)))
            return routes.make_response(data={"error": str(e)}, status=500)

    logger.info("<Domain> routes registered successfully")
```

**2. `tools/<domain>_tools.py`** — the MCP half.

```python
# -*- coding: utf-8 -*-
"""What this domain does."""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_<domain>_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register <domain> tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def <tool_name>(arg: str, ctx: Context = None) -> str:
        """..."""
        response = await revit_post("/<name>/", {"arg": arg}, ctx)
        return format_response(response)
```

Then **update `tests/unit/tool_manifest.txt`** in the same commit. It is the guard that
turns a silently dropped tool into a failing test and a blocked release.

### How discovery finds your module

- Any `revit_mcp/*.py` exposing a `register_*_routes` callable is registered.
- Any `tools/*.py` (or package) exposing a `register_*_tools` callable is registered.
- Leading-underscore files are never scanned.
- A module with no registrar is treated as a helper and **reported**, so a misspelled
  registrar name shows up rather than vanishing.
- Order is alphabetical and must stay insignificant: **never import one `revit_mcp/`
  domain from another.** A test enforces this.
- Registration failures are isolated per domain. One broken module no longer takes the
  whole extension down — but it is not silent either: `/status/` reports
  `"health": "degraded"` and names the failed domains.

## Non-negotiable invariants

- **Every document mutation runs in a transaction, and `suppress_warnings(t)` comes
  immediately after `t.Start()`.** Without it a routine Revit warning opens a modal
  dialog that blocks the headless Routes server *forever* — every later request times
  out until a human clicks it. Pattern: `revit_mcp/editing.py`. The one exception:
  `Save`/`SaveAs` run **outside** any transaction.
- **Read-only routes open no transaction at all.**
- **Never touch `ElementId.Value` / `.IntegerValue` or call `DB.ElementId(int)`.** Use
  `get_element_id_value()` and `make_element_id()` from `revit_mcp/utils.py`. A bare
  `DB.ElementId(<int>)` fails on Revit 2027 with "Multiple targets could match".
- **Route handlers never raise.** Wrap the whole body in `try/except` and return
  `routes.make_response(...)`. Status codes: `400` bad payload, `404` not found,
  `500` unexpected, `503` no active document.
- **Tool functions always return `str`, via `format_response(response)`.** A bridge
  result may be `dict` **or** a `"Error: …"` `str` — never index one directly.
- **A dict is an error only if it has a truthy `error` key or a status in
  `error/failed/failure/exception`.** Every other dict is data. Do not add new implicit
  error signals to `format_response` — that was a real shipped bug (`c1231f6`) that hid
  valid data behind an error banner. `tests/unit/test_format_response.py` guards it.
- **Never `print()` in `main.py` under stdio transport** — it corrupts the protocol
  stream. Log to `logging` (which goes to stderr); tool progress uses
  `await ctx.info(...)` guarded by `if ctx:`.
- **All tool-facing dimensions are millimetres.** Routes convert with
  `MM_TO_FEET = 1.0 / 304.8`.
- **Revit-sourced names go through `sanitize_string()` / `get_element_name()`.** These
  preserve non-ASCII text — Cyrillic names must survive. A fork regression once folded
  every Russian name to `?????`; `tests/unit/test_textutils.py` guards against its
  return.
- **Batch operations report what they skipped.** Catching a per-element exception,
  `continue`, and still returning `"status": "success"` hides real failures.

## Tool docstrings are the API contract

A `@mcp.tool()` docstring is generated into the schema the model sees. There is no other
API description — write it for a model, not a developer:

1. One line of purpose, with a domain example.
2. Scope rules — how the tool behaves for each combination of input.
3. Accepted value formats, with concrete examples (`["beams", "OST_StructuralColumns"]`,
   not "a list of categories").
4. Return shape, **with units**.
5. Known limitations, stated outright. The model cannot infer them.
6. An `Args:` block naming every parameter, **including `ctx`**.

Reference example: `check_clashes` in `tools/clash_tools.py`. Change the docstring in
the **same commit** as the behaviour — a description that no longer matches produces
wrong calls, because the model reads it and believes it.

### Tool budget

There are already 51 tools. Every one competes for the model's attention when it picks
a tool. Before adding a domain, justify why it is not a parameter on an existing tool.

## Testing

```bash
uv run pytest tests/unit          # Revit-free; must pass before every commit
uv run python tests/test_init_latency.py   # cold-start gate (<2.0 s)
```

`tests/unit/` must never need Revit, pyRevit or the network. The two standalone scripts
in `tests/` are a separate tier driven by hand;
`tests/test_model_info_format.py` needs live Revit with an open document.

`revit_mcp/` cannot be imported under CPython (it needs pyRevit), so logic that deserves
unit tests belongs on the CPython side or in a pure helper like `revit_mcp/textutils.py`.
**Prefer putting new domain logic in `tools/`** and keeping the Revit half a thin data
provider — that is the only way it can be tested without a Revit restart.

## Working on the Revit half

- `%APPDATA%\pyRevit\Extensions\revit-mcp-server.extension` is typically a **directory
  junction to this repo**, so your edits are the deployed extension — no copy step, and
  no staging buffer.
- **After editing anything under `revit_mcp/`, fully close and reopen Revit.** pyRevit's
  Reload button is not enough: reload-then-request has been observed to crash the whole
  Revit process.
- To exercise a route's logic without restarting Revit, POST the route file's own text
  to `/execute_code/`, `exec` it in a throwaway namespace with a fake `api` object that
  captures the handler, then call the handler with `doc`. Prepend `revit_mcp/` to
  `sys.path` and strip `\r\n` — IronPython's `exec` rejects CRLF source.
- Verify the extension loaded: `http://localhost:48884/revit_mcp/status/` in a browser.
  Add `?verbose=true` to list the registered domains.

## Commits

- Branches: `feature/<topic>`.
- Conventional prefixes where they fit: `fix(server):`, `feat(deploy):`, `perf(server):`,
  `docs:`.
- **Write a real body: symptom → cause → fix.** This is load-bearing here — the
  project's debugging knowledge base was reconstructed from commit bodies.
- Record AI co-authorship with a `Co-Authored-By` trailer.

This repository is a fork with a live `upstream` remote. When syncing, **read the diffs,
not the commit messages** — the Cyrillic regression arrived in a commit titled "Add
multi-version Revit support".

## Where to read next

- `CLAUDE.md` — the short version of everything above.
- `.planning/codebase/CONVENTIONS.md` — naming, style, imports, error handling in full.
- `.planning/codebase/CONCERNS.md` — known debt, bugs and fragile areas. Read before
  proposing a refactor; it is probably already listed.
- `deploy/README.md` — how this reaches a workstation, and what will bite you.
