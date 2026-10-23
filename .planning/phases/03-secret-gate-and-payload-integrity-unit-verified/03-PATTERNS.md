# Phase 3: Secret gate and payload integrity (unit-verified) - Pattern Map

**Mapped:** 2026-10-23
**Files analyzed:** 22 (new/modified)
**Analogs found:** 21 / 22 (all analog paths verified git-tracked)

Note: CONTEXT.md uses old phase numbering; live wiring is Phase 5. Do NOT edit `startup.py` (test_phase2_inventory.py:597 forbids a handler wrapper). Phase 3 is inert.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `revit_mcp/trust.py` | utility (pure helper) | transform | `revit_mcp/textutils.py` | exact |
| `revit_mcp/integrity.py` | utility (read-only file reader) | file-I/O | `revit_mcp/textutils.py` (dialect) + `deploy/gate.py` (OSError-tolerant read) | role-match |
| `bridge.py` (load_secret, with_envelope; additive) | service (client half) | request-response | `bridge.py::_send` (836-857) | exact |
| `deploy/secret_tool.py` | build tool | file-I/O | `scripts/build_contrib_kit.py` | role-match |
| `deploy/make_manifest.py` | build tool | batch/transform | `scripts/build_contrib_kit.py` (hashlib, `__main__`) | role-match |
| `deploy/config.cmd` | config | - | itself (lines 26, 42) | exact |
| `deploy/publish-extension.cmd` | config/build script | batch | itself (lines 51-71) | exact |
| `deploy/build-payload.cmd` | config/build script | batch | itself (lines 105-125) | exact |
| `deploy/gate.py` | test/gate | request-response | itself (lines 29-41 `_expected_tools`) | exact |
| `.gitignore` | config | - | itself (append-only) | exact |
| `scripts/dev_secret.py` | utility script | file-I/O | `scripts/build_contrib_kit.py` | role-match |
| `CLAUDE.md` | doc | - | itself ("Commands" paragraph mentioning `textutils.py`) | exact |
| `tests/unit/test_trust_envelope.py`, `test_trust_secret.py`, `test_trust_integrity.py`, `test_trust_listeners.py` | test | transform | `tests/unit/test_textutils.py` | exact |
| `tests/unit/test_trust_dialect.py` | test | transform | `tests/unit/test_textutils.py` (IronPython stand-in 156-188) + `test_conventions.py` | role-match |
| `tests/unit/test_integrity_reader.py` | test | file-I/O | `tests/unit/test_textutils.py` + tmp_path fixtures | role-match |
| `tests/unit/test_make_manifest.py` | test | batch | `tests/unit/test_payload_ships_root_modules.py` | role-match |
| `tests/unit/test_secret_pipeline.py` | test (regex over .cmd text) | transform | `tests/unit/test_payload_ships_root_modules.py` | exact |
| `tests/unit/test_bridge_secret_client.py` | test | request-response | `tests/unit/test_local_bridge_transport.py`, conftest.py autouse guard | role-match |
| `tests/unit/test_format_response.py` (edit, 401 pair) | test | request-response | rolled_back pair, lines 149-188 | exact |
| `tests/unit/test_registration.py` (edit helper sets) | test | transform | lines 238, 256 | exact |

## Pattern Assignments

### `revit_mcp/trust.py` (utility, transform)

**Analog:** `revit_mcp/textutils.py`

**Header + imports + runtime aliases** (lines 1-37): encoding cookie on line 1, module docstring stating "free of any pyRevit import ... registers no routes", then:
```python
# -*- coding: utf-8 -*-
import json
import logging

if bytes is str:  # IronPython 2.7 / Python 2
    _TEXT_TYPE = unicode  # noqa: F821 - defined only on Python 2
    _BYTES_TYPE = str
else:  # IronPython 3 / CPython 3
    _TEXT_TYPE = str
    _BYTES_TYPE = bytes
```
Do not re-declare the alias block. Use `from .textutils import _TEXT_TYPE, _BYTES_TYPE, parse_request_data` (relative, never flat; CLAUDE.md). `trust.py` adds `import hashlib`; it must NOT import `logging` (SEC-06: no logging in trust code).

