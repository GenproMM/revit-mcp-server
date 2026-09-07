# -*- coding: utf-8 -*-
"""Accept a contributed tool package into this repository.

    uv run python scripts/intake_package.py <package.zip> [--apply]

Contributors have no access to this repository. They build a self-contained
package with the contributor kit and drop it in the inbox share; this script is
the gate between that inbox and the working tree.

Without --apply it only inspects and reports. With --apply it copies the files
in and updates the manifest, leaving everything uncommitted for review.

WHAT THIS SCRIPT CAN AND CANNOT DO
----------------------------------
It can reject: packages that touch shared files, collide with existing names,
violate the conventions, or contain obviously dangerous constructs.

It cannot approve. The code being accepted runs as IronPython *inside the Revit
process*, with full Revit API and file system access, on every workstation in
the department. No static check establishes intent. A package that passes every
check here has earned a human reading it, nothing more.
"""

import argparse
import ast
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(REPO_ROOT, "tests", "unit", "tool_manifest.txt")

MAX_UNCOMPRESSED = 2 * 1024 * 1024  # a tool is a few KB; anything larger is wrong
IDENT = re.compile(r"^[a-z][a-z0-9_]*$")

# Modules a contributed tool has no business importing. The Revit half gets
# pyrevit/DB and the flat helpers; the MCP half gets the injected transport.
BANNED_IMPORTS = {
    "subprocess", "socket", "urllib", "urllib2", "urllib3", "httplib",
    "requests", "httpx", "ftplib", "smtplib", "telnetlib", "pickle",
    "marshal", "ctypes", "multiprocessing", "shutil", "tempfile", "webbrowser",
}
# Call names that need a human to look, wherever they appear.
BANNED_CALLS = {
    "eval", "exec", "compile", "__import__", "execfile", "input", "raw_input",
}
# Attribute calls that are suspicious on a contributed tool.
BANNED_ATTR_CALLS = {
    ("os", "system"), ("os", "remove"), ("os", "unlink"), ("os", "rmdir"),
    ("os", "popen"), ("os", "removedirs"), ("os", "startfile"),
    ("sys", "exit"),
}


class Reject(Exception):
    """A hard failure: the package does not enter the tree."""


def _fail(message):
    raise Reject(message)


def _norm(name):
    return name.replace("\\", "/")


# --------------------------------------------------------------------------
# 1. structural checks on the archive itself
# --------------------------------------------------------------------------

def read_package(zip_path):
    """Return {archive_path: text} after checking the archive is well formed."""
    if not zipfile.is_zipfile(zip_path):
        _fail("{} is not a zip archive".format(zip_path))

    files = {}
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        if bad is not None:
            _fail("archive is corrupt at {}".format(bad))

        total = 0
        for info in archive.infolist():
            name = _norm(info.filename)
            if name.endswith("/"):
                continue

            # Path traversal, absolute paths and drive letters. A contributed
            # archive is untrusted input; unpacking it naively is how a build
            # machine gets files written outside the target directory.
            if name.startswith("/") or ".." in name.split("/") or ":" in name:
                _fail("unsafe path in archive: {!r}".format(info.filename))

            # Symlinks are stored with this mode; following one on unpack
            # writes wherever it points.
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                _fail("archive contains a symlink: {!r}".format(info.filename))

            total += info.file_size
            if total > MAX_UNCOMPRESSED:
                _fail(
                    "archive expands to more than {} bytes -- a tool package "
                    "should be a few KB".format(MAX_UNCOMPRESSED)
                )

            files[name] = archive.read(info).decode("utf-8")

    return files


