# -*- coding: utf-8 -*-
"""Offline preflight contract: real document guard, no transactions or mutations."""

import importlib
import json
import sys
import types

import pytest

from test_routes_mep_parameter_identity import world


SUPPORTED = (
    "/set_parameter/", "/modify_element/", "/delete_elements/",
    "/transform_elements/", "/edit_family/", "/load_family/",
)


@pytest.fixture
def preflight(world, monkeypatch):
    monkeypatch.delitem(sys.modules, "revit_mcp.preflight", raising=False)
    module = importlib.import_module("revit_mcp.preflight")
    captured = {}

    class Api(object):
        def route(self, path, methods=None):
            def register(fn):
                captured[path] = fn
                return fn
            return register

    module.register_preflight_routes(Api())
    return module, captured["/mutation_preflight/"]


def invoke(world, preflight, body=None, raw=None):
    request = types.SimpleNamespace(
        data=raw if raw is not None else json.dumps(body or {}),
        path="/mutation_preflight/", method="POST")
    response = preflight[1](uiapp=world.uiapp, doc=world.injected, request=request)
    assert not world.transactions
    assert not world.events
    return response


@pytest.mark.parametrize("route", SUPPORTED)
def test_supported_route_uses_resolved_document_without_mutation(world, preflight, route):
    world.open("Модель", "C:/Models/Only.rvt", active=True)
    preflight[0]._FACTS[route] = lambda doc, args: {"available": False, "reason": "not_collected"}
    response = invoke(world, preflight, {"route": route, "args": {}})
    assert response.status == 200
    assert response.data["status"] == "ok"
    assert response.data["route"] == route
    assert response.data["document"]["title"] == "Модель"
    assert response.data["facts"] == {"available": False, "reason": "not_collected"}
    assert len(world.guard_calls) == 1


def test_unsupported_route_is_bad_request_before_document_access(world, preflight):
    response = invoke(world, preflight, {"route": "/no_such/", "args": {}})
    assert response.status == 400
    assert response.data["error_code"] == "preflight-unsupported-route"
    assert not world.guard_calls


@pytest.mark.parametrize("raw", ["{bad", "[]", "null", '"text"'])
def test_bad_body_is_bad_request(world, preflight, raw):
    assert invoke(world, preflight, raw=raw).status == 400
    assert not world.guard_calls


@pytest.mark.parametrize("args", [[], None, "bad"])
def test_non_object_args_are_bad_request(world, preflight, args):
    assert invoke(world, preflight, {"route": SUPPORTED[0], "args": args}).status == 400


def test_no_document_refuses_with_real_guard(world, preflight):
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}})
    assert response.status == 503


def test_multiple_documents_require_selector(world, preflight):
    world.open("A", "C:/Models/A.rvt", active=True)
    world.open("B", "C:/Models/B.rvt")
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}})
    assert response.status == 400
    assert response.data["error_code"] == "document-selector-required"


def test_inactive_selected_document_is_not_activated(world, preflight):
    active = world.open("A", "C:/Models/A.rvt", active=True)
    world.open("B", "C:/Models/B.rvt")
    selector = world.tokens()[1]
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}, "document": selector})
    assert response.status == 412
    assert world.uiapp.active is active


def test_guard_refusal_is_returned_unchanged(world, preflight, monkeypatch):
    sentinel = object()
    monkeypatch.setattr(preflight[0], "mutation_document_or_response", lambda *a, **kw: (None, None, sentinel))
    assert invoke(world, preflight, {"route": SUPPORTED[0], "args": {}}) is sentinel


def test_envelope_is_stripped_before_parsing(world, preflight):
    world.open("Only", "C:/Models/Only.rvt", active=True)
    preflight[0]._FACTS[SUPPORTED[0]] = lambda doc, args: {"available": False, "reason": "not_collected"}
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}, "_mcp": {"secret": "wrong"}})
    assert response.status == 200


