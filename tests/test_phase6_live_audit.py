# -*- coding: utf-8 -*-
"""Phase 6 live audit gate (plan 06-06 writes it, plan 06-07 runs it): one-shot runner and classifiers.

Older tier: a standalone script, run by hand by an engineer on a bench machine, excluded
from pytest (``testpaths = ["tests/unit"]``). It defines no ``test_*`` function and does
nothing at import (no bridge import, no environment change, no I/O), so the unit suite can
import its pure functions (tests/unit/test_phase6_live_audit.py). It never runs in Revit,
so it is ordinary CPython; the IronPython rules of the Revit half do not apply here.

What this is
------------
Phase 6 writes one audit entry for every call the bridge makes. Everything about those
entries is proven offline against a fake Revit except two things that need real Revit
processes: a real rollback and a real partial batch recorded truthfully (ROADMAP criterion
2), and two Revit instances mutated at the same time through one server process plus a
second server process without corrupting or mixing entries (criterion 5). The same record
also gives a live look at criteria 1 and 7. This script is that look.

Every write goes through the path an engineer's assistant uses: the audited wrapper FastMCP
registered for the tool in ``main.mcp`` (the call state, the real tool function, the production
bridge and the audit writer all run), with REVIT_MCP_AUDIT_DIR pointing at an operator-chosen
scratch directory before the first write. The wrapper is called with ctx=None:
``main.mcp.call_tool(...)`` outside a real MCP request hands the tool a Context that refuses
use, and execute_revit_code reports progress through it, so that call would raise before
anything was sent. The reads of the preflight go through ``bridge.revit_get``. Nothing is
judged by eye: ``classify_single`` and ``classify_dual`` turn the record and the audit files
into PHASE6_AUDIT_OK or PHASE6_AUDIT_STOP with named reasons.

The steps, each sent exactly once
---------------------------------
run-single (one Revit instance, one open scratch document):

  w1  execute_revit_code   the operator's rehearsed rollback code        (criterion 2: rolled_back, HTTP 409)
  w2  tag_elements         [TAG_ID, 999999999] in the named view         (criterion 2: partial)
  w3  set_parameter        one text parameter on the wall                (criteria 1 and 7: a successful entry)

run-dual (two Revit instances on two ports, one open scratch document each):

  K set_parameter calls per instance from the runner process, and K per instance from a child
  server process the runner starts and does not wait for, so the two processes write
  concurrently (criterion 5). K is --count (default 5, at most 20); the values are
  phase6-dual-<server pid>-<i>.

Commands
--------
    uv run python tests/test_phase6_live_audit.py template
    uv run python tests/test_phase6_live_audit.py rehearse --rollback-code FILE --audit-dir DIR [--port 48884]
    uv run python tests/test_phase6_live_audit.py run-single --wall-id N --parameter NAME --view-name VIEW
        --tag-id N --rollback-code FILE --audit-dir DIR --out RECORD.json [--port 48884]
    uv run python tests/test_phase6_live_audit.py run-dual --wall-a N --wall-b N --parameter NAME
        --audit-dir DIR --out RECORD.json [--count 5] [--port 48884]
    uv run python tests/test_phase6_live_audit.py classify RECORD.json
    uv run python tests/test_phase6_live_audit.py child ...      (internal: started by run-dual only)

``template`` prints the empty record. ``classify`` re-judges a saved record and sends nothing;
it reads the configured shared secret through the bridge only to count its occurrences. In
run-dual the first Revit (lowest port) gets --wall-a and the second --wall-b; the child
server process leaves its own record beside --out as <out stem>-child.json, and the runner
merges it into the main record (which names the child's file by PID in audit_files).

``rehearse`` sends exactly one execute_revit_code call with the operator's code and the
user_request "phase6 rehearsal", then reads the audit entry of that call and prints
REHEARSAL_ROLLED_BACK (HTTP 409, rolled_back), REHEARSAL_COMMITTED (the code committed) or
REHEARSAL_OTHER, plus POSTS_SENT=1 and the entry's outcome, HTTP status and transaction
status. It exits 0 only for REHEARSAL_ROLLED_BACK and does not judge the rest of the audit.
It is the repeatable rehearsal that research assumption A3 requires before the one-shot run:
use a fresh --audit-dir each time.

Output tokens and exit codes
----------------------------
Every run and classify prints PHASE6_AUDIT_OK or PHASE6_AUDIT_STOP, then a line
POSTS_SENT=<n> (POSTS_SENT=unknown for a record that carries no count), then
SECRET_OCCURRENCES=<n> and the reasons of a stop. Exit codes: 0 ok, 1 stop, 2 usage error or
refusal. The shared secret is never printed, recorded or logged: only its occurrence count
in the audit files, the replies and the record is printed, and a non-zero count is a stop.

POSTS_SENT and the one-shot rule
--------------------------------
``posts_sent`` is the number of write calls handed to the tool, counted immediately before
each call, so a call that raised or timed out still counts: its outcome in the model is
unknown. A write step is never repeated and a record is never overwritten.

  POSTS_SENT=0   the read-only preflight stopped the run before any write. Nothing was
                 written to any model. Fix the condition the output names and run again
                 with a fresh --out and a fresh (or empty) --audit-dir.
  POSTS_SENT>=1  a write was sent. The one-shot gate for that stage is consumed: never run
                 it again, whatever the verdict. A stop after that point is a finding about
                 the audit, to be read from the record, not a reason to retry.

Safety (what is refused before any request is sent)
---------------------------------------------------
* an --out record that already exists (a record is never overwritten);
* an --out record or an --audit-dir inside the repository (a raw record and the audit files
  name the ports, ids, paths and user names of a workstation);
* an --audit-dir that exists and is not empty (the classifiers read every file in it);
* a missing directory for --out, or a missing parent directory for --audit-dir;
* an element id that is not a positive whole number, or 999999999 (the id reserved for the
  deliberate failure); a blank parameter or view name; a --count outside 1..20;
* a --rollback-code file that is missing or empty.

Then a read-only preflight, still before any write. run-single: exactly one usable Revit
target and no port collision; GET /status/ answers with that process identity; the OS
listener inventory shows exactly one owner of the port; GET /documents/ lists exactly one
open document; GET /element_properties/ of the wall shows the parameter present, a text
parameter and not read-only; GET /element_properties/ of the tag element answers. run-dual:
exactly two usable targets on two different ports, one open document each, and the
parameter present and writable on each wall. Any failure is recorded with posts_sent 0.

The script names only these routes for reads: /status/, /documents/ and
/element_properties/; and only these tools for writes: execute_revit_code, tag_elements and
set_parameter. A call outside the lists is refused before anything is sent. It never saves a
document, never opens a model, and never reads, prints or records the shared secret.

Operator procedure (plan 06-07 follows this; the engineer controls the bench)
-----------------------------------------------------------------------------
1. Fully close Revit and reopen it with NO model (never pyRevit Reload after an edit under
   ``revit_mcp/``: it can crash Revit). Poll GET /status/ until it answers. Run
   ``Get-NetTCPConnection -LocalPort <port> -State Listen`` and check exactly one row (Revit
   Accelerator can start a second Revit by itself; with two rows stop).
2. Open ONE scratch, non-workshared model through open_model (never from the command line: a
   workshared model raises the workset dialog and blocks the routes forever). No other
   document may be open. Never save it; close it without saving at the end.
3. Read what the run needs: a wall id with a writable text parameter (for example Comments),
   a plan view name of the model, and one taggable element visible in that view.
4. Choose a scratch folder outside the repository. --audit-dir must not exist or must be
   empty; --out must not exist.
5. Write the rollback code (IronPython 3, no f-strings): code that makes no model change of
   its own and posts one error-severity failure so that Revit rolls the transaction back at
   Commit. Run ``rehearse`` (a fresh --audit-dir each time) until it prints
   REHEARSAL_ROLLED_BACK. REHEARSAL_COMMITTED means the code changed nothing by construction
   but is not the trigger: rework it.
6. Run ``run-single`` once. Read the token, POSTS_SENT and the reasons. With POSTS_SENT=0 fix
   the named condition and run again with a fresh --out and --audit-dir; with POSTS_SENT of 1
   or more never run it again.
7. For run-dual: close the model, start a second Revit with no model, wait for both /status/
   endpoints and check one listener row per port with two different PIDs. Open one scratch
   copy in each instance through open_model (one document per instance), then run
   ``run-dual`` once under the same POSTS_SENT rule.
8. Attach the --out records and the printed output to the 06-07 verification.

Records and audit directories are machine local: keep them outside the repository.
"""
import argparse
import asyncio
import datetime
import fnmatch
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import uuid
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BAD_ID = 999999999
DEFAULT_PORT = 48884
DEFAULT_COUNT = 5
MAX_COUNT = 20

