# -*- coding: utf-8 -*-
"""Our extension must not import or register over another vendor's revit_mcp.

These are offline loader/transport/install-script checks, not a live Revit pass.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
ALIAS = "genpro_revit_mcp"


@pytest.fixture
def loader_tree(tmp_path, monkeypatch):
    package = tmp_path / "revit_mcp"
    package.mkdir()
    (package / "__init__.py").write_text("marker = 'ours'\n", encoding="utf-8")
    (package / "registry.py").write_bytes((ROOT / "revit_mcp/registry.py").read_bytes())
    (package / "example.py").write_text(
        "from . import marker\n"
        "def register_example_routes(api):\n"
        "    @api.route('/status/', methods=['GET'])\n"
        "    def status():\n"
        "        return marker\n", encoding="utf-8")
    startup = tmp_path / "startup.py"
    startup.write_bytes((ROOT / "startup.py").read_bytes())
    table = {}

    class API:
        def __init__(self, name):
            self.name = name

        def route(self, pattern, methods):
            def decorate(fn):
                for method in methods:
                    key = (self.name, method, pattern)
                    assert key not in table, "route overwritten"
                    table[key] = fn
                return fn
            return decorate

    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=types.SimpleNamespace(API=API)))
    foreign = types.ModuleType("revit_mcp")
    foreign.__path__ = ["foreign-package-must-not-be-read"]
    foreign.marker = object()
    foreign_registry = types.ModuleType("revit_mcp.registry")
    foreign_registry.marker = object()
    monkeypatch.setitem(sys.modules, "revit_mcp", foreign)
    monkeypatch.setitem(sys.modules, "revit_mcp.registry", foreign_registry)
    for name in list(sys.modules):
        if name == ALIAS or name.startswith(ALIAS + "."):
            monkeypatch.delitem(sys.modules, name)

    def load():
        spec = importlib.util.spec_from_file_location("parallel_startup", startup)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    yield load, table, API, foreign, foreign_registry, package
    for name in list(sys.modules):
        if name == ALIAS or name.startswith(ALIAS + "."):
            del sys.modules[name]


@pytest.mark.parametrize("foreign_first", [True, False])
def test_two_namespaces_and_packages_do_not_overwrite_each_other(loader_tree, foreign_first):
    load, table, API, foreign, foreign_registry, package = loader_tree
    sentinel = lambda: "foreign"
    if foreign_first:
        API("revit_mcp").route("/status/", ["GET"])(sentinel)
    load()
    if not foreign_first:
        API("revit_mcp").route("/status/", ["GET"])(sentinel)
    assert sys.modules["revit_mcp"] is foreign
    assert sys.modules["revit_mcp.registry"] is foreign_registry
    ours = sys.modules[ALIAS]
    assert Path(ours.__file__).resolve() == (package / "__init__.py").resolve()
    assert sys.modules[ALIAS + ".registry"].REGISTERED == ["example"]
    assert table[(ALIAS, "GET", "/status/")]() == "ours"
    assert table[("revit_mcp", "GET", "/status/")] is sentinel


def test_loader_refuses_alias_from_another_directory(loader_tree, monkeypatch):
    load, table, _, _, _, _ = loader_tree
    collision = types.ModuleType(ALIAS)
    collision.__path__ = ["not-our-tree"]
    monkeypatch.setitem(sys.modules, ALIAS, collision)
    with pytest.raises(ImportError, match="package.*path|path.*package"):
        load()
    assert sys.modules[ALIAS] is collision
    assert table == {}


def test_bridge_never_falls_back_to_foreign_api(monkeypatch):
    import bridge

    seen = []

    def respond(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/status/"):
            return httpx.Response(200, json={"status": "active", "process_identity": {
                "pid": 4242, "actual_port": 48884, "revit_version": "2024",
                "session_token": "11111111-1111-4111-8111-111111111111"}})
        return httpx.Response(404, json={"error": "our route missing"})

    # The bridge now keeps one client per validated incarnation: fix the single
    # process that discovery would pick and route its client through the mock.
    target = {"host": "127.0.0.1", "port": 48884, "pid": 4242,
              "session_token": "11111111-1111-4111-8111-111111111111"}

    async def only_process():
        return dict(target)

    async def proven(_target, state, timeout):
        state.verified = True
        return None

    monkeypatch.setattr(bridge, "resolve_default_target", only_process)
    monkeypatch.setattr(bridge, "_verify_target", proven)
    monkeypatch.setattr(bridge, "listener_snapshot",
                        lambda ports, **kwargs: {target["port"]: [target["pid"]]})

    async def check():
        async with httpx.AsyncClient(base_url=bridge.BASE_URL + "/",
                                     transport=httpx.MockTransport(respond)) as client:
            bridge._state_for(target).client = client
            await bridge.revit_get("/status/")
            await bridge.revit_post("/modify_element/", {})
            await bridge.revit_image("/get_view/test")

    asyncio.run(check())
    assert seen == ["/genpro_revit_mcp/status/", "/genpro_revit_mcp/modify_element/",
                    "/genpro_revit_mcp/get_view/test"]


def test_installer_does_not_retire_disable_or_reconfigure_other_extensions():
    source = (ROOT / "deploy/install.cmd").read_text(encoding="utf-8").lower()
    commands = [line.strip() for line in source.splitlines()
                if line.strip() and not line.lstrip().startswith("rem")]
    assert not any("extensions disable" in line for line in commands)
    assert not any(".retired" in line for line in commands)
    assert not any("configs routes port" in line or "configs routes enable" in line
                   for line in commands)
    assert not any("configure_hermes.py" in line for line in commands)
    assert not any("forget_retired_path.py" in line for line in commands)
    assert not any("executionpolicy bypass" in line for line in commands)
    assert "check_routes_config.py" in (ROOT / "deploy/publish-extension.cmd").read_text()


@pytest.mark.parametrize("doc_state", ["active", "none", "error"])
def test_status_reports_its_own_api_name(loader_tree, monkeypatch, doc_state):
    load, table, _, _, _, package = loader_tree
    (package / "example.py").unlink()
    (package / "status.py").write_bytes((ROOT / "revit_mcp/status.py").read_bytes())
    (package / "utils.py").write_text("def sanitize_string(value):\n    return value\n")
    pyrevit = sys.modules["pyrevit"]
    pyrevit.routes.make_response = lambda data, status=200: (status, data)

    class Revit:
        @property
        def doc(self):
            if doc_state == "error":
                raise RuntimeError("document unavailable")
            return types.SimpleNamespace(Title="Модель") if doc_state == "active" else None

    monkeypatch.setattr(pyrevit, "revit", Revit(), raising=False)
    load()
    status, payload = table[(ALIAS, "GET", "/status/")]()
    assert status == (200 if doc_state == "active" else 503)
    assert payload["api_name"] == ALIAS


@pytest.mark.parametrize("enabled,host,port,expected", [
    ("true", '"127.0.0.1"', "48884", True),
    ("true", '"127.0.0.1"', "48885", True),
    ("false", '"127.0.0.1"', "48884", False),
    ("true", '"0.0.0.0"', "48884", False),
    ("true", '"127.0.0.1"', "0", False),
    ("true", '"127.0.0.1"', "65536", False),
    ("true", '"127.0.0.1"', "abc", False),
])
def test_shared_routes_check_is_read_only(tmp_path, enabled, host, port, expected):
    from deploy.check_routes_config import check_config

    path = tmp_path / "pyRevit_config.ini"
    content = ("[routes]\nenabled = {}\nhost = {}\nport = {}\n"
               "[foreign.extension]\ndisabled = false\n").format(enabled, host, port).encode()
    path.write_bytes(content)
    ok, message = check_config(path)
    assert ok is expected
    assert path.read_bytes() == content
    if expected:
        assert "REVIT_PORT=" + port in message


def test_diagnostic_clients_target_only_our_namespace():
    import ast

    for relative in ("scripts/probe_handler_overlap.py", "contrib-kit/revitmcp_kit.py",
                     "tests/test_phase2_preflight.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "/revit_mcp" not in source, relative
        assert "genpro_revit_mcp" in source, relative
    source = (ROOT / "tests/test_phase2_preflight.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    snippet = next(node.value.value for node in module.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "G1_SNIPPET" for t in node.targets))
    assert 'API_NAME = "genpro_revit_mcp"' in snippet
    kit = (ROOT / "contrib-kit/revitmcp_kit.py").read_text(encoding="utf-8")
    assert "import revit_mcp as" not in kit
    assert '"__package__": "genpro_revit_mcp"' in kit


def test_shared_routes_check_refuses_missing_configuration(tmp_path):
    from deploy.check_routes_config import check_config

    assert check_config(tmp_path / "missing.ini")[0] is False
