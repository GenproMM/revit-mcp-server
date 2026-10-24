---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 14
subsystem: phase-5-live-gate
tags: [live-gate, integrity, corrupt-stage, 423, verified_mismatch]
status: complete
plan_head_before: f9296805bbc6d470313b74395210c3da4d5f97d0
commits: 0
actuals:
  tokens: 0
  tasks: 3
  commits: 0
completed: 2026-10-24
---

# Plan 05-14 Summary: live corrupt stage (verdict PHASE5_GATE_OK, PASS)

**With one modified module (`revit_mcp/detail.py`) and one unexpected module (`revit_mcp/_zz_probe.py`) loaded in a freshly restarted Revit 2024, the extension reported `verified_mismatch` naming both files, went `degraded` with a security alert, and refused both an authenticated `create_level` and an authenticated `execute_revit_code` with `423`. An unauthenticated `create_level` was still `401` (secret before integrity), and reads and `/status/` kept answering. The stage ran once; the developer tree is restored to clean.**

`commits: 0` is correct: the plan changes no repository file (the corruption was made and undone in the working tree). The only commit is this SUMMARY, made after the measured count.

## Verdict

```
PHASE5_GATE_OK
STAGE=corrupt
POSTS_SENT=4
This stage is consumed and must not be run again.
```

Record: `C:/Temp/phase5/S2-corrupt.json` (outside the repository). The stage ran exactly once, at the first attempt. No level was created (both mutations were refused before any transaction).

## Task results

| Task | Result |
|------|--------|
| 1 Stage the two corruptions | `corrupt --module revit_mcp/detail.py` appended one comment line to `revit_mcp/detail.py` and created `revit_mcp/_zz_probe.py`. The offline check `deploy/make_manifest.py --check --dest .` printed `INTEGRITY verified_mismatch`, `MODIFIED revit_mcp/detail.py` and `UNEXPECTED revit_mcp/_zz_probe.py`. (Executed by an earlier executor; its console text is reported to me by the orchestrator in those three tokens, not as a verbatim transcript.) |
| 2 User restarts Revit | The user fully restarted Revit and replied "ready" with one listener row (127.0.0.1:48884, Listen). They opened one new unsaved project. |
| 3 Corrupt stage, restore, suite | Run once: PHASE5_GATE_OK. Restore printed `RESTORED clean`. Unit suite green. |

## Listener and document checks (before the run, by the executor)

- `Get-NetTCPConnection -LocalPort 48884 -State Listen`: exactly one row, `127.0.0.1:48884`, OwningProcess **19132**.
- `GET /genpro_revit_mcp/status/`: HTTP 200. `health` `degraded`, integrity `verified_mismatch` (modified `[revit_mcp/detail.py]`, unexpected `[revit_mcp/_zz_probe.py]`, missing `[]`), `bind` `loopback_only`, `domains_registered` 24, Revit 2024, PID 19132, port 48884, session `b175244e-9e3e-41c1-9a0e-f19022602942`, secret configured with fingerprint `6b6cfa6a`, and a security alert that the extension files differ from the published manifest and every mutation is refused with 423.
- `GET /genpro_revit_mcp/documents/`: HTTP 200, `count 1`, title "Проект1", `active true`, `saved false`, `path ""`, document `doc1.b020463cd5cd.1`.

## Console output (verbatim)

### Run, `uv run python tests/test_phase5_live_gate.py run --stage corrupt --module revit_mcp/detail.py --out C:/Temp/phase5/S2-corrupt.json` (exit 0)

```
PHASE5_GATE_OK
STAGE=corrupt
POSTS_SENT=4
This stage is consumed and must not be run again.
```

### Classify, `classify --stage corrupt C:/Temp/phase5/S2-corrupt.json` (exit 0)

```
PHASE5_GATE_OK
STAGE=corrupt
POSTS_SENT=4
```

### scan-secret (exit 0)

```
SECRET_ABSENT
```

## What the record shows (4 POSTs, 2 reads, 1 status)

| Step | Route | HTTP | Result |
|------|-------|------|--------|
| m_code | tool `execute_revit_code` -> `/execute_code/` (authenticated) | text only | `Error: 423 - {"error": "Mutation rejected: Revit extension files differ from the published manifest. Reinstall the extension from the share and restart Revit.", "files": ["revit_mcp/_zz_probe.py", "revit_mcp/detail.py"], "integrity": "verified_mismatch"}` plus the `Verified Revit process: PID 19132; Revit 2024; port 48884; session ...` trailer |
| m_create | tool `create_level` -> `/create_level/` (authenticated) | text only | the same 423 text naming both files |
| n_missing | direct `/create_level/`, no `_mcp` | 401 | `auth: missing`, "Mutation rejected: shared secret missing", no `outcome` (secret is checked before integrity) |
| p_levels | direct `GET /list_levels/` | 200 | `success`, 6 levels |
| r_levels_open | direct `POST /document_levels/` with the document selector, no secret | 200 | `success`, 6 levels, `ui_switched false`, `target_is_active true`, `active_before` equals `active_after` (`doc1.b020463cd5cd.1`) |
| s_status | tool `get_revit_status` -> `/status/` | 200 | `active`, health `degraded`, integrity `verified_mismatch` naming `detail.py` as modified and `_zz_probe.py` as unexpected, secret configured (fingerprint `6b6cfa6a`), security alert present |

