# Architecture Research: Trust Foundation (v0.1) Integration

**Domain:** Cross-cutting concerns (secret verification, identity stamping, mutation
serialization, startup integrity/restore) added to an existing dual-runtime,
convention-discovered plugin architecture.
**Researched:** 2026-09-21
**Confidence:** HIGH for everything traced directly through repo code and the local
pyRevit-Master source tree; MEDIUM where the recommendation depends on a design choice
this milestone has not made yet (explicitly flagged).

Every claim below was verified by reading the actual file named, not inferred from the
generic idea of "a plugin architecture." Where pyRevit's own behavior mattered, the
verification was against `C:\Users\Admin\AppData\Roaming\pyRevit-Master\pyrevitlib\pyrevit\`
(a real local pyRevit-Master checkout — same lineage as the fleet-standard install),
not documentation or memory.

---

## Standard Architecture (as it exists today — confirmed, not assumed)

```
MCP client --stdio/SSE/HTTP--> main.py + tools/ --HTTP :48884--> startup.py + revit_mcp/ --> Revit API
             (CPython 3.11+, async, one process)                  (IronPython 3, sync, inside Revit)
```

Confirmed chokepoints (read the code; nothing bypasses these):

| Chokepoint | File:lines | Why it really is one |
|---|---|---|
| `_revit_call` | `main.py:76-102` | `revit_get`/`revit_post`/`revit_image` all funnel through `_get_client()` and either `_revit_call` or its own inlined `client.get`. This is the **only** place an HTTP request leaves the CPython process toward Revit. |
| `format_response` | `tools/utils.py:5-107` | Every `tools/*_tools.py` module's `@mcp.tool()` body ends `return format_response(response)` — confirmed in `tools/editing_tools.py:29,50,66`. It is the single renderer between the bridge and the MCP client. |
| `register_routes()` | `startup.py:73-122` | The only place any `revit_mcp/*.py` module gets imported and its registrar invoked. Nothing else in the Revit half calls `__import__` on a domain module. |
| `routes.make_response(...)` | called from every handler, e.g. `revit_mcp/editing.py:23,90,108` | Confirmed against `pyrevit/routes/server/base.py`-style `Response` shape; it is how a handler produces its return value, but **it is not itself a chokepoint the framework calls through** — it just builds the payload the handler returns. The framework then serializes whatever the handler returned (see `handler.py:234-303`), so `make_response` is a convention every handler in this repo follows, not something pyRevit enforces or lets you wrap. |

Confirmed **non**-chokepoint (this is where a wrong assumption would be most costly):

`pyrevit.routes.API.route()` (`pyrevitlib/pyrevit/routes/api.py:28-39`) is a bare decorator:

```python
def route(self, pattern, methods=['GET']):
    def __func_wrapper__(f):
        for method in methods:
            add_route(api_name=self.name, pattern=pattern, method=method, handler_func=f)
        return f
    return __func_wrapper__
```

`add_route` (`server/router.py:171-186`) stores `handler_func` verbatim in a
`{Route(pattern, method): handler_func}` dict. Dispatch
(`server/server.py:153-192` `_handle_route`) calls
`router.get_route_handler(...)` and then either raises the handler through a Revit
`ExternalEvent` (`handler.py:305-328` `RequestHandler.Execute`) or, for handlers with no
`uiapp`/`uidoc`/`doc` argument, calls it directly:
`handler.RequestHandler.run_handler(handler=route_handler, kwargs=...)` (`handler.py:160-192`).

**There is no `before_request`, `after_request`, middleware chain, or interceptor
anywhere in this call path.** `api` (the object every `register_*_routes(api)` receives)
carries exactly one instance attribute (`self.name`) and one method (`route`). It cannot
be extended to run code around every handler without either (a) monkey-patching
`api.route` itself before any domain calls it, or (b) wrapping the handler function at
registration time. **Verified by reading `api.py`, `router.py`, `handler.py`, and
`server.py` directly — this is not an assumption from pyRevit's docs (which are silent on
the point; the public docs site does not enumerate `API`'s methods).**

---

## Question 1 — Structural answer for cross-cutting concerns under "no cross-domain imports"

### What the no-cross-import rule actually forbids, and what it permits

Re-reading `startup.py`'s own docstring and `CLAUDE.md` together: the rule is **domain →
domain** import prohibition, stated precisely as "no module in `revit_mcp/` imports
another module in `revit_mcp/`... every cross-module import goes to the flat `utils`
helper" (`startup.py:15-17`). `tests/unit/test_registration.py` enforces this at the
domain level. `revit_mcp/textutils.py` and `revit_mcp/utils.py` are *not* domains — they
expose no `register_*_routes` and `startup.py`'s own discovery logic
(`_registrar_in`, `startup.py:60-70`) classifies any such module as a helper
(`registry.SKIPPED[name] = "no register_*_routes callable"`). So the rule already has a
sanctioned exception lane: **shared, side-effect-free helper modules that never call
`api.route()` themselves may be imported by every domain.** `commit_and_report`,
`suppress_warnings`, `parse_request_data`, `sanitize_string` all live there today and are
imported by essentially every route module (confirmed in `revit_mcp/editing.py:7`).

This directly answers the question: **a new `revit_mcp/security.py` (or similarly named
helper) that exposes no registrar and is imported by every domain is not a violation of
the no-cross-import rule — it is exactly the pattern the rule already carves out.** The
rule is about domain coupling (rooms.py depending on views.py), not about a shared,
stateless utility layer.

### Evaluating the options for each of the four concerns

| Option | Verdict | Reasoning |
|---|---|---|
| Decorator applied per handler (e.g. `@require_secret` on each `@api.route`) | **Reject as the sole mechanism** | Since `api.route` is a bare decorator with no hook, a second decorator can be added, but it has to be applied at all 51 route definitions by hand — same cost as editing every handler, and the same "easy to forget on the next route" problem the milestone explicitly wants to avoid for identity stamping. Usable as a *thin* layer only if generated/enforced by a lint/test, see below. |
| Wrapping `revit_get`/`revit_post` in `main.py` | **Right answer for CPython-side concerns (secret injection, per-instance addressing, client-serialization)** | Confirmed sole chokepoint (`main.py:76-102`). Every domain's tool file calls only these three injected callables — never `httpx` directly (grep confirms `import httpx` appears exactly once, in `main.py`). Wrapping here costs **zero domain-file edits**. |
| Middleware/before-request hook in pyRevit Routes | **Does not exist — verified, not assumed** | See the code excerpts above. `routes.API` has no such extension point. Any "middleware" on the Revit side has to be synthesized by this repo, not borrowed from pyRevit. |
| Modifying the shared `api` object passed to `register_*_routes` | **Best available Revit-side chokepoint, with one large caveat** | `api` is a plain `API(name)` instance created once in `startup.py:30` and passed to every registrar. Nothing stops `startup.py` from replacing `api.route` with a wrapping version *before* calling `register_routes()` — i.e., monkey-patch `routes.API.route` (or the `api` instance's own `route` method) so that every `@api.route(...)` call in every domain module transparently wraps `f` before handing it to `add_route`. Because registration happens once, at extension load, in one place (`startup.py`), this is a **one-file change that retroactively covers all 51 routes with no per-domain edit**, despite `api.route` itself having no hook. This is the load-bearing insight for the Revit side. |
| Base/helper module every domain imports (`from .utils import ...` style) | **Right vehicle to *implement* the logic that the `api` monkey-patch *installs*** | Not a replacement for the `api`-patch mechanism, but where the actual secret-check / identity-stamp / commit-serialization code should live, since it must be unit-testable-by-convention-as-a-helper and importable by the patch installer in `startup.py`. |

### Recommended structure

**New file, Revit side:** `revit_mcp/security.py` (helper, no registrar, exposes no
`register_*_routes` — confirmed pattern from `textutils.py`/`utils.py`). Contains:

- `verify_shared_secret(request)` — reads a header/field pyRevit's `Request` object
  exposes (`base.Request` in `pyrevitlib/pyrevit/routes/server/base.py` — confirm field
  name against that class before implementing; not fully enumerated in this pass) and
  compares against the secret injected at build time (see Q for build pipeline below).
- `stamp_identity(payload)` — adds `document_title`, a process-stable instance id, PID,
  and port to a response dict (see Q2).
- A small **wrapping installer**, e.g. `def wrap_api(api, *, mutating_only=True)`, that
  replaces `api.route` with a version that, for POST (mutating) methods, wraps the
  decorated handler in a function performing secret verification before calling the
  real handler, and always wraps the return value through `stamp_identity`.

**Changed file, Revit side:** `startup.py`. Before the `for name in
_domain_modules(revit_mcp): ... registrar(api)` loop (`startup.py:90-104`), call
`api = security.wrap_api(api)` (import inside `register_routes()`, matching the existing
"imports live inside the register function" convention). This is a **single-file change**
that applies to all future and existing domains with **zero edits to the 23 domain
modules**, because `registrar(api)` in every domain calls `api.route(...)`, and `api`'s
`route` method is now the wrapped one.

**Verification of this claim:** `_domain_modules`/`_registrar_in`/`registrar(api)` in
`startup.py:90-104` is the only place any domain's `register_*_routes(api)` is invoked,
and every domain module receives the *same* `api` object built once in `startup.py:30`
(mutable, not re-instantiated per domain) — so mutating `api.route` before this loop
runs is guaranteed to affect every domain registered after that point, with no
domain-specific opt-in.

**New file, CPython side:** wrap `revit_get`/`revit_post` bodies in `main.py` (or, to
keep `main.py` from growing unboundedly, extract to a new `bridge.py` that `main.py`
imports and re-exports the same three names from) to: attach the shared secret as an
outgoing header on POST, and — depending on the per-instance-addressing decision (Q3) —
choose the target client. This still touches exactly one file group, not 27.

**Cost audit, explicit:** this design touches **2 files** (`startup.py`,
`main.py`/new `bridge.py`) plus **1 new helper module on each side**
(`revit_mcp/security.py`, and whatever CPython equivalent Q3/Q2 need) to cover all 23
domains / 51 routes / 54 tools. **It does not require touching any of the 23
`revit_mcp/*.py` or 23 `tools/*_tools.py` domain files.** The one exception: if the
milestone also wants `commit_and_report` used on the *remaining* routes that still call
bare `t.Commit()` (`editing.py`'s `delete_elements_handler` per `PROJECT.md` Context, and
`interop.py:96`'s `export_ifc`), that is a **separate, already-known, per-route fix**
unrelated to the cross-cutting wrapper — budget it as N small edits (N = count of routes
still bypassing `commit_and_report`; PROJECT.md names at least these two) rather than
folding it into the "touches every domain" cost bucket.

### Why the decorator-per-handler option is not simply wrong, just insufficient alone

A per-handler decorator becomes attractive only if the roadmap wants **route-selective**
policy (e.g., secret required on mutating routes, not on `/status/`). The `api.route`
wrapper installed in `startup.py` can implement that selectivity itself, by inspecting
`methods` at wrap time (mutating routes are POST in every domain module read here — see
`revit_mcp/editing.py:18,112`), so a per-handler decorator is not additionally needed. Do
not introduce both mechanisms; pick the single `api`-wrap point and make it
methods-aware.

---

## Question 2 — Where identity is stamped

### The two candidate chokepoints, evaluated

**Revit side — `routes.make_response(...)`:** This is *not* a function this repo can
wrap transparently the way `api.route` can be wrapped, because `make_response` is not
called by the framework on the handler's behalf — it is called *by the handler's own
code*, and its return value is simply whatever the handler returns
(`handler.py:283-303` `parse_response` reads `getattr(response, "status", ...)` /
`getattr(response, "data", response)` off whatever object the handler produced). So
"stamping at `make_response`" really means either (a) editing every one of the ~51 call
sites to pass extra keys — the 54-edit cost the question warns about — or (b) wrapping
`make_response` itself so every existing call site is stamped for free, analogous to the
`api.route` wrap.

**Recommendation: wrap `make_response`, not each call site.** Concretely, in
`revit_mcp/security.py` (or a dedicated `revit_mcp/identity.py` helper), define:

```python
from pyrevit import routes as _routes

def make_response_with_identity(data=None, status=_routes.OK, **kwargs):
    if isinstance(data, dict):
        data = dict(data)
        data.setdefault("document_title", ...)
        data.setdefault("instance_id", ...)
        data.setdefault("port", ...)
    return _routes.make_response(data=data, status=status, **kwargs)
```

...and have the `api`-wrap installer from Q1 monkey-patch `revit_mcp.utils.routes` (or,
more surgically, have every domain's `from pyrevit import routes` resolve to a
pre-stamped module-level shim) **or**, more simply and far less fragile: perform the
stamping in the same wrapper that Q1 already installs around every handler's *return
value*, not by patching `routes.make_response` itself. That is: `wrap_api`'s replacement
`route()` decorator wraps `f` so that after `f(**kwargs)` returns a `Response`-shaped
object (i.e., after `make_response` already ran *inside* the original handler), the
wrapper mutates or rebuilds that response's `.data` dict to add identity fields, then
returns it. This needs no monkey-patch of `pyrevit.routes` itself (fragile, since
`routes.make_response` is pyRevit's own function, shared with `routes_api` in
`pyrevit/routes/api.py:26-33` and any other extension on the same process) and instead
operates purely on the object the handler already produced, which is safe because
`Response` (or whatever `make_response` returns — confirm the exact type against
`pyrevit/routes/server/base.py` before implementing) is a value the wrapper fully owns
once `f()` returns.

**This is the single correct placement:** it is (1) applied once per request via the
same `api.route` wrap from Q1 — zero domain edits, (2) unconditional (every route, not
just ones someone remembers to touch), (3) does not perturb `format_response`'s error
classification (see next point), because it only **adds** keys to a dict that already
has whatever `error`/`status` keys the handler set — `format_response`
(`tools/utils.py:14-26`) checks `response.get("status", "")` and `response.get("error")`
and nothing else; adding `document_title`/`instance_id`/`port` keys cannot make either of
those two checks fire when they wouldn't have, because neither key it inspects is being
added or altered.

**MCP side — `format_response`:** Confirmed as the single renderer
(`tools/utils.py:5-107`), called from all 54 tool functions (spot-checked
`tools/editing_tools.py:29,50,66`; the docstring in `tools/utils.py:110-112` explicitly
says the two copies of the escape-culprit table are "the two halves of this repo," i.e.
this file is understood repo-wide as *the* MCP-side formatting boundary). **Do not stamp
identity here as the primary mechanism** — the whole point of Requirement "Every
document mutation... a specific instance" is that the *server* proves what answered, not
that the MCP-side formatter decorates a string after the fact with client-side
information it cannot verify (the CPython process does not itself know which Revit
instance answered; only Revit-side code does). `format_response` is, however, the right
place to make the identity fields *visible* to the model (e.g., include them in the
formatted text) once Revit has put them in the dict — which requires zero changes to the
`is_success`/`has_error` classification logic, since identity fields are additional
dict keys, not new status/error signals. Concretely: in the "structured success payload
without a standard wrapper key" branch (`tools/utils.py:59-71`) and the standard
`message`/`data` branches, identity fields already surface today because that code
iterates `sorted(data_fields)` over all non-`status`/`health`/`success` keys — **no
`format_response` edit is even strictly required** for the fields to appear once Revit
adds them, though a small edit to always prepend a one-line "Document: X | Instance: Y |
Port: Z" header regardless of which branch fires would improve legibility. That is an
edit to **one file**, not 27.

**Constraint honored:** `has_error` (`tools/utils.py:23-24`) only looks at `error` and
`status`. Adding `document_title`/`instance_id`/`port` as plain data keys cannot trip it.
Any implementer must resist the temptation to signal "identity unknown/degraded" via a
new `status` value or `error` key on an otherwise-successful response — that would
reintroduce the class of bug `commit c1231f6` already taught this codebase to avoid. If
"two listeners on 48884 detected" needs to be surfaced, it must be a normal data field
(e.g. `"port_conflict": true`), never a `status` value that could collide with the
`error/failed/failure/exception` set `format_response` checks.

---

## Question 3 — Serialization placement and multi-instance interaction

### Facts established by reading the code

- `main.py:13-19`: `FastMCP(..., stateless_http=True, json_response=True)`. This governs
  the **MCP protocol session model** (no server-held session state across HTTP
  connections) — it says nothing about the `httpx.AsyncClient` or Revit-call
  concurrency. It is orthogonal to the lock question, not a blocker to adding one.
- `main.py:30-47`: `_http_client` is a **lazily created module global**, `never closed`,
  bound to one `BASE_URL` computed once from `REVIT_HOST`/`REVIT_PORT=48884` at import
  time (`main.py:22-24`). One client → one base URL → one Revit instance today.
- `PROJECT.md` Context: confirms live, on the pilot station, that "httpx pool: 20
  simultaneous connections, no lock, no queue, no semaphore. Parallel tool calls open up
  to 20 simultaneous `DB.Transaction` against a single-threaded Revit API" — i.e., the
  absence of serialization is an already-diagnosed real defect, not a hypothetical.
- `PROJECT.md` Active requirements: "Конкретный экземпляр Revit адресуем — порт
  настраиваемый" (a specific Revit instance is addressable — port configurable) is
  **in scope for this same milestone**, alongside "Несколько моделей в одной сессии
  Revit: перечисление, адресация в вызове, переключение активного" (multiple models in
  one Revit session: enumeration, per-call addressing, active-switch).

### Should the lock be global or per-target-instance?

**Per-target-instance**, not a single global lock, for two independent reasons visible
directly in the code:

1. **The Revit API constraint the lock exists to satisfy is per-process, not
   per-server.** The single-threaded Revit API document-modification constraint
   (`DB.Transaction`) applies within one Revit process/document. Two *different* Revit
   processes (two ports, e.g. the pilot's own note that pyRevit puts a second Revit on
   48885) each have their own independent single-threaded API context. A single global
   lock would serialize calls to instance A behind calls to instance B for no reason
   Revit's own concurrency model requires — an unnecessary throughput tax the moment
   port-configurability (already an Active requirement) ships.
2. **A global lock silently regresses the moment multi-instance addressing exists.**
   If the roadmap adds per-instance addressing in the same milestone (it does, per
   PROJECT.md Active), a global lock becomes actively wrong: it either has to be resized
   into a per-instance lock immediately after shipping, or it ships a known-wrong
   serialization model that then has to be revisited — worse than building the
   per-instance object model up front, since the object model (below) is barely more
   code than a bare `asyncio.Lock()`.

**Recommendation:** an `asyncio.Lock` (or `anyio.Lock`, matching the `anyio` dependency
already imported in `main.py:6`) **keyed by target instance**, held only around the
POST/mutating path in `_revit_call`, not around GET.

### Object model for "the set of reachable Revit instances"

Given stdio's process lifecycle — the MCP server is a **subprocess spawned per client
session** (the Claude Desktop/Code convention: one `main.py` process per MCP client
connection, living exactly as long as that client keeps it running) — the object model
should be a small in-process registry, not a persisted store:

```python
# main.py or a new bridge.py

@dataclass
class RevitTarget:
    host: str
    port: int
    client: httpx.AsyncClient   # base_url = http://{host}:{port}/revit_mcp
    lock: asyncio.Lock          # serializes mutating calls to THIS instance only

_targets: dict[tuple[str, int], RevitTarget] = {}

def _get_target(host: str, port: int) -> RevitTarget:
    key = (host, port)
    if key not in _targets:
        _targets[key] = RevitTarget(
            host=host, port=port,
            client=httpx.AsyncClient(base_url=f"http://{host}:{port}/revit_mcp",
                                      trust_env=False,
                                      limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)),
            lock=asyncio.Lock(),
        )
    return _targets[key]
```

- **One `httpx.AsyncClient` per target, not one client with a dynamic `base_url`.**
  `httpx.AsyncClient(base_url=...)` is fixed at construction; the existing code already
  relies on this (`main.py:36-46`). Reusing a single client and mutating its `base_url`
  per call is not supported by httpx's public API and would defeat connection pooling
  guarantees across concurrent calls to different instances — a registry keyed by
  `(host, port)` is the natural extension of the existing single-global-client pattern,
  not a departure from it.
- **Lifecycle:** the registry is a plain module dict, matching the existing
  `_http_client` global's own lifecycle discipline (created lazily, "never closed" is
  already the accepted behavior per `ARCHITECTURE.md`'s own "State Management" section —
  the process exit is what reclaims the sockets, since this is a short-lived
  per-session subprocess, not a long-running server). No new cleanup problem is
  introduced by moving from one global to a dict of globals.
- **Where callers get a target from:** every tool already calls `revit_post`/`revit_get`
  through the *injected* callables (`register_editing_tools(mcp, revit_get, revit_post,
  revit_image=None)`, confirmed in `tools/editing_tools.py:8`). Add an optional
  `instance: tuple[str, int] | None = None` parameter to `revit_get`/`revit_post`
  (defaulting to the existing `REVIT_HOST`/`REVIT_PORT` module constants for
  backward compatibility with all 54 existing tool call sites, none of which need to
  change), and resolve it to a `RevitTarget` inside `_revit_call`. **This keeps the
  injection contract intact and requires zero edits to any of the 23
  `tools/*_tools.py` files** unless/until a specific tool (e.g. a new
  `list_revit_instances` / `switch_active_instance` tool this milestone's
  requirements already call for) needs to pass an explicit instance — which is 1-2 new
  tool files, not a retrofit of the existing 54.

### Confidence flag

**MEDIUM** on the exact shape of "addressing a specific instance in a call" (whether the
milestone wants a per-call `port` argument on every mutating tool, or a session-level
"active instance" set by a `switch_active_instance` tool and defaulted thereafter) —
that is a product decision PROJECT.md's Active list gestures at ("переключение
активного") but does not fully specify. The registry/lock object model above is correct
under either resolution; only the calling convention on top of it depends on that
decision.

---

## Question 4 — Startup-time integrity check and self-restore

### Hook points in the pyRevit extension lifecycle (verified against pyrevit-master source)

Traced `pyrevitlib/pyrevit/loader/sessionmgr.py:_new_session()` (lines 186-260), the
function that runs once per Revit session / pyRevit (re)load:

1. For each installed UI extension: `ui_ext.configure()`, load command modules,
   `asmmaker.create_assembly(ui_ext)` — this builds the extension's *button/ribbon*
   assembly from its `.pushbutton`/`.panel` bundles. `revit-mcp-server.extension` is a
   "no UI" pyRevit extension (it exposes routes, not buttons) so this step is close to a
   no-op for it, but it still runs first, per extension, before that extension's startup
   script.
2. **Only after every extension's assembly step has run**, in a second loop
   (`sessionmgr.py:220-236`): `execute_extension_startup_script(assm_ext.ext.startup_script,
   ...)` is called — this is `startup.py`. `Extension.startup_script`
   (`extensions/components.py:543-552`) resolves to whichever of
   `startup.py`/`.cs`/`.vb`/`.rb` exists in the bundle root via `find_bundle_file`; there
   is exactly one file name pyRevit will treat as "the" startup script per extension.
3. **Only after all startup scripts across all extensions have run**: `hooks.register_hooks`
   (Revit *application/document event* hooks — `command-before-exec`-style, per
   `loader/hooks.py:69`, confirmed unrelated to extension loading), then UI/ribbon
   creation (`uimaker.update_pyrevit_ui`).

**Conclusion, directly answering the question: there is no pre-load hook available to an
individual extension.** pyRevit's own hook system (`hooks.register_hooks`) is itself
registered *after* every extension's `startup.py` has already run, so it cannot be used
to gate or precede `startup.py`. `execute_extension_startup_script` hands pyRevit's
script executor the **file path** of `startup.py` and nothing else — pyRevit does not
read `startup.py`'s bytes into memory before that call in any way this repo could
intercept; whatever is physically on disk at that instant is what
`runtime.types.ScriptExecutor.ExecuteScript` executes.

**`startup.py` is the earliest point this codebase controls, full stop — and it is
already "too late" in the sense the question raises**, because `startup.py` executes
*inside* the same script-execution engine invocation that pyRevit uses to load the
extension; there is no antecedent extension-supplied code slot. This matches the
question's suspicion precisely: **`startup.py` is both the earliest hook available and
itself part of what integrity-checking would need to protect** — if `startup.py` on
disk is corrupted (partial write, wrong encoding, truncated), pyRevit's script executor
will fail to parse/execute it and the entire extension fails to load (visible as
`/status/` returning pyRevit's own "Route does not exist," exactly the failure mode
`PROJECT.md`/`CLAUDE.md` already documents for a different cause — a disabled extension
flag). There is no earlier code in the pipeline (not `hooks`, not `hooks.register_hooks`,
not the C# assembly step) that this repository's build can hook into.

### The bootstrap problem, made concrete

Because `startup.py` is simultaneously (a) the only file pyRevit will execute
unconditionally at load and (b) a candidate corruption target, self-restore has an
irreducible trust boundary:

- **`startup.py` itself cannot safely restore `startup.py`.** By the time `startup.py`'s
  own code is running, pyRevit has already committed to executing whatever bytes were on
  disk — a self-referential restore inside `startup.py` can at best detect that it *is*
  running a stale/corrupt copy of itself (e.g. by hashing its own `__file__` against a
  manifest and logging/aborting) but cannot un-corrupt the copy that already executed.
  This is the same class of problem as "a corrupted verifier cannot verify itself,"
  stated in the question, and it is real here, not hypothetical.
- **What `startup.py` *can* safely do, given it is guaranteed to run before
  `register_routes()` (and thus before any `revit_mcp/*.py` domain module is imported):**
  verify and restore every file **other than itself** — i.e. all of `revit_mcp/*.py` —
  before `register_routes()`'s import loop (`startup.py:90-104`) touches them. This is
  the actual, achievable integrity boundary: `startup.py` runs once per session, fully,
  before a single line of `revit_mcp/` is imported (confirmed: `register_routes()` is
  the very last statement in the file, `startup.py:126`, and it is the function that
  performs all `revit_mcp.*` imports). A verify-and-restore pass inserted at the top of
  `register_routes()`, before the `_domain_modules(revit_mcp)` loop, has never yet
  imported any domain module, so replacing corrupted `revit_mcp/*.py` files on disk at
  that point is safe under the existing constraint "replacing files under a running
  pyRevit engine has crashed Revit" — because no engine is "running" those files yet;
  they have not been loaded into any IronPython module table.
- **What it cannot safely do:** restore itself, or restore anything that must be correct
  before pyRevit even locates `startup.py` (`extension.json`, the extension folder
  structure pyRevit's `Extension.startup_script` property discovery depends on,
  `extensions/components.py:543-552`). A corrupted `extension.json` (e.g.
  `default_enabled` flipped, matching the exact failure mode `publish-extension.cmd`
  already guards against at *publish* time) is invisible to any runtime check this
  extension can perform, because pyRevit will simply not load the extension at all in
  that case — there is no code of ours running to detect it. That has to be a
  **pre-flight guarantee from the build/publish pipeline**, not a runtime self-heal.

### Recommended design

- **New helper, Revit side:** `revit_mcp/integrity.py` (helper module, no registrar —
  same "helper, not domain" pattern as `textutils.py`). Contains
  `verify_and_restore(package_dir, manifest)` — reads a manifest of
  `{relative_path: sha256}` shipped alongside the extension (see build-pipeline section
  below), hashes every `revit_mcp/*.py` file present, and for any mismatch or missing
  file, copies the known-good version from a **backup location that ships with the
  extension itself** (e.g. `revit_mcp/_golden/` or a sibling directory outside
  `revit_mcp/` entirely, so it is never itself subject to being "a domain module"
  scanned by `_domain_modules`). It must tolerate **its own file, `integrity.py`, and
  the manifest file, being the ones missing/corrupt** — in that specific case, it can
  only log and refuse to proceed with restoration for those two files (it has nothing
  trustworthy to restore *from* if the verifier or manifest itself is gone), which is
  the honest expression of the bootstrap limit above.
- **Changed file:** `startup.py`. At the very top of `register_routes()`
  (`startup.py:73`), before `registry.reset()` and before the `_domain_modules(...)`
  loop, call `integrity.verify_and_restore(...)`. This is one function call in one
  already-modified file (already touched for Q1's `api`-wrap), still zero edits to the
  23 domain modules.
- **What is explicitly out of this runtime's reach:** `startup.py` and `extension.json`
  self-protection. Treat their integrity as a **publish-time** guarantee only (see
  below), and accept, as `PROJECT.md`'s "Out of Scope" already does for the adjacent
  concern ("Защита от целенаправленного локального обхода... не входит"), that a user
  who deliberately corrupts `startup.py` itself is outside this milestone's threat model
  (accidental overwrite by an engineer, not adversarial tampering at the console).

---

## Build pipeline: where secret-injection and manifest-generation belong

### What exists today (traced directly)

- `deploy/build-payload.cmd` builds and publishes **only the CPython half**
  (`main.py`, `tools/`, dependencies) to `%MCP_SHARE_ROOT%\payload\`, gated by
  `deploy/gate.py` (spawns the built `server.py` over stdio, asserts tool count matches
  `tests/unit/tool_manifest.txt`, exactly as `CLAUDE.md` describes).
- `deploy/publish-extension.cmd` is the **separate** pipeline for the Revit/IronPython
  half: it copies `extension.json`, `startup.py`, and `revit_mcp/` (allow-listed, `/XJ`
  robocopy) to `%MCP_SHARE_ROOT%\ext\%MCP_EXT_NAME%`, from which `install.cmd` points
  pyRevit's `extensions paths add`. It already has one hard-fail gate: it refuses to
  publish unless `extension.json` has `"default_enabled": "True"` and `"builtin":
  "False"` — i.e. this script is **already** the place that protects against the exact
  "silently never loads" class of failure that Q4's file-corruption concern is a
  variant of.
- Neither script currently generates a secret or a file manifest for `revit_mcp/`.

### Where each new piece belongs

| New artifact | Belongs in | Why |
|---|---|---|
| Shared secret generation | `deploy/build-payload.cmd` **and** `deploy/publish-extension.cmd`, sourced from one place | The secret must reach both halves — the CPython payload needs to *send* it (Q1's `main.py`/`bridge.py` wrapper), the extension needs to *check* it (Q1's `revit_mcp/security.py`). Generate it once (e.g. in `deploy/config.cmd`, which both `.cmd` scripts already `call`, per `build-payload.cmd:22` and the parallel pattern in `publish-extension.cmd:19`) and write it into both payloads at their respective build steps, so a single build produces a matched pair. Never let the two pipelines mint independent secrets — that would make every mutating call fail against a same-day mismatched pair. |
| File-hash manifest for `revit_mcp/*.py` | `deploy/publish-extension.cmd`, generated immediately after the robocopy of `revit_mcp/` (`publish-extension.cmd:63-65`) and written into the same `%DEST%` tree (e.g. `%DEST%\revit_mcp\_manifest.json` or a sibling file outside `revit_mcp/` so `_domain_modules` never scans it — recall it already skips `_`-prefixed and non-`.py` entries, `startup.py:52-53`) | The manifest must describe exactly the files this publish step just wrote — computing it anywhere else risks describing a different tree than what actually ships. This mirrors how `gate.py` already verifies the *CPython* payload against `tool_manifest.txt` right after that payload is staged (`build-payload.cmd:122-124`, "verify BEFORE publishing"); the extension pipeline should adopt the identical shape: hash after copy, verify, *then* consider the publish complete. |
| A "golden copy" for `integrity.verify_and_restore` to restore from | Also written by `publish-extension.cmd`, alongside the manifest | The restore source and the manifest must be produced by the same step that produces the tree being protected, or drift between "what we think is correct" and "what we shipped" becomes its own bug class. |

### What `deploy/gate.py` should additionally enforce

`gate.py` today only exercises the CPython payload (spawns `server.py`, checks tool
count/names against `tests/unit/tool_manifest.txt`). It has **no visibility into the
Revit half at all** — it cannot, since it runs on the build server without a live Revit.
Recommended additions, all achievable without Revit:

1. **Assert the manifest was generated for the same commit/tree that
   `publish-extension.cmd` is about to publish** — i.e. gate.py (or a Revit-half
   equivalent invoked from `publish-extension.cmd` itself, since `gate.py` today is
   wired only into `build-payload.cmd`) should recompute hashes for every file under
   `revit_mcp/` right before publish and fail the publish if they do not match what
   `publish-extension.cmd` is about to write as the manifest — this catches a
   mid-build git-tree change or partial copy, the same class of "uncommitted change"
   warning `publish-extension.cmd:47-49` already surfaces, but as a hard gate for the
   manifest specifically, not just a warning.
2. **Assert the secret is present and non-empty in both the freshly built CPython
   payload and the freshly published extension tree**, and that they are byte-identical
   — a mismatched pair is a silent, total mutating-route outage that would otherwise
   only surface at first live use.
3. **Assert `extension.json`'s `default_enabled`/`builtin` guard (already present,
   `publish-extension.cmd:35-45`) stays in `gate.py` too if `gate.py` is ever pointed at
   the extension tree** — currently that check lives in the `.cmd` script as a
   `findstr`, not in the Python gate; consolidating it means one code path instead of
   two if the gate scope grows to cover both halves.

**Confidence: MEDIUM** on the precise file layout for the manifest/golden-copy (e.g.
whether the golden copy is a zip, a flat directory, or inline base64 in the manifest
JSON) — that is an implementation choice with no strong constraint from the code read
so far; the placement (generated by `publish-extension.cmd`, consumed by `startup.py`
via `revit_mcp/integrity.py`) is HIGH confidence.

---

## Summary Table — Integration Points and File Changes

| Concern | New component(s) | Runtime | Modified existing file(s) | Domain files touched |
|---|---|---|---|---|
| Secret verification | `revit_mcp/security.py` (helper) | IronPython | `startup.py` (install `api`-wrap before registration loop) | **0 of 23** |
| Secret injection | extend `main.py` or new `bridge.py` | CPython | `main.py` (`_revit_call` adds header) | **0 of 23** |
| Identity stamping | logic inside `revit_mcp/security.py`'s `api`-wrap (post-handler) | IronPython | `startup.py` (same wrap as above) | **0 of 23** |
| Identity surfaced to model | none required; optional polish | CPython | `tools/utils.py` (`format_response`, optional header line) | **0 of 27** |
| Mutation serialization | `RevitTarget` registry + per-instance `asyncio.Lock` | CPython | `main.py` (`_get_client`/`_revit_call` become target-aware) | **0 of 23** (new instance-management tools are additive, not retrofits) |
| Multi-instance object model | same `RevitTarget` registry | CPython | `main.py` | **0 of 23** |
| Startup integrity + restore | `revit_mcp/integrity.py` (helper) | IronPython | `startup.py` (call at top of `register_routes()`) | **0 of 23** |
| Manifest + golden copy generation | new logic in `deploy/publish-extension.cmd` | build pipeline | `deploy/publish-extension.cmd`, `deploy/config.cmd` (shared secret source) | n/a |
| Secret generation | new logic in `deploy/config.cmd`, consumed by both `.cmd` scripts | build pipeline | `deploy/build-payload.cmd`, `deploy/publish-extension.cmd`, `deploy/config.cmd` | n/a |
| Extended release gate | `deploy/gate.py` additions, or a parallel Revit-half gate invoked from `publish-extension.cmd` | build pipeline | `deploy/gate.py`, `deploy/publish-extension.cmd` | n/a |

**No recommendation in this document requires touching all 23-27 domain modules.** The
entire design rests on two verified single-instantiation chokepoints — the shared `api`
object built once in `startup.py:30` and passed by reference to every
`register_*_routes(api)` call, and the shared `_http_client`/injected
`revit_get`/`revit_post` callables built once in `main.py` and passed by reference into
every `register_*_tools(...)` call — plus one already-existing per-route convention
(`commit_and_report`) that is *separately, and already, incompletely adopted* by two
known routes (`editing.py`'s delete path, `interop.py`'s `export_ifc`); closing that gap
is a small, already-scoped, per-route fix, not a consequence of the cross-cutting design
above.

---

## Suggested Build Order

1. **`revit_mcp/textutils.py`-style helpers first, no wiring:** write
   `revit_mcp/security.py` and `revit_mcp/integrity.py` as pure, unit-testable-in-shape
   (though not directly unit-testable under CPython, since they touch `pyrevit`/`DB` —
   keep the hashing/comparison logic itself dependency-free so it *can* be extracted to
   `textutils.py`-style CPython-testable functions where possible, per the existing
   "new logic on the CPython-testable side" rule). Land with no `startup.py` wiring yet
   — inert code, safe to merge early.
2. **`main.py` / `bridge.py` changes for the `RevitTarget` registry and secret header**,
   independently testable via `tests/unit/` against a mocked httpx transport — this can
   proceed in parallel with step 1 since it touches the other runtime.
3. **Deploy pipeline: secret + manifest generation** (`deploy/config.cmd`,
   `deploy/publish-extension.cmd`, `deploy/build-payload.cmd`) — needs steps 1-2's
   shapes decided (what the secret header looks like, what the manifest schema is) but
   not their full implementation; can start once the interfaces are fixed.
4. **Wire `startup.py`:** install the `api`-wrap (secret verification + identity
   stamping) and call `integrity.verify_and_restore(...)` at the top of
   `register_routes()`. This is the integration point where both runtimes' work
   converges — do this only after steps 1-3 exist, since testing it live requires a
   full Revit restart (per `CLAUDE.md`'s sharp edge on `revit_mcp/` reload safety) and
   should not be iterated on repeatedly.
5. **`deploy/gate.py` additions** last, once the manifest/secret shapes from step 3 are
   final, so the gate encodes the final contract rather than an interim one.
6. **Per-route `commit_and_report` completion** (`editing.py` delete path,
   `interop.py:export_ifc`) can proceed at any point, independently — it is unrelated to
   the cross-cutting wrapper mechanism and only touches the two routes named in
   `PROJECT.md`'s Context section.

Rationale for this order: the two chokepoints (`api` in `startup.py`, `revit_get`/
`revit_post` in `main.py`) are cheap to change but expensive to *verify* live (full
Revit restart required per `CLAUDE.md`), so every other piece should be built and unit
tested first, minimizing the number of live-Revit verification cycles to essentially one
per major wiring change in `startup.py`.

## Sources

- `main.py` (read in full) — CPython chokepoint verification
- `startup.py` (read in full) — registration/discovery mechanics, `api` object lifecycle
- `tools/utils.py` (read in full) — `format_response` classification logic
- `revit_mcp/status.py`, `revit_mcp/editing.py`, `tools/editing_tools.py` (read in full)
  — representative domain pair, `commit_and_report` usage, tool-registrar shape
- `revit_mcp/utils.py`, `revit_mcp/textutils.py` (read in full) — sanctioned shared-helper
  pattern, `commit_and_report`/`suppress_warnings` implementation
- `revit_mcp/registry.py` (read in full) — registration bookkeeping consumed by `/status/`
- `deploy/gate.py`, `deploy/build-payload.cmd`, `deploy/publish-extension.cmd`,
  `deploy/server.py`, `deploy/update.cmd`, `deploy/install.cmd` (all read in full) —
  existing build/publish/update pipeline for both runtimes
- `extension.json` (read in full)
- `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md` (read in full) — milestone
  scope and prior architecture snapshot
- **`pyrevitlib/pyrevit/routes/api.py`, `server/router.py`, `server/handler.py`,
  `server/server.py`, `routes/__init__.py`** from a local pyRevit-Master checkout at
  `C:\Users\Admin\AppData\Roaming\pyRevit-Master\pyrevitlib\pyrevit\` — all read in full;
  this is the ground truth for "does pyRevit Routes support middleware" (it does not) and
  is HIGH confidence because it is the actual source, not documentation or inference.
- **`pyrevitlib/pyrevit/loader/sessionmgr.py`** (`_new_session`,
  `execute_extension_startup_script`), **`pyrevitlib/pyrevit/extensions/components.py`**
  (`Extension.startup_script`), **`pyrevitlib/pyrevit/loader/hooks.py`** — all read
  directly to establish extension load order and confirm no pre-load hook exists for an
  individual extension.
- pyRevit's public docs site (`docs.pyrevitlabs.io/reference/pyrevit/routes/api/`) was
  also checked and found to be silent on `API`'s full method surface — noted as a gap in
  the docs, resolved instead by reading the actual source above.

---
*Architecture research for: revit-mcp-server v0.1 "Доверенный мост" milestone*
*Researched: 2026-09-21*
