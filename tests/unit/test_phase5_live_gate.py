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
import shutil
import subprocess
import types

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


class _Reply(object):
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body, sort_keys=True)

    def json(self):
        return self._body


class _Client(object):
    def __init__(self, stage, post_failure=None):
        self.stage = stage
        self.post_failure = post_failure
        self.posts = []
        self.gets = []
        self.accepted = ""

    async def get(self, path):
        self.gets.append(path)
        if path.endswith("/status/"):
            return _Reply(200, _status(self.stage))
        if path.endswith("/documents/"):
            return _Reply(200, {"documents": [{"document": "sel-1", "title": "Project1"}]})
        if path.endswith("/list_levels/"):
            return _Reply(200, {"levels": [{"name": self.accepted}] if self.stage != "corrupt" else []})
        raise AssertionError("unexpected GET {}".format(path))

    async def post(self, path, content, headers):
        body = json.loads(content)
        self.posts.append((path, body, headers))
        if self.post_failure and len(self.posts) == self.post_failure:
            raise RuntimeError("planned direct failure")
        route = path.rsplit("/genpro_revit_mcp", 1)[-1]
        if route in ("/create_level/", "/execute_code/"):
            envelope = body.get("_mcp")
            if envelope is None:
                return _Reply(401, _auth("missing"))
            return _Reply(401, _auth("mismatch"))
        if route == "/document_levels/":
            if body.get("document") != "sel-1":
                return _Reply(400, {"error_code": "document-selector-required"})
            return _Reply(200, {"levels": []})
        raise AssertionError("unexpected POST {}".format(path))

    async def aclose(self):
        return None


class _Bridge(object):
    def __init__(self, stage):
        self.stage = stage
        self._secret_cache = None
        self.reset_calls = 0
        self.posts = []
        self.gets = []
        async def getting(endpoint, *args, **kwargs):
            return await self._get(endpoint, *args, **kwargs)
        getting.revit_target = "revit1"
        getting.discover_targets = lambda: []
        getting.secret_fingerprint = self.loaded_secret_fingerprint
        self.revit_get = getting
        self.revit_post = self._post
        self.revit_image = None

    @staticmethod
    def secret_fingerprint(value):
        return "wrong-fingerprint" if value == proc.WRONG_SECRET else FP

    @staticmethod
    def loaded_secret_fingerprint():
        return FP

    @staticmethod
    def listener_snapshot(ports):
        return {ports[0]: [4242]}

    def reset_secret_cache(self):
        self.reset_calls += 1
        self._secret_cache = None

    async def _get(self, endpoint, *args, **kwargs):
        self.gets.append(endpoint)
        if endpoint == "/status/":
            return _status(self.stage)
        raise AssertionError("unexpected bridge GET {}".format(endpoint))

    async def _post(self, endpoint, data, *args, **kwargs):
        self.posts.append((endpoint, data, self._secret_cache))
        if self.stage == "corrupt":
            return "Error: 423 - " + json.dumps(_integrity(), sort_keys=True)
        if self._secret_cache == proc.WRONG_SECRET:
            return "Error: 401 - " + json.dumps(_auth("mismatch"), sort_keys=True) + "\nVerified Revit process: PID 4242"
        levels = data.get("levels") if isinstance(data, dict) else None
        if isinstance(levels, list) and levels:
            self.client.accepted = levels[0]["name"]
        return _success()


def _args(tmp_path, stage="match", module=None):
    return types.SimpleNamespace(stage=stage, out=str(tmp_path / "record.json"), port=48884, module=module)


def _state(stage):
    return {"secret_file_present": True, "manifest_present": stage != "cleanup",
            "probe_present": stage == "corrupt", "module_clean": stage != "corrupt", "module_exists": True}


def _run_with_fakes(monkeypatch, tmp_path, stage="match", module=None, client=None, bridge=None):
    client = client or _Client(stage)
    bridge = bridge or _Bridge(stage)
    bridge.client = client
    monkeypatch.setattr(proc, "_bridge", lambda: bridge)
    monkeypatch.setattr(proc, "_direct_client", lambda port: client)
    monkeypatch.setattr(proc, "_repo_state", lambda current, selected: _state(current))
    client.accepted = "P5_P_CREATE_"
    if stage != "match":
        monkeypatch.setattr(proc, "_valid_module", lambda repo, selected, require_clean=True: None)
    return proc.main(["run", "--stage", stage, "--out", str(tmp_path / "record.json"), "--port", "48884"] + ([] if module is None else ["--module", module])), client, bridge, tmp_path / "record.json"


