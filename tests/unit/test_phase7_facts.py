# -*- coding: utf-8 -*-
"""Real MCP tools and bridge with scripted offline preflight responses."""

import copy
import dataclasses
import hashlib
import json

import httpx
import pytest
from mcp.server.fastmcp import Context

import approval
import bridge
import policy
from audit_support import PREFIX, SEL_A, make_machine, release_machine
from elicitation_support import connected, hermes_callback
from gate_support import TEST_SECRET
from revit_mcp import permits
from test_phase7_tracer import build_server, call, posts_to, verdict

TOKEN = "doc1.aaaaaaaaaaaa.2"
G = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def reply(facts=None):
    return {"status": "ok", "document": {"document": TOKEN, "title": "Модель", "path": "C:/A.rvt"},
            "facts": facts if facts is not None else {"available": True, "requested": 1, "found": 1,
                "missing": [], "categories": {"Стены": 1}, "kinds": {}, "cascade": "unknown"}}


def parameter(resolved="instance", has_value=False):
    return {"available": True, "element": {"exists": True, "is_type": False, "group_member": False,
        "type": "Стена 200", "type_instance_count": 340}, "parameters": [
        {"name": "Марка", "resolved": resolved, "has_value": has_value, "read_only": False,
         "display_value": "", "raw_value": None}]}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def machine(monkeypatch):
    fake = make_machine(monkeypatch)
    monkeypatch.setattr(permits, "_CONSUMED", {})
    monkeypatch.setattr(bridge, "_secret_cache", TEST_SECRET)
    monkeypatch.setattr(bridge, "_authorize", approval.authorize)
    fake.preflights = [reply()]
    original = fake.respond

    async def respond(request):
        if request.url.path == PREFIX + "/mutation_preflight/":
            fake.requests.append(request)
            fake.seen.append((request.url.port, request.method, request.url.path))
            item = fake.preflights.pop(0) if len(fake.preflights) > 1 else fake.preflights[0]
            if isinstance(item, Exception):
                raise item
            status, body = item if isinstance(item, tuple) else (200, item)
            return httpx.Response(status, json=copy.deepcopy(body))
        return await original(request)

    fake.respond = respond
    yield fake
    release_machine()


@pytest.mark.anyio
async def test_empty_instance_parameter_sends_without_window(machine):
    machine.preflights = [reply(parameter())]
    callback = hermes_callback([])
    async with connected(build_server(), callback) as session:
        text = await call(session, "set_parameter", element_id=1, parameter_name="Марка", value="А")
    assert "NOT sent" not in text
    assert not callback.messages
    assert len(posts_to(machine, "/set_parameter/")) == 1


@pytest.mark.anyio
async def test_type_parameter_shows_count_and_rechecks_before_send(machine):
    machine.preflights = [reply(parameter("type"))]
    callback = hermes_callback(["accept"])
    async with connected(build_server(), callback) as session:
        await call(session, "set_parameter", element_id=1, parameter_name="Марка", value="А")
    assert "340" in callback.messages[0]
    assert len(posts_to(machine, "/mutation_preflight/")) == 2
    assert len(posts_to(machine, "/set_parameter/")) == 1


@pytest.mark.anyio
async def test_changed_facts_void_accept(machine):
    machine.preflights = [reply(parameter("type")), reply(parameter("type", True))]
    async with connected(build_server(), hermes_callback(["accept"])) as session:
        text = await call(session, "set_parameter", element_id=1, parameter_name="Марка", value="А")
    assert "facts_changed" in text
    assert not posts_to(machine, "/set_parameter/")


@pytest.mark.anyio
async def test_document_is_pinned_and_permit_covers_final_body(machine):
    async with connected(build_server(), hermes_callback(["accept"])) as session:
        await call(session, "delete_elements", element_ids=[1])
    sent = posts_to(machine, "/delete_elements/")[0]
    assert json.loads(sent.content)["document"] == TOKEN
    assert verdict(sent, "/delete_elements/") == permits.OK
    recheck = posts_to(machine, "/mutation_preflight/")[1]
    assert json.loads(recheck.content)["document"] == TOKEN


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 404, 412, 503])
async def test_document_refusal_prevents_window_and_mutation(machine, status):
    machine.preflights = [(status, {"error": "document not active", "error_code": "document-not-active"})]
    callback = hermes_callback([])
    async with connected(build_server(), callback) as session:
        text = await call(session, "delete_elements", element_ids=[1])
    assert "preflight_refused" in text
    assert "document not active" in text
    assert not callback.messages and not posts_to(machine, "/delete_elements/")


