# -*- coding: utf-8 -*-
"""D-15..D-18 / AUDIT-06, AUDIT-07: segments, retention, readers, concurrency and a writer that never breaks a call. Needs no Revit."""

import asyncio
import glob
import json
import logging
import os
import subprocess
import sys
import threading

import pytest

import audit
import bridge
from audit_support import (
    PID_A, PID_B, PORT_A, PORT_B, SEL_A, SEL_B, TOKEN_A, make_machine, read_entries,
    release_machine)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DAY = 86400
MIB = 1024 * 1024
NOW = 2000000000  # whole seconds: float arithmetic on mtimes stays exact


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def machine(monkeypatch):
    fake = make_machine(monkeypatch)
    yield fake
    release_machine()


# ------------------------------------------------------------------ helpers

def make_handler(directory, stem="audit-t-1", max_bytes=200, keep=10):
    handler = audit.SegmentHandler(str(directory), stem, max_bytes, keep)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def emit(handler, text):
    handler.handle(logging.makeLogRecord({"msg": text, "levelno": logging.INFO,
                                          "levelname": "INFO"}))


def names(directory):
    return sorted(os.listdir(str(directory)))


def provenance(pid=4242, port=48884):
    return {"kind": "received", "requested": {"address": "127.0.0.1:%d" % port, "pid": pid},
            "process": {"pid": pid, "actual_port": port, "session_token": TOKEN_A,
                        "revit_version": "2024"},
            "http_status": 200, "corroborated": True}


def record(i, route_arg=None, **kwargs):
    call = audit.CallState("call-%04d" % i, "set_parameter", {"i": i}, kwargs.pop("user", None))
    body = {"status": "success", "outcome": {
        "transaction_status": "Committed", "requested": 1, "succeeded": [i], "failed": [],
        "revit_failures": []}}
    return audit.record_call(
        call, "POST", "/set_parameter/%s" % (i if route_arg is None else route_arg),
        provenance(), body, duration_ms=1, secret=None, **kwargs)


