# -*- coding: utf-8 -*-
"""Explicit per-handler document guard on the mutating routes of mep, parameters, rooms,
structure and tags (plan 02-14; D-05, D-08, D-09, D-10, G1 explicit-route-only).

Offline evidence only. The real route modules are imported against a fake pyRevit and
registered through their real register_*_routes functions with a fake api, so a handler
that forgets to call revit_mcp.identity.mutation_document_or_response fails here: every
fixture row drives the handler the way pyRevit would (injected uiapp, doc, request by
name) and observes every document, collector and transaction the handler touched.

What this proves: the guard runs first, refuses before any side effect, runs the work on
the document the guard resolved (never the injected ``doc``), and stamps the document
descriptor and process identity on every reply the handler produced, including the 409
rollback of ``set_parameter`` which stays an error. What it does not prove: how pyRevit
dispatches these handlers, or how a real Document answers -- that is a live recheck after
a full Revit restart (02-18; the parameter-write campaign G6 is not authorized). Nothing
here touches Revit.
"""

import importlib
import inspect
import json
import math
import re
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from revit_mcp import identity
from revit_mcp.textutils import classify_outcome
from tools.utils import format_response

IDENT = {"pid": 4242, "actual_port": 48885, "session_token": "tok-abc", "revit_version": "2024"}

BETA = u"\u0411\u0435\u0442\u0430"
ONLY_PATH = "C:/Models/Only.rvt"

REPO = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------- the classification
#
# Hand classification of every route in the five owned registrars. A route that is not
# listed here fails test_every_registered_route_is_classified, so a new route cannot
# slip in unguarded or be mislabelled silently. Classified by what a route DOES.

REGISTRARS = {
    "mep": "register_mep_routes",
    "parameters": "register_parameter_routes",
    "rooms": "register_room_routes",
    "structure": "register_structure_routes",
    "tags": "register_tag_routes",
}

_POINTS = {"start_point": {"x": 0, "y": 0, "z": 0}, "end_point": {"x": 1000, "y": 0, "z": 0}}

# (module, route) -> a body that gets past early validation and touches the document.
MUTATIONS = {
    ("mep", "/create_duct/"): dict(_POINTS),
    ("mep", "/create_pipe/"): dict(_POINTS),
    ("mep", "/create_mep_system/"): {"system_type": "mechanical", "system_name": "S",
                                     "element_ids": [1]},
    ("parameters", "/set_parameter/"): {"element_id": 1, "parameter_name": "Mark", "value": "A"},
    ("rooms", "/create_room/"): {"level_name": "L1"},
    ("rooms", "/create_room_separation/"): {"lines": [dict(_POINTS)], "view_name": "Plan A"},
    ("structure", "/create_grid/"): {"grids": [dict(_POINTS, name="A")]},
    ("structure", "/create_framing/"): {"elements": [dict(_POINTS, type_name="B", level_name="L1")]},
    ("tags", "/tag_elements/"): {"element_ids": [1], "view_name": "Plan A"},
}

# (module, route, method) -> the parameters it must keep: no uiapp, no guard, active document.
READS = {
    ("parameters", "/project_parameters/", "GET"):
        ["doc", "shared_only", "prefix", "search", "summary_only"],
    ("parameters", "/element_properties/<element_id>", "GET"): ["doc", "element_id"],
}

MUTATION_IDS = ["{}:{}".format(module, route) for module, route in MUTATIONS]


class _Item(object):
    """A collector result: a named element with the few members the routes read."""

    def __init__(self, world, name="Item", elevation=0.0, template=False):
        self.world = world
        self.Name = name
        self.Id = types.SimpleNamespace(Value=11)
        self.Elevation = elevation
        self.IsActive = True
        self.IsTemplate = template
        self.Category = None
        self.SketchPlane = MagicMock(name="SketchPlane")
        self.GenLevel = None
        self.ViewType = "FloorPlan"

    def Activate(self):
        pass


def _named(name, **kwargs):
    return lambda world: _Item(world, name, **kwargs)


