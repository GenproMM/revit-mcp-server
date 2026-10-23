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

Single-entry acceptance procedure (plan 02-18)
----------------------------------------------
One record, schema ``phase2-acceptance-v1``, drives the whole live acceptance of
phase 2 through ONE shared stdio MCP entry and per-call selectors. The classifier
``classify_phase2_acceptance`` keeps one slot per ROADMAP success criterion (c1..c9)
and one per gate (g1..g6); each slot is observed, stop or not-run, never inferred.
The verdict is ``accept-eligible`` only when all nine criteria and all six gates are
observed, no record-level rule is broken and every authorization is in order;
otherwise it is ``stop`` and the report lists the open gates (AMBIG-04 is named
whenever G6 is not observed). It never raises and never grants approval: every
report prints ``approval=not-granted`` and PHASE2_ACCEPTANCE_OBSERVED is printed only
for an accept-eligible live, non-synthetic record. The decision stays with the user at
the blocking checkpoint.

Authorization. Three flags, ``mutation_authorized``, ``g6_authorized`` and
``collision_authorized``, each stored with a timestamp and the user's own words. They
are set ONLY by the engineer-typed ``phase2-authorize`` command, once, never by a
capture command or a default. A flagged capture refuses before sending anything
unless its flag is set. A section recorded without its flag is a STOP (policy
violation); a flag left unset makes that section not-run, which keeps the verdict at
stop.

What each section sends (the allow-lists are SECTION_TOOLS / ACC_TOOL_ROUTES; a call
outside its section is a STOP, and the arbitrary-code tool and route are in none of
them, D-15 stays a documented exception outside every confinement claim):

  g2 (read only)        get_revit_status GET /status/; list_documents GET /documents/;
                        read_document_summary POST /document_summary/ (a read of a
                        closed, retired token; the only POST).
  two (read only)       discover_revit_targets (probes GET /status/ of each singleton
                        listener); get_revit_status GET /status/ with and without a
                        target; list_documents GET /documents/.
  http_thread (read)    get_revit_status GET /status/; get_revit_model_info
                        GET /model_info/. Informational, never gating.
  mutation (flag)       get_revit_status; list_documents; set_parameter
                        POST /set_parameter/ and activate_document
                        POST /activate_document/. Disposable copies only.
  collision (flag)      discover_revit_targets; get_revit_status; list_documents.
                        The collision port is never handshaken by the bridge; the
                        inventory is the full netstat parse (bridge.listener_snapshot,
                        netstat.exe -ano -p tcp) and the setup method is recorded.
  g6 (flag)             get_revit_status; list_documents; set_parameter
                        POST /set_parameter/. Disposable copies only.

Every Revit action is its own command. Mutation and G6 sections work only on
disposable model copies whose SHA256 is recorded before and after; the procedure
never saves and never syncs, and a changed hash is a STOP. A collision made with an
auxiliary RoutesServer is recorded as such and is not presented as proof of automatic
primary-port assignment. G6 classifies the wrong-process hypothesis only from the
measured target and answering PID, port and session token plus the observed write
(confirmed | ruled-out | inconclusive); a timed-out write keeps its unknown outcome
and may not be labelled with a verified document. Per-process locks are not shown to
synchronise handlers across sessions: backlog 999.1 stays open.

    phase2-template | phase2-start --out ACC.json | phase2-authorize --in ACC --flag F --words TEXT
    phase2-attach --in ACC --kind identity_recheck|g34 --record RAW.json | phase2-observe ... | phase2-classify ACC.json
    g2-list / g2-stale   two-discover / two-default / two-status / two-list / two-overlap   http-thread
    mut-start / mut-copy / mut-case / mut-activate / mut-finish   collision-probe / collision-after
    g6-start / g6-copy / g6-write / g6-overlap / g6-finish
"""
import asyncio
import base64
import contextlib
import datetime
import hashlib
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
# activate_document appends readable exception diagnostics after the JSON body of an
# activation-failed reply, introduced by this marker (tools/document_tools.py). Only
# that exact block is cut off before the JSON is parsed; any other trailing text still
# makes the body unparseable, as before.
_DIAGNOSTICS_MARKER = "\n\nException diagnostics from Revit"


def _without_diagnostics(body_text):
    return body_text.split(_DIAGNOSTICS_MARKER, 1)[0]


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
    # The JSON body is followed by whatever the renderer appends (the attribution lines of
    # plan 02-16, activation diagnostics): only the leading object is the reply body.
    body = _leading_json(_without_diagnostics(found.group(2)))
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

    def __init__(self, session, section=None):
        self.session = session
        self.section = section  # None: the g34 tool table; a name: that acceptance section's allow-list
        self.sent = []
        self.identity = None
        self.listener = None
        self.selector = None

    async def call(self, tool, arguments, step):
        entry = sent_call_entry(tool, step) if self.section is None else acc_sent_call_entry(self.section, tool, step)
        self.sent.append(entry)  # recorded before the request: a lost reply is still a sent request
        payload = dict(arguments)
        payload["target"] = self.selector
        result = await self.session.call_tool(tool, payload)
        return "\n".join(getattr(item, "text", "") for item in result.content)

    async def listing(self, step):
        return build_listing_entry(await self.call("list_documents", {}, step))


@contextlib.asynccontextmanager
async def _bound(port, expected_identity=None, section=None):
    """Bootstrap one incarnation: identity, sole port owner, selector; yields a _Bound.

    With ``expected_identity`` the answering process must be exactly that one: a
    restarted Revit, another PID or another session token is a stop, never a capture
    mixed into the record.
    """
    async with _server(port) as session:
        bound = _Bound(session, section)
        bound.sent.append(sent_call_entry("get_revit_status", "bootstrap") if section is None
                          else acc_sent_call_entry(section, "get_revit_status", "bootstrap"))
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


def _exception_lines(text):
    """Printable exception diagnostics of an activation-failed reply text; [] for any other reply.

    Display only: it is never read by a classifier. The full reply text stays in the record.
    """
    found = _ERROR_RE.match(text) if isinstance(text, str) else None
    if not found:
        return []
    try:
        body = json.loads(_without_diagnostics(found.group(2)))
    except ValueError:
        return []
    detail = body.get("exception") if isinstance(body, dict) else None
    if not isinstance(detail, dict):
        return []
    lines = ["  exception: {}: {}".format(
        detail.get("net_type") or detail.get("python_type"), detail.get("message"))]
    for index, entry in enumerate(detail.get("inner_exceptions") or [], 1):
        if isinstance(entry, dict):
            lines.append("  inner exception {}: {}: {}".format(index, entry.get("net_type"), entry.get("message")))
    return lines


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
    for line in _exception_lines(reply.get("text")):
        print(line)
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


# ==================================================== plan 02-18: single-entry acceptance
#
# One record (ACC_SCHEMA), many small engineer-run commands, one classifier. The
# capture commands send only what their section's allow-list names, through one stdio
# MCP server process each (two or three for the overlap steps, because the Phase-1
# lock covers one server process only), always with the selector built from a
# verified identity. They never write the engineer fields or an authorization flag.

# The title Revit gives a first unsaved project: English, then the Russian-localized default of the bench.
UNSAVED_DEFAULT_TITLES = ("Project1", "Проект1")
ACC_SCHEMA = "phase2-acceptance-v1"
ACCEPT_ELIGIBLE = "accept-eligible"
SLOT_OBSERVED = "observed"
SENTINEL_ACC_OBSERVED = "PHASE2_ACCEPTANCE_OBSERVED"
SENTINEL_ACC_STOP = "PHASE2_ACCEPTANCE_STOP"
SENTINEL_ACC_PENDING = "PHASE2_ACCEPTANCE_PENDING"

CRITERIA = ("c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9")
CRITERION_TEXT = {
    "c1": "/status/ returns PID, Revit version, port and a session token (live)",
    "c2": "a mutating reply names the document it changed, re-derived at request time, across an activation call and a manual UI switch",
    "c3": "two Revit instances both titled Project1 are distinguishable by response fields alone",
    "c4": "two listeners on one port produce an explicit, named refusal that names every PID",
    "c5": "the param-write-rolls-back wrong-process hypothesis is re-run live with identity visible and its outcome recorded",
    "c6": "every open document can be listed, addressed explicitly and switched by its own tool call; an inactive mutation is HTTP 412",
    "c7": "documents can be compared from one session without the Revit UI switching document (D-11)",
    "c8": "a mutating call that omits the document follows the documented explicit default",
    "c9": "a document closed after listing gives a named error, never a silent operation on another document",
}
CRITERION_REQUIREMENTS = {
    "c1": ("IDENT-01",), "c2": ("IDENT-02", "IDENT-03"), "c3": ("IDENT-04",),
    "c4": ("AMBIG-01", "AMBIG-02", "AMBIG-03"), "c5": ("AMBIG-04",),
    "c6": ("MDOC-01", "MDOC-02", "MDOC-04"), "c7": ("MDOC-01",), "c8": ("MDOC-03",), "c9": ("MDOC-05",),
}
GATES = ("g1", "g2", "g3", "g4", "g5", "g6")
GATE_TEXT = {
    "g1": "G1/G5 identity recheck on the production status route (attached record)",
    "g2": "G2 production: same-title pair, close, replacement and stale-token retry",
    "g3": "G3 production: addressed summary and levels reads of an inactive document (attached record)",
    "g4": "G4 production: explicit activation of a saved existing-path document and its refusals (attached record)",
    "g5": "G5 production: same-port duplicate-listener refusal on a real netstat collision",
    "g6": "G6: param-write rollback, sequential and overlapped, with identity visible",
}
UNITS = GATES + ("two", "mut_c2", "mut_c6", "mut_c8")
# a criterion is observed only when every unit it is built from is observed
CRITERION_UNITS = {
    "c1": ("g1",), "c2": ("mut_c2",), "c3": ("two",), "c4": ("g5",), "c5": ("g6",),
    "c6": ("g3", "g4", "mut_c6"), "c7": ("g3",), "c8": ("mut_c8",), "c9": ("g2",),
}

AUTH_FLAGS = ("mutation_authorized", "g6_authorized", "collision_authorized")
SECTION_FLAG = {"mutation": "mutation_authorized", "g6": "g6_authorized", "collision": "collision_authorized"}
AUTH_SOURCE = "engineer-command-line"
AUTH_MIN_WORDS = 8

# The only tools each section may call, and the single route each tool sends. A tool
# outside its section, any other route and the arbitrary-code surfaces are STOP.
ACC_TOOL_ROUTES = dict(
    TOOL_ROUTES,
    discover_revit_targets=("GET", "/status/"),
    get_revit_model_info=("GET", "/model_info/"),
    set_parameter=("POST", "/set_parameter/"),
)
SECTION_TOOLS = {
    "g2": ("get_revit_status", "list_documents", "read_document_summary"),
    "two": ("discover_revit_targets", "get_revit_status", "list_documents"),
    "http_thread": ("get_revit_status", "get_revit_model_info"),
    "mutation": ("get_revit_status", "list_documents", "set_parameter", "activate_document"),
    "collision": ("discover_revit_targets", "get_revit_status", "list_documents"),
    "g6": ("get_revit_status", "list_documents", "set_parameter"),
}

NETSTAT_METHOD = "netstat.exe -ano -p tcp"
INVENTORY_SOURCE = "bridge.listener_snapshot"
COLLISION_SETUP_KINDS = ("second-revit-primary-port", "auxiliary-routes-server")
_COLLISION_LABELS = ("listener collision", "listener-collision")
G2_LIST_STEPS = ("pair", "after_close", "after_replacement")
G2_STALE_STEPS = ("after_close", "after_replacement")
MUTATION_CASES = ("active_named", "inactive_412", "one_document_default", "many_documents_refused",
                  "after_activation", "after_manual_switch")
CASE_UNIT = {"active_named": "mut_c2", "after_activation": "mut_c2", "after_manual_switch": "mut_c2",
             "inactive_412": "mut_c6", "one_document_default": "mut_c8", "many_documents_refused": "mut_c8"}
CASES_WITH_DOCUMENT = ("active_named", "inactive_412", "after_activation", "after_manual_switch")
G6_WRITE_STEPS = ("seq1", "seq2", "seq_readback", "ov_readback_a", "ov_readback_b")
UI_WORDS = ("unchanged", "changed", "target-active", "other-active", "switched-by-hand",
            "same-title-confirmed", "closed-by-me", "reopened-by-me", "both-project1",
            "collision-created", "collision-removed")
OBS_EXPECTED = dict(
    [("g2:pair", "same-title-confirmed"), ("g2:after_close", "closed-by-me"),
     ("g2:after_replacement", "reopened-by-me"), ("two:setup", "both-project1"),
     ("mut:activation", "target-active"), ("mut:after_manual_switch", "switched-by-hand"),
     ("collision:setup", "collision-created"), ("collision:cleanup", "collision-removed")]
    + [("mut:" + c, "unchanged") for c in MUTATION_CASES if c != "after_manual_switch"]
    + [("g6:" + s, "unchanged") for s in G6_WRITE_STEPS + ("overlap",)])
OBS_DIALOG_PREFIXES = ("mut:", "g6:", "collision:")

R_AUTH_MALFORMED = "authorization-malformed"
R_SECTION_UNAUTHORIZED = "section-without-authorization"
R_AUTH_AFTER_SEND = "authorization-after-send"
R_UNIT_INCOMPLETE = "unit-incomplete"
R_PRIOR_MALFORMED = "prior-malformed"
R_G6_INCONCLUSIVE = "g6-inconclusive"

ACC_REASON_CODES = (
    R_NO_RECORD, R_NOT_LIVE, R_SYNTHETIC, R_SCHEMA, R_ROUTE_NOT_ALLOWED, R_CALLS_UNRECORDED,
    R_CLASSIFIER_ERROR, R_AUTH_MALFORMED, R_SECTION_UNAUTHORIZED, R_AUTH_AFTER_SEND,
    R_UNIT_INCOMPLETE, R_PRIOR_MALFORMED, R_ENGINEER_UI_CHANGED, R_WORKSHARED_ALLOW,
    "g2-engineer-unexpected", "two-engineer-unexpected", "collision-engineer-unexpected",
    "g6-engineer-unexpected", "collision-dialog-required-input",
    "g2-process-unverified", "g2-listing-unusable", "g2-no-same-title-pair", "g2-stale-not-from-pair",
    "g2-closed-token-listed", "g2-survivor-lost", "g2-stale-read-answered", "g2-stale-refusal-unnamed",
    "g2-replacement-missing", "g2-replacement-token-reused", "g2-engineer-unobserved",
    "g2-identity-mismatch",
    "two-discovery-incomplete", "two-not-two-processes", "two-collision-listed", "two-default-not-refused",
    "two-status-identity-mismatch", "two-identities-equal", "two-no-project1", "two-listener-not-sole",
    "two-list-unusable", "two-engineer-unobserved",
    "mutation-process-unverified", "mutation-disposable-unattested", "mutation-copy-unregistered",
    "mutation-copy-hash-missing", "mutation-copy-file-changed", "mutation-case-malformed",
    "mutation-send-count", "mutation-reply-unexpected", "mutation-document-not-named",
    "mutation-identity-mismatch", "mutation-listing-unusable", "mutation-active-changed",
    "mutation-activation-missing", "mutation-switch-not-observed", "mutation-candidates-incomplete",
    "mutation-engineer-unobserved", "mutation-engineer-unexpected", "mutation-dialog-required-input",
    "mutation-unknown-labelled-verified",
    "collision-setup-unrecorded", "collision-inventory-not-netstat", "collision-inventory-malformed",
    "collision-not-a-collision", "collision-pid-unnamed", "collision-discovery-offered-target",
    "collision-default-not-refused", "collision-selected-not-refused", "collision-request-sent",
    "collision-cleanup-incomplete", "collision-engineer-unobserved",
    "g6-process-unverified", "g6-disposable-unattested", "g6-copy-unregistered", "g6-copy-hash-missing",
    "g6-copy-file-changed", "g6-reply-unexpected", "g6-unknown-labelled-verified", R_G6_INCONCLUSIVE,
    "g6-listing-unusable", "g6-engineer-unobserved", "g6-dialog-required-input", "g6-send-count",
)


def acc_sent_call_entry(section, tool, step, at=None):
    """One sent-call record for a section; only that section's allow-listed tools have one."""
    allowed = SECTION_TOOLS.get(section) if isinstance(section, str) else None
    if allowed is None:
        raise ValueError("{!r} is not an acceptance section".format(section))
    if not isinstance(tool, str) or tool not in allowed:
        raise ValueError("{!r} is not a tool section {} may call".format(tool, section))
    method, route = ACC_TOOL_ROUTES[tool]
    return {"method": method, "route": route, "tool": tool, "section": section, "step": step,
            "at": at or _now()}


