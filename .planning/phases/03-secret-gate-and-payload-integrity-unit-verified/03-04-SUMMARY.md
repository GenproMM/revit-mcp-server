---
phase: 03-secret-gate-and-payload-integrity-unit-verified
plan: 04
subsystem: payload-integrity
tags: [sha256, manifest, git-ls-files, ironpython3, trust, http-423]

requires:
  - phase: 03-secret-gate-and-payload-integrity-unit-verified
    provides: "03-01 revit_mcp/trust.py (dialect, _blank style, 401 gate) which this plan extends"
provides:
  - "trust.evaluate_integrity / unverifiable / valid_manifest_path / mismatch_files / integrity_failure (pure three-state verdict and the 423 body)"
  - "revit_mcp/integrity.py: read-only check_integrity with the single hash_normalized"
  - "deploy/make_manifest.py: _manifest.json generator driven by git ls-files over the published copies"
  - "Manifest format {schema:1, generated_at, commit, files:{relpath: sha256}}"
affects: [03-05 reader/generator hardening, 03-06 IronPython simulation, 03-07 publish-extension.cmd, 03-08 live hashlib check, Phase 5 load-time check and 423 refusal]

plan_head_before: 67065f5a8e5098170bd8f88fdf9d61728453b79c
actuals:
  tokens: 9900
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Three-state integrity verdict: only a file that was read and differs is a mismatch; manifest_missing, manifest_unreadable and read_error are unverifiable"
    - "One hash function (CRLF->LF SHA-256) imported by the generator from the verifier's module, from the tool's own checkout"
    - "Reader opens only manifest-listed keys that pass valid_manifest_path; a hostile key is never opened"

key-files:
  created:
    - revit_mcp/integrity.py
    - deploy/make_manifest.py
    - tests/unit/test_integrity_e2e.py
    - tests/unit/test_trust_integrity.py
  modified:
    - revit_mcp/trust.py
    - tests/unit/test_registration.py

key-decisions:
  - "Underscore-prefixed revit_mcp/*.py files that the manifest does not list count as unexpected (D-12): startup discovery skips them as domains, but they are shipped code any module can import"
  - "integrity_failure accepts a list, tuple or set of names; a bare string yields an empty files list instead of being split into characters"
  - "A manifest that parses to a literal null is manifest_unreadable (present but unusable), not manifest_missing"
  - "datetime.now(timezone.utc) rather than utcnow() in the generator, to avoid the 3.12 deprecation warning while staying valid on CPython 3.8"

patterns-established:
  - "Generator refuses a DEST inside the git working tree and an untracked .py in the published tree, so the manifest can never silently disagree with what ships"

requirements-completed: [INTG-01, INTG-02, INTG-04, INTG-05, INTG-06]

coverage:
  - id: D1
    description: "Generator writes DEST/_manifest.json (schema 1, generated_at, full commit sha, files map from git ls-files, no pycache/pyc/LICENSE) and the verifier reads it back as verified_match"
    requirement: "INTG-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_e2e.py#test_manifest_has_schema_commit_and_exactly_the_tracked_files"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_e2e.py#test_untouched_published_tree_is_verified_match"
        status: pass
    human_judgment: false
  - id: D2
    description: "An edited, deleted or added revit_mcp file (underscore names included) is named under modified, missing or unexpected"
    requirement: "INTG-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_e2e.py#test_edited_deleted_and_added_files_are_named"
        status: pass
      - kind: unit
        ref: "tests/unit/test_trust_integrity.py#test_combination_gives_the_sorted_union"
        status: pass
    human_judgment: false
  - id: D3
    description: "A mismatch becomes an HTTP 423 body that reaches the model verbatim as Error: 423 - ... through the unchanged bridge._send and format_response"
    requirement: "INTG-04"
    verification:
      - kind: integration
        ref: "tests/unit/test_integrity_e2e.py#test_mismatch_reaches_the_model_as_a_visible_423"
        status: pass
      - kind: unit
        ref: "tests/unit/test_trust_integrity.py#test_integrity_423_status_and_body_keys"
        status: pass
    human_judgment: false
  - id: D4
    description: "Pure evaluate_integrity decision table: malformed manifest, bad observation and unreadable paths are unverifiable and never a mismatch; output is order-independent with sorted, non-ASCII-safe lists"
    requirement: "INTG-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_trust_integrity.py (65 tests, including the unverifiable property loop)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Hashes are SHA-256 over CRLF-normalized content, so a CRLF rewrite after generation still matches and a missing manifest is unverifiable/manifest_missing"
    requirement: "INTG-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_integrity_e2e.py#test_crlf_rewrite_after_generation_still_matches"
        status: pass
      - kind: unit
        ref: "tests/unit/test_integrity_e2e.py#test_deleted_manifest_is_unverifiable_never_mismatch"
        status: pass
    human_judgment: false
  - id: D6
    description: "integrity.py imports cleanly and registers nothing under IronPython 3 discovery (live behaviour not exercised here; plans 03-06 and 03-08 cover it)"
    verification:
      - kind: unit
        ref: "tests/unit/test_registration.py#test_revit_mcp_helpers_define_no_routes"
        status: pass
    human_judgment: true
    rationale: "Import under the real IronPython 3.4 routes engine is simulated in 03-06 and checked live in 03-08; no CPython test can prove it"

duration: 4min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 04: Payload Integrity Slice Summary

**SHA-256 payload manifest from `git ls-files` with a read-only three-state verifier (`verified_match` / `verified_mismatch` / `unverifiable`) and a visible HTTP 423 refusal, proven end to end from a temporary git repo through `bridge._send`.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-10-23T09:11:30Z
- **Completed:** 2026-10-23T09:15:14Z
- **Tasks:** 2
- **Files modified:** 6 (4 created, 2 modified)

