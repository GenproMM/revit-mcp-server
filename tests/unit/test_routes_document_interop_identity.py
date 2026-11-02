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
import os
import sys
import time
import types
from unittest.mock import MagicMock

import pytest

from gate_support import TEST_ROUTE, TEST_SECRET, configure_gate, enveloped_body, request_of
from revit_mcp import identity, trust
from revit_mcp.textutils import classify_outcome

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
        value = self._world.values.get((self.label, name))
        if value is not None:
            return value
        hook = self._world.hooks.get((self.label, name)) or self._world.hooks.get((None, name))
        if hook is not None:
            return lambda *args, **kwargs: hook(self, *args, **kwargs)
        return MagicMock(name=name)


class FakeFamParam(object):
    """A family parameter edit_family can write (or, read-only, cannot)."""

    StorageType = "String"

    def __init__(self, read_only=False):
        self.IsReadOnly = read_only


class FakeFamilyManager(object):
    """A FamilyManager with one writable parameter, Width, and one type, Default.
    ``params`` is the table get_Parameter answers from; tests add or replace entries."""

    def __init__(self):
        self.params = {"Width": FakeFamParam()}
        self.Types = [types.SimpleNamespace(Name="Default")]
        self.CurrentType = self.Types[0]
        self.set_calls = []

    def get_Parameter(self, name):
        return self.params.get(name)

    def Set(self, param, value):
        self.set_calls.append(value)

    def NewType(self, name):
        created = types.SimpleNamespace(Name=name)
        self.Types.append(created)
        return created


class FamilyDoc(_Touchable):
    """The family document EditFamily opens: not an open project, never in the registry."""

    IsFamilyDocument = True

    def __init__(self, world, title, path=""):
        self._world = world
        self._title = title
        self._path = path
        self.FamilyManager = FakeFamilyManager()

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
        # (label, name) -> an object handed back as that attribute (a hook answers a call;
        # a value answers an attribute that is itself used as an object, like doc.Create).
        self.values = {}
        self.collector_items = []
        self.commit_status = "Committed"
        self.break_start = set()
        self.family_load_error = None
        self.transactions = []
        # The element id doc.Import / doc.Link hand back through the out-reference.
        self.imported_id = 77
        self.sets = []
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
            self.status = "Uninitialized"
            world.transactions.append(self)

        def Start(self):
            if world.explode or getattr(self.doc, "label", None) in world.break_start:
                raise RuntimeError("transaction could not start")
            self.started = True
            self.status = "Started"
            world.record("start", self.doc)

        def Commit(self):
            world.record("commit", self.doc)
            self.status = world.commit_status
            return world.commit_status

        def RollBack(self):
            world.record("rollback", self.doc)
            self.status = "RolledBack"

        def GetStatus(self):
            # A real method, not __getattr__, so no "txattr" event is recorded and
            # test_suppress_warnings_comes_immediately_after_start is unaffected.
            return self.status

        def HasStarted(self):
            return self.started

        def HasEnded(self):
            return self.status in ("Committed", "RolledBack")

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
    db.StorageType = types.SimpleNamespace(String="String", Integer="Integer",
                                           Double="Double", ElementId="ElementId")
    # Distinguishable ids: delete_elements builds an id per input and reports it back.
    db.ElementId = MagicMock(
        name="DB.ElementId", side_effect=lambda value: types.SimpleNamespace(Value=int(value)))
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
    # Phase 5: the Revit-side gate state is configured and every request carries the
    # envelope, exactly as production delivers it once the bridge envelopes every POST.
    configure_gate(monkeypatch)
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
            def make():
                # What doc.Import / doc.Link leave in the out-reference: an ElementId, or nothing.
                imported = w.imported_id
                value = None if imported is None else types.SimpleNamespace(Value=imported)
                return types.SimpleNamespace(Value=value)
            return make

    monkeypatch.setitem(sys.modules, "clr", types.SimpleNamespace(Reference=_Reference()))
    generic = types.ModuleType("System.Collections.Generic")
    generic.List = db.FakeList
    collections_mod = types.ModuleType("System.Collections")
    collections_mod.Generic = generic
    system = types.ModuleType("System")
    system.Collections = collections_mod
    system.Int64 = int  # make_element_id builds DB.ElementId(System.Int64(n))
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


def route_of(world, fn):
    """The route a handler was registered under: pyRevit's request.path is that API-relative route.

    A handler the suite did not register falls back to TEST_ROUTE, which the request and its
    permit then share, so the pair is always consistent.
    """
    for captured in world.routes.values():
        for (route, _method), candidate in captured.items():
            if candidate is fn:
                return route
    return TEST_ROUTE


def call(world, fn, body=None, request=None):
    """Invoke a handler the way pyRevit does: injected arguments by name.

    ``request`` is a prebuilt request object (the gate tests build their own); without
    one the body travels with the Phase 5 envelope (gate_support.request_of).
    """
    if request is None:
        request = request_of(body, route=route_of(world, fn))
    available = {"uiapp": world.uiapp, "doc": world.injected, "uidoc": world.uidoc,
                 "request": request}
    parameters = inspect.signature(fn).parameters
    if "document" in parameters:
        available["uiapp"] = None
    return fn(**dict((name, available[name]) for name in parameters if name in available))


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


class FakeParam(object):
    """A string parameter modify_element can write (or, read-only, cannot)."""

    def __init__(self, world, read_only=False):
        self._world = world
        self.IsReadOnly = read_only
        self.StorageType = "String"
        self.value = ""

    def AsString(self):
        return self.value

    def Set(self, value):
        self._world.sets.append(value)
        self.value = value
        return True


class FakeElement(object):
    """An element GetElement answers, with the parameters it was armed with."""

    def __init__(self, world, ident, params):
        self.Id = types.SimpleNamespace(Value=ident)
        self._params = params
        self.Parameters = [types.SimpleNamespace(Definition=types.SimpleNamespace(Name=name))
                           for name in params]

    def LookupParameter(self, name):
        return self._params.get(name)


