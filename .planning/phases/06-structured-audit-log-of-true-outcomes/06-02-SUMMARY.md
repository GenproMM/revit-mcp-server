---
phase: 06-structured-audit-log-of-true-outcomes
plan: 02
subsystem: audit
tags: [audit, jsonl, outcome-table, provenance, bridge, cancellation, documents]

requires:
  - phase: 06-structured-audit-log-of-true-outcomes
    provides: audit.py tracer (build_entry, record_call, call state), bridge._dispatch hook, tests/unit/audit_support.py Machine
  - phase: 04-truthful-outcomes
    provides: outcome block (five keys) and reply statuses success/partial/failed/rolled_back
  - phase: 02-process-identity
    provides: provenance kinds, document descriptors, document refusal codes
provides:
  - audit.build_entry with the full fixed-precedence outcome table (12 labels) and the outcome block copied whatever the HTTP status
  - document_of with the D-09 source priority and labelled lesser sources (request_argument, handshake_active_title)
  - schema 1 field tuples (SCHEMA_1_FIELDS, ALWAYS_PRESENT_FIELDS), caps and DOCUMENT_REFUSAL_CODES / ROUTES_WITHOUT_OUTCOME_BLOCK / AUDITED_STATUS_TOOLS
  - bridge: images tagged with provenance, audited /status/ branch (get_revit_status only), cancellation entry, handshake active-title hint
affects: [06-03, 06-04, 06-05, 06-06, 06-07, phase-07]

plan_head_before: 98481cebef359f63befbe1f1477197eb94ef6eee
actuals:
  tokens: 12000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Outcome label by fixed precedence: provenance kind, HTTP 401/423, document refusal code, reply's own status, other 4xx/5xx, read-200, else unrecognized"
    - "Only named reply fields are copied into an entry; message/error text, the 423 file list and read data never are"
    - "Pure builder pinned to Revit-side constants by tests (OPEN_POST_READ_ROUTES, document refusal codes, gate_or_response per POST route)"
    - "Synthesized provenance for a cancelled sent call, written before CancelledError is re-raised"

key-files:
  created:
    - tests/unit/test_audit_entry.py
    - tests/unit/test_audit_bridge_hook.py
  modified:
    - audit.py
    - bridge.py
    - tests/unit/audit_support.py
    - tests/unit/test_identity_rendering.py

key-decisions:
  - "reason is written only for rejected_* labels; reply_status only for unrecognized (null when the reply stated none)"
  - "document_role is used for a route-reported document (reply document or documents_changed) and addressed for every lesser source and for /execute_code/"
  - "A non-received kind (unknown, no-reply, unverified-reply) ignores the reply body entirely, so a discarded reply can never leak lists or documents into an entry"
  - "Cancelled sent GET writes no_reply, cancelled POST writes unknown, both with cancelled true; never-sent cancel writes nothing"

patterns-established:
  - "Test rows for every reply shape live in tests/unit/test_audit_entry.py (pure) and test_audit_bridge_hook.py (real bridge + Machine)"
  - "Machine fake: per-port titles for /status/ document_title and str bodies as raw non-JSON replies"

requirements-completed: [AUDIT-01, AUDIT-02, AUDIT-03]