**Body-parse seam** (`textutils.py:257-261`, the only permitted path to parse the envelope):
```python
    if isinstance(data, _BYTES_TYPE):
        data = data.decode("utf-8")
    if isinstance(data, _TEXT_TYPE):
        return json.loads(data)
    return data
```
`split_envelope(raw)` calls `parse_request_data(raw)` inside try/except; unparseable -> `({}, None)`. Build the clean payload with `dict((k, v) for k, v in data.items() if k != "_mcp")`, never `{**data}`.

**Core pattern:** use RESEARCH.md Pattern 2 (hash-then-XOR, `bytearray(digest)`, no early return in loop, `except Exception: return False` with no text) and Pattern 4 (`evaluate_integrity` three-state). Helpers: `check_secret`, `auth_failure(reason) -> (body, 401)`, `integrity_failure(files) -> (body, 423)`, `classify_listeners`, `gate_applies(method)`.

**Error handling:** `textutils.py:54-61` style (`try ... except Exception: return <safe value>`), but with no message.

---

### `revit_mcp/integrity.py` (utility, file-I/O, read-only)

**Analog:** `revit_mcp/textutils.py` for dialect; `deploy/gate.py:37-41` for OSError-tolerant read:
```python
    try:
        with open(MANIFEST, encoding="utf-8") as handle:
            ...
    except OSError:
        return None
```
In `integrity.py` use `except (IOError, OSError) as exc` and `getattr(exc, "errno", None) == errno.ENOENT` (2.7/3.4 safe); open files `"rb"` only; hash `data.replace(b"\r\n", b"\n")`. One shared `hash_normalized(bytes)` imported by `deploy/make_manifest.py`. No `pathlib`, `os.scandir`, `subprocess.run`, f-strings. Only read modes; no writes (INTG-03 AST test).

---

### `bridge.py` (additive: `load_secret`, `with_envelope`)

**Analog:** `bridge.py::_send` (836-857). Excerpt (850-855) that must stay byte-identical (inert guarantee test):
```python
        response = await client.post(
            endpoint,
            content=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=timeout,
        )
```
Imports already present (105-116): `os, json, re, subprocess, sys, ...`; add nothing from `revit_mcp` (payload does not ship it; build-payload.cmd:109-118). Do not call from `_send`, do not reword the module docstring (pinned by test_serialization_scope_docs.py), no `print()`. Module-level constants `ENVELOPE_KEY`, `SECRET_FILE_NAME`; type hints are fine here (CPython side).

---

### `deploy/secret_tool.py`, `deploy/make_manifest.py`, `scripts/dev_secret.py` (CPython build tools)

**Analog:** `scripts/build_contrib_kit.py` (tracked). Pattern: stdlib-only, `argparse`, `hashlib.sha256` over `io.open(path, "rb")`, `print("Built: {}".format(...))`, `if __name__ == "__main__": main()` (lines 55-80). `deploy/` and `scripts/` are not dialect-checked, so `secrets`, `subprocess`, f-strings are allowed. `make_manifest.py` must `sys.path.insert(0, repo)` before `from revit_mcp.integrity import hash_normalized` (pyRevit CPython ignores PYTHONPATH). Exit non-zero with an explicit message on failure (publish must fail loud). Create secret with `os.open(O_CREAT|O_EXCL)`, ASCII, no trailing newline; never print the value.

Tool header style to copy from `deploy/gate.py:1-10`: encoding cookie plus a raw docstring with usage line.

---

### `deploy/publish-extension.cmd` (edit; file is `w/crlf`, preserve CRLF; user has uncommitted edits, use targeted Edit only)

**Analog:** itself, lines 62-71:
```bat
robocopy "%REPO%\revit_mcp" "%DEST%\revit_mcp" /E /XJ /XD __pycache__ /XF *.pyc ^
    /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (echo ERROR: publish failed. & exit /b 1)
...
robocopy "%~dp0." "%MCP_SHARE_ROOT%\install" install.cmd update.cmd find-python.cmd check_routes_config.py /NFL /NDL /NJH /NJS /NP >nul
```
Required order: robocopy with `/XF *.pyc _bridge_secret _manifest.json` < stage secret into `%DEST%\revit_mcp\_bridge_secret` < `make_manifest.py` call < installer robocopy. Error idiom: `|| (echo ERROR: ... & exit /b 1)` (lines 35-39). `call "%~dp0config.cmd" || exit /b 1` (line 19) already loads config.

