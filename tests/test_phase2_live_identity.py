# -*- coding: utf-8 -*-
"""Phase 2 production identity recheck (plan 02-02): operator procedure and classifier.

Older tier: a standalone script, run by hand by an engineer on a bench machine,
excluded from pytest (``testpaths = ["tests/unit"]``). It defines no ``test_*``
function and does nothing at import, so the unit suite can import the pure
classifier without side effects (tests/unit/test_phase2_live_identity.py).

What this is, and is not
------------------------
Plan 02-20 accepted the G1/G5 mechanisms from diagnostic captures. This procedure
rechecks the PRODUCTION 02-01 implementation (revit_mcp/identity.py, the status
route, bridge.listener_snapshot and the selected get_revit_status path) on a freshly
restarted Revit. It measures nothing by itself: it drives one stdio MCP server
process and records what the bridge returned. ``classify_identity_recheck`` turns
the record into STOP or ``recheck-observed``. ``recheck-observed`` means "complete
and self-consistent", never "approved": the engineer's choice at the plan's blocking
checkpoint is the decision, and every report prints ``approval=not-granted``.
An absent, partial, synthetic or contradictory record is STOP.

Every call this script asks for is ``get_revit_status`` (GET /status/), once without
a selector to bootstrap a candidate identity and then with the selector built from
that received identity. It never POSTs, never calls execute_code, never mutates a
model, never runs G6 and never creates a duplicate-listener condition. G2-production,
G3, G4, G5-production collision and G6 are carried as ``not_run`` slots; any slot that
claims anything but ``not-run`` makes the record STOP.

Commands
--------
    uv run python tests/test_phase2_live_identity.py template
    uv run python tests/test_phase2_live_identity.py first   --out RAW.json [--port 48884]
    uv run python tests/test_phase2_live_identity.py restart --in RAW.json [--out RAW2.json] [--port 48884]
    uv run python tests/test_phase2_live_identity.py classify RAW.json

Output tokens: PHASE2_IDENTITY_RECHECK_OBSERVED, PHASE2_IDENTITY_RECHECK_STOP,
PHASE2_IDENTITY_RECHECK_PENDING. Exit codes: 0 observed/ok, 1 stop, 2 usage error.

Procedure (engineer controls the bench; raw captures stay outside the repository)
---------------------------------------------------------------------------------
1. Fully close the Revit processes chosen for the recheck (never force-kill, never
   close user documents automatically). Start Revit WITHOUT a model so no workset
   dialog appears, then poll GET /status/ until it answers. Never use pyRevit
   Reload after an edit under ``revit_mcp/``: close and reopen Revit.
2. Check that exactly one listener holds the Routes port (netstat -ano -p tcp).
3. Run ``first --out RAW.json``. While no model is open the replies are the
   no-document HTTP 503 that must still carry process identity. The script
   bootstraps from the received identity, reconciles it with the full netstat
   inventory read only through bridge.listener_snapshot, builds the selector with
   make_selector (the exact inverse of bridge.parse_target) and sends two selected
   status requests through the one server process.
4. Fully close and reopen Revit a second time (same rules as step 1).
5. Run ``restart --in RAW.json``. It repeats the bootstrap and inventory, sends
   selected status requests to the new incarnation, retries the OLD selector (it must
   be refused with rediscovery guidance), classifies the combined record and prints
   the sentinel only when the classifier returns recheck-observed for a live record.
6. Attach the raw output of both runs and the RAW.json content, and record the
   observed/stop choice at the checkpoint.

The raw file holds PIDs, ports and session tokens of a local Revit; keep it machine
local. This script refuses an output path inside the repository.
"""
import asyncio
import base64
import contextlib
import datetime
import json
import os
import re
import sys
import uuid

PY = sys.executable
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(REPO_ROOT, "main.py")

STOP = "stop"
OBSERVED = "recheck-observed"
APPROVAL = "not-granted"
SCHEMA = "phase2-identity-recheck-v1"
STATUS_ROUTE = "/status/"
SENTINEL_OBSERVED = "PHASE2_IDENTITY_RECHECK_OBSERVED"
SENTINEL_STOP = "PHASE2_IDENTITY_RECHECK_STOP"
SENTINEL_PENDING = "PHASE2_IDENTITY_RECHECK_PENDING"
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 48884

