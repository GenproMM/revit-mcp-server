# -*- coding: utf-8 -*-
"""Structured audit log of what the bridge really did (Phase 6).

CPython side only: nothing here may run inside Revit. One writer per server
process. The outcome of an entry comes from the bridge's provenance and the
reply body, never from format_response. Nothing is written to stdout (it is the
stdio protocol stream): the only output paths are the log file and, once per
process, one stderr line that names an exception class. Nothing is created until
the first entry: importing this module makes no directory, thread or file. A
failure in here never breaks a tool call (D-18).

Pieces: the per-call state (a contextvar set by the wrapper that
install_audited_tools puts around every registered tool), the pure entry
builder, and a queue-backed roll-forward JSONL writer.

Schema 1
--------
One JSON object per line. SCHEMA_1_FIELDS lists every key this phase writes;
ALWAYS_PRESENT_FIELDS the keys every entry carries (a None value means "not
known", never "none happened"). All lengths count Python str code points.

  ts, schema, call_id, tool       UTC time (ms), 1, the tool call's uuid4, tool name or null
  route, route_arg, method        "/first_segment/", the tail after it (capped), GET or POST
  mutation                        false only for GET and the seven open POST reads (D-03)
  kind, http_status               the bridge's provenance kind and the reply's HTTP code
  outcome                         one of OUTCOME_LABELS, from provenance and the reply's own
                                  status, never from format_response (D-01, AUDIT-03)
  reason                          rejected_*: the verdict word or refusal code (never a file list)
  reply_status                    unrecognized only: the reply's raw top-level status or null
  outcome_block_missing           true when a mutating 200/409/422 reply has no outcome block
                                  (except ROUTES_WITHOUT_OUTCOME_BLOCK); otherwise absent
  transaction_status, requested,  copied from the reply's outcome block whatever the HTTP code
  succeeded, failed,              (a 500 after Commit() still shows Committed); succeeded keeps
  revit_failures                  the first SUCCEEDED_MAX in order, failed the first FAILED_MAX as
                                  {item, reason}, revit_failures the first REVIT_FAILURES_MAX
  succeeded_count, failed_count   the true totals before capping
  process, corroborated           the verified Revit process (pid, port, session_token,
                                  revit_version), only for provenance kind received
  requested_target                the {address, pid} the call asked for, whatever the kind
  document                        {token, title, path} per D-09 or null; document.path is the
                                  path Revit reports (doc.PathName): for a workshared local copy
                                  that is the local file, and no route in this release reports
                                  the central-model path (written as it is, not looked up)
  document_source                 reply_document | documents_changed | request_argument |
                                  handshake_active_title | none
  document_role                   used (the route reported it) | addressed (named by the request
                                  or the handshake, or /execute_code/) | null
  documents_changed               the reply's list, reduced, first DOCUMENTS_CHANGED_MAX
  observed_active_document        the reply's observation, kept apart from document
  document_scope                  /execute_code/ only: the reply's notice (NOTICE_MAX)
  cancelled                       true only for a send the client cancelled after it was sent
  server_pid, duration_ms         the writing server process and the call's wall time

  windows_user                    DOMAIN\\user of this server process (D-10); no computer name, MCP
                                  client, session id or address is written
  args                            the tool's arguments without ctx and None values (D-11); strings
                                  cut at ARG_STRING_MAX, lists at ARG_LIST_MAX items, nesting at
                                  ARG_DEPTH_MAX; a value under a key matching SECRET_ARG_KEY is
                                  REDACTED; the HTTP body and read results are never written
  args_truncated                  only when something was cut: {arg, length} for a string,
                                  {arg, count} for a list (arg is a dotted path)
  code_length, code_sha256        execute_revit_code only: the full code's length and the SHA-256
                                  of its UTF-8 bytes; args.code holds the first CODE_MAX points
  user_request                    the user's message as the ASSISTANT reported it (the server never
                                  sees the user's prompt), redacted, cut at USER_REQUEST_MAX
  user_request_length             the original length, or null when missing
  user_request_missing            true when the argument was absent or blank (D-12)
  user_request_source             "assistant" when a value was supplied, else null; unverified

Retention (D-16, AUDIT-07)
--------------------------
Growth is bounded from the first write. A line that would take the active segment past
SEGMENT_MAX_BYTES (10 MiB) starts a new segment (a single larger line is written whole into
a fresh one); each server process keeps its newest SEGMENT_KEEP (10) segments. When the writer
starts, prune() deletes audit-*.jsonl files older than REVIT_MCP_AUDIT_MAX_AGE_DAYS (whole days,
default 180) and then the oldest until the directory total is at or below
REVIT_MCP_AUDIT_MAX_TOTAL_MB (MiB = 1024 * 1024 bytes, default 500). A bad value (empty,
non-numeric, zero or negative) means the default. prune() touches only regular files named
audit-*.jsonl directly inside the audit directory, and runs before this process's own segment
exists.

Lengths and caps count code points of the Python str, not UTF-8 bytes. Redaction happens before
any cut (_clip), once more over the whole entry (redact) and a last time on the finished line
(serialize_entry): the configured secret, raw and JSON-escaped, never reaches a file (D-13).
"""

