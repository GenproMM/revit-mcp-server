---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '05'
subsystem: api
tags: [document-activation, g4-eligibility-gate, openandactivatedocument, activate_document, http-422, observed-state, ironpython3]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-04 document registry (resolve_document, retained-reference Equals, tombstones), documents.py route module, document_tools.py; 02-20 accepted G4 explicit-activation-api
provides:
  - "revit_mcp/documents.py POST /activate_document/ route, run_activation() (testable orchestration over an injected UIApplication and snapshot reader) and the pure activation_refusal_reason() G4 gate with ACTIVATION_REFUSALS"
  - "tools/document_tools.py activate_document(document, target=None, ctx=None) tool with the narrowed-scope docstring (manifest updated)"
  - "tests/unit/test_document_contracts.py: 55 new tests (45 in Task 1, 10 in Task 2) covering allow, every refusal class, token refusals, observed-state, failure paths, route contract, tool contract and an AST call scan"
affects: [02-06, 02-07, 02-08, 02-09, 02-10, 02-11, 02-18]

actuals:
  tokens: 13000   # chars/4 over `git diff fe94051..HEAD` (52043 chars) at the last task commit; excludes this SUMMARY
  tasks: 2
  commits: 5      # MEASURED: git rev-list --count fe940516f6f406a58f0ef1efc207de2a3768cfd7..HEAD before this SUMMARY commit (#3968)
plan_head_before: fe940516f6f406a58f0ef1efc207de2a3768cfd7

tech-stack:
  added: []
  patterns:
    - "Activation orchestration is a plain function (run_activation) over an injected UIApplication, snapshot reader, registry and file-exists probe; the route handler is a thin shell that adds process identity (CLAUDE.md: new domain logic where tests can reach it)"
    - "The eligibility gate fails closed: an unreadable PathName or flag refuses as eligibility-unreadable, a file-exists probe that raises means no-usable-file-path"
    - "Success is only ever an observed fact: the active document is re-read through the registry (Equals against the UI document) after the call; the input descriptor and the API return value are never used"

key-files:
  created: []
  modified:
    - revit_mcp/documents.py
    - tools/document_tools.py
    - tests/unit/test_document_contracts.py
    - tests/unit/tool_manifest.txt

key-decisions:
  - "Reply vocabulary: 200 activated / already-active; 400 document-selector-required (omitted selector never picks a default) and request-body-invalid, plus the 02-04 400/404/503 token refusals passed through; 422 with reason = unsaved | detached | no-usable-file-path | linked-unsupported | family-unmeasured | cloud-unmeasured | workshared-unmeasured | eligibility-unreadable; 409 document-not-activated (call returned, target not observed active); 500 activation-failed (API exception) and activation-unverified (re-read failed); 503 document-registry-unavailable."
  - "Every reply (route level) carries process_identity (or identity_error) and observed_active_document, a descriptor dict re-read from Revit (None when nothing listed is active) with observed_active_error when it could not be read. The key is deliberately not active_document, which in 02-04 replies is a token string."
  - "Handler takes only (request), like the zero-argument /documents/ handler, so a process whose injected doc is missing can still answer; the UIApplication comes from HOST_APP.uiapp, the same glue identity.py already reads. Whether pyRevit injects a request-only handler is unverified live."
  - "activate_document is locked by default in bridge.py (only GET /status/ is unlocked); it was not added to NEVER_UNLOCKED because bridge.py is outside this plan's files."

patterns-established:
  - "A refusal and a failure are different replies: refusals are decided before any API call (zero calls, 422), failures happen after exactly one call (409/500) and always report the observed active document"
  - "'unmeasured' in a reason code means refused, not tried"

requirements-completed: []  # Deliberately empty (02-02/02-03/02-04 precedent). MDOC-04 is narrowed to the saved-existing-path class and only offline-tested here; the production Routes handler has not been exercised (02-07). IDENT-03, MDOC-01 and MDOC-05 were not completed by this plan's offline work alone either.

