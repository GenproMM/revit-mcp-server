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


# ---------------------------------------------------------------- open_model local copies
#
# Pure decisions behind open_model's defaults (quick task 261025-ld5). A route module
# cannot be imported under CPython, so the naming, mode resolution and workset-name
# matching live here where they can be unit tested. Paths are cut by hand at the last
# "/" or "\" instead of through os.path so Windows, UNC and forward-slash inputs behave
# the same under CPython on any OS and under IronPython.

# The text "оси и уровни" (Russian: axes and levels), lower case, written as \u escapes.
AXES_LEVELS_WORKSET_MARKER = "\u043e\u0441\u0438 \u0438 \u0443\u0440\u043e\u0432\u043d\u0438"

_EXISTING_LOCAL_MODES = ("error", "overwrite", "timestamp")


def local_copy_stamp(moment):
    """Return the date-time stamp YYYYMMDD_HHMMSS for a datetime (zero padded, locale free).

    ASSUMED to match Revit's own "Append timestamp to existing copy" naming; the live
    check in the quick-task summary compares it against Revit's dialog.
    """
    return "{:04d}{:02d}{:02d}_{:02d}{:02d}{:02d}".format(
        moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)


def _split_local_path(path):
    """Return (directory including its trailing separator or "", base name)."""
    cut = max(path.rfind("/"), path.rfind("\\"))
    return path[:cut + 1], path[cut + 1:]


def _split_stem(base):
    """Return (stem, extension); the extension is kept only for ".rvt" in any case."""
    if base.lower().endswith(".rvt"):
        return base[:-4], base[-4:]
    return base, ""


def local_backup_dir(local_path):
    """Return the Revit "<stem>_backup" folder that belongs to a local copy."""
    directory, base = _split_local_path(local_path)
    stem, _ = _split_stem(base)
    return directory + stem + "_backup"


def stamped_local_paths(local_path, stamp, exists, limit=100):
    """Return (new .rvt path, new backup folder) for renaming an existing local copy.

    The new stem is "<stem>_<stamp>", then "<stem>_<stamp>_2", "_3", ... for the first
    candidate where exists() is False for BOTH the file and its backup folder. Never
    returns the input path. Returns (None, None) when every candidate up to ``limit``
    is taken.
    """
    directory, base = _split_local_path(local_path)
    stem, extension = _split_stem(base)
    for n in range(1, limit + 1):
        new_stem = "{}_{}".format(stem, stamp)
        if n >= 2:
            new_stem = "{}_{}".format(new_stem, n)
        new_rvt = directory + new_stem + extension
        new_backup = directory + new_stem + "_backup"
        if new_rvt == local_path:
            continue
        if not exists(new_rvt) and not exists(new_backup):
            return new_rvt, new_backup
    return None, None


def resolve_existing_local_mode(existing_local, overwrite_local):
    """Resolve open_model's existing_local / legacy overwrite_local into (mode, error).

    mode is "timestamp" (default), "overwrite" or "error". Given existing_local wins and
    a given overwrite_local must agree with it (equal to mode == "overwrite"). Without
    existing_local the legacy flag maps true -> overwrite, false -> error. Kept in step
    with _resolve_existing_local in tools/worksharing_tools.py (the halves share no
    interpreter).
    """
    allowed = ", ".join(_EXISTING_LOCAL_MODES)
    if overwrite_local is not None and not isinstance(overwrite_local, bool):
        return None, "overwrite_local must be true or false"
    if existing_local is None:
        if overwrite_local is None:
            return "timestamp", None
        return ("overwrite" if overwrite_local else "error"), None
    if not isinstance(existing_local, _TEXT_TYPE):
        return None, "existing_local must be one of: {}".format(allowed)
    mode = existing_local.strip().lower()
    if mode not in _EXISTING_LOCAL_MODES:
        return None, "existing_local must be one of: {}".format(allowed)
    if overwrite_local is not None and overwrite_local != (mode == "overwrite"):
        return None, ("existing_local={} conflicts with overwrite_local={}; "
                      "overwrite_local is deprecated, pass only existing_local").format(
                          mode, "true" if overwrite_local else "false")
    return mode, None


def _normalise_workset_name(name):
    return " ".join(name.lower().replace("_", " ").split())


def pick_axes_levels_workset(names):
    """Return the workset name to keep open in the retry, or None.

    Matching is case-insensitive, treats "_" as a space and collapses whitespace; the
    marker must be a substring. An exact normalised match wins, otherwise the first
    containing name in input order.
    """
    first = None
    for name in names:
        if not name or not isinstance(name, _TEXT_TYPE):
            continue
        normal = _normalise_workset_name(name)
        if normal == AXES_LEVELS_WORKSET_MARKER:
            return name
        if first is None and AXES_LEVELS_WORKSET_MARKER in normal:
            first = name
    return first


