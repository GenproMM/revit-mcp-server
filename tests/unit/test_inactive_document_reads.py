# -*- coding: utf-8 -*-
"""Offline two-document routing: run every real read entry point, never Revit."""
import ast
import asyncio
import json
import logging
from pathlib import Path
import sys
import types

import pytest

from revit_mcp import identity
from inventory_support import register_everything, minimal_kwargs
from test_document_contracts import FlagApplication, FakeUIApp

ROOT = Path(__file__).resolve().parents[2]
READS = {
    'analysis': ['ai_element_filter_handler', 'export_room_data_handler',
                 'get_material_quantities_handler', 'analyze_model_statistics_handler'],
    'clash': ['clash_check'], 'colors': ['list_parameters'],
    'parameters': ['get_project_parameters_handler', 'get_element_properties_handler'],
    'placement': ['list_families', 'list_family_categories', 'list_levels'],
    'model_info': ['get_model_info'],
    'views': ['get_view', 'list_views', 'get_current_view_info', 'get_current_view_elements'],
    'editing': ['get_selected_elements_handler'],
}
UI_READS = {'get_current_view_info', 'get_current_view_elements', 'get_selected_elements_handler'}
CASES = [(module, name) for module, names in READS.items() for name in names]


class Response:
    def __init__(self, data, status=200):
        self.data, self.status = data, status


@pytest.fixture
def world(monkeypatch):
    app = FlagApplication()
    a = app.open_document('Активная', 'C:/A.rvt')
    b = app.open_document('Фоновая', 'C:/B.rvt', IsDetached=True, IsWorkshared=True)
    uiapp = FakeUIApp(app, a)
    registry = identity.DocumentRegistry()
    listing = identity.current_document_descriptors(uiapp.read_snapshot(), registry)
    monkeypatch.setattr(identity, 'get_document_registry', lambda store=None: registry)
    monkeypatch.setattr(identity, 'process_identity_or_error', lambda uiapp=None: ({'pid': 7}, None))
    routes = types.SimpleNamespace(make_response=lambda data, status=200: Response(data, status))
    monkeypatch.setitem(sys.modules, 'pyrevit', types.SimpleNamespace(routes=routes))
    return types.SimpleNamespace(app=app, a=a, b=b, uiapp=uiapp, registry=registry,
                                 token=listing['documents'][1]['document'], calls=[], routes=routes)


