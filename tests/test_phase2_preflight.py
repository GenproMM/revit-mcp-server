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
    ``injection`` (what was injected, whether ExternalEvent dispatch happens,
    ``observation_method``, and ``wrapper_preserves_semantics`` set true only after a
    wrapper was actually shown to keep injection and non-throwing responses; leave
    null otherwise),
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
    ``injection.observation_method`` discloses how injection was observed.
    "signature-and-source" means the handler argument names from the G1 snippet plus
    reading the installed pyRevit handler source: that is inference from source, not
    an observed call. "live-dispatch" means it was observed during an actual request.
    Both values may continue; the field only makes the evidence level explicit.
G2 (document lifetime). Each button click is a fresh script run, so the snippet
    keeps the enumerated Document objects in process-wide AppDomain data
    ("phase2_g2_store", with the describe() rows as JSON under
    "phase2_g2_store_meta"). Run ``snippet g2`` with LABEL = "before-close" FIRST
    (the only label that stores; it overwrites any previous store), then again with
    another label after closing one of two same-title documents, then after opening
    a replacement with the same presentation fields. Every run prints
    ``stored_objects``: per stored document the stored row, ``is_valid_object``
    (or {"error": ...} if access throws) and ``still_enumerated`` (its stored
    Document has an Equals match in the current enumeration). Hashes are diagnostic
    only: neither RuntimeHelpers.GetHashCode nor Document.GetHashCode proves object
    identity or exposes a raw native handle. Never turn either into a selector.
    For ``binding_mechanism`` = "retained-reference-equals-v1", attach schema-2
    ``captures`` in order: before-close, while-open, after-close BEFORE reopen,
    after-replacement. Preserve the retained store across all four captures. Supply
    ``closed_store_index``, ``survivor_store_index`` and ``replacement_current_index``
    as observation positions, NOT document tokens. IsValidObject must be false for
    the closed entry both before and after reopen; an access error is STOP. Every
    other retained entry must stay valid, have exactly one Equals match and support
    a collector read. ReferenceEquals is measured separately and may be false.
    ``replacement_retained`` is a separate read-only observation of the retained
    replacement: original_valid false, and retained rows with distinct owned_index,
    title, path, valid, equals_matches and element_count. ``replacement_owned_index``
    identifies its row in that observation, not an external token. This observation
    must use the same current enumeration as after-replacement (verify its index and
    title/path); recapture if ordering changed. No automatic token-registry proof is
    inferred: ``token_design`` states mandatory future design constraints only.
    The legacy wrapper-lifetime branch remains available for old records; it still
    requires independently proven object identities and native handles, not hashes.
    Revit numbers new unsaved projects (Project1, Project2), so an unsaved
    same-title pair is probably impossible, and Revit may refuse to open a second
    saved file with the same name. Try both, and record in ``same_title_pairs``
    (keys ``unsaved`` and ``saved``, each ``reproducible`` + ``attempt``): a kind
    with a real same-title pair among ``open_objects`` is enough on its own; a kind
    without one needs ``reproducible`` false AND an ``attempt`` text saying what was
    tried (a measured negative). ``reproducible`` false while that kind's pair is in
    ``open_objects`` is contradictory. If neither kind has a real pair the gate
    STOPs: at least one real same-title pair is required.
G3 (inactive read safety). Run ``snippet g3`` with A active and B targeted, then
    with B active and A targeted. Fill both ``directions`` and list any accessor
    you found that reads ``revit.doc``/UIDocument in the summary/levels path.
G4 (activation). The routes run handlers through an ExternalEvent, so activation
    must be tested in that context, not only in a button's command context. Run
    ``snippet g4`` in MODE = "list" (default: lists overloads, open documents and
    the active document, never activates). Then, per case (saved, unsaved,
    workshared) under engineer control, set CONFIRM_ACTIVATION = True and run
    MODE = "external-event" (an IExternalEventHandler activates TARGET_PATH and
    stores its result under "phase2_g4_result"; Raise() only queues it), wait until
    Revit is idle, then run MODE = "report". Note any dialog by hand. MODE =
    "command" activates directly in the command context and is optional extra
    evidence only. Without CONFIRM_ACTIVATION the activating modes print a refusal
    line and do nothing. Record per case ``context`` ("command" | "external-event");
    a case with policy "allow" must have context "external-event". A case that did
    not cleanly activate must carry policy "refuse".
