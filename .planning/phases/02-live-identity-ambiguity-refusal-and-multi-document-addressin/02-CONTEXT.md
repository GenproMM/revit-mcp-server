# Phase 2: Live identity, ambiguity refusal, and multi-document addressing - Context

**Gathered:** 2026-10-14 (interactive revision of the 2026-09-23 `--auto` context)
**Status:** Ready for research and planning

The interactive decisions below replace the old Phase 4 boundary and its incompatible `--auto` choices. The original alternatives remain in `02-DISCUSSION-LOG.md`; they are history, not additional requirements. In particular, the old exclusion of multi-instance addressing and the old rule requiring *every* addressed document to be active are superseded. Technical mechanisms proposed in the old context are research leads, not user-approved implementation contracts.

<domain>
## Phase Boundary

In the **one shared `revit` MCP server entry**, discover the available Revit processes, select a process per call, and attribute responses to the actual process and document. Reject two listeners on one target port *before sending* rather than accepting an unpredictable answer. Enumerate documents in a selected process, explicitly address a document, and switch the active document with a separate action. Make it possible for one assistant session to read and compare documents within one process and across processes; at minimum compare model summaries and level lists without disturbing the active Revit UI where safely supported. This is Phase 2 of `.planning/ROADMAP.md`, criteria 1–9, covering IDENT-01..04, AMBIG-01..04 and MDOC-01..05. Per-call process selection and a per-target lock are carried from Phase 1 decision a5-a.

Outside this phase: secret authentication and integrity logic (Phase 3), **live** secret/integrity enforcement (Phase 5), honest batch outcomes (Phase 4), audit logging (Phase 6), mutation of an inactive document without an explicit activation, and the Revit-side cross-session handler fix (backlog 999.1). Phase 2 may establish an identity/document chokepoint but must not quietly wire in Phase 5's secret or integrity checks. The earlier `_mcp` envelope proposal is not a requirement to send a secret in Phase 2.

</domain>

<decisions>
## Implementation Decisions

### Selecting the Revit process
- **D-01:** Keep one shared MCP entry named `revit`; no user-visible duplicate entries per Revit instance. Give the assistant a way to list available processes with port and identity, then pass an exact process selector with subsequent calls. Selection is **per call**, not mutable shared session state. — **Reversibility:** costly — changing the call contract later touches tool signatures, client guidance and tests.
- **D-02:** If exactly one usable Revit process is available, a call without a process selector may use it. If several are available, the call refuses with the candidate list; never choose the latest, the active-looking process or the default port silently. A selected process that restarts must be selected again from a fresh list rather than being treated as the old target. A selector must therefore distinguish a new process incarnation from a reused port/PID; its concrete representation is for research and planning.
- **D-03:** Calls routed to different Revit targets have separate serialization locks; calls to one target share its lock across documents. Preserve the Phase 1 rule: only GET `/status/` is unlocked. This process-local queue does **not** solve cross-session/curl overlap or the pyRevit handler cross-wiring documented in Phase 1; backlog 999.1 remains open.
- **D-04:** If two processes listen on the same selected port, refuse before sending and name both conflicting PIDs. The process-listing path must not suggest either as an unambiguous target. How to enumerate listeners reliably, how to handle discovery failure, and the race between check and send need research; do not promise a stronger safety guarantee than the implementation can establish.

### Process and document identity
- **D-05:** `/status/` exposes PID, Revit version, actual port and a session token issued once per process start. A mutating route's response names the document it actually changed (title and path); resolve identity at request time, including after API activation and a manual UI switch, not from a cached document. Two unsaved documents both titled `Project1` in different processes must be distinguishable by response fields alone.
- **D-06:** Identity must reach the assistant in the *tool's rendered result*, not merely a nested field discarded by success formatting. Both successful and failed responses must make the selected/answering target intelligible where a response was actually received. Do not label a timed-out or unsent request as a verified response from that document; retain Phase 1's honest not-sent/outcome-unknown distinction.
- **D-07:** The live `param-write-rolls-back` reproduction is repeated with visible identity, and the observed result is recorded as confirming or ruling out the specific “wrong process answered” hypothesis (AMBIG-04). Do not infer the result from the earlier Phase 1 UAT pass or invent port/PID measurements.