SENTINEL_OK = "PHASE6_AUDIT_OK"
SENTINEL_STOP = "PHASE6_AUDIT_STOP"

VERDICT_OK = "ok"
VERDICT_STOP = "stop"

STAGE_SINGLE = "single"
STAGE_DUAL = "dual"

STEP_KEYS = ("w1", "w2", "w3")

# The only routes the preflight may read and the only tools a write may name. A call outside
# the lists is refused before the bridge or the server is touched.
ALLOWED_READS = frozenset((
    "/status/",
    "/documents/",
    "/element_properties/",
))
ALLOWED_TOOLS = frozenset((
    "execute_revit_code",
    "tag_elements",
    "set_parameter",
))

AUDIT_LINE = re.compile(r"^Audit: call_id ([0-9a-f-]{36})$", re.MULTILINE)

# audit-<UTC date>-<UTC time>-<server pid>[.<segment>].jsonl, as audit.SegmentHandler names it.
FILE_NAME = re.compile(r"^audit-\d{8}-\d{6}-(\d+)(?:\.(\d{4}))?\.jsonl$")

# What each single-Revit step must have written: (tool, route).
STEP_ENTRY = {
    "w1": ("execute_revit_code", "/execute_code/"),
    "w2": ("tag_elements", "/tag_elements/"),
    "w3": ("set_parameter", "/set_parameter/"),
}
DUAL_ENTRY = ("set_parameter", "/set_parameter/")

REASON_NO_SECRET = "secret: no secret configured; the gate needs the Phase 5 live secret"

MSG_NO_WRITE = ("No write step was sent: nothing was written to any model. Fix the condition "
                "named above and run again with a fresh --out and a fresh --audit-dir.")
MSG_CONSUMED = "The one-shot gate is consumed: do not run this stage again."


# ------------------------------------------------------------- primitives


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _describe(value):
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _outside_repo(path):
    real = os.path.normcase(os.path.realpath(path))
    root = os.path.normcase(os.path.realpath(REPO_ROOT))
    try:
        return os.path.commonpath([real, root]) != root
    except ValueError:  # different drives
        return True


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


# --------------------------------------------------------------- template


def evidence_template():
    """The record skeleton; a fresh object each call. Every value starts empty, which classifies as stop."""
    return {
        "stage": None,
        "inputs": {
            "wall_id": None, "parameter": None, "view_name": None, "tag_id": None,
            "rollback_code": None, "port": None, "wall_a": None, "wall_b": None,
            "count": None, "audit_dir": None,
        },
        "preflight": {
            "status_ok": None, "listeners": None, "documents": None,
            "parameter_writable": None, "tag_element_found": None,
            "selector": None, "targets": None,
        },
        "steps": {"w1": None, "w2": None, "w3": None, "parent": [], "child": []},
        "replies": {},
        "audit_files": {},
        "revit_pids": [],
        "server_pids": {"parent": None, "child": None},
        "posts_sent": 0,
    }


# ------------------------------------------------------- secret and audit files


def secret_occurrences(data, secret):
    """How often the secret shows in ``data`` (bytes): whole, JSON-escaped, or as a 16-character run.

    A whole or escaped occurrence counts once; the runs are then counted in what is left, so
    a partial leak (a 16-character piece) is found too. No secret counts as 0. Pure.
    """
    if not (isinstance(secret, str) and secret):
        return 0
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    if not isinstance(data, (bytes, bytearray)):
        return 0
    masked = bytes(data)
    total = 0
    forms = [secret]
    escaped = json.dumps(secret)[1:-1]
    if escaped != secret:
        forms.append(escaped)
    for form in forms:
        pattern = form.encode("utf-8", "replace")
        total += masked.count(pattern)
        masked = masked.replace(pattern, b"\x00")
    if len(secret) >= 16:
        runs = set(secret[i:i + 16] for i in range(len(secret) - 15))
        for run in runs:
            total += masked.count(run.encode("utf-8", "replace"))
    return total


def _record_bytes(record):
    """Everything the gate keeps or prints for a record: audit lines, replies and the saved JSON."""
    parts = []
    files = record.get("audit_files") if isinstance(record, dict) else None
    for lines in (files.values() if isinstance(files, dict) else ()):
        parts.extend(str(line) for line in (lines if isinstance(lines, list) else [lines]))
    replies = record.get("replies") if isinstance(record, dict) else None
    for text in (replies.values() if isinstance(replies, dict) else ()):
        parts.append(str(text))
    parts.append(json.dumps(record, ensure_ascii=False, default=str))
    return "\n".join(parts).encode("utf-8", "replace")


def record_secret_occurrences(record, secret):
    """The occurrence count the classifiers and the report use; 0 when it cannot be computed."""
    try:
        return secret_occurrences(_record_bytes(record), secret)
    except Exception:
        return 0


def parse_audit_files(mapping):
    """(entries, bad_lines, crlf_files) of {file name: [raw lines]}.

    entries are (file name, entry dict) in file-name then line order; a bad line is a
    (file name, 1-based line number) that is not one JSON object (a blank line, a torn
    line, a JSON value that is not an object); a file holding a CR is listed once in
    crlf_files. Pure; never raises.
    """
    entries, bad, crlf = [], [], []
    if not isinstance(mapping, dict):
        return entries, bad, crlf
    for name in sorted(mapping, key=str):
        lines = mapping[name]
        if not isinstance(lines, list):
            bad.append((name, 0))
            continue
        for number, line in enumerate(lines, 1):
            if not isinstance(line, str):
                bad.append((name, number))
                continue
            if "\r" in line and name not in crlf:
                crlf.append(name)
            try:
                value = json.loads(line)
            except (ValueError, RecursionError):
                bad.append((name, number))
                continue
            if not isinstance(value, dict):
                bad.append((name, number))
                continue
            entries.append((name, value))
    return entries, bad, crlf


def audit_id_of(reply_text):
    """The call_id of the last ``Audit: call_id <id>`` line of a tool reply, or None."""
    if not isinstance(reply_text, str):
        return None
    found = AUDIT_LINE.findall(reply_text)
    return found[-1] if found else None


def _file_pid(name):
    match = FILE_NAME.match(name) if isinstance(name, str) else None
    return int(match.group(1)) if match else None


def _file_label(name, server_pids):
    """A PID-free label for an audit file, so a reason never prints a process id."""
    match = FILE_NAME.match(name) if isinstance(name, str) else None
    if not match:
        return "an audit file with an unrecognised name"
    pid = int(match.group(1))
    role = "unknown-process"
    for who, value in _dict(server_pids).items():
        if _is_int(value) and value == pid:
            role = who
    label = "{} audit file".format(role)
    if match.group(2):
        label += " (segment {})".format(int(match.group(2)))
    return label


