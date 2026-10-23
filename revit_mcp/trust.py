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

    Live-verified 2026-10-23 (plan 03-08): pyRevit routes engine py=3.4.2 (.NET
    Framework 4, clr_version 4.0.30319.42000); Revit and pyRevit versions were not
    reported. hashlib.sha256 digests equal CPython's (abc_ok, first4 [227, 79, 109,
    236]); trust loads as a helper (/status/ skipped_modules) and check_secret gave
    ok and mismatch as expected (trust_ok). FixedTimeEquals type present: False and
    hmac.compare_digest present: True (both informational; neither is used).
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


# ---------------------------------------------------------------- payload integrity
#
# Three states (D-13): verified_match, verified_mismatch, unverifiable. Only a
# file that was read and differs makes a mismatch; a manifest or file that could
# not be read is "unverifiable", so an unreachable share can never be reported as
# tampering. evaluate_integrity() is pure: revit_mcp/integrity.py does the reading
# and hands it what it saw.

INTEGRITY_MATCH = "verified_match"
INTEGRITY_MISMATCH = "verified_mismatch"
INTEGRITY_UNVERIFIABLE = "unverifiable"

REASON_MANIFEST_MISSING = "manifest_missing"
REASON_MANIFEST_UNREADABLE = "manifest_unreadable"
REASON_READ_ERROR = "read_error"

MANIFEST_SCHEMA = 1
INTEGRITY_FAILURE_STATUS = 423

_HEX_DIGITS = "0123456789abcdef"


def _result(state, reason=None, modified=(), missing=(), unexpected=()):
    """The one result shape: state, reason and three sorted, de-duplicated lists."""
    return {
        "state": state,
        "reason": reason,
        "modified": sorted(set(modified)),
        "missing": sorted(set(missing)),
        "unexpected": sorted(set(unexpected)),
    }


def unverifiable(reason):
    """The result for a check that could not be completed, with its reason."""
    return _result(INTEGRITY_UNVERIFIABLE, reason)


def valid_manifest_path(key):
    """True only for a relative, '/'-separated path that stays inside the extension.

    Text, non-empty, no backslash, no colon (a drive letter), not absolute, and no
    segment that is empty, '.' or '..'. A manifest key failing this is never opened.
    """
    if not isinstance(key, _TEXT_TYPE) or not key:
        return False
    if "\\" in key or ":" in key or key.startswith("/"):
        return False
    for segment in key.split("/"):
        if segment in ("", ".", ".."):
            return False
    return True


def _valid_digest(value):
    """True for text of exactly 64 lowercase hexadecimal characters."""
    if not isinstance(value, _TEXT_TYPE) or len(value) != 64:
        return False
    for char in value:
        if char not in _HEX_DIGITS:
            return False
    return True


def _manifest_files(manifest):
    """The files map of a well-formed manifest, or None when anything is off."""
    if not isinstance(manifest, dict):
        return None
    schema = manifest.get("schema")
    if type(schema) is not int or schema != MANIFEST_SCHEMA:  # a bool is not 1 here
        return None
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return None
    for key, value in files.items():
        if not valid_manifest_path(key) or not _valid_digest(value):
            return None
    return files


def evaluate_integrity(manifest, observed):
    """The three-state verdict for a parsed manifest and what was observed; never raises.

    manifest is the parsed _manifest.json or None when it is absent. observed is
    {"hashes": {relpath: sha256}, "present_py": [relpath of every revit_mcp/*.py
    seen], "unreadable": [relpath that could not be read]}. The result is
    {"state", "reason", "modified", "missing", "unexpected"} with sorted lists.

    A None manifest is unverifiable/manifest_missing; a malformed manifest is
    unverifiable/manifest_unreadable; an observation of the wrong shape, or any
    unreadable path, is unverifiable/read_error even when other files differ
    (an unreachable file is never a mismatch). Otherwise modified (hash differs),
    missing (not observed) and unexpected (a .py present but not listed) decide
    verified_mismatch versus verified_match. Underscore-prefixed .py files count:
    they are shipped code any module can import.
    """
    try:
        if manifest is None:
            return unverifiable(REASON_MANIFEST_MISSING)
        files = _manifest_files(manifest)
        if files is None:
            return unverifiable(REASON_MANIFEST_UNREADABLE)
        if (not isinstance(observed, dict)
                or not isinstance(observed.get("hashes"), dict)
                or not isinstance(observed.get("present_py"), list)
                or not isinstance(observed.get("unreadable"), list)):
            return unverifiable(REASON_READ_ERROR)
        if observed["unreadable"]:
            return unverifiable(REASON_READ_ERROR)
        hashes = observed["hashes"]
        modified = [p for p in files if p in hashes and hashes[p] != files[p]]
        missing = [p for p in files if p not in hashes]
        unexpected = [p for p in observed["present_py"] if p not in files]
        if modified or missing or unexpected:
            return _result(INTEGRITY_MISMATCH, None, modified, missing, unexpected)
        return _result(INTEGRITY_MATCH)
    except Exception:
        return unverifiable(REASON_READ_ERROR)


