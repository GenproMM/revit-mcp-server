# -*- coding: utf-8 -*-
"""Phase 7 build-time policy tooling (07-04 task 3): stage the operator path, check the file, gate the base.

deploy/policy_tool.py runs as a subprocess with this interpreter, deploy/gate.py is imported
by path for its _base_policy_status. Nothing here touches a share or runs a deploy script.
Needs no Revit.
"""

import importlib.util
import os
import re
import subprocess
import sys

import pytest

import policy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(REPO_ROOT, "deploy", "policy_tool.py")
UNC = r"\\Сервер\Общая папка\operator_policy.toml"
GOOD = 'schema = 1\n[settings]\nconfirm_timeout_s = 200\n'
BAD = 'schema = 1\n[routes."/no_such_route/"]\ndecision = "allow"  # MARKER-NOT-TO-PRINT\n'


def run_tool(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, TOOL] + list(args), capture_output=True,
                          encoding="utf-8", timeout=120, env=env)


def read(path):
    with open(os.path.join(REPO_ROOT, path), "rb") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def gate():
    saved = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location(
            "deploy_gate_policy_under_test", os.path.join(REPO_ROOT, "deploy", "gate.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = saved


# ------------------------------------------------------------------------- stage

def test_stage_writes_exactly_the_path_and_one_lf_without_a_bom(tmp_path):
    dest = tmp_path / "app" / "policy_source"
    out = run_tool("stage", "--policy-file", UNC, "--dest", str(dest))
    assert out.returncode == 0, out.stderr
    assert dest.read_bytes() == UNC.encode("utf-8") + b"\n"
    assert not dest.read_bytes().startswith(b"\xef\xbb\xbf")


def test_the_staged_file_is_what_policy_operator_path_reads_back(tmp_path):
    dest = tmp_path / policy.POLICY_SOURCE_FILE
    assert run_tool("stage", "--policy-file", UNC, "--dest", str(dest)).returncode == 0
    assert policy.operator_path(str(tmp_path)) == UNC


def test_stage_without_a_policy_file_value_exits_2(tmp_path):
    dest = str(tmp_path / "policy_source")
    assert run_tool("stage", "--dest", dest).returncode == 2
    assert run_tool("stage", "--policy-file", "", "--dest", dest).returncode == 2
    assert run_tool("stage", "--policy-file", "   ", "--dest", dest).returncode == 2
    assert not os.path.exists(dest)


def test_stage_refuses_a_path_with_a_line_break(tmp_path):
    out = run_tool("stage", "--policy-file", "a\nb", "--dest", str(tmp_path / "policy_source"))
    assert out.returncode == 1 and "single-line" in out.stderr
    assert not (tmp_path / "policy_source").exists()


# ------------------------------------------------------------------------- check

def test_check_of_a_missing_file_is_absent_and_exits_0(tmp_path):
    out = run_tool("check", "--policy-file", str(tmp_path / "nothing.toml"))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "POLICY_FILE=absent"


def test_check_of_a_valid_file_prints_the_hash_the_servers_will_report(tmp_path):
    path = tmp_path / "operator_policy.toml"
    path.write_bytes(GOOD.encode("utf-8"))
    out = run_tool("check", "--policy-file", str(path))
    assert out.returncode == 0, out.stderr
    match = re.fullmatch(r"POLICY_FILE=accepted ([0-9a-f]{12})", out.stdout.strip())
    assert match, out.stdout
    assert match.group(1) == policy.policy_hash(read(policy.BASE_FILE), GOOD.encode("utf-8"))


def test_check_of_an_invalid_file_names_the_key_path_warns_and_exits_0(tmp_path):
    path = tmp_path / "operator_policy.toml"
    path.write_bytes(BAD.encode("utf-8"))
    out = run_tool("check", "--policy-file", str(path))
    assert out.returncode == 0, out.stderr
    assert out.stdout.startswith("POLICY_FILE=rejected ") and "no_such_route" in out.stdout
    assert "MARKER-NOT-TO-PRINT" not in out.stdout + out.stderr
    assert "base policy" in out.stderr


def test_check_of_an_unreadable_path_is_unreachable_and_exits_0(tmp_path):
    out = run_tool("check", "--policy-file", str(tmp_path))  # a directory cannot be read as a file
    assert out.returncode == 0, out.stderr
    assert out.stdout.startswith("POLICY_FILE=unreachable ")


def test_check_of_a_partial_file_is_rejected(tmp_path):
    path = tmp_path / "operator_policy.toml"
    path.write_bytes(b'schema = 1\n[routes."/delete_el')
    out = run_tool("check", "--policy-file", str(path))
    assert out.returncode == 0 and out.stdout.startswith("POLICY_FILE=rejected ")


# -------------------------------------------------------------------------- gate

def test_the_gate_accepts_the_repository_base_policy(gate, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    status, message = gate._base_policy_status(REPO_ROOT)
    assert status == "ok"
    assert re.fullmatch(r"base [0-9a-f]{12}", message)
    assert message == "base " + policy.load_base().hash


def test_the_gate_fails_on_a_broken_or_missing_base_policy(gate, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    (tmp_path / policy.BASE_FILE).write_bytes(b"schema = 2\n")
    status, message = gate._base_policy_status(str(tmp_path))
    assert status == "failed" and message.startswith("PolicyError: ") and "schema" in message
    empty = tmp_path / "empty"
    empty.mkdir()
    status, message = gate._base_policy_status(str(empty))
    assert status == "failed" and "PolicyError" in message


def test_gate_main_checks_the_policy_before_spawning_the_server():
    import ast

    with open(os.path.join(REPO_ROOT, "deploy", "gate.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    main = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "main"][0]
    lines = {}
    for node in ast.walk(main):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", None))
            lines.setdefault(name, node.lineno)
    assert lines["_base_policy_status"] < lines["stdio_client"]


# ------------------------------------------------------------------- build scripts

def cmd_lines(path):
    return read(path).decode("utf-8").split("\n")


def test_config_cmd_defines_the_operator_policy_default_beside_the_secret():
    lines = cmd_lines("deploy/config.cmd")
    wanted = 'if not defined MCP_POLICY_FILE set "MCP_POLICY_FILE=%MCP_SHARE_ROOT%\\_build\\operator_policy.toml"'
    assert wanted in lines
    assert lines.index(wanted) > next(
        i for i, ln in enumerate(lines) if ln.startswith("if not defined MCP_SECRET_FILE"))


def test_build_payload_stages_the_path_then_checks_before_the_gate_and_keeps_lf():
    lines = cmd_lines("deploy/build-payload.cmd")
    stage = [i for i, ln in enumerate(lines) if 'policy_tool.py" stage' in ln]
    check = [i for i, ln in enumerate(lines) if 'policy_tool.py" check' in ln]
    gate_run = [i for i, ln in enumerate(lines)
                if 'gate.py"' in ln and ln.startswith('"%MCP_PYEXE%"')]
    secret = [i for i, ln in enumerate(lines) if 'secret_tool.py" stage' in ln]
    assert len(stage) == 1 and len(check) == 1 and len(gate_run) == 1 and len(secret) == 1
    assert secret[0] < stage[0] < check[0] < gate_run[0]
    assert '--policy-file "%MCP_POLICY_FILE%"' in lines[stage[0]]
    assert '--dest "%BUILD%\\app\\policy_source"' in lines[stage[0]]
    assert "|| (echo ERROR:" in lines[stage[0]] and "exit /b 1)" in lines[stage[0]]
    assert "exit" not in lines[check[0]], "a missing or rejected operator file must not fail the build"
    assert all("!" not in lines[i] for i in stage + check), "delayed expansion is on"
    assert b"\r" not in read("deploy/build-payload.cmd") and b"\r" not in read("deploy/config.cmd")


def test_the_staging_line_is_not_mistaken_for_a_root_module_copy():
    pattern = re.compile(r'^\s*copy\s+/y\s+"%REPO%\\([A-Za-z0-9_]+)\.py"', re.IGNORECASE)
    for line in cmd_lines("deploy/build-payload.cmd"):
        if "policy_tool.py" in line:
            assert not pattern.match(line)


def test_policy_tool_keeps_the_encoding_cookie_and_is_not_copied_into_the_payload():
    assert read("deploy/policy_tool.py").startswith(b"# -*- coding: utf-8 -*-")
    assert b"\r" not in read("deploy/policy_tool.py")
    assert not re.search(rb'copy\s+/y\s+"%~dp0policy_tool\.py"', read("deploy/build-payload.cmd"))
