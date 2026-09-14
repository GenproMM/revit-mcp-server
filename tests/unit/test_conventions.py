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
def test_request_body_is_not_parsed_by_hand(path):
    violations = conventions.check_request_parsing(_rel(path), _read(path))
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


# --- the IronPython 3 move, 2026-09-07 --------------------------------------
#
# Each of these three shapes cost a pilot machine a route domain, and the last
# one failed silently: `unicode` inside `except Exception` raises NameError,
# is swallowed there, and blanks every parameter value with no log line. Three
# separate greps missed them before the checker owned the rule.

@pytest.mark.parametrize("source, expected", [
    ("from utils import get_element_name", "relatively"),
    ("from textutils import sanitize_string", "relatively"),
    ("from StringIO import StringIO", "IronPython 3"),
    ("from urllib import unquote", "IronPython 3"),
    ("import urlparse", "IronPython 3"),
])
def test_py2_only_forms_are_caught(source, expected):
    bad = "# -*- coding: utf-8 -*-\n{}\n".format(source)
    violations = conventions.check_ironpython_dialect("bad.py", bad)
    assert any(expected in v for v in violations), violations


def test_bare_py2_builtin_is_caught_even_inside_a_broad_except():
    """The parameters.py shape: swallowed NameError, blank data, no log."""
    bad = (
        "# -*- coding: utf-8 -*-\n"
        "def f(value):\n"
        "    try:\n"
        "        return unicode(value)\n"
        "    except Exception:\n"
        "        return ''\n"
    )
    violations = conventions.check_ironpython_dialect("bad.py", bad)
    assert any("Python 2 builtins" in v for v in violations), violations


@pytest.mark.parametrize("source", [
    "from .utils import get_element_name",
    "try:\n    from io import StringIO\nexcept ImportError:\n"
    "    from StringIO import StringIO",
    "try:\n    from urllib.parse import unquote\nexcept ImportError:\n"
    "    from urllib import unquote",
    "try:\n    T = unicode\nexcept NameError:\n    T = str",
])
def test_the_compatibility_idioms_are_allowed(source):
    """Guarded by the *named* exception -- the distinction the check turns on."""
    ok = "# -*- coding: utf-8 -*-\n{}\n".format(source)
    assert not conventions.check_ironpython_dialect("ok.py", ok)


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


def test_request_parsing_detector_catches_the_old_idiom():
    """The idiom that silently produced bytes on IronPython 3."""
    source = (
        "def h(doc, request):\n"
        "    data = json.loads(request.data) if isinstance(request.data, str) "
        "else request.data\n"
    )
    violations = conventions.check_request_parsing("revit_mcp/x.py", source)
    assert len(violations) == 1
    assert "parse_request_data" in violations[0]


def test_request_parsing_detector_allows_the_helper():
    source = "def h(doc, request):\n    data = parse_request_data(request.data)\n"
    assert conventions.check_request_parsing("revit_mcp/x.py", source) == []


def test_code_execution_rejects_missing_document_before_transaction():
    """A model switch can briefly leave pyRevit's injected doc as None."""
    path = os.path.join(REVIT_MCP_DIR, "code_execution.py")
    source = _read(path)
    transaction_at = source.index("DB.Transaction(doc")
    prefix = source[:transaction_at]
    assert "doc = revit.doc" in prefix
    guard_at = prefix.index("if not doc")
    assert guard_at < transaction_at
    assert "No active Revit document" in prefix[guard_at:]
