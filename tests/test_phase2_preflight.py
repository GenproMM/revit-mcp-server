# -*- coding: utf-8 -*-
"""Phase 2 preflight (gates G1-G5): operator procedure and offline evidence classifier.

Older tier: a standalone script, run by hand by an engineer, excluded from pytest
(``testpaths = ["tests/unit"]``). It defines no ``test_*`` function and does nothing
at import, so the unit suite can import its pure classifier without side effects.

What this is, and is not
------------------------
Plan 02-20 must decide, from MEASURED evidence on an installed Revit, how process
identity, document identity, inactive-document reads, explicit activation and
listener refusal are implemented. Nothing here measures anything by itself: the
engineer pastes the snippets into a pyRevit diagnostic console, records what they
observe, and ``classify`` turns that record into STOP or ELIGIBLE. ELIGIBLE means
"complete and self-consistent", never "approved": approval is the engineer's
decision at the plan's blocking checkpoint, and the classifier always prints
``approval=not-granted``. A missing, offline, synthetic or contradictory record is
STOP. This file never sends a request: it imports no HTTP, socket or MCP client,
and its only external action is the optional PowerShell listener snapshot (G5).

Commands
--------
    uv run python tests/test_phase2_preflight.py template
    uv run python tests/test_phase2_preflight.py snippet g1|g2|g3|g4
    uv run python tests/test_phase2_preflight.py listeners --ports 48884[,48885]
    uv run python tests/test_phase2_preflight.py classify evidence.json

Output tokens: PHASE2_PREFLIGHT_ELIGIBLE, PHASE2_PREFLIGHT_STOP, LISTENERS,
LISTENERS_UNAVAILABLE. Exit codes: 0 eligible/ok, 1 stop, 2 usage error.

Procedure (engineer, installed Revit, no model-mutating route is ever called)
-----------------------------------------------------------------------------
Run the snippets in a pyRevit diagnostic console, NOT through the unauthenticated
``/execute_code/`` route. After any edit under ``revit_mcp/`` fully restart Revit;
never use pyRevit Reload. ``template`` prints the record to fill in; every value
starts as null, which classifies as STOP.

G1 (process identity, wrapper feasibility, actual port). Run ``snippet g1``. It
    lists every registered handler's positional argument names, the active routes
    server and its ACTUAL bound address, and a token-facility candidate. Fill
    ``injection`` (what was injected, whether ExternalEvent dispatch happens, and
    set ``wrapper_preserves_semantics`` true only after a wrapper was actually
    shown to keep injection and non-throwing responses; leave null otherwise),
    ``token`` (facility, ``initialized_at`` = "process-start" only if shown, stable
    across requests, different after a full Revit restart) and ``port``: the
    Revit-side source of the actual bound port, whether that source is the
    requested selector or a configured default (then it is not authoritative),
    reported port/PID, and the OS listener snapshot for the same port
    (``listeners --ports N``) which must hold exactly the reported PID.
    Reading the installed pyRevit source suggests the handler decides injection
    and ExternalEvent use from ``inspect.getargspec(handler)[0]``, and takes
    ``doc``/``uidoc`` from ``uiapp.ActiveUIDocument`` at dispatch: a wrapper that
    hides the argument names loses both. That is a hint about what to measure, not
    a result.
G2 (document lifetime). Run ``snippet g2`` with LABEL set to before-close, then
    again after closing one of two same-title documents (do both an unsaved
    "Project1" pair and a saved pair), then after opening a replacement with the
    same presentation fields. Map ``runtime_identity_hash`` to ``object_id`` and
    ``api_hash_code`` to ``raw_handle``.
G3 (inactive read safety). Run ``snippet g3`` with A active and B targeted, then
    with B active and A targeted. Fill both ``directions`` and list any accessor
    you found that reads ``revit.doc``/UIDocument in the summary/levels path.
G4 (activation). Run ``snippet g4`` with CONFIRM_ACTIVATION left False to list the
    activation overloads, then set it True per case (saved, unsaved, workshared)
    under engineer control and note dialogs. A case that did not cleanly activate
    must carry policy "refuse".
G5 (ambiguity). Start the duplicate-port condition, run ``listeners --ports N``
    BEFORE any request to that port, capture PIDs independently (Task Manager or
    ``Get-Process revit``), and record ``model_route_send_count`` = the number of
    model-route requests you sent (it must be 0).
"""
import json
import subprocess
import sys

