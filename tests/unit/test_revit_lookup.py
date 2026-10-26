# -*- coding: utf-8 -*-
"""Small fake-Revit rows for the shared mutation/preflight lookup helpers."""

import sys
import types

import pytest


class ElementId(object):
    InvalidElementId = object()

    def __init__(self, value):
        self.Value = value


class StorageType(object):
    String = "String"
    Integer = "Integer"


@pytest.fixture
def lookup(monkeypatch):
    db = types.SimpleNamespace(
        ElementId=ElementId, StorageType=StorageType,
        IFailuresPreprocessor=object, FailureProcessingResult=types.SimpleNamespace(Continue="Continue"))
    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(DB=db))
    import revit_mcp
    missing = object()
    saved_modules = {name: sys.modules.pop("revit_mcp." + name, missing)
                     for name in ("lookup", "utils")}
    saved_attributes = {name: getattr(revit_mcp, name, missing)
                        for name in saved_modules}
    for name in saved_modules:
        if hasattr(revit_mcp, name):
            delattr(revit_mcp, name)
    try:
        import revit_mcp.lookup as module
        yield module
    finally:
        for name, previous in saved_modules.items():
            sys.modules.pop("revit_mcp." + name, None)
            if previous is not missing:
                sys.modules["revit_mcp." + name] = previous
            if hasattr(revit_mcp, name):
                delattr(revit_mcp, name)
            if saved_attributes[name] is not missing:
                setattr(revit_mcp, name, saved_attributes[name])


class Parameter(object):
    def __init__(self, value, has_value=True, storage=StorageType.String, raises=False):
        self.value, self.HasValue, self.StorageType, self.raises = value, has_value, storage, raises

    def AsString(self):
        if self.raises:
            raise RuntimeError("unreadable")
        return self.value


class Element(object):
    def __init__(self, parameters=None, type_id=None):
        self.parameters = parameters or {}
        self.type_id = type_id

    def LookupParameter(self, name):
        return self.parameters.get(name)

    def GetTypeId(self):
        return self.type_id


class Document(object):
    def __init__(self, elements):
        self.elements = elements

    def GetElement(self, key):
        return self.elements.get(key)


class Definition(object):
    def __init__(self, name):
        self.Name = name


class Group(object):
    def __init__(self, definitions):
        self.Definitions = definitions


class SharedFile(object):
    def __init__(self, groups):
        self.Groups = groups


def test_set_parameter_prefers_instance_then_uses_type_or_misses(lookup):
    instance = Parameter("instance")
    type_parameter = Parameter("type")
    doc = Document({"type": Element({"P": type_parameter})})

    assert lookup.resolve_set_parameter(doc, Element({"P": instance}, "type"), "P") == (instance, "instance")
    assert lookup.resolve_set_parameter(doc, Element({}, "type"), "P") == (type_parameter, "type")
    assert lookup.resolve_set_parameter(doc, Element({}, ElementId.InvalidElementId), "P") == (None, None)


def test_instance_lookup_never_uses_type(lookup):
    parameter = Parameter("instance")
    assert lookup.resolve_instance_parameter(Element({"P": parameter}), "P") is parameter
    assert lookup.resolve_instance_parameter(None, "P") is None


def test_shared_definitions_preserve_file_order_and_duplicates(lookup):
    first, second = Definition("X"), Definition("X")
    result = lookup.shared_definitions_by_name(SharedFile([Group([first]), Group([second])]))

    assert result == {"X": [first, second]}
    assert lookup.shared_definitions_by_name(None) == {}


class Collector(object):
    def __init__(self, elements):
        self.elements = elements
        self.visited = 0
        self.filters = []

    def OfClass(self, value):
        self.filters.append(("class", value))
        return self

    def ToElements(self):
        return self.elements

    def WherePasses(self, value):
        self.filters.append(("filter", value))
        return self

    def OfCategoryId(self, value):
        self.filters.append(("category", value))
        return self

    def WhereElementIsNotElementType(self):
        self.filters.append(("instances",))
        return self

    def __iter__(self):
        for element in self.elements:
            self.visited += 1
            yield element


