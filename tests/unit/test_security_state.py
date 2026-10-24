# -*- coding: utf-8 -*-
"""revit_mcp/security.py: the load-time state and the per-route gate (D-01, D-04, INTG-02,
INTG-03, SEC-06; Phase 5 plan 05-01). Needs no Revit.

initialize() is pinned on temporary extension trees, the gate (gate_or_response) and the
open-read strip (strip_envelope) on request doubles. The fake pyRevit holds only
``routes.make_response``, so a refusal comes back as a (status, data) pair. Plan 05-16
adds the startup rows to this file (every name contains "startup").
"""

import ast
import builtins
import importlib.util
import json
import os
import sys
import types
import unicodedata

import pytest

from gate_support import TEST_SECRET, configure_gate, enveloped_body
from revit_mcp import integrity, security, trust
from revit_mcp.textutils import parse_request_data

WRONG_SECRET = "wrong-secret-0123456789-abcdefXYZ-nope"
SECURITY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "revit_mcp", "security.py")

_REAL_OPEN = builtins.open

TREE = {
    "startup.py": b"# -*- coding: utf-8 -*-\r\nSTARTUP = 1\r\n",
    "extension.json": b'{"name": "genpro_revit_mcp"}\n',
    "revit_mcp/__init__.py": b"# -*- coding: utf-8 -*-\n",
    "revit_mcp/alpha.py": b"# -*- coding: utf-8 -*-\nALPHA = 1\n",
    "revit_mcp/beta.py": b"# -*- coding: utf-8 -*-\nBETA = 2\n",
}


@pytest.fixture(autouse=True)
def fake_pyrevit(monkeypatch):
    """pyRevit reduced to routes.make_response, and a state that starts uninitialized."""

    def make_response(data=None, status=200, headers=None):
        return types.SimpleNamespace(status=status, data=data)

    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=types.SimpleNamespace(make_response=make_response)))
    monkeypatch.setattr(security, "_STATE", None)


def _write(root, relpath, data):
    path = os.path.join(root, *relpath.split("/"))
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with _REAL_OPEN(path, "wb") as handle:
        handle.write(data)
    return path


def _build_tree(root, secret=TEST_SECRET, manifest=True):
    """An extension tree: files, a secret file and (optionally) a matching manifest."""
    contents = dict(TREE)
    for relpath, data in contents.items():
        _write(root, relpath, data)
    if secret is not None:
        _write(root, "revit_mcp/" + trust.SECRET_FILE_NAME,
               secret.encode("utf-8") if not isinstance(secret, bytes) else secret)
    if manifest:
        files = dict((k, integrity.hash_normalized(v)) for k, v in contents.items())
        _write(root, "_manifest.json", json.dumps(
            {"schema": 1, "generated_at": "2026-10-24T00:00:00Z", "commit": "0" * 40,
             "files": files}).encode("utf-8"))
    return contents


def _initialize(root):
    security.initialize(root, os.path.join(root, "revit_mcp"))
    return security._STATE


def _request(data):
    return types.SimpleNamespace(data=data)


def _mismatch(*files):
    return {"state": trust.INTEGRITY_MISMATCH, "reason": None,
            "modified": sorted(files), "missing": [], "unexpected": []}


# ------------------------------------------------------------------------- initialize


def test_initialize_on_a_complete_tree_holds_the_secret_and_a_match(tmp_path):
    root = str(tmp_path / "ext")
    _build_tree(root)
    state = _initialize(root)
    assert state["secret"] == TEST_SECRET
    assert state["integrity"]["state"] == trust.INTEGRITY_MATCH


def test_initialize_returns_nothing_that_contains_the_secret(tmp_path):
    root = str(tmp_path / "ext")
    _build_tree(root)
    assert security.initialize(root, os.path.join(root, "revit_mcp")) is None


@pytest.mark.parametrize("secret", [None, b"", b"   \r\n", b"short-secret"],
                         ids=["absent", "empty", "blank", "too-short"])
def test_initialize_reads_an_unusable_secret_file_as_none(tmp_path, secret):
    root = str(tmp_path / "ext")
    _build_tree(root, secret=secret)
    assert _initialize(root)["secret"] is None


def test_initialize_without_a_manifest_is_unverifiable_manifest_missing(tmp_path):
    root = str(tmp_path / "ext")
    _build_tree(root, manifest=False)
    result = _initialize(root)["integrity"]
    assert (result["state"], result["reason"]) == (
        trust.INTEGRITY_UNVERIFIABLE, trust.REASON_MANIFEST_MISSING)


