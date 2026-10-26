# -*- coding: utf-8 -*-
"""Phase 7 policy-decision fields in the durable audit log."""

import json

import pytest
from mcp.server.fastmcp import FastMCP

import approval
import audit
import bridge
import tools
from audit_support import PREFIX, PORT_A, SEL_A, make_machine, read_entries, release_machine
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
    mcp = FastMCP("phase7-audit")
    audit.install_audited_tools(mcp)
    tools.register_tools(mcp, bridge.revit_get, bridge.revit_post, bridge.revit_image)
    assert tools.FAILED == {}
    return mcp


async def call(session, name, **arguments):
    arguments.setdefault("target", SEL_A)
    result = await session.call_tool(name, arguments)
    assert not result.isError, result
    return "".join(part.text for part in result.content)


def only_entry():
    entries = read_entries()
    assert len(entries) == 1
    return entries[0]


@pytest.mark.anyio
async def test_decline_writes_one_not_sent_decision_entry_and_attaches_its_id(machine):
    async with connected(build_server(), hermes_callback(["decline"])) as session:
        text = await call(session, "delete_elements", element_ids=[5])

    entry = only_entry()
    assert entry["kind"] == "not-sent" and entry["outcome"] == "denied"
    assert entry["reason"] == "approval_declined"
    assert entry["decision"] == "confirm" and entry["approval"] == "declined"
    assert entry["reasons"] == ["delete", "approval_declined"]
    assert entry["policy"]["source"] == "base" and len(entry["policy"]["hash"]) == 12
    assert entry["method"] == "POST" and entry["route"] == "/delete_elements/"
    assert entry["http_status"] is None and entry["mutation"] is True
    assert text.rstrip().endswith("Audit: call_id {}".format(entry["call_id"]))
    assert set(audit.ALWAYS_PRESENT_FIELDS) <= set(entry)
    assert set(entry) <= set(audit.SCHEMA_1_FIELDS)


@pytest.mark.anyio
async def test_accepted_call_carries_policy_and_permit_prefix(machine):
    machine.reply(PORT_A, "/delete_elements/", 200, {
        "status": "success",
        "outcome": {"transaction_status": "Committed", "requested": 1,
                    "succeeded": [5], "failed": [], "revit_failures": []},
    })
    async with connected(build_server(), hermes_callback(["accept"])) as session:
        await call(session, "delete_elements", element_ids=[5])

    entry = only_entry()
    request = next(request for request in machine.requests
                   if request.url.path == PREFIX + "/delete_elements/")
    nonce = json.loads(request.content.decode("utf-8"))["_mcp"]["permit"]["n"]
    assert entry["outcome"] == "success"
    assert entry["decision"] == "confirm" and entry["approval"] == "accepted"
    assert entry["permit"] == nonce[:8]
    assert isinstance(entry["approval_wait_ms"], int) and entry["approval_wait_ms"] >= 0


@pytest.mark.anyio
async def test_revit_permit_rejection_has_a_distinct_outcome(machine):
    machine.reply(PORT_A, "/create_level/", 403,
                  {"error": "permit rejected", "permit": "replayed", "hint": "retry"})
    result = await bridge.revit_post("/create_level/", minimal_kwargs()["create_level"],
                                     target=SEL_A)

    assert "403" in result
    entry = only_entry()
    assert entry["outcome"] == "rejected_permit" and entry["reason"] == "replayed"
    assert entry["decision"] == "allow" and entry["approval"] == "none"


@pytest.mark.anyio
async def test_rolled_back_reply_keeps_revit_outcome_not_approval(machine):
    machine.reply(PORT_A, "/delete_elements/", 409, {
        "status": "rolled_back",
        "outcome": {"transaction_status": "RolledBack", "requested": 1,
                    "succeeded": [], "failed": [], "revit_failures": []},
    })
    async with connected(build_server(), hermes_callback(["accept"])) as session:
        await call(session, "delete_elements", element_ids=[5])

    entry = only_entry()
    assert entry["outcome"] == "rolled_back" and entry["approval"] == "accepted"


@pytest.mark.anyio
async def test_secret_never_reaches_decision_or_permitted_audit_entry(machine):
    async with connected(build_server(), hermes_callback(["decline"])) as session:
        await call(session, "delete_elements", element_ids=[5])

    assert TEST_SECRET not in json.dumps(only_entry(), ensure_ascii=False)
