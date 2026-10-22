---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '17'
subsystem: testing
status: complete
tags: [regression-inventory, contract-sweep, ast, discovery, exception-table, d-15, g1, g4, selector-edge-shapes, netstat, concurrency]

requires:
  - phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
    provides: 02-03..02-16 (per-incarnation bridge, target on every Revit-facing tool, guarded mutation routes with identity attribution, documents routes, the single provenance renderer) and 02-19 (process tools honour discovered ambiguity)
provides:
  - "tests/unit/inventory_support.py: discovery of every tool (real registrars through tools.register_tools) and every route (@api.route handlers inside each register_*_routes, read with ast), plus the hand classification tables TOOL_CLASSES / ROUTE_CLASSES and the named exception sets"
  - "tests/unit/test_phase2_inventory.py (589 tests): the exhaustive tool and route inventory; fails on any unclassified, stale, unmanifested, unaddressed or misclassified tool or route"
  - "All-domain provenance checks (test_identity_rendering.py) and an exhaustive G4 activation table (test_document_contracts.py)"
  - "Task 2 property tables: selector and netstat edge shapes, listener ordering, stale-selector and restart interleavings, per-process in-flight counts, close/replace between list and call"
affects: [02-18]

actuals:
  tokens: 24078   # chars/4 over `git diff 73f7c36..HEAD` (96314 chars) at the last task commit, tests only; excludes this SUMMARY
  tasks: 2
  commits: 2      # MEASURED: git rev-list --count 73f7c360f3e7c5804c3b7b326527d322d253361b..HEAD before this SUMMARY commit (#3968)
plan_head_before: 73f7c360f3e7c5804c3b7b326527d322d253361b

tech-stack:
  added: []
  patterns:
    - "Inventory by discovery, classification by hand: a tool or route that is discovered but not in a table fails until classified"
    - "Source-level (ast) per-handler assertions for the Revit half, which cannot be imported under CPython"
    - "Static same-module call-graph reachability to classify routes by what they DO (no Transaction/Save/Delete/Open reachable from a read)"
    - "Exception rows pinned as exact sets so a named exception cannot grow silently"

key-files:
  created:
    - tests/unit/inventory_support.py
    - tests/unit/test_phase2_inventory.py
  modified:
    - tests/unit/test_identity_rendering.py
    - tests/unit/test_document_contracts.py
    - tests/unit/test_target_resolution.py
    - tests/unit/test_target_locks.py

key-decisions:
  - "The exhaustive inventory lives in two NEW files (support module + test module) instead of inside the 3178-line test_document_contracts.py. The dispatch allowed new inventory files under tests/unit/; test_document_contracts.py still gained the exhaustive G4 table and the Task 2 document edge tables."
  - "Tool and route classes are by what the tool/route does, never by HTTP method. POST reads (/ai_filter/, /material_quantities/, /clash_check/, /list_category_parameters/) are reads, and a read route is proven to reach no Transaction, Commit, Delete, Save, SaveAs, SynchronizeWithCentral, Close, OpenDocumentFile, OpenAndActivateDocument, EditFamily or LoadFamily."
  - "No production file changed. Every guarded handler already had the exact shape (guard as the first statement, then the refusal return, no use of the injected doc, attribute_response with the descriptor and uiapp), so the sweep found no omission to fix."
  - "Minimal per-tool arguments for the behavioural checks are read from the four existing per-module forwarding inventories, so a tool covered there stays covered here, and a tool missing from both fails with an instruction."
  - "The two HTTP-thread routes (/model_info/, /status/) are an exact allow-list with their literal signatures; a third handler without uiapp/uidoc/doc fails, and so does a stale entry once one of the two is fixed."

patterns-established:
  - "Adding a tool: manifest line + TOOL_CLASSES row (+ minimal kwargs if no forwarding suite owns it). Adding a route: ROUTE_CLASSES row, a mutation also needs a guarded handler of the exact shape and a row in one route-suite MUTATIONS table."

requirements-completed: []  # Deliberately empty (02-02..02-16 precedent). Offline inventory evidence is not acceptance of IDENT/AMBIG/MDOC: the live gates in 02-18 are still required (see "What remains for 02-18").

