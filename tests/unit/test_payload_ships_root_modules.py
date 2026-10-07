# -*- coding: utf-8 -*-
"""Every repo-root module main.py imports must be copied into the payload.

deploy/build-payload.cmd stages main.py and its siblings into the app
directory by explicit ``copy`` lines. A module added next to main.py but not to
that list passes every unit test and then fails on a workstation with a
ModuleNotFoundError, which deploy/server.py misreports as a CPython-version
mismatch. This test closes that gap (D-20).

Needs no Revit.
"""
import ast
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN = os.path.join(REPO, "main.py")
BUILD = os.path.join(REPO, "deploy", "build-payload.cmd")

_COPY = re.compile(r'^\s*copy\s+/y\s+"%REPO%\\([A-Za-z0-9_]+)\.py"', re.IGNORECASE)


def _root_modules_main_imports():
    with open(MAIN, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            tops = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            tops = [node.module.split(".")[0]]
        else:
            continue
        for top in tops:
            if os.path.isfile(os.path.join(REPO, top + ".py")):
                names.add(top)
    return names


def _copied_from_repo_root():
    with open(BUILD, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    return set(m.group(1) for m in map(_COPY.match, lines) if m)


def test_payload_copies_every_root_module_main_imports():
    root_modules = _root_modules_main_imports()
    copied = _copied_from_repo_root()

    # Guard against passing vacuously: main.py really does import bridge.
    assert "bridge" in root_modules, root_modules
    assert "main" in copied, copied
    missing = sorted(root_modules - copied)
    assert not missing, (
        "main.py imports repo-root modules the payload does not copy: {} -- add "
        'a copy /y "%REPO%\\<name>.py" line to deploy/build-payload.cmd'.format(missing)
    )