STOP = "stop"
ELIGIBLE = "eligible-for-engineer-decision"
APPROVAL = "not-granted"

# ---------------------------------------------------------------- snippets
# Each is a self-contained, READ-ONLY script for a pyRevit diagnostic console.
# IronPython 3.4 language level (no f-strings), ASCII, LF only, one marked JSON
# line on stdout. None of them imports a pyrevit routes module: importing one in
# a console engine would execute that module's ExternalEvent creation. The
# routes server and the registered handlers are read through pyRevit's shared
# environment variables instead.

G1_SNIPPET = '''# -*- coding: utf-8 -*-
# PHASE 2 G1 probe. READ ONLY. Run in an engineer-operated pyRevit console.
import json
import inspect
import clr
clr.AddReference("System")
import System
from pyrevit import HOST_APP
from pyrevit.coreutils import envvars

API_NAME = "revit_mcp"
out = {"probe": "g1"}


def _try(label, fn):
    try:
        out[label] = fn()
    except Exception as ex:
        out[label] = {"error": repr(ex)}


def _process():
    proc = System.Diagnostics.Process.GetCurrentProcess()
    return {
        "pid": proc.Id,
        "start_time_utc": proc.StartTime.ToUniversalTime().ToString("o"),
        "revit_version": str(HOST_APP.version),
        "host_proc_id": HOST_APP.proc_id,
    }


def _token_facility():
    first = System.Guid.NewGuid().ToString()
    second = System.Guid.NewGuid().ToString()
    return {
        "candidate": "System.Guid.NewGuid",
        "two_calls_differ": first != second,
        "note": "initialized_at must be shown by creating the token at process start from the extension",
    }


def _server():
    srv = envvars.get_pyrevit_env_var(envvars.ROUTES_SERVER)
    if srv is None:
        return {"active_server": False}
    info = {
        "active_server": True,
        "requested_host": str(srv.host),
        "requested_port": srv.port,
    }
    inner = getattr(srv, "server", None)
    bound = getattr(inner, "server_address", None)
    if bound is not None:
        info["bound_server_address"] = [str(bound[0]), int(bound[1])]
    return info


def _handlers():
    route_map = envvars.get_pyrevit_env_var(envvars.ROUTES_ROUTES) or {}
    api_routes = route_map.get(API_NAME) or {}
    rows = []
    for route, func in api_routes.items():
        try:
            args = list(inspect.getargspec(func)[0])
        except Exception as ex:
            args = ["getargspec failed: " + repr(ex)]
        rows.append({
            "route": "{} {}".format(route.method, route.pattern),
            "args": args,
            "wants_api_context": any(a in args for a in ("uiapp", "uidoc", "doc")),
        })
    return sorted(rows, key=lambda r: r["route"])


def _listeners():
    ports = {}
    props = System.Net.NetworkInformation.IPGlobalProperties.GetIPGlobalProperties()
    for ep in props.GetActiveTcpListeners():
        ports.setdefault(ep.Port, []).append(str(ep.Address))
    wanted = [p for p in sorted(ports) if 48000 <= p <= 49999]
    return {
        "scope": "machine-wide endpoints, no PID",
        "ports_48000_49999": dict((str(p), ports[p]) for p in wanted),
    }


_try("process", _process)
_try("token_facility", _token_facility)
_try("server", _server)
_try("handlers", _handlers)
_try("listeners", _listeners)
print("PHASE2_G1_JSON=" + json.dumps(out, default=str))
'''

