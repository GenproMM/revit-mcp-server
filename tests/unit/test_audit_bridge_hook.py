# -*- coding: utf-8 -*-
"""Audit entries through the real bridge and the fake machine: which calls write, and what they record. Needs no Revit."""

import asyncio

import httpx
import pytest

import audit
import bridge
from audit_support import (
    PID_A, PORT_A, PORT_B, SEL_A, TOKEN_B, make_machine, read_entries, release_machine)


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def machine(monkeypatch):
    fake = make_machine(monkeypatch)
    yield fake
    release_machine()


def block(transaction_status="Committed", requested=1, succeeded=(5,), failed=(), failures=()):
    return {"transaction_status": transaction_status, "requested": requested,
            "succeeded": list(succeeded), "failed": [dict(f) for f in failed],
            "revit_failures": list(failures)}


async def started(gate):
    await asyncio.wait_for(gate.started.wait(), 1.0)


async def post(route="/set_parameter/", data=None, **kwargs):
    return await bridge.revit_post(route, data if data is not None else {}, target=SEL_A, **kwargs)


# ----------------------------------------------------------- outcome rows

OUTCOME_ROWS = [
    ("409-rolled-back", 409, {"status": "rolled_back", "transaction_status": "RolledBack",
                              "outcome": block("RolledBack", 2, [], [], ["Constraints"])},
     "rolled_back", {"transaction_status": "RolledBack", "succeeded": [], "revit_failures": ["Constraints"]}),
    ("422-failed", 422, {"status": "failed", "error": "none succeeded",
                         "outcome": block("Committed", 1, [], [{"item": 3, "reason": "no"}])},
     "failed", {"failed": [{"item": 3, "reason": "no"}]}),
    ("200-partial", 200, {"status": "partial", "outcome": block(
        "Committed", 2, [5], [{"item": 6, "reason": "read-only"}])},
     "partial", {"succeeded": [5], "failed_count": 1}),
    ("401-auth", 401, {"error": "Mutation rejected: shared secret mismatch", "auth": "mismatch",
                       "hint": "run update"}, "rejected_auth", {"reason": "mismatch"}),
    ("423-integrity", 423, {"error": "differ", "integrity": "verified_mismatch",
                            "files": ["a.py"]}, "rejected_integrity",
     {"reason": "verified_mismatch"}),
    ("412-document-not-active", 412, {"error": "not active", "error_code": "document-not-active"},
     "rejected_document", {"reason": "document-not-active"}),
    ("500-after-commit", 500, {"error": "boom", "outcome": block("Committed", 1, [7])},
     "error", {"transaction_status": "Committed", "succeeded": [7], "succeeded_count": 1}),
]


@pytest.mark.anyio
@pytest.mark.parametrize("name,status,body,label,expected", OUTCOME_ROWS,
                         ids=["outcome-" + row[0] for row in OUTCOME_ROWS])
async def test_outcome_row_through_the_bridge(machine, name, status, body, label, expected):
    machine.reply(PORT_A, "/set_parameter/", status, body)

    await post()

    entries = read_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["outcome"] == label and entry["http_status"] == status
    assert entry["kind"] == "received" and entry["mutation"] is True
    assert entry["process"]["pid"] == PID_A and entry["process"]["port"] == PORT_A
    for key, value in expected.items():
        assert entry[key] == value, key
    assert "a.py" not in str(entry)


# -------------------------------------------------- sent but not answered

@pytest.mark.anyio
async def test_post_timeout_after_the_handshake_is_one_unknown_entry(machine):
    machine.faults[(PORT_A, "/genpro_revit_mcp/set_parameter/")] = (
        lambda req: httpx.ReadTimeout("", request=req))

    await post()

    entries = read_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["kind"] == "unknown" and entry["outcome"] == "unknown"
    assert entry["process"] is None
    assert str(PORT_A) in entry["requested_target"]["address"]
    assert entry["requested_target"]["pid"] == PID_A
    assert entry["mutation"] is True and "cancelled" not in entry