def _sha256_file(path):
    """SHA256 of a file read in binary, or None when it cannot be read."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest()
    except (OSError, TypeError, ValueError):
        return None


def _is_sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


# ------------------------------------------------------------ parsing reply texts

_SET_RE = re.compile(r"^Set '(.+)' from '(.*)' to '(.*)' on element (\d+)[ \t]*$", re.MULTILINE)
_DOC_LINE_RE = re.compile(
    r"^Revit reported this document for the call: (.*) \(document (\S+); path: (.*?)(; active)?\)[ \t]*$",
    re.MULTILINE)
_NAMED_RE = re.compile(r"the reply names PID (\d+) on port (\d+)")
_USABLE_HEAD_RE = re.compile(r"^Usable Revit processes: (\d+)[ \t]*$")
_USABLE_LINE_RE = re.compile(r"^(\d+)\. PID (\d+); Revit (.+?); port (\d+); (.*)$")
_TARGET_LINE_RE = re.compile(r"^   target: (\S+)[ \t]*$")
_UNUSABLE_LINE_RE = re.compile(r"^- port (\d+); PID ([\d, ]+); ([^:]+): ")
_MULTIPLE_RE = re.compile(r"Multiple usable Revit processes \((\d+)\)")
_CANDIDATE_RE = re.compile(r"target=(revit1:[A-Za-z0-9_-]+)")


def _leading_json(text):
    """The JSON object a text starts with (trailing rendered lines ignored), or None."""
    try:
        value, _end = json.JSONDecoder().raw_decode(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _verified_identity(text):
    """The last verified-process line of a rendered reply, as an identity, or None."""
    found = list(_VERIFIED_RE.finditer(text))
    if not found:
        return None
    last = found[-1]
    identity = {"pid": int(last.group(1)), "actual_port": int(last.group(3)),
                "session_token": last.group(4), "revit_version": last.group(2).strip()}
    return identity if _complete_identity(identity) else None


def _empty_mutation():
    return {"kind": "error", "http_status": None, "error_code": None, "reason": None, "element_id": None,
            "parameter_name": None, "old_value": None, "new_value": None, "document": None,
            "document_title": None, "document_path": None, "document_active": None, "identity": None,
            "candidates": None, "active_document": None, "transaction_status": None, "named_pid": None,
            "named_port": None, "credits": False}


def parse_mutation_text(text):
    """Fields of one set_parameter reply text. Never raises.

    kind: success | rolled-back | refused | error | unknown | not-sent | conflict |
    unverified. ``credits`` is True when the rendered text credits a verified process or
    a document: it must be False for every kind that did not receive a verified reply.
    """
    parsed = _empty_mutation()
    if not isinstance(text, str):
        return parsed
    found = _DOC_LINE_RE.search(text)
    parsed["credits"] = bool(_VERIFIED_RE.search(text)) or found is not None
    if "came from a different Revit process" in text:
        named = _NAMED_RE.search(text)
        parsed["kind"] = "conflict"
        if named:
            parsed["named_pid"], parsed["named_port"] = int(named.group(1)), int(named.group(2))
        return parsed
    if "Attribution: none. This request was not sent" in text:
        parsed["kind"] = "not-sent"
        return parsed
    if "Attribution: unconfirmed. The request was sent toward Revit" in text or "outcome is unknown" in text.lower():
        parsed["kind"] = "unknown"
        return parsed
    if "Attribution: unconfirmed. A reply (HTTP" in text:
        parsed["kind"] = "unverified"
        return parsed
    identity = _verified_identity(text)
    error = _ERROR_RE.match(text)
    if error:
        status = int(error.group(1))
        body = _leading_json(error.group(2)) or {}
        parsed["http_status"] = status
        for key in ("error_code", "reason"):
            parsed[key] = body.get(key) if isinstance(body.get(key), str) else None
        parsed["transaction_status"] = body.get("transaction_status") if isinstance(
            body.get("transaction_status"), str) else None
        if isinstance(body.get("candidates"), list):
            parsed["candidates"] = [c.get("document") for c in body["candidates"] if isinstance(c, dict)]
        if isinstance(body.get("active_document"), str):
            parsed["active_document"] = body["active_document"]
        document = body.get("document")
        if isinstance(document, dict) and isinstance(document.get("document"), str):
            parsed["document"] = document["document"]
            parsed["document_title"] = document.get("title")
            parsed["document_path"] = document.get("path")
            parsed["document_active"] = document.get("active")
        for key, field in (("element_id", "element_id"), ("parameter_name", "parameter_name"),
                           ("old_value", "old_value")):
            parsed[field] = body.get(key)
        stamp = body.get("process_identity")
        if identity is None and _complete_identity(stamp):
            identity = dict((k, stamp[k]) for k in ("pid", "actual_port", "session_token", "revit_version"))
        parsed["identity"] = identity
        if status == 409 and body.get("status") == "rolled_back":
            parsed["kind"] = "rolled-back"
        elif 400 <= status < 500:
            parsed["kind"] = "refused"
        return parsed
    done = _SET_RE.search(text)
    if done:
        parsed.update(kind="success", http_status=200, parameter_name=done.group(1), old_value=done.group(2),
                      new_value=done.group(3), element_id=int(done.group(4)), identity=identity)
        if found:
            parsed.update(document=found.group(2), document_title=found.group(1),
                          document_path="" if found.group(3) == _NEVER_SAVED else found.group(3),
                          document_active=found.group(4) is not None)
    return parsed


def build_mutation_entry(text, at=None):
    entry = parse_mutation_text(text)
    entry.update({"text": text if isinstance(text, str) else None, "at": at or _now()})
    return entry


def parse_discovery_text(text):
    """Usable processes and unusable listeners of one discover_revit_targets reply.

    ok is True only for a reply with its header and as many well-formed usable entries
    as it declares; an error (an unavailable inventory) is never an empty list.
    """
    result = {"ok": False, "usable": [], "unusable": []}
    if not isinstance(text, str):
        return result
    lines = text.splitlines()
    declared = None
    for line in lines:
        head = _USABLE_HEAD_RE.match(line)
        if head:
            declared = int(head.group(1))
            break
        if line.startswith("No usable Revit process found"):
            declared = 0
            break
    if declared is None:
        return result
    usable, wellformed = [], True
    for index, line in enumerate(lines):
        row = _USABLE_LINE_RE.match(line)
        if row:
            target = _TARGET_LINE_RE.match(lines[index + 1]) if index + 1 < len(lines) else None
            entry = {"pid": int(row.group(2)), "revit_version": row.group(3), "port": int(row.group(4)),
                     "document_open": row.group(5).startswith("a document is open"),
                     "selector": target.group(1) if target else None, "session_token": None, "host": None}
            try:
                parsed = _bridge().parse_target(entry["selector"])
                entry["session_token"], entry["host"] = parsed["session_token"], parsed["host"]
                wellformed = wellformed and parsed["pid"] == entry["pid"] and parsed["port"] == entry["port"]
            except (ValueError, KeyError, TypeError):
                wellformed = False
            usable.append(entry)
        bad = _UNUSABLE_LINE_RE.match(line)
        if bad:
            result["unusable"].append({"port": int(bad.group(1)),
                                       "pids": sorted(int(p) for p in re.findall(r"\d+", bad.group(2))),
                                       "reason": bad.group(3).strip()})
    result["usable"] = usable
    result["ok"] = wellformed and len(usable) == declared
    return result


def parse_refusal_text(text):
    """Whether a reply is a not-sent refusal, which PIDs it names and whether it credits a process."""
    result = {"refused": False, "not_sent": False, "credits": False, "pids": [], "multiple": None,
              "candidates": []}
    if not isinstance(text, str):
        return result
    result["refused"] = text.startswith("Error:") and "request not sent" in text
    result["not_sent"] = "Attribution: none. This request was not sent" in text or result["refused"]
    result["credits"] = _VERIFIED_RE.search(text) is not None
    if "Listener collision:" in text:
        segment = text.split("Listener collision:", 1)[1].split("request not sent", 1)[0]
        segment = re.sub(r"port \d+", "", segment)
        result["pids"] = sorted(set(int(p) for p in re.findall(r"\d+", segment)))
    multiple = _MULTIPLE_RE.search(text)
    result["multiple"] = int(multiple.group(1)) if multiple else None
    result["candidates"] = _CANDIDATE_RE.findall(text)
    return result


# ------------------------------------------------------------ record and authorization


def acceptance_template():
    """The record to fill; every live value starts null or empty, which classifies as STOP."""
    return {
        "schema": ACC_SCHEMA, "live": None, "synthetic": None, "recorded_at": None, "route_namespace": None,
        "authorizations": dict((flag, None) for flag in AUTH_FLAGS),
        "prior": {"identity_recheck": None, "g34": None},
        "sent_calls": [], "engineer": {}, "copies": [],
        "g2": {}, "two": {}, "http_thread": {}, "mutation": {}, "collision": {}, "g6": {},
    }


def apply_authorization(record, flag, words):
    """Set one authorization flag from the user's own words; (ok, message).

    This is the only writer of a flag. Nothing else sets one: not a capture command,
    not a callback, not a default. A flag is set once and never overwritten.
    """
    if flag not in AUTH_FLAGS:
        return False, "unknown flag {!r}".format(flag)
    if not isinstance(words, str) or len(words.strip()) < AUTH_MIN_WORDS:
        return False, "the user's own words are required (at least {} characters)".format(AUTH_MIN_WORDS)
    auths = record.setdefault("authorizations", {})
    current = auths.get(flag)
    if isinstance(current, dict) and current.get("value") is True:
        return False, "{} is already set and is never overwritten".format(flag)
    auths[flag] = {"value": True, "at": _now(), "words": words, "source": AUTH_SOURCE}
    return True, "recorded"


# ------------------------------------------------------------ the classifier


class _Unit(object):
    """One slot: problems make it stop, missing pieces make it not-run, otherwise observed."""

    def __init__(self, name):
        self.name = name
        self.problems = []
        self.missing = []

    def stop(self, code, text):
        reason = _reason(code, text)
        if reason not in self.problems:
            self.problems.append(reason)

    def absent(self, text):
        reason = _reason(R_UNIT_INCOMPLETE, text)
        if reason not in self.missing:
            self.missing.append(reason)

    @property
    def status(self):
        if self.problems:
            return STOP
        return NOT_RUN if self.missing else SLOT_OBSERVED

    def as_dict(self):
        return {"status": self.status, "reasons": self.problems + self.missing}


def _auth_state(item):
    """(state, problem) of one stored flag: authorized | not-authorized | stop."""
    if item is None or item is False:
        return "not-authorized", None
    if isinstance(item, dict):
        value = item.get("value")
        if value is None or value is False:
            return "not-authorized", None
        if (value is True and _parse_time(item.get("at")) is not None and _nonblank(item.get("words"))
                and item.get("source") == AUTH_SOURCE):
            return "authorized", None
    return "stop", "the flag lacks a true value, an aware timestamp, the user's words or the engineer-command source"


def _section_calls(record, section):
    return [c for c in _list(record.get("sent_calls")) if isinstance(c, dict) and c.get("section") == section]


def _section_touched(record, section):
    data = record.get(section)
    if isinstance(data, dict) and any(value not in (None, {}, [], "") for value in data.values()):
        return True
    if _section_calls(record, section):
        return True
    return any(isinstance(c, dict) and c.get("section") == section for c in _list(record.get("copies")))


def _first_time(values):
    times = [t for t in (_parse_time(v) for v in values) if t is not None]
    return min(times) if times else None


def _policy(record, reasons):
    """Authorization states, plus the per-flag problems of sections recorded without one."""
    states, problems = {}, dict((flag, []) for flag in AUTH_FLAGS)
    auths = _dict(record.get("authorizations"))
    for flag in AUTH_FLAGS:
        state, problem = _auth_state(auths.get(flag))
        states[flag] = state
        section = [s for s, f in SECTION_FLAG.items() if f == flag][0]
        if state == "stop":
            problems[flag].append(_reason(R_AUTH_MALFORMED, "{}: {}".format(flag, problem)))
        elif state == "not-authorized" and _section_touched(record, section):
            problems[flag].append(_reason(
                R_SECTION_UNAUTHORIZED, "section {} has data but {} is not set by the engineer".format(section, flag)))
        elif state == "authorized":
            first = _first_time(c.get("at") for c in _section_calls(record, section))
            given = _parse_time(auths[flag].get("at"))
            if first is not None and given is not None and given > first:
                problems[flag].append(_reason(
                    R_AUTH_AFTER_SEND, "{} was given after the first request of section {}".format(flag, section)))
    for flag in AUTH_FLAGS:
        reasons.extend(problems[flag])
    return states, problems


def _check_sent_calls(record, reasons):
    calls = record.get("sent_calls")
    if not isinstance(calls, list) or not calls:
        reasons.append(_reason(R_CALLS_UNRECORDED, "no sent-call list was recorded"))
        return
    seen = set()
    for item in calls:
        section = item.get("section") if isinstance(item, dict) else None
        tool = item.get("tool") if isinstance(item, dict) else None
        allowed = SECTION_TOOLS.get(section) if isinstance(section, str) else None
        good = (allowed is not None and isinstance(tool, str) and tool in allowed
                and (item.get("method"), item.get("route")) == ACC_TOOL_ROUTES[tool])
        if not good and repr(item) not in seen:
            seen.add(repr(item))
            reasons.append(_reason(R_ROUTE_NOT_ALLOWED, "request outside its section allow-list: {!r}".format(item)))


def _count_sends(record, section, tool, step):
    return len([c for c in _section_calls(record, section) if c.get("tool") == tool and c.get("step") == step])


def _section_process(section_data, add, code, label):
    """The recorded process identity if it is complete and sole owner of its port, else None."""
    process = _dict(section_data.get("process"))
    identity = process.get("identity")
    if not _complete_identity(identity):
        add(code, "{}: the recorded process carries no complete identity".format(label))
        return None
    listener = _dict(process.get("listener"))
    owners = listener.get("owners")
    if not (isinstance(owners, list) and owners == [identity["pid"]] and listener.get("port") == identity["actual_port"]):
        add(code, "{}: the listener inventory does not show the recorded PID as sole owner of its port".format(label))
    return identity


def _engineer(record, step, add, code_prefix, expected=None):
    """Check the engineer's words for a captured step; adds problems through ``add``."""
    entry = _dict(_dict(record.get("engineer")).get(step))
    want = expected if expected is not None else OBS_EXPECTED.get(step)
    ui = entry.get("ui")
    dialog = entry.get("dialog_required_input")
    if ui not in UI_WORDS:
        add(code_prefix + "-engineer-unobserved", "{}: the engineer has not recorded an observation".format(step))
    elif ui != want:
        add(code_prefix + "-engineer-unexpected", "{}: the engineer saw {!r}, expected {!r}".format(step, ui, want))
    if step.startswith(OBS_DIALOG_PREFIXES):
        if dialog is True:
            add(code_prefix + "-dialog-required-input", "{}: the engineer reports a dialog requiring input".format(step))
        elif dialog is not False:
            add(code_prefix + "-engineer-unobserved",
                "{}: the engineer has not recorded whether a dialog appeared".format(step))


