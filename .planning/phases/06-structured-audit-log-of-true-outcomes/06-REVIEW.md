---
phase: 06-structured-audit-log-of-true-outcomes
reviewed: 2026-10-25T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - audit.py
  - bridge.py
  - main.py
  - tools/utils.py
  - deploy/build-payload.cmd
  - tests/test_phase6_live_audit.py
  - tests/unit/audit_support.py
  - tests/unit/conftest.py
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-10-25
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

I reviewed the audit module, the `_audit`/`_dispatch` hook in `bridge.py`, the wrapper install in `main.py`, the `Audit: call_id` line in `format_response`, the payload copy line, the live gate script and the shared test helpers. Three of the claims I checked held up under the code: stdout stays clean (the only output paths are the log file and one stderr line), the secret is redacted before every cut, and no code path I traced lets the writer raise into a call. `build-payload.cmd` ships `audit.py`.

I found no BLOCKER. Three WARNINGs are real correctness gaps, and the existing tests do not catch them:

- The roll-over size check defeats the writer's lone-surrogate protection.
- A failed read that answers HTTP 200 is logged as `success`.
- `NaN` and `Infinity` can reach the log as invalid JSON.

I confirmed the first and third by running the code, and the second against the route source.

## Warnings

### WR-01: A lone surrogate in any entry after the first drops that entry (UnicodeEncodeError in shouldRollover)

**File:** `audit.py:807-812` (with `audit.py:802-805`, `audit.py:761`)
**Issue:** `_open` writes with `errors="backslashreplace"` so that "a lone surrogate must not raise". `shouldRollover` then runs `record.getMessage().encode("utf-8")` in strict mode. A line holding a lone surrogate raises `UnicodeEncodeError` there. `BaseRotatingHandler.emit` catches it and calls `handleError`, which writes one stderr line and drops the entry. The first line of a segment escapes the bug only because `size > 0` short-circuits the encode.

`serialize_entry` uses `ensure_ascii=False`, so a lone surrogate survives into the line. Strings that come from Revit replies reach entries (document titles and paths, `failed[].reason`, `revit_failures`), and `httpx` `response.json()` uses the stdlib parser, which accepts `"\ud800"`. A mutation could therefore lose its audit entry because of one odd element or document name.

I reproduced this. After writing `{"a":"x"}`, the line `{"a":"lone\ud800"}` was dropped with `UnicodeEncodeError`, and the following line was written normally.

**Fix:** Measure the size the way the file is written.
```python
def shouldRollover(self, record):
    try:
        size = os.path.getsize(self.baseFilename)
    except OSError:
        size = 0
    line = record.getMessage().encode("utf-8", "backslashreplace")
    return size > 0 and size + len(line) + 1 > self.max_bytes
```
Alternatively, serialize with `ensure_ascii=True` (which also fixes WR-03 if combined with sanitizing). A unit test should write a second line that contains `"\ud800"` and assert that it lands in the file.

### WR-02: A read that answers HTTP 200 with an error payload is audited as `success`

**File:** `audit.py:430-438` (`_outcome`)
**Issue:** The "completed read as success" rule fires for any 200 on a non-mutation route. The only reply statuses recognized before it are `success`, `partial`, `failed` and `rolled_back`. The routes also signal failure in two other ways at HTTP 200:

- A top-level `{"status": "error"}`. Seen in `revit_mcp/colors.py` lines 642, 656, 915, 950, 1030 and others, and in the `code_execution.py:240` reply shape.
- A truthy `error` key. This is the shape `format_response` treats as an error, per the CLAUDE.md invariant.

`/list_category_parameters/` is one of the seven open POST reads, so `mutation` is False. It returns `routes.make_response(data=result)`, a 200, when `list_category_parameters` returns `{"status": "error", "message": "Category ... not found"}`. The model is shown `=== ERROR DETAILS ===`, while the audit entry says `outcome: "success"`.

For the same reply on a mutating route the label is `unrecognized`, not `error`, so the audit and what the model saw disagree there too. An audit log of "true outcomes" should not call a failed read a success. The reader is also told that a successful read's id is withheld (D-07), so no call id appears to flag the discrepancy.

