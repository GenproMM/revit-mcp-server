# -*- coding: utf-8 -*-
r"""Acceptance check for a deployed install: spawn server.py over stdio and
measure time to the initialize response, then count the registered tools.

Mirrors tests/test_init_latency.py, but exercises the *deployed* entry point
(server.py, with its sys.path injection) under the *deployed* interpreter,
which is what production actually runs.

    <pyrevit python.exe> <install root>\app\gate.py
"""

import asyncio
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "libs"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

LIMIT = 2.0

# Shipped by build-payload.cmd's robocopy of tests\ into app\.
MANIFEST = os.path.join(HERE, "tests", "unit", "tool_manifest.txt")

# Staged by build-payload.cmd (secret_tool.py stage) from MCP_SECRET_FILE.
SECRET_ARTIFACT = os.path.join(HERE, "_bridge_secret")


def _secret_pair_status(artifact=SECRET_ARTIFACT, secret_file=None):
    """(status, message) for the staged secret against MCP_SECRET_FILE.

    status is "ok", "failed" or "unchecked" (MCP_SECRET_FILE is not set, so a
    gate run outside the build has nothing to compare against). Messages name
    paths and defects only, never a secret value.
    """
    if secret_file is None:
        secret_file = os.environ.get("MCP_SECRET_FILE")
    if not secret_file:
        return "unchecked", "MCP_SECRET_FILE not set"
    raw = {}
    for path in (secret_file, artifact):
        try:
            with open(path, "rb") as handle:
                raw[path] = handle.read()
        except OSError:
            return "failed", "cannot read %s" % path
    if not raw[secret_file].strip():
        return "failed", "MCP_SECRET_FILE is empty"
    if raw[artifact] != raw[secret_file]:
        return "failed", "app\\_bridge_secret does not match MCP_SECRET_FILE byte for byte"
    return "ok", "app\\_bridge_secret matches MCP_SECRET_FILE"


def _expected_tools():
    """Tool names the payload is supposed to expose, or None if unavailable.

    Registration is by convention, so a domain that fails to import is skipped
    and the server still starts -- deliberately, so one broken domain cannot
    take down a fleet. That safety only works if a release still refuses to
    publish the shortfall, which is what this list is for.
    """
    try:
        with open(MANIFEST, encoding="utf-8") as handle:
            return sorted(line.strip() for line in handle if line.strip())
    except OSError:
        return None


async def main():
    status, message = _secret_pair_status()
    print("SECRET=%s (%s)" % (status, message))
    assert status != "failed", message

    t0 = time.time()
    params = StdioServerParameters(command=sys.executable,
                                   args=[os.path.join(HERE, "server.py")])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            info = await session.initialize()
            dt = time.time() - t0
            tools = await session.list_tools()
            print("INIT_LATENCY_S=%.3f" % dt)
            print("SERVER=%s" % info.serverInfo.name)
            print("TOOLS=%d" % len(tools.tools))
            assert tools.tools, "no tools registered"
            assert dt < LIMIT, "initialize too slow: %.3f s" % dt

            expected = _expected_tools()
            if expected is None:
                print("MANIFEST=absent (skipping tool-name check)")
            else:
                actual = sorted(t.name for t in tools.tools)
                missing = sorted(set(expected) - set(actual))
                added = sorted(set(actual) - set(expected))
                assert not missing, (
                    "tools missing from this build: %s -- a domain failed to "
                    "register; check the server log before publishing" % missing)
                assert not added, (
                    "tools not in tests/unit/tool_manifest.txt: %s -- update "
                    "the manifest in the same commit" % added)
                print("MANIFEST=ok (%d tools)" % len(expected))

            print("GATE_OK")


if __name__ == "__main__":
    asyncio.run(main())