### Documents and user-visible behavior
- **D-08:** List the open documents in the selected process with identities and active status. An explicit document selector must resolve one document only; ambiguous names must refuse with distinguishable candidates. A document closed after listing must produce a named error and **must not** fall back to whatever is now active. The precise stable key and error vocabulary are research/planning choices, subject to these rules.
- **D-09:** A mutating call without a document selector may target the only open eligible document. With several open documents it **refuses and lists them**; the tool's own docstring states this default. Do not infer the user's intended document from the current UI selection when several are open.
- **D-10:** A mutation explicitly addressed to a document that is open but **not active in the UI refuses with HTTP 412**. Do not activate it or retarget the mutation automatically. Use the separate activation action first; a mutation can then be retried with the explicit document. This is the user's direct answer after the interrupted question, not an inferred tool selection.
- **D-11:** Addressed **reads** of inactive documents should leave the Revit UI on the engineer's active document **only for routes proven safe with a nonactive `Document`**. The minimum comparison surface is the model summary and the list of levels for each of two documents. Any other addressed read not demonstrated safe must refuse clearly rather than silently switch the UI or read the active document under the wrong label. Research must test both routes' actual data access, including helpers that still read `revit.doc`/`UIDocument`. If either minimum read cannot be made safe, stop at a decision gate and report the limitation rather than silently relaxing this acceptance criterion.
- **D-12:** An engineer can switch the active document through a separate explicit tool call. Research the safe Revit API behavior for already-open saved and unsaved documents, worksharing dialogs and UI state; do not assume the existing `/open_model/` path already implements this action. Never auto-switch merely to satisfy an addressed read or mutation.

### Research and acceptance guardrails
- **D-13:** Before choosing a shared wrapper in `startup.py`, inspect pyRevit's handler signature inspection, `doc`/`request` injection and `ExternalEvent` dispatch. Preserve those semantics and the existing `text/plain`/`parse_request_data()` contract. Route handlers must continue returning error responses instead of raising. The old D-01..D-05 `security.wrap_api` wiring is **not** carried into this phase as a fixed design.
- **D-14:** Verify process identity, same-port ambiguity, UI stability for the two supported inactive-document reads, explicit activation, document-close races, and both single- and multi-process defaults against a live Revit bench. Full process restart is required after `revit_mcp/` changes; pyRevit Reload alone is unsafe. Unit tests and the existing cold-start gate remain required, but they are not substitutes for these live claims. Record observed results rather than declaring unrun checks passed.

### Preflight decision amendment — 2026-10-16
- **D-15 (explicit user decision):** Keep both `execute_revit_code` and our HTTP `/execute_code/` route enabled as a **trusted arbitrary-code exception**. Binding the injected `doc` does not confine arbitrary code: it can access other documents through `revit`, `DB`, `clr`, `System` and builtins. The document-confinement guarantees in D-08..D-11 do not extend to the effects of arbitrary executed code. Do not describe this exception as guarded or sandboxed; do not infer the actual document(s) changed solely from the injected/active document. Process selection and response attribution must not promise confinement of code-created side effects either. This is acceptance of a limitation, not evidence that the original all-routes guarantee passed, and not authorization to disable either surface. Phases 3/5 authentication and integrity boundaries are unchanged.
- **G1 mechanism selection:** The temporary `phase2-preflight.extension` demonstrated `System.Guid.NewGuid()` stored once in `System.AppDomain.CurrentDomain` at extension startup in a new Revit process, stable between requests and different across full restarts (PIDs 13052 and 88388). Initialization is at extension startup, not literal OS process creation. Actual bound port 48885 matched independent OS PID ownership in both runs. Prefer `explicit-route-only`; common-wrapper semantics are not proven. Raw evidence: `C:/preflight/out/g1-restart-comparison-20261016-174925.json` and its referenced captures. This is feasibility evidence, not an implemented production identity contract.
- **Routing/approval boundary:** The user selected the trusted exception and continuation to G2 only. Overall 02-20 remains STOP; no broad Phase 2 execution or G6 mutation/overlap campaign is approved. D-15 supersedes conflicting all-code document-confinement assumptions in the existing research/plans, without marking requirements complete. Before executing a downstream plan, reconcile its affected contracts/tests with this amendment; do not silently retain a false guarantee or disable arbitrary code.

