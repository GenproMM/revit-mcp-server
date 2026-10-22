# -*- coding: utf-8 -*-
"""Explicit per-handler document guard on the mutating routes of document, documentation,
editing, interop and placement (plan 02-13; D-05, D-08, D-09, D-10, G1 explicit-route-only).

Offline evidence only. The real route modules are imported against a fake pyRevit and
registered through their real register_*_routes functions with a fake api, so a handler
that forgets to call revit_mcp.identity.mutation_document_or_response fails here: every
fixture row drives the handler the way pyRevit would (injected uiapp, doc, request by
name) and observes every document, collector, transaction, save and nested family
document the handler touched.

What this proves: the guard runs first and refuses before any side effect (no transaction,
no Save or SaveAs, no export or file output, no EditFamily); the work runs on the document
the guard resolved, never on the injected ``doc``; Save and SaveAs stay outside any
transaction; every reply names the document it ran on and the process; a reply for a save
reads the title and path from the resolved Document after the operation; edit_family names
the project and the nested family document it actually changed. What it does not prove: how
pyRevit dispatches these handlers, or how a real Document answers -- that is a live recheck
after a full Revit restart (02-18). Nothing here touches Revit.
"""

import importlib
import importlib.util
import inspect
import json
import sys
import types
from unittest.mock import MagicMock

import pytest

from revit_mcp import identity

IDENT = {"pid": 4242, "actual_port": 48885, "session_token": "tok-abc", "revit_version": "2024"}

BETA = u"\u0411\u0435\u0442\u0430"

# --------------------------------------------------------------- the classification
#
# Hand classification of every route in the five owned registrars. A route that is not
# listed here fails test_every_registered_route_is_classified, so a new route cannot
# slip in unguarded or be mislabelled silently. "{tmp}" in a body is a per-test directory.

REGISTRARS = {
    "document": "register_document_routes",
    "documentation": "register_documentation_routes",
    "editing": "register_editing_routes",
    "interop": "register_interop_routes",
    "placement": "register_placement_routes",
}

# (module, route) -> a body that gets past early validation and touches the document.
MUTATIONS = {
    ("document", "/save_document/"): {},
    ("documentation", "/create_sheet/"): {"sheet_name": "S"},
    ("documentation", "/create_schedule/"): {"category": "OST_Walls"},
    ("documentation", "/export_document/"): {"format": "pdf"},
    ("editing", "/delete_elements/"): {"element_ids": [1]},
    ("editing", "/modify_element/"): {"element_id": 1, "parameters": {"Mark": "A"}},
    ("interop", "/export_ifc/"): {"file_path": "out.ifc"},
    ("interop", "/link_file/"): {"file_path": "{tmp}/plan.dwg", "mode": "import"},
    ("placement", "/place_family/"): {"family_name": "F", "type_name": "T",
                                      "location": {"x": 0, "y": 0, "z": 0}},
    ("placement", "/load_family/"): {"file_path": "{tmp}/Door.rfa"},
    ("placement", "/edit_family/"): {"family_name": "Door", "parameters": {"Width": 900}},
}

# (module, route, method) -> the parameters it must keep: no uiapp, no guard, active document.
READS = {
    ("editing", "/selected_elements/", "GET"): ["doc", "uidoc"],
    ("placement", "/list_families/", "GET"): ["doc", "request"],
    ("placement", "/list_family_categories/", "GET"): ["doc"],
    ("placement", "/list_levels/", "GET"): ["doc"],
}

# A body each mutation answers with its own validation error, and that error's status.
# (body, status, path of the only open document)
ONLY_PATH = "C:/Models/Only.rvt"
EARLY_ERROR = {
    ("document", "/save_document/"): ({}, 400, ""),
    ("documentation", "/create_sheet/"): ({"sheet_name": "S"}, 404, ONLY_PATH),
    ("documentation", "/create_schedule/"): ({}, 400, ONLY_PATH),
    ("documentation", "/export_document/"): ({"format": "bmp"}, 400, ONLY_PATH),
    ("editing", "/delete_elements/"): ({}, 400, ONLY_PATH),
    ("editing", "/modify_element/"): ({}, 400, ONLY_PATH),
    ("interop", "/export_ifc/"): ({}, 400, ONLY_PATH),
    ("interop", "/link_file/"): ({}, 400, ONLY_PATH),
    ("placement", "/place_family/"): ({"unrelated": True}, 400, ONLY_PATH),
    ("placement", "/load_family/"): ({}, 400, ONLY_PATH),
    ("placement", "/edit_family/"): ({}, 400, ONLY_PATH),
}

MUTATION_IDS = ["{}:{}".format(module, route) for module, route in MUTATIONS]


def _symbol():
    symbol = MagicMock()
    symbol.Family.Name = "F"
    symbol.Name = "T"
    symbol.IsActive = True
    symbol.Category = None
    return symbol


def _title_block():
    block = MagicMock()
    block.Name = "TB"
    block.IsActive = True
    return block


def _view():
    view = MagicMock()
    view.Name = "Plan A"
    return view


