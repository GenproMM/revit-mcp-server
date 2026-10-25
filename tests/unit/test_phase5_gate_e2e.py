# -*- coding: utf-8 -*-
"""revit_post through a MockTransport into the real Phase 5 gate. Needs no Revit.

The production bridge path (revit_post -> _dispatch -> _send) puts the loaded secret
under the reserved ``_mcp`` key of every POST body. The MockTransport handler plays
pyRevit's side: it wraps the bytes it received in a request double, runs the real
security.gate_or_response on them and answers the body the route would have parsed.
The incarnation proof is fixed (the same harness shape as test_bridge_serialization).
"""

import json
import os
import subprocess
import sys
import types
import uuid

import httpx
import pytest

import bridge
from gate_support import TEST_SECRET, configure_gate
from revit_mcp import security
from tools.utils import format_response

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WRONG_SECRET = "phase5-wrong-secret-9876543210-zyxwvuABC"

TOKEN = "11111111-1111-4111-8111-111111111111"
TARGET = {"host": "127.0.0.1", "port": 48884, "pid": 4242, "session_token": TOKEN}

DATA = {"levels": [{"name": "L1", "elevation": 3000.0}], "document": "Проект.rvt"}


@pytest.fixture(scope="module")
def anyio_backend():
    # trio is not installed and must not be added: pin asyncio.
    return "asyncio"


class _IronPython3Json(object):
    """json as IronPython 3 ships it: loads() refuses bytes (see test_textutils)."""

    def loads(self, payload, *args, **kwargs):
        if not isinstance(payload, str):
            raise TypeError(
                "the JSON object must be str, not {!r}".format(payload.__class__.__name__))
        return json.loads(payload, *args, **kwargs)


@pytest.fixture(autouse=True)
def _harness(monkeypatch):
    bridge._states.clear()

    async def only_process():
        return dict(TARGET)

    async def proven(target, state, timeout):
        state.verified = True
        return None

    def make_response(data=None, status=200, headers=None):
        return types.SimpleNamespace(status=status, data=data)

    monkeypatch.setattr(bridge, "resolve_default_target", only_process)
    monkeypatch.setattr(bridge, "_verify_target", proven)
    monkeypatch.setattr(bridge, "listener_snapshot",
                        lambda ports, **kwargs: {TARGET["port"]: [TARGET["pid"]]})
    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=types.SimpleNamespace(make_response=make_response)))
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())
    configure_gate(monkeypatch)
    yield
    bridge._states.clear()


def _handler(seen):
    """pyRevit's side: the real gate on the received bytes, then the route's own parse."""

    def handler(request):
        seen.append(request)
        if request.method != "POST":
            return httpx.Response(200, json={"status": "success", "body": request.content.decode()})
        double = types.SimpleNamespace(data=request.content)
        refusal = security.gate_or_response(double)
        if refusal is not None:
            return httpx.Response(refusal.status, json=refusal.data)
        return httpx.Response(200, json={"status": "success", "received": json.loads(double.data)})

    return handler


def _install(seen):
    bridge._state_for(TARGET).client = httpx.AsyncClient(
        base_url="http://test:1/genpro_revit_mcp/",
        transport=httpx.MockTransport(_handler(seen)),
        trust_env=False,
    )


def _posts(seen):
    return [r for r in seen if r.method == "POST"]


@pytest.mark.anyio
async def test_revit_post_sends_the_loaded_secret_and_the_handler_sees_the_tool_data(monkeypatch):
    monkeypatch.setattr(bridge, "_secret_cache", TEST_SECRET)
    seen = []
    _install(seen)
    result = await bridge.revit_post("/create_level/", DATA)
    assert isinstance(result, dict)
    assert result["received"] == DATA
    assert "_mcp" not in result["received"]
    posts = _posts(seen)
    assert len(posts) == 1
    assert posts[0].headers["content-type"] == "text/plain; charset=utf-8"
    envelope = json.loads(posts[0].content)["_mcp"]
    # Phase 6 (D-06): the call_id rides beside the secret; the real gate above accepted it.
    assert set(envelope) == {"secret", "call_id"}
    assert envelope["secret"] == TEST_SECRET
    assert uuid.UUID(envelope["call_id"]).version == 4


