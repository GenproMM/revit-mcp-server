---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
plan: '20'
status: human-checkpoint-accepted-with-measured-scope
completed: 2026-10-16
---

# 02-20 — measured preflight and human decision

## Decision

User: «Принимаю чекпоинт, давай дальше».

The separate implementation plan for **02-01 only** was also approved. This closes the human mechanism-selection checkpoint, not production acceptance of Phase 2. G6 is unrun and not authorized; 02-02 must recheck the production identity after a full Revit restart. No mutation sweep, discovery rollout or fleet publication follows automatically.

## Selected mechanisms and local evidence

Evidence below lives in `C:/preflight/out/`, is machine-local, and is not copied or published by this summary.

| Gate | Selected mechanism | Evidence |
|---|---|---|
| G1 | .NET GUID retained once in AppDomain at extension startup in a fresh process; actual port from existing RoutesServer.server.server_address; explicit-route-only | g1-restart-comparison-20261016-174925.json; referenced token stability captures for PIDs 13052/88388; g1-coexistence-70040.json for server/signatures |
| G2 | retained-reference-equals-v1: IsValidObject, unique semantic Equals match, retained lifetime references, separate monotonic tokens/permanent tombstones | g2-88388-verified.json; g2-88388-retained-branch-classification.json |
| G3 | explicit nonactive doc for summary/levels, Equals rather than runtime hashes for identity | g3-88388-classification.json |
| G4 | OpenAndActivateDocument only for measured saved-existing-path case; explicit refusal for unsaved/non-file cases | g4-88388-policy-and-human-observation.json |
| G5 | full netstat.exe -ano -p tcp; retain every distinct PID, fail closed on malformed/incomplete inventory | g5-netstat-repeat-20261016-b-with-provenance.json; g5-netstat-repeat-20261016-b-teardown.json |

## Evidence boundaries

- G1 measured extension startup, **not literal OS process creation time**. Its raw wording does not satisfy the classifier's literal `initialized_at == process-start` without a semantic amendment. No fabricated unified classifier PASS was created. Human acceptance of the disclosed mechanism is separate from automatic eligibility; the classifier still never grants approval.
- Historical G1 `execute_code_user_decision: pending` predates D-15. User chose to keep execute_revit_code and /execute_code/ enabled as trusted arbitrary-code exceptions. Injected doc is not whole-execution confinement; no arbitrary-code route was used for this preflight.
- G2 runtime hashes are diagnostics, not native handles or selectors. Production registry and token issuance remain unimplemented.
- G4 success covers saved COORD only. Unsaved empty path and detached-unsaved non-file PathName refused and left COORD active. User confirmed no dialogs. Saved workshared activation is not approved by analogy; no save/sync/reopen substitution.
- G5 genuine auxiliary RoutesServer objects in Revit PIDs 88388/112992 both bound 127.0.0.1:48991. Get-NetTCPConnection missed an owner; corrected full netstat retained both. Separate netstat captures share an OS backend, not independent implementation diversity. This is not evidence of automatic primary-port assignment.
- No HTTP, including status, was sent to 48991. Both temporary servers stopped; retained AppDomain references absent and OS teardown confirmed. Last measured primary mapping was 48884→68276, 48885→88388, 48886→112992; it is historical, not a current liveness claim.
- Original G5 classification omitted provenance flags and correctly STOPped. A separate derived record validated 34 capture hashes and added live/non-synthetic provenance; originals were not rewritten.
- Installed live attachment historically IPY2712PR; this does not establish production IPY342 compatibility. No attachment/config/foreign extension changes are authorized here.

## Completed checks

G5 correction: RED 36 failures/4 passes among 40 added tests, then 303 preflight tests passed. Full unit suite: 736 passed, 3 skipped; cold start INIT_LATENCY_S=0.728. Focused 303 passed again after live work. These results precede 02-01 changes and do not verify its implementation.

## Handoff

Execute existing 02-01 selected-status vertical slice with startup identity and complete listener refusal. Retain legacy no-target behavior without claiming it has new discovery guarantees. Stop before 02-02 live production recheck. Full close/reopen of Revit is required after extension edits; no Reload or execute-code workaround. No commit/push or shared publication was requested.
