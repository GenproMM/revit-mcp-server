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


def test_schema_request_side_fields_are_always_present():
    for name in ("windows_user", "args", "user_request", "user_request_missing",
                 "user_request_length", "user_request_source"):
        assert name in audit.ALWAYS_PRESENT_FIELDS, name
    for entry in schema_entries():
        for name in ("windows_user", "args", "user_request", "user_request_missing",
                     "user_request_length", "user_request_source"):
            assert name in entry, name


# ------------------------------------------------------------ args, code, request

# A secret of the real shape (secrets.token_urlsafe(32): 43 characters).
SECRET = "kQ3vZ9_xLm2-Tn8RwYb5Hc1JdFgPaUs7EoIe0Aq4XyB"
OK = {"status": "success", "outcome": block()}


def with_args(args, tool="tool_x", user_request=None):
    return audit.CallState("c-args", tool, args, user_request)


def args_entry(args, tool="tool_x", secret=None, **kwargs):
    return build(OK, call=with_args(args, tool), secret=secret, **kwargs)


def test_args_drop_ctx_and_none_values():
    entry = args_entry({"element_id": 5, "value": "new", "ctx": object(), "target": None})

    assert entry["args"] == {"element_id": 5, "value": "new"}
    assert "args_truncated" not in entry


def test_args_long_string_is_cut_and_its_length_listed():
    entry = args_entry({"value": "x" * 600})

    assert entry["args"]["value"] == "x" * 500
    assert entry["args_truncated"] == [{"arg": "value", "length": 600}]


def test_args_cyrillic_string_is_cut_by_code_points_not_bytes():
    text = "\u0436" * 600

    entry = args_entry({"value": text})

    assert len(entry["args"]["value"]) == 500
    assert len(entry["args"]["value"].encode("utf-8")) == 1000
    assert entry["args_truncated"] == [{"arg": "value", "length": 600}]
    line = audit.serialize_entry(entry, None)
    assert "\u0436" * 500 in line and "\\u0436" not in line


def test_args_long_list_keeps_the_first_200_in_order():
    entry = args_entry({"element_ids": list(range(250))})

    assert entry["args"]["element_ids"] == list(range(200))
    assert entry["args_truncated"] == [{"arg": "element_ids", "count": 250}]


def test_args_list_of_exactly_200_is_not_listed_as_truncated():
    entry = args_entry({"element_ids": list(range(200))})

    assert len(entry["args"]["element_ids"]) == 200 and "args_truncated" not in entry


def test_args_nested_dict_is_shaped_recursively_with_dotted_paths():
    entry = args_entry({"options": {"note": "n" * 700, "ids": list(range(300)), "keep": 1}})

    assert entry["args"]["options"]["keep"] == 1
    assert len(entry["args"]["options"]["note"]) == 500
    assert len(entry["args"]["options"]["ids"]) == 200
    assert {"arg": "options.note", "length": 700} in entry["args_truncated"]
    assert {"arg": "options.ids", "count": 300} in entry["args_truncated"]


def test_args_bytes_and_arbitrary_objects_become_their_type_name():
    class Odd(object):
        pass

    entry = args_entry({"blob": b"\x00\x01", "thing": Odd(), "items": [b"x", 1]})

    assert entry["args"] == {"blob": "bytes", "thing": "Odd", "items": ["bytes", 1]}


def test_args_nesting_beyond_the_depth_limit_becomes_a_type_name():
    deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}

    entry = args_entry({"deep": deep})

    assert entry["args"]["deep"]["a"]["b"]["c"] == {"d": "dict"}
    json.dumps(entry)


def test_args_scalars_keep_their_json_type_and_a_non_finite_float_does_not_break_json():
    entry = args_entry({"flag": True, "n": 3, "f": 1.5, "bad": float("nan")})

    assert entry["args"]["flag"] is True and entry["args"]["n"] == 3 and entry["args"]["f"] == 1.5
    assert entry["args"]["bad"] == "float"