coverage:
  - id: A1
    description: "A token for an open, saved, non-workshared project with an existing file path becomes active through exactly one OpenAndActivateDocument(path) call carrying the target's own PathName, never a same-titled decoy's; success only when the re-read active document Equals the target; already-active makes zero calls; repeating is idempotent"
    requirement: "MDOC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_saved_project_with_an_existing_path_is_activated_with_its_own_path_once"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_already_active_document_is_a_success_without_any_api_call"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_activation_is_idempotent"
        status: pass
    human_judgment: false
  - id: A2
    description: "Unsaved, detached, non-file path, linked, family, cloud and workshared documents (including a saved workshared model with an existing path) refuse in a fixed order with distinct 422 reasons and zero API calls; an unreadable property fails closed"
    requirement: "MDOC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_each_unsupported_class_has_its_own_named_reason"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_refusal_order_is_fixed_when_several_things_are_true"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_ineligible_documents_answer_422_with_zero_api_calls"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_an_unreadable_flag_fails_closed"
        status: pass
    human_judgment: false
  - id: A3
    description: "Closed, tombstoned, replaced-with-identical-title-and-path, stale, unknown, malformed, ambiguous and omitted selectors cannot activate any document"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_closed_token_never_activates_another_document"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_unknown_stale_and_malformed_tokens_refuse_with_zero_calls"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_ambiguous_lifetime_refuses_and_never_activates"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_omitted_document_refuses_and_never_picks_a_default"
        status: pass
    human_judgment: false
  - id: A4
    description: "An API exception, a call that returns without the target active, and an unreadable re-read are non-200, truthy-error replies naming the attempted and observed active document, never retried, never described as activated; the handler never raises and keeps process identity on every reply"
    requirement: "MDOC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_api_exception_is_a_named_500_that_names_both_documents_and_is_never_retried"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_an_unreadable_re_read_after_the_call_is_unverified_not_activated"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_a_call_that_does_not_make_the_target_active_is_not_reported_as_activated"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_route_never_raises_and_always_names_the_process"
        status: pass
    human_judgment: false
  - id: A5
    description: "revit_mcp/documents.py has exactly one activation call site (one positional path read from the target's own PathName) and no save, save-as, document-file-open, transaction, ExternalEvent, thread or Idling machinery, judged on AST call/identifier nodes"
    requirement: "MDOC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_documents_py_has_exactly_one_activation_call_site_and_no_save_open_or_event_machinery"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_the_activation_call_takes_one_positional_path_read_from_the_target_own_pathname"
        status: pass
    human_judgment: false
  - id: A6
    description: "activate_document is a registered, manifest-listed tool with ctx last, a required document, an Args block naming document/target/ctx, a docstring stating the supported class, every refusal reason and that reads/mutations never activate; it refuses a missing document without POSTing and renders the re-read active document and the answering process"
    requirement: "MDOC-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_activate_document_signature_and_docstring_are_the_api_contract"
        status: pass
      - kind: unit
        ref: "tests/unit/test_registration.py#test_tool_names_match_the_manifest"
        status: pass
    human_judgment: false
  - id: A7
    description: "Production behavior of /activate_document/ on live Revit: the saved existing-path allow case through pyRevit's own ExternalEvent dispatch (equivalence to the 02-20 diagnostic callback), the refusals with the UI unchanged, absence of dialogs, a request-only handler signature under pyRevit injection, System.IO.File.Exists and the IsDetached/IsModelInCloud flags on a real Document"
    requirement: "MDOC-04"
    verification:
      - kind: manual_procedural
        ref: "not run - 02-07 live recheck after a full Revit restart (never pyRevit Reload)"
        status: unknown
    human_judgment: true
    rationale: "The offline fixtures model the accepted G4 measurement; they do not prove how pyRevit dispatches this handler, whether the one-argument overload resolves under IronPython 3 from the Routes engine, or that no dialog appears."

duration: "8 min (start 07:13:10Z, end 07:21Z)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 05: Explicit activation of one already-open saved document Summary

**`POST /activate_document/` and an `activate_document` tool switch the Revit window to one already-open, saved, non-workshared document with an existing file path, using that document's own PathName in a single `OpenAndActivateDocument(string)` call; every other class is refused with a named 422 before any API call, and success is claimed only when the re-read active document `Equals` the target.**

## Performance

- **Duration:** 8 min (start 2026-10-22T07:13:10Z, end 07:21Z)
- **Tasks:** 2 of 2, both `tdd="true"` with a separate RED commit each, plus one small prerequisite refactor commit
- **Files:** 0 created, 4 modified (all in `files_modified`)

## Accomplishments

