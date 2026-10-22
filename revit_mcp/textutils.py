# -*- coding: utf-8 -*-
"""
Pure text helpers for the Revit MCP extension.

This module is deliberately free of any pyRevit or Revit API import, which
makes it the one part of revit_mcp/ that can be imported -- and therefore unit
tested -- under CPython 3. revit_mcp/utils.py re-exports these names, so route
modules keep using the familiar `from utils import sanitize_string`.

It registers no routes. startup.py's discovery classifies it as a helper.

The runtime aliases below are what let one definition serve both halves:
under IronPython 2.7 text is `unicode` and bytes are `str`; under CPython 3
text is `str` and bytes are `bytes`. Behaviour on the Revit side is unchanged.
"""

import json
import logging

# `bytes is str` is the discriminator, and the probe has to be this one: it is
# true only on Python 2, where the two really are one type.
#
# Testing `unicode` for a NameError instead -- the obvious version, and what
# this module did until 2026-09-07 -- reports the wrong runtime inside pyRevit.
# pyRevit injects `unicode` as an alias of `str` into its IronPython 3 engine,
# so the probe succeeded, both aliases collapsed onto `str`, and no real
# `bytes` ever matched _BYTES_TYPE. Every POST body then reached its route
# handler as undecoded bytes and died on `.get` ('bytes' object has no
# attribute 'get'), while sanitize_string() stringified byte text into a
# literal "b'...'". Verified live in the routes engine, where the same probe
# that returns bytes-is-not-str also reports unicode as present.
if bytes is str:  # IronPython 2.7 / Python 2
    _TEXT_TYPE = unicode  # noqa: F821 - defined only on Python 2
    _BYTES_TYPE = str
else:  # IronPython 3 / CPython 3
    _TEXT_TYPE = str
    _BYTES_TYPE = bytes


def sanitize_string(text):
    """Return Revit text as a JSON-safe text string.

    Revit API strings arrive as .NET System.String, which IronPython 2.7
    already represents as unicode -- there is no need to collapse non-ASCII
    characters (e.g. Cyrillic element/view names) to '?'. pyRevit's routes
    JSON serializer escapes non-ASCII as \\uXXXX on its own, so unicode text
    round-trips to the client intact.

    None becomes "Unnamed". Undecodable bytes are replaced rather than raising:
    a single bad name must never sink a whole listing.
    """
    if text is None:
        return "Unnamed"
    try:
        if isinstance(text, _TEXT_TYPE):
            return text
        if isinstance(text, _BYTES_TYPE):
            return text.decode("utf-8", "replace")
        return _TEXT_TYPE(text)
    except Exception:
        return "Unnamed"


def sanitize_value(value):
    """sanitize_string() with the empty-input contract parameter values need.

    A missing parameter renders as "" rather than "Unnamed": for a *value*,
    the word "Unnamed" would be indistinguishable from a parameter whose text
    genuinely is that, and an unset parameter is meaningfully empty.

    This lived in parameters.py as a hand-rolled copy that referenced `unicode`
    directly. Under IronPython 3 that raised NameError inside its own
    `except Exception`, so every parameter value silently serialized as "" --
    no error, no log, just blank data. Sharing the guarded aliases above is
    what stops that from happening again.
    """
    if value is None:
        return ""
    try:
        if isinstance(value, _TEXT_TYPE):
            return value
        if isinstance(value, _BYTES_TYPE):
            return value.decode("utf-8", "replace")
        return _TEXT_TYPE(value)
    except Exception:
        return ""


def normalize_string(text):
    """Whitespace-trimmed variant of sanitize_string()."""
    if text is None:
        return "Unnamed"
    try:
        return sanitize_string(text).strip()
    except Exception:
        return "Unnamed"


# ---------------------------------------------------------------- exception diagnostics
#
# Revit often raises a .NET exception whose Python-visible text is generic ("A
# managed exception was thrown by Revit or by one of its external applications.")
# while the real cause sits in the .NET type, the InnerException chain or the
# stack trace. exception_diagnostics() collects those into one small dict of
# bounded plain strings for a route to put in its error reply. Duck-typed and
# pure, so it is unit tested under CPython with fake exception objects.

