# -*- coding: utf-8 -*-
"""Unit tests for the D-23 overlap probe's pure logic.

The probe itself (scripts/probe_handler_overlap.py) needs one live pyRevit
Routes instance. What is tested here is everything that can be decided without
one: how a phase's observations are classified, and that the code the probe
generates for Revit is safe for IronPython 3.4 (no f-strings, no CRLF).

Needs no Revit.
"""

import ast
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import probe_handler_overlap as probe  # noqa: E402

MARK_A = "MARK-A-1234abcd"
MARK_B = "MARK-B-1234abcd"
MARK_C = "MARK-C-5678ef01"


def _obs(name, kind, status=200, body="", timed_out=False, error=None, elapsed=0.1):
    return {
        "name": name,
        "kind": kind,
        "status": status,
        "body": body,
        "timed_out": timed_out,
        "error": error,
        "elapsed": elapsed,
    }


def _phase_m(a_body, b_body, **kwargs):
    return [
        _obs("A", "mutation", body=a_body),
        _obs("B", "mutation", body=b_body),
    ]


def test_probe_serialized_when_each_caller_gets_its_own_marker():
    obs = _phase_m('{"output": "%s"}' % MARK_A, '{"output": "%s"}' % MARK_B)
    verdict, reasons = probe.classify_phase(
        obs, {"A": MARK_A, "B": MARK_B}, {"A": 1, "B": 1}
    )
    assert verdict == "serialized"
    assert reasons == []


def test_probe_swapped_mutation_marker_is_cross_wired_mutation():
    obs = _phase_m('{"output": "%s"}' % MARK_B, '{"output": "%s"}' % MARK_B)
    verdict, reasons = probe.classify_phase(
        obs, {"A": MARK_A, "B": MARK_B}, {"A": 1, "B": 1}
    )
    assert verdict == "cross-wired-mutation"
    assert reasons


def test_probe_read_holding_a_marker_is_cross_wired_read():
    obs = [
        _obs("C", "mutation", body='{"output": "%s"}' % MARK_C),
        _obs("levels", "read", body='{"output": "%s"}' % MARK_C),
    ]
    verdict, reasons = probe.classify_phase(obs, {"C": MARK_C}, {"C": 1})
    assert verdict == "cross-wired-read"
    assert reasons


def test_probe_mutation_with_read_shaped_answer_is_cross_wired_read():
    obs = [
        _obs("C", "mutation", body='{"levels": []}'),
        _obs("levels", "read", body='{"levels": []}'),
    ]
    verdict, _reasons = probe.classify_phase(obs, {"C": MARK_C}, {"C": 1})
    assert verdict == "cross-wired-read"


def test_probe_double_execution_is_duplicate_run():
    obs = _phase_m('{"output": "%s"}' % MARK_A, '{"output": "%s"}' % MARK_B)
    verdict, reasons = probe.classify_phase(
        obs, {"A": MARK_A, "B": MARK_B}, {"A": 2, "B": 1}
    )
    assert verdict == "duplicate-run"
    assert any("A" in r for r in reasons)


def test_probe_timeout_is_hang():
    obs = [
        _obs("A", "mutation", body='{"output": "%s"}' % MARK_A),
        _obs("B", "mutation", status=None, timed_out=True, error="timeout"),
    ]
    verdict, _reasons = probe.classify_phase(
        obs, {"A": MARK_A, "B": MARK_B}, {"A": 1, "B": 0}
    )
    assert verdict == "hang"


def test_probe_d27_trigger_only_when_read_phase_not_serialized():
    assert probe.d27_triggered("serialized") is False
    for verdict in (
        "cross-wired-read",
        "cross-wired-mutation",
        "hang",
        "duplicate-run",
        "missing-run",
        "lost-output",
        "error",
    ):
        assert probe.d27_triggered(verdict) is True


def test_probe_generated_code_is_ironpython_safe():
    log_path = "C:\\Users\\Some User\\AppData\\Local\\Temp\\rmcp_overlap_1234abcd.log"
    code = probe.build_code("A", "1234abcd", log_path, 4.0)
    tree = ast.parse(code)
    assert not any(isinstance(node, ast.JoinedStr) for node in ast.walk(tree))
    assert "\r" not in code
    assert MARK_A in code
    assert repr(log_path) in code
    assert "time.sleep" in code
    # No sleep when the caller asks for none.
    assert "time.sleep" not in probe.build_code("B", "1234abcd", log_path, 0)
