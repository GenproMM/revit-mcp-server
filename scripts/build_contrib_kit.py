# -*- coding: utf-8 -*-
"""Build the contributor kit for distribution.

    uv run python scripts/build_contrib_kit.py [--out <dir>]

Contributors have no access to this repository, so they get a zip. The kit is
assembled here rather than kept as a ready-made archive for one reason:
scripts/conventions.py is copied in at build time, so the checks a contributor
runs are byte-identical to the checks intake runs. A stale copy would tell a
contributor their package is fine when it is not, which is worse than having no
checker at all.

Rebuild and redistribute whenever scripts/conventions.py changes.
"""

import argparse
import hashlib
import io
import os
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT_DIR = os.path.join(REPO_ROOT, "contrib-kit")
CONVENTIONS = os.path.join(REPO_ROOT, "scripts", "conventions.py")

# Everything the contributor receives, and nothing else. An allow-list, for the
# same reason deploy/publish-extension.cmd uses one: a deny-list silently ships
# whatever someone drops into the folder.
MEMBERS = {
    "revitmcp_kit.py": os.path.join(KIT_DIR, "revitmcp_kit.py"),
    "INSTRUCTION.md": os.path.join(KIT_DIR, "INSTRUCTION.md"),
    "README.md": os.path.join(KIT_DIR, "README.md"),
    "AGENTS.md": os.path.join(KIT_DIR, "AGENTS.md"),
    ".kilo/agents/revit-tool.md": os.path.join(
        KIT_DIR, ".kilo", "agents", "revit-tool.md"
    ),
    # Copied from scripts/, not from contrib-kit/: one source of truth.
    "conventions.py": CONVENTIONS,
}


def main():
    parser = argparse.ArgumentParser(description="Build the contributor kit zip.")
    parser.add_argument(
        "--out",
        default=os.path.join(REPO_ROOT, "dist"),
        help="directory to write revitmcp-contrib-kit.zip into (default: dist/)",
    )
    args = parser.parse_args()

    missing = sorted(name for name, path in MEMBERS.items() if not os.path.isfile(path))
    if missing:
        raise SystemExit("missing kit files: {}".format(missing))

    if not os.path.isdir(args.out):
        os.makedirs(args.out)
    target = os.path.join(args.out, "revitmcp-contrib-kit.zip")

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for arcname, path in sorted(MEMBERS.items()):
            archive.write(path, arcname)

    with io.open(CONVENTIONS, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()[:12]

    print("Built: {}".format(target))
    for arcname in sorted(MEMBERS):
        print("  " + arcname)
    print("")
    print("conventions.py sha256: {}".format(digest))
    print("")
    print("Publish it where contributors can reach it, next to the inbox:")
    print(r"  \\srv-dfs\BIM\06_RevitMCP\contrib-kit\ ")
    print("")
    print("Rebuild whenever scripts/conventions.py changes -- an outdated kit")
    print("passes packages that intake will reject.")


if __name__ == "__main__":
    main()
