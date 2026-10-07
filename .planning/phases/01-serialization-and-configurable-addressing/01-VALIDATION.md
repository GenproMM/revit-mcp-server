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
| 01-01-T1, 01-02-T3 | 01, 02 | 1, 2 | SER-02 / SC2 | T-01-10 | GET (01-01), image and allowlisted POST (01-02) return < 1 s while lock held | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k reads_pass_while_locked -q` | ❌ W0 | ⬜ pending |
| 01-02-T2 | 02 | 2 | SER-03 / SC3 | T-01-07 | Lock released on exception, post-send timeout, holder and waiter cancellation; FIFO order | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k releases -q` | ❌ W0 | ⬜ pending |
| 01-02-T1 | 02 | 2 | SER-04 / SC4 | T-01-06 | Queued call keeps its full timeout (all four httpx components); over-bound wait returns "NOT sent to Revit" without sending | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k "budget_not_shrunk or queue_bound" -q` | ❌ W0 | ⬜ pending |
| 01-02-T2 | 02 | 2 | D-13 | T-01-06 | Post-send failure → "outcome UNKNOWN"; pre-send connect/pool error → "was not sent to Revit"; never a bare "Error: " | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k outcome_unknown -q` | ❌ W0 | ⬜ pending |
| 01-02-T3 | 02 | 2 | D-08/D-09 | T-01-08 | Allowlist is exactly the five read-only routes; never-unlocked routes stay locked even if listed; unknown POST locked; drift scan vs `tools/*.py` | unit (static) | `uv run pytest tests/unit/test_bridge_serialization.py -k allowlist -q` | ❌ W0 | ⬜ pending |
| 01-02-T2 | 02 | 2 | D-14 | T-01-09 | One `ctx.info` when waiting, none otherwise; raising `ctx.info` does not fail call | unit (fake ctx) | `uv run pytest tests/unit/test_bridge_serialization.py -k wait_message -q` | ❌ W0 | ⬜ pending |
| 01-01-T2 | 01 | 1 | IDENT-05 / SC5 (code) | T-01-01, T-01-02 | Strict `REVIT_PORT` parse incl. 1/65535 and 0/65536; refusal exit 2 on stderr, stdout empty; `BASE_URL` carries the port; literal 48884 only in `DEFAULT_REVIT_PORT` | unit | `uv run pytest tests/unit/test_bridge_serialization.py -k port -q` | ❌ W0 | ⬜ pending |
| 01-03-T1 | 03 | 2 | D-06 | T-01-11 | `get_revit_status` ends with `MCP target: host:port` for dict, message-dict and str responses; unchanged without the attribute | unit | `uv run pytest tests/unit/test_status_target.py -q` | ❌ W0 | ⬜ pending |
| 01-03-T1 | 03 | 2 | IDENT-05 / D-17 (harness, offline) | T-01-11 | Two stdio entries with ports 48997/48998 each report their own target; harness exits 1 with `TWO_INSTANCE_FAIL` when nothing listens | script (stdio) | `uv run python tests/test_two_instance_targets.py --ports 48997,48998` (expect exit 1 + both `target=` lines) | ❌ W0 | ⬜ pending |
| 01-01-T1 | 01 | 1 | D-20 | T-01-03 | `trust_env=False` and text/plain POST marker live in `bridge.py` | unit (retargeted) | `uv run pytest tests/unit/test_local_bridge_transport.py tests/unit/test_textutils.py -q` | ✅ retarget | ⬜ pending |
| 01-05-T1, 01-05-T2 | 05 | 4 | SER-05 / SC6 | T-01-19, T-01-20 | Docs state process-local scope, name second client / curl / `/execute_code/`; pinned sentences; over-claim scan | unit (doc pin) | `uv run pytest tests/unit -k serialization_scope -q` | ❌ W0 | ⬜ pending |
| 01-01-T1 | 01 | 1 | D-19 | — | `bridge` imports without FastMCP | unit | `uv run python -c "import sys, bridge; assert 'mcp.server.fastmcp' not in sys.modules"` (also `test_bridge_imports_without_fastmcp`) | ❌ W0 | ⬜ pending |
| 01-01-T1, 01-02-T3, 01-05-T2 | 01, 02, 05 | 1, 2, 4 | D-24 | — | Cold start < 2.0 s | script | `uv run python tests/test_init_latency.py` | ✅ | ⬜ pending |
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
- [ ] `tests/unit/test_payload_ships_root_modules.py` (01-03-T2), `tests/unit/test_probe_handler_overlap.py` (01-04-T1), `tests/unit/test_serialization_scope_docs.py` (01-05-T1)
- [ ] Retarget `tests/unit/test_local_bridge_transport.py` and `tests/unit/test_textutils.py::test_the_client_does_not_ask_pyrevit_to_parse_the_body` to `bridge.py` in the same commit as the move (01-01-T1)
- Framework install: none (pytest + anyio already in the dev group)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Two Revits on 48884/48885 with distinct PIDs; two stdio MCP entries each report own `host:port` + `document_title` | IDENT-05 / SC5, D-16, D-17, D-25, D-26 | Needs two live Revit processes | 01-04-T2 steps 1–6 (`tests/test_two_instance_targets.py` must print `TWO_INSTANCE_OK`); staggered start is the acceptance run (D-25); step 8 records a simultaneous launch |
| Overlapping `/execute_code/` POSTs + GET on one instance | D-23, D-27 | Needs live Revit; records pyRevit shared-handler behaviour | 01-04-T2 step 7 (`scripts/probe_handler_overlap.py`); `D27_TRIGGER=yes` stops at 01-04-T3 for the user's decision |
| Invalid / unreachable `REVIT_PORT` behaviour end-to-end | IDENT-05 | Exercises real process start | 01-04-T2 step 9 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
