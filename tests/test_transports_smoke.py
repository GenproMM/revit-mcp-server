# -*- coding: utf-8 -*-
"""Standalone smoke test of the three HTTP transports of main.py (Phase 7, D-06).

Older tier: no test_ functions, excluded from pytest, run by hand:

    uv run python tests/test_transports_smoke.py

For each mode in streamable-http, sse and combined it starts main.py's server in a
child process on a free loopback port, lists the tools through the matching MCP
client and asserts that all 59 are served. Prints "TRANSPORT_OK <mode> tools=59" per
mode and, when every mode passed, TRANSPORTS_OK.

Needs no Revit: listing tools never reaches the Routes server. The child gets a
throwaway audit directory so nothing is written to the real one.
"""

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED_TOOLS = 59
MODES = ("streamable-http", "sse", "combined")
STARTUP_CAP_S = 15.0

CHILD = r"""
import sys
sys.path.insert(0, {repo!r})
import main
main.mcp.settings.host = "127.0.0.1"
main.mcp.settings.port = {port}
mode = {mode!r}
if mode == "combined":
    import anyio
    anyio.run(main.run_combined_async)
else:
    main.mcp.run(transport=mode)
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(port, child):
    deadline = time.time() + STARTUP_CAP_S
    while time.time() < deadline:
        if child.poll() is not None:
            raise RuntimeError("server exited early with code %s" % child.returncode)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("port %d did not accept connections within %.0f s" % (port, STARTUP_CAP_S))


async def count_tools_streamable_http(port):
    async with streamablehttp_client("http://127.0.0.1:%d/mcp" % port) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return len((await session.list_tools()).tools)


async def count_tools_sse(port):
    async with sse_client("http://127.0.0.1:%d/sse" % port) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return len((await session.list_tools()).tools)


async def check_mode(mode, port):
    counters = []
    if mode in ("streamable-http", "combined"):
        counters.append(("/mcp", count_tools_streamable_http))
    if mode in ("sse", "combined"):
        counters.append(("/sse", count_tools_sse))
    for endpoint, counter in counters:
        count = await asyncio.wait_for(counter(port), timeout=30)
        assert count == EXPECTED_TOOLS, "%s %s lists %d tools, expected %d" % (
            mode, endpoint, count, EXPECTED_TOOLS)


def run_mode(mode):
    port = free_port()
    env = dict(os.environ)
    audit_dir = tempfile.mkdtemp(prefix="revitmcp-transport-smoke-")
    env["REVIT_MCP_AUDIT_DIR"] = os.path.join(audit_dir, "audit")
    log = tempfile.TemporaryFile()
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD.format(repo=REPO_ROOT, port=port, mode=mode)],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
    )
    try:
        wait_for_port(port, child)
        asyncio.run(check_mode(mode, port))
    except BaseException:
        log.seek(0)
        sys.stdout.write("--- server output (%s) ---\n%s\n" % (mode, log.read().decode("utf-8", "replace")[-3000:]))
        raise
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        log.close()
        shutil.rmtree(audit_dir, ignore_errors=True)
    print("TRANSPORT_OK %s tools=%d" % (mode, EXPECTED_TOOLS))


if __name__ == "__main__":
    for transport_mode in MODES:
        run_mode(transport_mode)
    print("TRANSPORTS_OK")
