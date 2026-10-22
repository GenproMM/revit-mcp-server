# -*- coding: utf-8 -*-
"""Offline selected-status tracer: no Revit, OS discovery or network required."""
import asyncio
import base64
import json

import httpx
import pytest

import bridge
from tools.status_tools import register_status_tools

TOKEN = "11111111-1111-4111-8111-111111111111"
IDENTITY = {"pid": 1234, "actual_port": 48885, "session_token": TOKEN,
            "revit_version": "2024"}


def selector(**changes):
    data = dict(host="127.0.0.1", port=48885, pid=1234, session_token=TOKEN)
    data.update(changes)
    return "revit1:" + base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


def run_status(monkeypatch, owners=(1234,), payload=None, status=200, token=None):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, json=payload if payload is not None else {
            "status": "active", "message": "hello", "process_identity": IDENTITY})

    monkeypatch.setattr(bridge, "listener_snapshot", lambda ports: (
        None if owners is None else {48885: list(owners)}))
    original = httpx.AsyncClient
    monkeypatch.setattr(bridge, "_selected_client", lambda target: original(
        base_url="http://127.0.0.1:48885/genpro_revit_mcp/",
        transport=httpx.MockTransport(respond), trust_env=False))
    mcp = FakeMCP()
    register_status_tools(mcp, bridge.revit_get)
    result = asyncio.run(mcp.tools["get_revit_status"](target=token or selector()))
    return result, calls


def test_selected_status_actual_registrar_and_http(monkeypatch):
    out, calls = run_status(monkeypatch)
    assert "hello" in out
    assert "Verified Revit process:" in out
    assert TOKEN in out and "1234" in out and "48885" in out
    assert "2024" in out
    assert len(calls) == 1
    assert calls[0].url.path == "/genpro_revit_mcp/status/"
    assert calls[0].method == "GET"
    assert "MCP target:" not in out


@pytest.mark.parametrize("owners, words", [
    ((1234, 5678), ("1234", "5678", "collision")),
    ((), ("listener",)), ((5678,), ("PID",)),
    (None, ("inventory",)),
])
def test_refusal_sends_nothing(monkeypatch, owners, words):
    out, calls = run_status(monkeypatch, owners=owners)
    assert out.startswith("Error:")
    assert not calls
    assert all(w.lower() in out.lower() for w in words)
    assert "Verified Revit process:" not in out


@pytest.mark.parametrize("changes", [
    {"host": "example.com"}, {"host": "127.0.0.1/path"},
    {"port": True}, {"port": 0}, {"port": 65536},
    {"pid": True}, {"pid": -1}, {"pid": "1234"},
    {"session_token": "garbage"}, {"extra": 1},
])
def test_malformed_selector_no_send(monkeypatch, changes):
    out, calls = run_status(monkeypatch, token=selector(**changes))
    assert out.startswith("Error:") and not calls


@pytest.mark.parametrize("field, value", [
    ("pid", 5678), ("actual_port", 48886),
    ("session_token", "22222222-2222-4222-8222-222222222222"),
    ("pid", True), ("revit_version", ""), ("actual_port", "48885"),
])
def test_received_identity_mismatch_refuses(monkeypatch, field, value):
    identity = dict(IDENTITY, **{field: value})
    out, calls = run_status(monkeypatch, payload={"process_identity": identity})
    assert len(calls) == 1
    assert out.startswith("Error:") and "rediscover" in out.lower()
    assert "Verified Revit process:" not in out


def test_no_doc_503_retains_verified_identity_and_error(monkeypatch):
    out, calls = run_status(monkeypatch, status=503, payload={
        "status": "unhealthy", "error": "No active Revit document",
        "process_identity": IDENTITY})
    assert len(calls) == 1
    assert "No active Revit document" in out
    assert "Verified Revit process:" in out
    assert TOKEN in out


def test_missing_identity_is_not_inferred_from_selector(monkeypatch):
    out, _ = run_status(monkeypatch, payload={"status": "active"})
    assert out.startswith("Error:")
    assert "Verified Revit process:" not in out


def test_explicit_target_never_falls_back_to_model_route():
    out = asyncio.run(bridge.revit_get("/model_info/", target=selector()))
    assert out.startswith("Error:") and "status" in out.lower()


def test_production_parser_matches_approved_dual_bind():
    text = "TCP 127.0.0.1:48991 0.0.0.0:0 LISTENING 112992\n" \
           "TCP 127.0.0.1:48991 0.0.0.0:0 LISTENING 88388\n"
    assert bridge.parse_netstat_listener_rows(text, [48991]) == {48991: [112992, 88388]}
    assert bridge.parse_netstat_listener_rows(text + "truncated", [48991]) is None


@pytest.mark.parametrize("value", ["", "revit2:abc", "revit1:a", "http://localhost:48885", 1, [], "revit1:!"])
def test_selector_syntax_refuses(value):
    with pytest.raises(ValueError):
        bridge.parse_target(value)


@pytest.mark.parametrize("method", ["post", "image"])
def test_selected_non_status_never_sends(method, monkeypatch):
    def forbidden():
        pytest.fail("Legacy client must not be created for a selected unsupported route")
    monkeypatch.setattr(bridge, "_get_client", forbidden)
    if method == "post":
        out = asyncio.run(bridge.revit_post("/execute_code/", {}, target=selector()))
    else:
        out = asyncio.run(bridge.revit_image("/view/", target=selector()))
    assert out.startswith("Error:") and "not sent" in out


@pytest.mark.parametrize("failure", [httpx.ConnectError("offline"),
    httpx.ReadTimeout("late"), "not-json", {"status": "active"}])
