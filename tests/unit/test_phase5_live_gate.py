# -*- coding: utf-8 -*-
"""Offline tests for the Phase 5 live gate (plans 05-11..05-15).

Needs no Revit, no pyRevit and no network. Canned tool texts use the real
``tools.utils.format_response`` so classifier checks match model-visible text.
"""
import ast
import copy
import importlib.util
import json
import os

import pytest

from revit_mcp.trust import auth_failure, integrity_failure
from tools.utils import format_response

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_PATH = os.path.join(REPO_ROOT, "tests", "test_phase5_live_gate.py")
_spec = importlib.util.spec_from_file_location("phase5_live_gate_procedure", SCRIPT_PATH)
proc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proc)

FP = "a1b2c3d4"
MODULE = "revit_mcp/detail.py"


def _step(kind, route, http, body, text=None):
    return {"kind": kind, "route": route, "sent": True, "http": http,
            "body": body, "text": format_response(body) if text is None else text,
            "error": None}


def _auth(reason):
    body, status = auth_failure(reason)
    assert status == 401
    return body


def _integrity():
    body, status = integrity_failure([proc.PROBE_FILE, MODULE])
    assert status == 423
    return body


def _success():
    return {"status": "success", "outcome": {"transaction_status": "Committed", "requested": 1, "succeeded": [1], "failed": [], "revit_failures": []}}


def _status(stage):
    integrity = {"state": "verified_match", "modified": [], "unexpected": [], "missing": []}
    health = "healthy"
    if stage == "corrupt":
        integrity = {"state": "verified_mismatch", "modified": [MODULE], "unexpected": [proc.PROBE_FILE], "missing": []}
        health = "degraded"
    if stage == "cleanup":
        integrity = {"state": "unverifiable", "reason": "manifest_missing", "modified": [], "unexpected": [], "missing": []}
    result = {"secret": {"configured": True, "fingerprint": FP}, "integrity": integrity,
              "bind": "loopback_only", "health": health}
    if stage == "corrupt": result["security_alerts"] = ["Mutation refused with 423."]
    return result


def _base(stage):
    record = proc.evidence_template(stage)
    record.update({"started_at": "2026-10-25T10:12:00+00:00", "posts_sent": proc.EXPECTED_POSTS[stage]})
    record["inputs"].update({"port": 48884, "stamp": "20261025T101200", "module": None if stage == "match" else MODULE,
                              "names": {"p_create": "P5_P_CREATE_20261025T101200", "n_missing": "P5_N_MISSING_20261025T101200", "n_mismatch": "P5_N_MISMATCH_20261025T101200", "m_create": "P5_M_CREATE_20261025T101200"}})
    record["preflight"].update({"listeners": [4242], "documents": 1, "document": {"id": 1}, "status_http": 200,
                                 "status": _status(stage), "bridge_fingerprint": FP,
                                 "repo": {"secret_file_present": True, "manifest_present": stage != "cleanup", "probe_present": stage == "corrupt", "module_clean": True}})
    return record


def match_ok():
    record = _base("match")
    names = record["inputs"]["names"]
    record["steps"] = {
        "n_missing": _step("direct", "/create_level/", 401, _auth("missing")),
        "n_mismatch": _step("direct", "/create_level/", 401, _auth("mismatch")),
        "n_code": _step("direct", "/execute_code/", 401, _auth("missing")),
        "r_levels_open": _step("direct", "/document_levels/", 200, {"levels": []}),
        "r_levels_wrong": _step("direct", "/document_levels/", 200, {"levels": []}),
        "b_wrong": _step("tool", "/create_level/", None, None, "Error: 401 - " + json.dumps(_auth("mismatch"))),
        "p_create": _step("tool", "/create_level/", 200, _success()),
        "p_levels": _step("direct", "/list_levels/", 200, {"levels": [{"name": names["p_create"]}]}),
        "s_status": _step("tool", "/status/", 200, _status("match"), "Shared secret: both halves hold the same secret (fingerprint a1b2c3d4)."),
    }
    return record


def corrupt_ok():
    record = _base("corrupt")
    failure = _integrity()
    record["steps"] = {
        "n_missing": _step("direct", "/create_level/", 401, _auth("missing")),
        "m_create": _step("tool", "/create_level/", None, None, "Error: 423 - " + json.dumps(failure)),
        "m_code": _step("tool", "/execute_code/", None, None, "Error: 423 - " + json.dumps(failure)),
        "r_levels_open": _step("direct", "/document_levels/", 200, {"levels": []}),
        "p_levels": _step("direct", "/list_levels/", 200, {"levels": []}),
        "s_status": _step("tool", "/status/", 200, _status("corrupt"), "verified_mismatch: revit_mcp/_zz_probe.py, revit_mcp/detail.py"),
    }
    return record