def test_args_requested_new_parameter_value_is_written_verbatim():
    entry = args_entry({"element_id": 7, "parameter_name": "Comments", "value": "\u041d\u043e\u0432\u043e\u0435"},
                       tool="set_parameter")

    assert entry["args"]["value"] == "\u041d\u043e\u0432\u043e\u0435"
    assert entry["args"]["parameter_name"] == "Comments"


def test_args_never_hold_the_http_body_or_reply_data():
    body = {"status": "success", "outcome": block(), "data": {"huge": "r" * 1000},
            "_mcp": {"secret": SECRET}}

    entry = build(body, call=with_args({"element_id": 5}), secret=SECRET)

    text = json.dumps(entry)
    assert "huge" not in text and "_mcp" not in text and "r" * 20 not in text


CODE_TOOL_NAME = "execute_revit_code"


def code_entry(code, secret=None, tool=CODE_TOOL_NAME):
    return build(OK, call=with_args({"code": code, "description": "d"}, tool),
                 endpoint="/execute_code/", secret=secret)


def test_code_long_text_is_cut_to_8192_with_length_and_sha256():
    import hashlib

    code = "print(1)\n" * 1112  # 10008 characters

    entry = code_entry(code)

    assert len(entry["args"]["code"]) == 8192 and entry["args"]["code"] == code[:8192]
    assert entry["code_length"] == len(code)
    assert entry["code_sha256"] == hashlib.sha256(code.encode("utf-8")).hexdigest()


def test_code_short_text_is_stored_whole_with_its_length_and_hash():
    import hashlib

    entry = code_entry("x = 1")

    assert entry["args"]["code"] == "x = 1"
    assert entry["code_length"] == 5
    assert entry["code_sha256"] == hashlib.sha256(b"x = 1").hexdigest()


def test_code_cut_is_not_reported_as_an_args_truncated_500_cut():
    entry = code_entry("a" * 10000)

    assert entry["code_length"] == 10000
    assert all(item["arg"] != "code" for item in entry.get("args_truncated", []))
    assert len(entry["args"]["description"]) == 1


def test_code_length_counts_code_points_and_the_hash_covers_utf8_bytes():
    import hashlib

    code = "\u0436" * 600

    entry = code_entry(code)

    assert entry["code_length"] == 600
    assert entry["code_sha256"] == hashlib.sha256(code.encode("utf-8")).hexdigest()
    assert entry["args"]["code"] == code


def test_code_hash_is_over_the_original_even_when_the_secret_is_redacted():
    import hashlib

    code = "token = '" + SECRET + "'"

    entry = code_entry(code, secret=SECRET)

    assert SECRET not in json.dumps(entry)
    assert entry["args"]["code"] == "token = '" + audit.REDACTED + "'"
    assert entry["code_sha256"] == hashlib.sha256(code.encode("utf-8")).hexdigest()
    assert entry["code_length"] == len(code)


def test_code_fields_exist_only_for_execute_revit_code():
    other = code_entry("x = 1", tool="some_other_tool")

    assert "code_length" not in other and "code_sha256" not in other
    assert "code_length" in code_entry("x = 1")


def request_entry(user_request, **kwargs):
    return build(OK, call=with_args({}, user_request=user_request), **kwargs)


def test_user_request_absent_is_recorded_as_missing():
    entry = request_entry(None)

    assert entry["user_request"] is None and entry["user_request_missing"] is True
    assert entry["user_request_length"] is None and entry["user_request_source"] is None


def test_user_request_blank_is_missing_too():
    for blank in ("", "   ", "\n\t "):
        entry = request_entry(blank)

        assert entry["user_request_missing"] is True and entry["user_request"] is None, repr(blank)


def test_user_request_long_text_is_cut_to_2000_with_its_true_length():
    entry = request_entry("q" * 2500)

    assert entry["user_request"] == "q" * 2000
    assert entry["user_request_length"] == 2500
    assert entry["user_request_missing"] is False and entry["user_request_source"] == "assistant"


