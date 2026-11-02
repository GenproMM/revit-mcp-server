# -*- coding: utf-8 -*-
"""Document guard on the transform and view mutations, process-scoped open_model, and the
D-15 arbitrary-code exception (plan 02-15; D-01, D-05, D-08, D-09, D-10, D-15, G1).

Offline evidence only. The real route modules are imported against a fake pyRevit and
registered through their real register_*_routes functions with a fake api. Every row drives
the handler the way pyRevit would (injected uiapp, doc, uidoc, request by name) and observes
every document, collector, transaction and view switch the handler touched.

What this proves:

* transform_elements, create_view and set_active_view call the guard first, refuse before
  any side effect, work on the document the guard resolved (never the injected ``doc``) and
  stamp that document and the process on every reply. set_active_view is a document-bound
  mutation: it never activates a document to satisfy a selection.
* open_model is process-level, not document-bound: it takes no selector and is never
  refused for a document count, keeps its workset-aware opening, and its reply names the
  Document Revit actually opened (read from that Document after the API call, never from
  the requested path) and the process.
* /execute_code/ and execute_revit_code stay enabled as the user's trusted exception (D-15):
  no selector, no guard, no 412, no confinement claim. Every reply of the route carries the
  constant document_scope notice and the process identity and attributes no changed
  document; the tool forwards ``target`` (so the call still passes listener preflight and
  the per-target lock) and has no document parameter.

What it does not prove: how pyRevit dispatches these handlers or how a real Document
answers. That is a live recheck after a full Revit close and reopen (never pyRevit Reload).
Nothing here touches Revit.
"""

import asyncio
import datetime
import importlib
import inspect
import json
import math
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from gate_support import TEST_ROUTE, TEST_SECRET, configure_gate, enveloped_body, request_of
from revit_mcp import identity, trust
from revit_mcp.textutils import classify_outcome

IDENT = {"pid": 4242, "actual_port": 48885, "session_token": "tok-abc", "revit_version": "2024"}

BETA = u"\u0411\u0435\u0442\u0430"
ONLY_PATH = "C:/Models/Only.rvt"

REPO = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------- the classification
#
# Hand classification of every route in the four owned registrars. A route that is not
# listed here fails test_every_registered_route_is_classified, so a new route cannot slip in
# unguarded or be mislabelled silently. Classified by what a route DOES, not its HTTP method:
# model_worksets is a POST that only previews a file on disk, so it is a read.

REGISTRARS = {
    "transforms": "register_transform_routes",
    "view_management": "register_view_management_routes",
    "worksharing": "register_worksharing_routes",
    "code_execution": "register_code_execution_routes",
}

# (module, route) -> a body that gets past early validation and touches the document.
MUTATIONS = {
    ("transforms", "/transform_elements/"): {"element_ids": [1], "operation": "move",
                                             "vector": {"x": 10, "y": 0, "z": 0}},
    ("view_management", "/create_view/"): {"view_type": "3d", "name": "V1"},
    ("view_management", "/set_active_view/"): {"view_name": "Plan A"},
}
MUTATION_IDS = ["{}:{}".format(module, route) for module, route in MUTATIONS]

# (module, route, method) -> the parameters it must keep: no uiapp, no guard.
READS = {
    ("worksharing", "/model_worksets/", "POST"): ["doc", "request"],
}

# Process-level: addressed by the call's `target`, never by a document selector.
PROCESS_LEVEL = {
    ("worksharing", "/open_model/"),
    ("code_execution", "/execute_code/"),
}


class _Item(object):
    """A collector result: a named element with the few members the routes read."""

    def __init__(self, world, name="Item", **members):
        self.world = world
        self.Name = name
        self.Id = types.SimpleNamespace(Value=11)
        self.IsTemplate = False
        self.GenLevel = None
        self.ViewType = "FloorPlan"
        for key, value in members.items():
            setattr(self, key, value)


def _named(name, **members):
    return lambda world: _Item(world, name, **members)


def _family(attribute):
    """A ViewFamilyType of the given DB.ViewFamily member."""
    return lambda world: _Item(world, "VFT", ViewFamily=getattr(world.db.ViewFamily, attribute))


# Routes that open a transaction on the document and succeed with HTTP 200:
# (collector items the route finds, body).
TRANSACTING = {
    ("transforms", "/transform_elements/"): ([], MUTATIONS[("transforms", "/transform_elements/")]),
    ("view_management", "/create_view/"): ([_family("ThreeDimensional")],
                                           MUTATIONS[("view_management", "/create_view/")]),
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
    """A wrapper over one open lifetime. Anything the guard does not read is recorded as a
    touch (and raises when the world is set to explode), so a handler that works on the
    wrong document or before the guard is visible in ``world.events``."""

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
    """The ``doc`` pyRevit injects. A handler that ignores the guard and uses it shows up
    as an event labelled INJECTED."""

    label = "INJECTED"

    def __init__(self, world):
        self._world = world

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        self._world.record("attr", self, name)
        return MagicMock(name=name)


class FakeUIDocument(_Touchable):
    """The UI side of one open lifetime; assigning ActiveView is the recorded side effect."""

    def __init__(self, world, lifetime):
        self._world = world
        self._lifetime = lifetime

    @property
    def label(self):
        return self._lifetime.title

    @property
    def Document(self):
        return RouteDocument(self._world, self._lifetime)

    @property
    def ActiveView(self):
        return None

    @ActiveView.setter
    def ActiveView(self, view):
        self._world.record("setview", self, getattr(view, "Name", None))


class RouteApplication(object):
    VersionNumber = "2024"

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

    def OpenDocumentFile(self, path, options):
        """Open without activating: what Revit opened is world.open_plan, not ``path``."""
        w = self._world
        w.open_calls.append(("open", path, options))
        error = w.next_open_error()
        if error:
            raise RuntimeError(error)
        if w.open_returns_none:
            return None
        title, actual = w.open_plan
        return self.open_document(title, actual)


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
        return FakeUIDocument(self._world, self.active._lifetime)

    def OpenAndActivateDocument(self, path, options, flag):
        w = self._world
        w.open_calls.append(("activate", path, options))
        error = w.next_open_error()
        if error:
            raise RuntimeError(error)
        if w.open_returns_none:
            return None
        title, actual = w.open_plan
        self.active = self.app.open_document(title, actual)
        return self.ActiveUIDocument


class World(object):
    """One fake Revit process: documents, the injected uiapp/doc, and an event log."""

    def __init__(self):
        self.events = []
        self.explode = False
        self.hooks = {}
        self.collector_items = []
        self.commit_status = "Committed"
        self.transactions = []
        self.break_start = set()
        self.open_calls = []
        self.open_error = None
        self.open_errors = []
        self.open_returns_none = False
        self.open_plan = ("Gamma", "C:/Models/Actual.rvt")
        self.app = RouteApplication(self)
        self.uiapp = RouteUIApp(self, self.app)
        self.injected = InjectedDocument(self)
        self.registry = identity.DocumentRegistry()
        self.db = None

    def next_open_error(self):
        """A queued per-attempt error (None entry = succeed), else the standing open_error."""
        if self.open_errors:
            return self.open_errors.pop(0)
        return self.open_error

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
        active = self.uiapp.ActiveUIDocument
        snapshot = (self.app.Documents, active.Document if active is not None else None)
        listing = identity.current_document_descriptors(snapshot, self.registry)
        assert listing["ok"], listing
        return [entry["document"] for entry in listing["documents"]]


class XYZ(object):
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z

    def DistanceTo(self, other):
        return math.sqrt((self.X - other.X) ** 2 + (self.Y - other.Y) ** 2 + (self.Z - other.Z) ** 2)

    def GetLength(self):
        return math.sqrt(self.X ** 2 + self.Y ** 2 + self.Z ** 2)

    def Normalize(self):
        length = self.GetLength() or 1.0
        return XYZ(self.X / length, self.Y / length, self.Z / length)

    def CrossProduct(self, other):
        return XYZ(self.Y * other.Z - self.Z * other.Y,
                   self.Z * other.X - self.X * other.Z,
                   self.X * other.Y - self.Y * other.X)


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
                return lambda: self._items()
            return lambda *args, **kwargs: self

        def __iter__(self):
            return iter(self._items())

        def __len__(self):
            return len(world.collector_items)

    class IFailuresPreprocessor(object):
        pass

    class _DB(object):
        """Members that tests compare are created once, so two reads are the same object."""

        def __init__(self):
            object.__setattr__(self, "_made", {})

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            made = self._made
            if name not in made:
                made[name] = MagicMock(name="DB." + name)
            return made[name]

    db = _DB()
    db.Transaction = Transaction
    db.FilteredElementCollector = FilteredElementCollector
    db.IFailuresPreprocessor = IFailuresPreprocessor
    db.TransactionStatus = types.SimpleNamespace(Committed="Committed", RolledBack="RolledBack")
    XYZ.Zero = XYZ(0.0, 0.0, 0.0)
    db.XYZ = XYZ
    db.BasicFileInfo = types.SimpleNamespace(Extract=lambda model_path: None)
    db.DetachFromCentralOption = types.SimpleNamespace(
        DetachAndPreserveWorksets="PRESERVE", DetachAndDiscardWorksets="DISCARD",
        DoNotDetach="NONE")
    return db


class HostAppTrap(object):
    """pyRevit's process-global HOST_APP. A handler must use the injected uiapp."""

    def __getattr__(self, name):
        raise AssertionError("HOST_APP." + name + " was read; use the injected uiapp")


class FList(list):
    """System.Collections.Generic.List: Add and Count."""

    def Add(self, item):
        self.append(item)

    @property
    def Count(self):
        return len(self)


ROUTE_MODULES = ("utils", "transforms", "view_management", "worksharing", "code_execution")


@pytest.fixture
def world(monkeypatch):
    """A fake Revit process with the route modules imported against a fake pyRevit.

    ``world.guard_calls`` counts calls of the production guard (it still runs for real), so a
    process-level route that gained a guard, or a mutation that lost its call, is visible.
    """
    w = World()
    configure_gate(monkeypatch)
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
        revit=types.SimpleNamespace(doc=MagicMock(name="revit.doc")),
        DB=db,
        HOST_APP=HostAppTrap(),
    )
    monkeypatch.setitem(sys.modules, "pyrevit", fake_pyrevit)
    generic = types.ModuleType("System.Collections.Generic")
    generic.List = FList
    collections_mod = types.ModuleType("System.Collections")
    collections_mod.Generic = generic
    system = types.ModuleType("System")
    system.Collections = collections_mod
    system.Int64 = int  # make_element_id builds DB.ElementId(System.Int64(n))
    monkeypatch.setitem(sys.modules, "System", system)
    monkeypatch.setitem(sys.modules, "System.Collections", collections_mod)
    monkeypatch.setitem(sys.modules, "System.Collections.Generic", generic)
    monkeypatch.setitem(sys.modules, "clr", types.ModuleType("clr"))

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


