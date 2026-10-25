---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "04"
subsystem: mutation-safety
tags: [policy, toml, operator-overlay, hot-reload, policy-hash, payload-staging, build-gate]

requires:
  - phase: 07-repository-owned-mutation-safety-and-human-approval
    provides: "plan 07-02: Policy/Rule model, minimal base loader, approval.authorize, permit p field; plan 07-03: pywin32 shim in gate.py and the scratch payload gate"
provides:
  - "policy.py: closed vocabularies, validate_base / validate_operator / merge (whole-file rejection, key-path messages)"
  - "policy.py: PolicyStore with debounced, capped, worker-thread operator reload, last-valid retention, honest operator_state, blocked on an invalid base, status()"
  - "policy.operator_path: REVIT_MCP_POLICY_FILE, else the first line of app\\policy_source (Cyrillic UNC byte-identical)"
  - "approval.py: policy re-read after the human answers; a changed hash refuses with policy_changed and nothing is sent"
  - "deploy: MCP_POLICY_FILE default, policy_tool.py stage/check, build-payload staging, gate.py base-policy check (POLICY= line)"
affects: [07-05, 07-06, 07-08, 07-09, 07-11, 07-12, 07-14]

actuals:
  tokens: 20257        # chars/4 over the realized diff (81029 chars) of the three task commits
  tasks: 3
  commits: 3
plan_head_before: 9cfe1c013995f56b53cf95b45a83622ae1a64b99
commits: 3

tech-stack:
  added: []
  patterns:
    - "policy as data: every key, word, type and number from a closed vocabulary; one defect invalidates the whole file; messages carry the key path only"
    - "operator overlay by route key and settings key; a route relaxed away from check drops the base's check name in the overlay"
    - "last-valid retention: state machine not_configured / absent / pending / accepted / rejected / unreachable with one-reference swap of an immutable Policy"
    - "build staging pattern copied from secret_tool.py: a path-only file (policy_source) staged beside the code, file itself stays on the share"

key-files:
  created: [tests/unit/test_policy_loader.py, tests/unit/test_policy_reload.py, tests/unit/test_policy_tool.py, deploy/policy_tool.py]
  modified: [policy.py, approval.py, deploy/gate.py, deploy/config.cmd, deploy/build-payload.cmd]

key-decisions:
  - "The operator file is read twice DEBOUNCE_S apart inside one worker-thread call under READ_TIMEOUT_S; two different reads mean pending, not applied"
  - "A FileNotFoundError with a WinError other than 2/3 (for example 67, network name not found) is unreachable, not absent: a share that cannot be reached must not silently drop an applied operator policy back to the base"
  - "approval re-reads the policy with force=True after the answer, so a change applied while the human decided is seen without waiting for the 2 s poll"
  - "An operator route overlay that moves a route off decision check also drops the base's check name; otherwise relaxing set_parameter to confirm would be rejected as an invalid pairing"
  - "A policy_source or operator file is size-capped (MAX_OPERATOR_BYTES 262144 for the operator file, 4096 for policy_source); an oversized operator file is rejected"

requirements-completed: [SAFE-09, SAFE-10, SAFE-13]