**Fix:** Before the `http_status == 200 and not mutation` rule, classify reply-level errors:
```python
if isinstance(status, str) and status.lower() in ("error", "failure", "exception"):
    return "error", None, None
if body.get("error"):
    return "error", None, None
```
Do the same check before `unrecognized` for mutating routes. Keep `partial` out of this set.

### WR-03: NaN and Infinity values reach the log as invalid JSON

**File:** `audit.py:399-403` (`_scalar`) and `audit.py:761` (`serialize_entry`)
**Issue:** `_shape_value` guards non-finite floats (`math.isfinite`), but `_scalar` returns any float unchanged. `_scalar` is used for `succeeded` items, `failed[].item` and the documents-changed descriptor fields. `serialize_entry` calls `json.dumps` with the default `allow_nan=True`, so such a value is written as a bare `NaN` or `Infinity`. That is not valid JSON, and strict consumers (`jq`, JS `JSON.parse`, most log shippers) reject the whole line. The stdlib parser in `httpx` accepts these tokens in a reply, so the value can arrive from Revit.

I confirmed `"NaN" in line` is True for `succeeded=[float("nan")]`. The reader helpers in the tests use stdlib `json.loads`, which accepts `NaN`, so the tests would not catch this.

**Fix:** Make `_scalar` reuse the same rule as `_shape_value`:
```python
if isinstance(value, float):
    return value if math.isfinite(value) else _type_name(value)
```
In `serialize_entry`, pass `allow_nan=False` inside a try, and fall back to a sanitized re-serialization on `ValueError`, so a rare bad value cannot cost the whole entry.

## Info

### IN-01: A JSON-looking user_request is not stored verbatim

**File:** `audit.py:258-267` (`_json_text`)
**Issue:** FastMCP json-parses the string before the validator runs, and `_json_text` re-serializes it with `json.dumps(value, ensure_ascii=False)`. A message such as `{"a":1}` is stored as `{"a": 1}`. A bare `1e3` becomes `1000.0`, `"yes"` with its quotes becomes `yes`, and `null` is recorded as missing. The log is labelled "as reported by the assistant", so this is minor. The text does not match the original character for character, and `user_request_length` is computed on the re-serialized text.
**Fix:** Accept and document the limitation in the schema notes. Real-prompt text is rarely JSON.

### IN-02: Arguments are held by reference and shaped at call end

**File:** `audit.py:249-253` (`new_call`), `audit.py:740` (`build_entry`)
**Issue:** `CallState.args` is a shallow copy of the kwargs dict, and `shape_args` runs when the entry is built, after the tool has finished. A tool that mutated a list or dict argument in place would change what the audit records. I grepped `tools/*_tools.py` and none does today, so this is a latent hazard only.
**Fix:** Shape or deep-copy the args at wrapper entry (cheap, since they are capped anyway), or add a conventions test that bans in-place mutation of tool arguments.

### IN-03: prune() can delete another live server's active segment on POSIX

**File:** `audit.py:921-937`
**Issue:** The total-size pass removes the oldest files regardless of whether another running server holds them open. On Windows `os.remove` fails and the file is skipped, which is the documented behaviour. On POSIX the unlink succeeds and the other process keeps writing to an unlinked file. The product is Windows-only, so the practical impact is nil, but the docstring's claim "another live server holds it, so it is skipped" is only true on Windows.
**Fix:** Skip files whose mtime is within the last few minutes, or limit the claim in the docstring to Windows.

### IN-04: Small cleanups

**File:** `audit.py:362-365`, `audit.py:672-673`
**Issue:**
- `_clip` is a pass-through wrapper over `_cut` that adds nothing.
- The `windows_user` keyword argument of `build_entry` shadows the module-level `windows_user()` function. That is harmless because `record_call` passes the call's result, but it is confusing to read.
- On POSIX the audit directory and files are created with the default umask, so the user's recorded requests would be world-readable. `%LOCALAPPDATA%` is per-user on the supported platform, so this is cosmetic.

**Fix:** Rename the argument to `user` (or `windows_user_name`), and drop `_clip` in favour of `_cut`. If the code ever runs off Windows, create the directory with `mode=0o700`.

---

_Reviewed: 2026-10-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
