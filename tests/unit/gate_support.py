# -*- coding: utf-8 -*-
"""Shared Phase 5 test helper: configure the Revit-side gate state and build enveloped bodies. Not a test module; needs no Revit."""

import json
import types

# A fixed test value, 32+ characters. Never the developer's real secret.
TEST_SECRET = "phase5-test-secret-0123456789-abcdefXYZ"


def configure_gate(monkeypatch, secret=TEST_SECRET, integrity=None):
    """Put revit_mcp.security into a configured state for one test.

    The state is the one security.initialize would compute at extension load:
    ``secret`` (None reads as "server_not_configured") and an integrity result
    (unverifiable/manifest_missing by default, which blocks nothing). Tests
    configure the state and send the envelope; production has no bypass.
    """
    from revit_mcp import security, trust

    if integrity is None:
        integrity = trust.unverifiable(trust.REASON_MANIFEST_MISSING)
    monkeypatch.setattr(security, "_STATE", {"secret": secret, "integrity": integrity})


def enveloped_body(body, secret=TEST_SECRET, as_type="bytes"):
    """``body`` plus the reserved ``_mcp`` envelope, as bytes, text or a dict.

    A None ``secret`` adds no envelope at all (the "missing" case). A None
    ``body`` is an empty object.
    """
    data = dict(body or {})
    if secret is not None:
        data["_mcp"] = {"secret": secret}
    if as_type == "dict":
        return data
    text = json.dumps(data)
    if as_type == "text":
        return text
    return text.encode("utf-8")


def request_of(body, secret=TEST_SECRET):
    """A request object the way pyRevit hands it over: ``data`` holds the body bytes.

    A None body keeps ``data=None`` (no body at all); any other body carries the
    envelope for ``secret``.
    """
    if body is None:
        return types.SimpleNamespace(data=None)
    return types.SimpleNamespace(data=enveloped_body(body, secret))