def _audit_entries(record, secret, reasons):
    """The parsed entries, with the file-level and secret reasons added to ``reasons``."""
    server_pids = record.get("server_pids")
    if not (isinstance(secret, str) and secret.strip()):
        reasons.append(REASON_NO_SECRET)
    else:
        found = record_secret_occurrences(record, secret)
        if found:
            reasons.append("secret: SECRET_OCCURRENCES={} in the audit files, replies or record".format(found))
    files = record.get("audit_files")
    if not (isinstance(files, dict) and files):
        reasons.append("audit_files: no audit file was recorded")
    entries, bad, crlf = parse_audit_files(files)
    for name, number in bad:
        reasons.append("{}: line {} is not a JSON object".format(_file_label(name, server_pids), number))
    for name in crlf:
        reasons.append("{}: CRLF line ending found".format(_file_label(name, server_pids)))
    return entries


def _by_call_id(entries):
    found = {}
    for name, entry in entries:
        call_id = entry.get("call_id")
        if isinstance(call_id, str):
            found.setdefault(call_id, []).append((name, entry))
    return found


def _verified_pids(record, reasons, expected=None):
    pids = [p for p in _list(record.get("revit_pids")) if _is_int(p) and p > 0]
    if not pids or len(pids) != len(_list(record.get("revit_pids"))):
        reasons.append("revit_pids: no verified Revit PID was recorded")
        return []
    if expected is not None and len(set(pids)) != expected:
        reasons.append("revit_pids: expected {} distinct verified Revit PIDs".format(expected))
    return pids


def _expect(reasons, label, entry, field, expected):
    value = entry.get(field)
    if value != expected:
        reasons.append("{}.{}: expected {}, got {}".format(label, field, _describe(expected), _describe(value)))


def _judge_common(label, entry, step, pids, server_pid, tool, route, reasons):
    """Checks every step's entry shares: what it names, who wrote it and which Revit answered."""
    _expect(reasons, label, entry, "tool", tool)
    _expect(reasons, label, entry, "route", route)
    if entry.get("mutation") is not True:
        reasons.append("{}.mutation: expected true, got {}".format(label, _describe(entry.get("mutation"))))
    _expect(reasons, label, entry, "kind", "received")
    process = entry.get("process")
    if not isinstance(process, dict):
        reasons.append("{}.process: missing".format(label))
    elif process.get("pid") not in pids or not _is_int(process.get("pid")):
        reasons.append("{}.process.pid: not one of the verified Revit PIDs".format(label))
    sent = step.get("user_request")
    if entry.get("user_request") != sent or entry.get("user_request_missing") is True:
        reasons.append("{}.user_request: differs from the text sent".format(label))
    if _is_int(server_pid) and entry.get("server_pid") != server_pid:
        reasons.append("{}.server_pid: not the PID of the runner process".format(label))
    if not _nonblank(entry.get("ts")):
        reasons.append("{}.ts: missing".format(label))
    if not _nonblank(entry.get("windows_user")):
        reasons.append("{}.windows_user: missing".format(label))


def _judge_w1(entry, inputs, reasons):
    _expect(reasons, "w1", entry, "outcome", "rolled_back")
    _expect(reasons, "w1", entry, "http_status", 409)
    status = entry.get("transaction_status")
    if not (_nonblank(status) and status != "Committed"):
        reasons.append("w1.transaction_status: expected a status other than Committed, got {}".format(
            _describe(status)))
    code = inputs.get("rollback_code")
    if not _nonblank(code):
        reasons.append("inputs.rollback_code: missing, so the code hash cannot be checked")
    elif entry.get("code_sha256") != _sha256(code):
        reasons.append("w1.code_sha256: does not match the SHA-256 of inputs.rollback_code")


def _judge_w2(entry, inputs, reasons):
    _expect(reasons, "w2", entry, "outcome", "partial")
    _expect(reasons, "w2", entry, "http_status", 200)
    failed = _list(entry.get("failed"))
    hit = [f for f in failed if isinstance(f, dict) and f.get("item") == BAD_ID]
    if not (len(hit) == 1 and _nonblank(hit[0].get("reason"))):
        reasons.append("w2.failed: expected one entry for item {} with a reason, got {}".format(
            BAD_ID, _describe(entry.get("failed"))))
    _expect(reasons, "w2", entry, "succeeded", [inputs.get("tag_id")])


def _judge_w3(entry, inputs, reasons):
    _expect(reasons, "w3", entry, "outcome", "success")
    _expect(reasons, "w3", entry, "http_status", 200)
    _expect(reasons, "w3", entry, "transaction_status", "Committed")
    # set_parameter reports the parameter name in outcome.succeeded; the wall is in the arguments.
    _expect(reasons, "w3", entry, "succeeded", [inputs.get("parameter")])
    args = _dict(entry.get("args"))
    if args.get("element_id") != inputs.get("wall_id"):
        reasons.append("w3.args.element_id: expected the wall id {}, got {}".format(
            _describe(inputs.get("wall_id")), _describe(args.get("element_id"))))
    document = entry.get("document")
    if not isinstance(document, dict):
        reasons.append("w3.document: missing")
    else:
        for field in ("token", "title", "path"):
            if not _nonblank(document.get(field)):
                reasons.append("w3.document.{}: empty".format(field))


def _find_step_entry(key, step, replies, entries, by_id, reasons):
    """The one entry whose call_id is the Audit line id of the step's reply, or None (reasons added)."""
    reply = replies.get(key)
    if not _nonblank(reply):
        reasons.append("{}.reply: no reply text was recorded".format(key))
        return None
    audit_id = audit_id_of(reply)
    if audit_id is None:
        reasons.append("{}.reply: no 'Audit: call_id' line".format(key))
        return None
    found = by_id.get(audit_id, [])
    if len(found) == 1:
        return found[0][1]
    reasons.append("{}: expected exactly one audit entry for the call_id of its reply, found {}".format(
        key, len(found)))
    if not found:
        near = [e for _n, e in entries
                if e.get("tool") == step.get("tool") and e.get("user_request") == step.get("user_request")]
        if len(near) == 1:
            reasons.append("{}.call_id: the entry's call_id differs from the Audit line id in its reply".format(key))
    return None


def _judge_single(record, secret, reasons):
    if not isinstance(record, dict):
        reasons.append("record: not an object ({})".format(type(record).__name__))
        return
    if record.get("stage") != STAGE_SINGLE:
        reasons.append("record.stage: expected 'single', got {}".format(_describe(record.get("stage"))))
        return
    entries = _audit_entries(record, secret, reasons)
    by_id = _by_call_id(entries)
    inputs = _dict(record.get("inputs"))
    steps = _dict(record.get("steps"))
    replies = _dict(record.get("replies"))
    pids = _verified_pids(record, reasons)
    server_pid = _dict(record.get("server_pids")).get("parent")
    judges = {"w1": _judge_w1, "w2": _judge_w2, "w3": _judge_w3}
    for key in STEP_KEYS:
        step = steps.get(key)
        if not isinstance(step, dict):
            reasons.append("{}: step was not recorded".format(key))
            continue
        entry = _find_step_entry(key, step, replies, entries, by_id, reasons)
        if entry is None:
            continue
        tool, route = STEP_ENTRY[key]
        _judge_common(key, entry, step, pids, server_pid, tool, route, reasons)
        judges[key](entry, inputs, reasons)


def _judge_dual_call(who, pid, call, inputs, replies, by_id, pids, reasons):
    key = call.get("key") if _nonblank(call.get("key")) else "{}-?".format(who)
    audit_id = audit_id_of(replies.get(key))
    if audit_id is None:
        reasons.append("{}.reply: no 'Audit: call_id' line".format(key))
        return
    found = by_id.get(audit_id, [])
    if len(found) != 1:
        reasons.append("{}: expected exactly one audit entry for the call_id of its reply, found {}".format(
            key, len(found)))
        return
    name, entry = found[0]
    if _is_int(pid) and _file_pid(name) != pid:
        reasons.append("{}: the entry sits in the file of another server process".format(key))
    tool, route = DUAL_ENTRY
    _expect(reasons, key, entry, "tool", tool)
    _expect(reasons, key, entry, "route", route)
    if entry.get("mutation") is not True:
        reasons.append("{}.mutation: expected true, got {}".format(key, _describe(entry.get("mutation"))))
    process = _dict(entry.get("process"))
    if not _is_int(process.get("pid")) or process.get("pid") != call.get("pid"):
        reasons.append("{}.process.pid: the entry names a different Revit than the call addressed".format(key))
    if call.get("pid") not in pids:
        reasons.append("{}.pid: the call addressed a Revit instance that was not verified".format(key))
    args = _dict(entry.get("args"))
    if (args.get("element_id") != call.get("element_id") or args.get("value") != call.get("value")
            or args.get("parameter_name") != inputs.get("parameter")):
        reasons.append("{}.args: element, parameter or value differ from the call".format(key))
    if entry.get("user_request") != call.get("user_request"):
        reasons.append("{}.user_request: differs from the text sent".format(key))


