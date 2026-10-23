# -*- coding: utf-8 -*-
"""Phase 4 live outcome gate (plan 04-10 writes it, plan 04-11 runs it): one-shot runner and classifier.

Older tier: a standalone script, run once by hand by an engineer on a bench machine,
excluded from pytest (``testpaths = ["tests/unit"]``). It defines no ``test_*`` function
and does nothing at import, so the unit suite can import the pure classifier without
side effects (tests/unit/test_phase4_live_outcomes.py). It never runs in Revit, so it is
ordinary CPython; the IronPython rules of the Revit half do not apply here.

What this is
------------
Phase 4 made every mutating route answer with an ``outcome`` block and a status that
tells the truth (success, partial, failed, rolled_back). Those replies are proven in a
fake pyRevit world; criteria 1 to 4 of the phase also need one live look. This script is
that look. It runs the D-11 live set against a freshly restarted Revit through the
PRODUCTION bridge (``bridge.revit_get`` / ``bridge.revit_post``, never an MCP stdio
session, because a 200 reply's ``outcome`` is only visible in the raw dict) and records,
for every step, the raw reply exactly as the bridge returned it and the text the model
would read (``tools.utils.format_response``). ``classify_outcomes`` turns the record into
ok or stop. Nothing is judged by eye.

The five write steps, in this order, each sent exactly once:

  s1  modify_element    one wall parameter                              (single-element family)
  s2  tag_elements      [valid id, 999999999]                           (batch family, criteria 3 and 4)
  s3  tag_elements      [999999999]                                     (all failed, HTTP 422)
  s4  export_ifc        to a scratch path outside the repository        (export family)
  s5  delete_elements   the tag ids step 2 created                      (TRUTH-02 live)

Commands
--------
    uv run python tests/test_phase4_live_outcomes.py template
    uv run python tests/test_phase4_live_outcomes.py run --wall-id N --parameter NAME --value TEXT
        --view-name VIEW --tag-id N --ifc-path C:/scratch/out.ifc --out C:/scratch/record.json [--port 48884]
    uv run python tests/test_phase4_live_outcomes.py classify RECORD.json

``template`` prints the empty record. ``classify`` re-judges a saved record. ``run`` does
the live set.

Output tokens: PHASE4_OUTCOMES_OK and PHASE4_OUTCOMES_STOP, always followed by a line
POSTS_SENT=<n> (POSTS_SENT=unknown for a record that carries no count). Exit codes:
0 ok, 1 stop, 2 usage error or refusal.

POSTS_SENT and the one-shot rule
--------------------------------
``posts_sent`` is the number of POST requests handed to the bridge, counted immediately
before each ``revit_post`` call, so a POST that raised or timed out still counts: its
outcome in the model is unknown. A write step is never repeated.

  POSTS_SENT=0   the read-only preflight stopped the run before any write. Nothing was
                 written to the model. Fix the condition the output names and run again
                 with a fresh --out (the old record is never overwritten).
  POSTS_SENT>=1  a write step was sent. The one-shot gate is consumed: never run this
                 again, whatever the verdict. A stop after that point is a finding about
                 the routes, to be read from the record, not a reason to retry.

Safety (what run refuses, before it sends any request)
------------------------------------------------------
* an --out record that already exists (a record is never overwritten);
* an --out record or an --ifc-path inside the repository (a raw record names the ports,
  ids and paths of a local Revit; an export is a model);
* an --ifc-path that already exists, or whose directory or the --out directory is missing;
* a wall id, tag id or text that is empty or not usable.

Then a read-only preflight, still before any write: GET /status/ answers; the OS listener
inventory (``bridge.listener_snapshot``) shows exactly one owner of the port; GET
/documents/ lists exactly one open document; GET /element_properties/ of the wall shows the
parameter present and not read-only; GET /element_properties/ of the tag target answers. Any
failure is recorded with posts_sent 0 and the run stops.

The script names only these routes: /status/, /documents/, /element_properties/,
/modify_element/, /tag_elements/, /export_ifc/ and /delete_elements/. It never saves the
document, never uses the arbitrary-code route, and never reads, prints or records the shared
secret (the bridge adds it to the request body itself). Step 5 deletes only ids that step 2
reported as new tags, never the wall or the tagged element.

Operator procedure (plan 04-11 follows this; the engineer controls the bench)
-----------------------------------------------------------------------------
1. Fully close Revit and reopen it with NO model (never pyRevit Reload after an edit under
   ``revit_mcp/``: it can crash Revit). Poll GET /status/ until it answers. Check exactly one
   listener holds the Routes port.
2. Open ONE scratch, non-workshared model through open_model. Never open a workshared model
   from the command line (it raises the workset dialog and blocks the routes forever). No
   other document may be open. Never save it.
3. Read, with the read-only tools, what the run needs: a wall id; a writable text parameter on
   that wall (for example Comments); the name of a plan view of this model; one taggable
   element visible in that view (a door or the wall itself). Confirm the view exists by name:
   an unknown view name is refused by tag_elements before its transaction, which would waste
   step 2.
4. Choose an --ifc-path and an --out path outside the repository, in an existing scratch
   directory, neither of which exists yet.
5. Run ``run`` once. Read the token, POSTS_SENT and the reasons.
6. If the output ends with POSTS_SENT=0 the preflight stopped before any write: fix the named
   condition and run again with a fresh --out. Once POSTS_SENT is 1 or more, never run again,
   whatever the verdict. Close the scratch model without saving.
7. Attach the --out record and the printed output to the 04-11 verification.

The record is machine local: keep it outside the repository.
"""
import argparse
import asyncio
import datetime
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BAD_ID = 999999999
DEFAULT_PORT = 48884

