---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "02"
subsystem: mutation-safety
tags: [policy, elicitation, hmac-permit, bridge-seam, ironpython-verifier, payload]

requires:
  - phase: 07-repository-owned-mutation-safety-and-human-approval
    provides: "plan 07-01: mcp 1.30 SDK, structured_output default, elicitation_support harness"
provides:
  - "policy.py + policy.base.toml: TOML policy classifying all 59 tools and 56 routes (D-10..D-13, D-22, D-25)"
  - "approval.py: authorize / ask_human (server-side elicitation, consent = action only) / Russian window text / refusal texts"
  - "permit.py + revit_mcp/permits.py: HMAC permit over the exact wire text, envelope first, single-use registry on the Revit side"
  - "bridge.revit_post authorization seam (_authorize, fails closed), human wait before _dispatch so no lock is held"
  - "payload copies the new modules and the base policy; stdout guard covers them"
affects: [07-03, 07-04, 07-05, 07-06, 07-07, 07-09, 07-10, 07-11, 07-14]

actuals:
  tokens: 18260        # chars/4 over the realized diff (73042 chars) of the two task commits
  tasks: 2
  commits: 2
plan_head_before: b55bc545687f6433eaff2b9bb8278441d0891322
commits: 2

tech-stack:
  added: []
  patterns:
    - "authorizer seam: module attribute _authorize in bridge, None = refuse, conftest installs an allow-all test authorizer"
    - "permit hashes the exact wire text; envelope member first, split with json raw_decode on the Revit side"
    - "policy as frozen dataclasses over tomllib with a minimal validator (07-04 completes it)"

key-files:
  created: [policy.py, policy.base.toml, approval.py, permit.py, revit_mcp/permits.py, tests/unit/test_phase7_tracer.py]
  modified: [bridge.py, tests/unit/conftest.py, tests/unit/audit_support.py, tests/unit/test_audit_stdio.py, deploy/build-payload.cmd, tests/unit/test_payload_ships_root_modules.py]

key-decisions:
  - "The authorizer runs inside revit_post before _dispatch; the target is resolved once and its selector is handed to _dispatch, so permit session token, window text and send address one incarnation"
  - "A gated POST with no loaded secret is refused (no_secret) instead of being sent unenveloped: nothing can be enforced without a secret"
  - "Consent is ElicitResult.action == accept only; content, agent text and arguments are never read"
  - "policy.current() does not cache a failure: an invalid base raises PolicyError on each call and is re-read, so a repaired file is picked up"
  - "edit_family carries confirm_when = [] in the base policy (its check is confirm-or-deny, not word-driven); 07-04 owns the vocabulary"

requirements-completed: [SAFE-01, SAFE-03, SAFE-11]

coverage:
  - id: D1
    description: "delete_elements through the audited FastMCP and the production bridge opens exactly one Russian window (Код операции + 6 hex), and after accept sends exactly one envelope-first POST whose permit the Revit-side verifier accepts once and then reports replayed; the unchanged gate strips the envelope"
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_delete_is_confirmed_once_sent_once_and_the_revit_verifier_accepts_the_bytes_once"
        status: pass
    human_judgment: false
  - id: D2
    description: "Decline, a client without elicitation, an approved=true style claim, an unknown route, a missing authorizer, a missing secret and a raising authorizer all send nothing and say the request was NOT sent"
    requirement: SAFE-01
    verification:
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_decline_sends_nothing_and_says_so"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_a_client_without_elicitation_sends_nothing_and_says_so"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_a_route_the_policy_does_not_list_is_refused_before_sending"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_without_an_authorizer_every_gated_post_is_refused_before_sending"
        status: pass
    human_judgment: false
  - id: D3
    description: "The human wait holds no per-incarnation lock (SAFE-03); allow-class routes open no window but carry a server-minted permit; floats and the empty argument object survive because the hash covers the sent text"
    requirement: SAFE-03
    verification:
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_delete_is_confirmed_once_sent_once_and_the_revit_verifier_accepts_the_bytes_once"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_a_float_vector_keeps_the_permit_valid_because_the_hash_covers_the_sent_text"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_an_allow_class_route_opens_no_window_and_still_carries_a_permit"
        status: pass
    human_judgment: false
  - id: D4
    description: "Permit format and verifier (hand-written HMAC equals hmac.new on 1/64/131-byte keys, wire split, single use) and the base policy covering 59 tools and 56 routes"
    requirement: SAFE-11
    verification:
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_the_hand_written_hmac_matches_the_standard_one_and_the_minted_permit_verifies"
        status: pass
      - kind: unit
        ref: "tests/unit/test_phase7_tracer.py#test_the_base_policy_covers_every_manifest_tool_and_the_delete_decision_is_confirm"
        status: pass
    human_judgment: false
  - id: D5
    description: "Payload ships policy.py, approval.py, permit.py and policy.base.toml; cold start stays under 2.0 s"
    verification:
      - kind: unit
        ref: "tests/unit/test_payload_ships_root_modules.py#test_payload_copies_every_root_module_reachable_from_main"
        status: pass
      - kind: unit
        ref: "tests/unit/test_payload_ships_root_modules.py#test_payload_copies_the_base_policy_file"
        status: pass
      - kind: other
        ref: "uv run python tests/test_init_latency.py -> INIT_LATENCY_S=0.997"
        status: pass
    human_judgment: false
  - id: D6
    description: "The Revit verifier under a real IronPython 3.4 engine inside Revit (hand-written HMAC, raw_decode, hashlib) and the window wording in a real Hermes client"
    verification: []
    human_judgment: true
    rationale: "Only the D-20 live bench (plan 07-14) can run revit_mcp/permits.py in pyRevit's engine and show the Hermes window; this plan proves the dialect statically (test_conventions) and the logic under CPython"

