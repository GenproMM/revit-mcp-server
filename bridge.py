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
One shared revit entry serves every Revit process on this machine (D-01). A
call names its process with an opaque revit1 selector (the target argument, from
discover_revit_targets), or names none: then exactly one usable process must
exist, otherwise the call is refused with the candidates and nothing is sent
(D-02). Never the latest, the active-looking or the default-port process, and
never a mutable per-session choice. A process incarnation is host, port, PID and
session token: a restart is a new incarnation even on a reused port or PID, so
its selector must be rediscovered.

Each incarnation owns one pooled client and one lock (D-03). Calls to one
process queue behind each other whatever document they address; calls to
different processes overlap. A superseded incarnation's state is evicted, and an
in-flight call keeps its client until it finishes.

Before every requested send the bridge reads a complete Windows netstat snapshot,
refuses a missing, duplicated or foreign listener, and proves the incarnation with
a GET /status/ identity handshake (PID, bound port, startup token). A refusal says
the request was NOT sent. Snapshot-to-send is still a finite TOCTOU window, not a
socket reservation or authentication. Identity is initialized at extension
startup in a fresh process, not literal OS creation. A usable process with no open
document answers its handshake with HTTP 503 and stays addressable.

REVIT_HOST and REVIT_PORT are read once at import. An invalid REVIT_PORT makes
the server refuse to start. They no longer route a call: REVIT_PORT only adds its
port to the discovery probe window, and discovery probes loopback addresses.
REVIT_PORT is a deployment and development setting: users share one revit entry
and do not add entries.

Provenance
----------
A complete reply from an incarnation proven before the send is returned tagged
with metadata (PROVENANCE_ATTR on a dict or str subclass, never a key in the
body, so a route cannot forge it): the verified process, the HTTP status and
whether the reply's own process stamp agrees. A reply whose stamp names another
process is discarded. A result that was not received (refused before the send,
queue busy, connect failure, no complete reply, outcome unknown) is tagged too
but credits no process and no document. tools/utils.py format_response renders
the tag; the document is only ever the one the route reports in its reply.

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
    return await _check_owner(parse_target(selector))


async def _check_owner(target: dict) -> dict:
    """Exactly one LISTENING PID on the target's port, and it is the target's PID."""
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
HANDSHAKE_TIMEOUT = 10.0           # cap on the identity handshake before a locked send


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
    for entry in usable:
        # A freshly proven incarnation supersedes older state on its port.
        await _retire_stale(entry["host"], entry["port"], _target_key(entry))
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


# --- Response provenance (02-16, D-05/D-06) -----------------------------------
# Kinds: "received" (complete reply from a proven process), "not-sent" (nothing
# left this process), "unknown" (a POST was sent and no complete, trustworthy
# reply came back), "no-reply" (a read got no usable reply) and
# "unverified-reply" (a reply arrived but the answering process was not proven).
# Only "received" carries a process; no kind ever carries a document, which is
# whatever the route itself reports in its body.

PROVENANCE_ATTR = "revit_provenance"  # keep in step with tools/utils.py


class ProvenanceDict(dict):
    """A received reply body; provenance is an attribute, so equality and JSON are unchanged."""


class ProvenanceText(str):
    """An error text; provenance is an attribute, so equality and startswith are unchanged."""


def _tag(value, provenance):
    if isinstance(value, dict):
        tagged = ProvenanceDict(value)
    elif isinstance(value, str):
        tagged = ProvenanceText(value)
    else:
        return value  # image bytes and other non-text results have no text channel
    setattr(tagged, PROVENANCE_ATTR, provenance)
    return tagged


def _meta(kind, requested=None, process=None, http_status=None, corroborated=None):
    return {"kind": kind, "requested": requested, "process": process,
            "http_status": http_status, "corroborated": corroborated}


def _requested_of(target):
    """The target a call was ASKED to reach; never evidence of who answered."""
    return {"address": _address_of(target), "pid": target["pid"]}


def _process_of(identity):
    return {"pid": identity["pid"], "actual_port": identity["actual_port"],
            "session_token": identity["session_token"],
            "revit_version": identity["revit_version"]}


def _uncertain(text, kind, requested):
    return _tag(text, _meta(kind, requested))


_HTTP_ERROR_TEXT = re.compile(r"Error: (\d{3}) - ")


