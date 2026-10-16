# -*- coding: utf-8 -*-
"""Unit tests for the Phase 2 preflight classifier (gates G1-G5).

The operator procedure (tests/test_phase2_preflight.py) needs an installed Revit
with pyRevit, two open models and, for G5, two listeners on one port. What is
tested here is everything that can be decided offline: that an incomplete,
contradictory, synthetic or missing record is STOP and never a pass, that the
evidence template covers every field a passing record needs, that the
IronPython snippets the engineer pastes are safe for IronPython 3.4 and
read-only, and that the procedure itself can never send a model-route request.

A passing classification here is NOT a live result. It only says a record is
complete and self-consistent; the engineer's decision (plan 02-20 task 2) is
what approves a mechanism. The classifier never emits an "approved" verdict.

Needs no Revit, no pyRevit and no network.
"""

import ast
import copy
import importlib.util
import json
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROCEDURE_PATH = os.path.join(REPO_ROOT, "tests", "test_phase2_preflight.py")

# Loaded under a different module name: this file is itself named
# test_phase2_preflight, and pytest's basename import would collide.
_spec = importlib.util.spec_from_file_location("phase2_preflight_procedure", PROCEDURE_PATH)
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


# ---------------------------------------------------------------- fixtures


def good_g1():
    return {
        "live": True,
        "synthetic": False,
        "revit_version": "2025",
        "pyrevit_version": "6.5.3",
        "injection": {
            "handler_signatures": [
                {"route": "/status/", "args": ["doc", "request"]},
                {"route": "/model_info/", "args": ["request"]},
            ],
            "injected": {"doc": True, "uidoc": True, "request": True},
            "external_event": True,
            "wrapper_preserves_semantics": True,
            "source_ref": "pyRevit routes server dispatch, read in the installed extension",
        },
        "token": {
            "facility": "System.Guid.NewGuid",
            "initialized_at": "process-start",
            "stable_across_requests": True,
            "differs_across_restarts": True,
        },
        "port": {
            "source": "prefix list of the routes server HttpListener",
            "is_requested_selector_or_default": False,
            "reported_port": 48884,
            "reported_pid": 1234,
            "os_snapshot": {"port": 48884, "pids": [1234]},
        },
    }


def good_g2():
    return {
        "live": True,
        "synthetic": False,
        "open_objects": [
            {"title": "Project1", "path": "", "kind": "unsaved", "object_id": "o1", "raw_handle": "h1"},
            {"title": "Project1", "path": "", "kind": "unsaved", "object_id": "o2", "raw_handle": "h2"},
            {"title": "Shared", "path": "C:/a/Shared.rvt", "kind": "saved", "object_id": "o3", "raw_handle": "h3"},
            {"title": "Shared", "path": "C:/b/Shared.rvt", "kind": "saved", "object_id": "o4", "raw_handle": "h4"},
        ],
        "wrapper_lifetime": {"stable_while_open": True, "stable_across_enumerations": True},
        "close_and_replace": {
            "closed_object_id": "o2",
            "closed_object_invalid_after_close": True,
            "survivor_resolves": True,
            "replacement": {
                "title": "Project1",
                "path": "",
                "object_id": "o5",
                "raw_handle": "h2",
                "presentation_matches_closed": True,
            },
            "raw_handle_equal_to_closed": True,
        },
        "token_design": {
            "registry_issued": True,
            "monotonic_unique_per_incarnation": True,
            "tombstone_after_close": True,
            "raw_handle_used_as_selector": False,
        },
    }


def _direction(active, target, title, levels):
    return {
        "active_before": active,
        "target": target,
        "active_after": active,
        "ui_switched": False,
        "summary": {"title": title, "level_count": len(levels)},
        "levels": levels,
        "data_from": target,
    }


def good_g3():
    return {
        "live": True,
        "synthetic": False,
        "code_path": "document-only",
        "accessors_reading_active_state": [],
        "directions": {
            "A_active_read_B": _direction("A", "B", "Model B", ["B-L1", "B-L2"]),
            "B_active_read_A": _direction("B", "A", "Model A", ["A-L1", "A-L2", "A-L3"]),
        },
    }


def _case(outcome="activated", policy="allow", dialog=False, active_after=True):
    return {
        "tested": True,
        "outcome": outcome,
        "dialog_observed": dialog,
        "active_after_is_target": active_after,
        "policy": policy,
    }