def cleanup_ok():
    record = _base("cleanup")
    name = record["inputs"]["names"]["p_create"]
    record["steps"] = {
        "p_create": _step("tool", "/create_level/", 200, _success()),
        "p_levels": _step("direct", "/list_levels/", 200, {"levels": [{"name": name}]}),
        "s_status": _step("tool", "/status/", 200, _status("cleanup"), "Integrity: unverifiable (manifest_missing)."),
    }
    return record


def _reasons(result):
    return " | ".join(result["reasons"])


def _tree():
    with open(SCRIPT_PATH, "rb") as handle:
        return ast.parse(handle.read().decode("utf-8"))


def test_import_is_inert_and_has_no_pytest_functions():
    for node in _tree().body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): assert not node.name.startswith("test")
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call): pytest.fail("module import call")


def test_encoding_cookie_and_exact_allowlist():
    with open(SCRIPT_PATH, "rb") as handle: assert handle.readline() == b"# -*- coding: utf-8 -*-\n"
    assert proc.ALLOWED_ENDPOINTS == {"/status/", "/documents/", "/list_levels/", "/document_levels/", "/create_level/", "/execute_code/"}


def test_no_forbidden_write_route_strings_anywhere():
    forbidden = ("/save_document/", "/open_model/", "/activate_document/", "/delete_elements/")
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str): assert not any(item in node.value for item in forbidden)


def test_templates_are_empty_fresh_and_unknown_is_rejected():
    record = proc.evidence_template("match")
    assert set(record["steps"]) == set(proc.STEP_IDS["match"])
    assert record["posts_sent"] is None and record["inputs"]["port"] is None
    record["inputs"]["port"] = 7
    assert proc.evidence_template("match")["inputs"]["port"] is None
    with pytest.raises(ValueError): proc.evidence_template("bad")


@pytest.mark.parametrize("stage,factory", [("match", match_ok), ("corrupt", corrupt_ok), ("cleanup", cleanup_ok)])
def test_complete_canned_stage_is_ok(stage, factory):
    assert proc.classify_stage(stage, factory()) == {"stage": stage, "verdict": "ok", "reasons": [], "posts_sent": proc.EXPECTED_POSTS[stage]}


@pytest.mark.parametrize("path,value,needle", [
    (("preflight", "listeners"), [1, 2], "listeners"), (("preflight", "documents"), 2, "documents"),
    (("preflight", "status_http"), 503, "status_http"), (("preflight", "status", "secret", "configured"), False, "configured"),
    (("preflight", "status", "secret", "fingerprint"), "deadbeef", "fingerprint"), (("preflight", "status", "integrity", "state"), "unverifiable", "integrity.state"),
    (("preflight", "status", "bind"), "exposed", "bind"), (("preflight", "status", "health"), "degraded", "health"),
    (("steps", "n_missing", "http"), 200, "n_missing.http"), (("steps", "n_missing", "body", "auth"), "mismatch", "n_missing.body.auth"),
    (("steps", "n_mismatch", "body", "auth"), "missing", "n_mismatch.body.auth"), (("steps", "n_code", "body", "outcome"), {}, "n_code.body.outcome"),
    (("steps", "r_levels_open", "http"), 401, "r_levels_open.http"), (("steps", "r_levels_wrong", "http"), 401, "r_levels_wrong.http"),
    (("steps", "b_wrong", "text"), "wrong", "b_wrong.text"), (("steps", "p_create", "body", "outcome", "transaction_status"), "RolledBack", "p_create.body.outcome.transaction_status"),
    (("steps", "s_status", "text"), "status", "s_status.text"), (("posts_sent",), 6, "posts_sent"), (("stage",), "corrupt", "stage"),
])
def test_match_perturbations_stop_with_named_reason(path, value, needle):
    record = match_ok(); target = record
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    assert needle in _reasons(proc.classify_stage("match", record))