The 6 levels in both reads were the same: Основание B.O. (-4600 mm), Основание T.O. (-4300), Плита T.O. (-4000), Фунд. стена T.O. (-300), Уровень 1 (0), Уровень 2 (4000). No `P5_*` level is among them: the blocked level `P5_M_CREATE_20261024T190803` was never created, and neither was `P5_N_MISSING_...` or the other seed names.

Truths covered: integrity named both files after one full restart (INTG-02, INTG-05); authenticated tool mutations and `/execute_code/` refused with 423 naming both files (INTG-04, D-04); unauthenticated mutation still 401; reads and `/status/` keep working (SEC-05, ROADMAP criterion 2).

## MCP read after the script (orchestrator, read only, verbatim)

```
Status: active | Health: degraded | API: genpro_revit_mcp | Document: Проект1 | Bind: loopback_only | Domains Registered: 24 | Integrity: {'modified': ['revit_mcp/detail.py'], 'unexpected': ['revit_mcp/_zz_probe.py'], 'state': 'verified_mismatch', 'missing': [], 'reason': None} | Process Identity: {'revit_version': '2024', 'pid': 19132, 'actual_port': 48884} | Secret: {'configured': True, 'fingerprint': '6b6cfa6a'} | Security Alerts: ['The extension files differ from the published manifest (revit_mcp/_zz_probe.py, revit_mcp/detail.py): every mutation is refused with 423 until the extension is reinstalled and Revit is fully restarted.'] | Shared secret: both halves hold the same secret (fingerprint 6b6cfa6a). | MCP target: 127.0.0.1:48884. (MCP-session server origin: the text carries the Phase 5 comparison line, so the session bridge is current.)
```

## INTG-03: the extension wrote nothing while loaded

Taken with the tree still corrupted, after the run:

`git status --porcelain -- revit_mcp startup.py extension.json`
```
 M revit_mcp/detail.py
?? revit_mcp/_zz_probe.py
```

`git status --porcelain --ignored -- _manifest.json revit_mcp`
```
 M revit_mcp/detail.py
?? revit_mcp/_zz_probe.py
!! _manifest.json
!! revit_mcp/__pycache__/
!! revit_mcp/_bridge_secret
```

Only the two deliberate corruptions plus ignored `_manifest.json`, `_bridge_secret` and `__pycache__` appear. No other finding.

## Restore and suite

`uv run python tests/test_phase5_live_gate.py restore --module revit_mcp/detail.py` (exit 0):

```
RESTORED clean
```

After restore:

- `git status --porcelain -- revit_mcp/detail.py revit_mcp/_zz_probe.py _manifest.json`: empty.
- `git status --porcelain --ignored -- _manifest.json revit_mcp/_zz_probe.py`: empty (so `_manifest.json` and the probe are gone).
- `uv run pytest tests/unit -q`: `5884 passed, 3 skipped in 71.57s (0:01:11)`. Zero failures, zero errors. The suite was run only after the restore.

## State left behind (important for 05-15)

- **The running Revit (PID 19132) STILL holds the corrupted integrity state.** It read the corrupted tree at its start and checks once at load, so every mutation it receives returns 423 and `/status/` still shows `verified_mismatch` and `degraded`, even though the files on disk are now clean. Only a full Revit restart by the user clears it. That restart is the first step of plan 05-15.
- `_manifest.json` was removed by restore, so the junction is back to its normal manifest-free state (the integrity check reports `unverifiable` and blocks nothing). Plan 05-15 starts from a restored junction with no manifest, which is consistent with its design.
- `revit_mcp/_bridge_secret` is unchanged (ignored by git).
- Nothing was started, stopped, reloaded, saved or opened in Revit by this plan's executors.

## Deviations from Plan

None. The stage ran once, first attempt, and the verdict was PASS. One note on evidence: the Task 1 console transcript is reported as its three tokens (`INTEGRITY verified_mismatch`, `MODIFIED revit_mcp/detail.py`, `UNEXPECTED revit_mcp/_zz_probe.py`) from the orchestrator, because the tree was already restored when this SUMMARY was written and the command could not be reproduced.

## Known Stubs

None.

## Threat Flags

None. No file was created or modified in the repository other than this SUMMARY.

## Self-Check: PASSED

- `C:/Temp/phase5/S2-corrupt.json` exists; classify prints PHASE5_GATE_OK; scan-secret prints SECRET_ABSENT.
- Restore printed `RESTORED clean`; the pathspec status checks are empty.
- Unit suite: 5884 passed, 3 skipped.
- `git rev-list --count f9296805bbc6d470313b74395210c3da4d5f97d0..HEAD` was 0 before this SUMMARY (no code changes, none expected).