import atexit
import contextvars
import dataclasses
import fnmatch
import functools
import getpass
import hashlib
import inspect
import json
import logging
import logging.handlers
import math
import os
import queue
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, Optional

SCHEMA_VERSION = 1
LOGGER_NAME = "revit_mcp.audit"
AUDIT_DIR_ENV = "REVIT_MCP_AUDIT_DIR"
SEGMENT_MAX_BYTES = 10 * 1024 * 1024
SEGMENT_KEEP = 10
MAX_AGE_DAYS_ENV = "REVIT_MCP_AUDIT_MAX_AGE_DAYS"
MAX_TOTAL_MB_ENV = "REVIT_MCP_AUDIT_MAX_TOTAL_MB"
DEFAULT_MAX_AGE_DAYS = 180
DEFAULT_MAX_TOTAL_MB = 500
AUDIT_FILE_GLOB = "audit-*.jsonl"
QUEUE_MAX = 10000
ROUTE_ARG_MAX = 200
REDACTED = "[REDACTED]"
ARG_STRING_MAX = 500
ARG_LIST_MAX = 200
ARG_DEPTH_MAX = 4
USER_REQUEST_MAX = 2000
CODE_MAX = 8192
CODE_TOOL = "execute_revit_code"
CODE_ARG = "code"
USER_REQUEST_SOURCE = "assistant"
SECRET_ARG_KEY = re.compile(r"secret|token|password|api_key", re.IGNORECASE)

# The POST routes that only read (D-03). A copy of revit_mcp/trust.py
# OPEN_POST_READ_ROUTES: the payload ships no revit_mcp/ package, so this half
# cannot import it. tests/unit/test_audit_entry.py pins the copy equal.
OPEN_POST_READ_ROUTES = frozenset({
    "/document_summary/",
    "/document_levels/",
    "/model_worksets/",
    "/material_quantities/",
    "/clash_check/",
    "/ai_filter/",
    "/list_category_parameters/",
})

# The wording the model sees (D-12). The short form rides in every tool's schema; the full
# rule is stated once, in SERVER_INSTRUCTIONS. tests/unit/test_audit_registration.py pins both.
USER_REQUEST_DESCRIPTION = (
    "The user's latest message, copied verbatim. If that message is only a short confirmation "
    "(for example 'да', 'согласую', 'делай', 'ок'), copy the last substantive request before it. "
    "Optional; recorded in the local audit log as reported by you."
)

SERVER_INSTRUCTIONS = (
    "Every tool of this server accepts an optional user_request argument. Put the user's latest "
    "message in it, word for word. When that message is only a confirmation such as \"да\", "
    "\"согласую\", \"делай\", \"ок\", \"yes\" or \"go ahead\", put the last substantive request "
    "before it instead. The server cannot see the conversation: it records the value in the "
    "local audit log as reported by the assistant, unverified. Omitting it never blocks a call."
)

_OUTCOME_STATUSES = ("success", "partial", "failed", "rolled_back")

OUTCOME_LABELS = (
    "success", "partial", "failed", "rolled_back", "rejected_auth", "rejected_integrity",
    "rejected_document", "error", "unknown", "no_reply", "unverified_reply", "unrecognized",
)

# The refusal codes of revit_mcp/identity.py (the document-* constants and
# no-open-document), copied for the same reason as OPEN_POST_READ_ROUTES and pinned
# equal by tests/unit/test_audit_entry.py. A bare 404 or 412 is not on this list: a 404
# also means "element not found" on other routes.
DOCUMENT_REFUSAL_CODES = frozenset({
    "document-identity-unavailable",
    "document-identity-ambiguous",
    "document-active-unknown",
    "document-selector-invalid",
    "document-token-stale",
    "document-closed",
    "document-token-unknown",
    "document-not-active",
    "no-open-document",
    "document-selector-required",
    "document-registry-unavailable",
})

# The one gated POST route whose reply carries no outcome block (Phase 4 left
# /activate_document/ without one on purpose). Every other mutating reply that lacks
# the block is flagged, so a regression shows instead of being masked (D-08).
ROUTES_WITHOUT_OUTCOME_BLOCK = frozenset({"/activate_document/"})

# GET /status/ is logged only inside these tool calls. The process tools and the identity
# handshake call /status/ through the bridge too; that is bridge housekeeping, not a call
# the user's tool made, so it writes nothing (D-02, research Pitfall 8).
AUDITED_STATUS_TOOLS = frozenset({"get_revit_status"})

SUCCEEDED_MAX = 500
FAILED_MAX = 100
REVIT_FAILURES_MAX = 50
REASON_MAX = 500
DOCUMENTS_CHANGED_MAX = 20
NOTICE_MAX = 500