@pytest.mark.anyio
async def test_get_timeout_is_a_no_reply_entry(machine):
    machine.faults[(PORT_A, "/genpro_revit_mcp/model_info/")] = (
        lambda req: httpx.ReadTimeout("", request=req))

    await bridge.revit_get("/model_info/", target=SEL_A)

    entries = read_entries()
    assert len(entries) == 1
    assert entries[0]["kind"] == "no-reply" and entries[0]["outcome"] == "no_reply"
    assert entries[0]["mutation"] is False and entries[0]["process"] is None


@pytest.mark.anyio
async def test_a_reply_naming_another_process_is_recorded_as_unknown(machine):
    machine.reply(PORT_A, "/set_parameter/", 200, {
        "status": "success", "outcome": block(),
        "process_identity": {"pid": 999, "actual_port": PORT_A, "session_token": TOKEN_B,
                             "revit_version": "2024"}})

    await post()

    entries = read_entries()
    assert len(entries) == 1
    assert entries[0]["outcome"] == "unknown" and entries[0]["process"] is None
    assert entries[0]["succeeded"] is None


@pytest.mark.anyio
async def test_a_200_with_a_body_that_is_not_json_is_recorded_as_unknown(machine):
    machine.reply(PORT_A, "/set_parameter/", 200, "<html>not json</html>")

    await post()

    entries = read_entries()
    assert len(entries) == 1
    assert entries[0]["outcome"] == "unknown" and entries[0]["kind"] == "unknown"


# ------------------------------------------------------------ not sent

@pytest.mark.anyio
async def test_not_sent_listener_missing_writes_nothing(machine):
    machine.listeners[PORT_A] = []

    await post()

    assert machine.routes() == [] and read_entries() == []


@pytest.mark.anyio
async def test_not_sent_identity_mismatch_at_the_handshake_writes_nothing(machine):
    machine.identity[PORT_A] = (PID_A, TOKEN_B)

    await post()

    assert machine.routes() == [] and read_entries() == []


@pytest.mark.anyio
async def test_not_sent_queue_busy_writes_nothing_for_the_refused_call(machine):
    gate = machine.gate(PORT_A, "/p1/")
    holder = asyncio.ensure_future(post("/p1/"))
    await started(gate)

    refused = await asyncio.wait_for(post("/p2/", timeout=0.1), 2.0)
    assert "NOT sent to Revit" in refused
    gate.release.set()
    await asyncio.wait_for(holder, 1.0)

    entries = read_entries()
    assert [e["route"] for e in entries] == ["/p1/"]


@pytest.mark.anyio
async def test_not_sent_connect_error_before_send_writes_nothing(machine):
    machine.faults[(PORT_A, "/genpro_revit_mcp/set_parameter/")] = (
        lambda req: httpx.ConnectError("", request=req))

    result = await post()

    assert "was not sent to Revit" in result
    assert read_entries() == []


@pytest.mark.anyio
async def test_not_sent_envelope_refusal_writes_nothing(machine):
    result = await post("/set_parameter/", {"_mcp": {"secret": "x"}})

    assert "NOT sent to Revit" in result
    assert machine.routes() == [] and read_entries() == []


# ------------------------------------------------- discovery and handshake

@pytest.mark.anyio
async def test_default_discovery_probe_and_handshake_write_nothing_but_the_call_does(machine):
    machine.listeners[PORT_B] = []

    result = await bridge.revit_post("/set_parameter/", {})

    assert result == {"port": PORT_A, "path": "/genpro_revit_mcp/set_parameter/"}
    entries = read_entries()
    assert len(entries) == 1
    assert entries[0]["route"] == "/set_parameter/" and entries[0]["process"]["pid"] == PID_A
    assert any(s[2].endswith("/status/") for s in machine.seen)


@pytest.mark.anyio
async def test_discover_targets_alone_writes_nothing(machine):
    found = await bridge.discover_targets()

    assert found["usable"]
    assert read_entries() == []


# ---------------------------------------------------------------- images