def test_run_match_records_real_tools_and_direct_wire_contract(monkeypatch, tmp_path, capsys):
    code, client, bridge, record_path = _run_with_fakes(monkeypatch, tmp_path)
    captured = capsys.readouterr()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert code == 0, proc.classify_stage("match", record)
    assert proc.classify_stage("match", record)["verdict"] == "ok"
    assert proc.SENTINEL_OK in captured.out and "STAGE=match" in captured.out and "POSTS_SENT=7" in captured.out
    assert record["posts_sent"] == 7 and bridge.reset_calls == 1
    assert all(headers["Content-Type"] == "text/plain; charset=utf-8" for _path, _body, headers in client.posts)
    assert "_mcp" not in client.posts[0][1] and "_mcp" not in client.posts[2][1]
    assert client.posts[1][1]["_mcp"] == {"secret": proc.WRONG_SECRET}
    assert client.posts[4][1]["_mcp"] == {"secret": proc.WRONG_SECRET}


@pytest.mark.parametrize("stage,module,expected", [("corrupt", MODULE, 4), ("cleanup", MODULE, 1)])
def test_run_other_stages_classify_ok(monkeypatch, tmp_path, capsys, stage, module, expected):
    code, _client, _bridge, record_path = _run_with_fakes(monkeypatch, tmp_path, stage, module)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert code == 0 and record["posts_sent"] == expected
    assert proc.classify_stage(stage, record)["verdict"] == "ok"
    assert "POSTS_SENT={}".format(expected) in capsys.readouterr().out


def test_run_preflight_stop_persists_zero_post_record(monkeypatch, tmp_path, capsys):
    client = _Client("match")
    bridge = _Bridge("match")
    bridge.listener_snapshot = lambda ports: {ports[0]: [1, 2]}
    code, client, _bridge, record_path = _run_with_fakes(monkeypatch, tmp_path, client=client, bridge=bridge)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    captured = capsys.readouterr()
    assert code == 1 and record["posts_sent"] == 0 and not client.posts
    assert proc.SENTINEL_STOP in captured.out and "POSTS_SENT=0" in captured.out and proc.MSG_NO_WRITE in captured.out


@pytest.mark.parametrize("change", ["exists", "inside", "missing-dir", "secret", "wrong-fingerprint", "stage"])
def test_run_refusals_do_not_write_or_request(monkeypatch, tmp_path, change):
    bridge = _Bridge("match")
    client = _Client("match")
    args = _args(tmp_path)
    if change == "exists":
        (tmp_path / "record.json").write_text("already", encoding="utf-8")
    elif change == "inside":
        args.out = os.path.join(proc.REPO_ROOT, "forbidden-evidence.json")
    elif change == "missing-dir":
        args.out = str(tmp_path / "missing" / "record.json")
    elif change == "secret":
        monkeypatch.setattr(proc, "_repo_state", lambda stage, module: dict(_state(stage), secret_file_present=False))
    elif change == "wrong-fingerprint":
        bridge.loaded_secret_fingerprint = lambda: "wrong-fingerprint"
    elif change == "stage":
        monkeypatch.setattr(proc, "_repo_state", lambda stage, module: dict(_state(stage), manifest_present=False))
    monkeypatch.setattr(proc, "_bridge", lambda: bridge)
    monkeypatch.setattr(proc, "_direct_client", lambda port: client)
    code = proc._cmd_run
    assert proc.main(["run", "--stage", "match", "--out", args.out]) == 2
    assert not client.gets and not client.posts
    assert not os.path.exists(args.out) or change == "exists"


def test_run_continues_after_counted_direct_post_failure(monkeypatch, tmp_path):
    client = _Client("match", post_failure=1)
    code, client, _bridge, record_path = _run_with_fakes(monkeypatch, tmp_path, client=client)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert code == 1 and record["posts_sent"] == 7
    assert record["steps"]["n_missing"]["sent"] is True
    assert "RuntimeError" in record["steps"]["n_missing"]["error"]
    assert len(client.posts) == 5


