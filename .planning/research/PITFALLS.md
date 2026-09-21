# Pitfalls Research: Identity, Secret Auth, Integrity Self-Restore, Serialization, Audit

**Domain:** Adding trust/safety foundation (v0.1 "Доверенный мост") to a live pyRevit/Revit MCP bridge
**Researched:** 2026-09-21
**Confidence:** HIGH for claims tied to this repo's own code/history; MEDIUM for Revit API behavior verified against Autodesk docs but not exercised live in this environment; explicitly flagged where inferred only

## How to read this document

Every pitfall below is ranked by **(likelihood in this environment) × (cost if hit)**, not by
generic severity. "Already hit once" pitfalls rank above novel ones even when the novel one
sounds scarier, because this project's own history (silent rollback, 22/23 domains lost to one
import style, IronPython-2-builtin runtime misdetection) shows failures here are systemic — one
wrong idiom reproduces across every module that copies it. The five capability areas map to
question numbers 1–5 in the brief; pitfalls are grouped by area but cross-references are called
out explicitly where a mistake in one area causes a symptom that looks like it belongs to another.

---

## Critical Pitfalls

### Pitfall 1: The 200-vs-non-200 contract gets broken by the new auth layer, resurrecting the exact silent-success bug that was just fixed

**What goes wrong:**
The `rolled_back` fix (`param-write-rolls-back`) works ONLY because `_revit_call` in `main.py`
treats any non-200 response as a `str` (`f"Error: {status_code} - {text}"`), which
`format_response` passes through untouched, and because 409 specifically was chosen over 200
to avoid `format_response`'s error-classification heuristic missing it. A shared-secret gate is
a brand-new response path that must independently satisfy this same contract. Two failure modes
are equally likely: (a) the secret check inside a route handler returns **200** with
`{"error": "invalid secret"}` or `{"status": "unauthorized"}` — same trap as `rolled_back`
would have hit, since `format_response`'s failure detection is a hardcoded set of exact
string values (`error`/`failed`/`failure`/`exception`) and `"unauthorized"` is not in it, so an
unauthenticated write attempt would render as ordinary data to the model; or (b) the check
happens in pyRevit's routes dispatch layer *before* the route body runs, in which case it is
pyRevit's own response shape, not `routes.make_response(...)`, and may not even carry a JSON
body `_revit_call` can render sensibly — this is the same category of problem documented for
the broken `application/json` parse (pyRevit's own layer answering instead of the route).

**Why it happens:**
The auth check is naturally written "does this look like the parameter-set / rollback pattern"
by a developer who read `commit_and_report` — but 409 was chosen for a specific, narrow reason
(avoid `format_response`'s success-shaped-dict trap), not as a general "problem happened" code.
Auth failures need their own convention decision, and if that decision is made ad hoc per-route
instead of via one shared helper, some routes will get it right and others won't — mirroring
the actual, lived history of `commit_and_report` adoption, which the project's own `PROJECT.md`
records as NOT rolled out to all mutating routes yet (`delete_elements` and `export_ifc` still
call bare `t.Commit()`).

**How to avoid:**
- Use HTTP 401 or 403 for the secret-mismatch case (distinct from 409's rollback semantics),
  and add it to a documented, tested contract next to the existing `rolled_back` one — ideally
  the same file/test (`tests/unit/test_format_response.py`) gets a
  `test_unauthorized_401_reaches_the_model_as_a_visible_error` sibling test and a
  `test_unauthorized_dict_is_not_yet_a_recognized_failure_signal` alarm test, matching the
  existing pair exactly.
- Do the secret check in **one shared helper** called from every mutating route's handler body
  (not from pyRevit's dispatch layer, not duplicated per-route), so there is exactly one place
  that decides the status code — the same "one contract, many call sites" lesson `commit_and_report`
  already teaches this codebase.
- Verify with a live curl/httpx test that a 401 response's body actually reaches `_revit_call`
  as a string and not an exception — pyRevit's HTTP/1.0 server has already surfaced one
  unexpected-shape bug (`ReadError` under a proxy) so don't assume happy-path framing.

**Warning signs:**
A code review or manual test where an unauthenticated mutation attempt returns `200` with any
body at all. Grep for `routes.make_response(data=.*status=200` near any new auth-check code, and
grep for hardcoded `state=200` on any response containing "secret" or "auth" in the same
function.

**Phase to address:**
Same phase as secret-auth introduction — this is not a follow-up, it is the acceptance criterion
for that phase. Do not consider "secret rejects bad requests" done until the 401 path has a
regression test proving the *client-visible* shape, the same way 409 does.

---

### Pitfall 2: Self-restore triggers (or races) the exact Reload-crashes-Revit failure mode this project has already documented

**What goes wrong:**
The stated design decision (`PROJECT.md`: "Самовосстановление payload — только при старте") is
correct, but "at start" is ambiguous between two very different moments: (a) pyRevit extension
load/reload time (`startup.py` executing inside a running Revit process), and (b) Revit process
launch time (before pyRevit has loaded anything). If self-restore is wired into `startup.py`
itself — the natural place to put "check integrity, fix if needed" — then a file replacement
happens on ANY pyRevit reload trigger, not just a genuine Revit process restart: pyRevit reloads
on extension-manager "Reload" clicks, on some settings changes, and potentially on its own
auto-reload-on-file-change feature if that's enabled for this extension. Since the extension
directory is a **junction to the repo** on the dev machine, and a developer is expected to be
editing files continuously, any reload-triggered restore either (a) does nothing useful (files
already match) or (b) — the dangerous case — treats an in-progress edit as "corruption" and
overwrites the developer's unsaved-to-git working tree changes mid-edit, which is silent data
loss disguised as a security feature, on top of already being the documented Revit-crashing
Reload path.

**Why it happens:**
"At start" reads as an implementation detail until you have two different processes (Revit.exe
launch vs. pyRevit extension reload) that both look like "start" from inside `startup.py`, and
this codebase's own history shows exactly this kind of ambiguity (two things that look identical
from one vantage point, e.g. two Revit processes both answering on :48884) causing real incidents.

**How to avoid:**
- Gate self-restore on a signal that is unambiguously "fresh Revit process," not "pyRevit
  (re)loaded the extension." A reasonable proxy: check whether this is the *first* time
  `startup.py` has run in this Revit process's lifetime (e.g. a module-level flag or a
  `System.Diagnostics.Process.GetCurrentProcess().StartTime` comparison), not merely "did
  `startup.py`'s top level execute" — that also runs on Reload.
  **This should be verified live against pyRevit's actual extension lifecycle hooks** (does
  pyRevit distinguish "engine reload" from "extension reload" from "Revit process start" in any
  exposed API?) before committing to a mechanism — do not assume `startup.py` running is a proxy
  for "new process" without checking pyRevit's own load-event documentation.
- On the dev machine specifically (junction, not copy), self-restore should be **disabled
  entirely** or at minimum diffed-and-logged-only (no actual file write), because there is no
  meaningful distinction there between "corruption" and "a commit not yet made" — the junction
  means dev-tree state IS the deployed state by design. Key off an explicit environment marker
  (e.g. presence of `.git` in the extension directory, or an explicit opt-out env var) rather than
  trying to infer "is this a junction" from within IronPython, which has no reliable way to detect
  a directory junction vs. a real directory without shelling out.
- Never wire restore into a live pyRevit Reload button-driven code path. If restore must run
  under a live engine at all (as opposed to only being checked and reported, with the actual
  file copy deferred to next full process start), that is itself the highest-risk sub-decision
  in this whole milestone and deserves its own explicit go/no-go, given the documented
  Reload-crashes-Revit history.

**Warning signs:** Any restore-triggering code path reachable from a function that also runs on
pyRevit's Reload button (check by tracing what `startup.py`'s top-level code calls, and whether
any of it is also invoked by pyRevit's own reload machinery, not just process start). A restore
event logged with a timestamp that doesn't correlate with a new Revit.exe PID.

**Phase to address:** The integrity/self-restore phase, before any restore-writes-files code is
merged — this is a design gate, not a bug to catch in review. Validate the "new process vs.
reload" detection mechanism live (open Revit, click Reload, confirm no restore fires; kill and
restart Revit, confirm restore does fire) before shipping to any pilot machine.

---

### Pitfall 3: Verifying integrity by content hash breaks on the very things that differ between the repo and the deployed copy in ordinary, expected ways