def test_user_request_is_verbatim_and_says_the_assistant_reported_it():
    text = "\u0421\u0434\u0435\u043b\u0430\u0439 \u0441\u0442\u0435\u043d\u044b \u0442\u043e\u043b\u0449\u0435"

    entry = request_entry(text)

    assert entry["user_request"] == text and entry["user_request_length"] == len(text)
    assert entry["user_request_source"] == "assistant"
    assert text in audit.serialize_entry(entry, None)


def test_user_request_with_a_newline_serializes_to_one_line():
    entry = request_entry("first\nsecond\r\nthird")

    line = audit.serialize_entry(entry, None)

    assert "\n" not in line and "\r" not in line and "first\\nsecond\\r\\nthird" in line


def test_user_request_is_never_claimed_as_seen_by_the_server():
    entry = request_entry("anything")

    assert entry["user_request_source"] == "assistant"
    assert "verified" not in json.dumps(entry)


def test_windows_user_is_domain_backslash_user(monkeypatch):
    monkeypatch.setenv("USERDOMAIN", "CORP")
    monkeypatch.setenv("USERNAME", "eng")
    audit._reset()

    assert audit.windows_user() == "CORP\\eng"


def test_windows_user_falls_back_to_getpass(monkeypatch):
    monkeypatch.delenv("USERDOMAIN", raising=False)
    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.setattr(audit.getpass, "getuser", lambda: "fallback")
    audit._reset()

    assert audit.windows_user() == "fallback"


def test_windows_user_is_unknown_when_nothing_answers(monkeypatch):
    monkeypatch.delenv("USERDOMAIN", raising=False)
    monkeypatch.delenv("USERNAME", raising=False)

    def broken():
        raise OSError("no user")

    monkeypatch.setattr(audit.getpass, "getuser", broken)
    audit._reset()

    assert audit.windows_user() == "unknown"


def test_windows_user_is_computed_once_per_process(monkeypatch):
    monkeypatch.setenv("USERDOMAIN", "CORP")
    monkeypatch.setenv("USERNAME", "eng")
    audit._reset()
    first = audit.windows_user()

    monkeypatch.setenv("USERNAME", "other")

    assert audit.windows_user() == first == "CORP\\eng"
    audit._reset()
    assert audit.windows_user() == "CORP\\other"


def test_windows_user_is_written_and_nothing_else_about_the_person_or_machine():
    entry = build(OK, windows_user="CORP\\eng")

    assert entry["windows_user"] == "CORP\\eng"
    text = json.dumps(entry)
    for forbidden in ("COMPUTERNAME", "hostname", "client", "session_id", "ip_address"):
        assert forbidden not in text


def test_redact_text_replaces_the_raw_and_the_json_escaped_secret():
    odd = 'ab"cd\\ef-0123456789-xyz'

    assert audit.redact_text("a " + odd + " b", odd) == "a " + audit.REDACTED + " b"
    assert audit.redact_text(json.dumps(odd)[1:-1], odd) == audit.REDACTED
    assert audit.redact_text("plain", None) == "plain"
    assert audit.redact_text("plain", "") == "plain"


def test_redact_clip_redacts_before_it_cuts():
    text = "z" * 480 + SECRET + "z" * 100

    clipped, original = audit._clip(text, 500, SECRET)

    assert original == len(text)
    assert SECRET not in clipped and SECRET[:16] not in clipped
    assert len(clipped) == 500


def test_redact_walks_dicts_and_lists_and_leaves_other_types_alone():
    value = {"a": [SECRET, {"b": "x" + SECRET}], "n": 5, "f": None}

    out = audit.redact(value, SECRET)

    assert out == {"a": [audit.REDACTED, {"b": "x" + audit.REDACTED}], "n": 5, "f": None}


def test_redact_secret_inside_an_args_string_becomes_redacted():
    entry = args_entry({"note": "see " + SECRET + " ok"}, secret=SECRET)

    assert entry["args"]["note"] == "see " + audit.REDACTED + " ok"


