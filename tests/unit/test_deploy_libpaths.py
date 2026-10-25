# -*- coding: utf-8 -*-
"""The pywin32 path shim in the three payload entry points (Phase 7, D-24).

Since mcp 1.11 the SDK imports pywin32 on Windows unconditionally, and pyRevit's
embeddable CPython ignores `.pth` files, so `import mcp` fails in the payload
layout with `No module named 'pywintypes'` unless the pywin32 directories are on
sys.path first. deploy/server.py, deploy/gate.py and deploy/warm.py each define
the same `_pywin32_paths(libs)` and call it right after the libs directory is put
on sys.path. The three copies must stay identical: they are the same fix, and a
drifted copy would work in one entry point and fail in another.

Needs no Revit and no pywin32: the function is extracted from the source with
`ast` and run against a fake libs tree.
"""

import ast
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENTRY_POINTS = ("server.py", "gate.py", "warm.py")
FIRST_PARTY_AND_SDK = ("mcp", "httpx", "anyio", "tools")


def _source(name):
    path = os.path.join(REPO_ROOT, "deploy", name)
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8")


def _tree(name):
    return ast.parse(_source(name))


def _function_node(name):
    matches = [
        node for node in _tree(name).body
        if isinstance(node, ast.FunctionDef) and node.name == "_pywin32_paths"
    ]
    assert len(matches) == 1, "%s must define exactly one module-level _pywin32_paths" % name
    return matches[0]


def _load_function(name):
    source = _source(name)
    node = _function_node(name)
    segment = ast.get_source_segment(source, node)
    namespace = {"os": os, "sys": sys}
    exec(compile(segment, "deploy/%s" % name, "exec"), namespace)
    return namespace["_pywin32_paths"]


def _calls_shim(node):
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "_pywin32_paths"
    )


def _is_libs_insert(node):
    """sys.path.insert(0, os.path.join(HERE, "libs"))"""
    if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
        return False
    func = node.value.func
    if not (isinstance(func, ast.Attribute) and func.attr == "insert"):
        return False
    return '"libs"' in ast.dump(node.value).replace("'", '"')


def _first_sdk_use(body):
    """Index of the first top-level statement that imports the SDK or runs main.py."""
    for index, node in enumerate(body):
        for inner in ast.walk(node):
            if isinstance(inner, ast.Import):
                roots = [alias.name.split(".")[0] for alias in inner.names]
            elif isinstance(inner, ast.ImportFrom):
                roots = [(inner.module or "").split(".")[0]]
            else:
                continue
            if any(root in FIRST_PARTY_AND_SDK or root == "runpy" for root in roots):
                return index
    return None


def _fake_libs(tmp_path, names):
    libs = tmp_path / "libs"
    libs.mkdir()
    for name in names:
        (libs / name).mkdir(parents=True)
    return str(libs)


@pytest.fixture
def sandboxed(monkeypatch):
    """A private copy of sys.path and a recorder in place of os.add_dll_directory."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    calls = []
    monkeypatch.setattr(os, "add_dll_directory", lambda path: calls.append(path), raising=False)
    return calls


def test_the_three_shims_are_identical():
    dumps = {name: ast.dump(_function_node(name)) for name in ENTRY_POINTS}
    assert len(set(dumps.values())) == 1, "the three _pywin32_paths copies drifted apart"


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_call_follows_libs_insert_and_precedes_the_first_sdk_use(name):
    body = _tree(name).body
    call_index = next(i for i, node in enumerate(body) if _calls_shim(node))
    insert_index = next(i for i, node in enumerate(body) if _is_libs_insert(node))
    assert insert_index < call_index, "%s calls the shim before libs is on sys.path" % name
    first_use = _first_sdk_use(body)
    assert first_use is not None
    assert call_index < first_use, "%s imports the SDK before the shim ran" % name


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_shim_is_called_with_the_libs_path(name):
    body = _tree(name).body
    node = next(node for node in body if _calls_shim(node))
    assert len(node.value.args) == 1
    assert '"libs"' in ast.dump(node.value.args[0]).replace("'", '"')


def test_adds_the_three_directories_in_order_and_registers_the_dll_directory(tmp_path, sandboxed):
    libs = _fake_libs(tmp_path, ["win32", os.path.join("win32", "lib"), "pythonwin", "pywin32_system32"])
    expected = [
        os.path.join(libs, "win32"),
        os.path.join(libs, "win32", "lib"),
        os.path.join(libs, "pythonwin"),
    ]
    for name in ENTRY_POINTS:
        sys.path[:] = [p for p in sys.path if p not in expected]
        del sandboxed[:]
        added = _load_function(name)(libs)
        assert added == expected
        for path in expected:
            assert sys.path.count(path) == 1
        assert sandboxed == [os.path.join(libs, "pywin32_system32")]


def test_second_call_adds_nothing_new(tmp_path, sandboxed):
    libs = _fake_libs(tmp_path, ["win32", os.path.join("win32", "lib"), "pythonwin"])
    function = _load_function("gate.py")
    assert len(function(libs)) == 3
    before = list(sys.path)
    assert function(libs) == []
    assert sys.path == before


def test_empty_libs_adds_nothing(tmp_path, sandboxed):
    libs = _fake_libs(tmp_path, [])
    before = list(sys.path)
    for name in ENTRY_POINTS:
        assert _load_function(name)(libs) == []
    assert sys.path == before
    assert sandboxed == []


def test_only_existing_directories_are_added(tmp_path, sandboxed):
    libs = _fake_libs(tmp_path, ["pythonwin"])
    assert _load_function("warm.py")(libs) == [os.path.join(libs, "pythonwin")]
    assert sandboxed == []


def test_dll_directory_failure_is_swallowed(tmp_path, monkeypatch, sandboxed):
    libs = _fake_libs(tmp_path, ["pywin32_system32"])

    def refuse(path):
        raise OSError("refused")

    monkeypatch.setattr(os, "add_dll_directory", refuse, raising=False)
    assert _load_function("server.py")(libs) == []


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_shim_writes_nothing_to_stdout(name, tmp_path, sandboxed, capsys):
    libs = _fake_libs(tmp_path, ["win32", "pythonwin", "pywin32_system32"])
    _load_function(name)(libs)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
