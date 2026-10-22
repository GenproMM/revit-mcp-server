---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '04'
subsystem: api
tags: [document-registry, retained-reference-equals-v1, tombstones, list_documents, mutation-guard, http-412, ironpython3]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-01 process identity helper (revit_mcp/identity.py); 02-02 Wave-0 retained-reference Document doubles; 02-03 target-keyed bridge and revit_get(target=); 02-20 accepted G1/G2
provides:
  - "revit_mcp/identity.py DocumentRegistry: one retained lifetime Document per opaque token (doc1.<generation>.<n>), request-time IsValidObject + exactly-one-Equals binding, permanent tombstones, refusal by name for unreadable or ambiguous lifetimes"
  - "current_document_descriptors / resolve_document (read side) and decide_mutation_document / mutation_document_or_response (the D-08/D-09/D-10 decision table, explicit per-handler guard)"
  - "revit_mcp/documents.py GET /documents/ route and tools/document_tools.py list_documents(target=..., ctx) MCP tool (manifest updated)"
  - "tests/unit/test_document_contracts.py: 53 tests (13 Wave-0 double self-tests plus 40 new), driving the production registry with the Wave-0 doubles"
affects: [02-05, 02-06, 02-07, 02-08, 02-09, 02-10, 02-11, 02-16, 02-18]

actuals:
  tokens: 15400   # chars/4 over `git diff 4d25f30..HEAD` (61660 chars) at the last task commit; excludes this SUMMARY
  tasks: 2
  commits: 4      # MEASURED: git rev-list --count 4d25f30..HEAD before this SUMMARY commit (#3968)
plan_head_before: 4d25f309c52a0c5e60aa56ffcb801df4dec37db3

tech-stack:
  added: []
  patterns:
    - "Registry logic is pure Python over duck-typed Document objects in the helper module; route and tool stay thin, so the CPython suite reaches the decisions (CLAUDE.md: new domain logic on the testable side)"
    - "Retained-reference-equals-v1: identity is the lifetime reference plus IsValidObject plus exactly one Equals match against a fresh enumeration; id() of enumeration wrappers is used only to avoid double-claiming within one request"
    - "Guard is called explicitly by each handler (G1); it returns (document, descriptor, None) or (None, None, response) and never raises"

key-files:
  created:
    - revit_mcp/documents.py
  modified:
    - revit_mcp/identity.py
    - tools/document_tools.py
    - tests/unit/test_document_contracts.py
    - tests/unit/tool_manifest.txt
    - tests/unit/test_registration.py   # outside files_modified, one mapping line, see Deviations

key-decisions:
  - "Token = doc1.<12-hex registry generation>.<monotonic counter>; never from title, path or any hash. A registry that is lost (empty or foreign slot) gets a new generation, so an earlier token is refused as stale by name and can never be reissued."
  - "Registry is kept in the owned AppDomain slot (same mechanism as the process token), with a process-local fallback only where System cannot be imported (CPython tests)."
  - "Link documents (Document.IsLinked) are neither listed nor eligible: a loaded RVT link would otherwise make every default selection ambiguous. Not in the plan text; added because Application.Documents includes them."
  - "A new lifetime is issued a token only when no retained lifetime is in doubt: an unreadable retained lifetime could be that very document, so listing and default selection refuse instead of risking a duplicate identity."
  - "Refusal vocabulary: 400 document-selector-invalid / document-selector-required / document-identity-ambiguous; 404 document-closed / document-token-stale / document-token-unknown; 412 document-not-active only; 503 no-open-document / document-identity-unavailable / document-active-unknown / document-registry-unavailable."
  - "mutation_document_or_response returns a 3-tuple (document, descriptor, response) rather than the plan's 2-tuple plus response object, so a caller never has to type-test the result."

patterns-established:
  - "A closed or unknown selector is answered with a named 404 and the current candidates, never with whatever document is open or active"
  - "412 is reserved for open-but-inactive, in both the explicit and the sole-eligible case; the message says the call did not activate anything"

requirements-completed: []  # Deliberately empty (02-02/02-03 precedent). Offline logic is in place for MDOC-01/MDOC-03/MDOC-05 and IDENT-03/04, but no mutating route accepts a selector yet (MDOC-02, 02-05..02-11), no mutating response names its document (IDENT-02), and the production registry on live Revit (G2-production) is not run.