# Routes that open a transaction on the document and succeed with HTTP 200:
# (collector items the route finds, body). The three routes with no project transaction
# (save_document, load_family, edit_family) are covered by their own tests below.
TRANSACTING = {
    ("documentation", "/create_sheet/"): ([_title_block], {"sheet_name": "S"}),
    ("documentation", "/create_schedule/"): ([], {"category": "OST_Walls"}),
    ("documentation", "/export_document/"): ([_view], {"view_name": "Plan A", "format": "dwg"}),
    ("editing", "/delete_elements/"): ([], {"element_ids": [1]}),
    ("editing", "/modify_element/"): ([], {"element_id": 1, "parameters": {"Mark": "A"}}),
    ("interop", "/export_ifc/"): ([], {"file_path": "out.ifc"}),
    ("interop", "/link_file/"): ([], {"file_path": "{tmp}/plan.dwg", "mode": "import"}),
    ("placement", "/place_family/"): ([_symbol], {"family_name": "F", "type_name": "T",
                                                  "location": {"x": 0, "y": 0, "z": 0}}),
}
TRANSACTING_IDS = ["{}:{}".format(module, route) for module, route in TRANSACTING]


# ------------------------------------------------------------------------- doubles


class FakeResponse(object):
    """pyRevit's Response: a mutable status and data pair."""

    def __init__(self, status=200, data=None):
        self.status = status
        self.data = data


class _Lifetime(object):
    def __init__(self, title, path):
        self.title = title
        self.path = path
        self.open = True


class _Touchable(object):
    """Anything whose use the event log records under its label."""


class RouteDocument(_Touchable):
    """A wrapper over one open lifetime. Anything the guard does not read is recorded
    as a touch (and raises when the world is set to explode), so a handler that works
    on the wrong document or before the guard is visible in ``world.events``. A method a
    test wants to behave (SaveAs, EditFamily) is a hook keyed by (label, name)."""

    IsLinked = False

    def __init__(self, world, lifetime):
        self._world = world
        self._lifetime = lifetime

    @property
    def label(self):
        return self._lifetime.title

    @property
    def Title(self):
        return self._lifetime.title

    @property
    def PathName(self):
        return self._lifetime.path

    @property
    def IsValidObject(self):
        return self._lifetime.open

    def Equals(self, other):
        return isinstance(other, RouteDocument) and other._lifetime is self._lifetime

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        self._world.record("attr", self, name)
        if self._world.explode:
            raise RuntimeError("document access failed: " + name)
        hook = self._world.hooks.get((self.label, name))
        if hook is not None:
            return lambda *args, **kwargs: hook(self, *args, **kwargs)
        return MagicMock(name=name)


class FamilyDoc(_Touchable):
    """The family document EditFamily opens: not an open project, never in the registry."""

    IsFamilyDocument = True

    def __init__(self, world, title, path=""):
        self._world = world
        self._title = title
        self._path = path
        self.FamilyManager = MagicMock(name="FamilyManager")

    @property
    def label(self):
        return "FAMILY:" + self._title

    @property
    def Title(self):
        return self._title

    @property
    def PathName(self):
        return self._path

    def Close(self, save):
        self._world.record("close", self, save)

    def LoadFamily(self, project, options):
        label = project.label if isinstance(project, _Touchable) else "?"
        self._world.record("load_into", self, label)
        if self._world.family_load_error is not None:
            raise self._world.family_load_error
        return True


class InjectedDocument(_Touchable):
    """The ``doc`` pyRevit injects. A handler that ignores the guard and uses it shows
    up as an event labelled INJECTED."""

    label = "INJECTED"

    def __init__(self, world):
        self._world = world

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        self._world.record("attr", self, name)
        return MagicMock(name=name)


class RouteApplication(object):
    def __init__(self, world):
        self._world = world
        self._open = []

    def open_document(self, title, path=""):
        lifetime = _Lifetime(title, path)
        self._open.append(lifetime)
        return RouteDocument(self._world, lifetime)

    def close_document(self, document):
        lifetime = document._lifetime
        if lifetime in self._open:
            lifetime.open = False
            self._open.remove(lifetime)

    @property
    def Documents(self):
        return [RouteDocument(self._world, lifetime) for lifetime in self._open]

    VersionNumber = "2024"


class RouteUIApp(object):
    def __init__(self, world, app):
        self._world = world
        self.app = app
        self.active = None

    @property
    def Application(self):
        return self.app

    @property
    def ActiveUIDocument(self):
        if self.active is None:
            return None
        return types.SimpleNamespace(Document=RouteDocument(self._world, self.active._lifetime))