R_NO_RECORD = "no-record"
R_NOT_LIVE = "not-live"
R_SYNTHETIC = "synthetic"
R_FIRST_PAIR = "same-incarnation-pair-missing"
R_RESTART_PAIR = "restart-pair-missing"
R_TOKEN_CHANGED = "token-changed-within-incarnation"
R_PID_CHANGED = "pid-changed-within-incarnation"
R_PORT_CHANGED = "port-changed-within-incarnation"
R_IDENTITY = "identity-incomplete"
R_NO_DOC = "no-document-reply-missing"
R_NO_DOC_IDENTITY = "no-document-identity-missing"
R_TOKEN_EQUAL = "token-equal-across-restart"
R_PID_EQUAL = "pid-equal-across-restart"
R_OWNER_ABSENT = "port-owner-absent"
R_OWNER_MISMATCH = "port-owner-different"
R_OWNER_MULTIPLE = "port-owner-multiple"
R_INVENTORY_UNAVAILABLE = "inventory-unavailable"
R_INVENTORY_MALFORMED = "inventory-malformed"
R_OLD_ACCEPTED = "old-selector-accepted"
R_OLD_NOT_RETRIED = "old-selector-not-retried"
R_NO_GUIDANCE = "old-selector-refusal-without-guidance"
R_ROUTE = "non-status-route-sent"
R_ROUTES_UNRECORDED = "sent-routes-unrecorded"
R_TIME = "timestamps-invalid"
R_NOT_RUN_CLAIMED = "not-run-slot-claimed"
R_CLASSIFIER_ERROR = "classifier-error"

REASON_CODES = (
    R_NO_RECORD, R_NOT_LIVE, R_SYNTHETIC, R_FIRST_PAIR, R_RESTART_PAIR,
    R_TOKEN_CHANGED, R_PID_CHANGED, R_PORT_CHANGED, R_IDENTITY, R_NO_DOC,
    R_NO_DOC_IDENTITY, R_TOKEN_EQUAL, R_PID_EQUAL, R_OWNER_ABSENT,
    R_OWNER_MISMATCH, R_OWNER_MULTIPLE, R_INVENTORY_UNAVAILABLE,
    R_INVENTORY_MALFORMED, R_OLD_ACCEPTED, R_OLD_NOT_RETRIED, R_NO_GUIDANCE,
    R_ROUTE, R_ROUTES_UNRECORDED, R_TIME, R_NOT_RUN_CLAIMED, R_CLASSIFIER_ERROR,
)

# Gates this procedure cannot measure. They can never yield a pass here.
NOT_RUN_SLOTS = ("g2_production", "g3", "g4", "g5_production_collision", "g6")
_NOT_RUN_REASONS = {
    "g2_production": "retained-reference document registry is 02-04; doubles are fixtures, not evidence",
    "g3": "inactive-document read safety is a later live gate",
    "g4": "production activation is a later live gate",
    "g5_production_collision": "duplicate-listener refusal through production code stays with 02-18",
    "g6": "write/read reproduction needs separate explicit user authorization",
}

_VERIFIED_RE = re.compile(
    r"^Verified Revit process: PID (\d+); Revit (.+?); port (\d+); "
    r"session ([0-9A-Fa-f-]{36})[ \t]*$",
    re.MULTILINE,
)
_IDENTITY_RE = re.compile(r"process[ _]identity['\"]?\s*:\s*(\{[^{}]*\})", re.IGNORECASE)


# ------------------------------------------------------------- primitives


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_port(value):
    return _is_int(value) and 1 <= value <= 65535


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _is_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _parse_time(value):
    """An aware ISO timestamp, else None (a naive time cannot be ordered)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _complete_identity(identity):
    return (
        isinstance(identity, dict)
        and _is_int(identity.get("pid"))
        and identity["pid"] > 0
        and _is_port(identity.get("actual_port"))
        and _is_uuid(identity.get("session_token"))
        and _nonblank(identity.get("revit_version"))
    )


def _reason(code, text):
    return "{}: {}".format(code, text)


def _never_raises(classify):
    def guarded(record):
        try:
            return classify(record)
        except Exception as ex:  # a classifier bug must read as STOP, not as a pass
            return STOP, [_reason(R_CLASSIFIER_ERROR, "{}: {}".format(type(ex).__name__, ex))]

    guarded.__name__ = classify.__name__
    guarded.__doc__ = classify.__doc__
    return guarded


# ----------------------------------------------------------- bridge access


def _bridge():
    """The production bridge module; imported lazily so the classifier stays light."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    import bridge

    return bridge