**What goes wrong:**
Two deployment topologies exist per `PROJECT.md`: dev machine = junction (file IS the repo file,
byte-for-byte, always); pilot machines = **copies**, which is exactly where `git` line-ending
normalization (`core.autocrlf`), `__pycache__`/`.pyc` artifacts IronPython may generate at
import time, and any editor/AV-scanner touch (timestamp change, BOM insertion) can make a
byte-identical-in-intent file hash differently from the "reference" hash captured at build time.
A hash-based verifier that doesn't explicitly exclude `__pycache__`/`*.pyc` and doesn't hash with
line-ending normalization matching how the reference hash was generated will report corruption
on machines that were never touched, and if self-restore is wired to that verifier, it will
"restore" perfectly good files — the restore-loop case explicitly flagged in the question:
restore, verify again, still mismatched (because the hash function itself is unstable, e.g. it
included `.pyc` files that regenerate on next import), restore again, forever, potentially
crashing Revit on each pass if restore isn't purely at-start (see Pitfall 2).

**Why it happens:**
IronPython does write compiled artifacts in some configurations, and this project's Revit half
has already shown git-line-ending sensitivity matters (`exec`'s CRLF rejection is explicitly
documented as a sharp edge for a *different* reason, but it's the same underlying fact: this
codebase's line endings are not uniform/guaranteed and IronPython cares). A verifier built by
someone thinking "just hash the files" without enumerating what's actually inside the extension
directory on a real pilot machine will miss this.

**How to avoid:**
- Hash only the tracked file set (derive the manifest from `git ls-files`, not `os.walk` over the
  extension directory) so caches, `__pycache__`, `.pyc`, and any stray local file are structurally
  excluded rather than pattern-excluded (pattern lists rot; a file-list-from-git does not).
- Decide explicitly whether the reference hash is computed over working-tree bytes (post-checkout,
  whatever `autocrlf` produced) or over git's blob content (pre-checkout-filter) — and hash the
  deployed copy the same way. The safest choice given `autocrlf` risk: hash **working-tree bytes
  as checked out on that machine** (i.e., generate the reference manifest as part of the build/
  payload step on a machine with the same git config as the target, not as a hardcoded git-blob
  hash), since that's what's actually present to compare against.
- Treat "verifier can't run" (missing reference manifest, unreadable file) as **fail closed for
  restore-triggering, fail open for gating an already-running Revit** — i.e., don't refuse to
  serve requests just because integrity couldn't be checked (that turns a hashing bug into a
  total-outage bug, which is strictly worse for the stated threat model of "accidental
  overwrite," not "attacker"), but also don't silently claim "verified OK" when verification
  didn't actually run — surface a distinct third state (`unverified`) in `/status/`, not a
  boolean.
- Cap restore attempts (e.g., restore once per process lifetime, then report `integrity: "still
  mismatched after restore"` rather than looping) as a hard backstop independent of getting the
  hash function right, because the hash function WILL have edge cases no one enumerates up front.

**Warning signs:** Any pilot machine reporting integrity failure with zero actual file changes
(compare hashes before/after a "restore" — if they're identical, the verifier's hash was never
wrong, only its *comparison* was). A `.pyc` or `__pycache__` path appearing in a diff/mismatch
report.

**Phase to address:** Integrity/self-restore phase. The manifest-generation mechanism (from
`git ls-files`, not filesystem walk) is a prerequisite decision, not a detail to fill in during
implementation — get this wrong and every subsequent test on a pilot machine is noise.

---

### Pitfall 4: Network-share unreachability during integrity check is treated the same as "verified corrupt," triggering restore-from-nothing or blocking startup

**What goes wrong:**
If the reference manifest/golden copy for restore lives on a network share (a reasonable
design — it's referenced as an option in the milestone's "restore at start" framing, and Genpro
is described as a company with `RSN://` Revit Server infra, implying network storage is normal
here), then a transient share unavailability (VPN not yet up, share server rebooting, DFS
namespace hiccup) at the exact moment `startup.py` runs is not a rare edge case — it is a normal
Monday-morning occurrence for a laptop-based engineer. If unreachability is not distinguished
from "hashes don't match," the natural but wrong implementations are: (a) treat "can't reach
reference" as "everything is corrupt," attempt a restore, and either fail with a confusing
network error mid-restore (worse than doing nothing) or effectively delete/replace local files
with nothing meaningful; or (b) block Revit startup / extension load entirely waiting for the
share, turning a transient network blip into "Revit won't start for BIM engineers," which given
this project's own definition of the threat model (accidental overwrite, not attacker) is a
self-inflicted worse outcome than the risk being defended against.

**Why it happens:**
"Verify integrity" and "reach the reference" are two different failure axes that collapse into
one boolean (`verified: true/false`) if not modeled explicitly, and the natural retrofit onto
existing code (`suppress_warnings`'s own `except Exception: pass` pattern, `_FailureSwallower`'s
original silent-failure default) is exactly this kind of "any exception means the negative
outcome" collapse — a pattern this codebase has now separately caught and fixed at least twice
(the rollback-swallowing bug, the `suppress_warnings`-swallows-its-own-setup-failure bug noted
in CONCERNS.md). A third instance of the same shape (network-unreachable → treated as failure)
in the integrity feature would repeat a known anti-pattern in new code.

**How to avoid:**
- Explicit three-state model: `verified_match`, `verified_mismatch`, `unverifiable` (network/IO
  error reaching the reference) — never collapse the third into the second.
- **Fail open for availability, fail closed (but non-blocking) for trust claims**: Revit must
  still start and the Routes server must still come up when the reference share is unreachable —
  do not block extension load on network I/O (this also avoids adding a new hang source to the
  existing "requests during Revit init already hang" problem — see Pitfall 9). But `/status/`
  should report `integrity: "unverifiable"` distinctly from `integrity: "ok"`, so a human/monitor
  can tell the difference between "confirmed good" and "we don't actually know."
  This is a deliberate, project-specific call given the stated threat model — a generic security
  posture might argue fail-closed, but that is not this project's model (accidental local
  overwrite, not a determined attacker) and blocking Revit startup fleet-wide over a share hiccup
  would be a worse outcome than the risk being mitigated.
- Never attempt a restore write when the reference could not be confidently read in full — a
  partial/interrupted read of the reference itself (not just the local copy) is a second version
  of the "partially copied file" question in the prompt, and applies symmetrically: verify the
  reference's own integrity (e.g., a manifest checksum covering the whole reference set) before
  trusting it enough to copy from.

**Warning signs:** Extension load taking noticeably longer when off the corporate network/VPN.
Any restore event correlated with known network-maintenance windows on the reference share.

**Phase to address:** Integrity/self-restore phase — the three-state model must be in the design
before any code is written, since retrofitting it after a boolean has shipped means redefining
what `/status/` already reports (a compatibility break for anything that started depending on
`integrity: true/false`).

---

### Pitfall 5: A client-side asyncio.Lock in `main.py` is advisory-only and gives false confidence against the actual concurrency source (a second MCP client, or Revit's own external-event queue)

**What goes wrong:**
The stated goal ("Мутации сериализованы — параллельные транзакции в однопоточный Revit API
исключены") is achievable *for calls that go through this one `main.py` process*, but nothing
stops a second MCP client (a second Claude Desktop / Claude Code session, the MCP Inspector, a
curl script, or literally the existing `/execute_code/` escape hatch hit directly) from issuing
a concurrent mutating POST that bypasses the lock entirely, because the lock lives in Python
process memory, not in Revit or in the Routes server. The team could ship a lock, watch it work
perfectly in every test that only ever launches one `main.py`, and still have concurrent
transactions reach Revit the moment a second client (or the pyRevit Routes server directly)
issues a request — this is the same *shape* of false confidence as the two-Revit-instances/
one-port problem already documented: a mechanism that looks like mutual exclusion but only
covers one of the actual paths to the resource.

**Why it happens:**
`main.py`'s lock is the only place a CPython developer *can* put a lock (they can't touch
`revit_mcp/`'s IronPython side meaningfully for real mutex semantics — the routes server there
handles one request at a time already per the external-event queue, per the question's own
framing), so it's natural to conflate "I serialized calls from my process" with "I serialized
writes to Revit." They are not the same claim, and the milestone's own requirement text should
be read as "reduce the *common* concurrency path (this server's own connection pool sending up to
20 simultaneous requests)," not as "guarantee exclusivity" — the second is not achievable from
this side of the process boundary without a change on the Revit/pyRevit side (e.g., a
Revit-side single-slot semaphore file, or accepting that the external-event queue itself already
does this serialization, just "badly" per the question's own framing, meaning slowly/without
prioritization rather than incorrectly).