### G2 preflight correction — 2026-10-16
- **Measured, not approved:** PID 88388 local cycle opened saved `A/SAME.rvt` and `B/SAME.rvt`, retained both plus two auto-numbered unsaved projects, captured before-close/while-open/after-close/after-replacement, and separately read the retained replacement. Valid retained documents had exactly one `Equals` match and working collectors. `ReferenceEquals` between enumerations was false. The old A reference was invalid before reopen and stayed invalid afterwards; B survived; replacement A was independently readable. Evidence: `C:/preflight/out/g2-88388-verified.json` and its eight referenced raw captures. Files remained byte-identical; no save/sync or execute_code call.
- **Correction under review:** preflight now distinguishes wrapper-reference identity from a `retained-reference-equals-v1` lifetime-binding candidate. It validates ordered raw captures, retained validity, unique semantic comparisons, collectors and close/replacement separation; diagnostic hashes are neither object identities nor native handles. Existing stable-wrapper records retain their stricter branch. An exception reading `IsValidObject` is STOP, not proof of closure.
- **Downstream constraint:** if explicitly accepted at checkpoint, keep only the registry's lifetime reference, revalidate `IsValidObject` and exactly-one `Equals` against request-time enumeration, and retire/tombstone invalid or missing lifetimes. Do not cache an active document, use name/path/hash as a selector, or silently retarget ambiguous/missing matches. Production token issuance/tombstones are future tests, not measured by this probe. Overall checkpoint remains STOP / approval not granted; this correction is not authorization to run 02-04 or G6.

### G3/G4 preflight measurements — 2026-10-16
- **G3 measured:** PID 88388 read nonactive `COORD_plain` with VENT active (5,030 non-type elements / 14 levels), then read nonactive detached VENT with COORD active (29,760 / 14). Both captures had one target, `target_is_active=false` and `ui_switched=false`. The probe now uses `Document.Equals` for active identity; hashes remain diagnostic only, with offline collision regressions. Target summary/level accessors use the explicit Document; ActiveUIDocument is read only for before/after diagnostics. Evidence: `C:/preflight/out/g3-88388-classification.json` with SHA256 references. Classifier: `document-only-path`; this is a diagnostic-button feasibility result, not implemented HTTP routing or overall checkpoint approval. Coordinated models have identical levels but distinct summaries/counts; these counts are not the model_info category subset.
- **G4 measured, STOP:** the string overload `UIApplication.OpenAndActivateDocument(System.String)` completed saved COORD activation through an ExternalEvent callback. An unsaved project with empty PathName returned `Null argument / modelPath`; already-open detached-and-unsaved workshared VENT exposed a non-file PathName and returned `The document to be opened does not exist.` Both failed cases left COORD active. `Raise=Accepted` was recorded separately from each callback result. Evidence: `C:/preflight/out/g4-88388-classification.json` with six referenced queued/result captures. This does not prove all workshared activation impossible, nor exclude other activation APIs. No retry using VENT's source path, reopen, save, sync or execute_code workaround was attempted.
- **G4 policy accepted by the user, 2026-10-16:** allow only the measured activation of an already-open saved document with a usable existing file path; explicitly refuse unsaved and detached documents without such a path. Never save, reopen or substitute the source path to bypass that refusal. This narrows D-12/MDOC-04 for the initial implementation; it is a policy decision, not proof that every other activation API is impossible. The saved workshared case is not measured and must not be enabled by analogy. Independent human dialog observations remain unset, not inferred from callback completion or this policy approval. G4 therefore remains STOP pending that evidence; the overall checkpoint is not approved. G5 duplicate-port evidence is still missing; this acceptance does not authorize shared/foreign configuration changes or a G6 mutation/overlap campaign.

### G5 baseline and G4 policy record — 2026-10-16
- **G4 policy provenance:** `C:/preflight/out/g4-88388-policy-accepted-20261016T181626Z.json` applies the user's accepted allow/refuse policy to the previous captures without overwriting historical evidence. G4 still classifies STOP because the saved allow case has no independent dialog observation. Do not turn the policy acceptance into an invented `dialog_observed=false`.
- **G5 actual baseline:** `C:/preflight/out/g5-real-listener-baseline-20261016T181626Z.json` records Get-NetTCPConnection and independent Get-Process Revit observations: PID 68276 on 127.0.0.1:48884, PID 88388 on 127.0.0.1:48885. This read-only capture sent zero HTTP/model requests during its observation interval. Each port has only one Revit PID, so both classify STOP. Different ports do not satisfy the same-port gate. No duplicate condition has been created and no PID inventory has been fabricated.
- **G4 human observation received:** the user explicitly confirmed no dialogs requiring input during saved COORD activation and the two failed cases. `C:/preflight/out/g4-88388-policy-and-human-observation.json` combines that observation with the accepted narrow policy and the unchanged raw captures: G4 now classifies `explicit-activation-api`. This is per-case feasibility, not overall checkpoint approval or production implementation. It supersedes the missing-observation STOP only; historical records are preserved.
- **G5 limited experiment authorized:** the user approved two temporary genuine pyRevit RoutesServer instances inside two Revit processes on one initially free loopback port, with zero HTTP requests, no shared/foreign configuration edits, and teardown of only those temporary servers. Failed second bind is a measured negative, never permission to bypass it. Non-Revit helper listeners do not count as this evidence. No process restart, model opening, or G6 campaign is authorized by that narrow approval. Read-only UI inspection found PID 68276 on Home without an accessible Preflight diagnostic tab; nothing has been started or stopped for G5 yet.

