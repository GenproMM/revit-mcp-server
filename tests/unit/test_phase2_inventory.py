# -*- coding: utf-8 -*-
"""Phase 2 exhaustive regression inventory (plan 02-17).

Every registered tool and every route handler of every domain is derived from the
real registrars (tools: run through ``tools.register_tools``; routes: the
``@api.route`` handlers inside each ``register_*_routes``, read as source because
``revit_mcp/`` cannot be imported without pyRevit) and checked against the phase
contract. There is no sample: a tool or route that appears without being
classified in ``inventory_support`` fails here until somebody classifies it.

Classification is by what a tool or route DOES, never by its HTTP method:
``/ai_filter/``, ``/material_quantities/``, ``/clash_check/`` and
``/list_category_parameters/`` are POST reads.

The named exceptions are exactly these, pinned as exact sets so the list cannot
grow silently:

* tools without ``target``: discover_revit_targets, get_revit_process_status and
  start_revit (local process tools; discovery-driven, 02-19);
* open_model (process-level file open; actual-opened-document identity on the reply);
* activate_document (the explicit G4 activation, saved non-workshared files only);
* execute_revit_code and /execute_code/ (the D-15 trusted arbitrary-code exception:
  available, forwards ``target``, no ``document``, honest label, never "confined");
* routes that pyRevit runs on its HTTP thread because they declare none of
  uiapp/uidoc/doc: /model_info/ and /status/ (02-04 follow-up concerns, not changed here);
* tools that pre-render their success text (list_documents, activate_document,
  read_document_summary, read_document_levels; get_revit_view returns an Image).

Offline evidence only. Nothing here touches Revit; the live gates are plan 02-18.
"""

import ast
import asyncio
import inspect
import os
import re

import pytest

import tools as tools_package
from inventory_support import (
    ACTIVATE, ACTIVATION, ACTIVE_READ, ADDRESSED_READ, ALLOWED_ROUTE_CLASSES,
    API_CONTEXT_ARGUMENTS, D15, D15_ROUTE, DOCUMENT_SELECTOR, FILE_PREVIEW, FILE_READ, GUARDED,
    GUARDED_WITHOUT_TRANSACTION, HTTP_THREAD, HTTP_THREAD_ALLOWLIST, LOCAL, MUTATION,
    MUTATION_PRIMITIVES, NO_TARGET_BY_DESIGN, PROCESS_OPEN, PROCESS_OPEN_ROUTE,
    PROCESS_SELECTOR, READ, REGISTRY_LIST, REGISTRY_READ, REPO_ROOT, REVIT_MCP_DIR,
    ROUTE_CLASSES, STATUS, TOOLS_DIR, TOOL_CLASSES, call_name, manifest_names, minimal_kwargs,
    module_registrars, parse_revit_module, reachable_calls, register_everything,
    revit_mcp_modules, route_inventory, tool_transport_calls)

TOOLS = register_everything()[0]
ROUTES = route_inventory()
ROUTE_BY_KEY = {route.key: route for route in ROUTES}
MINIMAL = minimal_kwargs()
TRANSPORT_CALLS = tool_transport_calls()

REVIT_FACING = sorted(name for name, kind in TOOL_CLASSES.items() if kind != LOCAL)
GUARDED_ROUTES = sorted(route.key for route in ROUTES if ROUTE_CLASSES.get(route.key) == GUARDED)
GUARDED_TOOLS = sorted(name for name, kind in TOOL_CLASSES.items() if kind == MUTATION)


def run_tool(name, **kwargs):
    """Run one real tool on a fresh recording transport; returns (text, calls)."""
    tools, calls = register_everything()
    text = asyncio.run(tools[name](**dict(MINIMAL[name], **kwargs)))
    return text, calls


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# ===================================================================== discovery


def test_tool_discovery_registers_every_domain_and_only_utils_is_a_helper():
    register_everything()
    assert tools_package.FAILED == {}
    assert sorted(tools_package.SKIPPED) == ["utils"]


