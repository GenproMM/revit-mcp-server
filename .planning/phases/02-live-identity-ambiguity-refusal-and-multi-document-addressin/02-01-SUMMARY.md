---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '01'
status: offline-verified-live-recheck-pending
completed: 2026-10-16
---

# 02-01 — selected-status vertical slice

## Implemented

- bridge.py: strict versioned `revit1:` base64url JSON selector (loopback host/port/PID/GUID session token), parse_target, listener_snapshot, resolve_target; full approved G5 netstat parser with AST-equivalence regression against the standalone procedure.
- Unknown inventory, zero owners, multiple owners and PID mismatch refuse before any HTTP. Multiple owners are all named. OS collection is off the asyncio loop; Windows-only, no cmdlet fallback.
- Explicit GET /status/ uses a scoped trust_env=False client, compares received identity before attaching per-response verified metadata. HTTP503 preserves no-document/error identity; transport/non-JSON/incomplete/mismatch responses never become verified. No mutable selected session/base URL or global response attribution.
- Explicit targets on non-status GET/POST/image refuse, never fall back. No-target calls retain legacy transport and its existing lock/text/plain/UNKNOWN behavior. Discovery and per-incarnation pools/locks remain 02-03.
- revit_mcp/identity.py: own AppDomain GUID slot initialized explicitly by startup.py. Getter never creates a token lazily; actual port comes only from retained primary RoutesServer.server.server_address. Helper uses IronPython-compatible syntax and no foreign package alias.
- status route: identity available with active doc or no-doc503; identity errors are visible, not invented defaults. Startup identity failure is recorded without aborting all other domains. Identity helper is included in the explicit helper-import/test allowlist; domain→domain prohibition remains.
- get_revit_status gains optional target, keeps ctx last and injected transport; verified responder is appended after format_response. Legacy configured MCP target suffix remains distinct from verified identity.

## Checks

RED observed: all 26 original selected-target tests failed before implementation; all 4 original identity tests failed before helper/startup changes. Additional edge-case regressions followed.

Final full working-tree offline suite: **790 passed, 3 skipped** (7.87s; repeated before session save: 6.07s). This includes pre-existing uncommitted coexistence/preflight changes, not just this session's patch.

Selective index snapshot at session save: **6 failed, 679 passed, 3 skipped**. Four status api_name assertions require the excluded coexistence namespace, one startup assertion requires its excluded owned-package loader, and parser AST equivalence requires the excluded preflight parser correction. The selected HTTP client also requires the excluded `/genpro_revit_mcp/` registration. The session-only commit is therefore a partial checkpoint with uncommitted prerequisites, not an independently passing or deployable revision; earlier changes were not silently bundled and tests were not weakened.
Cold-start gate: **INIT_LATENCY_S=0.904** (<2s).
Earlier focused selected-status/legacy transport: 88 passed, before added edge tests.
UTF-8/no BOM and Python3.4 AST parse checked for changed extension files. git diff --check passed with existing LF→CRLF advisory warnings. Graphify AST update performed; community-label drift warning is not a refreshed semantic label claim.

HTTP tests use httpx.MockTransport and the actual status tool registrar, not a live network/Revit endpoint. Extension identity/status tests use CLR/pyRevit doubles. No production live claims follow from these tests.

## Boundaries and deviations

- Necessary narrow additions to existing 02-01 file list: startup.py explicit initialization; tests/unit/test_process_identity.py; helper allowance in test_registration.py. The existing test_status_target.py remains unchanged and passes. No new MCP tool/manifest entry or route was added.
- G1 timing remains extension startup in a fresh process, not literal OS process creation. Full restart must verify this implementation's token stability/change and actual-port sourcing. Prefight evidence measured the mechanism, not this new helper.
- Snapshot→connect remains a finite race, not port reservation/authentication. Port-level owner aggregation is conservative across addresses.
- Legacy no-selector routing is not upgraded to discovery or collision protection by this tracer. Full target routing is deliberately pending.
- DSH hub was unavailable; no worker ran and no standalone fallback was used.
- Existing coexistence and other dirty workspace changes were preserved, not claimed as newly implemented here. No commits/pushes, foreign-extension edits, live route calls, document mutations, G6 or publication.

## Next boundary

Stop before **02-02 production recheck**. Extension files are the deployed junction source but running Revit still has old loaded code. Full close/reopen is required before live testing; never pyRevit Reload or execute-code hot injection. Do not close user documents/processes automatically. G6 requires separate authorization. Both execute capabilities remain enabled under D-15.
