# -*- coding: utf-8 -*-
"""ROADMAP criterion 7 / D-13: the configured secret never reaches an audit file, across success, 401, exception and pasted-secret paths. Needs no Revit."""

import json
import os

import httpx
import pytest
from mcp.server.fastmcp import Context, FastMCP

import audit
import bridge
from audit_support import PORT_A, PREFIX, SEL_A, make_machine, read_entries, release_machine
from gate_support import TEST_SECRET
from revit_mcp import trust
from tools.utils import format_response

AUDIT_LINE_PREFIX = "Audit: call_id "
DROPPED_PREFIX = "revit-mcp: audit log entry dropped ("

OK_BODY = {"status": "success", "outcome": {
    "transaction_status": "Committed", "requested": 1, "succeeded": [5], "failed": [],
    "revit_failures": []}}

ECHO_BODY = {
    "status": "partial",
    "document": {"document": "doc1.echo", "title": "Echo " + TEST_SECRET,
                 "path": "C:/models/" + TEST_SECRET + ".rvt"},
    "outcome": {"transaction_status": "Committed", "requested": 2, "succeeded": [5],
                "failed": [{"item": 6, "reason": "bad value " + TEST_SECRET}],
                "revit_failures": ["Revit says " + TEST_SECRET]},
}


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def machine(monkeypatch):
    fake = make_machine(monkeypatch)
    monkeypatch.setattr(bridge, "_secret_cache", TEST_SECRET)
    fake.reply(PORT_A, "/modify_element/", 200, OK_BODY)
    fake.reply(PORT_A, "/execute_code/", 200, OK_BODY)
    fake.reply(PORT_A, "/refused_route/", 401, trust.auth_failure("mismatch")[0])
    fake.reply(PORT_A, "/echo_route/", 200, ECHO_BODY)
    fake.faults[(PORT_A, PREFIX + "/timeout_route/")] = lambda request: httpx.ReadTimeout(
        "read timed out", request=request)
    yield fake
    release_machine()


def build_server():
    """The audited FastMCP: the real tool surface plus generic probes that call the real bridge."""
    import tools

    mcp = FastMCP("audit-secret")
    audit.install_audited_tools(mcp)
    tools.register_tools(mcp, bridge.revit_get, bridge.revit_post, bridge.revit_image)

    @mcp.tool()
    async def secret_post_probe(route: str, note: str = None, target: str = None,
                                ctx: Context = None) -> str:
        """POST to any route through the production bridge."""
        data = {"route": route}
        return format_response(await bridge.revit_post(route, data, ctx, target=target))

    @mcp.tool()
    async def secret_raise_probe(target: str = None, ctx: Context = None) -> str:
        """POST, then fail the way a buggy tool would."""
        await bridge.revit_post("/modify_element/", {"element_id": 5}, ctx, target=target)
        raise RuntimeError("tool failed after its bridge call")

    @mcp.tool()
    async def secret_get_probe(tail: str, target: str = None, ctx: Context = None) -> str:
        """GET /element_properties/<tail> through the production bridge."""
        return format_response(await bridge.revit_get(
            "/element_properties/" + tail, ctx, target=target))

    return mcp


async def call(mcp, name, arguments):
    content = await mcp.call_tool(name, arguments)
    return content[0].text


async def call_registered(mcp, name, arguments):
    """Run a real registered tool through its audited wrapper without an MCP request.

    mcp.call_tool hands the tool a Context that refuses use outside a request, and the
    real execute_revit_code reports progress through ctx. The wrapper stored on the
    tool is the same one a client reaches, so the call state and the bridge hook are
    the production ones; ctx is simply None, as in every other unit test of a tool.
    """
    tool = mcp._tool_manager.get_tool(name)
    return await tool.fn(ctx=None, **arguments)


def audit_bytes():
    """The concatenated bytes of every audit file, after the writer drained."""
    assert audit.flush(), "audit writer did not drain"
    directory = os.environ[audit.AUDIT_DIR_ENV]
    data = b""
    if not os.path.isdir(directory):
        return data
    for name in sorted(os.listdir(directory)):
        if name.startswith("audit-") and name.endswith(".jsonl"):
            with open(os.path.join(directory, name), "rb") as handle:
                data += handle.read()
    return data