@pytest.mark.anyio
@pytest.mark.parametrize("tool,args,route", [
    ("set_parameter", {"element_id": 1, "parameter_name": "Марка", "value": "x"}, "/set_parameter/"),
    ("delete_elements", {"element_ids": [1]}, "/delete_elements/"),
])
async def test_unavailable_preflight_still_opens_window_but_failed_recheck_refuses(machine, tool, args, route):
    machine.preflights = [httpx.ConnectError("unavailable")]
    callback = hermes_callback(["accept"])
    async with connected(build_server(), callback) as session:
        text = await call(session, tool, **args)
    assert len(callback.messages) == 1 and "неизвестно" in callback.messages[0]
    assert "facts_changed" in text
    assert not posts_to(machine, route)


@pytest.mark.anyio
@pytest.mark.parametrize("source", ["match", "missing_guid", "missing_file", "changed_after_accept"])
async def test_shared_parameter_source_checked_before_window(machine, tmp_path, monkeypatch, source):
    file = tmp_path / "ФОП.txt"
    if source != "missing_file":
        file.write_text("*PARAM\tGUID\tNAME\nPARAM\t{}\tADSK_Марка\tTEXT\n".format(
            G if source in ("match", "changed_after_accept") else "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"), encoding="utf-8")
    base = policy.load_base()
    current = dataclasses.replace(base, settings=dict(base.settings, shared_parameters_file=str(file)))

    async def local_policy(**kwargs):
        return current

    monkeypatch.setattr(policy, "current", local_policy)
    machine.preflights = [reply({"available": True, "family": {"name": "F", "instance_count": 2},
        "shared": {"definitions": [{"name": "ADSK_Марка", "resolved": True, "ambiguous": False, "guid": G}]}})]
    inner = hermes_callback(["accept"] if source in ("match", "changed_after_accept") else [])

    async def callback(context, params):
        if source == "changed_after_accept":
            before = file.stat()
            file.write_bytes(file.read_bytes().replace(G.encode(), b"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
            # Force re-reading even if a source preserves both cache metadata fields.
            import os
            os.utime(file, ns=(before.st_atime_ns, before.st_mtime_ns))
        return await inner(context, params)

    server = build_server()

    @server.tool()
    async def shared_edit(ctx: Context = None) -> str:
        return str(await bridge.revit_post("/edit_family/", {
            "family_name": "F", "add_shared_parameters": ["ADSK_Марка"]}, ctx, target=SEL_A))

    async with connected(server, callback) as session:
        result = await session.call_tool("shared_edit", {})
        text = "".join(part.text for part in result.content)
    if source == "match":
        assert len(inner.messages) == 1
        assert "совпадает с ФОП" in inner.messages[0]
        assert len(posts_to(machine, "/edit_family/")) == 1
    else:
        assert "shared_parameter_source" in text
        assert len(inner.messages) == (1 if source == "changed_after_accept" else 0)
        assert not posts_to(machine, "/edit_family/")


@pytest.mark.anyio
async def test_execute_has_no_preflight_and_retains_tool_registration(machine):
    code = "x = 1"
    callback = hermes_callback(["accept"])
    async with connected(build_server(), callback) as session:
        listed = await session.list_tools()
        assert "execute_revit_code" in {t.name for t in listed.tools}
        await call(session, "execute_revit_code", code=code)
    assert hashlib.sha256(code.encode()).hexdigest()[:16] in callback.messages[0]
    assert not posts_to(machine, "/mutation_preflight/")
    assert len(posts_to(machine, "/execute_code/")) == 1


@pytest.mark.anyio
async def test_load_warns_about_unchecked_fop_contents(machine):
    callback = hermes_callback(["accept"])
    async with connected(build_server(), callback) as session:
        await call(session, "load_family", file_path="C:/F.rfa")
    assert "не проверяются по ФОП" in callback.messages[0]
    assert len(posts_to(machine, "/load_family/")) == 1


@pytest.mark.anyio
async def test_changed_document_token_voids_accept(machine):
    changed = reply()
    changed["document"]["document"] = "doc1.aaaaaaaaaaaa.3"
    machine.preflights = [reply(), changed]
    async with connected(build_server(), hermes_callback(["accept"])) as session:
        text = await call(session, "delete_elements", element_ids=[1])
    assert "facts_changed" in text
    assert not posts_to(machine, "/delete_elements/")