def test_discovered_tools_manifest_and_classification_are_the_same_set():
    discovered = set(TOOLS)
    manifest = set(manifest_names())
    classified = set(TOOL_CLASSES)
    assert discovered == manifest, (
        "registered but not in tool_manifest.txt: {}; in the manifest but not registered: {}"
        .format(sorted(discovered - manifest), sorted(manifest - discovered)))
    assert discovered == classified, (
        "a new tool must be classified in tests/unit/inventory_support.py (TOOL_CLASSES) before "
        "it can ship. Unclassified: {}. Classified but not registered: {}".format(
            sorted(discovered - classified), sorted(classified - discovered)))


def test_every_discovered_route_is_classified_and_no_classification_is_stale():
    found = {route.key for route in ROUTES}
    assert len(found) == len(ROUTES), "two handlers register the same route"
    classified = set(ROUTE_CLASSES)
    assert found == classified, (
        "a new route must be classified in tests/unit/inventory_support.py (ROUTE_CLASSES) "
        "before it can ship. Unclassified: {}. Classified but not registered: {}".format(
            sorted(found - classified), sorted(classified - found)))


def test_every_route_domain_with_handlers_exposes_a_registrar_startup_would_find():
    for name in revit_mcp_modules():
        tree = parse_revit_module(name)
        has_handlers = any(r.module == name for r in ROUTES)
        registrars = module_registrars(tree)
        assert len(registrars) <= 1, (name, [r.name for r in registrars])
        if has_handlers:
            assert registrars, "{} defines routes but no register_*_routes".format(name)


def test_every_tool_transport_call_addresses_a_route_that_exists_with_a_matching_method():
    addressed = {}
    for tool, rows in TRANSPORT_CALLS.items():
        for transport, key in rows:
            assert key is not None, "{} sends to a route that is not a literal path".format(tool)
            route = ROUTE_BY_KEY.get(key)
            assert route is not None, "{} addresses {} which no handler registers".format(tool, key)
            method = "POST" if transport == "revit_post" else "GET"
            assert method in route.methods, (tool, key, route.methods)
            addressed.setdefault(key, set()).add(tool)
    assert set(addressed) == set(ROUTE_BY_KEY), (
        "routes no tool addresses: {}".format(sorted(set(ROUTE_BY_KEY) - set(addressed))))


def test_every_registered_tool_is_in_the_source_scan_and_addresses_at_most_one_route():
    assert set(TRANSPORT_CALLS) == set(TOOLS)
    for tool, rows in TRANSPORT_CALLS.items():
        assert len({key for _, key in rows}) <= 1, (tool, rows)
        if TOOL_CLASSES[tool] != LOCAL:
            assert rows, "{} is Revit-facing but sends nothing".format(tool)


def test_each_tool_class_addresses_only_the_route_classes_it_may():
    for tool, kind in TOOL_CLASSES.items():
        for _, key in TRANSPORT_CALLS[tool]:
            assert ROUTE_CLASSES[key] in ALLOWED_ROUTE_CLASSES[kind], (
                "{} ({}) addresses {} classified {}".format(tool, kind, key, ROUTE_CLASSES[key]))


def test_the_mutation_tools_and_the_guarded_routes_are_the_same_set_one_to_one():
    addressed = sorted(key for tool in GUARDED_TOOLS for _, key in TRANSPORT_CALLS[tool])
    assert addressed == GUARDED_ROUTES, (
        "a guarded route without a mutation tool, or a mutation tool on an unguarded route: "
        "{} vs {}".format(addressed, GUARDED_ROUTES))
    assert len(set(addressed)) == len(addressed), "two mutation tools share one route"


