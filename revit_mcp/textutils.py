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

try:  # IronPython 2.7 / Python 2
    _TEXT_TYPE = unicode  # noqa: F821 - defined only on Python 2
    _BYTES_TYPE = str
except NameError:  # CPython 3
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
