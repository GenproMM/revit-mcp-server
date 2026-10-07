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