coverage:
  - id: I1
    description: "Every registered tool is classified, in the manifest and in discovery (three-way set equality); every discovered route is classified, with no stale row"
    requirement: "D-01/D-09"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_discovered_tools_manifest_and_classification_are_the_same_set"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_every_discovered_route_is_classified_and_no_classification_is_stale"
        status: pass
    human_judgment: false
  - id: I2
    description: "Every tool transport call addresses an existing route with a matching method; every route is addressed; the 31 mutation tools and the 31 guarded routes are one to one; only the named tools reach open_model, execute_code and activate_document"
    requirement: "D-01/D-13"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_every_tool_transport_call_addresses_a_route_that_exists_with_a_matching_method"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_the_mutation_tools_and_the_guarded_routes_are_the_same_set_one_to_one"
        status: pass
    human_judgment: false
  - id: I3
    description: "Per-class signatures (target everywhere except the three named local tools; document only on mutations plus the two addressed reads and activation), docstring Args, scope phrases, forwarding of target as a transport keyword never in the body, document in the POST body only when given, blank/non-string document refused before send, reads reject a document"
    requirement: "D-01/D-05/D-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_tool_signature_matches_its_class"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_a_mutation_refuses_a_blank_or_non_string_document_without_sending"
        status: pass
    human_judgment: false
  - id: I4
    description: "D-15: execute_revit_code and /execute_code/ stay registered and in the manifest, the tool forwards target and takes no document, its docstring carries the exception label and no confinement claim, the route is unguarded and stamps only document_scope plus process identity, and neither is classified as guarded or confined"
    requirement: "T-02-11 / T-02-14"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_d15_execute_surfaces_are_registered_in_the_manifest_and_classified_as_the_exception"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_the_execute_route_is_unguarded_stamps_only_scope_and_process_and_never_a_document"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_the_d15_scope_notice_reaches_the_model_and_no_changed_document_is_rendered"
        status: pass
    human_judgment: false
  - id: I5
    description: "Every route handler declares uiapp, uidoc or doc except the exact two-route HTTP-thread allow-list; a third such handler fails"
    requirement: "02-07 finding"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_every_route_handler_declares_uiapp_uidoc_or_doc_except_the_two_known_http_thread_routes"
        status: pass
    human_judgment: false
  - id: I6
    description: "G1 explicit-route-only: every guarded handler calls mutation_document_or_response(request_document_selector(request), uiapp=uiapp) as its first statement, returns the refusal, never reads the injected doc, attaches the actual descriptor and process identity, and opens no transaction itself; startup.py touches api only to pass it to the registrar; no domain imports another domain in any import form or scope"
    requirement: "D-13 / T-02-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_a_guarded_handler_calls_the_explicit_guard_first_and_attributes_every_reply (31 routes)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_startup_installs_no_common_handler_wrapper"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_no_revit_mcp_module_imports_a_domain_module_in_any_form_or_scope"
        status: pass
    human_judgment: false
  - id: I7
    description: "Classification by behaviour: no read route (including POST reads) reaches a mutation primitive; every transacting guarded route reaches a Transaction; the only guarded routes without one are save_document, load_family and set_active_view"
    requirement: "D-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_a_read_route_reaches_no_transaction_save_delete_open_or_activation"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_a_guarded_route_opens_a_transaction_unless_it_is_a_named_exception"
        status: pass
    human_judgment: false
  - id: I8
    description: "G4: documents.run_activation holds the only OpenAndActivateDocument call outside open_model, is reachable only from the activate_document route, the refusal gate precedes the call, and the allow branch is reached for exactly one cell of the 2^5 flags x saved x file-exists table"
    requirement: "D-12"
    verification:
      - kind: unit
        ref: "tests/unit/test_phase2_inventory.py#test_only_documents_activation_and_the_file_open_may_activate_a_document"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_activation_is_reachable_only_for_the_saved_non_workshared_existing_path_class"
        status: pass
    human_judgment: false
  - id: I9
    description: "Provenance for every tool: the verified process on every received success except the exact named pre-renderers (and the get_revit_view Image), attributed received errors for all tools including the exceptions, nobody credited when nothing was sent, outcome UNKNOWN labelled unconfirmed, a forged process_identity in an untagged body never a verified process"
    requirement: "T-02-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_every_tool_names_the_verified_process_on_success_except_the_named_prerenderers"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_rendering.py#test_every_tool_attributes_a_received_error_including_the_named_exceptions"
        status: pass
    human_judgment: false
  - id: I10
    description: "Selector and listener edge shapes: 49 malformed and 9 non-string target selectors refuse before any client or inventory; 38 malformed netstat texts (22 shapes, 16 of them repeated after a good row) are unavailable, never an empty inventory, through both the selected and the default path; shared-port owners in either order refuse naming every PID; document selector shapes refuse by name and never decay to the default"
    requirement: "D-02/D-03/D-04/D-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_target_resolution.py#test_a_malformed_selector_sends_nothing_through_every_transport"
        status: pass
      - kind: unit
        ref: "tests/unit/test_target_resolution.py#test_malformed_netstat_text_refuses_a_selected_call_and_the_default_call"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_malformed_document_selectors_refuse_by_name_and_never_decay_to_the_one_document"
        status: pass
    human_judgment: false
  - id: I11
    description: "Concurrency: simultaneous stale selectors after a restart all refuse and nothing is routed to the new process; stale and current selectors interleaved never swap incarnations; a restart between two queued calls refuses the second; one process never has two requests in flight while two processes overlap; a document closed between list and call is refused by every verb"
    requirement: "D-03/D-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_target_locks.py#test_one_process_never_has_two_requests_in_flight_and_two_processes_overlap"
        status: pass
      - kind: unit
        ref: "tests/unit/test_target_locks.py#test_stale_and_current_selectors_interleaved_never_swap_incarnations"
        status: pass
      - kind: unit
        ref: "tests/unit/test_document_contracts.py#test_a_document_closed_between_list_and_call_is_refused_by_every_verb"
        status: pass
    human_judgment: false
  - id: I12
    description: "Real Revit behaviour of any of the above (live identity, same-title pair, close-then-replacement, duplicate-listener refusal, saved-workshared activation, the two HTTP-thread routes)"
    requirement: "IDENT/AMBIG/MDOC"
    verification:
      - kind: manual_procedural
        ref: "not run - 02-18 live gates need separate user authorization"
        status: unknown
    human_judgment: true
    rationale: "Everything here is source analysis, fakes, httpx.MockTransport and faked netstat; no live Revit was contacted."