coverage:
  - id: D1
    description: "The base policy and any operator overlay are validated as data against closed vocabularies; an unknown key, word, type or out-of-range number rejects the whole file, and the operator can set any decision (including allow for delete_elements) but cannot add a route, change method, document_bound or facts, or lift a GET route above allow"
    requirement: SAFE-09
    verification:
      - kind: unit
        ref: "tests/unit/test_policy_loader.py#test_each_base_defect_raises_and_names_the_key_path"
      - kind: unit
        ref: "tests/unit/test_policy_loader.py#test_one_defect_rejects_the_whole_operator_file"
      - kind: unit
        ref: "tests/unit/test_policy_loader.py#test_an_operator_allow_for_delete_merges_and_keeps_the_structure_of_the_base"
    human_judgment: false
  - id: D2
    description: "policy_hash is 12 hex over the LF-normalized base and operator bytes, stable across CRLF/LF, different with and without the operator, and is what the status and the permit p field carry"
    requirement: SAFE-09
    verification:
      - kind: unit
        ref: "tests/unit/test_policy_loader.py#test_the_hash_is_12_hex_stable_across_line_endings_and_changes_with_the_operator"
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_without_a_change_the_accept_is_sent_and_the_permit_carries_the_active_hash"
    human_judgment: false
  - id: D3
    description: "An invalid, partial, empty, oversized, unreadable, torn or absent operator file never weakens or changes the active rules: first-invalid leaves the base, a later invalid keeps the last valid version, only a deleted file falls back to the base, and the state and diagnostic say which"
    requirement: SAFE-10
    verification:
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_an_invalid_file_at_first_use_leaves_the_base_and_names_the_key_path"
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_valid_then_invalid_keeps_the_last_valid_operator_version"
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_two_reads_with_different_bytes_are_not_applied_and_the_state_is_pending"
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_valid_then_deleted_falls_back_to_the_base_and_reports_absent"
    human_judgment: false
  - id: D4
    description: "The operator file is read in a worker thread with a 3 s cap, never at import and never on the event loop: a hanging share returns the last valid policy within 4 s while another coroutine keeps running; 20 concurrent callers during a reload see the old or the new object only"
    requirement: SAFE-10
    verification:
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_a_share_that_hangs_returns_the_last_valid_policy_while_the_loop_keeps_running"
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_twenty_callers_during_a_reload_see_the_old_or_the_new_object_only"
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_importing_policy_reads_nothing_and_creates_no_store"
    human_judgment: false
  - id: D5
    description: "An invalid base blocks: current() raises PolicyError, approval refuses every gated route with policy_invalid and sends nothing, and the status reports blocked true"
    requirement: SAFE-10
    verification:
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_an_invalid_base_refuses_every_gated_route_and_sends_nothing"
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_an_invalid_base_raises_on_every_call_and_the_status_says_blocked"
    human_judgment: false
  - id: D6
    description: "A policy change applied while a confirmation window is open voids the accept: refusal reason policy_changed, text says NOT sent, zero POSTs reach the machine (policy half of SAFE-13)"
    requirement: SAFE-13
    verification:
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_a_policy_change_while_the_window_is_open_voids_the_accept"
    human_judgment: false
  - id: D7
    description: "operator_path resolves env first, then the staged policy_source first line (BOM and CRLF tolerated), byte-identical for a Cyrillic UNC path; policy_tool stage writes that file as UTF-8 without BOM"
    requirement: SAFE-09
    verification:
      - kind: unit
        ref: "tests/unit/test_policy_reload.py#test_operator_path_reads_the_first_line_of_policy_source_byte_identical"
      - kind: unit
        ref: "tests/unit/test_policy_tool.py#test_the_staged_file_is_what_policy_operator_path_reads_back"
    human_judgment: false
  - id: D8
    description: "The build stages the operator path, warns without failing on an absent or rejected operator file, and refuses a payload whose base policy is invalid (POLICY=ok, SCRATCH_GATE_OK on the scratch payload built with pyRevit's CPython)"
    requirement: SAFE-09
    verification:
      - kind: unit
        ref: "tests/unit/test_policy_tool.py#test_build_payload_stages_the_path_then_checks_before_the_gate_and_keeps_lf"
      - kind: unit
        ref: "tests/unit/test_policy_tool.py#test_the_gate_fails_on_a_broken_or_missing_base_policy"
      - kind: other
        ref: "uv run python scripts/scratch_payload_gate.py -> POLICY=ok (base a951ef8099df), SCRATCH_GATE_OK"
        status: pass
    human_judgment: false
  - id: D9
    description: "The operator policy read from a real UNC share under the fleet's embedded CPython, the share ACL being read-only for ordinary users (research assumption A7), and build-payload.cmd run for real"
    verification: []
    human_judgment: true
    rationale: "Only the operator on the real share can verify the ACL, and the deploy scripts are never run here (D-27, plan 07-12 runbook, plan 07-14 live bench); this plan proves the parts under CPython with an injected reader"

duration: 16min
completed: 2026-10-25
status: complete
---

# Phase 7 Plan 04: Two-layer policy (base + operator) with hot reload and build staging Summary

**The policy is now validated strictly as data (closed vocabularies, whole-file rejection, key-path messages), an optional operator TOML on the share overlays it by route and settings key and reloads atomically (debounced double read, worker thread, 3 s cap, last-valid retention, honest status), an invalid base blocks, an approval granted under one policy hash is refused as policy_changed under another, and the payload build stages the operator path and refuses an invalid base policy.**

## Performance

- **Duration:** about 16 min
- **Started:** 2026-10-25T18:29Z (approximate; first command at the pin check)
- **Completed:** 2026-10-25T18:45Z
- **Tasks:** 3
- **Files:** 4 created, 5 modified (three task commits, 1624 insertions)

## Accomplishments