SENTINEL_OK = "PHASE4_OUTCOMES_OK"
SENTINEL_STOP = "PHASE4_OUTCOMES_STOP"

VERDICT_OK = "ok"
VERDICT_STOP = "stop"

STEP_KEYS = ("s1", "s2", "s3", "s4", "s5")
BANNER_PARTIAL = "=== PARTIAL SUCCESS ==="
REASON_NOT_FOUND = "Element not found"

# The only routes this procedure may name. A call outside the list is refused before the
# bridge is touched (see _require_allowed).
ALLOWED_ENDPOINTS = frozenset((
    "/status/",
    "/documents/",
    "/element_properties/",
    "/modify_element/",
    "/tag_elements/",
    "/export_ifc/",
    "/delete_elements/",
))
_PROPERTIES_ROUTE = "/element_properties/"

_HTTP_ERROR = re.compile(r"Error: (\d{3}) - ")


# ------------------------------------------------------------- primitives


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _require_allowed(endpoint):
    """Raise ValueError unless `endpoint` is one of the seven allowed routes."""
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError("endpoint must be a non-empty string, got {!r}".format(endpoint))
    key = endpoint
    if endpoint.startswith(_PROPERTIES_ROUTE) and len(endpoint) > len(_PROPERTIES_ROUTE):
        if not endpoint[len(_PROPERTIES_ROUTE):].isdigit():
            raise ValueError("element id in {!r} is not a number".format(endpoint))
        key = _PROPERTIES_ROUTE
    if key not in ALLOWED_ENDPOINTS:
        raise ValueError("endpoint {!r} is not on the allow-list".format(endpoint))


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _plain(value):
    """A plain JSON-safe copy of a bridge reply.

    The bridge tags a reply with provenance (an attribute on a dict or str subclass); the
    copy carries none of it. A reserved ``_mcp`` key is dropped at every depth, so a record
    can never hold the shared-secret envelope even if a body ever carried it.
    """
    if isinstance(value, dict):
        return dict((str(key), _plain(item)) for key, item in value.items() if key != "_mcp")
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, str):
        return str(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _outside_repo(path):
    real = os.path.normcase(os.path.realpath(path))
    root = os.path.normcase(os.path.realpath(REPO_ROOT))
    try:
        return os.path.commonpath([real, root]) != root
    except ValueError:  # different drives
        return True


# ----------------------------------------------------------- bridge access

# The Routes port the bridge must be imported with. bridge.py reads REVIT_PORT once at
# import, so the run command sets this before the first import (never after one).
_BRIDGE_PORT = DEFAULT_PORT


def _bridge():
    """The production bridge module; imported lazily so the classifier stays light."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    if "bridge" not in sys.modules:
        os.environ["REVIT_PORT"] = str(_BRIDGE_PORT)
    import bridge

    return bridge


# ---------------------------------------------------------------- template


def evidence_template():
    """The record skeleton; every value starts null, which classifies as stop."""
    return {
        "inputs": {
            "wall_id": None,
            "parameter": None,
            "value": None,
            "view_name": None,
            "tag_id": None,
            "ifc_path": None,
            "port": None,
        },
        "preflight": {
            "status_ok": None,
            "listeners": None,
            "documents": None,
            "parameter_writable": None,
            "tag_element_found": None,
        },
        "posts_sent": None,
        "steps": dict((key, None) for key in STEP_KEYS),
    }


# --------------------------------------------------------------- classifier


def _dict(value):
    return value if isinstance(value, dict) else {}


def _http_error(raw):
    """(http status, JSON body or None) of an 'Error: NNN - {json}' reply; (None, None) otherwise."""
    if not isinstance(raw, str):
        return None, None
    found = _HTTP_ERROR.match(raw)
    if not found:
        return None, None
    status = int(found.group(1))
    try:
        body, _end = json.JSONDecoder().raw_decode(raw[found.end():].lstrip())
    except ValueError:
        return status, None
    return status, body if isinstance(body, dict) else None


def _describe(value):
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _committed_success(label, step, reasons):
    """Shared check for a 200 success reply with a committed outcome; returns the outcome or None."""
    raw = step.get("raw")
    if not isinstance(raw, dict):
        reasons.append("{}.raw: expected a 200 reply object, got {}".format(label, _describe(raw)))
        return None
    if raw.get("status") != "success":
        reasons.append("{}.raw.status: expected 'success', got {}".format(label, _describe(raw.get("status"))))
    outcome = raw.get("outcome")
    if not isinstance(outcome, dict):
        reasons.append("{}.raw.outcome: missing".format(label))
        return None
    if outcome.get("transaction_status") != "Committed":
        reasons.append("{}.raw.outcome.transaction_status: expected 'Committed', got {}".format(
            label, _describe(outcome.get("transaction_status"))))
    if outcome.get("failed") != []:
        reasons.append("{}.raw.outcome.failed: expected none, got {}".format(label, _describe(outcome.get("failed"))))
    return outcome


def _judge_preflight(record, reasons):
    pre = record.get("preflight")
    if not isinstance(pre, dict):
        reasons.append("preflight: missing")
        return
    if pre.get("status_ok") is not True:
        reasons.append("preflight.status_ok: GET /status/ did not answer ({})".format(
            _describe(pre.get("status_ok"))))
    listeners = pre.get("listeners")
    if not (isinstance(listeners, list) and len(listeners) == 1 and _is_int(listeners[0])):
        reasons.append("preflight.listeners: expected exactly one owner of the port, got {}".format(
            _describe(listeners)))
    if not (_is_int(pre.get("documents")) and pre.get("documents") == 1):
        reasons.append("preflight.documents: expected exactly one open document, got {}".format(
            _describe(pre.get("documents"))))
    if pre.get("parameter_writable") is not True:
        reasons.append("preflight.parameter_writable: the wall parameter is absent or read-only ({})".format(
            _describe(pre.get("parameter_writable"))))


def _judge_s1(step, inputs, reasons):
    outcome = _committed_success("s1", step, reasons)
    if outcome is not None and outcome.get("succeeded") != [inputs.get("parameter")]:
        reasons.append("s1.raw.outcome.succeeded: expected [{}], got {}".format(
            _describe(inputs.get("parameter")), _describe(outcome.get("succeeded"))))


def _judge_s2(step, inputs, reasons):
    raw = step.get("raw")
    if not isinstance(raw, dict):
        reasons.append("s2.raw: expected a 200 reply object, got {}".format(_describe(raw)))
        return
    if raw.get("status") != "partial":
        reasons.append("s2.raw.status: expected 'partial', got {}".format(_describe(raw.get("status"))))
    outcome = raw.get("outcome")
    if not isinstance(outcome, dict):
        reasons.append("s2.raw.outcome: missing")
    else:
        if outcome.get("succeeded") != [inputs.get("tag_id")]:
            reasons.append("s2.raw.outcome.succeeded: expected [{}], got {}".format(
                _describe(inputs.get("tag_id")), _describe(outcome.get("succeeded"))))
        expected = [{"item": BAD_ID, "reason": REASON_NOT_FOUND}]
        if outcome.get("failed") != expected:
            reasons.append("s2.raw.outcome.failed: expected {}, got {}".format(
                _describe(expected), _describe(outcome.get("failed"))))
    rendered = step.get("rendered")
    if not isinstance(rendered, str) or BANNER_PARTIAL not in rendered:
        reasons.append("s2.rendered: the text the model reads has no '{}' banner".format(BANNER_PARTIAL))
    elif str(BAD_ID) not in rendered:
        reasons.append("s2.rendered: the text the model reads does not name {}".format(BAD_ID))


def _judge_s3(step, reasons):
    raw = step.get("raw")
    status, body = _http_error(raw)
    if status != 422:
        reasons.append("s3.raw: expected an 'Error: 422' reply, got {}".format(_describe(raw)))
        return
    if body is None:
        reasons.append("s3.raw: the 422 body is not a JSON object")
        return
    if body.get("status") != "failed":
        reasons.append("s3.raw.status: expected 'failed', got {}".format(_describe(body.get("status"))))
    outcome = body.get("outcome")
    if not isinstance(outcome, dict):
        reasons.append("s3.raw.outcome: missing")
        return
    failed = outcome.get("failed")
    if not (isinstance(failed, list)
            and any(isinstance(entry, dict) and entry.get("item") == BAD_ID for entry in failed)):
        reasons.append("s3.raw.outcome.failed: expected an entry for {}, got {}".format(BAD_ID, _describe(failed)))
    if outcome.get("succeeded") != []:
        reasons.append("s3.raw.outcome.succeeded: expected none, got {}".format(_describe(outcome.get("succeeded"))))


def _judge_s4(step, inputs, reasons):
    outcome = _committed_success("s4", step, reasons)
    if outcome is not None and outcome.get("succeeded") != [inputs.get("ifc_path")]:
        reasons.append("s4.raw.outcome.succeeded: expected [{}], got {}".format(
            _describe(inputs.get("ifc_path")), _describe(outcome.get("succeeded"))))
    if step.get("file_exists") is not True:
        reasons.append("s4.file_exists: the export file was not found on disk ({})".format(
            _describe(step.get("file_exists"))))


def _judge_s5(step, reasons):
    if "skipped" in step:
        reasons.append("s5: skipped ({})".format(_describe(step.get("skipped"))))
    outcome = _committed_success("s5", step, reasons)
    ids = _dict(step.get("body")).get("element_ids")
    if not (isinstance(ids, list) and ids and all(_is_int(i) for i in ids)):
        reasons.append("s5.body.element_ids: expected the tag ids from step 2, got {}".format(_describe(ids)))
    elif outcome is not None and outcome.get("succeeded") != ids:
        reasons.append("s5.raw.outcome.succeeded: expected {}, got {}".format(
            _describe(ids), _describe(outcome.get("succeeded"))))


def _judge(record):
    """The reasons a record is not ok; an empty list means ok. May raise; classify_outcomes catches."""
    if not isinstance(record, dict):
        return ["record: not an object ({})".format(type(record).__name__)]
    reasons = []
    _judge_preflight(record, reasons)
    inputs = _dict(record.get("inputs"))
    steps = record.get("steps")
    if not isinstance(steps, dict):
        reasons.append("steps: missing")
        return reasons
    judges = (
        ("s1", lambda step: _judge_s1(step, inputs, reasons)),
        ("s2", lambda step: _judge_s2(step, inputs, reasons)),
        ("s3", lambda step: _judge_s3(step, reasons)),
        ("s4", lambda step: _judge_s4(step, inputs, reasons)),
        ("s5", lambda step: _judge_s5(step, reasons)),
    )
    for key, judge in judges:
        step = steps.get(key)
        if not isinstance(step, dict):
            reasons.append("{}: step was not recorded".format(key))
            continue
        judge(step)
    return reasons


def _posts_sent_of(record):
    value = record.get("posts_sent") if isinstance(record, dict) else None
    return value if _is_int(value) else None


def classify_outcomes(record):
    """Judge a record: {"verdict": "ok" | "stop", "reasons": [...], "posts_sent": int | None}.

    Pure and never raises: any exception is a stop with the exception text as its reason.
    posts_sent is reported, never used to decide the verdict.
    """
    posts_sent = _posts_sent_of(record)
    try:
        reasons = _judge(record)
    except Exception as ex:  # a classifier bug must read as stop, never as a pass
        reasons = ["classifier-error: {}: {}".format(type(ex).__name__, ex)]
    return {
        "verdict": VERDICT_STOP if reasons else VERDICT_OK,
        "reasons": list(reasons),
        "posts_sent": posts_sent,
    }


# ----------------------------------------------------------------- operator

USAGE = (
    "usage: test_phase4_live_outcomes.py template | classify RECORD.json | "
    "run --wall-id N --parameter NAME --value TEXT --view-name VIEW --tag-id N "
    "--ifc-path PATH --out RECORD.json [--port N]"
)


MSG_NO_WRITE = ("No write step was sent: nothing was written to the model. Fix the condition "
                "named above and run again with a fresh --out.")
MSG_CONSUMED = "The one-shot gate is consumed: do not run this again."


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)


def _build_parser():
    parser = _Parser(prog="test_phase4_live_outcomes.py")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("template")
    classify = commands.add_parser("classify")
    classify.add_argument("record")
    run = commands.add_parser("run")
    run.add_argument("--wall-id", type=int, required=True)
    run.add_argument("--parameter", required=True)
    run.add_argument("--value", required=True)
    run.add_argument("--view-name", required=True)
    run.add_argument("--tag-id", type=int, required=True)
    run.add_argument("--ifc-path", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser


def _refusal(args):
    """Why the run may not start, or None. Decided before the bridge is touched."""
    out = args.out
    ifc = args.ifc_path
    if not (_is_int(args.wall_id) and args.wall_id > 0):
        return "--wall-id must be a positive element id"
    if not (_is_int(args.tag_id) and args.tag_id > 0 and args.tag_id != BAD_ID):
        return "--tag-id must be a positive element id other than {}".format(BAD_ID)
    for name in ("parameter", "value", "view_name"):
        if not _nonblank(getattr(args, name)):
            return "--{} must not be blank".format(name.replace("_", "-"))
    if not (_is_int(args.port) and 1 <= args.port <= 65535):
        return "--port must be between 1 and 65535"
    if not _nonblank(out):
        return "--out must not be blank"
    if not (os.path.isabs(ifc) and ifc.lower().endswith(".ifc")):
        return "--ifc-path must be an absolute path ending in .ifc ({})".format(ifc)
    if os.path.normcase(os.path.abspath(out)) == os.path.normcase(os.path.abspath(ifc)):
        return "--out and --ifc-path must be different files"
    if os.path.exists(out):
        return "{} already exists; a record is never overwritten (use a fresh --out)".format(out)
    if not _outside_repo(out):
        return "--out {} is inside the repository; a raw record stays outside it".format(out)
    if not _outside_repo(ifc):
        return "--ifc-path {} is inside the repository; an export stays outside it".format(ifc)
    if os.path.exists(ifc):
        return "--ifc-path {} already exists; the export goes to a new file".format(ifc)
    if not os.path.isdir(os.path.dirname(os.path.abspath(ifc))):
        return "the directory of --ifc-path does not exist ({})".format(ifc)
    if not os.path.isdir(os.path.dirname(os.path.abspath(out))):
        return "the directory of --out does not exist ({}); the record would be lost".format(out)
    return None


def _render(raw):
    """The text the model would read for a reply, from the reply object as the bridge returned it."""
    try:
        if REPO_ROOT not in sys.path:
            sys.path.insert(0, REPO_ROOT)
        from tools.utils import format_response

        return format_response(raw)
    except Exception as ex:
        return "(format_response failed: {}: {})".format(type(ex).__name__, ex)


def _describe_reply(reply):
    text = repr(reply)
    return text if len(text) <= 120 else text[:117] + "..."


async def _read(bridge, endpoint):
    """One allowed GET: (reply, None) or (None, exception text)."""
    try:
        _require_allowed(endpoint)
        return await bridge.revit_get(endpoint), None
    except Exception as ex:
        return None, "{}: {}".format(type(ex).__name__, ex)


async def _preflight(bridge, args, record):
    """Read-only checks before any write. Returns the stop reason, or None when all pass."""
    pre = record["preflight"]
    configured = getattr(bridge, "REVIT_PORT", None)
    if configured is not None and configured != args.port:
        return ("preflight.port: the bridge targets port {} but --port is {}; start the script with "
                "REVIT_PORT unset or equal to --port".format(configured, args.port))

    reply, problem = await _read(bridge, "/status/")
    pre["status_ok"] = bool(isinstance(reply, dict) and not reply.get("error"))
    if not pre["status_ok"]:
        return "preflight.status_ok: GET /status/ did not answer ({})".format(problem or _describe_reply(reply))

    try:
        snapshot = bridge.listener_snapshot([args.port])
    except Exception:
        snapshot = None
    owners = snapshot.get(args.port) if isinstance(snapshot, dict) else None
    if not (isinstance(owners, list) and all(_is_int(pid) and pid > 0 for pid in owners)):
        return "preflight.listeners: the OS listener inventory is unavailable for port {}".format(args.port)
    pre["listeners"] = list(owners)
    if len(owners) != 1:
        return "preflight.listeners: expected exactly one owner of port {}, got {}".format(args.port, owners)

    reply, problem = await _read(bridge, "/documents/")
    documents = reply.get("documents") if isinstance(reply, dict) else None
    if not isinstance(documents, list):
        return "preflight.documents: GET /documents/ gave no listing ({})".format(problem or _describe_reply(reply))
    pre["documents"] = len(documents)
    if len(documents) != 1:
        return "preflight.documents: expected exactly one open document, got {}".format(len(documents))

    reply, problem = await _read(bridge, "/element_properties/{}".format(args.wall_id))
    parameters = reply.get("parameters") if isinstance(reply, dict) else None
    if not isinstance(parameters, list):
        pre["parameter_writable"] = False
        return "preflight.parameter_writable: wall {} was not read ({})".format(
            args.wall_id, problem or _describe_reply(reply))
    found = [p for p in parameters if isinstance(p, dict) and p.get("name") == args.parameter]
    entry = found[0] if found else None
    pre["parameter_writable"] = bool(
        entry is not None and entry.get("read_only") is False and str(entry.get("storage_type")) == "String")
    if not pre["parameter_writable"]:
        return ("preflight.parameter_writable: wall {} has no writable text parameter named {!r} "
                "(found: {})".format(args.wall_id, args.parameter, _describe_reply(entry)))

    reply, problem = await _read(bridge, "/element_properties/{}".format(args.tag_id))
    pre["tag_element_found"] = bool(isinstance(reply, dict) and not reply.get("error")
                                    and reply.get("element_id") == args.tag_id)
    if not pre["tag_element_found"]:
        return "preflight.tag_element_found: element {} was not read ({})".format(
            args.tag_id, problem or _describe_reply(reply))
    return None


async def _post_step(bridge, record, key, endpoint, body):
    """Send one write exactly once. Returns a stop reason when the POST raised, else None."""
    _require_allowed(endpoint)
    step = {"endpoint": endpoint, "body": _plain(body), "raw": None, "rendered": None}
    record["steps"][key] = step
    record["posts_sent"] += 1  # counted before the call: a POST that raises or times out was sent
    try:
        raw = await bridge.revit_post(endpoint, body)
    except Exception as ex:
        step["exception"] = "{}: {}".format(type(ex).__name__, ex)
        return "{}: revit_post raised {}".format(key, step["exception"])
    step["rendered"] = _render(raw)
    step["raw"] = _plain(raw)
    return None


def _new_tag_ids(step, args):
    """The tag ids step 2 reports as created, never the wall, the tagged element or the bad id."""
    raw = step.get("raw") if isinstance(step, dict) else None
    ids = raw.get("tag_ids") if isinstance(raw, dict) else None
    keep = []
    for value in ids if isinstance(ids, list) else []:
        if (_is_int(value) and value > 0 and value not in (args.wall_id, args.tag_id, BAD_ID)
                and value not in keep):
            keep.append(value)
    return keep


async def _write_steps(bridge, args, record):
    """The five D-11 writes in order, once each. Returns a stop reason, or None when all were sent."""
    inputs = record["inputs"]
    tag_body = {"element_ids": [args.tag_id, BAD_ID], "add_leader": False,
                "orientation": "horizontal", "view_name": args.view_name}
    bad_body = dict(tag_body, element_ids=[BAD_ID])
    plan = (
        ("s1", "/modify_element/",
         {"element_id": args.wall_id, "parameters": {args.parameter: args.value}}),
        ("s2", "/tag_elements/", tag_body),
        ("s3", "/tag_elements/", bad_body),
        ("s4", "/export_ifc/",
         {"file_path": inputs["ifc_path"], "ifc_version": "IFC2x3", "export_base_quantities": True}),
    )
    for key, endpoint, body in plan:
        reason = await _post_step(bridge, record, key, endpoint, body)
        if key == "s4":
            record["steps"]["s4"]["file_exists"] = os.path.exists(inputs["ifc_path"])
        if reason:
            return reason
    ids = _new_tag_ids(record["steps"]["s2"], args)
    if not ids:
        message = "step 2 returned no new tag ids, so there is nothing of this run to delete"
        record["steps"]["s5"] = {"skipped": message}
        return "s5: skipped ({})".format(message)
    return await _post_step(bridge, record, "s5", "/delete_elements/", {"element_ids": ids})


async def _execute(args, record):
    bridge = _bridge()
    reason = await _preflight(bridge, args, record)
    if reason:
        return reason
    return await _write_steps(bridge, args, record)


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


def _report(record):
    """Print the verdict token, POSTS_SENT, the guidance and the reasons; return the exit code."""
    result = classify_outcomes(record)
    ok = result["verdict"] == VERDICT_OK
    posts = result["posts_sent"]
    print(SENTINEL_OK if ok else SENTINEL_STOP)
    print("POSTS_SENT={}".format(posts if posts is not None else "unknown"))
    if posts == 0:
        print(MSG_NO_WRITE)
    elif posts is not None and posts >= 1:
        print(MSG_CONSUMED)
    stop_reason = record.get("stop_reason") if isinstance(record, dict) else None
    if stop_reason:
        print("stop: {}".format(stop_reason))
    for reason in result["reasons"]:
        print("  - " + reason)
    return 0 if ok else 1


async def _run(args):
    global _BRIDGE_PORT
    refusal = _refusal(args)
    if refusal:
        print("refused: {}".format(refusal))
        return 2
    _BRIDGE_PORT = args.port
    record = evidence_template()
    record["inputs"].update({
        "wall_id": args.wall_id, "parameter": args.parameter, "value": args.value,
        "view_name": args.view_name, "tag_id": args.tag_id, "ifc_path": args.ifc_path,
        "port": args.port,
    })
    record["posts_sent"] = 0
    reason = None
    try:
        reason = await _execute(args, record)
    except Exception as ex:
        reason = "unexpected {}: {}".format(type(ex).__name__, ex)
    except BaseException as ex:
        reason = "interrupted ({})".format(type(ex).__name__)
        raise
    finally:
        record["stop_reason"] = reason
        record["recorded_at"] = _now()
        written = _save(args.out, record)
    code = _report(record)
    if written:
        print("record: {}".format(args.out))
    return code


def _cmd_classify(path):
    try:
        with open(path, "rb") as handle:
            record = json.loads(handle.read().decode("utf-8-sig"))
    except (OSError, ValueError) as ex:
        record = {"stop_reason": "cannot read the record {!r}: {}".format(path, ex)}
    return _report(record)


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
    if namespace.command == "run":
        return asyncio.run(_run(namespace))
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
