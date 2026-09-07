# -*- coding: utf-8 -*-
"""Status and model information tools"""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_status_tools(mcp, revit_get, revit_post=None, revit_image=None):
    """Register status-related tools"""
    _ = revit_post, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def get_revit_status(ctx: Context) -> str:
        """Check whether the Revit bridge is reachable and healthy.

        Call this first when any other tool fails: it distinguishes "Revit is
        not running / the extension did not load" from a fault in one tool.

        Returns the bridge status, the open document's title, and how many
        route domains registered inside Revit. "health" is "degraded" when a
        domain failed to register — in that case "failed_domains" names them,
        and the tools belonging to those domains will not work until Revit is
        restarted.

        Uses a short 10-second timeout, so it fails fast rather than hanging.
        If Revit itself may be closed, use get_revit_process_status instead —
        this call goes through the bridge, which only exists inside Revit.

        Args:
            ctx: MCP context for logging
        """
        response = await revit_get("/status/", ctx, timeout=10.0)
        return format_response(response)

    @mcp.tool()
    async def get_revit_model_info(ctx: Context) -> str:
        """Summarise the currently open Revit model.

        Use this to orient yourself before doing anything else: it reports the
        document title and path, the element and family counts, the levels, and
        the project information fields.

        Scope: the active document only. Linked models are not traversed.

        Args:
            ctx: MCP context for logging
        """
        response = await revit_get("/model_info/", ctx)
        return format_response(response)
