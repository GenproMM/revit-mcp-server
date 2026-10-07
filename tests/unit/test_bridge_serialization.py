# -*- coding: utf-8 -*-
"""bridge.py serializes mutating POSTs behind one lock and resolves REVIT_PORT.

CPython side only: the transport is replaced by httpx.MockTransport, so every
test here runs against the real bridge code path with no Revit, no pyRevit and
no network. Needs no Revit.
"""

import asyncio
import os
import subprocess
import sys

import httpx
import pytest

import bridge

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def anyio_backend():
    # trio is not installed and must not be added: pin asyncio.
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_bridge_state():
    # A lock contended in one test's event loop is bound to that loop, and a
    # pooled client belongs to the loop it was first used in.
    bridge._lock = None
    bridge._http_client = None
    yield
    bridge._lock = None
    bridge._http_client = None


def _install_client(handler):
    bridge._http_client = httpx.AsyncClient(
        base_url="http://test:1/revit_mcp",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )


class _Gate(object):
    """A handler that holds /p1/ on an event and records what it has seen."""

    def __init__(self):
        self.seen = []
        self.timeouts = {}
        self.p1_started = asyncio.Event()
        self.release = asyncio.Event()

    async def handler(self, request):
        self.seen.append(request.url.path)
        self.timeouts[request.url.path] = dict(request.extensions["timeout"])
        if request.url.path.endswith("/p1/"):
            self.p1_started.set()
            await self.release.wait()
        return httpx.Response(200, json={"path": request.url.path})


@pytest.mark.anyio
async def test_second_post_waits_for_the_first():
    gate = _Gate()
    _install_client(gate.handler)

    first = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)
    second = asyncio.ensure_future(bridge.revit_post("/p2/", {}))
    await asyncio.sleep(0.05)

    assert gate.seen == ["/revit_mcp/p1/"]

    gate.release.set()
    r1 = await asyncio.wait_for(first, 1.0)
    r2 = await asyncio.wait_for(second, 1.0)
    assert r1 == {"path": "/revit_mcp/p1/"}
    assert r2 == {"path": "/revit_mcp/p2/"}
    assert gate.seen == ["/revit_mcp/p1/", "/revit_mcp/p2/"]


@pytest.mark.anyio
async def test_get_reads_pass_while_locked():
    gate = _Gate()
    _install_client(gate.handler)

    first = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)

    result = await asyncio.wait_for(bridge.revit_get("/status/"), 1.0)
    assert result == {"path": "/revit_mcp/status/"}

    gate.release.set()
    await asyncio.wait_for(first, 1.0)


def test_bridge_imports_without_fastmcp():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, bridge; print('mcp.server.fastmcp' in sys.modules)",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_main_delegates_transport_to_bridge():
    with open(os.path.join(REPO_ROOT, "main.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert "from bridge import revit_get, revit_post, revit_image" in source
    assert "def _revit_call" not in source
    assert "def _get_client" not in source


# --- REVIT_PORT (IDENT-05) ---------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [
        (None, 48884),
        ("48885", 48885),
        (" 48885 ", 48885),
        ("1", 1),
        ("65535", 65535),
    ],
)
def test_port_accepts(value, expected):
    assert bridge._resolve_port(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        "abc",
        "0",
        "65536",
        "-1",
        "+1",
        "48884.0",
        "4_8884",
        "0x10",
        u"٤٨٨٨٤",  # Arabic-Indic digits
    ],
)
def test_port_refuses(value):
    assert issubclass(bridge.RevitConfigError, ValueError)
    with pytest.raises(bridge.RevitConfigError):
        bridge._resolve_port(value)


def test_port_reaches_base_url():
    env = dict(os.environ)
    env["REVIT_HOST"] = "127.0.0.1"
    env["REVIT_PORT"] = "48885"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import bridge; print(bridge.BASE_URL); print(bridge.revit_get.revit_target)",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.split()
    assert lines == ["http://127.0.0.1:48885/revit_mcp", "127.0.0.1:48885"]


