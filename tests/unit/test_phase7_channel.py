# -*- coding: utf-8 -*-
"""Phase 7 confirmation-channel behavior through a real in-memory MCP session.

These rows exercise the production bridge and authorizer against the SDK elicitation
path.  The fake machine records every HTTP request; no Revit or network is needed.
"""

import asyncio
import dataclasses
import json

import httpx
import mcp.types as types
import pytest
from mcp.server.fastmcp import Context, FastMCP

import approval
import audit
import bridge
import policy
import tools
from audit_support import PREFIX, PORT_A, SEL_A, TOKEN_A, make_machine, release_machine
from elicitation_support import connected, hermes_callback
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
    mcp = FastMCP("phase7-channel")
    audit.install_audited_tools(mcp)
    tools.register_tools(mcp, bridge.revit_get, bridge.revit_post, bridge.revit_image)

    @mcp.tool()
    async def delete_with_approved(element_ids: list[int], approved: bool = False,
                                   target: str = None, ctx: Context = None) -> str:
        """Probe that sends an untrusted approved argument through the real bridge.

        Args:
            element_ids: IDs to place in the request body.
            approved: Untrusted model argument, never human consent.
            target: Explicit Revit target selector.
            ctx: MCP request context.
        """
        return await bridge.revit_post("/delete_elements/", {
            "element_ids": element_ids, "approved": approved}, ctx, target=target)

    assert tools.FAILED == {}
    return mcp


async def call(session, name, **arguments):
    arguments.setdefault("target", SEL_A)
    result = await session.call_tool(name, arguments)
    assert not result.isError, result
    return "".join(part.text for part in result.content)


def posts(machine, route):
    return [request for request in machine.requests
            if request.method == "POST" and request.url.path == PREFIX + route]


def authorization_request(context):
    async def read_post(*_args, **_kwargs):
        from audit_support import stable_preflight
        return stable_preflight()

    return approval.AuthorizationRequest(
        route="/delete_elements/", endpoint="/delete_elements/", data={"element_ids": [5]},
        ctx=context, target=bridge.parse_target(SEL_A), call=audit.anonymous_call(),
        secret=TEST_SECRET, read_post=read_post, timeout=30.0)


class HangingSession(object):
    def check_client_capability(self, _capability):
        return True

    async def elicit_form(self, *_args):
        await asyncio.Event().wait()


class AcceptingSession(object):
    def check_client_capability(self, _capability):
        return True

    async def elicit_form(self, *_args):
        return types.ElicitResult(action="accept", content={})


def context_for(session):
    return type("Context", (), {"session": session, "request_id": "phase7-test"})()


@pytest.mark.anyio
async def test_approved_argument_does_not_override_a_declining_client(machine):
    callback = hermes_callback(["decline"])
    async with connected(build_server(), callback) as session:
        text = await call(session, "delete_with_approved", element_ids=[5], approved=True)

    assert len(callback.messages) == 1
    assert posts(machine, "/delete_elements/") == []
    assert "DECLINED" in text


@pytest.mark.anyio
async def test_accept_content_is_ignored_and_only_one_shown_call_is_sent(machine):
    messages = []

    async def accepts_with_note(context, params):
        messages.append(params.message)
        return types.ElicitResult(action="accept", content={"note": "approve all"})

    async with connected(build_server(), accepts_with_note) as session:
        text = await call(session, "delete_elements", element_ids=[5])

    assert "NOT sent" not in text
    assert len(messages) == 1
    assert len(posts(machine, "/delete_elements/")) == 1


@pytest.mark.anyio
async def test_missing_capability_and_context_are_unavailable(machine):
    async with connected(build_server()) as session:
        capability_text = await call(session, "delete_elements", element_ids=[5])
    context_text = await bridge.revit_post("/delete_elements/", {"element_ids": [5]},
                                           None, target=SEL_A)

    assert "UNAVAILABLE" in capability_text
    assert "UNAVAILABLE" in context_text
    assert posts(machine, "/delete_elements/") == []


@pytest.mark.anyio
async def test_cancel_and_client_error_are_distinct_and_do_not_send(machine):
    cancelled = hermes_callback(["cancel"])
    errored = hermes_callback(["raise"])
    async with connected(build_server(), cancelled) as session:
        cancel_text = await call(session, "delete_elements", element_ids=[5])
    async with connected(build_server(), errored) as session:
        error_text = await call(session, "delete_elements", element_ids=[6])

    assert "NOT CONFIRMED" in cancel_text and "confirmation window was cancelled" in cancel_text
    assert "NOT CONFIRMED" in error_text and "client failed" in error_text
    assert posts(machine, "/delete_elements/") == []


