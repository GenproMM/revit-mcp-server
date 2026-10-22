# -*- coding: utf-8 -*-
"""One lock and one client per validated Revit process incarnation (02-03, D-03).

CPython side only. A fake machine replaces both netstat and HTTP, so every test
runs the real bridge dispatch path with no Revit, no pyRevit and no network.
Needs no Revit.
"""

import asyncio
import base64
import json

import httpx
import pytest

import bridge

# The unit-suite guard replaces bridge._selected_client per test; keep the real factory.
REAL_SELECTED_CLIENT = bridge._selected_client

TOKEN_A = "11111111-1111-4111-8111-111111111111"
TOKEN_B = "22222222-2222-4222-8222-222222222222"
TOKEN_A2 = "33333333-3333-4333-8333-333333333333"
PORT_A, PID_A = 48884, 111
PORT_B, PID_B = 48885, 222
PREFIX = "/genpro_revit_mcp"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


def selector(port, pid, token, host="127.0.0.1"):
    data = dict(host=host, port=port, pid=pid, session_token=token)
    return "revit1:" + base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


SEL_A = selector(PORT_A, PID_A, TOKEN_A)
SEL_B = selector(PORT_B, PID_B, TOKEN_B)


class Gate(object):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()


class Machine(object):
    """Listeners, identities and routes of a fake machine."""

    def __init__(self):
        self.listeners = {PORT_A: [PID_A], PORT_B: [PID_B]}
        self.identity = {PORT_A: (PID_A, TOKEN_A), PORT_B: (PID_B, TOKEN_B)}
        self.seen = []            # (port, method, path)
        self.requests = []        # httpx.Request, in arrival order
        self.gates = {}           # (port, path) -> Gate
        self.faults = {}          # (port, path) -> exception factory
        self.clients = []         # every client the factory handed out

    def gate(self, port, route):
        gate = self.gates[(port, PREFIX + route)] = Gate()
        return gate

    def snapshot(self, ports, **_kwargs):
        return dict((p, list(self.listeners.get(p, []))) for p in ports)

    async def respond(self, request):
        port, path = request.url.port, request.url.path
        self.seen.append((port, request.method, path))
        self.requests.append(request)
        if path == PREFIX + "/status/":
            who = self.identity.get(port)
            if who is None:
                raise httpx.ConnectError("refused", request=request)
            return httpx.Response(200, json={"status": "active", "process_identity": {
                "pid": who[0], "actual_port": port, "session_token": who[1],
                "revit_version": "2024"}})
        fault = self.faults.get((port, path))
        if fault is not None:
            raise fault(request)
        gate = self.gates.get((port, path))
        if gate is not None:
            gate.started.set()
            await gate.release.wait()
        if path.startswith(PREFIX + "/get_view/"):
            payload = base64.b64encode(b"\x89PNG-bytes").decode("ascii")
            return httpx.Response(200, json={"image_data": payload})
        return httpx.Response(200, json={"port": port, "path": path})

    def client(self, target):
        client = httpx.AsyncClient(
            base_url="http://127.0.0.1:{}{}/".format(target["port"], PREFIX),
            transport=httpx.MockTransport(self.respond), trust_env=False)
        self.clients.append(client)
        return client

    def routes(self, port=None):
        """Requested (non-status) routes, as (port, method, path)."""
        return [s for s in self.seen
                if s[2] != PREFIX + "/status/" and (port is None or s[0] == port)]


@pytest.fixture
def machine(monkeypatch):
    fake = Machine()
    monkeypatch.setattr(bridge, "listener_snapshot", fake.snapshot)
    monkeypatch.setattr(bridge, "_selected_client", fake.client)
    states = getattr(bridge, "_states", None)
    if isinstance(states, dict):
        states.clear()
    yield fake
    states = getattr(bridge, "_states", None)
    if isinstance(states, dict):
        states.clear()


async def started(gate):
    await asyncio.wait_for(gate.started.wait(), 1.0)


def target_of(sel):
    return bridge.parse_target(sel)


# --- one lock per incarnation -------------------------------------------------

