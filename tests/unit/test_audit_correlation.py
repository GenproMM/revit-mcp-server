# -*- coding: utf-8 -*-
"""AUDIT-04 / D-05..D-07: one call_id per tool call, in the envelope, on the Audit line. Needs no Revit."""

import asyncio
import json
import types
import uuid

import httpx
import pytest
from mcp.server.fastmcp import Context, FastMCP

import audit
import bridge
from audit_support import (
    PID_A, PID_B, PORT_A, PORT_B, PREFIX, SEL_A, SEL_B, make_machine, read_entries,
    release_machine)
from gate_support import TEST_SECRET, configure_gate
from tools.utils import format_response

AUDIT_LINE = "Audit: call_id "

SUCCESS_BODY = {"status": "success", "outcome": {
    "transaction_status": "Committed", "requested": 1, "succeeded": [5], "failed": [],
    "revit_failures": []}}


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def machine(monkeypatch):
    fake = make_machine(monkeypatch)
    fake.reply(PORT_A, "/modify_element/", 200, SUCCESS_BODY)
    fake.reply(PORT_B, "/modify_element/", 200, SUCCESS_BODY)
    fake.reply(PORT_A, "/element_properties/1", 200, {"id": 1})
    # Phase 5: the bridge sends the envelope only when a secret is loaded.
    monkeypatch.setattr(bridge, "_secret_cache", TEST_SECRET)
    yield fake
    release_machine()


def build_server():
    mcp = FastMCP("audit-correlation")
    audit.install_audited_tools(mcp)

    @mcp.tool()
    async def multi_call_probe(target: str = None, ctx: Context = None) -> str:
        """Make three bridge calls: a read, a mutation and an image fetch."""
        await bridge.revit_get("/element_properties/1", ctx, target=target)
        mutation = await bridge.revit_post("/modify_element/", {"element_id": 1}, ctx, target=target)
        await bridge.revit_image("/get_view/L1", ctx, target=target)
        return format_response(mutation)

    @mcp.tool()
    async def two_posts_probe(target: str = None, ctx: Context = None) -> str:
        """Make two mutations in a row."""
        await bridge.revit_post("/modify_element/", {"element_id": 1}, ctx, target=target)
        return format_response(await bridge.revit_post(
            "/modify_element/", {"element_id": 2}, ctx, target=target))

    @mcp.tool()
    async def one_post_probe(target: str = None, ctx: Context = None) -> str:
        """Make one mutation."""
        return format_response(await bridge.revit_post(
            "/modify_element/", {"element_id": 1}, ctx, target=target))

    @mcp.tool()
    async def route_probe(route: str, post: bool = True, target: str = None,
                          ctx: Context = None) -> str:
        """Make one call to a route and render its reply."""
        if post:
            return format_response(await bridge.revit_post(route, {"x": 1}, ctx, target=target))
        return format_response(await bridge.revit_get(route, ctx, target=target))

    @mcp.tool()
    async def no_bridge_probe(ctx: Context = None) -> str:
        """Make no bridge call at all."""
        return "nothing sent"

    return mcp


async def call(mcp, name, arguments):
    content = await mcp.call_tool(name, arguments)
    return content[0].text


def audit_id_of(text):
    last = text.split("\n")[-1]
    assert last.startswith(AUDIT_LINE), text
    return last[len(AUDIT_LINE):]


def posts(machine):
    """The (path, parsed JSON body) of every POST the machine received, in arrival order."""
    return [(request.url.path, json.loads(request.content.decode("utf-8")))
            for request in machine.requests if request.method == "POST"]


# ------------------------------------------------------------------ shared call_id

@pytest.mark.anyio
async def test_one_tool_call_with_three_bridge_calls_writes_three_entries_with_one_call_id(machine):
    mcp = build_server()

    text = await call(mcp, "multi_call_probe", {"target": SEL_A})

    call_id = audit_id_of(text)
    entries = read_entries()
    assert [entry["route"] for entry in entries] == [
        "/element_properties/", "/modify_element/", "/get_view/"]
    assert [entry["method"] for entry in entries] == ["GET", "POST", "GET"]
    assert {entry["call_id"] for entry in entries} == {call_id}
    assert {entry["tool"] for entry in entries} == {"multi_call_probe"}
    assert uuid.UUID(call_id).version == 4


