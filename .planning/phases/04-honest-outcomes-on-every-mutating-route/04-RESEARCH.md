# Phase 4: Honest outcomes on every mutating route - Research

**Researched:** 2026-10-23
**Domain:** Revit transaction reporting (IronPython 3 route handlers) + CPython response rendering (`format_response`), no new packages
**Confidence:** HIGH (in-repo facts read this session; Revit API return types cited from rvtdocs)

> Numbering note: CONTEXT.md was written when this phase was "Phase 3". Everything below uses the current number (Phase 4); Phase 5/6 in CONTEXT.md text = today's Phase 6 (audit log).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Охват миграции
- **D-01:** На `commit_and_report` переводятся **все** голые `.Commit()` в `revit_mcp/`, а не
  только два названных в PROJECT.md (`editing.py:75` `delete_elements`, `interop.py:96`
  `export_ifc`). Инвентаризация на 2026-09-23 — около 30 мест в `annotation`, `building`, `colors`,
  `detail`, `documentation`, `editing`, `interop`, `mep`, `placement` (включая `ft.Commit()` в
  семейном документе), `rooms`, `structure`, `tags`, `transforms`, `view_management`. Планировщик
  перепроверяет список grep-ом. Без этого TRUTH-01 («все мутирующие маршруты») не выполнено.
- **D-02:** Регрессия запрещается проверкой: `scripts/conventions.py` и `tests/unit/test_conventions.py`
  отвергают `.Commit()` в `revit_mcp/` везде, кроме тела `commit_and_report` в `utils.py`. Тот же
  статический подход, что уже ловит `json.loads(request.data)` и прямой `ElementId`.

### Единая форма исхода
- **D-03:** Каждый ответ мутирующего маршрута получает стандартный блок `outcome` **рядом** с
  существующими ключами (`deleted_ids`, `changes` и т.п. не переименовываются — на них
  опираются докстринги инструментов):
  ```
  "outcome": {
    "transaction_status": "Committed" | "RolledBack" | ... | null,
    "requested": <int|null>,
    "succeeded": [<id или индекс входа>, ...],
    "failed": [{"item": <id или индекс>, "reason": "<str(exc)>"}, ...],
    "revit_failures": [<failures из commit_and_report>]
  }
  ```
  Одноэлементные маршруты тоже несут блок (`requested: 1`) — фаза 5 читает одну схему.
  — **Reversibility:** costly — блок `outcome` читают `format_response` и журнал аудита фазы 5;
  смена схемы — синхронная правка трёх потребителей.
- **D-04:** Статус и HTTP-код выбирает одна чистая функция `classify_outcome(committed,
  n_succeeded, n_failed)` (в `revit_mcp/textutils.py` или `revit_mcp/trust.py` — тестируется из
  CPython), а Revit-зависимый построитель ответа в `utils.py` её вызывает:
  - откат при `Commit()` → **409**, `status: "rolled_back"` (существующий контракт, без изменений);
  - зафиксировано, `failed` пуст → **200**, `status: "success"`;
  - зафиксировано, есть и успехи, и отказы → **200**, `status: "partial"`;
  - ни одного успеха при непустом `failed` → **422**, `status: "failed"` + ключ `error`.
  Ошибки валидации до открытия транзакции (400/404/503) остаются как есть.
- **D-05:** `delete_elements` сохраняет поведение «всё или ничего»: предварительная проверка всех
  id и 404 на первом отсутствующем. Частичное удаление подмножества хуже, чем отказ. Маршрут
  получает `commit_and_report` и блок `outcome`, но не статус `partial`.
- **D-06:** Маршруты, меняющие состояние вне транзакции (`Save`/`SaveAs`, `open_model`, экспорт,
  запись файлов), получают блок `outcome` с `transaction_status: null` и фактическим результатом
  вызова API. `export_ifc`, у которого экспорт идёт внутри транзакции, переходит на
  `commit_and_report`, как и остальные.
- **D-07:** `reason` в `failed` — только `str(exc)`, без traceback (HYG-01 отложен, новые утечки
  не добавляются).

### Видимость частичного отказа для модели
- **D-08:** `format_response` (`tools/utils.py`) получает явную ветку для `status == "partial"`:
  баннер `=== PARTIAL SUCCESS ===`, `message`, строка «Succeeded: N of M», список неудачных
  элементов с причинами. Это **не** новый сигнал ошибки — `has_error` и множество
  `error/failed/failure/exception` не меняются (запрет CLAUDE.md соблюдён). Без ветки
  успех-ветка вернула бы один `message`, и отказы исчезли бы.
- **D-09:** Пара тестов в `test_format_response.py` по образцу `rolled_back`: `partial`-словарь
  отображается с баннером и id отказавших элементов; тест-сигнал, что `partial` сознательно не
  входит в множество отказов. Плюс тест, что 422 `failed` доходит видимой ошибкой.

### Проверка
- **D-10:** Итерации без перезапуска Revit: чистая классификация — unit-тестами; маршруты — приёмом
  из CLAUDE.md (текст модуля через `/execute_code/`, `exec` в пространстве имён с
  `__package__ = "revit_mcp"` и фиктивным `api`). Один полный перезапуск Revit в конце фазы для
  живых критериев 1 и 4.
- **D-11:** Живой набор критерия 1: по одному маршруту на семейство — одноэлементный
  (`modify_element`), пакетный, экспорт (`export_ifc`). Критерий 4 — пакетный маршрут с
  поэлементным `continue` (не `delete_elements`, см. D-05); конкретный маршрут выбирает
  планировщик из `building`/`tags`/`colors`.

### Claude's Discretion
- В каком из чистых модулей живёт `classify_outcome`.
- Имя Revit-зависимого построителя ответа и порядок миграции модулей.
- Что считать `item` для маршрутов создания (индекс входа или созданный id).

### Deferred Ideas (OUT OF SCOPE)
- Санитизация traceback в ответах (HYG-01).
- Лимиты размера партии (HYG-02).
- Dry-run для разрушительных инструментов — вместе с preview-токеном (POLICY-02).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRUTH-01 | Все мутирующие маршруты сообщают реальный `TransactionStatus`, а не предполагаемый успех | Inventory below: 26 bare `Commit()` call sites in 14 modules (AST-counted) plus 3 already-migrated routes; pure `finalize_outcome` helper; AST convention check (D-02) |
| TRUTH-02 | `delete_elements` и `export_ifc` переведены на `commit_and_report` | `editing.py:75`, `interop.py:96`; export additionally discards `doc.Export()`'s Boolean (see Pitfall 6) |
| TRUTH-03 | Пакетные операции возвращают пропущенные и сбойные элементы рядом с успешными, а не только счётчик | Per-route "how skips are reported today" column; `outcome.succeeded/failed` carrying input ids/indices |
| TRUTH-04 | Частичный отказ имеет собственный явный статус | `classify_outcome` -> 200 `partial` / 422 `failed`; `format_response` partial branch (D-08); bridge collapse of non-200 verified |
</phase_requirements>