def arm(world, items=(), missing=(), read_only=False, extra_params=None):
    """Collector results and the element GetElement answers, so a route reaches a real
    success. ``missing`` lists element ids GetElement answers None for; every other id is
    an element whose ``Mark`` parameter is a writable string (read-only when asked)."""
    world.collector_items = list(items)

    def get_element(doc, eid):
        value = getattr(eid, "Value", None)
        if value in missing:
            return None
        params = {"Mark": FakeParam(world, read_only=read_only)}
        params.update(extra_params or {})
        return FakeElement(world, value if isinstance(value, int) else 1, params)

    world.hooks[(None, "GetElement")] = get_element


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
    assert list(inspect.signature(fn).parameters) == READS[key] + ["uiapp", "document"]
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
    arm(world, items)
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
    arm(world, items)
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
        "cascaded_ids", "deleted_count", "deleted_ids", "message", "outcome", "status"]


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


# ------------------------------------------------- outcomes (phase 4, TRUTH-01/02, D-03..D-06)

# The world-wide invariants run over the whole TRANSACTING table with no restriction, so a
# route added to the table is covered by them automatically (D-04, D-14).
OUTCOME_ROWS = list(TRANSACTING)
OUTCOME_ROW_IDS = TRANSACTING_IDS


def reach(world, key):
    """Arm the fake so the row's route reaches a real success on the one open document."""
    items, body = TRANSACTING[key]
    arm(world, items)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    return fill(world, body)


@pytest.mark.parametrize("key", OUTCOME_ROWS, ids=OUTCOME_ROW_IDS)
def test_every_transacting_success_carries_an_outcome_that_agrees_with_its_status(world, key):
    reply = call(world, handler_of(world, *key), reach(world, key))
    assert reply.status in (200, 422), reply.data
    outcome = reply.data["outcome"]
    assert outcome["transaction_status"] == "Committed"
    expected = classify_outcome(True, len(outcome["succeeded"]), len(outcome["failed"]))
    assert (reply.data["status"], reply.status) == expected
    assert reply.status == 200, "the armed row must reach a real success: {}".format(reply.data)


@pytest.mark.parametrize("key", OUTCOME_ROWS, ids=OUTCOME_ROW_IDS)
def test_every_transacting_rollback_is_a_409_with_nothing_succeeded(world, key):
    body = reach(world, key)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, *key), body)
    assert reply.status == 409, reply.data
    assert reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == []


@pytest.mark.parametrize("key", OUTCOME_ROWS, ids=OUTCOME_ROW_IDS)
def test_every_transacting_500_carries_the_real_transaction_status(world, key):
    body = reach(world, key)
    world.break_start.add("Only")
    reply = call(world, handler_of(world, *key), body)
    assert reply.status == 500, reply.data
    assert world.transactions, "the route never built a transaction"
    assert reply.data["outcome"]["transaction_status"] == world.transactions[-1].status
    assert reply.data["outcome"]["succeeded"] == []


# --- delete_elements (D-05: all or nothing)


def test_a_committed_delete_reports_every_requested_id_as_succeeded(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "editing", "/delete_elements/"), {"element_ids": [1, 2]})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": 2,
                                     "succeeded": [1, 2], "failed": [], "revit_failures": []}
    assert reply.data["deleted_ids"] == [1, 2] and reply.data["deleted_count"] == 2
    assert reply.data["cascaded_ids"] == [] and reply.data["message"] == "Deleted 2 elements"


def test_a_rolled_back_delete_is_a_409_that_names_no_deleted_id(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "editing", "/delete_elements/"), {"element_ids": [1, 2]})
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert "deleted_ids" not in reply.data and "deleted_count" not in reply.data
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["requested"] == 2
    assert reply.data["document"]["title"] == "Only"


def test_a_missing_id_refuses_the_whole_delete_before_any_transaction(world):
    arm(world, missing=(999,))
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "editing", "/delete_elements/"),
                 {"element_ids": [1, 999]})
    assert reply.status == 404 and "999" in reply.data["error"]
    assert world.kinds("transaction") == [] and "Delete" not in world.attrs("Only")
    assert "outcome" not in reply.data


def test_a_delete_that_raises_midway_rolls_back_and_never_answers_partial(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()

    def second_delete_fails(document, eid):
        if eid.Value == 2:
            raise RuntimeError("cannot delete 2")
        return []

    world.hooks[("Only", "Delete")] = second_delete_fails
    reply = call(world, handler_of(world, "editing", "/delete_elements/"), {"element_ids": [1, 2]})
    assert reply.status == 500 and "cannot delete 2" in reply.data["error"]
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data.get("status") != "partial" and world.kinds("commit") == []


def test_a_delete_whose_transaction_cannot_start_carries_the_outcome_on_its_500(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.break_start.add("Only")
    reply = call(world, handler_of(world, "editing", "/delete_elements/"), {"element_ids": [1]})
    assert reply.status == 500 and world.kinds("commit") == []
    assert reply.data["outcome"] == {"transaction_status": "Uninitialized", "requested": 1,
                                     "succeeded": [], "failed": [], "revit_failures": []}


def test_a_cascaded_delete_keeps_its_cascaded_ids_beside_the_outcome(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.hooks[("Only", "Delete")] = lambda document, eid: [
        types.SimpleNamespace(Value=eid.Value), types.SimpleNamespace(Value=50)]
    reply = call(world, handler_of(world, "editing", "/delete_elements/"), {"element_ids": [1]})
    assert reply.status == 200
    assert reply.data["cascaded_ids"] == [50] and reply.data["deleted_ids"] == [1]
    assert reply.data["outcome"]["succeeded"] == [1] and "1 hosted element" in reply.data["message"]


# --- modify_element (D-03, D-04: classified through finalize_outcome)


def test_a_modify_where_some_parameters_fail_is_a_200_partial_naming_each_one(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "editing", "/modify_element/"),
                 {"element_id": 1, "parameters": {"Mark": "A", "Nope": "x"}})
    assert reply.status == 200 and reply.data["status"] == "partial"
    outcome = reply.data["outcome"]
    assert outcome["succeeded"] == ["Mark"] and outcome["requested"] == 2
    assert outcome["failed"] == [{"item": "Nope", "reason": "not found"}]
    assert outcome["transaction_status"] == "Committed"
    # the legacy keys stay beside the outcome (D-03)
    assert [change["parameter"] for change in reply.data["changes"]] == ["Mark"]
    assert [entry["parameter"] for entry in reply.data["failed"]] == ["Nope"]
    assert reply.data["transaction_status"] == "Committed" and world.sets == ["A"]


def test_a_modify_where_every_parameter_is_read_only_is_a_422_with_an_error(world):
    arm(world, read_only=True)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "editing", "/modify_element/"),
                 {"element_id": 1, "parameters": {"Mark": "A"}})
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["failed"] == [{"item": "Mark", "reason": "read-only"}]
    assert reply.data["outcome"]["succeeded"] == [] and world.sets == []


