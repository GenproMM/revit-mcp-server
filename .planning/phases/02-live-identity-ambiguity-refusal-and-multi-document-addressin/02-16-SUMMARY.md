---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '16'
subsystem: api
status: complete
tags: [provenance, format-response, bridge, response-attribution, d-06, d-15, per-target-lock, phase-1-regression, httpx, mcp-tool]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-03 per-incarnation bridge (identity handshake under the lock, per-target client and lock); 02-04..02-15 route replies that carry process_identity (or identity_error), the document descriptor the call ran on, observed_active_document, documents_changed (edit_family) and document_scope (execute_code); the tools forward target
provides:
  - "bridge.py received-response metadata contract: a reply from a proven incarnation is returned as ProvenanceDict / ProvenanceText carrying PROVENANCE_ATTR (revit_provenance) with kind, verified process, HTTP status and whether the reply's own stamp agrees; never a key in the body"
  - "A reply whose own process_identity names another process than the one verified before the send is discarded and replaced by an Error text (POST: outcome UNKNOWN); it is attributed to neither process"
  - "not-sent / no-reply / unknown / unverified-reply results are tagged too, carry at most the REQUESTED target and credit no process and no document; a POST whose 200 body is not JSON is now outcome UNKNOWN"
  - "tools/utils.py format_response: the ONE renderer. Unchanged projection moved into _project_response, then a visible attribution appended after it (document the route reports, document_scope, Verified Revit process line, or an Attribution: line for uncertain results)"
  - "get_revit_model_info(target, ctx) is target-aware; get_revit_status no longer presents the configured launch slot as the route; get_revit_view error strings go through the renderer"
  - "tests/unit/test_identity_rendering.py (57 tests) and test_bridge_serialization.py (every async Phase-1 queue test now also runs against the REAL handshake, plus 7 new per-incarnation tests)"
affects: [02-17, 02-18]

actuals:
  tokens: 19120   # chars/4 over `git diff 056a8c8..HEAD` (76479 chars) at the last task commit, tests included; excludes this SUMMARY
  tasks: 2
  commits: 3      # MEASURED: git rev-list --count 056a8c8d8eee12ca0e5ad5fe516086df01413060..HEAD before this SUMMARY commit (#3968)
plan_head_before: 056a8c8d8eee12ca0e5ad5fe516086df01413060

tech-stack:
  added: []
  patterns:
    - "Provenance as an attribute on dict/str subclasses (equality, JSON, startswith and process_tools string checks unchanged); the renderer trusts only that attribute, never a process_identity or _verified_process found inside a body"
    - "Pytest mode doubling for one module through pytest_generate_tests (only anyio-marked tests), so the pure and subprocess tests run once"

key-files:
  created:
    - tests/unit/test_identity_rendering.py
  modified:
    - bridge.py
    - tools/utils.py
    - tools/status_tools.py
    - tools/view_tools.py                          # outside files_modified, see Deviations
    - tests/unit/test_bridge_serialization.py

key-decisions:
  - "Metadata is an attribute, not a reserved key. A key could be forged by a route body (a reflected value) and would break exact-equality tests of the bridge result; an attribute on a dict/str subclass is invisible to equality, json.dumps and every existing string check. The legacy _verified_process key on selected /status/ replies is kept (02-03 tests read it) and excluded from the projection."
  - "A conflicting reply stamp (pid, actual_port or session_token of another process than the handshake proved) turns the reply into an Error and discards its body. A malformed or absent stamp is not a conflict: the reply is attributed on the pre-send proof alone and the metadata records corroborated=None."
  - "The renderer shows the document only from the route's own reply (document, documents_changed, observed_active_document); it never derives one from the request, the selector or the active document. A reply carrying document_scope (execute_code, D-15) renders the process and the notice only, even if a document key were present."
  - "Unsent and uncertain results append one Attribution line instead of staying silent. This changes the Phase-1 assertion format_response(queue_busy) == queue_busy: the bridge text is still verbatim and exactly one Attribution: none line follows (asserted)."
  - "An Image on HTTP 200 has no text channel and is left untagged; an image error string is attributed."
  - "get_revit_status keeps the line MCP target: host:port for a bare transport (legacy tests), but with bridge provenance it states when the configured slot is only a launch slot that did not route the call (gap a)."