G2_SNIPPET = '''# -*- coding: utf-8 -*-
# PHASE 2 G2 probe. READ ONLY. Run once per LABEL; close and open documents by hand.
import json
import clr
clr.AddReference("System")
import System
from pyrevit import HOST_APP

LABEL = "before-close"

app = HOST_APP.app
uiapp = HOST_APP.uiapp
helpers = System.Runtime.CompilerServices.RuntimeHelpers


def _describe(doc):
    return {
        "title": doc.Title,
        "path": doc.PathName,
        "kind": "saved" if doc.PathName else "unsaved",
        "is_workshared": bool(doc.IsWorkshared),
        "is_linked": bool(doc.IsLinked),
        "is_valid_object": bool(doc.IsValidObject),
        "runtime_identity_hash": helpers.GetHashCode(doc),
        "api_hash_code": doc.GetHashCode(),
    }


first = [d for d in app.Documents]
second = [d for d in app.Documents]
rows = [_describe(d) for d in first]
equals = []
for i, a in enumerate(first):
    for j, b in enumerate(first):
        if i < j:
            equals.append({"i": i, "j": j, "equals": bool(a.Equals(b))})
same_objects = len(first) == len(second) and all(
    helpers.GetHashCode(a) == helpers.GetHashCode(b) for a, b in zip(first, second)
)
active = uiapp.ActiveUIDocument
out = {
    "probe": "g2",
    "label": LABEL,
    "documents": rows,
    "equals_matrix": equals,
    "second_enumeration_same_objects": same_objects,
    "ui_active_title": None if active is None else active.Document.Title,
    "ui_active_path": None if active is None else active.Document.PathName,
}
print("PHASE2_G2_JSON=" + json.dumps(out, default=str))
'''

G3_SNIPPET = '''# -*- coding: utf-8 -*-
# PHASE 2 G3 probe. READ ONLY. Reads summary and levels of a NON-ACTIVE document
# through its own Document object. Set TARGET_PATH (or TARGET_TITLE for unsaved).
import json
import clr
clr.AddReference("System")
import System
from pyrevit import HOST_APP, DB

TARGET_PATH = ""
TARGET_TITLE = ""
FEET_TO_MM = 304.8

app = HOST_APP.app
uiapp = HOST_APP.uiapp


def _active_key():
    active = uiapp.ActiveUIDocument
    if active is None:
        return None
    doc = active.Document
    return [doc.Title, doc.PathName, doc.GetHashCode()]


def _pick():
    found = []
    for doc in app.Documents:
        if doc.IsLinked:
            continue
        if TARGET_PATH and doc.PathName != TARGET_PATH:
            continue
        if TARGET_TITLE and doc.Title != TARGET_TITLE:
            continue
        found.append(doc)
    return found


before = _active_key()
matches = _pick()
out = {"probe": "g3", "active_before": before, "match_count": len(matches)}
if len(matches) == 1:
    target = matches[0]
    levels = DB.FilteredElementCollector(target).OfClass(DB.Level).ToElements()
    rows = sorted(
        [{"name": lv.Name, "elevation_mm": round(lv.Elevation * FEET_TO_MM, 3)} for lv in levels],
        key=lambda r: r["elevation_mm"],
    )
    elements = DB.FilteredElementCollector(target).WhereElementIsNotElementType()
    out["target"] = [target.Title, target.PathName, target.GetHashCode()]
    out["target_is_active"] = target.GetHashCode() == (before or [None, None, None])[2]
    out["summary"] = {
        "title": target.Title,
        "path": target.PathName,
        "level_count": len(rows),
        "element_count": elements.GetElementCount(),
    }
    out["levels"] = rows
after = _active_key()
out["active_after"] = after
out["ui_switched"] = before != after
print("PHASE2_G3_JSON=" + json.dumps(out, default=str))
'''

G4_SNIPPET = '''# -*- coding: utf-8 -*-
# PHASE 2 G4 probe. Lists the activation API, and activates ONLY when the engineer
# sets CONFIRM_ACTIVATION to True. Activation changes UI state, never model data.
# Run once per case (saved, unsaved, workshared) and note any dialog by hand.
import json
import clr
clr.AddReference("System")
import System
from pyrevit import HOST_APP

CONFIRM_ACTIVATION = False
TARGET_PATH = ""
TARGET_TITLE = ""

uiapp = HOST_APP.uiapp
app = HOST_APP.app


def _active_key():
    active = uiapp.ActiveUIDocument
    if active is None:
        return None
    return [active.Document.Title, active.Document.PathName]


def _overloads():
    rows = []
    for method in uiapp.GetType().GetMethods():
        if "Activate" in method.Name:
            rows.append(str(method))
    return rows


def _open_documents():
    return [[d.Title, d.PathName, bool(d.IsWorkshared)] for d in app.Documents if not d.IsLinked]


out = {
    "probe": "g4",
    "confirm_activation": CONFIRM_ACTIVATION,
    "activation_overloads": _overloads(),
    "open_documents": _open_documents(),
    "active_before": _active_key(),
    "target": [TARGET_TITLE, TARGET_PATH],
}
if CONFIRM_ACTIVATION:
    try:
        uiapp.OpenAndActivateDocument(TARGET_PATH)
        out["activation"] = {"called": True}
    except Exception as ex:
        out["activation"] = {"called": True, "error": repr(ex)}
out["active_after"] = _active_key()
print("PHASE2_G4_JSON=" + json.dumps(out, default=str))
'''