def collector_for(lookup, monkeypatch, elements):
    collector = Collector(elements)
    monkeypatch.setattr(lookup._db(), "FilteredElementCollector", lambda doc: collector, raising=False)
    return collector


def test_family_lookup_returns_first_named_family(lookup, monkeypatch):
    first = types.SimpleNamespace(Name="Семейство")
    second = types.SimpleNamespace(Name="Семейство")
    monkeypatch.setattr(lookup._db(), "Family", object, raising=False)
    collector = collector_for(lookup, monkeypatch, [first, second])
    assert lookup.find_family_by_name(object(), "Семейство") is first
    assert lookup.find_family_by_name(object(), "missing") is None
    assert collector.filters == [("class", object), ("class", object)]


def test_type_count_under_cap_filters_system_category(lookup, monkeypatch):
    collector = collector_for(lookup, monkeypatch, [Element(type_id=ElementId(1)), Element(type_id=ElementId(2))])
    category_id = ElementId(90)
    target = types.SimpleNamespace(Id=ElementId(1), Category=types.SimpleNamespace(Id=category_id))
    assert lookup.type_instance_count(object(), target, 3) == (1, False)
    assert collector.filters == [("category", category_id), ("instances",)]


def test_type_count_caps_scanned_nonmatching_elements(lookup, monkeypatch):
    collector = collector_for(lookup, monkeypatch, [Element(type_id=ElementId(2)) for _ in range(10)])
    target = types.SimpleNamespace(Id=ElementId(1))
    assert lookup.type_instance_count(object(), target, 3) == (None, True)
    assert collector.visited == 3


def test_family_type_count_uses_family_instance_filter(lookup, monkeypatch):
    collector = collector_for(lookup, monkeypatch, [Element(type_id=ElementId(1))])
    monkeypatch.setattr(lookup._db(), "FamilyInstanceFilter", lambda doc, key: (doc, key), raising=False)
    doc = object()
    target = types.SimpleNamespace(Id=ElementId(1), Family=object())
    assert lookup.type_instance_count(doc, target, 2) == (1, False)
    assert collector.filters == [("filter", (doc, target.Id))]


def test_type_count_at_exact_scan_boundary_is_unknown(lookup, monkeypatch):
    collector_for(lookup, monkeypatch, [Element(type_id=ElementId(1)) for _ in range(3)])
    assert lookup.type_instance_count(object(), types.SimpleNamespace(Id=ElementId(1)), 3) == (None, True)


def test_lookup_errors_are_not_reported_as_missing(lookup, monkeypatch):
    def fail(*args):
        raise RuntimeError("unreadable")

    broken = types.SimpleNamespace(LookupParameter=fail)
    with pytest.raises(RuntimeError):
        lookup.resolve_instance_parameter(broken, "P")
    with pytest.raises(RuntimeError):
        lookup.resolve_set_parameter(object(), broken, "P")
    monkeypatch.setattr(lookup._db(), "FilteredElementCollector", fail, raising=False)
    with pytest.raises(RuntimeError):
        lookup.find_family_by_name(object(), "X")


def test_shared_definition_errors_are_not_silently_dropped(lookup):
    class BrokenGroup(object):
        @property
        def Definitions(self):
            raise RuntimeError("unreadable")

    with pytest.raises(RuntimeError):
        lookup.shared_definitions_by_name(SharedFile([BrokenGroup()]))


def test_parameter_has_value_distinguishes_empty_and_unreadable(lookup):
    assert lookup.parameter_has_value(Parameter("", has_value=True)) is False
    assert lookup.parameter_has_value(Parameter("value", has_value=True)) is True
    assert lookup.parameter_has_value(Parameter(None, has_value=False)) is False
    assert lookup.parameter_has_value(Parameter("", raises=True)) is None
