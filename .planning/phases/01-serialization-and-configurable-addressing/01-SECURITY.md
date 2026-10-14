---
phase: "1"
slug: "serialization-and-configurable-addressing"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-14"
---

# Phase 1 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register built from the `<threat_model>` blocks of 01-01..01-08-PLAN.md (01-05 superseded; its
> T-01-19..T-01-22 are re-registered in 01-07). Verified by gsd-security-auditor on 2026-10-14.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| client config env → MCP server process | `REVIT_HOST` / `REVIT_PORT` come from the MCP client's config block (operator-controlled, typo-prone) | host and port strings |
| MCP server stdout → MCP client | the stdio protocol stream; any stray byte corrupts it | MCP protocol frames |
| tool coroutine → bridge lock | concurrent tool calls from FastMCP (one task per request) contend for the lock | in-process call ordering |
| MCP server process → pyRevit Routes (loopback HTTP) | every mutation crosses here; pyRevit shares one request handler across HTTP threads, and overlap there cross-wires responses (measured, 01-04) | model reads and mutations |
| bridge → pyRevit Routes | a sent request may be applied by Revit after the client gave up | mutations of unknown outcome |
| bridge error string → model | the model decides whether to retry based on the wording alone | failure wording |
| tool output → model | the model attributes a response to an instance from the text alone | `MCP target: host:port`, `Document:` line |
| other clients (another MCP server process, curl, `/execute_code/` direct) → the same handler | outside this process's lock by construction | any request |
| probe → pyRevit Routes (`/execute_code/`) | unauthenticated arbitrary IronPython on the live model, bypassing the bridge lock on purpose (bench only) | generated sleep/append code |
| two Revit processes ↔ one port range | pyRevit assigns ports by launch order without an OS bind check | port → instance mapping |
| build host → fleet share | `build-payload.cmd` publishes; workstations mirror the share | deployed app payload |
| docs / planning record / executed SUMMARYs → people and later phases | wording sets expectations about concurrency safety; the record of what shipped must stay what shipped | promises and history |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-01-01 | Tampering / Spoofing | `bridge._resolve_port`, `main.py` import guard | high | mitigate | Strict ASCII-digit 1..65535 parse, no fallback, exit 2 (`bridge.py:86-109`, `main.py:3-12`); `test_port_refuses`, `test_port_accepts`, `test_port_literal_only_in_default` | closed |
| T-01-02 | Denial of service | `main.py` refusal path | medium | mitigate | Refusal goes to stderr then `sys.exit(2)`; stdout empty (`test_port_refusal_writes_stderr_only`) | closed |
| T-01-03 | Information disclosure | `bridge._get_client` | medium | mitigate | `trust_env=False` (`bridge.py:135`), shared by every call incl. `revit_image`; `test_local_bridge_transport.py` | closed |
| T-01-04 | Tampering | `bridge._revit_call` POST path | high | mitigate | Every POST locked (`_is_locked`, `bridge.py:230-240`; `_serialized`, `:331-336`); `test_second_post_waits_for_the_first` | closed |
| T-01-05 | Elevation of privilege | lock presented as access control | low | transfer | Honest-scope docs (01-07): `bridge.py:13-15`, `CLAUDE.md` "harm reduction, not access control"; pinned by `test_serialization_scope_pinned_in_*` | closed |
| T-01-06 | Tampering | `_revit_call` failure wording | high | mitigate | Not-sent vs outcome-UNKNOWN wording (`bridge.py:246,270-309`); `test_outcome_unknown_*`, `test_queue_bound_message_is_an_error_string`, `test_get_post_send_failure_is_not_outcome_unknown` | closed |
| T-01-07 | Denial of service | module-global lock | high | mitigate | `async with` only, `CancelledError` never caught, errors returned inside the lock (`bridge.py:332-353`); `test_releases_*` | closed |
| T-01-08 | Tampering | `READ_ONLY_POST` allowlist | medium | mitigate | Vector removed by 01-06: `UNLOCKED_GET = {"status"}`, `NEVER_UNLOCKED` checked first; `test_unlocked_*` incl. tool-endpoint drift scan | closed |
| T-01-09 | Denial of service | wait message | medium | mitigate | `_say` guards `ctx`, swallows `ctx.info` failure, never prints (`bridge.py:255-267`); `test_wait_message_*` | closed |
| T-01-10 | Tampering / Information disclosure | unlocked read overlapping a pending call in pyRevit's shared handler | high | mitigate | d27-b (01-06): only GET `/status/` unlocked, `revit_image` serialized, no transport bypass in `tools/`/`main.py`; `test_d27b_tool_path_model_info_waits_status_does_not` et al.; bench `01-04-SUMMARY.md` Step 7 | closed |
| T-01-11 | Spoofing | `get_revit_status` | medium | mitigate | `MCP target: host:port` appended after `format_response` (`tools/status_tools.py:41-48`); `test_status_target.py`; live `TWO_INSTANCE_OK` | closed |
| T-01-12 | Denial of service | payload staging | high | mitigate | `bridge.py` copied by `deploy/build-payload.cmd:110`; `test_payload_copies_every_root_module_main_imports`; staged `GATE_OK` in `01-03-SUMMARY.md` | closed |
| T-01-13 | Information disclosure | target line in tool output | low | accept | Loopback host and port only — see Accepted Risks | closed |
| T-01-14 | Tampering | fleet share | high | mitigate | Procedural: `build-payload.cmd` never run for verification (01-03 must_haves, `01-03-SUMMARY.md`); diff to the script is the single `bridge.py` copy line | closed |
| T-01-15 | Tampering | `scripts/probe_handler_overlap.py` | medium | mitigate | Generated code limited to sleep/append/print (`build_code`, `:51-65`); `scripts/` never shipped; `test_probe_generated_code_is_ironpython_safe` | closed |
| T-01-16 | Spoofing | hidden Accelerator instance on 48884 | medium | mitigate | Harness requires one listening PID per port, PIDs distinct (`tests/test_two_instance_targets.py:114-121`); bench `/routes/sisters` record | closed |
| T-01-17 | Repudiation | SC5 acceptance | high | mitigate | Staggered run decides (PIDs 11088→48884, 35780→48885); simultaneous launch recorded as finding only (D-25); scope stated in USER-GUIDE and VERIFICATION | closed |
| T-01-18 | Denial of service | workset selection dialog | medium | mitigate | Revit booted empty, models opened via `/open_model/` with `WorksetConfiguration` (`revit_mcp/worksharing.py`); USER-GUIDE instructs the same | closed |
| T-01-19 | Repudiation / Tampering | serialization scope wording | medium | mitigate | Scope sentence in `bridge.py`, `CLAUDE.md`, `README.md`, `deploy/README.md`, RU USER-GUIDE; `test_serialization_scope_*` incl. over-claim scan | closed |
| T-01-20 | Tampering | read-queueing wording | medium | mitigate | `STATUS_SENTENCE` pinned in three docs; OVERCLAIMS list rejects "reads are not queued" variants | closed |
| T-01-21 | Spoofing | port-to-instance mapping in docs | medium | mitigate | USER-GUIDE says check status `Document` line; `bridge.py` "port names a launch slot, not a model" | closed |
| T-01-22 | Information disclosure | config examples | low | accept | Loopback values only — see Accepted Risks | closed |
| T-01-23 | Tampering | cross-process overlap (two MCP processes, one Revit) | high | transfer | ROADMAP Backlog Phase 999.1 (d27-c) with bench evidence; `CROSS_PROCESS_SENTENCE` pinned in five docs | closed |
| T-01-24 | Tampering | lock released after client timeout (D-13) | medium | accept | Documented residual; POST says outcome UNKNOWN, verify — see Accepted Risks | closed |
| T-01-25 | Denial of service | slow reads and mutations queue behind each other | low | accept | Bounded by the call's own timeout; refusal says NOT sent — see Accepted Risks | closed |
| T-01-26 | Tampering / Elevation of privilege | future edit widening `UNLOCKED_GET` | medium | mitigate | `test_unlocked_is_exactly_get_status`, drift scan, `NEVER_UNLOCKED` precedence; docstring requires measurement + user decision | closed |
| T-01-27 | Tampering | user docs inviting a copied MCP entry | medium | mitigate | `test_serialization_scope_no_two_entry_user_docs`; `REVIT_PORT` absent from USER-GUIDE, deployment-only in README | closed |
| T-01-28 | Repudiation | executed history | medium | mitigate | Append-only numstat vs `791a8d2` for `01-CONTEXT.md` and `01-02-SUMMARY.md` | closed |
| T-01-29 | Repudiation | SC5 / IDENT-05 acceptance under a5-a | medium | mitigate | ROADMAP SC5 names the harness; cross-version / 6.5.5 gap carried as backstop and closed in UAT | closed |
| T-01-30 | Information disclosure | debug file carrying model data | low | accept | 01-08 additions are routes, verdicts and run counts only — see Accepted Risks | closed |
| T-01-SC | Tampering | package installs | low | accept | No dependency changes in the phase — see Accepted Risks | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-01 | T-01-13 | The target line shows a loopback host and port only; no secret exists in this phase | plan 01-03 threat model | 2026-10-07 |
| AR-01-02 | T-01-22 | Config examples carry loopback host and port values only | plan 01-07 threat model | 2026-10-07 |
| AR-01-03 | T-01-24 | The lock is released after a client timeout, so the next call can overlap a call Revit is still running; a POST reports "outcome UNKNOWN ... Verify". Documented in `bridge.py`, `CLAUDE.md`, `README.md` | plan 01-06 threat model (D-13) | 2026-10-07 |
| AR-01-04 | T-01-25 | Slow reads and mutations queue behind each other — the user-accepted narrowing of SER-02 (d27-b); wait bounded by the call's own timeout, `/status/` stays unlocked | user decision d27-b | 2026-10-07 |
| AR-01-05 | T-01-30 | The 01-08 debug-file additions contain routes, verdicts and run counts only (the file's older content, committed in `2b9b790`, includes an element ID and a parameter name) | plan 01-08 threat model | 2026-10-07 |
| AR-01-06 | T-01-SC | The phase installs no packages; `uv.lock` and `requirements.txt` untouched | plan 01-01 threat model | 2026-10-07 |

*Accepted risks do not resurface in future audit runs.*

Transfers: T-01-05 → honest-scope documentation (01-07); T-01-23 → ROADMAP Backlog Phase 999.1 (d27-c, owned by 01-08).

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-14 | 31 | 31 | 0 | gsd-security-auditor (ASVS L1, block_on high) |

### Security Audit 2026-10-14

| Metric | Count |
|--------|-------|
| Threats found | 31 |
| Closed | 31 |
| Open | 0 |

Advisory (non-blocking, no verdict changed):
- **WR-01 (`01-REVIEW.md`):** a POST answered HTTP 200 with an unparseable body returns bare `Error: Expecting value ...` instead of outcome-UNKNOWN wording (`response.json()` at `bridge.py:207`, caught at `:352`). Outside T-01-06's declared transport-error scope; fix before Phase 4 builds on this transport.
- **WR-03 (`01-REVIEW.md`):** `REVIT_HOST` is not validated; T-01-01 covers the port only.
- **UAT evidence:** `01-UAT.md` records pass for the 6.5.5 probe, `/model_info/` overlap, simultaneous launch and cross-version pair without captured output; `bridge.py` still says 6.5.5 was not benched and `/model_info/` stays locked. No mitigation depends on those results.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-14