def _judge_dual(record, secret, reasons):
    if not isinstance(record, dict):
        reasons.append("record: not an object ({})".format(type(record).__name__))
        return
    if record.get("stage") != STAGE_DUAL:
        reasons.append("record.stage: expected 'dual', got {}".format(_describe(record.get("stage"))))
        return
    entries = _audit_entries(record, secret, reasons)
    by_id = _by_call_id(entries)
    server_pids = _dict(record.get("server_pids"))
    pids_of = {"parent": server_pids.get("parent"), "child": server_pids.get("child")}
    valid_pids = (_is_int(pids_of["parent"]) and _is_int(pids_of["child"])
                  and pids_of["parent"] != pids_of["child"])
    if not valid_pids:
        reasons.append("server_pids: the parent and child PIDs must be two different whole numbers")
    files = _dict(record.get("audit_files"))
    file_pids = set()
    for name in files:
        pid = _file_pid(name)
        if pid is None:
            reasons.append("{}: the name carries no server PID".format(_file_label(name, server_pids)))
        else:
            file_pids.add(pid)
    if len(file_pids) < 2:
        reasons.append("audit files: only one server-process PID among the file names (two are expected)")
    elif valid_pids and file_pids != {pids_of["parent"], pids_of["child"]}:
        reasons.append("audit files: the server-process PIDs in the file names differ from the two processes")
    for name, entry in entries:
        if _file_pid(name) is not None and entry.get("server_pid") != _file_pid(name):
            reasons.append("{}: an entry names a server_pid that is not the PID in the file name".format(
                _file_label(name, server_pids)))
    pids = _verified_pids(record, reasons, expected=2)
    inputs = _dict(record.get("inputs"))
    count = inputs.get("count")
    expected_calls = None
    if _is_int(count) and 1 <= count <= MAX_COUNT:
        expected_calls = 2 * count
    else:
        reasons.append("inputs.count: expected a whole number from 1 to {}, got {}".format(
            MAX_COUNT, _describe(count)))
    steps = _dict(record.get("steps"))
    replies = _dict(record.get("replies"))
    for who in ("parent", "child"):
        calls = steps.get(who)
        if not isinstance(calls, list):
            reasons.append("{}: the calls were not recorded".format(who))
            continue
        issued = [c for c in calls if isinstance(c, dict)]
        if len(issued) != len(calls):
            reasons.append("{}: a recorded call is not an object".format(who))
        if expected_calls is not None and len(issued) != expected_calls:
            reasons.append("{}: issued {} calls, expected {}".format(who, len(issued), expected_calls))
        if expected_calls is not None:
            addressed = Counter(c.get("pid") for c in issued)
            for revit_pid in pids:
                if addressed.get(revit_pid, 0) != count:
                    reasons.append("{}: {} calls addressed one Revit instance, expected {}".format(
                        who, addressed.get(revit_pid, 0), count))
        wrote = [e for _n, e in entries
                 if e.get("tool") == DUAL_ENTRY[0] and e.get("server_pid") == pids_of[who]]
        if len(wrote) != len(issued):
            reasons.append("{}: wrote {} entries for {} calls issued".format(who, len(wrote), len(issued)))
        for call in issued:
            _judge_dual_call(who, pids_of[who], call, inputs, replies, by_id, pids, reasons)


def _classify(judge, record, secret):
    reasons = []
    try:
        judge(record, secret, reasons)
    except Exception as ex:  # a classifier bug must read as stop, never as a pass
        text = "classifier-error: {}: {}".format(type(ex).__name__, ex)
        if isinstance(secret, str) and secret:
            text = text.replace(secret, "[REDACTED]")
        reasons.append(text)
    return {"verdict": VERDICT_STOP if reasons else VERDICT_OK, "reasons": list(reasons)}


def classify_single(record, secret):
    """Judge a run-single record (ROADMAP criteria 1, 2 and 7): {"verdict": "ok"|"stop", "reasons": [...]}.

    Pure and never raises. ``secret`` is the loaded shared secret (None makes it a stop). The
    reasons name the field and carry its value, never the secret and never a process id.
    """
    return _classify(_judge_single, record, secret)


def classify_dual(record, secret):
    """Judge a run-dual record (ROADMAP criterion 5): {"verdict": "ok"|"stop", "reasons": [...]}.

    Pure and never raises; same contract as classify_single.
    """
    return _classify(_judge_dual, record, secret)


# --------------------------------------------------------------- refusals


def _child_record_path(out):
    return os.path.splitext(out)[0] + "-child.json"


def refusal(args):
    """Why the command may not start, or None. Decided before the bridge or the server is touched.

    ``args`` is an argparse namespace; only the attributes it has are judged, so one function
    serves rehearse, run-single and run-dual.
    """
    def has(name):
        return hasattr(args, name)

    for name in ("wall_id", "tag_id", "wall_a", "wall_b"):
        if has(name):
            value = getattr(args, name)
            if not (_is_int(value) and value > 0 and value != BAD_ID):
                return "--{} must be a positive element id other than {}".format(name.replace("_", "-"), BAD_ID)
    for name in ("parameter", "view_name"):
        if has(name) and not _nonblank(getattr(args, name)):
            return "--{} must not be blank".format(name.replace("_", "-"))
    if has("count"):
        value = args.count
        if not (_is_int(value) and 1 <= value <= MAX_COUNT):
            return "--count must be a whole number from 1 to {}".format(MAX_COUNT)
    if has("port"):
        value = args.port
        if not (_is_int(value) and 1 <= value <= 65535):
            return "--port must be between 1 and 65535"
    if has("rollback_code"):
        path = args.rollback_code
        try:
            with open(path, "rb") as handle:
                empty = not handle.read().strip()
        except (OSError, TypeError, ValueError):
            return "--rollback-code {} is missing or unreadable".format(path)
        if empty:
            return "--rollback-code {} is empty".format(path)
    out = getattr(args, "out", None) if has("out") else None
    if has("out"):
        if not _nonblank(out):
            return "--out must not be blank"
        if os.path.exists(out):
            return "{} already exists; a record is never overwritten (use a fresh --out)".format(out)
        if os.path.exists(_child_record_path(out)):
            return "{} already exists; a record is never overwritten".format(_child_record_path(out))
        if not _outside_repo(out):
            return "--out {} is inside the repository; a raw record stays outside it".format(out)
        if not os.path.isdir(os.path.dirname(os.path.abspath(out))):
            return "the directory of --out does not exist ({}); the record would be lost".format(out)
    if has("audit_dir"):
        audit_dir = args.audit_dir
        if not _nonblank(audit_dir):
            return "--audit-dir must not be blank"
        if not _outside_repo(audit_dir):
            return "--audit-dir {} is inside the repository; audit files stay outside it".format(audit_dir)
        if os.path.exists(audit_dir):
            if not os.path.isdir(audit_dir):
                return "--audit-dir {} exists and is not a directory".format(audit_dir)
            try:
                left = os.listdir(audit_dir)
            except OSError as ex:
                return "--audit-dir {} cannot be listed ({})".format(audit_dir, type(ex).__name__)
            if left:
                return "--audit-dir {} exists and is not empty; use a fresh directory".format(audit_dir)
        elif not os.path.isdir(os.path.dirname(os.path.abspath(audit_dir))):
            return "the parent directory of --audit-dir does not exist ({})".format(audit_dir)
        if out is not None:
            real_out = os.path.normcase(os.path.realpath(out))
            real_dir = os.path.normcase(os.path.realpath(audit_dir))
            try:
                if os.path.commonpath([real_out, real_dir]) == real_dir:
                    return "--out must not be inside --audit-dir"
            except ValueError:
                pass
    return None


