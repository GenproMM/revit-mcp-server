---
phase: 05-live-secret-gate-and-integrity-enforcement
plan: 13
subsystem: phase-5-live-gate
tags: [live-gate, secret, integrity, match-stage]
status: gap-found
plan_head_before: 118fc3c9b4898d6302081303a6b0c29c97d0633e
commits: 0
actuals:
  tokens: 0
  tasks: 2
  commits: 0
completed: 2026-10-24
---

# Plan 05-13 Summary: live match stage (verdict PHASE5_GATE_STOP, gap recorded)

**The match stage ran against one real Revit 2024 with one throwaway project. The secret gate behaved correctly on the wire (missing and wrong secret refused with 401, matching secret created a level), but the tested classifier returned PHASE5_GATE_STOP with three reasons that point at defects in the gate script's own step design and parsing, not at the product. The plan is NOT marked complete; 05-14 must not start.**

## Verdict

```
PHASE5_GATE_STOP
STAGE=match
POSTS_SENT=7
REASON=steps.r_levels_open.http: expected 200
REASON=steps.r_levels_wrong.http: expected 200
REASON=steps.b_wrong.text: expected Error: 401 - mismatch
This stage is consumed and must not be run again.
```

The match stage is consumed (POSTS_SENT=7). It was not rerun.

## Task results

| Task | Result |
|------|--------|
| 1 Preconditions and temporary manifest | Done earlier (no commit): git-ignored `_manifest.json` (34 files, 118fc3c9b489), `revit_mcp/_bridge_secret` created, `INTEGRITY verified_match`, unit suite green. |
| 2 User restarts Revit, opens one project | User replied "ready" (one listener row, 127.0.0.1:48884, Revit PID 29620). |
| 3 Match stage | Attempt 1: preflight stop, POSTS_SENT=0. Attempt 2 (after the user opened a project): ran, POSTS_SENT=7, PHASE5_GATE_STOP. |

## Console output of every run

### Run 1, `--out C:/Temp/phase5/S1-match.json` (summarised from the prior agent's report)

Preflight stop, no document was open (Revit Home screen; `/documents/` empty, `/status/` 503).
`PHASE5_GATE_STOP`, `POSTS_SENT=0`, `stop_reason "GET /status/ did not return 200"`.
Preflight facts recorded in the file: secret configured, fingerprints equal (`6b6cfa6a`), integrity `verified_match`, bind `loopback_only`, health `healthy`, 24 domains, one listener (PID 29620).

### Run 2, `uv run python tests/test_phase5_live_gate.py run --stage match --out C:/Temp/phase5/S1-match-2.json` (verbatim, exit 1)

```
PHASE5_GATE_STOP
STAGE=match
POSTS_SENT=7
REASON=steps.r_levels_open.http: expected 200
REASON=steps.r_levels_wrong.http: expected 200
REASON=steps.b_wrong.text: expected Error: 401 - mismatch
This stage is consumed and must not be run again.
```

### Classify, `classify --stage match C:/Temp/phase5/S1-match-2.json` (exit 1)

Same five lines as above (token, STAGE, POSTS_SENT, the three REASON lines). The plan's verify command named `S1-match.json`; that file is the POSTS_SENT=0 preflight record and was classified by the prior agent as a stop. The authoritative record is `S1-match-2.json`.

### scan-secret

```
scan-secret C:/Temp/phase5/S1-match-2.json  -> SECRET_ABSENT (exit 0)
scan-secret C:/Temp/phase5/S1-match.json    -> SECRET_ABSENT (exit 0)
```

### restore (no `--module`)

```
RESTORED clean
```
Exit 0. The temporary `_manifest.json` is now removed (`ls` confirms it is gone). `revit_mcp/_bridge_secret` is left in place (git-ignored, developer secret, created once by design).

## Record paths and listener checks

- `C:/Temp/phase5/S1-match.json` (POSTS_SENT=0, no document open).
- `C:/Temp/phase5/S1-match-2.json` (POSTS_SENT=7, authoritative). Both are outside the repository.
- Listener check before the run (executed by me): `Get-NetTCPConnection -LocalPort 48884 -State Listen` gave exactly one row, `127.0.0.1:48884`, OwningProcess 29620.
- Document check before the run (executed by me): `GET /documents/` returned `count: 1`, title "Проект1", `saved: false`, `path: ""`, document `doc1.9b96d960df03.1`, Revit 2024, PID 29620, port 48884, session `f4d0e0e0-3f41-4200-9af7-716667cb1b4f`.
- The script's own preflight in run 2 agreed: listeners `[29620]`, `documents: 1`, `status_http: 200`, bridge fingerprint `6b6cfa6a`.

## What the record shows (7 POSTs)