class World(object):
    """One fake Revit process: documents, the injected uiapp/doc, and an event log."""

    def __init__(self, tmp):
        self.tmp = tmp
        self.events = []
        self.explode = False
        self.hooks = {}
        self.collector_items = []
        self.commit_status = "Committed"
        self.break_start = set()
        self.family_load_error = None
        self.app = RouteApplication(self)
        self.uiapp = RouteUIApp(self, self.app)
        self.injected = InjectedDocument(self)
        self.uidoc = types.SimpleNamespace(
            Selection=types.SimpleNamespace(GetElementIds=lambda: []))
        self.registry = identity.DocumentRegistry()

    def record(self, kind, doc, detail=None):
        label = getattr(doc, "label", "?") if isinstance(doc, _Touchable) else "?"
        self.events.append((kind, label, detail))

    def events_on(self, label):
        return [event for event in self.events if event[1] == label]

    def kinds(self, kind):
        return [event for event in self.events if event[0] == kind]

    def attrs(self, label):
        return [event[2] for event in self.events_on(label) if event[0] == "attr"]

    def open(self, title, path="", active=False):
        document = self.app.open_document(title, path)
        if active:
            self.uiapp.active = document
        return document

    def activate(self, document):
        self.uiapp.active = document

    def tokens(self):
        """Selectors of the open documents, in enumeration order (issues them on first use)."""
        snapshot = (self.app.Documents,
                    self.uiapp.ActiveUIDocument.Document if self.uiapp.active else None)
        listing = identity.current_document_descriptors(snapshot, self.registry)
        assert listing["ok"], listing
        return [entry["document"] for entry in listing["documents"]]


def make_db(world):
    class Transaction(object):
        def __init__(self, doc, name=""):
            world.record("transaction", doc, name)
            self.doc = doc
            self.started = False

        def Start(self):
            if world.explode or getattr(self.doc, "label", None) in world.break_start:
                raise RuntimeError("transaction could not start")
            self.started = True
            world.record("start", self.doc)

        def Commit(self):
            world.record("commit", self.doc)
            return world.commit_status

        def RollBack(self):
            world.record("rollback", self.doc)

        def HasStarted(self):
            return self.started

        def HasEnded(self):
            return False

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            world.record("txattr", self.doc, name)
            return MagicMock(name=name)

    class FilteredElementCollector(object):
        def __init__(self, doc, *args):
            world.record("collector", doc)
            if world.explode:
                raise RuntimeError("collector could not be created")

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            if name == "ToElements":
                return lambda: [make() for make in world.collector_items]
            return lambda *args, **kwargs: self

        def __iter__(self):
            return iter([make() for make in world.collector_items])

        def __len__(self):
            return len(world.collector_items)

    class FakeList(list):
        def Add(self, item):
            self.append(item)

    class IFailuresPreprocessor(object):
        pass

    class _DB(object):
        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            return MagicMock(name="DB." + name)

    db = _DB()
    db.Transaction = Transaction
    db.FilteredElementCollector = FilteredElementCollector
    db.IFailuresPreprocessor = IFailuresPreprocessor
    db.IFamilyLoadOptions = object
    db.TransactionStatus = types.SimpleNamespace(Committed="Committed", RolledBack="RolledBack")
    db.FakeList = FakeList
    return db


class HostAppTrap(object):
    """pyRevit's process-global HOST_APP. A handler must use the injected uiapp."""

    def __getattr__(self, name):
        raise AssertionError("HOST_APP." + name + " was read; use the injected uiapp")


ROUTE_MODULES = ("utils", "document", "documentation", "editing", "interop", "placement")


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A fake Revit process with the route modules imported against a fake pyRevit.

    ``world.guard_calls`` counts calls of the production guard (it still runs for real),
    so a read that gained a guard, or a mutation that lost its call, is visible. The
    user profile points into a scratch directory so no export ever writes outside it.
    """
    w = World(tmp_path)
    w.guard_calls = []
    for name in ("plan.dwg", "Door.rfa", "model.rvt"):
        (tmp_path / name).write_bytes(b"x")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    real_guard = identity.mutation_document_or_response

    def counting_guard(*args, **kwargs):
        w.guard_calls.append((args, kwargs))
        return real_guard(*args, **kwargs)

    monkeypatch.setattr(identity, "mutation_document_or_response", counting_guard)
    monkeypatch.setattr(identity, "get_document_registry", lambda store=None: w.registry)
    monkeypatch.setattr(identity, "process_identity_or_error",
                        lambda uiapp=None: (dict(IDENT), None))

    def make_response(data=None, status=200, headers=None):
        return FakeResponse(status, data)

    db = make_db(w)
    fake_pyrevit = types.SimpleNamespace(
        routes=types.SimpleNamespace(make_response=make_response),
        revit=MagicMock(name="revit"),
        DB=db,
        HOST_APP=HostAppTrap(),
    )
    monkeypatch.setitem(sys.modules, "pyrevit", fake_pyrevit)

    class _Reference(object):
        def __getitem__(self, _type):
            return lambda: types.SimpleNamespace(Value=None)

    monkeypatch.setitem(sys.modules, "clr", types.SimpleNamespace(Reference=_Reference()))
    generic = types.ModuleType("System.Collections.Generic")
    generic.List = db.FakeList
    collections_mod = types.ModuleType("System.Collections")
    collections_mod.Generic = generic
    system = types.ModuleType("System")
    system.Collections = collections_mod
    monkeypatch.setitem(sys.modules, "System", system)
    monkeypatch.setitem(sys.modules, "System.Collections", collections_mod)
    monkeypatch.setitem(sys.modules, "System.Collections.Generic", generic)

    names = ["revit_mcp." + name for name in ROUTE_MODULES]
    saved = dict((name, sys.modules.pop(name, None)) for name in names)
    w.routes = {}
    try:
        yield w
    finally:
        for name in names:
            sys.modules.pop(name, None)
            if saved[name] is not None:
                sys.modules[name] = saved[name]


def load(world, module_name):
    """Register one module through its real registrar; returns {(route, method): handler}."""
    if module_name in world.routes:
        return world.routes[module_name]
    module = importlib.import_module("revit_mcp." + module_name)
    captured = {}

    class FakeApi(object):
        def route(self, path, methods=None):
            def register(fn):
                for method in methods or ():
                    captured[(path, method)] = fn
                return fn
            return register

    getattr(module, REGISTRARS[module_name])(FakeApi())
    world.routes[module_name] = captured
    return captured


def handler_of(world, module_name, route, method="POST"):
    return load(world, module_name)[(route, method)]


def request_of(body):
    if body is None:
        return types.SimpleNamespace(data=None)
    return types.SimpleNamespace(data=json.dumps(body).encode("utf-8"))


def call(world, fn, body=None):
    """Invoke a handler the way pyRevit does: injected arguments by name."""
    available = {"uiapp": world.uiapp, "doc": world.injected, "uidoc": world.uidoc,
                 "request": request_of(body)}
    parameters = inspect.signature(fn).parameters
    return fn(**dict((name, available[name]) for name in parameters))


def fill(world, value):
    """Substitute this test's scratch directory into a body."""
    if isinstance(value, str):
        return value.replace("{tmp}", world.tmp.as_posix())
    if isinstance(value, dict):
        return dict((key, fill(world, item)) for key, item in value.items())
    if isinstance(value, list):
        return [fill(world, item) for item in value]
    return value


