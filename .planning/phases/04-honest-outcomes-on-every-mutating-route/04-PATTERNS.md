# Phase 4: Honest outcomes on every mutating route - Pattern Map

**Mapped:** 2026-10-23
**Files analyzed:** 9 groups (about 30 modified files)
**Analogs found:** 9 / 9 (all analogs are tracked repo source; no gitignored mirrors used)

All line numbers refer to the files as read on 2026-10-23. Revit half = IronPython 3.4 level: no f-strings, no `{**a}` merges, relative sibling imports.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `revit_mcp/textutils.py` (+ `classify_outcome`, `build_outcome`, `finalize_outcome`) | utility (pure helper) | transform | `revit_mcp/textutils.py::parse_request_data` (pure, CPython-tested) | exact (same file/convention) |
| `revit_mcp/utils.py` (re-export; `commit_and_report` untouched) | utility | request-response | its own import block lines 9-14 | exact |
| 14 route modules: `annotation, building, colors, detail, documentation, editing, interop, mep, placement, rooms, structure, tags, transforms, view_management` | route handler | CRUD / batch | `revit_mcp/editing.py::_modify_element` lines 159-287 (already migrated) | exact |
| non-transaction routes: `document`, `worksharing`, `view_management.set_active_view`, `placement.load_family` | route handler | request-response | `_modify_element` response shape + `build_outcome(None, ...)` | role-match |
| already-migrated routes needing `outcome`: `code_execution.py`, `parameters.py`, `editing.modify_element` | route handler | CRUD | `editing.py:236-282` | exact |
| `tools/utils.py` (partial branch in `_project_response`) | renderer | transform | `_project_response` success/error branches, lines 157-250 | exact |
| `scripts/conventions.py` (+ `check_commit_goes_through_report`, wired into `check_route_module`) | static check | transform | `check_element_id` lines 308-344 (AST) and `check_request_parsing` 347-370 | exact |
| `tests/unit/test_conventions.py` | test | static | tests at lines 83-95, 193-201, 268-282 | exact |
| `tests/unit/test_format_response.py` | test | transform | rolled_back pair, lines 152-190 | exact |
| `tests/unit/test_textutils.py` / new `test_outcome.py` | test | transform | `test_textutils.py` header lines 18-28 | exact |
| four `tests/unit/test_routes_*_identity.py` worlds | test fixture | event-driven (fake) | `make_db` in `test_routes_mep_parameter_identity.py:344-416` | exact |
| `tests/test_phase4_live_outcomes.py` (new, standalone live) | test (live) | request-response | `tests/test_model_info_format.py` (whole, 18 lines) | exact |
| `scripts/new_tool.py:87`, `contrib-kit/revitmcp_kit.py:151`, `CONTRIBUTING.md`, `CLAUDE.md` | docs/scaffold | n/a | existing text mentioning `t.Commit()` | text edit |

## Pattern Assignments

### Every transacting route module (the migration shape)

**Analog:** `revit_mcp/editing.py::_modify_element` (lines 159-287), the reference migrated route.

**Imports** (editing.py line 7, 9):
```python
from .utils import get_element_name, make_element_id, get_element_id_value, suppress_warnings, parse_request_data, commit_and_report
from pyrevit import routes, revit, DB
```
Add `finalize_outcome` / `build_outcome` to the `.utils` import (re-exported from textutils). Never import one `revit_mcp/` domain from another.

**Swallower capture** (lines 160-162). Almost all 26 bare sites call `suppress_warnings(t)` as a bare statement (e.g. `editing.py:56`, `delete_elements`). Change to:
```python
t = DB.Transaction(doc, "Modify Element via MCP")
t.Start()
swallower = suppress_warnings(t)
```

**Commit and rollback branch** (lines 236-265, literal today):
```python
commit_result = commit_and_report(t, swallower)
if not commit_result["committed"]:
    logger.error("modify_element transaction did not commit (status={}) for element {}".format(
        commit_result["transaction_status"], element_id))
    return routes.make_response(
        data={"status": "rolled_back", "element_id": element_id,
              "attempted_changes": changes, "failed": failed,
              "transaction_status": commit_result["transaction_status"],
              "failures": commit_result["failures"],
              "message": ("... Revit rolled the transaction back at Commit() ... "
                          "No changes were saved to the model.")},
        status=409)
```
Same literal 409 shape also at `code_execution.py:132-160` and `parameters.py:497-523`.

