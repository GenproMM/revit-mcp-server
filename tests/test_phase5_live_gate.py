# -*- coding: utf-8 -*-
"""Offline classifier and future operator procedure for the Phase 5 live gate.

This older-tier standalone CPython 3.11+ script does no work at import, defines no
``test_*`` functions, makes no request, and never reads, logs, prints, persists, or
sends a shared secret except that ``scan-secret`` loads it through ``bridge.load_secret``.
Pytest collects only ``tests/unit``.

Commands: ``template``, ``run``, ``classify``, ``classify-phase``, ``corrupt``,
``restore``, and ``scan-secret``. Output is PHASE5_GATE_OK or PHASE5_GATE_STOP.
Exit status is 0 (ok), 1 (stop), or 2 (usage). POSTS_SENT=0 means preflight stopped
before a write and permits a fresh-output rerun; POSTS_SENT>=1 consumes that stage
permanently. Do not make concurrent MCP calls while this procedure runs.

Operator order: 05-13 runs ``scripts/dev_secret.py``,
``deploy/make_manifest.py --allow-repo-dest --repo . --dest .``, restarts Revit, then
runs ``run --stage match``. 05-14 runs ``corrupt --module revit_mcp/<module>.py``,
restarts Revit, runs ``run --stage corrupt``, then ``restore --module``. 05-15 restarts
Revit, runs ``run --stage cleanup``, ``classify-phase``, then ``scan-secret`` on every
record. Each live write stage is one-shot.
"""
import argparse
import asyncio
import datetime
import json
import os
import subprocess
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
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory): raise ValueError("record directory does not exist")
    with open(path, "x", encoding="utf-8", newline="\n") as handle: json.dump(record, handle, indent=2, sort_keys=True); handle.write("\n")


def _load(path):
    with open(path, "r", encoding="utf-8") as handle: return json.load(handle)


def _print(result):
    print(SENTINEL_OK if result["verdict"] == VERDICT_OK else SENTINEL_STOP); print("STAGE={}".format(result["stage"])); print("POSTS_SENT={}".format(result["posts_sent"] if result["posts_sent"] is not None else "unknown"))
    for reason in result["reasons"]: print("REASON={}".format(reason))


MSG_NO_WRITE = "Nothing was written; the stage may be rerun with a fresh --out after correcting the stop reason."
MSG_CONSUMED = "This stage is consumed and must not be run again."


class _UsageError(Exception): pass


class _FakeMCP(object):
    """Small real-registration target: tools receive the same decorators as FastMCP."""
    def __init__(self): self.tools = {}

    def tool(self):
        def decorate(func):
            self.tools[func.__name__] = func
            return func
        return decorate


class _Parser(argparse.ArgumentParser):
    def error(self, message): raise _UsageError(message)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _plain(value):
    """Copy a reply for evidence without retaining an envelope or other custom type."""
    if isinstance(value, dict): return dict((str(k), _plain(v)) for k, v in value.items() if k != "_mcp")
    if isinstance(value, (list, tuple)): return [_plain(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)): return value
    return str(value)


def _bridge():
    """Lazy production bridge import: no transport or secret work occurs at script import."""
    if REPO_ROOT not in sys.path: sys.path.insert(0, REPO_ROOT)
    import bridge
    return bridge


def _direct_client(port):
    """The direct HTTP seam for non-tool checks; tests replace it with a mock client."""
    import httpx
    return httpx.AsyncClient(base_url="http://127.0.0.1:{}".format(port), timeout=30.0)