def call(world, fn, body=None, **extra):
    """Invoke a handler the way pyRevit does: injected arguments by name."""
    available = {"uiapp": world.uiapp, "doc": world.injected,
                 "uidoc": world.uiapp.ActiveUIDocument,
                 "request": request_of(body, route=route_of(world, fn))}
    available.update(extra)
    parameters = inspect.signature(fn).parameters
    if "document" in parameters:
        available["uiapp"] = None
    return fn(**dict((name, available[name]) for name in parameters if name in available))


def arm(world, items=()):
    """Collector results and the element GetElement answers, for a success path."""
    world.collector_items = list(items)
    world.hooks[(None, "GetElement")] = lambda doc, eid: types.SimpleNamespace(
        Id=types.SimpleNamespace(Value=1), Name="El")


def two_documents(world, active="beta"):
    alpha = world.open("Alpha", "C:/Models/Alpha.rvt")
    beta = world.open(BETA, "")
    world.activate(beta if active == "beta" else alpha)
    return alpha, beta, world.tokens()


def armed_items(key):
    items = TRANSACTING[key][0] if key in TRANSACTING else [_named("Plan A")]
    return items


ATTRIBUTION_KEYS = ("document", "process_identity")


def without_attribution(data):
    return dict((key, value) for key, value in data.items() if key not in ATTRIBUTION_KEYS)


# ------------------------------------------------------------------ classification


@pytest.mark.parametrize("module_name", sorted(REGISTRARS))
def test_every_registered_route_is_classified(world, module_name):
    registered = set(load(world, module_name))
    expected = set((route, "POST") for (module, route) in MUTATIONS if module == module_name)
    expected |= set((route, method) for (module, route, method) in READS if module == module_name)
    expected |= set((route, "POST") for (module, route) in PROCESS_LEVEL if module == module_name)
    assert registered == expected, (
        "classify every route of revit_mcp/{}.py as a mutation, a read or process-level here".format(
            module_name))


# ------------------------------------------------------------------ API-context pin


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_mutation_handler_declares_the_api_context_arguments(world, key):
    """pyRevit runs a handler in the Revit API context only if it declares uiapp, uidoc or
    doc. The injected arguments stay; uiapp is added so the guard never needs HOST_APP."""
    module_name, route = key
    parameters = list(inspect.signature(handler_of(world, module_name, route)).parameters)
    if route == "/set_active_view/":
        assert parameters == ["uiapp", "doc", "uidoc", "request"]
    else:
        assert parameters == ["uiapp", "doc", "request"]


@pytest.mark.parametrize("route", ["/open_model/", "/execute_code/"])
def test_process_level_handlers_declare_uiapp_for_the_process_identity(world, route):
    module_name = "worksharing" if route == "/open_model/" else "code_execution"
    parameters = list(inspect.signature(handler_of(world, module_name, route)).parameters)
    assert parameters == ["uiapp", "doc", "request"]


@pytest.mark.parametrize("key", list(READS), ids=["{}:{}".format(k[0], k[1]) for k in READS])
def test_reads_keep_their_signature_and_are_not_guarded(world, key):
    module_name, route, method = key
    fn = handler_of(world, module_name, route, method)
    assert list(inspect.signature(fn).parameters) == READS[key]
    reply = call(world, fn, {})
    assert world.guard_calls == []
    assert reply.status == 400, "a preview with no file_path is still its own 400"
    assert "document" not in reply.data and "process_identity" not in reply.data


def test_the_route_modules_never_read_the_process_global_active_document():
    """Neither HOST_APP nor revit.doc: the document is the guard's, the process is the uiapp's.

    execute_code keeps its pre-existing ``revit.doc`` fallback for a null injected doc (D-15:
    execution semantics unchanged), so it is the one module exempt from the revit.doc part.
    """
    for name in ("transforms", "view_management", "worksharing", "code_execution"):
        source = (REPO / "revit_mcp" / (name + ".py")).read_text(encoding="utf-8")
        assert "HOST_APP" not in source, name
        if name != "code_execution":
            assert "revit.doc" not in source, name


# ------------------------------------------------------------- refusals (G1, D-09/D-10)


def assert_refused(world, reply, status, code):
    assert reply.status == status
    assert reply.data["error"] and reply.data["error_code"] == code
    assert reply.data["process_identity"] == IDENT
    assert world.events == [], "a refused call opened a transaction, switched a view or touched a document"


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
    assert world.kinds("setview") == []


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
    arm(world, armed_items(key))
    alpha, beta, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, *key), dict(MUTATIONS[key], document=tokens[1]))
    assert len(world.guard_calls) == 1
    assert world.events_on("INJECTED") == [], "the handler worked on the injected doc, not the guard's"
    assert world.events_on("Alpha") == []
    assert world.events_on(BETA), "the handler never touched the resolved document"
    assert reply.status == 200, reply.data
    assert reply.data["document"] == {"document": tokens[1], "title": BETA, "path": "",
                                      "active": True, "saved": False}
    assert reply.data["process_identity"] == IDENT


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_sole_active_document_is_used_without_a_selector_and_named(world, key):
    arm(world, armed_items(key))
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
    ("transforms", "/transform_elements/"): ["count", "message", "operation", "outcome", "status"],
    ("view_management", "/create_view/"): ["message", "name", "outcome", "status", "view_id",
                                           "view_type"],
    ("view_management", "/set_active_view/"): ["message", "name", "outcome", "status", "view_id",
                                               "view_type"],
}


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_guarded_success_keeps_its_original_body_keys(world, key):
    arm(world, armed_items(key))
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, *key), MUTATIONS[key])
    assert reply.status == 200, reply.data
    assert sorted(without_attribution(reply.data)) == EXPECTED_KEYS[key]


# ------------------------------------------------------------ set_active_view specifics


SET_VIEW = ("view_management", "/set_active_view/")


def test_set_active_view_switches_the_view_of_the_resolved_active_document_only(world):
    arm(world, [_named("Plan A")])
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, *SET_VIEW), dict(MUTATIONS[SET_VIEW], document=tokens[1]))
    assert reply.status == 200 and reply.data["name"] == "Plan A"
    assert [event[1] for event in world.kinds("setview")] == [BETA]
    assert world.kinds("transaction") == [], "a view switch is a UI operation, not a transaction"


def test_set_active_view_never_activates_a_document_to_satisfy_a_selection(world):
    arm(world, [_named("Plan A")])
    alpha, beta, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, *SET_VIEW), dict(MUTATIONS[SET_VIEW], document=tokens[0]))
    assert reply.status == 412
    assert world.uiapp.active is beta, "the active document must not have changed"
    assert world.kinds("setview") == [] and world.open_calls == []