def _titles(listing):
    return [d for d in _list(_dict(listing).get("documents")) if isinstance(d, dict)]


def _token_set(listing):
    return set(d.get("document") for d in _titles(listing))


def _unit_prior(record, units):
    prior = _dict(record.get("prior"))

    def attached(kind):
        item = prior.get(kind)
        if item is None:
            return None
        inner = item.get("record") if isinstance(item, dict) else None
        return inner if isinstance(inner, dict) else False

    ident = attached("identity_recheck")
    if ident is None:
        units["g1"].absent("no identity recheck record is attached (G1/G5 recheck)")
    elif ident is False:
        units["g1"].stop(R_PRIOR_MALFORMED, "the attached identity recheck record is not an object")
    else:
        verdict, reasons = classify_identity_recheck(ident)
        for reason in reasons if verdict != OBSERVED else ():
            units["g1"].problems.append(reason)
    g34 = attached("g34")
    if g34 is None:
        for name in ("g3", "g4"):
            units[name].absent("no g34 production record is attached")
    elif g34 is False:
        for name in ("g3", "g4"):
            units[name].stop(R_PRIOR_MALFORMED, "the attached g34 record is not an object")
    else:
        verdict3, reasons3 = classify_g3_production(g34)
        if verdict3 != G3_OBSERVED:
            units["g3"].problems.extend(reasons3)
        verdict4, reasons4 = classify_g4_production(g34)
        if verdict4 == NOT_RUN:
            for reason in reasons4:
                units["g4"].missing.append(reason)
        elif verdict4 != G4_OBSERVED:
            units["g4"].problems.extend(reasons4)


def _unit_g2(record, unit):
    g2 = _dict(record.get("g2"))
    if not g2:
        unit.absent("the g2 section was never captured")
        return
    add = unit.stop
    identity = _section_process(g2, add, "g2-process-unverified", "g2")
    steps, stale = _dict(g2.get("steps")), _dict(g2.get("stale"))
    for name in G2_LIST_STEPS:
        listing = steps.get(name)
        if not isinstance(listing, dict):
            unit.absent("listing {} was not captured".format(name))
            continue
        if not _usable_listing(listing):
            add("g2-listing-unusable", "listing {} is missing or unusable".format(name))
        elif not _same_process(listing, identity):
            add("g2-identity-mismatch", "listing {} was not answered by the recorded process".format(name))
        _engineer(record, "g2:" + name, add, "g2")
    pair = steps.get("pair")
    pair_docs = _titles(pair) if _usable_listing(pair) else []
    groups = {}
    for d in pair_docs:
        groups.setdefault(d.get("title"), set()).add(d.get("document"))
    if pair_docs and not any(len(tokens) >= 2 for tokens in groups.values()):
        add("g2-no-same-title-pair", "no two documents of the pair listing share a title")
    seen = set(_token_set(pair))
    for name in G2_STALE_STEPS:
        entry = stale.get(name)
        if not isinstance(entry, dict):
            unit.absent("stale-token retry {} was not captured".format(name))
            continue
        token, index = entry.get("stale_token"), entry.get("from_index")
        member = (_is_int(index) and 1 <= index <= len(pair_docs) and pair_docs[index - 1].get("document") == token
                  and len(groups.get(pair_docs[index - 1].get("title"), ())) >= 2)
        if pair_docs and not member:
            add("g2-stale-not-from-pair", "stale token {!r} is not document {} of a same-title group in the pair "
                "listing".format(token, index))
        reply = _dict(entry.get("reply"))
        if reply.get("kind") != "refused":
            add("g2-stale-read-answered", "the read of the closed token {} ({}) was not refused (kind {!r})".format(
                token, name, reply.get("kind")))
        elif reply.get("error_code") != "document-closed" or reply.get("http_status") != 404:
            add("g2-stale-refusal-unnamed", "the refusal of the closed token {} ({}) is not the named HTTP 404 "
                "document-closed ({!r}, {!r})".format(token, name, reply.get("http_status"), reply.get("error_code")))
        if identity is not None and reply.get("identity") not in (None, identity):
            add("g2-identity-mismatch", "the stale read ({}) was answered by another process".format(name))
        listing = steps.get(name)
        if not _usable_listing(listing):
            continue
        tokens = _token_set(listing)
        if name == "after_close":
            if token in tokens:
                add("g2-closed-token-listed", "the closed token {} is still listed after the close".format(token))
            if not (seen - {token}) <= tokens:
                add("g2-survivor-lost", "a document other than the closed one disappeared from the listing")
        else:
            seen_before = seen | _token_set(steps.get("after_close"))
            same = [d for d in _titles(listing) if d.get("title") == entry.get("closed_title")
                    and d.get("path") == entry.get("closed_path")]
            if not same:
                add("g2-replacement-missing", "no document with the closed title and path is listed after the "
                    "replacement")
            elif not [d for d in same if d.get("document") not in seen_before]:
                add("g2-replacement-token-reused", "the replacement carries a selector that was already issued")


def _unit_two(record, unit):
    two = _dict(record.get("two"))
    if not two:
        unit.absent("the two-process section was never captured")
        return
    add = unit.stop
    discovery = two.get("discovery")
    if not isinstance(discovery, dict):
        unit.absent("no discovery capture")
        return
    usable = [u for u in _list(discovery.get("usable")) if isinstance(u, dict)]
    if discovery.get("ok") is not True:
        add("two-discovery-incomplete", "the discovery reply was not a complete, well-formed listing")
    pids, ports, tokens = set(u.get("pid") for u in usable), set(u.get("port") for u in usable), set(
        u.get("session_token") for u in usable)
    if len(usable) != 2 or len(pids) != 2 or len(ports) != 2 or len(tokens) != 2:
        add("two-not-two-processes", "discovery shows {} usable process(es); two distinct incarnations are needed".format(
            len(usable)))
    if any(isinstance(u, dict) and u.get("reason") in _COLLISION_LABELS for u in _list(discovery.get("unusable"))):
        add("two-collision-listed", "a listener collision is listed while two processes are being compared")
    default = two.get("default")
    if not isinstance(default, dict):
        unit.absent("the default (no target) refusal was not captured")
    elif not (default.get("refused") is True and default.get("credits") is False and default.get("multiple") == 2):
        add("two-default-not-refused", "a call without a target was not refused with the two candidates")
    answers = {}
    for which in ("1", "2"):
        expected = usable[int(which) - 1] if len(usable) >= int(which) else None
        status = _dict(two.get("status")).get(which)
        listing = _dict(two.get("list")).get(which)
        inventory = _dict(two.get("listeners")).get(which)
        if not isinstance(status, dict):
            unit.absent("status of process {} was not captured".format(which))
        elif expected is not None:
            want = {"pid": expected.get("pid"), "actual_port": expected.get("port"),
                    "session_token": expected.get("session_token")}
            got = _dict(status.get("identity"))
            if not _complete_identity(got) or dict((k, got.get(k)) for k in want) != want:
                add("two-status-identity-mismatch", "the status reply of process {} does not carry the discovered "
                    "PID, port and token".format(which))
        if not isinstance(listing, dict):
            unit.absent("document list of process {} was not captured".format(which))
        else:
            if not _usable_listing(listing):
                add("two-list-unusable", "the document list of process {} is missing or unusable".format(which))
            else:
                got = listing.get("identity")
                answers[which] = got
                if expected is not None and not (isinstance(got, dict) and got.get("pid") == expected.get("pid")
                                                 and got.get("session_token") == expected.get("session_token")):
                    add("two-status-identity-mismatch", "the document list of process {} was answered by another "
                        "process".format(which))
                if not any(d.get("title") in UNSAVED_DEFAULT_TITLES and not d.get("path") for d in _titles(listing)):
                    add("two-no-project1", "process {} lists no unsaved document titled Project1 (or its localized "
                        "default {})".format(which, UNSAVED_DEFAULT_TITLES[1]))
        if isinstance(inventory, dict) and expected is not None:
            if not (inventory.get("owners") == [expected.get("pid")] and inventory.get("port") == expected.get("port")):
                add("two-listener-not-sole", "the port of process {} is not held by its PID alone".format(which))
    if len(answers) == 2 and answers["1"] == answers["2"]:
        add("two-identities-equal", "both document lists carry the same answering process identity")
    if isinstance(discovery, dict) and (_dict(two.get("list")) or _dict(two.get("status"))):
        _engineer(record, "two:setup", add, "two")


def _unit_copies(record, section, identity, add, mutated):
    """Disposable-copy registry rules for one section; ``mutated`` are the tokens a reply named."""
    copies = [c for c in _list(record.get("copies")) if isinstance(c, dict) and c.get("section") == section]
    prefix = "mutation" if section == "mutation" else "g6"
    if not copies:
        add(prefix + "-copy-unregistered", "no disposable copy is registered for {}".format(section))
        return
    for c in copies:
        if identity is not None and c.get("process_token") != identity["session_token"]:
            add(prefix + "-copy-unregistered", "copy {} is registered for another process".format(c.get("document")))
        if not _is_sha256(c.get("sha256_before")) or not _is_sha256(c.get("sha256_after")):
            add(prefix + "-copy-hash-missing", "copy {} lacks a SHA256 before or after the run".format(c.get("document")))
        elif c["sha256_before"] != c["sha256_after"]:
            add(prefix + "-copy-file-changed", "the file of copy {} changed: something saved or synced it".format(
                c.get("document")))
    registered = set(c.get("document") for c in copies)
    for token in sorted(t for t in mutated if t is not None and t not in registered):
        add(prefix + "-copy-unregistered", "document {} was mutated but is not a registered copy".format(token))


def _uncertain_labelled(reply):
    return reply.get("kind") in ("unknown", "not-sent", "conflict", "unverified") and reply.get("credits") is not False


def _unit_mutation(record, units):
    section = _dict(record.get("mutation"))
    names = ("mut_c2", "mut_c6", "mut_c8")
    if not section:
        for name in names:
            units[name].absent("the mutation section was never captured")
        return

    def add_all(code, text):
        for name in names:
            units[name].stop(code, text)

    identity = _section_process(section, add_all, "mutation-process-unverified", "mutation")
    if not _nonblank(_dict(section.get("disposable")).get("words")):
        add_all("mutation-disposable-unattested", "the engineer never attested that the documents are disposable copies")
    cases = _dict(section.get("cases"))
    mutated = set()
    for name in MUTATION_CASES:
        entry = cases.get(name)
        unit = units[CASE_UNIT[name]]
        if not isinstance(entry, dict):
            unit.absent("case {} was not captured".format(name))
            continue
        reply = _dict(entry.get("reply"))
        if reply.get("document"):
            mutated.add(reply.get("document"))
        _mutation_case(record, section, name, entry, identity, unit)
    activation = section.get("activation")
    if isinstance(activation, dict):
        _mutation_activation(record, activation, identity, units["mut_c2"])
    elif isinstance(cases.get("after_activation"), dict):
        units["mut_c2"].stop("mutation-activation-missing", "after_activation was captured without a captured activation")
    _unit_copies(record, "mutation", identity, add_all, mutated)


