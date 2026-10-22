# -*- coding: utf-8 -*-
"""Plan 02-10: per-call process (target) and mutation-document (document)
forwarding for the interop, MEP, model, parameter and room tools.

The real tool functions are registered on a recording fake transport and called;
each row asserts what actually reached the transport: the route, the ``target``
keyword and the POST body. A tool that drops either selector fails its row, not
just a convention scan.

Scope is exactly the callables registered by the five owned registrars
(register_interop_tools, register_mep_tools, register_model_tools,
register_parameter_tools, register_room_tools). get_revit_model_info lives in
status_tools and is not owned by this plan.

Classification is by hand, never by HTTP method:

* ``read``      -- target only, no document argument at all. Reading an inactive
                   document is supported only by read_document_summary and
                   read_document_levels (D-11), so no other read may offer it:
                   list_levels, list_project_parameters and get_element_properties
                   stay active-document reads of the selected process.
* ``mutation``  -- target and an optional document, forwarded in the POST body
                   only when given; a blank document refuses before any send.
                   export_ifc writes a file from the document and link_file adds
                   a link or import to it, so both are document-bound.

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

ROLLED_BACK_409 = (
    'Error: 409 - {"status": "rolled_back", "transaction_status": '
    '"RolledBack", "failures": [{"severity": "Error", "description": '
    '"Constraints are not satisfied"}]}'
)


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
    "export_ifc": _row(
        "interop", "mutation", "POST", "/export_ifc/",
        ["file_path", "ifc_version", "export_base_quantities", "view_name"],
        {"file_path": "C:/Out/model.ifc"}),
    "link_file": _row(
        "interop", "mutation", "POST", "/link_file/",
        ["file_path", "mode", "position"],
        {"file_path": "C:/Links/plan.dwg"}),
    "create_duct": _row(
        "mep", "mutation", "POST", "/create_duct/",
        ["start_point", "end_point", "system_type", "duct_type", "level_name",
         "diameter", "width", "height"],
        {"start_point": POINT_A, "end_point": POINT_B}),
    "create_pipe": _row(
        "mep", "mutation", "POST", "/create_pipe/",
        ["start_point", "end_point", "system_type", "pipe_type", "level_name", "diameter"],
        {"start_point": POINT_A, "end_point": POINT_B}),
    "create_mep_system": _row(
        "mep", "mutation", "POST", "/create_mep_system/",
        ["system_type", "system_name", "element_ids"],
        {"system_type": "mechanical", "system_name": "Level 1 Supply Air"}),
    "list_levels": _row("model", "read", "GET", "/list_levels/", [], {}),
}

TASK_TWO_TOOLS = {
    "list_project_parameters": _row(
        "parameter", "read", "GET", "/project_parameters/",
        ["shared_only", "prefix", "search", "summary_only"], {}),
    # The route embeds the element id, so the row carries the resolved path.
    "get_element_properties": _row(
        "parameter", "read", "GET", "/element_properties/7",
        ["element_id", "include_type_params"], {"element_id": 7}),
    "set_parameter": _row(
        "parameter", "mutation", "POST", "/set_parameter/",
        ["element_id", "parameter_name", "value"],
        {"element_id": 7, "parameter_name": "Comments", "value": "checked"}),
    "create_room": _row(
        "room", "mutation", "POST", "/create_room/",
        ["level_name", "location", "name", "number"], {"level_name": "Level 1"}),
    "create_room_separation": _row(
        "room", "mutation", "POST", "/create_room_separation/",
        ["lines", "level_name", "view_name"],
        {"lines": [{"start_point": POINT_A, "end_point": POINT_B}]}),
}

TOOLS = dict(TASK_ONE_TOOLS, **TASK_TWO_TOOLS)
MODULES = sorted({row["module"] for row in TOOLS.values()})
MUTATIONS = sorted(name for name, row in TOOLS.items() if row["kind"] == "mutation")
READS = sorted(name for name, row in TOOLS.items() if row["kind"] == "read")


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
    else:
        assert names == row["legacy"] + ["target", "ctx"], names
        assert "document" not in names
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
    else:
        assert not re.search(r"^\s+document:", args_block, re.M)
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
        assert "target" not in data and "document" not in data


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_forwards_target_as_a_transport_keyword_never_in_the_body(name):
    row = TOOLS[name]
    text, calls = run_tool(name, target=PROCESS_SELECTOR)
    assert isinstance(text, str) and len(calls) == 1
    method, route, data, options = calls[0]
    assert (method, route) == (row["method"], row["route"])
    assert options.get("target") == PROCESS_SELECTOR
    if method == "POST":
        assert "target" not in data and "document" not in data


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


def test_export_ifc_keeps_its_legacy_body_and_adds_only_the_document():
    text, calls = run_tool("export_ifc")
    assert calls == [("POST", "/export_ifc/",
                      {"file_path": "C:/Out/model.ifc", "ifc_version": "IFC2x3",
                       "export_base_quantities": True}, {})]
    text, calls = run_tool("export_ifc", ifc_version="IFC4", export_base_quantities=False,
                           view_name="Level 1", document=DOCUMENT_SELECTOR, target=PROCESS_SELECTOR)
    assert calls == [("POST", "/export_ifc/",
                      {"file_path": "C:/Out/model.ifc", "ifc_version": "IFC4",
                       "export_base_quantities": False, "view_name": "Level 1",
                       "document": DOCUMENT_SELECTOR}, {"target": PROCESS_SELECTOR})]


def test_export_ifc_and_link_file_still_refuse_a_mangled_path_before_sending():
    text, calls = run_tool("export_ifc", file_path="C:\x08ad\new.ifc", document=DOCUMENT_SELECTOR,
                           target=PROCESS_SELECTOR)
    assert calls == [] and "control characters" in text
    text, calls = run_tool("link_file", file_path="C:\x08ad\new.dwg", document=DOCUMENT_SELECTOR)
    assert calls == [] and "control characters" in text


def test_link_file_keeps_its_legacy_body_and_adds_only_the_document():
    text, calls = run_tool("link_file")
    assert calls == [("POST", "/link_file/", {"file_path": "C:/Links/plan.dwg", "mode": "link"}, {})]
    text, calls = run_tool("link_file", mode="import", position={"x": 1, "y": 2, "z": 3},
                           document=DOCUMENT_SELECTOR)
    assert calls == [("POST", "/link_file/",
                      {"file_path": "C:/Links/plan.dwg", "mode": "import",
                       "position": {"x": 1, "y": 2, "z": 3}, "document": DOCUMENT_SELECTOR}, {})]


def test_duct_and_pipe_keep_their_optional_fields_out_of_the_body_unless_given():
    text, calls = run_tool("create_duct")
    assert calls[0][2] == {"start_point": POINT_A, "end_point": POINT_B}
    text, calls = run_tool("create_duct", system_type="Supply Air", duct_type="Round Duct",
                           level_name="Level 1", diameter=200.0, width=300.0, height=150.0,
                           document=DOCUMENT_SELECTOR)
    assert calls[0][2] == {"start_point": POINT_A, "end_point": POINT_B, "system_type": "Supply Air",
                           "duct_type": "Round Duct", "level_name": "Level 1", "diameter": 200.0,
                           "width": 300.0, "height": 150.0, "document": DOCUMENT_SELECTOR}
    text, calls = run_tool("create_pipe")
    assert calls[0][2] == {"start_point": POINT_A, "end_point": POINT_B}
    text, calls = run_tool("create_pipe", system_type="DHW", pipe_type="Copper", level_name="Level 1",
                           diameter=25.0, document=DOCUMENT_SELECTOR)
    assert calls[0][2] == {"start_point": POINT_A, "end_point": POINT_B, "system_type": "DHW",
                           "pipe_type": "Copper", "level_name": "Level 1", "diameter": 25.0,
                           "document": DOCUMENT_SELECTOR}


def test_create_mep_system_keeps_element_ids_out_of_the_body_unless_given():
    text, calls = run_tool("create_mep_system")
    assert calls[0][2] == {"system_type": "mechanical", "system_name": "Level 1 Supply Air"}
    text, calls = run_tool("create_mep_system", element_ids=[5, 6], document=DOCUMENT_SELECTOR)
    assert calls[0][2] == {"system_type": "mechanical", "system_name": "Level 1 Supply Air",
                           "element_ids": [5, 6], "document": DOCUMENT_SELECTOR}


def test_list_levels_is_an_active_only_read_and_points_to_the_addressed_levels_tool():
    tools, _ = register_module("model")
    lowered = " ".join(tools["list_levels"].__doc__.lower().split())
    assert "active document" in lowered
    assert "read_document_levels" in lowered
    assert "no document argument" in lowered


def test_list_project_parameters_forwards_its_filter_params_and_the_target_together():
    text, calls = run_tool("list_project_parameters", shared_only=True, prefix="ADSK_", search="mark",
                           summary_only=True, target=PROCESS_SELECTOR)
    assert calls == [("GET", "/project_parameters/", None,
                      {"params": {"shared_only": "true", "prefix": "ADSK_", "search": "mark",
                                  "summary_only": "true"}, "target": PROCESS_SELECTOR})]
    text, calls = run_tool("list_project_parameters")
    assert calls == [("GET", "/project_parameters/", None, {"params": {}})]


def test_get_element_properties_keeps_the_element_id_in_the_path_and_adds_only_the_target():
    text, calls = run_tool("get_element_properties", element_id=42, target=PROCESS_SELECTOR)
    assert calls == [("GET", "/element_properties/42", None, {"target": PROCESS_SELECTOR})]


def test_parameter_reads_state_that_they_read_the_active_document_only():
    for name in ("list_project_parameters", "get_element_properties"):
        tools, _ = register_module("parameter")
        lowered = " ".join(tools[name].__doc__.lower().split())
        assert "no document argument" in lowered, name
        assert "active document" in lowered, name


def test_set_parameter_keeps_its_legacy_body_and_adds_only_the_document():
    text, calls = run_tool("set_parameter")
    assert calls == [("POST", "/set_parameter/",
                      {"element_id": 7, "parameter_name": "Comments", "value": "checked"}, {})]
    text, calls = run_tool("set_parameter", document=DOCUMENT_SELECTOR, target=PROCESS_SELECTOR)
    assert calls == [("POST", "/set_parameter/",
                      {"element_id": 7, "parameter_name": "Comments", "value": "checked",
                       "document": DOCUMENT_SELECTOR}, {"target": PROCESS_SELECTOR})]


def test_create_room_keeps_its_optional_fields_out_of_the_body_unless_given():
    text, calls = run_tool("create_room")
    assert calls[0][2] == {"level_name": "Level 1"}
    # run_tool's own first parameter is called name, so call the room tool directly here.
    tools, calls = register_module("room")
    asyncio.run(tools["create_room"](level_name="Level 1", location={"x": 1.0, "y": 2.0}, name="Hall",
                                     number="101", document=DOCUMENT_SELECTOR))
    assert calls[0][2] == {"level_name": "Level 1", "location": {"x": 1.0, "y": 2.0}, "name": "Hall",
                           "number": "101", "document": DOCUMENT_SELECTOR}


def test_create_room_separation_keeps_its_optional_fields_out_of_the_body_unless_given():
    lines = [{"start_point": POINT_A, "end_point": POINT_B}]
    text, calls = run_tool("create_room_separation")
    assert calls[0][2] == {"lines": lines}
    text, calls = run_tool("create_room_separation", level_name="Level 1", view_name="Plan 1",
                           document=DOCUMENT_SELECTOR)
    assert calls[0][2] == {"lines": lines, "level_name": "Level 1", "view_name": "Plan 1",
                           "document": DOCUMENT_SELECTOR}


@pytest.mark.parametrize("name", MUTATIONS)
def test_a_rolled_back_409_stays_a_visible_failure_never_a_success(name):
    """The bridge hands a non-200 reply over as an 'Error: 409 - ...' string (D-07).

    The tools must return it verbatim: no selector handling may rewrite it into a
    success, and no formatting may drop the rollback reason.
    """
    text, calls = run_tool(name, response=ROLLED_BACK_409, document=DOCUMENT_SELECTOR,
                           target=PROCESS_SELECTOR)
    assert len(calls) == 1
    assert text == ROLLED_BACK_409
    assert text.startswith("Error: 409")
    assert "rolled_back" in text and "Constraints are not satisfied" in text


@pytest.mark.parametrize("name", MUTATIONS)
def test_a_rollback_dict_signal_is_not_relabelled_by_the_tool(name):
    """Whatever a mutation tool gets back is formatted by format_response, nothing else."""
    from tools.utils import format_response
    reply = {"status": "rolled_back", "transaction_status": "RolledBack"}
    text, _ = run_tool(name, response=reply, document=DOCUMENT_SELECTOR)
    assert text == format_response(reply)


def test_route_replies_pass_through_format_response_unchanged_in_shape():
    text, _ = run_tool("create_pipe", response={"error": "boom", "status": "error"},
                       document=DOCUMENT_SELECTOR)
    assert isinstance(text, str) and "boom" in text
    text, _ = run_tool("list_levels", response="plain text reply")
    assert text == "plain text reply"


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
def test_none_of_the_modules_fetches_an_image_so_no_image_path_loses_a_target(module):
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