def body_of(world, key, **extra):
    body = fill(world, MUTATIONS[key])
    body.update(extra)
    return body


def two_documents(world, active="beta"):
    alpha = world.open("Alpha", "C:/Models/Alpha.rvt")
    beta = world.open(BETA, "")
    world.activate(beta if active == "beta" else alpha)
    return alpha, beta, world.tokens()


ATTRIBUTION_KEYS = ("document", "process_identity")


def without_attribution(data):
    return dict((key, value) for key, value in data.items() if key not in ATTRIBUTION_KEYS)


# ------------------------------------------------------------------ classification


@pytest.mark.parametrize("module_name", sorted(REGISTRARS))
def test_every_registered_route_is_classified(world, module_name):
    registered = set(load(world, module_name))
    expected = set((route, "POST") for (module, route) in MUTATIONS if module == module_name)
    expected |= set((route, method) for (module, route, method) in READS if module == module_name)
    assert registered == expected, (
        "classify every route of revit_mcp/{}.py as a mutation or a read here".format(module_name))


def test_every_mutation_has_an_early_error_row_and_every_transacting_row_is_a_mutation():
    assert set(EARLY_ERROR) == set(MUTATIONS)
    assert set(TRANSACTING) <= set(MUTATIONS)
    assert set(MUTATIONS) - set(TRANSACTING) == {
        ("document", "/save_document/"), ("placement", "/load_family/"),
        ("placement", "/edit_family/")}, "these three open no project transaction"


# ------------------------------------------------------------------ API-context pin


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_mutation_handler_declares_the_api_context_arguments(world, key):
    """pyRevit runs a handler in the Revit API context only if it declares uiapp, uidoc or
    doc. The injected doc and request stay; uiapp is added so the guard never needs HOST_APP."""
    module_name, route = key
    parameters = list(inspect.signature(handler_of(world, module_name, route)).parameters)
    assert parameters == ["uiapp", "doc", "request"]


@pytest.mark.parametrize("key", list(READS), ids=["{}:{}".format(k[0], k[1]) for k in READS])
def test_reads_keep_their_signature_and_are_not_guarded(world, key):
    module_name, route, method = key
    fn = handler_of(world, module_name, route, method)
    assert list(inspect.signature(fn).parameters) == READS[key]
    reply = call(world, fn, None)
    assert world.guard_calls == []
    assert reply.status == 200
    assert "document" not in reply.data and "process_identity" not in reply.data


@pytest.mark.parametrize("route", ["/list_families/", "/list_family_categories/", "/list_levels/"])
def test_placement_reads_still_read_the_injected_document(world, route):
    call(world, handler_of(world, "placement", route, "GET"), None)
    assert world.events_on("INJECTED"), "a read stays on the active (injected) document"


# ------------------------------------------------------------- refusals (G1, D-09/D-10)


