# -*- coding: utf-8 -*-
r"""Static check for D-06: does an extension tree ignore an extra _mcp key in a POST body?

Phase 5 puts the shared secret into every POST body under the reserved ``_mcp`` key.
The payload (the MCP server half) is published before the extension (D-05), so for a
while the NEW bridge talks to an OLD extension. That is safe only if no old handler
iterates, copies, echoes or forwards its parsed body, because then the extra key is
simply never looked at. This tool proves that statically, and it reads the route
modules as source only: nothing is imported, nothing is executed, nothing is written.

For every function that binds ``x = parse_request_data(<something>.data)`` (or an
``... or {}`` / conditional form of it) the tool follows the name and reports
ENVELOPE_SUSPECT for any use other than a read:

    allowed   data.get(...)   data["k"]   "k" in data   any comparison
              isinstance(data, ...)   a truthiness test (if / while / not / and / or)
    suspect   everything else: iteration, .items() / .keys() / .values() / .copy(),
              dict(data), list(data), len(data), json.dumps(data), str(data),
              "{}".format(data), f(**data), make_response(data=data), helper(data),
              a comprehension over it, ``return data``

A later assignment of the name to something else ends the tracking, so a reply dict
that reuses the name ``data`` is not a finding. The tool never prints a source line
or a body value, only the module label, the line number and a short reason.

Run it against the extension that is on the main share BEFORE publishing the payload:

    python scripts\scan_envelope_tolerance.py --dir "\\<share>\ext\revit-mcp-server.extension\revit_mcp"

or against a git revision of this repository (the pre-phase tree is c187004):

    python scripts\scan_envelope_tolerance.py --git-rev c187004 [--repo <checkout>]

Output: one ``ENVELOPE_TOLERANT <module>`` or ``ENVELOPE_SUSPECT <module>:<line> <reason>``
line per finding, then ``ENVELOPE_SCAN_OK files=<n>`` or ``ENVELOPE_SCAN_SUSPECT
findings=<k>``. Exit 0 only when nothing is suspect, 1 on a suspect, 2 on a usage error
or an unreadable input.

This is the STATIC half of the D-06 proof. A clean scan does not exercise Revit: the
payload-first rehearsal on the pilot share (the plan 05-10 runbook) is the live half,
and a suspect here is a blocker for the payload-first order that goes back to the user.

Runs under pyRevit's CPython on the build server: Python 3.8 grammar, standard library
only, no annotations.
"""

import argparse
import ast
import os
import subprocess
import sys

PARSER_NAME = "parse_request_data"
SUSPECT = "ENVELOPE_SUSPECT"
TOLERANT = "ENVELOPE_TOLERANT"

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


# ----------------------------------------------------------------------- classification


def _parent_map(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _is_parser_call(node):
    """True for a call to parse_request_data(...), bare or as an attribute."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == PARSER_NAME
    if isinstance(func, ast.Attribute):
        return func.attr == PARSER_NAME
    return False


def _is_body_parse(node):
    """parse_request_data(<something>.data): the parse of a request body."""
    return (
        _is_parser_call(node)
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Attribute)
        and node.args[0].attr == "data"
    )


def _binds_parsed_body(value):
    """True when an assigned value is (or may be) the parsed request body.

    Only the parse of a request's own `.data` counts. A helper that parses some other
    value (trust.split_envelope, which strips the envelope on purpose) is not a route
    handler's body and is out of this check's scope.
    """
    if _is_body_parse(value):
        return True
    if isinstance(value, ast.BoolOp):
        return any(_binds_parsed_body(item) for item in value.values)
    if isinstance(value, ast.IfExp):
        return _binds_parsed_body(value.body) or _binds_parsed_body(value.orelse)
    return False


def _in_truth_context(node, parents):
    """True when only the truthiness of node is used, never its value."""
    parent = parents.get(node)
    if parent is None:
        return False
    if isinstance(parent, (ast.If, ast.While, ast.IfExp, ast.Assert)) and parent.test is node:
        return True
    if isinstance(parent, ast.comprehension) and any(item is node for item in parent.ifs):
        return True
    if isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.Not):
        return True
    if isinstance(parent, ast.BoolOp):
        # `a or b` evaluates to one of its operands, so an operand is only a
        # truthiness test when the whole expression is one.
        return _in_truth_context(parent, parents)
    return False


def _is_request_data(node):
    """request.data, as a read."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "data"
        and isinstance(node.value, ast.Name)
        and node.value.id == "request"
        and isinstance(node.ctx, ast.Load)
    )