# ---------------------------------------------------------------- honest outcomes
#
# One schema and one classifier for what a mutating route reports (phase 4; D-03,
# D-04). The helpers are pure on purpose: a route module cannot be imported under
# CPython, so the decision of "success, partial, failed or rolled back" lives here
# where a truth table can pin it. Routes call finalize_outcome() with what
# commit_and_report() returned and answer with the (payload, http_status) it gives.


def classify_outcome(committed, n_succeeded, n_failed):
    """Return (status, http_status) for one finished transaction (D-04).

    The one place that decides the reply status and HTTP code, so no route can
    drift into its own convention. A transaction that did not commit is
    ("rolled_back", 409) whatever the counts say: the 409 is load-bearing because
    the bridge turns only non-200 replies into errors the model can see, so a
    rollback must never be a 200. A commit with no failed item is
    ("success", 200), which includes the empty call (0 succeeded, 0 failed). A
    commit where some items worked and some did not is ("partial", 200), and a
    commit where every attempted item failed is ("failed", 422).
    """
    if not committed:
        return "rolled_back", 409
    if n_failed == 0:
        return "success", 200
    if n_succeeded > 0:
        return "partial", 200
    return "failed", 422


def build_outcome(transaction_status, requested, succeeded, failed, revit_failures):
    """Return the `outcome` block (D-03): exactly five keys, in the order given.

    `requested` is the route's own integer count (or None) and is never derived
    here. `succeeded` and `revit_failures` become new lists with no sort and no
    de-duplication, so a repeated input id is reported as many times as the route
    handled it. Each failed entry is reduced to {"item", "reason"}: any other key a
    route attached (a request body, a secret, a traceback) is dropped, so nothing
    but the item and its reason text can ride along (D-07).
    """
    reduced = []
    for entry in (failed or []):
        reduced.append({
            "item": entry["item"],
            "reason": sanitize_value(entry.get("reason")),
        })
    return {
        "transaction_status": transaction_status,
        "requested": requested,
        "succeeded": list(succeeded or []),
        "failed": reduced,
        "revit_failures": list(revit_failures or []),
    }


def finalize_outcome(commit_result, data, requested, succeeded, failed):
    """Return (payload, http_status) for a route that just called commit_and_report().

    `commit_result` is the dict commit_and_report() returned; only a committed
    flag that is exactly True counts as committed. `data` is the route's own
    reply body and is never mutated.

    On 409 the payload is the existing rollback contract (status, message,
    top-level transaction_status and failures) plus an `outcome` whose succeeded
    is []. The route's legacy keys are left out on purpose: they would name
    elements, ids and counts that no longer exist in the model. On 200 and 422
    the payload is a copy of `data` with `status` set and `outcome` added; a 422
    also carries a truthy `error`, which is what makes the model see it.
    """
    committed = commit_result.get("committed") is True
    transaction_status = commit_result.get("transaction_status")
    failures = commit_result.get("failures") or []
    status, http_status = classify_outcome(committed, len(succeeded), len(failed))
    if http_status == 409:
        return {
            "status": status,
            "message": (
                "Revit rolled the transaction back at Commit() "
                "(transaction_status: {}); no change from this call was kept in the "
                "model. 'failures' lists what Revit reported.".format(transaction_status)),
            "transaction_status": transaction_status,
            "failures": list(failures),
            "outcome": build_outcome(transaction_status, requested, [], failed, failures),
        }, http_status
    payload = dict(data)
    payload["status"] = status
    payload["outcome"] = build_outcome(
        transaction_status, requested, succeeded, failed, failures)
    if http_status == 422:
        count = requested if requested is not None else len(failed)
        payload["error"] = (
            "None of the {} requested item(s) succeeded; each item and its reason "
            "is in outcome.failed".format(count))
    return payload, http_status


def transaction_status_of(transaction):
    """Return str(transaction.GetStatus()), or None when there is no transaction or it cannot be read.

    Used on the exception path (D-14): a route that raised after Commit() must say
    what the transaction really is instead of hiding a model change behind a bare
    500. GetStatus is read inside try/except because its behaviour after Commit is
    an assumption (A2); if Revit refuses, null is the honest answer, not a guess.
    """
    if transaction is None:
        return None
    try:
        return str(transaction.GetStatus())
    except Exception:
        return None


def exception_outcome(transaction, requested=None, succeeded=None, failed=None):
    """Return the `outcome` block for a reply built after an exception (D-14).

    `transaction_status` is read from the transaction itself. `succeeded` is kept
    only when that status is "Committed": a committed-then-raised call really did
    change the model, so its items must show, while an uncommitted or unreadable
    transaction changed nothing and reports an empty list. `failed` goes through
    build_outcome's item-and-reason reduction like every other outcome.
    """
    status = transaction_status_of(transaction)
    kept = list(succeeded or []) if status == "Committed" else []
    return build_outcome(status, requested, kept, failed or [], [])
