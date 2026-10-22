# -*- coding: utf-8 -*-
"""Shared discovery and classification for the Phase 2 exhaustive inventory (02-17).

Not a test module (the name does not start with ``test_``), so pytest never
collects it; ``test_phase2_inventory.py`` and ``test_identity_rendering.py``
import it.

Two things live here and they are kept apart on purpose:

* DISCOVERY derives what exists from the real code: the tool registrars are run
  through ``tools.register_tools`` against a recording transport, and the Revit
  half (which cannot be imported under CPython) is read as source with ``ast``,
  using the same convention ``startup.py`` uses (a ``register_*_routes`` callable
  per module, ``@api.route`` handlers inside it).
* CLASSIFICATION is the hand-written table of what every discovered tool and
  route IS, by what it does and never by its HTTP method. A tool or route that is
  discovered but not in a table fails the inventory until somebody classifies it,
  which is how an unexamined mutation path is kept out.

Needs no Revit, no pyRevit and no network.
"""

import ast
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REVIT_MCP_DIR = os.path.join(REPO_ROOT, "revit_mcp")
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_manifest.txt")

DOCUMENT_SELECTOR = "doc1.aaaaaaaaaaaa.2"
PROCESS_SELECTOR = "revit1:abc"

API_CONTEXT_ARGUMENTS = frozenset({"uiapp", "uidoc", "doc"})

# ---------------------------------------------------------------- tool classes
MUTATION = "mutation"          # target, document, ctx; POST body carries the document
READ = "read"                  # target, ctx; no way to name a document
STATUS = "status"              # target, ctx; process liveness, no document
ADDRESSED_READ = "addressed-read"  # (document, target, ctx): the two inactive-document reads
ACTIVATION = "activation"      # (document, target, ctx): explicit G4 activation
FILE_READ = "file-read"        # target, ctx; previews a file on disk
PROCESS_OPEN = "process-open"  # target, ctx; process-level file open
D15 = "d15-execute"            # target, ctx; trusted arbitrary-code exception
LOCAL = "local-process"        # no target by design: no Revit reply or discovery-based

MUTATION_TOOLS = (
    "clear_colors", "color_splash", "create_detail_line", "create_dimensions", "create_duct",
    "create_grid", "create_level", "create_line_based_element", "create_mep_system",
    "create_pipe", "create_room", "create_room_separation", "create_schedule", "create_sheet",
    "create_structural_framing", "create_surface_based_element", "create_view",
    "delete_elements", "edit_family", "export_document", "export_ifc", "link_file",
    "load_family", "modify_element", "place_family", "save_document", "set_active_view",
    "set_parameter", "tag_elements", "tag_walls", "transform_elements",
)

# POST reads (ai_element_filter, get_material_quantities, check_clashes,
# list_category_parameters) are reads: classified by what the route does.
READ_TOOLS = (
    "ai_element_filter", "analyze_model_statistics", "check_clashes", "export_room_data",
    "get_current_view_elements", "get_current_view_info", "get_element_properties",
    "get_material_quantities", "get_revit_model_info", "get_revit_view", "get_selected_elements",
    "list_category_parameters", "list_documents", "list_families", "list_family_categories",
    "list_levels", "list_project_parameters", "list_revit_views",
)

TOOL_CLASSES = {}
for _name in MUTATION_TOOLS:
    TOOL_CLASSES[_name] = MUTATION
for _name in READ_TOOLS:
    TOOL_CLASSES[_name] = READ
TOOL_CLASSES.update({
    "get_revit_status": STATUS,
    "read_document_levels": ADDRESSED_READ,
    "read_document_summary": ADDRESSED_READ,
    "activate_document": ACTIVATION,
    "list_model_worksets": FILE_READ,
    "open_model": PROCESS_OPEN,
    "execute_revit_code": D15,
    "discover_revit_targets": LOCAL,
    "get_revit_process_status": LOCAL,
    "start_revit": LOCAL,
})

# The named exception table, the only tools allowed to differ from the plain
# target/document contract. It is pinned as an exact set in the inventory test.
NO_TARGET_BY_DESIGN = {
    "discover_revit_targets": "lists the Revit processes; it is how a target is obtained",
    "get_revit_process_status": "local machine inventory; honors discovered ambiguity (02-19)",
    "start_revit": "launches a process; refuses on ambiguity or an inconclusive inventory (02-19)",
}

# Tools that render a new string from the reply and only then call format_response, so the
# bridge tag is lost on their SUCCESS path (named in 02-16). They name the answering process
# from the reply's own stamp and their error paths stay attributed.
PRERENDERED_SUCCESS = frozenset({
    "list_documents", "activate_document", "read_document_summary", "read_document_levels",
})

# ----------------------------------------------------------------- route classes
GUARDED = "guarded-mutation"
ACTIVE_READ = "active-document-read"
HTTP_THREAD = "http-thread"
REGISTRY_LIST = "registry-list"
REGISTRY_READ = "registry-addressed-read"
ACTIVATE = "registry-activation"
FILE_PREVIEW = "file-preview"
PROCESS_OPEN_ROUTE = "process-open"
D15_ROUTE = "d15-execute"

