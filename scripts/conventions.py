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

Checks over a Revit-half route module (composed by check_route_module):
encoding cookie, IronPython 3 dialect (f-strings, async, flat imports),
ElementId helpers, request parsing, commit_and_report, kept swallower, the one
register_*_routes registrar, and check_route_gate (Phase 5 D-01): every non-GET
route opens with the shared-secret gate unless it is one of the open reads.
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
# registry` does not depend on that. identity, trust, integrity and security
# are the Phase 2 and Phase 5 siblings; a flat import of the security module in
# particular would load a second copy with its own state and no secret.
LOCAL_MODULES = {"utils", "textutils", "registry", "revit_mcp",
                 "identity", "trust", "integrity", "security", "lookup", "permits"}

# Phase 5 D-01/D-02: the gate a route opens with, the strip an open read opens
# with, and the only names a route module may take from revit_mcp/security.py.
GATE_FUNCTION = "gate_or_response"
STRIP_FUNCTION = "strip_envelope"
SECURITY_IMPORTS = frozenset((GATE_FUNCTION, STRIP_FUNCTION, "status_block"))

# The eight POST routes that only read and are never gated (D-02, Phase 7 D-09). This mirrors
# OPEN_POST_READ_ROUTES in revit_mcp/trust.py because the contributor kit cannot
# import the repository; tests/unit/test_conventions.py pins the two equal, and
# tests/unit/test_phase5_gate_wiring.py pins both to a literal. Opening another
# route means editing all three.
OPEN_POST_READ_ROUTES = frozenset((
    "/document_summary/",
    "/document_levels/",
    "/model_worksets/",
    "/material_quantities/",
    "/clash_check/",
    "/ai_filter/",
    "/list_category_parameters/",
    "/mutation_preflight/",  # Phase 7 preflight read, D-09.
))

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
# compatibility idiom is allowed, in either of two guarded forms:
#     if bytes is str:  _TEXT_TYPE = unicode      # true only on Python 2
#     else:             _TEXT_TYPE = str
#     try:  _TEXT_TYPE = unicode
#     except NameError:  _TEXT_TYPE = str
# Prefer the first. pyRevit defines `unicode` in its IronPython 3 engine, so the
# NameError probe reports Python 2 there and every alias it sets is wrong.
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


def _guarded_by_python2_runtime_test(tree):
    """ids of nodes reachable only on Python 2, via an `if bytes is str:` test.

    The second sanctioned way to alias a Python-2 builtin, and the one
    textutils.py uses. `bytes is str` is true only on Python 2, so `unicode`
    inside that branch is unreachable on IronPython 3 -- the same guarantee
    `except NameError` gives, without depending on the name being absent.

    That distinction is why this form has to be allowed. pyRevit injects
    `unicode` into its IronPython 3 engine as an alias of `str`, so the
    NameError probe does not raise there and reports Python 2 on a Python 3
    runtime; the type-identity test is unfoolable. Both `else` and `elif`
    bodies count, since the Python 3 form lives there.
    """
    guarded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.Compare) and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Is)):
            continue
        names = {test.left.id} if isinstance(test.left, ast.Name) else set()
        right = test.comparators[0]
        if isinstance(right, ast.Name):
            names.add(right.id)
        if names != {"bytes", "str"}:
            continue
        for stmt in list(node.body) + list(node.orelse):
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
    nameable |= _guarded_by_python2_runtime_test(tree)
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
            "once under `if bytes is str:`, as revit_mcp/textutils.py does, or "
            "under `except NameError`."
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


def check_request_parsing(label, source):
    """A route must not parse request.data itself.

    pyRevit parses the body only for Content-Type: application/json, and that
    parse raises TypeError under IronPython 3 -- so the MCP client sends
    text/plain and the body reaches the handler unparsed, as bytes. The old
    idiom, `json.loads(request.data) if isinstance(request.data, str) else
    request.data`, then quietly yields bytes and the handler dies on .get().
    parse_request_data() accepts bytes, str and dict alike.
    """
    violations = []
    code = _blank_strings_and_comments(source)
    hits = [
        i + 1
        for i, line in enumerate(code.splitlines())
        if "json.loads(request.data)" in line
    ]
    if hits:
        violations.append(
            "{}: use parse_request_data(request.data) from .utils instead of "
            "parsing the body by hand -- on IronPython 3 the body arrives as "
            "bytes and json.loads rejects it. Lines: {}".format(label, hits)
        )
    return violations


