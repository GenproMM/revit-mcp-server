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


# =============================================================================
# Task 2: the runner, the template and classify commands.
#
# The runner is driven through the script's _bridge seam with a fake bridge. The fake
# answers the read-only preflight and the five writes with the canned replies above, and
# records every call so a test can say exactly what was sent and in which order.


class FakeBridge(object):
    def __init__(self, ifc_path=None, owners=(4242,), documents=1, writable=True,
                 post_replies=None, raise_on_post=None, port=PORT, status_reply=None,
                 parameter_present=True, storage_type="String", tag_found=True):
        self.REVIT_PORT = port
        self.owners = list(owners) if owners is not None else None
        self.documents = documents
        self.writable = writable
        self.parameter_present = parameter_present
        self.storage_type = storage_type
        self.tag_found = tag_found
        self.status_reply = status_reply if status_reply is not None else {
            "status": "active", "health": "healthy"}
        self.ifc_path = ifc_path
        self.raise_on_post = raise_on_post  # 1-based POST index that raises
        self.post_replies = post_replies if post_replies is not None else [
            reply_modify(), reply_partial(), reply_all_failed_text(), reply_export(), reply_delete()]
        self.calls = []

    def listener_snapshot(self, ports):
        self.calls.append(("SNAPSHOT", list(ports), None))
        if self.owners is None:
            return None
        return {ports[0]: list(self.owners)}

    async def revit_get(self, endpoint, *args, **kwargs):
        self.calls.append(("GET", endpoint, None))
        if endpoint == "/status/":
            return self.status_reply
        if endpoint == "/documents/":
            docs = [{"document": "doc1.aaaaaaaaaaaa.{}".format(i), "title": "Scratch"}
                    for i in range(self.documents)]
            return {"status": "success", "documents": docs, "count": len(docs)}
        if endpoint == "/element_properties/{}".format(WALL):
            parameters = []
            if self.parameter_present:
                parameters.append({"name": PARAMETER, "value": "", "storage_type": self.storage_type,
                                   "read_only": not self.writable, "is_instance": True})
            return {"status": "success", "element_id": WALL, "category": "Walls",
                    "parameters": parameters, "parameter_count": len(parameters)}
        if endpoint == "/element_properties/{}".format(TAG_TARGET):
            if not self.tag_found:
                return "Error: 404 - " + json.dumps({"error": "Element not found."})
            return {"status": "success", "element_id": TAG_TARGET, "category": "Doors",
                    "parameters": [], "parameter_count": 0}
        raise AssertionError("unexpected GET {}".format(endpoint))

    async def revit_post(self, endpoint, data, *args, **kwargs):
        self.calls.append(("POST", endpoint, copy.deepcopy(data)))
        index = len([c for c in self.calls if c[0] == "POST"])
        if self.raise_on_post == index:
            raise RuntimeError("synthetic transport failure on POST {}".format(index))
        reply = copy.deepcopy(self.post_replies[index - 1])
        if endpoint == "/export_ifc/" and self.ifc_path:
            with open(self.ifc_path, "wb") as handle:
                handle.write(b"ISO-10303-21;")
            if isinstance(reply, dict):  # the route names the path it was given, as the real one does
                reply["file_path"] = data["file_path"]
                reply["outcome"]["succeeded"] = [data["file_path"]]
        return reply

    def posts(self):
        return [(c[1], c[2]) for c in self.calls if c[0] == "POST"]

    def post_endpoints(self):
        return [c[1] for c in self.calls if c[0] == "POST"]


class ExplodingBridge(object):
    """Any use at all fails the test: a refusal must come before the bridge is touched."""

    def __getattr__(self, name):
        raise AssertionError("the bridge was touched ({}) before a refusal".format(name))


def install(monkeypatch, fake):
    monkeypatch.setattr(proc, "_bridge", lambda: fake)
    return fake


def paths(tmp_path, out="record.json", ifc="scratch.ifc"):
    return str(tmp_path / out), str(tmp_path / ifc)