def test_the_exact_set_of_routes_only_the_named_tools_address():
    owners = {}
    for tool, rows in TRANSPORT_CALLS.items():
        for _, key in rows:
            owners.setdefault(key, set()).add(tool)
    assert owners["/open_model/"] == {"open_model"}
    assert owners["/execute_code/"] == {"execute_revit_code"}
    assert owners["/activate_document/"] == {"activate_document"}
    assert owners["/status/"] == {"get_revit_status", "get_revit_process_status"}


def test_true_inventory_counts_are_recorded_for_the_docs_sweep():
    """Print the true current counts; CLAUDE.md still says 54 tools / 51 routes / 23 domains."""
    route_domains = sorted({route.module for route in ROUTES})
    registrar_modules = [n for n in revit_mcp_modules() if module_registrars(parse_revit_module(n))]
    assert route_domains == registrar_modules
    tool_domains = sorted(name for name in os.listdir(TOOLS_DIR) if name.endswith("_tools.py"))
    counts = {
        "tools": len(TOOLS),
        "revit_facing_tools": len(REVIT_FACING),
        "local_process_tools": len(TOOLS) - len(REVIT_FACING),
        "routes": len(ROUTES),
        "guarded_mutation_routes": len(GUARDED_ROUTES),
        "route_domains": len(route_domains),
        "tool_domains": len(tool_domains),
    }
    print("INVENTORY_COUNTS " + " ".join("{}={}".format(k, counts[k]) for k in sorted(counts)))
    assert counts["tools"] == len(manifest_names()) == len(TOOL_CLASSES)
    assert counts["routes"] == len(ROUTE_CLASSES)
    assert counts["tool_domains"] == len(tools_package.REGISTERED)


# ============================================================ tool-side contract


def _params(name):
    return list(inspect.signature(TOOLS[name]).parameters)


@pytest.mark.parametrize("name", sorted(TOOL_CLASSES))
def test_tool_signature_matches_its_class(name):
    kind = TOOL_CLASSES[name]
    params = inspect.signature(TOOLS[name]).parameters
    names = list(params)
    assert names[-1] == "ctx" and params["ctx"].default is None, names
    if kind == LOCAL:
        assert "target" not in names and "document" not in names, names
        return
    assert "target" in names and params["target"].default is None
    if kind == MUTATION:
        assert names[-3:] == ["target", "document", "ctx"], names
        assert params["document"].default is None
    elif kind in (ADDRESSED_READ, ACTIVATION):
        assert names == ["document", "target", "ctx"], names
        assert params["document"].default is inspect.Parameter.empty
    else:
        assert "document" not in names, names


def test_the_exact_set_of_tools_without_a_target_is_the_named_local_process_tools():
    without = {name for name in TOOLS if "target" not in _params(name)}
    assert without == set(NO_TARGET_BY_DESIGN), (
        "a Revit-facing tool must take `target`; only these local tools are exempt: {}".format(
            sorted(without ^ set(NO_TARGET_BY_DESIGN))))
    assert all(reason.strip() for reason in NO_TARGET_BY_DESIGN.values())
    assert {name for name, kind in TOOL_CLASSES.items() if kind == LOCAL} == set(NO_TARGET_BY_DESIGN)


def test_the_exact_set_of_tools_that_accept_a_document_is_mutations_plus_the_addressed_ones():
    with_document = {name for name in TOOLS if "document" in _params(name)}
    expected = {name for name, kind in TOOL_CLASSES.items()
                if kind in (MUTATION, ADDRESSED_READ, ACTIVATION)}
    assert with_document == expected


@pytest.mark.parametrize("name", sorted(TOOL_CLASSES))
def test_tool_docstring_is_the_api_contract(name):
    kind = TOOL_CLASSES[name]
    doc = TOOLS[name].__doc__ or ""
    assert "Args:" in doc, name
    args_block = doc.split("Args:", 1)[1]
    for argument in _params(name):
        assert re.search(r"^\s+{}:".format(argument), args_block, re.M), (name, argument)
    lowered = " ".join(doc.lower().split())
    if kind != LOCAL:
        assert "discover_revit_targets" in doc, name
    if kind == MUTATION:
        for phrase in ("list_documents", "activate_document", "412", "the only open document",
                       "several"):
            assert phrase in lowered, (name, phrase)
        for claim in ("switches to", "switch to that document", "retargets",
                      "activates it automatically", "activates the document automatically",
                      "makes it active"):
            assert claim not in lowered, (name, claim)


