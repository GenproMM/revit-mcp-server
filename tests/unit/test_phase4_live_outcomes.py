# -*- coding: utf-8 -*-
"""Offline tests for the Phase 4 live outcome gate (plan 04-10/04-11).

Needs no Revit, no pyRevit and no network.

The instrument (tests/test_phase4_live_outcomes.py) is run once, by hand, against a
freshly restarted Revit. What can be decided offline is tested here: that only a
complete and self-consistent record classifies as ok, that every perturbation of the
canned record is a stop with a reason naming the field, that the runner refuses
before any request, sends no write after a failed preflight, counts a POST that
raised, and that the script can only ever name the seven allowed routes.

The canned replies below are built from the reply shapes plan 04-01 defines and the
rendered text is produced by the real tools.utils.format_response, so the classifier
is pinned to what the model would actually read. None of this is a live result.
"""

import ast
import asyncio
import copy
import importlib.util
import json
import os

import pytest

from tools.utils import format_response

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_PATH = os.path.join(REPO_ROOT, "tests", "test_phase4_live_outcomes.py")

# Loaded under a different module name: this file is itself named
# test_phase4_live_outcomes, and pytest's basename import would collide.
_spec = importlib.util.spec_from_file_location("phase4_live_outcomes_procedure", SCRIPT_PATH)
proc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proc)

WALL = 1001
TAG_TARGET = 2002
NEW_TAG = 3003
BAD = 999999999
PARAMETER = "Comments"
VALUE = "phase4-live"
VIEW = "Level 1"
PORT = 48884
IFC = "C:/scratch/phase4/out.ifc"


# ------------------------------------------------------------- canned replies


def _outcome(requested, succeeded, failed, status="Committed"):
    return {"transaction_status": status, "requested": requested,
            "succeeded": list(succeeded), "failed": list(failed), "revit_failures": []}


def reply_modify():
    return {"status": "success", "element_id": WALL, "message": "Modified 1 parameter(s)",
            "outcome": _outcome(1, [PARAMETER], [])}


def reply_partial():
    return {"status": "partial", "tagged_count": 1, "tag_ids": [NEW_TAG],
            "skipped": [{"element_id": BAD, "reason": "Element not found"}],
            "outcome": _outcome(2, [TAG_TARGET], [{"item": BAD, "reason": "Element not found"}])}


def reply_all_failed_text():
    body = {"status": "failed", "tagged_count": 0, "tag_ids": [],
            "error": "None of the 1 requested item(s) succeeded; each item and its reason "
                     "is in outcome.failed",
            "outcome": _outcome(1, [], [{"item": BAD, "reason": "Element not found"}])}
    return "Error: 422 - " + json.dumps(body)


def reply_export():
    return {"status": "success", "file_path": IFC, "file_size_kb": 12,
            "outcome": _outcome(1, [IFC], [])}


def reply_delete():
    return {"status": "success", "deleted_count": 1, "deleted_ids": [NEW_TAG],
            "outcome": _outcome(1, [NEW_TAG], [])}


def step(endpoint, body, raw):
    return {"endpoint": endpoint, "body": body, "raw": raw, "rendered": format_response(raw)}


def ok_record():
    s4 = step("/export_ifc/", {"file_path": IFC}, reply_export())
    s4["file_exists"] = True
    return {
        "inputs": {"wall_id": WALL, "parameter": PARAMETER, "value": VALUE, "view_name": VIEW,
                   "tag_id": TAG_TARGET, "ifc_path": IFC, "port": PORT},
        "preflight": {"status_ok": True, "listeners": [4242], "documents": 1,
                      "parameter_writable": True},
        "posts_sent": 5,
        "steps": {
            "s1": step("/modify_element/", {"element_id": WALL, "parameters": {PARAMETER: VALUE}},
                       reply_modify()),
            "s2": step("/tag_elements/", {"element_ids": [TAG_TARGET, BAD], "view_name": VIEW},
                       reply_partial()),
            "s3": step("/tag_elements/", {"element_ids": [BAD], "view_name": VIEW},
                       reply_all_failed_text()),
            "s4": s4,
            "s5": step("/delete_elements/", {"element_ids": [NEW_TAG]}, reply_delete()),
        },
    }


