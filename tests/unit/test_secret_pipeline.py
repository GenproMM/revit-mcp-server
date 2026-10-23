# -*- coding: utf-8 -*-
"""Build-side secret tooling: deploy/secret_tool.py, scripts/dev_secret.py, ignore rules.

secret_tool creates the one fleet secret exactly once, stages it byte-for-byte
into an artifact and verifies the pair, without ever printing the value.
Every secret path here lives under tmp_path, never in the repository. Plan
03-07 adds the build-script order tests to this file.

Needs no Revit.
"""
import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys

import pytest

from revit_mcp import integrity, trust

REPO =os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN = re.compile(rb"\A[A-Za-z0-9_-]{43,}\Z")


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, relpath))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def secret_tool():
    return _load("deploy_secret_tool", os.path.join("deploy", "secret_tool.py"))


def _read(path):
    with open(str(path), "rb") as handle:
        return handle.read()


def _write(path, data):
    parent = os.path.dirname(str(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(str(path), "wb") as handle:
        handle.write(data)


# --- ensure_secret ---------------------------------------------------------


def test_ensure_creates_token_once(secret_tool, tmp_path):
    path = tmp_path / "deep" / "er" / "secret"
    assert secret_tool.ensure_secret(str(path)) is True
    first = _read(path)
    assert TOKEN.match(first), "token must be 43+ URL-safe ASCII chars, no newline"
    assert secret_tool.ensure_secret(str(path)) is False
    assert _read(path) == first


def test_ensure_two_dirs_give_different_values(secret_tool, tmp_path):
    a = tmp_path / "a" / "secret"
    b = tmp_path / "b" / "secret"
    secret_tool.ensure_secret(str(a))
    secret_tool.ensure_secret(str(b))
    assert _read(a) != _read(b)


_BAD_FILES = {
    "empty": b"",
    "utf8_bom": b"\xef\xbb\xbf" + b"A" * 43,
    "utf16_le": ("A" * 43).encode("utf-16"),
    "utf16_be": b"\xfe\xff" + b"A" * 43,
    "trailing_newline": b"A" * 43 + b"\n",
    "trailing_crlf": b"A" * 43 + b"\r\n",
    "space": b"A" * 20 + b" " + b"B" * 20,
    "nul": b"A" * 20 + b"\x00" + b"B" * 20,
    "non_ascii": ("A" * 20 + "Ж" + "B" * 20).encode("utf-8"),
    "too_short": b"A" * 15,
}


@pytest.mark.parametrize("label", sorted(_BAD_FILES))
def test_ensure_rejects_invalid_existing_and_leaves_it(secret_tool, tmp_path, label):
    path = tmp_path / "secret"
    _write(path, _BAD_FILES[label])
    with pytest.raises(secret_tool.SecretToolError):
        secret_tool.ensure_secret(str(path))
    assert _read(path) == _BAD_FILES[label]


def test_ensure_keeps_valid_existing(secret_tool, tmp_path):
    path = tmp_path / "secret"
    _write(path, b"A" * 16)
    assert secret_tool.ensure_secret(str(path)) is False
    assert _read(path) == b"A" * 16


def test_ensure_race_file_appears_first(secret_tool, tmp_path, monkeypatch):
    """Another build creates the file between the exists check and O_EXCL."""
    path = tmp_path / "secret"
    _write(path, b"R" * 43)
    real_exists = os.path.exists
    target = os.path.abspath(str(path))

    def lying_exists(candidate):
        if os.path.abspath(str(candidate)) == target:
            return False
        return real_exists(candidate)

    monkeypatch.setattr(secret_tool.os.path, "exists", lying_exists)
    assert secret_tool.ensure_secret(str(path)) is False
    assert _read(path) == b"R" * 43


def test_ensure_race_with_invalid_existing_raises(secret_tool, tmp_path, monkeypatch):
    path = tmp_path / "secret"
    _write(path, b"")
    target = os.path.abspath(str(path))
    real_exists = os.path.exists

    def lying_exists(candidate):
        if os.path.abspath(str(candidate)) == target:
            return False
        return real_exists(candidate)

    monkeypatch.setattr(secret_tool.os.path, "exists", lying_exists)
    with pytest.raises(secret_tool.SecretToolError):
        secret_tool.ensure_secret(str(path))
    assert _read(path) == b""


# --- stage_secret / verify_pair --------------------------------------------


def test_stage_makes_dest_byte_equal_and_overwrites_stale(secret_tool, tmp_path):
    src = tmp_path / "share" / "secret"
    dest = tmp_path / "payload" / "ext" / "_bridge_secret"
    _write(dest, b"stale-stale-stale-stale")
    secret_tool.stage_secret(str(src), str(dest))
    assert _read(dest) == _read(src)
    secret_tool.verify_pair(str(src), str(dest))


def test_stage_creates_dest_parent(secret_tool, tmp_path):
    src = tmp_path / "secret"
    dest = tmp_path / "new" / "dir" / "art"
    secret_tool.stage_secret(str(src), str(dest))
    assert os.path.isfile(str(dest))


def test_verify_pair_artifact_missing(secret_tool, tmp_path):
    src = tmp_path / "secret"
    secret_tool.ensure_secret(str(src))
    with pytest.raises(secret_tool.SecretToolError):
        secret_tool.verify_pair(str(src), str(tmp_path / "nope"))


def test_verify_pair_secret_missing(secret_tool, tmp_path):
    art = tmp_path / "art"
    _write(art, b"A" * 43)
    with pytest.raises(secret_tool.SecretToolError):
        secret_tool.verify_pair(str(tmp_path / "nope"), str(art))


def test_verify_pair_differs_by_one_byte(secret_tool, tmp_path):
    src = tmp_path / "secret"
    art = tmp_path / "art"
    secret_tool.stage_secret(str(src), str(art))
    data = bytearray(_read(art))
    data[0] = ord("A") if data[0] != ord("A") else ord("B")
    _write(art, bytes(data))
    with pytest.raises(secret_tool.SecretToolError) as info:
        secret_tool.verify_pair(str(src), str(art))
    assert "byte for byte" in str(info.value)


def test_verify_pair_artifact_with_bom(secret_tool, tmp_path):
    src = tmp_path / "secret"
    art = tmp_path / "art"
    secret_tool.stage_secret(str(src), str(art))
    _write(art, b"\xef\xbb\xbf" + _read(art))
    with pytest.raises(secret_tool.SecretToolError):
        secret_tool.verify_pair(str(src), str(art))


def test_validate_secret_bytes_accepts_token(secret_tool):
    secret_tool.validate_secret_bytes(b"A" * 43, "label")


# --- main / no-print --------------------------------------------------------


def test_main_ensure_stage_verify_return_zero(secret_tool, tmp_path, capsys):
    src = str(tmp_path / "s" / "secret")
    dest = str(tmp_path / "p" / "art")
    assert secret_tool.main(["ensure", "--secret-file", src]) == 0
    assert secret_tool.main(["stage", "--secret-file", src, "--dest", dest]) == 0
    assert secret_tool.main(["verify", "--secret-file", src, "--artifact", dest]) == 0
    out = capsys.readouterr().out
    assert "SECRET ensure: created" in out
    assert "SECRET staged:" in out
    assert "SECRET verify: ok" in out


def test_main_ensure_second_run_reports_unchanged(secret_tool, tmp_path, capsys):
    src = str(tmp_path / "secret")
    secret_tool.main(["ensure", "--secret-file", src])
    capsys.readouterr()
    assert secret_tool.main(["ensure", "--secret-file", src]) == 0
    assert "exists, left unchanged" in capsys.readouterr().out


def test_main_mismatching_verify_returns_one(secret_tool, tmp_path, capsys):
    src = str(tmp_path / "secret")
    dest = str(tmp_path / "art")
    secret_tool.main(["stage", "--secret-file", src, "--dest", dest])
    capsys.readouterr()
    _write(dest, b"B" * 43)
    assert secret_tool.main(["verify", "--secret-file", src, "--artifact", dest]) == 1
    assert "ERROR:" in capsys.readouterr().err


def test_secret_never_printed_on_success_paths(secret_tool, tmp_path, capsys):
    src = tmp_path / "secret"
    dest = tmp_path / "art"
    secret_tool.main(["ensure", "--secret-file", str(src)])
    secret_tool.main(["stage", "--secret-file", str(src), "--dest", str(dest)])
    secret_tool.main(["verify", "--secret-file", str(src), "--artifact", str(dest)])
    value = _read(src).decode("ascii")
    captured = capsys.readouterr()
    assert value not in captured.out
    assert value not in captured.err


def test_secret_never_printed_on_mismatch_failure(secret_tool, tmp_path, capsys):
    src = tmp_path / "secret"
    dest = tmp_path / "art"
    secret_tool.main(["stage", "--secret-file", str(src), "--dest", str(dest)])
    value = _read(src).decode("ascii")
    other = "Z" * 43
    _write(dest, other.encode("ascii"))
    capsys.readouterr()
    assert secret_tool.main(["verify", "--secret-file", str(src), "--artifact", str(dest)]) == 1
    captured = capsys.readouterr()
    for stream in (captured.out, captured.err):
        assert value not in stream
        assert other not in stream


@pytest.mark.parametrize("label", sorted(_BAD_FILES))
def test_secret_never_printed_on_invalid_file_failure(secret_tool, tmp_path, capsys, label):
    # A malformed-but-printable secret file must not be echoed by any failure path.
    src = tmp_path / "secret"
    raw = _BAD_FILES[label]
    _write(src, raw)
    for argv in (
        ["ensure", "--secret-file", str(src)],
        ["stage", "--secret-file", str(src), "--dest", str(tmp_path / "art")],
        ["verify", "--secret-file", str(src), "--artifact", str(src)],
    ):
        assert secret_tool.main(argv) == 1
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    text = captured.out + captured.err
    for chunk in re.findall(rb"[A-Za-z0-9_-]{8,}", raw):
        assert chunk.decode("ascii") not in text


def test_secret_never_printed_on_missing_artifact(secret_tool, tmp_path, capsys):
    src = tmp_path / "secret"
    secret_tool.main(["ensure", "--secret-file", str(src)])
    value = _read(src).decode("ascii")
    capsys.readouterr()
    assert secret_tool.main(["verify", "--secret-file", str(src), "--artifact", str(tmp_path / "x")]) == 1
    captured = capsys.readouterr()
    assert value not in captured.out + captured.err


def _assert_py38_clean(relpath):
    path = os.path.join(REPO, relpath)
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source, feature_version=(3, 8))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.AnnAssign), "annotation at line {}".format(node.lineno)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.returns is None, "return annotation on {}".format(node.name)
            args = node.args
            every = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
            if args.vararg:
                every.append(args.vararg)
            if args.kwarg:
                every.append(args.kwarg)
            for arg in every:
                assert arg.annotation is None, "annotation on {}".format(arg.arg)


