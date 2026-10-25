# -*- coding: utf-8 -*-
r"""Build-time operator-policy tool: stage the path of the operator file, and check the file.

    "%MCP_PYEXE%" "%~dp0policy_tool.py" stage --policy-file "%MCP_POLICY_FILE%" --dest <app>\policy_source
    "%MCP_PYEXE%" "%~dp0policy_tool.py" check --policy-file "%MCP_POLICY_FILE%"

The operator policy (D-14, D-27) is one TOML file on the share that every RevitMCP server
reads at run time. A workstation does not know the share path, so the payload build stages
a one-line text file, app\policy_source, holding that UNC path; policy.py reads it on first
use. ``stage`` writes exactly the path plus one LF, as UTF-8 without a byte order mark.

``check`` validates the current operator file with the very validator the servers use and
prints one status line, never any file content:

    POLICY_FILE=absent                 no file there; the fleet runs the base policy
    POLICY_FILE=accepted <12 hex>      valid; <12 hex> is the policy hash the servers will report
    POLICY_FILE=rejected <key path>    invalid; the fleet keeps running the base policy
    POLICY_FILE=unreachable <class>    the share could not be read just now
    POLICY_FILE=unchecked <reason>     this build could not run the check

Every status exits 0: a missing or bad operator file warns, it never fails a build. Only a
defect in the staging itself (no path, nowhere to write) exits non-zero. The share ACL
(read-only for ordinary users) is an operator deployment requirement the build cannot verify.

Runs under pyRevit's embedded CPython; written for the standard library only. ``check``
imports policy.py from the repository root, which needs CPython 3.11 or newer.
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PolicyToolError(Exception):
    """The staging could not be done."""


def stage_policy_source(policy_file, dest):
    """Write ``policy_file`` and one LF to ``dest`` as UTF-8 without a byte order mark."""
    value = policy_file.strip()
    if not value:
        raise PolicyToolError("--policy-file is empty")
    if "\n" in value or "\r" in value or "\x00" in value:
        raise PolicyToolError("--policy-file must be a single-line path")
    parent = os.path.dirname(os.path.abspath(dest))
    os.makedirs(parent, exist_ok=True)
    with open(dest, "wb") as handle:
        handle.write(value.encode("utf-8") + b"\n")
    with open(dest, "rb") as handle:
        if handle.read() != value.encode("utf-8") + b"\n":
            raise PolicyToolError("the staged file does not read back identically: " + dest)


def check_policy_file(policy_file):
    """The one status line for the operator file (see the module docstring)."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    try:
        import policy
    except Exception as exc:  # an interpreter older than 3.11 has no tomllib
        return "POLICY_FILE=unchecked cannot import policy.py ({})".format(type(exc).__name__)
    try:
        with open(os.path.join(REPO_ROOT, policy.BASE_FILE), "rb") as handle:
            base_bytes = handle.read()
        base_document = policy.parse_policy_bytes(base_bytes)
        policy.validate_base(base_document)
    except (OSError, policy.PolicyError) as exc:
        return "POLICY_FILE=unchecked the base policy is not usable ({})".format(
            type(exc).__name__)
    try:
        with open(policy_file, "rb") as handle:
            data = handle.read(policy.MAX_OPERATOR_BYTES + 1)
    except FileNotFoundError as exc:
        if getattr(exc, "winerror", None) in (None, 2, 3):
            return "POLICY_FILE=absent"
        return "POLICY_FILE=unreachable {}".format(type(exc).__name__)
    except OSError as exc:
        return "POLICY_FILE=unreachable {}".format(type(exc).__name__)
    if len(data) > policy.MAX_OPERATOR_BYTES:
        return "POLICY_FILE=rejected the file is larger than {} bytes".format(
            policy.MAX_OPERATOR_BYTES)
    try:
        merged = policy.merge(base_document, policy.parse_policy_bytes(data))
        built = policy.build_policy(merged, "operator", policy.policy_hash(base_bytes, data))
    except policy.PolicyError as exc:
        return "POLICY_FILE=rejected {}".format(exc)
    return "POLICY_FILE=accepted {}".format(built.hash)


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Stage the operator policy path and check the operator policy file "
                    "(never prints file content)."
    )
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    stage = sub.add_parser("stage", help="write the operator file path into app\\policy_source")
    stage.add_argument("--policy-file", required=True)
    stage.add_argument("--dest", required=True)

    check = sub.add_parser("check", help="validate the operator file; always exits 0")
    check.add_argument("--policy-file", required=True)
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.policy_file.strip():
        parser.error("--policy-file must not be empty")  # exits 2
    try:
        if args.command == "stage":
            stage_policy_source(args.policy_file, args.dest)
            print("POLICY_SOURCE staged: {}".format(args.dest))
        else:
            line = check_policy_file(args.policy_file)
            print(line)
            if line.startswith(("POLICY_FILE=rejected", "POLICY_FILE=unreachable")):
                sys.stderr.write(
                    "WARNING: the operator policy file is not applied; servers run the "
                    "base policy shipped in the payload (or keep their last valid one).\n")
    except (PolicyToolError, OSError) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
