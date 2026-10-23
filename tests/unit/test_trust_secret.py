# -*- coding: utf-8 -*-
"""revit_mcp/trust.py: the verdict table, constant-time structure, leaks, method rule, secret file.

trust.py is the Revit half's pure secret-gate logic (plan 03-01). It imports nothing
from pyRevit, so it is exercised directly under CPython. The structure tests read its
source with ast, because "no early exit" and "no logging" are properties of the code,
not of any one return value. Needs no Revit.
"""

import ast
import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import pytest

from inventory_support import REVIT_MCP_DIR, route_inventory
from revit_mcp import trust

SECRET = "unit-secret-0123456789-abcdefXYZ"
CYRILLIC = "Секретный-пароль-й-2026-абв"

TRUST_PATH = os.path.join(REVIT_MCP_DIR, "trust.py")


def _tree():
    with open(TRUST_PATH, encoding="utf-8") as handle:
        return ast.parse(handle.read())


def _function(name):
    for node in ast.walk(_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("trust.py defines no function {}".format(name))


# --------------------------------------------------------------------- verdicts

S = SECRET

VERDICT_TABLE = [
    # two absent or empty secrets never compare ok
    ((None, None), "server_not_configured"),
    (("", ""), "server_not_configured"),
    (("   ", "   "), "server_not_configured"),
    ((b"", b""), "server_not_configured"),
    # the server is not configured (short or absent expected value)
    ((S, "short"), "server_not_configured"),
    ((S, None), "server_not_configured"),
    ((S, 123), "server_not_configured"),
    # nothing provided
    ((None, S), "missing"),
    (("", S), "missing"),
    (("  ", S), "missing"),
    ((b"", S), "missing"),
    # equal, in every text/bytes combination
    ((S, S), "ok"),
    ((S.encode(), S), "ok"),
    ((S, S.encode()), "ok"),
    ((S.encode(), S.encode()), "ok"),
    # anything else is a mismatch
    ((S + "x", S), "mismatch"),
    (("x" + S, S), "mismatch"),
    ((S[:-1], S), "mismatch"),
    ((123, S), "mismatch"),
    (({"a": 1}, S), "mismatch"),
    ((["x"], S), "mismatch"),
    ((True, S), "mismatch"),
    # Cyrillic: equal to itself, no Unicode normalization
    ((CYRILLIC, CYRILLIC), "ok"),
    ((CYRILLIC.encode("utf-8"), CYRILLIC), "ok"),
    ((unicodedata.normalize("NFD", CYRILLIC), unicodedata.normalize("NFC", CYRILLIC)), "mismatch"),
    ((unicodedata.normalize("NFC", CYRILLIC), unicodedata.normalize("NFD", CYRILLIC)), "mismatch"),
]


@pytest.mark.parametrize("args,expected", VERDICT_TABLE)
def test_verdict_table(args, expected):
    assert trust.check_secret(*args) == expected


def test_verdict_cyrillic_forms_really_differ():
    """Guard the guard: the NFC/NFD rows above only mean something if the forms differ."""
    nfc = unicodedata.normalize("NFC", CYRILLIC)
    nfd = unicodedata.normalize("NFD", CYRILLIC)
    assert nfc != nfd
    assert len(nfd) >= trust.MIN_SECRET_LENGTH


def test_verdict_exactly_four_values_exist():
    verdicts = set(expected for _, expected in VERDICT_TABLE)
    assert verdicts == set([
        trust.AUTH_OK, trust.AUTH_MISSING, trust.AUTH_MISMATCH,
        trust.AUTH_SERVER_NOT_CONFIGURED,
    ])


def test_verdict_hostile_values_never_raise():
    class Explodes(object):
        def __bool__(self):
            raise RuntimeError("boom")

        def strip(self):
            raise RuntimeError("boom")

        __len__ = strip

    for hostile in (Explodes(), object(), float("nan"), 1 + 2j, lambda: None):
        assert trust.check_secret(hostile, S) in ("missing", "mismatch")
        assert trust.check_secret(S, hostile) == "server_not_configured"


def test_verdict_minimum_length_boundary():
    fifteen = "a" * 15
    sixteen = "a" * 16
    assert trust.check_secret(fifteen, fifteen) == "server_not_configured"
    assert trust.check_secret(sixteen, sixteen) == "ok"
    # the length is measured after stripping
    assert trust.check_secret(sixteen, "  " + fifteen + "  ") == "server_not_configured"


# ------------------------------------------------------- constant-time structure


class _Counting(object):
    """A byte sequence that counts how many items an iteration pulled from it."""

    def __init__(self, values):
        self.values = list(values)
        self.pulled = 0

    def __len__(self):
        return len(self.values)

    def __iter__(self):
        for value in self.values:
            self.pulled += 1
            yield value


@pytest.mark.parametrize("differ_at", [None, 0, 31])
def test_constant_time_visits_every_position(differ_at):
    base = list(range(32))
    other = list(base)
    if differ_at is not None:
        other[differ_at] ^= 0xFF
    left, right = _Counting(base), _Counting(other)
    result = trust._same_digest(left, right)
    assert result is (differ_at is None)
    assert left.pulled == 32
    assert right.pulled == 32


def test_constant_time_digests_are_32_bytes_whatever_the_input():
    assert len(trust._digest("x")) == 32
    assert len(trust._digest("x" * 4096)) == 32
    assert len(trust._digest(b"")) == 32
    assert trust._digest(5) is None
    assert trust._digest(None) is None


def test_constant_time_loop_has_no_early_exit():
    function = _function("_same_digest")
    loops = [n for n in ast.walk(function) if isinstance(n, ast.For)]
    assert len(loops) == 1
    for statement in loops[0].body:
        for node in ast.walk(statement):
            assert not isinstance(node, (ast.Return, ast.Break, ast.Continue)), (
                "the compare loop must not exit early (line {})".format(node.lineno))
    returns = [n for n in ast.walk(function) if isinstance(n, ast.Return)]
    assert len(returns) == 1
    assert returns[0].lineno > loops[0].lineno


def test_constant_time_no_direct_compare_of_secret_values():
    for name in ("secret_matches", "check_secret"):
        for node in ast.walk(_function(name)):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                continue
            operands = [node.left] + list(node.comparators)
            for operand in operands:
                assert not (isinstance(operand, ast.Name)
                            and operand.id in ("provided", "expected")), (
                    "{} compares a raw secret value with == (line {})".format(name, node.lineno))


def test_constant_time_uses_one_implementation_on_both_runtimes():
    """No per-runtime primitive branch: a later one would make the compare plural."""
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            assert called not in ("compare_digest", "FixedTimeEquals")


def test_constant_time_docstring_records_fallback_reason():
    doc = trust.secret_matches.__doc__
    assert "FixedTimeEquals" in doc
    assert ".NET Framework 4.8" in doc
    assert "compare_digest" in doc


def test_constant_time_lengths_do_not_matter():
    assert trust.secret_matches("a" * 16, "a" * 4096) is False
    assert trust.secret_matches("a" * 4096, "a" * 16) is False
    assert trust.secret_matches("a" * 4096, "a" * 4096) is True


def test_constant_time_non_text_values_never_match():
    assert trust.secret_matches(None, None) is False
    assert trust.secret_matches(5, 5) is False
    assert trust.secret_matches(S, None) is False


# ----------------------------------------------------------------------- leaks


class _HashRaisingTheSecret(object):
    """A hashlib stand-in whose failure text contains the secret."""

    def sha256(self, *args, **kwargs):
        raise RuntimeError(SECRET)


def test_secret_never_leaks_when_hashing_fails(monkeypatch, caplog):
    monkeypatch.setattr("revit_mcp.trust.hashlib", _HashRaisingTheSecret())
    with caplog.at_level(logging.DEBUG):
        verdict = trust.check_secret(SECRET, SECRET)
        matched = trust.secret_matches(SECRET, SECRET)
        body, status = trust.auth_failure(verdict)
    assert verdict == "mismatch"
    assert matched is False
    assert status == 401
    assert caplog.records == []
    assert SECRET not in repr((verdict, matched, body, status))


@pytest.mark.parametrize("reason", [SECRET, "ok", None, 7, "mismatch", ["x", SECRET], {"k": SECRET}])
def test_secret_never_in_an_auth_failure_body(reason):
    import json

    body, status = trust.auth_failure(reason)
    assert status == 401
    assert SECRET not in json.dumps(body)
    assert body["auth"] in ("missing", "mismatch", "server_not_configured")


def test_leak_reasons_outside_the_three_become_mismatch():
    for reason in (SECRET, "ok", None, 7, ""):
        assert trust.auth_failure(reason)[0]["auth"] == "mismatch"
    for reason in ("missing", "mismatch", "server_not_configured"):
        assert trust.auth_failure(reason)[0]["auth"] == reason


def test_leak_failure_body_shape_is_fixed():
    for reason in ("missing", "mismatch", "server_not_configured"):
        body, status = trust.auth_failure(reason)
        assert sorted(body) == ["auth", "error", "hint"]
        assert body["error"] == "Mutation rejected: shared secret {}".format(reason)
        assert body["hint"]
        assert status == trust.AUTH_FAILURE_STATUS == 401


def test_leak_trust_module_has_no_logging_or_print():
    tree = _tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in ("logging", "traceback", "warnings")
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in ("logging", "traceback", "warnings")
        elif isinstance(node, ast.Name):
            assert node.id not in ("print", "logger", "logging")
        elif isinstance(node, ast.Attribute):
            assert node.attr not in ("stderr", "stdout")


# ------------------------------------------------------------- state and imports


def test_stateless_trust_module_has_no_global_state():
    for node in ast.walk(_tree()):
        assert not isinstance(node, (ast.Global, ast.Nonlocal))


def test_stateless_concurrent_verdicts_match_sequential():
    rows = [args for args, _ in VERDICT_TABLE]
    sequential = [trust.check_secret(*args) for args in rows]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(lambda a=args: trust.check_secret(*a)) for args in rows * 20]
        concurrent = [future.result() for future in futures]
    assert concurrent == sequential * 20