@pytest.mark.parametrize("name", sorted(TOOL_CLASSES))
def test_every_tool_has_minimal_arguments_or_is_a_local_tool(name):
    if TOOL_CLASSES[name] == LOCAL:
        return
    assert name in MINIMAL, (
        "tool {} is covered by no forwarding inventory: add its minimal arguments to "
        "inventory_support.minimal_kwargs()".format(name))


@pytest.mark.parametrize("name", REVIT_FACING)
def test_target_is_forwarded_as_a_transport_keyword_and_never_in_the_body(name):
    text, calls = run_tool(name, target=PROCESS_SELECTOR)
    assert isinstance(text, str)
    assert len(calls) >= 1
    for method, path, body, options in calls:
        assert options.get("target") == PROCESS_SELECTOR, (name, path, options)
        if method == "POST":
            assert "target" not in body
            assert "document" not in body or TOOL_CLASSES[name] in (ADDRESSED_READ, ACTIVATION)


@pytest.mark.parametrize("name", REVIT_FACING)
def test_nothing_extra_is_forwarded_when_no_selector_is_given(name):
    text, calls = run_tool(name)
    assert isinstance(text, str) and len(calls) >= 1
    for method, path, body, options in calls:
        assert options.get("target") is None, (name, options)
        if method == "POST" and TOOL_CLASSES[name] not in (ADDRESSED_READ, ACTIVATION):
            assert "target" not in body and "document" not in body


@pytest.mark.parametrize("name", GUARDED_TOOLS)
def test_a_mutation_forwards_the_document_in_the_post_body_beside_its_own_fields(name):
    text, calls = run_tool(name, document=DOCUMENT_SELECTOR, target=PROCESS_SELECTOR)
    assert len(calls) == 1
    method, path, body, options = calls[0]
    assert method == "POST"
    assert body["document"] == DOCUMENT_SELECTOR
    assert options.get("target") == PROCESS_SELECTOR and "target" not in body
    for key, value in MINIMAL[name].items():
        assert body[key] == value


@pytest.mark.parametrize("name", GUARDED_TOOLS)
@pytest.mark.parametrize("blank", ["", "   ", 7])
def test_a_mutation_refuses_a_blank_or_non_string_document_without_sending(name, blank):
    text, calls = run_tool(name, document=blank)
    assert calls == []
    assert "document" in text and "list_documents" in text


@pytest.mark.parametrize("name", sorted(n for n, k in TOOL_CLASSES.items()
                                        if k in (READ, STATUS, FILE_READ, PROCESS_OPEN, D15)))
def test_no_read_or_process_level_tool_offers_a_way_to_name_a_document(name):
    """A document cannot be expressed on them: a TypeError before any dispatch."""
    tools, calls = register_everything()
    with pytest.raises(TypeError):
        asyncio.run(tools[name](**dict(MINIMAL[name], document=DOCUMENT_SELECTOR)))
    assert calls == []


@pytest.mark.parametrize("name", sorted(n for n, k in TOOL_CLASSES.items()
                                        if k in (ADDRESSED_READ, ACTIVATION)))
def test_the_addressed_tools_send_their_required_document_and_the_target(name):
    text, calls = run_tool(name, target=PROCESS_SELECTOR)
    assert len(calls) == 1
    _, _, body, options = calls[0]
    assert body["document"] == DOCUMENT_SELECTOR and options["target"] == PROCESS_SELECTOR