SCHEMA_1_FIELDS = (
    "ts", "schema", "call_id", "tool", "route", "route_arg", "method", "mutation", "kind",
    "http_status", "outcome", "reason", "reply_status", "outcome_block_missing",
    "transaction_status", "requested", "succeeded", "succeeded_count", "failed", "failed_count",
    "revit_failures", "process", "corroborated", "requested_target", "document",
    "document_source", "document_role", "documents_changed", "observed_active_document",
    "document_scope", "cancelled", "windows_user", "args", "args_truncated", "code_length",
    "code_sha256", "user_request", "user_request_missing", "user_request_length",
    "user_request_source", "server_pid", "duration_ms",
)

ALWAYS_PRESENT_FIELDS = (
    "ts", "schema", "call_id", "tool", "route", "route_arg", "method", "mutation", "kind",
    "http_status", "outcome", "transaction_status", "requested", "succeeded", "succeeded_count",
    "failed", "failed_count", "revit_failures", "process", "corroborated", "requested_target",
    "document", "document_source", "document_role", "windows_user", "args", "user_request",
    "user_request_missing", "user_request_length", "user_request_source", "server_pid",
    "duration_ms",
)


# --------------------------------------------------------------- per-call state

@dataclasses.dataclass(frozen=True)
class CallState:
    """What one tool call is: its id, name, arguments and the reported user request."""

    call_id: str
    tool: Optional[str]
    args: dict
    user_request: Optional[str]


_CALL = contextvars.ContextVar("revit_mcp_audit_call", default=None)


def current_call() -> Optional[CallState]:
    """The tool call this task runs inside, or None outside any tool call."""
    return _CALL.get()


def anonymous_call() -> CallState:
    """The identity of a bridge call made outside any tool call: its own id, no tool."""
    return CallState(str(uuid.uuid4()), None, {}, None)


def new_call(tool: Optional[str], kwargs: Dict[str, Any], user_request: Optional[str]) -> CallState:
    """A fresh call state; the MCP context object is dropped (checked by name, no mcp import)."""
    args = dict((key, value) for key, value in kwargs.items()
                if key != "ctx" and type(value).__name__ != "Context")
    return CallState(str(uuid.uuid4()), tool, args, user_request)


# ------------------------------------------------------- registration wrapper

def _json_text(value: Any) -> Any:
    """Turn a JSON-parsed user message back into text.

    FastMCP json-parses every string argument, so a user message such as
    '{"a":1}' or '[1,2]' would reach an Optional[str] parameter as a dict or a
    list and fail validation. None and text pass through unchanged.
    """
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _wrap(fn, user_request_type):
    """Wrap one tool function: set the call state around it and advertise user_request."""
    name = getattr(fn, "__name__", repr(fn))
    if not inspect.iscoroutinefunction(fn):
        raise TypeError("tool {} is not a coroutine function; it cannot be audited".format(name))
    signature = inspect.signature(fn)
    if "user_request" in signature.parameters:
        raise ValueError("tool {} already declares a user_request parameter".format(name))
    extra = inspect.Parameter("user_request", inspect.Parameter.KEYWORD_ONLY, default=None,
                              annotation=user_request_type)

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        user_request = kwargs.pop("user_request", None)
        token = _CALL.set(new_call(fn.__name__, kwargs, user_request))
        try:
            return await fn(*args, **kwargs)
        finally:
            _CALL.reset(token)

    wrapper.__signature__ = signature.replace(
        parameters=list(signature.parameters.values()) + [extra])
    return wrapper


def install_audited_tools(mcp) -> None:
    """Wrap every tool registered on this FastMCP from now on; a second call is a no-op.

    Install it before register_tools. The wrapper sets the call state the bridge
    reads, and adds one optional keyword-only parameter, user_request, to the
    published input schema of every tool.
    """
    if getattr(mcp, "_revit_mcp_audited", False):
        return
    # Inside the function: importing the bridge or this module must not import pydantic.
    from pydantic import BeforeValidator, Field

    user_request_type = Annotated[Optional[str], BeforeValidator(_json_text),
                                  Field(description=USER_REQUEST_DESCRIPTION)]
    original_tool = mcp.tool

    def audited_tool(*args, **kwargs):
        register = original_tool(*args, **kwargs)

        def decorator(fn):
            register(_wrap(fn, user_request_type))
            return fn

        return decorator

    mcp.tool = audited_tool
    mcp._revit_mcp_audited = True


# ------------------------------------------------------------- entry building

def route_parts(endpoint: str, secret: Optional[str] = None):
    """("/first_segment/", tail or None): the route and what follows it, query string dropped.

    The secret is replaced before the tail is cut, so a cut can never leave part of it.
    """
    path = redact_text(str(endpoint), secret).split("?", 1)[0].strip("/")
    head, _, tail = path.partition("/")
    route = "/" + head + "/" if head else "/"
    tail = tail.strip("/")[:ROUTE_ARG_MAX]
    return route, (tail or None)


def is_mutation(method: str, route: str) -> bool:
    """A read is a GET or a POST to an open-read route; everything else mutates (D-03)."""
    if str(method).upper() == "GET":
        return False
    return route not in OPEN_POST_READ_ROUTES


