# -*- coding: utf-8 -*-
"""Two MCP entries, two Revit ports, one client (D-17, IDENT-05).

Older tier: a standalone script, run on its own, excluded from pytest.

TWO_INSTANCE_OK needs two live Revit instances running, a different model open
in each, listening on the two ports given by --ports (default 48884,48885).
Without Revit it still proves what it can: each stdio server entry reports its
own configured target, so the output contains one ``ENTRY ... target=host:port``
line per port, and the run ends in TWO_INSTANCE_FAIL with exit code 1.

Usage:
    uv run python tests/test_two_instance_targets.py --ports 48884,48885
    uv run python tests/test_two_instance_targets.py --ports 48997,48998  (offline)

The script never sends a POST and writes nothing to the servers' stdout.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PY = sys.executable
MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
LABELS = ("revit-a", "revit-b")


def _value_after(text, prefix):
    """First line starting with `prefix`, with the prefix stripped, else ''."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


async def _ask_entry(host, port):
    """Start one stdio server entry with its own REVIT_PORT; return status text."""
    params = StdioServerParameters(
        command=PY,
        args=[MAIN],
        env={"REVIT_HOST": host, "REVIT_PORT": str(port), "PYTHONUTF8": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool("get_revit_status", {})
            return " ".join(getattr(c, "text", "") for c in res.content)


def _listeners(ports):
    """Best effort: {port: [pids]} of listening sockets, via PowerShell."""
    result = dict((p, []) for p in ports)
    script = (
        "Get-NetTCPConnection -State Listen -LocalPort {} "
        "-ErrorAction SilentlyContinue | "
        "Select-Object LocalPort,OwningProcess | ConvertTo-Json -Compress"
    ).format(",".join(str(p) for p in ports))
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        rows = json.loads(out) if out else []
    except Exception:
        return result
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        port = row.get("LocalPort")
        pid = row.get("OwningProcess")
        if port in result and pid not in result[port]:
            result[port].append(pid)
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ports", default="48884,48885")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    ports = [int(p) for p in args.ports.split(",")]
    if len(ports) != 2:
        print("TWO_INSTANCE_FAIL: --ports needs exactly two ports")
        sys.exit(1)

    texts = await asyncio.gather(*[_ask_entry(args.host, p) for p in ports])

    failures = []
    entries = []
    for label, port, text in zip(LABELS, ports, texts):
        target = _value_after(text, "MCP target:")
        status = _value_after(text, "Status:")
        document = _value_after(text, "Document:")
        entries.append((target, status, document))
        print("ENTRY label={} port={} target={} status={} document={}".format(
            label, port, target, status, document))
        expected = "{}:{}".format(args.host, port)
        if target != expected:
            failures.append("{} target {!r} != {!r}".format(label, target, expected))
        if status != "active":
            failures.append("{} status {!r} is not 'active'".format(label, status))
        if not document:
            failures.append("{} reports no document".format(label))

    if entries[0][2] and entries[0][2] == entries[1][2]:
        failures.append("both entries report the same document {!r}".format(entries[0][2]))

    listeners = _listeners(ports)
    for port in ports:
        pids = listeners[port]
        print("LISTENERS port={} pids={}".format(port, ",".join(str(p) for p in pids)))
        if len(pids) != 1:
            failures.append("port {} has {} listening PIDs, expected 1".format(port, len(pids)))
    if all(len(listeners[p]) == 1 for p in ports) and listeners[ports[0]] == listeners[ports[1]]:
        failures.append("both ports are held by the same PID")

    if failures:
        print("TWO_INSTANCE_FAIL: " + "; ".join(failures))
        sys.exit(1)
    print("TWO_INSTANCE_OK")


asyncio.run(main())
