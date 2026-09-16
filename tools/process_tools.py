# -*- coding: utf-8 -*-
"""Revit process lifecycle tools.

Every other tool in this package is a thin wrapper over the pyRevit Routes
bridge, which only exists while Revit is running. These two are the exception:
they are what you call when it is *not*. They therefore talk to the local
machine directly and use `revit_get` only to probe whether the bridge has come
up yet.
"""

import asyncio
import glob
import os
import subprocess
import sys
import time

from mcp.server.fastmcp import Context

from .utils import describe_broken_path, format_response

# Autodesk installs to a predictable path; REVIT_EXE overrides it for anything
# unusual (a network install, a non-default drive).
_INSTALL_GLOB = r"C:\Program Files\Autodesk\Revit *\Revit.exe"

_POLL_INTERVAL_S = 3.0
_PROGRESS_EVERY_S = 15.0


def _discover() -> "list[tuple[str, str]]":
    """[(version, exe_path)] for every Revit found, newest first."""
    found = {}

    override = os.environ.get("REVIT_EXE")
    if override and os.path.isfile(override):
        found[_version_of(override)] = override

    for exe in glob.glob(_INSTALL_GLOB):
        if os.path.isfile(exe):
            found.setdefault(_version_of(exe), exe)

    return sorted(found.items(), key=lambda kv: kv[0], reverse=True)


def _version_of(exe_path: str) -> str:
    """'C:\\...\\Revit 2027\\Revit.exe' -> '2027'; falls back to the folder name."""
    folder = os.path.basename(os.path.dirname(exe_path))
    tail = folder.rsplit(" ", 1)[-1]
    return tail if tail.isdigit() else folder


async def _say(ctx, message: str) -> None:
    """Best-effort progress log.

    ctx.info() raises when there is no active request context, and this tool can
    run for minutes. Losing a progress line must never fail the launch.
    """
    if not ctx:
        return
    try:
        await ctx.info(message)
    except Exception:
        pass


async def _bridge_state(revit_get, ctx) -> str:
    """One of "ready", "no_document", "down".

    The distinction matters: `/status/` answers 503 when Revit is running but
    has no document open (revit_mcp/status.py), and `_revit_call` collapses
    every non-200 into an "Error: <code> - <body>" string. Treating that as
    "down" would make start_revit wait out its whole timeout against a Revit
    that is already up and sitting on the Home screen.

    A transport failure has no status code in it ("Error: All connection
    attempts failed"), which is what separates the two cases.
    """
    response = await revit_get("/status/", ctx, timeout=5.0)
    if isinstance(response, dict):
        return "ready"
    text = str(response)
    if text.startswith("Error: "):
        head = text[len("Error: "):].split(" ", 1)[0]
        if head.isdigit():
            return "no_document"  # the server answered, just not with 200
    return "down"


