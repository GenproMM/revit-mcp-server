# Codebase Concerns

**Analysis Date:** 2026-09-04

## Tech Debt

**Arbitrary code execution endpoint doubles as the escape hatch for missing tools:**
- Issue: `/execute_code/` accepts raw IronPython and `exec()`s it with full `doc`, `DB`, `revit`, `clr`, `System` and unrestricted `__builtins__`. It is the de-facto fallback whenever a typed tool is absent, so pressure to add proper tools is relieved by the most dangerous path.
- Files: `revit_mcp/code_execution.py:57-80`, `tools/code_execution_tools.py`
- Impact: Every model-mutating capability gap gets solved by shipping untyped code over HTTP; no schema, no validation, no audit trail beyond a log line.
- Fix approach: Keep the endpoint but gate it behind an opt-in env flag (`REVIT_MCP_ALLOW_EXEC`), and promote frequently-executed snippets into typed routes under `revit_mcp/`.

**Two parallel module trees with duplicated registration boilerplate:**
- Issue: Every capability requires a matching pair — an IronPython route module in `revit_mcp/` and a CPython tool wrapper in `tools/` — plus a hand-maintained registration list.
- Files: `startup.py:14-105` (23 sequential import+register blocks), `tools/__init__.py:5-55` (23 imports + 23 register calls)
- Impact: Adding a feature means edits in 4 places; a forgotten line in either list silently drops the capability with no error.
- Fix approach: Replace both hand-written lists with package introspection (`pkgutil.iter_modules`) that discovers `register_*_routes` / `register_*_tools` by convention.

**`from utils import ...` relies on pyRevit's implicit sys.path:**
- Issue: All 20 route modules use a bare top-level `from utils import ...` rather than a package-relative import.
- Files: `revit_mcp/analysis.py:7`, `revit_mcp/annotation.py:7`, `revit_mcp/building.py:8`, and 17 more; target is `revit_mcp/utils.py`
- Impact: Modules are unimportable outside the pyRevit extension loader — they cannot be unit tested, linted with import resolution, or run under CPython. Any other `utils` on the path shadows them.
- Fix approach: Not trivially fixable while IronPython 2.7 hosts them; document the constraint and add a `sys.path` shim in `startup.py` so the intent is explicit.

**`format_response()` reimplements response shaping with heuristics:**
- Issue: A single 100-line function guesses at success/failure and picks an output key by trying `output` → `message` → `result` → `data` → status-special-case → generic key dump.
- Files: `tools/utils.py:5-107`
- Impact: A route returning an unexpected key shape produces either a wrong-looking dump or a false error. This already caused one production bug (fixed in commit `c1231f6`).
- Fix approach: Define one response envelope contract in `revit_mcp/` (`{"ok": bool, "data": ..., "error": ...}`) and make `format_response` a dumb renderer over it.

## Known Bugs

**Silent partial failures inside batch operations:**
- Symptoms: Bulk routes catch per-element exceptions, `continue`, and still return `"status": "success"` — the caller sees a success message while some elements were skipped.
- Files: `revit_mcp/building.py:244`, `revit_mcp/building.py:548`, `revit_mcp/clash.py:213`, `revit_mcp/analysis.py:367-382`
- Trigger: Any element in a batch that throws (deleted id, geometry-less element, locked family).
- Workaround: None — the count in the response is the only hint. Routes should return a `skipped` / `failures` array alongside the successes.

**`suppress_warnings()` swallows its own failure:**
- Symptoms: If configuring failure-handling options throws, the function returns silently and the transaction proceeds *without* modal suppression — the very scenario it exists to prevent.
- Files: `revit_mcp/utils.py:38-46`
- Trigger: Revit API version where `SetFailuresPreprocessor` signature differs (a real risk given the 2024–2027 support matrix).
- Workaround: None. It should at minimum `logger.warning` so a hung Routes server is diagnosable.

**`sys.stdout` restoration is not exception-safe in the outer scope:**
- Symptoms: `sys.stdout` is reassigned to a `StringIO` and restored in both the try and except branches, but not in a `finally`. A failure between assignment and the inner try (or an exception thrown by `t.RollBack()`) leaves global stdout pointing at a closed StringIO for the life of the Revit session.
- Files: `revit_mcp/code_execution.py:64-108`
- Trigger: Rollback failure or an error raised by the `print` lambda construction.
- Workaround: Restart Revit. Fix is a `try/finally`.

## Security Considerations

