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

G3 / G4 production observations (plan 02-07)
--------------------------------------------
A second record, schema ``phase2-g34-production-v1``, rechecks the PRODUCTION
/document_summary/, /document_levels/ and /activate_document/ routes (02-05, 02-06).
It is captured one command at a time on a Revit that was FULLY closed and reopened
after those edits (never pyRevit Reload), with at least two saved, non-workshared
documents open (A active, B inactive) and, for the refusal cases, a never-saved
document, a detached/non-file document and, if the bench has one, a saved workshared
one. It calls only get_revit_status, list_documents, read_document_summary,
read_document_levels and activate_document through one stdio MCP server process per
command, always with the selector built from the identity recorded by g34-start.

    g34-template                                  print the empty record
    g34-start    --out RAW.json                   bootstrap identity + first listing
    g3-read      --in RAW.json --slot S --target N   read inactive document N (summary + levels)
    g4-case      --in RAW.json --case C --target N   ONE activation request for document N
    g34-observe  --in RAW.json --step X --ui ...  the engineer's own observation
    g34-classify RAW.json                         classify both gates

``--target N`` is the 1-based number printed by g34-start / the listing; a read or
case is refused (nothing sent) if document N is the active one. g3-read never sends
an activation request. g4-case sends exactly one and never retries. Neither writes
the engineer fields: only g34-observe does, from words the engineer types after
looking at the Revit window (and at any dialog), and an unset field is STOP.
``classify_g3_production`` and ``classify_g4_production`` return STOP, not-run or
an *-observed verdict, never an approval; g34-classify prints
PHASE2_G3_PRODUCTION_OBSERVED / PHASE2_G4_PRODUCTION_OBSERVED only for an observed
live record (and PHASE2_G4_PRODUCTION_NOT_RUN when a required case was never run).
Nothing here saves, syncs, reopens, opens a file, substitutes a path, calls
execute_code or runs G6.
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

# ---- plan 02-07: G3/G4 production observations (the g34-* commands) ----------
G34_SCHEMA = "phase2-g34-production-v1"
G3_OBSERVED = "g3-production-observed"
G4_OBSERVED = "g4-production-observed"
NOT_RUN = "not-run"
SENTINEL_G3_OBSERVED = "PHASE2_G3_PRODUCTION_OBSERVED"
SENTINEL_G3_STOP = "PHASE2_G3_PRODUCTION_STOP"
SENTINEL_G4_OBSERVED = "PHASE2_G4_PRODUCTION_OBSERVED"
SENTINEL_G4_STOP = "PHASE2_G4_PRODUCTION_STOP"
SENTINEL_G4_NOT_RUN = "PHASE2_G4_PRODUCTION_NOT_RUN"
SENTINEL_G34_PENDING = "PHASE2_G34_PENDING"
SENTINEL_G34_STOP = "PHASE2_G34_STOP"

G3_SLOTS = ("a_active_b_read", "b_active_a_read")
G4_CASES = ("allow", "unsaved", "detached_or_non_file", "saved_workshared")
# The classes the user's policy names as refusals plus the one allow class. A saved
# workshared model is exercised only as a refusal and only if the bench has one.
G4_REQUIRED = ("allow", "unsaved", "detached_or_non_file")
G4_REFUSAL_REASONS = {
    "unsaved": ("unsaved",),
    "detached_or_non_file": ("detached", "no-usable-file-path"),
    "saved_workshared": ("workshared-unmeasured",),
}
G3_UI = ("unchanged", "changed")
G4_UI = ("unchanged", "target-active", "other-active")
DIALOG_WORDS = {"none": False, "input-required": True}
DATA_WORDS = {"matches": True, "mismatch": False}
# The only tools this procedure may call, and the single Routes request each one sends.
TOOL_ROUTES = {
    "get_revit_status": ("GET", "/status/"),
    "list_documents": ("GET", "/documents/"),
    "read_document_summary": ("POST", "/document_summary/"),
    "read_document_levels": ("POST", "/document_levels/"),
    "activate_document": ("POST", "/activate_document/"),
}
ALLOWED_ROUTES = frozenset(TOOL_ROUTES.values())
ACTIVATE_ROUTE = TOOL_ROUTES["activate_document"]
G34_NOT_RUN_SLOTS = ("g6",)
_G34_NOT_RUN_REASONS = {"g6": "write/read reproduction needs separate explicit user authorization"}

R_SCHEMA = "schema-mismatch"
R_PROCESS_IDENTITY = "process-identity-incomplete"
R_PROCESS_OWNER = "process-owner-unverified"
R_ROUTE_NOT_ALLOWED = "route-not-allowed"
R_CALLS_UNRECORDED = "sent-calls-unrecorded"
R_DIRECTION_MISSING = "direction-missing"
R_DIRECTION_NOT_REVERSED = "direction-not-reversed"
R_UNKNOWN_SLOT = "unknown-slot"
R_INDISTINGUISHABLE = "documents-indistinguishable"
R_LISTING = "listing-unusable"
R_ACTIVE_CHANGED = "active-document-changed"
R_UI_SWITCHED = "ui-switched"
R_UI_UNKNOWN = "ui-switch-unknown"
R_TARGET_ACTIVE = "target-is-active"
R_TARGET_NOT_LISTED = "target-not-listed"
R_READ_NOT_OK = "read-not-ok"
R_WRONG_DOCUMENT = "wrong-document"
R_DATA_NOT_TARGET = "data-not-from-target"
R_SUMMARY_INCOMPLETE = "summary-incomplete"
R_LEVELS_INCOMPLETE = "levels-incomplete"
R_COUNTS = "counts-inconsistent"
R_IDENTITY_MISMATCH = "identity-mismatch"
R_ACTIVATION_IN_READ = "activation-in-read"
R_ENGINEER_UI_MISSING = "engineer-ui-unobserved"
R_ENGINEER_UI_CHANGED = "engineer-ui-changed"
R_ENGINEER_UI_UNEXPECTED = "engineer-ui-unexpected"
R_ENGINEER_DATA_MISSING = "engineer-data-unconfirmed"
R_ENGINEER_DATA_MISMATCH = "engineer-data-mismatch"
R_DIALOG_MISSING = "dialog-observation-missing"
R_DIALOG_INPUT = "dialog-required-input"
R_ALLOW_NOT_ACTIVATED = "allow-not-activated"
R_ALLOW_ALREADY_ACTIVE = "allow-target-already-active"
R_ALLOW_NO_PATH = "allow-without-path"
R_NOT_ACTIVE_AFTER = "target-not-active-after"
R_OBSERVED_ACTIVE = "observed-active-mismatch"
R_REFUSAL_ACTIVATED = "refusal-activated"
R_REFUSAL_MISSING = "refusal-missing"
R_REFUSAL_REASON = "refusal-reason-mismatch"
R_WORKSHARED_ALLOW = "workshared-activation-attempt"
R_ACTIVATION_RETRIED = "activation-retried"
R_ACTIVATION_UNRECORDED = "activation-call-unrecorded"
R_ACTIVATION_OUTSIDE = "activation-outside-case"
R_UNKNOWN_CASE = "unknown-case"
R_CASE_MALFORMED = "case-malformed"
R_NOT_RUN_WITH_DATA = "not-run-slot-with-data"
R_CASE_NOT_RUN = "case-not-run"

