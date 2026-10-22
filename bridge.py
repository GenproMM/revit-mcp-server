# -*- coding: utf-8 -*-
"""The single HTTP exit from this MCP server to pyRevit Routes.

CPython side only. Every tool reaches Revit through the three callables defined
here (revit_get, revit_post, revit_image); main.py only wires them into the tool
registrars. Tool modules never import this module.

Scope
-----
Serialization covers calls issued through this one MCP server process only.
Another MCP server process is not covered: each assistant session runs its own
server process, so a second session (or a second entry) has its own lock. Nor
are curl or /execute_code/ called directly. The lock is harm reduction for the
calls this process makes; it is not a correctness guarantee against other
clients and it is not access control (D-15).
Overlapping sessions against one Revit can still cross-wire until d27-c lands.
The Revit-side fix is backlog item 999.1 in .planning/ROADMAP.md (D-30).

Lock coverage
-------------
Only /status/ skips the queue: every other call to Revit, reads included, waits for the lock.
/status/ is exempt because its handler takes no doc and pyRevit serves it on its
HTTP thread, off the shared request handler (measured 0.01-0.02 s while the
handler was busy for about 4 s). /model_info/ also takes no doc, but it stays
locked because its overlap was not measured. A route joins UNLOCKED_GET only
with a live overlap measurement and the user's decision (D-28).

Why the lock exists
-------------------
pyRevit Routes shares one request handler object across its HTTP threads and
assigns the pending request without a lock. The overlap experiment of
2026-10-07 (pyRevit 6.5.3, two Revit 2024.3.30 instances,
scripts/probe_handler_overlap.py, run twice with identical verdicts) returned
phase M verdict cross-wired-mutation: the overlapped mutation answered 200 with
the other caller's output and its own body never ran. Phase R verdict
cross-wired-read: a read returned the mutation's output. So the lock is a
correctness mechanism for every call that enters the handler, not only for
mutations (d27-b). pyRevit 6.5.5 was not benched.

Residual
--------
A call the client gave up on may still be running in Revit. The lock is
released anyway so that the queue never sticks (D-13, SER-03), and the next
call can overlap the abandoned one inside pyRevit's handler.

Time budget
-----------
A call's wait for the lock is bounded by its own timeout. The request timeout
starts once the lock is held, so queueing never shrinks a call's own budget and
the worst case is about twice the timeout. A slow read, such as a clash check,
delays a mutation queued behind it, and the other way round (D-11).

Failure wording
---------------
A busy queue or a failed connect says the request was NOT sent to Revit. After a
POST was sent, a failure says the outcome is UNKNOWN. A read's failure is
reported plainly, because a read changes nothing. The lock is never held while
waiting for Revit (D-13).

Target
------
REVIT_HOST and REVIT_PORT are read once at import. An invalid REVIT_PORT makes
the server refuse to start. One process means one target; the port names a
launch slot, not a model. REVIT_PORT is a deployment and development setting:
users share one revit entry and do not add entries. An explicit incarnation
selector currently supports only GET /status/ (02-01); all other selected calls
refuse rather than falling back to this configured address. No-selector calls
retain the legacy configured path, not discovery/ambiguity guarantees. Discovery,
full selected routing and incarnation-keyed locks remain 02-03 (D-29).

Selected status checks a complete Windows netstat snapshot before HTTP and
compares the received PID, bound port and startup token. Snapshot-to-connect is
still a finite TOCTOU window, not a socket reservation or authentication. Identity
is initialized at extension startup in a fresh process, not literal OS creation.
The scoped status client never mutates the legacy base URL or a shared selection.

This module must not import mcp at module level: it is imported on the cold
start path and has to stay cheap.
"""

import os
import json
import base64
import asyncio
import binascii
import ipaddress
import re
import subprocess
import sys
import uuid
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
BASE_URL = f"http://{REVIT_HOST}:{REVIT_PORT}/genpro_revit_mcp"
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


