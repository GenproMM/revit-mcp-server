# -*- coding: utf-8 -*-
r"""Unregister a retired pyRevit extension search path.

Usage:  forget_retired_path.py <pyrevit.exe> <ascii marker>

Why this is a script and not two lines of batch
-----------------------------------------------
The retired path is

    \\srv-dfs\BIM\01_Ресурсы плагинов\827_RevitMCP\ext

and both halves of the obvious batch solution break on it:

* Spelling it out in install.cmd does not work. cmd parses a .cmd file in the
  console codepage -- 866 on a Russian Windows, and a double-click from the
  share always gives us that -- so a UTF-8 literal arrives mangled and the
  forget silently misses.
* Reading it back and piping it through a `for /f` variable does not work
  either, for the same reason at the other end: the bytes are correct in the
  config, and cmd corrupts them on the way into %%p.

So the string never leaves Python. It is read from pyRevit's own config, where
it is already correctly encoded, matched on its ASCII segment, and handed to
pyrevit.exe as an argv element.

Reading pyRevit_config.ini is safe; only writing it by hand is forbidden, and
the removal itself still goes through the CLI. `pyrevit extensions paths` with
no argument prints usage rather than the list, which is why the config is the
source here.

Exit code is always 0: a machine that never had the retired path is the normal
case, and a failure to tidy an old setting must not fail an install.
"""

import json
import os
import subprocess
import sys

try:
    import configparser
except ImportError:  # pragma: no cover - Python 2 safety net
    import ConfigParser as configparser


def retired_paths(config_path, marker):
    """Every registered search path whose text contains marker."""
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except Exception as exc:
        sys.stderr.write("could not read {}: {}\n".format(config_path, exc))
        return []

    try:
        raw = parser.get("core", "userextensions")
    except Exception:
        return []

    try:
        paths = json.loads(raw)
    except ValueError as exc:
        sys.stderr.write("userextensions is not valid JSON: {}\n".format(exc))
        return []

    if not isinstance(paths, list):
        return []
    return [p for p in paths if isinstance(p, str) and marker in p]


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(__doc__)
        return 0

    pyrevit, marker = argv[1], argv[2]
    config_path = os.path.join(
        os.environ.get("APPDATA", ""), "pyRevit", "pyRevit_config.ini"
    )
    if not os.path.isfile(config_path):
        return 0

    for path in retired_paths(config_path, marker):
        # Printed with a replacement policy: the console codepage cannot
        # represent this path, and a UnicodeEncodeError here would abort an
        # install over a progress message.
        try:
            print("       unregistering retired path: {}".format(path))
        except UnicodeEncodeError:
            print("       unregistering retired path (name not printable here)")
        try:
            subprocess.call(
                [pyrevit, "extensions", "paths", "forget", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            sys.stderr.write("forget failed: {}\n".format(exc))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
