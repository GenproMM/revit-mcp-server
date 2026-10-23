# -*- coding: utf-8 -*-
"""The mutation tools' docstrings state the outcome statuses their routes can return (04-09).

A ``@mcp.tool()`` docstring is the model's API contract: the model plans retries and
follow-ups from what it promises. Phase 4 made every mutating route answer with an
honest outcome (``partial`` 200, ``failed`` 422, ``rolled_back`` 409), so each tool
must tell the model how those look, and it may promise ONLY the statuses its route
can actually return: an all-or-nothing route never says PARTIAL SUCCESS, and a route
that always reports the element it created never says HTTP 422 (the 422 path of
``finalize_outcome`` needs zero succeeded with a failure, which a created id rules out).

``OUTCOME_CLASSES`` classifies every tool in ``inventory_support.MUTATION_TOOLS``
and mirrors the routes implemented in plans 04-01..04-07. If a route's possible
statuses change, move its tool to the class that matches and update its docstring.

The docstrings are read by parsing ``tools/*_tools.py`` with ``ast``, so no tool module
is imported. Needs no Revit, no pyRevit and no network.
"""

import ast
import glob
import os

import pytest

from inventory_support import MUTATION_TOOLS, TOOLS_DIR

PARTIAL = "PARTIAL SUCCESS"
FAILED = "HTTP 422"
ROLLED_BACK = "HTTP 409"

# class -> (required phrases, forbidden phrases)
REQUIRED = {
    "P": (PARTIAL, FAILED, ROLLED_BACK),
    "S": (PARTIAL, ROLLED_BACK),
    "E": (FAILED, ROLLED_BACK),
    "A": (ROLLED_BACK,),
    "EXEMPT": (),
}
FORBIDDEN = {
    "P": (),
    "S": (FAILED,),
    "E": (PARTIAL,),
    "A": (PARTIAL, FAILED),
    "EXEMPT": (PARTIAL, FAILED, ROLLED_BACK),
}

_P_BATCH = ("partial when some items or steps fail; 422 when every input item fails, "
            "or when the single result (a dimension, an MEP system, a view) is not created")
_S_STEPS = ("the created id goes into succeeded as soon as Revit returns it and only "
            "follow-up steps can fail, so a 422 cannot occur")
_E_ONE = "one result per call (export Boolean, file existence, imported id): no partial"
_A_ALL = "all or nothing: every requested element is applied or the transaction rolls back"
_X_NONE = "no transaction, so no rollback, partial or 422"

OUTCOME_CLASSES = {
    "tag_elements": ("P", _P_BATCH),
    "tag_walls": ("P", _P_BATCH),
    "create_dimensions": ("P", _P_BATCH),
    "create_line_based_element": ("P", _P_BATCH),
    "create_surface_based_element": ("P", _P_BATCH),
    "create_level": ("P", _P_BATCH),
    "create_grid": ("P", _P_BATCH),
    "create_structural_framing": ("P", _P_BATCH),
    "color_splash": ("P", _P_BATCH),
    "clear_colors": ("P", _P_BATCH),
    "create_mep_system": ("P", "partial on a failed step; 422 when Revit creates no system"),
    "create_view": ("P", "partial on a failed step; 422 when Revit creates no view"),
    "edit_family": ("P", "partial on a failed item; 422 when every requested parameter fails"),
    "modify_element": ("P", "partial on a failed parameter; 422 when every parameter fails"),
    "create_detail_line": ("S", _S_STEPS),
    "create_duct": ("S", _S_STEPS),
    "create_pipe": ("S", _S_STEPS),
    "create_room": ("S", _S_STEPS),
    "create_schedule": ("S", _S_STEPS),
    "create_sheet": ("S", _S_STEPS),
    "place_family": ("S", _S_STEPS),
    "export_ifc": ("E", _E_ONE),
    "export_document": ("E", _E_ONE),
    "link_file": ("E", _E_ONE),
    "create_room_separation": ("E", "all-or-none boundary lines: no partial"),
    "delete_elements": ("A", _A_ALL),
    "transform_elements": ("A", _A_ALL),
    "set_parameter": ("A", _A_ALL),
    "save_document": ("EXEMPT", _X_NONE),
    "load_family": ("EXEMPT", _X_NONE),
    "set_active_view": ("EXEMPT", _X_NONE),
}


def _tool_docstrings():
    docs = {}
    for path in sorted(glob.glob(os.path.join(TOOLS_DIR, "*_tools.py"))):
        with open(path, "rb") as handle:
            tree = ast.parse(handle.read().decode("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                docs[node.name] = ast.get_docstring(node) or ""
    return docs


DOCSTRINGS = _tool_docstrings()


def test_classification_covers_exactly_the_mutation_tools():
    assert set(OUTCOME_CLASSES) == set(MUTATION_TOOLS)
    assert len(MUTATION_TOOLS) == 31
    counts = {}
    for klass, _ in OUTCOME_CLASSES.values():
        counts[klass] = counts.get(klass, 0) + 1
    assert counts == {"P": 14, "S": 7, "E": 4, "A": 3, "EXEMPT": 3}


@pytest.mark.parametrize("tool", sorted(OUTCOME_CLASSES))
def test_docstring_states_what_the_route_can_return_and_nothing_else(tool):
    klass, why = OUTCOME_CLASSES[tool]
    assert tool in DOCSTRINGS, "tool {} not found in tools/*_tools.py".format(tool)
    doc = DOCSTRINGS[tool]
    missing = [p for p in REQUIRED[klass] if p not in doc]
    over_promised = [p for p in FORBIDDEN[klass] if p in doc]
    assert not missing, "{} (class {}: {}) lacks {}".format(tool, klass, why, missing)
    assert not over_promised, "{} (class {}: {}) promises {}".format(
        tool, klass, why, over_promised)