def reasons_text(result):
    return " | ".join(result["reasons"])


# ----------------------------------------------------------- shape of the script


def _tree():
    with open(SCRIPT_PATH, "rb") as handle:
        return ast.parse(handle.read().decode("utf-8"))


def test_script_defines_no_pytest_collectable_name_and_does_nothing_at_import():
    tree = _tree()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert not node.name.startswith("test"), node.name
        if isinstance(node, ast.ClassDef):
            assert not node.name.startswith("Test"), node.name
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            pytest.fail("module-level call: {}".format(ast.dump(node)[:80]))
    guards = [n for n in tree.body if isinstance(n, ast.If)]
    assert len(guards) == 1  # the __main__ guard and nothing else


def test_script_has_the_encoding_cookie_on_line_one():
    with open(SCRIPT_PATH, "rb") as handle:
        first = handle.read().decode("utf-8").splitlines()[0]
    assert first == "# -*- coding: utf-8 -*-"


def test_script_is_outside_pytest_collection_roots():
    # pyproject testpaths is tests/unit; the standalone script lives one level up.
    assert os.path.dirname(SCRIPT_PATH) == os.path.join(REPO_ROOT, "tests")


# ------------------------------------------------------------------ allow-list


def test_allowed_endpoints_are_exactly_the_seven_routes():
    assert proc.ALLOWED_ENDPOINTS == {
        "/status/", "/documents/", "/element_properties/", "/modify_element/",
        "/tag_elements/", "/export_ifc/", "/delete_elements/"}


def test_script_names_neither_the_save_route_nor_the_arbitrary_code_route():
    # Every string constant, docstrings included, so the procedure text cannot name them either.
    forbidden = ("/save_document/", "/execute_code/")
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for name in forbidden:
                assert name not in node.value, (name, node.value[:60])


def test_route_check_refuses_anything_outside_the_allow_list():
    for endpoint in ("/status/", "/documents/", "/modify_element/", "/tag_elements/",
                     "/export_ifc/", "/delete_elements/", "/element_properties/1001"):
        proc._require_allowed(endpoint)
    for endpoint in ("/save_document/", "/execute_code/", "/set_parameter/", "/status", "",
                     "/element_properties_x/1", None, 5):
        with pytest.raises(ValueError):
            proc._require_allowed(endpoint)


def test_bad_id_is_the_agreed_unknown_element():
    assert proc.BAD_ID == 999999999


# ------------------------------------------------------------------- template


def test_evidence_template_has_every_slot_empty():
    template = proc.evidence_template()
    assert set(template) == {"inputs", "preflight", "posts_sent", "steps"}
    assert set(template["inputs"]) == {
        "wall_id", "parameter", "value", "view_name", "tag_id", "ifc_path", "port"}
    assert {"status_ok", "listeners", "documents", "parameter_writable"} <= set(template["preflight"])
    assert set(template["steps"]) == {"s1", "s2", "s3", "s4", "s5"}
    assert template["posts_sent"] is None
    assert all(value is None for value in template["inputs"].values())
    assert all(value is None for value in template["preflight"].values())
    assert all(value is None for value in template["steps"].values())
    json.dumps(template)


def test_evidence_template_is_a_fresh_object_each_call():
    first = proc.evidence_template()
    first["inputs"]["wall_id"] = 7
    assert proc.evidence_template()["inputs"]["wall_id"] is None


def test_the_empty_template_classifies_as_stop():
    result = proc.classify_outcomes(proc.evidence_template())
    assert result["verdict"] == "stop"
    assert result["posts_sent"] is None


# ------------------------------------------------------------------ classifier


def test_the_canned_complete_record_is_ok_and_carries_posts_sent():
    result = proc.classify_outcomes(ok_record())
    assert result == {"verdict": "ok", "reasons": [], "posts_sent": 5}


