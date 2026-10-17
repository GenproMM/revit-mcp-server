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
import copy
import importlib.util
import json
import os
import subprocess

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
    return {"at": at, "kind": kind, "identity": identity, "text": "synthetic fixture text"}


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
            "bootstrap": {"identity": first, "at": "2026-10-17T10:00:00+00:00"},
            "replies": [
                reply("no-document", first, "2026-10-17T10:00:02+00:00"),
                reply("no-document", first, "2026-10-17T10:00:03+00:00"),
            ],
            "no_document_reply": reply("no-document", first, "2026-10-17T10:00:02+00:00"),
            "listener": listener(PORT, [1111]),
        },
        "incarnation_2": {
            "bootstrap": {"identity": second, "at": "2026-10-17T10:30:00+00:00"},
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
