# -*- coding: utf-8 -*-
"""Plan 02-11: per-call process (target) and mutation-document (document)
forwarding for the structure, tag, transform, view-management, view and
worksharing tools.

The real tool functions are registered on a recording fake transport and called;
each row asserts what actually reached the transport: the route, the ``target``
keyword and the POST body. A tool that drops either selector fails its row, not
just a convention scan.

Scope is exactly the callables registered by the six owned registrars
(register_structure_tools, register_tag_tools, register_transform_tools,
register_view_management_tools, register_view_tools, register_worksharing_tools).

Classification is by hand, never by HTTP method:

* ``mutation`` -- target and an optional document, forwarded in the POST body
                  only when given; a blank document refuses before any send.
                  Grid, framing, tag, transform, create_view and set_active_view
                  all change a document (set_active_view changes the view that
                  document shows).
* ``read``     -- target only, no document argument at all. Reading an inactive
                  document is supported only by read_document_summary and
                  read_document_levels (D-11), so no view read may offer it: the
                  four view tools stay active-document reads of the selected
                  process, and an inactive selection cannot even be expressed.
* ``file_read`` / ``file_open`` -- process-level worksharing tools (added with
                  the worksharing rows).

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

# kind -> transport method the row is expected to use
POINT_A = {"x": 0, "y": 0, "z": 0}
POINT_B = {"x": 1000, "y": 0, "z": 0}


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


TASK_ONE_TOOLS = {
    "create_grid": _row(
        "structure", "mutation", "POST", "/create_grid/", ["grids"],
        {"grids": [{"start_point": POINT_A, "end_point": POINT_B}]}),
    "create_structural_framing": _row(
        "structure", "mutation", "POST", "/create_framing/", ["elements"],
        {"elements": [{"start_point": POINT_A, "end_point": POINT_B}]}),
    "tag_elements": _row(
        "tag", "mutation", "POST", "/tag_elements/",
        ["element_ids", "view_name", "tag_type_name", "add_leader", "orientation", "offset"],
        {"element_ids": [11, 12]}),
    "transform_elements": _row(
        "transform", "mutation", "POST", "/transform_elements/",
        ["element_ids", "operation", "vector", "axis_point", "angle", "mirror_plane"],
        {"element_ids": [11], "operation": "move", "vector": POINT_B}),
}

TOOLS = dict(TASK_ONE_TOOLS)
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

    async def revit_image(path, ctx=None, **options):
        calls.append(("IMAGE", path, None, options))
        return reply

    mcp = FakeMCP()
    registrar(module)(mcp, revit_get, revit_post, revit_image)
    return mcp.tools, calls


def run_tool(tool_name, response=None, **kwargs):
    row = TOOLS[tool_name]
    tools, calls = register_module(row["module"], response)
    text = asyncio.run(tools[tool_name](**dict(row["minimal"], **kwargs)))
    return text, calls


def tools_of(module):
    return sorted(name for name, row in TOOLS.items() if row["module"] == module)


def module_source(module):
    with open(os.path.join(REPO_ROOT, "tools", "{}_tools.py".format(module)), encoding="utf-8") as handle:
        return handle.read()


def normalized(text):
    return " ".join(text.lower().split())


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


@pytest.mark.parametrize("tool_name", sorted(TOOLS))
def test_signatures_carry_target_and_only_actual_mutations_carry_an_optional_document(tool_name):
    row = TOOLS[tool_name]
    tools, _ = register_module(row["module"])
    parameters = inspect.signature(tools[tool_name]).parameters
    names = list(parameters)
    if row["kind"] == "mutation":
        assert names == row["legacy"] + ["target", "document", "ctx"], names
        assert parameters["document"].default is None
    else:
        assert names == row["legacy"] + ["target", "ctx"], names
        assert "document" not in names
    assert parameters["target"].default is None and parameters["ctx"].default is None


@pytest.mark.parametrize("tool_name", sorted(TOOLS))
def test_docstrings_name_every_argument_and_state_the_scope_rule(tool_name):
    row = TOOLS[tool_name]
    tools, _ = register_module(row["module"])
    doc = tools[tool_name].__doc__
    args_block = doc.split("Args:", 1)[1]
    for argument in inspect.signature(tools[tool_name]).parameters:
        assert re.search(r"^\s+{}:".format(argument), args_block, re.M), (tool_name, argument)
    lowered = normalized(doc)
    assert "discover_revit_targets" in doc
    if row["kind"] == "mutation":
        for phrase in ("list_documents", "activate_document", "412", "the only open document",
                       "several", "nothing is activated"):
            assert phrase in lowered, (tool_name, phrase)
    elif row["kind"] == "read":
        assert not re.search(r"^\s+document:", args_block, re.M)
        assert "active document" in lowered
        assert "no document argument" in lowered
        assert "read_document_summary" in doc and "read_document_levels" in doc
        assert "inactive" in lowered


@pytest.mark.parametrize("tool_name", MUTATIONS)
def test_mutation_docstrings_never_claim_a_document_is_retargeted_without_activation(tool_name):
    row = TOOLS[tool_name]
    tools, _ = register_module(row["module"])
    lowered = normalized(tools[tool_name].__doc__)
    for claim in ("switches to", "switch to that document", "retargets", "activates it automatically",
                  "activates the document automatically", "makes it active"):
        assert claim not in lowered, (tool_name, claim)


# --------------------------------------------------------------- forwarding


@pytest.mark.parametrize("tool_name", sorted(TOOLS))
def test_forwards_nothing_extra_when_no_selector_is_given(tool_name):
    row = TOOLS[tool_name]
    text, calls = run_tool(tool_name)
    assert isinstance(text, str)
    assert len(calls) == 1
    method, route, data, options = calls[0]
    assert (method, route) == (row["method"], row["route"])
    assert "target" not in options
    if method == "POST":
        assert "target" not in data and "document" not in data


@pytest.mark.parametrize("tool_name", sorted(TOOLS))
def test_forwards_target_as_a_transport_keyword_never_in_the_body(tool_name):
    row = TOOLS[tool_name]
    text, calls = run_tool(tool_name, target=PROCESS_SELECTOR)
    assert isinstance(text, str) and len(calls) == 1
    method, route, data, options = calls[0]
    assert (method, route) == (row["method"], row["route"])
    assert options.get("target") == PROCESS_SELECTOR
    if method == "POST":
        assert "target" not in data and "document" not in data


@pytest.mark.parametrize("tool_name", MUTATIONS)
def test_mutations_forward_the_document_in_the_post_body_beside_their_own_fields(tool_name):
    row = TOOLS[tool_name]
    text, calls = run_tool(tool_name, document=DOCUMENT_SELECTOR, target=PROCESS_SELECTOR)
    assert isinstance(text, str) and len(calls) == 1
    method, route, data, options = calls[0]
    assert method == "POST" and route == row["route"]
    assert data["document"] == DOCUMENT_SELECTOR
    assert options.get("target") == PROCESS_SELECTOR and "target" not in data
    for key, value in row["minimal"].items():
        assert data[key] == value


@pytest.mark.parametrize("tool_name", MUTATIONS)
@pytest.mark.parametrize("blank", ["", "   ", 7])
def test_mutations_refuse_a_blank_document_without_sending(tool_name, blank):
    """A blank selector must never decay into the one-document default."""
    text, calls = run_tool(tool_name, document=blank)
    assert calls == []
    assert "document" in text and "list_documents" in text


@pytest.mark.parametrize("tool_name", READS)
def test_reads_offer_no_way_to_name_a_document_and_never_dispatch_when_asked(tool_name):
    row = TOOLS[tool_name]
    tools, calls = register_module(row["module"])
    with pytest.raises(TypeError):
        asyncio.run(tools[tool_name](document=DOCUMENT_SELECTOR))
    assert calls == []


# ------------------------------------------------- route-specific behaviour


def test_create_grid_and_framing_forward_the_batch_untouched_beside_the_document():
    grids = [{"start_point": POINT_A, "end_point": POINT_B, "name": "A"}]
    text, calls = run_tool("create_grid", grids=grids, document=DOCUMENT_SELECTOR, target=PROCESS_SELECTOR)
    assert calls == [("POST", "/create_grid/", {"grids": grids, "document": DOCUMENT_SELECTOR},
                      {"target": PROCESS_SELECTOR})]
    elements = [{"start_point": POINT_A, "end_point": POINT_B, "type_name": "W12", "level_name": "L1"}]
    text, calls = run_tool("create_structural_framing", elements=elements)
    assert calls == [("POST", "/create_framing/", {"elements": elements}, {})]


def test_tag_elements_keeps_its_legacy_body_and_adds_only_the_document():
    text, calls = run_tool("tag_elements")
    assert calls == [("POST", "/tag_elements/",
                      {"element_ids": [11, 12], "add_leader": False, "orientation": "horizontal"}, {})]
    text, calls = run_tool("tag_elements", view_name="Plan 1", tag_type_name="Door Tag", add_leader=True,
                           orientation="vertical", offset={"x": 10.0, "y": 5.0},
                           document=DOCUMENT_SELECTOR, target=PROCESS_SELECTOR)
    assert calls == [("POST", "/tag_elements/",
                      {"element_ids": [11, 12], "add_leader": True, "orientation": "vertical",
                       "view_name": "Plan 1", "tag_type_name": "Door Tag", "offset": {"x": 10.0, "y": 5.0},
                       "document": DOCUMENT_SELECTOR}, {"target": PROCESS_SELECTOR})]


def test_transform_elements_keeps_optional_fields_out_of_the_body_unless_given():
    text, calls = run_tool("transform_elements")
    assert calls == [("POST", "/transform_elements/",
                      {"element_ids": [11], "operation": "move", "vector": POINT_B}, {})]
    plane = {"origin": POINT_A, "normal": POINT_B}
    text, calls = run_tool("transform_elements", operation="rotate", vector=None, axis_point=POINT_A,
                           angle=90.0, mirror_plane=plane, document=DOCUMENT_SELECTOR)
    assert calls == [("POST", "/transform_elements/",
                      {"element_ids": [11], "operation": "rotate", "axis_point": POINT_A, "angle": 90.0,
                       "mirror_plane": plane, "document": DOCUMENT_SELECTOR}, {})]


def test_transform_elements_still_forwards_a_zero_angle():
    text, calls = run_tool("transform_elements", operation="rotate", axis_point=POINT_A, angle=0.0)
    assert calls[0][2]["angle"] == 0.0


@pytest.mark.parametrize("tool_name", MUTATIONS)
def test_route_replies_pass_through_format_response_unchanged_in_shape(tool_name):
    from tools.utils import format_response
    reply = {"error": "boom", "status": "error"}
    text, _ = run_tool(tool_name, response=reply, document=DOCUMENT_SELECTOR)
    assert text == format_response(reply) and "boom" in text
    text, _ = run_tool(tool_name, response="Error: 412 - not the active document", document=DOCUMENT_SELECTOR)
    assert text == "Error: 412 - not the active document"


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
def test_every_transport_call_in_the_module_source_forwards_a_target(module):
    """No dispatch site (GET, POST or image fetch) may be written without the per-call selector."""
    tree = ast.parse(module_source(module))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("revit_get", "revit_post", "revit_image")):
            options = [kw for kw in node.keywords if kw.arg is None]
            assert options, "{} call at line {} drops the target".format(node.func.id, node.lineno)