def _reply_identity_ok(reply, identity):
    return identity is None or reply.get("identity") == identity


def _mutation_case(record, section, name, entry, identity, unit):
    add = unit.stop
    step = "mut:" + name
    if entry.get("case") != name or entry.get("step") != step:
        add("mutation-case-malformed", "case {} does not name itself".format(name))
    request, reply = _dict(entry.get("request")), _dict(entry.get("reply"))
    before, after = entry.get("before_listing"), entry.get("after_listing")
    if not _usable_listing(before) or not _usable_listing(after):
        add("mutation-listing-unusable", "case {}: the listing before or after the request is unusable".format(name))
        return
    if _count_sends(record, "mutation", "set_parameter", step) != 1:
        add("mutation-send-count", "case {}: the write is sent exactly once, never retried".format(name))
    if _uncertain_labelled(reply):
        add("mutation-unknown-labelled-verified", "case {}: a {} outcome is labelled with a verified process or "
            "document".format(name, reply.get("kind")))
    active = before["active_document"]
    docs = _token_set(before)
    document = request.get("document")
    listed = dict((d["document"], d) for d in _titles(before))
    if name in CASES_WITH_DOCUMENT and document not in listed:
        add("mutation-case-malformed", "case {}: the request names a document that is not listed".format(name))
    if name not in CASES_WITH_DOCUMENT and document is not None:
        add("mutation-case-malformed", "case {}: the document argument must be omitted".format(name))
    if reply.get("kind") in ("success", "refused", "rolled-back", "error") and not _reply_identity_ok(reply, identity):
        add("mutation-identity-mismatch", "case {}: the reply was not answered by the recorded process".format(name))

    def success_naming(target):
        if reply.get("kind") != "success":
            add("mutation-reply-unexpected", "case {}: expected a success, got {!r}".format(name, reply.get("kind")))
            return
        descriptor = listed.get(target)
        if (reply.get("document") != target or descriptor is None or reply.get("document_title") != descriptor.get("title")
                or reply.get("document_path") != descriptor.get("path") or reply.get("document_active") is not True):
            add("mutation-document-not-named", "case {}: the reply does not name the changed document (title, path, "
                "active) the listing gives".format(name))
        if (reply.get("element_id") != request.get("element_id") or reply.get("parameter_name") != request.get("parameter_name")
                or reply.get("new_value") != request.get("value")):
            add("mutation-reply-unexpected", "case {}: the reply does not describe the requested write".format(name))

    def refused(status, code):
        if not (reply.get("kind") == "refused" and reply.get("http_status") == status and reply.get("error_code") == code):
            add("mutation-reply-unexpected", "case {}: expected HTTP {} {}, got {!r} {!r} {!r}".format(
                name, status, code, reply.get("kind"), reply.get("http_status"), reply.get("error_code")))
            return False
        return True

    if name == "active_named" or name == "after_manual_switch" or name == "after_activation":
        if document != active:
            add("mutation-case-malformed", "case {}: the named document is not the active one".format(name))
        success_naming(document)
    if name == "after_manual_switch":
        previous = entry.get("previous_active")
        if not (isinstance(previous, str) and previous and previous != active):
            add("mutation-switch-not-observed", "the active document was not seen to change by hand before the call")
    if name == "after_activation":
        act = _dict(_dict(section.get("activation")).get("reply"))
        if not (act.get("kind") == "success" and act.get("activation") == "activated" and act.get("document") == document):
            add("mutation-activation-missing", "no captured activation made {} active before this call".format(document))
    if name == "inactive_412":
        if document == active or document not in listed:
            add("mutation-case-malformed", "case inactive_412 must name an open, inactive document")
        if refused(412, "document-not-active") and reply.get("active_document") != active:
            add("mutation-reply-unexpected", "the 412 does not name the unchanged active document")
    if name == "one_document_default":
        if len(docs) != 1:
            add("mutation-case-malformed", "case one_document_default needs exactly one open document")
        else:
            success_naming(next(iter(docs)))
    if name == "many_documents_refused":
        if len(docs) < 2:
            add("mutation-case-malformed", "case many_documents_refused needs several open documents")
        if refused(400, "document-selector-required"):
            if set(reply.get("candidates") or []) != docs:
                add("mutation-candidates-incomplete", "the refusal does not list every open document")
            if reply.get("document") is not None:
                add("mutation-document-not-named", "a refusal must not name a document as changed")
    if after["active_document"] != active:
        add("mutation-active-changed", "case {}: the active document was {!r} before and {!r} after".format(
            name, active, after["active_document"]))
    _engineer(record, step, add, "mutation")


def _mutation_activation(record, activation, identity, unit):
    add = unit.stop
    reply = _dict(activation.get("reply"))
    before, after = activation.get("before_listing"), activation.get("after_listing")
    target = activation.get("target_document")
    if not (reply.get("kind") == "success" and reply.get("activation") == "activated" and reply.get("document") == target):
        add("mutation-reply-unexpected", "the activation was not answered as an activation of {}".format(target))
    if not _usable_listing(before) or not _usable_listing(after):
        add("mutation-listing-unusable", "the listing around the activation is unusable")
    elif after["active_document"] != target or before["active_document"] == target:
        add("mutation-active-changed", "the activation did not move the active document to the target")
    if not _reply_identity_ok(reply, identity):
        add("mutation-identity-mismatch", "the activation was not answered by the recorded process")
    if _count_sends(record, "mutation", "activate_document", "mut:activation") != 1:
        add("mutation-send-count", "the activation is sent exactly once")
    _engineer(record, "mut:activation", add, "mutation")


def _valid_inventory(inventory, port, allow_empty=False):
    owners = _dict(inventory).get("owners")
    return (isinstance(owners, list) and (bool(owners) or allow_empty)
            and all(_is_int(p) and p > 0 for p in owners)
            and len(set(owners)) == len(owners) and _is_port(_dict(inventory).get("port"))
            and inventory.get("port") == port)


def _unit_collision(record, unit, qualifications):
    col = _dict(record.get("collision"))
    probe = col.get("probe")
    if not isinstance(probe, dict):
        unit.absent("the collision probe was never captured")
        return
    add = unit.stop
    port = probe.get("port")
    if probe.get("setup_kind") not in COLLISION_SETUP_KINDS or not _nonblank(probe.get("setup_method")):
        add("collision-setup-unrecorded", "the setup kind and the setup method must both be recorded")

    def inventory_checks(inventory, label, port_, allow_empty=False):
        if not (isinstance(inventory, dict) and inventory.get("source") == INVENTORY_SOURCE
                and inventory.get("method") == NETSTAT_METHOD):
            add("collision-inventory-not-netstat", "{}: the inventory is not the full netstat parse".format(label))
            return None
        if not _valid_inventory(inventory, port_, allow_empty):
            add("collision-inventory-malformed", "{}: the inventory is malformed, duplicated or names another "
                "port".format(label))
            return None
        return sorted(inventory["owners"])

    owners = inventory_checks(probe.get("inventory"), "probe", port)
    if owners is not None and len(owners) < 2:
        add("collision-not-a-collision", "the inventory shows {} listener(s) on port {}".format(len(owners), port))
    if owners is not None:
        discovery = _dict(probe.get("discovery"))
        rows = [u for u in _list(discovery.get("unusable")) if isinstance(u, dict) and u.get("port") == port]
        if not any(r.get("reason") in _COLLISION_LABELS and sorted(r.get("pids") or []) == owners for r in rows):
            add("collision-pid-unnamed", "discovery does not list the collision naming every inventory PID")
        if any(isinstance(u, dict) and u.get("port") == port for u in _list(discovery.get("usable"))):
            add("collision-discovery-offered-target", "discovery offered a target on the collision port")

        def refusal(entry, label, code_not_refused):
            if not isinstance(entry, dict) or entry.get("refused") is not True:
                add(code_not_refused, "{} was not refused before sending".format(label))
                return
            if entry.get("credits") is not False:
                add("collision-request-sent", "{} reply credits a verified process: a request was sent".format(label))
            if sorted(entry.get("pids") or []) != owners:
                add("collision-pid-unnamed", "{} refusal does not name every PID {}".format(label, owners))

        refusal(probe.get("default"), "the default call", "collision-default-not-refused")
        if probe.get("selected") is not None:
            refusal(probe.get("selected"), "the selected call", "collision-selected-not-refused")
    _engineer(record, "collision:setup", add, "collision")
    after = col.get("after")
    if not isinstance(after, dict):
        unit.absent("the teardown inventory was not captured")
    else:
        remaining = inventory_checks(after.get("inventory"), "after", port, allow_empty=True)
        if remaining is not None and len(remaining) >= 2:
            add("collision-cleanup-incomplete", "the collision is still present after the teardown: {}".format(remaining))
        _engineer(record, "collision:cleanup", add, "collision")
    if probe.get("setup_kind") == "auxiliary-routes-server":
        qualifications.append(
            "G5 collision was made with an auxiliary RoutesServer: it shows the production refusal on a real "
            "netstat collision, not automatic primary-port assignment by Revit (no primary-port assignment evidence)")


_NEVER_UNCERTAIN = ("unknown", "not-sent", "unverified")


def _g6_persist_lost(previous_kind, previous_value, next_reply):
    """True/False when the next write's old value shows whether the previous write persisted; None if unknown."""
    if previous_kind not in ("success", "conflict", "unknown") or next_reply.get("kind") != "success":
        return None
    return next_reply.get("old_value") != previous_value


def _unit_g6(record, unit):
    g6 = _dict(record.get("g6"))
    info = {"hypothesis": None, "observations": {}}
    if not g6:
        unit.absent("the G6 section was never captured")
        return info
    add = unit.stop
    identity = _section_process(g6, add, "g6-process-unverified", "g6")
    if not _nonblank(_dict(g6.get("disposable")).get("words")):
        add("g6-disposable-unattested", "the engineer never attested that the documents are disposable copies")
    steps, overlap = _dict(g6.get("steps")), _dict(g6.get("overlap"))
    jobs = _dict(overlap.get("jobs"))
    writes = []  # (label, reply)
    for step in G6_WRITE_STEPS:
        entry = steps.get(step)
        if not isinstance(entry, dict):
            unit.absent("write step {} was not captured".format(step))
            continue
        writes.append((step, _dict(entry.get("reply"))))
        if _count_sends(record, "g6", "set_parameter", "g6:" + step) != 1:
            add("g6-send-count", "step {} is sent exactly once".format(step))
    if not jobs:
        unit.absent("the overlapped step was not captured")
    else:
        for key in ("a", "b"):
            job = _dict(jobs.get(key))
            writes.append(("overlap_" + key, _dict(job.get("reply"))))
        if _count_sends(record, "g6", "set_parameter", "g6:overlap") != 2:
            add("g6-send-count", "the overlapped step sends exactly two writes")
        read = _dict(_dict(jobs.get("read")).get("reply"))
        if not (read.get("ok") is True and _same_process(read, identity)):
            add("g6-listing-unusable", "the overlapped read did not return a usable listing from the recorded process")
    for label, reply in writes:
        if _uncertain_labelled(reply):
            add("g6-unknown-labelled-verified", "{}: a {} outcome is labelled with a verified process or "
                "document".format(label, reply.get("kind")))
        if reply.get("kind") in ("refused", "error"):
            add("g6-reply-unexpected", "{}: the write was refused or failed ({!r})".format(label, reply.get("http_status")))
    for step in G6_WRITE_STEPS + ("overlap",):
        if step in steps or (step == "overlap" and jobs):
            _engineer(record, "g6:" + step, add, "g6")
    _unit_copies(record, "g6", identity, add,
                 set(r.get("document") for _l, r in writes if r.get("kind") == "success"))
    if unit.problems or unit.missing:
        return info
    if not isinstance(g6.get("final"), dict):
        unit.absent("the final listener inventory was not captured")
        return info
    final_owners = _dict(_dict(g6["final"]).get("listener")).get("owners")
    obs = {"identity_mismatch": False, "unknown_outcome": False, "rolled_back": False, "sequential_loss": False,
           "overlap_loss": False, "cross_wired": False}
    for _label, reply in writes:
        kind = reply.get("kind")
        if kind == "conflict":
            obs["identity_mismatch"] = True
        elif kind in ("success", "rolled-back") and identity is not None and reply.get("identity") != identity:
            obs["identity_mismatch"] = True
        if kind in _NEVER_UNCERTAIN:
            obs["unknown_outcome"] = True
        if kind == "rolled-back":
            obs["rolled_back"] = True
    seq = dict((s, _dict(steps.get(s))) for s in G6_WRITE_STEPS)
    chain = (("seq1", "seq2"), ("seq2", "seq_readback"))
    for earlier, later in chain:
        lost = _g6_persist_lost(_dict(seq[earlier].get("reply")).get("kind"),
                                _dict(seq[earlier].get("request")).get("value"), _dict(seq[later].get("reply")))
        obs["sequential_loss"] = obs["sequential_loss"] or lost is True
    for key, readback in (("a", "ov_readback_a"), ("b", "ov_readback_b")):
        job = _dict(jobs.get(key))
        request, reply = _dict(job.get("request")), _dict(job.get("reply"))
        if reply.get("kind") == "success" and (
                reply.get("element_id") != request.get("element_id")
                or reply.get("parameter_name") != request.get("parameter_name")
                or reply.get("new_value") != request.get("value")):
            obs["cross_wired"] = True
        lost = _g6_persist_lost(reply.get("kind"), request.get("value"), _dict(seq[readback].get("reply")))
        obs["overlap_loss"] = obs["overlap_loss"] or lost is True
    info["observations"] = obs
    lost_any = obs["sequential_loss"] or obs["overlap_loss"]
    sole = isinstance(final_owners, list) and identity is not None and final_owners == [identity["pid"]]
    if obs["identity_mismatch"]:
        info["hypothesis"] = "confirmed" if lost_any else "inconclusive"
    elif obs["unknown_outcome"] or not sole:
        info["hypothesis"] = "inconclusive"
    else:
        info["hypothesis"] = "ruled-out"
    if info["hypothesis"] == "inconclusive":
        add(R_G6_INCONCLUSIVE, "the measured identities and write outcomes do not settle the wrong-process hypothesis "
            "(unknown outcome, a conflicting reply whose write persisted, or the port owner not verified at the end)")
    return info


