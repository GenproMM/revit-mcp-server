---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 15
subsystem: phase-5-live-gate
tags: [live-gate, cleanup-stage, integrity, unverifiable, classify-phase, scan-secret]
status: complete
plan_head_before: 58c0455
commits: 1
actuals:
  tokens: 0
  tasks: 3
  commits: 1
requirements-completed: [INTG-07, INTG-08, SEC-01, SEC-05, SEC-06]
completed: 2026-10-24
---

# Plan 05-15 Summary: live cleanup stage and phase verdict (PHASE5_GATE_OK, PASS)

**On a freshly restarted Revit 2024 with the restored developer junction (no manifest), the extension reported integrity `unverifiable` / `manifest_missing` with health `healthy`, no security alert and the same secret fingerprint on both halves, and an authenticated `create_level` still committed and was listed. The three live stages together classify as `PHASE5_GATE_OK`, no record holds the secret, and the verdicts are recorded in `05-VALIDATION.md`.**

`commits: 1` is the measured count before this SUMMARY (`58c0455..HEAD`): the `05-VALIDATION.md` commit `f1f1cdf`. This SUMMARY is committed separately afterwards. The plan changed no code.

## Verdict

```
PHASE5_GATE_OK
STAGE=cleanup
POSTS_SENT=1
This stage is consumed and must not be run again.
```

Record: `C:/Temp/phase5/S3-cleanup.json` (outside the repository). The stage ran exactly once, at the first attempt.

## Task results

| Task | Result |
|------|--------|
| 1 Offline check before the last restart | Done by the orchestrator: `deploy/make_manifest.py --check --dest .` printed `INTEGRITY unverifiable manifest_missing` (exit 1, expected); `git status --porcelain -- revit_mcp/detail.py revit_mcp/_zz_probe.py _manifest.json` printed nothing. |
| 2 User restarts Revit | The user fully restarted Revit, opened one new unsaved project and replied "ready" with one listener row (127.0.0.1:48884, Listen). |
| 3 Cleanup stage, classify-phase, scan-secret, validation file | Run once: PHASE5_GATE_OK. classify-phase PHASE5_GATE_OK, scan-secret SECRET_ABSENT, unit suite green, `05-VALIDATION.md` committed. |

## Listener and document checks (before the run, by the executor)

- `Get-NetTCPConnection -LocalPort 48884 -State Listen`: exactly one row, `127.0.0.1:48884`, State Listen.
- `GET /genpro_revit_mcp/status/`: HTTP 200, `health` `healthy`, `integrity` `unverifiable` with reason `manifest_missing` (modified, unexpected and missing empty), `bind` `loopback_only`, `domains_registered` 24, Revit 2024, secret configured with fingerprint `6b6cfa6a`, no `security_alerts` key.
- `GET /genpro_revit_mcp/documents/`: HTTP 200, `count 1`, title "Проект1", `active true`, `saved false`, `path ""`.

## Console output (verbatim)

### Run, `uv run python tests/test_phase5_live_gate.py run --stage cleanup --module revit_mcp/detail.py --out C:/Temp/phase5/S3-cleanup.json` (exit 0)

```
PHASE5_GATE_OK
STAGE=cleanup
POSTS_SENT=1
This stage is consumed and must not be run again.
```

### Classify, `classify --stage cleanup C:/Temp/phase5/S3-cleanup.json` (exit 0)

```
PHASE5_GATE_OK
STAGE=cleanup
POSTS_SENT=1
```

### scan-secret over the cleanup record (exit 0)

```
SECRET_ABSENT
```

### classify-phase, `classify-phase C:/Temp/phase5/S1-match-3.json C:/Temp/phase5/S2-corrupt.json C:/Temp/phase5/S3-cleanup.json` (exit 0)

```
PHASE5_GATE_OK
STAGE=match VERDICT=ok POSTS_SENT=7
STAGE=corrupt VERDICT=ok POSTS_SENT=4
STAGE=cleanup VERDICT=ok POSTS_SENT=1
```

### scan-secret over every record (each exit 0)

```
S1-match-3.json  -> SECRET_ABSENT
S2-corrupt.json  -> SECRET_ABSENT
S3-cleanup.json  -> SECRET_ABSENT
S1-match.json    -> SECRET_ABSENT   (superseded record, scanned for the record)
S1-match-2.json  -> SECRET_ABSENT   (superseded record, scanned for the record)
```

### Unit suite, `uv run pytest tests/unit -q`

