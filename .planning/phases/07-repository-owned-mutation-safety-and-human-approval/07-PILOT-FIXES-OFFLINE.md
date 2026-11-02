# Pilot fixes — offline verification

2026-10-26. Controller worked in the main checkout without subagents. Existing
staged/unstaged planning, vault, scripts and graph changes were retained; no commit,
push, tag, fleet release, live Revit/Routes/Hermes request or production build was run.
The shared .venv was not synchronized and other processes were not terminated.
This record does not replace 07-VALIDATION.md or the original PHASE7_BENCH_STOP.

## Implemented

- tests/test_phase7_live_bench.py: select the unique final audit row by call_id,
  expected tool and expected route; permit accompanying mutation_preflight rows
  for that same tool. Unexpected routes/tools, missing final rows and real final
  duplicates still stop. Reused IDs, H4 args and final decision/approval/outcome
  remain checked (H2/H3 and H4 outcome consistency also made explicit).
- classify RECORD --out NEW_REPORT: exclusive-create local report, classifier
  version 2-tool-route and SHA-256, source SHA-256, offline marker, secret-scan
  availability and manual evidence gaps. No overwrite or HTTP. A missing configured
  secret produces STOP rather than claiming a successful leak scan.
- tools/editing_tools.py: shallow-copy a successful selection payload and remove
  only its summary message before format_response; IDs, categories, count, Unicode
  and parameters remain visible. Bridge provenance is retained; original reply is
  unchanged. Error and string transport semantics unchanged. No global formatter edit.
- approval.py: deletion's fixed warning states that dependent elements are also
  deleted and the exact cascade is unknown. Tested with unknown facts and oversized
  details. No claim about the contents of the already observed H1 card.
- deploy/START-HERE.txt: updated operator instructions for the actual nested pilot,
  new-folder requirement, safe switch order, partial installation, Hermes/updaters,
  PowerShell UTF-8 stdin, original STOP and offline-only evidence review.

The old Downloads START-HERE.txt edit was denied by the environment. No alternate
write method was used. The old kit remains unchanged; the repository instruction
must be included explicitly in a newly authorized kit (current publish recipe copies
only the existing four installer files).

## Automated checks

Interpreter: separate phase7-test-venv, not the shared .venv.

| Check | Result |
| --- | --- |
| Focused bench/selection/messages/encoding tests | 106 passed in 3.01s |
| Complete tests/unit, child cmd CP866, final tree | 6965 passed, 3 skipped in 106.08s |
| Cold start, final tree | INIT_LATENCY_S=0.994 |
| Transport smoke | streamable-http, sse, combined: 59 tools each; TRANSPORTS_OK |
| Scratch payload, CPY3123, UV_OFFLINE=true | warm ok; TOOLS=59; MANIFEST=ok; GATE_OK; SCRATCH_GATE_OK; latency 1.067s |
| Scratch secret | unchecked, intentionally no MCP_SECRET_FILE; not a secret-bearing pilot build |
| Scratch policy | base dd435f53b542, POLICY_SOURCE=absent |
| graphify update . | exit 0, AST-only; generated changes not staged/committed |
| git diff --check on edited tracked code | exit 0 (autocrlf warnings only) |

Scratch gate destination was a new unique local TEMP directory. Dependencies were
installed into its app/libs from the offline cache. No pilot secret was copied.

### Failures investigated, not hidden

- Initial encoding test launcher used subprocess's list-to-command-line quoting for
  cmd, causing escaped quoted paths. Fixed the test launcher, then its tests passed.
- Existing guarded test_publish_smoke_scratch_share reproduced the CP65001 failure:
  fragments such as 'ONCE' and 'checks' were executed as commands. The same test passed
  under CP866 (1 passed in 1.17s). Production batch files were not changed.
- New encoding probe initially changed the console shared by later scratch tests,
  making a full run fail. Isolated that probe with CREATE_NEW_CONSOLE; final full
  run above passed. No test was skipped or production guard bypassed to fix it.
- Read-only inspection: config/find-python/install/update/build-payload use LF,
  publish-extension uses CRLF; none has a UTF-8 BOM. The old kit's three batch
  installers match current sources byte-for-byte. Added a guarded scratch packaging
  assertion for all four installer files. CRLF config copies parse under both
  CP866 and CP65001 with local ASCII overrides; this is not proof of all real build
  paths or a universal fix for UTF-8 Cyrillic path literals.
- Windows PowerShell 5 stdin regression verifies quotes and Cyrillic using explicit
  UTF-8 input/output and a BOM for the scratch .ps1 source.

## Real evidence — not reclassified

Local Documents/Downloads searches found preflight.json and direct.json in Downloads,
not final.json, replies.json or the original audit segment. User was asked for local
copies / a local dev-PC path. Partial files were not treated as complete acceptance
and were not rewritten. No workstation/share retrieval was attempted. Logs and BIM
data were not published.

Original PHASE7_BENCH_STOP, POSTS_SENT=5 and SECRET_OCCURRENCES=0 remain the
reported historical result, not a new controller-verified verdict. Direct and H1–H5
must not be repeated. Once copies are provided, use classify on the original final
record and an exclusive new output; do not overwrite source evidence or its STOP.

Remaining gaps: actual H4 args equality awaits original audit; operation codes were
not recorded, so their difference cannot be inferred from different call_ids.
H1 card contents/exact cascade prediction were not captured. Gateway and company
FOP are unverified. SAFE-20/21 and Phase 7 remain open.

## Next authorization

Offer a NEW local kit with a new version and separate directory, compatible payload
and extension, existing pilot secret (no rotation), manifest/integrity/gate/source
checks, secret-copy equality checks without printing values, and this instruction.
Do not run the build or include the secret in new portable artifacts without a new
explicit authorization. Do not overwrite the old kit. User owns network transfer,
installation and live testing. Multi-document read expansion requested earlier was
deferred when this pilot-fix scope arrived; it is not implemented by these changes.