@pytest.mark.anyio
async def test_two_calls_to_one_process_wait_for_each_other(machine):
    gate = machine.gate(PORT_A, "/p1/")
    first = asyncio.ensure_future(bridge.revit_post("/p1/", {}, target=SEL_A))
    await started(gate)
    second = asyncio.ensure_future(bridge.revit_post("/p2/", {}, target=SEL_A))
    await asyncio.sleep(0.05)
    assert machine.routes() == [(PORT_A, "POST", PREFIX + "/p1/")]
    gate.release.set()
    r1 = await asyncio.wait_for(first, 1.0)
    r2 = await asyncio.wait_for(second, 1.0)
    assert r1["path"] == PREFIX + "/p1/" and r2["path"] == PREFIX + "/p2/"
    assert [s[2] for s in machine.routes()] == [PREFIX + "/p1/", PREFIX + "/p2/"]


@pytest.mark.anyio
async def test_calls_to_different_processes_overlap(machine):
    gate = machine.gate(PORT_A, "/p1/")
    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}, target=SEL_A))
    await started(gate)
    other = await asyncio.wait_for(bridge.revit_post("/p2/", {}, target=SEL_B), 1.0)
    assert other == {"port": PORT_B, "path": PREFIX + "/p2/"}
    assert not holder.done()
    gate.release.set()
    await asyncio.wait_for(holder, 1.0)


@pytest.mark.anyio
async def test_documents_of_one_process_share_its_lock(machine):
    gate = machine.gate(PORT_A, "/p1/")
    first = asyncio.ensure_future(
        bridge.revit_post("/p1/", {"document": "doc-one"}, target=SEL_A))
    await started(gate)
    second = asyncio.ensure_future(
        bridge.revit_post("/p2/", {"document": "doc-two"}, target=SEL_A))
    await asyncio.sleep(0.05)
    assert [s[2] for s in machine.routes()] == [PREFIX + "/p1/"]
    gate.release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 1.0)
    assert [s[2] for s in machine.routes()] == [PREFIX + "/p1/", PREFIX + "/p2/"]


@pytest.mark.anyio
async def test_lock_key_is_the_incarnation_not_the_document_or_port(machine):
    a, b = target_of(SEL_A), target_of(SEL_B)
    assert bridge._get_lock(a) is bridge._get_lock(dict(a))
    assert bridge._get_lock(a) is not bridge._get_lock(b)
    assert bridge._get_client(a) is not bridge._get_client(b)
    restarted = dict(a, session_token=TOKEN_A2)
    assert bridge._get_lock(restarted) is not bridge._get_lock(a)
    assert bridge._get_client(restarted) is not bridge._get_client(a)


@pytest.mark.anyio
async def test_status_is_the_only_call_that_bypasses_the_lock(machine):
    gate = machine.gate(PORT_A, "/p1/")
    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}, target=SEL_A))
    await started(gate)
    status = await asyncio.wait_for(bridge.revit_get("/status/", target=SEL_A), 1.0)
    assert status["_verified_process"]["pid"] == PID_A
    model = asyncio.ensure_future(bridge.revit_get("/model_info/", target=SEL_A))
    await asyncio.sleep(0.05)
    assert not any(s[2].endswith("/model_info/") for s in machine.seen)
    gate.release.set()
    await asyncio.wait_for(asyncio.gather(holder, model), 1.0)
    assert bridge.UNLOCKED_GET == frozenset({"status"})


@pytest.mark.anyio
async def test_image_is_serialized_per_process_like_every_other_route(machine):
    gate = machine.gate(PORT_A, "/p1/")
    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}, target=SEL_A))
    await started(gate)
    same = asyncio.ensure_future(bridge.revit_image("/get_view/Level 1", target=SEL_A))
    await asyncio.sleep(0.05)
    assert not any("/get_view/" in s[2] for s in machine.seen)
    # Another process is not held up by it.
    other = await asyncio.wait_for(bridge.revit_image("/get_view/Level 2", target=SEL_B), 1.0)
    assert not isinstance(other, str), other
    gate.release.set()
    await asyncio.wait_for(holder, 1.0)
    result = await asyncio.wait_for(same, 1.0)
    assert not isinstance(result, str), result


# --- failure honesty ----------------------------------------------------------