def _informational(record, prior_g34):
    info = {}
    thread = _dict(record.get("http_thread"))
    status, model = _dict(thread.get("status")), _dict(thread.get("model_info"))
    if status and model:
        good = _complete_identity(status.get("identity")) and _complete_identity(model.get("identity"))
        info["http_thread"] = {"status": SLOT_OBSERVED if good else STOP, "reasons": [] if good else [
            "an HTTP-thread route did not carry a complete process identity"]}
    else:
        info["http_thread"] = {"status": NOT_RUN, "reasons": []}
    jobs = _list(_dict(_dict(record.get("two")).get("overlap")).get("jobs"))
    if not jobs:
        info["serialization"] = {"status": NOT_RUN, "reasons": []}
    else:
        bad = [j for j in jobs if not (isinstance(j, dict) and _dict(j.get("reply")).get("identity") == j.get("expected_identity")
                                       and _complete_identity(j.get("expected_identity")))]
        info["serialization"] = {"status": STOP if bad else SLOT_OBSERVED, "reasons": [
            _reason("two-cross-wired", "{} overlapped call(s) were answered by a process other than their "
                    "target".format(len(bad)))] if bad else []}
    outcome = g4_case_outcomes(prior_g34) if isinstance(prior_g34, dict) else {}
    word = outcome.get("saved_workshared", NOT_RUN)
    info["workshared_refusal"] = {"status": {"observed": SLOT_OBSERVED, "stop": STOP}.get(word, NOT_RUN), "reasons": []}
    return info


def _acc_evaluate(record):
    """Every unit of one record: units, record-level reasons, authorization states and side tables."""
    reasons = []
    if record.get("live") is not True:
        reasons.append(_reason(R_NOT_LIVE, "record is not marked live: an offline record never passes"))
    if record.get("synthetic") is not False:
        reasons.append(_reason(R_SYNTHETIC, "record is not explicitly non-synthetic"))
    if record.get("schema") != ACC_SCHEMA:
        reasons.append(_reason(R_SCHEMA, "record schema is not {}".format(ACC_SCHEMA)))
    _check_sent_calls(record, reasons)
    states, flag_problems = _policy(record, reasons)
    units = dict((name, _Unit(name)) for name in UNITS)
    qualifications = [
        "Per-process locks do not establish cross-session Revit handler synchronization; backlog 999.1 stays open",
        "D-15: both execute surfaces stay a trusted arbitrary-code exception outside every document-confinement claim",
    ]
    _unit_prior(record, units)
    _unit_g2(record, units["g2"])
    _unit_two(record, units["two"])
    _unit_mutation(record, units)
    _unit_collision(record, units["g5"], qualifications)
    g6 = _unit_g6(record, units["g6"])
    for flag, problems in flag_problems.items():
        section = [s for s, f in SECTION_FLAG.items() if f == flag][0]
        targets = {"mutation": ("mut_c2", "mut_c6", "mut_c8"), "g6": ("g6",), "collision": ("g5",)}[section]
        for text in problems:
            for name in targets:
                if text not in units[name].problems:
                    units[name].problems.append(text)
    prior_g34 = _dict(_dict(record.get("prior")).get("g34")).get("record")
    return {"units": units, "reasons": reasons, "auth": states, "qualifications": qualifications, "g6": g6,
            "informational": _informational(record, prior_g34)}


def _combine(statuses):
    if STOP in statuses:
        return STOP
    return NOT_RUN if NOT_RUN in statuses else SLOT_OBSERVED


def _acc_result(evaluated, base_reasons=None):
    units = dict((name, unit.as_dict()) for name, unit in evaluated["units"].items())
    reasons = list(evaluated["reasons"]) + list(base_reasons or [])
    criteria, open_lines = {}, []
    for criterion in CRITERIA:
        status = _combine([units[u]["status"] for u in CRITERION_UNITS[criterion]])
        criteria[criterion] = {
            "status": status, "text": CRITERION_TEXT[criterion], "units": list(CRITERION_UNITS[criterion]),
            "reasons": [r for u in CRITERION_UNITS[criterion] for r in units[u]["reasons"]]}
        if status != SLOT_OBSERVED:
            open_lines.append("{} ({}) {}: {}".format(criterion, ", ".join(CRITERION_REQUIREMENTS[criterion]),
                                                       status, CRITERION_TEXT[criterion]))
    gates = dict((g, units[g]) for g in GATES)
    for gate in GATES:
        if gate == "g6" and gates[gate]["status"] != SLOT_OBSERVED:
            open_lines.append("AMBIG-04: G6 {} - the param-write-rolls-back hypothesis has no recorded outcome; "
                              "AMBIG-04 stays open".format(gates[gate]["status"]))
        elif gates[gate]["status"] != SLOT_OBSERVED:
            open_lines.append("{}: {}".format(gate.upper(), gates[gate]["status"] + " - " + GATE_TEXT[gate]))
    accepted = (not reasons and all(c["status"] == SLOT_OBSERVED for c in criteria.values())
                and all(g["status"] == SLOT_OBSERVED for g in gates.values())
                and all(units[u]["status"] == SLOT_OBSERVED for u in UNITS))
    return {"verdict": ACCEPT_ELIGIBLE if accepted else STOP, "approval": APPROVAL, "criteria": criteria,
            "gates": gates, "units": units, "authorizations": dict(evaluated["auth"]), "reasons": reasons,
            "open": open_lines, "g6": evaluated["g6"], "informational": evaluated["informational"],
            "qualifications": list(evaluated["qualifications"])}


def _acc_blank_result(reasons):
    units = dict((name, _Unit(name)) for name in UNITS)
    for unit in units.values():
        unit.absent("no usable record")
    return _acc_result({"units": units, "reasons": [], "auth": dict((f, "not-authorized") for f in AUTH_FLAGS),
                        "qualifications": [], "g6": {"hypothesis": None, "observations": {}},
                        "informational": {k: {"status": NOT_RUN, "reasons": []}
                                          for k in ("http_thread", "serialization", "workshared_refusal")}},
                       base_reasons=reasons)


def classify_phase2_acceptance(record):
    """The per-criterion and per-gate table plus an overall verdict; never raises, never an approval.

    The verdict is accept-eligible only when every one of the nine criteria and the six
    gates is observed, every authorization is in order and no record-level rule is
    broken. Anything else, including an absent, synthetic or contradictory record, is stop.
    """
    try:
        if not isinstance(record, dict) or not record:
            return _acc_blank_result([_reason(R_NO_RECORD, "no evidence record (missing, empty or not an object)")])
        return _acc_result(_acc_evaluate(record))
    except Exception as ex:  # a classifier bug must read as STOP, not as a pass
        return _acc_blank_result([_reason(R_CLASSIFIER_ERROR, "{}: {}".format(type(ex).__name__, ex))])


# ------------------------------------------------------------ acceptance commands

ACC_USAGE = (
    "acceptance commands: phase2-template | phase2-start --out ACC.json | "
    "phase2-authorize --in ACC --flag mutation_authorized|g6_authorized|collision_authorized --words TEXT | "
    "phase2-attach --in ACC --kind identity_recheck|g34 --record RAW.json | "
    "phase2-observe --in ACC --step STEP --ui WORD [--dialog none|input-required] [--value-seen TEXT] | "
    "phase2-classify ACC.json | "
    "g2-list --in ACC --step pair|after_close|after_replacement [--port N] | "
    "g2-stale --in ACC --step after_close|after_replacement --number N [--port N] | "
    "two-discover --in ACC | two-default --in ACC | two-status --in ACC --which 1|2 | "
    "two-list --in ACC --which 1|2 | two-overlap --in ACC | http-thread --in ACC [--port N] | "
    "mut-start --in ACC --disposable yes [--port N] | mut-copy --in ACC --number N [--sha256 HEX] | "
    "mut-case --in ACC --case CASE [--number N] --element-id E --param P --value V | "
    "mut-activate --in ACC --number N | mut-finish --in ACC [--sha256-after 1=HEX,2=HEX] | "
    "collision-probe --in ACC --port P --setup-kind second-revit-primary-port|auxiliary-routes-server "
    "--setup-method TEXT [--selector S] | collision-after --in ACC --port P | "
    "g6-start --in ACC --disposable yes [--port N] | g6-copy --in ACC --number N [--sha256 HEX] | "
    "g6-write --in ACC --step seq1|seq2|seq_readback|ov_readback_a|ov_readback_b --number N "
    "[--element-id E --param P --value V] | g6-overlap --in ACC --number N --a E:P:V --b E:P:V | "
    "g6-finish --in ACC [--sha256-after 1=HEX]"
)


def _acc_stop(text):
    print("{} approval={}: {}".format(SENTINEL_ACC_STOP, APPROVAL, text))
    return 1


def _acc_pending(text):
    print("{} approval={}: {}".format(SENTINEL_ACC_PENDING, APPROVAL, text))
    return 0


def _acc_usage():
    print(ACC_USAGE)
    return 2


def _acc_load(path):
    """(record, None) or (None, message) for an acceptance record started by phase2-start."""
    try:
        record = _read_record(path)
    except (OSError, ValueError) as ex:
        return None, "cannot read the acceptance record {!r}: {}".format(path, ex)
    if not (isinstance(record, dict) and record.get("schema") == ACC_SCHEMA and isinstance(record.get("sent_calls"), list)):
        return None, "{!r} is not an acceptance record started by phase2-start".format(path)
    for key, kind in (("engineer", dict), ("copies", list), ("authorizations", dict), ("prior", dict)):
        if not isinstance(record.get(key), kind):
            record[key] = kind()
    for key in ("g2", "two", "http_thread", "mutation", "collision", "g6"):
        if not isinstance(record.get(key), dict):
            record[key] = {}
    return record, None


def _acc_enter(values, section=None):
    """Common prologue: (record, None) or (None, exit code). A flagged section needs its flag."""
    path = values["--in"]
    if not _outside_repo(path):
        print("refused: raw captures must stay outside the repository ({})".format(path))
        return None, 2
    record, problem = _acc_load(path)
    if problem:
        return None, _acc_stop(problem)
    flag = SECTION_FLAG.get(section)
    if flag is not None and _auth_state(record["authorizations"].get(flag))[0] != "authorized":
        return None, _acc_stop(
            "{} is not set. Nothing was sent. The user's explicit words must be recorded by the engineer with "
            "phase2-authorize before section {} may run.".format(flag, section))
    return record, None


def _acc_run(capture):
    try:
        return asyncio.run(capture()), None
    except _BenchProblem as ex:
        return None, _acc_stop(str(ex))
    except Exception as ex:
        return None, _acc_stop("live capture failed ({}: {})".format(type(ex).__name__, ex))


def _acc_save(path, record, sent):
    record["sent_calls"] = list(record["sent_calls"]) + list(sent)
    record["recorded_at"] = _now()
    _write_record(path, record)


def _acc_options(args, names, required):
    values = _options(args, names)
    if values is None or any(name not in values for name in required) or _port_option(values) is None:
        return None
    return values


def _identity_text(identity):
    return "PID {} port {} session {}".format(identity["pid"], identity["actual_port"], identity["session_token"])


class _Free(object):
    """One MCP server process and a recording call path that names no process of its own."""

    def __init__(self, session, section):
        self.session = session
        self.section = section
        self.sent = []

    async def call(self, tool, arguments, step):
        self.sent.append(acc_sent_call_entry(self.section, tool, step))
        result = await self.session.call_tool(tool, dict(arguments))
        return "\n".join(getattr(item, "text", "") for item in result.content)


@contextlib.asynccontextmanager
async def _free(section):
    async with _server(DEFAULT_PORT) as session:
        yield _Free(session, section)


def _collision_inventory(port):
    """The full netstat inventory for one port, as bridge.listener_snapshot reads it."""
    inventory = dict(collect_listener_owners(port))
    inventory["method"] = NETSTAT_METHOD
    return inventory


def _positive_number(values, key="--number"):
    return _positive_int(values.get(key))


# ---- phase2-template / start / authorize / attach / observe / classify


def _cmd_phase2_template(args):
    if args:
        return _acc_usage()
    print(json.dumps(acceptance_template(), indent=2))
    return 0


def _cmd_phase2_start(args):
    values = _options(args, ("--out",))
    if values is None or "--out" not in values:
        return _acc_usage()
    out = values["--out"]
    if not _outside_repo(out):
        print("refused: raw captures must stay outside the repository ({})".format(out))
        return 2
    if os.path.exists(out):
        print("refused: {} already exists; records are never overwritten".format(out))
        return 2
    record = acceptance_template()
    record.update({"live": True, "synthetic": False, "recorded_at": _now(), "route_namespace": route_namespace()})
    _write_record(out, record)
    return _acc_pending("acceptance record started in {}; flags are all unset. Run the non-mutating sections "
                        "first; set a flag only from the user's own words with phase2-authorize".format(out))


def _cmd_phase2_authorize(args):
    values = _options(args, ("--in", "--flag", "--words"))
    if (values is None or any(k not in values for k in ("--in", "--flag", "--words"))
            or values["--flag"] not in AUTH_FLAGS or len(values["--words"].strip()) < AUTH_MIN_WORDS):
        return _acc_usage()
    path = values["--in"]
    if not _outside_repo(path):
        print("refused: raw captures must stay outside the repository")
        return 2
    record, problem = _acc_load(path)
    if problem:
        return _acc_stop(problem)
    done, message = apply_authorization(record, values["--flag"], values["--words"])
    if not done:
        print("refused: " + message)
        return 2
    _write_record(path, record)
    item = record["authorizations"][values["--flag"]]
    return _acc_pending("{} recorded at {} with the user's words: {}".format(values["--flag"], item["at"], item["words"]))


ATTACH_SCHEMAS = {"identity_recheck": SCHEMA, "g34": G34_SCHEMA}