def good_g4():
    return {
        "live": True,
        "synthetic": False,
        "api": "UIApplication.OpenAndActivateDocument(String)",
        "external_event_context": True,
        "cases": {
            "saved": _case(),
            "unsaved": _case(),
            "workshared": _case(outcome="dialog", policy="refuse", dialog=True, active_after=False),
        },
    }


def good_g5():
    return {
        "live": True,
        "synthetic": False,
        "port": 48884,
        "os_snapshot": {"source": "Get-NetTCPConnection", "taken_before_any_send": True, "pids": [111, 222]},
        "independent_pid_capture": {"method": "Get-Process revit", "pids": [222, 111]},
        "model_route_send_count": 0,
    }


def good_evidence():
    return {
        "g1": good_g1(),
        "g2": good_g2(),
        "g3": good_g3(),
        "g4": good_g4(),
        "g5": good_g5(),
    }


def mutated(builder, path, value):
    """A copy of builder() with the dotted `path` set (or deleted if value is DELETE)."""
    record = builder()
    parts = path.split(".")
    node = record
    for part in parts[:-1]:
        node = node[part]
    if value is DELETE:
        del node[parts[-1]]
    else:
        node[parts[-1]] = value
    return record


DELETE = object()

CLASSIFIERS = {
    "g1": (pf.classify_g1, good_g1, ("wrapper-compatible", "explicit-route-only")),
    "g2": (pf.classify_g2, good_g2, ("document-object-binding-provable",)),
    "g3": (pf.classify_g3, good_g3, ("document-only-path",)),
    "g4": (pf.classify_g4, good_g4, ("explicit-activation-api",)),
    "g5": (pf.classify_g5, good_g5, ("listener-inventory-complete",)),
}


def _leaf_paths(node, prefix=""):
    if isinstance(node, dict):
        paths = set()
        for key, value in node.items():
            paths |= _leaf_paths(value, "{}.{}".format(prefix, key) if prefix else key)
        return paths
    if isinstance(node, list) and node and all(isinstance(i, dict) for i in node):
        return _leaf_paths(node[0], prefix + "[]")
    return {prefix}


# ------------------------------------------- a complete record is not a stop


@pytest.mark.parametrize("gate", sorted(CLASSIFIERS))
def test_complete_record_reaches_a_continue_verdict(gate):
    classify, builder, continue_verdicts = CLASSIFIERS[gate]
    verdict, reasons = classify(builder())
    assert verdict in continue_verdicts
    assert reasons == []


# --------------------------------------- missing / junk input is always STOP


JUNK = [None, {}, [], "", "PASS", 0, 1, True, ["g1"], {"live": True}, {"live": "yes"}]


@pytest.mark.parametrize("gate", sorted(CLASSIFIERS))
@pytest.mark.parametrize("junk", JUNK, ids=[repr(j) for j in JUNK])
def test_missing_or_malformed_record_is_stop_not_an_exception(gate, junk):
    classify = CLASSIFIERS[gate][0]
    verdict, reasons = classify(junk)
    assert verdict == "stop"
    assert reasons


@pytest.mark.parametrize("gate", sorted(CLASSIFIERS))
def test_offline_or_synthetic_record_is_stop(gate):
    classify, builder, _ = CLASSIFIERS[gate]
    for field, value in (("live", False), ("synthetic", True)):
        verdict, reasons = classify(mutated(builder, field, value))
        assert verdict == "stop", field
        assert reasons


@pytest.mark.parametrize("gate", sorted(CLASSIFIERS))
def test_every_required_field_missing_is_stop(gate):
    classify, builder, _ = CLASSIFIERS[gate]
    top_level = [k for k in builder() if k not in ("synthetic", "revit_version", "pyrevit_version")]
    for key in top_level:
        record = builder()
        del record[key]
        verdict, reasons = classify(record)
        assert verdict == "stop", "{} deleted".format(key)
        assert reasons


# ------------------------------------------------------------------- G1


def test_g1_wrapper_not_demonstrated_selects_explicit_route_only():
    for value in (False, None):
        record = mutated(good_g1, "injection.wrapper_preserves_semantics", value)
        verdict, reasons = pf.classify_g1(record)
        assert verdict == "explicit-route-only"
        assert reasons == []