**How to avoid:**
- Document the lock's actual scope precisely: "serializes mutating calls issued through this
  `main.py` process" — do not claim or imply it prevents concurrent Revit transactions from any
  source, including a second `main.py`, curl, or `/execute_code/` called directly.
  This directly interacts with Pitfall 1's auth work: if a shared secret is required for
  mutations, that *incidentally* narrows (but doesn't eliminate) the "other client" risk, since a
  same-process lock plus a shared secret at least means all *legitimate* mutation paths funnel
  through code that could, in principle, also share a lock — but only if the secret-holder is
  disciplined to use one `main.py` instance, which is a process/deployment convention, not
  something the code can enforce.
  **Do not oversell this as a fix for the concurrency problem** — pair the roadmap language with
  the accurate claim: it's harm reduction for the dominant case (one server, its own connection
  pool), not a correctness guarantee.
- Investigate whether Revit's external-event queue already provides the real serialization
  (per the question's framing: "does serializing hide a real problem... or fix it?"). Given
  `commit_and_report`'s existence and the fact that transactions in Revit's API are inherently
  single-document, single-transaction-at-a-time (confirmed against Autodesk's own Revit API
  Developer's Guide: "a document can have only one transaction open at any given time"), the
  external-event queue is very likely ALREADY the true serialization point, and a client-side
  lock's actual value is *not* correctness (Revit already refuses a second concurrent
  transaction on the same document) but **avoiding wasted/duplicate work and confusing partial
  failures under load** (e.g., 20 concurrent HTTP requests all opening transactions that fight
  over the same elements, each individually valid but collectively producing worksharing/
  ownership-style errors that then get misattributed to something else — plausibly relevant to
  the still-open parallel hypothesis in `param-write-rolls-back`). If that's confirmed, the lock
  is about **request-queueing UX and avoiding pointless 30s timeouts stacking up**, not about
  preventing an otherwise-possible double-transaction — say so explicitly in the design.
- **This is inferred from Autodesk API documentation on Transaction semantics; it was not
  exercised live in this environment (no live Revit access here) and should be confirmed against
  a live two-concurrent-request test before being treated as settled** — specifically, confirm
  what actually happens today (hang? error? silent queueing?) when two overlapping mutating
  requests hit the Routes server, before designing the lock around an assumption of what Revit
  does.

**Warning signs:** A design review or PR description that says the lock "prevents concurrent
transactions" without qualifying "issued through this process." A test suite that only ever
starts one `main.py` process and calls this "concurrency tested."

**Phase to address:** Serialization phase — as a documentation/scoping correction at minimum,
and ideally preceded by the live "what does Revit actually do with two overlapping requests
today" experiment during that phase's discussion/spec step, since it changes what the lock is
even for.

---

### Pitfall 6: Holding the lock across the full `_revit_call` 30s timeout starves `/status/`, turning a slow mutation into a fleet-wide diagnosability outage

**What goes wrong:**
If the serialization lock is acquired before the HTTP call to Revit and released only after the
response returns (the naive, obvious implementation), then a single slow mutating call — clash
detection is explicitly called out elsewhere in this repo's own docs as sharing the same 30s
timeout budget as a status ping — holds the lock for up to 30 seconds. If `/status/` (a
**read-only GET**, explicitly meant to be pollable during Revit startup per the existing
"poll status before the first POST" convention) is naively routed through the *same* lock
(e.g., because a developer serializes "all calls" rather than "all mutating calls"), then the
one tool that exists specifically to let a human or client find out *why things are hung*
becomes unavailable exactly when something is hung — the worst possible time.

**Why it happens:**
"Serialize mutations" is easy to over-generalize to "serialize everything" during implementation,
especially since the lock has to live somewhere central (likely wrapping `_revit_call` in
`main.py`, which is shared by both mutating and read routes) — the path of least resistance is
one lock around the whole function rather than a conditional based on HTTP method or an explicit
per-tool flag.

**How to avoid:**
- Gate the lock on an explicit allowlist of mutating endpoints (or, inverted, an explicit
  never-locked allowlist containing at minimum `/status/`), not on "all POST calls" (some POSTs,
  like `/execute_code/` running read-only inspection code, are not inherently mutations, though
  given `/execute_code/`'s unrestricted nature it may be simplest/safest to always serialize it —
  a judgment call to make explicitly, not by accident).
  Given this is a small, enumerable set of routes (the manifest already lists all 54 tools),
  build the lock gate from the tool manifest / an explicit per-route flag rather than inferring
  "mutating" from HTTP verb.
- `/status/` must remain reachable and fast regardless of lock state — verify this with a test
  that holds the lock (simulate a slow mutating call) and confirms a concurrent `/status/` call
  still returns promptly. This is directly testable without live Revit: mock `_revit_call`'s
  transport layer, hold the lock, assert `/status/`'s code path never blocks on it.
- Keep the existing per-tool timeout override precedent (`status_tools.py` already overrides the
  default 30s) as the model: status calls get their own short timeout AND bypass the mutation
  lock entirely, not just a shorter wait *for* the lock.

**Warning signs:** A `/status/` call taking anywhere close to the mutation timeout (30s) under
concurrent load in testing. Any lock acquisition code that doesn't visibly branch on route/tool
identity.

**Phase to address:** Serialization phase, as an explicit design requirement and test case
("status stays responsive under a held mutation lock"), not an incidental property to hope for.

---

### Pitfall 7: A cancelled or timed-out mutating call leaves the lock held, deadlocking every subsequent mutation

**What goes wrong:**
If the lock is acquired with a bare `await lock.acquire()` / manual `release()` rather than
`async with lock:`, or if `_revit_call`'s existing `try/except Exception: return f"Error: {e}"`
pattern (which already swallows all exceptions into a string return) is copied into the new
locked code path without also guaranteeing release in a `finally`, then any exception — including
`httpx.TimeoutException` on the existing 30s timeout, or an `asyncio.CancelledError` from the MCP
client disconnecting mid-call — can exit the locked region without releasing the lock. Every
mutation after that point queues forever (or until process restart), which will look identical
to "Revit is hung on a modal dialog" from the outside (the exact symptom this project has an
entire existing sharp-edge entry about) but is actually a Python-side deadlock unrelated to
Revit at all — a serious diagnostic red herring given how well-trained this team now is to expect
"hung request = modal dialog on the Revit side."

**Why it happens:**
`_revit_call`'s existing exception handling style (broad `try/except Exception`, return an error
string, move on) is a reasonable pattern for *stateless* HTTP calls, but a lock is *stateful*
across the call — the existing style must change shape (add a `finally: lock.release()` or,
much more simply, use `async with lock:` so release is unconditional) specifically because this
new code introduces state that outlives a single try/except the old pattern didn't have to
manage.

**How to avoid:**
- Use `async with lock:` exclusively — never manual `acquire()`/`release()` pairs — so release is
  structurally guaranteed regardless of how the block exits (return, exception, cancellation).
- Add a regression test that simulates a timeout/exception inside the locked region and asserts
  the lock is released afterward (acquire it again with a short timeout in the test and confirm
  it succeeds) — cheap to write, and this exact bug is invisible in any test that only checks the
  happy path.
- Consider wrapping lock acquisition itself with a timeout (`asyncio.wait_for(lock.acquire(), ...)`)
  so that even if a release bug slips through, callers get a clear "lock timeout" error rather than
  an indefinite hang — this converts a silent deadlock into a diagnosable one, consistent with
  this project's broader theme (per the `rolled_back` fix) of preferring loud, specific failures
  over silent ones.

**Warning signs:** Any mutation hanging with `/status/` simultaneously reporting Revit healthy
and responsive (this is the tell that distinguishes a Python-side lock deadlock from an actual
Revit-side modal-dialog hang — if `/status/` is unaffected per Pitfall 6's fix, but mutations are
all stuck, the lock is the suspect, not Revit).

**Phase to address:** Serialization phase — implement with `async with` from the first commit,
don't ship manual acquire/release and plan to "harden it later."

---

### Pitfall 8: `stateless_http=True` means no per-session state exists to anchor a lock or a "which client is queued" identity — the lock must be module-global, and anything assuming session affinity will silently not work