def route_namespace():
    """The Routes namespace as the bridge itself sends it, never hard-coded here."""
    tail = _bridge().BASE_URL.rstrip("/").rsplit("/", 1)[1]
    if not tail or ":" in tail:
        raise RuntimeError("bridge.BASE_URL carries no route namespace")
    return tail


def make_selector(host, port, pid, session_token):
    """The exact inverse of bridge.parse_target; it is not a validator."""
    payload = {"host": host, "port": port, "pid": pid, "session_token": session_token}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "revit1:" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def checked_selector(host, port, pid, session_token):
    """make_selector, accepted only if bridge.parse_target returns the same fields."""
    selector = make_selector(host, port, pid, session_token)
    parsed = _bridge().parse_target(selector)
    expected = {"host": host, "port": port, "pid": pid, "session_token": session_token}
    if parsed != expected:
        raise ValueError("selector does not round-trip through bridge.parse_target")
    return selector


def collect_listener_owners(port):
    """Listener PIDs for `port` from bridge.listener_snapshot only; None when unknown.

    No other subprocess, cmdlet or socket probe is used, and an unreadable,
    incomplete or malformed inventory is None, never an empty or single-owner pass.
    """
    owners = None
    try:
        snapshot = _bridge().listener_snapshot([port])
        value = snapshot.get(port) if isinstance(snapshot, dict) else None
        if (isinstance(value, list)
                and all(_is_int(p) and p > 0 for p in value)
                and len(set(value)) == len(value)):
            owners = list(value)
    except Exception:
        owners = None
    return {"port": port, "owners": owners, "source": "bridge.listener_snapshot", "at": _now()}


# ------------------------------------------------------------ reply parsing


def parse_status_text(text):
    """Kind and verified identity of one get_revit_status reply text.

    Only the verified-process line the status tool appends after formatting counts
    as identity. kind is active | no-document | error.
    """
    parsed = {"kind": "error", "identity": None}
    if not isinstance(text, str):
        return parsed
    matches = list(_VERIFIED_RE.finditer(text))
    if not matches:
        return parsed
    found = matches[-1]
    identity = {
        "pid": int(found.group(1)),
        "actual_port": int(found.group(3)),
        "session_token": found.group(4),
        "revit_version": found.group(2).strip(),
    }
    if not _complete_identity(identity):
        return parsed
    parsed["identity"] = identity
    if "Status: active" in text:
        parsed["kind"] = "active"
    elif "No active Revit document" in text:
        parsed["kind"] = "no-document"
    return parsed


def parse_bootstrap_identity(text):
    """process_identity from an untargeted read-only GET /status/ reply, or None.

    The legacy path returns a formatted dict on HTTP 200 and the raw JSON body text
    on the no-document 503; both carry the same four fields.
    """
    if not isinstance(text, str):
        return None
    found = _IDENTITY_RE.search(text)
    if not found:
        return None
    body = found.group(1)
    try:
        try:
            value = json.loads(body)
        except ValueError:
            import ast

            value = ast.literal_eval(body)
    except (ValueError, SyntaxError):
        return None
    if not _complete_identity(value):
        return None
    return {
        "pid": value["pid"],
        "actual_port": value["actual_port"],
        "session_token": value["session_token"],
        "revit_version": value["revit_version"],
    }


def describe_old_selector_retry(selector_token, text):
    """accepted is False only for an explicit refusal text with no verified identity."""
    accepted = None
    guidance = False
    if isinstance(text, str):
        if parse_status_text(text)["identity"] is not None:
            accepted = True
        elif text.startswith("Error:"):
            accepted = False
        guidance = "rediscover" in text.lower()
    return {
        "selector_token": selector_token,
        "accepted": accepted,
        "rediscovery_guidance": guidance,
        "text": text if isinstance(text, str) else None,
        "at": _now(),
    }