@pytest.mark.anyio
async def test_image_carries_provenance_and_writes_one_entry(machine):
    image = await bridge.revit_image("/get_view/Level 1", target=SEL_A)

    assert not isinstance(image, str), image
    provenance = getattr(image, bridge.PROVENANCE_ATTR)
    assert provenance["kind"] == "received" and provenance["http_status"] == 200
    assert provenance["process"]["pid"] == PID_A
    entries = read_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["route"] == "/get_view/" and entry["route_arg"] == "Level 1"
    assert entry["method"] == "GET" and entry["mutation"] is False
    assert entry["outcome"] == "success" and entry["process"]["pid"] == PID_A


# ---------------------------------------------------------------- /status/

@pytest.mark.anyio
async def test_status_outside_any_tool_call_writes_nothing(machine):
    await bridge.revit_get("/status/", target=SEL_A)

    assert read_entries() == []


@pytest.mark.anyio
async def test_status_inside_the_status_tool_writes_one_entry(machine):
    token = audit._CALL.set(audit.CallState("call-1", "get_revit_status", {}, None))
    try:
        await bridge.revit_get("/status/", target=SEL_A)
    finally:
        audit._CALL.reset(token)

    entries = read_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["route"] == "/status/" and entry["method"] == "GET"
    assert entry["mutation"] is False and entry["tool"] == "get_revit_status"
    assert entry["call_id"] == "call-1" and entry["outcome"] == "success"
    assert entry["process"]["pid"] == PID_A


@pytest.mark.anyio
async def test_status_inside_a_process_tool_writes_nothing(machine):
    token = audit._CALL.set(audit.CallState("call-2", "get_revit_process_status", {}, None))
    try:
        await bridge.revit_get("/status/", target=SEL_A)
    finally:
        audit._CALL.reset(token)

    assert read_entries() == []


# ---------------------------------------------------------- cancellation

@pytest.mark.anyio
async def test_cancel_after_send_writes_one_unknown_cancelled_entry(machine):
    gate = machine.gate(PORT_A, "/slow/")
    task = asyncio.ensure_future(post("/slow/"))
    await started(gate)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    entries = read_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["outcome"] == "unknown" and entry["cancelled"] is True
    assert entry["kind"] == "unknown" and entry["route"] == "/slow/"
    assert entry["process"] is None and entry["requested_target"]["pid"] == PID_A
    assert bridge._get_lock(bridge.parse_target(SEL_A)).locked() is False


@pytest.mark.anyio
async def test_cancel_while_waiting_for_the_lock_writes_nothing(machine):
    gate = machine.gate(PORT_A, "/p1/")
    holder = asyncio.ensure_future(post("/p1/"))
    await started(gate)
    waiting = asyncio.ensure_future(post("/p2/"))
    await asyncio.sleep(0.05)

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    gate.release.set()
    await asyncio.wait_for(holder, 1.0)

    entries = read_entries()
    assert [e["route"] for e in entries] == ["/p1/"]
    assert "cancelled" not in entries[0]


# --------------------------------------------------- handshake title hint

@pytest.mark.anyio
async def test_execute_code_records_the_handshake_title_as_an_addressed_document(machine):
    machine.reply(PORT_A, "/execute_code/", 200, {
        "status": "success", "outcome": block(), "document_scope": "the code may touch any document"})

    await post("/execute_code/", {"code": "x = 1"})

    entries = read_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["document"] == {"token": None, "title": "Project A", "path": None}
    assert entry["document_source"] == "handshake_active_title"
    assert entry["document_role"] == "addressed"
    assert entry["document_scope"] == "the code may touch any document"
    assert entry["mutation"] is True


@pytest.mark.anyio
async def test_the_reply_document_beats_the_handshake_title(machine):
    machine.reply(PORT_A, "/set_parameter/", 200, {
        "status": "success", "outcome": block(),
        "document": {"document": "doc1.a.1", "title": "Real", "path": "C:/m/Real.rvt"}})

    await post()

    entry = read_entries()[0]
    assert entry["document"]["title"] == "Real"
    assert entry["document_source"] == "reply_document"


@pytest.mark.anyio
async def test_no_reported_title_means_no_document(machine):
    machine.titles[PORT_A] = None
    await post()

    entry = read_entries()[0]
    assert entry["document"] is None and entry["document_source"] == "none"