def _reply_body(result):
    """The JSON object of a received reply: the dict itself or an HTTP error text's body."""
    if isinstance(result, dict):
        return result
    match = _HTTP_ERROR_TEXT.match(result)
    if match is None:
        return None
    try:
        body = json.loads(result[match.end():])
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _stamp_agrees(stamp, identity):
    """True or False when the reply's own process stamp is well formed; None when it is not."""
    if not _identity_fields_valid(stamp):
        return None
    return (stamp["pid"] == identity["pid"] and stamp["actual_port"] == identity["actual_port"]
            and stamp["session_token"] == identity["session_token"])


def _conflict_text(method, identity, stamp):
    text = ("Error: the reply came from a different Revit process than the one verified before "
            "the send (verified PID {} on port {}; the reply names PID {} on port {}); the reply "
            "is discarded and credited to neither process.".format(
                identity["pid"], identity["actual_port"], stamp["pid"], stamp["actual_port"]))
    if method == "POST":
        text += (" The request was sent, so its outcome is UNKNOWN - the change may have been "
                 "applied. Verify the model state before retrying.")
    return text


def _received_reply(result, identity, requested, method):
    """Tag a complete reply with the process proven before the send, or refuse a conflicting one.

    Without a proven identity (a stubbed or skipped handshake) nothing is claimed
    and the result is returned untouched.
    """
    if identity is None or not isinstance(result, (dict, str)):
        return result
    http_status = 200
    if isinstance(result, str):
        match = _HTTP_ERROR_TEXT.match(result)
        http_status = int(match.group(1)) if match else None
    corroborated = None
    body = _reply_body(result)
    if body is not None:
        stamp = body.get("process_identity")
        agrees = _stamp_agrees(stamp, identity)
        if agrees is False:
            kind = "unknown" if method == "POST" else "no-reply"
            return _uncertain(_conflict_text(method, identity, stamp), kind, requested)
        corroborated = agrees
        if isinstance(result, dict):
            result.pop("_verified_process", None)  # only this bridge may say who was verified
    return _tag(result, _meta("received", requested, _process_of(identity), http_status, corroborated))


# --- Per-incarnation state (02-03, D-03) --------------------------------------
# One pooled client and one lock per validated incarnation. The key is the whole
# incarnation, never the port or the document: a process restarted on a reused
# port or PID gets fresh state, and two documents of one process share one lock.

class _TargetState(object):
    """Pool, queue and bookkeeping of ONE process incarnation."""

    __slots__ = ("key", "client", "lock", "users", "verified", "evicted", "identity")

    def __init__(self, key):
        self.key = key
        self.client = None
        self.lock = asyncio.Lock()
        self.users = 0          # calls currently queued on, holding or using this state
        self.verified = False   # an identity handshake has succeeded for this key
        self.identity = None    # the process_identity that handshake proved (read with the lock held)
        self.evicted = False    # superseded: closed when the last user lets go


_states = {}


def _target_key(target):
    host = target["host"]
    if host == "localhost":
        host = "127.0.0.1"
    return (host, target["port"], target["pid"], target["session_token"])


def _state_for(target):
    key = _target_key(target)
    state = _states.get(key)
    if state is None:
        state = _states[key] = _TargetState(key)
    return state


def _client_of(state, target):
    if state.client is None or state.client.is_closed:
        state.client = _selected_client(target)
    return state.client


def _get_client(target):
    return _client_of(_state_for(target), target)


def _get_lock(target):
    return _state_for(target).lock


def _selected_client(target):
    """Build (not cache) a client for one process; _get_client pools it per incarnation."""
    host = target["host"]
    if host == "::1":
        host = "[::1]"
    return httpx.AsyncClient(
        base_url="http://{}:{}/genpro_revit_mcp/".format(host, target["port"]),
        # The MCP subprocess inherits Windows proxy settings from the desktop
        # agent. httpx may then send localhost traffic through that proxy unless
        # NO_PROXY happens to be configured, which the pyRevit Routes HTTP/1.0
        # server surfaces as an empty ReadError. The bridge is strictly local, so
        # environment proxies must never participate in these requests.
        trust_env=False, follow_redirects=False,
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
    )


def _address_of(target):
    return "{}:{}".format(target["host"], target["port"])


async def _close_state(state):
    client, state.client = state.client, None
    if client is not None and not client.is_closed:
        try:
            await client.aclose()
        except Exception:
            pass