# ----------------------------------------------------------------- report


def report(verdict, reasons, posts_sent, secret_occurrences=None):
    """The lines to print: the token, POSTS_SENT, the secret count when known, guidance and reasons."""
    posts = posts_sent if _is_int(posts_sent) and posts_sent >= 0 else None
    lines = [SENTINEL_OK if verdict == VERDICT_OK else SENTINEL_STOP,
             "POSTS_SENT={}".format(posts if posts is not None else "unknown")]
    if _is_int(secret_occurrences):
        lines.append("SECRET_OCCURRENCES={}".format(secret_occurrences))
    if posts == 0:
        lines.append(MSG_NO_WRITE)
    elif posts is not None:
        lines.append(MSG_CONSUMED)
    for reason in reasons:
        lines.append("  - " + reason)
    return lines


# --------------------------------------------------------------- operator

USAGE = (
    "usage: test_phase6_live_audit.py template | classify RECORD.json | "
    "rehearse --rollback-code FILE --audit-dir DIR [--port N] | "
    "run-single --wall-id N --parameter NAME --view-name VIEW --tag-id N --rollback-code FILE "
    "--audit-dir DIR --out RECORD.json [--port N] | "
    "run-dual --wall-a N --wall-b N --parameter NAME --audit-dir DIR --out RECORD.json "
    "[--count K] [--port N]"
)

CHILD_TOKEN_ENV = "PHASE6_AUDIT_CHILD_TOKEN"
CHILD_TIMEOUT = 900.0  # seconds the runner waits for its child server process

REHEARSAL_REQUEST = "phase6 rehearsal"
USER_REQUEST = {
    "w1": "phase6 live gate w1: deliberate rollback through execute_revit_code",
    "w2": "phase6 live gate w2: deliberate partial tag batch",
    "w3": "phase6 live gate w3: successful set_parameter",
}


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)


def _build_parser():
    parser = _Parser(prog="test_phase6_live_audit.py")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("template")
    classify = commands.add_parser("classify")
    classify.add_argument("record")
    rehearse = commands.add_parser("rehearse")
    rehearse.add_argument("--rollback-code", required=True)
    rehearse.add_argument("--audit-dir", required=True)
    rehearse.add_argument("--port", type=int, default=DEFAULT_PORT)
    single = commands.add_parser("run-single")
    single.add_argument("--wall-id", type=int, required=True)
    single.add_argument("--parameter", required=True)
    single.add_argument("--view-name", required=True)
    single.add_argument("--tag-id", type=int, required=True)
    single.add_argument("--rollback-code", required=True)
    single.add_argument("--audit-dir", required=True)
    single.add_argument("--out", required=True)
    single.add_argument("--port", type=int, default=DEFAULT_PORT)
    dual = commands.add_parser("run-dual")
    dual.add_argument("--wall-a", type=int, required=True)
    dual.add_argument("--wall-b", type=int, required=True)
    dual.add_argument("--parameter", required=True)
    dual.add_argument("--audit-dir", required=True)
    dual.add_argument("--out", required=True)
    dual.add_argument("--count", type=int, default=DEFAULT_COUNT)
    dual.add_argument("--port", type=int, default=DEFAULT_PORT)
    child = commands.add_parser("child")
    child.add_argument("--child-token", required=True)
    child.add_argument("--audit-dir", required=True)
    child.add_argument("--out", required=True)
    child.add_argument("--port", type=int, required=True)
    child.add_argument("--parameter", required=True)
    child.add_argument("--count", type=int, required=True)
    child.add_argument("--target-a", required=True)
    child.add_argument("--target-b", required=True)
    child.add_argument("--wall-a", type=int, required=True)
    child.add_argument("--wall-b", type=int, required=True)
    return parser


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _secret_value():
    """The configured shared secret, read only through bridge._secret(); None when there is none."""
    try:
        if REPO_ROOT not in sys.path:
            sys.path.insert(0, REPO_ROOT)
        import bridge

        return bridge._secret()
    except Exception:
        return None


def _load_record(path):
    try:
        with open(path, "rb") as handle:
            return json.loads(handle.read().decode("utf-8-sig")), None
    except (OSError, ValueError) as ex:
        return None, "record: cannot read {!r} ({})".format(path, type(ex).__name__)


def _verdict_of(record, secret):
    if not isinstance(record, dict):
        return {"verdict": VERDICT_STOP, "reasons": ["record: not an object"]}
    stage = record.get("stage")
    if stage == STAGE_SINGLE:
        return classify_single(record, secret)
    if stage == STAGE_DUAL:
        return classify_dual(record, secret)
    return {"verdict": VERDICT_STOP,
            "reasons": ["record.stage: expected 'single' or 'dual', got {}".format(_describe(stage))]}


def _posts_sent_of(record):
    value = record.get("posts_sent") if isinstance(record, dict) else None
    return value if _is_int(value) else None


# ------------------------------------------------------- bridge and tool access


def _require_allowed_read(endpoint):
    """Raise ValueError unless ``endpoint`` is one of the three routes a read may name."""
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError("endpoint must be a non-empty string, got {!r}".format(endpoint))
    key = endpoint
    prefix = "/element_properties/"
    if endpoint.startswith(prefix) and len(endpoint) > len(prefix):
        if not endpoint[len(prefix):].isdigit():
            raise ValueError("element id in {!r} is not a number".format(endpoint))
        key = prefix
    if key not in ALLOWED_READS:
        raise ValueError("endpoint {!r} is not on the allow-list".format(endpoint))


def _require_allowed_tool(tool):
    if tool not in ALLOWED_TOOLS:
        raise ValueError("tool {!r} is not on the allow-list".format(tool))


def _set_environment(args):
    """The audit directory and the port, set before the first bridge import (never after one)."""
    os.environ["REVIT_MCP_AUDIT_DIR"] = os.path.abspath(args.audit_dir)
    os.environ["REVIT_PORT"] = str(args.port)


def _bridge():
    """The production bridge module; imported lazily, after the environment is set."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    import bridge

    return bridge


def _main_module():
    """The production server module; importing it registers every tool through the audit wrapper."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    import main as main_module

    return main_module


def _tool_callable(tool):
    """An async ``call(arguments)`` for one registered tool, resolved before anything is counted.

    ``main.mcp.call_tool(...)`` outside a real MCP request hands the tool a Context that
    refuses use, and execute_revit_code reports progress through it, so that route would raise
    before a single byte reached Revit. The function FastMCP registered for the tool is the
    audit wrapper itself (call state, user_request, the real tool, the production bridge and
    the audit writer all run); it is called with ctx=None, as the tools accept.
    """
    _require_allowed_tool(tool)
    registered = _main_module().mcp._tool_manager.get_tool(tool)
    if registered is None:
        raise LookupError("tool {} is not registered".format(tool))

    async def call(arguments):
        return await registered.fn(ctx=None, **arguments)

    return call


def _reply_text(result):
    """The text a tool reply carries, whether it is a string or a list of content blocks."""
    if isinstance(result, tuple) and result and isinstance(result[0], (list, tuple)):
        result = result[0]
    if isinstance(result, (list, tuple)):
        texts = [getattr(item, "text", None) for item in result]
        return "\n".join(text for text in texts if isinstance(text, str))
    return result if isinstance(result, str) else str(result)


def _ex_text(ex):
    """``Type: message``, cut short, with the configured secret replaced if it ever appears."""
    text = "{}: {}".format(type(ex).__name__, ex)[:300]
    try:
        secret = _secret_value()
        if isinstance(secret, str) and secret:
            text = text.replace(secret, "[REDACTED]")
    except Exception:
        pass
    return text