### `deploy/build-payload.cmd` (edit)

**Analog:** itself, lines 109-118 (explicit `copy /y` list) and 125 gate call:
```bat
copy /y "%REPO%\bridge.py"          "%BUILD%\app\" >nul || exit /b 1
...
"%MCP_PYEXE%" "%BUILD%\app\gate.py" || (echo ERROR: acceptance gate failed. & exit /b 1)
```
Stage `app\_bridge_secret` after line 118 and before the line 132 `/MIR` publish. Beware: `test_payload_ships_root_modules.py:20` regex only matches `copy /y "%REPO%\<name>.py"` lines; a staged secret copy must not match (it is not a `.py`).

### `deploy/config.cmd` (edit)

**Analog:** itself, lines 26 and 42 (`if not defined X set "X=default"`):
```bat
if not defined MCP_EXT_NAME set "MCP_EXT_NAME=revit-mcp-server.extension"
```
Add `if not defined MCP_SECRET_FILE set "MCP_SECRET_FILE=%MCP_SHARE_ROOT%\_build\bridge_secret"` (default is discretion; Open Question 1). File is `w/lf`; keep ASCII.

### `deploy/gate.py` (edit)

**Analog:** itself, `_expected_tools` + the `MANIFEST=absent (skipping ...)` branch (lines 29-72): optional check that degrades to a printed skip when input absent, hard `assert` with actionable message when present and wrong; add a similar optional pair check (`MCP_SECRET_FILE` defined and `HERE/_bridge_secret` byte-equal) printing e.g. `SECRET=ok`. Keep `GATE_OK` last. Gate runs under the payload interpreter: `asyncio.run(main())` at module end, `sys.path.insert(0, libs)` at line 18.

### `.gitignore` (edit, append-only; user has uncommitted edits)

Tail currently ends with `workspace-mobile.json` (verified). Append `_bridge_secret` and `_manifest.json` lines.

### `CLAUDE.md` (edit)

Update the "no lint/format config" paragraph sentence "Pure helpers that both halves need go in `revit_mcp/textutils.py`, which imports nothing from pyRevit" to name `textutils.py` and `trust.py`. Do not touch the pinned serialization-scope sentences.

---

### Tests

#### `tests/unit/test_trust_*.py` (analog `tests/unit/test_textutils.py`)

Header style (test_textutils.py:18-23): encoding cookie, docstring ending "Needs no Revit.", `import pytest`, `from revit_mcp.trust import (...)`. `conftest.py` puts `REPO_ROOT` on `sys.path`, so `revit_mcp.trust` imports directly.

IronPython stand-in pattern (test_textutils.py:156-188) to copy for `test_trust_dialect.py`: a small class mimicking the hostile runtime, a "guard the guard" test proving the stand-in reproduces the failure, then behaviour tests with `monkeypatch.setattr("revit_mcp.trust.<name>", Stand())`:
```python
class _IronPython3Json(object):
    def loads(self, payload, *args, **kwargs):
        if not isinstance(payload, str):
            raise TypeError("the JSON object must be str, not {!r}".format(payload.__class__.__name__))
        return json.loads(payload, *args, **kwargs)
...
def test_parses_bytes_without_handing_them_to_json_loads(monkeypatch):
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())
    assert parse_request_data(b'{"a": 1}') == {"a": 1}
```
Source-text assertions (test_textutils.py:123-145: `open(path, encoding="utf-8")`, regex over source) are the template for AST/no-logging/no-write guards.

#### `tests/unit/test_secret_pipeline.py` and `test_make_manifest.py` (analog `test_payload_ships_root_modules.py`)

Lines 16-20, 40-43 pattern:
```python
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD = os.path.join(REPO, "deploy", "build-payload.cmd")
_COPY = re.compile(r'^\s*copy\s+/y\s+"%REPO%\\([A-Za-z0-9_]+)\.py"', re.IGNORECASE)

def _copied_from_repo_root():
    with open(BUILD, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    return set(m.group(1) for m in map(_COPY.match, lines) if m)
```
Include a vacuity guard (`assert "main" in copied`) like line 50-52. For .cmd line-order assertions read the file, find line indexes of the robocopy `/XF`, secret stage, `make_manifest.py`, installer robocopy, assert strictly increasing. `test_make_manifest.py` builds a tmp git repo (`skipif(shutil.which("git") is None)`).