def test_unexpected_builder_failure_never_raises(world, preflight, monkeypatch):
    world.open("Only", "C:/Models/Only.rvt", active=True)

    def fail(*args):
        raise RuntimeError("unreadable")

    monkeypatch.setitem(preflight[0]._FACTS, SUPPORTED[0], fail)
    response = invoke(world, preflight, {"route": SUPPORTED[0], "args": {}})
    assert response.status == 500
    assert response.data["error_code"] == "preflight-failed"


class Id(object):
    def __init__(self, value):
        self.Value = value


class Element(object):
    def __init__(self, key, name="Элемент", parameters=None, type_id=-1):
        self.Id = Id(key)
        self.Name = name
        self.Category = types.SimpleNamespace(Name="Стены", Id=Id(90))
        self.GroupId = Id(-1)
        self.Pinned = False
        self.parameters = parameters or {}
        self.type_id = type_id

    def LookupParameter(self, name):
        return self.parameters.get(name)

    def GetTypeId(self):
        return Id(self.type_id)


class ElementType(Element):
    pass


class Family(Element):
    IsEditable = True
    IsInPlace = False

    def GetFamilySymbolIds(self):
        return [Id(10), Id(11)]


class ParameterElement(Element):
    pass


class View(Element):
    pass


class Level(Element):
    pass


class Parameter(object):
    IsReadOnly = False

    def __init__(self, value, storage="String", display=None, has_value=True):
        self.value = value
        self.StorageType = storage
        self.HasValue = has_value
        self.display = display

    def AsString(self):
        return self.value

    def AsValueString(self):
        return self.display

    def AsInteger(self):
        return self.value

    def AsDouble(self):
        return self.value

    def AsElementId(self):
        return Id(self.value)


class Collector(object):
    def __init__(self, doc):
        self.items = list(doc.elements.values())

    def OfClass(self, kind):
        self.items = [item for item in self.items if isinstance(item, kind)]
        return self

    def ToElements(self):
        return self.items

    def WherePasses(self, type_id):
        self.items = [item for item in self.items if item.type_id == type_id.Value]
        return self

    def OfCategoryId(self, key):
        self.items = [item for item in self.items if item.Category.Id.Value == key.Value]
        return self

    def WhereElementIsNotElementType(self):
        self.items = [item for item in self.items if not isinstance(item, ElementType)]
        return self

    def __iter__(self):
        return iter(self.items)


class Document(object):
    def __init__(self):
        self.elements = {}
        self.Application = types.SimpleNamespace(
            SharedParametersFilename="", OpenSharedParameterFile=lambda: None)

    def GetElement(self, key):
        return self.elements.get(key.Value)


@pytest.fixture
def facts(world, preflight, monkeypatch):
    doc = Document()
    db = world.db
    for name, value in dict(
            ElementType=ElementType, Family=Family, ParameterElement=ParameterElement,
            View=View, Level=Level, FilteredElementCollector=Collector,
            FamilyInstanceFilter=lambda doc, key: key).items():
        monkeypatch.setattr(db, name, value, raising=False)
    monkeypatch.setattr(preflight[0], "make_element_id", Id)
    monkeypatch.setattr(preflight[0], "mutation_document_or_response",
                        lambda *a, **kw: (doc, {"title": "Модель"}, None))

    def collect(route, args):
        response = invoke(world, preflight, {"route": route, "args": args})
        assert response.status == 200
        return response.data["facts"]

    return doc, collect, preflight[0]


def test_instance_parameter_facts_keep_cyrillic_and_values(facts):
    doc, collect, _ = facts
    doc.elements[1] = Element(1, parameters={"Марка": Parameter("А-1")})
    result = collect("/set_parameter/", {"element_id": 1, "parameter_name": "Марка"})
    assert result["available"] is True
    assert result["element"]["category"] == "Стены"
    assert result["parameters"][0] == {
        "name": "Марка", "resolved": "instance", "read_only": False,
        "storage_type": "String", "has_value": True, "display_value": "А-1", "raw_value": "А-1"}


