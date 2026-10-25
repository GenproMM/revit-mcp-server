# -*- coding: utf-8 -*-
"""Explicit per-handler document guard on the mutating routes of analysis, annotation,
building, colors and detail (plan 02-12; D-05, D-08, D-09, D-10, G1 explicit-route-only).

Offline evidence only. The real route modules are imported against a fake pyRevit and
registered through their real register_*_routes functions with a fake api, so a handler
that forgets to call revit_mcp.identity.mutation_document_or_response fails here: every
fixture row drives the handler the way pyRevit would (injected uiapp, doc, request by
name) and observes every document, collector and transaction the handler touched.

What this proves: the guard runs first, refuses before any side effect, runs the work on
the document the guard resolved (never the injected ``doc``), and stamps the document
descriptor and process identity on every reply the handler produced. What it does not
prove: how pyRevit dispatches these handlers, or how a real Document answers -- that is a
live recheck after a full Revit restart (02-18). Nothing here touches Revit.
"""

import asyncio
import importlib
import inspect
import itertools
import json
import sys
import types
from unittest.mock import MagicMock

import httpx
import pytest

import bridge
from gate_support import TEST_ROUTE, TEST_SECRET, configure_gate, enveloped_body, request_of
from revit_mcp import identity, trust
from revit_mcp.textutils import classify_outcome
from tools.utils import format_response

IDENT = {"pid": 4242, "actual_port": 48885, "session_token": "tok-abc", "revit_version": "2024"}

# --------------------------------------------------------------- the classification
#
# Hand classification of every route in the five owned registrars. A route that is not
# listed here fails test_every_registered_route_is_classified, so a new route cannot
# slip in unguarded or be mislabelled silently. Reads that travel as POST stay reads.

REGISTRARS = {
    "analysis": "register_analysis_routes",
    "annotation": "register_annotation_routes",
    "building": "register_building_routes",
    "clash": "register_clash_routes",
    "colors": "register_color_routes",
    "detail": "register_detail_routes",
}

# (module, route) -> a body that gets past early validation and touches the document.
MUTATIONS = {
    ("annotation", "/create_dimensions/"): {"element_ids": [1, 2]},
    ("annotation", "/tag_walls/"): {},
    ("building", "/create_line/"): {"elements": [{"element_type": "wall"}]},
    ("building", "/create_surface/"): {"elements": [{"element_type": "floor"}]},
    ("building", "/create_level/"): {"levels": [{"elevation": 3000, "name": "L1"}]},
    ("colors", "/color_splash/"): {"category_name": "Walls", "parameter_name": "Mark"},
    ("colors", "/clear_colors/"): {"category_name": "Walls"},
    ("detail", "/create_detail_line/"): {"start_point": {"x": 0, "y": 0, "z": 0},
                                         "end_point": {"x": 1000, "y": 0, "z": 0}},
}

# (module, route, method): no document selector, the active document of the process.
READS = {
    ("analysis", "/ai_filter/", "POST"): {},
    ("analysis", "/room_data/", "GET"): None,
    ("analysis", "/material_quantities/", "POST"): {},
    ("analysis", "/model_statistics/", "GET"): None,
    ("colors", "/list_category_parameters/", "POST"): {"category_name": "Walls"},
}

# Phase 5 (05-02): clash.py is one more registrar of this suite. Its single route is an
# open POST read: no document selector, never gated, only the envelope is stripped.
CLASH_READS = {
    ("clash", "/clash_check/", "POST"): {},
}

# The four POST reads of the suite (they carry the envelope but are never refused).
POST_READS = dict((key, body) for key, body in READS.items() if key[2] == "POST")
POST_READS.update(CLASH_READS)
POST_READ_IDS = ["{}:{}".format(key[0], key[1]) for key in POST_READS]

MUTATION_IDS = ["{}:{}".format(module, route) for module, route in MUTATIONS]


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


class RouteDocument(object):
    """A wrapper over one open lifetime. Anything the guard does not read is recorded
    as a touch (and raises when the world is set to explode), so a handler that works
    on the wrong document or before the guard is visible in ``world.events``."""

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
        # A document attribute that must answer a configured object (doc.Create), then a
        # method a test wants to behave, keyed by (label or None, name).
        if name in self._world.attr_overrides:
            return self._world.attr_overrides[name]
        hook = self._world.hooks.get((self.label, name)) or self._world.hooks.get((None, name))
        if hook is not None:
            return lambda *args, **kwargs: hook(self, *args, **kwargs)
        return MagicMock(name=name)


class InjectedDocument(object):
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

    def __init__(self):
        self.events = []
        self.explode = False
        self.hooks = {}
        self.attr_overrides = {}
        self.transactions = []
        self.collector_items = []
        # (category object, "types" | "instances" | None) -> collector factories; a query
        # not listed here answers collector_items.
        self.results = {}
        self.create_methods = {}
        self.elements = {}
        self.refless = set()
        self.commit_status = "Committed"
        self.break_start = set()
        # element id -> exception the active view raises from SetElementOverrides; ids it
        # accepted are appended to overridden (the colour routes).
        self.override_failures = {}
        self.overridden = []
        self.db = None
        self.app = RouteApplication(self)
        self.uiapp = RouteUIApp(self, self.app)
        self.injected = InjectedDocument(self)
        self.registry = identity.DocumentRegistry()

    def record(self, kind, doc, detail=None):
        label = getattr(doc, "label", "?") if isinstance(
            doc, (RouteDocument, InjectedDocument)) else "?"
        self.events.append((kind, label, detail))

    def events_on(self, label):
        return [event for event in self.events if event[1] == label]

    def kinds(self, kind):
        return [event for event in self.events if event[0] == kind]

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


class _NetList(list):
    """System.Collections.Generic.List: a list with .NET's Add."""

    def Add(self, item):
        self.append(item)


class _Elements(list):
    """What ToElements answers: a list that also has the .NET collection's Count."""

    @property
    def Count(self):
        return len(self)


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
            # A real method, not __getattr__, so no event is recorded.
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
            return MagicMock(name=name)

    class FilteredElementCollector(object):
        def __init__(self, doc, *args):
            world.record("collector", doc)
            if world.explode:
                raise RuntimeError("collector could not be created")
            self._category = None
            self._kind = None

        def _items(self):
            factories = world.results.get((self._category, self._kind), world.collector_items)
            return [make(world) for make in factories]

        def _narrow(self, **fields):
            for key, value in fields.items():
                setattr(self, key, value)
            return self

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            if name == "ToElements":
                return lambda: _Elements(self._items())
            if name == "OfCategory":
                return lambda category: self._narrow(_category=category)
            if name == "OfClass":
                return lambda cls: self._narrow(_kind="types")
            if name == "WhereElementIsNotElementType":
                return lambda: self._narrow(_kind="instances")
            return lambda *args, **kwargs: self

        def __iter__(self):
            return iter(self._items())

        def __len__(self):
            return len(self._items())

        def __getitem__(self, index):
            return self._items()[index]

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
    # Assigned once, so what a route compares against is the same object on every access
    # (a fresh _DB.__getattr__ mock per access would never equal the Commit result).
    db.TransactionStatus = types.SimpleNamespace(Committed="Committed", RolledBack="RolledBack")
    db.BuiltInCategory = MagicMock(name="DB.BuiltInCategory")
    return db


class HostAppTrap(object):
    """pyRevit's process-global HOST_APP. A handler must use the injected uiapp."""

    def __getattr__(self, name):
        raise AssertionError("HOST_APP." + name + " was read; use the injected uiapp")