def test_set_active_view_refuses_when_the_injected_uidoc_is_not_the_resolved_document(world):
    """The injected uidoc is the UI's active document; if it is not the guard's document the
    switch must not land there. Nothing changes and the reply still names the document."""
    arm(world, [_named("Plan A")])
    alpha, beta, tokens = two_documents(world, active="beta")
    stray = FakeUIDocument(world, alpha._lifetime)
    reply = call(world, handler_of(world, *SET_VIEW), dict(MUTATIONS[SET_VIEW], document=tokens[1]),
                 uidoc=stray)
    assert reply.status == 412 and reply.data["error_code"] == "document-not-active"
    assert world.kinds("setview") == []
    assert reply.data["document"]["document"] == tokens[1]
    assert reply.data["process_identity"] == IDENT


def test_set_active_view_without_a_uidoc_refuses_instead_of_guessing(world):
    arm(world, [_named("Plan A")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, *SET_VIEW), MUTATIONS[SET_VIEW], uidoc=None)
    assert reply.status == 412 and world.kinds("setview") == []


def test_set_active_view_unknown_view_is_404_and_changes_nothing(world):
    arm(world, [_named("Other")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, *SET_VIEW), MUTATIONS[SET_VIEW])
    assert reply.status == 404 and reply.data["available_views"] == ["Other"]
    assert world.kinds("setview") == []
    assert reply.data["document"]["title"] == "Only"


# --------------------------------------- the resolved document is the one the body uses


def test_create_view_elevation_reads_the_active_view_of_the_resolved_document(world):
    """doc.ActiveView must be read from the guard's document, never the injected one."""
    elevation = lambda w: _Item(w, "VFT", ViewFamily=w.db.ViewFamily.Elevation,
                                ViewType=w.db.ViewType.FloorPlan)
    arm(world, [elevation])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "view_management", "/create_view/"),
                 {"view_type": "elevation", "name": "E1"})
    assert reply.status == 200, reply.data
    assert "ActiveView" in world.attrs("Only")
    assert world.events_on("INJECTED") == []


def test_create_view_keeps_its_section_basis_and_rollbacks(world):
    arm(world, [_family("Section")])
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    parallel = {"view_type": "section", "name": "S1",
                "section_box": {"direction": {"x": 0, "y": 0, "z": 1}, "up": {"x": 0, "y": 0, "z": 1}}}
    reply = call(world, handler_of(world, "view_management", "/create_view/"), parallel)
    assert reply.status == 400 and "perpendicular" in reply.data["error"]
    assert world.kinds("rollback") and world.kinds("commit") == []
    assert reply.data["document"]["title"] == "Only"


def test_transform_keeps_converting_millimetres_to_feet(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    call(world, handler_of(world, "transforms", "/transform_elements/"),
         {"element_ids": [1], "operation": "move", "vector": {"x": 304.8, "y": 609.6, "z": 0}})
    # MoveElement(doc, id, translation) is the one document-changing call of a move.
    transform_utils = world.db.ElementTransformUtils
    doc_arg, _, translation = transform_utils.MoveElement.call_args[0]
    assert getattr(doc_arg, "label", None) == "Only"
    assert translation.X == pytest.approx(1.0) and translation.Y == pytest.approx(2.0)


def test_transform_missing_element_is_still_a_404_before_any_transaction_and_is_attributed(world):
    world.hooks[(None, "GetElement")] = lambda doc, eid: None
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "transforms", "/transform_elements/"),
                 MUTATIONS[("transforms", "/transform_elements/")])
    assert reply.status == 404 and world.kinds("transaction") == []
    assert reply.data["document"]["title"] == "Only"


def test_transform_missing_vector_still_rolls_back_with_a_400(world):
    arm(world)
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    reply = call(world, handler_of(world, "transforms", "/transform_elements/"),
                 {"element_ids": [1], "operation": "move"})
    assert reply.status == 400 and "vector is required" in reply.data["error"]
    assert world.kinds("rollback") and world.kinds("commit") == []


# ------------------------------------------------- outcomes (phase 4, TRUTH-01, D-01, D-06, D-12)

TRANSFORM = ("transforms", "/transform_elements/")
CREATE = ("view_management", "/create_view/")


def only_document(world):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()


def reach(world, key):
    """Arm the fake so the row's route reaches a real success on the one open document."""
    items, body = TRANSACTING[key]
    arm(world, items)
    only_document(world)
    return body


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_every_transacting_success_carries_an_outcome_that_agrees_with_its_status(world, key):
    reply = call(world, handler_of(world, *key), reach(world, key))
    assert reply.status in (200, 422), reply.data
    outcome = reply.data["outcome"]
    assert outcome["transaction_status"] == "Committed"
    expected = classify_outcome(True, len(outcome["succeeded"]), len(outcome["failed"]))
    assert (reply.data["status"], reply.status) == expected
    assert reply.status == 200, "the armed row must reach a real success: {}".format(reply.data)


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


# --- transform_elements (all or nothing)


def test_a_committed_transform_reports_every_requested_id_as_succeeded(world):
    arm(world)
    only_document(world)
    reply = call(world, handler_of(world, *TRANSFORM),
                 {"element_ids": [1, 2], "operation": "move", "vector": {"x": 10, "y": 0, "z": 0}})
    assert reply.status == 200 and reply.data["status"] == "success"
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": 2,
                                     "succeeded": [1, 2], "failed": [], "revit_failures": []}
    assert reply.data["count"] == 2 and reply.data["message"] == "Moved 2 elements"


def test_a_committed_copy_keeps_new_element_ids_beside_the_outcome(world):
    arm(world)
    world.db.ElementTransformUtils = types.SimpleNamespace(
        CopyElement=lambda doc, eid, translation: [types.SimpleNamespace(Value=9)])
    only_document(world)
    reply = call(world, handler_of(world, *TRANSFORM),
                 {"element_ids": [1], "operation": "copy", "vector": {"x": 10, "y": 0, "z": 0}})
    assert reply.status == 200, reply.data
    assert reply.data["new_element_ids"] == [9]
    assert reply.data["outcome"]["succeeded"] == [1]


def test_a_rolled_back_transform_is_a_409_that_names_no_count_or_operation(world):
    arm(world)
    only_document(world)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, *TRANSFORM), MUTATIONS[TRANSFORM])
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert "count" not in reply.data and "operation" not in reply.data
    assert reply.data["outcome"]["requested"] == 1 and reply.data["outcome"]["succeeded"] == []


def test_a_transform_that_raises_mid_way_rolls_back_and_says_so(world):
    arm(world)

    def explode(doc, eid, translation):
        raise RuntimeError("element is pinned by a constraint")

    world.db.ElementTransformUtils = types.SimpleNamespace(MoveElement=explode)
    only_document(world)
    reply = call(world, handler_of(world, *TRANSFORM), MUTATIONS[TRANSFORM])
    assert reply.status == 500 and "pinned by a constraint" in reply.data["error"]
    assert reply.data["outcome"] == {"transaction_status": "RolledBack", "requested": 1,
                                     "succeeded": [], "failed": [], "revit_failures": []}
    assert world.kinds("commit") == []


def test_transform_refusals_before_the_commit_carry_no_outcome(world):
    world.hooks[(None, "GetElement")] = lambda doc, eid: None
    only_document(world)
    missing = call(world, handler_of(world, *TRANSFORM), MUTATIONS[TRANSFORM])
    assert missing.status == 404 and "outcome" not in missing.data
    arm(world)
    novector = call(world, handler_of(world, *TRANSFORM), {"element_ids": [1], "operation": "move"})
    assert novector.status == 400 and "outcome" not in novector.data


# --- create_view (D-12: the name is a step; the view is read only after a committed commit)


def tracked_view(world, name_error=None):
    """The view the fake creation call returns. Every public read is logged as a viewread
    event, so a test can prove nothing was read from it after the commit event."""

    class TrackedView(object):
        Id = types.SimpleNamespace(Value=77)
        ViewType = "ThreeD"
        _name = "Default"

        @property
        def Name(self):
            return self._name

        @Name.setter
        def Name(self, value):
            if name_error:
                raise RuntimeError(name_error)
            self._name = value

        def __getattribute__(self, attribute):
            if not attribute.startswith("_"):
                world.events.append(("viewread", "VIEW", attribute))
            return object.__getattribute__(self, attribute)

    view = TrackedView()
    world.db.View3D = types.SimpleNamespace(CreateIsometric=lambda doc, type_id: view)
    return view


