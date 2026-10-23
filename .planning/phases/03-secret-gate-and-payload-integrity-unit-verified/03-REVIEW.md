---
phase: 03-secret-gate-and-payload-integrity-unit-verified
reviewed: 2026-10-23T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - bridge.py
  - deploy/build-payload.cmd
  - deploy/config.cmd
  - deploy/gate.py
  - deploy/make_manifest.py
  - deploy/publish-extension.cmd
  - deploy/secret_tool.py
  - revit_mcp/integrity.py
  - revit_mcp/trust.py
  - scripts/dev_secret.py
  - scripts/probe_ipy_trust.py
findings:
  critical: 0
  warning: 2
  info: 5
  total: 7
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-10-23
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

I reviewed the inert shared-secret gate (`trust.py` plus the `bridge.py` envelope), the payload-integrity reader and generator, the secret tooling and the `.cmd` pipeline wiring. I found no BLOCKER.

What holds up:
- The secret never reaches an exception text, return value, response body or log. `auth_failure` clamps the reason to a fixed set, and `secret_tool` and `gate` messages name only paths and defects.
- The compare is a real fixed-length XOR over SHA-256 digests, with no early exit.
- `check_secret` decides server configuration before it looks at the provided value, so two empty secrets never compare equal.
- `integrity.py` opens files only in `"rb"` mode.
- Manifest keys are validated before any path is opened.
- The IronPython 3.4 and Python 3.8 dialect constraints are respected: no f-strings or annotations on the Revit side, and relative imports.
- Build order in `build-payload.cmd` is correct: the secret is staged before `gate.py`, which checks the pair. In `publish-extension.cmd`, `/XF` excludes `_bridge_secret` and `_manifest.json`, the secret is staged after the copy, and the manifest is written last.
- `.gitignore` covers `_bridge_secret` and `_manifest.json`.

The two warnings are both about failure behaviour at the edges. One is a case where the integrity reader can report tampering when it only lost the share. The other is a publish that can wipe the live extension and then fail.

## Warnings

### WR-01: A share that drops mid-scan is reported as verified_mismatch, not unverifiable

**File:** `revit_mcp/integrity.py:54-61, 95-100, 103-108`
**Issue:** `_read_bytes` treats `errno == ENOENT` as `"absent"`, which `evaluate_integrity` turns into `missing`, and so into `verified_mismatch`.
- On Windows, CPython maps `ERROR_BAD_NETPATH` (53) and `ERROR_BAD_NET_NAME` (67) to `ENOENT`. I confirmed this with `OSError(0, 'x', None, 53).errno == 2`.
- If the UNC share vanishes after `_manifest.json` was read, every listed file comes back `absent`. The scope `os.listdir` also hits ENOENT and is swallowed with `names = []`.
- The result is `verified_mismatch` with all files `missing`. That is the failure D-13 says can never happen: "an unreachable share can never be reported as tampering".
- Phase 5 caches the verdict once at extension load, so one SMB blip would block mutations until Revit restarts.

A manifest-read-first order shrinks the window but does not close it.

**Fix:** Corroborate absence before calling it a mismatch. After the scan, probe that the root is still reachable.
```python
def observe_tree(root, paths):
    ...
    # In check_integrity, after observe_tree:
    if not os.path.isdir(root) or not os.path.isfile(os.path.join(root, MANIFEST_NAME)):
        return unverifiable(REASON_READ_ERROR)
```
Alternatively, treat "scope directory ENOENT" and "all listed files absent" as `unreadable` (`SCOPE_DIR + "/"`) rather than as a legitimate deletion.

### WR-02: Untracked-.py and manifest failures happen after the live extension has been wiped

**File:** `deploy/publish-extension.cmd:61-83` (with `deploy/make_manifest.py:128-134`)
**Issue:** `rmdir /s /q "%DEST%"` and the copy run first. `secret_tool.py stage` and `make_manifest.py` run afterwards.
- `make_manifest` deliberately aborts on an untracked `.py` in `revit_mcp/`, on a missing tracked file, or when `git ls-files` fails. These are likely operator conditions, such as a stray scratch file.
- When it aborts, the script exits 1 with `%DEST%` already emptied and re-populated without `_manifest.json`.
- Every workstation that restarts Revit then loads an extension with no manifest, and with no secret if the stage step is what failed. That fails closed once Phase 5 lands, but today it is a silent outage on a shared path.