patterns-established:
  - "Tools never import the transport: PROVENANCE_ATTR is duplicated in tools/utils.py and pinned equal by a test"

requirements-completed: []  # Deliberately empty (02-02..02-15 precedent). IDENT-04/D-06 rendering is now met offline for every tool that returns format_response(response), but the four document tools pre-render (named exception below), nothing was observed on a real Revit, and the phase's live gates (02-18: G2-production, G5-production collision, G6) are still required. IDENT-01..03 and AMBIG-01..03 are closed by earlier evidence or wait for 02-18.

coverage:
  - id: P1
    description: "A received reply is rendered with the verified answering process after the unchanged projection, even when message, result, data or output collapse it; the document shown is only the one the route reports"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_received_success_keeps_its_projection_and_appends_the_process"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_message_cannot_hide_the_document_the_route_reports"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_the_reported_document_is_never_invented_from_the_request"
        status: pass
    human_judgment: false
  - id: P2
    description: "Two unsaved Project1 documents in two Revit processes render differently (distinct process line), through the real bridge and a real tool registrar"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_two_unsaved_project1_in_two_processes_render_differently"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_two_processes_answer_with_their_own_attribution"
        status: pass
    human_judgment: false
  - id: P3
    description: "D-15: an /execute_code/ reply shows the verified process and the route's document_scope notice only; no document is rendered as changed even if the body carried one"
    requirement: "T-02-14 (D-15 label)"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_execute_code_reply_shows_process_and_scope_and_no_document"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_execute_code_scope_wins_even_if_a_document_key_appears"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_execute_revit_code_shows_process_and_scope_and_no_changed_document"
        status: pass
    human_judgment: false
  - id: P4
    description: "Unsent, no-reply and outcome-unknown results credit no process or document, name at most the requested target, and an unknown POST outcome is never labelled safely failed; a reply stamped by another process is discarded and attributed to nobody"
    requirement: "T-02-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_outcome_unknown_is_never_labelled_safe_and_credits_nobody"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_a_reply_stamp_of_another_process_is_never_attributed_to_the_selected_one"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_post_failure_after_send_is_outcome_unknown_and_credits_nobody"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_a_post_whose_200_reply_is_not_json_is_outcome_unknown"
        status: pass
    human_judgment: false
  - id: P5
    description: "The rolled_back 409 stays a verbatim Error string (never a dict, never a success) and gains the answering process; format_response's error predicate is untouched"
    requirement: "T-02-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_rolled_back_409_text_is_unchanged_and_attributed"
        status: pass
      - kind: unit
        ref: "tests/unit/test_format_response.py#test_rolled_back_409_reaches_the_model_as_a_visible_error"
        status: pass
    human_judgment: false
  - id: P6
    description: "Phase-1 queue, timeout, cancel, POST-unknown, GET, image and status-exemption semantics hold against the real identity handshake taken under the lock, not only against a stubbed proof; a queued call never handshakes outside the lock"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py (26 async tests x [fixed-proof, real-handshake])"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_the_proof_of_the_incarnation_is_taken_inside_the_lock_before_each_send"
        status: pass
    human_judgment: false
  - id: P7
    description: "Image with target and the non-status lock, independent second target, selected status bypassing only its own queue, eviction of a stale incarnation never closing or releasing another in-flight call, no module-level mcp import in bridge.py"
    requirement: "AMBIG-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_eviction_of_a_stale_incarnation_never_releases_another_in_flight_call"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_image_with_a_target_waits_behind_that_targets_lock_only"
        status: pass
      - kind: unit
        ref: "tests/unit/test_bridge_serialization.py#test_no_module_level_mcp_import_in_the_bridge"
        status: pass
    human_judgment: false
  - id: P8
    description: "Rendering on a real Revit (verified-process line and route-reported document on live replies, a real rolled-back 409, a real conflicting stamp) and the production same-port refusal"
    requirement: "IDENT-04"
    verification:
      - kind: manual_procedural
        ref: "not run - 02-18 live gates need separate user authorization"
        status: unknown
    human_judgment: true
    rationale: "Everything here is httpx.MockTransport and a faked netstat; no live Revit was contacted."

