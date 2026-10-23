# -*- coding: utf-8 -*-
"""Hardening of deploy/make_manifest.py: the file list comes only from git
ls-files, and every disagreement with the published tree fails the build.

Needs no Revit. Each temporary git repository is the build checkout and a
separate temporary directory is the published copy (DEST); both live under
pytest's tmp_path, never inside this repository.
"""

import ast
import datetime
import glob
import importlib.util
import json
import os
import shutil
import subprocess
import types

import pytest

from revit_mcp import integrity, trust

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GENERATOR = os.path.join(REPO_ROOT, "deploy", "make_manifest.py")

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")

COMMIT = "0" * 40
NOW = datetime.datetime(2026, 10, 23, 12, 0, 0)

FILES = {
    "startup.py": u"# -*- coding: utf-8 -*-\nSTARTUP = 1\n",
    "extension.json": u'{"name": "genpro_revit_mcp"}\n',
    "revit_mcp/__init__.py": u"# -*- coding: utf-8 -*-\n",
    "revit_mcp/alpha.py": u"# -*- coding: utf-8 -*-\nNAME = u'Стена'\n",
    "revit_mcp/beta.py": u"# -*- coding: utf-8 -*-\nBETA = 2\n",
    "revit_mcp/data.txt": u"tracked but neither .py nor .json\n",
}
EXPECTED_KEYS = sorted(k for k in FILES if k.endswith((".py", ".json")))


@pytest.fixture(scope="module")
def make_manifest():
    spec = importlib.util.spec_from_file_location("make_manifest_hardening", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root, relpath, text):
    path = os.path.join(root, *relpath.split("/"))
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
    return path


def _git(repo, *args):
    return subprocess.run(
        ["git"] + list(args), cwd=repo, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.decode("utf-8")


def _init_repo(repo, files):
    os.makedirs(repo)
    for relpath, text in files.items():
        _write(repo, relpath, text)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "core.autocrlf", "false")
    _git(repo, "config", "core.quotepath", "true")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")


@pytest.fixture()
def tree(tmp_path):
    """(repo, dest): a committed repo and a byte-identical published copy with noise."""
    repo = str(tmp_path / "repo")
    dest = str(tmp_path / "dest")
    _init_repo(repo, FILES)
    os.makedirs(dest)
    for relpath, text in FILES.items():
        _write(dest, relpath, text)
    return repo, dest


def _no_walkers(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the generator walked the filesystem")

    monkeypatch.setattr(os, "walk", refuse)
    monkeypatch.setattr(os, "scandir", refuse)
    monkeypatch.setattr(glob, "glob", refuse)
    monkeypatch.setattr(glob, "iglob", refuse)


# ------------------------------------------------------------------ the list


@needs_git
def test_ls_files_only_list_with_walkers_banned(tree, make_manifest, monkeypatch):
    repo, dest = tree
    listed = _git(repo, "ls-files", "-z", "--", "startup.py", "extension.json", "revit_mcp")
    expected = sorted(n for n in listed.split("\0") if n.endswith((".py", ".json")))
    assert expected == EXPECTED_KEYS
    _no_walkers(monkeypatch)
    manifest = make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)
    assert sorted(manifest["files"]) == expected
    assert manifest["commit"] == COMMIT
    assert manifest["generated_at"] == "2026-10-23T12:00:00Z"


@needs_git
def test_ls_files_untracked_noise_in_dest_never_becomes_an_entry(tree, make_manifest):
    repo, dest = tree
    _write(dest, "revit_mcp/__pycache__/x.cpython-313.pyc", u"not python")
    _write(dest, "revit_mcp/notes.txt", u"scratch")
    _write(dest, "revit_mcp/_bridge_secret", u"0123456789abcdef-never-listed")
    _write(dest, "LICENSE", u"licence text\n")
    _write(dest, "README.md", u"readme\n")
    manifest = make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)
    assert sorted(manifest["files"]) == EXPECTED_KEYS
    text = json.dumps(manifest)
    assert "pycache" not in text and ".pyc" not in text and "_bridge_secret" not in text
    assert "LICENSE" not in text and "notes.txt" not in text


@needs_git
def test_ls_files_hash_is_of_the_dest_copy_not_the_working_tree(tree, make_manifest):
    repo, dest = tree
    _write(repo, "revit_mcp/beta.py", u"# edited in the checkout, not published\n")
    manifest = make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)
    published = (FILES["revit_mcp/beta.py"]).encode("utf-8")
    assert manifest["files"]["revit_mcp/beta.py"] == integrity.hash_normalized(published)


