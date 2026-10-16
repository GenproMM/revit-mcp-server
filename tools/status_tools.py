# -*- coding: utf-8 -*-
"""Status and model information tools"""

from mcp.server.fastmcp import Context
from .utils import format_response


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

        Without target, the legacy configured REVIT_HOST/REVIT_PORT path remains.
        Its last line is "MCP target: host:port", even on errors. That address
        identifies a launch slot, not a verified process or model; this legacy
        path does not provide the selected-target ownership guarantees.

        Uses a 10-second HTTP timeout. Selected status first allows up to
        10 seconds for OS inventory, so its total may approach 20 seconds.
        If Revit itself may be closed, use get_revit_process_status instead —
        this call goes through the bridge, which only exists inside Revit.

        Args:
            target: Optional opaque local process incarnation selector; omitted uses legacy configuration
            ctx: MCP context for logging
        """
        # Only the injected transport verifies a selected responder. Requested
        # identity and the legacy configured address are not proof of an answer.
        options = {"timeout": 10.0}
        if target is not None:
            options["target"] = target
        response = await revit_get("/status/", ctx, **options)
        received = None
        if isinstance(response, dict):
            response = dict(response)
            verified = response.pop("_verified_process", None)
            if target is not None:
                received = verified
        text = format_response(response)
        if received:
            text = "{}\nVerified Revit process: PID {}; Revit {}; port {}; session {}".format(
                text, received["pid"], received["revit_version"],
                received["actual_port"], received["session_token"])
        if target is None:
            configured = getattr(revit_get, "revit_target", None)
            if configured:
                text = "{}\nMCP target: {}".format(text, configured)
        return text

    @mcp.tool()
    async def get_revit_model_info(ctx: Context) -> str:
        """Summarise the currently open Revit model.

        Use this to orient yourself before doing anything else: it reports the
        document title and path, the element and family counts, the levels, and
        the project information fields.

        Scope: the active document only. Linked models are not traversed.

        Args:
            ctx: MCP context for logging
        """
        response = await revit_get("/model_info/", ctx)
        return format_response(response)
