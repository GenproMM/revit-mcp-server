# -*- coding: utf-8 -*-
"""Selection payloads must survive the tool's summary projection."""

import asyncio
import copy

import pytest

from tools.editing_tools import register_editing_tools
from tools.utils import format_response



def invoke(response):
    tools = {}

    class MCP:
        def tool(self):
            def register(function):
                tools[function.__name__] = function
                return function
            return register

    async def get(path, ctx, **options):
        assert path == "/selected_elements/"
        assert options == {"target": "test-target"}
        return response

    register_editing_tools(MCP(), get, None)
    return asyncio.run(tools["get_selected_elements"](target="test-target"))


def test_real_selection_shape_preserves_ids_categories_cyrillic_and_provenance():
    from bridge import ProvenanceDict
    response = ProvenanceDict(status="success", count=2, message="2 elements currently selected", elements=[
        {"id": 123, "category": "Стены", "type": "Стена 200", "level": "Этаж 1",
         "parameters": {"Comments": "Проверка"}},
        {"id": 9876543210, "category": "Двери", "type": "Дверь"},
    ])
    # Use the transport's actual provenance attribute rather than a lookalike key.
    from tools.utils import PROVENANCE_ATTR
    setattr(response, PROVENANCE_ATTR, {"kind": "received", "process": {
        "pid": 42, "revit_version": "2024", "actual_port": 48884, "session_token": "test"}})
    original = copy.deepcopy(response)
    text = invoke(response)
    for value in ("123", "9876543210", "Стены", "Двери", "Стена 200", "Этаж 1", "Проверка", "Count: 2", "PID 42"):
        assert value in text
    assert "ERROR" not in text
    assert response == original and response["message"] == "2 elements currently selected"


def test_empty_selection_remains_success_with_explicit_count_and_list():
    text = invoke({"status": "success", "count": 0, "elements": [], "message": "No elements currently selected"})
    assert "Count: 0" in text and "Elements: []" in text and "ERROR" not in text


@pytest.mark.parametrize("response", [
    "Error: 503 - No active document", "transport reply",
    {"error": "Нет документа", "elements": [], "message": "must not hide error"},
    {"status": "failed", "elements": [], "message": "must not hide failure"},
    {"status": "exception", "elements": [], "error": "Ошибка"},
])
def test_error_and_string_responses_keep_formatter_semantics(response):
    assert invoke(response) == format_response(response)


def test_falsy_error_is_data_not_an_implicit_failure():
    text = invoke({"error": "", "elements": [{"id": 456, "category": "Окна"}], "count": 1, "message": "summary"})
    assert "456" in text and "Окна" in text and "ERROR" not in text
