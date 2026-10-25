---
phase: 06-structured-audit-log-of-true-outcomes
plan: 04
subsystem: audit
tags: [audit, correlation, call_id, envelope, fastmcp, schema, server-instructions]

requires:
  - phase: 06-structured-audit-log-of-true-outcomes
    provides: call-state contextvar, install_audited_tools wrapper, _dispatch audit hook, Audit line (06-01); full entry schema (06-02, 06-03)
  - phase: 05-shared-secret-and-integrity
    provides: the reserved _mcp envelope and the Revit-side gate
provides:
  - audit.SERVER_INSTRUCTIONS (the full user_request rule, stated once) and the final short USER_REQUEST_DESCRIPTION
  - FastMCP(..., instructions=audit.SERVER_INSTRUCTIONS) in main.py
  - bridge.CALL_ID_KEY and with_envelope(data, secret, call_id=None); revit_post decides one CallState and hands it to _dispatch(call=)
  - proof over the whole 59-tool surface that the wrapper adds exactly one optional user_request property and changes nothing else
  - proof of call_id end to end: shared, ordered, distinct under concurrency, fresh outside a tool, in the POST envelope, accepted by the real gate, shown on the Audit line per D-07
affects: [06-05, 06-06, 06-07, phase-07]

plan_head_before: f7d7c9e6c9b3ef9095ac02ca2276cee7f7984358
actuals:
  tokens: 18000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "call_id rides in the existing _mcp envelope beside the secret; the Revit half reads only the secret and strips the whole envelope, so revit_mcp/ is untouched"
    - "One CallState decided once per POST (revit_post) and threaded to _dispatch so envelope and entry share an id; GET and image calls still decide in _dispatch"
    - "Schema invariant test: plain vs wrapped FastMCP over the real register_tools, property-by-property"

key-files:
  created:
    - tests/unit/test_audit_registration.py
    - tests/unit/test_audit_correlation.py
  modified:
    - audit.py
    - main.py
    - bridge.py
    - tests/unit/test_phase5_gate_e2e.py

key-decisions:
  - "call_id is added to the envelope only when a secret is loaded and the id is a non-empty str; with no secret no envelope exists at all (pinned behavior kept)"
  - "revit_post decides the CallState before building the body, so a POST's envelope id and its audit entry id are the same object by construction"
  - "Concurrency is proven with two incarnations (SEL_A, SEL_B) gated in the Machine: one incarnation serializes through its own lock, so two calls to one process could never both be in flight"

patterns-established:
  - "Synthetic multi-call tool (read, mutation, image) is the proof of AUDIT-04 shared ids while no real tool spans two bridge calls"

requirements-completed: [AUDIT-04, AUDIT-01]

coverage:
  - id: D1
    description: "Every one of the 59 published tools gains exactly one optional user_request property (anyOf string/null, default null, final description); all other properties and required lists are identical to the unwrapped server; tools.FAILED is empty and names equal the manifest"
    requirement: "AUDIT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_registration.py#test_wrapper_adds_exactly_one_optional_property_to_every_published_tool"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_registration.py#test_user_request_is_optional_nullable_text_with_the_final_description"
        status: pass
    human_judgment: false
  - id: D2
    description: "The production server's instructions equal audit.SERVER_INSTRUCTIONS, which states the confirmation rule and the unverified-as-reported caveat once"
    requirement: "AUDIT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_registration.py#test_the_production_server_publishes_the_wrapped_surface_and_the_instructions"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_registration.py#test_server_instructions_state_the_full_rule_once"
        status: pass
    human_judgment: false
  - id: D3
    description: "JSON-looking, numeric and Cyrillic user_request values are accepted and recorded as text; the bare word null is recorded as missing; installing the wrapper twice wraps once"
    requirement: "AUDIT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_registration.py#test_a_json_looking_user_request_is_accepted_and_recorded_as_text"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_registration.py#test_the_bare_word_null_is_recorded_as_a_missing_request"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_registration.py#test_installing_the_wrapper_twice_wraps_each_tool_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "One tool call with a read, a mutation and an image fetch writes three entries in issue order with one call_id equal to the Audit line id; concurrent calls get distinct ids with no cross entries; bridge calls outside a tool get a fresh id and tool null; a tool with no bridge call writes nothing"
    requirement: "AUDIT-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_one_tool_call_with_three_bridge_calls_writes_three_entries_with_one_call_id"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_entries_of_one_call_appear_in_the_order_the_tool_issued_its_calls"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_concurrent_tool_calls_get_distinct_call_ids_with_no_cross_entries"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_a_bridge_call_outside_any_tool_gets_a_fresh_call_id_each_time"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_a_post_with_no_data_writes_one_entry_with_empty_args"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_a_tool_call_that_makes_no_bridge_call_writes_no_entry"
        status: pass
    human_judgment: false
  - id: D5
    description: "With a secret loaded every POST body carries _mcp {secret, call_id} with the entry's id; with no secret no envelope is added; the real Revit gate accepts and strips an envelope carrying call_id, including the exact bytes the bridge sent"
    requirement: "AUDIT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_every_post_body_carries_the_secret_and_the_call_id_of_its_entry"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_without_a_secret_the_body_has_no_envelope_and_the_entry_still_has_a_call_id"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_the_real_gate_accepts_an_envelope_with_a_call_id_and_strips_it"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_the_gate_accepts_the_exact_bytes_the_bridge_sent"
        status: pass
    human_judgment: false
  - id: D6
    description: "The Audit line appears for a successful mutation and for 401, 423, document refusal, 500 and unknown outcomes, never for a successful read, an open POST read or a not-sent call"
    requirement: "AUDIT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_every_non_success_outcome_that_wrote_an_entry_has_an_audit_line"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_a_successful_read_and_an_open_post_read_have_no_audit_line"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_correlation.py#test_a_call_refused_before_sending_has_no_audit_line_and_no_entry"
        status: pass
    human_judgment: false
  - id: D7
    description: "The model actually follows the user_request wording (copies the user's message, resolves short confirmations to the last substantive request)"
    requirement: "AUDIT-04"
    verification: []
    human_judgment: true
    rationale: "Assistant behavior against the published wording cannot be asserted by a unit test; the value is recorded as reported and labelled unverified (D-12)"

