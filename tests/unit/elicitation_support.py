# -*- coding: utf-8 -*-
"""Phase 7 test helper: an in-memory MCP client whose elicitation callback answers like the unchanged Hermes handler (accept with empty content). Not a test module; needs no Revit.

``hermes_callback(script)`` builds the client-side elicitation callback: every
request it receives is recorded in ``.messages`` and answered with the next
scripted step. ``connected(server, callback)`` runs a real MCP client session
against a FastMCP server over in-memory streams, so a tool can call
``ctx.session.elicit_form`` exactly as it will in production.
"""

from contextlib import asynccontextmanager

import anyio
import mcp.types as types
from mcp.shared.memory import create_connected_server_and_client_session

STEPS = ("accept", "decline", "cancel", "raise", "hang")


class HermesCallback(object):
    """Elicitation callback shaped like the Hermes handler: consent is the action only."""

    def __init__(self, script):
        for step in script:
            if step not in STEPS:
                raise ValueError("unknown elicitation step {!r}; use one of {}".format(step, STEPS))
        self._script = list(script)
        self.messages = []

    async def __call__(self, context, params):
        self.messages.append(params.message)
        step = self._script.pop(0) if self._script else "decline"
        if step == "accept":
            return types.ElicitResult(action="accept", content={})
        if step == "decline":
            return types.ElicitResult(action="decline")
        if step == "cancel":
            return types.ElicitResult(action="cancel")
        if step == "raise":
            raise RuntimeError("boom")
        await anyio.Event().wait()  # "hang": never answers, for timeout tests
        return types.ElicitResult(action="cancel")  # unreachable


def hermes_callback(script):
    """A callback that answers the scripted steps in order, then declines."""
    return HermesCallback(script)


@asynccontextmanager
async def connected(server, callback=None):
    """An initialized ClientSession against ``server``; no callback means no elicitation capability."""
    kwargs = {}
    if callback is not None:
        kwargs["elicitation_callback"] = callback
    async with create_connected_server_and_client_session(server._mcp_server, **kwargs) as session:
        yield session
