# -*- coding: utf-8 -*-
"""RSN:// path handling on the CPython side.

A complete Revit Server URI must reach Revit untouched: the shared model
journal lives on a network share, and letting an unreachable share turn a
usable path into an error is what made the bridge look unable to open RSN
paths at all.
"""

import pytest

from tools.worksharing_tools import (
    _is_complete_revit_server_path,
    _is_revit_server_path,
    _resolve_revit_server_path,
    _revit_server_path_parts,
)


@pytest.mark.parametrize("path", [
    "RSN://srv-revit/Projects/Tower.rvt",
    "rsn://SRV/Проекты/Башня.rvt",
    "RSN://srv/a/b/c/Model.RVT",
    r"RSN:\\srv\Projects\Tower.rvt",
])
def test_complete_paths_are_recognised(path):
    assert _is_complete_revit_server_path(path)


@pytest.mark.parametrize("path", [
    "RSN://Tower.rvt",          # shorthand: filename only, needs the journal
    "RSN://srv/Projects",       # names no model file
    "RSN://",
    r"C:\Models\Tower.rvt",     # not a Revit Server path at all
    "",
])
def test_incomplete_paths_are_not_recognised(path):
    assert not _is_complete_revit_server_path(path)


def test_backslash_spelling_normalises_to_the_slash_form():
    # Normalisation has to happen before the scheme is stripped, or the
    # separators survive the slice and the path looks like one segment.
    assert _revit_server_path_parts(r"RSN:\\srv\Projects\Tower.rvt") == [
        "srv", "Projects", "Tower.rvt",
    ]


def test_complete_path_bypasses_the_journal(monkeypatch):
    def explode():
        raise OSError("//srv-dfs is unreachable")

    monkeypatch.setattr("tools.worksharing_tools._revit_server_models", explode)
    resolved = _resolve_revit_server_path("rsn://srv-revit/Projects/Tower.rvt")
    assert resolved == "RSN://srv-revit/Projects/Tower.rvt"


def test_backslash_path_bypasses_the_journal_too(monkeypatch):
    def explode():
        raise OSError("//srv-dfs is unreachable")

    monkeypatch.setattr("tools.worksharing_tools._revit_server_models", explode)
    resolved = _resolve_revit_server_path(r"RSN:\\srv\Projects\Tower.rvt")
    assert resolved == "RSN://srv/Projects/Tower.rvt"


def test_local_path_is_passed_through_untouched():
    local = r"C:\Models\Tower.rvt"
    assert not _is_revit_server_path(local)
    assert _resolve_revit_server_path(local) == local
