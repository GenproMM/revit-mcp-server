---
phase: quick-261025-ld5
plan: 01
subsystem: worksharing
tags: [open_model, local-copy, workset-fallback, ironpython3]
requires: []
provides:
  - "open_model opens a workshared central as a new local copy by default"
  - "existing local copy is renamed with a date-time stamp instead of deleted"
  - "one retry with only the axes-and-levels workset open when the all-closed open fails"
affects: [revit_mcp/worksharing.py, revit_mcp/textutils.py, tools/worksharing_tools.py]
tech-stack:
  added: []
  patterns: ["pure decisions in revit_mcp/textutils.py, route stays thin", "retry as a loop inside _open_model (test_phase2_inventory pins the lexical scope)"]
key-files:
  created:
    - tests/unit/test_open_model_local_copy.py
  modified:
    - revit_mcp/textutils.py
    - revit_mcp/worksharing.py
    - tools/worksharing_tools.py
    - tests/unit/test_routes_view_code_identity.py
    - tests/unit/test_tool_forwarding_views.py
    - README.md
decisions:
  - "DD-1 default detach is none in both halves"
  - "DD-2 overwrite_local kept as deprecated tri-state alias; existing_local is the primary parameter"
  - "DD-3 stamp format <stem>_<YYYYMMDD_HHMMSS>.rvt is [ASSUMED]"
  - "DD-4 backup folder is renamed together with the copy, .rvt first, nothing deleted"
  - "DD-5 workset fallback only for the default worksets, exactly one retry"
  - "DD-6 rename/refusal/fallback failures are 500 with outcome; invalid existing_local is 400 without outcome"
metrics:
  duration: "about 25 minutes"
  completed: 2026-10-25
status: complete
plan_head_before: 5050de7a7ae8f594814b9b73a490dc3e1edabef9
commits: 6
actuals:
  tokens: 14300
  tasks: 3
  commits: 6
---

# Phase quick-261025-ld5 Plan 01: open_model defaults to a local copy Summary

open_model now opens a workshared central as a fresh local copy by default, keeps an existing local copy under a date-stamped name instead of deleting it, and retries once with only the "Оси и уровни" workset open when the all-worksets-closed open fails.

Implements the user's 2026-10-25 decision recorded in `07-CONTEXT.md` (Deferred, first bullet). Requirement labels Q1-Q4 are from the plan.

## What changed

- `revit_mcp/textutils.py` (pure, no pyRevit): `AXES_LEVELS_WORKSET_MARKER`, `local_copy_stamp`, `local_backup_dir`, `stamped_local_paths`, `resolve_existing_local_mode`, `pick_axes_levels_workset`.
- `revit_mcp/worksharing.py`: route default `detach` is `none`; `_make_local_copy` takes `existing_mode` ("timestamp" | "overwrite" | "error") and renames instead of deleting by default (`_rename_existing_local`); `_open_model` retries once inside a `for` loop; `_build_workset_config` gained `keep_open`; a `_now()` clock seam.
- `tools/worksharing_tools.py`: `detach="none"`, `overwrite_local: bool = None`, new `existing_local`, `_resolve_existing_local` (deliberate duplicate of the textutils helper), the tool always sends `existing_local` and `overwrite_local = (mode == "overwrite")`, `close_worksets_matching` is sent only when the caller passed a list; docstring rewritten; `list_model_worksets` docstring sentence updated.
- `README.md`: the `open_model` row only.
- Tests: new `tests/unit/test_open_model_local_copy.py`; open_model section of `test_routes_view_code_identity.py` extended (World fake gained `open_errors`; the pinned workset-aware test now sends `detach: "preserve"` explicitly because the default changed by design); `test_tool_forwarding_views.py` updated.

## Decisions