def test_port_refusal_writes_stderr_only():
    env = dict(os.environ)
    env["REVIT_PORT"] = "abc"
    result = subprocess.run(
        [sys.executable, "main.py"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"REVIT_PORT" in result.stderr
    assert b"refusing to start" in result.stderr


def test_port_literal_only_in_default():
    import ast

    with open(os.path.join(REPO_ROOT, "bridge.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    allowed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "DEFAULT_REVIT_PORT" in names:
                allowed.add(id(node.value))

    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and node.value == 48884
        and id(node) not in allowed
    ]
    assert offenders == [], "literal 48884 outside DEFAULT_REVIT_PORT at lines {}".format(offenders)


def test_port_target_attribute_on_revit_get():
    expected = "{}:{}".format(bridge.REVIT_HOST, bridge.REVIT_PORT)
    assert bridge.revit_get.revit_target == bridge.REVIT_TARGET == expected


# --- Bounded queue wait (SER-04) ---------------------------------------------

@pytest.mark.anyio
async def test_budget_not_shrunk_by_queue_wait():
    gate = _Gate()
    _install_client(gate.handler)

    first = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)
    # The holder lets go at about 60 percent of the second call's bound.
    asyncio.get_running_loop().call_later(0.3, gate.release.set)

    second = await asyncio.wait_for(bridge.revit_post("/p2/", {}, timeout=0.5), 2.0)
    await asyncio.wait_for(first, 1.0)

    assert second == {"path": "/revit_mcp/p2/"}
    # The wait is not subtracted: httpx got the caller's whole timeout.
    assert gate.timeouts["/revit_mcp/p2/"] == {
        "connect": 0.5, "read": 0.5, "write": 0.5, "pool": 0.5,
    }


@pytest.mark.anyio
async def test_queue_bound_returns_not_sent_without_sending():
    gate = _Gate()
    _install_client(gate.handler)

    first = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)

    result = await asyncio.wait_for(bridge.revit_post("/p2/", {}, timeout=0.1), 2.0)

    assert isinstance(result, str)
    assert "NOT sent to Revit" in result
    assert "nothing was sent" in result
    assert "nothing was changed" in result
    assert gate.seen == ["/revit_mcp/p1/"]

    gate.release.set()
    await asyncio.wait_for(first, 1.0)
    assert gate.seen == ["/revit_mcp/p1/"]
    assert bridge._get_lock().locked() is False


@pytest.mark.anyio
async def test_queue_bound_message_is_an_error_string():
    from tools.utils import format_response

    gate = _Gate()
    _install_client(gate.handler)

    first = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)
    result = await asyncio.wait_for(bridge.revit_post("/p2/", {}, timeout=0.1), 2.0)
    gate.release.set()
    await asyncio.wait_for(first, 1.0)

    assert result.startswith("Error: ")
    after = result[len("Error: "):]
    assert after and not after[0].isdigit()
    assert format_response(result) == result


# --- Release on every exit, failure honesty, wait message (SER-03, D-13, D-14) --

class _Ctx(object):
    """A fake MCP context that records info() lines, or raises from them."""

    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    async def info(self, message):
        if self.fail:
            raise RuntimeError("no active request context")
        self.messages.append(message)


def _routing_handler(behaviours, seen=None):
    """A MockTransport handler: path suffix -> exception to raise, else a 200."""

    async def handler(request):
        if seen is not None:
            seen.append(request.url.path)
        for suffix, factory in behaviours.items():
            if request.url.path.endswith(suffix):
                raise factory(request)
        return httpx.Response(200, json={"path": request.url.path})

    return handler


@pytest.mark.anyio
async def test_releases_after_handler_exception():
    _install_client(_routing_handler({"/boom/": lambda req: RuntimeError("boom")}))

    result = await bridge.revit_post("/boom/", {})
    assert result == "Error: boom"
    assert bridge._get_lock().locked() is False

    assert await asyncio.wait_for(bridge.revit_post("/next/", {}), 1.0) == {"path": "/revit_mcp/next/"}


@pytest.mark.anyio
async def test_releases_after_post_send_timeout():
    _install_client(
        _routing_handler({"/slow/": lambda req: httpx.ReadTimeout("", request=req)})
    )

    result = await bridge.revit_post("/slow/", {})
    assert "outcome UNKNOWN" in result
    assert "may have been applied" in result
    assert "Verify" in result
    assert bridge._get_lock().locked() is False

    assert await asyncio.wait_for(bridge.revit_post("/next/", {}), 1.0) == {"path": "/revit_mcp/next/"}