async def _retire_stale(host, port, keep_key):
    """A verified incarnation supersedes every other one on its host and port.

    The old state leaves the map at once, so nothing new can use it. Its client
    is closed now if idle, otherwise by the last in-flight call that releases it.
    """
    for key in [k for k in _states if k[0] == host and k[1] == port and k != keep_key]:
        old = _states.pop(key, None)  # another task may have retired it across an await
        if old is None:
            continue
        old.evicted = True
        if old.users == 0:
            await _close_state(old)


async def _release(state):
    state.users -= 1
    if state.users > 0:
        return
    if state.evicted or not state.verified:
        # Superseded, or never proven: a stale selector must leave nothing behind.
        if _states.get(state.key) is state:
            del _states[state.key]
        await _close_state(state)


class _UnexpectedStatus(Exception):
    """The identity route answered something other than 200 or 503."""

    def __init__(self, status, text):
        Exception.__init__(self, "HTTP {}".format(status))
        self.status = status
        self.text = text


async def _handshake(target, client, timeout):
    """Prove ownership, then identity: (response, payload).

    A ValueError means the incarnation is refused before any requested send. The
    handshake requests GET /status/ only, never a model route.
    """
    await _check_owner(target)
    response = await client.get("status/", timeout=timeout)
    if response.status_code not in (200, 503):
        raise _UnexpectedStatus(response.status_code, response.text)
    payload = _json_or_none(response)
    identity = payload.get("process_identity") if isinstance(payload, dict) else None
    if not (_identity_fields_valid(identity)
            and identity["pid"] == target["pid"]
            and identity["actual_port"] == target["port"]
            and identity["session_token"] == target["session_token"]):
        raise ValueError("Revit identity missing or stale; request not sent. "
                         "Rediscover Revit targets.")
    return response, payload


async def _verify_target(target, state, timeout):
    """Refusal text if the incarnation cannot be proven right now, else None.

    Runs with the lock held, immediately before the requested send, so a process
    that restarted while the call queued is caught. Every refusal here says the
    request was NOT sent.
    """
    state.identity = None
    try:
        # Capped: the lock is held, and a Revit that is still initializing hangs
        # instead of failing, so the handshake must never wait out a long call.
        _response, payload = await _handshake(
            target, _client_of(state, target), min(timeout, HANDSHAKE_TIMEOUT))
    except _UnexpectedStatus as exc:
        state.verified = False
        return ("Error: Revit identity handshake answered HTTP {}; the request was NOT sent "
                "to Revit and nothing was changed. Rediscover Revit targets.".format(exc.status))
    except httpx.HTTPError as exc:
        state.verified = False
        return ("Error: {} - identity handshake with Revit at {} failed; the request was NOT "
                "sent to Revit and nothing was changed. Rediscover Revit "
                "targets.".format(type(exc).__name__, _address_of(target)))
    except ValueError as exc:
        state.verified = False
        return _error_text(exc)
    state.identity = _process_of(payload["process_identity"])
    state.verified = True
    await _retire_stale(state.key[0], state.key[1], state.key)
    return None


async def _status_call(selector, timeout):
    """GET /status/ for one incarnation, the single unlocked route.

    With a selector the result is the received payload plus per-response
    _verified_process metadata (a 503 keeps its identity and gains an error). With
    none, exactly one usable process must exist and the result keeps the legacy
    shapes: the payload for 200, "Error: <code> - <body>" otherwise.
    """
    state = None
    requested = None
    try:
        target = parse_target(selector) if selector is not None else await resolve_default_target()
        requested = _requested_of(target)
        state = _state_for(target)
        state.users += 1
        response, payload = await _handshake(target, _client_of(state, target), timeout)
        state.verified = True
        await _retire_stale(state.key[0], state.key[1], state.key)
        # The handshake proved PID, bound port and startup token before this reply
        # is used, and the reply's own stamp is that same identity.
        meta = _meta("received", requested, _process_of(payload["process_identity"]),
                     response.status_code, True)
        if selector is None:
            if response.status_code == 200:
                return _tag(payload, meta)
            return _tag("Error: {} - {}".format(response.status_code, response.text), meta)
        # Per-response metadata, never mutable callable/session state. Strip any
        # server-supplied verification claim before attaching our own result.
        payload.pop("_verified_process", None)
        payload["_verified_process"] = dict(payload["process_identity"])
        if response.status_code == 503 and not payload.get("error"):
            payload["error"] = "Revit status returned HTTP 503"
        return _tag(payload, meta)
    except _UnexpectedStatus as exc:
        if state is not None:
            state.verified = False
        return _tag("Error: {} - {}".format(exc.status, exc.text),
                    _meta("unverified-reply", requested, http_status=exc.status))
    except Exception as exc:
        if state is not None:
            state.verified = False
        kind = "not-sent" if (not isinstance(exc, httpx.TransportError)
                              or isinstance(exc, _NOT_SENT_ERRORS)) else "no-reply"
        return _uncertain(_error_text(exc), kind, requested)
    finally:
        if state is not None:
            await _release(state)