def _cmd_phase2_attach(args):
    values = _options(args, ("--in", "--kind", "--record"))
    if (values is None or any(k not in values for k in ("--in", "--kind", "--record"))
            or values["--kind"] not in ATTACH_SCHEMAS):
        return _acc_usage()
    if not _outside_repo(values["--in"]) or not _outside_repo(values["--record"]):
        print("refused: raw captures must stay outside the repository")
        return 2
    record, problem = _acc_load(values["--in"])
    if problem:
        return _acc_stop(problem)
    kind = values["--kind"]
    if record["prior"].get(kind) is not None:
        print("refused: a {} record is already attached; start a new acceptance record to attach another".format(kind))
        return 2
    try:
        prior = _read_record(values["--record"])
    except (OSError, ValueError) as ex:
        return _acc_stop("cannot read the prior record {!r}: {}".format(values["--record"], ex))
    if not (isinstance(prior, dict) and prior.get("schema") == ATTACH_SCHEMAS[kind]):
        return _acc_stop("{!r} is not a {} record (schema {})".format(values["--record"], kind, ATTACH_SCHEMAS[kind]))
    record["prior"][kind] = {"record": prior, "attached_at": _now(),
                             "source_name": os.path.basename(values["--record"])}
    _write_record(values["--in"], record)
    return _acc_pending("{} record attached (recorded at {}); it is re-classified, never trusted as a verdict".format(
        kind, prior.get("recorded_at")))


def _acc_captured(record, step):
    kind, _, name = step.partition(":")
    if kind == "g2":
        return name in _dict(record["g2"].get("steps"))
    if kind == "two":
        return isinstance(record["two"].get("discovery"), dict)
    if kind == "mut":
        if name == "activation":
            return isinstance(record["mutation"].get("activation"), dict)
        return name in _dict(record["mutation"].get("cases"))
    if kind == "collision":
        return isinstance(record["collision"].get("after" if name == "cleanup" else "probe"), dict)
    if kind == "g6":
        if name == "overlap":
            return isinstance(record["g6"].get("overlap"), dict)
        return name in _dict(record["g6"].get("steps"))
    return False


def _cmd_phase2_observe(args):
    values = _options(args, ("--in", "--step", "--ui", "--dialog", "--value-seen"))
    if values is None or any(k not in values for k in ("--in", "--step", "--ui")):
        return _acc_usage()
    step, ui = values["--step"], values["--ui"]
    dialog, seen = values.get("--dialog"), values.get("--value-seen")
    if (step not in OBS_EXPECTED or ui not in UI_WORDS or (dialog is not None and dialog not in DIALOG_WORDS)
            or (seen is not None and not step.startswith("g6:"))):
        return _acc_usage()
    if not _outside_repo(values["--in"]):
        print("refused: raw captures must stay outside the repository")
        return 2
    record, problem = _acc_load(values["--in"])
    if problem:
        return _acc_stop(problem)
    if not _acc_captured(record, step):
        return _acc_stop("step {} has not been captured in this record; run its capture command first".format(step))
    previous = record["engineer"].get(step)
    if isinstance(previous, dict) and previous.get("ui") is not None:
        record.setdefault("engineer_superseded", []).append(dict(previous, step=step))
    record["engineer"][step] = {"ui": ui, "dialog_required_input": DIALOG_WORDS[dialog] if dialog is not None else None,
                                "value_seen": seen, "at": _now(), "source": AUTH_SOURCE}
    _write_record(values["--in"], record)
    return _acc_pending("observation recorded for {}: ui={} dialog={}".format(step, ui, dialog))


def acc_summary_lines(record, result):
    lines = []
    for criterion in CRITERIA:
        slot = result["criteria"][criterion]
        lines.append("CRITERION {}: {} ({}) {}".format(criterion, slot["status"],
                                                       ", ".join(CRITERION_REQUIREMENTS[criterion]), slot["text"]))
    for gate in GATES:
        lines.append("GATE {}: {} - {}".format(gate, result["gates"][gate]["status"], GATE_TEXT[gate]))
    for name in ("two", "mut_c2", "mut_c6", "mut_c8"):
        lines.append("UNIT {}: {}".format(name, result["units"][name]["status"]))
    for flag in AUTH_FLAGS:
        item = _dict(_dict(record).get("authorizations")).get(flag)
        detail = ""
        if isinstance(item, dict) and item.get("value") is True:
            detail = " at {} words: {}".format(item.get("at"), item.get("words"))
        lines.append("AUTH {}: {}{}".format(flag, result["authorizations"].get(flag), detail))
    for name, slot in result["informational"].items():
        lines.append("INFO {}: {}".format(name, slot["status"]))
    g6 = result["g6"]
    if g6.get("hypothesis"):
        lines.append("G6 hypothesis (wrong process answered): {} observations={}".format(
            g6["hypothesis"], json.dumps(g6["observations"], sort_keys=True)))
    for text in result["qualifications"]:
        lines.append("NOTE " + text)
    return lines


def acc_report(record):
    """Print the classification of an acceptance record; the sentinel only for an accept-eligible live record."""
    result = classify_phase2_acceptance(record)
    for line in acc_summary_lines(record, result):
        print(line)
    print("verdict={}".format(result["verdict"]))
    for line in result["open"]:
        print("OPEN " + line)
    for reason in result["reasons"]:
        print("  - " + reason)
    for name in UNITS:
        for reason in result["units"][name]["reasons"]:
            print("  - {}: {}".format(name, reason))
    live = isinstance(record, dict) and record.get("live") is True and record.get("synthetic") is False
    if result["verdict"] == ACCEPT_ELIGIBLE and live:
        print("{} approval={}".format(SENTINEL_ACC_OBSERVED, APPROVAL))
        return 0
    print("{} approval={}".format(SENTINEL_ACC_STOP, APPROVAL))
    return 1


def _cmd_phase2_classify(args):
    if len(args) != 1:
        return _acc_usage()
    try:
        record = _read_record(args[0])
    except (OSError, ValueError) as ex:
        print("cannot read evidence file {!r}: {}".format(args[0], ex))
        print("{} approval={}".format(SENTINEL_ACC_STOP, APPROVAL))
        return 1
    return acc_report(record)


# ---- G2: same-title pair, close, replacement, stale-token retry


def _cmd_g2_list(args):
    values = _acc_options(args, ("--in", "--step", "--port"), ("--in", "--step"))
    if values is None or values["--step"] not in G2_LIST_STEPS:
        return _acc_usage()
    record, code = _acc_enter(values)
    if code is not None:
        return code
    step, port = values["--step"], _port_option(values)
    g2 = record["g2"]
    steps = g2.setdefault("steps", {})
    if step in steps:
        print("refused: listing {} is already captured; start a new record to repeat it".format(step))
        return 2
    process = g2.get("process")
    if step != "pair" and not isinstance(process, dict):
        return _acc_stop("capture the pair listing first; nothing was sent")

    async def capture():
        async with _bound(port, process["identity"] if process else None, "g2") as bound:
            listing = await bound.listing("g2:" + step)
            return bound.identity, bound.selector, bound.listener, bound.sent, listing

    result, code = _acc_run(capture)
    if code is not None:
        return code
    identity, selector, listener, sent, listing = result
    if not listing["ok"]:
        return _acc_stop("list_documents returned no usable listing: {}".format(listing.get("text")))
    if process is None:
        g2["process"] = {"identity": identity, "selector": selector, "listener": listener, "at": _now()}
    steps[step] = listing
    _acc_save(values["--in"], record, sent)
    print("PROCESS {}".format(_identity_text(identity)))
    print("OPEN DOCUMENTS ({}; numbers are for g2-stale --number):".format(step))
    _print_listing(listing)
    return _acc_pending("listing {} captured; now LOOK at the Revit window and record it with phase2-observe "
                        "--step g2:{} --ui {}".format(step, step, OBS_EXPECTED["g2:" + step]))


def _cmd_g2_stale(args):
    values = _acc_options(args, ("--in", "--step", "--number", "--port"), ("--in", "--step", "--number"))
    if values is None or values["--step"] not in G2_STALE_STEPS or _positive_number(values) is None:
        return _acc_usage()
    record, code = _acc_enter(values)
    if code is not None:
        return code
    step, number, port = values["--step"], _positive_number(values), _port_option(values)
    g2 = record["g2"]
    pair = _dict(g2.get("steps")).get("pair")
    if not isinstance(g2.get("process"), dict) or not _usable_listing(pair):
        return _acc_stop("capture the pair listing first (g2-list --step pair); nothing was sent")
    stale = g2.setdefault("stale", {})
    if step in stale:
        print("refused: stale-token retry {} is already captured".format(step))
        return 2
    documents = pair["documents"]
    if number > len(documents):
        return _acc_stop("--number {} is beyond the {} documents of the pair listing; nothing was sent".format(
            number, len(documents)))
    closed = documents[number - 1]
    token = closed["document"]
    label = "g2:stale:" + step

    async def capture():
        async with _bound(port, g2["process"]["identity"], "g2") as bound:
            fresh = await bound.listing(label)
            if token in _token_set(fresh):
                raise _BenchProblem("selector {} is still listed: nothing was closed, so no stale read was sent. "
                                    "Close document {} in Revit first.".format(token, number))
            text = await bound.call("read_document_summary", {"document": token}, label)
            return fresh, build_read_entry("read_document_summary", text), bound.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    fresh, reply, sent = result
    stale[step] = {"stale_token": token, "from_index": number, "closed_title": closed.get("title"),
                   "closed_path": closed.get("path"), "listing": fresh, "reply": reply, "at": _now()}
    _acc_save(values["--in"], record, sent)
    print("STALE READ {} token={} kind={} http={} code={}".format(
        step, token, reply.get("kind"), reply.get("http_status"), reply.get("error_code")))
    return _acc_pending("stale-token retry {} captured".format(step))


# ---- two Revit processes under one entry


def _two_entry(record, which):
    usable = [u for u in _list(_dict(record["two"].get("discovery")).get("usable")) if isinstance(u, dict)]
    index = int(which) - 1
    return usable[index] if 0 <= index < len(usable) else None


def _two_precheck(record, which):
    """(entry, inventory) of the discovered process, or (None, message) when nothing may be sent."""
    entry = _two_entry(record, which)
    if entry is None:
        return None, "discovery shows no usable process number {}; run two-discover first. Nothing was sent.".format(which)
    try:
        parsed = _bridge().parse_target(entry.get("selector"))
    except (ValueError, TypeError):
        return None, "the discovered selector of process {} does not parse; nothing was sent".format(which)
    if (parsed["pid"], parsed["port"], parsed["session_token"]) != (entry["pid"], entry["port"], entry["session_token"]):
        return None, "the discovered selector of process {} does not match its entry; nothing was sent".format(which)
    inventory = collect_listener_owners(entry["port"])
    if inventory["owners"] != [entry["pid"]]:
        return None, ("listener inventory {} does not show PID {} as sole owner of port {}; nothing was "
                      "sent".format(inventory["owners"], entry["pid"], entry["port"]))
    return entry, inventory


def _cmd_two_discover(args):
    values = _acc_options(args, ("--in",), ("--in",))
    if values is None:
        return _acc_usage()
    record, code = _acc_enter(values)
    if code is not None:
        return code
    if "discovery" in record["two"]:
        print("refused: discovery is already captured; start a new record to repeat it")
        return 2

    async def capture():
        async with _free("two") as free:
            return await free.call("discover_revit_targets", {}, "two:discover"), free.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    text, sent = result
    entry = dict(parse_discovery_text(text), text=text, at=_now())
    record["two"]["discovery"] = entry
    _acc_save(values["--in"], record, sent)
    for index, u in enumerate(entry["usable"], 1):
        print("{}. PID {} port {} session {} document_open={}".format(
            index, u["pid"], u["port"], u["session_token"], u["document_open"]))
    for u in entry["unusable"]:
        print("UNUSABLE port {} PIDs {} ({})".format(u["port"], u["pids"], u["reason"]))
    return _acc_pending("discovery captured: {} usable process(es); two are needed".format(len(entry["usable"])))


def _cmd_two_default(args):
    values = _acc_options(args, ("--in",), ("--in",))
    if values is None:
        return _acc_usage()
    record, code = _acc_enter(values)
    if code is not None:
        return code
    if not isinstance(record["two"].get("discovery"), dict):
        return _acc_stop("run two-discover first; nothing was sent")
    if "default" in record["two"]:
        print("refused: the default refusal is already captured")
        return 2

    async def capture():
        async with _free("two") as free:
            return await free.call("get_revit_status", {}, "two:default"), free.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    text, sent = result
    entry = dict(parse_refusal_text(text), text=text, at=_now())
    record["two"]["default"] = entry
    _acc_save(values["--in"], record, sent)
    print("DEFAULT CALL refused={} credits_a_process={} candidates={}".format(
        entry["refused"], entry["credits"], len(entry["candidates"])))
    return _acc_pending("the call without a target was captured; it must be refused with both candidates")


def _cmd_two_selected(args, tool, key):
    values = _acc_options(args, ("--in", "--which"), ("--in", "--which"))
    if values is None or values["--which"] not in ("1", "2"):
        return _acc_usage()
    record, code = _acc_enter(values)
    if code is not None:
        return code
    which = values["--which"]
    if which in _dict(record["two"].get(key)):
        print("refused: {} of process {} is already captured".format(key, which))
        return 2
    entry, inventory = _two_precheck(record, which)
    if entry is None:
        return _acc_stop(inventory)

    async def capture():
        async with _free("two") as free:
            return await free.call(tool, {"target": entry["selector"]}, "two:{}:{}".format(key, which)), free.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    text, sent = result
    if key == "status":
        parsed = parse_status_text(text)
        record["two"].setdefault("status", {})[which] = {
            "kind": parsed["kind"], "identity": parsed["identity"], "selector": entry["selector"],
            "at": _now(), "text": text}
        print("STATUS {} kind={} identity={}".format(which, parsed["kind"], parsed["identity"]))
    else:
        listing = build_listing_entry(text)
        record["two"].setdefault("list", {})[which] = listing
        print("DOCUMENTS of process {}:".format(which))
        _print_listing(listing)
    record["two"].setdefault("listeners", {}).setdefault(which, inventory)
    _acc_save(values["--in"], record, sent)
    return _acc_pending("{} of process {} captured through its own selector".format(key, which))