def test_transport_or_incomplete_response_never_verified(monkeypatch, failure):
    monkeypatch.setattr(bridge, "listener_snapshot", lambda ports: {48885: [1234]})
    def respond(request):
        if isinstance(failure, Exception):
            raise failure
        if isinstance(failure, str):
            return httpx.Response(200, text=failure)
        return httpx.Response(200, json=failure)
    original = httpx.AsyncClient
    monkeypatch.setattr(bridge, "_selected_client", lambda target: original(
        transport=httpx.MockTransport(respond), base_url="http://localhost/"))
    mcp = FakeMCP()
    register_status_tools(mcp, bridge.revit_get)
    out = asyncio.run(mcp.tools["get_revit_status"](target=selector()))
    assert out.startswith("Error:") and "Verified Revit process:" not in out


def test_parallel_selected_status_does_not_share_identity(monkeypatch):
    other_token = "22222222-2222-4222-8222-222222222222"
    monkeypatch.setattr(bridge, "listener_snapshot", lambda ports: {p: [1234 if p == 48885 else 5678] for p in ports})
    original = httpx.AsyncClient
    async def respond(request):
        await asyncio.sleep(0)
        second = request.url.port == 48886
        identity = dict(IDENTITY, pid=5678, actual_port=48886, session_token=other_token) if second else IDENTITY
        return httpx.Response(200, json={"message": "received", "process_identity": identity})
    monkeypatch.setattr(bridge, "_selected_client", lambda target: original(
        base_url="http://127.0.0.1:{}/genpro_revit_mcp/".format(target["port"]),
        transport=httpx.MockTransport(respond)))
    mcp = FakeMCP()
    register_status_tools(mcp, bridge.revit_get)
    async def both():
        fn = mcp.tools["get_revit_status"]
        return await asyncio.gather(fn(target=selector()), fn(target=selector(
            port=48886, pid=5678, session_token=other_token)))
    first, second = asyncio.run(both())
    assert TOKEN in first and other_token not in first
    assert other_token in second and TOKEN not in second


def test_production_parser_is_same_as_preflight():
    # Keep every strict G5 edge case shared even though the standalone operator
    # procedure must remain runnable without a production bridge/httpx import.
    import ast
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "test_phase2_preflight.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    production = ast.parse(Path(bridge.__file__).read_text(encoding="utf-8"))
    for name in ("_netstat_endpoint_port", "parse_netstat_listener_rows"):
        def body(module):
            fn = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == name)
            return fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body
        assert [ast.dump(n) for n in body(tree)] == [ast.dump(n) for n in body(production)]


def test_listener_adapter_full_command_no_fallback():
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Done", (), {"returncode": 0, "stdout":
            "TCP 127.0.0.1:48885 0.0.0.0:0 LISTENING 1234"})()
    assert bridge.listener_snapshot([48885], run=run, platform="win32") == {48885: [1234]}
    assert calls == [(["netstat.exe", "-ano", "-p", "tcp"],
                      {"capture_output": True, "text": True, "encoding": "ascii",
                       "errors": "replace", "timeout": 10})]
    assert bridge.listener_snapshot([48885], run=run, platform="linux") is None
    assert len(calls) == 1


# Real `netstat.exe -ano -p tcp` heading bytes from a ru-RU Windows 11 host (OEM cp866).
RU_NETSTAT_HEADER_BYTES = (
    b"\r\n\x80\xaa\xe2\xa8\xa2\xad\xeb\xa5 \xaf\xae\xa4\xaa\xab\xee\xe7\xa5\xad\xa8\xef\r\n\r\n"
    b"  \x88\xac\xef    \x8b\xae\xaa\xa0\xab\xec\xad\xeb\xa9 \xa0\xa4\xe0\xa5\xe1        "
    b"\x82\xad\xa5\xe8\xad\xa8\xa9 \xa0\xa4\xe0\xa5\xe1          "
    b"\x91\xae\xe1\xe2\xae\xef\xad\xa8\xa5       PID\r\n"
)
RU_NETSTAT_ROWS = (
    b"  TCP    127.0.0.1:48884        0.0.0.0:0              LISTENING       91920\r\n"
    b"  TCP    127.0.0.1:48884        127.0.0.1:49700        TIME_WAIT       0\r\n"
)


@pytest.mark.parametrize("decode", [
    lambda raw: raw.decode("cp1251", "replace"),
    lambda raw: raw.decode("cp866"),
    lambda raw: raw.decode("ascii", "replace"),
], ids=["cp1251-locale", "cp866-oem", "ascii-replace"])
def test_parser_survives_oem_encoded_localized_headings(decode):
    text = decode(RU_NETSTAT_HEADER_BYTES + RU_NETSTAT_ROWS)
    assert bridge.parse_netstat_listener_rows(text, [48884]) == {48884: [91920]}


def test_heading_skip_cannot_hide_a_garbled_data_row():
    text = "garbled TCP-ish 127.0.0.1:48884 0.0.0.0:0 LISTENING 5\n" \
           "TCP 127.0.0.1:48884 0.0.0.0:0 LISTENING 91920\n"
    assert bridge.parse_netstat_listener_rows(text, [48884]) is None


def test_unknown_text_after_first_row_still_fails_closed():
    text = "heading\nTCP 127.0.0.1:48884 0.0.0.0:0 LISTENING 91920\nheading again\n"
    assert bridge.parse_netstat_listener_rows(text, [48884]) is None
    assert bridge.parse_netstat_listener_rows("heading only\n", [48884]) is None
