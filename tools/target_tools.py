# -*- coding: utf-8 -*-
"""Revit process discovery: one shared entry, an exact selector per call.

The server is one MCP entry. When several Revit processes run on this machine
the assistant lists them here and passes one selector with later calls; nothing
picks a process for it. Discovery goes through the facade the injected
``revit_get`` carries (``revit_get.discover_targets``); this module never
imports the transport.
"""

from mcp.server.fastmcp import Context

from .utils import format_response


def _usable_line(index, entry):
    document = ("a document is open" if entry["document_open"]
                else "no document open (Revit answers HTTP 503 until one is opened)")
    return ("{}. PID {}; Revit {}; port {}; {}\n   target: {}".format(
        index, entry["pid"], entry["revit_version"], entry["port"], document,
        entry["selector"]))


def _unusable_line(entry):
    pids = ", ".join(str(p) for p in entry["pids"])
    label = "listener collision" if entry["reason"] == "listener-collision" else entry["reason"]
    return "- port {}; PID {}; {}: {}".format(entry["port"], pids, label, entry["detail"])


def register_target_tools(mcp, revit_get, revit_post=None, revit_image=None):
    """Register Revit process discovery tools."""
    _ = revit_post, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def discover_revit_targets(ctx: Context = None) -> str:
        """List the Revit processes this server can address, with an exact selector for each.

        Call this when more than one Revit may be running, when another tool
        refuses with a candidate list, or after a Revit restart. It reads the
        operating system's TCP listener table and asks each singleton listener
        for its identity on GET /status/; it never opens, changes or reads a
        model, so it is always safe to call.

        Returns, per usable process: PID, Revit version, port, whether a
        document is open, and a "target:" value. Pass that exact value as the
        target argument of a later call to address that process. A process that
        restarts is a new target even on the same port or PID: call this again.
        With exactly one usable process a call may omit target; with several, a
        call that omits it is refused and lists the candidates.

        Also lists unusable listeners. A port with two LISTENING processes is a
        collision: both PIDs are named and neither is offered as a target.
        A listener that did not answer (still initializing, hung, or not Revit)
        is listed with its reason, never as "no Revit".

        Limitations: only local loopback Revit processes are covered, within a
        bounded range of ports starting at the Routes default. The listener
        listing and the later request are separate moments, so this is a snapshot
        and not a reservation of the port. It is not authentication. If the
        operating system listing is unavailable this returns an error, which
        does not mean that no Revit is running.

        Args:
            ctx: MCP context for logging
        """
        discover = getattr(revit_get, "discover_targets", None)
        if discover is None:
            return format_response(
                "Error: Revit process discovery is not available on this transport; "
                "no process list was produced, which does not mean no Revit runs.")
        try:
            found = await discover()
        except Exception as exc:  # a tool never raises
            return format_response("Error: Revit process discovery failed: {}".format(
                str(exc) or type(exc).__name__))
        if found.get("status") != "ok":
            return format_response("Error: {}".format(found.get("message") or "discovery failed"))

        usable, unusable = found["usable"], found["unusable"]
        lines = []
        if usable:
            lines.append("Usable Revit processes: {}".format(len(usable)))
            lines.extend(_usable_line(i, e) for i, e in enumerate(usable, 1))
            if len(usable) > 1:
                lines.append("Several are usable: pass target=<one of the values above> to every call.")
        else:
            lines.append("No usable Revit process found in the probed local ports.")
        if unusable:
            lines.append("Unusable listeners (never offered as a target):")
            lines.extend(_unusable_line(e) for e in unusable)
        lines.append("Snapshot of the listener table and each identity answer at one instant; "
                     "not a reservation, not authentication.")
        return format_response("\n".join(lines))
