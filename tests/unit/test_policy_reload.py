# -*- coding: utf-8 -*-
"""Phase 7 operator policy at run time (07-04 task 2): hot reload, last-valid retention, honest status.

The store is driven with an injected reader (a callable (path) -> bytes, or raising) and an
injected clock, so no share and no real time is involved; the end-to-end rows reuse the
tracer's fake machine and the Hermes-shaped elicitation callback. Needs no Revit.
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time

import pytest
from mcp.server.fastmcp import FastMCP

import approval
import audit
import bridge
import policy
import tools
from audit_support import PREFIX, SEL_A, make_machine, release_machine
from elicitation_support import connected, hermes_callback
from gate_support import TEST_SECRET

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OP_PATH = r"\\Сервер\Общая папка\operator_policy.toml"
UNC = r"\\Сервер\Общая папка\policy_source target.toml"

GOOD_A = b'schema = 1\n[settings]\nconfirm_timeout_s = 200\n'
GOOD_B = b'schema = 1\n[settings]\nconfirm_timeout_s = 210\n'
BAD = b'schema = 1\n[routes."/no_such_route/"]\ndecision = "allow"\n'


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


class Clock(object):
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Reader(object):
    """What the operator path holds, as a callable the store calls in a worker thread."""

    def __init__(self, content=None):
        self.content = content          # bytes, a callable (call_number) -> bytes, or an exception
        self.calls = 0
        self.release = threading.Event()

    def __call__(self, path):
        self.calls += 1
        content = self.content
        if callable(content):
            content = content(self.calls)
        if isinstance(content, BaseException):
            raise content
        return content


@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch):
    monkeypatch.delenv(policy.POLICY_FILE_ENV, raising=False)
    monkeypatch.setattr(policy, "_debounce_sleep", lambda seconds: None)
    policy._reset()
    yield
    policy._reset()


@pytest.fixture
def operator_env(monkeypatch):
    monkeypatch.setenv(policy.POLICY_FILE_ENV, OP_PATH)


def make_store(tmp_path, reader=None, clock=None, **kwargs):
    reader = reader if reader is not None else Reader(GOOD_A)
    clock = clock if clock is not None else Clock()
    return policy.PolicyStore(reader=reader, clock=clock, source_dir=str(tmp_path), **kwargs), reader, clock


STATUS_KEYS = {"source", "hash", "operator_file", "operator_state", "diagnostic", "blocked",
               "blocked_reason", "confirm_timeout_s", "permit_ttl_s"}


# ------------------------------------------------------------------- the states

@pytest.mark.anyio
async def test_without_env_or_policy_source_the_base_is_active_and_not_configured(tmp_path):
    store, reader, _ = make_store(tmp_path)
    active = await store.current()
    status = store.status()
    assert active.source == "base" and status["source"] == "base"
    assert status["operator_state"] == "not_configured" and status["operator_file"] is None
    assert set(status) == STATUS_KEYS and status["blocked"] is False
    assert reader.calls == 0


@pytest.mark.anyio
async def test_a_valid_operator_file_is_accepted_and_changes_the_hash(tmp_path, operator_env):
    store, _, _ = make_store(tmp_path)
    base_hash = policy.load_base().hash
    active = await store.current()
    status = store.status()
    assert active.source == "operator" and status["source"] == "operator"
    assert status["operator_state"] == "accepted" and status["diagnostic"] is None
    assert status["hash"] == active.hash != base_hash
    assert status["operator_file"] == OP_PATH
    assert (status["confirm_timeout_s"], status["permit_ttl_s"]) == (200, 60)
    assert active.hash == policy.policy_hash(
        open(os.path.join(REPO_ROOT, policy.BASE_FILE), "rb").read(), GOOD_A)


@pytest.mark.anyio
async def test_an_invalid_file_at_first_use_leaves_the_base_and_names_the_key_path(tmp_path, operator_env):
    store, _, _ = make_store(tmp_path, Reader(BAD))
    active = await store.current()
    status = store.status()
    assert active.source == "base" and active.hash == policy.load_base().hash
    assert status["operator_state"] == "rejected"
    assert "no_such_route" in status["diagnostic"]


@pytest.mark.anyio
async def test_empty_and_partial_files_are_rejected_not_applied(tmp_path, operator_env):
    for content in (b"", b'schema = 1\n[routes."/delete_el', b"\xff\xfe\x00"):
        store, _, _ = make_store(tmp_path, Reader(content))
        active = await store.current()
        assert active.source == "base" and store.status()["operator_state"] == "rejected"


@pytest.mark.anyio
async def test_valid_then_invalid_keeps_the_last_valid_operator_version(tmp_path, operator_env):
    store, reader, clock = make_store(tmp_path)
    first = await store.current()
    reader.content = BAD
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    second = await store.current()
    status = store.status()
    assert second is first and second.source == "operator"
    assert status["hash"] == first.hash and status["operator_state"] == "rejected"
    assert status["diagnostic"]


@pytest.mark.anyio
async def test_valid_then_deleted_falls_back_to_the_base_and_reports_absent(tmp_path, operator_env):
    store, reader, clock = make_store(tmp_path)
    await store.current()
    reader.content = FileNotFoundError(2, "gone")
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    active = await store.current()
    assert active.source == "base" and store.status()["operator_state"] == "absent"
    reader.content = GOOD_A  # back again: applied again
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    assert (await store.current()).source == "operator"


@pytest.mark.anyio
async def test_valid_then_an_unreadable_share_keeps_the_last_valid_policy(tmp_path, operator_env):
    store, reader, clock = make_store(tmp_path)
    first = await store.current()
    reader.content = OSError(5, "denied")
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    second = await store.current()
    status = store.status()
    assert second is first
    assert status["operator_state"] == "unreachable" and status["diagnostic"] == "OSError"


@pytest.mark.anyio
@pytest.mark.skipif(sys.platform != "win32", reason="WinError codes exist on Windows only")
async def test_a_missing_share_name_is_unreachable_not_absent(tmp_path, operator_env):
    store, reader, clock = make_store(tmp_path)
    first = await store.current()
    reader.content = OSError(2, "network name not found", None, 67)
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    second = await store.current()
    assert second is first and store.status()["operator_state"] == "unreachable"


@pytest.mark.anyio
async def test_a_share_that_hangs_returns_the_last_valid_policy_while_the_loop_keeps_running(
        tmp_path, operator_env):
    reader = Reader(GOOD_A)
    store, _, clock = make_store(tmp_path, reader)
    first = await store.current()
    release = reader.release

    def hang(call):
        release.wait(10)
        return GOOD_B

    reader.content = hang
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    ticks = []

    async def counter():
        while True:
            ticks.append(1)
            await asyncio.sleep(0.05)

    task = asyncio.ensure_future(counter())
    started = time.monotonic()
    try:
        second = await store.current(force=True)
    finally:
        elapsed = time.monotonic() - started
        task.cancel()
        release.set()  # let the worker thread finish so the loop can close
    assert elapsed < 4.0
    assert second is first and store.status()["operator_state"] == "unreachable"
    assert len(ticks) >= 10  # the loop ran during the 3 s wait


@pytest.mark.anyio
async def test_two_reads_with_different_bytes_are_not_applied_and_the_state_is_pending(
        tmp_path, operator_env):
    store, reader, clock = make_store(tmp_path)
    first = await store.current()
    reader.content = lambda call: GOOD_B if call % 2 else BAD  # torn: the two reads differ
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    second = await store.current()
    assert second is first and store.status()["operator_state"] == "pending"


@pytest.mark.anyio
async def test_the_debounce_waits_between_the_two_reads(tmp_path, operator_env, monkeypatch):
    waited = []
    monkeypatch.setattr(policy, "_debounce_sleep", waited.append)
    store, reader, _ = make_store(tmp_path)
    await store.current()
    assert waited == [policy.DEBOUNCE_S] and reader.calls == 2


@pytest.mark.anyio
async def test_calls_inside_the_interval_do_not_read_again_and_force_does(tmp_path, operator_env):
    store, reader, clock = make_store(tmp_path)
    await store.current()
    after_first = reader.calls
    await store.current()
    clock.advance(policy.RELOAD_INTERVAL_S - 0.5)
    await store.current()
    assert reader.calls == after_first
    await store.current(force=True)
    assert reader.calls == after_first * 2
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    await store.current()
    assert reader.calls == after_first * 3


@pytest.mark.anyio
async def test_an_unchanged_file_keeps_the_same_policy_object(tmp_path, operator_env):
    store, _, clock = make_store(tmp_path)
    first = await store.current()
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    assert await store.current() is first
    assert store.status()["operator_state"] == "accepted"


@pytest.mark.anyio
async def test_an_oversized_operator_file_is_rejected(tmp_path, operator_env):
    store, _, _ = make_store(tmp_path, Reader(b"#" * (policy.MAX_OPERATOR_BYTES + 1)))
    active = await store.current()
    assert active.source == "base" and store.status()["operator_state"] == "rejected"


# ---------------------------------------------------------------- the invalid base

def broken_base(tmp_path):
    path = tmp_path / "policy.base.toml"
    path.write_bytes(b"schema = 2\n")
    return str(path)


@pytest.mark.anyio
async def test_an_invalid_base_raises_on_every_call_and_the_status_says_blocked(tmp_path):
    store, _, _ = make_store(tmp_path, base_path=broken_base(tmp_path))
    for _ in range(2):
        with pytest.raises(policy.PolicyError):
            await store.current()
    status = store.status()
    assert status["blocked"] is True and "schema" in status["blocked_reason"]
    assert status["source"] is None and status["hash"] is None
    assert set(status) == STATUS_KEYS


@pytest.mark.anyio
async def test_a_repaired_base_is_picked_up_without_a_restart(tmp_path):
    path = broken_base(tmp_path)
    store, _, _ = make_store(tmp_path, base_path=path)
    with pytest.raises(policy.PolicyError):
        await store.current()
    with open(os.path.join(REPO_ROOT, policy.BASE_FILE), "rb") as good:
        data = good.read()
    with open(path, "wb") as handle:
        handle.write(data)
    assert (await store.current()).source == "base" and store.status()["blocked"] is False


@pytest.mark.anyio
async def test_the_module_status_never_raises_and_reports_blocked(tmp_path, monkeypatch):
    store, _, _ = make_store(tmp_path, base_path=broken_base(tmp_path))
    monkeypatch.setattr(policy, "_STORE", store)
    status = await policy.status()
    assert status["blocked"] is True
    with pytest.raises(policy.PolicyError):
        await policy.current()


@pytest.fixture
def machine(monkeypatch):
    fake = make_machine(monkeypatch)
    monkeypatch.setattr(bridge, "_secret_cache", TEST_SECRET)
    monkeypatch.setattr(bridge, "_authorize", approval.authorize)
    yield fake
    release_machine()


def posts_to(machine, route):
    return [r for r in machine.requests
            if r.method == "POST" and r.url.path == PREFIX + route]


@pytest.mark.anyio
async def test_an_invalid_base_refuses_every_gated_route_and_sends_nothing(tmp_path, monkeypatch, machine):
    store, _, _ = make_store(tmp_path, base_path=broken_base(tmp_path))
    monkeypatch.setattr(policy, "_STORE", store)

    refusal = await approval.authorize(approval.AuthorizationRequest(
        route="/create_level/", endpoint="/create_level/", data={}, ctx=None, target={},
        call=None, secret=TEST_SECRET, read_post=None, timeout=1.0))
    assert isinstance(refusal, approval.Refusal) and refusal.reasons == ("policy_invalid",)
    assert "NOT sent" in refusal.text

    text = await bridge.revit_post("/create_level/", {"levels": []}, None, target=SEL_A)
    assert "NOT sent" in text and "policy_invalid" in text
    assert posts_to(machine, "/create_level/") == []


# ------------------------------------------------------------------ concurrency

@pytest.mark.anyio
async def test_twenty_callers_during_a_reload_see_the_old_or_the_new_object_only(tmp_path, operator_env):
    store, reader, clock = make_store(tmp_path)
    old = await store.current()
    reader.content = GOOD_B
    clock.advance(policy.RELOAD_INTERVAL_S + 0.1)
    results = await asyncio.gather(*[store.current() for _ in range(20)])
    new = await store.current()
    assert new is not old and new.confirm_timeout_s == 210
    assert all(item is old or item is new for item in results)


# --------------------------------------------------------------- operator_path

def test_operator_path_reads_the_first_line_of_policy_source_byte_identical(tmp_path):
    (tmp_path / policy.POLICY_SOURCE_FILE).write_bytes((UNC + "\n").encode("utf-8"))
    assert policy.operator_path(str(tmp_path)) == UNC


def test_operator_path_tolerates_a_bom_crlf_and_a_second_line(tmp_path):
    (tmp_path / policy.POLICY_SOURCE_FILE).write_bytes(
        b"\xef\xbb\xbf" + UNC.encode("utf-8") + b"\r\nignored\r\n")
    assert policy.operator_path(str(tmp_path)) == UNC


def test_an_env_value_wins_over_policy_source_and_an_empty_one_is_ignored(tmp_path, monkeypatch):
    (tmp_path / policy.POLICY_SOURCE_FILE).write_bytes((UNC + "\n").encode("utf-8"))
    monkeypatch.setenv(policy.POLICY_FILE_ENV, OP_PATH)
    assert policy.operator_path(str(tmp_path)) == OP_PATH
    monkeypatch.setenv(policy.POLICY_FILE_ENV, "")
    assert policy.operator_path(str(tmp_path)) == UNC
    monkeypatch.setenv(policy.POLICY_FILE_ENV, "   ")
    assert policy.operator_path(str(tmp_path)) == UNC


def test_without_env_or_a_usable_policy_source_there_is_no_operator_path(tmp_path):
    assert policy.operator_path(str(tmp_path)) is None
    (tmp_path / policy.POLICY_SOURCE_FILE).write_bytes(b"\n")
    assert policy.operator_path(str(tmp_path)) is None


@pytest.mark.anyio
async def test_the_store_uses_the_staged_policy_source_when_there_is_no_env(tmp_path):
    (tmp_path / policy.POLICY_SOURCE_FILE).write_bytes((UNC + "\n").encode("utf-8"))
    seen = []

    def reader(path):
        seen.append(path)
        return GOOD_A

    store, _, _ = make_store(tmp_path, reader)
    assert (await store.current()).source == "operator"
    assert set(seen) == {UNC}


# ------------------------------------------------------------- never at import

def test_importing_policy_reads_nothing_and_creates_no_store():
    code = "import policy; print(policy._STORE)"
    env = dict(os.environ, REVIT_MCP_POLICY_FILE=r"\\no-such-server\share\file.toml")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip() == "None", out.stderr


# ------------------------------------------------- policy change during a window

def build_server():
    mcp = FastMCP("reload")
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
async def test_a_policy_change_while_the_window_is_open_voids_the_accept(
        tmp_path, operator_env, monkeypatch, machine):
    store, reader, clock = make_store(tmp_path)
    monkeypatch.setattr(policy, "_STORE", store)
    await store.current()
    inner = hermes_callback(["accept"])

    async def callback(context, params):
        reader.content = GOOD_B           # an operator edit lands while the human decides
        clock.advance(policy.RELOAD_INTERVAL_S + 1)
        return await inner(context, params)

    async with connected(build_server(), callback) as session:
        text = await call(session, "delete_elements", element_ids=[101])

    assert len(inner.messages) == 1
    assert "NOT sent" in text and "policy changed" in text
    assert posts_to(machine, "/delete_elements/") == []


@pytest.mark.anyio
async def test_without_a_change_the_accept_is_sent_and_the_permit_carries_the_active_hash(
        tmp_path, operator_env, monkeypatch, machine):
    store, _, _ = make_store(tmp_path)
    monkeypatch.setattr(policy, "_STORE", store)
    active = await store.current()

    async with connected(build_server(), hermes_callback(["accept"])) as session:
        text = await call(session, "delete_elements", element_ids=[101])

    assert "NOT sent" not in text
    sent = posts_to(machine, "/delete_elements/")
    assert len(sent) == 1
    envelope = json.loads(sent[0].content.decode("ascii"))["_mcp"]
    assert envelope["permit"]["p"] == active.hash


def test_refusal_text_for_policy_changed_says_ask_again():
    text = approval.refusal_text("denied", ["policy_changed"])
    assert "NOT sent" in text and "policy changed while the window was open" in text
    assert "ask again" in text
