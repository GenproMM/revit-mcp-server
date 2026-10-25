# -*- coding: utf-8 -*-
"""get_revit_status names the MCP target it is wired to (D-06, IDENT-05).

The tool reads the ``revit_target`` attribute of the injected ``revit_get``
rather than importing the transport, so it is driven here with a fake callable
that carries (or lacks) that attribute. Driven with asyncio.run, matching
tests/unit/test_registration.py, so the suite needs no async plugin.

Needs no Revit.
"""
import asyncio
import json

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
    assert out == format_response(response) + "\n" + _old_permit_line()
    assert "MCP target" not in out


def test_status_keeps_endpoint_and_short_timeout():
    fake = _make_get({"status": "active"})
    _run_status(fake)
    assert fake.calls == [("/status/", 10.0)]


# --------------------------------------------- shared-secret comparison line (05-07)

_FP_REVIT = "aaaa1111"
_FP_MCP = "bbbb2222"


def _with_fingerprint(fake_get, fingerprint):
    fake_get.secret_fingerprint = fingerprint
    return fake_get


def _status_body(**extra):
    body = {"status": "active", "health": "healthy", "document_title": "M"}
    body.update(extra)
    return body


def _secret_lines(out):
    return [line for line in out.splitlines() if line.startswith("Shared secret:")]


def _old_permit_line():
    return ("One-time permits: the Revit extension does not report permit support (older than R5); "
            "a direct HTTP mutation is not refused for lacking a permit.")


def test_secret_line_same_secret_names_the_fingerprint():
    response = _status_body(secret={"configured": True, "fingerprint": _FP_REVIT})
    out = _run_status(_with_fingerprint(_make_get(response), lambda: _FP_REVIT))
    assert _secret_lines(out) == [
        "Shared secret: both halves hold the same secret (fingerprint aaaa1111)."]
    assert out.splitlines()[-1] == "MCP target: 127.0.0.1:48885"
    assert out.splitlines().index(_secret_lines(out)[0]) == len(out.splitlines()) - 3
    assert out.splitlines()[-2] == _old_permit_line()


def test_secret_line_halves_differ_names_both_and_the_fix():
    response = _status_body(secret={"configured": True, "fingerprint": _FP_REVIT})
    out = _run_status(_with_fingerprint(_make_get(response), lambda: _FP_MCP))
    line = _secret_lines(out)[0]
    assert "DIFFER" in line and _FP_REVIT in line and _FP_MCP in line
    assert "401 mismatch" in line and "Update RevitMCP" in line
    assert "restart the assistant session" in line and "fully restart Revit" in line


def test_secret_line_extension_has_none():
    response = _status_body(secret={"configured": False, "fingerprint": None})
    out = _run_status(_with_fingerprint(_make_get(response), lambda: _FP_MCP))
    line = _secret_lines(out)[0]
    assert "Revit extension has none" in line and "401 server_not_configured" in line


def test_secret_line_this_server_loaded_none():
    response = _status_body(secret={"configured": True, "fingerprint": _FP_REVIT})
    out = _run_status(_with_fingerprint(_make_get(response), lambda: None))
    line = _secret_lines(out)[0]
    assert "this MCP server loaded none" in line and "401 missing" in line
    assert "Update RevitMCP" in line and "assistant session" in line


def test_secret_line_both_without_a_secret_names_the_extension_first():
    response = _status_body(secret={"configured": False, "fingerprint": None})
    out = _run_status(_with_fingerprint(_make_get(response), lambda: None))
    assert "Revit extension has none" in _secret_lines(out)[0]


def test_secret_line_extension_does_not_report():
    out = _run_status(_with_fingerprint(_make_get(_status_body()), lambda: _FP_MCP))
    line = _secret_lines(out)[0]
    assert "does not report its secret state" in line and "older than R3" in line


def test_secret_line_absent_when_neither_side_reports():
    out = _run_status(_make_get(_status_body()))
    assert _secret_lines(out) == []
    assert out == (format_response(_status_body()) + "\n" + _old_permit_line() +
                   "\nMCP target: 127.0.0.1:48885")


def test_secret_line_for_a_503_text_reply():
    body = {"error": "No active Revit document",
            "secret": {"configured": True, "fingerprint": _FP_REVIT}}
    err = "Error: 503 - {}".format(json.dumps(body))
    out = _run_status(_with_fingerprint(_make_get(err), lambda: _FP_MCP))
    assert out.startswith(err)
    assert "DIFFER" in _secret_lines(out)[0]
    same = _run_status(_with_fingerprint(_make_get(err), lambda: _FP_REVIT))
    assert "both halves hold the same secret" in _secret_lines(same)[0]


def test_secret_line_never_shows_more_than_the_fingerprints():
    secret = "never-print-this-secret-0123456789"
    response = _status_body(secret={"configured": True, "fingerprint": _FP_REVIT})
    out = _run_status(_with_fingerprint(_make_get(response), lambda: _FP_MCP))
    assert secret not in out


def test_secret_line_survives_a_raising_fingerprint_reader():
    def boom():
        raise RuntimeError("no secret")

    response = _status_body(secret={"configured": True, "fingerprint": _FP_REVIT})
    out = _run_status(_with_fingerprint(_make_get(response), boom))
    assert "this MCP server loaded none" in _secret_lines(out)[0]


def test_status_docstring_documents_the_secret_integrity_and_bind_blocks():
    mcp = _FakeMCP()
    register_status_tools(mcp, _make_get({}))
    doc = mcp.tools["get_revit_status"].__doc__
    assert "Shared secret" in doc and "fingerprint" in doc
    assert "integrity" in doc and "unverifiable" in doc
    assert "bind" in doc and "loopback" in doc
