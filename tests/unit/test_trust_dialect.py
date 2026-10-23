# -*- coding: utf-8 -*-
"""revit_mcp/trust.py and integrity.py against the engine that will load them.

On 2026-09-08 textutils probed the runtime with `try: unicode / except NameError`;
pyRevit's IronPython 3 engine defines `unicode` as an alias of `str`, so the probe
reported Python 2 there and every POST route answered 500 while the CPython suite
stayed green. This file reconstructs that engine (the `unicode` builtin injected,
textutils, trust and integrity reloaded) and re-runs the verdict, envelope,
integrity and bind tables in it, then fences both modules against every syntax
and standard-library form above the Python 3.4 level that IronPython 3.4 cannot load.
Needs no Revit.
"""

import ast
import builtins
import contextlib
import hashlib
import importlib
import io
import json
import os
import sys
import tokenize

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import conventions  # noqa: E402  (read-only: PY3_ONLY_MODULES is reused, never edited)

from revit_mcp import integrity as _integrity_module  # noqa: E402
from revit_mcp import textutils as _textutils_module  # noqa: E402
from revit_mcp import trust as _trust_module  # noqa: E402
from test_trust_listeners import TABLE as LISTENER_TABLE  # noqa: E402
from test_trust_secret import VERDICT_TABLE  # noqa: E402

REVIT_MCP_DIR = os.path.join(REPO_ROOT, "revit_mcp")
TRUST_PATH = os.path.join(REVIT_MCP_DIR, "trust.py")
INTEGRITY_PATH = os.path.join(REVIT_MCP_DIR, "integrity.py")

SECRET = "unit-secret-0123456789-abcdefXYZ"
_MODULE_ORDER = (_textutils_module, _trust_module, _integrity_module)


# ------------------------------------------------------------ the simulated engine

def _reload_in_order():
    """textutils first (trust imports its aliases), then trust, then integrity."""
    for module in _MODULE_ORDER:
        importlib.reload(module)


@contextlib.contextmanager
def _ironpython3_engine():
    """pyRevit's IronPython 3 engine: `unicode` is a builtin alias of `str`.

    Yields (textutils, trust, integrity) freshly imported under that builtin, and
    always removes the builtin (or puts the previous value back) and reloads the
    three modules again, so later tests see plain CPython modules.
    """
    had = hasattr(builtins, "unicode")
    previous = getattr(builtins, "unicode", None)
    builtins.unicode = str
    try:
        _reload_in_order()
        yield _MODULE_ORDER
    finally:
        if had:
            builtins.unicode = previous
        else:
            del builtins.unicode
        _reload_in_order()


class _IronPython3Json(object):
    """json as IronPython 3 ships it: loads() refuses bytes (verbatim message)."""

    def loads(self, payload, *args, **kwargs):
        if not isinstance(payload, str):
            raise TypeError(
                "the JSON object must be str, not {!r}".format(payload.__class__.__name__)
            )
        return json.loads(payload, *args, **kwargs)


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write(root, relpath, data):
    path = os.path.join(root, *relpath.split("/"))
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "wb") as handle:
        handle.write(data)


def _build_extension_tree(root, integrity):
    """A tiny extension tree with a valid manifest hashed by the reader's own function."""
    files = {
        "startup.py": b"# startup\r\nprint('x')\r\n",
        "revit_mcp/alpha.py": b"A = 1\n",
        "revit_mcp/beta.py": b"B = 2\n",
    }
    for relpath, data in files.items():
        _write(root, relpath, data)
    manifest = {
        "schema": 1,
        "generated_at": "2026-10-23T00:00:00Z",
        "commit": "0" * 40,
        "files": dict((k, integrity.hash_normalized(v)) for k, v in files.items()),
    }
    _write(root, "_manifest.json", json.dumps(manifest).encode("utf-8"))
    return files