coverage:
  - id: D1
    description: "Two same-title unsaved documents get independent registry-issued selectors with correct, request-time active flags; empty process is an empty list; non-ASCII title/path preserved; link documents excluded"
    requirement: "MDOC-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_two_same_title_unsaved_documents_get_independent_selectors_and_flags"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_empty_application_is_an_empty_list_not_an_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "Close tombstones a token permanently; an identical title/path replacement (also under a recurring runtime hash) gets a fresh token; the stale selector is refused by name; a lost registry never reissues a token"
    requirement: "MDOC-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_replacement_with_identical_title_and_path_gets_a_fresh_token"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_registry_in_a_store_survives_reacquisition_and_a_lost_registry_never_reissues"
        status: pass
    human_judgment: false
  - id: D3
    description: "An IsValidObject (or Equals) exception and a two-match enumeration refuse by name, are not treated as closure, and never fall back to the active document or a sole-eligible guess"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_is_valid_object_exception_refuses_and_is_not_closure"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_retained_reference_with_two_matches_is_ambiguous"
        status: pass
    human_judgment: false
  - id: D4
    description: "Mutation decision table: explicit active ok, explicit inactive 412, closed/unknown/stale 404, invalid 400, omitted with 0/1/many documents; 412 locked to open-but-inactive"
    requirement: "MDOC-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_status_412_is_locked_to_the_inactive_case"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_omitted_selector_with_several_documents_refuses_and_lists_them"
        status: pass
    human_judgment: false
  - id: D5
    description: "list_documents is a registered, manifest-listed tool that renders every selector and the answering process, passes target through, and never labels a refusal as a received listing"
    requirement: "MDOC-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_list_documents_tool_renders_identity_and_every_selector"
        status: pass
      - kind: unit
        ref: "tests/unit/test_registration.py#test_tool_names_match_the_manifest"
        status: pass
    human_judgment: false
  - id: D6
    description: "Production registry on a live Revit: same-title pair, close then replacement, stale token, IsValidObject after close, Equals between enumerations, AppDomain slot retention of a Python object under IronPython 3"
    requirement: "IDENT-04"
    verification:
      - kind: manual_procedural
        ref: "not run - 02-18 live recheck after a full Revit restart (never pyRevit Reload)"
        status: unknown
    human_judgment: true
    rationale: "The Wave-0 doubles model the accepted G2 semantics; they do not prove how a real Revit Document, DocumentSet enumeration or an AppDomain data slot behaves. Preflight measured lifetime binding on PID 88388, not production issuance or tombstones."

duration: "~25 min (start time was not recorded at launch; estimated, first task commit 08:06 local to last 08:10)"
completed: 2026-10-22
status: complete
---

# Phase 2 Plan 04: Live document registry, list_documents and the mutation decision contract Summary

**Open documents are now individually selectable through opaque registry-issued tokens bound by retained lifetime reference (IsValidObject plus exactly one Equals match, permanent tombstones), exposed by a `/documents/` route and a `list_documents` tool, with one tested decision table (`decide_mutation_document` / `mutation_document_or_response`) that refuses ambiguity, closed selectors and inactive documents before any side effect, HTTP 412 only for open-but-inactive.**

## Performance

- **Completed:** 2026-10-22 (task commits 08:06 to 08:10 +01:00, see `git log`)
- **Tasks:** 2 of 2, both `tdd="true"` with a separate RED commit each
- **Files:** 1 created (`revit_mcp/documents.py`), 5 modified (one outside `files_modified`)

## Accomplishments