def assert_refused(world, reply, status, code):
    assert reply.status == status
    assert reply.data["error"] and reply.data["error_code"] == code
    assert reply.data["process_identity"] == IDENT
    assert world.events == [], "a refused call opened a transaction or touched a document"


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_no_open_document_refuses_503_before_any_side_effect(world, key):
    reply = call(world, handler_of(world, *key), body_of(world, key))
    assert_refused(world, reply, 503, "no-open-document")


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_several_documents_without_a_selector_refuse_400_and_list_them(world, key):
    _, _, tokens = two_documents(world)
    reply = call(world, handler_of(world, *key), body_of(world, key))
    assert_refused(world, reply, 400, "document-selector-required")
    assert [c["document"] for c in reply.data["candidates"]] == tokens


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_explicit_inactive_document_is_exactly_412_with_zero_side_effects(world, key):
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, *key), body_of(world, key, document=tokens[0]))
    assert_refused(world, reply, 412, "document-not-active")
    assert reply.data["active_document"] == tokens[1]


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_closed_document_is_refused_404_and_never_replaced_by_the_survivor(world, key):
    alpha, beta, tokens = two_documents(world, active="beta")
    world.app.close_document(alpha)
    reply = call(world, handler_of(world, *key), body_of(world, key, document=tokens[0]))
    assert_refused(world, reply, 404, "document-closed")


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
@pytest.mark.parametrize("selector", ["Alpha", "", None, 7, ["doc1.x.1"]],
                         ids=["title", "empty", "null", "number", "list"])
def test_an_invalid_selector_is_400_and_never_decays_into_the_sole_document(world, key, selector):
    world.open("Alpha", "C:/Models/Alpha.rvt", active=True)
    world.tokens()
    reply = call(world, handler_of(world, *key), body_of(world, key, document=selector))
    assert_refused(world, reply, 400, "document-selector-invalid")


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_refusal_without_process_identity_says_why_and_still_refuses(world, key, monkeypatch):
    monkeypatch.setattr(identity, "process_identity_or_error",
                        lambda uiapp=None: (None, "no retained RoutesServer"))
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, *key), body_of(world, key, document=tokens[0]))
    assert reply.status == 412 and world.events == []
    assert reply.data["identity_error"] == "no retained RoutesServer"
    assert "process_identity" not in reply.data


# --- a refused request produces no file output either (T-02-03: guard before file output)


def test_a_refused_save_as_creates_no_directory_and_saves_nothing(world):
    _, _, tokens = two_documents(world, active="beta")
    target = world.tmp / "never" / "Out.rvt"
    reply = call(world, handler_of(world, "document", "/save_document/"),
                 {"file_path": target.as_posix(), "document": tokens[0]})
    assert_refused(world, reply, 412, "document-not-active")
    assert not (world.tmp / "never").exists()


def test_a_refused_ifc_export_creates_no_directory_and_exports_nothing(world):
    _, _, tokens = two_documents(world, active="beta")
    target = world.tmp / "never" / "out.ifc"
    reply = call(world, handler_of(world, "interop", "/export_ifc/"),
                 {"file_path": target.as_posix(), "document": tokens[0]})
    assert_refused(world, reply, 412, "document-not-active")
    assert not (world.tmp / "never").exists()


def test_a_refused_document_export_creates_no_export_directory(world):
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 {"format": "pdf", "document": tokens[0]})
    assert_refused(world, reply, 412, "document-not-active")
    assert not (world.tmp / "Documents").exists()


# ------------------------------------------------------------ guarded run + attribution


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_active_selection_runs_on_the_resolved_document_and_names_it(world, key):
    alpha, beta, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, *key), body_of(world, key, document=tokens[1]))
    assert len(world.guard_calls) == 1
    assert world.events_on("INJECTED") == [], "the handler worked on the injected doc, not the guard's"
    assert world.events_on("Alpha") == []
    assert world.events_on(BETA), "the handler never touched the resolved document"
    assert reply.data["document"] == {"document": tokens[1], "title": BETA, "path": "",
                                      "active": True, "saved": False}
    assert reply.data["process_identity"] == IDENT


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_sole_active_document_is_used_without_a_selector_and_named(world, key):
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, *key), body_of(world, key))
    assert world.events_on("INJECTED") == [] and world.events_on("Only")
    assert reply.data["document"]["document"] == token
    assert reply.data["document"]["path"] == ONLY_PATH
    assert reply.data["process_identity"] == IDENT


def is_failure(reply):
    return reply.status >= 400 or bool(reply.data.get("error")) or reply.data.get("status") == "error"


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_failure_after_the_guard_still_names_the_document_it_ran_on(world, key):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.explode = True
    reply = call(world, handler_of(world, *key), body_of(world, key))
    assert is_failure(reply)
    assert reply.data["document"]["title"] == "Only"
    assert reply.data["process_identity"] == IDENT


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_validation_error_after_the_guard_is_attributed_too(world, key):
    body, status, path = EARLY_ERROR[key]
    world.open("Only", path, active=True)
    world.tokens()
    reply = call(world, handler_of(world, *key), fill(world, body))
    assert reply.status == status and reply.data["error"]
    assert reply.data["document"]["title"] == "Only"
    assert reply.data["process_identity"] == IDENT