SNIPPETS = {"g1": G1_SNIPPET, "g2": G2_SNIPPET, "g3": G3_SNIPPET, "g4": G4_SNIPPET}


# ------------------------------------------------------------- primitives


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_port(value):
    return _is_int(value) and 1 <= value <= 65535


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _pid_list(value):
    """True when `value` is a non-empty list of distinct positive integer PIDs."""
    return (
        isinstance(value, list)
        and bool(value)
        and all(_is_int(p) and p > 0 for p in value)
        and len(set(value)) == len(value)
    )


def _never_raises(classify):
    def guarded(record):
        try:
            return classify(record)
        except Exception as ex:  # a classifier bug must read as STOP, not as a pass
            return STOP, ["classifier error ({}): {}".format(type(ex).__name__, ex)]

    guarded.__name__ = classify.__name__
    guarded.__doc__ = classify.__doc__
    return guarded


def _preamble(record):
    """Reasons the record is unusable as live evidence at all."""
    if not isinstance(record, dict) or not record:
        return ["no evidence record (missing, empty or not an object)"]
    reasons = []
    if record.get("live") is not True:
        reasons.append("record is not marked live: an offline or unmeasured record never passes")
    if record.get("synthetic") is not False:
        reasons.append("record is not explicitly non-synthetic (synthetic must be false)")
    return reasons


def _section(record, name, reasons):
    value = record.get(name) if isinstance(record, dict) else None
    if not isinstance(value, dict) or not value:
        reasons.append("section '{}' is missing or empty".format(name))
        return {}
    return value


def _finish(reasons, verdict):
    return (STOP, reasons) if reasons else (verdict, [])


# --------------------------------------------------------------------- G1


@_never_raises
def classify_g1(record):
    """G1: wrapper-compatible | explicit-route-only | stop."""
    reasons = _preamble(record)
    if not isinstance(record, dict):
        return STOP, reasons

    inj = _section(record, "injection", reasons)
    sigs = inj.get("handler_signatures")
    if not (
        isinstance(sigs, list)
        and sigs
        and all(
            isinstance(s, dict) and _nonblank(s.get("route")) and isinstance(s.get("args"), list)
            for s in sigs
        )
    ):
        reasons.append("no handler signatures recorded for the installed routes (injection not observed)")
    injected = inj.get("injected") if isinstance(inj.get("injected"), dict) else {}
    missing = [n for n in ("doc", "uidoc", "request") if injected.get(n) is not True]
    for name in missing:
        reasons.append("injection of '{}' was not observed".format(name))
    if inj.get("external_event") is not True:
        reasons.append("ExternalEvent dispatch was not observed")
    if not _nonblank(inj.get("source_ref")):
        reasons.append("injection source_ref is blank (where was the installed implementation read?)")
    wrapper = inj.get("wrapper_preserves_semantics")
    if wrapper not in (True, False, None):
        reasons.append("wrapper_preserves_semantics must be true, false or null")
    elif wrapper is True and (missing or inj.get("external_event") is not True):
        reasons.append(
            "wrapper claimed to preserve injection semantics although injection or "
            "ExternalEvent dispatch was not observed (contradictory record)"
        )

    tok = _section(record, "token", reasons)
    if not _nonblank(tok.get("facility")):
        reasons.append("token facility is not recorded")
    if tok.get("initialized_at") != "process-start":
        reasons.append("token lifetime unproven: initialized_at must be 'process-start'")
    if tok.get("stable_across_requests") is not True:
        reasons.append("token stability across requests was not shown")
    if tok.get("differs_across_restarts") is not True:
        reasons.append("token difference across full Revit restarts was not shown")

    port = _section(record, "port", reasons)
    if not _nonblank(port.get("source")):
        reasons.append("no Revit-side port source recorded for the actual bound port")
    if port.get("is_requested_selector_or_default") is not False:
        reasons.append(
            "port source is the requested selector or a configured default (or unknown), "
            "not the actual bound port"
        )
    reported_port, reported_pid = port.get("reported_port"), port.get("reported_pid")
    if not _is_port(reported_port):
        reasons.append("reported_port is missing or not a valid port")
    if not (_is_int(reported_pid) and reported_pid > 0):
        reasons.append("reported_pid is missing or not a valid PID")
    snap = port.get("os_snapshot")
    if not isinstance(snap, dict):
        reasons.append("no independent OS listener snapshot for the reported port")
    else:
        snap_port, snap_pids = snap.get("port"), snap.get("pids")
        if not _is_port(snap_port):
            reasons.append("OS snapshot has no valid port")
        elif _is_port(reported_port) and snap_port != reported_port:
            reasons.append(
                "port mismatch: Revit reports {} but the OS snapshot is for port {}".format(
                    reported_port, snap_port
                )
            )
        if not _pid_list(snap_pids):
            reasons.append("OS snapshot has no usable PID list")
        elif len(snap_pids) != 1:
            reasons.append(
                "OS snapshot shows {} listeners on the port, expected exactly one".format(len(snap_pids))
            )
        elif _is_int(reported_pid) and snap_pids[0] != reported_pid:
            reasons.append(
                "PID mismatch: Revit reports pid {} but the OS listener is pid {}".format(
                    reported_pid, snap_pids[0]
                )
            )

    return _finish(reasons, "wrapper-compatible" if wrapper is True else "explicit-route-only")


