---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "12"
subsystem: confirmation-documentation-and-r5-runbook
status: complete
---

# Phase 7 Plan 12 Summary

## Outcome

Documented the Phase 7 confirmation contract for models, developers, operators and engineers. The documentation now distinguishes server-initiated client confirmation from chat text, pins the known bypass limits, explains R5 rollout order and operator-policy handling, and gives users a Russian explanation of the confirmation window.

## Changes

- `audit.SERVER_INSTRUCTIONS` and the seven mutation-sensitive tool docstrings now say when a client confirmation window opens, that chat or an argument cannot replace it, and that refusals sent nothing to Revit and must not be blindly retried.
- `CLAUDE.md` records the 59 tools / 57 routes / 25 domain modules surface, the authorization/permit/policy invariants, and the six verbatim residual-limit sentences.
- `approval.py` now keeps the same six limits in its module docstring; `tests/unit/test_phase7_scope_docs.py` pins every sentence independently in both locations, plus the operator/user documentation markers.
- `deploy/RELEASE-RUNBOOK.md` now has the R5 confirmation-and-permit section: pre-phase scanner and test gate, payload-first delivery, planned full restart and atomic extension publication, mixed-state remediation, operator policy validation/ACL/reload behavior and transport limits.
- `deploy/USER-GUIDE.md` explains in Russian what the confirmation window shows, the one-time approval, five-minute timeout, `подтверждение не получено`, and the limits of this protection. `deploy/README.md` maps `operator_policy.toml` and `app\policy_source`; the root `README.md` links to the user guidance.

## Verification

All checks used the isolated `phase7-test-venv`; no repository `.venv` was synchronized or changed.

- Focused confirmation/docstring gate: `1072 passed, 3 skipped`.
- Scope and serialization documentation pins: `23 passed`.
- Initial full-suite attempt from the PowerShell UTF-8 console failed in existing scratch publish tests because cmd parsed their LF batch files incorrectly under code page 65001.
- Final full suite through a child cmd at code page 866: `6877 passed, 3 skipped in 138.95s`.
- `git diff --check` passed for the Plan 07-12 documentation files.

## Commits

- `b1a8878 test(07-12): pin confirmation model contract`
- `927bead docs(07-12): pin mutation safety limits`
- `f7a5e8a docs(07-12): add R5 confirmation runbook`

## Deviations and remaining evidence

- `.planning/ROADMAP.md` already contained unrelated uncommitted orchestrator changes. Per the plan's dirty-file rule, its Phase 7 criterion 2 was not committed or modified by this plan; it still needs the planned D-15 wording when the file is safe to edit.
- No live Revit, Hermes Desktop, deployment share, route, restart/reload, release build, publication, push or tag was run. Telegram/gateway confirmation remains explicitly unverified live.
- `graphify update .` was not run: the repository already has extensive unrelated generated graph changes, and updating it would enlarge that unrelated dirty set.

## Next

Plan 07-13 provides an offline-tested, operator-run live acceptance bench. It must be authored and tested without invoking any live Revit, Hermes, route or share; Plan 07-14 remains the separately authorized human checkpoint.