def test_g1_wrapper_claim_contradicting_missing_injection_is_stop():
    record = mutated(good_g1, "injection.injected.doc", False)
    verdict, reasons = pf.classify_g1(record)
    assert verdict == "stop"
    assert any("wrapper" in r for r in reasons)


@pytest.mark.parametrize(
    "path,value",
    [
        ("injection.injected.doc", False),
        ("injection.injected.request", False),
        ("injection.external_event", False),
        ("injection.external_event", None),
        ("injection.handler_signatures", []),
    ],
)
def test_g1_unobserved_injection_is_stop(path, value):
    record = mutated(good_g1, path, value)
    record["injection"]["wrapper_preserves_semantics"] = None
    verdict, _ = pf.classify_g1(record)
    assert verdict == "stop"


def test_g1_without_a_revit_side_actual_port_source_is_stop():
    for value in (DELETE, "", "   ", None):
        record = mutated(good_g1, "port.source", value)
        verdict, reasons = pf.classify_g1(record)
        assert verdict == "stop"
        assert any("port source" in r for r in reasons)


def test_g1_port_taken_from_the_requested_selector_or_default_is_stop():
    record = mutated(good_g1, "port.is_requested_selector_or_default", True)
    verdict, reasons = pf.classify_g1(record)
    assert verdict == "stop"
    assert any("requested" in r for r in reasons)


def test_g1_port_mismatch_against_the_os_snapshot_is_stop():
    record = mutated(good_g1, "port.os_snapshot.port", 48885)
    verdict, reasons = pf.classify_g1(record)
    assert verdict == "stop"
    assert any("port" in r for r in reasons)


def test_g1_pid_mismatch_against_the_os_snapshot_is_stop():
    record = mutated(good_g1, "port.os_snapshot.pids", [9999])
    verdict, reasons = pf.classify_g1(record)
    assert verdict == "stop"
    assert any("pid" in r.lower() for r in reasons)


def test_g1_two_listeners_on_the_reported_port_is_stop():
    record = mutated(good_g1, "port.os_snapshot.pids", [1234, 5678])
    verdict, reasons = pf.classify_g1(record)
    assert verdict == "stop"
    assert any("listener" in r for r in reasons)


def test_g1_boolean_is_not_accepted_as_a_port_or_pid():
    for path in ("port.reported_port", "port.reported_pid"):
        verdict, _ = pf.classify_g1(mutated(good_g1, path, True))
        assert verdict == "stop", path


@pytest.mark.parametrize(
    "path,value",
    [
        ("token.facility", ""),
        ("token.facility", DELETE),
        ("token.initialized_at", "first-request"),
        ("token.initialized_at", "per-request"),
        ("token.initialized_at", DELETE),
        ("token.stable_across_requests", False),
        ("token.stable_across_requests", None),
        ("token.differs_across_restarts", False),
        ("token.differs_across_restarts", None),
    ],
)
def test_g1_unproven_token_lifetime_is_stop(path, value):
    verdict, reasons = pf.classify_g1(mutated(good_g1, path, value))
    assert verdict == "stop"
    assert any("token" in r for r in reasons)


# ------------------------------------------------------------------- G2


def test_g2_needs_both_an_unsaved_and_a_saved_same_title_pair():
    record = good_g2()
    record["open_objects"] = [o for o in record["open_objects"] if o["kind"] == "unsaved"]
    verdict, reasons = pf.classify_g2(record)
    assert verdict == "stop"
    assert any("saved" in r for r in reasons)
    record = good_g2()
    record["open_objects"] = [o for o in record["open_objects"] if o["kind"] == "saved"]
    verdict, reasons = pf.classify_g2(record)
    assert verdict == "stop"
    assert any("unsaved" in r for r in reasons)


def test_g2_two_open_documents_sharing_one_wrapper_object_is_stop():
    record = good_g2()
    record["open_objects"][1]["object_id"] = record["open_objects"][0]["object_id"]
    verdict, reasons = pf.classify_g2(record)
    assert verdict == "stop"
    assert any("distinct" in r for r in reasons)


@pytest.mark.parametrize(
    "path",
    ["wrapper_lifetime.stable_while_open", "wrapper_lifetime.stable_across_enumerations"],
)
def test_g2_unstable_wrapper_lifetime_is_stop(path):
    verdict, _ = pf.classify_g2(mutated(good_g2, path, False))
    assert verdict == "stop"