def _git(args, repo):
    completed = subprocess.run(["git"] + list(args), cwd=repo, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _valid_module(repo, module, require_clean=True):
    if not isinstance(module, str) or not module.startswith("revit_mcp/") or not module.endswith(".py") or "/_" in module:
        return "--module must be a tracked non-private revit_mcp/<name>.py"
    code, _out, _err = _git(["ls-files", "--error-unmatch", "--", module], repo)
    if code != 0: return "--module is not tracked: {}".format(module)
    if require_clean:
        code, out, _err = _git(["status", "--porcelain", "--", module], repo)
        if code != 0 or out: return "--module has uncommitted changes: {}".format(module)
    return None


def _repo_state(stage, module, repo=REPO_ROOT):
    manifest = os.path.join(repo, "_manifest.json")
    probe = os.path.join(repo, PROBE_FILE.replace("/", os.sep))
    module_path = os.path.join(repo, module.replace("/", os.sep)) if module else None
    if module is None:
        clean = True
    else:
        code, out, _err = _git(["status", "--porcelain", "--", module], repo)
        clean = code == 0 and not out
    return {"secret_file_present": os.path.isfile(os.path.join(repo, "revit_mcp", "_bridge_secret")),
            "manifest_present": os.path.isfile(manifest), "probe_present": os.path.isfile(probe),
            "module_clean": clean, "module_exists": bool(module_path and os.path.isfile(module_path))}


def _stage_state_reason(stage, state):
    required = {"match": (True, False, True), "corrupt": (True, True, False),
                "cleanup": (False, False, True)}[stage]
    current = (state["manifest_present"], state["probe_present"], state["module_clean"])
    return None if current == required else "repository state does not fit {}".format(stage)


def _run_refusal(args, bridge):
    if not _is_int(args.port) or not 1 <= args.port <= 65535: return "--port must be 1..65535"
    if not _text(args.out): return "--out must not be blank"
    if os.path.exists(args.out): return "--out already exists"
    if not _outside_repo(args.out): return "--out lies inside repository"
    if not os.path.isdir(os.path.dirname(os.path.abspath(args.out))): return "--out directory is missing"
    if args.stage != "match":
        problem = _valid_module(REPO_ROOT, args.module, require_clean=args.stage == "cleanup")
        if problem: return problem
    elif args.module is not None: return "match does not accept --module"
    state = _repo_state(args.stage, args.module)
    if not state["secret_file_present"]: return "revit_mcp/_bridge_secret is absent"
    fingerprint = bridge.loaded_secret_fingerprint()
    if fingerprint == bridge.secret_fingerprint(WRONG_SECRET): return "WRONG_SECRET equals bridge secret fingerprint"
    return _stage_state_reason(args.stage, state)


def _record_step(record, label, kind, route, body, reply=None, error=None, http=None):
    record["steps"][label] = {"kind": kind, "route": route, "sent": True, "http": http,
                               "body": _plain(reply) if isinstance(reply, dict) else None,
                               "text": reply if isinstance(reply, str) else json.dumps(_plain(reply), sort_keys=True),
                               "error": error}
    return record["steps"][label]


def _response_json(response):
    try: return response.json()
    except (ValueError, TypeError): return None


async def _direct_step(client, record, label, method, route, body=None):
    if route not in ALLOWED_ENDPOINTS: raise ValueError("endpoint not allowed: {}".format(route))
    sent = method == "POST"
    if sent: record["posts_sent"] += 1
    try:
        if method == "GET": response = await client.get("/genpro_revit_mcp" + route)
        else: response = await client.post("/genpro_revit_mcp" + route, content=json.dumps(body or {}), headers={"Content-Type": "text/plain; charset=utf-8"})
        value = _response_json(response)
        text = response.text if isinstance(response.text, str) else str(response.text)
        step = {"kind": "direct", "route": route, "sent": True, "http": response.status_code,
                "body": _plain(value), "text": text, "error": None}
    except Exception as ex:
        step = {"kind": "direct", "route": route, "sent": True, "http": None, "body": None,
                "text": "", "error": "{}: {}".format(type(ex).__name__, ex)}
    record["steps"][label] = step
    return step


async def _toolset(bridge, record):
    import tools
    fake = _FakeMCP()
    replies = {}

    async def posting(endpoint, data, *args, **kwargs):
        record["posts_sent"] += 1
        reply = await bridge.revit_post(endpoint, data, *args, **kwargs)
        replies[("POST", endpoint)] = reply
        return reply

    async def getting(endpoint, *args, **kwargs):
        reply = await bridge.revit_get(endpoint, *args, **kwargs)
        replies[("GET", endpoint)] = reply
        return reply

    for name in ("revit_target", "discover_targets", "secret_fingerprint"):
        if hasattr(bridge.revit_get, name):
            setattr(getting, name, getattr(bridge.revit_get, name))
    tools.register_tools(fake, getting, posting, getattr(bridge, "revit_image", None))
    return fake.tools, replies


def _tool_http(route, reply):
    if not isinstance(reply, dict):
        return None
    if route == "/status/" or reply.get("status") in ("success", "partial"):
        return 200
    return None


async def _tool_step(record, replies, label, route, func, *args, **kwargs):
    try:
        text = await func(*args, **kwargs)
        method = "GET" if route == "/status/" else "POST"
        reply = replies.get((method, route))
        record["steps"][label] = {"kind": "tool", "route": route, "sent": True,
                                   "http": _tool_http(route, reply), "body": _plain(reply) if isinstance(reply, dict) else None,
                                   "text": text, "error": None}
    except Exception as ex:
        record["steps"][label] = {"kind": "tool", "route": route, "sent": True, "http": None,
                                   "body": None, "text": "", "error": "{}: {}".format(type(ex).__name__, ex)}
    return record["steps"][label]


async def _live_preflight(bridge, client, args, record):
    pre = record["preflight"]
    try:
        response = await client.get("/genpro_revit_mcp/status/")
        pre["status_http"] = response.status_code
        pre["status"] = _response_json(response)
    except Exception as ex:
        return "status request failed: {}: {}".format(type(ex).__name__, ex)
    try: owners = bridge.listener_snapshot([args.port]).get(args.port)
    except Exception: owners = None
    pre["listeners"] = list(owners) if isinstance(owners, list) else owners
    pre["bridge_fingerprint"] = bridge.loaded_secret_fingerprint()
    pre["repo"] = _repo_state(args.stage, args.module)
    state_reason = _stage_state_reason(args.stage, pre["repo"])
    if state_reason is not None:
        return state_reason
    if response.status_code != 200: return "GET /status/ did not return 200"
    if not (isinstance(owners, list) and len(owners) == 1 and _is_int(owners[0])): return "expected exactly one listener"
    try:
        documents = await client.get("/genpro_revit_mcp/documents/")
        payload = _response_json(documents)
        found = payload.get("documents") if isinstance(payload, dict) else None
        pre["documents"] = len(found) if isinstance(found, list) else None
        pre["document"] = found[0] if isinstance(found, list) and len(found) == 1 else None
    except Exception as ex:
        return "documents request failed: {}: {}".format(type(ex).__name__, ex)
    if pre["documents"] != 1: return "expected exactly one document"
    return None


def _names(stage):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    return {"p_create": "P5_P_CREATE_{}".format(stamp), "n_missing": "P5_N_MISSING_{}".format(stamp),
            "n_mismatch": "P5_N_MISMATCH_{}".format(stamp), "m_create": "P5_M_CREATE_{}".format(stamp)}


async def _run_steps(bridge, client, args, record):
    names = record["inputs"]["names"]
    tools, replies = await _toolset(bridge, record)
    if args.stage == "match":
        await _direct_step(client, record, "n_missing", "POST", "/create_level/", {"levels": [{"name": names["n_missing"], "elevation": 1100.0}]})
        await _direct_step(client, record, "n_mismatch", "POST", "/create_level/", {"_mcp": {"secret": WRONG_SECRET}, "levels": [{"name": names["n_mismatch"], "elevation": 1200.0}]})
        await _direct_step(client, record, "n_code", "POST", "/execute_code/", {"code": "pass"})
        await _direct_step(client, record, "r_levels_open", "POST", "/document_levels/", {})
        await _direct_step(client, record, "r_levels_wrong", "POST", "/document_levels/", {"_mcp": {"secret": WRONG_SECRET}})
        try:
            bridge._secret_cache = WRONG_SECRET
            await _tool_step(record, replies, "b_wrong", "/create_level/", tools["create_level"], levels=[{"name": names["n_mismatch"], "elevation": 1300.0}])
        finally:
            bridge.reset_secret_cache()
        await _tool_step(record, replies, "p_create", "/create_level/", tools["create_level"], levels=[{"name": names["p_create"], "elevation": 1400.0}])
        await _direct_step(client, record, "p_levels", "GET", "/list_levels/")
        await _tool_step(record, replies, "s_status", "/status/", tools["get_revit_status"])
    elif args.stage == "corrupt":
        await _direct_step(client, record, "n_missing", "POST", "/create_level/", {"levels": [{"name": names["m_create"], "elevation": 1500.0}]})
        await _tool_step(record, replies, "m_create", "/create_level/", tools["create_level"], levels=[{"name": names["m_create"], "elevation": 1600.0}])
        await _tool_step(record, replies, "m_code", "/execute_code/", tools["execute_revit_code"], code="pass")
        await _direct_step(client, record, "r_levels_open", "POST", "/document_levels/", {})
        await _direct_step(client, record, "p_levels", "GET", "/list_levels/")
        await _tool_step(record, replies, "s_status", "/status/", tools["get_revit_status"])
    else:
        await _tool_step(record, replies, "p_create", "/create_level/", tools["create_level"], levels=[{"name": names["p_create"], "elevation": 1700.0}])
        await _direct_step(client, record, "p_levels", "GET", "/list_levels/")
        await _tool_step(record, replies, "s_status", "/status/", tools["get_revit_status"])


async def _cmd_run(args):
    bridge = _bridge()
    refusal = _run_refusal(args, bridge)
    if refusal:
        print("USAGE: {}".format(refusal), file=sys.stderr)
        return 2
    record = evidence_template(args.stage)
    record["started_at"] = _now()
    record["inputs"].update({"port": args.port, "stamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S"),
                             "module": args.module, "names": _names(args.stage)})
    record["posts_sent"] = 0
    client = _direct_client(args.port)
    try:
        reason = await _live_preflight(bridge, client, args, record)
        if reason is None: await _run_steps(bridge, client, args, record)
        else: record["stop_reason"] = reason
    except Exception as ex:
        record["stop_reason"] = "unexpected {}: {}".format(type(ex).__name__, ex)
    finally:
        close = getattr(client, "aclose", None)
        if close is not None: await close()
    _save(args.out, record)
    result = classify_stage(args.stage, record)
    _print(result)
    if record["posts_sent"] == 0: print(MSG_NO_WRITE)
    else: print(MSG_CONSUMED)
    return 0 if result["verdict"] == VERDICT_OK else 1


