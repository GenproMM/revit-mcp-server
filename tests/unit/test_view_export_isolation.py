# -*- coding: utf-8 -*-
"""Run the real export provider with file-backed fakes; no Revit or network."""
import ast
import base64
import logging
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


class ViewIds(list):
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def Add(self, item):
        self.append(item)


class Options:
    def SetViewsAndSheets(self, ids):
        self.ids = ids


@pytest.mark.parametrize('image_count', [0, 1, 2])
def test_export_cannot_return_another_documents_png(tmp_path, image_count):
    stale = tmp_path / 'RevitMCPExports'
    stale.mkdir()
    stale_image = stale / 'export-active-model.png'
    stale_image.write_bytes(b'wrong model A')
    folders, exports = [], []
    view = SimpleNamespace(Name='План B', IsTemplate=False, ViewType='FloorPlan', Id=42)

    class Collector:
        def __init__(self, document):
            assert document is selected_b

        def OfClass(self, cls):
            return self

        def ToElements(self):
            return [view]

    def export(options):
        exports.append(options)
        assert options.ids == [42]
        for index in range(image_count):
            Path(options.FilePath + str(index) + '.png').write_bytes(b'model B image')

    selected_b = SimpleNamespace(ExportImage=export)

    def private_folder(prefix):
        folder = tempfile.mkdtemp(prefix=prefix, dir=str(tmp_path))
        folders.append(Path(folder))
        return folder

    enums = SimpleNamespace(SetOfViews=1, PNG=2, DPI_150=3, FitToPage=4)
    db = SimpleNamespace(FilteredElementCollector=Collector, View=object, ElementId=int,
                         ImageExportOptions=Options, ExportRange=enums, ImageFileType=enums,
                         ImageResolution=enums, ZoomFitType=enums,
                         ViewType=SimpleNamespace(Internal='Internal', ProjectBrowser='Browser'))
    routes = SimpleNamespace(make_response=lambda data, status=200: SimpleNamespace(data=data, status=status))
    namespace = dict(DB=db, List=ViewIds, routes=routes, os=os, base64=base64,
                     tempfile=SimpleNamespace(mkdtemp=private_folder),
                     logger=logging.getLogger(__name__), unquote=lambda x: x,
                     normalize_string=lambda x: x, get_element_name=lambda v: v.Name)
    tree = ast.parse((ROOT / 'revit_mcp' / 'views.py').read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_get_view')
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<export-provider>', 'exec'), namespace)

    reply = namespace['_get_view'](selected_b, 'План B')

    assert len(exports) == 1 and len(folders) == 1
    assert folders[0] != stale
    assert stale_image.read_bytes() == b'wrong model A'
    if image_count == 1:
        assert reply.status == 200
        assert base64.b64decode(reply.data['image_data']) == b'model B image'
        assert not folders[0].exists()
    else:
        assert reply.status == 500 and 'image_data' not in reply.data
        assert 'exactly one' in reply.data['error']
        if image_count == 0:
            assert not folders[0].exists()
