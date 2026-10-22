# -*- coding: utf-8 -*-
"""Wave-0 Document doubles for the multi-document contracts (plan 02-02, D-08).

Pure Python, no Revit, no pyRevit, no network. These are FIXTURES that model the
retained-reference-equals-v1 semantics accepted at the 02-20 checkpoint (G2), so
the document registry and routes of 02-04 onward have something to be written
against. The doubles are NOT production evidence: nothing in this file proves how
a real Revit Document behaves; the live G2 measurement was the 02-20 diagnostic
capture. The tests added from "02-04 Task 1" on drive the production registry in
revit_mcp/identity.py against these doubles, as offline evidence of its decision
logic only (live recheck: 02-18, after a full Revit restart).

Modelled semantics (G2 retained-reference-equals-v1):

* Every enumeration of ``FakeApplication.Documents`` yields NEW wrapper objects, so
  ReferenceEquals / ``is`` between two enumerations is False.
* ``Equals`` is True only between wrappers of one open lifetime, and exactly one
  document of a current enumeration Equals a retained wrapper while it is open.
* ``Title`` and ``PathName`` are presentation fields, never identity: two unsaved
  Projects, two files named SAME.rvt in different folders, and a replacement
  opened after a close with identical title/path are distinguished only by
  lifetime.
* Closing a document makes every retained wrapper of that lifetime invalid
  (``IsValidObject`` False); a replacement with the same presentation fields is a
  NEW lifetime that the closed wrapper does not Equal.
* A variant whose ``IsValidObject`` raises models an inaccessible wrapper; the
  contract treats that as not valid, never as a pass.
"""

import itertools

import pytest


class InvalidObjectError(Exception):
    """Stands in for the Revit exception raised when a wrapper is accessed unusably."""


class _Lifetime(object):
    """One open lifetime of one document; never reused after close."""

    _counter = itertools.count(1)

    def __init__(self, title, path):
        self.serial = next(_Lifetime._counter)
        self.title = title
        self.path = path
        self.open = True


class FakeDocument(object):
    """A wrapper over one lifetime. Equals is lifetime equality, not reference equality."""

    def __init__(self, lifetime, raises_on_valid_check=False):
        self._lifetime = lifetime
        self._raises = raises_on_valid_check

    @property
    def Title(self):
        return self._lifetime.title

    @property
    def PathName(self):
        return self._lifetime.path

    @property
    def IsValidObject(self):
        if self._raises:
            raise InvalidObjectError("document wrapper is not accessible")
        return self._lifetime.open

    def Equals(self, other):
        return isinstance(other, FakeDocument) and other._lifetime is self._lifetime

    def ReferenceEquals(self, other):
        return self is other

    @property
    def lifetime_serial(self):
        """Test-only observation of the hidden lifetime; production code never sees it."""
        return self._lifetime.serial


class FakeApplication(object):
    """The application owning the open lifetimes."""

    def __init__(self, raises_on_valid_check=False):
        self._open = []
        self._raises = raises_on_valid_check

    def open_document(self, title, path=""):
        lifetime = _Lifetime(title, path)
        self._open.append(lifetime)
        return FakeDocument(lifetime, self._raises)

    def close_document(self, document):
        lifetime = document._lifetime
        if lifetime in self._open:
            lifetime.open = False
            self._open.remove(lifetime)

    @property
    def Documents(self):
        """A fresh enumeration: new wrapper objects on every access."""
        return [FakeDocument(lifetime, self._raises) for lifetime in self._open]


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def app():
    return FakeApplication()


@pytest.fixture
def two_unsaved_projects(app):
    """Two unsaved documents with the same presentation fields (Revit numbers
    new projects, so identical titles are a deliberate worst case here)."""
    first = app.open_document("Project1", "")
    second = app.open_document("Project1", "")
    return app, first, second


@pytest.fixture
def two_same_filename_documents(app):
    """A/SAME.rvt and B/SAME.rvt: same file name and title, different folders."""
    a = app.open_document("SAME", "C:/A/SAME.rvt")
    b = app.open_document("SAME", "C:/B/SAME.rvt")
    return app, a, b


@pytest.fixture
def close_then_replace(app):
    """Close one of two same-title documents, then open a replacement with the
    identical title and path. Returns (app, closed, survivor, replacement)."""
    closed = app.open_document("Project1", "")
    survivor = app.open_document("Project1", "")
    app.close_document(closed)
    replacement = app.open_document("Project1", "")
    return app, closed, survivor, replacement


def matches_in_current_enumeration(app, retained):
    return [doc for doc in app.Documents if retained.Equals(doc)]


# --------------------------------------------------------------- self-tests


def test_every_enumeration_yields_new_wrapper_objects(two_unsaved_projects):
    app, _first, _second = two_unsaved_projects
    one, two = app.Documents, app.Documents
    assert len(one) == len(two) == 2
    for a, b in zip(one, two):
        assert a is not b
        assert a.ReferenceEquals(b) is False
        assert a.Equals(b) is True  # same open lifetime


def test_retained_reference_has_exactly_one_equals_match_while_open(two_unsaved_projects):
    app, first, second = two_unsaved_projects
    assert len(matches_in_current_enumeration(app, first)) == 1
    assert len(matches_in_current_enumeration(app, second)) == 1
    assert matches_in_current_enumeration(app, first)[0].lifetime_serial == first.lifetime_serial
    assert not first.Equals(second)
    assert not second.Equals(first)


def test_title_and_path_are_presentation_fields_not_identity(two_unsaved_projects):
    _app, first, second = two_unsaved_projects
    assert (first.Title, first.PathName) == (second.Title, second.PathName)
    assert not first.Equals(second)


def test_same_filename_in_different_folders_are_distinct_lifetimes(two_same_filename_documents):
    app, a, b = two_same_filename_documents
    assert a.Title == b.Title == "SAME"
    assert a.PathName != b.PathName
    assert not a.Equals(b)
    assert len(matches_in_current_enumeration(app, a)) == 1
    assert len(matches_in_current_enumeration(app, b)) == 1


def test_close_invalidates_the_retained_wrapper_and_only_that_one(close_then_replace):
    app, closed, survivor, _replacement = close_then_replace
    assert closed.IsValidObject is False
    assert survivor.IsValidObject is True
    assert matches_in_current_enumeration(app, closed) == []
    assert len(matches_in_current_enumeration(app, survivor)) == 1


def test_replacement_with_identical_presentation_is_a_new_lifetime(close_then_replace):
    app, closed, survivor, replacement = close_then_replace
    assert (replacement.Title, replacement.PathName) == (closed.Title, closed.PathName)
    assert not closed.Equals(replacement)
    assert not replacement.Equals(closed)
    assert replacement.lifetime_serial != closed.lifetime_serial
    assert replacement.IsValidObject is True
    assert closed.IsValidObject is False, "must stay invalid after the replacement opens"
    assert len(matches_in_current_enumeration(app, replacement)) == 1
    assert len(matches_in_current_enumeration(app, survivor)) == 1


def test_a_closed_lifetime_is_never_revived_by_reopening_the_same_path(app):
    first = app.open_document("SAME", "C:/A/SAME.rvt")
    app.close_document(first)
    again = app.open_document("SAME", "C:/A/SAME.rvt")
    assert first.IsValidObject is False
    assert not first.Equals(again)
    assert matches_in_current_enumeration(app, first) == []


def test_closing_twice_is_harmless(app):
    doc = app.open_document("Project1", "")
    app.close_document(doc)
    app.close_document(doc)
    assert doc.IsValidObject is False
    assert app.Documents == []


def test_equals_rejects_foreign_objects(app):
    doc = app.open_document("Project1", "")
    assert doc.Equals(None) is False
    assert doc.Equals("Project1") is False
    assert doc.Equals(object()) is False


def test_is_valid_object_raises_variant_is_inaccessible_not_valid():
    app = FakeApplication(raises_on_valid_check=True)
    doc = app.open_document("Project1", "")
    with pytest.raises(InvalidObjectError):
        doc.IsValidObject
    # Equals still works on the retained lifetime: the contract must not treat a
    # raising validity check as proof of validity.
    assert len(matches_in_current_enumeration(app, doc)) == 1
    app.close_document(doc)
    assert matches_in_current_enumeration(app, doc) == []
    with pytest.raises(InvalidObjectError):
        doc.IsValidObject


def test_raising_variant_enumerations_also_raise_per_wrapper():
    app = FakeApplication(raises_on_valid_check=True)
    app.open_document("A", "C:/A.rvt")
    for wrapper in app.Documents:
        with pytest.raises(InvalidObjectError):
            wrapper.IsValidObject


def test_enumeration_after_all_closed_is_empty(two_unsaved_projects):
    app, first, second = two_unsaved_projects
    app.close_document(first)
    app.close_document(second)
    assert app.Documents == []
    assert first.IsValidObject is False and second.IsValidObject is False


def test_lifetime_serials_are_unique_across_applications():
    one = FakeApplication().open_document("Project1", "")
    two = FakeApplication().open_document("Project1", "")
    assert one.lifetime_serial != two.lifetime_serial
    assert not one.Equals(two)


# ===========================================================================
# 02-04 Task 1: the registry, descriptors and the list_documents tool/route.
#
# Everything below drives the PRODUCTION registry in revit_mcp/identity.py
# against the doubles above. It is offline evidence of the decision logic only:
# how a real Revit Document behaves (IsValidObject after close, Equals between
# enumerations, AppDomain slot retention of a Python object) is rechecked live
# in 02-18 after a full Revit restart.
# ===========================================================================

import asyncio
import inspect
import os
import re
import sys
import types

from revit_mcp import identity

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN_SHAPE = re.compile(r"^doc1\.[0-9a-f]{12}\.[1-9][0-9]*$")


@pytest.fixture
def registry():
    return identity.DocumentRegistry()


def snap(app, active=None):
    """(documents, active) exactly as the live glue reads them: a fresh enumeration
    plus the UI active document (a wrapper that is NOT one of the enumerated objects)."""
    return (app.Documents, active)


def tokens_of(result):
    return [entry["document"] for entry in result["documents"]]


def counter_of(token):
    return int(token.rsplit(".", 1)[1])


# --------------------------------------------------------- list / descriptors


def test_two_same_title_unsaved_documents_get_independent_selectors_and_flags(
        registry, two_unsaved_projects):
    app, first, second = two_unsaved_projects
    result = identity.current_document_descriptors(snap(app, second), registry)
    assert result["ok"] is True and result["count"] == 2
    docs = result["documents"]
    assert [d["title"] for d in docs] == ["Project1", "Project1"]
    assert [d["path"] for d in docs] == ["", ""]
    tokens = tokens_of(result)
    assert len(set(tokens)) == 2
    assert all(TOKEN_SHAPE.match(t) for t in tokens)
    assert [d["active"] for d in docs] == [False, True]
    assert result["active_document"] == tokens[1]
    # The same lifetimes keep the same selectors on the next request, and the
    # active flag follows the UI at request time (never cached).
    again = identity.current_document_descriptors(snap(app, first), registry)
    assert tokens_of(again) == tokens
    assert [d["active"] for d in again["documents"]] == [True, False]
    assert again["active_document"] == tokens[0]