def assert_no_secret(data):
    assert TEST_SECRET.encode("utf-8") not in data
    assert json.dumps(TEST_SECRET)[1:-1].encode("utf-8") not in data
    for start in range(len(TEST_SECRET) - 15):
        assert TEST_SECRET[start:start + 16].encode("utf-8") not in data, start


# ----------------------------------------------------------------- the scenarios

async def scenario_successful_post(mcp, machine):
    await call(mcp, "secret_post_probe", {"route": "/modify_element/", "target": SEL_A})
    # not vacuous: the bridge really did send the secret to Revit
    assert any(TEST_SECRET.encode("utf-8") in request.content for request in machine.requests)


async def scenario_401_refusal(mcp, machine):
    await call(mcp, "secret_post_probe", {"route": "/refused_route/", "target": SEL_A})


async def scenario_transport_exception(mcp, machine):
    await call(mcp, "secret_post_probe", {"route": "/timeout_route/", "target": SEL_A})


async def scenario_tool_raises_after_its_bridge_call(mcp, machine):
    with pytest.raises(Exception):
        await call(mcp, "secret_raise_probe", {"target": SEL_A})


async def scenario_secret_pasted_into_args_and_user_request(mcp, machine):
    await call(mcp, "secret_post_probe", {
        "route": "/modify_element/", "note": "my secret is " + TEST_SECRET, "target": SEL_A,
        "user_request": "please use " + TEST_SECRET + " as the key"})


async def scenario_secret_pasted_into_execute_code(mcp, machine):
    await call_registered(mcp, "execute_revit_code", {
        "code": "key = '" + TEST_SECRET + "'\nprint(key)", "description": "uses " + TEST_SECRET,
        "target": SEL_A})


async def scenario_reply_echoes_the_secret(mcp, machine):
    await call(mcp, "secret_post_probe", {"route": "/echo_route/", "target": SEL_A})


async def scenario_secret_straddles_the_argument_cut(mcp, machine):
    note = "a" * 480 + TEST_SECRET + "b" * 120
    await call(mcp, "secret_post_probe", {"route": "/modify_element/", "note": note,
                                          "target": SEL_A})


async def scenario_get_route_tail_is_the_secret(mcp, machine):
    await call(mcp, "secret_get_probe", {"tail": TEST_SECRET, "target": SEL_A})


SCENARIOS = [
    ("successful-post", scenario_successful_post, "success"),
    ("401-refusal", scenario_401_refusal, "rejected_auth"),
    ("transport-exception", scenario_transport_exception, "unknown"),
    ("tool-raises-after-bridge-call", scenario_tool_raises_after_its_bridge_call, "success"),
    ("secret-in-args-and-user-request", scenario_secret_pasted_into_args_and_user_request,
     "success"),
    ("secret-in-execute-code", scenario_secret_pasted_into_execute_code, "success"),
    ("reply-echoes-secret", scenario_reply_echoes_the_secret, "partial"),
    ("secret-straddles-the-cut", scenario_secret_straddles_the_argument_cut, "success"),
    ("secret-in-route-tail", scenario_get_route_tail_is_the_secret, "success"),
]


@pytest.mark.anyio
@pytest.mark.parametrize("name,scenario,label", SCENARIOS, ids=[row[0] for row in SCENARIOS])
async def test_secret_scenario_leaves_one_entry_and_no_trace_of_the_secret(
        machine, name, scenario, label):
    mcp = build_server()

    await scenario(mcp, machine)

    entries = read_entries()
    assert len(entries) == 1, name
    assert entries[0]["outcome"] == label, name
    assert_no_secret(audit_bytes())


@pytest.mark.anyio
async def test_secret_every_scenario_in_one_log_leaves_nine_entries_and_no_trace(machine):
    mcp = build_server()

    for _name, scenario, _label in SCENARIOS:
        await scenario(mcp, machine)

    entries = read_entries()
    assert len(entries) == len(SCENARIOS) == 9
    assert [entry["outcome"] for entry in entries] == [row[2] for row in SCENARIOS]
    assert_no_secret(audit_bytes())
    assert b'"_mcp"' not in audit_bytes()