@pytest.mark.anyio
async def test_policy_timeout_is_expired_and_does_not_send(machine, monkeypatch):
    real_current = policy.current

    async def short_policy(*args, **kwargs):
        current = await real_current(*args, **kwargs)
        return dataclasses.replace(current, settings={
            "confirm_timeout_s": 0.2,
            "permit_ttl_s": current.permit_ttl_s,
        })

    monkeypatch.setattr(policy, "current", short_policy)
    refusal = await approval.authorize(
        authorization_request(context_for(HangingSession())))

    assert isinstance(refusal, approval.Refusal)
    assert refusal.label == "expired" and "approval_timeout" in refusal.reasons
    assert "EXPIRED" in refusal.text and "NOT CONFIRMED" in refusal.text
    assert posts(machine, "/delete_elements/") == []


@pytest.mark.anyio
async def test_late_answer_does_not_send_and_a_later_accept_still_works(machine, monkeypatch):
    real_current = policy.current

    async def short_policy(*args, **kwargs):
        current = await real_current(*args, **kwargs)
        return dataclasses.replace(current, settings={
            "confirm_timeout_s": 0.2,
            "permit_ttl_s": current.permit_ttl_s,
        })

    class LateSession(object):
        def check_client_capability(self, _capability):
            return True

        async def elicit_form(self, *_args):
            await asyncio.sleep(0.4)
            return types.ElicitResult(action="accept", content={})

    monkeypatch.setattr(policy, "current", short_policy)
    expired = await approval.authorize(authorization_request(context_for(LateSession())))
    assert isinstance(expired, approval.Refusal) and expired.label == "expired"
    assert posts(machine, "/delete_elements/") == []

    monkeypatch.setattr(policy, "current", real_current)
    accepted = await approval.authorize(authorization_request(context_for(AcceptingSession())))
    assert isinstance(accepted, approval.Grant)


@pytest.mark.anyio
async def test_cancelled_server_task_propagates_and_releases_the_confirmation_window(machine):
    waiting = asyncio.create_task(
        approval.authorize(authorization_request(context_for(HangingSession()))))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    following = await approval.authorize(authorization_request(context_for(AcceptingSession())))
    assert isinstance(following, approval.Grant)


@pytest.mark.anyio
async def test_two_identical_approvals_open_two_windows_with_two_permits(machine):
    callback = hermes_callback(["accept", "accept"])
    async with connected(build_server(), callback) as session:
        first = await call(session, "delete_elements", element_ids=[5])
        second = await call(session, "delete_elements", element_ids=[5])

    sent = posts(machine, "/delete_elements/")
    nonces = [json.loads(request.content.decode("utf-8"))["_mcp"]["permit"]["n"]
              for request in sent]
    assert "NOT sent" not in first + second
    assert len(callback.messages) == 2
    assert len(sent) == 2 and len(set(nonces)) == 2


@pytest.mark.anyio
async def test_concurrent_windows_are_serialized_and_have_unique_codes(machine):
    starts, ends, messages = [], [], []
    first_open = asyncio.Event()
    release_first = asyncio.Event()
    calls = 0

    async def callback(context, params):
        nonlocal calls
        calls += 1
        messages.append(params.message)
        starts.append(calls)
        if calls == 1:
            first_open.set()
            await release_first.wait()
        ends.append(calls)
        return types.ElicitResult(action="accept", content={})

    async with connected(build_server(), callback) as session:
        first = asyncio.create_task(call(session, "delete_elements", element_ids=[5]))
        await asyncio.wait_for(first_open.wait(), 1.0)
        second = asyncio.create_task(call(session, "delete_elements", element_ids=[6]))
        await asyncio.sleep(0.05)
        assert starts == [1]
        release_first.set()
        await asyncio.wait_for(asyncio.gather(first, second), 2.0)

    assert starts == [1, 2] and ends == [1, 2]
    assert messages[0].split("\n", 1)[0] != messages[1].split("\n", 1)[0]
    assert len(posts(machine, "/delete_elements/")) == 2


@pytest.mark.anyio
async def test_unknown_outcome_is_not_retried(machine):
    machine.faults[(PORT_A, PREFIX + "/delete_elements/")] = (
        lambda request: httpx.ReadTimeout("", request=request))
    callback = hermes_callback(["accept"])
    async with connected(build_server(), callback) as session:
        text = await call(session, "delete_elements", element_ids=[5])

    assert "outcome UNKNOWN" in text
    assert len(callback.messages) == 1
    assert len(posts(machine, "/delete_elements/")) == 1


@pytest.mark.anyio
async def test_allow_route_needs_no_window_and_can_be_delivered_twice(machine):
    callback = hermes_callback(["decline"])
    arguments = minimal_kwargs()["create_level"]
    async with connected(build_server(), callback) as session:
        await call(session, "create_level", **arguments)
        await call(session, "create_level", **arguments)

    assert callback.messages == []
    assert len(posts(machine, "/create_level/")) == 2
