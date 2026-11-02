# -*- coding: utf-8 -*-
"""
Product version and runtime facts for the /status/ route.

PRODUCT_VERSION is the RevitMCP release both halves report; tools/status_tools.py
holds the same value for the MCP server and pyproject.toml holds it for the build.
tests/unit/test_runtime_info.py keeps the three equal.

The build facts come from the extension's own _manifest.json (commit and
generated_at), read once and cached: /status/ is called often and the extension
usually lives on a UNC share. A developer junction has no manifest, so its build
is None.

Imports nothing from pyRevit, clr or the Revit API: status.py gathers those facts
and hands them in, so everything here is unit tested under CPython. It registers
no routes, so startup.py's discovery reports it as a helper.

Dialect: the intersection of IronPython 2.7 and 3.4. It must also run on
IronPython 2.7, because that engine is exactly what runtime_alerts reports.
"""

import os
import sys

from .integrity import read_manifest

PRODUCT_VERSION = "2.0.0"

# The engine the extension is built and tested for (CLAUDE.md two-runtime rule).
SUPPORTED_PYTHON_MAJOR = 3

# root -> build dict; filled on first use, never invalidated (a new build needs a
# full Revit restart anyway, like the integrity check).
_BUILD_CACHE = {}


def python_info():
    """{"implementation", "version"} of the interpreter running this code; never raises."""
    try:
        implementation = getattr(getattr(sys, "implementation", None), "name", None)
        if not implementation:
            # IronPython 2.7 has no sys.implementation.
            implementation = "ironpython" if sys.platform == "cli" else "unknown"
        info = sys.version_info
        version = "{}.{}.{}".format(info[0], info[1], info[2])
        return {"implementation": str(implementation), "version": version, "major": int(info[0])}
    except Exception:
        return {"implementation": "unknown", "version": None, "major": None}


def extension_build(root):
    """{"path", "commit", "built_at"} for the extension at ``root``; never raises.

    commit and built_at are None when the manifest is absent or unreadable.
    """
    cached = _BUILD_CACHE.get(root)
    if cached is not None:
        return dict(cached)
    build = {"path": root, "commit": None, "built_at": None}
    try:
        manifest, _reason = read_manifest(root)
        if isinstance(manifest, dict):
            commit = manifest.get("commit")
            built_at = manifest.get("generated_at")
            build["commit"] = str(commit) if commit else None
            build["built_at"] = str(built_at) if built_at else None
    except Exception:
        pass
    _BUILD_CACHE[root] = build
    return dict(build)


def runtime_block(root, pyrevit=None, revit=None):
    """The "runtime" part of the /status/ reply; never raises.

    ``pyrevit`` and ``revit`` are the dicts status.py read from pyRevit and the
    Revit application (any value may be None); they are copied, not trusted.
    """
    block = {
        "product_version": PRODUCT_VERSION,
        "extension": extension_build(root),
        "python": python_info(),
        "pyrevit": dict(pyrevit) if isinstance(pyrevit, dict) else {},
        "revit": dict(revit) if isinstance(revit, dict) else {},
    }
    return block


def runtime_alerts(block):
    """Plain sentences about what is wrong in a runtime block; [] when nothing is."""
    alerts = []
    try:
        python = block.get("python") if isinstance(block, dict) else None
        major = python.get("major") if isinstance(python, dict) else None
        if major is not None and major != SUPPORTED_PYTHON_MAJOR:
            alerts.append(
                "pyRevit runs this extension on Python {} ({}); RevitMCP needs IronPython 3 "
                "(engine IPY342). Under this engine the shared secret is not read and every "
                "mutation is refused. Close Revit, run `pyrevit attach master 342 --attached` "
                "and start Revit again.".format(python.get("version"), python.get("implementation"))
            )
    except Exception:
        return []
    return alerts


def extension_root(module_file):
    """The extension directory for a module file inside revit_mcp/; never raises."""
    try:
        return os.path.dirname(os.path.dirname(os.path.abspath(module_file)))
    except Exception:
        return None