def test_a_modify_that_commits_every_parameter_is_a_plain_success(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "editing", "/modify_element/"),
                 {"element_id": 1, "parameters": {"Mark": "A"}})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"]["succeeded"] == ["Mark"] and reply.data["outcome"]["failed"] == []
    assert sorted(without_attribution(reply.data)) == [
        "changes", "element_id", "failed", "message", "outcome", "status", "transaction_status"]


def test_a_rolled_back_modify_keeps_its_attempted_changes_and_gains_the_outcome(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "editing", "/modify_element/"),
                 {"element_id": 1, "parameters": {"Mark": "A", "Nope": "x"}})
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert [change["parameter"] for change in reply.data["attempted_changes"]] == ["Mark"]
    outcome = reply.data["outcome"]
    assert outcome["succeeded"] == [] and outcome["transaction_status"] == "RolledBack"
    assert outcome["failed"] == [{"item": "Nope", "reason": "not found"}]
    assert outcome["requested"] == 2


def test_a_modify_whose_transaction_cannot_start_carries_the_outcome_on_its_500(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.break_start.add("Only")
    reply = call(world, handler_of(world, "editing", "/modify_element/"),
                 {"element_id": 1, "parameters": {"Mark": "A"}})
    assert reply.status == 500
    assert reply.data["outcome"]["transaction_status"] == "Uninitialized"
    assert reply.data["outcome"]["succeeded"] == []


# --- export_ifc (D-06: the Boolean Document.Export returns)


def test_export_ifc_that_returns_true_reports_the_file_as_succeeded(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "interop", "/export_ifc/"), {"file_path": "out.ifc"})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": 1,
                                     "succeeded": ["out.ifc"], "failed": [], "revit_failures": []}
    assert reply.data["file_path"] == "out.ifc" and reply.data["ifc_version"] == "IFC2x3"
    assert "file_size_kb" in reply.data and reply.data["message"].startswith("Exported IFC")


def test_export_ifc_that_returns_false_is_a_422_and_never_a_success(world):
    arm(world)
    world.hooks[(None, "Export")] = lambda document, *args: False
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "interop", "/export_ifc/"), {"file_path": "out.ifc"})
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    outcome = reply.data["outcome"]
    assert outcome["failed"] == [{"item": "out.ifc", "reason": "Document.Export returned False"}]
    assert outcome["succeeded"] == [] and outcome["transaction_status"] == "Committed"
    assert not reply.data["message"].startswith("Exported IFC")


def test_export_ifc_rolled_back_is_a_409_with_nothing_succeeded(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "interop", "/export_ifc/"), {"file_path": "out.ifc"})
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == [] and "file_path" not in reply.data


def test_export_ifc_that_raises_rolls_back_and_carries_the_outcome_on_its_500(world):
    arm(world)

    def refuses(document, *args):
        raise RuntimeError("exporter crashed")

    world.hooks[(None, "Export")] = refuses
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "interop", "/export_ifc/"), {"file_path": "out.ifc"})
    assert reply.status == 500 and "exporter crashed" in reply.data["error"]
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["requested"] == 1
    assert world.kinds("commit") == []


# --- link_file (TRUTH-01: no element id back from Revit is a failure)


def test_an_import_that_hands_back_no_element_id_is_a_422_naming_the_file(world):
    arm(world)
    world.imported_id = None
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    path = (world.tmp / "plan.dwg").as_posix()
    reply = call(world, handler_of(world, "interop", "/link_file/"),
                 {"file_path": path, "mode": "import"})
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["failed"] == [
        {"item": path, "reason": "Revit returned no element id for the imported file"}]
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["element_id"] is None and reply.data["mode"] == "import"


def test_a_link_that_hands_back_no_element_id_says_linked_in_its_reason(world):
    arm(world)
    world.imported_id = None
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    path = (world.tmp / "plan.dwg").as_posix()
    reply = call(world, handler_of(world, "interop", "/link_file/"),
                 {"file_path": path, "mode": "link"})
    assert reply.status == 422
    assert reply.data["outcome"]["failed"][0]["reason"] == (
        "Revit returned no element id for the linked file")


def test_an_import_that_returns_an_element_id_succeeds_with_the_file_path(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    path = (world.tmp / "plan.dwg").as_posix()
    reply = call(world, handler_of(world, "interop", "/link_file/"),
                 {"file_path": path, "mode": "import"})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["element_id"] == 77 and reply.data["file_name"] == "plan.dwg"
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": 1,
                                     "succeeded": [path], "failed": [], "revit_failures": []}
    assert sorted(without_attribution(reply.data)) == [
        "element_id", "file_name", "file_type", "message", "mode", "outcome", "status"]