**Unauthenticated remote code execution over HTTP:**
- Risk: The pyRevit Routes server exposes `/revit_mcp/execute_code/` with no authentication, no token, and no allowlist. Any local process — or any host on the network if pyRevit's Routes server is not bound to loopback — can execute arbitrary .NET/IronPython inside Revit with the user's privileges.
- Files: `revit_mcp/code_execution.py:20-24`, `startup.py:11`
- Current mitigation: The MCP client side defaults to `localhost` (`main.py:22-24`), but that is a client default, not a server-side bind restriction. `REVIT_HOST` is env-overridable to any host.
- Recommendations: Verify/force loopback binding of the Routes server; require a shared secret header on `/execute_code/`; make the endpoint opt-in at extension load.

**No input validation on any route payload:**
- Risk: Routes `json.loads(request.data)` and read keys directly. Element ids, category names, file paths and counts go straight into Revit API calls.
- Files: pattern across `revit_mcp/*.py`; e.g. `revit_mcp/clash.py:146-151`, `revit_mcp/code_execution.py:33-38`
- Current mitigation: Broad `try/except Exception` returns a 500 with `traceback.format_exc()`.
- Recommendations: Never return raw tracebacks over the wire (they leak absolute filesystem paths and extension internals); validate ids and bound list sizes at the route boundary.

**Traceback disclosure in error responses:**
- Risk: `"traceback": traceback.format_exc()` is returned to the client in multiple routes, exposing local paths and library versions.
- Files: `revit_mcp/clash.py:233-237`, `revit_mcp/code_execution.py:150-155`
- Current mitigation: None.
- Recommendations: Log the traceback, return only a correlation id plus a short message.

## Performance Bottlenecks

**Clash detection is one collector query per element in set A:**
- Problem: For each element in set A a fresh `FilteredElementCollector` runs an `ElementIntersectsElementFilter` (a slow filter) over the whole document.
- Files: `revit_mcp/clash.py:174-207`
- Cause: O(|A|) slow-filter passes; on a real model set A can be thousands of elements, each triggering full geometry intersection work.
- Improvement path: Pre-filter set B by bounding-box (`BoundingBoxIntersectsFilter`) before applying the slow intersection filter, and cap set A size with an explicit `max_elements` parameter rather than only capping results.

**No pagination or result caps on collector-based read routes:**
- Problem: Read routes materialise full collector results with `list(...)` and serialise everything.
- Files: `revit_mcp/clash.py:167-172`, `revit_mcp/model_info.py`, `revit_mcp/analysis.py`
- Cause: Whole-model traversal with per-element string sanitisation (`sanitize_string` does an encode/decode round-trip per name).
- Improvement path: Add `limit`/`offset` to read routes; responses that exceed a token budget are useless to the MCP client anyway.

**Hardcoded 30s default timeout regardless of operation cost:**
- Problem: `_revit_call` defaults to `timeout=30.0` for all calls; only `tools/status_tools.py:14` overrides it.
- Files: `main.py:66-84`, `tools/status_tools.py:14`
- Cause: Long operations (clash check, full model info, exports) share the same budget as a status ping.
- Improvement path: Per-tool timeouts set at the wrapper level, with generous values for known-slow endpoints.

## Fragile Areas

**Revit version compatibility shims:**
- Files: `revit_mcp/utils.py:70-130` (`get_element_id_value`, `make_element_id`)
- Why fragile: Compatibility across Revit 2024/2025/2026/2027 rests on try/except chains — `eid.Value` then `eid.IntegerValue`; `DB.ElementId(System.Int64(x))` then `DB.ElementId(int)`. Revit 2027 specifically breaks bare `DB.ElementId(<int>)` with "Multiple targets could match" (documented at `revit_mcp/code_execution.py:59-63`).
- Safe modification: Never construct `DB.ElementId` or read an id directly; always route through these two helpers. New code doing `element.Id.IntegerValue` will break on 2027.
- Test coverage: None. These are the highest-leverage untested functions in the repo.

**`revit_mcp/colors.py` at 1246 lines:**
- Files: `revit_mcp/colors.py`
- Why fragile: Largest module by a factor of 2 (next is `building.py` at 662), holds multiple route handlers plus override/graphics helpers in one namespace with 6+ bare `except Exception` blocks.
- Safe modification: Split by route before adding to it; changes today require reading the whole file to know what shares state.
- Test coverage: None.

**Broad `except Exception` used as control flow:**
- Files: 60+ occurrences across `revit_mcp/`; densest in `revit_mcp/analysis.py` (22), `revit_mcp/building.py` (13), `revit_mcp/colors.py` (7)
- Why fragile: Many are bare `except Exception: pass` or `continue`, so genuine defects (typos, API signature changes after a Revit upgrade) are indistinguishable from expected per-element misses.
- Safe modification: When touching one of these, narrow it to the specific Revit exception and log at warning level.
- Test coverage: None.

## Scaling Limits

**Single Revit document, single Revit instance:**
- Current capacity: One `revit.doc` per Routes server; the document is injected by pyRevit into every handler.
- Limit: No multi-document, no multi-Revit-instance addressing. Two open Revit sessions cannot both be driven — the Routes port `48884` is hardcoded (`main.py:23`).
- Scaling path: Make the port env-configurable like `REVIT_HOST` already is, and add a document selector parameter to routes that need it.

