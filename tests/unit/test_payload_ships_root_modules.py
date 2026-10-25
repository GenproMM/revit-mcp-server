# -*- coding: utf-8 -*-
"""Every repo-root module reachable from main.py must be copied into the payload.

deploy/build-payload.cmd stages main.py and its siblings into the app
directory by explicit ``copy`` lines. A module added next to main.py but not to
that list passes every unit test and then fails on a workstation with a
ModuleNotFoundError, which deploy/server.py misreports as a CPython-version
mismatch. This test closes that gap (D-20). The walk is transitive
(main -> bridge -> audit): a root module imported only by bridge.py is as
needed on a workstation as one main.py imports itself.

Needs no Revit.
"""
import ast
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN = os.path.join(REPO, "main.py")
BUILD = os.path.join(REPO, "deploy", "build-payload.cmd")

_COPY = re.compile(r'^\s*copy\s+/y\s+"%REPO%\\([A-Za-z0-9_]+)\.py"', re.IGNORECASE)


def _root_imports_of(path):
    """Top-level names of the repo-root modules one file imports (absolute imports only)."""
    with open(path, encoding="utf-8") as handle:
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


def _root_modules_reached_from_main():
    """Repo-root modules main.py imports, and those they import in turn (each file read once)."""
    reached = set()
    pending = [MAIN]
    while pending:
        for name in _root_imports_of(pending.pop()):
            if name not in reached:
                reached.add(name)
                pending.append(os.path.join(REPO, name + ".py"))
    return reached


def _copied_from_repo_root():
    with open(BUILD, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    return set(m.group(1) for m in map(_COPY.match, lines) if m)


def test_payload_copies_every_root_module_reachable_from_main():
    root_modules = _root_modules_reached_from_main()
    copied = _copied_from_repo_root()

    # Guard against passing vacuously: main.py really does import bridge, and
    # bridge.py really does import audit (the transitive step this test exists for).
    assert "bridge" in root_modules, root_modules
    assert "audit" in root_modules, root_modules
    # Phase 7: the authorization modules bridge.py imports eagerly (D-01, D-16).
    assert {"policy", "approval", "permit"} <= root_modules, root_modules
    assert "main" in copied, copied
    missing = sorted(root_modules - copied)
    assert not missing, (
        "main.py reaches repo-root modules the payload does not copy: {} -- add "
        'a copy /y "%REPO%\\<name>.py" line to deploy/build-payload.cmd'.format(missing)
    )


_POLICY_COPY = re.compile(r'^\s*copy\s+/y\s+"%REPO%\\policy\.base\.toml"\s+"%BUILD%\\app\\"', re.IGNORECASE)


def test_payload_copies_the_base_policy_file():
    """The base policy is data the payload reads beside policy.py; the .py-only walk above cannot see it."""
    with open(BUILD, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    matches = [line for line in lines if _POLICY_COPY.match(line)]
    assert len(matches) == 1, matches
    assert os.path.isfile(os.path.join(REPO, "policy.base.toml"))