G5 (ambiguity). Start the duplicate-port condition, run ``listeners --ports N``
    BEFORE any request to that port. This captures full ``netstat.exe -ano -p tcp``
    output, retaining every LISTENING PID, including duplicate endpoints, wildcard
    and IPv6 binds. Get-NetTCPConnection alone was incomplete in the live dual-bind
    experiment and is not a fallback. Unknown states, malformed rows or an unreadable
    inventory mean STOP, never "no listeners". Independently cross-check the socket
    owners against Revit processes (Task Manager or ``Get-Process revit``); process
    existence alone does not prove socket ownership. Record both capture methods and
    any disagreement, and ``model_route_send_count`` (it must be 0). Do not send even
    a status request to the conflicting port. This auxiliary-server experiment does
    not establish automatic primary-port selection or whole-checkpoint approval.
"""
import ipaddress
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

API_NAME = "genpro_revit_mcp"
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
# Every button click is a fresh script run, so the Document objects enumerated under
# LABEL = "before-close" are kept in process-wide AppDomain data and read back by
# every later run. Run LABEL = "before-close" FIRST (it overwrites any earlier store),
# then "after-close" BEFORE reopening, then "after-replacement". Runtime/API hashes
# are diagnostic only, never identity or selector proofs. Schema 2 uses Equals for
# still_enumerated; keep ReferenceEquals separate from semantic document equality.
# Nothing here opens, closes, saves or changes a document.
import json
import clr
clr.AddReference("System")
import System
from pyrevit import HOST_APP, DB

LABEL = "before-close"
STORE_KEY = "phase2_g2_store"
META_KEY = "phase2_g2_store_meta"

app = HOST_APP.app
uiapp = HOST_APP.uiapp
helpers = System.Runtime.CompilerServices.RuntimeHelpers
domain = System.AppDomain.CurrentDomain


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
        "label": LABEL,
    }


def _comparisons(doc, current):
    rows = []
    for index, other in enumerate(current):
        row = {"current_index": index, "equals": None, "reference_equals": None}
        try:
            row["reference_equals"] = bool(System.Object.ReferenceEquals(doc, other))
            row["equals"] = bool(doc.Equals(other))
        except Exception as ex:
            row["error"] = repr(ex)
        rows.append(row)
    return rows


def _stored_objects(current):
    store = domain.GetData(STORE_KEY)
    meta_text = domain.GetData(META_KEY)
    if store is None or meta_text is None:
        return None
    meta = json.loads(str(meta_text))
    rows = []
    for index in range(store.Count):
        doc = store[index]
        stored = meta[index] if index < len(meta) else None
        try:
            valid = bool(doc.IsValidObject)
        except Exception as ex:
            valid = {"error": repr(ex)}
        comparisons = _comparisons(doc, current) if valid is True else []
        row = {
            "stored": stored,
            "is_valid_object": valid,
            "comparisons": comparisons,
            "still_enumerated": any(r["equals"] is True for r in comparisons),
        }
        if valid is True:
            try:
                collector = DB.FilteredElementCollector(doc).WhereElementIsNotElementType()
                row["element_count"] = collector.GetElementCount()
            except Exception as ex:
                row["collector_error"] = repr(ex)
        rows.append(row)
    return rows


first = [d for d in app.Documents]
second = [d for d in app.Documents]
rows = [_describe(d) for d in first]
if LABEL == "before-close":
    keep = System.Collections.ArrayList()
    for d in first:
        keep.Add(d)
    domain.SetData(STORE_KEY, keep)
    domain.SetData(META_KEY, json.dumps(rows, default=str))
equals = []
for i, a in enumerate(first):
    for j, b in enumerate(first):
        if i < j:
            equals.append({"i": i, "j": j, "equals": bool(a.Equals(b))})
enumerations = [{"first_index": i, "comparisons": _comparisons(d, second)}
                for i, d in enumerate(first)]
same_objects = len(first) == len(second) and all(
    sum(1 for r in row["comparisons"] if r["reference_equals"] is True) == 1
    for row in enumerations
)
active = uiapp.ActiveUIDocument
out = {
    "probe": "g2",
    "probe_schema": 2,
    "identity_note": "hashes are diagnostic; Equals and ReferenceEquals are separate measurements",
    "enumeration_comparisons": enumerations,
    "label": LABEL,
    "documents": rows,
    "equals_matrix": equals,
    "second_enumeration_same_objects": same_objects,
    "ui_active_title": None if active is None else active.Document.Title,
    "ui_active_path": None if active is None else active.Document.PathName,
    "stored_objects": _stored_objects(first),
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


def _active_doc():
    active = uiapp.ActiveUIDocument
    return None if active is None else active.Document


def _active_key(doc):
    return None if doc is None else [doc.Title, doc.PathName, doc.GetHashCode()]


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


before_doc = _active_doc()
before = _active_key(before_doc)
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
    out["target_is_active"] = before_doc is not None and bool(target.Equals(before_doc))
    out["summary"] = {
        "title": target.Title,
        "path": target.PathName,
        "level_count": len(rows),
        "element_count": elements.GetElementCount(),
    }
    out["levels"] = rows
after_doc = _active_doc()
after = _active_key(after_doc)
out["active_after"] = after
out["ui_switched"] = ((after_doc is not None) if before_doc is None else
                      (after_doc is None or not bool(before_doc.Equals(after_doc))))
print("PHASE2_G3_JSON=" + json.dumps(out, default=str))
'''

G4_SNIPPET = '''# -*- coding: utf-8 -*-
# PHASE 2 G4 probe. MODE "list" (default) lists the activation overloads, the open
# documents and the active document and never activates anything. Modes "command"
# and "external-event" activate TARGET_PATH and need CONFIRM_ACTIVATION = True, else
# they print a refusal line and do nothing. Activation changes UI state, never model
# data. Run once per case (saved, unsaved, workshared) and note any dialog by hand.
#   "command"        activate directly in this button's command context (extra evidence)
#   "external-event" activate inside an ExternalEvent handler, the context the routes
#                    use; Raise() only queues it, so wait until Revit is idle
#   "report"         print the result the handler stored under "phase2_g4_result"
import json
import clr
clr.AddReference("System")
clr.AddReference("RevitAPIUI")
import System
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent
from pyrevit import HOST_APP

MODE = "list"
CONFIRM_ACTIVATION = False
TARGET_PATH = ""
TARGET_TITLE = ""

RESULT_KEY = "phase2_g4_result"
HANDLER_KEY = "phase2_g4_handler"
EVENT_KEY = "phase2_g4_event"

uiapp = HOST_APP.uiapp
app = HOST_APP.app
domain = System.AppDomain.CurrentDomain


def _active_key_of(ui):
    active = ui.ActiveUIDocument
    if active is None:
        return None
    return [active.Document.Title, active.Document.PathName]


class Phase2G4Handler(IExternalEventHandler):
    def __init__(self, target_path, target_title):
        self.target_path = target_path
        self.target_title = target_title

    def Execute(self, uiapp):
        # The button engine may have cleared its globals before this callback runs.
        import System
        import json
        result = {
            "context": "external-event",
            "target": [self.target_title, self.target_path],
            "active_before": None,
            "active_after": None,
            "error": None,
        }
        try:
            active = uiapp.ActiveUIDocument
            result["active_before"] = None if active is None else [active.Document.Title, active.Document.PathName]
            uiapp.OpenAndActivateDocument(self.target_path)
        except Exception as ex:
            result["error"] = repr(ex)
        try:
            active = uiapp.ActiveUIDocument
            result["active_after"] = None if active is None else [active.Document.Title, active.Document.PathName]
        except Exception as ex:
            result["error"] = "{} / active_after: {}".format(result["error"], repr(ex))
        System.AppDomain.CurrentDomain.SetData("phase2_g4_result", json.dumps(result, default=str))

    def GetName(self):
        return "Phase2G4Handler"


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
    "mode": MODE,
    "context": None,
    "confirm_activation": CONFIRM_ACTIVATION,
    "activation_overloads": _overloads(),
    "open_documents": _open_documents(),
    "active_before": _active_key_of(uiapp),
    "target": [TARGET_TITLE, TARGET_PATH],
}
if MODE == "list":
    pass
elif MODE == "report":
    raw = domain.GetData(RESULT_KEY)
    out["result"] = None if raw is None else json.loads(str(raw))
    if out["result"] is not None:
        out["context"] = out["result"].get("context")
elif MODE in ("command", "external-event"):
    if CONFIRM_ACTIVATION:
        if MODE == "command":
            out["context"] = "command"
            try:
                uiapp.OpenAndActivateDocument(TARGET_PATH)
                out["activation"] = {"called": True}
            except Exception as ex:
                out["activation"] = {"called": True, "error": repr(ex)}
        else:
            out["context"] = "external-event"
            handler = Phase2G4Handler(TARGET_PATH, TARGET_TITLE)
            event = ExternalEvent.Create(handler)
            domain.SetData(HANDLER_KEY, handler)
            domain.SetData(EVENT_KEY, event)
            domain.SetData(RESULT_KEY, None)
            out["raise_request"] = str(event.Raise())
            out["note"] = "queued; wait until Revit is idle, then run MODE = report"
    else:
        out["refused"] = "MODE {} needs CONFIRM_ACTIVATION = True".format(MODE)
        print("PHASE2_G4_REFUSED: set CONFIRM_ACTIVATION = True to run mode " + MODE)
else:
    out["error"] = "unknown MODE " + repr(MODE)
out["active_after"] = _active_key_of(uiapp)
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

# A disclosure, not a stricter gate: both values may continue. "signature-and-source"
# is inference from the handler argument names and the installed source.
_G1_METHODS = ("signature-and-source", "live-dispatch")


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
    if inj.get("observation_method") not in _G1_METHODS:
        reasons.append(
            "injection observation_method must be 'signature-and-source' or 'live-dispatch' "
            "(how was injection observed?)"
        )
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


def _g2_token_design(record, reasons):
    # Design constraints, not a claim that the production registry exists.
    design = _section(record, "token_design", reasons)
    for key in ("registry_issued", "monotonic_unique_per_incarnation", "tombstone_after_close"):
        if design.get(key) is not True:
            reasons.append("token_design.{} must be true".format(key))
    if design.get("raw_handle_used_as_selector") is not False:
        reasons.append("a raw handle/hash may be used as a selector")


def _g2_presentation(doc):
    if not isinstance(doc, dict) or not _nonblank(doc.get("title")) or not isinstance(doc.get("path"), str):
        raise ValueError("G2 document needs title and path")
    return doc["title"], doc["path"]


def _g2_matches(rows, count):
    """Validate a full comparison matrix row; return the one semantic match."""
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError("G2 comparison row does not cover current documents")
    indices, matches, references = [], [], []
    for row in rows:
        if not isinstance(row, dict) or "error" in row:
            raise ValueError("G2 comparison error")
        index = row.get("current_index")
        if not _is_int(index) or not 0 <= index < count:
            raise ValueError("G2 comparison index invalid")
        if type(row.get("equals")) is not bool or type(row.get("reference_equals")) is not bool:
            raise ValueError("G2 comparison booleans are missing or invalid")
        indices.append(index)
        if row["equals"]:
            matches.append(index)
        if row["reference_equals"]:
            if not row["equals"]:
                raise ValueError("G2 ReferenceEquals contradicts Equals")
            references.append(index)
    if len(set(indices)) != count or len(matches) != 1 or len(references) > 1:
        raise ValueError("G2 binding must have exactly one unique Equals match")
    return matches[0], bool(references)


def _g2_collector(row):
    count = row.get("element_count")
    if "collector_error" in row or not _is_int(count) or count < 0:
        raise ValueError("G2 retained collector read missing or failed")


def _classify_retained_g2(record, reasons):
    """Validate lifetime observations, without deriving identities from hashes."""
    captures = record.get("captures")
    labels = ["before-close", "while-open", "after-close", "after-replacement"]
    if not isinstance(captures, list) or len(captures) != 4:
        return STOP, reasons + ["G2 needs four ordered lifetime captures"]
    if any(not isinstance(c, dict) for c in captures) or [c.get("label") for c in captures] != labels:
        return STOP, reasons + ["G2 capture order must include after-close before replacement"]
    closed, survivor = record.get("closed_store_index"), record.get("survivor_store_index")
    first = captures[0].get("stored_objects")
    if not isinstance(first, list) or len(first) < 2:
        return STOP, reasons + ["G2 needs at least two retained documents"]
    size = len(first)
    if any(not _is_int(i) or not 0 <= i < size for i in (closed, survivor)) or closed == survivor:
        return STOP, reasons + ["G2 closed/survivor store positions invalid"]
    initial = [_g2_presentation(r.get("stored")) for r in first]
    if initial[closed][0] != initial[survivor][0]:
        reasons.append("G2 closed/survivor must be a same-title pair")
    objects = captures[0].get("documents")
    if not isinstance(objects, list):
        return STOP, reasons + ["G2 initial document list missing"]
    pairs = _section(record, "same_title_pairs", reasons)
    observed = 0
    for kind in ("saved", "unsaved"):
        titles = []
        for doc in objects:
            title, path = _g2_presentation(doc)
            if doc.get("kind") not in ("saved", "unsaved") or (doc["kind"] == "saved") != bool(path):
                raise ValueError("G2 saved/unsaved kind contradicts path")
            if doc["kind"] == kind:
                titles.append(title)
        has_pair = any(titles.count(t) > 1 for t in titles)
        entry = pairs.get(kind, {})
        if has_pair:
            observed += 1
            if entry.get("reproducible") is not True:
                reasons.append("G2 same-title {} pair needs reproducible=true".format(kind))
        elif not (entry.get("reproducible") is False and _nonblank(entry.get("attempt"))):
            reasons.append("G2 no same-title {} pair or measured negative".format(kind))
    if not observed:
        reasons.append("G2 same-title binding is unmeasured")
    match_maps = []
    for stage, capture in enumerate(captures):
        if "pf_error" in capture or "error" in capture:
            raise ValueError("G2 capture reports an error")
        if capture.get("probe") != "g2" or type(capture.get("probe_schema")) is not int or capture["probe_schema"] != 2:
            raise ValueError("G2 raw capture must use probe_schema 2")
        docs, stored = capture.get("documents"), capture.get("stored_objects")
        expected = size - 1 if stage == 2 else size
        if not isinstance(docs, list) or len(docs) != expected or not isinstance(stored, list) or len(stored) != size:
            raise ValueError("G2 lifetime document/store counts inconsistent")
        mapping = {}
        for i, row in enumerate(stored):
            if "error" in row:
                raise ValueError("G2 retained observation reports an error")
            if _g2_presentation(row.get("stored")) != initial[i]:
                raise ValueError("G2 retained-store presentation changed")
            valid = i != closed or stage < 2
            if row.get("is_valid_object") is not valid:
                raise ValueError("G2 invalid retained lifetime: closed reference must never revive")
            if not valid:
                if row.get("still_enumerated") is not False or row.get("comparisons") != []:
                    raise ValueError("G2 closed reference must be invalid and not compared")
                continue
            match, _ = _g2_matches(row.get("comparisons"), len(docs))
            if row.get("still_enumerated") is not True or _g2_presentation(docs[match]) != initial[i]:
                raise ValueError("G2 retained semantic match contradicts presentation")
            _g2_collector(row)
            mapping[i] = match
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("G2 distinct retained documents collapse onto one current document")
        enumerations = capture.get("enumeration_comparisons")
        if not isinstance(enumerations, list) or len(enumerations) != len(docs):
            raise ValueError("G2 second enumeration missing")
        starts, targets, references = [], [], []
        for row in enumerations:
            index = row.get("first_index")
            if not _is_int(index) or not 0 <= index < len(docs):
                raise ValueError("G2 first enumeration position invalid")
            target, reference = _g2_matches(row.get("comparisons"), len(docs))
            starts.append(index)
            targets.append(target)
            references.append(reference)
        if len(set(starts)) != len(docs) or len(set(targets)) != len(docs):
            raise ValueError("G2 enumeration mapping is not one-to-one")
        if capture.get("second_enumeration_same_objects") is not all(references):
            raise ValueError("G2 wrapper identity flag contradicts ReferenceEquals measurements")
        match_maps.append(mapping)
    replacement = record.get("replacement_current_index")
    final_docs = captures[-1]["documents"]
    if not _is_int(replacement) or not 0 <= replacement < len(final_docs):
        raise ValueError("G2 replacement position invalid")
    if replacement in match_maps[-1].values() or _g2_presentation(final_docs[replacement]) != initial[closed]:
        raise ValueError("G2 replacement must be unmatched by old live bindings and match closed presentation")
    check = _section(record, "replacement_retained", reasons)
    if "error" in check or "pf_error" in check:
        raise ValueError("G2 replacement observation reports an error")
    if check.get("probe") != "g2-retained-replacement" or check.get("original_valid") is not False:
        reasons.append("G2 replacement retained probe must show original invalid")
    rows, owner = check.get("retained"), record.get("replacement_owned_index")
    if not isinstance(rows, list) or not rows or not _is_int(owner) or owner < 0:
        raise ValueError("G2 replacement retained reference missing")
    owned = set()
    selected = []
    for row in rows:
        index = row.get("owned_index")
        if not _is_int(index) or index < 0 or index in owned:
            raise ValueError("G2 retained owned positions must be distinct")
        owned.add(index)
        matches = row.get("equals_matches")
        if row.get("valid") is not True or not isinstance(matches, list) or len(matches) != 1:
            raise ValueError("G2 replacement retained reference is not uniquely valid")
        target = matches[0]
        if not _is_int(target) or not 0 <= target < len(final_docs) or _g2_presentation(row) != _g2_presentation(final_docs[target]):
            raise ValueError("G2 replacement retained match/presentation inconsistent")
        _g2_collector(row)
        if index == owner:
            selected.append(target)
    if selected != [replacement]:
        reasons.append("G2 retained replacement does not resolve the new document")
    _g2_token_design(record, reasons)
    return _finish(reasons, "document-object-binding-provable")


@_never_raises
def classify_g2(record):
    """G2: document-object-binding-provable | stop."""
    reasons = _preamble(record)
    if not isinstance(record, dict):
        return STOP, reasons

    mechanism = record.get("binding_mechanism")
    if mechanism == "retained-reference-equals-v1":
        return _classify_retained_g2(record, reasons)
    if mechanism not in (None, "stable-wrapper-v1"):
        return STOP, reasons + ["unknown G2 binding mechanism"]

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
    pairs = _section(record, "same_title_pairs", reasons)
    if not valid:
        reasons.append("open_objects must list at least two documents with title, path, kind, object_id, raw_handle")
    else:
        observed = 0
        for kind in ("unsaved", "saved"):
            titles = [o["title"] for o in objs if o["kind"] == kind]
            has_pair = any(titles.count(t) >= 2 for t in titles)
            entry = pairs.get(kind)
            if not isinstance(entry, dict):
                reasons.append("same_title_pairs.{} is missing or not an object".format(kind))
            elif has_pair:
                observed += 1
                if entry.get("reproducible") is False:
                    reasons.append(
                        "contradictory record: same_title_pairs.{}.reproducible is false although "
                        "open_objects holds a same-title {} pair".format(kind, kind)
                    )
            elif not (entry.get("reproducible") is False and _nonblank(entry.get("attempt"))):
                reasons.append(
                    "no same-title {} pair and no recorded non-reproducible attempt".format(kind)
                )
        if not observed:
            reasons.append(
                "no same-title pair of any kind was observed, so same-title binding is unmeasured"
            )
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
_G4_CONTEXTS = ("command", "external-event")


@_never_raises
def classify_g4(record):
    """G4: explicit-activation-api | stop."""
    reasons = _preamble(record)
    if not isinstance(record, dict):
        return STOP, reasons

    if not _nonblank(record.get("api")):
        reasons.append("the activation API (name and overload) is not recorded")

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
        outcome, policy, context = case.get("outcome"), case.get("policy"), case.get("context")
        if context not in _G4_CONTEXTS:
            reasons.append(
                "case {} has an unknown or missing context (must be command or external-event)".format(name)
            )
        elif policy == "allow" and context != "external-event":
            reasons.append(
                "case {} is allowed but was not activated through an ExternalEvent, "
                "the context the routes use".format(name)
            )
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
        "context": None,
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
                "observation_method": None,
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
            "binding_mechanism": None,
            "closed_store_index": None,
            "survivor_store_index": None,
            "replacement_current_index": None,
            "replacement_owned_index": None,
            "captures": [{
                "probe": None, "probe_schema": None, "label": None,
                "documents": [{"title": None, "path": None, "kind": None}],
                "stored_objects": [{
                    "stored": {"title": None, "path": None, "kind": None},
                    "is_valid_object": None, "still_enumerated": None, "element_count": None,
                    "comparisons": [{"current_index": None, "equals": None, "reference_equals": None}],
                }],
                "second_enumeration_same_objects": None,
                "enumeration_comparisons": [{"first_index": None, "comparisons": [
                    {"current_index": None, "equals": None, "reference_equals": None}]}],
            }],
            "replacement_retained": {
                "probe": None, "original_valid": None,
                "retained": [{"owned_index": None, "title": None, "path": None,
                              "valid": None, "equals_matches": None, "element_count": None}],
            },
            "open_objects": [
                {"title": None, "path": None, "kind": None, "object_id": None, "raw_handle": None}
            ],
            "same_title_pairs": {
                "unsaved": {"reproducible": None, "attempt": None},
                "saved": {"reproducible": None, "attempt": None},
            },
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
    """Parse legacy Get-NetTCPConnection evidence; not used for OS collection.

    This source missed a real duplicate bind and cannot establish G5 completeness.
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


