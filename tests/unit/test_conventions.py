# -*- coding: utf-8 -*-
"""Mechanical enforcement of the conventions in CONTRIBUTING.md.

Everything here used to be enforced only by review. That does not survive
contact with several developers of mixed experience driving code generation
models: prose in a rules file is advice, a failing test is not.

The checks themselves live in scripts/conventions.py, not here, because three
callers must agree exactly -- this suite, scripts/intake_package.py, and the
copy of that module shipped in the contributor kit. A contributor has no access
to this repository, so if the rules lived in a test file their kit would drift
and tell them a package is fine when it is not.

If a check is wrong, fix it in scripts/conventions.py -- but never weaken it
silently, because the rule it stands for is what keeps the IronPython half
loadable and the tool schemas usable by a model.

Needs no Revit.
"""

import io
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import conventions  # noqa: E402

REVIT_MCP_DIR = os.path.join(REPO_ROOT, "revit_mcp")
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")


def _py_files(directory):
    return sorted(
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.endswith(".py")
    )


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _rel(path):
    return os.path.relpath(path, REPO_ROOT).replace("\\", "/")


REVIT_MCP_FILES = _py_files(REVIT_MCP_DIR)
TOOLS_FILES = [p for p in _py_files(TOOLS_DIR) if not p.endswith("__init__.py")]

# Modules that legitimately hold no registrar. Everything else under these two
# directories is a domain and is checked as one.
HELPERS = {"revit_mcp/utils.py", "revit_mcp/textutils.py", "revit_mcp/registry.py",
           "tools/utils.py"}


def _report(violations):
    return "\n  - " + "\n  - ".join(violations) if violations else ""


# --- applies to both halves -------------------------------------------------

@pytest.mark.parametrize("path", REVIT_MCP_FILES + TOOLS_FILES, ids=_rel)
def test_encoding_cookie(path):
    violations = conventions.check_encoding_cookie(_rel(path), _read(path))
    assert not violations, _report(violations)


# --- the Revit half ---------------------------------------------------------

@pytest.mark.parametrize("path", REVIT_MCP_FILES, ids=_rel)
def test_ironpython_dialect(path):
    """f-strings, async and Python-3-only imports break extension load."""
    violations = conventions.check_ironpython_dialect(_rel(path), _read(path))
    assert not violations, _report(violations)


@pytest.mark.parametrize("path", REVIT_MCP_FILES, ids=_rel)
def test_element_id_helpers_are_used(path):
    if _rel(path) == "revit_mcp/utils.py":
        pytest.skip("utils.py is where the compatibility shims legitimately live")
    violations = conventions.check_element_id(_rel(path), _read(path))
    assert not violations, _report(violations)


@pytest.mark.parametrize("path", REVIT_MCP_FILES, ids=_rel)
def test_route_registrar(path):
    violations = conventions.check_route_registrar(_rel(path), _read(path))
    assert not violations, _report(violations)


# --- the MCP half -----------------------------------------------------------

@pytest.mark.parametrize("path", TOOLS_FILES, ids=_rel)
def test_tool_registrar_signature(path):
    if _rel(path) in HELPERS:
        pytest.skip("{} is a helper module, not a tool domain".format(_rel(path)))
    violations = conventions.check_tool_registrar(_rel(path), _read(path))
    assert not violations, _report(violations)


@pytest.mark.parametrize("path", TOOLS_FILES, ids=_rel)
def test_tool_signatures_and_docstrings(path):
    """The docstring is the API contract the model sees before calling."""
    if _rel(path) in HELPERS:
        pytest.skip("{} is a helper module, not a tool domain".format(_rel(path)))
    violations = conventions.check_tools(_rel(path), _read(path))
    assert not violations, _report(violations)


# --- the checkers themselves ------------------------------------------------
#
# The contributor kit ships a copy of scripts/conventions.py and a contributor
# never runs this suite. If a checker silently stopped detecting anything, both
# they and intake would go green on a broken package -- so the detectors are
# tested against known-bad input, not only against the clean tree.