- **Registry** (`revit_mcp/identity.py`, 433 lines added in the first GREEN, more in the second): `DocumentRegistry.observe()` runs on every request. For each retained lifetime it checks `IsValidObject` then counts `Equals` matches in a fresh `Application.Documents` enumeration: one match is bound; invalid or none is retired and the token tombstoned permanently; several is `document-identity-ambiguous`; a check that raises is `document-identity-unavailable` and is neither closure nor a pass. New lifetimes get `doc1.<generation>.<counter>`; the counter only grows, the generation changes whenever the registry is recreated, so no token is ever reissued within or across registries. Title and path never take part in identity.
- **Read side:** `current_document_descriptors()` returns title, path, saved, active and the selector for every non-link open document, `active` computed against the UI document at request time (never cached); an empty process is valid data; a registry in doubt refuses instead of returning a shortened list. `resolve_document(selector)` returns the document or a named refusal with the current candidates.
- **Route and tool:** `GET /documents/` (thin, zero-argument handler like `model_info`, so a document-less process answers an empty list rather than 503) with `process_identity` in the body; `list_documents(target=None, ctx=None)` renders every selector, marks the active one and ends with "Answering Revit process: PID ...; port ...; session ..." taken from the received body, so a refusal or unsent request is never attributed to a process.
- **Decision contract:** `decide_mutation_document(selector)` implements D-08/D-09/D-10; `mutation_document_or_response(selector, ...)` is the explicit per-handler guard (no wrapper or decorator in `startup.py`, asserted by a test). Rejections carry `error`, `error_code`, `process_identity` (or `identity_error`), `candidates` and, for 412, `active_document`.

### Decision table (locked by tests)

| Selector | State | Result |
|---|---|---|
| explicit | open and active | ok, returns Document and descriptor |
| explicit | open, not active | **412** `document-not-active`, never activates, never retargets |
| explicit | closed (tombstoned) | 404 `document-closed`, candidates listed, survivor not substituted |
| explicit | other registry generation / never issued | 404 `document-token-stale` / `document-token-unknown` |
| explicit | not a token (a title, a path, empty, wrong type) | 400 `document-selector-invalid` |
| explicit | lifetime unreadable | 503 `document-identity-unavailable` (not closure) |
| explicit | lifetime matches several documents | 400 `document-identity-ambiguous` |
| omitted | one non-link document, active | ok |
| omitted | one non-link document, not active | **412** `document-not-active` |
| omitted | none open | 503 `no-open-document` |
| omitted | several open | 400 `document-selector-required`, every candidate listed; the UI selection is not used |
| either | active comparison raised | 503 `document-active-unknown` |

## Task Commits

1. **Task 1 RED:** `d8146c3` (test) - 22 registry/descriptor/tool/route-shape tests failing on missing `DocumentRegistry` and `documents.py`
2. **Task 1 GREEN:** `9b01c6b` (feat) - registry, `/documents/`, `list_documents`, manifest line, mapping line
3. **Task 2 RED:** `9ec0a71` (test) - 15 failing decision-table and guard tests (missing `decide_mutation_document`)
4. **Task 2 GREEN:** `901f386` (feat) - decision table, guard, plus three route-handler tests with a fake `pyrevit`

## Verification (real numbers)

