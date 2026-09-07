# Technology Stack

**Analysis Date:** 2026-09-04

This repository is a **dual-runtime** project. The same repo is both (a) a CPython MCP server run on the host and (b) a pyRevit/IronPython extension loaded inside Revit. The two halves never share an interpreter — they talk over local HTTP.

```
AI Client --stdio/SSE/HTTP--> MCP server (CPython 3.13, `main.py` + `tools/`)
          --HTTP :48884-->    pyRevit Routes (IronPython 2.7, `startup.py` + `revit_mcp/`)
          -->                 Revit API (.NET)
```

## Languages

**Primary:**
- Python 3 (CPython) — MCP server side: `main.py`, `tools/*.py`, `tests/*.py`. Uses modern async/await, `typing`, f-strings.
- Python 2.7 dialect (IronPython, hosted by pyRevit) — Revit side: `startup.py`, `revit_mcp/*.py`. Constrained to py2 syntax: `from StringIO import StringIO` (`revit_mcp/code_execution.py:12`), `"{}".format(...)` instead of f-strings, `# -*- coding: UTF-8 -*-` headers.

**Secondary:**
- .NET / CLR interop via `clr` and `System` inside the Revit half (`revit_mcp/code_execution.py:66-67`, `System.Collections.Generic.List` used across `revit_mcp/`).

## Runtime

**Environment:**
- CPython >= 3.11 required (`pyproject.toml`); pinned to 3.13 for development (`.python-version`).
- IronPython 2.7 supplied by pyRevit inside Revit (not installed by this repo, no manifest for it).
- Windows 10/11 only in practice — Revit is Windows-only.

**Package Manager:**
- `uv` (Astral) — primary; `uv sync` / `uv run main.py` (`README.md`, `README_UV.md`).
- Lockfile: `uv.lock` present (29 resolved packages).
- `requirements.txt` present as a fully pinned mirror for `uv pip install -r requirements.txt`.

## Frameworks

**Core:**
- `mcp[cli]` >= 1.9.0 (pinned 1.9.0 in `requirements.txt`) — MCP protocol; `FastMCP` server constructed in `main.py:12-18`.
- `pyrevit` (`routes`, `DB`, `revit`, `revit.db.query`) — provided by the Revit host, imported in `startup.py:8` and every `revit_mcp/*.py`. Not a PyPI dependency of this project.
- `starlette` 0.46.2 + `uvicorn` 0.34.2 — ASGI stack behind the SSE / streamable-HTTP transports (`main.py:run_combined_async`).
- `httpx` 0.28.1 — async client to the pyRevit Routes server (`main.py:_get_client`).

**Testing:**
- No test framework. `tests/test_init_latency.py` and `tests/test_model_info_format.py` are standalone scripts run directly with the interpreter; they use `assert` and the `mcp` client SDK (`mcp.ClientSession`, `mcp.client.stdio.stdio_client`).

**Build/Dev:**
- `mcp dev main.py` for the MCP Inspector (`README.md`).
- No linter, formatter, or CI configuration in the repo.

## Key Dependencies

**Critical:**
- `mcp` 1.9.0 — tool registration, transports, `Image`/`Context` types. Dominates cold-start cost (~426ms, noted in `tests/test_init_latency.py`).
- `httpx` 1.0.9/0.28.1 — every Revit call goes through the single pooled `AsyncClient` in `main.py:31-40`.
- `anyio` 4.9.0 — used directly for `anyio.run(run_combined_async)` in `main.py`.
- `pydantic` 2.11.4 / `pydantic-core` 2.33.2 — tool schema generation via FastMCP.

**Infrastructure:**
- `uvicorn` 0.34.2 — HTTP server for `--sse`, `--streamable-http`, `--combined` modes.
- `sse-starlette` 2.3.5, `httpx-sse` 0.4.0 — SSE transport.
- `typer` 0.15.4, `rich` 14.0.0, `click` 8.1.8 — pulled in by `mcp[cli]`.
- `python-dotenv` 1.1.0, `pydantic-settings` 2.9.1 — transitive; no `.env` file is used by this codebase.

**Stale entry:**
- `uv.lock` contains a package named `simple-revit-mcp` that does not appear in `pyproject.toml` or `requirements.txt` — likely the lock's own root-project alias or a leftover.

## Configuration

**Environment:**
- `REVIT_HOST` — hostname of the pyRevit Routes server, defaults to `localhost` (`main.py:21`). The only environment variable the server reads.
- `USERPROFILE` / `HOME` — read for a default output directory in `revit_mcp/documentation.py:332`.
- No `.env` file, no config file, no secrets. Nothing is authenticated.

**Hardcoded constants (`main.py`):**
- MCP server bind: `127.0.0.1:8000`, `stateless_http=True`, `json_response=True`.
- Revit Routes port: `48884` (pyRevit default), not overridable by env var.
- Base URL: `http://{REVIT_HOST}:48884/revit_mcp`.
- Timeouts: 30.0s default for GET/POST (`main.py:_revit_call`), 60.0s for image fetches (`main.py:revit_image`).

**Extension manifest:**
- `extension.json` — pyRevit extension descriptor (`type: extension`, `rocket_mode_compatible: True`, no dependencies).

**Build:**
- `pyproject.toml` only; no build backend configured, the project is run from source rather than packaged.

## Platform Requirements

**Development:**
- Windows 10/11, Autodesk Revit 2024 / 2025 / 2026 / 2027 with a document open.
- pyRevit installed with the Routes Server enabled (pyRevit tab > Settings > Routes).
- Multi-version Revit compatibility is handled in code, not by dependency pinning: `get_element_id_value` / `make_element_id` in `revit_mcp/utils.py` try `ElementId.Value` (2024+) then fall back to `IntegerValue`.
- `uv` on PATH.

**Production:**
- Same as development — this is a local developer/designer tool. Both halves run on the engineer's workstation; the MCP server binds to loopback only.

---

*Stack analysis: 2026-09-04*