def run_argv(out, ifc, **overrides):
    values = {"--wall-id": str(WALL), "--parameter": PARAMETER, "--value": VALUE,
              "--view-name": VIEW, "--tag-id": str(TAG_TARGET), "--ifc-path": ifc, "--out": out}
    values.update(overrides)
    argv = ["run"]
    for name, value in values.items():
        argv += [name, value]
    return argv


def load_record(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


# ------------------------------------------------------------------- refusals


def _refusal_cases(tmp_path):
    out, ifc = paths(tmp_path)
    existing = tmp_path / "existing.json"
    existing.write_text("{}", encoding="utf-8")
    present_ifc = tmp_path / "present.ifc"
    present_ifc.write_bytes(b"x")
    inside_out = os.path.join(REPO_ROOT, "phase4-record-never-written.json")
    inside_ifc = os.path.join(REPO_ROOT, "phase4-export-never-written.ifc")
    return [
        ("record-exists", run_argv(str(existing), ifc)),
        ("record-inside-repo", run_argv(inside_out, ifc)),
        ("ifc-inside-repo", run_argv(out, inside_ifc)),
        ("ifc-exists", run_argv(out, str(present_ifc))),
        ("ifc-directory-missing", run_argv(out, str(tmp_path / "nope" / "x.ifc"))),
        ("record-directory-missing", run_argv(str(tmp_path / "nope" / "r.json"), ifc)),
        ("ifc-not-absolute", run_argv(out, "relative.ifc")),
        ("ifc-wrong-extension", run_argv(out, str(tmp_path / "x.txt"))),
        ("record-is-the-ifc-path", run_argv(ifc, ifc)),
        ("bad-id-unknown-element", run_argv(out, ifc, **{"--tag-id": str(BAD)})),
        ("blank-parameter", run_argv(out, ifc, **{"--parameter": "  "})),
        ("port-out-of-range", run_argv(out, ifc, **{"--port": "70000"})),
    ]


REFUSAL_LABELS = ["record-exists", "record-inside-repo", "ifc-inside-repo", "ifc-exists",
                  "ifc-directory-missing", "record-directory-missing", "ifc-not-absolute",
                  "ifc-wrong-extension", "record-is-the-ifc-path", "bad-id-unknown-element",
                  "blank-parameter", "port-out-of-range"]


@pytest.mark.parametrize("label", REFUSAL_LABELS)
def test_run_refuses_before_any_request_and_writes_nothing(monkeypatch, tmp_path, capsys, label):
    argv = dict(_refusal_cases(tmp_path))[label]
    install(monkeypatch, ExplodingBridge())
    before = sorted(os.listdir(str(tmp_path)))
    assert proc.main(argv) == 2
    out = capsys.readouterr().out
    assert "PHASE4_OUTCOMES_OK" not in out
    assert sorted(os.listdir(str(tmp_path))) == before
    for leaked in ("phase4-record-never-written.json", "phase4-export-never-written.ifc"):
        assert not os.path.exists(os.path.join(REPO_ROOT, leaked))


def test_run_refusal_of_an_existing_record_leaves_it_untouched(monkeypatch, tmp_path):
    out, ifc = paths(tmp_path)
    with open(out, "wb") as handle:
        handle.write(b'{"keep": "me"}')
    install(monkeypatch, ExplodingBridge())
    assert proc.main(run_argv(out, ifc)) == 2
    with open(out, "rb") as handle:
        assert handle.read() == b'{"keep": "me"}'


def test_run_with_a_missing_required_option_is_a_usage_error_and_sends_nothing(monkeypatch, capsys):
    install(monkeypatch, ExplodingBridge())
    assert proc.main(["run", "--wall-id", "5"]) == 2
    assert proc.main([]) == 2
    assert proc.main(["nonsense"]) == 2
    assert "PHASE4_OUTCOMES_OK" not in capsys.readouterr().out


# ------------------------------------------------------------------ preflight


def _preflight_cases():
    return [
        ("two-listeners", dict(owners=(1, 2)), "preflight.listeners"),
        ("no-listener", dict(owners=()), "preflight.listeners"),
        ("inventory-unavailable", dict(owners=None), "preflight.listeners"),
        ("two-documents", dict(documents=2), "preflight.documents"),
        ("no-document", dict(documents=0), "preflight.documents"),
        ("parameter-read-only", dict(writable=False), "preflight.parameter_writable"),
        ("parameter-absent", dict(parameter_present=False), "preflight.parameter_writable"),
        ("parameter-not-text", dict(storage_type="Integer"), "preflight.parameter_writable"),
        ("status-error", dict(status_reply="Error: 503 - {}"), "preflight.status_ok"),
        ("tag-target-missing", dict(tag_found=False), "preflight.tag_element_found"),
        ("wrong-port", dict(port=48999), "port"),
    ]


@pytest.mark.parametrize("label,fault,field", _preflight_cases(), ids=[c[0] for c in _preflight_cases()])
def test_preflight_failure_sends_no_post_and_records_zero(monkeypatch, tmp_path, capsys, label, fault, field):
    out, ifc = paths(tmp_path)
    fake = install(monkeypatch, FakeBridge(**fault))
    assert proc.main(run_argv(out, ifc)) == 1
    text = capsys.readouterr().out
    assert fake.posts() == []
    assert not os.path.exists(ifc)
    assert "PHASE4_OUTCOMES_STOP" in text and "PHASE4_OUTCOMES_OK" not in text
    assert "POSTS_SENT=0" in text
    assert "consumed" not in text
    assert "nothing was written to the model" in text.lower()
    record = load_record(out)
    assert record["posts_sent"] == 0
    assert record["stop_reason"]
    assert field in record["stop_reason"] or field in text
    assert all(step is None for step in record["steps"].values())


def test_preflight_stop_sends_nothing_and_allows_a_rerun_to_a_fresh_out(monkeypatch, tmp_path, capsys):
    out1, ifc = paths(tmp_path, out="first.json")
    install(monkeypatch, FakeBridge(owners=(1, 2)))
    assert proc.main(run_argv(out1, ifc)) == 1
    first_text = capsys.readouterr().out
    assert "POSTS_SENT=0" in first_text and "fresh --out" in first_text
    assert not os.path.exists(ifc)
    with open(out1, "rb") as handle:
        first_bytes = handle.read()

    # The condition is fixed (one listener now); the same arguments with a fresh --out are not refused.
    out2 = str(tmp_path / "second.json")
    fixed = install(monkeypatch, FakeBridge(ifc_path=ifc))
    assert proc.main(run_argv(out2, ifc)) == 0
    second_text = capsys.readouterr().out
    assert "PHASE4_OUTCOMES_OK" in second_text and "POSTS_SENT=5" in second_text
    assert len(fixed.posts()) == 5
    with open(out1, "rb") as handle:
        assert handle.read() == first_bytes  # the first record is left unchanged
    assert load_record(out2)["posts_sent"] == 5


# ----------------------------------------------------------------- the full run


def test_run_issues_the_five_posts_once_each_in_order(monkeypatch, tmp_path, capsys):
    out, ifc = paths(tmp_path)
    fake = install(monkeypatch, FakeBridge(ifc_path=ifc))
    assert proc.main(run_argv(out, ifc)) == 0
    text = capsys.readouterr().out
    assert fake.post_endpoints() == [
        "/modify_element/", "/tag_elements/", "/tag_elements/", "/export_ifc/", "/delete_elements/"]
    assert "PHASE4_OUTCOMES_OK" in text and "POSTS_SENT=5" in text
    assert "one-shot gate is consumed" in text
    posts = dict(enumerate(fake.posts()))
    assert posts[0][1]["element_id"] == WALL and posts[0][1]["parameters"] == {PARAMETER: VALUE}
    assert posts[1][1]["element_ids"] == [TAG_TARGET, BAD] and posts[1][1]["view_name"] == VIEW
    assert posts[2][1]["element_ids"] == [BAD] and posts[2][1]["view_name"] == VIEW
    assert posts[3][1]["file_path"] == ifc
    assert posts[4][1]["element_ids"] == [NEW_TAG]  # the tag ids step 2's raw reply returned
    record = load_record(out)
    assert record["posts_sent"] == 5
    assert record["steps"]["s4"]["file_exists"] is True
    assert record["inputs"]["ifc_path"] == ifc and record["inputs"]["port"] == PORT
    assert record["preflight"] == {"status_ok": True, "listeners": [4242], "documents": 1,
                                   "parameter_writable": True, "tag_element_found": True}
    assert proc.classify_outcomes(record) == {"verdict": "ok", "reasons": [], "posts_sent": 5}


def test_run_sends_only_allowed_routes_and_never_the_secret_key(monkeypatch, tmp_path):
    out, ifc = paths(tmp_path)
    fake = install(monkeypatch, FakeBridge(ifc_path=ifc))
    assert proc.main(run_argv(out, ifc)) == 0
    assert fake.calls
    for method, endpoint, body in fake.calls:
        if method != "SNAPSHOT":
            proc._require_allowed(endpoint)
        assert "_mcp" not in (body or {})
    with open(out, "rb") as handle:
        assert b"_mcp" not in handle.read()


def test_run_records_the_raw_reply_and_the_rendered_text_of_every_step(monkeypatch, tmp_path):
    out, ifc = paths(tmp_path)
    install(monkeypatch, FakeBridge(ifc_path=ifc))
    assert proc.main(run_argv(out, ifc)) == 0
    record = load_record(out)
    for key in proc.STEP_KEYS:
        recorded = record["steps"][key]
        assert set(recorded) >= {"endpoint", "body", "raw", "rendered"}
    assert record["steps"]["s2"]["raw"] == reply_partial()
    assert record["steps"]["s2"]["rendered"] == format_response(reply_partial())
    assert "=== PARTIAL SUCCESS ===" in record["steps"]["s2"]["rendered"]
    # the 422 stays the bridge's error string, exactly as returned
    assert record["steps"]["s3"]["raw"] == reply_all_failed_text()


def test_run_record_keeps_non_ascii_text_as_utf8(monkeypatch, tmp_path):
    out, ifc = paths(tmp_path)
    fake = install(monkeypatch, FakeBridge(ifc_path=ifc))
    assert proc.main(run_argv(out, ifc, **{"--value": "Проект"})) == 0
    with open(out, "rb") as handle:
        assert "Проект".encode("utf-8") in handle.read()
    assert fake.posts()[0][1]["parameters"] == {PARAMETER: "Проект"}


def test_run_without_new_tag_ids_skips_the_delete_and_is_a_stop(monkeypatch, tmp_path, capsys):
    out, ifc = paths(tmp_path)
    empty = reply_partial()
    empty["tag_ids"] = []
    replies = [reply_modify(), empty, reply_all_failed_text(), reply_export(), reply_delete()]
    fake = install(monkeypatch, FakeBridge(ifc_path=ifc, post_replies=replies))
    assert proc.main(run_argv(out, ifc)) == 1
    text = capsys.readouterr().out
    assert len(fake.posts()) == 4 and "/delete_elements/" not in fake.post_endpoints()
    assert "POSTS_SENT=4" in text and "consumed" in text
    record = load_record(out)
    assert record["posts_sent"] == 4 and "skipped" in record["steps"]["s5"]


def test_run_never_deletes_the_wall_or_the_tagged_element(monkeypatch, tmp_path):
    out, ifc = paths(tmp_path)
    risky = reply_partial()
    risky["tag_ids"] = [WALL, TAG_TARGET, BAD, NEW_TAG, NEW_TAG, "7", True]
    replies = [reply_modify(), risky, reply_all_failed_text(), reply_export(), reply_delete()]
    fake = install(monkeypatch, FakeBridge(ifc_path=ifc, post_replies=replies))
    proc.main(run_argv(out, ifc))
    assert fake.posts()[4][1]["element_ids"] == [NEW_TAG]


def test_run_keeps_going_after_a_failing_reply_and_still_sends_each_step_once(monkeypatch, tmp_path):
    out, ifc = paths(tmp_path)
    replies = [reply_modify(), reply_partial(), reply_all_failed_text(), "Error: 500 - {}", reply_delete()]
    fake = install(monkeypatch, FakeBridge(ifc_path=ifc, post_replies=replies))
    assert proc.main(run_argv(out, ifc)) == 1  # a failing export is a stop, but every step was sent once
    assert len(fake.posts()) == 5


def test_posts_sent_counts_a_raising_post_and_declares_the_gate_consumed(monkeypatch, tmp_path, capsys):
    out, ifc = paths(tmp_path)
    fake = install(monkeypatch, FakeBridge(ifc_path=ifc, raise_on_post=2))
    assert proc.main(run_argv(out, ifc)) == 1
    text = capsys.readouterr().out
    assert len(fake.posts()) == 2  # no third POST after the raise
    assert "PHASE4_OUTCOMES_STOP" in text and "PHASE4_OUTCOMES_OK" not in text
    assert "POSTS_SENT=2" in text
    assert "The one-shot gate is consumed: do not run this again." in text
    record = load_record(out)
    assert record["posts_sent"] == 2  # the raising POST counts: its outcome is unknown
    assert "synthetic transport failure" in record["steps"]["s2"]["exception"]
    assert record["steps"]["s2"]["raw"] is None
    assert record["steps"]["s3"] is None and record["steps"]["s5"] is None
    assert "synthetic transport failure" in record["stop_reason"]
    assert not os.path.exists(ifc)


def test_the_record_is_written_even_when_the_bridge_cannot_be_imported(monkeypatch, tmp_path, capsys):
    out, ifc = paths(tmp_path)

    def broken():
        raise ImportError("synthetic import failure")

    monkeypatch.setattr(proc, "_bridge", broken)
    assert proc.main(run_argv(out, ifc)) == 1
    text = capsys.readouterr().out
    assert "POSTS_SENT=0" in text and "PHASE4_OUTCOMES_STOP" in text
    assert "synthetic import failure" in load_record(out)["stop_reason"]


# --------------------------------------------------------------- plain records


class _TaggedDict(dict):
    pass


class _TaggedStr(str):
    pass


def test_plain_copies_a_provenance_tagged_reply_into_plain_json_types():
    raw = _TaggedDict({"status": "success", "nested": [_TaggedDict({"a": 1})], 5: "int key"})
    raw.revit_provenance = {"pid": 1}
    plain = proc._plain(raw)
    assert type(plain) is dict and type(plain["nested"][0]) is dict
    assert plain["5"] == "int key"
    assert not hasattr(plain, "revit_provenance")
    text = _TaggedStr("Error: 422 - {}")
    text.revit_provenance = {"pid": 1}
    assert type(proc._plain(text)) is str
    assert proc._plain({"_mcp": {"secret": "s"}, "kept": 1}) == {"kept": 1}
    json.dumps(proc._plain({"x": object(), "y": (1, 2)}))


# ------------------------------------------------------------- template / classify


def test_template_command_prints_the_empty_record(capsys):
    assert proc.main(["template"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert {"inputs", "preflight", "posts_sent", "steps"} <= set(printed)
    assert printed == proc.evidence_template()


def test_classify_command_prints_the_token_and_posts_sent(tmp_path, capsys):
    path = tmp_path / "record.json"
    path.write_text(json.dumps(ok_record(), ensure_ascii=False), encoding="utf-8")
    assert proc.main(["classify", str(path)]) == 0
    text = capsys.readouterr().out
    assert "PHASE4_OUTCOMES_OK" in text and "POSTS_SENT=5" in text


def test_classify_command_stop_lists_reasons_and_reports_an_unknown_count(tmp_path, capsys):
    record = ok_record()
    del record["posts_sent"]
    record["steps"]["s4"]["file_exists"] = False
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert proc.main(["classify", str(path)]) == 1
    text = capsys.readouterr().out
    assert "PHASE4_OUTCOMES_STOP" in text and "PHASE4_OUTCOMES_OK" not in text
    assert "POSTS_SENT=unknown" in text
    assert "s4.file_exists" in text


def test_classify_command_unreadable_files_are_a_stop_not_a_traceback(tmp_path, capsys):
    assert proc.main(["classify", str(tmp_path / "does-not-exist.json")]) == 1
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe not json")
    assert proc.main(["classify", str(bad)]) == 1
    text = capsys.readouterr().out
    assert "PHASE4_OUTCOMES_OK" not in text
    assert text.count("PHASE4_OUTCOMES_STOP") == 2 and "POSTS_SENT=unknown" in text