ROUTE_CLASSES = {}
for _route in (
    "/create_dimensions/", "/tag_walls/", "/create_line/", "/create_surface/", "/create_level/",
    "/color_splash/", "/clear_colors/", "/create_detail_line/", "/save_document/",
    "/create_sheet/", "/create_schedule/", "/export_document/", "/delete_elements/",
    "/modify_element/", "/export_ifc/", "/link_file/", "/create_duct/", "/create_pipe/",
    "/create_mep_system/", "/set_parameter/", "/place_family/", "/load_family/",
    "/edit_family/", "/create_room/", "/create_room_separation/", "/create_grid/",
    "/create_framing/", "/tag_elements/", "/transform_elements/", "/create_view/",
    "/set_active_view/",
):
    ROUTE_CLASSES[_route] = GUARDED
for _route in (
    "/ai_filter/", "/room_data/", "/material_quantities/", "/model_statistics/", "/clash_check/",
    "/list_category_parameters/", "/selected_elements/", "/project_parameters/",
    "/element_properties/", "/list_families/", "/list_family_categories/", "/list_levels/",
    "/get_view/", "/list_views/", "/current_view_info/", "/current_view_elements/",
):
    ROUTE_CLASSES[_route] = ACTIVE_READ
ROUTE_CLASSES.update({
    "/model_info/": HTTP_THREAD,
    "/status/": HTTP_THREAD,
    "/documents/": REGISTRY_LIST,
    "/document_summary/": REGISTRY_READ,
    "/document_levels/": REGISTRY_READ,
    "/activate_document/": ACTIVATE,
    "/model_worksets/": FILE_PREVIEW,
    "/open_model/": PROCESS_OPEN_ROUTE,
    "/execute_code/": D15_ROUTE,
})

# The two handlers that pyRevit runs on its HTTP thread because they declare none of
# uiapp, uidoc or doc (found in 02-04, recorded as follow-up concerns, deliberately not
# changed in 02-17). The allow-list is exact: a third such handler fails, and so does a
# stale entry once one of the two is fixed, so the exception cannot outlive its reason.
HTTP_THREAD_ALLOWLIST = {
    "/model_info/": ("model_info", "get_model_info", ()),
    "/status/": ("status", "revit_status", ("verbose",)),
}

# Which route classes a tool class may address.
ALLOWED_ROUTE_CLASSES = {
    MUTATION: {GUARDED},
    READ: {ACTIVE_READ, HTTP_THREAD, REGISTRY_LIST},
    STATUS: {HTTP_THREAD},
    ADDRESSED_READ: {REGISTRY_READ},
    ACTIVATION: {ACTIVATE},
    FILE_READ: {FILE_PREVIEW},
    PROCESS_OPEN: {PROCESS_OPEN_ROUTE},
    D15: {D15_ROUTE},
    LOCAL: {HTTP_THREAD},
}

# What a route may reach, by class. Reads must never reach a mutation primitive.
MUTATION_PRIMITIVES = frozenset({
    "Transaction", "TransactionGroup", "SubTransaction", "Commit", "Delete", "DeleteElements",
    "Save", "SaveAs", "SynchronizeWithCentral", "Close", "OpenAndActivateDocument",
    "OpenDocumentFile", "EditFamily", "LoadFamily",
})

# Mutations that legitimately open no project transaction: Save/SaveAs must run outside one
# (CLAUDE.md), LoadFamily is its own operation, and a view switch is a UI state change.
GUARDED_WITHOUT_TRANSACTION = frozenset({"/save_document/", "/load_family/", "/set_active_view/"})


# ------------------------------------------------------------------ tool discovery
class FakeMCP(object):
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


def register_everything(reply=None, image_reply=None):
    """Run the real discovery against a recording transport.

    Returns (tools by name, calls). Each call is (kind, path, body, options) with kind
    GET / POST / IMAGE. ``reply`` and ``image_reply`` may be a value or a callable taking
    (kind, path, body, options).
    """
    import tools as tools_package

    calls = []

    def answer(spec, kind, path, body, options, default):
        value = default if spec is None else spec
        return value(kind, path, body, options) if callable(value) else value

    async def revit_get(path, ctx=None, **options):
        calls.append(("GET", path, None, options))
        return answer(reply, "GET", path, None, options, {"status": "success"})

    async def revit_post(path, data, ctx=None, **options):
        calls.append(("POST", path, data, options))
        return answer(reply, "POST", path, data, options, {"status": "success"})

    async def revit_image(path, ctx=None, **options):
        calls.append(("IMAGE", path, None, options))
        return answer(image_reply if image_reply is not None else reply, "IMAGE", path, None,
                      options, {"status": "success"})

    server = FakeMCP()
    tools_package.register_tools(server, revit_get, revit_post, revit_image)
    return server.tools, calls