_DIAG_MESSAGE_CAP = 1000
_DIAG_INNER_MESSAGE_CAP = 500
_DIAG_STACK_CAP = 2000
_DIAG_MAX_INNER = 5
_DIAG_TRUNCATED = "...[truncated]"

logger = logging.getLogger(__name__)


def _diag_read(obj, name):
    """getattr that returns None instead of raising (a hostile wrapper may raise anything)."""
    try:
        return getattr(obj, name)
    except AttributeError:
        return None  # absent, which is the normal case for a plain Python exception
    except Exception:
        logger.warning("exception diagnostics: attribute {} could not be read".format(name))
        return None


def _diag_text(value, cap):
    """(bounded text, truncated); (None, False) for None or anything that cannot be rendered."""
    if value is None:
        return None, False
    try:
        text = sanitize_value(value)
        if len(text) > cap:
            return text[:cap] + _DIAG_TRUNCATED, True
        return text, False
    except Exception:
        logger.warning("exception diagnostics: a value could not be rendered as text")
        return None, False


def _diag_net_type_name(net):
    """Full .NET type name of ``net`` via GetType().FullName, or None."""
    getter = _diag_read(net, "GetType")
    if getter is None:
        return None
    try:
        net_type = getter()
    except Exception:
        logger.warning("exception diagnostics: GetType() failed")
        return None
    return _diag_text(_diag_read(net_type, "FullName"), _DIAG_INNER_MESSAGE_CAP)[0]


def _diag_net_exception(exc):
    """The .NET exception behind ``exc`` (clsException, or exc itself when it is one), or None."""
    for candidate in (_diag_read(exc, "clsException"), exc):
        if candidate is not None and _diag_read(candidate, "GetType") is not None:
            return candidate
    return None


def _diag_stack_trace(net):
    """(text, truncated) from the .NET StackTrace, falling back to ToString()."""
    trace = _diag_read(net, "StackTrace")
    if trace is None or not _diag_text(trace, 1)[0]:
        try:
            trace = net.ToString()
        except Exception:
            logger.warning("exception diagnostics: ToString() failed")
            trace = None
    return _diag_text(trace, _DIAG_STACK_CAP)


def _diag_inner_chain(net):
    """[{net_type, message}] for the InnerException chain, at most _DIAG_MAX_INNER deep."""
    chain = []
    current = net
    for _ in range(_DIAG_MAX_INNER):
        inner = _diag_read(current, "InnerException")
        if inner is None:
            break
        chain.append({
            "net_type": _diag_net_type_name(inner),
            "message": _diag_text(_diag_read(inner, "Message"), _DIAG_INNER_MESSAGE_CAP)[0],
        })
        current = inner
    return chain


def exception_diagnostics(exc):
    """Bounded plain-string diagnostics of one caught exception; never raises.

    Keys: python_type (class name), net_type (.NET full type name or None),
    message (Python text of the exception), net_message (the .NET Message or
    None), inner_exceptions (list of {net_type, message}, at most five deep),
    stack_trace (.NET stack trace, at most 2000 characters, or None) and
    stack_trace_truncated. Duck-typed over IronPython (a Python exception exposes
    its .NET exception as clsException, a caught .NET exception is its own) and
    over the fake objects the unit tests use. Non-ASCII text is kept: the routes
    serializer escapes it. Nothing here calls the Revit API.
    """
    try:
        python_type = type(exc).__name__
    except Exception:
        python_type = "unknown"
    info = {
        "python_type": python_type,
        "net_type": None,
        "message": None,
        "net_message": None,
        "inner_exceptions": [],
        "stack_trace": None,
        "stack_trace_truncated": False,
    }
    try:
        info["message"] = _diag_text(exc, _DIAG_MESSAGE_CAP)[0] if exc is not None else None
        net = _diag_net_exception(exc)
        if net is not None:
            info["net_type"] = _diag_net_type_name(net)
            info["net_message"] = _diag_text(_diag_read(net, "Message"), _DIAG_MESSAGE_CAP)[0]
            if net is exc and info["net_message"]:
                info["message"] = info["net_message"]
            info["inner_exceptions"] = _diag_inner_chain(net)
            info["stack_trace"], info["stack_trace_truncated"] = _diag_stack_trace(net)
    except Exception:
        logger.warning("exception diagnostics: collection stopped early")
    return info


