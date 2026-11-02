# -*- coding: utf-8 -*-
"""View-related tools for capturing and listing Revit views"""

from mcp.server.fastmcp import Context
from .utils import read_options, format_response


def _target_options(target):
    """Transport keyword for the per-call process selector; absent when not given."""
    return {} if target is None else {"target": target}


def register_view_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register view-related tools"""

    @mcp.tool()
    async def get_revit_view(view_name: str, target: str = None, document: str = None, ctx: Context = None) -> str:
        """Export one Revit view as a PNG image.

        Use list_revit_views first to get an exact, exportable view name.

        The name must match exactly, including spaces and case; names with
        spaces are URL-encoded by the route, so "L2 Floor Plan" works as-is.
        Schedules, legends and sheets are not exportable this way — an
        unexportable or unknown name comes back as an error string, not an image.

        Returns an image on success. This tool deliberately bypasses the usual
        response formatting, so the result is either image data or an error
        string.

        This is a read of document (an opaque selector from list_documents),
        active or inactive. Without document, reads the active document. Never
        activates a document. Invalid or closed selectors never fall back.
        UI selection/current-view reads and visible_in_view require the active document.

        Args:
            view_name: Exact view name as reported by list_revit_views,
                e.g. "L2 Floor Plan"
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional opaque document selector from list_documents; omitted means active
            ctx: MCP context for logging
        """
        if document is not None and (not isinstance(document, str) or not document.strip()):
            return format_response({"error": "document must be a non-blank selector from list_documents. Nothing was sent to Revit."})
        response = await revit_image(f"/get_view/{view_name}", ctx, **read_options(target, document))
        # An Image has no text channel for provenance; an error string goes through
        # the shared renderer so a received 4xx names the process that answered.
        return format_response(response) if isinstance(response, str) else str(response)

    @mcp.tool()
    async def list_revit_views(target: str = None, document: str = None, ctx: Context = None) -> str:
        """List the views in the current Revit model that can be exported.

        This is the companion to get_revit_view: it returns the exact names
        that tool needs. Views that cannot be exported as an image (schedules,
        legends, sheets) are excluded, so a view missing here cannot be
        captured — it is not a lookup failure.

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
        response = await revit_get("/list_views/", ctx, **read_options(target, document))
        return format_response(response)

    @mcp.tool()
    async def get_current_view_info(target: str = None, document: str = None, ctx: Context = None) -> str:
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

        This is a read of document (an opaque selector from list_documents),
        which must be active: UI selection/current-view state is not model-wide
        data. An inactive selector is refused with HTTP 412; nothing is activated.
        Without document, reads the active document. Invalid/closed tokens never fall back.

        Args:
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional opaque document selector from list_documents; omitted means active
            ctx: MCP context for logging
        """
        if document is not None and (not isinstance(document, str) or not document.strip()):
            return format_response({"error": "document must be a non-blank selector from list_documents. Nothing was sent to Revit."})
        if ctx:
            await ctx.info("Getting current view information...")
        response = await revit_get("/current_view_info/", ctx, **read_options(target, document))
        return format_response(response)


    @mcp.tool()
    async def get_current_view_elements(target: str = None, document: str = None, ctx: Context = None) -> str:
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

        This is a read of document (an opaque selector from list_documents),
        which must be active: UI selection/current-view state is not model-wide
        data. An inactive selector is refused with HTTP 412; nothing is activated.
        Without document, reads the active document. Invalid/closed tokens never fall back.

        Args:
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional opaque document selector from list_documents; omitted means active
            ctx: MCP context for logging
        """
        if document is not None and (not isinstance(document, str) or not document.strip()):
            return format_response({"error": "document must be a non-blank selector from list_documents. Nothing was sent to Revit."})
        if ctx:
            await ctx.info("Getting elements in current view...")
        response = await revit_get("/current_view_elements/", ctx, **read_options(target, document))
        return format_response(response)
