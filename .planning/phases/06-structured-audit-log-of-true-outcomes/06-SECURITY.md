---
phase: "06"
slug: "structured-audit-log-of-true-outcomes"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-25"
---

# Phase 06 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| MCP client -> tool wrapper / published schema | the model supplies tool arguments and the injected `user_request`; every client learns the new parameter from the schema | tool arguments, free text, possibly pasted secret or personal data |
| MCP server process -> local filesystem | entries leave the process into `%LOCALAPPDATA%\RevitMCP\audit` (or `REVIT_MCP_AUDIT_DIR`); the writer creates, rotates and deletes files | audit entries (JSONL) |
| MCP server process -> stdout | stdout is the stdio protocol stream; any stray byte corrupts the session | JSON-RPC only |
| Revit reply body -> entry builder | route-supplied keys (status, outcome, document, error_code, failure text) are copied into the log | reply fields, never read data or message text |
| bridge provenance -> entry builder | only the bridge decides kind and process; the reply cannot forge it | request provenance |
| MCP server -> pyRevit Routes (POST envelope) | `call_id` joins the secret in the reserved `_mcp` envelope | shared secret, call_id |
| concurrent MCP requests inside one server process | each request runs in its own task with its own contextvar state | call_id |
| two server processes -> one audit directory | concurrent writers and pruners share the directory, never a file | audit files |
| live runner / operator -> real Revit instances | write steps change scratch models on the engineer's bench | test mutations |
| live runner -> local disk; validation file -> repository | records hold ports, ids, paths and user names; recorded verdicts are committed | verdicts and counts only |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-06-01 | Denial of service | audit writer output path (stdout) | high | mitigate | audit.py `_writer`: logger propagate False, one QueueHandler; no print/stdout in audit.py or bridge.py; test_audit_stdio.py static and logger rows | closed |
| T-06-02 | Information disclosure | secret text inside an entry | high | mitigate | audit.py `serialize_entry` replaces raw and JSON-escaped secret on the finished line; `redact_text`; test_audit_secret.py (9 scenarios) | closed |
| T-06-03 | Denial of service | writer exception reaching a tool call | medium | mitigate | `record_call` and `bridge._audit` swallow every exception; test_audit_writer.py `test_never_breaks_*` | closed |
| T-06-04 | Information disclosure | `logging.Handler.handleError` default | medium | mitigate | both handlers override `handleError` to `_warn_once` (exception class only, once per process) | closed |
| T-06-05 | Tampering | log forging via newlines/quotes | medium | mitigate | one `json.dumps` per entry; control characters escaped; newline and CR rows | closed |
| T-06-06 | Denial of service | payload built without audit.py | medium | mitigate | `build-payload.cmd:111` copy line, eager `import audit` in bridge.py, transitive payload test, gate.py | closed |
| T-06-07 | Tampering | wrapper changing tool parameters | medium | mitigate | `__signature__` = original parameters plus keyword-only `user_request`; test_audit_registration.py asserts `FAILED == {}` over the manifest | closed |
| T-06-SC | Tampering | package installs | low | accept | stdlib plus mcp and pydantic already in uv.lock; no package installed (see Accepted Risks) | closed |
| T-06-08 | Repudiation | outcome label | high | mitigate | audit.py `_outcome` fixed precedence; unknown/unrecognized never read as success; 21 outcome rows plus bridge rows. Caveat: see AR-05 (WR-02) for non-mutating 200 replies | closed |
| T-06-09 | Repudiation | process and document attribution | medium | mitigate | process only from provenance kind "received"; document from reply first, lesser sources labelled; `execute_code` always "addressed" | closed |
| T-06-10 | Information disclosure | reply data entering the log | medium | mitigate | `_outcome_fields` / `_triplet` copy named keys only; read results, messages and 423 file lists never copied | closed |
| T-06-11 | Denial of service | oversized succeeded/failed lists | low | mitigate | caps 500 / 100 / 50 / 20 with true totals in count fields | closed |
| T-06-12 | Repudiation | sent POST cancelled by the client | medium | mitigate | `bridge._dispatch` catches CancelledError after send, writes unknown with `cancelled: true`, re-raises | closed |
| T-06-13 | Information disclosure | secret in args, user_request, code, reply strings | high | mitigate | redact before every cut, structural pass, key scrub, final pass on the serialized line; test_audit_secret.py incl. straddled cut | closed |
| T-06-14 | Information disclosure | writer failure path printing the entry | medium | mitigate | `_warn_once` writes class name only; stderr row asserts secret absent | closed |
| T-06-15 | Information disclosure | excess personal data | medium | mitigate | only `windows_user` collected; schema rows pin the key set | closed |
| T-06-16 | Spoofing | model reports a false user_request | low | accept | recorded as `user_request_source: "assistant"`, unverified by design (D-12) (see Accepted Risks) | closed |
| T-06-17 | Denial of service | huge arguments or code inflating entries | low | mitigate | code-point caps 500 / 200 items / 2000 / 8192 with recorded true lengths; code recorded as length plus sha256 | closed |
| T-06-18 | Denial of service | Revit gate rejecting an envelope with an extra key | high | mitigate | `with_envelope` adds `call_id` inside `_mcp`; `trust.split_envelope` strips the whole key; real-gate rows in test_audit_correlation.py | closed |
| T-06-19 | Spoofing | model pre-seeding `_mcp.call_id` | medium | mitigate | `with_envelope` refuses data already holding `_mcp`; call_id only from `audit.current_call()` | closed |
| T-06-20 | Repudiation | call_id cross-wired between concurrent calls | medium | mitigate | contextvar set/reset per tool call; concurrency row asserts distinct ids | closed |
| T-06-21 | Denial of service | JSON-looking `user_request` failing validation | medium | mitigate | `_json_text` BeforeValidator; rows for `{"a":1}`, `[1,2]`, `42`, `null` | closed |
| T-06-22 | Tampering | wrapper changing other parameters of the 59 tools | medium | mitigate | wrapped vs plain schema comparison over the whole manifest | closed |
| T-06-23 | Denial of service | disk fill by unbounded logs | high | mitigate | segment cap from first write, keep 10, start-up prune by age then size, bounded queue | closed |
| T-06-24 | Tampering | prune deleting files it does not own | high | mitigate | `prune`: no recursion, `audit-*.jsonl` only, symlinks skipped, regular files only; foreign-file and symlink rows | closed |
| T-06-25 | Denial of service | stray stdout bytes corrupting the stdio session | high | mitigate | AST rows over audit.py and bridge.py; real `main.py` subprocess session parsed as pure JSON-RPC | closed |
| T-06-26 | Repudiation | records dropped while a reader holds the file | medium | mitigate | roll-forward handler never renames; held-reader row. Residual: WR-01 (AR-04) | closed |
| T-06-27 | Tampering | two server processes interleaving in one file | medium | mitigate | file name carries UTC timestamp and PID; two-subprocess row | closed |
| T-06-28 | Information disclosure | log placed where other users can read it | medium | mitigate | default per-user `%LOCALAPPDATA%` directory, no ACL change; default-directory rows | closed |
| T-06-29 | Information disclosure | secret in the live-run record or console | high | mitigate | secret read only via `bridge._secret()` for the count; only `SECRET_OCCURRENCES=<n>` printed; live runs reported 0 | closed |
| T-06-30 | Tampering | a write step repeated on the model | medium | mitigate | `posts_sent` counted before each call; records opened with mode "x"; existing `--out` refused | closed |
| T-06-31 | Information disclosure | record or audit dir inside the repository | medium | mitigate | `--out` and `--audit-dir` refused inside the repository before any request | closed |
| T-06-32 | Tampering | a write to the wrong Revit instance | medium | mitigate | preflight requires exactly one listener (single) or two distinct usable targets (dual); every write names its selector | closed |
| T-06-33 | Denial of service | a rehearsal that commits real changes | low | mitigate | rehearse reports `REHEARSAL_COMMITTED` and is not a pass; live run gave `REHEARSAL_ROLLED_BACK` | closed |
| T-06-34 | Tampering | writes landing on the wrong Revit or a production model | high | mitigate | script preflights and allow-lists; no save/open route named; scratch non-workshared copies via `open_model`, never saved (procedure-attested, see 06-VALIDATION.md) | closed |
| T-06-35 | Denial of service | Revit crash from pyRevit Reload, or workset dialog | medium | mitigate | full close and clean start; models opened through `open_model`; instances stopped by exact PID | closed |
| T-06-36 | Information disclosure | PIDs, tokens or the secret in the validation file | medium | mitigate | only verdicts, counts, dates and record paths written; scan found no PID, token or secret | closed |
| T-06-37 | Denial of service | every mutation answering 423 from a leftover manifest | medium | mitigate | pre-gate check for `_manifest.json` at the repository root; none present on re-check | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-06-SC | No package is installed by this phase; stdlib plus mcp and pydantic already locked in uv.lock | phase plan 06-01 | 2026-10-25 |
| AR-02 | T-06-16 | `user_request` is the model's own report, recorded as `user_request_source: "assistant"` and never presented as proof (D-12) | phase plan 06-03 | 2026-10-25 |
| AR-03 | T-06-05 (WR-03) | WR-03: bare `NaN`/`Infinity` can be written (invalid JSON for strict readers); each entry still stays one line | user, UAT test 4 (06-UAT.md) | 2026-10-25 |
| AR-04 | T-06-26 / T-06-03 (WR-01) | A lone surrogate in a string drops that one entry; not silent (one stderr line naming the exception class) and never changes a tool result | user, UAT test 4 (06-UAT.md) | 2026-10-25 |
| AR-05 | T-06-08 (WR-02) | A non-mutating 200 reply whose body says `{"status":"error"}` is labelled `success`. Mutating routes label the same body `unrecognized`, so mutation outcomes are never recorded falsely. T-06-08 is closed on the basis that its declared mitigation covers mutations; if it is read to include reads, this becomes a high open threat. Patches are in 06-REVIEW.md | user, UAT test 4 (06-UAT.md) | 2026-10-25 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-25 | 38 | 38 | 0 | gsd-security-auditor (sonnet), orchestrated by Claude |

## Security Audit 2026-10-25

| Metric | Count |
|--------|-------|
| Threats found | 38 |
| Closed | 38 |
| Open | 0 |

Evidence base: the auditor read audit.py, bridge.py, main.py, deploy/build-payload.cmd, deploy/gate.py, revit_mcp/trust.py, the live
runner and the audit/writer/stdio/secret/correlation/registration/payload tests, and ran the related pytest subset (955 passed,
3 skipped). It reproduced WR-01..WR-03 in a scratch directory only. No unregistered threat flags: every `## Threat Flags` section
in the SUMMARY files reads "None" (06-07-SUMMARY.md has no such section).

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-25
