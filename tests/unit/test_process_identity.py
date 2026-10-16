# -*- coding: utf-8 -*-
"""Exercise the extension helper with CLR/pyRevit doubles, never live Revit."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_identity(monkeypatch):
    stored, generated = {}, []
    domain = types.SimpleNamespace(GetData=stored.get,
        SetData=lambda key, value: stored.__setitem__(key, value))
    def new_guid():
        generated.append(True)
        return "11111111-1111-4111-8111-111111111111"
    monkeypatch.setitem(sys.modules, "System", types.SimpleNamespace(
        AppDomain=types.SimpleNamespace(CurrentDomain=domain),
        Guid=types.SimpleNamespace(NewGuid=new_guid),
        Diagnostics=types.SimpleNamespace(Process=types.SimpleNamespace(
            GetCurrentProcess=lambda: types.SimpleNamespace(Id=1234)))))
    server = types.SimpleNamespace(server=types.SimpleNamespace(
        server_address=("127.0.0.1", 48885)))
    envvars = types.SimpleNamespace(ROUTES_SERVER="routes-server",
        get_pyrevit_env_var=lambda key: server)
    monkeypatch.setitem(sys.modules, "pyrevit.coreutils", types.SimpleNamespace(envvars=envvars))
    spec = importlib.util.spec_from_file_location("tested_identity", ROOT / "revit_mcp/identity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, stored, generated, server


def test_getter_never_lazily_creates_startup_identity(monkeypatch):
    module, stored, generated, _ = load_identity(monkeypatch)
    with pytest.raises(RuntimeError, match="startup"):
        module.get_process_identity("2024")
    assert not stored and not generated


def test_startup_is_once_and_actual_port_comes_from_retained_server(monkeypatch):
    module, stored, generated, server = load_identity(monkeypatch)
    module.initialize_process_identity()
    module.initialize_process_identity()
    assert len(generated) == 1 and len(stored) == 1
    result = module.get_process_identity("2024")
    assert result == {"pid": 1234, "actual_port": 48885,
                      "session_token": "11111111-1111-4111-8111-111111111111",
                      "revit_version": "2024"}
    server.server.server_address = ("127.0.0.1", 48886)
    assert module.get_process_identity("2024")["actual_port"] == 48886
    assert len(generated) == 1


def test_missing_bound_port_does_not_invent_default(monkeypatch):
    module, _, _, server = load_identity(monkeypatch)
    module.initialize_process_identity()
    server.server = None
    with pytest.raises((RuntimeError, AttributeError)):
        module.get_process_identity("2024")


@pytest.mark.parametrize("has_doc", [True, False])
@pytest.mark.parametrize("identity_failure", [False, True])
def test_actual_status_handler_exposes_identity_without_document(monkeypatch, has_doc, identity_failure):
    identity = {"pid": 1234, "actual_port": 48885,
                "session_token": "11111111-1111-4111-8111-111111111111", "revit_version": "2024"}
    package_name = "identity_status_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT / "revit_mcp")]
    monkeypatch.setitem(sys.modules, package_name, package)
    monkeypatch.setitem(sys.modules, package_name + ".utils", types.SimpleNamespace(sanitize_string=str))
    def get_identity(version):
        if identity_failure:
            raise RuntimeError("startup identity missing")
        return dict(identity)
    monkeypatch.setitem(sys.modules, package_name + ".identity", types.SimpleNamespace(
        get_process_identity=get_identity))
    monkeypatch.setitem(sys.modules, package_name + ".registry", types.SimpleNamespace(
        snapshot=lambda verbose=False: {"registered_domains": 23}, is_degraded=lambda: False))
    routes = types.SimpleNamespace(make_response=lambda data, status=200: (status, data))
    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=routes, revit=types.SimpleNamespace(doc=types.SimpleNamespace(Title="Model") if has_doc else None),
        HOST_APP=types.SimpleNamespace(app=types.SimpleNamespace(VersionNumber="2024"))))
    spec = importlib.util.spec_from_file_location(package_name + ".status", ROOT / "revit_mcp/status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handlers = {}
    def route(path, methods):
        def capture(fn):
            handlers[path] = fn
            return fn
        return capture
    module.register_status_routes(types.SimpleNamespace(name="genpro_revit_mcp", route=route))
    code, payload = handlers["/status/"]()
    assert code == (200 if has_doc else 503)
    if identity_failure:
        assert "process_identity" not in payload
        assert payload["identity_error"] == "startup identity missing"
        if has_doc:
            assert payload["health"] == "degraded"
    else:
        assert payload["process_identity"] == identity
    assert payload["api_name"] == "genpro_revit_mcp"
    if not has_doc:
        assert payload["error"] == "No active Revit document"


def test_startup_initializes_owned_helper_before_domain_registration():
    source = (ROOT / "startup.py").read_text(encoding="utf-8")
    assert "initialize_process_identity()" in source
    assert source.index("initialize_process_identity()") < source.index("for name in _domain_modules(package)")
    assert '"{}.identity".format(_PACKAGE)' in source