**Success + transaction wrapper** (lines 267-287):
```python
return routes.make_response(data={"status": "success", "element_id": element_id,
    "changes": changes, "failed": failed,
    "transaction_status": commit_result["transaction_status"], "message": message})
except Exception as tx_error:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    raise tx_error
```
Outer handler (editing.py:105-110, also tags.py:240-245) returns `{"error": str(e), "traceback": error_trace}` with 500. Per D-14 add an `outcome` (real status via `try: str(t.GetStatus()) except Exception: None`) to that body for transacting routes; traceback stays (HYG-01 deferred).

**Batch accounting** (analog `tags.py:150-233`, `tag_elements`): per-item `skipped.append({"element_id": eid, "reason": ...}); continue`, then bare `t.Commit()` at 219, then `status: "success"` always. Migrate to: add `succeeded.append(eid)` where `tagged_ids.append(...)` happens, `failed.append({"item": eid, "reason": str(err)})` beside each `skipped.append`, keep legacy keys (`tagged_count`, `tag_ids`, `skipped`) and call `finalize_outcome(commit_result, data, len(element_ids), succeeded, failed)`.

**All-or-nothing variant** (D-05, `editing.py:54-103` `delete_elements`): keep pre-validation 404 loop (lines 41-51) before the transaction; replace `t.Commit()` at line 75 with `commit_and_report`; do not emit `partial` (`succeeded` = all ids or rollback 409). `transform_elements` and `create_room_separation` follow the same shape.

**Post-commit reads** (Pitfall 2): `documentation.create_sheet`, `view_management.create_view`, `rooms.create_room`, `placement.place_family` read element state after `Commit()`. Check `commit_result["committed"]` first and return 409, then read.

**Anti-patterns:** no `{**a, **b}` (use `dict(a); d.update(b)`); no f-strings; no new module for helpers; do not put `partial` or `rolled_back` into the `format_response` error set.

---

### `revit_mcp/textutils.py` (utility, transform)

**Analog:** `parse_request_data` (lines 231-261) plus module header imports (lines 17-18: `import json`, `import logging`). Pure, no pyRevit imports, docstring explains the why, 3.4-level syntax. Register the three new helpers here (research-recommended: `test_registration.py:256` hard-codes the helper set, so a new module costs two test edits plus `LOCAL_MODULES` in `scripts/conventions.py:42`). Skeleton in 04-RESEARCH.md "Pure helpers"; `finalize_outcome(commit_result, data, requested, succeeded, failed) -> (payload, http)` must: set `payload["status"]`, `payload["outcome"]` (D-03), on 409 keep top-level `transaction_status` and `failures` and swap the message, on 422 add a truthy `error`. Re-export in `utils.py` by extending the block at lines 9-14:
```python
from .textutils import (  # noqa: F401
    normalize_string,
    parse_request_data,
    sanitize_string,
    sanitize_value,
)
```

---

### `tools/utils.py` partial branch (renderer)

**Analog:** `_project_response` lines 157-250.
Insert before the `if is_success:` payload pick (after `has_error` computed at 169-171, which must NOT change):
```python
status = response.get("status", "").lower()
has_error = (bool(response.get("error")) or
             status in ("error", "failed", "failure", "exception"))
...
if is_success:
    if "output" in response: ...
    elif "message" in response:
        return response["message"]      # <- a partial dict would collapse to this
```
Add `if status == "partial": ...` as the first thing inside `if is_success:` (banner `=== PARTIAL SUCCESS ===`, `Succeeded: N of M`, one line per failed item with id and reason, cap about 100). Use `.format`, keep `str` return. Note `format_response` appends provenance (lines 40-47) automatically; the new branch only changes `_project_response`.

---

### `scripts/conventions.py` (static check, D-02)