def test_an_unsupported_file_type_still_rolls_back_and_answers_400_without_an_outcome(world):
    arm(world)
    (world.tmp / "notes.txt").write_bytes(b"x")
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "interop", "/link_file/"),
                 {"file_path": (world.tmp / "notes.txt").as_posix()})
    assert reply.status == 400 and "Unsupported file type" in reply.data["error"]
    assert "outcome" not in reply.data and world.kinds("commit") == []
    assert world.kinds("rollback")


# --- save_document (D-06: no transaction, transaction_status null)


def test_a_save_in_place_reports_the_path_the_document_has_with_a_null_transaction_status(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "document", "/save_document/"), {})
    assert reply.status == 200 and reply.data["operation"] == "save"
    assert reply.data["outcome"] == {"transaction_status": None, "requested": 1,
                                     "succeeded": [ONLY_PATH], "failed": [], "revit_failures": []}
    assert world.transactions == []


def test_a_save_as_reports_the_path_the_document_has_after_it(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    requested = (world.tmp / "asked.rvt").as_posix()
    actual = (world.tmp / "actually.rvt").as_posix()

    def lands_elsewhere(document, *args, **kwargs):
        document._lifetime.path = actual

    world.hooks[("Only", "SaveAs")] = lands_elsewhere
    reply = call(world, handler_of(world, "document", "/save_document/"), {"file_path": requested})
    assert reply.status == 200 and reply.data["file_path"] == actual
    assert reply.data["outcome"]["succeeded"] == [actual]
    assert reply.data["outcome"]["transaction_status"] is None
    assert requested not in reply.data["outcome"]["succeeded"]


def test_a_save_that_raises_is_a_500_with_the_document_path_as_the_failed_item(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()

    def refuses(document, *args, **kwargs):
        raise RuntimeError("file is locked")

    world.hooks[("Only", "Save")] = refuses
    reply = call(world, handler_of(world, "document", "/save_document/"), {})
    assert reply.status == 500 and "file is locked" in reply.data["error"]
    assert reply.data["outcome"] == {
        "transaction_status": None, "requested": 1, "succeeded": [],
        "failed": [{"item": ONLY_PATH, "reason": "file is locked"}], "revit_failures": []}


def test_a_save_as_that_raises_names_the_requested_path_as_the_failed_item(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    requested = (world.tmp / "x.rvt").as_posix()

    def refuses(document, *args, **kwargs):
        raise RuntimeError("disk full")

    world.hooks[("Only", "SaveAs")] = refuses
    reply = call(world, handler_of(world, "document", "/save_document/"), {"file_path": requested})
    assert reply.status == 500
    assert reply.data["outcome"]["failed"] == [{"item": requested, "reason": "disk full"}]
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["transaction_status"] is None


def test_a_save_of_an_untitled_document_falls_back_to_its_title_as_the_item(world):
    world.open(BETA, "", active=True)
    world.tokens()
    requested = (world.tmp / "new.rvt").as_posix()

    def lands_nowhere(document, *args, **kwargs):
        document._lifetime.path = ""

    world.hooks[(BETA, "SaveAs")] = lands_nowhere
    reply = call(world, handler_of(world, "document", "/save_document/"), {"file_path": requested})
    assert reply.status == 200
    assert reply.data["outcome"]["succeeded"] == [BETA]


def test_the_never_saved_400_carries_no_outcome(world):
    world.open(BETA, "", active=True)
    world.tokens()
    reply = call(world, handler_of(world, "document", "/save_document/"), {})
    assert reply.status == 400 and "outcome" not in reply.data


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


# ----------------------------------------------------- documentation outcomes (04-06, D-06, D-12)


def db_of():
    return sys.modules["pyrevit"].DB


def export_dir_of(world):
    return os.path.join(str(world.tmp), "Documents", "RevitMCPExport")


class TrackedSheet(object):
    """A ViewSheet whose every public read is logged, so a test can prove nothing was read
    from it after the commit event. ``number_error`` makes the SheetNumber setter raise."""

    def __init__(self, world, number_error=None):
        self.__dict__["_world"] = world
        self.__dict__["_number_error"] = number_error
        self.__dict__["_values"] = {"SheetNumber": "A-9", "Name": "Auto",
                                    "Id": types.SimpleNamespace(Value=555)}

    def __getattribute__(self, name):
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        object.__getattribute__(self, "_world").events.append(("sheetread", "SHEET", name))
        return object.__getattribute__(self, "_values")[name]

    def __setattr__(self, name, value):
        if name == "SheetNumber" and self._number_error is not None:
            raise self._number_error
        self._values[name] = value


def arm_sheet(world, number_error=None):
    """A title block in the collector and a ViewSheet.Create that hands back a tracked sheet."""
    world.collector_items = [_title_block]
    sheet = TrackedSheet(world, number_error)
    db_of().ViewSheet = types.SimpleNamespace(Create=lambda doc, title_block_id: sheet)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    return sheet


def events_after_commit(world, kind):
    commits = [i for i, event in enumerate(world.events) if event[0] == "commit"]
    assert commits, "the route never committed"
    return [event for event in world.events[commits[0]:] if event[0] == kind]


def test_create_sheet_success_reports_the_new_sheet_id(world):
    arm_sheet(world)
    reply = call(world, handler_of(world, "documentation", "/create_sheet/"),
                 {"sheet_number": "A-1", "sheet_name": "Plan"})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": 1,
                                     "succeeded": [555], "failed": [], "revit_failures": []}
    assert reply.data["created"]["id"] == 555 and reply.data["created"]["title_block"] == "TB"
    assert reply.data["created"]["sheet_number"] == "A-1"
    assert reply.data["message"] == "Created sheet A-1 - Plan"


def test_a_rolled_back_create_sheet_is_a_409_and_the_sheet_is_never_read_after_the_commit(world):
    arm_sheet(world)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "documentation", "/create_sheet/"),
                 {"sheet_number": "A-1", "sheet_name": "Plan"})
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["requested"] == 1
    assert "created" not in reply.data
    assert events_after_commit(world, "sheetread") == []