ROUTE_MODULES = ("utils", "analysis", "annotation", "building", "clash", "colors", "detail")


@pytest.fixture
def world(monkeypatch):
    """A fake Revit process with the route modules imported against a fake pyRevit.

    ``world.guard_calls`` counts calls of the production guard (it still runs for real),
    so a read that gained a guard, or a mutation that lost its call, is visible.
    """
    w = World()
    w.guard_calls = []
    # Phase 5: the Revit-side gate state is configured and every request carries the
    # envelope, exactly as production delivers it once the bridge envelopes every POST.
    configure_gate(monkeypatch)
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
    generic.List = _NetList
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
    available = {"uiapp": world.uiapp, "doc": world.injected, "request": request}
    parameters = inspect.signature(fn).parameters
    return fn(**dict((name, available[name]) for name in parameters))


def two_documents(world, active="beta"):
    alpha = world.open("Alpha", "C:/Models/Alpha.rvt")
    beta = world.open(u"\u0411\u0435\u0442\u0430", "")
    world.activate(beta if active == "beta" else alpha)
    return alpha, beta, world.tokens()


ATTRIBUTION_KEYS = ("document", "process_identity")


def without_attribution(data):
    return dict((key, value) for key, value in data.items() if key not in ATTRIBUTION_KEYS)


# --------------------------------------------------- arming the world for real successes
#
# Plan 04-03: a migrated route commits through commit_and_report, which compares the
# Commit() result with DB.TransactionStatus.Committed, and builds an outcome from what
# the fake Revit created. The MUTATIONS bodies above stay minimal (they only prove the
# guard); the rows below reach a real success.


class XYZ(object):
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z

    def DistanceTo(self, other):
        return ((self.X - other.X) ** 2 + (self.Y - other.Y) ** 2 + (self.Z - other.Z) ** 2) ** 0.5


class _Item(object):
    """A collector result: a named element with the few members the routes read."""

    def __init__(self, world, name="Item", elevation=0.0):
        self.world = world
        self.Name = name
        self.Id = types.SimpleNamespace(Value=11)
        self.Elevation = elevation
        self.IsActive = True
        self.IsTemplate = False
        self.Category = None

    def Activate(self):
        pass


def _named(name, **kwargs):
    return lambda world: _Item(world, name, **kwargs)


class Created(object):
    """An element a fake Create call answers."""

    def __init__(self, ident, name_raises=None):
        self.Id = types.SimpleNamespace(Value=ident)
        self._name = "Created {}".format(ident)
        self._name_raises = name_raises

    @property
    def Name(self):
        return self._name

    @Name.setter
    def Name(self, value):
        if self._name_raises is not None:
            raise self._name_raises
        self._name = value


_WALL = {"element_type": "wall", "start_point": {"x": 0, "y": 0}, "end_point": {"x": 1000, "y": 0}}
_FLOOR = {"element_type": "floor",
          "boundary": [{"x": 0, "y": 0}, {"x": 1000, "y": 0}, {"x": 1000, "y": 1000}]}



def override_create(world, **methods):
    """Make ``doc.Create`` answer a configured object; methods accumulate across calls."""
    world.create_methods.update(methods)
    create = MagicMock(name="Create")
    for name, fn in world.create_methods.items():
        getattr(create, name).side_effect = fn
    world.attr_overrides["Create"] = create
    return create


class FakeCurve(object):
    def __init__(self, x):
        self.x = x

    def Evaluate(self, parameter, normalized):
        return XYZ(self.x, 0.0, 0.0)


class FakeWall(object):
    """An element GetElement or a collector answers for the annotation routes: a wall
    with a location curve and, unless told otherwise, a geometry reference."""

    def __init__(self, ident, x=0.0, located=True, reference=True):
        self.Id = types.SimpleNamespace(Value=ident)
        self.Category = None
        self.Location = types.SimpleNamespace(Curve=FakeCurve(x)) if located else None
        self._reference = reference

    def GetReferenceByName(self, name):
        return types.SimpleNamespace(tag="reference") if self._reference else None

    def get_Geometry(self, options):
        return []


def _wall(ident, **kwargs):
    return lambda world: FakeWall(ident, **kwargs)


def _tag(target):
    """An existing wall tag that points at the wall with id ``target``."""
    return lambda world: types.SimpleNamespace(
        Id=types.SimpleNamespace(Value=700 + target),
        TaggedLocalElementId=types.SimpleNamespace(Value=target))


class FakeView(object):
    Id = types.SimpleNamespace(Value=5)
    Name = "Plan A"
    IsTemplate = False
    ViewType = "FloorPlan"

    def __init__(self, world=None):
        self._world = world

    def SetElementOverrides(self, element_id, settings):
        failure = self._world.override_failures.get(element_id.Value) if self._world else None
        if failure is not None:
            raise failure
        if self._world is not None:
            self._world.overridden.append(element_id.Value)


class _RefArray(object):
    def __init__(self):
        self.items = []

    def Append(self, ref):
        self.items.append(ref)

    @property
    def Size(self):
        return len(self.items)


class DimensionCreated(Created):
    ValueString = "1000 mm"


class DetailCurve(Created):
    """A created detail curve whose LineStyle assignment can be made to fail."""

    def __init__(self, ident, style_raises=None):
        Created.__init__(self, ident)
        self._style_raises = style_raises
        self.style = None

    def GetLineStyleIds(self):
        return []

    @property
    def LineStyle(self):
        return self.style

    @LineStyle.setter
    def LineStyle(self, value):
        if self._style_raises is not None:
            raise self._style_raises
        self.style = value


class _SubCategory(object):
    def __init__(self, name):
        self.Name = name

    def GetGraphicsStyle(self, kind):
        return types.SimpleNamespace(Id=types.SimpleNamespace(Value=7001))


class _Categories(object):
    """doc.Settings.Categories: get_Item answers the Lines category; iterating yields the
    model categories the colour routes look up by name."""

    def __init__(self, line_category):
        self._line_category = line_category
        self._walls = types.SimpleNamespace(Name="Walls", Id=types.SimpleNamespace(Value=-2000011))

    def get_Item(self, category):
        return self._line_category

    def __iter__(self):
        return iter([self._walls])


def line_styles(world, *names):
    """doc.Settings.Categories answers an Lines category with the given sub-categories."""
    line_category = types.SimpleNamespace(SubCategories=[_SubCategory(n) for n in names])
    world.attr_overrides["Settings"] = types.SimpleNamespace(
        Categories=_Categories(line_category))


class ColourElement(object):
    """A wall the colour routes can group by its Mark parameter."""

    def __init__(self, ident, mark):
        self.Id = types.SimpleNamespace(Value=ident)
        param = types.SimpleNamespace(
            Definition=types.SimpleNamespace(Name="Mark"), HasValue=True,
            StorageType="String", AsString=lambda: mark)
        self.Parameters = [param]


def _coloured(ident, mark):
    return lambda world: ColourElement(ident, mark)