def create_3d(world, name="V1"):
    arm(world, [_family("ThreeDimensional")])
    only_document(world)
    return call(world, handler_of(world, *CREATE), {"view_type": "3d", "name": name})


def test_a_created_view_is_reported_with_its_id_as_succeeded(world):
    view = tracked_view(world)
    reply = create_3d(world)
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": 1,
                                     "succeeded": [77], "failed": [], "revit_failures": []}
    assert reply.data["view_id"] == 77 and reply.data["view_type"] == "ThreeD"
    assert reply.data["name"] == "V1" and view.Name == "V1"


def test_a_view_that_cannot_take_the_requested_name_is_a_partial(world):
    tracked_view(world, name_error="dup")
    reply = create_3d(world)
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["succeeded"] == [77]
    assert reply.data["outcome"]["failed"] == [{"item": "name", "reason": "dup"}]
    assert reply.data["view_id"] == 77
    assert "error" not in reply.data
    assert reply.data["name"] == "Default", "the reply must name the view Revit actually made"
    assert "V1" in reply.data["message"] and "dup" in reply.data["message"]


def test_no_view_created_at_all_is_a_422_that_names_no_view(world):
    world.db.View3D = types.SimpleNamespace(CreateIsometric=lambda doc, type_id: None)
    reply = create_3d(world)
    assert reply.status == 422 and reply.data["status"] == "failed", reply.data
    assert reply.data["outcome"]["succeeded"] == []
    (entry,) = reply.data["outcome"]["failed"]
    assert entry["item"] == "view" and "3d" in entry["reason"]
    assert "view_id" not in reply.data and "view_type" not in reply.data
    assert reply.data["error"]


def test_a_rolled_back_view_creation_is_a_409_and_the_view_is_never_read_after_the_commit(world):
    tracked_view(world)
    world.commit_status = "RolledBack"
    reply = create_3d(world)
    assert reply.status == 409 and reply.data["status"] == "rolled_back", reply.data
    assert "view_id" not in reply.data and "name" not in reply.data
    assert reply.data["outcome"]["succeeded"] == []
    commit = [i for i, event in enumerate(world.events) if event[0] == "commit"][0]
    assert [e for e in world.events[commit:] if e[0] == "viewread"] == []


def test_a_committed_view_is_not_read_for_its_id_before_the_commit(world):
    tracked_view(world)
    reply = create_3d(world)
    assert reply.status == 200
    commit = [i for i, event in enumerate(world.events) if event[0] == "commit"][0]
    before = [e[2] for e in world.events[:commit] if e[0] == "viewread"]
    assert "Id" not in before and "ViewType" not in before


def test_create_view_refusals_inside_the_transaction_carry_no_outcome(world):
    arm(world, [_family("Section")])
    only_document(world)
    reply = call(world, handler_of(world, *CREATE), {"view_type": "section", "name": "S1"})
    assert reply.status == 400 and "outcome" not in reply.data


# --- set_active_view (D-06: no transaction, null status)


def test_set_active_view_reports_the_switched_view_with_a_null_transaction_status(world):
    arm(world, [_named("Plan A")])
    only_document(world)
    reply = call(world, handler_of(world, *SET_VIEW), MUTATIONS[SET_VIEW])
    assert reply.status == 200
    assert reply.data["outcome"] == {"transaction_status": None, "requested": 1,
                                     "succeeded": ["Plan A"], "failed": [], "revit_failures": []}
    assert world.kinds("transaction") == []


def test_set_active_view_refusals_carry_no_outcome(world):
    arm(world, [_named("Other")])
    only_document(world)
    unknown = call(world, handler_of(world, *SET_VIEW), MUTATIONS[SET_VIEW])
    assert unknown.status == 404 and "outcome" not in unknown.data
    missing = call(world, handler_of(world, *SET_VIEW), {})
    assert missing.status == 400 and "outcome" not in missing.data
    refused = call(world, handler_of(world, *SET_VIEW), MUTATIONS[SET_VIEW], uidoc=None)
    assert refused.status == 412 and "outcome" not in refused.data


def test_set_active_view_that_cannot_switch_is_a_500_that_names_the_view_and_the_reason(world):
    arm(world, [_named("Plan A")])
    only_document(world)

    class RefusingUIDocument(FakeUIDocument):
        @property
        def ActiveView(self):
            return None

        @ActiveView.setter
        def ActiveView(self, view):
            raise RuntimeError("switch refused")

    uidoc = RefusingUIDocument(world, world.uiapp.active._lifetime)
    reply = call(world, handler_of(world, *SET_VIEW), MUTATIONS[SET_VIEW], uidoc=uidoc)
    assert reply.status == 500 and "switch refused" in reply.data["error"]
    assert reply.data["outcome"] == {
        "transaction_status": None, "requested": 1, "succeeded": [],
        "failed": [{"item": "Plan A", "reason": "switch refused"}], "revit_failures": []}


# ====================================================================== open_model


OPEN = ("worksharing", "/open_model/")


@pytest.fixture
def model_file(tmp_path):
    path = tmp_path / "Requested.rvt"
    path.write_bytes(b"rvt")
    return str(path)


def open_model(world, body, **extra):
    return call(world, handler_of(world, *OPEN), body, **extra)


def test_open_model_reports_the_newly_opened_document_not_the_previous_active_one(world, model_file):
    world.open("Alpha", "C:/Models/Alpha.rvt", active=True)
    alpha_token = world.tokens()[0]
    reply = open_model(world, {"file_path": model_file})
    assert reply.status == 200, reply.data
    new_token = world.tokens()[1]
    assert new_token != alpha_token
    assert reply.data["document"] == {"document": new_token, "title": "Gamma",
                                      "path": "C:/Models/Actual.rvt", "active": True,
                                      "saved": True}
    assert reply.data["document"]["document"] != alpha_token
    assert reply.data["document_title"] == "Gamma"
    assert reply.data["process_identity"] == IDENT


def test_open_model_names_what_revit_opened_never_the_requested_path(world, model_file):
    world.open_plan = ("Renamed By Revit", "D:/elsewhere/Other.rvt")
    reply = open_model(world, {"file_path": model_file})
    assert reply.data["document"]["title"] == "Renamed By Revit"
    assert reply.data["document"]["path"] == "D:/elsewhere/Other.rvt"
    assert reply.data["file_path"] == model_file, "the request's own path stays its own field"
    assert model_file not in json.dumps(reply.data["document"])


def test_open_model_without_activation_says_the_new_document_is_not_active(world, model_file):
    world.open("Alpha", "C:/Models/Alpha.rvt", active=True)
    world.tokens()
    reply = open_model(world, {"file_path": model_file, "activate": False})
    assert reply.status == 200 and reply.data["activated"] is False
    assert [call_[0] for call_ in world.open_calls] == ["open"]
    assert reply.data["document"]["title"] == "Gamma"
    assert reply.data["document"]["active"] is False


def test_open_model_is_process_scoped_so_several_open_documents_do_not_refuse_it(world, model_file):
    two_documents(world)
    reply = open_model(world, {"file_path": model_file})
    assert reply.status == 200 and reply.data["document"]["title"] == "Gamma"
    assert world.guard_calls == []


def test_open_model_takes_no_document_selector(world, model_file):
    """A document key is not a selector here: nothing is resolved, nothing is refused."""
    world.open("Alpha", "C:/Models/Alpha.rvt", active=True)
    world.tokens()
    reply = open_model(world, {"file_path": model_file, "document": "doc1.zzzz.9"})
    assert reply.status == 200 and world.guard_calls == []


def test_open_model_opens_no_transaction_and_never_touches_the_injected_document(world, model_file):
    world.open("Alpha", "C:/Models/Alpha.rvt", active=True)
    world.tokens()
    open_model(world, {"file_path": model_file})
    assert world.kinds("transaction") == []
    assert world.events_on("INJECTED") == []


def test_open_model_keeps_its_original_reply_keys_and_adds_only_identity(world, model_file):
    reply = open_model(world, {"file_path": model_file})
    original = ["activated", "audited", "detach", "document_title", "file_path", "is_central",
                "is_local_copy", "is_workshared", "message", "outcome", "requested_detach",
                "saved_in_version", "status", "worksets_total"]
    assert sorted(without_attribution(reply.data)) == original
    assert set(reply.data) - set(original) == {"document", "process_identity"}


