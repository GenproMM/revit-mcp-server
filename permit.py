# -*- coding: utf-8 -*-
"""One-time permits for confirmed and allowed mutations, and the envelope-first wire text (D-18).

CPython side only, standard library only. The bridge mints a permit after the
authorization step decided (allow, or confirm and accepted by the human) and sends the
body as exact text: the shared-secret envelope first, then the argument text the permit
hashes, unchanged. The Revit half (revit_mcp/permits.py, IronPython 3.4 dialect) splits
that text again, checks the signature, route, session, argument hash and expiry, and
consumes the nonce once.

Why text and not objects: the permit commits to the exact characters sent, never to a
re-serialized object. IronPython 3.4 prints floats differently from CPython
(repr(0.1) is 0.10000000000000001 there), so a canonical re-encoding on both sides would
disagree on the first float. Hashing the text removes the question.

Known limit (D-18): the secret rides in the same body, so a process that can read the
shared secret can mint permits itself. The permit is an integrity and consistency device
and a barrier against stray callers on the network; it is not isolation from an agent
that has the user's own operating-system rights.

This module never prints, never logs and never reads a file. It imports nothing from mcp.
"""

import hashlib
import hmac
import json
import secrets
import time

PERMIT_PROTOCOL = 1
PERMIT_KEY = "permit"
ENVELOPE_KEY = "_mcp"
KEY_LABEL = b"revit-mcp/permit/v1"
MAC_PREFIX = "permit1"


def args_text(data):
    """The exact JSON object text of a request body (compact, pure ASCII), refusing bad bodies.

    The texts of the two ValueErrors are the ones bridge.with_envelope has always used,
    so the model sees one wording. Neither carries the body or the secret.
    """
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object to carry the shared-secret envelope")
    if ENVELOPE_KEY in data:
        raise ValueError("request body already carries the reserved _mcp key; "
                         "refusing to merge it into the shared-secret envelope")
    try:
        return json.dumps(data, separators=(",", ":"), allow_nan=False)
    except ValueError:
        raise ValueError("request body contains NaN or Infinity, which JSON cannot carry")


def args_hash(text):
    """SHA-256 hex of the argument text (ASCII by construction)."""
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def derive_key(secret):
    """The permit MAC key: HMAC-SHA256 of a fixed label under the shared secret (domain separation)."""
    return hmac.new(secret.encode("utf-8"), KEY_LABEL, hashlib.sha256).digest()


def mac_message(route, a, s, e, n, p):
    """The seven lines the MAC covers, joined by LF, as ASCII bytes."""
    return "\n".join((MAC_PREFIX, route, a, s, str(e), n, p)).encode("ascii")


def mint(secret, route, args_text, session_token, policy_hash, ttl_s, now=None, nonce=None):
    """A permit dict bound to route, exact argument text, target session, policy and expiry."""
    issued = int(time.time() if now is None else now)
    nonce = secrets.token_hex(16) if nonce is None else nonce
    a = args_hash(args_text)
    e = issued + int(ttl_s)
    mac = hmac.new(derive_key(secret),
                   mac_message(route, a, session_token, e, nonce, policy_hash),
                   hashlib.sha256).hexdigest()
    return {"v": PERMIT_PROTOCOL, "r": route, "a": a, "s": session_token, "e": e,
            "n": nonce, "p": policy_hash, "m": mac}


def wire_text(args_text, envelope):
    """The request body text: the envelope member first, the argument text unchanged after it.

    ``args_text`` is the text args_text() returned (an object); ``{}`` has no members to
    follow the envelope, any other text continues after its opening brace.
    """
    head = '{"' + ENVELOPE_KEY + '":' + json.dumps(envelope, separators=(",", ":"))
    if args_text == "{}":
        return head + "}"
    return head + "," + args_text[1:]
