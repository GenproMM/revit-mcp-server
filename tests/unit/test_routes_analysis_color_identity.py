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

import importlib
import inspect
import json
import sys
import types
from unittest.mock import MagicMock

import pytest

from revit_mcp import identity

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


def make_db(world):
    class Transaction(object):
        def __init__(self, doc, name=""):
            world.record("transaction", doc, name)
            self.doc = doc
            self.started = False

        def Start(self):
            if world.explode:
                raise RuntimeError("transaction could not start")
            self.started = True
            world.record("start", self.doc)

        def Commit(self):
            world.record("commit", self.doc)
            return "Committed"

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
            return MagicMock(name=name)

    class FilteredElementCollector(object):
        def __init__(self, doc, *args):
            world.record("collector", doc)
            if world.explode:
                raise RuntimeError("collector could not be created")

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            return lambda *args, **kwargs: self

        def __iter__(self):
            return iter(())

        def __len__(self):
            return 0

        def __getitem__(self, index):
            raise IndexError(index)

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
    return db


class HostAppTrap(object):
    """pyRevit's process-global HOST_APP. A handler must use the injected uiapp."""

    def __getattr__(self, name):
        raise AssertionError("HOST_APP." + name + " was read; use the injected uiapp")


ROUTE_MODULES = ("utils", "analysis", "annotation", "building", "colors", "detail")


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

    fake_pyrevit = types.SimpleNamespace(
        routes=types.SimpleNamespace(make_response=make_response),
        revit=MagicMock(name="revit"),
        DB=make_db(w),
        HOST_APP=HostAppTrap(),
    )
    monkeypatch.setitem(sys.modules, "pyrevit", fake_pyrevit)
    generic = types.ModuleType("System.Collections.Generic")
    generic.List = list
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
    available = {"uiapp": world.uiapp, "doc": world.injected, "request": request_of(body)}
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


# ------------------------------------------------------------------ classification


@pytest.mark.parametrize("module_name", sorted(REGISTRARS))
def test_every_registered_route_is_classified(world, module_name):
    registered = set(load(world, module_name))
    expected = set((route, "POST") for (module, route) in MUTATIONS if module == module_name)
    expected |= set((route, method) for (module, route, method) in READS if module == module_name)
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
    assert sorted(without_attribution(reply.data)) == ["count", "created", "message", "status"]
    assert reply.data["status"] == "success"
    order = [event[0] for event in world.events]
    assert order[:2] == ["transaction", "start"], "the guard must precede any transaction"
    assert world.kinds("transaction")[0][1] == "Only"
    assert world.kinds("commit")


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
