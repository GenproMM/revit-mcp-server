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
sys.path.insert(0, os.path.join(HERE, "libs"))
sys.path.insert(0, HERE)

import mcp.server.fastmcp  # noqa: F401,E402
import httpx  # noqa: F401,E402
import anyio  # noqa: F401,E402
import tools  # noqa: F401,E402

print("warm ok")