def _run_git(args, repo):
    result = subprocess.run(["git"] + list(args), cwd=repo, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _init_repo(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git is unavailable")
    repo = tmp_path / "repo"
    (repo / "revit_mcp").mkdir(parents=True)
    (repo / ".gitignore").write_text("_manifest.json\n", encoding="utf-8")
    (repo / "revit_mcp" / "detail.py").write_bytes(b"# -*- coding: utf-8 -*-\nvalue = 1\n")
    (repo / "revit_mcp" / "crlf.py").write_bytes(b"# -*- coding: utf-8 -*-\r\nvalue = 1\r\n")
    _run_git(["init"], str(repo))
    _run_git(["config", "user.email", "tests@example.invalid"], str(repo))
    _run_git(["config", "user.name", "Tests"], str(repo))
    _run_git(["add", "."], str(repo))
    _run_git(["commit", "-m", "fixture"], str(repo))
    (repo / "_manifest.json").write_text("{}\n", encoding="utf-8")
    return repo


def test_corrupt_cmd_and_restore_preserve_only_named_module(tmp_path):
    repo = _init_repo(tmp_path)
    proc.corrupt(str(repo), MODULE)
    source = (repo / MODULE).read_bytes()
    assert source.endswith(b"restore with tests/test_phase5_live_gate.py restore\n")
    assert (repo / proc.PROBE_FILE).read_bytes().startswith(b"# -*- coding: utf-8 -*-\n")
    assert _run_git(["status", "--porcelain"], str(repo))[1].splitlines() == ["M revit_mcp/detail.py", "?? revit_mcp/_zz_probe.py"]
    assert proc.restore(str(repo), MODULE) == []
    assert not (repo / "_manifest.json").exists() and not (repo / proc.PROBE_FILE).exists()
    assert _run_git(["status", "--porcelain"], str(repo))[1] == ""
    assert proc.restore(str(repo), MODULE) == []


def test_corrupt_preserves_crlf_and_refuses_unsafe_states(tmp_path):
    repo = _init_repo(tmp_path)
    proc.corrupt(str(repo), "revit_mcp/crlf.py")
    assert b"\r\n# phase5 live gate:" in (repo / "revit_mcp" / "crlf.py").read_bytes()
    assert proc.restore(str(repo), "revit_mcp/crlf.py") == []
    with pytest.raises(ValueError): proc.corrupt(str(repo), "revit_mcp/_private.py")
    with pytest.raises(ValueError): proc.corrupt(str(repo), "tools/x.py")
    (repo / "revit_mcp" / "detail.py").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError): proc.corrupt(str(repo), MODULE)


def test_corrupt_refuses_missing_manifest_or_existing_probe(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "_manifest.json").unlink()
    with pytest.raises(ValueError, match="manifest"):
        proc.corrupt(str(repo), MODULE)
    (repo / "_manifest.json").write_text("{}\n", encoding="utf-8")
    probe = repo / proc.PROBE_FILE
    probe.write_text("# existing\n", encoding="utf-8")
    with pytest.raises(ValueError, match="probe"):
        proc.corrupt(str(repo), MODULE)


def test_restore_incomplete_when_git_cannot_restore(monkeypatch, tmp_path):
    repo = _init_repo(tmp_path)
    proc.corrupt(str(repo), MODULE)
    original = proc._git

    def failing(args, current):
        if args[:1] == ["checkout"]:
            return 1, "", "planned failure"
        return original(args, current)

    monkeypatch.setattr(proc, "_git", failing)
    reasons = proc.restore(str(repo), MODULE)
    assert any("detail.py" in item for item in reasons)


class _SecretBridge(object):
    def __init__(self, secret): self.secret = secret
    def load_secret(self): return self.secret


def test_scan_secret_has_exact_status_without_secret_output(tmp_path, capsys):
    secret = "a-secret-that-must-not-print"
    clean = tmp_path / "clean.json"; clean.write_text("{}", encoding="utf-8")
    found = tmp_path / "found.json"; found.write_text("x {} y".format(secret), encoding="utf-8")
    absent = _SecretBridge(None)
    assert proc.scan_secret([str(clean)], _SecretBridge(secret)) == (0, None)
    assert proc.scan_secret([str(found)], _SecretBridge(secret)) == (1, str(found))
    assert proc.scan_secret([str(clean)], absent) == (2, None)
    assert secret not in capsys.readouterr().out + capsys.readouterr().err


def test_scan_secret_command_prints_only_status_tokens(monkeypatch, tmp_path, capsys):
    secret = "secret-never-in-console"
    clean = tmp_path / "clean.json"; clean.write_text("{}", encoding="utf-8")
    found = tmp_path / "found.json"; found.write_text(secret, encoding="utf-8")
    monkeypatch.setattr(proc, "_bridge", lambda: _SecretBridge(secret))
    assert proc.main(["scan-secret", str(clean)]) == 0
    assert capsys.readouterr().out.strip() == "SECRET_ABSENT"
    assert proc.main(["scan-secret", str(found)]) == 1
    output = capsys.readouterr().out.strip()
    assert output == "SECRET_FOUND {}".format(found)
    assert secret not in output
    monkeypatch.setattr(proc, "_bridge", lambda: _SecretBridge(None))
    assert proc.main(["scan-secret", str(clean)]) == 2
    assert capsys.readouterr().out.strip() == "SECRET_UNAVAILABLE"


def test_error_body_ignores_trailing_bridge_line():
    text = "Error: 401 - " + json.dumps(_auth("mismatch")) + "\nVerified Revit process: PID 4242"
    assert proc._error_body(text, 401) == _auth("mismatch")
    assert proc._error_body("Error: 401 - not json", 401) is None
    assert proc._error_body("Error: 423 - {}", 401) is None


def test_document_levels_steps_carry_the_preflight_selector(monkeypatch, tmp_path):
    client = _Client("match")
    _run_with_fakes(monkeypatch, tmp_path, "match", client=client)
    bodies = [body for path, body, _ in client.posts if path.endswith("/document_levels/")]
    assert [body["document"] for body in bodies] == ["sel-1", "sel-1"]
    assert "_mcp" not in bodies[0] and "_mcp" in bodies[1]
