---
phase: 04-honest-outcomes-on-every-mutating-route
plan: 10
subsystem: testing
tags: [live-gate, one-shot-instrument, classify_outcomes, posts_sent, outcome-schema, bridge, format_response]
status: complete

requires:
  - phase: 04-honest-outcomes-on-every-mutating-route
    provides: "outcome contract and reply shapes (04-01 tag_elements, 04-04 modify_element / export_ifc / delete_elements)"
  - phase: 02-document-identity-and-mutation-guard
    provides: "tests/test_phase2_live_identity.py idiom (older-tier script, lazy bridge import, _outside_repo, one-shot discipline)"
provides:
  - "tests/test_phase4_live_outcomes.py: standalone one-shot live gate runner (template / run / classify), pure classify_outcomes, evidence_template, ALLOWED_ENDPOINTS, BAD_ID; tokens PHASE4_OUTCOMES_OK / PHASE4_OUTCOMES_STOP; output line POSTS_SENT=<n>"
  - "tests/unit/test_phase4_live_outcomes.py: 113 offline tests of the classifier, the refusal paths, the preflight, the write order, posts_sent accounting and the endpoint allow-list"
affects: [04-11]

plan_head_before: 0b0f18d0e885ad31faf3cc1abe473d1bba9eccad
actuals:
  tokens: 17000   # chars/4 over the +/- lines of the realized diff (68023 chars); the plan estimated 55000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Live one-shot instrument: refuse before any request, read-only preflight, writes counted before each revit_post, record written in a finally so a raising POST or an interrupt still leaves evidence"
    - "Reply recorded twice per step: raw (plain JSON copy of the dict or Error: string the bridge returned) and rendered (format_response on the ORIGINAL tagged reply, so provenance lines are what the model reads)"

key-files:
  created:
    - tests/test_phase4_live_outcomes.py
    - tests/unit/test_phase4_live_outcomes.py
  modified: []

key-decisions:
  - "A preflight stop sends no POST and records posts_sent 0; the run may be repeated with a fresh --out. Any run that handed a POST to the bridge records posts_sent >= 1 and prints that the one-shot gate is consumed, whatever the verdict. A POST that raised counts as sent."
  - "A failing reply does not stop the run (each family's evidence is wanted once); only a raising POST stops it. Step 5 is skipped, and classifies as stop, when step 2 returned no new tag ids."
  - "Step 5 deletes only the integer tag ids step 2 reported as created, dropping the wall id, the tagged element id, BAD_ID, duplicates, bools and non-integers, so the run can never delete the host it tagged."
  - "The record file is created with exclusive mode ('x'), so a record is never overwritten even in a race; it is written in a finally block and, if the write fails, printed to stdout."
  - "The script never names the save route or the arbitrary-code route anywhere, docstring included: a test scans every string constant, and _require_allowed also refuses any endpoint outside the seven allowed ones at call time."

patterns-established:
  - "Fake bridge injected through the script's _bridge seam (listener_snapshot sync, revit_get / revit_post async, REVIT_PORT attribute), with an ExplodingBridge for refusal tests that fails on any attribute access"

requirements-completed: [TRUTH-01, TRUTH-02, TRUTH-03, TRUTH-04]

coverage:
  - id: D1
    description: "classify_outcomes returns ok only for a complete, consistent record (preflight, s1 committed, s2 partial with the failing id and the PARTIAL SUCCESS text, s3 an Error: 422 failed reply, s4 committed with the file on disk, s5 committed delete); every perturbation is a stop naming its field; it never raises"
    requirement: TRUTH-01
    verification:
      - kind: unit
        ref: "tests/unit/test_phase4_live_outcomes.py -k 'perturbation or canned or never_raises or posts_sent_is_none or internal_error'"
        status: pass
    human_judgment: false
  - id: D2
    description: "run refuses before any request (existing or in-repo record, in-repo or existing export, missing directories, unusable ids) and the read-only preflight sends no POST; a preflight stop reports POSTS_SENT=0 and is repeatable with a fresh --out"
    requirement: TRUTH-03
    verification:
      - kind: unit
        ref: "tests/unit/test_phase4_live_outcomes.py -k 'refus or preflight or rerun'"
        status: pass
    human_judgment: false
  - id: D3
    description: "The five writes go once each in D-11 order with step 5 using step 2's tag ids; posts_sent counts a raising POST and declares the gate consumed; only the seven allowed routes are named and the secret key never reaches the record"
    requirement: TRUTH-04
    verification:
      - kind: unit
        ref: "tests/unit/test_phase4_live_outcomes.py -k 'order or posts_sent or allowed or secret'"
        status: pass
    human_judgment: false
  - id: D4
    description: "The instrument works against a real Revit (real bridge handshake, real replies, real IFC export)"
    requirement: TRUTH-02
    verification: []
    human_judgment: true
    rationale: "Deliberately not run in this plan; plan 04-11 runs it once on a freshly restarted Revit and this plan only proves the logic offline"

