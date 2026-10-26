# -*- coding: utf-8 -*-
"""Operator-run Phase 7 live acceptance bench; all unit tests are offline.

Importing this older-tier CPython script performs no I/O, network work, Revit work,
policy loading, or secret loading. The operator runs it only on one disposable,
non-workshared model after fully closing and reopening Revit. Records are local and
outside the repository, are never overwritten, and direct runs are one-shot.

``preflight`` is read-only. ``direct`` sends S6, S5a, S5b and S5c directly to Routes,
not through MCP tools, and deliberately mints permits from the readable shared secret.
That proves the documented D-18 readable-secret limit; it is not a shipped feature and
must only run on the disposable model. A network-hosted operator policy makes this bench
stop before a request: it is not read as a workaround. ``ingest`` combines pasted local
observations with audit JSONL. Audit data, not pasted claims, proves decision, approval,
outcome, tool and route. H6 remains ``not_verified``.

Operator procedure: confirm exactly one listener with ``Get-NetTCPConnection -LocalPort
<port> -State Listen`` after a full Revit restart (never pyRevit Reload). Open ONE disposable
model through ``open_model``, never on the Revit command line and never save it. Run
preflight, then direct once. In Hermes Desktop ask H1 «удали элемент <A>» and answer yes;
H2 «удали элемент <B>» and answer no; H3 «удали элемент <C>» and wait over five minutes;
H4 decline a deletion, then send that same request again, observing two operation codes;
H5 ask «сдвинь
элемент <D> на 12.5 мм по X» and answer yes. Keep replies and audit logs locally. The
``--replies`` file must be JSON: h1={call_id, element_gone:true}, h2={call_id,
element_present:true}, h3={call_id}, h4={call_ids:[first,second]}, h5={call_id,
fractional_mm:12.5}, h6={status:"not_verified"}. Use the real IDs from the Audit reply lines.
Ingest joins this JSON to local audit-*.jsonl files; classify judges the resulting record.
Close the disposable model without saving. No Telegram/gateway acceptance is claimed.

POSTS_SENT=0 means no write was handed to transport. POSTS_SENT>=1 consumes the direct
run and it must never be repeated. ``classify`` sends nothing and prints a Phase 7
sentinel plus POSTS_SENT and SECRET_OCCURRENCES. Exit statuses: 0 OK, 1 STOP, 2 refusal
before a write. A failure after a post still prints STOP and the nonzero count.
"""

import argparse
import asyncio
import ctypes
import json
import os
import re
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENTINEL_OK = "PHASE7_BENCH_OK"
SENTINEL_STOP = "PHASE7_BENCH_STOP"
LEVEL_PREFIX = "phase7-bench-"
VERDICT_OK = "ok"
VERDICT_STOP = "stop"
ALLOWED_ENDPOINTS = frozenset(("/status/", "/list_levels/", "/create_level/", "/create_grid/"))
SCENARIOS = {
    "h1": ("delete_elements", "/delete_elements/"),
    "h2": ("delete_elements", "/delete_elements/"),
    "h3": ("delete_elements", "/delete_elements/"),
    "h4": ("delete_elements", "/delete_elements/"),
    "h5": ("transform_elements", "/transform_elements/"),
}


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _windows_path_is_local(path):
    """No filesystem I/O: reject UNC/device paths and mapped network drives."""
    if not isinstance(path, str) or not path.strip():
        return False
    value = path.strip()
    if value.startswith(("\\\\", "//", "\\\\?\\", "\\\\.\\")):
        return False
    drive, _tail = os.path.splitdrive(os.path.abspath(value))
    if not drive:
        return True
    try:
        kind = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")
    except (AttributeError, OSError):
        return False
    return kind in (2, 3, 5, 6)  # known local drives only; unknown/no-root fail closed


def _local_path(path):
    """Validate a lexical path before exists/realpath/open; POSIX test paths are local."""
    if not _text(path):
        return None
    if os.name == "nt" and not _windows_path_is_local(path):
        return None
    lexical = os.path.abspath(path)
    # Never resolve a local junction/symlink that could redirect into a share.
    if os.name == "nt":
        drive, tail = os.path.splitdrive(lexical)
        current = drive + os.sep
        for component in tail.strip("\\/").replace("/", "\\").split("\\"):
            current = os.path.join(current, component)
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                break
            except OSError:
                return None
            if getattr(info, "st_file_attributes", 0) & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
                return None
    resolved = os.path.realpath(lexical)
    if os.name == "nt" and not _windows_path_is_local(resolved):
        return None
    return resolved


