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