def test_secret_tool_parses_as_python_38():
    _assert_py38_clean(os.path.join("deploy", "secret_tool.py"))


# --- scripts/dev_secret.py and the ignore rules ----------------------------


@pytest.fixture(scope="module")
def dev_secret():
    return _load("scripts_dev_secret", os.path.join("scripts", "dev_secret.py"))


def test_dev_secret_creates_once_and_never_prints(dev_secret, tmp_path, capsys):
    repo = tmp_path / "checkout"
    target = repo / "revit_mcp" / "_bridge_secret"
    assert dev_secret.main(["--repo", str(repo)]) == 0
    first = _read(target)
    assert TOKEN.match(first)
    assert dev_secret.main(["--repo", str(repo)]) == 0
    assert _read(target) == first
    captured = capsys.readouterr()
    assert first.decode("ascii") not in captured.out + captured.err
    assert "created" in captured.out
    assert "exists, left unchanged" in captured.out


def test_dev_secret_invalid_existing_fails_and_keeps_file(dev_secret, tmp_path, capsys):
    target = tmp_path / "revit_mcp" / "_bridge_secret"
    _write(target, b"short")
    assert dev_secret.main(["--repo", str(tmp_path)]) == 1
    assert _read(target) == b"short"
    assert "ERROR:" in capsys.readouterr().err