# ----------------------------------------------- transactions: right document, warnings off


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_a_guarded_success_opens_its_transaction_on_the_resolved_document(world, key):
    items, body = TRANSACTING[key]
    world.collector_items = list(items)
    two_documents(world, active="beta")
    tokens = world.tokens()
    reply = call(world, handler_of(world, *key), dict(fill(world, body), document=tokens[1]))
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["document"]["document"] == tokens[1]
    assert [event[1] for event in world.kinds("transaction")] == [BETA]
    assert world.events_on("INJECTED") == [] and world.events_on("Alpha") == []
    assert world.kinds("commit")


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_suppress_warnings_comes_immediately_after_start(world, key):
    items, body = TRANSACTING[key]
    world.collector_items = list(items)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    call(world, handler_of(world, *key), fill(world, body))
    starts = [i for i, event in enumerate(world.events) if event[0] == "start"]
    assert starts, "the route opened no transaction"
    for index in starts:
        assert world.events[index + 1][:2] == ("txattr", "Only"), "no suppress_warnings after Start"
        assert world.events[index + 1][2] == "GetFailureHandlingOptions"


def test_a_guarded_success_keeps_its_original_body_keys(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "editing", "/delete_elements/"),
                 {"element_ids": [1]})
    assert reply.status == 200
    assert sorted(without_attribution(reply.data)) == [
        "cascaded_ids", "deleted_count", "deleted_ids", "message", "status"]


def test_rolled_back_409_stays_an_error_and_names_the_document(world):
    """The load-bearing 409: modify_element's rollback must not turn into a success."""
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "editing", "/modify_element/"),
                 {"element_id": 1, "parameters": {"Mark": "A"}})
    assert reply.status == 409
    assert reply.data["status"] == "rolled_back"
    assert "attempted_changes" in reply.data and reply.data["message"]
    assert reply.data["document"]["title"] == "Only"
    assert reply.data["process_identity"] == IDENT


def test_a_rolled_back_modify_on_a_refused_document_never_starts_a_transaction(world):
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, "editing", "/modify_element/"),
                 {"element_id": 1, "parameters": {"Mark": "A"}, "document": tokens[0]})
    assert reply.status == 412 and world.kinds("transaction") == []


def test_a_transaction_error_still_rolls_back_and_names_the_document(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.break_start.add("Only")
    reply = call(world, handler_of(world, "editing", "/delete_elements/"), {"element_ids": [1]})
    assert reply.status == 500
    assert reply.data["document"]["title"] == "Only"
    assert world.kinds("commit") == []


def test_export_document_reports_the_view_it_exported_and_the_document_it_came_from(world):
    world.collector_items = [_view]
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 {"view_name": "Plan A", "format": "dwg"})
    assert reply.status == 200
    assert reply.data["exported"]["view_name"] == "Plan A"
    assert reply.data["document"]["document"] == token
    assert "Export" in world.attrs("Only")


def test_export_ifc_runs_the_export_on_the_resolved_document_only(world):
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, "interop", "/export_ifc/"),
                 {"file_path": "out.ifc", "document": tokens[1]})
    assert reply.status == 200 and reply.data["document"]["title"] == BETA
    assert "Export" in world.attrs(BETA)
    assert world.attrs("Alpha") == [] and world.events_on("INJECTED") == []


def test_link_file_names_the_document_it_linked_into(world):
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, "interop", "/link_file/"),
                 {"file_path": (world.tmp / "plan.dwg").as_posix(), "mode": "import",
                  "document": tokens[1]})
    assert reply.status == 200 and reply.data["document"]["title"] == BETA
    assert "Import" in world.attrs(BETA) and world.attrs("Alpha") == []


# --------------------------------------------------------------- save and save-as


def test_save_document_source_opens_no_transaction():
    path = importlib.util.find_spec("revit_mcp.document").origin
    with open(path, "rb") as handle:
        source = handle.read().decode("utf-8")
    assert "DB.Transaction" not in source and "TransactionGroup" not in source


def test_save_in_place_saves_the_resolved_document_outside_any_transaction(world):
    two_documents(world, active="alpha")
    tokens = world.tokens()
    reply = call(world, handler_of(world, "document", "/save_document/"), {"document": tokens[0]})
    assert reply.status == 200 and reply.data["operation"] == "save"
    assert "Save" in world.attrs("Alpha")
    assert world.attrs(BETA) == [] and world.events_on("INJECTED") == []
    assert world.kinds("transaction") == [] and world.kinds("start") == []
    assert reply.data["file_path"] == "C:/Models/Alpha.rvt"
    assert reply.data["document"] == {"document": tokens[0], "title": "Alpha",
                                      "path": "C:/Models/Alpha.rvt", "active": True,
                                      "saved": True}
    assert reply.data["process_identity"] == IDENT


def test_save_as_runs_outside_any_transaction_and_names_where_the_document_now_lives(world):
    _, _, tokens = two_documents(world, active="alpha")
    requested = (world.tmp / "saved" / "Alpha2.rvt").as_posix()

    def lands_where_asked(document, *args, **kwargs):
        document._lifetime.path = requested

    world.hooks[("Alpha", "SaveAs")] = lands_where_asked
    reply = call(world, handler_of(world, "document", "/save_document/"),
                 {"file_path": requested, "document": tokens[0]})
    assert reply.status == 200 and reply.data["operation"] == "save_as"
    assert world.kinds("transaction") == [] and world.kinds("start") == []
    assert "SaveAs" in world.attrs("Alpha") and "Save" not in world.attrs("Alpha")
    assert world.attrs(BETA) == [] and world.events_on("INJECTED") == []
    # read from the resolved Document after the operation, not copied from the request
    assert reply.data["document"]["document"] == tokens[0]
    assert reply.data["document"]["path"] == requested and reply.data["document"]["saved"] is True
    assert reply.data["file_path"] == requested
    assert reply.data["previous_path"] == "C:/Models/Alpha.rvt"
    assert "actual_path" not in reply.data