**Transactions are serialised through the Revit UI thread:**
- Current capacity: One mutating operation at a time; the MCP side allows up to 20 concurrent HTTP connections (`main.py:35-38`).
- Limit: Concurrent tool calls queue behind Revit's API context; a modal dialog (if `suppress_warnings` fails) blocks all of them indefinitely.
- Scaling path: Serialise mutating calls client-side rather than relying on the connection pool.

## Dependencies at Risk

**IronPython 2.7 (implicit, via pyRevit):**
- Risk: `revit_mcp/` is Python 2 (`from StringIO import StringIO`, `.format()`-only strings, no type hints) while `tools/` and `main.py` are Python 3.11+ (`pyproject.toml` sets `requires-python = ">=3.11"`).
- Impact: The two halves can never share code; helpers are duplicated (`revit_mcp/utils.py` vs `tools/utils.py` are unrelated files with the same name). pyRevit's CPython path would be a migration, not an upgrade.
- Migration plan: None available short-term; keep the boundary explicit and never import across it.

**`mcp==1.9.0` pinned exactly:**
- Risk: `requirements.txt` pins all 28 transitive deps exactly while `pyproject.toml` declares `mcp[cli]>=1.9.0`. The two files disagree on intent.
- Impact: `uv sync` (from `pyproject.toml` + `uv.lock`) and `pip install -r requirements.txt` can produce different environments.
- Migration plan: Delete `requirements.txt` and make `uv.lock` the single source of truth, or regenerate it from the lock.

## Missing Critical Features

**No server-side configuration surface:**
- Problem: Only `REVIT_HOST` is configurable. Port `48884`, MCP host `127.0.0.1`, MCP port `8000`, and all timeouts are hardcoded.
- Blocks: Running two servers side by side; non-default pyRevit Routes configurations.
- Files: `main.py:12-24`

**No structured logging or request correlation:**
- Problem: `logging.getLogger(__name__)` with plain `.format()` messages; nothing ties an MCP tool call to the Routes request it produced.
- Blocks: Diagnosing a hung or slow operation across the two processes.
- Files: every module in `revit_mcp/`

**No linting or formatting configuration:**
- Problem: No `.ruff.toml`, `setup.cfg`, `.flake8`, or pre-commit config exists. Style drifts between the Python 2 and Python 3 halves and within `revit_mcp/` (mixed `# -*- coding: utf-8 -*-` vs `UTF-8`, inconsistent blank-line usage).
- Blocks: Automated quality gates; the dual-runtime split means one linter config cannot cover both trees anyway.

## Test Coverage Gaps

**All 20 IronPython route modules — zero tests:**
- What's not tested: Every route handler in `revit_mcp/`, including all transaction-mutating operations.
- Files: `revit_mcp/*.py` (~7,000 lines)
- Risk: A Revit API change or a typo in a rarely-used route is discovered only by a user in a live model, after a transaction has already started.
- Priority: High — but blocked by the `from utils import` path issue and the IronPython host requirement. The pragmatic first step is extracting pure helpers (`get_element_id_value`, `make_element_id`, `sanitize_string`, `_resolve_categories`) into a module importable under CPython 3.

**`tools/utils.py:format_response()` — zero tests:**
- What's not tested: The success/error classification heuristic and all six output-key branches.
- Files: `tools/utils.py`
- Risk: This function already shipped a bug that mislabeled valid data as an error (`c1231f6`). It is pure, dependency-free, and trivially testable — the highest value-per-effort test in the repo.
- Priority: High.

**All 48 MCP tool wrappers — zero tests:**
- What's not tested: Parameter marshalling in `tools/*_tools.py`; only `get_revit_model_info` is exercised, and only end-to-end.
- Files: `tools/*.py` (~1,400 lines)
- Risk: A wrong payload key silently produces a 400 from Revit that surfaces as a generic error string.
- Priority: Medium.

**Existing tests require a live Revit instance and are not runnable in CI:**
- What's not tested: `tests/test_model_info_format.py` calls the real `get_revit_model_info` tool, which needs Revit + pyRevit listening on port 48884. `tests/test_init_latency.py` is a timing assertion (`< 2.0s`) sensitive to machine speed.
- Files: `tests/test_init_latency.py`, `tests/test_model_info_format.py`
- Risk: Both are bare `asyncio.run` scripts, not pytest tests — there is no runner, no `pytest` dependency, and no CI workflow (`.github/` absent). Effectively the suite never runs.
- Priority: High — establishing a runnable, Revit-free test tier is the precondition for every other coverage item above.

---

*Concerns audit: 2026-09-04*