def test_type_parameter_counts_actual_instances(facts):
    doc, collect, _ = facts
    target = ElementType(10, parameters={"P": Parameter(2, "Integer", "2")})
    doc.elements[10] = target
    doc.elements.update({key: Element(key, type_id=10) for key in range(100, 440)})
    result = collect("/set_parameter/", {"element_id": 100, "parameter_name": "P"})
    assert result["parameters"][0]["resolved"] == "type"
    assert result["element"]["type_instance_count"] == 340
    assert result["element"]["count_capped"] is False


def test_type_parameter_scan_cap_is_unknown(facts, monkeypatch):
    doc, collect, module = facts
    doc.elements[10] = ElementType(10, parameters={"P": Parameter("x")})
    doc.elements.update({key: Element(key, type_id=10) for key in range(100, 105)})
    monkeypatch.setattr(module, "SCAN_CAP", 3)
    result = collect("/set_parameter/", {"element_id": 100, "parameter_name": "P"})
    assert result["element"]["type_instance_count"] is None
    assert result["element"]["count_capped"] is True


def test_type_element_and_group_membership_are_reported(facts):
    doc, collect, _ = facts
    target = ElementType(10, parameters={"P": Parameter("")})
    target.GroupId = Id(99)
    doc.elements[10] = target
    result = collect("/set_parameter/", {"element_id": 10, "parameter_name": "P"})
    assert result["element"]["is_type"] is True
    assert result["element"]["group_member"] is True


def test_missing_element_has_no_parameters(facts):
    _, collect, _ = facts
    result = collect("/set_parameter/", {"element_id": 999, "parameter_name": "P"})
    assert result["element"]["exists"] is False
    assert result["parameters"] == []


def test_modify_is_instance_only_and_reports_missing_parameter(facts):
    doc, collect, _ = facts
    doc.elements[1] = Element(1, parameters={"A": Parameter("", has_value=False)}, type_id=10)
    doc.elements[10] = ElementType(10, parameters={"B": Parameter("type")})
    result = collect("/modify_element/", {"element_id": 1, "parameters": {"A": "new", "B": "new"}})
    assert [p["resolved"] for p in result["parameters"]] == ["instance", "not_found"]
    assert result["parameters"][0]["has_value"] is False


def test_parameter_cap_refuses_before_document_lookup(facts):
    _, collect, _ = facts
    result = collect("/modify_element/", {"element_id": 1, "parameters": {str(i): "x" for i in range(51)}})
    assert result == {"available": False, "reason": "too_many_parameters"}


@pytest.mark.parametrize("storage,value,display", [("Double", 1.5, "457.2 mm"), ("Integer", 2, "Да"), ("ElementId", 77, None)])
def test_parameter_storage_values_are_internal_not_converted(facts, storage, value, display):
    doc, collect, _ = facts
    doc.elements[1] = Element(1, parameters={"P": Parameter(value, storage, display)})
    result = collect("/set_parameter/", {"element_id": 1, "parameter_name": "P"})
    assert result["parameters"][0]["raw_value"] == value
    if display:
        assert result["parameters"][0]["display_value"] == display


def test_delete_reports_missing_kinds_and_never_guesses_cascade(facts):
    doc, collect, _ = facts
    doc.elements[1] = ParameterElement(1)
    doc.elements[2] = ElementType(2)
    result = collect("/delete_elements/", {"element_ids": [1, 2, 999]})
    assert (result["requested"], result["found"], result["missing"]) == (3, 2, [999])
    assert result["categories"] == {"Стены": 2}
    assert result["kinds"]["type"] == result["kinds"]["parameter_definition"] == 1
    assert result["cascade"] == "unknown"


def test_transform_reports_pinned_and_operation(facts):
    doc, collect, _ = facts
    doc.elements[1] = Element(1)
    doc.elements[1].Pinned = True
    result = collect("/transform_elements/", {"element_ids": [1], "operation": "move"})
    assert result["pinned"] == 1
    assert result["operation"] == "move"


def test_id_cap_and_missing_output_cap(facts):
    _, collect, _ = facts
    assert collect("/delete_elements/", {"element_ids": list(range(2001))}) == {
        "available": False, "reason": "too_many_ids"}
    result = collect("/delete_elements/", {"element_ids": list(range(25))})
    assert result["missing"] == list(range(20))
    assert result["found"] == 0


