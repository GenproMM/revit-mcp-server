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
