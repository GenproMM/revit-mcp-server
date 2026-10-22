# -*- coding: utf-8 -*-
"""Status and model information tools"""

from mcp.server.fastmcp import Context
from .utils import PROVENANCE_ATTR, format_response


def _launch_slot_note(configured, response):
    """Qualify the configured launch slot when it is not what answered.

    A response without bridge provenance (a bare transport) keeps the legacy
    line unchanged. Otherwise the slot is only named as the answer when the
    verified process really answered on its port.
    """
    provenance = getattr(response, PROVENANCE_ATTR, None)
    if not isinstance(provenance, dict):
        return ""
    process = provenance.get("process")
    if provenance.get("kind") == "received" and isinstance(process, dict):
        port = str(configured).rpartition(":")[2]
        if str(process.get("actual_port")) == port:
            return ""
        return (" (configured launch slot only; this call was answered by the verified process "
                "on port {}, not by {})".format(process.get("actual_port"), configured))
    return " (configured launch slot only; it does not route calls)"


def register_status_tools(mcp, revit_get, revit_post=None, revit_image=None):
    """Register status-related tools"""
    _ = revit_post, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def get_revit_status(target: str = None, ctx: Context = None) -> str:
        """Check whether the Revit bridge is reachable and healthy.

        Call this first when any other tool fails: it distinguishes "Revit is
        not running / the extension did not load" from a fault in one tool.

        Returns the bridge status, the open document's title, and how many
        route domains registered inside Revit. "health" is "degraded" when a
        domain failed to register — in that case "failed_domains" names them,
        and the tools belonging to those domains will not work until Revit is
        restarted.

        With target, use an opaque revit1 incarnation selector from a verified
        identity capture. Local Windows listener ownership is checked before
        HTTP, then received PID/actual port/session token must match. Collisions,
        unknown inventory and stale selectors refuse; rediscover rather than
        guessing. Discovery automation is not yet exposed by this status slice.
        A verified-process suffix survives formatting, even for no-document 503;
        identity alone does not mean a healthy model. The snapshot-to-connect
        race remains; this is not authentication or a socket reservation.

        Without target, exactly one usable Revit process must exist (several
        are refused with the candidates); the answering process is named by the
        same verified-process line. A last line "MCP target: host:port" shows the
        configured REVIT_HOST/REVIT_PORT launch slot. That slot no longer routes
        calls: when the verified process answered on another port, or nothing
        was sent, the line says so and the verified-process line is the only
        statement of who answered.

        Uses a 10-second HTTP timeout. Selected status first allows up to
        10 seconds for OS inventory, so its total may approach 20 seconds.
        If Revit itself may be closed, use get_revit_process_status instead —
        this call goes through the bridge, which only exists inside Revit.

        Args:
            target: Optional opaque local process incarnation selector from discover_revit_targets
            ctx: MCP context for logging
        """
        # Only the injected transport verifies a responder; format_response renders
        # the verified process after the projection. The requested selector and the
        # configured address are never proof of an answer.
        options = {"timeout": 10.0}
        if target is not None:
            options["target"] = target
        response = await revit_get("/status/", ctx, **options)
        text = format_response(response)
        if target is None:
            configured = getattr(revit_get, "revit_target", None)
            if configured:
                text = "{}\nMCP target: {}{}".format(
                    text, configured, _launch_slot_note(configured, response))
        return text

    @mcp.tool()
    async def get_revit_model_info(target: str = None, ctx: Context = None) -> str:
        """Summarise the currently open Revit model.

        Use this to orient yourself before doing anything else: it reports the
        document title and path, the element and family counts, the levels, and
        the project information fields.

        Scope: the active document only. Linked models are not traversed.

        The reply names the Revit process that answered (a final verified-process
        line). The route does not report a document selector, so the text does
        not attribute the answer to one document: to name and compare documents
        use list_documents, read_document_summary and read_document_levels. If
        the request could not be sent or timed out, the text says so and no
        process is named.

        Args:
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            ctx: MCP context for logging
        """
        options = {} if target is None else {"target": target}
        response = await revit_get("/model_info/", ctx, **options)
        return format_response(response)