duration: 6min
completed: 2026-10-25
status: complete
---

# Phase 6 Plan 04: Correlation and the published schema change Summary

**Every one of the 59 published tools now asks for an optional `user_request` with one short description (full rule once in the server instructions), and every Revit call of a tool call is tied together by one `call_id` that appears in the audit file, in the POST envelope Revit receives and on the reply's Audit line.**

## Performance

- **Duration:** about 6 min (2026-10-25T10:17:47Z to 10:23:33Z)
- **Tasks:** 2
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- `audit.USER_REQUEST_DESCRIPTION` finalized and `audit.SERVER_INSTRUCTIONS` added; `main.py` passes `instructions=audit.SERVER_INSTRUCTIONS` to `FastMCP` (CRLF kept, `import audit` moved above the construction, host/port/stateless/json settings unchanged).
- `tests/unit/test_audit_registration.py` (7 rows): two real FastMCP instances (plain and wrapped) over the real `register_tools`; for each tool the wrapped properties equal the plain ones plus exactly `user_request`, `required` lists equal, names equal the manifest, `tools.FAILED` empty; `import main` checks the instructions and that every listed tool has the property. Pre-parse rows: `'{"a":1}'` and `'[1,2]'` arrive as text, `'42'` and Cyrillic verbatim, the bare `null` as missing.
- `bridge.CALL_ID_KEY`, `with_envelope(..., call_id=None)` and `revit_post` deciding one `CallState` once and passing it to `_dispatch(call=...)`; `_dispatch` falls back to `current_call() or anonymous_call()` so GET and image calls are unchanged.
- `tests/unit/test_audit_correlation.py` (16 rows): the accepted assumption-delta invariant (synthetic tool with a read, a mutation and an image fetch writes three ordered entries with one id equal to the Audit line id), concurrency with two gated incarnations, anonymous calls, empty-args POST, no-bridge tool, envelope content with and without a secret, real `gate_or_response` on both a hand-built envelope and the exact bytes the bridge sent, and the full D-07 Audit-line matrix (success mutation, GET read, open POST read, 401, 423, document refusal, 500, unknown, not-sent).
- Unit suite 6057 passed, 3 skipped (baseline after 06-03 plus this plan's rows); cold start `INIT_LATENCY_S=0.789`.

## Task Commits

1. **Task 1: every published tool schema gains exactly one optional user_request; full rule once in server instructions** - `79d807f` (feat)
2. **Task 2: one call_id per tool call, end to end** - `83c7770` (feat)

**Plan metadata:** committed separately as `docs(06-04)` (SUMMARY, STATE, ROADMAP, REQUIREMENTS).

## Files Created/Modified

- `audit.py` - final `USER_REQUEST_DESCRIPTION`, new `SERVER_INSTRUCTIONS`
- `main.py` - `import audit` above the constructor, `instructions=audit.SERVER_INSTRUCTIONS` (CRLF kept)
- `bridge.py` - `CALL_ID_KEY`, `with_envelope(..., call_id=None)`, `revit_post` decides the call once, `_dispatch(..., call=None)`, docstrings and envelope comment block
- `tests/unit/test_audit_registration.py` - schema comparison, instructions, pre-parse rows (new)
- `tests/unit/test_audit_correlation.py` - correlation, envelope, gate acceptance, Audit line rules (new)
- `tests/unit/test_phase5_gate_e2e.py` - two wire-envelope assertions now expect `{secret, call_id}`

`scripts/conventions.py` was not touched (`git diff --stat` empty): `check_tools` reads tool source and never sees the injected parameter. `revit_mcp/` was not edited (D-06).

## Decisions Made

- `call_id` rides only beside a secret and only when it is a non-empty str; the pinned "no secret, no envelope" behavior holds, and a model-built body that already holds `_mcp` is still refused (T-06-19).
- Concurrency is proven with two incarnations because one incarnation serializes through its own lock (a second call to the same process cannot be in flight with the first).
- The D-07 rule needed no change: `bridge._audit` and `format_response` already satisfied every row; the new rows pin it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Existing wire-envelope assertions pinned `{"secret": ...}` exactly**
- **Found during:** Task 2 (running the plan's own second verify command)
- **Issue:** `test_phase5_gate_e2e.py::test_revit_post_sends_the_loaded_secret_and_the_handler_sees_the_tool_data` and `::test_a_none_body_is_sent_as_an_empty_object_with_the_envelope` asserted the envelope equals `{"secret": TEST_SECRET}`. Adding `call_id` to the envelope is the deliberate D-06 change, so those two equality checks had to follow. The plan only required `test_bridge_secret_client.py` to stay unchanged (it did).
- **Fix:** assert the envelope keys are `{secret, call_id}`, the secret is the test secret and the id is a uuid4. The real gate still accepted the body and the handler still saw the tool data unchanged (existing assertions in the same tests).
- **Files modified:** `tests/unit/test_phase5_gate_e2e.py`
- **Verification:** `uv run pytest tests/unit/test_bridge_secret_client.py tests/unit/test_phase5_gate_e2e.py tests/unit/test_secret_gate_e2e.py -q` -> 108 passed (with the new correlation file); full suite green.
- **Committed in:** `83c7770`

---

**Total deviations:** 1 auto-fixed (1 Rule 3)
**Impact on plan:** None on behavior; two assertions updated to the new wire shape, file added to Task 2's commit pathspec.

## Issues Encountered

- First Task 1 commit attempt failed because a pathspec commit cannot name an untracked file; the new test file was `git add`ed and the commit repeated. Nothing was committed by the failed attempt.
- `git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` (stale unrelated worktree entry, as in 06-01); the commits succeeded.
- Several RED rows already passed before the implementation (the description wording check for Task 1, the shared-id, Audit-line and ordering rows for Task 2) because 06-01 and 06-02 had already built that behavior. They stay as pins; the genuinely failing rows were the instructions, `call_id` in the envelope and `with_envelope`.

## Limitations

- ROADMAP criterion 3 (one call_id across several bridge calls of one tool call) is proven with a synthetic tool: no real tool of the 59 spans two bridge calls today (research Pitfall 17). The invariant is in place for when one does.
- The wording of `user_request` is an instruction to the model. The server cannot verify what the assistant copies, so the entry labels it `user_request_source: "assistant"` and the instructions say so (D-12).
- The `call_id` in the envelope is correlation data only; Revit does not log it in this release. Revit-side use is outside this phase (D-06, no `revit_mcp/` change).

## Known Stubs

None.

## Threat Flags

None. The only new wire content is `call_id` inside the already-reserved `_mcp` envelope, covered by T-06-18 (real-gate acceptance row) and T-06-19 (pre-seeding refused).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 06-05: `call_id` is on every entry, in the envelope and on the reply; the wrapper and instructions are final. Entries shared across one tool call are ordered by issue order, so the 06-05 never-breaks and retention rows can rely on it.

---
*Phase: 06-structured-audit-log-of-true-outcomes*
*Completed: 2026-10-25*

## Self-Check: PASSED

- Created files exist: `tests/unit/test_audit_registration.py`, `tests/unit/test_audit_correlation.py` (verified with `[ -f ]`).
- Commits found in `git log`: 79d807f, 83c7770; `git rev-list --count f7d7c9e..HEAD` = 2 before this docs commit.
- Acceptance criteria re-run: registration 7 passed; `main.mcp.instructions == audit.SERVER_INSTRUCTIONS` prints True; description check prints True; `test_conventions.py` green and `git diff --stat -- scripts/conventions.py` empty; correlation 16 passed; `with_envelope` one-liners print the specified dicts; `uv run pytest tests/unit` 6057 passed, 3 skipped, 0 failed.
