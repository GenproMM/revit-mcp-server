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
        hook = self._world.hooks.get((self.label, name)) or self._world.hooks.get((None, name))
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
                return lambda: self._items()
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
    return fn(**dict((name, available[name]) for name in parameters))


def arm(world, items=()):
    """Collector results and the element GetElement answers, for a success path."""
    world.collector_items = list(items)
    world.hooks[(None, "GetElement")] = lambda doc, eid: FakeElement(world)


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
    ("mep", "/create_duct/"): ["duct_id", "duct_type", "level", "message", "status", "system_type"],
    ("mep", "/create_pipe/"): ["level", "message", "pipe_id", "pipe_type", "status", "system_type"],
    ("mep", "/create_mep_system/"): ["element_count", "message", "status", "system_id",
                                     "system_name", "system_type"],
    ("parameters", "/set_parameter/"): ["element_id", "message", "new_value", "old_value",
                                        "parameter_name", "status", "transaction_status"],
    ("rooms", "/create_room/"): ["area", "level", "message", "name", "number", "room_id", "status"],
    ("rooms", "/create_room_separation/"): ["line_count", "line_ids", "message", "status"],
    ("structure", "/create_grid/"): ["count", "created", "message", "status"],
    ("structure", "/create_framing/"): ["count", "created", "message", "status"],
    ("tags", "/tag_elements/"): ["message", "skipped", "status", "tag_ids", "tagged_count"],
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