async def revit_get(endpoint: str, ctx: Any = None, target: Optional[str] = None,
                    timeout: float = 30.0, params: Optional[Dict] = None) -> Union[Dict, str]:
    """GET one Revit route, on the selected incarnation or the only usable one."""
    if endpoint == "/status/" and params is None:
        return await _status_call(target, timeout)

    async def read(client) -> Union[Dict, str]:
        return await _send(client, "GET", endpoint, None, timeout, params)

    return await _dispatch("GET", endpoint, ctx, timeout, read, target)


# Seam read with getattr by the status tool: tool modules never import the
# transport, and the registrar signature is pinned by scripts/conventions.py.
revit_get.revit_target = REVIT_TARGET
# Discovery facade (02-03): tools reach discovery through the injected callable,
# never by importing this module, so the four-argument registrar stays fixed.
revit_get.discover_targets = discover_targets


async def revit_post(endpoint: str, data: Dict[str, Any], ctx: Any = None,
                     target: Optional[str] = None, timeout: float = 30.0,
                     params: Optional[Dict] = None) -> Union[Dict, str]:
    """POST to one Revit route, on the selected incarnation or the only usable one."""

    async def write(client) -> Union[Dict, str]:
        return await _send(client, "POST", endpoint, data, timeout, params)

    return await _dispatch("POST", endpoint, ctx, timeout, write, target)


async def revit_image(endpoint: str, ctx: Any = None, timeout: float = 60.0,
                      target: Optional[str] = None) -> Union[Any, str]:
    """GET request that returns an Image object.

    Runs through the same bounded-wait, per-incarnation lock path as every other
    call (d27-b, D-03).
    """

    async def fetch(client) -> Union[Any, str]:
        from mcp.server.fastmcp import Image  # inside: keeps cold start cheap (D-24)

        response = await client.get(endpoint, timeout=timeout)

        if response.status_code == 200:
            data = response.json()
            image_bytes = base64.b64decode(data["image_data"])
            return Image(data=image_bytes, format="png")
        return "Error: {} - {}".format(response.status_code, response.text)

    return await _dispatch("GET", endpoint, ctx, timeout, fetch, target)


async def _send(client: httpx.AsyncClient, method: str, endpoint: str, data: Optional[Dict],
                timeout: float, params: Optional[Dict]) -> Union[Dict, str]:
    """The one HTTP send. Does no locking; callers decide."""
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


def _transport_failure_message(e: httpx.TransportError, timeout: float,
                               address: str = REVIT_TARGET) -> str:
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
            "to Revit and nothing was changed.".format(name, address)
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


async def _dispatch(method: str, endpoint: str, ctx: Any, timeout: float, exchange: Any,
                    target: Optional[str] = None) -> Union[Dict, str, Any]:
    """The one bounded-wait, per-incarnation lock path for every non-status call.

    ``exchange`` is a coroutine function taking the incarnation's client and
    performing exactly one HTTP exchange. The process is the explicit target or
    the only usable one (a refusal is returned, nothing sent). Every call except
    GET /status/ runs inside that incarnation's lock (d27-b, D-03), and the
    incarnation is proven again with the lock held, right before the send.

    A locked call's wait for the lock is bounded by the call's own timeout, and
    that bound stops applying the moment the lock is held. The request then gets
    its full timeout counted from acquisition, so queueing never shrinks a
    call's own budget (SER-04). Worst case is about twice the call timeout.
    """
    budget = None  # must exist before the except clause reads it
    state = None
    requested = None
    progress = {"sent": False}  # whether the requested exchange was ever started
    try:
        resolved = parse_target(target) if target is not None else await resolve_default_target()
        requested = _requested_of(resolved)
        state = _state_for(resolved)
        state.users += 1
        if _is_locked(method, endpoint):
            # Emitted before the wait bound starts, so the message's own
            # latency does not consume it. Once per call, best-effort.
            if state.lock.locked():
                await _say(ctx, WAIT_MESSAGE)
            async with asyncio.timeout(timeout) as budget:
                async with state.lock:
                    # Lock held: the wait bound no longer applies.
                    budget.reschedule(None)
                    # Returned, not raised: async with releases the lock on every
                    # exit. Never hold it waiting for Revit (SER-03).
                    return await _verified_exchange(
                        method, exchange, state, resolved, requested, timeout, progress, True)
        return await _verified_exchange(
            method, exchange, state, resolved, requested, timeout, progress, False)
    except TimeoutError:
        # Only our own wait deadline means "queue busy"; any other TimeoutError
        # must not be mislabelled, and tool functions rely on never seeing a raise.
        if budget is not None and budget.expired():
            return _uncertain(_queue_busy_message(timeout), "not-sent", requested)
        return _uncertain("Error: TimeoutError", _unconfirmed_kind(method, progress), requested)
    except Exception as e:
        return _uncertain(_error_text(e), _unconfirmed_kind(method, progress), requested)
    finally:
        if state is not None:
            await _release(state)


