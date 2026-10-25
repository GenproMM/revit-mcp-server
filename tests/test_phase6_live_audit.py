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

Every write goes through the path an engineer's assistant uses: ``main.mcp.call_tool`` (the
audited wrapper, the real tool, the production bridge and the audit writer), with
REVIT_MCP_AUDIT_DIR pointing at an operator-chosen scratch directory before the first
write. The reads of the preflight go through ``bridge.revit_get``. Nothing is judged by
eye: ``classify_single`` and ``classify_dual`` turn the record and the audit files into
PHASE6_AUDIT_OK or PHASE6_AUDIT_STOP with named reasons.

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
run-dual the first Revit (lowest port) gets --wall-a and the second --wall-b.

``rehearse`` sends exactly one execute_revit_code call with the operator's code and the
user_request "phase6 rehearsal", then reads the audit entry of that call and prints
REHEARSAL_ROLLED_BACK (HTTP 409, rolled_back), REHEARSAL_COMMITTED (the code committed) or
REHEARSAL_OTHER, plus POSTS_SENT=1. It does not judge the audit. It is the repeatable
rehearsal that research assumption A3 requires before the one-shot run: use a fresh
--audit-dir each time.

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
import hashlib
import json
import os
import re
import sys
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
    return parser


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


def _print_report(record, secret, extra_reasons=()):
    result = _verdict_of(record, secret)
    reasons = list(extra_reasons) + result["reasons"]
    ok = result["verdict"] == VERDICT_OK and not extra_reasons
    found = record_secret_occurrences(record, secret) if (
        isinstance(record, dict) and isinstance(secret, str) and secret) else None
    for line in report(VERDICT_OK if ok else VERDICT_STOP, reasons, _posts_sent_of(record), found):
        print(line)
    return 0 if ok else 1


def _cmd_classify(path):
    record, problem = _load_record(path)
    return _print_report(record, _secret_value(), [problem] if problem else [])


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
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
