# -*- coding: utf-8 -*-
"""
Pure helper for the shared-secret gate (and, from plan 03-04, payload integrity).

This module is deliberately free of any pyRevit, clr, System or Revit API
import, so it is unit tested under CPython 3 and a refusal it decides can be
returned before any transaction is opened. It registers no routes, so
startup.py's discovery imports it at extension load and reports it as a helper.
It was built in Phase 3 and is wired into the request path by Phase 5; until
then nothing calls it.

Dialect: IronPython 3 at the Python 3.4 language level (CLAUDE.md two-runtime
rule). Only text.format, no annotations, relative sibling imports, and runtime
detection only through the textutils aliases.

The request carries the secret in the body, under one reserved key (ENVELOPE_KEY).
split_envelope() separates it from the payload, check_secret() returns one of four
verdicts, and auth_failure() turns a refusal into the HTTP 401 body. The secret
value never appears in any exception text, return value or response body produced
here, and this module never logs.
"""

import hashlib

from .textutils import _BYTES_TYPE, _TEXT_TYPE, parse_request_data

ENVELOPE_KEY = "_mcp"
SECRET_KEY = "secret"
SECRET_FILE_NAME = "_bridge_secret"
MIN_SECRET_LENGTH = 16

AUTH_OK = "ok"
AUTH_MISSING = "missing"
AUTH_MISMATCH = "mismatch"
AUTH_SERVER_NOT_CONFIGURED = "server_not_configured"
AUTH_FAILURE_STATUS = 401

# Reads are exempt from the gate (D-03). Any other verb, an unknown one included,
# is gated, so a route added with a new verb is closed rather than silently open.
UNGATED_METHODS = ("GET", "HEAD")

_AUTH_HINTS = {
    AUTH_MISSING: (
        "The MCP server sent no shared secret. Update the payload so _bridge_secret "
        "exists and restart the MCP server."
    ),
    AUTH_MISMATCH: (
        "The MCP server and the Revit extension hold different shared secrets. "
        "Install both from the same build and restart Revit."
    ),
    AUTH_SERVER_NOT_CONFIGURED: (
        "The Revit extension has no _bridge_secret file. Republish the extension "
        "and restart Revit."
    ),
}


def split_envelope(raw):
    """Return (envelope, payload) for one request body; never raises, never mutates.

    The body is parsed only through parse_request_data, so bytes (IronPython 3),
    str (IronPython 2.7) and dict (an engine whose own parse worked) are all
    accepted. envelope is the whole reserved-key dict (the secret today; a call id
    or an approval token may ride it later) and payload is the body without that
    key. An empty, null, non-JSON or unparseable body gives ({}, None); a body that
    parses to something other than an object gives ({}, that value); a missing or
    non-object reserved key gives an empty envelope, so the verdict is "missing".
    """
    try:
        data = parse_request_data(raw)
    except Exception:
        return {}, None
    if not isinstance(data, dict):
        return {}, data
    envelope = data.get(ENVELOPE_KEY)
    if not isinstance(envelope, dict):
        envelope = {}
    payload = dict((k, v) for k, v in data.items() if k != ENVELOPE_KEY)
    return envelope, payload


def envelope_secret(envelope):
    """The secret carried by an envelope, or None when there is none."""
    if isinstance(envelope, dict):
        return envelope.get(SECRET_KEY)
    return None


def _digest(value):
    """32 SHA-256 bytes of a text or bytes value as a bytearray, else None.

    Text is encoded as UTF-8 (no Unicode normalization); bytes are hashed as they
    are. A bytearray yields ints on every runtime, which the compare relies on.
    """
    if isinstance(value, _TEXT_TYPE):
        value = value.encode("utf-8")
    elif not isinstance(value, _BYTES_TYPE):
        return None
    return bytearray(hashlib.sha256(value).digest())


def _same_digest(left, right):
    """Equality of two byte sequences by XOR-accumulation, visiting every position.

    There is no return, break or continue inside the loop, so the work done does
    not depend on where the first difference sits.
    """
    acc = len(left) ^ len(right)
    for a, b in zip(left, right):
        acc |= a ^ b
    return acc == 0


