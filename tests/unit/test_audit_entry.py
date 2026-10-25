# -*- coding: utf-8 -*-
"""Pure audit.build_entry rows: the outcome table, mutation flag, documents and the schema 1 field set. Needs no Revit."""

import ast
import json
import os
import re
from datetime import datetime, timezone

import pytest

import audit
from inventory_support import REVIT_MCP_DIR, reachable_calls, route_inventory
from revit_mcp import trust

NOW = datetime(2026, 10, 25, 10, 0, 0, tzinfo=timezone.utc)
CALL = audit.CallState("11111111-2222-4333-8444-555555555555", "tool_x", {}, None)
PROCESS = {"pid": 111, "actual_port": 48884, "session_token": "tok-a", "revit_version": "2024"}
REQUESTED = {"address": "127.0.0.1:48884", "pid": 111}


def meta(kind="received", http_status=200, process=PROCESS, requested=REQUESTED, corroborated=True):
    """Provenance shaped like bridge._meta."""
    return {"kind": kind, "requested": requested,
            "process": process if kind == "received" else None,
            "http_status": http_status, "corroborated": corroborated}


def build(body, method="POST", endpoint="/set_parameter/", kind="received", http_status=200,
          call=CALL, **kwargs):
    return audit.build_entry(call, method, endpoint, meta(kind, http_status), body,
                             duration_ms=7, now=NOW, server_pid=4242, **kwargs)


def block(transaction_status="Committed", requested=1, succeeded=(5,), failed=(), failures=()):
    return {"transaction_status": transaction_status, "requested": requested,
            "succeeded": list(succeeded), "failed": [dict(f) for f in failed],
            "revit_failures": list(failures)}


# --------------------------------------------------------------- outcome table

OUTCOME_ROWS = [
    ("200-success", "POST", "/set_parameter/", "received", 200,
     {"status": "success", "outcome": block()}, "success", {}),
    ("200-partial", "POST", "/set_parameter/", "received", 200,
     {"status": "partial", "outcome": block(requested=2, succeeded=[5], failed=[
         {"item": 6, "reason": "read-only"}])}, "partial",
     {"failed": [{"item": 6, "reason": "read-only"}], "failed_count": 1}),
    ("409-rolled-back", "POST", "/set_parameter/", "received", 409,
     {"status": "rolled_back", "transaction_status": "RolledBack",
      "outcome": block("RolledBack", 3, [], [], ["Constraints are not satisfied"])},
     "rolled_back", {"transaction_status": "RolledBack", "succeeded": [], "succeeded_count": 0,
                     "revit_failures": ["Constraints are not satisfied"]}),
    ("422-failed", "POST", "/set_parameter/", "received", 422,
     {"status": "failed", "error": "None of the 1 requested item(s) succeeded",
      "outcome": block(requested=1, succeeded=[], failed=[{"item": 9, "reason": "no such"}])},
     "failed", {"failed_count": 1}),
    ("401-auth", "POST", "/set_parameter/", "received", 401,
     trust.auth_failure("mismatch")[0], "rejected_auth", {"reason": "mismatch"}),
    ("401-auth-beats-body-status", "POST", "/set_parameter/", "received", 401,
     {"status": "success", "auth": "missing"}, "rejected_auth", {"reason": "missing"}),
    ("423-integrity", "POST", "/set_parameter/", "received", 423,
     trust.integrity_failure(["a.py"])[0], "rejected_integrity", {"reason": "verified_mismatch"}),
    ("412-document-refusal", "POST", "/set_parameter/", "received", 412,
     {"error": "not active", "error_code": "document-not-active"}, "rejected_document",
     {"reason": "document-not-active"}),
    ("422-document-refusal-beats-status", "POST", "/set_parameter/", "received", 422,
     {"status": "failed", "error_code": "document-closed"}, "rejected_document",
     {"reason": "document-closed"}),
    ("404-bare-is-error", "POST", "/set_parameter/", "received", 404,
     {"error": "Element not found"}, "error", {}),
    ("500-with-committed-outcome", "POST", "/set_parameter/", "received", 500,
     {"error": "boom", "outcome": block("Committed", 1, [7])}, "error",
     {"transaction_status": "Committed", "succeeded": [7], "succeeded_count": 1}),
    ("read-500-error", "GET", "/model_info/", "received", 500, {"error": "boom"}, "error", {}),
    ("unknown-kind", "POST", "/set_parameter/", "unknown", None, None, "unknown",
     {"process": None, "requested_target": REQUESTED}),
    ("no-reply-kind", "GET", "/model_info/", "no-reply", None, None, "no_reply",
     {"process": None}),
    ("unverified-reply-kind", "GET", "/status/", "unverified-reply", 200, {"status": "x"},
     "unverified_reply", {"process": None}),
    ("mutation-200-without-status", "POST", "/set_parameter/", "received", 200, {"port": 1},
     "unrecognized", {"reply_status": None}),
    ("mutation-200-odd-status", "POST", "/set_parameter/", "received", 200,
     {"status": "weird", "outcome": block()}, "unrecognized", {"reply_status": "weird"}),
    ("read-200-without-status", "GET", "/model_info/", "received", 200, {"a": 1}, "success", {}),
    ("open-post-read-200-without-status", "POST", "/document_summary/", "received", 200,
     {"title": "A"}, "success", {}),
    ("200-partial-with-zero-failed-is-never-recomputed", "POST", "/set_parameter/", "received", 200,
     {"status": "partial", "outcome": block(requested=1, succeeded=[5], failed=[])}, "partial",
     {"failed": [], "failed_count": 0}),
    ("200-success-with-failed-items-is-never-recomputed", "POST", "/set_parameter/", "received",
     200, {"status": "success", "outcome": block(failed=[{"item": 1, "reason": "x"}])},
     "success", {"failed_count": 1}),
]