def test_save_as_that_lands_elsewhere_never_claims_the_requested_path(world):
    """Prohibition: do not report a save as affecting the requested path when the actual
    document ended up somewhere else."""
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    requested = (world.tmp / "asked.rvt").as_posix()
    actual = (world.tmp / "actually.rvt").as_posix()

    def lands_elsewhere(document, *args, **kwargs):
        document._lifetime.path = actual

    world.hooks[("Only", "SaveAs")] = lands_elsewhere
    reply = call(world, handler_of(world, "document", "/save_document/"), {"file_path": requested})
    assert reply.status == 200
    assert reply.data["document"]["path"] == actual
    assert reply.data["file_path"] == actual
    assert reply.data["requested_file_path"] == requested
    assert requested not in reply.data["message"]


def test_a_failed_save_as_names_the_document_with_the_path_it_still_has(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()

    def refuses(document, *args, **kwargs):
        raise RuntimeError("disk full")

    world.hooks[("Only", "SaveAs")] = refuses
    reply = call(world, handler_of(world, "document", "/save_document/"),
                 {"file_path": (world.tmp / "x.rvt").as_posix()})
    assert reply.status == 500 and "disk full" in reply.data["error"]
    assert reply.data["document"]["title"] == "Only"
    assert reply.data["document"]["path"] == ONLY_PATH
    assert world.kinds("transaction") == []


def test_save_never_touches_a_document_other_than_the_resolved_one(world):
    """Two documents open, one explicitly selected: the other is neither read nor saved,
    and neither is the injected doc (which pyRevit points at whatever is active)."""
    _, _, tokens = two_documents(world, active="alpha")
    call(world, handler_of(world, "document", "/save_document/"), {"document": tokens[0]})
    assert world.events_on(BETA) == [] and world.events_on("INJECTED") == []


def test_a_never_saved_document_still_answers_400_and_is_attributed(world):
    world.open(BETA, "", active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "document", "/save_document/"), {})
    assert reply.status == 400 and "never been saved" in reply.data["error"]
    assert reply.data["document"]["document"] == token and reply.data["document"]["saved"] is False
    assert "Save" not in world.attrs(BETA) and "SaveAs" not in world.attrs(BETA)


# ------------------------------------------------------------------------ load_family


def test_load_family_loads_into_the_resolved_document_and_names_it(world):
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, "placement", "/load_family/"),
                 {"file_path": (world.tmp / "Door.rfa").as_posix(), "document": tokens[1]})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert "LoadFamily" in world.attrs(BETA)
    assert world.attrs("Alpha") == [] and world.events_on("INJECTED") == []
    assert world.kinds("transaction") == [], "LoadFamily manages its own transaction"
    assert reply.data["document"]["document"] == tokens[1]


def test_load_family_refusal_loads_nothing(world):
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, "placement", "/load_family/"),
                 {"file_path": (world.tmp / "Door.rfa").as_posix(), "document": tokens[0]})
    assert_refused(world, reply, 412, "document-not-active")


# ------------------------------------------------------------- edit_family: nested documents


def _family_item():
    family = MagicMock()
    family.Name = "Door"
    family.IsEditable = True
    return family


def arm_family(world, title="Door.rfa", path="C:/Lib/Door.rfa", project="Only"):
    world.collector_items = [_family_item]
    family_doc = FamilyDoc(world, title, path)
    opened = []

    def edit_family(document, target):
        opened.append(target)
        return family_doc

    world.hooks[(project, "EditFamily")] = edit_family
    return family_doc


def family_entry(**fields):
    entry = {"role": "family", "title": "Door.rfa", "path": "C:/Lib/Door.rfa",
             "is_family_document": True, "saved": False}
    entry.update(fields)
    return entry


def project_entry(token, **fields):
    entry = {"role": "project", "document": token, "title": "Only", "path": ONLY_PATH,
             "active": True, "saved": True}
    entry.update(fields)
    return entry


EDIT_BODY = {"family_name": "Door", "parameters": {"Width": 900}}


def test_edit_family_reports_the_project_and_the_family_document_it_changed(world):
    arm_family(world)
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "placement", "/edit_family/"), EDIT_BODY)
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["reloaded"] is True
    assert reply.data["documents_changed"] == [
        project_entry(token, changed=True), family_entry(changed=True)]
    assert reply.data["document"]["document"] == token
    assert reply.data["process_identity"] == IDENT
    # the family's own transaction ran on the FAMILY document, with warnings suppressed
    family_label = "FAMILY:Door.rfa"
    assert [event[1] for event in world.kinds("transaction")] == [family_label]
    start = [i for i, event in enumerate(world.events) if event[0] == "start"][0]
    assert world.events[start + 1][:3] == ("txattr", family_label, "GetFailureHandlingOptions")
    # the project got no transaction; the family was loaded back into the RESOLVED document
    assert world.events_on("Only") and not [e for e in world.events_on("Only")
                                            if e[0] in ("transaction", "start", "commit")]
    assert ("load_into", family_label, "Only") in world.events
    assert ("close", family_label, False) in world.events
    assert world.events_on("INJECTED") == []


