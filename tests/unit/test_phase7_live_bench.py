# -*- coding: utf-8 -*-
"""Offline regression tests for the operator-only Phase 7 bench."""

import asyncio
import importlib.util
import json
import os
import uuid

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO_ROOT, "tests", "test_phase7_live_bench.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("phase7_live_bench", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = _load_module()
TOKEN = str(uuid.UUID("11111111-1111-1111-1111-111111111111"))


def _audit(call_id, tool, route, decision="confirm", approval="accepted", outcome="success"):
    args = ({"element_ids": [123], "operation": "move", "vector": {"x": 12.5, "y": 0, "z": 0}}
            if tool == "transform_elements" else {"element_ids": [123]})
    return json.dumps({"call_id": call_id, "tool": tool, "route": route, "args": args,
                       "decision": decision, "approval": approval, "outcome": outcome})


def _passing_record():
    record = bench.evidence_template()
    record["preflight"].update({
        "status_http": 200, "listeners": [1234],
        "identity": {"pid": 1234, "actual_port": 48884, "session_token": TOKEN},
        "port": 48884, "permit_protocol": 1, "revit_version": "2026",
        "policy": {"source": "base", "hash": "0123456789ab", "blocked": False,
                   "operator_state": "not_configured"},
    })
    record["direct"].update({
        "s6": {"http": 403, "permit": "missing", "level_absent": True},
        "s5a": {"first_http": 200, "first_outcome": "success", "second_http": 403,
                "second": {"permit": "replayed"}},
        "s5b": {"http": 403, "permit": "args_mismatch", "level_absent": True},
        "s5c": {"http": 403, "permit": "route_mismatch"},
    })
    record["hermes"].update({
        "h1": {"call_id": "h1", "element_gone": True},
        "h2": {"call_id": "h2", "element_present": True},
        "h3": {"call_id": "h3"},
        "h4": {"call_ids": ["h4a", "h4b"]},
        "h5": {"call_id": "h5", "fractional_mm": 12.5},
        "h6": {"status": "not_verified"},
    })
    record["audit_files"] = {"audit-test.jsonl": [
        _audit("h1", "delete_elements", "/delete_elements/"),
        _audit("h2", "delete_elements", "/delete_elements/", approval="declined", outcome="denied"),
        _audit("h3", "delete_elements", "/delete_elements/", approval="expired", outcome="expired"),
        _audit("h4a", "delete_elements", "/delete_elements/"),
        _audit("h4b", "delete_elements", "/delete_elements/"),
        _audit("h5", "transform_elements", "/transform_elements/"),
    ]}
    record["posts_sent"] = 5
    return record


def test_template_has_all_phase7_evidence_sections():
    record = bench.evidence_template()
    assert set(("preflight", "direct", "hermes", "audit_files", "posts_sent", "revit_version", "policy")) <= set(record)
    assert set(record["direct"]) == {"s6", "s5a", "s5b", "s5c"}


def test_complete_synthetic_record_classifies_ok():
    assert bench.classify(_passing_record(), "unrelated-secret") == ("ok", [])


def test_no_audit_evidence_never_classifies_ok():
    record = _passing_record(); record["audit_files"] = {}
    verdict, reasons = bench.classify(record, "secret")
    assert verdict == "stop" and any("audit_files" in reason for reason in reasons)


def test_audit_wrong_tool_or_route_stops():
    record = _passing_record()
    record["audit_files"]["audit-test.jsonl"][0] = _audit("h1", "get_model_info", "/model_info/")
    verdict, reasons = bench.classify(record, "secret")
    assert verdict == "stop" and any("hermes.h1.audit" in reason for reason in reasons)


def test_reused_call_id_across_scenarios_stops():
    record = _passing_record(); record["hermes"]["h2"]["call_id"] = "h1"
    verdict, reasons = bench.classify(record, "secret")
    assert verdict == "stop" and any("reused" in reason for reason in reasons)


def test_fractional_transform_must_show_12_5_mm():
    record = _passing_record(); record["hermes"]["h5"]["fractional_mm"] = 12
    verdict, reasons = bench.classify(record, "secret")
    assert verdict == "stop" and any("h5" in reason for reason in reasons)


