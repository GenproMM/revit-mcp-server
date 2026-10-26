# -*- coding: utf-8 -*-
"""Phase 7 model-facing confirmation contract on the risky tool surface."""

import inspect

from inventory_support import register_everything


def _tool_functions():
    functions, _calls = register_everything()
    return functions


def test_confirmation_contract_covers_each_risky_tool():
    functions = _tool_functions()
    expected = {
        "delete_elements": ("confirmation", "always"),
        "transform_elements": ("confirmation", "always"),
        "set_parameter": ("confirmation", "when"),
        "modify_element": ("confirmation", "when"),
        "load_family": ("confirmation", "always"),
        "edit_family": ("confirmation", "when"),
        "execute_revit_code": ("confirmation", "always"),
    }
    for name, required in expected.items():
        docstring = inspect.getdoc(functions[name])
        assert docstring is not None
        text = docstring.lower()
        for phrase in required:
            assert phrase in text, name
        assert "nothing was sent" in text, name


def test_high_risk_tool_docstrings_state_their_specific_limits():
    functions = _tool_functions()
    execute = inspect.getdoc(functions["execute_revit_code"]).lower()
    load = inspect.getdoc(functions["load_family"]).lower()
    edit = inspect.getdoc(functions["edit_family"]).lower()

    assert "not a review of the code" in execute
    assert "trusted arbitrary-code path" in execute
    assert "not checked against the company shared-parameter file" in load
    assert "shared parameter" in edit
    assert "company file" in edit