def test_a_tool_module_never_imports_the_transport():
    offenders = []
    for filename in sorted(os.listdir(TOOLS_DIR)):
        if not filename.endswith(".py"):
            continue
        tree = ast.parse(source_of(os.path.join(TOOLS_DIR, filename)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "")] + [a.name for a in node.names]
            else:
                continue
            if any(n.split(".")[0] == "bridge" or n == "bridge" for n in names):
                offenders.append(filename)
    assert offenders == []


# ----------------------------------------------------- D-15 and process-level rows


def test_d15_execute_surfaces_are_registered_in_the_manifest_and_classified_as_the_exception():
    assert "execute_revit_code" in manifest_names() and "execute_revit_code" in TOOLS
    assert "/execute_code/" in ROUTE_BY_KEY
    assert TOOL_CLASSES["execute_revit_code"] == D15
    assert ROUTE_CLASSES["/execute_code/"] == D15_ROUTE
    assert "execute_revit_code" not in GUARDED_TOOLS and "/execute_code/" not in GUARDED_ROUTES
    assert [k for t, rows in TRANSPORT_CALLS.items() for _, k in rows
            if k == "/execute_code/"] == ["/execute_code/"]


def test_the_execute_tool_forwards_target_has_no_document_and_states_the_exception_honestly():
    assert _params("execute_revit_code") == ["code", "description", "target", "ctx"]
    text, calls = run_tool("execute_revit_code", target=PROCESS_SELECTOR)
    (method, path, body, options), = calls
    assert (method, path) == ("POST", "/execute_code/")
    assert options["target"] == PROCESS_SELECTOR
    assert set(body) == {"code", "description"}
    doc = " ".join(TOOLS["execute_revit_code"].__doc__.lower().split())
    assert "trusted arbitrary-code exception" in doc
    assert "no document guard" in doc and "no confinement" in doc
    assert "not confined" in doc
    assert "never names a changed document" in doc
    for claim in ("confined to the selected", "only the selected document", "guarded document",
                  "changed documents are listed"):
        assert claim not in doc


def test_the_execute_route_is_unguarded_stamps_only_scope_and_process_and_never_a_document():
    route = ROUTE_BY_KEY["/execute_code/"]
    assert route.name == "execute_code" and route.module == "code_execution"
    assert set(route.args) >= {"uiapp", "doc", "request"}
    names = {call_name(c) for c in route.calls_in()}
    assert "mutation_document_or_response" not in names
    assert "attribute_response" not in names
    assert "_stamp_exception" in names
    tree = route.tree
    stamp = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
             and n.name == "_stamp_exception"][0]
    keys = set()
    for node in ast.walk(stamp):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            index = node.slice
            keys.add(index.value if isinstance(index, ast.Constant) else None)
    assert keys == {"document_scope", "process_identity", "identity_error"}, keys
    notice = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "DOCUMENT_SCOPE_NOTICE" for t in n.targets)]
    assert len(notice) == 1
    text = notice[0].value.value.lower()
    assert "trusted arbitrary-code exception" in text and "no document guard" in text
    assert "not identified" in text or "not attributed" in text


def test_open_model_is_process_level_with_the_actual_opened_document_identity():
    assert _params("open_model")[-2:] == ["target", "ctx"] and "document" not in _params("open_model")
    route = ROUTE_BY_KEY["/open_model/"]
    names = {call_name(c) for c in route.calls_in()}
    assert "mutation_document_or_response" not in names
    assert "_stamp_process" in names
    opener = route.defs["_open_model"][0]
    inner = {call_name(c) for c in ast.walk(opener) if isinstance(c, ast.Call)}
    assert "_opened_document_descriptor" in inner, (
        "open_model must report the document Revit actually opened, not the requested path")


# ============================================================= route-side contract