def corrupt(repo, module):
    """Create the D-12 modified and unexpected files, refusing unrelated local work."""
    if not os.path.isfile(os.path.join(repo, "_manifest.json")): raise ValueError("_manifest.json is absent")
    if os.path.exists(os.path.join(repo, PROBE_FILE.replace("/", os.sep))): raise ValueError("probe already exists")
    problem = _valid_module(repo, module)
    if problem: raise ValueError(problem)
    path = os.path.join(repo, module.replace("/", os.sep))
    with open(path, "rb") as handle: source = handle.read()
    ending = b"\r\n" if b"\r\n" in source else b"\n"
    line = b"# phase5 live gate: deliberate integrity mismatch (D-12); restore with tests/test_phase5_live_gate.py restore"
    with open(path, "ab") as handle: handle.write(ending + line + ending)
    probe = os.path.join(repo, PROBE_FILE.replace("/", os.sep))
    with open(probe, "wb") as handle: handle.write(b'# -*- coding: utf-8 -*-\n"Unexpected Phase 5 live-gate probe; never imported."\n')


def restore(repo, module=None):
    """Remove temporary integrity evidence and restore only the optional named tracked module."""
    reasons = []
    for relative in ("_manifest.json", "_manifest.json.tmp", PROBE_FILE):
        path = os.path.join(repo, relative.replace("/", os.sep))
        try:
            if os.path.lexists(path): os.remove(path)
        except OSError as ex: reasons.append("{}: {}".format(relative, ex))
    if module is not None:
        problem = _valid_module(repo, module, require_clean=False)
        if problem: reasons.append(problem)
        else:
            code, _out, err = _git(["checkout", "--", module], repo)
            if code != 0: reasons.append("{}: {}".format(module, err or "git checkout failed"))
    checks = [PROBE_FILE]
    if module is not None: checks.append(module)
    for relative in checks:
        code, out, _err = _git(["status", "--porcelain", "--", relative], repo)
        if code != 0 or out: reasons.append("{} remains modified".format(relative))
    if os.path.exists(os.path.join(repo, "_manifest.json")): reasons.append("_manifest.json remains")
    return reasons


