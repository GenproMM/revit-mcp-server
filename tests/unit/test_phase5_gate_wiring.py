# -*- coding: utf-8 -*-
"""Closed by default (Phase 5, D-01): every non-GET route opens with the shared-secret and
integrity gate unless it is one of the eight open POST reads (D-02, Phase 7 D-09). Source-only; needs no Revit.

The route inventory is read with ``ast`` from the real ``revit_mcp/`` modules (they cannot be
imported without pyRevit), so a route added tomorrow is covered the day it is written. The
open list lives in three places on purpose: ``revit_mcp/trust.py`` (what the extension uses),
``scripts/conventions.py`` (what the repository suite, the contributor kit and package intake
check) and the literal ``D02_OPEN`` below. Opening a route means editing all three.
"""

import ast

import pytest

from inventory_support import (
    ACTIVE_READ, FILE_PREVIEW, MUTATION_PRIMITIVES, REGISTRY_READ, ROUTE_CLASSES, GUARDED,
    PREFLIGHT_READ,
    call_name, parse_revit_module, reachable_calls, revit_mcp_modules, route_inventory)
from revit_mcp import trust

GATE = "gate_or_response"
STRIP = "strip_envelope"
ALLOWED_SECURITY_NAMES = frozenset((GATE, STRIP, "status_block"))

# D-02: the only POST routes that read and are never refused. Written out literally so a change
# of trust.OPEN_POST_READ_ROUTES alone cannot pass.
D02_OPEN = frozenset((
    "/document_summary/",
    "/document_levels/",
    "/model_worksets/",
    "/material_quantities/",
    "/clash_check/",
    "/ai_filter/",
    "/list_category_parameters/",
    "/mutation_preflight/",  # Phase 7 preflight read, D-09.
))

# D-03: state changes, file writes, code execution and process-level opens. Always gated.
D03_BOUNDARY = frozenset((
    "/activate_document/",
    "/set_active_view/",
    "/open_model/",
    "/export_document/",
    "/export_ifc/",
    "/save_document/",
    "/link_file/",
    "/execute_code/",
))

OPEN_READ_CLASSES = frozenset((ACTIVE_READ, REGISTRY_READ, FILE_PREVIEW, PREFLIGHT_READ))

ROUTES = route_inventory()
ROUTE_BY_KEY = {route.key: route for route in ROUTES}


def _is_get(route):
    return bool(route.methods) and all(m in ("GET", "HEAD") for m in route.methods)


NON_GET = [route for route in ROUTES if not _is_get(route)]
GET_ROUTES = [route for route in ROUTES if _is_get(route)]
NON_GET_KEYS = frozenset(route.key for route in NON_GET)
GATED_KEYS = NON_GET_KEYS - D02_OPEN


def _body(function):
    statements = list(function.body)
    if statements and isinstance(statements[0], ast.Expr) \
            and isinstance(getattr(statements[0], "value", None), ast.Constant) \
            and isinstance(statements[0].value.value, str):
        statements = statements[1:]
    return statements


def _calls_by_name(route, name):
    return [c for c in ast.walk(route.node) if isinstance(c, ast.Call) and call_name(c) == name]


def _gate_statements(route):
    """(assignment, if-return) of the gated preamble, asserting its exact shape."""
    statements = _body(route.node)
    first, second = statements[0], statements[1]
    assert isinstance(first, ast.Assign), "{} does not open with the gate assignment".format(route.key)
    assert len(first.targets) == 1 and isinstance(first.targets[0], ast.Name)
    name = first.targets[0].id
    call = first.value
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == GATE, (
        "{} first statement is not {}(request)".format(route.key, GATE))
    assert len(call.args) == 1 and isinstance(call.args[0], ast.Name) \
        and call.args[0].id == "request" and not call.keywords
    assert isinstance(second, ast.If), "{} gate is not followed by its refusal return".format(route.key)
    test = second.test
    assert isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == name
    assert len(test.ops) == 1 and isinstance(test.ops[0], ast.IsNot)
    assert len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant) \
        and test.comparators[0].value is None
    assert len(second.body) == 1 and isinstance(second.body[0], ast.Return)
    assert isinstance(second.body[0].value, ast.Name) and second.body[0].value.id == name
    assert not second.orelse
    return first, second


def _strip_statement(route):
    first = _body(route.node)[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call), (
        "{} does not open with {}(request)".format(route.key, STRIP))
    call = first.value
    assert isinstance(call.func, ast.Name) and call.func.id == STRIP
    assert len(call.args) == 1 and isinstance(call.args[0], ast.Name) \
        and call.args[0].id == "request" and not call.keywords
    return first


# --------------------------------------------------------------- the pinned inventory

def test_the_open_list_in_trust_equals_the_eight_d02_keys():
    assert trust.OPEN_POST_READ_ROUTES == D02_OPEN
    assert len(D02_OPEN) == 8