# Phase 4 D-02 -- every Commit() goes through commit_and_report.
#
# Revit's Transaction.Commit() does not raise when the failure swallower vetoes
# the transaction; it returns TransactionStatus.RolledBack. A route that
# discards that return value answers "success" for an edit Revit threw away,
# and that is exactly what hid rollbacks on 26 sites until Phase 4. The only
# place a Commit() may be written is commit_and_report in revit_mcp/utils.py,
# which reads the status and hands it to finalize_outcome. Phase 6's audit log
# reads `outcome` from every mutating reply, so a bypass here is not a style
# problem: it makes the audit record wrong.
#
# The second check closes the other half of the same hole. commit_and_report
# can only report the failures Revit raised if it is given the swallower that
# collected them, and suppress_warnings() returns that swallower; a discarded
# result means outcome.revit_failures is silently always empty.

COMMIT_HELPER = "commit_and_report"
COMMIT_HELPER_HOME = "revit_mcp/utils.py"


def check_commit_goes_through_report(label, source):
    """No `.Commit` attribute in a revit_mcp module outside commit_and_report.

    Any attribute named Commit counts, whether it is called, compared
    (`ft.Commit() == Committed`) or bound (`commit = t.Commit`). Comments and
    string literals are not attributes, so a docstring that explains the rule
    is fine. The single exemption is the module-level `commit_and_report` in
    revit_mcp/utils.py and applies only there and only to that function.
    """
    tree, error = _parse(label, source)
    if error:
        return [error]

    exempt = set()
    if label.replace("\\", "/").endswith(COMMIT_HELPER_HOME):
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == COMMIT_HELPER:
                for child in ast.walk(node):
                    exempt.add(id(child))

    lines = sorted({
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and n.attr == "Commit" and id(n) not in exempt
    })
    if not lines:
        return []
    return [
        "{}: Commit() outside commit_and_report at lines {}: use swallower = "
        "suppress_warnings(t), commit_result = commit_and_report(t, swallower) "
        "and finalize_outcome(...) (Phase 4 D-02)".format(label, lines)
    ]


def _is_none_constant(node):
    return isinstance(node, ast.Constant) and node.value is None


def check_swallower_is_kept(label, source):
    """suppress_warnings() must be assigned and commit_and_report must get it."""
    tree, error = _parse(label, source)
    if error:
        return [error]

    discarded = sorted({
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "id", None) == "suppress_warnings"
    })

    unswallowed = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == COMMIT_HELPER):
            continue
        if any(isinstance(a, ast.Starred) for a in node.args):
            continue  # arguments are not statically known
        if len(node.args) >= 2:
            second = node.args[1]
        else:
            keyword = [k for k in node.keywords if k.arg == "swallower"]
            second = keyword[0].value if keyword else None
        if second is None or _is_none_constant(second):
            unswallowed.append(node.lineno)

    violations = []
    if discarded:
        violations.append(
            "{}: the result of suppress_warnings(...) is discarded at lines "
            "{}: keep it (swallower = suppress_warnings(t)) and pass it to "
            "commit_and_report, or outcome.revit_failures can never name what "
            "Revit rolled back for (Phase 4 D-02)".format(label, discarded)
        )
    if unswallowed:
        violations.append(
            "{}: commit_and_report needs the swallower as its second argument "
            "at lines {}: commit_and_report(t, swallower) (Phase 4 D-02)".format(
                label, sorted(set(unswallowed))
            )
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


# Phase 5 D-01 -- closed by default.
#
# Every non-GET route opens with
#     gate_refusal = gate_or_response(request)
#     if gate_refusal is not None:
#         return gate_refusal
# before it reads the body or touches the document, so a request without the
# shared secret never reaches Revit. The only exceptions are the seven open POST
# reads of D-02, which open with strip_envelope(request) instead: it removes the
# reserved key so the route's own parse does not see it, but it authenticates
# nothing. A GET route calls neither (SEC-05: reads stay open). The same rule is
# a sentinel over the real inventory in tests/unit/test_phase5_gate_wiring.py;
# this copy is what the kit and package intake run on a contributed module.

def _route_decorator(function):
    """The @api.route(...) call on a handler, or None."""
    for decorator in function.decorator_list:
        if (isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "route"):
            return decorator
    return None


def _route_path(decorator):
    """The literal path of a route with any <converter> or {param} tail removed."""
    if decorator.args and isinstance(decorator.args[0], ast.Constant) \
            and isinstance(decorator.args[0].value, str):
        return re.split(r"[<{]", decorator.args[0].value, maxsplit=1)[0]
    return "<non-literal path>"


def _route_is_get(decorator):
    """True only for a literal methods list holding nothing but GET and HEAD.

    A missing or non-literal `methods` is treated as non-GET: unknown means closed.
    """
    for keyword in decorator.keywords:
        if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple)):
            names = [e.value for e in keyword.value.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if len(names) != len(keyword.value.elts) or not names:
                return False
            return all(n.upper() in ("GET", "HEAD") for n in names)
    return False


def _handler_statements(function):
    statements = list(function.body)
    if (statements and isinstance(statements[0], ast.Expr)
            and isinstance(statements[0].value, ast.Constant)
            and isinstance(statements[0].value.value, str)):
        statements = statements[1:]
    return statements


def _is_request_call(node, name):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == name and len(node.args) == 1 and not node.keywords
            and isinstance(node.args[0], ast.Name) and node.args[0].id == "request")


