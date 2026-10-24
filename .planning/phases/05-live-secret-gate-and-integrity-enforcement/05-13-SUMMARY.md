---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 13
subsystem: phase-5-live-gate
tags: [live-gate, secret, integrity, match-stage]
status: complete
plan_head_before: 118fc3c9b4898d6302081303a6b0c29c97d0633e
commits: 3
actuals:
  tokens: 0
  tasks: 3
  commits: 3
completed: 2026-10-24
---

# Plan 05-13 Summary: live match stage (verdict PHASE5_GATE_OK, PASS)

**The match stage passed on the third attempt: one real Revit 2024, one throwaway project, secret and integrity both matching. A missing or wrong secret is refused with 401 on every mutation path tried, a matching secret creates a level, the open POST read ignores the envelope as designed, and the model-visible tools agree. The two earlier attempts are kept below because the first stopped in preflight and the second stopped on two defects in the runner, not in the product.**

## Verdict (attempt 3, authoritative)

```
PHASE5_GATE_OK
STAGE=match
POSTS_SENT=7
This stage is consumed and must not be run again.
```

Record: `C:/Temp/phase5/S1-match-3.json` (outside the repository). Created level: `P5_P_CREATE_20261024T185550` (id 286664, 1400 mm, transaction `Committed`).

## History of the three attempts

| Attempt | Record | Outcome |
|---------|--------|---------|
| 1 | `S1-match.json` | Preflight STOP, `POSTS_SENT=0`: no document open (Revit Home screen, `/documents/` empty, `/status/` 503). Nothing was sent. |
| 2 | `S1-match-2.json` | `PHASE5_GATE_STOP`, `POSTS_SENT=7`, three REASON lines caused by two defects in the runner (details below). The product behaved correctly (401s, authenticated create committed). |
| 3 | `S1-match-3.json` | `PHASE5_GATE_OK`, `POSTS_SENT=7`, after the runner fix in commit `9aa9876`. |

**One-shot exception.** The match stage is one-shot by design (a write step must never repeat). Attempt 3 reran it only because the runner, not the product, had stopped attempt 2, and the user explicitly approved this single rerun ("go") as a documented exception, with a fresh `--out`. The stage is consumed again and must not be run a third time.

### Attempt 2: the two runner defects (fixed in `9aa9876`)

Console output of attempt 2 (verbatim, exit 1):

```
PHASE5_GATE_STOP
STAGE=match
POSTS_SENT=7
REASON=steps.r_levels_open.http: expected 200
REASON=steps.r_levels_wrong.http: expected 200
REASON=steps.b_wrong.text: expected Error: 401 - mismatch
This stage is consumed and must not be run again.
```

1. The `/document_levels/` steps (`r_levels_open`, `r_levels_wrong`) posted `{}` without a `document` selector. The real route requires one ("a read never chooses a default") and answered 400 `document-selector-required`. Fix: the steps now send the document selector read from `/documents/`.
2. `_error_body` parsed the whole tool text as JSON, but the model-visible text carries a trailing `Verified Revit process: ...` line, so the parse failed for `b_wrong`. Fix: it tolerates the trailer line.

Neither defect touched the gate, the integrity check or the tools.

## Task results

| Task | Result |
|------|--------|
| 1 Preconditions and temporary manifest | Done earlier; regenerated for attempt 3 (see below). `revit_mcp/_bridge_secret` is unchanged (the live Revit loaded it). |
| 2 User restarts Revit, opens one project | User replied "ready" (one listener, Revit PID 29620; project "Проект1" opened before attempt 2). |
| 3 Match stage | Attempt 3 PHASE5_GATE_OK, POSTS_SENT=7. |

## Console output of attempt 3 (verbatim)

### Manifest regeneration

```
WARNING: developer manifest written into the repository root; delete .\_manifest.json after the live check
MANIFEST written: .\_manifest.json (34 files, commit 9aa98764bea6)
INTEGRITY verified_match -
```

`git status --porcelain -- _manifest.json revit_mcp/_bridge_secret` printed nothing (both git-ignored). `dev_secret.py` was not rerun.

### Run, `uv run python tests/test_phase5_live_gate.py run --stage match --out C:/Temp/phase5/S1-match-3.json` (exit 0)

```
PHASE5_GATE_OK
STAGE=match
POSTS_SENT=7
This stage is consumed and must not be run again.
```

### Classify, `classify --stage match C:/Temp/phase5/S1-match-3.json` (exit 0)

```
PHASE5_GATE_OK
STAGE=match
POSTS_SENT=7
```

### scan-secret

```
scan-secret C:/Temp/phase5/S1-match-3.json  -> SECRET_ABSENT (exit 0)
```

For the earlier records: `S1-match.json` and `S1-match-2.json` were also `SECRET_ABSENT`. This SUMMARY contains fingerprints only.

## Listener and document checks (before attempt 3, run by the executor)

- `Get-NetTCPConnection -LocalPort 48884 -State Listen`: exactly one row, `127.0.0.1:48884`, State Listen, OwningProcess 29620.
- `GET /genpro_revit_mcp/documents/`: `status success`, `count 1`, title "Проект1", `active true`, `saved false`, `path ""`, document `doc1.9b96d960df03.1`, Revit 2024, PID 29620, port 48884, session `f4d0e0e0-3f41-4200-9af7-716667cb1b4f`.
- The orchestrator independently re-ran after the script: `classify` (PHASE5_GATE_OK, STAGE=match, POSTS_SENT=7), `scan-secret` (SECRET_ABSENT), `make_manifest --check` (INTEGRITY verified_match) and the listener count (1).

