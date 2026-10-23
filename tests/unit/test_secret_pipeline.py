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

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