@pytest.mark.parametrize(
    "path,value",
    [
        ("close_and_replace.closed_object_invalid_after_close", False),
        ("close_and_replace.survivor_resolves", False),
        ("close_and_replace.replacement.presentation_matches_closed", False),
        ("close_and_replace.closed_object_id", "o-not-open"),
        ("close_and_replace.raw_handle_equal_to_closed", None),
        ("close_and_replace.replacement", DELETE),
    ],
)
def test_g2_incomplete_close_and_replace_measurement_is_stop(path, value):
    verdict, reasons = pf.classify_g2(mutated(good_g2, path, value))
    assert verdict == "stop"
    assert reasons


def test_g2_replacement_wrapper_equal_to_a_prior_object_is_stop():
    record = mutated(good_g2, "close_and_replace.replacement.object_id", "o2")
    verdict, reasons = pf.classify_g2(record)
    assert verdict == "stop"
    assert any("replacement" in r for r in reasons)


def test_g2_recurring_raw_handle_is_survivable_but_a_contradicting_claim_is_stop():
    # The recurring handle is the case the tombstone exists for: still provable.
    verdict, _ = pf.classify_g2(good_g2())
    assert verdict == "document-object-binding-provable"
    # Claiming "not equal" while the recorded handles are equal contradicts itself.
    record = mutated(good_g2, "close_and_replace.raw_handle_equal_to_closed", False)
    verdict, reasons = pf.classify_g2(record)
    assert verdict == "stop"
    assert any("contradict" in r for r in reasons)


@pytest.mark.parametrize(
    "path,value",
    [
        ("token_design.registry_issued", False),
        ("token_design.monotonic_unique_per_incarnation", False),
        ("token_design.tombstone_after_close", False),
        ("token_design.raw_handle_used_as_selector", True),
        ("token_design.raw_handle_used_as_selector", None),
    ],
)
def test_g2_token_design_that_permits_reuse_or_raw_handles_is_stop(path, value):
    verdict, _ = pf.classify_g2(mutated(good_g2, path, value))
    assert verdict == "stop"


# ------------------------------------------------------------------- G3


def test_g3_one_direction_only_is_stop():
    for key in ("A_active_read_B", "B_active_read_A"):
        record = good_g3()
        del record["directions"][key]
        verdict, reasons = pf.classify_g3(record)
        assert verdict == "stop", key
        assert reasons


def test_g3_ui_switch_in_either_direction_is_stop():
    for key in ("A_active_read_B", "B_active_read_A"):
        record = good_g3()
        record["directions"][key]["ui_switched"] = True
        verdict, reasons = pf.classify_g3(record)
        assert verdict == "stop", key
        assert any("switch" in r for r in reasons)


def test_g3_active_document_changed_between_before_and_after_is_stop():
    record = good_g3()
    record["directions"]["A_active_read_B"]["active_after"] = "B"
    verdict, _ = pf.classify_g3(record)
    assert verdict == "stop"


def test_g3_data_that_came_from_the_active_document_is_stop():
    record = good_g3()
    record["directions"]["A_active_read_B"]["data_from"] = "A"
    verdict, reasons = pf.classify_g3(record)
    assert verdict == "stop"
    assert any("data" in r for r in reasons)


def test_g3_identical_answers_for_both_documents_are_stop():
    record = good_g3()
    one = record["directions"]["A_active_read_B"]
    record["directions"]["B_active_read_A"].update(
        summary=copy.deepcopy(one["summary"]), levels=list(one["levels"])
    )
    verdict, reasons = pf.classify_g3(record)
    assert verdict == "stop"
    assert any("identical" in r for r in reasons)


def test_g3_empty_levels_or_missing_summary_is_stop():
    record = good_g3()
    record["directions"]["A_active_read_B"]["levels"] = []
    assert pf.classify_g3(record)[0] == "stop"
    record = good_g3()
    del record["directions"]["B_active_read_A"]["summary"]
    assert pf.classify_g3(record)[0] == "stop"


def test_g3_accessor_that_reads_the_active_document_blocks_the_document_only_path():
    record = good_g3()
    record["accessors_reading_active_state"] = ["revit.doc in get_levels helper"]
    verdict, reasons = pf.classify_g3(record)
    assert verdict == "stop"
    assert any("revit.doc" in r for r in reasons)