def test_kind_counts_and_top_ten_categories(facts):
    doc, collect, _ = facts
    for key, kind in enumerate([Family, View, Level] + [Element] * 9):
        item = kind(key)
        item.Category.Name = "Категория {}".format(key)
        doc.elements[key] = item
    result = collect("/delete_elements/", {"element_ids": list(doc.elements)})
    assert len(result["categories"]) == 10
    assert result["kinds"]["family"] == result["kinds"]["view"] == result["kinds"]["level"] == 1


def test_family_edit_reports_requested_changes_without_opening_family(facts):
    doc, collect, _ = facts
    doc.elements[1] = Family(1, "Семейство")
    result = collect("/edit_family/", {"family_name": "Семейство", "parameters": {"P": 3}, "new_type_name": "Новый"})
    assert result["family"] == {
        "name": "Семейство", "found": True, "id": 1, "editable": True, "in_place": False,
        "symbol_count": 2, "instance_count": 0, "count_capped": False}
    assert result["requested"]["parameters"] == ["P"]
    assert result["requested"]["new_type_name"] == "Новый"
    assert result["requested"]["reload"] is True


def test_family_missing_is_explicit(facts):
    _, collect, _ = facts
    assert collect("/edit_family/", {"family_name": "Missing"})["family"]["found"] is False


def definition(name, guid):
    return types.SimpleNamespace(Name=name, GUID=guid, GetDataType=lambda: types.SimpleNamespace(TypeId="spec:length"),
                                 OwnerGroup=types.SimpleNamespace(Name="Размеры"))