**What goes wrong:**
`stateless_http=True` (already set in `main.py`, with the comment "for better compatibility") means
FastMCP does not maintain server-side session state tied to a client connection across calls — each
request is handled independently. A design that tries to attach the mutation lock or a "this
client is currently mutating" marker to anything resembling a session object will find there is no
stable session to hang it on under the HTTP transports (`--streamable-http`, `--sse`, `--combined`);
under stdio (the default, single-process-per-client transport) this isn't an issue since there's
exactly one client per `main.py` process anyway, but the codebase supports multiple transports and
any lock design should not silently assume stdio's one-client-per-process shape when `--combined`
explicitly serves multiple transports/clients from one process.

**Why it happens:**
`stateless_http` is easy to read as "doesn't affect me, I'm not using sessions" when actually
designing a lock, but the lock IS a piece of cross-request state, and the natural instinct
("attach it near the session/context object since that's where per-client state usually lives")
doesn't have a home to land on here.

**How to avoid:**
- Put the lock at true module/global scope in `main.py` (next to `_http_client`), matching the
  existing pattern for the one shared `httpx.AsyncClient` — this is already the codebase's
  established idiom for "one shared resource, all callers use it," so follow it rather than
  inventing a session-scoped alternative.
- If the audit log (capability 4) needs to attribute a mutation to "which caller," that identity
  must come from the request/tool-call payload itself (e.g., an MCP client identifier if one
  exists, or simply "no per-client identity is available under stdio/stateless-http, so audit
  entries are per-process, not per-client" — state this limitation rather than building a fragile
  session-tracking shim to work around it.

**Warning signs:** Any code reaching for `ctx.session` or similar to store lock/queue state, given
`stateless_http=True` is already configured — a design that requires session persistence
contradicts an existing, deliberate configuration choice and should be caught in review before
implementation.

**Phase to address:** Serialization phase, design step — confirm the lock's home is a module
global before writing code.

---

### Pitfall 9: Secret-checking code adds a new hang source on top of the existing "requests during Revit init hang" problem, or a new place where a mismatched secret becomes undiagnosable

**What goes wrong:**
Two distinct bootstrap-ordering problems compound here. First: if the secret check happens
inside a route handler that runs through Revit's external-event queue (like every other mutating
route), then a request with a *wrong* secret sent while Revit is still initializing will still
hang exactly like today's documented behavior — the secret mismatch is never even evaluated
until the queue pumps, so the operator sees an indistinguishable hang, not a fast, clear "401."
Second, and more serious for operability: if the secret is wrong AND `/status/` (or an
equivalent lightweight diagnostic) is *also* gated by the secret, there is no way to ask the
running system "why is my secret failing" without already having a working secret — a classic
bootstrap lockout. Given this project's stated environment (secret baked into the payload at
build time, per the `PROJECT.md` decision "Секрет и политика вшиваются в payload при сборке"),
a secret mismatch most plausibly means "server payload and client payload were built from
different versions" — exactly the kind of mismatch a diagnostic tool should surface clearly, but
cannot if the diagnostic tool itself requires the secret to answer.

**Why it happens:**
Gating "everything" behind the secret is the simplest mental model ("mutations need a secret" 
generalizes to "the whole API needs a secret" without a deliberate carve-out), and the carve-out
requires an explicit design decision the question itself flags: keep `/status/` usable for
diagnosis while gating mutations.

**How to avoid:**
- `/status/` (GET, read-only, already designed to answer fast including the 503 "no active
  document" case) must remain **unauthenticated** — this is explicitly a diagnostic surface, and
  the project's own threat model (accidental overwrite / network access to mutation, not
  determined local attacker) does not require hiding "Revit is running, here is its health"
  behind a secret. Anything more sensitive that `/status/` might later report (e.g. document path)
  should be considered separately, but health/registration/degraded-domain info should stay open.
  Extend `/status/` (or add a small unauthenticated diagnostic addition) to report *whether* the
  server's expected secret is configured/present, WITHOUT ever echoing the secret value itself,
  so a mismatch is diagnosable as "client sent a secret, server has one configured, they don't
  match" versus "server has no secret configured at all" versus "client sent nothing" — three very
  different failure causes that a bare 401 collapses into one.
- Evaluate the secret **before** entering the Revit external-event dispatch path wherever
  technically possible (i.e., in the route handler's very first lines, before touching `doc` or
  scheduling any Revit-side work) so a bad secret fails fast even while Revit is still
  initializing, rather than joining the queue and hanging with everything else. This needs to be
  verified against how pyRevit's routes framework actually structures request handling (does the
  handler function itself run before or after the external-event hand-off?) — **inferred design
  intent, verify against pyRevit's routes source/behavior before relying on it**, since the whole
  "hangs during init" problem exists precisely because handler code runs through that queue.
- Never log the secret itself, even at DEBUG level, even in a traceback. Given `traceback.format_exc()`
  is currently returned to clients on some routes per `CONCERNS.md` (not yet fixed as of this
  milestone's "Out of Scope" list — traceback sanitization is explicitly deferred to later), a
  secret-comparison exception (e.g. a `TypeError` from comparing `None` to `str` if the header is
  missing) must not be allowed to bubble into a traceback string that includes the secret in a
  local variable — keep the compare in a narrow function with no other locals holding the secret
  in scope near the exception site, or explicitly redact before any traceback formatting occurs
  on that code path.

**Warning signs:** A wrong-secret request taking the full ~30s timeout to fail rather than
failing in milliseconds. Any traceback in logs or client responses containing anything that looks
like the configured secret value.

**Phase to address:** Secret-auth phase. The `/status/`-stays-open decision and the
fail-fast-before-queueing decision are both acceptance criteria, not implementation details —
write the test ("wrong secret fails in <1s, doesn't wait on Revit init") before writing the
check.

---

### Pitfall 10: Timing-unsafe secret comparison, combined with the text/plain contract, is easy to get subtly wrong in IronPython 3

**What goes wrong:**
A `==` string comparison for the secret is timing-*technically* unsafe (early-exit on first
mismatched byte), though the practical risk here is low given the stated threat model (no
attacker capable of timing a local loopback HTTP comparison). The more concrete, likely-to-bite
mistake is different: comparing a secret sent as part of a `text/plain` POST body (parsed via
`parse_request_data`) against a Python 3 `str` on the IronPython 3 side, where `parse_request_data`
already has to handle bytes/str/dict inputs (per its documented contract) — if the secret is
pulled from a dict key without going through the same normalization path as the rest of the
payload, encoding mismatches (a `bytes` secret from one path vs. a `str` reference value) will
produce comparison failures that look identical to "wrong secret" but are actually a data-type
bug — very hard to distinguish from an actually-wrong secret without instrumenting the compare
itself, especially given this project's own documented history of exactly this class of bug
(`textutils.py`'s `unicode`-alias misdetection making `bytes`/`str` collapse silently under
IronPython 3, discovered because ALL POST routes returned 500 not because of a logic error but a
type-identity assumption that was true on IronPython 2.7 and false on IronPython 3).

**Why it happens:**
The secret most likely travels as just another key in the same JSON-ish payload that
`parse_request_data` already normalizes, so it's tempting to read it directly (`data.get("secret")`)
without checking whether it's already gone through the same str-normalization the rest of the
payload gets — and if it hasn't (e.g., if it's read from a header instead, which pyRevit's routes
server may hand over as a different type than the body), a `bytes is str` mismatch in the compare
is exactly the kind of thing that silently "works" on a dev machine's engine version and fails
elsewhere, mirroring the actual `unicode`-alias incident.

**How to avoid:**
- Route the secret through the exact same parse/normalize path as the rest of the request body
  (i.e., make it a field inside the `text/plain` JSON payload — NOT an HTTP header — so it goes
  through the already-proven `parse_request_data` contract, and inherits the existing "handles
  bytes, str, or dict" test coverage) rather than inventing a second, untested code path for
  header extraction. This also sidesteps any question of "does pyRevit's routes server handle
  headers consistently under IronPython 3" (an area this project has NOT yet had to characterize,
  unlike the body-parsing path, which was characterized the hard way).