def test_open_model_keeps_the_workset_aware_opening_untouched(world, model_file):
    """The workset configuration and detach option are applied BEFORE the open call, so the
    workset-selection dialog never appears (a blocked headless server)."""
    db = world.db
    db.OpenOptions = MagicMock(name="OpenOptions")
    options = db.OpenOptions.return_value
    db.WorksetConfiguration = MagicMock(name="WorksetConfiguration")
    config = db.WorksetConfiguration.return_value
    info = types.SimpleNamespace(Name="Workset1", Id=MagicMock(name="WorksetId"))
    db.WorksharingUtils = types.SimpleNamespace(GetUserWorksetInfo=lambda model_path: [info])
    reply = open_model(world, {"file_path": model_file, "detach": "preserve"})
    assert reply.status == 200, reply.data
    options.SetOpenWorksetsConfiguration.assert_called_once_with(config)
    config.Close.assert_called_once()
    assert options.DetachFromCentralOption == "PRESERVE"
    assert world.open_calls[0][2] is options
    assert reply.data["detach"] == "preserve" and reply.data["is_workshared"] is True
    assert reply.data["worksets_closed"] == ["Workset1"]
    assert reply.data["document"]["title"] == "Gamma"


def test_open_model_open_failure_names_the_process_and_no_document(world, model_file):
    world.open("Alpha", "C:/Models/Alpha.rvt", active=True)
    world.tokens()
    world.open_error = "file is locked"
    reply = open_model(world, {"file_path": model_file})
    assert reply.status == 500 and "file is locked" in reply.data["error"]
    assert reply.data["process_identity"] == IDENT
    assert "document" not in reply.data, "nothing was opened, so no document may be named"


def test_open_model_that_returns_no_document_names_the_process_and_no_document(world, model_file):
    world.open_returns_none = True
    reply = open_model(world, {"file_path": model_file})
    assert reply.status == 500 and "returned no document" in reply.data["error"]
    assert reply.data["process_identity"] == IDENT
    assert "document" not in reply.data


def test_open_model_validation_and_missing_file_replies_name_the_process(world, tmp_path):
    missing = open_model(world, {})
    assert missing.status == 400 and missing.data["process_identity"] == IDENT
    absent = open_model(world, {"file_path": str(tmp_path / "nope.rvt")})
    assert absent.status == 404 and absent.data["process_identity"] == IDENT
    assert world.open_calls == []


def test_open_model_without_process_identity_says_why_and_still_opens(world, model_file, monkeypatch):
    monkeypatch.setattr(identity, "process_identity_or_error",
                        lambda uiapp=None: (None, "no retained RoutesServer"))
    reply = open_model(world, {"file_path": model_file})
    assert reply.status == 200
    assert reply.data["identity_error"] == "no retained RoutesServer"
    assert "process_identity" not in reply.data


def test_open_model_is_honest_when_the_opened_document_cannot_be_given_a_selector(
        world, model_file, monkeypatch):
    class Broken(object):
        def observe(self, documents, active):
            raise RuntimeError("registry unreadable")

        def classify(self, selector):
            return "invalid"

    monkeypatch.setattr(identity, "get_document_registry", lambda store=None: Broken())
    reply = open_model(world, {"file_path": model_file})
    assert reply.status == 200, "the document IS open; the reply must not claim otherwise"
    document = reply.data["document"]
    assert document["document"] is None
    assert document["title"] == "Gamma" and document["path"] == "C:/Models/Actual.rvt"
    assert reply.data["process_identity"] == IDENT


def test_open_model_success_carries_an_outcome_with_a_null_transaction_status(world, model_file):
    reply = open_model(world, {"file_path": model_file})
    assert reply.status == 200, reply.data
    assert reply.data["outcome"] == {"transaction_status": None, "requested": 1,
                                     "succeeded": [model_file], "failed": [], "revit_failures": []}
    assert world.kinds("transaction") == []


def test_open_model_open_failure_names_the_requested_file_and_the_reason_in_the_outcome(
        world, model_file):
    world.open_error = "file is locked"
    reply = open_model(world, {"file_path": model_file})
    assert reply.status == 500 and "document" not in reply.data
    assert reply.data["outcome"] == {
        "transaction_status": None, "requested": 1, "succeeded": [],
        "failed": [{"item": model_file, "reason": "Open failed: file is locked"}],
        "revit_failures": []}


def test_open_model_that_returns_no_document_is_a_failed_item_in_the_outcome(world, model_file):
    world.open_returns_none = True
    reply = open_model(world, {"file_path": model_file})
    assert reply.status == 500 and "document" not in reply.data
    (entry,) = reply.data["outcome"]["failed"]
    assert entry["item"] == model_file and "returned no document" in entry["reason"]
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["transaction_status"] is None


def test_open_model_validation_and_missing_file_replies_carry_no_outcome(world, tmp_path):
    missing = open_model(world, {})
    assert missing.status == 400 and "outcome" not in missing.data
    absent = open_model(world, {"file_path": str(tmp_path / "nope.rvt")})
    assert absent.status == 404 and "outcome" not in absent.data
    bad = open_model(world, {"file_path": str(tmp_path), "detach": "sideways"})
    assert "outcome" not in bad.data


# ------------------------------------------- open_model: local copy by default (261025-ld5)


# The Russian "axes and levels" workset name, written as \u escapes so this file stays ASCII.
AXES = "\u041e\u0441\u0438 \u0438 \u0443\u0440\u043e\u0432\u043d\u0438"
STAMP_MOMENT = datetime.datetime(2026, 10, 25, 9, 5, 3)


def workshared_world(world, names):
    """A fake workshared central: workset names, CreateNewLocal that writes b"new", and a
    ModelPath that is the path itself. Returns (OpenOptions instance, WorksetConfiguration
    instance). Tests that reach the local-copy path must always pass local_path under tmp_path."""
    db = world.db
    db.OpenOptions = MagicMock(name="OpenOptions")
    db.WorksetConfiguration = MagicMock(name="WorksetConfiguration")
    infos = [types.SimpleNamespace(Name=name, Id=MagicMock(name="WorksetId:" + name))
             for name in names]
    world.created_locals = []

    def create_new_local(central, local):
        world.created_locals.append((central, local))
        with open(local, "wb") as handle:
            handle.write(b"new")

    db.WorksharingUtils = types.SimpleNamespace(
        GetUserWorksetInfo=lambda model_path: list(infos), CreateNewLocal=create_new_local)
    db.ModelPathUtils = types.SimpleNamespace(
        ConvertUserVisiblePathToModelPath=lambda path: path)
    world.workset_infos = infos
    return db.OpenOptions.return_value, db.WorksetConfiguration.return_value


def pin_clock(monkeypatch, world):
    handler_of(world, *OPEN)  # loads revit_mcp.worksharing
    module = sys.modules["revit_mcp.worksharing"]
    monkeypatch.setattr(module, "_now", lambda: STAMP_MOMENT)


@pytest.fixture
def local_target(tmp_path):
    return str(tmp_path / "local" / "Requested_u.rvt")


def make_existing_local(tmp_path, with_backup=True):
    folder = tmp_path / "local"
    folder.mkdir()
    (folder / "Requested_u.rvt").write_bytes(b"old")
    if with_backup:
        backup = folder / "Requested_u_backup"
        backup.mkdir()
        (backup / "f.dat").write_bytes(b"x")
    return folder


def test_open_model_defaults_to_a_new_local_copy_of_a_workshared_central(
        world, model_file, local_target):
    options, _ = workshared_world(world, ["Workset1"])
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 200, reply.data
    assert world.created_locals == [(model_file, local_target)]
    assert world.open_calls[0][1] == local_target
    data = reply.data
    assert data["detach"] == "none" and data["requested_detach"] == "none"
    assert data["is_local_copy"] is True and data["local_path"] == local_target
    assert data["existing_local"] == "timestamp"
    assert data["renamed_existing_local"] is None
    assert data["replaced_existing_local"] is False
    assert data["worksets_applied"] == "all_user_closed"
    assert options.DetachFromCentralOption not in ("PRESERVE", "DISCARD")


def test_open_model_explicit_discard_still_detaches_without_a_local_copy(world, model_file):
    options, _ = workshared_world(world, ["Workset1"])
    reply = open_model(world, {"file_path": model_file, "detach": "discard"})
    assert reply.status == 200, reply.data
    assert options.DetachFromCentralOption == "DISCARD"
    assert world.created_locals == [] and reply.data["is_local_copy"] is False
    assert world.open_calls[0][1] == model_file


def test_open_model_renames_an_existing_local_copy_and_its_backup_folder(
        world, model_file, local_target, tmp_path, monkeypatch):
    workshared_world(world, ["Workset1"])
    folder = make_existing_local(tmp_path)
    pin_clock(monkeypatch, world)
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 200, reply.data
    assert (folder / "Requested_u.rvt").read_bytes() == b"new"
    assert (folder / "Requested_u_20261025_090503.rvt").read_bytes() == b"old"
    assert (folder / "Requested_u_20261025_090503_backup" / "f.dat").read_bytes() == b"x"
    assert not (folder / "Requested_u_backup").exists()
    assert reply.data["renamed_existing_local"] == {
        "from": str(folder / "Requested_u.rvt"),
        "to": str(folder / "Requested_u_20261025_090503.rvt"),
        "backup_from": str(folder / "Requested_u_backup"),
        "backup_to": str(folder / "Requested_u_20261025_090503_backup"),
    }
    assert reply.data["replaced_existing_local"] is False


