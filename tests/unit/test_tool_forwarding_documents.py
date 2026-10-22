# -*- coding: utf-8 -*-
"""Plan 02-09: per-call process (target) and mutation-document (document)
forwarding for the detail, document, documentation, editing and family tools.

The real tool functions are registered on a recording fake transport and called;
each row asserts what actually reached the transport: the route, the ``target``
keyword and the POST body. A tool that drops either selector fails its row, not
just a convention scan.

Scope is exactly the callables registered by the five owned registrars
(register_detail_tools, register_document_tools, register_documentation_tools,
register_editing_tools, register_family_tools). The worksharing file-open tool
belongs to plan 02-11 and is deliberately absent.

Classification is by hand, never by HTTP method:

* ``read``      -- target only, no document argument at all: reading an inactive
                   document is supported only by read_document_summary and
                   read_document_levels (D-11), so no other read may offer it.
* ``mutation``  -- target and an optional document, forwarded in the POST body
                   only when given; a blank document refuses before any send.
* ``addressed`` -- the 02-04..02-06 tools whose document is a required first
                   argument; only their target forwarding is pinned here, their
                   behavior contracts stay in test_document_contracts.py.

Offline evidence only: the route-side guard that enforces the document is plan
02-12, and nothing here is a live observation.
"""

import asyncio
import ast
import importlib
import inspect
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DOCUMENT_SELECTOR = "doc1.aaaaaaaaaaaa.2"
PROCESS_SELECTOR = "revit1:abc"


class FakeMCP(object):
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


def _row(module, kind, method, route, legacy, minimal):
    return {"module": module, "kind": kind, "method": method, "route": route,
            "legacy": legacy, "minimal": minimal}


POINT_A = {"x": 0, "y": 0, "z": 0}
POINT_B = {"x": 1000, "y": 0, "z": 0}

TASK_ONE_TOOLS = {
    "create_detail_line": _row(
        "detail", "mutation", "POST", "/create_detail_line/",
        ["start_point", "end_point", "view_name", "line_style"],
        {"start_point": POINT_A, "end_point": POINT_B}),
    "create_sheet": _row(
        "documentation", "mutation", "POST", "/create_sheet/",
        ["sheet_number", "sheet_name", "title_block_name"], {}),
    "create_schedule": _row(
        "documentation", "mutation", "POST", "/create_schedule/",
        ["category", "fields", "schedule_name"], {"category": "OST_Walls"}),
    # Writes a file to disk through a transaction on the document: document-bound.
    "export_document": _row(
        "documentation", "mutation", "POST", "/export_document/",
        ["view_name", "format", "resolution"], {}),
}

TASK_TWO_TOOLS = {
    "save_document": _row(
        "document", "mutation", "POST", "/save_document/",
        ["file_path", "overwrite", "as_central"], {}),
    "list_documents": _row("document", "read", "GET", "/documents/", [], {}),
    "activate_document": _row(
        "document", "addressed", "POST", "/activate_document/", [],
        {"document": DOCUMENT_SELECTOR}),
    "read_document_summary": _row(
        "document", "addressed", "POST", "/document_summary/", [],
        {"document": DOCUMENT_SELECTOR}),
    "read_document_levels": _row(
        "document", "addressed", "POST", "/document_levels/", [],
        {"document": DOCUMENT_SELECTOR}),
    "delete_elements": _row(
        "editing", "mutation", "POST", "/delete_elements/", ["element_ids"],
        {"element_ids": [1, 2]}),
    "modify_element": _row(
        "editing", "mutation", "POST", "/modify_element/", ["element_id", "parameters"],
        {"element_id": 7, "parameters": {"Mark": "EW-01"}}),
    "get_selected_elements": _row("editing", "read", "GET", "/selected_elements/", [], {}),
    "place_family": _row(
        "family", "mutation", "POST", "/place_family/",
        ["family_name", "type_name", "x", "y", "z", "rotation", "level_name", "properties"],
        {"family_name": "Chair"}),
    "list_families": _row("family", "read", "GET", "/list_families/", ["contains", "limit"], {}),
    "list_family_categories": _row(
        "family", "read", "GET", "/list_family_categories/", [], {}),
    "load_family": _row(
        "family", "mutation", "POST", "/load_family/", ["file_path"],
        {"file_path": "C:/Families/Chair.rfa"}),
    "edit_family": _row(
        "family", "mutation", "POST", "/edit_family/",
        ["family_name", "type_name", "parameters", "new_type_name", "reload"],
        {"family_name": "Chair"}),
}