def redact_text(text, secret):
    """``text`` with the secret and its JSON-escaped form replaced; unchanged without a secret."""
    if isinstance(secret, str) and secret and isinstance(text, str):
        text = text.replace(secret, REDACTED)
        escaped = json.dumps(secret)[1:-1]
        if escaped != secret:
            text = text.replace(escaped, REDACTED)
    return text


def _cut(text, limit, secret):
    """(clipped, original_length, was_cut): redact first, then cut to ``limit`` code points."""
    original = len(text)
    redacted = redact_text(text, secret)
    return redacted[:limit], original, len(redacted) > limit


def _clip(text, limit, secret):
    """(clipped, original_length): the one place a string is cut, always after redaction."""
    clipped, original, _cut_made = _cut(text, limit, secret)
    return clipped, original


def redact(value, secret):
    """A copy of ``value`` with the secret replaced in every string (keys included).

    Walks dicts, lists and tuples; other values pass through. No key scrub here: that
    belongs to tool arguments only (shape_args), so identity fields such as
    process.session_token are never touched.
    """
    if not (isinstance(secret, str) and secret):
        return value
    if isinstance(value, str):
        return redact_text(value, secret)
    if isinstance(value, dict):
        return dict((redact_text(key, secret) if isinstance(key, str) else key,
                     redact(item, secret)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return [redact(item, secret) for item in value]
    return value


def _text(value, limit=REASON_MAX, secret=None):
    """A str copy of value, redacted then cut to ``limit`` code points; None stays None. Never raises."""
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:
            return None
    return _clip(value, limit, secret)[0]


def _scalar(value, secret=None):
    """An id, count or flag as it is; any other value as a capped string."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _text(value, REASON_MAX, secret)


def _outcome(kind, http_status, body, mutation, secret=None):
    """(label, reason, reply_status) in the fixed precedence of D-08 and AUDIT-03.

    Provenance kind first, then HTTP 401/423, then a document refusal code, then the
    reply's own top-level status, then any other 4xx/5xx as error, then a completed
    read as success, else unrecognized. The label is never derived from the rendered
    text, from the request's intent or from recomputed counts. ``kind`` None (a call
    with no provenance) counts as received.
    """
    if kind == "unknown":
        return "unknown", None, None
    if kind == "no-reply":
        return "no_reply", None, None
    if kind == "unverified-reply":
        return "unverified_reply", None, None
    if not isinstance(body, dict):
        body = {}
    if http_status == 401:
        return "rejected_auth", _text(body.get("auth"), REASON_MAX, secret), None
    if http_status == 423:
        return "rejected_integrity", _text(body.get("integrity"), REASON_MAX, secret), None
    code = body.get("error_code")
    if isinstance(code, str) and code in DOCUMENT_REFUSAL_CODES:
        return "rejected_document", _text(code, REASON_MAX, secret), None
    status = body.get("status")
    if isinstance(status, str) and status in _OUTCOME_STATUSES:
        return status, None, None
    if isinstance(http_status, int) and http_status >= 400:
        return "error", None, None
    if http_status == 200 and not mutation:
        return "success", None, None
    return "unrecognized", None, (
        _text(status, REASON_MAX, secret) if isinstance(status, str) else None)


def _outcome_fields(body, secret=None):
    """The Phase 4 outcome block's fields, copied whatever the HTTP status.

    A 500 after Commit() still carries transaction_status Committed and its succeeded
    items: the model changed. Only these named keys are read; nothing else of the body
    enters the entry (D-11, D-13). Without a block every list and count is None.
    """
    fields = {"transaction_status": None, "requested": None, "succeeded": None,
              "succeeded_count": None, "failed": None, "failed_count": None,
              "revit_failures": None}
    if not isinstance(body, dict):
        return fields
    block = body.get("outcome")
    block = block if isinstance(block, dict) else None
    status = block.get("transaction_status") if block is not None else None
    if status is None:
        status = body.get("transaction_status")
    fields["transaction_status"] = _text(status, REASON_MAX, secret)
    if block is None:
        return fields
    requested = block.get("requested")
    fields["requested"] = requested if isinstance(requested, int) and not isinstance(
        requested, bool) else None
    succeeded = block.get("succeeded")
    succeeded = succeeded if isinstance(succeeded, list) else []
    fields["succeeded"] = [_scalar(item, secret) for item in succeeded[:SUCCEEDED_MAX]]
    fields["succeeded_count"] = len(succeeded)
    failed = block.get("failed")
    failed = failed if isinstance(failed, list) else []
    reduced = []
    for entry in failed[:FAILED_MAX]:
        if isinstance(entry, dict):
            reduced.append({"item": _scalar(entry.get("item"), secret),
                            "reason": _text(entry.get("reason"), REASON_MAX, secret)})
        else:
            reduced.append({"item": _scalar(entry, secret), "reason": None})
    fields["failed"] = reduced
    fields["failed_count"] = len(failed)
    failures = block.get("revit_failures")
    failures = failures if isinstance(failures, list) else []
    fields["revit_failures"] = [_text(item, REASON_MAX, secret)
                                for item in failures[:REVIT_FAILURES_MAX]]
    return fields


def _triplet(descriptor, secret=None):
    """{token, title, path} of a document descriptor, or None when it names nothing.

    Revit stores the token under the key "document" (identity._descriptor); the entry
    calls it token. Never raises.
    """
    if not isinstance(descriptor, dict):
        return None
    token = descriptor.get("document")
    if not isinstance(token, str):
        token = descriptor.get("token")
    title, path = descriptor.get("title"), descriptor.get("path")
    triplet = {"token": _text(token, REASON_MAX, secret) if isinstance(token, str) else None,
               "title": _text(title, REASON_MAX, secret) if isinstance(title, str) else None,
               "path": _text(path, REASON_MAX, secret) if isinstance(path, str) else None}
    if triplet["token"] is None and triplet["title"] is None and triplet["path"] is None:
        return None
    return triplet


def _changed_entry(descriptor, secret=None):
    entry = _triplet(descriptor, secret) or {"token": None, "title": None, "path": None}
    for key in ("role", "changed", "saved", "is_family_document"):
        entry[key] = _scalar(descriptor.get(key), secret)
    return entry


def document_of(route, body, args, active_title_hint, secret=None):
    """(document, document_source, document_role, extras) by the D-09 priority.

    The reply's own document descriptor, then its documents_changed list (the project
    entry first), then the tool's document argument, then the active title the
    handshake reported just before the send, then nothing. Only the first two are
    attributed by the route; the others are labelled lesser sources with role
    "addressed". /execute_code/ is always "addressed" and never gets a changed
    document (Phase 2 D-15). ``extras`` holds documents_changed,
    observed_active_document and document_scope when the reply carries them.
    """
    body = body if isinstance(body, dict) else {}
    args = args if isinstance(args, dict) else {}
    execute_code = route == "/execute_code/"
    changed = body.get("documents_changed")
    entries = [item for item in changed if isinstance(item, dict)] if (
        isinstance(changed, list) and not execute_code) else None
    extras = {}
    if entries is not None:
        extras["documents_changed"] = [_changed_entry(item, secret)
                                       for item in entries[:DOCUMENTS_CHANGED_MAX]]
    observed = _triplet(body.get("observed_active_document"), secret)
    if observed is not None:
        extras["observed_active_document"] = observed
    if execute_code and isinstance(body.get("document_scope"), str):
        extras["document_scope"] = _text(body["document_scope"], NOTICE_MAX, secret)

    document, source, role = _triplet(body.get("document"), secret), "reply_document", "used"
    if document is None:
        chosen = None
        if entries:
            chosen = next((item for item in entries if item.get("role") == "project"), None)
            if chosen is None:
                chosen = next((item for item in entries if _triplet(item) is not None), None)
        document, source, role = _triplet(chosen, secret), "documents_changed", "used"
    if document is None:
        selector = args.get("document")
        if isinstance(selector, str) and selector:
            document = {"token": _text(selector, REASON_MAX, secret), "title": None, "path": None}
        source, role = "request_argument", "addressed"
    if document is None:
        if isinstance(active_title_hint, str) and active_title_hint:
            document = {"token": None, "title": _text(active_title_hint, REASON_MAX, secret), "path": None}
        source, role = "handshake_active_title", "addressed"
    if document is None:
        source, role = "none", None
    if execute_code and document is not None:
        role = "addressed"
    return document, source, role, extras


def _outcome_block_missing(mutation, kind, http_status, route, body):
    if not mutation or kind not in (None, "received"):
        return False
    if http_status not in (200, 409, 422) or route in ROUTES_WITHOUT_OUTCOME_BLOCK:
        return False
    return not (isinstance(body, dict) and isinstance(body.get("outcome"), dict))


def _shape_value(value, path, depth, secret, truncated):
    """One argument value reduced to JSON-safe, capped, redacted form; cuts go to ``truncated``."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _type_name(value)
    if isinstance(value, str):
        clipped, original, was_cut = _cut(value, ARG_STRING_MAX, secret)
        if was_cut:
            truncated.append({"arg": path, "length": original})
        return clipped
    if isinstance(value, dict):
        if depth > ARG_DEPTH_MAX:
            return _type_name(value)
        shaped = {}
        for key, item in value.items():
            name = redact_text(key if isinstance(key, str) else str(key), secret)
            if SECRET_ARG_KEY.search(name):
                shaped[name] = REDACTED
            else:
                shaped[name] = _shape_value(item, path + "." + name, depth + 1, secret, truncated)
        return shaped
    if isinstance(value, (list, tuple)):
        if depth > ARG_DEPTH_MAX:
            return _type_name(value)
        if len(value) > ARG_LIST_MAX:
            truncated.append({"arg": path, "count": len(value)})
        return [_shape_value(item, "{}[{}]".format(path, index), depth + 1, secret, truncated)
                for index, item in enumerate(value[:ARG_LIST_MAX])]
    return _type_name(value)


