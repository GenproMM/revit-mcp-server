---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '03'
subsystem: api
tags: [bridge, discovery, process-incarnation, per-target-lock, netstat, httpx, mcp-tool]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-01 selector/parse_target/listener_snapshot/identity route and the ru-RU netstat fix; 02-02 production identity observed live (model-less Revit 2024, PID/port/token, stale selector refused)
provides:
  - "bridge.discover_targets / resolve_default_target and the revit_get.discover_targets facade (usable incarnations, unusable collisions naming every PID, named inventory-unavailable status)"
  - "tools/target_tools.py discover_revit_targets (registered, in tool_manifest.txt)"
  - "Target-keyed bridge: one pooled client + one lock per (host, port, PID, token) incarnation for GET, POST and image; only GET /status/ unlocked"
  - "Identity handshake (netstat owner + GET /status/) with the lock held right before every requested send; refusals say not sent"
  - "tests/unit/test_target_locks.py and 22 discovery tests in test_target_resolution.py"
affects: [02-04, 02-08, 02-16, 02-18, 02-19]

actuals:
  tokens: 19700   # chars/4 over `git diff d7337eb..HEAD` (78916 chars) at the last task commit; excludes the uncommitted test_parallel_installation.py edit and this SUMMARY
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count d7337eb..HEAD before this SUMMARY commit (#3968)
plan_head_before: d7337eb5cfbe32b259846e8346268929f369f100

tech-stack:
  added: []
  patterns:
    - "State machine per incarnation: _TargetState(client, lock, users, verified, evicted); a stale selector leaves no state, a superseded incarnation is evicted and closed by its last in-flight user"
    - "Tools reach discovery through an attribute on the injected revit_get (no tool-side bridge import, four-argument registrar unchanged)"
    - "Unit conftest guard: bridge never reaches a real Revit or the host socket table from tests/unit"

key-files:
  created:
    - tools/target_tools.py
    - tests/unit/test_target_locks.py
  modified:
    - bridge.py
    - tests/unit/test_target_resolution.py
    - tests/unit/tool_manifest.txt
    - tests/unit/conftest.py                       # outside files_modified, see Deviations
    - tests/unit/test_bridge_serialization.py      # outside files_modified, fixture adaptation only
    - tests/unit/test_local_bridge_transport.py    # outside files_modified, one slicing marker
    - tests/unit/test_serialization_scope_docs.py  # outside files_modified, one slicing marker

key-decisions:
  - "A call with no selector now dispatches only to the single usable incarnation found by discovery; zero, several, or ANY listener collision in the probe window refuses with the candidates/PIDs and sends nothing (the collision-beside-one-usable case is stricter than the plan text, chosen because a hidden second Revit means 'the only one' is not established)."
  - "Probe window is DEFAULT_REVIT_PORT .. +127 plus REVIT_PORT, read from one full netstat snapshot; only singleton listeners are handshaken; same-port pairs are never probed. This is a bounded scan policy, not a prediction of which port a process holds."
  - "REVIT_HOST/REVIT_PORT no longer route a call: REVIT_PORT only adds its port to the probe window; discovery probes loopback addresses. revit_get.revit_target is kept as the configured launch-slot string."
  - "Identity is re-proven with the lock held (full netstat + GET /status/, handshake capped at 10 s) immediately before each requested send, so a process that restarted while the call queued is caught; the cost is one netstat per call."
  - "No-selector GET /status/ keeps the legacy result shapes (payload for 200, 'Error: <code> - <body>' otherwise) so the unmigrated process tools still read HTTP 503 as no-document; selected status keeps the 02-01 shape with _verified_process."

patterns-established:
  - "Refusals before a send always say 'request not sent' (or NOT sent); a verified identity is attached only to a response actually received"
  - "State key is the whole incarnation; document selectors and ports never create a second lock"

requirements-completed: []  # Deliberately empty (02-02 precedent). AMBIG-01/02/03 are satisfied offline at the bridge for every transport but the production same-port refusal is the 02-18 live observation the plan itself reserves; IDENT-01 was closed by 02-01/02-02 evidence; IDENT-04 needs the document tools (02-04+) and rendering (02-16).

coverage:
  - id: D1
    description: "Discovery lists usable incarnations (identity, port, selector, document open/no-document 503) and unusable listeners; same-port pair reported as collision naming both PIDs and never probed; unavailable/malformed inventory is a named status, never an empty list"
    requirement: "AMBIG-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_target_resolution.py#test_same_port_pair_is_unusable_names_both_pids_and_is_never_probed"
        status: pass
      - kind: unit
        ref: "tests/unit/test_target_resolution.py#test_inventory_failure_is_a_named_refusal_not_an_empty_list"
        status: pass
    human_judgment: false
  - id: D2
    description: "No-selector dispatch only for exactly one usable incarnation: zero refuses with a named failure, several list every candidate selector, a collision refuses naming PIDs; nothing requested is sent"
    requirement: "AMBIG-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_target_locks.py#test_no_selector_with_two_usable_refuses_every_transport"
        status: pass
      - kind: unit
        ref: "tests/unit/test_target_resolution.py#test_collision_beside_one_usable_process_still_refuses_the_default"
        status: pass
    human_judgment: false
  - id: D3
    description: "One lock and one client per incarnation across GET, POST and image: same process waits (any document), different processes overlap, GET /status/ bypasses, queue timeout is not sent, POST failure after send stays UNKNOWN, restarted PID/port reuse is refused, eviction never closes an in-flight call"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_target_locks.py (26 tests) and tests/unit/test_bridge_serialization.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "discover_revit_targets registered through the actual registration callable, in the manifest, through revit_get.discover_targets"
    requirement: "IDENT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_target_resolution.py#test_discovery_tool_through_the_actual_registration_callable"
        status: pass
    human_judgment: false
  - id: D5
    description: "Production same-port collision refusal and production multi-process discovery on the live bench"
    requirement: "AMBIG-01"
    verification:
      - kind: manual_procedural
        ref: "not run - 02-18 live observation, needs separate user authorization"
        status: unknown
    human_judgment: true
    rationale: "Offline fakes prove the bridge decision logic; a real duplicate listener on one port was measured only with auxiliary RoutesServer instances in 02-20 and needs its own authorized bench run."

duration: "~25 min"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 03: Process discovery, unambiguous default and per-incarnation serialization Summary

**One shared `revit` entry now discovers Revit incarnations from the full netstat inventory, refuses an ambiguous default (several processes or any same-port collision, naming every PID), and serializes every GET, POST and image call per validated (host, port, PID, token) incarnation with the identity re-proven under the lock before each send.**

## Performance

- **Started:** 2026-10-22T06:40:36Z
- **Completed:** 2026-10-22T07:00Z (approx.)
- **Tasks:** 2 of 2 (both `tdd="true"`: RED then GREEN each)
- **Files:** 2 created, 7 modified (plus one uncommitted edit, see Deviations)

## Accomplishments

- `bridge.discover_targets()` / `resolve_default_target()`: bounded loopback probe window over one full `netstat -ano -p tcp` snapshot (`listener_snapshot`, the only listener source). Singleton listeners are handshaken on `GET /status/` only; a port with two LISTENING PIDs is an unusable `listener-collision` naming both and is never probed; a listener that times out, answers non-Revit, or claims another PID is unusable with a reason; an unavailable or malformed inventory is `inventory-unavailable` with empty lists, never "no Revit". A no-document Revit (HTTP 503) is usable with `document_open: false`.
- `revit_get.discover_targets` facade attached to the injected callable; verified on the actual registration callable (`tools.register_tools`). `tools/target_tools.py` registers `discover_revit_targets` (docstring as API contract, `ctx` last, returns `str` via `format_response`); a missing facade is a visible `Error:`, not "none".
- Target-keyed transport: `_TargetState` (client, lock, users, verified, evicted) per incarnation; `_get_client(target)` / `_get_lock(target)`; `revit_get`, `revit_post`, `revit_image` all accept `target=`. Documents of one process share its lock; different processes overlap; only `GET /status/` bypasses (`UNLOCKED_GET` unchanged, `/model_info/` still locked).
- Before every requested send, with the lock held: full netstat owner check plus a `GET /status/` identity handshake on the pooled client; a stale token (even on a reused PID and port), a duplicate listener or a missing listener refuses with "request not sent" and the requested route is never sent. Failure wording is preserved: queue timeout is "NOT sent", a POST failing after send is "outcome UNKNOWN", a connect failure names the addressed process.
- Eviction (T-02-06): a verified incarnation retires older state on the same host/port at once; its client is closed immediately if idle, otherwise by its last in-flight call. A stale selector leaves no state behind.

## Task Commits

1. **Task 1 RED:** `aae8103` (test) - 17 failing discovery/default/facade/tool tests
2. **Task 1 GREEN:** `6bc3306` (feat) - discovery, default resolution, facade, tool, manifest
3. **Task 2 RED:** `56ee35b` (test) - 25 failing lock/handshake/default-dispatch tests plus the unit conftest guard
4. **Task 2 GREEN:** `62abbfd` (feat) - target-keyed client/lock state, dispatch rewrite, Phase-1 fixtures adapted

**Ordering note:** Task 1's acceptance text includes "no-selector dispatch occurs only for exactly one usable incarnation". The default *decision* (`resolve_default_target`) landed in Task 1; routing the actual requested calls through it needs the target-keyed state, so that wiring landed in Task 2's commit.

## Verification (real numbers)

- Task 1 verify `uv run pytest tests/unit/test_target_resolution.py tests/unit/test_registration.py -q`: **76 passed**.
- Task 2 verify `uv run pytest tests/unit/test_target_locks.py tests/unit/test_target_resolution.py -q`: **91 passed**.
- Plan verification `uv run pytest tests/unit -q`: **1023 passed, 3 skipped** (baseline 975 passed, 3 skipped; +48 new tests).
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.406** (<2.0).
- All HTTP in these tests is `httpx.MockTransport` and netstat is faked; no live claim follows. Live items stay not-run: production same-port collision refusal (02-18), production multi-process discovery.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Phase-1 serialization fixtures encoded the removed single-target globals**
- **Found during:** Task 2 GREEN
- **Issue:** `tests/unit/test_bridge_serialization.py` injected `bridge._http_client` / read `bridge._get_lock()`; with per-incarnation state and discovery-based default routing 25 tests failed, plus two source-slicing marker tests (`def _get_client()` is now `def _get_client(target)`). The plan defers this "fixture adaptation" to the later contract-sweep plan (02-16) but the suite must stay green on a sequential tree.
- **Fix:** fixture-only adaptation: one fixed incarnation, `resolve_default_target` and `_verify_target` stubbed, client injected into the incarnation's state, `_get_lock(TARGET)`; the `/status/` mock answers with identity. No assertion was removed or weakened. The two marker strings became `def _get_client(`.
- **Files modified:** tests/unit/test_bridge_serialization.py, tests/unit/test_local_bridge_transport.py, tests/unit/test_serialization_scope_docs.py
- **Verification:** 66 passed in those three files; full suite green.
- **Commit:** `62abbfd`. This pre-empts most of 02-16 Task 2 (its remaining value: image/target and stale-eviction assertions already exist in test_target_locks.py).

**2. [Rule 2/3 - Critical/Blocking] Unit-suite guard against reaching a live Revit**
- **Found during:** Task 2 RED. The first RED run of `test_target_locks.py` executed against the *unmodified* bridge, whose no-selector path talks to the configured `localhost:48884`. A Revit is open on this machine, so that run sent a handful of read-only GETs (`/status/`, `/list_levels/`, one image-style `GET /get_view/x`) and POSTs with an empty body to nonexistent routes (`/p1/`) to the user's live Revit. I believe nothing changed (nonexistent routes answer 404, the reads are read-only) but I did not verify the live model afterwards; flagged for the user.
- **Fix:** `tests/unit/conftest.py` autouse fixture: default `listener_snapshot` is an unavailable inventory (only a caller passing its own `run=` reaches the real function), `_selected_client` is a refusing client, and `bridge._states` is fresh per test. Any test that wants a process must fake both netstat and the client factory.
- **Files modified:** tests/unit/conftest.py (outside files_modified)
- **Commit:** `56ee35b`, `62abbfd`

**3. [Rule 3 - Blocking] Two semantics tests in the plan's own test file rewritten**
- `test_explicit_target_never_falls_back_to_model_route` and `test_selected_non_status_never_sends` asserted the 02-01 refusal "explicit targets support only status". They now assert that a selected model route is refused before any HTTP when the incarnation cannot be proven (inventory unavailable). Both stay in `tests/unit/test_target_resolution.py` (in files_modified). Commit `62abbfd`.

**4. [Rule 3 - Blocking] Untracked other-session test adapted on disk, NOT committed**
- `tests/unit/test_parallel_installation.py::test_bridge_never_falls_back_to_foreign_api` (untracked, another session's file) patched `bridge._http_client`/`_lock`, so it broke. I adapted it the same way (fixed incarnation, status answers with identity) so the working tree is green, but did not commit it because the file belongs to uncommitted work from an earlier session. The user must commit it with that work.

**Total deviations:** 4 (all Rule 2/3). **Impact:** no production behavior beyond the plan; test infrastructure touched outside files_modified for the reasons above.

## Issues Encountered / Surprises

- **Behavior change to know about:** with no selector, a call now needs a working netstat plus a handshake and refuses when several Revits run (or any port collides). Before this plan it went to the configured `REVIT_HOST:REVIT_PORT` regardless. Tools do not yet accept `target` (02-08..02-11), so with two Revits running every existing tool is refused with the candidate list until those plans land. This is the intended D-02 behavior, but it is a visible interim regression for a two-Revit workstation.
- `get_revit_status` (no selector) still appends `MCP target: host:port` (the configured launch slot); when discovery picks a different port that line can mislead. `status_tools.py` is outside this plan; 02-16 owns status rendering.
- `tools/process_tools._bridge_state` reads `revit_get("/status/")` with no selector: zero Revit or several Revits both come back as a non-HTTP `Error:` and read as "down" (and `start_revit` could launch another). The no-selector 503 shape is preserved so no-document still reads as `no_document`. 02-19 owns the real fix; until then do not run `start_revit` on a machine where discovery may be ambiguous.
- Docs now stale (outside files_modified): CLAUDE.md "Known sharp edges" first bullet (Routes target is REVIT_HOST/REVIT_PORT) and "Current surface: 54 MCP tools" (now 55 with `discover_revit_targets`); README/deploy text on REVIT_PORT routing.
- Each non-status call now runs one `netstat` (and one extra local GET) while holding the lock; measured cost not benchmarked on the live bench.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: local-probe-surface | bridge.py | Discovery sends `GET /genpro_revit_mcp/status/` to every singleton loopback listener in DEFAULT_REVIT_PORT..+127 and REVIT_PORT (read-only, loopback only, no body, `trust_env=False`, no redirects). Information disclosure is limited to what that route already reveals; not authentication and not a socket reservation (finite snapshot-to-send TOCTOU window documented in the bridge docstring). |

## Next Phase Readiness

- 02-04 (documents) and 02-05..02-19 may build on `target=` on all three injected callables and on `revit_get.discover_targets`.
- Still not run and not claimed: production same-port collision refusal and production multi-process discovery (02-18, needs authorization), G2-production, G3, G4, G6.
- `requirements-completed` left empty on purpose (see frontmatter).

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist: `aae8103`, `6bc3306`, `56ee35b`, `62abbfd` (`git log --oneline d7337eb..HEAD`); `git rev-list --count d7337eb..HEAD` was 4; no deleted tracked files in any of them.
- Files exist: tools/target_tools.py, tests/unit/test_target_locks.py, and the modified bridge.py / test files above.
- `uv run pytest tests/unit -q`: 1023 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.406`.

---
*Phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin*
*Completed: 2026-10-22*