## What the record shows (attempt 3, 7 POSTs)

| Step | Route | Result |
|------|-------|--------|
| n_missing | `/create_level/` direct, no `_mcp` | 401, `auth: missing`, "Mutation rejected: shared secret missing" |
| n_mismatch | `/create_level/` direct, wrong secret | 401, `auth: mismatch`, "Mutation rejected: shared secret mismatch" |
| n_code | `/execute_code/` direct, no `_mcp` | 401, `auth: missing` |
| r_levels_open | `/document_levels/` direct, with document selector | 200, `active_before` equals `active_after` (`doc1.9b96d960df03.1`) |
| r_levels_wrong | `/document_levels/` direct, wrong secret, with selector | 200, same document identity (open POST read ignores the envelope, as designed) |
| b_wrong | `create_level` tool with a wrong secret | text `Error: 401 - {... "Mutation rejected: shared secret mismatch", "auth": "mismatch" ...}` (trailer line tolerated) |
| p_create | `create_level` tool, matching secret | 200, `Created 1 level(s)`, id 286664, `P5_P_CREATE_20261024T185550`, 1400 mm, `outcome.transaction_status` `Committed`, requested 1, succeeded [286664], failed [] |
| p_levels | `/list_levels/` direct | 200, 4 levels, includes both `P5_P_CREATE_*` levels |
| s_status | `get_revit_status` tool | health `healthy`, 24 domains, `integrity.state verified_match` (missing/modified/unexpected empty), PID 29620, port 48884 |

The rejected-name levels (`P5_N_MISSING_*`, `P5_N_MISMATCH_*`, `P5_M_CREATE_*`) were generated as inputs but never created; the refused calls changed nothing.

## MCP corroboration (D-13, by the orchestrator, after the script exited, reads only)

`get_revit_status` text (verbatim, no secret in it):

```
Status: active | Health: healthy | API: genpro_revit_mcp | Document: Проект1 | Revit Available: True | Bind: loopback_only | Domains Registered: 24 | Integrity: {'modified': [], 'unexpected': [], 'state': 'verified_match', 'missing': [], 'reason': None} | Process Identity: {'revit_version': '2024', 'pid': 29620, 'actual_port': 48884} | Secret: {'configured': True, 'fingerprint': '6b6cfa6a'} | Verified Revit process: PID 29620; Revit 2024; port 48884 | Shared secret: both halves hold the same secret (fingerprint 6b6cfa6a). | MCP target: 127.0.0.1:48884
```

`list_levels` text (as relayed by the orchestrator):

```
Total Levels: 4: 'Уровень 1' (id 311, 0 mm), 'P5_P_CREATE_20261024T184804' (id 286663, 1400 mm, from the consumed attempt 2), 'P5_P_CREATE_20261024T185550' (id 286664, 1400 mm, this run's authenticated create), 'Уровень 2' (id 694, 4000 mm). None of the rejected names (P5_N_MISSING_*, P5_N_MISMATCH_*, P5_M_CREATE_*) is listed. Process: PID 29620; Revit 2024; port 48884.
```

MCP server origin: not reported by the user. The MCP text contains the Phase 5 line "Shared secret: both halves hold the same secret", so the session server runs the current bridge from this repository, not a stale installed payload. This executor made no MCP call; the corroboration above came from the orchestrator's session.

## Side effects left in the throwaway project

Two test levels remain in the unsaved project "Проект1": `P5_P_CREATE_20261024T184804` (id 286663, attempt 2) and `P5_P_CREATE_20261024T185550` (id 286664, attempt 3), both 1400 mm. Nothing was saved; Revit was not restarted, pyRevit not reloaded, no other model opened. Both disappear when the throwaway project is closed unsaved.

## Deviations from Plan

- [Process] The runner needed two fixes (commit `9aa9876`, `fix(05-12)`) before the stage could return a verdict; the match stage was run a second time under the user-approved one-time exception described above.
- [Process] The plan's verify names `S1-match.json`; the authoritative record is `S1-match-3.json` (attempt 1 stopped in preflight, attempt 2 on runner defects).
- No product file was changed by this plan. The only code change was the runner fix `9aa9876`.

## Known Stubs

None.

## Threat Flags

None. T-05-56: `scan-secret` returned `SECRET_ABSENT` for every record.

## State after this plan

- The temporary `_manifest.json` is intentionally still present in the repository root (git-ignored) because plan 05-14 needs it. Until 05-15 the developer must not edit tracked files under `revit_mcp/`, `startup.py` or `extension.json`: any edit makes the manifest disagree with the tree and blocks the developer's own mutations (423).
- `revit_mcp/_bridge_secret` is unchanged and must stay so while this Revit session runs.
- 05-14 may start. Revit PID 29620 must not be restarted or reloaded before it.

## Self-Check: PASSED

- `C:/Temp/phase5/S1-match-3.json` exists; classify PHASE5_GATE_OK, scan-secret SECRET_ABSENT.
- `make_manifest --check` printed `INTEGRITY verified_match`; listener count 1.
- `commits: 3` measured against `plan_head_before` 118fc3c: `a92f675`, `9aa9876`, and this summary commit.