async def _tool_step(record, key, tool, arguments, slot=None, extra=None):
    """Send one write exactly once through the audited tool; the exception text, or None.

    The POST is counted immediately before the call, so a call that raised or timed out still
    counts: its outcome in the model is unknown. The step is never retried here.
    """
    _require_allowed_tool(tool)
    call = _tool_callable(tool)
    step = {"tool": tool, "arguments": dict(arguments), "user_request": arguments.get("user_request"),
            "exception": None}
    if extra:
        step.update(extra)
    if slot is None:
        record["steps"][key] = step
    else:
        step["key"] = key
        slot.append(step)
    record["posts_sent"] += 1  # counted before the call
    try:
        result = await call(arguments)
    except Exception as ex:
        step["exception"] = _ex_text(ex)
        return step["exception"]
    record["replies"][key] = _reply_text(result)
    return None


def _flush():
    import audit

    return audit.flush(10.0)


def _read_audit_dir(path):
    """{file name: [raw lines]} of the audit files in a directory; lines keep any CR they carry."""
    files = {}
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return files
    for name in names:
        full = os.path.join(path, name)
        if not fnmatch.fnmatchcase(name, "audit-*.jsonl") or not os.path.isfile(full):
            continue
        try:
            with open(full, "rb") as handle:
                data = handle.read()
        except OSError:
            continue
        lines = data.decode("utf-8", "replace").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        files[name] = lines
    return files


def _save(path, record):
    """Write the record once; never overwrites. False (and the record on stdout) if it cannot."""
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
        return True
    except OSError as ex:
        print("WARNING: the record could not be written to {} ({}: {}); it follows.".format(
            path, type(ex).__name__, ex))
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return False


# ------------------------------------------------------------------ preflight


async def _read(bridge, endpoint, selector):
    """One allowed GET: (reply, None) or (None, exception text)."""
    try:
        _require_allowed_read(endpoint)
        return await bridge.revit_get(endpoint, target=selector), None
    except Exception as ex:
        return None, "{}: {}".format(type(ex).__name__, ex)


def _describe_reply(reply):
    text = repr(reply)
    return text if len(text) <= 120 else text[:117] + "..."


def _parameter_entry(reply, name):
    """The parameter dict named ``name`` in an element_properties reply, or None."""
    parameters = reply.get("parameters") if isinstance(reply, dict) else None
    for parameter in (parameters if isinstance(parameters, list) else []):
        if isinstance(parameter, dict) and parameter.get("name") == name:
            return parameter
    return None


def _writable_text(entry):
    return bool(entry is not None and entry.get("read_only") is False
                and str(entry.get("storage_type")) == "String")


async def _usable_targets(bridge):
    """(usable entries, None) from discovery, or (None, the reason the targets cannot be trusted)."""
    try:
        found = await bridge.discover_targets()
    except Exception as ex:
        return None, "preflight.targets: discovery failed ({})".format(type(ex).__name__)
    if not isinstance(found, dict) or found.get("status") != "ok":
        message = found.get("message") if isinstance(found, dict) else None
        return None, "preflight.targets: {}".format(message or "discovery gave no usable answer")
    collisions = [u for u in _list(found.get("unusable"))
                  if isinstance(u, dict) and u.get("reason") == "listener-collision"]
    if collisions:
        return None, "preflight.targets: more than one process listens on port {}".format(
            ", ".join(str(u.get("port")) for u in collisions))
    return [u for u in _list(found.get("usable")) if isinstance(u, dict)], None


async def _documents_of(bridge, selector):
    """(count, None) when GET /documents/ lists exactly one document, else (count or None, reason)."""
    reply, problem = await _read(bridge, "/documents/", selector)
    documents = reply.get("documents") if isinstance(reply, dict) else None
    if not isinstance(documents, list):
        return None, "preflight.documents: GET /documents/ gave no listing ({})".format(
            problem or _describe_reply(reply))
    if len(documents) != 1:
        return len(documents), "preflight.documents: expected exactly one open document, got {}".format(
            len(documents))
    return 1, None


async def _preflight_target(bridge, args, record):
    """The checks run-single and rehearse share: one Revit, answering, the only listener, one document."""
    pre = record["preflight"]
    configured = getattr(bridge, "REVIT_PORT", None)
    if configured is not None and configured != args.port:
        return ("preflight.port: the bridge targets port {} but --port is {}; start the script with "
                "REVIT_PORT unset or equal to --port".format(configured, args.port))
    usable, reason = await _usable_targets(bridge)
    if reason:
        return reason
    if len(usable) != 1:
        return "preflight.targets: expected exactly one usable Revit target, found {}".format(len(usable))
    target = usable[0]
    if target.get("port") != args.port:
        return "preflight.port: the only usable Revit listens on port {} but --port is {}".format(
            target.get("port"), args.port)
    selector, pid = target.get("selector"), target.get("pid")
    pre["selector"] = selector
    record["revit_pids"] = [pid]
    reply, problem = await _read(bridge, "/status/", selector)
    identity = reply.get("process_identity") if isinstance(reply, dict) else None
    pre["status_ok"] = bool(isinstance(reply, dict) and not reply.get("error")
                            and isinstance(identity, dict) and identity.get("pid") == pid)
    if not pre["status_ok"]:
        return "preflight.status_ok: GET /status/ did not answer with the process identity ({})".format(
            problem or _describe_reply(reply))
    try:
        snapshot = bridge.listener_snapshot([args.port])
    except Exception:
        snapshot = None
    owners = snapshot.get(args.port) if isinstance(snapshot, dict) else None
    if not (isinstance(owners, list) and all(_is_int(p) and p > 0 for p in owners)):
        return "preflight.listeners: the OS listener inventory is unavailable for port {}".format(args.port)
    pre["listeners"] = list(owners)
    if owners != [pid]:
        return "preflight.listeners: expected exactly one owner of port {}, got {}".format(
            args.port, len(owners))
    pre["documents"], reason = await _documents_of(bridge, selector)
    return reason


async def _preflight_single(bridge, args, record):
    """Read-only checks before any write. Returns the stop reason, or None when all pass."""
    reason = await _preflight_target(bridge, args, record)
    if reason:
        return reason
    pre = record["preflight"]
    selector = pre["selector"]
    reply, problem = await _read(bridge, "/element_properties/{}".format(args.wall_id), selector)
    entry = _parameter_entry(reply, args.parameter)
    pre["parameter_writable"] = _writable_text(entry)
    if not pre["parameter_writable"]:
        return ("preflight.parameter_writable: wall {} has no writable text parameter named {!r} "
                "({})".format(args.wall_id, args.parameter, problem or _describe_reply(entry or reply)))
    reply, problem = await _read(bridge, "/element_properties/{}".format(args.tag_id), selector)
    pre["tag_element_found"] = bool(isinstance(reply, dict) and not reply.get("error")
                                    and reply.get("element_id") == args.tag_id)
    if not pre["tag_element_found"]:
        return "preflight.tag_element_found: element {} was not read ({})".format(
            args.tag_id, problem or _describe_reply(reply))
    return None


async def _preflight_dual(bridge, args, record):
    """Two usable Revit instances, one document each, the parameter writable on each wall."""
    pre = record["preflight"]
    usable, reason = await _usable_targets(bridge)
    if reason:
        return reason
    if len(usable) != 2:
        return "preflight.targets: expected exactly two usable Revit targets, found {}".format(len(usable))
    usable = sorted(usable, key=lambda t: t.get("port") if _is_int(t.get("port")) else 0)
    if usable[0].get("port") == usable[1].get("port") or usable[0].get("pid") == usable[1].get("pid"):
        return "preflight.targets: the two targets are not two distinct Revit processes"
    targets = []
    pre["targets"] = targets
    record["revit_pids"] = [t.get("pid") for t in usable]
    for target, wall in zip(usable, (args.wall_a, args.wall_b)):
        info = {"port": target.get("port"), "pid": target.get("pid"), "selector": target.get("selector"),
                "wall_id": wall, "documents": None, "parameter_writable": None}
        targets.append(info)
        info["documents"], reason = await _documents_of(bridge, info["selector"])
        if reason:
            return "{} (Revit on port {})".format(reason, info["port"])
        reply, problem = await _read(bridge, "/element_properties/{}".format(wall), info["selector"])
        info["parameter_writable"] = _writable_text(_parameter_entry(reply, args.parameter))
        if not info["parameter_writable"]:
            return ("preflight.parameter_writable: wall {} on port {} has no writable text parameter "
                    "named {!r} ({})".format(wall, info["port"], args.parameter,
                                             problem or _describe_reply(reply)))
    pre["status_ok"] = True  # discovery answered the identity handshake of both
    pre["parameter_writable"] = True
    return None