@pytest.mark.anyio
async def test_entries_of_one_call_appear_in_the_order_the_tool_issued_its_calls(machine):
    mcp = build_server()

    text = await call(mcp, "two_posts_probe", {"target": SEL_A})

    entries = read_entries()
    assert len(entries) == 2
    assert entries[0]["call_id"] == entries[1]["call_id"] == audit_id_of(text)
    assert [path for path, _body in posts(machine)] == [PREFIX + "/modify_element/"] * 2
    assert [body["element_id"] for _path, body in posts(machine)] == [1, 2]


@pytest.mark.anyio
async def test_concurrent_tool_calls_get_distinct_call_ids_with_no_cross_entries(machine):
    gate_a = machine.gate(PORT_A, "/modify_element/")
    gate_b = machine.gate(PORT_B, "/modify_element/")
    mcp = build_server()

    first = asyncio.ensure_future(call(mcp, "one_post_probe", {"target": SEL_A}))
    second = asyncio.ensure_future(call(mcp, "one_post_probe", {"target": SEL_B}))
    await asyncio.wait_for(gate_a.started.wait(), 10)
    await asyncio.wait_for(gate_b.started.wait(), 10)
    gate_a.release.set()
    gate_b.release.set()
    text_a, text_b = await asyncio.wait_for(asyncio.gather(first, second), 10)

    id_a, id_b = audit_id_of(text_a), audit_id_of(text_b)
    assert id_a != id_b
    entries = read_entries()
    assert len(entries) == 2
    by_pid = dict((entry["process"]["pid"], entry) for entry in entries)
    assert by_pid[PID_A]["call_id"] == id_a
    assert by_pid[PID_B]["call_id"] == id_b
    sent = dict((request.url.port, json.loads(request.content.decode("utf-8")))
                for request in machine.requests if request.method == "POST")
    assert sent[PORT_A]["_mcp"]["call_id"] == id_a
    assert sent[PORT_B]["_mcp"]["call_id"] == id_b


@pytest.mark.anyio
async def test_a_bridge_call_outside_any_tool_gets_a_fresh_call_id_each_time(machine):
    await bridge.revit_post("/modify_element/", {"element_id": 1}, target=SEL_A)
    await bridge.revit_post("/modify_element/", {"element_id": 1}, target=SEL_A)

    entries = read_entries()
    assert len(entries) == 2
    assert [entry["tool"] for entry in entries] == [None, None]
    assert entries[0]["call_id"] != entries[1]["call_id"]
    sent = [body["_mcp"]["call_id"] for _path, body in posts(machine)]
    assert sent == [entry["call_id"] for entry in entries]


@pytest.mark.anyio
async def test_a_post_with_no_data_writes_one_entry_with_empty_args(machine):
    await bridge.revit_post("/clear_colors/", None, target=SEL_A)

    entries = read_entries()
    assert len(entries) == 1
    assert entries[0]["args"] == {}
    assert entries[0]["route"] == "/clear_colors/"
    assert posts(machine)[0][1]["_mcp"]["call_id"] == entries[0]["call_id"]


@pytest.mark.anyio
async def test_a_tool_call_that_makes_no_bridge_call_writes_no_entry(machine):
    mcp = build_server()

    assert await call(mcp, "no_bridge_probe", {}) == "nothing sent"

    assert read_entries() == []
    assert machine.routes() == []


# ------------------------------------------------------------------------ envelope

@pytest.mark.anyio
async def test_every_post_body_carries_the_secret_and_the_call_id_of_its_entry(machine):
    mcp = build_server()

    text = await call(mcp, "two_posts_probe", {"target": SEL_A})

    call_id = audit_id_of(text)
    bodies = posts(machine)
    assert len(bodies) == 2
    for _path, body in bodies:
        assert body["_mcp"] == {"secret": TEST_SECRET, "call_id": call_id}
    assert [entry["call_id"] for entry in read_entries()] == [call_id, call_id]
    assert TEST_SECRET not in json.dumps(read_entries())


@pytest.mark.anyio
async def test_without_a_secret_the_body_has_no_envelope_and_the_entry_still_has_a_call_id(
        machine, monkeypatch):
    monkeypatch.setattr(bridge, "_secret_cache", None)
    mcp = build_server()

    text = await call(mcp, "one_post_probe", {"target": SEL_A})

    [(_path, body)] = posts(machine)
    assert "_mcp" not in body
    entries = read_entries()
    assert len(entries) == 1
    assert uuid.UUID(entries[0]["call_id"]).version == 4
    assert audit_id_of(text) == entries[0]["call_id"]


