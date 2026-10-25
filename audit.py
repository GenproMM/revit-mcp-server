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
"""

import atexit
import contextvars
import dataclasses
import functools
import inspect
import json
import logging
import logging.handlers
import os
import queue
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
QUEUE_MAX = 10000
ROUTE_ARG_MAX = 200
REDACTED = "[REDACTED]"

# The POST routes that only read (D-03). A copy of revit_mcp/trust.py
# OPEN_POST_READ_ROUTES: the payload ships no revit_mcp/ package, so this half
# cannot import it. 06-02 pins the copy equal by test.
OPEN_POST_READ_ROUTES = frozenset({
    "/document_summary/",
    "/document_levels/",
    "/model_worksets/",
    "/material_quantities/",
    "/clash_check/",
    "/ai_filter/",
    "/list_category_parameters/",
})

USER_REQUEST_DESCRIPTION = (
    "The user's latest message, copied verbatim; if it is only a short confirmation such as "
    "'да', 'согласую', 'делай' or 'ок', copy the last substantive request before it. "
    "Recorded in the local audit log; optional."
)

_OUTCOME_STATUSES = ("success", "partial", "failed", "rolled_back")


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

def route_parts(endpoint: str):
    """("/first_segment/", tail or None): the route and what follows it, query string dropped."""
    path = str(endpoint).split("?", 1)[0].strip("/")
    head, _, tail = path.partition("/")
    route = "/" + head + "/" if head else "/"
    tail = tail.strip("/")[:ROUTE_ARG_MAX]
    return route, (tail or None)


def is_mutation(method: str, route: str) -> bool:
    """A read is a GET or a POST to an open-read route; everything else mutates (D-03)."""
    if str(method).upper() == "GET":
        return False
    return route not in OPEN_POST_READ_ROUTES


def _outcome_label(kind, http_status, body, mutation):
    if kind == "unknown":
        return "unknown"
    if kind == "no-reply":
        return "no_reply"
    if kind == "unverified-reply":
        return "unverified_reply"
    status = body.get("status") if isinstance(body, dict) else None
    if status in _OUTCOME_STATUSES:
        return status
    if isinstance(http_status, int) and http_status >= 400:
        return "error"
    if http_status == 200 and not mutation:
        return "success"
    return "unrecognized"


def build_entry(call, method, endpoint, provenance, body, *, duration_ms, now, server_pid):
    """One audit entry as a dict, or None for a call that never left this process (D-02).

    Pure: no I/O and no clock. ``provenance`` is the bridge's meta dict, ``body``
    the parsed reply object (or None). The outcome is read from the reply's own
    status, never guessed from rendered text.
    """
    kind = provenance.get("kind")
    if kind == "not-sent":
        return None
    route, route_arg = route_parts(endpoint)
    mutation = is_mutation(method, route)
    http_status = provenance.get("http_status")
    process = provenance.get("process")
    if isinstance(process, dict):
        process = {"pid": process.get("pid"), "port": process.get("actual_port"),
                   "session_token": process.get("session_token"),
                   "revit_version": process.get("revit_version")}
    else:
        process = None
    return {
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
        "outcome": _outcome_label(kind, http_status, body, mutation),
        "process": process,
        "corroborated": provenance.get("corroborated"),
        "server_pid": server_pid,
        "duration_ms": duration_ms,
    }


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


def _writer() -> logging.Logger:
    """The audit logger; the directory, listener thread and file appear on the first call."""
    global _WRITER, _atexit_registered
    with _WRITER_LOCK:
        if _WRITER is None:
            directory = audit_dir()
            os.makedirs(directory, exist_ok=True)
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


def record_call(call, method, endpoint, provenance, body, *, duration_ms, secret):
    """Write one entry for a finished bridge call; return the entry, or None. Never raises (D-18)."""
    try:
        entry = build_entry(call, method, endpoint, provenance, body, duration_ms=duration_ms,
                            now=datetime.now(timezone.utc), server_pid=os.getpid())
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
    """Forget the writer and the warn-once flag. For tests only."""
    global _WRITER, _warned
    _shutdown()
    with _WRITER_LOCK:
        logger = logging.getLogger(LOGGER_NAME)
        for existing in list(logger.handlers):
            logger.removeHandler(existing)
        _WRITER = None
    _warned = False
