# -*- coding: utf-8 -*-
"""Tagging tools — tag elements with annotation symbols"""

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


def register_tag_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register tag tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def tag_elements(
        element_ids: list[int],
        view_name: str = None,
        tag_type_name: str = None,
        add_leader: bool = False,
        orientation: str = "horizontal",
        offset: dict = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Tag elements with annotation symbols in a view.

        Places tags on the specified elements. Tags display element properties
        like type name, mark, or room name/number. Works with walls, doors,
        windows, rooms, and other taggable categories.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. element_ids, view_name and tag_type_name are looked up in that
        document.

        Args:
            element_ids: List of element IDs to tag
            view_name: View to place tags in (defaults to active view)
            tag_type_name: Tag family type name (auto-detects appropriate tag if omitted)
            add_leader: Show leader line from tag to element (default: false)
            orientation: Tag orientation — "horizontal" or "vertical" (default: "horizontal")
            offset: Tag offset from element center {"x": float, "y": float} in mm
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {
            "element_ids": element_ids,
            "add_leader": add_leader,
            "orientation": orientation,
        }
        if view_name is not None:
            data["view_name"] = view_name
        if tag_type_name is not None:
            data["tag_type_name"] = tag_type_name
        if offset is not None:
            data["offset"] = offset
        if document is not None:
            data["document"] = document
        response = await revit_post("/tag_elements/", data, ctx, **_target_options(target))
        return format_response(response)
