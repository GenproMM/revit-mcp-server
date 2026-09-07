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


asyncio.run(main())