# --------------------------------------------------------------------- G2


@_never_raises
def classify_g2(record):
    """G2: document-object-binding-provable | stop."""
    reasons = _preamble(record)
    if not isinstance(record, dict):
        return STOP, reasons

    objs = record.get("open_objects")
    valid = (
        isinstance(objs, list)
        and len(objs) >= 2
        and all(
            isinstance(o, dict)
            and _nonblank(o.get("title"))
            and isinstance(o.get("path"), str)
            and o.get("kind") in ("saved", "unsaved")
            and _nonblank(o.get("object_id"))
            and _nonblank(o.get("raw_handle"))
            for o in objs
        )
    )
    ids = {}
    if not valid:
        reasons.append("open_objects must list at least two documents with title, path, kind, object_id, raw_handle")
    else:
        for kind in ("unsaved", "saved"):
            titles = [o["title"] for o in objs if o["kind"] == kind]
            if not any(titles.count(t) >= 2 for t in titles):
                reasons.append("no same-title {} pair among open_objects".format(kind))
        ids = dict((o["object_id"], o) for o in objs)
        if len(ids) != len(objs):
            reasons.append("open documents do not have distinct wrapper objects (an object_id repeats)")

    life = _section(record, "wrapper_lifetime", reasons)
    if life.get("stable_while_open") is not True:
        reasons.append("wrapper object is not shown stable while the document is open")
    if life.get("stable_across_enumerations") is not True:
        reasons.append("wrapper object is not shown stable across enumerations")

    cr = _section(record, "close_and_replace", reasons)
    closed = ids.get(cr.get("closed_object_id")) if valid else None
    if valid and closed is None:
        reasons.append("closed_object_id does not name one of the open_objects")
    if cr.get("closed_object_invalid_after_close") is not True:
        reasons.append("the closed document's object was not shown invalid after close")
    if cr.get("survivor_resolves") is not True:
        reasons.append("the surviving same-title document was not shown to still resolve")
    rep = cr.get("replacement")
    if not (
        isinstance(rep, dict) and _nonblank(rep.get("object_id")) and _nonblank(rep.get("raw_handle"))
    ):
        reasons.append("replacement document record (object_id, raw_handle) is missing")
    else:
        if rep.get("presentation_matches_closed") is not True:
            reasons.append("replacement was not opened with presentation fields matching the closed document")
        if valid and rep["object_id"] in ids:
            reasons.append("replacement wrapper object equals a previously open object (object_id reused)")
        equal = cr.get("raw_handle_equal_to_closed")
        if not isinstance(equal, bool):
            reasons.append("raw_handle_equal_to_closed was not measured")
        elif closed is not None and (rep["raw_handle"] == closed["raw_handle"]) != equal:
            reasons.append(
                "contradictory record: raw_handle_equal_to_closed={} disagrees with the recorded handles".format(equal)
            )

    design = _section(record, "token_design", reasons)
    for key, text in (
        ("registry_issued", "token is not registry-issued"),
        ("monotonic_unique_per_incarnation", "token is not monotonically unique within a process incarnation"),
        ("tombstone_after_close", "token is not tombstoned after close"),
    ):
        if design.get(key) is not True:
            reasons.append(text)
    if design.get("raw_handle_used_as_selector") is not False:
        reasons.append("a raw Revit handle is (or may be) used as an externally addressable selector")

    return _finish(reasons, "document-object-binding-provable")


