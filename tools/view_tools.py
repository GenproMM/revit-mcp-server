# -*- coding: utf-8 -*-
"""View-related tools for capturing and listing Revit views"""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_view_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register view-related tools"""

    @mcp.tool()
    async def get_revit_view(view_name: str, ctx: Context = None) -> str:
        """Export one Revit view as a PNG image.

        Use list_revit_views first to get an exact, exportable view name.

        The name must match exactly, including spaces and case; names with
        spaces are URL-encoded by the route, so "L2 Floor Plan" works as-is.
        Schedules, legends and sheets are not exportable this way — an
        unexportable or unknown name comes back as an error string, not an image.

        Returns an image on success. This tool deliberately bypasses the usual
        response formatting, so the result is either image data or an error
        string.

        Args:
            view_name: Exact view name as reported by list_revit_views,
                e.g. "L2 Floor Plan"
            ctx: MCP context for logging
        """
        response = await revit_image(f"/get_view/{view_name}", ctx)
        # Note: revit_image already returns a formatted response (Image object or error string)
        return str(response) if not isinstance(response, str) else response

    @mcp.tool()
    async def list_revit_views(ctx: Context = None) -> str:
        """List the views in the current Revit model that can be exported.

        This is the companion to get_revit_view: it returns the exact names
        that tool needs. Views that cannot be exported as an image (schedules,
        legends, sheets) are excluded, so a view missing here cannot be
        captured — it is not a lookup failure.

        Args:
            ctx: MCP context for logging
        """
        response = await revit_get("/list_views/", ctx)
        return format_response(response)

    @mcp.tool()
    async def get_current_view_info(ctx: Context = None) -> str:
        """
        Get detailed information about the currently active view in Revit.

        Returns comprehensive information including:
        - View name, type, and ID
        - Scale and detail level
        - Crop box status
        - View family type
        - View discipline
        - Template status

        Use this to find out what the user is currently looking at before
        acting on "the current view". Scale is the denominator (100 means
        1:100).

        Args:
            ctx: MCP context for logging
        """
        if ctx:
            await ctx.info("Getting current view information...")
        response = await revit_get("/current_view_info/", ctx)
        return format_response(response)

    @mcp.tool()
    async def get_current_view_elements(ctx: Context = None) -> str:
        """
        Get all elements visible in the currently active view in Revit.

        Returns detailed information about each element including:
        - Element ID, name, and type
        - Category and category ID
        - Level information (if applicable)
        - Location information (point or curve)
        - Summary statistics grouped by category

        This is useful for understanding what elements are currently visible
        and analyzing the content of the active view.

        Scope: only what is visible in the active view, so it is affected by
        the view's crop box, filters and visibility settings — it is not a
        model-wide query. Locations are reported in millimetres. Schedules and
        sheets do not support element collection and return an error.

        Args:
            ctx: MCP context for logging
        """
        if ctx:
            await ctx.info("Getting elements in current view...")
        response = await revit_get("/current_view_elements/", ctx)
        return format_response(response)
