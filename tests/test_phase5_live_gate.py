# -*- coding: utf-8 -*-
"""Offline classifier and future operator procedure for the Phase 5 live gate.

This older-tier standalone CPython 3.11+ script does no work at import, defines no
``test_*`` functions, makes no request, and never reads, logs, prints, persists, or
sends a shared secret. Pytest collects only ``tests/unit``.

Commands: ``template``, ``run``, ``classify``, ``classify-phase``, ``corrupt``,
``restore``, and ``scan-secret``. Plans 05-12 completes run and maintenance commands.
Output is PHASE5_GATE_OK or PHASE5_GATE_STOP. Exit status is 0 (ok), 1 (stop), or 2
(usage). POSTS_SENT=0 means preflight stopped before a write and permits a fresh-output
rerun after correction; POSTS_SENT>=1 consumes that stage permanently. Later operators
fully restart Revit with no model, open one unsaved project in its UI, confirm exactly
one listener, and make no concurrent MCP calls while this procedure runs.
"""
import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENTINEL_OK = "PHASE5_GATE_OK"
SENTINEL_STOP = "PHASE5_GATE_STOP"
VERDICT_OK = "ok"
VERDICT_STOP = "stop"
STAGES = ("match", "corrupt", "cleanup")
STEP_IDS = {
    "match": ("n_missing", "n_mismatch", "n_code", "r_levels_open", "r_levels_wrong", "b_wrong", "p_create", "p_levels", "s_status"),
    "corrupt": ("n_missing", "m_create", "m_code", "r_levels_open", "p_levels", "s_status"),
    "cleanup": ("p_create", "p_levels", "s_status"),
}
EXPECTED_POSTS = {"match": 7, "corrupt": 4, "cleanup": 1}
ALLOWED_ENDPOINTS = {"/status/", "/documents/", "/list_levels/", "/document_levels/", "/create_level/", "/execute_code/"}
PROBE_FILE = "revit_mcp/_zz_probe.py"
WRONG_SECRET = "0000000000000000000000000000000000000000"


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _hex8(value):
    return isinstance(value, str) and len(value) == 8 and all(c in "0123456789abcdef" for c in value)


def _add(reasons, path, detail):
    reasons.append("{}: {}".format(path, detail))


def _contains(value, text):
    if isinstance(value, str):
        return text in value
    if isinstance(value, dict):
        return any(_contains(item, text) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, text) for item in value)
    return False


def _error_body(text, status):
    prefix = "Error: {} - ".format(status)
    if not isinstance(text, str) or not text.startswith(prefix):
        return None
    try:
        value = json.loads(text[len(prefix):])
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def evidence_template(stage):
    """Fresh, all-empty stage record skeleton; unknown stages raise ValueError."""
    if stage not in STAGES:
        raise ValueError("unknown stage {!r}".format(stage))
    return {"schema": 1, "stage": stage, "started_at": None,
            "inputs": {"port": None, "stamp": None, "module": None, "names": {}},
            "posts_sent": None,
            "preflight": {"listeners": None, "documents": None, "document": None,
                          "status_http": None, "status": None, "bridge_fingerprint": None,
                          "repo": {"secret_file_present": None, "manifest_present": None,
                                   "probe_present": None, "module_clean": None}},
            "steps": dict((key, None) for key in STEP_IDS[stage])}


def _shape(stage, record, reasons):
    if not isinstance(record, dict):
        _add(reasons, "record", "expected object")
        return None, None, None
    if record.get("schema") != 1:
        _add(reasons, "schema", "expected 1")
    if record.get("stage") != stage:
        _add(reasons, "stage", "expected {!r}".format(stage))
    if not _text(record.get("started_at")):
        _add(reasons, "started_at", "expected ISO text")
    inputs, preflight, steps = record.get("inputs"), record.get("preflight"), record.get("steps")
    if not isinstance(inputs, dict):
        _add(reasons, "inputs", "expected object"); inputs = None
    if not isinstance(preflight, dict):
        _add(reasons, "preflight", "expected object"); preflight = None
    if not isinstance(steps, dict):
        _add(reasons, "steps", "expected object"); steps = None
    posts = record.get("posts_sent")
    if not _is_int(posts) or posts < 0:
        _add(reasons, "posts_sent", "expected non-negative integer")
    elif posts != EXPECTED_POSTS[stage]:
        _add(reasons, "posts_sent", "expected {}".format(EXPECTED_POSTS[stage]))
    return inputs, preflight, steps