```
5884 passed, 3 skipped in 67.09s (0:01:07)
```

### `git status --porcelain -- revit_mcp startup.py extension.json _manifest.json` after the run

Empty.

## What the record shows (1 POST, 1 read, 1 status)

| Step | Route | HTTP | Result |
|------|-------|------|--------|
| p_create | tool `create_level` -> `/create_level/` (authenticated) | 200 | `Created 1 level(s)`, level `P5_P_CREATE_20261024T203317` (id 279311, 1700 mm), `outcome.transaction_status` `Committed`, requested 1, succeeded [279311], failed [] |
| p_levels | direct `GET /list_levels/` | 200 | `success`, 7 levels; the created level is listed with 1700 mm |
| s_status | tool `get_revit_status` -> `/status/` | 200 | `active`, health `healthy`, integrity `unverifiable` / `manifest_missing`, secret configured (fingerprint `6b6cfa6a`), no security alert, shared-secret comparison line present |

Truths covered: with no manifest the developer junction blocks nothing (INTG-07, INTG-08; D-11) while the secret gate stays on (the write carried the matching secret, SEC-01); `/status/` and reads answered (SEC-05); no record contains the secret (SEC-06).

## MCP read after the script (orchestrator, read only, as relayed)

`get_revit_status` text: Status active | Health healthy | Document Проект1 | Bind loopback_only | Domains Registered 24 | Integrity `{'modified': [], 'unexpected': [], 'state': 'unverifiable', 'missing': [], 'reason': 'manifest_missing'}` | Secret `{'configured': True, 'fingerprint': '6b6cfa6a'}` | no Security Alerts line | "Shared secret: both halves hold the same secret (fingerprint 6b6cfa6a)." | MCP target 127.0.0.1:48884. The process id and session token were deliberately not recorded. This executor made no MCP call.

## 05-VALIDATION.md

Commit `f1f1cdf` (`docs(05-15): record live gate verdicts`) changed only `05-VALIDATION.md`: the Manual-Only rows L1, L2 and L3 now carry verdict, POSTS_SENT, date, listener-check result, fingerprint equality and record path; the live rows of the Per-Task map are green on PHASE5_GATE_OK; and a "Live gate phase verdict" block plus a "Gaps and history" note were added. `grep -c "PHASE5_GATE_"` prints 8 (needed: at least 3). No process ids, session tokens or secret material were written.

## Superseded match records (history)

`S1-match.json` stopped in preflight (`POSTS_SENT=0`, no document open). `S1-match-2.json` stopped on two defects in the live runner (`POSTS_SENT=7`), fixed in commit `9aa9876`. `S1-match-3.json` reran the stage under a user-approved one-time exception and is the authoritative L1 record. The plan's verify command and the validation map name `S1-match.json`; the real record path `S1-match-3.json` was used for `classify-phase`.

## Side effects left in the throwaway project

The unsaved project "Проект1" still holds the cleanup-stage test level `P5_P_CREATE_20261024T203317` (id 279311, 1700 mm). It disappears when the project is closed unsaved. Nothing was saved; Revit was not restarted, reloaded or otherwise touched by the executors in this plan.

## Developer junction state

The junction has no `_manifest.json` and no leftover `revit_mcp/_zz_probe.py`; `git status` is empty for `revit_mcp`, `startup.py`, `extension.json` and `_manifest.json`. `revit_mcp/_bridge_secret` is unchanged and ignored by git.

## Deviations from Plan

- [Process] Verify and map rows named `S1-match.json`; `S1-match-3.json` is the authoritative match record (see above). The map rows' automated commands in `05-VALIDATION.md` were updated to the real paths.
- [Process] The plan marked Task 3 as one executor flow; it was split into two steps (stage run and evidence, then validation file and SUMMARY) because the orchestrator performed the MCP read between them.
- No code was changed.

## Known Stubs

None.

## Threat Flags

None. T-05-62: one listener, one new unsaved project, one write. T-05-63: only verdicts, counts, dates, check results, fingerprint equality and paths in `05-VALIDATION.md`. T-05-64: `scan-secret` returned `SECRET_ABSENT` for all five records.

## Self-Check: PASSED

- `C:/Temp/phase5/S3-cleanup.json` exists; classify PHASE5_GATE_OK; scan-secret SECRET_ABSENT.
- Commit `f1f1cdf` exists and lists only `05-VALIDATION.md`.
- `classify-phase` PHASE5_GATE_OK; unit suite 5884 passed, 3 skipped.