def test_with_envelope_adds_the_call_id_only_beside_a_secret():
    secret = "s" * 20

    assert bridge.with_envelope({"a": 1}, secret, call_id="x") == {
        "a": 1, "_mcp": {"secret": secret, "call_id": "x"}}
    assert bridge.with_envelope({"a": 1}, secret) == {"a": 1, "_mcp": {"secret": secret}}
    assert bridge.with_envelope({"a": 1}, None, call_id="x") == {"a": 1}
    assert bridge.with_envelope({"a": 1}, secret, call_id="") == {"a": 1, "_mcp": {"secret": secret}}
    assert bridge.with_envelope({"a": 1}, secret, call_id=None) == {
        "a": 1, "_mcp": {"secret": secret}}
    assert bridge.CALL_ID_KEY == "call_id"


def test_a_model_built_body_cannot_pre_seed_the_envelope_or_the_call_id():
    with pytest.raises(ValueError):
        bridge.with_envelope({"_mcp": {"call_id": "forged"}}, "s" * 20, call_id="x")


def test_the_real_gate_accepts_an_envelope_with_a_call_id_and_strips_it(monkeypatch):
    from revit_mcp import security

    configure_gate(monkeypatch)
    sent = json.dumps({"x": 1, "_mcp": {"secret": TEST_SECRET, "call_id": "abc"}}).encode("utf-8")
    request = types.SimpleNamespace(data=sent)

    assert security.gate_or_response(request) is None
    assert json.loads(request.data) == {"x": 1}


@pytest.mark.anyio
async def test_the_gate_accepts_the_exact_bytes_the_bridge_sent(machine, monkeypatch):
    from revit_mcp import security

    configure_gate(monkeypatch)
    mcp = build_server()
    await call(mcp, "one_post_probe", {"target": SEL_A})
    [post] = [r for r in machine.requests if r.method == "POST"]
    request = types.SimpleNamespace(data=post.content)

    assert security.gate_or_response(request) is None
    assert json.loads(request.data) == {"element_id": 1}


# --------------------------------------------------------------------- Audit line

@pytest.mark.anyio
async def test_the_audit_line_names_the_call_id_of_a_successful_mutation(machine):
    mcp = build_server()

    text = await call(mcp, "route_probe", {"route": "/modify_element/", "target": SEL_A})

    [entry] = read_entries()
    assert text.split("\n")[-1] == AUDIT_LINE + entry["call_id"]


@pytest.mark.anyio
async def test_a_successful_read_and_an_open_post_read_have_no_audit_line(machine):
    mcp = build_server()

    get_text = await call(mcp, "route_probe", {
        "route": "/element_properties/1", "post": False, "target": SEL_A})
    open_text = await call(mcp, "route_probe", {"route": "/document_summary/", "target": SEL_A})

    assert AUDIT_LINE not in get_text
    assert AUDIT_LINE not in open_text
    entries = read_entries()
    assert [(entry["route"], entry["outcome"], entry["mutation"]) for entry in entries] == [
        ("/element_properties/", "success", False), ("/document_summary/", "success", False)]


@pytest.mark.anyio
async def test_every_non_success_outcome_that_wrote_an_entry_has_an_audit_line(machine):
    machine.reply(PORT_A, "/modify_element/", 401, {"auth": "missing"})
    machine.reply(PORT_A, "/rename_view/", 423, {"integrity": "mismatch", "files": ["a.py"]})
    machine.reply(PORT_A, "/delete_elements/", 412, {"error_code": "document-token-stale"})
    machine.reply(PORT_A, "/set_parameter/", 500, {"error": "boom"})
    machine.faults[(PORT_A, PREFIX + "/place_family/")] = (
        lambda request: httpx.ReadTimeout("slow", request=request))
    mcp = build_server()
    expected = {
        "/modify_element/": "rejected_auth",
        "/rename_view/": "rejected_integrity",
        "/delete_elements/": "rejected_document",
        "/set_parameter/": "error",
        "/place_family/": "unknown",
    }

    for route in expected:
        text = await call(mcp, "route_probe", {"route": route, "target": SEL_A})
        assert text.split("\n")[-1].startswith(AUDIT_LINE), route

    entries = read_entries()
    assert dict((entry["route"], entry["outcome"]) for entry in entries) == expected


@pytest.mark.anyio
async def test_a_call_refused_before_sending_has_no_audit_line_and_no_entry(machine):
    machine.listeners[PORT_A] = []
    mcp = build_server()

    text = await call(mcp, "route_probe", {"route": "/modify_element/", "target": SEL_A})

    assert AUDIT_LINE not in text
    assert read_entries() == []
    assert machine.routes() == []