def test_same_filename_in_different_folders_are_distinct_selectable_documents(
        registry, two_same_filename_documents):
    app, a, _b = two_same_filename_documents
    result = identity.current_document_descriptors(snap(app, a), registry)
    assert [d["path"] for d in result["documents"]] == ["C:/A/SAME.rvt", "C:/B/SAME.rvt"]
    assert len(set(tokens_of(result))) == 2


def test_tokens_are_not_derived_from_title_path_or_hash(registry, app, monkeypatch):
    def forbidden(self):
        raise AssertionError("the registry must never read a runtime hash")

    monkeypatch.setattr(FakeDocument, "GetHashCode", forbidden, raising=False)
    app.open_document("Project1", "C:/Models/Project1.rvt")
    app.open_document("Project1", "C:/Models/Project1.rvt")
    result = identity.current_document_descriptors(snap(app), registry)
    for entry in result["documents"]:
        lowered = entry["document"].lower()
        assert "project1" not in lowered and "models" not in lowered
    assert len(set(tokens_of(result))) == 2


def test_empty_application_is_an_empty_list_not_an_error(registry, app):
    result = identity.current_document_descriptors(snap(app), registry)
    assert result == {"ok": True, "documents": [], "count": 0, "active_document": None}


def test_non_ascii_title_and_path_are_preserved(registry, app):
    app.open_document("Проект1", "C:/Модели/Здание.rvt")
    result = identity.current_document_descriptors(snap(app), registry)
    assert result["documents"][0]["title"] == "Проект1"
    assert result["documents"][0]["path"] == "C:/Модели/Здание.rvt"


def test_linked_documents_are_never_listed_or_eligible(registry, app, monkeypatch):
    monkeypatch.setattr(FakeDocument, "IsLinked",
                        property(lambda self: self.Title == "Link"), raising=False)
    host = app.open_document("Host", "C:/Host.rvt")
    app.open_document("Link", "C:/Link.rvt")
    result = identity.current_document_descriptors(snap(app, host), registry)
    assert [d["title"] for d in result["documents"]] == ["Host"]
    assert result["count"] == 1


# ----------------------------------------------- close, tombstones, replacement


def test_closing_a_document_tombstones_its_token_permanently(registry, two_unsaved_projects):
    app, first, second = two_unsaved_projects
    tokens = tokens_of(identity.current_document_descriptors(snap(app, second), registry))
    app.close_document(first)
    after = identity.current_document_descriptors(snap(app, second), registry)
    assert tokens_of(after) == [tokens[1]]
    closed = identity.resolve_document(tokens[0], snap(app, second), registry)
    assert closed["ok"] is False
    assert closed["status"] == 404 and closed["code"] == "document-closed"
    # Permanent: still refused after further churn.
    app.open_document("Other", "")
    identity.current_document_descriptors(snap(app, second), registry)
    again = identity.resolve_document(tokens[0], snap(app, second), registry)
    assert again["code"] == "document-closed"
    survivor = identity.resolve_document(tokens[1], snap(app, second), registry)
    assert survivor["ok"] is True


def test_replacement_with_identical_title_and_path_gets_a_fresh_token(registry, app):
    closed = app.open_document("Project1", "")
    survivor = app.open_document("Project1", "")
    old_tokens = tokens_of(identity.current_document_descriptors(snap(app, survivor), registry))
    app.close_document(closed)
    replacement = app.open_document("Project1", "")
    result = identity.current_document_descriptors(snap(app, replacement), registry)
    new_tokens = tokens_of(result)
    assert new_tokens[0] == old_tokens[1]                  # survivor unchanged
    assert new_tokens[1] not in old_tokens                 # replacement is new
    assert counter_of(new_tokens[1]) > max(counter_of(t) for t in old_tokens)
    stale = identity.resolve_document(old_tokens[0], snap(app, replacement), registry)
    assert stale["ok"] is False and stale["code"] == "document-closed"
    assert stale["status"] == 404


def test_a_recurring_runtime_hash_does_not_recycle_a_token(registry, app, monkeypatch):
    monkeypatch.setattr(FakeDocument, "GetHashCode", lambda self: 12345, raising=False)
    first = app.open_document("Project1", "")
    token_one = tokens_of(identity.current_document_descriptors(snap(app, first), registry))[0]
    app.close_document(first)
    second = app.open_document("Project1", "")
    token_two = tokens_of(identity.current_document_descriptors(snap(app, second), registry))[0]
    assert token_one != token_two
    assert identity.resolve_document(token_one, snap(app, second), registry)["code"] == "document-closed"


def test_token_counter_is_monotonic_across_open_and_close(registry, app):
    seen = []
    for index in range(4):
        doc = app.open_document("Project1", "")
        seen.append(tokens_of(identity.current_document_descriptors(snap(app, doc), registry))[-1])
        app.close_document(doc)
    assert [counter_of(t) for t in seen] == sorted(set(counter_of(t) for t in seen))
    assert len(set(seen)) == 4


# ------------------------------------------- unreadable lifetimes never close


def test_is_valid_object_exception_refuses_and_is_not_closure(registry, two_unsaved_projects, monkeypatch):
    app, first, second = two_unsaved_projects
    tokens = tokens_of(identity.current_document_descriptors(snap(app, first), registry))

    def unreadable(self):
        raise InvalidObjectError("wrapper not accessible")

    with monkeypatch.context() as patched:
        patched.setattr(FakeDocument, "IsValidObject", property(unreadable))
        explicit = identity.resolve_document(tokens[0], snap(app, first), registry)
        assert explicit["ok"] is False
        assert explicit["status"] == 503 and explicit["code"] == "document-identity-unavailable"
        listing = identity.current_document_descriptors(snap(app, first), registry)
        assert listing["ok"] is False and listing["code"] == "document-identity-unavailable"
    # Recovery: nothing was tombstoned, the same tokens still resolve.
    for token in tokens:
        assert identity.resolve_document(token, snap(app, first), registry)["ok"] is True


def test_application_whose_validity_check_always_raises_never_resolves():
    app = FakeApplication(raises_on_valid_check=True)
    doc = app.open_document("Project1", "")
    registry = identity.DocumentRegistry()
    first = identity.current_document_descriptors(snap(app, doc), registry)
    assert first["ok"] is True       # a brand-new lifetime has nothing retained to check
    token = tokens_of(first)[0]
    second = identity.resolve_document(token, snap(app, doc), registry)
    assert second["ok"] is False and second["code"] == "document-identity-unavailable"


class DuplicatingApplication(FakeApplication):
    """An enumeration that yields one lifetime twice: a retained reference then has
    two Equals matches, which is ambiguity, never a choice."""

    @property
    def Documents(self):
        docs = FakeApplication.Documents.fget(self)
        return docs + docs[:1]


def test_two_equals_matches_refuse_by_name_and_never_retarget():
    app = DuplicatingApplication()
    doc = app.open_document("Project1", "")
    registry = identity.DocumentRegistry()
    # The first observation sees one lifetime twice: it is refused by name, and
    # nothing is chosen between the two wrappers.
    first = identity.current_document_descriptors(snap(app, doc), registry)
    assert first["ok"] is False and first["code"] == "document-identity-ambiguous"
    assert first["status"] == 400


def test_retained_reference_with_two_matches_is_ambiguous(registry, app):
    doc = app.open_document("Project1", "")
    token = tokens_of(identity.current_document_descriptors(snap(app, doc), registry))[0]
    docs = app.Documents
    result = identity.resolve_document(token, (docs + docs[:1], doc), registry)
    assert result["ok"] is False and result["code"] == "document-identity-ambiguous"
    assert result["status"] == 400
    # It is not closure either: a clean enumeration resolves it again.
    assert identity.resolve_document(token, snap(app, doc), registry)["ok"] is True


# ---------------------------------------------- registry lifetime and selectors


def test_registry_in_a_store_survives_reacquisition_and_a_lost_registry_never_reissues():
    store = identity.LocalStore()
    one = identity.get_document_registry(store)
    assert identity.get_document_registry(store) is one
    app = FakeApplication()
    doc = app.open_document("Project1", "")
    old_token = tokens_of(identity.current_document_descriptors(snap(app, doc), one))[0]
    # The slot is lost (module re-import without an owned slot): a new generation.
    fresh = identity.DocumentRegistry()
    new_token = tokens_of(identity.current_document_descriptors(snap(app, doc), fresh))[0]
    assert new_token != old_token
    assert counter_of(new_token) == counter_of(old_token)      # same counter, different generation
    stale = identity.resolve_document(old_token, snap(app, doc), fresh)
    assert stale["ok"] is False and stale["status"] == 404
    assert stale["code"] == "document-token-stale"


def test_a_store_holding_a_foreign_object_gets_a_fresh_registry():
    store = identity.LocalStore()
    store.set(identity.REGISTRY_KEY, "not a registry")
    assert isinstance(identity.get_document_registry(store), identity.DocumentRegistry)


def test_selectors_that_are_not_tokens_are_refused_by_name(registry, app):
    doc = app.open_document("Project1", "C:/Models/Project1.rvt")
    for selector in ("Project1", "C:/Models/Project1.rvt", "", "doc1.zz.1", 7):
        result = identity.resolve_document(selector, snap(app, doc), registry)
        assert result["ok"] is False
        assert result["status"] == 400 and result["code"] == "document-selector-invalid"
    unknown = identity.resolve_document(
        "doc1.{}.99".format(registry.generation), snap(app, doc), registry)
    assert unknown["status"] == 404 and unknown["code"] == "document-token-unknown"


# ------------------------------------------------------------ tool and route


class FakeMCP(object):
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


def run_tool(response, **kwargs):
    from tools.document_tools import register_document_tools

    calls = []

    async def revit_get(path, ctx=None, **options):
        calls.append((path, options))
        return response

    async def revit_post(*args, **kwargs):  # pragma: no cover - never called
        raise AssertionError("list_documents must not POST")

    mcp = FakeMCP()
    register_document_tools(mcp, revit_get, revit_post)
    text = asyncio.run(mcp.tools["list_documents"](**kwargs))
    return text, calls


IDENT = {"pid": 4242, "actual_port": 48885, "session_token": "tok-abc", "revit_version": "2024"}


def listing_payload(documents):
    return {"status": "success", "process_identity": dict(IDENT), "documents": documents,
            "count": len(documents),
            "active_document": next((d["document"] for d in documents if d["active"]), None)}


