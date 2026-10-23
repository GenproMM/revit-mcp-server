# -*- coding: utf-8 -*-
"""Offline tests of the live D-04 probe (scripts/probe_ipy_trust.py).

The probe sends one snippet to a live pyRevit engine through /execute_code/ and
judges two things separately: whether hashlib.sha256 works there (D-04) and
whether trust.py and integrity.py loaded there (judged from /status/). What is
tested here is everything decidable without Revit: the snippet's shape, the
snippet run under CPython, both verdict functions, the exit codes, and the whole
of main() over an httpx MockTransport.

Needs no Revit.
"""

import ast
import importlib.util
import json
import os
import sys

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROBE_PATH = os.path.join(REPO_ROOT, "scripts", "probe_ipy_trust.py")

_spec = importlib.util.spec_from_file_location("probe_ipy_trust", PROBE_PATH)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

FIRST4 = "[227, 79, 109, 236]"
LF_HASH = "7e18f737311b2dc3b2f269dd78396b0351f14fb66efa879f768cb23181883c78"

# The RESEARCH "Live gate snippet for D-04" lines, every one of which the probe's
# snippet must keep verbatim.
RESEARCH_LINES = [
    "import sys",
    "import hashlib",
    'print("py={}".format(sys.version.split()[0]))',
    'd = hashlib.sha256(u"тест".encode("utf-8")).digest()',
    'print("digest_type={} len={} first4={}".format(type(d).__name__, len(d), list(bytearray(d))[:4]))',
    'print("abc_ok={}".format(hashlib.sha256(b"abc").hexdigest() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"))',
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
]

PASSING_OUTPUT = "\n".join(
    [
        "py=3.4.0",
        "digest_type=bytes len=32 first4=" + FIRST4,
        "abc_ok=True",
        "lf_ok=True",
        "hmac_compare_digest=True",
        "clr_version=4.0.30319.42000",
        "FixedTimeEquals_type_present=False",
        "trust_loaded=True",
        "trust_ok=True",
        "integrity_loaded=True",
        "integrity_ok=True",
    ]
)


def _status(skipped=("trust", "integrity"), failed=()):
    body = {"status": "active", "health": "healthy", "domains_registered": 23}
    if skipped:
        body["skipped_modules"] = dict((k, "no register_*_routes callable") for k in skipped)
    if failed:
        body["failed_domains"] = dict((k, "ImportError: boom") for k in failed)
        body["health"] = "degraded"
    return body


def _good_fields():
    return {
        "abc_ok": "True",
        "lf_ok": "True",
        "len": "32",
        "first4": FIRST4,
        "trust_loaded": "False",
        "integrity_loaded": "False",
    }


def _status_fields(skipped=("trust", "integrity"), failed=()):
    return {
        "STATUS_SKIPPED": json.dumps(dict((k, "x") for k in skipped)),
        "STATUS_FAILED": json.dumps(dict((k, "boom") for k in failed)),
    }


# --- snippet shape ---------------------------------------------------------


def test_snippet_is_py34_safe_source():
    tree = ast.parse(probe.SNIPPET)
    assert not any(isinstance(n, ast.JoinedStr) for n in ast.walk(tree)), "f-string"
    assert "\r" not in probe.SNIPPET
    lf_line = [ln for ln in probe.SNIPPET.split("\n") if ln.startswith('print("lf_ok=')]
    assert len(lf_line) == 1
    assert "\\r\\n" in lf_line[0]  # escape text, not a raw CR/LF


def test_snippet_keeps_every_research_line_in_order():
    lines = probe.SNIPPET.split("\n")
    position = -1
    for expected in RESEARCH_LINES:
        assert expected in lines[position + 1:], "missing or out of order: " + expected
        position = lines.index(expected, position + 1)


def test_snippet_exercises_the_phase_modules_through_the_lookup():
    assert 'sys.modules.get("genpro_revit_mcp.trust")' in probe.SNIPPET
    assert 'sys.modules.get("genpro_revit_mcp.integrity")' in probe.SNIPPET
    assert "check_secret" in probe.SNIPPET
    assert "hash_normalized" in probe.SNIPPET