def _inputs(stage, inputs, reasons):
    if inputs is None:
        return {}
    if not (_is_int(inputs.get("port")) and 1 <= inputs.get("port") <= 65535):
        _add(reasons, "inputs.port", "expected port integer")
    if not _text(inputs.get("stamp")):
        _add(reasons, "inputs.stamp", "expected text")
    names = inputs.get("names")
    if not isinstance(names, dict):
        _add(reasons, "inputs.names", "expected object"); names = {}
    for key in ("p_create",):
        if not _text(names.get(key)):
            _add(reasons, "inputs.names.{}".format(key), "expected level-name text")
    module = inputs.get("module")
    if stage == "match" and module is not None:
        _add(reasons, "inputs.module", "expected null")
    if stage != "match" and not (_text(module) and module.startswith("revit_mcp/") and module.endswith(".py") and "/_" not in module):
        _add(reasons, "inputs.module", "expected Revit module path")
    return names


def _preflight(stage, pre, reasons):
    if pre is None:
        return {}, {}, {}
    listeners = pre.get("listeners")
    if not (isinstance(listeners, list) and len(listeners) == 1 and _is_int(listeners[0])):
        _add(reasons, "preflight.listeners", "expected exactly one PID")
    if pre.get("documents") != 1 or not _is_int(pre.get("documents")):
        _add(reasons, "preflight.documents", "expected exactly one document")
    if not isinstance(pre.get("document"), dict):
        _add(reasons, "preflight.document", "expected selector object")
    if pre.get("status_http") != 200:
        _add(reasons, "preflight.status_http", "expected 200")
    fp = pre.get("bridge_fingerprint")
    if not _hex8(fp):
        _add(reasons, "preflight.bridge_fingerprint", "expected 8 lowercase hex")
    status = pre.get("status")
    if not isinstance(status, dict):
        _add(reasons, "preflight.status", "expected object"); status = {}
    secret = status.get("secret")
    if not isinstance(secret, dict):
        _add(reasons, "preflight.status.secret", "expected object")
    else:
        if secret.get("configured") is not True:
            _add(reasons, "preflight.status.secret.configured", "expected true")
        if not _hex8(secret.get("fingerprint")):
            _add(reasons, "preflight.status.secret.fingerprint", "expected 8 lowercase hex")
        elif secret.get("fingerprint") != fp:
            _add(reasons, "preflight.status.secret.fingerprint", "does not equal bridge_fingerprint")
    integrity = status.get("integrity")
    if not isinstance(integrity, dict):
        _add(reasons, "preflight.status.integrity", "expected object"); integrity = {}
    if status.get("bind") != "loopback_only":
        _add(reasons, "preflight.status.bind", "expected loopback_only")
    repo = pre.get("repo")
    if not isinstance(repo, dict):
        _add(reasons, "preflight.repo", "expected object"); repo = {}
    for name in ("secret_file_present", "manifest_present", "probe_present", "module_clean"):
        if not isinstance(repo.get(name), bool):
            _add(reasons, "preflight.repo.{}".format(name), "expected boolean")
    return status, integrity, repo


def _step(steps, label, kind, route, reasons):
    value = steps.get(label) if isinstance(steps, dict) else None
    if not isinstance(value, dict):
        _add(reasons, "steps.{}".format(label), "step was not recorded")
        return None
    if value.get("kind") != kind: _add(reasons, "steps.{}.kind".format(label), "wrong kind")
    if value.get("route") != route: _add(reasons, "steps.{}.route".format(label), "wrong route")
    if value.get("sent") is not True: _add(reasons, "steps.{}.sent".format(label), "expected true")
    if value.get("http") is not None and not _is_int(value.get("http")): _add(reasons, "steps.{}.http".format(label), "wrong type")
    if value.get("body") is not None and not isinstance(value.get("body"), dict): _add(reasons, "steps.{}.body".format(label), "wrong type")
    if not isinstance(value.get("text"), str): _add(reasons, "steps.{}.text".format(label), "expected text")
    if value.get("error") is not None and not isinstance(value.get("error"), str): _add(reasons, "steps.{}.error".format(label), "wrong type")
    return value


