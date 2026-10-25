---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "05"
subsystem: mutation-safety
tags: [hmac-permit, parity, golden-vector, exactly-once, refusal-body, ironpython-verifier]

requires:
  - phase: 07-repository-owned-mutation-safety-and-human-approval
    provides: "plan 07-02: permit.py minter and revit_mcp/permits.py tracer verifier"
provides:
  - "tests/unit/test_permit_protocol.py: HMAC parity (RFC 4231 TC1/TC2/TC6, edge sizes), pinned GOLDEN_MAC literal, every verdict by name, edge wire forms, refusal body (108 rows)"
  - "tests/unit/test_permit_concurrency.py: exactly-once consumption under 32 threads, purge, cap (9 rows)"
  - "revit_mcp.permits.failure(verdict) -> (body, 403), FAILURE_STATUS, fixed mixed-rollout hint texts, status_info()"
affects: [07-07, 07-08, 07-14]

actuals:
  tokens: 6833         # chars/4 over the realized non-.planning diff (27333 chars) of the two commits
  tasks: 2
  commits: 2
plan_head_before: a07d33ecebfb57ab0277ff7a6a51afa6bfc175f3
commits: 2

tech-stack:
  added: []
  patterns:
    - "refusal builder never reports a pass: an unknown verdict (including ok) is reported as malformed"
    - "unparseable body -> no trustworthy envelope -> missing (never ok), burning nothing"

key-files:
  created: [tests/unit/test_permit_protocol.py, tests/unit/test_permit_concurrency.py]
  modified: [revit_mcp/permits.py]

key-decisions:
  - "failure() maps any verdict that is not a known refusal word (None, int, empty, 'ok') to malformed, so the 403 body can never read like acceptance"
  - "A body that is not valid JSON (trailing garbage, missing comma after the envelope) answers missing, not malformed: trust.split_envelope finds no envelope, which is the safe, already-existing behavior"

requirements-completed: [SAFE-11, SAFE-12, SAFE-16]

coverage:
  - id: D1
    description: "The IronPython-dialect HMAC and derived key equal CPython's (RFC 4231 TC1/TC2/TC6 with the 131-byte key, empty message/key, block-size edges) and a golden MAC pinned as a literal is reproduced by both the minter and the verifier"
    requirement: SAFE-11
    verification:
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_hand_rolled_hmac_matches_rfc_4231_and_the_standard_library"
        status: pass
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_the_minter_reproduces_the_pinned_golden_mac"
        status: pass
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_the_verifier_recomputes_the_same_golden_mac"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every refusal verdict is returned by name without raising: args/route/session mismatch, expired and ttl_too_long at the SKEW and MAX_TTL boundaries, bad_signature for MAC flips, wrong secret and edited fields, unsupported_version, malformed shapes and wire forms, missing, not_configured; failed checks never burn the nonce"
    requirement: SAFE-12
    verification:
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_one_changed_character_in_the_arguments_is_args_mismatch"
        status: pass
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_a_permit_of_the_wrong_shape_is_malformed"
        status: pass
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_a_mismatch_does_not_burn_the_permit"
        status: pass
    human_judgment: false
  - id: D3
    description: "Edge forms verify: empty argument object, Cyrillic (escaped to ASCII), floats 0.1 / 1e16 / -2.5, expiry inside the SKEW window"
    requirement: SAFE-11
    verification:
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_edge_forms_of_the_arguments_verify"
        status: pass
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_a_permit_inside_the_skew_window_is_still_accepted"
        status: pass
    human_judgment: false
  - id: D4
    description: "One permit is consumed exactly once under 32 concurrent callers (1 ok, 31 replayed); 32 distinct permits all pass; failed checks record nothing; spent entries are purged; the registry is capped at REGISTRY_CAP and answers registry_full"
    requirement: SAFE-16
    verification:
      - kind: unit
        ref: "tests/unit/test_permit_concurrency.py#test_the_same_permit_on_32_threads_is_consumed_exactly_once"
        status: pass
      - kind: unit
        ref: "tests/unit/test_permit_concurrency.py#test_a_race_at_the_cap_admits_exactly_the_cap"
        status: pass
      - kind: unit
        ref: "tests/unit/test_permit_concurrency.py#test_a_full_registry_answers_registry_full_until_entries_expire"
        status: pass
    human_judgment: false
  - id: D5
    description: "failure(verdict) gives HTTP 403 and {error, permit, hint}; missing carries the Russian and English update-and-restart sentences; every error says nothing was changed; status_info() advertises protocol 1"
    requirement: SAFE-12
    verification:
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_a_missing_permit_hint_names_the_update_in_both_languages"
        status: pass
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_every_refusal_has_the_same_closed_body_and_says_nothing_was_changed"
        status: pass
      - kind: unit
        ref: "tests/unit/test_permit_protocol.py#test_the_status_advertisement_names_the_protocol"
        status: pass
    human_judgment: false
  - id: D6
    description: "The hand-rolled HMAC and raw_decode verifier inside Revit's own IronPython 3.4 engine"
    verification: []
    human_judgment: true
    rationale: "Only the D-20 live bench (plan 07-14) can run revit_mcp/permits.py in pyRevit's engine; this plan proves the logic under CPython and the dialect statically (test_conventions)"

duration: 5min
completed: 2026-10-25
status: complete
---

# Phase 7 Plan 05: Permit protocol hardening Summary

**The one-time permit is now proven equal on both runtimes (hand-rolled HMAC vs hmac.new on RFC 4231 vectors, a pinned golden MAC literal), refuses every tampering, replay, expiry, wrong-process and malformed form by name, consumes exactly once under 32 racing threads, and the verifier has the 403 refusal body with the mixed-rollout hint ready for the gate.**

