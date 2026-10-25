# -*- coding: utf-8 -*-
"""
Load-time security state and the per-route gate of the Revit extension.

This is a helper module: it registers no routes (no register_*_routes callable), so
startup.py's discovery imports it at extension load and reports it as a helper.

The gate is an explicit first call in every non-GET handler, not a wrapper, an api
attribute or anything startup.py installs: a common wrapper was rejected (D-01, the
Phase 2 G1 explicit-route-only rule). A handler opens with

    gate_refusal = gate_or_response(request)
    if gate_refusal is not None:
        return gate_refusal

before the document guard and before any other statement, so a refusal arrives
before a document attribute, a collector or a transaction is touched.

State is read once, at extension load, by initialize(): the shared secret from
revit_mcp/_bridge_secret and the integrity verdict from _manifest.json. A file that
changes after load is seen only after a full Revit restart. Until initialize has
succeeded the state is None and the gate answers 401 server_not_configured, so a
failed initialization keeps every gated route closed. There is deliberately no flag,
environment variable or module attribute that lets production code skip the gate.

Nothing here writes, renames or deletes a file (INTG-03), and nothing here logs or
returns the shared secret or the raw request body (SEC-06).

Dialect: IronPython 3 at the Python 3.4 language level (CLAUDE.md two-runtime rule).
Relative sibling imports only; pyRevit is imported inside _refusal only, so CPython
tests import this module directly.
"""

import os

from . import identity
from . import integrity
from . import permits
from . import textutils
from . import trust

# None means "not initialized": the gate refuses with 401 server_not_configured.
_STATE = None


def initialize(root, package_dir):
    """Compute the load-time state from the extension's own files; returns None.

    ``root`` is the extension directory (it holds startup.py and _manifest.json) and
    ``package_dir`` the revit_mcp directory (it holds _bridge_secret). The state is
    reset to None first and every call recomputes everything, so a pyRevit Reload
    (which re-runs startup.py while submodules stay cached) never keeps a stale
    answer. Both readers are read-only and never raise; an unexpected exception
    propagates so startup can record it, with the state left None (gate closed).
    Nothing returned or kept in an exception contains the secret.
    """
    global _STATE
    _STATE = None
    secret = trust.read_secret_file(os.path.join(package_dir, trust.SECRET_FILE_NAME))
    result = integrity.check_integrity(root)
    _STATE = {"secret": secret, "integrity": result}


def _dotnet_listeners():
    """(host text, port) pairs of every active TCP listener, or None when unreadable.

    IronPython-only path: System.Net is imported inside the function so CPython
    tests import this module freely (under CPython the import fails and the result
    is None). Any exception gives None, which trust.classify_listeners reports as
    "unknown". Never raises.
    """
    try:
        from System.Net.NetworkInformation import IPGlobalProperties
        endpoints = IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners()
        return [(str(ep.Address), int(ep.Port)) for ep in endpoints]
    except Exception:
        return None


def status_block(port, listeners=None):
    """The security part of the /status/ reply; never raises, never carries the secret.

    Returns {"secret": {"configured", "fingerprint"}, "integrity": <the result
    initialize stored, or unverifiable/read_error when there is no usable state>,
    "bind": <trust.classify_listeners verdict>, "permit": {"protocol"}}. The secret appears only as
    ``configured`` and its 8-hex SHA-256 fingerprint (D-08). ``listeners`` is a
    zero-argument callable returning (host text, port) pairs for ``port`` (default
    _dotnet_listeners); a raising callable or None reads as bind "unknown". A bind
    outside loopback is reported, never blocked (03 D-16).
    """
    try:
        state = _STATE
        secret = state.get("secret") if isinstance(state, dict) else None
        result = state.get("integrity") if isinstance(state, dict) else None
        fingerprint = trust.secret_fingerprint(secret)
        if not isinstance(result, dict):
            result = trust.unverifiable(trust.REASON_READ_ERROR)
        try:
            endpoints = (listeners if listeners is not None else _dotnet_listeners)()
        except Exception:
            endpoints = None
        return {
            "secret": {"configured": fingerprint is not None, "fingerprint": fingerprint},
            "integrity": result,
            "bind": trust.classify_listeners(endpoints, port),
            "permit": permits.status_info(),
        }
    except Exception:
        return {
            "secret": {"configured": False, "fingerprint": None},
            "integrity": trust.unverifiable(trust.REASON_READ_ERROR),
            "bind": trust.BIND_UNKNOWN,
            "permit": permits.status_info(),
        }


def _refusal(body, status):
    """The pyRevit routes response for a refusal. pyRevit is imported only here."""
    from pyrevit import routes
    return routes.make_response(data=body, status=status)


def _raw_data(request):
    """The request body as it arrived, or None for a missing request or attribute."""
    return getattr(request, "data", None)


def _process_token():
    """The current Revit process token for permit verification, or None; never raises."""
    return identity.process_token()


def gate_or_response(request):
    """None when the call may proceed, otherwise the routes response that refuses it.

    Order: no state gives 401 server_not_configured; then the shared secret
    (trust.check_secret, no compare of its own); then the integrity state, so a wrong
    secret is a 401 even when the integrity state is a mismatch (D-04); a verified
    mismatch gives 423 naming the files; then one-time permit verification gives 403.
    The permit binds the exact body text, route, process token, expiry and nonce and is
    consumed only here, before a route sees the cleaned body. A process that can read
    the shared secret can mint permits; this is an authorization boundary, not OS isolation.
    On success request.data is replaced by the body without the reserved key, in the type
    it arrived in. An empty, non-JSON or non-object body carries no envelope and is a 401
    missing. Never raises: any failure, a request whose data cannot be reassigned included,
    answers the fixed HTTP 500 text of trust.gate_failure with no local, body or secret in it.
    """
    try:
        state = _STATE
        if state is None:
            return _refusal(*trust.auth_failure(trust.AUTH_SERVER_NOT_CONFIGURED))
        raw = _raw_data(request)
        envelope, payload = trust.split_envelope(raw)
        verdict = trust.check_secret(trust.envelope_secret(envelope), state["secret"])
        if verdict != trust.AUTH_OK:
            return _refusal(*trust.auth_failure(verdict))
        if state["integrity"].get("state") == trust.INTEGRITY_MISMATCH:
            return _refusal(*trust.integrity_failure(trust.mismatch_files(state["integrity"])))
        permit_verdict = permits.check_and_consume(
            raw, getattr(request, "path", None), state["secret"], _process_token())
        if permit_verdict != permits.OK:
            return _refusal(*permits.failure(permit_verdict))
        request.data = trust.clean_body(raw, payload)
        return None
    except Exception:
        return _refusal(*trust.gate_failure())


def strip_envelope(request):
    """Remove the reserved key from the body of an open POST read; always returns None.

    The seven open reads (trust.OPEN_POST_READ_ROUTES) are never refused, whatever
    the request carries, a wrong secret and a verified mismatch included; their
    handlers call this so the reserved key does not reach the route's own parse. The
    body is rewritten, in the type it arrived in, only when it parses to an object
    that contains the reserved key. Any other body (None, empty, invalid JSON, a
    list, an object without the key) is left exactly as it arrived. Never raises: a
    request that cannot be read or rewritten is left as it is.
    """
    try:
        raw = _raw_data(request)
        data = textutils.parse_request_data(raw)
        if not isinstance(data, dict) or trust.ENVELOPE_KEY not in data:
            return None
        payload = trust.split_envelope(raw)[1]
        request.data = trust.clean_body(raw, payload)
    except Exception:
        return None
    return None