def test_every_route_handler_declares_uiapp_uidoc_or_doc_except_the_two_known_http_thread_routes():
    """pyRevit runs a handler in the Revit API context only if it declares one of them (02-07)."""
    without = {route.key: (route.module, route.name, tuple(route.args))
               for route in ROUTES if not API_CONTEXT_ARGUMENTS & set(route.args)}
    assert without == HTTP_THREAD_ALLOWLIST, (
        "a third handler without uiapp/uidoc/doc would run on pyRevit's HTTP thread: {}"
        .format(sorted(set(without) ^ set(HTTP_THREAD_ALLOWLIST))))
    for key in HTTP_THREAD_ALLOWLIST:
        assert ROUTE_CLASSES[key] == HTTP_THREAD


def test_the_http_thread_allow_list_is_recorded_not_fixed_here():
    """02-17 must not change these two handlers; the declared signatures are pinned verbatim."""
    assert ROUTE_BY_KEY["/model_info/"].args == []
    assert ROUTE_BY_KEY["/status/"].args == ["verbose"]
    for key in ("/model_info/", "/status/"):
        assert ROUTE_BY_KEY[key].methods == ["GET"]


def _body(function):
    statements = list(function.body)
    if statements and isinstance(statements[0], ast.Expr) \
            and isinstance(getattr(statements[0], "value", None), ast.Constant) \
            and isinstance(statements[0].value.value, str):
        statements = statements[1:]
    return statements


@pytest.mark.parametrize("key", GUARDED_ROUTES)
def test_a_guarded_handler_calls_the_explicit_guard_first_and_attributes_every_reply(key):
    route = ROUTE_BY_KEY[key]
    assert {"uiapp", "request"} <= set(route.args), route.args
    statements = _body(route.node)
    first, second = statements[0], statements[1]
    # document, descriptor, refusal = mutation_document_or_response(request_document_selector(request), uiapp=uiapp)
    assert isinstance(first, ast.Assign) and isinstance(first.value, ast.Call)
    assert call_name(first.value) == "mutation_document_or_response"
    assert [e.id for e in first.targets[0].elts] == ["document", "descriptor", "refusal"]
    selector = first.value.args[0]
    assert isinstance(selector, ast.Call) and call_name(selector) == "request_document_selector"
    assert [a.id for a in selector.args] == ["request"]
    assert [(k.arg, k.value.id) for k in first.value.keywords] == [("uiapp", "uiapp")]
    # if refusal is not None: return refusal
    assert isinstance(second, ast.If)
    assert isinstance(second.test, ast.Compare) and second.test.left.id == "refusal"
    assert isinstance(second.test.ops[0], ast.IsNot)
    assert len(second.body) == 1 and isinstance(second.body[0], ast.Return)
    assert second.body[0].value.id == "refusal"
    # Nothing at all before the guard; the injected `doc` is never used by the handler.
    guard_line = first.lineno
    for statement in route.node.body:
        for call in ast.walk(statement):
            if isinstance(call, ast.Call):
                assert call.lineno >= guard_line, (key, call.lineno)
    for node in ast.walk(route.node):
        assert not (isinstance(node, ast.Name) and node.id == "doc"
                    and isinstance(node.ctx, ast.Load)), (key, "reads the injected doc")
    # The reply carries process identity and the ACTUAL document descriptor.
    attribution = [c for c in route.calls_in() if call_name(c) == "attribute_response"]
    assert attribution, key
    for call in attribution:
        assert [(k.arg, k.value.id) for k in call.keywords] == [("uiapp", "uiapp")]
        assert "descriptor" in ast.dump(call.args[1])
    # The handler itself opens no transaction and touches no document API.
    handler_names = {call_name(c) for c in route.calls_in()}
    assert not handler_names & {"Transaction", "TransactionGroup", "Start", "Commit"}, key


@pytest.mark.parametrize("module", sorted({ROUTE_BY_KEY[k].module for k in GUARDED_ROUTES}))
def test_a_guarded_module_imports_the_guard_relatively_from_identity(module):
    tree = parse_revit_module(module)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "identity":
            imported.update(a.name for a in node.names)
    assert {"mutation_document_or_response", "request_document_selector",
            "attribute_response"} <= imported, (module, imported)


