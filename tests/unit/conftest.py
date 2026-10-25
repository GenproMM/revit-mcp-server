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


@pytest.fixture(scope="session")
def _audit_base_dir(tmp_path_factory):
    """One temp base for every test's audit directory; nothing is written to the real one."""
    return tmp_path_factory.mktemp("audit-logs")


@pytest.fixture(autouse=True)
def _isolated_audit_log(monkeypatch, _audit_base_dir):
    """No unit test may write into the developer's real audit directory (Phase 6).

    REVIT_MCP_AUDIT_DIR points at a fresh, not yet created path under the session
    base; the audit writer is reset before and after the test, so its thread,
    queue and file never leak from one test into the next. The guard keeps the
    fixture safe in a tree that has no audit module.
    """
    import uuid

    try:
        import audit
    except ImportError:
        audit = None
    monkeypatch.setenv("REVIT_MCP_AUDIT_DIR", os.path.join(str(_audit_base_dir), uuid.uuid4().hex))
    if audit is not None and hasattr(audit, "_reset"):
        audit._reset()
    yield
    if audit is not None and hasattr(audit, "_reset"):
        audit._reset()


@pytest.fixture(autouse=True)
def _no_live_revit_from_the_bridge(monkeypatch):
    """No unit test may reach a real Revit through bridge.py.

    A call with no target selector resolves its process by reading the OS
    listener table and handshaking over HTTP. On a workstation with Revit open
    that would silently talk to the user's live process, so the default is a
    listener inventory that is unavailable: discovery refuses before any HTTP.
    A test that wants a process fakes BOTH listener_snapshot and the client
    factory itself, which overrides this default.

    The bridge's loaded shared secret is pinned to None for the same reason: no
    test may read the developer's real revit_mcp/_bridge_secret. A test that wants
    a secret sets bridge._secret_cache itself.
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
    if hasattr(bridge, "_secret_cache"):  # never read the developer's real revit_mcp/_bridge_secret
        monkeypatch.setattr(bridge, "_secret_cache", None)
    if hasattr(bridge, "_states"):  # pooled clients and locks never leak between tests
        monkeypatch.setattr(bridge, "_states", {})
    if hasattr(bridge, "_selected_client"):
        monkeypatch.setattr(bridge, "_selected_client", refusing_client)
    if hasattr(bridge, "_http_client"):  # the single-target client, until it is retired
        monkeypatch.setattr(bridge, "_http_client", refusing_client())


@pytest.fixture(autouse=True)
def _allow_all_authorizer(monkeypatch):
    """The unit suite's authorizer: grants every call and mints no permit (Phase 7).

    Production's default is approval.authorize, and a bridge with no authorizer refuses
    every gated POST. Most tests exercise something else (forwarding, locking, audit), so
    they get a permissive authorizer: the body keeps today's envelope (secret and call_id,
    or no envelope without a secret) and only the wire form is the exact argument text.
    A test of the real flow restores ``approval.authorize`` itself; the production code
    carries no flag that skips the authorizer. Plan 07-07 switches this fixture to mint
    real permits when the Revit gate starts to require them.
    """
    import bridge

    if not hasattr(bridge, "_authorize"):
        return
    import approval
    import permit

    async def allow_all(request):
        return approval.Grant(data=request.data, args_text=permit.args_text(request.data),
                              permit=None, audit_fields={})

    monkeypatch.setattr(bridge, "_authorize", allow_all)
