# -*- coding: utf-8 -*-
"""Live D-04 probe: does hashlib.sha256 work in pyRevit's engine, and did the
Phase 3 helper modules load there?

ROADMAP Phase 3 success criterion 2 needs the hand-rolled secret compare of
D-04 (SHA-256 digests compared by XOR-accumulation) observed in the live
IronPython engine, not assumed. This script sends one small snippet through
``/execute_code/`` and reads ``/status/``; nothing else in the repository
talks to Revit for this. It also shows that ``revit_mcp/trust.py`` and
``revit_mcp/integrity.py``, which startup's discovery imports at extension
load, loaded in that engine.

Prerequisites (the live step is run by a human, never by an assistant):
  * Revit fully closed and reopened after the Phase 3 ``revit_mcp/`` changes
    (never pyRevit Reload: it can crash Revit),
  * a throwaway or untitled model open (``/execute_code/`` wraps every call in
    a transaction; the snippet changes nothing),
  * exactly one listener on the Routes port:
    ``Get-NetTCPConnection -LocalPort 48884 -State Listen``.

It lives in ``scripts/`` so it never ships in the deployed payload.

Two verdicts, each PASS, FAIL or INCONCLUSIVE:
  D04_VERDICT      judges only the primitive: ``abc_ok``, ``lf_ok``, ``len`` and
                   ``first4`` from the snippet, plus an ``/execute_code/`` error
                   that names hashlib (the primitive itself is missing).
  MODULES_VERDICT  judges module load from ``/status/``: ``trust`` and
                   ``integrity`` must be under ``skipped_modules`` (helpers) and
                   neither under ``failed_domains``. ``/status/`` is the
                   evidence because it reports startup's own import pass. The
                   snippet's ``sys.modules`` lookup runs inside the
                   ``/execute_code/`` exec, whose module table may not be
                   startup's (the routes server keeps its own engine), so a
                   lookup miss (``trust_loaded=False``) is informational and
                   changes neither verdict. A module the lookup does find must
                   also pass its ``trust_ok`` / ``integrity_ok`` check.
INCONCLUSIVE (a missing primitive field, or absent status lines) changes no
code and never reopens D-04: fix the named cause and run again. Informational
only, never judged: ``py``, ``hmac_compare_digest``, ``clr_version``,
``FixedTimeEquals_type_present``.

The request body is sent as text/plain JSON, as bridge.py does, because pyRevit
parses an application-typed body itself with a parse that is broken under
IronPython 3.

Output tokens: STATUS_SKIPPED, STATUS_FAILED, EXEC_ERROR, the snippet's own
lines, D04_VERDICT, MODULES_VERDICT, REASON, PROBE_UNREACHABLE,
PROBE_NO_DOCUMENT. The stream is parseable: ``parse_output`` plus the two
verdict functions reproduce both verdicts from pasted text.
Exit codes: 0 both PASS, 1 either FAIL, 4 neither FAIL and one INCONCLUSIVE,
2 nothing listening, 3 no active document.

Usage:
    uv run python scripts/probe_ipy_trust.py --port 48884
"""
import argparse
import json
import re
import sys

import httpx

# Expected values, computed under CPython 3.13 during planning.
EXPECTED_FIRST4 = "[227, 79, 109, 236]"
EXPECTED_LEN = "32"
LF_HASH = "7e18f737311b2dc3b2f269dd78396b0351f14fb66efa879f768cb23181883c78"
PHASE_MODULES = ("trust", "integrity")