duration: "not timed (start time was not captured at plan start)"
completed: 2026-10-22
---

# Phase 2 Plan 17: Exhaustive tool and route regression inventory Summary

**Every registered tool and every route handler is now derived from the real registrars, classified by what it does, and checked against the phase contract; an unclassified tool or route, a handler that loses its guard or its uiapp/uidoc/doc, a read that reaches a transaction, a wrapper in startup.py, a domain-to-domain import or a growing exception list all fail the suite.**

## True inventory counts (source of truth for the docs sweep)

The inventory test prints `INVENTORY_COUNTS` (run `uv run pytest tests/unit/test_phase2_inventory.py -q -s -k true_inventory`):

```
INVENTORY_COUNTS guarded_mutation_routes=31 local_process_tools=3 revit_facing_tools=56 route_domains=24 routes=56 tool_domains=25 tools=59
```

| Fact | True value | CLAUDE.md says |
|---|---|---|
| MCP tools (registered = manifest = classified) | **59** | 54 |
| of which Revit-facing | 56 | |
| of which local, no `target` by design | 3 (`discover_revit_targets`, `get_revit_process_status`, `start_revit`) | |
| Routes (`@api.route` handlers) | **56** | 51 |
| Route domains (revit_mcp modules with a `register_*_routes`) | **24** | 23 |
| Tool domains (tools modules with a `register_*_tools`) | 25 (plus the `utils` helper) | |
| Guarded document-changing routes = mutation tools | **31** (including transform, create_view, set_active_view) | the plan text said "33 + 3" |

Route classes: 31 guarded mutation, 16 active-document reads (four of them POST reads), 2 HTTP-thread (`/model_info/`, `/status/`), 1 registry list, 2 registry-addressed reads, 1 activation, 1 file preview (`/model_worksets/`), 1 process-level open (`/open_model/`), 1 D-15 (`/execute_code/`). Tool classes: 31 mutation, 18 read, 1 status, 2 addressed read, 1 activation, 1 file read, 1 process open, 1 D-15, 3 local.

The plan's "33 guarded mutations of 02-12..02-14 plus transform/create_view/set_active_view" does not match the code: there are 31 guarded routes in total, one per mutation tool. The discrepancy is in the plan's arithmetic, not in the code; the inventory derives the number.

## What was built

