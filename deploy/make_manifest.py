# -*- coding: utf-8 -*-
r"""Write the integrity manifest of a published extension copy.

    "%MCP_PYEXE%" "%~dp0make_manifest.py" --repo "%REPO%" --dest "%DEST%"

Run at publish time, after the files have been copied to DEST. It writes
DEST\_manifest.json (and nothing else, and never inside the git working tree):

    {"schema": 1, "generated_at": "...Z", "commit": "<40 hex>",
     "files": {"revit_mcp/x.py": "<sha256 hex>", ...}}

The LIST of files comes from ``git ls-files`` over the repository (startup.py,
extension.json and revit_mcp/), so caches, .pyc files and anything untracked can
never be listed. The HASHES come from the published copies in DEST, which is what
the extension will actually load. The hash function is revit_mcp.integrity's own
hash_normalized (CRLF replaced by LF), imported from the checkout this tool lives
in, so the generator and the verifier cannot drift apart.

Runs under CPython 3.8 or newer (including pyRevit's embedded one): no annotations,
standard library only.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

REPO_OF_THIS_TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TRACKED_SCOPE = ["startup.py", "extension.json", "revit_mcp"]
_HEX = "0123456789abcdef"


class ManifestError(Exception):
    """A condition that makes publishing a manifest unsafe or impossible."""


def _hashing():
    """(hash_normalized, MANIFEST_NAME, SCOPE_DIR) from this tool's own checkout.

    pyRevit's CPython ignores PYTHONPATH, so the checkout is put on sys.path here.
    The hasher always comes from the checkout this file lives in, never from --repo.
    """
    if REPO_OF_THIS_TOOL not in sys.path:
        sys.path.insert(0, REPO_OF_THIS_TOOL)
    from revit_mcp.integrity import MANIFEST_NAME, SCOPE_DIR, hash_normalized
    return hash_normalized, MANIFEST_NAME, SCOPE_DIR


hash_normalized, MANIFEST_NAME, SCOPE_DIR = _hashing()


def tracked_files(repo, run=subprocess.run):
    """Sorted tracked .py and .json paths under the published scope, from git ls-files."""
    try:
        done = run(
            ["git", "-C", repo, "ls-files", "-z", "--"] + _TRACKED_SCOPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        done = None
    if done is None or done.returncode != 0:
        raise ManifestError(
            "git ls-files failed in {}: publishing needs a git checkout".format(repo)
        )
    names = done.stdout.decode("utf-8").split("\0")
    kept = sorted(
        n for n in names
        if n and n.endswith((".py", ".json")) and n.rsplit("/", 1)[-1] != MANIFEST_NAME
    )
    if not kept:
        raise ManifestError("git ls-files found no tracked files in {}".format(repo))
    return kept


def current_commit(repo, run=subprocess.run):
    """The full 40-hex HEAD commit of ``repo``."""
    try:
        done = run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        done = None
    if done is None or done.returncode != 0:
        raise ManifestError("git rev-parse HEAD failed in {}".format(repo))
    sha = done.stdout.decode("utf-8").strip()
    if len(sha) != 40 or any(c not in _HEX for c in sha):
        raise ManifestError("git rev-parse HEAD gave an unexpected value: {!r}".format(sha))
    return sha


def _refuse_repo_dest(repo, dest):
    """Refuse a destination that is, or lies inside, the git working tree."""
    real_repo = os.path.normcase(os.path.realpath(repo))
    real_dest = os.path.normcase(os.path.realpath(dest))
    try:
        inside = os.path.commonpath([real_repo, real_dest]) == real_repo
    except ValueError:  # different drives
        inside = False
    if inside:
        raise ManifestError(
            "refusing to write a manifest into the git working tree (INTG-08)"
        )


def build_manifest(repo, dest, commit=None, now=None, run=subprocess.run):
    """The manifest dict for the published copy in ``dest`` of the checkout ``repo``."""
    _refuse_repo_dest(repo, dest)
    tracked = tracked_files(repo, run=run)
    files = {}
    for relpath in tracked:
        path = os.path.join(dest, *relpath.split("/"))
        if not os.path.isfile(path):
            raise ManifestError(
                "tracked file missing from the published tree: {}".format(relpath)
            )
        with open(path, "rb") as handle:
            files[relpath] = hash_normalized(handle.read())
    scope = os.path.join(dest, SCOPE_DIR)
    present = []
    if os.path.isdir(scope):
        for name in os.listdir(scope):
            if name.endswith(".py") and os.path.isfile(os.path.join(scope, name)):
                present.append(SCOPE_DIR + "/" + name)
    untracked = sorted(p for p in present if p not in files)
    if untracked:
        raise ManifestError(
            "untracked .py in the published tree: {}; commit it or remove it before "
            "publishing, or every workstation will report it as unexpected".format(
                ", ".join(untracked))
        )
    if commit is None:
        commit = current_commit(repo, run=run)
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "schema": 1,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": commit,
        "files": files,
    }


def write_manifest(dest, manifest):
    """Write dest/_manifest.json atomically: a temporary file, then os.replace."""
    final = os.path.join(dest, MANIFEST_NAME)
    temporary = final + ".tmp"
    text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    try:
        with open(temporary, "wb") as handle:
            handle.write(text.encode("ascii"))
        os.replace(temporary, final)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise
    return final


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write _manifest.json for a published copy.")
    parser.add_argument("--repo", default=REPO_OF_THIS_TOOL,
                        help="git checkout the file list comes from (default: this tool's repository)")
    parser.add_argument("--dest", required=True,
                        help="published extension directory that receives _manifest.json")
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(args.repo, args.dest)
        path = write_manifest(args.dest, manifest)
    except (ManifestError, OSError) as exc:
        sys.stderr.write("ERROR: {}\n".format(exc))
        return 1
    print("MANIFEST written: {} ({} files, commit {})".format(
        path, len(manifest["files"]), manifest["commit"][:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