# --------------------------------------------------------------------- G3

_G3_DIRECTIONS = (("A_active_read_B", "A", "B"), ("B_active_read_A", "B", "A"))


@_never_raises
def classify_g3(record):
    """G3: document-only-path | stop."""
    reasons = _preamble(record)
    if not isinstance(record, dict):
        return STOP, reasons

    if record.get("code_path") != "document-only":
        reasons.append("code_path is not 'document-only'")
    accessors = record.get("accessors_reading_active_state")
    if not isinstance(accessors, list):
        reasons.append("accessors_reading_active_state was not recorded (must be a list)")
    elif accessors:
        reasons.append(
            "accessors read the active document, so the Document-only path is not proven: {}".format(
                "; ".join(str(a) for a in accessors)
            )
        )

    dirs = _section(record, "directions", reasons)
    answers = []
    for key, active, target in _G3_DIRECTIONS:
        d = dirs.get(key)
        if not isinstance(d, dict):
            reasons.append("direction {} was not measured".format(key))
            continue
        if d.get("active_before") != active or d.get("target") != target:
            reasons.append("direction {} must have {} active and read {}".format(key, active, target))
        if d.get("active_after") != d.get("active_before"):
            reasons.append("direction {}: the active document changed during the read".format(key))
        if d.get("ui_switched") is not False:
            reasons.append("direction {}: UI switch not ruled out (ui_switched must be false)".format(key))
        if d.get("data_from") != target:
            reasons.append("direction {}: data did not come from the addressed document".format(key))
        summary, levels = d.get("summary"), d.get("levels")
        if not (isinstance(summary, dict) and _nonblank(summary.get("title"))):
            reasons.append("direction {}: summary with a title is missing".format(key))
        if not (isinstance(levels, list) and levels):
            reasons.append("direction {}: levels are missing or empty".format(key))
        answers.append((summary, levels))
    if len(answers) == 2 and answers[0] == answers[1]:
        reasons.append("the two documents returned identical summary and levels (not distinct A/B data)")

    return _finish(reasons, "document-only-path")


# --------------------------------------------------------------------- G4

_G4_CASES = ("saved", "unsaved", "workshared")
_G4_OUTCOMES = ("activated", "refused", "dialog", "error")


@_never_raises
def classify_g4(record):
    """G4: explicit-activation-api | stop."""
    reasons = _preamble(record)
    if not isinstance(record, dict):
        return STOP, reasons

    if not _nonblank(record.get("api")):
        reasons.append("the activation API (name and overload) is not recorded")
    if record.get("external_event_context") is not True:
        reasons.append("activation was not shown to run in a valid Revit API context")

    cases = _section(record, "cases", reasons)
    allowed = 0
    for name in _G4_CASES:
        case = cases.get(name)
        if not isinstance(case, dict):
            reasons.append("case {} is missing".format(name))
            continue
        if case.get("tested") is not True:
            reasons.append("case {} was not tested".format(name))
            continue
        outcome, policy = case.get("outcome"), case.get("policy")
        if outcome not in _G4_OUTCOMES:
            reasons.append("case {} has an unknown outcome".format(name))
        if policy not in ("allow", "refuse"):
            reasons.append("case {} has an unknown policy (must be allow or refuse)".format(name))
        if policy == "allow":
            if outcome != "activated" or case.get("active_after_is_target") is not True:
                reasons.append("case {} is allowed but did not activate the target".format(name))
            elif case.get("dialog_observed") is not False:
                reasons.append("case {} is allowed but a dialog was observed".format(name))
            else:
                allowed += 1
    if not any(r.startswith("case ") for r in reasons) and not allowed:
        reasons.append("no case activates the target cleanly, so there is nothing to release")

    return _finish(reasons, "explicit-activation-api")