@pytest.mark.anyio
async def test_releases_after_cancellation_of_holder():
    gate = _Gate()
    _install_client(gate.handler)

    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)
    holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder

    assert bridge._get_lock().locked() is False
    assert await asyncio.wait_for(bridge.revit_post("/p2/", {}), 1.0) == {"path": "/revit_mcp/p2/"}


@pytest.mark.anyio
async def test_releases_cancelled_waiter_is_never_sent():
    gate = _Gate()
    _install_client(gate.handler)

    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)
    waiter = asyncio.ensure_future(bridge.revit_post("/waiter/", {}))
    await asyncio.sleep(0.05)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    gate.release.set()
    assert await asyncio.wait_for(holder, 1.0) == {"path": "/revit_mcp/p1/"}
    assert gate.seen == ["/revit_mcp/p1/"]
    assert bridge._get_lock().locked() is False
    assert await asyncio.wait_for(bridge.revit_post("/p2/", {}), 1.0) == {"path": "/revit_mcp/p2/"}


@pytest.mark.anyio
async def test_releases_queued_posts_in_arrival_order():
    gate = _Gate()
    _install_client(gate.handler)

    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)
    queued = []
    for name in ("q1", "q2", "q3", "q4"):
        queued.append(asyncio.ensure_future(bridge.revit_post("/{}/".format(name), {})))
        await asyncio.sleep(0.02)

    gate.release.set()
    await asyncio.wait_for(asyncio.gather(holder, *queued), 2.0)
    assert gate.seen == [
        "/revit_mcp/p1/", "/revit_mcp/q1/", "/revit_mcp/q2/", "/revit_mcp/q3/", "/revit_mcp/q4/",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error_class",
    [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout],
)
async def test_outcome_unknown_not_claimed_on_connect_error(error_class):
    _install_client(_routing_handler({"/x/": lambda req: error_class("", request=req)}))

    result = await bridge.revit_post("/x/", {})
    assert result.startswith("Error: ")
    assert "was not sent to Revit" in result
    assert "UNKNOWN" not in result
    assert bridge._get_lock().locked() is False


@pytest.mark.anyio
async def test_outcome_unknown_error_text_never_empty():
    _install_client(
        _routing_handler({"/slow/": lambda req: httpx.ReadTimeout("", request=req)})
    )

    got = await bridge.revit_get("/slow/")
    assert got == "Error: ReadTimeout"

    posted = await bridge.revit_post("/slow/", {})
    assert posted.startswith("Error: ")
    assert posted[len("Error: "):].strip() != ""
    assert not posted[len("Error: "):][0].isdigit()


@pytest.mark.anyio
async def test_wait_message_once_when_queued():
    gate = _Gate()
    _install_client(gate.handler)
    ctx = _Ctx()

    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)
    second = asyncio.ensure_future(bridge.revit_post("/p2/", {}, ctx=ctx))
    await asyncio.sleep(0.05)
    assert ctx.messages == [bridge.WAIT_MESSAGE]

    gate.release.set()
    await asyncio.wait_for(asyncio.gather(holder, second), 2.0)
    assert ctx.messages == [bridge.WAIT_MESSAGE]


@pytest.mark.anyio
async def test_wait_message_absent_when_free():
    gate = _Gate()
    _install_client(gate.handler)
    ctx = _Ctx()

    result = await asyncio.wait_for(bridge.revit_post("/p2/", {}, ctx=ctx), 1.0)
    assert result == {"path": "/revit_mcp/p2/"}
    assert ctx.messages == []


@pytest.mark.anyio
async def test_wait_message_failure_does_not_fail_call():
    gate = _Gate()
    _install_client(gate.handler)
    ctx = _Ctx(fail=True)

    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)
    second = asyncio.ensure_future(bridge.revit_post("/p2/", {}, ctx=ctx))
    await asyncio.sleep(0.05)
    gate.release.set()

    r1, r2 = await asyncio.wait_for(asyncio.gather(holder, second), 2.0)
    assert r2 == {"path": "/revit_mcp/p2/"}


# --- Read-only POST allowlist (SER-02, D-08, D-09) -----------------------------

_FIVE_READ_ONLY = {
    "ai_filter",
    "material_quantities",
    "clash_check",
    "list_category_parameters",
    "model_worksets",
}