@pytest.mark.anyio
async def test_revit_post_without_a_secret_is_a_visible_401_missing(monkeypatch):
    monkeypatch.setattr(bridge, "_secret_cache", None)
    seen = []
    _install(seen)
    result = await bridge.revit_post("/create_level/", DATA)
    assert isinstance(result, str)
    assert result.startswith("Error: 401 - ")
    assert "missing" in result
    assert format_response(result) == result
    assert TEST_SECRET not in result
    assert "_mcp" not in json.loads(_posts(seen)[0].content)


@pytest.mark.anyio
async def test_revit_post_with_a_wrong_secret_is_a_visible_401_mismatch(monkeypatch):
    monkeypatch.setattr(bridge, "_secret_cache", WRONG_SECRET)
    seen = []
    _install(seen)
    result = await bridge.revit_post("/create_level/", DATA)
    assert isinstance(result, str)
    assert result.startswith("Error: 401 - ")
    assert "mismatch" in result
    assert format_response(result) == result
    assert TEST_SECRET not in result
    assert WRONG_SECRET not in result


@pytest.mark.anyio
@pytest.mark.parametrize("body", [
    {"_mcp": {"secret": "forged-by-the-model"}, "levels": []},
    ["not", "an", "object"],
    "just text",
], ids=["forged-envelope", "list", "text"])
async def test_a_forged_or_non_object_body_is_refused_before_anything_is_sent(monkeypatch, body):
    monkeypatch.setattr(bridge, "_secret_cache", TEST_SECRET)
    seen = []
    _install(seen)
    result = await bridge.revit_post("/create_level/", body)
    assert isinstance(result, str)
    assert "NOT sent" in result
    assert "outcome is UNKNOWN" not in result
    assert "forged-by-the-model" not in result
    assert TEST_SECRET not in result
    assert _posts(seen) == []
    meta = getattr(result, bridge.PROVENANCE_ATTR)
    assert meta["kind"] == "not-sent"


@pytest.mark.anyio
async def test_revit_get_sends_no_body(monkeypatch):
    monkeypatch.setattr(bridge, "_secret_cache", TEST_SECRET)
    seen = []
    _install(seen)
    result = await bridge.revit_get("/model_info/")
    assert isinstance(result, dict)
    assert result["body"] == ""
    gets = [r for r in seen if r.method == "GET"]
    assert len(gets) == 1
    assert gets[0].content == b""
    assert TEST_SECRET not in gets[0].url.query.decode()


@pytest.mark.anyio
async def test_a_none_body_is_sent_as_an_empty_object_with_the_envelope(monkeypatch):
    monkeypatch.setattr(bridge, "_secret_cache", TEST_SECRET)
    seen = []
    _install(seen)
    result = await bridge.revit_post("/create_level/", None)
    assert result["received"] == {}
    sent = json.loads(_posts(seen)[0].content)
    assert set(sent) == {"_mcp"}
    assert sent["_mcp"]["secret"] == TEST_SECRET
    assert uuid.UUID(sent["_mcp"]["call_id"]).version == 4


def test_secret_is_loaded_lazily_once_and_memoized_none_included(monkeypatch):
    calls = []

    def fake_load(search_dirs=None):
        calls.append(search_dirs)
        return TEST_SECRET if len(calls) == 1 else None

    monkeypatch.setattr(bridge, "load_secret", fake_load)
    monkeypatch.setattr(bridge, "_secret_cache", bridge._SECRET_UNSET)
    assert calls == []
    assert bridge._secret() == TEST_SECRET
    assert bridge._secret() == TEST_SECRET
    assert len(calls) == 1
    bridge.reset_secret_cache()
    assert bridge._secret() is None  # the second load answers None
    assert bridge._secret() is None  # and None is memoized too
    assert len(calls) == 2


def test_importing_bridge_never_loads_the_secret():
    code = (
        "import bridge\n"
        "assert bridge._secret_cache is bridge._SECRET_UNSET\n"
        "print('LAZY_OK')\n"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "LAZY_OK" in done.stdout


def test_no_unit_test_reads_the_developers_secret_file():
    # tests/unit/conftest.py pins the cache to None; this test does not set it.
    assert bridge._secret_cache is None
    assert bridge._secret() is None