def _auth(label, step, auth, reasons):
    if step is None: return
    if step.get("http") != 401: _add(reasons, "steps.{}.http".format(label), "expected 401")
    body = step.get("body")
    if not isinstance(body, dict): _add(reasons, "steps.{}.body".format(label), "expected object")
    else:
        if body.get("auth") != auth: _add(reasons, "steps.{}.body.auth".format(label), "expected {!r}".format(auth))
        if "outcome" in body: _add(reasons, "steps.{}.body.outcome".format(label), "must be absent")


def _committed(label, step, reasons):
    if step is None: return
    if step.get("http") != 200: _add(reasons, "steps.{}.http".format(label), "expected 200")
    body = step.get("body")
    outcome = body.get("outcome") if isinstance(body, dict) else None
    if not isinstance(outcome, dict): _add(reasons, "steps.{}.body.outcome".format(label), "expected object")
    elif outcome.get("transaction_status") != "Committed": _add(reasons, "steps.{}.body.outcome.transaction_status".format(label), "expected Committed")


def _levels(label, step, accepted, rejected, reasons):
    if step is None: return
    if step.get("http") != 200: _add(reasons, "steps.{}.http".format(label), "expected 200")
    body = step.get("body")
    if not isinstance(body, dict): _add(reasons, "steps.{}.body".format(label), "expected object"); return
    if accepted and not _contains(body, accepted): _add(reasons, "steps.{}.body".format(label), "missing accepted name")
    for name in rejected:
        if _contains(body, name): _add(reasons, "steps.{}.body".format(label), "contains rejected name")


def _match(record, reasons):
    inputs, pre, steps = _shape("match", record, reasons); names = _inputs("match", inputs, reasons); status, integrity, repo = _preflight("match", pre, reasons)
    if integrity.get("state") != "verified_match": _add(reasons, "preflight.status.integrity.state", "expected verified_match")
    if status.get("health") != "healthy": _add(reasons, "preflight.status.health", "expected healthy")
    for key, expected in (("secret_file_present", True), ("manifest_present", True), ("probe_present", False), ("module_clean", True)):
        if repo.get(key) is not expected: _add(reasons, "preflight.repo.{}".format(key), "wrong value")
    specs = (("n_missing", "direct", "/create_level/"), ("n_mismatch", "direct", "/create_level/"), ("n_code", "direct", "/execute_code/"), ("r_levels_open", "direct", "/document_levels/"), ("r_levels_wrong", "direct", "/document_levels/"), ("b_wrong", "tool", "/create_level/"), ("p_create", "tool", "/create_level/"), ("p_levels", "direct", "/list_levels/"), ("s_status", "tool", "/status/"))
    found = dict((label, _step(steps, label, kind, route, reasons)) for label, kind, route in specs)
    for label, auth in (("n_missing", "missing"), ("n_mismatch", "mismatch"), ("n_code", "missing")): _auth(label, found[label], auth, reasons)
    for label in ("r_levels_open", "r_levels_wrong"):
        if found[label] is not None and found[label].get("http") != 200: _add(reasons, "steps.{}.http".format(label), "expected 200")
    wrong = found["b_wrong"]
    if wrong is not None and (_error_body(wrong.get("text"), 401) or {}).get("auth") != "mismatch": _add(reasons, "steps.b_wrong.text", "expected Error: 401 - mismatch")
    _committed("p_create", found["p_create"], reasons)
    _levels("p_levels", found["p_levels"], names.get("p_create"), [v for k, v in names.items() if k != "p_create" and isinstance(v, str)], reasons)
    if found["s_status"] is not None and "both halves hold the same secret" not in found["s_status"].get("text", ""): _add(reasons, "steps.s_status.text", "missing same-secret message")