def test_trust_imports_nothing_from_revit():
    absolute, relative = set(), set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            absolute.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.add(node.module)
            else:
                absolute.add(node.module)
    assert absolute == set(["hashlib"])
    assert relative == set(["textutils"])


def test_trust_source_never_names_a_route_decorator_or_hand_parse():
    with open(TRUST_PATH, encoding="utf-8") as handle:
        text = handle.read()
    assert "@api.route(" not in text
    assert "json.loads(request.data)" not in text
    assert re.search(r"\bf[\"']", text) is None


# ---------------------------------------------------------------------- methods


@pytest.mark.parametrize("method", ["GET", "get", " GET ", "HEAD", "head", b"GET"])
def test_method_reads_are_ungated(method):
    assert trust.gate_applies(method) is False


@pytest.mark.parametrize("method", ["POST", "post", "PUT", "DELETE", "PATCH", "OPTIONS", "", None, 7, b"\xff"])
def test_method_everything_else_is_gated(method):
    assert trust.gate_applies(method) is True


def test_method_every_route_is_get_or_post():
    routes = route_inventory()
    decorators = 0
    for entry in sorted(os.listdir(REVIT_MCP_DIR)):
        if entry.endswith(".py"):
            with open(os.path.join(REVIT_MCP_DIR, entry), encoding="utf-8") as handle:
                decorators += handle.read().count("@api.route(")
    assert len(routes) == decorators, "the inventory walker missed a route"

    for route in routes:
        assert route.methods, "{} declares no methods".format(route.path)
        assert set(route.methods) <= set(["GET", "POST"]), route.path

    status = [r for r in routes if r.path.strip("/") == "status"]
    assert len(status) == 1
    assert status[0].methods == ["GET"]

    assert sum(1 for r in routes if r.methods == ["POST"]) >= 30
    for route in routes:
        gated = any(trust.gate_applies(m) for m in route.methods)
        assert gated is ("POST" in route.methods), route.path
        if route.methods == ["GET"]:
            assert trust.gate_applies("GET") is False