def test_f_string_detector_catches_a_real_f_string():
    bad = '# -*- coding: utf-8 -*-\nx = 1\nname = f"level {x}"\n'
    violations = conventions.check_ironpython_dialect("bad.py", bad)
    assert any("f-strings" in v for v in violations), violations


@pytest.mark.parametrize(
    "line",
    ['y = float("inf")', 'kind = "roof"', 'path = "plan.pdf"', 'msg = "of "'],
)
def test_f_string_detector_ignores_lookalikes(line):
    source = "# -*- coding: utf-8 -*-\n{}\n".format(line)
    violations = conventions.check_ironpython_dialect("ok.py", source)
    assert not any("f-strings" in v for v in violations), violations


def test_element_id_detector_catches_an_integer():
    bad = "# -*- coding: utf-8 -*-\nDB.ElementId(12345)\n"
    assert conventions.check_element_id("bad.py", bad)


def test_element_id_detector_allows_an_enum_overload():
    """DB.ElementId(<BuiltInCategory>) is a different, valid overload."""
    ok = "# -*- coding: utf-8 -*-\ncat_id = DB.ElementId(bic)\n"
    assert not conventions.check_element_id("ok.py", ok)


def test_ctx_last_detector_catches_the_wrong_order():
    bad = (
        "# -*- coding: utf-8 -*-\n"
        "def register_x_tools(mcp, revit_get, revit_post, revit_image=None):\n"
        "    @mcp.tool()\n"
        "    async def t(ctx: Context = None, name: str = None) -> str:\n"
        '        \"\"\"Doc.\n\n        Args:\n            name: n\n'
        '            ctx: c\n        \"\"\"\n'
        "        return format_response(None)\n"
    )
    violations = conventions.check_tools("bad.py", bad)
    assert any("last parameter" in v for v in violations), violations


def test_missing_args_block_is_caught():
    bad = (
        "# -*- coding: utf-8 -*-\n"
        "def register_x_tools(mcp, revit_get, revit_post, revit_image=None):\n"
        "    @mcp.tool()\n"
        "    async def t(ctx: Context = None) -> str:\n"
        '        \"\"\"Just a summary.\"\"\"\n'
        "        return format_response(None)\n"
    )
    violations = conventions.check_tools("bad.py", bad)
    assert any("Args:" in v for v in violations), violations


def test_undocumented_parameter_is_caught():
    bad = (
        "# -*- coding: utf-8 -*-\n"
        "def register_x_tools(mcp, revit_get, revit_post, revit_image=None):\n"
        "    @mcp.tool()\n"
        "    async def t(name: str = None, ctx: Context = None) -> str:\n"
        '        \"\"\"Doc.\n\n        Args:\n            ctx: c\n        \"\"\"\n'
        "        return format_response(None)\n"
    )
    violations = conventions.check_tools("bad.py", bad)
    assert any("missing from the Args:" in v for v in violations), violations


def test_missing_tool_registrar_is_caught():
    bad = "# -*- coding: utf-8 -*-\ndef setup(mcp):\n    pass\n"
    violations = conventions.check_tool_registrar("bad.py", bad)
    assert any("no register_*_tools" in v for v in violations), violations


def test_route_module_without_a_registrar_is_caught():
    bad = (
        "# -*- coding: utf-8 -*-\n"
        "def wire(api):\n"
        "    @api.route(\"/x/\", methods=[\"GET\"])\n"
        "    def h(doc):\n"
        "        return None\n"
    )
    violations = conventions.check_route_registrar("bad.py", bad)
    assert any("no register_*_routes" in v for v in violations), violations


def test_clean_module_produces_no_violations():
    """A sanity anchor: the reference tool module must pass every checker."""
    path = os.path.join(TOOLS_DIR, "clash_tools.py")
    assert not conventions.check_tool_module("tools/clash_tools.py", _read(path))
