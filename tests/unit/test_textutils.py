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

import json
import re

import pytest

from revit_mcp.textutils import (
    build_outcome,
    classify_outcome,
    exception_outcome,
    finalize_outcome,
    normalize_string,
    parse_request_data,
    sanitize_string,
    sanitize_value,
    transaction_status_of,
)


# --- sanitize_value: the parameters.py copy, now shared ---------------------
#
# The copy in parameters.py referenced `unicode` directly. Under IronPython 3
# that is a NameError raised inside its own `except Exception`, so every
# parameter value serialized as "" -- silently, with no log line. These tests
# exist so the shared version cannot regress the same way.

def test_sanitize_value_preserves_cyrillic():
    assert sanitize_value("Стена базовая") == "Стена базовая"


def test_sanitize_value_renders_missing_as_empty_not_unnamed():
    assert sanitize_value(None) == ""


def test_sanitize_value_converts_non_text_without_swallowing_it():
    assert sanitize_value(42) == "42"
    assert sanitize_value(3.5) == "3.5"


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
    """Route modules use `from .utils import sanitize_string`; keep that working.

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

    reexport = re.search(r"from \.textutils import \(?(.+?)\)?\n\n", source, re.DOTALL)
    assert reexport, "revit_mcp/utils.py must re-export the textutils helpers"

    for name in (
        "sanitize_string",
        "normalize_string",
        "sanitize_value",
        "parse_request_data",
    ):
        assert re.search(r"\b{}\b".format(name), reexport.group(1)), (
            "revit_mcp/utils.py must re-export {}, or route modules' "
            "`from .utils import {}` breaks".format(name, name)
        )


# --- parse_request_data: the request-body contract --------------------------
#
# pyRevit parses an application/json body itself and, under IronPython 3, dies
# doing it: routes/server/server.py hands raw bytes to a 3.5-level json.loads.
# That happens in pyRevit's own engine, which the extension cannot patch (tried
# and measured on 2026-09-07), so bridge.py declares text/plain instead and the
# body arrives here unparsed. Every shape below was observed live.

class _IronPython3Json(object):
    """json as IronPython 3 ships it: loads() refuses bytes.

    CPython grew bytes support in 3.6, so a CPython test run cannot reach the
    failure this contract exists for. This stands in for the 3.5-level module
    the Revit half actually runs against, with its exact message.
    """

    def loads(self, payload, *args, **kwargs):
        if not isinstance(payload, str):
            raise TypeError(
                "the JSON object must be str, not {!r}".format(
                    payload.__class__.__name__
                )
            )
        return json.loads(payload, *args, **kwargs)


def test_the_ironpython3_stand_in_reproduces_the_reported_failure():
    """Guard the guard: this is verbatim what users got from every POST route."""
    with pytest.raises(TypeError) as excinfo:
        _IronPython3Json().loads(b'{"a": 1}')
    assert str(excinfo.value) == "the JSON object must be str, not 'bytes'"


def test_parses_the_bytes_body_ironpython3_delivers():
    assert parse_request_data(b'{"code": "print(1)"}') == {"code": "print(1)"}


def test_parses_bytes_without_handing_them_to_json_loads(monkeypatch):
    """The decode has to happen here, not in json -- IronPython 3's would raise."""
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())
    assert parse_request_data(b'{"a": 1}') == {"a": 1}


def test_keeps_cyrillic_payloads_intact():
    """Room names and parameter values on Russian models arrive as UTF-8."""
    body = '{"value": "ИЗ Группирование"}'.encode("utf-8")
    assert parse_request_data(body) == {"value": "ИЗ Группирование"}


def test_parses_the_str_body_ironpython2_delivers():
    assert parse_request_data('{"a": 1}') == {"a": 1}