- **G4 gate** (`activation_refusal_reason`, pure over a duck-typed Document): fixed order unsaved, detached, no-usable-file-path (`System.IO.File.Exists`, falling back to `os.path.isfile` only where `System` cannot be imported), linked-unsupported, family-unmeasured, cloud-unmeasured, workshared-unmeasured. A saved workshared model with an existing path is refused as `workshared-unmeasured`: enabling it by analogy is exactly what the plan prohibits.
- **Orchestration** (`run_activation`): resolve the token through the 02-04 registry (400/404/503 on any doubt, omitted selector is `document-selector-required`, never a default), already-active returns 200 with zero API calls, ineligible returns 422 with `reason` and `error_code`, eligible makes the single call with `path = document.PathName`, then re-reads and resolves the same token again; 200 only if that re-read descriptor is active (Equals against the UI document), 409 `document-not-activated` otherwise.
- **Failure paths:** an API exception is a named 500 `activation-failed` whose text names the attempted document and the document active now; an unreadable re-read is 500 `activation-unverified`; an unreadable Revit state is 503 `document-registry-unavailable`. No retry, save, reopen, other path or worksharing option exists anywhere in the module (AST-pinned).
- **Route:** `/activate_document/` takes a text/plain body (bytes, str or dict) through `parse_request_data`, whole body in try/except, every reply carries `process_identity` (or `identity_error`) and `observed_active_document`.
- **Tool:** `activate_document(document, target=None, ctx=None)`, `document` required, posts via the injected `revit_post`, refuses a blank document without sending anything, renders success with the re-read active document and the answering process; refusals and failures pass through `format_response` (the bridge delivers non-200 bodies as `Error: <status> - <json>` text, which carries the reason, process and observed document).

## Task Commits

1. **Prerequisite refactor:** `92905b9` (refactor) - `from pyrevit import routes` moved inside `register_documents_routes` so `revit_mcp.documents` imports under CPython (see Deviations)
2. **Task 1 RED:** `212ffae` (test) - 45 failing activation tests (missing `run_activation`, `activation_refusal_reason`, `ACTIVATION_REFUSALS`, `_file_exists`, tool, manifest line); the 53 earlier tests kept passing
3. **Task 1 GREEN:** `df12c46` (feat) - gate, orchestration, route, tool, manifest line
4. **Task 2 RED:** `47649da` (test) - 6 failing failure-path tests (exceptions escaping, generic `activation-error` instead of `activation-failed`); the route no-change test and the two whole-file AST tests passed immediately as pins on Task 1 behavior (stated plainly: they are guard tests, not RED evidence)
5. **Task 2 GREEN:** `c096312` (feat) - exception/unverified/unreadable-state branches

## Verification (real numbers)

