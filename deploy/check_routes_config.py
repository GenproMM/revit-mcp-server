# -*- coding: utf-8 -*-
"""Read shared pyRevit Routes settings; never change another extension's host."""

import configparser
import os
import sys
from pathlib import Path


def check_config(path):
    config = configparser.ConfigParser(interpolation=None)
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            config.read_file(stream)
        enabled = config.get("routes", "enabled").strip().strip('"\'').lower()
        host = config.get("routes", "host").strip().strip('"\'')
        port = config.get("routes", "port").strip().strip('"\'')
    except (OSError, UnicodeError, configparser.Error) as exc:
        return False, "Cannot confirm shared Routes settings: {}".format(exc)
    if enabled != "true" or host != "127.0.0.1":
        return False, "Routes must already be enabled on 127.0.0.1; ask the pyRevit owner."
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        return False, "Shared Routes port is invalid; ask the pyRevit owner."
    return True, "Shared Routes unchanged: 127.0.0.1:{}. Set REVIT_PORT={} in OUR MCP entry.".format(port, port)


def main():
    path = Path(os.environ["APPDATA"]) / "pyRevit" / "pyRevit_config.ini"
    ok, message = check_config(path)
    print(message)
    if not ok:
        print("No Routes settings were changed. Agree changes with owners of other extensions first.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
