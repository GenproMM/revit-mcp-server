# -*- coding: utf-8 -*-
"""Hardening of revit_mcp/integrity.py: it never writes, it never calls an
unreachable reference "tampered", and it stays quiet on the developer's junction.

Needs no Revit. Every tree is built under pytest's tmp_path; the real-repository
tests only read. The write guards are installed only around the check itself, so
the fixtures that build a tree are free to write.
"""

import ast
import builtins
import contextlib
import errno
import os
import shutil

import pytest

from revit_mcp import integrity, trust

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FILES = {
    "startup.py": u"# -*- coding: utf-8 -*-\nSTARTUP = 1\n",
    "extension.json": u'{"name": "genpro_revit_mcp"}\n',
    "revit_mcp/__init__.py": u"# -*- coding: utf-8 -*-\n",
    "revit_mcp/alpha.py": u"# -*- coding: utf-8 -*-\nNAME = u'Стена'\n",
    "revit_mcp/beta.py": u"# -*- coding: utf-8 -*-\nBETA = 2\n",
}

_REAL_OPEN = builtins.open


def _write(root, relpath, data):
    path = os.path.join(root, *relpath.split("/"))
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    if not isinstance(data, bytes):
        data = data.encode("utf-8")
    with _REAL_OPEN(path, "wb") as handle:
        handle.write(data)
    return path


def _manifest_for(contents):
    """The manifest text for {relpath: bytes}, hashed with the verifier's own function."""
    import json
    files = dict((k, integrity.hash_normalized(v)) for k, v in contents.items())
    return json.dumps({"schema": 1, "generated_at": "2026-10-23T00:00:00Z",
                       "commit": "0" * 40, "files": files}, sort_keys=True, indent=2) + "\n"


def _build_tree(root, files=FILES, manifest=True):
    os.makedirs(root)
    contents = {}
    for relpath, text in files.items():
        _write(root, relpath, text)
        contents[relpath] = text.encode("utf-8") if not isinstance(text, bytes) else text
    if manifest:
        _write(root, "_manifest.json", _manifest_for(contents))
    return contents


def _snapshot(root):
    """{relpath: (bytes, mtime_ns)} for every file and {relpath/: None} for every directory."""
    seen = {}
    for folder, dirs, names in os.walk(root):
        for name in dirs:
            seen[os.path.relpath(os.path.join(folder, name), root) + "/"] = None
        for name in names:
            path = os.path.join(folder, name)
            with _REAL_OPEN(path, "rb") as handle:
                seen[os.path.relpath(path, root)] = (handle.read(), os.stat(path).st_mtime_ns)
    return seen


def _forbidden(name):
    def refuse(*args, **kwargs):
        raise AssertionError("integrity check called {}".format(name))
    return refuse


