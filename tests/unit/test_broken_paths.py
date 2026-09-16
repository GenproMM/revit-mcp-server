# -*- coding: utf-8 -*-
"""Broken-Windows-path detection, in both runtimes' copies of the helper.

The bug these guard against reads as a Unicode failure and is not one: a
Cyrillic path survives the bridge intact, but a path written into a non-raw
string literal loses every backslash that forms a recognised escape, so a
segment like "10_bim_lab" arrives carrying a backspace. Revit then answers
"not found" for a file that is plainly there.
"""

import pytest

from revit_mcp.textutils import describe_broken_path as revit_side
from tools.utils import describe_broken_path as mcp_side

BOTH = pytest.mark.parametrize("describe", [revit_side, mcp_side],
                               ids=["revit_mcp", "tools"])

BS = chr(92)
CYRILLIC_DIR = "\u043e\u0431\u0449\u0438\u0435 \u0434\u0438\u0441\u043a\u0438"


@BOTH
def test_well_formed_cyrillic_path_is_not_flagged(describe):
    """The reported path, correctly escaped, must pass untouched."""
    good = BS.join(["G:", CYRILLIC_DIR, "10_bim_lab", "4_plugins", "nak.rvt"])
    assert describe(good) is None


@BOTH
def test_forward_slash_path_is_not_flagged(describe):
    assert describe("G:/" + CYRILLIC_DIR + "/nak.rvt") is None


@BOTH
def test_plain_ascii_path_is_not_flagged(describe):
    assert describe(BS.join(["C:", "Models", "Tower.rvt"])) is None


@BOTH
def test_backspace_from_escaped_one_is_detected(describe):
    """An escaped 1 collapses to U+0008 -- the exact reported failure."""
    mangled = "G:" + BS + CYRILLIC_DIR + "\x08" + "0_bim_lab" + BS + "nak.rvt"
    problem = describe(mangled)
    assert problem is not None
    assert "U+0008" in problem


@BOTH
def test_newline_from_escaped_n_is_detected(describe):
    """A filename starting with n is the classic case."""
    problem = describe("G:" + BS + "models" + "\n" + "ak.rvt")
    assert problem is not None
    assert "U+000A" in problem


@BOTH
def test_message_names_the_real_cause_not_unicode(describe):
    problem = describe("C:" + BS + "models" + "\n" + "ak.rvt")
    assert "not a Unicode problem" in problem
    assert "forward slashes" in problem


@BOTH
def test_every_reported_position_is_a_real_control_char(describe):
    mangled = "G:" + BS + "a" + "\x08" + "b" + "\t" + "c" + "\n" + "d.rvt"
    problem = describe(mangled)
    for code in ("U+0008", "U+0009", "U+000A"):
        assert code in problem


@BOTH
def test_non_string_input_returns_none(describe):
    assert describe(None) is None
    assert describe(123) is None


@BOTH
def test_empty_string_returns_none(describe):
    assert describe("") is None


def test_both_runtimes_agree():
    """The two copies are duplicated by the Two-Runtime Rule; keep them in step."""
    samples = [
        BS.join(["G:", CYRILLIC_DIR, "nak.rvt"]),
        "G:" + BS + "a" + "\x08" + "b.rvt",
        "G:/ok/path.rvt",
        "",
    ]
    for sample in samples:
        a, b = revit_side(sample), mcp_side(sample)
        assert (a is None) == (b is None)
        if a is not None:
            assert a == b
