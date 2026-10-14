---
phase: 01-serialization-and-configurable-addressing
reviewed: 2026-10-14T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - CLAUDE.md
  - README.md
  - bridge.py
  - deploy/README.md
  - deploy/USER-GUIDE.md
  - deploy/build-payload.cmd
  - main.py
  - pyproject.toml
  - scripts/probe_handler_overlap.py
  - tests/test_two_instance_targets.py
  - tests/unit/test_bridge_serialization.py
  - tests/unit/test_format_response.py
  - tests/unit/test_local_bridge_transport.py
  - tests/unit/test_payload_ships_root_modules.py
  - tests/unit/test_probe_handler_overlap.py
  - tests/unit/test_serialization_scope_docs.py
  - tests/unit/test_status_target.py
  - tests/unit/test_textutils.py
  - tools/process_tools.py
  - tools/status_tools.py
findings:
  critical: 0
  warning: 3
  info: 5
  total: 8
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-10-14
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

The phase extracts the HTTP transport from `main.py` into `bridge.py`, adds one process-wide asyncio lock with a bounded wait, makes the Routes port configurable through `REVIT_PORT`, and adds an overlap probe. I traced the lock path (`_serialized`) through cancellation, timeout expiry, handler exceptions and the lock-free `/status/` path. I found no lock leak, no deadlock and no race around `asyncio.timeout` / `reschedule(None)`. The unit suite passes (416 passed, 3 skipped).

No BLOCKER-class defect was found. Three WARNING items remain, all reproduced by running the code:

- The "outcome UNKNOWN" honesty guarantee for POST has a hole.
- The overlap probe can report `serialized` for failed responses.
- `REVIT_HOST` is not validated, although `REVIT_PORT` is validated strictly.

The rest is documentation and test-hygiene debt.

No structural findings (fallow) were supplied and no external reviewer evidence was supplied.

## Warnings

### WR-01: A sent POST whose response cannot be parsed is reported without the "outcome UNKNOWN" wording

**File:** `bridge.py:207` and `bridge.py:352-353`
**Issue:** The design invariant (module docstring "Failure wording", D-13) is that after a POST has been sent, a failure must say the outcome is UNKNOWN, so the model does not retry a possibly-applied mutation. That wording is produced only for `httpx.TransportError` (`bridge.py:337-343`). `_send` calls `response.json()` after the request has completed, and the exception is handled by the generic `except Exception` in `_serialized`, which returns the bare `_error_text(e)`. Reproduced with a mock transport answering 200 with a non-JSON body:

```
await bridge.revit_post("/bad/", {})
-> 'Error: Expecting value: line 1 column 1 (char 0)'
```

The request reached Revit and may have been applied, but the model sees a plain error and is likely to retry. The same hole applies to `httpx` errors that are `RequestError` but not `TransportError`, for example `DecodingError` and `TooManyRedirects`. No test covers it: `test_outcome_unknown_*` only exercises `TransportError` subclasses.

**Fix:** For POST, treat anything that fails after the send began as UNKNOWN. For example, in `_serialized`'s generic handler:

```python
    except Exception as e:
        if method == "POST" and sent_started:   # set True just before client.post(...)
            return "Error: {} - the request was sent to Revit but its response could not be read; " \
                   "outcome UNKNOWN - verify the model state before retrying.".format(type(e).__name__)
        return _error_text(e)
```

Alternatively, wrap the `response.json()` call in `_send` and raise a dedicated exception that `_serialized` maps to the UNKNOWN text for POST. Add a test with a 200 non-JSON body.

### WR-02: Overlap probe reports verdict `serialized` when requests failed with a non-200 status

**File:** `scripts/probe_handler_overlap.py:87-118` (`classify_phase`), consumed at `:264-267`
**Issue:** `classify_phase` only flags timeouts, transport errors, marker cross-talk, run counts, and `status == 200` anomalies. A response with any other status (500, 503, 404) and no marker contamination produces no flag. Reproduced:

```
mutation C 500 / read levels 500 / read status 200, runs {"C": 0}  -> ('serialized', [])
mutation A 500 / mutation B 500, runs {"A": 1, "B": 1}             -> ('serialized', [])
```

The `missing-run` check requires `status == 200`, so a mutation that never ran because it got a 500 is also not flagged. The probe's purpose is to gate decisions (`D27_TRIGGER=no`, and the rule that a route may join `UNLOCKED_GET` only with a live measurement). A run in which Revit answered errors to everything would print `OVERLAP_VERDICT ... serialized` and `D27_TRIGGER=no`, which is false evidence. The unit tests in `test_probe_handler_overlap.py` do not cover non-200 statuses.

**Fix:** Add an explicit non-200 branch before the marker checks:

```python
        if o["status"] != 200:
            flag("error", "{} answered HTTP {}".format(name, o["status"]))
            continue
```

Add a test that two 500 answers do not yield `serialized`. Alternatively, make `serialized` require every observation to be a 200 whose body carries the expected content.

### WR-03: `REVIT_HOST` is not validated, so a bad value starts the server and fails every call

**File:** `bridge.py:108-111`
**Issue:** `REVIT_PORT` is parsed strictly and refuses to start on bad input, but `REVIT_HOST` is interpolated into `BASE_URL` unchecked. Reproduced:

- `REVIT_HOST=` (empty) gives `http://:48884/revit_mcp`. The server starts, then every call fails. The POST error text claims "could not reach Revit at :48884", which names no host.
- `REVIT_HOST=::1` (an unbracketed IPv6 literal, which the README's "use `127.0.0.1` where IPv6 is enabled" text invites people to try) gives `http://::1:48884/revit_mcp`. POSTs then fail with `Error: Invalid port: ':1:48884'`.

The module docstring promises that a bad target is refused at start. This is the same class of failure that `_resolve_port` exists to prevent, left half-done.

**Fix:** Validate the host in a `_resolve_host` helper (strip, refuse empty, bracket IPv6 literals containing `:` unless already bracketed). Raise `RevitConfigError` so `main.py` exits 2 with the reason. Add `test_host_refuses_empty` and `test_host_brackets_ipv6`.

## Info

### IN-01: The module docstring says the lock is never held while waiting for Revit, which is false

**File:** `bridge.py:57-58` (also the "Failure wording" section)
**Issue:** "The lock is never held while waiting for Revit (D-13)" contradicts the design. The lock is held for the entire `send()`, which is exactly the wait for Revit's response; that is the whole point of the serialization. What D-13 and SER-03 actually mean is that the lock is released on every exit and is never held across a retry or a post-failure wait. The docstring is pinned by tests, so the error will persist and mislead the next maintainer.
**Fix:** Reword to "The lock is released on every exit, including failure; a failed call is returned, never retried while holding it (D-13)."

### IN-02: Wording of the UNKNOWN message is inaccurate for failures that are not timeouts

**File:** `bridge.py:289-293`
**Issue:** `_transport_failure_message` says "no complete response arrived within {timeout}s" for every non-pre-send `TransportError`, including `RemoteProtocolError` or `ReadError` that can occur immediately. The elapsed claim is wrong, though the "outcome UNKNOWN" conclusion is right.
**Fix:** Drop the time claim for non-timeout subclasses, or branch on `isinstance(e, httpx.TimeoutException)`.

### IN-03: `main.py` catches every `ValueError` raised during `import bridge` as a REVIT_PORT refusal

**File:** `main.py:3-12`
**Issue:** `RevitConfigError` cannot be imported when `bridge` fails to import, so the broad `ValueError` catch is understandable. It also swallows unrelated import-time `ValueError`s, including `UnicodeDecodeError`, and labels them "refusing to start ... (no fallback to the default port)". The `exc` text is included, so the damage is limited to a misleading suffix.
**Fix:** Keep the catch, but drop the fixed "(no fallback to the default port)" tail, or check `"REVIT_PORT" in str(exc)` before using that message and re-raise otherwise.

### IN-04: Docs: undocumented third standalone test script, stale runtime row, opaque internal IDs in user-facing docs

**File:** `pyproject.toml:31-32`, `CLAUDE.md:49-50` and the "Two test tiers" paragraph, `README.md` (components table), `README.md` / `deploy/README.md` (serialization sections)
**Issue:**
- `tests/test_two_instance_targets.py` is a new third standalone script, but `pyproject.toml` and `CLAUDE.md` still say "the two standalone scripts" and list only `test_init_latency.py` and `test_model_info_format.py`.
- The README components table still says the Revit half runs on "IronPython 2.7"; `CLAUDE.md` says IronPython 3 since 2026-09-07. The adjacent row was edited in this diff and this one was left.
- User-facing README and `deploy/README.md` cite internal tracking IDs (`d27-c`, D-xx, SER-xx) that a reader cannot resolve. The pinned sentence "until d27-c lands" is meaningless outside the planning directory.
- The `tests/test_two_instance_targets.py` script lets a crashing server entry raise out of `asyncio.gather` without printing `TWO_INSTANCE_FAIL`, which breaks the sentinel convention the other scripts follow.

**Fix:** Add the script to the standalone list and the `pyproject.toml` comment. Correct the README runtime row. Reword the pinned sentence in plain language and update the pins. Wrap `_ask_entry` in `try/except` that records a failure.

### IN-05: Test hygiene: brittle doc pins and weak slices

**File:** `tests/unit/test_serialization_scope_docs.py:71-86, 155-161`, `tests/unit/test_textutils.py:285-290`, `tests/unit/test_bridge_serialization.py:28-36`
**Issue:**
- The docs test pins the Russian sentence verbatim, the version string `6.5.3` and the date `2026-10-07` inside the `bridge.py` docstring. A harmless wording or date edit now fails the suite, and the "slicing marker" test exists only because other tests slice `bridge.py` source by string search.
- `test_the_client_does_not_ask_pyrevit_to_parse_the_body` now slices from `else:  # POST` to the end of the much larger `bridge.py`, so its assertion can be satisfied by any later `"Content-Type": "text/plain` text. It also never asserts that `application/json` is absent.
- `_reset_bridge_state` discards the pooled `httpx.AsyncClient` without closing it, so it leaks unclosed clients and can emit resource warnings.

**Fix:** Parse the AST of `_send` for the header, or assert on `_send`'s source only. Keep doc pins to the three load-bearing sentences. Close clients in the fixture, for example `asyncio.run(bridge._http_client.aclose())` when it is not None.

---

_Reviewed: 2026-10-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