# pyRevit's engine is a Python 3 runtime that also defines `unicode`, aliased to
# `str`. Detecting the runtime by asking whether `unicode` raises NameError --
# what this module did until 2026-09-07 -- therefore concluded "Python 2"
# there, collapsed both type aliases onto `str`, and stopped matching real
# bytes. A CPython run has no `unicode`, so it took the aliases down the
# correct branch and every test above still passed while the Revit half
# answered 500 to every POST. These two reconstruct that engine.

def _reload_textutils_with(builtin_name, value):
    """Re-import textutils with an extra builtin, as pyRevit's engine has."""
    import builtins
    import importlib

    import revit_mcp.textutils as module

    had = hasattr(builtins, builtin_name)
    previous = getattr(builtins, builtin_name, None)
    setattr(builtins, builtin_name, value)
    try:
        return importlib.reload(module)
    finally:
        if had:
            setattr(builtins, builtin_name, previous)
        else:
            delattr(builtins, builtin_name)
        importlib.reload(module)


def test_runtime_probe_survives_a_unicode_alias_on_python3():
    """`unicode` existing must not be read as "this is Python 2"."""
    reloaded = _reload_textutils_with("unicode", str)
    assert reloaded._BYTES_TYPE is bytes
    assert reloaded._TEXT_TYPE is str


def test_parses_a_bytes_body_when_unicode_is_defined():
    """The live failure: pyRevit's engine, a bytes body, and unicode present."""
    reloaded = _reload_textutils_with("unicode", str)
    assert reloaded.parse_request_data(b'{"file_path": "C:/m.rvt"}') == {
        "file_path": "C:/m.rvt"
    }


def test_passes_a_dict_through_untouched():
    """A client that still sends application/json to a working pyRevit parse."""
    payload = {"a": 1}
    assert parse_request_data(payload) is payload


def test_leaves_a_missing_body_alone():
    """Routes decide for themselves whether no payload is a 400 or a default."""
    assert parse_request_data(None) is None


def test_no_route_module_parses_the_body_by_hand():
    """The old idiom silently returned bytes on IronPython 3; keep it gone."""
    import os

    revit_mcp_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "revit_mcp",
    )
    offenders = []
    for entry in sorted(os.listdir(revit_mcp_dir)):
        if not entry.endswith(".py"):
            continue
        with open(os.path.join(revit_mcp_dir, entry), encoding="utf-8") as handle:
            if "json.loads(request.data)" in handle.read():
                offenders.append(entry)
    assert not offenders, (
        "these modules parse request.data themselves instead of calling "
        "parse_request_data(): {}".format(", ".join(offenders))
    )


def test_the_client_does_not_ask_pyrevit_to_parse_the_body():
    """bridge.py's content type is the other half of the contract."""
    import os

    bridge_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "bridge.py",
    )
    with open(bridge_path, encoding="utf-8") as handle:
        source = handle.read()

    post_call = source[source.index("else:  # POST"):]
    assert '"Content-Type": "text/plain' in post_call, (
        "POSTing application/json makes pyRevit parse the body itself, which "
        "raises TypeError under IronPython 3 before any route handler runs"
    )


# --- honest outcomes (phase 4: D-03 schema, D-04 classifier, D-14 500 outcome) --
#
# classify_outcome is the single place that picks a mutating route's reply status and
# HTTP code. build_outcome fixes the five-key schema and finalize_outcome assembles the
# reply a route returns. They are pure so this truth table can pin them without Revit.

@pytest.mark.parametrize("committed, n_ok, n_bad, expected", [
    (False, 0, 0, ("rolled_back", 409)),
    (False, 3, 0, ("rolled_back", 409)),
    (False, 0, 2, ("rolled_back", 409)),
    (False, 2, 2, ("rolled_back", 409)),
    (True, 0, 0, ("success", 200)),
    (True, 3, 0, ("success", 200)),
    (True, 1, 1, ("partial", 200)),
    (True, 5, 2, ("partial", 200)),
    (True, 0, 1, ("failed", 422)),
    (True, 0, 4, ("failed", 422)),
])
def test_classify_outcome_truth_table(committed, n_ok, n_bad, expected):
    assert classify_outcome(committed, n_ok, n_bad) == expected