def check_layout(files):
    """Only the manifest, the two halves, optional tests and notes."""
    manifest_raw = files.get("manifest.json")
    if manifest_raw is None:
        _fail("manifest.json is missing")

    try:
        manifest = json.loads(manifest_raw)
    except ValueError as exc:
        _fail("manifest.json is not valid JSON: {}".format(exc))

    domain = manifest.get("domain")
    tools = manifest.get("tools")
    if not domain or not IDENT.match(domain):
        _fail("manifest domain must be lower snake_case, got {!r}".format(domain))
    if not isinstance(tools, list) or not tools:
        _fail("manifest must list at least one tool name in \"tools\"")
    for tool in tools:
        if not isinstance(tool, str) or not IDENT.match(tool):
            _fail("tool name must be lower snake_case, got {!r}".format(tool))
    if not manifest.get("author"):
        _fail("manifest must name an author -- the commit records who wrote this")

    allowed = {
        "manifest.json",
        "NOTES.md",
        "revit_mcp/{}.py".format(domain),
        "tools/{}_tools.py".format(domain),
        "tests/test_{}.py".format(domain),
    }
    extra = sorted(set(files) - allowed)
    if extra:
        _fail(
            "package contains files outside the allowed layout: {}\n"
            "        A capability is exactly two modules plus its own tests. "
            "Anything else -- edits to shared files, extra modules, data -- "
            "has to be discussed before it can be accepted.".format(extra)
        )

    for required in ("revit_mcp/{}.py".format(domain), "tools/{}_tools.py".format(domain)):
        if required not in files:
            _fail("package is missing {}".format(required))

    return manifest, domain, tools


# --------------------------------------------------------------------------
# 2. collision with what already exists
# --------------------------------------------------------------------------

def check_collisions(domain, tools):
    route = os.path.join(REPO_ROOT, "revit_mcp", domain + ".py")
    tool_module = os.path.join(REPO_ROOT, "tools", domain + "_tools.py")
    for path in (route, tool_module):
        if os.path.exists(path):
            _fail(
                "{} already exists -- this package would overwrite an existing "
                "domain. Ask the contributor to extend it by patch instead."
                .format(_rel(path))
            )

    with io.open(MANIFEST_PATH, encoding="utf-8") as handle:
        existing = {line.strip() for line in handle if line.strip()}
    clash = sorted(set(tools) & existing)
    if clash:
        _fail("these tool names are already taken: {}".format(clash))


def _rel(path):
    return os.path.relpath(path, REPO_ROOT).replace("\\", "/")


# --------------------------------------------------------------------------
# 3. static safety scan
# --------------------------------------------------------------------------

def scan_dangerous(files, domain):
    """Report constructs that need a human decision. Never silently allowed."""
    findings = []
    sources = {
        name: text
        for name, text in files.items()
        if name.endswith(".py")
    }

    for name, source in sorted(sources.items()):
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            _fail("{} does not parse: {}".format(name, exc))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in BANNED_IMPORTS:
                        findings.append((name, node.lineno, "imports " + alias.name))
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in BANNED_IMPORTS:
                    findings.append((name, node.lineno, "imports from " + root))
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in BANNED_CALLS:
                    findings.append((name, node.lineno, "calls " + func.id + "()"))
                elif isinstance(func, ast.Attribute):
                    owner = getattr(func.value, "id", None)
                    if (owner, func.attr) in BANNED_ATTR_CALLS:
                        findings.append(
                            (name, node.lineno, "calls {}.{}()".format(owner, func.attr))
                        )
                    if func.attr == "open" and owner == "io":
                        findings.append((name, node.lineno, "opens a file (io.open)"))
                elif isinstance(func, ast.Name) and func.id == "open":
                    findings.append((name, node.lineno, "opens a file"))

    return findings


# --------------------------------------------------------------------------
# 4. conventions + full suite, against a scratch copy of the tree
# --------------------------------------------------------------------------