def secret_matches(provided, expected):
    """True only when two secrets are equal, compared in constant time; never raises.

    Both values are normalized to UTF-8 bytes and hashed with SHA-256, and the two
    32-byte digests are compared by XOR-accumulation over every position with no
    early exit. Hashing first equalizes the length, so the secret's length does not
    leak through the compare. No exception text is kept: a failure anywhere gives
    False.

    Documented fallback reason (ROADMAP Phase 3 success criterion 2):
    CryptographicOperations.FixedTimeEquals exists only on .NET Core 2.1+,
    .NET Standard 2.1 and .NET 5+ and takes a ReadOnlySpan of byte, while Revit
    2024 runs .NET Framework 4.8; hmac.compare_digest is unverified on
    IronPython 3.4. So one CLR-free implementation serves both halves.

    Live check of hashlib.sha256 under the IPY342 routes engine: pending, plan 03-08.
    """
    try:
        left = _digest(provided)
        right = _digest(expected)
        if left is None or right is None:
            return False
        return _same_digest(left, right)
    except Exception:
        return False


def _blank(value):
    """True for None and for text or bytes that are empty once stripped."""
    if value is None:
        return True
    if isinstance(value, _TEXT_TYPE) or isinstance(value, _BYTES_TYPE):
        return len(value.strip()) == 0
    return False


def _configured(expected):
    """True only for text or bytes of at least MIN_SECRET_LENGTH once stripped."""
    if isinstance(expected, _TEXT_TYPE) or isinstance(expected, _BYTES_TYPE):
        return len(expected.strip()) >= MIN_SECRET_LENGTH
    return False


def check_secret(provided, expected):
    """One of AUTH_OK, AUTH_MISSING, AUTH_MISMATCH, AUTH_SERVER_NOT_CONFIGURED; never raises.

    The server's own configuration is decided first: an expected value that is
    None, blank or shorter than MIN_SECRET_LENGTH is "server_not_configured", so
    two empty secrets can never compare equal. Then a None or blank provided value
    is "missing", and any other value is "ok" or "mismatch".
    """
    try:
        if not _configured(expected):
            return AUTH_SERVER_NOT_CONFIGURED
        if _blank(provided):
            return AUTH_MISSING
        if secret_matches(provided, expected):
            return AUTH_OK
        return AUTH_MISMATCH
    except Exception:
        return AUTH_MISMATCH


def auth_failure(reason):
    """(body, status) of the HTTP 401 refusal for a failed verdict.

    A reason outside the three failure verdicts is replaced by "mismatch", so no
    caller can echo arbitrary text, a secret included, into the response.
    """
    if reason not in (AUTH_MISSING, AUTH_MISMATCH, AUTH_SERVER_NOT_CONFIGURED):
        reason = AUTH_MISMATCH
    body = {
        "error": "Mutation rejected: shared secret {}".format(reason),
        "auth": reason,
        "hint": _AUTH_HINTS[reason],
    }
    return body, AUTH_FAILURE_STATUS


def secret_from_bytes(raw):
    """The secret text held by the bytes of a secret file, or None; never raises.

    Strips a UTF-8 BOM, then surrounding space, tab, CR and LF (a trailing CRLF
    is the usual editor artifact). Returns None for anything that is not bytes,
    for undecodable input (UTF-16 included), for text holding a NUL, and for a
    value shorter than MIN_SECRET_LENGTH. The same rule is duplicated, on purpose,
    in bridge.py (plan 03-03): keep the two identical.
    """
    if not isinstance(raw, _BYTES_TYPE):
        return None
    try:
        text = raw.decode("utf-8-sig")
    except ValueError:  # UnicodeDecodeError subclasses ValueError on every runtime
        return None
    text = text.strip(" \t\r\n")
    if "\x00" in text or len(text) < MIN_SECRET_LENGTH:
        return None
    return text


def read_secret_file(path):
    """The secret held by the file at ``path``, or None; never raises, never logs.

    The only file access in this module, and read-only. A missing, unreadable or
    directory path gives None, which check_secret reads as "server_not_configured".
    """
    try:
        handle = open(path, "rb")
    except (IOError, OSError, TypeError, ValueError):
        return None
    try:
        return secret_from_bytes(handle.read())
    except (IOError, OSError):
        return None
    finally:
        handle.close()


def gate_applies(method):
    """False for GET and HEAD (any case), True for every other or unknown method.

    Fails closed: None, a non-text value and an unrecognized verb are all gated.
    """
    if isinstance(method, _BYTES_TYPE):
        try:
            method = method.decode("ascii")
        except ValueError:
            return True
    if isinstance(method, _TEXT_TYPE):
        return method.strip().upper() not in UNGATED_METHODS
    return True