def shape_args(tool, args, secret):
    """(shaped, args_truncated, code_fields) for one tool call's arguments (D-04, D-11).

    ctx and None values are dropped; a value under a key matching SECRET_ARG_KEY is
    REDACTED whatever it is; strings are redacted and then cut at ARG_STRING_MAX code
    points, lists keep their first ARG_LIST_MAX items, nesting stops at ARG_DEPTH_MAX
    (deeper values become their type name) and any non-JSON value becomes its type name.
    For execute_revit_code the code is cut at CODE_MAX instead, and ``code_fields``
    carries its full length and the SHA-256 of its original UTF-8 bytes (hashed before
    redaction: the digest identifies what ran). Never raises on odd input.
    """
    shaped, truncated, code_fields = {}, [], {}
    for key, value in (args if isinstance(args, dict) else {}).items():
        name = redact_text(key if isinstance(key, str) else str(key), secret)
        if name == "ctx" or value is None:
            continue
        if SECRET_ARG_KEY.search(name):
            shaped[name] = REDACTED
        elif tool == CODE_TOOL and name == CODE_ARG and isinstance(value, str):
            shaped[name], length, _cut_made = _cut(value, CODE_MAX, secret)
            code_fields = {
                "code_length": length,
                "code_sha256": hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest(),
            }
        else:
            shaped[name] = _shape_value(value, name, 1, secret, truncated)
    return shaped, truncated, code_fields