# Routes that open a transaction on the document and succeed with HTTP 200:
# (collector items the route finds, body).
TRANSACTING = {
    ("mep", "/create_duct/"): ([_named("D")], dict(_POINTS)),
    ("mep", "/create_pipe/"): ([_named("P")], dict(_POINTS)),
    ("mep", "/create_mep_system/"): ([], {"system_type": "mechanical", "system_name": "S",
                                          "element_ids": [1]}),
    ("parameters", "/set_parameter/"): ([], {"element_id": 1, "parameter_name": "Mark",
                                             "value": "A"}),
    ("rooms", "/create_room/"): ([_named("L1")], {"level_name": "L1"}),
    ("rooms", "/create_room_separation/"): ([_named("Plan A")],
                                            {"lines": [dict(_POINTS)], "view_name": "Plan A"}),
    ("structure", "/create_grid/"): ([], {"grids": [dict(_POINTS, name="A")]}),
    ("structure", "/create_framing/"): ([_named("B")],
                                        {"elements": [dict(_POINTS, type_name="B",
                                                           level_name="L1")]}),
    ("tags", "/tag_elements/"): ([_named("Plan A")],
                                 {"element_ids": [1], "view_name": "Plan A"}),
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
    test wants to behave (GetElement) is a hook keyed by (label or None, name)."""

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
        if name in self._world.attr_overrides:
            return self._world.attr_overrides[name]
        hook =self._world.hooks.get((self.label, name)) or self._world.hooks.get((None, name))
        if hook is not None:
            return lambda *args, **kwargs: hook(self, *args, **kwargs)
        return MagicMock(name=name)


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


class FakeParam(object):
    """A writable string parameter that records what it was set to."""

    StorageType = "String"
    IsReadOnly = False
    HasValue = True

    def __init__(self, world, value="old"):
        self._world = world
        self.value = value

    def AsString(self):
        return self.value

    def Set(self, value):
        self._world.sets.append(value)
        self.value = value
        return True


class FakeElement(object):
    """An element GetElement answers: it has a settable parameter and one connector that
    already belongs to a system, so set_parameter and create_mep_system run to the end."""

    def __init__(self, world, ident=1, with_system=True):
        self._world = world
        self.Id = types.SimpleNamespace(Value=ident)
        self.Name = "El"
        # Taggable: a wall with a point location, so tag_elements runs to the end.
        self.Category = types.SimpleNamespace(
            BuiltInCategory=world.db.BuiltInCategory.OST_Walls, Name="Walls")
        self.Location = types.SimpleNamespace(Point=XYZ(0, 0, 0))
        self.Parameters = []
        system = FakeElement(world, 7, with_system=False) if with_system else None
        self.ConnectorManager = types.SimpleNamespace(
            Connectors=[types.SimpleNamespace(MEPSystem=system)] if with_system else [])

    def LookupParameter(self, name):
        return FakeParam(self._world)

    def GetTypeId(self):
        return None


class World(object):
    """One fake Revit process: documents, the injected uiapp/doc, and an event log."""

    def __init__(self):
        self.events = []
        self.explode = False
        self.hooks = {}
        # A document attribute that must answer a configured object (not a recorded
        # MagicMock), such as ``doc.Create``; consulted before ``hooks``.
        self.attr_overrides = {}
        self.transactions = []
        self.collector_items = []
        self.commit_status = "Committed"
        self.break_start = set()
        self.sets = []
        self.app = RouteApplication(self)
        self.uiapp = RouteUIApp(self, self.app)
        self.injected = InjectedDocument(self)
        self.registry = identity.DocumentRegistry()
        self.db = None

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


class _Elements(list):
    """What ToElements answers: a list that also has the .NET collection's Count."""

    @property
    def Count(self):
        return len(self)


class XYZ(object):
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z

    def DistanceTo(self, other):
        return math.sqrt((self.X - other.X) ** 2 + (self.Y - other.Y) ** 2 + (self.Z - other.Z) ** 2)


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

        def _items(self):
            return [make(world) for make in world.collector_items]

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            if name == "ToElements":
                return lambda: _Elements(self._items())
            return lambda *args, **kwargs: self

        def __iter__(self):
            return iter(self._items())

        def __len__(self):
            return len(world.collector_items)

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
    db.TransactionStatus = types.SimpleNamespace(Committed="Committed", RolledBack="RolledBack")
    db.StorageType = types.SimpleNamespace(String="String", Integer="Integer",
                                           Double="Double", ElementId="ElementId")
    db.XYZ = XYZ
    db.Line = MagicMock(name="DB.Line")
    # Distinguishable ids: tag_elements builds an id per input and the fake document
    # answers by its value. A MagicMock caches its children, so OST_Walls is the same
    # key on every access.
    db.ElementId = MagicMock(
        name="DB.ElementId", side_effect=lambda value: types.SimpleNamespace(Value=int(value)))
    db.BuiltInCategory = MagicMock(name="DB.BuiltInCategory")
    created_tags = []

    def create_tag(*args, **kwargs):
        created_tags.append(args)
        return types.SimpleNamespace(Id=types.SimpleNamespace(Value=900 + len(created_tags)))

    db.IndependentTag = types.SimpleNamespace(Create=create_tag)
    return db


class HostAppTrap(object):
    """pyRevit's process-global HOST_APP. A handler must use the injected uiapp."""

    def __getattr__(self, name):
        raise AssertionError("HOST_APP." + name + " was read; use the injected uiapp")


ROUTE_MODULES = ("utils", "mep", "parameters", "rooms", "structure", "tags")


@pytest.fixture
def world(monkeypatch):
    """A fake Revit process with the route modules imported against a fake pyRevit.

    ``world.guard_calls`` counts calls of the production guard (it still runs for real),
    so a read that gained a guard, or a mutation that lost its call, is visible.
    """
    w = World()
    w.guard_calls = []
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
    w.db = db
    fake_pyrevit = types.SimpleNamespace(
        routes=types.SimpleNamespace(make_response=make_response),
        revit=MagicMock(name="revit"),
        DB=db,
        HOST_APP=HostAppTrap(),
    )
    monkeypatch.setitem(sys.modules, "pyrevit", fake_pyrevit)
    generic = types.ModuleType("System.Collections.Generic")
    generic.List = list
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


def request_of(body):
    if body is None:
        return types.SimpleNamespace(data=None)
    return types.SimpleNamespace(data=json.dumps(body).encode("utf-8"))


def call(world, fn, body=None, **extra):
    """Invoke a handler the way pyRevit does: injected arguments by name."""
    available = {"uiapp": world.uiapp, "doc": world.injected, "request": request_of(body)}
    available.update(extra)
    parameters = inspect.signature(fn).parameters
    return fn(**dict((name, available[name]) for name in parameters if name in available))


class StepParam(object):
    """A parameter a secondary step writes: read-only or raising on demand (D-12)."""

    StorageType = "String"
    HasValue = True

    def __init__(self, read_only=False, raises=None, value="", area=0.0):
        self.IsReadOnly = read_only
        self._raises = raises
        self._value = value
        self._area = area
        self.sets = []

    def Set(self, value):
        if self._raises is not None:
            raise self._raises
        self.sets.append(value)
        self._value = value
        return True

    def AsString(self):
        return self._value

    def AsDouble(self):
        return self._area


class StepElement(object):
    """A created element (duct, pipe, system, room) whose parameters a test configures.

    ``lookups`` records (name, commits seen so far) so a test can prove a read happened
    only after a committed commit."""

    def __init__(self, world, ident, params=None):
        self._world = world
        self.Id = types.SimpleNamespace(Value=ident)
        self.Name = "Created"
        self._params = params or {}
        self.lookups = []

    def LookupParameter(self, name):
        self.lookups.append((name, len(self._world.kinds("commit"))))
        return self._params.get(name)


class StepLine(object):
    def __init__(self, ident):
        self.Id = types.SimpleNamespace(Value=ident)


def override_create(world, **methods):
    """Make ``doc.Create`` answer a configured object: each keyword is a Create method
    name mapped to the callable that implements it."""
    create = MagicMock(name="Create")
    for name, fn in methods.items():
        getattr(create, name).side_effect = fn
    world.attr_overrides["Create"] = create
    return create


def arm(world, items=(), missing=()):
    """Collector results and the element GetElement answers, for a success path.

    ``missing`` lists element ids GetElement answers None for (an id that is not in the
    model); every other id is a taggable element carrying that id. ``doc.Create`` answers
    two room separation lines, so create_room_separation reaches a real success."""
    world.collector_items = list(items)
    override_create(world, NewRoomBoundaryLines=lambda *args: [StepLine(501), StepLine(502)])

    def get_element(doc, eid):
        value = getattr(eid, "Value", None)
        if value in missing:
            return None
        return FakeElement(world, value if isinstance(value, int) else 1)

    world.hooks[(None, "GetElement")] = get_element


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


def test_every_mutation_has_a_transacting_row():
    assert sorted(MUTATIONS) == sorted(TRANSACTING)


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
    if route == "/project_parameters/":
        def bindings():
            world.record("attr", world.injected, "ParameterBindings")
            return types.SimpleNamespace(
                ForwardIterator=lambda: types.SimpleNamespace(
                    Reset=lambda: None, MoveNext=lambda: False))
        world.injected.ParameterBindings = bindings()
        reply = call(world, fn)
    else:
        reply = call(world, fn, element_id="5")
    assert world.guard_calls == []
    assert world.events_on("INJECTED"), "a read still works on the injected doc"
    assert reply.status == 200
    assert "document" not in reply.data and "process_identity" not in reply.data


def test_the_route_modules_never_read_the_process_global_active_document():
    """Neither HOST_APP nor revit.doc: the document is the guard's, the process is the uiapp's."""
    for name in REGISTRARS:
        source = (REPO / "revit_mcp" / (name + ".py")).read_text(encoding="utf-8")
        assert "HOST_APP" not in source and "revit.doc" not in source, name


# ------------------------------------------------------------- refusals (G1, D-09/D-10)


def assert_refused(world, reply, status, code):
    assert reply.status == status
    assert reply.data["error"] and reply.data["error_code"] == code
    assert reply.data["process_identity"] == IDENT
    assert world.events == [], "a refused call opened a transaction or touched a document"


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_no_open_document_refuses_503_before_any_side_effect(world, key):
    reply = call(world, handler_of(world, *key), MUTATIONS[key])
    assert_refused(world, reply, 503, "no-open-document")


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_several_documents_without_a_selector_refuse_400_and_list_them(world, key):
    _, _, tokens = two_documents(world)
    reply = call(world, handler_of(world, *key), MUTATIONS[key])
    assert_refused(world, reply, 400, "document-selector-required")
    assert [c["document"] for c in reply.data["candidates"]] == tokens


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_explicit_inactive_document_is_exactly_412_with_zero_side_effects(world, key):
    _, _, tokens = two_documents(world, active="beta")
    body = dict(MUTATIONS[key], document=tokens[0])
    reply = call(world, handler_of(world, *key), body)
    assert_refused(world, reply, 412, "document-not-active")
    assert reply.data["active_document"] == tokens[1]


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_closed_document_is_refused_404_and_never_replaced_by_the_survivor(world, key):
    alpha, beta, tokens = two_documents(world, active="beta")
    world.app.close_document(alpha)
    body = dict(MUTATIONS[key], document=tokens[0])
    reply = call(world, handler_of(world, *key), body)
    assert_refused(world, reply, 404, "document-closed")


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
@pytest.mark.parametrize("selector", ["Alpha", "", None, 7, ["doc1.x.1"]],
                         ids=["title", "empty", "null", "number", "list"])
def test_an_invalid_selector_is_400_and_never_decays_into_the_sole_document(world, key, selector):
    world.open("Alpha", "C:/Models/Alpha.rvt", active=True)
    world.tokens()
    body = dict(MUTATIONS[key], document=selector)
    reply = call(world, handler_of(world, *key), body)
    assert_refused(world, reply, 400, "document-selector-invalid")


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_refusal_without_process_identity_says_why_and_still_refuses(world, key, monkeypatch):
    monkeypatch.setattr(identity, "process_identity_or_error",
                        lambda uiapp=None: (None, "no retained RoutesServer"))
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, *key), dict(MUTATIONS[key], document=tokens[0]))
    assert reply.status == 412 and world.events == []
    assert reply.data["identity_error"] == "no retained RoutesServer"
    assert "process_identity" not in reply.data


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_the_guard_is_called_once_with_the_selector_and_the_injected_uiapp(world, key):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    call(world, handler_of(world, *key), dict(MUTATIONS[key], document="doc1.zzzz.1"))
    assert len(world.guard_calls) == 1
    args, kwargs = world.guard_calls[0]
    assert (args[0] if args else kwargs.get("selector")) == "doc1.zzzz.1"
    assert kwargs["uiapp"] is world.uiapp


