# -*- coding: utf-8 -*-
"""SAFE-19 / D-24: the mcp 1.30 upgrade keeps the published tool surface and proves server elicitation.

Rows: version range, 59-tool surface with no outputSchema and the optional
user_request property, call_tool keeps its content-list shape, and a form-mode
elicitation round trip against a client shaped like the unchanged Hermes
handler (accept arrives with empty content; decline; cancel; no capability;
Cyrillic text intact). Needs no Revit.
"""

import importlib.metadata
import json

import pytest
import mcp.types as types
from mcp.server.fastmcp import Context, FastMCP

import audit
from elicitation_support import connected, hermes_callback
from inventory_support import manifest_names

EMPTY_FORM = {"type": "object", "properties": {}}
CYRILLIC = "Код операции: 7F3A91 — удалить 3 элемента?"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


def _server_with_ask_tool():
    """A FastMCP with the audit wrapper and a tool that elicits and reports what it saw."""
    mcp = FastMCP("sdk-test")
    audit.install_audited_tools(mcp)

    @mcp.tool()
    async def ask(message: str, ctx: Context = None) -> str:
        """Open a form-mode elicitation with an empty object schema and report the answer."""
        capable = ctx.session.check_client_capability(
            types.ClientCapabilities(elicitation=types.ElicitationCapability()))
        if not capable:
            return json.dumps({"capable": False})
        result = await ctx.session.elicit_form(message, EMPTY_FORM, ctx.request_id)
        return json.dumps({"capable": True, "action": result.action, "content": result.content})

    return mcp


async def _ask(session, message="Подтвердить?"):
    result = await session.call_tool("ask", {"message": message})
    assert not result.isError, result
    return json.loads(result.content[0].text)


def test_mcp_version_is_1_30_or_later_1_x():
    parts = importlib.metadata.version("mcp").split(".")
    version = (int(parts[0]), int(parts[1]))

    assert (1, 30) <= version < (2, 0)


@pytest.mark.anyio
async def test_all_production_tools_listed_without_output_schema_and_with_user_request():
    import main

    listed = await main.mcp.list_tools()

    assert sorted(tool.name for tool in listed) == manifest_names()
    assert len(listed) == 59
    for tool in listed:
        assert tool.outputSchema is None, tool.name
        prop = tool.inputSchema["properties"]["user_request"]
        assert prop["default"] is None, tool.name
        assert "user_request" not in tool.inputSchema.get("required", []), tool.name


@pytest.mark.anyio
async def test_call_tool_returns_content_blocks_with_text_not_a_tuple():
    mcp = FastMCP("sdk-test")
    audit.install_audited_tools(mcp)

    @mcp.tool()
    async def probe(ctx: Context = None) -> str:
        """Return a fixed string."""
        return "probe-ok"

    out = await mcp.call_tool("probe", {})

    assert not isinstance(out, tuple)
    assert not isinstance(out, dict)
    assert out[0].text == "probe-ok"


@pytest.mark.anyio
@pytest.mark.parametrize("step", ["accept", "decline", "cancel"])
async def test_elicit_form_returns_the_action_the_hermes_style_client_chose(step):
    callback = hermes_callback([step])

    async with connected(_server_with_ask_tool(), callback) as session:
        seen = await _ask(session)

    assert seen["capable"] is True
    assert seen["action"] == step
    assert seen["content"] == ({} if step == "accept" else None)
    assert callback.messages == ["Подтвердить?"]


@pytest.mark.anyio
async def test_client_without_elicitation_callback_reports_no_capability():
    async with connected(_server_with_ask_tool()) as session:
        seen = await _ask(session)

    assert seen == {"capable": False}


@pytest.mark.anyio
async def test_cyrillic_elicitation_message_arrives_byte_identical():
    callback = hermes_callback(["accept"])

    async with connected(_server_with_ask_tool(), callback) as session:
        await _ask(session, CYRILLIC)

    assert callback.messages == [CYRILLIC]
    assert callback.messages[0].encode("utf-8") == CYRILLIC.encode("utf-8")


@pytest.mark.anyio
async def test_exhausted_script_declines_and_messages_record_every_request():
    callback = hermes_callback(["accept"])

    async with connected(_server_with_ask_tool(), callback) as session:
        first = await _ask(session, "one")
        second = await _ask(session, "two")

    assert first["action"] == "accept"
    assert second["action"] == "decline"
    assert callback.messages == ["one", "two"]
