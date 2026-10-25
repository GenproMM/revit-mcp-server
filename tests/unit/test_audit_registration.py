# -*- coding: utf-8 -*-
"""D-12: the injected user_request parameter on every published tool schema, and nothing else changed. Needs no Revit."""

import pytest
from mcp.server.fastmcp import Context, FastMCP

import audit
import bridge
from inventory_support import manifest_names


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


def _register_all(mcp):
    import tools

    tools.register_tools(mcp, bridge.revit_get, bridge.revit_post, bridge.revit_image)
    return tools


async def _schemas(mcp):
    return dict((tool.name, tool.inputSchema) for tool in await mcp.list_tools())


@pytest.mark.anyio
async def test_wrapper_adds_exactly_one_optional_property_to_every_published_tool():
    plain = FastMCP("plain")
    wrapped = FastMCP("wrapped")
    audit.install_audited_tools(wrapped)

    _register_all(plain)
    tools = _register_all(wrapped)

    plain_schemas = await _schemas(plain)
    wrapped_schemas = await _schemas(wrapped)
    assert tools.FAILED == {}
    assert sorted(plain_schemas) == sorted(wrapped_schemas) == manifest_names()
    for name, schema in wrapped_schemas.items():
        before = plain_schemas[name]
        added = set(schema["properties"]) - set(before["properties"])
        assert added == {"user_request"}, name
        assert set(before["properties"]) <= set(schema["properties"]), name
        for key, value in before["properties"].items():
            assert schema["properties"][key] == value, (name, key)
        assert schema.get("required", []) == before.get("required", []), name
        assert "user_request" not in schema.get("required", []), name


@pytest.mark.anyio
async def test_user_request_is_optional_nullable_text_with_the_final_description():
    mcp = FastMCP("wrapped")
    audit.install_audited_tools(mcp)
    _register_all(mcp)

    schemas = await _schemas(mcp)

    for name, schema in schemas.items():
        prop = schema["properties"]["user_request"]
        assert prop["default"] is None, name
        assert sorted(item["type"] for item in prop["anyOf"]) == ["null", "string"], name
        assert prop["description"] == audit.USER_REQUEST_DESCRIPTION, name
    description = audit.USER_REQUEST_DESCRIPTION
    assert description == (
        "The user's latest message, copied verbatim. If that message is only a short confirmation "
        "(for example 'да', 'согласую', "
        "'делай', 'ок'), copy the last substantive request "
        "before it. Optional; recorded in the local audit log as reported by you.")
    assert "verbatim" in description
    assert "да" in description  # the Russian confirmation 'da'
    assert "confirmation" in description


def test_server_instructions_state_the_full_rule_once():
    text = audit.SERVER_INSTRUCTIONS

    assert "user_request" in text
    assert "word for word" in text
    for confirmation in ("да", "согласую",
                         "делай", "ок", "yes", "go ahead"):
        assert confirmation in text, confirmation
    assert "last substantive request" in text
    assert "unverified" in text
    assert "audit log" in text
    assert text.count("user_request") >= 1


def test_the_production_server_publishes_the_wrapped_surface_and_the_instructions():
    import main
    import tools

    assert main.mcp.instructions == audit.SERVER_INSTRUCTIONS
    assert tools.FAILED == {}
    listed = main.mcp._tool_manager.list_tools()
    assert sorted(tool.name for tool in listed) == manifest_names()
    for tool in listed:
        assert "user_request" in tool.parameters["properties"], tool.name
        assert "user_request" not in tool.parameters.get("required", []), tool.name


def _recording_server():
    mcp = FastMCP("recording")
    audit.install_audited_tools(mcp)
    seen = []

    @mcp.tool()
    async def recording_probe(ctx: Context = None) -> str:
        """Record the user request the call state carries."""
        seen.append(audit.current_call().user_request)
        return "ok"

    return mcp, seen


@pytest.mark.anyio
async def test_a_json_looking_user_request_is_accepted_and_recorded_as_text():
    mcp, seen = _recording_server()
    cases = [
        ({}, None),
        ({"user_request": None}, None),
        ({"user_request": "42"}, "42"),
        ({"user_request": "Сделай стену"},
         "Сделай стену"),
        ({"user_request": '{"a":1}'}, '{"a": 1}'),
        ({"user_request": "[1,2]"}, "[1, 2]"),
        ({"user_request": "null"}, None),
    ]

    for arguments, _expected in cases:
        content = await mcp.call_tool("recording_probe", arguments)
        assert content[0].text == "ok", arguments

    assert seen == [expected for _arguments, expected in cases]


@pytest.mark.anyio
async def test_the_bare_word_null_is_recorded_as_a_missing_request():
    mcp, seen = _recording_server()

    await mcp.call_tool("recording_probe", {"user_request": "null"})

    assert seen == [None]
    assert audit.shape_user_request(seen[0], None)["user_request_missing"] is True


@pytest.mark.anyio
async def test_installing_the_wrapper_twice_wraps_each_tool_once():
    mcp = FastMCP("twice")
    audit.install_audited_tools(mcp)
    audit.install_audited_tools(mcp)
    seen = []

    @mcp.tool()
    async def twice_probe(ctx: Context = None) -> str:
        """Record the user request the call state carries."""
        seen.append(audit.current_call().user_request)
        return "ok"

    schema = (await _schemas(mcp))["twice_probe"]
    assert list(schema["properties"]).count("user_request") == 1
    content = await mcp.call_tool("twice_probe", {"user_request": "go"})
    assert content[0].text == "ok"
    assert seen == ["go"]
