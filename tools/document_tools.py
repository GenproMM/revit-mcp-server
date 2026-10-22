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


def _identity_line(payload):
    identity = payload.get("process_identity")
    if isinstance(identity, dict):
        return "Answering Revit process: PID {}; Revit {}; port {}; session {}".format(
            identity.get("pid"), identity.get("revit_version"),
            identity.get("actual_port"), identity.get("session_token"))
    if payload.get("identity_error"):
        return "Answering process identity unavailable: {}".format(payload["identity_error"])
    return None


def _describe(entry):
    return "{} (document {}; path: {})".format(
        entry.get("title", ""), entry.get("document", ""), entry.get("path") or "(never saved)")


def _render_activation(payload):
    """Readable text for a received /activate_document/ success, naming the re-read active document."""
    if payload.get("activation") == "activated":
        lines = ["Activated: {}".format(_describe(payload.get("document") or {}))]
    else:
        lines = ["Already the active document, no activation call was made: {}".format(
            _describe(payload.get("document") or {}))]
    observed = payload.get("observed_active_document")
    if isinstance(observed, dict):
        lines.append("Active document now (re-read from Revit): {}".format(_describe(observed)))
    identity_line = _identity_line(payload)
    if identity_line:
        lines.append(identity_line)
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
    async def activate_document(document: str, target: str = None, ctx: Context = None) -> str:
        """Make one already-open Revit document the active one, as an explicit action.

        This is the only way to switch the document shown in the Revit window.
        Reads and mutations never activate a document implicitly: a call that
        names a document that is open but not active is refused (HTTP 412), and
        you then use this tool and retry. Get the "document" value from
        list_documents.

        Supported: a document that is already open, has been saved, is not
        workshared and whose file exists on disk. It is activated using its own
        file path, and nothing is saved, reopened or opened from another path.
        If it is already the active document the call succeeds without doing
        anything.

        Everything else is refused before Revit is touched, with one of these
        reasons: unsaved (never saved, no path), detached (a detached copy),
        no-usable-file-path (the path is not an existing file, e.g. a cloud
        path), linked-unsupported, family-unmeasured, cloud-unmeasured,
        workshared-unmeasured (any workshared model, even a saved one) and
        eligibility-unreadable (a needed property could not be read). The
        "unmeasured" classes have not been verified safe, so they are refused,
        not tried. A selector that is closed, stale, unknown, ambiguous or
        missing is also refused; no other document is ever activated instead.

        Returns the activated document and, from a fresh read of Revit, the
        document that is active now, plus a final line naming the Revit process
        that answered. Success is reported only when the re-read active
        document is the requested one; otherwise the text says it was not
        activated and names the document that is active. A refusal or failure
        gives the HTTP status, the reason and the same identity details.

        Args:
            document: The opaque "document" selector from list_documents (required)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            ctx: MCP context for logging
        """
        if not isinstance(document, str) or not document.strip():
            return format_response({
                "error": "document is required: pass the 'document' value of one document "
                         "from list_documents. Activation never chooses a default."})
        if ctx:
            await ctx.info("Activating document {}".format(document))
        options = {}
        if target is not None:
            options["target"] = target
        response = await revit_post("/activate_document/", {"document": document}, ctx, **options)
        if (isinstance(response, dict) and not response.get("error")
                and response.get("activation") in ("activated", "already-active")):
            return format_response(_render_activation(response))
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
