# -*- coding: utf-8 -*-
"""Unit tests for convention-based registration on both halves.

Registration used to be two hand-maintained lists, where a forgotten line
dropped a capability with no error anywhere: the tool simply never appeared and
the route 404'd. Discovery removes the forgotten line; these tests make sure
discovery itself cannot quietly stop finding a domain.

The Revit half cannot be imported here -- revit_mcp/ modules need pyRevit and
IronPython -- so it is checked by applying startup.py's own discovery rules to
the source text. That catches the case these tests exist for: a module that
discovery would skip because its registrar is missing or misspelled.

Needs no Revit.
"""

import asyncio
import os
import re

import tools

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REVIT_MCP_DIR = os.path.join(REPO_ROOT, "revit_mcp")
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_manifest.txt")

# Same patterns startup.py and tools/__init__.py match against.
ROUTE_REGISTRAR = re.compile(r"^def (register_\w+_routes)\(", re.MULTILINE)
ROUTE_DECORATOR = re.compile(r"@api\.route\(")


def _revit_mcp_modules():
    """Module names startup.py's _domain_modules() would scan."""
    return sorted(
        entry[:-3]
        for entry in os.listdir(REVIT_MCP_DIR)
        if entry.endswith(".py") and not entry.startswith("_")
    )


def _source_of(module_name):
    path = os.path.join(REVIT_MCP_DIR, module_name + ".py")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# --- CPython half -----------------------------------------------------------

