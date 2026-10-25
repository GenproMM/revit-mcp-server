# -*- coding: utf-8 -*-
r"""Build a scratch payload locally and run the deployed acceptance gate on it.

What it proves (Phase 7, D-24): the real payload recipe of deploy/build-payload.cmd
-- dependencies from uv.lock installed with pyRevit's own embeddable CPython, the
same application files copied next to them -- imports the pinned mcp SDK and passes
deploy/gate.py. That is the exact situation the pywin32 path shim in deploy/server.py,
deploy/gate.py and deploy/warm.py exists for: the embeddable CPython ignores .pth
files, so `import mcp` only works because the entry points add the pywin32
directories themselves.

What it never does: write to a share, publish, or run build-payload.cmd,
publish-extension.cmd or update.cmd. Everything lands under the local temp directory
(or an explicit --dest that is neither inside the repository nor a UNC path). It
needs no Revit.

Usage:
    uv run python scripts/scratch_payload_gate.py [--pyexe PATH] [--dest DIR]

Interpreter lookup: --pyexe, else the MCP_PYEXE environment variable, else the newest
%APPDATA%\pyRevit-Master\bin\cengines\CPY*\python.exe. Exit codes: 0 = SCRATCH_GATE_OK,
1 = SCRATCH_GATE_FAILED, 2 = refused (no interpreter, unsafe destination, missing tool).
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_CMD = os.path.join(REPO_ROOT, "deploy", "build-payload.cmd")
DEFAULT_DEST = os.path.join(tempfile.gettempdir(), "revitmcp-phase7-scratch-payload")
MARKER = ".revitmcp-scratch-payload"

# copy /y "%REPO%\main.py" "%BUILD%\app\" ...   and   copy /y "%~dp0server.py" "%BUILD%\app\" ...
COPY_RE = re.compile(
    r'^\s*copy\s+/y\s+"(?P<src>%REPO%\\|%~dp0)(?P<name>[^"\\]+)"\s+"%BUILD%\\app\\"', re.IGNORECASE
)


def refuse(message):
    sys.stderr.write("scratch_payload_gate: refused: %s\n" % message)
    sys.exit(2)


def find_pyexe(explicit):
    if explicit:
        candidate = explicit
    elif os.environ.get("MCP_PYEXE"):
        candidate = os.environ["MCP_PYEXE"]
    else:
        appdata = os.environ.get("APPDATA", "")
        pattern = os.path.join(appdata, "pyRevit-Master", "bin", "cengines", "CPY*", "python.exe")
        matches = sorted(glob.glob(pattern), reverse=True)
        candidate = matches[0] if matches else None
    if not candidate or not os.path.isfile(candidate):
        refuse("pyRevit's CPython engine was not found (use --pyexe or MCP_PYEXE)")
    return os.path.abspath(candidate)


def interpreter_version(pyexe):
    out = subprocess.run(
        [pyexe, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
        capture_output=True, text=True, check=False,
    )
    version = out.stdout.strip()
    if out.returncode != 0 or not re.match(r"^\d+\.\d+$", version):
        refuse("could not ask %s for its version" % pyexe)
    return version


def check_dest(dest):
    dest = os.path.abspath(dest)
    if dest.startswith("\\\\"):
        refuse("destination %s is a UNC path; the scratch gate never touches a share" % dest)
    real_dest = os.path.normcase(os.path.realpath(dest))
    real_repo = os.path.normcase(os.path.realpath(REPO_ROOT))
    if real_dest == real_repo or real_dest.startswith(real_repo + os.sep):
        refuse("destination %s lies inside the repository" % dest)
    if real_repo.startswith(real_dest + os.sep):
        refuse("destination %s contains the repository" % dest)
    if os.path.isdir(dest) and os.listdir(dest) and not os.path.isfile(os.path.join(dest, MARKER)):
        refuse("destination %s exists, is not empty and is not a previous scratch payload" % dest)
    return dest


def fresh_dir(dest):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    with open(os.path.join(dest, MARKER), "w") as handle:
        handle.write("scratch payload of scripts/scratch_payload_gate.py\n")


def app_files():
    """Files build-payload.cmd copies into %BUILD%\\app\\, parsed so the layout follows the real build."""
    found = []
    with open(BUILD_CMD, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = COPY_RE.match(line)
            if not match:
                continue
            base = REPO_ROOT if match.group("src").upper() == "%REPO%\\" else os.path.join(REPO_ROOT, "deploy")
            found.append(os.path.join(base, match.group("name")))
    if not found:
        refuse("no 'copy /y ... %BUILD%\\app\\' lines found in %s" % BUILD_CMD)
    return found


def run(cmd, env=None):
    sys.stdout.write("$ %s\n" % " ".join(cmd))
    sys.stdout.flush()
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, check=False)


def echo(result):
    if result.stdout:
        sys.stdout.write(result.stdout if result.stdout.endswith("\n") else result.stdout + "\n")
    if result.stderr:
        sys.stdout.write(result.stderr if result.stderr.endswith("\n") else result.stderr + "\n")
    sys.stdout.flush()


def fail(message):
    sys.stdout.write("%s\nSCRATCH_GATE_FAILED\n" % message)
    sys.exit(1)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scratch payload build plus gate run (never a share).")
    parser.add_argument("--pyexe", help="pyRevit's embeddable CPython (default: MCP_PYEXE or the newest cengine)")
    parser.add_argument("--dest", default=DEFAULT_DEST, help="scratch directory (default: %s)" % DEFAULT_DEST)
    args = parser.parse_args(argv)

    pyexe = find_pyexe(args.pyexe)
    version = interpreter_version(pyexe)
    dest = check_dest(args.dest)
    uv = shutil.which("uv")
    if not uv:
        refuse("uv was not found on PATH")

    print("python : %s (CPython %s)" % (pyexe, version))
    print("dest   : %s" % dest)
    fresh_dir(dest)

    lock = os.path.join(dest, "requirements.lock.txt")
    step = run([uv, "export", "--project", REPO_ROOT, "--frozen", "--no-dev", "--no-emit-project",
                "--format", "requirements.txt", "-o", lock])
    if step.returncode != 0:
        echo(step)
        fail("uv export failed")

    libs = os.path.join(dest, "app", "libs")
    step = run([uv, "pip", "install", "--python", pyexe, "--target", libs,
                "--python-platform", "windows", "--python-version", version,
                "--compile-bytecode", "-r", lock])
    if step.returncode != 0:
        echo(step)
        fail("uv pip install failed")

    app = os.path.join(dest, "app")
    for source in app_files():
        if not os.path.isfile(source):
            fail("build-payload.cmd names %s, which does not exist" % source)
        shutil.copy2(source, app)
    ignore = shutil.ignore_patterns("__pycache__")
    for name in ("tools", "tests"):
        shutil.copytree(os.path.join(REPO_ROOT, name), os.path.join(app, name), ignore=ignore)

    env = dict(os.environ)
    env.pop("MCP_SECRET_FILE", None)

    warm = run([pyexe, os.path.join(app, "warm.py")], env=env)
    echo(warm)
    gate = run([pyexe, os.path.join(app, "gate.py")], env=env)
    echo(gate)

    gate_lines = [line.strip() for line in gate.stdout.splitlines()]
    if warm.returncode == 0 and "warm ok" in warm.stdout and gate.returncode == 0 and "GATE_OK" in gate_lines:
        print("SCRATCH_GATE_OK")
        return 0
    fail("warm.py exit %s, gate.py exit %s" % (warm.returncode, gate.returncode))


if __name__ == "__main__":
    sys.exit(main())
