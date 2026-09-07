# -*- coding: utf-8 -*-
"""Model structure and hierarchy tools"""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_model_tools(mcp, revit_get, revit_post=None, revit_image=None):
    """Register model structure tools"""
    _ = revit_post, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def list_levels(ctx: Context = None) -> str:
        """List all levels in the current Revit model.

        Returns each level's name, id and elevation. Level names are what
        place_family, create_level and the structural tools expect in their
        level_name arguments, so this is usually the first call before placing
        anything level-hosted.

        Each level reports both `elevation_mm` and `elevation_feet`; the list is
        sorted by elevation, lowest first. A level whose data cannot be read is
        skipped, so the list can be shorter than the model's level count.

        Args:
            ctx: MCP context for logging
        """
        response = await revit_get("/list_levels/", ctx)
        return format_response(response)
