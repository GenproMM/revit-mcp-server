# -*- coding: utf-8 -*-
"""Unit tests for revit_mcp/textutils.py.

These helpers used to live in revit_mcp/utils.py, which imports pyRevit and so
could never be imported outside Revit -- leaving the single most bug-prone
function in the extension untested. The fork shipped an ASCII-folding
sanitize_string (commit bb7cda2, under a commit title about ElementId) that
turned every Cyrillic level, wall, family and parameter name into "?????" on
Russian-language models, and a second independent copy of the same bug lived in
revit_mcp/parameters.py.

The first two tests are that regression. They must never pass again by
accident.

Needs no Revit.
"""

from revit_mcp.textutils import normalize_string, sanitize_string


# --- the bb7cda2 regression -------------------------------------------------

def test_cyrillic_is_preserved_not_folded_to_question_marks():
    assert sanitize_string("План 1-го этажа") == "План 1-го этажа"


def test_cyrillic_parameter_names_survive():
    for name in ("GP_Этаж", "GP_Номер корпуса", "Код по классификатору"):
        assert sanitize_string(name) == name


def test_mixed_scripts_are_preserved():
    assert sanitize_string("Level 1 — Этаж 1 (寸法)") == "Level 1 — Этаж 1 (寸法)"


# --- None and non-string input ----------------------------------------------

def test_none_becomes_unnamed():
    assert sanitize_string(None) == "Unnamed"
    assert normalize_string(None) == "Unnamed"


def test_numbers_are_coerced_to_text():
    assert sanitize_string(42) == "42"
    assert sanitize_string(3.5) == "3.5"


def test_empty_string_stays_empty():
    """Empty is a real value; only None is "Unnamed"."""
    assert sanitize_string("") == ""


# --- bytes ------------------------------------------------------------------

def test_utf8_bytes_are_decoded():
    assert sanitize_string("Этаж".encode("utf-8")) == "Этаж"


def test_undecodable_bytes_are_replaced_rather_than_raising():
    """One bad name must never sink a whole listing."""
    out = sanitize_string(b"\xff\xfe bad")
    assert isinstance(out, str)
    assert "bad" in out


# --- normalize_string -------------------------------------------------------

def test_normalize_trims_surrounding_whitespace():
    assert normalize_string("  Этаж 1  ") == "Этаж 1"


def test_normalize_keeps_interior_whitespace():
    assert normalize_string("  План 1-го этажа  ") == "План 1-го этажа"


def test_normalize_of_whitespace_only_is_empty():
    assert normalize_string("   ") == ""


def test_normalize_matches_sanitize_then_strip():
    for value in ("Этаж", "  Этаж  ", "", "Level 1"):
        assert normalize_string(value) == sanitize_string(value).strip()


# --- utils.py re-export contract --------------------------------------------

def test_utils_reexports_the_helpers():
    """Route modules use `from utils import sanitize_string`; keep that working.

    revit_mcp/utils.py itself needs pyRevit and cannot be imported here, so the
    re-export is verified against the source text.
    """
    import os

    utils_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "revit_mcp",
        "utils.py",
    )
    with open(utils_path, encoding="utf-8") as handle:
        source = handle.read()

    assert "from textutils import sanitize_string, normalize_string" in source, (
        "revit_mcp/utils.py must re-export the text helpers, or every route "
        "module's `from utils import sanitize_string` breaks"
    )
