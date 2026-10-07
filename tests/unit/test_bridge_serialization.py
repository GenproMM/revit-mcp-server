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
        self.p1_started = asyncio.Event()
        self.release = asyncio.Event()

    async def handler(self, request):
        self.seen.append(request.url.path)
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