def test_list_documents_tool_renders_identity_and_every_selector():
    docs = [{"document": "doc1.aaaaaaaaaaaa.1", "title": "Проект1", "path": "", "active": False, "saved": False},
            {"document": "doc1.aaaaaaaaaaaa.2", "title": "Проект1", "path": "C:/М/П.rvt", "active": True, "saved": True}]
    text, calls = run_tool(listing_payload(docs))
    assert calls == [("/documents/", {})]
    assert "doc1.aaaaaaaaaaaa.1" in text and "doc1.aaaaaaaaaaaa.2" in text
    assert text.count("Проект1") == 2 and "C:/М/П.rvt" in text
    assert "ACTIVE" in text
    assert "PID 4242" in text and "48885" in text and "tok-abc" in text


def test_list_documents_tool_passes_target_and_reports_an_empty_list_as_data():
    text, calls = run_tool(listing_payload([]), target="revit1:xyz")
    assert calls == [("/documents/", {"target": "revit1:xyz"})]
    assert "No documents are open" in text and "PID 4242" in text
    assert "ERROR" not in text.upper()


def test_list_documents_tool_never_labels_a_refusal_as_a_received_listing():
    text, _ = run_tool("Error: request not sent: queue busy")
    assert text == "Error: request not sent: queue busy"
    text, _ = run_tool({"error": "boom", "error_code": "document-identity-unavailable"})
    assert "boom" in text and "Answering Revit process" not in text


def test_list_documents_signature_keeps_ctx_last():
    from tools.document_tools import register_document_tools

    mcp = FakeMCP()
    register_document_tools(mcp, None, None)
    names = list(inspect.signature(mcp.tools["list_documents"]).parameters)
    assert names == ["target", "ctx"]
    doc = mcp.tools["list_documents"].__doc__
    for name in names:
        assert name + ":" in doc, "docstring Args must name {}".format(name)