def test_guarded_routes_are_exactly_the_routes_the_behavioural_route_suites_exercise():
    """Each guarded route has a behavioural test of its guard in one of the route suites."""
    import test_routes_analysis_color_identity as analysis_color
    import test_routes_document_interop_identity as document_interop
    import test_routes_mep_parameter_identity as mep_parameter
    import test_routes_view_code_identity as view_code

    exercised = set()
    for suite in (analysis_color, document_interop, mep_parameter, view_code):
        exercised.update(route for _, route in suite.MUTATIONS)
    assert exercised == set(GUARDED_ROUTES), (
        "guard behaviour untested for {}; tested but not guarded {}".format(
            sorted(set(GUARDED_ROUTES) - exercised), sorted(exercised - set(GUARDED_ROUTES))))
    for suite in (analysis_color, document_interop, mep_parameter, view_code):
        for module, route in suite.MUTATIONS:
            assert ROUTE_BY_KEY[route].module == module, (module, route)


@pytest.mark.parametrize("key", sorted(k for k, c in ROUTE_CLASSES.items() if c != GUARDED))
def test_a_route_that_is_not_a_guarded_mutation_never_calls_the_mutation_guard(key):
    route = ROUTE_BY_KEY[key]
    assert "mutation_document_or_response" not in reachable_calls(route), key


@pytest.mark.parametrize("key", sorted(
    k for k, c in ROUTE_CLASSES.items()
    if c in (ACTIVE_READ, HTTP_THREAD, REGISTRY_LIST, REGISTRY_READ, FILE_PREVIEW)))
def test_a_read_route_reaches_no_transaction_save_delete_open_or_activation(key):
    """Classified by what the route does: a POST read is a read, and a read mutates nothing."""
    route = ROUTE_BY_KEY[key]
    reached = reachable_calls(route) & MUTATION_PRIMITIVES
    assert reached == set(), (key, sorted(reached))


@pytest.mark.parametrize("key", GUARDED_ROUTES)
def test_a_guarded_route_opens_a_transaction_unless_it_is_a_named_exception(key):
    route = ROUTE_BY_KEY[key]
    transacts = "Transaction" in reachable_calls(route)
    if key in GUARDED_WITHOUT_TRANSACTION:
        assert not transacts, "{} must run outside any transaction".format(key)
    else:
        assert transacts, "{} is classified as a transacting mutation but opens none".format(key)


def test_the_named_no_transaction_mutations_are_exactly_the_documented_three():
    assert GUARDED_WITHOUT_TRANSACTION == {"/save_document/", "/load_family/", "/set_active_view/"}
    assert GUARDED_WITHOUT_TRANSACTION <= set(GUARDED_ROUTES)


# ----------------------------------------------------------- G4 and G1 source pins


def _enclosing_function_names(tree, call):
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and any(n is call for n in ast.walk(node)):
            names.append(node.name)
    return names


def test_only_documents_activation_and_the_file_open_may_activate_a_document():
    """G4: the single activation call site is documents.run_activation; open_model is file opening."""
    sites = []
    stores = []
    forbidden = []
    for module in revit_mcp_modules():
        tree = parse_revit_module(module)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = call_name(node)
                if name == "OpenAndActivateDocument":
                    inner = _enclosing_function_names(tree, node)
                    sites.append((module, inner[-1]))
                if name in ("SetActiveDocument", "ActivateDocument", "RequestViewChange"):
                    forbidden.append((module, name))
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store) \
                    and node.attr in ("ActiveView", "ActiveUIDocument", "ActiveDocument"):
                stores.append((module, node.attr, _enclosing_function_names(tree, node)[-1]))
    assert sorted(sites) == [("documents", "run_activation"), ("worksharing", "_open_model")]
    assert stores == [("view_management", "ActiveView", "_set_active_view")]
    assert forbidden == []


