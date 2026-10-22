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


def test_no_route_wrapper_or_decorator_is_installed_in_startup():
    with open(os.path.join(REPO_ROOT, "startup.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert "mutation_document_or_response" not in source
    assert "decide_mutation_document" not in source