def register_process_tools(mcp, revit_get, revit_post=None, revit_image=None):
    """Register Revit process lifecycle tools."""
    _ = revit_post, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def get_revit_process_status(ctx: Context = None) -> str:
        """Report whether Revit is reachable and which versions are installed.

        Use this before any other Revit tool when you are unsure Revit is open,
        and to decide which version to pass to start_revit. It talks to the
        local machine and to the pyRevit Routes port only; it never opens or
        modifies a document, so it is always safe to call.

        Returns lines of "Field: value" with:
          ready            bool  - a document is open; every tool will work
          revit_running    bool  - Revit is up and the bridge answers
          installed        list  - [{"version": "2027", "path": "..."}], newest first
          recommendation   str   - what to do next in plain words

        The two booleans differ in one common case: Revit open on its Home
        screen with no document. The bridge answers, so revit_running is true,
        but model tools will fail until a document is opened - so ready is false.

        Limitations: when revit_running is false this cannot distinguish Revit
        being closed from Revit still starting up, or from the pyRevit Routes
        server being disabled.

        Args:
            ctx: MCP context, used for progress logging. Optional.
        """
        installed = _discover()
        state = await _bridge_state(revit_get, ctx)

        if state == "ready":
            recommendation = "Revit is reachable; use the other tools normally."
        elif state == "no_document":
            recommendation = (
                "Revit is running but no document is open. Open a model in "
                "Revit; the other tools cannot work without one."
            )
        elif installed:
            recommendation = (
                "Revit is not running. Call start_revit to launch it "
                "(version %s will be used by default)." % installed[0][0]
            )
        else:
            recommendation = (
                "No Revit installation was found under %s. Set REVIT_EXE to the "
                "full path of Revit.exe if it lives elsewhere." % _INSTALL_GLOB
            )

        return format_response(
            {
                "ready": state == "ready",
                "revit_running": state != "down",
                "installed": [{"version": v, "path": p} for v, p in installed],
                "recommendation": recommendation,
            }
        )

    @mcp.tool()
    async def start_revit(
        version: str = None,
        model_path: str = None,
        wait_seconds: float = 240.0,
        ctx: Context = None,
    ) -> str:
        """Launch Revit on this machine and wait until the MCP bridge responds.

        Call this when get_revit_process_status reports ready=false, or when any
        other tool fails with a connection error. If the bridge already answers,
        this returns immediately without starting a second Revit.

        Revit is slow to start: a cold launch plus pyRevit loading commonly takes
        60-180 seconds, and opening a large central model takes longer still. The
        call blocks until the bridge answers or wait_seconds elapses. A timeout is
        not proof of failure - Revit may still be loading - so on timeout, poll
        get_revit_process_status rather than calling this again.

        Returns lines of "Field: value" with:
          outcome        "success" when the bridge answered, "timeout" otherwise
          already_running  bool  - true if Revit was reachable before this call
          document_open  bool  - false when Revit is up but on its Home screen
          version        str   - the Revit version launched
          exe            str   - the executable used
          waited_seconds float - how long the wait actually took
          next_step      str   - what to do next in plain words
        On failure it returns an "=== ERROR DETAILS ===" block instead.

        Success means Revit is up and the bridge answers. It does NOT mean a
        model is loaded: launched without model_path, Revit stops on its Home
        screen and document_open is false. The other tools need a document.

        Limitations: launches on the machine the MCP server runs on, which is the
        user's own workstation. It cannot open a model that needs credentials, and
        it cannot dismiss a startup dialog - if Revit stops on one, the wait times
        out. Only one Revit is started; a second instance would bind a different
        Routes port and be unreachable anyway.

        Args:
            version: Revit release to launch, e.g. "2027". Defaults to the newest
                installed version.
            model_path: Optional full path to a .rvt file to open on startup.
                Must exist on this machine.
            wait_seconds: How long to wait for the bridge, in seconds. Default 240.
            ctx: MCP context, used for progress logging. Optional.
        """
        state = await _bridge_state(revit_get, ctx)
        if state != "down":
            return format_response(
                {
                    "outcome": "success",
                    "already_running": True,
                    "document_open": state == "ready",
                    "waited_seconds": 0.0,
                    "next_step": "Revit was already running; nothing was started."
                    + ("" if state == "ready"
                       else " No document is open - open a model in Revit before "
                            "using the other tools."),
                }
            )

        installed = _discover()
        if not installed:
            return format_response(
                {
                    "error": "No Revit installation found under %s. Set REVIT_EXE "
                    "to the full path of Revit.exe." % _INSTALL_GLOB
                }
            )

        if version:
            match = [(v, p) for v, p in installed if v == str(version)]
            if not match:
                return format_response(
                    {
                        "error": "Revit %s is not installed. Available: %s"
                        % (version, ", ".join(v for v, _ in installed))
                    }
                )
            chosen_version, exe = match[0]
        else:
            chosen_version, exe = installed[0]

        args = [exe]
        if model_path:
            if not os.path.isfile(model_path):
                problem = describe_broken_path(model_path)
                message = "Model not found on this machine: %s" % model_path
                if problem:
                    message = "%s -- %s" % (message, problem)
                return format_response({"error": message})
            args.append(model_path)

        await _say(ctx, "Starting Revit %s%s" % (
            chosen_version,
            " with %s" % os.path.basename(model_path) if model_path else ""))

        try:
            # Detached, with stdio pinned to DEVNULL. Inheriting this process's
            # stdout would let Revit write into the MCP protocol stream.
            creationflags = 0
            if sys.platform == "win32":
                creationflags = (
                    getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
            subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creationflags,
            )
        except Exception as e:
            return format_response({"error": "Could not launch %s: %s" % (exe, e)})

        started = time.time()
        next_report = _PROGRESS_EVERY_S
        while True:
            waited = time.time() - started
            if waited >= wait_seconds:
                return format_response(
                    {
                        "outcome": "timeout",
                        "already_running": False,
                        "document_open": False,
                        "version": chosen_version,
                        "exe": exe,
                        "waited_seconds": round(waited, 1),
                        "next_step": "Revit was launched but the bridge did not answer "
                        "within %.0fs. It may still be loading, waiting on a startup "
                        "dialog, or have the pyRevit Routes server disabled. Poll "
                        "get_revit_process_status rather than calling start_revit "
                        "again." % wait_seconds,
                    }
                )

            await asyncio.sleep(_POLL_INTERVAL_S)

            # "no_document" counts as started: Revit is up and the bridge is
            # answering. Waiting for a document would mean waiting for a human.
            state = await _bridge_state(revit_get, ctx)
            if state != "down":
                waited = time.time() - started
                return format_response(
                    {
                        "outcome": "success",
                        "already_running": False,
                        "document_open": state == "ready",
                        "version": chosen_version,
                        "exe": exe,
                        "waited_seconds": round(waited, 1),
                        "next_step": "Revit %s is up and the bridge is responding."
                        % chosen_version
                        + ("" if state == "ready"
                           else " No document is open - open a model in Revit before "
                                "using the other tools."),
                    }
                )

            if (time.time() - started) >= next_report:
                next_report += _PROGRESS_EVERY_S
                await _say(
                    ctx,
                    "Still waiting for Revit to finish loading (%.0fs elapsed)"
                    % (time.time() - started),
                )