- `validate_base`, `validate_operator`, `merge` and the vocabularies `REASONS`, `CONFIRM_WHEN`, `FACTS`, `SETTINGS_RANGES`, `SETTINGS_TEXT`, `OPERATOR_ROUTE_KEYS`, `STRUCTURAL_ROUTE_KEYS`. `build_policy` now validates through `validate_base`, so the base and the merged document go through one checker. Messages are a fixed phrase plus the key path and never repeat a value (a test with a secret-looking word in `reasons` proves it).
- Operator overlay (D-14, D-15): any decision may be set, including `allow` for `/delete_elements/`; reasons, check and confirm_when are replaced, not appended; routes the base lacks, `method`, `document_bound`, `facts`, `tools`, unknown top-level or settings keys, a GET route above allow and an out-of-range number each reject the whole file. Neither input dict is mutated.
- `PolicyStore` (D-17): the operator file is read twice 200 ms apart in one `asyncio.to_thread` under a 3 s cap; two different reads are `pending`; identical bytes of the applied version change nothing; a valid, stable file replaces the active immutable Policy in one assignment. States `not_configured / absent / pending / accepted / rejected / unreachable`; `status()` always returns the same nine keys and never raises. An invalid base raises `PolicyError` on every `current()` and `status()` reports `blocked`; a repaired base is picked up without a restart.
- `approval.authorize` re-reads the policy (forced) after an accept: `PolicyError` gives `policy_invalid`, a different hash gives `policy_changed`, and the permit is minted with the hash that is active at send time. Refusal text: "NOT CONFIRMED: the approval policy changed while the window was open; ask again."
- Deploy: `MCP_POLICY_FILE` in `config.cmd` (with the read-only ACL requirement written down), `deploy/policy_tool.py stage|check`, two lines in `build-payload.cmd` between the secret staging and the gate, and `gate.py` `_base_policy_status` with `POLICY=` and `POLICY_SOURCE=` lines that fail the build on an invalid base.

## Task Commits

1. **Task 1: closed-vocabulary validation, operator overlay, two-layer hash** - `0c146de` (feat)
2. **Task 2: hot reload, last-valid retention, status, blocked base, policy_changed** - `b555551` (feat)
3. **Task 3: payload staging of the operator path and the base-policy build gate** - `9c62e8f` (feat)

**Plan metadata:** the commit that adds this SUMMARY (docs). STATE.md, ROADMAP.md and REQUIREMENTS.md were updated through the gsd-tools verbs and deliberately not committed (they carry unrelated user edits, per the dispatch instruction).

## Files Created/Modified

- `policy.py` - vocabularies, validators, overlay, `PolicyStore`, `operator_path`, module `current`/`status`/`_reset`
- `approval.py` - policy re-read after the answer, `policy_changed` / `policy_invalid` refusals and text
- `tests/unit/test_policy_loader.py` (50 rows), `tests/unit/test_policy_reload.py` (28 rows), `tests/unit/test_policy_tool.py` (16 rows)
- `deploy/policy_tool.py` - stage and check subcommands (never prints file content, check always exits 0)
- `deploy/gate.py`, `deploy/config.cmd`, `deploy/build-payload.cmd` - see Accomplishments

## Decisions Made

See `key-decisions`. Not implemented here by plan: rendering `policy.status()` in `get_revit_status`, the audit fields and the `revit_get.policy_status` seam (later plans); the runbook text for the share ACL (07-12).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] A missing share name read as a deleted file**
- **Found during:** Task 2 design
- **Issue:** on Windows, `OSError(2, ..., winerror=67)` ("network name not found") is a `FileNotFoundError`. The plan maps `FileNotFoundError` to absent, which falls back to the base: an unreachable file server would silently drop an applied operator policy.
- **Fix:** `FileNotFoundError` is absent only when `winerror` is None, 2 or 3; anything else is `unreachable` and keeps the active policy. Same rule in `policy_tool check`.
- **Files modified:** `policy.py`, `deploy/policy_tool.py`; test `test_a_missing_share_name_is_unreachable_not_absent` (Windows only)
- **Commit:** `b555551`, `9c62e8f`

**2. [Rule 2 - Missing critical] Size caps**
- **Issue:** the plan sets no limit on the operator file or on `policy_source`; a huge file on the share would be read into memory every poll.
- **Fix:** `MAX_OPERATOR_BYTES = 262144` (reader returns at most one byte more; longer is `rejected`), `policy_source` read capped at 4096 bytes. Test `test_an_oversized_operator_file_is_rejected`.
- **Commit:** `b555551`

**3. [Plan wording] Forced policy re-read after the human answers**
- **Issue:** the plan says `latest = await policy.current()`. A non-forced call returns the cached policy for up to 2 s, so a change applied seconds before the click could be missed.
- **Fix:** `policy.current(force=True)`; the test also advances the injected clock, so both readings pass. Cost: one extra debounced read of the share per accepted confirmation.
- **Commit:** `b555551`

**4. [Plan gap] Relaxing a check route**
- **Issue:** merging an operator `decision = "confirm"` onto `/set_parameter/` kept the base `check = "parameter_write"`, which `validate_base` rejects as an invalid pairing, so the operator could not relax a check route (D-15).
- **Fix:** the overlay drops `check` when the merged decision is not `check` and the overlay did not name a check itself. Test `test_an_operator_may_relax_a_check_route_to_confirm_or_allow`.
- **Commit:** `0c146de`