@pytest.mark.anyio
async def test_queue_timeout_is_not_sent_and_sends_nothing(machine):
    gate = machine.gate(PORT_A, "/p1/")
    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}, target=SEL_A))
    await started(gate)
    result = await asyncio.wait_for(
        bridge.revit_post("/p2/", {}, target=SEL_A, timeout=0.1), 2.0)
    assert result.startswith("Error: ") and "NOT sent to Revit" in result
    assert "nothing was changed" in result
    gate.release.set()
    await asyncio.wait_for(holder, 1.0)
    assert [s[2] for s in machine.routes()] == [PREFIX + "/p1/"]
    assert bridge._get_lock(target_of(SEL_A)).locked() is False


@pytest.mark.anyio
async def test_post_failure_after_send_is_outcome_unknown_and_lock_is_released(machine):
    machine.faults[(PORT_A, PREFIX + "/slow/")] = lambda req: httpx.ReadTimeout("", request=req)
    result = await bridge.revit_post("/slow/", {}, target=SEL_A)
    assert "outcome UNKNOWN" in result and "may have been applied" in result
    assert bridge._get_lock(target_of(SEL_A)).locked() is False
    assert (await asyncio.wait_for(bridge.revit_post("/ok/", {}, target=SEL_A), 1.0))["path"].endswith("/ok/")


@pytest.mark.anyio
async def test_connect_failure_never_claims_unknown_and_names_the_target_address(machine):
    machine.faults[(PORT_A, PREFIX + "/x/")] = lambda req: httpx.ConnectError("", request=req)
    result = await bridge.revit_post("/x/", {}, target=SEL_A)
    assert "was not sent to Revit" in result and "UNKNOWN" not in result
    assert "127.0.0.1:{}".format(PORT_A) in result


@pytest.mark.anyio
async def test_get_failure_is_reported_plainly(machine):
    machine.faults[(PORT_A, PREFIX + "/slow/")] = lambda req: httpx.ReadTimeout("", request=req)
    result = await bridge.revit_get("/slow/", target=SEL_A)
    assert result == "Error: ReadTimeout" and "UNKNOWN" not in result


@pytest.mark.anyio
async def test_cancelled_holder_releases_its_process_lock_only(machine):
    gate = machine.gate(PORT_A, "/p1/")
    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}, target=SEL_A))
    await started(gate)
    holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder
    assert bridge._get_lock(target_of(SEL_A)).locked() is False
    again = await asyncio.wait_for(bridge.revit_post("/p2/", {}, target=SEL_A), 1.0)
    assert again["path"].endswith("/p2/")


@pytest.mark.anyio
async def test_post_body_stays_text_plain_on_a_selected_target(machine):
    await bridge.revit_post("/p1/", {"x": 1}, target=SEL_A)
    posted = [r for r in machine.requests if r.method == "POST"]
    assert len(posted) == 1
    assert posted[0].headers["content-type"] == "text/plain; charset=utf-8"
    assert json.loads(posted[0].content.decode("utf-8")) == {"x": 1}


@pytest.mark.anyio
async def test_pooled_client_never_uses_environment_proxies():
    client = REAL_SELECTED_CLIENT(target_of(SEL_A))
    try:
        assert client._trust_env is False and client.follow_redirects is False
    finally:
        await client.aclose()


# --- handshake before the requested send --------------------------------------

@pytest.mark.anyio
async def test_status_handshake_precedes_the_requested_route_on_one_client(machine):
    await bridge.revit_post("/p1/", {}, target=SEL_A)
    assert [(s[1], s[2]) for s in machine.seen][-2:] == [
        ("GET", PREFIX + "/status/"), ("POST", PREFIX + "/p1/")]
    assert len(machine.clients) == 1


@pytest.mark.anyio
async def test_restarted_process_with_reused_pid_and_port_never_receives_the_call(machine):
    machine.identity[PORT_A] = (PID_A, TOKEN_A2)          # same PID, same port, new token
    result = await bridge.revit_post("/modify/", {}, target=SEL_A)
    assert result.startswith("Error:") and "rediscover" in result.lower()
    assert "not sent" in result.lower()
    assert machine.routes() == []
    assert bridge._states == {}                            # the stale selector left no state