# ------------------------------------------------------------ guarded run + attribution


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_active_selection_runs_on_the_resolved_document_and_names_it(world, key):
    alpha, beta, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, *key), dict(MUTATIONS[key], document=tokens[1]))
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
    reply = call(world, handler_of(world, *key), MUTATIONS[key])
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
    reply = call(world, handler_of(world, *key), MUTATIONS[key])
    assert is_failure(reply)
    assert reply.data["document"]["title"] == "Only"
    assert reply.data["process_identity"] == IDENT


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_validation_error_after_the_guard_is_attributed_too(world, key):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, *key), {"unrelated": True})
    assert reply.status == 400 and reply.data["error"]
    assert reply.data["document"]["title"] == "Only"
    assert reply.data["process_identity"] == IDENT
    assert world.kinds("transaction") == []


# ----------------------------------------------- transactions: right document, warnings off


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_a_guarded_success_opens_its_transaction_on_the_resolved_document(world, key):
    items, body = TRANSACTING[key]
    arm(world, items)
    two_documents(world, active="beta")
    tokens = world.tokens()
    reply = call(world, handler_of(world, *key), dict(body, document=tokens[1]))
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["document"]["document"] == tokens[1]
    assert reply.data["process_identity"] == IDENT
    assert [event[1] for event in world.kinds("transaction")] == [BETA]
    assert world.events_on("INJECTED") == [] and world.events_on("Alpha") == []
    assert world.kinds("commit")


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_suppress_warnings_comes_immediately_after_start(world, key):
    items, body = TRANSACTING[key]
    arm(world, items)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    call(world, handler_of(world, *key), body)
    starts = [i for i, event in enumerate(world.events) if event[0] == "start"]
    assert starts, "the route opened no transaction"
    for index in starts:
        assert world.events[index + 1][:2] == ("txattr", "Only"), "no suppress_warnings after Start"
        assert world.events[index + 1][2] == "GetFailureHandlingOptions"


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_a_guarded_transaction_that_cannot_start_changes_nothing_and_names_the_document(world, key):
    items, body = TRANSACTING[key]
    arm(world, items)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.break_start.add("Only")
    reply = call(world, handler_of(world, *key), body)
    assert reply.status >= 400 and reply.data["error"]
    assert reply.data["document"]["title"] == "Only"
    assert world.kinds("commit") == []