def test_shared_definitions_report_guid_type_group_and_ambiguity(facts):
    doc, collect, _ = facts
    doc.elements[1] = Family(1, "F")
    one = definition("ADSK_Марка", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA")
    duplicates = [definition("X", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                  definition("X", "cccccccc-cccc-cccc-cccc-cccccccccccc")]
    doc.Application.SharedParametersFilename = "C:/ФОП.txt"
    doc.Application.OpenSharedParameterFile = lambda: types.SimpleNamespace(
        Groups=[types.SimpleNamespace(Definitions=[one] + duplicates)])
    result = collect("/edit_family/", {"family_name": "F", "add_shared_parameters": ["ADSK_Марка", "X"]})
    a, x = result["shared"]["definitions"]
    assert a == {"name": "ADSK_Марка", "resolved": True, "guid": one.GUID.lower(),
                 "datatype": "spec:length", "group": "Размеры", "ambiguous": False}
    assert x["ambiguous"] is True
    assert x["guid"] is None


def test_no_shared_file_does_not_invent_definitions(facts):
    doc, collect, _ = facts
    doc.elements[1] = Family(1, "F")
    result = collect("/edit_family/", {"family_name": "F", "add_shared_parameters": ["P"]})
    assert result["shared"]["configured_file"] is None
    assert result["shared"]["definitions"][0]["resolved"] is False


def test_family_instance_count_is_bounded_across_symbols(facts, monkeypatch):
    doc, collect, module = facts
    doc.elements[1] = Family(1, "F")
    doc.elements.update({key: Element(key, type_id=10) for key in range(100, 105)})
    monkeypatch.setattr(module, "SCAN_CAP", 3)
    result = collect("/edit_family/", {"family_name": "F"})
    assert result["family"]["instance_count"] is None
    assert result["family"]["count_capped"] is True


def test_load_family_reports_disk_metadata_and_loaded_name(facts, tmp_path):
    doc, collect, _ = facts
    path = tmp_path / "Семейство.rfa"
    path.write_bytes(b"not a real family")
    doc.elements[1] = Family(1, "Семейство")
    result = collect("/load_family/", {"file_path": str(path)})
    assert result["file"] == {"path": str(path), "exists": True, "size": 17}
    assert result["already_loaded"] is True
    assert result["contents"] == "unknown"


def test_missing_family_file_has_no_size(facts, tmp_path):
    _, collect, _ = facts
    result = collect("/load_family/", {"file_path": str(tmp_path / "missing.rfa")})
    assert result["file"]["exists"] is False
    assert result["file"]["size"] is None


def test_builder_error_is_unavailable_not_partial_facts(facts, monkeypatch, caplog):
    doc, collect, _ = facts

    def fail(key):
        raise RuntimeError("unreadable")

    monkeypatch.setattr(doc, "GetElement", fail)
    assert collect("/set_parameter/", {"element_id": 1, "parameter_name": "P"}) == {
        "available": False, "reason": "RuntimeError"}
    assert "RuntimeError" in caplog.text


def test_exact_parameter_and_element_caps_are_accepted(facts):
    doc, collect, _ = facts
    doc.elements[1] = Element(1)
    result = collect("/modify_element/", {"element_id": 1, "parameters": {str(i): "x" for i in range(50)}})
    assert result["available"] is True
    assert len(result["parameters"]) == 50
    result = collect("/delete_elements/", {"element_ids": list(range(2000))})
    assert result["available"] is True
    assert result["requested"] == 2000


def test_family_parameter_cap_includes_shared_requests(facts):
    _, collect, _ = facts
    assert collect("/edit_family/", {"family_name": "F", "parameters": {"P": 1},
                                    "add_shared_parameters": [str(i) for i in range(50)]}) == {
        "available": False, "reason": "too_many_parameters"}


def test_repeated_same_guid_is_not_ambiguous(facts):
    doc, collect, _ = facts
    doc.elements[1] = Family(1, "F")
    guid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    doc.Application.SharedParametersFilename = "C:/shared.txt"
    doc.Application.OpenSharedParameterFile = lambda: types.SimpleNamespace(Groups=[
        types.SimpleNamespace(Definitions=[definition("P", guid), definition("P", guid.upper())])])
    result = collect("/edit_family/", {"family_name": "F", "add_shared_parameters": ["P"]})
    item = result["shared"]["definitions"][0]
    assert item["guid"] == guid
    assert item["ambiguous"] is False


def test_read_only_and_unset_parameter_are_explicit(facts):
    doc, collect, _ = facts
    parameter = Parameter(None, has_value=False)
    parameter.IsReadOnly = True
    doc.elements[1] = Element(1, parameters={"P": parameter})
    result = collect("/set_parameter/", {"element_id": 1, "parameter_name": "P"})
    assert result["parameters"][0]["read_only"] is True
    assert result["parameters"][0]["has_value"] is False
    assert result["parameters"][0]["raw_value"] is None


def test_family_count_under_cap_counts_all_symbols(facts):
    doc, collect, _ = facts
    doc.elements[1] = Family(1, "F")
    doc.elements[100] = Element(100, type_id=10)
    doc.elements[101] = Element(101, type_id=11)
    doc.elements[102] = Element(102, type_id=12)
    result = collect("/edit_family/", {"family_name": "F"})
    assert result["family"]["instance_count"] == 2
    assert result["family"]["count_capped"] is False


@pytest.mark.parametrize("route,args", [
    ("/set_parameter/", {}), ("/modify_element/", {"parameters": []}),
    ("/delete_elements/", {"element_ids": ["invalid"]}),
    ("/transform_elements/", {"element_ids": ["invalid"]}),
    ("/edit_family/", {"family_name": "F"}), ("/load_family/", {}),
])
def test_each_builder_exception_is_unavailable(world, preflight, monkeypatch, route, args):
    def fail(*args, **kwargs):
        raise RuntimeError("read failed")

    doc = Document()
    monkeypatch.setattr(doc, "GetElement", fail)
    monkeypatch.setattr(preflight[0], "find_family_by_name", fail)
    monkeypatch.setattr(preflight[0], "mutation_document_or_response",
                        lambda *a, **kw: (doc, {"title": "M"}, None))
    response = invoke(world, preflight, {"route": route, "args": args})
    assert response.status == 200
    assert response.data["facts"]["available"] is False
    assert response.data["facts"]["reason"] in ("RuntimeError", "TypeError", "ValueError")
