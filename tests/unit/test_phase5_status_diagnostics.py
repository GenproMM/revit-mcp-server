# -*- coding: utf-8 -*-
"""Phase 5 /status/ diagnostics (D-08, SEC-07, INTG-05, INTG-07) end to end through status.py and get_revit_status. Needs no Revit."""

import asyncio
import importlib
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


# --------------------------------------------------------------- bind (Task 2)


@pytest.mark.parametrize("listeners, expected", [
    (_LOOPBACK, "loopback_only"),
    (_EXPOSED, "exposed"),
    ([("127.0.0.1", 50000)], "unknown"),
    (None, "unknown"),
])
def test_bind_comes_from_the_listener_table(monkeypatch, listeners, expected):
    code, payload = _status(monkeypatch, listeners=listeners)
    assert code == 200
    assert payload["bind"] == expected


def test_status_block_with_listener_callable_variants(monkeypatch):
    _, security = load_status(monkeypatch)

    def boom():
        raise RuntimeError("no table")

    assert security.status_block(48884, lambda: [("127.0.0.1", 48884)])["bind"] == "loopback_only"
    assert security.status_block(48884, lambda: [("0.0.0.0", 48884)])["bind"] == "exposed"
    assert security.status_block(48884, boom)["bind"] == "unknown"
    assert security.status_block(48884, lambda: None)["bind"] == "unknown"
    assert security.status_block(48884, lambda: [("127.0.0.1", 1)])["bind"] == "unknown"


def test_status_block_uninitialized_state_reports_unverifiable_read_error(monkeypatch):
    _, security = load_status(monkeypatch)
    monkeypatch.setattr(security, "_STATE", None)
    block = security.status_block(48884, lambda: _LOOPBACK)
    assert block["secret"] == {"configured": False, "fingerprint": None}
    assert block["integrity"]["state"] == "unverifiable"
    assert block["integrity"]["reason"] == trust.REASON_READ_ERROR


def test_dotnet_listeners_adapter_gives_none_without_the_clr(monkeypatch):
    _, security = load_status(monkeypatch)
    monkeypatch.undo()
    # Under CPython System.Net is absent: the adapter must swallow that into None.
    assert security._dotnet_listeners() is None


# ------------------------------------------------------------ security_alerts


_MISMATCH = {"state": "verified_mismatch", "reason": None,
             "modified": ["revit_mcp/detail.py"], "missing": [],
             "unexpected": ["revit_mcp/_zz_probe.py"]}


def test_alert_for_verified_mismatch_names_files_and_423():
    block = {"secret": {"configured": True, "fingerprint": "abcdef12"},
             "integrity": _MISMATCH, "bind": "loopback_only"}
    alerts = trust.security_alerts(block)
    assert len(alerts) == 1
    assert "revit_mcp/detail.py" in alerts[0]
    assert "revit_mcp/_zz_probe.py" in alerts[0]
    assert "423" in alerts[0]


def test_alert_for_exposed_bind_says_mutations_are_not_blocked():
    block = {"secret": {"configured": True, "fingerprint": "abcdef12"},
             "integrity": trust.unverifiable(trust.REASON_MANIFEST_MISSING), "bind": "exposed"}
    alerts = trust.security_alerts(block)
    assert len(alerts) == 1
    assert "not blocked" in alerts[0]


def test_alert_for_missing_secret_names_401():
    block = {"secret": {"configured": False, "fingerprint": None},
             "integrity": trust.unverifiable(trust.REASON_MANIFEST_MISSING), "bind": "loopback_only"}
    alerts = trust.security_alerts(block)
    assert len(alerts) == 1
    assert "401" in alerts[0]


@pytest.mark.parametrize("reason", [trust.REASON_MANIFEST_MISSING, trust.REASON_READ_ERROR,
                                    trust.REASON_ABSENCE_UNCONFIRMED])
def test_unverifiable_integrity_never_alerts(reason):
    block = {"secret": {"configured": True, "fingerprint": "abcdef12"},
             "integrity": trust.unverifiable(reason), "bind": "loopback_only"}
    assert trust.security_alerts(block) == []


@pytest.mark.parametrize("block", [None, "x", 7, {}, {"secret": 3, "integrity": [], "bind": None},
                                   {"integrity": {"state": "verified_mismatch", "modified": 5}}])
def test_malformed_block_gives_no_alert_and_never_raises(block):
    assert isinstance(trust.security_alerts(block), list)


# ------------------------------------------------------------ health rule (200)


