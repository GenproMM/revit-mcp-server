# -*- coding: utf-8 -*-
"""Unit twin of tests/test_phase6_live_audit.py: the pure classifiers and refusals on canned records. Needs no Revit.

The instrument (tests/test_phase6_live_audit.py) is run once, by a human, against real
Revit instances (plan 06-07). What can be decided offline is decided here: that only a
complete and self-consistent record classifies as ok, that every perturbation of the
canned records is a stop with a reason naming the field, that no reason ever carries the
secret, and that the refusals protecting the one-shot gate fire before anything is sent.

The canned audit entries are hand-built in the shape of audit.py "Schema 1". None of this
is a live result.
"""

import ast
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from argparse import Namespace
from types import SimpleNamespace

import pytest

import audit
import bridge
from audit_support import (
    PID_A, PID_B, PORT_A, PORT_B, PREFIX, SEL_A, SEL_B, make_machine, release_machine)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_PATH = os.path.join(REPO_ROOT, "tests", "test_phase6_live_audit.py")

# Loaded under a private module name: this file is itself named test_phase6_live_audit,
# and pytest's basename import would collide with the script's name.
_spec = importlib.util.spec_from_file_location("phase6_live_audit_procedure", SCRIPT_PATH)
proc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proc)

SECRET = "Zq7!pX-live-secret-9f8e7d6c5b4a"
WALL, TAG, BAD = 1001, 2002, 999999999
WALL_A, WALL_B = 1101, 1202
PARAM = "Comments"
VIEW = "Level 1"
CODE = "# откат\nraise Exception('rehearsed')\n"
REVIT_PID, REVIT_A, REVIT_B = 4242, 4242, 4343
SERVER_PID, CHILD_PID = 5151, 6262
SESSION = "11111111-1111-4111-8111-111111111111"
DOC = {"token": "doc1.aaaaaaaaaaaa.1", "title": "Scratch", "path": "C:/scratch/a.rvt"}
K = 2


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_name(pid, suffix=""):
    return "audit-20261025-101500-{}{}.jsonl".format(pid, suffix)


def line_of(entry):
    return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))


def entry(call_id, tool, route, outcome, status, tx="Committed", succeeded=None, failed=None,
          server_pid=SERVER_PID, process_pid=REVIT_PID, user_request=None, args=None,
          document=DOC, mutation=True, method="POST", **extra):
    succeeded = [] if succeeded is None else succeeded
    failed = [] if failed is None else failed
    built = {
        "ts": "2026-10-25T10:15:00.123Z", "schema": 1, "call_id": call_id, "tool": tool,
        "route": route, "route_arg": None, "method": method, "mutation": mutation,
        "kind": "received", "http_status": status, "outcome": outcome,
        "transaction_status": tx, "requested": 1, "succeeded": succeeded,
        "succeeded_count": len(succeeded), "failed": failed, "failed_count": len(failed),
        "revit_failures": [],
        "process": {"pid": process_pid, "port": 48884, "session_token": SESSION,
                    "revit_version": "2024"},
        "corroborated": True,
        "requested_target": {"address": "127.0.0.1:48884", "pid": process_pid},
        "document": document, "document_source": "reply_document", "document_role": "used",
        "windows_user": "DOM\\user", "args": args or {},
        "user_request": user_request, "user_request_missing": user_request is None,
        "user_request_length": len(user_request) if user_request else None,
        "user_request_source": "assistant" if user_request else None,
        "server_pid": server_pid, "duration_ms": 12,
    }
    built.update(extra)
    return built


def read_entry(server_pid=SERVER_PID, path="/documents/"):
    """A preflight read made outside any tool call: tool null, not a mutation."""
    return entry(str(uuid.uuid4()), None, path, "success", 200, tx=None, mutation=False,
                 method="GET", server_pid=server_pid, user_request=None)


def reply_for(call_id, text="done"):
    return "{}\nAudit: call_id {}".format(text, call_id)


# ------------------------------------------------------------- canned single record


def single_parts():
    ids = dict((key, str(uuid.uuid4())) for key in ("w1", "w2", "w3"))
    ur = {"w1": "phase6 w1 rollback", "w2": "phase6 w2 partial", "w3": "phase6 w3 success"}
    entries = {
        "w1": entry(ids["w1"], "execute_revit_code", "/execute_code/", "rolled_back", 409,
                    tx="RolledBack", user_request=ur["w1"], args={"code": CODE},
                    code_length=len(CODE), code_sha256=sha(CODE)),
        "w2": entry(ids["w2"], "tag_elements", "/tag_elements/", "partial", 200,
                    succeeded=[TAG], failed=[{"item": BAD, "reason": "Element not found"}],
                    user_request=ur["w2"], args={"element_ids": [TAG, BAD], "view_name": VIEW}),
        "w3": entry(ids["w3"], "set_parameter", "/set_parameter/", "success", 200,
                    succeeded=[PARAM], user_request=ur["w3"],
                    args={"element_id": WALL, "parameter_name": PARAM, "value": "phase6-live"}),
    }
    return {
        "ids": ids, "ur": ur, "entries": entries,
        "extra": [read_entry(), read_entry(path="/element_properties/")],
        "replies": dict((key, reply_for(ids[key])) for key in ids),
        "steps": {
            "w1": {"tool": "execute_revit_code", "user_request": ur["w1"], "exception": None,
                   "arguments": {"code": CODE, "user_request": ur["w1"]}},
            "w2": {"tool": "tag_elements", "user_request": ur["w2"], "exception": None,
                   "arguments": {"element_ids": [TAG, BAD], "view_name": VIEW,
                                 "user_request": ur["w2"]}},
            "w3": {"tool": "set_parameter", "user_request": ur["w3"], "exception": None,
                   "arguments": {"element_id": WALL, "parameter_name": PARAM,
                                 "value": "phase6-live", "user_request": ur["w3"]}},
        },
        "revit_pids": [REVIT_PID], "posts_sent": 3, "secret_lines": [], "line_end": "",
    }


def render_single(parts):
    lines = [line_of(e) for e in parts["extra"]]
    lines += [line_of(parts["entries"][key]) for key in ("w1", "w2", "w3") if key in parts["entries"]]
    lines += list(parts["secret_lines"])
    lines = [line + parts["line_end"] for line in lines]
    record = proc.evidence_template()
    record.update({
        "stage": "single",
        "inputs": {"wall_id": WALL, "parameter": PARAM, "view_name": VIEW, "tag_id": TAG,
                   "rollback_code": CODE, "port": 48884, "wall_a": None, "wall_b": None,
                   "count": None, "audit_dir": "C:/scratch/audit-single"},
        "preflight": {"status_ok": True, "listeners": [REVIT_PID], "documents": 1,
                      "parameter_writable": True, "tag_element_found": True,
                      "selector": "revit1:abc", "targets": None},
        "steps": dict(parts["steps"], parent=[], child=[]),
        "replies": dict(parts["replies"]),
        "audit_files": {file_name(SERVER_PID): lines},
        "revit_pids": list(parts["revit_pids"]),
        "server_pids": {"parent": SERVER_PID, "child": None},
        "posts_sent": parts["posts_sent"],
    })
    return record


def ok_single():
    return render_single(single_parts())


# --------------------------------------------------------------- canned dual record


def dual_parts():
    parts = {"entries": {}, "calls": {"parent": [], "child": []}, "replies": {},
             "extra": {"parent": [read_entry()], "child": []}, "secret_lines": [],
             "line_end": "", "order": []}
    for who, pid in (("parent", SERVER_PID), ("child", CHILD_PID)):
        for index, (revit_pid, wall) in enumerate(((REVIT_A, WALL_A), (REVIT_B, WALL_B))):
            for i in range(1, K + 1):
                key = "{}-{}-{}".format(who, index, i)
                call_id = str(uuid.uuid4())
                value = "phase6-dual-{}-{}".format(pid, i)
                ur = "phase6 dual {}".format(key)
                parts["entries"][key] = entry(
                    call_id, "set_parameter", "/set_parameter/", "success", 200,
                    succeeded=[PARAM], server_pid=pid, process_pid=revit_pid, user_request=ur,
                    args={"element_id": wall, "parameter_name": PARAM, "value": value})
                parts["calls"][who].append({
                    "key": key, "tool": "set_parameter", "pid": revit_pid, "element_id": wall,
                    "value": value, "user_request": ur, "exception": None,
                    "arguments": {"element_id": wall, "parameter_name": PARAM, "value": value,
                                  "user_request": ur}})
                parts["replies"][key] = reply_for(call_id)
                parts["order"].append((who, key))
    return parts


def render_dual(parts):
    record = proc.evidence_template()
    files = {}
    for who, pid in (("parent", SERVER_PID), ("child", CHILD_PID)):
        lines = [line_of(e) for e in parts["extra"][who]]
        lines += [line_of(parts["entries"][key]) for w, key in parts["order"]
                  if w == who and key in parts["entries"]]
        files[file_name(pid)] = [line + parts["line_end"] for line in lines]
    for name, lines in parts.get("more_files", {}).items():
        files[name] = lines
    for name in parts.get("drop_files", ()):
        files.pop(name, None)
    files[file_name(SERVER_PID)].extend(parts["secret_lines"])
    record.update({
        "stage": "dual",
        "inputs": {"wall_id": None, "parameter": PARAM, "view_name": None, "tag_id": None,
                   "rollback_code": None, "port": 48884, "wall_a": WALL_A, "wall_b": WALL_B,
                   "count": K, "audit_dir": "C:/scratch/audit-dual"},
        "preflight": {"status_ok": True, "listeners": None, "documents": None,
                      "parameter_writable": True, "tag_element_found": None, "selector": None,
                      "targets": [{"pid": REVIT_A, "port": 48884}, {"pid": REVIT_B, "port": 48885}]},
        "steps": {"w1": None, "w2": None, "w3": None,
                  "parent": copy.deepcopy(parts["calls"]["parent"]),
                  "child": copy.deepcopy(parts["calls"]["child"])},
        "replies": dict(parts["replies"]),
        "audit_files": files,
        "revit_pids": [REVIT_A, REVIT_B],
        "server_pids": {"parent": SERVER_PID, "child": CHILD_PID},
        "posts_sent": 4 * K,
    })
    return record