def test_g3_code_path_other_than_document_only_is_stop():
    verdict, _ = pf.classify_g3(mutated(good_g3, "code_path", "revit.doc"))
    assert verdict == "stop"


# ------------------------------------------------------------------- G4


def test_g4_missing_case_is_stop():
    for case in ("saved", "unsaved", "workshared"):
        record = good_g4()
        del record["cases"][case]
        verdict, reasons = pf.classify_g4(record)
        assert verdict == "stop", case
        assert any(case in r for r in reasons)


def test_g4_untested_case_is_stop():
    record = good_g4()
    record["cases"]["unsaved"]["tested"] = False
    assert pf.classify_g4(record)[0] == "stop"


def test_g4_allowed_case_that_did_not_activate_the_target_is_stop():
    record = good_g4()
    record["cases"]["saved"]["active_after_is_target"] = False
    assert pf.classify_g4(record)[0] == "stop"


def test_g4_allowed_case_that_raised_a_dialog_is_stop():
    record = good_g4()
    record["cases"]["saved"]["dialog_observed"] = True
    assert pf.classify_g4(record)[0] == "stop"


def test_g4_failed_case_must_carry_an_explicit_refusal_policy():
    record = good_g4()
    record["cases"]["workshared"]["policy"] = "allow"
    verdict, reasons = pf.classify_g4(record)
    assert verdict == "stop"
    assert any("workshared" in r for r in reasons)


def test_g4_nothing_activatable_is_stop():
    record = good_g4()
    for case in ("saved", "unsaved"):
        record["cases"][case] = _case(outcome="error", policy="refuse", active_after=False)
    verdict, reasons = pf.classify_g4(record)
    assert verdict == "stop"
    assert any("no case" in r for r in reasons)


def test_g4_blank_api_or_missing_api_context_is_stop():
    assert pf.classify_g4(mutated(good_g4, "api", "  "))[0] == "stop"
    assert pf.classify_g4(mutated(good_g4, "external_event_context", False))[0] == "stop"


def test_g4_unknown_outcome_or_policy_is_stop():
    record = good_g4()
    record["cases"]["saved"]["outcome"] = "probably-fine"
    assert pf.classify_g4(record)[0] == "stop"
    record = good_g4()
    record["cases"]["saved"]["policy"] = "maybe"
    assert pf.classify_g4(record)[0] == "stop"


# ------------------------------------------------------------------- G5


def test_g5_single_listener_means_the_duplicate_condition_was_not_created():
    record = mutated(good_g5, "os_snapshot.pids", [111])
    record["independent_pid_capture"]["pids"] = [111]
    verdict, reasons = pf.classify_g5(record)
    assert verdict == "stop"
    assert any("two" in r for r in reasons)


def test_g5_independent_capture_disagreeing_with_the_snapshot_is_stop():
    verdict, reasons = pf.classify_g5(mutated(good_g5, "independent_pid_capture.pids", [111, 333]))
    assert verdict == "stop"
    assert any("independent" in r for r in reasons)


@pytest.mark.parametrize("count", [1, 3, None, "0", False, -1])
def test_g5_any_model_route_send_is_stop(count):
    verdict, _ = pf.classify_g5(mutated(good_g5, "model_route_send_count", count))
    assert verdict == "stop"


def test_g5_snapshot_taken_after_a_send_is_stop():
    verdict, _ = pf.classify_g5(mutated(good_g5, "os_snapshot.taken_before_any_send", False))
    assert verdict == "stop"


def test_g5_repeated_or_blank_pids_are_stop():
    assert pf.classify_g5(mutated(good_g5, "os_snapshot.pids", [111, 111]))[0] == "stop"
    assert pf.classify_g5(mutated(good_g5, "os_snapshot.pids", [111, 0]))[0] == "stop"
    assert pf.classify_g5(mutated(good_g5, "port", 0))[0] == "stop"
    assert pf.classify_g5(mutated(good_g5, "port", 70000))[0] == "stop"


# -------------------------------------------------------------- overall


def test_overall_is_eligible_only_when_all_five_gates_continue_and_never_approved():
    result = pf.classify_all(good_evidence())
    assert result["overall"] == "eligible-for-engineer-decision"
    assert sorted(result["gates"]) == ["G1", "G2", "G3", "G4", "G5"]
    assert result["approval"] == "not-granted"
    assert "approved" not in json.dumps(result).lower().replace("not-granted", "")