@pytest.mark.anyio
async def test_secret_pasted_values_are_replaced_in_place_not_dropped(machine):
    mcp = build_server()

    await scenario_secret_pasted_into_args_and_user_request(mcp, machine)
    await scenario_secret_pasted_into_execute_code(mcp, machine)

    posted, executed = read_entries()
    assert posted["args"]["note"] == "my secret is " + audit.REDACTED
    assert posted["user_request"] == "please use " + audit.REDACTED + " as the key"
    assert posted["user_request_source"] == "assistant"
    assert executed["args"]["code"] == "key = '" + audit.REDACTED + "'\nprint(key)"
    assert executed["code_length"] == len("key = '" + TEST_SECRET + "'\nprint(key)")
    assert executed["tool"] == "execute_revit_code" and executed["route"] == "/execute_code/"


@pytest.mark.anyio
async def test_secret_echoed_by_the_reply_is_redacted_in_every_copied_field(machine):
    mcp = build_server()

    await scenario_reply_echoes_the_secret(mcp, machine)

    (entry,) = read_entries()
    assert entry["failed"][0]["reason"] == "bad value " + audit.REDACTED
    assert entry["revit_failures"] == ["Revit says " + audit.REDACTED]
    assert entry["document"]["title"] == "Echo " + audit.REDACTED
    assert audit.REDACTED in entry["document"]["path"]


@pytest.mark.anyio
async def test_secret_in_the_route_tail_is_written_as_redacted(machine):
    mcp = build_server()

    await scenario_get_route_tail_is_the_secret(mcp, machine)

    (entry,) = read_entries()
    assert entry["route"] == "/element_properties/" and entry["route_arg"] == audit.REDACTED


@pytest.mark.anyio
async def test_secret_with_none_loaded_writes_every_value_as_given(machine, monkeypatch):
    monkeypatch.setattr(bridge, "_secret_cache", None)
    mcp = build_server()

    await call(mcp, "secret_post_probe", {"route": "/modify_element/", "note": "plain text",
                                          "target": SEL_A})

    (entry,) = read_entries()
    assert entry["args"]["note"] == "plain text"
    assert audit.REDACTED.encode("utf-8") not in audit_bytes()


@pytest.mark.anyio
async def test_secret_the_writers_own_identity_fields_are_kept(machine):
    mcp = build_server()

    await scenario_successful_post(mcp, machine)

    (entry,) = read_entries()
    assert entry["process"]["session_token"] == "11111111-1111-4111-8111-111111111111"
    assert entry["windows_user"]


# --------------------------------------------------------------- the failure path

async def post_text(mcp):
    return await call(mcp, "secret_post_probe", {"route": "/modify_element/", "target": SEL_A})


def without_audit_line(text):
    lines = text.split("\n")
    assert lines[-1].startswith(AUDIT_LINE_PREFIX), text
    return "\n".join(lines[:-1])


@pytest.mark.anyio
async def test_secret_failure_path_writes_one_stderr_line_and_changes_no_reply(
        machine, monkeypatch, tmp_path, capsys):
    mcp = build_server()
    working = without_audit_line(await post_text(mcp))
    capsys.readouterr()
    blocker = tmp_path / "a-regular-file"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv(audit.AUDIT_DIR_ENV, str(blocker))
    audit._reset()

    first = await post_text(mcp)
    second = await post_text(mcp)

    captured = capsys.readouterr()
    assert first == working and second == working
    lines = [line for line in captured.err.splitlines() if line.startswith(DROPPED_PREFIX)]
    assert len(lines) == 1, captured.err
    assert lines[0].endswith(")") and lines[0][len(DROPPED_PREFIX):-1].isidentifier()
    assert TEST_SECRET not in captured.err and TEST_SECRET not in captured.out
    assert "modify_element" not in lines[0]
    assert blocker.read_text(encoding="utf-8") == "not a directory"


@pytest.mark.anyio
async def test_secret_stderr_has_nothing_when_the_log_works(machine, capsys):
    mcp = build_server()

    await post_text(mcp)
    read_entries()

    assert DROPPED_PREFIX not in capsys.readouterr().err