def _corrupt(record, reasons):
    inputs, pre, steps = _shape("corrupt", record, reasons); names = _inputs("corrupt", inputs, reasons); status, integrity, repo = _preflight("corrupt", pre, reasons); module = inputs.get("module")
    if integrity.get("state") != "verified_mismatch": _add(reasons, "preflight.status.integrity.state", "expected verified_mismatch")
    if integrity.get("modified") != [module]: _add(reasons, "preflight.status.integrity.modified", "expected chosen module")
    if integrity.get("unexpected") != [PROBE_FILE]: _add(reasons, "preflight.status.integrity.unexpected", "expected probe")
    if integrity.get("missing") != []: _add(reasons, "preflight.status.integrity.missing", "expected empty")
    if status.get("health") != "degraded": _add(reasons, "preflight.status.health", "expected degraded")
    alerts = status.get("security_alerts")
    if not (isinstance(alerts, list) and alerts and all(isinstance(v, str) for v in alerts)): _add(reasons, "preflight.status.security_alerts", "expected non-empty text list")
    if repo.get("probe_present") is not True: _add(reasons, "preflight.repo.probe_present", "expected true")
    specs = (("n_missing", "direct", "/create_level/"), ("m_create", "tool", "/create_level/"), ("m_code", "tool", "/execute_code/"), ("r_levels_open", "direct", "/document_levels/"), ("p_levels", "direct", "/list_levels/"), ("s_status", "tool", "/status/"))
    found = dict((label, _step(steps, label, kind, route, reasons)) for label, kind, route in specs); _auth("n_missing", found["n_missing"], "missing", reasons)
    for label in ("m_create", "m_code"):
        step = found[label]; body = _error_body(step.get("text"), 423) if step is not None else None
        if step is not None and (step.get("http") is not None or not isinstance(body, dict) or body.get("integrity") != "verified_mismatch" or set(body.get("files", [])) != {PROBE_FILE, module}): _add(reasons, "steps.{}.text".format(label), "expected Error: 423 - naming both files")
    if found["r_levels_open"] is not None and found["r_levels_open"].get("http") != 200: _add(reasons, "steps.r_levels_open.http", "expected 200")
    _levels("p_levels", found["p_levels"], "", [names.get("m_create")], reasons)
    text = found["s_status"].get("text", "") if found["s_status"] else ""
    if "verified_mismatch" not in text or PROBE_FILE not in text or module not in text: _add(reasons, "steps.s_status.text", "missing mismatch files")


def _cleanup(record, reasons):
    inputs, pre, steps = _shape("cleanup", record, reasons); names = _inputs("cleanup", inputs, reasons); status, integrity, repo = _preflight("cleanup", pre, reasons)
    if integrity.get("state") != "unverifiable": _add(reasons, "preflight.status.integrity.state", "expected unverifiable")
    if integrity.get("reason") != "manifest_missing": _add(reasons, "preflight.status.integrity.reason", "expected manifest_missing")
    if status.get("health") != "healthy": _add(reasons, "preflight.status.health", "expected healthy")
    for key, expected in (("manifest_present", False), ("probe_present", False), ("module_clean", True)):
        if repo.get(key) is not expected: _add(reasons, "preflight.repo.{}".format(key), "wrong value")
    specs = (("p_create", "tool", "/create_level/"), ("p_levels", "direct", "/list_levels/"), ("s_status", "tool", "/status/"))
    found = dict((label, _step(steps, label, kind, route, reasons)) for label, kind, route in specs); _committed("p_create", found["p_create"], reasons); _levels("p_levels", found["p_levels"], names.get("p_create"), [], reasons)
    if found["s_status"] is not None and "unverifiable" not in found["s_status"].get("text", ""): _add(reasons, "steps.s_status.text", "missing unverifiable")


def _posts(record):
    value = record.get("posts_sent") if isinstance(record, dict) else None
    return value if _is_int(value) and value >= 0 else None