def parse_target(selector: str) -> dict:
    """Decode a local incarnation selector, not an authentication credential."""
    if not isinstance(selector, str) or len(selector) > 1024:
        raise ValueError("Invalid target selector; rediscover Revit targets.")
    if not re.fullmatch(r"revit1:[A-Za-z0-9_-]+", selector):
        raise ValueError("Invalid target selector; rediscover Revit targets.")
    encoded = selector.split(":", 1)[1]
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate target field")
            result[key] = value
        return result
    try:
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4),
                               altchars=b"-_", validate=True)
        target = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_keys)
        if not isinstance(target, dict) or set(target) != {
            "host", "port", "pid", "session_token"
        }:
            raise ValueError("Invalid target fields")
        if target["host"] not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Only local loopback targets are supported")
        if type(target["port"]) is not int or not 1 <= target["port"] <= 65535:
            raise ValueError("Invalid target port")
        if type(target["pid"]) is not int or target["pid"] <= 0:
            raise ValueError("Invalid target PID")
        token = target["session_token"]
        if not isinstance(token, str) or str(uuid.UUID(token)) != token:
            raise ValueError("Invalid target session token")
        return target
    except (ValueError, TypeError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Invalid target selector; rediscover Revit targets: {}".format(exc)) from exc


def _netstat_endpoint_port(endpoint):
    host, separator, port = endpoint.rpartition(":")
    if not separator or not port.isascii() or not port.isdecimal():
        return None
    if not 0 <= int(port) <= 65535:
        return None
    try:
        if host.startswith("[") and host.endswith("]"):
            ipaddress.IPv6Address(host[1:-1])
        else:
            ipaddress.IPv4Address(host)
    except ValueError:
        return None
    return int(port)


def parse_netstat_listener_rows(text, ports):
    """Full approved G5 parser: preserve all owners; unknown rows fail closed."""
    if not isinstance(text, str) or not text.strip():
        return None
    non_listening = {
        "CLOSED", "SYN_SENT", "SYN_RECEIVED", "ESTABLISHED", "FIN_WAIT_1",
        "FIN_WAIT_2", "CLOSE_WAIT", "CLOSING", "LAST_ACK", "TIME_WAIT",
        "DELETE_TCB", "BOUND",
    }
    result = dict((p, []) for p in ports)
    saw_row = False
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] != "TCP":
            # Before the first row only: netstat prints its banner and column
            # heading in the OEM code page and the host language, which an ANSI
            # locale mis-decodes (ru-RU: cp866 read as cp1251). Skip such lines
            # by shape, not by text. A skipped line must carry no host:port
            # token, so a garbled data row is never dropped as a heading.
            if not saw_row and all(_netstat_endpoint_port(f) is None for f in fields):
                continue
            return None
        if len(fields) != 5:
            return None
        _, local, remote, state, raw_pid = fields
        port = _netstat_endpoint_port(local)
        if port is None or _netstat_endpoint_port(remote) is None:
            return None
        if state != "LISTENING" and state not in non_listening:
            return None
        if not raw_pid.isascii() or not raw_pid.isdecimal():
            return None
        pid = int(raw_pid)
        if state == "LISTENING" and (pid == 0 or port == 0):
            return None
        saw_row = True
        if state == "LISTENING" and port in result and pid not in result[port]:
            result[port].append(pid)
    return result if saw_row else None


