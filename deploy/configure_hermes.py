#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Idempotently register the Revit MCP server in the user's Hermes Agent config.

Runs on the WORKSTATION, executed by pyRevit's own bundled CPython:

    python.exe configure_hermes.py --root <install root> --python <that python.exe>

This edits a file the user owns and may have hand-written, so the strategy is
deliberately conservative:

  * PyYAML is NOT used. It drops comments, reorders keys (``sort_keys=True``),
    and is YAML 1.1 -- where a bare ``on`` / ``no`` / ``y`` anywhere in the file
    silently becomes a boolean and ``22:30`` becomes an integer.
  * ruamel.yaml is used ONLY to validate, never to re-emit.
  * The actual write is a text splice between sentinel comments, so every byte
    outside our managed block is preserved exactly.
  * If the user already has an ``mcp_servers`` entry with our name outside the
    sentinels, we refuse to touch it and print the block for a manual merge.

This module is deploy-only. Nothing the stdio server imports may import it --
it prints to stdout, which would corrupt the MCP protocol stream.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

# ruamel.yaml ships beside this script in install-libs\. It has to be put on
# sys.path here rather than via PYTHONPATH: pyRevit's embeddable CPython has a
# python3XX._pth next to it, which makes the interpreter ignore PYTHONPATH.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "install-libs")
)

BEGIN = "# >>> RevitMCP managed block -- do not edit by hand >>>"
END = "# <<< RevitMCP managed block <<<"

DEFAULT_NAME = "revit"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def die(msg: str, code: int = 1) -> "None":
    sys.stderr.write("ERROR: {}\n".format(msg))
    raise SystemExit(code)


def hermes_is_running() -> bool:
    """True if any running process image name contains 'hermes'.

    Hermes reads config.yaml at startup and may write it back from its own
    settings UI, which would clobber whatever we splice in.
    """
    try:
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return False  # can't tell -- don't block the install on it
    text = out.decode("utf-8", "replace").lower()
    return "hermes" in text


def read_text(path: str) -> "tuple[str, str, bool]":
    """Return (text, newline, had_bom), preserving the file's own conventions."""
    with open(path, "rb") as fh:
        raw = fh.read()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]
    text = raw.decode("utf-8")
    newline = "\r\n" if text.count("\r\n") >= text.count("\n") - text.count("\r\n") else "\n"
    if "\r\n" not in text:
        newline = "\n"
    return text.replace("\r\n", "\n"), newline, had_bom


def write_text_atomic(path: str, text: str, newline: str, bom: bool) -> None:
    payload = text.replace("\n", newline).encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)  # atomic on NTFS within a volume


def validate(text: str, name: str, require_absent: bool) -> "str | None":
    """Parse with ruamel; return an error string, or None if the doc is usable."""
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError
    except ImportError:
        return None  # validation unavailable; the splice is still safe

    yaml = YAML()
    try:
        doc = yaml.load(text)
    except YAMLError as exc:
        return "config.yaml does not parse as YAML: {}".format(exc)

    if doc is None:
        return None
    if not hasattr(doc, "get"):
        return "config.yaml top level is not a mapping"

    servers = doc.get("mcp_servers")
    if servers is None:
        return None
    if not hasattr(servers, "get"):
        return "'mcp_servers' exists but is not a mapping"
    if require_absent and name in servers:
        return (
            "'mcp_servers.{}' already exists outside the managed block".format(name)
        )
    return None


# --------------------------------------------------------------------------- #
# block construction
# --------------------------------------------------------------------------- #