def shape_user_request(text, secret):
    """The four user_request fields; a blank or absent value is recorded as missing (D-12).

    The text is what the assistant reported: the server never sees the user's prompt,
    so a supplied value is labelled with the source "assistant" and nothing more.
    """
    if text is not None and not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            text = None
    if text is None or not text.strip():
        return {"user_request": None, "user_request_missing": True,
                "user_request_length": None, "user_request_source": None}
    clipped, original = _clip(text, USER_REQUEST_MAX, secret)
    return {"user_request": clipped, "user_request_missing": False,
            "user_request_length": original, "user_request_source": USER_REQUEST_SOURCE}


_WINDOWS_USER: Optional[str] = None


def windows_user() -> str:
    """DOMAIN\\user of this process (D-10), computed once; never raises.

    USERDOMAIN and USERNAME when both are set, else getpass.getuser(), else "unknown".
    Nothing else about the person or the machine is looked up.
    """
    global _WINDOWS_USER
    if _WINDOWS_USER is None:
        try:
            domain, user = os.environ.get("USERDOMAIN"), os.environ.get("USERNAME")
            value = (domain + "\\" + user) if (domain and user) else getpass.getuser()
        except Exception:
            value = None
        _WINDOWS_USER = value if (isinstance(value, str) and value) else "unknown"
    return _WINDOWS_USER


def build_entry(call, method, endpoint, provenance, body, *, duration_ms, now, server_pid,
                active_title_hint=None, cancelled=False, windows_user=None, secret=None):
    """One audit entry as a dict, or None for a call that never left this process (D-02).

    Pure: no I/O, no clock, no environment (windows_user and secret arrive as
    arguments). ``provenance`` is the bridge's meta dict, ``body`` the parsed reply
    object (or None). The outcome is the reply's own statement under a fixed
    precedence (see _outcome), never guessed from rendered text. Only named fields of
    the body are copied: no message or error text, no 423 file list, no read results.
    Every string is redacted before it is cut and the finished entry is redacted once
    more (D-13); process and requested_target are the writer's own fields and are
    never scrubbed by key.
    """
    kind = provenance.get("kind")
    if kind == "not-sent":
        return None
    received = kind in (None, "received")
    reply = body if received and isinstance(body, dict) else None
    route, route_arg = route_parts(endpoint, secret)
    mutation = is_mutation(method, route)
    http_status = provenance.get("http_status")
    process = provenance.get("process")
    if isinstance(process, dict):
        process = {"pid": process.get("pid"), "port": process.get("actual_port"),
                   "session_token": process.get("session_token"),
                   "revit_version": process.get("revit_version")}
    else:
        process = None
    requested_target = provenance.get("requested")
    if isinstance(requested_target, dict):
        requested_target = {"address": requested_target.get("address"),
                            "pid": requested_target.get("pid")}
    else:
        requested_target = None
    label, reason, reply_status = _outcome(kind, http_status, reply, mutation, secret)
    document, document_source, document_role, extras = document_of(
        route, reply, call.args, active_title_hint, secret)
    entry = {
        "ts": now.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "schema": SCHEMA_VERSION,
        "call_id": call.call_id,
        "tool": call.tool,
        "route": route,
        "route_arg": route_arg,
        "method": method,
        "mutation": mutation,
        "kind": kind,
        "http_status": http_status,
        "outcome": label,
    }
    if reason is not None:
        entry["reason"] = reason
    if label == "unrecognized":
        entry["reply_status"] = reply_status
    if _outcome_block_missing(mutation, kind, http_status, route, reply):
        entry["outcome_block_missing"] = True
    entry.update(_outcome_fields(reply, secret))
    entry.update({
        "process": process,
        "corroborated": provenance.get("corroborated"),
        "requested_target": requested_target,
        "document": document,
        "document_source": document_source,
        "document_role": document_role,
    })
    entry.update(extras)
    if cancelled is True:
        entry["cancelled"] = True
    shaped_args, args_truncated, code_fields = shape_args(call.tool, call.args, secret)
    entry["windows_user"] = windows_user
    entry["args"] = shaped_args
    if args_truncated:
        entry["args_truncated"] = args_truncated
    entry.update(code_fields)
    entry.update(shape_user_request(call.user_request, secret))
    entry["server_pid"] = server_pid
    entry["duration_ms"] = duration_ms
    return redact(entry, secret)