duration: "9 min measured (clock started after reading the plan, prior summaries and the phase 2 analog)"
completed: 2026-10-23
---

# Phase 4 Plan 10: Live outcome gate instrument Summary

**A standalone one-shot script that runs the D-11 live set (modify_element, tag_elements partial, tag_elements all-failed 422, export_ifc, delete_elements) through the production bridge, records each raw reply beside the text the model would read, and classifies the record into `PHASE4_OUTCOMES_OK` or `PHASE4_OUTCOMES_STOP` with an exact `POSTS_SENT=<n>` count, so the one live run in plan 04-11 cannot be wasted on a script bug.**

## Performance

- **Duration:** about 9 min measured (see frontmatter); reading came before the clock
- **Completed:** 2026-10-23
- **Tasks:** 2 of 2
- **Files:** 2 created (`tests/test_phase4_live_outcomes.py`, `tests/unit/test_phase4_live_outcomes.py`), none modified

## Accomplishments

- **Pure classifier (Task 1):** `classify_outcomes(record)` returns `{"verdict", "reasons", "posts_sent"}`, never raises and reports the record's `posts_sent` (an int, else `None`) without letting it change the verdict. `ok` needs: preflight with one listener, one document, a writable parameter and an answering status; s1 `Committed`, `success`, `succeeded == [parameter]`; s2 `partial` with `succeeded == [tag_id]`, `failed == [{item: 999999999, reason: "Element not found"}]` and rendered text containing `=== PARTIAL SUCCESS ===` and the bad id; s3 an `Error: 422` string whose body is `failed`; s4 committed with `succeeded == [ifc_path]` and the file on disk; s5 a committed delete of exactly the ids it asked for. 34 named perturbations each stop with the field in the reason, and a node-by-node junk replacement sweep (over 40 variants for each of 9 junk values) never raises.
- **Runner (Task 2):** refusals before any request, then a read-only preflight (GET `/status/`, `bridge.listener_snapshot` shows exactly one owner, GET `/documents/` lists one document, GET `/element_properties/` of the wall shows a writable text parameter, and of the tag target answers), then the five writes once each. Each step records `{endpoint, body, raw, rendered}`, s4 adds `file_exists`, and the record is written exclusively in a `finally`.
- **Output contract:** the token line, then `POSTS_SENT=<n>`, then one guidance line (`No write step was sent: nothing was written to the model ...fresh --out.` for 0; `The one-shot gate is consumed: do not run this again.` for 1 or more), the stop reason and each classifier reason.
- **Operator procedure** is the module docstring (restart Revit with no model, never pyRevit Reload, one listener, one scratch non-workshared model through open_model, confirm the view exists by name, never save, rerun only after POSTS_SENT=0 with a fresh `--out`).
- Suite: 5061 passed before Task 2, now **5101 passed, 3 skipped**; `tests/unit/tool_manifest.txt` untouched; the live script was never run against Revit.

## Task Commits

1. **Task 1: pure classifier, evidence template, allow-list** - `a4bb62f` (test)
2. **Task 2: one-shot runner, preflight, refusals, template and classify commands** - `eef10a3` (test)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED and GREEN committed together per task, not as separate commits**
- **Found during:** both tasks
- **Issue:** the plan's commit protocol requires `uv run pytest tests/unit` green before every commit, which a standalone RED commit would violate (same resolution as 04-01). RED was observed first in both tasks: a `FileNotFoundError` at collection for Task 1, 25 failures for Task 2.
- **Files modified:** none beyond the plan
- **Commit:** a4bb62f, eef10a3