# --------------------------------------------------------------- classifier


def _check_incarnation(section, label, first, reasons):
    """Check one incarnation; returns (reference identity or None, timestamps)."""
    seen = set()

    def add(code, text):
        if (label, code) not in seen:
            seen.add((label, code))
            reasons.append(_reason(code, "{}: {}".format(label, text)))

    pair_code = R_FIRST_PAIR if first else R_RESTART_PAIR
    need = 2 if first else 1
    replies = section.get("replies") if isinstance(section, dict) else None
    if not isinstance(replies, list) or len(replies) < need:
        add(pair_code, "needs {} status repl{} carrying one token".format(need, "y" if need == 1 else "ies"))
        return None, []

    times = []
    reference = None
    for index, item in enumerate(replies):
        identity = item.get("identity") if isinstance(item, dict) else None
        stamp = _parse_time(item.get("at") if isinstance(item, dict) else None)
        if stamp is None:
            add(R_TIME, "reply {} has no aware ISO timestamp".format(index))
        else:
            times.append(stamp)
        if not _complete_identity(identity):
            add(R_IDENTITY, "reply {} lacks a complete identity".format(index))
            continue
        if reference is None:
            reference = identity
            continue
        if identity["session_token"] != reference["session_token"]:
            add(R_TOKEN_CHANGED, "token differs between replies of one incarnation")
        if identity["pid"] != reference["pid"]:
            add(R_PID_CHANGED, "PID differs between replies of one incarnation")
        if identity["actual_port"] != reference["actual_port"]:
            add(R_PORT_CHANGED, "actual_port differs between replies of one incarnation")

    if first:
        no_doc = section.get("no_document_reply")
        if not isinstance(no_doc, dict) or no_doc.get("kind") != "no-document":
            add(R_NO_DOC, "no no-document HTTP 503 reply was recorded")
        else:
            stamp = _parse_time(no_doc.get("at"))
            if stamp is None:
                add(R_TIME, "no-document reply has no aware ISO timestamp")
            else:
                times.append(stamp)
            identity = no_doc.get("identity")
            if not _complete_identity(identity):
                add(R_NO_DOC_IDENTITY, "the no-document reply carries no complete identity")
            elif reference is not None:
                if identity["session_token"] != reference["session_token"]:
                    add(R_TOKEN_CHANGED, "no-document reply token differs from the incarnation token")
                if identity["pid"] != reference["pid"]:
                    add(R_PID_CHANGED, "no-document reply PID differs from the incarnation PID")
                if identity["actual_port"] != reference["actual_port"]:
                    add(R_PORT_CHANGED, "no-document reply actual_port differs from the incarnation port")

    listener = section.get("listener")
    if not isinstance(listener, dict) or listener.get("owners") is None:
        add(R_INVENTORY_UNAVAILABLE, "no usable listener inventory was recorded")
    else:
        owners = listener.get("owners")
        shaped = (
            isinstance(owners, list)
            and all(_is_int(p) and p > 0 for p in owners)
            and len(set(owners)) == len(owners)
            and _is_port(listener.get("port"))
            and (reference is None or listener["port"] == reference["actual_port"])
        )
        if not shaped:
            add(R_INVENTORY_MALFORMED, "listener inventory is malformed or names another port")
        elif not owners:
            add(R_OWNER_ABSENT, "no listener holds the reported actual_port")
        elif len(owners) > 1:
            add(R_OWNER_MULTIPLE, "several PIDs {} hold the reported actual_port".format(sorted(owners)))
        elif reference is not None and owners != [reference["pid"]]:
            add(R_OWNER_MISMATCH, "port owner {} is not the reported PID {}".format(owners, reference["pid"]))
    return reference, times


def _check_routes(record, reasons):
    routes = record.get("sent_routes")
    if not isinstance(routes, list) or not routes:
        reasons.append(_reason(R_ROUTES_UNRECORDED, "no sent-route list was recorded"))
        return
    for item in routes:
        if not (isinstance(item, dict) and item.get("method") == "GET" and item.get("route") == STATUS_ROUTE):
            reasons.append(_reason(R_ROUTE, "only GET /status/ may be sent, got {!r}".format(item)))
            return