# --------------------------------------------------------------------- G5


@_never_raises
def classify_g5(record):
    """G5: listener-inventory-complete | stop."""
    reasons = _preamble(record)
    if not isinstance(record, dict):
        return STOP, reasons

    if not _is_port(record.get("port")):
        reasons.append("port is missing or not a valid port")
    snap = _section(record, "os_snapshot", reasons)
    snap_pids = snap.get("pids")
    if snap.get("taken_before_any_send") is not True:
        reasons.append("the OS snapshot was not shown to precede every request to the port")
    if not _nonblank(snap.get("source")):
        reasons.append("the OS snapshot source is not recorded")
    snap_ok = _pid_list(snap_pids)
    if not snap_ok:
        reasons.append("OS snapshot has no usable PID list")
    elif len(snap_pids) < 2:
        reasons.append("the two-listener condition was not created: the snapshot holds a single PID")

    indep = _section(record, "independent_pid_capture", reasons)
    indep_pids = indep.get("pids")
    if not _nonblank(indep.get("method")):
        reasons.append("the independent PID capture method is not recorded")
    if not _pid_list(indep_pids):
        reasons.append("independent PID capture has no usable PID list")
    elif snap_ok and set(indep_pids) != set(snap_pids):
        reasons.append("independent PID capture disagrees with the OS snapshot")

    sends = record.get("model_route_send_count")
    if not (_is_int(sends) and sends == 0):
        reasons.append("model_route_send_count must be exactly 0 (a request reached the port, or it was not counted)")

    return _finish(reasons, "listener-inventory-complete")


# ----------------------------------------------------------------- overall

GATES = (
    ("G1", "g1", classify_g1),
    ("G2", "g2", classify_g2),
    ("G3", "g3", classify_g3),
    ("G4", "g4", classify_g4),
    ("G5", "g5", classify_g5),
)


def classify_all(evidence):
    """Classify every gate. Never approves: `approval` is always 'not-granted'."""
    source = evidence if isinstance(evidence, dict) else {}
    gates = {}
    for label, key, classify in GATES:
        verdict, reasons = classify(source.get(key))
        gates[label] = {"verdict": verdict, "reasons": list(reasons)}
    eligible = all(g["verdict"] != STOP for g in gates.values())
    return {"gates": gates, "overall": ELIGIBLE if eligible else STOP, "approval": APPROVAL}


def evidence_template():
    """The record to fill in. Every value is null, so it classifies as STOP."""
    case = {
        "tested": None,
        "outcome": None,
        "dialog_observed": None,
        "active_after_is_target": None,
        "policy": None,
    }
    direction = {
        "active_before": None,
        "target": None,
        "active_after": None,
        "ui_switched": None,
        "summary": {"title": None, "level_count": None},
        "levels": None,
        "data_from": None,
    }
    return {
        "g1": {
            "live": None,
            "synthetic": None,
            "revit_version": None,
            "pyrevit_version": None,
            "injection": {
                "handler_signatures": [{"route": None, "args": None}],
                "injected": {"doc": None, "uidoc": None, "request": None},
                "external_event": None,
                "wrapper_preserves_semantics": None,
                "source_ref": None,
            },
            "token": {
                "facility": None,
                "initialized_at": None,
                "stable_across_requests": None,
                "differs_across_restarts": None,
            },
            "port": {
                "source": None,
                "is_requested_selector_or_default": None,
                "reported_port": None,
                "reported_pid": None,
                "os_snapshot": {"port": None, "pids": None},
            },
        },
        "g2": {
            "live": None,
            "synthetic": None,
            "open_objects": [
                {"title": None, "path": None, "kind": None, "object_id": None, "raw_handle": None}
            ],
            "wrapper_lifetime": {"stable_while_open": None, "stable_across_enumerations": None},
            "close_and_replace": {
                "closed_object_id": None,
                "closed_object_invalid_after_close": None,
                "survivor_resolves": None,
                "replacement": {
                    "title": None,
                    "path": None,
                    "object_id": None,
                    "raw_handle": None,
                    "presentation_matches_closed": None,
                },
                "raw_handle_equal_to_closed": None,
            },
            "token_design": {
                "registry_issued": None,
                "monotonic_unique_per_incarnation": None,
                "tombstone_after_close": None,
                "raw_handle_used_as_selector": None,
            },
        },
        "g3": {
            "live": None,
            "synthetic": None,
            "code_path": None,
            "accessors_reading_active_state": None,
            "directions": {
                "A_active_read_B": dict(direction, summary=dict(direction["summary"])),
                "B_active_read_A": dict(direction, summary=dict(direction["summary"])),
            },
        },
        "g4": {
            "live": None,
            "synthetic": None,
            "api": None,
            "external_event_context": None,
            "cases": {name: dict(case) for name in _G4_CASES},
        },
        "g5": {
            "live": None,
            "synthetic": None,
            "port": None,
            "os_snapshot": {"source": None, "taken_before_any_send": None, "pids": None},
            "independent_pid_capture": {"method": None, "pids": None},
            "model_route_send_count": None,
        },
    }


