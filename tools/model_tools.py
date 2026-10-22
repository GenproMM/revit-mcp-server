# -*- coding: utf-8 -*-
"""Model structure and hierarchy tools"""

from mcp.server.fastmcp import Context
from .utils import format_response


def _target_options(target):
    """Transport keyword for the per-call process selector; absent when not given."""
    return {} if target is None else {"target": target}


def register_model_tools(mcp, revit_get, revit_post=None, revit_image=None):
    """Register model structure tools"""
    _ = revit_post, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def list_levels(target: str = None, ctx: Context = None) -> str:
        """List all levels in the current Revit model.

        Returns each level's name, id and elevation. Level names are what
        place_family, create_level and the structural tools expect in their
        level_name arguments, so this is usually the first call before placing
        anything level-hosted.

        Each level reports both `elevation_mm` and `elevation_feet`; the list is
        sorted by elevation, lowest first. A level whose data cannot be read is
        skipped, so the list can be shorter than the model's level count.

        This is a read. It lists the levels of the active document of the
        selected Revit process; it has no document argument and never reports
        the levels of an inactive document as if they were these. To read the
        levels of a named document, active or inactive, use read_document_levels
        (read_document_summary does the same for a document summary).

        Args:
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            ctx: MCP context for logging
        """
        response = await revit_get("/list_levels/", ctx, **_target_options(target))
        return format_response(response)