- If a constant-time comparison is desired anyway (cheap insurance even if not strictly required
  by the threat model), use `hmac.compare_digest` — but verify it's available and behaves
  correctly under IronPython 3 (**not verified in this research; a quick standalone check should
  be run** — `hmac.compare_digest` has historically required `bytes`-like inputs in CPython and
  IronPython's stdlib compatibility is not guaranteed 1:1). If unavailable or unreliable, a
  same-length manual XOR-accumulate compare is an acceptable, well-understood fallback — do not
  silently fall back to `==` without at least noting the tradeoff, given the stated threat model
  makes this a low-priority hardening rather than a blocking requirement.
- Add exactly one unit test on the CPython side (where `textutils.py`-style pure logic is
  testable) asserting the secret-compare helper treats `b"x"` and `"x"` as equivalent inputs (or
  explicitly rejects one), so this doesn't silently regress the way the `unicode`-alias bug did
  while the CPython suite stayed green.

**Warning signs:** A secret that "sometimes" fails to authenticate depending on which code path
supplied it (header vs. body) — inconsistent auth failures are the signature of a type-identity
bug here, not a logic bug, per this project's own precedent.

**Phase to address:** Secret-auth phase. Decide "secret lives in the body, not a header" as an
explicit design choice up front — it's a one-line decision now and a hard-to-diagnose bug later.

---

### Pitfall 11: The audit log records the route's claimed outcome, not `commit_and_report`'s actual one — reproducing the silent-success problem one layer up, in the very feature meant to catch it

**What goes wrong:**
This is the single highest-value pitfall in the whole set, because it is explicitly what this
milestone's Context section is warning about (`PROJECT.md`: "Локальный структурный журнал аудита
всех мутаций с честным результатом"). If the audit-logging code is added as a wrapper around
"the tool was called with these arguments" (the easy, obvious integration point — e.g. a decorator
on the MCP tool function, or a log line in `_revit_call` before/after the HTTP round-trip) rather
than around the **actual per-element outcome** reported by `commit_and_report` and by each batch
route's per-element try/except, the log will faithfully record "delete_elements called with 50
ids" and "status: success" even on a route where 12 of those 50 elements were skipped via the
documented `continue`-and-still-report-success pattern (`building.py`, `clash.py`, `analysis.py`),
or even on a route where `commit_and_report` itself reports `rolled_back` but the *logging*
wrapper only saw "the HTTP call returned 409" and logged that generically as "mutation attempted"
without recording it as a failure. An audit log with this shape is actively worse than no audit
log, because it creates false confidence that a record exists proving what happened, when what it
actually proves is what was *requested* — precisely the gap the question calls out.

**Why it happens:**
The two natural integration points for audit logging — the CPython tool wrapper (`tools/*_tools.py`,
sees the request and the final string/dict response) and `_revit_call` (sees HTTP status and body) —
are BOTH on the wrong side of the real information for batch partial-failure. Neither has visibility
into "50 requested, 12 skipped," because that number currently only exists as an integer inside a
response body the audit layer would have to parse and interpret correctly, which requires the
audit layer to duplicate `format_response`'s already-fragile classification logic (or worse, invent
a third, differently-fragile classifier) unless the routes themselves are changed to emit an
explicit, structured `{"requested": N, "succeeded": M, "skipped": [...ids...]}` shape that both
`format_response` and the audit logger can consume identically.

**How to avoid:**
- **Fix the outcome-reporting contract before building the audit log on top of it**, not after.
  Every mutating route (not just `code_execution`/`parameters`/`editing`, which already have
  `commit_and_report`, but `delete_elements` and `export_ifc`, explicitly named in `PROJECT.md`'s
  Context as NOT yet migrated, plus every batch route in `building.py`/`clash.py`/`analysis.py`
  with the documented `continue`-and-still-success pattern) needs to report a structured, honest
  outcome — `{requested, succeeded, skipped: [...], transaction_status, failures}` at minimum —
  BEFORE the audit logger is written to trust that shape. `PROJECT.md`'s own Active list already
  names "`commit_and_report` покрывает все мутирующие маршруты" as a separate line item from the
  audit log — treat that as a hard dependency ordering, not a nice-to-have: audit logging that
  reads from routes that haven't been migrated yet will encode the old lie structurally.
- Log from the **single point that already has the true outcome** — i.e., wherever
  `commit_and_report`'s return dict (or its batch-route equivalent) is available, on the Revit
  (IronPython) side, not the CPython tool-wrapper side — so the log entry is written from the same
  data the client's response is built from, not a re-derivation of it. This also sidesteps a
  structural risk: if the audit log is written from the CPython side by re-parsing the HTTP
  response, it inherits every future risk of `format_response`'s heuristics changing without the
  audit logger being updated in lockstep (two independent consumers of one fragile classifier is
  worse than one).
- For batch routes specifically, the log line must include the skipped/failed subset (ids and
  reasons), not just a success/fail boolean and a count — a count alone ("48/50 succeeded") is
  still useless for reconstructing what actually happened without the ids, and reconstructing "what
  happened to element X" is presumably the actual point of an audit log in a BIM-engineering
  context (a colleague asking "who deleted this wall and why did it say success").
  Migrating the batch routes to emit that shape is real, non-trivial work — flag it as in scope for
  this phase, not an audit-logging detail to bolt on afterward.
- Add a test in the same spirit as the two existing `rolled_back` regression tests: one pinning
  "a route reporting partial batch failure produces an audit entry that includes the skipped ids,"
  and one alarm test documenting "if a route ever reports bare `status: success` without a
  `skipped` key on a batch operation, audit logging silently can't tell partial failure from full
  success" — so a future regression in a route's outcome-reporting is caught by the audit-logging
  test suite too, not just by whatever test the route itself has.