duration: "not timed (start time was not captured at plan start)"
completed: 2026-10-22
---

# Phase 2 Plan 16: Response provenance renderer and per-target Phase-1 regression Summary

**Every tool result now goes through one `format_response` that appends the process the bridge verified before the send and the document the route itself reports (never the requested one), credits nobody for unsent, no-reply and outcome-unknown results, and the Phase-1 queue semantics are re-proven against the real identity handshake.**

## What was built

**Task 1 - provenance end to end.**
- `bridge.py`: `_dispatch` now delegates the locked/unlocked exchange to `_verified_exchange`. `_verify_target` records the identity its handshake proved on the incarnation state; the call reads it right after the proof (no await in between, lock held) and tags the reply (`ProvenanceDict` / `ProvenanceText`, attribute `revit_provenance`). Kinds: `received`, `not-sent`, `unknown`, `no-reply`, `unverified-reply`. A reply whose `process_identity` disagrees with the proven one is replaced by an error (POST: outcome UNKNOWN, GET: no claim). A server-supplied `_verified_process` is stripped from received bodies. `/status/` (selected and default) is tagged `received` with the handshake identity and keeps its legacy shapes. An image on 200 stays untagged; an image error text is tagged.
- `tools/utils.py`: `format_response(response)` = unchanged projection (`_project_response`, error predicate untouched, reserved `_verified_process` excluded) + `_provenance_lines`. An untagged result renders exactly as before.
- `tools/status_tools.py`: status goes through the renderer; `get_revit_model_info` gained `target`; the `MCP target:` line says so when the configured slot did not route the call.
- `tools/view_tools.py` (outside files_modified): `get_revit_view` sends an error string through `format_response`.

**Task 2 - Phase-1 semantics under per-target state.** 02-03 had stubbed `_verify_target` in the whole file and loosened one exact equality. Now every async queue/timeout/cancel/failure-wording test runs twice (`fixed-proof`, `real-handshake`; the real mode answers `/status/` with identity and records handshakes apart from requested routes), the exact `/status/` payload equality is restored, and new tests prove the proof is taken inside the lock, image-with-target locking, second-target independence, selected-status bypass of only its own queue, eviction not touching another in-flight call, no module-level `mcp` import, and that every NEVER_UNLOCKED route is both scanned and locked.

## What the single renderer outputs

Received (message collapses the dict, document comes from the reply body):
```
Moved 1 element
Revit reported this document for the call: Project1 (document docA; path: (never saved); active)
Verified Revit process: PID 111; Revit 2024; port 48884; session 11111111-1111-4111-8111-111111111111
```
Received, execute_code (D-15; no document line even if a document key appears):
```
42
Document scope: Arbitrary code is a trusted exception: no document guard applies.
Verified Revit process: PID 111; Revit 2024; port 48884; session 11111111-...
```
Outcome unknown (POST sent, no complete reply; nothing credited):
```
Error: ReadTimeout - the request was sent to Revit but no complete response arrived within 30.0s; outcome UNKNOWN - ...
Attribution: unconfirmed. The request was sent toward Revit (requested target 127.0.0.1:48884, PID 111; not confirmed as the answering process) but no complete trustworthy reply was accepted, so its outcome is UNKNOWN and no Revit process or document is confirmed to have handled it.
```
Not sent (refusal, inventory failure, queue busy, connect failure):
```
Error: Listener inventory unavailable; request not sent. Rediscover targets.
Attribution: none. This request was not sent to Revit, so no Revit process or document is credited with it (requested target 127.0.0.1:48884, PID 111; not confirmed as the answering process).
```
(An invalid selector or an ambiguous default names `no target was established`.) The `Verified Revit process:` line keeps its exact 02-01 format because the live-procedure parser anchors on it.