**2. [Rule 2 - Missing critical functionality] Extra refusals and one extra preflight check**
- **Found during:** Task 2 design
- **Issue:** a record that cannot be written after the five writes loses the only evidence, and a relative or non-`.ifc` path would be read relative to Revit's own working directory.
- **Fix:** `run` also refuses a missing `--out` or `--ifc-path` directory, a relative or non-`.ifc` export path, `--out` equal to `--ifc-path`, a blank parameter, value or view name, an id equal to 999999999, and a port outside 1..65535. The preflight also reads the tag target (`preflight.tag_element_found`, a fifth key in the template's preflight block) and requires the parameter's `storage_type` to be `String`, because step 2 would otherwise be wasted by a bad id and the value sent is text.
- **Files modified:** tests/test_phase4_live_outcomes.py, tests/unit/test_phase4_live_outcomes.py
- **Commit:** eef10a3

**3. [Rule 1 - Bug, test double] Canned export reply named a fixed path**
- **Found during:** Task 2 (first GREEN run)
- **Issue:** the fake bridge replied to `/export_ifc/` with the canned reply's constant path, so the classifier (correctly) judged `succeeded != [ifc_path]` for every real tmp path.
- **Fix:** the fake now echoes the path it was given, as the real route does (`succeeded.append(file_path)`).
- **Files modified:** tests/unit/test_phase4_live_outcomes.py
- **Commit:** eef10a3

**Total deviations:** 3 (1 blocking-process, 1 missing-critical, 1 test-double bug). **Impact:** none on the contract; the added refusals only make the one-shot safer.

## Issues Encountered

- `git commit` prints `failed to delete '.git/worktrees/hot-cirrus': Permission denied` after each commit; both commits landed (verified with `git log`). Harmless, as the orchestrator warned.
- `graphify update .` was not run (instructed not to: it rewrites `graphify-out/`, which holds another session's changes).
- REQUIREMENTS.md was not touched; the orchestrator owns requirement completion at phase end. The `requirements-completed` list above is the plan's `requirements` array copied verbatim.

## Notes for plan 04-11

- Pick the view by name from a read-only listing before the run: an unknown `view_name` is refused by `tag_elements` before its transaction (404), which would spend the gate on step 2 without evidence.
- `run` needs `--port` equal to the bridge's `REVIT_PORT`; the script sets `REVIT_PORT` from `--port` before it first imports the bridge and refuses if the bridge was configured for another port.
- Any `POSTS_SENT` of 1 or more is final: a stop after that point is a finding about the routes, to be read from the record.

## Known Stubs

None.

## Threat Flags

None. The script adds no endpoint, auth path or trust-boundary surface to the product; it only calls the seven routes on its allow-list. T-04-34 (repeated or misdirected writes), T-04-35 (record in the repository), T-04-36 (secret in output: the script never reads the secret and drops any `_mcp` key from recorded bodies) and T-04-37 (save or arbitrary-code route) are mitigated and tested.

## Self-Check: PASSED

- Files exist: `tests/test_phase4_live_outcomes.py`, `tests/unit/test_phase4_live_outcomes.py`, committed.
- Commits found: a4bb62f, eef10a3 (`git log --grep "04-10"`); `commits: 2` measured from the ledger base `0b0f18d`.
- Acceptance criteria re-run: unit file 113 passed; `-k "refus or preflight or order"` 28 passed; `-k "posts_sent or rerun"` 12 passed; `template` prints JSON with `inputs`, `posts_sent`, `preflight`, `steps`; `classify does-not-exist.json` prints `PHASE4_OUTCOMES_STOP` / `POSTS_SENT=unknown`, exit 1, no traceback; a CLI `run` with an in-repo `--out` was refused with exit 2 and created nothing; `pytest --collect-only tests` lists nothing from `tests/test_phase4_live_outcomes.py`; full suite 5101 passed, 3 skipped; no new untracked files beyond the two planned ones.
- Plan verification: template command prints the template JSON; `graphify update .` deliberately not run.