- Task 1 verify `uv run pytest tests/unit/test_document_contracts.py tests/unit/test_registration.py tests/unit/test_conventions.py -q`: **292 passed, 3 skipped**.
- Task 2 verify `uv run pytest tests/unit/test_document_contracts.py tests/unit/test_conventions.py -q` (also run with registration and process-identity): **316 passed, 3 skipped**.
- Plan verification `uv run pytest tests/unit -q`: **1101 passed, 3 skipped** (baseline given for this run: 1056 passed, 3 skipped; +45). `test_document_contracts.py` itself went from 13 to 53 tests (+40); I did not reconcile the other 5 of the +45 against the baseline, which came from the dispatch rather than a run of mine.
- `uv run python scripts/conventions.py`: clean (exit 0). `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.422** (<2.0).
- Offline only. `tests/unit/conftest.py` blocked the bridge from a real Revit; no `mcp__revit__*` tool was called, Revit was not started, stopped or reloaded, and no live bridge was touched. No accidental live contact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `test_registration.py` had no tools module for the new route domain**
- **Found during:** Task 1 GREEN
- **Issue:** `test_every_route_domain_has_a_matching_tool_module` derives `documents` -> `documents_tools`, but the plan fixes the tool in `tools/document_tools.py` (the existing module that also drives `revit_mcp/document.py`).
- **Fix:** one line in `KNOWN_MAPPINGS`: `"documents": "document_tools"`. No assertion weakened.
- **Files modified:** `tests/unit/test_registration.py` (outside `files_modified`)
- **Commit:** `9b01c6b`

**2. [Rule 2 - Missing critical] Link documents are excluded**
- **Found during:** Task 1 design
- **Issue:** `Application.Documents` includes documents of loaded RVT links; counting them would make D-09's sole-eligible rule refuse on any model with a loaded link, and would offer a link as a mutation target.
- **Fix:** `Document.IsLinked` documents are never listed, tokenised or eligible; an unreadable flag keeps the document (only able to make a default selection refuse, never to pick wrongly). Pinned by `test_linked_documents_are_never_listed_or_eligible`.
- **Commit:** `9b01c6b`

**3. [Interface choice] `mutation_document_or_response` returns a 3-tuple**
- The plan says "(resolved Document, descriptor) only on success; rejection yields routes.make_response". A single return that is a tuple on success and a response object on failure forces callers to type-test, so it returns `(document, descriptor, None)` or `(None, None, response)`. 02-05 onward should unpack three values.

**Total deviations:** 3 (one Rule 3, one Rule 2, one interface choice). **Impact:** none on scope; one test-mapping line outside the file list.

## Issues Encountered / Surprises

- `git commit` printed `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` (a stale registered worktree being pruned by git's auto gc). Commits succeeded; it is an environment condition, not caused by this plan.
- Task 1's RED run failed on `AttributeError` for the not-yet-written registry (15), `LocalStore` (2), `KeyError: 'list_documents'` (4) and the missing route file (1), i.e. for the intended reasons.
- The start time was not recorded at launch, so the duration is an estimate.

## Known Stubs

None. `list_documents`' docstring states that most tools do not yet accept a document selector; that is a true statement of the current surface, not a stub.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: local-path-disclosure | revit_mcp/documents.py | `GET /documents/` returns the full local path of every open model to any local client that can reach the Routes server. Accepted as T-02-07 (inherent in D-08, local MCP clients only); external authentication is Phase 5 and is not claimed. |

## Not run / not claimed

- **G2-production** (the registry on live Revit: same-title pair, close then replacement, stale token, real `IsValidObject` after close, `Equals` between `DocumentSet` enumerations, a Python registry object retained in the AppDomain data slot under IronPython 3, whether `HOST_APP.uiapp.ActiveUIDocument` is the right active-document read): not run. 02-18, after a full Revit restart.
- **G3, G4** (inactive-document read safety, production activation) and **G6** (write/read reproduction, needs separate authorization): not run, not authorized here.
- **Revit restart required.** `revit_mcp/identity.py` and `revit_mcp/documents.py` are new `revit_mcp/` code on the IronPython side, and the extension directory is a junction to this repo. Before any live test of `/documents/` fully close and reopen Revit; pyRevit Reload can crash the process (CLAUDE.md). Later plans must not test route changes live until that restart has happened. Note too that `startup.py` discovery must pick `documents.py` up (alphabetically beside `document.py`); `/status/` should list `documents` among registered domains after the restart.
- `HOST_APP.uiapp.ActiveUIDocument` and the zero-argument route handler shape follow `model_info.py`/`status.py` precedent but are unverified on a live engine.

## Next Phase Readiness

- 02-05 onward can call `mutation_document_or_response(selector, ...)` from their own handlers (explicit call, three return values) and add a `document` argument to their tools; `revit_get("/documents/", target=...)` and `list_documents` are available.
- Stale docs outside this plan's file list: CLAUDE.md "Current surface" tool/route/domain counts (now one more tool, one more route, one more domain than the 02-03 note), and the module-list wording.
- `requirements-completed` left empty on purpose (see frontmatter).
- STATE.md, ROADMAP.md and REQUIREMENTS.md were updated through the gsd-tools verbs and left uncommitted per the dispatch instruction (they hold other sessions' uncommitted work).

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist: `d8146c3`, `9b01c6b`, `9ec0a71`, `901f386` (`git log --oneline 4d25f30..HEAD`); `git rev-list --count 4d25f30..HEAD` was 4; no tracked file deleted by any of them.
- Files exist: `revit_mcp/documents.py`, `revit_mcp/identity.py`, `tools/document_tools.py`, `tests/unit/test_document_contracts.py`, `tests/unit/tool_manifest.txt` (contains `list_documents`).
- `uv run pytest tests/unit -q`: 1101 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.422`.

---
*Phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin*
*Completed: 2026-10-22*