EXPECTED_KEYS = {
    ("mep", "/create_duct/"): ["duct_id", "duct_type", "level", "message", "outcome", "status",
                               "system_type"],
    ("mep", "/create_pipe/"): ["level", "message", "outcome", "pipe_id", "pipe_type", "status",
                               "system_type"],
    ("mep", "/create_mep_system/"): ["element_count", "message", "outcome", "status", "system_id",
                                     "system_name", "system_type"],
    ("parameters", "/set_parameter/"): ["element_id", "message", "new_value", "old_value",
                                        "outcome", "parameter_name", "status",
                                        "transaction_status"],
    ("rooms", "/create_room/"): ["area", "level", "message", "name", "number", "outcome",
                                 "room_id", "status"],
    ("rooms", "/create_room_separation/"): ["line_count", "line_ids", "message", "outcome",
                                            "status"],
    ("structure", "/create_grid/"): ["count", "created", "message", "outcome", "status"],
    ("structure", "/create_framing/"): ["count", "created", "message", "outcome", "status"],
    ("tags", "/tag_elements/"): ["message", "outcome", "skipped", "status", "tag_ids",
                                 "tagged_count"],
}


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_a_guarded_success_keeps_its_original_body_keys(world, key):
    items, body = TRANSACTING[key]
    arm(world, items)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, *key), body)
    assert reply.status == 200
    assert sorted(without_attribution(reply.data)) == EXPECTED_KEYS[key]


# ------------------------------------------- set_parameter: the load-bearing 409 rollback


PARAM_BODY = {"element_id": 1, "parameter_name": "Mark", "value": "A"}


def test_a_rolled_back_parameter_write_stays_409_and_is_never_a_success(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    token = world.tokens()[0]
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "parameters", "/set_parameter/"), PARAM_BODY)
    assert reply.status == 409
    assert reply.data["status"] == "rolled_back"
    assert reply.data["status"] != "success" and "new_value" not in reply.data
    assert reply.data["attempted_value"] == "A" and reply.data["old_value"] == "old"
    assert reply.data["transaction_status"] == "RolledBack"
    assert "NOT changed" in reply.data["message"]
    assert reply.data["failures"] == []


def test_a_rolled_back_parameter_write_names_the_attempted_document_and_process(world):
    arm(world)
    world.open("Alpha", "C:/Models/Alpha.rvt")
    world.open(BETA, "", active=True)
    tokens = world.tokens()
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "parameters", "/set_parameter/"),
                 dict(PARAM_BODY, document=tokens[1]))
    assert reply.status == 409
    assert reply.data["document"] == {"document": tokens[1], "title": BETA, "path": "",
                                      "active": True, "saved": False}
    assert reply.data["process_identity"] == IDENT
    assert [event[1] for event in world.kinds("transaction")] == [BETA]
    assert [event[1] for event in world.kinds("commit")] == [BETA]
    assert world.events_on("INJECTED") == [] and world.events_on("Alpha") == []


def test_a_rolled_back_parameter_write_on_a_refused_document_never_starts_a_transaction(world):
    arm(world)
    _, _, tokens = two_documents(world, active="beta")
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "parameters", "/set_parameter/"),
                 dict(PARAM_BODY, document=tokens[0]))
    assert reply.status == 412 and world.events == []
    assert reply.data["error_code"] == "document-not-active"


def test_parameter_rollback_source_is_unchanged():
    """The 409 branch is what G6 will read; the identity work must not have reshaped it."""
    source = (REPO / "revit_mcp" / "parameters.py").read_text(encoding="utf-8")
    assert "commit_result = commit_and_report(t, swallower)" in source
    assert "if not commit_result[\"committed\"]:" in source
    assert "\"status\": \"rolled_back\"" in source
    assert re.search(r"status=409,\s*\)", source)
    assert source.count("status=409") == 1


def test_set_parameter_writes_inside_the_transaction_on_the_resolved_document(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "parameters", "/set_parameter/"), PARAM_BODY)
    assert reply.status == 200 and world.sets == ["A"]
    order = [event[0] for event in world.events if event[0] in ("transaction", "start", "commit")]
    assert order == ["transaction", "start", "commit"]
    assert reply.data["old_value"] == "old" and reply.data["new_value"] == "A"


# --------------------------------------- the resolved document is the one the body uses


@pytest.mark.parametrize("key", [("rooms", "/create_room_separation/"), ("tags", "/tag_elements/")])
def test_a_route_without_a_view_name_uses_the_active_view_of_the_resolved_document(world, key):
    """doc.ActiveView must be read from the guard's document, never the injected one."""
    arm(world, [_named("Plan A")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    body = dict(MUTATIONS[key])
    del body["view_name"]
    reply = call(world, handler_of(world, *key), body)
    assert "ActiveView" in world.attrs("Only")
    assert world.events_on("INJECTED") == []
    assert reply.data["document"]["title"] == "Only"


def test_create_grid_keeps_converting_millimetres_to_feet(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    call(world, handler_of(world, "structure", "/create_grid/"),
         {"grids": [{"start_point": {"x": 0, "y": 0, "z": 0},
                     "end_point": {"x": 304.8, "y": 609.6, "z": 0}}]})
    start, end = world.db.Line.CreateBound.call_args[0]
    assert (start.X, start.Y, start.Z) == (0.0, 0.0, 0.0)
    assert end.X == pytest.approx(1.0) and end.Y == pytest.approx(2.0)


def test_create_framing_keeps_offsetting_the_beam_by_its_level_elevation(world):
    arm(world, [_named("B", elevation=2.0)])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "structure", "/create_framing/"),
                 MUTATIONS[("structure", "/create_framing/")])
    assert reply.status == 200
    start, end = world.db.Line.CreateBound.call_args[0]
    assert start.Z == pytest.approx(2.0) and end.Z == pytest.approx(2.0)


def test_create_mep_system_without_element_ids_is_still_a_400_that_rolls_back(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "mep", "/create_mep_system/"),
                 {"system_type": "mechanical", "system_name": "S"})
    assert reply.status == 400 and "element_ids is required" in reply.data["error"]
    assert world.kinds("rollback") and world.kinds("commit") == []
    assert reply.data["document"]["title"] == "Only"