@pytest.mark.parametrize("name,method,endpoint,kind,http_status,body,label,expected",
                         OUTCOME_ROWS, ids=["outcome-" + row[0] for row in OUTCOME_ROWS])
def test_outcome_row(name, method, endpoint, kind, http_status, body, label, expected):
    entry = build(body, method=method, endpoint=endpoint, kind=kind, http_status=http_status)

    assert entry["outcome"] == label
    for key, value in expected.items():
        assert entry[key] == value, key
    if label not in ("rejected_auth", "rejected_integrity", "rejected_document"):
        assert "reason" not in entry
    if label != "unrecognized":
        assert "reply_status" not in entry


def test_outcome_not_sent_builds_no_entry():
    assert build({"status": "success"}, kind="not-sent", http_status=None) is None


def test_outcome_integrity_file_list_is_never_copied():
    body, _status = trust.integrity_failure(["secret_dir/a.py", "b.py"])

    entry = build(body, http_status=423)

    assert "a.py" not in json.dumps(entry) and "b.py" not in json.dumps(entry)
    assert entry["outcome"] == "rejected_integrity"


def test_outcome_with_no_provenance_kind_reads_as_received():
    entry = audit.build_entry(CALL, "POST", "/set_parameter/", {"kind": None, "http_status": 200},
                              {"status": "success", "outcome": block()}, duration_ms=1, now=NOW,
                              server_pid=1)

    assert entry["outcome"] == "success" and entry["kind"] is None
    assert entry["process"] is None


def test_outcome_label_is_one_of_the_documented_labels():
    labels = set(row[6] for row in OUTCOME_ROWS)
    assert labels <= set(audit.OUTCOME_LABELS)
    assert len(audit.OUTCOME_LABELS) == len(set(audit.OUTCOME_LABELS)) == 12


def test_outcome_never_copies_message_error_or_read_data():
    body = {"status": "success", "message": "SECRET-MESSAGE", "error": "SECRET-ERROR",
            "elements": ["SECRET-READ"], "outcome": block(), "files": ["SECRET-FILE"]}

    text = json.dumps(build(body))

    for word in ("SECRET-MESSAGE", "SECRET-ERROR", "SECRET-READ", "SECRET-FILE"):
        assert word not in text


