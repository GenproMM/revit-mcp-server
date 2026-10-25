---
phase: 06-structured-audit-log-of-true-outcomes
verified: 2026-10-25T12:00:00Z
status: human_needed
score: 7/7 must-haves verified
covered_files:
  - .planning/REQUIREMENTS.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-01-PLAN.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-01-SUMMARY.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-02-PLAN.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-02-SUMMARY.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-03-PLAN.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-03-SUMMARY.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-04-PLAN.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-04-SUMMARY.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-05-PLAN.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-05-SUMMARY.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-06-PLAN.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-06-SUMMARY.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-07-PLAN.md
  - .planning/phases/06-structured-audit-log-of-true-outcomes/06-07-SUMMARY.md
  - audit.py
  - bridge.py
  - deploy/build-payload.cmd
  - main.py
  - tests/test_phase6_live_audit.py
  - tests/unit/audit_support.py
  - tests/unit/conftest.py
  - tools/utils.py
covered_digest: "v1:sha256:1a1df2637b200300b04f11ab345833cacc1c0c47a7c3dbed0d035a17d20ad3ed"
behavior_unverified: 0
overrides_applied: 0
gaps: []
review_warnings_carried:
  - id: WR-01
    summary: "A lone surrogate in any entry after the first of a segment drops that entry (UnicodeEncodeError in SegmentHandler.shouldRollover)"
    reproduced: true
  - id: WR-02
    summary: "A read answered HTTP 200 with a top-level status error / truthy error key is labelled outcome success"
    reproduced: true
  - id: WR-03
    summary: "NaN / Infinity in succeeded, failed.item or documents_changed fields are written as bare NaN / Infinity (invalid JSON for strict readers)"
    reproduced: true
human_verification:
  - test: "Decide whether ROADMAP criterion 3 (one correlation id across several underlying Revit operations) is accepted on offline evidence"
    expected: "tests/unit/test_audit_correlation.py runs a synthetic tool (read + mutation + image) through the real audit wrapper and the real bridge and gets three ordered entries with one call_id equal to the Audit line id. No shipped tool makes more than one bridge call (checked by AST over tools/*_tools.py), so a live demonstration is not possible today. Accept, or require a live proof when a multi-call tool exists."
    why_human: "The criterion's wording does not say 'with a synthetic tool'; whether a proof that cannot use a real multi-call tool satisfies it is a product decision, not a code fact."
  - test: "AUDIT-05 / AUDIT-06 edge probes the plans flagged as unresolved"
    expected: "Reviewer reads the 'Edge probe' items in 06-05-PLAN.md (stdout cleanliness of the audit writer, behaviour with two writers) against the evidence listed below and either accepts them or names a missing probe. Evidence already present: static no-print AST rows, a real main.py stdio session (only JSON-RPC on stdout), two real subprocess writers writing PID-named files, and live run-dual (two files, 20 POSTs, no corruption)."
    why_human: "The plans explicitly reserve these for human judgment."
  - test: "Does the assistant follow the user_request wording?"
    expected: "In a real session, a mutation made after a user message such as 'да' records the last substantive request, not 'да', in the entry's user_request. Entries show user_request_source 'assistant', unverified by design (D-12)."
    why_human: "Model behaviour against a published instruction cannot be asserted by a unit test. In the live runs the field was present (user_request_missing false) on every tool-driven mutation, but the script supplied the value, so this proves the plumbing, not the model."
  - test: "Accept or require a fix for the three code-review warnings (WR-01..WR-03) before the R4 release checkpoint"
    expected: "See 'Review warnings against success criteria' below. None contradicts a ROADMAP criterion as written; each is a small hardening fix in audit.py with a given patch in 06-REVIEW.md."
    why_human: "Whether a rare-input defect that can lose or mis-label an entry is acceptable for release is a risk decision."
---

# Phase 6: Structured audit log of true outcomes — Verification Report

**Phase Goal:** Every mutation is recorded in a local, structured, honest log, reflecting Phase 4's real per-element outcomes, not the request's stated intent, without becoming a second place the shared secret leaks.
**Verified:** 2026-10-25
**Status:** human_needed
**Re-verification:** No, initial verification

## Goal Achievement

