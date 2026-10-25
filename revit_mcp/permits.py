# -*- coding: utf-8 -*-
"""
Verifier and single-use registry for one-time mutation permits (Phase 7, D-18).

A helper module, not a route domain: it registers no routes, so startup.py's
discovery imports it at extension load and reports it as a helper. It imports no
pyRevit, clr, System or Revit API name, so it is unit tested under CPython 3 and
can run before any document is touched.

Dialect: IronPython 3 at the Python 3.4 language level (CLAUDE.md two-runtime
rule). Only text.format, no annotations, relative sibling imports, and runtime
detection only through the textutils aliases. Imports are limited to hashlib,
json, threading and time: IronPython has no ``secrets`` module and ``hmac.new`` is
unverified there, so the HMAC below is RFC 2104 written over hashlib and compared
with the constant-time helper of trust.py.

The permit travels in the body, beside the secret, under the reserved key
(trust.ENVELOPE_KEY). The body is exact text with the envelope member first and the
argument text after it unchanged; split_wire() cuts it with json raw_decode, so the
argument hash is taken over the characters that were sent and never over a
re-serialized object (IronPython 3.4 prints floats differently from CPython).

check_and_consume() never raises, never returns the body or the secret, and answers
one verdict word. Only a fully verified permit touches the registry, and it does so in
the same call, under one lock: a nonce is consumed once. The registry lives in this
process only (it dies with Revit, which is safe because a permit also binds the
process session token and lives at most MAX_TTL seconds).

Known limit (D-18): the shared secret is in the same body, so a process that can read
the secret can mint permits itself. The permit proves the body is the one the
authorizing side sent, once, to this process; it is not isolation from an agent that
holds the user's own operating-system rights.
"""

import hashlib
import json
import threading
import time

from . import trust
from .textutils import _BYTES_TYPE, _TEXT_TYPE

PERMIT_PROTOCOL = 1
PERMIT_KEY = "permit"
KEY_LABEL = b"revit-mcp/permit/v1"
MAC_PREFIX = "permit1"
WIRE_PREFIX = '{"_mcp":'
MAX_TTL = 120
SKEW = 5
REGISTRY_CAP = 4096

OK = "ok"
MISSING = "missing"
MALFORMED = "malformed"
UNSUPPORTED = "unsupported_version"
BAD_SIGNATURE = "bad_signature"
ROUTE_MISMATCH = "route_mismatch"
SESSION_MISMATCH = "session_mismatch"
ARGS_MISMATCH = "args_mismatch"
EXPIRED = "expired"
TTL_TOO_LONG = "ttl_too_long"
REPLAYED = "replayed"
REGISTRY_FULL = "registry_full"
NOT_CONFIGURED = "not_configured"

_PERMIT_FIELDS = ("v", "r", "a", "s", "e", "n", "p", "m")
_TEXT_FIELDS = ("r", "a", "s", "n", "p", "m")

_LOCK = threading.Lock()
_CONSUMED = {}  # nonce -> expiry (epoch seconds)


def hmac_sha256(key, msg):
    """HMAC-SHA256 digest bytes of ``msg`` under ``key`` (RFC 2104, block size 64)."""
    block = 64
    if len(key) > block:
        key = hashlib.sha256(key).digest()
    key = key + b"\x00" * (block - len(key))
    outer = bytes(bytearray(b ^ 0x5c for b in bytearray(key)))
    inner = bytes(bytearray(b ^ 0x36 for b in bytearray(key)))
    return hashlib.sha256(outer + hashlib.sha256(inner + msg).digest()).digest()


def derive_key(secret):
    """The permit MAC key: HMAC-SHA256 of the fixed label under the secret (text or bytes)."""
    if isinstance(secret, _TEXT_TYPE):
        secret = secret.encode("utf-8")
    return hmac_sha256(secret, KEY_LABEL)


def normalize_route(path):
    """"/" + the path without its query string, stripped of slashes, + "/"; None for no route."""
    if not isinstance(path, _TEXT_TYPE):
        return None
    head = path.split("?", 1)[0].strip("/")
    if not head:
        return None
    return "/" + head + "/"


