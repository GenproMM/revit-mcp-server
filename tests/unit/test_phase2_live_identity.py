# -*- coding: utf-8 -*-
"""Offline tests for the Phase 2 production identity recheck classifier (plan 02-02).

The operator procedure (tests/test_phase2_live_identity.py) needs a freshly
restarted Revit, pyRevit Routes and a full close/reopen between two runs. What can
be decided offline is tested here: that an absent, partial, synthetic or
contradictory record is STOP and never a pass, that no classifier verdict is an
approval, that the selector builder is the exact inverse of bridge.parse_target,
that listener inventory comes only from bridge.listener_snapshot, and that the
procedure can only ever name GET /status/.

A recheck-observed verdict here is NOT a live result: it only says a record is
complete and self-consistent. The engineer's decision at the plan's blocking
checkpoint is what records production identity as observed.

Needs no Revit, no pyRevit and no network.
"""

import ast
import asyncio
import contextlib
import copy
import functools
import importlib.util
import json
import os
import subprocess
import tempfile
import types

import pytest

import bridge

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROCEDURE_PATH = os.path.join(REPO_ROOT, "tests", "test_phase2_live_identity.py")

# Loaded under a different module name: this file is itself named
# test_phase2_live_identity, and pytest's basename import would collide.
_spec = importlib.util.spec_from_file_location("phase2_live_identity_procedure", PROCEDURE_PATH)
proc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proc)

T1 = "11111111-1111-4111-8111-111111111111"
T2 = "22222222-2222-4222-8222-222222222222"
PORT = 48884


def ident(pid, token, port=PORT, version="2025"):
    return {"pid": pid, "actual_port": port, "session_token": token, "revit_version": version}


def reply(kind, identity, at):
    # A copy per reply: a mutation of one reply must never leak into another.
    return {"at": at, "kind": kind, "identity": dict(identity), "text": "synthetic fixture text"}


def listener(port, owners):
    return {"port": port, "owners": owners, "source": "bridge.listener_snapshot",
            "at": "2026-10-17T10:00:05+00:00"}


def good_record():
    first = ident(1111, T1)
    second = ident(2222, T2)
    return {
        "schema": "phase2-identity-recheck-v1",
        "live": True,
        "synthetic": False,
        "recorded_at": "2026-10-17T10:40:00+00:00",
        "route_namespace": "genpro_revit_mcp",
        "sent_routes": [
            {"method": "GET", "route": "/status/", "via": "get_revit_status", "at": "2026-10-17T10:00:00+00:00"},
            {"method": "GET", "route": "/status/", "via": "get_revit_status", "at": "2026-10-17T10:00:02+00:00"},
        ],
        "incarnation_1": {
            "selector": "revit1:placeholder",
            "bootstrap": {"identity": dict(first), "at": "2026-10-17T10:00:00+00:00"},
            "replies": [
                reply("no-document", first, "2026-10-17T10:00:02+00:00"),
                reply("no-document", first, "2026-10-17T10:00:03+00:00"),
            ],
            "no_document_reply": reply("no-document", first, "2026-10-17T10:00:02+00:00"),
            "listener": listener(PORT, [1111]),
        },
        "incarnation_2": {
            "bootstrap": {"identity": dict(second), "at": "2026-10-17T10:30:00+00:00"},
            "replies": [
                reply("no-document", second, "2026-10-17T10:30:02+00:00"),
                reply("no-document", second, "2026-10-17T10:30:03+00:00"),
            ],
            "listener": listener(PORT, [2222]),
        },
        "old_selector_retry": {
            "selector_token": T1,
            "accepted": False,
            "text": "Error: Listener PID mismatch (owners [2222]); request not sent. Rediscover targets.",
            "at": "2026-10-17T10:30:04+00:00",
        },
        "not_run": proc.evidence_template()["not_run"],
    }


def codes(reasons):
    return [r.split(":", 1)[0] for r in reasons]


def verdict_codes(record):
    verdict, reasons = proc.classify_identity_recheck(record)
    return verdict, codes(reasons)


# ---------------------------------------------------------------- the good record


def test_good_record_is_recheck_observed_without_approval():
    verdict, reasons = proc.classify_identity_recheck(good_record())
    assert verdict == proc.OBSERVED == "recheck-observed"
    assert reasons == []
    assert proc.APPROVAL == "not-granted"


def test_classifier_only_ever_returns_stop_or_observed():
    mutated = [good_record()]
    for _label, mutate, _code in STOP_CASES:
        rec = good_record()
        mutate(rec)
        mutated.append(rec)
    for junk in (None, [], "x", 0, {}, {"live": True}):
        mutated.append(junk)
    for rec in mutated:
        verdict, _reasons = proc.classify_identity_recheck(rec)
        assert verdict in (proc.STOP, proc.OBSERVED)
        assert "approv" not in verdict and "pass" not in verdict


# ---------------------------------------------------------------- one case per STOP reason


def _drop(path):
    def mutate(rec):
        node = rec
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
    return mutate


def _set(path, value):
    def mutate(rec):
        node = rec
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return mutate


def _token_change_within_first(rec):
    rec["incarnation_1"]["replies"][1]["identity"]["session_token"] = T2


def _pid_change_within_first(rec):
    rec["incarnation_1"]["replies"][1]["identity"]["pid"] = 9999


def _equal_token_across_restart(rec):
    for item in rec["incarnation_2"]["replies"]:
        item["identity"]["session_token"] = T1
    rec["incarnation_2"]["bootstrap"]["identity"]["session_token"] = T1


def _equal_pid_across_restart(rec):
    for item in rec["incarnation_2"]["replies"]:
        item["identity"]["pid"] = 1111
    rec["incarnation_2"]["listener"]["owners"] = [1111]


def _no_document_without_identity(rec):
    rec["incarnation_1"]["no_document_reply"]["identity"] = None


def _first_pair_single(rec):
    rec["incarnation_1"]["replies"] = rec["incarnation_1"]["replies"][:1]


def _two_routes(rec):
    rec["sent_routes"].append({"method": "POST", "route": "/execute_code/", "via": "x", "at": "t"})


def _model_info_route(rec):
    rec["sent_routes"].append({"method": "GET", "route": "/model_info/", "via": "x", "at": "t"})


def _post_status_route(rec):
    rec["sent_routes"].append({"method": "POST", "route": "/status/", "via": "x", "at": "t"})


def _claim_not_run(rec):
    rec["not_run"]["g6"] = {"status": "pass"}


def _reversed_times(rec):
    rec["incarnation_2"]["replies"][0]["at"] = "2026-10-17T09:00:00+00:00"


def _bad_time(rec):
    rec["incarnation_1"]["replies"][0]["at"] = "not a time"


STOP_CASES = [
    ("live-not-true", _set(["live"], False), "not-live"),
    ("live-missing", _drop(["live"]), "not-live"),
    ("live-truthy-string", _set(["live"], "true"), "not-live"),
    ("synthetic-true", _set(["synthetic"], True), "synthetic"),
    ("synthetic-missing", _drop(["synthetic"]), "synthetic"),
    ("missing-restart-pair", _drop(["incarnation_2"]), "restart-pair-missing"),
    ("restart-replies-empty", _set(["incarnation_2", "replies"], []), "restart-pair-missing"),
    ("first-pair-single", _first_pair_single, "same-incarnation-pair-missing"),
    ("first-incarnation-missing", _drop(["incarnation_1"]), "same-incarnation-pair-missing"),
    ("token-change-within-incarnation", _token_change_within_first, "token-changed-within-incarnation"),
    ("pid-change-within-incarnation", _pid_change_within_first, "pid-changed-within-incarnation"),
    ("token-equal-across-restart", _equal_token_across_restart, "token-equal-across-restart"),
    ("pid-equal-across-restart", _equal_pid_across_restart, "pid-equal-across-restart"),
    ("no-document-reply-missing", _set(["incarnation_1", "no_document_reply"], None), "no-document-reply-missing"),
    ("no-document-reply-wrong-kind",
     _set(["incarnation_1", "no_document_reply", "kind"], "active"), "no-document-reply-missing"),
    ("no-document-identity-missing", _no_document_without_identity, "no-document-identity-missing"),
    ("no-document-other-incarnation-token",
     _set(["incarnation_1", "no_document_reply", "identity", "session_token"], T2),
     "token-changed-within-incarnation"),
    ("identity-field-missing", _drop(["incarnation_1", "replies", 0, "identity", "actual_port"]), "identity-incomplete"),
    ("identity-token-not-uuid", _set(["incarnation_1", "replies", 0, "identity", "session_token"], "abc"),
     "identity-incomplete"),
    ("identity-pid-bool", _set(["incarnation_1", "replies", 0, "identity", "pid"], True), "identity-incomplete"),
    ("identity-version-blank", _set(["incarnation_1", "replies", 0, "identity", "revit_version"], "  "),
     "identity-incomplete"),
    ("port-owner-absent", _set(["incarnation_1", "listener", "owners"], []), "port-owner-absent"),
    ("port-owner-different", _set(["incarnation_1", "listener", "owners"], [4242]), "port-owner-different"),
    ("port-owner-multiple", _set(["incarnation_1", "listener", "owners"], [1111, 4242]), "port-owner-multiple"),
    ("port-owner-multiple-restart", _set(["incarnation_2", "listener", "owners"], [2222, 4242]),
     "port-owner-multiple"),
    ("port-owner-different-restart", _set(["incarnation_2", "listener", "owners"], [1111]),
     "port-owner-different"),
    ("inventory-none", _set(["incarnation_1", "listener", "owners"], None), "inventory-unavailable"),
    ("inventory-section-none", _set(["incarnation_1", "listener"], None), "inventory-unavailable"),
    ("inventory-none-restart", _set(["incarnation_2", "listener", "owners"], None), "inventory-unavailable"),
    ("inventory-not-a-list", _set(["incarnation_1", "listener", "owners"], "1111"), "inventory-malformed"),
    ("inventory-bool-pid", _set(["incarnation_1", "listener", "owners"], [True]), "inventory-malformed"),
    ("inventory-duplicate-pid", _set(["incarnation_1", "listener", "owners"], [1111, 1111]),
     "inventory-malformed"),
    ("inventory-zero-pid", _set(["incarnation_1", "listener", "owners"], [0]), "inventory-malformed"),
    ("inventory-other-port", _set(["incarnation_1", "listener", "port"], 48885), "inventory-malformed"),
    ("old-selector-accepted", _set(["old_selector_retry", "accepted"], True), "old-selector-accepted"),
    ("old-selector-accepted-by-text",
     _set(["old_selector_retry", "text"],
          "=== REVIT STATUS ===\nVerified Revit process: PID 1111; Revit 2025; port 48884; session " + T1),
     "old-selector-accepted"),
    ("old-selector-accepted-not-bool", _set(["old_selector_retry", "accepted"], None), "old-selector-accepted"),
    ("old-selector-not-retried", _drop(["old_selector_retry"]), "old-selector-not-retried"),
    ("old-selector-wrong-token", _set(["old_selector_retry", "selector_token"], T2), "old-selector-not-retried"),
    ("old-selector-no-guidance", _set(["old_selector_retry", "text"], "Error: boom"),
     "old-selector-refusal-without-guidance"),
    ("route-post-execute-code", _two_routes, "non-status-route-sent"),
    ("route-model-info", _model_info_route, "non-status-route-sent"),
    ("route-post-status", _post_status_route, "non-status-route-sent"),
    ("routes-missing", _drop(["sent_routes"]), "sent-routes-unrecorded"),
    ("routes-empty", _set(["sent_routes"], []), "sent-routes-unrecorded"),
    ("not-run-slot-claimed", _claim_not_run, "not-run-slot-claimed"),
    ("timestamps-out-of-order", _reversed_times, "timestamps-invalid"),
    ("timestamp-unparseable", _bad_time, "timestamps-invalid"),
]


@pytest.mark.parametrize("label,mutate,code", STOP_CASES, ids=[c[0] for c in STOP_CASES])
def test_stop_reason_is_named(label, mutate, code):
    rec = good_record()
    mutate(rec)
    verdict, found = verdict_codes(rec)
    assert verdict == proc.STOP, label
    assert code in found, (label, found)


def test_every_declared_reason_code_has_a_stop_case():
    covered = set(code for _l, _m, code in STOP_CASES)
    declared = set(proc.REASON_CODES)
    # no-record and identity-port-changed are exercised by the dedicated tests below
    assert declared - covered <= {"no-record", "port-changed-within-incarnation", "classifier-error"}


def test_missing_record_is_stop_with_name():
    for junk in (None, {}, [], "text", 7):
        verdict, found = verdict_codes(junk)
        assert verdict == proc.STOP
        assert "no-record" in found


def test_port_change_within_incarnation_is_stop():
    rec = good_record()
    rec["incarnation_1"]["replies"][1]["identity"]["actual_port"] = 48885
    verdict, found = verdict_codes(rec)
    assert verdict == proc.STOP
    assert "port-changed-within-incarnation" in found


def test_stop_reasons_accumulate():
    rec = good_record()
    rec["live"] = False
    rec["synthetic"] = True
    verdict, found = verdict_codes(rec)
    assert verdict == proc.STOP
    assert "not-live" in found and "synthetic" in found


def test_second_replies_on_no_document_state_alone_do_not_need_active_kind():
    # An active-document reply is not required: the model-less start is the case under test.
    rec = good_record()
    assert all(r["kind"] == "no-document" for r in rec["incarnation_1"]["replies"])
    assert proc.classify_identity_recheck(rec)[0] == proc.OBSERVED


def test_active_replies_with_separate_no_document_reply_are_observed():
    rec = good_record()
    first = rec["incarnation_1"]["no_document_reply"]["identity"]
    rec["incarnation_1"]["replies"] = [
        reply("active", dict(first), "2026-10-17T10:00:10+00:00"),
        reply("active", dict(first), "2026-10-17T10:00:11+00:00"),
    ]
    assert proc.classify_identity_recheck(rec)[0] == proc.OBSERVED


# ---------------------------------------------------------------- never raises


def _walk_replace(value, junk):
    """Yield copies of `value` with each node replaced by `junk`, one at a time."""
    yield junk
    if isinstance(value, dict):
        for key in list(value):
            for variant in _walk_replace(value[key], junk):
                clone = copy.deepcopy(value)
                clone[key] = variant
                yield clone
    elif isinstance(value, list):
        for index in range(len(value)):
            for variant in _walk_replace(value[index], junk):
                clone = copy.deepcopy(value)
                clone[index] = variant
                yield clone


@pytest.mark.parametrize("junk", [None, 0, -1, True, "", "x", [], {}, [None], {"a": 1}, 1.5, b"bytes", object()])
def test_classifier_never_raises_on_malformed_records(junk):
    count = 0
    for variant in _walk_replace(good_record(), junk):
        verdict, reasons = proc.classify_identity_recheck(variant)
        assert verdict in (proc.STOP, proc.OBSERVED)
        assert isinstance(reasons, list)
        count += 1
    assert count > 20


def test_classifier_internal_error_reads_as_stop(monkeypatch):
    def boom(_value):
        raise RuntimeError("synthetic classifier bug")

    monkeypatch.setattr(proc, "_is_port", boom)
    verdict, found = verdict_codes(good_record())
    assert verdict == proc.STOP
    assert "classifier-error" in found


# ---------------------------------------------------------------- selector round trip


def test_make_selector_round_trips_through_parse_target():
    selector = proc.make_selector("127.0.0.1", PORT, 1111, T1)
    assert selector.startswith("revit1:")
    assert bridge.parse_target(selector) == {
        "host": "127.0.0.1", "port": PORT, "pid": 1111, "session_token": T1}


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_make_selector_round_trips_every_loopback_host(host):
    selector = proc.make_selector(host, 1, 2, T2)
    assert bridge.parse_target(selector)["host"] == host


def test_make_selector_has_no_padding_and_is_ascii():
    selector = proc.make_selector("127.0.0.1", 65535, 2147483647, T1)
    assert "=" not in selector
    assert selector.isascii()
    assert len(selector) <= 1024


def test_make_selector_never_hides_an_invalid_value_from_parse_target():
    # The builder is the exact inverse, not a validator: parse_target stays the gate.
    bad = proc.make_selector("example.com", PORT, 1111, T1)
    with pytest.raises(ValueError):
        bridge.parse_target(bad)
    with pytest.raises(ValueError):
        bridge.parse_target(proc.make_selector("127.0.0.1", 0, 1111, T1))


def test_verified_selector_helper_rejects_a_selector_parse_target_changes():
    assert proc.checked_selector("127.0.0.1", PORT, 1111, T1).startswith("revit1:")
    with pytest.raises(ValueError):
        proc.checked_selector("127.0.0.1", PORT, 0, T1)


def test_route_namespace_comes_from_bridge():
    expected = bridge.BASE_URL.rstrip("/").rsplit("/", 1)[1]
    assert expected
    assert proc.route_namespace() == expected
    source = open(PROCEDURE_PATH, "rb").read().decode("utf-8")
    assert "genpro_revit_mcp" not in source


# ---------------------------------------------------------------- reply parsing


ACTIVE_TEXT = (
    "=== REVIT STATUS ===\nStatus: active\nHealth: healthy\nAPI: genpro_revit_mcp\n"
    "Document: Model\nRevit Available: True\n\nRegistered Domains: 23\n"
    "Verified Revit process: PID 1111; Revit 2025; port 48884; session " + T1
)
NO_DOC_TEXT = (
    "=== ERROR DETAILS ===\nStatus: unhealthy\nError: No active Revit document\n"
    "\n=== ADDITIONAL RESPONSE DATA ===\napi_name: genpro_revit_mcp\n"
    "Verified Revit process: PID 1111; Revit 2025; port 48884; session " + T1
)


def test_parse_status_text_active():
    parsed = proc.parse_status_text(ACTIVE_TEXT)
    assert parsed["kind"] == "active"
    assert parsed["identity"] == ident(1111, T1)


def test_parse_status_text_no_document():
    parsed = proc.parse_status_text(NO_DOC_TEXT)
    assert parsed["kind"] == "no-document"
    assert parsed["identity"] == ident(1111, T1)


@pytest.mark.parametrize("text", [
    "", None, 5, "Error: Listener PID mismatch (owners [1]); request not sent. Rediscover targets.",
    "Verified Revit process: PID x; Revit 2025; port 48884; session " + T1,
    "Verified Revit process: PID 1111; Revit 2025; port 48884; session not-a-uuid",
])
def test_parse_status_text_without_verified_identity_has_none(text):
    parsed = proc.parse_status_text(text)
    assert parsed["identity"] is None
    assert parsed["kind"] == "error"


def test_parse_status_text_identity_without_active_or_no_document_is_error_kind():
    text = "=== ERROR DETAILS ===\nError: something else\nVerified Revit process: PID 1; Revit 2025; port 2; session " + T1
    parsed = proc.parse_status_text(text)
    assert parsed["kind"] == "error"
    assert parsed["identity"] == ident(1, T1, port=2)


def test_parse_bootstrap_identity_from_a_503_json_body():
    body = json.dumps({"status": "unhealthy", "error": "No active Revit document",
                       "process_identity": ident(1111, T1)})
    assert proc.parse_bootstrap_identity("Error: 503 - " + body) == ident(1111, T1)


def test_parse_bootstrap_identity_from_a_formatted_active_reply():
    text = "=== REVIT STATUS ===\nStatus: active\n\nProcess Identity: {}".format(repr(ident(1111, T1)))
    assert proc.parse_bootstrap_identity(text) == ident(1111, T1)


@pytest.mark.parametrize("text", [
    "", None, "Error: 503 - {}", "Process Identity: not a dict",
    "Process Identity: {'pid': 1}",
    "Process Identity: {'pid': True, 'actual_port': 1, 'session_token': '" + T1 + "', 'revit_version': '2025'}",
    "Process Identity: {'pid': 1, 'actual_port': 0, 'session_token': '" + T1 + "', 'revit_version': '2025'}",
])
def test_parse_bootstrap_identity_rejects_unusable_text(text):
    assert proc.parse_bootstrap_identity(text) is None


# ---------------------------------------------------------------- inventory only through bridge


def test_collect_listener_owners_uses_only_bridge_listener_snapshot(monkeypatch):
    calls = []

    def spy(ports, *args, **kwargs):
        calls.append((list(ports), args, kwargs))
        return {PORT: [1111, 2222]}

    def no_subprocess(*_a, **_k):
        raise AssertionError("the procedure must not run any subprocess of its own")

    monkeypatch.setattr(bridge, "listener_snapshot", spy)
    monkeypatch.setattr(subprocess, "run", no_subprocess)
    monkeypatch.setattr(subprocess, "Popen", no_subprocess)
    result = proc.collect_listener_owners(PORT)
    assert calls == [([PORT], (), {})]
    assert result["port"] == PORT
    assert result["owners"] == [1111, 2222]
    assert result["source"] == "bridge.listener_snapshot"
    assert "at" in result


@pytest.mark.parametrize("snapshot", [None, {}, {PORT: None}, "x", {PORT: "1"}])
def test_collect_listener_owners_unknown_inventory_is_never_empty_or_single(monkeypatch, snapshot):
    monkeypatch.setattr(bridge, "listener_snapshot", lambda ports, *a, **k: snapshot)
    result = proc.collect_listener_owners(PORT)
    assert result["owners"] is None