@needs_git
def test_ls_files_non_ascii_tracked_name_survives_into_the_manifest(tmp_path, make_manifest):
    name = u"revit_mcp/модуль.py"
    files = dict(FILES)
    files[name] = u"# -*- coding: utf-8 -*-\nX = 1\n"
    repo = str(tmp_path / "repo")
    dest = str(tmp_path / "dest")
    try:
        _init_repo(repo, files)
    except (OSError, UnicodeError) as exc:
        pytest.skip("filesystem rejects a non-ASCII file name: {}".format(exc))
    os.makedirs(dest)
    for relpath, text in files.items():
        _write(dest, relpath, text)
    manifest = make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)
    assert name in manifest["files"]
    assert sorted(manifest["files"]) == sorted(k for k in files if k.endswith((".py", ".json")))


# ------------------------------------------------------------- build guards


@needs_git
def test_guard_untracked_py_in_dest_names_the_file(tree, make_manifest, capsys):
    repo, dest = tree
    _write(dest, "revit_mcp/extra.py", u"x = 1\n")
    with pytest.raises(make_manifest.ManifestError) as caught:
        make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)
    assert "extra.py" in str(caught.value)
    assert make_manifest.main(["--repo", repo, "--dest", dest]) == 1
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err and "extra.py" in captured.err
    assert not os.path.exists(os.path.join(dest, "_manifest.json"))


@needs_git
def test_guard_tracked_file_missing_from_dest_names_the_file(tree, make_manifest, capsys):
    repo, dest = tree
    os.remove(os.path.join(dest, "revit_mcp", "beta.py"))
    with pytest.raises(make_manifest.ManifestError) as caught:
        make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)
    assert "revit_mcp/beta.py" in str(caught.value)
    assert make_manifest.main(["--repo", repo, "--dest", dest]) == 1
    assert "ERROR:" in capsys.readouterr().err


@needs_git
def test_guard_dest_equal_to_the_repo_is_refused_and_writes_nothing(tree, make_manifest, capsys):
    repo, _ = tree
    before = sorted(os.listdir(repo))
    assert make_manifest.main(["--repo", repo, "--dest", repo]) == 1
    assert "INTG-08" in capsys.readouterr().err
    assert sorted(os.listdir(repo)) == before
    assert not os.path.exists(os.path.join(repo, "_manifest.json"))


@needs_git
def test_guard_dest_inside_the_repo_is_refused_and_writes_nothing(tree, make_manifest, capsys):
    repo, _ = tree
    inside = os.path.join(repo, "published")
    os.makedirs(inside)
    for relpath, text in FILES.items():
        _write(inside, relpath, text)
    assert make_manifest.main(["--repo", repo, "--dest", inside]) == 1
    assert "INTG-08" in capsys.readouterr().err
    assert not os.path.exists(os.path.join(inside, "_manifest.json"))
    assert not os.path.exists(os.path.join(repo, "_manifest.json"))


def test_guard_the_real_repository_is_refused_as_a_destination(make_manifest, capsys):
    assert make_manifest.main(["--dest", REPO_ROOT]) == 1
    assert "INTG-08" in capsys.readouterr().err
    assert not os.path.exists(os.path.join(REPO_ROOT, "_manifest.json"))


@needs_git
def test_guard_git_missing_raises_manifest_error(tree, make_manifest):
    repo, dest = tree

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    with pytest.raises(make_manifest.ManifestError):
        make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW, run=no_git)
    with pytest.raises(make_manifest.ManifestError):
        make_manifest.current_commit(repo, run=no_git)


@needs_git
def test_guard_git_failure_raises_manifest_error(tree, make_manifest):
    repo, dest = tree

    def failing(*args, **kwargs):
        return types.SimpleNamespace(returncode=128, stdout=b"", stderr=b"fatal")

    with pytest.raises(make_manifest.ManifestError):
        make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW, run=failing)
    with pytest.raises(make_manifest.ManifestError):
        make_manifest.current_commit(repo, run=failing)


@needs_git
def test_guard_a_directory_that_is_not_a_checkout_exits_one(tmp_path, make_manifest,
                                                            monkeypatch, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    dest = tmp_path / "dest"
    dest.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert make_manifest.main(["--repo", str(plain), "--dest", str(dest)]) == 1
    assert "ERROR:" in capsys.readouterr().err
    assert not (dest / "_manifest.json").exists()


@needs_git
def test_guard_an_empty_listing_is_an_error(tmp_path, make_manifest):
    repo = str(tmp_path / "repo")
    _init_repo(repo, {"other.txt": u"nothing published\n"})
    dest = str(tmp_path / "dest")
    os.makedirs(dest)
    with pytest.raises(make_manifest.ManifestError):
        make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)


# ------------------------------------------------------------- atomic write


def _sample_manifest(make_manifest):
    return {"schema": 1, "generated_at": "2026-10-23T12:00:00Z", "commit": COMMIT,
            "files": {"startup.py": "a" * 64}}