def test_initialize_with_a_modified_and_an_extra_file_is_a_verified_mismatch(tmp_path):
    root = str(tmp_path / "ext")
    _build_tree(root)
    _write(root, "revit_mcp/alpha.py", b"ALPHA = 999\n")
    _write(root, "revit_mcp/_zz_probe.py", b"PROBE = 1\n")
    result = _initialize(root)["integrity"]
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert result["modified"] == ["revit_mcp/alpha.py"]
    assert result["unexpected"] == ["revit_mcp/_zz_probe.py"]
    assert result["missing"] == []


def test_initialize_recomputes_everything_on_every_call(tmp_path):
    root = str(tmp_path / "ext")
    _build_tree(root)
    assert _initialize(root)["secret"] == TEST_SECRET
    os.remove(os.path.join(root, "revit_mcp", trust.SECRET_FILE_NAME))
    _write(root, "revit_mcp/alpha.py", b"ALPHA = 2\n")
    second = _initialize(root)
    assert second["secret"] is None
    assert second["integrity"]["state"] == trust.INTEGRITY_MISMATCH


def test_an_unexpected_exception_propagates_and_leaves_the_gate_closed(tmp_path, monkeypatch):
    root = str(tmp_path / "ext")
    _build_tree(root)
    security.initialize(root, os.path.join(root, "revit_mcp"))
    assert security._STATE is not None

    def boom(_root):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(security.integrity, "check_integrity", boom)
    with pytest.raises(RuntimeError):
        security.initialize(root, os.path.join(root, "revit_mcp"))
    assert security._STATE is None
    refusal = security.gate_or_response(_request(enveloped_body({"a": 1})))
    assert refusal.status == 401 and refusal.data["auth"] == "server_not_configured"


# ------------------------------------------------------------------------------ gate


def test_the_gate_before_initialize_answers_401_server_not_configured():
    request = _request(enveloped_body({"a": 1}))
    refusal = security.gate_or_response(request)
    assert refusal.status == 401
    assert refusal.data["auth"] == "server_not_configured"
    assert "outcome" not in refusal.data


def test_the_gate_without_an_envelope_answers_401_missing(monkeypatch):
    configure_gate(monkeypatch)
    refusal = security.gate_or_response(_request(enveloped_body({"a": 1}, secret=None)))
    assert refusal.status == 401 and refusal.data["auth"] == "missing"


def test_the_gate_with_a_wrong_secret_answers_401_mismatch(monkeypatch):
    configure_gate(monkeypatch)
    refusal = security.gate_or_response(_request(enveloped_body({"a": 1}, WRONG_SECRET)))
    assert refusal.status == 401 and refusal.data["auth"] == "mismatch"


def test_the_gate_with_a_server_that_has_no_secret_answers_401_server_not_configured(monkeypatch):
    configure_gate(monkeypatch, secret=None)
    refusal = security.gate_or_response(_request(enveloped_body({"a": 1})))
    assert refusal.status == 401 and refusal.data["auth"] == "server_not_configured"


def test_the_gate_with_the_valid_secret_proceeds_and_removes_the_envelope(monkeypatch):
    configure_gate(monkeypatch)
    request = _request(enveloped_body({"a": 1, "b": [2]}))
    assert security.gate_or_response(request) is None
    assert json.loads(request.data.decode("utf-8")) == {"a": 1, "b": [2]}


def test_the_gate_with_a_mismatch_answers_423_naming_the_sorted_files(monkeypatch):
    configure_gate(monkeypatch, integrity=_mismatch("revit_mcp/zeta.py", "revit_mcp/alpha.py"))
    request = _request(enveloped_body({"a": 1}))
    refusal = security.gate_or_response(request)
    assert refusal.status == 423
    assert refusal.data["files"] == ["revit_mcp/alpha.py", "revit_mcp/zeta.py"]
    assert b"_mcp" in request.data, "a refused request is left as it arrived"


def test_a_wrong_secret_with_a_mismatch_is_still_a_401(monkeypatch):
    configure_gate(monkeypatch, integrity=_mismatch("revit_mcp/alpha.py"))
    refusal = security.gate_or_response(_request(enveloped_body({"a": 1}, WRONG_SECRET)))
    assert refusal.status == 401 and refusal.data["auth"] == "mismatch"
    assert "files" not in refusal.data


