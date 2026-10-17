# -*- coding: utf-8 -*-
"""Wave-0 Document doubles for the multi-document contracts (plan 02-02, D-08).

Pure Python, no Revit, no pyRevit, no network. These are FIXTURES that model the
retained-reference-equals-v1 semantics accepted at the 02-20 checkpoint (G2), so
the document registry and routes of 02-04 onward have something to be written
against. They are NOT production registry evidence: no token issuance, registry or
route exists here, and nothing in this file proves how a real Revit Document
behaves; the live G2 measurement was the 02-20 diagnostic capture.

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