def test_s6_success_stops():
    record = _passing_record(); record["direct"]["s6"]["http"] = 200
    assert bench.classify(record, "secret")[0] == "stop"


def test_replayed_permit_success_stops():
    record = _passing_record(); record["direct"]["s5a"]["second_http"] = 200
    assert bench.classify(record, "secret")[0] == "stop"


def test_secret_occurrences_detects_whole_escaped_and_run():
    secret = "0123456789abcdef0123456789abcdef"
    assert bench.secret_occurrences("x {} y".format(secret), secret) == 1
    assert bench.secret_occurrences(json.dumps({"secret": secret}), secret) >= 1
    assert bench.secret_occurrences("x {} y".format(secret[:16]), secret) == 1


def test_secret_in_record_stops():
    secret = "0123456789abcdef0123456789abcdef"
    record = _passing_record(); record["audit_files"]["audit-test.jsonl"].append(secret[:16])
    verdict, reasons = bench.classify(record, secret)
    assert verdict == "stop" and any("SECRET_OCCURRENCES" in reason for reason in reasons)


def test_identity_must_match_listener_production_contract():
    record = _passing_record(); record["preflight"]["identity"]["pid"] = 999
    verdict, reasons = bench.classify(record, "secret")
    assert verdict == "stop" and any("preflight.identity" in reason for reason in reasons)


def test_malformed_list_levels_is_not_absence_proof():
    for body in ({}, {"levels": [], "total_levels": 1}, {"levels": [{"name": "x"}], "total_levels": "1"}):
        try:
            bench._levels(body)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed list_levels accepted")


def test_has_level_requires_exact_name_not_substring():
    assert not bench._has_level([{"name": "phase7-bench-x-s6-extra"}], "phase7-bench-x-s6")
    assert bench._has_level([{"name": "phase7-bench-x-s6"}], "phase7-bench-x-s6")


def test_post_counts_before_transport_exception_and_strips_exception_text(tmp_path):
    class BrokenClient(object):
        async def post(self, *args, **kwargs):
            raise RuntimeError("secret-text-must-not-appear")
    record = bench.evidence_template()
    with open(tmp_path / "persist.json", "w+", encoding="utf-8") as handle:
        step = asyncio.run(bench._post(BrokenClient(), record, "/create_level/", "{}",
                                       lambda: bench._write_reserved(handle, record)))
    assert record["posts_sent"] == 1 and step["error"] == "RuntimeError"
    assert "secret-text" not in json.dumps(step)


def test_direct_rejects_non_allowlisted_endpoint_before_counting():
    record = bench.evidence_template()
    try:
        asyncio.run(bench._post(object(), record, "/execute_code/", "{}", lambda: None))
    except ValueError:
        pass
    else:
        raise AssertionError("non-allowlisted endpoint was accepted")
    assert record["posts_sent"] == 0


def test_preflight_fake_client_records_valid_identity(monkeypatch, tmp_path):
    class Response(object):
        status_code = 200
        def json(self):
            return {"process_identity": {"pid": 4321, "actual_port": 48884, "session_token": TOKEN, "revit_version": "2026"}, "permit": {"protocol": 1}}
    class Client(object):
        async def get(self, path): assert path == "/genpro_revit_mcp/status/"; return Response()
        async def aclose(self): return None
    class Bridge(object):
        @staticmethod
        def listener_snapshot(ports): return {48884: [4321]}
    async def policy_snapshot():
        return {"source": "base", "hash": "0123456789ab", "blocked": False, "operator_state": "not_configured"}
    monkeypatch.setattr(bench, "_direct_client", lambda port: Client())
    monkeypatch.setattr(bench, "_bridge", lambda: Bridge())
    monkeypatch.setattr(bench, "_safe_policy_snapshot", policy_snapshot)
    args = type("Args", (), {"port": 48884, "out": str(tmp_path / "preflight.json")})()
    record, reasons = asyncio.run(bench._cmd_preflight(args))
    assert reasons == [] and record["posts_sent"] == 0