def _outside_repo(path):
    checked = _local_path(path)
    if checked is None:
        return False
    root = os.path.normcase(os.path.realpath(REPO_ROOT))
    try:
        return os.path.commonpath([os.path.normcase(checked), root]) != root
    except ValueError:
        return True


def secret_occurrences(data, secret):
    """Count whole, JSON-escaped and 16-character-run leaks without returning the secret."""
    if not (_text(secret) and isinstance(data, (str, bytes, bytearray))):
        return 0
    raw = data.encode("utf-8", "replace") if isinstance(data, str) else bytes(data)
    total = 0
    forms = [secret]
    escaped = json.dumps(secret)[1:-1]
    if escaped != secret:
        forms.append(escaped)
    for form in forms:
        needle = form.encode("utf-8", "replace")
        total += raw.count(needle)
        raw = raw.replace(needle, b"\x00")
    if len(secret) >= 16:
        for run in set(secret[index:index + 16] for index in range(len(secret) - 15)):
            total += raw.count(run.encode("utf-8", "replace"))
    return total


def evidence_template():
    return {
        "schema": 1,
        "preflight": {"status_http": None, "listeners": None, "identity": None,
                      "permit_protocol": None, "revit_version": None, "policy": None},
        "direct": {"s6": None, "s5a": None, "s5b": None, "s5c": None},
        "hermes": {"h1": {"call_id": None, "element_gone": None},
                   "h2": {"call_id": None, "element_present": None},
                   "h3": {"call_id": None}, "h4": {"call_ids": []},
                   "h5": {"call_id": None, "fractional_mm": None},
                   "h6": {"status": "not_verified"}},
        "audit_files": {}, "posts_sent": 0, "revit_version": None, "policy": None,
    }


