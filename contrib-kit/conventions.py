# -*- coding: utf-8 -*-
"""The conventions, as code. Single source of truth for every checker.

Used by three callers that must never disagree:

  * tests/unit/test_conventions.py  -- the repository's own suite
  * scripts/intake_package.py       -- the gate on contributed packages
  * contrib-kit/revitmcp_kit.py     -- what a contributor runs before sending

A contributor has no access to this repository, so the kit ships a copy of this
file. If the checks lived in the test file, the copy would drift and a
contributor would be told their package is fine when it is not. Keep this
module standard-library only and free of pytest, so it runs under any python3 --
including the one pyRevit brings, which is all a contributor is guaranteed to
have.

Every function takes source text and returns a list of human-readable
violations. Empty list means the rule holds.
"""

import ast
import re

ENCODING_COOKIE = re.compile(r"^#\s*-\*-\s*coding:\s*utf-8\s*-\*-\s*$", re.IGNORECASE)

TOOL_REGISTRAR = re.compile(r"^register_\w+_tools$")
ROUTE_REGISTRAR = re.compile(r"^register_\w+_routes$")

CANONICAL_TOOL_REGISTRAR = ["mcp", "revit_get", "revit_post", "revit_image"]

# Not available in IronPython.
PY3_ONLY_MODULES = {
    "pathlib", "dataclasses", "typing", "asyncio", "enum", "secrets",
    "statistics", "unittest.mock", "concurrent",
}

# Modules that live inside the revit_mcp package. Importing one of these
# without a leading dot is the implicit relative import Python 3 removed.
# `revit_mcp` itself is listed because `from revit_mcp import registry` works
# only while the extension root happens to be on sys.path; `from . import
# registry` does not depend on that.
LOCAL_MODULES = {"utils", "textutils", "registry", "revit_mcp"}

# Gone in Python 3, so gone in IronPython 3.
PY2_ONLY_MODULES = {
    "StringIO", "cStringIO", "urlparse", "urllib2", "httplib", "ConfigParser",
    "cPickle", "Queue", "HTMLParser", "commands", "copy_reg",
}

# Modules that still exist but whose members moved.
PY2_MOVED_NAMES = {
    "urllib": {"unquote", "quote", "quote_plus", "unquote_plus", "urlencode",
               "urlopen", "urlretrieve", "pathname2url", "url2pathname"},
    "itertools": {"izip", "imap", "ifilter", "izip_longest", "ifilterfalse"},
}

# Builtins removed in Python 3. `unicode` is the one that matters: written
# bare inside an `except Exception`, it raises NameError, gets swallowed on the
# spot, and the function returns its empty fallback for every input. That is
# not a crash anyone notices -- it is blank data. Only the explicit
# compatibility idiom is allowed, and only when the handler names NameError:
#     try:  _TEXT_TYPE = unicode
#     except NameError:  _TEXT_TYPE = str
PY2_ONLY_NAMES = {"unicode", "basestring", "xrange", "long", "raw_input", "unichr"}