def test_a_sheet_number_that_is_in_use_is_a_200_partial_naming_the_step(world):
    arm_sheet(world, number_error=RuntimeError("in use"))
    reply = call(world, handler_of(world, "documentation", "/create_sheet/"),
                 {"sheet_number": "A-1", "sheet_name": "Plan"})
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"]["failed"] == [{"item": "sheet_number", "reason": "in use"}]
    assert reply.data["outcome"]["succeeded"] == [555]
    assert reply.data["created"]["id"] == 555 and reply.data["created"]["sheet_name"] == "Plan"
    assert "sheet_number" in reply.data["message"] and "in use" in reply.data["message"]


class FakeField(object):
    def __init__(self, name):
        self._name = name

    def GetName(self, doc):
        return self._name


class FakeSchedule(object):
    """A ViewSchedule with two schedulable fields, Mark and Other."""

    def __init__(self, name_error=None):
        self.added = []
        self.Id = types.SimpleNamespace(Value=321)
        self._name = ""
        self._name_error = name_error
        fields = [FakeField("Mark"), FakeField("Other")]
        self.Definition = types.SimpleNamespace(
            GetSchedulableFields=lambda: fields,
            AddField=lambda field: self.added.append(field.GetName(None)))
        body = types.SimpleNamespace(NumberOfRows=4)
        self._table = types.SimpleNamespace(GetSectionData=lambda section: body)

    @property
    def Name(self):
        return self._name

    @Name.setter
    def Name(self, value):
        if self._name_error is not None:
            raise self._name_error
        self._name = value

    def GetTableData(self):
        return self._table


def arm_schedule(world, name_error=None):
    schedule = FakeSchedule(name_error)
    db_of().ViewSchedule = types.SimpleNamespace(CreateSchedule=lambda doc, category_id: schedule)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    return schedule


def test_create_schedule_with_a_field_that_does_not_exist_is_a_200_partial(world):
    schedule = arm_schedule(world)
    reply = call(world, handler_of(world, "documentation", "/create_schedule/"),
                 {"category": "OST_Walls", "fields": ["Mark", "Nope"], "schedule_name": "Walls"})
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"] == {
        "transaction_status": "Committed", "requested": 1, "succeeded": [321],
        "failed": [{"item": "Nope", "reason": "field not found"}], "revit_failures": []}
    assert schedule.added == ["Mark"]
    assert reply.data["created"]["fields"] == ["Mark"] and reply.data["created"]["id"] == 321
    assert reply.data["created"]["name"] == "Walls" and reply.data["created"]["row_count"] == 4
    assert reply.data["fields_not_found"] == ["Nope"]
    assert reply.data["available_fields"] == ["Mark", "Other"]


def test_create_schedule_without_fields_is_a_plain_success(world):
    schedule = arm_schedule(world)
    reply = call(world, handler_of(world, "documentation", "/create_schedule/"),
                 {"category": "OST_Walls"})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"]["succeeded"] == [321] and reply.data["outcome"]["failed"] == []
    assert schedule.added == ["Mark", "Other"] and "fields_not_found" not in reply.data


def test_a_schedule_that_cannot_take_its_name_is_a_200_partial_naming_the_step(world):
    arm_schedule(world, name_error=RuntimeError("name taken"))
    reply = call(world, handler_of(world, "documentation", "/create_schedule/"),
                 {"category": "OST_Walls", "schedule_name": "Walls"})
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"]["failed"] == [{"item": "name", "reason": "name taken"}]
    assert reply.data["outcome"]["succeeded"] == [321]


def test_a_rolled_back_create_schedule_is_a_409_with_nothing_succeeded(world):
    arm_schedule(world)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "documentation", "/create_schedule/"),
                 {"category": "OST_Walls", "fields": ["Mark", "Nope"]})
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == [] and "created" not in reply.data


EXPORT_VIEW = {"view_name": "Plan A"}


def export_path(world, extension):
    return os.path.join(export_dir_of(world), "Plan_A." + extension)


def arm_export(world, hook=None, name="Export"):
    world.collector_items = [_view]
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    if hook is not None:
        world.hooks[("Only", name)] = hook


def test_a_dwg_export_that_returns_true_reports_the_path_as_succeeded(world):
    arm_export(world, lambda document, *args: True)
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="dwg"))
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"] == {
        "transaction_status": "Committed", "requested": 1,
        "succeeded": [export_path(world, "dwg")], "failed": [], "revit_failures": []}
    assert reply.data["exported"]["file_path"] == export_path(world, "dwg")


def test_a_dwg_export_that_returns_false_is_a_422_naming_the_output_path(world):
    arm_export(world, lambda document, *args: False)
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="dwg"))
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["failed"] == [
        {"item": export_path(world, "dwg"), "reason": "Document.Export returned False"}]
    assert reply.data["outcome"]["transaction_status"] == "Committed"
    assert "exported" not in reply.data


def test_a_pdf_export_that_returns_false_is_a_422_and_no_longer_a_rolled_back_500(world):
    arm_export(world, lambda document, *args: False)
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="pdf"))
    assert reply.status == 422 and reply.data["status"] == "failed"
    assert reply.data["outcome"]["failed"] == [
        {"item": export_path(world, "pdf"), "reason": "Document.Export returned False"}]
    assert world.kinds("rollback") == [] and world.kinds("commit")


def test_a_pdf_export_that_returns_true_reports_the_pdf_as_succeeded(world):
    arm_export(world, lambda document, *args: True)
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="pdf"))
    assert reply.status == 200
    assert reply.data["outcome"]["succeeded"] == [export_path(world, "pdf")]


def test_a_pdf_export_that_raises_rolls_back_and_carries_the_outcome_on_its_500(world):
    def refuses(document, *args):
        raise RuntimeError("no printer")

    arm_export(world, refuses)
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="pdf"))
    assert reply.status == 500 and "no printer" in reply.data["error"]
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["failed"] == [
        {"item": export_path(world, "pdf"), "reason": "no printer"}]
    assert world.kinds("commit") == []


