# -*- coding: utf-8 -*-
"""Status and model information tools"""

import sys
from pathlib import Path

from mcp.server.fastmcp import Context
from .utils import PROVENANCE_ATTR, _body_of, format_response

# Must equal revit_mcp/runtime_info.PRODUCT_VERSION and the version in pyproject.toml;
# tests/unit/test_runtime_info.py keeps the three equal. The payload ships no
# revit_mcp package, hence the copy.
PRODUCT_VERSION = "2.0.0"


def _payload_build():
    """The build stamp in the installed payload's VERSION file, or None in a checkout.

    In a payload this file lives at <payload>/app/tools/, so VERSION sits two levels
    up; a development checkout has no app/ directory and reports None.
    """
    try:
        app_dir = Path(__file__).resolve().parents[1]
        if app_dir.name.lower() != "app":
            return None
        text = (app_dir.parent / "VERSION").read_text(encoding="utf-8-sig").strip()
        return text or None
    except (OSError, ValueError):
        return None


def _sdk_version():
    """The installed mcp SDK version, or None."""
    try:
        from importlib.metadata import version

        return version("mcp")
    except Exception:
        return None


def server_info():
    """{"product_version", "build", "python", "mcp_sdk", "executable"} of this server; never raises."""
    info = sys.version_info
    return {
        "product_version": PRODUCT_VERSION,
        "build": _payload_build(),
        "python": "{}.{}.{}".format(info[0], info[1], info[2]),
        "mcp_sdk": _sdk_version(),
        "executable": sys.executable,
    }


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


def _secret_line(response, revit_get):
    """One line saying whether the two halves hold the same shared secret, or "".

    Built from the reply's ``secret`` block (a dict reply, or the JSON body of an
    "Error: 503 - ..." text) and the transport's own fingerprint (the
    ``secret_fingerprint`` seam, read with getattr: tools never import the
    transport). Only 8-hex fingerprints are ever named, never the secret. Returns ""
    when the reply has no secret block and the transport reports no fingerprint, so a
    bare transport keeps its exact text.
    """
    body = _body_of(response)
    block = body.get("secret") if isinstance(body, dict) else None
    reader = getattr(revit_get, "secret_fingerprint", None)
    if not isinstance(block, dict) and not callable(reader):
        return ""
    try:
        local = reader() if callable(reader) else None
    except Exception:
        local = None
    if not isinstance(block, dict):
        return ("Shared secret: the Revit extension does not report its secret state "
                "(an extension older than R3).")
    remote = block.get("fingerprint")
    if not block.get("configured") or not remote:
        return ("Shared secret: the Revit extension has none; every mutation is refused "
                "(401 server_not_configured).")
    if not local:
        return ("Shared secret: this MCP server loaded none; every mutation is refused "
                "(401 missing): run Update RevitMCP (or sign out of Windows and back in) "
                "and restart the assistant session.")
    if remote == local:
        return "Shared secret: both halves hold the same secret (fingerprint {}).".format(remote)
    return ("Shared secret: the halves DIFFER (Revit {}, this MCP server {}); every mutation "
            "is refused with 401 mismatch until both come from the same build: run Update "
            "RevitMCP, restart the assistant session, then fully restart Revit.".format(remote, local))


def _permit_line(response):
    """One line stating whether the Revit extension reports one-time permit enforcement."""
    body = _body_of(response)
    block = body.get("permit") if isinstance(body, dict) else None
    if not isinstance(block, dict):
        return ("One-time permits: the Revit extension does not report permit support (older than R5); "
                "a direct HTTP mutation is not refused for lacking a permit.")
    protocol = block.get("protocol")
    if protocol is None:
        return ("One-time permits: the Revit extension does not report permit support (older than R5); "
                "a direct HTTP mutation is not refused for lacking a permit.")
    return "One-time permits: the Revit extension enforces them (protocol {}).".format(protocol)