def test_dev_secret_default_repo_is_parent_of_scripts():
    source = open(os.path.join(REPO, "scripts", "dev_secret.py"), encoding="utf-8").read()
    assert "ensure_secret(" in source
    assert "_bridge_secret" in source


def test_dev_secret_parses_as_python_38():
    _assert_py38_clean(os.path.join("scripts", "dev_secret.py"))


def _gitignore_lines():
    with open(os.path.join(REPO, ".gitignore"), encoding="utf-8") as handle:
        return [line.strip() for line in handle.read().splitlines()]


def test_gitignore_lists_both_artifacts_as_whole_lines():
    lines = _gitignore_lines()
    assert "_bridge_secret" in lines
    assert "_manifest.json" in lines


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_gitignore_check_ignore_reports_both_ignored():
    for name in ("revit_mcp/_bridge_secret", "_manifest.json"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", name], cwd=REPO, capture_output=True
        )
        assert result.returncode == 0, "{} is not git-ignored".format(name)


# --- build scripts: config.cmd and publish-extension.cmd (plan 03-07) -------

CONFIG_CMD = os.path.join("deploy", "config.cmd")
PUBLISH_CMD = os.path.join("deploy", "publish-extension.cmd")
BUILD_PAYLOAD_CMD = os.path.join("deploy", "build-payload.cmd")
REAL_SHARE_DEFAULT = "\\\\srv-dfs\\BIM\\06_RevitMCP"
SECRET_LINE = 'if not defined MCP_SECRET_FILE set "MCP_SECRET_FILE=%MCP_SHARE_ROOT%\\_build\\bridge_secret"'


