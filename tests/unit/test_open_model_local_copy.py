# -*- coding: utf-8 -*-
"""Unit tests for the pure helpers behind open_model's local-copy defaults.

Pins the 2026-10-25 decision (07-CONTEXT.md, Deferred): a workshared central opens
as a new local copy, an existing local copy is renamed with a date-time stamp
instead of being deleted, and when the default open fails the route retries once
with only the "Оси и уровни" workset open. The route module cannot be imported
under CPython, so the decisions live in revit_mcp/textutils.py where they can be
tested.

Needs no Revit and touches no real filesystem.
"""

import datetime

import pytest

from revit_mcp.textutils import (
    AXES_LEVELS_WORKSET_MARKER,
    local_backup_dir,
    local_copy_stamp,
    pick_axes_levels_workset,
    resolve_existing_local_mode,
    stamped_local_paths,
)


def _taken(*paths):
    taken = set(paths)
    return lambda p: p in taken


# ------------------------------------------------------------------ stamp

def test_stamp_is_zero_padded_and_locale_free():
    assert local_copy_stamp(datetime.datetime(2026, 10, 25, 9, 5, 3)) == "20261025_090503"


def test_marker_is_the_lower_case_russian_phrase():
    assert AXES_LEVELS_WORKSET_MARKER == u"оси и уровни"


# ------------------------------------------------------------------ backup dir

def test_backup_dir_forward_slashes():
    assert local_backup_dir("C:/Work/Tower_ivanov.rvt") == "C:/Work/Tower_ivanov_backup"


def test_backup_dir_cyrillic_backslashes():
    assert (local_backup_dir(u"D:\\Проекты\\Башня_иванов.rvt")
            == u"D:\\Проекты\\Башня_иванов_backup")


def test_backup_dir_upper_case_extension():
    assert local_backup_dir("C:\\W\\Model_u.RVT") == "C:\\W\\Model_u_backup"


# ------------------------------------------------------------------ stamped paths

def test_stamped_paths_basic():
    result = stamped_local_paths(
        "C:\\Users\\u\\Documents\\Tower_ivanov.rvt", "20261025_090503", lambda p: False)
    assert result == (
        "C:\\Users\\u\\Documents\\Tower_ivanov_20261025_090503.rvt",
        "C:\\Users\\u\\Documents\\Tower_ivanov_20261025_090503_backup",
    )


def test_stamped_paths_keep_forward_slashes():
    result = stamped_local_paths("C:/Work/Tower_u.rvt", "20261025_090503", lambda p: False)
    assert result == ("C:/Work/Tower_u_20261025_090503.rvt",
                      "C:/Work/Tower_u_20261025_090503_backup")


def test_stamped_paths_unc_keeps_prefix_and_extension_case():
    result = stamped_local_paths(
        u"\\\\srv\\share\\Модель_user.RVT", "20261025_090503", lambda p: False)
    assert result == (u"\\\\srv\\share\\Модель_user_20261025_090503.RVT",
                      u"\\\\srv\\share\\Модель_user_20261025_090503_backup")


def test_stamped_paths_bare_file_name():
    result = stamped_local_paths("Tower_u.rvt", "20261025_090503", lambda p: False)
    assert result == ("Tower_u_20261025_090503.rvt", "Tower_u_20261025_090503_backup")


def test_stamped_paths_cyrillic_stem_survives():
    result = stamped_local_paths(u"C:\\W\\Башня_u.rvt", "20261025_090503", lambda p: False)
    assert result[0] == u"C:\\W\\Башня_u_20261025_090503.rvt"


def test_stamped_paths_rvt_collision_moves_to_suffix_2():
    first = "C:\\W\\Tower_u_20261025_090503.rvt"
    result = stamped_local_paths("C:\\W\\Tower_u.rvt", "20261025_090503", _taken(first))
    assert result == ("C:\\W\\Tower_u_20261025_090503_2.rvt",
                      "C:\\W\\Tower_u_20261025_090503_2_backup")