# ------------------------------------------------------------ OS listeners


def parse_listener_rows(text, ports):
    """Parse Get-NetTCPConnection JSON into {port: [pids]}, or None if unreadable.

    None, never an empty inventory, for output that cannot be read: an unreadable
    snapshot must not look like "no listeners".
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        rows = json.loads(text)
    except ValueError:
        return None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return None
    result = dict((p, []) for p in ports)
    for row in rows:
        if not isinstance(row, dict):
            continue
        port, pid = row.get("LocalPort"), row.get("OwningProcess")
        if _is_int(port) and _is_int(pid) and port in result and pid not in result[port]:
            result[port].append(pid)
    return result


def os_listener_snapshot(ports, run=subprocess.run):
    """Listening-socket PIDs per port from the OS, or None if it cannot be read."""
    script = (
        "$r = @(Get-NetTCPConnection -State Listen -LocalPort {} "
        "-ErrorAction SilentlyContinue | Select-Object LocalPort,OwningProcess); "
        "ConvertTo-Json -InputObject $r -Compress"
    ).format(",".join(str(p) for p in ports))
    try:
        done = run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return parse_listener_rows(done.stdout, ports)


# --------------------------------------------------------------------- CLI

USAGE = (
    "usage: test_phase2_preflight.py template | snippet g1|g2|g3|g4 | "
    "listeners --ports N[,N] | classify evidence.json"
)


def _stop(text):
    print("PHASE2_PREFLIGHT_STOP: " + text)
    return 1


def _cmd_classify(path):
    try:
        with open(path, "rb") as handle:
            evidence = json.loads(handle.read().decode("utf-8-sig"))
    except (OSError, ValueError) as ex:
        return _stop("cannot read evidence file {!r}: {}".format(path, ex))
    result = classify_all(evidence)
    for label, _key, _fn in GATES:
        gate = result["gates"][label]
        print("{} verdict={}".format(label, gate["verdict"]))
        for reason in gate["reasons"]:
            print("  - " + reason)
    token = "PHASE2_PREFLIGHT_ELIGIBLE" if result["overall"] == ELIGIBLE else "PHASE2_PREFLIGHT_STOP"
    print("{} approval={}".format(token, result["approval"]))
    return 0 if result["overall"] == ELIGIBLE else 1


def _cmd_listeners(args):
    if len(args) != 2 or args[0] != "--ports":
        print(USAGE)
        return 2
    try:
        ports = [int(p) for p in args[1].split(",")]
    except ValueError:
        print(USAGE)
        return 2
    if not ports or not all(_is_port(p) for p in ports):
        print(USAGE)
        return 2
    snapshot = os_listener_snapshot(ports)
    if snapshot is None:
        print("LISTENERS_UNAVAILABLE: the OS listener snapshot could not be read")
        return 1
    for port in ports:
        print("LISTENERS port={} pids={}".format(port, ",".join(str(p) for p in snapshot[port])))
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(USAGE)
        return _stop("no command given and no evidence recorded")
    command, rest = args[0], args[1:]
    if command == "template" and not rest:
        print(json.dumps(evidence_template(), indent=2))
        return 0
    if command == "snippet" and len(rest) == 1 and rest[0] in SNIPPETS:
        print(SNIPPETS[rest[0]])
        return 0
    if command == "classify" and len(rest) == 1:
        return _cmd_classify(rest[0])
    if command == "listeners":
        return _cmd_listeners(rest)
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
