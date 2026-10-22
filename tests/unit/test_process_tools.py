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


# --- start_revit -----------------------------------------------------------------

class PopenRecorder:
    """Replaces subprocess.Popen: counts launches, never starts anything."""

    def __init__(self):
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        return object()

    @property
    def count(self):
        return len(self.calls)


@pytest.fixture
def popen(monkeypatch):
    recorder = PopenRecorder()
    monkeypatch.setattr(process_tools.subprocess, "Popen", recorder)
    monkeypatch.setattr(process_tools, "_POLL_INTERVAL_S", 0.01)
    return recorder


def run_start(rig, **kwargs):
    out = asyncio.run(rig.tool("start_revit")(**kwargs))
    assert isinstance(out, str)
    return out


@pytest.mark.parametrize("name, rig", [
    ("collision", lambda: Rig([ok([], [collision(48884, [3001, 3002])])])),
    ("collision beside a usable process",
     lambda: Rig([ok([usable(555, 48886)], [collision(48884, [3001, 3002])])])),
    ("initializing listener", lambda: Rig([ok([], [hung(48884, 777)])])),
    ("handshake mismatch", lambda: Rig([ok([], [{
        "port": 48884, "pids": [778], "reason": "identity-mismatch",
        "detail": "PID 778 owns port 48884 but the responder claims PID 9"}])])),
    ("inventory failure", lambda: Rig([INVENTORY_FAILURE])),
    ("discovery exception", lambda: Rig(raises=RuntimeError("boom"))),
    ("missing facade", lambda: Rig(facade=False)),
])
def test_start_revit_never_launches_when_discovery_is_inconclusive(popen, name, rig):
    rig = rig()
    out = run_start(rig, wait_seconds=0.05)
    assert popen.count == 0, name
    assert "ERROR" in out.upper() or "not launch" in out.lower()
    assert rig.status_calls == [] and rig.other_calls == []


def test_start_revit_collision_refusal_names_both_pids():
    rig = Rig([ok([], [collision(48884, [3001, 3002])])])
    out = run_start(rig, wait_seconds=0.05)
    assert "3001" in out and "3002" in out
    assert "collision" in out.lower() or "same port" in out.lower()


def test_start_revit_inventory_failure_is_not_called_no_revit():
    out = run_start(Rig([INVENTORY_FAILURE]), wait_seconds=0.05)
    assert "inventory" in out.lower() and "not proof" in out.lower()


def test_start_revit_already_running_selected_process_returns_without_launch(popen):
    rig = Rig([ok([usable(4242, 48884, document_open=False)])])
    out = run_start(rig, wait_seconds=0.05)
    assert popen.count == 0
    assert "Already Running: True" in out and "Document Open: False" in out
    assert "4242" in out and "nothing was started" in out.lower()
    assert rig.status_calls == []


def test_start_revit_with_several_running_processes_launches_nothing(popen):
    rig = Rig([ok([usable(111, 48884), usable(222, 48885)])])
    out = run_start(rig, wait_seconds=0.05)
    assert popen.count == 0
    assert "111" in out and "222" in out and "Already Running: True" in out
    assert "Document Open: unknown" in out
    assert rig.status_calls == []


def test_start_revit_proven_absence_launches_exactly_once_and_reports_observed(popen):
    rig = Rig([ok(), ok(), ok([usable(900, 48885, document_open=False, version="2027")])])
    out = run_start(rig, wait_seconds=5.0)
    assert popen.count == 1
    args, kwargs = popen.calls[0]
    assert args == [r"C:\fake\Autodesk\Revit 2027\Revit.exe"]
    assert kwargs["stdin"] is process_tools.subprocess.DEVNULL
    assert kwargs["stdout"] is process_tools.subprocess.DEVNULL
    assert kwargs["stderr"] is process_tools.subprocess.DEVNULL
    assert kwargs["close_fds"] is True
    assert rig.discover_calls == 3  # one gate + re-discovery until it was observed
    assert "Outcome: success" in out and "Already Running: False" in out
    assert "900" in out and "48885" in out and "Document Open: False" in out
    assert "48884" not in out  # a port nobody observed is never claimed
    assert rig.status_calls == []


def test_start_revit_launch_passes_model_path_and_version(popen, tmp_path, monkeypatch):
    model = tmp_path / "m.rvt"
    model.write_text("x")
    monkeypatch.setattr(process_tools, "_discover", lambda: [
        ("2027", r"C:\fake\Revit 2027\Revit.exe"), ("2024", r"C:\fake\Revit 2024\Revit.exe")])
    rig = Rig([ok(), ok([usable(901, 48884)])])
    out = run_start(rig, version="2024", model_path=str(model), wait_seconds=5.0)
    assert popen.count == 1
    assert popen.calls[0][0] == [r"C:\fake\Revit 2024\Revit.exe", str(model)]
    assert "901" in out and "Document Open: True" in out


def test_start_revit_timeout_reports_unknown_identity_never_a_port(popen):
    rig = Rig([ok()])
    out = run_start(rig, wait_seconds=0.1)
    assert popen.count == 1
    assert "Outcome: timeout" in out
    assert "Observed Processes: unknown" in out
    assert "48884" not in out and "48885" not in out
    assert "get_revit_process_status" in out


def test_start_revit_collision_after_launch_stops_waiting_and_launches_no_second(popen):
    rig = Rig([ok(), ok([], [collision(48884, [41, 42])])])
    out = run_start(rig, wait_seconds=5.0)
    assert popen.count == 1
    assert "Outcome: unknown" in out
    assert "41" in out and "42" in out
    assert "Observed Processes: unknown" in out


def test_start_revit_keeps_polling_through_an_inventory_blip_after_launch(popen):
    rig = Rig([ok(), INVENTORY_FAILURE, ok(), ok([usable(902, 48884)])])
    out = run_start(rig, wait_seconds=5.0)
    assert popen.count == 1
    assert "Outcome: success" in out and "902" in out


def test_start_revit_refuses_missing_model_before_launch(popen):
    out = run_start(Rig([ok()]), model_path=r"C:\definitely\missing\x.rvt", wait_seconds=0.05)
    assert popen.count == 0
    assert "not found" in out.lower()


def test_start_revit_refuses_an_uninstalled_version_before_launch(popen):
    out = run_start(Rig([ok()]), version="1999", wait_seconds=0.05)
    assert popen.count == 0
    assert "1999" in out and "not installed" in out.lower()


def test_start_revit_docstring_drops_the_one_entry_one_port_promise():
    server = FakeServer()
    process_tools.register_process_tools(server, Rig(facade=False).revit_get)
    doc = server.tools["start_revit"].__doc__
    assert "REVIT_PORT" not in doc and "first port" not in doc and "48884" not in doc
    for word in ("collision", "discover_revit_targets", "target", "unknown", "ctx"):
        assert word in doc