- **DD-1 Default detach.** Value set stays preserve | discard | none; default changed to "none" in the tool signature and in the route `data.get("detach", "none")`. No new alias: "none" already means "do not detach; for a central create a local copy and open that", which is Q1. The plugin-diagnostic skills pass `detach` explicitly and are out of scope.
- **DD-2 Fate of `overwrite_local`.** KEPT as a deprecated tri-state alias (default None = not given) next to the new primary `existing_local: "timestamp" | "overwrite" | "error"` (default None, resolved to "timestamp"). Why: (a) explicit legacy callers keep their meaning: `overwrite_local=true` is an explicit opt-in to the destructive replace, `false` still refuses when a copy exists; (b) mixed-version safety: the tool always sends `overwrite_local = (mode == "overwrite")`, so a Revit that still runs the old route (old default `overwrite_local=True`) refuses with "A local copy already exists" instead of deleting the copy during the window between updating the repo and restarting Revit; (c) removing the parameter would break explicit callers for no safety gain. Rule (same in both halves): `existing_local` given must be one of the three (case-insensitive) and a given `overwrite_local` must equal `(mode == "overwrite")`, else a conflict error; `existing_local` absent: true = overwrite, false = error, absent = timestamp. The route reads `existing_local` first, so the paired `overwrite_local=false` the new tool sends with "timestamp" is consistent, not a conflict. **Known transitional residue:** an OLD MCP server process (session started before the update) talking to a NEW extension still sends `overwrite_local=true` by its old default, which the new route honours as an explicit "overwrite" for `detach="none"` calls. Restart the assistant session together with Revit.
- **DD-3 Stamp format [ASSUMED].** Revit's exact naming for "Append timestamp to existing copy" could not be confirmed offline (no lookup possible at planning time and none attempted during execution). Used `<stem>_<YYYYMMDD_HHMMSS>.rvt`, collision suffix `_2`, `_3`, ... (bounded at 100). Manual step (г) below compares it with Revit's native dialog.
- **DD-4 Backup folder.** An existing `<stem>_backup` folder is renamed to `<newstem>_backup`, so the renamed copy keeps its own backup folder and the new local starts clean. Order: the .rvt first (the rename most likely to fail when the file is open in Revit; nothing has changed then); then the folder; if the folder rename fails the .rvt is renamed back and the error says whether the restore worked and where every file is. Nothing is deleted on the timestamp path. If CreateNewLocal fails after a successful rename there is no restore; the error reply carries `renamed_existing_local` and names where the old copy went.
- **DD-5 Workset fallback eligibility.** Only when the model is workshared AND the caller did not supply `close_worksets_matching` (key absent or null). An explicit list, even `["__ALL_USER_WORKSETS__"]`, keeps the old behaviour with no retry. Trigger: the first open raised or returned no document. Exactly one retry, on the same path (the local copy already created: no second CreateNewLocal, no second rename). Matching is lower-case, "_" as space, whitespace collapsed, substring "оси и уровни"; an exact normalised match is preferred, otherwise the first match in `GetUserWorksetInfo` order. The tool omits `close_worksets_matching` when the caller passed None so the route can tell "default" from "explicit".
- **DD-6 Statuses.** Rename failure, `existing_local="error"` with an existing copy, and fallback failures are 500 with `outcome` (same class as the old local-copy and open failures). Invalid or conflicting `existing_local` / `overwrite_local` is 400 with no `outcome` (validation before any action).

## Reply fields (workshared path only)

`document_title`, `detach`, `requested_detach`, `is_workshared`, `is_local_copy`, `local_path`, `existing_local`, `replaced_existing_local`, `renamed_existing_local` (`{from, to, backup_from, backup_to}` or null), `worksets_applied` (`all_user_closed` | `axes_and_levels_open` | `caller_patterns`), `fallback_workset` and `fallback_reason` after a retry, `worksets_opened` / `worksets_closed`, `activated`. The non-workshared reply key set is unchanged.

## Test results

- Task 1 gate (`test_open_model_local_copy`, `test_textutils`, `test_conventions`, `test_registration`): `521 passed, 3 skipped in 3.51s`.
- Task 2 gate (`test_routes_view_code_identity`, `test_phase2_inventory`, `test_phase5_gate_wiring`, `test_conventions`, `test_open_model_local_copy`): `1365 passed, 3 skipped in 7.05s`.
- Task 3 focused (`test_tool_forwarding_views`, `test_conventions`, `test_phase2_inventory`): `1152 passed, 3 skipped in 5.38s`.
- Full suite `uv run pytest tests/unit -q`: `6361 passed, 3 skipped in 80.85s (0:01:20)`.
- `git diff --quiet -- tests/unit/tool_manifest.txt`: unchanged. `data.get("detach", "none")` appears once; `os.remove` appears once (the explicit overwrite branch).