def _check_old_selector(record, first_reference, reasons):
    retry = record.get("old_selector_retry")
    if not isinstance(retry, dict):
        reasons.append(_reason(R_OLD_NOT_RETRIED, "the old selector was never retried after the restart"))
        return
    token = retry.get("selector_token")
    if not _is_uuid(token) or (first_reference is not None and token != first_reference["session_token"]):
        reasons.append(_reason(R_OLD_NOT_RETRIED, "the retried selector is not the first incarnation's"))
        return
    text = retry.get("text")
    if _parse_time(retry.get("at")) is None:
        reasons.append(_reason(R_TIME, "old selector retry has no aware ISO timestamp"))
    if retry.get("accepted") is not False or (
            isinstance(text, str) and _VERIFIED_RE.search(text)):
        reasons.append(_reason(R_OLD_ACCEPTED, "the old selector was accepted or its outcome is unknown"))
    elif not (isinstance(text, str) and "rediscover" in text.lower()):
        reasons.append(_reason(R_NO_GUIDANCE, "the refusal did not tell the caller to rediscover targets"))


def _check_not_run(record, reasons):
    slots = record.get("not_run")
    if not isinstance(slots, dict):
        reasons.append(_reason(R_NOT_RUN_CLAIMED, "not_run section is missing"))
        return
    for name in NOT_RUN_SLOTS:
        slot = slots.get(name)
        if not (isinstance(slot, dict) and slot.get("status") == "not-run"):
            reasons.append(_reason(R_NOT_RUN_CLAIMED, "slot {} is missing or not 'not-run'".format(name)))
    for name, slot in slots.items():
        if name not in NOT_RUN_SLOTS and not (isinstance(slot, dict) and slot.get("status") == "not-run"):
            reasons.append(_reason(R_NOT_RUN_CLAIMED, "slot {} claims more than 'not-run'".format(name)))


@_never_raises
def classify_identity_recheck(record):
    """STOP or recheck-observed for a combined first + restart record; never an approval."""
    if not isinstance(record, dict) or not record:
        return STOP, [_reason(R_NO_RECORD, "no evidence record (missing, empty or not an object)")]
    reasons = []
    if record.get("live") is not True:
        reasons.append(_reason(R_NOT_LIVE, "record is not marked live: an offline record never passes"))
    if record.get("synthetic") is not False:
        reasons.append(_reason(R_SYNTHETIC, "record is not explicitly non-synthetic"))
    _check_routes(record, reasons)

    first, first_times = _check_incarnation(record.get("incarnation_1"), "incarnation_1", True, reasons)
    second, second_times = _check_incarnation(record.get("incarnation_2"), "incarnation_2", False, reasons)
    if first is not None and second is not None:
        if first["session_token"] == second["session_token"]:
            reasons.append(_reason(R_TOKEN_EQUAL, "the token did not change across the full restart"))
        if first["pid"] == second["pid"]:
            reasons.append(_reason(R_PID_EQUAL, "the PID did not change across the full restart"))
    if first_times and second_times and min(second_times) <= max(first_times):
        reasons.append(_reason(R_TIME, "the restart observations are not after the first incarnation's"))

    _check_old_selector(record, first, reasons)
    _check_not_run(record, reasons)
    return (STOP, reasons) if reasons else (OBSERVED, [])


# ---------------------------------------------------------------- template


def evidence_template():
    """The record to fill; every live value starts null, which classifies as STOP."""
    return {
        "schema": SCHEMA,
        "live": None,
        "synthetic": None,
        "recorded_at": None,
        "route_namespace": None,
        "sent_routes": [],
        "incarnation_1": {
            "selector": None,
            "bootstrap": None,
            "replies": [],
            "no_document_reply": None,
            "listener": None,
        },
        "incarnation_2": {
            "selector": None,
            "bootstrap": None,
            "replies": [],
            "listener": None,
        },
        "old_selector_retry": None,
        "not_run": dict(
            (name, {"status": "not-run", "reason": _NOT_RUN_REASONS[name]}) for name in NOT_RUN_SLOTS
        ),
    }


# ----------------------------------------------------------------- operator


def _route_entry(via):
    return {"method": "GET", "route": STATUS_ROUTE, "via": via, "at": _now()}


