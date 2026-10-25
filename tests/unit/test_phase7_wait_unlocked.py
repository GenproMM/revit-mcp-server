# -*- coding: utf-8 -*-
"""A confirmation wait never owns the selected Revit target's dispatch lock (SAFE-03)."""

import asyncio

import mcp.types as types
import pytest
from mcp.server.fastmcp import FastMCP

import approval
import audit
import bridge
import tools
from audit_support import PREFIX, PORT_A, SEL_A, make_machine, release_machine
from elicitation_support import connected
from gate_support import TEST_SECRET
from inventory_support import minimal_kwargs


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def machine(monkeypatch):
    fake = make_machine(monkeypatch)
    monkeypatch.setattr(bridge, "_secret_cache", TEST_SECRET)
    monkeypatch.setattr(bridge, "_authorize", approval.authorize)
    yield fake
    release_machine()


def build_server():
    mcp = FastMCP("phase7-wait-unlocked")
    audit.install_audited_tools(mcp)
    tools.register_tools(mcp, bridge.revit_get, bridge.revit_post, bridge.revit_image)
    assert tools.FAILED == {}
    return mcp


async def call(session, name, **arguments):
    arguments.setdefault("target", SEL_A)
    result = await session.call_tool(name, arguments)
    assert not result.isError, result
    return "".join(part.text for part in result.content)


@pytest.mark.anyio
async def test_confirm_window_holds_no_target_lock_and_allow_call_can_complete(machine):
    opened = asyncio.Event()
    release = asyncio.Event()
    observed_locks = []

    async def callback(context, params):
        observed_locks.append([state.lock.locked() for state in bridge._states.values()])
        opened.set()
        await release.wait()
        return types.ElicitResult(action="accept", content={})

    async with connected(build_server(), callback) as session:
        waiting = asyncio.create_task(call(session, "delete_elements", element_ids=[5]))
        await asyncio.wait_for(opened.wait(), 1.0)
        assert observed_locks and not any(any(row) for row in observed_locks)

        allowed = await asyncio.wait_for(
            bridge.revit_post("/create_level/", minimal_kwargs()["create_level"],
                              target=SEL_A), 1.0)
        assert "NOT sent" not in allowed
        assert any(request.url.path == PREFIX + "/create_level/" for request in machine.requests)
        assert not waiting.done()

        release.set()
        confirmed = await asyncio.wait_for(waiting, 1.0)

    assert "NOT sent" not in confirmed
    assert any(request.url.path == PREFIX + "/delete_elements/" for request in machine.requests)