def test_a_missing_element_is_still_a_404_before_any_transaction_and_is_attributed(world):
    world.hooks[(None, "GetElement")] = lambda doc, eid: None
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "mep", "/create_mep_system/"),
                 MUTATIONS[("mep", "/create_mep_system/")])
    assert reply.status == 404 and world.kinds("transaction") == []
    assert reply.data["document"]["title"] == "Only"


# ------------------------------------------------ tag_elements: honest outcome (D-03, D-04, D-14)

MISSING_ID = 999999999


def test_tag_elements_mixed_batch_reaches_the_model_as_a_partial_with_the_failing_id(world):
    """The phase tracer: route handler -> outcome helpers -> reply -> format_response."""
    arm(world, [_named("Plan A")], missing=(MISSING_ID,))
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "tags", "/tag_elements/"),
                 {"element_ids": [5, MISSING_ID], "view_name": "Plan A"})
    assert reply.status == 200
    assert reply.data["status"] == "partial"
    assert reply.data["outcome"] == {
        "transaction_status": "Committed",
        "requested": 2,
        "succeeded": [5],
        "failed": [{"item": MISSING_ID, "reason": "Element not found"}],
        "revit_failures": [],
    }
    assert reply.data["tagged_count"] == 1
    assert reply.data["skipped"] == [{"element_id": MISSING_ID, "reason": "Element not found"}]
    assert len(reply.data["tag_ids"]) == 1
    text = format_response(reply.data)
    assert "=== PARTIAL SUCCESS ===" in text
    assert "Succeeded: 1 of 2" in text
    assert str(MISSING_ID) in text and "Element not found" in text
    assert "ERROR DETAILS" not in text


TAG_BODY = {"element_ids": [5, MISSING_ID], "view_name": "Plan A"}


def tag_handler(world):
    return handler_of(world, "tags", "/tag_elements/")


def test_tag_elements_rolled_back_at_commit_is_409_and_keeps_no_success_claim(world):
    arm(world, [_named("Plan A")], missing=(MISSING_ID,))
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.commit_status = "RolledBack"
    reply = call(world, tag_handler(world), TAG_BODY)
    assert reply.status == 409
    assert reply.data["status"] == "rolled_back"
    assert reply.data["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["failed"] == [{"item": MISSING_ID, "reason": "Element not found"}]
    assert "tag_ids" not in reply.data and "tagged_count" not in reply.data


def test_tag_elements_all_ids_missing_is_422_failed_and_the_model_reads_every_id(world):
    arm(world, [_named("Plan A")], missing=(MISSING_ID,))
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, tag_handler(world),
                 {"element_ids": [MISSING_ID], "view_name": "Plan A"})
    assert reply.status == 422
    assert reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == []
    assert len(reply.data["outcome"]["failed"]) == 1
    # The bridge turns a non-200 reply into this string; the model must see it verbatim.
    bridged = "Error: 422 - " + json.dumps(reply.data)
    assert format_response(bridged) == bridged
    assert str(MISSING_ID) in format_response(bridged)