def test_health_healthy_for_unverifiable_with_secret_and_loopback(monkeypatch):
    code, payload = _status(monkeypatch)
    assert code == 200
    assert payload["health"] == "healthy"
    assert "security_alerts" not in payload
    assert "error" not in payload


@pytest.mark.parametrize("kwargs", [
    {"integrity": _MISMATCH},
    {"listeners": _EXPOSED},
    {"secret": None},
])
def test_health_degraded_for_each_alerting_state(monkeypatch, kwargs):
    code, payload = _status(monkeypatch, **kwargs)
    assert code == 200
    assert payload["health"] == "degraded"
    assert payload["security_alerts"]
    assert "error" not in payload


def test_verified_match_is_healthy(monkeypatch):
    matched = {"state": "verified_match", "reason": None,
               "modified": [], "missing": [], "unexpected": []}
    code, payload = _status(monkeypatch, integrity=matched)
    assert code == 200
    assert payload["integrity"]["state"] == "verified_match"
    assert payload["health"] == "healthy"


# ------------------------------------------------------------------ 503 branch


def test_503_carries_block_health_and_keeps_error(monkeypatch):
    code, payload = _status(monkeypatch, has_doc=False)
    assert code == 503
    assert payload["error"] == "No active Revit document"
    assert payload["secret"]["configured"] is True
    assert payload["integrity"]["state"] == "unverifiable"
    assert payload["bind"] == "loopback_only"
    assert payload["health"] == "healthy"
    assert "security_alerts" not in payload


def test_503_degraded_with_alerts(monkeypatch):
    code, payload = _status(monkeypatch, has_doc=False, secret=None, listeners=_EXPOSED)
    assert code == 503
    assert payload["health"] == "degraded"
    assert len(payload["security_alerts"]) == 2
    assert payload["error"] == "No active Revit document"
    assert TEST_SECRET not in repr(payload)


@pytest.mark.parametrize("has_doc", [True, False])
def test_status_still_answers_without_the_security_module(monkeypatch, has_doc):
    code, payload = _status(monkeypatch, has_doc=has_doc, security_missing=True)
    assert code == (200 if has_doc else 503)
    for key in ("secret", "integrity", "bind", "security_alerts"):
        assert key not in payload
    assert payload["api_name"] == "genpro_revit_mcp"


def test_status_keeps_its_signature_and_never_touches_uiapp():
    source = (ROOT / "revit_mcp" / "status.py").read_text(encoding="utf-8")
    assert "def revit_status(verbose=None):" in source
    assert "uiapp" not in source


# ------------------------------------------------------------------ D-07 hints


def test_hint_wording_names_the_d07_actions():
    missing = trust.auth_failure("missing")[0]["hint"]
    assert "Update RevitMCP" in missing and "assistant session" in missing
    mismatch = trust.auth_failure("mismatch")[0]["hint"]
    assert "same build" in mismatch and "get_revit_status" in mismatch
    unconfigured = trust.auth_failure("server_not_configured")[0]["hint"]
    assert "restart Revit" in unconfigured


def test_no_hint_contains_the_secret_or_a_fingerprint():
    fingerprint = trust.secret_fingerprint(TEST_SECRET)
    for reason in ("missing", "mismatch", "server_not_configured"):
        body = json.dumps(trust.auth_failure(reason)[0])
        assert TEST_SECRET not in body
        assert fingerprint not in body
        assert not re.search(r"\b[0-9a-f]{8}\b", body)


# ------------------------------------------------- end to end comparison + leaks


def test_end_to_end_leak_scan_across_payload_and_tool_text(monkeypatch):
    code, payload = _status(monkeypatch, secret=None, listeners=_EXPOSED, integrity=_MISMATCH)
    text = _tool_text(_get_with(payload, lambda: trust.secret_fingerprint(TEST_SECRET)))
    assert TEST_SECRET not in repr(payload)
    assert TEST_SECRET not in text
    assert all(TEST_SECRET not in alert for alert in payload["security_alerts"])


def test_end_to_end_comparison_lines_through_status_and_tool(monkeypatch):
    fingerprint = trust.secret_fingerprint(TEST_SECRET)
    _, payload = _status(monkeypatch)
    differ = _tool_text(_get_with(payload, lambda: "00000000"))
    assert "DIFFER" in differ and fingerprint in differ and "00000000" in differ
    none_local = _tool_text(_get_with(payload, lambda: None))
    assert "this MCP server loaded none" in none_local
    _, payload = _status(monkeypatch, secret=None, has_doc=False)
    extension_none = _tool_text(_get_with(payload, lambda: fingerprint))
    assert "extension has none" in extension_none
    assert TEST_SECRET not in extension_none