duration: 13min
completed: 2026-10-25
status: complete
---

# Phase 7 Plan 02: Confirm-class tracer through policy, window, permit and Revit verifier Summary

**delete_elements now travels tool -> TOML policy -> one Russian confirmation window (MCP elicitation, action-only consent) -> one-time HMAC permit over the exact wire text -> envelope-first POST that the IronPython-dialect verifier accepts exactly once; every refusal path sends nothing and the payload ships the slice.**

## Performance

- **Duration:** about 13 min
- **Started:** 2026-10-25T18:05Z (first file written 18:06:48Z)
- **Completed:** 2026-10-25T18:18Z
- **Tasks:** 2
- **Files:** 6 created, 6 modified (two commits)

## Accomplishments

- `policy.base.toml` classifies the 59 manifest tools (`routes = [...]`, `local = true` for `discover_revit_targets` and `start_revit`) and the 56 routes: 49 allow (27 gated + 7 open reads + 15 GET), 4 confirm (`delete_elements`, `transform_elements`, `load_family`, `execute_code`), 3 check (`set_parameter`, `modify_element` -> `parameter_write`; `edit_family` -> `family_edit`); 32 document-bound; settings 300 s window, 60 s permit TTL, the company FOP path as a TOML literal string (never read here).
- `bridge.revit_post` for every POST outside the seven open reads: arguments validated, target resolved once, `await _authorize(...)` before `_dispatch`, refusals returned as not-sent text, a grant adds the permit to the envelope beside the secret and call_id and sends `permit.wire_text(...)` verbatim (`_send` posts a str unchanged). `_authorize is None` refuses; an authorizer exception refuses with fixed text; a non-Grant/Refusal return refuses.
- `revit_mcp/permits.py`: RFC 2104 HMAC over hashlib, `split_wire` with `raw_decode`, verdict chain in the planned order, duplicate-`_mcp` differential closed against `trust.split_envelope`, single-use registry (cap 4096, purge at exp + 5 s). `revit_mcp.security.gate_or_response` is untouched and strips the same body (tracer row), so the payload is harmless to the extension deployed today.
- Tracer: 15 rows (confirm path, decline, no capability, approved=true claim, allow with permit, float vector, empty `{}` args, unknown route, no authorizer, no secret, raising authorizer, open read, HMAC parity, `args_text` refusals, base policy coverage).

## Task Commits

1. **Task 1: tracer (policy, approval, permit, verifier, bridge seam, tests)** - `f0a568e` (feat)
2. **Task 2: payload copy lines, transitive payload test, stdout guard scope** - `668850d` (feat)

**Plan metadata:** the commit that adds this SUMMARY (docs). STATE.md and ROADMAP.md were updated through the gsd-tools verbs and deliberately not committed (they carry unrelated staged edits, per the dispatch instruction).

## Files Created/Modified

- `policy.py` - Policy/Rule model, TOML parse, minimal validation, `policy_hash`, `load_base`, lazy `current()`
- `policy.base.toml` - the base policy (generated once from the AST route inventory, then hand-annotated)
- `approval.py` - `AuthorizationRequest`/`Grant`/`Refusal`, `authorize`, `ask_human`, `build_message`, `refusal_text`, `operation_code`
- `permit.py` - `args_text`, `args_hash`, `derive_key`, `mac_message`, `mint`, `wire_text`
- `revit_mcp/permits.py` - IronPython-dialect verifier and registry
- `bridge.py` - `_authorize` seam, `PERMIT_KEY`, `_send` accepting pre-serialized text, docstrings
- `tests/unit/conftest.py` - autouse `_allow_all_authorizer`
- `tests/unit/test_phase7_tracer.py` - tracer rows
- `tests/unit/audit_support.py`, `tests/unit/test_audit_stdio.py` - see deviation 1
- `deploy/build-payload.cmd`, `tests/unit/test_payload_ships_root_modules.py` - payload copy lines and tests

## Decisions Made