### G5 bounded dual-listener experiment — 2026-10-16
- **Authorized setup:** user approved an additional test Revit 2024, started as PID 112992 without a model, then one fresh local non-workshared `C:/preflight/work/g5-112992/G5_DIAG.rvt` copy was opened on its independently owned primary port 48886. Copy SHA256 stayed unchanged. PID 68276 and its foreign extension were untouched. No shared configuration edit, Reload, production-code change, or execute_code request.
- **Actual dual bind, candidate failure:** two temporary instances of the installed `pyrevit.routes.server.server.RoutesServer` were retained inside Revit PIDs 88388 and 112992, both bound to `127.0.0.1:48991`. `netstat -ano -p tcp` independently showed BOTH listening PIDs; `Get-Process Revit` confirmed them. The exact current `os_listener_snapshot([48991])`, using Get-NetTCPConnection, returned only `[88388]`. Earlier direct Get-NetTCPConnection also exposed only one owner. `C:/preflight/out/g5-dual-48991-inventory.json` therefore classifies STOP: incomplete inventory / disagreement, not a missing real duplicate. No request was sent to 48991. The classifier's generic single-PID reason is not a factual denial of the independently measured duplicate.
- **Diagnostic control anomaly:** the first scoped click attempt in PID 112992 reported a PowerShell Add-Type/module-load failure and initially no output file. A later invoke found the retained temporary server already present and refused duplicate creation. Start chronology is uncertain; no successful second start is inferred from that failed call. Read-only inspect captures plus independent netstat prove the two live binds. Future retries must inspect AppDomain state as well as output files and OS inventory before another invoke; missing output is not proof of no side effect.
- **Teardown verified:** both retained temporary servers reported stopped; independent netstat found no listener on 48991 and preserved primary mappings 48884→68276, 48885→88388, 48886→112992. Evidence: `C:/preflight/out/g5-48991-teardown.json`, with stop-capture hashes. The new test Revit remains open; no force-kill or unrequested model close. Same-port behavior was measured with genuine auxiliary RoutesServer instances, not automatic primary-port assignment. G5 blocks until its inventory mechanism is corrected and remeasured; overall checkpoint and G6 remain unapproved.

### G5 inventory correction and repeat blocker — 2026-10-16
- **Preflight-only correction:** `tests/test_phase2_preflight.py` now runs full `netstat.exe -ano -p tcp` without shell/port filtering or Get-NetTCPConnection fallback. The pure parser retains distinct LISTENING PIDs for duplicate endpoints, wildcard and IPv6 binds; malformed rows on any port, unknown/localized states, header-only output, launch/decode/timeout/nonzero failures return unavailable (STOP), not an empty inventory. English/Russian headers are recognized; other formats conservatively refuse. The legacy JSON parser remains unused by OS collection. G5 classifier and `approval=not-granted` are unchanged; this is not a production discovery implementation or race-free port reservation.
- **Offline verification:** 40 added regressions include the exact-shaped historical dual-bind rows (112992 and 88388), deduplication, scoped IPv6, known non-listening states, malformed output and subprocess failure/command contracts. RED was observed before implementation; the complete preflight unit file then passed 303 tests. Synthetic/replayed rows are not a new live G5 pass.
- **Fresh read-only OS observation:** corrected collection returned 48884→68276, 48885→88388, 48886→112992 and no listener on 48991. Get-Process independently showed those Revit processes still running. No HTTP request was made for this observation.
- **Repeat not executed:** the controller prepared a scratch-only repeat harness with exclusive attempt/evidence files and an in-button CreateNew claim to prevent repeated execution/overwrite after missing output. Its first inspect command was denied by the permission boundary because it would rewrite the disposable diagnostic `phase2-preflight.extension/Preflight.tab/Probes.panel/SETUP.pushbutton/script.py`. No alternate tool or process was used to bypass that denial; no new temporary server was created. Resuming the live repeat needs permission for that exact diagnostic target. Historical STOP evidence is preserved; G5, the overall checkpoint and G6 remain unapproved.