def _netstat_endpoint_port(endpoint):
    """Validate a numeric Windows netstat endpoint, including scoped IPv6."""
    host, separator, port = endpoint.rpartition(":")
    if not separator or not port.isascii() or not port.isdecimal():
        return None
    if not 0 <= int(port) <= 65535:
        return None
    try:
        if host.startswith("[") and host.endswith("]"):
            ipaddress.IPv6Address(host[1:-1])
        else:
            ipaddress.IPv4Address(host)
    except ValueError:
        return None
    return int(port)


def parse_netstat_listener_rows(text, ports):
    """Parse full Windows netstat TCP output without collapsing duplicate binds.

    Headers may be localized; TCP states must be recognized. A malformed row on
    ANY port makes the entire snapshot unusable. Header-only/empty output cannot
    establish an empty inventory, so it also returns None. This is a preflight
    observation, not a race-free reservation of the port.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    non_listening = {
        "CLOSED", "SYN_SENT", "SYN_RECEIVED", "ESTABLISHED", "FIN_WAIT_1",
        "FIN_WAIT_2", "CLOSE_WAIT", "CLOSING", "LAST_ACK", "TIME_WAIT",
        "DELETE_TCB", "BOUND",
    }
    result = dict((p, []) for p in ports)
    saw_row = False
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] != "TCP":
            # Before the first row only: netstat prints its banner and column
            # heading in the OEM code page and the host language, which an ANSI
            # locale mis-decodes (ru-RU: cp866 read as cp1251). Skip such lines
            # by shape, not by text. A skipped line must carry no host:port
            # token, so a garbled data row is never dropped as a heading.
            if not saw_row and all(_netstat_endpoint_port(f) is None for f in fields):
                continue
            return None
        if len(fields) != 5:
            return None
        _, local, remote, state, raw_pid = fields
        port = _netstat_endpoint_port(local)
        if port is None or _netstat_endpoint_port(remote) is None:
            return None
        if state != "LISTENING" and state not in non_listening:
            return None
        if not raw_pid.isascii() or not raw_pid.isdecimal():
            return None
        pid = int(raw_pid)
        if state == "LISTENING" and (pid == 0 or port == 0):
            return None
        saw_row = True
        if state == "LISTENING" and port in result and pid not in result[port]:
            result[port].append(pid)
    return result if saw_row else None


def os_listener_snapshot(ports, run=subprocess.run):
    """Full netstat listener PIDs per port, or None; never a cmdlet fallback."""
    try:
        done = run(
            ["netstat.exe", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            encoding="ascii",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    if done.returncode != 0:
        return None
    return parse_netstat_listener_rows(done.stdout, ports)


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