@pytest.mark.parametrize("port,name", [(0, "phase7-bench-a"), (65536, "phase7-bench-a"), (48884, "ordinary-level")])
def test_direct_bad_arguments_refuse_without_transport(monkeypatch, tmp_path, port, name):
    monkeypatch.setattr(bench, "_direct_client", lambda *args: pytest.fail("transport constructed"))
    args = type("Args", (), {"port": port, "level_name": name, "out": str(tmp_path / "out.json")})()
    record, reasons = None, None
    with pytest.raises(bench._UsageError):
        asyncio.run(bench._cmd_direct(args))


@pytest.mark.parametrize("passing", [True, False])
def test_classify_cli_uses_only_synthetic_secret(monkeypatch, tmp_path, capsys, passing):
    record = _passing_record() if passing else bench.evidence_template()
    path = tmp_path / "classify.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(bench, "_load_secret", lambda: "unrelated-secret")
    assert bench.main(["classify", str(path)]) == (0 if passing else 1)
    output = capsys.readouterr().out
    assert (bench.SENTINEL_OK if passing else bench.SENTINEL_STOP) in output
    assert "SECRET_OCCURRENCES=0" in output and "POSTS_SENT=" in output


def test_missing_audit_directory_refuses_without_reads(tmp_path):
    args = type("Args", (), {"record": str(tmp_path / "record.json"), "audit_dir": str(tmp_path / "missing"),
                              "replies": str(tmp_path / "replies.json"), "out": str(tmp_path / "out.json")})()
    with pytest.raises(bench._UsageError):
        bench._cmd_ingest(args)


def test_network_hosted_policy_is_refused_before_open(monkeypatch):
    class Policy(object):
        __file__ = "C:/local/policy.py"
        BASE_FILE = "policy.base.toml"; POLICY_FILE_ENV = "POLICY"; MAX_OPERATOR_BYTES = 10
    monkeypatch.setattr(bench, "_policy", lambda: Policy())
    monkeypatch.setattr(bench.os, "name", "nt", raising=False)
    monkeypatch.setattr(bench, "_windows_path_is_local", lambda path: False)
    try:
        asyncio.run(bench._safe_policy_snapshot())
    except ValueError as ex:
        assert "non-local" in str(ex) or "network-hosted" in str(ex)
    else:
        raise AssertionError("network policy source accepted")


def test_direct_real_permits_five_posts_and_no_secret_or_mac_in_record(monkeypatch, tmp_path):
    import permit
    from revit_mcp import permits as verifier
    secret = "0123456789abcdef0123456789abcdef"
    verifier._CONSUMED.clear()
    class Response(object):
        def __init__(self, status, body): self.status_code, self._body = status, body
        def json(self): return self._body
    class Client(object):
        def __init__(self): self.posts, self.levels = [], []
        async def get(self, path):
            if path.endswith("status/"):
                return Response(200, {"process_identity": {"pid": 4321, "actual_port": 48884, "session_token": TOKEN, "revit_version": "2026"}, "permit": {"protocol": 1}})
            return Response(200, {"levels": [{"name": name} for name in self.levels], "total_levels": len(self.levels)})
        async def post(self, path, content, headers):
            self.posts.append((path, content)); route = path.replace("/genpro_revit_mcp", "")
            verdict = verifier.check_and_consume(content, route, secret, TOKEN)
            if verdict != verifier.OK: return Response(403, {"permit": verdict})
            arguments = verifier.split_wire(content)[1]
            body = json.loads(arguments)
            if route == "/create_level/": self.levels.append(body["levels"][0]["name"])
            return Response(200, {"status": "success"})
        async def aclose(self): return None
    client = Client()
    class Bridge(object):
        @staticmethod
        def listener_snapshot(ports): return {48884: [4321]}
        @staticmethod
        def load_secret(): return secret
    async def policy_snapshot(): return {"source": "base", "hash": "0123456789ab", "blocked": False, "operator_state": "not_configured"}
    monkeypatch.setattr(bench, "_direct_client", lambda port: client)
    monkeypatch.setattr(bench, "_bridge", lambda: Bridge())
    monkeypatch.setattr(bench, "_load_secret", lambda: secret)
    monkeypatch.setattr(bench, "_permit", lambda: permit)
    monkeypatch.setattr(bench, "_safe_policy_snapshot", policy_snapshot)
    out = tmp_path / "direct.json"; args = type("Args", (), {"port": 48884, "level_name": "phase7-bench-a", "out": str(out)})()
    record, reasons = asyncio.run(bench._cmd_direct(args))
    assert reasons == [] and record["posts_sent"] == 5 and len(client.posts) == 5
    saved = out.read_text(encoding="utf-8")
    assert secret not in saved and '"m"' not in saved
    assert bench.classify(record, "different-secret")[0] == "stop"  # no Hermes evidence yet


