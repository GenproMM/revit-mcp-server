# -*- coding: utf-8 -*-
"""Worksharing tools — opening models with detach and workset configuration"""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_worksharing_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register worksharing / model-open tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def list_model_worksets(
        file_path: str,
        close_worksets_matching: list[str] = None,
        ctx: Context = None,
    ) -> str:
        """Inspect a Revit model's worksets without opening it.

        Reads the .rvt header and its workset table straight from disk, so it is
        cheap and safe to call on a heavy federated model before deciding how to
        open it. Use it to confirm a model is workshared and to preview which
        worksets open_model would close.

        Returns the file's workshared/central flags, the Revit version it was
        saved in, every user workset with its id and name, and a would_close
        list. A model that is not workshared returns an empty workset list with
        an explanatory message rather than an error.

        Limitations: reports user worksets only, not families or view worksets.
        A model already open in Revit is still read from disk, so unsaved
        workset changes are not reflected.

        Args:
            file_path: Full path to the .rvt file, e.g. "C:\\Models\\Tower.rvt"
            close_worksets_matching: Substrings marking link worksets, matched
                case-insensitively. Defaults to ["#_RVT_LINK"]. Pass [] to
                preview with nothing closed.
            ctx: MCP context for logging
        """
        data = {"file_path": file_path}
        if close_worksets_matching is not None:
            data["close_worksets_matching"] = close_worksets_matching
        response = await revit_post("/model_worksets/", data, ctx)
        return format_response(response)

    @mcp.tool()
    async def open_model(
        file_path: str,
        detach: str = "preserve",
        close_worksets_matching: list[str] = None,
        activate: bool = True,
        audit: bool = False,
        ctx: Context = None,
    ) -> str:
        """Open a Revit model from disk, detaching from central and choosing worksets.

        This is the way to get a model into Revit for the other tools to work on.
        By default it detaches from central while preserving worksets — the Revit
        dialog's "Detach and preserve worksets" — and closes the worksets that
        hold RVT links.

        Closing link worksets matters on federated models: left open, Revit loads
        every attached RVT as its own document, which on a large model means
        roughly ten extra discipline models and ten times the memory.

        A model that is not workshared is opened plainly, with neither detach nor
        workset configuration, because Revit rejects both on such a file; the
        response says so via is_workshared.

        Returns the opened document's title, the detach mode actually applied,
        whether it became the active document, and the worksets opened vs closed.

        Limitations: a closed workset cannot be opened later without reopening
        the model, so choose close_worksets_matching deliberately. Opening is
        synchronous and a large model can exceed the 30s bridge timeout — the
        open usually completes in Revit even when the call times out, so check
        get_revit_status rather than retrying blindly. Detaching leaves an unsaved
        document; use save_document with a file_path to persist it.

        Args:
            file_path: Full path to the .rvt file, e.g. "C:\\Models\\Tower.rvt"
            detach: "preserve" keeps worksets (default), "discard" drops them,
                "none" opens the central file itself without detaching
            close_worksets_matching: Substrings marking worksets to leave closed,
                matched case-insensitively. Defaults to ["#_RVT_LINK"]. Pass []
                to open every workset.
            activate: Make the opened model the active document, which the other
                tools operate on (defaults to True)
            audit: Run Revit's audit while opening — slow, for suspect files
            ctx: MCP context for logging
        """
        data = {
            "file_path": file_path,
            "detach": detach,
            "activate": activate,
            "audit": audit,
        }
        if close_worksets_matching is not None:
            data["close_worksets_matching"] = close_worksets_matching
        response = await revit_post("/open_model/", data, ctx)
        return format_response(response)
