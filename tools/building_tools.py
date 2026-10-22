# -*- coding: utf-8 -*-
"""Building creation tools — walls, floors, roofs, ceilings, and levels"""

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


def register_building_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register building creation tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def create_line_based_element(
        elements: list[dict],
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create walls, beams, and other line-based building elements in Revit.

        Each element needs start and end points (in millimeters), element type
        (wall/beam), and optionally a level name, height, and family type name.
        Supports batch creation — pass multiple elements in one call.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            elements: List of element definitions, each with:
                - element_type (str): "wall" or "beam" (required)
                - start_point (dict): {"x": float, "y": float, "z": float} in mm (required)
                - end_point (dict): {"x": float, "y": float, "z": float} in mm (required)
                - type_name (str): Family type name, e.g. "Generic - 200mm" (optional)
                - level_name (str): Target level name (optional, defaults to first level)
                - height (float): Element height in mm (optional, defaults to 3000)
                - offset (float): Offset from base level in mm (optional, defaults to 0)
                - structural (bool): Mark as structural (optional, defaults to false)
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
        response = await revit_post("/create_line/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def create_surface_based_element(
        elements: list[dict],
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create floors, roofs, ceilings, and other surface-based building elements.

        Each element needs a closed boundary polygon (list of line segments) where
        the last point connects back to the first. All dimensions in millimeters.
        Supports batch creation.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            elements: List of element definitions, each with:
                - element_type (str): "floor", "roof", or "ceiling" (required)
                - boundary (list[dict]): Array of {"p0": Point, "p1": Point} segments
                  forming a closed polygon (required, minimum 3 segments)
                - type_name (str): Family type name (optional)
                - level_name (str): Target level name (optional)
                - offset (float): Offset from level in mm (optional, defaults to 0)
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
        response = await revit_post("/create_surface/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def create_level(
        levels: list[dict],
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create building levels (floor elevations) in Revit.

        Levels define the floor-to-floor heights of a building and must be
        created before placing walls, floors, or other level-dependent elements.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            levels: List of level definitions, each with:
                - elevation (float): Elevation in mm from project origin (required)
                - name (str): Level name, e.g. "Ground Floor" (optional, auto-assigned)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"levels": levels}
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_level/", data, ctx, **_target_options(target))
        return format_response(response)
