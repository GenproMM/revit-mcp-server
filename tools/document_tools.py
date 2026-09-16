# -*- coding: utf-8 -*-
"""Document tools — saving and persistence"""

from mcp.server.fastmcp import Context
from .utils import describe_broken_path, format_response


def register_document_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register document persistence tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def save_document(
        file_path: str = None,
        overwrite: bool = True,
        as_central: bool = None,
        ctx: Context = None,
    ) -> str:
        """Save the active Revit document to disk so work persists.

        If file_path is given (or the document was started from a template and
        has never been saved), performs Save As to that path. Otherwise saves
        the document in place. Use this to persist a model before closing or
        restarting Revit.

        A workshared document — which is what open_model returns after a
        detach-and-preserve-worksets open — is saved as a new central model by
        default, because Revit refuses any other Save As on it and because
        saving as central is what carries the worksets into the new file.

        Args:
            file_path: Full .rvt path to save to, e.g. "C:\\Models\\ESB.rvt"
                (required the first time a template-based model is saved)
            overwrite: Overwrite an existing file at that path (defaults to True)
            as_central: Save as a central model. Defaults to True for a
                workshared document and False otherwise; only set it explicitly
                to override that, and note Revit rejects False on a detached
                workshared model.
            ctx: MCP context for logging
        """
        # file_path is optional here: only validate one that was given.
        problem = describe_broken_path(file_path) if file_path else None
        if problem:
            return format_response({"error": problem})
        data = {"file_path": file_path, "overwrite": overwrite}
        if as_central is not None:
            data["as_central"] = as_central
        response = await revit_post("/save_document/", data, ctx)
        return format_response(response)