# Routes that open a transaction on the document and reach a real HTTP 200:
# (collector items the route finds, body). The colour rows come last (plan 04-07).
TRANSACTING = {
    ("building", "/create_line/"): ([_named("L1")], {"elements": [dict(_WALL)]}),
    ("building", "/create_surface/"): ([_named("L1")], {"elements": [dict(_FLOOR)]}),
    ("building", "/create_level/"): ([], {"levels": [{"elevation": 3000, "name": "L1"}]}),
    ("annotation", "/create_dimensions/"): ([], {"element_ids": [1, 2]}),
    ("annotation", "/tag_walls/"): (
        {("OST_WallTags", "types"): [_named("Wall Tag")],
         ("OST_Walls", "instances"): [_wall(31, x=0.0)],
         ("OST_WallTags", "instances"): []},
        {}),
    ("detail", "/create_detail_line/"): (
        [], {"start_point": {"x": 0, "y": 0, "z": 0}, "end_point": {"x": 1000, "y": 0, "z": 0}}),
    ("colors", "/color_splash/"): (
        [_coloured(101, "A"), _coloured(102, "B"), _coloured(103, "A")],
        {"category_name": "Walls", "parameter_name": "Mark"}),
    ("colors", "/clear_colors/"): (
        [_coloured(101, "A"), _coloured(102, "B"), _coloured(103, "A")],
        {"category_name": "Walls"}),
}
TRANSACTING_IDS = ["{}:{}".format(module, route) for module, route in TRANSACTING]


def arm(world, items=()):
    """Collector results plus stable DB attributes, so a route reaches a real success.

    Every DB attribute a route compares or calls is assigned once here: the fake DB hands
    out a fresh MagicMock on each access of an unassigned name."""
    if isinstance(items, dict):
        world.collector_items = []
        world.results = dict(
            ((getattr(world.db.BuiltInCategory, category), kind), list(factories))
            for (category, kind), factories in items.items())
    else:
        world.collector_items = list(items)
    ids = itertools.count(61)
    world.db.XYZ = XYZ
    world.db.Line = MagicMock(name="DB.Line")
    world.db.Wall = types.SimpleNamespace(Create=lambda *args: Created(next(ids)))
    world.db.Floor = types.SimpleNamespace(Create=lambda *args: Created(next(ids)))
    world.db.Level = types.SimpleNamespace(Create=lambda *args: Created(next(ids)))
    override_create(world,
                    NewFootPrintRoof=lambda *args: Created(next(ids)),
                    NewDimension=lambda *args: DimensionCreated(81),
                    NewDetailCurve=lambda *args: DetailCurve(91))
    # Annotation routes: a plan view to work in, ids that carry their value, elements that
    # can be dimensioned, a tag-capable factory and line styles.
    world.attr_overrides["ActiveView"] = FakeView(world)
    world.db.StorageType = types.SimpleNamespace(
        Double="Double", Integer="Integer", String="String", ElementId="ElementId")
    world.db.ViewType = types.SimpleNamespace(
        FloorPlan="FloorPlan", CeilingPlan="CeilingPlan", Section="Section",
        Elevation="Elevation", Detail="Detail", EngineeringPlan="EngineeringPlan",
        AreaPlan="AreaPlan", DraftingView="DraftingView")
    world.db.ReferenceArray = _RefArray
    world.db.ElementId = MagicMock(
        name="DB.ElementId", side_effect=lambda value: types.SimpleNamespace(Value=int(value)))
    world.db.IndependentTag = types.SimpleNamespace(
        Create=lambda *args: Created(900 + next(ids)))
    line_styles(world, "Thin Lines", "Wide Lines")

    def get_element(doc, eid):
        value = getattr(eid, "Value", None)
        if value in world.elements:
            return world.elements[value]
        return FakeWall(value if isinstance(value, int) else 1, x=float(value or 0) * 10.0,
                        reference=value not in world.refless)

    world.hooks[(None, "GetElement")] = get_element


def reach(world, key):
    items, body = TRANSACTING[key]
    arm(world, items)
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    return body


def run(world, key, body=None):
    """Reach the route's real success state and call it with ``body`` (default: its row)."""
    row_body = reach(world, key)
    return call(world, handler_of(world, *key), row_body if body is None else body)


# ------------------------------------------------------------------ classification


@pytest.mark.parametrize("module_name", sorted(REGISTRARS))
def test_every_registered_route_is_classified(world, module_name):
    registered = set(load(world, module_name))
    expected = set((route, "POST") for (module, route) in MUTATIONS if module == module_name)
    expected |= set((route, method) for (module, route, method) in READS if module == module_name)
    expected |= set((route, method)
                    for (module, route, method) in CLASH_READS if module == module_name)
    assert registered == expected, (
        "classify every route of revit_mcp/{}.py as a mutation or a read here".format(module_name))


def test_analysis_has_no_mutating_route(world):
    """analysis.py only reads (ai_filter and material_quantities travel as POST): nothing to guard."""
    assert not [key for key in MUTATIONS if key[0] == "analysis"]
    load(world, "analysis")
    assert world.guard_calls == []


# ------------------------------------------------------------------ API-context pin


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_mutation_handler_declares_the_api_context_arguments(world, key):
    """pyRevit runs a handler in the Revit API context only if it declares uiapp, uidoc or
    doc. The injected doc and request stay; uiapp is added so the guard never needs HOST_APP."""
    module_name, route = key
    parameters = list(inspect.signature(handler_of(world, module_name, route)).parameters)
    assert "uiapp" in parameters and "doc" in parameters and "request" in parameters


@pytest.mark.parametrize("key", list(READS), ids=["{}:{}".format(k[0], k[1]) for k in READS])
def test_reads_keep_their_signature_and_are_not_guarded(world, key):
    module_name, route, method = key
    body = READS[key]
    fn = handler_of(world, module_name, route, method)
    expected = ["doc"] if body is None else ["doc", "request"]
    assert list(inspect.signature(fn).parameters) == expected
    reply = call(world, fn, body)
    assert world.guard_calls == []
    assert world.events_on("INJECTED"), "a read still works on the injected doc"
    assert "document" not in reply.data and "process_identity" not in reply.data


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


# ------------------------------------------------------------ guarded run + attribution


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_active_selection_runs_on_the_resolved_document_and_names_it(world, key):
    alpha, beta, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, *key), dict(MUTATIONS[key], document=tokens[1]))
    assert len(world.guard_calls) == 1
    assert world.events_on("INJECTED") == [], "the handler worked on the injected doc, not the guard's"
    assert world.events_on("Alpha") == []
    assert world.events_on(u"\u0411\u0435\u0442\u0430"), "the handler never touched the resolved document"
    stamped = reply.data["document"]
    assert stamped == {"document": tokens[1], "title": u"\u0411\u0435\u0442\u0430", "path": "",
                       "active": True, "saved": False}
    assert reply.data["process_identity"] == IDENT


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_sole_active_document_is_used_without_a_selector_and_named(world, key):
    only = world.open("Only", "C:/Models/Only.rvt", active=True)
    token = world.tokens()[0]
    reply = call(world, handler_of(world, *key), MUTATIONS[key])
    assert world.events_on("INJECTED") == [] and world.events_on("Only")
    assert reply.data["document"]["document"] == token
    assert reply.data["document"]["path"] == "C:/Models/Only.rvt"
    assert reply.data["process_identity"] == IDENT


def is_failure(reply):
    """A failed reply by any of the routes' own conventions: an HTTP error, an error key,
    or (colors) HTTP 200 with status "error" and a message."""
    data = reply.data
    return reply.status >= 400 or bool(data.get("error")) or data.get("status") == "error"


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_failure_after_the_guard_still_names_the_document_it_ran_on(world, key):
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    world.explode = True
    reply = call(world, handler_of(world, *key), MUTATIONS[key])
    assert is_failure(reply)
    assert reply.data["document"]["title"] == "Only"
    assert reply.data["process_identity"] == IDENT