def _unconfirmed_kind(method: str, progress: dict) -> str:
    """What an unclassified failure must be assumed to be: nothing sent, a read with no reply, or an unknown POST."""
    if not progress["sent"]:
        return "not-sent"
    return "unknown" if method == "POST" else "no-reply"


async def _verified_exchange(method: str, exchange: Any, state: "_TargetState", resolved: dict,
                             requested: dict, timeout: float, progress: dict,
                             locked: bool) -> Union[Dict, str, Any]:
    """Prove the incarnation, perform the one exchange and tag the outcome.

    A refusal is "not-sent". A complete reply is tagged with the process proven
    just before the send (or replaced by a conflict error when its own stamp names
    another process). A locked call turns transport failures into honest text
    (D-13): only a POST may claim an unknown outcome, a read changes nothing.
    """
    refusal = await _verify_target(resolved, state, timeout)
    if refusal is not None:
        return _uncertain(refusal, "not-sent", requested)
    identity = state.identity  # no await since the handshake: still this call's proof
    progress["sent"] = True
    client = _client_of(state, resolved)
    if not locked:
        return _received_reply(await exchange(client), identity, requested, method)
    try:
        result = await exchange(client)
    except httpx.TransportError as e:
        pre_send = isinstance(e, _NOT_SENT_ERRORS)
        if method == "POST":
            return _uncertain(_transport_failure_message(e, timeout, _address_of(resolved)),
                              "not-sent" if pre_send else "unknown", requested)
        return _uncertain(_error_text(e), "not-sent" if pre_send else "no-reply", requested)
    except json.JSONDecodeError as e:
        # Revit (or something in front of it) answered with a body that is not JSON.
        if method == "POST":
            return _uncertain(
                "Error: the reply to this request was not valid JSON ({}); the request was sent "
                "to Revit, so its outcome is UNKNOWN - the change may have been applied. Verify "
                "the model state before retrying.".format(type(e).__name__),
                "unknown", requested)
        return _uncertain(_error_text(e), "no-reply", requested)
    return _received_reply(result, identity, requested, method)


# ---------------------------------------------------------------- shared-secret envelope
#
# The client half of the shared-secret gate. It is built and unit-tested in Phase 3
# and is NOT sent yet: nothing calls with_envelope(), and _send posts exactly the
# bytes it always did. Phase 5 wires it. ENVELOPE_KEY is the reserved body key the
# Revit half (revit_mcp/trust.py) reads; a test pins the two constants equal.
ENVELOPE_KEY = "_mcp"
SECRET_KEY = "secret"


def with_envelope(data: Optional[Dict[str, Any]], secret: Optional[str]) -> Dict[str, Any]:
    """Return a copy of a request body that carries the shared secret under ENVELOPE_KEY.

    None data becomes {}. A body that is not a dict, or that already holds the
    reserved key, is refused with a fixed text (never the body, never the secret):
    a model-built argument must not pre-seed the envelope. A None secret adds no
    envelope at all, so the Revit half answers "missing". The argument is never
    mutated.
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object to carry the shared-secret envelope")
    if ENVELOPE_KEY in data:
        raise ValueError("request body already carries the reserved _mcp key; "
                         "refusing to merge it into the shared-secret envelope")
    body = dict(data)
    if secret is not None:
        body[ENVELOPE_KEY] = {SECRET_KEY: secret}
    return body
