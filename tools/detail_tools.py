# -*- coding: utf-8 -*-
"""Detail tools — detail lines for view-specific annotation"""

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


def register_detail_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register detail tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def create_detail_line(
        start_point: dict,
        end_point: dict,
        view_name: str = None,
        line_style: str = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a detail line in a Revit view for annotation purposes.

        Detail lines are view-specific 2D annotation elements. They only
        appear in the view where they are created (unlike model lines).
        Must be created in a plan, section, or detail view.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            start_point: Start point {"x", "y", "z"} in mm
            end_point: End point {"x", "y", "z"} in mm
            view_name: Target view name (defaults to active view)
            line_style: Line style name (e.g., "Medium Lines"). Uses default if omitted
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"start_point": start_point, "end_point": end_point}
        if view_name is not None:
            data["view_name"] = view_name
        if line_style is not None:
            data["line_style"] = line_style
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_detail_line/", data, ctx, **_target_options(target))
        return format_response(response)
