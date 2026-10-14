---
slug: param-write-rolls-back
status: awaiting_human_verify
trigger: |
  Дефект записи параметров через RevitMCP Routes: изменения откатываются после завершения HTTP-запроса.
  Через /revit_mcp/execute_code/ запись в параметры элементов не сохраняется между запросами.
  Внутри одного запроса всё успешно (Set() -> True, Commit() -> Committed, HasValue=True),
  но следующий запрос видит пустое значение. Модель при этом doc.IsModified = False.
  Затрагивает и пользовательские, и встроенные параметры Revit.
created: 2026-09-17
updated: 2026-10-07
---

# Debug Session: param-write-rolls-back

## Symptoms

**Expected behavior:**
A parameter value written through `/revit_mcp/execute_code/` (or `/set_parameter/`,
`/modify_element/`) persists in the model and is visible to the next HTTP request.

**Actual behavior:**
The write appears to succeed within the request, then silently disappears. The next
request reads an empty value. `doc.IsModified` stays `False`, i.e. Revit does not
consider the document changed at all.

**Error messages:**
None. Every response reports `"status": "success"`. The failure is entirely silent —
this is a core part of the complaint.

**Timeline:**
Reported as reproducing consistently, dozens of times, across Revit restarts.

**Reproduction:**
Step 1 — `POST /revit_mcp/execute_code/`:
```python
p = w.LookupParameter("MR_Подземная часть")
st = SubTransaction(doc); st.Start()
p.Set(0)
st.Commit()
```
Response: `HAS_VALUE_before=True | Set_returns=True | commit=Committed | HasValue_after=True`

Step 2 — `GET /revit_mcp/element_properties/8850561`:
`MR_Подземная часть | Integer | value=''`

**Key discriminating observation (narrows this a lot):**
Element *creation* through the same endpoint DOES persist — `Level.Create()` + `Commit()`
yields a real level visible in the next request. So the outer transaction commits in
general; it is specifically edits to existing elements that vanish.

## Eliminated

The reporter has already excluded, by direct test:
- hypothesis: own `Transaction` is the problem — not viable, an outer transaction is already open
- hypothesis: missing `Regenerate()` — tested, no effect
- hypothesis: only `/execute_code/` is affected — no, stock `/set_parameter/` and
  `/modify_element/` also report success with no model change
- hypothesis: wrong value type — tested `Set(str/unicode/System.String)` and `SetValueString`
- hypothesis: binding/permission — `IsReadOnly=False`, `IsShared=True`
- hypothesis: element grouped / pinned — checked
- hypothesis: type-vs-instance parameter confusion — checked
- hypothesis: batch size — tested 1 … 4784 elements
- hypothesis: Cyrillic parameter names — latin names behave the same
- hypothesis: stale Revit state — Revit restarted

## Evidence

- timestamp: 2026-09-17 (orchestrator, static read before delegation)
  `revit_mcp/utils.py:19-35` — `_FailureSwallower.PreprocessFailures` returns
  `DB.FailureProcessingResult.ProceedWithRollBack` when ANY failure message of
  severity `Error` is present, and logs nothing when it does so. The rollback is
  therefore invisible to both the client and the log.

- timestamp: 2026-09-17 (orchestrator, static read before delegation)
  `revit_mcp/code_execution.py:104` — `t.Commit()` return value is DISCARDED.
  In the Revit API `Transaction.Commit()` returns a `TransactionStatus`; when the
  failure preprocessor answers `ProceedWithRollBack`, Commit returns
  `TransactionStatus.RolledBack` rather than raising. Line 106 then unconditionally
  returns `"status": "success"`. This exactly matches the reported symptom shape:
  silent rollback + false success.

- timestamp: 2026-09-17 (orchestrator, static read before delegation)
  `revit_mcp/utils.py:49-56` — `suppress_warnings` wraps everything in
  `except Exception: pass`, so a failure to install the handling options is also silent.

- timestamp: 2026-10-07 (01-04 bench, pyRevit 6.5.3, Revit 2024.3.30)
  Two overlapping `/execute_code/` POSTs to one Revit through pyRevit's shared request
  handler gave verdict `cross-wired-mutation`, run twice with identical verdicts: the second
  request answered HTTP 200 carrying the first request's output, and its own code never ran
  (run count A=1, B=0). A read overlapping a mutation returned the mutation's output
  (`cross-wired-read`). `/status/` was unaffected (0.01-0.02 s). Source: 01-04-SUMMARY.md
  "Bench record", Step 7. See `second_candidate` under Current Focus.

