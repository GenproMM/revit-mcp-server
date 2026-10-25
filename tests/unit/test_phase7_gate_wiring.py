# -*- coding: utf-8 -*-
"""Phase 7 one-time-permit enforcement is structurally unique and fails closed."""

import ast
import os
import sys
import types

import pytest

from gate_support import (
    TEST_ROUTE, TEST_SECRET, TEST_SESSION_TOKEN, configure_gate, enveloped_body, request_of,
)
from revit_mcp import identity, permits, security, trust

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECURITY_PATH = os.path.join(REPO_ROOT, "revit_mcp", "security.py")


@pytest.fixture(autouse=True)
def fake_pyrevit(monkeypatch):
    def make_response(data=None, status=200, headers=None):
        return types.SimpleNamespace(status=status, data=data)

    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=types.SimpleNamespace(make_response=make_response)))


def _dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return "{}.{}".format(base, node.attr) if base else None
    return None


def _security_tree():
    with open(SECURITY_PATH, encoding="utf-8") as handle:
        return ast.parse(handle.read())


def _function(tree, name):
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _calls(node, dotted):
    return [call for call in ast.walk(node) if isinstance(call, ast.Call)
            and _dotted_name(call.func) == dotted]


def test_gate_calls_check_and_consume_exactly_once_between_integrity_and_rewrite():
    gate = _function(_security_tree(), "gate_or_response")
    calls = _calls(gate, "permits.check_and_consume")

    assert len(calls) == 1
    statements = next(statement.body for statement in gate.body if isinstance(statement, ast.Try))
    permit_index = next(index for index, statement in enumerate(statements)
                        if calls[0] in ast.walk(statement))
    integrity_index = next(index for index, statement in enumerate(statements)
                           if isinstance(statement, ast.If)
                           and "INTEGRITY_MISMATCH" in ast.unparse(statement.test))
    rewrite_index = next(index for index, statement in enumerate(statements)
                         if isinstance(statement, ast.Assign)
                         and any(isinstance(target, ast.Attribute) and target.attr == "data"
                                 for target in statement.targets))
    assert integrity_index < permit_index < rewrite_index
    refusal = statements[permit_index + 1]
    assert isinstance(refusal, ast.If)
    assert _calls(refusal, "_refusal")
    assert _calls(refusal, "permits.failure")


def test_gate_is_the_only_caller_of_check_and_consume():
    for filename in os.listdir(os.path.join(REPO_ROOT, "revit_mcp")):
        if not filename.endswith(".py"):
            continue
        with open(os.path.join(REPO_ROOT, "revit_mcp", filename), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
            calls = _calls(function, "permits.check_and_consume")
            assert not calls or (filename == "security.py" and function.name == "gate_or_response")


def test_valid_permit_passes_and_rewrites_the_body(monkeypatch):
    configure_gate(monkeypatch)
    request = request_of({"element_ids": [101]}, route="/delete_elements/")

    assert security.gate_or_response(request) is None
    assert b"_mcp" not in request.data and b"element_ids" in request.data


def test_a_replayed_permit_is_refused(monkeypatch):
    configure_gate(monkeypatch)
    body = enveloped_body({"element_ids": [101]}, route="/delete_elements/")

    assert security.gate_or_response(types.SimpleNamespace(data=body, path="/delete_elements/")) is None
    refusal = security.gate_or_response(types.SimpleNamespace(data=body, path="/delete_elements/"))
    assert (refusal.status, refusal.data["permit"]) == (403, permits.REPLAYED)


def test_a_permit_for_another_route_is_refused(monkeypatch):
    configure_gate(monkeypatch)
    request = types.SimpleNamespace(
        data=enveloped_body({"element_ids": [101]}, route="/transform_elements/"),
        path="/delete_elements/",
    )

    refusal = security.gate_or_response(request)
    assert (refusal.status, refusal.data["permit"]) == (403, permits.ROUTE_MISMATCH)


def test_a_permit_for_another_revit_session_is_refused(monkeypatch):
    configure_gate(monkeypatch, session_token="another-process")
    request = request_of({"element_ids": [101]}, route="/delete_elements/")

    refusal = security.gate_or_response(request)
    assert (refusal.status, refusal.data["permit"]) == (403, permits.SESSION_MISMATCH)


def test_a_valid_secret_without_a_permit_is_refused_with_the_update_hint(monkeypatch):
    configure_gate(monkeypatch)
    request = types.SimpleNamespace(
        data=enveloped_body({"element_ids": [101]}, route="/delete_elements/", permit=False),
        path="/delete_elements/",
    )

    refusal = security.gate_or_response(request)
    assert (refusal.status, refusal.data["permit"]) == (403, permits.MISSING)
    assert "Обновите RevitMCP и перезапустите сессию ассистента" in refusal.data["hint"]
    assert "Run Update RevitMCP and restart the assistant session" in refusal.data["hint"]


def test_wrong_secret_precedes_permit_and_does_not_consume_a_permit(monkeypatch):
    configure_gate(monkeypatch)
    valid = enveloped_body({"element_ids": [101]}, route="/delete_elements/")
    wrong = enveloped_body({"element_ids": [101]}, secret="wrong-secret-0123456789-abcdefXYZ-nope",
                           route="/delete_elements/")

    refusal = security.gate_or_response(types.SimpleNamespace(data=wrong, path="/delete_elements/"))
    assert (refusal.status, refusal.data["auth"]) == (401, trust.AUTH_MISMATCH)
    assert security.gate_or_response(types.SimpleNamespace(data=valid, path="/delete_elements/")) is None


def test_integrity_precedes_permit_and_does_not_consume_a_permit(monkeypatch):
    mismatch = {"state": trust.INTEGRITY_MISMATCH, "reason": None,
                "modified": ["revit_mcp/security.py"], "missing": [], "unexpected": []}
    configure_gate(monkeypatch, integrity=mismatch)
    body = enveloped_body({"element_ids": [101]}, route="/delete_elements/")

    refusal = security.gate_or_response(types.SimpleNamespace(data=body, path="/delete_elements/"))
    assert refusal.status == 423
    security._STATE["integrity"] = trust.unverifiable(trust.REASON_MANIFEST_MISSING)
    assert security.gate_or_response(types.SimpleNamespace(data=body, path="/delete_elements/")) is None


def test_strip_envelope_never_consumes_a_permit(monkeypatch):
    configure_gate(monkeypatch)
    body = enveloped_body({"category": "Walls"}, route="/ai_filter/")
    open_read = types.SimpleNamespace(data=body, path="/ai_filter/")

    assert security.strip_envelope(open_read) is None
    assert b"_mcp" not in open_read.data
    assert security.gate_or_response(types.SimpleNamespace(data=body, path="/ai_filter/")) is None


def test_process_token_is_none_under_cpython_and_security_delegates(monkeypatch):
    assert identity.process_token() is None
    monkeypatch.setattr(identity, "process_token", lambda: TEST_SESSION_TOKEN)
    assert security._process_token() == TEST_SESSION_TOKEN


@pytest.mark.parametrize("path,expected", (
    (None, None), ("", None), ("/", None), (TEST_ROUTE, TEST_ROUTE), ("/x/?q=1", "/x/"),
))
def test_permit_route_normalization_is_the_verifier_contract(path, expected):
    assert permits.normalize_route(path) == expected
