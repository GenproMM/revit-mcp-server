# -*- coding: utf-8 -*-
"""Offline preflight contract: real document guard, no transactions or mutations."""

import importlib
import json
import sys
import types

import pytest

from test_routes_mep_parameter_identity import world


SUPPORTED = (
    "/set_parameter/", "/modify_element/", "/delete_elements/",
    "/transform_elements/", "/edit_family/", "/load_family/",
)


@pytest.fixture
def preflight(world, monkeypatch):
    monkeypatch.delitem(sys.modules, "revit_mcp.preflight", raising=False)
    module = importlib.import_module("revit_mcp.preflight")
    captured = {}

    class Api(object):
        def route(self, path, methods=None):
            def register(fn):
                captured[path] = fn
                return fn
            return register

    module.register_preflight_routes(Api())
    return module, captured["/mutation_preflight/"]


def invoke(world, preflight, body=None, raw=None):
    request = types.SimpleNamespace(
        data=raw if raw is not None else json.dumps(body or {}),
        path="/mutation_preflight/", method="POST")
    response = preflight[1](uiapp=world.uiapp, doc=world.injected, request=request)
    assert not world.transactions
    assert not world.events
    return response


@pytest.mark.parametrize("route", SUPPORTED)
def test_supported_route_uses_resolved_document_without_mutation(world, preflight, route):
    world.open("Модель", "C:/Models/Only.rvt", active=True)
    response = invoke(world, preflight, {"route": route, "args": {}})
    assert response.status == 200
    assert response.data["status"] == "ok"
    assert response.data["route"] == route
    assert response.data["document"]["title"] == "Модель"
    assert response.data["facts"] == {"available": False, "reason": "not_collected"}
    assert len(world.guard_calls) == 1


def test_unsupported_route_is_bad_request_before_document_access(world, preflight):
    response = invoke(world, preflight, {"route": "/no_such/", "args": {}})
    assert response.status == 400
    assert response.data["error_code"] == "preflight-unsupported-route"
    assert not world.guard_calls


@pytest.mark.parametrize("raw", ["{bad", "[]", "null", '"text"'])
def test_bad_body_is_bad_request(world, preflight, raw):
    assert invoke(world, preflight, raw=raw).status == 400
    assert not world.guard_calls


@pytest.mark.parametrize("args", [[], None, "bad"])
def test_non_object_args_are_bad_request(world, preflight, args):
    assert invoke(world, preflight, {"route": SUPPORTED[0], "args": args}).status == 400


def test_no_document_refuses_with_real_guard(world, preflight):
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}})
    assert response.status == 503


def test_multiple_documents_require_selector(world, preflight):
    world.open("A", "C:/Models/A.rvt", active=True)
    world.open("B", "C:/Models/B.rvt")
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}})
    assert response.status == 400
    assert response.data["error_code"] == "document-selector-required"


def test_inactive_selected_document_is_not_activated(world, preflight):
    active = world.open("A", "C:/Models/A.rvt", active=True)
    world.open("B", "C:/Models/B.rvt")
    selector = world.tokens()[1]
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}, "document": selector})
    assert response.status == 412
    assert world.uiapp.active is active


def test_guard_refusal_is_returned_unchanged(world, preflight, monkeypatch):
    sentinel = object()
    monkeypatch.setattr(preflight[0], "mutation_document_or_response", lambda *a, **kw: (None, None, sentinel))
    assert invoke(world, preflight, {"route": SUPPORTED[0], "args": {}}) is sentinel


def test_envelope_is_stripped_before_parsing(world, preflight):
    world.open("Only", "C:/Models/Only.rvt", active=True)
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}, "_mcp": {"secret": "wrong"}})
    assert response.status == 200


def test_unexpected_builder_failure_never_raises(world, preflight, monkeypatch):
    world.open("Only", "C:/Models/Only.rvt", active=True)

    def fail(*args):
        raise RuntimeError("unreadable")

    monkeypatch.setitem(preflight[0]._FACTS, SUPPORTED[0], fail)
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}})
    assert response.status == 500
    assert response.data["error_code"] == "preflight-failed"