G34_REASON_CODES = (
    R_NO_RECORD, R_NOT_LIVE, R_SYNTHETIC, R_SCHEMA, R_PROCESS_IDENTITY, R_PROCESS_OWNER,
    R_ROUTE_NOT_ALLOWED, R_CALLS_UNRECORDED, R_NOT_RUN_CLAIMED, R_CLASSIFIER_ERROR,
    R_DIRECTION_MISSING, R_DIRECTION_NOT_REVERSED, R_UNKNOWN_SLOT, R_INDISTINGUISHABLE,
    R_LISTING, R_ACTIVE_CHANGED, R_UI_SWITCHED, R_UI_UNKNOWN, R_TARGET_ACTIVE,
    R_TARGET_NOT_LISTED, R_READ_NOT_OK, R_WRONG_DOCUMENT, R_DATA_NOT_TARGET,
    R_SUMMARY_INCOMPLETE, R_LEVELS_INCOMPLETE, R_COUNTS, R_IDENTITY_MISMATCH,
    R_ACTIVATION_IN_READ, R_ENGINEER_UI_MISSING, R_ENGINEER_UI_CHANGED,
    R_ENGINEER_UI_UNEXPECTED, R_ENGINEER_DATA_MISSING, R_ENGINEER_DATA_MISMATCH,
    R_DIALOG_MISSING, R_DIALOG_INPUT, R_ALLOW_NOT_ACTIVATED, R_ALLOW_ALREADY_ACTIVE,
    R_ALLOW_NO_PATH, R_NOT_ACTIVE_AFTER, R_OBSERVED_ACTIVE, R_REFUSAL_ACTIVATED,
    R_REFUSAL_MISSING, R_REFUSAL_REASON, R_WORKSHARED_ALLOW, R_ACTIVATION_RETRIED,
    R_ACTIVATION_UNRECORDED, R_ACTIVATION_OUTSIDE, R_UNKNOWN_CASE, R_CASE_MALFORMED,
    R_NOT_RUN_WITH_DATA, R_CASE_NOT_RUN,
)

