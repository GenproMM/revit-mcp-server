---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "06"
subsystem: mutation-safety
status: complete
completed: 2026-10-25
requirements-completed: [SAFE-06, SAFE-07]

requires:
  - phase: 07-repository-owned-mutation-safety-and-human-approval
    provides: "07-04 policy loader, operator overlay and approval boundary"
provides:
  - "AST-derived policy inventory guard for all 59 tools and 56 registered routes"
  - "Pure policy.Decision and policy.decide D-10/D-22 evaluator"
  - "approval.authorize delegates conditional outcomes to policy.decide"
affects: [07-08, 07-10, 07-11, 07-14]

key-files:
  created:
    - tests/unit/test_policy_inventory.py
    - tests/unit/test_policy_decisions.py
  modified:
    - policy.base.toml
    - policy.py
    - approval.py

commits:
  - 3e789a5
  - cad6e68
---

# Phase 7 Plan 06: Complete policy inventory and decisions Summary

**The base policy is now checked against the source-derived tool and route surfaces, while a pure decision evaluator applies the chosen parameter-write and family-edit rules before approval asks a human or grants a permit.**

## Accomplishments

- Added an AST-backed classification guard for the 59 manifest tools and 56 registered extension routes. It verifies each tool's transport routes, every route's decorator method, each GET route's `allow` decision, and `document_bound` from the handler call graph.
- Pinned the seven non-default decisions in a literal expectation table; all other routes must be explicit `allow` rows. The guard reports unclassified synthetic tool and route additions as coverage gaps and confirms that unknown routes have no rule.
- Corrected `/activate_document/` to `document_bound = false`, matching the `mutation_document_or_response` AST fact. This is the only source-vs-policy structural difference found by the guard.
- Added immutable `Decision` and pure `policy.decide(rule, data, facts=None, fop=None)`.
  - `parameter_write` permits only an empty instance-level parameter write on an existing, non-type, non-group element, subject to the rule's `confirm_when` overlay.
  - Unknown/missing facts, type-level writes, multi-instance type effects, overwrite attempts, and group members are confirmed with their reason words.
  - `family_edit` confirms ordinary edits but denies additions of shared parameters unless the supplied FOP facts are `ok` and every requested name is `match`.
- Routed `approval.authorize` through `policy.decide`; current calls without 07-10/07-11 facts retain the conservative confirm/deny outcomes.
- Added decision-table coverage for normal cases, unsafe facts, FOP verdicts and states, fixed always-confirm routes, and the deliberately permitted D-15 operator relaxations.

## Verification

- `uv run pytest tests/unit/test_policy_inventory.py -q` — **10 passed**
- `uv run pytest tests/unit/test_policy_decisions.py -q` — **31 passed**
- `uv run pytest tests/unit/test_policy_decisions.py tests/unit/test_phase7_tracer.py tests/unit/test_policy_reload.py -q` — **74 passed**
- `uv run pytest tests/unit -q` — **6665 passed, 3 skipped**
- `git diff --check` passed for both task changes.
- `graphify update .` completed after the code changes; its generated working-tree output was intentionally not included in these commits.

## Task Commits

1. **Task 1 — policy classification guard:** `3e789a5` (`test(07-06): guard policy inventory`)
2. **Task 2 — policy decision evaluator and approval integration:** `cad6e68` (`feat(07-06): decide policy checks`)

## Deviations and Notes

- The initial inventory guard exposed two policy mismatches. `/activate_document/` had a stale `document_bound = true` value and was corrected. `get_revit_process_status` is classified as a local process tool by the wider Phase 2 taxonomy but still deliberately sends a `/status/` transport call, so it remains a non-local policy tool with that route; the final AST transport assertion covers the actual behavior.
- The repository's Git maintenance attempted to remove an unrelated stale `.git/worktrees/hot-cirrus` record after each commit and printed `Permission denied`. Both commits completed successfully; no worktree was removed or changed.
- No Revit route, deployment, publication, upstream merge/rebase, or live test was run.

## Next Phase Readiness

Plan 07-06 is complete. Plan 07-08 remains blocked on the separate, explicit user checkpoint: `enforce` (turn on Revit-side one-time-permit enforcement) or `defer` (stop before that irreversible compatibility change).