# ------------------------------------------------------- outcome_block_missing

def test_outcome_block_missing_flags_a_mutation_reply_without_the_block():
    assert build({"status": "success"}, endpoint="/set_parameter/")["outcome_block_missing"] is True
    assert build({"status": "failed"}, endpoint="/set_parameter/",
                 http_status=422)["outcome_block_missing"] is True


def test_outcome_block_missing_is_absent_on_activate_document():
    entry = build({"status": "success"}, endpoint="/activate_document/")

    assert "outcome_block_missing" not in entry


def test_outcome_block_missing_is_absent_for_refusals_and_reads():
    assert "outcome_block_missing" not in build({"error": "bad"}, http_status=400)
    assert "outcome_block_missing" not in build({"status": "success"}, http_status=401)
    assert "outcome_block_missing" not in build({"status": "success"}, method="GET",
                                                endpoint="/model_info/")
    assert "outcome_block_missing" not in build({"status": "success", "outcome": block()})


# ------------------------------------------------------------------ mutation

def test_mutation_open_read_copy_equals_trust():
    assert audit.OPEN_POST_READ_ROUTES == trust.OPEN_POST_READ_ROUTES


def test_mutation_flag_for_get_and_execute_code():
    assert audit.is_mutation("GET", "/set_parameter/") is False
    assert audit.is_mutation("POST", "/execute_code/") is True
    for route in trust.OPEN_POST_READ_ROUTES:
        assert audit.is_mutation("POST", route) is False


def _post_routes():
    return [r for r in route_inventory() if "POST" in r.methods]


def test_mutation_equals_the_handler_gate_for_every_post_route():
    routes = _post_routes()
    assert len(routes) > 30
    for route in routes:
        gated = "gate_or_response" in reachable_calls(route)
        computed = audit.is_mutation("POST", audit.route_parts(route.path)[0])
        assert computed == gated, route.path


def test_mutation_every_gated_route_reaches_an_outcome_builder_but_the_exempt_one():
    builders = {"finalize_outcome", "build_outcome", "exception_outcome"}
    without = set()
    for route in _post_routes():
        if "gate_or_response" not in reachable_calls(route):
            continue
        if not (reachable_calls(route) & builders):
            without.add(audit.route_parts(route.path)[0])

    assert without == set(audit.ROUTES_WITHOUT_OUTCOME_BLOCK)
    assert sorted(audit.ROUTES_WITHOUT_OUTCOME_BLOCK) == ["/activate_document/"]


def test_mutation_field_is_written_into_the_entry():
    assert build({"status": "success", "outcome": block()})["mutation"] is True
    assert build({"a": 1}, method="GET", endpoint="/model_info/")["mutation"] is False


