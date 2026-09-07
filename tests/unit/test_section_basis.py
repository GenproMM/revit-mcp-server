# -*- coding: utf-8 -*-
"""Guard the section view's basis-vector handedness.

Revit accepts a section box only when its transform is right-handed, meaning
BasisX == BasisY.CrossProduct(BasisZ). view_management.py assigns
BasisX=right, BasisY=up, BasisZ=direction, so `right` has to come from
up x direction.

Crossing the operands the other way -- direction x up, which the route did
until 2026-09-08 -- produces BasisZ x BasisY. That is the negation, so the
determinant is -1 for *every* perpendicular input, and
ViewSection.CreateSection throws an ArgumentException carrying no message at
all. The route reported `"error": ""` and no section view was ever created by
any payload.

The check is on the source text because revit_mcp/view_management.py imports
pyRevit and cannot be imported under CPython, and because a re-implementation
of the cross products here would only test itself. The determinant test below
is what establishes that the ordering the source is asserted to use is in fact
the right-handed one.

Needs no Revit.
"""

import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE = os.path.join(REPO_ROOT, "revit_mcp", "view_management.py")


def _section_branch():
    """The `elif view_type == "section":` block, up to the next branch."""
    with open(SOURCE, encoding="utf-8") as handle:
        source = handle.read()
    start = source.index('elif view_type == "section":')
    end = source.index('elif view_type == "3d":', start)
    return source[start:end]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _determinant(x, y, z):
    return sum(xi * ci for xi, ci in zip(x, _cross(y, z)))


@pytest.mark.parametrize(
    "direction,up",
    [
        ((0, 1, 0), (0, 0, 1)),   # the default payload
        ((1, 0, 0), (0, 0, 1)),
        ((0, -1, 0), (0, 0, 1)),
        ((0, 0, 1), (0, 1, 0)),
    ],
)
def test_up_cross_direction_is_the_right_handed_ordering(direction, up):
    """up x direction gives determinant +1; direction x up always gives -1."""
    right = _cross(up, direction)
    assert _determinant(right, up, direction) == pytest.approx(1.0)

    flipped = _cross(direction, up)
    assert _determinant(flipped, up, direction) == pytest.approx(-1.0)


def test_section_branch_crosses_up_into_direction():
    """The ordering Revit accepts. Reversing it breaks every section request."""
    branch = _section_branch()
    assert "up_vec.CrossProduct(dir_vec)" in branch


def test_section_branch_does_not_cross_direction_into_up():
    """The exact regression: it failed silently, with an empty error message."""
    branch = _section_branch()
    assert "dir_vec.CrossProduct(up_vec)" not in branch


def test_section_branch_rejects_parallel_direction_and_up():
    """Normalizing a zero-length cross product raises deep in the Revit API."""
    branch = _section_branch()
    assert "GetLength()" in branch, (
        "a parallel direction/up pair must be caught and returned as a 400, "
        "not left to Normalize()"
    )
