# -*- coding: UTF-8 -*-
"""Process identity helper; initialized at extension startup, never at first GET.

The token survives repeated initialization within this AppDomain. This is not
literal OS process-creation timing, authentication, or arbitrary-code isolation.
"""

_KEY = "genpro_revit_mcp.process_identity.v1"


def initialize_process_identity():
    """Assign one GUID in our owned AppDomain slot during extension startup."""
    import System

    domain = System.AppDomain.CurrentDomain
    token = domain.GetData(_KEY)
    if token is None:
        token = str(System.Guid.NewGuid())
        domain.SetData(_KEY, token)
    return token


def get_process_identity(revit_version):
    """Read the initialized token and actual bound primary RoutesServer port.

    No configured/default/request port is a substitute for server_address.
    Missing startup state or unavailable bound server fails rather than guessing.
    """
    import System
    from pyrevit.coreutils import envvars

    token = System.AppDomain.CurrentDomain.GetData(_KEY)
    if not token:
        raise RuntimeError("Process identity unavailable: extension startup initialization missing")
    primary = envvars.get_pyrevit_env_var(envvars.ROUTES_SERVER)
    if primary is None:
        raise RuntimeError("Process identity unavailable: no retained RoutesServer")
    port = int(primary.server.server_address[1])
    if port < 1 or port > 65535:
        raise RuntimeError("Process identity unavailable: invalid bound port")
    version = str(revit_version) if revit_version is not None else ""
    if not version.strip():
        raise RuntimeError("Process identity unavailable: Revit version missing")
    return {
        "pid": int(System.Diagnostics.Process.GetCurrentProcess().Id),
        "actual_port": port,
        "session_token": str(token),
        "revit_version": version,
    }
