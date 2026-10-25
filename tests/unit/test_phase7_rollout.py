# -*- coding: utf-8 -*-
"""Phase 7 rollout signals: old extension tolerance and current status diagnostics. Needs no Revit."""

import asyncio
import importlib
import json
import os
import shutil
import subprocess
import sys
import types

import pytest

import permit
from gate_support import TEST_ROUTE, TEST_SECRET, TEST_SESSION_TOKEN, configure_gate, enveloped_body
from revit_mcp import permits, security
from tools.status_tools import register_status_tools

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRE_PHASE7_REV = "781a548"


class _MCP(object):
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorate(function):
            self.tools[function.__name__] = function
            return function
        return decorate


def _response(data=None, status=200, headers=None):
    return types.SimpleNamespace(data=data, status=status)


@pytest.fixture
def fake_pyrevit(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=types.SimpleNamespace(make_response=_response)))


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")
def test_pre_phase7_gate_strips_a_permit_envelope_from_the_old_extension(tmp_path, monkeypatch):
    shown = {}
    needed = ("security.py", "trust.py", "textutils.py", "integrity.py")
    for name in needed:
        result = subprocess.run(
            ["git", "-C", REPO_ROOT, "show", "{}:revit_mcp/{}".format(PRE_PHASE7_REV, name)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            pytest.skip("revision {} is not in this clone".format(PRE_PHASE7_REV))
        shown[name] = result.stdout

    package_name = "old_revit_mcp_781a548"
    package = tmp_path / package_name
    package.mkdir()
    (package / "__init__.py").write_bytes(b"# -*- coding: utf-8 -*-\n")
    for name, source in shown.items():
        (package / name).write_bytes(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    old_security = importlib.import_module(package_name + ".security")
    old_security._STATE = {
        "secret": TEST_SECRET,
        "integrity": old_security.trust.unverifiable(old_security.trust.REASON_MANIFEST_MISSING),
    }
    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=types.SimpleNamespace(make_response=_response)))
    request = types.SimpleNamespace(
        data=enveloped_body({"element_ids": [1]}, route=TEST_ROUTE), path=TEST_ROUTE)
    assert old_security.gate_or_response(request) is None
    assert "_mcp" not in json.loads(request.data.decode("utf-8"))


def test_missing_permit_explains_the_mixed_rollout(fake_pyrevit, monkeypatch):
    configure_gate(monkeypatch)
    request = types.SimpleNamespace(
        data=enveloped_body({"element_ids": [1]}, permit=False), path=TEST_ROUTE)
    refusal = security.gate_or_response(request)
    assert refusal.status == 403
    assert refusal.data["permit"] == permits.MISSING
    assert "Обновите RevitMCP и перезапустите сессию ассистента" in refusal.data["hint"]
    assert "Run Update RevitMCP and restart the assistant session" in refusal.data["hint"]
    assert "Nothing was changed" in refusal.data["error"]


def test_status_block_advertises_permit_protocol_including_fallback(monkeypatch):
    configure_gate(monkeypatch)
    assert security.status_block(48884, lambda: []) ["permit"] == permits.status_info()
    monkeypatch.setattr(security, "_STATE", object())
    assert security.status_block(48884, lambda: []) ["permit"] == permits.status_info()


def _status_text(response, policy_status=None):
    async def revit_get(endpoint, ctx=None, timeout=30.0, **kwargs):
        return response

    if policy_status is not None:
        revit_get.policy_status = policy_status
    mcp = _MCP()
    register_status_tools(mcp, revit_get)
    return asyncio.run(mcp.tools["get_revit_status"]())


def test_status_says_when_permits_are_enforced():
    text = _status_text({"permit": {"protocol": 1}})
    assert "One-time permits: the Revit extension enforces them (protocol 1)" in text


def test_status_warns_when_old_extension_does_not_report_permits():
    text = _status_text({})
    assert "One-time permits: the Revit extension does not report permit support (older than R5)" in text
    assert "direct HTTP mutation is not refused" in text


def test_status_names_the_operator_policy_source_and_version():
    async def status(refresh=True):
        assert refresh is True
        return {"source": "operator", "hash": "abc123abc123", "operator_state": "accepted"}

    assert "Approval policy: source operator, version abc123abc123." in _status_text({}, status)


def test_status_explains_rejected_operator_policy():
    async def status(refresh=True):
        return {"source": "base", "hash": "abc123abc123", "operator_state": "rejected",
                "diagnostic": "invalid TOML"}

    text = _status_text({}, status)
    assert "Operator policy file not accepted (файл оператора не принят): rejected: invalid TOML." in text


def test_status_explains_invalid_base_policy_blocks_mutations():
    async def status(refresh=True):
        return {"source": None, "hash": None, "blocked": True, "blocked_reason": "bad base"}

    assert "Every protected operation is refused because the base policy is invalid: bad base." in _status_text({}, status)


def test_transport_without_policy_seam_keeps_legacy_text():
    text = _status_text({})
    assert "Approval policy:" not in text