@pytest.mark.parametrize("reason", [trust.REASON_MANIFEST_MISSING, trust.REASON_READ_ERROR])
def test_unverifiable_integrity_does_not_block(monkeypatch, reason):
    configure_gate(monkeypatch, integrity=trust.unverifiable(reason))
    assert security.gate_or_response(_request(enveloped_body({"a": 1}))) is None


def test_a_verified_match_does_not_block(monkeypatch):
    configure_gate(monkeypatch, integrity={"state": trust.INTEGRITY_MATCH, "reason": None,
                                           "modified": [], "missing": [], "unexpected": []})
    assert security.gate_or_response(_request(enveloped_body({"a": 1}))) is None


# ------------------------------------------------------------------------ rewrite table


@pytest.mark.parametrize("as_type,expected_type", [
    ("bytes", bytes), ("text", str), ("dict", dict)])
def test_the_gate_rewrites_data_in_the_type_it_arrived_in(monkeypatch, as_type, expected_type):
    configure_gate(monkeypatch)
    request = _request(enveloped_body({"a": 1}, as_type=as_type))
    assert security.gate_or_response(request) is None
    assert type(request.data) is expected_type
    assert parse_request_data(request.data) == {"a": 1}


@pytest.mark.parametrize("as_type,expected", [("bytes", b"{}"), ("text", "{}"), ("dict", {})])
def test_an_envelope_only_body_keeps_the_truthiness_the_route_saw_before(
        monkeypatch, as_type, expected):
    configure_gate(monkeypatch)
    request = _request(enveloped_body({}, as_type=as_type))
    before = bool(request.data)
    assert security.gate_or_response(request) is None
    assert request.data == expected
    if as_type != "dict":
        assert bool(request.data) is before is True, "RESEARCH Pitfall 3: stays truthy"


def test_cyrillic_values_round_trip_through_parse_request_data(monkeypatch):
    configure_gate(monkeypatch)
    body = {"name": u"Стена Бета", "n": [1]}
    request = _request(enveloped_body(body))
    assert security.gate_or_response(request) is None
    assert isinstance(request.data, bytes)
    assert parse_request_data(request.data) == body
    assert request.data.decode("ascii"), "ensure_ascii keeps the rewritten body ASCII"


@pytest.mark.parametrize("data", [None, b"", b"{not json", b"[1, 2]", "", "null", b"42"],
                         ids=["none", "empty", "invalid", "list", "empty-text", "null", "number"])
def test_an_empty_or_odd_body_is_a_401_missing_and_is_left_untouched(monkeypatch, data):
    configure_gate(monkeypatch)
    request = _request(data)
    refusal = security.gate_or_response(request)
    assert refusal.status == 401 and refusal.data["auth"] == "missing"
    assert request.data == data and type(request.data) is type(data)


@pytest.mark.parametrize("shape", ["none", "no-data-attribute"])
def test_a_missing_request_or_data_attribute_is_a_401_missing(monkeypatch, shape):
    configure_gate(monkeypatch)
    request = None if shape == "none" else types.SimpleNamespace()
    refusal = security.gate_or_response(request)
    assert refusal.status == 401 and refusal.data["auth"] == "missing"


class _FrozenData(object):
    """A request whose ``data`` is readable but cannot be reassigned."""

    def __init__(self, data):
        self._data = data

    @property
    def data(self):
        return self._data


class _UnreadableData(object):
    @property
    def data(self):
        raise RuntimeError("cannot read the body " + TEST_SECRET)


@pytest.mark.parametrize("request_class,payload", [
    (_FrozenData, enveloped_body({"a": 1})), (_UnreadableData, None)],
    ids=["frozen-data", "unreadable-data"])
def test_a_request_the_gate_cannot_handle_fails_closed_and_loud(monkeypatch, request_class, payload):
    configure_gate(monkeypatch)
    request = _FrozenData(payload) if payload is not None else request_class()
    refusal = security.gate_or_response(request)
    assert refusal.status == 500
    assert refusal.data["gate"] == "internal_error"
    assert refusal.data == trust.gate_failure()[0]
    assert TEST_SECRET not in repr(refusal.data) and "cannot read" not in repr(refusal.data)


# ------------------------------------------------------------------ SEC-04 / SEC-02 edges


