---
phase: 03-secret-gate-and-payload-integrity-unit-verified
plan: 07
subsystem: deploy-pipeline
tags: [secret, manifest, publish-extension, build-payload, gate, cmd, robocopy, line-order-tests]

requires:
  - phase: 03-secret-gate-and-payload-integrity-unit-verified
    provides: "03-02 deploy/secret_tool.py (ensure/stage/verify); 03-04/03-05 deploy/make_manifest.py and revit_mcp/integrity.py"
provides:
  - "deploy/config.cmd: MCP_SECRET_FILE (env override, default %MCP_SHARE_ROOT%\\_build\\bridge_secret) with rotation and threat-model notes"
  - "deploy/publish-extension.cmd: find-python guard, /XF *.pyc _bridge_secret _manifest.json, secret_tool.py stage, make_manifest.py, in that strict order"
  - "deploy/build-payload.cmd: secret_tool.py stage into app\\_bridge_secret between the app copy and gate.py"
  - "deploy/gate.py: _secret_pair_status / SECRET= line, import-safe main guard"
  - "CLAUDE.md: shared-helpers sentence (textutils + trust + integrity) and the secret/manifest sharp-edge bullet"
  - "tests/unit/test_secret_pipeline.py: 33 new tests (config, publish order, scratch guard, Windows publish smoke, build-payload order, gate pair, CLAUDE.md)"
affects: [03-08 live hashlib check, Phase 5 load-time secret and integrity enforcement, Phase 5 runbook update]

plan_head_before: 44a2d2ca2dd65073a46efcc16679364ff089aa14
actuals:
  tokens: 5500
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Line-order tests over .cmd files: locate lines by stripped prefix/substring (skipping rem lines), assert strictly increasing indexes"
    - "Scratch guard for a destructive script test: _assert_scratch calls pytest.fail (never skip) unless every written root resolves under tmp_path and none is UNC; the guard's own rejection of the real share is tested without spawning anything"
    - "Dirty-tree isolated-hunk commit via a temporary GIT_INDEX_FILE holding HEAD's blob plus only this task's edits"

key-files:
  created: []
  modified:
    - deploy/config.cmd
    - deploy/publish-extension.cmd
    - deploy/build-payload.cmd
    - deploy/gate.py
    - tests/unit/test_secret_pipeline.py
    - CLAUDE.md

key-decisions:
  - "Default MCP_SECRET_FILE is %MCP_SHARE_ROOT%\\_build\\bridge_secret (RESEARCH A4, reversible one-line change in config.cmd); outside ext\\ and payload\\"
  - "gate.py reports SECRET=unchecked (not a failure) when MCP_SECRET_FILE is unset so a gate run outside the build still works"
  - "Runbook/README not edited in this phase; the operator note lives in config.cmd, the runbook update belongs to Phase 5"

patterns-established:
  - "The secret is staged AFTER the exclusion-bearing robocopy and the manifest is written LAST into DEST, so the manifest describes exactly the published tree"

requirements-completed: [SEC-08, INTG-01]

coverage:
  - id: D1
    description: "Extension publish excludes a developer's _bridge_secret and stray _manifest.json, stages the fleet secret and writes a manifest of exactly what was copied (ROADMAP SC7 end to end)"
    requirement: "SEC-08"
    verification:
      - kind: integration
        ref: "tests/unit/test_secret_pipeline.py#test_publish_smoke_scratch_share"
        status: pass
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_publish_order_lines_strictly_increasing"
        status: pass
    human_judgment: false
  - id: D2
    description: "Payload build stages the same secret before the gate, and the gate refuses a mismatched pair without printing a value"
    requirement: "SEC-08"
    verification:
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_build_payload_order_stage_between_app_copy_and_gate"
        status: pass
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_gate_pair_one_byte_off_fails_without_printing_either_value"
        status: pass
    human_judgment: false
  - id: D3
    description: "The publish smoke test cannot reach the real fleet share"
    requirement: "INTG-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_publish_smoke_guard_rejects_real_share"
        status: pass
    human_judgment: false
  - id: D4
    description: "Developer documentation of the pipeline, rotation and the LAN-barrier threat model"
    verification:
      - kind: unit
        ref: "tests/unit/test_secret_pipeline.py#test_claude_md_documents_the_secret_and_manifest_pipeline"
        status: pass
    human_judgment: true
    rationale: "Tests pin required terms; whether the prose is clear to a developer needs a human read"

duration: 25min
completed: 2026-10-23
status: complete
---

# Phase 3 Plan 07: Secret and Manifest Build Wiring Summary

**One MCP_SECRET_FILE now feeds a byte-identical secret into both the published extension and the payload, and publish-extension.cmd writes a manifest after the copy that is verified by a real publish into a scratch share.**

## Performance

- **Duration:** about 25 min
- **Tasks:** 2
- **Files modified:** 6 (no files created)

## Accomplishments