**Analog:** `check_element_id` (308-344). Pattern to copy: `tree, error = _parse(label, source)`; `if error: return violations + [error]`; `ast.walk` over `ast.Call` matching `getattr(node.func, "attr", None)`; append one message string with `sorted(lines)`. Use AST (not text) since scaffolds mention `t.Commit()` in comments. Exempt only the body of `commit_and_report` when `label` ends with `revit_mcp/utils.py` (code in 04-RESEARCH.md "Static check"). Wire in at lines 510-517:
```python
def check_route_module(label, source):
    return (
        check_encoding_cookie(label, source)
        + check_ironpython_dialect(label, source)
        + check_element_id(label, source)
        + check_request_parsing(label, source)
        + check_route_registrar(label, source)
    )
```

### `tests/unit/test_conventions.py`

**Parametrised file test** (lines 91-95; copy, but do NOT copy the `utils.py` skip of 84-86, the exemption lives in the checker):
```python
@pytest.mark.parametrize("path", REVIT_MCP_FILES, ids=_rel)
def test_request_body_is_not_parsed_by_hand(path):
    violations = conventions.check_request_parsing(_rel(path), _read(path))
    assert not violations, _report(violations)
```
**Known-bad / known-good detector tests** (lines 193-201, 268-282): inline source string with `# -*- coding: utf-8 -*-\n` header; `assert conventions.check_...("bad.py", bad)` and `== []`. Add: bare `t.Commit()` caught; `commit_and_report(t, swallower)` allowed; commented/string `t.Commit()` ignored; `revit_mcp/utils.py` exempt only inside `commit_and_report`.

---

### `tests/unit/test_format_response.py`

**Analog:** lines 152-190. Copy structure: module-level comment explaining the contract, then
```python
def test_rolled_back_409_reaches_the_model_as_a_visible_error():
    body = ('Error: 409 - {"status": "rolled_back", ...}')
    out = format_response(body)
    assert out == body
...
def test_rolled_back_dict_is_not_yet_a_recognized_failure_signal():
    out = format_response({"status": "rolled_back", "transaction_status": "RolledBack"})
    assert "ERROR DETAILS" not in out
```
New tests: partial dict -> `"PARTIAL SUCCESS" in out`, failed ids and reasons present, `"ERROR DETAILS" not in out`; a 422 `Error: 422 - {"status": "failed", ...}` string passes verbatim. Keep the existing rolled_back alarm test unchanged. Imports at lines 16-21 (`import json`, `import pytest`, `from tools.utils import format_response`).

### `tests/unit/test_textutils.py` (or new `test_outcome.py`)

Import style (lines 18-28): `from revit_mcp.textutils import (...)`; plain functions, pytest `parametrize` for the truth table `(False,*,*)->(rolled_back,409)`, `(True,n,0)->(success,200)`, `(True,>0,>0)->(partial,200)`, `(True,0,>0)->(failed,422)`, `(True,0,0)->success`.

---

### Four route-test worlds (`tests/unit/test_routes_*_identity.py`)

**Analog (good world):** `test_routes_mep_parameter_identity.py:344-416`; same in document_interop (340-415) and view_code (358-433).
```python
def Commit(self):
    world.record("commit", self.doc)
    return world.commit_status
...
db.TransactionStatus = types.SimpleNamespace(Committed="Committed", RolledBack="RolledBack")
```
and `World.__init__` has `self.commit_status = "Committed"` (mep:296).

**Gap world:** `test_routes_analysis_color_identity.py:236-238` `Commit()` returns the literal `"Committed"` and there is no `db.TransactionStatus` (falls to MagicMock, so migrated routes would answer 409). Wave 0: add `self.commit_status = "Committed"` to `World.__init__` (line 186-192), return it from `Commit`, and add the `TransactionStatus` SimpleNamespace in `make_db`. Its Transaction also has `__enter__/__exit__` (249-253) used by `colors.py` `with DB.Transaction`.