@pytest.mark.parametrize("route", ["/color_splash/", "/clear_colors/"])
def test_color_failures_keep_their_http_200_error_body_and_gain_the_identity(world, route):
    """The colour routes answer HTTP 200 with status "error" and a message (their old
    contract, untouched). That is exactly the shape a formatter would collapse to its
    message, so the identity must sit in the body beside it."""
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    world.explode = True
    reply = call(world, handler_of(world, "colors", route), MUTATIONS[("colors", route)])
    assert reply.status == 200
    assert reply.data["status"] == "error" and reply.data["message"]
    assert reply.data["document"]["title"] == "Only"
    assert reply.data["process_identity"] == IDENT


@pytest.mark.parametrize("route", ["/color_splash/", "/clear_colors/"])
def test_color_mutations_never_reach_a_style_or_transaction_on_a_refused_document(world, route):
    _, _, tokens = two_documents(world, active="beta")
    reply = call(world, handler_of(world, "colors", route),
                 dict(MUTATIONS[("colors", route)], document=tokens[0]))
    assert reply.status == 412 and world.events == []
    assert world.kinds("transaction") == [] and world.kinds("collector") == []


def test_list_category_parameters_stays_a_read_and_reads_the_active_document(world):
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    reply = call(world, handler_of(world, "colors", "/list_category_parameters/"),
                 {"category_name": "Walls", "document": "doc1.000000000000.9"})
    assert world.guard_calls == []
    assert world.events_on("INJECTED") and "document" not in reply.data


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_a_validation_error_after_the_guard_is_attributed_too(world, key):
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    reply = call(world, handler_of(world, *key), {"unrelated": True})
    assert reply.status == 400 and reply.data["error"]
    assert reply.data["document"]["title"] == "Only"
    assert reply.data["process_identity"] == IDENT


def test_create_level_success_keeps_its_body_and_opens_the_transaction_on_the_resolved_document(world):
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    reply = call(world, handler_of(world, "building", "/create_level/"),
                 MUTATIONS[("building", "/create_level/")])
    assert reply.status == 200
    assert sorted(without_attribution(reply.data)) == [
        "count", "created", "message", "outcome", "status"]
    assert reply.data["status"] == "success"
    order = [event[0] for event in world.events]
    assert order[:2] == ["transaction", "start"], "the guard must precede any transaction"
    assert world.kinds("transaction")[0][1] == "Only"
    assert world.kinds("commit")


# --------------------------------------------- Phase 5 tracer: the gate on /create_level/
#
# One real mutation travels from the production bridge (with_envelope plus the unchanged
# _send, text/plain bytes) through revit_mcp.security.gate_or_response into the real
# handler. Every refusal must arrive before the document guard and before any Revit
# object (document attribute, collector, transaction) is touched.


class _IronPython3Json(object):
    """json as IronPython 3 ships it: loads() refuses bytes (see test_secret_gate_e2e)."""

    def loads(self, payload, *args, **kwargs):
        if not isinstance(payload, str):
            raise TypeError(
                "the JSON object must be str, not {!r}".format(payload.__class__.__name__))
        return json.loads(payload, *args, **kwargs)


CREATE_LEVEL = ("building", "/create_level/")
LEVEL_BODY = MUTATIONS[CREATE_LEVEL]


def _wire(secret):
    """LEVEL_BODY as the bridge sends it after Phase 7: envelope first, with a real permit for /create_level/.

    A None secret adds no envelope at all.
    """
    return enveloped_body(LEVEL_BODY, secret, as_type="text", route=CREATE_LEVEL[1])


def _through_the_bridge(world, body):
    """POST ``body`` to the real /create_level/ handler through the unchanged bridge._send.

    Returns (what _send returned, the request objects the handler received).
    """
    fn = handler_of(world, *CREATE_LEVEL)
    seen = []

    def revit(http_request):
        request = types.SimpleNamespace(data=http_request.content, path=CREATE_LEVEL[1])
        seen.append(request)
        reply = call(world, fn, request=request)
        return httpx.Response(reply.status, json=reply.data)

    async def run():
        transport = httpx.MockTransport(revit)
        async with httpx.AsyncClient(base_url="http://revit.test/genpro_revit_mcp/",
                                     transport=transport) as client:
            return await bridge._send(client, "POST", "/create_level/", body, 5.0, None)

    return asyncio.run(run()), seen


def _mismatch_naming(*files):
    return {"state": trust.INTEGRITY_MISMATCH, "reason": None,
            "modified": sorted(files), "missing": [], "unexpected": []}


def test_create_level_through_the_real_bridge_send_path_reaches_the_handler_without_the_envelope(
        world, monkeypatch):
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    result, seen = _through_the_bridge(world, _wire(TEST_SECRET))
    assert isinstance(result, dict), result
    assert result["outcome"]["transaction_status"] == "Committed"
    assert world.kinds("transaction")[0][1] == "Only"
    assert world.kinds("start") and world.kinds("commit")
    assert len(world.guard_calls) == 1
    assert len(seen) == 1
    data = seen[0].data
    assert isinstance(data, bytes), "bytes in, bytes out (RESEARCH Pitfall 3)"
    assert "_mcp" not in json.loads(data.decode("utf-8"))
    assert TEST_SECRET.encode("utf-8") not in data


def _refusal_case(name, monkeypatch):
    if name == "no-envelope":
        return _wire(None)
    if name == "wrong-secret":
        return _wire("wrong-secret-0123456789-abcdefXYZ-nope")
    configure_gate(monkeypatch, secret=None)
    return _wire(TEST_SECRET)


@pytest.mark.parametrize("name,word", [
    ("no-envelope", "missing"),
    ("wrong-secret", "mismatch"),
    ("unconfigured", "server_not_configured"),
])
def test_create_level_refusals_happen_before_any_document_access(world, monkeypatch, name, word):
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    del world.events[:]
    body = _refusal_case(name, monkeypatch)
    result, _ = _through_the_bridge(world, body)
    assert isinstance(result, str), result
    assert result.startswith("Error: 401 - ")
    assert word in result
    assert '"outcome"' not in result, "a refusal before any transaction carries no outcome"
    assert format_response(result) == result
    assert TEST_SECRET not in result
    assert world.transactions == []
    assert world.events == [], "no collector, document attribute or transaction before the gate"
    assert world.guard_calls == []


def test_create_level_with_a_verified_mismatch_is_a_423_naming_the_files(world, monkeypatch):
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    del world.events[:]
    configure_gate(monkeypatch, integrity=_mismatch_naming("revit_mcp/detail.py"))
    result, _ = _through_the_bridge(world, _wire(TEST_SECRET))
    assert isinstance(result, str), result
    assert result.startswith("Error: 423 - ")
    assert "revit_mcp/detail.py" in result
    assert format_response(result) == result
    assert TEST_SECRET not in result
    assert world.transactions == [] and world.events == [] and world.guard_calls == []


def test_create_level_with_a_wrong_secret_and_a_mismatch_is_still_a_401(world, monkeypatch):
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    del world.events[:]
    configure_gate(monkeypatch, integrity=_mismatch_naming("revit_mcp/detail.py"))
    wrong = _wire("wrong-secret-0123456789-abcdefXYZ-nope")
    result, _ = _through_the_bridge(world, wrong)
    assert isinstance(result, str), result
    assert result.startswith("Error: 401 - ")
    assert "mismatch" in result
    assert "revit_mcp/detail.py" not in result, "the secret is checked first (D-04)"
    assert world.transactions == [] and world.events == [] and world.guard_calls == []


