# Testing Patterns

**Analysis Date:** 2026-09-04

## Test Framework

**Runner:**
- None. There is no pytest/unittest harness — no `pytest.ini`, no `setup.cfg`,
  no `[tool.pytest.ini_options]` in `pyproject.toml`, no test dependency
  declared (`pyproject.toml` lists only `mcp[cli]>=1.9.0`).
- Tests are **standalone executable scripts** run directly with the interpreter.

**Assertion Library:**
- Bare `assert` statements with an explanatory message.

**Run Commands:**
```bash
python tests/test_model_info_format.py   # end-to-end: stdio tool call returns real data
python tests/test_init_latency.py        # perf gate: cold start under 2.0s
mcp dev main.py                          # manual: MCP Inspector at http://127.0.0.1:6274
```

There is no aggregate "run all" command and no CI workflow (`.github/` absent).
Run each script individually.

## Test File Organization

**Location:**
- Flat `tests/` directory at the repo root, separate from source.

**Naming:**
- `test_<subject>.py` — `tests/test_model_info_format.py`, `tests/test_init_latency.py`

**Structure:**
```
tests/
├── test_init_latency.py      # cold-start latency budget
└── test_model_info_format.py # response formatting regression
```

Only the CPython side (`main.py`, `tools/`) is testable this way. `revit_mcp/`
runs inside Revit's IronPython host and has **no automated tests at all** — it
is exercised only by live calls against a running Revit instance.

## Test Structure

**Suite Organization:** one `async def main()` per file, driven by
`asyncio.run(main())` at module bottom. No classes, no fixtures, no test
functions collected by a runner.

```python
import asyncio, sys, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PY = sys.executable
MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")

async def main():
    async with stdio_client(StdioServerParameters(command=PY, args=[MAIN])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("get_revit_model_info", {})
            txt = " ".join(getattr(c, "text", "") for c in res.content)
            assert "ERROR DETAILS" not in txt, "false error header present:\n" + txt[:300]
            assert "total_elements" in txt, "expected model data missing"
            print("MODEL_INFO_OK")

asyncio.run(main())
```

**Patterns:**
- Setup: spawn the real server as a subprocess over stdio using `sys.executable`
  and an absolute path to `main.py` derived from `__file__` (never CWD-relative).
- Teardown: the nested `async with` blocks tear down the session and subprocess.
- Assertion: substring checks against the flattened text of `res.content`, with
  a truncated slice of the payload in the failure message.
- Success signal: a single uppercase sentinel line printed on pass
  (`MODEL_INFO_OK`, `INIT_LATENCY_S=...`). Exit code 0 means pass.

## Mocking

**Framework:** none. No `unittest.mock`, no `pytest-mock`, no fixtures.

**What to Mock:** nothing currently. Tests hit the real MCP server process.

**What NOT to Mock:**
- The stdio transport and `ClientSession` handshake — the cold-start and
  response-format bugs these tests guard against only reproduce end to end.

**Important consequence:** `tests/test_model_info_format.py` requires a **live
Revit instance with the pyRevit Routes server on `localhost:48884`** and an open
document. Without it, `revit_get` returns a connection error string and the
`total_elements` assertion fails. `tests/test_init_latency.py` has no such
dependency — it only needs the MCP handshake and runs anywhere.

## Fixtures and Factories

**Test Data:** none. Assertions use literal expected substrings.

**Location:** no fixtures directory exists. If test data becomes necessary,
add `tests/fixtures/` and load with `os.path.join(os.path.dirname(__file__), ...)`
to match the existing absolute-path convention.

## Coverage

**Requirements:** none enforced; no coverage tooling installed.

**View Coverage:**
```bash
# Not configured. Would require adding pytest + pytest-cov as dev dependencies.
```

Practical coverage is very low: 2 scripts touching 1 of 48 tools. The
~8,500 lines under `revit_mcp/` are uncovered.

## Test Types

**Unit Tests:** none. Pure-function candidates that would be easy to unit test
without Revit: `format_response` (`tools/utils.py`), `get_element_id_value` /
`make_element_id` / `sanitize_string` (`revit_mcp/utils.py`), `_resolve_bic` /
`_resolve_categories` (`revit_mcp/clash.py`).

**Integration Tests:** both existing scripts. They spawn `main.py` over stdio
and exercise the registration → transport → `format_response` path.

**Performance Tests:** `tests/test_init_latency.py` is a regression gate, not a
benchmark. The 2.0s threshold sits above the measured ~0.9s floor (the cost of
importing `mcp.server.fastmcp` plus `httpx`); the file's inline comment records
that measurement — update the comment alongside the number if it changes.

**E2E / Revit tests:** manual only, via MCP Inspector (`mcp dev main.py`,
README "Testing with MCP Inspector") against a live model.

## Common Patterns

**Async Testing:**
```python
async def main():
    ...
asyncio.run(main())
```

**Error Testing:** by negative substring assertion on formatted output rather
than exception capture — e.g. asserting the `=== ERROR DETAILS ===` banner
emitted by `format_response` is *absent*:

```python
assert "ERROR DETAILS" not in txt, "false error header present:\n" + txt[:300]
```

**Adding a new test:** copy the stdio-client skeleton above, change the
`call_tool` name and arguments, keep the absolute-`MAIN`-path idiom, assert on
substrings of the joined `res.content` text, and print a unique sentinel on
success. State in a comment whether the test needs a live Revit connection.

---

*Testing analysis: 2026-09-04*