## Commits

1. **Task 1 RED:** `07c3072` (test) - 57 provenance tests; 55 failed first (missing `bridge._tag` for the pure-renderer rows, behaviour for the bridge rows), 2 passed
2. **Task 1 GREEN:** `55699f5` (feat) - bridge.py, tools/utils.py, tools/status_tools.py, tools/view_tools.py, fixture tweaks, the one Phase-1 assertion update
3. **Task 2:** `336182f` (test) - test_bridge_serialization.py

## Verification (real numbers)

- Plan verify `uv run pytest tests/unit/test_identity_rendering.py tests/unit/test_status_target.py tests/unit/test_format_response.py -q`: **87 passed** (57 + 5 + 25 tests).
- Task 2 verify `uv run pytest tests/unit/test_bridge_serialization.py tests/unit/test_target_locks.py tests/unit/test_serialization_scope_docs.py -q`: **129 passed**.
- `uv run pytest tests/unit -q`: **2858 passed, 3 skipped** (baseline 2763 passed, 3 skipped; +57 identity-rendering, +38 bridge-serialization). No pre-existing failure.
- `uv run python scripts/conventions.py`: exit 0, no output. `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.359** (<2.0).
- **TDD honesty for Task 2:** its tests were not red first; they restate behaviour the 02-03 bridge already had. They were proven to bite with three temporary mutations of bridge.py (each restored byte-for-byte, `git diff` clean afterwards): evicting a state closed an in-flight client (2 failures), one shared lock for all incarnations (35 failures), an extra handshake taken outside the lock (1 failure, the proof-inside-the-lock test in real-handshake mode).
- Offline only. No `mcp__revit__*` tool was called, `execute_revit_code` was never run, the live bridge and every document were left alone (a Revit was open); tests/unit/conftest.py kept the bridge away from the real listener table and sockets. No accidental live contact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Critical] A POST whose 200 reply is not JSON was reported as a plain error**
- **Found during:** Task 1 (designing the unknown/not-sent classification)
- **Issue:** `response.json()` raising inside a locked POST fell through to `Error: Expecting value...`, which reads as a safe failure although the request was sent.
- **Fix:** locked POSTs catch `json.JSONDecodeError` and say outcome UNKNOWN (kind `unknown`); a read says only the error (kind `no-reply`).
- **Files modified:** bridge.py. **Commit:** `55699f5`. Tests: `test_a_post_whose_200_reply_is_not_json_is_outcome_unknown`, `test_a_read_whose_200_reply_is_not_json_credits_nobody`.

**2. [Rule 3 - Blocking] tools/view_tools.py is outside files_modified**
- `get_revit_view` returned a ReceivedText error string without the renderer ("deliberately bypasses the usual response formatting"). One line now routes error strings through `format_response`. The CRLF endings of the file are kept. **Commit:** `55699f5`.

**3. [Rule 3 - Blocking] One Phase-1 assertion changed rather than kept**
- `test_queue_bound_message_is_an_error_string` asserted `format_response(result) == result`. Unsent results now get one `Attribution: none.` line by design (the plan asks for attribution on unsent paths). The test now asserts the bridge text is verbatim, exactly one extra line follows, it starts `Attribution: none.` and no `Verified Revit process` appears. The property it guarded (a letter after `Error: `, text survives formatting) is kept. **Commit:** `55699f5`.

### Interface choices

1. **Attribute, not reserved key** for the metadata (see key-decisions); the plan wording says "reserved metadata keys". The projection still excludes the one reserved key that exists (`_verified_process`).
2. **A conflicting stamp is an error, not a warning line.** The plan only required that a wrong-process response is never attributed to the selected process; discarding the body also protects the four pre-rendering document tools, which read the body directly.
3. **Gap (a) resolved, not removed:** the `MCP target:` line stays last (pinned by tests and the live scripts) but is qualified when the verified process answered on another port or nothing was sent.
4. **Gap (b) resolved:** `get_revit_model_info` takes `target` (before `ctx`, manifest name unchanged) and its docstring says the route stamps no document, so the answer is attributed to a process only.
5. The Task 1 test file was tuned after RED for fixture mistakes only (an unawaited coroutine in the fake machine, an empty `ReadTimeout` message, one assertion word that collided with "discarded").

## Known exceptions for the 02-17 inventory

- `list_documents`, `activate_document`, `read_document_summary` and `read_document_levels` (tools/document_tools.py) render a new string and then call `format_response(text)`, so the bridge tag is lost on their success path. They name the answering process from the reply's own stamp (`Answering Revit process: ...`) and are separately tested in test_document_contracts.py / test_tool_forwarding_documents.py. Their error paths pass the tagged response straight to `format_response` and are attributed. The conflict check in the bridge covers their success path too (a reply stamped by another process never reaches them).
- `get_revit_view` on HTTP 200 returns an Image, which has no text channel.
- `tools/process_tools.py` and `tools/target_tools.py` build their own dicts/strings (no Revit reply): untagged, unchanged.
- Routes that stamp no process (for example /model_info/ and the reads not yet stamped) are attributed on the pre-send proof only (`corroborated: null`); this is the documented snapshot-to-send TOCTOU window, not authentication.

## Issues Encountered / Surprises

- Two attempts at bash heredocs with apostrophes in the body failed to parse (nothing was written); the edits were redone with the Edit tool. No file was left half-written.
- `git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on every commit (stale registered worktree, as in earlier plans); commits succeed.
- Because the tag is an attribute, `dict(response)` or any re-render drops it. `status_tools` therefore no longer copies the dict before formatting.
- CLAUDE.md "Known sharp edges" (REVIT_HOST/REVIT_PORT routing, 54 tools) is still stale after 02-03; not touched here (outside this plan and the pinned sentences must not move).

