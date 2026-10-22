# -*- coding: utf-8 -*-
"""Room creation tools — rooms and room separation lines"""

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


def register_room_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register room tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def create_room(
        level_name: str,
        location: dict = None,
        name: str = None,
        number: str = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a room in the Revit model at a specified level.

        Rooms must be placed inside enclosed areas (bounded by walls or room
        separation lines). If no location is given, Revit auto-places the room.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. level_name is looked up in that document.

        Args:
            level_name: Target level name (e.g., "Level 1")
            location: Optional placement point {"x": float, "y": float} in mm
            name: Room name (e.g., "Living Room")
            number: Room number (e.g., "101")
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"level_name": level_name}
        if location is not None:
            data["location"] = location
        if name is not None:
            data["name"] = name
        if number is not None:
            data["number"] = number
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_room/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def create_room_separation(
        lines: list[dict],
        level_name: str = None,
        view_name: str = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create room separation lines to define room boundaries.

        Room separation lines act as invisible walls for room calculation.
        Use these when physical walls don't fully enclose a space (e.g.,
        open-plan areas, corridors). All coordinates in millimeters.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. level_name and view_name are looked up in that document.

        Args:
            lines: List of line segments, each with:
                - start_point (dict): {"x": float, "y": float, "z": float} in mm
                - end_point (dict): {"x": float, "y": float, "z": float} in mm
            level_name: Target level name (defaults to active view's level)
            view_name: Plan view name (defaults to active view)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"lines": lines}
        if level_name is not None:
            data["level_name"] = level_name
        if view_name is not None:
            data["view_name"] = view_name
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_room_separation/", data, ctx, **_target_options(target))
        return format_response(response)