def _cmd_lines(relpath):
    with open(os.path.join(REPO, relpath), encoding="utf-8") as handle:
        return [line.strip() for line in handle.read().splitlines()]


def _code_lines(lines):
    """(index, line) of every line that is not a rem comment or blank."""
    return [(i, ln) for i, ln in enumerate(lines)
            if ln and not ln.lower().startswith("rem ") and ln.lower() != "rem"]


def _find(lines, predicate, label):
    hits = [i for i, ln in _code_lines(lines) if predicate(ln)]
    assert hits, "no line for {}".format(label)
    return hits[0]


def _logical(lines, index):
    """The line at ``index`` joined with its ^ continuation lines."""
    text = lines[index]
    while text.endswith("^") and index + 1 < len(lines):
        index += 1
        text = text[:-1].rstrip() + " " + lines[index]
    return text


def test_config_defines_secret_file_once_after_share_root():
    lines = _cmd_lines(CONFIG_CMD)
    hits = [i for i, ln in enumerate(lines) if ln == SECRET_LINE]
    assert len(hits) == 1, "expected exactly one MCP_SECRET_FILE default line"
    assert sum(1 for ln in lines if ln.startswith("if not defined MCP_SECRET_FILE")) == 1
    root = _find(lines, lambda ln: ln.startswith("if not defined MCP_SHARE_ROOT"), "MCP_SHARE_ROOT")
    assert hits[0] > root


def test_config_secret_default_outside_published_trees():
    default = SECRET_LINE.split("MCP_SECRET_FILE=", 1)[1].rstrip('"').lower()
    assert "\\ext\\" not in default
    assert "\\payload\\" not in default
    assert default.startswith("%mcp_share_root%\\_build\\")


def test_config_documents_the_secret_honestly():
    text = "\n".join(_cmd_lines(CONFIG_CMD)).lower()
    assert "network" in text or "lan" in text
    assert "never regenerat" in text or "not regenerat" in text or "once" in text
    assert "rotate" in text or "rotation" in text