# Every line of the RESEARCH "Live gate snippet for D-04" is kept verbatim; the
# lf_ok line and the trust_*/integrity_* lines are added. The escape text in the
# lf_ok line is written with doubled backslashes so it reaches the engine as the
# characters backslash-r-backslash-n, never as raw CR/LF. No f-strings (Python
# 3.4 language level), one format() argument per print (the route's injected
# print joins its arguments), and the lines are joined with a bare LF because
# IronPython's exec rejects CRLF.
_SNIPPET_LINES = [
    "import sys",
    "import hashlib",
    'print("py={}".format(sys.version.split()[0]))',
    'd = hashlib.sha256(u"тест".encode("utf-8")).digest()',
    'print("digest_type={} len={} first4={}".format(type(d).__name__, len(d), list(bytearray(d))[:4]))',
    'print("abc_ok={}".format(hashlib.sha256(b"abc").hexdigest() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"))',
    'print("lf_ok={}".format(hashlib.sha256(b"a\\r\\nb".replace(b"\\r\\n", b"\\n")).hexdigest() == "' + LF_HASH + '"))',
    "try:",
    "    import hmac",
    '    print("hmac_compare_digest={}".format(hasattr(hmac, "compare_digest")))',
    "except Exception as exc:",
    '    print("hmac_import_failed={}".format(type(exc).__name__))',
    "try:",
    "    import System",
    '    print("clr_version={}".format(System.Environment.Version))',
    '    print("FixedTimeEquals_type_present={}".format(',
    '        System.Type.GetType("System.Security.Cryptography.CryptographicOperations") is not None))',
    "except Exception as exc:",
    '    print("clr_probe_failed={}".format(type(exc).__name__))',
    't = sys.modules.get("genpro_revit_mcp.trust")',
    'print("trust_loaded={}".format(t is not None))',
    "if t is not None:",
    '    print("trust_ok={}".format(t.check_secret("s" * 20, "s" * 20) == "ok" and t.check_secret("s" * 20, "t" * 20) == "mismatch"))',
    'i = sys.modules.get("genpro_revit_mcp.integrity")',
    'print("integrity_loaded={}".format(i is not None))',
    "if i is not None:",
    '    print("integrity_ok={}".format(i.hash_normalized(b"a\\r\\nb") == "' + LF_HASH + '"))',
]
SNIPPET = "\n".join(_SNIPPET_LINES)

DESCRIPTION = "D-04 live probe: hashlib.sha256 and Phase 3 module load (reads nothing, writes nothing)"

_DIGEST_RE = re.compile(r"^digest_type=(\S*) len=(\S*) first4=(.*)$")
_PAIR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)=(.*)$")
_MODULE_WORD_RE = re.compile(r"\b(trust|integrity)\b", re.IGNORECASE)


def build_body():
    """UTF-8 JSON bytes for /execute_code/: keys ``code`` and ``description``."""
    return json.dumps({"code": SNIPPET, "description": DESCRIPTION}).encode("utf-8")


def parse_output(text):
    """key=value pairs of the probe's output stream, as a dict of text.

    The ``digest_type=... len=... first4=[...]`` line splits on the spaces before
    ``first4=`` so the list survives. ``STATUS_SKIPPED`` and ``STATUS_FAILED``
    keep their JSON as text; ``EXEC_ERROR`` keeps the rest of its line. Lines
    that are not a pair, and ``REASON=`` lines, are ignored.
    """
    fields = {}
    for raw in text.splitlines():
        line = raw.strip()
        digest = _DIGEST_RE.match(line)
        if digest:
            fields["digest_type"] = digest.group(1)
            fields["len"] = digest.group(2)
            fields["first4"] = digest.group(3).strip()
            continue
        pair = _PAIR_RE.match(line)
        if not pair or pair.group(1) == "REASON":
            continue
        fields[pair.group(1)] = pair.group(2).strip()
    return fields


def d04_verdict(fields):
    """``(outcome, reasons)`` for the primitive; reads only abc_ok, lf_ok, len, first4, EXEC_ERROR."""
    failures = []
    expected = (
        ("abc_ok", "True"),
        ("lf_ok", "True"),
        ("len", EXPECTED_LEN),
        ("first4", EXPECTED_FIRST4),
    )
    for name, want in expected:
        if name in fields and fields[name] != want:
            failures.append("{}={} (expected {})".format(name, fields[name], want))
    error = fields.get("EXEC_ERROR", "")
    if "hashlib" in error.lower():
        failures.append("EXEC_ERROR names hashlib: {}".format(error))
    if failures:
        return "FAIL", failures
    missing = [name for name, _ in expected if name not in fields]
    if missing:
        return "INCONCLUSIVE", ["missing primitive field(s): {}".format(", ".join(missing))]
    return "PASS", []


def _status_json(fields, key):
    """(dict, None) for a parseable status line, else (None, reason)."""
    if key not in fields:
        return None, "{} line absent".format(key)
    try:
        value = json.loads(fields[key])
    except ValueError:
        return None, "{} is not valid JSON".format(key)
    if not isinstance(value, dict):
        return None, "{} is not a JSON object".format(key)
    return value, None