def test_atomic_failed_replace_leaves_no_manifest_and_no_tmp(tmp_path, make_manifest,
                                                             monkeypatch):
    dest = str(tmp_path / "dest")
    os.makedirs(dest)

    def boom(*args, **kwargs):
        raise OSError("share went away")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        make_manifest.write_manifest(dest, _sample_manifest(make_manifest))
    assert os.listdir(dest) == []


def test_atomic_failed_replace_keeps_the_previous_manifest_bytes(tmp_path, make_manifest,
                                                                monkeypatch):
    dest = str(tmp_path / "dest")
    os.makedirs(dest)
    path = _write(dest, "_manifest.json", u'{"previous": true}\n')
    with open(path, "rb") as handle:
        before = handle.read()

    def boom(*args, **kwargs):
        raise OSError("share went away")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        make_manifest.write_manifest(dest, _sample_manifest(make_manifest))
    with open(path, "rb") as handle:
        assert handle.read() == before
    assert sorted(os.listdir(dest)) == ["_manifest.json"]


def test_atomic_unserializable_manifest_leaves_nothing_behind(tmp_path, make_manifest):
    dest = str(tmp_path / "dest")
    os.makedirs(dest)
    bad = _sample_manifest(make_manifest)
    bad["files"]["x.py"] = object()
    with pytest.raises(TypeError):
        make_manifest.write_manifest(dest, bad)
    assert os.listdir(dest) == []


def test_atomic_truncated_manifest_is_unverifiable_never_mismatch(tmp_path, make_manifest):
    dest = str(tmp_path / "dest")
    os.makedirs(dest)
    for relpath, text in FILES.items():
        _write(dest, relpath, text)
    contents = dict((k, v.encode("utf-8")) for k, v in FILES.items()
                    if k.endswith((".py", ".json")))
    manifest = {"schema": 1, "generated_at": "2026-10-23T12:00:00Z", "commit": COMMIT,
                "files": dict((k, integrity.hash_normalized(v)) for k, v in contents.items())}
    path = make_manifest.write_manifest(dest, manifest)
    with open(path, "rb") as handle:
        whole = handle.read()
    assert integrity.check_integrity(dest)["state"] == trust.INTEGRITY_MATCH
    with open(path, "wb") as handle:
        handle.write(whole[:len(whole) // 2])
    result = integrity.check_integrity(dest)
    assert (result["state"], result["reason"]) == (
        trust.INTEGRITY_UNVERIFIABLE, trust.REASON_MANIFEST_UNREADABLE)


# ------------------------------------------------------------- determinism


@needs_git
def test_determinism_equal_dicts_and_exact_bytes(tree, make_manifest):
    repo, dest = tree
    first = make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)
    second = make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)
    assert first == second
    path = make_manifest.write_manifest(dest, first)
    with open(path, "rb") as handle:
        data = handle.read()
    assert data == (json.dumps(first, sort_keys=True, indent=2) + "\n").encode("ascii")
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    assert b"\r" not in data
    assert sorted(os.listdir(dest)).count("_manifest.json.tmp") == 0


@needs_git
def test_determinism_non_ascii_content_is_written_as_ascii(tree, make_manifest):
    repo, dest = tree
    manifest = make_manifest.build_manifest(repo, dest, commit=COMMIT, now=NOW)
    manifest["files"][u"revit_mcp/м.py"] = "b" * 64
    path = make_manifest.write_manifest(dest, manifest)
    with open(path, "rb") as handle:
        data = handle.read()
    data.decode("ascii")
    assert b"\\u043c" in data


@needs_git
def test_main_writes_a_manifest_the_reader_accepts(tree, make_manifest, capsys):
    repo, dest = tree
    assert make_manifest.main(["--repo", repo, "--dest", dest]) == 0
    assert capsys.readouterr().out.startswith("MANIFEST written:")
    assert integrity.check_integrity(dest)["state"] == trust.INTEGRITY_MATCH
    assert not os.path.exists(os.path.join(repo, "_manifest.json"))


# ------------------------------------------------------------- grammar


def test_grammar_python_38_and_no_annotations():
    with open(GENERATOR, "rb") as handle:
        source = handle.read().decode("utf-8")
    tree = ast.parse(source, feature_version=(3, 8))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.AnnAssign)]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.returns is None, node.name
            args = node.args
            every = args.posonlyargs + args.args + args.kwonlyargs
            every += [a for a in (args.vararg, args.kwarg) if a is not None]
            assert all(a.annotation is None for a in every), node.name


def test_grammar_the_generator_never_walks_the_filesystem():
    with open(GENERATOR, "rb") as handle:
        tree = ast.parse(handle.read())
    banned = {"walk", "scandir", "glob", "iglob", "rglob"}
    called = [n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in banned]
    assert called == []
    assert "glob" not in [a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                          for a in n.names]