def test_the_canned_record_survives_a_json_round_trip_as_ok():
    record = json.loads(json.dumps(ok_record(), ensure_ascii=False))
    assert proc.classify_outcomes(record)["verdict"] == "ok"


def test_a_preflight_record_reports_zero_posts_sent():
    record = proc.evidence_template()
    record["posts_sent"] = 0
    result = proc.classify_outcomes(record)
    assert result["verdict"] == "stop" and result["posts_sent"] == 0


def _set(path, value):
    def mutate(record):
        node = record
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return mutate


def _drop(path):
    def mutate(record):
        node = record
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
    return mutate


def _unrender_banner(record):
    record["steps"]["s2"]["rendered"] = "Tagged 1 of 2 elements (999999999 skipped)"


def _unrender_bad_id(record):
    record["steps"]["s2"]["rendered"] = record["steps"]["s2"]["rendered"].replace("999999999", "x")


STOP_CASES = [
    ("listeners-two", _set(["preflight", "listeners"], [1, 2]), "preflight.listeners"),
    ("listeners-none", _set(["preflight", "listeners"], []), "preflight.listeners"),
    ("documents-two", _set(["preflight", "documents"], 2), "preflight.documents"),
    ("documents-zero", _set(["preflight", "documents"], 0), "preflight.documents"),
    ("status-not-ok", _set(["preflight", "status_ok"], False), "preflight.status_ok"),
    ("parameter-not-writable", _set(["preflight", "parameter_writable"], False),
     "preflight.parameter_writable"),
    ("s1-rolled-back", _set(["steps", "s1", "raw", "outcome", "transaction_status"], "RolledBack"),
     "s1"),
    ("s1-status-missing", _drop(["steps", "s1", "raw", "outcome", "transaction_status"]), "s1"),
    ("s1-outcome-missing", _drop(["steps", "s1", "raw", "outcome"]), "s1"),
    ("s1-parameter-not-succeeded", _set(["steps", "s1", "raw", "outcome", "succeeded"], []), "s1"),
    ("s2-status-success", _set(["steps", "s2", "raw", "status"], "success"), "s2"),
    ("s2-failed-missing-bad-id", _set(["steps", "s2", "raw", "outcome", "failed"], []), "s2"),
    ("s2-failed-wrong-reason",
     _set(["steps", "s2", "raw", "outcome", "failed"], [{"item": BAD, "reason": "boom"}]), "s2"),
    ("s2-valid-id-not-succeeded", _set(["steps", "s2", "raw", "outcome", "succeeded"], []), "s2"),
    ("s2-rendered-without-banner", _unrender_banner, "s2.rendered"),
    ("s2-rendered-without-bad-id", _unrender_bad_id, "s2.rendered"),
    ("s3-is-a-200-dict", _set(["steps", "s3", "raw"], {"status": "failed", "outcome": {}}), "s3"),
    ("s3-is-another-error", _set(["steps", "s3", "raw"], "Error: 500 - {}"), "s3"),
    ("s3-body-not-failed",
     _set(["steps", "s3", "raw"], "Error: 422 - " + json.dumps({"status": "success"})), "s3"),
    ("s3-body-unparseable", _set(["steps", "s3", "raw"], "Error: 422 - not json"), "s3"),
    ("s4-file-missing", _set(["steps", "s4", "file_exists"], False), "s4.file_exists"),
    ("s4-file-unrecorded", _drop(["steps", "s4", "file_exists"]), "s4.file_exists"),
    ("s4-succeeded-not-the-path", _set(["steps", "s4", "raw", "outcome", "succeeded"], ["C:/other.ifc"]),
     "s4"),
    ("s4-not-committed", _set(["steps", "s4", "raw", "outcome", "transaction_status"], "RolledBack"), "s4"),
    ("s4-failed-status", _set(["steps", "s4", "raw", "status"], "failed"), "s4"),
    ("s5-missing", _set(["steps", "s5"], None), "s5"),
    ("s5-key-missing", _drop(["steps", "s5"]), "s5"),
    ("s5-rolled-back", _set(["steps", "s5", "raw", "outcome", "transaction_status"], "RolledBack"), "s5"),
    ("s5-not-the-requested-ids", _set(["steps", "s5", "raw", "outcome", "succeeded"], [1]), "s5"),
    ("s5-skipped", _set(["steps", "s5"], {"skipped": "no tag ids were returned by step 2"}), "s5"),
    ("s1-none", _set(["steps", "s1"], None), "s1"),
    ("s2-none", _set(["steps", "s2"], None), "s2"),
    ("s3-none", _set(["steps", "s3"], None), "s3"),
    ("s4-none", _set(["steps", "s4"], None), "s4"),
]