def _raw_body_findings(label, tree, parents):
    """request.data reads that are neither parse_request_data's argument nor a truthiness test."""
    found = set()
    for node in ast.walk(tree):
        if not _is_request_data(node):
            continue
        parent = parents.get(node)
        if _is_parser_call(parent) and any(arg is node for arg in parent.args):
            continue
        if _in_truth_context(node, parents):
            continue
        found.add((label, node.lineno, "raw request.data read outside parse_request_data"))
    return found


def _call_name(call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return "a call"


def _suspect_reason(node, parents):
    """None when the use of a tracked name is a read, else a short reason."""
    parent = parents.get(node)
    grand = parents.get(parent)

    if isinstance(parent, ast.Attribute) and parent.value is node:
        if parent.attr == "get" and isinstance(grand, ast.Call) and grand.func is parent:
            return None
        return "attribute {} used".format(parent.attr)
    if isinstance(parent, ast.Subscript) and parent.value is node:
        return None
    if isinstance(parent, ast.Compare):
        return None
    if (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Name)
        and parent.func.id == "isinstance"
        and any(arg is node for arg in parent.args)
    ):
        return None
    if _in_truth_context(node, parents):
        return None

    if isinstance(parent, ast.For) and parent.iter is node:
        return "iterated"
    if isinstance(parent, ast.comprehension) and parent.iter is node:
        return "iterated"
    if isinstance(parent, ast.Call):
        return "passed to {}()".format(_call_name(parent))
    if isinstance(parent, ast.keyword) and isinstance(grand, ast.Call):
        if parent.arg is None:
            return "unpacked with ** into {}()".format(_call_name(grand))
        return "passed to {}".format(_call_name(grand))
    if isinstance(parent, ast.Starred):
        return "unpacked with *"
    if isinstance(parent, ast.Return):
        return "returned"
    if isinstance(parent, ast.Assign):
        return "assigned to another name"
    if isinstance(parent, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
        return "stored in a container"
    if isinstance(parent, ast.FormattedValue):
        return "formatted into a string"
    return "used as {}".format(type(parent).__name__ if parent is not None else "an expression")


# ---------------------------------------------------------------------------- scanning


class _Flow(object):
    """Walks one tree statement by statement, tracking which names hold the body.

    The state is the set of tracked names at a point. A branch that rebinds a name
    only ends the tracking on that path; after the branches meet, a name stays
    tracked if any path left it tracked, because a missed use is the unsafe error.
    """

    def __init__(self, label, parents):
        self.label = label
        self.parents = parents
        self.findings = set()

    # expressions -------------------------------------------------------------

    def scan(self, node, state):
        if node is None:
            return
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Name)
                and isinstance(sub.ctx, ast.Load)
                and sub.id in state
            ):
                reason = _suspect_reason(sub, self.parents)
                if reason is not None:
                    self.findings.add((self.label, sub.lineno, reason))

    # targets -----------------------------------------------------------------

    def _target_names(self, target):
        if isinstance(target, ast.Name):
            return [target.id]
        if isinstance(target, (ast.Tuple, ast.List)):
            names = []
            for item in target.elts:
                names.extend(self._target_names(item))
            return names
        if isinstance(target, ast.Starred):
            return self._target_names(target.value)
        return []

    def _scan_compound_target(self, target, state):
        # data["k"] = v and data.attr = v read the name without rebinding it.
        if not isinstance(target, (ast.Name, ast.Tuple, ast.List, ast.Starred)):
            self.scan(target, state)

    # statements --------------------------------------------------------------

    def visit_block(self, statements, state):
        for statement in statements:
            state = self.visit(statement, state)
        return state

    def visit(self, node, state):
        if isinstance(node, ast.Assign):
            self.scan(node.value, state)
            binds = _binds_parsed_body(node.value)
            after = set(state)
            for target in node.targets:
                self._scan_compound_target(target, state)
                for name in self._target_names(target):
                    if binds and isinstance(target, ast.Name):
                        after.add(name)
                    else:
                        after.discard(name)
            return after

        if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            self.scan(getattr(node, "value", None), state)
            self._scan_compound_target(node.target, state)
            after = set(state)
            for name in self._target_names(node.target):
                after.discard(name)
            return after

        if isinstance(node, ast.If):
            self.scan(node.test, state)
            left = self.visit_block(node.body, set(state))
            right = self.visit_block(node.orelse, set(state))
            return left | right

        if isinstance(node, (ast.For, ast.AsyncFor)):
            self.scan(node.iter, state)
            inner = set(state)
            for name in self._target_names(node.target):
                inner.discard(name)
            after_body = self.visit_block(node.body, inner)
            after_else = self.visit_block(node.orelse, set(state) | after_body)
            return set(state) | after_body | after_else

        if isinstance(node, ast.While):
            self.scan(node.test, state)
            after_body = self.visit_block(node.body, set(state))
            after_else = self.visit_block(node.orelse, set(state) | after_body)
            return set(state) | after_body | after_else

        if isinstance(node, ast.Try):
            after_body = self.visit_block(node.body, set(state))
            merged = set(state) | after_body
            for handler in node.handlers:
                self.scan(handler.type, merged)
                merged |= self.visit_block(handler.body, set(state) | after_body)
            merged |= self.visit_block(node.orelse, set(after_body))
            return self.visit_block(node.finalbody, merged)

        if isinstance(node, (ast.With, ast.AsyncWith)):
            inner = set(state)
            for item in node.items:
                self.scan(item.context_expr, state)
                if item.optional_vars is not None:
                    for name in self._target_names(item.optional_vars):
                        inner.discard(name)
            return self.visit_block(node.body, inner)

        if isinstance(node, _FUNCTIONS):
            for decorator in node.decorator_list:
                self.scan(decorator, state)
            inner = set(state)
            args = node.args
            names = [a.arg for a in args.args] + [a.arg for a in args.kwonlyargs]
            names += [a.arg for a in getattr(args, "posonlyargs", [])]
            if args.vararg is not None:
                names.append(args.vararg.arg)
            if args.kwarg is not None:
                names.append(args.kwarg.arg)
            for name in names:
                inner.discard(name)
            # A nested handler sees the enclosing names as they are at its definition.
            self.visit_block(node.body, inner)
            after = set(state)
            after.discard(node.name)
            return after

        if isinstance(node, ast.ClassDef):
            self.visit_block(node.body, set(state))
            after = set(state)
            after.discard(node.name)
            return after

        # Return, Expr, Raise, Delete, Assert, Import ... : scan their expressions.
        self.scan(node, state)
        return state