def test_open_model_stamped_name_collision_lands_on_suffix_2(
        world, model_file, local_target, tmp_path, monkeypatch):
    workshared_world(world, ["Workset1"])
    folder = make_existing_local(tmp_path)
    (folder / "Requested_u_20261025_090503.rvt").write_bytes(b"older")
    pin_clock(monkeypatch, world)
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 200, reply.data
    assert (folder / "Requested_u_20261025_090503.rvt").read_bytes() == b"older"
    assert (folder / "Requested_u_20261025_090503_2.rvt").read_bytes() == b"old"
    assert reply.data["renamed_existing_local"]["to"].endswith("_20261025_090503_2.rvt")


def test_open_model_existing_copy_without_a_backup_folder_is_renamed_alone(
        world, model_file, local_target, tmp_path, monkeypatch):
    workshared_world(world, ["Workset1"])
    folder = make_existing_local(tmp_path, with_backup=False)
    pin_clock(monkeypatch, world)
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 200, reply.data
    renamed = reply.data["renamed_existing_local"]
    assert renamed["backup_from"] is None and renamed["backup_to"] is None
    assert (folder / "Requested_u_20261025_090503.rvt").read_bytes() == b"old"


def test_open_model_rename_failure_is_an_error_and_deletes_nothing(
        world, model_file, local_target, tmp_path, monkeypatch):
    workshared_world(world, ["Workset1"])
    folder = make_existing_local(tmp_path)

    def refuse(src, dst):
        raise OSError("used by another process")

    monkeypatch.setattr(os, "rename", refuse)
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 500
    assert local_target in reply.data["error"] and "used by another process" in reply.data["error"]
    assert (folder / "Requested_u.rvt").read_bytes() == b"old"
    assert world.created_locals == [] and world.open_calls == []
    (entry,) = reply.data["outcome"]["failed"]
    assert entry["item"] == model_file


def test_open_model_backup_folder_rename_failure_restores_the_file(
        world, model_file, local_target, tmp_path, monkeypatch):
    workshared_world(world, ["Workset1"])
    folder = make_existing_local(tmp_path)
    real_rename = os.rename

    def only_the_folder_fails(src, dst):
        if str(src).endswith("_backup"):
            raise OSError("folder is locked")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", only_the_folder_fails)
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 500 and "folder is locked" in reply.data["error"]
    assert (folder / "Requested_u.rvt").read_bytes() == b"old", "the .rvt was renamed back"
    assert (folder / "Requested_u_backup" / "f.dat").exists()
    assert world.created_locals == [] and world.open_calls == []


def test_open_model_existing_local_error_refuses_and_touches_nothing(
        world, model_file, local_target, tmp_path):
    workshared_world(world, ["Workset1"])
    folder = make_existing_local(tmp_path)
    reply = open_model(world, {"file_path": model_file, "local_path": local_target,
                               "existing_local": "error"})
    assert reply.status == 500 and "already exists" in reply.data["error"]
    assert (folder / "Requested_u.rvt").read_bytes() == b"old"
    assert (folder / "Requested_u_backup" / "f.dat").exists()
    assert world.created_locals == [] and world.open_calls == []


@pytest.mark.parametrize("extra", [{"existing_local": "overwrite"}, {"overwrite_local": True}])
def test_open_model_explicit_overwrite_replaces_the_copy(
        world, model_file, local_target, tmp_path, extra):
    workshared_world(world, ["Workset1"])
    folder = make_existing_local(tmp_path)
    body = {"file_path": model_file, "local_path": local_target}
    body.update(extra)
    reply = open_model(world, body)
    assert reply.status == 200, reply.data
    assert (folder / "Requested_u.rvt").read_bytes() == b"new"
    assert reply.data["replaced_existing_local"] is True
    assert reply.data["renamed_existing_local"] is None
    assert [p.name for p in folder.iterdir() if p.name.startswith("Requested_u_2")] == []


def test_open_model_legacy_overwrite_local_false_behaves_as_error(
        world, model_file, local_target, tmp_path):
    workshared_world(world, ["Workset1"])
    folder = make_existing_local(tmp_path)
    reply = open_model(world, {"file_path": model_file, "local_path": local_target,
                               "overwrite_local": False})
    assert reply.status == 500 and "already exists" in reply.data["error"]
    assert (folder / "Requested_u.rvt").read_bytes() == b"old"


@pytest.mark.parametrize("extra", [
    {"existing_local": "bogus"},
    {"existing_local": "timestamp", "overwrite_local": True},
])
def test_open_model_invalid_or_conflicting_existing_local_is_a_400_without_outcome(
        world, model_file, local_target, tmp_path, extra):
    workshared_world(world, ["Workset1"])
    folder = make_existing_local(tmp_path)
    body = {"file_path": model_file, "local_path": local_target}
    body.update(extra)
    reply = open_model(world, body)
    assert reply.status == 400 and "outcome" not in reply.data
    assert world.open_calls == [] and world.created_locals == []
    assert (folder / "Requested_u.rvt").read_bytes() == b"old"


def test_open_model_retries_once_with_the_axes_and_levels_workset(
        world, model_file, local_target):
    options, config = workshared_world(world, ["Workset1", "02_" + AXES, "Links"])
    world.open_errors = ["boom", None]
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 200, reply.data
    assert [c[1] for c in world.open_calls] == [local_target, local_target]
    assert len(world.created_locals) == 1
    data = reply.data
    assert data["worksets_applied"] == "axes_and_levels_open"
    assert data["fallback_workset"] == "02_" + AXES
    assert "boom" in data["fallback_reason"]
    assert data["worksets_opened"] == ["02_" + AXES]
    assert options.SetOpenWorksetsConfiguration.call_count == 2
    assert config.Close.call_count == 2


def test_open_model_retry_also_fires_when_the_first_open_returns_no_document(
        world, model_file, local_target):
    workshared_world(world, ["Workset1", AXES])
    world.open_returns_none = True
    original = world.uiapp.OpenAndActivateDocument

    def second_attempt_succeeds(path, options, flag):
        result = original(path, options, flag)
        world.open_returns_none = False
        return result

    world.uiapp.OpenAndActivateDocument = second_attempt_succeeds
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 200, reply.data
    assert reply.data["worksets_applied"] == "axes_and_levels_open"
    assert "returned no document" in reply.data["fallback_reason"]


def test_open_model_retry_without_a_matching_workset_is_an_error_after_one_open(
        world, model_file, local_target):
    workshared_world(world, ["Workset1", "Links"])
    world.open_errors = ["boom"]
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 500
    assert "boom" in reply.data["error"] and "No user workset" in reply.data["error"]
    assert len(world.open_calls) == 1 and "outcome" in reply.data


def test_open_model_failed_retry_reports_both_reasons(world, model_file, local_target):
    workshared_world(world, ["Workset1", AXES])
    world.open_errors = ["first problem", "second problem"]
    reply = open_model(world, {"file_path": model_file, "local_path": local_target})
    assert reply.status == 500
    assert "first problem" in reply.data["error"] and "second problem" in reply.data["error"]
    assert reply.data["fallback_workset"] == AXES
    assert len(world.open_calls) == 2


@pytest.mark.parametrize("patterns", [["__ALL_USER_WORKSETS__"], ["#_RVT_LINK"]])
def test_open_model_explicit_patterns_are_never_retried(
        world, model_file, local_target, patterns):
    workshared_world(world, ["Workset1", AXES])
    world.open_error = "boom"
    reply = open_model(world, {"file_path": model_file, "local_path": local_target,
                               "close_worksets_matching": patterns})
    assert reply.status == 500 and "boom" in reply.data["error"]
    assert len(world.open_calls) == 1


def test_open_model_explicit_patterns_report_caller_patterns(world, model_file, local_target):
    workshared_world(world, ["Workset1", "Links"])
    reply = open_model(world, {"file_path": model_file, "local_path": local_target,
                               "close_worksets_matching": ["Links"]})
    assert reply.status == 200, reply.data
    assert reply.data["worksets_applied"] == "caller_patterns"


def test_open_model_source_still_configures_worksets_and_never_reads_host_app():
    source = (REPO / "revit_mcp" / "worksharing.py").read_text(encoding="utf-8")
    assert "SetOpenWorksetsConfiguration" in source and "DetachFromCentralOption" in source
    assert "HOST_APP" not in source


# ================================================================ /execute_code/ (D-15)