## Performance

- **Duration:** about 5 min
- **Started:** 2026-10-25T18:47:31Z
- **Completed:** 2026-10-25T18:53Z
- **Tasks:** 2
- **Files:** 2 created, 1 modified (two commits)

## Accomplishments

- `tests/unit/test_permit_protocol.py` (108 rows): RFC 4231 TC1/TC2/TC6 plus empty message/key and block-size edges against both the literal RFC digests and `hmac.new`; `derive_key` equality (including Cyrillic and bytes secrets); `GOLDEN_MAC` as a literal reproduced by `permit.mint` and recomputed by the verifier; one row per verdict and boundary (SKEW, MAX_TTL); edited-field rows prove the signature is checked before route/session; shape and wire-form negatives; edge forms; no-leak and refusal-body rows.
- `revit_mcp/permits.py`: `FAILURE_STATUS = 403`, fixed `_HINTS` (missing: Russian plus English update-and-restart sentence; not_configured: reinstall and restart Revit; everything else: ask again for a new confirmation window), `failure(verdict)` (unknown verdict reported as malformed, so a refusal can never read as a pass), `status_info()`.
- `tests/unit/test_permit_concurrency.py` (9 rows): barrier-released 32-thread race gives exactly one `ok` and 31 `replayed` (repeated 10 times), 32 distinct permits all `ok`, failed checks leave the registry empty, purge past e + SKEW, cap at `REGISTRY_CAP` (also under a race: exactly the cap admitted).

## Task Commits

1. **Task 1: parity, golden vector, verdicts, edge forms, refusal body** - `a1fd15a` (feat)
2. **Task 2: exactly-once under concurrency, purge and cap** - `e106c19` (test)

**Plan metadata:** the commit that adds this SUMMARY (docs). STATE.md and ROADMAP.md were updated through the gsd-tools verbs and deliberately not committed (they carry unrelated staged edits, per the dispatch instruction).

## Files Created/Modified

- `tests/unit/test_permit_protocol.py` - protocol parity, golden vector, verdicts, edge forms, failure body
- `tests/unit/test_permit_concurrency.py` - exactly-once, purge, cap
- `revit_mcp/permits.py` - `FAILURE_STATUS`, `_HINTS`, `failure()`, `status_info()`
- `permit.py` - unchanged (the tracer API already satisfied every row; nothing added that weakens a check)

## Decisions Made

See `key-decisions`. No module attribute or function that skips verification, accepts without consuming or clears the registry was added (prohibition SAFE-12); tests isolate the registry only by `monkeypatch.setattr(permits, "_CONSUMED", {})` and `REGISTRY_CAP`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test expectation] Unparseable bodies answer `missing`, not `malformed`**
- **Found during:** Task 1 RED run
- **Issue:** two rows I wrote expected `malformed` (trailing garbage after the argument object; a space instead of a comma after the envelope). Such a body is not valid JSON, so `trust.split_envelope` returns no envelope and the verdict is `missing`. The behavior is safe (refused, nonce untouched, the gate refuses on `missing` anyway); my expectation was wrong, not the verifier.
- **Fix:** the rows now assert `missing`, assert the permit is not burnt afterwards, and assert `split_wire` itself returns `None` for the missing-comma shape.
- **Files modified:** `tests/unit/test_permit_protocol.py`
- **Commit:** `a1fd15a`

**2. [Rule 3 - Process] RED and GREEN share one commit for Task 1; Task 2 has no GREEN**
- RED was observed (24 failed, 84 passed: `failure`/`status_info` absent, plus the two rows above) but committing RED alone would have left the suite red, which the commit protocol forbids; protocol tests and the implementation are one `feat` commit. The tracer from 07-02 already satisfied every concurrency row (the purge, membership test and insert are already under one `with _LOCK:` block), so Task 2 is a `test` commit only, as the plan allows ("GREEN only if a row fails").

**Total deviations:** 2 (one wrong test expectation, one process note). **Impact:** none on delivered behavior.

## Issues Encountered

None. The 07-02 tracer verifier needed no change beyond the planned additions.

## Verification

- `uv run pytest tests/unit/test_permit_protocol.py -q`: 108 passed
- `uv run pytest tests/unit/test_permit_concurrency.py -q`: 9 passed
- `uv run pytest tests/unit/test_permit_protocol.py tests/unit/test_permit_concurrency.py tests/unit/test_conventions.py -q`: 540 passed, 3 skipped
- `uv run pytest tests/unit -q`: **6624 passed, 3 skipped**, 0 failed (baseline 6507 + 117 new rows)
- `grep -c 'GOLDEN_MAC = "' tests/unit/test_permit_protocol.py` = 1 (a literal)
- Environment: scratch venv with the approved mcp 1.30.0 lock (repo `.venv` untouched)

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-07-19..T-07-23): T-07-19/20 by the binding and replay rows, T-07-21 by `trust._same_digest` (unchanged, covered by the bad-signature rows), T-07-22 by purge and cap rows, T-07-23 by fixed-text refusal rows.

## Next Phase Readiness

Ready for 07-07 (the gate can call `permits.failure(verdict)` and `permits.status_info()`) and 07-08 (status advertisement). HMAC parity inside Revit's own IronPython engine is still proven only by the D-20 live bench (07-14).

## Self-Check: PASSED

- FOUND: tests/unit/test_permit_protocol.py, tests/unit/test_permit_concurrency.py, revit_mcp/permits.py (`def failure(`)
- FOUND: commits a1fd15a, e106c19 (no graphify-out or .planning paths in either)
- `git rev-list --count a07d33e..HEAD` = 2 (measured before this SUMMARY commit)