def test_documents_route_module_shape():
    with open(os.path.join(REPO_ROOT, "revit_mcp", "documents.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert source.startswith("# -*- coding: UTF-8 -*-") or source.startswith("# -*- coding: utf-8 -*-")
    assert "def register_documents_routes(api)" in source
    assert '"/documents/"' in source or "'/documents/'" in source
    assert "from .identity import" in source
    assert "revit.doc" not in source, "the active document is read only through the registry glue"


# ===========================================================================
# 02-04 Task 2: the mutation decision contract (D-08, D-09, D-10).
#
# A pure decision plus a thin response builder that handlers call explicitly
# (G1: explicit-route-only, no wrapper in startup.py). 412 is locked to the
# open-but-inactive case.
# ===========================================================================


def two_open(registry, app, active_index):
    """Open two same-title documents; return (first, second, tokens)."""
    first = app.open_document("Project1", "")
    second = app.open_document("Project1", "")
    docs = [first, second]
    tokens = tokens_of(identity.current_document_descriptors(snap(app, docs[active_index]), registry))
    return first, second, tokens


def test_explicit_active_token_succeeds_and_returns_the_document(registry, app):
    first, second, tokens = two_open(registry, app, 1)
    decision = identity.decide_mutation_document(tokens[1], snap(app, second), registry)
    assert decision["ok"] is True
    assert decision["document"].Equals(second)
    assert decision["descriptor"]["document"] == tokens[1]
    assert decision["descriptor"]["active"] is True


def test_explicit_inactive_token_is_412_and_never_returns_a_document(registry, app):
    first, second, tokens = two_open(registry, app, 1)
    decision = identity.decide_mutation_document(tokens[0], snap(app, second), registry)
    assert decision["ok"] is False and "document" not in decision
    assert decision["status"] == 412 and decision["code"] == "document-not-active"
    assert decision["active_document"] == tokens[1]
    assert [c["document"] for c in decision["candidates"]] == tokens
    assert "does not activate" in decision["error"]


def test_closed_selector_never_falls_back_to_the_surviving_active_document(registry, app):
    first, second, tokens = two_open(registry, app, 0)
    app.close_document(first)
    # The survivor is now the only open document, but the caller named the closed one.
    decision = identity.decide_mutation_document(tokens[0], snap(app, second), registry)
    assert decision["ok"] is False and "document" not in decision
    assert decision["status"] == 404 and decision["code"] == "document-closed"
    assert [c["document"] for c in decision["candidates"]] == [tokens[1]]


def test_replacement_with_a_recycled_handle_never_revalidates_a_stale_token(registry, app):
    first, second, tokens = two_open(registry, app, 1)
    app.close_document(first)
    replacement = app.open_document("Project1", "")
    # The replacement is active and carries identical title and path.
    decision = identity.decide_mutation_document(tokens[0], snap(app, replacement), registry)
    assert decision["ok"] is False and decision["code"] == "document-closed"
    fresh = identity.current_document_descriptors(snap(app, replacement), registry)
    assert tokens[0] not in tokens_of(fresh)
    ok = identity.decide_mutation_document(tokens_of(fresh)[1], snap(app, replacement), registry)
    assert ok["ok"] is True and ok["document"].Equals(replacement)


def test_omitted_selector_with_one_active_document_succeeds(registry, app):
    only = app.open_document("Only", "C:/Only.rvt")
    decision = identity.decide_mutation_document(None, snap(app, only), registry)
    assert decision["ok"] is True and decision["descriptor"]["title"] == "Only"


def test_omitted_selector_with_one_inactive_document_is_412(registry, app):
    app.open_document("Only", "C:/Only.rvt")
    for active in (None, FakeApplication().open_document("Elsewhere", "")):
        decision = identity.decide_mutation_document(None, snap(app, active), registry)
        assert decision["ok"] is False
        assert decision["status"] == 412 and decision["code"] == "document-not-active"
        assert "document" not in decision


def test_omitted_selector_with_no_document_is_refused_503(registry, app):
    decision = identity.decide_mutation_document(None, snap(app), registry)
    assert decision["ok"] is False
    assert decision["status"] == 503 and decision["code"] == "no-open-document"
    assert decision["candidates"] == []


def test_omitted_selector_with_several_documents_refuses_and_lists_them(registry, app):
    first, second, tokens = two_open(registry, app, 1)
    decision = identity.decide_mutation_document(None, snap(app, second), registry)
    assert decision["ok"] is False and "document" not in decision
    assert decision["status"] == 400 and decision["code"] == "document-selector-required"
    # Even though one of them is active in the UI: the UI selection is not inferred.
    assert [c["document"] for c in decision["candidates"]] == tokens
    assert [c["active"] for c in decision["candidates"]] == [False, True]


def test_invalid_title_selector_is_400_and_never_matched_by_name(registry, app):
    first, second, tokens = two_open(registry, app, 0)
    decision = identity.decide_mutation_document("Project1", snap(app, first), registry)
    assert decision["ok"] is False
    assert decision["status"] == 400 and decision["code"] == "document-selector-invalid"


def test_unreadable_identity_refuses_the_default_too(registry, app, monkeypatch):
    first, second, tokens = two_open(registry, app, 0)

    def unreadable(self):
        raise InvalidObjectError("wrapper not accessible")

    with monkeypatch.context() as patched:
        patched.setattr(FakeDocument, "IsValidObject", property(unreadable))
        for selector in (None, tokens[0]):
            decision = identity.decide_mutation_document(selector, snap(app, first), registry)
            assert decision["ok"] is False and "document" not in decision
            assert decision["status"] == 503 and decision["code"] == "document-identity-unavailable"
    assert identity.decide_mutation_document(tokens[0], snap(app, first), registry)["ok"] is True


def test_active_state_that_cannot_be_compared_refuses_503(registry, app, monkeypatch):
    first, second, tokens = two_open(registry, app, 0)
    active = app.Documents[0]
    original = FakeDocument.Equals

    def selective(self, other):
        if other is active:
            raise InvalidObjectError("cannot compare")
        return original(self, other)

    with monkeypatch.context() as patched:
        patched.setattr(FakeDocument, "Equals", selective)
        decision = identity.decide_mutation_document(tokens[0], (app.Documents, active), registry)
        assert decision["ok"] is False
        assert decision["status"] == 503 and decision["code"] == "document-active-unknown"


def test_status_412_is_locked_to_the_inactive_case(registry, app):
    first, second, tokens = two_open(registry, app, 1)
    app.close_document(first)
    lone = snap(app, second)
    cases = [
        identity.decide_mutation_document("Project1", lone, registry),                 # invalid
        identity.decide_mutation_document(tokens[0], lone, registry),                   # closed
        identity.decide_mutation_document("doc1.{}.99".format(registry.generation), lone, registry),
        identity.decide_mutation_document("doc1.000000000000.1", lone, registry),       # stale
        identity.decide_mutation_document(tokens[1], snap(app, None), registry),        # inactive
        identity.decide_mutation_document(None, snap(app, None), registry),             # sole, inactive
        identity.decide_mutation_document(None, snap(FakeApplication()),
                                          identity.DocumentRegistry()),                 # none open
    ]
    assert all(case["ok"] is False for case in cases)
    for case in cases:
        assert (case["status"] == 412) == (case["code"] == "document-not-active"), case["code"]
    assert [case["code"] for case in cases].count("document-not-active") == 2


# --------------------------------------------------------- response builder


@pytest.fixture
def fake_routes(monkeypatch):
    made = []

    def make_response(data=None, status=200):
        made.append((data, status))
        return ("response", data, status)

    monkeypatch.setitem(sys.modules, "pyrevit",
                        types.SimpleNamespace(routes=types.SimpleNamespace(make_response=make_response)))
    return made


def test_guard_returns_document_and_descriptor_on_success(registry, app, fake_routes):
    only = app.open_document("Only", "C:/Only.rvt")
    document, descriptor, response = identity.mutation_document_or_response(
        None, snap(app, only), registry, identity=IDENT)
    assert response is None and document.Equals(only)
    assert descriptor["title"] == "Only" and fake_routes == []


def test_guard_rejection_is_a_response_naming_the_process_and_candidates(registry, app, fake_routes):
    first, second, tokens = two_open(registry, app, 1)
    document, descriptor, response = identity.mutation_document_or_response(
        tokens[0], snap(app, second), registry, identity=IDENT)
    assert document is None and descriptor is None
    assert response == ("response", fake_routes[0][0], 412)
    payload, status = fake_routes[0]
    assert status == 412
    assert payload["error_code"] == "document-not-active" and payload["error"]
    assert payload["process_identity"] == IDENT
    assert [c["document"] for c in payload["candidates"]] == tokens
    assert payload["active_document"] == tokens[1]


def test_guard_never_raises_when_revit_cannot_be_read(registry, fake_routes):
    def broken():
        raise RuntimeError("Application.Documents unavailable")

    document, descriptor, response = identity.mutation_document_or_response(
        None, None, registry, identity=IDENT, read_snapshot=broken)
    assert document is None and descriptor is None
    payload, status = fake_routes[0]
    assert status == 503 and payload["error_code"] == "document-registry-unavailable"
    assert "Application.Documents unavailable" in payload["error"]


def load_documents_route(monkeypatch, fake_routes):
    """Import revit_mcp/documents.py against a fake pyrevit and capture its handler."""
    import importlib

    monkeypatch.delitem(sys.modules, "revit_mcp.documents", raising=False)
    module = importlib.import_module("revit_mcp.documents")
    captured = {}

    class FakeApi(object):
        def route(self, path, methods=None):
            def register(fn):
                captured[(path, tuple(methods or ()))] = fn
                return fn
            return register

    module.register_documents_routes(FakeApi())
    monkeypatch.delitem(sys.modules, "revit_mcp.documents", raising=False)
    return captured[("/documents/", ("GET",))]


def test_documents_route_answers_an_empty_list_with_identity_and_status_200(monkeypatch, fake_routes):
    handler = load_documents_route(monkeypatch, fake_routes)
    monkeypatch.setattr(identity, "process_identity_or_error", lambda: (dict(IDENT), None))
    monkeypatch.setattr(identity, "current_document_descriptors", lambda: {
        "ok": True, "documents": [], "count": 0, "active_document": None})
    handler()
    payload, status = fake_routes[-1]
    assert status == 200 and payload["documents"] == [] and payload["count"] == 0
    assert payload["process_identity"] == IDENT and "error" not in payload


def test_documents_route_refusal_keeps_its_status_and_never_raises(monkeypatch, fake_routes):
    handler = load_documents_route(monkeypatch, fake_routes)
    monkeypatch.setattr(identity, "process_identity_or_error", lambda: (None, "no retained RoutesServer"))
    monkeypatch.setattr(identity, "current_document_descriptors", lambda: {
        "ok": False, "status": 503, "code": "document-identity-unavailable", "error": "cannot tell apart"})
    handler()
    payload, status = fake_routes[-1]
    assert status == 503 and payload["error_code"] == "document-identity-unavailable"
    assert payload["identity_error"] == "no retained RoutesServer" and "process_identity" not in payload

    def boom():
        raise RuntimeError("Revit exploded")

    monkeypatch.setattr(identity, "current_document_descriptors", boom)
    handler()
    payload, status = fake_routes[-1]
    assert status == 500 and payload["error"] == "Revit exploded"


def test_no_route_wrapper_or_decorator_is_installed_in_startup():
    with open(os.path.join(REPO_ROOT, "startup.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert "mutation_document_or_response" not in source
    assert "decide_mutation_document" not in source


# ===========================================================================
# 02-05 Task 1: explicit activation of one already-open saved document (D-12,
# the accepted G4 policy). Offline evidence only: a fake UIApplication records
# the one OpenAndActivateDocument(path) call; whether the production Routes
# handler behaves like the 02-20 ExternalEvent diagnostic is rechecked live in
# 02-07 after a full Revit restart (never pyRevit Reload).
# ===========================================================================

import ast

from revit_mcp import documents

ACTIVATION_FLAGS = ("IsDetached", "IsLinked", "IsFamilyDocument", "IsModelInCloud", "IsWorkshared")


class FlagDocument(FakeDocument):
    """A FakeDocument that also answers the Document flags the G4 gate reads.

    A flag value that is an Exception instance is raised, to model an unreadable flag.
    """

    def _flag(self, name):
        value = getattr(self._lifetime, "flags", {}).get(name, False)
        if isinstance(value, Exception):
            raise value
        return value

    IsDetached = property(lambda self: self._flag("IsDetached"))
    IsLinked = property(lambda self: self._flag("IsLinked"))
    IsFamilyDocument = property(lambda self: self._flag("IsFamilyDocument"))
    IsModelInCloud = property(lambda self: self._flag("IsModelInCloud"))
    IsWorkshared = property(lambda self: self._flag("IsWorkshared"))


class FlagApplication(FakeApplication):
    def open_document(self, title, path="", **flags):
        lifetime = FakeApplication.open_document(self, title, path)._lifetime
        lifetime.flags = flags
        return FlagDocument(lifetime, self._raises)

    @property
    def Documents(self):
        return [FlagDocument(lifetime, self._raises) for lifetime in self._open]


class FakeUIApp(object):
    """UIApplication double: records every activation call and moves the active
    document only in mode "activate"."""

    def __init__(self, app, active=None, mode="activate"):
        self.app = app
        self.active = active
        self.mode = mode
        self.calls = []

    @property
    def ActiveUIDocument(self):
        return None if self.active is None else types.SimpleNamespace(Document=self.active)

    def read_snapshot(self):
        active = self.ActiveUIDocument
        return self.app.Documents, (active.Document if active is not None else None)

    def OpenAndActivateDocument(self, *args):
        self.calls.append(args)
        if self.mode == "raise":
            raise RuntimeError("Revit refused the activation")
        matches = [d for d in self.app.Documents if d.PathName == args[0]]
        if self.mode == "noop":
            # Returns a UIDocument for the target without ever making it active.
            return types.SimpleNamespace(Document=matches[0]) if matches else None
        self.active = matches[0]
        return types.SimpleNamespace(Document=matches[0])


def exists_everywhere(path):
    return True


def exists_nowhere(path):
    return False


def rig(mode="activate", **options):
    """Two saved projects, OTHER active, COORD not: (app, uiapp, registry, tokens, docs)."""
    app = FlagApplication()
    other = app.open_document("OTHER", "C:/Models/OTHER.rvt")
    coord = app.open_document("COORD", "C:/Models/COORD.rvt", **options)
    uiapp = FakeUIApp(app, other, mode)
    reg = identity.DocumentRegistry()
    tokens = tokens_of(identity.current_document_descriptors(uiapp.read_snapshot(), reg))
    return app, uiapp, reg, {"other": tokens[0], "coord": tokens[1]}, {"other": other, "coord": coord}


def activate(uiapp, reg, selector, file_exists=exists_everywhere):
    return documents.run_activation(selector, uiapp, read_snapshot=uiapp.read_snapshot,
                                    registry=reg, file_exists=file_exists)


# ---------------------------------------------------------------- allow branch


def test_saved_project_with_an_existing_path_is_activated_with_its_own_path_once():
    app, uiapp, reg, tokens, docs = rig()
    decoy = app.open_document("COORD", "C:/Models/Elsewhere/COORD.rvt")   # same title, other file
    status, payload = activate(uiapp, reg, tokens["coord"])
    assert status == 200
    assert uiapp.calls == [("C:/Models/COORD.rvt",)]
    assert payload["activation"] == "activated"
    assert payload["observed_active_document"]["document"] == tokens["coord"]
    assert payload["observed_active_document"]["active"] is True
    assert uiapp.active.Equals(docs["coord"]) and not uiapp.active.Equals(decoy)


def test_already_active_document_is_a_success_without_any_api_call():
    app, uiapp, reg, tokens, docs = rig()
    status, payload = activate(uiapp, reg, tokens["other"])
    assert status == 200 and uiapp.calls == []
    assert payload["activation"] == "already-active"
    assert payload["observed_active_document"]["document"] == tokens["other"]


def test_activation_is_idempotent():
    app, uiapp, reg, tokens, docs = rig()
    first = activate(uiapp, reg, tokens["coord"])
    second = activate(uiapp, reg, tokens["coord"])
    assert first[0] == 200 and second[0] == 200
    assert len(uiapp.calls) == 1
    assert second[1]["activation"] == "already-active"


# ------------------------------------------------------------ the G4 gate order


def reason_of(**flags):
    app = FlagApplication()
    path = flags.pop("path", "C:/Models/M.rvt")
    exists = flags.pop("exists", True)
    document = app.open_document("M", path, **flags)
    return documents.activation_refusal_reason(
        document, file_exists=exists_everywhere if exists else exists_nowhere)


def test_a_saved_non_workshared_project_with_an_existing_file_has_no_refusal():
    assert reason_of() is None


@pytest.mark.parametrize("flags,expected", [
    (dict(path=""), "unsaved"),
    (dict(IsDetached=True), "detached"),
    (dict(path="BIM360://Acme/Project.rvt", exists=False), "no-usable-file-path"),
    (dict(IsLinked=True), "linked-unsupported"),
    (dict(IsFamilyDocument=True), "family-unmeasured"),
    (dict(IsModelInCloud=True), "cloud-unmeasured"),
    (dict(IsWorkshared=True), "workshared-unmeasured"),
])
def test_each_unsupported_class_has_its_own_named_reason(flags, expected):
    assert reason_of(**flags) == expected


def test_refusal_order_is_fixed_when_several_things_are_true():
    everything = dict(IsDetached=True, IsLinked=True, IsFamilyDocument=True,
                      IsModelInCloud=True, IsWorkshared=True)
    assert reason_of(path="", exists=False, **everything) == "unsaved"
    assert reason_of(exists=False, **everything) == "detached"
    remaining = dict(everything)
    del remaining["IsDetached"]
    assert reason_of(exists=False, **remaining) == "no-usable-file-path"
    for expected, flag in (("linked-unsupported", "IsLinked"),
                           ("family-unmeasured", "IsFamilyDocument"),
                           ("cloud-unmeasured", "IsModelInCloud"),
                           ("workshared-unmeasured", "IsWorkshared")):
        assert reason_of(**remaining) == expected
        del remaining[flag]
    assert reason_of(**remaining) is None


def test_saved_workshared_model_with_an_existing_path_is_still_refused():
    assert reason_of(IsWorkshared=True, path="C:/Models/Central.rvt", exists=True) == "workshared-unmeasured"


@pytest.mark.parametrize("flag", ACTIVATION_FLAGS)
def test_an_unreadable_flag_fails_closed(flag):
    assert reason_of(**{flag: RuntimeError("cannot read")}) == "eligibility-unreadable"


def test_a_file_existence_check_that_raises_is_not_a_usable_path():
    app = FlagApplication()
    document = app.open_document("M", "C:/Models/M.rvt")

    def broken(path):
        raise OSError("bad path")

    assert documents.activation_refusal_reason(document, file_exists=broken) == "no-usable-file-path"


@pytest.mark.parametrize("flags,file_exists,reason", [
    (dict(), exists_everywhere, None),    # control: the same rig activates
    (dict(IsDetached=True), exists_everywhere, "detached"),
    (dict(IsFamilyDocument=True), exists_everywhere, "family-unmeasured"),
    (dict(IsModelInCloud=True), exists_everywhere, "cloud-unmeasured"),
    (dict(IsWorkshared=True), exists_everywhere, "workshared-unmeasured"),
    (dict(), exists_nowhere, "no-usable-file-path"),
])
def test_ineligible_documents_answer_422_with_zero_api_calls(flags, file_exists, reason):
    app, uiapp, reg, tokens, docs = rig(**flags)
    status, payload = activate(uiapp, reg, tokens["coord"], file_exists)
    if reason is None:
        assert status == 200 and len(uiapp.calls) == 1
        return
    assert status == 422 and uiapp.calls == []
    assert payload["error"] and payload["reason"] == reason and payload["error_code"] == reason
    assert payload["observed_active_document"]["document"] == tokens["other"]
    assert uiapp.active.Equals(docs["other"])


def test_unsaved_document_answers_422_unsaved_with_zero_api_calls():
    app = FlagApplication()
    active = app.open_document("OTHER", "C:/Models/OTHER.rvt")
    app.open_document("Project1", "")
    uiapp = FakeUIApp(app, active)
    reg = identity.DocumentRegistry()
    tokens = tokens_of(identity.current_document_descriptors(uiapp.read_snapshot(), reg))
    status, payload = activate(uiapp, reg, tokens[1])
    assert status == 422 and payload["reason"] == "unsaved" and uiapp.calls == []


def test_every_refusal_reason_has_a_message():
    for code in documents.ACTIVATION_REFUSALS:
        assert documents.ACTIVATION_REFUSALS[code].strip()
    assert set(documents.ACTIVATION_REFUSALS) == {
        "unsaved", "detached", "no-usable-file-path", "linked-unsupported", "family-unmeasured",
        "cloud-unmeasured", "workshared-unmeasured", "eligibility-unreadable"}


# ---------------------------------------------------------- token refusals


def test_closed_token_never_activates_another_document():
    app, uiapp, reg, tokens, docs = rig()
    app.close_document(docs["coord"])
    status, payload = activate(uiapp, reg, tokens["coord"])
    assert status == 404 and payload["error_code"] == "document-closed" and payload["error"]
    assert uiapp.calls == [] and uiapp.active.Equals(docs["other"])


def test_unknown_stale_and_malformed_tokens_refuse_with_zero_calls():
    app, uiapp, reg, tokens, docs = rig()
    cases = [
        ("doc1.{}.99".format(reg.generation), 404, "document-token-unknown"),
        ("doc1.000000000000.1", 404, "document-token-stale"),
        ("COORD", 400, "document-selector-invalid"),
        ("C:/Models/COORD.rvt", 400, "document-selector-invalid"),
        (7, 400, "document-selector-invalid"),
    ]
    for selector, status_code, code in cases:
        status, payload = activate(uiapp, reg, selector)
        assert (status, payload["error_code"]) == (status_code, code), selector
    assert uiapp.calls == []


def test_replacement_with_identical_title_and_path_does_not_inherit_the_old_token():
    app, uiapp, reg, tokens, docs = rig()
    app.close_document(docs["coord"])
    app.open_document("COORD", "C:/Models/COORD.rvt")
    status, payload = activate(uiapp, reg, tokens["coord"])
    assert status == 404 and payload["error_code"] == "document-closed"
    assert uiapp.calls == []


def test_ambiguous_lifetime_refuses_and_never_activates():
    app, uiapp, reg, tokens, docs = rig()
    single = uiapp.read_snapshot

    def doubled():
        documents_now, active = single()
        return documents_now + documents_now[1:], active

    status, payload = documents.run_activation(
        tokens["coord"], uiapp, read_snapshot=doubled, registry=reg, file_exists=exists_everywhere)
    assert status == 400 and payload["error_code"] == "document-identity-ambiguous"
    assert uiapp.calls == []


def test_omitted_document_refuses_and_never_picks_a_default():
    app, uiapp, reg, tokens, docs = rig()
    status, payload = activate(uiapp, reg, None)
    assert status == 400 and payload["error_code"] == "document-selector-required"
    assert [c["document"] for c in payload["candidates"]] == [tokens["other"], tokens["coord"]]
    assert uiapp.calls == []
    # Even with a single, inactive document open: no default is chosen.
    solo = FlagApplication()
    solo.open_document("ONLY", "C:/Models/ONLY.rvt")
    solo_ui = FakeUIApp(solo, None)
    status, payload = documents.run_activation(
        None, solo_ui, read_snapshot=solo_ui.read_snapshot, registry=identity.DocumentRegistry(),
        file_exists=exists_everywhere)
    assert status == 400 and solo_ui.calls == []


def test_a_call_that_does_not_make_the_target_active_is_not_reported_as_activated():
    app, uiapp, reg, tokens, docs = rig(mode="noop")
    status, payload = activate(uiapp, reg, tokens["coord"])
    assert status == 409 and len(uiapp.calls) == 1
    assert payload["error"] and payload["error_code"] == "document-not-activated"
    assert payload.get("activation") != "activated"
    assert payload["observed_active_document"]["document"] == tokens["other"]


# ----------------------------------------------------------------- the route


def activate_handlers(monkeypatch, fake_routes, uiapp, registry, identity_value=None):
    """Register revit_mcp/documents.py against a fake pyrevit; return its handlers by (path, methods)."""
    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=sys.modules["pyrevit"].routes,
        HOST_APP=types.SimpleNamespace(uiapp=uiapp, app=uiapp.app)))
    monkeypatch.setattr(identity, "get_document_registry", lambda store=None: registry)
    if identity_value == "none":
        monkeypatch.setattr(identity, "process_identity_or_error",
                            lambda: (None, "no retained RoutesServer"))
    else:
        monkeypatch.setattr(identity, "process_identity_or_error",
                            lambda: (dict(identity_value or IDENT), None))
    monkeypatch.setattr(documents, "_file_exists", exists_everywhere)
    captured = {}

    class FakeApi(object):
        def route(self, path, methods=None):
            def register(fn):
                captured[(path, tuple(methods or ()))] = fn
                return fn
            return register

    documents.register_documents_routes(FakeApi())
    return captured


class FakeRequest(object):
    def __init__(self, body):
        self.data = body


def test_the_route_is_registered_as_a_post_handler_taking_only_the_request(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = rig()
    captured = activate_handlers(monkeypatch, fake_routes, uiapp, reg)
    handler = captured[("/activate_document/", ("POST",))]
    assert list(inspect.signature(handler).parameters) == ["request"]
    assert ("/documents/", ("GET",)) in captured


def test_route_activates_from_a_text_plain_bytes_body_and_names_the_process(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = rig()
    handler = activate_handlers(monkeypatch, fake_routes, uiapp, reg)[("/activate_document/", ("POST",))]
    body = ('{"document": "%s"}' % tokens["coord"]).encode("utf-8")
    handler(FakeRequest(body))
    payload, status = fake_routes[-1]
    assert status == 200 and payload["activation"] == "activated"
    assert payload["process_identity"] == IDENT
    assert payload["observed_active_document"]["document"] == tokens["coord"]
    assert uiapp.calls == [("C:/Models/COORD.rvt",)]


def test_route_refusal_keeps_process_and_observed_active_identity(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = rig(IsWorkshared=True)
    handler = activate_handlers(monkeypatch, fake_routes, uiapp, reg)[("/activate_document/", ("POST",))]
    handler(FakeRequest({"document": tokens["coord"]}))     # a dict body is accepted too
    payload, status = fake_routes[-1]
    assert status == 422 and payload["reason"] == "workshared-unmeasured" and payload["error"]
    assert payload["process_identity"] == IDENT
    assert payload["observed_active_document"]["document"] == tokens["other"]
    assert uiapp.calls == []


def test_route_without_a_document_or_with_a_bad_body_is_a_400_not_an_exception(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = rig()
    handler = activate_handlers(monkeypatch, fake_routes, uiapp, reg)[("/activate_document/", ("POST",))]
    for body in (None, b"", b"{}", b"not json", b"[1, 2]"):
        handler(FakeRequest(body))
        payload, status = fake_routes[-1]
        assert status == 400 and payload["error"], body
        assert payload["process_identity"] == IDENT
    assert uiapp.calls == []


def test_route_without_process_identity_says_so_instead_of_inventing_one(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = rig()
    handler = activate_handlers(monkeypatch, fake_routes, uiapp, reg, identity_value="none")[
        ("/activate_document/", ("POST",))]
    handler(FakeRequest({"document": tokens["other"]}))
    payload, status = fake_routes[-1]
    assert status == 200 and "process_identity" not in payload
    assert payload["identity_error"] == "no retained RoutesServer"


# ------------------------------------------------------------------ the tool


def run_activate_tool(response, **kwargs):
    from tools.document_tools import register_document_tools

    calls = []

    async def revit_get(*args, **options):  # pragma: no cover - never called
        raise AssertionError("activate_document must not GET")

    async def revit_post(path, data, ctx=None, **options):
        calls.append((path, data, options))
        return response

    mcp = FakeMCP()
    register_document_tools(mcp, revit_get, revit_post)
    return asyncio.run(mcp.tools["activate_document"](**kwargs)), calls


def activation_reply(kind="activated"):
    descriptor = {"document": "doc1.aaaaaaaaaaaa.2", "title": "COORD", "path": "C:/M/COORD.rvt",
                  "active": True, "saved": True}
    return {"status": "success", "activation": kind, "process_identity": dict(IDENT),
            "document": descriptor, "observed_active_document": descriptor,
            "message": "ignored by the tool"}


def test_activate_document_tool_posts_the_token_and_target_and_renders_the_observed_state():
    text, calls = run_activate_tool(activation_reply(), document="doc1.aaaaaaaaaaaa.2", target="revit1:xyz")
    assert calls == [("/activate_document/", {"document": "doc1.aaaaaaaaaaaa.2"}, {"target": "revit1:xyz"})]
    assert "activated" in text.lower() and "COORD" in text and "doc1.aaaaaaaaaaaa.2" in text
    assert "PID 4242" in text and "48885" in text and "tok-abc" in text


def test_activate_document_tool_says_when_nothing_was_activated():
    text, _ = run_activate_tool(activation_reply("already-active"), document="doc1.aaaaaaaaaaaa.2")
    assert "already" in text.lower() and "no activation call" in text.lower()


def test_activate_document_tool_passes_refusals_through():
    refusal = 'Error: 422 - {"error": "no", "reason": "workshared-unmeasured"}'
    text, calls = run_activate_tool(refusal, document="doc1.aaaaaaaaaaaa.2")
    assert "workshared-unmeasured" in text and "Activated" not in text
    assert len(calls) == 1


def test_activate_document_tool_refuses_a_missing_document_without_posting():
    for bad in ("", "   ", None):
        text, calls = run_activate_tool({"status": "success"}, document=bad)
        assert calls == [] and "document" in text.lower() and "list_documents" in text


def test_activate_document_signature_and_docstring_are_the_api_contract():
    from tools.document_tools import register_document_tools

    mcp = FakeMCP()
    register_document_tools(mcp, None, None)
    function = mcp.tools["activate_document"]
    names = list(inspect.signature(function).parameters)
    assert names == ["document", "target", "ctx"]
    assert inspect.signature(function).parameters["document"].default is inspect.Parameter.empty
    doc = function.__doc__
    for name in names:
        assert name + ":" in doc, "docstring Args must name {}".format(name)
    for code in documents.ACTIVATION_REFUSALS:
        assert code in doc, "docstring must state refusal {}".format(code)
    lowered = doc.lower()
    assert "OpenAndActivateDocument" not in doc    # the model needs the contract, not the API
    assert "never activate" in lowered or "does not activate" in lowered
    assert "refused" in lowered and "list_documents" in doc


def test_activate_document_is_in_the_tool_manifest():
    manifest = os.path.join(REPO_ROOT, "tests", "unit", "tool_manifest.txt")
    with open(manifest, encoding="utf-8") as handle:
        assert "activate_document" in handle.read().split()


# ------------------------------------------------------------- AST call scan

FORBIDDEN_CALLS = re.compile(r"^(Save|SaveAs|SaveAndClose|Close|Open\w*|Synchronize\w*|Reload\w*|Detach\w*)$")


def callee_names(tree):
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                names.append(func.attr)
            elif isinstance(func, ast.Name):
                names.append(func.id)
    return names


def function_node(name):
    with open(os.path.join(REPO_ROOT, "revit_mcp", "documents.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("no function " + name)


def test_run_activation_has_exactly_one_activation_call_and_no_save_or_open_call():
    names = callee_names(function_node("run_activation"))
    assert names.count("OpenAndActivateDocument") == 1
    others = [n for n in names if n != "OpenAndActivateDocument" and FORBIDDEN_CALLS.match(n)]
    assert others == [], others


# ===========================================================================
# 02-05 Task 2: activation failure paths and the route return contract.
#
# An exception from OpenAndActivateDocument, a call that returns without the
# target becoming active, and an unreadable re-read are all non-200 and name the
# attempted document and the OBSERVED active document. Only an observed Equals
# match is ever described as activated. Nothing is retried with another path,
# a save, a reopen or a worksharing option.
# ===========================================================================


class ActivateThenRaiseUIApp(FakeUIApp):
    """Activates, then raises: the exception must still never be reported as success."""

    def OpenAndActivateDocument(self, *args):
        FakeUIApp.OpenAndActivateDocument(self, *args)
        raise RuntimeError("exception after the switch")


def failing_read_after(uiapp, allowed):
    """A snapshot reader that works for ``allowed`` reads and then raises."""
    state = {"reads": 0}

    def read():
        state["reads"] += 1
        if state["reads"] > allowed:
            raise RuntimeError("Application.Documents unavailable")
        return uiapp.read_snapshot()

    return read


def test_api_exception_is_a_named_500_that_names_both_documents_and_is_never_retried():
    app, uiapp, reg, tokens, docs = rig(mode="raise")
    status, payload = activate(uiapp, reg, tokens["coord"])
    assert status == 500 and len(uiapp.calls) == 1
    assert payload["error_code"] == "activation-failed" and payload["reason"] == "activation-failed"
    assert "Revit refused the activation" in payload["error"]
    assert tokens["coord"] in payload["error"] and "COORD" in payload["error"]
    assert payload["document"]["document"] == tokens["coord"]
    assert payload["observed_active_document"]["document"] == tokens["other"]
    assert payload.get("activation") != "activated"
    assert uiapp.calls == [("C:/Models/COORD.rvt",)]       # the one call, with the target's own path


def test_an_exception_after_the_switch_is_still_a_failure_never_success():
    app = FlagApplication()
    other = app.open_document("OTHER", "C:/Models/OTHER.rvt")
    coord = app.open_document("COORD", "C:/Models/COORD.rvt")
    uiapp = ActivateThenRaiseUIApp(app, other)
    reg = identity.DocumentRegistry()
    tokens = tokens_of(identity.current_document_descriptors(uiapp.read_snapshot(), reg))
    status, payload = activate(uiapp, reg, tokens[1])
    assert status == 500 and payload["error_code"] == "activation-failed"
    assert payload["observed_active_document"]["document"] == tokens[1]    # reported as observed, not as success
    assert payload.get("activation") != "activated" and len(uiapp.calls) == 1
    assert uiapp.active.Equals(coord)


def test_an_unreadable_re_read_after_the_call_is_unverified_not_activated():
    app, uiapp, reg, tokens, docs = rig()
    status, payload = documents.run_activation(
        tokens["coord"], uiapp, read_snapshot=failing_read_after(uiapp, 1), registry=reg,
        file_exists=exists_everywhere)
    assert status == 500 and len(uiapp.calls) == 1
    assert payload["error_code"] == "activation-unverified" and payload["error"]
    assert payload.get("activation") != "activated"
    assert payload["observed_active_document"] is None
    assert "Application.Documents unavailable" in payload["observed_active_error"]


def test_run_activation_never_raises_when_revit_cannot_be_read():
    app, uiapp, reg, tokens, docs = rig()
    status, payload = documents.run_activation(
        tokens["coord"], uiapp, read_snapshot=failing_read_after(uiapp, 0), registry=reg,
        file_exists=exists_everywhere)
    assert status == 503 and payload["error_code"] == "document-registry-unavailable"
    assert "Application.Documents unavailable" in payload["error"] and uiapp.calls == []


def test_run_activation_never_raises_when_the_uiapplication_is_missing():
    app, uiapp, reg, tokens, docs = rig()
    status, payload = documents.run_activation(
        tokens["coord"], None, read_snapshot=uiapp.read_snapshot, registry=reg,
        file_exists=exists_everywhere)
    assert status == 500 and payload["error_code"] == "activation-failed"
    assert payload["observed_active_document"]["document"] == tokens["other"]


def test_route_exception_reply_keeps_process_and_observed_active_identity(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = rig(mode="raise")
    handler = activate_handlers(monkeypatch, fake_routes, uiapp, reg)[("/activate_document/", ("POST",))]
    handler(FakeRequest({"document": tokens["coord"]}))
    payload, status = fake_routes[-1]
    assert status == 500 and payload["error"] and payload["error_code"] == "activation-failed"
    assert payload["process_identity"] == IDENT
    assert payload["observed_active_document"]["document"] == tokens["other"]
    assert len(uiapp.calls) == 1


def test_route_no_change_reply_keeps_process_and_observed_active_identity(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = rig(mode="noop")
    handler = activate_handlers(monkeypatch, fake_routes, uiapp, reg)[("/activate_document/", ("POST",))]
    handler(FakeRequest({"document": tokens["coord"]}))
    payload, status = fake_routes[-1]
    assert status == 409 and payload["error"] and payload["error_code"] == "document-not-activated"
    assert payload["process_identity"] == IDENT
    assert payload["observed_active_document"]["document"] == tokens["other"]


def test_route_never_raises_and_always_names_the_process(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = rig()
    handlers = activate_handlers(monkeypatch, fake_routes, uiapp, reg)
    handler = handlers[("/activate_document/", ("POST",))]

    class BrokenUIApp(object):
        app = uiapp.app

        @property
        def ActiveUIDocument(self):
            raise RuntimeError("UI unavailable")

    monkeypatch.setattr(sys.modules["pyrevit"], "HOST_APP",
                        types.SimpleNamespace(uiapp=BrokenUIApp(), app=uiapp.app))
    handler(FakeRequest({"document": tokens["coord"]}))
    payload, status = fake_routes[-1]
    assert status >= 500 and payload["error"] and payload["process_identity"] == IDENT

    class NoUIApp(object):
        @property
        def uiapp(self):
            raise RuntimeError("no UIApplication")

    monkeypatch.setattr(sys.modules["pyrevit"], "HOST_APP", NoUIApp())
    handler(FakeRequest({"document": tokens["coord"]}))
    payload, status = fake_routes[-1]
    assert status == 500 and payload["error_code"] == "activation-error"
    assert payload["process_identity"] == IDENT
    assert uiapp.calls == []


# --------------------------------------------------- AST scan of the whole file


def documents_tree():
    with open(os.path.join(REPO_ROOT, "revit_mcp", "documents.py"), encoding="utf-8") as handle:
        return ast.parse(handle.read())


FORBIDDEN_IDENTIFIERS = {
    "Transaction", "TransactionGroup", "SubTransaction", "ExternalEvent", "IExternalEventHandler",
    "Idling", "Thread", "Timer", "SaveAs", "SaveAsOptions", "OpenOptions", "OpenDocumentFile",
    "WorksetConfiguration", "ModelPathUtils", "ModelPath", "SynchronizeWithCentral",
}


def test_documents_py_has_exactly_one_activation_call_site_and_no_save_open_or_event_machinery():
    tree = documents_tree()
    names = callee_names(tree)
    assert names.count("OpenAndActivateDocument") == 1
    assert [n for n in names if n != "OpenAndActivateDocument" and FORBIDDEN_CALLS.match(n)] == []
    identifiers = set()
    for node in ast.walk(tree):          # code only: comments and docstrings are not nodes here
        if isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            identifiers.update(alias.name.split(".")[-1] for alias in node.names)
    assert identifiers & FORBIDDEN_IDENTIFIERS == set()


def test_the_activation_call_takes_one_positional_path_read_from_the_target_own_pathname():
    function = function_node("run_activation")
    calls = [n for n in ast.walk(function) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "OpenAndActivateDocument"]
    assert len(calls) == 1
    call = calls[0]
    assert call.keywords == [] and len(call.args) == 1
    assert isinstance(call.args[0], ast.Name) and call.args[0].id == "path"
    assigned = [n for n in ast.walk(function) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "path" for t in n.targets)]
    assert len(assigned) == 1
    value = assigned[0].value
    assert isinstance(value, ast.Attribute) and value.attr == "PathName"
    assert isinstance(value.value, ast.Name) and value.value.id == "document"


# ===========================================================================
# 02-06 Task 1: read the summary of the explicitly selected document (D-11, the
# accepted G3 document-only-path). Offline evidence only: a fake DB records the
# Document every collector is built on. Whether the production route preserves the
# UI focus on live Revit is NOT proved here; 02-07 rechecks it after a full Revit
# restart (never pyRevit Reload).
# ===========================================================================


class FakeLevel(object):
    """A Level element: a raising Elevation models an unreadable one."""

    def __init__(self, name, elevation, ident):
        self.Name = name
        self._elevation = elevation
        self.Id = ident

    @property
    def Elevation(self):
        if isinstance(self._elevation, Exception):
            raise self._elevation
        return self._elevation


class FakeInfo(object):
    """ProjectInfo: a value that is an Exception instance is raised when read."""

    def __init__(self, values):
        self._values = values

    def __getattr__(self, name):
        values = self.__dict__.get("_values", {})
        if name not in values:
            raise AttributeError(name)
        value = values[name]
        if isinstance(value, Exception):
            raise value
        return value


class ModelDocument(FlagDocument):
    """A document that also holds model data: elements, levels and project information."""

    @property
    def ProjectInformation(self):
        info = self._lifetime.info
        if isinstance(info, Exception):
            raise info
        return FakeInfo(info)

    @property
    def model(self):
        return self._lifetime.model


class ModelApplication(FlagApplication):
    def open_model(self, title, path, elements, levels, info=None, **flags):
        lifetime = FlagApplication.open_document(self, title, path, **flags)._lifetime
        lifetime.model = {"elements": list(range(elements)), "levels": levels}
        lifetime.info = {"Name": title + " project", "Number": "N-" + title, "ClientName": "Client " + title,
                         "Status": "Design"} if info is None else info
        return ModelDocument(lifetime, self._raises)

    @property
    def Documents(self):
        return [ModelDocument(lifetime, self._raises) for lifetime in self._open]


class FakeBuiltInCategory(object):
    OST_Levels = "OST_Levels"


class FakeCollector(object):
    def __init__(self, document):
        self._document = document
        self._category = None
        self._types_excluded = False

    def OfCategory(self, category):
        self._category = category
        return self

    def WhereElementIsNotElementType(self):
        self._types_excluded = True
        return self

    def _elements(self):
        assert self._types_excluded, "only non-type elements are collected"
        if self._category == FakeBuiltInCategory.OST_Levels:
            return self._document.model["levels"]
        assert self._category is None
        return self._document.model["elements"]

    def GetElementCount(self):
        return len(self._elements())

    def ToElements(self):
        return list(self._elements())


class FakeDB(object):
    """The DB namespace: records the Document every collector is built on."""

    BuiltInCategory = FakeBuiltInCategory

    def __init__(self, on_collect=None, raises=None):
        self.collected = []
        self._on_collect = on_collect
        self._raises = raises

    def FilteredElementCollector(self, document):
        self.collected.append(document)
        if self._raises is not None:
            raise self._raises
        if self._on_collect is not None:
            self._on_collect(document)
        return FakeCollector(document)


def read_rig(mode="activate"):
    """OTHER (3 elements, 1 level) is active; COORD (10 elements, 2 levels) is open, not active."""
    app = ModelApplication()
    other = app.open_model("OTHER", "C:/Models/OTHER.rvt", 3, [FakeLevel("OTHER L1", 0.0, 11)])
    coord = app.open_model("COORD", "C:/Models/COORD.rvt", 10,
                           [FakeLevel("COORD L2", 10.0, 22), FakeLevel("COORD L1", 0.0, 21)],
                           info={"Name": "Coordination", "Number": "B-200", "ClientName": "Client B",
                                 "Status": "Design"})
    uiapp = FakeUIApp(app, other, mode)
    reg = identity.DocumentRegistry()
    tokens = tokens_of(identity.current_document_descriptors(uiapp.read_snapshot(), reg))
    return app, uiapp, reg, {"a": tokens[0], "b": tokens[1]}, {"a": other, "b": coord}


def read_summary(uiapp, reg, selector, db, read_snapshot=None):
    return documents.run_document_summary(
        selector, read_snapshot=read_snapshot or uiapp.read_snapshot, registry=reg, db=db)


def only_from(db, document, other):
    return (bool(db.collected) and all(d.Equals(document) for d in db.collected)
            and not any(d.Equals(other) for d in db.collected))


# -------------------------------------------------------------- the read itself


def test_summary_of_an_inactive_document_is_read_from_that_document_only():
    app, uiapp, reg, tokens, docs = read_rig()
    db = FakeDB()
    status, payload = read_summary(uiapp, reg, tokens["b"], db)
    assert status == 200 and payload["status"] == "success"
    summary = payload["summary"]
    assert summary["title"] == "COORD" and summary["path"] == "C:/Models/COORD.rvt"
    assert summary["non_type_element_count"] == 10 and summary["level_count"] == 2
    assert summary["project_information"] == {
        "name": "Coordination", "number": "B-200", "client": "Client B", "status": "Design"}
    assert summary["unreadable_fields"] == []
    assert payload["document"]["document"] == tokens["b"] and payload["document"]["active"] is False
    assert only_from(db, docs["b"], docs["a"])
    assert uiapp.calls == []                       # nothing was activated


def test_summary_reports_the_active_flag_and_the_before_and_after_diagnostics():
    app, uiapp, reg, tokens, docs = read_rig()
    status, payload = read_summary(uiapp, reg, tokens["b"], FakeDB())
    assert payload["target_is_active"] is False and payload["ui_switched"] is False
    assert payload["active_before"] == tokens["a"] == payload["active_after"]
    assert uiapp.active.Equals(docs["a"])
    status, payload = read_summary(uiapp, reg, tokens["a"], FakeDB())
    assert status == 200 and payload["target_is_active"] is True and payload["ui_switched"] is False
    assert payload["summary"]["title"] == "OTHER" and payload["summary"]["non_type_element_count"] == 3


def test_a_switch_of_the_active_document_during_the_read_is_reported_not_hidden():
    app, uiapp, reg, tokens, docs = read_rig()
    db = FakeDB(on_collect=lambda document: setattr(uiapp, "active", docs["b"]))
    status, payload = read_summary(uiapp, reg, tokens["b"], db)
    assert status == 200 and payload["summary"]["title"] == "COORD"
    assert payload["ui_switched"] is True
    assert payload["active_before"] == tokens["a"] and payload["active_after"] == tokens["b"]


def test_an_unreadable_after_state_leaves_the_switch_unknown_not_false():
    app, uiapp, reg, tokens, docs = read_rig()
    status, payload = read_summary(uiapp, reg, tokens["b"], FakeDB(),
                                   read_snapshot=failing_read_after(uiapp, 1))
    assert status == 200 and payload["summary"]["title"] == "COORD"
    assert payload["ui_switched"] is None and payload["active_after"] is None
    assert "Application.Documents unavailable" in payload["active_after_error"]


def test_project_information_fields_that_cannot_be_read_are_omitted_and_named():
    app = ModelApplication()
    other = app.open_model("OTHER", "C:/Models/OTHER.rvt", 3, [])
    app.open_model("COORD", "C:/Models/COORD.rvt", 10, [],
                   info={"Name": "Coordination", "Number": RuntimeError("no number"),
                         "ClientName": "Client B"})   # Status is absent altogether
    uiapp = FakeUIApp(app, other)
    reg = identity.DocumentRegistry()
    tokens = tokens_of(identity.current_document_descriptors(uiapp.read_snapshot(), reg))
    status, payload = read_summary(uiapp, reg, tokens[1], FakeDB())
    summary = payload["summary"]
    assert status == 200
    assert summary["project_information"] == {"name": "Coordination", "client": "Client B"}
    assert sorted(summary["unreadable_fields"]) == ["project_information.number", "project_information.status"]
    assert summary["non_type_element_count"] == 10      # the measured fields do not depend on it


def test_unreadable_project_information_never_borrows_another_documents_values():
    app = ModelApplication()
    other = app.open_model("OTHER", "C:/Models/OTHER.rvt", 3, [])
    app.open_model("COORD", "C:/Models/COORD.rvt", 10, [], info=RuntimeError("no ProjectInformation"))
    uiapp = FakeUIApp(app, other)
    reg = identity.DocumentRegistry()
    tokens = tokens_of(identity.current_document_descriptors(uiapp.read_snapshot(), reg))
    status, payload = read_summary(uiapp, reg, tokens[1], FakeDB())
    assert status == 200 and payload["summary"]["project_information"] == {}
    assert payload["summary"]["unreadable_fields"] == ["project_information"]
    assert "OTHER" not in str(payload["summary"])


# ------------------------------------------------------------------- refusals


def test_a_closed_token_is_refused_by_name_even_for_an_addressed_read():
    app, uiapp, reg, tokens, docs = read_rig()
    app.close_document(docs["b"])
    db = FakeDB()
    status, payload = read_summary(uiapp, reg, tokens["b"], db)
    assert status == 404 and payload["error_code"] == "document-closed" and payload["error"]
    assert db.collected == []
    assert "summary" not in payload and "document" not in payload   # never relabeled as other data


def test_a_replacement_with_the_same_title_and_path_does_not_inherit_the_token():
    app, uiapp, reg, tokens, docs = read_rig()
    app.close_document(docs["b"])
    app.open_model("COORD", "C:/Models/COORD.rvt", 99, [])
    db = FakeDB()
    status, payload = read_summary(uiapp, reg, tokens["b"], db)
    assert status == 404 and payload["error_code"] == "document-closed"
    assert db.collected == [] and "summary" not in payload


def test_unknown_stale_malformed_and_omitted_selectors_refuse_without_collecting():
    app, uiapp, reg, tokens, docs = read_rig()
    db = FakeDB()
    cases = [
        ("doc1.{}.99".format(reg.generation), 404, "document-token-unknown"),
        ("doc1.000000000000.1", 404, "document-token-stale"),
        ("COORD", 400, "document-selector-invalid"),
        ("C:/Models/COORD.rvt", 400, "document-selector-invalid"),
        (7, 400, "document-selector-invalid"),
        (None, 400, "document-selector-required"),
    ]
    for selector, status_code, code in cases:
        status, payload = read_summary(uiapp, reg, selector, db)
        assert (status, payload["error_code"]) == (status_code, code), selector
        assert "summary" not in payload
    assert db.collected == []
    status, payload = read_summary(uiapp, reg, None, db)
    assert [c["document"] for c in payload["candidates"]] == [tokens["a"], tokens["b"]]


def test_an_ambiguous_lifetime_refuses_and_collects_nothing():
    app, uiapp, reg, tokens, docs = read_rig()
    single = uiapp.read_snapshot

    def doubled():
        documents_now, active = single()
        return documents_now + documents_now[1:], active

    db = FakeDB()
    status, payload = read_summary(uiapp, reg, tokens["b"], db, read_snapshot=doubled)
    assert status == 400 and payload["error_code"] == "document-identity-ambiguous"
    assert db.collected == [] and "summary" not in payload


def test_an_unreadable_open_document_list_is_a_503_that_never_raises():
    app, uiapp, reg, tokens, docs = read_rig()

    def broken():
        raise RuntimeError("Application.Documents unavailable")

    db = FakeDB()
    status, payload = read_summary(uiapp, reg, tokens["b"], db, read_snapshot=broken)
    assert status == 503 and payload["error_code"] == "document-registry-unavailable"
    assert "Application.Documents unavailable" in payload["error"]
    assert db.collected == []


def test_a_collector_that_raises_is_a_named_500_with_no_data_and_the_observed_active_document():
    app, uiapp, reg, tokens, docs = read_rig()
    status, payload = read_summary(uiapp, reg, tokens["b"], FakeDB(raises=RuntimeError("Document was closed")))
    assert status == 500 and payload["error_code"] == "document-read-failed" and payload["error"]
    assert "Document was closed" in payload["error"] and tokens["b"] in payload["error"]
    assert "summary" not in payload
    assert payload["document"]["document"] == tokens["b"]
    assert payload["observed_active_document"]["document"] == tokens["a"]
    assert uiapp.calls == []


def test_every_request_resolves_the_live_token_again():
    app, uiapp, reg, tokens, docs = read_rig()
    db = FakeDB()
    assert read_summary(uiapp, reg, tokens["b"], db)[0] == 200
    app.close_document(docs["b"])
    db_after = FakeDB()
    status, payload = read_summary(uiapp, reg, tokens["b"], db_after)
    assert status == 404 and payload["error_code"] == "document-closed"
    assert db_after.collected == []


# ----------------------------------------------- no UI dependency in the collector


UI_DEPENDENT_NAMES = {"ActiveUIDocument", "HOST_APP", "uiapp", "UIDocument", "UIApplication",
                      "ActiveView", "uidoc", "revit", "doc", "OpenAndActivateDocument"}


def code_identifiers(node):
    found = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute):
            found.add(child.attr)
        elif isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.ImportFrom):
            found.update(alias.name for alias in child.names)
    return found


def test_the_summary_collector_and_its_helpers_have_no_ui_or_active_document_dependency():
    for name in ("collect_document_summary", "_project_information", "_db"):
        assert code_identifiers(function_node(name)) & UI_DEPENDENT_NAMES == set(), name


def test_the_read_orchestration_never_activates_and_never_reads_the_ui_document_itself():
    for name in ("run_document_read", "run_document_summary"):
        node = function_node(name)
        assert "OpenAndActivateDocument" not in callee_names(node), name
        assert code_identifiers(node) & {"ActiveUIDocument", "HOST_APP", "uiapp", "OpenAndActivateDocument"} == set()
    # The only place the UI document is read is the identity snapshot, never this module.
    assert "ActiveUIDocument" not in code_identifiers(documents_tree())


# ----------------------------------------------------------------- the route


def read_handlers(monkeypatch, fake_routes, uiapp, registry, db, identity_value=None):
    captured = activate_handlers(monkeypatch, fake_routes, uiapp, registry, identity_value)
    monkeypatch.setattr(documents, "_db", lambda: db)
    return captured


def test_the_summary_route_is_a_post_handler_taking_only_the_request(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = read_rig()
    captured = read_handlers(monkeypatch, fake_routes, uiapp, reg, FakeDB())
    handler = captured[("/document_summary/", ("POST",))]
    assert list(inspect.signature(handler).parameters) == ["request"]
    assert ("/documents/", ("GET",)) in captured and ("/activate_document/", ("POST",)) in captured


def test_the_summary_route_reads_a_text_plain_bytes_body_and_names_the_process(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = read_rig()
    db = FakeDB()
    handler = read_handlers(monkeypatch, fake_routes, uiapp, reg, db)[("/document_summary/", ("POST",))]
    handler(FakeRequest(('{"document": "%s"}' % tokens["b"]).encode("utf-8")))
    payload, status = fake_routes[-1]
    assert status == 200 and payload["summary"]["title"] == "COORD"
    assert payload["process_identity"] == IDENT and payload["ui_switched"] is False
    assert only_from(db, docs["b"], docs["a"]) and uiapp.calls == []


def test_the_summary_route_refusal_keeps_its_status_and_the_process(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = read_rig()
    app.close_document(docs["b"])
    db = FakeDB()
    handler = read_handlers(monkeypatch, fake_routes, uiapp, reg, db)[("/document_summary/", ("POST",))]
    handler(FakeRequest({"document": tokens["b"]}))     # a dict body is accepted too
    payload, status = fake_routes[-1]
    assert status == 404 and payload["error_code"] == "document-closed" and "summary" not in payload
    assert payload["process_identity"] == IDENT and db.collected == []


def test_the_summary_route_answers_a_bad_or_empty_body_with_400(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = read_rig()
    db = FakeDB()
    handler = read_handlers(monkeypatch, fake_routes, uiapp, reg, db)[("/document_summary/", ("POST",))]
    for body in (None, b"", b"{}", b"not json", b"[1, 2]"):
        handler(FakeRequest(body))
        payload, status = fake_routes[-1]
        assert status == 400 and payload["error"], body
        assert payload["process_identity"] == IDENT
    assert db.collected == []


def test_the_summary_route_without_process_identity_says_so(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = read_rig()
    handler = read_handlers(monkeypatch, fake_routes, uiapp, reg, FakeDB(), identity_value="none")[
        ("/document_summary/", ("POST",))]
    handler(FakeRequest({"document": tokens["b"]}))
    payload, status = fake_routes[-1]
    assert status == 200 and "process_identity" not in payload
    assert payload["identity_error"] == "no retained RoutesServer"


def test_the_summary_route_never_raises(monkeypatch, fake_routes):
    app, uiapp, reg, tokens, docs = read_rig()
    handlers = read_handlers(monkeypatch, fake_routes, uiapp, reg, FakeDB())
    handler = handlers[("/document_summary/", ("POST",))]

    def no_db():
        raise RuntimeError("DB namespace unavailable")

    monkeypatch.setattr(documents, "_db", no_db)
    handler(FakeRequest({"document": tokens["b"]}))
    payload, status = fake_routes[-1]
    assert status == 500 and payload["error_code"] == "document-read-failed"
    assert "DB namespace unavailable" in payload["error"] and payload["process_identity"] == IDENT

    class NoUIApp(object):
        @property
        def uiapp(self):
            raise RuntimeError("no UIApplication")

    monkeypatch.setattr(sys.modules["pyrevit"], "HOST_APP", NoUIApp())
    handler(FakeRequest({"document": tokens["b"]}))
    payload, status = fake_routes[-1]
    assert status == 503 and payload["error_code"] == "document-registry-unavailable"
    assert payload["process_identity"] == IDENT and uiapp.calls == []


# ------------------------------------------------------------------ the tool


def run_read_tool(name, response, **kwargs):
    from tools.document_tools import register_document_tools

    calls = []

    async def revit_get(*args, **options):  # pragma: no cover - never called
        raise AssertionError(name + " must not GET")

    async def revit_post(path, data, ctx=None, **options):
        calls.append((path, data, options))
        return response

    mcp = FakeMCP()
    register_document_tools(mcp, revit_get, revit_post)
    return asyncio.run(mcp.tools[name](**kwargs)), calls


B_DESCRIPTOR = {"document": "doc1.aaaaaaaaaaaa.2", "title": "COORD", "path": "C:/M/COORD.rvt",
                "active": False, "saved": True}


def summary_reply(**override):
    reply = {
        "status": "success", "process_identity": dict(IDENT), "document": dict(B_DESCRIPTOR),
        "target_is_active": False, "ui_switched": False,
        "active_before": "doc1.aaaaaaaaaaaa.1", "active_after": "doc1.aaaaaaaaaaaa.1",
        "summary": {"title": "COORD", "path": "C:/M/COORD.rvt", "non_type_element_count": 1234,
                    "level_count": 7,
                    "project_information": {"name": "Coordination", "number": "B-200",
                                            "client": "Client B", "status": "Design"},
                    "unreadable_fields": []},
    }
    reply.update(override)
    return reply


def test_read_document_summary_tool_posts_the_token_and_target_and_renders_the_data():
    text, calls = run_read_tool("read_document_summary", summary_reply(),
                                document="doc1.aaaaaaaaaaaa.2", target="revit1:xyz")
    assert calls == [("/document_summary/", {"document": "doc1.aaaaaaaaaaaa.2"}, {"target": "revit1:xyz"})]
    for needle in ("COORD", "C:/M/COORD.rvt", "1234", "Coordination", "B-200", "Client B", "Design",
                   "doc1.aaaaaaaaaaaa.2", "PID 4242", "48885", "tok-abc"):
        assert needle in text, needle
    lowered = text.lower()
    assert "not activated" in lowered or "no activation" in lowered
    assert "observation" in lowered and "unchanged" in lowered
    assert "not the model_info" in lowered or "not model_info" in lowered


def test_read_document_summary_tool_says_loudly_when_the_active_document_changed():
    text, _ = run_read_tool("read_document_summary",
                            summary_reply(ui_switched=True, active_after="doc1.aaaaaaaaaaaa.2"),
                            document="doc1.aaaaaaaaaaaa.2")
    assert "changed" in text.lower() and "unchanged" not in text.lower()
    text, _ = run_read_tool("read_document_summary",
                            summary_reply(ui_switched=None, active_after=None,
                                          active_after_error="Application.Documents unavailable"),
                            document="doc1.aaaaaaaaaaaa.2")
    assert "unknown" in text.lower() and "unchanged" not in text.lower()


def test_read_document_summary_tool_lists_unreadable_fields_instead_of_hiding_them():
    reply = summary_reply()
    reply["summary"]["unreadable_fields"] = ["project_information.number"]
    del reply["summary"]["project_information"]["number"]
    text, _ = run_read_tool("read_document_summary", reply, document="doc1.aaaaaaaaaaaa.2")
    assert "project_information.number" in text and "B-200" not in text


def test_read_document_summary_tool_never_renders_a_refusal_as_data():
    refusal = 'Error: 404 - {"error": "closed", "error_code": "document-closed"}'
    text, calls = run_read_tool("read_document_summary", refusal, document="doc1.aaaaaaaaaaaa.2")
    assert "document-closed" in text and "Answering Revit process" not in text and len(calls) == 1
    text, _ = run_read_tool("read_document_summary", {"error": "boom", "error_code": "document-read-failed"},
                            document="doc1.aaaaaaaaaaaa.2")
    assert "boom" in text and "COORD" not in text


def test_read_document_summary_tool_refuses_a_missing_document_without_posting():
    for bad in ("", "   ", None):
        text, calls = run_read_tool("read_document_summary", summary_reply(), document=bad)
        assert calls == [] and "document" in text.lower() and "list_documents" in text


def test_read_document_summary_signature_and_docstring_are_the_api_contract():
    from tools.document_tools import register_document_tools

    mcp = FakeMCP()
    register_document_tools(mcp, None, None)
    function = mcp.tools["read_document_summary"]
    names = list(inspect.signature(function).parameters)
    assert names == ["document", "target", "ctx"]
    assert inspect.signature(function).parameters["document"].default is inspect.Parameter.empty
    doc = function.__doc__
    for name in names:
        assert name + ":" in doc, "docstring Args must name {}".format(name)
    for field in ("title", "path", "non_type_element_count", "level_count", "project_information",
                  "name", "number", "client", "status", "unreadable_fields", "ui_switched"):
        assert field in doc, "docstring must list returned field {}".format(field)
    lowered = doc.lower()
    assert "exactly two" in lowered and "02-07" in doc and "list_documents" in doc
    assert "does not activate" in lowered or "never activate" in lowered
    assert "closed" in lowered and "refused" in lowered
    assert "model_info" in doc and "OpenAndActivateDocument" not in doc


def test_read_document_summary_is_in_the_tool_manifest():
    manifest = os.path.join(REPO_ROOT, "tests", "unit", "tool_manifest.txt")
    with open(manifest, encoding="utf-8") as handle:
        assert "read_document_summary" in handle.read().split()