def test_tag_elements_every_id_valid_is_200_success(world):
    arm(world, [_named("Plan A")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, tag_handler(world), {"element_ids": [5, 6], "view_name": "Plan A"})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"]["succeeded"] == [5, 6]
    assert reply.data["outcome"]["failed"] == []


def test_tag_elements_duplicate_valid_id_is_reported_twice_not_deduplicated(world):
    arm(world, [_named("Plan A")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, tag_handler(world), {"element_ids": [5, 5], "view_name": "Plan A"})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"]["requested"] == 2
    assert reply.data["outcome"]["succeeded"] == [5, 5]


def test_tag_elements_500_before_the_transaction_starts_still_carries_an_outcome(world):
    arm(world, [_named("Plan A")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    world.break_start.add("Only")
    reply = call(world, tag_handler(world), TAG_BODY)
    assert reply.status == 500 and reply.data["error"]
    assert reply.data["outcome"]["transaction_status"] == "Uninitialized"
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["requested"] == 2


def test_tag_elements_500_after_a_commit_names_committed_and_keeps_what_was_tagged(
        world, monkeypatch):
    """D-14: a call that raised after Commit() really did change the model."""
    arm(world, [_named("Plan A")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    handler = tag_handler(world)

    def explode(*args, **kwargs):
        raise RuntimeError("reply could not be built")

    monkeypatch.setattr(sys.modules["revit_mcp.tags"], "finalize_outcome", explode)
    reply = call(world, handler, {"element_ids": [5], "view_name": "Plan A"})
    assert reply.status == 500 and "reply could not be built" in reply.data["error"]
    assert reply.data["outcome"]["transaction_status"] == "Committed"
    assert reply.data["outcome"]["succeeded"] == [5]
    assert world.kinds("rollback") == [], "a committed transaction must not be rolled back"



# ----------------------------------- mep: honest outcomes (D-03, D-12, D-14, D-15; plan 04-02)


def mep_call(world, route, body, items=()):
    # A test configures GetElement / doc.Create first; arm() must not overwrite them.
    hook = world.hooks.get((None, "GetElement"))
    create = world.attr_overrides.get("Create")
    arm(world, items)
    if hook is not None:
        world.hooks[(None, "GetElement")] = hook
    if create is not None:
        world.attr_overrides["Create"] = create
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    return call(world, handler_of(world, "mep", route), body)


def create_answers(world, kind, created):
    """DB.Mechanical.Duct.Create / DB.Plumbing.Pipe.Create answer ``created``."""
    if kind == "duct":
        world.db.Mechanical = MagicMock(name="DB.Mechanical")
        world.db.Mechanical.Duct.Create.return_value = created
    else:
        world.db.Plumbing = MagicMock(name="DB.Plumbing")
        world.db.Plumbing.Pipe.Create.return_value = created


DIMENSION_CASES = [
    pytest.param(lambda: StepParam(read_only=True), "parameter is read-only", id="read-only"),
    pytest.param(lambda: None, "parameter not found", id="missing"),
    pytest.param(lambda: StepParam(raises=RuntimeError("bad")), "bad", id="raises"),
]

DUCT_OR_PIPE = [
    pytest.param("duct", "/create_duct/", "duct_id", "D", id="duct"),
    pytest.param("pipe", "/create_pipe/", "pipe_id", "P", id="pipe"),
]


@pytest.mark.parametrize("kind,route,id_key,item_name", DUCT_OR_PIPE)
@pytest.mark.parametrize("make_param,reason", DIMENSION_CASES)
def test_a_duct_or_pipe_whose_diameter_cannot_be_set_is_a_partial_naming_the_step(
        world, kind, route, id_key, item_name, make_param, reason):
    created = StepElement(world, 77, {"Diameter": make_param()})
    create_answers(world, kind, created)
    reply = mep_call(world, route, dict(_POINTS, diameter=200), [_named(item_name)])
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data[id_key] == 77
    assert reply.data["outcome"] == {
        "transaction_status": "Committed",
        "requested": 1,
        "succeeded": [77],
        "failed": [{"item": "diameter", "reason": reason}],
        "revit_failures": [],
    }
    assert "=== PARTIAL SUCCESS ===" in format_response(reply.data)


def test_a_duct_with_writable_width_and_height_is_a_success_with_nothing_failed(world):
    width, height = StepParam(), StepParam()
    create_answers(world, "duct", StepElement(world, 77, {"Width": width, "Height": height}))
    reply = mep_call(world, "/create_duct/", dict(_POINTS, width=300, height=150), [_named("D")])
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"]["failed"] == [] and reply.data["outcome"]["succeeded"] == [77]
    assert width.sets == [pytest.approx(300 * (1.0 / 304.8))]
    assert height.sets == [pytest.approx(150 * (1.0 / 304.8))]


def test_a_duct_whose_width_is_read_only_still_sets_the_height_and_reports_only_the_width(world):
    height = StepParam()
    create_answers(world, "duct", StepElement(
        world, 77, {"Width": StepParam(read_only=True), "Height": height}))
    reply = mep_call(world, "/create_duct/", dict(_POINTS, width=300, height=150), [_named("D")])
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"]["failed"] == [
        {"item": "width", "reason": "parameter is read-only"}]
    assert reply.data["outcome"]["succeeded"] == [77]
    assert len(height.sets) == 1


@pytest.mark.parametrize("kind,route,id_key,item_name", DUCT_OR_PIPE)
def test_a_pipe_or_duct_without_a_dimension_request_is_a_plain_success(
        world, kind, route, id_key, item_name):
    create_answers(world, kind, StepElement(world, 77))
    reply = mep_call(world, route, dict(_POINTS), [_named(item_name)])
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"]["succeeded"] == [77] and reply.data["outcome"]["failed"] == []
    assert reply.data[id_key] == 77


MEP_ROLLBACK_ROWS = [
    pytest.param("/create_duct/", dict(_POINTS), [_named("D")], "duct_id", id="duct"),
    pytest.param("/create_pipe/", dict(_POINTS), [_named("P")], "pipe_id", id="pipe"),
    pytest.param("/create_mep_system/",
                 {"system_type": "mechanical", "system_name": "S", "element_ids": [1]},
                 [], "system_id", id="mep_system"),
]


@pytest.mark.parametrize("route,body,items,id_key", MEP_ROLLBACK_ROWS)
def test_a_rolled_back_duct_pipe_or_mep_system_is_a_409_with_nothing_succeeded(
        world, route, body, items, id_key):
    world.commit_status = "RolledBack"
    reply = mep_call(world, route, body, items)
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == []
    assert id_key not in reply.data


class _Unassigned(object):
    """An element with one connector that belongs to no system yet."""

    def __init__(self, ident=1):
        self.Id = types.SimpleNamespace(Value=ident)
        self.ConnectorManager = types.SimpleNamespace(
            Connectors=[types.SimpleNamespace(MEPSystem=None)])


MEP_SYSTEM_BODY = {"system_type": "mechanical", "system_name": "S", "element_ids": [1]}


def test_create_mep_system_that_yields_no_system_rolls_back_and_answers_422(world):
    world.hooks[(None, "GetElement")] = lambda doc, eid: _Unassigned()
    override_create(world, NewMechanicalSystem=lambda *args: None)
    reply = mep_call(world, "/create_mep_system/", MEP_SYSTEM_BODY)
    assert reply.status == 422
    assert reply.data["status"] == "failed" and reply.data["error"]
    outcome = reply.data["outcome"]
    assert outcome["transaction_status"] == "RolledBack"
    assert outcome["requested"] == 1 and outcome["succeeded"] == []
    assert [entry["item"] for entry in outcome["failed"]] == ["system"]
    assert outcome["failed"][0]["reason"].startswith("Revit created no mechanical system")
    assert world.kinds("rollback") and world.kinds("commit") == []
    assert "system_id" not in reply.data


def test_create_mep_system_with_every_connector_assigned_is_still_a_500_with_an_outcome(world):
    world.hooks[(None, "GetElement")] = lambda doc, eid: FakeElement(world, 1, with_system=False)
    reply = mep_call(world, "/create_mep_system/", MEP_SYSTEM_BODY)
    assert reply.status == 500 and "already assigned" in reply.data["error"]
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["requested"] == 1


def renamed_system_world(world, name_param):
    """The element already belongs to system 901, whose name parameter is ``name_param``."""
    system = StepElement(world, 901, {"System Name": name_param})
    member = types.SimpleNamespace(
        Id=types.SimpleNamespace(Value=1),
        ConnectorManager=types.SimpleNamespace(
            Connectors=[types.SimpleNamespace(MEPSystem=system)]))
    world.hooks[(None, "GetElement")] = lambda doc, eid: system if eid.Value == 901 else member


def test_create_mep_system_rename_with_a_read_only_name_is_a_partial_naming_the_step(world):
    renamed_system_world(world, StepParam(read_only=True))
    reply = mep_call(world, "/create_mep_system/", MEP_SYSTEM_BODY)
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["succeeded"] == [901]
    assert reply.data["outcome"]["failed"] == [
        {"item": "system_name", "reason": "parameter is read-only"}]
    assert reply.data["system_id"] == 901


def test_create_mep_system_rename_with_a_writable_name_is_a_success_written_once(world):
    name = StepParam()
    renamed_system_world(world, name)
    reply = mep_call(world, "/create_mep_system/", MEP_SYSTEM_BODY)
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"]["succeeded"] == [901]
    assert reply.data["outcome"]["failed"] == []
    assert name.sets == ["S"]


@pytest.mark.parametrize("name_param,status,failed", [
    (StepParam(read_only=True), "partial", [{"item": "system_name",
                                            "reason": "parameter is read-only"}]),
    (StepParam(), "success", []),
], ids=["read-only", "writable"])
def test_a_newly_created_mep_system_reports_its_name_step(world, name_param, status, failed):
    world.hooks[(None, "GetElement")] = lambda doc, eid: _Unassigned()
    override_create(world, NewMechanicalSystem=lambda *args: StepElement(
        world, 88, {"System Name": name_param}))
    reply = mep_call(world, "/create_mep_system/", MEP_SYSTEM_BODY)
    assert reply.status == 200 and reply.data["status"] == status, reply.data
    assert reply.data["outcome"]["succeeded"] == [88]
    assert reply.data["outcome"]["failed"] == failed
    assert reply.data["system_id"] == 88


# --------------------------- rooms and structure: honest outcomes (D-12, TRUTH-03; plan 04-02)

ZERO_LENGTH = {"start_point": {"x": 0, "y": 0, "z": 0}, "end_point": {"x": 0, "y": 0, "z": 0}}


class StepGrid(object):
    """A grid whose Name setter can be made to raise, like a duplicate grid name."""

    def __init__(self, ident, name_raises=None):
        self.Id = types.SimpleNamespace(Value=ident)
        self._name = "G"
        self._raises = name_raises

    @property
    def Name(self):
        return self._name

    @Name.setter
    def Name(self, value):
        if self._raises is not None:
            raise self._raises
        self._name = value


def structure_call(world, route, body, items=()):
    arm(world, items)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    return call(world, handler_of(world, "structure", route), body)


def grid_answers(world, grid):
    world.db.Grid = MagicMock(name="DB.Grid")
    world.db.Grid.Create.return_value = grid


def test_create_grid_with_one_valid_and_one_zero_length_grid_is_a_partial_naming_the_index(world):
    grid_answers(world, StepGrid(31))
    reply = structure_call(world, "/create_grid/",
                           {"grids": [dict(_POINTS, name="A"), ZERO_LENGTH]})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"] == {
        "transaction_status": "Committed",
        "requested": 2,
        "succeeded": [31],
        "failed": [{"item": 1, "reason": "grid has zero length"}],
        "revit_failures": [],
    }
    assert reply.data["count"] == 1 and len(reply.data["created"]) == 1
    text = format_response(reply.data)
    assert "=== PARTIAL SUCCESS ===" in text and "grid has zero length" in text


def test_create_grid_with_only_zero_length_grids_is_a_422_failed(world):
    grid_answers(world, StepGrid(31))
    reply = structure_call(world, "/create_grid/", {"grids": [ZERO_LENGTH, ZERO_LENGTH]})
    assert reply.status == 422
    assert reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == []
    assert [entry["item"] for entry in reply.data["outcome"]["failed"]] == [0, 1]
    assert reply.data["count"] == 0


def test_create_grid_whose_name_cannot_be_set_is_a_partial_but_keeps_the_created_grid(world):
    grid_answers(world, StepGrid(31, name_raises=RuntimeError("dup")))
    reply = structure_call(world, "/create_grid/", {"grids": [dict(_POINTS, name="A")]})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["succeeded"] == [31]
    assert reply.data["outcome"]["failed"] == [{"item": "0.name", "reason": "dup"}]
    assert reply.data["count"] == 1


def test_create_grid_rolled_back_is_a_409_with_nothing_succeeded(world):
    grid_answers(world, StepGrid(31))
    world.commit_status = "RolledBack"
    reply = structure_call(world, "/create_grid/", {"grids": [dict(_POINTS, name="A")]})
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == []
    assert "created" not in reply.data and "count" not in reply.data


def test_create_framing_with_one_valid_and_one_zero_length_beam_is_a_partial(world):
    arm(world, [_named("B")])
    override_create(world, NewFamilyInstance=lambda *args: StepElement(world, 41))
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "structure", "/create_framing/"),
                 {"elements": [dict(_POINTS, type_name="B", level_name="L1"), ZERO_LENGTH]})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["requested"] == 2
    assert reply.data["outcome"]["succeeded"] == [41]
    assert reply.data["outcome"]["failed"] == [{"item": 1, "reason": "beam has zero length"}]
    assert reply.data["count"] == 1


def test_create_framing_with_only_zero_length_beams_is_a_422(world):
    arm(world, [_named("B")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "structure", "/create_framing/"),
                 {"elements": [ZERO_LENGTH]})
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["failed"] == [{"item": 0, "reason": "beam has zero length"}]


def test_create_framing_rolled_back_is_a_409_with_nothing_succeeded(world):
    arm(world, [_named("B")])
    world.commit_status = "RolledBack"
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "structure", "/create_framing/"),
                 MUTATIONS[("structure", "/create_framing/")])
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == []


ROOM_BODY = {"level_name": "L1", "name": "Lobby", "number": "101"}


def room_world(world, room, rolled_back=False):
    arm(world, [_named("L1")])
    override_create(world, NewRoom=lambda *args: room)
    if rolled_back:
        world.commit_status = "RolledBack"
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()


def make_room(world, **params):
    defaults = {"Name": StepParam(), "Number": StepParam(), "Area": StepParam(area=10.0)}
    defaults.update(params)
    return StepElement(world, 301, defaults)


@pytest.mark.parametrize("step,param_name,body_key", [
    ("name", "Name", "name"),
    ("number", "Number", "number"),
])
def test_create_room_whose_name_or_number_is_read_only_is_a_partial_naming_the_step(
        world, step, param_name, body_key):
    room = make_room(world, **{param_name: StepParam(read_only=True)})
    room_world(world, room)
    reply = call(world, handler_of(world, "rooms", "/create_room/"), ROOM_BODY)
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["succeeded"] == [301]
    assert reply.data["outcome"]["failed"] == [
        {"item": step, "reason": "parameter is read-only"}]
    assert reply.data["room_id"] == 301


def test_create_room_whose_name_raises_on_set_reports_the_exception_text(world):
    room = make_room(world, Name=StepParam(raises=RuntimeError("name taken")))
    room_world(world, room)
    reply = call(world, handler_of(world, "rooms", "/create_room/"), ROOM_BODY)
    assert reply.status == 200 and reply.data["status"] == "partial"
    assert reply.data["outcome"]["failed"] == [{"item": "name", "reason": "name taken"}]