# ----------------------------------- Phase 5 (05-02): every mutation of the suite is gated
#
# One parametrized refusal set over the whole MUTATIONS table. One active document is open,
# so a call that slipped past the gate would visibly reach the document guard.

WRONG_SECRET = "wrong-secret-0123456789-abcdefXYZ-nope"


def _one_open_document(world):
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()
    del world.events[:]


def _assert_gate_refusal(world, reply, status):
    assert reply.status == status
    assert "outcome" not in reply.data
    assert world.events == [], "no collector, document attribute or transaction before the gate"
    assert world.transactions == []
    assert world.guard_calls == []
    text = repr(reply.data)
    assert TEST_SECRET not in text and WRONG_SECRET not in text


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_without_the_shared_secret_a_mutation_is_401_before_any_side_effect(world, key):
    _one_open_document(world)
    request = types.SimpleNamespace(data=enveloped_body(MUTATIONS[key], secret=None, route=key[1]), path=key[1])
    reply = call(world, handler_of(world, *key), request=request)
    _assert_gate_refusal(world, reply, 401)
    assert reply.data["auth"] == "missing"


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_with_a_wrong_secret_a_mutation_is_401_before_any_side_effect(world, key):
    _one_open_document(world)
    request = types.SimpleNamespace(data=enveloped_body(MUTATIONS[key], secret=WRONG_SECRET, route=key[1]), path=key[1])
    reply = call(world, handler_of(world, *key), request=request)
    _assert_gate_refusal(world, reply, 401)
    assert reply.data["auth"] == "mismatch"


@pytest.mark.parametrize("key", list(MUTATIONS), ids=MUTATION_IDS)
def test_with_an_integrity_mismatch_a_mutation_is_423_before_any_side_effect(
        world, monkeypatch, key):
    _one_open_document(world)
    configure_gate(monkeypatch, integrity=_mismatch_naming("revit_mcp/detail.py"))
    request = types.SimpleNamespace(data=enveloped_body(MUTATIONS[key], route=key[1]), path=key[1])
    reply = call(world, handler_of(world, *key), request=request)
    _assert_gate_refusal(world, reply, 423)
    assert reply.data["files"] == ["revit_mcp/detail.py"]


# ------------------------------- Phase 5 (05-02): the four open POST reads strip, never refuse
#
# /ai_filter/, /material_quantities/, /list_category_parameters/ and /clash_check/ stay
# available whatever the request carries (SEC-05); their handlers only drop the reserved
# key so it never reaches the route's own parse (SEC-06).

OPEN_READ_VARIANTS = [
    ("no-envelope", None),
    ("wrong-secret", WRONG_SECRET),
    ("valid-secret", TEST_SECRET),
]


def _assert_open(world, reply, request, sent_envelope):
    assert reply.status not in (401, 423), reply.data
    assert world.guard_calls == []
    data = request.data
    assert data is not None
    assert b"_mcp" not in data and TEST_SECRET.encode("utf-8") not in data
    assert WRONG_SECRET.encode("utf-8") not in data
    if sent_envelope:
        assert isinstance(json.loads(data.decode("utf-8")), dict)
    assert TEST_SECRET not in repr(reply.data) and WRONG_SECRET not in repr(reply.data)


@pytest.mark.parametrize("variant", OPEN_READ_VARIANTS, ids=[v[0] for v in OPEN_READ_VARIANTS])
@pytest.mark.parametrize("key", list(POST_READS), ids=POST_READ_IDS)
def test_an_open_read_needs_no_secret_and_never_sees_the_envelope(world, key, variant):
    _name, secret = variant
    module_name, route, method = key
    request = types.SimpleNamespace(data=enveloped_body(POST_READS[key], secret=secret, route=route), path=route)
    reply = call(world, handler_of(world, module_name, route, method), request=request)
    _assert_open(world, reply, request, sent_envelope=secret is not None)


@pytest.mark.parametrize("key", list(POST_READS), ids=POST_READ_IDS)
def test_open_reads_work_when_the_gate_state_is_uninitialized(world, monkeypatch, key):
    from revit_mcp import security
    monkeypatch.setattr(security, "_STATE", None)
    module_name, route, method = key
    request = types.SimpleNamespace(data=enveloped_body(POST_READS[key], route=route), path=route)
    reply = call(world, handler_of(world, module_name, route, method), request=request)
    _assert_open(world, reply, request, sent_envelope=True)


# ------------------------------------------------------------------- helper contracts


def test_request_document_selector_reads_the_body_and_never_raises():
    pick = identity.request_document_selector
    assert pick(types.SimpleNamespace(data=json.dumps({"document": "doc1.a.1"}).encode())) == "doc1.a.1"
    assert pick(types.SimpleNamespace(data=json.dumps({"document": "doc1.a.1"}))) == "doc1.a.1"
    assert pick(types.SimpleNamespace(data={"document": "doc1.a.1"})) == "doc1.a.1"
    assert pick(types.SimpleNamespace(data=json.dumps({"x": 1}).encode())) is None
    assert pick(types.SimpleNamespace(data=None)) is None
    assert pick(None) is None
    assert pick(types.SimpleNamespace(data=b"{not json")) is None
    assert pick(types.SimpleNamespace(data=b"[1, 2]")) is None
    # present but null is an explicit, broken choice: it must not look like "omitted"
    assert pick(types.SimpleNamespace(data=b'{"document": null}')) == ""
    assert pick(types.SimpleNamespace(data=b'{"document": 7}')) == 7


class _Weird(object):
    @property
    def data(self):
        raise RuntimeError("no data")


def test_request_document_selector_survives_a_request_that_raises():
    assert identity.request_document_selector(_Weird()) is None


def test_attribute_response_stamps_a_copy_and_leaves_non_dict_data_alone(monkeypatch):
    monkeypatch.setattr(identity, "process_identity_or_error",
                        lambda uiapp=None: (dict(IDENT), None))
    descriptor = {"document": "doc1.a.1", "title": "T", "path": "P", "active": True, "saved": True}
    response = FakeResponse(200, {"status": "success"})
    assert identity.attribute_response(response, descriptor) is response
    assert response.data == {"status": "success", "document": descriptor, "process_identity": IDENT}
    assert response.data["document"] is not descriptor
    other = FakeResponse(200, "plain text")
    assert identity.attribute_response(other, descriptor).data == "plain text"
    assert identity.attribute_response(None, descriptor) is None


def test_attribute_response_names_why_identity_is_missing(monkeypatch):
    monkeypatch.setattr(identity, "process_identity_or_error",
                        lambda uiapp=None: (None, "no retained RoutesServer"))
    response = FakeResponse(500, {"error": "boom"})
    identity.attribute_response(response, {"document": "doc1.a.1"})
    assert response.data["identity_error"] == "no retained RoutesServer"
    assert "process_identity" not in response.data and response.data["error"] == "boom"


def test_attribute_response_passes_the_injected_uiapp_through(monkeypatch):
    seen = []
    monkeypatch.setattr(identity, "process_identity_or_error",
                        lambda uiapp=None: (seen.append(uiapp), (dict(IDENT), None))[1])
    marker = object()
    identity.attribute_response(FakeResponse(200, {}), {"document": "doc1.a.1"}, uiapp=marker)
    assert seen == [marker]