def test_read_failure_after_post_persists_stop_and_nonzero_count(monkeypatch, tmp_path):
    class Response(object):
        status_code = 200
        def json(self): return {"process_identity": {"pid": 4321, "actual_port": 48884, "session_token": TOKEN, "revit_version": "2026"}, "permit": {"protocol": 1}}
    class Client(object):
        async def get(self, path):
            if path.endswith("status/"): return Response()
            raise RuntimeError("secret in message")
        async def post(self, *args, **kwargs): return Response()
        async def aclose(self): return None
    class Bridge(object):
        @staticmethod
        def listener_snapshot(ports): return {48884: [4321]}
        @staticmethod
        def load_secret(): return "0123456789abcdef0123456789abcdef"
    async def policy_snapshot(): return {"source": "base", "hash": "0123456789ab", "blocked": False, "operator_state": "not_configured"}
    monkeypatch.setattr(bench, "_direct_client", lambda port: Client())
    monkeypatch.setattr(bench, "_bridge", lambda: Bridge())
    monkeypatch.setattr(bench, "_safe_policy_snapshot", policy_snapshot)
    monkeypatch.setattr(bench, "_load_secret", lambda: "0123456789abcdef0123456789abcdef")
    args = type("Args", (), {"port": 48884, "level_name": "phase7-bench-a", "out": str(tmp_path / "broken.json")})()
    record, reasons = asyncio.run(bench._cmd_direct(args))
    assert record["posts_sent"] == 1 and reasons and "RuntimeError" in reasons[0]
    saved = (tmp_path / "broken.json").read_text(encoding="utf-8")
    assert '"posts_sent": 1' in saved and "secret in message" not in saved


def test_main_template_is_offline_and_prints_record(capsys):
    assert bench.main(["template"]) == 0
    assert '"direct"' in capsys.readouterr().out


def test_script_has_no_pytest_style_functions():
    with open(SCRIPT, encoding="utf-8") as handle: assert "def test_" not in handle.read()


@pytest.mark.parametrize("section,key,value", [
    ("preflight", "permit_protocol", None),
    ("preflight", "identity", {"pid": 1234, "actual_port": 1, "session_token": TOKEN}),
    ("direct", "s6", {"http": 403, "permit": "missing", "level_absent": False}),
    ("direct", "s5b", {"http": 403, "permit": "replayed", "level_absent": True}),
    ("direct", "s5c", {"http": 403, "permit": "args_mismatch"}),
    ("hermes", "h4", {"call_ids": ["h4a", "h4a"]}),
    ("hermes", "h6", {"status": "verified"}),
])
def test_negative_record_contracts(section, key, value):
    record = _passing_record()
    record[section][key] = value
    assert bench.classify(record, "unrelated-secret")[0] == "stop"


@pytest.mark.parametrize("index,approval,outcome", [(0, "none", "success"), (1, "declined", "success"), (2, "expired", "denied")])
def test_audit_refusal_contracts(index, approval, outcome):
    record = _passing_record()
    entry = json.loads(record["audit_files"]["audit-test.jsonl"][index])
    entry.update(approval=approval, outcome=outcome)
    record["audit_files"]["audit-test.jsonl"][index] = json.dumps(entry)
    assert bench.classify(record, "unrelated-secret")[0] == "stop"