def test_publish_order_lines_strictly_increasing():
    lines = _cmd_lines(PUBLISH_CMD)
    order = [
        ("config", lambda ln: ln.startswith('call "%~dp0config.cmd"')),
        ("find-python", lambda ln: ln.startswith('call "%~dp0find-python.cmd"')),
        ("pyexe guard", lambda ln: ln.startswith("if not defined MCP_PYEXE")),
        ("revit_mcp robocopy", lambda ln: ln.lower().startswith('robocopy "%repo%\\revit_mcp"')),
        ("secret stage", lambda ln: 'secret_tool.py" stage' in ln),
        ("manifest", lambda ln: 'make_manifest.py" --repo' in ln),
        ("installer robocopy",
         lambda ln: ln.lower().startswith('robocopy "%~dp0." "%mcp_share_root%\\install"')),
    ]
    indexes = [_find(lines, pred, label) for label, pred in order]
    assert indexes == sorted(set(indexes)), dict(zip([o[0] for o in order], indexes))


def test_publish_order_pyexe_guard_stops_with_error():
    lines = _cmd_lines(PUBLISH_CMD)
    guard = lines[_find(lines, lambda ln: ln.startswith("if not defined MCP_PYEXE"), "guard")]
    assert "ERROR:" in guard
    assert "exit /b 1" in guard


def test_publish_order_revit_mcp_robocopy_excludes_local_artifacts():
    lines = _cmd_lines(PUBLISH_CMD)
    index = _find(lines, lambda ln: ln.lower().startswith('robocopy "%repo%\\revit_mcp"'), "robocopy")
    tokens = _logical(lines, index).split()
    assert "/XF" in tokens
    names = []
    for token in tokens[tokens.index("/XF") + 1:]:
        if token.startswith("/"):
            break
        names.append(token)
    for needed in ("*.pyc", "_bridge_secret", "_manifest.json"):
        assert needed in names, "/XF list lacks {}: {}".format(needed, names)


def test_publish_order_stage_and_manifest_arguments():
    lines = _cmd_lines(PUBLISH_CMD)
    stage = lines[_find(lines, lambda ln: 'secret_tool.py" stage' in ln, "stage")]
    assert stage.startswith('"%MCP_PYEXE%" "%~dp0secret_tool.py" stage')
    assert '--secret-file "%MCP_SECRET_FILE%"' in stage
    assert '--dest "%DEST%\\revit_mcp\\_bridge_secret"' in stage
    assert "|| (echo ERROR:" in stage and "exit /b 1)" in stage
    manifest = lines[_find(lines, lambda ln: 'make_manifest.py" --repo' in ln, "manifest")]
    assert manifest.startswith('"%MCP_PYEXE%" "%~dp0make_manifest.py"')
    assert '--repo "%REPO%"' in manifest
    assert '--dest "%DEST%"' in manifest
    assert "|| (echo ERROR:" in manifest and "exit /b 1)" in manifest


def test_publish_order_nothing_copied_into_dest_after_manifest():
    lines = _cmd_lines(PUBLISH_CMD)
    after = _find(lines, lambda ln: 'make_manifest.py" --repo' in ln, "manifest")
    for i, ln in _code_lines(lines):
        if i <= after:
            continue
        verb = ln.split(None, 1)[0].lower()
        if verb in ("copy", "robocopy", "xcopy", "move"):
            assert "%dest%" not in _logical(lines, i).lower(), "line {} writes into DEST".format(i + 1)


def test_publish_order_dest_derivation():
    lines = _cmd_lines(PUBLISH_CMD)
    assigns = [ln for ln in lines if ln.lower().startswith('set "dest=')]
    assert assigns == ['set "DEST=%MCP_SHARE_ROOT%\\ext\\%MCP_EXT_NAME%"']
    installer = lines[_find(lines, lambda ln: ln.lower().startswith('robocopy "%~dp0."'), "installer")]
    assert '"%MCP_SHARE_ROOT%\\install"' in installer


