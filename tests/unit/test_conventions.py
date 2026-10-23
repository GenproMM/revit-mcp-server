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


# Phase 4 D-02. No utils.py skip here, unlike test_element_id_helpers_are_used:
# the one legitimate Commit() lives in utils.py and the checker exempts exactly
# that function, so the file is checked like every other.

@pytest.mark.parametrize("path", REVIT_MCP_FILES, ids=_rel)
def test_commits_go_through_commit_and_report(path):
    violations = conventions.check_commit_goes_through_report(_rel(path), _read(path))
    assert not violations, _report(violations)


@pytest.mark.parametrize("path", REVIT_MCP_FILES, ids=_rel)
def test_suppress_warnings_result_is_kept(path):
    violations = conventions.check_swallower_is_kept(_rel(path), _read(path))
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


# --- Phase 4 D-02: a Commit() goes through commit_and_report ----------------
#
# A discarded Commit() return hid every rollback: the route answered success
# for an edit Revit had thrown away, and Phase 6's audit log reads `outcome`.
# These detectors are proven on known-bad input for the same reason as the rest:
# the kit ships a copy and a contributor never runs this suite.

_HEADER = "# -*- coding: utf-8 -*-\n"


def _commit_hits(source, label="revit_mcp/x.py"):
    return conventions.check_commit_goes_through_report(label, _HEADER + source)


def test_commit_detector_catches_a_bare_commit():
    violations = _commit_hits(
        "def h(doc, request):\n"
        "    t = DB.Transaction(doc, 'x')\n"
        "    t.Start()\n"
        "    t.Commit()\n"
    )
    assert len(violations) == 1, violations
    assert "commit_and_report" in violations[0]
    assert "[5]" in violations[0]


def test_commit_detector_catches_a_family_document_comparison():
    violations = _commit_hits(
        "def h(ft):\n"
        "    touched = (ft.Commit() == DB.TransactionStatus.Committed)\n"
    )
    assert len(violations) == 1, violations
    assert "commit_and_report" in violations[0]


def test_commit_detector_catches_a_bound_reference():
    """`commit = t.Commit` then `commit()` is the same bypass, one step removed."""
    violations = _commit_hits(
        "def h(t):\n"
        "    commit = t.Commit\n"
        "    commit()\n"
    )
    assert len(violations) == 1, violations


@pytest.mark.parametrize("source", [
    "def h(t, swallower):\n    commit_result = commit_and_report(t, swallower)\n",
    "def h(t):\n    # t.Commit() is what commit_and_report calls\n    pass\n",
    "def h(t):\n    msg = 'rolled back at t.Commit()'\n",
    "def h(t):\n    '''Docstring that says t.Commit().'''\n",
    "def h(r):\n    return r == DB.TransactionStatus.Committed\n",
])
def test_commit_detector_ignores_the_good_forms_and_mentions(source):
    assert _commit_hits(source) == []


_UTILS_COMMIT = (
    "def commit_and_report(transaction, swallower=None):\n"
    "    status = transaction.Commit()\n"
    "    return status\n"
)


def test_commit_detector_exempts_commit_and_report_in_utils():
    assert _commit_hits(_UTILS_COMMIT, label="revit_mcp/utils.py") == []


def test_commit_detector_utils_exemption_accepts_backslash_labels():
    assert _commit_hits(_UTILS_COMMIT, label="revit_mcp\\utils.py") == []


def test_commit_detector_utils_exemption_is_only_for_that_function():
    violations = _commit_hits(
        _UTILS_COMMIT
        + "def other(t):\n"
        "    t.Commit()\n",
        label="revit_mcp/utils.py",
    )
    assert len(violations) == 1, violations
    assert "[6]" in violations[0]


def test_commit_detector_utils_exemption_is_only_for_utils():
    """The same function in any other file is not exempt."""
    violations = _commit_hits(_UTILS_COMMIT, label="revit_mcp/x.py")
    assert len(violations) == 1, violations


def test_commit_detector_exemption_does_not_cover_a_nested_other_label():
    """A commit in a function merely nested beside the exempt one is caught."""
    violations = _commit_hits(
        "def commit_and_report(transaction, swallower=None):\n"
        "    return transaction.Commit()\n"
        "class K:\n"
        "    def commit_and_report(self, t):\n"
        "        return t.Commit()\n",
        label="revit_mcp/utils.py",
    )
    # The module-level function is exempt; the method of the same name is not.
    assert len(violations) == 1, violations
    assert "[6]" in violations[0]


def _swallower_hits(source):
    return conventions.check_swallower_is_kept("revit_mcp/x.py", _HEADER + source)


def test_swallower_detector_catches_a_discarded_suppress_warnings():
    violations = _swallower_hits("def h(t):\n    suppress_warnings(t)\n")
    assert len(violations) == 1, violations
    assert "suppress_warnings" in violations[0]
    assert "[3]" in violations[0]


@pytest.mark.parametrize("call", [
    "commit_and_report(t)",
    "commit_and_report(t, None)",
    "commit_and_report(t, swallower=None)",
])
def test_swallower_detector_catches_a_commit_without_a_swallower(call):
    violations = _swallower_hits("def h(t):\n    r = {}\n".format(call))
    assert len(violations) == 1, violations
    assert "commit_and_report" in violations[0]


@pytest.mark.parametrize("source", [
    "def h(t):\n    swallower = suppress_warnings(t)\n",
    "def h(t, swallower):\n    r = commit_and_report(t, swallower)\n",
    "def h(t, s):\n    r = commit_and_report(t, swallower=s)\n",
    "def h(t):\n    # suppress_warnings(t) must keep its result\n    pass\n",
    "def h(t):\n    msg = 'commit_and_report(t)'\n",
])
def test_swallower_detector_ignores_the_good_forms_and_mentions(source):
    assert _swallower_hits(source) == []


def test_route_module_check_reports_the_new_violations_with_the_old():
    bad = (
        "# -*- coding: utf-8 -*-\n"
        "def register_x_routes(api):\n"
        "    @api.route('/x/', methods=['POST'])\n"
        "    def h(doc, request):\n"
        "        t = DB.Transaction(doc, 'x')\n"
        "        t.Start()\n"
        "        suppress_warnings(t)\n"
        "        t.Commit()\n"
        "        data = json.loads(request.data)\n"
    )
    violations = conventions.check_route_module("revit_mcp/x.py", bad)
    assert any("Commit() outside commit_and_report" in v for v in violations), violations
    assert any("suppress_warnings" in v for v in violations), violations
    assert any("parse_request_data" in v for v in violations), violations


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