def scan_secret(paths, bridge=None):
    bridge = _bridge() if bridge is None else bridge
    secret = bridge.load_secret()
    if secret is None: return 2, None
    for path in paths:
        try:
            with open(path, "rb") as handle: text = handle.read().decode("utf-8", "replace")
        except OSError: return 2, None
        if secret in text: return 1, path
    return 0, None


def main(argv=None):
    try:
        parser = _Parser(prog="test_phase5_live_gate.py"); commands = parser.add_subparsers(dest="command", required=True)
        template = commands.add_parser("template"); template.add_argument("--stage", choices=STAGES, required=True)
        classify = commands.add_parser("classify"); classify.add_argument("--stage", choices=STAGES, required=True); classify.add_argument("record")
        phase = commands.add_parser("classify-phase"); phase.add_argument("records", nargs=3)
        run = commands.add_parser("run"); run.add_argument("--stage", choices=STAGES, required=True); run.add_argument("--out", required=True); run.add_argument("--port", type=int, default=48884); run.add_argument("--module")
        corrupt_cmd = commands.add_parser("corrupt"); corrupt_cmd.add_argument("--module", required=True)
        restore_cmd = commands.add_parser("restore"); restore_cmd.add_argument("--module")
        scan = commands.add_parser("scan-secret"); scan.add_argument("files", nargs="+")
        args = parser.parse_args(argv)
        if args.command == "template": print(json.dumps(evidence_template(args.stage), indent=2, sort_keys=True)); return 0
        if args.command == "classify": result = classify_stage(args.stage, _load(args.record)); _print(result); return 0 if result["verdict"] == VERDICT_OK else 1
        if args.command == "classify-phase":
            result = classify_phase([_load(path) for path in args.records]); print(SENTINEL_OK if result["verdict"] == VERDICT_OK else SENTINEL_STOP)
            for item in result["stages"]: print("STAGE={} VERDICT={} POSTS_SENT={}".format(item["stage"], item["verdict"], item["posts_sent"] if item["posts_sent"] is not None else "unknown"))
            return 0 if result["verdict"] == VERDICT_OK else 1
        if args.command == "run": return asyncio.run(_cmd_run(args))
        if args.command == "corrupt":
            corrupt(REPO_ROOT, args.module); print("CORRUPTED modified={} unexpected={}".format(args.module, PROBE_FILE)); return 0
        if args.command == "restore":
            reasons = restore(REPO_ROOT, args.module)
            if not reasons: print("RESTORED clean"); return 0
            print("RESTORE_INCOMPLETE: {}".format("; ".join(reasons)), file=sys.stderr); return 1
        if args.command == "scan-secret":
            code, found = scan_secret(args.files)
            if code == 0: print("SECRET_ABSENT")
            elif code == 1: print("SECRET_FOUND {}".format(found))
            else: print("SECRET_UNAVAILABLE")
            return code
    except (OSError, ValueError, json.JSONDecodeError, _UsageError) as ex:
        print("USAGE: {}".format(ex), file=sys.stderr); return 2

if __name__ == "__main__": sys.exit(main())