def yq(value: str) -> str:
    """Double-quoted YAML scalar. Backslashes must be escaped inside them."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_block(name: str, python_exe: str, entry_py: str, indent: str) -> str:
    i1 = indent
    i2 = indent * 2
    i3 = indent * 3
    lines = [
        i1 + BEGIN,
        i1 + "{}:".format(name),
        i2 + "command: {}".format(yq(python_exe)),
        i2 + "args: [{}]".format(yq(entry_py)),
        # start_revit blocks while Revit cold-starts and pyRevit loads -- 60-180 s
        # normally, longer with a large central model. The default per-call
        # timeout would cut that off mid-launch.
        i2 + "timeout: 600",
        i2 + "env:",
        # Routes binds 127.0.0.1 (IPv4 only). main.py defaults REVIT_HOST to
        # "localhost", which resolves to ::1 first on an IPv6-enabled image --
        # costing a failed connect on every single call.
        i3 + 'REVIT_HOST: "127.0.0.1"',
        # No PYTHONHOME/PYTHONPATH here. The interpreter is pyRevit's embeddable
        # CPython: it ships a python3XX._pth, which disables site and makes it
        # ignore PYTHONPATH outright, and setting PYTHONHOME would break its
        # zip-based stdlib. server.py injects sys.path itself instead.
        i3 + 'PYTHONUTF8: "1"',
        i3 + 'PYTHONIOENCODING: "utf-8"',
        i1 + END,
    ]
    return "\n".join(lines)


def detect_indent(lines: "list[str]", start: int) -> str:
    """Indent used by the children of the mcp_servers: line at index `start`."""
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        lead = len(line) - len(line.lstrip())
        if lead == 0:
            break
        return " " * lead
    return "  "


def find_mcp_servers(lines: "list[str]") -> int:
    for idx, line in enumerate(lines):
        if re.match(r"^mcp_servers\s*:", line):
            return idx
    return -1


def region_end(lines: "list[str]", start: int) -> int:
    """Index one past the last line belonging to the mcp_servers block."""
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) == 0:
            end = idx
            break
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def splice(text: str, name: str, python_exe: str, entry_py: str) -> "tuple[str, str]":
    """Return (new_text, what_happened). Raises RuntimeError if a manual merge is needed."""
    lines = text.split("\n")

    # 1. Existing managed block -> replace it in place.
    b = next((i for i, l in enumerate(lines) if l.strip() == BEGIN), -1)
    e = next((i for i, l in enumerate(lines) if l.strip() == END), -1)
    if b != -1 and e != -1 and e > b:
        indent = " " * (len(lines[b]) - len(lines[b].lstrip())) or "  "
        block = build_block(name, python_exe, entry_py, indent)
        return "\n".join(lines[:b] + block.split("\n") + lines[e + 1:]), "updated"
    if (b == -1) != (e == -1):
        raise RuntimeError(
            "found only one of the two managed-block sentinels -- the block was "
            "edited by hand; remove it entirely and re-run"
        )

    # 2. No managed block. Find or create the mcp_servers mapping.
    idx = find_mcp_servers(lines)
    if idx == -1:
        err = validate(text, name, require_absent=True)
        if err:
            raise RuntimeError(err)
        block = build_block(name, python_exe, entry_py, "  ")
        prefix = lines[:]
        while prefix and not prefix[-1].strip():
            prefix.pop()
        tail = ["", "mcp_servers:"] + block.split("\n") + [""]
        return "\n".join(prefix + tail), "created mcp_servers"

    inline = re.sub(r"^mcp_servers\s*:", "", lines[idx]).strip()
    if inline and not inline.startswith("#"):
        if inline in ("{}", "{ }"):
            lines[idx] = "mcp_servers:"
        else:
            raise RuntimeError(
                "'mcp_servers' is written inline as {!r}; cannot splice safely".format(inline)
            )

    err = validate("\n".join(lines), name, require_absent=True)
    if err:
        raise RuntimeError(err)

    indent = detect_indent(lines, idx)
    block = build_block(name, python_exe, entry_py, indent)
    end = region_end(lines, idx)
    return "\n".join(lines[:end] + block.split("\n") + lines[end:]), "added"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv: "list[str]") -> int:
    ap = argparse.ArgumentParser(description="Register the Revit MCP server with Hermes Agent.")
    ap.add_argument("--root", required=True,
                    help=r"Install root, e.g. %%LOCALAPPDATA%%\RevitMCP\current")
    ap.add_argument("--config", default=None,
                    help="Path to Hermes config.yaml (default: ~/.hermes/config.yaml)")
    ap.add_argument("--python", required=True,
                    help=r"Interpreter Hermes should launch -- pyRevit's bundled "
                         r"CPython at bin\cengines\CPY*\python.exe")
    ap.add_argument("--name", default=DEFAULT_NAME, help="MCP server name (default: revit)")
    ap.add_argument("--print-only", action="store_true",
                    help="Print the block and exit without writing anything")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    python_exe = os.path.abspath(args.python)
    # server.py, not main.py: it injects libs\ onto sys.path first, which the
    # embeddable interpreter cannot be told to do any other way.
    entry_py = os.path.join(root, "app", "server.py")

    for label, path in (("interpreter", python_exe), ("server entry point", entry_py)):
        if not os.path.isfile(path):
            die("{} not found: {}\nRun the payload copy step first.".format(label, path))

    cfg = args.config or os.path.join(os.path.expanduser("~"), ".hermes", "config.yaml")
    cfg = os.path.abspath(cfg)

    block_preview = build_block(args.name, python_exe, entry_py, "  ")

    if args.print_only:
        print("mcp_servers:")
        print(block_preview)
        return 0

    if hermes_is_running():
        sys.stderr.write(
            "\nHermes Agent is running. It read config.yaml at startup and may write it\n"
            "back from its own settings UI, which would discard this change.\n"
            "Close Hermes and re-run this installer, or paste the block below by hand:\n\n"
            "mcp_servers:\n" + block_preview + "\n\n"
        )
        return 2

    if not os.path.isfile(cfg):
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        body = "mcp_servers:\n" + block_preview + "\n"
        write_text_atomic(cfg, body, "\r\n", False)
        print("Created {}".format(cfg))
        return 0

    text, newline, bom = read_text(cfg)
    try:
        new_text, action = splice(text, args.name, python_exe, entry_py)
    except RuntimeError as exc:
        sys.stderr.write(
            "\nRefusing to modify {}:\n  {}\n\n"
            "Nothing was changed. Merge this block under 'mcp_servers:' by hand:\n\n"
            "{}\n\n".format(cfg, exc, block_preview)
        )
        return 3

    if new_text == text:
        print("{} already up to date.".format(cfg))
        return 0

    backup = "{}.bak.{}".format(cfg, time.strftime("%Y%m%d-%H%M%S"))
    write_text_atomic(backup, text, newline, bom)
    write_text_atomic(cfg, new_text, newline, bom)

    # Re-read and re-validate what we actually wrote; roll back on any doubt.
    verify, _, _ = read_text(cfg)
    err = validate(verify, args.name, require_absent=False)
    if err:
        write_text_atomic(cfg, text, newline, bom)
        die("post-write validation failed ({}); restored from {}".format(err, backup))

    print("{} {} (backup: {})".format(cfg, action, os.path.basename(backup)))
    print("Run /reload-mcp in Hermes, or restart it, to pick up the change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
