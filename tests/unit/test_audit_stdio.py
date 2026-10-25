# -*- coding: utf-8 -*-
"""ROADMAP criterion 4 / AUDIT-05: the audit writer never writes to stdout; a real stdio session stays pure JSON-RPC. The session row needs Windows (netstat), no Revit."""

import ast
import glob
import json
import logging
import logging.handlers
import os
import queue
import subprocess
import sys
import threading
import time

import pytest

import audit
from audit_support import FakeRevitServer
from gate_support import TEST_SECRET

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN = os.path.join(REPO_ROOT, "main.py")
USER_REQUEST = "проверка"


def _tree(name):
    path = os.path.join(REPO_ROOT, name)
    with open(path, "rb") as handle:
        return ast.parse(handle.read().decode("utf-8"), filename=path)


# ---------------------------------------------------------------- static rows

@pytest.mark.parametrize("module", ["audit.py", "bridge.py"])
def test_static_no_path_to_stdout_in_the_audit_and_bridge_sources(module):
    offenders = []
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            offenders.append("print() at line %d" % node.lineno)
        if (isinstance(node, ast.Attribute) and node.attr == "stdout"
                and isinstance(node.value, ast.Name) and node.value.id == "sys"):
            offenders.append("sys.stdout at line %d" % node.lineno)
        name = node.id if isinstance(node, ast.Name) else (
            node.attr if isinstance(node, ast.Attribute) else None)
        if name in ("StreamHandler", "basicConfig"):
            offenders.append("%s at line %d" % (name, node.lineno))
    assert offenders == [], "%s reaches stdout: %s" % (module, offenders)


def test_static_the_only_print_in_main_py_sits_in_the_combined_branch():
    tree = _tree("main.py")
    prints = [node for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == "print"]
    assert len(prints) == 1
    main_block = next(
        node for node in tree.body
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__")
    combined = None
    for node in ast.walk(main_block):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Constant)
                and node.test.left.value == "--combined"):
            combined = node
    assert combined is not None, "the --combined branch is gone"
    assert prints[0] in list(ast.walk(combined))


# ----------------------------------------------------------------- logger row

def test_logger_does_not_propagate_and_has_exactly_one_queue_handler():
    root_before = list(logging.getLogger().handlers)
    assert audit.record_call(
        audit.CallState("c-1", "set_parameter", {}, None), "POST", "/set_parameter/1",
        {"kind": "received", "requested": None, "http_status": 200, "corroborated": True,
         "process": None},
        {"status": "success"}, duration_ms=1, secret=None) is not None
    assert audit.flush()
    logger = logging.getLogger(audit.LOGGER_NAME)
    assert logger.propagate is False
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.handlers.QueueHandler)
    assert list(logging.getLogger().handlers) == root_before


# ---------------------------------------------------------------- session row

class _Session(object):
    """A main.py stdio server in a subprocess; stdout lines arrive on a queue."""

    def __init__(self, audit_directory):
        code = ("import runpy, bridge; bridge._secret_cache = %r; "
                "runpy.run_path(%r, run_name='__main__')" % (TEST_SECRET, MAIN))
        env = dict(os.environ, REVIT_MCP_AUDIT_DIR=str(audit_directory), PYTHONUTF8="1")
        self.process = subprocess.Popen(
            [sys.executable, "-c", code], cwd=REPO_ROOT, env=env, text=True, encoding="utf-8",
            bufsize=1, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.lines = queue.Queue()
        self.stderr = []
        self._threads = [
            threading.Thread(target=self._pump, args=(self.process.stdout, self.lines.put),
                             daemon=True),
            threading.Thread(target=self._pump, args=(self.process.stderr, self.stderr.append),
                             daemon=True)]
        for thread in self._threads:
            thread.start()

    @staticmethod
    def _pump(stream, sink):
        for line in iter(stream.readline, ""):
            sink(line)

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def collect(self, wanted_ids, timeout=30.0):
        """Every stdout line until responses for ``wanted_ids`` arrived; raises on the deadline."""
        deadline = time.monotonic() + timeout
        seen, raw = set(), []
        while not set(wanted_ids) <= seen:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("no responses %s within %ss; got %r; stderr %r" % (
                    sorted(set(wanted_ids) - seen), timeout, raw, "".join(self.stderr)))
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty:
                continue
            raw.append(line)
            try:
                message = json.loads(line)
            except ValueError:
                continue  # reported by the caller's per-line check
            if isinstance(message, dict) and message.get("id") is not None:
                seen.add(message["id"])
        return raw

    def finish(self):
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=20)
        finally:
            self.close()
        for thread in self._threads:
            thread.join(5)
        rest = []
        while True:
            try:
                rest.append(self.lines.get_nowait())
            except queue.Empty:
                break
        return rest

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(10)


@pytest.mark.skipif(sys.platform != "win32", reason="the real bridge reads netstat.exe")
def test_session_stdout_stays_pure_json_rpc_while_the_audit_file_fills(tmp_path):
    with FakeRevitServer() as fake:
        session = _Session(tmp_path)
        try:
            session.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "audit-stdio-test", "version": "0"}}})
            session.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            session.send({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "get_revit_status", "arguments": {"target": fake.selector}}})
            session.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "execute_revit_code", "arguments": {
                    "code": "print(1)", "target": fake.selector, "user_request": USER_REQUEST}}})
            lines = session.collect({1, 2, 3})
        finally:
            lines_after = session.finish()
    lines = lines + lines_after
    stderr = "".join(session.stderr)

    messages = []
    for line in lines:
        message = json.loads(line)  # a stray byte on stdout fails here
        assert isinstance(message, dict) and message.get("jsonrpc") == "2.0", line
        messages.append(message)
    by_id = dict((m["id"], m) for m in messages if m.get("id") is not None)
    assert {1, 2, 3} <= set(by_id)
    for key in (2, 3):
        assert "error" not in by_id[key], by_id[key]
    text = "".join(part.get("text", "") for part in by_id[3]["result"]["content"])
    assert "Audit: call_id " in text, text

    files = glob.glob(os.path.join(str(tmp_path), "audit-*.jsonl"))
    assert len(files) == 1
    with open(files[0], "rb") as handle:
        data = handle.read()
    assert TEST_SECRET.encode("utf-8") not in data
    assert TEST_SECRET not in stderr
    entries = [json.loads(raw.decode("utf-8")) for raw in data.split(b"\n") if raw]
    status = [e for e in entries if e["tool"] == "get_revit_status"]
    code = [e for e in entries if e["tool"] == "execute_revit_code"]
    assert len(status) == 1 and len(code) == 1
    assert code[0]["outcome"] == "success"
    assert code[0]["user_request"] == USER_REQUEST
    assert status[0]["outcome"] == "success"