# Gates this procedure cannot measure. They can never yield a pass here.
NOT_RUN_SLOTS = ("g2_production", "g3", "g4", "g5_production_collision", "g6")
_NOT_RUN_REASONS = {
    "g2_production": "retained-reference document registry is 02-04; doubles are fixtures, not evidence",
    "g3": "inactive-document read safety is recorded by the separate g34 production record (plan 02-07), never by this one",
    "g4": "production activation is recorded by the separate g34 production record (plan 02-07), never by this one",
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


# ==================================================== plan 02-07: G3 / G4 production
#
# What the records below are: one engineer-controlled bench session, captured one
# command at a time, then classified. The capture commands call only the five tools
# in TOOL_ROUTES through one stdio MCP server process each, always with the selector
# built from the verified identity of the Revit process recorded by g34-start. They
# never save, sync, reopen, open a file, substitute a path, call execute_code or run
# G6. The engineer fields (UI observation, dialog observation, data comparison) are
# written ONLY by g34-observe from the engineer's own command-line words; a capture
# command, a callback or a policy acceptance never fills them.


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _token(word):
    """The selector a diagnostic line printed; the word 'none' means no active document."""
    return None if word in (None, "none") else word


def _int_or_none(word):
    try:
        return int(word)
    except (TypeError, ValueError):
        return None


def _float_or_none(word):
    try:
        return float(word)
    except (TypeError, ValueError):
        return None


def _is_count(value):
    return _is_int(value) and value >= 0


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ------------------------------------------------------- parsing tool reply text

_ANSWERING_RE = re.compile(
    r"^Answering Revit process: PID (\d+); Revit (.+?); port (\d+); "
    r"session ([0-9A-Fa-f-]{36})[ \t]*$",
    re.MULTILINE,
)
_ERROR_RE = re.compile(r"^Error: (\d{3}) - (.*)$", re.DOTALL)
_LISTING_HEAD_RE = re.compile(r"^Open documents in this Revit process: (\d+)[ \t]*$")
_LISTING_NONE = "No documents are open in this Revit process."
_ACTIVE_FLAG = "  [ACTIVE]"
_SUMMARY_HEAD_RE = re.compile(r"^Summary of document (\S+): (.*)$", re.MULTILINE)
_LEVELS_HEAD_RE = re.compile(r"^Levels of document (\S+): (.*)$", re.MULTILINE)
_LEVEL_LINE_RE = re.compile(
    r"^(\d+)\. (.*): elevation (\S+) mm \((\S+) ft\), id (\S+)[ \t]*$", re.MULTILINE)
_UNCHANGED_RE = re.compile(
    r"^Active document before and after this read: (\S+) \(unchanged\)\.", re.MULTILINE)
_SWITCHED_RE = re.compile(
    r"^WARNING: the active document changed while this read ran \(before: (\S+); after: ([^)]*)\)\.",
    re.MULTILINE)
_UNKNOWN_RE = re.compile(
    r"^Whether the active document changed during this read is unknown \(.*\); "
    r"before: (\S+); after: (\S+)\.[ \t]*$", re.MULTILINE)
_ACTIVATION_RE = re.compile(
    r"^(Activated|Already the active document, no activation call was made): "
    r"(.*) \(document (\S+); path: (.*)\)[ \t]*$", re.MULTILINE)
_OBSERVED_ACTIVE_RE = re.compile(
    r"^Active document now \(re-read from Revit\): (.*) \(document (\S+); path: (.*)\)[ \t]*$",
    re.MULTILINE)
_NEVER_SAVED = "(never saved)"


def _answering_identity(text):
    found = list(_ANSWERING_RE.finditer(text))
    if not found:
        return None
    last = found[-1]
    identity = {
        "pid": int(last.group(1)),
        "actual_port": int(last.group(3)),
        "session_token": last.group(4),
        "revit_version": last.group(2).strip(),
    }
    return identity if _complete_identity(identity) else None


def _error_fields(text):
    """kind, http_status, error_code, reason, document, observed, identity of an Error: reply."""
    fields = {"kind": "error", "http_status": None, "error_code": None, "reason": None,
              "document": None, "observed_active_document": None, "identity": None}
    if not isinstance(text, str):
        return fields
    found = _ERROR_RE.match(text)
    if not found:
        return fields
    status = int(found.group(1))
    try:
        body = json.loads(found.group(2))
    except ValueError:
        body = None
    fields["http_status"] = status
    if not isinstance(body, dict):
        return fields
    fields["error_code"] = body.get("error_code") if isinstance(body.get("error_code"), str) else None
    fields["reason"] = body.get("reason") if isinstance(body.get("reason"), str) else None
    document = body.get("document")
    if isinstance(document, dict) and isinstance(document.get("document"), str):
        fields["document"] = document["document"]
    observed = body.get("observed_active_document")
    if isinstance(observed, dict) and isinstance(observed.get("document"), str):
        fields["observed_active_document"] = observed["document"]
    identity = body.get("process_identity")
    if _complete_identity(identity):
        fields["identity"] = {k: identity[k] for k in ("pid", "actual_port", "session_token", "revit_version")}
    if 400 <= status < 500:
        fields["kind"] = "refused"
    return fields


def parse_listing_text(text):
    """The documents of one list_documents reply, or ok False for anything else.

    ok is True only for a reply that has its header, as many entries as the header
    counts and a path and a document selector for each; a refusal, a transport error
    or a partly readable listing is never a short list.
    """
    parsed = {"ok": False, "documents": [], "active_document": None, "active_count": 0, "identity": None}
    if not isinstance(text, str):
        return parsed
    lines = text.splitlines()
    declared = None
    for line in lines:
        if line.startswith(_LISTING_NONE):
            declared = 0
            break
        head = _LISTING_HEAD_RE.match(line)
        if head:
            declared = int(head.group(1))
            break
    if declared is None:
        return parsed
    documents = []
    current = None
    for line in lines:
        entry = re.match(r"^(\d+)\. (.*)$", line)
        if entry:
            title = entry.group(2)
            active = title.endswith(_ACTIVE_FLAG)
            if active:
                title = title[: -len(_ACTIVE_FLAG)]
            current = {"title": title, "active": active, "path": None, "document": None}
            documents.append(current)
        elif current is not None and line.startswith("   path: "):
            path = line[len("   path: "):]
            current["path"] = "" if path == _NEVER_SAVED else path
        elif current is not None and line.startswith("   document: "):
            current["document"] = line[len("   document: "):].strip()
    if (len(documents) != declared
            or any(d["path"] is None or not d["document"] for d in documents)
            or len(set(d["document"] for d in documents)) != len(documents)):
        return parsed
    active = [d for d in documents if d["active"]]
    parsed.update({
        "ok": True,
        "documents": documents,
        "active_count": len(active),
        "active_document": active[0]["document"] if len(active) == 1 else None,
        "identity": _answering_identity(text),
    })
    return parsed


def _empty_read():
    return {"kind": "error", "http_status": None, "error_code": None, "reason": None,
            "document": None, "title": None, "path": None, "non_type_element_count": None,
            "level_count": None, "total_levels": None, "skipped_levels": None, "levels": None,
            "target_is_active": None, "ui_switched": None, "active_before": None,
            "active_after": None, "active_token": None, "identity": None}


def _diagnostic(text, parsed):
    """The active-document diagnostic sentence of an addressed read, as an observation."""
    found = _UNCHANGED_RE.search(text)
    if found:
        token = _token(found.group(1))
        parsed.update(ui_switched=False, active_before=token, active_after=token, active_token=token)
        return
    found = _SWITCHED_RE.search(text)
    if found:
        parsed.update(ui_switched=True, active_before=_token(found.group(1)),
                      active_after=_token(found.group(2).strip()))
        return
    found = _UNKNOWN_RE.search(text)
    if found:
        parsed.update(ui_switched=None, active_before=_token(found.group(1)),
                      active_after=_token(found.group(2)))


def _target_line(text):
    found = re.search(r"^Target is the active document: (yes|no)[ \t]*$", text, re.MULTILINE)
    return None if not found else found.group(1) == "yes"


def _refused_read(text):
    parsed = _empty_read()
    fields = _error_fields(text)
    for key in ("kind", "http_status", "error_code", "reason", "identity"):
        parsed[key] = fields[key]
    return parsed


def parse_summary_text(text):
    """Fields of one read_document_summary reply; kind ok | refused | error. Never raises."""
    if not isinstance(text, str):
        return _empty_read()
    head = _SUMMARY_HEAD_RE.search(text)
    if not head:
        return _refused_read(text)
    parsed = _empty_read()
    parsed.update(kind="ok", document=head.group(1), title=head.group(2))
    path = re.search(r"^path: (.*)$", text, re.MULTILINE)
    if path:
        parsed["path"] = "" if path.group(1).rstrip() == _NEVER_SAVED else path.group(1).rstrip("\r")
    count = re.search(r"^non-type element count: (\S+)[ \t]*$", text, re.MULTILINE)
    parsed["non_type_element_count"] = _int_or_none(count.group(1)) if count else None
    levels = re.search(r"^level count: (\S+)[ \t]*$", text, re.MULTILINE)
    parsed["level_count"] = _int_or_none(levels.group(1)) if levels else None
    parsed["target_is_active"] = _target_line(text)
    _diagnostic(text, parsed)
    parsed["identity"] = _answering_identity(text)
    return parsed


def parse_levels_text(text):
    """Fields of one read_document_levels reply; kind ok | refused | error. Never raises."""
    if not isinstance(text, str):
        return _empty_read()
    head = _LEVELS_HEAD_RE.search(text)
    if not head:
        return _refused_read(text)
    parsed = _empty_read()
    parsed.update(kind="ok", document=head.group(1), title=head.group(2))
    total = re.search(r"^Levels: (\S+)[ \t]*$", text, re.MULTILINE)
    parsed["total_levels"] = _int_or_none(total.group(1)) if total else None
    parsed["levels"] = [
        {"name": m.group(2), "elevation_mm": _float_or_none(m.group(3)),
         "elevation_feet": _float_or_none(m.group(4)), "id": _int_or_none(m.group(5))}
        for m in _LEVEL_LINE_RE.finditer(text)]
    skipped = re.search(r"^Skipped (\d+) unreadable level\(s\)", text, re.MULTILINE)
    parsed["skipped_levels"] = int(skipped.group(1)) if skipped else 0
    parsed["target_is_active"] = _target_line(text)
    _diagnostic(text, parsed)
    parsed["identity"] = _answering_identity(text)
    return parsed


def parse_activation_text(text):
    """Fields of one activate_document reply; kind success | refused | error. Never raises."""
    parsed = {"kind": "error", "http_status": None, "activation": None, "reason": None,
              "error_code": None, "document": None, "observed_active_document": None,
              "identity": None}
    if not isinstance(text, str):
        return parsed
    found = _ACTIVATION_RE.search(text)
    if found:
        parsed.update(kind="success", http_status=200, document=found.group(3),
                      activation="activated" if found.group(1) == "Activated" else "already-active",
                      identity=_answering_identity(text))
        observed = _OBSERVED_ACTIVE_RE.search(text)
        if observed:
            parsed["observed_active_document"] = observed.group(2)
        return parsed
    fields = _error_fields(text)
    for key in ("kind", "http_status", "error_code", "reason", "document",
                "observed_active_document", "identity"):
        parsed[key] = fields[key]
    return parsed


# --------------------------------------------------------------- record builders


def sent_call_entry(tool, step, at=None):
    """One sent-call record; only the five tools this procedure may use have one."""
    if not isinstance(tool, str) or tool not in TOOL_ROUTES:
        raise ValueError("{!r} is not a tool this procedure may call".format(tool))
    method, route = TOOL_ROUTES[tool]
    return {"method": method, "route": route, "tool": tool, "step": step, "at": at or _now()}


def build_listing_entry(text, at=None):
    entry = parse_listing_text(text)
    entry.update({"at": at or _now(), "text": text if isinstance(text, str) else None})
    return entry


def build_read_entry(tool, text, at=None):
    if tool == "read_document_summary":
        entry = parse_summary_text(text)
    elif tool == "read_document_levels":
        entry = parse_levels_text(text)
    else:
        raise ValueError("{!r} is not an addressed read".format(tool))
    entry.update({"at": at or _now(), "text": text if isinstance(text, str) else None})
    return entry


def build_activation_entry(text, at=None):
    entry = parse_activation_text(text)
    entry.update({"at": at or _now(), "text": text if isinstance(text, str) else None})
    return entry


def empty_engineer():
    """The engineer's fields, unset. Nothing but apply_observation ever sets them."""
    return {"ui": None, "dialog_required_input": None, "data_matches_addressed": None,
            "at": None, "source": None}


def build_g3_slot(step, target, before, summary, levels, after):
    return {"step": step, "target_document": target, "before_listing": before,
            "summary": summary, "levels": levels, "after_listing": after,
            "engineer": empty_engineer()}


def build_g4_case(case, target, before, reply, after):
    return {"step": "g4:" + case, "case": case, "expect": "allow" if case == "allow" else "refuse",
            "target_document": target, "before_listing": before, "reply": reply,
            "after_listing": after, "engineer": empty_engineer()}


def g34_template():
    """The record to fill; every live value starts null or not-run, which classifies as STOP."""
    return {
        "schema": G34_SCHEMA,
        "live": None,
        "synthetic": None,
        "recorded_at": None,
        "route_namespace": None,
        "process": None,
        "listing_0": None,
        "sent_calls": [],
        "g3": {"slots": dict((name, None) for name in G3_SLOTS)},
        "g4": {"cases": dict(
            (name, {"status": "not-run", "reason": "not exercised yet"}) for name in G4_CASES)},
        "not_run": dict(
            (name, {"status": "not-run", "reason": _G34_NOT_RUN_REASONS[name]}) for name in G34_NOT_RUN_SLOTS),
    }


def apply_observation(record, step, ui, dialog, data):
    """Write the engineer's own observation onto a captured step; (ok, message).

    This is the only writer of the engineer fields. ``dialog`` and ``data`` are the
    engineer's words (see DIALOG_WORDS, DATA_WORDS) or None; they are never defaulted.
    """
    kind, _, name = step.partition(":") if isinstance(step, str) else ("", "", "")
    if kind == "g3" and name in G3_SLOTS:
        target = _dict(_dict(_dict(record.get("g3")).get("slots")).get(name))
        captured = "summary" in target
    elif kind == "g4" and name in G4_CASES:
        target = _dict(_dict(_dict(record.get("g4")).get("cases")).get(name))
        captured = "reply" in target
    else:
        return False, "unknown step {!r}".format(step)
    if not captured:
        return False, "step {} has not been captured in this record; run its capture command first".format(step)
    previous = target.get("engineer")
    if isinstance(previous, dict) and previous.get("ui") is not None:
        target.setdefault("engineer_superseded", []).append(previous)
    target["engineer"] = {
        "ui": ui,
        "dialog_required_input": DIALOG_WORDS[dialog] if dialog is not None else None,
        "data_matches_addressed": DATA_WORDS[data] if data is not None else None,
        "at": _now(),
        "source": "engineer-command-line",
    }
    return True, "recorded"


# ------------------------------------------------------------------- classifiers


class _Reasons(object):
    """Reason list with one entry per (scope, code), in the order first seen."""

    def __init__(self):
        self.items = []
        self._seen = set()

    def add(self, code, text, scope=None):
        if (scope, code) not in self._seen:
            self._seen.add((scope, code))
            self.items.append(_reason(code, text))


def _check_calls(record, reasons):
    calls = record.get("sent_calls")
    if not isinstance(calls, list) or not calls:
        reasons.add(R_CALLS_UNRECORDED, "no sent-call list was recorded")
        return
    for item in calls:
        method = item.get("method") if isinstance(item, dict) else None
        route = item.get("route") if isinstance(item, dict) else None
        if not (isinstance(method, str) and isinstance(route, str) and (method, route) in ALLOWED_ROUTES):
            reasons.add(R_ROUTE_NOT_ALLOWED, "only the five document/status requests may be sent, got {!r}".format(item),
                        scope=repr(item))


def _check_not_run_g34(record, reasons):
    slots = record.get("not_run")
    if not isinstance(slots, dict):
        reasons.add(R_NOT_RUN_CLAIMED, "not_run section is missing")
        return
    for name in G34_NOT_RUN_SLOTS:
        slot = slots.get(name)
        if not (isinstance(slot, dict) and slot.get("status") == "not-run"):
            reasons.add(R_NOT_RUN_CLAIMED, "slot {} is missing or not 'not-run'".format(name), scope=name)
    for name, slot in slots.items():
        if name not in G34_NOT_RUN_SLOTS and not (isinstance(slot, dict) and slot.get("status") == "not-run"):
            reasons.add(R_NOT_RUN_CLAIMED, "slot {} claims more than 'not-run'".format(name), scope=name)


def _check_header(record, reasons):
    """Checks shared by both gates; returns the recorded process identity or None."""
    if record.get("live") is not True:
        reasons.add(R_NOT_LIVE, "record is not marked live: an offline record never passes")
    if record.get("synthetic") is not False:
        reasons.add(R_SYNTHETIC, "record is not explicitly non-synthetic")
    if record.get("schema") != G34_SCHEMA:
        reasons.add(R_SCHEMA, "record schema is not {}".format(G34_SCHEMA))
    process = _dict(record.get("process"))
    identity = process.get("identity")
    if not _complete_identity(identity):
        reasons.add(R_PROCESS_IDENTITY, "the recorded process carries no complete identity")
        identity = None
    listener = _dict(process.get("listener"))
    owners = listener.get("owners")
    sole = (identity is not None and isinstance(owners, list) and owners == [identity["pid"]]
            and all(_is_int(p) for p in owners) and listener.get("port") == identity["actual_port"])
    if not sole:
        reasons.add(R_PROCESS_OWNER, "the listener inventory does not show the recorded PID as sole owner of its port")
    _check_calls(record, reasons)
    _check_not_run_g34(record, reasons)
    return identity


def _usable_listing(entry):
    return (isinstance(entry, dict) and entry.get("ok") is True
            and isinstance(entry.get("documents"), list)
            and all(isinstance(d, dict) for d in entry["documents"])
            and _is_int(entry.get("active_count")) and entry["active_count"] == 1
            and isinstance(entry.get("active_document"), str) and bool(entry["active_document"]))


def _find_document(listing, selector):
    if not _usable_listing(listing) or not isinstance(selector, str):
        return None
    for item in listing["documents"]:
        if item.get("document") == selector:
            return item
    return None


def _same_process(entry, identity):
    return identity is None or (isinstance(entry, dict) and entry.get("identity") == identity)


def _valid_level(level):
    return (isinstance(level, dict) and isinstance(level.get("name"), str)
            and _is_number(level.get("elevation_mm")) and _is_int(level.get("id")))


def _check_g3_read(add, label, entry, target, descriptor, active, summary):
    """Checks common to the summary and the levels read of one slot; the entry, or None if unusable.

    The summary carries a path as well as a title; the levels reply carries a title only.
    """
    if not isinstance(entry, dict) or entry.get("kind") != "ok":
        add(R_READ_NOT_OK, "{} read did not return data (kind {!r})".format(
            label, entry.get("kind") if isinstance(entry, dict) else None))
        return None
    if entry.get("document") != target:
        add(R_WRONG_DOCUMENT, "{} read names {!r}, not the addressed {!r}".format(
            label, entry.get("document"), target))
    if descriptor is not None:
        belongs = entry.get("title") == descriptor.get("title")
        if summary:
            belongs = belongs and entry.get("path") == descriptor.get("path")
        if not belongs:
            add(R_DATA_NOT_TARGET,
                "{} read title/path are not those the listing gives the addressed document".format(label))
    if entry.get("target_is_active") is not False:
        add(R_TARGET_ACTIVE, "{} read does not report the addressed document as inactive".format(label))
    switched = entry.get("ui_switched")
    if switched is True:
        add(R_UI_SWITCHED, "{} read reports the active document changed during the read".format(label))
    elif switched is not False:
        add(R_UI_UNKNOWN, "{} read does not establish whether the active document changed".format(label))
    elif active is not None and entry.get("active_token") != active:
        add(R_ACTIVE_CHANGED, "{} read saw active document {!r}, not {!r}".format(
            label, entry.get("active_token"), active))
    return entry


def _g3_slot(name, slot, identity, reasons):
    label = "g3 slot {}".format(name)

    def add(code, text):
        reasons.add(code, "{}: {}".format(label, text), scope=label)

    info = {"active": None, "target": slot.get("target_document"), "active_descriptor": None,
            "target_descriptor": None}
    before, after = slot.get("before_listing"), slot.get("after_listing")
    before_ok, after_ok = _usable_listing(before), _usable_listing(after)
    if not before_ok:
        add(R_LISTING, "the listing before the reads is missing or unusable")
    if not after_ok:
        add(R_LISTING, "the listing after the reads is missing or unusable")
    target = info["target"]
    active = None
    descriptor = None
    if before_ok:
        active = before["active_document"]
        info["active"] = active
        info["active_descriptor"] = _find_document(before, active)
        descriptor = _find_document(before, target)
        info["target_descriptor"] = descriptor
        if descriptor is None:
            add(R_TARGET_NOT_LISTED, "the addressed document is not in the listing taken before the reads")
        if target == active:
            add(R_TARGET_ACTIVE, "the addressed document is the active document, so this is not an inactive read")
    if before_ok and after_ok and after["active_document"] != active:
        add(R_ACTIVE_CHANGED, "the active document was {!r} before the reads and {!r} after".format(
            active, after["active_document"]))
    for key, entry in (("before listing", before), ("after listing", after),
                       ("summary", slot.get("summary")), ("levels", slot.get("levels"))):
        if not _same_process(entry, identity):
            add(R_IDENTITY_MISMATCH, "the {} was not answered by the recorded Revit process".format(key))

    summary = _check_g3_read(add, "summary", slot.get("summary"), target, descriptor, active, True)
    levels = _check_g3_read(add, "levels", slot.get("levels"), target, descriptor, active, False)
    if summary is not None:
        if not (_is_count(summary.get("non_type_element_count")) and _is_count(summary.get("level_count"))):
            add(R_SUMMARY_INCOMPLETE, "summary lacks a non-type element count or a level count")
    if levels is not None:
        listed = levels.get("levels")
        shaped = (_is_count(levels.get("total_levels")) and _is_count(levels.get("skipped_levels"))
                  and isinstance(listed, list) and len(listed) == levels.get("total_levels")
                  and all(_valid_level(item) for item in listed))
        if not shaped:
            add(R_LEVELS_INCOMPLETE, "levels reply is not a well-formed level list")
        elif summary is not None and _is_count(summary.get("level_count")) and (
                summary["level_count"] != levels["total_levels"] + levels["skipped_levels"]):
            add(R_COUNTS, "summary level_count {} differs from levels total {} + skipped {}".format(
                summary["level_count"], levels["total_levels"], levels["skipped_levels"]))

    engineer = _dict(slot.get("engineer"))
    ui = engineer.get("ui")
    if ui == "unchanged":
        pass
    elif ui == "changed":
        add(R_ENGINEER_UI_CHANGED, "the engineer reports the Revit window changed during the reads")
    else:
        add(R_ENGINEER_UI_MISSING, "the engineer has not recorded an observation of the Revit window")
    data = engineer.get("data_matches_addressed")
    if data is False:
        add(R_ENGINEER_DATA_MISMATCH, "the engineer reports the returned data is not the addressed document's")
    elif data is not True:
        add(R_ENGINEER_DATA_MISSING, "the engineer has not confirmed the data belongs to the addressed document")
    dialog = engineer.get("dialog_required_input")
    if dialog is not None and dialog is not False:
        add(R_DIALOG_INPUT, "a dialog requiring input is reported during the reads")
    return info


@_never_raises
def classify_g3_production(record):
    """STOP or g3-production-observed for the A/B + B/A addressed-read record; never an approval."""
    if not isinstance(record, dict) or not record:
        return STOP, [_reason(R_NO_RECORD, "no evidence record (missing, empty or not an object)")]
    reasons = _Reasons()
    identity = _check_header(record, reasons)
    slots = _dict(_dict(record.get("g3")).get("slots"))
    for name in slots:
        if name not in G3_SLOTS:
            reasons.add(R_UNKNOWN_SLOT, "slot {!r} is not a defined direction".format(name), scope=repr(name))
    infos = {}
    for name in G3_SLOTS:
        slot = slots.get(name)
        if not isinstance(slot, dict):
            reasons.add(R_DIRECTION_MISSING, "direction {} was not captured".format(name), scope=name)
            continue
        infos[name] = _g3_slot(name, slot, identity, reasons)
    first, second = infos.get(G3_SLOTS[0]), infos.get(G3_SLOTS[1])
    if first and second and first["active"] and second["active"]:
        reversed_ok = (first["active"] == second["target"] and first["target"] == second["active"]
                       and first["active"] != first["target"])
        if not reversed_ok:
            reasons.add(R_DIRECTION_NOT_REVERSED,
                        "the two directions do not read each other's document while the other is active")
        a, b = first["active_descriptor"], first["target_descriptor"]
        if a and b and (a.get("title"), a.get("path")) == (b.get("title"), b.get("path")):
            reasons.add(R_INDISTINGUISHABLE,
                        "the two documents share title and path, so a read cannot show whose data it returned")
    for item in _list(record.get("sent_calls")):
        if (isinstance(item, dict) and (item.get("method"), item.get("route")) == ACTIVATE_ROUTE
                and isinstance(item.get("step"), str) and item["step"].startswith("g3:")):
            reasons.add(R_ACTIVATION_IN_READ, "an activation request was sent during {}".format(item["step"]),
                        scope=item["step"])
    return (STOP, reasons.items) if reasons.items else (G3_OBSERVED, [])


def _activation_counts(record):
    counts = {}
    for item in _list(record.get("sent_calls")):
        if isinstance(item, dict) and (item.get("method"), item.get("route")) == ACTIVATE_ROUTE:
            step = item.get("step") if isinstance(item.get("step"), str) else None
            counts[step] = counts.get(step, 0) + 1
    return counts


_CASE_DATA_KEYS = ("before_listing", "reply", "after_listing", "engineer", "target_document")


def _g4_case(name, slot, identity, counts):
    """(state, [(code, text)]) for one case; state is observed | stop | not-run."""
    problems = []

    def add(code, text):
        problems.append((code, "g4 case {}: {}".format(name, text)))

    if slot is None:
        return "not-run", []
    if not isinstance(slot, dict):
        add(R_CASE_MALFORMED, "the case slot is not an object")
        return "stop", problems
    if slot.get("status") == "not-run":
        if any(key in slot for key in _CASE_DATA_KEYS):
            add(R_NOT_RUN_WITH_DATA, "a slot marked not-run carries capture data")
            return "stop", problems
        return "not-run", []

    step = "g4:" + name
    if slot.get("case") != name or slot.get("step") != step:
        add(R_CASE_MALFORMED, "the slot does not name itself as case {}".format(name))
    expected_expect = "allow" if name == "allow" else "refuse"
    if slot.get("expect") != expected_expect:
        if name == "saved_workshared" and slot.get("expect") == "allow":
            add(R_WORKSHARED_ALLOW, "saved-workshared activation was set up as an allow case")
        else:
            add(R_CASE_MALFORMED, "the case expectation is not {!r}".format(expected_expect))

    before, after = slot.get("before_listing"), slot.get("after_listing")
    before_ok, after_ok = _usable_listing(before), _usable_listing(after)
    if not before_ok:
        add(R_LISTING, "the listing before the activation request is missing or unusable")
    if not after_ok:
        add(R_LISTING, "the listing after the activation request is missing or unusable")
    target = slot.get("target_document")
    active_before = before["active_document"] if before_ok else None
    active_after = after["active_document"] if after_ok else None
    descriptor = _find_document(before, target) if before_ok else None
    if before_ok and descriptor is None:
        add(R_TARGET_NOT_LISTED, "the target document is not in the listing taken before the request")
    reply = slot.get("reply")
    reply_ok = isinstance(reply, dict)
    for key, entry in (("before listing", before), ("after listing", after), ("reply", reply)):
        if not _same_process(entry, identity):
            add(R_IDENTITY_MISMATCH, "the {} was not answered by the recorded Revit process".format(key))

    sent = counts.get(step, 0)
    if sent == 0:
        add(R_ACTIVATION_UNRECORDED, "no activation request is recorded for this case")
    elif sent > 1:
        add(R_ACTIVATION_RETRIED, "{} activation requests are recorded; a case is sent once, never retried".format(sent))

    if name == "allow":
        if before_ok and target == active_before:
            add(R_ALLOW_ALREADY_ACTIVE, "the target was already the active document, so the call changed nothing")
        if descriptor is not None and not descriptor.get("path"):
            add(R_ALLOW_NO_PATH, "the target has no saved path in the listing")
        if not (reply_ok and reply.get("kind") == "success" and reply.get("activation") == "activated"):
            add(R_ALLOW_NOT_ACTIVATED, "the explicit call did not report an activation")
        elif reply.get("document") != target or reply.get("observed_active_document") != target:
            add(R_OBSERVED_ACTIVE, "the reply does not name the target as the re-read active document")
        if after_ok and active_after != target:
            add(R_NOT_ACTIVE_AFTER, "the listing after the call shows {!r} active, not the target".format(active_after))
        expected_ui = "target-active"
    else:
        activated = reply_ok and (reply.get("activation") is not None or reply.get("kind") == "success")
        if activated:
            add(R_REFUSAL_ACTIVATED, "the request was answered as an activation instead of a refusal")
            if name == "saved_workshared":
                add(R_WORKSHARED_ALLOW, "a saved-workshared document was activated")
        elif not (reply_ok and reply.get("kind") == "refused" and reply.get("http_status") == 422):
            add(R_REFUSAL_MISSING, "no HTTP 422 named refusal was recorded")
        else:
            reason = reply.get("reason")
            if not (isinstance(reason, str) and reason in G4_REFUSAL_REASONS[name]):
                add(R_REFUSAL_REASON, "refusal reason {!r} is not one of {}".format(reason, G4_REFUSAL_REASONS[name]))
            if reply.get("document") != target or (before_ok and reply.get("observed_active_document") != active_before):
                add(R_OBSERVED_ACTIVE, "the refusal does not name the target and the unchanged active document")
        if before_ok and after_ok and active_after != active_before:
            add(R_ACTIVE_CHANGED, "the active document was {!r} before the request and {!r} after".format(
                active_before, active_after))
        expected_ui = "unchanged"

    engineer = _dict(slot.get("engineer"))
    ui = engineer.get("ui")
    if ui == expected_ui:
        pass
    elif ui in G4_UI:
        add(R_ENGINEER_UI_UNEXPECTED, "the engineer saw {!r}, expected {!r}".format(ui, expected_ui))
    else:
        add(R_ENGINEER_UI_MISSING, "the engineer has not recorded an observation of the Revit window")
    dialog = engineer.get("dialog_required_input")
    if dialog is True:
        add(R_DIALOG_INPUT, "the engineer reports a dialog requiring input appeared")
    elif dialog is not False:
        add(R_DIALOG_MISSING, "the engineer has not recorded whether a dialog requiring input appeared")
    return ("stop" if problems else "observed"), problems


def _g4_cases(record):
    return _dict(_dict(record.get("g4")).get("cases"))


def _g4_evaluate(record, identity):
    cases = _g4_cases(record)
    counts = _activation_counts(record)
    outcomes, problems = {}, []
    for name in G4_CASES:
        state, found = _g4_case(name, cases.get(name), identity, counts)
        outcomes[name] = state
        problems.extend(found)
    return outcomes, problems, counts


def g4_case_outcomes(record):
    """observed | stop | not-run for each G4 case on its own, without the shared header checks."""
    try:
        header = _dict(_dict(record).get("process")).get("identity") if isinstance(record, dict) else None
        outcomes, _problems, _counts = _g4_evaluate(_dict(record), header if _complete_identity(header) else None)
        return outcomes
    except Exception:
        return dict((name, "stop") for name in G4_CASES)


@_never_raises
def classify_g4_production(record):
    """STOP, not-run or g4-production-observed for the activation record; never an approval."""
    if not isinstance(record, dict) or not record:
        return STOP, [_reason(R_NO_RECORD, "no evidence record (missing, empty or not an object)")]
    reasons = _Reasons()
    identity = _check_header(record, reasons)
    cases = _g4_cases(record)
    for name in cases:
        if name not in G4_CASES:
            reasons.add(R_UNKNOWN_CASE, "case {!r} is not a defined activation case".format(name), scope=repr(name))
    outcomes, problems, counts = _g4_evaluate(record, identity)
    for code, text in problems:
        reasons.add(code, text, scope=text)
    exercised = set("g4:" + name for name in G4_CASES if outcomes[name] != "not-run")
    for step in counts:
        if step not in exercised:
            reasons.add(R_ACTIVATION_OUTSIDE, "an activation request was sent outside any exercised case (step {!r})".format(step),
                        scope=repr(step))
    if reasons.items:
        return STOP, reasons.items
    missing = [name for name in G4_REQUIRED if outcomes[name] == "not-run"]
    if missing:
        return NOT_RUN, [_reason(R_CASE_NOT_RUN, "{} was not exercised on this bench; absent is never a pass".format(name))
                         for name in missing]
    return G4_OBSERVED, []


# ------------------------------------------------------------------ live capture


class _BenchProblem(Exception):
    """A reason to stop before anything is written; the message is for the engineer."""


class _Bound(object):
    """One MCP server process bound to ONE verified Revit incarnation."""

    def __init__(self, session):
        self.session = session
        self.sent = []
        self.identity = None
        self.listener = None
        self.selector = None

    async def call(self, tool, arguments, step):
        entry = sent_call_entry(tool, step)
        self.sent.append(entry)  # recorded before the request: a lost reply is still a sent request
        payload = dict(arguments)
        payload["target"] = self.selector
        result = await self.session.call_tool(tool, payload)
        return "\n".join(getattr(item, "text", "") for item in result.content)

    async def listing(self, step):
        return build_listing_entry(await self.call("list_documents", {}, step))


@contextlib.asynccontextmanager
async def _bound(port, expected_identity=None):
    """Bootstrap one incarnation: identity, sole port owner, selector; yields a _Bound.

    With ``expected_identity`` the answering process must be exactly that one: a
    restarted Revit, another PID or another session token is a stop, never a capture
    mixed into the record.
    """
    async with _server(port) as session:
        bound = _Bound(session)
        bound.sent.append(sent_call_entry("get_revit_status", "bootstrap"))
        text = await _status_text(session, None)
        identity = parse_bootstrap_identity(text)
        if identity is None:
            raise _BenchProblem("bootstrap reply carried no complete process_identity (is Revit up with Routes enabled?)")
        if expected_identity is not None and identity != expected_identity:
            raise _BenchProblem(
                "process identity changed since g34-start (recorded PID {} session {}, now PID {} session {}); "
                "Revit was restarted or another instance answered. Nothing was captured; start a new capture "
                "after a full restart.".format(
                    expected_identity.get("pid"), expected_identity.get("session_token"),
                    identity["pid"], identity["session_token"]))
        listener = collect_listener_owners(identity["actual_port"])
        if listener["owners"] != [identity["pid"]]:
            raise _BenchProblem(
                "listener inventory {} does not show the reported PID {} as sole owner of port {}; "
                "no selector is built".format(listener["owners"], identity["pid"], identity["actual_port"]))
        bound.identity = identity
        bound.listener = listener
        bound.selector = checked_selector(
            LOOPBACK_HOST, identity["actual_port"], identity["pid"], identity["session_token"])
        yield bound


def _g34_stop(text):
    print("{} approval={}: {}".format(SENTINEL_G34_STOP, APPROVAL, text))
    return 1


def _g34_pending(text):
    print("{} approval={}: {}".format(SENTINEL_G34_PENDING, APPROVAL, text))
    return 0


def _print_listing(listing):
    for index, item in enumerate(listing.get("documents") or [], 1):
        print("  {}. {}{} | path: {} | document: {}".format(
            index, "[ACTIVE] " if item.get("active") else "", item.get("title"),
            item.get("path") or "(never saved)", item.get("document")))


def _positive_int(word):
    try:
        value = int(word)
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None


def _load_for_update(path):
    """(record, None) or (None, message) for an existing capture file."""
    try:
        record = _read_record(path)
    except (OSError, ValueError) as ex:
        return None, "cannot read the capture {!r}: {}".format(path, ex)
    if not (isinstance(record, dict) and record.get("schema") == G34_SCHEMA
            and _complete_identity(_dict(record.get("process")).get("identity"))
            and isinstance(record.get("sent_calls"), list)):
        return None, "{!r} is not a g34 capture started by g34-start".format(path)
    return record, None


G34_USAGE = (
    "g34 commands: g34-template | "
    "g34-start --out RAW.json [--port N] | "
    "g3-read --in RAW.json --slot a_active_b_read|b_active_a_read --target N [--port N] | "
    "g4-case --in RAW.json --case allow|unsaved|detached_or_non_file|saved_workshared --target N [--port N] | "
    "g34-observe --in RAW.json --step g3:SLOT|g4:CASE --ui WORD [--dialog none|input-required] "
    "[--data matches|mismatch] | g34-classify RAW.json"
)


def _cmd_g34_start(args):
    values = _options(args, ("--out", "--port"))
    if values is None or "--out" not in values or _port_option(values) is None:
        print(G34_USAGE)
        return 2
    out = values["--out"]
    if not _outside_repo(out):
        print("refused: raw captures must stay outside the repository ({})".format(out))
        return 2
    if os.path.exists(out):
        print("refused: {} already exists; raw captures are never overwritten".format(out))
        return 2
    port = _port_option(values)

    async def capture():
        async with _bound(port) as bound:
            listing = await bound.listing("start")
            return bound.identity, bound.selector, bound.listener, bound.sent, listing

    try:
        identity, selector, listener, sent, listing = asyncio.run(capture())
    except _BenchProblem as ex:
        return _g34_stop(str(ex))
    except Exception as ex:
        return _g34_stop("live capture failed ({}: {})".format(type(ex).__name__, ex))
    if not listing["ok"]:
        return _g34_stop("list_documents returned no usable listing: {}".format(listing.get("text")))
    record = g34_template()
    record.update({
        "live": True,
        "synthetic": False,
        "recorded_at": _now(),
        "route_namespace": route_namespace(),
        "process": {"identity": identity, "selector": selector, "listener": listener, "at": _now()},
        "listing_0": listing,
        "sent_calls": sent,
    })
    _write_record(out, record)
    print("PROCESS pid={} port={} session={} revit={}".format(
        identity["pid"], identity["actual_port"], identity["session_token"], identity["revit_version"]))
    print("OPEN DOCUMENTS (use these numbers with --target; the active one is marked):")
    _print_listing(listing)
    return _g34_pending("capture started in {}; next: g3-read with the active document A open and B inactive".format(out))


def _read_options(args, names, required):
    values = _options(args, names)
    if values is None or any(name not in values for name in required) or _port_option(values) is None:
        return None
    return values


def _cmd_g3_read(args):
    values = _read_options(args, ("--in", "--slot", "--target", "--port"), ("--in", "--slot", "--target"))
    if (values is None or values["--slot"] not in G3_SLOTS or _positive_int(values["--target"]) is None):
        print(G34_USAGE)
        return 2
    path, slot_name, number, port = values["--in"], values["--slot"], _positive_int(values["--target"]), _port_option(values)
    if not _outside_repo(path):
        print("refused: raw captures must stay outside the repository")
        return 2
    record, problem = _load_for_update(path)
    if problem:
        return _g34_stop(problem)
    if isinstance(_dict(_dict(record.get("g3")).get("slots")).get(slot_name), dict):
        print("refused: slot {} is already captured in {}; captures are never overwritten "
              "(start a new capture to repeat it)".format(slot_name, path))
        return 2
    step = "g3:" + slot_name

    async def capture():
        async with _bound(port, record["process"]["identity"]) as bound:
            before = await bound.listing(step)
            if not before["ok"] or before["active_count"] != 1:
                raise _BenchProblem("the listing is unusable or has no single active document; nothing was read")
            if number > len(before["documents"]):
                raise _BenchProblem("--target {} is beyond the {} open documents; nothing was read".format(
                    number, len(before["documents"])))
            target = before["documents"][number - 1]
            if target["document"] == before["active_document"]:
                raise _BenchProblem(
                    "--target {} is the ACTIVE document; an inactive document must be addressed. Nothing was read.".format(number))
            summary = build_read_entry(
                "read_document_summary",
                await bound.call("read_document_summary", {"document": target["document"]}, step))
            levels = build_read_entry(
                "read_document_levels",
                await bound.call("read_document_levels", {"document": target["document"]}, step))
            after = await bound.listing(step)
            return build_g3_slot(step, target["document"], before, summary, levels, after), bound.sent

    try:
        slot, sent = asyncio.run(capture())
    except _BenchProblem as ex:
        return _g34_stop(str(ex))
    except Exception as ex:
        return _g34_stop("live capture failed ({}: {})".format(type(ex).__name__, ex))
    record["g3"]["slots"][slot_name] = slot
    record["sent_calls"] = list(record["sent_calls"]) + sent
    record["recorded_at"] = _now()
    _write_record(path, record)
    summary, levels = slot["summary"], slot["levels"]
    print("G3 {} active={} target={} ({})".format(
        slot_name, slot["before_listing"]["active_document"], slot["target_document"], summary.get("title")))
    print("  summary: kind={} path={!r} non_type_elements={} levels={} target_is_active={} ui_switched={}".format(
        summary["kind"], summary.get("path"), summary.get("non_type_element_count"),
        summary.get("level_count"), summary.get("target_is_active"), summary.get("ui_switched")))
    print("  levels: kind={} total={} skipped={} {}".format(
        levels["kind"], levels.get("total_levels"), levels.get("skipped_levels"),
        [(lv["name"], lv["elevation_mm"]) for lv in _list(levels.get("levels"))]))
    print("  active after the reads: {}".format(slot["after_listing"].get("active_document")))
    print("OPEN DOCUMENTS now (numbers for the next --target):")
    _print_listing(slot["after_listing"])
    return _g34_pending(
        "now LOOK at the Revit window, then record what you saw with g34-observe --in {} --step {} "
        "(--ui takes the word unchanged or changed; --data takes the word matches or mismatch)".format(path, step))


def _cmd_g4_case(args):
    values = _read_options(args, ("--in", "--case", "--target", "--port"), ("--in", "--case", "--target"))
    if (values is None or values["--case"] not in G4_CASES or _positive_int(values["--target"]) is None):
        print(G34_USAGE)
        return 2
    path, case, number, port = values["--in"], values["--case"], _positive_int(values["--target"]), _port_option(values)
    if not _outside_repo(path):
        print("refused: raw captures must stay outside the repository")
        return 2
    record, problem = _load_for_update(path)
    if problem:
        return _g34_stop(problem)
    if "reply" in _dict(_g4_cases(record).get(case)):
        print("refused: case {} is already captured in {}; an activation request is never repeated "
              "(start a new capture to repeat it)".format(case, path))
        return 2
    step = "g4:" + case

    async def capture():
        async with _bound(port, record["process"]["identity"]) as bound:
            before = await bound.listing(step)
            if not before["ok"] or before["active_count"] != 1:
                raise _BenchProblem("the listing is unusable or has no single active document; no request was sent")
            if number > len(before["documents"]):
                raise _BenchProblem("--target {} is beyond the {} open documents; no request was sent".format(
                    number, len(before["documents"])))
            target = before["documents"][number - 1]
            if target["document"] == before["active_document"]:
                raise _BenchProblem(
                    "--target {} is the ACTIVE document; a case needs an inactive one. No request was sent.".format(number))
            if case == "unsaved" and target["path"]:
                raise _BenchProblem(
                    "--target {} has a saved path; the unsaved case must name a never-saved document. "
                    "No request was sent.".format(number))
            if case in ("allow", "saved_workshared") and not target["path"]:
                raise _BenchProblem(
                    "--target {} has no saved path; the {} case needs a saved document. "
                    "No request was sent.".format(number, case))
            try:
                reply_text = await bound.call("activate_document", {"document": target["document"]}, step)
            except Exception as ex:  # the request may have reached Revit: record the loss, never retry
                reply_text = "Error: {}: {}".format(type(ex).__name__, ex)
            reply = build_activation_entry(reply_text)
            try:
                after = await bound.listing(step)
            except Exception as ex:
                after = build_listing_entry("Error: {}: {}".format(type(ex).__name__, ex))
            return build_g4_case(case, target["document"], before, reply, after), bound.sent

    try:
        entry, sent = asyncio.run(capture())
    except _BenchProblem as ex:
        return _g34_stop(str(ex))
    except Exception as ex:
        return _g34_stop("live capture failed ({}: {})".format(type(ex).__name__, ex))
    record["g4"]["cases"][case] = entry
    record["sent_calls"] = list(record["sent_calls"]) + sent
    record["recorded_at"] = _now()
    _write_record(path, record)
    reply = entry["reply"]
    print("G4 {} target={} request sent once".format(case, entry["target_document"]))
    print("  reply: kind={} http={} activation={} reason={} observed_active_document={}".format(
        reply["kind"], reply.get("http_status"), reply.get("activation"), reply.get("reason"),
        reply.get("observed_active_document")))
    print("  active before: {}  after: {}".format(
        entry["before_listing"].get("active_document"), entry["after_listing"].get("active_document")))
    print("OPEN DOCUMENTS now (numbers for the next --target):")
    _print_listing(entry["after_listing"])
    expected = "target-active" if case == "allow" else "unchanged"
    return _g34_pending(
        "now LOOK at the Revit window and for any dialog, then record both with g34-observe --in {} --step {} "
        "(--ui takes the word {} if that is what you saw, else other-active or one of the other words; "
        "--dialog takes the word none or input-required)".format(path, step, expected))


def _cmd_g34_observe(args):
    values = _options(args, ("--in", "--step", "--ui", "--dialog", "--data"))
    if values is None or "--in" not in values or "--step" not in values or "--ui" not in values:
        print(G34_USAGE)
        return 2
    step, ui = values["--step"], values["--ui"]
    dialog, data = values.get("--dialog"), values.get("--data")
    kind, _, name = step.partition(":")
    valid = False
    if kind == "g3" and name in G3_SLOTS:
        valid = (ui in G3_UI and data in DATA_WORDS and (dialog is None or dialog in DIALOG_WORDS))
    elif kind == "g4" and name in G4_CASES:
        valid = ui in G4_UI and dialog in DIALOG_WORDS and data is None
    if not valid:
        print(G34_USAGE)
        return 2
    path = values["--in"]
    if not _outside_repo(path):
        print("refused: raw captures must stay outside the repository")
        return 2
    record, problem = _load_for_update(path)
    if problem:
        return _g34_stop(problem)
    done, message = apply_observation(record, step, ui, dialog, data)
    if not done:
        return _g34_stop(message)
    _write_record(path, record)
    return _g34_pending("observation recorded for {}: ui={} dialog={} data={}".format(step, ui, dialog, data))


def _g3_summary_lines(record):
    lines = []
    try:
        for name in G3_SLOTS:
            slot = _dict(_dict(_dict(record.get("g3")).get("slots")).get(name))
            if not slot:
                lines.append("G3 SLOT {}: not captured".format(name))
                continue
            summary, levels = _dict(slot.get("summary")), _dict(slot.get("levels"))
            lines.append("G3 SLOT {}: active={} target={} summary[{} path={!r} elements={} levels={} ui_switched={}] "
                         "levels[total={} skipped={}] active_after={} engineer={}".format(
                             name, _dict(slot.get("before_listing")).get("active_document"),
                             slot.get("target_document"), summary.get("title"), summary.get("path"),
                             summary.get("non_type_element_count"), summary.get("level_count"),
                             summary.get("ui_switched"), levels.get("total_levels"),
                             levels.get("skipped_levels"),
                             _dict(slot.get("after_listing")).get("active_document"),
                             json.dumps(_dict(slot.get("engineer")), sort_keys=True)))
    except Exception:
        pass
    return lines


def _g4_summary_lines(record, outcomes):
    lines = []
    try:
        cases = _g4_cases(record)
        for name in G4_CASES:
            slot = _dict(cases.get(name))
            reply = _dict(slot.get("reply"))
            detail = ""
            if outcomes[name] != "not-run":
                detail = " (reply kind={} http={} activation={} reason={}; active {} -> {}; engineer={})".format(
                    reply.get("kind"), reply.get("http_status"), reply.get("activation"), reply.get("reason"),
                    _dict(slot.get("before_listing")).get("active_document"),
                    _dict(slot.get("after_listing")).get("active_document"),
                    json.dumps(_dict(slot.get("engineer")), sort_keys=True))
            lines.append("G4 CASE {}: {}{}".format(name, outcomes[name], detail))
    except Exception:
        pass
    return lines


def g34_report(record):
    """Print both classifications; each sentinel only for an observed live record. 0 only if both."""
    live = isinstance(record, dict) and record.get("live") is True
    verdict3, reasons3 = classify_g3_production(record)
    for line in _g3_summary_lines(record):
        print(line)
    print("G3 verdict={}".format(verdict3))
    for reason in reasons3:
        print("  - " + reason)
    observed3 = verdict3 == G3_OBSERVED and live
    print("{} approval={}".format(SENTINEL_G3_OBSERVED if observed3 else SENTINEL_G3_STOP, APPROVAL))

    verdict4, reasons4 = classify_g4_production(record)
    for line in _g4_summary_lines(record, g4_case_outcomes(record)):
        print(line)
    print("G4 verdict={}".format(verdict4))
    for reason in reasons4:
        print("  - " + reason)
    observed4 = verdict4 == G4_OBSERVED and live
    if observed4:
        print("{} approval={}".format(SENTINEL_G4_OBSERVED, APPROVAL))
    elif verdict4 == NOT_RUN:
        print("{} approval={}".format(SENTINEL_G4_NOT_RUN, APPROVAL))
    else:
        print("{} approval={}".format(SENTINEL_G4_STOP, APPROVAL))
    return 0 if observed3 and observed4 else 1


def _cmd_g34_classify(path):
    try:
        record = _read_record(path)
    except (OSError, ValueError) as ex:
        print("cannot read evidence file {!r}: {}".format(path, ex))
        print("{} approval={}".format(SENTINEL_G3_STOP, APPROVAL))
        print("{} approval={}".format(SENTINEL_G4_STOP, APPROVAL))
        return 1
    return g34_report(record)


def _tolerate_console_encoding():
    """A document title outside the console code page must never crash a report."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except Exception:
                pass


def main(argv=None):
    _tolerate_console_encoding()
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
    if command == "g34-template" and not rest:
        print(json.dumps(g34_template(), indent=2))
        return 0
    if command == "g34-classify" and len(rest) == 1:
        return _cmd_g34_classify(rest[0])
    if command == "g34-start":
        return _cmd_g34_start(rest)
    if command == "g3-read":
        return _cmd_g3_read(rest)
    if command == "g4-case":
        return _cmd_g4_case(rest)
    if command == "g34-observe":
        return _cmd_g34_observe(rest)
    print(USAGE)
    print(G34_USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