- `publish-extension.cmd` locates pyRevit's CPython (stops with an ERROR if absent), copies `revit_mcp` with `/XF *.pyc _bridge_secret _manifest.json`, then stages the fleet secret, then runs `make_manifest.py --repo --dest`, then the installer robocopy. Nothing is copied into `%DEST%` after the manifest.
- A real run of the working-tree script against a scratch share (temp dir, `MCP_PYEXE` = test interpreter) exits 0, `revit_mcp\_bridge_secret` is byte-equal to `MCP_SECRET_FILE`, `check_integrity` returns `verified_match`, no `__pycache__` ships, and the secret never appears in the output. It ran on this machine and was not skipped.
- The smoke test runs `rmdir /s /q` on DEST, so it is fenced: `_assert_scratch` (pytest.fail, never skip) requires MCP_SHARE_ROOT, MCP_SECRET_FILE, DEST (pinned by `test_publish_order_dest_derivation`) and the installer target to resolve under tmp_path and not be UNC; a separate test proves it rejects config.cmd's default `\\srv-dfs\BIM\06_RevitMCP`, a secret path outside tmp_path and an escaping `MCP_EXT_NAME`, with no process started.
- `build-payload.cmd` stages `app\_bridge_secret` from the same file after the app copy and before `gate.py`; `gate.py` gained `_secret_pair_status` (SECRET=ok / unchecked / failed, paths only) and no longer runs `main()` on import.
- CLAUDE.md names `revit_mcp/trust.py` and `revit_mcp/integrity.py` beside `textutils.py` and documents the pipeline, dev layout, rotation, the reserved `_mcp` body key and that the secret is a network barrier only.

## Task Commits

1. **Task 1: extension publish excludes local artifacts, stages the secret, writes the manifest** - `8666be4` (feat)
2. **Task 2: payload build stages the same secret, gate verifies the pair, developer docs** - `b305698` (feat)

**Plan metadata:** the `docs(03-07): complete plan summary` commit (SUMMARY only; STATE/ROADMAP left uncommitted for the orchestrator).

## Files Created/Modified

- `deploy/config.cmd` - MCP_SECRET_FILE default plus rem block (once-only, rotation, LAN barrier)
- `deploy/publish-extension.cmd` - find-python guard, /XF names, secret stage, manifest step (CRLF preserved)
- `deploy/build-payload.cmd` - secret stage line before the gate
- `deploy/gate.py` - `SECRET_ARTIFACT`, `_secret_pair_status`, `SECRET=` line, `if __name__ == "__main__"`
- `tests/unit/test_secret_pipeline.py` - config, publish order, guard, smoke, build-payload order, gate, CLAUDE.md tests
- `CLAUDE.md` - helpers sentence and the sharp-edge bullet

## Decisions Made

Followed the plan's reconciliations (C5, C6, A4, A6). The default secret path is the flagged-assumption `_build\bridge_secret`; the runbook and README were deliberately not touched.

## Deviations from Plan

None - plan executed exactly as written. Two process notes, not deviations:

- **Dirty-tree commits.** `deploy/publish-extension.cmd` carries a foreign uncommitted one-line edit (installer robocopy: `forget_retired_path.py` replaced by `check_routes_config.py`). Task 1 was committed through a temporary index holding HEAD's blob plus only this plan's edits; `git show HEAD:deploy/publish-extension.cmd` still has `forget_retired_path.py` and `make_manifest.py`, and `git diff -- deploy/publish-extension.cmd` afterwards shows only that foreign hunk. The real index still lists exactly the pre-existing foreign staged files (phase-07 CONTEXT and RESEARCH-NOTES, plus the Obsidian notes; ROADMAP.md was later committed by another session).
- **Interleaved foreign commits.** Another session committed `001a140` and `60b757e` between my two commits (including the CLAUDE.md "Release checkpoints" hunk that had been dirty), so `git rev-list --count 44a2d2c..HEAD` reads 4. `commits: 2` is the measured count of `(03-07)` commits (`git log --grep`), which is what the plan produced. CLAUDE.md was therefore clean at Task 2 and committed by plain pathspec.

## Known Stubs

None.

## Threat Flags

None. The new surface (secret and manifest files on the share) is the planned T-03-36 to T-03-40 surface; T-03-40 (anyone who can read the share holds the secret) is accepted and documented.

## Issues Encountered

- RED run of the gate tests against the old `gate.py` ran `main()` on import (it spawned the server) and hung until the shell timeout; this was the expected RED for the import-safety requirement and is fixed by the main guard.

## Verification

- `uv run pytest tests/unit -q`: 4630 passed, 3 skipped (baseline before this plan 4602 passed, 3 skipped; the 3 skips are pre-existing and unrelated).
- `-k "config or publish"`: 12 passed, 0 skipped. `-k "build_payload or gate or claude_md"`: 14 passed.
- `tests/unit/test_payload_ships_root_modules.py` and `tests/unit/test_serialization_scope_docs.py` pass.
- CRLF check on `deploy/publish-extension.cmd` passes; `config.cmd`, `build-payload.cmd`, `gate.py`, `CLAUDE.md` remain LF. `GATE_GUARD_OK` printed. `tests/test_init_latency.py`: `INIT_LATENCY_S=0.372`.
- No `_manifest.json` was created in the repository by the smoke test.
- The real `.cmd` scripts were not run against the live share or the %APPDATA% junction; only the scratch smoke test ran.

## Next Phase Readiness

Ready for 03-08. Nothing in Revit reads the secret or the manifest until Phase 5, which should also update the runbook and README with the operator note now living in `config.cmd`.

## Self-Check: PASSED

- Commits `8666be4` and `b305698` exist; all six modified files exist on disk.
- All task acceptance criteria re-run and green (see Verification).