@pytest.mark.parametrize("gate", ["g1", "g2", "g3", "g4", "g5"])
def test_overall_one_missing_gate_is_stop(gate):
    evidence = good_evidence()
    del evidence[gate]
    result = pf.classify_all(evidence)
    assert result["overall"] == "stop"
    assert result["gates"][gate.upper()]["verdict"] == "stop"
    assert result["approval"] == "not-granted"


def test_overall_one_stopping_gate_stops_the_whole_preflight():
    evidence = good_evidence()
    evidence["g5"]["model_route_send_count"] = 2
    result = pf.classify_all(evidence)
    assert result["overall"] == "stop"
    assert result["gates"]["G5"]["verdict"] == "stop"
    assert result["gates"]["G1"]["verdict"] in ("wrapper-compatible", "explicit-route-only")


@pytest.mark.parametrize("junk", [None, [], "x", 3, {}])
def test_overall_junk_evidence_is_stop(junk):
    result = pf.classify_all(junk)
    assert result["overall"] == "stop"
    assert result["approval"] == "not-granted"


def test_overall_blank_template_is_stop():
    result = pf.classify_all(pf.evidence_template())
    assert result["overall"] == "stop"
    assert all(g["verdict"] == "stop" for g in result["gates"].values())


def test_template_names_every_field_a_passing_record_needs():
    template = pf.evidence_template()
    for gate, builder in (
        ("g1", good_g1),
        ("g2", good_g2),
        ("g3", good_g3),
        ("g4", good_g4),
        ("g5", good_g5),
    ):
        needed = _leaf_paths(builder())
        offered = _leaf_paths(template[gate])
        assert needed <= offered, "{}: template lacks {}".format(gate, sorted(needed - offered))


def test_template_values_are_all_unset_so_it_cannot_pass_by_accident():
    def values(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from values(v)
        elif isinstance(node, list):
            for v in node:
                yield from values(v)
        else:
            yield node

    assert all(v is None for v in values(pf.evidence_template()))


# ---------------------------------------------------- listener-row parsing


def test_parse_listener_rows_single_object_list_and_dedup():
    one = json.dumps({"LocalPort": 48884, "OwningProcess": 10})
    many = json.dumps(
        [
            {"LocalPort": 48884, "OwningProcess": 10},
            {"LocalPort": 48884, "OwningProcess": 20},
            {"LocalPort": 48884, "OwningProcess": 20},
            {"LocalPort": 5555, "OwningProcess": 30},
        ]
    )
    assert pf.parse_listener_rows(one, [48884]) == {48884: [10]}
    assert pf.parse_listener_rows(many, [48884, 48885]) == {48884: [10, 20], 48885: []}


@pytest.mark.parametrize("text", ["", "   ", "not json", "null", "42", '"x"'])
def test_parse_listener_rows_unreadable_output_is_none_never_an_empty_inventory(text):
    # An unreadable snapshot must not look like "no listeners": that would be a
    # silent pass for the duplicate-listener check.
    assert pf.parse_listener_rows(text, [48884]) is None


def test_parse_listener_rows_ignores_malformed_rows():
    text = json.dumps([{"LocalPort": "x"}, {"OwningProcess": 5}, {"LocalPort": 48884, "OwningProcess": 7}])
    assert pf.parse_listener_rows(text, [48884]) == {48884: [7]}


# ------------------------------------------------ snippets are IronPython-safe

SNIPPETS = {
    "g1": lambda: pf.G1_SNIPPET,
    "g2": lambda: pf.G2_SNIPPET,
    "g3": lambda: pf.G3_SNIPPET,
    "g4": lambda: pf.G4_SNIPPET,
}

# Anything that could write to a model or reach the unauthenticated route.
FORBIDDEN_IN_SNIPPETS = (
    "Transaction",
    ".Start(",
    ".Commit(",
    ".Delete(",
    ".Close(",
    "SaveAs",
    ".Save(",
    "execute_code",
    "importlib.reload",
    "Reload",
    "requests",
    "urllib",
    "socket",
    "WebClient",
    "pyrevit.routes",
)


@pytest.mark.parametrize("name", sorted(SNIPPETS))
def test_snippet_parses_without_fstrings_or_carriage_returns(name):
    source = SNIPPETS[name]()
    assert source.strip(), "snippet is empty"
    assert "\r" not in source
    source.encode("ascii")
    tree = ast.parse(source)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    # The Python-3-only modules scripts/conventions.py bans on the Revit side.
    assert not imported & {"pathlib", "dataclasses", "typing", "asyncio", "enum", "secrets",
                           "statistics", "concurrent"}


@pytest.mark.parametrize("name", sorted(SNIPPETS))
def test_snippet_is_read_only_and_prints_one_marked_json_line(name):
    source = SNIPPETS[name]()
    for token in FORBIDDEN_IN_SNIPPETS:
        assert token not in source, "{} contains {}".format(name, token)
    assert "PHASE2_{}_JSON=".format(name.upper()) in source


def test_g4_snippet_does_not_activate_anything_unless_the_engineer_confirms():
    source = pf.G4_SNIPPET
    assert "CONFIRM_ACTIVATION = False" in source
    tree = ast.parse(source)
    guarded = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "CONFIRM_ACTIVATION":
            guarded = any("OpenAndActivateDocument" in ast.dump(n) for n in node.body)
    assert guarded, "activation call must sit under `if CONFIRM_ACTIVATION:`"
    outside = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and "OpenAndActivateDocument" in ast.dump(n.func)
    ]
    assert len(outside) == 1