def test_match_rejects_missing_step_rejected_or_missing_level_name():
    record = match_ok(); record["steps"]["n_missing"] = None
    assert "steps.n_missing" in _reasons(proc.classify_stage("match", record))
    record = match_ok(); record["steps"]["p_levels"]["body"]["levels"].append({"name": record["inputs"]["names"]["n_missing"]})
    assert "p_levels.body" in _reasons(proc.classify_stage("match", record))
    record = match_ok(); record["steps"]["p_levels"]["body"] = {"levels": []}
    assert "p_levels.body" in _reasons(proc.classify_stage("match", record))


@pytest.mark.parametrize("record", [None, [], {"stage": "match"}, {"stage": "match", "posts_sent": "7"}])
def test_malformed_records_never_raise(record):
    result = proc.classify_stage("match", record)
    assert result["verdict"] == "stop" and result["reasons"]


@pytest.mark.parametrize("path,value,needle", [
    (("preflight", "status", "integrity", "state"), "verified_match", "integrity.state"), (("preflight", "status", "integrity", "modified"), [], "integrity.modified"),
    (("preflight", "status", "integrity", "unexpected"), [], "integrity.unexpected"), (("preflight", "status", "integrity", "missing"), ["x"], "integrity.missing"),
    (("preflight", "status", "health"), "healthy", "health"), (("preflight", "status", "security_alerts"), [], "security_alerts"),
    (("steps", "n_missing", "http"), 423, "n_missing.http"), (("steps", "m_create", "text"), "Error: 401 - nope", "m_create.text"),
    (("steps", "m_code", "text"), "Error: 200 - nope", "m_code.text"), (("steps", "r_levels_open", "http"), 423, "r_levels_open.http"),
    (("posts_sent",), 3, "posts_sent"), (("preflight", "repo", "probe_present"), False, "probe_present"),
])
def test_corrupt_perturbations_stop(path, value, needle):
    record = corrupt_ok(); target = record
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    assert needle in _reasons(proc.classify_stage("corrupt", record))


def test_corrupt_rejects_blocked_name_and_status_missing_file():
    record = corrupt_ok(); record["steps"]["p_levels"]["body"] = {"levels": [{"name": record["inputs"]["names"]["m_create"]}]}
    assert "p_levels.body" in _reasons(proc.classify_stage("corrupt", record))
    record = corrupt_ok(); record["steps"]["s_status"]["text"] = "verified_mismatch"
    assert "s_status.text" in _reasons(proc.classify_stage("corrupt", record))


@pytest.mark.parametrize("path,value,needle", [
    (("preflight", "status", "integrity", "state"), "verified_match", "integrity.state"), (("preflight", "status", "integrity", "reason"), "read_error", "integrity.reason"),
    (("preflight", "status", "health"), "degraded", "health"), (("preflight", "status", "secret", "fingerprint"), "deadbeef", "fingerprint"),
    (("preflight", "repo", "manifest_present"), True, "manifest_present"), (("preflight", "repo", "probe_present"), True, "probe_present"),
    (("preflight", "repo", "module_clean"), False, "module_clean"), (("steps", "p_create", "http"), 423, "p_create.http"),
    (("steps", "s_status", "text"), "clean", "s_status.text"),
])
def test_cleanup_perturbations_stop(path, value, needle):
    record = cleanup_ok(); target = record
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    assert needle in _reasons(proc.classify_stage("cleanup", record))


def test_cleanup_rejects_missing_restored_name_and_wrong_secret_status():
    record = cleanup_ok(); record["steps"]["p_levels"]["body"] = {"levels": []}
    assert "p_levels.body" in _reasons(proc.classify_stage("cleanup", record))
    record = cleanup_ok(); record["steps"]["p_create"]["http"] = 401
    assert "p_create.http" in _reasons(proc.classify_stage("cleanup", record))


def test_phase_accepts_exactly_one_ok_record_per_stage():
    records = [match_ok(), corrupt_ok(), cleanup_ok()]
    assert proc.classify_phase(records)["verdict"] == "ok"
    assert proc.classify_phase(records[:-1])["verdict"] == "stop"
    assert proc.classify_phase(records + [match_ok()])["verdict"] == "stop"
    broken = copy.deepcopy(records); broken[0]["posts_sent"] = 6
    assert "stage match" in _reasons(proc.classify_phase(broken))


def test_canned_records_round_trip_json_without_losing_acceptance():
    for stage, factory in (("match", match_ok), ("corrupt", corrupt_ok), ("cleanup", cleanup_ok)):
        assert proc.classify_stage(stage, json.loads(json.dumps(factory())))["verdict"] == "ok"