### G5 corrected live repeat — 2026-10-16
- **Explicit target authorization:** the user explicitly permitted rewriting `C:/Users/Admin/AppData/Roaming/pyRevit/Extensions/phase2-preflight.extension/Preflight.tab/Probes.panel/SETUP.pushbutton/script.py` and the bounded G5 repeat with teardown of only its temporary servers. The earlier permission blocker is resolved for this diagnostic scope, not for either MCP extension or shared configuration.
- **Control recovery:** the first inspect controller timed out while enumerating top-level UI Automation windows, before reaching its button Invoke call. OS socket/process inspection showed unchanged primary mappings and no 48991 listener. Native EnumWindows found the exact Autodesk Revit main windows; fresh attempt/evidence names were used. Subsequent in-process inspections confirmed no retained temporary server in either PID. One-shot CreateNew claims prevent a repeated button click from repeating an operation or overwriting its capture.
- **Measured repeat:** both Revit PIDs 88388 and 112992 successfully created a genuine installed `pyrevit.routes.server.server.RoutesServer` bound to `127.0.0.1:48991`, with live threads. Corrected `os_listener_snapshot([48991])` returned `[112992, 88388]`; a separate full netstat capture showed the same two owners and Get-Process confirmed both Revit processes. No HTTP request, including status, was sent to 48991. Separate netstat calls share the OS backend; independent implementation diversity is not claimed. Retained-server captures plus exact socket rows corroborate process ownership.
- **Provenance correction, not rewritten evidence:** the initial repeat result omitted mandatory `live`/`synthetic` flags and correctly classified STOP. The original `C:/preflight/out/g5-netstat-repeat-20261016-b-classification.json` is preserved. A separate record validates 34 SHA256-referenced raw captures (inspect/start/stop, invocation, pre-action observations and teardown), adds explicit `live=true, synthetic=false` provenance and classifies `listener-inventory-complete`: `C:/preflight/out/g5-netstat-repeat-20261016-b-with-provenance.json`. The classifier and measured PID sets were not changed.
- **Teardown confirmed:** both owned temporary servers stopped, subsequent AppDomain inspections found neither retained object, and full netstat showed no 48991 listener. Primary mappings remained 48884→68276, 48885→88388, 48886→112992. Evidence: `C:/preflight/out/g5-netstat-repeat-20261016-b-teardown.json`. No document mutation/save/sync, execute_code, Reload, force-kill, model close or foreign-extension change. Revit processes remain open.
- **Decision boundary:** G5's inventory feasibility gate is now measured as `listener-inventory-complete`; auxiliary-server collision does not prove automatic primary-port assignment or an implemented production pre-send refusal. Formal G1–G5 reconciliation and the overall checkpoint decision remain separate: overall STOP / approval not granted, no broad Phase 2 implementation or G6 authorization.

### Human checkpoint acceptance — 2026-10-16

User decision: «Принимаю чекпоинт, давай дальше». This supersedes the earlier pending human approval, not historical STOP measurements. Proceed only to existing 02-01 selected-status implementation; production live verification remains 02-02. G6 and the wider rollout are not authorized by this decision.

Accepted mechanisms: G1 startup GUID retained in AppDomain and actual bound RoutesServer port, explicit-route-only; G2 retained-reference-equals-v1 with lifetime validity/unique Equals and permanent tombstones; G3 explicit-document summary/levels; G4 measured saved-existing-path activation only, otherwise refusal; G5 full netstat inventory with fail-closed parsing. D-15 remains the trusted arbitrary-code exception, both execute capabilities enabled, no confinement claim.

G1 timing is extension startup in a fresh process, **not literal OS process creation**. The classifier's historical `process-start` literal is not evidence of stronger timing: no synthetic aggregate PASS is manufactured and raw captures remain unchanged. Older G1 execute-code-pending wording is superseded by D-15. G5 provenance-corrected evidence is separate from the original correctly refused capture; both are retained. See 02-20-SUMMARY.md for evidence pointers and limitations.

