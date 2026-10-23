# -*- coding: utf-8 -*-
"""Create the developer shared secret in revit_mcp/_bridge_secret, once.

    uv run python scripts/dev_secret.py

On a developer machine the pyRevit extension is a junction to this repository,
so this creates the one revit_mcp/_bridge_secret that both halves read:
bridge.py looks beside itself first, then in revit_mcp/. The file is never
overwritten and its value is never printed. It is git-ignored.

Run the server from the repository with `uv run main.py` rather than from an
installed payload, or the two halves read different secrets.

Deleting the file and running this script again rotates the developer secret
(restart Revit afterwards so the extension reads the new one).

Python 3.8 grammar, standard library only.
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "deploy"))

import secret_tool  # noqa: E402  (this repository's deploy/secret_tool.py)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create revit_mcp/_bridge_secret once (never overwrites, never prints it)."
    )
    parser.add_argument(
        "--repo",
        default=os.path.dirname(_HERE),
        help="repository root (default: the parent of this script's directory)",
    )
    args = parser.parse_args(argv)
    path = os.path.join(args.repo, "revit_mcp", "_bridge_secret")
    try:
        if secret_tool.ensure_secret(path):
            print("created {}".format(path))
        else:
            print("exists, left unchanged {}".format(path))
    except (secret_tool.SecretToolError, OSError) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