def test_stamped_paths_backup_folder_collision_moves_to_suffix_2():
    first_backup = "C:\\W\\Tower_u_20261025_090503_backup"
    result = stamped_local_paths("C:\\W\\Tower_u.rvt", "20261025_090503", _taken(first_backup))
    assert result == ("C:\\W\\Tower_u_20261025_090503_2.rvt",
                      "C:\\W\\Tower_u_20261025_090503_2_backup")


def test_stamped_paths_two_taken_gives_suffix_3():
    taken = _taken("C:\\W\\Tower_u_20261025_090503.rvt",
                   "C:\\W\\Tower_u_20261025_090503_2.rvt")
    result = stamped_local_paths("C:\\W\\Tower_u.rvt", "20261025_090503", taken)
    assert result[0] == "C:\\W\\Tower_u_20261025_090503_3.rvt"


def test_stamped_paths_never_return_the_input_and_exhaust_to_none():
    result = stamped_local_paths("C:\\W\\Tower_u.rvt", "20261025_090503", lambda p: True,
                                 limit=5)
    assert result == (None, None)
    free = stamped_local_paths("C:\\W\\Tower_u.rvt", "20261025_090503", lambda p: False)
    assert free[0] != "C:\\W\\Tower_u.rvt"


# ------------------------------------------------------------------ mode resolution

@pytest.mark.parametrize("existing_local, overwrite_local, expected", [
    (None, None, "timestamp"),
    (None, True, "overwrite"),
    (None, False, "error"),
    ("TimeStamp", None, "timestamp"),
    ("overwrite", True, "overwrite"),
    ("timestamp", False, "timestamp"),
    ("error", False, "error"),
])
def test_resolve_mode_accepts(existing_local, overwrite_local, expected):
    assert resolve_existing_local_mode(existing_local, overwrite_local) == (expected, None)


@pytest.mark.parametrize("existing_local, overwrite_local", [
    ("bogus", None),
    (5, None),
    (None, "yes"),
])
def test_resolve_mode_rejects_invalid_values(existing_local, overwrite_local):
    mode, error = resolve_existing_local_mode(existing_local, overwrite_local)
    assert mode is None
    assert error


@pytest.mark.parametrize("existing_local, overwrite_local", [
    ("timestamp", True),
    ("overwrite", False),
])
def test_resolve_mode_conflict_names_both_parameters(existing_local, overwrite_local):
    mode, error = resolve_existing_local_mode(existing_local, overwrite_local)
    assert mode is None
    assert "existing_local" in error and "overwrite_local" in error


def test_resolve_mode_error_lists_the_allowed_values():
    _, error = resolve_existing_local_mode("bogus", None)
    assert "error, overwrite, timestamp" in error


# ------------------------------------------------------------------ axes and levels

def test_pick_finds_the_workset():
    assert pick_axes_levels_workset(["Workset1", u"02_Оси и уровни"]) == u"02_Оси и уровни"


def test_pick_is_case_insensitive():
    assert (pick_axes_levels_workset([u"ОСИ И УРОВНИ (общие)"])
            == u"ОСИ И УРОВНИ (общие)")


def test_pick_treats_underscore_and_whitespace_runs_as_a_space():
    assert pick_axes_levels_workset([u"Оси_и_уровни"]) == u"Оси_и_уровни"
    assert pick_axes_levels_workset([u"Оси  и   уровни"]) == u"Оси  и   уровни"


def test_pick_returns_none_without_a_match():
    assert pick_axes_levels_workset([u"Оси", u"Уровни"]) is None
    assert pick_axes_levels_workset([]) is None
    assert pick_axes_levels_workset([None]) is None


def test_pick_prefers_the_exact_normalised_match():
    assert (pick_axes_levels_workset([u"00 Оси и уровни архив", u"Оси и уровни"])
            == u"Оси и уровни")


def test_pick_takes_the_first_of_several_containing_matches():
    assert (pick_axes_levels_workset([u"A Оси и уровни", u"B Оси и уровни"])
            == u"A Оси и уровни")