def _tool_post_endpoints():
    """Every literal revit_post("/route/") endpoint in tools/*.py, as route keys."""
    import glob
    import re

    pattern = re.compile(r'revit_post\(\s*"(/[^"]+)"')
    keys = set()
    for path in glob.glob(os.path.join(REPO_ROOT, "tools", "*.py")):
        with open(path, encoding="utf-8") as handle:
            for match in pattern.finditer(handle.read()):
                keys.add(bridge._route_key(match.group(1)))
    # A scan that finds nothing would pass every assertion below vacuously.
    assert len(keys) >= 30, "drift scan found only {} endpoints".format(len(keys))
    return keys


def test_allowlist_is_exactly_the_five_read_only_routes():
    assert set(bridge.READ_ONLY_POST) == _FIVE_READ_ONLY


def test_allowlist_never_contains_execute_open_save():
    assert set(bridge.NEVER_UNLOCKED) == {"execute_code", "open_model", "save_document"}
    assert set(bridge.READ_ONLY_POST).isdisjoint(bridge.NEVER_UNLOCKED)


def test_allowlist_never_unlocked_routes_stay_locked_even_if_listed(monkeypatch):
    monkeypatch.setattr(
        bridge,
        "READ_ONLY_POST",
        frozenset(set(bridge.READ_ONLY_POST) | set(bridge.NEVER_UNLOCKED)),
    )
    for route in ("execute_code", "open_model", "save_document"):
        assert bridge._is_locked("POST", "/{}/".format(route)) is True


def test_allowlist_unknown_post_is_locked():
    for endpoint in ("/made_up_route/", "made_up_route", "/made_up_route/?x=1"):
        assert bridge._is_locked("POST", endpoint) is True
    for endpoint in ("/ai_filter/", "ai_filter", "/ai_filter/?x=1"):
        assert bridge._is_locked("POST", endpoint) is False


def test_allowlist_get_is_never_locked():
    endpoints = ["/status/", "/made_up_route/", "/execute_code/", "/open_model/", "/save_document/"]
    endpoints += ["/{}/".format(route) for route in _FIVE_READ_ONLY]
    for endpoint in endpoints:
        assert bridge._is_locked("GET", endpoint) is False


def test_allowlist_entries_are_real_tool_endpoints():
    posted = _tool_post_endpoints()
    for route in set(bridge.READ_ONLY_POST) | set(bridge.NEVER_UNLOCKED):
        assert route in posted, "{} is not posted to by any tool".format(route)


def test_allowlist_every_other_tool_post_is_locked():
    for route in _tool_post_endpoints():
        expected_locked = route not in bridge.READ_ONLY_POST
        assert bridge._is_locked("POST", "/{}/".format(route)) is expected_locked, route


@pytest.mark.anyio
async def test_image_reads_pass_while_locked():
    import base64

    gate = _Gate()
    original = gate.handler

    async def handler(request):
        if "/get_view/" in request.url.path:
            payload = base64.b64encode(b"\x89PNG-bytes").decode("ascii")
            return httpx.Response(200, json={"image_data": payload})
        return await original(request)

    _install_client(handler)
    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)

    image = await asyncio.wait_for(bridge.revit_image("/get_view/Level 1"), 1.0)
    assert not isinstance(image, str), image

    gate.release.set()
    await asyncio.wait_for(holder, 1.0)


@pytest.mark.anyio
async def test_allowlisted_post_reads_pass_while_locked():
    gate = _Gate()
    _install_client(gate.handler)
    ctx = _Ctx()

    holder = asyncio.ensure_future(bridge.revit_post("/p1/", {}))
    await asyncio.wait_for(gate.p1_started.wait(), 1.0)

    plain = await asyncio.wait_for(bridge.revit_post("/ai_filter/", {}, ctx=ctx), 1.0)
    queried = await asyncio.wait_for(bridge.revit_post("/ai_filter/?x=1", {}), 1.0)
    assert plain == {"path": "/revit_mcp/ai_filter/"}
    assert queried == {"path": "/revit_mcp/ai_filter/"}
    assert ctx.messages == []  # it never waited, so it never said it would

    gate.release.set()
    await asyncio.wait_for(holder, 1.0)