| Step | Route | Result |
|------|-------|--------|
| n_missing | `/create_level/` direct, no `_mcp` | 401, `auth: missing`, "shared secret missing" (correct refusal) |
| n_mismatch | `/create_level/` direct, wrong secret | 401, `auth: mismatch` (correct refusal) |
| n_code | `/execute_code/` direct, no `_mcp` | 401, `auth: missing` (correct refusal) |
| r_levels_open | `/document_levels/` direct, body `{}` | HTTP 400, `error_code: document-selector-required` |
| r_levels_wrong | `/document_levels/` direct, wrong secret | HTTP 400, same `document-selector-required` body (wrong secret did not produce 401: open POST read ignores the envelope, as designed) |
| b_wrong | `create_level` tool with a wrong secret | text `Error: 401 - {"error": "Mutation rejected: shared secret mismatch", "auth": "mismatch", ...}` followed by a second line `Verified Revit process: PID 29620; Revit 2024; port 48884; session f4d0e0e0-...` |
| p_create | `create_level` tool, matching secret | 200, `Created 1 level(s)`, id 286663, name `P5_P_CREATE_20261024T184804`, elevation 1400 mm, transaction `Committed` |
| p_levels | `/list_levels/` direct | 200, 3 levels, includes `P5_P_CREATE_20261024T184804` (id 286663) |
| s_status | `get_revit_status` tool | recorded (see record); classifier raised no reason for it |

Criterion 1 (a matching secret mutates) and the refusal half of criterion 3 (missing and mismatched secrets are refused with 401 before any document access) are evidenced on the wire. The three stop reasons are all about steps the script itself designed:

## Gaps (the three STOP reasons)

1. **`steps.r_levels_open.http` and `steps.r_levels_wrong.http` (script defect).** `tests/test_phase5_live_gate.py` line ~561-562 POSTs `/document_levels/` with `{}` and `{"_mcp": {...}}` and the classifier demands HTTP 200. The real route requires a `document` selector when it is not given ("A read never chooses a default"; Phase 2 invariant) and answers 400 `document-selector-required`, listing exactly one candidate (`doc1.9b96d960df03.1`). The read route is open and reached its selector validation, so the evidence that matters (an open POST read is not gated by the secret) is present, but the step's body should carry `{"document": "<id from /documents/>"}` and the offline fake in `tests/unit/test_phase5_live_gate.py` apparently modelled a 200 for an empty body. The same defect exists in the `corrupt` stage (`r_levels_open`, line ~575, and the check at line ~263), so that stage would also stop on it.
2. **`steps.b_wrong.text` (classifier parse defect).** `_error_body(text, 401)` (line 73-81) does `json.loads(text[len(prefix):])`, but the model-visible tool text carries a trailing `\nVerified Revit process: ...` line (Phase 2 process-identity footer) so the JSON parse fails and the step is classed as wrong although the text starts with `Error: 401 - ` and states `auth: mismatch`. The helper must parse only the first line (or the first JSON object).

None of the three points at a product defect in the gate, the integrity check or the tools. They are defects in the 05-12 script/test pair (offline fakes did not reproduce the real `/document_levels/` 400 or the identity footer). A script fix plus a new live run needs a fresh stage; the match stage's one-shot rule means the user decides how to re-run (the stage is consumed in this record, not in the product).

## MCP corroboration (not performed)

The live rules required `get_revit_status` and `list_levels` through the session's `revit` MCP tools after the script exited. This executor session had no revit MCP tool available (only file/shell/skill tools; no deferred-tool search surfaced them), so those two calls were NOT made and no MCP text is recorded. MCP server origin (plan step 6): not reported by the user, and nothing could be inferred from MCP read texts because none were obtained. The script's own tool steps (`b_wrong`, `p_create`, `s_status`) exercised the production tools through the injected bridge and are the only tool-level evidence.

As a clearly labelled substitute (a plain read-only GET, not an MCP call) I fetched `GET /genpro_revit_mcp/status/` after the run: `status active`, `health healthy`, `bind loopback_only`, `secret {configured: true, fingerprint: 6b6cfa6a}`, `integrity.state verified_match` (no modified/missing/unexpected), `domains_registered 24`, PID 29620, session `f4d0e0e0-...`. No secret value appears in any of these texts.

## Side effects left in the throwaway project

`P5_P_CREATE_20261024T184804` (id 286663, 1400 mm) was created in the unsaved project "Проект1" by design. Nothing was saved; Revit was not restarted, pyRevit not reloaded, no other model opened. It disappears when the throwaway project is closed unsaved.

## Deviations from Plan

- [Process] The plan's verify `classify` names `S1-match.json`; the real evidence is `S1-match-2.json` because attempt 1 stopped in preflight (POSTS_SENT=0), which the plan itself anticipates.
- [Process] MCP corroboration not done (tools unavailable to the executor), see above.
- No code, test or product file was changed by this plan.

## Known Stubs

None.

## Threat Flags

None. T-05-56: `scan-secret` returned `SECRET_ABSENT` for both records; this SUMMARY contains fingerprints only.

## State after this plan

- `_manifest.json` removed by `restore` (RESTORED clean). 05-14 needs it, but 05-14 is not to start; regenerate it with the plan 05-13 Task 1 procedure if the sequence is resumed.
- Phase 5 live sequence halted here for the user's decision: fix the two script defects (a `document` selector in the `/document_levels/` steps; first-line parse in `_error_body`) with matching offline tests, then re-run the match stage under a new decision.
- The plan is not marked complete in ROADMAP/STATE.

## Self-Check: PASSED

- `C:/Temp/phase5/S1-match.json` and `S1-match-2.json` exist; both `SECRET_ABSENT`.
- `restore` printed `RESTORED clean`; `_manifest.json` is absent.
- `commits: 0` measured against `plan_head_before` 118fc3c; no code changes (documentation-only plan outcome).