def _record_bytes(record):
    try:
        return json.dumps(record, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8", "replace")
    except Exception:
        return b""


def _add(reasons, path, detail):
    reasons.append("{}: {}".format(path, detail))


def _permit_verdict(step):
    value = _dict(step).get("permit")
    return _dict(value).get("verdict") or _dict(value).get("status") if isinstance(value, dict) else value


def judge_preflight(preflight):
    reasons = []
    data = _dict(preflight)
    if data.get("status_http") != 200:
        _add(reasons, "preflight.status_http", "expected 200")
    listeners = data.get("listeners")
    if not (isinstance(listeners, list) and len(listeners) == 1 and _is_int(listeners[0]) and listeners[0] > 0):
        _add(reasons, "preflight.listeners", "expected exactly one listener")
    identity = _dict(data.get("identity"))
    token = identity.get("session_token")
    try:
        token_ok = _text(token) and str(uuid.UUID(token)) == token
    except (ValueError, AttributeError):
        token_ok = False
    if not token_ok or not _is_int(identity.get("pid")) or identity.get("pid") != (listeners[0] if isinstance(listeners, list) and len(listeners) == 1 else None):
        _add(reasons, "preflight.identity", "must match listener with UUID session token")
    if (not _is_int(data.get("port")) or not 1 <= data["port"] <= 65535 or
            not _is_int(identity.get("actual_port")) or identity.get("actual_port") != data.get("port")):
        _add(reasons, "preflight.identity.actual_port", "must match requested port")
    if data.get("permit_protocol") != 1:
        _add(reasons, "preflight.permit_protocol", "extension does not advertise permits")
    if not _text(data.get("revit_version")):
        _add(reasons, "preflight.revit_version", "missing Revit version")
    policy = _dict(data.get("policy"))
    if not (_text(policy.get("source")) and _text(policy.get("hash")) and
            policy.get("blocked") is False and policy.get("operator_state") in ("not_configured", "absent", "accepted")):
        _add(reasons, "preflight.policy", "policy is blocked, invalid, unreachable or incomplete")
    return reasons


def judge_direct(direct):
    reasons, steps = [], _dict(direct)
    s6 = _dict(steps.get("s6"))
    if s6.get("http") != 403 or _permit_verdict(s6) != "missing":
        _add(reasons, "direct.s6", "expected 403 missing permit")
    if s6.get("level_absent") is not True:
        _add(reasons, "direct.s6.level_absent", "expected true")
    s5a = _dict(steps.get("s5a"))
    if s5a.get("first_http") != 200 or s5a.get("first_outcome") != "success":
        _add(reasons, "direct.s5a.first", "expected 200 success")
    if s5a.get("second_http") != 403 or _permit_verdict(s5a.get("second")) != "replayed":
        _add(reasons, "direct.s5a.second", "expected 403 replayed")
    s5b = _dict(steps.get("s5b"))
    if s5b.get("http") != 403 or _permit_verdict(s5b) != "args_mismatch":
        _add(reasons, "direct.s5b", "expected 403 args_mismatch")
    if s5b.get("level_absent") is not True:
        _add(reasons, "direct.s5b.level_absent", "expected true")
    s5c = _dict(steps.get("s5c"))
    if s5c.get("http") != 403 or _permit_verdict(s5c) != "route_mismatch":
        _add(reasons, "direct.s5c", "expected 403 route_mismatch")
    return reasons


def _audit_entries(files, reasons):
    entries, by_id = [], {}
    if not isinstance(files, dict) or not files:
        _add(reasons, "audit_files", "no audit JSONL evidence")
        return by_id
    for filename, lines in files.items():
        if not isinstance(filename, str) or not isinstance(lines, list):
            _add(reasons, "audit_files", "invalid audit file mapping")
            continue
        for number, line in enumerate(lines, 1):
            try:
                entry = json.loads(line)
            except (TypeError, ValueError):
                _add(reasons, "audit_files.{}".format(filename), "line {} is not JSON".format(number))
                continue
            call_id = entry.get("call_id") if isinstance(entry, dict) else None
            if not _text(call_id):
                _add(reasons, "audit_files.{}".format(filename), "line {} lacks call_id".format(number))
                continue
            by_id.setdefault(call_id, []).append(entry)
            entries.append(entry)
    return by_id


def _scenario_entry(key, call_id, by_id, used, reasons):
    tool, route = SCENARIOS[key]
    if not _text(call_id) or call_id in used:
        _add(reasons, "hermes.{}.call_id".format(key), "missing or reused")
        return None
    found = by_id.get(call_id, [])
    if len(found) != 1:
        _add(reasons, "hermes.{}.audit".format(key), "expected one audit entry")
        return None
    entry = found[0]
    if entry.get("tool") != tool or entry.get("route") != route:
        _add(reasons, "hermes.{}.audit".format(key), "wrong tool or route")
        return None
    used.add(call_id)
    return entry


def judge_hermes(hermes, audit_files):
    reasons, values = [], _dict(hermes)
    by_id = _audit_entries(audit_files, reasons)
    used = set()
    h1 = _dict(values.get("h1")); a1 = _scenario_entry("h1", h1.get("call_id"), by_id, used, reasons)
    if not (a1 and a1.get("decision") == "confirm" and a1.get("approval") == "accepted" and
            a1.get("outcome") == "success" and h1.get("element_gone") is True):
        _add(reasons, "hermes.h1", "expected accepted confirmed delete")
    h2 = _dict(values.get("h2")); a2 = _scenario_entry("h2", h2.get("call_id"), by_id, used, reasons)
    if not (a2 and a2.get("approval") == "declined" and a2.get("outcome") == "denied" and h2.get("element_present") is True):
        _add(reasons, "hermes.h2", "expected declined delete without effect")
    h3 = _dict(values.get("h3")); a3 = _scenario_entry("h3", h3.get("call_id"), by_id, used, reasons)
    if not (a3 and a3.get("outcome") == "expired"):
        _add(reasons, "hermes.h3", "expected expired")
    h4 = _dict(values.get("h4")); call_ids = _list(h4.get("call_ids"))
    if len(call_ids) != 2 or len(set(call_ids)) != 2:
        _add(reasons, "hermes.h4.call_ids", "expected two different call_ids")
    else:
        entries = [_scenario_entry("h4", value, by_id, used, reasons) for value in call_ids]
        if any(not entry or entry.get("decision") != "confirm" or
               entry.get("approval") not in ("accepted", "declined", "cancelled", "expired")
               for entry in entries):
            _add(reasons, "hermes.h4", "each same-request audit entry needs approval")
        if all(entries):
            first_args, second_args = (entry.get("args") for entry in entries)
            if not isinstance(first_args, dict) or not first_args or first_args != second_args:
                _add(reasons, "hermes.h4.args", "expected the same request twice")
    h5 = _dict(values.get("h5")); a5 = _scenario_entry("h5", h5.get("call_id"), by_id, used, reasons)
    args5 = _dict(a5.get("args")) if a5 else {}
    vector5 = _dict(args5.get("vector"))
    if not (a5 and a5.get("decision") == "confirm" and a5.get("approval") == "accepted" and
            a5.get("outcome") == "success" and h5.get("fractional_mm") == 12.5 and
            args5.get("operation") == "move" and vector5.get("x") == 12.5):
        _add(reasons, "hermes.h5", "expected accepted 12.5 mm fractional transform")
    if _dict(values.get("h6")).get("status") != "not_verified":
        _add(reasons, "hermes.h6", "gateway must remain not_verified")
    return reasons


def classify(record, secret):
    reasons = []
    try:
        if not isinstance(record, dict):
            _add(reasons, "record", "expected object"); record = {}
        if record.get("schema") != 1:
            _add(reasons, "schema", "expected 1")
        if not _text(secret):
            _add(reasons, "secret", "no configured secret available for leak scan")
        leaks = secret_occurrences(_record_bytes(record), secret)
        if leaks:
            _add(reasons, "secret", "SECRET_OCCURRENCES={}".format(leaks))
        reasons.extend(judge_preflight(record.get("preflight")))
        reasons.extend(judge_direct(record.get("direct")))
        reasons.extend(judge_hermes(record.get("hermes"), record.get("audit_files")))
        if not _is_int(record.get("posts_sent")) or record.get("posts_sent") != 5:
            _add(reasons, "posts_sent", "expected exactly five direct POST attempts")
        if record.get("stop_reason"):
            _add(reasons, "stop_reason", "run stopped before completion")
    except Exception as ex:
        _add(reasons, "classifier-error", type(ex).__name__)
    return (VERDICT_OK if not reasons else VERDICT_STOP, reasons)


def _response_json(response):
    try:
        value = response.json()
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _step(response):
    body = _response_json(response)
    verdict = body.get("permit")
    allowed = {"missing", "malformed", "bad_mac", "expired", "replayed", "args_mismatch",
               "route_mismatch", "session_mismatch", "ok"}
    outcome = body.get("status")
    return {"http": getattr(response, "status_code", None),
            "permit": verdict if isinstance(verdict, str) and verdict in allowed else None,
            "outcome": outcome if outcome in ("success", "partial", "failed", "rolled_back") else None}


def _levels(body):
    if not isinstance(body, dict) or not isinstance(body.get("levels"), list) or not _is_int(body.get("total_levels")):
        raise ValueError("list_levels malformed")
    levels = body["levels"]
    if body["total_levels"] != len(levels) or not all(isinstance(item, dict) and _text(item.get("name")) for item in levels):
        raise ValueError("list_levels malformed")
    return levels


def _has_level(levels, name):
    return any(item.get("name") == name for item in levels)


def _bridge():
    if REPO_ROOT not in sys.path: sys.path.insert(0, REPO_ROOT)
    import bridge
    return bridge


def _load_secret():
    module = _bridge()
    here = _local_path(os.path.dirname(module.__file__))
    if here is None:
        return None
    directories = [here, os.path.join(here, "revit_mcp")]
    if any(_local_path(os.path.join(path, module.SECRET_FILE_NAME)) is None for path in directories):
        return None
    return module.load_secret(search_dirs=directories)


def _permit():
    if REPO_ROOT not in sys.path: sys.path.insert(0, REPO_ROOT)
    import permit
    return permit


def _policy():
    if REPO_ROOT not in sys.path: sys.path.insert(0, REPO_ROOT)
    import policy
    return policy


def _direct_client(port):
    import httpx
    return httpx.AsyncClient(base_url="http://127.0.0.1:{}".format(port), timeout=30.0, trust_env=False)


def _validate_out(path):
    checked = _local_path(path)
    if checked is None: return "--out must be a local path"
    if not _outside_repo(checked): return "--out lies inside repository"
    if os.path.exists(checked): return "--out already exists"
    if not os.path.isdir(os.path.dirname(checked)): return "--out directory is missing"
    return None


def _write_reserved(handle, record):
    handle.seek(0)
    json.dump(record, handle, indent=2, sort_keys=True)
    handle.write("\n")
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def _reserve(path, record):
    problem = _validate_out(path)
    if problem: raise _UsageError(problem)
    handle = open(_local_path(path), "x+", encoding="utf-8", newline="\n")
    _write_reserved(handle, record)
    return handle


def _load_checked(path, label):
    checked = _local_path(path)
    if checked is None or not os.path.isfile(checked): raise _UsageError("{} is missing or non-local".format(label))
    with open(checked, "r", encoding="utf-8") as handle: return json.load(handle)


async def _safe_policy_snapshot():
    """Read an isolated, guarded local policy store; never falls back from bad remote policy."""
    module = _policy()
    source_dir = _local_path(os.path.dirname(module.__file__))
    base_path = _local_path(os.path.join(source_dir or "", module.BASE_FILE)) if source_dir else None
    if source_dir is None or base_path is None:
        raise ValueError("policy source is non-local")
    configured = os.environ.get(module.POLICY_FILE_ENV, "").strip()
    if configured and _local_path(configured) is None:
        raise ValueError("network-hosted operator policy refused")
    # Override only this isolated store's operator reader; production module state stays intact.
    # Validate the local pointer and its target before any file access.
    def guarded_operator_path(directory=None):
        if configured:
            return configured
        pointer = _local_path(os.path.join(source_dir, module.POLICY_SOURCE_FILE))
        if pointer is None:
            raise ValueError("network-hosted operator policy refused")
        try:
            with open(pointer, "rb") as handle:
                raw = handle.read(module._SOURCE_MAX)
            lines = raw.decode("utf-8-sig").splitlines()
        except FileNotFoundError:
            return None
        candidate = lines[0].strip() if lines else ""
        if candidate and _local_path(candidate) is None:
            raise ValueError("network-hosted operator policy refused")
        return candidate or None
    def guarded_reader(path):
        checked = _local_path(path)
        if checked is None: raise ValueError("network-hosted operator policy refused")
        with open(checked, "rb") as handle: return handle.read(module.MAX_OPERATOR_BYTES + 1)
    class LocalPolicyStore(module.PolicyStore):
        def _read_operator(self):
            path = guarded_operator_path()
            self._operator_file = path
            if not path:
                return None, None, None
            first = guarded_reader(path)
            module._debounce_sleep(module.DEBOUNCE_S)
            return path, first, guarded_reader(path)

    store = LocalPolicyStore(base_path=base_path, reader=guarded_reader, source_dir=source_dir)
    try:
        await store.current(force=True)
    except Exception as ex:
        raise ValueError("policy unavailable: {}".format(type(ex).__name__))
    snapshot = store.status()
    if snapshot.get("blocked") or snapshot.get("operator_state") not in ("not_configured", "absent", "accepted"):
        raise ValueError("policy unavailable: {}".format(snapshot.get("operator_state")))
    if not (_text(snapshot.get("source")) and _text(snapshot.get("hash"))):
        raise ValueError("policy unavailable: incomplete")
    return {"source": snapshot["source"], "hash": snapshot["hash"], "blocked": False,
            "operator_state": snapshot["operator_state"]}


async def _status_preflight(client, port, record):
    policy_snapshot = await _safe_policy_snapshot()
    response = await client.get("/genpro_revit_mcp/status/")
    body, preflight = _response_json(response), record["preflight"]
    preflight["status_http"] = getattr(response, "status_code", None)
    owners = _bridge().listener_snapshot([port]).get(port)
    preflight["listeners"] = list(owners) if isinstance(owners, list) else owners
    identity = _dict(body.get("process_identity"))
    preflight["identity"] = {key: identity.get(key) for key in ("pid", "actual_port", "session_token")}
    preflight["port"] = port
    preflight["permit_protocol"] = _dict(body.get("permit")).get("protocol")
    preflight["revit_version"] = identity.get("revit_version")
    preflight["policy"] = policy_snapshot
    record["revit_version"], record["policy"] = preflight["revit_version"], preflight["policy"]
    return judge_preflight(preflight)


async def _get_levels(client):
    response = await client.get("/genpro_revit_mcp/list_levels/")
    if getattr(response, "status_code", None) != 200: raise ValueError("list_levels HTTP failure")
    return _levels(_response_json(response))


async def _post(client, record, route, body, persist):
    if route not in ALLOWED_ENDPOINTS or not route.startswith("/create_"):
        raise ValueError("endpoint not allowed: {}".format(route))
    record["posts_sent"] += 1
    persist()  # durable conservative one-shot marker before transport receives a write
    try:
        return _step(await client.post("/genpro_revit_mcp" + route, content=body,
                                       headers={"Content-Type": "text/plain; charset=utf-8"}))
    except Exception as ex:
        return {"http": None, "permit": None, "outcome": None, "error": type(ex).__name__}


def _wire(secret, route, data, session, policy_hash, permits, permit_data=None):
    arguments = permits.args_text(data)
    permit_data = permits.mint(secret, route, arguments, session, policy_hash, 60) if permit_data is None else permit_data
    return permits.wire_text(arguments, {"secret": secret, "permit": permit_data}), permit_data


async def _cmd_preflight(args):
    if not (_is_int(args.port) and 1 <= args.port <= 65535): raise _UsageError("--port must be 1..65535")
    record, handle = evidence_template(), _reserve(args.out, evidence_template())
    try:
        client = _direct_client(args.port)
        try:
            reasons = await _status_preflight(client, args.port, record)
        except Exception as ex:
            reasons = ["preflight: {}".format(type(ex).__name__)]; record["stop_reason"] = reasons[0]
        finally:
            await client.aclose()
        _write_reserved(handle, record); return record, reasons
    finally:
        handle.close()


async def _cmd_direct(args):
    if not (_is_int(args.port) and 1 <= args.port <= 65535): raise _UsageError("--port must be 1..65535")
    if not (_text(args.level_name) and args.level_name.startswith(LEVEL_PREFIX)): raise _UsageError("--level-name must start with {}".format(LEVEL_PREFIX))
    record, client = evidence_template(), None
    handle = _reserve(args.out, record)
    try:
        persist = lambda: _write_reserved(handle, record)
        client = _direct_client(args.port)
        try:
            reasons = await _status_preflight(client, args.port, record)
        except Exception as ex:
            reasons = ["preflight: {}".format(type(ex).__name__)]; record["stop_reason"] = reasons[0]
        if reasons: persist(); return record, reasons
        secret = _load_secret()
        if not _text(secret): record["stop_reason"] = "secret unavailable"; persist(); return record, ["secret: unavailable"]
        permits, session, policy_hash = _permit(), record["preflight"]["identity"]["session_token"], record["preflight"]["policy"]["hash"]
        names = {key: args.level_name + "-" + key for key in ("s6", "s5a", "s5b")}
        s6_data = {"levels": [{"name": names["s6"], "elevation": 1000.0}]}
        s6_wire = permits.wire_text(permits.args_text(s6_data), {"secret": secret})
        record["direct"]["s6"] = await _post(client, record, "/create_level/", s6_wire, persist)
        record["direct"]["s6"]["level_absent"] = not _has_level(await _get_levels(client), names["s6"]); persist()
        s5a_data = {"levels": [{"name": names["s5a"], "elevation": 1100.0}]}
        s5a_wire, _permit_data = _wire(secret, "/create_level/", s5a_data, session, policy_hash, permits)
        first = await _post(client, record, "/create_level/", s5a_wire, persist)
        second = await _post(client, record, "/create_level/", s5a_wire, persist)
        record["direct"]["s5a"] = {"first_http": first["http"], "first_outcome": first["outcome"], "second_http": second["http"], "second": second}; persist()
        s5b_data = {"levels": [{"name": names["s5b"], "elevation": 1200.0}]}
        _unused, mismatch = _wire(secret, "/create_level/", s5a_data, session, policy_hash, permits)
        mismatch_wire, _unused = _wire(secret, "/create_level/", s5b_data, session, policy_hash, permits, mismatch)
        record["direct"]["s5b"] = await _post(client, record, "/create_level/", mismatch_wire, persist)
        record["direct"]["s5b"]["level_absent"] = not _has_level(await _get_levels(client), names["s5b"]); persist()
        _unused, wrong_route = _wire(secret, "/create_level/", s5a_data, session, policy_hash, permits)
        wrong_wire, _unused = _wire(secret, "/create_grid/", s5a_data, session, policy_hash, permits, wrong_route)
        record["direct"]["s5c"] = await _post(client, record, "/create_grid/", wrong_wire, persist)
        persist(); return record, []
    except Exception as ex:
        record["stop_reason"] = "direct: {}".format(type(ex).__name__)
        if handle is not None:
            try:
                _write_reserved(handle, record)
            except OSError:
                record["stop_reason"] += "; record-write failed"
        return record, [record["stop_reason"]]
    finally:
        try:
            if client is not None:
                try:
                    await client.aclose()
                except Exception as ex:
                    record["stop_reason"] = "client-close: {}".format(type(ex).__name__)
                    if handle is not None:
                        try:
                            _write_reserved(handle, record)
                        except OSError:
                            record["stop_reason"] += "; record-write failed"
        finally:
            if handle is not None:
                handle.close()


def _read_audit_dir(directory):
    checked = _local_path(directory)
    if checked is None or not os.path.isdir(checked): raise _UsageError("--audit-dir is missing or non-local")
    records = {}
    for name in sorted(os.listdir(checked)):
        if re.match(r"^audit-.*\.jsonl$", name):
            entry_path = _local_path(os.path.join(checked, name))
            if entry_path is None:
                raise _UsageError("audit file is non-local")
            with open(entry_path, "r", encoding="utf-8") as handle:
                records[name] = [line.rstrip("\n") for line in handle]
    return records


def _ingest_entries(record, replies):
    try: values = json.loads(replies) if replies.strip().startswith("{") else {}
    except ValueError: values = {}
    if not isinstance(values, dict): return
    for key in record["hermes"]:
        if isinstance(values.get(key), dict): record["hermes"][key] = dict(values[key])


def _cmd_ingest(args):
    record_path, replies_path, audit_dir = _local_path(args.record), _local_path(args.replies), _local_path(args.audit_dir)
    if record_path is None or replies_path is None or audit_dir is None: raise _UsageError("input path is non-local")
    record = _load_checked(record_path, "--record")
    record["audit_files"] = _read_audit_dir(audit_dir)
    with open(replies_path, "r", encoding="utf-8") as handle: _ingest_entries(record, handle.read())
    handle = _reserve(args.out, record); handle.close(); return record


def _print_result(record, secret):
    verdict, reasons = classify(record, secret)
    print(SENTINEL_OK if verdict == VERDICT_OK else SENTINEL_STOP)
    print("POSTS_SENT={}".format(record.get("posts_sent", "unknown")))
    print("SECRET_OCCURRENCES={}".format(secret_occurrences(_record_bytes(record), secret)))
    for reason in reasons: print("REASON={}".format(reason))
    return 0 if verdict == VERDICT_OK else 1


def main(argv=None):
    record = None
    try:
        parser = _Parser(prog="test_phase7_live_bench.py"); commands = parser.add_subparsers(dest="command", required=True)
        commands.add_parser("template")
        for name in ("preflight", "direct"):
            command = commands.add_parser(name); command.add_argument("--port", type=int, default=48884); command.add_argument("--out", required=True)
            if name == "direct": command.add_argument("--level-name", required=True)
        ingest = commands.add_parser("ingest"); ingest.add_argument("--record", required=True); ingest.add_argument("--audit-dir", required=True); ingest.add_argument("--replies", required=True); ingest.add_argument("--out", required=True)
        classify_cmd = commands.add_parser("classify"); classify_cmd.add_argument("record")
        args = parser.parse_args(argv)
        if args.command == "template": print(json.dumps(evidence_template(), indent=2, sort_keys=True)); return 0
        if args.command == "classify": return _print_result(_load_checked(args.record, "record"), _load_secret())
        if args.command == "preflight": record, _ = asyncio.run(_cmd_preflight(args)); return _print_result(record, _load_secret())
        if args.command == "direct": record, _ = asyncio.run(_cmd_direct(args)); return _print_result(record, _load_secret())
        if args.command == "ingest": return _print_result(_cmd_ingest(args), _load_secret())
    except (_UsageError, OSError, ValueError, json.JSONDecodeError) as ex:
        print("USAGE: {}".format(type(ex).__name__), file=sys.stderr)
        if record is not None and record.get("posts_sent", 0) > 0: return _print_result(record, None)
        print("POSTS_SENT=0"); return 2


if __name__ == "__main__": sys.exit(main())