def test_build_outcome_has_exactly_the_five_schema_keys():
    outcome = build_outcome("Committed", 2, [1, 2], [], [])
    assert sorted(outcome) == ["failed", "requested", "revit_failures", "succeeded",
                               "transaction_status"]


def test_build_outcome_returns_new_lists_in_input_order_and_keeps_duplicates():
    succeeded = [5, 3, 5]
    failures = [{"severity": "Warning"}]
    outcome = build_outcome("Committed", 3, succeeded, [], failures)
    assert outcome["succeeded"] == [5, 3, 5]
    assert outcome["succeeded"] is not succeeded
    assert outcome["revit_failures"] == failures
    assert outcome["revit_failures"] is not failures


def test_build_outcome_reduces_a_failed_entry_to_item_and_reason_only():
    """A stray key (a body, a secret, a traceback) must not ride along (D-07)."""
    outcome = build_outcome("Committed", 1, [], [
        {"item": 3, "reason": None, "traceback": "x", "_mcp": "s"}], [])
    assert outcome["failed"] == [{"item": 3, "reason": ""}]


def test_build_outcome_keeps_item_types_and_requested_as_given():
    outcome = build_outcome(None, 0, [7], [{"item": "0.name", "reason": "bad"},
                                           {"item": 4, "reason": "worse"}], [])
    assert outcome["failed"][0]["item"] == "0.name"
    assert outcome["failed"][1]["item"] == 4 and isinstance(outcome["failed"][1]["item"], int)
    assert outcome["requested"] == 0
    assert build_outcome(None, None, [], [], [])["requested"] is None


def test_build_outcome_never_sorts_failed_items():
    outcome = build_outcome("Committed", 3, [], [
        {"item": 9, "reason": "a"}, {"item": 2, "reason": "b"}, {"item": 9, "reason": "c"}], [])
    assert [entry["item"] for entry in outcome["failed"]] == [9, 2, 9]


COMMITTED = {"committed": True, "transaction_status": "Committed", "failures": []}


def test_finalize_outcome_success_is_data_plus_status_and_outcome_and_data_is_not_mutated():
    data = {"tagged_count": 2, "tag_ids": [10, 11]}
    before = json.loads(json.dumps(data))
    payload, http = finalize_outcome(COMMITTED, data, 2, [1, 2], [])
    assert http == 200
    assert data == before
    assert payload["status"] == "success"
    assert payload["tagged_count"] == 2 and payload["tag_ids"] == [10, 11]
    assert payload["outcome"] == {"transaction_status": "Committed", "requested": 2,
                                  "succeeded": [1, 2], "failed": [], "revit_failures": []}
    assert "error" not in payload


def test_finalize_outcome_overwrites_a_status_the_route_put_in_data():
    payload, http = finalize_outcome(COMMITTED, {"status": "success"}, 1, [1], [
        {"item": 2, "reason": "r"}])
    assert (payload["status"], http) == ("partial", 200)


def test_finalize_outcome_partial_is_200():
    payload, http = finalize_outcome(COMMITTED, {"message": "m"}, 2, [1], [
        {"item": 2, "reason": "Element not found"}])
    assert http == 200 and payload["status"] == "partial"
    assert payload["message"] == "m"
    assert "error" not in payload


def test_finalize_outcome_all_failed_is_422_with_a_truthy_error_naming_the_count():
    payload, http = finalize_outcome(COMMITTED, {"tagged_count": 0}, 3, [], [
        {"item": 1, "reason": "a"}, {"item": 2, "reason": "b"}, {"item": 3, "reason": "c"}])
    assert http == 422 and payload["status"] == "failed"
    assert payload["error"] and "3" in payload["error"]
    assert payload["tagged_count"] == 0
    assert len(payload["outcome"]["failed"]) == 3


