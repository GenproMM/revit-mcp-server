# -*- coding: utf-8 -*-
"""Document tools — saving and persistence"""

from mcp.server.fastmcp import Context
from .utils import describe_broken_path, format_response


def _render_listing(payload):
    """Readable text for a received /documents/ answer, with the answering process."""
    documents = payload.get("documents") or []
    lines = []
    if not documents:
        lines.append("No documents are open in this Revit process.")
    else:
        lines.append("Open documents in this Revit process: {}".format(len(documents)))
        for index, entry in enumerate(documents, 1):
            flag = "  [ACTIVE]" if entry.get("active") else ""
            lines.append("{}. {}{}".format(index, entry.get("title", ""), flag))
            lines.append("   path: {}".format(entry.get("path") or "(never saved)"))
            lines.append("   document: {}".format(entry.get("document", "")))
    identity = payload.get("process_identity")
    if isinstance(identity, dict):
        lines.append("Answering Revit process: PID {}; Revit {}; port {}; session {}".format(
            identity.get("pid"), identity.get("revit_version"),
            identity.get("actual_port"), identity.get("session_token")))
    elif payload.get("identity_error"):
        lines.append("Answering process identity unavailable: {}".format(payload["identity_error"]))
    return "\n".join(lines)


def register_document_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register document persistence tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def list_documents(target: str = None, ctx: Context = None) -> str:
        """List the documents open in one Revit process, each with its own selector.

        Use this to see what is open before addressing a document: two unsaved
        projects can both be titled "Project1", and a title or path is never a
        selector. Each entry gives title, path, whether it is the document
        active in the Revit UI, and a "document" value. That value is an opaque
        selector minted by the extension; it is the only way to name one
        document. A document that is closed has its selector retired for good,
        and reopening a file with the same title or path gives a new selector.
        Link documents are not listed. This call only reads and changes nothing;
        it does not activate a document.

        Returns the documents with a final line naming the Revit process that
        actually answered (PID, version, port, session). A process with no open
        document answers with an empty list. If two documents cannot be told
        apart safely the answer is an error naming why, never a shortened list.
        If the request could not be sent or timed out, the text says so and no
        process is named.

        Which tools accept a document selector is stated in each tool's own
        docstring; most do not yet, and an omitted selector there keeps its
        current behaviour.

        Args:
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            ctx: MCP context for logging
        """
        options = {}
        if target is not None:
            options["target"] = target
        response = await revit_get("/documents/", ctx, **options)
        if (isinstance(response, dict) and not response.get("error")
                and isinstance(response.get("documents"), list)):
            return format_response(_render_listing(response))
        return format_response(response)

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