EXEC = ("code_execution", "/execute_code/")
CODE = {"code": "print('hello')", "description": "greet"}
# Keys that would attribute a document the code changed. None may ever appear (D-15).
ATTRIBUTING = ("document", "documents", "changed_documents", "affected_document", "title", "path",
               "candidates", "active_document", "document_title")


def run_code(world, body=CODE, **extra):
    return call(world, handler_of(world, *EXEC), body, **extra)


def scope_of(world):
    module = importlib.import_module("revit_mcp.code_execution")
    return module.DOCUMENT_SCOPE_NOTICE


def assert_exception_labelled(world, reply):
    assert reply.data["document_scope"] == scope_of(world)
    assert reply.data["process_identity"] == IDENT
    for key in ATTRIBUTING:
        assert key not in reply.data, "a changed-document attribution key leaked: " + key


def test_execute_code_stays_registered_and_takes_no_selector_guard_or_412(world):
    assert (EXEC[1], "POST") in load(world, "code_execution")
    source = (REPO / "revit_mcp" / "code_execution.py").read_text(encoding="utf-8")
    for name in ("mutation_document_or_response", "decide_mutation_document", "resolve_document",
                 "request_document_selector"):
        assert name not in source, "/execute_code/ must stay outside the document guard (D-15)"


def test_execute_code_runs_when_two_documents_are_open_and_no_selector_is_given(world):
    two_documents(world)
    reply = run_code(world)
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert "hello" in reply.data["output"]
    assert world.guard_calls == []
    assert [event[1] for event in world.kinds("transaction")] == ["INJECTED"]
    assert_exception_labelled(world, reply)


def test_execute_code_still_hands_the_code_the_injected_doc(world):
    world.open("Alpha", "C:/Models/Alpha.rvt", active=True)
    reply = run_code(world, {"code": "print(doc.label)", "description": "who"})
    assert reply.status == 200 and "INJECTED" in reply.data["output"]


def test_execute_code_succeeds_with_the_exception_notice_and_no_attribution(world):
    world.open("Only", ONLY_PATH, active=True)
    reply = run_code(world)
    assert reply.status == 200
    assert_exception_labelled(world, reply)
    assert set(reply.data) == {"status", "description", "output", "code_executed",
                               "transaction_status", "outcome", "document_scope",
                               "process_identity"}


def test_execute_code_error_reply_carries_the_notice_and_no_attribution(world):
    world.open("Only", ONLY_PATH, active=True)
    reply = run_code(world, {"code": "raise ValueError('boom')", "description": "bad"})
    assert reply.status == 500 and reply.data["status"] == "error"
    assert "boom" in reply.data["error"]
    assert world.kinds("rollback")
    assert_exception_labelled(world, reply)


def test_execute_code_rollback_stays_a_409_error_and_carries_the_notice(world):
    world.open("Only", ONLY_PATH, active=True)
    world.commit_status = "RolledBack"
    reply = run_code(world)
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert "No changes were saved" in reply.data["message"]
    assert reply.data["transaction_status"] == "RolledBack"
    assert_exception_labelled(world, reply)


def test_execute_code_success_carries_an_outcome_with_the_real_transaction_status(world):
    world.open("Only", ONLY_PATH, active=True)
    reply = run_code(world)
    assert reply.status == 200
    assert reply.data["outcome"] == {"transaction_status": "Committed", "requested": None,
                                     "succeeded": [], "failed": [], "revit_failures": []}


def test_execute_code_rollback_outcome_says_rolled_back_and_keeps_its_409_body(world):
    world.open("Only", ONLY_PATH, active=True)
    world.commit_status = "RolledBack"
    reply = run_code(world)
    assert reply.status == 409
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["requested"] is None
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["failed"] == []
    assert reply.data["outcome"]["revit_failures"] == reply.data["failures"]
    assert reply.data["code_executed"] == CODE["code"]


def test_execute_code_error_outcome_carries_the_status_after_the_rollback(world):
    world.open("Only", ONLY_PATH, active=True)
    reply = run_code(world, {"code": "raise ValueError('boom')", "description": "bad"})
    assert reply.status == 500 and reply.data["status"] == "error"
    assert reply.data["outcome"] == {"transaction_status": "RolledBack", "requested": None,
                                     "succeeded": [], "failed": [], "revit_failures": []}


def test_execute_code_outcome_never_carries_the_code_the_output_or_the_traceback(world):
    world.open("Only", ONLY_PATH, active=True)
    for body in ({"code": "print('secret-output')", "description": "d"},
                 {"code": "raise ValueError('secret-boom')", "description": "d"}):
        reply = run_code(world, body)
        rendered = json.dumps(reply.data["outcome"])
        assert "secret" not in rendered and "print(" not in rendered and "Traceback" not in rendered


def test_execute_code_early_errors_carry_no_outcome(world):
    world.open("Only", ONLY_PATH, active=True)
    empty = run_code(world, {"code": "", "description": "none"})
    assert empty.status == 400 and "outcome" not in empty.data
    # A body that is not JSON carries no envelope: the gate answers 401 before the route's own
    # parse ever runs (Phase 5, D-01), and that refusal has no outcome either.
    bad = run_code(world, request=types.SimpleNamespace(data=b"{not json", path=EXEC[1]))
    assert bad.status == 401 and "outcome" not in bad.data


def test_execute_code_early_error_replies_carry_the_notice_too(world):
    world.open("Only", ONLY_PATH, active=True)
    empty = run_code(world, {"code": "", "description": "none"})
    assert empty.status == 400 and empty.data["error"] == "No code provided"
    assert_exception_labelled(world, empty)

    sys.modules["pyrevit"].revit.doc = None
    no_doc = run_code(world, CODE, doc=None)
    assert no_doc.status == 503 and no_doc.data["error"] == "No active Revit document"
    assert_exception_labelled(world, no_doc)
    assert world.kinds("transaction") == []


def test_execute_code_unparseable_body_is_a_non_raising_500_with_the_notice(world, monkeypatch):
    """With a valid envelope the gate passes, so the route's own parse failure is still a
    non-raising 500 that carries the notice. A non-JSON body never gets this far (401)."""
    world.open("Only", ONLY_PATH, active=True)
    module = importlib.import_module("revit_mcp.code_execution")

    def broken_parse(raw):
        raise ValueError("body could not be parsed")

    monkeypatch.setattr(module, "parse_request_data", broken_parse)
    reply = run_code(world)
    assert reply.status == 500 and reply.data["error"]
    assert_exception_labelled(world, reply)


def test_execute_code_non_json_body_is_a_gate_401_with_zero_side_effects(world):
    world.open("Only", ONLY_PATH, active=True)
    del world.events[:]
    reply = run_code(world, request=types.SimpleNamespace(data=b"{not json", path=EXEC[1]))
    assert reply.status == 401 and reply.data["auth"] == "missing"
    assert world.events == []
    assert "document_scope" not in reply.data and "process_identity" not in reply.data


def test_execute_code_without_process_identity_says_why_and_still_executes(world, monkeypatch):
    monkeypatch.setattr(identity, "process_identity_or_error",
                        lambda uiapp=None: (None, "no retained RoutesServer"))
    world.open("Only", ONLY_PATH, active=True)
    reply = run_code(world)
    assert reply.status == 200
    assert reply.data["identity_error"] == "no retained RoutesServer"
    assert reply.data["document_scope"] == scope_of(world)
    assert "process_identity" not in reply.data


def test_the_document_scope_notice_states_the_exception_honestly(world):
    notice = scope_of(world)
    for statement in ("trusted arbitrary-code exception",
                      "No document guard or confinement applies",
                      "starting context",
                      "could read and change any open document",
                      "not identified or attributed in this reply",
                      "process_identity"):
        assert statement in notice, statement


def test_execute_code_keeps_stdout_capture_and_the_pre_commit_semantics(world):
    world.open("Only", ONLY_PATH, active=True)
    reply = run_code(world, {"code": "print('a', 1)", "description": "two args"})
    assert reply.data["output"] == "a 1\n"
    assert reply.data["code_executed"] == "print('a', 1)"
    assert reply.data["description"] == "two args"
    start = [i for i, event in enumerate(world.events) if event[0] == "start"][0]
    assert world.events[start + 1][:3] == ("txattr", "INJECTED", "GetFailureHandlingOptions")


# ============================================================ execute_revit_code (tool)


class FakeMCP(object):
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


class RecordingTransport(object):
    def __init__(self):
        self.calls = []

    async def post(self, endpoint, data, ctx=None, **options):
        self.calls.append({"endpoint": endpoint, "data": data, "options": options})
        return {"status": "success", "output": "ok"}


