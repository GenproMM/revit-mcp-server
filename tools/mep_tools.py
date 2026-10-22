# -*- coding: utf-8 -*-
"""MEP tools — ducts, pipes, and mechanical/plumbing systems"""

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


def register_mep_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register MEP tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def create_duct(
        start_point: dict,
        end_point: dict,
        system_type: str = None,
        duct_type: str = None,
        level_name: str = None,
        diameter: float = None,
        width: float = None,
        height: float = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a duct in the Revit model between two points.

        Requires a project with mechanical families loaded (MEP template).
        Specify diameter for round ducts, or width+height for rectangular.
        All dimensions in millimeters.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. Type, system and level names are looked up in that document.

        Args:
            start_point: Start point {"x", "y", "z"} in mm
            end_point: End point {"x", "y", "z"} in mm
            system_type: System type name (e.g., "Supply Air"). Auto-detects if omitted
            duct_type: Duct type name (e.g., "Round Duct"). Auto-detects if omitted
            level_name: Level name. Defaults to nearest level
            diameter: Round duct diameter in mm
            width: Rectangular duct width in mm
            height: Rectangular duct height in mm
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"start_point": start_point, "end_point": end_point}
        if system_type is not None:
            data["system_type"] = system_type
        if duct_type is not None:
            data["duct_type"] = duct_type
        if level_name is not None:
            data["level_name"] = level_name
        if diameter is not None:
            data["diameter"] = diameter
        if width is not None:
            data["width"] = width
        if height is not None:
            data["height"] = height
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_duct/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def create_pipe(
        start_point: dict,
        end_point: dict,
        system_type: str = None,
        pipe_type: str = None,
        level_name: str = None,
        diameter: float = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a pipe in the Revit model between two points.

        Requires a project with plumbing families loaded (MEP template).
        All dimensions in millimeters.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. Type, system and level names are looked up in that document.

        Args:
            start_point: Start point {"x", "y", "z"} in mm
            end_point: End point {"x", "y", "z"} in mm
            system_type: System type name (e.g., "Domestic Hot Water"). Auto-detects if omitted
            pipe_type: Pipe type name (e.g., "Copper"). Auto-detects if omitted
            level_name: Level name. Defaults to nearest level
            diameter: Pipe diameter in mm
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"start_point": start_point, "end_point": end_point}
        if system_type is not None:
            data["system_type"] = system_type
        if pipe_type is not None:
            data["pipe_type"] = pipe_type
        if level_name is not None:
            data["level_name"] = level_name
        if diameter is not None:
            data["diameter"] = diameter
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_pipe/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def create_mep_system(
        system_type: str,
        system_name: str,
        element_ids: list[int] = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a mechanical or piping system and optionally add elements to it.

        Groups ducts or pipes into a named system for organization and analysis.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. Element ids belong to one document, so name the document the
        ids were read from.

        Args:
            system_type: "mechanical" or "piping"
            system_name: Display name for the system (e.g., "Level 1 Supply Air")
            element_ids: Optional list of duct/pipe element IDs to add to the system
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"system_type": system_type, "system_name": system_name}
        if element_ids is not None:
            data["element_ids"] = element_ids
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_mep_system/", data, ctx, **_target_options(target))
        return format_response(response)
