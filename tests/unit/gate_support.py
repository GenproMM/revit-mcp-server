# -*- coding: utf-8 -*-
"""Shared test helper: configure the Revit-side gate state and build the requests pyRevit hands over. Not a test module; needs no Revit.

Phase 7 requests carry a path and a one-time permit. The body is envelope-first wire
text (``{"_mcp":{...},<arguments>}``) whose envelope holds the test secret and a real
permit minted by ``permit.mint`` for the request's own route, and the request double has
a ``path`` attribute. Production has no bypass: a test pins the Revit-side process token
and sends a real permit, it never switches the check off.
"""

import json
import types

import permit as permit_module

# A fixed test value, 32+ characters. Never the developer's real secret.
TEST_SECRET = "phase5-test-secret-0123456789-abcdefXYZ"

# The Revit-process incarnation token the test gate reports, and the default route a
# request double addresses. Fixed test values, never a real session token.
TEST_SESSION_TOKEN = "33333333-3333-4333-8333-333333333333"
TEST_ROUTE = "/unit-test/"

_TEST_POLICY_HASH = "000000000000"
_TEST_PERMIT_TTL_S = 60


def configure_gate(monkeypatch, secret=TEST_SECRET, integrity=None, session_token=TEST_SESSION_TOKEN):
    """Put revit_mcp.security into a configured state for one test.

    The state is the one security.initialize would compute at extension load:
    ``secret`` (None reads as "server_not_configured") and an integrity result
    (unverifiable/manifest_missing by default, which blocks nothing). The Revit-side
    process token is pinned to ``session_token`` and the single-use permit registry is
    emptied. Tests configure the state and send the envelope; production has no bypass.
    """
    from revit_mcp import permits, security, trust

    if integrity is None:
        integrity = trust.unverifiable(trust.REASON_MANIFEST_MISSING)
    monkeypatch.setattr(security, "_STATE", {"secret": secret, "integrity": integrity})
    monkeypatch.setattr(security, "_process_token", lambda: session_token, raising=False)
    monkeypatch.setattr(permits, "_CONSUMED", {})


def enveloped_body(body, secret=TEST_SECRET, as_type="bytes", route=TEST_ROUTE, permit=True,
                   session_token=TEST_SESSION_TOKEN, now=None):
    """``body`` as the bridge sends it: envelope first, with a real permit, as bytes, text or a dict.

    A None ``secret`` adds no envelope at all (the "missing" case) and keeps the plain
    ``json.dumps`` of the data. Otherwise the argument text is ``permit.args_text(data)``,
    the envelope is ``{"secret": secret}`` plus, when ``permit`` is true, a permit minted
    by ``permit.mint`` for ``route`` and ``session_token``, and the text is
    ``permit.wire_text(args, envelope)``. A None ``body`` is an empty object.
    """
    data = dict(body or {})
    if secret is None:
        text = json.dumps(data)
    else:
        args = permit_module.args_text(data)
        envelope = {"secret": secret}
        if permit:
            envelope["permit"] = permit_module.mint(secret, route, args, session_token,
                                                    _TEST_POLICY_HASH, _TEST_PERMIT_TTL_S, now=now)
        text = permit_module.wire_text(args, envelope)
    if as_type == "dict":
        return json.loads(text)
    if as_type == "text":
        return text
    return text.encode("ascii")


def request_of(body, secret=TEST_SECRET, route=TEST_ROUTE):
    """A request object the way pyRevit hands it over: ``data`` holds the body bytes, ``path`` the route.

    A None body keeps ``data=None`` (no body at all); any other body carries the
    envelope and a permit for ``secret`` and ``route``.
    """
    if body is None:
        return types.SimpleNamespace(data=None, path=route)
    return types.SimpleNamespace(data=enveloped_body(body, secret, route=route), path=route)