def scan_source(label, source):
    """Return [(label, line, reason)] for every non-read use of a parsed body.

    An unparsable module is itself a finding: tolerance cannot be proven for it.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        return [(label, getattr(exc, "lineno", None) or 1, "source does not parse")]
    parents = _parent_map(tree)
    flow = _Flow(label, parents)
    # Every function body is analysed from an empty state, so a handler nested in a
    # register_*_routes function is found whatever its depth. The enclosing walk also
    # reaches it with the outer state; the findings set merges the duplicates.
    for node in ast.walk(tree):
        if isinstance(node, _FUNCTIONS):
            flow.visit_block(node.body, set())
    found = flow.findings | _raw_body_findings(label, tree, parents)
    return sorted(found, key=lambda item: (item[1], item[2]))


# ------------------------------------------------------------------------------ inputs


class ScanError(Exception):
    """An input could not be read; main() prints it and returns 2."""


def _decode(raw):
    return raw.decode("utf-8-sig")


def scan_git_rev(repo, rev):
    """Scan every revit_mcp/*.py of a git revision. Returns {label: [findings]}."""
    if not rev or rev.startswith("-"):
        raise ScanError("not a usable git revision: {!r}".format(rev))
    try:
        listing = subprocess.run(
            ["git", "-C", repo, "ls-tree", "-z", "--name-only", rev, "--", "revit_mcp/"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ScanError("cannot run git: {}".format(exc))
    if listing.returncode != 0:
        raise ScanError("git ls-tree failed for revision {}".format(rev))
    paths = sorted(
        item.decode("utf-8")
        for item in listing.stdout.split(b"\0")
        if item.endswith(b".py")
    )
    if not paths:
        raise ScanError("revision {} has no revit_mcp/*.py".format(rev))
    results = {}
    for path in paths:
        shown = subprocess.run(
            ["git", "-C", repo, "show", "{}:{}".format(rev, path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if shown.returncode != 0:
            raise ScanError("git show failed for {}:{}".format(rev, path))
        try:
            source = _decode(shown.stdout)
        except UnicodeDecodeError:
            raise ScanError("{} is not UTF-8".format(path))
        results[path] = scan_source(path, source)
    return results


def scan_directory(path):
    """Scan every *.py under a directory (a revit_mcp folder). Returns {label: [findings]}.

    Labels are paths relative to the directory with forward slashes. __pycache__ is
    skipped; nothing is written and nothing is imported.
    """
    if not os.path.isdir(path):
        raise ScanError("not a directory: {}".format(path))
    results = {}
    for folder, dirs, names in os.walk(path):
        dirs[:] = sorted(name for name in dirs if name != "__pycache__")
        for name in sorted(names):
            if not name.endswith(".py"):
                continue
            full = os.path.join(folder, name)
            label = os.path.relpath(full, path).replace(os.sep, "/")
            try:
                with open(full, "rb") as handle:
                    source = _decode(handle.read())
            except (IOError, OSError) as exc:
                raise ScanError("cannot read {}: {}".format(label, exc))
            except UnicodeDecodeError:
                raise ScanError("{} is not UTF-8".format(label))
            results[label] = scan_source(label, source)
    if not results:
        raise ScanError("no .py files under {}".format(path))
    return results


# ------------------------------------------------------------------------------- main


def _report(results):
    findings = 0
    for label in sorted(results):
        items = results[label]
        if not items:
            print("{} {}".format(TOLERANT, label))
            continue
        for _, line, reason in sorted(items, key=lambda item: (item[1], item[2])):
            print("{} {}:{} {}".format(SUSPECT, label, line, reason))
            findings += 1
    if findings:
        print("ENVELOPE_SCAN_SUSPECT findings={}".format(findings))
        return 1
    print("ENVELOPE_SCAN_OK files={}".format(len(results)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Static D-06 check: does an extension tree tolerate the _mcp key "
        "in every POST body? Reads source only and writes nothing."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--dir",
        help="scan every *.py in this folder, for example the extension's revit_mcp "
        "folder on the main share",
    )
    source.add_argument(
        "--git-rev",
        help="scan revit_mcp/*.py of this git revision (the pre-phase tree is c187004)",
    )
    parser.add_argument(
        "--repo",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="repository for --git-rev (default: the parent of this script's directory)",
    )
    args = _parse(parser, argv)
    if args is None:
        return 2
    try:
        if args.dir:
            results = scan_directory(args.dir)
        else:
            results = scan_git_rev(args.repo, args.git_rev)
    except ScanError as exc:
        print("ERROR: {}".format(exc))
        return 2
    return _report(results)


def _parse(parser, argv):
    try:
        return parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code in (0, None):
            raise
        return None


if __name__ == "__main__":
    sys.exit(main())