def test_the_guard_reads_everything_through_the_injected_uiapp(world):
    """No HOST_APP: the fake pyRevit raises if it is read, and that would be a 503."""
    only = world.open("Only", "C:/Models/Only.rvt", active=True)
    document, descriptor, response = identity.mutation_document_or_response(
        None, uiapp=world.uiapp)
    assert response is None and descriptor["title"] == "Only" and document.Equals(only)
    world.activate(None)
    document, descriptor, response = identity.mutation_document_or_response(
        None, uiapp=world.uiapp)
    assert document is None and response.status == 412
    assert response.data["process_identity"] == IDENT


# ------------------------------------------------- honest outcomes (plan 04-03, Task 1)


@pytest.mark.parametrize("key", list(TRANSACTING), ids=TRANSACTING_IDS)
def test_every_transacting_success_carries_an_outcome_that_agrees_with_its_status(world, key):
    reply = run(world, key)
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
    if key[0] == "colors":
        # The colour routes keep their historic contract: an exception is HTTP 200 with
        # status "error" and a message (D-04, D-14); the outcome rides beside it.
        assert reply.status == 200 and reply.data["status"] == "error", reply.data
    else:
        assert reply.status == 500, reply.data
    assert world.transactions, "the route never built a transaction"
    assert reply.data["outcome"]["transaction_status"] == world.transactions[-1].status
    assert reply.data["outcome"]["succeeded"] == []


def test_the_fake_world_reports_the_transaction_status_it_commits_with(world):
    """Wave 0 gap: a route that compares Commit() with DB.TransactionStatus needs both
    sides in the fake, and GetStatus must follow the transaction."""
    doc = world.open("Only", "C:/Models/Only.rvt", active=True)
    t = world.db.Transaction(doc, "x")
    assert t.GetStatus() == "Uninitialized"
    t.Start()
    assert t.GetStatus() == "Started" and not t.HasEnded()
    assert t.Commit() == world.db.TransactionStatus.Committed
    assert t.GetStatus() == "Committed" and t.HasEnded()
    world.commit_status = "RolledBack"
    t2 = world.db.Transaction(doc, "y")
    t2.Start()
    assert t2.Commit() == world.db.TransactionStatus.RolledBack


def levels_answer(world, *levels):
    queue = iter(levels)
    world.db.Level = types.SimpleNamespace(Create=lambda *args: next(queue))


def test_create_level_with_one_valid_and_one_without_elevation_is_a_partial(world):
    reach(world, ("building", "/create_level/"))
    levels_answer(world, Created(21))
    reply = call(world, handler_of(world, "building", "/create_level/"),
                 {"levels": [{"elevation": 3000, "name": "L1"}, {"name": "no elevation"}]})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"] == {
        "transaction_status": "Committed",
        "requested": 2,
        "succeeded": [21],
        "failed": [{"item": 1, "reason": "elevation is required"}],
        "revit_failures": [],
    }
    assert reply.data["errors"] == ["Level 1: elevation is required"]
    assert reply.data["count"] == 1
    text = format_response(without_attribution(reply.data))
    assert "=== PARTIAL SUCCESS ===" in text and "elevation is required" in text


def test_create_level_with_no_valid_level_is_a_422_failed(world):
    reach(world, ("building", "/create_level/"))
    reply = call(world, handler_of(world, "building", "/create_level/"),
                 {"levels": [{"name": "a"}, {"name": "b"}]})
    assert reply.status == 422
    assert reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == []
    assert [entry["item"] for entry in reply.data["outcome"]["failed"]] == [0, 1]
    assert reply.data["count"] == 0


def test_a_level_that_cannot_be_named_is_still_succeeded_and_only_the_name_step_fails(world):
    reach(world, ("building", "/create_level/"))
    levels_answer(world, Created(22, name_raises=RuntimeError("taken")))
    reply = call(world, handler_of(world, "building", "/create_level/"),
                 {"levels": [{"elevation": 3000, "name": "L1"}]})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["succeeded"] == [22]
    assert reply.data["outcome"]["failed"] == [{"item": "0.name", "reason": "taken"}]
    assert reply.data["count"] == 1 and reply.data["created"][0]["id"] == 22
    assert reply.data["created"][0]["name"] == "Created 22"


def test_create_level_success_has_exactly_the_legacy_keys_plus_outcome(world):
    reply = run(world, ("building", "/create_level/"))
    assert sorted(without_attribution(reply.data)) == [
        "count", "created", "message", "outcome", "status"]
    assert reply.data["outcome"]["requested"] == 1


def test_create_line_with_an_unsupported_item_and_a_valid_wall_is_a_partial(world):
    body = {"elements": [dict(_WALL, element_type="door"), dict(_WALL)]}
    reply = run(world, ("building", "/create_line/"), body)
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    outcome = reply.data["outcome"]
    assert outcome["requested"] == 2 and outcome["succeeded"] == [61]
    assert [entry["item"] for entry in outcome["failed"]] == [0]
    assert "element_type 'door' not supported" in outcome["failed"][0]["reason"]
    assert not outcome["failed"][0]["reason"].startswith("Element 0")
    assert reply.data["errors"][0].startswith("Element 0: element_type 'door'")
    assert reply.data["count"] == 1


def test_create_line_with_only_invalid_items_is_a_422(world):
    body = {"elements": [dict(_WALL, element_type="door"), {"start_point": {"x": 0}}]}
    reply = run(world, ("building", "/create_line/"), body)
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert [entry["item"] for entry in reply.data["outcome"]["failed"]] == [0, 1]


def test_create_surface_with_only_invalid_items_is_a_422(world):
    body = {"elements": [{"element_type": "wallpaper"}, {"element_type": "floor"}]}
    reply = run(world, ("building", "/create_surface/"), body)
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == []
    assert [entry["item"] for entry in reply.data["outcome"]["failed"]] == [0, 1]
    assert reply.data["errors"][1].startswith("Element 1: Boundary requires")


def test_create_surface_with_one_valid_floor_and_one_invalid_item_is_a_partial(world):
    body = {"elements": [dict(_FLOOR), {"element_type": "wallpaper"}]}
    reply = run(world, ("building", "/create_surface/"), body)
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["succeeded"] == [61]
    assert [entry["item"] for entry in reply.data["outcome"]["failed"]] == [1]


def test_a_floor_whose_offset_cannot_be_applied_is_succeeded_and_only_the_offset_step_fails(world):
    class ReadOnlyOffset(Created):
        def get_Parameter(self, name):
            return types.SimpleNamespace(IsReadOnly=True)

    reach(world, ("building", "/create_surface/"))
    world.db.Floor = types.SimpleNamespace(Create=lambda *args: ReadOnlyOffset(71))
    reply = call(world, handler_of(world, "building", "/create_surface/"),
                 {"elements": [dict(_FLOOR, offset=150)]})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["succeeded"] == [71]
    assert reply.data["outcome"]["failed"][0]["item"] == "0.offset"
    assert reply.data["count"] == 1


@pytest.mark.parametrize("route,body", [
    ("/create_line/", {"elements": [dict(_WALL)]}),
    ("/create_surface/", {"elements": [dict(_FLOOR)]}),
    ("/create_level/", {"levels": [{"elevation": 3000}]}),
])
def test_a_rolled_back_building_route_never_claims_what_it_created(world, route, body):
    reach(world, ("building", route))
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, "building", route), body)
    assert reply.status == 409 and reply.data["status"] == "rolled_back"
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["requested"] == 1
    assert "created" not in reply.data and "count" not in reply.data