def split_wire(raw):
    """(envelope dict, argument text) cut from the exact wire text, or None; never raises.

    The text must be ASCII (bytes are decoded as ASCII, anything else is refused), start
    with the envelope member and continue with either the closing brace or a comma and
    the rest of the argument members.
    """
    try:
        if isinstance(raw, _BYTES_TYPE):
            text = raw.decode("ascii")
        elif isinstance(raw, _TEXT_TYPE):
            text = raw
            text.encode("ascii")
        else:
            return None
        if not text.startswith(WIRE_PREFIX):
            return None
        envelope, end = json.JSONDecoder().raw_decode(text, len(WIRE_PREFIX))
        if not isinstance(envelope, dict):
            return None
        rest = text[end:]
        if rest == "}":
            return envelope, "{}"
        if rest.startswith(","):
            return envelope, "{" + rest[1:]
        return None
    except Exception:
        return None


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _shape_ok(permit):
    if not isinstance(permit, dict) or sorted(permit.keys()) != sorted(_PERMIT_FIELDS):
        return False
    if not _is_int(permit["v"]) or not _is_int(permit["e"]):
        return False
    for name in _TEXT_FIELDS:
        value = permit[name]
        if not isinstance(value, _TEXT_TYPE) or "\n" in value:
            return False
    return True


def _blank(value):
    return not isinstance(value, _TEXT_TYPE) or len(value.strip()) == 0


def check_and_consume(raw, route_path, secret, session_token, now=None):
    """OK or one verdict word; consumes the permit's nonce only on OK. Never raises.

    ``raw`` is the request body as it arrived (bytes, text or dict is accepted for the
    envelope lookup, but only bytes or text can be verified: the wire form is text),
    ``route_path`` the route the request addressed, ``secret`` the extension's own
    secret and ``session_token`` this Revit process's incarnation token.
    """
    try:
        if _blank(secret) or _blank(session_token):
            return NOT_CONFIGURED
        trusted_envelope = trust.split_envelope(raw)[0]
        if PERMIT_KEY not in trusted_envelope:
            return MISSING
        split = split_wire(raw)
        if split is None:
            return MALFORMED
        envelope, args_text = split
        # A second reserved member later in the body would be read differently by
        # json.loads (last one wins) than by raw_decode (the first one is the one cut).
        if envelope != trusted_envelope:
            return MALFORMED
        permit = envelope.get(PERMIT_KEY)
        if not _shape_ok(permit):
            return MALFORMED
        if permit["v"] != PERMIT_PROTOCOL:
            return UNSUPPORTED
        message = "\n".join((MAC_PREFIX, permit["r"], permit["a"], permit["s"],
                             str(permit["e"]), permit["n"], permit["p"])).encode("ascii")
        expected = hmac_sha256(derive_key(secret), message)
        expected_hex = "".join("{:02x}".format(b) for b in bytearray(expected))
        if not trust._same_digest(bytearray(expected_hex.encode("ascii")),
                                  bytearray(permit["m"].encode("ascii"))):
            return BAD_SIGNATURE
        if normalize_route(route_path) != permit["r"]:
            return ROUTE_MISMATCH
        if session_token != permit["s"]:
            return SESSION_MISMATCH
        if hashlib.sha256(args_text.encode("ascii")).hexdigest() != permit["a"]:
            return ARGS_MISMATCH
        if now is None:
            now = int(time.time())
        expiry = permit["e"]
        if expiry < now - SKEW:
            return EXPIRED
        if expiry - now > MAX_TTL:
            return TTL_TOO_LONG
        with _LOCK:
            for nonce in [n for n, e in _CONSUMED.items() if e + SKEW < now]:
                del _CONSUMED[nonce]
            if permit["n"] in _CONSUMED:
                return REPLAYED
            if len(_CONSUMED) >= REGISTRY_CAP:
                return REGISTRY_FULL
            _CONSUMED[permit["n"]] = expiry
        return OK
    except Exception:
        return MALFORMED