def _cmd_two_overlap(args):
    values = _acc_options(args, ("--in",), ("--in",))
    if values is None:
        return _acc_usage()
    record, code = _acc_enter(values)
    if code is not None:
        return code
    if "overlap" in record["two"]:
        print("refused: the overlap is already captured")
        return 2
    entries = []
    for which in ("1", "2"):
        entry, inventory = _two_precheck(record, which)
        if entry is None:
            return _acc_stop(inventory)
        entries.append(entry)

    async def capture():
        async with _free("two") as free:
            async def job(entry):
                started = _now()
                text = await free.call("list_documents", {"target": entry["selector"]}, "two:overlap:{}".format(entry["port"]))
                return {"which": entry["port"], "expected_identity": {
                    "pid": entry["pid"], "actual_port": entry["port"], "session_token": entry["session_token"],
                    "revit_version": entry["revit_version"]},
                    "started_at": started, "finished_at": _now(), "reply": build_listing_entry(text)}

            jobs = await asyncio.gather(*[job(e) for e in (entries[0], entries[0], entries[1], entries[1])])
            return list(jobs), free.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    jobs, sent = result
    record["two"]["overlap"] = {"jobs": jobs, "at": _now()}
    _acc_save(values["--in"], record, sent)
    return _acc_pending("{} overlapped listings captured (informational: per-process serialization is not provable "
                        "from outside)".format(len(jobs)))


def _cmd_http_thread(args):
    values = _acc_options(args, ("--in", "--port"), ("--in",))
    if values is None:
        return _acc_usage()
    record, code = _acc_enter(values)
    if code is not None:
        return code
    if record["http_thread"].get("status") is not None:
        print("refused: the HTTP-thread routes are already captured")
        return 2
    port = _port_option(values)

    async def capture():
        async with _bound(port, None, "http_thread") as bound:
            status = await bound.call("get_revit_status", {}, "http:status")
            model = await bound.call("get_revit_model_info", {}, "http:model_info")
            return bound.identity, bound.listener, status, model, bound.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    identity, listener, status, model, sent = result
    parsed = parse_status_text(status)
    record["http_thread"] = {
        "process": {"identity": identity, "listener": listener, "at": _now()},
        "status": {"kind": parsed["kind"], "identity": parsed["identity"], "at": _now(), "text": status},
        "model_info": {"kind": "text", "identity": _verified_identity(model), "at": _now(), "text": model}}
    _acc_save(values["--in"], record, sent)
    return _acc_pending("the two HTTP-thread routes were read once (informational; not an acceptance gate)")


# ---- mutation and G6 sections (disposable copies only)


def _sec_registered(record, section, identity):
    return set(c.get("document") for c in record["copies"]
               if isinstance(c, dict) and c.get("section") == section and c.get("process_token") == identity["session_token"])


def _require_all_registered(listing, record, section, identity):
    unregistered = sorted(_token_set(listing) - _sec_registered(record, section, identity))
    if unregistered:
        raise _BenchProblem("open document(s) {} are not registered disposable copies of section {} (register each "
                            "with {}-copy); nothing was sent".format(unregistered, section, _sec_cmd(section)))


def _sec_cmd(section):
    return "mut" if section == "mutation" else "g6"


def _sec_prepare(values, section):
    record, code = _acc_enter(values, section)
    if code is not None:
        return None, None, code
    data = record[section]
    if not _complete_identity(_dict(data.get("process")).get("identity")):
        return None, None, _acc_stop("run {}-start first; nothing was sent".format(_sec_cmd(section)))
    return record, data, None


def _cmd_sec_start(args, section):
    values = _acc_options(args, ("--in", "--disposable", "--port"), ("--in", "--disposable"))
    if values is None or values["--disposable"] != "yes":
        return _acc_usage()
    record, code = _acc_enter(values, section)
    if code is not None:
        return code
    data = record[section]
    if data.get("process") is not None:
        print("refused: section {} is already started in this record".format(section))
        return 2
    port = _port_option(values)

    async def capture():
        async with _bound(port, None, section) as bound:
            listing = await bound.listing(_sec_cmd(section) + ":start")
            return bound.identity, bound.selector, bound.listener, bound.sent, listing

    result, code = _acc_run(capture)
    if code is not None:
        return code
    identity, selector, listener, sent, listing = result
    if not listing["ok"]:
        return _acc_stop("list_documents returned no usable listing: {}".format(listing.get("text")))
    data.update({"disposable": {"words": "yes", "at": _now(), "source": AUTH_SOURCE},
                 "process": {"identity": identity, "selector": selector, "listener": listener, "at": _now()},
                 "listing_0": listing})
    data.setdefault("cases" if section == "mutation" else "steps", {})
    _acc_save(values["--in"], record, sent)
    print("PROCESS {}".format(_identity_text(identity)))
    print("OPEN DOCUMENTS (register every one as a disposable copy with {}-copy --number N):".format(_sec_cmd(section)))
    _print_listing(listing)
    return _acc_pending("section {} started; every open document must be a disposable copy".format(section))


def _hex_option(values):
    typed = values.get("--sha256")
    if typed is None:
        return None, True
    typed = typed.strip().lower()
    return typed, _is_sha256(typed)


def _cmd_sec_copy(args, section):
    values = _acc_options(args, ("--in", "--number", "--sha256", "--port"), ("--in", "--number"))
    if values is None or _positive_number(values) is None or not _hex_option(values)[1]:
        return _acc_usage()
    record, data, code = _sec_prepare(values, section)
    if code is not None:
        return code
    number, typed, port = _positive_number(values), _hex_option(values)[0], _port_option(values)
    identity = data["process"]["identity"]

    async def capture():
        async with _bound(port, identity, section) as bound:
            listing = await bound.listing(_sec_cmd(section) + ":copy")
            return listing, bound.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    listing, sent = result
    if not listing["ok"] or number > len(listing["documents"]):
        return _acc_stop("--number {} is not an open document of a usable listing; nothing was registered".format(number))
    document = listing["documents"][number - 1]
    for c in record["copies"]:
        if c.get("section") == section and c.get("document") == document["document"] \
                and c.get("process_token") == identity["session_token"]:
            print("refused: document {} is already registered as a copy".format(document["document"]))
            return 2
    path = document.get("path")
    if not path:
        return _acc_stop("document {} was never saved: it has no file to hash, so it cannot be a recorded "
                         "disposable copy".format(number))
    if not _outside_repo(path):
        return _acc_stop("the file of document {} is inside the repository; a disposable copy lives elsewhere".format(number))
    computed = _sha256_file(path)
    if computed is not None and typed is not None and computed != typed:
        return _acc_stop("the typed SHA256 differs from the file's: refusing to register document {}".format(number))
    digest = computed if computed is not None else typed
    if digest is None:
        return _acc_stop("the file of document {} cannot be read; type its SHA256 (computed before Revit opened it) "
                         "with --sha256".format(number))
    record["copies"].append({
        "section": section, "document": document["document"], "title": document.get("title"), "path": path,
        "process_token": identity["session_token"], "sha256_before": digest,
        "sha256_before_source": "computed-by-procedure" if computed is not None else "engineer-typed",
        "sha256_after": None, "sha256_after_source": None, "registered_at": _now()})
    _acc_save(values["--in"], record, sent)
    count = len([c for c in record["copies"] if c.get("section") == section])
    print("COPY {} document={} path={} sha256={}".format(count, document["document"], path, digest))
    return _acc_pending("document {} registered as a disposable copy (hash recorded before any write)".format(number))


def _cmd_sec_finish(args, section):
    values = _acc_options(args, ("--in", "--sha256-after", "--port"), ("--in",))
    typed = {}
    if values is not None and values.get("--sha256-after"):
        for part in values["--sha256-after"].split(","):
            index, _, digest = part.partition("=")
            if not index.isdigit() or int(index) < 1 or not _is_sha256(digest.strip().lower()):
                return _acc_usage()
            typed[int(index)] = digest.strip().lower()
    if values is None:
        return _acc_usage()
    record, data, code = _sec_prepare(values, section)
    if code is not None:
        return code
    if data.get("final") is not None:
        print("refused: section {} is already finished".format(section))
        return 2
    port, identity = _port_option(values), data["process"]["identity"]

    async def capture():
        async with _bound(port, identity, section) as bound:
            return bound.identity, bound.listener, bound.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    final_identity, listener, sent = result
    copies = [c for c in record["copies"] if c.get("section") == section]
    for index, c in enumerate(copies, 1):
        computed = _sha256_file(c.get("path"))
        digest = computed if computed is not None else typed.get(index)
        c["sha256_after"] = digest
        c["sha256_after_source"] = None if digest is None else (
            "computed-by-procedure" if computed is not None else "engineer-typed")
        print("COPY {} document={} before={} after={} {}".format(
            index, c.get("document"), c.get("sha256_before"), digest,
            "unchanged" if digest == c.get("sha256_before") else "CHANGED OR UNKNOWN"))
    data["final"] = {"identity": final_identity, "listener": listener, "at": _now()}
    _acc_save(values["--in"], record, sent)
    return _acc_pending("section {} finished: process still {} and sole owner of its port".format(
        section, _identity_text(final_identity)))


def _cmd_mut_start(args):
    return _cmd_sec_start(args, "mutation")


def _cmd_g6_start(args):
    return _cmd_sec_start(args, "g6")


def _cmd_mut_copy(args):
    return _cmd_sec_copy(args, "mutation")


def _cmd_g6_copy(args):
    return _cmd_sec_copy(args, "g6")


def _cmd_mut_finish(args):
    return _cmd_sec_finish(args, "mutation")


def _cmd_g6_finish(args):
    return _cmd_sec_finish(args, "g6")


def _write_arguments(request):
    arguments = {"element_id": request["element_id"], "parameter_name": request["parameter_name"],
                 "value": request["value"]}
    if request.get("document") is not None:
        arguments["document"] = request["document"]
    return arguments


async def _send_write(bound, request, step):
    """One write, never retried; a lost reply is recorded as an unknown outcome, not as a failure."""
    try:
        text = await bound.call("set_parameter", _write_arguments(request), step)
    except Exception as ex:
        text = "Error: the request was sent but no reply was received ({}: {}); its outcome is unknown.".format(
            type(ex).__name__, ex)
    return build_mutation_entry(text)


async def _safe_listing(bound, step):
    try:
        return await bound.listing(step)
    except Exception as ex:
        return build_listing_entry("Error: {}: {}".format(type(ex).__name__, ex))


def _element_id(word):
    return int(word) if isinstance(word, str) and word.isdigit() and int(word) > 0 else None


def _cmd_mut_case(args):
    names = ("--in", "--case", "--number", "--element-id", "--param", "--value", "--port")
    values = _acc_options(args, names, ("--in", "--case", "--element-id", "--param", "--value"))
    if values is None or values["--case"] not in MUTATION_CASES or _element_id(values["--element-id"]) is None \
            or not values["--param"].strip():
        return _acc_usage()
    case = values["--case"]
    if (case in CASES_WITH_DOCUMENT) != ("--number" in values) or (
            "--number" in values and _positive_number(values) is None):
        return _acc_usage()
    record, data, code = _sec_prepare(values, "mutation")
    if code is not None:
        return code
    cases = data.setdefault("cases", {})
    if case in cases:
        print("refused: case {} is already captured; a write is never repeated".format(case))
        return 2
    number, port = _positive_number(values) if "--number" in values else None, _port_option(values)
    identity, step = data["process"]["identity"], "mut:" + case
    last_active = _dict(data.get("last_active")).get("document")
    request = {"element_id": _element_id(values["--element-id"]), "parameter_name": values["--param"],
               "value": values["--value"], "document": None}

    async def capture():
        async with _bound(port, identity, "mutation") as bound:
            before = await bound.listing(step)
            if not before["ok"] or before["active_count"] != 1:
                raise _BenchProblem("the listing is unusable or has no single active document; nothing was sent")
            _require_all_registered(before, record, "mutation", identity)
            docs, active = before["documents"], before["active_document"]
            target = None
            if number is not None:
                if number > len(docs):
                    raise _BenchProblem("--number {} is beyond the {} open documents; nothing was sent".format(number, len(docs)))
                target = docs[number - 1]["document"]
            wrong = None
            if case in ("active_named", "after_activation", "after_manual_switch") and target != active:
                wrong = "document {} is not the active document".format(number)
            elif case == "inactive_412" and target == active:
                wrong = "document {} is the active document; this case needs an inactive one".format(number)
            elif case == "one_document_default" and len(docs) != 1:
                wrong = "{} documents are open; this case needs exactly one".format(len(docs))
            elif case == "many_documents_refused" and len(docs) < 2:
                wrong = "{} document is open; this case needs several".format(len(docs))
            elif case == "after_activation":
                act = _dict(_dict(data.get("activation")).get("reply"))
                if not (act.get("activation") == "activated" and act.get("document") == target):
                    wrong = "no captured activation made document {} active (run mut-activate first)".format(number)
            elif case == "after_manual_switch" and (last_active is None or last_active == active):
                wrong = "the active document did not change by hand since the last capture ({})".format(last_active)
            if wrong:
                raise _BenchProblem(wrong + "; nothing was sent")
            req = dict(request, document=target)
            reply = await _send_write(bound, req, step)
            after = await _safe_listing(bound, step)
            return {"case": case, "step": step, "expect": "success" if case in (
                "active_named", "one_document_default", "after_activation", "after_manual_switch") else "refuse",
                "target_document": target, "request": req, "before_listing": before, "reply": reply,
                "after_listing": after, "previous_active": last_active}, bound.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    entry, sent = result
    cases[case] = entry
    if _usable_listing(entry["after_listing"]):
        data["last_active"] = {"document": entry["after_listing"]["active_document"], "at": _now()}
    _acc_save(values["--in"], record, sent)
    reply = entry["reply"]
    print("MUTATION {} request sent once: kind={} http={} code={} document={} identity={}".format(
        case, reply["kind"], reply.get("http_status"), reply.get("error_code"), reply.get("document"), reply.get("identity")))
    return _acc_pending("now LOOK at the Revit window and for any dialog, then record both with phase2-observe "
                        "--step {} --ui {} --dialog none".format(step, OBS_EXPECTED[step]))