def manifest_names():
    with open(MANIFEST, encoding="utf-8") as handle:
        return sorted(line.strip() for line in handle if line.strip() and not line.startswith("#"))


def _literal_path(node):
    """The literal prefix of the first argument of a transport call."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        first = node.values[0] if node.values else None
        if isinstance(first, ast.Constant):
            return first.value
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format" and isinstance(node.func.value, ast.Constant)):
        return node.func.value.value
    return None


def _route_key(path):
    return re.split(r"[<{]", path, maxsplit=1)[0]


def tool_transport_calls():
    """{tool name: [(transport, route key)]} read from every tools/*_tools.py source."""
    found = {}
    for filename in sorted(os.listdir(TOOLS_DIR)):
        if not filename.endswith("_tools.py"):
            continue
        with open(os.path.join(TOOLS_DIR, filename), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool"
                       for d in node.decorator_list):
                continue
            rows = []
            for call in ast.walk(node):
                if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                        and call.func.id in ("revit_get", "revit_post", "revit_image")):
                    path = _literal_path(call.args[0]) if call.args else None
                    rows.append((call.func.id, _route_key(path) if path else None))
            found[node.name] = rows
    return found


# ------------------------------------------------------------------ route discovery
class Route(object):
    """One @api.route handler found in revit_mcp/<module>.py."""

    def __init__(self, module, path, methods, node, registrar, tree, defs):
        self.module = module
        self.path = path
        self.key = _route_key(path)
        self.methods = methods
        self.node = node
        self.name = node.name
        self.registrar = registrar
        self.tree = tree
        self.defs = defs
        self.args = [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]

    def calls_in(self, node=None):
        node = node or self.node
        return [c for c in ast.walk(node) if isinstance(c, ast.Call)]


def call_name(call):
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def revit_mcp_modules():
    """Module names startup.py's _domain_modules() would scan."""
    return sorted(e[:-3] for e in os.listdir(REVIT_MCP_DIR)
                  if e.endswith(".py") and not e.startswith("_"))


def parse_revit_module(name):
    with open(os.path.join(REVIT_MCP_DIR, name + ".py"), encoding="utf-8") as handle:
        return ast.parse(handle.read())


_REGISTRAR = re.compile(r"^register_\w+_routes$")


def module_registrars(tree):
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and _REGISTRAR.match(n.name)]


def route_inventory():
    """Every @api.route handler of every revit_mcp module, in registrar order.

    Fails loudly (AssertionError) if a route decorator sits outside a registrar, because such a
    handler is never registered and so is not part of any surface.
    """
    routes = []
    for name in revit_mcp_modules():
        tree = parse_revit_module(name)
        registrars = module_registrars(tree)
        defs = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                defs.setdefault(node.name, []).append(node)
        inside = set()
        for registrar in registrars:
            for node in ast.walk(registrar):
                if isinstance(node, ast.FunctionDef) and node is not registrar:
                    inside.add(id(node))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not (isinstance(decorator, ast.Call)
                        and getattr(decorator.func, "attr", "") == "route"):
                    continue
                assert id(node) in inside, (
                    "{}.{} has @api.route outside a register_*_routes function".format(
                        name, node.name))
                methods = []
                for keyword in decorator.keywords:
                    if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                        methods = [e.value for e in keyword.value.elts]
                registrar = [r for r in registrars if any(n is node for n in ast.walk(r))][0]
                routes.append(Route(name, decorator.args[0].value, methods, node,
                                    registrar.name, tree, defs))
    return routes


def reachable_calls(route):
    """Names called by a handler or by any same-module function it can reach by name."""
    seen = set()
    stack = [route.node]
    names = set()
    while stack:
        function = stack.pop()
        for call in ast.walk(function):
            if not isinstance(call, ast.Call):
                continue
            name = call_name(call)
            if name:
                names.add(name)
            if isinstance(call.func, ast.Name) and call.func.id in route.defs \
                    and call.func.id not in seen:
                seen.add(call.func.id)
                stack.extend(route.defs[call.func.id])
    return names


def minimal_kwargs():
    """Minimal valid arguments for every tool that the per-module forwarding suites cover.

    Read from the existing hand inventories so a tool covered there stays covered here; the
    rows for the tools those suites do not own are added below. A tool missing from both
    fails the inventory with an instruction.
    """
    import test_document_contracts as contracts
    import test_tool_forwarding_documents as documents
    import test_tool_forwarding_model as model
    import test_tool_forwarding_views as views

    merged = {}
    for table in (contracts.ALL_ADDRESSING_TOOLS, documents.TOOLS, model.TOOLS, views.TOOLS):
        for name, row in table.items():
            merged[name] = dict(row["minimal"])
    merged.update({
        "execute_revit_code": {"code": "print(1)"},
        "get_revit_status": {},
        "get_revit_model_info": {},
    })
    return merged