**Task 1 - inventory** (`inventory_support.py`, `test_phase2_inventory.py`, additions to `test_identity_rendering.py` and `test_document_contracts.py`).
- Discovery: tools by running `tools.register_tools` against a recording transport; routes by `ast` over `revit_mcp/*.py` (decorator nested in a registrar, methods, arguments, same-module call graph). Tool-to-route pairs are read from the transport call in each tool's source.
- Tables: `TOOL_CLASSES`, `ROUTE_CLASSES`, `NO_TARGET_BY_DESIGN`, `PRERENDERED_SUCCESS`, `HTTP_THREAD_ALLOWLIST`, `GUARDED_WITHOUT_TRANSACTION`, `ALLOWED_ROUTE_CLASSES`.
- Tool contract (parametrized over every tool): signature per class, docstring `Args:` and scope phrases (mutations name `list_documents`, `activate_document`, 412, the only open document, several), `target` forwarded as a transport keyword never in the body, nothing extra without a selector, the document in the POST body only when given, a blank or non-string document refused before any send, a `document` argument rejected (TypeError, no send) on every read and process-level tool.
- Route contract: exact HTTP-thread allow-list; every guarded handler checked by AST (guard first, then `if refusal is not None: return refusal`, no read of the injected `doc`, `attribute_response(..., descriptor, uiapp=uiapp)`, no transaction in the handler); a guarded module imports the guard relatively from `.identity`; the guarded set equals the union of the four behavioural route suites' `MUTATIONS`; reads and POST reads reach no mutation primitive; every transacting guarded route reaches a Transaction.
- D-15 row, `open_model` row, G4 call-site pins, `startup.py` no-wrapper pin, no-domain-import pin (all import forms, nested included, `__import__` included).
- All-domain provenance (`test_identity_rendering.py`): every tool run on a tagged reply; the exact set without the verified-process line on success is the four pre-renderers plus the `get_revit_view` Image; errors are attributed for all 56; unsent and outcome-unknown results credit nobody for all 56.
- Exhaustive G4 table: 2^5 flag combinations x saved x file-exists; the allow branch (one `OpenAndActivateDocument(own path)`, 200) is reached for exactly one cell, every other cell is 422 with zero API calls and the other document stays active.

**Task 2 - edge shapes and interleavings** (`test_target_resolution.py`, `test_target_locks.py`, `test_document_contracts.py`).
- 49 malformed and 9 non-string target selectors (bad prefix, whitespace, non-ASCII, over-length, duplicate keys, missing or extra fields, bool/float/string port and pid, wildcard/remote/unicode hosts, uppercase/braced/urn tokens, invalid UTF-8): a ValueError from the parser and a named `Error:` through get, status, post and image with no client and no inventory used; falsy non-strings (0, False, [], {}) never decay to the default target.
- 22 malformed netstat shapes plus 16 of them repeated after a good row (38 texts): unavailable (never an empty inventory) at the parser, through the adapter and through both the selected and the default path; a shared port is refused with every PID whichever owner is listed first; row ordering and noise never change the owner; adapter fails closed on exit code, OS error, timeout, decode error and a non-Windows platform.
- Concurrency: per-process in-flight count tables (1..4 calls on one process, 1..4 on two): peak 1 per process, 2 overall when both are used; reads, posts and images to one process all serialized; simultaneous stale selectors after a restart all refuse and route nothing; stale and current selectors interleaved are never swapped; a restart between two queued calls refuses the second; every listener ordering of a shared port refuses all simultaneous calls; a cancelled call among simultaneous ones blocks nobody.
- Documents: 45 malformed selector shapes (and the request-body shapes that produce them, including `"document": null` read as an explicit broken choice, never as omitted) refuse by name with no document returned and no decay to the one-open-document default, with one and with several documents open; NFC/NFD/case-variant non-ASCII titles are distinct lifetimes; enumeration order between list and call never changes what a token means; a document closed between list and call is refused by resolve, mutate and activate and a look-alike with identical title and path gets its own token; repeated close and reopen never recycles a token.

## Named exceptions (exact sets, cannot grow silently)