def _opens_with_strip(statements):
    return bool(statements) and isinstance(statements[0], ast.Expr) \
        and _is_request_call(statements[0].value, STRIP_FUNCTION)


def _opens_with_gate(statements):
    """The two-statement preamble: assign the gate result, return it when not None."""
    if len(statements) < 2:
        return False
    first, second = statements[0], statements[1]
    if not (isinstance(first, ast.Assign) and len(first.targets) == 1
            and isinstance(first.targets[0], ast.Name)
            and _is_request_call(first.value, GATE_FUNCTION)):
        return False
    name = first.targets[0].id
    test = second.test if isinstance(second, ast.If) else None
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name) and test.left.id == name
        and len(test.ops) == 1 and isinstance(test.ops[0], ast.IsNot)
        and len(test.comparators) == 1 and _is_none_constant(test.comparators[0])
        and len(second.body) == 1 and isinstance(second.body[0], ast.Return)
        and isinstance(second.body[0].value, ast.Name) and second.body[0].value.id == name
        and not second.orelse
    )


def _calls_named(function, name):
    return [n for n in ast.walk(function)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name]


def _check_security_imports(label, tree):
    violations = []
    flat = []
    bad_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[-1] == "security" for a in node.names):
                flat.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            last = (node.module or "").split(".")[-1]
            if last == "security":
                if node.level != 1 or node.module != "security":
                    flat.append(node.lineno)
                else:
                    bad_names.extend(a.name for a in node.names
                                     if a.name not in SECURITY_IMPORTS)
            elif any(a.name == "security" for a in node.names):
                flat.append(node.lineno)
    if flat:
        violations.append(
            "{}: imports the security module by a flat or absolute name at lines {}; "
            "use from .security import ... (a second copy would carry no secret "
            "state)".format(label, sorted(set(flat))))
    for name in sorted(set(bad_names)):
        violations.append(
            "{}: imports {} from security; only gate_or_response, strip_envelope "
            "and status_block may be imported".format(label, name))
    return violations


def check_route_gate(label, source):
    """Every non-GET route opens with the gate; the open reads strip; GET routes do neither."""
    tree, error = _parse(label, source)
    if error:
        return [error]

    violations = _check_security_imports(label, tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        decorator = _route_decorator(node)
        if decorator is None:
            continue
        path = _route_path(decorator)
        where = "{}: route {} ({}, line {})".format(label, path, node.name, node.lineno)
        statements = _handler_statements(node)

        if _route_is_get(decorator):
            if _calls_named(node, GATE_FUNCTION) or _calls_named(node, STRIP_FUNCTION):
                violations.append(
                    "{} is a GET route and must not call the gate or strip_envelope; "
                    "reads stay open (SEC-05)".format(where))
        elif path in OPEN_POST_READ_ROUTES:
            if not _opens_with_strip(statements) or _calls_named(node, GATE_FUNCTION):
                violations.append(
                    "{} is an open read and must open with strip_envelope(request), "
                    "never the gate (D-02)".format(where))
        else:
            if _calls_named(node, STRIP_FUNCTION):
                violations.append(
                    "{} is not an open read; strip_envelope does not authenticate "
                    "(D-01)".format(where))
            if not _opens_with_gate(statements):
                violations.append(
                    "{} must open with gate_refusal = gate_or_response(request) and "
                    "return it when it is not None, before any other statement "
                    "(D-01)".format(where))
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
        + check_request_parsing(label, source)
        + check_commit_goes_through_report(label, source)
        + check_swallower_is_kept(label, source)
        + check_route_registrar(label, source)
        + check_route_gate(label, source)
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