def _cmd_mut_activate(args):
    values = _acc_options(args, ("--in", "--number", "--port"), ("--in", "--number"))
    if values is None or _positive_number(values) is None:
        return _acc_usage()
    record, data, code = _sec_prepare(values, "mutation")
    if code is not None:
        return code
    if data.get("activation") is not None:
        print("refused: the activation is already captured; it is never repeated")
        return 2
    number, port, identity = _positive_number(values), _port_option(values), data["process"]["identity"]

    async def capture():
        async with _bound(port, identity, "mutation") as bound:
            before = await bound.listing("mut:activation")
            if not before["ok"] or before["active_count"] != 1:
                raise _BenchProblem("the listing is unusable or has no single active document; nothing was sent")
            _require_all_registered(before, record, "mutation", identity)
            if number > len(before["documents"]):
                raise _BenchProblem("--number {} is beyond the open documents; nothing was sent".format(number))
            target = before["documents"][number - 1]
            if target["document"] == before["active_document"]:
                raise _BenchProblem("document {} is already the active document; nothing was sent".format(number))
            if not target["path"]:
                raise _BenchProblem("document {} has no saved path; activation is refused for it; nothing was "
                                    "sent".format(number))
            try:
                text = await bound.call("activate_document", {"document": target["document"]}, "mut:activation")
            except Exception as ex:
                text = "Error: {}: {}".format(type(ex).__name__, ex)
            after = await _safe_listing(bound, "mut:activation")
            return {"step": "mut:activation", "target_document": target["document"], "before_listing": before,
                    "reply": build_activation_entry(text), "after_listing": after}, bound.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    entry, sent = result
    data["activation"] = entry
    if _usable_listing(entry["after_listing"]):
        data["last_active"] = {"document": entry["after_listing"]["active_document"], "at": _now()}
    _acc_save(values["--in"], record, sent)
    print("ACTIVATION target={} kind={} activation={}".format(
        entry["target_document"], entry["reply"]["kind"], entry["reply"].get("activation")))
    return _acc_pending("now LOOK at the Revit window and for any dialog, then record both with phase2-observe "
                        "--step mut:activation --ui target-active --dialog none")


def _g6_request(record, data, step, values):
    """(request, error) of one G6 write step; readbacks reuse the chained write's own request."""
    steps = _dict(data.get("steps"))
    if step in ("seq1", "seq2"):
        request = {"element_id": _element_id(values.get("--element-id")), "parameter_name": values["--param"],
                   "value": values["--value"], "document": None}
        if step == "seq2":
            first = _dict(_dict(steps.get("seq1")).get("request"))
            if not first:
                return None, "seq1 is not captured yet; nothing was sent"
            if (first.get("element_id"), first.get("parameter_name")) != (request["element_id"], request["parameter_name"]) \
                    or first.get("value") == request["value"]:
                return None, "seq2 must write the same element and parameter as seq1 with a different value; nothing was sent"
        return request, None
    if step == "seq_readback":
        previous = _dict(_dict(steps.get("seq2")).get("request"))
        return (dict(previous) if previous else None), (None if previous else "seq2 is not captured yet; nothing was sent")
    job = _dict(_dict(_dict(data.get("overlap")).get("jobs")).get("a" if step.endswith("_a") else "b"))
    previous = _dict(job.get("request"))
    return (dict(previous) if previous else None), (None if previous else "the overlapped step is not captured yet; "
                                                    "nothing was sent")


def _cmd_g6_write(args):
    names = ("--in", "--step", "--number", "--element-id", "--param", "--value", "--port")
    values = _acc_options(args, names, ("--in", "--step", "--number"))
    if values is None or values["--step"] not in G6_WRITE_STEPS or _positive_number(values) is None:
        return _acc_usage()
    step = values["--step"]
    given = [k for k in ("--element-id", "--param", "--value") if k in values]
    if step in ("seq1", "seq2"):
        if len(given) != 3 or _element_id(values["--element-id"]) is None or not values["--param"].strip():
            return _acc_usage()
    elif given:
        return _acc_usage()
    record, data, code = _sec_prepare(values, "g6")
    if code is not None:
        return code
    steps = data.setdefault("steps", {})
    if step in steps:
        print("refused: step {} is already captured; a write is never repeated".format(step))
        return 2
    request, problem = _g6_request(record, data, step, values)
    if problem:
        return _acc_stop(problem)
    number, port, identity = _positive_number(values), _port_option(values), data["process"]["identity"]
    label = "g6:" + step

    async def capture():
        async with _bound(port, identity, "g6") as bound:
            before = await bound.listing(label)
            if not before["ok"] or before["active_count"] != 1:
                raise _BenchProblem("the listing is unusable or has no single active document; nothing was sent")
            _require_all_registered(before, record, "g6", identity)
            if number > len(before["documents"]):
                raise _BenchProblem("--number {} is beyond the open documents; nothing was sent".format(number))
            target = before["documents"][number - 1]["document"]
            if target != before["active_document"]:
                raise _BenchProblem("document {} is not the active document; a G6 write needs the active copy; "
                                    "nothing was sent".format(number))
            req = dict(request, document=target)
            reply = await _send_write(bound, req, label)
            after = await _safe_listing(bound, label)
            return {"step": label, "target_document": target, "request": req, "before_listing": before,
                    "reply": reply, "after_listing": after}, bound.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    entry, sent = result
    steps[step] = entry
    _acc_save(values["--in"], record, sent)
    reply = entry["reply"]
    print("G6 {} write sent once: kind={} http={} old={!r} new={!r} identity={}".format(
        step, reply["kind"], reply.get("http_status"), reply.get("old_value"), reply.get("new_value"), reply.get("identity")))
    return _acc_pending("now LOOK at the Revit window, any dialog and (optionally) the parameter value, then record "
                        "them with phase2-observe --step {} --ui unchanged --dialog none [--value-seen TEXT]".format(label))


def _triple(word):
    parts = word.split(":", 2) if isinstance(word, str) else []
    if len(parts) != 3 or _element_id(parts[0]) is None or not parts[1].strip():
        return None
    return {"element_id": int(parts[0]), "parameter_name": parts[1], "value": parts[2], "document": None}


def _cmd_g6_overlap(args):
    values = _acc_options(args, ("--in", "--number", "--a", "--b", "--port"), ("--in", "--number", "--a", "--b"))
    if values is None or _positive_number(values) is None:
        return _acc_usage()
    first, second = _triple(values["--a"]), _triple(values["--b"])
    if first is None or second is None or (first["element_id"], first["parameter_name"]) == (
            second["element_id"], second["parameter_name"]):
        return _acc_usage()
    record, data, code = _sec_prepare(values, "g6")
    if code is not None:
        return code
    if data.get("overlap") is not None:
        print("refused: the overlapped step is already captured; it is never repeated")
        return 2
    if "seq_readback" not in _dict(data.get("steps")):
        return _acc_stop("the sequential run (seq1, seq2, seq_readback) must be captured first; nothing was sent")
    number, port, identity = _positive_number(values), _port_option(values), data["process"]["identity"]

    async def capture():
        async with contextlib.AsyncExitStack() as stack:
            bounds = [await stack.enter_async_context(_bound(port, identity, "g6")) for _ in range(3)]
            before = await bounds[0].listing("g6:overlap")
            if not before["ok"] or before["active_count"] != 1:
                raise _BenchProblem("the listing is unusable or has no single active document; nothing was sent")
            _require_all_registered(before, record, "g6", identity)
            if number > len(before["documents"]):
                raise _BenchProblem("--number {} is beyond the open documents; nothing was sent".format(number))
            target = before["documents"][number - 1]["document"]
            if target != before["active_document"]:
                raise _BenchProblem("document {} is not the active document; nothing was sent".format(number))
            ra, rb = dict(first, document=target), dict(second, document=target)

            async def write(bound, request):
                started = _now()
                reply = await _send_write(bound, request, "g6:overlap")
                return {"tool": "set_parameter", "request": request, "reply": reply, "started_at": started,
                        "finished_at": _now(), "identity_bound": bound.identity}

            async def read(bound):
                started = _now()
                listing = build_listing_entry(await bound.call("list_documents", {}, "g6:overlap"))
                return {"tool": "list_documents", "request": {}, "reply": listing, "started_at": started,
                        "finished_at": _now(), "identity_bound": bound.identity}

            a, b, r = await asyncio.gather(write(bounds[1], ra), write(bounds[2], rb), read(bounds[0]))
            after = await _safe_listing(bounds[0], "g6:overlap")
            sent = [c for bound in bounds for c in bound.sent]
            return {"step": "g6:overlap", "target_document": target, "before_listing": before,
                    "jobs": {"a": a, "b": b, "read": r}, "after_listing": after}, sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    entry, sent = result
    data["overlap"] = entry
    _acc_save(values["--in"], record, sent)
    for key in ("a", "b"):
        reply = entry["jobs"][key]["reply"]
        print("G6 overlap {}: kind={} http={} identity={}".format(key, reply["kind"], reply.get("http_status"), reply.get("identity")))
    return _acc_pending("overlapped step captured through three server processes; now run g6-write --step "
                        "ov_readback_a and --step ov_readback_b, then record g6:overlap with phase2-observe")


# ---- G5: duplicate listener on one port


def _cmd_collision_probe(args):
    names = ("--in", "--port", "--setup-kind", "--setup-method", "--selector")
    values = _options(args, names)
    if values is None or any(k not in values for k in ("--in", "--port", "--setup-kind", "--setup-method")) \
            or _port_option(values) is None or values["--setup-kind"] not in COLLISION_SETUP_KINDS \
            or not values["--setup-method"].strip():
        return _acc_usage()
    selector = values.get("--selector")
    target = None
    if selector is not None:
        try:
            target = _bridge().parse_target(selector)
        except ValueError:
            return _acc_usage()
    record, code = _acc_enter(values, "collision")
    if code is not None:
        return code
    if record["collision"].get("probe") is not None:
        print("refused: the collision probe is already captured; it is never repeated")
        return 2
    port = _port_option(values)
    if target is not None and target["port"] != port:
        return _acc_stop("the selector names port {}, not {}; nothing was sent".format(target["port"], port))
    inventory = _collision_inventory(port)
    owners = inventory["owners"]
    if owners is None or len(owners) < 2:
        return _acc_stop("the full netstat inventory shows {} for port {}: no two-listener condition exists, so "
                         "nothing was sent".format("no usable inventory" if owners is None else "listener(s) {}".format(owners), port))

    async def capture():
        async with _free("collision") as free:
            discovery = await free.call("discover_revit_targets", {}, "collision:discover")
            default = await free.call("get_revit_status", {}, "collision:default")
            selected = None
            if selector is not None:
                selected = await free.call("list_documents", {"target": selector}, "collision:selected")
            return discovery, default, selected, free.sent

    result, code = _acc_run(capture)
    if code is not None:
        return code
    discovery, default, selected, sent = result
    record["collision"]["probe"] = {
        "port": port, "setup_kind": values["--setup-kind"], "setup_method": values["--setup-method"],
        "inventory": inventory, "discovery": dict(parse_discovery_text(discovery), text=discovery),
        "default": dict(parse_refusal_text(default), text=default),
        "selected": None if selected is None else dict(parse_refusal_text(selected), text=selected), "at": _now()}
    _acc_save(values["--in"], record, sent)
    probe = record["collision"]["probe"]
    print("INVENTORY port {} owners {} source {} ({})".format(port, owners, inventory["source"], NETSTAT_METHOD))
    print("DEFAULT CALL refused={} names PIDs {} credits_a_process={}".format(
        probe["default"]["refused"], probe["default"]["pids"], probe["default"]["credits"]))
    return _acc_pending("collision probe captured; now record what you did and saw with phase2-observe --step "
                        "collision:setup --ui collision-created --dialog none, then tear the setup down and run "
                        "collision-after")


def _cmd_collision_after(args):
    values = _acc_options(args, ("--in", "--port"), ("--in", "--port"))
    if values is None or "--port" not in values:
        return _acc_usage()
    record, code = _acc_enter(values, "collision")
    if code is not None:
        return code
    probe = record["collision"].get("probe")
    if not isinstance(probe, dict):
        return _acc_stop("run collision-probe first; nothing was recorded")
    if record["collision"].get("after") is not None:
        print("refused: the teardown inventory is already captured")
        return 2
    port = _port_option(values)
    if port != probe.get("port"):
        return _acc_stop("the probe was for port {}, not {}".format(probe.get("port"), port))
    inventory = _collision_inventory(port)
    if inventory["owners"] is None:
        return _acc_stop("the full netstat inventory is unavailable; the teardown is not verified")
    record["collision"]["after"] = {"port": port, "inventory": inventory, "at": _now()}
    _acc_save(values["--in"], record, [])
    return _acc_pending("teardown inventory for port {}: owners {}; now record it with phase2-observe --step "
                        "collision:cleanup --ui collision-removed --dialog none".format(port, inventory["owners"]))


ACC_COMMANDS = {
    "phase2-template": _cmd_phase2_template, "phase2-start": _cmd_phase2_start,
    "phase2-authorize": _cmd_phase2_authorize, "phase2-attach": _cmd_phase2_attach,
    "phase2-observe": _cmd_phase2_observe, "phase2-classify": _cmd_phase2_classify,
    "g2-list": _cmd_g2_list, "g2-stale": _cmd_g2_stale,
    "two-discover": _cmd_two_discover, "two-default": _cmd_two_default,
    "two-status": lambda args: _cmd_two_selected(args, "get_revit_status", "status"),
    "two-list": lambda args: _cmd_two_selected(args, "list_documents", "list"),
    "two-overlap": _cmd_two_overlap, "http-thread": _cmd_http_thread,
    "mut-start": _cmd_mut_start, "mut-copy": _cmd_mut_copy, "mut-case": _cmd_mut_case,
    "mut-activate": _cmd_mut_activate, "mut-finish": _cmd_mut_finish,
    "collision-probe": _cmd_collision_probe, "collision-after": _cmd_collision_after,
    "g6-start": _cmd_g6_start, "g6-copy": _cmd_g6_copy, "g6-write": _cmd_g6_write,
    "g6-overlap": _cmd_g6_overlap, "g6-finish": _cmd_g6_finish,
}

USAGE = USAGE + "\n" + G34_USAGE + "\n" + ACC_USAGE


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
    if command in ACC_COMMANDS:
        return ACC_COMMANDS[command](rest)
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