| Exception | Why it differs from the plain contract | Pinned by |
|---|---|---|
| `discover_revit_targets`, `get_revit_process_status`, `start_revit` | local process tools, no `target` by design (02-19 made the last two honour discovered ambiguity) | `test_the_exact_set_of_tools_without_a_target_is_the_named_local_process_tools` |
| `open_model` / `/open_model/` | process-level file open: `target` only, no document selector, process identity stamped, the document Revit actually opened is read from the opened Document (`_open_model` references `_opened_document_descriptor`) | `test_open_model_is_process_level_with_the_actual_opened_document_identity` |
| `activate_document` / `/activate_document/` | the explicit G4 activation; the only `OpenAndActivateDocument` call outside `open_model`; allow branch only for saved, non-workshared, existing-path | G4 pins and the exhaustive table |
| `execute_revit_code` / `/execute_code/` | D-15 trusted arbitrary-code exception: available, forwards `target`, no document, honest label, replies carry `document_scope` and process identity and never a changed document | the D-15 rows |
| `/model_info/` (`get_model_info()`) and `/status/` (`revit_status(verbose)`) | declare none of uiapp/uidoc/doc, so pyRevit runs them on its HTTP thread; recorded follow-up concerns, deliberately not changed here | `test_every_route_handler_declares_uiapp_uidoc_or_doc_except_...` |
| `list_documents`, `activate_document`, `read_document_summary`, `read_document_levels` | pre-render their success text, so the bridge tag is lost on success; they name the process from the reply's own stamp (`Answering Revit process:`); their error paths are attributed | `test_every_tool_names_the_verified_process_on_success_except_the_named_prerenderers` |
| `get_revit_view` | returns an Image on HTTP 200 (no text channel); an error string is attributed | same test plus `test_get_revit_view_adds_no_attribution_to_a_non_text_success_reply` |
| `/save_document/`, `/load_family/`, `/set_active_view/` | guarded mutations that legitimately open no project transaction (Save/SaveAs run outside one; LoadFamily; a UI view switch) | `test_the_named_no_transaction_mutations_are_exactly_the_documented_three` |

## Commits

1. **Task 1:** `9ac26d7` (test) - inventory_support.py, test_phase2_inventory.py, additions to test_identity_rendering.py and test_document_contracts.py
2. **Task 2:** `6e7d8c4` (test) - additions to test_target_resolution.py, test_target_locks.py and test_document_contracts.py

## Verification (real numbers)