def test_a_dwg_export_that_raises_rolls_back_and_carries_the_outcome_on_its_500(world):
    def refuses(document, *args):
        raise RuntimeError("no dwg")

    arm_export(world, refuses)
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="dwg"))
    assert reply.status == 500 and "no dwg" in reply.data["error"]
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["failed"] == [
        {"item": export_path(world, "dwg"), "reason": "no dwg"}]


def test_an_image_export_that_leaves_no_file_is_a_422(world):
    arm_export(world, lambda document, *args: None, name="ExportImage")
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="png"))
    assert reply.status == 422 and reply.data["status"] == "failed"
    assert reply.data["outcome"]["failed"] == [
        {"item": export_path(world, "png"), "reason": "expected export file was not created"}]
    assert reply.data["outcome"]["succeeded"] == []


def test_an_image_export_that_writes_its_file_is_a_200_success(world):
    def writes(document, *args):
        with open(export_path(world, "png"), "wb") as handle:
            handle.write(b"x" * 2048)

    arm_export(world, writes, name="ExportImage")
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="png"))
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"]["succeeded"] == [export_path(world, "png")]
    assert reply.data["exported"]["file_size_kb"] == 2


def test_an_image_export_never_counts_a_file_from_an_earlier_export_as_its_own(world):
    os.makedirs(export_dir_of(world))
    stale = export_path(world, "jpg")
    with open(stale, "wb") as handle:
        handle.write(b"old")
    long_ago = time.time() - 3600
    os.utime(stale, (long_ago, long_ago))
    arm_export(world, lambda document, *args: None, name="ExportImage")
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="jpg"))
    assert reply.status == 422
    assert reply.data["outcome"]["failed"][0]["reason"] == "expected export file was not created"


def test_a_rolled_back_export_is_a_409_with_nothing_succeeded(world):
    arm_export(world, lambda document, *args: True)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "documentation", "/export_document/"),
                 dict(EXPORT_VIEW, format="dwg"))
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == [] and "exported" not in reply.data


# --------------------------------------------- placement outcomes (04-06, D-12, D-06)

PLACE_BODY = {"family_name": "F", "type_name": "T", "location": {"x": 0, "y": 0, "z": 0}}


class TrackedInstance(object):
    """A placed family instance. Reading Location is logged so a test can prove it was not
    read after the commit event. ``params`` answers LookupParameter."""

    def __init__(self, world, params=None, rotate_result=True, rotate_error=None,
                 location_error=None, can_rotate=True):
        self._world = world
        self.Id = types.SimpleNamespace(Value=900)
        self._params = {"Mark": FakeParam(world)} if params is None else params
        self._location_error = location_error
        self.rotations = []

        def rotate(axis, radians):
            self.rotations.append(radians)
            if rotate_error is not None:
                raise rotate_error
            return rotate_result

        point = types.SimpleNamespace(X=1.0, Y=2.0, Z=3.0)
        self._location = types.SimpleNamespace(Point=point)
        if can_rotate:
            self._location.Rotate = rotate

    @property
    def Location(self):
        self._world.events.append(("locread", "INSTANCE", "Location"))
        if self._location_error is not None:
            raise self._location_error
        return self._location

    def LookupParameter(self, name):
        return self._params.get(name)


def arm_placement(world, instance=None, **kwargs):
    """A symbol in the collector and a doc.Create that places the given instance."""
    world.collector_items = [_symbol]
    instance = instance or TrackedInstance(world, **kwargs)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.values[("Only", "Create")] = types.SimpleNamespace(
        NewFamilyInstance=lambda *args: instance)
    return instance


def test_place_family_success_reports_the_instance_and_every_legacy_key(world):
    arm_placement(world)
    reply = call(world, handler_of(world, "placement", "/place_family/"),
                 dict(PLACE_BODY, properties={"Mark": "A"}))
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": 1,
                                     "succeeded": [900], "failed": [], "revit_failures": []}
    assert reply.data["element_id"] == 900
    assert reply.data["properties_set"] == ["Mark"] and reply.data["properties_failed"] == []
    assert reply.data["actual_location"] == pytest.approx({"x": 304.8, "y": 609.6, "z": 914.4})
    for key in ("family_name", "type_name", "requested_location", "rotation_degrees", "level"):
        assert key in reply.data


def test_place_family_reports_every_property_it_could_not_set_as_a_failed_step(world):
    arm_placement(world, params={"Mark": FakeParam(world), "Fixed": FakeParam(world, read_only=True)})
    reply = call(world, handler_of(world, "placement", "/place_family/"),
                 dict(PLACE_BODY, properties={"Mark": "A", "Fixed": "x", "Ghost": "y"}))
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"]["succeeded"] == [900]
    assert reply.data["outcome"]["failed"] == [{"item": "Fixed", "reason": "read-only"},
                                               {"item": "Ghost", "reason": "not found"}]
    assert reply.data["properties_set"] == ["Mark"]
    assert reply.data["properties_failed"] == ["Fixed (read-only)", "Ghost (not found)"]


def test_place_family_names_an_unsupported_parameter_type_and_a_set_that_raises(world):
    odd = FakeParam(world)
    odd.StorageType = "ElementId"
    boom = FakeParam(world)

    def refuses(value):
        raise RuntimeError("bad value")

    boom.Set = refuses
    arm_placement(world, params={"Odd": odd, "Boom": boom})
    reply = call(world, handler_of(world, "placement", "/place_family/"),
                 dict(PLACE_BODY, properties={"Odd": "1", "Boom": "x"}))
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"]["failed"] == [{"item": "Odd", "reason": "unsupported type"},
                                               {"item": "Boom", "reason": "bad value"}]
    assert reply.data["properties_failed"] == ["Odd (unsupported type)", "Boom (error: bad value)"]