# ------------------------------------------------- honest outcomes (plan 04-03, Task 2)

TAG_WALLS = ("annotation", "/tag_walls/")
DIMENSIONS = ("annotation", "/create_dimensions/")
DETAIL_LINE = ("detail", "/create_detail_line/")
_WALL_TAGS_TYPES = ("OST_WallTags", "types")
_WALLS = ("OST_Walls", "instances")
_WALL_TAGS_PLACED = ("OST_WallTags", "instances")
NO_CURVE = "Wall has no location curve to anchor a tag"


def tag_walls_world(world, walls, existing=()):
    world.results = {}
    arm(world, {_WALL_TAGS_TYPES: [_named("Wall Tag")], _WALLS: walls,
                _WALL_TAGS_PLACED: list(existing)})
    world.open("Only", "C:/Models/Only.rvt", active=True)
    world.tokens()


def tag_walls_call(world, walls, existing=()):
    tag_walls_world(world, walls, existing)
    return call(world, handler_of(world, *TAG_WALLS), {})


def test_tag_walls_with_a_tagged_a_taggable_and_a_curveless_wall_is_a_partial(world):
    reply = tag_walls_call(
        world, [_wall(31), _wall(32, x=10.0), _wall(33, located=False)], existing=[_tag(31)])
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    outcome = reply.data["outcome"]
    assert outcome["requested"] == 2
    assert outcome["succeeded"] == [32]
    assert outcome["failed"] == [{"item": 33, "reason": NO_CURVE}]
    assert reply.data["walls_already_tagged"] == 1 and reply.data["tags_placed"] == 1
    assert reply.data["walls_total"] == 3
    assert reply.data["skipped"] == [{"wall_id": 33, "reason": NO_CURVE}]
    text = format_response(without_attribution(reply.data))
    assert "=== PARTIAL SUCCESS ===" in text and NO_CURVE in text


def test_tag_walls_where_every_attempted_wall_fails_is_a_422(world):
    reply = tag_walls_call(world, [_wall(33, located=False), _wall(34, located=False)])
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    outcome = reply.data["outcome"]
    assert outcome["requested"] == 2 and outcome["succeeded"] == []
    assert [entry["item"] for entry in outcome["failed"]] == [33, 34]
    assert reply.data["tags_placed"] == 0


def test_tag_walls_where_every_wall_is_already_tagged_is_a_plain_success_of_nothing(world):
    reply = tag_walls_call(world, [_wall(31), _wall(32)], existing=[_tag(31), _tag(32)])
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"]["requested"] == 0
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["failed"] == []
    assert reply.data["walls_already_tagged"] == 2 and reply.data["tags_placed"] == 0


def test_tag_walls_whose_tag_cannot_be_created_names_the_wall_and_the_reason(world):
    tag_walls_world(world, [_wall(31), _wall(32)])

    def create(*args):
        if not hasattr(create, "done"):
            create.done = True
            raise RuntimeError("view is locked")
        return Created(950)

    world.db.IndependentTag = types.SimpleNamespace(Create=create)
    reply = call(world, handler_of(world, *TAG_WALLS), {})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["failed"] == [{"item": 31, "reason": "view is locked"}]
    assert reply.data["outcome"]["succeeded"] == [32]


def dimensions_call(world, body, refless=()):
    reach(world, DIMENSIONS)
    world.refless = set(refless)
    return call(world, handler_of(world, *DIMENSIONS), body)


def test_create_dimensions_with_two_referenced_elements_is_a_success_naming_the_dimension(world):
    reply = dimensions_call(world, {"element_ids": [1, 2]})
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"]["requested"] == 1
    assert reply.data["outcome"]["succeeded"] == [81] and reply.data["outcome"]["failed"] == []
    assert reply.data["count"] == 1 and reply.data["created"][0]["id"] == 81


def test_create_dimensions_when_revit_makes_no_dimension_is_a_422_naming_the_step(world):
    reach(world, DIMENSIONS)
    override_create(world, NewDimension=lambda *args: None)
    reply = call(world, handler_of(world, *DIMENSIONS), {"element_ids": [1, 2]})
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["failed"] == [
        {"item": "dimension", "reason": "NewDimension returned no dimension"}]
    assert reply.data["count"] == 0


def test_create_dimensions_with_one_element_that_yields_no_reference_is_a_partial(world):
    reply = dimensions_call(world, {"element_ids": [1, 2, 3]}, refless=[2])
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["succeeded"] == [81]
    assert [entry["item"] for entry in reply.data["outcome"]["failed"]] == [2]
    assert reply.data["outcome"]["failed"][0]["reason"].startswith("no geometry reference")
    assert reply.data["count"] == 1


def test_create_dimensions_with_fewer_than_two_references_is_still_a_400_before_any_transaction(world):
    reply = dimensions_call(world, {"element_ids": [1, 2]}, refless=[2])
    assert reply.status == 400 and "outcome" not in reply.data
    assert world.kinds("transaction") == []


def detail_call(world, body=None):
    reach(world, DETAIL_LINE)
    row = TRANSACTING[DETAIL_LINE][1]
    return call(world, handler_of(world, *DETAIL_LINE), dict(row, **(body or {})))


def test_create_detail_line_with_a_missing_line_style_is_a_partial_naming_the_style(world):
    reply = detail_call(world, {"line_style": "Missing"})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"] == {
        "transaction_status": "Committed",
        "requested": 1,
        "succeeded": [91],
        "failed": [{"item": "line_style", "reason": "line style 'Missing' not found"}],
        "revit_failures": [],
    }
    assert reply.data["line_id"] == 91 and reply.data["view_name"] == "Plan A"


def test_create_detail_line_with_a_known_line_style_is_a_success(world):
    reply = detail_call(world, {"line_style": "Wide Lines"})
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"]["failed"] == []


def test_create_detail_line_without_a_line_style_is_a_success(world):
    reply = detail_call(world)
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert sorted(without_attribution(reply.data)) == [
        "line_id", "message", "outcome", "status", "view_name"]


def test_create_detail_line_whose_style_cannot_be_applied_reports_the_reason(world):
    reach(world, DETAIL_LINE)
    override_create(world, NewDetailCurve=lambda *args: DetailCurve(
        92, style_raises=RuntimeError("style is locked")))
    row = TRANSACTING[DETAIL_LINE][1]
    reply = call(world, handler_of(world, *DETAIL_LINE), dict(row, line_style="Wide Lines"))
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"]["succeeded"] == [92]
    assert reply.data["outcome"]["failed"] == [{"item": "line_style", "reason": "style is locked"}]


def test_create_detail_line_that_yields_no_curve_keeps_its_rollback_and_500_and_gains_an_outcome(world):
    reach(world, DETAIL_LINE)
    override_create(world, NewDetailCurve=lambda *args: None)
    row = TRANSACTING[DETAIL_LINE][1]
    reply = call(world, handler_of(world, *DETAIL_LINE), dict(row))
    assert reply.status == 500 and reply.data["error"] == "Failed to create detail line"
    assert world.kinds("rollback") and world.kinds("commit") == []
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["requested"] == 1


@pytest.mark.parametrize("key", [DIMENSIONS, TAG_WALLS, DETAIL_LINE],
                         ids=["create_dimensions", "tag_walls", "create_detail_line"])
def test_a_rolled_back_annotation_route_never_claims_what_it_created(world, key):
    body = reach(world, key)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, *key), body)
    assert reply.status == 409 and reply.data["status"] == "rolled_back", reply.data
    assert reply.data["outcome"]["succeeded"] == []
    for legacy in ("created", "count", "tags_placed", "line_id", "walls_total"):
        assert legacy not in reply.data