## Current Focus

reasoning_checkpoint:
  hypothesis: "The outer DB.Transaction opened by each edit route (execute_code,
    set_parameter, modify_element) is silently rolled back at Commit() because
    _FailureSwallower.PreprocessFailures returns ProceedWithRollBack whenever any
    error-severity FailureMessage is present on the transaction, and every route
    discards the TransactionStatus that Commit() returns, then unconditionally
    reports status=success. Element creation (placement.py, Level.Create) uses the
    identical Transaction/Commit pattern but does not go through the rollback path
    because creating an element does not raise an error-severity failure the way
    editing an existing element's parameter can (constraint/validation checks fire
    on existing elements, not on brand-new ones in the same transaction)."
  confirming_evidence:
    - "utils.py:19-35 _FailureSwallower.PreprocessFailures: DeleteAllWarnings() then
      for any FailureMessage with GetSeverity()==Error, returns
      ProceedWithRollBack; no logging on either branch."
    - "code_execution.py:104-117 discards t.Commit() return value and
      unconditionally returns status=success two lines later."
    - "parameters.py:492-507 (set_parameter_handler) has the identical
      Commit-discarded-then-success pattern."
    - "editing.py:227-243 (modify_element_handler) has the identical pattern."
    - "placement.py:408 (element creation) uses the same Transaction + suppress_warnings
      + discarded Commit() pattern, yet creation is reported by the reporter to
      persist — consistent with creation not triggering an error-severity failure,
      not with the transaction/commit machinery itself being sound for edits."
    - "doc is pyRevit-injected revit.doc identically across every route
      (status.py:60-61, code_execution.py:42, all handlers read doc as first
      positional arg) — one active document, same injection path for reads and
      writes, and element_properties correctly resolves the same element_id/
      category/family/type across requests, which is inconsistent with a
      doc-identity mismatch and consistent with the same document simply not
      having the edit applied."
  falsification_test: "Add TransactionStatus capture + failure-message logging
    (severity, description, failing element ids) to all three edit routes and to
    _FailureSwallower, then have the reporter re-run the Step 1 repro against a
    live Revit/pyRevit session. If Commit() returns Committed and no error-severity
    failure is logged, this hypothesis is wrong and the doc-context/other-mechanism
    line must be pursued instead. If Commit() returns RolledBack and a specific
    error-severity FailureDefinitionId is logged, the hypothesis is confirmed and
    that failure ID is the true root cause of why edits (not creates) roll back."
  fix_rationale: "The fix makes the existing rollback observable instead of
    changing transaction behavior: log every failure message before deciding a
    verdict, capture the real TransactionStatus, and surface it (plus any logged
    failures) in the JSON response instead of a hardcoded status=success. This
    addresses the reporter's request 1 directly (rollback is invisible) and is a
    real, independently valuable fix regardless of what the logged failure turns
    out to be — it replaces false-success with either true-success or a diagnosable
    failure. It does not yet address a deeper root cause for the error-severity
    failure itself (e.g. a specific constraint on MR_* shared parameters) because
    that cannot be observed without a live run; the log output from this fix is
    exactly what's needed to identify it next."
  blind_spots: "Cannot run Revit in this environment, so this hypothesis is not yet
    confirmed by a live TransactionStatus/failure-message observation — only by
    static code reading. It remains possible the real cause is something the static
    read cannot see (e.g. a worksharing ownership conflict, a central-model sync
    interaction, or a specific parameter constraint) that also happens to produce
    an error-severity failure only on edit, not create. The doc-context hypothesis
    is weakened but not fully eliminated by static reading alone (e.g. two Revit
    processes both bound to :48884 per the repo's own documented sharp edge would
    also be consistent with 'writes vanish, doc.IsModified stays False' if the
    request that returns success is served by a *different* process/doc instance
    than the one central status.py reports on) — should be flagged to the reporter
    as a parallel check via Get-NetTCPConnection."
  blind_spots_addendum: "Added 2026-10-07: a mechanism not known when the hypothesis above
    was written (a write that never runs because its request was cross-wired inside
    pyRevit's shared handler) is recorded in second_candidate below."

second_candidate:
  added: 2026-10-07 (from the 01-04 bench, follow-up item 8 of 01-04-SUMMARY.md)
  hypothesis: "A write that 'vanishes' may never have run. Its request overlapped another
    request in pyRevit's shared request handler, was answered 200 carrying the other
    request's payload, and Revit never executed its body, so doc.IsModified stays False
    and the next read sees the old value."
  confirming_evidence:
    - "01-04 Step 7 verdicts (see Evidence, 2026-10-07): cross-wired-mutation (the overlapped
      mutation answered 200 with the other caller's output, its own body ran 0 times) and
      cross-wired-read, reproduced twice with identical verdicts."
    - "The reporter's repro issued requests from tooling that, before plan 01-06, did not
      serialize reads against writes (the read-only allowlist of plan 01-02 sent reads around
      the lock), and any second assistant session or curl is never serialized by bridge.py."
  discriminating_test: "Repeat Step 1 then Step 2 once strictly sequentially through one MCP
    server process after plan 01-06 (every call except /status/ is locked), and once with a
    second request deliberately overlapping the write. Check whether the write's own response
    carries its own transaction_status and its own printed output; a cross-wired answer carries
    the other request's payload. A loss only under overlap confirms this mechanism. A loss in
    the strictly sequential run with transaction_status: Committed in the write's own response
    rules it out for that run."
  relation_to_first: "Independent of the rollback hypothesis; both can be true. Phase 2
    AMBIG-04 re-runs the repro with identity visible, and backlog item 999.1 (d27-c) is the
    fix for the cross-process case."

next_action: DONE (fix implemented, static checks pass). Awaiting reporter's live
  reproduction per the human-verify checkpoint below — cannot run Revit in this
  environment. Reporter should re-run Step 1 from Symptoms and report back the
  `transaction_status` / `failures` field from the response, plus check for a
  second `:48884` listener as a parallel line of investigation.

## Constraints for this investigation

- The Revit half (`revit_mcp/`) is IronPython 3 at Python-3.4 language level: no
  f-strings, use `"{}".format(x)`. Relative imports only (`from .utils import ...`).
- Live verification needs Revit open with a document and pyRevit Routes on :48884.
  Confirm exactly one listener: `Get-NetTCPConnection -LocalPort 48884 -State Listen`.
- After editing `revit_mcp/`, pyRevit Reload is NOT safe — fully close and reopen Revit.
- The model currently contains diagnostic residue from the reporter that must NOT be
  treated as real data and should be cleaned once writes work: 9 walls with
  `MR_Подземная часть = 1`, 5 walls with junk `MR_Секция` (M1, M2, M3, TEST50, NEWVALUE),
  3 walls with test `MR_Корпус`.

## Resolution

root_cause: NOT YET CONFIRMED LIVE (static analysis only — this environment cannot
  run Revit). Leading, evidence-backed hypothesis: `/execute_code/`, `/set_parameter/`,
  and `/modify_element/` all discard the `TransactionStatus` returned by `t.Commit()`
  and unconditionally report `status: "success"`. `_FailureSwallower.PreprocessFailures`
  (utils.py) returns `ProceedWithRollBack` whenever any error-severity FailureMessage
  is present on the transaction, which silently rolls the whole transaction back
  (Commit() then returns RolledBack) with zero logging. This is fully consistent with
  every reported symptom: success reported, `doc.IsModified` stays False, edits vanish,
  while element *creation* (which does not trigger an error-severity failure) persists
  through the identical Transaction/suppress_warnings/Commit pattern in placement.py.
  What specific error-severity failure fires on edit-of-existing-element (e.g. a
  constraint tied to the `MR_*` shared parameters, a worksharing/ownership check, or
  something else) is NOT yet known — the fix below makes it observable but a live run
  is required to read the actual FailureDefinitionId/description.

fix: Added `commit_and_report(transaction, swallower)` to `revit_mcp/utils.py`, which
  calls `transaction.Commit()`, captures the real `TransactionStatus`, and returns
  `{committed, transaction_status, failures}`. `suppress_warnings()` now returns the
  `_FailureSwallower` instance (previously discarded) instead of None, and
  `_FailureSwallower.PreprocessFailures` now logs every failure message (severity,
  description via `GetDescriptionText()`, failing element ids via `GetFailingElements()`)
  at `logger.error`/`logger.warning` before deciding a verdict, and records them on
  `self.failures` for the caller to read. All three edit routes
  (`code_execution.execute_code`, `parameters.set_parameter_handler`,
  `editing.modify_element_handler`) now call `commit_and_report` instead of a bare
  `t.Commit()`, and return HTTP 409 with `status: "rolled_back"`, the real
  `transaction_status`, and the `failures` list when the transaction did not actually
  commit — instead of the previous hardcoded `status: "success"`. On a genuine commit,
  the response now also includes `transaction_status: "Committed"` for confirmation.
  This satisfies the reporter's request 1 (rollback is no longer invisible — it is
  logged AND returned in the HTTP response) directly. It does not change any Revit
  document-mutation behavior; it only reports the truth about what `Commit()` did.