@contextlib.contextmanager
def _guards(monkeypatch, fail=None, record=None):
    """Write guards plus an optional failing open().

    fail maps a path suffix to the exception that open() raises for any path ending
    in it. record, a list, receives every path open() is asked for.
    """
    def guarded_open(path, mode="r", *args, **kwargs):
        text = str(mode)
        if any(flag in text for flag in "wax+"):
            raise AssertionError("integrity check opened {!r} in mode {!r}".format(path, text))
        if record is not None:
            record.append(os.fspath(path))
        if fail:
            normalized = os.fspath(path).replace("\\", "/")
            for suffix, error in fail.items():
                if normalized.endswith(suffix):
                    raise error
        return _REAL_OPEN(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    for name in ("remove", "unlink", "rename", "replace", "mkdir", "makedirs",
                 "rmdir", "utime", "chmod"):
        monkeypatch.setattr(os, name, _forbidden("os." + name))
    for name in ("copy", "copy2", "copyfile", "move", "rmtree"):
        monkeypatch.setattr(shutil, name, _forbidden("shutil." + name))
    try:
        yield
    finally:
        monkeypatch.undo()


def _check(root, monkeypatch, **options):
    with _guards(monkeypatch, **options):
        return integrity.check_integrity(root)


def _windows_style_error():
    """An OSError with no errno, as a dropped network share produces on Windows."""
    error = OSError(None, "network path not found")
    try:
        error.winerror = 53
    except (AttributeError, TypeError):
        pass
    assert error.errno is None
    return error


UNREACHABLE = [
    ("eacces", lambda: OSError(errno.EACCES, "denied")),
    ("eio", lambda: OSError(errno.EIO, "i/o error")),
    ("einval", lambda: OSError(errno.EINVAL, "invalid")),
    ("permission", lambda: PermissionError("no access")),
    ("network", _windows_style_error),
]


# ---------------------------------------------------------------- never writes


def _tamper(root):
    with _REAL_OPEN(os.path.join(root, "revit_mcp", "alpha.py"), "ab") as handle:
        handle.write(b"EVIL = 1\n")


def _drop_manifest(root):
    os.remove(os.path.join(root, "_manifest.json"))


def _break_manifest(root):
    _write(root, "_manifest.json", b'{"schema": 1, "files": {')


TREE_CLASSES = {
    "matching": (lambda root: None, {}, trust.INTEGRITY_MATCH),
    "tampered": (_tamper, {}, trust.INTEGRITY_MISMATCH),
    "manifest_missing": (_drop_manifest, {}, trust.INTEGRITY_UNVERIFIABLE),
    "manifest_invalid_json": (_break_manifest, {}, trust.INTEGRITY_UNVERIFIABLE),
    "listed_file_unreadable": (lambda root: None,
                               {"revit_mcp/beta.py": PermissionError("locked")},
                               trust.INTEGRITY_UNVERIFIABLE),
}


@pytest.mark.parametrize("kind", sorted(TREE_CLASSES))
def test_never_writes_leaves_the_tree_untouched(tmp_path, monkeypatch, kind):
    prepare, fail, expected_state = TREE_CLASSES[kind]
    root = str(tmp_path / "tree")
    _build_tree(root)
    prepare(root)
    before = _snapshot(root)
    result = _check(root, monkeypatch, fail=fail)
    assert result["state"] == expected_state
    assert _snapshot(root) == before


def test_never_writes_guards_really_refuse_a_write(tmp_path, monkeypatch):
    """The guard itself works: a write attempt inside it fails loudly."""
    root = str(tmp_path / "tree")
    _build_tree(root)
    with _guards(monkeypatch):
        with pytest.raises(AssertionError):
            open(os.path.join(root, "x.txt"), "w")
        with pytest.raises(AssertionError):
            open(os.path.join(root, "x.txt"), "r+b")
        with pytest.raises(AssertionError):
            os.remove(os.path.join(root, "startup.py"))
        with pytest.raises(AssertionError):
            shutil.rmtree(root)
    assert os.path.exists(os.path.join(root, "startup.py"))


def _read_ast(name):
    path = os.path.join(REPO_ROOT, "revit_mcp", name)
    with _REAL_OPEN(path, "rb") as handle:
        return ast.parse(handle.read(), filename=path)


_BANNED_CALLS = {"write", "writelines", "remove", "unlink", "rename", "replace",
                 "mkdir", "makedirs", "rmdir", "utime", "chmod"}
# bytes.replace / str.replace is a pure function; only os.replace touches the disk.
_PURE_WHEN_NOT_ON_MODULE = {"replace", "rename"}
_MODULES = {"os", "shutil", "pathlib"}


def _violations(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += ["import " + a.name for a in node.names if a.name.split(".")[0] == "shutil"]
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "shutil":
                found.append("from shutil import")
            if (node.module or "") == "os":
                found += ["from os import " + a.name for a in node.names
                          if a.name in _BANNED_CALLS]
        if isinstance(node, ast.Name) and node.id == "shutil":
            found.append("name shutil")
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            mode = None
            if len(node.args) > 1:
                mode = node.args[1]
            for keyword in node.keywords:
                if keyword.arg == "mode":
                    mode = keyword.value
            if not (isinstance(mode, ast.Constant) and mode.value == "rb"):
                found.append("open() with a mode other than 'rb' at line {}".format(node.lineno))
        if isinstance(func, ast.Attribute) and func.attr in _BANNED_CALLS:
            receiver = func.value
            on_module = isinstance(receiver, ast.Name) and receiver.id in _MODULES
            if func.attr in _PURE_WHEN_NOT_ON_MODULE and not on_module:
                continue
            found.append("call {} at line {}".format(func.attr, node.lineno))
        if isinstance(func, ast.Name) and func.id in _BANNED_CALLS:
            found.append("call {} at line {}".format(func.id, node.lineno))
    return found


@pytest.mark.parametrize("name", ["trust.py", "integrity.py"])
def test_never_writes_ast_scan_finds_no_write_call(name):
    assert _violations(_read_ast(name)) == []


def test_never_writes_ast_scan_detects_a_planted_violation():
    """The scan is not vacuous: each banned shape is reported."""
    samples = [
        "open(p, 'w')",
        "open(p)",
        "open(p, mode='ab')",
        "handle.write(b'x')",
        "os.remove(p)",
        "os.replace(a, b)",
        "import shutil",
        "from os import unlink",
        "os.chmod(p, 0)",
    ]
    for source in samples:
        assert _violations(ast.parse(source)), source
    assert _violations(ast.parse("open(p, 'rb')\ndata.replace(b'a', b'b')")) == []


def test_never_writes_open_modes_are_literal_rb():
    """Every open() in the two modules is rb, and there is at least one of each."""
    for name in ("trust.py", "integrity.py"):
        opens = [n for n in ast.walk(_read_ast(name))
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "open"]
        assert opens, name
        assert all(n.args[1].value == "rb" for n in opens), name


# ---------------------------------------------------------------- unreachable


@pytest.mark.parametrize("label,make", UNREACHABLE, ids=[u[0] for u in UNREACHABLE])
def test_unreachable_manifest_is_unverifiable_read_error(tmp_path, monkeypatch, label, make):
    root = str(tmp_path / "tree")
    _build_tree(root)
    result = _check(root, monkeypatch, fail={"/_manifest.json": make()})
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_READ_ERROR
    assert result["modified"] == [] and result["missing"] == [] and result["unexpected"] == []


@pytest.mark.parametrize("label,make", UNREACHABLE, ids=[u[0] for u in UNREACHABLE])
def test_unreachable_listed_file_is_unverifiable_read_error(tmp_path, monkeypatch, label, make):
    root = str(tmp_path / "tree")
    _build_tree(root)
    _tamper(root)  # a real difference elsewhere must not turn unreachable into mismatch
    result = _check(root, monkeypatch, fail={"/revit_mcp/beta.py": make()})
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_READ_ERROR


def test_unreachable_enoent_on_a_listed_file_is_missing(tmp_path, monkeypatch):
    root = str(tmp_path / "tree")
    _build_tree(root)
    result = _check(root, monkeypatch,
                    fail={"/revit_mcp/beta.py": OSError(errno.ENOENT, "gone")})
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert result["missing"] == ["revit_mcp/beta.py"]
    assert result["modified"] == [] and result["unexpected"] == []


def test_unreachable_enoent_on_the_manifest_is_manifest_missing(tmp_path, monkeypatch):
    root = str(tmp_path / "tree")
    _build_tree(root)
    result = _check(root, monkeypatch, fail={"/_manifest.json": OSError(errno.ENOENT, "gone")})
    assert (result["state"], result["reason"]) == (
        trust.INTEGRITY_UNVERIFIABLE, trust.REASON_MANIFEST_MISSING)


@pytest.mark.parametrize("label,make", UNREACHABLE, ids=[u[0] for u in UNREACHABLE])
def test_unreachable_listdir_failure_is_unverifiable_read_error(tmp_path, monkeypatch, label, make):
    root = str(tmp_path / "tree")
    _build_tree(root)
    real_listdir = os.listdir

    def failing_listdir(path="."):
        if os.fspath(path).replace("\\", "/").endswith("/revit_mcp"):
            raise make()
        return real_listdir(path)

    with _guards(monkeypatch):
        monkeypatch.setattr(os, "listdir", failing_listdir)
        result = integrity.check_integrity(root)
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_READ_ERROR


def test_unreachable_absent_scope_directory_lists_its_files_as_missing(tmp_path, monkeypatch):
    root = str(tmp_path / "tree")
    _build_tree(root)
    shutil.rmtree(os.path.join(root, "revit_mcp"))
    result = _check(root, monkeypatch)
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert result["missing"] == ["revit_mcp/__init__.py", "revit_mcp/alpha.py",
                                 "revit_mcp/beta.py"]


def test_unverifiable_for_a_missing_extension_root(tmp_path, monkeypatch):
    result = _check(str(tmp_path / "does-not-exist"), monkeypatch)
    assert (result["state"], result["reason"]) == (
        trust.INTEGRITY_UNVERIFIABLE, trust.REASON_MANIFEST_MISSING)


def test_unverifiable_when_the_check_itself_raises(tmp_path, monkeypatch):
    root = str(tmp_path / "tree")
    _build_tree(root)

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(integrity, "observe_tree", boom)
    result = integrity.check_integrity(root)
    assert (result["state"], result["reason"]) == (
        trust.INTEGRITY_UNVERIFIABLE, trust.REASON_READ_ERROR)


# ---------------------------------------------------------------- dev junction


def test_real_repo_is_never_a_mismatch():
    result = integrity.check_integrity(REPO_ROOT)
    assert result["state"] != trust.INTEGRITY_MISMATCH, result


def test_real_repo_without_a_manifest_is_manifest_missing():
    if os.path.exists(os.path.join(REPO_ROOT, integrity.MANIFEST_NAME)):
        pytest.skip("a _manifest.json exists at the repository root")
    result = integrity.check_integrity(REPO_ROOT)
    assert (result["state"], result["reason"]) == (
        trust.INTEGRITY_UNVERIFIABLE, trust.REASON_MANIFEST_MISSING)


def test_real_repo_check_leaves_no_manifest_behind():
    before = os.path.exists(os.path.join(REPO_ROOT, integrity.MANIFEST_NAME))
    integrity.check_integrity(REPO_ROOT)
    assert os.path.exists(os.path.join(REPO_ROOT, integrity.MANIFEST_NAME)) == before


def _copy_layout(tmp_path):
    """A tmp copy of startup.py, extension.json and revit_mcp/*.py from the real repo."""
    root = str(tmp_path / "copy")
    os.makedirs(os.path.join(root, "revit_mcp"))
    contents = {}
    names = ["startup.py", "extension.json"]
    scope = os.path.join(REPO_ROOT, "revit_mcp")
    names += ["revit_mcp/" + n for n in sorted(os.listdir(scope)) if n.endswith(".py")]
    for relpath in names:
        target = os.path.join(root, *relpath.split("/"))
        shutil.copyfile(os.path.join(REPO_ROOT, *relpath.split("/")), target)
        with _REAL_OPEN(target, "rb") as handle:
            contents[relpath] = handle.read()
    return root, contents


def test_dev_junction_layout_copy_with_its_own_manifest_matches(tmp_path, monkeypatch):
    root, contents = _copy_layout(tmp_path)
    _write(root, "_manifest.json", _manifest_for(contents))
    result = _check(root, monkeypatch)
    assert result["state"] == trust.INTEGRITY_MATCH, result


def test_dev_junction_layout_copy_with_a_stale_manifest_is_the_negative_control(
        tmp_path, monkeypatch):
    root, contents = _copy_layout(tmp_path)
    stale = dict((k, v + b"# stale\n") for k, v in contents.items())
    _write(root, "_manifest.json", _manifest_for(stale))
    result = _check(root, monkeypatch)
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert sorted(result["modified"]) == sorted(
        k for k in contents if k.startswith("revit_mcp/") or k in ("startup.py", "extension.json"))


def test_dev_junction_layout_copy_without_a_manifest_is_unverifiable(tmp_path, monkeypatch):
    root, _ = _copy_layout(tmp_path)
    result = _check(root, monkeypatch)
    assert (result["state"], result["reason"]) == (
        trust.INTEGRITY_UNVERIFIABLE, trust.REASON_MANIFEST_MISSING)


# ---------------------------------------------------------------- traversal


HOSTILE = ["../outside.py", "/abs.py", "C:/x.py", "revit_mcp/../../escape.py",
           "revit_mcp\\win.py"]


@pytest.mark.parametrize("key", HOSTILE)
def test_hostile_manifest_key_is_never_opened(tmp_path, monkeypatch, key):
    import json
    root = str(tmp_path / "tree")
    contents = _build_tree(root)
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"secret outside the tree\n")
    files = dict((k, integrity.hash_normalized(v)) for k, v in contents.items())
    files[key] = "0" * 64
    _write(root, "_manifest.json",
           json.dumps({"schema": 1, "commit": "0" * 40, "files": files}))
    seen = []
    result = _check(root, monkeypatch, record=seen)
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_MANIFEST_UNREADABLE
    assert seen, "the manifest itself is opened"
    inside = os.path.normcase(os.path.realpath(root))
    for path in seen:
        real = os.path.normcase(os.path.realpath(path))
        assert os.path.commonpath([inside, real]) == inside, path


def test_hostile_manifest_keys_together_are_never_opened(tmp_path, monkeypatch):
    import json
    root = str(tmp_path / "tree")
    contents = _build_tree(root)
    files = dict((k, integrity.hash_normalized(v)) for k, v in contents.items())
    for key in HOSTILE:
        files[key] = "0" * 64
    _write(root, "_manifest.json", json.dumps({"schema": 1, "files": files}))
    seen = []
    result = _check(root, monkeypatch, record=seen)
    assert result["reason"] == trust.REASON_MANIFEST_UNREADABLE
    assert all(os.path.normcase(os.path.realpath(p)).startswith(
        os.path.normcase(os.path.realpath(root))) for p in seen)


# ---------------------------------------------------------------- determinism


def test_determinism_two_runs_over_one_tree_are_equal(tmp_path, monkeypatch):
    root = str(tmp_path / "tree")
    _build_tree(root)
    _tamper(root)
    first = _check(root, monkeypatch)
    second = _check(root, monkeypatch)
    assert first == second
    assert first["state"] == trust.INTEGRITY_MISMATCH


def test_determinism_a_changed_tree_changes_the_answer(tmp_path, monkeypatch):
    """No cache: the second run sees the edit made between the two."""
    root = str(tmp_path / "tree")
    _build_tree(root)
    assert _check(root, monkeypatch)["state"] == trust.INTEGRITY_MATCH
    _tamper(root)
    assert _check(root, monkeypatch)["state"] == trust.INTEGRITY_MISMATCH


def test_determinism_integrity_has_no_global_or_nonlocal_statement():
    tree = _read_ast("integrity.py")
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Global, ast.Nonlocal))]


def test_determinism_a_concurrent_reader_cannot_change_the_tree(tmp_path, monkeypatch):
    """Two overlapping checks, one inside the other's read, leave the tree as it was."""
    root = str(tmp_path / "tree")
    _build_tree(root)
    before = _snapshot(root)
    results = []
    original = integrity._read_bytes
    state = {"nested": False}

    def reentrant(path):
        if not state["nested"]:
            state["nested"] = True
            results.append(integrity.check_integrity(root))
        return original(path)

    monkeypatch.setattr(integrity, "_read_bytes", reentrant)
    outer = _check(root, monkeypatch)
    assert outer["state"] == trust.INTEGRITY_MATCH
    assert results and results[0]["state"] == trust.INTEGRITY_MATCH
    assert _snapshot(root) == before