def _integrity_rows(trust):
    a, b, s = "revit_mcp/alpha.py", "revit_mcp/beta.py", "startup.py"

    def manifest(**overrides):
        m = {"schema": 1, "files": {a: _digest("a"), b: _digest("b"), s: _digest("s")}}
        m.update(overrides)
        return m

    def observed(**overrides):
        o = {
            "hashes": {a: _digest("a"), b: _digest("b"), s: _digest("s")},
            "present_py": [a, b],
            "unreadable": [],
        }
        o.update(overrides)
        return o

    rows = [
        (manifest(), observed()),
        (manifest(), observed(hashes={a: _digest("x"), b: _digest("b"), s: _digest("s")})),
        (manifest(), observed(hashes={b: _digest("b"), s: _digest("s")})),
        (manifest(), observed(present_py=[a, b, "revit_mcp/_extra.py"])),
        (manifest(), observed(hashes={a: _digest("a"), s: _digest("s")}, unconfirmed=[b])),
        (manifest(), observed(hashes={a: _digest("a"), s: _digest("s")}, unconfirmed=[])),
        (manifest(), observed(unreadable=[a])),
        (manifest(), None),
        (None, observed()),
        (manifest(schema=2), observed()),
        (manifest(files={"../x.py": _digest("a")}), observed()),
        (manifest(files={}), observed()),
        ([], observed()),
    ]
    return [trust.evaluate_integrity(m, o) for m, o in rows]


def _scenario(textutils, trust, integrity, root):
    """Everything the two modules decide, as plain data comparable across engines."""
    real_json = textutils.json
    textutils.json = _IronPython3Json()
    try:
        body = ('{"_mcp": {"secret": "' + "s" * 20 + '"}, "a": 1}').encode("utf-8")
        envelope = trust.split_envelope(body)
        cyrillic = trust.split_envelope('{"a": "ИЗ"}'.encode("utf-8"))
    finally:
        textutils.json = real_json
    return {
        "verdicts": [trust.check_secret(*args) for args, _ in VERDICT_TABLE],
        "envelope": envelope,
        "cyrillic": cyrillic,
        "integrity_rows": _integrity_rows(trust),
        "check_integrity": integrity.check_integrity(root),
        "listeners": [trust.classify_listeners(e, p) for e, p, _ in LISTENER_TABLE],
        "gate": [trust.gate_applies(m) for m in ("GET", "post", b"HEAD", b"POST", None, 7)],
        "secret_file": [
            trust.secret_from_bytes(b"\xef\xbb\xbf" + SECRET.encode("utf-8") + b"\r\n"),
            trust.secret_from_bytes(b"short"),
            trust.secret_from_bytes("x".encode("utf-16")),
        ],
    }


# ------------------------------------------------------- simulation tests (SC1, SEC-04)

def test_ironpython3_engine_the_injection_is_real():
    """Guard the guard: under the engine a NameError probe really reports Python 2."""
    probe = "try:\n    unicode\n    py2 = True\nexcept NameError:\n    py2 = False\n"
    outside = {}
    exec(probe, outside)
    assert outside["py2"] is False
    with _ironpython3_engine() as (textutils, _, _):
        inside = {}
        exec(probe, inside)
        assert inside["py2"] is True
        # ...yet the `bytes is str` discriminator textutils uses still picks Python 3
        assert textutils._BYTES_TYPE is bytes
        assert textutils._TEXT_TYPE is str


def test_ironpython3_engine_trust_keeps_the_python3_aliases():
    with _ironpython3_engine() as (_, trust, integrity):
        assert trust._BYTES_TYPE is bytes
        assert trust._TEXT_TYPE is str
        assert hasattr(integrity, "check_integrity")


def test_ironpython3_engine_results_equal_plain_cpython(tmp_path):
    root = str(tmp_path)
    _build_extension_tree(root, _integrity_module)
    plain = _scenario(_textutils_module, _trust_module, _integrity_module, root)
    with _ironpython3_engine() as (textutils, trust, integrity):
        simulated = _scenario(textutils, trust, integrity, root)
    assert simulated == plain


def test_ironpython3_engine_results_are_not_vacuous(tmp_path):
    """The comparison above only means something if the scenario exercises every branch."""
    root = str(tmp_path)
    _build_extension_tree(root, _integrity_module)
    with _ironpython3_engine() as (textutils, trust, integrity):
        result = _scenario(textutils, trust, integrity, root)
    assert result["verdicts"] == [expected for _, expected in VERDICT_TABLE]
    assert set(result["verdicts"]) == set(["ok", "missing", "mismatch", "server_not_configured"])
    assert result["envelope"] == ({"secret": "s" * 20}, {"a": 1})
    assert result["cyrillic"] == ({}, {"a": "ИЗ"})
    assert result["listeners"] == [expected for _, _, expected in LISTENER_TABLE]
    assert result["check_integrity"]["state"] == "verified_match"
    states = [row["state"] for row in result["integrity_rows"]]
    assert states.count("verified_match") == 1
    assert states.count("verified_mismatch") == 4
    assert states.count("unverifiable") == 8
    assert "absence_unconfirmed" in [row["reason"] for row in result["integrity_rows"]]
    assert result["gate"] == [False, True, False, True, True, True]
    assert result["secret_file"] == [SECRET, None, None]