@pytest.mark.anyio
async def test_old_and_new_incarnation_never_share_lock_client_or_state(machine):
    old_state = None
    await bridge.revit_post("/p1/", {}, target=SEL_A)
    old_key = bridge._target_key(target_of(SEL_A))
    old_state = bridge._states[old_key]
    old_client = old_state.client
    machine.identity[PORT_A] = (PID_A, TOKEN_A2)
    new_sel = selector(PORT_A, PID_A, TOKEN_A2)
    result = await bridge.revit_post("/p2/", {}, target=new_sel)
    assert result["path"].endswith("/p2/")
    assert old_key not in bridge._states
    new_state = bridge._states[bridge._target_key(target_of(new_sel))]
    assert new_state is not old_state
    assert new_state.lock is not old_state.lock and new_state.client is not old_client
    assert old_client.is_closed
    stale = await bridge.revit_post("/p3/", {}, target=SEL_A)
    assert stale.startswith("Error:") and "rediscover" in stale.lower()
    assert new_state is bridge._states[bridge._target_key(target_of(new_sel))]


@pytest.mark.anyio
async def test_eviction_does_not_close_a_call_still_in_flight(machine):
    gate = machine.gate(PORT_A, "/p1/")
    inflight = asyncio.ensure_future(bridge.revit_post("/p1/", {}, target=SEL_A))
    await started(gate)
    old_state = bridge._states[bridge._target_key(target_of(SEL_A))]
    old_client = old_state.client
    # The incarnation is replaced while the old call is still running.
    machine.identity[PORT_A] = (PID_A, TOKEN_A2)
    new_sel = selector(PORT_A, PID_A, TOKEN_A2)
    fresh = await asyncio.wait_for(bridge.revit_post("/p2/", {}, target=new_sel), 1.0)
    assert fresh["path"].endswith("/p2/")
    assert bridge._target_key(target_of(SEL_A)) not in bridge._states
    assert old_client.is_closed is False                    # still serving its in-flight call
    gate.release.set()
    done = await asyncio.wait_for(inflight, 1.0)
    assert done["path"].endswith("/p1/")
    assert old_client.is_closed is True


@pytest.mark.anyio
async def test_duplicate_listener_after_selection_refuses_before_sending(machine):
    machine.listeners[PORT_A] = [PID_A, 999]
    result = await bridge.revit_post("/p1/", {}, target=SEL_A)
    assert result.startswith("Error:") and "111" in result and "999" in result
    assert machine.seen == []                              # no HTTP of any kind
    assert bridge._states == {}


# --- default (no selector) dispatch -------------------------------------------

@pytest.mark.anyio
async def test_no_selector_with_two_usable_processes_refuses_and_sends_no_route(machine):
    result = await bridge.revit_post("/p1/", {})
    assert result.startswith("Error:") and "not sent" in result.lower()
    assert SEL_A in result and SEL_B in result
    assert machine.routes() == []
    assert bridge._states == {}


@pytest.mark.anyio
@pytest.mark.parametrize("make", [
    lambda: bridge.revit_get("/list_levels/"),
    lambda: bridge.revit_post("/p1/", {}),
    lambda: bridge.revit_image("/get_view/x"),
    lambda: bridge.revit_get("/status/"),
])
async def test_no_selector_with_two_usable_refuses_every_transport(machine, make):
    result = await make()
    assert isinstance(result, str) and result.startswith("Error:")
    assert SEL_A in result and SEL_B in result
    assert machine.routes() == []


@pytest.mark.anyio
async def test_no_selector_with_one_usable_dispatches_to_that_incarnation(machine):
    del machine.listeners[PORT_A], machine.identity[PORT_A]
    result = await bridge.revit_post("/p1/", {})
    assert result == {"port": PORT_B, "path": PREFIX + "/p1/"}
    assert machine.routes() == [(PORT_B, "POST", PREFIX + "/p1/")]
    levels = await bridge.revit_get("/list_levels/")
    assert levels["port"] == PORT_B


@pytest.mark.anyio
async def test_no_selector_with_no_process_names_the_failure(machine):
    machine.listeners.clear()
    result = await bridge.revit_get("/list_levels/")
    assert result.startswith("Error:") and "no usable revit process" in result.lower()
    assert machine.seen == []


@pytest.mark.anyio
async def test_no_selector_status_keeps_the_legacy_result_shapes(machine):
    del machine.listeners[PORT_A], machine.identity[PORT_A]
    payload = await bridge.revit_get("/status/")
    assert isinstance(payload, dict) and payload["status"] == "active"
    assert "_verified_process" not in payload
