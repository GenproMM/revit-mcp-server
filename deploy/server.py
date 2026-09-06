# -*- coding: utf-8 -*-
r"""Entry point Hermes launches. Ships as <install root>\app\server.py.

pyRevit's bundled CPython is the *embeddable* distribution: its stdlib lives in
python312.zip and a `python312._pth` file sits next to python.exe. That file
disables `site` and makes the interpreter **ignore PYTHONPATH entirely**, so
neither site-packages nor an environment variable can bring our dependencies
into scope. What it does not do is freeze sys.path at runtime -- hence this
launcher, which injects the paths itself and then hands over to main.py.

Doing it here rather than by editing pyRevit's `._pth` matters: that file is
shared with pyRevit's own in-Revit CPython engine and is overwritten whenever
pyRevit updates.

Nothing here may print to stdout -- that is the MCP protocol stream.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(HERE, "libs"))
sys.path.insert(0, HERE)

try:
    import runpy
    runpy.run_path(os.path.join(HERE, "main.py"), run_name="__main__")
except ImportError as exc:
    # The usual cause is a pyRevit update that swapped the CPython engine:
    # the wheels under libs\ are ABI-pinned to one CPython minor version.
    sys.stderr.write(
        "RevitMCP: cannot start -- {}\n"
        "Dependencies in {} were built for a different CPython than the one\n"
        "running this ({}). Re-run install.cmd from the share to rebuild.\n".format(
            exc, os.path.join(HERE, "libs"), ".".join(map(str, sys.version_info[:2]))
        )
    )
    raise