def test_publish_cmd_is_crlf_and_ascii_additions():
    with open(os.path.join(REPO, PUBLISH_CMD), "rb") as handle:
        data = handle.read()
    assert data.count(b"\n") == data.count(b"\r\n")
    data.decode("ascii")


def _scratch_publish_env(tmp_path):
    env = dict(os.environ)
    env["MCP_SHARE_ROOT"] = os.path.join(str(tmp_path), "share")
    env["MCP_SECRET_FILE"] = os.path.join(str(tmp_path), "secret", "bridge_secret")
    env["MCP_EXT_NAME"] = "revit-mcp-server.extension"
    env["MCP_PYEXE"] = sys.executable
    return env


def _assert_scratch(env, tmp_path):
    """Fail (never skip) unless every path the publish writes is under tmp_path."""
    root = os.path.normcase(os.path.realpath(str(tmp_path)))
    share = env.get("MCP_SHARE_ROOT", "")
    targets = [
        ("MCP_SHARE_ROOT", share),
        ("MCP_SECRET_FILE", env.get("MCP_SECRET_FILE", "")),
        ("DEST", os.path.join(share, "ext", env.get("MCP_EXT_NAME", ""))),
        ("installer target", os.path.join(share, "install")),
    ]
    for label, path in targets:
        if not path or path.startswith("\\\\") or path.startswith("//"):
            pytest.fail("{} is empty or a UNC path: {!r}".format(label, path))
        real = os.path.normcase(os.path.realpath(path))
        try:
            inside = os.path.commonpath([root, real]) == root
        except ValueError:  # another drive
            inside = False
        if not inside:
            pytest.fail("{} resolves outside tmp_path: {!r}".format(label, path))


def test_publish_smoke_guard_rejects_real_share(tmp_path):
    env = _scratch_publish_env(tmp_path)
    _assert_scratch(env, tmp_path)  # the scratch env itself is accepted

    bad = dict(env, MCP_SHARE_ROOT=REAL_SHARE_DEFAULT)
    with pytest.raises(pytest.fail.Exception):
        _assert_scratch(bad, tmp_path)

    outside = dict(env, MCP_SECRET_FILE=os.path.join(REPO, "somewhere", "bridge_secret"))
    with pytest.raises(pytest.fail.Exception):
        _assert_scratch(outside, tmp_path)

    escaping = dict(env, MCP_EXT_NAME=os.path.join("..", "..", "..", "escape"))
    with pytest.raises(pytest.fail.Exception):
        _assert_scratch(escaping, tmp_path)


@pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("git") is None or shutil.which("robocopy") is None,
    reason="needs Windows, git and robocopy",
)
def test_publish_smoke_scratch_share(tmp_path):
    env = _scratch_publish_env(tmp_path)
    _assert_scratch(env, tmp_path)  # before anything is spawned: the script rmdirs DEST

    guarded = [os.path.join(REPO, "_manifest.json"),
               os.path.join(REPO, "revit_mcp", "_manifest.json")]
    existed = [os.path.exists(path) for path in guarded]

    result = subprocess.run(
        ["cmd", "/c", r"deploy\publish-extension.cmd"],
        cwd=REPO, env=env, capture_output=True, timeout=180,
    )
    out = result.stdout + result.stderr
    if os.path.isfile(env["MCP_SECRET_FILE"]):
        assert _read(env["MCP_SECRET_FILE"]) not in out, "the publish printed the secret"
    assert result.returncode == 0, out.decode("utf-8", "replace")[-2000:]
    secret_value = _read(env["MCP_SECRET_FILE"])

    ext = os.path.join(env["MCP_SHARE_ROOT"], "ext", env["MCP_EXT_NAME"])
    assert _read(os.path.join(ext, "revit_mcp", "_bridge_secret")) == secret_value
    assert os.path.isfile(os.path.join(ext, "_manifest.json"))
    verdict = integrity.check_integrity(ext)
    assert verdict["state"] == trust.INTEGRITY_MATCH, verdict
    for _, dirs, _ in os.walk(ext):
        assert "__pycache__" not in dirs
    assert [os.path.exists(path) for path in guarded] == existed