def _type_name(value):
    return type(value).__name__


def serialize_entry(entry: dict, secret: Optional[str]) -> str:
    """One JSON line, the secret (raw and JSON-escaped) replaced on the finished text.

    json.dumps escapes control characters, so one entry is always one line.
    """
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"), default=_type_name)
    if isinstance(secret, str) and secret:
        line = line.replace(secret, REDACTED).replace(json.dumps(secret)[1:-1], REDACTED)
    return line


# ---------------------------------------------------------------------- writer

_warned = False


def _warn_once(exc) -> None:
    """The first call per process says an entry was dropped, naming only the exception class."""
    global _warned
    if _warned:
        return
    _warned = True
    try:
        name = _type_name(exc) if isinstance(exc, BaseException) else "Exception"
        sys.stderr.write("revit-mcp: audit log entry dropped (" + name + ")\n")
    except Exception:
        pass


class SegmentHandler(logging.handlers.BaseRotatingHandler):
    """Roll-forward JSONL file: a new segment instead of a rename.

    RotatingFileHandler renames the active file, and on Windows that fails (and
    the record is lost) while any reader holds it. This handler only ever opens
    the next segment and removes its own oldest one.
    """

    def __init__(self, directory, stem, max_bytes, keep):
        self.directory, self.stem = directory, stem
        self.max_bytes, self.keep, self.seq = max_bytes, keep, 1
        super().__init__(self._segment(1), "a", encoding="utf-8", delay=True)

    def _segment(self, n):  # never `_name`: logging.Handler owns that attribute
        return os.path.join(self.directory,
                            self.stem + (".jsonl" if n == 1 else ".%04d.jsonl" % n))

    def _open(self):
        # LF endings on Windows, and a lone surrogate must not raise.
        return open(self.baseFilename, self.mode, encoding="utf-8", errors="backslashreplace",
                    newline="\n")

    def shouldRollover(self, record):
        try:
            size = os.path.getsize(self.baseFilename)
        except OSError:
            size = 0
        return size > 0 and size + len(record.getMessage().encode("utf-8")) + 1 > self.max_bytes

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        self.seq += 1
        self.baseFilename = os.path.abspath(self._segment(self.seq))
        old = self.seq - self.keep
        if old >= 1:
            try:
                os.remove(self._segment(old))
            except OSError:
                pass

    def handleError(self, record):
        _warn_once(sys.exc_info()[1])


class _QueueHandler(logging.handlers.QueueHandler):
    def handleError(self, record):
        _warn_once(sys.exc_info()[1])


class _Sink(object):
    def __init__(self, logger, queue_, listener, handler):
        self.logger, self.queue = logger, queue_
        self.listener, self.handler = listener, handler


_WRITER: Optional[_Sink] = None
_WRITER_LOCK = threading.Lock()
_atexit_registered = False


def audit_dir() -> str:
    """The local per-user directory for audit files (D-14)."""
    override = os.environ.get(AUDIT_DIR_ENV)
    if override:
        return override
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "RevitMCP", "audit")
    return os.path.join(os.path.expanduser("~"), ".revit-mcp", "audit")


def _positive_int_env(name: str, default: int) -> int:
    """The environment variable as a whole number above zero, else ``default``. Never raises."""
    try:
        text = os.environ.get(name)
        if text is None:
            return default
        text = text.strip()
        if not (text.isascii() and text.isdigit()):
            return default
        value = int(text)
        return value if value > 0 else default
    except Exception:
        return default


def retention_settings():
    """(max_age_seconds, max_total_bytes) from the environment; MB means MiB (1024 * 1024 bytes)."""
    days = _positive_int_env(MAX_AGE_DAYS_ENV, DEFAULT_MAX_AGE_DAYS)
    megabytes = _positive_int_env(MAX_TOTAL_MB_ENV, DEFAULT_MAX_TOTAL_MB)
    return days * 86400, megabytes * 1024 * 1024