coverage:
  - id: D1
    description: "Every reply shape maps to one honest label in the fixed precedence (200 success/partial, 409, 422, 401, 423, 412 document refusal, bare 404, 500 with committed outcome, unknown, no_reply, unverified_reply, unrecognized); not-sent builds no entry; a partial or success label is never recomputed from counts"
    requirement: "AUDIT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_outcome_row"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_outcome_integrity_file_list_is_never_copied"
        status: pass
    human_judgment: false
  - id: D2
    description: "Per-element lists and the reported document are copied in reply order and capped (500/100/50/20) with true totals; same-title documents stay distinct by token and path; sources are labelled"
    requirement: "AUDIT-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_list_succeeded_is_capped_with_the_true_total_and_keeps_order"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_document_same_title_is_told_apart_by_token_and_path"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_document_execute_code_never_gets_a_changed_document"
        status: pass
    human_judgment: false
  - id: D3
    description: "mutation flag: audit.OPEN_POST_READ_ROUTES equals trust.OPEN_POST_READ_ROUTES; for every POST route it equals whether the handler calls gate_or_response; the only gated route without an outcome-builder call is /activate_document/; DOCUMENT_REFUSAL_CODES equals the identity.py constants"
    requirement: "AUDIT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_mutation_equals_the_handler_gate_for_every_post_route"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_mutation_every_gated_route_reaches_an_outcome_builder_but_the_exempt_one"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_document_refusal_codes_equal_the_identity_constants"
        status: pass
    human_judgment: false
  - id: D4
    description: "Through the production bridge every sent call (GET, POST, image) writes exactly one entry; handshake, discovery probes and every not-sent refusal write none; GET /status/ is logged only inside get_revit_status"
    requirement: "AUDIT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_bridge_hook.py#test_outcome_row_through_the_bridge"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_bridge_hook.py#test_image_carries_provenance_and_writes_one_entry"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_bridge_hook.py#test_status_inside_the_status_tool_writes_one_entry"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_bridge_hook.py#test_default_discovery_probe_and_handshake_write_nothing_but_the_call_does"
        status: pass
    human_judgment: false
  - id: D5
    description: "A POST cancelled after it was sent writes one unknown entry with cancelled true before CancelledError propagates; a call cancelled while still queued writes nothing"
    requirement: "AUDIT-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_bridge_hook.py#test_cancel_after_send_writes_one_unknown_cancelled_entry"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_bridge_hook.py#test_cancel_while_waiting_for_the_lock_writes_nothing"
        status: pass
    human_judgment: false
  - id: D6
    description: "The writer never records an outcome the Revit reply did not state (no success for an absent, unrecognized, unknown or no-reply status; no label from format_response, intent or recomputed counts)"
    requirement: "AUDIT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_entry.py#test_outcome_row"
        status: pass
    human_judgment: true
    rationale: "Prohibition is verified by judgment per the plan (descriptor-less); the outcome rows exercise it but do not prove the absence of other derivations"

duration: 11min
completed: 2026-10-25
status: complete
---

# Phase 6 Plan 02: Full honest schema 1 and exact call set Summary

**The audit entry now says what Revit actually did for every reply shape (a rollback as a rollback, a partial as a partial, a 500 after Commit() as an error that still shows Committed), names the elements and the reported document, and exists for exactly the calls that left this process, including a POST the client cancelled after sending.**

## Performance

- **Duration:** about 11 min
- **Started:** 2026-10-25T09:52:36Z
- **Completed:** 2026-10-25T10:03Z
- **Tasks:** 2
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- `audit.build_entry` implements the fixed outcome precedence (`_outcome`): provenance kind, HTTP 401/423, document refusal code, the reply's own top-level status, other 4xx/5xx as `error`, a completed read as `success`, else `unrecognized` with the raw `reply_status`. A mutation 200 with no status is never `success`.
- `_outcome_fields` copies `transaction_status`, `requested`, `succeeded`, `failed` (`{item, reason}`), `revit_failures` from the outcome block whatever the HTTP code, capped at 500/100/50 with true totals; `outcome_block_missing` flags a mutating 200/409/422 reply without a block (except `/activate_document/`).
- `document_of` follows D-09: reply descriptor, `documents_changed` (project entry first), request `document` argument, handshake active title, none; every entry names `document_source` and `document_role`; `/execute_code/` is always `addressed` with its `document_scope`.
- Schema 1 documented in the module docstring; `SCHEMA_1_FIELDS` / `ALWAYS_PRESENT_FIELDS` pinned by tests; the open-read list, the document refusal codes and `gate_or_response` per POST route are pinned to the Revit-side source.
- Bridge: `revit_image` results carry provenance; the `/status/` branch records only inside `get_revit_status`; the handshake title is kept as a labelled hint; a cancel after send writes `unknown`/`no_reply` with `cancelled: true` and re-raises.
- Unit suite: 5975 passed, 3 skipped (baseline after 06-01: 5892 plus 56 builder rows and 27 bridge rows). `INIT_LATENCY_S=0.766`.

## Task Commits

1. **Task 1: Pure entry builder, outcome table, lists, documents** - `c74f6c9` (feat)
2. **Task 2: Bridge hook completion (images, /status/, cancellation, title hint)** - `78b83f4` (feat)

**Plan metadata:** committed separately as `docs(06-02)`.

