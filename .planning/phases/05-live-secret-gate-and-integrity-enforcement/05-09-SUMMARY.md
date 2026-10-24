---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 09
subsystem: deploy
tags: [d-06, envelope, static-analysis, ast, payload-first, tdd]

requires:
  - phase: 03-trust-primitives
    provides: revit_mcp/textutils.py parse_request_data (the single sanctioned body parser)
provides:
  - scripts/scan_envelope_tolerance.py, the static half of the D-06 proof (does an extension tree tolerate the extra _mcp key in every POST body)
  - the recorded verdict on the pre-phase tree c187004 - ENVELOPE_SCAN_OK files=31, no D-06 blocker
affects: [05-10, 05-16]

plan_head_before: dd735a7fb578b99103f95f50118b56654428b4c7
actuals:
  tokens: 8000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Source-only AST scan with a statement-level flow walker: a name stays tracked while any path leaves it bound to the parsed body, so a rebinding on one branch cannot hide a use on the other"
    - "Output tokens as the only evidence: module label, line number and a short reason, never source text or a body value"

key-files:
  created:
    - scripts/scan_envelope_tolerance.py
    - tests/unit/test_scan_envelope_tolerance.py
  modified: []

key-decisions:
  - "Only parse_request_data(<x>.data) binds a tracked body. trust.split_envelope and identity/documents helpers parse other values and are out of scope; trust.split_envelope iterates its parsed dict on purpose to strip the envelope key and no pre-phase route calls it"
  - "A BoolOp operand counts as a truthiness test only when the whole BoolOp is one, because `a or b` evaluates to an operand; `x = request.data or {}` is therefore a raw-body finding"
  - "A module that does not parse is a finding (exit 1), not a pass: tolerance cannot be proven for it"
  - "--dir and --git-rev are a required mutually exclusive pair; --repo defaults to the repository containing the script"

requirements-completed: [SEC-02, SEC-06]

duration: about 25 min
completed: 2026-10-24
status: complete
---

# Phase 5 Plan 09: D-06 envelope tolerance scanner Summary

**Pre-phase verdict: no D-06 blocker. `scan_envelope_tolerance.py --git-rev c187004` reports ENVELOPE_SCAN_OK over all 31 revit_mcp modules, so no old handler iterates, copies, echoes or forwards its parsed body or reads request.data raw, and the payload-first order (D-05) is not blocked by what the static scan can see.**

This is the STATIC half of the D-06 proof (T-05-40). A clean scan does not exercise Revit and can miss shapes it does not model; the payload-first rehearsal on the pilot share (plan 05-10 runbook) is the live half and must still run.

## Pre-phase scan output (`uv run python scripts/scan_envelope_tolerance.py --git-rev c187004`, exit 0)

```
ENVELOPE_TOLERANT revit_mcp/__init__.py
ENVELOPE_TOLERANT revit_mcp/analysis.py
ENVELOPE_TOLERANT revit_mcp/annotation.py
ENVELOPE_TOLERANT revit_mcp/building.py
ENVELOPE_TOLERANT revit_mcp/clash.py
ENVELOPE_TOLERANT revit_mcp/code_execution.py
ENVELOPE_TOLERANT revit_mcp/colors.py
ENVELOPE_TOLERANT revit_mcp/detail.py
ENVELOPE_TOLERANT revit_mcp/document.py
ENVELOPE_TOLERANT revit_mcp/documentation.py
ENVELOPE_TOLERANT revit_mcp/documents.py
ENVELOPE_TOLERANT revit_mcp/editing.py
ENVELOPE_TOLERANT revit_mcp/identity.py
ENVELOPE_TOLERANT revit_mcp/integrity.py
ENVELOPE_TOLERANT revit_mcp/interop.py
ENVELOPE_TOLERANT revit_mcp/mep.py
ENVELOPE_TOLERANT revit_mcp/model_info.py
ENVELOPE_TOLERANT revit_mcp/parameters.py
ENVELOPE_TOLERANT revit_mcp/placement.py
ENVELOPE_TOLERANT revit_mcp/registry.py
ENVELOPE_TOLERANT revit_mcp/rooms.py
ENVELOPE_TOLERANT revit_mcp/status.py
ENVELOPE_TOLERANT revit_mcp/structure.py
ENVELOPE_TOLERANT revit_mcp/tags.py
ENVELOPE_TOLERANT revit_mcp/textutils.py
ENVELOPE_TOLERANT revit_mcp/transforms.py
ENVELOPE_TOLERANT revit_mcp/trust.py
ENVELOPE_TOLERANT revit_mcp/utils.py
ENVELOPE_TOLERANT revit_mcp/view_management.py
ENVELOPE_TOLERANT revit_mcp/views.py
ENVELOPE_TOLERANT revit_mcp/worksharing.py
ENVELOPE_SCAN_OK files=31
```