def test_edit_family_labels_the_right_project_when_several_documents_are_open(world):
    arm_family(world, project=BETA)
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, "placement", "/edit_family/"),
                 dict(EDIT_BODY, document=tokens[1]))
    assert reply.status == 200
    project, family = reply.data["documents_changed"]
    assert project["document"] == tokens[1] and project["title"] == BETA and project["changed"]
    assert family["title"] == "Door.rfa" and family["changed"] is True
    assert ("load_into", "FAMILY:Door.rfa", BETA) in world.events
    assert world.events_on("Alpha") == [] and world.events_on("INJECTED") == []


def test_edit_family_without_reload_changes_the_family_in_memory_only(world):
    arm_family(world)
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "placement", "/edit_family/"),
                 dict(EDIT_BODY, reload=False))
    assert reply.status == 200 and reply.data["reloaded"] is False
    assert reply.data["documents_changed"] == [
        project_entry(token, changed=False), family_entry(changed=True)]
    assert world.kinds("load_into") == []


def test_edit_family_reload_failure_is_a_500_that_says_the_project_did_not_change(world):
    arm_family(world)
    world.family_load_error = RuntimeError("load refused")
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "placement", "/edit_family/"), EDIT_BODY)
    assert reply.status == 500 and "reload failed" in reply.data["error"]
    assert reply.data["documents_changed"] == [
        project_entry(token, changed=False), family_entry(changed=True)]
    assert ("close", "FAMILY:Door.rfa", False) in world.events
    assert reply.data["process_identity"] == IDENT


def test_edit_family_that_fails_to_start_its_transaction_changed_nothing(world):
    arm_family(world)
    world.break_start.add("FAMILY:Door.rfa")
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "placement", "/edit_family/"), EDIT_BODY)
    assert reply.status == 500
    assert reply.data["documents_changed"] == [
        project_entry(token, changed=False), family_entry(changed=False)]
    assert ("close", "FAMILY:Door.rfa", False) in world.events, "the family document is closed"
    assert world.kinds("load_into") == []


def test_edit_family_with_an_unknown_type_rolls_back_and_changed_nothing(world):
    arm_family(world)
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "placement", "/edit_family/"),
                 {"family_name": "Door", "type_name": "Nope", "parameters": {"Width": 900}})
    assert reply.status == 404 and "not found in family" in reply.data["error"]
    assert reply.data["documents_changed"] == [
        project_entry(token, changed=False), family_entry(changed=False)]
    assert ("rollback", "FAMILY:Door.rfa", None) in world.events


def test_edit_family_that_never_opens_a_family_lists_only_the_unchanged_project(world):
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "placement", "/edit_family/"), EDIT_BODY)
    assert reply.status == 404 and "not loaded" in reply.data["error"]
    assert reply.data["documents_changed"] == [project_entry(token, changed=False)]


def test_edit_family_refusal_opens_no_family_and_reports_no_change(world):
    arm_family(world)
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, "placement", "/edit_family/"),
                 dict(EDIT_BODY, document=tokens[0]))
    assert_refused(world, reply, 412, "document-not-active")
    assert "documents_changed" not in reply.data


# ------------------------------------------------------------------- helper contracts


def test_current_descriptor_rereads_title_and_path_from_the_document():
    lifetime = _Lifetime("Old", "")
    world_stub = types.SimpleNamespace(record=lambda *a, **k: None, explode=False, hooks={})
    document = RouteDocument(world_stub, lifetime)
    before = {"document": "doc1.a.1", "title": "Old", "path": "", "active": True, "saved": False}
    lifetime.title, lifetime.path = u"\u041d\u043e\u0432\u0430\u044f", "C:/Models/New.rvt"
    after = identity.current_descriptor(before, document)
    assert after == {"document": "doc1.a.1", "title": u"\u041d\u043e\u0432\u0430\u044f",
                     "path": "C:/Models/New.rvt", "active": True, "saved": True}
    assert before["title"] == "Old" and after is not before


def test_current_descriptor_keeps_the_old_values_when_the_document_cannot_be_read():
    class Broken(object):
        @property
        def Title(self):
            raise RuntimeError("invalid object")

        @property
        def PathName(self):
            raise RuntimeError("invalid object")

    before = {"document": "doc1.a.1", "title": "T", "path": "P", "active": True, "saved": True}
    assert identity.current_descriptor(before, Broken()) == before
    assert identity.current_descriptor(before, None) == before


def test_family_document_info_reads_title_and_path_and_never_raises():
    class Fam(object):
        Title = "Door.rfa"
        PathName = None

    assert identity.family_document_info(Fam()) == {
        "title": "Door.rfa", "path": "", "is_family_document": True}

    class Broken(object):
        @property
        def Title(self):
            raise RuntimeError("closed")

    info = identity.family_document_info(Broken())
    assert info["is_family_document"] is True and info["title"] == "Unnamed"
