# -*- coding: utf-8 -*-
"""Annotation tools — dimensions and wall tags"""

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


def register_annotation_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register annotation tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def create_dimensions(
        element_ids: list[int],
        dimension_type: str = "linear",
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create dimension annotations for elements in the current view.

        Automatically dimensions the specified elements. Works in plan, section,
        and elevation views. The dimension line is placed at an offset from the
        elements for readability.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            element_ids: List of element IDs to dimension
            dimension_type: Type of dimension — "linear", "aligned", or "angular"
                (defaults to "linear")
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"element_ids": element_ids, "dimension_type": dimension_type}
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_dimensions/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def tag_walls(
        use_leader: bool = False,
        tag_type_name: str = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Tag all untagged walls in the current Revit view.

        Places wall tags on every wall visible in the active view that doesn't
        already have a tag. Tags are centered on each wall segment.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            use_leader: Whether to show leader lines (defaults to False)
            tag_type_name: Specific wall tag family type name (optional, uses first available)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"use_leader": use_leader, "tag_type_name": tag_type_name}
        if document is not None:
            data["document"] = document
        response = await revit_post("/tag_walls/", data, ctx, **_target_options(target))
        return format_response(response)
