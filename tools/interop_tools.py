# -*- coding: utf-8 -*-
"""Interop tools — IFC export and external file linking"""

from mcp.server.fastmcp import Context
from .utils import describe_broken_path, format_response


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


def register_interop_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register interop tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def export_ifc(
        file_path: str,
        ifc_version: str = "IFC2x3",
        export_base_quantities: bool = True,
        view_name: str = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Export the Revit model to IFC format.

        Creates an IFC file at the specified path. Optionally filter by view
        to export only visible elements. Supports IFC2x3 and IFC4.

        This writes a file from a document, so it follows the document rule of
        the tools that change a model. Document choice: pass document (a value
        from list_documents) to name the document to export. Without it the call
        uses the only open document; if several documents are open it is refused
        and the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. view_name is looked up in that document.

        Args:
            file_path: Output file path (must end in .ifc)
            ifc_version: "IFC2x3" (default) or "IFC4"
            export_base_quantities: Include IFC base quantities (default: true)
            view_name: Export only elements visible in this view (optional)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        problem = describe_broken_path(file_path)
        if problem:
            return format_response({"error": problem})
        data = {
            "file_path": file_path,
            "ifc_version": ifc_version,
            "export_base_quantities": export_base_quantities,
        }
        if view_name is not None:
            data["view_name"] = view_name
        if document is not None:
            data["document"] = document
        response = await revit_post("/export_ifc/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def link_file(
        file_path: str,
        mode: str = "link",
        position: dict = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Link or import an external file into the Revit model.

        Supports DWG, DXF, DGN (CAD files) and RVT (Revit links).
        Linked files maintain a live connection; imported files are embedded.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document that receives the link or import.
        Without it the call uses the only open document; if several documents
        are open it is refused and the candidates are listed, and the document
        active in the UI is never assumed. A document that is open but not active
        is refused (HTTP 412) and nothing is activated: use activate_document,
        then retry with the same selector.

        Args:
            file_path: Path to the file (DWG, DXF, DGN, or RVT)
            mode: "link" (default, maintains connection) or "import" (embeds copy)
            position: Optional placement offset {"x", "y", "z"} in mm
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        problem = describe_broken_path(file_path)
        if problem:
            return format_response({"error": problem})
        data = {"file_path": file_path, "mode": mode}
        if position is not None:
            data["position"] = position
        if document is not None:
            data["document"] = document
        response = await revit_post("/link_file/", data, ctx, **_target_options(target))
        return format_response(response)