def _blank_strings_and_comments(source):
    """Blank string literals and comments so text checks only see code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if hasattr(node, "end_lineno") and node.end_lineno is not None:
                for i in range(node.lineno - 1, min(node.end_lineno, len(lines))):
                    lines[i] = ""
    return "\n".join(line.split("#")[0] for line in lines)


def _parse(label, source):
    """Parse with Python 3's parser.

    The Revit half must be written in the subset that is valid under BOTH
    IronPython 3 (which sits at the Python 3.4 language level) and modern
    Python 3 -- that is what `"{}".format(x)` everywhere buys, and it is what
    lets any of this be checked outside Revit at all. Python-2-only syntax
    (`except E, e:`, `print x`, backticks) is therefore a violation in its own
    right, not just an inconvenience for the checker.
    """
    try:
        return ast.parse(source), None
    except SyntaxError as exc:
        return None, (
            "{}: does not parse as Python 3 -- {}. The Revit half must be "
            "valid under both IronPython 3 and modern Python 3; avoid "
            "Python-2-only syntax such as `except E, e:` or `print x`.".format(
                label, exc
            )
        )


# --------------------------------------------------------------------------
# both halves
# --------------------------------------------------------------------------

def check_encoding_cookie(label, source):
    lines = source.splitlines()
    if not lines or not ENCODING_COOKIE.match(lines[0]):
        found = lines[0] if lines else "<empty file>"
        return [
            "{}: line 1 must be `# -*- coding: utf-8 -*-` (IronPython needs it), "
            "found: {!r}".format(label, found)
        ]
    return []


# --------------------------------------------------------------------------
# the Revit half: IronPython 3 dialect (Python 3.4 language level)
# --------------------------------------------------------------------------

def _guarded_by(tree, exception_names):
    """ids of nodes in a try/except that explicitly handles one of these.

    Both the body and the handler bodies count: the compatibility idiom puts
    the Python 3 form in one and the Python 2 form in the other, and which
    goes where differs between an import and a name alias.

    The handler must *name* the exception. `except Exception` does catch
    NameError, but it catches everything else too -- which is exactly how the
    parameters.py copy of sanitize_string hid a NameError for months.
    """
    guarded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        handled = set()
        for handler in node.handlers:
            if handler.type is None:
                continue
            for sub in ast.walk(handler.type):
                if isinstance(sub, ast.Name):
                    handled.add(sub.id)
        if not (handled & exception_names):
            continue
        for stmt in list(node.body) + [s for h in node.handlers for s in h.body]:
            for child in ast.walk(stmt):
                guarded.add(id(child))
    return guarded


def check_ironpython_dialect(label, source):
    """f-strings, async and Python-3-only imports break the Revit half.

    An f-string here is a SyntaxError at extension load: the domain is skipped,
    the tool never appears, and nothing in the log says why.
    """
    violations = []
    tree, error = _parse(label, source)
    if error:
        return [error]

    # An f-string is exactly ast.JoinedStr. Detected structurally rather than
    # by matching text: a regex for f["'] also matches the tail of
    # float("inf"), "roof" and ".pdf", and an earlier text-based version of
    # this check missed real f-strings outright because blanking string
    # literals erased the `f` prefix along with the string.
    f_lines = sorted({n.lineno for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)})
    if f_lines:
        violations.append(
            "{}: f-strings need Python 3.6+ and this file runs under "
            "IronPython 3, which sits at the Python 3.4 language level -- use "
            "\"{{}}\".format(x). Lines: {}".format(label, f_lines)
        )

    async_defs = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    if async_defs:
        violations.append(
            "{}: async is Python 3 only; the Revit half is synchronous. "
            "Functions: {}".format(label, async_defs)
        )

    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    banned = sorted(found & PY3_ONLY_MODULES)
    if banned:
        violations.append(
            "{}: {} do not exist in IronPython".format(label, banned)
        )

    # Helper imports must be RELATIVE. A flat `from utils import ...` inside
    # the revit_mcp package is an implicit relative import, and Python 3
    # removed those. pyRevit now attaches IronPython 3, so a flat import here
    # raises ImportError at load: the domain is skipped, its tools never
    # appear, and /status/ answers "Route does not exist" from pyRevit's own
    # server rather than ours. Verified on the first pilot machine, where this
    # took out 22 of 23 domains at once.
    #
    # The direction changed on 2026-09-07; the consistency requirement did not.
    # pyRevit also puts the module directory on sys.path, so mixing both forms
    # loads utils.py twice under two identities, each with its own state.
    # Python-2-only imports and builtins. Each of these cost a pilot machine a
    # domain on 2026-09-07, and two of the three failed silently.
    importable = _guarded_by(tree, {"ImportError"})
    py2_imports = []
    for node in ast.walk(tree):
        if id(node) in importable:
            continue
        if isinstance(node, ast.Import):
            py2_imports.extend(
                a.name for a in node.names
                if a.name.split(".")[0] in PY2_ONLY_MODULES
            )
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] in PY2_ONLY_MODULES:
                py2_imports.append(node.module)
            else:
                moved = PY2_MOVED_NAMES.get(node.module, set())
                py2_imports.extend(
                    "{}.{}".format(node.module, a.name)
                    for a in node.names if a.name in moved
                )
    if py2_imports:
        violations.append(
            "{}: {} do not exist in IronPython 3. Guard with "
            "`try: <py3 form> / except ImportError: <py2 form>`.".format(
                label, sorted(set(py2_imports))
            )
        )

    nameable = _guarded_by(tree, {"NameError"})
    py2_names = sorted({
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name)
        and n.id in PY2_ONLY_NAMES
        and id(n) not in nameable
    })
    if py2_names:
        violations.append(
            "{}: {} are Python 2 builtins, removed in IronPython 3. A bare "
            "reference inside `except Exception` raises NameError, is swallowed "
            "there, and silently blanks the data instead of failing. Alias them "
            "once under `except NameError`, as revit_mcp/textutils.py does."
            .format(label, py2_names)
        )

    flat = sorted({
        n.module for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        and n.level == 0
        and n.module in LOCAL_MODULES
    })
    if flat:
        violations.append(
            "{}: import package modules relatively -- `from .utils import ...`, "
            "not {}. A flat import of a sibling is an implicit relative import, "
            "which Python 3 removed, so the domain fails to load under "
            "IronPython 3.".format(label, flat)
        )
    return violations


def check_element_id(label, source):
    """.IntegerValue and DB.ElementId(<int>) break across Revit versions."""
    violations = []
    code = _blank_strings_and_comments(source)
    hits = [i + 1 for i, line in enumerate(code.splitlines()) if ".IntegerValue" in line]
    if hits:
        violations.append(
            "{}: use get_element_id_value() instead of .IntegerValue. "
            "Lines: {}".format(label, hits)
        )

    tree, error = _parse(label, source)
    if error:
        return violations + [error]

    # DB.ElementId(<enum>) -- e.g. a BuiltInCategory -- is a different, valid
    # overload. Only the integer forms are the 2027 foot-gun.
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "ElementId" or not node.args:
            continue
        arg = node.args[0]
        if (
            (isinstance(arg, ast.Constant) and isinstance(arg.value, int))
            or (isinstance(arg, ast.Call) and getattr(arg.func, "id", None) == "int")
            or (isinstance(arg, ast.Name) and (arg.id.endswith("_id") or arg.id in ("eid", "id")))
        ):
            bad.append(node.lineno)
    if bad:
        violations.append(
            "{}: use make_element_id() instead of building DB.ElementId from an "
            "integer -- a bare int fails on Revit 2027 with \"Multiple targets "
            "could match\". Lines: {}".format(label, sorted(bad))
        )
    return violations


def check_route_registrar(label, source):
    """Exactly one register_*_routes(api), or discovery cannot find the domain."""
    tree, error = _parse(label, source)
    if error:
        return [error]

    registrars = [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and ROUTE_REGISTRAR.match(n.name)
    ]
    has_routes = any(
        isinstance(n, ast.Call) and getattr(getattr(n.func, "value", None), "id", None) == "api"
        for n in ast.walk(tree)
    ) or "@api.route(" in source

    if has_routes and not registrars:
        return [
            "{}: defines @api.route but no register_*_routes function, so "
            "discovery will treat it as a helper and the routes will never be "
            "registered.".format(label)
        ]
    violations = []
    for node in registrars:
        args = [a.arg for a in node.args.args]
        if args != ["api"]:
            violations.append(
                "{}: {}() must take exactly (api), found {}".format(
                    label, node.name, args
                )
            )
    return violations


# --------------------------------------------------------------------------
# the MCP half: tool signatures and docstrings
# --------------------------------------------------------------------------

def _tool_functions(tree):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if getattr(target, "attr", getattr(target, "id", None)) == "tool":
                yield node
                break


def check_tool_registrar(label, source):
    """One canonical signature so discovery can call every registrar alike."""
    tree, error = _parse(label, source)
    if error:
        return [error]

    registrars = [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and TOOL_REGISTRAR.match(n.name)
    ]
    if not registrars:
        return [
            "{}: no register_*_tools function -- discovery will treat this as a "
            "helper module and none of its tools will be registered.".format(label)
        ]
    if len(registrars) > 1:
        return [
            "{}: expected one register_*_tools function, found {}".format(
                label, [r.name for r in registrars]
            )
        ]
    args = [a.arg for a in registrars[0].args.args]
    if args != CANONICAL_TOOL_REGISTRAR:
        return [
            "{}: registrar must be (mcp, revit_get, revit_post, "
            "revit_image=None), found {}".format(label, args)
        ]
    return []


def check_tools(label, source):
    """Signature and docstring rules for every @mcp.tool() function."""
    tree, error = _parse(label, source)
    if error:
        return [error]

    violations = []
    found_any = False
    for node in _tool_functions(tree):
        found_any = True
        where = "{}::{}".format(label, node.name)

        if not isinstance(node, ast.AsyncFunctionDef):
            violations.append("{}: tool functions must be `async def`".format(where))

        returns = node.returns
        if returns is None or getattr(returns, "id", None) != "str":
            violations.append("{}: must be annotated `-> str`".format(where))

        args = [a.arg for a in node.args.args]
        if not args:
            violations.append("{}: takes no parameters".format(where))
        elif args[-1] != "ctx":
            violations.append(
                "{}: `ctx` must be the last parameter, found order {}".format(
                    where, args
                )
            )

        doc = ast.get_docstring(node)
        if not doc:
            violations.append(
                "{}: has no docstring. The docstring IS the API contract -- it "
                "is the only thing the model sees before calling.".format(where)
            )
            continue
        if "Args:" not in doc:
            violations.append(
                "{}: docstring needs an `Args:` block describing every "
                "parameter, including ctx".format(where)
            )
            continue
        args_block = doc.split("Args:", 1)[-1]
        missing = [a for a in args if a not in args_block]
        if missing:
            violations.append(
                "{}: these parameters are missing from the Args: block: "
                "{}".format(where, missing)
            )

    if not found_any:
        violations.append("{}: defines no @mcp.tool() functions".format(label))
    return violations


# --------------------------------------------------------------------------
# whole-package convenience, used by the kit and by intake
# --------------------------------------------------------------------------

def check_route_module(label, source):
    return (
        check_encoding_cookie(label, source)
        + check_ironpython_dialect(label, source)
        + check_element_id(label, source)
        + check_route_registrar(label, source)
    )


def check_tool_module(label, source):
    return (
        check_encoding_cookie(label, source)
        + check_tool_registrar(label, source)
        + check_tools(label, source)
    )


def check_package(domain, route_source, tool_source):
    """All violations for one contributed capability."""
    return (
        check_route_module("revit_mcp/{}.py".format(domain), route_source)
        + check_tool_module("tools/{}_tools.py".format(domain), tool_source)
    )