def _run_snippet(monkeypatch):
    for name in ("genpro_revit_mcp.trust", "genpro_revit_mcp.integrity"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    printed = []
    namespace = {
        "__builtins__": __builtins__,
        "print": lambda *args: printed.append(" ".join(str(a) for a in args)),
    }
    exec(probe.SNIPPET, namespace)
    return "\n".join(printed)


def test_snippet_under_cpython_matches_the_planned_values(monkeypatch):
    text = _run_snippet(monkeypatch)
    fields = probe.parse_output(text)
    assert fields["abc_ok"] == "True"
    assert fields["lf_ok"] == "True"
    assert fields["len"] == "32"
    assert fields["first4"] == FIRST4
    assert fields["trust_loaded"] == "False"
    assert fields["integrity_loaded"] == "False"
    assert "trust_ok" not in fields
    assert "integrity_ok" not in fields


def test_lookup_miss_never_fails_d04(monkeypatch):
    fields = probe.parse_output(_run_snippet(monkeypatch))
    outcome, reasons = probe.d04_verdict(fields)
    assert outcome == "PASS"
    assert reasons == []


# --- parse_output ----------------------------------------------------------


def test_parse_output_keeps_the_first4_list_and_error_text_whole():
    text = "\n".join(
        [
            "digest_type=bytes len=32 first4=" + FIRST4,
            "EXEC_ERROR=ImportError: No module named hashlib = fatal",
            'STATUS_SKIPPED={"trust": "x"}',
            "not a pair line",
            "REASON=whatever",
        ]
    )
    fields = probe.parse_output(text)
    assert fields["digest_type"] == "bytes"
    assert fields["len"] == "32"
    assert fields["first4"] == FIRST4
    assert fields["EXEC_ERROR"] == "ImportError: No module named hashlib = fatal"
    assert json.loads(fields["STATUS_SKIPPED"]) == {"trust": "x"}


# --- d04_verdict -----------------------------------------------------------


def test_d04_pass():
    assert probe.d04_verdict(_good_fields()) == ("PASS", [])


@pytest.mark.parametrize(
    "field,value",
    [
        ("abc_ok", "False"),
        ("lf_ok", "False"),
        ("len", "20"),
        ("first4", "[1, 2, 3, 4]"),
    ],
)
def test_d04_fails_on_a_wrong_primitive_field_and_names_it(field, value):
    outcome, reasons = probe.d04_verdict(dict(_good_fields(), **{field: value}))
    assert outcome == "FAIL"
    assert any(field in r for r in reasons)


def test_d04_fails_on_an_exec_error_naming_hashlib():
    outcome, reasons = probe.d04_verdict({"EXEC_ERROR": "ImportError: No module named hashlib"})
    assert outcome == "FAIL"
    assert any("hashlib" in r for r in reasons)


def test_d04_inconclusive_when_a_primitive_field_is_missing():
    fields = _good_fields()
    del fields["lf_ok"]
    del fields["len"]
    outcome, reasons = probe.d04_verdict(fields)
    assert outcome == "INCONCLUSIVE"
    joined = " ".join(reasons)
    assert "lf_ok" in joined and "len" in joined


def test_d04_inconclusive_for_an_unrelated_exec_error():
    outcome, _ = probe.d04_verdict({"EXEC_ERROR": "NameError: name 'x' is not defined"})
    assert outcome == "INCONCLUSIVE"


def test_d04_reads_only_the_primitive_fields():
    base = _good_fields()
    noisy = dict(
        base,
        trust_loaded="True",
        trust_ok="False",
        integrity_loaded="True",
        integrity_ok="False",
        STATUS_SKIPPED="not json",
        STATUS_FAILED='{"trust": "boom"}',
        hmac_compare_digest="False",
        clr_version="nonsense",
        FixedTimeEquals_type_present="False",
    )
    assert probe.d04_verdict(noisy) == probe.d04_verdict(base)


# --- modules_verdict -------------------------------------------------------


def test_modules_pass_with_a_lookup_miss_is_informational():
    fields = dict(_good_fields(), **_status_fields())
    outcome, reasons = probe.modules_verdict(fields)
    assert outcome == "PASS"
    assert any("/status/" in r for r in reasons)


def test_modules_pass_when_found_modules_pass_their_checks():
    fields = dict(
        _good_fields(),
        trust_loaded="True",
        trust_ok="True",
        integrity_loaded="True",
        integrity_ok="True",
        **_status_fields()
    )
    assert probe.modules_verdict(fields) == ("PASS", [])


@pytest.mark.parametrize("drop", ["STATUS_SKIPPED", "STATUS_FAILED"])
def test_modules_inconclusive_when_a_status_line_is_absent(drop):
    fields = dict(_good_fields(), **_status_fields())
    del fields[drop]
    assert probe.modules_verdict(fields)[0] == "INCONCLUSIVE"


def test_modules_inconclusive_when_status_json_is_unparseable():
    fields = dict(_good_fields(), **_status_fields())
    fields["STATUS_FAILED"] = "{oops"
    assert probe.modules_verdict(fields)[0] == "INCONCLUSIVE"


def test_modules_fail_when_failed_domains_names_a_module():
    for name in ("trust", "integrity"):
        fields = dict(_good_fields(), **_status_fields(failed=(name,)))
        outcome, reasons = probe.modules_verdict(fields)
        assert outcome == "FAIL"
        assert any(name in r for r in reasons)


def test_modules_fail_when_skipped_modules_lacks_one():
    fields = dict(_good_fields(), **_status_fields(skipped=("trust",)))
    outcome, reasons = probe.modules_verdict(fields)
    assert outcome == "FAIL"
    assert any("integrity" in r for r in reasons)


def test_modules_fail_when_a_found_module_does_not_pass_its_check():
    base = dict(_good_fields(), **_status_fields())
    for loaded, ok in (("trust_loaded", "trust_ok"), ("integrity_loaded", "integrity_ok")):
        wrong = dict(base, **{loaded: "True", ok: "False"})
        outcome, reasons = probe.modules_verdict(wrong)
        assert outcome == "FAIL" and any(ok in r for r in reasons)
        raised = dict(base, **{loaded: "True"})  # no *_ok line: the call raised
        outcome, reasons = probe.modules_verdict(raised)
        assert outcome == "FAIL" and any(ok in r for r in reasons)


# --- exit_code -------------------------------------------------------------


def test_exit_code_table():
    assert probe.exit_code("PASS", "PASS") == 0
    assert probe.exit_code("FAIL", "PASS") == 1
    assert probe.exit_code("PASS", "FAIL") == 1
    assert probe.exit_code("FAIL", "INCONCLUSIVE") == 1
    assert probe.exit_code("INCONCLUSIVE", "PASS") == 4
    assert probe.exit_code("PASS", "INCONCLUSIVE") == 4
    assert probe.exit_code("INCONCLUSIVE", "INCONCLUSIVE") == 4


# --- request body ----------------------------------------------------------


def test_build_body_is_utf8_json_with_code_and_description():
    body = probe.build_body()
    assert isinstance(body, bytes)
    data = json.loads(body.decode("utf-8"))
    assert data["code"] == probe.SNIPPET
    assert data["description"]


# --- main over a MockTransport ---------------------------------------------


def _transport(status_json=None, status_code=200, exec_status=200, exec_json=None, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        if request.url.path.endswith("/status/"):
            if status_json is None:
                return httpx.Response(status_code, text="Route does not exist")
            return httpx.Response(status_code, json=status_json)
        if request.url.path.endswith("/execute_code/"):
            return httpx.Response(exec_status, json=exec_json)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _ok_exec(output=PASSING_OUTPUT):
    return {"status": "success", "output": output}


def _run_main(transport, capsys):
    code = probe.main([], transport=transport)
    return code, capsys.readouterr().out


def test_main_both_pass_returns_0(capsys):
    seen = []
    code, out = _run_main(_transport(_status(), exec_json=_ok_exec(), seen=seen), capsys)
    assert code == 0
    assert "D04_VERDICT=PASS" in out
    assert "MODULES_VERDICT=PASS" in out
    posts = [r for r in seen if r.method == "POST"]
    assert len(posts) == 1
    assert posts[0].url.path == "/genpro_revit_mcp/execute_code/"
    assert posts[0].headers["content-type"] == "text/plain; charset=utf-8"
    assert json.loads(posts[0].content.decode("utf-8"))["code"] == probe.SNIPPET


def test_main_failing_primitive_returns_1(capsys):
    bad = PASSING_OUTPUT.replace("abc_ok=True", "abc_ok=False")
    code, out = _run_main(_transport(_status(), exec_json=_ok_exec(bad)), capsys)
    assert code == 1
    assert "D04_VERDICT=FAIL" in out


def test_main_failed_module_with_passing_primitive_returns_1(capsys):
    code, out = _run_main(_transport(_status(failed=("trust",)), exec_json=_ok_exec()), capsys)
    assert code == 1
    assert "D04_VERDICT=PASS" in out
    assert "MODULES_VERDICT=FAIL" in out


def test_main_missing_hashlib_error_returns_1(capsys):
    err = {"status": "error", "error": "ImportError: No module named hashlib"}
    code, out = _run_main(_transport(_status(), exec_status=500, exec_json=err), capsys)
    assert code == 1
    assert "D04_VERDICT=FAIL" in out
    assert "EXEC_ERROR=ImportError: No module named hashlib" in out


def test_main_other_error_without_partial_output_returns_4(capsys):
    err = {"status": "error", "error": "NameError: name 'q' is not defined"}
    code, out = _run_main(_transport(_status(), exec_status=500, exec_json=err), capsys)
    assert code == 4
    assert "D04_VERDICT=INCONCLUSIVE" in out


def test_main_prints_partial_output_of_an_error_reply(capsys):
    err = {"status": "error", "error": "NameError: x", "partial_output": "py=3.4.0\nabc_ok=True\n"}
    code, out = _run_main(_transport(_status(), exec_status=500, exec_json=err), capsys)
    assert code == 4
    assert "abc_ok=True" in out


def test_main_absent_status_lines_make_modules_inconclusive(capsys):
    code, out = _run_main(_transport(status_json=None, exec_json=_ok_exec()), capsys)
    assert code == 4
    assert "MODULES_VERDICT=INCONCLUSIVE" in out
    assert "STATUS_SKIPPED=" not in out


def test_main_connect_error_returns_2(capsys):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    code, out = _run_main(httpx.MockTransport(refuse), capsys)
    assert code == 2
    assert "PROBE_UNREACHABLE" in out


def test_main_503_from_execute_code_returns_3(capsys):
    code, out = _run_main(
        _transport(_status(), exec_status=503, exec_json={"error": "No active Revit document"}),
        capsys,
    )
    assert code == 3
    assert "PROBE_NO_DOCUMENT" in out


def test_printed_stream_reproduces_both_verdicts_from_pasted_text(capsys):
    for status, output in (
        (_status(), PASSING_OUTPUT),
        (_status(failed=("integrity",)), PASSING_OUTPUT),
        (_status(), PASSING_OUTPUT.replace("lf_ok=True", "lf_ok=False")),
    ):
        _, out = _run_main(_transport(status, exec_json=_ok_exec(output)), capsys)
        fields = probe.parse_output(out)
        assert fields["D04_VERDICT"] == probe.d04_verdict(fields)[0]
        assert fields["MODULES_VERDICT"] == probe.modules_verdict(fields)[0]


# --- the script itself -----------------------------------------------------


def test_script_source_dialect():
    with open(PROBE_PATH, "rb") as handle:
        raw = handle.read()
    text = raw.decode("utf-8")
    assert text.split("\n", 1)[0].strip() == "# -*- coding: utf-8 -*-"
    assert b"\r" not in raw
    assert "application/json" not in text
