---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "10"
subsystem: mutation-preflight
status: complete
---

# Phase 7 Plan 10 Summary

## Outcome

Added the bridge-internal read-only `/mutation_preflight/` route and shared lookup helpers. The route resolves the document through the production mutation guard, returns guard refusals unchanged, and reports facts for the six supported mutations. This plan supplies the route; CPython approval integration and company shared-parameter validation continue in Plan 07-11.

## Changes

- Shared parameter, family and shared-definition resolution lives in `revit_mcp/lookup.py`, used by the existing mutation handlers and preflight.
- Follow-up tests exposed two defects in the initial helper refactor: the type count capped matches rather than scanned elements, and API errors were silently treated as missing objects. The scan now stops at the visited-element cap; lookup errors propagate to the existing handler exception boundaries rather than becoming false not-found results.
- `/mutation_preflight/` is an open POST read with `strip_envelope` first. It accepts only the six supported route keys and object bodies/arguments, uses `parse_request_data`, and never opens a transaction or activates a document.
- Added the eighth open-read entry in trust, conventions, audit and the literal security sentinel. Inventory pins are 57 routes, 42 non-GET, 15 GET, 34 gated and 8 open. MCP tools remain 59; the preflight is explicitly bridge-internal.
- Parameter facts include instance/type resolution, read-only and storage flags, meaningful-value status, display and raw internal values, element/type/family/category/group details and capped type-instance counts.
- Delete/transform facts include requested/found/missing IDs, categories, important element kinds, pinned count and operation. Cascade remains `unknown`.
- Family edit facts include family metadata, requested changes, counts across symbols and configured shared definitions with GUID/data-type/group metadata and duplicate-GUID ambiguity. Family load facts read only file existence/size and loaded-name presence; RFA contents remain `unknown`.
- Caps: 2000 requested IDs, 50 requested parameter names (including shared additions for family edits), 20000 scanned elements per count, first 20 missing IDs and top 10 categories. Reaching a count cap yields null with `count_capped`, not an estimate.
- Fact-builder failures return `available: false` with the exception class and a warning; Cyrillic names are retained.

## Verification

Checks used the isolated `phase7-test-venv`, not the shared repository `.venv`.

- Helper/mutation-contract suite after helper corrections: `2009 passed, 3 skipped`.
- Preflight, conventions and inventory suite: `1073 passed, 3 skipped` before the additional boundary/error rows.
- Final helper and preflight suites: `64 passed` (11 helper tests and 53 preflight tests).
- Full suite after route/pin implementation: `6769 passed, 3 skipped`.
- Final full suite after fact implementation: `6802 passed, 3 skipped` in 113.67 seconds.
- Cold start: `INIT_LATENCY_S=0.988`.
- `git diff --check` passed for the owned changes; new/changed source files checked without UTF-8 BOM.
- `graphify update .` completed; generated graph changes were excluded from commits.

## Deviations and remaining evidence

- Additional existing pins in `test_policy_inventory.py`, `test_phase7_tracer.py` and `test_registration.py` needed updates. Registration permits only explicitly classified bridge-internal route domains to lack a tool module; mixed internal/external domains still fail.
- The offline tests prove read-only behavior against fakes and the source call graph, not actual Revit API performance, group fan-out or live shared-file metadata. These remain the user-run Plan 07-14 bench.
- Duplicate shared definitions retain file order and the mutation still selects the last entry. The helper has a duplicate-order test and the existing family mutation suite passed, but no new end-to-end duplicate-name family mutation row was added in this plan.
- No live Revit calls, starts, reloads or restarts were performed. No real deployment, release build, publication, push or tag was performed. Deployment unit fixtures use scratch paths only.
- Git reported its existing `hot-cirrus` worktree cleanup permission warning; commits succeeded. No worktree cleanup was attempted.

## Commits

- `2aaea53 refactor(07-10): share mutation lookups`
- `ee735fa feat(07-10): add pinned read-only mutation preflight`
- `3b5da45 feat(07-10): collect bounded mutation preflight facts`

## Next

Plan 07-11: connect the bounded preflight facts to approval and validate shared-parameter requests against the company FOP source. Live verification remains Plan 07-14 after a full Revit restart, never Reload.