- Task 1 verify `uv run pytest tests/unit/test_document_contracts.py tests/unit/test_registration.py tests/unit/test_conventions.py -q`: **355 passed, 3 skipped**.
- Task 2 verify `uv run pytest tests/unit/test_document_contracts.py tests/unit/test_conventions.py -q`: **354 passed, 3 skipped**.
- Plan verification `uv run pytest tests/unit -q`: **1156 passed, 3 skipped** (baseline 1101 passed, 3 skipped; +55, all in `test_document_contracts.py`, 53 to 108 tests).
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.393** (<2.0).
- Acceptance criteria, Task 1: exactly one `OpenAndActivateDocument` call carrying the target's own PathName (test 1, with a same-titled decoy at another path); zero calls and a distinct reason for each of the seven classes (six through `run_activation`, linked at the helper level only, see below); zero calls for already-active; 200 only on an observed Equals; `activate_document` in the manifest with document, target, ctx in its Args block. Task 2: exception, no-change and refusal replies are non-200 with a truthy error plus process and observed-active identity at route level; the handler raised in no fixture.
- Offline only. `tests/unit/conftest.py` blocks real Revit and socket access; no `mcp__revit__*` tool was called, Revit was not started, stopped, reloaded or activated, and no live bridge was touched. No accidental live contact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `revit_mcp/documents.py` could not be imported under CPython**
- **Found during:** Task 1 RED (collection error `No module named 'pyrevit'` from the new test module's `from revit_mcp import documents`)
- **Issue:** the module imported `pyrevit.routes` at the top, so the pure helpers the plan asks for (`activation_refusal_reason`) and the orchestration could not be reached by the unit suite without polluting `sys.modules` with a fake `pyrevit`.
- **Fix:** moved the import inside `register_documents_routes` (CLAUDE.md already wants imports inside register functions). No behavior change; the existing 53 tests still passed. Committed alone before RED so the RED run failed on the missing activation code, not on an import error.
- **Files modified:** `revit_mcp/documents.py` (inside `files_modified`)
- **Commit:** `92905b9`

**2. [Rule 2 - Missing critical] Eighth refusal `eligibility-unreadable`**
- **Issue:** the plan names seven refusal classes; a `PathName` or flag that raises would otherwise either raise out of the gate or be read as "not set" and let an unclassified document through.
- **Fix:** an unreadable property refuses with `eligibility-unreadable` (fail closed, HTTP 422, zero API calls), pinned for each of the five flags. A raising file-exists probe maps to `no-usable-file-path`.
- **Commit:** `df12c46`

**Interface choices (not deviations from a stated requirement):** the plan gives no reply vocabulary beyond 422/200/404/400/500; the codes `document-not-activated` (409), `activation-failed`, `activation-unverified`, `document-registry-unavailable`, `request-body-invalid` and the `observed_active_document` key are mine and are listed under key-decisions. The linked-document refusal is exercised through the helper only: 02-04's registry never lists or tokenises a link document, so a token for one cannot reach the handler (the registry already refuses it earlier, which is the safer outcome).

**Total deviations:** 2 auto-fixed (one Rule 3, one Rule 2). **Impact:** none on scope; no file outside `files_modified` was touched.

## Issues Encountered / Surprises

- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on every commit (a stale registered worktree pruned by git's auto gc, same as 02-04). Commits succeeded; environment condition.
- The shell wrapper rejected large heredocs that contain apostrophes (`unexpected EOF`), so the test and source edits were made with the Edit/Write tools instead. Nothing was partially written (checked with `wc -l` and `git status`).
- `git stash list` was run once (read-only) at the start of the refactor step; no stash was created or applied.
- Task 1's tests passed at the first GREEN run and so did Task 2's; no auto-fix attempt was needed on either.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint beyond the planned `/activate_document/` (covered by T-02-03, T-02-08, T-02-13 in the plan); it only changes the UI-active document and, like every other route, is reachable by any local client of the Routes server (T-02-07 posture unchanged, no authentication claimed).

## Not run / not claimed

- **G3, G4 live behavior and G2-production are not run.** The production `/activate_document/` route has not been exercised: whether pyRevit's own ExternalEvent dispatch of a Routes handler behaves like the accepted 02-20 diagnostic callback, whether the one-argument `OpenAndActivateDocument` overload resolves under IronPython 3 (IPY342) in the Routes engine, whether `Document.IsDetached` / `IsModelInCloud` read correctly on real documents, whether `System.IO.File.Exists` behaves on non-ASCII and UNC paths, whether a request-only `(request)` handler signature is injected by pyRevit, and whether any dialog appears. This is 02-07's live recheck.
- **G6 is not authorized and not touched.** No save, reopen, source-path or worksharing workaround exists.
- **MDOC-04 is not claimed complete.** Even offline it covers only the narrowed saved-existing-path scope; saved workshared, cloud, family, unsaved and detached documents are refused, not activated. `requirements-completed` is empty (see frontmatter).
- **Revit restart required.** `revit_mcp/documents.py` is `revit_mcp/` code on the IronPython side and the extension directory is a junction to this repo. Before any live test of `/activate_document/` fully close and reopen Revit; pyRevit Reload can crash the process (CLAUDE.md). `/status/` should list `documents` among registered domains after the restart.
- `bridge.py` was not touched: `/activate_document/` is locked by default (only `GET /status/` skips the lock). `NEVER_UNLOCKED` was left as is.

## Next Phase Readiness

- 02-07 has a precisely bounded allow case (saved, non-workshared, existing file, one call with its own PathName) and a refusal list to evaluate against the production route; the reply fields to read are `activation`, `reason`, `observed_active_document` and `process_identity`.
- The 412 `document-not-active` refusal from 02-04 now points at a real step: its message says "Make it active with the separate activation step", which is `activate_document`.
- Stale docs outside this plan's file list: CLAUDE.md "Current surface" counts (one more tool and one more route than after 02-04; the manifest now lists 57 tool names), and the `document_tools.py` module docstring still says "saving and persistence".
- STATE.md, ROADMAP.md and REQUIREMENTS.md were updated through the gsd-tools verbs (REQUIREMENTS.md untouched by this plan) and left uncommitted per the dispatch instruction (they hold other sessions' uncommitted work).

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist: `92905b9`, `212ffae`, `df12c46`, `47649da`, `c096312` (`git log --oneline fe94051..HEAD`); `git rev-list --count fe940516f6f406a58f0ef1efc207de2a3768cfd7..HEAD` was 5; no tracked file deleted by any of them.
- Files exist: `revit_mcp/documents.py`, `tools/document_tools.py`, `tests/unit/test_document_contracts.py`, `tests/unit/tool_manifest.txt` (contains `activate_document` once).
- `uv run pytest tests/unit -q`: 1156 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.393`.
