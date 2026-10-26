---
phase: 07-repository-owned-mutation-safety-and-human-approval
plan: "11"
subsystem: approval-facts-and-fop
status: complete
---

# Phase 7 Plan 11 Summary

## Outcome

Connected the internal mutation preflight to CPython authorization, document pinning, the Russian confirmation window and the post-accept facts re-check. Shared-parameter additions require a company FOP GUID/name match; unavailable source evidence denies the addition.

## Changes

- `policy.py` strictly decodes UTF-16 LE/BE with BOM, UTF-8 with BOM and BOM-less UTF-8. PARAM records build immutable GUID/name indexes with NFC, case-sensitive names and canonical GUIDs. Conflicting GUID records are invalid; unresolved or ambiguous Revit definitions never match.
- Stat/read/parse runs through `asyncio.to_thread` under a three-second deadline, with a 16 MiB size bound and a bounded, two-second cache keyed by path/mtime/size. Cache hits do not extend entry age. A timed-out worker cannot publish a late cache entry. The post-accept FOP check bypasses the cache, including when metadata is unchanged.
- Authorization calls `/mutation_preflight/` through the bridge's same-target open-read seam for parameter, element, family and load facts. Document HTTP 400/404/412/503 refusals stop before a window and carry a sanitized, bounded Revit error excerpt. Other unavailable facts remain conservative rather than becoming an allow.
- D-10 decisions now use facts: a single empty instance parameter can proceed without a window; type, overwrite, group and unknown cases confirm. A successful document-bound preflight supplies the omitted document token, which is covered by the exact-body permit.
- After accept, policy hash is checked and the preflight is repeated with the pinned document. A changed document token, any changed fact or an unsuccessful re-check refuses with `facts_changed`. Shared additions must also still match a freshly read FOP.
- The Russian plain-text message includes operation code, time limit, tool/route/process, document, translated reasons and bounded facts/arguments. Unknowns remain explicit. Code gets length, SHA-256 prefix and an unchecked-safety warning; family load and parameter-definition deletion get their specific warnings. Total length is at most 1500 characters; details and code excerpts may be shortened to fit.
- String data is quoted, stripped of control characters before serialization (including nested values), and shortened to 120 characters with original length. Parameter details show current display/raw and requested raw values; type writes show instance impact counts or explicit unknown/capped counts.
- Existing consent fixtures now supply stable unknown preflight facts. Audit tests distinguish read-only preflight records from the mutation/decision record rather than assuming one audit entry per tool.

## Verification

All checks used the isolated `phase7-test-venv`, not a repaired or synchronized repository `.venv`.

- New integration RED: `14 failed, 2 passed`, before authorize integration.
- Consent/audit/tracer/policy regression suite after fixture updates: `91 passed`.
- Final new suites: `58 passed` (23 FOP, 18 message, 17 integration cases).
- Initial full suite under console code page 65001: `8 failed, 6851 passed, 3 skipped`; all failures were scratch deployment batch tests. A single scratch test reproduced the failure independently. Existing LF batch scripts were parsed incorrectly by cmd under CP65001.
- The same scratch test under a child cmd with code page 866 passed. Final full suite under that child process: `6860 passed, 3 skipped` in 116.55 seconds. Deployment scripts and persistent system settings were not modified.
- Cold start: `INIT_LATENCY_S=1.016` (limit 2 seconds).
- Owned source files decode as UTF-8 without BOM; `git diff --check` passed.
- `graphify update .` completed; generated graph artifacts are not part of this commit.

## Deviations and remaining evidence

- The public `edit_family` tool does not expose `add_shared_parameters`. Its source-policy integration is exercised by a test-only MCP tool calling the production bridge/authorizer; this plan does not expand the public tool API. Ordinary public family edits still use the production-tool harness.
- Stable `available: false` facts may be confirmed and rechecked when the document is known. A transport failure can open an unknown-facts window, but accept cannot authorize a mutation without a successful comparable re-check.
- The 1500-character limit necessarily bounds displayed detail for large batches: only the first three parameter fact entries are prepared, and later shared-name/argument lines or code excerpts can be cut. The digest still covers every returned fact, not only visible entries. No claim is made that a large batch's every value fits in the window.
- The preflight/re-check/send sequence is not atomic with respect to edits in another process or Revit itself. The underlying OS file read cannot be forcibly terminated by the coroutine deadline. These are residual limits, not safety guarantees.
- Company FOP format/encoding was verified against local fixtures only, not the actual corporate source. Revit API behavior and client display remain Plan 07-14 live evidence.
- No corporate share access, live Revit call, Revit reload/restart, actual deployment, release build, publication, push or tag occurred. Deployment tests wrote guarded temporary local paths only.

## Next

Plan 07-12: documentation and operator runbook. User-run live acceptance remains Plan 07-14; any live verification of the Revit-side changes requires a full Revit restart, not Reload.
