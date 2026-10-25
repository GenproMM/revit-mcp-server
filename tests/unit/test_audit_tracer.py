# -*- coding: utf-8 -*-
"""Phase 6 tracer: one audited tool call through the production bridge (06-01).

A real FastMCP with audit.install_audited_tools applied, a probe tool that calls
the real bridge, a fake machine in place of netstat and HTTP, and the audit
directory read back from disk. Needs no Revit.
"""

import os
import subprocess
import sys
import uuid

import pytest
from mcp.server.fastmcp import Context, FastMCP

import audit
import bridge
from audit_support import (
    PID_A, PORT_A, SEL_A, TOKEN_A, make_machine, read_entries, release_machine)
from inventory_support import manifest_names
from tools.utils import PROVENANCE_ATTR, format_response

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    fake.reply(PORT_A, "/element_properties/5", 200, {"id": 5})
    yield fake
    release_machine()


def build_server():
    mcp = FastMCP("audit-test")
    audit.install_audited_tools(mcp)

    @mcp.tool()
    async def audit_tracer_probe(element_id: int, target: str = None, ctx: Context = None) -> str:
        """Modify one element through the production bridge."""
        return format_response(await bridge.revit_post(
            "/modify_element/", {"element_id": element_id}, ctx, target=target))

    @mcp.tool()
    async def audit_read_probe(element_id: int, target: str = None, ctx: Context = None) -> str:
        """Read one element through the production bridge."""
        return format_response(await bridge.revit_get(
            "/element_properties/{}".format(element_id), ctx, target=target))

    @mcp.tool()
    async def audit_ctx_probe(ctx: Context = None) -> str:
        """Report whether the wrapped function still receives ctx."""
        return "ctx" if ctx is not None else "noctx"

    return mcp


async def call(mcp, name, arguments):
    content = await mcp.call_tool(name, arguments)
    return content[0].text


def audit_id_of(text):
    last = text.split("\n")[-1]
    assert last.startswith(AUDIT_LINE), text
    return last[len(AUDIT_LINE):]


@pytest.mark.anyio
async def test_mutation_writes_one_entry_and_the_reply_names_its_call_id(machine):
    mcp = build_server()

    text = await call(mcp, "audit_tracer_probe", {"element_id": 5, "target": SEL_A})

    call_id = audit_id_of(text)
    entries = read_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["schema"] == 1
    assert entry["call_id"] == call_id
    assert len(call_id) == 36 and uuid.UUID(call_id).version == 4
    assert entry["tool"] == "audit_tracer_probe"
    assert entry["route"] == "/modify_element/"
    assert entry["route_arg"] is None
    assert entry["method"] == "POST"
    assert entry["mutation"] is True
    assert entry["kind"] == "received"
    assert entry["http_status"] == 200
    assert entry["outcome"] == "success"
    assert entry["process"] == {"pid": PID_A, "port": PORT_A, "session_token": TOKEN_A,
                                "revit_version": "2024"}
    assert entry["server_pid"] == os.getpid()
    assert isinstance(entry["duration_ms"], int) and entry["duration_ms"] >= 0
    assert entry["ts"].endswith("Z")
    files = [n for n in os.listdir(os.environ[audit.AUDIT_DIR_ENV]) if n.endswith(".jsonl")]
    assert len(files) == 1 and files[0].startswith("audit-")


@pytest.mark.anyio
async def test_identical_calls_make_two_entries_with_two_call_ids(machine):
    mcp = build_server()

    first = await call(mcp, "audit_tracer_probe", {"element_id": 5, "target": SEL_A})
    second = await call(mcp, "audit_tracer_probe", {"element_id": 5, "target": SEL_A})

    entries = read_entries()
    assert len(entries) == 2
    assert entries[0]["call_id"] != entries[1]["call_id"]
    assert {entries[0]["call_id"], entries[1]["call_id"]} == {audit_id_of(first), audit_id_of(second)}


@pytest.mark.anyio
async def test_successful_read_is_logged_but_the_reply_has_no_audit_line(machine):
    mcp = build_server()

    text = await call(mcp, "audit_read_probe", {"element_id": 5, "target": SEL_A})

    assert AUDIT_LINE not in text
    entries = read_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["method"] == "GET"
    assert entry["route"] == "/element_properties/"
    assert entry["route_arg"] == "5"
    assert entry["mutation"] is False
    assert entry["outcome"] == "success"
    assert entry["tool"] == "audit_read_probe"


@pytest.mark.anyio
async def test_a_call_refused_before_sending_writes_nothing(machine):
    machine.listeners[PORT_A] = []
    mcp = build_server()

    text = await call(mcp, "audit_tracer_probe", {"element_id": 5, "target": SEL_A})

    assert AUDIT_LINE not in text
    assert machine.routes() == []
    assert read_entries() == []


@pytest.mark.anyio
async def test_a_bridge_call_outside_any_tool_gets_its_own_call_id(machine):
    result = await bridge.revit_post("/modify_element/", {"element_id": 5}, target=SEL_A)

    entries = read_entries()
    assert len(entries) == 1
    assert entries[0]["tool"] is None
    assert uuid.UUID(entries[0]["call_id"]).version == 4
    assert getattr(result, PROVENANCE_ATTR)["audit_call_id"] == entries[0]["call_id"]


@pytest.mark.anyio
async def test_wrapper_injects_user_request_and_keeps_ctx(machine):
    mcp = build_server()

    listed = dict((tool.name, tool) for tool in await mcp.list_tools())

    for name in ("audit_tracer_probe", "audit_read_probe", "audit_ctx_probe"):
        properties = listed[name].inputSchema["properties"]
        assert "user_request" in properties, name
        assert properties["user_request"].get("default") is None
        assert "ctx" not in properties, name
        assert "user_request" not in listed[name].inputSchema.get("required", []), name
    assert await call(mcp, "audit_ctx_probe", {}) == "ctx"
    assert await call(mcp, "audit_ctx_probe", {"user_request": "{\"a\": 1}"}) == "ctx"


@pytest.mark.anyio
async def test_every_manifest_tool_registers_through_the_wrapper(machine):
    import tools

    mcp = FastMCP("audit-all")
    audit.install_audited_tools(mcp)

    tools.register_tools(mcp, bridge.revit_get, bridge.revit_post, bridge.revit_image)

    assert tools.FAILED == {}
    listed = list(await mcp.list_tools())
    assert sorted(tool.name for tool in listed) == manifest_names()
    for tool in listed:
        assert "user_request" in tool.inputSchema["properties"], tool.name
        assert "ctx" not in tool.inputSchema["properties"], tool.name


def test_importing_audit_and_bridge_creates_nothing(tmp_path):
    missing = str(tmp_path / "never-created")
    script = (
        "import os, sys, threading\n"
        "sys.path.insert(0, {repo!r})\n"
        "before = threading.active_count()\n"
        "import audit, bridge\n"
        "assert threading.active_count() == before\n"
        "assert not os.path.exists({missing!r})\n"
        "assert 'mcp.server.fastmcp' not in sys.modules\n"
        "sys.stdout.write('IMPORT_QUIET_OK')\n"
    ).format(repo=REPO, missing=missing)
    env = dict(os.environ)
    env["REVIT_MCP_AUDIT_DIR"] = missing

    done = subprocess.run([sys.executable, "-I", "-c", script], env=env, capture_output=True,
                          text=True, timeout=60)

    assert done.returncode == 0, done.stderr
    assert done.stdout == "IMPORT_QUIET_OK"
    assert not os.path.exists(missing)