def run_suite_with_package(files, domain, tools):
    """Copy the repo to a temp dir, add the package, run the whole suite."""
    scratch = tempfile.mkdtemp(prefix="intake-")
    try:
        work = os.path.join(scratch, "repo")
        shutil.copytree(
            REPO_ROOT,
            work,
            ignore=shutil.ignore_patterns(
                ".git", ".venv", "__pycache__", "graphify-out",
                "rvt-mcp_Obsidian", ".planning",
            ),
        )
        for archive_path in (
            "revit_mcp/{}.py".format(domain),
            "tools/{}_tools.py".format(domain),
            "tests/test_{}.py".format(domain),
        ):
            if archive_path not in files:
                continue
            target = os.path.join(work, *archive_path.split("/"))
            if archive_path.startswith("tests/"):
                target = os.path.join(work, "tests", "unit", os.path.basename(archive_path))
            with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(files[archive_path])

        manifest_target = os.path.join(work, "tests", "unit", "tool_manifest.txt")
        with io.open(manifest_target, encoding="utf-8") as handle:
            names = [line.strip() for line in handle if line.strip()]
        names.extend(tools)
        with io.open(manifest_target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(sorted(names)) + "\n")

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/unit", "-q"],
            cwd=work,
            capture_output=True,
            text=True,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# --------------------------------------------------------------------------
# 5. apply
# --------------------------------------------------------------------------

def apply_package(files, domain, tools):
    written = []
    for archive_path in (
        "revit_mcp/{}.py".format(domain),
        "tools/{}_tools.py".format(domain),
    ):
        target = os.path.join(REPO_ROOT, *archive_path.split("/"))
        with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(files[archive_path])
        written.append(_rel(target))

    test_path = "tests/test_{}.py".format(domain)
    if test_path in files:
        target = os.path.join(REPO_ROOT, "tests", "unit", os.path.basename(test_path))
        with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(files[test_path])
        written.append(_rel(target))

    with io.open(MANIFEST_PATH, encoding="utf-8") as handle:
        names = [line.strip() for line in handle if line.strip()]
    names.extend(tools)
    with io.open(MANIFEST_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(sorted(names)) + "\n")
    written.append(_rel(MANIFEST_PATH))
    return written


# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Inspect and optionally accept a contributed tool package."
    )
    parser.add_argument("package", help="path to the .zip produced by the contributor kit")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="copy the files in and update the manifest (still uncommitted)",
    )
    args = parser.parse_args()

    try:
        files = read_package(args.package)
        manifest, domain, tools = check_layout(files)
        check_collisions(domain, tools)
    except Reject as exc:
        print("REJECTED: {}".format(exc))
        return 1

    print("Package    : {}".format(os.path.basename(args.package)))
    print("Domain     : {}".format(domain))
    print("Tools      : {}".format(", ".join(tools)))
    print("Author     : {}".format(manifest.get("author")))
    print("Kind       : {}".format(manifest.get("kind", "unstated")))
    if manifest.get("description"):
        print("Purpose    : {}".format(manifest["description"]))
    print("")

    try:
        findings = scan_dangerous(files, domain)
    except Reject as exc:
        print("REJECTED: {}".format(exc))
        return 1

    if findings:
        print("NEEDS A HUMAN DECISION -- flagged constructs:")
        for name, line, what in findings:
            print("  {}:{}  {}".format(name, line, what))
        print("")
        print("  None of these are automatically fatal, and none are")
        print("  automatically fine. Read the code before going further.")
        print("")

    print("Running the full suite with this package applied...")
    code, output = run_suite_with_package(files, domain, tools)
    tail = [line for line in output.strip().splitlines() if line.strip()][-12:]
    for line in tail:
        print("  " + line)
    print("")

    if code != 0:
        print("REJECTED: the suite fails with this package applied.")
        print("Send the output above back to the contributor.")
        return 1

    print("Checks passed. This means the package MAY be reviewed -- not that it")
    print("may be merged. Read both modules before accepting: this code runs")
    print("inside Revit with full API access on every workstation.")
    print("")

    if not args.apply:
        print("Re-run with --apply to copy it into the working tree.")
        return 0

    written = apply_package(files, domain, tools)
    print("Applied (uncommitted):")
    for path in written:
        print("  " + path)
    print("")
    print("Next:")
    print("  1. Read revit_mcp/{}.py and tools/{}_tools.py in full.".format(domain, domain))
    print("  2. uv run pytest tests/unit")
    print("  3. Fully restart Revit, check /revit_mcp/status/?verbose=true")
    print("  4. Commit, crediting the author:")
    print("     git commit --author=\"{} <>\" ...".format(manifest.get("author")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