def test_collect_listener_owners_survives_a_raising_snapshot(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("netstat missing")

    monkeypatch.setattr(bridge, "listener_snapshot", boom)
    assert proc.collect_listener_owners(PORT)["owners"] is None


def test_procedure_source_has_no_subprocess_or_shell_of_its_own():
    tree = ast.parse(open(PROCEDURE_PATH, "rb").read().decode("utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "subprocess" not in imported
    assert "socket" not in imported
    assert "urllib" not in imported
    assert "httpx" not in imported
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
    assert not names & {"system", "Popen", "check_output", "popen"}
    # no PowerShell fallback
    assert "Get-NetTCPConnection" not in open(PROCEDURE_PATH, "rb").read().decode("utf-8").replace(
        "never Get-NetTCPConnection", "")


# ---------------------------------------------------------------- procedure shape


def test_procedure_defines_no_pytest_collectable_function():
    tree = ast.parse(open(PROCEDURE_PATH, "rb").read().decode("utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert not node.name.startswith("test"), node.name
        if isinstance(node, ast.ClassDef):
            assert not node.name.startswith("Test"), node.name


def test_procedure_has_encoding_cookie_and_no_work_at_import():
    first_line = open(PROCEDURE_PATH, "rb").read().decode("utf-8").splitlines()[0]
    assert first_line == "# -*- coding: utf-8 -*-"
    tree = ast.parse(open(PROCEDURE_PATH, "rb").read().decode("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            pytest.fail("module-level call: {}".format(ast.dump(node)[:80]))
    # the only module-level call-bearing statement allowed is the __main__ guard
    guards = [n for n in tree.body if isinstance(n, ast.If)]
    assert len(guards) == 1


def test_procedure_uses_the_absolute_main_py_path_idiom():
    assert os.path.isabs(proc.MAIN)
    assert os.path.basename(proc.MAIN) == "main.py"
    assert os.path.isfile(proc.MAIN)


def test_template_has_not_run_slots_that_never_pass():
    template = proc.evidence_template()
    for slot in ("g2_production", "g3", "g4", "g5_production_collision", "g6"):
        assert template["not_run"][slot]["status"] == "not-run"
    assert template["live"] is None and template["synthetic"] is None
    verdict, found = verdict_codes(template)
    assert verdict == proc.STOP
    assert "not-live" in found and "synthetic" in found


def test_template_slots_cannot_be_flipped_to_a_pass():
    rec = good_record()
    for slot in list(rec["not_run"]):
        for claim in ("pass", "observed", "ok", True, None, ""):
            clone = copy.deepcopy(rec)
            clone["not_run"][slot] = {"status": claim}
            verdict, found = verdict_codes(clone)
            assert verdict == proc.STOP, (slot, claim)
            assert "not-run-slot-claimed" in found


def test_template_missing_not_run_slot_is_stop():
    rec = good_record()
    del rec["not_run"]["g6"]
    assert verdict_codes(rec)[0] == proc.STOP


# ---------------------------------------------------------------- the CLI never invents a pass


def _write(tmp_path, record):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return str(path)


def test_classify_command_prints_sentinel_only_for_an_observed_record(tmp_path, capsys):
    code = proc.main(["classify", _write(tmp_path, good_record())])
    out = capsys.readouterr().out
    assert code == 0
    assert "PHASE2_IDENTITY_RECHECK_OBSERVED" in out
    assert "approval=not-granted" in out


@pytest.mark.parametrize("label,mutate,expected", [
    (c[0], c[1], c[2]) for c in STOP_CASES
], ids=[c[0] for c in STOP_CASES])
def test_classify_command_never_prints_sentinel_for_a_stop_record(tmp_path, capsys, label, mutate, expected):
    rec = good_record()
    mutate(rec)
    code = proc.main(["classify", _write(tmp_path, rec)])
    out = capsys.readouterr().out
    assert code == 1
    assert "PHASE2_IDENTITY_RECHECK_OBSERVED" not in out
    assert "PHASE2_IDENTITY_RECHECK_STOP" in out
    assert expected in out


def test_classify_command_unreadable_or_garbage_file_is_stop(tmp_path, capsys):
    assert proc.main(["classify", str(tmp_path / "missing.json")]) == 1
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe not json")
    assert proc.main(["classify", str(bad)]) == 1
    out = capsys.readouterr().out
    assert "PHASE2_IDENTITY_RECHECK_OBSERVED" not in out


def test_no_command_is_stop_without_sentinel(capsys):
    assert proc.main([]) == 1
    out = capsys.readouterr().out
    assert "PHASE2_IDENTITY_RECHECK_OBSERVED" not in out
    assert "PHASE2_IDENTITY_RECHECK_STOP" in out


def test_unknown_command_is_usage_error(capsys):
    assert proc.main(["nonsense"]) == 2
    assert "PHASE2_IDENTITY_RECHECK_OBSERVED" not in capsys.readouterr().out


def test_template_command_prints_json_and_no_sentinel(capsys):
    assert proc.main(["template"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["not_run"]["g6"]["status"] == "not-run"
    assert "PHASE2_IDENTITY_RECHECK_OBSERVED" not in out


def test_stage_output_inside_the_repository_is_refused_before_any_live_call(capsys):
    inside = os.path.join(REPO_ROOT, "raw-identity-capture.json")
    assert proc.main(["first", "--out", inside]) == 2
    assert not os.path.exists(inside)
    assert "PHASE2_IDENTITY_RECHECK_OBSERVED" not in capsys.readouterr().out


def test_restart_stage_without_a_first_capture_is_stop(tmp_path, capsys):
    missing = str(tmp_path / "never-written.json")
    assert proc.main(["restart", "--in", missing]) == 1
    assert "PHASE2_IDENTITY_RECHECK_OBSERVED" not in capsys.readouterr().out


def test_synthetic_marked_live_file_cannot_print_sentinel(tmp_path, capsys):
    rec = good_record()
    rec["synthetic"] = True
    assert proc.main(["classify", _write(tmp_path, rec)]) == 1
    assert "PHASE2_IDENTITY_RECHECK_OBSERVED" not in capsys.readouterr().out


def test_old_selector_refusal_helper_classifies_text():
    refused = proc.describe_old_selector_retry(
        T1, "Error: Listener PID mismatch (owners [2]); request not sent. Rediscover targets.")
    assert refused["accepted"] is False and refused["selector_token"] == T1
    accepted = proc.describe_old_selector_retry(T1, ACTIVE_TEXT)
    assert accepted["accepted"] is True
    unknown = proc.describe_old_selector_retry(T1, None)
    assert unknown["accepted"] is not False


# =============================================================================
# Plan 02-07: G3/G4 production observations (classify_g3_production,
# classify_g4_production and the g34-* operator commands).
#
# The live subcommands are exercised here against FakeBench: the REAL document
# tools (tools/document_tools.py) run against a text-level stand-in for the
# Revit routes, so the records the procedure writes are the records it would
# write live, and the parsers are pinned to the real renderers. None of this is
# a live result. A recheck-observed style verdict from a fake bench proves only
# that the classifier accepts a complete, self-consistent record; it never
# approves anything, and the engineer's choice at the blocking checkpoint does.

SEL_A = "doc1.aaaaaaaaaaaa.1"
SEL_B = "doc1.aaaaaaaaaaaa.2"
SEL_U = "doc1.aaaaaaaaaaaa.3"  # never saved
SEL_D = "doc1.aaaaaaaaaaaa.4"  # detached copy
SEL_W = "doc1.aaaaaaaaaaaa.5"  # saved, workshared
SEL_ZZ = "doc1.zzzzzzzzzzzz.9"  # not open

G34_IDENT = ident(4242, T1)
IDX = {SEL_A: "1", SEL_B: "2", SEL_U: "3", SEL_D: "4", SEL_W: "5"}  # 1-based listing position


class _ToolRegistry(object):
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


class FakeBench(object):
    """The Revit routes as plain data, behind the REAL document tools.

    Faults the tests switch on: read_moves_ui_to (an addressed read changes the
    active document), read_answers_from (a read answers with another document's
    data), refusals_activate (a refused class gets activated anyway).
    """

    def __init__(self, same_presentation=False):
        self.docs = [
            {"document": SEL_A, "title": "Alpha", "path": "C:/bench/Alpha.rvt"},
            {"document": SEL_B, "title": "Beta", "path": "C:/bench/Beta.rvt"},
            {"document": SEL_U, "title": "Project1", "path": ""},
            {"document": SEL_D, "title": "Gamma (detached)", "path": ""},
            {"document": SEL_W, "title": "Delta: central", "path": "C:/bench/Delta.rvt"},
        ]
        if same_presentation:
            self.docs[1]["title"] = self.docs[0]["title"]
            self.docs[1]["path"] = self.docs[0]["path"]
        self.refusals = {SEL_U: "unsaved", SEL_D: "detached", SEL_W: "workshared-unmeasured"}
        self.counts = {SEL_A: 1200, SEL_B: 800, SEL_U: 10, SEL_D: 20, SEL_W: 3000}
        self.levels = {
            SEL_A: [("Level 0", 0.0), ("Level 1: podium", 3000.0), ("Level 2", 6000.0)],
            SEL_B: [("B0", -500.0), ("B1", 2500.0)],
            SEL_U: [("Level 1", 0.0)],
            SEL_D: [("Level 1", 0.0), ("Level 2", 3000.0)],
            SEL_W: [("Level 1", 0.0)],
        }
        self.active = SEL_A
        self.tool_calls = []
        self.routes = []
        self.read_moves_ui_to = None
        self.read_answers_from = {}
        self.refusals_activate = False
        from tools.document_tools import register_document_tools

        self.mcp = _ToolRegistry()
        register_document_tools(self.mcp, self.revit_get, self.revit_post)

    # -- Routes ---------------------------------------------------------------

    def find(self, selector):
        for entry in self.docs:
            if entry["document"] == selector:
                return entry
        return None

    def descriptor(self, selector):
        entry = self.find(selector)
        return {"document": selector, "title": entry["title"], "path": entry["path"],
                "active": selector == self.active, "saved": bool(entry["path"])}

    async def revit_get(self, path, ctx=None, **options):
        return self.route("GET", path, None, options)

    async def revit_post(self, path, data, ctx=None, **options):
        return self.route("POST", path, data, options)

    def route(self, method, path, data, options):
        self.routes.append((method, path, dict(data or {}), dict(options)))
        identity = dict(G34_IDENT)
        if (method, path) == ("GET", "/documents/"):
            documents = [self.descriptor(entry["document"]) for entry in self.docs]
            return {"status": "success", "process_identity": identity, "documents": documents,
                    "count": len(documents), "active_document": self.active}
        selector = (data or {}).get("document")
        if self.find(selector) is None:
            return "Error: 404 - " + json.dumps({
                "error": "unknown document", "error_code": "document-unknown",
                "process_identity": identity})
        if (method, path) == ("POST", "/activate_document/"):
            return self.activate(selector, identity)
        if (method, path) in (("POST", "/document_summary/"), ("POST", "/document_levels/")):
            return self.read(path, selector, identity)
        raise AssertionError("unexpected route {} {}".format(method, path))

    def read(self, path, selector, identity):
        source = self.read_answers_from.get(selector, selector)
        entry = self.find(source)
        before = self.active
        descriptor = self.descriptor(selector)
        if self.read_moves_ui_to:
            self.active = self.read_moves_ui_to
        payload = {"status": "success", "document": descriptor, "target_is_active": selector == before,
                   "ui_switched": before != self.active, "active_before": before,
                   "active_after": self.active, "process_identity": identity}
        if path == "/document_summary/":
            payload["summary"] = {
                "title": entry["title"], "path": entry["path"],
                "non_type_element_count": self.counts[source],
                "level_count": len(self.levels[source]),
                "project_information": {"name": entry["title"], "number": "P-1"},
                "unreadable_fields": []}
        else:
            payload["levels"] = [
                {"name": name, "elevation_mm": mm, "elevation_feet": round(mm / 304.8, 4), "id": 1000 + i}
                for i, (name, mm) in enumerate(self.levels[source])]
            payload["total_levels"] = len(self.levels[source])
            payload["skipped_levels"] = 0
        return payload

    def activate(self, selector, identity):
        if selector == self.active:
            descriptor = self.descriptor(selector)
            return {"status": "success", "activation": "already-active", "document": descriptor,
                    "observed_active_document": descriptor, "process_identity": identity}
        reason = self.refusals.get(selector)
        if reason and not self.refusals_activate:
            return "Error: 422 - " + json.dumps({
                "error": "Activation refused ({}).".format(reason), "error_code": reason,
                "reason": reason, "document": self.descriptor(selector),
                "observed_active_document": self.descriptor(self.active),
                "process_identity": identity})
        self.active = selector
        descriptor = self.descriptor(selector)
        return {"status": "success", "activation": "activated", "document": descriptor,
                "observed_active_document": descriptor, "process_identity": identity}

    # -- The MCP surface the procedure drives ---------------------------------------

    def status_text(self, arguments):
        return "=== REVIT STATUS ===\nStatus: active\n\nProcess Identity: {}".format(repr(G34_IDENT))

    def called(self, name):
        return [args for tool, args in self.tool_calls if tool == name]


class FakeSession(object):
    def __init__(self, bench):
        self.bench = bench

    async def call_tool(self, name, arguments):
        self.bench.tool_calls.append((name, dict(arguments)))
        if name == "get_revit_status":
            text = self.bench.status_text(arguments)
        else:
            text = await self.bench.mcp.tools[name](**arguments)
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=text)])


def install_bench(monkeypatch, bench):
    @contextlib.asynccontextmanager
    async def fake_server(port):
        yield FakeSession(bench)

    monkeypatch.setattr(proc, "_server", fake_server)
    monkeypatch.setattr(
        proc, "collect_listener_owners",
        lambda port: {"port": port, "owners": [G34_IDENT["pid"]], "source": "bridge.listener_snapshot",
                      "at": "2026-10-22T10:00:05+00:00"})


def cmd(*argv):
    return proc.main([str(a) for a in argv])


def observe(raw, step, ui, dialog=None, data=None):
    argv = ["g34-observe", "--in", raw, "--step", step, "--ui", ui]
    if dialog is not None:
        argv += ["--dialog", dialog]
    if data is not None:
        argv += ["--data", data]
    return cmd(*argv)


def load(raw):
    with open(raw, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def capture_flow(tmp_path, bench, cases=("allow", "unsaved", "detached_or_non_file", "saved_workshared"),
                 observe_engineer=True):
    """The whole engineer procedure through the CLI; returns the raw file path."""
    raw = str(tmp_path / "g34-production.json")
    assert cmd("g34-start", "--out", raw) == 0
    # A is active; B is read while inactive; the engineer then makes B active by hand.
    assert bench.active == SEL_A
    assert cmd("g3-read", "--in", raw, "--slot", "a_active_b_read", "--target", IDX[SEL_B]) == 0
    if observe_engineer:
        assert observe(raw, "g3:a_active_b_read", "unchanged", data="matches") == 0
    bench.active = SEL_B  # the engineer clicks the other window; no tool does this
    assert cmd("g3-read", "--in", raw, "--slot", "b_active_a_read", "--target", IDX[SEL_A]) == 0
    if observe_engineer:
        assert observe(raw, "g3:b_active_a_read", "unchanged", data="matches") == 0
    plan = {"allow": SEL_A, "unsaved": SEL_U, "detached_or_non_file": SEL_D, "saved_workshared": SEL_W}
    expected_ui = {"allow": "target-active"}
    for case in cases:
        assert cmd("g4-case", "--in", raw, "--case", case, "--target", IDX[plan[case]]) == 0
        if observe_engineer:
            assert observe(raw, "g4:" + case, expected_ui.get(case, "unchanged"), dialog="none") == 0
    return raw


class _Path(object):
    """Just enough of pathlib.Path for capture_flow: folder / name."""

    def __init__(self, folder):
        self.folder = folder

    def __truediv__(self, name):
        return os.path.join(self.folder, name)


@functools.lru_cache(maxsize=1)
def _good_g34_json():
    with pytest.MonkeyPatch.context() as mp:
        bench = FakeBench()
        install_bench(mp, bench)
        with tempfile.TemporaryDirectory() as folder:
            raw = capture_flow(_Path(folder), bench)
            with open(raw, "rb") as handle:
                return handle.read().decode("utf-8")


def good_g34_record():
    return json.loads(_good_g34_json())


# ---------------------------------------------------------------- parsers vs the real renderers


def render(bench, tool, **kwargs):
    return asyncio.run(bench.mcp.tools[tool](**kwargs))


def render_payload(tool, payload, **kwargs):
    """Render an arbitrary route reply through the real tool."""
    from tools.document_tools import register_document_tools

    async def answer(*_args, **_kwargs):
        return payload

    registry = _ToolRegistry()
    register_document_tools(registry, answer, answer)
    return asyncio.run(registry.tools[tool](**kwargs))


def test_parse_listing_text_reads_every_document_and_the_active_one():
    parsed = proc.parse_listing_text(render(FakeBench(), "list_documents"))
    assert parsed["ok"] is True
    assert [d["document"] for d in parsed["documents"]] == [SEL_A, SEL_B, SEL_U, SEL_D, SEL_W]
    assert [d["title"] for d in parsed["documents"]] == [
        "Alpha", "Beta", "Project1", "Gamma (detached)", "Delta: central"]
    assert [d["path"] for d in parsed["documents"]] == [
        "C:/bench/Alpha.rvt", "C:/bench/Beta.rvt", "", "", "C:/bench/Delta.rvt"]
    assert [d["active"] for d in parsed["documents"]] == [True, False, False, False, False]
    assert parsed["active_document"] == SEL_A and parsed["active_count"] == 1
    assert parsed["identity"] == G34_IDENT


def test_parse_listing_text_keeps_non_ascii_titles():
    bench = FakeBench()
    bench.docs[0]["title"] = "Проект Альфа"
    parsed = proc.parse_listing_text(render(bench, "list_documents"))
    assert parsed["documents"][0]["title"] == "Проект Альфа"


def test_parse_listing_text_empty_listing_is_data_with_no_active_document():
    bench = FakeBench()
    bench.docs = []
    parsed = proc.parse_listing_text(render(bench, "list_documents"))
    assert parsed["ok"] is True and parsed["documents"] == []
    assert parsed["active_document"] is None and parsed["active_count"] == 0


def test_parse_listing_text_two_active_documents_is_not_one_active_document():
    text = render(FakeBench(), "list_documents").replace("Beta", "Beta  [ACTIVE]")
    parsed = proc.parse_listing_text(text)
    assert parsed["active_count"] == 2 and parsed["active_document"] is None


@pytest.mark.parametrize("text", [
    None, 5, "", "Error: request not sent: queue busy",
    "=== ERROR DETAILS ===\nStatus: unknown\nError: boom",
    "Open documents in this Revit process: 1\n1. Alpha\n   path: C:/a.rvt",  # no document line
])
def test_parse_listing_text_unusable_text_is_not_ok(text):
    assert proc.parse_listing_text(text)["ok"] is False


def test_parse_summary_text_unchanged_read():
    parsed = proc.parse_summary_text(render(FakeBench(), "read_document_summary", document=SEL_B))
    assert parsed["kind"] == "ok"
    assert parsed["document"] == SEL_B and parsed["title"] == "Beta" and parsed["path"] == "C:/bench/Beta.rvt"
    assert parsed["non_type_element_count"] == 800 and parsed["level_count"] == 2
    assert parsed["target_is_active"] is False and parsed["ui_switched"] is False
    assert parsed["active_token"] == SEL_A
    assert parsed["identity"] == G34_IDENT


def test_parse_summary_text_never_saved_document_has_an_empty_path():
    parsed = proc.parse_summary_text(render(FakeBench(), "read_document_summary", document=SEL_U))
    assert parsed["kind"] == "ok" and parsed["path"] == ""


def test_parse_summary_text_switched_read_is_ui_switched_true():
    bench = FakeBench()
    bench.read_moves_ui_to = SEL_B
    parsed = proc.parse_summary_text(render(bench, "read_document_summary", document=SEL_B))
    assert parsed["ui_switched"] is True
    assert parsed["active_before"] == SEL_A and parsed["active_after"] == SEL_B
    assert parsed["active_token"] is None


def test_parse_summary_text_unknown_diagnostic_is_ui_switched_none():
    bench = FakeBench()
    payload = bench.route("POST", "/document_summary/", {"document": SEL_B}, {})
    payload["ui_switched"] = None
    payload["active_after_error"] = "registry unreadable"
    parsed = proc.parse_summary_text(render_payload("read_document_summary", payload, document=SEL_B))
    assert parsed["kind"] == "ok" and parsed["ui_switched"] is None


def test_parse_summary_text_without_the_diagnostic_line_has_no_ui_verdict():
    text = render(FakeBench(), "read_document_summary", document=SEL_B)
    stripped = "\n".join(line for line in text.splitlines() if "Active document before and after" not in line)
    assert proc.parse_summary_text(stripped)["ui_switched"] is None


def test_parse_summary_text_refused_selector_is_a_named_refusal():
    text = render(FakeBench(), "read_document_summary", document=SEL_ZZ)
    parsed = proc.parse_summary_text(text)
    assert parsed["kind"] == "refused" and parsed["http_status"] == 404
    assert parsed["error_code"] == "document-unknown"
    assert parsed["identity"] == G34_IDENT


@pytest.mark.parametrize("text", [None, 5, "", "Error: request not sent: queue busy", "Error: 500 - not json"])
def test_parse_read_text_unusable_text_is_not_ok(text):
    assert proc.parse_summary_text(text)["kind"] in ("error", "refused")
    assert proc.parse_levels_text(text)["kind"] in ("error", "refused")
    assert proc.parse_summary_text(text)["kind"] != "ok"


def test_parse_levels_text_reads_every_level_with_colons_in_names():
    parsed = proc.parse_levels_text(render(FakeBench(), "read_document_levels", document=SEL_A))
    assert parsed["kind"] == "ok" and parsed["document"] == SEL_A and parsed["title"] == "Alpha"
    assert parsed["total_levels"] == 3 and parsed["skipped_levels"] == 0
    assert [lv["name"] for lv in parsed["levels"]] == ["Level 0", "Level 1: podium", "Level 2"]
    assert [lv["elevation_mm"] for lv in parsed["levels"]] == [0.0, 3000.0, 6000.0]
    assert [lv["id"] for lv in parsed["levels"]] == [1000, 1001, 1002]
    assert parsed["target_is_active"] is True and parsed["ui_switched"] is False
    assert parsed["identity"] == G34_IDENT


def test_parse_levels_text_counts_skipped_levels_and_reads_an_empty_list():
    bench = FakeBench()
    payload = bench.route("POST", "/document_levels/", {"document": SEL_B}, {})
    payload["skipped_levels"] = 2
    parsed = proc.parse_levels_text(render_payload("read_document_levels", payload, document=SEL_B))
    assert parsed["skipped_levels"] == 2
    payload["levels"], payload["total_levels"], payload["skipped_levels"] = [], 0, 0
    parsed = proc.parse_levels_text(render_payload("read_document_levels", payload, document=SEL_B))
    assert parsed["kind"] == "ok" and parsed["levels"] == [] and parsed["total_levels"] == 0


def test_parse_activation_text_activated_and_already_active():
    bench = FakeBench()
    bench.active = SEL_B
    activated = proc.parse_activation_text(render(bench, "activate_document", document=SEL_A))
    assert activated["kind"] == "success" and activated["http_status"] == 200
    assert activated["activation"] == "activated"
    assert activated["document"] == SEL_A and activated["observed_active_document"] == SEL_A
    assert activated["identity"] == G34_IDENT
    again = proc.parse_activation_text(render(bench, "activate_document", document=SEL_A))
    assert again["kind"] == "success" and again["activation"] == "already-active"


def test_parse_activation_text_refusal_carries_status_reason_and_observed_active():
    parsed = proc.parse_activation_text(render(FakeBench(), "activate_document", document=SEL_U))
    assert parsed["kind"] == "refused" and parsed["http_status"] == 422
    assert parsed["reason"] == "unsaved" and parsed["error_code"] == "unsaved"
    assert parsed["document"] == SEL_U and parsed["observed_active_document"] == SEL_A
    assert parsed["activation"] is None
    assert parsed["identity"] == G34_IDENT


@pytest.mark.parametrize("text,kind", [
    (None, "error"), (5, "error"), ("", "error"),
    ("Error: request not sent: queue busy", "error"),
    ("Error: 500 - not json", "error"),
    ("Error: 500 - " + json.dumps({"error": "x", "reason": "activation-failed"}), "error"),
    ("Error: 409 - " + json.dumps({"error": "x", "reason": "document-not-activated"}), "refused"),
])
def test_parse_activation_text_other_outcomes(text, kind):
    parsed = proc.parse_activation_text(text)
    assert parsed["kind"] == kind
    assert parsed["activation"] is None


def test_parsers_never_raise_on_junk():
    for junk in (None, 0, b"x", [], {}, object(), "\x00", "Error: ", "Error: 999999 - {", "- " * 50):
        for parse in (proc.parse_listing_text, proc.parse_summary_text, proc.parse_levels_text,
                      proc.parse_activation_text):
            assert isinstance(parse(junk), dict)


def test_sent_call_entry_names_only_the_five_allowed_routes():
    expected = {
        "get_revit_status": ("GET", "/status/"),
        "list_documents": ("GET", "/documents/"),
        "read_document_summary": ("POST", "/document_summary/"),
        "read_document_levels": ("POST", "/document_levels/"),
        "activate_document": ("POST", "/activate_document/"),
    }
    for tool, (method, route) in expected.items():
        entry = proc.sent_call_entry(tool, "g3:a_active_b_read")
        assert (entry["method"], entry["route"], entry["tool"]) == (method, route, tool)
        assert entry["step"] == "g3:a_active_b_read" and entry["at"]
    for tool in ("execute_code", "save_document", "open_model", "get_revit_model_info", "", None):
        with pytest.raises(ValueError):
            proc.sent_call_entry(tool, "x")


# ---------------------------------------------------------------- the good record


S1 = ["g3", "slots", "a_active_b_read"]
S2 = ["g3", "slots", "b_active_a_read"]
CA = ["g4", "cases", "allow"]
CU = ["g4", "cases", "unsaved"]
CD = ["g4", "cases", "detached_or_non_file"]
CW = ["g4", "cases", "saved_workshared"]


def g3_verdict(record):
    verdict, reasons = proc.classify_g3_production(record)
    return verdict, codes(reasons)


def g4_verdict(record):
    verdict, reasons = proc.classify_g4_production(record)
    return verdict, codes(reasons)


def test_good_g3_record_is_observed_without_approval():
    verdict, reasons = proc.classify_g3_production(good_g34_record())
    assert verdict == proc.G3_OBSERVED, reasons
    assert reasons == []
    assert proc.APPROVAL == "not-granted"


def test_good_g4_record_is_observed_without_approval():
    verdict, reasons = proc.classify_g4_production(good_g34_record())
    assert verdict == proc.G4_OBSERVED, reasons
    assert reasons == []


def test_the_good_record_came_from_one_process_one_route_namespace_and_no_forbidden_route():
    record = good_g34_record()
    assert record["schema"] == proc.G34_SCHEMA
    assert record["live"] is True and record["synthetic"] is False
    assert record["process"]["identity"] == G34_IDENT
    allowed = {("GET", "/status/"), ("GET", "/documents/"), ("POST", "/document_summary/"),
               ("POST", "/document_levels/"), ("POST", "/activate_document/")}
    assert record["sent_calls"]
    assert {(c["method"], c["route"]) for c in record["sent_calls"]} <= allowed


def test_good_record_engineer_observations_are_exactly_what_the_commands_wrote():
    record = good_g34_record()
    assert record["g3"]["slots"]["a_active_b_read"]["engineer"]["ui"] == "unchanged"
    assert record["g3"]["slots"]["a_active_b_read"]["engineer"]["data_matches_addressed"] is True
    assert record["g4"]["cases"]["allow"]["engineer"]["ui"] == "target-active"
    for name in ("allow", "unsaved", "detached_or_non_file", "saved_workshared"):
        engineer = record["g4"]["cases"][name]["engineer"]
        assert engineer["dialog_required_input"] is False
        assert engineer["source"] == "engineer-command-line"


def test_template_classifies_as_stop_for_both_gates_and_carries_not_run_slots():
    template = proc.g34_template()
    verdict, found = g3_verdict(template)
    assert verdict == proc.STOP and "not-live" in found and "synthetic" in found
    assert "direction-missing" in found
    verdict, found = g4_verdict(template)
    assert verdict == proc.STOP and "not-live" in found
    assert template["not_run"]["g6"]["status"] == "not-run"
    for case in ("allow", "unsaved", "detached_or_non_file", "saved_workshared"):
        assert template["g4"]["cases"][case]["status"] == "not-run"
    assert template["live"] is None and template["synthetic"] is None


def _append_call(method, route, tool="x", step="g3:a_active_b_read"):
    def mutate(rec):
        rec["sent_calls"].append({"method": method, "route": route, "tool": tool, "step": step,
                                  "at": "2026-10-22T10:00:00+00:00"})
    return mutate


def _remove_calls(tool, step):
    def mutate(rec):
        rec["sent_calls"] = [c for c in rec["sent_calls"] if not (c["tool"] == tool and c["step"] == step)]
    return mutate


def _same_direction(rec):
    rec["g3"]["slots"]["b_active_a_read"] = copy.deepcopy(rec["g3"]["slots"]["a_active_b_read"])


# Header mutations: both gates stop on every one of them.
COMMON_STOP_CASES = [
    ("live-not-true", _set(["live"], False), "not-live"),
    ("live-missing", _drop(["live"]), "not-live"),
    ("live-truthy-string", _set(["live"], "true"), "not-live"),
    ("synthetic-true", _set(["synthetic"], True), "synthetic"),
    ("synthetic-missing", _drop(["synthetic"]), "synthetic"),
    ("schema-other", _set(["schema"], "phase2-identity-recheck-v1"), "schema-mismatch"),
    ("process-identity-field-missing", _drop(["process", "identity", "pid"]), "process-identity-incomplete"),
    ("process-identity-token-not-uuid", _set(["process", "identity", "session_token"], "abc"),
     "process-identity-incomplete"),
    ("process-identity-missing", _drop(["process"]), "process-identity-incomplete"),
    ("owner-different", _set(["process", "listener", "owners"], [1]), "process-owner-unverified"),
    ("owner-multiple", _set(["process", "listener", "owners"], [4242, 1]), "process-owner-unverified"),
    ("owner-unknown", _set(["process", "listener", "owners"], None), "process-owner-unverified"),
    ("owner-section-missing", _drop(["process", "listener"]), "process-owner-unverified"),
    ("route-execute-code", _append_call("POST", "/execute_code/"), "route-not-allowed"),
    ("route-save-document", _append_call("POST", "/save_document/"), "route-not-allowed"),
    ("route-open-model", _append_call("POST", "/open_model/"), "route-not-allowed"),
    ("route-model-info", _append_call("GET", "/model_info/"), "route-not-allowed"),
    ("route-get-activate", _append_call("GET", "/activate_document/"), "route-not-allowed"),
    ("route-post-documents", _append_call("POST", "/documents/"), "route-not-allowed"),
    ("route-entry-not-a-dict", lambda rec: rec["sent_calls"].append("GET /status/"), "route-not-allowed"),
    ("calls-missing", _drop(["sent_calls"]), "sent-calls-unrecorded"),
    ("calls-empty", _set(["sent_calls"], []), "sent-calls-unrecorded"),
    ("g6-claimed", _set(["not_run", "g6"], {"status": "pass"}), "not-run-slot-claimed"),
    ("g6-slot-missing", _drop(["not_run", "g6"]), "not-run-slot-claimed"),
    ("not-run-section-missing", _drop(["not_run"]), "not-run-slot-claimed"),
    ("another-slot-claimed", _set(["not_run", "save"], {"status": "done"}), "not-run-slot-claimed"),
]


def _engineer(path, key, value):
    return _set(path + ["engineer", key], value)


G3_STOP_CASES = [
    # directions
    ("direction-a-null", _set(S1, None), "direction-missing"),
    ("direction-b-missing", _drop(S2), "direction-missing"),
    ("both-directions-missing", _drop(["g3"]), "direction-missing"),
    ("slots-empty", _set(["g3", "slots"], {}), "direction-missing"),
    ("same-direction-twice", _same_direction, "direction-not-reversed"),
    ("second-target-is-a-third-document", _set(S2 + ["target_document"], SEL_U), "direction-not-reversed"),
    ("unknown-slot", _set(["g3", "slots", "c_extra"], {"step": "g3:c_extra"}), "unknown-slot"),
    ("slot-not-a-dict", _set(S1, "done"), "direction-missing"),
    # listings
    ("before-listing-missing", _drop(S1 + ["before_listing"]), "listing-unusable"),
    ("before-listing-not-ok", _set(S1 + ["before_listing", "ok"], False), "listing-unusable"),
    ("after-listing-missing", _drop(S1 + ["after_listing"]), "listing-unusable"),
    ("after-listing-no-active", _set(S1 + ["after_listing", "active_count"], 0), "listing-unusable"),
    ("after-listing-two-active", _set(S1 + ["after_listing", "active_count"], 2), "listing-unusable"),
    ("before-listing-two-active", _set(S2 + ["before_listing", "active_count"], 2), "listing-unusable"),
    ("before-listing-documents-not-a-list", _set(S1 + ["before_listing", "documents"], "x"), "listing-unusable"),
    # the active document must be the same by selector before and after
    ("active-changed-between-listings", _set(S1 + ["after_listing", "active_document"], SEL_B),
     "active-document-changed"),
    ("summary-reports-another-active-token", _set(S1 + ["summary", "active_token"], SEL_B),
     "active-document-changed"),
    ("levels-reports-another-active-token", _set(S2 + ["levels", "active_token"], SEL_A),
     "active-document-changed"),
    ("summary-ui-switched", _set(S1 + ["summary", "ui_switched"], True), "ui-switched"),
    ("levels-ui-switched", _set(S2 + ["levels", "ui_switched"], True), "ui-switched"),
    ("summary-ui-unknown", _set(S1 + ["summary", "ui_switched"], None), "ui-switch-unknown"),
    ("levels-ui-unknown", _drop(S2 + ["levels", "ui_switched"]), "ui-switch-unknown"),
    ("summary-ui-not-a-bool", _set(S1 + ["summary", "ui_switched"], "no"), "ui-switch-unknown"),
    # the target must be inactive and listed
    ("target-is-the-active-document", _set(S1 + ["target_document"], SEL_A), "target-is-active"),
    ("summary-says-target-active", _set(S1 + ["summary", "target_is_active"], True), "target-is-active"),
    ("levels-says-target-active", _set(S2 + ["levels", "target_is_active"], True), "target-is-active"),
    ("summary-target-active-unknown", _set(S1 + ["summary", "target_is_active"], None), "target-is-active"),
    ("target-not-listed", _set(S1 + ["target_document"], SEL_ZZ), "target-not-listed"),
    ("target-missing", _drop(S1 + ["target_document"]), "target-not-listed"),
    # the reads themselves
    ("summary-refused", _set(S1 + ["summary", "kind"], "refused"), "read-not-ok"),
    ("levels-error", _set(S2 + ["levels", "kind"], "error"), "read-not-ok"),
    ("summary-missing", _drop(S1 + ["summary"]), "read-not-ok"),
    ("levels-missing", _drop(S2 + ["levels"]), "read-not-ok"),
    ("summary-names-the-other-document", _set(S1 + ["summary", "document"], SEL_A), "wrong-document"),
    ("levels-name-the-other-document", _set(S2 + ["levels", "document"], SEL_B), "wrong-document"),
    ("summary-title-is-the-other-documents", _set(S1 + ["summary", "title"], "Alpha"), "data-not-from-target"),
    ("summary-path-is-the-other-documents", _set(S1 + ["summary", "path"], "C:/bench/Alpha.rvt"),
     "data-not-from-target"),
    ("levels-title-is-the-other-documents", _set(S2 + ["levels", "title"], "Beta"), "data-not-from-target"),
    ("summary-count-missing", _set(S1 + ["summary", "non_type_element_count"], None), "summary-incomplete"),
    ("summary-count-bool", _set(S1 + ["summary", "non_type_element_count"], True), "summary-incomplete"),
    ("summary-count-negative", _set(S1 + ["summary", "non_type_element_count"], -1), "summary-incomplete"),
    ("summary-level-count-string", _set(S2 + ["summary", "level_count"], "3"), "summary-incomplete"),
    ("levels-total-not-an-int", _set(S1 + ["levels", "total_levels"], "2"), "levels-incomplete"),
    ("levels-list-not-a-list", _set(S1 + ["levels", "levels"], "x"), "levels-incomplete"),
    ("levels-total-differs-from-the-list", _set(S1 + ["levels", "total_levels"], 7), "levels-incomplete"),
    ("level-entry-without-a-name", _set(S2 + ["levels", "levels", 0, "name"], None), "levels-incomplete"),
    ("level-entry-without-an-id", _set(S2 + ["levels", "levels", 0, "id"], None), "levels-incomplete"),
    ("level-count-differs-between-routes", _set(S1 + ["summary", "level_count"], 99), "counts-inconsistent"),
    ("skipped-levels-hide-a-count", _set(S1 + ["levels", "skipped_levels"], 1), "counts-inconsistent"),
    # one process only
    ("summary-from-another-process", _set(S1 + ["summary", "identity", "session_token"], T2), "identity-mismatch"),
    ("levels-without-identity", _drop(S2 + ["levels", "identity"]), "identity-mismatch"),
    ("listing-from-another-pid", _set(S1 + ["before_listing", "identity", "pid"], 1), "identity-mismatch"),
    ("after-listing-without-identity", _set(S2 + ["after_listing", "identity"], None), "identity-mismatch"),
    # a read never activates
    ("activation-call-during-a-read", _append_call("POST", "/activate_document/", "activate_document",
                                                   "g3:a_active_b_read"), "activation-in-read"),
    ("activation-call-in-the-reverse-read", _append_call("POST", "/activate_document/", "activate_document",
                                                         "g3:b_active_a_read"), "activation-in-read"),
    # the engineer's own observation
    ("ui-unobserved", _engineer(S1, "ui", None), "engineer-ui-unobserved"),
    ("ui-observation-section-missing", _drop(S2 + ["engineer"]), "engineer-ui-unobserved"),
    ("ui-changed-by-the-read", _engineer(S1, "ui", "changed"), "engineer-ui-changed"),
    ("ui-some-other-word", _engineer(S1, "ui", "fine"), "engineer-ui-unobserved"),
    ("data-unconfirmed", _engineer(S1, "data_matches_addressed", None), "engineer-data-unconfirmed"),
    ("data-mismatch", _engineer(S2, "data_matches_addressed", False), "engineer-data-mismatch"),
    ("data-confirmation-is-a-string", _engineer(S2, "data_matches_addressed", "yes"), "engineer-data-unconfirmed"),
    ("a-dialog-needed-input-during-a-read", _engineer(S1, "dialog_required_input", True), "dialog-required-input"),
]


@pytest.mark.parametrize("label,mutate,code", COMMON_STOP_CASES + G3_STOP_CASES,
                         ids=[c[0] for c in COMMON_STOP_CASES + G3_STOP_CASES])
def test_g3_stop_reason_is_named(label, mutate, code):
    rec = good_g34_record()
    mutate(rec)
    verdict, found = g3_verdict(rec)
    assert verdict == proc.STOP, label
    assert code in found, (label, found)


def test_g3_unset_dialog_field_is_allowed_but_never_an_assumed_pass():
    rec = good_g34_record()
    assert rec["g3"]["slots"]["a_active_b_read"]["engineer"]["dialog_required_input"] is None
    assert proc.classify_g3_production(rec)[0] == proc.G3_OBSERVED


def test_g3_indistinguishable_documents_are_stop():
    # Two open documents with the same title and path: a read cannot show whose data it returned.
    with pytest.MonkeyPatch.context() as mp:
        bench = FakeBench(same_presentation=True)
        install_bench(mp, bench)
        with tempfile.TemporaryDirectory() as folder:
            raw = capture_flow(_Path(folder), bench, cases=())
            record = load(raw)
    verdict, found = g3_verdict(record)
    assert verdict == proc.STOP and "documents-indistinguishable" in found


def test_g3_reasons_accumulate():
    rec = good_g34_record()
    rec["live"] = False
    rec["g3"]["slots"]["a_active_b_read"]["summary"]["ui_switched"] = True
    verdict, found = g3_verdict(rec)
    assert verdict == proc.STOP and "not-live" in found and "ui-switched" in found


# ---------------------------------------------------------------- G4 production


def _not_run(path, reason="not on this bench"):
    return _set(path, {"status": "not-run", "reason": reason})


def _case_reply(path, key, value):
    return _set(path + ["reply", key], value)


def _a_second_activation(step):
    return _append_call("POST", "/activate_document/", "activate_document", step)


G4_STOP_CASES = [
    # the allow case
    ("allow-refused", _case_reply(CA, "kind", "refused"), "allow-not-activated"),
    ("allow-answered-already-active", _case_reply(CA, "activation", "already-active"), "allow-not-activated"),
    ("allow-without-an-activation-word", _case_reply(CA, "activation", None), "allow-not-activated"),
    ("allow-http-500", _set(CA + ["reply"], {"kind": "error", "http_status": 500, "activation": None,
                                             "reason": "activation-failed", "document": SEL_A,
                                             "observed_active_document": SEL_B,
                                             "identity": dict(G34_IDENT), "at": "t", "text": "x"}),
     "allow-not-activated"),
    ("allow-target-was-already-active", _set(CA + ["target_document"], SEL_B), "allow-target-already-active"),
    ("allow-target-has-no-path", _set(CA + ["before_listing", "documents", 0, "path"], ""), "allow-without-path"),
    ("allow-after-listing-names-the-other-document", _set(CA + ["after_listing", "active_document"], SEL_B),
     "target-not-active-after"),
    ("allow-reply-observed-the-other-document", _case_reply(CA, "observed_active_document", SEL_B),
     "observed-active-mismatch"),
    ("allow-reply-names-another-document", _case_reply(CA, "document", SEL_B), "observed-active-mismatch"),
    # refusal cases
    ("unsaved-was-activated", _set(CU + ["reply"], {
        "kind": "success", "http_status": 200, "activation": "activated", "reason": None, "error_code": None,
        "document": SEL_U, "observed_active_document": SEL_U, "identity": dict(G34_IDENT), "at": "t", "text": "x"}),
     "refusal-activated"),
    ("unsaved-answered-already-active", _case_reply(CU, "activation", "already-active"), "refusal-activated"),
    ("unsaved-409", _set(CU + ["reply"], {
        "kind": "refused", "http_status": 409, "activation": None, "reason": "document-not-activated",
        "error_code": "document-not-activated", "document": SEL_U, "observed_active_document": SEL_A,
        "identity": dict(G34_IDENT), "at": "t", "text": "x"}), "refusal-missing"),
    ("unsaved-transport-error", _set(CU + ["reply"], {
        "kind": "error", "http_status": None, "activation": None, "reason": None, "error_code": None,
        "document": None, "observed_active_document": None, "identity": None, "at": "t", "text": "Error: x"}),
     "refusal-missing"),
    ("unsaved-reply-missing", _drop(CU + ["reply"]), "refusal-missing"),
    ("unsaved-wrong-reason", _case_reply(CU, "reason", "detached"), "refusal-reason-mismatch"),
    ("detached-wrong-reason", _case_reply(CD, "reason", "unsaved"), "refusal-reason-mismatch"),
    ("detached-reason-absent", _case_reply(CD, "reason", None), "refusal-reason-mismatch"),
    ("workshared-wrong-reason", _case_reply(CW, "reason", "detached"), "refusal-reason-mismatch"),
    ("unsaved-ui-changed-by-the-refusal", _set(CU + ["after_listing", "active_document"], SEL_U),
     "active-document-changed"),
    ("detached-ui-changed-by-the-refusal", _set(CD + ["after_listing", "active_document"], SEL_D),
     "active-document-changed"),
    ("unsaved-reply-observed-another-document", _case_reply(CU, "observed_active_document", SEL_U),
     "observed-active-mismatch"),
    # saved-workshared is a refusal case only
    ("workshared-allow-attempt-by-expectation", _set(CW + ["expect"], "allow"), "workshared-activation-attempt"),
    ("workshared-activated", _set(CW + ["reply"], {
        "kind": "success", "http_status": 200, "activation": "activated", "reason": None, "error_code": None,
        "document": SEL_W, "observed_active_document": SEL_W, "identity": dict(G34_IDENT), "at": "t",
        "text": "x"}), "workshared-activation-attempt"),
    ("workshared-refusal-then-active-moved", _set(CW + ["after_listing", "active_document"], SEL_W),
     "active-document-changed"),
    # listings and identity
    ("before-listing-missing", _drop(CU + ["before_listing"]), "listing-unusable"),
    ("after-listing-not-ok", _set(CD + ["after_listing", "ok"], False), "listing-unusable"),
    ("after-listing-two-active", _set(CA + ["after_listing", "active_count"], 2), "listing-unusable"),
    ("target-not-listed", _set(CU + ["target_document"], SEL_ZZ), "target-not-listed"),
    ("reply-from-another-process", _set(CA + ["reply", "identity", "session_token"], T2), "identity-mismatch"),
    ("reply-without-identity", _set(CU + ["reply", "identity"], None), "identity-mismatch"),
    ("listing-from-another-pid", _set(CD + ["before_listing", "identity", "pid"], 1), "identity-mismatch"),
    # the engineer's own observation
    ("allow-ui-unobserved", _engineer(CA, "ui", None), "engineer-ui-unobserved"),
    ("allow-ui-still-the-old-document", _engineer(CA, "ui", "unchanged"), "engineer-ui-unexpected"),
    ("allow-ui-another-document", _engineer(CA, "ui", "other-active"), "engineer-ui-unexpected"),
    ("refusal-ui-unobserved", _engineer(CU, "ui", None), "engineer-ui-unobserved"),
    ("refusal-ui-moved", _engineer(CU, "ui", "target-active"), "engineer-ui-unexpected"),
    ("refusal-ui-another-document", _engineer(CD, "ui", "other-active"), "engineer-ui-unexpected"),
    ("engineer-section-missing", _drop(CD + ["engineer"]), "engineer-ui-unobserved"),
    ("allow-dialog-field-unset", _engineer(CA, "dialog_required_input", None), "dialog-observation-missing"),
    ("refusal-dialog-field-unset", _engineer(CU, "dialog_required_input", None), "dialog-observation-missing"),
    ("workshared-dialog-field-unset", _engineer(CW, "dialog_required_input", None), "dialog-observation-missing"),
    ("dialog-field-missing-entirely", _drop(CD + ["engineer", "dialog_required_input"]),
     "dialog-observation-missing"),
    ("dialog-field-is-a-string", _engineer(CD, "dialog_required_input", "none"), "dialog-observation-missing"),
    ("dialog-field-is-zero", _engineer(CA, "dialog_required_input", 0), "dialog-observation-missing"),
    ("allow-dialog-required-input", _engineer(CA, "dialog_required_input", True), "dialog-required-input"),
    ("refusal-dialog-required-input", _engineer(CU, "dialog_required_input", True), "dialog-required-input"),
    # activation calls: one per exercised case, never a retry, never outside a case
    ("refused-case-retried", _a_second_activation("g4:unsaved"), "activation-retried"),
    ("allow-case-retried", _a_second_activation("g4:allow"), "activation-retried"),
    ("allow-call-unrecorded", _remove_calls("activate_document", "g4:allow"), "activation-call-unrecorded"),
    ("activation-tagged-with-no-case", _a_second_activation("g4:other"), "activation-outside-case"),
    ("activation-tagged-with-no-step", _a_second_activation(None), "activation-outside-case"),
    ("activation-during-a-g3-read", _a_second_activation("g3:a_active_b_read"), "activation-outside-case"),
    # case slots
    ("unknown-case", _set(["g4", "cases", "bogus"], {"status": "not-run"}), "unknown-case"),
    ("case-claims-a-status-without-data", _set(CU, {"status": "pass"}), "case-malformed"),
    ("case-slot-not-a-dict", _set(CD, "done"), "case-malformed"),
    ("not-run-slot-holding-data", _set(CW, {"status": "not-run", "reply": {"kind": "success"}}),
     "not-run-slot-with-data"),
    ("case-key-and-name-disagree", _set(CU + ["case"], "allow"), "case-malformed"),
]


@pytest.mark.parametrize("label,mutate,code", COMMON_STOP_CASES + G4_STOP_CASES,
                         ids=[c[0] for c in COMMON_STOP_CASES + G4_STOP_CASES])
def test_g4_stop_reason_is_named(label, mutate, code):
    rec = good_g34_record()
    mutate(rec)
    verdict, found = g4_verdict(rec)
    assert verdict == proc.STOP, label
    assert code in found, (label, found)


def test_g4_every_case_needs_the_engineer_dialog_observation_set_to_false():
    for path in (CA, CU, CD, CW):
        rec = good_g34_record()
        assert rec["g4"]["cases"][path[-1]]["engineer"]["dialog_required_input"] is False
        for bad in (None, True, "false", 0, "", [], {}):
            clone = copy.deepcopy(rec)
            node = clone
            for key in path:
                node = node[key]
            node["engineer"]["dialog_required_input"] = bad
            verdict, _found = g4_verdict(clone)
            assert verdict == proc.STOP, (path[-1], bad)


def test_g4_detached_or_non_file_accepts_either_measured_refusal_reason():
    for reason in ("detached", "no-usable-file-path"):
        rec = good_g34_record()
        rec["g4"]["cases"]["detached_or_non_file"]["reply"]["reason"] = reason
        rec["g4"]["cases"]["detached_or_non_file"]["reply"]["error_code"] = reason
        assert proc.classify_g4_production(rec)[0] == proc.G4_OBSERVED, reason


def test_g4_only_the_workshared_class_may_be_absent_and_it_is_reported_not_run():
    rec = good_g34_record()
    _not_run(CW, "no saved workshared model on this bench")(rec)
    rec["sent_calls"] = [c for c in rec["sent_calls"] if c["step"] != "g4:saved_workshared"]
    verdict, reasons = proc.classify_g4_production(rec)
    assert verdict == proc.G4_OBSERVED and reasons == []
    outcomes = proc.g4_case_outcomes(rec)
    assert outcomes == {"allow": "observed", "unsaved": "observed", "detached_or_non_file": "observed",
                        "saved_workshared": "not-run"}


@pytest.mark.parametrize("path,name", [(CA, "allow"), (CU, "unsaved"), (CD, "detached_or_non_file")])
def test_g4_an_absent_required_case_is_not_run_never_pass(path, name):
    rec = good_g34_record()
    _not_run(path)(rec)
    rec["sent_calls"] = [c for c in rec["sent_calls"] if c["step"] != "g4:" + name]
    verdict, found = g4_verdict(rec)
    assert verdict == proc.NOT_RUN and "case-not-run" in found
    assert proc.g4_case_outcomes(rec)[name] == "not-run"
    # a missing key and a null slot read the same way
    for variant in (_drop(path), _set(path, None)):
        clone = good_g34_record()
        clone["sent_calls"] = [c for c in clone["sent_calls"] if c["step"] != "g4:" + name]
        variant(clone)
        assert g4_verdict(clone)[0] == proc.NOT_RUN


def test_g4_no_case_at_all_is_not_run_and_an_empty_cases_section_too():
    rec = good_g34_record()
    rec["g4"]["cases"] = {}
    rec["sent_calls"] = [c for c in rec["sent_calls"] if c["tool"] != "activate_document"]
    assert g4_verdict(rec)[0] == proc.NOT_RUN
    rec = good_g34_record()
    del rec["g4"]
    rec["sent_calls"] = [c for c in rec["sent_calls"] if c["tool"] != "activate_document"]
    assert g4_verdict(rec)[0] == proc.NOT_RUN


def test_g4_a_stop_wins_over_a_not_run():
    rec = good_g34_record()
    _not_run(CD)(rec)
    rec["sent_calls"] = [c for c in rec["sent_calls"] if c["step"] != "g4:detached_or_non_file"]
    rec["g4"]["cases"]["unsaved"]["reply"]["activation"] = "activated"
    verdict, found = g4_verdict(rec)
    assert verdict == proc.STOP and "refusal-activated" in found


def test_g4_outcomes_name_stop_for_the_failing_case_only():
    rec = good_g34_record()
    rec["g4"]["cases"]["unsaved"]["engineer"]["dialog_required_input"] = None
    outcomes = proc.g4_case_outcomes(rec)
    assert outcomes["unsaved"] == "stop"
    assert outcomes["allow"] == "observed" and outcomes["detached_or_non_file"] == "observed"


def test_g3_and_g4_verdicts_are_independent_of_each_others_case_data():
    rec = good_g34_record()
    rec["g3"]["slots"]["a_active_b_read"]["summary"]["ui_switched"] = True
    assert proc.classify_g3_production(rec)[0] == proc.STOP
    assert proc.classify_g4_production(rec)[0] == proc.G4_OBSERVED
    rec = good_g34_record()
    rec["g4"]["cases"]["allow"]["engineer"]["dialog_required_input"] = True
    assert proc.classify_g4_production(rec)[0] == proc.STOP
    assert proc.classify_g3_production(rec)[0] == proc.G3_OBSERVED


# ---------------------------------------------------------------- no approval, never raises


ALL_MUTATED = (
    [(m, c) for _l, m, c in COMMON_STOP_CASES + G3_STOP_CASES + G4_STOP_CASES]
)


def _mutated_records():
    yield good_g34_record()
    for mutate, _code in ALL_MUTATED:
        rec = good_g34_record()
        try:
            mutate(rec)
        except (KeyError, IndexError, TypeError):
            continue
        yield rec
    for junk in (None, [], "x", 0, {}, {"live": True}, proc.g34_template(), proc.evidence_template()):
        yield junk


def test_neither_classifier_can_return_an_approval_verdict():
    allowed = {proc.STOP, proc.G3_OBSERVED, proc.G4_OBSERVED, proc.NOT_RUN}
    seen = set()
    for rec in _mutated_records():
        for classify in (proc.classify_g3_production, proc.classify_g4_production):
            verdict, reasons = classify(rec)
            assert verdict in allowed
            assert isinstance(reasons, list)
            for word in ("approv", "pass", "accept"):
                assert word not in verdict
            seen.add(verdict)
    assert {proc.STOP, proc.G3_OBSERVED, proc.G4_OBSERVED} <= seen
    assert proc.APPROVAL == "not-granted"


def test_g3_observed_is_only_ever_returned_by_the_g3_classifier_and_g4_by_the_g4_one():
    rec = good_g34_record()
    assert proc.classify_g3_production(rec)[0] == proc.G3_OBSERVED
    assert proc.classify_g4_production(rec)[0] == proc.G4_OBSERVED
    assert proc.G3_OBSERVED != proc.G4_OBSERVED


@pytest.mark.parametrize("junk", [None, "x", {}, 7, [None]])
@pytest.mark.parametrize("classify", ["classify_g3_production", "classify_g4_production"])
def test_g34_classifiers_never_raise_on_malformed_records(classify, junk):
    count = 0
    for variant in _walk_replace(good_g34_record(), junk):
        verdict, reasons = getattr(proc, classify)(variant)
        assert verdict in (proc.STOP, proc.NOT_RUN, proc.G3_OBSERVED, proc.G4_OBSERVED)
        assert isinstance(reasons, list)
        count += 1
    assert count > 100


@pytest.mark.parametrize("junk", [None, [], "x", 0, {}, b"bytes", 1.5, object()])
def test_g34_classifiers_stop_on_a_non_record(junk):
    for classify in (proc.classify_g3_production, proc.classify_g4_production):
        verdict, found = classify(junk)
        assert verdict == proc.STOP
        assert codes(found)[0] == "no-record"


def test_g34_classifier_internal_error_reads_as_stop(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("synthetic classifier bug")

    monkeypatch.setattr(proc, "_complete_identity", boom)
    for classify in (proc.classify_g3_production, proc.classify_g4_production):
        verdict, found = classify(good_g34_record())
        assert verdict == proc.STOP
        assert "classifier-error" in codes(found)


def test_every_declared_g34_reason_code_has_a_stop_case():
    covered = set(code for _l, _m, code in COMMON_STOP_CASES + G3_STOP_CASES + G4_STOP_CASES)
    declared = set(proc.G34_REASON_CODES)
    assert declared - covered <= {"no-record", "classifier-error", "case-not-run",
                                  "documents-indistinguishable"}
    # and the cases only name declared codes
    assert covered <= declared


# ---------------------------------------------------------------- the commands against the bench double


G3_OBS = "PHASE2_G3_PRODUCTION_OBSERVED"
G4_OBS = "PHASE2_G4_PRODUCTION_OBSERVED"


@pytest.fixture
def bench(monkeypatch):
    fake = FakeBench()
    install_bench(monkeypatch, fake)
    return fake


def test_full_flow_prints_both_sentinels_only_after_the_engineer_observations(tmp_path, bench, capsys):
    raw = capture_flow(tmp_path, bench)
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 0
    out = capsys.readouterr().out
    assert G3_OBS + " approval=not-granted" in out
    assert G4_OBS + " approval=not-granted" in out
    assert "STOP" not in out
    for case in ("allow", "unsaved", "detached_or_non_file", "saved_workshared"):
        assert "G4 CASE {}: observed".format(case) in out


def test_the_capture_commands_themselves_never_print_an_observed_sentinel(tmp_path, bench, capsys):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    assert cmd("g3-read", "--in", raw, "--slot", "a_active_b_read", "--target", "2") == 0
    bench.active = SEL_B
    assert cmd("g3-read", "--in", raw, "--slot", "b_active_a_read", "--target", "1") == 0
    assert cmd("g4-case", "--in", raw, "--case", "allow", "--target", "1") == 0
    out = capsys.readouterr().out
    assert G3_OBS not in out and G4_OBS not in out
    assert "PHASE2_G34_PENDING" in out and "approval=not-granted" in out


def test_without_the_engineer_nothing_is_ever_observed(tmp_path, bench, capsys):
    raw = capture_flow(tmp_path, bench, observe_engineer=False)
    record = load(raw)
    for slot in record["g3"]["slots"].values():
        assert slot["engineer"]["ui"] is None and slot["engineer"]["dialog_required_input"] is None
        assert slot["engineer"]["data_matches_addressed"] is None
    for case in record["g4"]["cases"].values():
        assert case["engineer"]["ui"] is None and case["engineer"]["dialog_required_input"] is None
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 1
    out = capsys.readouterr().out
    assert G3_OBS not in out and G4_OBS not in out
    assert "PHASE2_G3_PRODUCTION_STOP approval=not-granted" in out
    assert "PHASE2_G4_PRODUCTION_STOP approval=not-granted" in out
    assert "engineer-ui-unobserved" in out and "dialog-observation-missing" in out


def test_a_bench_without_a_saved_workshared_model_still_observes_and_lists_it_as_not_run(tmp_path, bench, capsys):
    raw = capture_flow(tmp_path, bench, cases=("allow", "unsaved", "detached_or_non_file"))
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 0
    out = capsys.readouterr().out
    assert G4_OBS in out
    assert "G4 CASE saved_workshared: not-run" in out


def test_a_bench_without_an_unsaved_document_is_not_run_and_prints_no_g4_sentinel(tmp_path, bench, capsys):
    raw = capture_flow(tmp_path, bench, cases=("allow", "detached_or_non_file", "saved_workshared"))
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 1
    out = capsys.readouterr().out
    assert G3_OBS in out
    assert G4_OBS not in out
    assert "PHASE2_G4_PRODUCTION_NOT_RUN approval=not-granted" in out
    assert "G4 CASE unsaved: not-run" in out


def test_an_addressed_read_that_moves_the_ui_is_stop_even_when_the_data_is_right(tmp_path, bench, capsys):
    bench.read_moves_ui_to = SEL_B
    raw = capture_flow(tmp_path, bench)
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 1
    out = capsys.readouterr().out
    assert G3_OBS not in out and "PHASE2_G3_PRODUCTION_STOP" in out
    assert "ui-switched" in out or "active-document-changed" in out


def test_a_read_answered_with_another_documents_data_is_stop(tmp_path, bench, capsys):
    bench.read_answers_from = {SEL_B: SEL_A}
    raw = capture_flow(tmp_path, bench)
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 1
    out = capsys.readouterr().out
    assert G3_OBS not in out and "data-not-from-target" in out


def test_a_refused_class_that_gets_activated_is_stop_and_names_the_case(tmp_path, bench, capsys):
    bench.refusals_activate = True
    raw = capture_flow(tmp_path, bench)
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 1
    out = capsys.readouterr().out
    assert G4_OBS not in out and "PHASE2_G4_PRODUCTION_STOP" in out
    assert "refusal-activated" in out and "workshared-activation-attempt" in out
    assert "G4 CASE saved_workshared: stop" in out


def test_engineer_reporting_a_dialog_is_stop_not_observed(tmp_path, bench, capsys):
    raw = capture_flow(tmp_path, bench)
    assert observe(raw, "g4:unsaved", "unchanged", dialog="input-required") == 0
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 1
    out = capsys.readouterr().out
    assert G4_OBS not in out and "dialog-required-input" in out
    assert G3_OBS in out  # the read gate does not depend on a G4 dialog


def test_engineer_reporting_the_window_moved_during_a_read_is_stop(tmp_path, bench, capsys):
    raw = capture_flow(tmp_path, bench)
    assert observe(raw, "g3:a_active_b_read", "changed", data="matches") == 0
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 1
    out = capsys.readouterr().out
    assert G3_OBS not in out and "engineer-ui-changed" in out


def test_engineer_reporting_wrong_data_is_stop(tmp_path, bench, capsys):
    raw = capture_flow(tmp_path, bench)
    assert observe(raw, "g3:b_active_a_read", "unchanged", data="mismatch") == 0
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 1
    assert "engineer-data-mismatch" in capsys.readouterr().out


def test_a_re_recorded_observation_keeps_the_superseded_one(tmp_path, bench):
    raw = capture_flow(tmp_path, bench)
    assert observe(raw, "g4:allow", "other-active", dialog="none") == 0
    record = load(raw)
    case = record["g4"]["cases"]["allow"]
    assert case["engineer"]["ui"] == "other-active"
    assert case["engineer_superseded"][0]["ui"] == "target-active"
    assert proc.classify_g4_production(record)[0] == proc.STOP


# ---------------------------------------------------------------- what the commands send


def test_every_document_call_names_the_bootstrapped_process_and_the_chosen_document(tmp_path, bench):
    capture_flow(tmp_path, bench)
    for name in ("list_documents", "read_document_summary", "read_document_levels", "activate_document"):
        calls = bench.called(name)
        assert calls, name
        for args in calls:
            assert args["target"].startswith("revit1:"), (name, args)
    for args in bench.called("read_document_summary") + bench.called("read_document_levels"):
        assert args["document"] in (SEL_A, SEL_B)
    assert [a["document"] for a in bench.called("activate_document")] == [SEL_A, SEL_U, SEL_D, SEL_W]


def test_only_the_five_allowed_tools_are_ever_called_and_one_activation_per_case(tmp_path, bench):
    capture_flow(tmp_path, bench)
    names = [name for name, _args in bench.tool_calls]
    assert set(names) <= {"get_revit_status", "list_documents", "read_document_summary",
                          "read_document_levels", "activate_document"}
    assert names.count("activate_document") == 4
    assert {route for _m, route, _d, _o in bench.routes} <= {
        "/documents/", "/document_summary/", "/document_levels/", "/activate_document/"}
    routes = [route for _m, route, _d, _o in bench.routes]
    first_activation = routes.index("/activate_document/")
    assert "/activate_document/" not in routes[:first_activation]
    assert routes[:first_activation].count("/document_summary/") == 2  # both G3 directions came first
    assert routes[:first_activation].count("/document_levels/") == 2


def test_the_g3_reads_never_activate_anything(tmp_path, bench):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    assert cmd("g3-read", "--in", raw, "--slot", "a_active_b_read", "--target", "2") == 0
    assert bench.active == SEL_A
    assert not bench.called("activate_document")
    record = load(raw)
    assert not [c for c in record["sent_calls"] if c["route"] == "/activate_document/"]
    slot = record["g3"]["slots"]["a_active_b_read"]
    assert slot["target_document"] == SEL_B
    assert slot["summary"]["title"] == "Beta" and slot["levels"]["total_levels"] == 2
    assert slot["before_listing"]["active_document"] == SEL_A == slot["after_listing"]["active_document"]
    # one listing before, the two reads, one listing after
    assert [n for n, _a in bench.tool_calls] == [
        "get_revit_status", "list_documents", "get_revit_status", "list_documents",
        "read_document_summary", "read_document_levels", "list_documents"]


def test_g4_refusal_case_is_sent_exactly_once_and_never_retried_after_a_refusal(tmp_path, bench):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    assert cmd("g4-case", "--in", raw, "--case", "unsaved", "--target", "3") == 0
    assert bench.called("activate_document") == [{"document": SEL_U, "target": load(raw)["process"]["selector"]}]
    case = load(raw)["g4"]["cases"]["unsaved"]
    assert case["reply"]["kind"] == "refused" and case["reply"]["http_status"] == 422
    assert case["reply"]["reason"] == "unsaved"
    assert case["expect"] == "refuse"
    assert bench.active == SEL_A


# ---------------------------------------------------------------- command guards (no live call)


def test_start_refuses_an_output_path_inside_the_repository_before_any_live_call(monkeypatch, capsys):
    def no_server(_port):
        raise AssertionError("a live server must not start")

    monkeypatch.setattr(proc, "_server", no_server)
    inside = os.path.join(REPO_ROOT, "raw-g34-capture.json")
    assert cmd("g34-start", "--out", inside) == 2
    assert not os.path.exists(inside)
    assert G3_OBS not in capsys.readouterr().out


def test_start_never_overwrites_an_existing_capture(tmp_path, bench):
    raw = tmp_path / "g34.json"
    raw.write_bytes(b"precious")
    assert cmd("g34-start", "--out", str(raw)) == 2
    assert raw.read_bytes() == b"precious"
    assert not bench.tool_calls


@pytest.mark.parametrize("argv", [
    ["g34-start"],
    ["g34-start", "--out"],
    ["g34-start", "--out", "x.json", "--port", "70000"],
    ["g34-start", "--out", "x.json", "--port", "abc"],
    ["g34-start", "--out", "x.json", "--out", "y.json"],
    ["g3-read", "--in", "x.json", "--slot", "a_active_b_read"],
    ["g3-read", "--in", "x.json", "--slot", "c_other", "--target", "2"],
    ["g3-read", "--in", "x.json", "--slot", "a_active_b_read", "--target", "two"],
    ["g3-read", "--in", "x.json", "--slot", "a_active_b_read", "--target", "0"],
    ["g4-case", "--in", "x.json", "--case", "bogus", "--target", "1"],
    ["g4-case", "--in", "x.json", "--case", "allow"],
    ["g4-case", "--in", "x.json", "--target", "1"],
    ["g34-observe", "--in", "x.json", "--step", "g4:allow", "--ui", "target-active"],
    ["g34-observe", "--in", "x.json", "--step", "g4:nothing", "--ui", "unchanged", "--dialog", "none"],
    ["g34-observe", "--in", "x.json", "--step", "g4:unsaved", "--ui", "sideways", "--dialog", "none"],
    ["g34-observe", "--in", "x.json", "--step", "g4:unsaved", "--ui", "unchanged", "--dialog", "maybe"],
    ["g34-observe", "--in", "x.json", "--step", "g3:a_active_b_read", "--ui", "unchanged"],
    ["g34-observe", "--in", "x.json", "--step", "g3:a_active_b_read", "--data", "matches"],
    ["g34-observe", "--in", "x.json", "--step", "g3:a_active_b_read", "--ui", "target-active", "--data", "matches"],
    ["g34-observe", "--in", "x.json", "--step", "g3:a_active_b_read", "--ui", "unchanged", "--data", "yes"],
    ["g34-classify"],
    ["g34-classify", "a.json", "b.json"],
    ["g34-template", "extra"],
])
def test_malformed_commands_are_usage_errors_before_any_live_call(monkeypatch, argv, capsys):
    def no_server(_port):
        raise AssertionError("a live server must not start")

    monkeypatch.setattr(proc, "_server", no_server)
    code = cmd(*argv)
    out = capsys.readouterr().out
    assert code == 2, (argv, out)
    assert G3_OBS not in out and G4_OBS not in out


@pytest.mark.parametrize("argv", [
    ["g3-read", "--in", "MISSING", "--slot", "a_active_b_read", "--target", "2"],
    ["g4-case", "--in", "MISSING", "--case", "allow", "--target", "1"],
    ["g34-observe", "--in", "MISSING", "--step", "g4:allow", "--ui", "target-active", "--dialog", "none"],
    ["g34-classify", "MISSING"],
])
def test_commands_without_a_capture_are_stop_not_a_live_call(monkeypatch, tmp_path, argv, capsys):
    def no_server(_port):
        raise AssertionError("a live server must not start")

    monkeypatch.setattr(proc, "_server", no_server)
    argv = [str(tmp_path / "never-written.json") if a == "MISSING" else a for a in argv]
    assert cmd(*argv) == 1
    out = capsys.readouterr().out
    assert G3_OBS not in out and G4_OBS not in out


def test_live_commands_refuse_an_input_path_inside_the_repository(monkeypatch):
    def no_server(_port):
        raise AssertionError("a live server must not start")

    monkeypatch.setattr(proc, "_server", no_server)
    inside = os.path.join(REPO_ROOT, "tests", "unit", "test_phase2_live_identity.py")
    assert cmd("g3-read", "--in", inside, "--slot", "a_active_b_read", "--target", "2") == 2
    assert cmd("g4-case", "--in", inside, "--case", "allow", "--target", "1") == 2
    assert cmd("g34-observe", "--in", inside, "--step", "g4:allow", "--ui", "target-active",
               "--dialog", "none") == 2


def test_g3_read_of_the_active_document_is_refused_before_any_read(tmp_path, bench):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    before = open(raw, "rb").read()
    assert cmd("g3-read", "--in", raw, "--slot", "a_active_b_read", "--target", IDX[SEL_A]) == 1
    assert not bench.called("read_document_summary") and not bench.called("read_document_levels")
    assert open(raw, "rb").read() == before


def test_g3_read_with_a_target_number_beyond_the_listing_is_refused(tmp_path, bench):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    assert cmd("g3-read", "--in", raw, "--slot", "a_active_b_read", "--target", "9") == 1
    assert not bench.called("read_document_summary")


def test_a_captured_slot_or_case_is_never_overwritten(tmp_path, bench):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    assert cmd("g3-read", "--in", raw, "--slot", "a_active_b_read", "--target", "2") == 0
    first = load(raw)["g3"]["slots"]["a_active_b_read"]
    calls = len(bench.tool_calls)
    assert cmd("g3-read", "--in", raw, "--slot", "a_active_b_read", "--target", "2") == 2
    assert len(bench.tool_calls) == calls
    assert load(raw)["g3"]["slots"]["a_active_b_read"] == first
    assert cmd("g4-case", "--in", raw, "--case", "unsaved", "--target", "3") == 0
    calls = len(bench.called("activate_document"))
    assert cmd("g4-case", "--in", raw, "--case", "unsaved", "--target", "3") == 2
    assert len(bench.called("activate_document")) == calls


def test_g4_case_guards_stop_before_the_activation_call(tmp_path, bench):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    # the active document is never a refusal or allow measurement
    assert cmd("g4-case", "--in", raw, "--case", "allow", "--target", IDX[SEL_A]) == 1
    # an unsaved measurement must not be pointed at a document that has a path
    assert cmd("g4-case", "--in", raw, "--case", "unsaved", "--target", IDX[SEL_B]) == 1
    # an allow measurement needs a saved document
    assert cmd("g4-case", "--in", raw, "--case", "allow", "--target", IDX[SEL_U]) == 1
    # a saved-workshared measurement needs a document with a path
    assert cmd("g4-case", "--in", raw, "--case", "saved_workshared", "--target", IDX[SEL_U]) == 1
    assert cmd("g4-case", "--in", raw, "--case", "allow", "--target", "9") == 1
    assert not bench.called("activate_document")
    assert bench.active == SEL_A
    assert load(raw)["g4"]["cases"]["allow"]["status"] == "not-run"


def test_a_restarted_revit_between_commands_is_stop_and_leaves_the_record_alone(tmp_path, bench, capsys):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    before = open(raw, "rb").read()
    other = ident(9999, T2)
    bench.status_text = lambda arguments: "Process Identity: {}".format(repr(other))
    calls = len(bench.tool_calls)
    assert cmd("g3-read", "--in", raw, "--slot", "a_active_b_read", "--target", "2") == 1
    assert cmd("g4-case", "--in", raw, "--case", "unsaved", "--target", "3") == 1
    assert [n for n, _a in bench.tool_calls[calls:]] == ["get_revit_status", "get_revit_status"]
    assert open(raw, "rb").read() == before
    assert "identity" in capsys.readouterr().out.lower()


def test_an_ambiguous_port_owner_stops_before_any_selected_call(tmp_path, bench, monkeypatch, capsys):
    raw = str(tmp_path / "g34.json")
    monkeypatch.setattr(
        proc, "collect_listener_owners",
        lambda port: {"port": port, "owners": [4242, 1], "source": "bridge.listener_snapshot", "at": "t"})
    assert cmd("g34-start", "--out", raw) == 1
    assert not os.path.exists(raw)
    assert [n for n, _a in bench.tool_calls] == ["get_revit_status"]
    assert G3_OBS not in capsys.readouterr().out


def test_observe_needs_a_captured_step(tmp_path, bench):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    assert observe(raw, "g4:allow", "target-active", dialog="none") == 1
    assert observe(raw, "g3:a_active_b_read", "unchanged", data="matches") == 1


def test_observe_is_the_only_writer_of_the_engineer_fields(tmp_path, bench):
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    assert cmd("g4-case", "--in", raw, "--case", "unsaved", "--target", "3") == 0
    engineer = load(raw)["g4"]["cases"]["unsaved"]["engineer"]
    assert engineer["ui"] is None and engineer["dialog_required_input"] is None
    assert observe(raw, "g4:unsaved", "unchanged", dialog="none") == 0
    engineer = load(raw)["g4"]["cases"]["unsaved"]["engineer"]
    assert engineer["ui"] == "unchanged" and engineer["dialog_required_input"] is False
    assert engineer["source"] == "engineer-command-line" and engineer["at"]


# ---------------------------------------------------------------- other commands


def test_g34_template_command_prints_json_and_no_sentinel(capsys):
    assert cmd("g34-template") == 0
    out = capsys.readouterr().out
    template = json.loads(out)
    assert template["schema"] == proc.G34_SCHEMA and template["not_run"]["g6"]["status"] == "not-run"
    assert G3_OBS not in out and G4_OBS not in out


def test_g34_classify_on_the_template_or_garbage_prints_no_sentinel(tmp_path, capsys):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(proc.g34_template()), encoding="utf-8")
    assert cmd("g34-classify", str(path)) == 1
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe not json")
    assert cmd("g34-classify", str(bad)) == 1
    out = capsys.readouterr().out
    assert G3_OBS not in out and G4_OBS not in out
    assert "PHASE2_G3_PRODUCTION_STOP" in out


def test_g34_classify_never_prints_a_sentinel_for_a_synthetic_record(tmp_path, bench, capsys):
    raw = capture_flow(tmp_path, bench)
    record = load(raw)
    record["synthetic"] = True
    with open(raw, "wb") as handle:
        handle.write(json.dumps(record).encode("utf-8"))
    capsys.readouterr()
    assert cmd("g34-classify", raw) == 1
    out = capsys.readouterr().out
    assert G3_OBS not in out and G4_OBS not in out


def test_the_identity_commands_are_unchanged_and_keep_g3_g4_as_not_run(tmp_path, capsys):
    template = proc.evidence_template()
    assert template["not_run"]["g3"]["status"] == "not-run" and template["not_run"]["g4"]["status"] == "not-run"
    assert proc.main(["template"]) == 0
    capsys.readouterr()


def test_usage_names_every_g34_command():
    for name in ("g34-template", "g34-start", "g3-read", "g4-case", "g34-observe", "g34-classify"):
        assert name in proc.USAGE or name in proc.G34_USAGE, name


ACTIVATION_FAILED_BODY = {
    "error": "Activating document failed", "error_code": "activation-failed",
    "reason": "activation-failed", "document": {"document": "doc1.aaaaaaaaaaaa.2"},
    "observed_active_document": None,
    "exception": {"python_type": "InvalidOperationException",
                  "net_type": "Autodesk.Revit.Exceptions.InvalidOperationException",
                  "message": "A managed exception was thrown",
                  "inner_exceptions": [{"net_type": "System.IO.IOException", "message": "root"}],
                  "stack_trace": "   at Frame()"},
}


@pytest.mark.parametrize("tool,kwargs,status", [
    ("read_document_summary", {"document": "doc1.zzzzzzzzzzzz.9"}, 404),
    ("activate_document", {"document": "doc1.zzzzzzzzzzzz.9"}, 404),
])
def test_a_refusal_rendered_with_the_attribution_lines_of_02_16_still_parses_as_a_named_refusal(tool, kwargs, status):
    p = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    p.open_doc("X", "C:/b/X.rvt", active=True)
    bench = AccBench(p)
    text = render_tool(bench, tool, target=bench.discovery()["usable"][0]["selector"], **kwargs)
    assert "Verified Revit process:" in text and text.startswith("Error: {} - ".format(status))
    parsed = proc.parse_summary_text(text) if tool == "read_document_summary" else proc.parse_activation_text(text)
    assert parsed["kind"] == "refused" and parsed["http_status"] == status
    assert parsed["error_code"] == "document-token-unknown" and parsed["identity"] == p.identity


def test_g4_activation_failed_reply_keeps_its_full_text_and_classification_with_diagnostics():
    raw_json = "Error: 500 - " + json.dumps(ACTIVATION_FAILED_BODY)
    appended = raw_json + "\n\nException diagnostics from Revit (rendered by the tool):\n  exception: x"
    plain = proc.build_activation_entry(raw_json)
    rendered = proc.build_activation_entry(appended)
    assert rendered["text"] == appended                      # the full reply text is recorded
    for key in ("kind", "http_status", "error_code", "reason", "document"):
        assert rendered[key] == plain[key]
    assert rendered["http_status"] == 500 and rendered["error_code"] == "activation-failed"


def test_g4_case_prints_the_exception_class_and_message_lines():
    lines = proc._exception_lines(
        "Error: 500 - " + json.dumps(ACTIVATION_FAILED_BODY) + "\n\nException diagnostics from Revit: x")
    assert lines[0] == ("  exception: Autodesk.Revit.Exceptions.InvalidOperationException: "
                        "A managed exception was thrown")
    assert "System.IO.IOException: root" in lines[1]
    assert proc._exception_lines('Error: 422 - {"error": "no"}') == []
    assert proc._exception_lines("Error: 500 - not json") == []
    assert proc._exception_lines(None) == []


def test_non_ascii_document_titles_survive_capture_and_printing(tmp_path, bench, capsys):
    bench.docs[0]["title"] = "Проект Альфа"
    raw = str(tmp_path / "g34.json")
    assert cmd("g34-start", "--out", raw) == 0
    assert cmd("g3-read", "--in", raw, "--slot", "a_active_b_read", "--target", "2") == 0
    capsys.readouterr()
    assert load(raw)["listing_0"]["documents"][0]["title"] == "Проект Альфа"
    assert cmd("g34-classify", raw) == 1  # engineer fields unset: nothing is observed
    assert G3_OBS not in capsys.readouterr().out


# =============================================================================
# Plan 02-18: the single-entry acceptance procedure (classify_phase2_acceptance and
# the phase2-* / g2-* / two-* / mut-* / collision-* / g6-* operator commands).
#
# Everything below runs against AccBench: the REAL tools (documents, parameters,
# status, discovery) behind a text-level stand-in for one or two Revit processes and
# the REAL bridge provenance tagging, so the records the procedure writes are the
# records it would write live and the parsers are pinned to the real renderers. None
# of this is a live result: an accept-eligible verdict from a double proves only that
# the classifier accepts a complete, authorized, self-consistent record. It never
# approves anything; the engineer's choice at the blocking checkpoint does.

import hashlib  # noqa: E402

T3 = "33333333-3333-4333-8333-333333333333"
T4 = "44444444-4444-4444-8444-444444444444"
ACC_FLAGS = ("mutation_authorized", "g6_authorized", "collision_authorized")
ACC_OBS = "PHASE2_ACCEPTANCE_OBSERVED"
ACC_STOP = "PHASE2_ACCEPTANCE_STOP"
USER_WORDS = {
    "mutation_authorized": "Authorized: mutations on the two disposable copies, no save, no sync",
    "g6_authorized": "Authorized: the G6 write/read campaign on the disposable copy, no save, no sync",
    "collision_authorized": "Authorized: the bounded duplicate-listener setup on port 48991 and its teardown",
}


class AccProcess(object):
    """One Revit process as plain data (documents, parameters, behaviour script)."""

    def __init__(self, pid, port, token, prefix):
        self.identity = ident(pid, token, port=port, version="2024")
        self.prefix = prefix
        self.docs = []
        self.active = None
        self.closed = set()
        self.params = {}
        self.serial = 0
        self.script = []  # modes for successive set_parameter calls; empty means persist
        self.visible = True
        self.last_body = None

    def open_doc(self, title, path="", active=False):
        self.serial += 1
        token = "{}.{}".format(self.prefix, self.serial)  # never recycled, even for the same file
        self.docs.append({"document": token, "title": title, "path": path})
        if active or self.active is None:
            self.active = token
        return token

    def close_doc(self, token):
        self.docs = [d for d in self.docs if d["document"] != token]
        self.closed.add(token)
        if self.active == token:
            self.active = self.docs[0]["document"] if self.docs else None

    def entry(self, token):
        for item in self.docs:
            if item["document"] == token:
                return item
        return None

    def descriptor(self, token):
        item = self.entry(token)
        return {"document": token, "title": item["title"], "path": item["path"],
                "active": token == self.active, "saved": bool(item["path"])}


class _AccGet(object):
    revit_target = None

    def __init__(self, bench):
        self.bench = bench

    async def __call__(self, path, ctx=None, **options):
        return self.bench.dispatch("GET", path, None, options)

    async def discover_targets(self, timeout=None):
        return self.bench.discovery()


class _AccPost(object):
    def __init__(self, bench):
        self.bench = bench

    async def __call__(self, path, data, ctx=None, **options):
        return self.bench.dispatch("POST", path, data, options)


class AccBench(object):
    """Zero or more Revit processes behind the real document, parameter, status and discovery tools."""

    def __init__(self, *processes):
        self.processes = list(processes)
        self.collision = {}   # port -> every LISTENING pid, when a collision is staged
        self.tool_calls = []
        self.routes = []
        from tools.document_tools import register_document_tools
        from tools.parameter_tools import register_parameter_tools
        from tools.status_tools import register_status_tools
        from tools.target_tools import register_target_tools

        self.mcp = _ToolRegistry()
        get, post = _AccGet(self), _AccPost(self)
        register_document_tools(self.mcp, get, post)
        register_parameter_tools(self.mcp, get, post)
        register_status_tools(self.mcp, get)
        register_target_tools(self.mcp, get)

    # -- the listener table and discovery -----------------------------------------
    def owners(self, port):
        if port in self.collision:
            return list(self.collision[port])
        return [p.identity["pid"] for p in self.processes
                if p.visible and p.identity["actual_port"] == port]

    def _usable(self):
        return [p for p in sorted(self.processes, key=lambda q: q.identity["actual_port"])
                if p.visible and len(self.owners(p.identity["actual_port"])) == 1]

    def discovery(self):
        usable, unusable = [], []
        for port, pids in sorted(self.collision.items()):
            if len(pids) > 1:
                unusable.append({"port": port, "pids": sorted(pids), "reason": "listener-collision",
                                 "detail": "Port {} has {} LISTENING processes (PIDs {}): requests would land "
                                           "on an unpredictable one.".format(
                                               port, len(pids), ", ".join(str(x) for x in sorted(pids)))})
        for p in self._usable():
            ident_ = p.identity
            usable.append({"selector": proc.make_selector("127.0.0.1", ident_["actual_port"], ident_["pid"],
                                                          ident_["session_token"]),
                           "host": "127.0.0.1", "port": ident_["actual_port"], "pid": ident_["pid"],
                           "session_token": ident_["session_token"], "revit_version": ident_["revit_version"],
                           "document_open": p.active is not None})
        return {"status": "ok", "message": "", "usable": usable, "unusable": unusable}

    # -- the transport ------------------------------------------------------------
    @staticmethod
    def _refused(text, requested=None):
        return bridge._uncertain("Error: " + text, "not-sent", requested)

    def resolve(self, selector):
        if selector is None:
            collisions = [(port, pids) for port, pids in sorted(self.collision.items()) if len(pids) > 1]
            if collisions:
                return None, self._refused(
                    "Listener collision: {}; request not sent. Close the extra Revit or choose a target "
                    "from discover_revit_targets.".format("; ".join(
                        "port {} PIDs {}".format(p, ", ".join(str(x) for x in pids)) for p, pids in collisions)))
            usable = self._usable()
            if not usable:
                return None, self._refused("No usable Revit process found in the probed local ports; "
                                           "request not sent. Start Revit or check discover_revit_targets.")
            if len(usable) > 1:
                lines = "\n".join("- PID {}; Revit {}; port {}; target={}".format(
                    d["pid"], d["revit_version"], d["port"], d["selector"]) for d in self.discovery()["usable"])
                return None, self._refused("Multiple usable Revit processes ({}); request not sent. Pass "
                                           "target=<selector> to choose one:\n{}".format(len(usable), lines))
            return usable[0], None
        try:
            target = bridge.parse_target(selector)
        except ValueError as exc:
            return None, self._refused(str(exc))
        requested = bridge._requested_of(target)
        owners = sorted(set(self.owners(target["port"])))
        if len(owners) > 1:
            return None, self._refused(
                "Listener collision: PIDs {}; request not sent. Rediscover targets.".format(owners), requested)
        for p in self.processes:
            ident_ = p.identity
            if (p.visible and ident_["pid"] == target["pid"] and ident_["actual_port"] == target["port"]
                    and ident_["session_token"] == target["session_token"] and owners == [target["pid"]]):
                return p, None
        return None, self._refused(
            "Listener PID mismatch (owners {}); request not sent. Rediscover targets.".format(owners), requested)

    def dispatch(self, method, path, data, options):
        self.routes.append((method, path, dict(data or {}), dict(options)))
        p, refusal = self.resolve(options.get("target"))
        if refusal is not None:
            return refusal
        ident_ = p.identity
        requested = bridge._requested_of({"host": "127.0.0.1", "port": ident_["actual_port"],
                                          "pid": ident_["pid"], "session_token": ident_["session_token"]})
        result = self.handle(p, method, path, data or {})
        if isinstance(result, tuple):
            return bridge._uncertain(result[1], "unknown", requested)
        return bridge._received_reply(result, ident_, requested, method)

    @staticmethod
    def _error(p, status, code, text, **extra):
        body = {"error": text, "error_code": code, "process_identity": dict(p.identity)}
        body.update(extra)
        return "Error: {} - {}".format(status, json.dumps(body))

    def _resolve_doc(self, p, selector):
        if selector in p.closed:
            return None, self._error(p, 404, "document-closed",
                                     "The document behind selector {} was closed; no other document was "
                                     "substituted.".format(selector))
        if p.entry(selector) is None:
            return None, self._error(p, 404, "document-token-unknown", "Selector {} was never issued.".format(selector))
        return p.descriptor(selector), None

    def handle(self, p, method, path, data):
        ident_ = dict(p.identity)
        if (method, path) == ("GET", "/status/"):
            if p.active is None:
                return "Error: 503 - " + json.dumps({"error": "No active Revit document", "process_identity": ident_})
            return {"status": "active", "health": "healthy", "document_title": p.entry(p.active)["title"],
                    "process_identity": ident_}
        if (method, path) == ("GET", "/model_info/"):
            return {"status": "success", "document_title": "n/a" if p.active is None else p.entry(p.active)["title"],
                    "levels": 1, "process_identity": ident_}
        if (method, path) == ("GET", "/documents/"):
            documents = [p.descriptor(d["document"]) for d in p.docs]
            return {"status": "success", "process_identity": ident_, "documents": documents,
                    "count": len(documents), "active_document": p.active}
        selector = data.get("document")
        if (method, path) == ("POST", "/document_summary/"):
            descriptor, refusal = self._resolve_doc(p, selector)
            if refusal is not None:
                return refusal
            entry = p.entry(selector)
            return {"status": "success", "document": descriptor, "target_is_active": selector == p.active,
                    "ui_switched": False, "active_before": p.active, "active_after": p.active,
                    "process_identity": ident_,
                    "summary": {"title": entry["title"], "path": entry["path"], "non_type_element_count": 10,
                                "level_count": 1, "project_information": {"name": entry["title"]},
                                "unreadable_fields": []}}
        if (method, path) == ("POST", "/activate_document/"):
            descriptor, refusal = self._resolve_doc(p, selector)
            if refusal is not None:
                return refusal
            if selector == p.active:
                return {"status": "success", "activation": "already-active", "document": descriptor,
                        "observed_active_document": descriptor, "process_identity": ident_}
            if not p.entry(selector)["path"]:
                return self._error(p, 422, "unsaved", "Activation refused (unsaved).", reason="unsaved",
                                   document=descriptor, observed_active_document=p.descriptor(p.active))
            p.active = selector
            descriptor = p.descriptor(selector)
            return {"status": "success", "activation": "activated", "document": descriptor,
                    "observed_active_document": descriptor, "process_identity": ident_}
        if (method, path) == ("POST", "/set_parameter/"):
            return self._set_parameter(p, data, ident_)
        raise AssertionError("unexpected route {} {}".format(method, path))

    def _set_parameter(self, p, data, ident_):
        selector = data.get("document")
        if selector is not None:
            descriptor, refusal = self._resolve_doc(p, selector)
            if refusal is not None:
                return refusal
        else:
            if not p.docs:
                return self._error(p, 503, "no-open-document", "No document is open in this Revit process.")
            if len(p.docs) > 1:
                return self._error(p, 400, "document-selector-required",
                                   "{} documents are open and the call named none.".format(len(p.docs)),
                                   candidates=[p.descriptor(d["document"]) for d in p.docs])
            descriptor = p.descriptor(p.docs[0]["document"])
        if not descriptor["active"]:
            return self._error(p, 412, "document-not-active", "The document is open but is not the active "
                               "document in Revit.", active_document=p.active)
        mode = p.script.pop(0) if p.script else "persist"
        element, name, value = int(data["element_id"]), data["parameter_name"], str(data["value"])
        key = (descriptor["document"], element, name)
        old = p.params.get(key, "")
        body = {"status": "success", "element_id": element, "parameter_name": name, "old_value": old,
                "new_value": value, "transaction_status": "Committed",
                "message": "Set '{}' from '{}' to '{}' on element {}".format(name, old, value, element),
                "document": descriptor, "process_identity": ident_}
        if mode in ("persist", "conflict_persist"):
            p.params[key] = value
        if mode == "unknown":
            return ("unknown", "Error: the request timed out after it was sent; its outcome is unknown.")
        if mode == "rollback":
            return "Error: 409 - " + json.dumps({
                "status": "rolled_back", "element_id": element, "parameter_name": name, "old_value": old,
                "attempted_value": value, "transaction_status": "RolledBack",
                "failures": [{"severity": "Error", "description": "bench rollback"}],
                "message": "Revit rolled the transaction back. The parameter value was NOT changed.",
                "document": descriptor, "process_identity": ident_})
        if mode == "cross" and p.last_body is not None:
            body = dict(p.last_body)
        if mode in ("conflict", "conflict_persist"):
            body["process_identity"] = ident(9999, T4, port=p.identity["actual_port"] + 1)
        if mode not in ("cross",):
            p.last_body = dict(body)
        return body


class AccSession(object):
    def __init__(self, bench):
        self.bench = bench

    async def call_tool(self, name, arguments):
        self.bench.tool_calls.append((name, dict(arguments)))
        text = await self.bench.mcp.tools[name](**arguments)
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=text)])


def install_acc_bench(mp, bench):
    @contextlib.asynccontextmanager
    async def fake_server(port):
        yield AccSession(bench)

    mp.setattr(proc, "_server", fake_server)
    mp.setattr(proc, "collect_listener_owners",
               lambda port: {"port": port, "owners": bench.owners(port), "source": "bridge.listener_snapshot",
                             "at": proc._now()})


def sha_of(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def acc_observe(raw, step, ui, dialog=None, value_seen=None):
    argv = ["phase2-observe", "--in", raw, "--step", step, "--ui", ui]
    if dialog is not None:
        argv += ["--dialog", dialog]
    if value_seen is not None:
        argv += ["--value-seen", value_seen]
    return cmd(*argv)


def acc_start(folder):
    raw = os.path.join(folder, "phase2-acceptance.json")
    assert cmd("phase2-start", "--out", raw) == 0
    return raw


def acc_authorize(raw, flags=ACC_FLAGS):
    for flag in flags:
        assert cmd("phase2-authorize", "--in", raw, "--flag", flag, "--words", USER_WORDS[flag]) == 0


def acc_attach(raw, folder, identity=True, g34=True):
    if identity:
        path = os.path.join(folder, "prior-identity.json")
        with open(path, "wb") as handle:
            handle.write(json.dumps(good_record()).encode("utf-8"))
        assert cmd("phase2-attach", "--in", raw, "--kind", "identity_recheck", "--record", path) == 0
    if g34:
        path = os.path.join(folder, "prior-g34.json")
        with open(path, "wb") as handle:
            handle.write(json.dumps(good_g34_record()).encode("utf-8"))
        assert cmd("phase2-attach", "--in", raw, "--kind", "g34", "--record", path) == 0


def make_copy_files(folder, names=("X", "Y")):
    os.makedirs(os.path.join(folder, "disposable"), exist_ok=True)
    paths = {}
    for name in names:
        paths[name] = os.path.join(folder, "disposable", name + ".rvt")
        with open(paths[name], "wb") as handle:
            handle.write(("model bytes of " + name).encode("ascii"))
    return paths


def flow_g2(raw, mp, folder):
    paths = make_copy_files(folder, ("SAME_A", "SAME_B", "OTHER"))
    p = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    a = p.open_doc("SAME", paths["SAME_A"], active=True)
    p.open_doc("SAME", paths["SAME_B"])
    p.open_doc("Other", paths["OTHER"])
    bench = AccBench(p)
    install_acc_bench(mp, bench)
    assert cmd("g2-list", "--in", raw, "--step", "pair") == 0
    assert acc_observe(raw, "g2:pair", "same-title-confirmed") == 0
    p.close_doc(a)  # the engineer closes document 1 by hand
    assert cmd("g2-list", "--in", raw, "--step", "after_close") == 0
    assert cmd("g2-stale", "--in", raw, "--step", "after_close", "--number", "1") == 0
    assert acc_observe(raw, "g2:after_close", "closed-by-me") == 0
    p.open_doc("SAME", paths["SAME_A"])  # the engineer reopens the same file: a replacement
    assert cmd("g2-list", "--in", raw, "--step", "after_replacement") == 0
    assert cmd("g2-stale", "--in", raw, "--step", "after_replacement", "--number", "1") == 0
    assert acc_observe(raw, "g2:after_replacement", "reopened-by-me") == 0
    return bench


def flow_two(raw, mp):
    p1 = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    p2 = AccProcess(2222, 48885, T2, "doc1.2222aaaaaaaa")
    p1.open_doc("Project1")
    p2.open_doc("Project1")
    bench = AccBench(p1, p2)
    install_acc_bench(mp, bench)
    assert cmd("two-discover", "--in", raw) == 0
    assert cmd("two-default", "--in", raw) == 0
    for which in ("1", "2"):
        assert cmd("two-status", "--in", raw, "--which", which) == 0
        assert cmd("two-list", "--in", raw, "--which", which) == 0
    assert acc_observe(raw, "two:setup", "both-project1") == 0
    assert cmd("two-overlap", "--in", raw) == 0
    return bench


def flow_http(raw, mp):
    p = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    p.open_doc("Alpha", "C:/bench/Alpha.rvt")
    bench = AccBench(p)
    install_acc_bench(mp, bench)
    assert cmd("http-thread", "--in", raw) == 0
    return bench


def flow_mutation(raw, mp, folder):
    paths = make_copy_files(folder, ("X", "Y"))
    p = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    x = p.open_doc("X", paths["X"], active=True)
    y = p.open_doc("Y", paths["Y"])
    bench = AccBench(p)
    install_acc_bench(mp, bench)
    assert cmd("mut-start", "--in", raw, "--disposable", "yes") == 0
    assert cmd("mut-copy", "--in", raw, "--number", "1") == 0
    assert cmd("mut-copy", "--in", raw, "--number", "2") == 0

    def case(name, number=None, observe_ui="unchanged"):
        argv = ["mut-case", "--in", raw, "--case", name, "--element-id", "101", "--param", "Comments",
                "--value", "alpha"]
        if number is not None:
            argv += ["--number", str(number)]
        assert cmd(*argv) == 0, name
        assert acc_observe(raw, "mut:" + name, observe_ui, dialog="none") == 0

    case("active_named", 1)
    case("inactive_412", 2)
    case("many_documents_refused")
    assert cmd("mut-activate", "--in", raw, "--number", "2") == 0
    assert acc_observe(raw, "mut:activation", "target-active", dialog="none") == 0
    case("after_activation", 2)
    p.active = x  # the engineer clicks the other window; no tool does this
    case("after_manual_switch", 1, observe_ui="switched-by-hand")
    p.close_doc(y)  # the engineer closes the second copy
    case("one_document_default")
    assert cmd("mut-finish", "--in", raw) == 0
    return bench


def flow_g6(raw, mp, folder, script=None, overlap_modes=None):
    paths = make_copy_files(folder, ("G6",))
    p = AccProcess(3333, 48884, T3, "doc1.3333aaaaaaaa")
    p.open_doc("G6copy", paths["G6"], active=True)
    p.script = list(script or [])
    bench = AccBench(p)
    install_acc_bench(mp, bench)
    assert cmd("g6-start", "--in", raw, "--disposable", "yes") == 0
    assert cmd("g6-copy", "--in", raw, "--number", "1") == 0
    assert cmd("g6-write", "--in", raw, "--step", "seq1", "--number", "1", "--element-id", "201",
               "--param", "Mark", "--value", "v1") == 0
    assert cmd("g6-write", "--in", raw, "--step", "seq2", "--number", "1", "--element-id", "201",
               "--param", "Mark", "--value", "v2") == 0
    assert cmd("g6-write", "--in", raw, "--step", "seq_readback", "--number", "1") == 0
    assert cmd("g6-overlap", "--in", raw, "--number", "1", "--a", "301:Mark:va", "--b", "302:Mark:vb") == 0
    assert cmd("g6-write", "--in", raw, "--step", "ov_readback_a", "--number", "1") == 0
    assert cmd("g6-write", "--in", raw, "--step", "ov_readback_b", "--number", "1") == 0
    for step in ("seq1", "seq2", "seq_readback", "overlap", "ov_readback_a", "ov_readback_b"):
        assert acc_observe(raw, "g6:" + step, "unchanged", dialog="none") == 0
    assert cmd("g6-finish", "--in", raw) == 0
    return bench


def flow_collision(raw, mp):
    p = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    p.open_doc("Alpha", "C:/bench/Alpha.rvt")
    bench = AccBench(p)
    bench.collision[48991] = [3333, 4444]
    install_acc_bench(mp, bench)
    assert cmd("collision-probe", "--in", raw, "--port", "48991", "--setup-kind", "auxiliary-routes-server",
               "--setup-method", "temporary pyRevit RoutesServer in two Revit PIDs via the diagnostic button") == 0
    assert acc_observe(raw, "collision:setup", "collision-created", dialog="none") == 0
    bench.collision.clear()  # the engineer tears the temporary servers down
    assert cmd("collision-after", "--in", raw, "--port", "48991") == 0
    assert acc_observe(raw, "collision:cleanup", "collision-removed", dialog="none") == 0
    return bench


def build_acc(folder, mp, sections=("g2", "two", "http", "mutation", "g6", "collision"),
              flags=ACC_FLAGS, attach=True, g6_script=None):
    raw = acc_start(folder)
    acc_authorize(raw, flags)
    if attach:
        acc_attach(raw, folder)
    if "g2" in sections:
        flow_g2(raw, mp, folder)
    if "two" in sections:
        flow_two(raw, mp)
    if "http" in sections:
        flow_http(raw, mp)
    if "mutation" in sections:
        flow_mutation(raw, mp, folder)
    if "g6" in sections:
        flow_g6(raw, mp, folder, script=g6_script)
    if "collision" in sections:
        flow_collision(raw, mp)
    return raw


@functools.lru_cache(maxsize=1)
def _good_acc_json():
    with pytest.MonkeyPatch.context() as mp:
        with tempfile.TemporaryDirectory() as folder:
            raw = build_acc(folder, mp)
            with open(raw, "rb") as handle:
                return handle.read().decode("utf-8")


def good_acc_record():
    return json.loads(_good_acc_json())


@pytest.fixture
def acc_dir(tmp_path, monkeypatch):
    return str(tmp_path), monkeypatch


# ---------------------------------------------------------------- the classifier: good record and table shape


def acc_result(record):
    return proc.classify_phase2_acceptance(record)


def has_code(slot, code):
    return any(code in reason for reason in slot["reasons"])


def test_the_acceptance_constants_name_nine_criteria_six_gates_and_three_authorizations():
    assert proc.ACC_SCHEMA == "phase2-acceptance-v1"
    assert proc.CRITERIA == ("c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9")
    assert proc.GATES == ("g1", "g2", "g3", "g4", "g5", "g6")
    assert proc.AUTH_FLAGS == ACC_FLAGS
    assert set(proc.CRITERION_TEXT) == set(proc.CRITERIA)
    assert proc.ACCEPT_ELIGIBLE == "accept-eligible"


def test_the_good_acceptance_record_is_accept_eligible_with_every_slot_observed_and_no_approval():
    result = acc_result(good_acc_record())
    assert result["verdict"] == proc.ACCEPT_ELIGIBLE, result["reasons"] + [
        (u, s["reasons"]) for u, s in result["units"].items() if s["status"] != "observed"]
    assert result["approval"] == "not-granted"
    assert result["reasons"] == [] and result["open"] == []
    for criterion in proc.CRITERIA:
        assert result["criteria"][criterion]["status"] == "observed", criterion
    for gate in proc.GATES:
        assert result["gates"][gate]["status"] == "observed", gate
    assert result["authorizations"] == dict((flag, "authorized") for flag in ACC_FLAGS)
    assert "approv" not in result["verdict"]


def test_the_good_record_g6_hypothesis_is_ruled_out_from_matching_identities():
    result = acc_result(good_acc_record())
    assert result["g6"]["hypothesis"] == "ruled-out"
    assert result["g6"]["observations"]["identity_mismatch"] is False
    assert result["g6"]["observations"]["unknown_outcome"] is False


def test_the_auxiliary_collision_is_qualified_as_not_primary_port_assignment_evidence():
    result = acc_result(good_acc_record())
    assert result["gates"]["g5"]["status"] == "observed"
    assert any("primary-port" in q for q in result["qualifications"])


def test_the_template_is_stop_with_every_slot_not_run_and_g6_named_open():
    template = proc.acceptance_template()
    assert template["schema"] == proc.ACC_SCHEMA and template["live"] is None
    assert all(template["authorizations"][flag] is None for flag in ACC_FLAGS)
    result = acc_result(template)
    assert result["verdict"] == proc.STOP
    assert all(result["criteria"][c]["status"] == "not-run" for c in proc.CRITERIA)
    assert any("AMBIG-04" in line for line in result["open"])


@pytest.mark.parametrize("junk", [None, [], "x", 0, {}, b"bytes", 1.5, object(), {"live": True}])
def test_the_acceptance_classifier_never_raises_and_is_stop_on_junk(junk):
    result = acc_result(junk)
    assert result["verdict"] == proc.STOP and result["approval"] == "not-granted"


def test_the_acceptance_classifier_internal_error_reads_as_stop(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("bug")

    monkeypatch.setattr(proc, "_acc_evaluate", boom)
    result = acc_result(good_acc_record())
    assert result["verdict"] == proc.STOP and any("classifier-error" in r for r in result["reasons"])


# ---------------------------------------------------------------- STOP cases on the good record


def _append_call(**fields):
    call = {"method": "GET", "route": "/status/", "tool": "get_revit_status", "section": "g2",
            "step": "x", "at": "2026-10-23T10:00:00+00:00"}
    call.update(fields)

    def mutate(rec):
        rec["sent_calls"].append(dict(call))
    return mutate


def _doc_list(rec, step):
    return rec["g2"]["steps"][step]["documents"]


def _after_close_lists_the_stale_token(rec):
    rec["g2"]["steps"]["after_close"]["documents"] = copy.deepcopy(_doc_list(rec, "pair"))


def _survivor_lost(rec):
    rec["g2"]["steps"]["after_close"]["documents"] = [
        d for d in _doc_list(rec, "after_close") if d["title"] != "SAME"]


def _replacement_missing(rec):
    rec["g2"]["steps"]["after_replacement"]["documents"] = copy.deepcopy(_doc_list(rec, "after_close"))


def _replacement_reuses_the_closed_token(rec):
    stale = rec["g2"]["stale"]["after_close"]["stale_token"]
    for d in _doc_list(rec, "after_replacement"):
        if d["title"] == "SAME" and d["path"] == rec["g2"]["stale"]["after_close"]["closed_path"]:
            d["document"] = stale


def _no_pair(rec):
    _doc_list(rec, "pair")[1]["title"] = "Other2"


def _copies_of(rec, section):
    return [c for c in rec["copies"] if c["section"] == section]


def _drop_copies(section):
    def mutate(rec):
        rec["copies"] = [c for c in rec["copies"] if c["section"] != section]
    return mutate


def _set_copy(section, key, value):
    def mutate(rec):
        for c in _copies_of(rec, section):
            c[key] = value
    return mutate


def _two_discovery_one_usable(rec):
    rec["two"]["discovery"]["usable"] = rec["two"]["discovery"]["usable"][:1]


def _two_collision_listed(rec):
    rec["two"]["discovery"]["unusable"].append({"port": 48991, "pids": [1, 2], "reason": "listener-collision"})


def _two_swap_status(rec):
    rec["two"]["status"]["1"]["identity"] = copy.deepcopy(rec["two"]["status"]["2"]["identity"])


def _two_same_listing_identity(rec):
    rec["two"]["list"]["2"]["identity"] = copy.deepcopy(rec["two"]["list"]["1"]["identity"])


def _two_no_project1(rec):
    rec["two"]["list"]["1"]["documents"][0]["title"] = "Alpha"


def _mutation_other_doc_named(rec):
    entry = rec["mutation"]["cases"]["active_named"]
    others = [d["document"] for d in entry["before_listing"]["documents"]
              if d["document"] != entry["reply"]["document"]]
    entry["reply"]["document"] = others[0]


def _many_candidates_short(rec):
    reply = rec["mutation"]["cases"]["many_documents_refused"]["reply"]
    reply["candidates"] = reply["candidates"][:1]


def _inactive_active_changed(rec):
    entry = rec["mutation"]["cases"]["inactive_412"]
    other = [d["document"] for d in entry["after_listing"]["documents"] if not d["active"]][0]
    for d in entry["after_listing"]["documents"]:
        d["active"] = d["document"] == other
    entry["after_listing"]["active_document"] = other


def _switch_not_observed(rec):
    entry = rec["mutation"]["cases"]["after_manual_switch"]
    entry["previous_active"] = entry["before_listing"]["active_document"]


def _activation_other_target(rec):
    rec["mutation"]["activation"]["reply"]["document"] = \
        rec["mutation"]["cases"]["active_named"]["request"]["document"]


def _labelled_unknown(node_of):
    """A timed-out write whose rendered text still credits a verified process or document."""
    def mutate(rec):
        node_of(rec)["reply"].update(kind="unknown", credits=True, http_status=None)
    return mutate


def _collision(rec):
    return rec["collision"]["probe"]


def _collision_inventory(key, value):
    def mutate(rec):
        _collision(rec)["inventory"][key] = value
    return mutate


def _collision_add_usable(rec):
    _collision(rec)["discovery"]["usable"].append(
        {"selector": "revit1:x", "pid": 3333, "port": 48991, "session_token": T3, "revit_version": "2024",
         "document_open": True})


def _update(path, **fields):
    def mutate(rec):
        node = rec
        for key in path:
            node = node[key]
        node.update(fields)
    return mutate


NO_AUTH = {"value": False, "at": None, "words": None, "source": None}


def _edit_selected(rec):
    rec["collision"]["probe"]["selected"] = {"refused": False, "credits": True, "pids": [], "text": "x"}


# (label, mutate, unit that must be stop, code that must be named; unit "global" = record-level reasons)
ACC_STOP_CASES = [
    ("synthetic", _set(["synthetic"], True), "global", "synthetic"),
    ("not-live", _set(["live"], False), "global", "not-live"),
    ("live-missing", _drop(["live"]), "global", "not-live"),
    ("schema", _set(["schema"], "other-v1"), "global", "schema-mismatch"),
    ("execute-code-route", _append_call(method="POST", route="/execute_code/", tool="execute_revit_code",
                                        section="mutation"), "global", "route-not-allowed"),
    ("execute-tool-in-a-read-section", _append_call(method="POST", route="/execute_code/",
                                                    tool="execute_revit_code", section="g2"),
     "global", "route-not-allowed"),
    ("mutation-tool-in-a-read-section", _append_call(method="POST", route="/set_parameter/",
                                                     tool="set_parameter", section="g2"),
     "global", "route-not-allowed"),
    ("activation-in-g6", _append_call(method="POST", route="/activate_document/", tool="activate_document",
                                      section="g6"), "global", "route-not-allowed"),
    ("route-of-another-tool", _append_call(route="/delete_elements/"), "global", "route-not-allowed"),
    ("unknown-section", _append_call(section="elsewhere"), "global", "route-not-allowed"),
    ("no-sent-calls", _set(["sent_calls"], []), "global", "sent-calls-unrecorded"),
    # authorization policy
    ("mutation-flag-false-with-data", _set(["authorizations", "mutation_authorized"], dict(NO_AUTH)),
     "mut_c2", "section-without-authorization"),
    ("mutation-flag-none-with-data", _set(["authorizations", "mutation_authorized"], None),
     "mut_c8", "section-without-authorization"),
    ("mutation-flag-none-hits-c6", _set(["authorizations", "mutation_authorized"], None),
     "mut_c6", "section-without-authorization"),
    ("g6-flag-false-with-data", _set(["authorizations", "g6_authorized"], dict(NO_AUTH)),
     "g6", "section-without-authorization"),
    ("g6-flag-missing-with-data", _drop(["authorizations", "g6_authorized"]), "g6",
     "section-without-authorization"),
    ("collision-flag-none-with-data", _set(["authorizations", "collision_authorized"], None),
     "g5", "section-without-authorization"),
    ("bare-true-flag", _set(["authorizations", "g6_authorized"], True), "g6", "authorization-malformed"),
    ("flag-without-words", _set(["authorizations", "mutation_authorized", "words"], "  "),
     "mut_c2", "authorization-malformed"),
    ("flag-with-naive-time", _set(["authorizations", "collision_authorized", "at"], "2026-10-23T10:00:00"),
     "g5", "authorization-malformed"),
    ("flag-set-by-something-else", _set(["authorizations", "g6_authorized", "source"], "default"),
     "g6", "authorization-malformed"),
    ("flag-given-after-the-first-send", _set(["authorizations", "mutation_authorized", "at"],
                                             "2999-01-01T00:00:00+00:00"), "mut_c2", "authorization-after-send"),
    ("g6-flag-given-after-the-first-send", _set(["authorizations", "g6_authorized", "at"],
                                                "2999-01-01T00:00:00+00:00"), "g6", "authorization-after-send"),
    # prior records (G1, G3, G4)
    ("identity-record-not-live", _set(["prior", "identity_recheck", "record", "live"], False), "g1", "not-live"),
    ("g3-engineer-saw-the-window-change",
     _set(["prior", "g34", "record", "g3", "slots", "a_active_b_read", "engineer", "ui"], "changed"),
     "g3", "engineer-ui-changed"),
    ("saved-workshared-activation-attempt",
     _set(["prior", "g34", "record", "g4", "cases", "saved_workshared", "expect"], "allow"),
     "g4", "workshared-activation-attempt"),
    ("saved-workshared-was-activated",
     _update(["prior", "g34", "record", "g4", "cases", "saved_workshared", "reply"], kind="success",
             activation="activated"),
     "g4", "workshared-activation-attempt"),
    ("prior-g34-synthetic", _set(["prior", "g34", "record", "synthetic"], True), "g4", "synthetic"),
    # G2
    ("g2-process-without-identity", _drop(["g2", "process", "identity"]), "g2", "g2-process-unverified"),
    ("g2-port-has-two-owners", _set(["g2", "process", "listener", "owners"], [1111, 4242]), "g2",
     "g2-process-unverified"),
    ("g2-pair-listing-unusable", _set(["g2", "steps", "pair", "ok"], False), "g2", "g2-listing-unusable"),
    ("g2-no-same-title-pair", _no_pair, "g2", "g2-no-same-title-pair"),
    ("g2-stale-token-not-from-the-pair", _set(["g2", "stale", "after_close", "from_index"], 3), "g2",
     "g2-stale-not-from-pair"),
    ("g2-closed-token-still-listed", _after_close_lists_the_stale_token, "g2", "g2-closed-token-listed"),
    ("g2-survivor-lost", _survivor_lost, "g2", "g2-survivor-lost"),
    ("g2-stale-read-answered", _set(["g2", "stale", "after_close", "reply", "kind"], "ok"), "g2",
     "g2-stale-read-answered"),
    ("g2-stale-read-accepted-after-replacement",
     _set(["g2", "stale", "after_replacement", "reply", "kind"], "ok"), "g2", "g2-stale-read-answered"),
    ("g2-refusal-not-the-named-close", _set(["g2", "stale", "after_close", "reply", "error_code"],
                                            "document-token-unknown"), "g2", "g2-stale-refusal-unnamed"),
    ("g2-replacement-missing", _replacement_missing, "g2", "g2-replacement-missing"),
    ("g2-replacement-reuses-the-token", _replacement_reuses_the_closed_token, "g2",
     "g2-replacement-token-reused"),
    ("g2-engineer-unobserved", _drop(["engineer", "g2:after_close"]), "g2", "g2-engineer-unobserved"),
    ("g2-listing-from-another-process",
     _set(["g2", "steps", "pair", "identity"], ident(7777, T4)), "g2", "g2-identity-mismatch"),
    # two processes
    ("two-single-usable-process", _two_discovery_one_usable, "two", "two-not-two-processes"),
    ("two-collision-in-the-window", _two_collision_listed, "two", "two-collision-listed"),
    ("two-default-was-answered", _set(["two", "default", "refused"], False), "two", "two-default-not-refused"),
    ("two-default-credits-a-process", _set(["two", "default", "credits"], True), "two",
     "two-default-not-refused"),
    ("two-status-names-the-other-process", _two_swap_status, "two", "two-status-identity-mismatch"),
    ("two-listings-share-an-answering-process", _two_same_listing_identity, "two", "two-identities-equal"),
    ("two-no-project1", _two_no_project1, "two", "two-no-project1"),
    ("two-port-not-sole-owner", _set(["two", "listeners", "1", "owners"], [1111, 5]), "two",
     "two-listener-not-sole"),
    ("two-engineer-unobserved", _drop(["engineer", "two:setup"]), "two", "two-engineer-unobserved"),
    # mutation
    ("mutation-disposable-unattested", _set(["mutation", "disposable"], None), "mut_c2",
     "mutation-disposable-unattested"),
    ("mutation-process-has-two-owners", _set(["mutation", "process", "listener", "owners"], [1111, 2]),
     "mut_c8", "mutation-process-unverified"),
    ("mutation-copies-unregistered", _drop_copies("mutation"), "mut_c2", "mutation-copy-unregistered"),
    ("mutation-copy-hash-missing", _set_copy("mutation", "sha256_after", None), "mut_c6",
     "mutation-copy-hash-missing"),
    ("mutation-copy-file-changed", _set_copy("mutation", "sha256_after", "0" * 64), "mut_c8",
     "mutation-copy-file-changed"),
    ("mutation-active-named-names-another-document", _mutation_other_doc_named, "mut_c2",
     "mutation-document-not-named"),
    ("mutation-active-named-not-a-success",
     _set(["mutation", "cases", "active_named", "reply", "kind"], "refused"), "mut_c2",
     "mutation-reply-unexpected"),
    ("mutation-inactive-was-not-412", _set(["mutation", "cases", "inactive_412", "reply", "http_status"], 200),
     "mut_c6", "mutation-reply-unexpected"),
    ("mutation-inactive-wrong-code", _set(["mutation", "cases", "inactive_412", "reply", "error_code"],
                                          "document-closed"), "mut_c6", "mutation-reply-unexpected"),
    ("mutation-inactive-changed-the-active-document", _inactive_active_changed, "mut_c6",
     "mutation-active-changed"),
    ("mutation-many-candidates-incomplete", _many_candidates_short, "mut_c8", "mutation-candidates-incomplete"),
    ("mutation-many-refusal-became-success",
     _set(["mutation", "cases", "many_documents_refused", "reply", "kind"], "success"), "mut_c8",
     "mutation-reply-unexpected"),
    ("mutation-default-case-sent-a-selector",
     _set(["mutation", "cases", "one_document_default", "request", "document"], "doc1.1111aaaaaaaa.1"),
     "mut_c8", "mutation-case-malformed"),
    ("mutation-send-count", _append_call(method="POST", route="/set_parameter/", tool="set_parameter",
                                         section="mutation", step="mut:active_named"), "mut_c2",
     "mutation-send-count"),
    ("mutation-answered-by-another-process",
     _set(["mutation", "cases", "active_named", "reply", "identity"], ident(7777, T4)), "mut_c2",
     "mutation-identity-mismatch"),
    ("mutation-listing-unusable", _set(["mutation", "cases", "active_named", "before_listing", "ok"], False),
     "mut_c2", "mutation-listing-unusable"),
    ("mutation-activation-missing", _drop(["mutation", "activation"]), "mut_c2", "mutation-activation-missing"),
    ("mutation-activation-of-another-document", _activation_other_target, "mut_c2",
     "mutation-activation-missing"),
    ("mutation-manual-switch-not-observed", _switch_not_observed, "mut_c2", "mutation-switch-not-observed"),
    ("mutation-manual-switch-without-previous", _drop(["mutation", "cases", "after_manual_switch",
                                                       "previous_active"]), "mut_c2",
     "mutation-switch-not-observed"),
    ("mutation-engineer-unobserved", _drop(["engineer", "mut:active_named"]), "mut_c2",
     "mutation-engineer-unobserved"),
    ("mutation-engineer-saw-a-dialog", _set(["engineer", "mut:inactive_412", "dialog_required_input"], True),
     "mut_c6", "mutation-dialog-required-input"),
    ("mutation-dialog-unrecorded", _set(["engineer", "mut:one_document_default", "dialog_required_input"],
                                        None), "mut_c8", "mutation-engineer-unobserved"),
    ("mutation-engineer-ui-unexpected", _set(["engineer", "mut:after_manual_switch", "ui"], "unchanged"),
     "mut_c2", "mutation-engineer-unexpected"),
    ("mutation-timed-out-write-labelled-verified",
     _labelled_unknown(lambda rec: rec["mutation"]["cases"]["after_activation"]), "mut_c2",
     "mutation-unknown-labelled-verified"),
    # collision
    ("collision-unknown-setup-kind", _set(["collision", "probe", "setup_kind"], "magic"), "g5",
     "collision-setup-unrecorded"),
    ("collision-blank-setup-method", _set(["collision", "probe", "setup_method"], " "), "g5",
     "collision-setup-unrecorded"),
    ("collision-inventory-from-get-nettcpconnection", _collision_inventory("source", "Get-NetTCPConnection"),
     "g5", "collision-inventory-not-netstat"),
    ("collision-inventory-method-not-netstat", _collision_inventory("method", "engineer-typed"), "g5",
     "collision-inventory-not-netstat"),
    ("collision-single-owner", _collision_inventory("owners", [3333]), "g5", "collision-not-a-collision"),
    ("collision-duplicate-owner-rows", _collision_inventory("owners", [3333, 3333]), "g5",
     "collision-inventory-malformed"),
    ("collision-inventory-other-port", _collision_inventory("port", 48884), "g5",
     "collision-inventory-malformed"),
    ("collision-discovery-misses-a-pid", _set(["collision", "probe", "discovery", "unusable", 0, "pids"], [3333]),
     "g5", "collision-pid-unnamed"),
    ("collision-discovery-offers-a-target", _collision_add_usable, "g5", "collision-discovery-offered-target"),
    ("collision-default-was-answered", _set(["collision", "probe", "default", "refused"], False), "g5",
     "collision-default-not-refused"),
    ("collision-default-names-one-pid", _set(["collision", "probe", "default", "pids"], [3333]), "g5",
     "collision-pid-unnamed"),
    ("collision-default-credits-a-process", _set(["collision", "probe", "default", "credits"], True), "g5",
     "collision-request-sent"),
    ("collision-still-present-after-teardown", _set(["collision", "after", "inventory", "owners"], [3333, 4444]),
     "g5", "collision-cleanup-incomplete"),
    ("collision-cleanup-from-another-source", _set(["collision", "after", "inventory", "source"], "typed"),
     "g5", "collision-inventory-not-netstat"),
    ("collision-engineer-unobserved", _drop(["engineer", "collision:setup"]), "g5",
     "collision-engineer-unobserved"),
    # G6
    ("g6-disposable-unattested", _set(["g6", "disposable"], None), "g6", "g6-disposable-unattested"),
    ("g6-process-has-two-owners", _set(["g6", "process", "listener", "owners"], [3333, 4]), "g6",
     "g6-process-unverified"),
    ("g6-copies-unregistered", _drop_copies("g6"), "g6", "g6-copy-unregistered"),
    ("g6-copy-file-changed", _set_copy("g6", "sha256_after", "f" * 64), "g6", "g6-copy-file-changed"),
    ("g6-copy-hash-missing", _set_copy("g6", "sha256_before", None), "g6", "g6-copy-hash-missing"),
    ("g6-timed-out-write-labelled-verified",
     _labelled_unknown(lambda rec: rec["g6"]["steps"]["seq1"]), "g6", "g6-unknown-labelled-verified"),
    ("g6-write-refused", _update(["g6", "steps", "seq2", "reply"], kind="refused", http_status=412),
     "g6", "g6-reply-unexpected"),
    ("g6-overlap-read-unusable", _set(["g6", "overlap", "jobs", "read", "reply", "ok"], False), "g6",
     "g6-listing-unusable"),
    ("g6-engineer-unobserved", _drop(["engineer", "g6:seq1"]), "g6", "g6-engineer-unobserved"),
    ("g6-engineer-saw-a-dialog", _set(["engineer", "g6:overlap", "dialog_required_input"], True), "g6",
     "g6-dialog-required-input"),
    ("g6-step-sent-twice", _append_call(method="POST", route="/set_parameter/", tool="set_parameter",
                                        section="g6", step="g6:seq1"), "g6", "g6-send-count"),
    # the remaining declared codes: another engineer word, an unusable capture, a refusal that was sent
    ("g2-engineer-saw-something-else", _set(["engineer", "g2:after_close", "ui"], "unchanged"), "g2",
     "g2-engineer-unexpected"),
    ("two-engineer-saw-something-else", _set(["engineer", "two:setup", "ui"], "unchanged"), "two",
     "two-engineer-unexpected"),
    ("collision-engineer-saw-something-else", _set(["engineer", "collision:setup", "ui"], "unchanged"), "g5",
     "collision-engineer-unexpected"),
    ("collision-engineer-saw-a-dialog", _set(["engineer", "collision:cleanup", "dialog_required_input"], True),
     "g5", "collision-dialog-required-input"),
    ("g6-engineer-saw-something-else", _set(["engineer", "g6:seq2", "ui"], "changed"), "g6",
     "g6-engineer-unexpected"),
    ("two-discovery-reply-incomplete", _set(["two", "discovery", "ok"], False), "two", "two-discovery-incomplete"),
    ("two-list-unusable", _set(["two", "list", "2", "ok"], False), "two", "two-list-unusable"),
    ("collision-selected-call-was-not-refused",
     _edit_selected, "g5", "collision-selected-not-refused"),
]


@pytest.mark.parametrize("label,mutate,unit,code", ACC_STOP_CASES, ids=[c[0] for c in ACC_STOP_CASES])
def test_acceptance_stop_reason_is_named(label, mutate, unit, code):
    rec = good_acc_record()
    mutate(rec)
    result = acc_result(rec)
    assert result["verdict"] == proc.STOP, (label, result["verdict"])
    assert result["approval"] == "not-granted"
    if unit == "global":
        assert any(code in reason for reason in result["reasons"]), (label, result["reasons"])
    else:
        slot = result["units"][unit]
        assert slot["status"] == "stop", (label, unit, slot)
        assert has_code(slot, code), (label, code, slot["reasons"])
        # a STOP in any unit keeps every criterion built from it out of the accepted set
        assert any(result["criteria"][c]["status"] == "stop" for c in proc.CRITERIA)


def test_every_declared_acceptance_reason_code_has_a_stop_case():
    declared = set(proc.ACC_REASON_CODES)
    covered = set(code for _l, _m, _u, code in ACC_STOP_CASES)
    assert declared - covered <= {"classifier-error", "no-record", "prior-missing", "unit-incomplete",
                                  "prior-malformed", "g6-inconclusive"}, sorted(declared - covered)
    assert covered <= declared, sorted(covered - declared)


def test_the_acceptance_classifier_only_ever_returns_stop_or_accept_eligible():
    seen = set()
    for _l, mutate, _u, _c in ACC_STOP_CASES:
        rec = good_acc_record()
        mutate(rec)
        seen.add(acc_result(rec)["verdict"])
    assert seen == {proc.STOP}
    assert acc_result(good_acc_record())["verdict"] == proc.ACCEPT_ELIGIBLE


# ---------------------------------------------------------------- not-run and unauthorized sections


@pytest.mark.parametrize("flags,section_units,criteria", [
    (("g6_authorized", "collision_authorized"), ("mut_c2", "mut_c6", "mut_c8"), ("c2", "c6", "c8")),
    (("mutation_authorized", "collision_authorized"), ("g6",), ("c5",)),
    (("mutation_authorized", "g6_authorized"), ("g5",), ("c4",)),
    ((), ("mut_c2", "mut_c6", "mut_c8", "g6", "g5"), ("c2", "c4", "c5", "c6", "c8")),
])
def test_an_authorization_flag_left_unset_makes_its_sections_not_run_and_the_verdict_stop(
        tmp_path, monkeypatch, flags, section_units, criteria):
    sections = [s for s, flag in (("mutation", "mutation_authorized"), ("g6", "g6_authorized"),
                                  ("collision", "collision_authorized")) if flag in flags]
    raw = build_acc(str(tmp_path), monkeypatch, sections=("g2", "two", "http") + tuple(sections), flags=flags)
    result = acc_result(load(raw))
    assert result["verdict"] == proc.STOP
    for unit in section_units:
        assert result["units"][unit]["status"] == "not-run", unit
    for criterion in criteria:
        assert result["criteria"][criterion]["status"] != "observed"
    for flag in ACC_FLAGS:
        assert result["authorizations"][flag] == ("authorized" if flag in flags else "not-authorized")
    assert not result["reasons"], result["reasons"]  # not-run is not a policy violation
    assert result["criteria"]["c1"]["status"] == "observed" and result["criteria"]["c3"]["status"] == "observed"


def test_g6_not_run_keeps_the_verdict_at_stop_and_names_ambig_04():
    with pytest.MonkeyPatch.context() as mp, tempfile.TemporaryDirectory() as folder:
        raw = build_acc(folder, mp, sections=("g2", "two", "http", "mutation", "collision"),
                        flags=("mutation_authorized", "collision_authorized"))
        result = acc_result(load(raw))
    assert result["verdict"] == proc.STOP
    assert result["gates"]["g6"]["status"] == "not-run"
    assert any("AMBIG-04" in line and "G6" in line for line in result["open"])
    assert result["g6"]["hypothesis"] is None


def test_without_any_prior_record_g1_g3_g4_are_not_run_not_a_pass(tmp_path, monkeypatch):
    raw = build_acc(str(tmp_path), monkeypatch, attach=False)
    result = acc_result(load(raw))
    assert result["verdict"] == proc.STOP
    for gate in ("g1", "g3", "g4"):
        assert result["gates"][gate]["status"] == "not-run"
    assert result["criteria"]["c1"]["status"] == "not-run" and result["criteria"]["c7"]["status"] == "not-run"


@pytest.mark.parametrize("section", ["g2", "two", "mutation", "g6", "collision"])
def test_a_section_never_captured_is_not_run(section):
    rec = good_acc_record()
    rec[section] = {}
    rec["sent_calls"] = [c for c in rec["sent_calls"] if c["section"] != section]
    rec["copies"] = [c for c in rec["copies"] if c["section"] != section]
    result = acc_result(rec)
    unit = {"g2": "g2", "two": "two", "mutation": "mut_c2", "g6": "g6", "collision": "g5"}[section]
    assert result["units"][unit]["status"] == "not-run"
    assert result["verdict"] == proc.STOP


@pytest.mark.parametrize("case,unit", [("active_named", "mut_c2"), ("after_activation", "mut_c2"),
                                       ("after_manual_switch", "mut_c2"), ("inactive_412", "mut_c6"),
                                       ("one_document_default", "mut_c8"), ("many_documents_refused", "mut_c8")])
def test_a_mutation_case_not_captured_is_not_run_never_a_pass(case, unit):
    rec = good_acc_record()
    del rec["mutation"]["cases"][case]
    rec["sent_calls"] = [c for c in rec["sent_calls"] if c.get("step") != "mut:" + case]
    result = acc_result(rec)
    assert result["units"][unit]["status"] == "not-run", result["units"][unit]
    assert result["verdict"] == proc.STOP


@pytest.mark.parametrize("path", [["collision", "after"], ["g2", "steps", "after_replacement"],
                                  ["two", "list", "2"], ["g6", "steps", "ov_readback_b"], ["g6", "final"]])
def test_a_missing_required_capture_is_not_run_not_accepted(path):
    rec = good_acc_record()
    _drop(path)(rec)
    result = acc_result(rec)
    assert result["verdict"] == proc.STOP
    assert any(s["status"] == "not-run" for s in result["units"].values()), path


def test_a_removed_http_thread_capture_does_not_block_acceptance_it_is_informational():
    rec = good_acc_record()
    rec["http_thread"] = {}
    rec["sent_calls"] = [c for c in rec["sent_calls"] if c["section"] != "http_thread"]
    result = acc_result(rec)
    assert result["verdict"] == proc.ACCEPT_ELIGIBLE
    assert result["informational"]["http_thread"]["status"] == "not-run"


def test_the_collision_through_a_second_revit_on_the_primary_port_has_no_qualification():
    rec = good_acc_record()
    rec["collision"]["probe"]["setup_kind"] = "second-revit-primary-port"
    result = acc_result(rec)
    assert result["gates"]["g5"]["status"] == "observed"
    assert not any("primary-port" in q for q in result["qualifications"])


def test_a_non_ascii_authorization_wording_is_kept_verbatim():
    rec = good_acc_record()
    words = "Разрешаю G6 на копии модели, без сохранения и синхронизации"
    rec["authorizations"]["g6_authorized"]["words"] = words
    assert acc_result(rec)["verdict"] == proc.ACCEPT_ELIGIBLE
    assert json.loads(json.dumps(rec))["authorizations"]["g6_authorized"]["words"] == words


# ---------------------------------------------------------------- G6: the hypothesis is classified from evidence only
# set_parameter call order of flow_g6: seq1, seq2, seq_readback, overlap a, overlap b, ov_readback_a, ov_readback_b


def g6_result(tmp_path, monkeypatch, script):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("g6_authorized",))
    flow_g6(raw, monkeypatch, str(tmp_path), script=script)
    return acc_result(load(raw)), load(raw)


def test_a_silently_lost_write_with_matching_identities_rules_the_wrong_process_hypothesis_out(
        tmp_path, monkeypatch):
    result, rec = g6_result(tmp_path, monkeypatch, ["lose"])
    assert result["g6"]["hypothesis"] == "ruled-out"
    assert result["g6"]["observations"]["sequential_loss"] is True
    assert result["g6"]["observations"]["identity_mismatch"] is False
    assert result["gates"]["g6"]["status"] == "observed"
    assert rec["g6"]["steps"]["seq1"]["reply"]["kind"] == "success"  # the reply said success; the model did not change


def test_a_rolled_back_write_is_recorded_as_a_rollback_with_the_raw_409_and_rules_the_hypothesis_out(
        tmp_path, monkeypatch):
    result, rec = g6_result(tmp_path, monkeypatch, ["rollback"])
    reply = rec["g6"]["steps"]["seq1"]["reply"]
    assert reply["kind"] == "rolled-back" and reply["http_status"] == 409
    assert reply["transaction_status"] == "RolledBack" and "Error: 409" in reply["text"]
    assert result["g6"]["observations"]["rolled_back"] is True
    assert result["g6"]["hypothesis"] == "ruled-out"


def test_an_outcome_unknown_write_is_inconclusive_never_confirmed_or_ruled_out(tmp_path, monkeypatch):
    result, rec = g6_result(tmp_path, monkeypatch, ["unknown"])
    reply = rec["g6"]["steps"]["seq1"]["reply"]
    assert reply["kind"] == "unknown" and reply["credits"] is False
    assert result["g6"]["hypothesis"] == "inconclusive"
    assert result["g6"]["observations"]["unknown_outcome"] is True
    assert result["gates"]["g6"]["status"] == "stop" and has_code(result["gates"]["g6"], "g6-inconclusive")
    assert result["criteria"]["c5"]["status"] == "stop"
    assert result["verdict"] == proc.STOP
    assert any("AMBIG-04" in line for line in result["open"])


def test_a_measured_different_process_with_a_lost_write_confirms_the_hypothesis(tmp_path, monkeypatch):
    result, rec = g6_result(tmp_path, monkeypatch, ["conflict"])
    reply = rec["g6"]["steps"]["seq1"]["reply"]
    assert reply["kind"] == "conflict" and reply["named_pid"] == 9999
    assert result["g6"]["observations"]["identity_mismatch"] is True
    assert result["g6"]["hypothesis"] == "confirmed"
    assert result["gates"]["g6"]["status"] == "observed"


def test_a_conflicting_reply_whose_write_persisted_is_inconclusive_not_confirmed(tmp_path, monkeypatch):
    result, _rec = g6_result(tmp_path, monkeypatch, ["conflict_persist"])
    assert result["g6"]["observations"]["identity_mismatch"] is True
    assert result["g6"]["hypothesis"] == "inconclusive"
    assert result["gates"]["g6"]["status"] == "stop"


def test_a_cross_wired_overlapped_reply_is_recorded_without_blaming_another_process(tmp_path, monkeypatch):
    result, rec = g6_result(tmp_path, monkeypatch, ["persist", "persist", "persist", "persist", "cross"])
    assert result["g6"]["observations"]["cross_wired"] is True
    assert result["g6"]["observations"]["overlap_loss"] is True
    assert result["g6"]["observations"]["identity_mismatch"] is False
    assert result["g6"]["hypothesis"] == "ruled-out"
    assert any("999.1" in q for q in result["qualifications"])  # per-process locks do not cover cross-session overlap


def test_the_overlap_runs_three_concurrent_sessions_each_bound_to_the_verified_process(tmp_path, monkeypatch):
    _result, rec = g6_result(tmp_path, monkeypatch, None)
    jobs = rec["g6"]["overlap"]["jobs"]
    assert set(jobs) == {"a", "b", "read"}
    assert jobs["a"]["tool"] == jobs["b"]["tool"] == "set_parameter" and jobs["read"]["tool"] == "list_documents"
    identity = rec["g6"]["process"]["identity"]
    for job in jobs.values():
        assert job["identity_bound"] == identity and job["started_at"] and job["finished_at"]
    assert (jobs["a"]["request"]["element_id"], jobs["a"]["request"]["parameter_name"]) != (
        jobs["b"]["request"]["element_id"], jobs["b"]["request"]["parameter_name"])


def test_the_g6_readbacks_use_the_chained_old_value_of_a_following_write(tmp_path, monkeypatch):
    _result, rec = g6_result(tmp_path, monkeypatch, None)
    steps = rec["g6"]["steps"]
    assert steps["seq2"]["reply"]["old_value"] == "v1"
    assert steps["seq_readback"]["request"]["value"] == "v2" and steps["seq_readback"]["reply"]["old_value"] == "v2"
    assert steps["ov_readback_a"]["reply"]["old_value"] == "va"
    assert steps["ov_readback_b"]["reply"]["old_value"] == "vb"


# ---------------------------------------------------------------- parsers against the real renderers


def render_tool(bench, tool, **kwargs):
    return asyncio.run(bench.mcp.tools[tool](**kwargs))


def one_process_bench(paths=None):
    p = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    x = p.open_doc("X", (paths or {}).get("X", "C:/b/X.rvt"), active=True)
    y = p.open_doc("Y", (paths or {}).get("Y", "C:/b/Y.rvt"))
    return AccBench(p), p, x, y


def test_parse_mutation_text_success_names_the_document_and_the_verified_process():
    bench, p, x, _y = one_process_bench()
    text = render_tool(bench, "set_parameter", element_id=7, parameter_name="Mark", value="a", document=x,
                       target=bench.discovery()["usable"][0]["selector"])
    parsed = proc.parse_mutation_text(text)
    assert parsed["kind"] == "success" and parsed["http_status"] == 200
    assert (parsed["element_id"], parsed["parameter_name"], parsed["old_value"], parsed["new_value"]) == (
        7, "Mark", "", "a")
    assert parsed["document"] == x and parsed["document_title"] == "X" and parsed["document_path"] == "C:/b/X.rvt"
    assert parsed["document_active"] is True and parsed["identity"] == p.identity and parsed["credits"] is True


def test_parse_mutation_text_names_a_412_and_the_400_candidate_list():
    bench, p, x, y = one_process_bench()
    selector = bench.discovery()["usable"][0]["selector"]
    refused = proc.parse_mutation_text(render_tool(bench, "set_parameter", element_id=7, parameter_name="Mark",
                                                   value="a", document=y, target=selector))
    assert refused["kind"] == "refused" and refused["http_status"] == 412
    assert refused["error_code"] == "document-not-active" and refused["active_document"] == x
    assert refused["document"] is None and refused["identity"] == p.identity
    many = proc.parse_mutation_text(render_tool(bench, "set_parameter", element_id=7, parameter_name="Mark",
                                                value="a", target=selector))
    assert many["http_status"] == 400 and many["error_code"] == "document-selector-required"
    assert many["candidates"] == [x, y]


def test_parse_mutation_text_rolled_back_unknown_not_sent_and_conflict_credit_nobody():
    for mode, kind in (("rollback", "rolled-back"), ("unknown", "unknown"), ("conflict", "conflict")):
        bench, p, x, _y = one_process_bench()
        p.script = [mode]
        text = render_tool(bench, "set_parameter", element_id=7, parameter_name="Mark", value="a", document=x,
                           target=bench.discovery()["usable"][0]["selector"])
        parsed = proc.parse_mutation_text(text)
        assert parsed["kind"] == kind, (mode, text)
        if kind != "rolled-back":
            assert parsed["credits"] is False and parsed["document"] is None, (mode, text)
    sent_nothing = proc.parse_mutation_text(
        render_tool(one_process_bench()[0], "set_parameter", element_id=7, parameter_name="Mark", value="a",
                    target="revit1:bad"))
    assert sent_nothing["kind"] == "not-sent" and sent_nothing["credits"] is False


@pytest.mark.parametrize("junk", [None, 5, "", "Error: ", "Error: 999999 - {", b"x", [], {}])
def test_the_new_parsers_never_raise_on_junk(junk):
    for parse in (proc.parse_mutation_text, proc.parse_discovery_text, proc.parse_refusal_text):
        assert isinstance(parse(junk), dict)
    assert proc.parse_mutation_text(junk)["kind"] != "success"
    assert proc.parse_discovery_text(junk)["ok"] is False


def test_parse_discovery_text_reads_usable_selectors_and_collisions():
    p1 = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    p2 = AccProcess(2222, 48885, T2, "doc1.2222aaaaaaaa")
    p1.open_doc("Project1")
    bench = AccBench(p1, p2)
    bench.collision[48991] = [3333, 4444]
    parsed = proc.parse_discovery_text(render_tool(bench, "discover_revit_targets"))
    assert parsed["ok"] is True and [u["pid"] for u in parsed["usable"]] == [1111, 2222]
    assert [u["port"] for u in parsed["usable"]] == [48884, 48885]
    assert [u["session_token"] for u in parsed["usable"]] == [T1, T2]
    assert parsed["usable"][0]["document_open"] is True and parsed["usable"][1]["document_open"] is False
    assert parsed["usable"][0]["selector"] == bench.discovery()["usable"][0]["selector"]
    assert parsed["unusable"] == [{"port": 48991, "pids": [3333, 4444], "reason": "listener collision"}]


def test_parse_discovery_text_an_unavailable_inventory_is_not_ok_and_not_an_empty_list():
    parsed = proc.parse_discovery_text("Error: Listener inventory unavailable; request not sent.")
    assert parsed["ok"] is False and parsed["usable"] == []
    none = proc.parse_discovery_text("No usable Revit process found in the probed local ports.\nSnapshot ...")
    assert none["ok"] is True and none["usable"] == []


def test_parse_refusal_text_reads_collision_pids_candidates_and_whether_anyone_is_credited():
    bench = AccBench(AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa"))
    bench.collision[48991] = [3333, 4444]
    parsed = proc.parse_refusal_text(render_tool(bench, "get_revit_status"))
    assert parsed["refused"] is True and parsed["not_sent"] is True and parsed["credits"] is False
    assert parsed["pids"] == [3333, 4444]
    bench.collision.clear()
    ok = proc.parse_refusal_text(render_tool(bench, "get_revit_status"))
    assert ok["refused"] is False and ok["credits"] is True
    p1 = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    p2 = AccProcess(2222, 48885, T2, "doc1.2222aaaaaaaa")
    many = proc.parse_refusal_text(render_tool(AccBench(p1, p2), "get_revit_status"))
    assert many["refused"] is True and many["multiple"] == 2 and len(many["candidates"]) == 2


# ---------------------------------------------------------------- the commands: authorization is only ever typed


def test_the_authorize_command_records_the_users_words_and_a_time_and_nothing_else_sets_a_flag(tmp_path):
    raw = acc_start(str(tmp_path))
    assert all(load(raw)["authorizations"][flag] is None for flag in ACC_FLAGS)
    assert cmd("phase2-authorize", "--in", raw, "--flag", "g6_authorized", "--words", USER_WORDS["g6_authorized"]) == 0
    item = load(raw)["authorizations"]["g6_authorized"]
    assert item["value"] is True and item["words"] == USER_WORDS["g6_authorized"]
    assert item["source"] == "engineer-command-line" and proc._parse_time(item["at"]) is not None
    assert load(raw)["authorizations"]["mutation_authorized"] is None


@pytest.mark.parametrize("argv", [
    ["--flag", "g6_authorized", "--words", ""],
    ["--flag", "g6_authorized", "--words", "  "],
    ["--flag", "g6_authorized", "--words", "ok"],
    ["--flag", "everything_authorized", "--words", "I authorize everything for this run"],
    ["--flag", "g6_authorized"],
    ["--words", "I authorize the G6 campaign on the disposable copy"],
])
def test_the_authorize_command_refuses_blank_short_or_unknown_input(tmp_path, argv):
    raw = acc_start(str(tmp_path))
    before = open(raw, "rb").read()
    assert cmd("phase2-authorize", "--in", raw, *argv) == 2
    assert open(raw, "rb").read() == before


def test_a_flag_is_set_once_and_never_overwritten(tmp_path):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("g6_authorized",))
    before = open(raw, "rb").read()
    assert cmd("phase2-authorize", "--in", raw, "--flag", "g6_authorized", "--words", "A different later wording") == 2
    assert open(raw, "rb").read() == before


def test_apply_authorization_is_the_only_writer_and_needs_words():
    rec = proc.acceptance_template()
    assert proc.apply_authorization(rec, "g6_authorized", "")[0] is False
    assert proc.apply_authorization(rec, "nope_authorized", "some user words here")[0] is False
    assert proc.apply_authorization(rec, "g6_authorized", "some user words here")[0] is True
    assert proc.apply_authorization(rec, "g6_authorized", "some user words here")[0] is False


@pytest.mark.parametrize("argv", [
    ["mut-start", "--disposable", "yes"],
    ["g6-start", "--disposable", "yes"],
    ["collision-probe", "--port", "48991", "--setup-kind", "auxiliary-routes-server", "--setup-method", "two temporary servers"],
])
def test_a_flagged_capture_refuses_before_any_send_without_its_authorization(tmp_path, monkeypatch, argv):
    raw = acc_start(str(tmp_path))
    bench = one_process_bench()[0]
    bench.collision[48991] = [3333, 4444]
    install_acc_bench(monkeypatch, bench)
    before = open(raw, "rb").read()
    assert cmd(argv[0], "--in", raw, *argv[1:]) == 1
    assert bench.tool_calls == [] and not bench.routes
    assert open(raw, "rb").read() == before


def test_a_flag_for_one_section_does_not_open_another(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("mutation_authorized",))
    bench = one_process_bench()[0]
    install_acc_bench(monkeypatch, bench)
    assert cmd("g6-start", "--in", raw, "--disposable", "yes") == 1
    assert bench.tool_calls == []


def test_capture_commands_never_fill_the_engineer_fields(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw)
    flow_two_no_observe = AccBench(AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa"),
                                   AccProcess(2222, 48885, T2, "doc1.2222aaaaaaaa"))
    for p in flow_two_no_observe.processes:
        p.open_doc("Project1")
    install_acc_bench(monkeypatch, flow_two_no_observe)
    assert cmd("two-discover", "--in", raw) == 0
    assert cmd("two-status", "--in", raw, "--which", "1") == 0
    assert load(raw)["engineer"] == {}


def test_phase2_start_refuses_a_path_inside_the_repository_and_never_overwrites(tmp_path, monkeypatch):
    inside = os.path.join(REPO_ROOT, "raw-phase2-acceptance.json")
    assert cmd("phase2-start", "--out", inside) == 2 and not os.path.exists(inside)
    existing = tmp_path / "acc.json"
    existing.write_bytes(b"precious")
    assert cmd("phase2-start", "--out", str(existing)) == 2
    assert existing.read_bytes() == b"precious"


@pytest.mark.parametrize("name,extra", [
    ("phase2-authorize", ["--flag", "g6_authorized", "--words", "words of the user here"]),
    ("phase2-observe", ["--step", "g2:pair", "--ui", "same-title-confirmed"]),
    ("phase2-attach", ["--kind", "g34", "--record", "X"]),
    ("g2-list", ["--step", "pair"]),
    ("two-discover", []),
    ("mut-start", ["--disposable", "yes"]),
    ("g6-start", ["--disposable", "yes"]),
    ("collision-after", ["--port", "48991"]),
    ("http-thread", []),
])
def test_commands_refuse_an_input_path_inside_the_repository_before_any_live_call(monkeypatch, name, extra):
    def no_server(_port):
        raise AssertionError("a live server must not start")

    monkeypatch.setattr(proc, "_server", no_server)
    inside = os.path.join(REPO_ROOT, "tests", "unit", "test_phase2_live_identity.py")
    assert cmd(name, "--in", inside, *extra) == 2


@pytest.mark.parametrize("argv", [
    ["phase2-start"], ["phase2-start", "--out"], ["phase2-classify"], ["phase2-classify", "a", "b"],
    ["phase2-template", "extra"], ["g2-list", "--in", "x.json", "--step", "nothing"],
    ["g2-stale", "--in", "x.json", "--step", "pair", "--number", "1"],
    ["g2-stale", "--in", "x.json", "--step", "after_close", "--number", "zero"],
    ["two-status", "--in", "x.json", "--which", "3"], ["two-list", "--in", "x.json"],
    ["mut-start", "--in", "x.json"], ["mut-start", "--in", "x.json", "--disposable", "maybe"],
    ["mut-copy", "--in", "x.json"], ["mut-copy", "--in", "x.json", "--number", "1", "--sha256", "nothex"],
    ["mut-case", "--in", "x.json", "--case", "bogus", "--element-id", "1", "--param", "a", "--value", "b"],
    ["mut-case", "--in", "x.json", "--case", "active_named", "--element-id", "1", "--param", "a", "--value", "b"],
    ["mut-case", "--in", "x.json", "--case", "one_document_default", "--number", "1", "--element-id", "1",
     "--param", "a", "--value", "b"],
    ["mut-case", "--in", "x.json", "--case", "active_named", "--number", "1", "--element-id", "x", "--param", "a",
     "--value", "b"],
    ["mut-activate", "--in", "x.json"], ["mut-finish", "--in", "x.json", "--sha256-after", "1=zz"],
    ["g6-write", "--in", "x.json", "--step", "other", "--number", "1"],
    ["g6-write", "--in", "x.json", "--step", "seq1", "--number", "1"],
    ["g6-write", "--in", "x.json", "--step", "seq_readback", "--number", "1", "--value", "v"],
    ["g6-overlap", "--in", "x.json", "--number", "1", "--a", "1:P:v", "--b", "bad"],
    ["g6-overlap", "--in", "x.json", "--number", "1", "--a", "1:P:v", "--b", "1:P:w"],
    ["collision-probe", "--in", "x.json", "--port", "48991", "--setup-kind", "magic", "--setup-method", "m"],
    ["collision-probe", "--in", "x.json", "--port", "70000", "--setup-kind", "auxiliary-routes-server",
     "--setup-method", "m"],
    ["phase2-observe", "--in", "x.json", "--step", "nope", "--ui", "unchanged"],
    ["phase2-observe", "--in", "x.json", "--step", "g2:pair", "--ui", "sideways"],
    ["phase2-observe", "--in", "x.json", "--step", "g2:pair", "--ui", "unchanged", "--value-seen", "x"],
    ["phase2-attach", "--in", "x.json", "--kind", "other", "--record", "y.json"],
])
def test_malformed_acceptance_commands_are_usage_errors_before_any_live_call(monkeypatch, argv, capsys):
    def no_server(_port):
        raise AssertionError("a live server must not start")

    monkeypatch.setattr(proc, "_server", no_server)
    code = cmd(*argv)
    out = capsys.readouterr().out
    assert code == 2, (argv, out)
    assert ACC_OBS not in out


# ---------------------------------------------------------------- the commands: preconditions refuse before sending


def sent_mutation(bench):
    return [r for r in bench.routes if r[0] == "POST" and r[1] in ("/set_parameter/", "/activate_document/")]


def mutation_ready(tmp_path, monkeypatch, copy_both=True, second_doc=True):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("mutation_authorized",))
    paths = make_copy_files(str(tmp_path), ("X", "Y"))
    bench, p, x, y = one_process_bench(paths)
    if not second_doc:
        p.close_doc(y)
    install_acc_bench(monkeypatch, bench)
    assert cmd("mut-start", "--in", raw, "--disposable", "yes") == 0
    assert cmd("mut-copy", "--in", raw, "--number", "1") == 0
    if copy_both and second_doc:
        assert cmd("mut-copy", "--in", raw, "--number", "2") == 0
    return raw, bench, p, x, y


def case_argv(raw, name, number=None):
    argv = ["mut-case", "--in", raw, "--case", name, "--element-id", "101", "--param", "Comments", "--value", "v"]
    return argv + (["--number", str(number)] if number is not None else [])


@pytest.mark.parametrize("name,number,second_doc", [
    ("active_named", 2, True),            # document 2 is inactive
    ("inactive_412", 1, True),            # document 1 is the active one
    ("one_document_default", None, True),  # two documents are open
    ("many_documents_refused", None, False),  # only one document is open
    ("after_activation", 2, True),        # no activation was captured
    ("after_manual_switch", 1, True),     # nothing was switched by hand since the last capture
])
def test_a_mutation_case_with_wrong_preconditions_refuses_before_any_mutation_is_sent(
        tmp_path, monkeypatch, name, number, second_doc):
    raw, bench, _p, _x, _y = mutation_ready(tmp_path, monkeypatch, second_doc=second_doc)
    before = open(raw, "rb").read()
    assert cmd(*case_argv(raw, name, number)) == 1
    assert sent_mutation(bench) == []
    assert open(raw, "rb").read() == before


def test_a_mutation_refuses_while_any_open_document_is_not_a_registered_copy(tmp_path, monkeypatch):
    raw, bench, _p, _x, _y = mutation_ready(tmp_path, monkeypatch, copy_both=False)
    assert cmd(*case_argv(raw, "active_named", 1)) == 1
    assert sent_mutation(bench) == []


def test_a_mutation_case_is_never_repeated_or_overwritten(tmp_path, monkeypatch):
    raw, bench, _p, _x, _y = mutation_ready(tmp_path, monkeypatch)
    assert cmd(*case_argv(raw, "active_named", 1)) == 0
    first = load(raw)["mutation"]["cases"]["active_named"]
    count = len(sent_mutation(bench))
    assert cmd(*case_argv(raw, "active_named", 1)) == 2
    assert len(sent_mutation(bench)) == count and load(raw)["mutation"]["cases"]["active_named"] == first


def test_the_activation_step_refuses_the_active_or_an_unregistered_document_and_is_sent_once(tmp_path, monkeypatch):
    raw, bench, _p, _x, _y = mutation_ready(tmp_path, monkeypatch)
    assert cmd("mut-activate", "--in", raw, "--number", "1") == 1  # already active
    assert [r for r in bench.routes if r[1] == "/activate_document/"] == []
    assert cmd("mut-activate", "--in", raw, "--number", "2") == 0
    assert cmd("mut-activate", "--in", raw, "--number", "1") == 2  # recorded once; never repeated
    assert len([r for r in bench.routes if r[1] == "/activate_document/"]) == 1


def test_a_registered_copy_needs_a_saved_path_outside_the_repository_and_a_matching_hash(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("mutation_authorized",))
    paths = make_copy_files(str(tmp_path), ("X", "Y"))
    bench, p, x, y = one_process_bench(paths)
    p.open_doc("Project1", "")  # never saved
    p.open_doc("InRepo", os.path.join(REPO_ROOT, "README.md"))
    install_acc_bench(monkeypatch, bench)
    assert cmd("mut-start", "--in", raw, "--disposable", "yes") == 0
    assert cmd("mut-copy", "--in", raw, "--number", "3") == 1       # no saved path: no file to hash
    assert cmd("mut-copy", "--in", raw, "--number", "4") == 1       # inside the repository
    assert cmd("mut-copy", "--in", raw, "--number", "1", "--sha256", "0" * 64) == 1  # typed hash disagrees
    assert load(raw)["copies"] == []
    assert cmd("mut-copy", "--in", raw, "--number", "1", "--sha256", sha_of(paths["X"])) == 0
    copies = load(raw)["copies"]
    assert len(copies) == 1 and copies[0]["sha256_before"] == sha_of(paths["X"])
    assert copies[0]["section"] == "mutation" and copies[0]["process_token"] == T1
    assert cmd("mut-copy", "--in", raw, "--number", "1") == 2       # registered once


def test_an_unreadable_file_needs_a_typed_hash_and_is_recorded_with_its_source(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("mutation_authorized",))
    paths = make_copy_files(str(tmp_path), ("X", "Y"))
    bench, _p, _x, _y = one_process_bench(paths)
    install_acc_bench(monkeypatch, bench)
    monkeypatch.setattr(proc, "_sha256_file", lambda path: None)
    assert cmd("mut-start", "--in", raw, "--disposable", "yes") == 0
    assert cmd("mut-copy", "--in", raw, "--number", "1") == 1
    assert cmd("mut-copy", "--in", raw, "--number", "1", "--sha256", sha_of(paths["X"])) == 0
    assert load(raw)["copies"][0]["sha256_before_source"] == "engineer-typed"


def test_a_restarted_revit_between_mutation_commands_is_stop_and_leaves_the_record_alone(tmp_path, monkeypatch):
    raw, bench, p, _x, _y = mutation_ready(tmp_path, monkeypatch)
    before = open(raw, "rb").read()
    p.identity = ident(9999, T4, port=48884, version="2024")  # a new incarnation answers
    calls = len(bench.tool_calls)
    assert cmd(*case_argv(raw, "active_named", 1)) == 1
    assert sent_mutation(bench) == [] and open(raw, "rb").read() == before
    assert [n for n, _a in bench.tool_calls[calls:]] == ["get_revit_status"]


def test_mut_finish_records_after_hashes_and_a_changed_file_is_visible_to_the_classifier(tmp_path, monkeypatch):
    raw, _bench, _p, _x, _y = mutation_ready(tmp_path, monkeypatch)
    with open(load(raw)["copies"][0]["path"], "ab") as handle:
        handle.write(b"saved by something")  # the model file changed: a save or sync happened
    assert cmd("mut-finish", "--in", raw) == 0
    copies = load(raw)["copies"]
    assert copies[0]["sha256_after"] != copies[0]["sha256_before"] and copies[1]["sha256_after"] == copies[1]["sha256_before"]


def g6_ready(tmp_path, monkeypatch, copy=True):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("g6_authorized",))
    paths = make_copy_files(str(tmp_path), ("G6",))
    p = AccProcess(3333, 48884, T3, "doc1.3333aaaaaaaa")
    p.open_doc("G6copy", paths["G6"], active=True)
    bench = AccBench(p)
    install_acc_bench(monkeypatch, bench)
    assert cmd("g6-start", "--in", raw, "--disposable", "yes") == 0
    if copy:
        assert cmd("g6-copy", "--in", raw, "--number", "1") == 0
    return raw, bench, p


def g6_write(raw, step, **extra):
    argv = ["g6-write", "--in", raw, "--step", step, "--number", "1"]
    for flag, value in extra.items():
        argv += ["--" + flag.replace("_", "-"), value]
    return cmd(*argv)


def test_g6_refuses_before_any_write_for_an_unregistered_copy_or_a_step_out_of_order(tmp_path, monkeypatch):
    raw, bench, _p = g6_ready(tmp_path, monkeypatch, copy=False)
    assert g6_write(raw, "seq1", element_id="1", param="Mark", value="v1") == 1
    assert cmd("g6-copy", "--in", raw, "--number", "1") == 0
    assert g6_write(raw, "seq2", element_id="1", param="Mark", value="v2") == 1      # seq1 not captured
    assert g6_write(raw, "seq_readback") == 1                                         # seq2 not captured
    assert g6_write(raw, "ov_readback_a") == 1                                        # no overlap yet
    assert cmd("g6-overlap", "--in", raw, "--number", "1", "--a", "1:Mark:a", "--b", "2:Mark:b") == 1  # no seq run
    assert sent_mutation(bench) == []
    assert g6_write(raw, "seq1", element_id="1", param="Mark", value="v1") == 0
    assert g6_write(raw, "seq1", element_id="1", param="Mark", value="v1") == 2      # never repeated
    assert len(sent_mutation(bench)) == 1


def test_a_g6_write_names_the_active_registered_copy_and_a_wrong_number_is_refused(tmp_path, monkeypatch):
    raw, bench, _p = g6_ready(tmp_path, monkeypatch)
    assert cmd("g6-write", "--in", raw, "--step", "seq1", "--number", "5", "--element-id", "1", "--param", "Mark",
               "--value", "v1") == 1
    assert sent_mutation(bench) == []


def test_g6_never_sends_anything_but_set_parameter_and_reads(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory() as folder:
        raw = acc_start(folder)
        acc_authorize(raw, ("g6_authorized",))
        bench = flow_g6(raw, monkeypatch, folder)
    assert {(m, route) for m, route, _d, _o in bench.routes} <= {
        ("GET", "/status/"), ("GET", "/documents/"), ("POST", "/set_parameter/")}
    assert [r for r in bench.routes if r[1] == "/set_parameter/"][0][2]["document"]  # every write names its document
    assert all("document" in r[2] for r in bench.routes if r[1] == "/set_parameter/")


def test_collision_probe_refuses_when_the_inventory_shows_no_collision_and_sends_nothing(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("collision_authorized",))
    bench = one_process_bench()[0]
    install_acc_bench(monkeypatch, bench)
    before = open(raw, "rb").read()
    assert cmd("collision-probe", "--in", raw, "--port", "48884", "--setup-kind", "auxiliary-routes-server",
               "--setup-method", "two temporary servers") == 1
    assert bench.tool_calls == [] and open(raw, "rb").read() == before


def test_collision_after_needs_the_probe_first_and_nothing_is_sent_before_it(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("collision_authorized",))
    bench = one_process_bench()[0]
    install_acc_bench(monkeypatch, bench)
    assert cmd("collision-after", "--in", raw, "--port", "48991") == 1
    assert bench.tool_calls == []


def test_the_collision_probe_sends_no_model_request_and_records_every_pid_from_the_netstat_inventory(
        tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("collision_authorized",))
    bench = flow_collision(raw, monkeypatch)
    probe = load(raw)["collision"]["probe"]
    assert probe["inventory"]["owners"] == [3333, 4444]
    assert probe["inventory"]["source"] == "bridge.listener_snapshot"
    assert probe["inventory"]["method"] == "netstat.exe -ano -p tcp"
    assert probe["setup_kind"] == "auxiliary-routes-server" and probe["setup_method"]
    assert probe["default"]["refused"] is True and probe["default"]["pids"] == [3333, 4444]
    assert probe["discovery"]["unusable"][0]["pids"] == [3333, 4444]
    assert not [r for r in bench.routes if r[1] in ("/documents/", "/set_parameter/", "/activate_document/")]
    assert {name for name, _a in bench.tool_calls} <= {"discover_revit_targets", "get_revit_status", "list_documents"}


def test_a_selected_call_at_a_collision_port_is_refused_and_recorded(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("collision_authorized",))
    p = AccProcess(3333, 48991, T3, "doc1.3333aaaaaaaa")
    p.open_doc("Alpha", "C:/bench/Alpha.rvt")
    bench = AccBench(p)
    install_acc_bench(monkeypatch, bench)
    selector = bench.discovery()["usable"][0]["selector"]
    bench.collision[48991] = [3333, 4444]  # a second listener appears on the port the selector names
    assert cmd("collision-probe", "--in", raw, "--port", "48991", "--setup-kind", "second-revit-primary-port",
               "--setup-method", "second Revit bound the same primary port", "--selector", selector) == 0
    selected = load(raw)["collision"]["probe"]["selected"]
    assert selected["refused"] is True and selected["pids"] == [3333, 4444] and selected["credits"] is False
    other = proc.make_selector("127.0.0.1", 48884, 3333, T3)
    raw2 = os.path.join(str(tmp_path), "second.json")
    assert cmd("phase2-start", "--out", raw2) == 0
    acc_authorize(raw2, ("collision_authorized",))
    assert cmd("collision-probe", "--in", raw2, "--port", "48991", "--setup-kind", "second-revit-primary-port",
               "--setup-method", "second Revit bound the same primary port", "--selector", other) == 1  # other port


def test_two_commands_refuse_before_any_send_when_discovery_is_missing_or_a_listener_is_not_sole(
        tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    p1 = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    p2 = AccProcess(2222, 48885, T2, "doc1.2222aaaaaaaa")
    p1.open_doc("Project1")
    p2.open_doc("Project1")
    bench = AccBench(p1, p2)
    install_acc_bench(monkeypatch, bench)
    assert cmd("two-status", "--in", raw, "--which", "1") == 1
    assert cmd("two-list", "--in", raw, "--which", "1") == 1
    assert bench.tool_calls == []
    assert cmd("two-discover", "--in", raw) == 0
    assert cmd("two-discover", "--in", raw) == 2  # never overwritten
    bench.collision[48885] = [2222, 5555]
    calls = len(bench.tool_calls)
    assert cmd("two-status", "--in", raw, "--which", "2") == 1
    assert len(bench.tool_calls) == calls


def test_two_discover_with_a_single_process_is_recorded_and_classifies_as_not_two_processes(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    bench = one_process_bench()[0]
    install_acc_bench(monkeypatch, bench)
    assert cmd("two-discover", "--in", raw) == 0
    assert cmd("two-status", "--in", raw, "--which", "2") == 1
    result = acc_result(load(raw))
    assert result["units"]["two"]["status"] == "stop" and has_code(result["units"]["two"], "two-not-two-processes")


def test_two_status_and_two_list_name_the_process_each_selector_chose(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    bench = flow_two(raw, monkeypatch)
    rec = load(raw)["two"]
    usable = rec["discovery"]["usable"]
    assert [u["pid"] for u in usable] == [1111, 2222]
    for which, u in (("1", usable[0]), ("2", usable[1])):
        assert rec["status"][which]["identity"]["pid"] == u["pid"]
        assert rec["status"][which]["identity"]["session_token"] == u["session_token"]
        assert rec["list"][which]["identity"]["pid"] == u["pid"]
    targets = [a.get("target") for n, a in bench.tool_calls if n in ("get_revit_status", "list_documents")]
    assert targets.count(None) == 1  # only the deliberate default call names no target
    assert not [r for r in bench.routes if r[0] == "POST"]
    assert {n for n, _a in bench.tool_calls} <= {"discover_revit_targets", "get_revit_status", "list_documents"}


def test_the_two_overlap_is_informational_and_a_cross_wired_answer_is_stop(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    flow_two(raw, monkeypatch)
    rec = load(raw)
    assert len(rec["two"]["overlap"]["jobs"]) == 4
    assert acc_result(rec)["informational"]["serialization"]["status"] == "observed"
    swapped = copy.deepcopy(rec)
    swapped["two"]["overlap"]["jobs"][0]["reply"]["identity"] = copy.deepcopy(
        swapped["two"]["overlap"]["jobs"][-1]["reply"]["identity"])
    assert acc_result(swapped)["informational"]["serialization"]["status"] == "stop"


def test_http_thread_routes_are_informational_get_only_captures(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    bench = flow_http(raw, monkeypatch)
    rec = load(raw)["http_thread"]
    assert rec["status"]["identity"]["pid"] == 1111 and rec["model_info"]["identity"]["pid"] == 1111
    assert {(m, r) for m, r, _d, _o in bench.routes} == {("GET", "/status/"), ("GET", "/model_info/")}
    assert acc_result(load(raw))["informational"]["http_thread"]["status"] == "observed"


def test_g2_commands_refuse_before_sending_when_the_stale_token_is_still_listed_or_out_of_range(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    paths = make_copy_files(str(tmp_path), ("A", "B"))
    p = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    p.open_doc("SAME", paths["A"], active=True)
    p.open_doc("SAME", paths["B"])
    bench = AccBench(p)
    install_acc_bench(monkeypatch, bench)
    assert cmd("g2-stale", "--in", raw, "--step", "after_close", "--number", "1") == 1   # no pair listing yet
    assert cmd("g2-list", "--in", raw, "--step", "pair") == 0
    assert cmd("g2-list", "--in", raw, "--step", "pair") == 2                            # never overwritten
    assert cmd("g2-stale", "--in", raw, "--step", "after_close", "--number", "9") == 1   # out of range
    assert cmd("g2-stale", "--in", raw, "--step", "after_close", "--number", "1") == 1   # nothing was closed
    assert not [r for r in bench.routes if r[1] == "/document_summary/"]


def test_the_g2_stale_read_is_a_read_of_the_closed_token_and_no_mutation_route_is_ever_sent(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory() as folder:
        raw = acc_start(folder)
        bench = flow_g2(raw, monkeypatch, folder)
    routes = {(m, r) for m, r, _d, _o in bench.routes}
    assert routes == {("GET", "/status/"), ("GET", "/documents/"), ("POST", "/document_summary/")}
    stale = [d for _m, r, d, _o in bench.routes if r == "/document_summary/"]
    assert len(stale) == 2 and stale[0]["document"] == stale[1]["document"]


# ---------------------------------------------------------------- observe, attach and the report


def test_observe_needs_a_captured_step_and_keeps_a_superseded_observation(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    assert acc_observe(raw, "g2:pair", "same-title-confirmed") == 1
    flow_http(raw, monkeypatch)
    paths = make_copy_files(str(tmp_path), ("A", "B"))
    p = AccProcess(1111, 48884, T1, "doc1.1111aaaaaaaa")
    p.open_doc("SAME", paths["A"], active=True)
    p.open_doc("SAME", paths["B"])
    install_acc_bench(monkeypatch, AccBench(p))
    assert cmd("g2-list", "--in", raw, "--step", "pair") == 0
    assert acc_observe(raw, "g2:pair", "same-title-confirmed") == 0
    assert acc_observe(raw, "g2:pair", "closed-by-me") == 0
    rec = load(raw)
    assert rec["engineer"]["g2:pair"]["ui"] == "closed-by-me"
    assert rec["engineer_superseded"][0]["ui"] == "same-title-confirmed"
    assert rec["engineer"]["g2:pair"]["source"] == "engineer-command-line"


def test_a_value_seen_note_is_only_for_g6_steps_and_is_kept_verbatim(tmp_path, monkeypatch):
    raw = acc_start(str(tmp_path))
    acc_authorize(raw, ("g6_authorized",))
    flow_g6(raw, monkeypatch, str(tmp_path))
    assert acc_observe(raw, "g6:seq2", "unchanged", dialog="none", value_seen="v2 (Properties palette)") == 0
    assert load(raw)["engineer"]["g6:seq2"]["value_seen"] == "v2 (Properties palette)"


def test_attach_embeds_a_prior_record_and_refuses_the_wrong_schema_or_a_second_attach(tmp_path):
    raw = acc_start(str(tmp_path))
    wrong = tmp_path / "wrong.json"
    wrong.write_bytes(json.dumps({"schema": "something-else"}).encode("utf-8"))
    assert cmd("phase2-attach", "--in", raw, "--kind", "g34", "--record", str(wrong)) == 1
    acc_attach(raw, str(tmp_path), identity=True, g34=False)
    prior = load(raw)["prior"]["identity_recheck"]
    assert prior["record"] == good_record() and prior["attached_at"] and prior["source_name"] == "prior-identity.json"
    before = open(raw, "rb").read()
    assert cmd("phase2-attach", "--in", raw, "--kind", "identity_recheck", "--record",
               str(tmp_path / "prior-identity.json")) == 2
    assert open(raw, "rb").read() == before


def test_the_acceptance_sentinel_is_printed_only_for_an_accept_eligible_live_record(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(good_acc_record()), encoding="utf-8")
    capsys.readouterr()
    assert cmd("phase2-classify", str(good)) == 0
    out = capsys.readouterr().out
    assert ACC_OBS + " approval=not-granted" in out and ACC_STOP not in out
    for c in proc.CRITERIA:
        assert "CRITERION {}: observed".format(c) in out
    for g in proc.GATES:
        assert "GATE {}: observed".format(g) in out


@pytest.mark.parametrize("label,mutate,unit,code", ACC_STOP_CASES[:25], ids=[c[0] for c in ACC_STOP_CASES[:25]])
def test_the_acceptance_sentinel_is_never_printed_for_a_stop_record(tmp_path, capsys, label, mutate, unit, code):
    rec = good_acc_record()
    mutate(rec)
    path = tmp_path / "stop.json"
    path.write_text(json.dumps(rec), encoding="utf-8")
    capsys.readouterr()
    assert cmd("phase2-classify", str(path)) == 1
    out = capsys.readouterr().out
    assert ACC_OBS not in out and ACC_STOP + " approval=not-granted" in out


def test_the_report_names_the_open_gates_authorizations_and_the_999_1_limitation(tmp_path, capsys):
    rec = good_acc_record()
    rec["authorizations"]["g6_authorized"] = None
    rec["g6"] = {}
    rec["sent_calls"] = [c for c in rec["sent_calls"] if c["section"] != "g6"]
    rec["copies"] = [c for c in rec["copies"] if c["section"] != "g6"]
    path = tmp_path / "open.json"
    path.write_text(json.dumps(rec), encoding="utf-8")
    capsys.readouterr()
    assert cmd("phase2-classify", str(path)) == 1
    out = capsys.readouterr().out
    assert "AUTH g6_authorized: not-authorized" in out and "GATE g6: not-run" in out
    assert "AMBIG-04" in out and "999.1" in out and ACC_OBS not in out


def test_phase2_classify_unreadable_or_garbage_file_is_stop(tmp_path, capsys):
    assert cmd("phase2-classify", str(tmp_path / "missing.json")) == 1
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe not json")
    assert cmd("phase2-classify", str(bad)) == 1
    out = capsys.readouterr().out
    assert ACC_OBS not in out and ACC_STOP in out


def test_phase2_template_prints_json_with_unset_flags_and_no_sentinel(capsys):
    assert cmd("phase2-template") == 0
    out = capsys.readouterr().out
    template = json.loads(out)
    assert template["schema"] == proc.ACC_SCHEMA and template["authorizations"]["g6_authorized"] is None
    assert ACC_OBS not in out


# ---------------------------------------------------------------- allow-lists, usage, no arbitrary code


def test_every_section_sends_only_tools_from_its_own_allow_list_and_nothing_arbitrary():
    assert set(proc.SECTION_TOOLS) == {"g2", "two", "http_thread", "mutation", "collision", "g6"}
    for section, tools in proc.SECTION_TOOLS.items():
        for tool in tools:
            assert tool in proc.ACC_TOOL_ROUTES, (section, tool)
            assert "execute" not in tool and "execute" not in proc.ACC_TOOL_ROUTES[tool][1]
    posts = lambda s: {t for t in proc.SECTION_TOOLS[s] if proc.ACC_TOOL_ROUTES[t][0] == "POST"}  # noqa: E731
    assert posts("g6") == {"set_parameter"}
    assert posts("mutation") == {"set_parameter", "activate_document"}
    assert posts("g2") <= {"read_document_summary", "read_document_levels"}
    for section in ("two", "http_thread", "collision"):
        assert posts(section) == set(), section
    assert proc.SECTION_FLAG == {"mutation": "mutation_authorized", "g6": "g6_authorized",
                                 "collision": "collision_authorized"}


@pytest.mark.parametrize("section", ["g2", "two", "http_thread", "mutation", "collision", "g6"])
def test_the_entry_builder_refuses_any_tool_outside_the_section_and_the_arbitrary_code_tools(section):
    for tool in ("execute_revit_code", "execute_code", "save_document", "open_model", "delete_elements", "", None):
        with pytest.raises(ValueError):
            proc.acc_sent_call_entry(section, tool, "x")
    with pytest.raises(ValueError):
        proc.acc_sent_call_entry("elsewhere", "get_revit_status", "x")
    for tool in proc.SECTION_TOOLS[section]:
        entry = proc.acc_sent_call_entry(section, tool, "step")
        assert (entry["method"], entry["route"]) == proc.ACC_TOOL_ROUTES[tool] and entry["section"] == section


def test_the_procedure_has_no_call_node_that_targets_the_arbitrary_code_tool_or_route():
    tree = ast.parse(open(PROCEDURE_PATH, "rb").read().decode("utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if "execute" in name.lower():
            found.append(("call", name, node.lineno))
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str) and "execute" in child.value.lower():
                found.append(("argument", child.value[:40], node.lineno))
    assert found == []


def test_the_module_docstring_documents_exactly_what_each_section_sends():
    doc = proc.__doc__
    for tools in proc.SECTION_TOOLS.values():
        for tool in tools:
            assert tool in doc, tool
    for route in {proc.ACC_TOOL_ROUTES[t][1] for tools in proc.SECTION_TOOLS.values() for t in tools}:
        assert route in doc, route
    for flag in ACC_FLAGS:
        assert flag in doc
    for word in ("disposable", "never saves", "AMBIG-04", "999.1", "netstat", "auxiliary"):
        assert word in doc, word


def test_usage_lists_every_command_main_dispatches():
    usage = proc.USAGE + proc.G34_USAGE + proc.ACC_USAGE
    tree = ast.parse(open(PROCEDURE_PATH, "rb").read().decode("utf-8"))
    main = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"][0]
    dispatched = set()
    for node in ast.walk(main):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "command":
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    dispatched.add(comparator.value)
    dispatched |= set(proc.ACC_COMMANDS)
    assert {"template", "classify", "first", "restart", "g34-template", "g34-start", "g3-read", "g4-case",
            "g34-observe", "g34-classify", "phase2-start", "phase2-authorize", "mut-case", "g6-overlap",
            "collision-probe"} <= dispatched
    for name in sorted(dispatched):
        assert name in usage, name


def test_the_existing_identity_g3_and_g4_commands_are_unchanged_by_the_acceptance_extension():
    assert proc.main(["template"]) == 0
    assert proc.classify_identity_recheck(good_record())[0] == proc.OBSERVED
    assert proc.classify_g3_production(good_g34_record())[0] == proc.G3_OBSERVED
    assert proc.classify_g4_production(good_g34_record())[0] == proc.G4_OBSERVED
    assert proc.G34_NOT_RUN_SLOTS == ("g6",) and proc.NOT_RUN_SLOTS[-1] == "g6"