### Claude's Discretion
- Exact process/document selector encoding, key format, discovery mechanism, where common response formatting lives, wrapper structure, and message wording, provided the visible behaviors above hold and security work is not pulled forward from Phases 3/5.
- Whether additional read-only routes are proven safe for nonactive documents after the minimum summary/levels comparison works. Do not classify an unmeasured route as safe by analogy.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and prior decisions
- `.planning/ROADMAP.md` §Phase 2, §Phase 5, Backlog 999.1 — boundary, nine criteria, carried per-call target/per-target lock, and deferred Revit-side fix.
- `.planning/REQUIREMENTS.md` §IDENT, §AMBIG, §MDOC — requirement contracts and traceability.
- `.planning/STATE.md` §Accumulated Context — Phase 1 outcome, unresolved bench measurements and outstanding risks.
- `.planning/phases/01-serialization-and-configurable-addressing/01-CONTEXT.md` D-28..D-30 — only `/status/` unlocked, a5-a one shared entry, d27-c backlog.
- `.planning/phases/01-serialization-and-configurable-addressing/01-04-SUMMARY.md` §Bench record — observed pyRevit overlap; do not replace with assumptions.
- `.planning/debug/param-write-rolls-back.md` — hypothesis to recheck live.

### Research and implementation constraints
- `.planning/research/ARCHITECTURE.md` §Question 1, §Question 2 — candidate chokepoint and response attribution (reassess pre-d27-b read advice).
- `.planning/research/PITFALLS.md` §Pitfall 14, §Pitfall 15 — stale document and Document/UIDocument risks (reassess pre-d27-b lock advice).
- `CLAUDE.md` §The Two-Runtime Rule, §Non-negotiable invariants, §Known sharp edges — IronPython 3.4 syntax, request parsing, route errors, restarts, duplicate listeners and honest queue scope.
- `bridge.py` — current fixed target, injected transports, global lock and only `/status/` exemption.
- `tools/status_tools.py`, `tools/utils.py` — status target display and tool-visible formatting.
- `startup.py`, `revit_mcp/status.py`, `revit_mcp/model_info.py`, `revit_mcp/worksharing.py`, `revit_mcp/document.py` — route registration, active-document reads, open/activate behavior and Save outside a transaction.
- `tests/unit/tool_manifest.txt` — authoritative MCP tool list when adding capabilities.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Injected `revit_get`/`revit_post`/`revit_image` and centralized `_revit_call` in `bridge.py` provide the transport boundary; `UNLOCKED_GET` currently contains only `status`.
- `/open_model/` has workset-aware opening logic, but it is not proof that activation of an already-open or unsaved document works.
- Existing `get_revit_model_info` and level listing cover the requested comparison data for the **active** document; inactive-document routing must be established rather than assumed.

### Established Patterns
- Response formatting regards a dict as error only for a truthy `error` or error-like status. Identity fields must not masquerade as failures; HTTP non-200 refusals must render visibly.
- Revit route modules use relative imports and are registered by convention. POST uses `text/plain` plus `parse_request_data()`. Transactions suppress warnings immediately after start; Save/SaveAs occur outside a transaction.

### Integration Points
- `bridge.py` target selection and per-target lock; tool call arguments/docstrings; status and discovery tools; Revit-side identity/document resolution and safe read routes; response formatting; manifest and unit/live acceptance.

</code_context>

<specifics>
## Specific Ideas

- Compare a model summary and its levels from two documents in one assistant session without changing the engineer's active UI where those two reads are proven safe.
- A refusal for multiple processes or documents lists the exact candidates so the assistant can retry deliberately; a process restart requires re-selection.
- An explicitly selected inactive document is readable on the supported comparison surface but not mutable until the engineer explicitly activates it (412).

</specifics>

<deferred>
## Deferred Ideas

- Live secret gate and file-integrity enforcement from the former Phase 4 `--auto` context D-01..D-05 → Phase 5 (logic built in Phase 3); do not carry their secret-in-`_mcp`, 401 or 423 wiring into Phase 2.
- Mutation of an inactive document without explicit activation → future capability only after Document/UIDocument behavior is proven.
- Cross-session pyRevit handler synchronization → `.planning/ROADMAP.md` backlog 999.1 (d27-c); a per-target lock in this MCP process is not that fix.

</deferred>

---

*Phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin*
*Context gathered: 2026-10-14*