def execute_tool(transport=None):
    module = importlib.import_module("tools.code_execution_tools")
    mcp = FakeMCP()
    transport = transport or RecordingTransport()

    async def unused(*args, **kwargs):
        raise AssertionError("execute_revit_code must only POST")

    module.register_code_execution_tools(mcp, unused, transport.post)
    return mcp.tools["execute_revit_code"], transport


def test_execute_revit_code_is_registered_and_its_manifest_entry_is_unchanged():
    fn, _ = execute_tool()
    manifest = (REPO / "tests" / "unit" / "tool_manifest.txt").read_text(encoding="utf-8").split()
    assert manifest.count("execute_revit_code") == 1
    assert fn.__name__ == "execute_revit_code"


def test_execute_revit_code_has_a_target_and_no_document_parameter():
    fn, _ = execute_tool()
    assert list(inspect.signature(fn).parameters) == ["code", "description", "target", "ctx"]
    parameters = inspect.signature(fn).parameters
    assert parameters["target"].default is None and parameters["ctx"].default is None
    assert parameters["description"].default == "Code execution"


def test_execute_revit_code_forwards_target_and_sends_no_document_field():
    fn, transport = execute_tool()
    out = asyncio.run(fn("print(1)", "one", target="revit1:abc"))
    assert "ok" in out
    (sent,) = transport.calls
    assert sent["endpoint"] == "/execute_code/"
    assert sent["options"] == {"target": "revit1:abc"}
    assert sent["data"] == {"code": "print(1)", "description": "one"}
    assert "document" not in sent["data"]


def test_execute_revit_code_without_a_target_sends_none_so_the_only_process_is_used():
    fn, transport = execute_tool()
    asyncio.run(fn("print(1)"))
    (sent,) = transport.calls
    assert sent["options"] == {}
    assert sent["data"] == {"code": "print(1)", "description": "Code execution"}


def test_execute_revit_code_docstring_states_the_trusted_exception():
    fn, _ = execute_tool()
    doc = " ".join(fn.__doc__.split())
    for statement in (
        "trusted arbitrary-code exception",
        "starting context",
        "can reach and change other open documents",
        "not identified or attributed in the reply",
        "target selects which Revit process runs the code and nothing more",
        "not authentication",
        "no document guard",
        "Args:",
        "code:",
        "description:",
        "target:",
        "ctx:",
    ):
        assert statement in doc, statement


def test_execute_revit_code_goes_through_the_real_bridge_preflight_and_lock(monkeypatch):
    """The tool's target reaches bridge.revit_post: an unprovable incarnation is refused
    before any HTTP is sent (listener preflight), exactly like every other selected call."""
    import base64

    import bridge

    selector = "revit1:" + base64.urlsafe_b64encode(json.dumps(
        {"host": "127.0.0.1", "port": 48885, "pid": 1234,
         "session_token": "11111111-1111-4111-8111-111111111111"},
        separators=(",", ":")).encode()).decode().rstrip("=")
    sent = []
    original = httpx.AsyncClient
    monkeypatch.setattr(bridge, "_selected_client", lambda target: original(
        base_url="http://127.0.0.1:48885/genpro_revit_mcp/",
        transport=httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(200, json={}))))
    monkeypatch.setattr(bridge, "listener_snapshot", lambda ports, **kwargs: None)
    module = importlib.import_module("tools.code_execution_tools")
    mcp = FakeMCP()
    module.register_code_execution_tools(mcp, bridge.revit_get, bridge.revit_post)
    out = asyncio.run(mcp.tools["execute_revit_code"]("print(1)", "one", target=selector))
    assert out.startswith("Error") and "not sent" in out.lower()
    assert sent == []


# ------------------------------------------------------- the Phase 5 gate (D-01, D-03, D-04)
#
# transform_elements, create_view, set_active_view, open_model and execute_code open with
# revit_mcp.security.gate_or_response, before the document guard (where there is one), before
# _stamp_process / _stamp_exception and before any Revit read. The world has one open document,
# so a call that slipped past the gate would visibly reach the guard, a transaction, an Open*
# call or a view switch. /model_worksets/ is an open read: it strips the envelope and never
# refuses (SEC-05).

WRONG_SECRET = "wrong-secret-0123456789-abcdefXYZ-nope"

GATE_BODIES = {
    ("code_execution", "/execute_code/"): {"code": "result = 1"},
    ("worksharing", "/open_model/"): {"file_path": "C:/Models/Scratch.rvt"},
}
GATE_KEYS = list(MUTATIONS) + sorted(PROCESS_LEVEL)
GATE_IDS = ["{}:{}".format(module, route) for module, route in GATE_KEYS]


def _gate_body(key):
    return MUTATIONS[key] if key in MUTATIONS else GATE_BODIES[key]


def _mismatch_naming(*files):
    return {"state": trust.INTEGRITY_MISMATCH, "reason": None,
            "modified": sorted(files), "missing": [], "unexpected": []}


def _refused(world, key, request, status):
    world.open("Only", ONLY_PATH, active=True)
    world.tokens()
    del world.events[:]
    reply = call(world, handler_of(world, *key), request=request)
    assert reply.status == status
    assert "outcome" not in reply.data
    assert world.events == [], "no collector, document attribute, view switch or transaction"
    assert world.transactions == []
    assert world.open_calls == [], "no OpenDocumentFile or OpenAndActivateDocument call"
    assert world.guard_calls == []
    assert "document_scope" not in reply.data, "a refusal reads nothing from Revit (Pitfall 12)"
    assert "process_identity" not in reply.data
    assert "identity_error" not in reply.data
    text = repr(reply.data)
    assert TEST_SECRET not in text and WRONG_SECRET not in text
    return reply


@pytest.mark.parametrize("key", GATE_KEYS, ids=GATE_IDS)
def test_without_the_shared_secret_the_route_is_401_before_any_side_effect(world, key):
    request = types.SimpleNamespace(data=enveloped_body(_gate_body(key), secret=None, route=key[1]), path=key[1])
    reply = _refused(world, key, request, 401)
    assert reply.data["auth"] == "missing"


@pytest.mark.parametrize("key", GATE_KEYS, ids=GATE_IDS)
def test_with_a_wrong_secret_the_route_is_401_before_any_side_effect(world, key):
    request = types.SimpleNamespace(data=enveloped_body(_gate_body(key), secret=WRONG_SECRET, route=key[1]), path=key[1])
    reply = _refused(world, key, request, 401)
    assert reply.data["auth"] == "mismatch"


@pytest.mark.parametrize("key", GATE_KEYS, ids=GATE_IDS)
def test_with_an_integrity_mismatch_the_route_is_423_before_any_side_effect(
        world, monkeypatch, key):
    configure_gate(monkeypatch, integrity=_mismatch_naming("revit_mcp/detail.py"))
    request = types.SimpleNamespace(data=enveloped_body(_gate_body(key), route=key[1]), path=key[1])
    reply = _refused(world, key, request, 423)
    assert reply.data["files"] == ["revit_mcp/detail.py"]


def test_a_refused_execute_code_never_compiles_or_runs_the_submitted_code(world):
    world.open("Only", ONLY_PATH, active=True)
    probe = types.ModuleType("_gate_probe")
    probe.ran = False
    sys.modules["_gate_probe"] = probe
    try:
        body = {"code": "import sys; sys.modules['_gate_probe'].ran = True"}
        request = types.SimpleNamespace(data=enveloped_body(body, secret=None, route=EXEC[1]), path=EXEC[1])
        reply = run_code(world, request=request)
        assert reply.status == 401
        assert probe.ran is False, "the submitted code ran for a caller without a secret"
    finally:
        sys.modules.pop("_gate_probe", None)


MODEL_WORKSETS = ("worksharing", "/model_worksets/")


@pytest.mark.parametrize("variant", ["none", "wrong", "valid", "mismatch"])
def test_model_worksets_needs_no_secret_and_never_sees_the_envelope(world, monkeypatch, variant):
    body = {"file_path": "C:/Models/Missing.rvt"}
    fn = handler_of(world, *MODEL_WORKSETS, method="POST")
    bare = call(world, fn, request=types.SimpleNamespace(
        data=json.dumps(body).encode("utf-8"), path=MODEL_WORKSETS[1]))
    assert bare.status == 404
    if variant == "mismatch":
        configure_gate(monkeypatch, integrity=_mismatch_naming("revit_mcp/detail.py"))
    secret = {"none": None, "wrong": WRONG_SECRET}.get(variant, TEST_SECRET)
    request = types.SimpleNamespace(data=enveloped_body(body, secret=secret, route=MODEL_WORKSETS[1]), path=MODEL_WORKSETS[1])
    reply = call(world, fn, request=request)
    assert reply.status == bare.status
    assert reply.data == bare.data
    assert "_mcp" not in json.loads(request.data.decode("utf-8"))
    assert world.guard_calls == []