def listener_snapshot(ports, run=subprocess.run, platform=None):
    """Complete Windows snapshot, never Get-NetTCPConnection or an empty fallback."""
    if (sys.platform if platform is None else platform) != "win32":
        return None
    try:
        done = run(["netstat.exe", "-ano", "-p", "tcp"],
                   capture_output=True, text=True, encoding="ascii",
                   errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    if done.returncode != 0:
        return None
    return parse_netstat_listener_rows(done.stdout, ports)


async def resolve_target(selector: str) -> dict:
    """Validate ownership before any HTTP; a snapshot does not reserve a socket."""
    target = parse_target(selector)
    snapshot = await asyncio.to_thread(listener_snapshot, [target["port"]])
    if not isinstance(snapshot, dict):
        raise ValueError("Listener inventory unavailable; request not sent. Rediscover targets.")
    owners = snapshot.get(target["port"])
    if not isinstance(owners, list) or any(type(p) is not int or p <= 0 for p in owners):
        raise ValueError("Listener inventory unusable; request not sent. Rediscover targets.")
    owners = sorted(set(owners))
    if len(owners) > 1:
        raise ValueError("Listener collision: PIDs {}; request not sent. Rediscover targets.".format(owners))
    if not owners:
        raise ValueError("No listener; request not sent. Rediscover targets.")
    if owners != [target["pid"]]:
        raise ValueError("Listener PID mismatch (owners {}); request not sent. Rediscover targets.".format(owners))
    return target


# --- Discovery (02-03, D-01/D-02/D-04) ---------------------------------------
# Discovery reports what a complete netstat snapshot shows inside a bounded probe
# window and what each singleton listener answers on GET /status/. It never
# predicts which port a process will take, never uses /routes/sisters, and never
# turns an unavailable inventory into an empty list.

DISCOVERY_PORT_SPAN = 128          # probe window: DEFAULT_REVIT_PORT .. +SPAN-1, plus REVIT_PORT
DISCOVERY_PROBE_HOST = "127.0.0.1"
DISCOVERY_PROBE_TIMEOUT = 3.0


def _discovery_ports():
    ports = set(range(DEFAULT_REVIT_PORT, DEFAULT_REVIT_PORT + DISCOVERY_PORT_SPAN))
    ports.add(REVIT_PORT)
    return sorted(p for p in ports if 1 <= p <= 65535)


def _selector_for(target):
    """Encode a validated incarnation as the opaque revit1 selector parse_target reads."""
    raw = json.dumps({"host": target["host"], "port": target["port"], "pid": target["pid"],
                      "session_token": target["session_token"]},
                     separators=(",", ":")).encode("utf-8")
    return "revit1:" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _identity_fields_valid(identity):
    """Shape of a received process_identity, before comparing it with anything."""
    if not isinstance(identity, dict):
        return False
    if type(identity.get("pid")) is not int or type(identity.get("actual_port")) is not int:
        return False
    token = identity.get("session_token")
    try:
        if not isinstance(token, str) or str(uuid.UUID(token)) != token:
            return False
    except ValueError:
        return False
    version = identity.get("revit_version")
    return isinstance(version, str) and bool(version.strip())


def _json_or_none(response):
    try:
        return response.json()
    except ValueError:
        return None


_INVENTORY_REFUSAL = (
    "Listener inventory unavailable (the full netstat listing was missing, "
    "malformed or incomplete); request not sent. This is not proof that no Revit "
    "is running. Rediscover targets once the OS listing works."
)


async def _probe_port(port, owner, timeout):
    """Handshake with ONE singleton listener: ("usable"|"unusable", entry). Never raises."""
    base = {"port": port, "pids": [owner]}
    try:
        async with _selected_client({"host": DISCOVERY_PROBE_HOST, "port": port}) as client:
            response = await client.get("status/", timeout=timeout)
    except Exception as exc:
        name = type(exc).__name__
        return "unusable", dict(base, reason="handshake-failed", detail=(
            "PID {} listens on port {} but did not answer the identity handshake ({}): "
            "Revit may still be initializing, the Routes server may be hung, or this "
            "is not Revit. Not offered as a target.".format(owner, port, name)))
    payload = _json_or_none(response) if response.status_code in (200, 503) else None
    identity = payload.get("process_identity") if isinstance(payload, dict) else None
    if not _identity_fields_valid(identity):
        return "unusable", dict(base, reason="not-revit-status", detail=(
            "PID {} listens on port {} and answered HTTP {}, but not with a Revit "
            "process identity (another service, or an extension without identity). "
            "Not offered as a target.".format(owner, port, response.status_code)))
    if identity["pid"] != owner or identity["actual_port"] != port:
        return "unusable", dict(base, reason="identity-mismatch", detail=(
            "PID {} owns port {} but the responder claims PID {} on port {}. "
            "Not offered as a target.".format(owner, port, identity["pid"], identity["actual_port"])))
    target = {"host": DISCOVERY_PROBE_HOST, "port": port, "pid": owner,
              "session_token": identity["session_token"]}
    return "usable", {
        "selector": _selector_for(target), "host": target["host"], "port": port, "pid": owner,
        "session_token": identity["session_token"],
        "revit_version": identity["revit_version"],
        "document_open": response.status_code == 200,
    }


async def discover_targets(timeout=DISCOVERY_PROBE_TIMEOUT):
    """List usable Revit incarnations and unusable listeners; the discovery facade.

    Returns {"status": "ok"|"inventory-unavailable", "message": str, "usable": [...],
    "unusable": [...]}. A port with more than one LISTENING PID is reported as an
    unusable collision naming every PID and is never handshaken. An unavailable
    inventory is its own status with empty lists: it is never "no Revit".
    """
    ports = _discovery_ports()
    snapshot = await asyncio.to_thread(listener_snapshot, ports)
    refusal = {"status": "inventory-unavailable", "message": _INVENTORY_REFUSAL,
               "usable": [], "unusable": []}
    if not isinstance(snapshot, dict):
        return refusal
    unusable, probes = [], []
    for port in ports:
        owners = snapshot.get(port)
        if not isinstance(owners, list) or any(type(p) is not int or p <= 0 for p in owners):
            return refusal
        owners = sorted(set(owners))
        if len(owners) > 1:
            unusable.append({"port": port, "pids": owners, "reason": "listener-collision", "detail": (
                "Port {} has {} LISTENING processes (PIDs {}): requests would land on an "
                "unpredictable one. Neither is offered as a target; close the extra "
                "Revit.".format(port, len(owners), ", ".join(str(p) for p in owners)))})
        elif owners:
            probes.append((port, owners[0]))
    answers = await asyncio.gather(*[_probe_port(p, o, timeout) for p, o in probes])
    usable = []
    for kind, entry in answers:
        (usable if kind == "usable" else unusable).append(entry)
    usable.sort(key=lambda e: e["port"])
    unusable.sort(key=lambda e: e["port"])
    return {"status": "ok", "message": "", "usable": usable, "unusable": unusable}


def _candidate_lines(usable):
    return "\n".join("- PID {}; Revit {}; port {}; target={}".format(
        e["pid"], e["revit_version"], e["port"], e["selector"]) for e in usable)


async def resolve_default_target():
    """The target of a call that names none: exactly one usable incarnation, else refuse.

    Never the latest, the active-looking or the default-port process (D-02). A
    port collision anywhere in the probe window also refuses, because a hidden
    second Revit means "the only one" is not established.
    """
    found = await discover_targets()
    if found["status"] != "ok":
        raise ValueError(found["message"])
    usable, unusable = found["usable"], found["unusable"]
    collisions = [u for u in unusable if u["reason"] == "listener-collision"]
    if collisions:
        raise ValueError("Listener collision: {}; request not sent. Close the extra Revit "
                         "or choose a target from discover_revit_targets.".format(
                             "; ".join("port {} PIDs {}".format(
                                 u["port"], ", ".join(str(p) for p in u["pids"]))
                                 for u in collisions)))
    if not usable:
        extra = ""
        if unusable:
            extra = " Unusable listeners: {}".format(
                "; ".join("port {} PID {} ({})".format(u["port"], u["pids"][0], u["reason"])
                          for u in unusable))
        raise ValueError("No usable Revit process found in the probed local ports; request "
                         "not sent. Start Revit or check discover_revit_targets.{}".format(extra))
    if len(usable) > 1:
        raise ValueError("Multiple usable Revit processes ({}); request not sent. Pass "
                         "target=<selector> to choose one:\n{}".format(
                             len(usable), _candidate_lines(usable)))
    entry = usable[0]
    return {"host": entry["host"], "port": entry["port"], "pid": entry["pid"],
            "session_token": entry["session_token"]}


def _selected_client(target):
    # A scoped status-only tracer; per-incarnation pools and locks belong to 02-03.
    host = target["host"]
    if host == "::1":
        host = "[::1]"
    return httpx.AsyncClient(
        base_url="http://{}:{}/genpro_revit_mcp/".format(host, target["port"]),
        trust_env=False, follow_redirects=False,
    )


async def _selected_status(selector, timeout):
    try:
        target = await resolve_target(selector)
        async with _selected_client(target) as client:
            response = await client.get("status/", timeout=timeout)
        if response.status_code not in (200, 503):
            return "Error: {} - {}".format(response.status_code, response.text)
        payload = response.json()
        identity = payload.get("process_identity") if isinstance(payload, dict) else None
        if (not isinstance(identity, dict)
                or type(identity.get("pid")) is not int
                or type(identity.get("actual_port")) is not int
                or identity.get("pid") != target["pid"]
                or identity.get("actual_port") != target["port"]
                or identity.get("session_token") != target["session_token"]
                or not isinstance(identity.get("revit_version"), str)
                or not identity["revit_version"].strip()):
            return "Error: Revit identity missing or stale; rediscover Revit targets."
        # Per-response metadata, never mutable callable/session state. Strip any
        # server-supplied verification claim before attaching our own result.
        payload.pop("_verified_process", None)
        payload["_verified_process"] = dict(identity)
        if response.status_code == 503 and not payload.get("error"):
            payload["error"] = "Revit status returned HTTP 503"
        return payload
    except Exception as exc:
        return _error_text(exc)


async def revit_get(endpoint: str, ctx: Any = None, target: Optional[str] = None,
                    **kwargs) -> Union[Dict, str]:
    """GET with an optional explicit incarnation on the status tracer only."""
    if target is not None:
        if endpoint != "/status/" or set(kwargs) - {"timeout"}:
            return "Error: Explicit targets currently support only GET /status/; request not sent."
        return await _selected_status(target, kwargs.get("timeout", 30.0))
    return await _revit_call("GET", endpoint, ctx=ctx, **kwargs)


# Seam read with getattr by the status tool: tool modules never import the
# transport, and the registrar signature is pinned by scripts/conventions.py.
revit_get.revit_target = REVIT_TARGET
# Discovery facade (02-03): tools reach discovery through the injected callable,
# never by importing this module, so the four-argument registrar stays fixed.
revit_get.discover_targets = discover_targets


async def revit_post(endpoint: str, data: Dict[str, Any], ctx: Any = None,
                     target: Optional[str] = None, **kwargs) -> Union[Dict, str]:
    """Simple POST request to Revit API; selected mutation routing is not yet enabled."""
    if target is not None:
        return "Error: Explicit targets currently support only GET /status/; request not sent."
    return await _revit_call("POST", endpoint, data=data, ctx=ctx, **kwargs)


async def revit_image(endpoint: str, ctx: Any = None, timeout: float = 60.0,
                      target: Optional[str] = None) -> Union[Any, str]:
    """GET request that returns an Image object.

    Runs through the same bounded-wait lock path as every other call (d27-b).
    """

    if target is not None:
        return "Error: Explicit targets currently support only GET /status/; request not sent."

    async def fetch() -> Union[Any, str]:
        from mcp.server.fastmcp import Image  # inside: keeps cold start cheap (D-24)

        client = _get_client()
        response = await client.get(endpoint, timeout=timeout)

        if response.status_code == 200:
            data = response.json()
            image_bytes = base64.b64decode(data["image_data"])
            return Image(data=image_bytes, format="png")
        return "Error: {} - {}".format(response.status_code, response.text)

    return await _serialized("GET", endpoint, ctx, timeout, fetch)


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


# The only GET routes that opt OUT of the lock. On the 01-04 bench (2026-10-07,
# pyRevit 6.5.3) overlapping requests through pyRevit's shared request handler
# were cross-wired (cross-wired-mutation and cross-wired-read), so every call
# takes the lock except GET /status/, whose handler takes no doc and runs on
# pyRevit's HTTP thread (measured unaffected). /model_info/ also takes no doc
# but stays locked because its overlap was not measured. Adding a key needs a
# live overlap measurement with scripts/probe_handler_overlap.py, the user's
# decision, and an update to test_unlocked_is_exactly_get_status.
UNLOCKED_GET = frozenset({"status"})

# Never unlockable, even by a mistaken edit of UNLOCKED_GET: arbitrary code
# can mutate anything, and open/save change session state (D-09).
NEVER_UNLOCKED = frozenset({"execute_code", "open_model", "save_document"})


def _route_key(endpoint: str) -> str:
    """"/ai_filter/?x=1" -> "ai_filter": tolerate query strings and slashes."""
    return endpoint.split("?", 1)[0].strip("/")


def _is_locked(method: str, endpoint: str) -> bool:
    """Whether a call must wait its turn in the queue.

    False only for a GET whose route key is in UNLOCKED_GET (that is, GET
    /status/). Fail-safe: every other route and method, including unknown ones,
    waits rather than racing. NEVER_UNLOCKED is checked first (D-09).
    """
    key = _route_key(endpoint)
    if key in NEVER_UNLOCKED:
        return True
    return not (method == "GET" and key in UNLOCKED_GET)


# The only failures where the request certainly never left this process. Every
# other transport error (ReadTimeout, WriteTimeout, ReadError,
# RemoteProtocolError, ...) may have reached Revit before it surfaced.
_NOT_SENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)

