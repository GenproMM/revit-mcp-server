# -*- coding: utf-8 -*-
"""The single HTTP exit from this MCP server to pyRevit Routes.

CPython side only. Every tool reaches Revit through the three callables defined
here, which main.py injects into the tool registrars. Mutating POSTs issued
through this process are serialized behind one module-global lock, because the
Revit API is single-threaded; GET requests never take the lock.

This module must not import mcp at module level: it is imported on the cold
start path and has to stay cheap.
"""

import os
import json
import base64
import asyncio
import httpx
from typing import Optional, Dict, Any, Union

DEFAULT_REVIT_PORT = 48884  # Default pyRevit Routes port


class RevitConfigError(ValueError):
    """The deployment configuration names no usable Revit target."""


def _resolve_port(value: Optional[str]) -> int:
    """Strictly parse REVIT_PORT.

    None (variable unset) is the default. Anything else must be an ASCII
    integer in 1..65535; an empty or malformed value is refused rather than
    defaulted, because a typo must never land a mutation on a different Revit
    instance.
    """
    if value is None:
        return DEFAULT_REVIT_PORT
    text = str(value).strip()
    if not (text.isascii() and text.isdigit()):
        raise RevitConfigError(
            "REVIT_PORT must be an integer in 1..65535, got {!r}".format(value)
        )
    port = int(text)
    if not 1 <= port <= 65535:
        raise RevitConfigError("REVIT_PORT out of range 1..65535: {}".format(port))
    return port


# Configuration. Read once at import: one Revit target per MCP server process.
REVIT_HOST = os.environ.get("REVIT_HOST", "localhost")
REVIT_PORT = _resolve_port(os.environ.get("REVIT_PORT"))
BASE_URL = f"http://{REVIT_HOST}:{REVIT_PORT}/revit_mcp"
REVIT_TARGET = "{}:{}".format(REVIT_HOST, REVIT_PORT)

# Shared HTTP client with keep-alive connection pooling. Reusing a single
# AsyncClient across all tool calls avoids the per-request TCP/handshake cost
# of creating a new client each time — meaningful when a session fires dozens
# of calls at the local Routes server.
_http_client: Optional[httpx.AsyncClient] = None

# One lock per Revit target; one target per process, so one module-global lock.
# Created lazily so it binds to the running event loop, not the import-time one.
_lock: Optional[asyncio.Lock] = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            base_url=BASE_URL,
            # The MCP subprocess inherits Windows proxy settings from the
            # desktop agent.  httpx may then send localhost traffic through
            # that proxy unless NO_PROXY happens to be configured, which the
            # pyRevit Routes HTTP/1.0 server surfaces as an empty ReadError.
            # The bridge is strictly local, so environment proxies must never
            # participate in these requests.
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _http_client


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def revit_get(endpoint: str, ctx: Any = None, **kwargs) -> Union[Dict, str]:
    """Simple GET request to Revit API"""
    return await _revit_call("GET", endpoint, ctx=ctx, **kwargs)


# Seam read with getattr by the status tool: tool modules never import the
# transport, and the registrar signature is pinned by scripts/conventions.py.
revit_get.revit_target = REVIT_TARGET


async def revit_post(endpoint: str, data: Dict[str, Any], ctx: Any = None, **kwargs) -> Union[Dict, str]:
    """Simple POST request to Revit API"""
    return await _revit_call("POST", endpoint, data=data, ctx=ctx, **kwargs)


async def revit_image(endpoint: str, ctx: Any = None) -> Union[Any, str]:
    """GET request that returns an Image object"""
    try:
        from mcp.server.fastmcp import Image

        client = _get_client()
        response = await client.get(endpoint, timeout=60.0)

        if response.status_code == 200:
            data = response.json()
            image_bytes = base64.b64decode(data["image_data"])
            return Image(data=image_bytes, format="png")
        else:
            return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error: {e}"


async def _send(method: str, endpoint: str, data: Optional[Dict],
                timeout: float, params: Optional[Dict]) -> Union[Dict, str]:
    """The one HTTP send. Does no locking; callers decide."""
    client = _get_client()

    if method == "GET":
        response = await client.get(endpoint, params=params, timeout=timeout)
    else:  # POST
        # The body is JSON, but it is deliberately declared text/plain.
        # pyRevit parses an application/json body itself, before any route
        # handler runs, and that parse is broken under IronPython 3: it
        # passes the raw bytes to a 3.5-level json.loads, which rejects them
        # with "the JSON object must be str, not 'bytes'" and answers 500.
        # Declaring text/plain leaves the body untouched for the route to
        # parse -- see revit_mcp/textutils.py:parse_request_data, which is
        # the other half of this contract.
        response = await client.post(
            endpoint,
            content=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=timeout,
        )

    return response.json() if response.status_code == 200 else "Error: {} - {}".format(response.status_code, response.text)


async def _revit_call(method: str, endpoint: str, data: Dict = None, ctx: Any = None,
                      timeout: float = 30.0, params: Dict = None) -> Union[Dict, str]:
    """Internal function handling all HTTP calls.

    Every POST is treated as a mutation and runs inside the lock (fail-safe
    default); GET never touches it.
    """
    try:
        if method == "POST":
            async with _get_lock():
                return await _send(method, endpoint, data, timeout, params)
        return await _send(method, endpoint, data, timeout, params)
    except Exception as e:
        return f"Error: {e}"
