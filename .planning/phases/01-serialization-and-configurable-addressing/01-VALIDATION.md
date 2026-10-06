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

Additional gates: `python tests/test_init_latency.py` (< 2.0 s, D-24); `deploy\build-payload.cmd` → `deploy/gate.py` (D-20).

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_bridge_serialization.py -q` (plus retargeted transport/textutils tests once `bridge.py` exists)
- **After every plan wave:** Run `uv run pytest tests/unit` and `python tests/test_init_latency.py`
- **Before `/gsd-verify-work`:** Full unit suite, latency gate and payload gate green; live bench recorded
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

Task IDs are filled in by the planner/executor; rows are keyed by requirement until then.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | SER-01 / SC1 | — | Second mutating POST not sent while first held | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k second_post_waits -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SER-02 / SC2 | — | GET, image and allowlisted POST return < 1 s while lock held | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k reads_pass_while_locked -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SER-03 / SC3 | — | Lock released on exception, post-send timeout, cancellation, queue-bound expiry | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k releases -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SER-04 / SC4 | — | Queued call keeps its full read timeout; over-bound wait returns "NOT sent to Revit" without sending | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k "budget_not_shrunk or queue_bound" -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-13 | T-blind-retry | Post-send timeout → "outcome UNKNOWN"; pre-send connect error → "not sent" | unit (async) | `uv run pytest tests/unit/test_bridge_serialization.py -k outcome_unknown -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-08/D-09 | — | Allowlist is exactly the five read-only routes; unknown POST locked; drift scan vs `tools/*.py` | unit (static) | `uv run pytest tests/unit/test_bridge_serialization.py -k allowlist -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-14 | T-stdout | One `ctx.info` when waiting, none otherwise; raising `ctx.info` does not fail call | unit (fake ctx) | `uv run pytest tests/unit/test_bridge_serialization.py -k wait_message -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | IDENT-05 / SC5 | T-port-typo | Strict `REVIT_PORT` parse; refusal on stderr only, stdout untouched | unit | `uv run pytest tests/unit/test_bridge_serialization.py -k port -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-06 | T-port-typo | `get_revit_status` shows `host:port` for dict and str responses | unit | `uv run pytest tests/unit/test_status_target.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-20 | T-proxy | `trust_env=False` and text/plain POST marker live in `bridge.py` | unit (retargeted) | `uv run pytest tests/unit/test_local_bridge_transport.py tests/unit/test_textutils.py -q` | ✅ retarget | ⬜ pending |
| TBD | TBD | TBD | SER-05 / SC6 | T-overclaim | Docs state process-local scope, name second client / curl / `/execute_code/` | unit (doc pin) | `uv run pytest tests/unit -k serialization_scope -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-19 | — | `bridge` imports without FastMCP | unit | `uv run python -c "import sys, bridge; assert 'mcp.server.fastmcp' not in sys.modules"` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-24 | — | Cold start < 2.0 s | script | `python tests/test_init_latency.py` | ✅ | ⬜ pending |
| TBD | TBD | TBD | D-20 | — | Payload ships `bridge.py`; gate passes | build/gate | `deploy\build-payload.cmd` | ✅ edit | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/conftest.py` — `anyio_backend` fixture returning `"asyncio"`; autouse fixture resetting `bridge._lock` / `bridge._http_client` per test
- [ ] `tests/unit/test_bridge_serialization.py` — stubs for SER-01..SER-05, D-08/D-09, D-13, D-14, IDENT-05
- [ ] `tests/unit/test_status_target.py` — fake `mcp` + fake `revit_get` for D-06
- [ ] Retarget `tests/unit/test_local_bridge_transport.py` and `tests/unit/test_textutils.py::test_the_client_does_not_ask_pyrevit_to_parse_the_body` to `bridge.py` in the same commit as the move
- Framework install: none (pytest + anyio already in the dev group)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Two Revits on 48884/48885 with distinct PIDs; two stdio MCP entries each report own `host:port` + `document_title` | IDENT-05 / SC5, D-16, D-17, D-25, D-26 | Needs two live Revit processes | `01-RESEARCH.md` Live bench steps 1–6; staggered start is the acceptance run (D-25); also record a simultaneous launch |
| Overlapping `/execute_code/` POSTs + GET on one instance | D-23, D-27 | Needs live Revit; records pyRevit shared-handler behaviour | Live bench step 7; if a read hijacks a pending mutation, stop for user decision (D-27) |
| Invalid / unreachable `REVIT_PORT` behaviour end-to-end | IDENT-05 | Exercises real process start | Live bench step 8 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