def test_document_refusal_codes_equal_the_identity_constants():
    with open(os.path.join(REVIT_MCP_DIR, "identity.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    found = set(node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                and (re.match(r"^document-[a-z-]+$", node.value) or node.value == "no-open-document"))

    assert audit.DOCUMENT_REFUSAL_CODES == found
    assert len(found) == 11


# ----------------------------------------------------------------- documents

def doc_body(token, title, path, **extra):
    body = {"status": "success", "outcome": block(),
            "document": {"document": token, "title": title, "path": path, "active": True,
                         "saved": True}}
    body.update(extra)
    return body


def test_document_from_the_reply_descriptor():
    entry = build(doc_body("doc1.a.1", "A", "C:/m/A.rvt"))

    assert entry["document"] == {"token": "doc1.a.1", "title": "A", "path": "C:/m/A.rvt"}
    assert entry["document_source"] == "reply_document"
    assert entry["document_role"] == "used"


def test_document_same_title_is_told_apart_by_token_and_path():
    first = build(doc_body("doc1.a.1", "A", "C:/m/A.rvt"))
    second = build(doc_body("doc1.a.2", "A", "D:/other/A.rvt"))

    assert first["document"]["title"] == second["document"]["title"]
    assert first["document"]["token"] != second["document"]["token"]
    assert first["document"]["path"] != second["document"]["path"]


def test_document_from_documents_changed_prefers_the_project_entry():
    family = {"role": "family", "changed": True, "saved": False, "is_family_document": True,
              "title": "Fam", "path": ""}
    project = {"document": "doc1.p.1", "title": "P", "path": "C:/m/P.rvt", "role": "project",
               "changed": False, "saved": True, "active": True}
    body = {"status": "success", "outcome": block(), "documents_changed": [family, project]}

    entry = build(body)

    assert entry["document"] == {"token": "doc1.p.1", "title": "P", "path": "C:/m/P.rvt"}
    assert entry["document_source"] == "documents_changed"
    assert entry["document_role"] == "used"
    assert [e["role"] for e in entry["documents_changed"]] == ["family", "project"]
    assert entry["documents_changed"][1] == {
        "token": "doc1.p.1", "title": "P", "path": "C:/m/P.rvt", "role": "project",
        "changed": False, "saved": True, "is_family_document": None}
    assert "active" not in entry["documents_changed"][1]


def test_document_documents_changed_is_capped_at_twenty():
    many = [{"document": "doc1.x.{}".format(i), "role": "project", "title": "T", "path": ""}
            for i in range(1, 31)]

    entry = build({"status": "success", "outcome": block(), "documents_changed": many})

    assert len(entry["documents_changed"]) == audit.DOCUMENTS_CHANGED_MAX == 20


def test_document_from_the_request_argument_when_the_reply_has_none():
    call = audit.CallState("c", "tool_x", {"document": "doc1.b.2"}, None)

    entry = build({"status": "success", "outcome": block()}, call=call)

    assert entry["document"] == {"token": "doc1.b.2", "title": None, "path": None}
    assert entry["document_source"] == "request_argument"
    assert entry["document_role"] == "addressed"


def test_document_from_the_handshake_title_hint_only():
    entry = build({"status": "success", "outcome": block()}, active_title_hint="H")

    assert entry["document"] == {"token": None, "title": "H", "path": None}
    assert entry["document_source"] == "handshake_active_title"
    assert entry["document_role"] == "addressed"


def test_document_reply_beats_argument_and_hint():
    call = audit.CallState("c", "tool_x", {"document": "doc1.b.2"}, None)

    entry = build(doc_body("doc1.a.1", "A", "C:/m/A.rvt"), call=call, active_title_hint="H")

    assert entry["document"]["token"] == "doc1.a.1"
    assert entry["document_source"] == "reply_document"


def test_document_nothing_known_is_null_and_named_none():
    entry = build({"status": "success", "outcome": block(succeeded=[])})

    assert entry["document"] is None
    assert entry["document_source"] == "none"
    assert entry["document_role"] is None
    assert entry["succeeded"] == [] and entry["succeeded_count"] == 0


def test_document_execute_code_is_addressed_with_its_scope_notice():
    notice = "x" * 700
    body = {"status": "success", "outcome": block(), "document_scope": notice}

    entry = build(body, endpoint="/execute_code/", active_title_hint="H")

    assert entry["document_role"] == "addressed"
    assert entry["document"] == {"token": None, "title": "H", "path": None}
    assert entry["document_scope"] == "x" * audit.NOTICE_MAX
    assert "document_scope" not in build({"status": "success", "outcome": block(),
                                          "document_scope": "n"}, endpoint="/set_parameter/")


def test_document_execute_code_never_gets_a_changed_document():
    body = doc_body("doc1.a.1", "A", "C:/m/A.rvt", documents_changed=[
        {"document": "doc1.z.9", "role": "project", "title": "Z", "path": "", "changed": True}])

    entry = build(body, endpoint="/execute_code/")

    assert entry["document_role"] == "addressed"
    assert "documents_changed" not in entry


def test_document_observed_active_document_is_a_separate_field():
    body = {"status": "success", "outcome": block(),
            "observed_active_document": {"document": "doc1.o.1", "title": "O", "path": "C:/o.rvt",
                                         "active": True}}

    entry = build(body)

    assert entry["observed_active_document"] == {"token": "doc1.o.1", "title": "O",
                                                 "path": "C:/o.rvt"}
    assert entry["document"] is None


# --------------------------------------------------------------------- lists

def test_list_succeeded_is_capped_with_the_true_total_and_keeps_order():
    ids = list(range(1000, 1600))

    entry = build({"status": "success", "outcome": block(requested=600, succeeded=ids)})

    assert entry["succeeded"] == ids[:500] and entry["succeeded_count"] == 600


def test_list_failed_is_capped_and_reasons_are_truncated():
    failed = [{"item": i, "reason": "r" * 900, "extra": "dropped"} for i in range(150)]

    entry = build({"status": "failed", "outcome": block(requested=150, succeeded=[], failed=failed)},
                  http_status=422)

    assert len(entry["failed"]) == 100 and entry["failed_count"] == 150
    assert [f["item"] for f in entry["failed"]] == list(range(100))
    assert all(set(f) == {"item", "reason"} and len(f["reason"]) == 500 for f in entry["failed"])


def test_list_revit_failures_are_capped_and_truncated():
    failures = ["f" * 900 for _ in range(80)]

    entry = build({"status": "rolled_back", "outcome": block("RolledBack", 1, [], [], failures)},
                  http_status=409)

    assert len(entry["revit_failures"]) == 50
    assert all(len(f) == 500 for f in entry["revit_failures"])


def test_list_no_outcome_block_gives_null_lists_and_counts():
    entry = build({"status": "success"})

    for key in ("transaction_status", "requested", "succeeded", "succeeded_count", "failed",
                "failed_count", "revit_failures"):
        assert entry[key] is None, key


def test_list_top_level_transaction_status_is_used_without_a_block():
    entry = build({"status": "rolled_back", "transaction_status": "RolledBack"}, http_status=409)

    assert entry["transaction_status"] == "RolledBack" and entry["succeeded"] is None


# -------------------------------------------------------------------- schema

def schema_entries():
    yield build({"status": "success", "outcome": block()})
    yield build({"status": "rolled_back", "outcome": block("RolledBack", 1, [], [], ["x"])},
                http_status=409)
    yield build(None, kind="unknown", http_status=None)
    yield build(None, method="GET", endpoint="/model_info/", kind="no-reply", http_status=None)
    yield build({"status": "success", "outcome": block(), "document_scope": "n"},
                endpoint="/execute_code/", cancelled=True, active_title_hint="H")
    yield build(doc_body("doc1.a.1", "A", "C:/m/A.rvt"))


def test_schema_every_entry_has_the_always_present_fields_and_no_unknown_key():
    for entry in schema_entries():
        assert set(audit.ALWAYS_PRESENT_FIELDS) <= set(entry), set(audit.ALWAYS_PRESENT_FIELDS) - set(entry)
        assert set(entry) <= set(audit.SCHEMA_1_FIELDS), set(entry) - set(audit.SCHEMA_1_FIELDS)
        assert entry["schema"] == 1
        json.dumps(entry)


def test_schema_always_present_is_a_subset_of_schema_1():
    assert set(audit.ALWAYS_PRESENT_FIELDS) <= set(audit.SCHEMA_1_FIELDS)
    assert len(set(audit.SCHEMA_1_FIELDS)) == len(audit.SCHEMA_1_FIELDS)


def test_schema_process_uses_port_never_actual_port():
    entry = build({"status": "success", "outcome": block()})

    assert entry["process"] == {"pid": 111, "port": 48884, "session_token": "tok-a",
                                "revit_version": "2024"}
    assert "actual_port" not in json.dumps(entry)


def test_schema_cancelled_is_written_only_when_true():
    assert "cancelled" not in build({"status": "success", "outcome": block()})
    assert build(None, kind="unknown", http_status=None, cancelled=True)["cancelled"] is True


def test_schema_requested_target_is_the_provenance_requested_for_every_kind():
    assert build({"status": "success", "outcome": block()})["requested_target"] == REQUESTED
    assert build(None, kind="no-reply", http_status=None, method="GET",
                 endpoint="/model_info/")["requested_target"] == REQUESTED