def test_the_gate_decides_through_trust_check_secret_only(monkeypatch):
    configure_gate(monkeypatch)
    seen = []

    def fake(provided, expected):
        seen.append((provided, expected))
        return trust.AUTH_MISMATCH

    monkeypatch.setattr(trust, "check_secret", fake)
    refusal = security.gate_or_response(_request(enveloped_body({"a": 1})))
    assert refusal.status == 401 and refusal.data["auth"] == "mismatch"
    assert seen == [(TEST_SECRET, TEST_SECRET)]
    # and the other way round: a wrong secret passes when check_secret says so, so the
    # gate holds no compare of its own
    monkeypatch.setattr(trust, "check_secret", lambda provided, expected: trust.AUTH_OK)
    assert security.gate_or_response(_request(enveloped_body({"a": 1}, WRONG_SECRET))) is None


def test_the_gate_source_adds_no_compare_primitive_of_its_own():
    with open(SECURITY_PATH, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add(node.module)
    # System.Net.NetworkInformation: the /status/ bind adapter (_dotnet_listeners, 05-07).
    assert imported == set(["os", "pyrevit", "System.Net.NetworkInformation"]), (
        "no hashlib, hmac or secrets: the compare is trust's")
    with open(SECURITY_PATH, encoding="utf-8") as handle:
        text = handle.read()
    assert "compare_digest" not in text and "hmac" not in text


def test_a_secret_differing_only_in_unicode_normalization_form_is_a_mismatch(monkeypatch):
    composed = u"café-secret-0123456789"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    configure_gate(monkeypatch, secret=composed)
    assert security.gate_or_response(_request(enveloped_body({"a": 1}, composed))) is None
    refusal = security.gate_or_response(_request(enveloped_body({"a": 1}, decomposed)))
    assert refusal.status == 401 and refusal.data["auth"] == "mismatch"


# ---------------------------------------------------------------------- strip_envelope


@pytest.mark.parametrize("state", ["uninitialized", "valid", "wrong", "no-envelope"])
@pytest.mark.parametrize("as_type", ["bytes", "text", "dict"])
def test_strip_envelope_never_refuses_and_removes_the_reserved_key(monkeypatch, state, as_type):
    if state != "uninitialized":
        configure_gate(monkeypatch)
    secret = {"valid": TEST_SECRET, "wrong": WRONG_SECRET}.get(state)
    request = _request(enveloped_body({"a": 1}, secret, as_type=as_type))
    assert security.strip_envelope(request) is None
    assert type(request.data) is {"bytes": bytes, "text": str, "dict": dict}[as_type]
    assert parse_request_data(request.data) == {"a": 1}


def test_strip_envelope_lets_an_open_read_through_a_mismatch_too(monkeypatch):
    configure_gate(monkeypatch, integrity=_mismatch("revit_mcp/alpha.py"))
    request = _request(enveloped_body({"a": 1}, WRONG_SECRET))
    assert security.strip_envelope(request) is None
    assert parse_request_data(request.data) == {"a": 1}


@pytest.mark.parametrize("data", [None, b"", b"{not json", b"[1, 2]", "x", b'{"a": 1}'],
                         ids=["none", "empty", "invalid", "list", "text", "no-envelope-key"])
def test_strip_envelope_leaves_any_other_body_exactly_as_it_arrived(data):
    request = _request(data)
    assert security.strip_envelope(request) is None
    assert request.data is data


def test_strip_envelope_never_raises_on_a_request_it_cannot_read_or_write():
    assert security.strip_envelope(None) is None
    assert security.strip_envelope(types.SimpleNamespace()) is None
    assert security.strip_envelope(_UnreadableData()) is None
    frozen = _FrozenData(enveloped_body({"a": 1}))
    assert security.strip_envelope(frozen) is None
    assert b"_mcp" in frozen.data


# ------------------------------------------------------------------------ leak (SEC-06)


def _every_refusal(monkeypatch):
    refusals = []
    wrong = enveloped_body({"a": 1}, WRONG_SECRET)
    right = enveloped_body({"a": 1})
    none = enveloped_body({"a": 1}, secret=None)
    security._STATE = None
    refusals.append(security.gate_or_response(_request(right)))
    configure_gate(monkeypatch)
    refusals.append(security.gate_or_response(_request(wrong)))
    refusals.append(security.gate_or_response(_request(none)))
    refusals.append(security.gate_or_response(_FrozenData(right)))
    refusals.append(security.gate_or_response(_UnreadableData()))
    configure_gate(monkeypatch, integrity=_mismatch("revit_mcp/alpha.py"))
    refusals.append(security.gate_or_response(_request(right)))
    configure_gate(monkeypatch, secret=None)
    refusals.append(security.gate_or_response(_request(right)))
    return refusals


def test_no_refusal_body_repr_or_log_line_holds_a_secret(monkeypatch, caplog):
    caplog.set_level(0)
    refusals = _every_refusal(monkeypatch)
    security.strip_envelope(_request(enveloped_body({"a": 1}, WRONG_SECRET)))
    assert all(refusal is not None for refusal in refusals)
    for refusal in refusals:
        for text in (json.dumps(refusal.data), repr(refusal), repr(refusal.data)):
            assert TEST_SECRET not in text and WRONG_SECRET not in text
    assert TEST_SECRET not in caplog.text and WRONG_SECRET not in caplog.text
    assert caplog.records == [], "the gate never logs"


def test_no_refusal_echoes_the_request_body(monkeypatch):
    configure_gate(monkeypatch)
    marker = "MARKER-body-value-0123456789"
    refusal = security.gate_or_response(_request(enveloped_body({"a": marker}, WRONG_SECRET)))
    assert marker not in json.dumps(refusal.data)


# --------------------------------------------------------------------- never writes


def _forbidden(name):
    def refuse(*args, **kwargs):
        raise AssertionError("security called {}".format(name))
    return refuse


def test_initialize_gate_and_strip_never_write_anything(tmp_path, monkeypatch):
    root = str(tmp_path / "ext")
    _build_tree(root)

    def guarded_open(path, mode="r", *args, **kwargs):
        if any(flag in str(mode) for flag in "wa+"):
            raise AssertionError("security opened {!r} in mode {!r}".format(path, mode))
        return _REAL_OPEN(path, mode, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", guarded_open)
        for name in ("remove", "rename", "replace", "unlink", "makedirs"):
            guard.setattr(os, name, _forbidden("os." + name))
        security.initialize(root, os.path.join(root, "revit_mcp"))
        request = _request(enveloped_body({"a": 1}))
        assert security.gate_or_response(request) is None
        assert security.strip_envelope(_request(enveloped_body({"a": 1}))) is None
        assert security.gate_or_response(_request(None)).status == 401
    assert security._STATE["secret"] == TEST_SECRET


# ---------------------------------------------------------------------------
# startup.py initializes the gate (plan 05-16, INTG-02, INTG-07, T-05-04)
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALIAS = "genpro_revit_mcp"
HELPERS = ("registry.py", "security.py", "trust.py", "integrity.py", "textutils.py")


def _startup_source():
    with open(os.path.join(REPO_ROOT, "startup.py"), encoding="utf-8") as handle:
        return handle.read()


def test_startup_source_initializes_security_between_identity_and_the_domain_loop():
    source = _startup_source()
    reset = source.index("registry.reset()")
    identity = source.index("initialize_process_identity()")
    call = source.index("security.initialize(")
    loop = source.index("for name in _domain_modules(package)")
    assert reset < identity < call < loop
    tree = ast.parse(source)
    guarded = [n for n in ast.walk(tree) if isinstance(n, ast.Try)
               and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                       and c.func.attr == "initialize"
                       and isinstance(c.func.value, ast.Name) and c.func.value.id == "security"
                       for stmt in n.body for c in ast.walk(stmt))]
    assert len(guarded) == 1
    recorded = [t for h in guarded[0].handlers for st in h.body if isinstance(st, ast.Assign)
                for t in st.targets if isinstance(t, ast.Subscript)
                and isinstance(t.slice, ast.Constant) and t.slice.value == "security"
                and ast.dump(t.value) == ast.dump(ast.parse("registry.FAILED").body[0].value)]
    assert len(recorded) == 1


@pytest.fixture
def startup_tree(tmp_path, monkeypatch):
    """The real startup.py run under CPython from a temporary extension tree."""
    table = {}

    class API(object):
        def __init__(self, name):
            self.name = name

        def route(self, pattern, methods):
            def decorate(fn):
                for method in methods:
                    table[(self.name, method, pattern)] = fn
                return fn
            return decorate

    def make_response(data=None, status=200, headers=None):
        return types.SimpleNamespace(status=status, data=data)

    monkeypatch.setitem(sys.modules, "pyrevit", types.SimpleNamespace(
        routes=types.SimpleNamespace(API=API, make_response=make_response)))

    def drop_alias():
        for name in list(sys.modules):
            if name == ALIAS or name.startswith(ALIAS + "."):
                del sys.modules[name]

    drop_alias()
    package = tmp_path / "revit_mcp"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"# -*- coding: utf-8 -*-\n")
    (package / "example.py").write_bytes(
        b"# -*- coding: utf-8 -*-\n"
        b"def register_example_routes(api):\n"
        b"    @api.route('/status/', methods=['GET'])\n"
        b"    def status():\n"
        b"        return 'ok'\n")
    (tmp_path / "startup.py").write_bytes(
        open(os.path.join(REPO_ROOT, "startup.py"), "rb").read())

    def build(helpers=HELPERS, secret=TEST_SECRET, stubs=None):
        for name in helpers:
            with open(os.path.join(REPO_ROOT, "revit_mcp", name), "rb") as handle:
                (package / name).write_bytes(handle.read())
        for name, text in (stubs or {}).items():
            (package / name).write_bytes(text.encode("utf-8"))
        if secret is not None:
            (package / trust.SECRET_FILE_NAME).write_bytes(secret.encode("utf-8"))

    def load():
        spec = importlib.util.spec_from_file_location("startup_under_test", str(tmp_path / "startup.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    yield build, load, str(tmp_path)
    drop_alias()


def test_startup_loaded_from_a_tree_without_a_manifest_opens_the_gate_with_its_own_secret(startup_tree):
    build, load, root = startup_tree
    build()
    load()
    registry = sys.modules[ALIAS + ".registry"]
    alias_security = sys.modules[ALIAS + ".security"]
    assert alias_security._STATE["secret"] == TEST_SECRET
    assert alias_security._STATE["integrity"]["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert alias_security._STATE["integrity"]["reason"] == trust.REASON_MANIFEST_MISSING
    assert "security" not in registry.FAILED
    assert registry.REGISTERED == ["example"]
    ok = types.SimpleNamespace(data=enveloped_body({"a": 1}))
    assert alias_security.gate_or_response(ok) is None
    assert json.loads(ok.data) == {"a": 1}
    refused = alias_security.gate_or_response(types.SimpleNamespace(data=enveloped_body({"a": 1}, secret=None)))
    assert refused.status == 401 and refused.data["auth"] == "missing"


def test_startup_records_an_initialize_failure_and_still_registers_every_domain(startup_tree):
    build, load, root = startup_tree
    build(helpers=[h for h in HELPERS if h != "security.py"],
          stubs={"security.py": "def initialize(root, package_dir):\n"
                                "    raise RuntimeError('boom')\n"})
    load()
    registry = sys.modules[ALIAS + ".registry"]
    assert registry.FAILED["security"] == "RuntimeError: boom"
    assert registry.REGISTERED == ["example"]


def test_startup_records_a_missing_security_module_and_still_registers_every_domain(startup_tree):
    build, load, root = startup_tree
    build(helpers=[h for h in HELPERS if h != "security.py"])
    load()
    registry = sys.modules[ALIAS + ".registry"]
    assert registry.FAILED["security"].startswith(("ModuleNotFoundError", "ImportError"))
    assert registry.REGISTERED == ["example"]


def test_startup_secret_is_not_in_the_failure_record_or_the_log(startup_tree, caplog):
    build, load, root = startup_tree
    build(helpers=[h for h in HELPERS if h != "security.py"],
          stubs={"security.py": "def initialize(root, package_dir):\n"
                                "    raise RuntimeError('boom')\n"})
    with caplog.at_level("DEBUG"):
        load()
    registry = sys.modules[ALIAS + ".registry"]
    assert TEST_SECRET not in repr(registry.FAILED)
    assert TEST_SECRET not in caplog.text


def test_startup_check_integrity_raising_keeps_the_gate_closed(monkeypatch, tmp_path):
    root = str(tmp_path / "ext")
    _build_tree(root)
    _initialize(root)
    assert security._STATE is not None

    def boom(_root):
        raise RuntimeError("manifest reader exploded")

    monkeypatch.setattr(integrity, "check_integrity", boom)
    with pytest.raises(RuntimeError):
        _initialize(root)
    assert security._STATE is None
    refused = security.gate_or_response(types.SimpleNamespace(data=enveloped_body({"a": 1})))
    assert refused.status == 401
    assert refused.data["auth"] == "server_not_configured"
