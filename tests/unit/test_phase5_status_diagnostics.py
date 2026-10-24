# -*- coding: utf-8 -*-
"""Phase 5 /status/ diagnostics (D-08, SEC-07, INTG-05, INTG-07) end to end through status.py and get_revit_status. Needs no Revit."""

import asyncio
import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

from gate_support import TEST_SECRET
from revit_mcp import trust
from tools.status_tools import register_status_tools

ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = "phase5_status_diag_pkg"
_LOOPBACK = [("127.0.0.1", 48884)]
_EXPOSED = [("0.0.0.0", 48884)]


class _FakeMCP(object):
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


def _purge():
    for name in [n for n in sys.modules if n == _PACKAGE or n.startswith(_PACKAGE + ".")]:
        del sys.modules[name]


@pytest.fixture(autouse=True)
def _clean_modules():
    _purge()
    yield
    _purge()


def load_status(monkeypatch, secret=TEST_SECRET, integrity=None, listeners=_LOOPBACK,
                has_doc=True, security_missing=False, identity_failure=False):
    """Load revit_mcp/status.py under a synthetic package; security, trust, integrity and textutils are the real files.

    Returns (handler, security_module). ``listeners`` replaces the .NET adapter so
    CPython never needs System.Net; None makes the adapter report nothing.
    """
    package = types.ModuleType(_PACKAGE)
    package.__path__ = [str(ROOT / "revit_mcp")]
    monkeypatch.setitem(sys.modules, _PACKAGE, package)
    monkeypatch.setitem(sys.modules, _PACKAGE + ".utils", types.SimpleNamespace(sanitize_string=str))

    def get_identity(version):
        if identity_failure:
            raise RuntimeError("startup identity missing")
        return {"pid": 1, "actual_port": 48884, "session_token": "t", "revit_version": version}

    monkeypatch.setitem(sys.modules, _PACKAGE + ".identity",
                        types.SimpleNamespace(get_process_identity=get_identity))
    monkeypatch.setitem(sys.modules, _PACKAGE + ".registry", types.SimpleNamespace(
        snapshot=lambda verbose=False: {"registered_domains": 23}, is_degraded=lambda: False))
    routes = types.SimpleNamespace(make_response=lambda data, status=200: (status, data))
    doc = types.SimpleNamespace(Title="Model") if has_doc else None
    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=routes, revit=types.SimpleNamespace(doc=doc),
        HOST_APP=types.SimpleNamespace(app=types.SimpleNamespace(VersionNumber="2024"))))

    security = None
    if security_missing:
        monkeypatch.setitem(sys.modules, _PACKAGE + ".security", None)
    else:
        import importlib

        security = importlib.import_module(_PACKAGE + ".security")
        if integrity is None:
            integrity = trust.unverifiable(trust.REASON_MANIFEST_MISSING)
        monkeypatch.setattr(security, "_STATE", {"secret": secret, "integrity": integrity})
        if listeners is None:
            monkeypatch.setattr(security, "_dotnet_listeners", lambda: None)
        else:
            monkeypatch.setattr(security, "_dotnet_listeners", lambda: list(listeners))

    spec = importlib.util.spec_from_file_location(_PACKAGE + ".status", ROOT / "revit_mcp/status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handlers = {}

    def route(path, methods):
        def capture(fn):
            handlers[path] = fn
            return fn

        return capture

    module.register_status_routes(types.SimpleNamespace(name="genpro_revit_mcp", route=route))
    return handlers["/status/"], security


def _status(monkeypatch, **kwargs):
    handler, _ = load_status(monkeypatch, **kwargs)
    return handler()


def _get_with(response, fingerprint="__absent__"):
    async def fake_get(endpoint, ctx=None, timeout=30.0):
        return response

    if fingerprint != "__absent__":
        fake_get.secret_fingerprint = fingerprint
    return fake_get


def _tool_text(fake_get):
    mcp = _FakeMCP()
    register_status_tools(mcp, fake_get)
    return asyncio.run(mcp.tools["get_revit_status"](None))


# ----------------------------------------------------------------- tracer (Task 1)


def test_tracer_secret_becomes_fingerprint_and_comparison_line(monkeypatch):
    code, payload = _status(monkeypatch)
    assert code == 200
    fingerprint = trust.secret_fingerprint(TEST_SECRET)
    assert payload["secret"] == {"configured": True, "fingerprint": fingerprint}
    assert re.fullmatch(r"[0-9a-f]{8}", fingerprint)
    assert payload["integrity"]["state"] == "unverifiable"
    assert TEST_SECRET not in repr(payload)

    text = _tool_text(_get_with(payload, lambda: trust.secret_fingerprint(TEST_SECRET)))
    assert "both halves hold the same secret" in text
    assert fingerprint in text
    assert TEST_SECRET not in text
