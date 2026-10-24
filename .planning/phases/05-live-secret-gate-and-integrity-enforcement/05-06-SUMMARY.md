---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 06
subsystem: route-gate-conventions
status: complete
---

# Plan 05-06 Summary

## Completed

- Added the closed-by-default AST sentinel over the real route inventory and made the Phase 2 guarded-handler test require the gate-first preamble.
- Added `check_route_gate` to `scripts/conventions.py`, including the mirrored open-read list, relative security-import allowlist, and IronPython sibling-import protection.
- Added convention cases for malformed gates, misplaced strips, GET routes, security imports, parity with `trust.OPEN_POST_READ_ROUTES`, and contributor-package checking.
- Updated both POST route scaffolds to start with the gate before parsing or document access; GET scaffolds remain ungated.
- Extracted `scripts/new_tool.py` route generation into `build_route_source()` for direct convention testing.
- Updated `CONTRIBUTING.md` for IronPython 3 relative imports and the closed-by-default gate contract.

## Verification

- `uv run pytest tests/unit/test_phase5_gate_wiring.py tests/unit/test_phase2_inventory.py -q`
- `uv run pytest tests/unit/test_conventions.py -q -k "route_gate or gate or parity or local_modules or scaffold or build_route_source or kit"` — 48 passed.
- `uv run pytest tests/unit/test_conventions.py -q` — 415 passed, 3 skipped.
- `uv run pytest tests/unit -q` — 5809 passed, 3 skipped.
- Confirmed edited code files have no UTF-8 BOM and `git diff --check` is clean.

## Notes

- `scripts/new_tool.py` had a pre-existing status URL correction that was preserved and is not part of this plan's scaffold implementation.
- `contrib-kit/conventions.py` remains a generated artifact and was not edited. Rebuild the contributor kit with `scripts/build_contrib_kit.py` during the next user-run release.