The new steps added failure points after the destructive step.

**Fix:** Do the fallible work before wiping the live copy. Either publish to `%DEST%.new`, run stage and manifest there, then swap with rename. Or run a dry-run pre-check before the `rmdir`:
```bat
"%MCP_PYEXE%" "%~dp0make_manifest.py" --repo "%REPO%" --check-only || exit /b 1
```
The check-only mode would run `tracked_files` and the untracked-`.py` comparison against `%REPO%\revit_mcp` instead of `DEST`.

## Info

### IN-01: Secret creation can be observed half-written by a concurrent build

**File:** `deploy/secret_tool.py:88-101`
**Issue:** The `FileExistsError` race is handled, but a second process that sees `os.path.exists(path)` between `os.open(O_EXCL)` and the `handle.write` reads an empty file. It fails with `"... is empty"`. A crash between create and write leaves a permanent empty file that every later run rejects until someone deletes it by hand. This is safe because it fails closed, but the message does not say how to recover.
**Fix:** Add a recovery hint to the empty-file error: "delete it and re-run". Optionally write to a temp file in the same directory and `os.link` or `os.replace` it into place so the file is never visible empty.

### IN-02: Whitespace definitions differ between the file reader and the configured check

**File:** `revit_mcp/trust.py:146-159` versus `213` (and the duplicate at `bridge.py:1115`)
**Issue:** `secret_from_bytes` strips only `" \t\r\n"`. `_blank` and `_configured` call `.strip()`, which also removes `\x0b`, `\x0c`, NBSP and so on. A secret whose last character is one of those can pass the reader's length check and fail `_configured`, which reports `server_not_configured`. Real fleet secrets are `token_urlsafe` and never hit this, but the two rules should agree.
**Fix:** Use `.strip(" \t\r\n")` in `_blank` and `_configured`, or share one constant.

### IN-03: Integrity scope has gaps that a reader of "unexpected" would not expect

**File:** `revit_mcp/integrity.py:101-111` and `deploy/make_manifest.py:122-134`
**Issue:** Both the generator and the verifier look only at `*.py` directly inside `revit_mcp/`, using a case-sensitive `endswith(".py")`.
- Not detected: a `.py` in a subdirectory of `revit_mcp/`, an extra file beside `startup.py`, an importable `.pyd` or `.dll`, or a `Foo.PY` on a case-insensitive filesystem.
- The make_manifest-side "untracked .py" publish check has the same blind spots, so such a file is published and never flagged.
- This is consistent with the documented scope ("revit_mcp/*.py"). It is a drift check, not a tamper defence, since anyone who can write the share can rewrite `_manifest.json` as well.

**Fix:** At minimum, compare with `name.lower().endswith(".py")` on both sides. State the scope limit in the `/status/` documentation Phase 5 writes.

### IN-04: gate.py runs unchecked when MCP_SECRET_FILE is unset, and uses `assert`

**File:** `deploy/gate.py:39-42, 75`
**Issue:** `status == "unchecked"` passes silently. On the build server `config.cmd` always sets the variable, so this is only reachable if someone runs `gate.py` by hand, but then a missing `_bridge_secret` goes unreported. Failure is enforced with `assert`, which is skipped under `python -O`. The gate also checks only byte equality and non-emptiness, not the token shape that `secret_tool.validate_secret_bytes` enforces. The staging step already validates it, so this is redundant rather than wrong.
**Fix:** Optionally treat "unchecked" with a missing artifact as `failed`. Use `if status == "failed": raise SystemExit(message)`, or `sys.exit`, instead of `assert`.

### IN-05: make_manifest mutates sys.path and imports at module import time

**File:** `deploy/make_manifest.py:40-52`
**Issue:** `_hashing()` runs at import, so a broken checkout raises a raw `ImportError` traceback at import instead of the tool's clean `ERROR: ...` and exit 1. It also leaves `sys.path[0]` set for any importer, for example tests.
**Fix:** Import lazily inside `build_manifest`, or wrap the module-level call and turn failure into a `ManifestError` in `main`.

---

_Reviewed: 2026-10-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
