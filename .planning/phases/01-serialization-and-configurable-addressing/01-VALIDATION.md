---
phase: "1"
slug: "serialization-and-configurable-addressing"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-06"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + anyio 4.9.0 plugin (`@pytest.mark.anyio`, backend pinned to `asyncio`), `httpx.MockTransport` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options] testpaths = ["tests/unit"]`; fixtures in `tests/unit/conftest.py` |
| **Quick run command** | `uv run pytest tests/unit/test_bridge_serialization.py -q` |
| **Full suite command** | `uv run pytest tests/unit` (baseline: 337 passed, 3 skipped) |
| **Estimated runtime** | ~2 seconds (full unit suite); quick run < 1 s |

Additional gates: `uv run python tests/test_init_latency.py` (< 2.0 s, D-24); `deploy/gate.py` run from a staged local copy of the app layout (D-20, 01-03-T2). `deploy\build-payload.cmd` is never run for verification: it publishes to the fleet share.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_bridge_serialization.py -q` (plus retargeted transport/textutils tests once `bridge.py` exists)
- **After every plan wave:** Run `uv run pytest tests/unit` and `python tests/test_init_latency.py`
- **Before `/gsd-verify-work`:** Full unit suite, latency gate and payload gate green; live bench recorded
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

Task IDs filled by the planner on 2026-10-06 (`01-PP-Tn` = plan PP, task n). Threat refs point at the
`<threat_model>` registers in the PLAN files.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01 | 1 | SER-01 / SC1 | T-01-04 | Second mutating POST not sent while first held | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k second_post_waits -q` | ❌ W0 (created by 01-01-T1) | ⬜ pending |
| ~~01-01-T1, 01-02-T3~~ → 01-06-T1, 01-06-T2 | 06 | 3 | SER-02 (narrowed by d27-b) / SC2 | T-01-10 | GET `/status/` returns < 1 s while the lock is held; GET reads, `/model_info/` (through the tool layer), former allowlist POSTs and `revit_image` wait for release. The 01-02 "reads pass while locked" tests are replaced (D-28) | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k "d27b or passes_while_locked or waits_while_locked" -q` | ❌ W0 (01-06) | ⬜ pending |
| 01-02-T2 | 02 | 2 | SER-03 / SC3 | T-01-07 | Lock released on exception, post-send timeout, holder and waiter cancellation; FIFO order | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k releases -q` | ❌ W0 | ⬜ pending |
| 01-02-T1 | 02 | 2 | SER-04 / SC4 | T-01-06 | Queued call keeps its full timeout (all four httpx components); over-bound wait returns "NOT sent to Revit" without sending | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k "budget_not_shrunk or queue_bound" -q` | ❌ W0 | ⬜ pending |
| 01-02-T2 | 02 | 2 | D-13 | T-01-06 | Post-send failure → "outcome UNKNOWN"; pre-send connect/pool error → "was not sent to Revit"; never a bare "Error: " | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k outcome_unknown -q` | ❌ W0 | ⬜ pending |
| ~~01-02-T3~~ → 01-06-T1, 01-06-T2 | 06 | 3 | D-28 (supersedes D-08) / D-09 | T-01-26 | `UNLOCKED_GET` is exactly {status}; `READ_ONLY_POST` gone; never-unlocked routes stay locked even if listed; unknown, empty and prefix routes lock; drift scan of every `revit_get`/`revit_post`/`revit_image` endpoint in `tools/*.py` (≥ 40) | unit (static) | `uv run pytest tests/unit/test_bridge_serialization.py -k unlocked -q` | ❌ W0 (01-06) | ⬜ pending |
| 01-06-T2 | 06 | 3 | SER-01 ordering, SER-04 for reads, D-12, D-13 | T-01-10, T-01-24 | `revit_image` locked through `_serialized`; GET/image queue bound returns NOT sent; GET keeps full budget; mixed GET/POST/image FIFO; locked GET failure never says outcome UNKNOWN; wait wording does not call the holder a mutation | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k "image or queue_bound or budget or arrival_order or wait_message or not_outcome_unknown" -q` | ❌ W0 (01-06) | ⬜ pending |
| 01-02-T2 | 02 | 2 | D-14 | T-01-09 | One `ctx.info` when waiting, none otherwise; raising `ctx.info` does not fail call | unit (fake ctx) | `uv run pytest tests/unit/test_bridge_serialization.py -k wait_message -q` | ❌ W0 | ⬜ pending |
| 01-01-T2 | 01 | 1 | IDENT-05 / SC5 (code) | T-01-01, T-01-02 | Strict `REVIT_PORT` parse incl. 1/65535 and 0/65536; refusal exit 2 on stderr, stdout empty; `BASE_URL` carries the port; literal 48884 only in `DEFAULT_REVIT_PORT` | unit | `uv run pytest tests/unit/test_bridge_serialization.py -k port -q` | ❌ W0 | ⬜ pending |
| 01-03-T1 | 03 | 2 | D-06 | T-01-11 | `get_revit_status` ends with `MCP target: host:port` for dict, message-dict and str responses; unchanged without the attribute | unit | `uv run pytest tests/unit/test_status_target.py -q` | ❌ W0 | ⬜ pending |
| 01-03-T1 | 03 | 2 | IDENT-05 / D-17 (harness, offline) | T-01-11 | Two stdio entries with ports 48997/48998 each report their own target; harness exits 1 with `TWO_INSTANCE_FAIL` when nothing listens | script (stdio) | `uv run python tests/test_two_instance_targets.py --ports 48997,48998` (expect exit 1 + both `target=` lines) | ❌ W0 | ⬜ pending |
| 01-01-T1 | 01 | 1 | D-20 | T-01-03 | `trust_env=False` and text/plain POST marker live in `bridge.py` | unit (retargeted) | `uv run pytest tests/unit/test_local_bridge_transport.py tests/unit/test_textutils.py -q` | ✅ retarget | ⬜ pending |
| ~~01-05-T1, 01-05-T2~~ → 01-07-T1, 01-07-T2 | 07 | 4 | SER-05 / SC6, SER-02 docs, IDENT-05 docs | T-01-19, T-01-20, T-01-23, T-01-27 | Docs pin the process-local scope, "only `/status/` skips the queue" and "cross-wire until d27-c" (English, plus a Russian sentence for engineers); over-claim scan over five docs; no two-entry user docs; `REVIT_PORT` only as a deployment setting | unit (doc pin) | `uv run pytest tests/unit -k serialization_scope -q` (8 tests) | ❌ W0 (01-07) | ⬜ pending |
| 01-08-T1, 01-08-T2 | 08 | 1 | SER-02 text, SC2/SC5/SC6, Phase 2 per-target lock, d27-c backlog | T-01-23, T-01-28, T-01-29 | Requirement and roadmap text match d27-b / a5-a; backlog 999.1 carries the bench evidence; executed history changed by added lines only | doc check (grep/awk) | see the `<verify>` blocks of 01-08-PLAN.md Tasks 1-2 (`git diff --numstat 791a8d2` append-only check included) | n/a | ⬜ pending |
| 01-08-T3 | 08 | 1 | debug lead (follow-up item 8) | — | `.planning/debug/param-write-rolls-back.md` gains the cross-wiring candidate and a discriminating test; original hypothesis intact | doc check (grep) | `grep -c 'cross-wired' .planning/debug/param-write-rolls-back.md` (≥ 2) | n/a | ⬜ pending |
| 01-01-T1 | 01 | 1 | D-19 | — | `bridge` imports without FastMCP | unit | `uv run python -c "import sys, bridge; assert 'mcp.server.fastmcp' not in sys.modules"` (also `test_bridge_imports_without_fastmcp`) | ❌ W0 | ⬜ pending |
| 01-01-T1, 01-02-T3, 01-06-T2, 01-07-T2 | 01, 02, 06, 07 | 1, 2, 3, 4 | D-24 | — | Cold start < 2.0 s | script | `uv run python tests/test_init_latency.py` | ✅ | ⬜ pending |
| 01-03-T2 | 03 | 2 | D-20 | T-01-12, T-01-14 | Payload copy list includes every root module `main.py` imports; staged local app layout passes `gate.py` | unit + staged gate | `uv run pytest tests/unit/test_payload_ships_root_modules.py -q` and the staged `gate.py` run in 01-03-T2 (never `deploy\build-payload.cmd`, which publishes to the fleet share) | ❌ W0 | ⬜ pending |
| 01-04-T1 | 04 | 3 | D-23 (instrument) | T-01-15 | Probe classifier verdicts; offline run exits 2 with `OVERLAP_UNREACHABLE` | unit + script | `uv run pytest tests/unit/test_probe_handler_overlap.py -q` | ❌ W0 | ⬜ pending |
| 01-04-T2 | 04 | 3 | IDENT-05 / SC5 live, D-16, D-17, D-23, D-25, D-26 | T-01-16, T-01-17 | Staggered two-Revit bench, two-entry session, overlap probe, negative probes | **live, manual** | see Manual-Only Verifications | n/a | ⬜ pending |
| 01-04-T3 | 04 | 3 | D-18, D-27, A5 | T-01-17, T-01-10 | Conditional decision gate; nothing chosen unilaterally | checkpoint:decision | n/a | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_bridge_serialization.py` (01-01-T1) — module-scoped `anyio_backend` fixture returning `"asyncio"` and an autouse fixture resetting `bridge._lock` / `bridge._http_client` per test. Planner choice: these live in the test module, not `tests/unit/conftest.py` — only this module touches bridge globals, so no other test imports `bridge` or depends on `REVIT_PORT`; conftest stays unchanged
- [ ] `tests/unit/test_bridge_serialization.py` — tests for SER-01..SER-04, D-08/D-09, D-13, D-14, IDENT-05 (01-01, 01-02)
- [ ] `tests/unit/test_status_target.py` — fake `mcp` + fake `revit_get`, driven with `asyncio.run` like `test_registration.py` (01-03-T1)
- [ ] `tests/unit/test_payload_ships_root_modules.py` (01-03-T2), `tests/unit/test_probe_handler_overlap.py` (01-04-T1), `tests/unit/test_serialization_scope_docs.py` (01-07-T1; was 01-05-T1, superseded)
- [ ] Gap closure (2026-10-07): `tests/unit/test_bridge_serialization.py` lock-coverage rework — tracer `test_d27b_tool_path_model_info_waits_status_does_not` and the `unlocked` / `waits_while_locked` tests (01-06-T1, 01-06-T2)
- [ ] Retarget `tests/unit/test_local_bridge_transport.py` and `tests/unit/test_textutils.py::test_the_client_does_not_ask_pyrevit_to_parse_the_body` to `bridge.py` in the same commit as the move (01-01-T1)
- Framework install: none (pytest + anyio already in the dev group)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Two Revits on 48884/48885 with distinct PIDs; two stdio MCP entries each report own `host:port` + `document_title` | IDENT-05 / SC5, D-16, D-17, D-25, D-26 | Needs two live Revit processes | 01-04-T2 steps 1–6 (`tests/test_two_instance_targets.py` must print `TWO_INSTANCE_OK`); staggered start is the acceptance run (D-25); step 8 records a simultaneous launch |
| Overlapping `/execute_code/` POSTs + GET on one instance | D-23, D-27 | Needs live Revit; records pyRevit shared-handler behaviour | 01-04-T2 step 7 (`scripts/probe_handler_overlap.py`); `D27_TRIGGER=yes` stops at 01-04-T3 for the user's decision |
| Invalid / unreachable `REVIT_PORT` behaviour end-to-end | IDENT-05 | Exercises real process start | 01-04-T2 step 9 |
| **Open evidence gap:** overlap behaviour on the fleet's pyRevit 6.5.5 (RESEARCH A2) | SER-01, SER-02 (d27-b rationale) | Bench ran 6.5.3 only | Re-run `scripts/probe_handler_overlap.py` on 6.5.5 against a throwaway model, full Revit restart afterwards; backstop truth in 01-06-PLAN.md |
| **Open evidence gap:** `/model_info/` under overlap | SER-02 | Not measured on the 01-04 bench; it stays locked | Measure only if unlocking it is ever proposed; backstop truth in 01-06-PLAN.md |
| **Open evidence gap:** cross-version Revit pair (e.g. 2024 + 2027) | IDENT-05 / SC5 | Bench used two Revit 2024.3.30 | Repeat 01-04-T2 steps 2-5 with two versions; backstop truth in 01-08-PLAN.md |
| **Open evidence gap:** simultaneous launch | IDENT-05 (finding, not acceptance, D-25) | 01-04 Step 8 not performed | Start two Revit at once, record the ports per PID; confirms or corrects the docs' "can both land on 48884"; backstop truth in 01-07-PLAN.md |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
