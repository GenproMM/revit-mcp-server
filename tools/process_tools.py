# -*- coding: utf-8 -*-
"""Revit process lifecycle tools.

Every other tool in this package is a thin wrapper over the pyRevit Routes
bridge, which only exists while Revit is running. These two are the exception:
they are what you call when it is *not*. They therefore talk to the local
machine directly. Whether a Revit is running is decided by the discovery facade
the injected `revit_get` carries (`revit_get.discover_targets`), never by one
fixed-port guess: with a single shared MCP entry several Revit processes can
run, two can listen on one port, and the listener inventory can fail. None of
those is "Revit is closed", and only proven absence may launch another process.
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


_NO_FACADE = (
    "Revit process discovery is not available on this transport, so no process list "
    "was produced. That does not mean no Revit runs."
)


async def _survey(revit_get) -> dict:
    """What discovery proves right now, as {"kind", "usable", "unusable", "detail"}.

    kind is one of:
      discovery_unavailable  the injected callable has no discover_targets facade
      discovery_failed       the facade raised
      inventory_failure      the OS listener inventory was missing or malformed
      collision              some port has two or more LISTENING PIDs
      many / one             one or more usable (identity-proven) incarnations
      unresolved_listeners   listeners exist but none answered as Revit
      none                   the inventory was read and nothing listens: proven absence

    Only "none" is evidence that Revit is not running. Every other kind that has
    no usable process is inconclusive, and a lifecycle tool must not launch on it.
    """
    discover = getattr(revit_get, "discover_targets", None)
    if discover is None:
        return {"kind": "discovery_unavailable", "usable": [], "unusable": [],
                "detail": _NO_FACADE}
    try:
        found = await discover()
    except Exception as exc:  # a tool never raises
        return {"kind": "discovery_failed", "usable": [], "unusable": [],
                "detail": "Revit process discovery failed: %s. That does not mean no "
                          "Revit runs." % (str(exc) or type(exc).__name__)}
    if (not isinstance(found, dict) or found.get("status") != "ok"
            or not isinstance(found.get("usable"), list)
            or not isinstance(found.get("unusable"), list)):
        message = found.get("message") if isinstance(found, dict) else None
        return {"kind": "inventory_failure", "usable": [], "unusable": [],
                "detail": message or "Revit process discovery returned no usable "
                                     "answer. That does not mean no Revit runs."}
    usable, unusable = found["usable"], found["unusable"]
    collisions = [u for u in unusable if u.get("reason") == "listener-collision"]
    if collisions:
        kind = "collision"
    elif len(usable) > 1:
        kind = "many"
    elif usable:
        kind = "one"
    elif unusable:
        kind = "unresolved_listeners"
    else:
        kind = "none"
    return {"kind": kind, "usable": usable, "unusable": unusable, "detail": ""}


def _pids(entries) -> str:
    return ", ".join(str(p) for e in entries for p in e.get("pids", []))


def _process_rows(usable) -> list:
    return [{"pid": e.get("pid"), "port": e.get("port"),
             "revit_version": e.get("revit_version"),
             "document_open": e.get("document_open")} for e in usable]


def _listener_rows(unusable) -> list:
    return [{"port": e.get("port"), "pids": list(e.get("pids", [])),
             "reason": e.get("reason")} for e in unusable]


def register_process_tools(mcp, revit_get, revit_post=None, revit_image=None):
    """Register Revit process lifecycle tools."""
    _ = revit_post, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def get_revit_process_status(ctx: Context = None) -> str:
        """Report which Revit processes are running and which versions are installed.

        Use this before any other Revit tool when you are unsure Revit is open,
        and to decide which version to pass to start_revit. It talks to the
        local machine only (the operating system's listener table and each
        listener's identity answer); it never opens or modifies a document, so
        it is always safe to call. It never reports "not running" unless the
        listener table was read and nothing was listening.

        Returns lines of "Field: value" with:
          process_state    str   - exactly one of:
            none                   proven absence: no Revit process is listening
            one_ready              one Revit, a document is open; every tool works
            one_no_document        one Revit on its Home screen (HTTP 503); open a model
            many                   several usable Revits; see processes
            collision              a port has two LISTENING processes (both PIDs are
                                   in ambiguous_listeners); no process is selected
            inventory_failure      the OS listener listing was unavailable or malformed
            discovery_failed       discovery raised an error
            discovery_unavailable  this transport has no discovery
            unresolved_listeners   something listens but did not answer as Revit
            status_unavailable     one Revit was found but its own status call failed
          ready            bool  - true only for one_ready
          revit_running    bool or "unknown" - true when a usable Revit exists, false
                           only for none, "unknown" when discovery is inconclusive
          processes        list  - [{"pid", "port", "revit_version", "document_open"}]
          ambiguous_listeners list - [{"port", "pids", "reason"}] never selected
          installed        list  - [{"version": "2027", "path": "..."}], newest first
          recommendation   str   - what to do next in plain words

        With several processes or a collision the status of an individual process
        is not read (that would pick one): call discover_revit_targets for the
        exact target value of each usable process. A collision, an unavailable
        listing and a listener that did not answer are all different from a
        closed Revit: do not launch another one on their account.

        Limitations: only local loopback Revit processes in the probed port range
        are covered, and the listing is a snapshot, not a reservation. It cannot
        distinguish a still-starting Revit from a disabled pyRevit Routes server.

        Args:
            ctx: MCP context, used for progress logging. Optional.
        """
        installed = _discover()
        survey = await _survey(revit_get)
        kind, usable, unusable = survey["kind"], survey["usable"], survey["unusable"]
        processes = _process_rows(usable)
        state = kind
        ready = False

        if kind == "one":
            # The one validated incarnation: its own selected status, never an
            # unselected route. HTTP 503 (selected payload carrying an error) means
            # Revit is running with no document.
            entry = usable[0]
            try:
                answer = await revit_get("/status/", ctx, target=entry["selector"],
                                         timeout=5.0)
            except Exception:
                answer = None
            if isinstance(answer, dict):
                ready = not answer.get("error")
                state = "one_ready" if ready else "one_no_document"
                processes[0]["document_open"] = ready
            else:
                state = "status_unavailable"

        if state == "none":
            running = False
        elif usable:
            running = True
        else:
            running = "unknown"

        if state == "none":
            if installed:
                recommendation = (
                    "No Revit process is running. Call start_revit to launch it "
                    "(version %s will be used by default)." % installed[0][0]
                )
            else:
                recommendation = (
                    "No Revit installation was found under %s. Set REVIT_EXE to the "
                    "full path of Revit.exe if it lives elsewhere." % _INSTALL_GLOB
                )
        elif state == "one_ready":
            recommendation = ("Revit is reachable; use the other tools normally. With one "
                              "process a call may omit target.")
        elif state == "one_no_document":
            recommendation = (
                "Revit is running but no document is open. Open a model in "
                "Revit; the other tools cannot work without one."
            )
        elif state == "status_unavailable":
            recommendation = (
                "One Revit process was found (PID %s) but its own status call failed. "
                "Call discover_revit_targets and retry; do not launch another Revit."
                % usable[0].get("pid")
            )
        elif state == "many":
            recommendation = (
                "%d usable Revit processes are running. Call discover_revit_targets "
                "for the exact target value of each and pass one with every call; "
                "no launch is needed." % len(usable)
            )
        elif state == "collision":
            recommendation = (
                "Two Revit processes listen on the same port (PIDs %s), so requests "
                "would land on an unpredictable one and none is selected. Close the "
                "extra Revit, then run discover_revit_targets. Launching another "
                "Revit now would make it worse." % _pids(
                    [u for u in unusable if u.get("reason") == "listener-collision"])
            )
        elif state == "unresolved_listeners":
            recommendation = (
                "Something listens on a Revit port (PIDs %s) but did not answer as "
                "Revit: it may still be starting, hung, or not Revit. Wait and run "
                "discover_revit_targets again; do not launch another Revit yet."
                % _pids(unusable)
            )
        else:  # inventory_failure, discovery_failed, discovery_unavailable
            recommendation = (
                "%s Whether Revit is open is unknown: this is not proof that Revit is "
                "closed, so do not launch another one on this evidence; run "
                "discover_revit_targets once the listener listing works."
                % survey["detail"]
            )

        return format_response(
            {
                "process_state": state,
                "ready": ready,
                "revit_running": running,
                "processes": processes,
                "ambiguous_listeners": _listener_rows(unusable),
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
        out.

        Which Revit this means: the call probes and waits on this MCP entry's
        own Routes port (REVIT_PORT, default 48884). On an entry configured for
        another port it therefore launches a new Revit even while one is
        already running on 48884. pyRevit gives each new Revit the first port
        not already registered by a running Revit, counting up from 48884, so
        start instances one at a time, each after the previous one answers, or
        two can end up sharing 48884. If no Revit holds 48884, a Revit launched
        from an entry configured for 48885 takes 48884 and this call waits
        until its timeout.

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
