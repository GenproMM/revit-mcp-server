# -*- coding: utf-8 -*-
"""Shared setup for the Revit-free unit suite.

Everything under tests/unit/ must run with no Revit, no pyRevit and no network,
so that a contributor can prove a change before touching a workstation. The two
standalone scripts in tests/ are a different tier: they drive a real server over
stdio and are excluded from collection by [tool.pytest.ini_options].
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_revit_from_the_bridge(monkeypatch):
    """No unit test may reach a real Revit through bridge.py.

    A call with no target selector resolves its process by reading the OS
    listener table and handshaking over HTTP. On a workstation with Revit open
    that would silently talk to the user's live process, so the default is a
    listener inventory that is unavailable: discovery refuses before any HTTP.
    A test that wants a process fakes BOTH listener_snapshot and the client
    factory itself, which overrides this default.
    """
    import bridge

    import httpx

    real_snapshot = bridge.listener_snapshot

    def guarded_snapshot(ports, run=None, platform=None):
        # Only a caller that injects its own `run` (a test of the adapter itself)
        # reaches the real function; the default never reads the host's sockets.
        if run is None:
            return None
        return real_snapshot(ports, run=run, platform=platform)

    def refuse(request):
        raise httpx.ConnectError("unit tests never reach a real Revit", request=request)

    def refusing_client(*args, **kwargs):
        return httpx.AsyncClient(base_url="http://127.0.0.1:1/genpro_revit_mcp/",
                                 transport=httpx.MockTransport(refuse), trust_env=False)

    monkeypatch.setattr(bridge, "listener_snapshot", guarded_snapshot)
    if hasattr(bridge, "_states"):  # pooled clients and locks never leak between tests
        monkeypatch.setattr(bridge, "_states", {})
    if hasattr(bridge, "_selected_client"):
        monkeypatch.setattr(bridge, "_selected_client", refusing_client)
    if hasattr(bridge, "_http_client"):  # the single-target client, until it is retired
        monkeypatch.setattr(bridge, "_http_client", refusing_client())
