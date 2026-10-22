# -*- coding: utf-8 -*-
"""Structure tools — grids and structural framing"""

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


def register_structure_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register structure tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def create_grid(
        grids: list[dict],
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create grid lines for the structural layout of a building.

        Grids define the column grid system. Each grid is a line from start to end
        point (in millimeters). Names auto-assign (A, B, C... or 1, 2, 3...) if
        not provided. Supports batch creation.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            grids: List of grid definitions, each with:
                - start_point (dict): {"x": float, "y": float, "z": float} in mm (required)
                - end_point (dict): {"x": float, "y": float, "z": float} in mm (required)
                - name (str): Grid line name (optional, auto-assigned)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"grids": grids}
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_grid/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def create_structural_framing(
        elements: list[dict],
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create structural beams and framing elements in Revit.

        Beams are placed along a line between two points, positioned at the
        given level's elevation (like walls/floors). The point `z` is an offset
        from that level — so pass z=0 to put the beam on the level, or a small
        z for a drop/raise relative to it. All dimensions in millimeters.
        Supports batch creation.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. level_name and type_name are looked up in that document.

        Args:
            elements: List of beam definitions, each with:
                - start_point (dict): {"x": float, "y": float, "z": float} in mm (required; z is offset from level)
                - end_point (dict): {"x": float, "y": float, "z": float} in mm (required; z is offset from level)
                - type_name (str): Beam family type name (optional)
                - level_name (str): Target level name — sets the beam elevation (optional)
                - name (str): Description for reference (optional)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"elements": elements}
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_framing/", data, ctx, **_target_options(target))
        return format_response(response)