#### `tests/unit/test_bridge_secret_client.py`

`tests/unit/conftest.py` has an autouse fixture (line ~20+) that stubs `bridge.listener_snapshot` so no test reaches live Revit; keep using plain `import bridge`. Inert guarantee: assert `_send` still posts exactly `json.dumps(data).encode("utf-8")` (bridge.py:852) using `httpx.MockTransport`; see `test_local_bridge_transport.py` for the transport idiom.

#### `tests/unit/test_format_response.py` (edit): 401 pair

**Analog:** lines 149-188. Copy the commented header block and both tests; adapt per Conflict C4:
```python
def test_rolled_back_409_reaches_the_model_as_a_visible_error():
    body = ('Error: 409 - {"status": "rolled_back", ...}')
    out = format_response(body)
    assert out == body

def test_rolled_back_dict_is_not_yet_a_recognized_failure_signal():
    out = format_response({"status": "rolled_back", "transaction_status": "RolledBack"})
    assert "ERROR DETAILS" not in out
```
401 version: (1) `'Error: 401 - {"error": "...", "auth": "mismatch"}'` returns verbatim; (2) the real `auth_failure()` body as a dict DOES render `ERROR DETAILS` (it has a truthy `error` key, `tools/utils.py:169-170`); (3) alarm: `format_response({"auth": "mismatch"})` is NOT an error; plus secret absent from output and 401 distinct from 409/503/412/422/423. Import is `from tools.utils import format_response` (line 18); add `from revit_mcp.trust import auth_failure`.

#### `tests/unit/test_registration.py` (edit)

Add `"trust"` and `"integrity"` to both helper sets: line 238 `for name in ("utils", "textutils", "registry", "identity"):` and line 256 `helpers = {"utils", "textutils", "registry", "identity"}`.

## Shared Patterns

### IronPython 3.4 dialect (all `revit_mcp/` new files)
**Source:** `revit_mcp/textutils.py:1-37`; `scripts/conventions.py` (f-strings, async, `PY3_ONLY_MODULES` incl. `secrets`, flat-import check). Rules: encoding cookie on line 1; `"{}".format`; relative imports; `if bytes is str:` (never `unicode` probe); no `{**d}`, `[*l]`, `bytes.hex()`, `pathlib`, `typing`. `test_conventions.py` auto-enumerates `revit_mcp/*.py` so new files are covered; do not edit `conventions.py` (contrib-kit drift).

### Never raise, never echo secrets
**Source:** `textutils.py:54-61` (swallow, return safe value) + D-05. Applies to `trust.py`, `integrity.py`, `bridge.load_secret/with_envelope` (fixed ValueError text with no body).

### Status-code-as-signal
**Source:** `bridge.py:857` (`"Error: {} - {}".format(status, text)` for every non-200) and `tools/utils.py:150-170`. Distinct codes: 401 auth, 423 integrity; never add implicit error signals to `format_response`.

### Dirty tree discipline
Files with user uncommitted changes: `.gitignore`, `deploy/publish-extension.cmd`, `deploy/install.cmd`, `deploy/*.md`, `README.md`. Use targeted edits, preserve CRLF in `publish-extension.cmd`, commit by pathspec.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `tests/unit/test_trust_dialect.py` AST guards for 3.5+ syntax | test | transform | Only partial analog: `test_conventions.py` parametrized checks; structural `ast.parse(feature_version=(3, 4))` guards plus unpacking/`.hex()` checks are new (use RESEARCH.md Pitfall 8) |
| Secret/manifest generation in `.cmd` (CSPRNG) | build | - | No existing Python call from `.cmd` that generates state; follow `build-payload.cmd:90` style `"%MCP_PYEXE%" script.py args || (echo ERROR ... & exit /b 1)` |

## Metadata

**Analog search scope:** `revit_mcp/`, `deploy/`, `scripts/`, `tests/unit/`, `bridge.py`
**Files scanned:** ~15 read in full or in part
**Tracked check:** `git ls-files --error-unmatch` passed for textutils.py, gate.py, test_textutils.py, test_format_response.py, publish-extension.cmd, build_contrib_kit.py
**Pattern extraction date:** 2026-10-23