def _version_lines(response, server=None):
    """Lines naming the versions of both halves and what runs them; never raises.

    The MCP-server line comes from this process. The extension lines come from the
    reply's ``runtime`` block; an extension older than 2.0.0 has none and is named as
    such. A product-version difference between the halves gets its own warning line.
    """
    server = server if isinstance(server, dict) else server_info()
    lines = ["MCP server: RevitMCP {}, build {}, Python {}, MCP SDK {}.".format(
        server.get("product_version"), server.get("build") or "development checkout",
        server.get("python"), server.get("mcp_sdk") or "unknown")]
    body = _body_of(response)
    if not isinstance(body, dict):
        return lines
    runtime = body.get("runtime")
    if not isinstance(runtime, dict):
        lines.append("Revit extension: reports no version (older than 2.0.0).")
        return lines
    extension = runtime.get("extension") if isinstance(runtime.get("extension"), dict) else {}
    python = runtime.get("python") if isinstance(runtime.get("python"), dict) else {}
    pyrevit = runtime.get("pyrevit") if isinstance(runtime.get("pyrevit"), dict) else {}
    revit = runtime.get("revit") if isinstance(runtime.get("revit"), dict) else {}
    commit = extension.get("commit")
    build = ("{} ({})".format(str(commit)[:7], extension.get("built_at") or "time unknown")
             if commit else "no manifest (development junction)")
    lines.append("Revit extension: RevitMCP {}, build {}, loaded from {}.".format(
        runtime.get("product_version") or "unknown", build, extension.get("path") or "unknown"))
    lines.append("Revit side: pyRevit {}, engine {} ({} {}), Revit {} build {}.".format(
        pyrevit.get("version") or "unknown", pyrevit.get("engine") or "unknown",
        python.get("implementation") or "unknown", python.get("version") or "unknown",
        revit.get("sub_version") or revit.get("version") or "unknown", revit.get("build") or "unknown"))
    remote = runtime.get("product_version")
    if remote and remote != server.get("product_version"):
        lines.append("Versions DIFFER: the Revit extension is {}, this MCP server is {}; run Update "
                     "RevitMCP, restart the assistant session, then fully restart Revit.".format(
                         remote, server.get("product_version")))
    return lines


async def _policy_line(revit_get):
    """One approval-policy diagnostics line from the optional injected transport seam."""
    reader = getattr(revit_get, "policy_status", None)
    if not callable(reader):
        return ""
    try:
        status = await reader(refresh=True)
    except Exception:
        return ""
    if not isinstance(status, dict):
        return ""
    source = status.get("source")
    version = status.get("hash")
    if source is None and version is None and not status.get("blocked"):
        return ""
    line = "Approval policy: source {}, version {}.".format(source or "unknown", version or "unknown")
    if status.get("blocked"):
        return (line + " Every protected operation is refused because the base policy is invalid" +
                (": {}.".format(status.get("blocked_reason")) if status.get("blocked_reason") else "."))
    if status.get("operator_state") == "rejected":
        diagnostic = status.get("diagnostic")
        line += " Operator policy file not accepted (файл оператора не принят): rejected"
        if diagnostic:
            line += ": {}".format(diagnostic)
        line += "."
    return line


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

        The reply also carries four security blocks from the extension.
        "secret" is whether the extension holds a shared secret plus its short
        fingerprint (8 hex characters of a SHA-256: it identifies the secret, it is
        not the secret). A line "Shared secret: ..." right after the status
        compares that fingerprint with this MCP server's own and says whether both
        halves hold the same secret, differ, or one of them has none; when they
        differ or either has none, every mutation is refused with 401. "integrity"
        is whether the extension files match the published manifest, taken once at
        load: on verified_mismatch the differing files are named and mutations are
        refused with 423 until the extension is reinstalled and Revit fully
        restarted; unverifiable (for example a developer junction with no manifest)
        is reported but is not damage and blocks nothing. "bind" is
        loopback_only, exposed or unknown: exposed means Routes listens beyond this
        machine, which is reported and degrades health but blocks nothing. "permit"
        names the one-time-permit protocol the extension enforces; its status line warns
        when an older extension does not report it, because that extension still accepts
        a direct HTTP mutation without a permit. A second status line names the active
        approval-policy source and version and reports an invalid operator/base policy.
        "security_alerts" lists in plain words anything that needs action.

        Version lines come right after the status: "MCP server:" names this server's RevitMCP version,
        payload build, Python and MCP SDK; "Revit extension:" names the extension's
        version, build commit and the folder it was loaded from; "Revit side:" names
        the pyRevit version, the Python engine (IPY342 is the supported one) and the
        Revit version and build. "Versions DIFFER" means the halves come from
        different releases. The raw facts are in the reply's "runtime" block;
        "runtime_alerts" (which degrade health) explain an unsupported engine.

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
        body = _body_of(response)
        # Version lines need a runtime block or the real bridge (it carries the
        # secret_fingerprint seam); a bare transport keeps its exact text.
        if (isinstance(body, dict) and isinstance(body.get("runtime"), dict)) or \
                callable(getattr(revit_get, "secret_fingerprint", None)):
            for line in _version_lines(response):
                text = "{}\n{}".format(text, line)
        secret_line = _secret_line(response, revit_get)
        if secret_line:
            text = "{}\n{}".format(text, secret_line)
        permit_line = _permit_line(response)
        if permit_line:
            text = "{}\n{}".format(text, permit_line)
        policy_line = await _policy_line(revit_get)
        if policy_line:
            text = "{}\n{}".format(text, policy_line)
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