def test_place_family_with_a_rotation_that_returns_false_is_a_partial(world):
    instance = arm_placement(world, rotate_result=False)
    reply = call(world, handler_of(world, "placement", "/place_family/"),
                 dict(PLACE_BODY, rotation=90))
    assert instance.rotations, "the rotation was never attempted"
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"]["failed"] == [
        {"item": "rotation", "reason": "RotateElement returned False"}]
    assert reply.data["outcome"]["succeeded"] == [900]


def test_place_family_with_a_rotation_that_raises_names_the_error(world):
    arm_placement(world, rotate_error=RuntimeError("cannot rotate"))
    reply = call(world, handler_of(world, "placement", "/place_family/"),
                 dict(PLACE_BODY, rotation=45))
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"]["failed"] == [{"item": "rotation", "reason": "cannot rotate"}]


def test_place_family_with_a_rotation_on_an_element_that_cannot_rotate_is_a_partial(world):
    arm_placement(world, can_rotate=False)
    reply = call(world, handler_of(world, "placement", "/place_family/"),
                 dict(PLACE_BODY, rotation=45))
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"]["failed"][0]["item"] == "rotation"


def test_place_family_with_a_rotation_that_works_is_a_plain_success(world):
    instance = arm_placement(world, rotate_result=True)
    reply = call(world, handler_of(world, "placement", "/place_family/"),
                 dict(PLACE_BODY, rotation=90))
    assert instance.rotations and reply.data["status"] == "success"
    assert reply.data["outcome"]["failed"] == []


def test_a_rolled_back_place_family_is_a_409_and_the_instance_location_is_never_read_after_the_commit(world):
    arm_placement(world)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "placement", "/place_family/"),
                 dict(PLACE_BODY, properties={"Mark": "A"}))
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["requested"] == 1
    for key in ("element_id", "actual_location", "requested_location", "properties_set"):
        assert key not in reply.data, key
    assert events_after_commit(world, "locread") == []


def test_place_family_falls_back_to_the_requested_point_only_for_a_committed_instance(world):
    db_of().XYZ = lambda x, y, z: types.SimpleNamespace(X=x, Y=y, Z=z)
    arm_placement(world, location_error=RuntimeError("no location"))
    reply = call(world, handler_of(world, "placement", "/place_family/"),
                 dict(PLACE_BODY, location={"x": 304.8, "y": 0, "z": 0}))
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["actual_location"] == reply.data["requested_location"]
    assert reply.data["actual_location"]["x"] == 304.8


def test_load_family_success_carries_an_outcome_with_a_null_transaction_status(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    path = (world.tmp / "Door.rfa").as_posix()
    world.hooks[("Only", "LoadFamily")] = lambda document, file_path: True
    reply = call(world, handler_of(world, "placement", "/load_family/"), {"file_path": path})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"] == {"transaction_status": None, "requested": 1,
                                     "succeeded": [path], "failed": [], "revit_failures": []}
    assert world.kinds("transaction") == []


def test_load_family_already_loaded_keeps_its_status_and_empties_both_lists(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    path = (world.tmp / "Door.rfa").as_posix()
    world.hooks[("Only", "LoadFamily")] = lambda document, file_path: False
    reply = call(world, handler_of(world, "placement", "/load_family/"), {"file_path": path})
    assert reply.status == 200 and reply.data["status"] == "already_loaded"
    assert reply.data["outcome"] == {"transaction_status": None, "requested": 1,
                                     "succeeded": [], "failed": [], "revit_failures": []}


def test_load_family_that_raises_is_a_500_naming_the_file(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    path = (world.tmp / "Door.rfa").as_posix()

    def refuses(document, file_path):
        raise RuntimeError("corrupt family")

    world.hooks[("Only", "LoadFamily")] = refuses
    reply = call(world, handler_of(world, "placement", "/load_family/"), {"file_path": path})
    assert reply.status == 500 and "corrupt family" in reply.data["error"]
    assert reply.data["outcome"] == {
        "transaction_status": None, "requested": 1, "succeeded": [],
        "failed": [{"item": path, "reason": "corrupt family"}], "revit_failures": []}


def test_load_family_validation_replies_carry_no_outcome(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    handler = handler_of(world, "placement", "/load_family/")
    missing = call(world, handler, {})
    assert missing.status == 400 and "outcome" not in missing.data
    absent = call(world, handler, {"file_path": (world.tmp / "Nope.rfa").as_posix()})
    assert absent.status == 404 and "outcome" not in absent.data


# ------------------------------------ edit_family outcomes (04-06, D-01, D-14, TRUTH-01)

FAMILY_LABEL = "FAMILY:Door.rfa"


def test_edit_family_that_applies_its_parameter_carries_the_family_transaction_outcome(world):
    arm_family(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "placement", "/edit_family/"), EDIT_BODY)
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": 1,
                                     "succeeded": ["Width"], "failed": [], "revit_failures": []}
    assert reply.data["reloaded"] is True
    assert reply.data["parameters_applied"] == {"Width": 900}
    assert reply.data["parameters_failed"] == {}


def test_edit_family_rolled_back_family_commit_is_a_409_that_never_reloads_the_family(world):
    family_doc = arm_family(world)
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "placement", "/edit_family/"), EDIT_BODY)
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert world.kinds("load_into") == [], "a rolled-back edit must never be loaded into the project"
    assert not reply.data.get("reloaded") and not reply.data.get("project_changed")
    assert "parameters_applied" not in reply.data
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["documents_changed"] == [
        project_entry(token, changed=False), family_entry(changed=False)]
    assert ("close", FAMILY_LABEL, False) in world.events
    assert family_doc.FamilyManager.set_calls == ["900"]