def test_redact_secret_named_argument_keys_lose_their_value():
    entry = args_entry({"api_key": "k1", "password": 12345, "secret": {"a": 1}, "token": "t",
                        "X_Token": ["a"], "element_id": 5}, secret=None)

    for key in ("api_key", "password", "secret", "token", "X_Token"):
        assert entry["args"][key] == audit.REDACTED, key
    assert entry["args"]["element_id"] == 5


def test_redact_secret_named_keys_inside_nested_argument_dicts():
    entry = args_entry({"options": {"Password": "p", "fine": "v"}})

    assert entry["args"]["options"] == {"Password": audit.REDACTED, "fine": "v"}


def test_redact_keeps_the_process_session_token():
    entry = build(OK, secret=SECRET)

    assert entry["process"]["session_token"] == "tok-a"
    assert entry["requested_target"] == REQUESTED


def test_redact_secret_in_every_string_of_the_entry():
    body = {"status": "partial", "document": {"document": "doc1.x", "title": "T " + SECRET,
                                               "path": "C:/" + SECRET + ".rvt"},
            "outcome": block(requested=2, succeeded=[5], failed=[
                {"item": 6, "reason": "bad " + SECRET}], failures=["warn " + SECRET])}
    call = with_args({"note": SECRET}, user_request="please " + SECRET)

    entry = build(body, call=call, endpoint="/set_parameter/" + SECRET, secret=SECRET)

    line = audit.serialize_entry(entry, SECRET)
    assert SECRET not in line
    assert entry["failed"][0]["reason"] == "bad " + audit.REDACTED
    assert entry["revit_failures"] == ["warn " + audit.REDACTED]
    assert entry["document"]["title"] == "T " + audit.REDACTED
    assert entry["user_request"] == "please " + audit.REDACTED
    assert entry["route_arg"] == audit.REDACTED


def test_redact_secret_straddling_the_argument_cut_leaves_no_16_character_run():
    text = "a" * 480 + SECRET + "b" * 120

    entry = args_entry({"value": text}, secret=SECRET)

    line = audit.serialize_entry(entry, SECRET)
    for start in range(len(SECRET) - 15):
        assert SECRET[start:start + 16] not in line, start
    assert entry["args_truncated"] == [{"arg": "value", "length": len(text)}]


def test_redact_secret_straddling_the_user_request_and_reason_cuts():
    long_request = "u" * 1990 + SECRET
    long_reason = "r" * 495 + SECRET
    body = {"status": "failed", "outcome": block(succeeded=[], failed=[
        {"item": 1, "reason": long_reason}])}

    entry = build(body, call=with_args({}, user_request=long_request), http_status=422,
                  secret=SECRET)

    line = audit.serialize_entry(entry, SECRET)
    for start in range(len(SECRET) - 15):
        assert SECRET[start:start + 16] not in line, start


def test_redact_secret_with_a_quote_and_a_backslash_in_neither_form():
    odd = 'pre"mid\\post-0123456789-abcdef'
    call = with_args({"note": "x " + odd + " y"}, user_request=odd)

    entry = build(OK, call=call, secret=odd)

    line = audit.serialize_entry(entry, odd)
    assert odd not in line and json.dumps(odd)[1:-1] not in line


def test_redact_without_a_secret_replaces_nothing():
    entry = args_entry({"note": SECRET}, secret=None)

    assert entry["args"]["note"] == SECRET
    assert audit.REDACTED not in audit.serialize_entry(entry, None)


def test_redact_entry_for_a_post_has_no_mcp_key_anywhere():
    entry = build(OK, call=with_args({"element_id": 5}), secret=SECRET)

    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                for inner in keys(item):
                    yield inner
        elif isinstance(value, list):
            for item in value:
                for inner in keys(item):
                    yield inner

    assert "_mcp" not in set(keys(entry))
    assert set(entry) <= set(audit.SCHEMA_1_FIELDS)