verification: Static only — `revit_mcp/` cannot be imported or executed under CPython,
  so this fix has NOT been exercised against a live Revit/pyRevit process. Human
  verification is required — see checkpoint below. What WAS verified here:
  - `python scripts/conventions.py` → exit 0 (no f-strings, no flat imports,
    encoding cookies intact). Independently re-checked via `ast.JoinedStr` walk over
    all four changed files: 0 f-strings, line-1 cookie present in each.
  - `uv run pytest tests/unit` → 322 passed, 3 skipped. The 3 skips are the
    pre-existing live-Revit-only tests, unaffected. (320→322: two tests added, below.)
  - `python tests/test_init_latency.py` → INIT_LATENCY_S=1.104, under the 2.0s gate.
  - `tool_manifest.txt` deliberately NOT touched: no tool was added or renamed, only
    response payloads changed, so the manifest still matches.
  - `deploy/gate.py` cannot run in the dev tree at all (it targets a *deployed*
    payload and needs `deploy/libs` + `app/server.py` from build-payload.cmd; the
    directory does not exist here). Its "Connection closed" is an environment
    artifact, NOT a regression from this change. `tests/test_init_latency.py` is the
    dev-tree equivalent and passes.

  END-TO-END TRANSPORT TRACE (the part that makes the 409 actually work — traced
  statically, worth recording because it is a non-obvious coupling):
  `main.py:93` in `_revit_call` returns `f"Error: {status_code} - {text}"` for ANY
  non-200 response. So a 409 never parses into a dict — it reaches the tool layer as
  a STRING carrying the failures payload verbatim, and `format_response` passes
  strings through untouched. The rollback therefore surfaces to the model as a
  visible error with the failure descriptions inline. This was checked because of a
  real latent trap: `format_response` (tools/utils.py) classifies a dict as an error
  only on a truthy "error" key or status in error/failed/failure/exception —
  "rolled_back" is in NONE of those. Had the routes returned 200 with
  status="rolled_back" instead of 409, the false success would have survived the
  whole fix, and for /execute_code/ specifically format_response would have returned
  response["output"] (the captured stdout, which still reads as if the code worked).
  The 409 status code is thus load-bearing, not cosmetic — do not "soften" it to 200.

  REGRESSION TESTS ADDED (tests/unit/test_format_response.py, +2):
  - `test_rolled_back_409_reaches_the_model_as_a_visible_error` pins the working path.
  - `test_rolled_back_dict_is_not_yet_a_recognized_failure_signal` is a deliberate
    alarm test documenting the trap above: if `_revit_call` is ever changed to parse
    non-200 bodies into dicts, that test's premise breaks and the silent-false-success
    bug returns. It failing is the intended signal to re-verify, not a nuisance.

files_changed:
  - tests/unit/test_format_response.py (+2 tests pinning the rolled_back/409 contract
    and the format_response "rolled_back" trap)
  - revit_mcp/utils.py (added logging + failing-element capture to
    _FailureSwallower.PreprocessFailures; suppress_warnings now returns the
    swallower instead of None; added commit_and_report helper)
  - revit_mcp/code_execution.py (execute_code uses commit_and_report, returns
    409/rolled_back with transaction_status + failures on non-commit)
  - revit_mcp/parameters.py (set_parameter_handler uses commit_and_report, same
    409/rolled_back behavior)
  - revit_mcp/editing.py (modify_element_handler uses commit_and_report, same
    409/rolled_back behavior)