def modules_verdict(fields):
    """``(outcome, reasons)`` for module load.

    Evidence of a failure wins over missing status lines: a found module whose
    check is not True fails even when the status lines are absent. A lookup miss
    adds an informational reason and fails nothing.
    """
    failures = []
    unknown = []
    info = []

    skipped, why = _status_json(fields, "STATUS_SKIPPED")
    if why:
        unknown.append(why)
    failed, why = _status_json(fields, "STATUS_FAILED")
    if why:
        unknown.append(why)

    if failed is not None:
        for domain, text in sorted(failed.items()):
            if domain in PHASE_MODULES or _MODULE_WORD_RE.search(str(text)):
                failures.append("STATUS_FAILED names {}: {}".format(domain, text))
    if skipped is not None:
        for name in PHASE_MODULES:
            if name not in skipped:
                failures.append("STATUS_SKIPPED lacks {} (not loaded as a helper)".format(name))

    for name in PHASE_MODULES:
        loaded = fields.get(name + "_loaded")
        if loaded == "True":
            if fields.get(name + "_ok") != "True":
                failures.append(
                    "{}_ok={} (the loaded module's check did not pass)".format(
                        name, fields.get(name + "_ok", "absent")
                    )
                )
        elif loaded == "False":
            info.append(
                "{}_loaded=False: the /execute_code/ lookup missed; /status/ is the load evidence".format(name)
            )

    if failures:
        return "FAIL", failures + unknown
    if unknown:
        return "INCONCLUSIVE", unknown
    return "PASS", info


def exit_code(d04, modules):
    """0 both PASS, 1 either FAIL, 4 neither FAIL and one INCONCLUSIVE."""
    if "FAIL" in (d04, modules):
        return 1
    if "INCONCLUSIVE" in (d04, modules):
        return 4
    return 0


def _one_line(text):
    return " ".join(str(text).split())


def _json_or_none(response):
    try:
        return response.json()
    except ValueError:
        return None


def main(argv=None, transport=None):
    parser = argparse.ArgumentParser(description="Live D-04 probe (one live Revit instance)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=48884)
    parser.add_argument("--prefix", default="genpro_revit_mcp")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    base = "http://{}:{}/{}".format(args.host, args.port, args.prefix.strip("/"))
    target = "{}:{}".format(args.host, args.port)
    printed = []

    def emit(line):
        printed.append(line)
        print(line)

    with httpx.Client(transport=transport, trust_env=False) as client:
        status_data = None
        try:
            status_resp = client.get(base + "/status/", timeout=5.0)
            if status_resp.status_code == 200:
                parsed = _json_or_none(status_resp)
                if isinstance(parsed, dict):
                    status_data = parsed
        except (httpx.ConnectError, httpx.ConnectTimeout):
            print("PROBE_UNREACHABLE target={}".format(target))
            return 2
        except httpx.HTTPError:
            status_data = None

        exec_error = None
        exec_resp = None
        try:
            exec_resp = client.post(
                base + "/execute_code/",
                content=build_body(),
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=args.timeout,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            print("PROBE_UNREACHABLE target={}".format(target))
            return 2
        except httpx.TimeoutException:
            exec_error = "timeout after {}s (Revit still initializing, or a modal dialog is open)".format(
                args.timeout
            )
        except httpx.HTTPError as exc:
            exec_error = "transport error {}: {}".format(type(exc).__name__, exc)

    if exec_resp is not None and exec_resp.status_code == 503:
        print("PROBE_NO_DOCUMENT target={} status=503".format(target))
        return 3

    if status_data is not None:
        emit("STATUS_SKIPPED={}".format(json.dumps(status_data.get("skipped_modules") or {}, sort_keys=True)))
        emit("STATUS_FAILED={}".format(json.dumps(status_data.get("failed_domains") or {}, sort_keys=True)))

    if exec_resp is not None:
        data = _json_or_none(exec_resp)
        data = data if isinstance(data, dict) else {}
        if exec_resp.status_code != 200:
            emit("EXEC_ERROR={}".format(_one_line(data.get("error") or "HTTP {}".format(exec_resp.status_code))))
        text = data.get("output") if exec_resp.status_code == 200 else (data.get("partial_output") or data.get("output"))
        for line in str(text or "").splitlines():
            emit(line)
    elif exec_error is not None:
        emit("EXEC_ERROR={}".format(_one_line(exec_error)))

    fields = parse_output("\n".join(printed))
    d04, d04_reasons = d04_verdict(fields)
    modules, modules_reasons = modules_verdict(fields)
    emit("D04_VERDICT={}".format(d04))
    emit("MODULES_VERDICT={}".format(modules))
    for reason in d04_reasons:
        emit("REASON=d04: {}".format(_one_line(reason)))
    for reason in modules_reasons:
        emit("REASON=modules: {}".format(_one_line(reason)))
    return exit_code(d04, modules)


if __name__ == "__main__":
    sys.exit(main())