## Known Stubs

None.

## Threat Flags

None. No endpoint, auth path or schema was added. The new text exposes only what the route already returns plus the already-verified process PID, port, version and session token (same as the status line since 02-01); `process_identity`/`document` in a body are never trusted by the renderer on their own. T-02-02 (repudiation) and T-02-05 (queue exemption) are mitigated and tested; the only unlocked route is still GET /status/.

## Not run / not claimed

- **Live behaviour is not run.** Rendering on real Revit replies, a real rolled-back 409 through the new tag, and a real conflicting stamp are unobserved. G2-production and G5-production collision (02-18) are not run; G6 is not authorized.
- **No revit_mcp/ file changed**, so no Revit restart is needed for this plan. The MCP server process must be restarted by the client to load the new bridge and tools.
- **Requirements:** `requirements-completed` is empty on purpose (see frontmatter).
- STATE.md and ROADMAP.md were updated through the gsd-tools verbs and left uncommitted per the dispatch instruction (they hold other sessions' uncommitted work).

## Next Phase Readiness

- 02-17 can assert that every registrar calls `format_response` (named exceptions above) and can reuse the `tool()` / `Machine` helpers in tests/unit/test_identity_rendering.py.
- 02-18 live gates still need separate user authorization.

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist in `git log`: `07c3072`, `55699f5`, `336182f`; `git rev-list --count 056a8c8d8eee12ca0e5ad5fe516086df01413060..HEAD` was 3; no tracked file was deleted by any of them; `git status --short -- bridge.py tools tests revit_mcp` shows only the untracked other-session `tests/unit/test_parallel_installation.py`.
- Files exist: tests/unit/test_identity_rendering.py, bridge.py, tools/utils.py, tools/status_tools.py, tools/view_tools.py, tests/unit/test_bridge_serialization.py.
- `uv run pytest tests/unit -q`: 2858 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.359`.
