# -*- coding: utf-8 -*-
"""Editing tools — delete, modify, and select elements"""

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


def register_editing_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register editing tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def delete_elements(
        element_ids: list[int],
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Delete one or more elements from the Revit model.

        Removes elements by their IDs. If a deleted element hosts other elements
        (e.g., a wall with doors), the hosted elements are also deleted (cascade).
        All deletions happen in a single transaction — if any fails, none are deleted.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. Element ids belong to one document, so name the document the
        ids were read from.

        Args:
            element_ids: List of Revit element IDs to delete
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"element_ids": element_ids}
        if document is not None:
            data["document"] = document
        response = await revit_post("/delete_elements/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def modify_element(
        element_id: int,
        parameters: dict,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Modify parameter values on a Revit element.

        Changes one or more instance parameters on the specified element.
        Returns old and new values for confirmation.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. Element ids belong to one document, so name the document the
        id was read from.

        Args:
            element_id: Revit element ID to modify
            parameters: Dictionary of parameter name to new value pairs
                e.g., {"Mark": "EW-01", "Comments": "Updated via MCP"}
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"element_id": element_id, "parameters": parameters}
        if document is not None:
            data["document"] = document
        response = await revit_post("/modify_element/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def get_selected_elements(
        target: str = None,
        ctx: Context = None,
    ) -> str:
        """Get details of elements currently selected in the Revit UI.

        Returns IDs, categories, types, and key parameters of all elements
        the user has selected in Revit. Returns an empty list if nothing
        is selected (not an error).

        This is a read. The selection belongs to the active document of the
        selected Revit process; it has no document argument, because reading an
        inactive document is supported only by read_document_summary and
        read_document_levels.

        Args:
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            ctx: MCP context for logging
        """
        response = await revit_get("/selected_elements/", ctx, **_target_options(target))
        return format_response(response)