# The one progress line a call emits when it has to wait for the lock (D-14).
WAIT_MESSAGE = (
    "A previous Revit call from this MCP server is still running; this call "
    "will be sent to Revit after it finishes."
)


async def _say(ctx: Any, message: str) -> None:
    """Best-effort progress log.

    Duplicated from tools/process_tools.py: the bridge must not import tools.
    ctx.info() raises when there is no active request context; losing a
    progress line must never fail the call.
    """
    if not ctx:
        return
    try:
        await ctx.info(message)
    except Exception:
        pass


def _error_text(e: Exception) -> str:
    """"Error: <reason>" that is never bare: httpx timeouts stringify to ''."""
    return "Error: {}".format(str(e) or type(e).__name__)


def _transport_failure_message(e: httpx.TransportError, timeout: float) -> str:
    """Honest wording for a transport failure on a locked POST (D-13).

    A pre-send failure certainly changed nothing. Anything else may have been
    applied, and the text must never say it was not: a model that believes a
    maybe-applied change failed will retry blindly and apply it twice. Both
    start with a letter after "Error: " (process_tools reads digits as HTTP).
    """
    name = type(e).__name__
    if isinstance(e, _NOT_SENT_ERRORS):
        return (
            "Error: {} - could not reach Revit at {}; the request was not sent "
            "to Revit and nothing was changed.".format(name, REVIT_TARGET)
        )
    return (
        "Error: {} - the request was sent to Revit but no complete response "
        "arrived within {}s; outcome UNKNOWN - the change may have been applied "
        "in Revit. Verify the model state before retrying.".format(name, timeout)
    )