See `key-decisions`. Additions beyond the plan text: `build_message` takes an optional `timeout_s` keyword (the window length in the first sentence needs the policy's timeout); `refusal_text` has a `no_secret` branch that says to run Update RevitMCP and restart the session; argument lines beyond ten end with "ещё аргументов: N".

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing stdio session test called a confirm-class tool**
- **Found during:** Task 1 full-suite run
- **Issue:** `tests/unit/test_audit_stdio.py::test_session_stdout_stays_pure_json_rpc_while_the_audit_file_fills` runs `main.py` in a subprocess (the conftest authorizer cannot reach it) and called `execute_revit_code`, which is confirm-class; a bare stdio client declares no elicitation, so the call is now correctly refused as UNAVAILABLE and no `Audit: call_id` line exists.
- **Fix:** the session now calls `create_level` (allow-class, goes through the real authorizer with a real permit) and `FakeRevitServer` in `audit_support.py` answers `/create_level/` like `/execute_code/`. The test's purpose (stdout stays pure JSON-RPC, audit file fills, secret never leaks) is unchanged and it now also exercises the real authorizer in a subprocess.
- **Files modified:** `tests/unit/test_audit_stdio.py`, `tests/unit/audit_support.py` (the plan's Task 2 named the first file for the scan list only)
- **Commit:** `f0a568e`

**2. [Rule 3 - Process] RED not observed before GREEN**
- **Issue:** the plan asks for RED first. I wrote the modules and the bridge seam before the tracer test file, so the rows were never seen failing against an absent implementation; they passed on the first run (15 passed). I checked the rows are not vacuous by printing the real window text and wire body of the delete path and the decline text.
- **Impact:** weaker TDD evidence only; behavior is covered by the rows.

**3. [Rule 3 - Blocking] Full suite not green between the two task commits**
- **Issue:** after Task 1 the full run had 9 failures: `test_payload_copies_every_root_module_reachable_from_main` (expected, fixed by Task 2) and 8 `test_secret_pipeline` publish tests that refuse an untracked `revit_mcp/permits.py` (cleared by `git add` before the Task 1 commit, since `deploy/make_manifest.py` reads `git ls-files`). The Task 1 commit itself was not re-run in full; the first full green run is after Task 2.
- **Verification:** after Task 2, `uv run pytest tests/unit -q` = 6398 passed, 3 skipped.

**4. [Rule 3 - Minor] `policy.current()` does not cache errors**
- **Issue:** the plan text says it re-raises on every call while the base is invalid; caching a transient read error forever would also do that but never recover. It re-reads on the next call instead (same observable behavior: a PolicyError per call while invalid).

**Total deviations:** 4 (1 bug-in-existing-test, 3 process or minor). **Impact:** none on the delivered behavior; deviation 3 is a history-hygiene note.

## Issues Encountered

- A bash heredoc halves backslashes in this environment: the first policy generator wrote a corrupted `shared_parameters_file` (rejected by `tomllib`), and a test regex was halved once. Both were fixed with the Edit tool and verified (`tomllib` round trip prints the exact UNC path with Cyrillic).
- Not done, by plan: `scripts/conventions.py` `LOCAL_MODULES` and the helper tuples in `tests/unit/test_registration.py` do not yet list `permits` (07-07's area; `test_conventions.py -k permits` passes: the new module satisfies the dialect checks).

## Verification

- `uv run pytest tests/unit/test_phase7_tracer.py -q`: 15 passed
- `uv run pytest tests/unit/test_bridge_serialization.py tests/unit/test_target_locks.py tests/unit/test_audit_tracer.py tests/unit/test_audit_correlation.py tests/unit/test_conventions.py tests/unit/test_phase2_inventory.py -q`: 1173 passed, 3 skipped
- `uv run pytest tests/unit/test_payload_ships_root_modules.py tests/unit/test_audit_stdio.py -q`: 10 passed
- `uv run pytest tests/unit -q`: **6398 passed, 3 skipped**, 0 failed
- `uv run python tests/test_init_latency.py`: **INIT_LATENCY_S=0.997** (< 2.0)
- `python -c "import tomllib ..."` prints `59 56 confirm allow`; `bridge.py` has the top-level `_authorize` assignment; a fresh interpreter `import bridge` leaves `mcp.server.fastmcp` unimported (`False`)
- Environment: ran against the scratch venv with the approved mcp 1.30.0 lock (the repo `.venv` is still the half-upgraded one from 07-01; untouched)

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-07-04..T-07-10). T-07-09 (an agent that can read the shared secret can mint permits) is accepted and written into the verifier docstring.

## Next Phase Readiness

Ready for 07-03 and the Wave 3+ plans. 07-04 completes policy validation and operator overlays (note `edit_family` `confirm_when = []`), 07-06 replaces the inline `check` branch of `approval.authorize` with `policy.decide`, and 07-07 switches the conftest authorizer to mint real permits when the gate starts to require them. `revit_mcp/permits.py` is untested inside a real IronPython engine until the D-20 bench.

## Self-Check: PASSED

- FOUND: policy.py, policy.base.toml, approval.py, permit.py, revit_mcp/permits.py, tests/unit/test_phase7_tracer.py
- FOUND: commits f0a568e, 668850d (no graphify-out or .planning paths in either)
- `git rev-list --count b55bc54..HEAD` = 2 (measured before this SUMMARY commit)
