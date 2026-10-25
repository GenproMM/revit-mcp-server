# -*- coding: utf-8 -*-
"""Shared Phase 6 test helpers: fake machine through the real bridge and the audit-file reader. Not a test module; needs no Revit."""

import asyncio
import base64
import glob
import json
import os

import httpx

import audit
import bridge

TOKEN_A = "11111111-1111-4111-8111-111111111111"
TOKEN_B = "22222222-2222-4222-8222-222222222222"
PORT_A, PID_A = 48884, 111
PORT_B, PID_B = 48885, 222
PREFIX = "/genpro_revit_mcp"


def selector(port, pid, token, host="127.0.0.1"):
    data = dict(host=host, port=port, pid=pid, session_token=token)
    return "revit1:" + base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


SEL_A = selector(PORT_A, PID_A, TOKEN_A)
SEL_B = selector(PORT_B, PID_B, TOKEN_B)


class Gate(object):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()


class Machine(object):
    """Listeners, identities, routes and canned replies of a fake machine."""

    def __init__(self):
        self.listeners = {PORT_A: [PID_A], PORT_B: [PID_B]}
        self.identity = {PORT_A: (PID_A, TOKEN_A), PORT_B: (PID_B, TOKEN_B)}
        self.seen = []            # (port, method, path)
        self.requests = []        # httpx.Request, in arrival order
        self.gates = {}           # (port, path) -> Gate
        self.faults = {}          # (port, path) -> exception factory
        self.replies = {}         # (port, path) -> (status_code, body_dict or raw text)
        self.titles = {PORT_A: "Project A", PORT_B: "Project B"}  # /status/ document_title
        self.clients = []         # every client the factory handed out

    def gate(self, port, route):
        gate = self.gates[(port, PREFIX + route)] = Gate()
        return gate

    def reply(self, port, route_path, status_code, body):
        """Answer one route (path as the bridge sends it, e.g. "/modify_element/").

        A dict body is sent as JSON; a str body is sent as raw text (not JSON).
        """
        self.replies[(port, PREFIX + route_path)] = (status_code, body)

    def snapshot(self, ports, **_kwargs):
        return dict((p, list(self.listeners.get(p, []))) for p in ports)

    async def respond(self, request):
        port, path = request.url.port, request.url.path
        self.seen.append((port, request.method, path))
        self.requests.append(request)
        if path == PREFIX + "/status/":
            who = self.identity.get(port)
            if who is None:
                raise httpx.ConnectError("refused", request=request)
            return httpx.Response(200, json={
                "status": "active", "document_title": self.titles.get(port),
                "process_identity": {"pid": who[0], "actual_port": port,
                                     "session_token": who[1], "revit_version": "2024"}})
        fault = self.faults.get((port, path))
        if fault is not None:
            raise fault(request)
        gate = self.gates.get((port, path))
        if gate is not None:
            gate.started.set()
            await gate.release.wait()
        canned = self.replies.get((port, path))
        if canned is not None:
            if isinstance(canned[1], str):
                return httpx.Response(canned[0], content=canned[1].encode("utf-8"))
            return httpx.Response(canned[0], json=canned[1])
        if path.startswith(PREFIX + "/get_view/"):
            payload = base64.b64encode(b"\x89PNG-bytes").decode("ascii")
            return httpx.Response(200, json={"image_data": payload})
        return httpx.Response(200, json={"port": port, "path": path})

    def client(self, target):
        client = httpx.AsyncClient(
            base_url="http://127.0.0.1:{}{}/".format(target["port"], PREFIX),
            transport=httpx.MockTransport(self.respond), trust_env=False)
        self.clients.append(client)
        return client

    def routes(self, port=None):
        """Requested (non-status) routes, as (port, method, path)."""
        return [s for s in self.seen
                if s[2] != PREFIX + "/status/" and (port is None or s[0] == port)]


def make_machine(monkeypatch):
    """Install a fresh Machine behind the real bridge (netstat and HTTP replaced)."""
    fake = Machine()
    monkeypatch.setattr(bridge, "listener_snapshot", fake.snapshot)
    monkeypatch.setattr(bridge, "_selected_client", fake.client)
    states = getattr(bridge, "_states", None)
    if isinstance(states, dict):
        states.clear()
    return fake


def release_machine():
    states = getattr(bridge, "_states", None)
    if isinstance(states, dict):
        states.clear()


def _segment_order(path):
    """(writer stem, segment number): "<stem>.jsonl" is segment 1, "<stem>.0002.jsonl" the next.

    A plain name sort would put ".0002.jsonl" before ".jsonl", so the first segment of a
    writer would read last.
    """
    stem = os.path.basename(path)[:-len(".jsonl")]
    head, dot, tail = stem.rpartition(".")
    if dot and tail.isdigit():
        return head, int(tail)
    return stem, 1


def read_entries(directory=None):
    """Flush the writer, then return every audit entry in the directory, oldest file first.

    Asserts the file contract on the way: LF-terminated lines, each one JSON object.
    """
    assert audit.flush(), "audit writer did not drain"
    directory = directory or os.environ[audit.AUDIT_DIR_ENV]
    entries = []
    for path in sorted(glob.glob(os.path.join(directory, "audit-*.jsonl")), key=_segment_order):
        with open(path, "rb") as handle:
            data = handle.read()
        assert b"\r\n" not in data, path
        if not data:
            continue
        assert data.endswith(b"\n"), path
        for raw in data.split(b"\n")[:-1]:
            entry = json.loads(raw.decode("utf-8"))
            assert isinstance(entry, dict), raw
            entries.append(entry)
    return entries