def test_ironpython3_engine_check_integrity_on_a_changed_tree(tmp_path):
    """A tampered file is a mismatch in the engine too, not only a clean tree."""
    root = str(tmp_path)
    _build_extension_tree(root, _integrity_module)
    _write(root, "revit_mcp/alpha.py", b"A = 999\n")
    _write(root, "revit_mcp/gamma.py", b"G = 3\n")
    plain = _integrity_module.check_integrity(root)
    with _ironpython3_engine() as (_, _, integrity):
        simulated = integrity.check_integrity(root)
    assert simulated == plain
    assert simulated["state"] == "verified_mismatch"
    assert simulated["modified"] == ["revit_mcp/alpha.py"]
    assert simulated["unexpected"] == ["revit_mcp/gamma.py"]


def test_ironpython3_engine_check_integrity_confirms_a_deleted_file(tmp_path):
    """A really deleted file is confirmed by the second read and stays a mismatch in the engine too."""
    root = str(tmp_path)
    _build_extension_tree(root, _integrity_module)
    os.remove(os.path.join(root, "revit_mcp", "beta.py"))
    plain = _integrity_module.check_integrity(root)
    with _ironpython3_engine() as (_, _, integrity):
        simulated = integrity.check_integrity(root)
    assert simulated == plain
    assert simulated["state"] == "verified_mismatch"
    assert simulated["missing"] == ["revit_mcp/beta.py"]


def test_ironpython3_engine_bytes_body_survives_the_json_stand_in():
    """The live failure: a bytes body, `unicode` present, and a json that refuses bytes."""
    with _ironpython3_engine() as (textutils, trust, _):
        real_json = textutils.json
        textutils.json = _IronPython3Json()
        try:
            envelope, payload = trust.split_envelope(
                b'{"_mcp": {"secret": "' + b"s" * 20 + b'"}, "a": 1}'
            )
        finally:
            textutils.json = real_json
    assert envelope == {"secret": "s" * 20}
    assert payload == {"a": 1}


def test_ironpython3_engine_leaves_cpython_modules_behind(tmp_path):
    assert not hasattr(builtins, "unicode")
    with _ironpython3_engine():
        assert builtins.unicode is str
    assert not hasattr(builtins, "unicode")
    assert _textutils_module._BYTES_TYPE is bytes
    assert _trust_module._BYTES_TYPE is bytes
    assert _trust_module._TEXT_TYPE is str
    root = str(tmp_path)
    _build_extension_tree(root, _integrity_module)
    assert _integrity_module.check_integrity(root)["state"] == "verified_match"


def test_ironpython3_engine_is_restored_when_the_body_raises():
    with pytest.raises(RuntimeError):
        with _ironpython3_engine():
            raise RuntimeError("boom")
    assert not hasattr(builtins, "unicode")
    assert _trust_module._BYTES_TYPE is bytes


def test_ironpython3_engine_puts_a_previous_unicode_back():
    builtins.unicode = "sentinel"
    try:
        with _ironpython3_engine():
            assert builtins.unicode is str
        assert builtins.unicode == "sentinel"
    finally:
        del builtins.unicode


# ---------------------------------------------------------------- digest types

class _BytesSubclass(bytes):
    pass


class _FakeSha(object):
    def __init__(self, real, wrap):
        self._real = real
        self._wrap = wrap

    def digest(self):
        return self._wrap(self._real.digest())


class _FakeHashlib(object):
    def __init__(self, wrap):
        self._wrap = wrap

    def sha256(self, data=b""):
        return _FakeSha(hashlib.sha256(data), self._wrap)


@pytest.mark.parametrize("wrap", [bytearray, _BytesSubclass], ids=["bytearray", "bytes_subclass"])
def test_digest_types_do_not_change_the_verdicts(monkeypatch, wrap):
    monkeypatch.setattr(_trust_module, "hashlib", _FakeHashlib(wrap))
    assert _trust_module.check_secret(SECRET, SECRET) == "ok"
    assert _trust_module.check_secret(SECRET.encode("utf-8"), SECRET) == "ok"
    assert _trust_module.check_secret(SECRET + "x", SECRET) == "mismatch"
    assert _trust_module.check_secret("x" + SECRET, SECRET) == "mismatch"
    assert _trust_module.secret_matches(SECRET, SECRET) is True
    assert _trust_module.secret_matches(SECRET, SECRET[:-1] + "!") is False


