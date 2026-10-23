# -*- coding: utf-8 -*-
r"""Build-time shared-secret tool: create once, stage byte-for-byte, verify the pair.

    "%MCP_PYEXE%" "%~dp0secret_tool.py" ensure --secret-file "%MCP_SECRET_FILE%"
    "%MCP_PYEXE%" "%~dp0secret_tool.py" stage  --secret-file "%MCP_SECRET_FILE%" --dest <artifact>
    "%MCP_PYEXE%" "%~dp0secret_tool.py" verify --secret-file "%MCP_SECRET_FILE%" --artifact <artifact>

ensure creates the fleet secret exactly once (secrets.token_urlsafe(32), written
through O_CREAT|O_EXCL) and never overwrites or regenerates an existing file.
stage copies it byte-for-byte into an artifact and then verifies the copy.
verify fails when either file is missing or malformed or when the two differ.

The secret is stable rather than per-build. update.cmd refreshes the payload
while Revit keeps the old extension loaded, so a fresh secret on every build
would disable every mutation until each Revit is restarted. Rotation is a
deliberate procedure: delete MCP_SECRET_FILE, rebuild the payload, republish the
extension, restart Revit everywhere.

The secret is a network barrier against callers on the LAN. It is not
protection from anyone who can read the share, ext\ or an installed payload.

No output of this tool (stdout, stderr, exception text) contains the secret
value: messages name paths and defects only.

Runs under pyRevit's embedded CPython, which is 3.8 on pyRevit 4.8 hosts, so it
is written for Python 3.8 with the standard library only.
"""

import argparse
import os
import re
import secrets
import sys

TOKEN_BYTES = 32
MIN_LENGTH = 16
_TOKEN = re.compile(r"\A[A-Za-z0-9_-]+\Z")


class SecretToolError(Exception):
    """A secret file is missing, malformed or does not match its pair."""


def validate_secret_bytes(raw, label):
    """Raise SecretToolError naming ``label`` (a path) and the defect, never the value."""
    if not raw:
        raise SecretToolError("{} is empty".format(label))
    if raw.startswith(b"\xef\xbb\xbf"):
        raise SecretToolError("{} starts with a UTF-8 byte order mark".format(label))
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        raise SecretToolError("{} is UTF-16 text (byte order mark)".format(label))
    if b"\x00" in raw:
        raise SecretToolError("{} contains a NUL byte".format(label))
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise SecretToolError("{} contains non-ASCII bytes".format(label))
    if not _TOKEN.match(text):
        raise SecretToolError(
            "{} contains characters outside A-Z a-z 0-9 _ - "
            "(whitespace and a trailing newline are not allowed)".format(label)
        )
    if len(text) < MIN_LENGTH:
        raise SecretToolError(
            "{} is shorter than {} characters".format(label, MIN_LENGTH)
        )


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _validate_existing(path):
    validate_secret_bytes(_read_bytes(path), path)


def _ensure_parent(path):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)


def ensure_secret(path):
    """Create the secret at ``path`` once. True if created, False if it already existed.

    An existing file is validated and left untouched, never regenerated.
    """
    if os.path.exists(path):
        _validate_existing(path)
        return False
    _ensure_parent(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        # Another build created it between the check and the create.
        _validate_existing(path)
        return False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(secrets.token_urlsafe(TOKEN_BYTES).encode("ascii"))
    except BaseException:
        # Do not leave a truncated secret that a later run would have to reject.
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return True


def verify_pair(secret_file, artifact):
    """Both files must exist, be well formed and be byte-for-byte equal."""
    for path in (secret_file, artifact):
        if not os.path.isfile(path):
            raise SecretToolError("{} does not exist".format(path))
    secret_raw = _read_bytes(secret_file)
    artifact_raw = _read_bytes(artifact)
    validate_secret_bytes(secret_raw, secret_file)
    validate_secret_bytes(artifact_raw, artifact)
    if secret_raw != artifact_raw:
        raise SecretToolError(
            "{} does not match MCP_SECRET_FILE byte for byte".format(artifact)
        )


def stage_secret(secret_file, dest):
    """Ensure the secret exists, copy its bytes to ``dest`` and verify the copy."""
    ensure_secret(secret_file)
    raw = _read_bytes(secret_file)
    _ensure_parent(dest)
    with open(dest, "wb") as handle:
        handle.write(raw)
    verify_pair(secret_file, dest)


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Create, stage and verify the shared secret (never prints it)."
    )
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    ensure = sub.add_parser("ensure", help="create the secret if absent")
    ensure.add_argument("--secret-file", required=True)

    stage = sub.add_parser("stage", help="copy the secret into an artifact and verify")
    stage.add_argument("--secret-file", required=True)
    stage.add_argument("--dest", required=True)

    verify = sub.add_parser("verify", help="check an artifact equals the secret")
    verify.add_argument("--secret-file", required=True)
    verify.add_argument("--artifact", required=True)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "ensure":
            if ensure_secret(args.secret_file):
                print("SECRET ensure: created {}".format(args.secret_file))
            else:
                print("SECRET ensure: exists, left unchanged {}".format(args.secret_file))
        elif args.command == "stage":
            stage_secret(args.secret_file, args.dest)
            print("SECRET staged: {}".format(args.dest))
        else:
            verify_pair(args.secret_file, args.artifact)
            print("SECRET verify: ok {}".format(args.artifact))
    except (SecretToolError, OSError) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
