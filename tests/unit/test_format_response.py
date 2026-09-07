# -*- coding: utf-8 -*-
"""Unit tests for tools/utils.py::format_response.

format_response is the most connected function in the codebase and the one
that already shipped a production bug: before commit c1231f6 it treated any
dict without a "status" key as a failure, so get_revit_model_info returned
valid data under an "=== ERROR DETAILS ===" banner.

The rule these tests lock down: a dict is an error ONLY if it has a truthy
"error" key or a status in error/failed/failure/exception. Every other dict is
data. Adding a new implicit error signal must break these tests.

Needs no Revit.
"""

import pytest

from tools.utils import format_response


# --- the c1231f6 regression -------------------------------------------------

def test_status_less_dict_is_data_not_error():
    """The exact shape that regressed: data-bearing dict with no "status"."""
    out = format_response({"total_elements": 1234, "levels": 18})
    assert "ERROR DETAILS" not in out
    assert "1234" in out


def test_status_less_dict_renders_every_field():
    out = format_response({"total_elements": 7, "rooms": 54})
    assert "Total Elements: 7" in out
    assert "Rooms: 54" in out


def test_falsy_error_key_is_not_an_error():
    """`{"error": None}` and `{"error": ""}` are success, not failure."""
    assert "ERROR DETAILS" not in format_response({"error": None, "count": 3})
    assert "ERROR DETAILS" not in format_response({"error": "", "count": 3})


def test_status_success_is_not_an_error():
    assert "ERROR DETAILS" not in format_response({"status": "success", "count": 1})


# --- what genuinely is an error ---------------------------------------------

def test_truthy_error_key_is_an_error():
    out = format_response({"error": "boom"})
    assert "ERROR DETAILS" in out
    assert "boom" in out


@pytest.mark.parametrize("status", ["error", "failed", "failure", "exception"])
def test_failure_statuses_are_errors(status):
    out = format_response({"status": status, "error": "nope"})
    assert "ERROR DETAILS" in out


@pytest.mark.parametrize("status", ["ERROR", "Failed", "FAILURE"])
def test_failure_status_matching_is_case_insensitive(status):
    assert "ERROR DETAILS" in format_response({"status": status, "error": "nope"})


def test_traceback_is_surfaced_in_its_own_block():
    out = format_response(
        {"status": "error", "error": "bad", "traceback": "Traceback: line 1"}
    )
    assert "=== TRACEBACK ===" in out
    assert "line 1" in out


# --- success key precedence: output > message > result > data ---------------

def test_output_wins_over_message():
    out = format_response({"output": "from-output", "message": "from-message"})
    assert out == "from-output"


def test_message_wins_over_result():
    out = format_response({"message": "from-message", "result": "from-result"})
    assert out == "from-message"


def test_result_wins_over_data():
    out = format_response({"result": "from-result", "data": "from-data"})
    assert out == "from-result"


def test_data_is_used_when_alone():
    assert format_response({"data": "from-data"}) == "from-data"


# --- the status block -------------------------------------------------------

def test_active_status_renders_the_status_block():
    out = format_response(
        {
            "status": "active",
            "health": "healthy",
            "api_name": "revit_mcp",
            "document_title": "Model",
            "revit_available": True,
        }
    )
    assert "=== REVIT STATUS ===" in out
    assert "Document: Model" in out


def test_active_status_surfaces_unknown_fields():
    """New /status/ fields must not vanish -- degraded state has to be visible."""
    out = format_response(
        {
            "status": "active",
            "health": "degraded",
            "domains_registered": 21,
            "failed_domains": {"clash": "ImportError: no module named foo"},
        }
    )
    assert "degraded" in out
    assert "clash" in out


# --- non-dict passthrough ---------------------------------------------------

def test_error_string_from_the_bridge_passes_through():
    """_revit_call collapses every non-200 and every exception to a string."""
    assert format_response("Error: 503 - No active Revit document") == (
        "Error: 503 - No active Revit document"
    )


def test_none_becomes_a_string_rather_than_raising():
    assert format_response(None) == "None"


# --- non-ASCII --------------------------------------------------------------

def test_cyrillic_survives_rendering():
    """Guards the fork's ASCII-mangling regression at the presentation layer."""
    out = format_response({"document_title": "План 1-го этажа", "levels": 3})
    assert "План 1-го этажа" in out


def test_empty_dict_reports_success_rather_than_an_error():
    assert "ERROR DETAILS" not in format_response({})
