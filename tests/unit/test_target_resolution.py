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


def test_explicit_target_with_unavailable_inventory_sends_no_model_route(monkeypatch):
    # 02-03: a selected model route is dispatched like any other call, but only
    # after the incarnation is proven. Without a listener inventory it is
    # refused before any HTTP, and never falls back to a configured address.
    sent = []
    original = httpx.AsyncClient
    monkeypatch.setattr(bridge, "_selected_client", lambda target: original(
        base_url="http://127.0.0.1:48885/genpro_revit_mcp/",
        transport=httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(200, json={}))))
    out = asyncio.run(bridge.revit_get("/model_info/", target=selector()))
    assert out.startswith("Error:") and "inventory" in out.lower() and "not sent" in out.lower()
    assert sent == []


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
def test_selected_non_status_never_sends_without_a_proven_incarnation(method, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No client may be used for a selected route before its incarnation is proven")
    monkeypatch.setattr(bridge, "_get_client", forbidden)
    monkeypatch.setattr(bridge, "listener_snapshot", lambda ports, **kwargs: None)
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


# --- 02-03 Task 1: discovery, unambiguous default, discovery facade ----------
# Offline throughout: netstat and HTTP are both replaced, so these tests never
# touch a real Revit, the OS socket table or the network.

TOKEN_B = "22222222-2222-4222-8222-222222222222"


class World:
    """A fake machine: listeners per port and what each port's HTTP side says."""

    def __init__(self, listeners, revit=None, inventory=True):
        self.listeners = listeners          # {port: [pid, ...]}
        self.revit = revit or {}            # {port: ("ok", pid, token, status) | ("http", code) | ("raise", exc)}
        self.inventory = inventory
        self.requests = []                  # [(port, method, path)]
        self.snapshot_ports = []

    def snapshot(self, ports, **_kwargs):
        self.snapshot_ports.append(list(ports))
        if not self.inventory:
            return None
        return dict((p, list(self.listeners.get(p, []))) for p in ports)

    def client(self, target):
        def respond(request):
            port = request.url.port
            self.requests.append((port, request.method, request.url.path))
            kind = self.revit.get(port, ("raise", httpx.ConnectError("refused")))
            if kind[0] == "raise":
                raise kind[1]
            if kind[0] == "http":
                return httpx.Response(kind[1], text="not ours")
            _, pid, token, status = kind
            body = {"status": "active" if status == 200 else "unhealthy",
                    "process_identity": {"pid": pid, "actual_port": port,
                                         "session_token": token, "revit_version": "2024"}}
            if status == 503:
                body["error"] = "No active Revit document"
            return httpx.Response(status, json=body)
        return httpx.AsyncClient(
            base_url="http://127.0.0.1:{}/genpro_revit_mcp/".format(target["port"]),
            transport=httpx.MockTransport(respond), trust_env=False)

    def install(self, monkeypatch):
        monkeypatch.setattr(bridge, "listener_snapshot", self.snapshot)
        monkeypatch.setattr(bridge, "_selected_client", self.client)
        return self


def one_revit(port=48884, pid=1234, token=TOKEN, status=200):
    return {"listeners": {port: [pid]}, "revit": {port: ("ok", pid, token, status)}}


def test_discovery_zero_listeners_is_a_named_empty_result(monkeypatch):
    world = World({}).install(monkeypatch)
    result = asyncio.run(bridge.discover_targets())
    assert result["status"] == "ok"
    assert result["usable"] == [] and result["unusable"] == []
    assert world.requests == []
    with pytest.raises(ValueError) as caught:
        asyncio.run(bridge.resolve_default_target())
    assert "no usable revit process" in str(caught.value).lower()
    assert "not sent" in str(caught.value).lower()


def test_discovery_one_usable_defaults_to_that_incarnation(monkeypatch):
    world = World(**one_revit(port=48886, pid=4321, token=TOKEN)).install(monkeypatch)
    result = asyncio.run(bridge.discover_targets())
    assert [u["pid"] for u in result["usable"]] == [4321]
    entry = result["usable"][0]
    assert entry["port"] == 48886 and entry["session_token"] == TOKEN
    assert entry["revit_version"] == "2024" and entry["document_open"] is True
    parsed = bridge.parse_target(entry["selector"])
    assert (parsed["pid"], parsed["port"], parsed["session_token"]) == (4321, 48886, TOKEN)
    target = asyncio.run(bridge.resolve_default_target())
    assert (target["pid"], target["port"], target["session_token"]) == (4321, 48886, TOKEN)
    # Only the identity route is ever requested while discovering.
    assert world.requests and all(p == "/genpro_revit_mcp/status/" for _, _, p in world.requests)
    assert all(m == "GET" for _, m, _ in world.requests)


def test_discovery_no_document_503_is_usable_not_absent(monkeypatch):
    World(**one_revit(status=503)).install(monkeypatch)
    result = asyncio.run(bridge.discover_targets())
    assert len(result["usable"]) == 1
    assert result["usable"][0]["document_open"] is False
    assert asyncio.run(bridge.resolve_default_target())["pid"] == 1234


def test_discovery_two_usable_refuses_default_and_lists_every_candidate(monkeypatch):
    world = World(
        {48884: [111], 48885: [222]},
        {48884: ("ok", 111, TOKEN, 200), 48885: ("ok", 222, TOKEN_B, 200)},
    ).install(monkeypatch)
    result = asyncio.run(bridge.discover_targets())
    assert sorted(u["pid"] for u in result["usable"]) == [111, 222]
    with pytest.raises(ValueError) as caught:
        asyncio.run(bridge.resolve_default_target())
    text = str(caught.value)
    assert "not sent" in text.lower() and "multiple" in text.lower()
    for entry in result["usable"]:
        assert entry["selector"] in text and str(entry["pid"]) in text
    assert all(p == "/genpro_revit_mcp/status/" for _, _, p in world.requests)


def test_same_port_pair_is_unusable_names_both_pids_and_is_never_probed(monkeypatch):
    world = World({48884: [111, 222]}, {48884: ("ok", 111, TOKEN, 200)}).install(monkeypatch)
    result = asyncio.run(bridge.discover_targets())
    assert result["usable"] == []
    assert len(result["unusable"]) == 1
    entry = result["unusable"][0]
    assert entry["port"] == 48884 and entry["pids"] == [111, 222]
    assert entry["reason"] == "listener-collision"
    assert "111" in entry["detail"] and "222" in entry["detail"]
    assert world.requests == []          # a duplicated listener is never handshaken
    with pytest.raises(ValueError) as caught:
        asyncio.run(bridge.resolve_default_target())
    assert "111" in str(caught.value) and "222" in str(caught.value)


def test_collision_beside_one_usable_process_still_refuses_the_default(monkeypatch):
    world = World(
        {48884: [111, 222], 48885: [333]},
        {48885: ("ok", 333, TOKEN, 200)},
    ).install(monkeypatch)
    with pytest.raises(ValueError) as caught:
        asyncio.run(bridge.resolve_default_target())
    text = str(caught.value)
    assert "111" in text and "222" in text and "collision" in text.lower()
    assert [r[0] for r in world.requests] == [48885]


def test_inventory_failure_is_a_named_refusal_not_an_empty_list(monkeypatch):
    world = World({}, inventory=False).install(monkeypatch)
    result = asyncio.run(bridge.discover_targets())
    assert result["status"] == "inventory-unavailable"
    assert result["usable"] == [] and result["unusable"] == []
    assert "inventory" in result["message"].lower()
    with pytest.raises(ValueError) as caught:
        asyncio.run(bridge.resolve_default_target())
    assert "inventory" in str(caught.value).lower()
    assert "no usable" not in str(caught.value).lower()
    assert world.requests == []


@pytest.mark.parametrize("answer, reason", [
    (("raise", httpx.ReadTimeout("late")), "handshake-failed"),
    (("raise", httpx.ConnectError("refused")), "handshake-failed"),
    (("http", 404), "not-revit-status"),
    (("ok", 999, TOKEN, 200), "identity-mismatch"),      # answers as another PID
])
def test_singleton_listener_that_cannot_prove_identity_is_unusable(monkeypatch, answer, reason):
    World({48884: [111]}, {48884: answer}).install(monkeypatch)
    result = asyncio.run(bridge.discover_targets())
    assert result["usable"] == []
    assert [(u["port"], u["pids"], u["reason"]) for u in result["unusable"]] == [(48884, [111], reason)]
    with pytest.raises(ValueError):
        asyncio.run(bridge.resolve_default_target())


def test_discovery_probe_window_covers_default_and_configured_port(monkeypatch):
    world = World({}).install(monkeypatch)
    asyncio.run(bridge.discover_targets())
    probed = world.snapshot_ports[0]
    assert bridge.DEFAULT_REVIT_PORT in probed and bridge.REVIT_PORT in probed
    assert probed == sorted(set(probed))


# The unit-suite guard replaces bridge._selected_client per test; keep the real factory.
REAL_SELECTED_CLIENT = bridge._selected_client


def test_probe_client_never_uses_environment_proxies_and_never_redirects():
    client = REAL_SELECTED_CLIENT({"host": "127.0.0.1", "port": 48884})
    assert client._trust_env is False
    assert client.follow_redirects is False
    assert str(client.base_url) == "http://127.0.0.1:48884/genpro_revit_mcp/"


def test_restarted_process_on_reused_pid_and_port_is_rejected_for_old_selector(monkeypatch):
    # Same PID, same port, new token: the old selector must not be accepted.
    world = World(**one_revit(token=TOKEN_B)).install(monkeypatch)
    out = asyncio.run(bridge.revit_get("/status/", target=selector(port=48884)))
    assert out.startswith("Error:") and "rediscover" in out.lower()
    assert "Verified" not in out
    assert all(p == "/genpro_revit_mcp/status/" for _, _, p in world.requests)


def test_facade_is_attached_to_the_injected_get_callable():
    assert bridge.revit_get.discover_targets is bridge.discover_targets
    assert bridge.revit_get.revit_target == bridge.REVIT_TARGET


class FakeServer:
    """Collects tools the way FastMCP would, without importing the server."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


def _registered_discovery_tool(get_callable):
    import tools
    server = FakeServer()

    async def unused(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("discovery must not use the post/image transports")

    tools.register_tools(server, get_callable, unused, unused)
    return server.tools["discover_revit_targets"]


def test_discovery_tool_through_the_actual_registration_callable(monkeypatch):
    World(
        {48884: [111, 222], 48885: [333], 48886: [444]},
        {48885: ("ok", 333, TOKEN, 200), 48886: ("ok", 444, TOKEN_B, 503)},
    ).install(monkeypatch)
    tool = _registered_discovery_tool(bridge.revit_get)
    out = asyncio.run(tool())
    assert isinstance(out, str)
    for port, pid, token in ((48885, 333, TOKEN), (48886, 444, TOKEN_B)):
        assert selector(port=port, pid=pid, session_token=token) in out
    assert "333" in out and "444" in out
    assert "111" in out and "222" in out and "collision" in out.lower()
    assert "no document" in out.lower()
    # The collision is never offered as a selector.
    assert out.count("revit1:") == 2


def test_discovery_tool_reports_inventory_failure_visibly(monkeypatch):
    World({}, inventory=False).install(monkeypatch)
    out = asyncio.run(_registered_discovery_tool(bridge.revit_get)())
    assert out.startswith("Error:") and "inventory" in out.lower()
    assert "no usable" not in out.lower()


def test_discovery_tool_reports_zero_processes_distinctly(monkeypatch):
    World({}).install(monkeypatch)
    out = asyncio.run(_registered_discovery_tool(bridge.revit_get)())
    assert "no usable revit" in out.lower() and "inventory" not in out.lower()


def test_discovery_tool_without_facade_fails_visibly_and_never_reports_none():
    async def plain_get(endpoint, ctx=None, **kwargs):  # pragma: no cover - never called
        raise AssertionError("an unselected route must not be requested")
    out = asyncio.run(_registered_discovery_tool(plain_get)())
    assert out.startswith("Error:") and "discovery" in out.lower()
