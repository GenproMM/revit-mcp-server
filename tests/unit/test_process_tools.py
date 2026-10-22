# -*- coding: utf-8 -*-
"""Local process lifecycle tools under multi-target discovery (02-19).

``get_revit_process_status`` and ``start_revit`` run when Revit may be closed, so
they used to read one unselected ``/status/`` and call every non-HTTP failure
"down". With one shared MCP entry that guess is wrong twice over: a listener
collision or an unavailable inventory is not a stopped Revit, and an unselected
status call is refused (or worse, ambiguous) when several processes run.

These tests drive the tools through the real registrar (``tools.register_tools``)
with a fake ``revit_get`` that carries a fake ``discover_targets`` facade. No
Revit, no socket, no subprocess: ``subprocess.Popen`` is replaced by a recorder.
"""

import asyncio

import pytest

import tools
from tools import process_tools


class FakeServer:
    """Collects tools the way FastMCP would, without importing the server."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


def selector_of(pid):
    return "revit1:fake-selector-{}".format(pid)


def usable(pid, port, document_open=True, version="2024"):
    return {"selector": selector_of(pid), "host": "127.0.0.1", "port": port, "pid": pid,
            "session_token": "00000000-0000-4000-8000-%012d" % pid,
            "revit_version": version, "document_open": document_open}


def collision(port, pids):
    return {"port": port, "pids": list(pids), "reason": "listener-collision",
            "detail": "Port {} has {} LISTENING processes".format(port, len(pids))}


def hung(port, pid):
    return {"port": port, "pids": [pid], "reason": "handshake-failed",
            "detail": "PID {} listens on port {} but did not answer".format(pid, port)}


def ok(usable_entries=(), unusable_entries=()):
    return {"status": "ok", "message": "", "usable": list(usable_entries),
            "unusable": list(unusable_entries)}


INVENTORY_FAILURE = {"status": "inventory-unavailable", "usable": [], "unusable": [],
                     "message": "Listener inventory unavailable (the full netstat listing "
                                "was missing, malformed or incomplete); request not sent."}

STATUS_OK = {"status": "active", "health": "healthy", "process_identity": {"pid": 1},
             "_verified_process": {"pid": 1}}
STATUS_503 = {"status": "error", "error": "Revit status returned HTTP 503",
              "process_identity": {"pid": 1}, "_verified_process": {"pid": 1}}


class Rig:
    """A fake revit_get plus its discovery facade, recording every call."""

    def __init__(self, discoveries=None, selected=None, facade=True, raises=None):
        # `discoveries` is a list consumed one per discover_targets() call; the last
        # entry repeats, so a poll loop keeps seeing the final answer.
        self.discoveries = list(discoveries or [])
        self.selected = selected
        self.raises = raises
        self.status_calls = []     # (endpoint, target) for every /status/ request
        self.other_calls = []      # anything that is not /status/
        self.discover_calls = 0

        async def revit_get(endpoint, ctx=None, target=None, timeout=30.0, params=None):
            if endpoint != "/status/":
                self.other_calls.append(endpoint)
                raise AssertionError("lifecycle tools must only ask for /status/")
            self.status_calls.append((endpoint, target))
            if target is None:
                raise AssertionError("an unselected /status/ must never be requested")
            if isinstance(self.selected, Exception):
                raise self.selected
            return self.selected

        async def discover_targets():
            self.discover_calls += 1
            if self.raises is not None:
                raise self.raises
            index = min(self.discover_calls - 1, len(self.discoveries) - 1)
            return self.discoveries[index]

        if facade:
            revit_get.discover_targets = discover_targets
        self.revit_get = revit_get

    @property
    def unselected_status_calls(self):
        return [c for c in self.status_calls if c[1] is None]

    def tool(self, name):
        server = FakeServer()

        async def unused(*args, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("lifecycle tools must not use the post/image transports")

        tools.register_tools(server, self.revit_get, unused, unused)
        return server.tools[name]


@pytest.fixture(autouse=True)
def _fixed_installation(monkeypatch):
    monkeypatch.setattr(process_tools, "_discover",
                        lambda: [("2027", r"C:\fake\Autodesk\Revit 2027\Revit.exe")])


def run_status(rig):
    out = asyncio.run(rig.tool("get_revit_process_status")())
    assert isinstance(out, str)
    return out


def state_of(out):
    for line in out.splitlines():
        if line.startswith("Process State: "):
            return line[len("Process State: "):].strip()
    raise AssertionError("no 'Process State:' line in:\n" + out)


# --- get_revit_process_status ---------------------------------------------------

def test_status_zero_processes_reports_none_and_recommends_launch():
    rig = Rig([ok()])
    out = run_status(rig)
    assert state_of(out) == "none"
    assert "Revit Running: False" in out and "Ready: False" in out
    assert "start_revit" in out and "2027" in out  # installed version still reported
    assert rig.status_calls == []


def test_status_one_ready_process_asks_only_its_own_selected_status():
    rig = Rig([ok([usable(4242, 48884)])], selected=STATUS_OK)
    out = run_status(rig)
    assert state_of(out) == "one_ready"
    assert "Ready: True" in out and "Revit Running: True" in out
    assert "4242" in out and "48884" in out and "2024" in out
    assert rig.status_calls == [("/status/", selector_of(4242))]


def test_status_one_no_document_503_is_running_but_not_ready():
    rig = Rig([ok([usable(4242, 48884, document_open=False)])], selected=STATUS_503)
    out = run_status(rig)
    assert state_of(out) == "one_no_document"
    assert "Revit Running: True" in out and "Ready: False" in out
    assert "no document" in out.lower()
    recommendation = [l for l in out.splitlines() if l.startswith("Recommendation:")][0]
    assert "start_revit" not in recommendation
    assert rig.status_calls == [("/status/", selector_of(4242))]


def test_status_two_usable_lists_both_and_never_calls_status():
    rig = Rig([ok([usable(111, 48884), usable(222, 48885, document_open=False)])])
    out = run_status(rig)
    assert state_of(out) == "many"
    assert "111" in out and "222" in out and "48884" in out and "48885" in out
    assert "discover_revit_targets" in out
    assert "Ready: False" in out and "Revit Running: True" in out
    assert rig.status_calls == []


def test_status_two_pid_collision_names_both_pids_and_is_not_down():
    rig = Rig([ok([], [collision(48884, [3001, 3002])])])
    out = run_status(rig)
    assert state_of(out) == "collision"
    assert "3001" in out and "3002" in out
    assert "Revit Running: unknown" in out and "Ready: False" in out
    assert "down" not in state_of(out)
    assert "call start_revit" not in out.lower()
    assert rig.status_calls == []


def test_status_collision_beside_a_usable_process_stays_a_collision_and_lists_both():
    rig = Rig([ok([usable(555, 48886)], [collision(48884, [3001, 3002])])])
    out = run_status(rig)
    assert state_of(out) == "collision"
    assert "3001" in out and "3002" in out and "555" in out
    assert rig.status_calls == []


def test_status_inventory_failure_is_not_reported_as_no_revit():
    rig = Rig([INVENTORY_FAILURE])
    out = run_status(rig)
    assert state_of(out) == "inventory_failure"
    assert "Revit Running: unknown" in out
    assert "not proof" in out.lower() or "does not mean" in out.lower()
    assert "call start_revit" not in out.lower()
    assert rig.status_calls == []


def test_status_discovery_exception_is_a_visible_failure_not_none():
    rig = Rig(raises=RuntimeError("boom"))
    out = run_status(rig)
    assert state_of(out) == "discovery_failed"
    assert "Revit Running: unknown" in out and "boom" in out
    assert rig.status_calls == []


def test_status_missing_facade_is_a_visible_failure_not_none():
    rig = Rig(facade=False)
    out = run_status(rig)
    assert state_of(out) == "discovery_unavailable"
    assert "Revit Running: unknown" in out
    assert "call start_revit" not in out.lower()
    assert rig.status_calls == [] and rig.other_calls == []


def test_status_unresolved_listener_is_neither_none_nor_down():
    rig = Rig([ok([], [hung(48884, 777)])])
    out = run_status(rig)
    assert state_of(out) == "unresolved_listeners"
    assert "777" in out and "Revit Running: unknown" in out
    assert "call start_revit" not in out.lower()
    assert rig.status_calls == []


def test_status_selected_status_failure_keeps_the_process_visible():
    rig = Rig([ok([usable(4242, 48884)])],
              selected="Error: Revit identity missing or stale; request not sent.")
    out = run_status(rig)
    assert state_of(out) == "status_unavailable"
    assert "Revit Running: True" in out and "Ready: False" in out and "4242" in out


def test_status_selected_status_exception_never_escapes_the_tool():
    rig = Rig([ok([usable(4242, 48884)])], selected=RuntimeError("socket gone"))
    out = run_status(rig)
    assert state_of(out) == "status_unavailable"


def test_status_every_condition_renders_a_distinct_state():
    scenarios = {
        "none": Rig([ok()]),
        "one_ready": Rig([ok([usable(1, 48884)])], selected=STATUS_OK),
        "one_no_document": Rig([ok([usable(1, 48884, False)])], selected=STATUS_503),
        "many": Rig([ok([usable(1, 48884), usable(2, 48885)])]),
        "collision": Rig([ok([], [collision(48884, [8, 9])])]),
        "inventory_failure": Rig([INVENTORY_FAILURE]),
        "discovery_unavailable": Rig(facade=False),
    }
    rendered = {name: state_of(run_status(rig)) for name, rig in scenarios.items()}
    assert rendered == {name: name for name in scenarios}
    assert all(rig.unselected_status_calls == [] for rig in scenarios.values())


def test_status_docstring_names_the_multi_process_states():
    server = FakeServer()
    process_tools.register_process_tools(server, Rig(facade=False).revit_get)
    doc = server.tools["get_revit_process_status"].__doc__
    for word in ("process_state", "collision", "inventory", "discover_revit_targets"):
        assert word in doc
    assert "ctx" in doc