## Files Created/Modified

- `audit.py` - outcome table, outcome block copy, document_of, constants, Schema 1 docstring, record_call forwards `active_title_hint` / `cancelled`
- `bridge.py` - `_tag`/`_received_reply` tag non-text results, `_TargetState.active_title`, progress keys `requested` / `active_title_hint`, `_audit` extended, cancellation catch in `_dispatch`, audited `/status/` branch
- `tests/unit/test_audit_entry.py` - 56 pure builder rows (new)
- `tests/unit/test_audit_bridge_hook.py` - 27 rows through the real bridge and the Machine (new)
- `tests/unit/audit_support.py` - Machine `titles` and raw-text replies
- `tests/unit/test_identity_rendering.py` - the image assertion now expects a provenance-tagged image

## Decisions Made

- `reason` is written only for `rejected_*` labels and `reply_status` only for `unrecognized` (null when the reply stated none): those keys are absent otherwise, not null, because they are not in `ALWAYS_PRESENT_FIELDS`.
- `document_role` is `used` for a route-reported document and `addressed` for every lesser source and for `/execute_code/`; whether a listed document changed is in `documents_changed[i].changed`.
- A non-received kind ignores the reply body entirely, so a discarded or absent reply can never contribute lists or a document.
- A cancelled sent GET records `no_reply`, a cancelled POST `unknown`, both with `cancelled: true`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Existing test pinned "an image carries no provenance"**
- **Found during:** Task 2 (full-suite run)
- **Issue:** `test_identity_rendering.py::test_image_success_cannot_carry_text_but_an_image_error_is_attributed` asserted `provenance(image) is None`, the exact behaviour Task 2 (research Pitfall 7) removes on purpose.
- **Fix:** assert the image carries a `received` / HTTP 200 provenance naming process A; the "cannot carry text" half of the test (no rendered line from an image) is unchanged.
- **Files modified:** `tests/unit/test_identity_rendering.py`
- **Verification:** `uv run pytest tests/unit -q` -> 5975 passed, 3 skipped
- **Committed in:** `78b83f4`

---

**Total deviations:** 1 auto-fixed (1 Rule 3)
**Impact on plan:** None on behaviour; one assertion updated to the new, planned contract.

## Issues Encountered

- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` (stale unrelated worktree entry, as in 06-01); the commits succeeded. Not touched.
- `_audit` was reshaped (explicit `provenance` override plus an `attach_to` reference) rather than patched, so an audit id is only ever attached to a real provenance dict of the result.

## Known Stubs

None. Fields written by 06-03 (`windows_user`, `args`, `args_truncated`, `code_length`, `code_sha256`, `user_request*`) are named in `SCHEMA_1_FIELDS` but not yet produced; that is the plan's stated hand-off, not a stub.

## Threat Flags

None. All new surface (reply-body fields entering the log, cancellation entry) is covered by T-06-08 to T-06-12 in the plan's threat model.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 06-03: entry shape is fixed; `ALWAYS_PRESENT_FIELDS` is where `windows_user`, `args` and the `user_request*` fields get added, and redaction before truncation applies to the `failed[].reason`, `revit_failures`, `document` and `reason` strings written here.
- Note: `reason` strings (`failed[].reason`, `revit_failures`) come from Revit text and are capped here at 500 code points but not yet secret-redacted before the cap; `serialize_entry`'s final-line replacement covers the whole-secret case and 06-03 owns redact-before-truncate.

---
*Phase: 06-structured-audit-log-of-true-outcomes*
*Completed: 2026-10-25*

## Self-Check: PASSED

- Created files exist: tests/unit/test_audit_entry.py, tests/unit/test_audit_bridge_hook.py (verified with `[ -f ]`).
- Commits found: c74f6c9, 78b83f4 (`git log`); measured `git rev-list --count` from plan_head_before = 2.
- Acceptance criteria re-run: entry `-k outcome` 31 passed, `-k mutation` 8, `-k document` 16; constants print `['/activate_document/'] 11 1` and `True`; bridge hook 27 passed, `-k outcome` 7, `-k cancel` 2; `'active_title' in __slots__` True; tracer 8 passed; full unit suite 5975 passed 3 skipped; `INIT_LATENCY_S=0.766`.