**Rollback test pattern** (mep:803-815):
```python
world.commit_status = "RolledBack"
reply = call(world, handler_of(world, "parameters", "/set_parameter/"), PARAM_BODY)
assert reply.status == 409
assert reply.data["status"] == "rolled_back"
assert reply.data["transaction_status"] == "RolledBack"
```
Replicate per migrated route (parametrised over a world's routes).

**Pinned tests that must be edited with each module** (add `"outcome"`): `EXPECTED_KEYS` in mep:771-783 and view_code:822-836; view_code:1175 (`/execute_code/` key set, D-13), view_code:1036-1037 (`open_model`), analysis_color:612 (`create_level`), document_interop:793-794 (`delete_elements`). **Pinned source text:** `test_parameter_rollback_source_is_unchanged` (mep:845-852) requires in `parameters.py`: `commit_result = commit_and_report(t, swallower)`, `if not commit_result["committed"]:`, `"status": "rolled_back"`, regex `status=409,\s*\)`, and exactly one `status=409`. Keep `set_parameter`'s literal 409 branch and only add `outcome` into both bodies; do not route it through a shared 409 builder.

---

### `tests/test_phase4_live_outcomes.py` (standalone live, new)

**Analog:** `tests/test_model_info_format.py` (entire file):
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
            print("MODEL_INFO_OK")

asyncio.run(main())
```
Copy skeleton, add a comment line stating it needs live Revit, sentinel `PHASE4_OUTCOMES_OK`, `asyncio.run` at import (so it is excluded from pytest). Never repeat write steps; human-run.

## Shared Patterns

### Transaction invariant
**Source:** `revit_mcp/editing.py:159-162` and `utils.py:83-109`. `t.Start()` then `swallower = suppress_warnings(t)` immediately; only `commit_and_report(t, swallower)` may call `Commit()` (the one legitimate `.Commit()` is `utils.py:129`). `Save`/`SaveAs` stay outside any transaction.

### Route handlers never raise
**Source:** `editing.py:105-110`: outer `try/except Exception as e` returning `routes.make_response(data={"error": str(e), "traceback": error_trace}, status=500)`; validation returns 503 (`No active Revit document`), 400, 404 before the transaction (editing.py:22-51), with no `outcome` (D-04).

### Guarded handler wrapper
**Source:** `editing.py:112-120`. The public `@api.route` handler calls `mutation_document_or_response(...)`, returns the refusal if any, else `attribute_response(_inner(document, request), descriptor, uiapp=uiapp)`. `outcome` is built inside `_inner`; `attribute_response` adds `document`/`process_identity` afterwards.

### Outcome schema (D-03) and `item` meaning
`{"transaction_status", "requested", "succeeded", "failed":[{"item","reason"}], "revit_failures"}`. `reason` = `str(exc)` only (D-07). Recommended `item`: input element id for id-taking routes; 0-based input index for creation routes; step name for secondary-step failures (D-12). Non-transaction routes use `transaction_status: None`.

### Error-dict rule on the MCP side
**Source:** `tools/utils.py:162-171`. A dict is an error only for truthy `error` or status in `error/failed/failure/exception`; `bridge.py` collapses every non-200 to `"Error: <code> - <body>"`, so 409 and 422 are visible for free and only 200 `partial` needs the new render branch.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `outcome` `item_kind` key (optional) | schema | n/a | New schema element; follow 04-RESEARCH.md Open question 5 |
| Export Boolean check (`export_ifc`, `export_document`) | route logic | file-I/O | No existing route checks `doc.Export()` return; only the PDF branch checks its bool (inspect `documentation.py` PDF branch near line 442 when planning). Use 04-RESEARCH.md Pitfall 6 |
| Per-item failure injection hook in fake worlds | test fixture | n/a | No existing hook; add (for example `world.fail_items`) in each world, modeled on `world.break_start` (mep world, `Start()` at line 352) |

## Metadata

**Analog search scope:** `revit_mcp/`, `tools/`, `scripts/conventions.py`, `tests/unit/`, `tests/`
**Files read:** utils.py, editing.py (1-290), tags.py (150-250), tools/utils.py, textutils.py (partial), conventions.py (partial), four test files (partial), test_model_info_format.py
**Pattern extraction date:** 2026-10-23