## Accomplishments

- `deploy/make_manifest.py` builds `_manifest.json` (schema 1, `generated_at`, full commit sha, files map) from `git ls-files` over `startup.py`, `extension.json` and `revit_mcp/`, hashing the published DEST copies with the verifier's own `hash_normalized`. It refuses a DEST inside the working tree and an untracked `.py` in the published tree, and writes atomically.
- `revit_mcp/integrity.py` is a read-only (`"rb"` only) reader; `check_integrity(root)` never raises and only opens manifest keys that pass `valid_manifest_path`, delegating the verdict to `trust.evaluate_integrity`.
- `trust.py` gained the pure verdict, `mismatch_files` and `integrity_failure` (HTTP 423 body: `error`, `integrity`, sorted `files`).
- Tamper end to end: edit, delete, add (`rogue.py`, `_hidden.py`) are named; a CRLF rewrite still matches; a deleted manifest is `unverifiable/manifest_missing`; the 423 reaches the model as `Error: 423 - ...`.
- 65 decision-table tests pin every malformed-manifest, bad-observation and ordering case, with a property loop that no unreadable or unverifiable input is ever reported as a mismatch.

## Task Commits

1. **Task 1: End-to-end integrity slice** - `172c7c7` (feat)
2. **Task 2: Decision table and integrity registered as a helper** - `f12d6fb` (test)

**Plan metadata:** committed separately (docs: complete plan summary)

## Files Created/Modified

- `revit_mcp/trust.py` - integrity constants, `_result`, `unverifiable`, `valid_manifest_path`, `_valid_digest`, `evaluate_integrity`, `mismatch_files`, `integrity_failure`
- `revit_mcp/integrity.py` - `hash_normalized`, `read_manifest`, `observe_tree`, `check_integrity`, `MANIFEST_NAME`, `SCOPE_DIR`
- `deploy/make_manifest.py` - `tracked_files`, `current_commit`, `build_manifest`, `write_manifest`, `main`
- `tests/unit/test_integrity_e2e.py` - 8 tests: generator -> manifest -> reader -> verdict -> 423 through `_send`
- `tests/unit/test_trust_integrity.py` - 65 decision-table tests
- `tests/unit/test_registration.py` - "integrity" added to both helper sets

## Decisions Made

- Underscore-prefixed unlisted `.py` files are `unexpected` (D-12, RESEARCH Open Question 4; top-level listing only).
- `integrity_failure` takes a list, tuple or set; a bare string gives an empty list rather than characters.
- A manifest of literal `null` is `manifest_unreadable`, not `manifest_missing`.
- Generator timestamps with `datetime.now(datetime.timezone.utc)`; valid on CPython 3.8 and free of the 3.12 `utcnow` deprecation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] JSON `null` manifest produced `unverifiable` with reason `None`**
- **Found during:** Task 1 (reviewing `read_manifest` before the first run)
- **Issue:** `json.loads("null")` returns `None`, which `read_manifest` would have returned as `(None, None)`, making `check_integrity` emit `unverifiable(None)`.
- **Fix:** A parsed `None` returns `manifest_unreadable`.
- **Files modified:** `revit_mcp/integrity.py`
- **Committed in:** `172c7c7`

**2. [Rule 1 - Bug] `datetime.utcnow()` deprecated on newer CPython**
- **Found during:** Task 1
- **Fix:** `datetime.datetime.now(datetime.timezone.utc)`.
- **Files modified:** `deploy/make_manifest.py`
- **Committed in:** `172c7c7`

---

**Total deviations:** 2 auto-fixed (2 Rule 1)
**Impact on plan:** Both are small correctness fixes inside planned files; no scope change.

## TDD Note

Task 1 followed RED (collection failed with `ImportError: cannot import name 'integrity'`) then GREEN (8 passed on the first run of the implementation). Task 2's decision table passed on first run because `evaluate_integrity` and `integrity_failure` were already built to the full contract in Task 1, so no `trust.py` change was needed there and a separate RED was not observable.

## Issues Encountered

- `startup.py` already showed as modified in the working tree before this plan began (another session's work). Its hash is `85de483307be925517bee2ce3f109e5d6538560c` before and after; this plan did not touch it, and it was not committed.
- `uv run pytest tests/unit`: 4379 passed, 3 skipped (the 3 skips are not in this plan's tests; `test_integrity_e2e.py` ran with 0 skipped).
- Git prints LF-to-CRLF working-copy warnings on add; harmless, and the hashing is CRLF-insensitive by design.

## Known Stubs

None.

## Threat Flags

None. The new surface (a manifest file read and a build-time generator) is covered by the plan's threat model (T-03-19 to T-03-23). Nothing is wired into Revit's load path; Phase 5 does that.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 03-05 can harden the reader and generator (never-writes proof, unreachable reference, dev junction, untracked files) on top of these functions.
- 03-07 can call `deploy/make_manifest.py` from `publish-extension.cmd`.
- Live check of `hashlib` under IronPython 3 and discovery of `integrity.py` as a helper remain for 03-06 and 03-08.

## Self-Check: PASSED

- FOUND: revit_mcp/integrity.py, deploy/make_manifest.py, tests/unit/test_integrity_e2e.py, tests/unit/test_trust_integrity.py
- FOUND commits: 172c7c7, f12d6fb (`git log --oneline --grep="03-04"`)
- Acceptance checks re-run: INTEGRITY_SLICE_OK, PY38_OK, no `_manifest.json` in the repo root, `startup.py` hash unchanged, `uv run pytest tests/unit -q` 4379 passed.

---
*Phase: 03-secret-gate-and-payload-integrity-unit-verified*
*Completed: 2026-10-23*