# ------------------------------------------------------------------ secret file


def test_secret_file_bytes_normalization():
    token = "a" * 20
    assert trust.secret_from_bytes(b"\xef\xbb\xbf" + token.encode()) == token
    assert trust.secret_from_bytes(token.encode() + b"\r\n") == token
    assert trust.secret_from_bytes(b"  " + token.encode() + b"  ") == token
    assert trust.secret_from_bytes(b"\t" + token.encode() + b"\n\n") == token


@pytest.mark.parametrize("raw", [
    b"", b"   ", b"\r\n", b"a" * 15, "a" * 20, None, 5,
    ("a" * 20).encode("utf-16"), ("a" * 20).encode("utf-16-le"),
    b"\xff\xfe\x00", b"abcdefghij\x00klmnopqrstuvw",
])
def test_secret_file_bytes_unusable_input_gives_none(raw):
    assert trust.secret_from_bytes(raw) is None


def test_secret_file_cyrillic_round_trips():
    assert trust.secret_from_bytes(CYRILLIC.encode("utf-8")) == CYRILLIC
    assert trust.secret_from_bytes(b"\xef\xbb\xbf" + CYRILLIC.encode("utf-8") + b"\r\n") == CYRILLIC


def test_secret_file_read_returns_the_token(tmp_path):
    path = tmp_path / "_bridge_secret"
    path.write_bytes(b"\xef\xbb\xbf" + SECRET.encode() + b"\r\n")
    assert trust.read_secret_file(str(path)) == SECRET


def test_secret_file_missing_directory_and_unreadable_give_none(tmp_path, monkeypatch):
    assert trust.read_secret_file(str(tmp_path / "absent")) is None
    assert trust.read_secret_file(str(tmp_path)) is None
    assert trust.read_secret_file(None) is None
    assert trust.read_secret_file("bad\x00path") is None

    path = tmp_path / "_bridge_secret"
    path.write_bytes(SECRET.encode())

    def refuse(*args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr("builtins.open", refuse)
    assert trust.read_secret_file(str(path)) is None


def test_secret_file_name_constant():
    assert trust.SECRET_FILE_NAME == "_bridge_secret"
    assert trust.MIN_SECRET_LENGTH == 16