def test_the_measured_route_counts_are_pinned():
    assert len(ROUTES) == 57
    assert len(NON_GET) == 42
    assert len(GET_ROUTES) == 15
    assert len(GATED_KEYS) == 34
    assert len(NON_GET_KEYS & D02_OPEN) == 8
    assert D02_OPEN <= NON_GET_KEYS


def test_every_route_declares_its_methods_literally():
    for route in ROUTES:
        assert route.methods, "{} has no literal methods list".format(route.key)


# ------------------------------------------------------------ closed by default (D-01)

@pytest.mark.parametrize("route", NON_GET, ids=lambda r: r.key)
def test_a_non_get_route_opens_with_the_gate_or_the_open_read_strip(route):
    assert "request" in route.args, route.args
    if route.key in D02_OPEN:
        first = _strip_statement(route)
    else:
        first, _ = _gate_statements(route)
    # No call of any kind may precede the first statement.
    for statement in route.node.body:
        for call in ast.walk(statement):
            if isinstance(call, ast.Call):
                assert call.lineno >= first.lineno, (route.key, call.lineno, first.lineno)


def test_the_routes_that_strip_are_exactly_the_open_list():
    stripping = {r.key for r in NON_GET + GET_ROUTES if _calls_by_name(r, STRIP)}
    assert stripping == D02_OPEN


def test_the_routes_that_gate_are_exactly_the_non_get_routes_off_the_open_list():
    gating = {r.key for r in NON_GET + GET_ROUTES if _calls_by_name(r, GATE)}
    assert gating == GATED_KEYS


def test_an_open_route_never_gates_and_a_gated_route_never_only_strips():
    for route in NON_GET:
        if route.key in D02_OPEN:
            assert not _calls_by_name(route, GATE), route.key
        else:
            assert not _calls_by_name(route, STRIP), route.key


# --------------------------------------------------------------- reads stay open (SEC-05)

@pytest.mark.parametrize("route", GET_ROUTES, ids=lambda r: r.key)
def test_a_get_route_neither_gates_nor_strips(route):
    reached = reachable_calls(route)
    assert GATE not in reached and STRIP not in reached, route.key


# ----------------------------------------------------------- the open set is reads only

@pytest.mark.parametrize("key", sorted(D02_OPEN))
def test_an_open_read_is_classified_as_a_read_and_reaches_no_mutation(key):
    assert ROUTE_CLASSES[key] in OPEN_READ_CLASSES, (key, ROUTE_CLASSES[key])
    reached = reachable_calls(ROUTE_BY_KEY[key])
    assert not reached & MUTATION_PRIMITIVES, (key, sorted(reached & MUTATION_PRIMITIVES))
    assert "SetElementIds" not in reached, key


def test_the_boundary_routes_are_gated_never_open():
    assert D03_BOUNDARY <= GATED_KEYS
    assert not D03_BOUNDARY & D02_OPEN
    assert len(D03_BOUNDARY) == 8


# --------------------------------------------------------------- order inside a handler

@pytest.mark.parametrize("key", sorted(k for k, v in ROUTE_CLASSES.items() if v == GUARDED))
def test_the_gate_precedes_the_document_guard_of_every_guarded_mutation(key):
    route = ROUTE_BY_KEY[key]
    gate, _ = _gate_statements(route)
    guard = [s for s in _body(route.node)
             if isinstance(s, ast.Assign) and isinstance(s.value, ast.Call)
             and call_name(s.value) == "mutation_document_or_response"]
    assert guard, key
    assert gate.lineno < guard[0].lineno, key


# ------------------------------------------------------------------------- the imports

def _security_imports(tree):
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[-1] == "security"]


def _imports_security_module_by_other_means(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[-1] == "security" for a in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
            if any(a.name == "security" for a in node.names):
                return True
    return False


GATE_MODULES = sorted({route.module for route in NON_GET})


@pytest.mark.parametrize("module", GATE_MODULES)
def test_a_module_with_gated_or_open_routes_imports_security_relatively_and_exactly(module):
    tree = parse_revit_module(module)
    imports = _security_imports(tree)
    assert imports, "{} imports nothing from security".format(module)
    for node in imports:
        assert node.level == 1 and node.module == "security", (
            "{} imports security by a flat or absolute name".format(module))
    imported = {alias.name for node in imports for alias in node.names}
    used = set()
    for call in ast.walk(tree):
        if isinstance(call, ast.Call) and call_name(call) in (GATE, STRIP):
            used.add(call_name(call))
    assert imported == used, (module, sorted(imported), sorted(used))
    assert not _imports_security_module_by_other_means(tree), module


@pytest.mark.parametrize("module", [m for m in revit_mcp_modules() if m != "security"])
def test_no_module_imports_a_security_name_outside_the_allow_list(module):
    tree = parse_revit_module(module)
    for node in _security_imports(tree):
        assert node.level == 1 and node.module == "security", module
        names = {alias.name for alias in node.names}
        assert names <= ALLOWED_SECURITY_NAMES, (module, sorted(names - ALLOWED_SECURITY_NAMES))
    assert not _imports_security_module_by_other_means(tree), module