**5. [Rule 3 - Blocking] Scratch gate default destination was locked**
- **Issue:** `scripts/scratch_payload_gate.py` failed with `PermissionError` removing the default `%TEMP%\revitmcp-phase7-scratch-payload` left by 07-03 (something still holds a handle inside it). No process was touched.
- **Fix:** ran it with `--dest %TEMP%\revitmcp-phase7-scratch-payload-0704` (outside the repository, not a share): `POLICY=ok (base a951ef8099df)`, `POLICY_SOURCE=absent` (the scratch build does not run policy_tool), `MANIFEST=ok (59 tools)`, `SCRATCH_GATE_OK`.

**6. [Process] TDD evidence**
- Task 1: RED observed first (46 failed, 4 passed against the old module), then GREEN.
- Task 2: `test_policy_reload.py` was written before the implementation but I did not run it red. As a substitute I mutation-checked it: disabling the hash comparison in `approval.py` and the two-read comparison in `policy.py` made `test_a_policy_change_while_the_window_is_open_voids_the_accept` and `test_two_reads_with_different_bytes_..._pending` fail (2 failed, 26 passed); both files were restored byte for byte.
- Task 3: the implementation was written before its tests; the tests passed on the first run (16 passed). Weaker TDD evidence only.
- The full suite was green before each commit (6463, 6491 and 6507 passed, 3 skipped).

**7. [Process] A bash heredoc halved backslashes once more**
- A first attempt to edit `config.cmd` / `build-payload.cmd` from a heredoc script failed its own anchor assertion before writing either file (`gate.py` was already written and verified); both cmd files were edited with the Edit tool and checked for LF and the exact acceptance lines.

**Total deviations:** 7 (3 Rule 2 additions, 1 wording hardening, 1 plan gap, 1 blocking workaround, 2 process notes). **Impact:** none on scope; items 1-4 only narrow what the operator layer can do wrongly.

## Issues Encountered

- `git add` / `git commit` print "LF will be replaced by CRLF" warnings (core.autocrlf on this machine); the working-copy files are LF, as the repository's cmd tests require.
- Not verified here, by plan: research assumption A7 (the share ACL is read-only for ordinary users) is an operator deployment requirement, recorded in `config.cmd`; a real UNC read and a real `build-payload.cmd` run belong to the human-run live gates.

## Verification

- `uv run pytest tests/unit/test_policy_loader.py -q`: 50 passed (acceptance: at least 20)
- `uv run pytest tests/unit/test_policy_reload.py -q`: 28 passed (acceptance: at least 13)
- `uv run pytest tests/unit/test_policy_tool.py -q`: 16 passed (acceptance: at least 6)
- `uv run pytest tests/unit -q`: **6507 passed, 3 skipped**, 0 failed (baseline before the plan: 6413 passed, 3 skipped)
- `uv run python -c "import policy;p=policy.load_base();print(...)"`: `base 12 confirm`
- AST check of `policy.py` prints all eight names (`PolicyStore, _reset, current, merge, operator_path, status, validate_base, validate_operator`)
- `uv run python tests/test_init_latency.py`: `INIT_LATENCY_S=0.984` (below 2.0)
- `grep -F 'set "MCP_POLICY_FILE=%MCP_SHARE_ROOT%' deploy/config.cmd`: one line ending in `_build\operator_policy.toml"`; `grep -c policy_tool.py deploy/build-payload.cmd`: 2
- `uv run python scripts/scratch_payload_gate.py --dest <temp>`: `POLICY=ok (base a951ef8099df)` and `SCRATCH_GATE_OK`
- Environment: scratch venv with the approved mcp 1.30.0 lock (the repo `.venv` untouched)

## Known Stubs

None.

## Threat Flags

None. The only new trust boundary (operator file on the share to every server) is T-07-14..T-07-18 of this plan's threat model; mitigations T-07-15 (whole-file validation, debounce, last-valid retention), T-07-16 (worker thread, 3 s cap), T-07-17 (data only, tomllib) and T-07-18 (hash re-read after the answer) are implemented and covered by the rows above. T-07-14 stays a transferred operator requirement.

## Next Phase Readiness

Ready for 07-05. Later plans can call `await policy.status()` for the status line (`source`, `hash`, `operator_state`, `diagnostic`, `blocked`) and rely on the `policy_changed` / `policy_invalid` reason words in audit fields.

## Self-Check: PASSED

All nine created or modified source files exist; commits `0c146de`, `b555551` and `9c62e8f` are in the log; `git rev-list --count 9cfe1c0..HEAD` was 3 before this summary; no tracked file was deleted by the task commits.