**Warning signs:** Any audit log entry for a batch route showing only `"status": "success"` with
no per-element detail. An audit log line written before the HTTP response from Revit has actually
been received (a sign it's logging intent, not outcome, timing-wise).

**Phase to address:** Audit-logging phase — but its true prerequisite is completing
`commit_and_report` coverage and fixing the batch-route silent-skip pattern first (both already
separately listed in `PROJECT.md`'s Active requirements). Sequence the roadmap so audit logging
is the LAST of the four target-feature groups to land, not built in parallel with the outcome-
reporting fixes it depends on.

---

### Pitfall 12: Audit log writes from IronPython under concurrent Revit instances (or the async CPython side) corrupt or interleave on Windows, and the file grows without bound

**What goes wrong:**
Two already-documented environment facts compound directly here: (a) two Revit.exe processes can
both bind port 48884 and both be alive simultaneously (explicitly called out as still relevant —
one of this milestone's own Active requirements is *detecting* that case, implying it is not yet
prevented), and (b) if each Revit-side process writes to a shared audit log file (e.g. a fixed
path like `%APPDATA%\pyRevit\...\audit.log` or similar), naive `open(path, "a")` appends from two
OS processes on Windows are not guaranteed atomic across process boundaries for anything beyond
very small writes, risking interleaved/corrupted lines under real concurrent load — exactly the
scenario this milestone is otherwise trying to make detectable, now potentially corrupting the
evidence trail itself. Separately, an audit log with no rotation/cap will grow unbounded on a
long-lived Revit session (BIM engineers routinely leave Revit open for a full workday or longer),
and if writes happen synchronously on a network-mapped path (plausible, given this org's evident
comfort with UNC/RSN paths per other recent commits) rather than local disk, each log write adds
real, blocking network I/O latency to the IronPython side of every mutation — worse, on the CPython
side, if audit logging happens in `main.py` and is not made properly async (a blocking file write
inside an `async def` tool handler), it stalls the event loop for every concurrent tool call, which
given `stateless_http` and the existing 20-connection pool, could measurably slow the whole server
under load.

**Why it happens:**
Structured audit logging is naturally implemented as "just write a line to a file" on whichever
side is easiest to instrument, and file-append safety under concurrent writers plus async-safety
under an event loop are both details that don't surface in single-request manual testing — they
only appear under the specific two-instance or high-concurrency conditions this project's own
history shows are not hypothetical here.

**How to avoid:**
- Prefer writing the audit log from the CPython side (`main.py`, one process, already async) over
  the IronPython side, specifically because the two-Revit-instances problem means the IronPython
  side cannot be assumed to be a single writer — but this requires the true-outcome data
  (Pitfall 11) to actually reach the CPython side intact, which is the dependency ordering
  argument above. If IronPython-side logging is unavoidable for some data, use a per-process log
  file path (e.g. including the Revit PID or the bound port) rather than one shared path, sidestepping
  the concurrent-writer problem entirely rather than trying to solve file-locking on Windows across
  two independent process runtimes (CPython's `logging` module's file locking guarantees do not
  extend to a completely separate IronPython engine writing the same path).
- On the CPython side, write logs via a thread-pool executor or an async-safe queue rather than a
  blocking `open().write()` inside `async def` tool code — matching the existing care this codebase
  already puts into not blocking (the whole reason for the pooled `httpx.AsyncClient`).
- Add rotation (size- or date-based) from day one — do not ship "append forever" even for a v0.1;
  this is cheap to add up front and expensive to retrofit onto files already in the tens-of-MB
  range on machines nobody is watching closely.
- Keep the audit log local-disk by default (matching the project's constraint that mutation-secret
  material is baked into the payload rather than fetched over network at runtime — the same
  "don't add a network dependency to a hot path" reasoning applies to audit writes).

**Warning signs:** Garbled/interleaved lines in the audit log on a machine later found to have had
two Revit processes running. Noticeably slower mutation response times correlating with audit log
file size growth over a long Revit session.

**Phase to address:** Audit-logging phase — writer-location and rotation are both design
decisions to fix before the first log line is written, not tuning to revisit later.

---

### Pitfall 13: The audit log (or its error paths) leaks the secret, full model file paths, or PII-bearing element data — the opposite failure mode from Pitfall 11, equally damaging

**What goes wrong:**
Given this codebase's existing, documented habit of returning raw `traceback.format_exc()` to
clients (explicitly not yet fixed — traceback sanitization is explicitly listed as Out of Scope
for THIS milestone in `PROJECT.md`), any audit-logging code that logs "the full request payload"
or "the full exception" for context will, by construction, also log the shared secret (if it's a
field in that same request body — see Pitfall 10's recommendation to put it there) and any
absolute file paths, UNC/RSN model paths, or Cyrillic personal/project names embedded in element
data (this project explicitly cares about preserving Cyrillic text through the pipeline, meaning
real Russian names/addresses plausibly appear in real model data it might log). A log file meant
to build trust ("everything mutated is recorded honestly") becomes a new liability if it becomes
the easiest place on the machine to find the shared secret in plaintext, especially since the
project's own threat model change (adding the secret) implies the secret's value now needs
protecting to the degree the model itself needs protecting.

**Why it happens:**
The obvious, defensively-minded implementation of "audit log the full request for completeness"
directly conflicts with "don't log secrets," and unless secret-redaction is applied at exactly
the log-writing boundary (not upstream, since upstream code paths won't all know they're feeding
a logger), it's easy to miss one path — mirroring the traceback-leak pattern already known to
exist elsewhere in this codebase.

**How to avoid:**
- Apply redaction at the single audit-log-writing function, not at every call site — strip or
  mask a known field name (`secret`, `token`, whatever the payload key ends up being) unconditionally
  before serializing to the log line, treating it the same way `sanitize_string` is applied
  uniformly at the JSON-serialization boundary rather than trusted to be handled correctly by
  each caller.
- Log element ids and parameter *names* freely (useful for audit), but be deliberate about whether
  parameter *values* (which may contain the Cyrillic personal/project data this project already
  cares about preserving faithfully) belong in a log that might be shared more broadly than the
  model file itself (e.g., attached to a support ticket) — this is a judgment call for the team,
  but it should be an explicit line item, not an afterthought realized after the first log export
  is shared externally.
- Do not log full absolute file paths (model paths, RSN paths) if avoidable — log the filename/
  title only (the same `sanitize_string(doc.Title)` value `/status/` already exposes), consistent
  with treating file paths as sensitive the same way the existing traceback-disclosure concern in
  `CONCERNS.md` already flags them.

**Warning signs:** Grep the audit log implementation for anywhere it serializes an entire request
dict or exception object rather than an explicit allowlist of fields.

**Phase to address:** Audit-logging phase, as an explicit redaction step reviewed alongside the
"honest outcome" requirement (Pitfall 11) — these two properties (honest, but not leaky) are in
tension and both need to be verified together, not sequentially.

---

### Pitfall 14: Document/instance identity is added to responses but built from `revit.doc`, which is proven stale/null during exactly the multi-document operations this feature exists to make safe

**What goes wrong:**
This project has ALREADY hit and fixed one instance of this exact problem
(`2026-09-14-null-document-transaction.md`: `revit.doc` can be `None` or stale during
`OpenAndActivateDocument`, fixed by re-fetching `revit.doc` before constructing a `Transaction`
and returning 503 if still empty). Adding document/instance identity to every response is, by
construction, adding MORE code that reads `revit.doc` (or equivalent) — and if that new
identity-stamping code is added as a generic wrapper applied uniformly to all routes (a natural,
DRY implementation choice) without re-deriving `doc` the same defensive way the existing fix
does, the identity stamp itself can be wrong or `None` at precisely the moment (mid document-switch)
when correct identity matters most — silently reintroducing the same class of bug this project
already paid to fix once, in new code that has an even stronger reason to get it right (it exists
specifically to answer "which document did this happen to").

**Why it happens:**
The existing fix lives in `code_execution.py` (transaction construction), a narrow, specific
location. A new cross-cutting "stamp every response with document identity" feature naturally
wants a single shared helper called from every route — and if that helper is written fresh rather
than reusing/extending the exact `revit.doc`-refetch-and-503-if-empty pattern already proven
necessary, it's an easy, structurally-invited regression: two independently-written pieces of code
doing "get the current document" with different levels of defensiveness.

**How to avoid:**
- Build the identity-stamping helper as a direct extension of the existing, proven pattern (re-fetch
  `revit.doc` defensively; if still empty/stale, the route already returns 503 rather than proceeding
  — the identity helper should do the same check, not a lighter-weight one), ideally by literally
  factoring the existing null-check out of `code_execution.py` into a shared helper in
  `revit_mcp/utils.py` and having BOTH the transaction-construction path and the new identity-
  stamping path call it — one function, two call sites, rather than two independently-maintained
  copies of "handle a possibly-null doc."
- Decide what identity actually means before implementing: at minimum PID
  (`System.Diagnostics.Process.GetCurrentProcess().Id`, stable per Revit process) and something
  that survives a `Project1`-vs-`Project1` title collision (the milestone's own Context explicitly
  flags this: two instances with identical untitled-document titles are indistinguishable today).
  A `doc.Title` string alone is insufficient by the project's own admission — PID plus the bound
  port (once port becomes configurable per another Active item) plus title is the minimum tuple
  that actually disambiguates the two documented open problems (title collision + two-listeners-
  one-port) simultaneously.
- Re-verify this specific claim against a live two-Revit/switch-documents test as part of this
  phase's acceptance criteria, precisely because the underlying bug class has already fooled this
  codebase once via static reasoning alone (the `param-write-rolls-back` investigation's own
  "blind_spots" section explicitly says the doc-identity hypothesis was "weakened but not fully
  eliminated by static reading alone" and recommends exactly the live check this new identity
  feature should finally make possible) — building this feature is also the mechanism to finally
  close that lingering open question, so treat "run the param-write-rolls-back live repro with
  identity now visible in the response" as a concrete acceptance test for this phase, not a
  separate follow-up.

**Warning signs:** An identity field in a response that is `null`/`Untitled`/empty immediately
after a document-switch or open operation. Any new code reading `revit.doc` directly rather than
through the shared, defensive helper.

**Phase to address:** Multi-document/instance-identity phase. This phase should explicitly close
the loop on the still-open `param-write-rolls-back` parallel hypothesis as part of its own
verification, since it is the first point in the project where that hypothesis becomes testable
at all.

---

### Pitfall 15: Addressing "a specific instance by port" is incoherent while the two-listeners-one-port bug remains unfixed, and any new "select document/instance" API silently inherits that incoherence

**What goes wrong:**
The milestone's Active requirements list both "detect two listeners, fail explicitly" and
"specific Revit instance addressable — port configurable" as separate line items, which is the
right split, but if multi-document/multi-instance addressing work (e.g. "operate on document X in
instance Y") is designed or implemented BEFORE the two-listener detection lands, any "instance Y"
concept in the new API is built on a foundation (the port number) that is currently proven, in
this exact codebase's own documentation, to not reliably identify a single process at all. A
"select instance by port 48884" parameter added to routes now would need to be entirely reworked
once ports become configurable and once two-listener detection exists — worse, it could give
users false confidence that they successfully "addressed" a specific Revit process when in fact
the OS silently routed their request to the other one, which is precisely today's silent-failure
mode, just wrapped in a new API that looks like it solved it.

**Why it happens:**
"Multiple models in one session: enumerate, address in call, switch active" and "specific instance
addressable, port configurable" read as adjacent, similarly-scoped work and are natural to build
together or in either order — but one is a prerequisite for the other to mean anything, and
nothing in a quick read of the requirements list signals that ordering explicitly.

**How to avoid:**
- Sequence this explicitly: two-listener detection and port configurability land BEFORE (or in
  the same phase as, with detection landing first within that phase) any "address instance by
  port/identity" API surface. Land the PID-based identity (Pitfall 14) first since it's meaningful
  regardless of port configuration, then layer port-based addressing on top once ports are
  actually distinguishing.
- Within a single Revit process, "multiple models in one session" (multiple open `Document`s in
  ONE `Application.Documents` collection) is a genuinely different problem from "multiple Revit
  processes" (the port-collision problem) — verify the roadmap phase doesn't conflate them. Per
  Autodesk's own Revit API documentation (confirmed via web search above): `Application.Documents`
  enumerates all open documents within one Revit session, while `UIApplication.ActiveUIDocument`
  is the one currently active in the UI; **switching the active document is documented as
  disallowed during API event handling** — meaning a route handler (which runs inside an
  external-event callback, per this project's own architecture) cannot simply call something like
  "activate document X, do work, activate back" mid-request the way a UI-driven macro might. This
  is confirmed against Autodesk's public API docs, not this project's code, and should be spiked
  against a live two-open-documents Revit session before committing to an implementation approach
  for "operate on a non-active document."
- For "operate on a non-active document" specifically: many mutating Revit API operations
  (`Transaction`, element creation/deletion, parameter `Set`) are `Document`-scoped, not
  `UIDocument`-scoped, and Autodesk's introductory API documentation describes the
  `Application`/`Document` pair as covering "an individual instance of a Revit project" independent
  of UI activation, suggesting many mutations CAN target a non-active `Document` obtained from
  `Application.Documents` without activating it first — but operations requiring a `UIDocument`
  (anything view/selection/UI-interaction-shaped, e.g. `RequestViewChange`, `Selection`,
  `ShowElements`) require the document to be active. **This split (Document-scoped mutations
  possibly OK on a non-active doc; UIDocument-scoped operations require activation) is inferred
  from Autodesk's introductory API documentation structure, not verified against this project's
  own routes or a live multi-document test — treat it as a hypothesis to validate per-route, not
  a settled fact**, since pyRevit's `revit.doc` injection convention (used by literally every
  existing route in this codebase) has only ever been exercised against the single active document,
  and pyRevit itself may not expose a clean "give me Document N from Application.Documents" pattern
  without additional plumbing this project hasn't built yet.

**Warning signs:** Any new API parameter named `port` or `instance_id` merged before the
two-listener-detection requirement is done. A route that accepts a `document_id`/`document_title`
selector parameter but internally still reads `revit.doc` (the active document) instead of looking
up the requested one from `Application.Documents` — meaning the parameter is accepted but silently
ignored, an even worse outcome than not offering it (looks like it works, doesn't).

**Phase to address:** Multi-document/instance phase — explicitly sequence two-listener-detection
and port-configurability ahead of (or as the first sub-step within) any "address a specific
instance" API work, and validate the Document-vs-UIDocument operation split live before writing
routes that assume non-active-document mutation works uniformly across all existing route types.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Secret gate implemented ad hoc per-route instead of one shared helper | Faster to ship one route at a time | Repeats the exact "`commit_and_report` not rolled out everywhere" partial-coverage gap this milestone is already trying to close for rollback visibility | Never — write the shared helper first, even if only 2 routes use it initially |
| Client-side lock described as "prevents concurrent Revit transactions" | Sounds like a stronger guarantee, easier to write in the roadmap | Overclaims a guarantee the architecture cannot provide (see Pitfall 5); erodes trust in this milestone's own stated goal ("доверенный мост") when the gap is discovered later | Never in written documentation; acceptable only as informal shorthand in conversation if everyone present knows the real scope |
| Audit logging built against current route outputs before `commit_and_report`/batch-outcome migration is complete | Audit logging "ships" sooner, looks like progress | Bakes in the exact silent-success shape this feature exists to catch (Pitfall 11); worse than not having audit logging yet, because it looks trustworthy | Never — sequence audit logging after outcome-reporting fixes, per PROJECT.md's own Active list ordering |
| Self-restore wired directly into `startup.py`'s top-level execution | Simplest place to put "check on load" | Fires on every pyRevit Reload, not just process restart (Pitfall 2), on the exact codebase already documented to crash on Reload-after-edit | Never on the dev machine (junction); needs the new-process-vs-reload distinction resolved first even for pilot machines |
| Hashing the extension directory via `os.walk` for integrity verification | Simple, no dependency on `git` being available at runtime | Picks up `__pycache__`/`.pyc`/editor artifacts as false corruption (Pitfall 3), triggering restore loops | Never — derive the manifest from the tracked file list (`git ls-files` at build time), not a runtime directory walk |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| pyRevit Routes server + shared-secret header | Reading the secret from an HTTP header, assuming pyRevit's routes server hands headers over consistently under IronPython 3 (uncharacterized territory, unlike the body-parsing path) | Put the secret inside the already-proven `text/plain` JSON body, parsed via the existing `parse_request_data()` contract — reuse tested code, don't open a new uncharacterized path |
| pyRevit extension reload lifecycle + integrity self-restore | Treating any `startup.py` top-level execution as "a fresh start" worth restoring on | Distinguish genuine Revit process start from pyRevit Reload before wiring in any file-writing restore logic; verify against pyRevit's actual load-event semantics, don't assume |
| Revit external-event queue + auth check ordering | Letting the secret check run inside the same queued handler path as the Revit work, so a bad secret waits behind Revit init/other queued work before failing | Evaluate the secret as early as possible in the handler, ideally before any Revit-side work is scheduled, so auth failures are fast regardless of Revit's init state |
| `Application.Documents` (multi-doc) + pyRevit's `revit.doc` injection convention | Assuming `revit.doc` (always the active document) is sufficient once "address a non-active document" is a requirement | `revit.doc` only ever gives the active document; addressing a specific non-active one requires walking `Application.Documents` directly, which no existing route does today — new plumbing, not a parameter tweak |
| Windows file writes for audit log + two-Revit-instances-one-port scenario | One shared audit log path written by both IronPython engines when two Revit processes are alive | Use a per-process log path (PID or port in filename) for the IronPython side, or centralize writing on the single CPython process instead |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Secret gate added to mutating routes but `/execute_code/` left reachable without it (or gated separately, inconsistently) | `/execute_code/` is already documented as unauthenticated arbitrary code execution with full `doc`/`DB`/`clr`/`System` access — the single highest-value target for the new secret gate, and easy to forget precisely because it doesn't look like a typical "mutation" route | Explicitly include `/execute_code/` in whatever route-classification mechanism decides "needs secret" — do not derive the list only from routes that touch `DB.Transaction`, since `/execute_code/` can do so dynamically without appearing in a static scan |
| Secret compared or logged via a code path that can also throw and get its locals dumped into a returned traceback | Given traceback sanitization is explicitly out of scope for this milestone, a secret-compare exception could leak the secret value in a client-visible 500 response | Keep the secret-compare function minimal (no other secret-bearing locals in scope) and add a narrow try/except around just that comparison that never re-raises with locals attached |
| Bind-to-127.0.0.1 enforcement checked only at MCP-client (`main.py`) level, not at the pyRevit Routes server itself | This milestone's own Context notes a pilot station was found listening on `0.0.0.0:48884` already — a client-side default doesn't change what the server actually binds to | Verify/force the actual Routes server bind (pyRevit configuration), not just `main.py`'s `REVIT_HOST` default — this is explicitly called out as a gap in `CONCERNS.md` already |

## "Looks Done But Isn't" Checklist

- [ ] **Secret auth on mutations:** Often missing coverage of `/execute_code/` and any batch/export
  route not yet migrated to `commit_and_report` — verify by checking the secret-check call site
  exists in every route file matching the tool manifest's mutating tools, not just the three
  routes already touched by the rollback fix.
- [ ] **Integrity self-restore:** Often missing a working distinction between "Revit process
  start" and "pyRevit Reload" — verify by clicking Reload in pyRevit's extension manager on a
  test machine and confirming no restore/file-write fires, then fully restarting Revit and
  confirming it does.
- [ ] **Integrity verification:** Often missing exclusion of `__pycache__`/`.pyc`/editor artifacts
  from the hashed file set — verify by diffing the manifest generation against `git ls-files`
  output on the actual extension directory.
- [ ] **Serialized mutations:** Often missing a test proving `/status/` stays responsive while the
  mutation lock is held — verify with a concurrent-request test, not just a "mutations don't
  interleave" test.
- [ ] **Serialized mutations:** Often missing lock release under exception/cancellation — verify
  with a test that forces a timeout/exception inside the locked region and re-acquires afterward.
- [ ] **Audit log honesty:** Often missing per-element skip/failure detail on batch routes — verify
  by triggering a batch operation with at least one intentionally-invalid element id and checking
  the audit log records it as a partial failure, not a bare success line.
- [ ] **Audit log honesty:** Often missing correlation with `commit_and_report`'s `rolled_back`
  outcome — verify by triggering an actual rollback (an edit that fails Revit's validation) and
  confirming the audit log records failure, not "mutation completed."
- [ ] **Document/instance identity:** Often missing correct behavior during an active document
  switch — verify by opening two documents in one Revit session, switching the active one via the
  UI mid-session, and confirming responses reflect the switch rather than stale cached identity.
- [ ] **Document/instance identity:** Often missing disambiguation of two `Project1`-titled
  documents — verify with the two-Revit-instances-open pilot setup already available per
  `PROJECT.md`, checking that the identity fields (not just title) actually differ.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|-----------------|
| Secret gate silently returns 200 on failure (Pitfall 1) | LOW | Same fix pattern as `rolled_back`: change status code to 401/403, add the same pair of regression tests, no data-model change needed |
| Self-restore fires on Reload and overwrites in-progress dev edits (Pitfall 2) | HIGH on the dev machine (uncommitted work lost); recoverable via git reflog/IDE local history if caught quickly | Immediately disable the restore trigger; check `git status`/editor undo history for the overwritten file; add the process-start-vs-reload guard before re-enabling |
| Integrity verifier false-positives on `__pycache__`/line-endings, triggering restore loop (Pitfall 3) | MEDIUM | Regenerate the manifest from `git ls-files`; add the exclusion; confirm hashes stabilize across two consecutive checks with no restore in between |
| Lock deadlock from an unreleased lock on exception (Pitfall 7) | LOW to MEDIUM (requires Revit/process restart to clear an in-memory lock, but no data corruption) | Restart `main.py` (the MCP server process) to clear the module-global lock state; fix to `async with` before resuming |
| Audit log recorded false success on a batch partial failure (Pitfall 11) | HIGH — the log itself is now unreliable retroactively for the period before the fix | Cannot be recovered for already-written entries; flag the affected date range as unreliable in any audit review, fix the outcome-reporting contract, and re-verify going forward with the regression tests described above |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|---------------|
| 1. Secret failure returns 200 / breaks the `_revit_call` string-vs-dict contract | Secret-auth phase | Regression test pair mirroring `test_rolled_back_409_reaches_the_model_as_a_visible_error` / the alarm test, for 401 |
| 9. Secret check hangs during Revit init / `/status/` becomes unreachable | Secret-auth phase | Timed test: wrong-secret request fails in <1s; `/status/` reachable unauthenticated |
| 10. Timing/type-unsafe secret comparison via header vs. body | Secret-auth phase | Unit test: compare helper treats bytes/str secret inputs consistently; secret travels in body, not header |
| 2. Self-restore fires on Reload, not just process start | Integrity/self-restore phase | Manual test: Reload does not restore; full Revit restart does |
| 3. False-positive integrity mismatches from caches/line-endings | Integrity/self-restore phase | Manifest generated from `git ls-files`; two consecutive checks with no intervening edit produce zero mismatches |
| 4. Network-share unreachable treated as corrupt / blocks startup | Integrity/self-restore phase | Simulated share-unreachable test: Revit still starts, `/status/` reports `unverifiable`, no restore attempted |
| 5. Client-side lock overclaimed as true mutual exclusion | Serialization phase | Design doc / roadmap language explicitly scoped to "this process's own calls"; live two-overlapping-request experiment run and documented |
| 6. Lock held across full mutation timeout starves `/status/` | Serialization phase | Concurrent test: `/status/` responds while a simulated slow mutation holds the lock |
| 7. Lock not released on exception/cancellation | Serialization phase | Test: forced exception inside locked region, lock re-acquirable immediately after |
| 8. Lock design assumes session state under `stateless_http=True` | Serialization phase | Code review: lock is a module global next to `_http_client`, not attached to any session/context object |
| 11. Audit log records intent, not outcome, for batch/rollback cases | Audit-logging phase (sequenced AFTER outcome-reporting fixes) | Test: intentional rollback and intentional partial-batch-failure both produce audit entries reflecting the true outcome |
| 12. Audit log corruption/growth under concurrency and long sessions | Audit-logging phase | Per-process log path or single-writer (CPython-side) design; rotation configured from first commit |
| 13. Audit log leaks secret/paths/PII | Audit-logging phase | Redaction applied at the single log-writing function; reviewed against a known-sensitive-field checklist |
| 14. Document identity built on the same `revit.doc` staleness bug already fixed once | Multi-document/instance-identity phase | Live test: identity remains correct across `OpenAndActivateDocument` and mid-session active-document switch; re-run `param-write-rolls-back` repro with identity now visible |
| 15. Instance addressing by port is incoherent before two-listener detection exists | Multi-document/instance-identity phase | Sequencing check: two-listener detection and port configurability merged before/alongside any "address by instance" API; Document-vs-UIDocument operation split validated live per route type |

## Sources

- This project's own `.planning/PROJECT.md` (Context section, dated 2026-09-21) — code-audit-derived
  facts about `/execute_code/` exposure, 0.0.0.0 bind on a pilot station, `/status/` field gaps,
  unmigrated `commit_and_report` coverage, hardcoded port. **Confidence: HIGH** (primary source,
  same repo).
- This project's own `CLAUDE.md` "Known sharp edges" and "Non-negotiable invariants" — the
  Reload-crashes-Revit, two-listeners-one-port, modal-dialog-hangs-forever, init-hang,
  broken-JSON-parse, and `unicode`-alias incidents. **Confidence: HIGH** (primary source, same repo,
  each with a dated incident).
- `.planning/debug/param-write-rolls-back.md` — the silent-rollback root cause, the `commit_and_report`
  fix, and its own explicitly-flagged unresolved parallel hypothesis about document identity.
  **Confidence: HIGH** (primary source; note status is `awaiting_human_verify` — the fix is
  static-analysis-verified only, not yet live-confirmed, per the document itself).
- `.planning/codebase/CONCERNS.md` (dated 2026-09-04) — traceback disclosure, batch silent-skip
  pattern, `suppress_warnings` swallowing its own setup failure. **Confidence: MEDIUM** — dated
  before this milestone's 2026-09-21 code audit in `PROJECT.md`; cross-checked against `PROJECT.md`'s
  Context section, which independently reconfirms the batch-skip and traceback issues as still live,
  so treated as still accurate for those specific claims.
- `.rvt-mcp_Obsidian/knowledge/debugging/2026-09-14-null-document-transaction.md` — the specific,
  dated, already-fixed incident of `revit.doc` being null/stale during `OpenAndActivateDocument`.
  **Confidence: HIGH** (primary source, same repo).
- `revit_mcp/utils.py`, `revit_mcp/status.py`, `revit_mcp/editing.py`, `main.py` — read directly to
  confirm current `commit_and_report`/`_FailureSwallower` implementation, `revit.doc` injection
  pattern, `stateless_http=True` configuration, and the `_revit_call` string/dict response contract.
  **Confidence: HIGH** (primary source, current code, read in full for this research).
- Autodesk Revit API Developer's Guide — "Application and Document" and "Document and File
  Management" pages (help.autodesk.com/cloudhelp/…/Revit-API/…) — confirms `Application.Documents`
  enumerates all open documents in a session, `UIApplication.ActiveUIDocument` is the active one,
  a document can have only one open transaction at a time, and switching active documents is
  disallowed during API event handling. **Confidence: MEDIUM** — verified via web search against
  Autodesk's own documentation pages, but not exercised live against this project's actual pyRevit
  routes/external-event setup; the Document-vs-UIDocument operation-scoping split (Pitfall 15) is
  explicitly flagged as inferred from this documentation's structure and needs a live per-route
  validation before being treated as settled for this codebase specifically.

---
*Pitfalls research for: revit-mcp-server v0.1 "Доверенный мост" milestone (identity, secret auth,
integrity self-restore, mutation serialization, audit logging)*
*Researched: 2026-09-21*