TOOLS = dict(TASK_ONE_TOOLS)
MODULES = ["detail", "documentation"]
MUTATIONS = sorted(name for name, row in TOOLS.items() if row["kind"] == "mutation")
READS = sorted(name for name, row in TOOLS.items() if row["kind"] == "read")
ADDRESSED = sorted(name for name, row in TOOLS.items() if row["kind"] == "addressed")


def registrar(module):
    loaded = importlib.import_module("tools.{}_tools".format(module))
    return getattr(loaded, "register_{}_tools".format(module))


def register_module(module, response=None):
    """Register one module on a recording fake transport; returns (tools, calls)."""
    calls = []
    reply = {"status": "success"} if response is None else response

    async def revit_get(path, ctx=None, **options):
        calls.append(("GET", path, None, options))
        return reply

    async def revit_post(path, data, ctx=None, **options):
        calls.append(("POST", path, data, options))
        return reply

    async def revit_image(*args, **kwargs):  # pragma: no cover - none of the five fetch images
        raise AssertionError("none of these modules fetches an image")

    mcp = FakeMCP()
    registrar(module)(mcp, revit_get, revit_post, revit_image)
    return mcp.tools, calls


def run_tool(name, response=None, **kwargs):
    row = TOOLS[name]
    tools, calls = register_module(row["module"], response)
    text = asyncio.run(tools[name](**dict(row["minimal"], **kwargs)))
    return text, calls


def tools_of(module):
    return sorted(name for name, row in TOOLS.items() if row["module"] == module)


def module_source(module):
    with open(os.path.join(REPO_ROOT, "tools", "{}_tools.py".format(module)), encoding="utf-8") as handle:
        return handle.read()


# --------------------------------------------------------------- inventory


@pytest.mark.parametrize("module", MODULES)
def test_each_owned_registrar_registers_exactly_the_inventoried_tools(module):
    tools, _ = register_module(module)
    assert sorted(tools) == tools_of(module)


def test_the_worksharing_file_open_tool_is_owned_by_another_plan_and_has_no_row_here():
    assert "open_model" not in TOOLS
    assert all(row["module"] != "worksharing" for row in TOOLS.values())


def test_every_inventoried_tool_is_in_the_manifest():
    with open(os.path.join(REPO_ROOT, "tests", "unit", "tool_manifest.txt"), encoding="utf-8") as handle:
        manifest = {line.strip() for line in handle if line.strip() and not line.startswith("#")}
    assert set(TOOLS) <= manifest


# --------------------------------------------------------------- signatures


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_signatures_carry_target_and_only_actual_mutations_carry_an_optional_document(name):
    row = TOOLS[name]
    tools, _ = register_module(row["module"])
    parameters = inspect.signature(tools[name]).parameters
    names = list(parameters)
    if row["kind"] == "mutation":
        assert names == row["legacy"] + ["target", "document", "ctx"], names
        assert parameters["document"].default is None
    elif row["kind"] == "read":
        assert names == row["legacy"] + ["target", "ctx"], names
        assert "document" not in names
    else:
        # 02-04..02-06 contract: required document first, then target, then ctx.
        assert names == ["document", "target", "ctx"], names
        assert parameters["document"].default is inspect.Parameter.empty
    assert parameters["target"].default is None and parameters["ctx"].default is None


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_docstrings_name_every_argument_and_state_the_scope_rule(name):
    row = TOOLS[name]
    tools, _ = register_module(row["module"])
    doc = tools[name].__doc__
    args_block = doc.split("Args:", 1)[1]
    for argument in inspect.signature(tools[name]).parameters:
        assert re.search(r"^\s+{}:".format(argument), args_block, re.M), (name, argument)
    lowered = " ".join(doc.lower().split())
    assert "discover_revit_targets" in doc
    if row["kind"] == "mutation":
        for phrase in ("list_documents", "activate_document", "412", "the only open document",
                       "several", "nothing is activated"):
            assert phrase in lowered, (name, phrase)
    elif row["kind"] == "read":
        assert not re.search(r"^\s+document:", args_block, re.M)
        if name != "list_documents":
            assert "active document" in lowered
            assert "read_document_summary" in doc and "read_document_levels" in doc
            assert "inactive" in lowered


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutation_docstrings_never_claim_a_document_is_retargeted_without_activation(name):
    row = TOOLS[name]
    tools, _ = register_module(row["module"])
    lowered = " ".join(tools[name].__doc__.lower().split())
    for claim in ("switches to", "switch to that document", "retargets", "activates it automatically",
                  "activates the document automatically", "makes it active"):
        assert claim not in lowered, (name, claim)