- Task 1 verify `uv run pytest tests/unit/test_document_contracts.py tests/unit/test_identity_rendering.py tests/unit/test_registration.py -q` plus the new file: green (668 passed for identity + inventory + registration at the time).
- `uv run pytest tests/unit -q`: **3752 passed, 3 skipped** (baseline 2858 passed, 3 skipped; +894). Per file now: test_phase2_inventory 589, test_identity_rendering 68, test_document_contracts 313, test_target_resolution 323, test_target_locks 42. No pre-existing failure.
- `uv run python scripts/conventions.py`: exit 0, no output. `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.378** (<2.0).
- **TDD honesty:** the inventory and edge tests restate behaviour already built, so none of them could be red first (no production file changed). They were proven to bite with 22 temporary mutations, each applied to the real file with a before/after SHA-256 check, restored byte-for-byte, `git diff` clean afterwards (startup.py was already modified by another session and was restored to its exact prior bytes). Caught: a read handler losing `doc`; a read reaching a Transaction; a tool losing `target`; the execute stamp adding a `document` key; a nested import of another domain; an inverted refusal condition; a handler reading the injected `doc` before the guard; a new unclassified route; a second activation call site; a wrapper in startup.py; the mutation guard called from a read route; the execute docstring losing its label; a tool bypassing the renderer on success and another on its error path; activation ignoring a flag; a loosened uuid spelling in `parse_target`; an ignored unknown netstat state (first not caught by my cases, which only had a single bad row - fixed by adding the bad-row-after-a-good-row variants, then caught by 6 of them with the pre-existing parity test deselected); a lock key that ignores the process; a blank document decaying to the default; `"document": null` read as omitted; a proof cached across queued calls.
- Offline only. No `mcp__revit__*` tool was called, `execute_revit_code` was never run, the live bridge and every document were left alone (a Revit was open); tests/unit/conftest.py kept the bridge away from the real listener table and sockets. **No accidental live contact.**

## Deviations from Plan

### Auto-fixed Issues

None. The sweep found no real omission: no tool or route violated the contract, so no production file was touched (no Rule 1 fix).

### Interface choices

1. **New files for the exhaustive inventory** (`inventory_support.py`, `test_phase2_inventory.py`) rather than appending 650 lines to `test_document_contracts.py`; allowed by the dispatch. The plan's `artifacts` entry naming `test_document_contracts.py` as the home of the schema/route inventory is therefore satisfied by the new file, while `test_document_contracts.py` carries the G4 table and the Task 2 document edge tables.
2. **Sibling test modules are imported** (`test_document_contracts`, `test_tool_forwarding_*`, `test_routes_*_identity`) so the per-module hand inventories and this one cannot drift apart: the guarded set must equal the union of the four route suites' `MUTATIONS`, and the minimal tool arguments come from the four forwarding suites. This relies on pytest's default import mode (tests/unit has no `__init__.py`).
3. **The plan-level ledger file** (`gsd-plan-head-before-02-17`, protocol 0c) was not created at start; the base `73f7c36` is the HEAD recorded by the `git log` at the start of the run, and `git rev-list --count` from it was 2 before this SUMMARY.

## Observations (not fixed; nothing here was in scope or wrong enough to change)

1. **A trailing newline passes the document-token shape regex.** `_TOKEN_SHAPE` ends in `$`, which matches before a final `\n`; `"doc1.<gen>.1\n"` is therefore classified as a well-formed token and then refused as `document-token-unknown` (404) rather than `document-selector-invalid` (400). It is refused either way and never resolves, so the tests pin "refused by name, no document" for it, not the exact code. Switching the regex to `\Z`/`fullmatch` would make it a 400; left alone.
2. **A padded target selector is refused** (the parser's alphabet has no `=`); only the unpadded form `discover_revit_targets` emits is accepted. This is deterministic and now pinned.
3. **`get_revit_view` returns `str(response)` for a non-text success reply.** That is the pre-existing behaviour (02-16 only changed the error branch) although the docstring promises an image; it is outside this plan and recorded here only because the inventory pins that no attribution is added to it. Worth a look in the docs/live sweep.
4. **The four pre-rendering document tools do show the verified-process line for a reply body they do not recognise** (they fall through to `format_response(response)`); the named exception is exactly their recognised success shape. The inventory pins both.
5. `git commit` prints `error: failed to delete '.git/worktrees/hot-cirrus': Permission denied` on every commit (stale worktree registration, as in earlier plans); commits succeed.
6. CLAUDE.md (54 tools / 51 routes / 23 domains, "Known sharp edges" on REVIT_HOST/REVIT_PORT) is stale; not touched here, as instructed. The true counts above are the source for the docs sweep.

## Known Stubs

None.

## Threat Flags

None. No endpoint, auth path or schema was added and no production file changed. T-02-03 (a mutation unguarded or a tool unable to pass the selected document) and T-02-02 (received identity not rendered by a domain path) are mitigated by tests that fail on a violation; T-02-11 stays accepted per D-15 and T-02-14 is mitigated (the label and the no-attribution property of both execute surfaces are pinned).

## What remains for 02-18 (live acceptance; nothing here is claimed as observed)

- **G2-production**: a same-title pair of documents and close-then-replacement against a real Revit (the tombstoned token must refuse; a replacement with identical title and path must get a fresh token).
- **G5-production**: duplicate-listener refusal on a real same-port collision (all PIDs named, the requested route not sent).
- **G6**: not authorized; the param-write-rolls-back diagnosis was not run.
- **Saved-workshared activation**: not run; the policy refuses it (`workshared-unmeasured`) and the exhaustive table proves the refusal offline only.
- **The two HTTP-thread routes** (`/model_info/`, `/status/`): their behaviour on a live Revit (HTTP-thread execution) is unobserved and they are deliberately unchanged.
- Rendering on real replies, a real rolled-back 409, a real conflicting stamp, a real `open_model` opened-document identity and a real `UIDocument.ActiveView` switch remain unobserved (carried from 02-15/02-16).
- All `revit_mcp/` edits of 02-12..02-15 still need a full Revit close/reopen (never Reload) before any live run.

## Self-Check: PASSED

Verified on disk and in git before writing this line:
- Commits exist in `git log`: `9ac26d7`, `6e7d8c4`; `git rev-list --count 73f7c360f3e7c5804c3b7b326527d322d253361b..HEAD` was 2; no tracked file was deleted by either; `git status --short -- bridge.py tools revit_mcp tests` shows only the untracked other-session `tests/unit/test_parallel_installation.py`.
- Files exist: tests/unit/inventory_support.py, tests/unit/test_phase2_inventory.py, and the four modified test files.
- `uv run pytest tests/unit -q`: 3752 passed, 3 skipped; `scripts/conventions.py` exit 0; `INIT_LATENCY_S=0.378`.