# --------------------------------------------------------------------- finish


def _finish(args, record, reason):
    """Flush the audit writer, read every audit file into the record and save it once."""
    try:
        flushed = _flush()
    except Exception:
        flushed = False
    if not flushed and not reason:
        reason = "the audit writer did not finish writing before the files were read"
    record["audit_files"] = _read_audit_dir(os.path.abspath(args.audit_dir))
    record["stop_reason"] = reason
    record["recorded_at"] = _now()
    return _save(args.out, record)


def _print_report(record, secret, extra_reasons=()):
    """Print the verdict token, POSTS_SENT, the secret count and the reasons; return the exit code."""
    stop = record.get("stop_reason") if isinstance(record, dict) else None
    posts = _posts_sent_of(record)
    if stop and posts == 0:
        # A preflight stop: nothing was written, so the classifier's list of missing steps is noise.
        result = {"verdict": VERDICT_STOP, "reasons": []}
    else:
        result = _verdict_of(record, secret)
    reasons = list(extra_reasons) + (["stop: {}".format(stop)] if stop else []) + result["reasons"]
    ok = result["verdict"] == VERDICT_OK and not extra_reasons and not stop
    found = record_secret_occurrences(record, secret) if (
        isinstance(record, dict) and isinstance(secret, str) and secret) else None
    for line in report(VERDICT_OK if ok else VERDICT_STOP, reasons, posts, found):
        print(line)
    return 0 if ok else 1


def _cmd_classify(path):
    record, problem = _load_record(path)
    return _print_report(record, _secret_value(), [problem] if problem else [])


def _read_code(path):
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8-sig")


# ----------------------------------------------------------------- run-single


async def _execute_single(args, record):
    bridge = _bridge()
    reason = await _preflight_single(bridge, args, record)
    if reason:
        return reason
    _main_module()
    selector = record["preflight"]["selector"]
    value = "phase6-live-{}".format(uuid.uuid4().hex[:8])
    plan = (
        ("w1", "execute_revit_code",
         {"code": record["inputs"]["rollback_code"], "description": "phase6 live gate: deliberate rollback",
          "target": selector, "user_request": USER_REQUEST["w1"]}),
        ("w2", "tag_elements",
         {"element_ids": [args.tag_id, BAD_ID], "view_name": args.view_name, "target": selector,
          "user_request": USER_REQUEST["w2"]}),
        ("w3", "set_parameter",
         {"element_id": args.wall_id, "parameter_name": args.parameter, "value": value,
          "target": selector, "user_request": USER_REQUEST["w3"]}),
    )
    problems = []
    for key, tool, arguments in plan:
        problem = await _tool_step(record, key, tool, arguments)
        if problem:
            problems.append("{}: {}".format(key, problem))
    return "; ".join(problems) or None


async def _run_single(args, code):
    record = evidence_template()
    record["stage"] = STAGE_SINGLE
    record["inputs"].update({
        "wall_id": args.wall_id, "parameter": args.parameter, "view_name": args.view_name,
        "tag_id": args.tag_id, "rollback_code": code, "port": args.port,
        "audit_dir": os.path.abspath(args.audit_dir),
    })
    record["server_pids"]["parent"] = os.getpid()
    reason = None
    written = False
    try:
        reason = await _execute_single(args, record)
    except Exception as ex:
        reason = "unexpected {}".format(_ex_text(ex))
    except BaseException as ex:
        reason = "interrupted ({})".format(type(ex).__name__)
        raise
    finally:
        written = _finish(args, record, reason)
    exit_code = _print_report(record, _secret_value())
    if written:
        print("record: {}".format(args.out))
    return exit_code


def _cmd_run_single(args):
    problem = refusal(args)
    if problem:
        print("refused: {}".format(problem))
        return 2
    try:
        code = _read_code(args.rollback_code)
    except (OSError, ValueError) as ex:
        print("refused: --rollback-code cannot be read as UTF-8 text ({})".format(type(ex).__name__))
        return 2
    _set_environment(args)
    return asyncio.run(_run_single(args, code))


# ------------------------------------------------------------------ rehearse


def _rehearsal_verdict(record, files):
    """("ROLLED_BACK" | "COMMITTED" | "OTHER", the audit entry of the call or None)."""
    audit_id = audit_id_of(record["replies"].get("w1"))
    entries = parse_audit_files(files)[0]
    found = [e for _n, e in entries if audit_id and e.get("call_id") == audit_id]
    if len(found) != 1:
        return "OTHER", None
    entry = found[0]
    if entry.get("outcome") == "rolled_back" and entry.get("http_status") == 409:
        return "ROLLED_BACK", entry
    if entry.get("outcome") == "success" and entry.get("transaction_status") == "Committed":
        return "COMMITTED", entry
    return "OTHER", entry


async def _execute_rehearse(args, record, code):
    bridge = _bridge()
    reason = await _preflight_target(bridge, args, record)
    if reason:
        return reason
    _main_module()
    arguments = {"code": code, "description": REHEARSAL_REQUEST,
                 "target": record["preflight"]["selector"], "user_request": REHEARSAL_REQUEST}
    problem = await _tool_step(record, "w1", "execute_revit_code", arguments)
    return "w1: {}".format(problem) if problem else None


async def _run_rehearse(args, code):
    record = evidence_template()
    record["stage"] = "rehearse"
    reason = None
    try:
        reason = await _execute_rehearse(args, record, code)
    except Exception as ex:
        reason = "unexpected {}".format(_ex_text(ex))
    try:
        _flush()
    except Exception:
        pass
    files = _read_audit_dir(os.path.abspath(args.audit_dir))
    verdict, entry = _rehearsal_verdict(record, files) if "w1" in record["replies"] else ("OTHER", None)
    print("REHEARSAL_{}".format(verdict))
    print("POSTS_SENT={}".format(record["posts_sent"]))
    if entry is not None:
        print("entry: outcome={} http_status={} transaction_status={}".format(
            entry.get("outcome"), entry.get("http_status"), entry.get("transaction_status")))
    if reason:
        print("stop: {}".format(reason))
    if record["posts_sent"] == 0:
        print(MSG_NO_WRITE)
    return 0 if verdict == "ROLLED_BACK" else 1


def _cmd_rehearse(args):
    problem = refusal(args)
    if problem:
        print("refused: {}".format(problem))
        return 2
    try:
        code = _read_code(args.rollback_code)
    except (OSError, ValueError) as ex:
        print("refused: --rollback-code cannot be read as UTF-8 text ({})".format(type(ex).__name__))
        return 2
    _set_environment(args)
    return asyncio.run(_run_rehearse(args, code))


# ------------------------------------------------------------------ run-dual


async def _issue_calls(record, who, targets, count, parameter, server_pid):
    """``count`` set_parameter calls per target, all handed to the tool at once (asyncio.gather)."""
    slot = record["steps"][who]
    jobs = []
    for index, target in enumerate(targets):
        for i in range(1, count + 1):
            key = "{}-{}-{}".format(who, index, i)
            value = "phase6-dual-{}-{}".format(server_pid, i)
            arguments = {
                "element_id": target["wall_id"], "parameter_name": parameter, "value": value,
                "target": target["selector"],
                "user_request": "phase6 dual gate: {} call {}".format(who, key),
            }
            jobs.append(_tool_step(record, key, "set_parameter", arguments, slot=slot,
                                   extra={"pid": target["pid"], "element_id": target["wall_id"],
                                          "value": value}))
    await asyncio.gather(*jobs)


