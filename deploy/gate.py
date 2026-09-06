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
            print("GATE_OK")


asyncio.run(main())