def test_finalize_outcome_422_error_counts_failed_items_when_requested_is_none():
    payload, http = finalize_outcome(COMMITTED, {}, None, [], [{"item": 1, "reason": "a"}])
    assert http == 422 and "1 requested" in payload["error"]


def test_finalize_outcome_empty_call_is_an_honest_success():
    payload, http = finalize_outcome(COMMITTED, {}, 0, [], [])
    assert (payload["status"], http) == ("success", 200)
    assert payload["outcome"]["requested"] == 0
    assert payload["outcome"]["succeeded"] == [] and payload["outcome"]["failed"] == []


@pytest.mark.parametrize("tx_status", ["RolledBack", "Pending", "Error"])
def test_finalize_outcome_not_committed_is_409_rolled_back_with_the_status_verbatim(tx_status):
    commit_result = {"committed": False, "transaction_status": tx_status,
                     "failures": [{"severity": "Error", "description": "d"}]}
    failed = [{"item": 9, "reason": "Element not found"}]
    data = {"tagged_count": 1, "tag_ids": [10]}
    payload, http = finalize_outcome(commit_result, data, 2, [1], failed)
    assert http == 409
    assert sorted(payload) == ["failures", "message", "outcome", "status", "transaction_status"]
    assert payload["status"] == "rolled_back"
    assert payload["transaction_status"] == tx_status
    assert payload["failures"] == commit_result["failures"]
    assert tx_status in payload["message"]
    assert payload["outcome"]["transaction_status"] == tx_status
    assert payload["outcome"]["succeeded"] == []
    assert payload["outcome"]["failed"] == failed
    assert payload["outcome"]["revit_failures"] == commit_result["failures"]


def test_finalize_outcome_only_a_committed_flag_of_true_counts_as_committed():
    for flag in (None, 0, "", "Committed"):
        payload, http = finalize_outcome(
            {"committed": flag, "transaction_status": "Committed", "failures": []},
            {}, 1, [1], [])
        assert http == 409 and payload["status"] == "rolled_back"


class _Transaction(object):
    def __init__(self, status=None, boom=False):
        self._status = status
        self._boom = boom

    def GetStatus(self):
        if self._boom:
            raise RuntimeError("status unreadable")
        return self._status


def test_transaction_status_of_none_is_none():
    assert transaction_status_of(None) is None


def test_transaction_status_of_reads_the_status_as_text():
    assert transaction_status_of(_Transaction("Committed")) == "Committed"


def test_transaction_status_of_is_none_when_the_status_cannot_be_read():
    assert transaction_status_of(_Transaction(boom=True)) is None


def test_exception_outcome_keeps_succeeded_only_for_a_committed_transaction():
    outcome = exception_outcome(_Transaction("Committed"), 2, [5], [{"item": 6, "reason": "r"}])
    assert outcome == {"transaction_status": "Committed", "requested": 2, "succeeded": [5],
                       "failed": [{"item": 6, "reason": "r"}], "revit_failures": []}


@pytest.mark.parametrize("transaction", [
    _Transaction("RolledBack"), _Transaction("Uninitialized"), _Transaction(boom=True), None])
def test_exception_outcome_drops_succeeded_unless_committed(transaction):
    outcome = exception_outcome(transaction, 2, [5], [])
    assert outcome["succeeded"] == []
    assert outcome["transaction_status"] == transaction_status_of(transaction)


def test_exception_outcome_defaults_describe_a_call_that_died_before_any_item():
    outcome = exception_outcome(None)
    assert outcome == {"transaction_status": None, "requested": None, "succeeded": [],
                       "failed": [], "revit_failures": []}


def test_exception_outcome_failed_goes_through_the_reason_reduction():
    outcome = exception_outcome(_Transaction("Committed"), 1, [],
                                [{"item": 1, "reason": "r", "traceback": "secret"}])
    assert outcome["failed"] == [{"item": 1, "reason": "r"}]