def test_digest_types_fake_really_is_used(monkeypatch):
    """Guard the guard: the fake hashlib returns the type the test claims."""
    assert type(_FakeHashlib(bytearray).sha256(b"x").digest()) is bytearray
    assert type(_FakeHashlib(_BytesSubclass).sha256(b"x").digest()) is _BytesSubclass
    monkeypatch.setattr(_trust_module, "hashlib", _FakeHashlib(bytearray))
    assert isinstance(_trust_module._digest("x"), bytearray)


# --------------------------------------------------------------- the syntax guard

def _is_name(node, name):
    return isinstance(node, ast.Name) and node.id == name


def _bytes_constant(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, bytes)


def _imported_modules(node):
    """Every dotted module name an absolute import statement names."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and not node.level and node.module:
        return [node.module] + ["{}.{}".format(node.module, a.name) for a in node.names]
    return []


def _py3_only(module):
    for banned in conventions.PY3_ONLY_MODULES:
        if module == banned or module.startswith(banned + "."):
            return True
    return False


def _find_unsupported(source):
    """Sorted names of the constructs in ``source`` that IronPython 3.4 cannot load."""
    found = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            found.add("f-string")
        elif isinstance(node, (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith)):
            found.add("async")
        elif isinstance(node, ast.Await):
            found.add("await")
        elif isinstance(node, ast.Dict) and any(key is None for key in node.keys):
            found.add("dict-unpacking")
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if isinstance(getattr(node, "ctx", ast.Load()), ast.Load) and any(
                isinstance(item, ast.Starred) for item in node.elts
            ):
                found.add("iterable-unpacking")
        elif isinstance(node, ast.Call):
            stars = [i for i, arg in enumerate(node.args) if isinstance(arg, ast.Starred)]
            if len(stars) > 1:
                found.add("multi-star-call")
            if stars and stars[0] != len(node.args) - 1:
                found.add("positional-after-star")
            if len([kw for kw in node.keywords if kw.arg is None]) > 1:
                found.add("multi-doublestar-call")
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "hex":
                found.add("hex-call")
        elif isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.MatMult):
                found.add("matmul")
            if isinstance(node.op, ast.Mod) and _bytes_constant(node.left):
                found.add("bytes-percent")
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.MatMult):
            found.add("matmul")
        elif isinstance(node, ast.AnnAssign):
            found.add("annotation")
        elif isinstance(node, ast.NamedExpr):
            found.add("walrus")
        elif isinstance(node, ast.Attribute):
            if _is_name(node.value, "os") and node.attr == "scandir":
                found.add("os.scandir")
            if _is_name(node.value, "subprocess") and node.attr == "run":
                found.add("subprocess.run")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = node.args
            if args.posonlyargs:
                found.add("posonly")
            every = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
            every += [a for a in (args.vararg, args.kwarg) if a is not None]
            if any(a.annotation is not None for a in every):
                found.add("annotation")
            if getattr(node, "returns", None) is not None:
                found.add("annotation")
        for module in _imported_modules(node):
            if _py3_only(module):
                found.add("py3-only-import")
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NUMBER and "_" in token.string:
            found.add("underscore-literal")
    return sorted(found)


KNOWN_BAD = [
    ('x = f"{1}"', "f-string"),
    ("async def f():\n    pass\n", "async"),
    ("async def f():\n    await g()\n", "await"),
    ("{**a}", "dict-unpacking"),
    ("[*a]", "iterable-unpacking"),
    ("(*a,)", "iterable-unpacking"),
    ("{*a}", "iterable-unpacking"),
    ("f(*a, *b)", "multi-star-call"),
    ("f(**a, **b)", "multi-doublestar-call"),
    ("a @ b", "matmul"),
    ("x: int = 1", "annotation"),
    ("def f(a: int): pass", "annotation"),
    ("def f() -> int: pass", "annotation"),
    ("(y := 1)", "walrus"),
    ("def f(a, /): pass", "posonly"),
    ("1_000", "underscore-literal"),
    ('b"%d" % 1', "bytes-percent"),
    ('b"x".hex()', "hex-call"),
    ('os.scandir(".")', "os.scandir"),
    ("subprocess.run([])", "subprocess.run"),
    ("import pathlib", "py3-only-import"),
    ("from typing import List", "py3-only-import"),
    # more forms of the same constructs
    ("a @= b", "matmul"),
    ("f(*a, b)", "positional-after-star"),
    ("async def f():\n    async with a:\n        pass\n", "async"),
    ("x = [1, *a]", "iterable-unpacking"),
    ("from unittest import mock", "py3-only-import"),
    ("import concurrent.futures", "py3-only-import"),
    ("g = lambda a: (b := a)", "walrus"),
    ("0xDEAD_BEEF", "underscore-literal"),
]

KNOWN_GOOD = [
    "a, *b = x",
    "for a, *b in x:\n    pass\n",
    "f(*a)",
    "f(**a)",
    "f(*a, k=1)",
    "f(a, k=1, **kw)",
    "h.hexdigest()",
    '"%d" % 1',
    'b"x".decode("ascii")',
    'os.listdir(".")',
    "subprocess.Popen([])",
    "import hashlib",
    "from .trust import x",
    "from .typing import x",
    "def f(a, b=1, *args, **kwargs): pass",
    "def f(a, *, k=1): pass",
    "x = 1 if y else 2",
    'print("a {}".format(1))',
]


@pytest.mark.parametrize("source,construct", KNOWN_BAD, ids=[c + ":" + s[:24] for s, c in KNOWN_BAD])
def test_dialect_guard_finds_each_known_bad_construct(source, construct):
    assert construct in _find_unsupported(source)


@pytest.mark.parametrize("source", KNOWN_GOOD)
def test_dialect_guard_accepts_valid_python34_forms(source):
    assert _find_unsupported(source) == []


def test_dialect_guard_known_bad_table_covers_every_planned_construct():
    covered = set(construct for _, construct in KNOWN_BAD)
    assert covered >= set([
        "f-string", "async", "await", "dict-unpacking", "iterable-unpacking",
        "multi-star-call", "multi-doublestar-call", "matmul", "annotation", "walrus",
        "posonly", "underscore-literal", "bytes-percent", "hex-call", "os.scandir",
        "subprocess.run", "py3-only-import",
    ])


def test_dialect_guard_reuses_the_repository_module_list_read_only():
    assert "pathlib" in conventions.PY3_ONLY_MODULES
    assert "typing" in conventions.PY3_ONLY_MODULES


@pytest.mark.parametrize("path", [TRUST_PATH, INTEGRITY_PATH], ids=["trust", "integrity"])
def test_dialect_modules_use_no_construct_above_python34(path):
    with io.open(path, encoding="utf-8") as handle:
        source = handle.read()
    assert _find_unsupported(source) == []


@pytest.mark.parametrize("path", [TRUST_PATH, INTEGRITY_PATH], ids=["trust", "integrity"])
def test_dialect_modules_keep_the_encoding_cookie_and_the_repo_checker_quiet(path):
    with io.open(path, encoding="utf-8") as handle:
        source = handle.read()
    assert source.splitlines()[0] == "# -*- coding: utf-8 -*-"
    assert conventions.check_ironpython_dialect(os.path.basename(path), source) == []


# ----------------------------------------------------------------- import allow-lists

def _imports(path):
    with io.open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    absolute, relative = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.add(node.module)
            else:
                absolute.add(node.module)
    return absolute, relative


def test_dialect_trust_imports_only_hashlib_and_textutils():
    absolute, relative = _imports(TRUST_PATH)
    assert absolute == set(["hashlib"])
    assert relative == set(["textutils"])


def test_dialect_integrity_imports_only_the_allowed_standard_library_and_trust():
    absolute, relative = _imports(INTEGRITY_PATH)
    assert absolute == set(["errno", "hashlib", "json", "os"])
    assert relative == set(["trust"])


def test_dialect_import_helper_detects_a_stray_import(tmp_path):
    """Guard the guard: the allow-list scan sees extra imports in a planted module."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import os\nimport ipaddress\nfrom . import x\nfrom .y import z\n",
        encoding="utf-8",
    )
    absolute, relative = _imports(str(planted))
    assert absolute == set(["os", "ipaddress"])
    assert relative == set([None, "y"])