def make_file(directory, name, size=10, mtime=None, data=None):
    path = os.path.join(str(directory), name)
    with open(path, "wb") as handle:
        handle.write(data if data is not None else b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def stderr_lines(capsys):
    return [line for line in capsys.readouterr().err.splitlines() if line.strip()]


# ------------------------------------------------------------ first_write rows

def test_first_write_two_lines_that_do_not_fit_together_use_two_segments(tmp_path):
    handler = make_handler(tmp_path)
    emit(handler, "a" * 150)
    emit(handler, "b" * 150)
    handler.close()
    assert names(tmp_path) == ["audit-t-1.0002.jsonl", "audit-t-1.jsonl"]


def test_first_write_a_line_landing_exactly_on_the_cap_stays(tmp_path):
    handler = make_handler(tmp_path)
    emit(handler, "a" * 100)          # 101 bytes
    emit(handler, "b" * 98)           # 101 + 99 = 200
    assert names(tmp_path) == ["audit-t-1.jsonl"]
    assert os.path.getsize(str(tmp_path / "audit-t-1.jsonl")) == 200
    emit(handler, "c")                # 202 > 200
    handler.close()
    assert names(tmp_path) == ["audit-t-1.0002.jsonl", "audit-t-1.jsonl"]


def test_first_write_one_byte_over_the_cap_rolls(tmp_path):
    handler = make_handler(tmp_path)
    emit(handler, "a" * 100)
    emit(handler, "b" * 99)           # 101 + 100 = 201
    handler.close()
    assert names(tmp_path) == ["audit-t-1.0002.jsonl", "audit-t-1.jsonl"]


def test_first_write_an_oversize_line_is_written_whole_and_the_next_opens_a_segment(tmp_path):
    handler = make_handler(tmp_path)
    emit(handler, "z" * 500)
    assert names(tmp_path) == ["audit-t-1.jsonl"]
    assert os.path.getsize(str(tmp_path / "audit-t-1.jsonl")) == 501
    emit(handler, "next")
    handler.close()
    assert names(tmp_path) == ["audit-t-1.0002.jsonl", "audit-t-1.jsonl"]
    assert (tmp_path / "audit-t-1.jsonl").read_bytes() == b"z" * 500 + b"\n"


# ---------------------------------------------------------------- rotate rows

def test_rotate_keeps_only_the_newest_segments_and_never_renames(tmp_path):
    handler = make_handler(tmp_path, keep=3)
    for letter in "abcdef":
        emit(handler, letter * 150)   # one line per segment
    handler.close()
    assert names(tmp_path) == ["audit-t-1.0004.jsonl", "audit-t-1.0005.jsonl",
                               "audit-t-1.0006.jsonl"]
    # Each surviving file still holds the line written when it was created: nothing was renamed.
    for seq, letter in ((4, "d"), (5, "e"), (6, "f")):
        assert (tmp_path / ("audit-t-1.%04d.jsonl" % seq)).read_bytes() == \
            (letter * 150).encode() + b"\n"


def test_rotate_leaves_another_writers_segments_alone(tmp_path):
    other = make_file(tmp_path, "audit-t-2.jsonl", 20)
    handler = make_handler(tmp_path, keep=1)
    for letter in "abc":
        emit(handler, letter * 150)
    handler.close()
    assert os.path.exists(other)
    assert names(tmp_path) == ["audit-t-1.0003.jsonl", "audit-t-2.jsonl"]


# ---------------------------------------------------------------- reader row

def test_reader_holding_the_active_segment_loses_no_record(monkeypatch, capsys):
    monkeypatch.setattr(audit, "SEGMENT_MAX_BYTES", 2500)
    monkeypatch.setattr(audit, "SEGMENT_KEEP", 100)
    record(0)
    assert audit.flush()
    first = glob.glob(os.path.join(os.environ[audit.AUDIT_DIR_ENV], "audit-*.jsonl"))
    assert len(first) == 1
    with open(first[0], "rb") as reader:
        for i in range(1, 20):
            record(i)
        assert audit.flush()
        reader.read(10)
    entries = read_entries()
    assert [e["call_id"] for e in entries] == ["call-%04d" % i for i in range(20)]
    assert len(glob.glob(os.path.join(os.environ[audit.AUDIT_DIR_ENV], "audit-*.jsonl"))) > 1
    assert stderr_lines(capsys) == []


# ---------------------------------------------------------------- format rows

def test_format_no_carriage_return_in_any_segment(monkeypatch):
    monkeypatch.setattr(audit, "SEGMENT_MAX_BYTES", 2500)
    monkeypatch.setattr(audit, "SEGMENT_KEEP", 100)
    for i in range(8):
        record(i, user="line one\r\nline two")
    assert audit.flush()
    directory = os.environ[audit.AUDIT_DIR_ENV]
    for path in glob.glob(os.path.join(directory, "audit-*.jsonl")):
        with open(path, "rb") as handle:
            assert b"\r\n" not in handle.read()
    assert len(read_entries()) == 8


def test_format_a_lone_surrogate_is_written_and_the_line_still_parses(capsys):
    record(1, route_arg="bad\ud800name", user="req \udfff end")
    entries = read_entries()
    assert len(entries) == 1
    assert entries[0]["call_id"] == "call-0001"
    assert stderr_lines(capsys) == []


def test_format_a_lone_surrogate_does_not_break_the_segment_size_arithmetic(tmp_path, capsys):
    handler = make_handler(tmp_path, max_bytes=2000)
    emit(handler, "x\ud800y")
    emit(handler, "second")
    handler.close()
    assert stderr_lines(capsys) == []
    assert (tmp_path / "audit-t-1.jsonl").read_bytes() == b"x\\ud800y\nsecond\n"


# ---------------------------------------------------------------- ordering row

def test_ordering_sequential_calls_appear_in_enqueue_order():
    for i in range(50):
        record(i)
    entries = read_entries()
    assert [int(e["route_arg"]) for e in entries] == list(range(50))


# ------------------------------------------------------------- concurrent row

def _block(status, i):
    return {"transaction_status": status, "requested": 1, "succeeded": [i] if status == "Committed" else [],
            "failed": [], "revit_failures": []}


@pytest.mark.anyio
async def test_concurrent_calls_to_two_incarnations_yield_one_whole_line_each(machine):
    for i in range(100):
        if i % 2 == 0:
            machine.reply(PORT_A, "/set_parameter/%d" % i, 200,
                          {"status": "success", "outcome": _block("Committed", i)})
        else:
            machine.reply(PORT_B, "/set_parameter/%d" % i, 409,
                          {"status": "rolled_back", "transaction_status": "RolledBack",
                           "outcome": _block("RolledBack", i)})
    await asyncio.gather(*[
        bridge.revit_post("/set_parameter/%d" % i, {"i": i}, target=SEL_A if i % 2 == 0 else SEL_B)
        for i in range(100)])

    entries = read_entries()
    assert len(entries) == 100
    assert len(set(e["call_id"] for e in entries)) == 100
    seen = set()
    for entry in entries:
        i = int(entry["route_arg"])
        seen.add(i)
        assert entry["process"]["pid"] == (PID_A if i % 2 == 0 else PID_B)
        assert entry["process"]["port"] == (PORT_A if i % 2 == 0 else PORT_B)
        assert entry["outcome"] == ("success" if i % 2 == 0 else "rolled_back")
    assert seen == set(range(100))


# --------------------------------------------------------- two_processes row

_CHILD = r"""
import os, sys
import audit
for i in range(200):
    call = audit.CallState("c-%d-%d" % (os.getpid(), i), "set_parameter", {}, None)
    prov = {"kind": "received", "requested": None, "http_status": 200, "corroborated": True,
            "process": {"pid": 7, "actual_port": 48884,
                        "session_token": "11111111-1111-4111-8111-111111111111",
                        "revit_version": "2024"}}
    audit.record_call(call, "POST", "/set_parameter/%d" % i, prov,
                      {"status": "success", "outcome": {"transaction_status": "Committed",
                       "requested": 1, "succeeded": [i], "failed": [], "revit_failures": []}},
                      duration_ms=1, secret=None)
assert audit.flush(30.0)
sys.stdout.write(str(os.getpid()))
"""


def test_two_processes_write_two_distinct_files_named_with_their_own_pids(tmp_path):
    env = dict(os.environ, REVIT_MCP_AUDIT_DIR=str(tmp_path))
    children = [subprocess.Popen([sys.executable, "-c", _CHILD], cwd=REPO_ROOT, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for _ in range(2)]
    pids = []
    for child in children:
        out, err = child.communicate(timeout=60)
        assert child.returncode == 0, err.decode("utf-8", "replace")
        assert err == b""
        pids.append(int(out.decode("ascii")))
    assert pids[0] != pids[1]

    files = glob.glob(os.path.join(str(tmp_path), "audit-*.jsonl"))
    assert len(files) == 2
    by_pid = {}
    for path in files:
        stem = os.path.basename(path)[:-len(".jsonl")]
        by_pid[int(stem.rsplit("-", 1)[1])] = path
    assert sorted(by_pid) == sorted(pids)
    for pid, path in by_pid.items():
        with open(path, "rb") as handle:
            lines = handle.read().split(b"\n")
        assert lines[-1] == b""
        parsed = [json.loads(line.decode("utf-8")) for line in lines[:-1]]
        assert len(parsed) == 200
        assert all(entry["server_pid"] == pid for entry in parsed)


# ----------------------------------------------------------------- prune rows

def test_prune_age_boundary_keeps_exactly_the_limit_and_deletes_one_second_more(tmp_path):
    limit = 180 * DAY
    make_file(tmp_path, "audit-keep.jsonl", mtime=NOW - limit)
    make_file(tmp_path, "audit-gone.jsonl", mtime=NOW - limit - 1)
    deleted = audit.prune(str(tmp_path), NOW, limit, 10 * MIB)
    assert deleted == ["audit-gone.jsonl"]
    assert names(tmp_path) == ["audit-keep.jsonl"]


def test_prune_size_deletes_the_oldest_until_the_total_fits(tmp_path):
    for index, name in enumerate(("audit-a.jsonl", "audit-b.jsonl", "audit-c.jsonl")):
        make_file(tmp_path, name, MIB, mtime=NOW - 1000 + index)
    deleted = audit.prune(str(tmp_path), NOW, 180 * DAY, 2 * MIB)
    assert deleted == ["audit-a.jsonl"]
    assert names(tmp_path) == ["audit-b.jsonl", "audit-c.jsonl"]


def test_prune_size_stops_as_soon_as_the_total_is_at_the_cap(tmp_path):
    for index, name in enumerate(("audit-a.jsonl", "audit-b.jsonl", "audit-c.jsonl")):
        make_file(tmp_path, name, 1000, mtime=NOW - 100 + index)
    assert audit.prune(str(tmp_path), NOW, 180 * DAY, 3000) == []
    assert audit.prune(str(tmp_path), NOW, 180 * DAY, 2999) == ["audit-a.jsonl"]
    assert names(tmp_path) == ["audit-b.jsonl", "audit-c.jsonl"]


def test_prune_twice_deletes_nothing_the_second_time(tmp_path):
    make_file(tmp_path, "audit-old.jsonl", mtime=NOW - 400 * DAY)
    for index in range(4):
        make_file(tmp_path, "audit-%d.jsonl" % index, 1000, mtime=NOW - 100 + index)
    first = audit.prune(str(tmp_path), NOW, 180 * DAY, 2500)
    assert first == ["audit-old.jsonl", "audit-0.jsonl", "audit-1.jsonl"]
    assert audit.prune(str(tmp_path), NOW, 180 * DAY, 2500) == []
    assert names(tmp_path) == ["audit-2.jsonl", "audit-3.jsonl"]


def test_prune_never_touches_a_file_it_does_not_own(tmp_path):
    make_file(tmp_path, "notes.txt", 5000, mtime=NOW - 900 * DAY)
    make_file(tmp_path, "audit-x.json", 5000, mtime=NOW - 900 * DAY)
    make_file(tmp_path, "Audit-y.jsonl", 5000, mtime=NOW - 900 * DAY)
    folder = tmp_path / "audit-sub.jsonl"
    folder.mkdir()
    (folder / "audit-inner.jsonl").write_bytes(b"x" * 5000)
    os.utime(str(folder / "audit-inner.jsonl"), (NOW - 900 * DAY, NOW - 900 * DAY))
    make_file(tmp_path, "audit-mine.jsonl", 10, mtime=NOW - 900 * DAY)
    deleted = audit.prune(str(tmp_path), NOW, 180 * DAY, 1)
    assert deleted == ["audit-mine.jsonl"]
    assert names(tmp_path) == ["Audit-y.jsonl", "audit-sub.jsonl", "audit-x.json", "notes.txt"]
    assert (folder / "audit-inner.jsonl").exists()


def test_prune_never_follows_a_symlink(tmp_path, monkeypatch):
    make_file(tmp_path, "audit-link.jsonl", 100, mtime=NOW - 900 * DAY)
    make_file(tmp_path, "audit-real.jsonl", 100, mtime=NOW - 900 * DAY)
    real_islink = os.path.islink
    monkeypatch.setattr(os.path, "islink",
                        lambda p: os.path.basename(p) == "audit-link.jsonl" or real_islink(p))
    deleted = audit.prune(str(tmp_path), NOW, 180 * DAY, MIB)
    assert deleted == ["audit-real.jsonl"]
    assert names(tmp_path) == ["audit-link.jsonl"]


def test_prune_skips_a_file_it_cannot_delete_and_continues(tmp_path, monkeypatch):
    for index, name in enumerate(("audit-a.jsonl", "audit-b.jsonl", "audit-c.jsonl")):
        make_file(tmp_path, name, 1000, mtime=NOW - 1000 + index)
    real_remove = os.remove

    def remove(path):
        if os.path.basename(path) == "audit-a.jsonl":
            raise PermissionError(13, "held open by another server")
        real_remove(path)

    monkeypatch.setattr(os, "remove", remove)
    deleted = audit.prune(str(tmp_path), NOW, 180 * DAY, 1000)
    assert deleted == ["audit-b.jsonl", "audit-c.jsonl"]
    assert names(tmp_path) == ["audit-a.jsonl"]


def test_prune_tolerates_a_file_another_server_already_removed(tmp_path, monkeypatch):
    for index, name in enumerate(("audit-a.jsonl", "audit-b.jsonl", "audit-c.jsonl")):
        make_file(tmp_path, name, 1000, mtime=NOW - 1000 + index)
    real_remove = os.remove

    def remove(path):
        real_remove(path)
        if os.path.basename(path) == "audit-a.jsonl":
            raise FileNotFoundError(2, "already gone")

    monkeypatch.setattr(os, "remove", remove)
    deleted = audit.prune(str(tmp_path), NOW, 180 * DAY, 2000)
    # a was gone (by someone else), which already brings the total to 2000: b stays.
    assert "audit-a.jsonl" not in deleted
    assert deleted == []
    assert names(tmp_path) == ["audit-b.jsonl", "audit-c.jsonl"]


def test_prune_a_missing_directory_returns_an_empty_list(tmp_path):
    assert audit.prune(str(tmp_path / "nowhere"), NOW, DAY, MIB) == []


# ------------------------------------------------------------- settings rows

def test_settings_come_from_the_environment_in_seconds_and_mebibytes(monkeypatch):
    monkeypatch.setenv(audit.MAX_AGE_DAYS_ENV, "30")
    monkeypatch.setenv(audit.MAX_TOTAL_MB_ENV, "1")
    assert audit.retention_settings() == (30 * 86400, 1048576)


def test_settings_default_when_unset(monkeypatch):
    monkeypatch.delenv(audit.MAX_AGE_DAYS_ENV, raising=False)
    monkeypatch.delenv(audit.MAX_TOTAL_MB_ENV, raising=False)
    assert audit.retention_settings() == (180 * 86400, 500 * 1024 * 1024)


@pytest.mark.parametrize("value", ["", "  ", "abc", "0", "-5", "1.5", "0x10"])
def test_settings_fall_back_on_a_bad_value_without_raising(monkeypatch, value):
    monkeypatch.setenv(audit.MAX_AGE_DAYS_ENV, value)
    monkeypatch.setenv(audit.MAX_TOTAL_MB_ENV, value)
    assert audit.retention_settings() == (180 * 86400, 500 * 1024 * 1024)


def test_settings_constants_are_the_documented_ones():
    assert (audit.DEFAULT_MAX_AGE_DAYS, audit.DEFAULT_MAX_TOTAL_MB) == (180, 500)
    assert audit.MAX_AGE_DAYS_ENV == "REVIT_MCP_AUDIT_MAX_AGE_DAYS"
    assert audit.MAX_TOTAL_MB_ENV == "REVIT_MCP_AUDIT_MAX_TOTAL_MB"
    assert audit.AUDIT_FILE_GLOB == "audit-*.jsonl"


# --------------------------------------------------------------- startup row

def test_startup_prunes_old_files_before_its_own_segment_exists(monkeypatch):
    import time

    directory = os.environ[audit.AUDIT_DIR_ENV]
    os.makedirs(directory)
    old = make_file(directory, "audit-20200101-000000-1.jsonl", 50,
                    mtime=time.time() - 200 * DAY)
    foreign = make_file(directory, "readme.txt", 50, mtime=time.time() - 900 * DAY)
    calls = []
    real_prune = audit.prune

    def spy(directory_, now, max_age, max_total):
        before = os.listdir(directory_)
        deleted = real_prune(directory_, now, max_age, max_total)
        calls.append((before, deleted))
        return deleted

    monkeypatch.setattr(audit, "prune", spy)
    record(1)
    record(2)
    assert audit.flush()
    assert len(calls) == 1
    before, deleted = calls[0]
    assert sorted(before) == ["audit-20200101-000000-1.jsonl", "readme.txt"]
    assert deleted == ["audit-20200101-000000-1.jsonl"]
    assert not os.path.exists(old) and os.path.exists(foreign)
    assert len(glob.glob(os.path.join(directory, "audit-*.jsonl"))) == 1
    assert len(read_entries()) == 2


def test_startup_a_failing_prune_never_stops_the_writer(monkeypatch, capsys):
    def boom(*_args, **_kwargs):
        raise RuntimeError("prune broke")

    monkeypatch.setattr(audit, "prune", boom)
    assert record(1) is not None
    assert len(read_entries()) == 1
    assert stderr_lines(capsys) == []


# ------------------------------------------------------- default directory rows

def test_default_directory_on_windows_is_under_localappdata(monkeypatch):
    monkeypatch.delenv(audit.AUDIT_DIR_ENV, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", os.path.join(os.sep, "somewhere", "Local"))
    monkeypatch.setattr(sys, "platform", "win32")
    assert audit.audit_dir() == os.path.join(os.sep, "somewhere", "Local", "RevitMCP", "audit")


def test_default_directory_without_localappdata_falls_back_to_the_profile(monkeypatch):
    monkeypatch.delenv(audit.AUDIT_DIR_ENV, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    assert audit.audit_dir() == os.path.join(
        os.path.expanduser("~"), "AppData", "Local", "RevitMCP", "audit")


def test_default_directory_elsewhere_is_under_the_home_directory(monkeypatch):
    monkeypatch.delenv(audit.AUDIT_DIR_ENV, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert audit.audit_dir() == os.path.join(os.path.expanduser("~"), ".revit-mcp", "audit")


def test_default_directory_can_be_overridden(monkeypatch):
    monkeypatch.setenv(audit.AUDIT_DIR_ENV, os.path.join(os.sep, "elsewhere", "audit"))
    assert audit.audit_dir() == os.path.join(os.sep, "elsewhere", "audit")


# --------------------------------------------------------- never_breaks rows

async def _plain_result():
    """What a call returns with a working audit, as the baseline for the failure rows."""
    result = await bridge.revit_post("/set_parameter/", {}, target=SEL_A)
    return result


@pytest.mark.anyio
async def test_never_breaks_an_unwritable_directory_costs_only_the_entry(
        machine, monkeypatch, tmp_path, capsys):
    baseline = await _plain_result()
    capsys.readouterr()
    audit._reset()
    blocker = tmp_path / "not-a-directory"
    blocker.write_bytes(b"i am a regular file")
    monkeypatch.setenv(audit.AUDIT_DIR_ENV, str(blocker))

    first = await bridge.revit_post("/set_parameter/", {}, target=SEL_A)
    second = await bridge.revit_post("/set_parameter/", {}, target=SEL_A)

    assert first == baseline and second == baseline
    lines = stderr_lines(capsys)
    assert len(lines) == 1
    assert lines[0].startswith("revit-mcp: audit log entry dropped (")
    assert lines[0].endswith(")") and "\\" not in lines[0] and str(blocker) not in lines[0]


@pytest.mark.anyio
async def test_never_breaks_a_full_queue_drops_entries_not_calls(machine, monkeypatch, capsys):
    monkeypatch.setattr(audit, "QUEUE_MAX", 1)
    release = threading.Event()
    started = threading.Event()
    try:
        assert record(0) is not None
        assert audit.flush()
        handler = audit._WRITER.handler
        real_emit = handler.emit

        def blocked(record_):
            started.set()
            release.wait(10)
            real_emit(record_)

        monkeypatch.setattr(handler, "emit", blocked)
        baseline = await bridge.revit_post("/set_parameter/", {}, target=SEL_A)
        assert started.wait(5)           # the listener now holds one record and is stuck
        results = [await bridge.revit_post("/set_parameter/", {}, target=SEL_A) for _ in range(4)]
        assert all(r == baseline for r in results)
        lines = stderr_lines(capsys)
        assert len(lines) == 1 and lines[0].startswith("revit-mcp: audit log entry dropped (")
    finally:
        release.set()
        audit.flush(10.0)


@pytest.mark.anyio
async def test_never_breaks_a_failing_serialization_returns_none(machine, monkeypatch, capsys):
    def boom(entry, secret):
        raise ValueError("cannot serialize")

    monkeypatch.setattr(audit, "serialize_entry", boom)
    assert record(1) is None
    result = await bridge.revit_post("/set_parameter/", {}, target=SEL_A)
    assert result["path"].endswith("/set_parameter/")
    lines = stderr_lines(capsys)
    assert len(lines) == 1 and lines[0] == "revit-mcp: audit log entry dropped (ValueError)"


@pytest.mark.anyio
async def test_never_breaks_a_raising_record_call_leaves_the_result_untouched(machine, monkeypatch):
    baseline = await _plain_result()

    def boom(*_args, **_kwargs):
        raise RuntimeError("the hook itself failed")

    monkeypatch.setattr(audit, "record_call", boom)
    result = await bridge.revit_post("/set_parameter/", {}, target=SEL_A)

    assert result == baseline
    assert type(result) is type(baseline)
    meta, base_meta = (getattr(r, bridge.PROVENANCE_ATTR) for r in (result, baseline))
    assert meta["kind"] == base_meta["kind"] == "received"
    assert meta["process"] == base_meta["process"]
    assert "audit_call_id" not in meta