# ------------------------------------------------- honest outcomes (plan 04-07)

COLOR_SPLASH = ("colors", "/color_splash/")
CLEAR_COLORS = ("colors", "/clear_colors/")
_SPLASH_BODY = {"category_name": "Walls", "parameter_name": "Mark"}


def colour_call(world, key, failures=None):
    """Reach the route's real success state, make some element overrides raise, call it."""
    body = reach(world, key)
    world.override_failures.update(failures or {})
    return call(world, handler_of(world, *key), body)


def test_color_splash_with_one_override_that_raises_is_a_partial_naming_the_element(world):
    reply = colour_call(world, COLOR_SPLASH, {102: RuntimeError("view is locked")})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"] == {
        "transaction_status": "Committed",
        "requested": 3,
        "succeeded": [101, 103],
        "failed": [{"item": 102, "reason": "view is locked"}],
        "revit_failures": [],
    }
    assert reply.data["statistics"]["elements_colored"] == 2
    assert reply.data["statistics"]["total_elements"] == 3
    assert reply.data["category"] == "Walls" and reply.data["color_assignments"]
    text = format_response(without_attribution(reply.data))
    assert "=== PARTIAL SUCCESS ===" in text and "view is locked" in text


def test_color_splash_where_every_override_raises_is_a_422_failed(world):
    failures = dict((ident, RuntimeError("view is locked")) for ident in (101, 102, 103))
    reply = colour_call(world, COLOR_SPLASH, failures)
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == []
    assert [entry["item"] for entry in reply.data["outcome"]["failed"]] == [101, 103, 102]
    assert reply.data["statistics"]["elements_colored"] == 0


def test_color_splash_success_names_every_colored_element_and_keeps_its_legacy_keys(world):
    reply = run(world, COLOR_SPLASH)
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"]["requested"] == 3
    assert reply.data["outcome"]["succeeded"] == [101, 103, 102]
    assert reply.data["outcome"]["failed"] == []
    assert reply.data["statistics"]["elements_colored"] == 3
    assert "Successfully colored 3 elements" in reply.data["message"]
    assert world.overridden == [101, 103, 102]


def test_a_rolled_back_color_splash_never_says_it_colored_anything(world):
    body = reach(world, COLOR_SPLASH)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, *COLOR_SPLASH), body)
    assert reply.status == 409 and reply.data["status"] == "rolled_back", reply.data
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["requested"] == 3
    assert reply.data["outcome"]["transaction_status"] == "RolledBack"
    assert "Successfully colored" not in json.dumps(reply.data)
    for legacy in ("statistics", "color_assignments", "category"):
        assert legacy not in reply.data


def test_a_color_splash_that_raises_keeps_its_200_error_body_and_gains_an_outcome(world):
    body = reach(world, COLOR_SPLASH)
    world.break_start.add("Only")
    reply = call(world, handler_of(world, *COLOR_SPLASH), body)
    assert reply.status == 200 and reply.data["status"] == "error"
    assert reply.data["message"].startswith("Failed to color elements:")
    assert reply.data["outcome"]["transaction_status"] == "Uninitialized"
    assert reply.data["outcome"]["succeeded"] == []
    assert reply.data["outcome"]["requested"] == 3


def test_color_splash_validation_bodies_are_unchanged_and_carry_no_outcome(world):
    reach(world, COLOR_SPLASH)
    unknown = call(world, handler_of(world, *COLOR_SPLASH),
                   {"category_name": "Nothing", "parameter_name": "Mark"})
    assert unknown.status == 200 and unknown.data["status"] == "error"
    assert unknown.data["message"] == "Category 'Nothing' not found"
    assert "outcome" not in unknown.data
    world.collector_items = []
    empty = call(world, handler_of(world, *COLOR_SPLASH), dict(_SPLASH_BODY))
    assert empty.status == 200 and empty.data["status"] == "error"
    assert empty.data["message"] == "No elements found in category 'Walls'"
    assert "outcome" not in empty.data
    assert world.kinds("transaction") == []


def test_clear_colors_with_one_override_that_raises_is_a_partial_naming_the_element(world):
    reply = colour_call(world, CLEAR_COLORS, {102: RuntimeError("view is locked")})
    assert reply.status == 200 and reply.data["status"] == "partial", reply.data
    assert reply.data["outcome"] == {
        "transaction_status": "Committed",
        "requested": 3,
        "succeeded": [101, 103],
        "failed": [{"item": 102, "reason": "view is locked"}],
        "revit_failures": [],
    }
    assert reply.data["elements_processed"] == 2 and reply.data["category"] == "Walls"
    text = format_response(without_attribution(reply.data))
    assert "=== PARTIAL SUCCESS ===" in text and "view is locked" in text


def test_clear_colors_where_every_override_raises_is_a_422_failed(world):
    failures = dict((ident, RuntimeError("view is locked")) for ident in (101, 102, 103))
    reply = colour_call(world, CLEAR_COLORS, failures)
    assert reply.status == 422 and reply.data["status"] == "failed" and reply.data["error"]
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["elements_processed"] == 0


def test_clear_colors_success_names_every_cleared_element(world):
    reply = run(world, CLEAR_COLORS)
    assert reply.status == 200 and reply.data["status"] == "success", reply.data
    assert reply.data["outcome"]["succeeded"] == [101, 102, 103]
    assert reply.data["outcome"]["requested"] == 3
    assert reply.data["elements_processed"] == 3
    assert sorted(without_attribution(reply.data)) == [
        "category", "elements_processed", "message", "outcome", "status"]


def test_a_rolled_back_clear_colors_never_says_it_cleared_anything(world):
    body = reach(world, CLEAR_COLORS)
    world.commit_status = "RolledBack"
    reply = call(world, handler_of(world, *CLEAR_COLORS), body)
    assert reply.status == 409 and reply.data["status"] == "rolled_back", reply.data
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["requested"] == 3
    assert "Successfully cleared" not in json.dumps(reply.data)
    assert "elements_processed" not in reply.data


def test_a_clear_colors_that_raises_keeps_its_200_error_body_and_gains_an_outcome(world):
    body = reach(world, CLEAR_COLORS)
    world.break_start.add("Only")
    reply = call(world, handler_of(world, *CLEAR_COLORS), body)
    assert reply.status == 200 and reply.data["status"] == "error"
    assert reply.data["message"].startswith("Failed to clear colors:")
    assert reply.data["outcome"]["transaction_status"] == "Uninitialized"
    assert reply.data["outcome"]["succeeded"] == [] and reply.data["outcome"]["requested"] == 3


def test_clear_colors_validation_bodies_are_unchanged_and_carry_no_outcome(world):
    reach(world, CLEAR_COLORS)
    unknown = call(world, handler_of(world, *CLEAR_COLORS), {"category_name": "Nothing"})
    assert unknown.status == 200 and unknown.data["status"] == "error"
    assert unknown.data["message"] == "Category 'Nothing' not found"
    assert "outcome" not in unknown.data
    world.collector_items = []
    empty = call(world, handler_of(world, *CLEAR_COLORS), {"category_name": "Walls"})
    assert empty.status == 200 and empty.data["status"] == "warning"
    assert empty.data["message"] == "No elements found in category 'Walls'"
    assert "outcome" not in empty.data
    assert world.kinds("transaction") == []