def _text_items(values):
    """The text items of a list, tuple or set, sorted by code point; [] for anything else."""
    if not isinstance(values, (list, tuple, set, frozenset)):
        return []
    return sorted(set(v for v in values if isinstance(v, _TEXT_TYPE)))


def mismatch_files(result):
    """Sorted union of modified, missing and unexpected; [] for a malformed result."""
    if not isinstance(result, dict):
        return []
    names = []
    for key in ("modified", "missing", "unexpected"):
        names.extend(_text_items(result.get(key)))
    return sorted(set(names))


def integrity_failure(files):
    """(body, status) of the HTTP 423 refusal naming the files that differ.

    files is a list, tuple or set of relative names; its text items are sorted into the
    body, and anything else gives an empty list. The names carry no file content.
    """
    body = {
        "error": (
            "Mutation rejected: Revit extension files differ from the published "
            "manifest. Reinstall the extension from the share and restart Revit."
        ),
        "integrity": INTEGRITY_MISMATCH,
        "files": _text_items(files),
    }
    return body, INTEGRITY_FAILURE_STATUS


# ------------------------------------------------------------------ bind classification
#
# SEC-07 (D-16). classify_listeners() is the pure half: it names a Routes listener
# set as loopback_only, exposed or unknown. It never blocks a mutation and collects
# nothing; Phase 5 builds the (host, port) pairs from the .NET active TCP listener
# table and reports the result on /status/.

BIND_LOOPBACK_ONLY = "loopback_only"
BIND_EXPOSED = "exposed"
BIND_UNKNOWN = "unknown"

_ASCII_DIGITS = "0123456789"


def _as_port(value):
    """An int port for an int (never a bool) or digit-only text, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, _TEXT_TYPE):
        text = value.strip()
        if not text:
            return None
        for char in text:
            if char not in _ASCII_DIGITS:
                return None
        return int(text)
    return None


def _is_loopback_ipv4(text):
    """True only for a dotted quad of four plain decimal parts (0-255) starting with 127.

    A part with a leading zero is refused: some stacks read it as octal, so it is not
    provably the address it looks like.
    """
    parts = text.split(".")
    if len(parts) != 4:
        return False
    numbers = []
    for part in parts:
        if not part or (len(part) > 1 and part[0] == "0"):
            return False
        for char in part:
            if char not in _ASCII_DIGITS:
                return False
        number = int(part)
        if number > 255:
            return False
        numbers.append(number)
    return numbers[0] == 127


def _is_loopback_host(host):
    """True only for a literal loopback address; text that is not one is False.

    Accepts 127.0.0.0/8, ::1, 0:0:0:0:0:0:0:1 and ::ffff:127.x.x.x, lower-cased,
    stripped, with one pair of surrounding brackets and a %scope suffix removed. A
    wildcard, a LAN or public address, a hostname and anything malformed is False.
    """
    if not isinstance(host, _TEXT_TYPE):
        return False
    text = host.strip().lower()
    if len(text) >= 2 and text[0] == "[" and text[-1] == "]":
        text = text[1:-1]
    cut = text.find("%")
    if cut >= 0:
        text = text[:cut]
    if text in ("::1", "0:0:0:0:0:0:0:1"):
        return True
    if text.startswith("::ffff:"):
        text = text[len("::ffff:"):]
    return _is_loopback_ipv4(text)


def classify_listeners(endpoints, port):
    """BIND_LOOPBACK_ONLY, BIND_EXPOSED or BIND_UNKNOWN for the listeners on ``port``; never raises.

    endpoints is an iterable of (host text, port) pairs, which the Phase 5 wrapper
    builds from .NET IPGlobalProperties.GetActiveTcpListeners(). Only pairs on
    ``port`` count. Every such host a literal loopback address gives
    "loopback_only"; any wildcard (0.0.0.0, ::), LAN or public address, or non-IP
    text such as a hostname gives "exposed". None, a non-iterable, a malformed
    entry, an unreadable port or no listener on the port gives "unknown". Two
    loopback listeners stay "loopback_only": this is not an ambiguity detector.

    "exposed" is reported by /status/ as bind: exposed with health: degraded, but it
    never blocks a mutation: the shared secret is the network barrier, and pyRevit
    offers no way to choose the bind host. A forced 127.0.0.1 bind is deferred.
    """
    try:
        wanted = _as_port(port)
        if wanted is None or endpoints is None:
            return BIND_UNKNOWN
        hosts = []
        for entry in endpoints:
            if not isinstance(entry, (tuple, list)) or len(entry) != 2:
                return BIND_UNKNOWN
            host, entry_port = entry
            entry_port = _as_port(entry_port)
            if not isinstance(host, _TEXT_TYPE) or entry_port is None:
                return BIND_UNKNOWN
            if entry_port == wanted:
                hosts.append(host)
        if not hosts:
            return BIND_UNKNOWN
        for host in hosts:
            if not _is_loopback_host(host):
                return BIND_EXPOSED
        return BIND_LOOPBACK_ONLY
    except Exception:
        return BIND_UNKNOWN