# ------------------------------------- the procedure can never send a request


def test_procedure_module_imports_no_network_or_mcp_client():
    with open(PROCEDURE_PATH, "rb") as handle:
        source = handle.read().decode("utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    banned = {"httpx", "urllib", "urllib3", "socket", "requests", "http", "aiohttp",
              "asyncio", "mcp", "bridge", "websockets", "ssl"}
    assert not imported & banned, sorted(imported & banned)


def test_procedure_module_has_encoding_cookie_and_no_collectible_tests():
    with open(PROCEDURE_PATH, "rb") as handle:
        first_line = handle.readline()
    assert b"coding: utf-8" in first_line
    # pytest never collects tests/ (testpaths = tests/unit), but a stray test_*
    # function would run if someone pointed pytest at the file.
    assert not [n for n in dir(pf) if n.startswith("test_")]


# ------------------------------------------------------------------ the CLI


def _write(tmp_path, evidence):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return str(path)


def test_cli_without_arguments_is_stop(capsys):
    assert pf.main([]) == 1
    assert "PHASE2_PREFLIGHT_STOP" in capsys.readouterr().out


def test_cli_classify_complete_evidence_is_eligible_but_not_approved(tmp_path, capsys):
    assert pf.main(["classify", _write(tmp_path, good_evidence())]) == 0
    out = capsys.readouterr().out
    assert "PHASE2_PREFLIGHT_ELIGIBLE" in out
    assert "approval=not-granted" in out
    assert "PHASE2_PREFLIGHT_STOP" not in out


def test_cli_classify_stopping_evidence_is_exit_1_with_reasons(tmp_path, capsys):
    evidence = good_evidence()
    evidence["g1"]["port"]["source"] = ""
    assert pf.main(["classify", _write(tmp_path, evidence)]) == 1
    out = capsys.readouterr().out
    assert "PHASE2_PREFLIGHT_STOP" in out
    assert "G1" in out and "port source" in out


def test_cli_classify_missing_or_unparseable_file_is_stop(tmp_path, capsys):
    assert pf.main(["classify", str(tmp_path / "nope.json")]) == 1
    assert "PHASE2_PREFLIGHT_STOP" in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert pf.main(["classify", str(bad)]) == 1
    assert "PHASE2_PREFLIGHT_STOP" in capsys.readouterr().out


def test_cli_template_prints_json_that_classifies_as_stop(capsys):
    assert pf.main(["template"]) == 0
    template = json.loads(capsys.readouterr().out)
    assert pf.classify_all(template)["overall"] == "stop"


@pytest.mark.parametrize("gate", ["g1", "g2", "g3", "g4"])
def test_cli_snippet_prints_the_snippet(gate, capsys):
    assert pf.main(["snippet", gate]) == 0
    assert capsys.readouterr().out.strip() == SNIPPETS[gate]().strip()


def test_cli_unknown_command_is_exit_2(capsys):
    assert pf.main(["frobnicate"]) == 2
