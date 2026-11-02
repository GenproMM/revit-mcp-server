# -*- coding: utf-8 -*-
"""Model structure and hierarchy tools"""

from mcp.server.fastmcp import Context
from .utils import read_options, format_response


def _target_options(target):
    """Transport keyword for the per-call process selector; absent when not given."""
    return {} if target is None else {"target": target}


def register_model_tools(mcp, revit_get, revit_post=None, revit_image=None):
    """Register model structure tools"""
    _ = revit_post, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def list_levels(target: str = None, document: str = None, ctx: Context = None) -> str:
        """List all levels in the current Revit model.

        Returns each level's name, id and elevation. Level names are what
        place_family, create_level and the structural tools expect in their
        level_name arguments, so this is usually the first call before placing
        anything level-hosted.

        Each level reports both `elevation_mm` and `elevation_feet`; the list is
        sorted by elevation, lowest first. A level whose data cannot be read is
        skipped, so the list can be shorter than the model's level count.

        This is a read of document (an opaque selector from list_documents),
        active or inactive. Without document, reads the active document. Never
        activates a document. Invalid or closed selectors never fall back.
        UI selection/current-view reads and visible_in_view require the active document.

        Args:
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional opaque document selector from list_documents; omitted means active
            ctx: MCP context for logging
        """
        if document is not None and (not isinstance(document, str) or not document.strip()):
            return format_response({"error": "document must be a non-blank selector from list_documents. Nothing was sent to Revit."})
        response = await revit_get("/list_levels/", ctx, **read_options(target, document))
        return format_response(response)