## Summary

The phase is a mechanical-but-wide migration, not a research-heavy one. Three routes already use `commit_and_report` (`code_execution`, `parameters.set_parameter`, `editing.modify_element`); an AST count shows **26** remaining bare `.Commit()` calls in 14 modules (not "about 30"; 25 `t.Commit()` plus the family-document `ft.Commit()` in `placement.py:922`, which is the only one whose result is compared but then ignored on the rollback branch). Almost every one of them also calls `suppress_warnings(t)` and **throws the swallower away**, so `commit_and_report(t, None)` would return an empty `failures` list: each migration must capture `swallower = suppress_warnings(t)`.

The load-bearing transport fact is unchanged and re-verified: `bridge.py` hands every non-200 reply to the tools as an `"Error: <code> - <body>"` string, while a 200 arrives as a dict that `format_response` renders by picking ONE key (`output` / `message` / `result` / `data`). So (a) 409 `rolled_back` and 422 `failed` stay visible for free, and (b) a 200 `partial` dict is rendered as just its `message` today, so the failure ids vanish exactly as D-08 predicts; the new branch in `tools/utils.py` is mandatory, not cosmetic. Today `create_line`/`create_surface`/`create_level` already collect `errors` and `tag_elements`/`tag_walls` already collect `skipped`, but `format_response` shows the model only `"Created 1 element(s)"` - the per-element reasons never reach it.

The biggest planning risk is **test-fixture blast radius**, not Revit behaviour: four route test files fake pyRevit with a "world"; the analysis/color world has no `DB.TransactionStatus`, so every migrated route there would return 409 in unit tests until the fake is fixed; and at least 15 existing tests pin exact reply key sets (`EXPECTED_KEYS`, `sorted(...) == [...]`, `set(reply.data) == {...}`) or source text (`status=409` count) that adding `outcome` will break. All are deliberate-update tests and must be edited in the same commit as each module.

**Primary recommendation:** Put `classify_outcome` plus a pure `finalize_outcome(commit_result, data, requested, succeeded, failed)` (returns `(payload, http_status)`) in `revit_mcp/textutils.py` (already a registered helper; a new helper module would force edits to two hard-coded helper sets in `test_registration.py`), re-export it through `utils.py`, migrate modules in four groups aligned to the four existing test worlds, and finish with one human-run live gate after a full Revit restart.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Real `TransactionStatus` capture | Revit extension (`revit_mcp/*`, IronPython) | - | Only the in-process `Transaction.Commit()` knows the status |
| Outcome classification (`success/partial/failed/rolled_back` + HTTP code) | Pure helper in `revit_mcp/textutils.py` (imports nothing from pyRevit; CPython-testable) | `utils.py` re-export | CLAUDE.md: new domain logic belongs where it can be tested |
| Per-element succeeded/failed accounting | Route handlers (each knows its own loop) | - | Only the loop sees which item raised |
| Surfacing partial/failed to the model | MCP tool layer (`tools/utils.py::format_response`) | `bridge.py` (non-200 -> `Error:` string) | Single renderer on the CPython side |
| Static regression guard (no bare `Commit()`) | `scripts/conventions.py` + `tests/unit/test_conventions.py` | `scripts/new_tool.py`, `contrib-kit` scaffolds | Same mechanism as `json.loads(request.data)` / `ElementId` checks |
| Live proof of real status | Human-run live gate against real Revit | - | CPython cannot import pyRevit |

## Standard Stack

No new packages. Nothing is installed in this phase.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| existing `revit_mcp/utils.py::commit_and_report` | in repo | returns `{committed, transaction_status, failures}` | already the project contract (3 routes use it) |
| existing `revit_mcp/textutils.py` | in repo | home for the new pure helpers | importable under CPython, tested in `tests/unit/test_textutils.py` |
| pytest | `>=8.0.0` (dev group, pyproject) | unit suite | repo standard; baseline measured below |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| helpers in `textutils.py` | new `revit_mcp/outcome.py` | Cleaner name, but `tests/unit/test_registration.py:256` hard-codes `helpers = {"utils", "textutils", "registry", "identity", "trust", "integrity"}` and `test_revit_mcp_helpers_define_no_routes` hard-codes the same tuple; a new module needs both edited, plus `LOCAL_MODULES` in `scripts/conventions.py:42` for the flat-import check. Not worth it. |
| helpers in `trust.py` | - | `trust.py` is the secret/integrity module; unrelated concern. |

**Installation:** none.

**Baseline (measured this session):** `uv run pytest tests/unit -q -x` -> `4692 passed, 3 skipped in 59.35s`. [VERIFIED: local run]

## Package Legitimacy Audit