# --------------------------------------------------------------- forwarding


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_forwards_nothing_extra_when_no_selector_is_given(name):
    row = TOOLS[name]
    text, calls = run_tool(name)
    assert isinstance(text, str)
    assert len(calls) == 1
    method, route, data, options = calls[0]
    assert (method, route) == (row["method"], row["route"])
    assert "target" not in options
    if method == "POST":
        assert "target" not in data
        if row["kind"] != "addressed":
            assert "document" not in data


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_forwards_target_as_a_transport_keyword_never_in_the_body(name):
    row = TOOLS[name]
    text, calls = run_tool(name, target=PROCESS_SELECTOR)
    assert isinstance(text, str) and len(calls) == 1
    method, route, data, options = calls[0]
    assert (method, route) == (row["method"], row["route"])
    assert options.get("target") == PROCESS_SELECTOR
    if method == "POST":
        assert "target" not in data
        if row["kind"] != "addressed":
            assert "document" not in data


@pytest.mark.parametrize("name", MUTATIONS)
def test_mutations_forward_the_document_in_the_post_body_beside_their_own_fields(name):
    row = TOOLS[name]
    text, calls = run_tool(name, document=DOCUMENT_SELECTOR, target=PROCESS_SELECTOR)
    assert isinstance(text, str) and len(calls) == 1
    method, route, data, options = calls[0]
    assert method == "POST" and route == row["route"]
    assert data["document"] == DOCUMENT_SELECTOR
    assert options.get("target") == PROCESS_SELECTOR and "target" not in data
    for key, value in row["minimal"].items():
        assert data[key] == value


@pytest.mark.parametrize("name", ADDRESSED)
def test_addressed_tools_keep_posting_their_required_document_with_the_target(name):
    text, calls = run_tool(name, target=PROCESS_SELECTOR)
    method, route, data, options = calls[0]
    assert route == TOOLS[name]["route"]
    assert data == {"document": DOCUMENT_SELECTOR}
    assert options == {"target": PROCESS_SELECTOR}


@pytest.mark.parametrize("name", MUTATIONS)
@pytest.mark.parametrize("blank", ["", "   ", 7])
def test_mutations_refuse_a_blank_document_without_sending(name, blank):
    """A blank selector must never decay into the one-document default."""
    text, calls = run_tool(name, document=blank)
    assert calls == []
    assert "document" in text and "list_documents" in text


@pytest.mark.parametrize("name", READS)
def test_reads_offer_no_way_to_name_a_document_and_never_dispatch_when_asked(name):
    row = TOOLS[name]
    tools, calls = register_module(row["module"])
    with pytest.raises(TypeError):
        asyncio.run(tools[name](document=DOCUMENT_SELECTOR))
    assert calls == []


# ------------------------------------------------- route-specific behaviour


def test_create_detail_line_keeps_its_optional_fields_out_of_the_body_unless_given():
    text, calls = run_tool("create_detail_line")
    assert calls[0][2] == {"start_point": POINT_A, "end_point": POINT_B}
    text, calls = run_tool("create_detail_line", view_name="Level 1", line_style="Medium Lines",
                           document=DOCUMENT_SELECTOR)
    assert calls[0][2] == {"start_point": POINT_A, "end_point": POINT_B, "view_name": "Level 1",
                           "line_style": "Medium Lines", "document": DOCUMENT_SELECTOR}


def test_route_replies_pass_through_format_response_unchanged_in_shape():
    text, _ = run_tool("create_sheet", response={"error": "boom", "status": "error"},
                       document=DOCUMENT_SELECTOR)
    assert isinstance(text, str) and "boom" in text


# ------------------------------------------------------------ source checks


@pytest.mark.parametrize("module", MODULES)
def test_document_is_attached_exactly_once_per_mutation_in_the_module_source(module):
    """The inventory and the source agree: one forwarding site per mutation, none for a read."""
    source = module_source(module)
    mutations = [n for n, row in TOOLS.items() if row["module"] == module and row["kind"] == "mutation"]
    assert source.count('data["document"] = document') == len(mutations)


@pytest.mark.parametrize("module", MODULES)
def test_modules_never_import_the_transport(module):
    tree = ast.parse(module_source(module))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"bridge", "httpx"}, imported


@pytest.mark.parametrize("module", MODULES)
def test_none_of_the_five_modules_fetches_an_image_so_no_image_path_loses_a_target(module):
    tree = ast.parse(module_source(module))
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "revit_image" not in called


@pytest.mark.parametrize("module", MODULES)
def test_every_transport_call_in_the_module_source_forwards_a_target(module):
    """No dispatch site may be written without the per-call selector."""
    tree = ast.parse(module_source(module))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("revit_get", "revit_post")):
            options = [kw for kw in node.keywords if kw.arg is None]
            assert options, "{} call at line {} drops the target".format(node.func.id, node.lineno)