def ok_dual():
    return render_dual(dual_parts())


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
    assert os.path.dirname(SCRIPT_PATH) == os.path.join(REPO_ROOT, "tests")


def test_importing_the_script_prints_nothing_touches_nothing_and_defines_no_test_name(tmp_path):
    code = (
        "import importlib.util, os, sys\n"
        "before = os.environ.get('REVIT_MCP_AUDIT_DIR')\n"
        "s = importlib.util.spec_from_file_location('p6', {path!r})\n"
        "m = importlib.util.module_from_spec(s)\n"
        "s.loader.exec_module(m)\n"
        "assert os.environ.get('REVIT_MCP_AUDIT_DIR') == before\n"
        "assert 'bridge' not in sys.modules and 'main' not in sys.modules and 'audit' not in sys.modules\n"
        "print([n for n in dir(m) if n.startswith('test_')], m.SENTINEL_OK, m.SENTINEL_STOP, end='')\n"
    ).format(path=SCRIPT_PATH)
    env = dict(os.environ)
    env.pop("REVIT_MCP_AUDIT_DIR", None)
    done = subprocess.run([sys.executable, "-I", "-c", code], env=env, capture_output=True,
                          text=True, timeout=60, cwd=str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert done.stdout == "[] PHASE6_AUDIT_OK PHASE6_AUDIT_STOP"
    assert done.stderr == ""


def test_constants_are_the_agreed_values():
    assert proc.BAD_ID == 999999999
    assert proc.DEFAULT_PORT == 48884
    assert (proc.DEFAULT_COUNT, proc.MAX_COUNT) == (5, 20)
    assert proc.ALLOWED_READS == {"/status/", "/documents/", "/element_properties/"}
    assert proc.ALLOWED_TOOLS == {"execute_revit_code", "tag_elements", "set_parameter"}
    found = proc.AUDIT_LINE.findall("text\nAudit: call_id 12345678-1234-4234-8234-123456789abc")
    assert found == ["12345678-1234-4234-8234-123456789abc"]


def test_script_names_neither_the_save_route_nor_the_open_route():
    # Every string constant, docstrings included: the procedure text may say the script never
    # saves or opens a model, but it may not name either route.
    forbidden = ("/save_document/", "/open_model/")
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for name in forbidden:
                assert name not in node.value, (name, node.value[:60])


# ------------------------------------------------------------------- template


def test_evidence_template_has_every_slot_empty():
    template = proc.evidence_template()
    assert {"stage", "inputs", "preflight", "steps", "replies", "audit_files", "revit_pids",
            "posts_sent"} <= set(template)
    assert template["posts_sent"] == 0
    assert template["stage"] is None
    assert template["replies"] == {} and template["audit_files"] == {}
    assert template["revit_pids"] == []
    assert {"w1", "w2", "w3", "parent", "child"} <= set(template["steps"])
    json.dumps(template)


def test_evidence_template_is_a_fresh_object_each_call():
    first = proc.evidence_template()
    first["replies"]["w1"] = "x"
    first["steps"]["parent"].append(1)
    again = proc.evidence_template()
    assert again["replies"] == {} and again["steps"]["parent"] == []


def test_the_empty_template_classifies_as_stop_for_both_stages():
    template = proc.evidence_template()
    assert proc.classify_single(template, SECRET)["verdict"] == "stop"
    assert proc.classify_dual(template, SECRET)["verdict"] == "stop"


# ------------------------------------------------------------ secret occurrences


def test_secret_occurrences_counts_the_whole_secret_the_escaped_form_and_16_char_runs():
    assert proc.secret_occurrences(b"nothing here", SECRET) == 0
    assert proc.secret_occurrences(("x" + SECRET + "y").encode("utf-8"), SECRET) >= 1
    assert proc.secret_occurrences(SECRET[3:19].encode("utf-8"), SECRET) >= 1  # a 16-char run
    assert proc.secret_occurrences(SECRET[3:18].encode("utf-8"), SECRET) == 0  # 15 is not a run
    tricky = 'a"b\\c-' + "é" + "0123456789abcdefghijklmnop"
    escaped = json.dumps(tricky)[1:-1]
    assert escaped != tricky
    assert proc.secret_occurrences(("log " + escaped).encode("utf-8"), tricky) >= 1
    assert proc.secret_occurrences(("log " + tricky).encode("utf-8"), tricky) >= 1


def test_secret_occurrences_without_a_secret_is_zero():
    assert proc.secret_occurrences(b"anything", None) == 0
    assert proc.secret_occurrences(b"anything", "") == 0


# ------------------------------------------------------------- audit file parsing


def test_parse_audit_files_returns_entries_bad_lines_and_crlf():
    good = line_of(read_entry())
    mapping = {"audit-a.jsonl": [good, "{broken", ""], "audit-b.jsonl": [good + "\r"]}
    entries, bad, crlf = proc.parse_audit_files(mapping)
    assert [name for name, _entry in entries] == ["audit-a.jsonl", "audit-b.jsonl"]
    assert sorted(bad) == [("audit-a.jsonl", 2), ("audit-a.jsonl", 3)]
    assert crlf == ["audit-b.jsonl"]


def test_parse_audit_files_refuses_a_line_that_is_json_but_not_an_object():
    entries, bad, crlf = proc.parse_audit_files({"audit-a.jsonl": ["[1,2]", "7", "null"]})
    assert entries == [] and len(bad) == 3 and crlf == []


def test_parse_audit_files_never_raises_on_odd_input():
    for junk in (None, [], "x", {"a": None}, {"a": "text"}, {"a": [1, None]}):
        entries, bad, crlf = proc.parse_audit_files(junk)
        assert isinstance(entries, list) and isinstance(bad, list) and isinstance(crlf, list)


def test_audit_id_of_reads_the_last_line_id_or_none():
    call_id = str(uuid.uuid4())
    assert proc.audit_id_of(reply_for(call_id)) == call_id
    assert proc.audit_id_of("no audit line here") is None
    assert proc.audit_id_of(None) is None
    assert proc.audit_id_of("Audit: call_id not-a-uuid") is None


# ----------------------------------------------------------- classify_single: ok


def test_the_canned_single_record_is_ok_with_no_reasons():
    assert proc.classify_single(ok_single(), SECRET) == {"verdict": "ok", "reasons": []}


def test_the_canned_single_record_survives_a_json_round_trip_as_ok():
    record = json.loads(json.dumps(ok_single(), ensure_ascii=False))
    assert proc.classify_single(record, SECRET)["verdict"] == "ok"


def test_preflight_read_entries_never_count_as_step_entries():
    parts = single_parts()
    parts["extra"] = [read_entry() for _ in range(6)]
    assert proc.classify_single(render_single(parts), SECRET)["verdict"] == "ok"


# ------------------------------------------------- classify_single: perturbations


def _entry(key, **changes):
    def mutate(parts):
        parts["entries"][key].update(changes)
    return mutate


def _args(key, **changes):
    def mutate(parts):
        parts["entries"][key]["args"].update(changes)
    return mutate


def _document(key, **changes):
    def mutate(parts):
        document = dict(parts["entries"][key]["document"])
        document.update(changes)
        parts["entries"][key]["document"] = document
    return mutate


def _process(key, pid):
    def mutate(parts):
        parts["entries"][key]["process"] = dict(parts["entries"][key]["process"], pid=pid)
    return mutate


def _drop_entry(key):
    def mutate(parts):
        del parts["entries"][key]
    return mutate


def _duplicate_entry(key):
    def mutate(parts):
        parts["extra"].append(copy.deepcopy(parts["entries"][key]))
    return mutate


def _reply(key, text):
    def mutate(parts):
        parts["replies"][key] = text
    return mutate


def _new_call_id(key):
    def mutate(parts):
        parts["entries"][key]["call_id"] = str(uuid.uuid4())
    return mutate


def _torn_line(parts):
    parts["secret_lines"].append('{"ts":"2026-10-25T10:15:00.123Z","schema":1,"call_id"')


def _crlf(parts):
    parts["line_end"] = "\r"


def _secret_in_an_entry(parts):
    parts["secret_lines"].append(line_of(read_entry(path="/x/" + SECRET)))


def _secret_in_a_reply(parts):
    parts["replies"]["w1"] = parts["replies"]["w1"] + "\nleak: " + SECRET


SINGLE_STOP_CASES = [
    ("w1-outcome-unknown", _entry("w1", outcome="unknown", http_status=None), "w1.outcome"),
    ("w1-http-200", _entry("w1", http_status=200), "w1.http_status"),
    ("w1-committed", _entry("w1", transaction_status="Committed"), "w1.transaction_status"),
    ("w1-no-transaction-status", _entry("w1", transaction_status=None), "w1.transaction_status"),
    ("w1-sha-differs", _entry("w1", code_sha256=sha("other code")), "w1.code_sha256"),
    ("w1-sha-missing", _entry("w1", code_sha256=None), "w1.code_sha256"),
    ("w1-process-not-verified", _process("w1", 777), "w1.process.pid"),
    ("w2-outcome-success", _entry("w2", outcome="success"), "w2.outcome"),
    ("w2-failed-missing-bad-id", _entry("w2", failed=[]), "w2.failed"),
    ("w2-failed-without-reason",
     _entry("w2", failed=[{"item": BAD, "reason": None}]), "w2.failed"),
    ("w2-other-item-failed", _entry("w2", failed=[{"item": 5, "reason": "x"}]), "w2.failed"),
    ("w2-valid-id-not-succeeded", _entry("w2", succeeded=[]), "w2.succeeded"),
    ("w3-outcome-failed", _entry("w3", outcome="failed", http_status=422), "w3.outcome"),
    ("w3-document-token-empty", _document("w3", token=""), "w3.document.token"),
    ("w3-document-token-null", _document("w3", token=None), "w3.document.token"),
    ("w3-document-title-empty", _document("w3", title=""), "w3.document.title"),
    ("w3-document-path-null", _document("w3", path=None), "w3.document.path"),
    ("w3-document-missing", _entry("w3", document=None), "w3.document"),
    ("w3-process-not-in-revit-pids", _process("w3", 777), "w3.process.pid"),
    ("w3-process-missing", _entry("w3", process=None), "w3.process"),
    ("w3-user-request-differs", _entry("w3", user_request="another text"), "w3.user_request"),
    ("w3-succeeded-not-the-parameter", _entry("w3", succeeded=["Mark"]), "w3.succeeded"),
    ("w3-wrong-wall", _args("w3", element_id=5), "w3.args.element_id"),
    ("w3-windows-user-missing", _entry("w3", windows_user=None), "w3.windows_user"),
    ("w3-timestamp-missing", _entry("w3", ts=None), "w3.ts"),
    ("w3-not-a-mutation", _entry("w3", mutation=False), "w3.mutation"),
    ("w1-call-id-differs-from-audit-line", _new_call_id("w1"), "w1.call_id"),
    ("w2-zero-entries", _drop_entry("w2"), "w2"),
    ("w3-two-entries", _duplicate_entry("w3"), "w3"),
    ("w1-reply-has-no-audit-line", _reply("w1", "plain reply, no id"), "w1.reply"),
    ("w2-reply-missing", lambda parts: parts["replies"].pop("w2"), "w2.reply"),
    ("an-audit-line-does-not-parse", _torn_line, "not a JSON object"),
    ("crlf-in-a-file", _crlf, "CRLF"),
    ("secret-in-an-audit-file", _secret_in_an_entry, "SECRET_OCCURRENCES"),
    ("secret-in-a-reply", _secret_in_a_reply, "SECRET_OCCURRENCES"),
]


@pytest.mark.parametrize("label,mutate,field", SINGLE_STOP_CASES, ids=[c[0] for c in SINGLE_STOP_CASES])
def test_every_single_perturbation_is_a_stop_that_names_the_field(label, mutate, field):
    parts = single_parts()
    mutate(parts)
    result = proc.classify_single(render_single(parts), SECRET)
    assert result["verdict"] == "stop", label
    assert any(field in reason for reason in result["reasons"]), (label, result["reasons"])
    assert SECRET not in reasons_text(result)


def test_a_step_that_was_not_recorded_is_a_stop():
    record = ok_single()
    record["steps"]["w2"] = None
    result = proc.classify_single(record, SECRET)
    assert result["verdict"] == "stop" and "w2" in reasons_text(result)


def test_single_stops_when_no_secret_is_configured():
    result = proc.classify_single(ok_single(), None)
    assert result["verdict"] == "stop"
    assert "no secret configured" in reasons_text(result)


def test_single_refuses_a_record_of_the_other_stage():
    record = ok_single()
    record["stage"] = "dual"
    result = proc.classify_single(record, SECRET)
    assert result["verdict"] == "stop" and "stage" in reasons_text(result)


@pytest.mark.parametrize("junk", [None, [], "text", 7, {}, {"stage": "single"},
                                  {"stage": "single", "steps": 3, "replies": []},
                                  {"stage": "dual", "steps": {"parent": 5}, "audit_files": 4}])
def test_classifiers_never_raise_on_a_malformed_record(junk):
    for classify in (proc.classify_single, proc.classify_dual):
        result = classify(junk, SECRET)
        assert result["verdict"] == "stop"
        assert isinstance(result["reasons"], list) and result["reasons"]


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


@pytest.mark.parametrize("junk", [None, 0, "", "x", [], {}, [None]])
def test_classifiers_never_raise_when_any_single_node_is_replaced(junk):
    count = 0
    for record, classify in ((ok_single(), proc.classify_single), (ok_dual(), proc.classify_dual)):
        for variant in _replace_each_node(record, junk):
            result = classify(variant, SECRET)
            assert result["verdict"] in ("ok", "stop")
            assert isinstance(result["reasons"], list)
            count += 1
    assert count > 100


def test_a_classifier_internal_error_reads_as_stop(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic classifier bug")

    monkeypatch.setattr(proc, "parse_audit_files", boom)
    for classify, record in ((proc.classify_single, ok_single()), (proc.classify_dual, ok_dual())):
        result = classify(record, SECRET)
        assert result["verdict"] == "stop"
        assert "RuntimeError" in reasons_text(result)


# ------------------------------------------------------------- classify_dual: ok


def test_the_canned_dual_record_is_ok_with_no_reasons():
    assert proc.classify_dual(ok_dual(), SECRET) == {"verdict": "ok", "reasons": []}


def test_the_canned_dual_record_survives_a_json_round_trip_as_ok():
    record = json.loads(json.dumps(ok_dual(), ensure_ascii=False))
    assert proc.classify_dual(record, SECRET)["verdict"] == "ok"


# ------------------------------------------------- classify_dual: perturbations


def _dual_entry(key, **changes):
    def mutate(parts):
        parts["entries"][key].update(changes)
    return mutate


def _dual_drop(key):
    def mutate(parts):
        del parts["entries"][key]
    return mutate


def _dual_other_revit(key, pid):
    def mutate(parts):
        parts["entries"][key]["process"] = dict(parts["entries"][key]["process"], pid=pid)
    return mutate


def _single_file(parts):
    # the child's entries land in the parent's file and the child's file disappears
    for key, value in parts["entries"].items():
        if key.startswith("child"):
            value["server_pid"] = SERVER_PID
    parts["order"] = [("parent", key) for _who, key in parts["order"]]
    parts["drop_files"] = (file_name(CHILD_PID),)


def _two_half_entries_in_one_line(parts):
    first = line_of(parts["entries"]["child-0-1"])
    second = line_of(parts["entries"]["child-0-2"])
    torn = first[:len(first) // 2] + second  # a half entry run into the next whole one
    with pytest.raises(ValueError):  # the case must really be torn, not a lucky valid hybrid
        json.loads(torn)
    parts["secret_lines"].append(torn)


def _aligned_hybrid_line(parts):
    # two halves that happen to join into valid JSON: still caught, by the counts
    first = line_of(parts["entries"]["child-0-1"])
    second = line_of(parts["entries"]["child-0-2"])
    parts["secret_lines"].append(first[:len(first) // 2] + second[len(second) // 2:])


def _dual_secret(parts):
    parts["secret_lines"].append(line_of(read_entry(path="/x/" + SECRET)))


def _entry_in_the_wrong_file(parts):
    parts["entries"]["child-0-1"]["server_pid"] = SERVER_PID


def _issued_fewer_calls(parts):
    parts["calls"]["child"].pop()


def _call_pid_wrong(parts):
    parts["calls"]["parent"][0]["pid"] = REVIT_B


def _entry_args_differ(parts):
    parts["entries"]["parent-1-1"]["args"]["value"] = "somebody-elses-value"


def _duplicate_call_id(parts):
    parts["entries"]["parent-0-2"]["call_id"] = parts["entries"]["parent-0-1"]["call_id"]
    parts["replies"]["parent-0-2"] = parts["replies"]["parent-0-1"]


DUAL_STOP_CASES = [
    ("only-one-server-pid", _single_file, "only one server-process PID"),
    ("torn-line-of-two-half-entries", _two_half_entries_in_one_line, "not a JSON object"),
    ("an-aligned-hybrid-line-is-caught-by-the-counts", _aligned_hybrid_line, "found"),
    ("a-process-wrote-fewer-entries", _dual_drop("child-1-2"), "wrote"),
    ("a-parent-entry-is-missing", _dual_drop("parent-0-1"), "wrote"),
    ("entry-names-the-other-revit", _dual_other_revit("child-0-1", REVIT_B), "different Revit"),
    ("entry-names-an-unknown-revit", _dual_other_revit("parent-1-2", 777), "different Revit"),
    ("secret-in-a-file", _dual_secret, "SECRET_OCCURRENCES"),
    ("crlf-in-a-file", _crlf, "CRLF"),
    ("entry-sits-in-the-other-process-file", _entry_in_the_wrong_file, "server_pid"),
    ("child-issued-fewer-calls-than-expected", _issued_fewer_calls, "issued"),
    ("call-addressed-an-unexpected-revit", _call_pid_wrong, "addressed"),
    ("entry-args-differ-from-the-call", _entry_args_differ, "args"),
    ("a-call-id-appears-twice", _duplicate_call_id, "call_id"),
    ("a-call-has-no-audit-line", lambda parts: parts["replies"].__setitem__("parent-0-1", "plain"),
     "reply"),
    ("an-entry-is-not-a-set-parameter-mutation", _dual_entry("parent-0-1", tool="tag_elements"),
     "tool"),
]


@pytest.mark.parametrize("label,mutate,field", DUAL_STOP_CASES, ids=[c[0] for c in DUAL_STOP_CASES])
def test_every_dual_perturbation_is_a_stop_that_names_the_field(label, mutate, field):
    parts = dual_parts()
    mutate(parts)
    result = proc.classify_dual(render_dual(parts), SECRET)
    assert result["verdict"] == "stop", label
    assert any(field in reason for reason in result["reasons"]), (label, result["reasons"])
    assert SECRET not in reasons_text(result)


def test_dual_reasons_never_print_a_pid():
    parts = dual_parts()
    _dual_other_revit("child-0-1", 987654)(parts)
    result = proc.classify_dual(render_dual(parts), SECRET)
    assert result["verdict"] == "stop"
    for pid in ("987654", str(REVIT_A), str(REVIT_B), str(SERVER_PID), str(CHILD_PID)):
        assert pid not in reasons_text(result)


def test_dual_stops_when_no_secret_is_configured():
    result = proc.classify_dual(ok_dual(), None)
    assert result["verdict"] == "stop" and "no secret configured" in reasons_text(result)


def test_dual_refuses_a_record_of_the_other_stage():
    record = ok_dual()
    record["stage"] = "single"
    result = proc.classify_dual(record, SECRET)
    assert result["verdict"] == "stop" and "stage" in reasons_text(result)


def test_dual_needs_the_two_server_pids_to_differ():
    record = ok_dual()
    record["server_pids"]["child"] = record["server_pids"]["parent"]
    result = proc.classify_dual(record, SECRET)
    assert result["verdict"] == "stop"


# ------------------------------------------------------------------- the report


def test_report_prints_the_token_then_posts_sent():
    lines = proc.report("ok", [], 3)
    assert lines[0] == "PHASE6_AUDIT_OK" and lines[1] == "POSTS_SENT=3"
    lines = proc.report("stop", ["w1.outcome: x"], None)
    assert lines[0] == "PHASE6_AUDIT_STOP" and lines[1] == "POSTS_SENT=unknown"
    assert any("w1.outcome: x" in line for line in lines)


def test_report_guidance_follows_posts_sent():
    zero = "\n".join(proc.report("stop", [], 0))
    assert "nothing was written" in zero.lower() and "fresh" in zero
    consumed = "\n".join(proc.report("stop", [], 2))
    assert "consumed" in consumed
    unknown = "\n".join(proc.report("stop", [], None))
    assert "consumed" not in unknown and "nothing was written" not in unknown.lower()


def test_report_prints_only_the_count_of_secret_occurrences():
    lines = proc.report("ok", [], 3, secret_occurrences=0)
    assert "SECRET_OCCURRENCES=0" in lines
    assert not any(SECRET in line for line in lines)
    assert not any(line.startswith("SECRET_OCCURRENCES") for line in proc.report("ok", [], 3))


# ---------------------------------------------------------------------- refusals


def _args_for(tmp_path, **changes):
    rollback = tmp_path / "rollback.py"
    if not rollback.exists():
        rollback.write_text("# rollback code\n", encoding="utf-8")
    values = {
        "wall_id": WALL, "parameter": PARAM, "view_name": VIEW, "tag_id": TAG,
        "rollback_code": str(rollback), "audit_dir": str(tmp_path / "audit"),
        "out": str(tmp_path / "record.json"), "port": 48884,
    }
    values.update(changes)
    return Namespace(**dict((k, v) for k, v in values.items() if v is not Ellipsis))


def test_a_valid_set_of_arguments_is_not_refused(tmp_path):
    assert proc.refusal(_args_for(tmp_path)) is None


def test_an_empty_existing_audit_directory_is_allowed(tmp_path):
    (tmp_path / "audit").mkdir()
    assert proc.refusal(_args_for(tmp_path)) is None


def test_dual_arguments_are_judged_by_the_same_function(tmp_path):
    args = Namespace(wall_a=WALL_A, wall_b=WALL_B, parameter=PARAM, count=5,
                     audit_dir=str(tmp_path / "audit"), out=str(tmp_path / "dual.json"), port=48884)
    assert proc.refusal(args) is None


def _refusal_cases(tmp_path):
    existing = tmp_path / "existing.json"
    existing.write_text("{}", encoding="utf-8")
    full = tmp_path / "full-audit"
    full.mkdir()
    (full / "left-over.txt").write_text("x", encoding="utf-8")
    empty_code = tmp_path / "empty.py"
    empty_code.write_text("  \n", encoding="utf-8")
    inside = os.path.join(REPO_ROOT, "phase6-never-written.json")
    return [
        ("out-exists", dict(out=str(existing)), "already exists"),
        ("out-inside-repo", dict(out=inside), "repository"),
        ("audit-dir-inside-repo", dict(audit_dir=os.path.join(REPO_ROOT, "phase6-audit-never")),
         "repository"),
        ("audit-dir-is-the-repo-itself", dict(audit_dir=REPO_ROOT), "repository"),
        ("audit-dir-not-empty", dict(audit_dir=str(full)), "not empty"),
        ("out-directory-missing", dict(out=str(tmp_path / "nope" / "r.json")), "directory"),
        ("audit-dir-parent-missing", dict(audit_dir=str(tmp_path / "nope" / "audit")), "directory"),
        ("wall-id-zero", dict(wall_id=0), "wall-id"),
        ("wall-id-negative", dict(wall_id=-4), "wall-id"),
        ("wall-id-text", dict(wall_id="12"), "wall-id"),
        ("wall-id-bool", dict(wall_id=True), "wall-id"),
        ("tag-id-zero", dict(tag_id=0), "tag-id"),
        ("tag-id-is-the-bad-id", dict(tag_id=BAD), "tag-id"),
        ("parameter-blank", dict(parameter="  "), "parameter"),
        ("parameter-empty", dict(parameter=""), "parameter"),
        ("view-name-empty", dict(view_name=""), "view-name"),
        ("rollback-code-missing", dict(rollback_code=str(tmp_path / "gone.py")), "rollback-code"),
        ("rollback-code-empty", dict(rollback_code=str(empty_code)), "rollback-code"),
        ("port-out-of-range", dict(port=70000), "port"),
    ]


REFUSAL_LABELS = ["out-exists", "out-inside-repo", "audit-dir-inside-repo",
                  "audit-dir-is-the-repo-itself", "audit-dir-not-empty", "out-directory-missing",
                  "audit-dir-parent-missing", "wall-id-zero", "wall-id-negative", "wall-id-text",
                  "wall-id-bool", "tag-id-zero", "tag-id-is-the-bad-id", "parameter-blank",
                  "parameter-empty", "view-name-empty", "rollback-code-missing",
                  "rollback-code-empty", "port-out-of-range"]


@pytest.mark.parametrize("label", REFUSAL_LABELS)
def test_refusal_names_the_unsafe_input(tmp_path, label):
    changes, keyword = dict((c[0], (c[1], c[2])) for c in _refusal_cases(tmp_path))[label]
    reason = proc.refusal(_args_for(tmp_path, **changes))
    assert isinstance(reason, str) and reason, label
    assert keyword in reason, (label, reason)


@pytest.mark.parametrize("count", [0, 21, -1, "5", True, None])
def test_count_outside_one_to_twenty_is_refused(tmp_path, count):
    args = Namespace(wall_a=WALL_A, wall_b=WALL_B, parameter=PARAM, count=count,
                     audit_dir=str(tmp_path / "audit"), out=str(tmp_path / "dual.json"), port=48884)
    reason = proc.refusal(args)
    assert reason and "count" in reason


@pytest.mark.parametrize("count", [1, 5, 20])
def test_count_from_one_to_twenty_is_allowed(tmp_path, count):
    args = Namespace(wall_a=WALL_A, wall_b=WALL_B, parameter=PARAM, count=count,
                     audit_dir=str(tmp_path / "audit"), out=str(tmp_path / "dual.json"), port=48884)
    assert proc.refusal(args) is None


@pytest.mark.parametrize("name,value", [("wall_a", 0), ("wall_b", -1), ("wall_a", BAD)])
def test_dual_wall_ids_must_be_usable(tmp_path, name, value):
    values = dict(wall_a=WALL_A, wall_b=WALL_B, parameter=PARAM, count=5,
                  audit_dir=str(tmp_path / "audit"), out=str(tmp_path / "dual.json"), port=48884)
    values[name] = value
    reason = proc.refusal(Namespace(**values))
    assert reason and name.replace("_", "-") in reason


def test_a_refused_check_touches_no_file(tmp_path):
    before = sorted(os.listdir(str(tmp_path)))
    proc.refusal(_args_for(tmp_path, wall_id=0))
    after = sorted(os.listdir(str(tmp_path)))
    assert after == before + ["rollback.py"]
    assert not (tmp_path / "audit").exists() and not (tmp_path / "record.json").exists()


def test_outside_repo_is_true_only_for_paths_outside_the_repository(tmp_path):
    assert proc._outside_repo(str(tmp_path / "x.json")) is True
    assert proc._outside_repo(os.path.join(REPO_ROOT, "x.json")) is False
    assert proc._outside_repo(os.path.join(REPO_ROOT, "tests", "unit", "x.json")) is False
    assert proc._outside_repo(os.path.join(REPO_ROOT + "-sibling", "x.json")) is True


# ------------------------------------------------------ main: template and classify


def test_template_command_prints_the_empty_record(capsys):
    assert proc.main(["template"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert "posts_sent" in printed
    assert printed == proc.evidence_template()


def _write(tmp_path, record, name="record.json"):
    path = tmp_path / name
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_classify_command_prints_ok_posts_sent_and_the_secret_count(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(proc, "_secret_value", lambda: SECRET)
    assert proc.main(["classify", _write(tmp_path, ok_single())]) == 0
    text = capsys.readouterr().out
    assert "PHASE6_AUDIT_OK" in text and "POSTS_SENT=3" in text and "SECRET_OCCURRENCES=0" in text
    assert SECRET not in text


def test_classify_command_judges_a_dual_record_by_its_stage(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(proc, "_secret_value", lambda: SECRET)
    assert proc.main(["classify", _write(tmp_path, ok_dual())]) == 0
    text = capsys.readouterr().out
    assert "PHASE6_AUDIT_OK" in text and "POSTS_SENT={}".format(4 * K) in text


def test_classify_command_stop_exits_1_lists_reasons_and_never_prints_the_secret(
        tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(proc, "_secret_value", lambda: SECRET)
    parts = single_parts()
    _secret_in_an_entry(parts)
    record = render_single(parts)
    del record["posts_sent"]
    assert proc.main(["classify", _write(tmp_path, record)]) == 1
    text = capsys.readouterr().out
    assert "PHASE6_AUDIT_STOP" in text and "PHASE6_AUDIT_OK" not in text
    assert "POSTS_SENT=unknown" in text
    assert "SECRET_OCCURRENCES=" in text and "SECRET_OCCURRENCES=0" not in text
    assert SECRET not in text


def test_classify_command_without_a_loaded_secret_is_a_stop(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(proc, "_secret_value", lambda: None)
    assert proc.main(["classify", _write(tmp_path, ok_single())]) == 1
    assert "no secret configured" in capsys.readouterr().out


def test_classify_command_unknown_stage_is_a_stop(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(proc, "_secret_value", lambda: SECRET)
    record = ok_single()
    record["stage"] = "other"
    assert proc.main(["classify", _write(tmp_path, record)]) == 1
    assert "stage" in capsys.readouterr().out


def test_classify_command_unreadable_files_are_a_stop_not_a_traceback(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(proc, "_secret_value", lambda: SECRET)
    assert proc.main(["classify", str(tmp_path / "does-not-exist.json")]) == 1
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe not json")
    assert proc.main(["classify", str(bad)]) == 1
    text = capsys.readouterr().out
    assert "PHASE6_AUDIT_OK" not in text
    assert text.count("PHASE6_AUDIT_STOP") == 2 and "POSTS_SENT=unknown" in text


def test_main_with_no_command_or_an_unknown_one_is_a_usage_error(capsys):
    assert proc.main([]) == 2
    assert proc.main(["nonsense"]) == 2
    assert proc.main(["classify"]) == 2
    assert "PHASE6_AUDIT_OK" not in capsys.readouterr().out


# =============================================================================
# Task 2: the runner (rehearse, run-single, run-dual, child) driven through the real
# main.py tools, the real bridge and the real audit writer, against the Machine
# fake of tests/unit/audit_support.py. No Revit, no network, no subprocess for the
# child except its refusal. A second server process is simulated by a fake child
# that leaves a canned record and a canned audit file, because one process can have
# only one audit writer.


def _document_body():
    return {"document": DOC["token"], "title": DOC["title"], "path": DOC["path"]}


def _outcome(tx, requested, succeeded, failed, failures=()):
    return {"transaction_status": tx, "requested": requested, "succeeded": list(succeeded),
            "failed": list(failed), "revit_failures": list(failures)}


def docs_reply(count):
    docs = [{"document": "doc1.aaaaaaaaaaaa.{}".format(i), "title": "Scratch {}".format(i),
             "path": "C:/scratch/{}.rvt".format(i), "active": i == 0} for i in range(count)]
    return {"status": "success", "documents": docs, "count": count}


def props_reply(element_id, writable=True, storage="String", present=True):
    parameters = []
    if present:
        parameters.append({"name": PARAM, "value": "", "storage_type": storage,
                           "read_only": not writable, "is_instance": True})
    return {"status": "success", "element_id": element_id, "category": "Walls",
            "parameters": parameters, "parameter_count": len(parameters)}


ROLLED_BACK_BODY = {"status": "rolled_back", "document_scope": "no document scope",
                    "outcome": _outcome("RolledBack", None, [], [], ["posted failure"])}
COMMITTED_BODY = {"status": "success", "document_scope": "no document scope",
                  "outcome": _outcome("Committed", None, [], [])}
PARTIAL_BODY = {"status": "partial", "tagged_count": 1, "tag_ids": [3003],
                "skipped": [{"element_id": BAD, "reason": "Element not found"}],
                "document": _document_body(),
                "outcome": _outcome("Committed", 2, [TAG], [{"item": BAD, "reason": "Element not found"}])}
SET_BODY = {"status": "success", "element_id": WALL, "document": _document_body(),
            "outcome": _outcome("Committed", 1, [PARAM], [])}


@pytest.fixture
def one_revit(monkeypatch):
    """One fake Revit (port A) with one document, a writable wall parameter and canned write replies."""
    fake = make_machine(monkeypatch)
    fake.listeners = {PORT_A: [PID_A]}
    monkeypatch.setattr(bridge, "_secret_cache", SECRET)
    monkeypatch.setenv("REVIT_PORT", "48884")
    fake.reply(PORT_A, "/documents/", 200, docs_reply(1))
    fake.reply(PORT_A, "/element_properties/{}".format(WALL), 200, props_reply(WALL))
    fake.reply(PORT_A, "/element_properties/{}".format(TAG), 200,
               {"status": "success", "element_id": TAG, "category": "Doors", "parameters": []})
    fake.reply(PORT_A, "/execute_code/", 409, ROLLED_BACK_BODY)
    fake.reply(PORT_A, "/tag_elements/", 200, PARTIAL_BODY)
    fake.reply(PORT_A, "/set_parameter/", 200, SET_BODY)
    yield fake
    release_machine()


@pytest.fixture
def two_revits(monkeypatch):
    """Two fake Revit instances (ports A and B), one document each, the parameter writable on each wall."""
    fake = make_machine(monkeypatch)
    monkeypatch.setattr(bridge, "_secret_cache", SECRET)
    monkeypatch.setenv("REVIT_PORT", "48884")
    for port, wall in ((PORT_A, WALL_A), (PORT_B, WALL_B)):
        fake.reply(port, "/documents/", 200, docs_reply(1))
        fake.reply(port, "/element_properties/{}".format(wall), 200, props_reply(wall))
        fake.reply(port, "/set_parameter/", 200, SET_BODY)
    yield fake
    release_machine()


def rollback_file(tmp_path):
    path = tmp_path / "rollback.py"
    if not path.exists():
        path.write_bytes(CODE.encode("utf-8"))
    return str(path)


def single_argv(tmp_path, **overrides):
    values = {"--wall-id": str(WALL), "--parameter": PARAM, "--view-name": VIEW, "--tag-id": str(TAG),
              "--rollback-code": rollback_file(tmp_path), "--audit-dir": str(tmp_path / "audit"),
              "--out": str(tmp_path / "single.json")}
    values.update(overrides)
    argv = ["run-single"]
    for name, value in values.items():
        argv += [name, value]
    return argv


def dual_argv(tmp_path, **overrides):
    values = {"--wall-a": str(WALL_A), "--wall-b": str(WALL_B), "--parameter": PARAM,
              "--audit-dir": str(tmp_path / "audit"), "--out": str(tmp_path / "dual.json"),
              "--count": str(K)}
    values.update(overrides)
    argv = ["run-dual"]
    for name, value in values.items():
        argv += [name, value]
    return argv


def rehearse_argv(tmp_path, **overrides):
    values = {"--rollback-code": rollback_file(tmp_path), "--audit-dir": str(tmp_path / "audit")}
    values.update(overrides)
    argv = ["rehearse"]
    for name, value in values.items():
        argv += [name, value]
    return argv


def load_record(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def posts_of(fake):
    return [path for (_port, method, path) in fake.seen if method == "POST"]


class ExplodingBridge(object):
    """Any use at all fails the test: a refusal must come before the bridge is touched."""

    def __getattr__(self, name):
        raise AssertionError("the bridge was touched ({}) before a refusal".format(name))


def _explode(*_args, **_kwargs):
    raise AssertionError("touched before a refusal")


# --------------------------------------------------------- the script's own seams


def test_the_script_commands_are_all_listed_in_help(tmp_path):
    done = subprocess.run([sys.executable, SCRIPT_PATH, "--help"], capture_output=True, text=True,
                          timeout=60, cwd=str(tmp_path))
    assert done.returncode == 0, done.stderr
    for name in ("template", "rehearse", "run-single", "run-dual", "child", "classify"):
        assert name in done.stdout, name


def test_the_acceptance_refusal_exits_2_names_the_repository_and_writes_nothing():
    target = os.path.join(REPO_ROOT, "tests", "record.json")
    done = subprocess.run(
        [sys.executable, SCRIPT_PATH, "run-single", "--wall-id", "1", "--parameter", "Comments",
         "--view-name", "L1", "--tag-id", "2", "--rollback-code", SCRIPT_PATH, "--audit-dir", ".",
         "--out", os.path.join("tests", "record.json")],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT)
    assert done.returncode == 2, done.stdout + done.stderr
    assert "repository" in done.stdout
    assert not os.path.exists(target)


def test_the_parent_issues_its_calls_with_asyncio_gather():
    with open(SCRIPT_PATH, "rb") as handle:
        assert "asyncio.gather(" in handle.read().decode("utf-8")


def test_read_audit_dir_returns_raw_lines_of_audit_files_only(tmp_path):
    first, second = "audit-20261025-101500-11.jsonl", "audit-20261025-101500-11.0002.jsonl"
    (tmp_path / first).write_bytes(b'{"a":1}\r\n{"b":2}\r\n')
    (tmp_path / second).write_bytes(b'{"c":3}\n{"torn"')
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "audit-dir.jsonl").mkdir()
    files = proc._read_audit_dir(str(tmp_path))
    assert set(files) == {first, second}
    assert files[first] == ['{"a":1}\r', '{"b":2}\r']
    assert files[second] == ['{"c":3}', '{"torn"']
    assert proc._read_audit_dir(str(tmp_path / "missing")) == {}


def test_save_writes_once_and_never_overwrites(tmp_path):
    path = tmp_path / "r.json"
    assert proc._save(str(path), {"a": "Проект"}) is True
    assert proc._save(str(path), {"a": 2}) is False
    assert load_record(str(path)) == {"a": "Проект"}
    assert b"\r\n" not in path.read_bytes()


def test_reply_text_joins_content_blocks_and_accepts_plain_text():
    blocks = [SimpleNamespace(text="one"), SimpleNamespace(text="two"), SimpleNamespace(data=b"x")]
    assert proc._reply_text(blocks) == "one\ntwo"
    assert proc._reply_text((blocks, {"structured": True})) == "one\ntwo"
    assert proc._reply_text("plain") == "plain"


def test_tool_step_counts_the_post_before_the_call_even_when_the_call_raises(monkeypatch):
    record = proc.evidence_template()
    seen = []

    async def failing_call(arguments):
        seen.append(record["posts_sent"])
        raise RuntimeError("synthetic transport failure")

    monkeypatch.setattr(proc, "_tool_callable", lambda tool: failing_call)
    problem = asyncio.run(proc._tool_step(
        record, "w1", "execute_revit_code", {"code": "x", "user_request": "ur"}))
    assert seen == [1] and record["posts_sent"] == 1
    assert problem.startswith("RuntimeError")
    assert record["steps"]["w1"]["exception"] == problem
    assert record["steps"]["w1"]["user_request"] == "ur"
    assert "w1" not in record["replies"]


def test_tool_step_stores_the_reply_text_of_a_successful_call(monkeypatch):
    record = proc.evidence_template()

    async def call(arguments):
        return reply_for("11111111-2222-4333-8444-555555555555")

    monkeypatch.setattr(proc, "_tool_callable", lambda tool: call)
    assert asyncio.run(proc._tool_step(record, "w3", "set_parameter", {"user_request": "u"})) is None
    assert record["replies"]["w3"].endswith("11111111-2222-4333-8444-555555555555")
    assert record["posts_sent"] == 1


def test_tool_step_refuses_a_tool_outside_the_allow_list_before_counting(monkeypatch):
    record = proc.evidence_template()
    monkeypatch.setattr(proc, "_tool_callable", _explode)
    for tool in ("save_document", "open_model", "delete_elements", "", None):
        with pytest.raises(ValueError):
            asyncio.run(proc._tool_step(record, "w1", tool, {}))
    assert record["posts_sent"] == 0


def test_read_routes_outside_the_allow_list_are_refused():
    for endpoint in ("/status/", "/documents/", "/element_properties/1001"):
        proc._require_allowed_read(endpoint)
    for endpoint in ("/save_document/", "/execute_code/", "/open_model/", "/set_parameter/", "/status",
                     "", "/element_properties/x", None, 5):
        with pytest.raises(ValueError):
            proc._require_allowed_read(endpoint)


# ------------------------------------------------------------------- refusals first


@pytest.mark.parametrize("command,argv_for", [("run-single", single_argv), ("run-dual", dual_argv),
                                              ("rehearse", rehearse_argv)])
def test_an_audit_dir_with_files_is_refused_before_the_bridge_is_touched(
        monkeypatch, tmp_path, capsys, command, argv_for):
    (tmp_path / "audit").mkdir()
    (tmp_path / "audit" / "left-over.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(proc, "_bridge", ExplodingBridge)
    monkeypatch.setattr(proc, "_main_module", _explode)
    monkeypatch.setattr(proc, "_start_child", _explode)
    assert proc.main(argv_for(tmp_path)) == 2
    out = capsys.readouterr().out
    assert "not empty" in out and "PHASE6_AUDIT_OK" not in out


@pytest.mark.parametrize("command,argv_for", [("run-single", single_argv), ("run-dual", dual_argv)])
def test_an_existing_out_record_is_refused_untouched_before_the_bridge_is_touched(
        monkeypatch, tmp_path, capsys, command, argv_for):
    out = tmp_path / ("single.json" if command == "run-single" else "dual.json")
    out.write_bytes(b'{"keep": "me"}')
    monkeypatch.setattr(proc, "_bridge", _explode)
    monkeypatch.setattr(proc, "_main_module", _explode)
    monkeypatch.setattr(proc, "_start_child", _explode)
    assert proc.main(argv_for(tmp_path)) == 2
    assert out.read_bytes() == b'{"keep": "me"}'
    assert not (tmp_path / "audit").exists()


def test_a_missing_option_is_a_usage_error_that_sends_nothing(monkeypatch, capsys):
    monkeypatch.setattr(proc, "_bridge", _explode)
    monkeypatch.setattr(proc, "_main_module", _explode)
    for argv in (["run-single", "--wall-id", "5"], ["run-dual"], ["rehearse"], ["child"]):
        assert proc.main(argv) == 2
    assert "PHASE6_AUDIT_OK" not in capsys.readouterr().out


def test_the_audit_dir_and_port_are_set_before_the_bridge_is_imported(monkeypatch, one_revit, tmp_path):
    seen = {}
    real = proc._bridge

    def capturing():
        seen["dir"] = os.environ.get("REVIT_MCP_AUDIT_DIR")
        seen["port"] = os.environ.get("REVIT_PORT")
        return real()

    monkeypatch.setattr(proc, "_bridge", capturing)
    proc.main(single_argv(tmp_path))
    assert seen["dir"] == os.path.abspath(str(tmp_path / "audit"))
    assert seen["port"] == "48884"


# --------------------------------------------------- run-single: preflight and run


SINGLE_PREFLIGHT_FAULTS = [
    ("two-documents", lambda fake, mp: fake.reply(PORT_A, "/documents/", 200, docs_reply(2)), {}, "documents"),
    ("no-document", lambda fake, mp: fake.reply(PORT_A, "/documents/", 200, docs_reply(0)), {}, "documents"),
    ("parameter-read-only",
     lambda fake, mp: fake.reply(PORT_A, "/element_properties/{}".format(WALL), 200,
                                 props_reply(WALL, writable=False)), {}, "parameter"),
    ("parameter-absent",
     lambda fake, mp: fake.reply(PORT_A, "/element_properties/{}".format(WALL), 200,
                                 props_reply(WALL, present=False)), {}, "parameter"),
    ("parameter-not-text",
     lambda fake, mp: fake.reply(PORT_A, "/element_properties/{}".format(WALL), 200,
                                 props_reply(WALL, storage="Integer")), {}, "parameter"),
    ("tag-element-missing",
     lambda fake, mp: fake.reply(PORT_A, "/element_properties/{}".format(TAG), 404,
                                 {"error": "Element not found."}), {}, "tag"),
    ("two-usable-targets", lambda fake, mp: fake.listeners.__setitem__(PORT_B, [PID_B]), {}, "targets"),
    ("port-collision", lambda fake, mp: fake.listeners.__setitem__(PORT_A, [PID_A, 999]), {}, "targets"),
    ("inventory-unavailable",
     lambda fake, mp: mp.setattr(bridge, "listener_snapshot", lambda ports, **kw: None), {}, "inventory"),
    ("wrong-port", lambda fake, mp: None, {"--port": "48999"}, "port"),
]


@pytest.mark.parametrize("label,fault,overrides,field", SINGLE_PREFLIGHT_FAULTS,
                         ids=[c[0] for c in SINGLE_PREFLIGHT_FAULTS])
def test_run_single_preflight_failure_sends_no_post_and_records_zero(
        monkeypatch, one_revit, tmp_path, capsys, label, fault, overrides, field):
    fault(one_revit, monkeypatch)
    argv = single_argv(tmp_path, **overrides)
    assert proc.main(argv) == 1
    text = capsys.readouterr().out
    assert posts_of(one_revit) == []
    assert "PHASE6_AUDIT_STOP" in text and "PHASE6_AUDIT_OK" not in text
    assert "POSTS_SENT=0" in text
    assert "consumed" not in text and "nothing was written" in text.lower()
    assert SECRET not in text
    record = load_record(str(tmp_path / "single.json"))
    assert record["posts_sent"] == 0 and record["stage"] == "single"
    assert field in record["stop_reason"]
    assert all(record["steps"][key] is None for key in ("w1", "w2", "w3"))


def test_a_preflight_stop_allows_a_rerun_to_a_fresh_out_and_leaves_the_first_record_alone(
        monkeypatch, one_revit, tmp_path, capsys):
    one_revit.reply(PORT_A, "/documents/", 200, docs_reply(2))
    assert proc.main(single_argv(tmp_path)) == 1
    first = (tmp_path / "single.json").read_bytes()
    capsys.readouterr()
    audit._reset()  # a real rerun is a fresh process; one process keeps its first audit writer
    one_revit.reply(PORT_A, "/documents/", 200, docs_reply(1))
    argv = single_argv(tmp_path, **{"--out": str(tmp_path / "second.json"),
                                    "--audit-dir": str(tmp_path / "audit-2")})
    assert proc.main(argv) == 0
    assert "PHASE6_AUDIT_OK" in capsys.readouterr().out
    assert (tmp_path / "single.json").read_bytes() == first


def test_run_single_end_to_end_through_the_audited_tools_is_ok(one_revit, tmp_path, capsys):
    assert proc.main(single_argv(tmp_path)) == 0
    text = capsys.readouterr().out
    assert "PHASE6_AUDIT_OK" in text and "POSTS_SENT=3" in text and "SECRET_OCCURRENCES=0" in text
    assert "consumed" in text and SECRET not in text
    assert posts_of(one_revit) == [PREFIX + "/execute_code/", PREFIX + "/tag_elements/",
                                   PREFIX + "/set_parameter/"]
    for (_port, method, path) in one_revit.seen:
        if method == "GET" and not path.endswith("/status/"):
            assert path.startswith((PREFIX + "/documents/", PREFIX + "/element_properties/")), path
    record = load_record(str(tmp_path / "single.json"))
    assert record["stage"] == "single" and record["posts_sent"] == 3
    assert record["revit_pids"] == [PID_A]
    assert record["server_pids"]["parent"] == os.getpid()
    assert record["inputs"]["rollback_code"] == CODE
    requests = [step["user_request"] for step in (record["steps"][k] for k in ("w1", "w2", "w3"))]
    assert all(requests) and len(set(requests)) == 3
    assert set(record["steps"]["w2"]["arguments"]["element_ids"]) == {TAG, BAD}
    assert len(record["audit_files"]) == 1
    assert next(iter(record["audit_files"])).endswith("-{}.jsonl".format(os.getpid()))
    assert SECRET.encode("utf-8") not in (tmp_path / "single.json").read_bytes()
    assert proc.classify_single(record, SECRET) == {"verdict": "ok", "reasons": []}
    capsys.readouterr()
    assert proc.main(["classify", str(tmp_path / "single.json")]) == 0
    assert "PHASE6_AUDIT_OK" in capsys.readouterr().out


def test_run_single_calls_each_write_once_in_order_even_when_the_second_raises(
        monkeypatch, one_revit, tmp_path, capsys):
    calls = []

    def callable_for(tool):
        async def call(arguments):
            calls.append(tool)
            if tool == "tag_elements":
                raise RuntimeError("synthetic transport failure")
            return reply_for(str(uuid.uuid4()))
        return call

    monkeypatch.setattr(proc, "_tool_callable", callable_for)
    assert proc.main(single_argv(tmp_path)) == 1
    text = capsys.readouterr().out
    assert calls == ["execute_revit_code", "tag_elements", "set_parameter"]
    assert "PHASE6_AUDIT_STOP" in text and "POSTS_SENT=3" in text and "consumed" in text
    record = load_record(str(tmp_path / "single.json"))
    assert record["posts_sent"] == 3
    assert "synthetic transport failure" in record["steps"]["w2"]["exception"]
    assert "w2" not in record["replies"] and "w1" in record["replies"] and "w3" in record["replies"]


def test_run_single_still_writes_its_record_when_the_bridge_cannot_be_imported(
        monkeypatch, tmp_path, capsys):
    def broken():
        raise ImportError("synthetic import failure")

    monkeypatch.setenv("REVIT_PORT", "48884")  # the command sets it; the fixture restores it
    monkeypatch.setattr(proc, "_bridge", broken)
    assert proc.main(single_argv(tmp_path)) == 1
    text = capsys.readouterr().out
    assert "POSTS_SENT=0" in text and "PHASE6_AUDIT_STOP" in text
    assert "synthetic import failure" in load_record(str(tmp_path / "single.json"))["stop_reason"]


# ------------------------------------------------------------------- rehearse


def test_rehearse_reports_a_rollback_after_exactly_one_post(one_revit, tmp_path, capsys):
    assert proc.main(rehearse_argv(tmp_path)) == 0
    text = capsys.readouterr().out
    assert "REHEARSAL_ROLLED_BACK" in text and "POSTS_SENT=1" in text
    assert "PHASE6_AUDIT" not in text and SECRET not in text
    assert posts_of(one_revit) == [PREFIX + "/execute_code/"]
    body = json.loads([r for r in one_revit.requests if r.method == "POST"][0].content)
    assert body["description"] == "phase6 rehearsal" and body["code"] == CODE
    files = proc._read_audit_dir(str(tmp_path / "audit"))
    entries = [e for _n, e in proc.parse_audit_files(files)[0] if e.get("tool") == "execute_revit_code"]
    assert len(entries) == 1 and entries[0]["user_request"] == "phase6 rehearsal"


def test_rehearse_reports_a_commit_and_is_not_a_pass(one_revit, tmp_path, capsys):
    one_revit.reply(PORT_A, "/execute_code/", 200, COMMITTED_BODY)
    assert proc.main(rehearse_argv(tmp_path)) == 1
    text = capsys.readouterr().out
    assert "REHEARSAL_COMMITTED" in text and "POSTS_SENT=1" in text


def test_rehearse_reports_anything_else_as_other(one_revit, tmp_path, capsys):
    one_revit.reply(PORT_A, "/execute_code/", 500, {"error": "boom"})
    assert proc.main(rehearse_argv(tmp_path)) == 1
    text = capsys.readouterr().out
    assert "REHEARSAL_OTHER" in text and "POSTS_SENT=1" in text


def test_rehearse_stops_before_any_post_when_the_preflight_fails(one_revit, tmp_path, capsys):
    one_revit.reply(PORT_A, "/documents/", 200, docs_reply(2))
    assert proc.main(rehearse_argv(tmp_path)) == 1
    text = capsys.readouterr().out
    assert "REHEARSAL_OTHER" in text and "POSTS_SENT=0" in text
    assert posts_of(one_revit) == []


# ------------------------------------------------------------------- run-dual


class FakeChild(object):
    def __init__(self, returncode=0, timeout=False):
        self.returncode = returncode
        self._timeout = timeout
        self.killed = False

    def communicate(self, timeout=None):
        if self._timeout and not self.killed:
            raise subprocess.TimeoutExpired("child", timeout)
        return b"", b""

    def kill(self):
        self.killed = True


def install_fake_child(monkeypatch, fake, write_record=True, write_audit=True, returncode=0,
                       timeout=False, started=None):
    """A stand-in for the second server process: leaves its record and its audit file on disk."""
    def start(argv, env):
        options = dict(zip(argv[3::2], argv[4::2]))
        if started is not None:
            started.update(argv=list(argv), env=dict(env), options=options,
                           posts_at_start=len(posts_of(fake)))
        count = int(options["--count"])
        audit_dir = options["--audit-dir"]
        os.makedirs(audit_dir, exist_ok=True)
        calls, replies, lines = [], {}, []
        for index, (sel, wall) in enumerate((("--target-a", "--wall-a"), ("--target-b", "--wall-b"))):
            revit_pid = bridge.parse_target(options[sel])["pid"]
            for i in range(1, count + 1):
                key = "child-{}-{}".format(index, i)
                call_id = str(uuid.uuid4())
                value = "phase6-dual-{}-{}".format(CHILD_PID, i)
                ur = "phase6 dual child {}".format(key)
                element = int(options[wall])
                lines.append(line_of(entry(
                    call_id, "set_parameter", "/set_parameter/", "success", 200, succeeded=[PARAM],
                    server_pid=CHILD_PID, process_pid=revit_pid, user_request=ur,
                    args={"element_id": element, "parameter_name": PARAM, "value": value})))
                calls.append({"key": key, "tool": "set_parameter", "pid": revit_pid,
                              "element_id": element, "value": value, "user_request": ur,
                              "exception": None, "arguments": {}})
                replies[key] = reply_for(call_id)
        if write_audit:
            with open(os.path.join(audit_dir, file_name(CHILD_PID)), "wb") as handle:
                handle.write(("\n".join(lines) + "\n").encode("utf-8"))
        if write_record:
            record = proc.evidence_template()
            record.update({"stage": "dual-child", "posts_sent": len(calls), "replies": replies,
                           "server_pids": {"parent": None, "child": CHILD_PID}})
            record["steps"]["child"] = calls
            with open(options["--out"], "wb") as handle:
                handle.write(json.dumps(record).encode("utf-8"))
        return FakeChild(returncode=returncode, timeout=timeout)

    monkeypatch.setattr(proc, "_start_child", start)


def test_run_dual_end_to_end_with_a_second_server_process_is_ok(monkeypatch, two_revits, tmp_path, capsys):
    started = {}
    install_fake_child(monkeypatch, two_revits, started=started)
    assert proc.main(dual_argv(tmp_path)) == 0
    text = capsys.readouterr().out
    assert "PHASE6_AUDIT_OK" in text and "POSTS_SENT={}".format(4 * K) in text
    assert "SECRET_OCCURRENCES=0" in text and SECRET not in text
    # the child was started, with its token in argv and environment, before the parent wrote anything
    assert started["posts_at_start"] == 0
    token = started["options"]["--child-token"]
    assert token and started["env"][proc.CHILD_TOKEN_ENV] == token
    assert started["options"]["--count"] == str(K) and started["options"]["--parameter"] == PARAM
    assert started["options"]["--wall-a"] == str(WALL_A) and started["options"]["--wall-b"] == str(WALL_B)
    assert bridge.parse_target(started["options"]["--target-a"])["pid"] == PID_A
    assert bridge.parse_target(started["options"]["--target-b"])["pid"] == PID_B
    assert started["options"]["--audit-dir"] == os.path.abspath(str(tmp_path / "audit"))
    assert started["options"]["--out"] != str(tmp_path / "dual.json")
    # the parent's own calls: K per Revit, each on its own wall, with values naming its pid
    bodies = [(r.url.port, json.loads(r.content)) for r in two_revits.requests if r.method == "POST"]
    assert len(bodies) == 2 * K
    for port, wall in ((PORT_A, WALL_A), (PORT_B, WALL_B)):
        mine = [b for p, b in bodies if p == port]
        assert [b["element_id"] for b in mine] == [wall] * K
        assert sorted(b["value"] for b in mine) == ["phase6-dual-{}-{}".format(os.getpid(), i)
                                                    for i in range(1, K + 1)]
    record = load_record(str(tmp_path / "dual.json"))
    assert record["stage"] == "dual" and record["posts_sent"] == 4 * K
    assert record["revit_pids"] == [PID_A, PID_B]
    assert record["server_pids"] == {"parent": os.getpid(), "child": CHILD_PID}
    assert len(record["steps"]["parent"]) == 2 * K and len(record["steps"]["child"]) == 2 * K
    assert len(record["audit_files"]) == 2
    assert SECRET.encode("utf-8") not in (tmp_path / "dual.json").read_bytes()
    assert proc.classify_dual(record, SECRET) == {"verdict": "ok", "reasons": []}


def test_run_dual_gives_the_lowest_port_the_first_wall(monkeypatch, two_revits, tmp_path):
    install_fake_child(monkeypatch, two_revits)
    assert proc.main(dual_argv(tmp_path)) == 0
    record = load_record(str(tmp_path / "dual.json"))
    targets = record["preflight"]["targets"]
    assert [t["wall_id"] for t in targets] == [WALL_A, WALL_B]
    assert [t["pid"] for t in targets] == [PID_A, PID_B]


DUAL_PREFLIGHT_FAULTS = [
    ("one-revit-only", lambda fake: fake.listeners.pop(PORT_B), "targets"),
    ("no-revit", lambda fake: fake.listeners.clear(), "targets"),
    ("port-collision", lambda fake: fake.listeners.__setitem__(PORT_A, [PID_A, 999]), "targets"),
    ("second-has-two-documents", lambda fake: fake.reply(PORT_B, "/documents/", 200, docs_reply(2)),
     "documents"),
    ("first-has-no-document", lambda fake: fake.reply(PORT_A, "/documents/", 200, docs_reply(0)),
     "documents"),
    ("wall-b-read-only",
     lambda fake: fake.reply(PORT_B, "/element_properties/{}".format(WALL_B), 200,
                             props_reply(WALL_B, writable=False)), "parameter"),
    ("wall-a-missing",
     lambda fake: fake.reply(PORT_A, "/element_properties/{}".format(WALL_A), 404,
                             {"error": "Element not found."}), "parameter"),
]


@pytest.mark.parametrize("label,fault,field", DUAL_PREFLIGHT_FAULTS, ids=[c[0] for c in DUAL_PREFLIGHT_FAULTS])
def test_run_dual_preflight_failure_starts_no_child_sends_no_post_and_records_zero(
        monkeypatch, two_revits, tmp_path, capsys, label, fault, field):
    fault(two_revits)
    monkeypatch.setattr(proc, "_start_child", _explode)
    assert proc.main(dual_argv(tmp_path)) == 1
    text = capsys.readouterr().out
    assert posts_of(two_revits) == []
    assert "PHASE6_AUDIT_STOP" in text and "POSTS_SENT=0" in text
    assert "nothing was written" in text.lower()
    record = load_record(str(tmp_path / "dual.json"))
    assert record["posts_sent"] == 0 and field in record["stop_reason"]
    assert not (tmp_path / "dual-child.json").exists()


def test_run_dual_without_the_child_record_is_a_stop_with_an_unknown_count(
        monkeypatch, two_revits, tmp_path, capsys):
    install_fake_child(monkeypatch, two_revits, write_record=False)
    assert proc.main(dual_argv(tmp_path)) == 1
    text = capsys.readouterr().out
    assert "PHASE6_AUDIT_STOP" in text and "POSTS_SENT=unknown" in text
    record = load_record(str(tmp_path / "dual.json"))
    assert record["posts_sent"] is None and "child" in record["stop_reason"]


def test_run_dual_with_a_failed_child_exit_is_a_stop(monkeypatch, two_revits, tmp_path, capsys):
    install_fake_child(monkeypatch, two_revits, returncode=3)
    assert proc.main(dual_argv(tmp_path)) == 1
    record = load_record(str(tmp_path / "dual.json"))
    assert "exited" in record["stop_reason"] and record["child_exit"] == 3


def test_run_dual_kills_a_child_that_never_finishes_and_reports_an_unknown_count(
        monkeypatch, two_revits, tmp_path, capsys):
    install_fake_child(monkeypatch, two_revits, timeout=True, write_record=False)
    assert proc.main(dual_argv(tmp_path)) == 1
    record = load_record(str(tmp_path / "dual.json"))
    assert "timed out" in record["stop_reason"] and record["posts_sent"] is None


def test_run_dual_stops_when_the_child_leaves_no_audit_file(monkeypatch, two_revits, tmp_path, capsys):
    install_fake_child(monkeypatch, two_revits, write_audit=False)
    assert proc.main(dual_argv(tmp_path)) == 1
    text = capsys.readouterr().out
    assert "PHASE6_AUDIT_STOP" in text and "only one server-process PID" in text


# ---------------------------------------------------------------------- child


def child_argv(tmp_path, token="tok-1", **overrides):
    values = {"--child-token": token, "--audit-dir": str(tmp_path / "audit-child"),
              "--out": str(tmp_path / "child.json"), "--port": "48884", "--parameter": PARAM,
              "--count": str(K), "--target-a": SEL_A, "--target-b": SEL_B,
              "--wall-a": str(WALL_A), "--wall-b": str(WALL_B)}
    values.update(overrides)
    argv = ["child"]
    for name, value in values.items():
        argv += [name, value]
    return argv


def test_child_issues_its_calls_flushes_and_writes_its_record(monkeypatch, two_revits, tmp_path, capsys):
    monkeypatch.setenv(proc.CHILD_TOKEN_ENV, "tok-1")
    assert proc.main(child_argv(tmp_path)) == 0
    record = load_record(str(tmp_path / "child.json"))
    assert record["stage"] == "dual-child" and record["posts_sent"] == 2 * K
    assert record["server_pids"]["child"] == os.getpid()
    calls = record["steps"]["child"]
    assert len(calls) == 2 * K
    assert sorted(c["pid"] for c in calls) == [PID_A] * K + [PID_B] * K
    assert all(proc.audit_id_of(record["replies"][c["key"]]) for c in calls)
    assert all(c["value"].startswith("phase6-dual-{}-".format(os.getpid())) for c in calls)
    files = proc._read_audit_dir(str(tmp_path / "audit-child"))
    entries = [e for _n, e in proc.parse_audit_files(files)[0] if e.get("tool") == "set_parameter"]
    assert len(entries) == 2 * K
    assert SECRET.encode("utf-8") not in (tmp_path / "child.json").read_bytes()
    assert SECRET not in capsys.readouterr().out


def test_child_refuses_without_the_token_before_touching_anything(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(proc.CHILD_TOKEN_ENV, raising=False)
    monkeypatch.setattr(proc, "_bridge", _explode)
    monkeypatch.setattr(proc, "_main_module", _explode)
    assert proc.main(child_argv(tmp_path)) == 2
    assert "run-dual" in capsys.readouterr().out
    assert not (tmp_path / "child.json").exists() and not (tmp_path / "audit-child").exists()


def test_child_refuses_a_token_that_differs_from_the_environment(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(proc.CHILD_TOKEN_ENV, "other")
    monkeypatch.setattr(proc, "_bridge", _explode)
    assert proc.main(child_argv(tmp_path)) == 2


def test_child_run_as_a_real_subprocess_without_the_token_exits_2(tmp_path):
    env = dict(os.environ)
    env.pop(proc.CHILD_TOKEN_ENV, None)
    argv = [sys.executable, SCRIPT_PATH] + child_argv(tmp_path)
    done = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120, cwd=str(tmp_path))
    assert done.returncode == 2, done.stdout + done.stderr
    assert "run-dual" in done.stdout
    assert not (tmp_path / "child.json").exists() and not (tmp_path / "audit-child").exists()