The current working tree (`--dir revit_mcp`, 32 files including the new modules) also ends in `ENVELOPE_SCAN_OK files=32`.

## Command for the administrator

Run against the extension currently on the main share BEFORE publishing the R3 payload (read-only, writes nothing):

```
python scripts\scan_envelope_tolerance.py --dir "\\<share>\ext\revit-mcp-server.extension\revit_mcp"
```

Exit 0 means nothing suspect; 1 means a suspect (a D-06 blocker for payload-first, goes back to the user); 2 means a usage error or an unreadable input.

## Accomplishments

- Task 1 (tracer, e6f26d2): `scan_source` follows every name bound from `parse_request_data(<x>.data)` (including `... or {}` and conditional forms) through a statement-level flow walker, classifies each use by its parent node (allowed: `.get(...)`, subscript read, any comparison, `isinstance`, truthiness; everything else suspect with a reason such as "iterated" or "passed to make_response"), ends tracking at a rebinding, and handles handlers nested in `register_*_routes`. `scan_git_rev` lists and reads `revit_mcp/*.py` via `git ls-tree` and `git show`. Verified end to end on c187004.
- Task 2 (0a165db): raw `request.data` rule (neither the argument of `parse_request_data` nor a truthiness test is suspect), `scan_directory` and `--dir`, stable sorted output, every failure path prints an `ERROR:` line and returns 2, and a 56-row test table including the Python 3.8 grammar and no-annotation check, a write-nothing check (listing and mtimes unchanged) and a standard-library-only import check.

## Task Commits

1. Task 1: e6f26d2 `feat(05-09): add D-06 envelope tolerance scanner with --git-rev`
2. Task 2: 0a165db `feat(05-09): add --dir mode, raw request.data rule and full suspect table`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Tracking was wider than the plan's definition and flagged trust.py**
- **Found during:** Task 1, first run on c187004 (ENVELOPE_SUSPECT at revit_mcp/trust.py:74 and :78)
- **Issue:** I first tracked the result of `parse_request_data(<any argument>)`. `trust.split_envelope` parses its own `raw` argument and iterates the dict with `.items()` to strip the `_mcp` key on purpose; it is a helper, not a route handler, and no pre-phase route calls it. Reported as suspect it would have been a false D-06 blocker.
- **Fix:** Tracking now follows the plan's definition exactly: only `parse_request_data(<x>.data)` binds a body. Test `test_the_parse_of_a_non_request_value_is_out_of_scope` pins it.
- **Files modified:** scripts/scan_envelope_tolerance.py, tests/unit/test_scan_envelope_tolerance.py
- **Commit:** e6f26d2

**Total deviations:** 1 auto-fixed (1 bug). **Impact:** none on scope; the verdict is the plan's own definition applied literally.

## Known limitations of the static scan (why it is only half the proof)

- A body read through an alias, for example `body = getattr(request, "data", None)` (revit_mcp/documents.py `_selector_from_request`), is not tracked as a raw `request.data` read. That site only compares the value and passes it to `parse_request_data`, then reads `data.get("document")`, so it is tolerant by inspection, but the scanner does not prove it.
- Aliases of the parsed body (`other = data`) are reported as suspect rather than followed, which is the conservative direction.
- Dynamic access (`getattr`, `eval`, `exec`, `/execute_code/`) is not modelled.
- Scope is the shipped route modules as source; it says nothing about pyRevit's own handling of the body.

## Issues Encountered

None.

## Threat Flags

None. The scanner adds no endpoint, auth path or file write; it reads source and prints labels, line numbers and reasons only.

## Known Stubs

None.

## Next Phase Readiness

Ready for the next plan. The 05-10 runbook should cite the `--dir` command above as the pre-publish static check and keep the pilot-share payload-first rehearsal as the live half.

## Self-Check: PASSED

- FOUND: scripts/scan_envelope_tolerance.py
- FOUND: tests/unit/test_scan_envelope_tolerance.py
- FOUND: e6f26d2, 0a165db (`git log --grep="05-09"`)
- `uv run pytest tests/unit/test_scan_envelope_tolerance.py -q`: 56 passed (criteria: at least 25)
- `uv run python scripts/scan_envelope_tolerance.py --git-rev c187004`: 32 `ENVELOPE_` lines, final ENVELOPE_SCAN_OK (criteria: at least 24 plus a final token)
- `uv run python scripts/scan_envelope_tolerance.py --dir revit_mcp`: exit 0, final ENVELOPE_SCAN_OK
- `uv run pytest tests/unit -q`: 5382 passed, 3 skipped (baseline 5326 passed, 3 skipped)
