# -*- coding: utf-8 -*-
r"""Pre-import the heavy dependencies so the first real launch is not cold.

Run by update.cmd against a freshly copied version, before the `current`
junction is flipped. A new version means a new path: cold file cache, no
__pycache__ for app\, and a first antivirus scan of the extension modules.
Without this the first Hermes session after every update looks hung.

Doubles as the acceptance check -- a non-zero exit stops the switch.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

def _pywin32_paths(libs):
    """mcp>=1.11 imports pywin32 on Windows; the embeddable CPython ignores pywin32.pth, so add its directories here (D-24)"""
    added = []
    for sub in ("win32", os.path.join("win32", "lib"), "pythonwin"):
        path = os.path.join(libs, sub)
        if os.path.isdir(path) and path not in sys.path:
            sys.path.append(path)
            added.append(path)
    dll_dir = os.path.join(libs, "pywin32_system32")
    if os.path.isdir(dll_dir) and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(dll_dir)
        except OSError:
            pass
    return added


sys.path.insert(0, os.path.join(HERE, "libs"))
_pywin32_paths(os.path.join(HERE, "libs"))
sys.path.insert(0, HERE)

import mcp.server.fastmcp  # noqa: F401,E402
import httpx  # noqa: F401,E402
import anyio  # noqa: F401,E402
import tools  # noqa: F401,E402

print("warm ok")