def parse_request_data(data):
    """Return a route request body as Python data, in either engine.

    pyRevit parses the body itself only when the request carries
    Content-Type: application/json -- and that parse is broken on IronPython 3:
    routes/server/server.py hands the raw bytes from rfile.read() to a
    3.5-level json.loads, which rejects them with "the JSON object must be str,
    not 'bytes'". The exception is raised while pyRevit prepares the request, so
    no handler runs and no Revit work is attempted. Patching it from the
    extension is not possible: the routes server lives in its own IronPython
    engine with its own module table, and a patch installed from startup.py
    reaches a different copy of that module (verified live, 2026-09-07).

    So the MCP client declares text/plain instead (main.py), pyRevit passes the
    body through untouched, and route handlers parse it here. That leaves three
    shapes to accept, and all three are real:

      bytes  what pyRevit passes through on IronPython 3
      str    the same on IronPython 2.7, where bytes and str are one type
      dict   a client that still sends application/json, on an engine where
             pyRevit's own parse works (IronPython 2.7, or a fixed pyRevit)

    Anything else -- None above all, from a request with no body -- is returned
    untouched, so a route keeps deciding for itself whether a missing payload is
    a 400 or a default.
    """
    if isinstance(data, _BYTES_TYPE):
        data = data.decode("utf-8")
    if isinstance(data, _TEXT_TYPE):
        return json.loads(data)
    return data



# Control characters that a mangled Windows path carries, mapped to the escape
# that produced them. A Windows path typed into a non-raw string literal loses
# every backslash that forms a recognised escape:
#     "C:\10_bim\4_p\new.rvt"  ->  "C:\x08_bim\x04_p" + newline + "ew.rvt"
# because \1 is \x08 (backspace), \4 is \x04 and \n is a newline.
#
# A Cyrillic path makes this look like an encoding fault, which it is not. The
# bridge round-trips UTF-8 correctly: json.dumps escapes non-ASCII to \uXXXX and
# json.loads restores it (verified end to end). What actually breaks is that
# "\<Cyrillic>" is not a recognised escape and survives untouched, while "\10"
# silently becomes a control character -- so the path still looks almost right
# and fails with a bare "not found" that points nowhere near the real cause.
_ESCAPE_CULPRITS = {
    "\x07": "\\a",
    "\x08": "\\b",
    "\x0c": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\x0b": "\\v",
    "\0": "\\0",
}


def describe_broken_path(path):
    """Return a diagnosis if `path` carries mangled escapes, else None.

    A Windows path is only safe inside a string literal when its backslashes are
    doubled or the literal is raw. When they are not, the surviving control
    characters are unambiguous evidence: no legal Windows path may contain one.
    """
    if not isinstance(path, _TEXT_TYPE):
        return None

    hits = []
    for index, char in enumerate(path):
        code = ord(char)
        if code < 32 or code == 127:
            culprit = _ESCAPE_CULPRITS.get(char, "\\x{:02x}".format(code))
            hits.append("U+{:04X} at position {} (from a literal {})".format(
                code, index, culprit))
    if not hits:
        return None

    return (
        "The path contains control characters, which means its backslashes were "
        "consumed as escape sequences before it arrived: {}. Resend the path with "
        "doubled backslashes (\"G:\\\\folder\\\\file.rvt\"), as a raw string "
        "(r\"G:\\folder\\file.rvt\"), or with forward slashes (\"G:/folder/file.rvt\"). "
        "This is not a Unicode problem: Cyrillic and other non-ASCII path names "
        "transfer correctly.".format("; ".join(hits))
    )