def test_duplicate_audit_and_wrong_post_count_stop():
    record = _passing_record()
    record["audit_files"]["audit-test.jsonl"].append(record["audit_files"]["audit-test.jsonl"][0])
    assert bench.classify(record, "unrelated-secret")[0] == "stop"
    record = _passing_record()
    record["posts_sent"] = 0
    assert bench.classify(record, "unrelated-secret")[0] == "stop"


def test_outside_repo_and_existing_output_refusal(tmp_path):
    assert bench._outside_repo(str(tmp_path / "record.json"))
    assert not bench._outside_repo(os.path.join(REPO_ROOT, "record.json"))
    existing = tmp_path / "exists.json"
    existing.write_text("keep", encoding="utf-8")
    with pytest.raises(bench._UsageError):
        bench._reserve(str(existing), bench.evidence_template())
    assert existing.read_text(encoding="utf-8") == "keep"


def test_post_step_does_not_copy_untrusted_secret_or_mac():
    class Response:
        status_code = 403
        def json(self):
            return {"permit": {"mac": "sensitive"}, "status": "sensitive"}
    assert bench._step(Response()) == {"http": 403, "permit": None, "outcome": None}


def test_level_http_failure_is_not_absence():
    class Client:
        async def get(self, path):
            return type("Response", (), {"status_code": 500})()
    with pytest.raises(ValueError):
        asyncio.run(bench._get_levels(Client()))


def test_ingest_cannot_override_audit_decision():
    record = _passing_record()
    entry = json.loads(record["audit_files"]["audit-test.jsonl"][0])
    entry["approval"] = "none"
    record["audit_files"]["audit-test.jsonl"][0] = json.dumps(entry)
    bench._ingest_entries(record, json.dumps({"h1": {"call_id": "h1", "element_gone": True,
                                                     "approval": "accepted", "outcome": "success"}}))
    assert bench.classify(record, "unrelated-secret")[0] == "stop"


def test_local_policy_store_uses_only_scratch_files(monkeypatch, tmp_path):
    import policy
    source = tmp_path / "policy.py"
    base = tmp_path / policy.BASE_FILE
    with open(os.path.join(REPO_ROOT, policy.BASE_FILE), "rb") as handle:
        base.write_bytes(handle.read())
    monkeypatch.setattr(policy, "__file__", str(source))
    monkeypatch.delenv(policy.POLICY_FILE_ENV, raising=False)
    monkeypatch.setattr(bench, "_policy", lambda: policy)
    original_lookup = policy.operator_path
    snapshot = asyncio.run(bench._safe_policy_snapshot())
    assert snapshot["source"] == "base" and snapshot["blocked"] is False
    assert policy.operator_path is original_lookup


@pytest.mark.parametrize("scenario,index", [("h4", 4), ("h5", 5)])
def test_audit_must_prove_same_request_and_fractional_arguments(scenario, index):
    record = _passing_record()
    entry = json.loads(record["audit_files"]["audit-test.jsonl"][index])
    entry["args"] = {"element_ids": [999]}
    record["audit_files"]["audit-test.jsonl"][index] = json.dumps(entry)
    assert bench.classify(record, "unrelated-secret")[0] == "stop"


def test_network_operator_pointer_is_refused_before_target_open(monkeypatch, tmp_path):
    import policy
    with open(os.path.join(REPO_ROOT, policy.BASE_FILE), "rb") as handle:
        (tmp_path / policy.BASE_FILE).write_bytes(handle.read())
    (tmp_path / policy.POLICY_SOURCE_FILE).write_text("//never-contact/policy.toml", encoding="utf-8")
    monkeypatch.setattr(policy, "__file__", str(tmp_path / "policy.py"))
    monkeypatch.delenv(policy.POLICY_FILE_ENV, raising=False)
    monkeypatch.setattr(bench, "_policy", lambda: policy)
    real_check = bench._local_path
    monkeypatch.setattr(bench, "_local_path", lambda path: None if path.startswith("//") else real_check(path))
    with pytest.raises(ValueError):
        asyncio.run(bench._safe_policy_snapshot())