@contextlib.asynccontextmanager
async def _server(port):
    """One stdio MCP server process whose legacy target is the given Routes port."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=PY,
        args=[MAIN],
        env={"REVIT_HOST": LOOPBACK_HOST, "REVIT_PORT": str(port), "PYTHONUTF8": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _status_text(session, selector):
    arguments = {} if selector is None else {"target": selector}
    result = await session.call_tool("get_revit_status", arguments)
    return "\n".join(getattr(item, "text", "") for item in result.content)


async def _observe(port, old_selector=None, old_token=None, calls=2):
    """One incarnation through one server process. Returns (section, sent_routes, problem)."""
    sent = []
    section = {"selector": None, "bootstrap": None, "replies": [], "listener": None}
    async with _server(port) as session:
        text = await _status_text(session, None)
        sent.append(_route_entry("get_revit_status:bootstrap-without-selector"))
        identity = parse_bootstrap_identity(text)
        section["bootstrap"] = {"identity": identity, "at": _now(), "text": text}
        if identity is None:
            return section, sent, "bootstrap reply carried no complete process_identity"
        listener = collect_listener_owners(identity["actual_port"])
        section["listener"] = listener
        if listener["owners"] != [identity["pid"]]:
            return section, sent, (
                "listener inventory {} does not show the reported PID {} as sole owner of port {}; "
                "no selector is built".format(listener["owners"], identity["pid"], identity["actual_port"]))
        selector = checked_selector(
            LOOPBACK_HOST, identity["actual_port"], identity["pid"], identity["session_token"])
        section["selector"] = selector
        for _ in range(calls):
            reply_text = await _status_text(session, selector)
            sent.append(_route_entry("get_revit_status:selected"))
            parsed = parse_status_text(reply_text)
            section["replies"].append(
                {"at": _now(), "kind": parsed["kind"], "identity": parsed["identity"], "text": reply_text})
        retry = None
        if old_selector is not None:
            retry_text = await _status_text(session, old_selector)
            sent.append(_route_entry("get_revit_status:old-selector"))
            retry = describe_old_selector_retry(old_token, retry_text)
    section["old_selector_retry"] = retry
    return section, sent, None


def _outside_repo(path):
    real = os.path.normcase(os.path.realpath(path))
    root = os.path.normcase(os.path.realpath(REPO_ROOT))
    try:
        return os.path.commonpath([real, root]) != root
    except ValueError:  # different drives
        return True


def _write_record(path, record):
    with open(path, "wb") as handle:
        handle.write(json.dumps(record, indent=2).encode("utf-8"))


def _read_record(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8-sig"))


def _stop(text):
    print("{} approval={}: {}".format(SENTINEL_STOP, APPROVAL, text))
    return 1


def _summary_lines(record):
    lines = []
    try:
        for label in ("incarnation_1", "incarnation_2"):
            section = record.get(label) or {}
            replies = section.get("replies") or []
            identity = next((r.get("identity") for r in replies if isinstance(r, dict) and r.get("identity")), None)
            listener = section.get("listener") or {}
            lines.append("IDENTITY {} identity={} replies={} owners={}".format(
                label, json.dumps(identity, sort_keys=True),
                [r.get("kind") for r in replies if isinstance(r, dict)], listener.get("owners")))
        retry = record.get("old_selector_retry")
        if isinstance(retry, dict):
            lines.append("OLD_SELECTOR accepted={} guidance={}".format(
                retry.get("accepted"), retry.get("rediscovery_guidance")))
        for name in NOT_RUN_SLOTS:
            lines.append("NOT_RUN {}: {}".format(name, _NOT_RUN_REASONS[name]))
    except Exception:
        pass
    return lines


def report(record):
    """Print the classification of a record; the sentinel only for an observed live record."""
    verdict, reasons = classify_identity_recheck(record)
    for line in _summary_lines(record):
        print(line)
    print("verdict={}".format(verdict))
    for reason in reasons:
        print("  - " + reason)
    if verdict == OBSERVED and isinstance(record, dict) and record.get("live") is True:
        print("{} approval={}".format(SENTINEL_OBSERVED, APPROVAL))
        return 0
    print("{} approval={}".format(SENTINEL_STOP, APPROVAL))
    return 1


def _options(args, names):
    """Parse --name value pairs; None on any unknown, repeated or valueless option."""
    values = {}
    index = 0
    while index < len(args):
        name = args[index]
        if name not in names or name in values or index + 1 >= len(args):
            return None
        values[name] = args[index + 1]
        index += 2
    return values


USAGE = (
    "usage: test_phase2_live_identity.py template | classify RAW.json | "
    "first --out RAW.json [--port N] | restart --in RAW.json [--out RAW2.json] [--port N]"
)


def _port_option(values):
    try:
        port = int(values.get("--port", str(DEFAULT_PORT)))
    except ValueError:
        return None
    return port if _is_port(port) else None


def _cmd_first(args):
    values = _options(args, ("--out", "--port"))
    if values is None or "--out" not in values or _port_option(values) is None:
        print(USAGE)
        return 2
    out = values["--out"]
    if not _outside_repo(out):
        print("refused: raw captures must stay outside the repository ({})".format(out))
        return 2
    if os.path.exists(out):
        print("refused: {} already exists; raw captures are never overwritten".format(out))
        return 2
    port = _port_option(values)
    try:
        section, sent, problem = asyncio.run(_observe(port))
    except Exception as ex:
        return _stop("live capture failed ({}: {})".format(type(ex).__name__, ex))
    if problem:
        return _stop(problem)
    replies = section["replies"]
    section["no_document_reply"] = next((r for r in replies if r["kind"] == "no-document"), None)
    record = evidence_template()
    record.update({
        "live": True,
        "synthetic": False,
        "recorded_at": _now(),
        "route_namespace": route_namespace(),
        "sent_routes": sent,
        "incarnation_1": section,
    })
    section.pop("old_selector_retry", None)
    _write_record(out, record)
    for line in _summary_lines(record):
        print(line)
    kinds = [r["kind"] for r in replies]
    if section["no_document_reply"] is None:
        print("note: no no-document reply was captured ({}); start Revit without a model for this run".format(kinds))
    print("{} approval={}: first incarnation captured in {}; now fully close and reopen Revit "
          "(never pyRevit Reload), then run: restart --in {}".format(SENTINEL_PENDING, APPROVAL, out, out))
    return 0


def _cmd_restart(args):
    values = _options(args, ("--in", "--out", "--port"))
    if values is None or "--in" not in values or _port_option(values) is None:
        print(USAGE)
        return 2
    source = values["--in"]
    out = values.get("--out", source)
    if not _outside_repo(source) or not _outside_repo(out):
        print("refused: raw captures must stay outside the repository")
        return 2
    try:
        record = _read_record(source)
        first = record["incarnation_1"]
        old_selector = first["selector"]
        old_token = first["replies"][0]["identity"]["session_token"]
        if not isinstance(old_selector, str) or not old_selector:
            raise ValueError("no selector recorded for the first incarnation")
    except (OSError, ValueError, KeyError, IndexError, TypeError) as ex:
        return _stop("cannot use the first capture {!r}: {}".format(source, ex))
    port = _port_option(values)
    try:
        section, sent, problem = asyncio.run(_observe(port, old_selector, old_token))
    except Exception as ex:
        return _stop("live capture failed ({}: {})".format(type(ex).__name__, ex))
    retry = section.pop("old_selector_retry", None)
    record["incarnation_2"] = section
    record["old_selector_retry"] = retry
    record["sent_routes"] = list(record.get("sent_routes") or []) + sent
    record["recorded_at"] = _now()
    _write_record(out, record)
    if problem:
        print("note: " + problem)
    return report(record)


def _cmd_classify(path):
    try:
        record = _read_record(path)
    except (OSError, ValueError) as ex:
        return _stop("cannot read evidence file {!r}: {}".format(path, ex))
    return report(record)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(USAGE)
        return _stop("no command given and no evidence recorded")
    command, rest = args[0], args[1:]
    if command == "template" and not rest:
        print(json.dumps(evidence_template(), indent=2))
        return 0
    if command == "classify" and len(rest) == 1:
        return _cmd_classify(rest[0])
    if command == "first":
        return _cmd_first(rest)
    if command == "restart":
        return _cmd_restart(rest)
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