def test_edit_family_in_which_no_parameter_applies_is_a_422_that_never_reloads(world):
    arm_family(world)
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "placement", "/edit_family/"),
                 {"family_name": "Door", "parameters": {"Nope": 1}})
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["failed"] == [{"item": "Nope", "reason": "no such family parameter"}]
    assert reply.data["outcome"]["transaction_status"] == "Committed"
    assert reply.data["parameters_failed"] == {"Nope": "no such family parameter"}
    assert reply.data["reloaded"] is False and world.kinds("load_into") == []
    assert reply.data["documents_changed"] == [
        project_entry(token, changed=False), family_entry(changed=False)]
    assert ("close", FAMILY_LABEL, False) in world.events


def test_edit_family_with_one_applied_and_one_failed_parameter_is_a_200_partial(world):
    family_doc = arm_family(world)
    family_doc.FamilyManager.params["Fixed"] = FakeFamParam(read_only=True)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "placement", "/edit_family/"),
                 {"family_name": "Door", "parameters": {"Width": 900, "Fixed": 1, "Nope": 2}})
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"] == {
        "transaction_status": "Committed", "requested": 3, "succeeded": ["Width"],
        "failed": [{"item": "Fixed", "reason": "read-only"},
                   {"item": "Nope", "reason": "no such family parameter"}],
        "revit_failures": []}
    assert reply.data["reloaded"] is True and ("load_into", FAMILY_LABEL, "Only") in world.events


def test_edit_family_that_creates_a_type_and_adds_a_missing_shared_parameter_names_both_items(world):
    arm_family(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "placement", "/edit_family/"),
                 {"family_name": "Door", "new_type_name": "Wide", "parameters": {"Width": 900},
                  "add_shared_parameters": ["Ghost", "Width"]})
    assert reply.status == 200 and reply.data["status"] == "partial"
    outcome = reply.data["outcome"]
    assert outcome["succeeded"] == ["new_type:Wide", "Width"]
    assert outcome["failed"] == [
        {"item": "shared:Ghost", "reason": "not found in shared parameters file"}]
    assert outcome["requested"] == 3, "Width already exists, so it is a no-op in neither list"
    assert reply.data["type_created"] == "Wide" and reply.data["current_type"] == "Wide"


def test_edit_family_reload_failure_is_still_a_500_and_carries_the_family_transaction_status(world):
    arm_family(world)
    world.family_load_error = RuntimeError("load refused")
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, "placement", "/edit_family/"), EDIT_BODY)
    assert reply.status == 500 and "Family edited but reload failed" in reply.data["error"]
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": 1,
                                     "succeeded": ["Width"], "failed": [], "revit_failures": []}
    assert reply.data["documents_changed"] == [
        project_entry(token, changed=False), family_entry(changed=True)]


def test_edit_family_whose_transaction_cannot_start_carries_the_real_status_on_its_500(world):
    arm_family(world)
    world.break_start.add(FAMILY_LABEL)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "placement", "/edit_family/"), EDIT_BODY)
    assert reply.status == 500
    assert reply.data["outcome"]["transaction_status"] == world.transactions[-1].status
    assert reply.data["outcome"]["succeeded"] == []


def test_edit_family_validation_replies_carry_no_outcome(world):
    arm_family(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    handler = handler_of(world, "placement", "/edit_family/")
    unknown = call(world, handler, {"family_name": "Door", "type_name": "Nope",
                                    "parameters": {"Width": 900}})
    assert unknown.status == 404 and "outcome" not in unknown.data
    nothing = call(world, handler, {"family_name": "Door"})
    assert nothing.status == 400 and "outcome" not in nothing.data


# ----------------------------------- Phase 5 (05-03): every mutation of the suite is gated
#
# One parametrized refusal set over the whole MUTATIONS table. One active document is open,
# so a call that slipped past the gate would visibly reach the document guard. The file
# writing routes (save, export, IFC export, link) must leave no file behind.

WRONG_SECRET = "wrong-secret-0123456789-abcdefXYZ-nope"

def _one_open_document(world):
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    del world.events[:]


def _tree(world):
    return sorted(str(path.relative_to(world.tmp)) for path in world.tmp.rglob("*"))


def _mismatch_naming(*files):
    return {"state": trust.INTEGRITY_MISMATCH, "reason": None,
            "modified": sorted(files), "missing": [], "unexpected": []}


def _refused(world, key, request, status):
    before = _tree(world)
    reply = call(world, handler_of(world, *key), request=request)
    assert reply.status == status
    assert "outcome" not in reply.data
    assert world.events == [], "no collector, document attribute, save or transaction before the gate"
    assert world.transactions == []
    assert world.guard_calls == []
    assert _tree(world) == before, "an unauthenticated call must write no file"
    text = repr(reply.data)
    assert TEST_SECRET not in text and WRONG_SECRET not in text
    return reply


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_without_the_shared_secret_a_mutation_is_401_before_any_side_effect(world, key):
    _one_open_document(world)
    body = fill(world, MUTATIONS[key])
    request = types.SimpleNamespace(data=enveloped_body(body, secret=None, route=key[1]), path=key[1])
    reply = _refused(world, key, request, 401)
    assert reply.data["auth"] == "missing"


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_with_a_wrong_secret_a_mutation_is_401_before_any_side_effect(world, key):
    _one_open_document(world)
    body = fill(world, MUTATIONS[key])
    request = types.SimpleNamespace(data=enveloped_body(body, secret=WRONG_SECRET, route=key[1]), path=key[1])
    reply = _refused(world, key, request, 401)
    assert reply.data["auth"] == "mismatch"


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_with_an_integrity_mismatch_a_mutation_is_423_before_any_side_effect(
        world, monkeypatch, key):
    _one_open_document(world)
    configure_gate(monkeypatch, integrity=_mismatch_naming("revit_mcp/detail.py"))
    body = fill(world, MUTATIONS[key])
    request = types.SimpleNamespace(data=enveloped_body(body, route=key[1]), path=key[1])
    reply = _refused(world, key, request, 423)
    assert reply.data["files"] == ["revit_mcp/detail.py"]


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