Commits (6, measured against `plan_head_before`): b12e31f, 7f36395, b1416db, 3971376, 9f4982c, eb05c2c. The Task 1 GREEN commit was amended once before any later work: the Write tool had turned the `\u` escapes of the Cyrillic marker into literal Cyrillic, and the plan requires `\u` escapes in `revit_mcp/`.

## Deviations from Plan

None in behaviour. Execution notes:

- **[Rule 1 - Bug, self-caught]** Literal Cyrillic had slipped into `AXES_LEVELS_WORKSET_MARKER` (and the test constant `AXES`); replaced by `\u` escapes and the Task 1 commit amended (local, unpushed).
- The `open_model` fake in `test_routes_view_code_identity.py` got an extra test not listed in the plan (backup-folder rename failure restores the .rvt) and one for "first open returns no document" triggering the retry.

## Known Stubs

None.

## Threat Flags

None. No new endpoint or trust boundary; the gate preamble on `/open_model/` is untouched (`test_phase5_gate_wiring` green).

## Ручная проверка (живой Revit)

Живая проверка НЕ выполнялась, push, публикация и релиз тоже не выполнялись. Проверять на ОДНОРАЗОВОЙ центральной модели.

**Предусловия**
- Полный перезапуск Revit после изменения `revit_mcp/` (кнопка Reload не годится, она может уронить Revit).
- Новая сессия ассистента, чтобы сервер MCP был новым (иначе остаётся переходный случай из DD-2: старый сервер шлёт `overwrite_local=true`).
- `Get-NetTCPConnection -LocalPort 48884 -State Listen` возвращает ровно одну строку.
- Dev-секрет настроен (`uv run python scripts/dev_secret.py`), сервер запущен из репозитория через `uv run main.py`.

**(а) Локальной копии нет.** Вызвать `open_model(file_path=<центральная>)` без `detach`. Ожидается: `is_local_copy: true`, `detach: "none"`, `local_path` = `Documents\<Центральная>_<пользователь>.rvt`, `existing_local: "timestamp"`, `renamed_existing_local: null`, `worksets_applied: "all_user_closed"`, файл копии появился. Закрыть документ без синхронизации.

**(б) Повторить тот же вызов.** Ожидается: `renamed_existing_local` с `from`, `to`, `backup_from`, `backup_to`; старый файл и папка `_backup` переименованы со штампом, новая копия создана по исходному пути, ничего не удалено (сравнить список файлов в папке до и после). Затем повторить вызов, НЕ закрывая документ: ожидается ошибка переименования с путём и причиной, старый файл на месте, новая копия не создана.

**(в) Рабочие наборы.** Записать `worksets_applied`. Если Revit не открыл модель со всеми закрытыми наборами, ожидается `axes_and_levels_open` с `fallback_workset` и `fallback_reason`. Принудительно вызвать сбой безопасно нельзя, поэтому фиксируется наблюдаемый вариант. Если набора с «Оси и уровни» в названии нет, ожидается ошибка с текстом первой неудачи и пояснением, что повторять не с чем.

**(г) Сверка штампа с Revit.** Открыть ту же центральную через диалог Revit с «Создать новый локальный» и «Добавить штамп даты и времени к существующей копии». Записать фактическое имя переименованной копии и судьбу папки `_backup`. При расхождении с `<имя>_<YYYYMMDD_HHMMSS>.rvt` завести быструю задачу на выравнивание формата (формат в DD-3 помечен [ASSUMED]).

## Self-Check: PASSED

- Files exist: textutils.py, worksharing.py, worksharing_tools.py, test_open_model_local_copy.py, README.md (all modified or created and committed).
- Commits found in `git log`: b12e31f, 7f36395, b1416db, 3971376, 9f4982c, eb05c2c (6 = `git rev-list --count` from `plan_head_before`).
- Full unit suite green; manifest unchanged; no files outside the plan's list were committed.