def _queue_busy_message(timeout: float) -> str:
    """The wording for a call that waited out its bound without being sent.

    The model decides whether to retry from this text alone, so it must say in
    so many words that nothing reached Revit. It starts with a letter after
    "Error: " because tools/process_tools.py reads "Error: <digits>" as an HTTP
    status.
    """
    return (
        "Error: Revit queue busy - another call from this MCP server held the "
        "queue for longer than this call's timeout ({}s). The request was "
        "NOT sent to Revit: nothing was sent and nothing was changed. It is "
        "safe to retry once the other operation has finished.".format(timeout)
    )


async def _serialized(method: str, endpoint: str, ctx: Any, timeout: float,
                      send: Any) -> Union[Dict, str, Any]:
    """The one bounded-wait lock path, shared by _revit_call and revit_image.

    ``send`` is a zero-argument coroutine function performing exactly one HTTP
    exchange. Every call except GET /status/ runs inside the lock (d27-b).

    A locked call's wait for the lock is bounded by the call's own timeout, and
    that bound stops applying the moment the lock is held. The request then gets
    its full timeout counted from acquisition, so queueing never shrinks a
    call's own budget (SER-04). Worst case is about twice the call timeout.
    """
    budget = None  # must exist before the except clause reads it
    try:
        if _is_locked(method, endpoint):
            # Emitted before the wait bound starts, so the message's own
            # latency does not consume it. Once per call, best-effort.
            if _get_lock().locked():
                await _say(ctx, WAIT_MESSAGE)
            async with asyncio.timeout(timeout) as budget:
                async with _get_lock():
                    # Lock held: the wait bound no longer applies.
                    budget.reschedule(None)
                    try:
                        return await send()
                    except httpx.TransportError as e:
                        # Returned, not raised: async with releases the lock on
                        # every exit. Never hold it waiting for Revit (SER-03).
                        # A read changes nothing, so only a POST may claim an
                        # unknown outcome (D-13).
                        if method == "POST":
                            return _transport_failure_message(e, timeout)
                        return _error_text(e)
        return await send()
    except TimeoutError:
        # Only our own wait deadline means "queue busy"; any other TimeoutError
        # must not be mislabelled, and tool functions rely on never seeing a raise.
        if budget is not None and budget.expired():
            return _queue_busy_message(timeout)
        return "Error: TimeoutError"
    except Exception as e:
        return _error_text(e)


async def _revit_call(method: str, endpoint: str, data: Dict = None, ctx: Any = None,
                      timeout: float = 30.0, params: Dict = None) -> Union[Dict, str]:
    """Internal function handling all HTTP calls.

    Every call except GET /status/ runs inside the lock (d27-b); see _serialized.
    """

    async def send() -> Union[Dict, str]:
        return await _send(method, endpoint, data, timeout, params)

    return await _serialized(method, endpoint, ctx, timeout, send)