def _child_argv(args, token, child_path, targets):
    return [sys.executable, os.path.abspath(__file__), "child",
            "--child-token", token, "--audit-dir", os.path.abspath(args.audit_dir),
            "--out", child_path, "--port", str(args.port), "--parameter", args.parameter,
            "--count", str(args.count), "--target-a", targets[0]["selector"],
            "--target-b", targets[1]["selector"], "--wall-a", str(targets[0]["wall_id"]),
            "--wall-b", str(targets[1]["wall_id"])]


def _start_child(argv, env):
    return subprocess.Popen(argv, env=env, cwd=REPO_ROOT, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _wait_child(child):
    """(exit code, None) or (None, 'timed out'); a child that never finishes is killed."""
    try:
        child.communicate(timeout=CHILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        child.kill()
        try:
            child.communicate(timeout=30)
        except Exception:
            pass
        return None, "timed out"
    return child.returncode, None


def _merge_child(record, child_path, code, problem):
    """Fold the child's record into the parent's; the list of stop reasons (empty when all is well)."""
    reasons = []
    record["child_exit"] = code
    try:
        with open(child_path, "rb") as handle:
            child = json.loads(handle.read().decode("utf-8-sig"))
    except (OSError, ValueError):
        child = None
    steps = child.get("steps") if isinstance(child, dict) else None
    pids = child.get("server_pids") if isinstance(child, dict) else None
    usable = (isinstance(steps, dict) and isinstance(steps.get("child"), list)
              and isinstance(child.get("replies"), dict) and _is_int(child.get("posts_sent"))
              and isinstance(pids, dict) and _is_int(pids.get("child")))
    if usable:
        record["steps"]["child"] = steps["child"]
        record["replies"].update(child["replies"])
        record["server_pids"]["child"] = pids["child"]
        record["posts_sent"] += child["posts_sent"]
        if child.get("stop_reason"):
            reasons.append("child: {}".format(child["stop_reason"]))
    else:
        record["posts_sent"] = None
        reasons.append("child: no usable child record, so its POSTS_SENT is unknown; treat the "
                       "one-shot gate as consumed")
    if problem:
        reasons.append("child: the child process timed out and was killed")
    elif code != 0:
        reasons.append("child: the child process exited with code {}".format(code))
    return reasons


async def _execute_dual(args, record, token, child_path):
    bridge = _bridge()
    reason = await _preflight_dual(bridge, args, record)
    if reason:
        return reason
    _main_module()
    targets = record["preflight"]["targets"]
    env = dict(os.environ)
    env[CHILD_TOKEN_ENV] = token
    try:
        child = _start_child(_child_argv(args, token, child_path, targets), env)
    except OSError as ex:
        return "child: could not be started ({}); nothing was written".format(type(ex).__name__)
    reasons = []
    try:
        await _issue_calls(record, "parent", targets, args.count, args.parameter, os.getpid())
    except Exception as ex:
        reasons.append("parent: unexpected {}".format(_ex_text(ex)))
    code, problem = await asyncio.to_thread(_wait_child, child)
    reasons.extend(_merge_child(record, child_path, code, problem))
    failed = ["{}: {}".format(c.get("key"), c.get("exception"))
              for c in _list(record["steps"]["parent"]) if isinstance(c, dict) and c.get("exception")]
    reasons.extend(failed)
    return "; ".join(reasons) or None


async def _run_dual(args):
    record = evidence_template()
    record["stage"] = STAGE_DUAL
    record["inputs"].update({
        "parameter": args.parameter, "port": args.port, "wall_a": args.wall_a, "wall_b": args.wall_b,
        "count": args.count, "audit_dir": os.path.abspath(args.audit_dir),
    })
    record["server_pids"]["parent"] = os.getpid()
    token = uuid.uuid4().hex
    reason = None
    written = False
    try:
        reason = await _execute_dual(args, record, token, _child_record_path(args.out))
    except Exception as ex:
        reason = "unexpected {}".format(_ex_text(ex))
    except BaseException as ex:
        reason = "interrupted ({})".format(type(ex).__name__)
        raise
    finally:
        written = _finish(args, record, reason)
    code = _print_report(record, _secret_value())
    if written:
        print("record: {}".format(args.out))
    return code


def _cmd_run_dual(args):
    problem = refusal(args)
    if problem:
        print("refused: {}".format(problem))
        return 2
    _set_environment(args)
    return asyncio.run(_run_dual(args))


# ----------------------------------------------------------------------- child


def _child_refusal(args):
    """Why the child may not run, or None; it shares the runner's audit directory, so it may be non-empty."""
    for name in ("wall_a", "wall_b"):
        value = getattr(args, name)
        if not (_is_int(value) and value > 0 and value != BAD_ID):
            return "--{} must be a positive element id".format(name.replace("_", "-"))
    if not _nonblank(args.parameter):
        return "--parameter must not be blank"
    if not (_is_int(args.count) and 1 <= args.count <= MAX_COUNT):
        return "--count must be a whole number from 1 to {}".format(MAX_COUNT)
    if not (_is_int(args.port) and 1 <= args.port <= 65535):
        return "--port must be between 1 and 65535"
    if os.path.exists(args.out):
        return "{} already exists; a record is never overwritten".format(args.out)
    if not os.path.isdir(os.path.dirname(os.path.abspath(args.out))):
        return "the directory of --out does not exist ({})".format(args.out)
    return None


async def _run_child(args, targets):
    record = evidence_template()
    record["stage"] = "dual-child"
    record["server_pids"]["child"] = os.getpid()
    reason = None
    try:
        _bridge()
        _main_module()
        await _issue_calls(record, "child", targets, args.count, args.parameter, os.getpid())
    except Exception as ex:
        reason = "unexpected {}".format(_ex_text(ex))
    try:
        _flush()
    except Exception:
        pass
    problems = ["{}: {}".format(c.get("key"), c.get("exception"))
                for c in _list(record["steps"]["child"]) if isinstance(c, dict) and c.get("exception")]
    if problems and not reason:
        reason = "; ".join(problems)
    record["stop_reason"] = reason
    record["recorded_at"] = _now()
    _save(args.out, record)
    return 1 if reason and not record["steps"]["child"] else 0


def _cmd_child(args):
    expected = os.environ.get(CHILD_TOKEN_ENV)
    if not (expected and _nonblank(args.child_token) and hmac.compare_digest(
            expected.encode("utf-8"), args.child_token.encode("utf-8"))):
        print("refused: child is internal and runs only when started by run-dual")
        return 2
    problem = _child_refusal(args)
    if problem:
        print("refused: {}".format(problem))
        return 2
    _set_environment(args)
    bridge = _bridge()
    targets = []
    for selector, wall in ((args.target_a, args.wall_a), (args.target_b, args.wall_b)):
        try:
            targets.append({"selector": selector, "wall_id": wall, "pid": bridge.parse_target(selector)["pid"]})
        except ValueError:
            print("refused: a target selector is not valid")
            return 2
    return asyncio.run(_run_child(args, targets))


# ---------------------------------------------------------------------- main


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        namespace = _build_parser().parse_args(args)
    except _UsageError as ex:
        print("usage error: {}".format(ex))
        print(USAGE)
        return 2
    if namespace.command == "template":
        print(json.dumps(evidence_template(), indent=2))
        return 0
    if namespace.command == "classify":
        return _cmd_classify(namespace.record)
    if namespace.command == "rehearse":
        return _cmd_rehearse(namespace)
    if namespace.command == "run-single":
        return _cmd_run_single(namespace)
    if namespace.command == "run-dual":
        return _cmd_run_dual(namespace)
    if namespace.command == "child":
        return _cmd_child(namespace)
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