The goal is achieved in the code and in the live record. Every ROADMAP criterion resolves to VERIFIED. The status is `human_needed`, not `passed`, because four items need a human decision (criterion 3's offline-only proof, the two flagged edge probes, model compliance with `user_request`, and acceptance of three reproduced review warnings). Nothing is FAILED, so there is no `gaps_found` blocker.

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Every mutation produces a JSONL entry with timestamp, tool, route, document/instance identity, affected elements, outcome | VERIFIED | `audit.build_entry` (audit.py:672-749) writes `ts`, `tool`, `route`, `process{pid,port,session_token,revit_version}`, `document{token,title,path}`, `succeeded/failed/requested` lists and `outcome`; `ALWAYS_PRESENT_FIELDS` pins them. Hooked from `bridge._dispatch` (bridge.py:1050) for every sent call, reads included with a `mutation` flag (D-02, wider than the criterion). Live: I read the single and dual audit files myself; every POST entry carries all of these fields. Not-sent calls write nothing by design. |
| 2 | A real rollback and a real partial batch each log that true outcome, confirmed live | VERIFIED | I parsed `audit-single/audit-20261025-112552-35144.jsonl`: `execute_revit_code` is `kind received, http 409, outcome rolled_back, transaction_status RolledBack`; `tag_elements` is `http 200, outcome partial, requested 2, succeeded_count 1, failed_count 1, failed [{item 999999999, reason "Element not found"}]`. Outcome comes from the reply body's own status in the fixed precedence of `_outcome` (audit.py:406-438), never from `format_response`. `classify` re-judged `single.json` as `PHASE6_AUDIT_OK` (sent nothing). Offline: outcome table through the real bridge in test_audit_bridge_hook.py. |
| 3 | One tool call spanning several Revit operations gives entries sharing one correlation id | VERIFIED (offline, synthetic tool) | `_CALL` contextvar set by the wrapper `audit._wrap` (audit.py:281-288); `revit_post` decides the `CallState` once and the same id goes into the `_mcp` envelope and the entry (bridge.py:854-864). `test_one_tool_call_with_three_bridge_calls_writes_three_entries_with_one_call_id`, ordering and concurrent-distinct-id rows pass in the full run. No shipped tool makes more than one bridge call (AST scan of `tools/*_tools.py` found none), so no live proof exists. Routed to a human decision, see item 1. |
| 4 | Nothing is written to stdout by the audit writer, confirmed with the stdio transport running | VERIFIED | `grep print(` in audit.py and bridge.py returns nothing. Only output paths are the log file and one stderr line (`_warn_once`, audit.py:772-781). Logger has `propagate = False` and one `QueueHandler`. `tests/unit/test_audit_stdio.py` runs the real `main.py` over stdio against a fake Revit and parses every stdout line as JSON-RPC; the 6 tests of stdio + payload files passed when I ran them. |
| 5 | Two Revit instances mutated at once do not interleave or corrupt either instance's entries, confirmed live | VERIFIED | Isolation is by construction: one file per server process (`audit-<UTC>-<pid>.jsonl`), one in-process queue writer per process. Live `dual.json`: I parsed both files, 14 and 10 whole JSON lines, every line valid, no cross entries, entries name both documents scratch1 and scratch2 and both Revit processes. `classify` re-judged `dual.json` as `PHASE6_AUDIT_OK`, POSTS_SENT=20. One caveat: the live design proves two server processes writing separate files, not two writers contending for one file; that case cannot arise by design, and a unit row (100 concurrent calls to two incarnations) covers the in-process side. |
| 6 | The file has a rotation or size cap from its first write | VERIFIED | `SegmentHandler` rolls forward at 10 MiB from the first line (an exact-cap line stays, one byte over rolls, an oversize line goes whole into a fresh segment), keeps 10 segments per process, and `prune()` runs at writer start by age (default 180 days) then total size (default 500 MiB). Rows `first_write`, `rotate`, `prune`, `reader`, `settings`, `startup` in test_audit_writer.py (42 rows) pass. |
| 7 | Grepping the log for the configured secret returns nothing across a request that included it, an auth failure, and an exception path | VERIFIED | Redaction is applied before every cut (`_cut`), over the whole entry (`redact`) and on the finished line (`serialize_entry`), raw and JSON-escaped. `test_audit_secret.py` has a nine-scenario row (success, 401, exception, truncation and others) with a byte grep of the file. Live: I read the real dev secret (43 chars, existence not printed) and counted occurrences, raw and escaped, in all four audit files and the three run records: 0 total; `_mcp` appears in none. The live runs had no 401 path; that part is offline only. |

**Score:** 7/7 truths verified (0 present but behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `audit.py` | Pure entry builder, wrapper, queue-backed segment writer, prune | VERIFIED | 1036 lines, substantive, no stubs, no debt markers; imported eagerly by `bridge.py:130` and `main.py:16` |
| `bridge.py` hook | `_audit`/`_dispatch`, `call_id` in envelope | VERIFIED | `_audit` is called on every sent call and on a cancelled send (outcome `unknown`/`no_reply`); never raises (D-18) |
| `main.py` | `install_audited_tools(mcp)` before `register_tools`; server instructions | VERIFIED | main.py:26, 31 |
| `tools/utils.py` | `Audit: call_id` line for mutations and non-success | VERIFIED | tools/utils.py:49-51 |
| `deploy/build-payload.cmd` | ships `audit.py` | VERIFIED | line 111; `test_payload_ships_root_modules.py` passes |
| `tests/test_phase6_live_audit.py` + unit helpers | live instrument and classifier | VERIFIED | `classify` runs offline and sends nothing; reproduced both verdicts |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `FastMCP.tool` | per-call state | `install_audited_tools` wraps `mcp.tool` | WIRED | all 59 tools gain exactly one optional `user_request`; `test_audit_registration.py` compares wrapped vs plain schema per tool |
| `revit_post` | audit entry and Revit body | one `CallState` into `with_envelope(call_id=)` and `_dispatch(call=)` | WIRED | the real Revit gate accepts and strips the extra `call_id` key (`test_the_real_gate_accepts_an_envelope_with_a_call_id_and_strips_it`); `revit_mcp/` unchanged since e81b68f |
| reply body | entry outcome | `_reply_body` parses the 4xx/5xx text body, so 409 `rolled_back` reaches `_outcome` | WIRED | live-confirmed by the 409 entry above |
| entry id | model reply | `provenance["audit_call_id"]` then `format_response` | WIRED | rule: mutation or non-success only (D-07) |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| audit entry | outcome, succeeded, failed, transaction_status | the live reply's `outcome` block, copied by `_outcome_fields` | Yes, shown by the live 409 and `partial` entries | FLOWING |
| audit entry | process, document | handshake provenance and reply descriptors | Yes, live entries name process and document | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Unit suite | `uv run pytest tests/unit -q` | 6297 passed, 3 skipped in 79 s | PASS |
| Cold start | `python tests/test_init_latency.py` | `INIT_LATENCY_S=0.959` (< 2.0) | PASS |
| Stdio and payload rows | `uv run pytest tests/unit/test_audit_stdio.py tests/unit/test_payload_ships_root_modules.py -q` | 6 passed | PASS |
| Re-judge live records, read-only | `classify single.json`, `classify dual.json` | `PHASE6_AUDIT_OK` (POSTS_SENT 3 and 20, SECRET_OCCURRENCES 0) | PASS |
| Secret grep over live files | my own raw + escaped count with the real secret | 0 occurrences in 7 files | PASS |
| `_outcome` table | direct calls | 409 rolled_back, 200 partial, 422 failed, 500 error as expected | PASS |

### Probe Execution

No phase-declared probes. Step 7c: SKIPPED. The live gate is a one-shot record and was not re-run, per the instructions.

### Requirements Coverage

Every ID appears in at least one PLAN `requirements:` field; none is orphaned in REQUIREMENTS.md (AUDIT-01..08 all map to Phase 6, all checked).

| Requirement | Source plans | Status | Evidence |
|-------------|--------------|--------|----------|
| AUDIT-01 JSONL log of mutations | 06-01, 06-02, 06-04, 06-06, 06-07 | SATISFIED | criterion 1; see WR-01 for a rare entry-loss input |
| AUDIT-02 time, tool, route, document identity, elements, outcome | 06-02, 06-03 | SATISFIED | schema 1, live entries |
| AUDIT-03 actual outcome, not intent | 06-02, 06-06, 06-07 | SATISFIED for mutations | live `rolled_back` and `partial`; WR-02 mislabels a failed read, see below |
| AUDIT-04 one call, shared id | 06-01, 06-04 | SATISFIED (offline) | criterion 3, human item 1 |
| AUDIT-05 stdout untouched | 06-01, 06-05 | SATISFIED | criterion 4; edge probe is human item 2 |
| AUDIT-06 safe with two Revit instances | 06-05, 06-06, 06-07 | SATISFIED | criterion 5; edge probe is human item 2 |
| AUDIT-07 bounded growth | 06-05 | SATISFIED | criterion 6 |
| AUDIT-08 no secret, no excess personal data | 06-03, 06-06, 06-07 | SATISFIED | criterion 7; only `DOMAIN\user`, tool arguments and the user's request are recorded, no computer name, address or session id of the MCP client |

### Review warnings against success criteria

I reproduced all three warnings from 06-REVIEW.md by running the code.

- **WR-01 (lone surrogate drops an entry).** Reproduced: after `{"a":"x"}`, the line `{"a":"lone\ud800"}` is dropped with `UnicodeEncodeError`, one stderr line is printed, and the next entry is written. This is a real hole in "every mutation is recorded" (AUDIT-01) for an unusual input: a lone surrogate in a Revit-sourced string, on a line that is not first in its segment. It does not contradict any criterion as tested, since no criterion or live run involves such input, and it is not silent (one stderr line per process). Not a blocker. Recommend the one-line fix (`encode("utf-8", "backslashreplace")`) plus a test.
- **WR-02 (failed read logged as success).** Reproduced: `_outcome("received", 200, {"status":"error",...}, mutation=False)` returns `success`. This does not break AUDIT-03 or criterion 2 for mutations: the same body on a mutating route yields `unrecognized` with `reply_status: "error"`, and `outcome_block_missing` is flagged, so a mutation is never recorded as a false success and a rollback or partial is never collapsed. It does mislabel reads (which D-02 chose to log beyond the criterion) and, for mutations, labels an error reply `unrecognized` rather than `error`. The spirit of "true outcome" is better served by the fix; the letter of AUDIT-03 (rollback is a rollback, a partial skip is a partial skip) holds. Not a blocker, but it should be fixed before readers rely on read-entry outcomes.
- **WR-03 (NaN/Infinity as invalid JSON).** Reproduced: `serialize_entry({"succeeded":[float("nan")]})` gives `{"succeeded":[NaN]}`. Python's `json` reads it; `jq` and `JSON.parse` do not. The affected fields hold element ids and flags that Revit does not realistically report as NaN. No criterion is contradicted; the log's own readers and `classify` work. Not a blocker; low priority hardening.

None of the three turns a must-have into FAILED; together they are the reason a human accept-or-fix decision is listed (item 4) rather than a silent pass.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (phase files) | n/a | TBD / FIXME / XXX | none | The only `XXX` hit is the pre-existing `\uXXXX` explanatory text at tools/utils.py:326, not a debt marker. No `print(` in audit.py or bridge.py. |
| audit.py | 807-812 | strict `encode` in `shouldRollover` | Warning | WR-01 |
| audit.py | 435-438 | read 200 with error body is success | Warning | WR-02 |
| audit.py | 399-403, 761 | non-finite float written as is | Warning | WR-03 |
| audit.py | 258-267 | JSON-looking `user_request` re-serialized, not verbatim | Info | review IN-01; labelled "as reported by the assistant" |

### Human Verification Required

#### 1. Criterion 3 on offline evidence

**Test:** Decide whether the synthetic multi-call tool proof is enough.
**Expected:** Accept the offline proof (three ordered entries, one `call_id`, equal to the Audit line id, also present in the POST envelope), or require a live proof once a real tool makes more than one bridge call.
**Why human:** No shipped tool spans two bridge calls, so the criterion cannot be shown on a real tool today; whether that satisfies the wording is a product call.

#### 2. AUDIT-05 and AUDIT-06 edge probes

**Test:** Review the plans' "edge probe, unresolved" items against the stdio-session test, the two-subprocess-writer test and live `run-dual`.
**Expected:** Accept, or name a missing probe.
**Why human:** The plans reserve these for human judgment.

#### 3. user_request compliance by the model

**Test:** In a real client session, give a mutating instruction, then answer a confirmation with "да"; read the newest entry.
**Expected:** `user_request` holds the last substantive request, with `user_request_source: "assistant"`.
**Why human:** It depends on the model, and the server can only label the value unverified.

#### 4. Accept or fix WR-01 to WR-03 before the R4 release checkpoint

**Test:** Read the reproduction results above and decide.
**Expected:** Either accept as known limitations, or add three small fixes in audit.py with tests.
**Why human:** Release-risk decision.

### Gaps Summary

No blocking gaps. All seven ROADMAP criteria and all eight AUDIT requirements are backed by code I read, a green full suite (6297 passed, 3 skipped), and live audit files that I parsed and grepped myself. The phase is held at `human_needed` for the four decisions above. One of them (criterion 3) is a limitation the plans and summaries disclose openly, not a hidden defect.

---

_Verified: 2026-10-25_
_Verifier: Claude (gsd-verifier)_
