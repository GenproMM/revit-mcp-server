# Stack Research

**Domain:** Trust/identity/integrity foundation for an existing dual-runtime Revit MCP bridge (CPython MCP server ⇄ IronPython 3 pyRevit extension)
**Researched:** 2026-09-21
**Confidence:** MEDIUM-HIGH (stdlib/API claims HIGH via docs; a few pyRevit-internals claims MEDIUM — flagged inline)

This file only covers the four NEW capabilities in `.planning/PROJECT.md`'s Active milestone
(v0.1 "Доверенный мост"): shared-secret auth, payload integrity + self-restore, mutation
serialization, structured audit log — plus the configurable-port question. It assumes
everything in "Validated" already works and does not re-litigate it.

**Governing rule:** every recommendation below is labeled `[CPython]` or `[IronPython 3]`.
A recommendation that is illegal on the IronPython side is worse than none, per the two-runtime
rule in `CLAUDE.md`.

## Recommended Stack

### Core Technologies — zero new dependencies

Every one of the four capabilities is achievable with what's already on disk: CPython 3.11+
stdlib on one side, IronPython 3.4-level stdlib + .NET BCL (`System.*`) on the other. **Do not
add a single new pip package for this milestone.** The workstation constraint (AppLocker/EDR,
file-copy deployment, no network in the payload) makes every new dependency a liability, and
none is needed.

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `hmac` + `hashlib` (stdlib) | CPython ≥3.11 (already pinned) | HMAC-SHA256 request signing, manifest hashing | Already imported nowhere in this repo but ships with CPython; no install step; constant-time compare via `hmac.compare_digest` |
| `System.Security.Cryptography.HMACSHA256` (.NET BCL) | via `clr` in IronPython 3 (`IPY342`) | Verify the same HMAC on the Revit side | IronPython 3.4's `hmac` module (Python-source, ported from CPython 3.4) has **no `compare_digest`** — CPython added it in 3.3 via a C accelerator (`_operator.compare_digest`) that IronPython's pure-Python `hmac.py` never got. `System.Security.Cryptography` is always available (it's part of the .NET Framework Revit itself runs on) |
| `asyncio.Lock` (stdlib) | CPython ≥3.11 | Serialize mutating tool calls at the MCP-server boundary | Exactly matches "one Revit transaction at a time" semantics — mutual exclusion, not a bounded pool; see rationale below |
| `logging` + stdlib `JSONFormatter` (hand-rolled, ~20 lines) or `logging.handlers.RotatingFileHandler` | CPython ≥3.11 | Structured JSONL audit trail | stdlib `logging` already has the file-handler machinery; JSONL is just one `json.dumps(record)+\n` per line — no library earns its keep here |
| `os.replace` (stdlib, POSIX-atomic on the same volume) | CPython ≥3.11, build-time only | Atomic swap when restoring payload files from the network share | Same-volume rename is atomic on NTFS; the risky leg is the network copy, not the final swap (see Capability 2) |

### Supporting Libraries — none required, but note these existing ones

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | ≥0.28.1 (already a dependency) | Carries the new `X-Revit-MCP-Signature` / bearer header | No change to the library, just a new header on the existing `client.post(...)` call in `main.py:_revit_call` |
| `json` (stdlib) | both runtimes | Manifest format, audit record format, HMAC payload canonicalization | Already the wire format for the whole bridge (`parse_request_data`) |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv run pytest tests/unit` | Verify HMAC verification logic, manifest diffing, lock behavior on CPython | All four capabilities' CPython-side logic must land here, testable without Revit — matches the existing "new domain logic belongs on the CPython side" rule in `CLAUDE.md` |
| Manual `/execute_code/` exec harness (documented in `CLAUDE.md` "Known sharp edges") | Exercise the IronPython-side HMAC verify / manifest hash without a full Revit restart | Use for the one function that must run correctly under IronPython 3: the header-verify comparison |

## Installation

```bash
# Nothing to install. Every primitive used below already ships with:
#   - CPython >=3.11 stdlib (hmac, hashlib, asyncio, logging, os, json)
#   - IronPython 3.4 stdlib (hashlib; hmac minus compare_digest)
#   - .NET BCL via clr (System.Security.Cryptography.*), always present in the Revit process
uv sync   # unchanged — no new entries needed in pyproject.toml
```

---

## Capability 1 — Shared-secret authentication on mutating routes

### Reading headers in a pyRevit Routes handler `[IronPython 3]`

pyRevit's `routes.Request` object is passed to every handler and exposes a `.headers` dict
property alongside `.data`, `.method`, `.path`, `.params`, `.query_params`
(docs.pyrevitlabs.io/reference/pyrevit/routes/). Route signatures in this codebase already
receive `(doc, request)` (per `CLAUDE.md`), so reading a header is:

```python
# revit_mcp/<domain>.py  (IronPython 3, Python 3.4 language level)
secret_header = request.headers.get("X-Revit-MCP-Token")  # or whatever the header is named
```

**MEDIUM confidence** on the exact casing/normalization pyRevit applies to header keys (its
own docs don't state whether lookup is case-insensitive) — verify once against a live request
with `?verbose` style logging before hardening the check. This is the one item in this file
that could not be fully verified from documentation alone.

### Static bearer token vs HMAC-over-body — cost comparison

| Approach | CPython side cost | IronPython 3 side cost | Verdict |
|---|---|---|---|
| **Static bearer token**, sent as a header, compared with a constant-time compare | One header add per request (`headers={"X-Revit-MCP-Token": SECRET}` next to the existing `Content-Type` header in `_revit_call`) | One dict `.get()` + one constant-time compare | **Recommended for this milestone.** The PROJECT.md threat model is explicitly "не входит: целенаправленный локальный обход инженером" (not in scope: a deliberate local bypass by an engineer at the console) — the secret's job is to stop *accidental* direct HTTP (e.g., a stray curl, a misconfigured second client), not a hostile attacker who can already read the payload's embedded secret from disk. A static token fully satisfies that bar. |
| **HMAC-SHA256 over the request body**, using the shared secret as key | Compute `hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()` before every POST — cheap (single-digit microseconds for typical route bodies) but must be recomputed per request since bodies differ | Verify with `System.Security.Cryptography.HMACSHA256` — more code (byte-array marshaling from a .NET perspective is more ceremony than a Python string compare), and only pays for itself if you need tamper-evidence of the *body*, not just prove-you-hold-the-secret | **Not justified for this milestone.** The transport is `127.0.0.1`-only (a sibling requirement in the same milestone forces the bind), so there is no network path for a man-in-the-middle to tamper with an in-flight body — the only threat HMAC-over-body defends against that a static token doesn't. Revisit if/when the transport story changes (e.g., a future milestone allows non-loopback binds). |

**Recommendation: static bearer token, compared with a constant-time compare.** This is
simpler on both runtimes, matches the stated threat model exactly, and avoids forcing
`System.Security.Cryptography` byte-marshaling code onto the IronPython side for no
security benefit under a loopback-only transport.

### Constant-time compare — the actual gap

`hmac.compare_digest` **is present in IronPython 3.4's `hashlib`/`hmac` port only if** the
CPython 3.4-era pure-Python fallback is what shipped — but CPython's own 3.4 `hmac.py`
implements `compare_digest` as a pure-Python constant-time loop when the C accelerator isn't
present (see CPython's `Lib/hmac.py` history: the pure-Python fallback has existed since the
function was added in 3.3). Because IronPython3's stdlib is a fork of CPython's `.py` sources
(github.com/IronLanguages/ironpython3, "IronPython 3.4.1 is based off the Python 3.4.10
standard library"), whether `compare_digest` exists there depends on whether that specific
file was ported. **This could not be conclusively verified from public docs** — the IronPython
docs site's `hmac.rst` reference (github.com/IronLanguages/ironpython-docs) lists only `new`,
`update`, `digest`, `hexdigest`, `copy` and conspicuously omits `compare_digest`, which is
the strongest available signal that it is **absent**.

**Action: do not depend on `hmac.compare_digest` being present in IronPython 3.** Use the
.NET-native primitive instead, which is guaranteed present because it's part of the .NET
Framework Revit itself runs on:

```python
# revit_mcp/<domain>.py or a small revit_mcp/auth.py helper — IronPython 3
import clr
clr.AddReference("System")
from System.Security.Cryptography import CryptographicOperations
from System.Text import Encoding

def constant_time_equals(a, b):
    """Constant-time string compare via .NET, since IronPython 3's hmac
    module does not expose compare_digest (CPython added it via a C
    accelerator IronPython never ported; see ironpython-docs/library/hmac.rst,
    which lists new/update/digest/hexdigest/copy and omits it)."""
    a_bytes = Encoding.UTF8.GetBytes(a)
    b_bytes = Encoding.UTF8.GetBytes(b)
    return CryptographicOperations.FixedTimeEquals(a_bytes, b_bytes)
```

`System.Security.Cryptography.CryptographicOperations.FixedTimeEquals(byte[], byte[])` is the
direct .NET equivalent of `hmac.compare_digest` — it exists specifically to prevent
timing-attack-based comparison and predates .NET Core 2.1, so it is present on every .NET
runtime version Revit 2024–2027 could plausibly host. **If `CryptographicOperations` is
unavailable** (older .NET Framework versions predate its introduction — verify against the
actual CLR version pyRevit's IPY342 engine hosts), fall back to a hand-rolled XOR-accumulate
loop over both byte arrays of equal fixed length; do **not** fall back to `a == b` or
`a.Equals(b)`, both of which short-circuit on first mismatch and leak length/prefix via timing.

On the CPython side, `hmac.compare_digest` is unconditionally available (stdlib since 3.3) —
use it there without qualification:

```python
# main.py or a small tools/auth.py helper — CPython >=3.11
import hmac
hmac.compare_digest(candidate_token, expected_token)
```

Note asymmetry: CPython compares with `hmac.compare_digest`, IronPython 3 compares with
`CryptographicOperations.FixedTimeEquals`. This is expected and correct — each side uses its
own runtime's guaranteed-present primitive; there is no shared code path here (`textutils.py`
cannot host this because it imports nothing .NET-specific, and it must stay that way).

---

## Capability 2 — Payload integrity verification with self-restore at startup

### Hashing — `[CPython]` build time, `[IronPython 3]` verify time

Both runtimes have a real `hashlib` with `sha256` — IronPython's docs confirm `md5, sha1,
sha224, sha256, sha384, sha512` are always present constructors
(ironpython-docs/library/hashlib.rst), and this is a pure-algorithm module with no C
accelerator dependency, unlike `hmac.compare_digest`. **Use plain `hashlib.sha256` on both
sides — no .NET fallback needed here**, which is a meaningfully simpler story than Capability 1:

```python
# Build time — CPython, e.g. deploy/build-payload.py
import hashlib, json, os

def build_manifest(payload_root):
    manifest = {}
    for dirpath, _, filenames in os.walk(payload_root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, payload_root).replace("\\", "/")
            with open(path, "rb") as f:
                manifest[rel] = hashlib.sha256(f.read()).hexdigest()
    return manifest

# Ships as payload/manifest.json alongside the extension files
```

```python
# Verify time — IronPython 3, startup.py (runs before pyRevit finishes loading
# revit_mcp/, so this must be dependency-free — no clr.AddReference needed for
# this part, hashlib alone suffices)
import hashlib
import json
import os

def verify_manifest(payload_root, manifest_path):
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    mismatches = []
    for rel, expected_hash in manifest.items():
        full_path = os.path.join(payload_root, rel.replace("/", os.sep))
        try:
            with open(full_path, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
        except IOError:
            mismatches.append(rel)  # missing file counts as a mismatch
            continue
        if actual_hash != expected_hash:
            mismatches.append(rel)
    return mismatches
```

No f-strings used above (IronPython 3.4 language level per `CLAUDE.md`); `"{}".format(...)`
if any interpolation is needed in log messages.

### File-copy / atomicity on Windows UNC shares `[IronPython 3, startup-time]`

The risk to design around: a restore that dies halfway (network drop, permissions, a locked
file because Revit or antivirus has it open) must never leave the extension in a worse state
than the mismatch it was trying to fix.

**Two-phase copy, same pattern as any safe deploy:**

1. Copy each restored file from the UNC share to a **temp name in the same target
   directory** (e.g. `utils.py.restoring`), not to the final name directly. A partial network
   copy then lands on a throwaway filename, never on the file `startup.py` is about to import.
2. Once the full file is copied and its hash re-verified against the manifest, `os.replace(tmp_path,
   final_path)` — this is an atomic rename on NTFS as long as source and destination are on
   the **same volume** (both under the same local extension directory), which they are here
   since only the temp file crossed the network, not the final swap.
3. If any file's restore fails verification twice, **do not partially apply** — abort the
   whole restore and fail loud (extension refuses to load / `/status/` reports the specific
   failure) rather than silently running with a mixed-integrity payload. This matches the
   project's existing philosophy of explicit failure over silent degradation
   (`/status/` `degraded` pattern already exists for domain registration).

**Do not use `shutil.copy2` as the sole operation** — its Python-level copy is not atomic on
its own; wrap it (or an equivalent `open`/`read`/`write` loop, since `shutil` availability
under IronPython 3 is unconfirmed — verify before relying on it) with the temp-name-then-
`os.replace` pattern above regardless.

**Robocopy is not needed and adds a subprocess dependency** for a job that a same-runtime
file copy handles correctly; reserve it only if hash verification reveals that plain
byte-copy strips something (permissions, alternate data streams) that matters — unlikely for
`.py` source files.

### Prior art for pyRevit extension self-verification

**Could not verify:** no documented precedent was found in pyRevit's own ecosystem for an
extension verifying its own file integrity at load and self-healing from a network share.
pyRevit's own updater (`pyrevit update`) handles the analogous problem for pyRevit *itself*
via git-based sync, not manifest-hash verification, and that mechanism is not exposed for a
third-party extension to reuse. Treat this capability as bespoke to this project — flag it as
a candidate for the next phase's deeper research if edge cases (concurrent Revit instances
racing to restore at the same time, share unavailable at boot) turn out to matter; the current
milestone's Out-of-Scope list already defers "защита от целенаправленного локального обхода"
(protection against deliberate local bypass), so a best-effort restore-then-fail-loud design
is sufficient without building distributed-lock coordination between instances.

---

## Capability 3 — Serializing mutating calls

### `asyncio.Lock` vs `asyncio.Semaphore(1)` vs queue+worker `[CPython]`

All three achieve mutual exclusion; they differ in ergonomics and failure behavior:

| Primitive | Behavior | Fit here |
|---|---|---|
| `asyncio.Lock()` | One holder at a time; `async with lock:` block; raises nothing special on contention, callers simply await | **Recommended.** Semantically exact match: "only one Revit transaction may be in flight" is mutual exclusion, not a rate limit. `asyncio.Lock` documents this exact use case. |
| `asyncio.Semaphore(1)` | Functionally identical to a Lock when bound to 1, but its API and docs frame it as a *counting* primitive for admitting N concurrent holders | Works, but `Semaphore(1)` is what you write when you might raise the bound later. Since the real constraint is Revit's single-threaded API — not a resource pool this project controls the size of — a plain `Lock` states the invariant more honestly and is what a future reader should reach for. Use `Lock`, not `Semaphore(1)`. |
| Queue + dedicated worker task | Full control over ordering, retry, backpressure, cancellation | **Overkill for this milestone.** PROJECT.md defers "Идемпотентность и безопасные повторы" (idempotency and safe retries) explicitly to a later milestone ("сначала сериализация" — serialization first). A queue buys ordering/retry semantics this milestone doesn't need yet, at the cost of a redesign of how tool calls dispatch. Revisit when retry/backpressure work starts. |

### Where the lock lives, relative to `stateless_http=True` and the shared `httpx.AsyncClient`

`stateless_http=True` governs the **MCP protocol session layer** — it means each MCP
request/response doesn't persist a session object across calls at the transport layer (per
FastMCP's stateless-mode docs: "no sessions are tracked on the server, each request creates a
temporary session that's discarded after the response"). **It does not affect process-wide
Python state.** A module-level `asyncio.Lock()` in `main.py`, sibling to the existing
module-level `_http_client`, lives for the lifetime of the OS process regardless of
`stateless_http` — the flag only concerns MCP session bookkeeping, not your own globals.

This matters concretely: `stateless_http=True` was chosen (per the comment in `main.py`) "for
better compatibility" at the protocol layer — it does **not** mean "treat this process as
stateless" in the way a horizontally-scaled web service would. There is exactly one OS
process, one Revit instance behind it (mostly — see the two-listeners problem this same
milestone addresses), and one event loop. A single lock at module scope in `main.py` is
correct and sufficient; no external coordination (Redis, file lock, etc. — irrelevant anyway
since this is single-instance-per-Revit-process by construction) is needed.

```python
# main.py — module scope, alongside _http_client
_mutation_lock: Optional[asyncio.Lock] = None

def _get_mutation_lock() -> asyncio.Lock:
    global _mutation_lock
    if _mutation_lock is None:
        _mutation_lock = asyncio.Lock()
    return _mutation_lock
```

**Placement relative to the httpx pool (`max_connections=20`):** the lock must wrap the
*mutating* call, not live inside the httpx client or its connection limits. The pool's 20
connections govern how many HTTP sockets can be open concurrently (useful for concurrent
*read* routes, e.g. several `GET /status/` or list-elements calls that don't touch a
transaction) — that concurrency is fine to keep. Only the **mutating POST routes** (the same
set that need `commit_and_report`, per PROJECT.md's Active list) need to funnel through the
lock before they're allowed to fire their `client.post(...)`. Concretely: acquire the lock
inside `revit_post` (or a wrapper it calls) only when the target endpoint is known to mutate —
or, simpler and safer against a forgotten classification, wrap *all* POSTs (mutating and not)
in the lock and leave GETs unlocked, since serializing POSTs against each other costs nothing
observable at this call volume and removes any need to classify routes by mutation status:

```python
async def revit_post(endpoint, data, ctx=None, **kwargs):
    async with _get_mutation_lock():
        return await _revit_call("POST", endpoint, data=data, ctx=ctx, **kwargs)
```

This is a two-line change at the exact seam that already exists (`revit_post` is already the
single chokepoint every mutating tool calls through — see `CLAUDE.md`'s "three callables are
injected into every tool registrar"). No change to `_get_client()` or its `httpx.Limits` is
needed; the 20-connection pool and the mutation lock solve different problems and coexist
cleanly.

### FastMCP-specific hooks for wrapping tool calls

FastMCP (the standalone Prefect/jlowin package) has a `Middleware` class with an `on_call_tool`
hook for exactly this kind of cross-cutting concern (gofastmcp.com/servers/middleware) — but
**this project depends on `mcp[cli]>=1.9.0`, the official `modelcontextprotocol/python-sdk`
package, which exposes `mcp.server.fastmcp.FastMCP`, not the standalone `fastmcp` PyPI
package.** These are two different projects that happen to share a class name (FastMCP 1.0
was contributed into the official SDK in 2024; the standalone package continued as FastMCP
2.0+ with a materially larger API surface, middleware included). **Do not add `fastmcp` as a
dependency to get middleware** — that would mean running two overlapping MCP implementations
side by side for one hook. The lock-in-`revit_post` approach above needs no middleware layer
at all; it is strictly simpler and stays inside the officially-vendored SDK already in use.

---

## Capability 4 — Structured local audit log (JSONL)

### Logging approach `[CPython]`

**stdlib `logging` with a minimal custom JSON formatter — not `structlog`, not manual
`open().write()` calls.**

- **Why not `structlog`:** it's a real dependency (pure Python, but still one more thing
  AppLocker/EDR has to allow through and one more line in `uv.lock` to audit) for a feature
  stdlib covers completely. `structlog`'s value proposition — contextvars-based context
  binding, processor pipelines — is aimed at applications with much richer structured-logging
  needs (multiple subsystems, request-scoped context threaded implicitly) than "append one
  JSON object per mutation." Skip it.
- **Why not raw manual writes:** hand-rolled `open(path, "a").write(json.dumps(...) + "\n")`
  reimplements what `logging.handlers.RotatingFileHandler` already does correctly (buffering,
  rotation, file handle lifecycle) and is easy to get subtly wrong under concurrent access
  (see below). Using `logging` also means audit entries can share the same `logger =
  logging.getLogger(__name__)` convention already established for Revit-side logging in
  `CLAUDE.md`'s non-negotiable invariants, keeping one mental model.
- **The formatter is genuinely small** — no library earns its keep:

```python
# tools/audit.py — CPython, new module
import json
import logging

class JsonlFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "audit_extra"):
            payload.update(record.audit_extra)
        return json.dumps(payload, ensure_ascii=False)
```

### The stdio-safety constraint

**This is the one place a mistake here is catastrophic, not just wrong.** `CLAUDE.md` is
explicit: "Never `print()` in `main.py` under stdio transport — it corrupts the protocol
stream." The audit logger must never write to stdout/stderr under any transport, stdio or
otherwise, because a bug that flips a code path (e.g., a misconfigured handler that defaults
to `StreamHandler()`) could resurface for someone who only tested `--streamable-http` and then
hits the bug the day someone runs it under stdio (which is the default transport per
`main.py`'s `if __name__ == "__main__"` block).

**Safe pattern: construct the audit logger with an explicit `FileHandler`/
`RotatingFileHandler` only, and never attach it to the root logger** (which might have a
`StreamHandler` from elsewhere, or gain one later):

```python
import logging
from pathlib import Path

def build_audit_logger():
    log_dir = Path(os.environ.get("LOCALAPPDATA", ".")) / "revit-mcp-server" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("revit_mcp.audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # critical: never bubble up to root, which may have a stream handler

    handler = logging.handlers.RotatingFileHandler(
        log_dir / "audit.jsonl",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(JsonlFormatter())
    logger.addHandler(handler)
    return logger
```

`logger.propagate = False` is the load-bearing line — it's what guarantees a stray root
`StreamHandler` (present or future) never receives an audit record and never touches stdout.
Construct this logger once at import time in `main.py` (or a small `tools/audit.py`), the same
way `_http_client` is a module-level singleton.

### Log rotation on Windows without extra deps

**`logging.handlers.RotatingFileHandler` is the stdlib default and is what's recommended
above** — but it has one confirmed Windows-specific defect: a rotation failure (typically
because the file is still open/locked by another handle) means the rename step fails and, in
the standard library's default error handling, subsequent log events after a failed rotation
can be dropped rather than retried (documented Windows-specific `RotatingFileHandler` issue).

For this project's actual concurrency profile, that risk is low but not zero — see next
section — and the third-party fix (`concurrent-log-handler` on PyPI) is explicitly **not
recommended** here: it's a new dependency solving a problem this project's write pattern
mostly avoids by construction (see below). If rotation failures are observed in practice,
the pragmatic zero-dependency mitigation is `delay=True` on the handler (defers file open
until first write, reducing the window where the file is held open across a config reload)
combined with accepting that a rare dropped rotation is not catastrophic for an audit trail
that's supplementary to Revit's own journal — this is a local diagnostic log, not a
compliance ledger, per the stated threat model.

### Location on Windows

**`%LOCALAPPDATA%\revit-mcp-server\logs\audit.jsonl`** — `%LOCALAPPDATA%` is the correct
choice over `%APPDATA%` (roaming) because this data is machine-local, per-user, and
explicitly the documented convention for logs and non-essential per-user application data
(it resolves to `C:\Users\<user>\AppData\Local` and is never synced by roaming profiles,
which matters on domain-joined BIM workstations where roaming profiles are common and syncing
a growing log file on every login/logout would be actively harmful).

### Concurrent-write concerns if two Revit instances run

This is the sharpest edge in this capability, and it connects directly to a problem this same
milestone is already solving: `CLAUDE.md` documents that two Revit instances **can both bind
`127.0.0.1:48884`** because pyRevit's routes server sets no exclusive-address flag. If that
happens, **both MCP server processes** (one per Revit instance, per the architecture — each
`main.py` process talks to whichever Revit process the OS routes its connection to) could, in
the degenerate case, end up with two independent `RotatingFileHandler` instances targeting the
same `audit.jsonl` path if a user runs two Claude Desktop / Claude Code sessions against two
Revit instances on the same machine.

Two independent `logging.handlers.RotatingFileHandler`s writing to the same path from two
separate OS processes is a known-bad pattern — Python's own `RotatingFileHandler` is documented
as unsafe for multi-process writers to a shared file (this is precisely the gap
`concurrent-log-handler` exists to fill). Two mitigations, in order of preference:

1. **Prefer: make the log path instance-specific.** Since this same milestone already adds
   document/instance identity to every response (per PROJECT.md's Active requirement "Каждый
   ответ сервера относится к конкретному документу в конкретном процессе Revit"), reuse that
   identity (e.g., the Revit process PID once discovered, or the resolved port after the
   configurable-port work below) to namespace the log file:
   `%LOCALAPPDATA%\revit-mcp-server\logs\audit-{port}.jsonl` or `audit-{revit_pid}.jsonl`.
   This sidesteps the multi-writer problem entirely with zero new dependencies, and is a
   natural fit since this milestone is already threading that identity through the system.
2. **Fallback: accept interleaved-but-not-corrupted appends.** A single `logging.FileHandler`
   (not rotating) opened in `"a"` (append) mode is safe for **interleaved line-level writes**
   from multiple processes on Windows as long as each write is a single `write()` call under
   roughly one line — NTFS append-mode writes for small buffers are effectively atomic at the
   OS level for the common case, though this is not a documented guarantee at arbitrary size.
   **Rotation** is what breaks under concurrent processes (the rename step), not plain append —
   so if per-instance file naming (option 1) isn't implemented, at minimum disable rotation
   (`FileHandler` instead of `RotatingFileHandler`) for the shared-path case and manage growth
   out-of-band (e.g., a scheduled task, or accept unbounded growth as a known limitation and
   note it for the next milestone).

**Recommendation: implement option 1** (instance-namespaced log files) since the milestone is
already building the instance-identity mechanism it depends on — this is the only approach
that fully removes the concurrent-writer hazard rather than just tolerating it.

---

## Configurable port

### Current state (confirmed in `main.py:23`)

```python
REVIT_PORT = 48884  # Default pyRevit Routes port
```

Only `REVIT_HOST` is environment-driven; `REVIT_PORT` is a literal. Per PROJECT.md's own
Context section, this is a real, already-diagnosed gap: "pyRevit ставит [второй Revit] на
48885" (pyRevit places a second Revit on 48885) and it's unreachable by construction.

**Fix on the CPython side is trivial and needs no new dependency:**

```python
REVIT_PORT = int(os.environ.get("REVIT_PORT", "48884"))
```

This mirrors the existing `REVIT_HOST` pattern exactly (`os.environ.get("REVIT_HOST",
"localhost")`) and requires no further stack decision — it's a one-line change, not a
capability needing library research.

### pyRevit-side story for binding Routes to a specific host/port

**Confirmed:** `pyrevit configs routes` has a `port` subcommand — described in community
sources as configuring "the starting port number for the Routes servers... the first Revit
instance will start with this number and other instances will continue up adding one for each
instance (e.g., 48884 → 48885 → 48886)." This matches the PROJECT.md finding exactly (second
instance lands on 48885) and confirms port is **settable but only as a starting point for an
auto-incrementing sequence per Revit instance launched**, not a fixed assignment per instance.

**Confirmed: no `host` subcommand exists** under `pyrevit configs routes` — this matches
PROJECT.md's own finding ("`pyrevit configs routes` не умеет ставить `host`") and the pilot
station's observed `0.0.0.0:48884` bind, which is a security-relevant finding this same
milestone is addressing (force `127.0.0.1`).

**Where host/port actually originate, from pyRevit's own routes server source
(docs.pyrevitlabs.io/reference/pyrevit/routes/server/):** `activate_server()` reads
configuration via `serverinfo.register()` and constructs `RoutesServer(host=rsinfo.server_host,
port=rsinfo.server_port)`. This confirms host and port are **not hardcoded inside the routes
server itself** — they're read from pyRevit's own config store (the `.ini` file, via
`userconfig`), which the CLI's `configs routes port` subcommand is a front-end for. **No
programmatic host override exists from the extension side** (i.e., `startup.py` cannot force
a different bind at runtime) — the only lever available is pyRevit's own config file/CLI,
predating this extension's control. This is consistent with PROJECT.md's constraint that the
127.0.0.1 bind must be *forced* at a different layer (most likely: detect a non-loopback bind
in `/status/` or at startup and refuse to serve / warn loudly, since the extension cannot
change pyRevit's own listen address). **This is a pyRevit-ecosystem limitation, not something
resolvable by adding a library** — flag for the roadmap: forcing the bind is a policy/detection
problem, not a stack problem, and belongs in `revit_mcp/` code, not in a new dependency.

**MEDIUM confidence** on the exact mechanics of the auto-incrementing port sequence across
instances (formatting assumed from secondary/community sources — Notion page and search
snippets, not the primary pyRevitLabs docs site, which didn't surface a page dedicated to this
CLI subcommand). Verify directly with `pyrevit configs routes --help` on a pilot machine before
relying on the increment behavior in code.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| Static bearer token + constant-time compare | HMAC-SHA256 over request body | If a future milestone allows non-loopback binds, making body tampering in transit a real threat |
| `System.Security.Cryptography.CryptographicOperations.FixedTimeEquals` | Hand-rolled XOR-accumulate loop in pure IronPython | Only if `CryptographicOperations` proves unavailable on the specific .NET runtime version pyRevit's IPY342 hosts — verify on a pilot machine before shipping either |
| `hashlib.sha256` on both runtimes | `System.Security.Cryptography.SHA256` on IronPython | Not needed — unlike `hmac.compare_digest`, `hashlib.sha256` has no C-accelerator gap; only reach for the .NET class if a future finding shows IronPython's `hashlib` is missing or broken for this specific algorithm |
| `asyncio.Lock` | `asyncio.Semaphore(1)` | Functionally interchangeable at bound 1; prefer `Lock` for the honest single-holder semantics unless a later milestone deliberately raises the bound above 1 |
| stdlib `logging` + tiny JSON formatter | `structlog` | If audit logging grows into a much richer structured-logging need across many subsystems with implicit context propagation — not the case for one JSONL-per-mutation stream |
| `logging.handlers.RotatingFileHandler`, instance-namespaced path | `concurrent-log-handler` (PyPI) | If instance-namespacing (recommended) turns out to be impractical and true single-shared-file multi-process writing becomes unavoidable — this is the one place a new dependency would be defensible, but only as a fallback |
| `os.replace` + temp-name-then-rename | `robocopy` subprocess | If plain byte copy is shown to lose something byte-hash verification doesn't catch (unlikely for `.py` source) |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `hmac.compare_digest` on the IronPython 3 side | Not confirmed present — IronPython's own `hmac.rst` reference lists only `new/update/digest/hexdigest/copy`, omitting it; CPython's version depends on a C accelerator IronPython never ported | `System.Security.Cryptography.CryptographicOperations.FixedTimeEquals` via `clr` |
| `a == b` string equality for secret comparison, on either runtime | Short-circuits on first mismatched byte — leaks timing information proportional to matching prefix length, defeating the purpose of a shared secret | `hmac.compare_digest` (CPython) / `FixedTimeEquals` (IronPython 3) |
| `structlog` | Real dependency for a problem stdlib fully solves; adds an AppLocker/EDR review surface for zero capability gain at this milestone's scope | stdlib `logging` + ~10-line JSON `Formatter` subclass |
| `concurrent-log-handler` (PyPI) as a first choice | New dependency; the actual multi-process hazard is better solved by namespacing the log path per Revit instance, which this milestone is already building the identity mechanism for | Instance-namespaced `RotatingFileHandler` (own file per instance) |
| Attaching the audit logger to the root logger, or letting it inherit a `StreamHandler` | Root logger convention is fragile — any future code that calls `logging.basicConfig()` or adds a `StreamHandler()` anywhere corrupts the stdio MCP protocol stream the moment the audit logger's records propagate there | Dedicated named logger (`logging.getLogger("revit_mcp.audit")`) with `propagate = False` and an explicit `FileHandler`/`RotatingFileHandler` only |
| `asyncio.Semaphore(N)` with `N > 1` for "some concurrency" on mutations | Revit's API is single-threaded per the project's own non-negotiable invariants — any `N > 1` reintroduces the exact concurrent-`DB.Transaction` bug this capability exists to close | `asyncio.Lock()` (equivalent to a strict `N=1`, but states the true invariant) |
| Adding the standalone `fastmcp` (Prefect/jlowin) package to get `Middleware`/`on_call_tool` hooks | This project depends on the **official SDK's** `mcp.server.fastmcp.FastMCP`, a different package with a smaller API; adding the standalone package means running two overlapping MCP implementations for one hook | Wrap the mutation lock directly at the existing `revit_post` chokepoint — no middleware layer needed |
| `robocopy` subprocess call for the manifest restore | Subprocess dependency, extra surface for AppLocker/EDR to flag, and no capability gain over a same-runtime file copy for plain source files | `open`/read/write loop (or `shutil.copy2` if confirmed available) into a temp name, then `os.replace` |

## Stack Patterns by Variant

**If the .NET runtime hosting IPY342 turns out to predate `CryptographicOperations`:**
- Fall back to a hand-rolled fixed-length XOR-accumulate compare in IronPython, iterating the
  full length of both byte arrays regardless of where a mismatch is found
- Because `FixedTimeEquals` was introduced with .NET Core 2.1 / .NET Standard 2.1 — verify
  which CLR pyRevit's bundled IronPython 3 actually targets before assuming its presence

**If a future milestone allows non-loopback binding (relaxing the current `127.0.0.1`-only
constraint):**
- Revisit the bearer-token-only decision in Capability 1 — add HMAC-over-body once there is an
  actual network path for tampering to matter
- This also changes the audit-log multi-writer risk profile (more clients, not just two local
  Revit instances) — reconsider file-per-session naming, not just file-per-instance

**If Revit instance count on one workstation regularly exceeds two:**
- The port auto-increment behavior (48884 → 48885 → 48886...) means `REVIT_PORT` becomes a
  range, not a single override — the `os.environ.get("REVIT_PORT", "48884")` fix above is
  correct for "which instance do I mean" but a multi-instance discovery/enumeration mechanism
  (already separately listed in PROJECT.md's Active requirements) is the real fix, not a stack
  concern

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `mcp[cli]>=1.9.0` (official SDK, already pinned) | `mcp.server.fastmcp.FastMCP` | This is **not** the standalone `fastmcp` PyPI package (Prefect/jlowin, now at 3.x) — the two share a class name but diverged after FastMCP 1.0 was contributed into the official SDK in 2024; do not mix installation instructions or middleware docs between them |
| CPython `hashlib.sha256` | IronPython 3.4 `hashlib.sha256` | Both produce identical SHA-256 digests for identical byte input — this is a pure algorithm with no accelerator dependency, unlike `hmac.compare_digest`; safe to hash on one side and verify on the other |
| IronPython 3.4 (`IPY342`, fleet standard since 2026-09-07) | .NET BCL `System.Security.Cryptography.*` | Always available via `clr.AddReference("System")` since it's part of the runtime pyRevit itself hosts — no separate install |
| `httpx>=0.28.1` (already pinned) | New auth header on existing `client.post(...)` calls | No version bump needed; headers dict is already used for `Content-Type` in `_revit_call` |

## Sources

- IronPython docs — `ironpython-docs/library/hmac.rst` (github.com/IronLanguages/ironpython-docs) — confirms only `new/update/digest/hexdigest/copy`, omitting `compare_digest`. **MEDIUM confidence** (absence-of-evidence, not an explicit "not implemented" statement) — verify empirically on a pilot machine before relying on this in production code.
- IronPython docs — `ironpython-docs/library/hashlib.rst` — confirms sha256 and siblings always present. **HIGH confidence.**
- `github.com/IronLanguages/ironpython3` — confirms IronPython 3.4.1 targets the Python 3.4.10 standard library baseline. **HIGH confidence.**
- pyRevit official docs — `docs.pyrevitlabs.io/reference/pyrevit/routes/` — `Request`/`Response` object shape, `.headers` property. **HIGH confidence** (primary source).
- pyRevit official docs — `docs.pyrevitlabs.io/reference/pyrevit/routes/server/` — `activate_server()`, `RoutesServer(host=..., port=...)`, config sourced from `serverinfo.register()`. **HIGH confidence** (primary source).
- Community sources (Notion pyRevit CLI page, search snippets) — `pyrevit configs routes port` auto-increment behavior across instances. **MEDIUM confidence** — not from pyrevitlabs.io directly; verify with `pyrevit configs routes --help` on a pilot machine.
- Microsoft Learn / .NET docs — `System.Security.Cryptography.SHA256`, `CryptographicOperations.FixedTimeEquals` — standard BCL API, stable since .NET Core 2.1. **HIGH confidence** (well-documented, stable API).
- Python official docs — `docs.python.org/3/library/asyncio-sync.html` — `asyncio.Lock` vs `asyncio.Semaphore` semantics. **HIGH confidence** (primary source).
- FastMCP (standalone, gofastmcp.com/servers/middleware) — confirms `Middleware`/`on_call_tool` hooks exist **only in the Prefect/jlowin standalone package**, not the official SDK this project uses. **HIGH confidence**, but explicitly not applicable here — included to justify the "don't add fastmcp" recommendation.
- CPython bug tracker / `python/cpython` issues — `RotatingFileHandler` Windows rotation-failure behavior. **MEDIUM confidence** (issue-tracker discussion, not a documentation guarantee) — treat rotation-failure risk as real but low-probability for this project's write volume.
- Project source (this repo) — `main.py`, `CLAUDE.md`, `.planning/PROJECT.md`, `revit_mcp/textutils.py`, `pyproject.toml` — **HIGH confidence** (primary, read directly).

**Explicitly flagged as NOT verifiable from available sources:**
- Whether pyRevit's `request.headers` dict lookup is case-sensitive or case-insensitive.
- Whether `CryptographicOperations.FixedTimeEquals` is available on the exact .NET runtime version pyRevit's bundled IPY342 hosts (vs. an older .NET Framework version that predates it).
- Any documented prior art for a pyRevit *extension* (as opposed to pyRevit itself) doing self-integrity-verification and restore at load — none found; treat as bespoke design.
- Exact case/format of the `pyrevit configs routes port` CLI output and whether a per-instance (not just starting-point) port assignment is possible through any undocumented flag.

---
*Stack research for: trust/identity/integrity foundation, Revit MCP bridge (dual-runtime: CPython + IronPython 3)*
*Researched: 2026-09-21*
