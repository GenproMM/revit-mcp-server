# -*- coding: utf-8 -*-
"""get_revit_status names the MCP target it is wired to (D-06, IDENT-05).

The tool reads the ``revit_target`` attribute of the injected ``revit_get``
rather than importing the transport, so it is driven here with a fake callable
that carries (or lacks) that attribute. Driven with asyncio.run, matching
tests/unit/test_registration.py, so the suite needs no async plugin.

Needs no Revit.
"""
import asyncio

from tools.status_tools import register_status_tools
from tools.utils import format_response


class _FakeMCP(object):
    """Collects the functions registered through @mcp.tool()."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


def _make_get(response, target="127.0.0.1:48885", with_target=True):
    calls = []

    async def fake_get(endpoint, ctx=None, timeout=30.0):
        calls.append((endpoint, timeout))
        return response

    if with_target:
        fake_get.revit_target = target
    fake_get.calls = calls
    return fake_get


def _run_status(fake_get):
    mcp = _FakeMCP()
    register_status_tools(mcp, fake_get)
    return asyncio.run(mcp.tools["get_revit_status"](None))


def test_status_reports_target_for_dict():
    fake = _make_get(
        {"status": "active", "health": "healthy", "document_title": "Model A"}
    )
    out = _run_status(fake)
    assert "Document: Model A" in out
    assert out.splitlines()[-1] == "MCP target: 127.0.0.1:48885"


def test_status_reports_target_for_error_string():
    err = "Error: 503 - {\"error\": \"No active Revit document\"}"
    out = _run_status(_make_get(err))
    assert out.startswith(err)
    assert out.splitlines()[-1] == "MCP target: 127.0.0.1:48885"


def test_status_reports_target_when_payload_has_message():
    # format_response reduces a dict with a "message" key to the message alone;
    # the target line is appended after formatting so it survives that.
    out = _run_status(_make_get({"status": "active", "message": "hello"}))
    assert "hello" in out
    assert out.splitlines()[-1] == "MCP target: 127.0.0.1:48885"


def test_status_unchanged_without_target_attribute():
    response = {"status": "active", "health": "healthy", "document_title": "M"}
    out = _run_status(_make_get(response, with_target=False))
    assert out == format_response(response)
    assert "MCP target" not in out


def test_status_keeps_endpoint_and_short_timeout():
    fake = _make_get({"status": "active"})
    _run_status(fake)
    assert fake.calls == [("/status/", 10.0)]
