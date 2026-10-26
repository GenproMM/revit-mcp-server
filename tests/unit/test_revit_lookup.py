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
    sys.modules.pop("revit_mcp.lookup", None)
    import revit_mcp.lookup as module
    yield module
    sys.modules.pop("revit_mcp.lookup", None)
    sys.modules.pop("revit_mcp.utils", None)
    import revit_mcp
    for name in ("lookup", "utils"):
        if hasattr(revit_mcp, name):
            delattr(revit_mcp, name)


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


def test_parameter_has_value_distinguishes_empty_and_unreadable(lookup):
    assert lookup.parameter_has_value(Parameter("", has_value=True)) is False
    assert lookup.parameter_has_value(Parameter("value", has_value=True)) is True
    assert lookup.parameter_has_value(Parameter(None, has_value=False)) is False
    assert lookup.parameter_has_value(Parameter("", raises=True)) is None