No external packages are installed or recommended in this phase. `gsd_run query package-legitimacy check` not run (nothing to check). 
**Packages removed due to [SLOP] verdict:** none  **Packages flagged [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
MCP client
   | tool call (e.g. tag_elements)
   v
tools/<domain>_tools.py  -- format_response(result) --> text to model
   |  revit_post(...)                         ^
   v                                          |
bridge.py _revit_call  ---- 200 -> dict ------+  (dict: success / partial -> new PARTIAL branch)
   |   HTTP :48884         non-200 -> "Error: <code> - <body>" string (409 rolled_back, 422 failed, 4xx/5xx)
   v
revit_mcp/<domain>.py handler (IronPython, in Revit)
   1. guard (mutation_document_or_response)   -> 412/409/etc refusal, no outcome
   2. validate payload                         -> 400/404/503, no outcome (D-04)
   3. t = DB.Transaction; t.Start(); swallower = suppress_warnings(t)
   4. per-item loop: item ok -> succeeded.append(item)
                     item raised/skipped -> failed.append({"item": .., "reason": str(exc)}); continue
   5. commit_result = commit_and_report(t, swallower)      <-- ONLY place Commit() is called
   6. payload, http = finalize_outcome(commit_result, data, requested, succeeded, failed)   (pure, textutils)
        not committed          -> 409 "rolled_back"
        committed, no failed   -> 200 "success"
        committed, mixed       -> 200 "partial"
        committed, 0 success   -> 422 "failed" (+ "error")
   7. routes.make_response(data=payload, status=http) -> attribute_response (adds document/process_identity)
```

### Recommended Project Structure
```
revit_mcp/textutils.py    # + classify_outcome, build_outcome, finalize_outcome (pure; tested)
revit_mcp/utils.py        # re-export the new names in the existing "from .textutils import (...)" block; commit_and_report unchanged
revit_mcp/<14 modules>    # migrate each Commit() site
tools/utils.py            # + partial branch in _project_response (D-08)
scripts/conventions.py    # + check_commit_goes_through_report (D-02), wired into check_route_module
tests/unit/               # new test_outcome.py (pure), test_format_response additions, test_conventions additions, per-world updates
```

### Pattern 1: migration shape (IronPython-3.4-safe, no f-strings)
**What:** every transacting handler captures the swallower, accounts for every item, commits only through `commit_and_report`, and never reads element state before checking `committed`.
**Example (derived from the in-repo reference `editing.py:162-265`):**
```python
t = DB.Transaction(doc, "Tag Elements via MCP")
t.Start()
swallower = suppress_warnings(t)          # capture it: commit_and_report needs it for `failures`
try:
    succeeded, failed = [], []
    for eid in element_ids:
        try:
            ...                              # existing per-item work
            succeeded.append(eid)
        except Exception as item_err:
            failed.append({"item": eid, "reason": str(item_err)})   # D-07: str(exc) only
    commit_result = commit_and_report(t, swallower)
    data = {"message": ..., "tagged_count": ..., "tag_ids": ..., "skipped": skipped}  # legacy keys kept
    payload, http = finalize_outcome(commit_result, data, len(element_ids), succeeded, failed)
    return routes.make_response(data=payload, status=http)
except Exception as tx_error:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    raise tx_error
```
`finalize_outcome` must: set `payload["status"]`; set `payload["outcome"]` per D-03; on 409 replace the success `message` with the rollback wording and keep `transaction_status`/`failures` top-level keys as `set_parameter` does today; on 422 add a truthy `error`; never mutate legacy keys' names.

### Anti-Patterns to Avoid
- **Reading element state before checking `committed`.** `documentation.py` (`new_sheet.SheetNumber`), `view_management.py` (`new_view`), `rooms.py` (`room.LookupParameter`), `placement.py` (`new_instance.Location.Point` inside a bare `except:` that falls back to the *requested* point) all read after `Commit()`. After a rollback the element is invalid; today that either raises into a 500 or, in `place_family`, silently reports success with a fabricated location. Check `committed` first, return 409, then read.
- **`{**a, **b}`, `f(*a, *b)`, any 3.5+ syntax in the Revit half.** IronPython 3.4 is at the Python 3.4 language level; `conventions.py` parses with modern `ast`, so it only catches f-strings, not PEP 448. Build dicts with `dict(a); d.update(b)`.
- **Adding `"partial"` (or `"rolled_back"`) to the `format_response` failure set.** Forbidden by CLAUDE.md and D-08. Add a dedicated render branch instead.
- **Returning 207 or 200 for rollback.** 409 is load-bearing (project memory + `test_format_response.py:179`).
- **Changing legacy keys.** `deleted_ids`, `created`, `errors`, `skipped`, `changes`, `failed` stay; `outcome` is additive.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Status/HTTP selection | per-route `if/elif` ladders | one `classify_outcome` | 20+ call sites would drift; Phase 6 reads one schema |
| Failure list from Revit | reading `swallower` yourself | `commit_and_report(t, swallower)["failures"]` | already the contract; includes warning-severity entries Revit auto-deleted |
| Request parsing | `json.loads(request.data)` | `parse_request_data` | enforced by `conventions.py` |
| Element ids | `.IntegerValue`, `DB.ElementId(int)` | `get_element_id_value`, `make_element_id` | Revit 2024-2027 span |
| Static ban on bare `Commit()` | grep in a test | AST check in `scripts/conventions.py` | blanks strings/comments (scaffold comments mention `t.Commit()`), same pattern as `check_element_id` |

**Key insight:** the audit log (Phase 6) will read exactly the `outcome` block; any route that computes its own status string is a future audit lie.

## Mutating-Route Inventory

Source: every `@api.route` in `revit_mcp/*.py` (read this session), plus an AST count of `.Commit()` calls: `annotation [183, 362] building [247, 560, 651] colors [865, 983] detail [128] documentation [98, 235, 451] editing [75] interop [96, 225] mep [161, 321, 490] placement [446, 922] rooms [105, 275] structure [89, 273] tags [219] transforms [174] view_management [297]` = 26 outside `utils.py` (`utils.py:129` is the legitimate one inside `commit_and_report`). [VERIFIED: ast scan this session]

"Family": S = single element, B = batch with per-item accounting, A = batch all-or-nothing (pre-validated or one call), E = export, N = no transaction. "Skips today": how per-item failure is reported before the phase.

| Module | Route | Commit line | Family | Skips today | Migration notes |
|--------|-------|-------------|--------|-------------|-----------------|
| annotation | `/create_dimensions/` | 183 | S | none; `dim` falsy -> `created=[]` still `success` | falsy `dim` must become `failed` (reason "NewDimension returned nothing") |
| annotation | `/tag_walls/` | 362 | B | `skipped[{wall_id, reason}]`; `tags_placed` count; `walls_already_tagged` counted separately | succeeded not tracked by id (only count) - add list; already-tagged = no-op, exclude from `requested` and keep legacy key |
| building | `/create_line/` | 247 | B | `errors[]` strings `"Element {idx}: ..."`; status always `success` even if all failed | track `(idx, reason)` structurally; best live candidate with invalid `level_name` (no Revit side effect for the bad item) |
| building | `/create_surface/` | 560 | B | same as create_line | same |
| building | `/create_level/` | 651 | B | `errors[]` | `DB.Level.Create` succeeds before `new_level.Name = ...` can raise: the level exists in the transaction but is listed as an error. Decide: count as failed AND note it persists, or roll the single item back; recommend `failed` with reason noting "created but not named". |
| colors | `/color_splash/` | 865 | B (module-level function returns a dict, route wraps it in `make_response(data=result)` -> always 200) | per-element exceptions only `logger.warning`; `statistics.elements_colored` count | `with DB.Transaction(...) as t:`; swallower discarded; result dict carries `status: "error"` at HTTP 200 for validation failures (pre-existing, stays per D-04) |
| colors | `/clear_colors/` | 983 | B | `logger.warning` only; `elements_processed` count | same |
| detail | `/create_detail_line/` | 128 | S | line-style failure swallowed at debug level -> `success` | style failure = `failed` item "line_style" (instance created, style not applied) |
| documentation | `/create_sheet/` | 98 | S | none | post-commit reads `new_sheet.*` - reorder |
| documentation | `/create_schedule/` | 235 | S | `fields_not_found` list (success even if no field added) | requested = len(fields) when given; unknown field names -> `failed` |
| documentation | `/export_document/` | 451 | E (export inside transaction) | `doc.ExportImage`/`doc.Export` return value ignored for png/jpg/dwg; success even when file missing (`file_size_kb: 0`) | D-06 + Pitfall 6 |
| editing | `/delete_elements/` | 75 | A (D-05) | pre-validation -> 404 on first missing | add `commit_and_report` + `outcome`; no `partial` |
| editing | `/modify_element/` | already migrated | S (multi-param) | `failed[{parameter, reason}]`; 409 on rollback | add `outcome`; keep literal rollback structure if `test_parameter_rollback_source_is_unchanged`-style pins exist for it (only `parameters.py` is pinned) |
| interop | `/export_ifc/` | 96 | E | `doc.Export()` Boolean ignored; success reported with `file_size_kb: 0` if no file | D-06 + Pitfall 6 |
| interop | `/link_file/` | 225 | S | `result_id` may be `None` and still `success` | `None` id = `failed` |
| mep | `/create_duct/` | 161 | S | diameter/width/height silently skipped when parameter missing/read-only | each skipped dimension = `failed` item |
| mep | `/create_pipe/` | 321 | S | diameter silently skipped | same |
| mep | `/create_mep_system/` | 490 | S | commits, then returns 500 "Failed to create system" if `new_system` is None | decide order: if nothing was created, roll back instead of committing an empty transaction; report via outcome |
| parameters | `/set_parameter/` | already migrated | S | 409 on rollback | add `outcome`; has a source-text pin (see Pitfall 3) |
| placement | `/place_family/` | 446 | S | `properties_set` / `properties_failed` (strings) | `properties_failed` entries -> `failed` items -> instance placed + failed props = `partial`? **Open question 1** |
| placement | `/edit_family/` | 922 (`ft.Commit()` in the FAMILY document) | S | result stored in `touched["family_edited"]`, but a rolled-back family commit still proceeds to `LoadFamily` and answers `success`, `reloaded: true` | must stop before reload and return 409 `rolled_back`; reply of a rolled-back family edit must not claim the reload |
| placement | `/load_family/` | none | N | `ok` False -> `status: "already_loaded"` (200) | `outcome.transaction_status: null`, `requested: 1` |
| rooms | `/create_room/` | 105 | S | name/number param set silently skipped; post-commit reads | reorder reads after `committed` check |
| rooms | `/create_room_separation/` | 275 | A (one `NewRoomBoundaryLines` call; exception -> rollback) | none | `succeeded` = created line ids |
| structure | `/create_grid/` | 89 | B-silent | zero-length grid `continue` with only `logger.warning`; grid-name failure swallowed | zero-length = `failed`; cleanest zero-side-effect live partial candidate |
| structure | `/create_framing/` | 273 | B-silent | zero-length `continue` only logged | same |
| tags | `/tag_elements/` | 219 | B | `skipped[{element_id, reason}]`, `tag_ids` are TAG ids not input ids | track input `eid` in `succeeded`; keep `tag_ids`. Best live batch candidate (takes element ids; "Element not found" skip is side-effect free) |
| transforms | `/transform_elements/` | 174 | A (pre-validation 404/500; exception rolls back all) | none | `succeeded` = all ids on commit |
| view_management | `/create_view/` | 297 | S | none | post-commit `new_view` reads - reorder |
| view_management | `/set_active_view/` | none (UI `uidoc.ActiveView = ...`) | N | exception -> 500 | `transaction_status: null` |
| worksharing | `/open_model/` | none | N | exception/None doc -> 500 | `transaction_status: null`, `succeeded: [file_path]` |
| document | `/save_document/` | none (`Save`/`SaveAs` outside tx by design) | N | exception -> 500 | `transaction_status: null` |
| documents | `/activate_document/` | none | N | already returns 200/422 with verified observation | D-06 outcome optional; **Open question 3** (not a model mutation) |
| code_execution | `/execute_code/` | already migrated | S | n/a | adds `outcome` -> breaks pinned key set (Pitfall 3) |

Not mutating (no work): `ai_filter`, `room_data`, `material_quantities`, `model_statistics`, `clash_check`, `list_category_parameters`, `selected_elements`, `model_info`, `project_parameters`, `element_properties`, `list_families`, `list_family_categories`, `list_levels`, `status`, `get_view`, `list_views`, `current_view_info`, `current_view_elements`, `documents`, `document_summary`, `document_levels`, `model_worksets`. [VERIFIED: route list read this session; `model_worksets` is a POST that only reads file info]

No new routes or tools are added, so `tests/unit/tool_manifest.txt` is unchanged.

## Current shape of the key contracts (verbatim)

`revit_mcp/utils.py:112-135` [VERIFIED: Read this session]:
```
def commit_and_report(transaction, swallower=None):
    ...
    status = transaction.Commit()
    failures = list(swallower.failures) if swallower is not None else []
    return {
        "committed": status == DB.TransactionStatus.Committed,
        "transaction_status": str(status),
        "failures": failures,
    }
```
Each `failures` entry is `{"severity", "description", "failing_element_ids"}` (`utils.py:60-64`). The swallower records **warnings too** (it deletes them and logs), so a successful commit can carry non-empty `failures`; `outcome.revit_failures` on a 200 means "Revit auto-deleted these warnings", not an error. Keep it, but do not let the renderer or classifier treat a non-empty list as failure.

`tools/utils.py` classification [VERIFIED: Read this session]: `has_error = (bool(response.get("error")) or status in ("error", "failed", "failure", "exception"))`; the success branch returns the first present of `output`, `message`, `result`, `data`, else a generic key dump. A status-less dict with `message` renders as `message` only. `"failed"` IS already in the error set; only a dict (200) path matters because 422 arrives as a string.

`bridge.py` non-200 handling [VERIFIED: grep lines 755-760, 827, 857]: `return "Error: {} - {}".format(response.status_code, response.text)`; no special-casing of 409 or 422 anywhere in `bridge.py` or `tools/` (only `documents.py` uses 422, for activation refusals, which `process_tools` does not interpret).

Rollback body today (`editing.py:249-265`, `parameters.py` equivalent) [VERIFIED: Read]: `{"status": "rolled_back", "element_id", "attempted_changes", "failed", "transaction_status", "failures", "message"}` with `status=409`.

## Test infrastructure that already exists (and what it pins)

| File | What it pins | Effect of this phase |
|------|--------------|----------------------|
| `tests/unit/test_format_response.py:151-190` | `rolled_back` 409 string passes through verbatim; **alarm test**: `format_response({"status": "rolled_back", "transaction_status": "RolledBack"})` must NOT contain `ERROR DETAILS` | keep; add the `partial` pair (D-09) next to it |
| `tests/unit/test_routes_mep_parameter_identity.py:771-783` `EXPECTED_KEYS` | exact sorted key list for 9 success replies (`create_duct`, `create_pipe`, `create_mep_system`, `set_parameter`, `create_room`, `create_room_separation`, `create_grid`, `create_framing`, `tag_elements`), e.g. `("structure", "/create_grid/"): ["count", "created", "message", "status"]` | add `"outcome"` to each list |
| same file `:846-852` `test_parameter_rollback_source_is_unchanged` | source text of `parameters.py` must contain `commit_result = commit_and_report(t, swallower)`, `if not commit_result["committed"]:`, `"status": "rolled_back"`, a `status=409,` regex, and `source.count("status=409") == 1` | do NOT route `set_parameter` through a shared 409 builder unless this test is deliberately rewritten; simplest: keep its literal 409 branch and add `outcome` to both bodies |
| `tests/unit/test_routes_view_code_identity.py:822-836` `EXPECTED_KEYS` | keys for `transform_elements`, `create_view`, `set_active_view` | add `"outcome"` |
| same file `:1175` | `set(reply.data) == {"status", "description", "output", "code_executed", "transaction_status", "document_scope", "process_identity"}` for `/execute_code/` | add `"outcome"` (or exempt execute_code - Open question 2) |
| same file `:1036-1037` | `open_model` keys: original list `+ {"document","process_identity"}` only | add `"outcome"` |
| `tests/unit/test_routes_analysis_color_identity.py:612` | `create_level` success keys `["count","created","message","status"]` | add `"outcome"` |
| `tests/unit/test_routes_document_interop_identity.py:793-794` | `delete_elements` keys `["cascaded_ids","deleted_count","deleted_ids","message","status"]` | add `"outcome"` |
| `tests/unit/test_routes_*_identity.py` `make_db(world)` | fake `DB`; `Transaction.Commit()` returns `world.commit_status` ("Committed"/"RolledBack") in three worlds; `db.TransactionStatus = types.SimpleNamespace(Committed="Committed", RolledBack="RolledBack")` in three worlds | **analysis_color world has neither** (its `Commit()` returns the literal `"Committed"` and `db.TransactionStatus` falls through to `MagicMock`, so `"Committed" == MagicMock` is False): every migrated annotation/building/colors/detail route would answer 409 until `TransactionStatus` and `commit_status` are added to that fake (Wave 0) |
| `tests/unit/test_registration.py:256` | hard-coded helper set for the no-cross-domain-import rule | untouched if helpers go in `textutils.py` |
| `tests/unit/test_conventions.py` | parametrised per file; detectors tested against known-bad input | add check + known-bad/known-good tests for the Commit rule |
| `tests/unit/test_textutils.py` | imports from `revit_mcp.textutils` under CPython | home for `classify_outcome` / `finalize_outcome` tests |

The route-test "world" harness (fake `pyrevit` module in `sys.modules`, real `register_*_routes` captured by a fake `api`, events recorded) means the **handlers themselves are unit-testable under CPython**, including rollback (`world.commit_status = "RolledBack"`) and per-item failures. This is stronger than D-10's `/execute_code/` trick, which remains only for iteration against a real `doc`. All 20+ migrated modules already belong to one of these four worlds: `("utils","analysis","annotation","building","colors","detail")`, `("utils","document","documentation","editing","interop","placement")`, `("utils","mep","parameters","rooms","structure","tags")`, `("utils","transforms","view_management","worksharing","code_execution")`.

## Common Pitfalls

### Pitfall 1: `suppress_warnings(t)` result discarded
**What goes wrong:** all 26 sites call `suppress_warnings(t)` / `suppress_warnings(ft)` as a bare statement (26 bare calls counted by grep, one per site); `commit_and_report(t, None)` then reports `failures: []` even on rollback, hiding *why*.
**How to avoid:** `swallower = suppress_warnings(t)` everywhere; a conventions check can assert that a function calling `commit_and_report` passes a non-literal-`None` second argument (optional hardening).
**Warning signs:** `outcome.revit_failures == []` on a 409.

### Pitfall 2: reading model state after a rolled-back commit
See Anti-Patterns. Affects `create_sheet`, `create_view`, `create_room`, `place_family`, `create_schedule`, `create_mep_system`, `create_duct`/`pipe` (ids read after commit). The existing 500-on-invalid-object behaviour is an *accidental* error; the migrated behaviour must be a deliberate 409.

### Pitfall 3: pinned key sets and source text
Listed in the test table. Adding `outcome` is a deliberate reshaping; those tests exist to make you acknowledge it. Update each in the same commit as the module; do not widen `without_attribution` to hide `outcome` (that would hide future accidental additions).

### Pitfall 4: a committed route that then raises
Handlers do `if t.HasStarted() and not t.HasEnded(): t.RollBack()` then `raise`; after a successful `Commit()` `HasEnded()` is True, so a later exception (post-commit read) produces a 500 `error` although the model changed. The generic 500 path should carry an `outcome` whose `transaction_status` is the real one. `Transaction.GetStatus()` returns the current `TransactionStatus` (the rvtdocs `Transaction.Commit` remarks point to it) [CITED: rvtdocs.com/2025/32714010-7138-f64f-8fde-a310354448e3, via search summary; method page itself not fetched]. Recommend: make the 500 branch cheap and safe (`try: status = str(t.GetStatus()) except Exception: status = None`) in a small shared helper, or keep scope tight and only guarantee `outcome` on the non-500 paths (Open question 4).

### Pitfall 5: statuses other than Committed/RolledBack
`TransactionStatus` has six members: Uninitialized, Started, RolledBack, Committed, Pending, Error [CITED: rvtdocs.com/2027/Autodesk.Revit.DB.Transaction via search]. `commit_and_report` treats everything but `Committed` as not committed. `suppress_warnings` sets `SetForcedModalHandling(False)`, so Pending (waiting on a modeless dialog) should not occur in practice [ASSUMED]. Recommended: `classify_outcome` maps every non-committed result to 409 + `status: "rolled_back"` (existing contract), and `outcome.transaction_status` carries the verbatim string so a rare `Pending`/`Error` stays visible. Do not invent a new status without the user.

### Pitfall 6: exports report success without checking what the export call returned
`Document.Export(String, String, IFCExportOptions)` returns a Boolean (true on success) [CITED: https://rvtdocs.com/2025/7efa4eb3-8d94-b8e7-f608-3dbae751331d]; the DWG overload `Document.Export(String, String, ICollection<ElementId>, DWGExportOptions)` also returns bool [CITED: rvtdocs.com/2025/44ee91ff-c9f3-7df5-b8c0-81c17ac75dc7 via search]. `interop.py:95` (`doc.Export(output_dir or ".", file_name, ifc_options)`) and `documentation.py:442` (DWG) discard it, and `ExportImage` success is inferred from the expected file name. `commit_and_report` only proves the *model transaction* committed. For export routes the outcome must also carry the API result: `succeeded: [file_path]` only when `Export()` returned True (and, as a belt-and-braces check, the file exists), else `failed: [{"item": file_path, "reason": "Export() returned False"}]` -> 422 `failed` if the transaction committed. PDF already checks the bool.
Autodesk's own IFC-export sample wraps the export in a transaction and then **rolls it back** to discard changes the exporter makes [CITED: aps.autodesk.com/blog/export-ifc-rvt-using-revit-automation-api-part-i via search; a sample, not a rule]; this repo commits it. Do not change commit-vs-rollback in this phase (D-06 says migrate onto `commit_and_report`); record it in Open questions.

### Pitfall 7: `already tagged` and other no-op items
`tag_walls` counts `walls_already_tagged` without failure. They are neither succeeded nor failed. Define `requested` as "items the route attempted" and keep the legacy count key; do not put no-ops in `failed`.

### Pitfall 8: scaffolds teach the old idiom
`scripts/new_tool.py:87` and `contrib-kit/revitmcp_kit.py:151` print a commented `t.Commit()` example; `CONTRIBUTING.md:103-108` states the transaction invariant without `commit_and_report`. Once D-02 rejects bare `Commit()`, contributors following the scaffold produce rejected packages. Update the three texts and `CLAUDE.md`'s "Non-negotiable invariants" in the same phase. (`check_route_module` is shared by `scripts/intake_package.py` and the kit, so the new rule also gates contributed packages; the checked-in `contrib-kit/conventions.py` already differs from `scripts/conventions.py` and is rebuilt by `scripts/build_contrib_kit.py`.)

### Pitfall 9: 422 semantics collide only superficially
`documents.py` already answers 422 for refused activation, with a distinct body (`error_code`). The bridge does not interpret 422, so reuse is safe; the discriminator is `status: "failed"` + `outcome`.

## Code Examples

### Pure helpers (textutils.py; no f-strings; 3.4-level syntax)
```python
# Source: derived from CONTEXT D-03/D-04 and commit_and_report's return shape (utils.py:112-135)
def classify_outcome(committed, n_succeeded, n_failed):
    """(status, http_status) for one finished mutation. Pure."""
    if not committed:
        return "rolled_back", 409
    if n_failed == 0:
        return "success", 200
    if n_succeeded > 0:
        return "partial", 200
    return "failed", 422


def build_outcome(transaction_status, requested, succeeded, failed, revit_failures):
    return {
        "transaction_status": transaction_status,
        "requested": requested,
        "succeeded": list(succeeded),
        "failed": [{"item": f["item"], "reason": f["reason"]} for f in failed],
        "revit_failures": list(revit_failures),
    }
```
`finalize_outcome(commit_result, data, requested, succeeded, failed)` = `classify_outcome(commit_result["committed"], len(succeeded), len(failed))` + `build_outcome(...)` + the 409/422 payload fixups; returns `(payload, http)`. Non-transaction routes use `build_outcome(None, ...)` with the API result as succeeded/failed.

### format_response partial branch (tools/utils.py, inside `_project_response`, before the success `message` pick)
```python
# Source: D-08; must not touch the has_error set
if status == "partial":
    outcome = response.get("outcome") or {}
    succeeded = outcome.get("succeeded") or []
    failed = outcome.get("failed") or []
    requested = outcome.get("requested")
    lines = ["=== PARTIAL SUCCESS ===", str(response.get("message", ""))]
    lines.append("Succeeded: {} of {}".format(len(succeeded), requested if requested is not None else len(succeeded) + len(failed)))
    for entry in failed:
        lines.append("Failed {}: {}".format(entry.get("item"), entry.get("reason")))
    return "\n".join(lines)
```
Cap the failed list in the rendering (suggest 100, then "... and N more in outcome.failed") since HYG-02 batch limits are deferred; the model still needs ids (CONTEXT specifics), so print ids, not just counts.

### Static check (scripts/conventions.py, D-02)
```python
# AST, not text: scaffold comments and docstrings legitimately mention `t.Commit()`.
def check_commit_goes_through_report(label, source):
    tree, error = _parse(label, source)
    if error:
        return [error]
    allowed = None
    if label.replace("\\", "/").endswith("revit_mcp/utils.py"):
        allowed = next((n for n in ast.walk(tree)
                        if isinstance(n, ast.FunctionDef) and n.name == "commit_and_report"), None)
    inside = set(id(c) for c in ast.walk(allowed)) if allowed is not None else set()
    bad = sorted(n.lineno for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "Commit"
                 and id(n) not in inside)
    ...
```
Add to `check_route_module`; test with known-bad (`t.Commit()` in a handler), known-good (`commit_and_report(t, swallower)`), the `utils.py` exemption, and a commented/string occurrence. Note `test_element_id_helpers_are_used` skips `revit_mcp/utils.py`; the new parametrised test must NOT skip it (the exemption lives in the checker).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| discard `Commit()` return, answer `success` | `commit_and_report` + 409 on non-commit | param-write debug session (3 routes) | this phase finishes the other 26 sites |
| `errors[]`/`skipped[]` side lists, status always `success` | `outcome` block + `partial`/`failed` status | this phase | model sees failing ids; audit can log truth |

**Deprecated/outdated:** CONTEXT.md "около 30 мест" - actual is 26; CONTEXT canonical refs cite `editing.py:54-101` / `interop.py:89-117` (still accurate) and `revit_mcp/utils.py:83-135` (accurate).

## Runtime State Inventory

Not a rename/migration phase. Nothing persisted by route code holds the old reply shape: no stored data, no registered OS state, no secrets/env vars, no build artifacts change. One deploy-time note: `%APPDATA%\pyRevit\Extensions\revit-mcp-server.extension` is a junction to this repo, so edits under `revit_mcp/` are live on disk immediately but only load after a **full Revit restart** (never pyRevit Reload) [VERIFIED: CLAUDE.md "Known sharp edges"]. Mixed state window: a new CPython `format_response` with an old Revit extension just never sees `partial`/`outcome` (harmless); a new extension with an old `format_response` renders a 200 `partial` as only its `message` (failure ids hidden) - ship both halves together at R2 (RELEASES.md R2 note requires `format_response` to distinguish `partial` from `rolled_back`).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | test runs | yes | 0.11.1 | - |
| Python | `scripts/`, direct runs | yes | 3.14.2 (repo pin 3.13 via uv) | - |
| pytest (dev group) | unit suite | yes | measured: suite runs | - |
| Revit + pyRevit Routes | live gate only | one Revit process and one listener on 48884 are running right now | not probed further | none - human-run; `Get-NetTCPConnection -LocalPort 48884 -State Listen` must return exactly 1 row before trusting any live result |

**Missing dependencies with no fallback:** none for planning or unit work. The live gate is blocking-human by project rule (memory: live gates are human-run, one-shot write steps, full Revit restart after any `revit_mcp/` edit).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0.0 (uv dev group) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests/unit"]` |
| Quick run command | `uv run pytest tests/unit/test_textutils.py tests/unit/test_format_response.py tests/unit/test_conventions.py -q` |
| Route worlds | `uv run pytest tests/unit/test_routes_analysis_color_identity.py tests/unit/test_routes_document_interop_identity.py tests/unit/test_routes_mep_parameter_identity.py tests/unit/test_routes_view_code_identity.py -q` |
| Full suite command | `uv run pytest tests/unit -q` (baseline 4692 passed, 3 skipped, ~60 s) |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRUTH-01 | no bare `.Commit()` outside `commit_and_report` | static (AST) | `uv run pytest tests/unit/test_conventions.py -q` | add tests; checker is Wave 0 |
| TRUTH-01 | each migrated route returns 409 `rolled_back` + `outcome.transaction_status == "RolledBack"` when `world.commit_status = "RolledBack"` (parametrised over the 4 worlds) | unit (fake pyRevit) | route-world command | add per world |
| TRUTH-01 | success reply carries `outcome.transaction_status == "Committed"`, `requested`, `succeeded` | unit (fake pyRevit) | route-world command | update `EXPECTED_KEYS` + add |
| TRUTH-02 | `delete_elements`: commit goes through `commit_and_report`; rollback -> 409, no `deleted_ids` success; still 404 before any transaction on a missing id (D-05) | unit | `... test_routes_document_interop_identity.py -q` | extend |
| TRUTH-02 | `export_ifc`: rollback -> 409; `Export()` returning False with committed tx -> 422 `failed`; file path in `succeeded` only on True | unit (fake `doc.Export` returns bool) | same | add |
| TRUTH-03 | batch with mixed valid/invalid ids returns both lists (`tag_elements`, `create_line`, `create_grid` zero-length) | unit | route-world commands | add |
| TRUTH-04 | `classify_outcome` truth table: (False,*,*)->409; (True,n,0)->200 success; (True,>0,>0)->200 partial; (True,0,>0)->422 failed; includes (True,0,0) | pure unit | `uv run pytest tests/unit/test_textutils.py -q` | add |
| TRUTH-04 | `format_response`: partial dict shows banner, "Succeeded: N of M", every failed id + reason; partial NOT an error; 422 string passes through verbatim; the existing rolled_back alarm test still passes | unit | `uv run pytest tests/unit/test_format_response.py -q` | add (D-09) |
| TRUTH-01..04 | live: real `TransactionStatus` in `outcome`, partial on mixed-id batch, export | live, human | see Live gate below | write script in Wave N |

### Sampling Rate
- **Per task commit:** quick run command (+ the one route-world file the task touched)
- **Per wave merge:** full suite
- **Phase gate:** full suite green (>= 4692 passed baseline + new) before `/gsd-verify-work`; live gate recorded

### Wave 0 Gaps
- [ ] `revit_mcp/textutils.py` helpers + `tests/unit/test_textutils.py` (or new `test_outcome.py`) truth-table tests
- [ ] `tools/utils.py` partial branch + `test_format_response.py` pair + 422-string test
- [ ] `scripts/conventions.py` check + `tests/unit/test_conventions.py` tests; update `scripts/new_tool.py:87`, `contrib-kit/revitmcp_kit.py:151` text, `CONTRIBUTING.md`, `CLAUDE.md`
- [ ] analysis_color world fake: add `commit_status` + `db.TransactionStatus = types.SimpleNamespace(Committed="Committed", RolledBack="RolledBack")` so `Commit()` and `commit_and_report` agree (the other three worlds already have both)
- [ ] a reusable world hook for per-item failure injection (e.g. make `doc.GetElement` return None for a chosen id / make a creation call raise) in each world, to produce partial/failed deterministically

### Live gate (human-run, once, after full Revit restart)
Per memory ("write steps never repeat", "one Revit"): confirm exactly one listener on 48884 first; use an unsaved scratch document, never save; check parameters/ids exist before a one-shot write; clean up created elements with `delete_elements` (which is itself a TRUTH-02 live check).
1. Single-element: `modify_element` on a wall's «Комментарии» -> reply `outcome.transaction_status == "Committed"` (already observable: `transaction_status: "Committed"` was seen live in the param-write debug session).
2. Batch + partial (criteria 3 and 4): `tag_elements` with `element_ids=[<valid id in the view>, 999999999]` and a real plan `view_name` -> HTTP 200 `partial`, `outcome.succeeded == [valid]`, `outcome.failed == [{"item": 999999999, "reason": "Element not found"}]`, and the tool text shows the PARTIAL banner with the bad id. Variant for 422: `tag_elements` with only invalid ids. Alternative with no tag side effects needing cleanup of the invalid item: `create_line` with one valid and one bad `level_name`.
3. Export (criterion 1 export family): `export_ifc` to a scratch path -> `outcome.transaction_status == "Committed"` and `succeeded == [path]`, file exists.
4. Rollback honesty stays covered by units (provoking an error-severity failure live is out of scope; G6-style campaigns are one-shot and unauthorized here).
Suggested artifact: `tests/test_phase4_live_outcomes.py` as a standalone stdio-client script following CLAUDE.md's skeleton (absolute `main.py` path, uppercase sentinel such as `PHASE4_OUTCOMES_OK`, comment stating it needs live Revit), excluded from pytest collection like the other two.

## Security Domain

`security_enforcement` is absent from `.planning/config.json` (treated as enabled).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2/V3 Authentication, Session | no | untouched (Phase 3/5 secret gate) |
| V4 Access Control | no | document guard unchanged; `outcome` is emitted after the guard |
| V5 Input Validation | yes (unchanged) | existing validation before the transaction returns 400/404/503 without `outcome` (D-04) |
| V6 Cryptography | no | - |
| V7 Error handling / information disclosure | yes | `reason` = `str(exc)` only (D-07); the generic 500 still returns `traceback` (HYG-01 deferred, no new leak) |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Reply echoes request data into `outcome` (item ids, paths) | Information disclosure | `item` is the caller's own id/index/path; never put the `_mcp` secret key or whole request bodies in `outcome`; `export_*` items are file paths the caller supplied |
| False success that hides a rollback (repudiation of what actually happened) | Repudiation / Tampering | this phase's purpose; 409 stays load-bearing |
| `str(exc)` of a .NET exception containing a file path | Information disclosure | accepted per D-07; Phase 6 audit must still scrub (AUDIT-08) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `Pending`/`Error` TransactionStatus will not occur in practice because `SetForcedModalHandling(False)` is set | Pitfall 5 | classification maps any non-committed to 409 `rolled_back`; wrong label for a rare status, verbatim `transaction_status` still shown |
| A2 | `Transaction.GetStatus()` is safe to call after Commit/RollBack in the 500 branch (only known from a search summary of rvtdocs) | Pitfall 4 | wrap in try/except; fall back to `null` |
| A3 | Autodesk's IFC export rolls back its transaction in the official sample; repo commits and that is acceptable for now | Pitfall 6 | none for this phase; a later phase might switch to rollback to avoid persisting exporter side effects |
| A4 | Under IronPython 3 `str(status)` of the enum yields `"Committed"`/`"RolledBack"` | Code examples | verified live once for `Committed` in the param-write debug notes; `RolledBack` text rests on the fake world and the debug doc |
| A5 | Recommended mapping `item` = input index for creation routes (both lists) and input element id for id-taking routes | Open question 5 | discretionary under CONTEXT; changing it later costs the Phase 6 schema |

## Open Questions

1. **Instance created but secondary step failed (`place_family` properties, `create_duct` dimensions, `detail` line style, `create_level` name).** 
   - Known: the element exists after commit; today these are reported as `success` plus a side list.
   - Unclear: is that `partial` (1 requested, 1 succeeded, N failed -> `partial`) or `success` with warnings? D-04's rule yields `partial` automatically if failed secondary items are listed.
   - Recommendation: list each failed secondary step in `outcome.failed` with `item` = the step name (e.g. `"line_style"`), `succeeded` = the created element id; result is `partial`. Confirm with the user because it changes `success` to `partial` for routes that never warned before.
2. **Should `/execute_code/` carry `outcome`?** D-03 says every mutating route; its pinned key set (`test_routes_view_code_identity.py:1175`) will need `"outcome"`. Recommend yes (`requested: null`, `succeeded: []`, `failed: []`, real status) so Phase 6 reads one schema.
3. **`/activate_document/` and `/set_active_view/`** change UI state, not the model. Recommend `outcome` with `transaction_status: null` for `set_active_view` (it is guarded as a mutation) and leave `activate_document` as is (it already returns a verified observation) unless the audit phase wants uniformity.
4. **500 replies: carry `outcome` or not?** Recommend yes for transacting routes (real `transaction_status`, `succeeded: []`) because a post-commit exception is a committed-but-reported-failed lie; if time-boxed, restrict to routes that read state after commit.
5. **Meaning of `item`.** Recommend: id-taking routes (`tag_elements`, `tag_walls`, `delete_elements`, `transform_elements`, `modify_element` -> parameter name) use the input element id; creation routes (`create_line/surface/level/grid/framing/room_separation`) use the 0-based input index in BOTH `succeeded` and `failed`, keeping created ids in the legacy `created[]`. Consider an additive `"item_kind": "element_id" | "index" | "parameter" | "path"` key so Phase 6 never guesses; it is cheap now and "costly" later (D-03 reversibility).
6. **IFC export: commit vs rollback of the exporter's transaction** (Pitfall 6). Out of scope; record for the user.
7. **`create_mep_system` empty commit then 500.** Recommend rolling back instead of committing when `new_system` is None; confirm.

## Sources

### Primary (HIGH confidence) - read this session
- `revit_mcp/utils.py:112-135`, `revit_mcp/editing.py` (whole route file region), `tools/utils.py` (whole), all route modules listed in the inventory (relevant regions), `bridge.py` non-200 handling, `scripts/conventions.py` (whole), `tests/unit/test_conventions.py`, `tests/unit/test_format_response.py:140-200`, the four `test_routes_*_identity.py` fixtures and pinned key sets, `tests/unit/test_registration.py:236-270`, `.planning/RELEASES.md` R2 note, `.planning/research/PITFALLS.md` Pitfall 11, `.planning/debug/param-write-rolls-back.md`, project memory notes.
- Local runs: AST scan of `.Commit()` calls; `uv run pytest tests/unit -q -x` baseline.

### Secondary (MEDIUM confidence)
- https://rvtdocs.com/2025/7efa4eb3-8d94-b8e7-f608-3dbae751331d - `Document.Export(String, String, IFCExportOptions)` returns Boolean; throws `ModificationOutsideTransactionException` when no open transaction (fetched).
- rvtdocs.com `Document.Export(String, String, ICollection<ElementId>, DWGExportOptions)` returns bool; rvtdocs `TransactionStatus` members (Uninitialized, Started, RolledBack, Committed, Pending, Error); `Transaction.Commit` remarks pointing to `GetStatus` - via search summaries, pages not fetched in full.

### Tertiary (LOW confidence)
- aps.autodesk.com IFC-export sample that rolls back after export (search summary only).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies; all helpers in-repo.
- Architecture: HIGH - transport and renderer read directly; decisions fixed by CONTEXT.
- Pitfalls: HIGH for repo-internal ones (fixtures, pins, post-commit reads); MEDIUM for Revit-API behaviour (export Boolean cited; Pending/Error rarity assumed).

**Research date:** 2026-10-23
**Valid until:** 2026-11-22 (repo moves with other phases; re-grep `.Commit()` and the pinned-key tests at plan time, since Phase 5 work touches `startup.py` and may touch the same test files)

## Project Constraints (from CLAUDE.md)

- Two-runtime rule: Revit half is IronPython 3.4-level: no f-strings, no `async`, no `pathlib`, no modern typing, relative sibling imports (`from .utils import ...`), encoding cookie on line 1; helper shared logic goes in `revit_mcp/textutils.py` / `trust.py`.
- Every document mutation runs in a transaction and `suppress_warnings(t)` comes immediately after `t.Start()` (`Save`/`SaveAs` outside any transaction).
- Never touch `ElementId.Value` / `.IntegerValue` or `DB.ElementId(int)`; use `get_element_id_value()` / `make_element_id()`.
- POST bodies are `text/plain`, parsed with `parse_request_data()`.
- Route handlers never raise; wrap in `try/except` and return `routes.make_response(data=..., status=...)`; status conventions 400/404/500/503 (and 409 rolled_back).
- A dict is an error only with a truthy `error` key or status in `error/failed/failure/exception`; do not add implicit error signals to `format_response`. Tool functions always return `str` via `format_response`.
- Never `print()` in `main.py`/`bridge.py`; Revit-side logging via `logging.getLogger(__name__)`.
- Dimensions in millimeters; names via `sanitize_string()` / `get_element_name()`.
- Tool docstrings are the API contract (purpose, scope, return shape, limitations, `Args:` incl. `ctx`): batch-tool docstrings should mention `partial`/`failed` replies.
- Adding a capability = 2 files + `tool_manifest.txt`; this phase adds none.
- Never import one `revit_mcp/` domain from another.
- After editing `revit_mcp/`, a full Revit close/reopen is required before live testing (never pyRevit Reload).
- `uv run pytest tests/unit` before every commit; no CI.
- Release checkpoint: at phase close, read `.planning/RELEASES.md` and offer R2 via `AskUserQuestion` before moving on; the offer is not permission to build/publish/push/tag.
- Project memory: `rolled_back` 409 is load-bearing; live gates are human-run and write steps are one-shot; execute sequentially with `use_worktrees=false` and commit by explicit pathspec on a dirty tree.