def prune(directory, now, max_age_seconds, max_total_bytes):
    """Delete old, then surplus audit files; return the names this call deleted (D-16, AUDIT-07).

    Touches only regular files directly inside ``directory`` whose names match
    AUDIT_FILE_GLOB (case-sensitive, no recursion, symlinks skipped), so a directory
    that also holds other data loses nothing else. A file older than
    ``max_age_seconds`` (strictly: a file aged exactly the limit stays) goes first; then,
    oldest mtime first, files go until the summed size of those left is at or below
    ``max_total_bytes``. Sizes are whole bytes from os.path.getsize, ages are seconds
    against mtime, nothing is rounded. A file that cannot be deleted (another live server
    holds it) is skipped and still counts toward the total; one that is already gone
    (another server pruning at the same time) is not counted and not reported as ours.
    Never raises.
    """
    deleted = []
    try:
        candidates = []
        for name in os.listdir(directory):
            if not fnmatch.fnmatchcase(name, AUDIT_FILE_GLOB):
                continue
            path = os.path.join(directory, name)
            try:
                if os.path.islink(path) or not os.path.isfile(path):
                    continue
                candidates.append((os.path.getmtime(path), name, path, os.path.getsize(path)))
            except OSError:
                continue
        candidates.sort(key=lambda item: (item[0], item[1]))

        def remove(path):
            """(gone, ours): gone afterwards, and removed by this call rather than by someone else."""
            try:
                os.remove(path)
                return True, True
            except FileNotFoundError:
                return True, False
            except OSError:
                return False, False

        remaining = []
        for mtime, name, path, size in candidates:
            if now - mtime > max_age_seconds:
                gone, ours = remove(path)
                if ours:
                    deleted.append(name)
                if gone:
                    continue
            remaining.append((mtime, name, path, size))
        total = sum(item[3] for item in remaining)
        for mtime, name, path, size in remaining:
            if total <= max_total_bytes:
                break
            gone, ours = remove(path)
            if ours:
                deleted.append(name)
            if gone:
                total -= size
    except Exception:
        pass
    return deleted


def _writer() -> logging.Logger:
    """The audit logger; the directory, listener thread and file appear on the first call."""
    global _WRITER, _atexit_registered
    with _WRITER_LOCK:
        if _WRITER is None:
            directory = audit_dir()
            os.makedirs(directory, exist_ok=True)
            try:  # before this process's own segment exists, so it can never delete it
                prune(directory, time.time(), *retention_settings())
            except Exception:
                pass
            stem = "audit-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") \
                + "-" + str(os.getpid())
            handler = SegmentHandler(directory, stem, SEGMENT_MAX_BYTES, SEGMENT_KEEP)
            handler.setFormatter(logging.Formatter("%(message)s"))
            pending = queue.Queue(QUEUE_MAX)
            queue_handler = _QueueHandler(pending)
            listener = logging.handlers.QueueListener(pending, handler)
            listener.start()
            logger = logging.getLogger(LOGGER_NAME)
            logger.propagate = False
            logger.setLevel(logging.INFO)
            for existing in list(logger.handlers):
                logger.removeHandler(existing)
            logger.addHandler(queue_handler)
            _WRITER = _Sink(logger, pending, listener, handler)
            if not _atexit_registered:
                atexit.register(_shutdown)
                _atexit_registered = True
        return _WRITER.logger


def record_call(call, method, endpoint, provenance, body, *, duration_ms, secret,
                active_title_hint=None, cancelled=False):
    """Write one entry for a finished bridge call; return the entry, or None. Never raises (D-18)."""
    try:
        entry = build_entry(call, method, endpoint, provenance, body, duration_ms=duration_ms,
                            now=datetime.now(timezone.utc), server_pid=os.getpid(),
                            active_title_hint=active_title_hint, cancelled=cancelled,
                            windows_user=windows_user(), secret=secret)
        if entry is None:
            return None
        # The message is the finished line: QueueHandler would stringify a dict.
        _writer().info(serialize_entry(entry, secret))
        return entry
    except Exception as exc:
        _warn_once(exc)
        return None


def flush(timeout: float = 5.0) -> bool:
    """Wait until every queued entry reached the file; False when the deadline passed first."""
    sink = _WRITER
    if sink is None:
        return True
    deadline = time.monotonic() + timeout
    while sink.queue.unfinished_tasks:
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.005)
    try:
        sink.handler.flush()
    except Exception:
        pass
    return True


def _shutdown() -> None:
    """Stop the listener (it drains the queue first) and close the file. Never raises."""
    sink = _WRITER
    if sink is None:
        return
    try:
        sink.listener.stop()
    except Exception:
        pass
    try:
        sink.handler.close()
    except Exception:
        pass


def _reset() -> None:
    """Forget the writer, the warn-once flag and the cached Windows user. For tests only."""
    global _WRITER, _warned, _WINDOWS_USER
    _shutdown()
    with _WRITER_LOCK:
        logger = logging.getLogger(LOGGER_NAME)
        for existing in list(logger.handlers):
            logger.removeHandler(existing)
        _WRITER = None
    _warned = False
    _WINDOWS_USER = None