def _register_all():
    """Register every tool domain against a throwaway server."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("test")

    async def _unused(*args, **kwargs):  # pragma: no cover - never awaited
        raise AssertionError("transport must not be called during registration")

    tools.register_tools(server, _unused, _unused, _unused)
    return server


def test_no_tool_domain_fails_to_register():
    _register_all()
    assert tools.FAILED == {}, "tool domains failed to register: {}".format(tools.FAILED)


def test_every_tool_module_with_a_registrar_is_registered():
    """A module holding a registrar must end up in REGISTERED, not SKIPPED."""
    _register_all()
    for name in tools.SKIPPED:
        module = __import__("tools." + name, fromlist=[name])
        offenders = [a for a in dir(module) if a.startswith("register_")]
        assert not offenders, (
            "tools/{}.py was skipped but defines {} -- the registrar name does "
            "not match register_*_tools".format(name, offenders)
        )


def test_utils_is_classified_as_a_helper():
    _register_all()
    assert "utils" in tools.SKIPPED


def test_every_tool_module_on_disk_is_accounted_for():
    """Derived, not hardcoded.

    A magic domain count would break on every new domain and teach
    contributors to edit the assertion instead of reading it. The manifest is
    the one place a change must be acknowledged deliberately; here we only
    check that discovery accounts for every file it scanned.
    """
    _register_all()
    on_disk = {
        name[:-3]
        for name in os.listdir(os.path.join(REPO_ROOT, "tools"))
        if name.endswith(".py") and not name.startswith("_")
    }
    accounted = set(tools.REGISTERED) | set(tools.SKIPPED) | set(tools.FAILED)
    unaccounted = sorted(on_disk - accounted)
    assert not unaccounted, (
        "discovery never looked at these files: {}".format(unaccounted)
    )


def test_tool_names_match_the_manifest():
    """The guard against a silently dropped tool.

    Adding or removing a tool is a deliberate act: update tool_manifest.txt in
    the same commit. deploy/gate.py checks the same list before publishing.

    Driven with asyncio.run rather than an async test, matching the idiom the
    existing tests/ scripts use and keeping the suite free of a plugin.
    """
    server = _register_all()
    actual = sorted(t.name for t in asyncio.run(server.list_tools()))

    with open(MANIFEST, encoding="utf-8") as handle:
        expected = sorted(line.strip() for line in handle if line.strip())

    missing = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    assert not missing, "tools lost since the manifest was written: {}".format(missing)
    assert not added, (
        "new tools not in the manifest: {} -- add them to "
        "tests/unit/tool_manifest.txt".format(added)
    )


def test_a_broken_domain_is_isolated_and_recorded(monkeypatch):
    """The whole point of discovery-with-isolation.

    One developer's broken module must not stop every other domain from
    registering — and must not disappear quietly either. Simulated by pointing
    discovery at a module name that cannot be imported.
    """
    real_discover = tools._discover

    def _discover_with_a_broken_module():
        yield "definitely_not_a_real_module"
        for name in real_discover():
            yield name

    _register_all()
    healthy_count = len(tools.REGISTERED)

    monkeypatch.setattr(tools, "_discover", _discover_with_a_broken_module)
    _register_all()

    assert "definitely_not_a_real_module" in tools.FAILED, (
        "a module that fails to import must be recorded, not swallowed"
    )
    assert len(tools.REGISTERED) == healthy_count, (
        "one broken domain must not stop the other {} from registering".format(
            healthy_count
        )
    )


def test_a_registrar_that_raises_is_isolated(monkeypatch):
    """An exception inside register_*_tools is contained the same way."""
    import tools.clash_tools as clash_tools

    def _boom(*args, **kwargs):
        raise RuntimeError("registrar exploded")

    monkeypatch.setattr(clash_tools, "register_clash_tools", _boom)
    _register_all()

    assert "clash_tools" in tools.FAILED
    assert "RuntimeError" in tools.FAILED["clash_tools"]
    assert "status_tools" in tools.REGISTERED, (
        "domains after the failing one must still register"
    )


# --- IronPython half (checked as source text) -------------------------------

def test_every_revit_mcp_route_module_exposes_a_registrar():
    """A route module whose registrar is missing or misspelled is invisible."""
    offenders = []
    for name in _revit_mcp_modules():
        source = _source_of(name)
        has_routes = bool(ROUTE_DECORATOR.search(source))
        has_registrar = bool(ROUTE_REGISTRAR.search(source))
        if has_routes and not has_registrar:
            offenders.append(name)
    assert not offenders, (
        "revit_mcp modules define @api.route but no register_*_routes, so "
        "startup.py discovery would skip them: {}".format(offenders)
    )


def test_every_route_domain_has_a_matching_tool_module():
    """Both halves must exist, or a route is unreachable from the MCP client.

    Derived rather than counted. The mapping is by convention but not always
    mechanical, so known exceptions are listed explicitly and anything new has
    to be justified by adding it here.
    """
    # revit_mcp module -> the tools module that drives it, where the names
    # differ. Documented deviations, not accidents.
    KNOWN_MAPPINGS = {
        "placement": "family_tools",   # also driven by model_tools
        "model_info": "status_tools",  # get_revit_model_info lives with status
        "rooms": "room_tools",
        "views": "view_tools",
        "colors": "colors_tools",
        "tags": "tag_tools",
        "parameters": "parameter_tools",
        "transforms": "transform_tools",
        "analysis": "analysis_tools",
    }
    tools_dir = os.path.join(REPO_ROOT, "tools")
    available = {
        name[:-3]
        for name in os.listdir(tools_dir)
        if name.endswith("_tools.py")
    }

    orphans = []
    for domain in _revit_mcp_modules():
        if not ROUTE_DECORATOR.search(_source_of(domain)):
            continue
        candidates = {KNOWN_MAPPINGS.get(domain, ""), domain + "_tools"}
        if not (candidates & available):
            orphans.append(domain)

    assert not orphans, (
        "these route domains have no tools module, so their routes cannot be "
        "reached from an MCP client: {} -- add tools/<domain>_tools.py, or "
        "record the deviation in KNOWN_MAPPINGS".format(orphans)
    )


def test_revit_mcp_helpers_define_no_routes():
    """Helpers must stay helpers -- otherwise discovery would need to load them."""
    for name in ("utils", "textutils", "registry"):
        assert not ROUTE_DECORATOR.search(_source_of(name)), (
            "revit_mcp/{}.py defines routes but is a helper module".format(name)
        )


def test_no_revit_mcp_module_imports_another_revit_mcp_module():
    """The premise that makes alphabetical registration order safe.

    Every cross-module import goes to the `utils`/`textutils` helper. If a
    domain ever imports another domain, registration order starts to matter and
    discovery's sorted() order would need revisiting.

    The import form flipped on 2026-09-07 -- pyRevit attaches IronPython 3, so
    the helpers are reached as `from .utils import ...` rather than flat. A
    relative import is therefore no longer evidence of a violation on its own,
    and this checks the import's *target* instead.
    """
    helpers = {"utils", "textutils", "registry"}
    targets = re.compile(
        r"^from \.(\w+) import|^from revit_mcp\.(\w+) import|^\s*from \. import (\w+)",
        re.MULTILINE,
    )
    offenders = []
    for name in _revit_mcp_modules():
        if name in ("registry",):  # documented exception: holds no Revit code
            continue
        for match in targets.finditer(_source_of(name)):
            target = match.group(1) or match.group(2) or match.group(3)
            if target not in helpers:
                offenders.append("{} -> {}".format(name, target))
    assert not offenders, (
        "these modules import another revit_mcp domain, which would make "
        "registration order significant: {}".format(sorted(offenders))
    )