def classify_stage(stage, record):
    """Pure, strict, never-raising stage classification."""
    reasons = []
    try:
        if stage not in STAGES: _add(reasons, "stage", "unknown stage")
        elif stage == "match": _match(record, reasons)
        elif stage == "corrupt": _corrupt(record, reasons)
        else: _cleanup(record, reasons)
    except Exception as ex:
        _add(reasons, "classifier-error", "{}: {}".format(type(ex).__name__, ex))
    return {"stage": stage, "verdict": VERDICT_OK if not reasons else VERDICT_STOP, "reasons": reasons, "posts_sent": _posts(record)}


def classify_phase(records):
    """Accept exactly one fully valid record per stage; pure and fail-closed."""
    results, reasons = [], []
    try:
        if not isinstance(records, list): records = []; reasons.append("records: expected list")
        for stage in STAGES:
            selected = [item for item in records if isinstance(item, dict) and item.get("stage") == stage]
            if len(selected) != 1:
                reasons.append("stage {}: expected exactly one record".format(stage)); result = {"stage": stage, "verdict": VERDICT_STOP, "reasons": ["record count"], "posts_sent": None}
            else:
                result = classify_stage(stage, selected[0])
                if result["verdict"] != VERDICT_OK: reasons.append("stage {}: {}".format(stage, "; ".join(result["reasons"])))
            results.append(result)
        if len(records) != len(STAGES): reasons.append("records: expected exactly three")
    except Exception as ex:
        reasons.append("classifier-error: {}: {}".format(type(ex).__name__, ex))
    return {"verdict": VERDICT_OK if not reasons else VERDICT_STOP, "reasons": reasons, "stages": results}


def _outside_repo(path):
    try: return os.path.commonpath([os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(REPO_ROOT))]) != os.path.normcase(os.path.realpath(REPO_ROOT))
    except ValueError: return True


def _save(path, record):
    if os.path.exists(path): raise ValueError("record already exists")
    if not _outside_repo(path): raise ValueError("record path is inside repository")
    with open(path, "x", encoding="utf-8", newline="\n") as handle: json.dump(record, handle, indent=2, sort_keys=True); handle.write("\n")


def _load(path):
    with open(path, "r", encoding="utf-8") as handle: return json.load(handle)


def _print(result):
    print(SENTINEL_OK if result["verdict"] == VERDICT_OK else SENTINEL_STOP); print("STAGE={}".format(result["stage"])); print("POSTS_SENT={}".format(result["posts_sent"] if result["posts_sent"] is not None else "unknown"))
    for reason in result["reasons"]: print("REASON={}".format(reason))


class _UsageError(Exception): pass

class _Parser(argparse.ArgumentParser):
    def error(self, message): raise _UsageError(message)


def main(argv=None):
    try:
        parser = _Parser(prog="test_phase5_live_gate.py"); commands = parser.add_subparsers(dest="command", required=True)
        template = commands.add_parser("template"); template.add_argument("--stage", choices=STAGES, required=True)
        classify = commands.add_parser("classify"); classify.add_argument("--stage", choices=STAGES, required=True); classify.add_argument("record")
        phase = commands.add_parser("classify-phase"); phase.add_argument("records", nargs=3)
        for name in ("run", "corrupt", "restore", "scan-secret"): commands.add_parser(name)
        args = parser.parse_args(argv)
        if args.command == "template": print(json.dumps(evidence_template(args.stage), indent=2, sort_keys=True)); return 0
        if args.command == "classify": result = classify_stage(args.stage, _load(args.record)); _print(result); return 0 if result["verdict"] == VERDICT_OK else 1
        if args.command == "classify-phase":
            result = classify_phase([_load(path) for path in args.records]); print(SENTINEL_OK if result["verdict"] == VERDICT_OK else SENTINEL_STOP)
            for item in result["stages"]: print("STAGE={} VERDICT={} POSTS_SENT={}".format(item["stage"], item["verdict"], item["posts_sent"] if item["posts_sent"] is not None else "unknown"))
            return 0 if result["verdict"] == VERDICT_OK else 1
        raise _UsageError("{} is not implemented until plan 05-12".format(args.command))
    except (OSError, ValueError, json.JSONDecodeError, _UsageError) as ex:
        print("USAGE: {}".format(ex), file=sys.stderr); return 2

if __name__ == "__main__": sys.exit(main())