def entry(world, module, name):
    """Compile the production entry point; stub only its existing data provider.

    Existing route suites exercise the real providers. This suite isolates the
    selector seam, including deliberately misleading injected active Document A.
    """
    tree = ast.parse((ROOT / 'revit_mcp' / (module + '.py')).read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    def provider(*args):
        world.calls.append(args)
        return Response({'status': 'success', 'source_title': args[0].Title if hasattr(args[0], 'Title') else 'UI'})
    def strip(request):
        data = json.loads(request.data)
        data.pop('_mcp', None)
        request.data = json.dumps(data)
    namespace = dict(read_document_or_response=identity.read_document_or_response,
                     request_document_selector=identity.request_document_selector,
                     attribute_response=identity.attribute_response,
                     strip_envelope=strip, parse_request_data=json.loads, routes=world.routes)
    namespace['_' + name] = provider
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<read-entry>', 'exec'), namespace)
    return namespace[name]


def invoke(world, module, name, selector, **data):
    fn = entry(world, module, name)
    kwargs = dict(doc=world.a, uiapp=world.uiapp,
                  uidoc=types.SimpleNamespace(Document=world.a),
                  request=types.SimpleNamespace(data=json.dumps(dict(data, document=selector))),
                  document=selector, element_id='42', view_name='План')
    return fn(**{k: v for k, v in kwargs.items() if k in fn.__code__.co_varnames[:fn.__code__.co_argcount]})


@pytest.mark.parametrize('module,name', CASES)
def test_each_read_selects_inactive_b_or_explicitly_refuses_ui_state(world, module, name):
    reply = invoke(world, module, name, world.token)
    if name in UI_READS:
        assert reply.status == 412 and not world.calls
    else:
        assert reply.status == 200
        assert world.calls[0][0].Equals(world.b)
        assert reply.data['source_title'] == 'Фоновая'
        assert reply.data['document']['document'] == world.token
        assert reply.data['document']['active'] is False
        assert reply.data['process_identity'] == {'pid': 7}
    assert world.uiapp.active.Equals(world.a) and world.uiapp.calls == []


@pytest.mark.parametrize('module,name', CASES)
@pytest.mark.parametrize('bad', ['', 'Фоновая', 'C:/B.rvt', 'doc1.000000000000.8', None])
def test_explicit_broken_selector_never_reads_a(world, module, name, bad):
    # HTTP query cannot carry JSON null; its empty spelling is an explicit invalid selector.
    reply = invoke(world, module, name, '' if bad is None else bad)
    assert reply.status in (400, 404) and reply.data['error']
    assert world.calls == [] and world.uiapp.calls == []


@pytest.mark.parametrize('module,name', CASES)
def test_closed_b_token_is_not_replaced_by_a_or_reopened_same_path(world, module, name):
    world.app.close_document(world.b)
    world.app.open_document('Фоновая', 'C:/B.rvt')
    reply = invoke(world, module, name, world.token)
    assert reply.status == 404 and reply.data['error_code'] == 'document-closed'
    assert world.calls == [] and world.uiapp.calls == []


@pytest.mark.parametrize('module,name', [(m, n) for m, n in CASES if n in {
    'ai_element_filter_handler', 'get_material_quantities_handler', 'clash_check', 'list_parameters'}])
def test_post_json_null_is_an_explicit_refusal(world, module, name):
    reply = invoke(world, module, name, None)
    assert reply.status == 400 and world.calls == []
    assert world.uiapp.calls == []


def test_visibility_filter_refuses_inactive_document_before_provider(world):
    reply = invoke(world, 'analysis', 'ai_element_filter_handler', world.token, visible_in_view=True)
    assert reply.status == 412 and world.calls == []
    assert reply.data['document']['document'] == world.token


def test_omitted_read_selector_uses_current_active_not_only_open_document(world):
    selected, descriptor, refusal = identity.read_document_or_response(world.a, uiapp=world.uiapp)
    assert refusal is None and selected.Equals(world.a) and descriptor['active'] is True
    world.uiapp.active = world.b
    selected, descriptor, refusal = identity.read_document_or_response(world.a, uiapp=world.uiapp)
    assert refusal is None and selected.Equals(world.b) and descriptor['document'] == world.token


def test_real_room_provider_collects_only_inactive_b(world):
    room = types.SimpleNamespace(Location=True, LevelId=None,
                                 get_Parameter=lambda name: None)
    collected = []

    class Collector:
        def __init__(self, document):
            assert document.Equals(world.b)
            collected.append(document)

        def OfCategory(self, category):
            return self

        def WhereElementIsNotElementType(self):
            return self

        def ToElements(self):
            return [room]

    fn = entry(world, 'analysis', 'export_room_data_handler')
    tree = ast.parse((ROOT / 'revit_mcp' / 'analysis.py').read_text(encoding='utf-8'))
    provider = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == '_export_room_data_handler')
    fn.__globals__.update(
        DB=types.SimpleNamespace(FilteredElementCollector=Collector,
                                 BuiltInCategory=types.SimpleNamespace(OST_Rooms=1),
                                 BuiltInParameter=types.SimpleNamespace(
                                     ROOM_NAME=1, ROOM_NUMBER=2, ROOM_AREA=3,
                                     ROOM_PERIMETER=4, ROOM_DEPARTMENT=5)),
        get_element_id_value=lambda element: 9001,
        logger=logging.getLogger(__name__))
    exec(compile(ast.Module(body=[provider], type_ignores=[]), '<room-provider>', 'exec'), fn.__globals__)

    reply = fn(doc=world.a, uiapp=world.uiapp, document=world.token)

    assert reply.status == 200 and reply.data['count'] == 1
    assert reply.data['rooms'][0]['id'] == 9001
    assert len(collected) == 1 and reply.data['document']['active'] is False
    assert world.uiapp.active.Equals(world.a) and world.uiapp.calls == []


MODEL_TOOLS = [
    'ai_element_filter', 'export_room_data', 'get_material_quantities', 'analyze_model_statistics',
    'check_clashes', 'list_category_parameters', 'list_project_parameters', 'get_element_properties',
    'list_families', 'list_family_categories', 'list_levels', 'get_revit_model_info',
    'get_revit_view', 'list_revit_views', 'get_current_view_info', 'get_current_view_elements',
    'get_selected_elements',
]


@pytest.mark.parametrize('name', MODEL_TOOLS)
def test_every_model_read_forwards_document_and_process_independently(name):
    tools, calls = register_everything()
    asyncio.run(tools[name](**dict(minimal_kwargs()[name], target='revit1:test', document='doc1.test.2')))
    assert len(calls) == 1
    method, path, body, options = calls[0]
    assert options['target'] == 'revit1:test'
    if method == 'POST':
        assert body['document'] == 'doc1.test.2' and 'target' not in body
    else:
        assert options['params']['document'] == 'doc1.test.2'


@pytest.mark.parametrize('name', MODEL_TOOLS)
@pytest.mark.parametrize('bad', ['', '  ', 7])
def test_every_model_read_rejects_blank_before_transport(name, bad):
    tools, calls = register_everything()
    reply = asyncio.run(tools[name](**dict(minimal_kwargs()[name], document=bad)))
    assert not calls and 'list_documents' in reply
