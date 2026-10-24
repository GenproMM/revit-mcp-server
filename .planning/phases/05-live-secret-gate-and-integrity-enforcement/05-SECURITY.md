---
phase: "05"
slug: live-secret-gate-and-integrity-enforcement
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-25"
---

# Phase 05 - Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| MCP server -> Revit Routes server (localhost/LAN :48884) | Every non-GET route must carry the shared secret in the reserved `_mcp` body key; refusal is 401 (secret) or 423 (integrity) before any document access | Shared secret, POST bodies, refusal texts |
| Seven open POST reads | `strip_envelope` removes `_mcp` and never refuses; listed in `trust.OPEN_POST_READ_ROUTES` | Caller-addressed model reads (see WR-01 for `/model_worksets/`) |
| `/status/` (open GET) | Reports `configured`, an 8-hex SHA-256 fingerprint, integrity file names, bind verdict | Diagnostics only, never the secret |
| Publish pipeline (`deploy/`) -> shared `ext\` and payload | Staging, manifest, secret verify, swap by rename; payload first, then extension | Extension tree, `_bridge_secret`, `_manifest.json` |
| Live-gate runner (`tests/test_phase5_live_gate.py`) -> developer's Revit | One-shot writes into one new unsaved project; records scanned for the secret | Verdict records (no secret field) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-05-01 | Elevation of privilege | /create_level/ handler | high | mitigate | gate preamble is the first statement, before the document guard; 401 rows prove zero transactions, collectors and document reads (Task 1) | closed |
| T-05-02 | Information disclosure | request.data after the gate | high | mitigate | gate replaces request.data with the payload without `_mcp` before handler code; e2e test reads the handler's request (Task 1) | closed |
| T-05-03 | Information disclosure | refusal bodies and the gate exception path | high | mitigate | fixed texts from trust.auth_failure / integrity_failure / gate_failure; leak tests over bodies, repr and caplog (Task 2) | closed |
| T-05-04 | Denial of service turned open door | security.initialize failure at extension load | high | mitigate | startup records it in registry.FAILED["security"] so /status/ is degraded, and `_STATE` stays None so every gated route answers 401 server_not_configured (Task 2 rows: stub raising, module missing, check_integrity raising) | closed |
| T-05-05 | Spoofing | model-built `_mcp` in tool data | medium | mitigate | with_envelope refuses; revit_post returns NOT sent before _dispatch; transport sees no POST (Task 1) | closed |
| T-05-06 | Repudiation | pre-send refusal mislabelled as outcome unknown | medium | mitigate | envelope built before _dispatch, tagged not-sent (Task 1) | closed |
| T-05-07 | Information disclosure | unit tests reading the developer's real secret | low | mitigate | conftest pins the bridge secret cache to None (Task 1) | closed |
| T-05-08 | Information disclosure | timing of the secret compare | low | mitigate | reuse trust.check_secret (SHA-256 digests, XOR accumulation); no new compare (Tasks 1, 2) | closed |
| T-05-09 | Tampering | handler reads a body whose truthiness changed | medium | mitigate | type-preserving clean_body; envelope-only bytes stay b'{}' (Task 2 rewrite table) | closed |
| T-05-10 | Elevation of privilege | seven gated handlers in annotation, building, colors, detail | high | mitigate | gated preamble first; parametrized 401/401/423 rows with world.events == [] (Task 1) | closed |
| T-05-11 | Information disclosure | document candidates in 400/412 guard bodies | medium | mitigate | gate runs before the guard, so an unauthenticated caller never sees candidate lists (Task 1 asserts guard_calls == []) | closed |
| T-05-12 | Denial of service | open reads refused on a secret mismatch | medium | mitigate | strip_envelope never refuses; rows with no, wrong and valid envelopes and with uninitialized state (Task 2) | closed |
| T-05-13 | Information disclosure | secret left in an open read's body | medium | mitigate | strip removes `_mcp` before the handler; rows assert the request has no `_mcp` afterwards (Task 2) | closed |
| T-05-14 | Elevation of privilege | eleven gated handlers in document, documentation, editing, interop, placement | high | mitigate | gated preamble first; parametrized refusal rows with world.events == [] (Tasks 1-2) | closed |
| T-05-15 | Tampering | files written on the station by save/export/IFC/link | high | mitigate | gate precedes any path handling; rows assert no new file under tmp_path (Tasks 1-2) | closed |
| T-05-16 | Information disclosure | guard refusal bodies listing documents | medium | mitigate | gate before guard; guard_calls == [] on every refusal row | closed |
| T-05-17 | Elevation of privilege | nine gated handlers in mep, parameters, rooms, structure, tags | high | mitigate | gated preamble first; parametrized refusal rows with world.events == [] and world.sets == [] (Tasks 1-2) | closed |
| T-05-18 | Information disclosure | guard refusal bodies listing documents | medium | mitigate | gate before guard; guard_calls == [] on every refusal row | closed |
| T-05-19 | Elevation of privilege | /execute_code/ | high | mitigate | gated preamble before _stamp_exception and before any compile; 401 and 423 rows with zero events (Task 1) | closed |
| T-05-20 | Tampering | /open_model/, /activate_document/, /set_active_view/ | high | mitigate | gated preamble; rows assert no open, activation or view switch call (Tasks 1-2) | closed |
| T-05-21 | Information disclosure | refusal stamped with Revit-read identity | medium | mitigate | gate returns before _stamp_*; rows assert no document_scope / process_identity in refusals (Task 1) | closed |
| T-05-22 | Denial of service | /document_summary/, /document_levels/, /model_worksets/ refused on mismatch | medium | mitigate | strip_envelope never refuses; rows over three envelope variants (Tasks 1-2) | closed |
| T-05-23 | Elevation of privilege | a new or edited non-GET route without the gate | high | mitigate | sentinel over the real inventory (Task 1) and check_route_gate in every checker (Task 2) | closed |
| T-05-24 | Elevation of privilege | open-reads list silently widened | high | mitigate | literal D02_OPEN in the sentinel plus parity pin with conventions; reads-only class and primitive checks (Tasks 1-2) | closed |
| T-05-25 | Tampering | a contributed module importing gate internals (_STATE, initialize) | medium | mitigate | SECURITY_IMPORTS allow-list in check_route_gate and in the sentinel (Tasks 1-2) | closed |
| T-05-26 | Elevation of privilege | contributor kit zip still carrying the old checker | medium | transfer | the kit zip is rebuilt at release by the user (scripts/build_contrib_kit.py); intake runs the repository suite, which has the new rule, regardless | closed |
| T-05-27 | Information disclosure | secret on the open /status/ | high | mitigate | only configured + 8-hex SHA-256 fingerprint; leak rows scan payload repr, hints and tool text (Tasks 1-3) | closed |
| T-05-28 | Information disclosure | fingerprint of a weak manual secret enabling offline guessing | low | accept | D-08 locked the fingerprint; secret_tool creates token_urlsafe(32), whose 8-hex fingerprint reveals nothing usable (RESEARCH A8) | closed |
| T-05-29 | Denial of service | /status/ failing because of the security module | medium | mitigate | lazy import inside try/except; ImportError row proves /status/ still answers (Task 2) | closed |
| T-05-30 | Spoofing (misdiagnosis) | wrong health or hint sending the engineer the wrong way | medium | mitigate | health rule and hint wording pinned by rows; unverifiable never degrades (Task 2) | closed |
| T-05-31 | Information disclosure | exposed Routes bind | medium | mitigate | bind reported as exposed with health degraded and an alert, never blocking (03 D-16, Task 2) | closed |
| T-05-32 | Denial of service | Revit starting mid-publish loads a half-built extension (WR-02) | high | mitigate | build and gate in ext-staging, swap by rename (Task 1) | closed |
| T-05-33 | Denial of service | swap failure destroying the live extension | high | mitigate | move live aside first (failure changes nothing), restore previous if the second move fails; in-use row (Task 2) | closed |
| T-05-34 | Tampering | a staged tree whose manifest or secret is wrong reaching ext | high | mitigate | --check verified_match and secret_tool verify gate the swap (Task 1) | closed |
| T-05-35 | Tampering | developer manifest committed or written in a subfolder | medium | mitigate | --allow-repo-dest only at the repo root and only when git-ignored (Task 3) | closed |
| T-05-36 | Information disclosure | stale secret copy in ext-previous / ext-rejected after a rotation | medium | mitigate | documented in the rotation procedure (plan 05-10); folders sit under the same access-controlled share root | closed |
| T-05-37 | Tampering | a test publishing to the real share | high | mitigate | _assert_scratch extended to every new target before any spawn (Tasks 1-2) | closed |
| T-05-38 | Information disclosure | an old handler echoing the body (with the secret) into a reply or error text | high | mitigate | scanner flags every non-read use of the parsed body and every raw request.data read (Tasks 1-2); a suspect blocks the payload-first order (D-06) | closed |
| T-05-39 | Denial of service | an old handler that iterates the body and fails on the extra key | medium | mitigate | iteration and whole-body forwarding are suspect rows (Task 2) | closed |
| T-05-40 | Repudiation | a scanner false negative presented as proof | medium | mitigate | the SUMMARY and the runbook state it is the static half; the pilot rehearsal is the live half | closed |
| T-05-41 | Denial of service | fleet-wide 401 after an out-of-order publish | high | mitigate | RELEASES/RUNBOOK fix payload first, the D-06 scanner gate and the pilot rehearsal before the main-share extension (Task 1) | closed |
| T-05-42 | Denial of service | payload rolled back while the new extension is live | high | mitigate | rollback section and matrix forbid it and say why (Task 1) | closed |
| T-05-43 | Spoofing (wrong secret promoted) | pilot secret reaching the main share | medium | mitigate | fingerprint check on the first fleet machine after promotion (Task 1) | closed |
| T-05-44 | Information disclosure | stale secret copies after rotation | medium | mitigate | rotation text in README, RELEASES and config.cmd clears ext-previous and ext-rejected (Tasks 1-2) | closed |
| T-05-45 | Denial of service | the D-10 swap blocked on the share by open handles | medium | mitigate | pilot probe; on failure the release stops and D-10 returns to the user (Task 1) | closed |
| T-05-46 | Repudiation | a verdict of ok on incomplete or contradictory evidence | high | mitigate | every check is a named helper; perturbation tables make each missing or wrong field a stop (Tasks 1-2) | closed |
| T-05-47 | Information disclosure | the secret in a record or the script | high | mitigate | the record contract has no secret field; the script never reads it; WRONG_SECRET is a constant (Task 1) | closed |
| T-05-48 | Tampering | the script calling a write route beyond the probe | medium | mitigate | ALLOWED_ENDPOINTS and the string-constant scan (Task 1) | closed |
| T-05-49 | Tampering | a write step repeated or sent to the wrong Revit | high | mitigate | one-shot posts_sent rule, refusal of an existing --out, preflight of exactly one listener and one document (Tasks 1-2) | closed |
| T-05-50 | Information disclosure | the secret in a record or console output | high | mitigate | never read except via load_secret inside scan-secret; scan-secret prints tokens only (Task 3) | closed |
| T-05-51 | Tampering | corrupt or restore discarding the user's uncommitted work | high | mitigate | corrupt refuses a module with uncommitted changes; both touch only the named module and the probe; temp-repo rows (Task 3) | closed |
| T-05-52 | Denial of service | a leftover manifest or probe blocking the developer's mutations | medium | mitigate | restore verifies git status and manifest absence and says RESTORE_INCOMPLETE otherwise (Task 3) | closed |
| T-05-53 | Tampering | overlapping callers cross-wiring in pyRevit's handler | medium | mitigate | the operator procedure forbids MCP calls while the script runs; direct steps run sequentially | closed |
| T-05-54 | Tampering | writes landing on a production model or a second Revit | high | mitigate | one new unsaved project, one listener checked by the user and again by Claude, preflight of one document (Tasks 2-3) | closed |
| T-05-55 | Denial of service | Revit crash from pyRevit Reload | medium | mitigate | full close and reopen only (Task 2) | closed |
| T-05-56 | Information disclosure | the secret in a record, SUMMARY or MCP text | high | mitigate | the script never reads it; scan-secret on the record; only fingerprints in texts (Task 3) | closed |
| T-05-57 | Denial of service | the temporary manifest blocking the developer after a stop | medium | mitigate | restore on a STOP; warning to the user while it exists (Tasks 1, 3) | closed |
| T-05-58 | Denial of service | corruption or manifest left behind, blocking the developer's mutations | high | mitigate | restore in Task 3 whatever the verdict, verified by git status and the green suite | closed |
| T-05-59 | Tampering | corrupting a file that holds the user's uncommitted work | high | mitigate | corrupt refuses a module with uncommitted changes; precondition checks git status (Task 1) | closed |
| T-05-60 | Tampering | writes on the wrong Revit or a production model | high | mitigate | one listener, one new unsaved project (Tasks 2-3) | closed |
| T-05-61 | Information disclosure | secret in the record | high | mitigate | scan-secret (Task 3) | closed |
| T-05-62 | Tampering | the write landing on a second Revit or a production model | high | mitigate | one listener, one new unsaved project (Tasks 2-3) | closed |
| T-05-63 | Information disclosure | PIDs, tokens or the secret in the validation file | medium | mitigate | only verdicts, counts, dates, check results, fingerprint equality and paths (Task 3) | closed |
| T-05-64 | Information disclosure | the secret in any record | high | mitigate | scan-secret over all three records (Task 3) | closed |
| T-05-65 | Information disclosure | bridge reply texts and the stdio stream | medium | mitigate | the NOT sent text is fixed and carries neither body nor secret; the 401 rows assert TEST_SECRET is absent from the model-visible text; bridge.py never prints (Task 1) | closed |

*Status: open - closed - open (below high threshold, non-blocking)*
*Severity: critical > high > medium > low - only open threats at or above workflow.security_block_on (high) count toward threats_open*
*Disposition: mitigate (implementation required) - accept (documented risk) - transfer (third-party)*

Evidence per threat (file:line and test names) was gathered by gsd-security-auditor on 2026-10-25 and is summarised in the audit trail below. Basis of the run: `uv run pytest tests/unit -q` = 5884 passed, 3 skipped; `scripts/scan_envelope_tolerance.py --dir revit_mcp` = `ENVELOPE_SCAN_OK files=32`; `tests/test_phase5_live_gate.py classify-phase` = `PHASE5_GATE_OK`; `scan-secret` over the five records = `SECRET_ABSENT`; 41 non-GET routes = 34 gated + 7 open reads, matching `trust.OPEN_POST_READ_ROUTES`.

T-05-26 is a **transfer**: the contributor kit zip is rebuilt by the user at release (`scripts/build_contrib_kit.py`). R3 was skipped in the release ledger, so no rebuild has happened yet (see WR-04).

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-05-01 | T-05-28 | Fingerprint of the secret is exposed on open `/status/` (decision D-08 locked it). `secret_tool` creates `secrets.token_urlsafe(32)`, so an 8-hex fingerprint reveals nothing usable (RESEARCH A8, 05-07-PLAN) | Phase 5 plan decision D-08 (user) | 2026-10-24 |

---

## Unregistered Flags and Advisories (non-blocking, not counted in threats_open)

| ID | Status | Description |
|----|--------|-------------|
| WR-01 | **open** | `/model_worksets/` is an open read that passes a caller-supplied `file_path` to `os.path.exists` and the Revit file APIs without the secret: SMB credential coercion via UNC path, file-existence oracle, workset-name disclosure; the path is echoed in the 404 and success bodies (`revit_mcp/worksharing.py`). UAT test 5 was answered "pass" without choosing keep-open vs gate, so no code change was made. Options (05-REVIEW.md WR-01): remove the route from `OPEN_POST_READ_ROUTES` and gate it like `/open_model/`, or reject UNC/`//` paths before any API call and stop echoing `file_path`. Decide before a release that carries this route |
| WR-02 | open | Live-gate runner `_valid_module` accepts `revit_mcp/../<tracked file>` (residual on T-05-51 / T-05-59); operator-typed argument |
| WR-03 | open | One-shot write stage is enforced only by refusing an existing `--out`; the record is written after the writes (residual on T-05-49); the match stage ran three times once, in a throwaway project |
| WR-04 | open | Tracked `contrib-kit/conventions.py` is a stale copy without `check_route_gate` (residual on T-05-26) |
| WR-05 | open | Route inventory recognises only the `@x.route(...)` decorator form (residual on T-05-23); all 41 current routes use it |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-25 | 65 | 65 | 0 | gsd-security-auditor (sonnet), orchestrated by /gsd-secure-phase 5 |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-25 (WR-01..WR-05 remain open advisories)