def test_create_room_with_writable_name_and_number_is_a_success_that_reads_the_result(world):
    room = make_room(world)
    room_world(world, room)
    reply = call(world, handler_of(world, "rooms", "/create_room/"), ROOM_BODY)
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"] == {
        "transaction_status": "Committed", "requested": 1, "succeeded": [301],
        "failed": [], "revit_failures": [],
    }
    assert reply.data["name"] == "Lobby" and reply.data["number"] == "101"
    assert reply.data["area"] == pytest.approx(0.93, abs=0.01)


def test_create_room_rolled_back_is_a_409_and_never_reads_the_room_after_the_commit(world):
    room = make_room(world)
    room_world(world, room, rolled_back=True)
    reply = call(world, handler_of(world, "rooms", "/create_room/"), ROOM_BODY)
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == []
    assert "room_id" not in reply.data and "area" not in reply.data
    after_commit = [name for name, commits in room.lookups if commits >= 1]
    assert after_commit == [], "the room was read after a rolled-back commit"


def test_create_room_that_yields_no_room_is_still_a_500_that_rolls_back_with_an_outcome(world):
    room_world(world, None)
    reply = call(world, handler_of(world, "rooms", "/create_room/"), ROOM_BODY)
    assert reply.status == 500 and "Failed to create room" in reply.data["error"]
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == []
    assert world.kinds("rollback") and world.kinds("commit") == []


SEPARATION_BODY = {"lines": [dict(_POINTS), dict(_POINTS)], "view_name": "Plan A"}


def test_create_room_separation_that_creates_lines_lists_their_ids(world):
    arm(world, [_named("Plan A")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "rooms", "/create_room_separation/"), SEPARATION_BODY)
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"]["succeeded"] == [501, 502]
    assert reply.data["outcome"]["requested"] == 2
    assert reply.data["line_ids"] == [501, 502] and reply.data["line_count"] == 2


def test_create_room_separation_that_creates_nothing_is_a_422_naming_every_input_line(world):
    arm(world, [_named("Plan A")])
    override_create(world, NewRoomBoundaryLines=lambda *args: None)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "rooms", "/create_room_separation/"), SEPARATION_BODY)
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["failed"] == [
        {"item": 0, "reason": "NewRoomBoundaryLines created no line"},
        {"item": 1, "reason": "NewRoomBoundaryLines created no line"},
    ]


def test_create_room_separation_rolled_back_is_a_409_with_nothing_succeeded(world):
    arm(world, [_named("Plan A")])
    world.commit_status = "RolledBack"
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "rooms", "/create_room_separation/"), SEPARATION_BODY)
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == [] and "line_ids" not in reply.data


# ------------------------------------ set_parameter outcome (D-03) and the world-wide invariant


def parameter_world(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    return world.tokens()


def test_set_parameter_success_carries_the_outcome_with_the_parameter_name(world):
    parameter_world(world)
    reply = call(world, handler_of(world, "parameters", "/set_parameter/"), PARAM_BODY)
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"] == {
        "transaction_status": "Committed", "requested": 1, "succeeded": ["Mark"],
        "failed": [], "revit_failures": [],
    }
    assert reply.data["old_value"] == "old" and reply.data["new_value"] == "A"
    assert reply.data["transaction_status"] == "Committed"


def test_set_parameter_rollback_carries_the_outcome_and_stays_409(world):
    parameter_world(world)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "parameters", "/set_parameter/"), PARAM_BODY)
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["attempted_value"] == "A" and reply.data["old_value"] == "old"
    assert reply.data["outcome"] == {
        "transaction_status": "RolledBack", "requested": 1, "succeeded": [],
        "failed": [], "revit_failures": [],
    }


class _OddParam(FakeParam):
    """A parameter whose StorageType is none of String, Integer, Double or ElementId."""

    StorageType = "None"


def test_set_parameter_with_an_unsupported_storage_type_rolls_back_and_is_a_400(world):
    parameter_world(world)
    odd = _OddParam(world)
    element = FakeElement(world, 1)
    element.LookupParameter = lambda name: odd
    world.hooks[(None, "GetElement")] = lambda doc, eid: element
    reply = call(world, handler_of(world, "parameters", "/set_parameter/"), PARAM_BODY)
    assert reply.status == 400
    assert "storage type" in reply.data["error"] and "None" in reply.data["error"]
    assert reply.data.get("status") != "success" and "new_value" not in reply.data
    assert world.kinds("rollback") and world.kinds("commit") == []
    assert world.sets == []


def test_set_parameter_500_before_the_transaction_starts_carries_the_real_status(world):
    parameter_world(world)
    world.break_start.add("Only")
    reply = call(world, handler_of(world, "parameters", "/set_parameter/"), PARAM_BODY)
    assert reply.status == 500 and reply.data["error"]
    assert reply.data["outcome"]["transaction_status"] == "Uninitialized"
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["requested"] == 1


def reach(world, key):
    items, body = TRANSACTING[key]
    arm(world, items)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    return body


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_every_transacting_success_carries_an_outcome_that_agrees_with_its_status(world, key):
    body = reach(world, key)
    reply = call(world, handler_of(world, *key), body)
    assert reply.status == 200, reply.data
    outcome = reply.data["outcome"]
    assert outcome["transaction_status"] == "Committed"
    expected = classify_outcome(True, len(outcome["succeeded"]), len(outcome["failed"]))
    assert (reply.data["status"], reply.status) == expected


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_every_transacting_rollback_is_a_409_with_nothing_succeeded(world, key):
    body = reach(world, key)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, *key), body)
    assert reply.status == 409, reply.data
    assert reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == []


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_every_transacting_500_carries_the_real_transaction_status(world, key):
    body = reach(world, key)
    world.break_start.add("Only")
    reply = call(world, handler_of(world, *key), body)
    assert reply.status == 500, reply.data
    assert world.transactions, "the route never built a transaction"
    assert reply.data["outcome"]["transaction_status"] == world.transactions[-1].status
    assert reply.data["outcome"]["succeeded"] == []