@pytest.mark.parametrize("label,mutate,field", STOP_CASES, ids=[c[0] for c in STOP_CASES])
def test_every_perturbation_is_a_stop_that_names_the_field(label, mutate, field):
    record = ok_record()
    mutate(record)
    result = proc.classify_outcomes(record)
    assert result["verdict"] == "stop", label
    assert any(field in reason for reason in result["reasons"]), (label, result["reasons"])
    assert result["posts_sent"] == 5  # a perturbation never changes what was counted


@pytest.mark.parametrize("junk", [None, [], "text", 7, {}, {"steps": 3}, {"steps": []},
                                  {"inputs": 1, "preflight": 2, "steps": {"s1": 4}}])
def test_classifier_never_raises_on_a_malformed_record(junk):
    result = proc.classify_outcomes(junk)
    assert result["verdict"] == "stop"
    assert isinstance(result["reasons"], list) and result["reasons"]
    assert result["posts_sent"] is None


def _replace_each_node(value, junk):
    yield junk
    if isinstance(value, dict):
        for key in list(value):
            for variant in _replace_each_node(value[key], junk):
                clone = copy.deepcopy(value)
                clone[key] = variant
                yield clone
    elif isinstance(value, list):
        for index in range(len(value)):
            for variant in _replace_each_node(value[index], junk):
                clone = copy.deepcopy(value)
                clone[index] = variant
                yield clone


@pytest.mark.parametrize("junk", [None, 0, True, "", "x", [], {}, [None], 1.5])
def test_classifier_never_raises_when_any_single_node_is_replaced(junk):
    count = 0
    for variant in _replace_each_node(ok_record(), junk):
        result = proc.classify_outcomes(variant)
        assert result["verdict"] in ("ok", "stop")
        assert isinstance(result["reasons"], list)
        count += 1
    assert count > 40


@pytest.mark.parametrize("value", [None, "5", 5.0, True, [], {}])
def test_posts_sent_is_none_unless_the_record_holds_an_int(value):
    record = ok_record()
    record["posts_sent"] = value
    assert proc.classify_outcomes(record)["posts_sent"] is None


def test_posts_sent_absent_is_none_and_does_not_change_the_verdict():
    record = ok_record()
    del record["posts_sent"]
    result = proc.classify_outcomes(record)
    assert result["posts_sent"] is None and result["verdict"] == "ok"


def test_classifier_internal_error_reads_as_stop(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic classifier bug")

    monkeypatch.setattr(proc, "_judge", boom)
    result = proc.classify_outcomes(ok_record())
    assert result["verdict"] == "stop"
    assert "RuntimeError" in reasons_text(result)
    assert result["posts_sent"] == 5


# ----------------------------------------------------------------- repo refusal


def test_outside_repo_is_true_only_for_paths_outside_the_repository(tmp_path):
    assert proc._outside_repo(str(tmp_path / "x.json")) is True
    assert proc._outside_repo(os.path.join(REPO_ROOT, "x.json")) is False
    assert proc._outside_repo(os.path.join(REPO_ROOT, "tests", "unit", "x.json")) is False
    assert proc._outside_repo(os.path.join(REPO_ROOT + "-sibling", "x.json")) is True
