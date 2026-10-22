# -*- coding: utf-8 -*-
"""Documentation tools — sheets, schedules, and document export"""

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


def register_documentation_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register documentation tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def create_sheet(
        sheet_number: str = None,
        sheet_name: str = "Unnamed Sheet",
        title_block_name: str = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a drawing sheet in Revit for construction documentation.

        Sheets are the printable output of a Revit project. Each sheet has a
        title block, sheet number, and name. Views can be placed on sheets
        after creation.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            sheet_number: Sheet number, e.g. "A101" (optional, auto-assigned)
            sheet_name: Sheet title, e.g. "Ground Floor Plan" (defaults to "Unnamed Sheet")
            title_block_name: Title block family name (optional, uses first available)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {
            "sheet_number": sheet_number,
            "sheet_name": sheet_name,
            "title_block_name": title_block_name,
        }
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_sheet/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def create_schedule(
        category: str,
        fields: list[str] = None,
        schedule_name: str = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a schedule (quantity takeoff view) for a specific element category.

        Schedules tabulate element data — e.g., a wall schedule showing all walls
        with their types, lengths, and areas. The schedule appears as a new view
        in the Revit project browser.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            category: BuiltInCategory name, e.g. "OST_Walls", "OST_Rooms" (required)
            fields: Parameter names to include as columns (optional, uses default set)
                e.g., ["Family and Type", "Length", "Area", "Mark"]
            schedule_name: Name for the schedule view (optional, auto-generated)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {
            "category": category,
            "fields": fields,
            "schedule_name": schedule_name,
        }
        if document is not None:
            data["document"] = document
        response = await revit_post("/create_schedule/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def export_document(
        view_name: str = None,
        format: str = "pdf",
        resolution: int = 300,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Export a Revit view or sheet to PDF or image format.

        Exports the specified view (or the active view if none specified) to a
        file on disk. Supported formats: PDF, PNG, JPG, DWG.

        This acts on one document and writes a file to disk, so it follows the
        same document rule as a model change. Document choice: pass document (a
        value from list_documents) to name the document to export from. Without
        it the call uses the only open document; if several documents are open it
        is refused and the candidates are listed, and the document active in the
        UI is never assumed. A document that is open but not active is refused
        (HTTP 412) and nothing is activated: use activate_document, then retry
        with the same selector.

        Args:
            view_name: Name of the view or sheet to export (optional, uses active view)
            format: Output format — "pdf", "png", "jpg", or "dwg" (defaults to "pdf")
            resolution: DPI for image formats (defaults to 300, ignored for PDF/DWG)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {
            "view_name": view_name,
            "format": format,
            "resolution": resolution,
        }
        if document is not None:
            data["document"] = document
        response = await revit_post("/export_document/", data, ctx, **_target_options(target))
        return format_response(response)