def test_the_activation_helper_is_reachable_only_from_the_activate_document_route():
    callers = []
    for module in revit_mcp_modules():
        tree = parse_revit_module(module)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and call_name(node) == "run_activation":
                callers.append((module, _enclosing_function_names(tree, node)[-1]))
    assert callers == [("documents", "activate_document")], callers
    assert ROUTE_BY_KEY["/activate_document/"].name == "activate_document"


def test_the_activation_allow_branch_is_gated_by_the_saved_non_workshared_file_class():
    tree = parse_revit_module("documents")
    run = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
           and n.name == "run_activation"][0]
    call_lines = {call_name(c): c.lineno for c in ast.walk(run) if isinstance(c, ast.Call)}
    assert call_lines["activation_refusal_reason"] < call_lines["OpenAndActivateDocument"]
    gate = [n for n in ast.walk(run) if isinstance(n, ast.If)
            and "reason" in ast.dump(n.test) and "IsNot" in ast.dump(n.test)]
    assert gate and any(isinstance(s, ast.Return) for s in gate[0].body)
    assert gate[0].lineno < call_lines["OpenAndActivateDocument"]
    refusal = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
               and n.name == "activation_refusal_reason"][0]
    text = ast.dump(refusal)
    for flag in ("IsDetached", "IsLinked", "IsFamilyDocument", "IsModelInCloud", "IsWorkshared"):
        assert flag in text, flag


def test_startup_installs_no_common_handler_wrapper():
    """G1 explicit-route-only: startup.py hands the api to each registrar untouched."""
    tree = ast.parse(source_of(os.path.join(REPO_ROOT, "startup.py")))
    api_attributes = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                      and isinstance(n.value, ast.Name) and n.value.id == "api"]
    assert api_attributes == [], "startup.py touches api.<attribute>: a wrapper candidate"
    api_uses = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "api"
                and isinstance(n.ctx, ast.Load)]
    passed = [c for c in ast.walk(tree) if isinstance(c, ast.Call)
              and any(isinstance(a, ast.Name) and a.id == "api" for a in c.args)]
    assert len(api_uses) == len(passed) == 1
    assert call_name(passed[0]) == "registrar"
    assignments = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "api" for t in n.targets)]
    assert len(assignments) == 1 and call_name(assignments[0].value) == "API"
    decorated = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.decorator_list]
    assert decorated == []
    for forbidden in ("wraps", "setattr", "functools", "mutation_document_or_response",
                      "decide_mutation_document", "attribute_response"):
        assert forbidden not in source_of(os.path.join(REPO_ROOT, "startup.py")), forbidden


def test_no_revit_mcp_module_imports_a_domain_module_in_any_form_or_scope():
    """Registration order stays insignificant: helpers only, nested imports included."""
    domains = {n for n in revit_mcp_modules() if module_registrars(parse_revit_module(n))}
    helpers = set(revit_mcp_modules()) - domains
    assert {"identity", "registry", "textutils", "utils"} <= helpers
    offenders = []
    packages = ("revit_mcp", "genpro_revit_mcp")
    for module in revit_mcp_modules():
        tree = parse_revit_module(module)
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level >= 1:
                    parts = base.split(".")[0]
                    targets.append(parts if parts else None)
                    if not base:
                        targets.extend(a.name for a in node.names)
                elif base.split(".")[0] in packages:
                    rest = base.split(".")[1:]
                    targets.append(rest[0] if rest else None)
                    if not rest:
                        targets.extend(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    head = alias.name.split(".")
                    if head[0] in packages and len(head) > 1:
                        targets.append(head[1])
            elif isinstance(node, ast.Call) and call_name(node) == "__import__" and node.args \
                    and isinstance(node.args[0], ast.Constant):
                head = str(node.args[0].value).split(".")
                if head[0] in packages and len(head) > 1:
                    targets.append(head[1])
            for target in targets:
                if target in domains:
                    offenders.append("{} -> {}".format(module, target))
    assert offenders == [], offenders
