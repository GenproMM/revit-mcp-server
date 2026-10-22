# -*- coding: utf-8 -*-
"""View management tools — create views and set active view"""

from mcp.server.fastmcp import Context
from .utils import format_response


def _target_options(target):
    """Transport keyword for the per-call process selector; absent when not given."""
    return {} if target is None else {"target": target}


def _blank_document(document):
    """True for a document selector that was given but is not a usable string.

    A blank value must refuse, never decay into the one-open-document default.
    """
    return document is not None and (not isinstance(document, str) or not document.strip())


_BLANK_DOCUMENT_REFUSAL = {
    "error": "document must be a non-blank selector: pass the 'document' value of one document "
             "from list_documents, or omit it. Nothing was sent to Revit."
}


def register_view_management_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register view management tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def create_view(
        view_type: str,
        name: str,
        level_name: str = None,
        section_box: dict = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a new view in the Revit model.

        Supports floor plans, ceiling plans, sections, elevations, and 3D views.
        Floor plans and ceiling plans require a level name. Sections require a
        section box definition with origin, direction, and dimensions.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. level_name is looked up in that document.

        Args:
            view_type: Type of view — "floor_plan", "ceiling_plan", "section",
                "elevation", or "3d"
            name: Display name for the new view
            level_name: Required for floor_plan and ceiling_plan — the level to show
            section_box: Required for section — defines the cut plane:
                - origin (dict): {"x", "y", "z"} center point in mm
                - direction (dict): {"x", "y", "z"} view direction vector
                - up (dict): {"x", "y", "z"} up direction vector
                - width (float): Section width in mm
                - height (float): Section height in mm
                - depth (float): Section depth in mm
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"view_type": view_type, "name": name}
        if level_name is not None:
            data["level_name"] = level_name
        if section_box is not None:
            data["section_box"] = section_box
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_view/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def set_active_view(
        view_name: str,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Switch the active view in Revit to the specified view.

        Changes which view is displayed in the Revit UI. Use list_revit_views
        first to find available view names.

        This changes the view shown for one document; it never activates a
        document. Document choice: pass document (a value from list_documents)
        to name the document whose view changes. Without it the call uses the
        only open document; if several documents are open it is refused and the
        candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412)
        and nothing is activated: use activate_document, then retry with the
        same selector. view_name is looked up in that document.

        Args:
            view_name: Name of the view to activate
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"view_name": view_name}
        if document is not None:
            data["document"] = document
        response = await revit_post("/set_active_view/", data, ctx, **_target_options(target))
        return format_response(response)
